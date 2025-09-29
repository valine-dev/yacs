from .app import routes, DefaultNamespace
from os import makedirs, path, listdir, rename
import click
from flask import Flask
from .definitions import CONFIG_DEFAULT
import tomllib
from werkzeug.middleware.proxy_fix import ProxyFix
from string import ascii_lowercase, ascii_uppercase
from flask_socketio import SocketIO
from .db import init_db, close_db, migrate_db, clean_resources


def deep_update(dst: dict, src: dict) -> None:
    for k, v in src.items():
        if isinstance(v, dict) and isinstance(dst.get(k), dict):
            deep_update(dst[k], v)
        else:
            dst[k] = v


def create_app(config=None) -> tuple[Flask, SocketIO]:
    app = Flask(__name__)

    # Load config
    app.config.update(CONFIG_DEFAULT)
    if config is not None:
        if path.isfile(path.abspath(config)):
            with open(path.abspath(config), 'rb') as file:
                try:
                    conf = tomllib.load(file)
                except tomllib.TOMLDecodeError as e:
                    app.logger.critical(
                        f'Initialization failed while parsing config file: {e}')
                    app.logger.warning('Starting YACS without config file')
                else:
                    top = conf.get('flask', None)
                    if top:
                        app.config.update(conf.pop('flask'))
                    deep_update(app.config, conf)
    else:
        app.logger.warning('Starting YACS without config file')

    if not path.isdir(app.config['res']['path']):
        makedirs(app.config['res']['path'], exist_ok=True)

    # Set pre-calculated values
    app.config.update({'runtime': {}})
    app.config['runtime']['SIZE_MAX_BYTE'] = app.config['res']['size_max'] * 1000000
    options = app.config['captcha']['options']
    app.config['runtime']['challenge_set'] = ['', ascii_lowercase][options['lowercase']] + \
        ['', ascii_uppercase][options['uppercase']] + \
        ['', '0123456789'][options['numbers']]

    # Configure app instance
    app.logger.setLevel(app.config['app']['log_level'])
    if app.config['app']['proxy_fix']:
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_host=1)

    # Create socket.io instance
    socketio = SocketIO(
        app, cors_allowed_origins=app.config['app']['cors_allowed_origins'])

    # Attach routes
    app.register_blueprint(routes)
    socketio.on_namespace(DefaultNamespace('/'))
    app.teardown_appcontext(close_db)

    # Making sure that db is propperly initialized
    with app.app_context():
        init_db(app.config['db']['path'])


    return (app, socketio)

@click.group()
def main():
    '''Anonymous Internet Chatroom in Y2K'''
    pass

@main.command()
@click.option('-c', '--config', default=None, help='Path to the config file.')
def start(config):
    '''Starting YACS'''

    # Validate given path
    if config is not None:
        if not path.isfile(config):
            click.echo('Config file does not exist!', err=True)
            return 0

    (app, socketio) = create_app(config)

    app.logger.info(
        f'YACS is now running on http://{app.config["app"]["ip"]}:{app.config["app"]["port"]}{' with DEBUG MODE ON' if app.config['DEBUG'] else ''}.')

    # Check misconfigurations
    user_phrase = app.config['app']['user_phrase']
    admin_phrase = app.config['app']['admin_phrase']

    if user_phrase == '' and admin_phrase == 'admin':
        app.logger.warning(
            f'You have not set the passphrases or set exactly as default values, this is not safe!')
        app.logger.warning(
            f'There\'s no passphrase for user and "{admin_phrase}" for admin.')
    if user_phrase == admin_phrase:
        app.logger.critical(
            'user_phrase and admin_phrase shouldn\'t be exactly same!')
        return 0
    if admin_phrase == '':
        app.logger.critical('admin_phrase shouldn\'t be empty!')
        return 0

    socketio.run(
        app,
        host=app.config["app"]["ip"],
        port=app.config["app"]["port"],
        debug=app.config["DEBUG"],
    )

@main.command()
@click.option('-c', '--config', default=None, help='Path to the config file.')
def gc(config):
    '''Clean not needed resources from disk'''
    (app, _) = create_app(config)
    with app.app_context():
        clean_resources(
            app.config['db']['path'],
            app.config['res']['path'],
        )

@main.command()
@click.option('-c', '--config', default=None, help='Path to the config file.')
def migrate(config):
    '''Migrate your YACServer from 0.3.x to 0.4'''
    (app, _) = create_app(config)
    with app.app_context():
        if migrate_db(app.config['db']['path']):
            click.echo("Database fixed!")
        res_path = path.abspath(app.config['res']['path'])
        for file in [x for x in listdir(res_path) if path.isfile(path.join(res_path, x))]:
            corrected = file.replace('..', '.')
            rename(path.join(res_path, file), path.join(res_path, corrected))
        click.echo("Resource naming fixed!")
