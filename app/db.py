import sqlite3
from flask import g, current_app
from os import path
from .definitions import SCHEMA
from logging import Logger


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