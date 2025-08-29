# YACS
Yet Another Chatroom Script

Inspired by [LE-CHAT-PHP](https://github.com/DanWin/le-chat-php)


## Featuring

- Multiple channels.
- Admins.
- Files and embedded images/videos.
- BBCode.
- CAPTCHA.
- Vanilla HTML & CSS & JS.
- No Cookies, it's bad for your teeth.

## Try It Out Right Now!

Join [The YACS Demo Server](https://chat.valine0x.icu) with passphrase **`the-yacs`** to evaluate how it goes! ~~For free!~~

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

Consult <a href="docs/manual.md">User Manual</a> for guidance.

## Configuration

Copy the following to `config.toml` and make sure you change the phrases.

```toml
[flask]
# here you can configure built-in config values defined by flask
DEBUG = true

[app]
# The app itself will only exposed through plain HTTP and it's strongly discorage to do so directly to public web. Use a reverse proxy to encrypt public connection over HTTP.
ip = "0.0.0.0"
port = 8080

admin_phrase = "CHANGE_ME_ADMIN"
# set user_phrase to empty will expose chatroom to the public
user_phrase = "CHANGE_ME"

log_level = "DEBUG"
timeout = 5000 # in milisecond, use for heartbeat

# Set to true only when the app is behind a reverse proxy!
# Make sure X-Forwarded-For and X-Forwarded-Host are properly set!
proxy_fix = false


[custom]
title = "The YACS"
motd = "Hello!\nRule No.1"

# These are the emotes that will rendered to the webpage 
emoticons = [
    "( ﾟ∀。)",
    "Insert Anything",
    "⭐"
]


[res]
path = "./resource" # Relative to project's root
size_max = 1024 # In Megabytes


[captcha]
length = 4
max_cache = 60
expire = 120 # Expire time in seconds

[captcha.options]
# you don't want to have all of them turn on, it'll be confusing
numbers = false
lowercase = true
uppercase = false

[db]
path = "./yacs.db"
```


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
