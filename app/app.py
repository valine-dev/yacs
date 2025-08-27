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

import bbcode
from app.db import get_db
from captcha.image import ImageCaptcha
from flask import (Flask, Response, redirect, render_template,
                   render_template_string, request, send_file)
from flask_socketio import (ConnectionRefusedError, SocketIO, emit, join_room,
                            leave_room)
from webargs import fields, validate
from webargs.flaskparser import use_args
from werkzeug.middleware.proxy_fix import ProxyFix


# --- INITIALIZATION ---

app = Flask(__name__)

# Read configuration
with open(path.abspath('./config.toml'), 'rb') as file:
    conf = tomllib.load(file)
    # read built-in values
    app.config.update(conf['flask'])
    conf.pop('flask')
    app.config.update(conf)

if app.config["app"]["proxy_fix"]:
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_host=1)

if not path.isdir(app.config['res']['path']):
    mkdir(app.config['res']['path'])

app.logger.setLevel(app.config['app']['log_level'])
logger = app.logger

socketio = SocketIO(app, cors_allowed_origins='*')
conn = get_db(app.config['db']['path'], logger)

# Caches across requests
candidates = dict()
online = dict()
channels = dict()
file_buffer = dict()
valid_tokens = []

# Precalculations
SIZE_MAX_BYTE = app.config['res']['size_max'] * 1000000

# Setup captcha challenge
options = app.config['captcha']['options']
challenge_set = ['', ascii_lowercase][options['lowercase']] + \
                ['', ascii_uppercase][options['uppercase']] + \
                ['', '0123456789'][options['numbers']]
image_captcha = ImageCaptcha()

# --- HELPER FUNCTIONS ---


def push_candidate(identifier, challenge, time):
    if len(candidates) > app.config['captcha']['max_cache']:
        candidates.pop(candidates.keys()[0])
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


def clean_user(nick):
    item = online.pop(nick)
    valid_tokens.remove(item['token'])
    logger.info(f'User {nick} logged out.')


def time_milisecond():
    return round(time() * 1000)


# --- WRAPPERS ---

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.headers.get('Authorization', default=None)
        if not auth:
            return Response(status=401)
        _, nick, token = str(auth).split(' ')
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
        _, nick, token = str(auth).split(' ')
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
    # making captcha
    identifier = str(uuid.uuid1())
    challenge = ''.join(random.choices(
        challenge_set, k=app.config['captcha']['length']))
    push_candidate(identifier, challenge, time())
    data = image_captcha.generate(challenge).read()
    captcha_data = b64encode(data).decode()
    return render_template(
        'index.jinja',
        title=app.config['custom']['title'],
        captcha=captcha_data,
        identifier=identifier
    )


LOGIN_FORM = {
    'nick': fields.Str(required=True, validate=[validate.Length(min=3, max=16), validate.ContainsOnly(list(ascii_lowercase + ascii_uppercase + "0123456789_"))]),
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
        # clean any dangling user
        keys = list(online.keys())
        for user in keys:
            if (time_milisecond() - online[user]['last_heartbeat']) > app.config['app']['timeout']:
                clean_user(user)
        if form['nick'] in online.keys():
            return redirect('/?failed=User+exists')
        token = str(uuid.uuid4())
        is_admin = (form['phrase'] == app.config['app']['admin_phrase'])
        online[form['nick']] = dict(
            token=token,
            is_admin=is_admin,
            last_heartbeat=time_milisecond()
        )
        valid_tokens.append(token)
        return render_template_string(
            '''<form action='/room' name='next' id='next' method='post'><input name='nick' id='nick' type='hidden' value='{{ nick }}' /><input name='token' id='token' type='hidden' value='{{ token }}' /></form><script>document.forms['next'].submit()</script>''',
            nick=form['nick'],
            token=token,
        )
    return redirect('/?failed=Wrong+CAPTCHA')


@app.route('/room-preview', methods=['POST', 'GET'])
def room_preview():
    if not app.config['DEBUG']:
        return Response(status=404)
    online['test'] = {
        'token': 'test',
        'is_admin': True,
        'last_heartbeat': time_milisecond()
    }
    if not 'test' in valid_tokens:
        valid_tokens.append('test')
    return render_template(
        'room.jinja',
        title=app.config['custom']['title'],
        token='test',
        nick='test',
        emotes=app.config['custom']['emoticons'],
        motd=app.config['custom']['motd'],
        is_admin=True
    )


ROOM_FORM = {
    'nick': fields.Str(validate=lambda x: (x in online.keys()), required=True),
    'token': fields.Str(required=True),
}


@app.route('/room', methods=['POST', 'GET'])
@use_args(ROOM_FORM, location='form')
def room_view(form):
    if request.method == 'GET':
        return redirect('/')
    nick = form['nick']
    token = form['token']
    try:
        if online[nick]['token'] != token:
            return redirect('/')
    except:
        return redirect('/')
    return render_template(
        'room.jinja',
        title=app.config['custom']['title'],
        emotes=app.config['custom']['emoticons'],
        nick=nick,
        token=token,
        motd=app.config['custom']['motd'],
        is_admin=online[nick]['is_admin']
    )

# --- SECRET API ---
# ROUTES HERE NEED TO BE CALLED BY LOGGED IN CLIENT SCRIPT


@app.route('/channels')
@login_required
def get_channels():
    auth = request.headers.get('Authorization', default=None)
    nick = str(auth).split(' ')[1]
    res = conn.execute('SELECT * FROM CHANNEL WHERE IS_DELETED=0' +
                       (' AND ADMIN_ONLY=0;', '')[online[nick]["is_admin"]])
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
    file = request.files['file']
    name = file.filename
    mime = file.mimetype
    token = str(auth).split(' ')[2]
    binary = file.read()
    if len(binary) > SIZE_MAX_BYTE:
        return Response(status=400)
    id = str(uuid.uuid4())
    file_buffer[id] = (binary, name, mime, token)
    return {'uuid': id}


@app.route('/submit_upload')
@login_required
def upload_submit():
    auth = request.headers.get('Authorization', default=None)
    if 'recall' in request.args.keys():
        token = str(auth).split(' ')[2]
        requested = request.args['recall']
        if requested not in file_buffer.keys():
            return Response(status=400)
        if file_buffer[requested][3] != token:
            return Response(status=400)
        file_buffer.pop(requested)
        return Response(status=200)
    if 'submit' in request.args.keys():
        token = str(auth).split(' ')[2]
        id = request.args['submit']
        if id not in file_buffer.keys():
            return Response(status=400)
        if file_buffer[id][3] != token:
            return Response(status=400)
        binary, name, mime, _ = file_buffer.pop(id)
        extension = path.splitext(name)[1]
        # Save file
        with open(path.abspath(path.join(app.config['res']['path'], f'{id}.{extension}')), 'xb') as f:
            f.write(binary)
        conn.execute(
            'INSERT INTO RESOURCE (UUID, FILE_NAME, MIME_TYPE) VALUES (?, ?, ?);', (id, name, mime))
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
    nick = str(auth).split(' ')[1]
    priv = conn.execute(
        'SELECT ADMIN_ONLY FROM CHANNEL WHERE ID=?;', (channel_id,))
    if not priv:
        return Response(status=403)
    priv = priv.fetchone()[0]
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
    return send_file(path.abspath(path.join(
        app.config['res']['path'],
        f'{resource_id}.{extension}'
    )), mimetype=row[1], download_name=row[0])

# --- ADMIN APIS ---


@app.route('/channel', methods=['POST', 'UPDATE', 'DELETE'])
@admin_login_required
def channel_control():
    if request.method == 'POST':
        try:
            name = request.get_json()['name']
        except:
            Response(code=415)
        conn.execute(
            'INSERT INTO CHANNEL (NAME, ADMIN_ONLY) VALUES (?, 0)', (name, ))
        return Response(status=200)
    elif request.method == 'UPDATE':
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
    except:
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
    except:
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
    to = json['to']
    is_admin = online[json['nick']]['is_admin']
    res = conn.execute('SELECT id FROM CHANNEL' +
                       (' WHERE ADMIN_ONLY=0;', '')[is_admin])
    ids = [x[0] for x in res.fetchall()]
    if json['nick'] in channels.keys():
        leave_room(channels[json['nick']])
        emit('leaving', {'target': json['nick']}, to=channels[json['nick']])
    if to in ids:
        join_room(to)
        channels[json['nick']] = to
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
    attachments: list = json['attachments']
    time: str = datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S')
    msg = {
        'author': author,
        'datetime': time,
        'body': body,
        'attachments': attachments
    }
    cur = conn.execute('INSERT INTO CHAT (BODY, CHANNEL_ID, AUTHOR) VALUES (?,?,?) RETURNING ID;', (
        body,
        channels[author],
        author
    ))
    (chat_id, ) = cur.fetchone()
    msg.update({'id': chat_id})
    if attachments != []:
        for a in attachments:
            conn.execute(
                'INSERT INTO ATTACHMENT (CHAT_ID, RESOURCE_ID) VALUES (?,?);', (chat_id, a))
    emit('msg_deliver', msg, to=channels[author])


@socketio.on('connect')
def connect_handler(auth):
    try:
        if online[auth['nick']]['token'] != auth['token']:
            return ConnectionRefusedError('Not Authorized')
    except:
        return ConnectionRefusedError('Missing Authorization')
    logger.info(f'User {auth['nick']} logged in.')


@socketio.on('heartbeat')
def heartbeat_handler(json):
    try:
        if online[json['nick']]['token'] != json['token']:
            return
    except:
        return
    online[json['nick']]['last_heartbeat'] = time_milisecond()


def exit():
    conn.close()


atexit.register(exit)
