SCHEMA = '''PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS CHAT (
    ID INTEGER PRIMARY KEY AUTOINCREMENT,
    BODY TEXT NOT NULL,
    CREATED TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHANNEL_ID INTEGER NOT NULL,
    AUTHOR TEXT NOT NULL,
    IS_DELETED INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (CHANNEL_ID) REFERENCES CHANNEL(ID)
);

CREATE TABLE IF NOT EXISTS CHANNEL (
    ID INTEGER PRIMARY KEY AUTOINCREMENT,
    NAME TEXT NOT NULL,
    IS_DELETED INTEGER NOT NULL DEFAULT 0,
    ADMIN_ONLY INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS RESOURCE (
    UUID TEXT PRIMARY KEY,
    FILE_NAME TEXT NOT NULL,
    MIME_TYPE TEXT NOT NULL,
    IS_EXPIRED INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS ATTACHMENT (
    CHAT_ID INTEGER,
    RESOURCE_ID TEXT,
    FOREIGN KEY (CHAT_ID) REFERENCES CHAT(ID),
    FOREIGN KEY (RESOURCE_ID) REFERENCES RESOURCE(UUID)
);

INSERT INTO CHANNEL (NAME,ADMIN_ONLY)
VALUES ('Default Channel', 0);'''

CONFIG_DEFAULT = {
    'DEBUG': True,
    'app': {
        'ip': '0.0.0.0',
        'port': 8080,
        'admin_phrase': 'admin',
        'user_phrase': '',
        'log_level': 'INFO',
        'timeout': 5000,
        'proxy_fix': False,
        'cors_allowed_origins': '*'
    },
    'custom': {
        'title': 'The YACS',
        'motd': 'Heya!',
        'emoticons': ['(*ﾟ∇ﾟ)'],
    },
    'res': {
        'path': './resource',
        'size_max': 1024
    },
    'captcha': {
        'length': 4,
        'max_cache': 60,
        'expire': 120,
        'options': {
            'numbers': False,
            'lowercase': True,
            'uppercase': False,
        }
    },
    'db': {
        'path': './yacs.db'
    }
}
