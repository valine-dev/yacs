# YACS
Yet Another Chatroom Script

Inspired by [LE-CHAT-PHP](https://github.com/DanWin/le-chat-php)


## Featuring

- Multiple channels.
- Admins.
- Files and embedded images.
- BBCode.
- CAPTCHA.
- Vanilla HTML & CSS & JS.
- No Cookies, it's bad for your teeth.

## Deploying

### 1. Install uv.

```bash
# Install with pip.
$ pip install uv

# Install on macOS and Linux.
$ curl -LsSf https://astral.sh/uv/install.sh | sh

# Install on Windows.
$ powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### 2. Clone the repo.
```bash
$ git clone https://github.com/valine-dev/yacs.git
$ cd yacs
```

### 3. Fill out the form, will ya?
```bash
$ vi ./config.toml
```
**MAKE SURE YOU HAVE SET YOUR OWN `admin_phrase` AND `user_phrase`**

See <a href="## Configuration">Configuration</a> for more detail.

### 4. Start the server

This will install the venv and dependencies along the way.

```bash
$ uv run main.py
```

## Usage

### Permission control

Use the passphrase to log in to the chatroom (you can always change it in the config file). To manage channels and possibly delete chats, use the admin passphrase to log in.

## Configuration

The configuration file `config.toml` is self-explanatory already; however, you may need to consult the following if you are confused by some of the entries.

|Option|Description|
|:----:|:----------|
|flask.*|See [Flask's Documentation](https://flask.palletsprojects.com/en/stable/config/#builtin-configuration-values) for more information.|
|custom.*|Here you customize your website with a lighter effort.|
|res.path|You can set a relative path, but remember it's relative to project's root directory, the same directory with this config file.|
|res.size_max|in MB.|
|captcha.options.*|It's not suggested to have all of them set to true at once since it'll be confusing|


## Customization

Yes, you can rewrite templates in `./app/templates/` and static assets in `./app/static/` to customize ya site. It's written in jinja2 template syntax.

## Acknowledgement
YACS will not be possible without following existing projects.

- [98.css](https://github.com/jdan/98.css)
- [flask](https://github.com/pallets/flask/)
- [bbcode](https://github.com/dcwatson/bbcode)
- [webargs](https://github.com/marshmallow-code/webargs)
- [captcha](https://github.com/lepture/captcha)
- [flask-socketio](https://github.com/miguelgrinberg/flask-socketio)


## Loicense
Oi mate! Got a loicense for that project Govna? Yes, and it is the best one.

YACS is licensed under WTFTPL with NO WARRANTY.

<a href="http://www.wtfpl.net/"><img
       src="http://www.wtfpl.net/wp-content/uploads/2012/12/wtfpl-badge-4.png"
       width="80" height="15" alt="WTFPL" /></a>