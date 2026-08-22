import os
import sqlite3
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "guardian.db")

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # Chat settings table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chat_settings (
                chat_id INTEGER PRIMARY KEY,
                media_delay_minutes INTEGER DEFAULT 60,
                delete_edited INTEGER DEFAULT 1,
                sticker_mode TEXT DEFAULT 'nsfw_only',
                updated_at TEXT
            )
        """)
        
        # Approved edit users table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS approved_edit_users (
                chat_id INTEGER,
                user_id INTEGER,
                added_at TEXT,
                PRIMARY KEY (chat_id, user_id)
            )
        """)
        
        # Approved sticker users table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS approved_sticker_users (
                chat_id INTEGER,
                user_id INTEGER,
                added_at TEXT,
                PRIMARY KEY (chat_id, user_id)
            )
        """)

        # Users table for caching usernames and display names
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                updated_at TEXT
            )
        """)
        
        conn.commit()

# --- Users Caching CRUD ---

def upsert_user(user_id: int, username: str, first_name: str, last_name: str):
    now = datetime.utcnow().isoformat()
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO users (user_id, username, first_name, last_name, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username = excluded.username,
                first_name = excluded.first_name,
                last_name = excluded.last_name,
                updated_at = excluded.updated_at
        """, (user_id, username, first_name, last_name, now))
        conn.commit()

def get_user_by_username(username: str):
    clean = username.lstrip("@").lower()
    with get_connection() as conn:
        cursor = conn.execute("SELECT * FROM users WHERE LOWER(username) = ?", (clean,))
        row = cursor.fetchone()
        return dict(row) if row else None

def get_user_by_id(user_id: int):
    with get_connection() as conn:
        cursor = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


# --- Chat Settings CRUD ---

def get_chat_settings(chat_id: int):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM chat_settings WHERE chat_id = ?", (chat_id,))
        row = cursor.fetchone()
        if not row:
            now = datetime.utcnow().isoformat()
            cursor.execute(
                "INSERT INTO chat_settings (chat_id, media_delay_minutes, delete_edited, sticker_mode, updated_at) VALUES (?, ?, ?, ?, ?)",
                (chat_id, 60, 1, 'nsfw_only', now)
            )
            conn.commit()
            return {"chat_id": chat_id, "media_delay_minutes": 60, "delete_edited": 1, "sticker_mode": "nsfw_only"}
        return dict(row)

def update_media_delay(chat_id: int, minutes: int):
    now = datetime.utcnow().isoformat()
    get_chat_settings(chat_id)
    with get_connection() as conn:
        conn.execute(
            "UPDATE chat_settings SET media_delay_minutes = ?, updated_at = ? WHERE chat_id = ?",
            (minutes, now, chat_id)
        )
        conn.commit()

def update_delete_edited(chat_id: int, enabled: int):
    now = datetime.utcnow().isoformat()
    get_chat_settings(chat_id)
    with get_connection() as conn:
        conn.execute(
            "UPDATE chat_settings SET delete_edited = ?, updated_at = ? WHERE chat_id = ?",
            (enabled, now, chat_id)
        )
        conn.commit()

def update_sticker_mode(chat_id: int, mode: str):
    now = datetime.utcnow().isoformat()
    get_chat_settings(chat_id)
    with get_connection() as conn:
        conn.execute(
            "UPDATE chat_settings SET sticker_mode = ?, updated_at = ? WHERE chat_id = ?",
            (mode, now, chat_id)
        )
        conn.commit()

# --- Approved Edit Users CRUD ---

def add_approved_edit_user(chat_id: int, user_id: int) -> bool:
    now = datetime.utcnow().isoformat()
    with get_connection() as conn:
        try:
            conn.execute(
                "INSERT OR REPLACE INTO approved_edit_users (chat_id, user_id, added_at) VALUES (?, ?, ?)",
                (chat_id, user_id, now)
            )
            conn.commit()
            return True
        except Exception:
            return False

def remove_approved_edit_user(chat_id: int, user_id: int) -> bool:
    with get_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM approved_edit_users WHERE chat_id = ? AND user_id = ?",
            (chat_id, user_id)
        )
        conn.commit()
        return cursor.rowcount > 0

def is_user_edit_approved(chat_id: int, user_id: int) -> bool:
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT 1 FROM approved_edit_users WHERE chat_id = ? AND user_id = ?",
            (chat_id, user_id)
        )
        return cursor.fetchone() is not None

# --- Approved Sticker Users CRUD ---

def add_approved_sticker_user(chat_id: int, user_id: int) -> bool:
    now = datetime.utcnow().isoformat()
    with get_connection() as conn:
        try:
            conn.execute(
                "INSERT OR REPLACE INTO approved_sticker_users (chat_id, user_id, added_at) VALUES (?, ?, ?)",
                (chat_id, user_id, now)
            )
            conn.commit()
            return True
        except Exception:
            return False

def remove_approved_sticker_user(chat_id: int, user_id: int) -> bool:
    with get_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM approved_sticker_users WHERE chat_id = ? AND user_id = ?",
            (chat_id, user_id)
        )
        conn.commit()
        return cursor.rowcount > 0

def is_user_sticker_approved(chat_id: int, user_id: int) -> bool:
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT 1 FROM approved_sticker_users WHERE chat_id = ? AND user_id = ?",
            (chat_id, user_id)
        )
        return cursor.fetchone() is not None

# --- Listing Approved Users ---

def get_approved_edit_users(chat_id: int):
    with get_connection() as conn:
        cursor = conn.execute("SELECT user_id FROM approved_edit_users WHERE chat_id = ?", (chat_id,))
        return [row["user_id"] for row in cursor.fetchall()]

def get_approved_sticker_users(chat_id: int):
    with get_connection() as conn:
        cursor = conn.execute("SELECT user_id FROM approved_sticker_users WHERE chat_id = ?", (chat_id,))
        return [row["user_id"] for row in cursor.fetchall()]

# --- Bot Owner Stats & Global Data ---

def get_bot_stats():
    with get_connection() as conn:
        chats = conn.execute("SELECT COUNT(*) as cnt FROM chat_settings").fetchone()["cnt"]
        edits = conn.execute("SELECT COUNT(*) as cnt FROM approved_edit_users").fetchone()["cnt"]
        stickers = conn.execute("SELECT COUNT(*) as cnt FROM approved_sticker_users").fetchone()["cnt"]
        users = conn.execute("SELECT COUNT(*) as cnt FROM users").fetchone()["cnt"]
        return {"chats": chats, "approved_edits": edits, "approved_stickers": stickers, "cached_users": users}

def get_all_chat_ids():
    with get_connection() as conn:
        cursor = conn.execute("SELECT chat_id FROM chat_settings")
        return [row["chat_id"] for row in cursor.fetchall()]
