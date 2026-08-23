import aiosqlite
import json
import time
from config import DB_PATH

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS games (
                chat_id INTEGER PRIMARY KEY,
                owner_id INTEGER,
                state TEXT,              -- LOBBY, ROLE_ASSIGNMENT, NIGHT, DAY_VOTE, ENDED
                phase_round INTEGER DEFAULT 1,
                expires_at INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS players (
                chat_id INTEGER,
                user_id INTEGER,
                username TEXT,
                full_name TEXT,
                role TEXT,
                is_alive BOOLEAN DEFAULT 1,
                can_last_word BOOLEAN DEFAULT 0,
                bullets INTEGER DEFAULT 2,
                has_vest BOOLEAN DEFAULT 0,
                extra_last_words INTEGER DEFAULT 0,
                PRIMARY KEY (chat_id, user_id)
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS night_actions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER,
                round INTEGER,
                actor_id INTEGER,
                role TEXT,
                target_id INTEGER,
                action_type TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS day_votes (
                chat_id INTEGER,
                round INTEGER,
                voter_id INTEGER,
                target_id INTEGER,
                weight INTEGER DEFAULT 1,
                PRIMARY KEY (chat_id, round, voter_id)
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_profiles (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                full_name TEXT,
                games_played INTEGER DEFAULT 0,
                games_won INTEGER DEFAULT 0,
                mafia_wins INTEGER DEFAULT 0,
                town_wins INTEGER DEFAULT 0,
                neutral_wins INTEGER DEFAULT 0,
                coins INTEGER DEFAULT 50,
                inventory TEXT DEFAULT '{}'
            )
        """)

        await db.commit()

async def create_game(chat_id: int, owner_id: int, duration_sec: int = 60):
    expires_at = int(time.time()) + duration_sec
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO games (chat_id, owner_id, state, phase_round, expires_at) VALUES (?, ?, 'LOBBY', 1, ?)",
            (chat_id, owner_id, expires_at)
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

async def set_game_state(chat_id: int, state: str, phase_round: int = None, duration_sec: int = 60):
    expires_at = int(time.time()) + duration_sec
    async with aiosqlite.connect(DB_PATH) as db:
        if phase_round is not None:
            await db.execute("UPDATE games SET state = ?, phase_round = ?, expires_at = ? WHERE chat_id = ?", (state, phase_round, expires_at, chat_id))
        else:
            await db.execute("UPDATE games SET state = ?, expires_at = ? WHERE chat_id = ?", (state, expires_at, chat_id))
        await db.commit()

async def extend_game_timer(chat_id: int, extra_sec: int = 60) -> int:
    game = await get_game(chat_id)
    now = int(time.time())
    current_expires = game["expires_at"] if game and game["expires_at"] > now else now
    new_expires = current_expires + extra_sec
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE games SET expires_at = ? WHERE chat_id = ?", (new_expires, chat_id))
        await db.commit()
    return new_expires - now

async def add_player(chat_id: int, user_id: int, username: str, full_name: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT OR REPLACE INTO players (chat_id, user_id, username, full_name, role, is_alive, can_last_word, bullets, has_vest, extra_last_words)
            VALUES (?, ?, ?, ?, 'UNASSIGNED', 1, 0, 2, 0, 0)
        """, (chat_id, user_id, username or "", full_name or "Player"))

        await db.execute("""
            INSERT INTO user_profiles (user_id, username, full_name, games_played, coins)
            VALUES (?, ?, ?, 1, 60)
            ON CONFLICT(user_id) DO UPDATE SET
                username = excluded.username,
                full_name = excluded.full_name,
                games_played = games_played + 1,
                coins = coins + 10
        """, (user_id, username or "", full_name or "Player"))
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
        async with db.execute("SELECT extra_last_words FROM players WHERE chat_id = ? AND user_id = ?", (chat_id, user_id)) as cursor:
            row = await cursor.fetchone()
            if row and row[0] > 0:
                await db.execute("UPDATE players SET extra_last_words = extra_last_words - 1 WHERE chat_id = ? AND user_id = ?", (chat_id, user_id))
            else:
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

async def get_user_profile(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM user_profiles WHERE user_id = ?", (user_id,)) as cursor:
            return await cursor.fetchone()

async def record_win(user_id: int, win_type: str):
    async with aiosqlite.connect(DB_PATH) as db:
        column = "town_wins"
        if win_type == "MAFIA":
            column = "mafia_wins"
        elif win_type in ("JESTER", "SERIAL_KILLER", "NEUTRAL"):
            column = "neutral_wins"

        await db.execute(f"""
            UPDATE user_profiles
            SET games_won = games_won + 1, {column} = {column} + 1, coins = coins + 25
            WHERE user_id = ?
        """, (user_id,))
        await db.commit()

async def buy_shop_item(user_id: int, item_key: str, price: int) -> tuple[bool, str]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT coins, inventory FROM user_profiles WHERE user_id = ?", (user_id,)) as cursor:
            profile = await cursor.fetchone()

        if not profile or profile["coins"] < price:
            return False, "❌ Insufficient coins! Play more games to earn coins."

        inv = json.loads(profile["inventory"] or "{}")
        inv[item_key] = inv.get(item_key, 0) + 1

        new_coins = profile["coins"] - price
        await db.execute("""
            UPDATE user_profiles
            SET coins = ?, inventory = ?
            WHERE user_id = ?
        """, (new_coins, json.dumps(inv), user_id))
        await db.commit()
        return True, f"✅ Successfully purchased **{item_key}**! Coins remaining: 🪙 **{new_coins}**"

async def consume_inventory_item(user_id: int, item_key: str) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT inventory FROM user_profiles WHERE user_id = ?", (user_id,)) as cursor:
            profile = await cursor.fetchone()

        if not profile:
            return False

        inv = json.loads(profile["inventory"] or "{}")
        if inv.get(item_key, 0) <= 0:
            return False

        inv[item_key] -= 1
        if inv[item_key] <= 0:
            del inv[item_key]

        await db.execute("UPDATE user_profiles SET inventory = ? WHERE user_id = ?", (json.dumps(inv), user_id))
        await db.commit()
        return True

async def delete_game(chat_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM games WHERE chat_id = ?", (chat_id,))
        await db.execute("DELETE FROM players WHERE chat_id = ?", (chat_id,))
        await db.execute("DELETE FROM night_actions WHERE chat_id = ?", (chat_id,))
        await db.execute("DELETE FROM day_votes WHERE chat_id = ?", (chat_id,))
        await db.commit()
