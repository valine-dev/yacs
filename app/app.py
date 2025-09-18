import atexit
import random
import tomllib
import uuid
from base64 import b64encode
from datetime import UTC, datetime
from functools import wraps
from os import path, mkdir
from string import ascii_lowercase, ascii_uppercase
from time import time
from collections import OrderedDict

import bbcode
from app.db import get_db
from captcha.image import ImageCaptcha
from flask import (Flask, Response, redirect, render_template,
                   request, send_file, jsonify)
from flask_socketio import (SocketIO, emit, join_room,
                            leave_room, disconnect)
from webargs import fields, validate
from webargs.flaskparser import use_args
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.utils import secure_filename


# --- INITIALIZATION ---

app = Flask(__name__)

# Read configuration
with open(path.abspath('./config.toml'), 'rb') as file:
    conf = tomllib.load(file)
    # read built-in values
    app.config.update(conf['flask'])
    conf.pop('flask')
    app.config.update(conf)

if app.config['app']['proxy_fix']:
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_host=1)

if not path.isdir(app.config['res']['path']):
    mkdir(app.config['res']['path'])

app.logger.setLevel(app.config['app']['log_level'])
logger = app.logger

socketio = SocketIO(app, cors_allowed_origins='*')
conn = get_db(app.config['db']['path'], logger)

# Caches
candidates: OrderedDict = OrderedDict()
online = dict()

# Precalculations
SIZE_MAX_BYTE = app.config['res']['size_max'] * 1000000

# Setup captcha challenge
options = app.config['captcha']['options']
challenge_set = ['', ascii_lowercase][options['lowercase']] + \
                ['', ascii_uppercase][options['uppercase']] + \
                ['', '0123456789'][options['numbers']]
image_captcha = ImageCaptcha()

# --- HELPER FUNCTIONS ---


def get_channel_member(channel_id: int):
    resp = []
    for k, v in online.items():
        cid = v['channel']
        if cid == channel_id:
            resp.append(k)
    return resp


def push_candidate(identifier, challenge, time):
    if len(candidates) >= app.config['captcha']['max_cache']:
        candidates.popitem(last=False)
    candidates[identifier] = (challenge, time)


def verify_candidate(identifier, challenge, time):
    try:
        candidate = candidates.pop(identifier)
    except:
        return False
    if (time - candidate[1]) > app.config['captcha']['expire']:
        return False
    if challenge == candidate[0]:
        return True
    return False


def clean_user(name):
    item = online.pop(name)
    if item['channel'] != 0:
        emit('leaving', {'target': name},
             to=item['channel'], namespace=item['namespace'])
        leave_room(
            item['channel'],
            item['sid'],
            item['namespace']
        )
    disconnect(
        item['sid'],
        item['namespace']
    )
    logger.info(f'User {name} logged out.')


def time_milisecond():
    return round(time() * 1000)


def garbage_collect():
    for k, v in list(online.items()):
        if (time_milisecond() - v['last_heartbeat']) > app.config['app']['timeout']:
            clean_user(k)


@app.errorhandler(422)
@app.errorhandler(400)
def handle_error(err):
    headers = err.data.get('headers', None)
    messages = err.data.get('messages', ['Invalid request.'])
    if headers:
        return jsonify({'errors': messages}), err.code, headers
    else:
        return jsonify({'errors': messages}), err.code

# --- WRAPPERS ---


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.headers.get('Authorization', default=None)
        if not auth:
            return Response(status=401)
        try:
            _, nick, token = str(auth).split(' ')
        except:
            return Response(status=401)
        if nick not in online.keys():
            return Response(status=401)
        if not online[nick]['token'] == token:
            return Response(status=401)
        return f(*args, **kwargs)
    return decorated


def admin_login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.headers.get('Authorization', default=None)
        if not auth:
            return Response(status=401)
        try:
            _, nick, token = str(auth).split(' ')
        except:
            return Response(status=401)
        if nick not in online.keys():
            return Response(status=401)
        if not online[nick]['token'] == token:
            return Response(status=401)
        if not online[nick]['is_admin']:
            return Response(status=401)
        return f(*args, **kwargs)
    return decorated


# --- VIEW ROUTES ---
# ROUTES HERE ARE SPECIFIALLY FOR RENDERING VIEWS

@app.route('/')
def landing_page():
    # get possible failure callback
    failed = request.args.get('failed', default=None)
    if failed:
        failed = failed.replace('+', ' ')
    # making captcha
    identifier = str(uuid.uuid4())
    challenge = ''.join(random.choices(
        challenge_set, k=app.config['captcha']['length']))
    push_candidate(identifier, challenge, time())
    data = image_captcha.generate(challenge).read()
    captcha_data = b64encode(data).decode()
    return render_template(
        'index.jinja',
        title=app.config['custom']['title'],
        captcha=captcha_data,
        identifier=identifier,
        failed=failed
    )


LOGIN_FORM = {
    'nick': fields.Str(required=True, validate=[validate.Length(min=3, max=16), validate.ContainsOnly(list(ascii_lowercase + ascii_uppercase + '0123456789_'))]),
    'phrase': fields.Str(),
    'captcha': fields.Str(required=True),
    'identifier': fields.Str(required=True)
}


@app.route('/auth', methods=['POST'])
@use_args(LOGIN_FORM, location='form')
def auth(form):
    if form['phrase'] != app.config['app']['admin_phrase']:
        if form['phrase'] != app.config['app']['user_phrase']:
            return redirect('/?failed=Wrong+passphrase')

    if verify_candidate(form['identifier'], form['captcha'], time()):
        garbage_collect()
        if form['nick'] in online.keys():
            return redirect('/?failed=User+exists')
        token = str(uuid.uuid4())
        is_admin = (form['phrase'] == app.config['app']['admin_phrase'])
        online[form['nick']] = dict(
            token=token,
            is_admin=is_admin,
            last_heartbeat=time_milisecond(),
            files_pending=dict(),
            channel=0,
            sid=None,
            namespace=None,
            is_uploading=False,
            is_alive=False
        )
        logger.info(f'User {form['nick']} logged in.')
        return redirect(f'/room?nickname={form['nick']}&token={token}')
    return redirect('/?failed=CAPTCHA+failed')


@app.route('/room-preview', methods=['POST', 'GET'])
def room_preview():
    if not app.config['DEBUG']:
        return Response(status=404)
    name = 'test_' + ''.join(random.choices(challenge_set, k=5))
    online[name] = {
        'token': 'test',
        'is_admin': True,
        'last_heartbeat': time_milisecond(),
        'files_pending': dict(),
        'channel': 0,
        'sid': None,
        'namespace': None,
        'is_uploading': False,
        'is_alive': False,
    }
    return render_template(
        'room.jinja',
        title=app.config['custom']['title'],
        token='test',
        nick=name,
        emotes=app.config['custom']['emoticons'],
        motd=app.config['custom']['motd'],
        is_admin=True
    )


ROOM_FORM = {
    'nickname': fields.Str(validate=lambda x: (x in online.keys()), required=True),
    'token': fields.Str(required=True),
}


@app.route('/room')
@use_args(ROOM_FORM, location='query')
def room_view(auth):
    nick = auth['nickname']
    token = auth['token']
    try:
        if online[nick]['token'] != token:
            return redirect('/?failed=Invalid+authentication')
    except:
        return redirect('/?failed=Invalid+authentication')
    if online[nick]['last_heartbeat']:
        if (time_milisecond() - online[nick]['last_heartbeat']) > app.config['app']['timeout']:
            clean_user(nick)
            return redirect('/?failed=Authentication+expired')
    return render_template(
        'room.jinja',
        title=app.config['custom']['title'],
        emotes=app.config['custom']['emoticons'],
        nick=nick,
        token=token,
        motd=app.config['custom']['motd'],
        is_admin=online[nick]['is_admin'],
        timeout=app.config['app']['timeout'],
    )

# --- SECRET API ---
# ROUTES HERE NEED TO BE CALLED BY LOGGED IN CLIENT SCRIPT


@app.route('/channels')
@login_required
def get_channels():
    auth = request.headers.get('Authorization', default=None)
    nick = str(auth).split(' ')[1]
    res = conn.execute(
        'SELECT * FROM CHANNEL WHERE IS_DELETED=0 AND (ADMIN_ONLY=0 OR ?=1)', (online[nick]['is_admin'],))
    channels = []
    for row in res.fetchall():
        channels.append({
            'id': row[0],
            'name': row[1],
            'is_admin': bool(row[3])
        })
    return channels


@app.route('/index_upload', methods=['POST'])
@login_required
def upload_index():
    auth = request.headers.get('Authorization', default=None)
    uploader = str(auth).split(' ')[1]
    if online[uploader]['is_uploading']:
        return Response(status=429)
    # lock
    online[uploader]['is_uploading'] = True

    file = request.files.get("file", default=None)
    if file is None:
        online[uploader]['is_uploading'] = False
        return Response(status=400)

    name = file.filename
    if name is None:
        online[uploader]['is_uploading'] = False
        return Response(status=400)

    name = secure_filename(name)
    mime = file.mimetype
    binary = file.read()
    if len(binary) > SIZE_MAX_BYTE:
        online[uploader]['is_uploading'] = False
        return Response(status=400)
    id = str(uuid.uuid4())
    online[uploader]['files_pending'].update({
        id: (binary, name, mime)
    })
    online[uploader]['is_uploading'] = False
    return {'uuid': id, 'file_name': name}


@app.route('/submit_upload')
@login_required
def upload_submit():
    auth = request.headers.get('Authorization', default=None)
    user = str(auth).split(' ')[1]

    recall = request.args.get('recall', default=None)
    submit = request.args.get('submit', default=None)

    if recall:
        if recall not in online[user]['files_pending'].keys():
            return Response(status=400)
        online[user]['files_pending'].pop(recall)
        return Response(status=200)

    if submit:
        if submit not in online[user]['files_pending'].keys():
            return Response(status=400)
        binary, name, mime = online[user]['files_pending'].pop(submit)

        # Write to disk
        extension = path.splitext(name)[1]
        file_path = path.abspath(
            path.join(app.config['res']['path'], f'{submit}{extension}'))
        with open(file_path, 'xb') as f:
            f.write(binary)

        # Write to DB
        conn.execute(
            'INSERT INTO RESOURCE (UUID, FILE_NAME, MIME_TYPE) VALUES (?, ?, ?);',
            (submit, name, mime)
        )
        return Response(status=200)
    return Response(status=400)


@app.route('/messages/<int:channel_id>')
@login_required
def get_messages(channel_id):
    if channel_id == 0:
        return Response(status=404)
    count = 30
    if 'count' in request.args.keys():
        count = int(request.args['count'])
    offset = 0
    if 'offset' in request.args.keys():
        offset = int(request.args['offset'])

    # check your fucking privilege
    auth = request.headers.get('Authorization', default=None)
    nick = str(auth).split(' ')[1]
    cur = conn.execute(
        'SELECT ADMIN_ONLY FROM CHANNEL WHERE ID=?;', (channel_id,))
    row = cur.fetchone()
    if row is None:
        return Response(status=403)
    priv = row[0]
    if priv == 1 and online[nick]['is_admin'] == 0:
        return Response(status=403)

    # get latest message first
    res = conn.execute(
        'SELECT * FROM CHAT WHERE CHANNEL_ID=? AND IS_DELETED=0 ORDER BY ID DESC LIMIT ? OFFSET ?;', (channel_id, count, offset))
    res = res.fetchall()
    # Process BBCODE
    resp = []
    for row in res:
        cur = conn.execute(
            'SELECT RESOURCE_ID FROM ATTACHMENT WHERE CHAT_ID=?;', (row[0],))
        cur = cur.fetchall()
        attachments = [x[0] for x in cur]
        msg = {
            'id': row[0],
            'author': row[4],
            'datetime': row[2],
            'body': row[1],
            'attachments': attachments
        }
        resp.append(msg)
    return resp


@app.route('/fellows')
@login_required
def get_fellows():
    auth = request.headers.get('Authorization', default=None)
    if auth == None:
        # auth is guaranteed to be valid after decoration
        # so uh this is merely a trick to disable static checker
        return Response(status=400)
    user = auth.split(' ')[1]
    channel = online[user]['channel']
    if channel == 0:
        return Response(status=404)
    return {'fellows': get_channel_member(channel)}

# --- PUBLIC APIS ---


@app.route('/resource_meta/<resource_id>')
def get_resource_meta(resource_id):
    row = conn.execute(
        'SELECT FILE_NAME, MIME_TYPE FROM RESOURCE WHERE IS_EXPIRED=0 AND UUID=?;', (resource_id, ))
    row = row.fetchone()
    if not row:
        return Response(status=404)
    return {
        'filename': row[0],
        'mime': row[1]
    }


@app.route('/resource/<resource_id>')
def get_resource(resource_id):
    row = conn.execute(
        'SELECT FILE_NAME, MIME_TYPE FROM RESOURCE WHERE IS_EXPIRED=0 AND UUID=?;', (resource_id, ))
    row = row.fetchone()
    if not row:
        return Response(status=404)
    extension = path.splitext(row[0])[1]
    file_path = path.abspath(path.join(
        app.config['res']['path'],
        f'{resource_id}.{extension}'
    ))
    if path.exists(file_path):
        return send_file(file_path, mimetype=row[1], download_name=row[0])
    file_path = path.abspath(path.join(
        app.config['res']['path'],
        f'{resource_id}{extension}'
    ))
    if path.exists(file_path):
        return send_file(file_path, mimetype=row[1], download_name=row[0])
    try:
        conn.execute(
            'UPDATE RESOURCE SET IS_EXPIRED=1 WHERE UUID=?;',
            (resource_id, )
        )
    except Exception as e:
        logger.error(
            f'Error deleting resource {resource_id} with exception {e}')
    return Response(status=404)

# --- ADMIN APIS ---


@app.route('/channel', methods=['POST', 'PUT', 'DELETE'])
@admin_login_required
def channel_control():
    if request.method == 'POST':
        try:
            name = request.get_json()['name']
        except:
            return Response(status=415)
        conn.execute(
            'INSERT INTO CHANNEL (NAME, ADMIN_ONLY) VALUES (?, 0)', (name, ))
        return Response(status=200)
    elif request.method == 'PUT':
        if 'sw_priv' in request.args.keys():
            id = int(request.args['sw_priv'])
            conn.execute(
                'UPDATE CHANNEL SET ADMIN_ONLY = 1 - ADMIN_ONLY WHERE ID=?;',
                (id,)
            )
            return Response(status=200)
        elif 'name' in request.args.keys() and 'id' in request.args.keys():
            id = int(request.args['id'])
            name = request.args['name']
            conn.execute(
                'UPDATE CHANNEL SET NAME=? WHERE ID=?;',
                (name, id)
            )
            return Response(status=200)
    elif request.method == 'DELETE':
        if 'id' in request.args.keys():
            id = request.args['id']
            conn.execute(
                'UPDATE CHANNEL SET IS_DELETED=1 WHERE ID=?;',
                (id, )
            )
            return Response(status=200)
    return Response(status=404)


@app.route('/online/<name>', methods=['DELETE'])
@admin_login_required
def kick_user(name):
    if name in online.keys():
        clean_user(name)
        return Response(status=200)
    return Response(status=400)


@app.route('/resource/<res_id>', methods=['DELETE'])
@admin_login_required
def delete_resource(res_id):
    try:
        conn.execute(
            'UPDATE RESOURCE SET IS_EXPIRED=1 WHERE UUID=?;',
            (res_id, )
        )
    except Exception as e:
        logger.error(f'Error deleting resource {res_id} with exception {e}')
        return Response(status=400)
    return Response(status=200)


@app.route('/message/<int:id>', methods=['DELETE'])
@admin_login_required
def delete_msg(id: int):
    try:
        conn.execute(
            'UPDATE CHAT SET IS_DELETED=1 WHERE ID=?;',
            (id, )
        )
    except Exception as e:
        logger.error(f'Error deleting msg {id} with exception {e}')
        return Response(status=400)
    return Response(status=200)


# --- SOCKET EVENTS ---

@socketio.on('updating_channel')
def updated_channel():
    emit('channel_updated')


@socketio.on('sw_channel')
def sw_channel_handler(json):
    try:
        if json['token'] != online[json['nick']]['token']:
            return
    except:
        return

    user = json['nick']
    to = json['to']
    is_admin = online[user]['is_admin']
    res = conn.execute('SELECT id FROM CHANNEL' +
                       (' WHERE ADMIN_ONLY=0;', '')[is_admin])
    ids = [x[0] for x in res.fetchall()]

    if to not in ids:
        return

    current_channel = online[user]['channel']
    if current_channel != 0:
        leave_room(current_channel)
        emit('leaving', {'target': json['nick']}, to=current_channel)
    join_room(to)
    online[user]['channel'] = to
    emit('joining', {'target': json['nick']}, to=to)


@socketio.on('msg_send')
def msg_send_handler(json):
    author: str = json['author']
    token: str = json['token']
    if not author in online.keys():
        return
    if online[author]['token'] != token:
        return
    if json['body'] == '':
        return
    body: str = bbcode.render_html(json['body'])
    attachments: list = json.get('attachments', [])
    time: str = datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S')
    msg = {
        'author': author,
        'datetime': time,
        'body': body,
        'attachments': attachments
    }
    cur = conn.execute('INSERT INTO CHAT (BODY, CHANNEL_ID, AUTHOR) VALUES (?,?,?) RETURNING ID;', (
        body,
        online[author]['channel'],
        author
    ))
    (chat_id, ) = cur.fetchone()
    msg.update({'id': chat_id})
    if attachments != []:
        for a in attachments:
            conn.execute(
                'INSERT INTO ATTACHMENT (CHAT_ID, RESOURCE_ID) VALUES (?,?);', (chat_id, a))
    emit('msg_deliver', msg, to=online[author]['channel'])


@socketio.on('connect')
def connect_handler(auth):
    try:
        if online[auth['nick']]['token'] != auth['token']:
            raise ConnectionRefusedError('Not Authorized')
    except:
        raise ConnectionRefusedError('Missing Authorization')

    try:
        # to make static checking happy
        online[auth['nick']]['sid'] = getattr(request, 'sid', None)
        online[auth['nick']]['namespace'] = getattr(request, 'namespace', None)
    except:
        raise ConnectionRefusedError('No sid or namespace')
    else:
        if (time_milisecond() - online[auth['nick']]['last_heartbeat']) > app.config['app']['timeout']:
            clean_user(auth['nick'])
            raise ConnectionRefusedError('Not Authorized')
        if online[auth['nick']]['is_alive']:
            raise ConnectionRefusedError('Duplicate Session')
        logger.info(f'User {auth['nick']} connected.')
        online[auth['nick']]['is_alive'] = True


@socketio.on('disconnect')
def disconnect_handler():
    nick = None
    for k, v in online.items():
        if v["sid"] == getattr(request, 'sid', None):
            nick = k
    if nick:
        logger.info(f'User {nick} disconnected.')
        online[nick]['is_alive'] = False
        online[nick]['last_heartbeat'] = time_milisecond()


@socketio.on('heartbeat')
def heartbeat_handler(json):
    try:
        if online[json['nick']]['token'] != json['token']:
            return False
    except:
        return False
    online[json['nick']]['is_alive'] = True
    online[json['nick']]['last_heartbeat'] = time_milisecond()


def exit():
    conn.close()


atexit.register(exit)
