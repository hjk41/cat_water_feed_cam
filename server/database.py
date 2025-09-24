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

def delete_older_records_keep_latest(limit=10):
    """Delete records older than the latest `limit`, return deleted rows as dicts."""
    conn = get_conn()
    # Identify IDs to keep
    keep_rows = conn.execute(
        "SELECT id FROM log ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    keep_ids = {r[0] for r in keep_rows}

    # Collect rows to delete (id, image_path)
    del_rows = conn.execute(
        "SELECT id, image_path FROM log WHERE id NOT IN (" + ",".join(["?"] * len(keep_ids)) + ")",
        tuple(keep_ids) if keep_ids else tuple()
    ).fetchall() if keep_ids else []

    if del_rows:
        del_ids = [r[0] for r in del_rows]
        conn.execute(
            "DELETE FROM log WHERE id IN (" + ",".join(["?"] * len(del_ids)) + ")",
            tuple(del_ids)
        )
        conn.commit()
    conn.close()
    return [{"id": r[0], "image_path": r[1]} for r in del_rows]

init_db()