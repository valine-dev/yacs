import random
import uuid
from base64 import b64encode
from datetime import UTC, datetime
from functools import wraps
from os import path
from string import ascii_lowercase, ascii_uppercase
from time import time
from collections import OrderedDict

import bbcode
from flask import (Response, redirect, render_template,
                   request, send_file, jsonify, current_app, Blueprint, g)
from flask.views import MethodView
from flask_socketio import (emit, join_room,
                            leave_room, disconnect, Namespace)
from webargs import fields, validate
from webargs.flaskparser import use_args, use_kwargs
from werkzeug.utils import secure_filename
from captcha.image import ImageCaptcha

from .db import get_db


routes = Blueprint('views', __name__)

# Caches
candidates: OrderedDict = OrderedDict()
online = dict()


# --- HELPER FUNCTIONS ---


def get_channel_member(channel_id: int):
    resp = []
    for k, v in online.items():
        cid = v['channel']
        if cid == channel_id:
            resp.append(k)
    return resp


def push_candidate(identifier, challenge, time):
    if len(candidates) >= current_app.config['captcha']['max_cache']:
        candidates.popitem(last=False)
    candidates[identifier] = (challenge, time)


def verify_candidate(identifier, challenge, time):
    try:
        candidate = candidates.pop(identifier)
    except:
        return False
    if (time - candidate[1]) > current_app.config['captcha']['expire']:
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
    try:
        emit(
            'kicked',
            to=item['sid'],
            namespace=item['namespace']
        )
    except:
        current_app.logger.warning(f"Failed sending kicking event to {name}.")
    disconnect(
        item['sid'],
        item['namespace']
    )
    current_app.logger.info(f'User {name} logged out.')


def time_milisecond():
    return round(time() * 1000)


def garbage_collect():
    for k, v in list(online.items()):
        if (time_milisecond() - v['last_heartbeat']) > current_app.config['app']['timeout']:
            clean_user(k)


@routes.errorhandler(422)
@routes.errorhandler(400)
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
        auth = request.authorization
        if not auth:
            return Response(status=401)
        try:
            nick = auth.get('username')
            token = auth.get('password')
        except:
            return Response(status=401)
        else:
            if nick not in online.keys():
                return Response(status=401)
            if not online[nick]['token'] == token:
                return Response(status=401)
            g.nick = nick
            g.token = token
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth:
            return Response(status=401)
        if not online[auth.get('username')]['is_admin']:
            return Response(status=401)
        return f(*args, **kwargs)
    return decorated


# --- VIEW ROUTES ---
# ROUTES HERE ARE SPECIFIALLY FOR RENDERING VIEWS

@routes.route('/')
def landing_page():
    # get possible failure callback
    failed = request.args.get('failed', default=None)
    if failed:
        failed = failed.replace('+', ' ')
    # making captcha
    identifier = str(uuid.uuid4())
    challenge = ''.join(random.choices(
        current_app.config['runtime']['challenge_set'], k=current_app.config['captcha']['length']))
    push_candidate(identifier, challenge, time())
    image_captcha = ImageCaptcha()
    data = image_captcha.generate(challenge).read()
    captcha_data = b64encode(data).decode()
    return render_template(
        'index.jinja',
        title=current_app.config['custom']['title'],
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


@routes.route('/auth', methods=['POST'])
@use_args(LOGIN_FORM, location='form')
def auth(form):
    if form['phrase'] != current_app.config['app']['admin_phrase']:
        if form['phrase'] != current_app.config['app']['user_phrase']:
            return redirect('/?failed=Wrong+passphrase')

    if verify_candidate(form['identifier'], form['captcha'], time()):
        garbage_collect()
        if form['nick'] in online.keys():
            return redirect('/?failed=User+exists')
        token = str(uuid.uuid4())
        is_admin = (form['phrase'] ==
                    current_app.config['app']['admin_phrase'])
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
        current_app.logger.info(f'User {form['nick']} logged in.')
        return redirect(f'/room?nickname={form['nick']}&token={token}')
    return redirect('/?failed=CAPTCHA+failed')


@routes.route('/room-preview', methods=['POST', 'GET'])
def room_preview():
    if not current_app.config['DEBUG']:
        return Response(status=404)
    name = 'test_' + ''.join(random.choices(ascii_lowercase, k=5))
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
        title=current_app.config['custom']['title'],
        token='test',
        nick=name,
        emotes=current_app.config['custom']['emoticons'],
        motd=current_app.config['custom']['motd'],
        is_admin=True
    )


ROOM_FORM = {
    'nickname': fields.Str(validate=lambda x: (x in online.keys()), required=True),
    'token': fields.Str(required=True),
}


@routes.route('/room')
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
        if (time_milisecond() - online[nick]['last_heartbeat']) > current_app.config['app']['timeout']:
            clean_user(nick)
            return redirect('/?failed=Authentication+expired')
    return render_template(
        'room.jinja',
        title=current_app.config['custom']['title'],
        emotes=current_app.config['custom']['emoticons'],
        nick=nick,
        token=token,
        motd=current_app.config['custom']['motd'],
        is_admin=online[nick]['is_admin'],
        timeout=current_app.config['app']['timeout'],
    )

# --- SECRET API ---
# ROUTES HERE NEED TO BE CALLED BY LOGGED IN CLIENT SCRIPT


@routes.route('/channels')
@login_required
def get_channels():
    nick = g.get('nick')
    conn = get_db()
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


@routes.route('/cache_upload', methods=['POST'])
@login_required
def upload_cache():
    uploader = g.get('nick')
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
    if len(binary) > current_app.config['runtime']['SIZE_MAX_BYTE']:
        online[uploader]['is_uploading'] = False
        return Response(status=400)
    id = str(uuid.uuid4())
    online[uploader]['files_pending'].update({
        id: (binary, name, mime)
    })
    online[uploader]['is_uploading'] = False
    return {'uuid': id, 'file_name': name}


@routes.route('/submit_upload')
@login_required
def upload_submit():
    user = g.get('nick')

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
            path.join(current_app.config['res']['path'], f'{submit}{extension}'))
        with open(file_path, 'xb') as f:
            f.write(binary)

        # Write to DB
        conn = get_db()
        conn.execute(
            'INSERT INTO RESOURCE (UUID, FILE_NAME, MIME_TYPE) VALUES (?, ?, ?);',
            (submit, name, mime)
        )
        return Response(status=200)
    return Response(status=400)


@routes.route('/messages/<int:channel_id>')
@use_kwargs({'count': fields.Int(load_default=15), 'offset': fields.Int(load_default=0)}, location='query')
@login_required
def get_messages(channel_id, count, offset):
    if channel_id == 0:
        return Response(status=404)

    # check your fucking privilege
    nick = g.get('nick')
    conn = get_db()
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


@routes.route('/fellows')
@login_required
def get_fellows():
    user = g.get('nick')
    channel = online[user]['channel']
    if channel == 0:
        return Response(status=404)
    return {'fellows': get_channel_member(channel)}

# --- PUBLIC APIS ---


@routes.route('/resource_meta/<resource_id>')
def get_resource_meta(resource_id):
    conn = get_db()
    row = conn.execute(
        'SELECT FILE_NAME, MIME_TYPE FROM RESOURCE WHERE IS_EXPIRED=0 AND UUID=?;', (resource_id, ))
    row = row.fetchone()
    if not row:
        return Response(status=404)
    return {
        'filename': row[0],
        'mime': row[1]
    }


@routes.route('/resource/<resource_id>')
def get_resource(resource_id):
    conn = get_db()
    row = conn.execute(
        'SELECT FILE_NAME, MIME_TYPE FROM RESOURCE WHERE IS_EXPIRED=0 AND UUID=?;', (resource_id, ))
    row = row.fetchone()
    if not row:
        return Response(status=404)

    extension = path.splitext(row[0])[1]
    file_path = path.abspath(path.join(
        current_app.config['res']['path'],
        f'{resource_id}{extension}'
    ))

    if file_path != '':
        return send_file(file_path, mimetype=row[1], download_name=row[0])

    try:
        conn.execute(
            'UPDATE RESOURCE SET IS_EXPIRED=1 WHERE UUID=?;',
            (resource_id, )
        )
    except Exception as e:
        current_app.logger.error(
            f'Error deleting resource {resource_id} with exception {e}')
    return Response(status=404)

# --- ADMIN APIS ---


class ChannelAPI(MethodView):
    decorators = [login_required, admin_required]

    def __init__(self):
        self.conn = get_db()

    def post(self):
        try:
            name = request.get_json()['name']
        except:
            return Response(status=415)
        self.conn.execute(
            'INSERT INTO CHANNEL (NAME, ADMIN_ONLY) VALUES (?, 0)', (name, ))
        return Response(status=200)

    def put(self):
        if 'sw_priv' in request.args.keys():
            id = int(request.args['sw_priv'])
            self.conn.execute(
                'UPDATE CHANNEL SET ADMIN_ONLY = 1 - ADMIN_ONLY WHERE ID=?;',
                (id,)
            )
            return Response(status=200)
        elif 'name' in request.args.keys() and 'id' in request.args.keys():
            id = int(request.args['id'])
            name = request.args['name']
            self.conn.execute(
                'UPDATE CHANNEL SET NAME=? WHERE ID=?;',
                (name, id)
            )
            return Response(status=200)

    def delete(self):
        if 'id' in request.args.keys():
            id = request.args['id']
            self.conn.execute(
                'UPDATE CHANNEL SET IS_DELETED=1 WHERE ID=?;',
                (id, )
            )
            return Response(status=200)


routes.add_url_rule('/channel', view_func=ChannelAPI.as_view('channel'))


@routes.route('/online/<name>', methods=['DELETE'])
@login_required
@admin_required
def kick_user(name):
    if name in online.keys():
        clean_user(name)
        return Response(status=200)
    return Response(status=400)


@routes.route('/resource/<res_id>', methods=['DELETE'])
@login_required
@admin_required
def delete_resource(res_id):
    conn = get_db()
    try:
        conn.execute(
            'UPDATE RESOURCE SET IS_EXPIRED=1 WHERE UUID=?;',
            (res_id, )
        )
    except Exception as e:
        current_app.logger.error(
            f'Error deleting resource {res_id} with exception {e}')
        return Response(status=400)
    return Response(status=200)


@routes.route('/message/<int:id>', methods=['DELETE'])
@login_required
@admin_required
def delete_msg(id: int):
    conn = get_db()
    try:
        conn.execute(
            'UPDATE CHAT SET IS_DELETED=1 WHERE ID=?;',
            (id, )
        )
    except Exception as e:
        current_app.logger.error(f'Error deleting msg {id} with exception {e}')
        return Response(status=400)
    else:
        # Cleaning up attachments
        attachs_cur = conn.execute(
            'SELECT RESOURCE_ID FROM ATTACHMENT WHERE CHAT_ID=?',
            (id, )
        )
        attachs = attachs_cur.fetchall()
        for attach in attachs:
            try:
                conn.execute(
                    'UPDATE RESOURCE SET IS_EXPIRED=1 WHERE UUID=?;',
                    attach
                )
            except:
                current_app.logger.warning(
                    f'Marking {attach[0]} to expired failed.')

        cur = conn.execute(
            'SELECT CHANNEL_ID FROM CHAT WHERE ID=?',
            (id, )
        )
        channel = cur.fetchone()[0]
        emit(
            'msg_delete',
            {'id': id},
            namespace='/',
            to=channel
        )
    return Response(status=200)


# --- SOCKET EVENTS ---

class DefaultNamespace(Namespace):
    def on_connect(self, auth):
        if online.get(auth['nick'], None) is None:
            return False
        try:
            if online[auth['nick']]['token'] != auth['token']:
                return False
        except:
            return False

        try:
            # to make static checking happy
            online[auth['nick']]['sid'] = getattr(request, 'sid', None)
            online[auth['nick']]['namespace'] = getattr(
                request, 'namespace', None)
        except:
            return False
        else:
            if (time_milisecond() - online[auth['nick']]['last_heartbeat']) > current_app.config['app']['timeout']:
                clean_user(auth['nick'])
                return False
            if online[auth['nick']]['is_alive']:
                return False
            current_app.logger.info(f'User {auth['nick']} connected.')
            online[auth['nick']]['is_alive'] = True

    def on_disconnect(self, reason):
        nick = None
        for k, v in online.items():
            if v["sid"] == getattr(request, 'sid', None):
                nick = k
        if nick:
            current_app.logger.info(f'User {nick} disconnected. {reason}')
            online[nick]['is_alive'] = False
            online[nick]['last_heartbeat'] = time_milisecond()

    def on_sw_channel(self, json):
        try:
            if json['token'] != online[json['nick']]['token']:
                return False
        except:
            return False

        user = json['nick']
        to = json['to']
        is_admin = online[user]['is_admin']
        conn = get_db()
        res = conn.execute('SELECT id FROM CHANNEL' +
                           (' WHERE ADMIN_ONLY=0;', '')[is_admin])
        ids = [x[0] for x in res.fetchall()]

        if to not in ids:
            return False

        current_channel = online[user]['channel']
        if current_channel != 0:
            leave_room(current_channel)
            emit('leaving', {'target': json['nick']}, to=current_channel)
        join_room(to)
        online[user]['channel'] = to
        emit('joining', {'target': json['nick']}, to=to)

    def on_msg_send(self, json):
        author: str = json['author']
        token: str = json['token']
        conn = get_db()
        if not author in online.keys():
            return False
        if online[author]['token'] != token:
            return False
        if json['body'] == '':
            return False
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

    def on_heartbeat(self, json):
        try:
            if online[json['nick']]['token'] != json['token']:
                return False
        except:
            return False
        online[json['nick']]['is_alive'] = True
        online[json['nick']]['last_heartbeat'] = time_milisecond()

    def on_updating_channel(self):
        emit('channel_updated')
