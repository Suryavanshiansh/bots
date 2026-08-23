import aiosqlite
import json
from config import DB_PATH

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        # Table to track game instances per group chat
        await db.execute("""
            CREATE TABLE IF NOT EXISTS games (
                chat_id INTEGER PRIMARY KEY,
                owner_id INTEGER,
                state TEXT,              -- LOBBY, ROLE_ASSIGNMENT, NIGHT, DAY_VOTE, ENDED
                phase_round INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Table for players in games
        await db.execute("""
            CREATE TABLE IF NOT EXISTS players (
                chat_id INTEGER,
                user_id INTEGER,
                username TEXT,
                full_name TEXT,
                role TEXT,
                is_alive BOOLEAN DEFAULT 1,
                can_last_word BOOLEAN DEFAULT 0,
                bullets INTEGER DEFAULT 2,   -- For Vigilante
                PRIMARY KEY (chat_id, user_id)
            )
        """)

        # Table for night actions log
        await db.execute("""
            CREATE TABLE IF NOT EXISTS night_actions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER,
                round INTEGER,
                actor_id INTEGER,
                role TEXT,
                target_id INTEGER,
                action_type TEXT,        -- KILL, SAVE, INVESTIGATE, SHOOT
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Table for day votes
        await db.execute("""
            CREATE TABLE IF NOT EXISTS day_votes (
                chat_id INTEGER,
                round INTEGER,
                voter_id INTEGER,
                target_id INTEGER,
                weight INTEGER DEFAULT 1, -- Mayor gets 2
                PRIMARY KEY (chat_id, round, voter_id)
            )
        """)

        await db.commit()

async def create_game(chat_id: int, owner_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO games (chat_id, owner_id, state, phase_round) VALUES (?, ?, 'LOBBY', 1)",
            (chat_id, owner_id)
        )
        await db.execute("DELETE FROM players WHERE chat_id = ?", (chat_id,))
        await db.execute("DELETE FROM night_actions WHERE chat_id = ?", (chat_id,))
        await db.execute("DELETE FROM day_votes WHERE chat_id = ?", (chat_id,))
        await db.commit()

async def get_game(chat_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM games WHERE chat_id = ?", (chat_id,)) as cursor:
            return await cursor.fetchone()

async def set_game_state(chat_id: int, state: str, phase_round: int = None):
    async with aiosqlite.connect(DB_PATH) as db:
        if phase_round is not None:
            await db.execute("UPDATE games SET state = ?, phase_round = ? WHERE chat_id = ?", (state, phase_round, chat_id))
        else:
            await db.execute("UPDATE games SET state = ? WHERE chat_id = ?", (state, chat_id))
        await db.commit()

async def add_player(chat_id: int, user_id: int, username: str, full_name: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT OR REPLACE INTO players (chat_id, user_id, username, full_name, role, is_alive, can_last_word, bullets)
            VALUES (?, ?, ?, ?, 'UNASSIGNED', 1, 0, 2)
        """, (chat_id, user_id, username or "", full_name or "Player"))
        await db.commit()

async def get_players(chat_id: int, alive_only: bool = False):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        query = "SELECT * FROM players WHERE chat_id = ?"
        if alive_only:
            query += " AND is_alive = 1"
        async with db.execute(query, (chat_id,)) as cursor:
            return await cursor.fetchall()

async def set_player_role(chat_id: int, user_id: int, role: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE players SET role = ? WHERE chat_id = ? AND user_id = ?", (role, chat_id, user_id))
        await db.commit()

async def set_player_dead(chat_id: int, user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE players SET is_alive = 0, can_last_word = 1 WHERE chat_id = ? AND user_id = ?", (chat_id, user_id))
        await db.commit()

async def disable_last_word(chat_id: int, user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE players SET can_last_word = 0 WHERE chat_id = ? AND user_id = ?", (chat_id, user_id))
        await db.commit()

async def log_night_action(chat_id: int, phase_round: int, actor_id: int, role: str, target_id: int, action_type: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO night_actions (chat_id, round, actor_id, role, target_id, action_type)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (chat_id, phase_round, actor_id, role, target_id, action_type))
        await db.commit()

async def get_night_actions(chat_id: int, phase_round: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM night_actions WHERE chat_id = ? AND round = ?", (chat_id, phase_round)) as cursor:
            return await cursor.fetchall()

async def record_day_vote(chat_id: int, phase_round: int, voter_id: int, target_id: int, weight: int = 1):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT OR REPLACE INTO day_votes (chat_id, round, voter_id, target_id, weight)
            VALUES (?, ?, ?, ?, ?)
        """, (chat_id, phase_round, voter_id, target_id, weight))
        await db.commit()

async def get_day_votes(chat_id: int, phase_round: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM day_votes WHERE chat_id = ? AND round = ?", (chat_id, phase_round)) as cursor:
            return await cursor.fetchall()

async def delete_game(chat_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM games WHERE chat_id = ?", (chat_id,))
        await db.execute("DELETE FROM players WHERE chat_id = ?", (chat_id,))
        await db.execute("DELETE FROM night_actions WHERE chat_id = ?", (chat_id,))
        await db.execute("DELETE FROM day_votes WHERE chat_id = ?", (chat_id,))
        await db.commit()
