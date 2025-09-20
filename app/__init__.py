from .app import app, socketio, initialization
from os.path import isfile
import click

@click.command()
@click.option('-c', '--config', default=None, help='Path to the config file.')
def main(config):
    '''Entry point for YACS.'''
    if config is not None:
        if not isfile(config):
            click.echo('Config file does not exist!', err=True)
            return 0
    result = initialization(config)
    if result != 'ok':
        click.echo(f'Initialization failed while parsing config file: {result}')
        return 0
    app.logger.info(f'YACS is now running on http://{app.config["app"]["ip"]}:{app.config["app"]["port"]}{' with DEBUG MODE ON' if app.config['DEBUG'] else ''}.')
    user_phrase = app.config['app']['user_phrase']
    admin_phrase = app.config['app']['admin_phrase']

    if user_phrase == '' and admin_phrase == 'admin':
        app.logger.warning(f'You have not set the passphrases or set exactly as default values, this is not safe!')
        app.logger.warning(f'There\'s no passphrase for user and "{admin_phrase}" for admin.')
    if user_phrase == admin_phrase:
        app.logger.critical('user_phrase and admin_phrase shouldn\'t be exactly same!')
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