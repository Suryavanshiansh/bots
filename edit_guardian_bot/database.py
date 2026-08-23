import os
import psycopg2
import psycopg2.extras
from datetime import datetime

DATABASE_URL = os.getenv("DATABASE_URL", "")

def get_connection():
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    return conn

def init_db():
    if not DATABASE_URL:
        print("[DB] ❌ DATABASE_URL is not set! Please add your Supabase connection string to .env")
        return
    print(f"[DB] Connecting to PostgreSQL database...")
    with get_connection() as conn:
        cursor = conn.cursor()

        # Chat settings table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chat_settings (
                chat_id BIGINT PRIMARY KEY,
                media_delay_minutes INTEGER DEFAULT 60,
                delete_edited INTEGER DEFAULT 1,
                sticker_mode TEXT DEFAULT 'nsfw_only',
                updated_at TEXT
            )
        """)

        # Approved edit users table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS approved_edit_users (
                chat_id BIGINT,
                user_id BIGINT,
                added_at TEXT,
                PRIMARY KEY (chat_id, user_id)
            )
        """)

        # Approved sticker users table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS approved_sticker_users (
                chat_id BIGINT,
                user_id BIGINT,
                added_at TEXT,
                PRIMARY KEY (chat_id, user_id)
            )
        """)

        # Users table for caching usernames and display names
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                updated_at TEXT
            )
        """)

    print("[DB] ✅ PostgreSQL database initialized successfully!")

# --- Users Caching CRUD ---

def upsert_user(user_id: int, username: str, first_name: str, last_name: str):
    now = datetime.utcnow().isoformat()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO users (user_id, username, first_name, last_name, updated_at)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT(user_id) DO UPDATE SET
                username = EXCLUDED.username,
                first_name = EXCLUDED.first_name,
                last_name = EXCLUDED.last_name,
                updated_at = EXCLUDED.updated_at
        """, (user_id, username, first_name, last_name, now))

def get_user_by_username(username: str):
    clean = username.lstrip("@").lower()
    with get_connection() as conn:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute("SELECT * FROM users WHERE LOWER(username) = %s", (clean,))
        return cursor.fetchone()

def get_user_by_id(user_id: int):
    with get_connection() as conn:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
        return cursor.fetchone()


# --- Chat Settings CRUD ---

def get_chat_settings(chat_id: int):
    with get_connection() as conn:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute("SELECT * FROM chat_settings WHERE chat_id = %s", (chat_id,))
        row = cursor.fetchone()
        if not row:
            now = datetime.utcnow().isoformat()
            cursor.execute(
                "INSERT INTO chat_settings (chat_id, media_delay_minutes, delete_edited, sticker_mode, updated_at) VALUES (%s, %s, %s, %s, %s)",
                (chat_id, 60, 1, 'nsfw_only', now)
            )
            return {"chat_id": chat_id, "media_delay_minutes": 60, "delete_edited": 1, "sticker_mode": "nsfw_only"}
        return dict(row)

def update_media_delay(chat_id: int, minutes: int):
    now = datetime.utcnow().isoformat()
    get_chat_settings(chat_id)
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE chat_settings SET media_delay_minutes = %s, updated_at = %s WHERE chat_id = %s",
            (minutes, now, chat_id)
        )

def update_delete_edited(chat_id: int, enabled: int):
    now = datetime.utcnow().isoformat()
    get_chat_settings(chat_id)
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE chat_settings SET delete_edited = %s, updated_at = %s WHERE chat_id = %s",
            (enabled, now, chat_id)
        )

def update_sticker_mode(chat_id: int, mode: str):
    now = datetime.utcnow().isoformat()
    get_chat_settings(chat_id)
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE chat_settings SET sticker_mode = %s, updated_at = %s WHERE chat_id = %s",
            (mode, now, chat_id)
        )

# --- Approved Edit Users CRUD ---

def add_approved_edit_user(chat_id: int, user_id: int) -> bool:
    now = datetime.utcnow().isoformat()
    with get_connection() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                """INSERT INTO approved_edit_users (chat_id, user_id, added_at) VALUES (%s, %s, %s)
                   ON CONFLICT (chat_id, user_id) DO UPDATE SET added_at = EXCLUDED.added_at""",
                (chat_id, user_id, now)
            )
            return True
        except Exception:
            return False

def remove_approved_edit_user(chat_id: int, user_id: int) -> bool:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM approved_edit_users WHERE chat_id = %s AND user_id = %s",
            (chat_id, user_id)
        )
        return cursor.rowcount > 0

def is_user_edit_approved(chat_id: int, user_id: int) -> bool:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT 1 FROM approved_edit_users WHERE chat_id = %s AND user_id = %s",
            (chat_id, user_id)
        )
        return cursor.fetchone() is not None

# --- Approved Sticker Users CRUD ---

def add_approved_sticker_user(chat_id: int, user_id: int) -> bool:
    now = datetime.utcnow().isoformat()
    with get_connection() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                """INSERT INTO approved_sticker_users (chat_id, user_id, added_at) VALUES (%s, %s, %s)
                   ON CONFLICT (chat_id, user_id) DO UPDATE SET added_at = EXCLUDED.added_at""",
                (chat_id, user_id, now)
            )
            return True
        except Exception:
            return False

def remove_approved_sticker_user(chat_id: int, user_id: int) -> bool:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM approved_sticker_users WHERE chat_id = %s AND user_id = %s",
            (chat_id, user_id)
        )
        return cursor.rowcount > 0

def is_user_sticker_approved(chat_id: int, user_id: int) -> bool:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT 1 FROM approved_sticker_users WHERE chat_id = %s AND user_id = %s",
            (chat_id, user_id)
        )
        return cursor.fetchone() is not None

# --- Listing Approved Users ---

def get_approved_edit_users(chat_id: int):
    with get_connection() as conn:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute("SELECT user_id FROM approved_edit_users WHERE chat_id = %s", (chat_id,))
        return [row["user_id"] for row in cursor.fetchall()]

def get_approved_sticker_users(chat_id: int):
    with get_connection() as conn:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute("SELECT user_id FROM approved_sticker_users WHERE chat_id = %s", (chat_id,))
        return [row["user_id"] for row in cursor.fetchall()]

# --- Bot Owner Stats & Global Data ---

def get_bot_stats():
    with get_connection() as conn:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute("SELECT COUNT(*) as cnt FROM chat_settings")
        chats = cursor.fetchone()["cnt"]
        cursor.execute("SELECT COUNT(*) as cnt FROM approved_edit_users")
        edits = cursor.fetchone()["cnt"]
        cursor.execute("SELECT COUNT(*) as cnt FROM approved_sticker_users")
        stickers = cursor.fetchone()["cnt"]
        cursor.execute("SELECT COUNT(*) as cnt FROM users")
        users = cursor.fetchone()["cnt"]
        return {"chats": chats, "approved_edits": edits, "approved_stickers": stickers, "cached_users": users}

def get_all_chat_ids():
    with get_connection() as conn:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute("SELECT chat_id FROM chat_settings")
        return [row["chat_id"] for row in cursor.fetchall()]
