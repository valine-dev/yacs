import os
import sqlite3
from logging import Logger
from app.definitions import SCHEMA


def get_db(path: str, logger: Logger) -> sqlite3.Connection:
    if not os.path.exists(path):
        logger.warning("Database not found!")
        conn = sqlite3.connect(path, check_same_thread=False, autocommit=True)
        conn.executescript(SCHEMA)
        logger.info("Database created and initialized.")
        return conn

    conn = sqlite3.connect(path, check_same_thread=False, autocommit=True)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='CHAT';")
    if cursor.fetchone() is None:
        logger.warning("Database not initialized or is CORRUPTED!")
        conn.executescript(SCHEMA)
        logger.info("Database initialized.")
    cursor.close()
    logger.info("Database good!")
    return conn
