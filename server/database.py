import sqlite3
from datetime import datetime
from pathlib import Path

DB_FILE = "detect.db"
Path(DB_FILE).touch()

def get_conn():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_conn()
    conn.execute(
        """CREATE TABLE IF NOT EXISTS log(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT,
            image_path TEXT,
            cat INTEGER,
            error TEXT)"""
    )
    conn.commit()
    conn.close()

def insert_record(image_path: str, cat: bool, error: str = None):
    conn = get_conn()
    conn.execute("INSERT INTO log(ts, image_path, cat, error) VALUES (?,?,?,?)",
                 (datetime.now().isoformat(), image_path, int(cat), error))
    conn.commit()
    conn.close()

def get_recent_logs(limit=20):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM log ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

init_db()