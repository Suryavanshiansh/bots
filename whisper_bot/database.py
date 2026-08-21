import sqlite3
import os
from typing import Optional, Dict, Any

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "whispers.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS whispers (
                whisper_id TEXT PRIMARY KEY,
                sender_id INTEGER NOT NULL,
                sender_username TEXT,
                target_id INTEGER,
                target_username TEXT,
                secret_text TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()

def save_whisper(
    whisper_id: str,
    sender_id: int,
    sender_username: Optional[str],
    target_id: Optional[int],
    target_username: Optional[str],
    secret_text: str
):
    with get_db() as conn:
        conn.execute("""
            INSERT INTO whispers (whisper_id, sender_id, sender_username, target_id, target_username, secret_text)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (whisper_id, sender_id, sender_username, target_id, target_username, secret_text))
        conn.commit()

def get_whisper(whisper_id: str) -> Optional[Dict[str, Any]]:
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM whispers WHERE whisper_id = ?", (whisper_id,))
        row = cur.fetchone()
        if row:
            return dict(row)
    return None

if __name__ == "__main__":
    init_db()
    print("Database initialized successfully!")
