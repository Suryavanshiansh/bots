import os
import sqlite3
from datetime import datetime

DATABASE_URL = os.getenv("DATABASE_URL", "")
IS_POSTGRES = bool(DATABASE_URL and (DATABASE_URL.startswith("postgres://") or DATABASE_URL.startswith("postgresql://")))

if IS_POSTGRES:
    import psycopg2
    import psycopg2.extras

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SQLITE_DB_PATH = os.path.join(BASE_DIR, "guardian.db")

def get_connection():
    if IS_POSTGRES:
        conn = psycopg2.connect(DATABASE_URL)
        conn.autocommit = True
        return conn
    else:
        conn = sqlite3.connect(SQLITE_DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn

def execute_query(query: str, params: tuple = (), fetchone: bool = False, fetchall: bool = False, commit: bool = True):
    """Execute SQL query safely across PostgreSQL and SQLite."""
    is_select = query.strip().upper().startswith("SELECT")
    
    if IS_POSTGRES:
        with get_connection() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cursor.execute(query, params)
            if fetchone:
                res = cursor.fetchone()
                return dict(res) if res else None
            if fetchall:
                res = cursor.fetchall()
                return [dict(r) for r in res]
            return cursor.rowcount
    else:
        # SQLite uses ? for placeholders instead of %s
        sqlite_query = query.replace("%s", "?")
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sqlite_query, params)
            if commit and not is_select:
                conn.commit()
            if fetchone:
                res = cursor.fetchone()
                return dict(res) if res else None
            if fetchall:
                res = cursor.fetchall()
                return [dict(r) for r in res]
            return cursor.rowcount

def init_db():
    if IS_POSTGRES:
        print("[DB] Connecting to PostgreSQL (Supabase) database...")
    else:
        print(f"[DB] Using local SQLite database at: {SQLITE_DB_PATH}")

    # Chat settings table
    execute_query("""
        CREATE TABLE IF NOT EXISTS chat_settings (
            chat_id BIGINT PRIMARY KEY,
            media_delay_minutes INTEGER DEFAULT 60,
            delete_edited INTEGER DEFAULT 1,
            sticker_mode TEXT DEFAULT 'nsfw_only',
            updated_at TEXT
        )
    """)

    # Approved edit users table
    execute_query("""
        CREATE TABLE IF NOT EXISTS approved_edit_users (
            chat_id BIGINT,
            user_id BIGINT,
            added_at TEXT,
            PRIMARY KEY (chat_id, user_id)
        )
    """)

    # Approved sticker users table
    execute_query("""
        CREATE TABLE IF NOT EXISTS approved_sticker_users (
            chat_id BIGINT,
            user_id BIGINT,
            added_at TEXT,
            PRIMARY KEY (chat_id, user_id)
        )
    """)

    # Users table for caching usernames and display names
    execute_query("""
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            updated_at TEXT
        )
    """)

    # AFK users table
    execute_query("""
        CREATE TABLE IF NOT EXISTS afk_users (
            user_id BIGINT PRIMARY KEY,
            reason TEXT,
            afk_since TEXT
        )
    """)

    print("[DB] ✅ Database initialized successfully!")

# --- Users Caching CRUD ---

def upsert_user(user_id: int, username: str, first_name: str, last_name: str):
    now = datetime.utcnow().isoformat()
    query = """
        INSERT INTO users (user_id, username, first_name, last_name, updated_at)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT(user_id) DO UPDATE SET
            username = EXCLUDED.username,
            first_name = EXCLUDED.first_name,
            last_name = EXCLUDED.last_name,
            updated_at = EXCLUDED.updated_at
    """
    execute_query(query, (user_id, username or "", first_name or "", last_name or "", now))

def get_user_by_username(username: str):
    clean = username.lstrip("@").lower()
    return execute_query("SELECT * FROM users WHERE LOWER(username) = %s", (clean,), fetchone=True)

def get_user_by_id(user_id: int):
    return execute_query("SELECT * FROM users WHERE user_id = %s", (user_id,), fetchone=True)


# --- Chat Settings CRUD ---

def get_chat_settings(chat_id: int):
    row = execute_query("SELECT * FROM chat_settings WHERE chat_id = %s", (chat_id,), fetchone=True)
    if not row:
        now = datetime.utcnow().isoformat()
        execute_query(
            "INSERT INTO chat_settings (chat_id, media_delay_minutes, delete_edited, sticker_mode, updated_at) VALUES (%s, %s, %s, %s, %s)",
            (chat_id, 60, 1, 'nsfw_only', now)
        )
        return {"chat_id": chat_id, "media_delay_minutes": 60, "delete_edited": 1, "sticker_mode": "nsfw_only"}
    return row

def update_media_delay(chat_id: int, minutes: int):
    now = datetime.utcnow().isoformat()
    get_chat_settings(chat_id)
    execute_query(
        "UPDATE chat_settings SET media_delay_minutes = %s, updated_at = %s WHERE chat_id = %s",
        (minutes, now, chat_id)
    )

def update_delete_edited(chat_id: int, enabled: int):
    now = datetime.utcnow().isoformat()
    get_chat_settings(chat_id)
    execute_query(
        "UPDATE chat_settings SET delete_edited = %s, updated_at = %s WHERE chat_id = %s",
        (enabled, now, chat_id)
    )

def update_sticker_mode(chat_id: int, mode: str):
    now = datetime.utcnow().isoformat()
    get_chat_settings(chat_id)
    execute_query(
        "UPDATE chat_settings SET sticker_mode = %s, updated_at = %s WHERE chat_id = %s",
        (mode, now, chat_id)
    )

# --- Approved Edit Users CRUD ---

def add_approved_edit_user(chat_id: int, user_id: int) -> bool:
    now = datetime.utcnow().isoformat()
    try:
        execute_query(
            """INSERT INTO approved_edit_users (chat_id, user_id, added_at) VALUES (%s, %s, %s)
               ON CONFLICT (chat_id, user_id) DO UPDATE SET added_at = EXCLUDED.added_at""",
            (chat_id, user_id, now)
        )
        return True
    except Exception:
        return False

def remove_approved_edit_user(chat_id: int, user_id: int) -> bool:
    res = execute_query(
        "DELETE FROM approved_edit_users WHERE chat_id = %s AND user_id = %s",
        (chat_id, user_id)
    )
    return res > 0

def is_user_edit_approved(chat_id: int, user_id: int) -> bool:
    row = execute_query(
        "SELECT 1 FROM approved_edit_users WHERE chat_id = %s AND user_id = %s",
        (chat_id, user_id),
        fetchone=True
    )
    return row is not None

# --- Approved Sticker Users CRUD ---

def add_approved_sticker_user(chat_id: int, user_id: int) -> bool:
    now = datetime.utcnow().isoformat()
    try:
        execute_query(
            """INSERT INTO approved_sticker_users (chat_id, user_id, added_at) VALUES (%s, %s, %s)
               ON CONFLICT (chat_id, user_id) DO UPDATE SET added_at = EXCLUDED.added_at""",
            (chat_id, user_id, now)
        )
        return True
    except Exception:
        return False

def remove_approved_sticker_user(chat_id: int, user_id: int) -> bool:
    res = execute_query(
        "DELETE FROM approved_sticker_users WHERE chat_id = %s AND user_id = %s",
        (chat_id, user_id)
    )
    return res > 0

def is_user_sticker_approved(chat_id: int, user_id: int) -> bool:
    row = execute_query(
        "SELECT 1 FROM approved_sticker_users WHERE chat_id = %s AND user_id = %s",
        (chat_id, user_id),
        fetchone=True
    )
    return row is not None

# --- Listing Approved Users ---

def get_approved_edit_users(chat_id: int):
    rows = execute_query("SELECT user_id FROM approved_edit_users WHERE chat_id = %s", (chat_id,), fetchall=True)
    return [r["user_id"] for r in rows]

def get_approved_sticker_users(chat_id: int):
    rows = execute_query("SELECT user_id FROM approved_sticker_users WHERE chat_id = %s", (chat_id,), fetchall=True)
    return [r["user_id"] for r in rows]

# --- AFK Users CRUD ---

def set_user_afk(user_id: int, reason: str):
    now = datetime.utcnow().isoformat()
    query = """
        INSERT INTO afk_users (user_id, reason, afk_since)
        VALUES (%s, %s, %s)
        ON CONFLICT(user_id) DO UPDATE SET
            reason = EXCLUDED.reason,
            afk_since = EXCLUDED.afk_since
    """
    execute_query(query, (user_id, reason, now))

def remove_user_afk(user_id: int):
    afk_info = get_user_afk(user_id)
    if afk_info:
        execute_query("DELETE FROM afk_users WHERE user_id = %s", (user_id,))
    return afk_info

def get_user_afk(user_id: int):
    return execute_query("SELECT * FROM afk_users WHERE user_id = %s", (user_id,), fetchone=True)

def get_afk_user_by_username(username: str):
    clean = username.lstrip("@").lower()
    query = """
        SELECT a.*, u.first_name, u.username
        FROM afk_users a
        JOIN users u ON a.user_id = u.user_id
        WHERE LOWER(u.username) = %s
    """
    return execute_query(query, (clean,), fetchone=True)

# --- Bot Owner Stats & Global Data ---

def get_bot_stats():
    chats = execute_query("SELECT COUNT(*) as cnt FROM chat_settings", fetchone=True)["cnt"]
    edits = execute_query("SELECT COUNT(*) as cnt FROM approved_edit_users", fetchone=True)["cnt"]
    stickers = execute_query("SELECT COUNT(*) as cnt FROM approved_sticker_users", fetchone=True)["cnt"]
    users = execute_query("SELECT COUNT(*) as cnt FROM users", fetchone=True)["cnt"]
    afks = execute_query("SELECT COUNT(*) as cnt FROM afk_users", fetchone=True)["cnt"]
    return {
        "chats": chats,
        "approved_edits": edits,
        "approved_stickers": stickers,
        "cached_users": users,
        "afk_users": afks
    }

def get_all_chat_ids():
    rows = execute_query("SELECT chat_id FROM chat_settings", fetchall=True)
    return [r["chat_id"] for r in rows]
