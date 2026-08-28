import sqlite3
import os
import logging
from typing import Optional, Dict, Any, List

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "whispers.db")
SUPABASE_URL = os.getenv("SUPABASE_DB_URL") or os.getenv("DATABASE_URL")

try:
    import psycopg2
    import psycopg2.extras
    HAS_PSYCOPG2 = True
except ImportError:
    HAS_PSYCOPG2 = False

def is_using_supabase() -> bool:
    return bool(SUPABASE_URL and HAS_PSYCOPG2)

def get_db():
    if is_using_supabase():
        return psycopg2.connect(SUPABASE_URL)
    else:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn

def execute_query(query: str, params: tuple = (), fetch_one: bool = False, fetch_all: bool = False):
    use_pg = is_using_supabase()
    conn = get_db()
    try:
        if use_pg:
            pg_query = query.replace("?", "%s")
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(pg_query, params)
                if fetch_one:
                    res = cur.fetchone()
                    conn.commit()
                    conn.close()
                    return dict(res) if res else None
                if fetch_all:
                    res = cur.fetchall()
                    conn.commit()
                    conn.close()
                    return [dict(r) for r in res]
                conn.commit()
                conn.close()
                return None
        else:
            cur = conn.cursor()
            cur.execute(query, params)
            if fetch_one:
                res = cur.fetchone()
                conn.commit()
                conn.close()
                return dict(res) if res else None
            if fetch_all:
                res = cur.fetchall()
                conn.commit()
                conn.close()
                return [dict(r) for r in res]
            conn.commit()
            conn.close()
            return None
    except Exception as e:
        logging.error(f"Database query error: {e}")
        try:
            conn.close()
        except Exception:
            pass
        return None if (fetch_one or fetch_all) else None

def init_db():
    use_pg = is_using_supabase()
    print(f"[DB] Initializing database (Mode: {'Supabase PostgreSQL' if use_pg else 'SQLite'})...")
    conn = get_db()
    try:
        if use_pg:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS whispers (
                        whisper_id VARCHAR(50) PRIMARY KEY,
                        sender_id BIGINT NOT NULL,
                        sender_username VARCHAR(255),
                        target_id BIGINT,
                        target_username VARCHAR(255),
                        secret_text TEXT NOT NULL,
                        is_seen INT DEFAULT 0,
                        seen_at TIMESTAMP,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        user_id BIGINT PRIMARY KEY,
                        username VARCHAR(255),
                        first_name VARCHAR(255),
                        last_name VARCHAR(255),
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                conn.commit()
                conn.close()
        else:
            with conn as c:
                c.execute("""
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
                    );
                """)
                c.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        user_id INTEGER PRIMARY KEY,
                        username TEXT,
                        first_name TEXT,
                        last_name TEXT,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                cur = c.cursor()
                cur.execute("PRAGMA table_info(whispers)")
                existing_cols = [row[1] for row in cur.fetchall()]
                if "is_seen" not in existing_cols:
                    c.execute("ALTER TABLE whispers ADD COLUMN is_seen INTEGER DEFAULT 0")
                if "seen_at" not in existing_cols:
                    c.execute("ALTER TABLE whispers ADD COLUMN seen_at TIMESTAMP")
                c.commit()
    except Exception as e:
        logging.error(f"[DB] Error initializing DB: {e}")

def upsert_user(
    user_id: int,
    username: Optional[str] = None,
    first_name: Optional[str] = None,
    last_name: Optional[str] = None
):
    if not user_id:
        return
    clean_user = username.lstrip("@").lower() if username else None
    clean_fn = first_name.strip() if first_name else None
    clean_ln = last_name.strip() if last_name else None

    if is_using_supabase():
        execute_query("""
            INSERT INTO users (user_id, username, first_name, last_name, updated_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE SET
                username = COALESCE(EXCLUDED.username, users.username),
                first_name = COALESCE(EXCLUDED.first_name, users.first_name),
                last_name = COALESCE(EXCLUDED.last_name, users.last_name),
                updated_at = CURRENT_TIMESTAMP
        """, (user_id, clean_user, clean_fn, clean_ln))
    else:
        execute_query("""
            INSERT INTO users (user_id, username, first_name, last_name, updated_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE SET
                username = COALESCE(excluded.username, users.username),
                first_name = COALESCE(excluded.first_name, users.first_name),
                last_name = COALESCE(excluded.last_name, users.last_name),
                updated_at = CURRENT_TIMESTAMP
        """, (user_id, clean_user, clean_fn, clean_ln))

def get_user_by_id(user_id: int) -> Optional[Dict[str, Any]]:
    if not user_id:
        return None
    return execute_query("SELECT * FROM users WHERE user_id = ?", (user_id,), fetch_one=True)

def get_user_by_username(username: str) -> Optional[Dict[str, Any]]:
    if not username:
        return None
    clean = username.lstrip("@").lower()
    return execute_query("SELECT * FROM users WHERE LOWER(username) = ?", (clean,), fetch_one=True)

def save_whisper(
    whisper_id: str,
    sender_id: int,
    sender_username: Optional[str],
    target_id: Optional[int],
    target_username: Optional[str],
    secret_text: str
):
    clean_target_u = target_username.lstrip("@").lower() if target_username else None
    execute_query("""
        INSERT INTO whispers (whisper_id, sender_id, sender_username, target_id, target_username, secret_text)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (whisper_id, sender_id, sender_username, target_id, clean_target_u, secret_text))

def mark_whisper_seen(whisper_id: str):
    execute_query("""
        UPDATE whispers
        SET is_seen = 1, seen_at = CURRENT_TIMESTAMP
        WHERE whisper_id = ?
    """, (whisper_id,))

def get_whisper(whisper_id: str) -> Optional[Dict[str, Any]]:
    return execute_query("SELECT * FROM whispers WHERE whisper_id = ?", (whisper_id,), fetch_one=True)

def get_all_past_targets(sender_id: int, limit: int = 40) -> List[Dict[str, Any]]:
    use_pg = is_using_supabase()
    if use_pg:
        query = """
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
            GROUP BY w.target_username, w.target_id, u.first_name, u.last_name, u.username
            ORDER BY last_sent DESC
            LIMIT ?
        """
    else:
        query = """
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
        """
    rows = execute_query(query, (sender_id, limit), fetch_all=True) or []
    results = []
    for row in rows:
        first_name = row.get("user_first_name")
        last_name = row.get("user_last_name")
        name = None
        if first_name and first_name.strip():
            fn = first_name.strip()
            ln = last_name.strip() if last_name else ""
            name = f"{fn} {ln}".strip() if ln else fn
        elif row.get("target_username"):
            name = f"@{row.get('target_username').lstrip('@')}"
        elif row.get("target_id"):
            name = f"User ID {row.get('target_id')}"

        results.append({
            "target_username": row.get("target_username"),
            "target_id": row.get("target_id"),
            "target_name": name
        })
    return results

if __name__ == "__main__":
    init_db()
    print("Database initialized successfully!")
