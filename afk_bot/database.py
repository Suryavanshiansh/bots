import os
import sqlite3
import threading
from datetime import datetime

# Check if psycopg2 is available
try:
    import psycopg2
    import psycopg2.extras
    from psycopg2.pool import ThreadedConnectionPool
    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SQLITE_DB_PATH = os.path.join(BASE_DIR, "afk_bot.db")

USE_POSTGRES = False
PG_POOL = None
AFK_CACHE = {}
USER_CACHE = {}

def get_db_url() -> str:
    raw_url = (os.getenv("SUPABASE_DB_URL") or os.getenv("DATABASE_URL") or "").strip()
    if raw_url.startswith("postgres://"):
        return raw_url.replace("postgres://", "postgresql://", 1)
    return raw_url

def check_postgres_connection():
    global USE_POSTGRES, PG_POOL
    db_url = get_db_url()
    if db_url and PSYCOPG2_AVAILABLE and "YOUR-PASSWORD" not in db_url:
        try:
            PG_POOL = ThreadedConnectionPool(1, 10, db_url, connect_timeout=10)
            USE_POSTGRES = True
            print("[DB] ✅ Successfully connected to PostgreSQL (Supabase Connection Pool Ready)!")
            return True
        except Exception as e:
            print(f"[DB] ⚠️ Could not connect to PostgreSQL pool: {e}")
            print("[DB] 🔄 Falling back to local SQLite database...")
            USE_POSTGRES = False
            return False
    else:
        if db_url and "YOUR-PASSWORD" in db_url:
            print("[DB] ⚠️ DATABASE_URL contains placeholder '[YOUR-PASSWORD]'. Using local SQLite.")
        else:
            print("[DB] ℹ️ DATABASE_URL not set. Using local SQLite.")
        USE_POSTGRES = False
        return False

def get_connection():
    if USE_POSTGRES and PG_POOL:
        return PG_POOL.getconn()
    else:
        conn = sqlite3.connect(SQLITE_DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn

def execute_query(query: str, params: tuple = (), fetchone: bool = False, fetchall: bool = False, commit: bool = True):
    """Execute SQL query safely across PostgreSQL and SQLite using connection pool."""
    is_select = query.strip().upper().startswith("SELECT")
    
    if USE_POSTGRES and PG_POOL:
        conn = None
        for attempt in range(3):
            try:
                conn = PG_POOL.getconn()
                conn.autocommit = True
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                    cursor.execute(query, params)
                    if fetchone:
                        res = cursor.fetchone()
                        ret = dict(res) if res else None
                    elif fetchall:
                        res = cursor.fetchall()
                        ret = [dict(r) for r in res]
                    else:
                        ret = cursor.rowcount
                PG_POOL.putconn(conn)
                return ret
            except Exception as e:
                if conn:
                    try:
                        PG_POOL.putconn(conn, close=True)
                    except Exception:
                        pass
                print(f"[DB] ⚠️ Postgres query attempt {attempt+1}/3 failed: {e}")
                if attempt == 2:
                    print(f"[DB] ❌ All 3 PostgreSQL attempts failed for query.")
                    return None if (fetchone or fetchall) else 0
        return None if (fetchone or fetchall) else 0

    # SQLite execution
    sqlite_query = query.replace("%s", "?")
    with sqlite3.connect(SQLITE_DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(sqlite_query, params)
        if commit and not is_select:
            conn.commit()
        if fetchone:
            res = cursor.fetchone()
            if res is None:
                return None
            return dict(res)
        if fetchall:
            res = cursor.fetchall()
            return [dict(r) for r in res]
        return cursor.rowcount

def init_db():
    check_postgres_connection()
    if USE_POSTGRES:
        print("[DB] Initializing PostgreSQL AFK Bot tables...")
    else:
        print(f"[DB] Initializing local SQLite database at: {SQLITE_DB_PATH}")

    # Users table
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

    # Load cached users into RAM cache
    try:
        u_rows = execute_query("SELECT * FROM users", fetchall=True)
        if u_rows:
            for ur in u_rows:
                uid = int(ur["user_id"])
                USER_CACHE[uid] = (uid, ur.get("username", "") or "", ur.get("first_name", "") or "", ur.get("last_name", "") or "")
            print(f"[DB] 🧠 Loaded {len(u_rows)} cached user profiles into RAM cache!")
    except Exception as e:
        print(f"[DB] Warning loading User cache: {e}")

    print("[DB] ✅ AFK Database initialized successfully!")

# --- Users Caching CRUD ---

def upsert_user(user_id: int, username: str, first_name: str, last_name: str):
    """RAM-first non-blocking upsert user to prevent message latency."""
    uid = int(user_id)
    u_name = username or ""
    f_name = first_name or ""
    l_name = last_name or ""
    cache_key = (uid, u_name, f_name, l_name)

    if USER_CACHE.get(uid) == cache_key:
        return  # Unchanged user info, zero DB query delay!

    USER_CACHE[uid] = cache_key

    def _do_db_upsert():
        try:
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
            execute_query(query, (uid, u_name, f_name, l_name, now))
        except Exception as e:
            print(f"[DB] Async upsert_user error: {e}")

    threading.Thread(target=_do_db_upsert, daemon=True).start()

def get_user_by_username(username: str):
    clean = username.lstrip("@").lower()
    # Check RAM cache first
    for uid, info in USER_CACHE.items():
        if info[1].lower() == clean:
            return {"user_id": uid, "username": info[1], "first_name": info[2], "last_name": info[3]}
    return execute_query("SELECT * FROM users WHERE LOWER(username) = %s", (clean,), fetchone=True)

def get_user_by_id(user_id: int):
    uid = int(user_id)
    if uid in USER_CACHE:
        info = USER_CACHE[uid]
        return {"user_id": uid, "username": info[1], "first_name": info[2], "last_name": info[3]}
    return execute_query("SELECT * FROM users WHERE user_id = %s", (uid,), fetchone=True)

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

    def _do_db_set():
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

    threading.Thread(target=_do_db_set, daemon=True).start()

def remove_user_afk(user_id: int):
    uid = int(user_id)
    afk_info = AFK_CACHE.pop(uid, None)
    if not afk_info:
        afk_info = get_user_afk(uid)
    if afk_info:
        def _do_db_remove():
            try:
                execute_query("DELETE FROM afk_users WHERE user_id = %s", (uid,))
            except Exception as e:
                print(f"[DB] Could not delete AFK from DB: {e}")
        threading.Thread(target=_do_db_remove, daemon=True).start()
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
    cnt_users = users["cnt"] if users else len(USER_CACHE)
    return {"cached_users": cnt_users, "active_afks": len(AFK_CACHE)}
