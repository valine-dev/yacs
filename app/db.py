import os
import sqlite3
from logging import Logger

def get_db(path: str, logger: Logger) -> sqlite3.Connection:
    if not os.path.exists(path):
        logger.warning("Database not found!")
        conn = sqlite3.connect(path, check_same_thread=False, autocommit=True)
        with open(os.path.abspath("./sql/schema.sql"), encoding="utf-8") as file:
            script = file.read()
            conn.executescript(script)
            logger.info("Database created and initialized.")
        return conn

    conn = sqlite3.connect(path, check_same_thread=False, autocommit=True)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='CHAT';")
    if cursor.fetchone() is None:
        logger.warning("Database not initialized or is CORRUPTED!")
        with open(os.path.abspath("./sql/schema.sql"), encoding="utf-8") as file:
            script = file.read()
            conn.executescript(script)
            logger.info("Database initialized.")
    cursor.close()
    logger.info("Database good.")
    return conn