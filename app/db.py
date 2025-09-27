import sqlite3
from flask import g, current_app
from os import path, remove
from .definitions import SCHEMA

MIGRATE = '''BEGIN TRANSACTION;

PRAGMA foreign_keys = OFF;

CREATE TABLE AA (
    CHAT_ID INTEGER,
    RESOURCE_ID TEXT,
    FOREIGN KEY (CHAT_ID) REFERENCES CHAT(ID),
    FOREIGN KEY (RESOURCE_ID) REFERENCES RESOURCE(UUID)
);

INSERT INTO AA SELECT * FROM ATTACHMENT;

DROP TABLE ATTACHMENT;

ALTER TABLE AA RENAME TO ATTACHMENT;

PRAGMA foreign_keys = ON;
'''

def init_db(db_path: str):
    if not path.exists(db_path):
        current_app.logger.warning("Database not found!")
        conn = sqlite3.connect(db_path, check_same_thread=False, autocommit=True)
        conn.executescript(SCHEMA)
        current_app.logger.info("Database created and initialized.")
        conn.close()

def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(current_app.config['db']['path'], check_same_thread=False, autocommit=True)
    return g.db

def close_db(e=None):
    db = g.pop('db', None)
    if db:
        db.close()

def migrate(db_path: str):
    '''Fixing schema for ATTACHMENTS'''
    if not path.exists(db_path):
        return False
    
    conn = sqlite3.connect(db_path)
    sql = conn.execute('SELECT sql FROM sqlite_master WHERE name="ATTACHMENT";')
    type = sql.fetchone()[0].split(',')[1]
    if 'INTEGER' not in type:
        return False
    try:
        conn.executescript(MIGRATE)
    except:
        conn.rollback()
        return False
    else:
        conn.commit()
    conn.close()
    return True

def clean_resources(db_path: str, res_path: str):
    conn = sqlite3.connect(db_path)
    cur = conn.execute('SELECT FILE_NAME, UUID FROM RESOURCE WHERE IS_EXPIRED=1')
    expireds = cur.fetchall()
    for expired in expireds:
        extension = path.splitext(expired[0])[1]
        resource_id = expired[1]

        file_path_A = path.abspath(path.join(
            res_path,
            f'{resource_id}.{extension}'
        ))
        file_path_B = path.abspath(path.join(
            res_path,
            f'{resource_id}{extension}'
        ))

        file_path = ""
        if path.exists(file_path_A):
            file_path = file_path_A
        if path.exists(file_path_B):
            file_path = file_path_B

        try:
            remove(file_path)
        except Exception as e:
            current_app.logger.warning(f'Resource {file_path} failed to be removed due to {e}')
        else:
            current_app.logger.info(f'Resource {file_path} removed.')
    conn.close()
