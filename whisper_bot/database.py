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
                is_seen INTEGER DEFAULT 0,
                seen_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(whispers)")
        existing_cols = [row[1] for row in cur.fetchall()]
        if "is_seen" not in existing_cols:
            conn.execute("ALTER TABLE whispers ADD COLUMN is_seen INTEGER DEFAULT 0")
        if "seen_at" not in existing_cols:
            conn.execute("ALTER TABLE whispers ADD COLUMN seen_at TIMESTAMP")
        conn.commit()

def upsert_user(
    user_id: int,
    username: Optional[str] = None,
    first_name: Optional[str] = None,
    last_name: Optional[str] = None
):
    if not user_id:
        return
    with get_db() as conn:
        conn.execute("""
            INSERT INTO users (user_id, username, first_name, last_name, updated_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE SET
                username = COALESCE(excluded.username, users.username),
                first_name = COALESCE(excluded.first_name, users.first_name),
                last_name = COALESCE(excluded.last_name, users.last_name),
                updated_at = CURRENT_TIMESTAMP
        """, (user_id, username, first_name, last_name))
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

def mark_whisper_seen(whisper_id: str):
    with get_db() as conn:
        conn.execute("""
            UPDATE whispers
            SET is_seen = 1, seen_at = CURRENT_TIMESTAMP
            WHERE whisper_id = ?
        """, (whisper_id,))
        conn.commit()

def get_whisper(whisper_id: str) -> Optional[Dict[str, Any]]:
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM whispers WHERE whisper_id = ?", (whisper_id,))
        row = cur.fetchone()
        if row:
            return dict(row)
    return None

def get_all_past_targets(sender_id: int, limit: int = 40) -> list[Dict[str, Any]]:
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT 
                w.target_username, 
                w.target_id, 
                MAX(w.created_at) as last_sent,
                u.first_name as user_first_name,
                u.last_name as user_last_name,
                u.username as user_current_username
            FROM whispers w
            LEFT JOIN users u ON (
                (w.target_id IS NOT NULL AND w.target_id = u.user_id) OR
                (w.target_id IS NULL AND w.target_username IS NOT NULL AND LOWER(w.target_username) = LOWER(u.username))
            )
            WHERE w.sender_id = ? AND (w.target_username IS NOT NULL OR w.target_id IS NOT NULL)
            GROUP BY LOWER(IFNULL(w.target_username, '')), w.target_id
            ORDER BY last_sent DESC
            LIMIT ?
        """, (sender_id, limit))
        rows = cur.fetchall()
        results = []
        for row in rows:
            first_name = row["user_first_name"]
            last_name = row["user_last_name"]
            name = None
            if first_name:
                name = f"{first_name} {last_name}".strip() if last_name else first_name.strip()
            
            results.append({
                "target_username": row["target_username"],
                "target_id": row["target_id"],
                "target_name": name
            })
        return results

if __name__ == "__main__":
    init_db()
    print("Database initialized successfully!")
