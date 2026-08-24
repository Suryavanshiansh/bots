import os
import sqlite3
from datetime import datetime

RAW_DB_URL = os.getenv("DATABASE_URL", "").strip()

# Normalize postgres:// to postgresql:// for psycopg2 compatibility
if RAW_DB_URL.startswith("postgres://"):
    DATABASE_URL = RAW_DB_URL.replace("postgres://", "postgresql://", 1)
else:
    DATABASE_URL = RAW_DB_URL

# Check if psycopg2 is available
try:
    import psycopg2
    import psycopg2.extras
    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SQLITE_DB_PATH = os.path.join(BASE_DIR, "afk_bot.db")

USE_POSTGRES = False
AFK_CACHE = {}

def check_postgres_connection():
    global USE_POSTGRES
    if DATABASE_URL and PSYCOPG2_AVAILABLE and "YOUR-PASSWORD" not in DATABASE_URL:
        try:
            conn = psycopg2.connect(DATABASE_URL, connect_timeout=5)
            conn.close()
            USE_POSTGRES = True
            print("[DB] ✅ Successfully connected to PostgreSQL (Supabase)!")
            return True
        except Exception as e:
            print(f"[DB] ⚠️ Could not connect to PostgreSQL: {e}")
            print("[DB] 🔄 Falling back to local SQLite database...")
            USE_POSTGRES = False
            return False
    else:
        if DATABASE_URL and "YOUR-PASSWORD" in DATABASE_URL:
            print("[DB] ⚠️ DATABASE_URL contains placeholder '[YOUR-PASSWORD]'. Using local SQLite.")
        else:
            print("[DB] ℹ️ DATABASE_URL not set. Using local SQLite.")
        USE_POSTGRES = False
        return False

def get_connection():
    if USE_POSTGRES:
        conn = psycopg2.connect(DATABASE_URL, connect_timeout=10)
        conn.autocommit = True
        return conn
    else:
        conn = sqlite3.connect(SQLITE_DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn

def execute_query(query: str, params: tuple = (), fetchone: bool = False, fetchall: bool = False, commit: bool = True):
    """Execute SQL query safely across PostgreSQL and SQLite."""
    is_select = query.strip().upper().startswith("SELECT")
    
    if USE_POSTGRES:
        for attempt in range(3):
            try:
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
            except Exception as e:
                print(f"[DB] ⚠️ Postgres query attempt {attempt+1}/3 failed: {e}")
                if attempt == 2:
                    print(f"[DB] ❌ All 3 PostgreSQL attempts failed for query.")
                    return None if (fetchone or fetchall) else 0
        return None if (fetchone or fetchall) else 0

    # SQLite execution
    sqlite_query = query.replace("%s", "?")
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(sqlite_query, params)
        if commit and not is_select:
            conn.commit()
        if fetchone:
            res = cursor.fetchone()
            if res is None:
                return None
            if isinstance(res, sqlite3.Row):
                return dict(res)
            colnames = [desc[0] for desc in cursor.description]
            return dict(zip(colnames, res))
        if fetchall:
            res = cursor.fetchall()
            if not res:
                return []
            if isinstance(res[0], sqlite3.Row):
                return [dict(r) for r in res]
            colnames = [desc[0] for desc in cursor.description]
            return [dict(zip(colnames, r)) for r in res]
        return cursor.rowcount

def init_db():
    check_postgres_connection()
    if USE_POSTGRES:
        print("[DB] Initializing PostgreSQL AFK Bot tables...")
    else:
        print(f"[DB] Initializing local SQLite database at: {SQLITE_DB_PATH}")

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
            afk_since TEXT,
            reason_msg_id BIGINT DEFAULT 0,
            chat_id BIGINT DEFAULT 0
        )
    """)

    # Load active AFK users into RAM cache
    try:
        rows = execute_query("SELECT * FROM afk_users", fetchall=True)
        if rows:
            for r in rows:
                AFK_CACHE[int(r["user_id"])] = dict(r)
            print(f"[DB] 🧠 Loaded {len(rows)} active AFK records into RAM cache!")
    except Exception as e:
        print(f"[DB] Warning loading AFK cache: {e}")

    print("[DB] ✅ AFK Database initialized successfully!")

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
    execute_query(query, (int(user_id), username or "", first_name or "", last_name or "", now))

def get_user_by_username(username: str):
    clean = username.lstrip("@").lower()
    return execute_query("SELECT * FROM users WHERE LOWER(username) = %s", (clean,), fetchone=True)

def get_user_by_id(user_id: int):
    return execute_query("SELECT * FROM users WHERE user_id = %s", (int(user_id),), fetchone=True)

# --- AFK Users CRUD ---

def set_user_afk(user_id: int, reason: str, reason_msg_id: int = 0, chat_id: int = 0):
    now = datetime.utcnow().isoformat()
    uid = int(user_id)
    afk_data = {
        "user_id": uid,
        "reason": reason,
        "afk_since": now,
        "reason_msg_id": int(reason_msg_id),
        "chat_id": int(chat_id)
    }
    AFK_CACHE[uid] = afk_data
    
    query = """
        INSERT INTO afk_users (user_id, reason, afk_since, reason_msg_id, chat_id)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT(user_id) DO UPDATE SET
            reason = EXCLUDED.reason,
            afk_since = EXCLUDED.afk_since,
            reason_msg_id = EXCLUDED.reason_msg_id,
            chat_id = EXCLUDED.chat_id
    """
    try:
        execute_query(query, (uid, reason, now, int(reason_msg_id), int(chat_id)))
    except Exception as e:
        print(f"[DB] Could not persist AFK to DB: {e}")

def remove_user_afk(user_id: int):
    uid = int(user_id)
    afk_info = AFK_CACHE.pop(uid, None)
    if not afk_info:
        afk_info = get_user_afk(uid)
    if afk_info:
        try:
            execute_query("DELETE FROM afk_users WHERE user_id = %s", (uid,))
        except Exception as e:
            print(f"[DB] Could not delete AFK from DB: {e}")
    return afk_info

def get_user_afk(user_id: int):
    uid = int(user_id)
    if uid in AFK_CACHE:
        return AFK_CACHE[uid]
    res = execute_query("SELECT * FROM afk_users WHERE user_id = %s", (uid,), fetchone=True)
    if res:
        AFK_CACHE[uid] = res
    return res

def get_afk_user_by_username(username: str):
    clean = username.lstrip("@").lower()
    # Check RAM cache first
    user_info = get_user_by_username(clean)
    if user_info and int(user_info["user_id"]) in AFK_CACHE:
        afk_data = dict(AFK_CACHE[int(user_info["user_id"])])
        afk_data["first_name"] = user_info.get("first_name", "")
        afk_data["username"] = user_info.get("username", "")
        return afk_data
    
    query = """
        SELECT a.*, u.first_name, u.username
        FROM afk_users a
        JOIN users u ON a.user_id = u.user_id
        WHERE LOWER(u.username) = %s
    """
    res = execute_query(query, (clean,), fetchone=True)
    if res:
        AFK_CACHE[int(res["user_id"])] = res
    return res

def get_bot_stats():
    users = execute_query("SELECT COUNT(*) as cnt FROM users", fetchone=True)
    cnt_users = users["cnt"] if users else len(AFK_CACHE)
    return {"cached_users": cnt_users, "active_afks": len(AFK_CACHE)}
