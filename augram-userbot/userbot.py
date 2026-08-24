"""
Augram Word Grid Userbot
========================
Fully autonomous Hard Mode Word Search player.

Flow:
  1. Detects new game from @WordGridRobot in the group
  2. Forwards grid image + clues to your solver bot
  3. Parses solver bot reply → word list
  4. Types words in group one-by-one (skipping already-guessed)
  5. Detects missing clues after each round → requests new hints
  6. On game end → starts a new hard game automatically
  7. If a normal game starts → kills it and starts hard mode
"""

import asyncio
import logging
import os
import random
import re
import sys

# Force UTF-8 output on Windows console
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv
from telethon import TelegramClient, events
from telethon.tl.types import PeerChannel

from state import GameState
from parser import (
    has_clue_pattern,
    is_game_over,
    is_normal_game,
    extract_confirmed_word,
    extract_all_solved_words,
    extract_missing_clue_numbers,
    get_unsolved_clue_numbers,
    parse_solver_words,
)

load_dotenv()

# ─── CONFIGURATION ────────────────────────────────────────────────────────────
API_ID        = int(os.getenv("TELEGRAM_API_ID", "0"))
API_HASH      = os.getenv("TELEGRAM_API_HASH", "")
GROUP_ID      = int(os.getenv("GROUP_ID", "-1002714592126"))
WORD_GRID_BOT = os.getenv("WORD_GRID_BOT", "WordGridRobot").lstrip("@")
SOLVER_BOT    = os.getenv("SOLVER_BOT", "word_gridsbot").lstrip("@")
WORD_DELAY    = float(os.getenv("WORD_DELAY", "1.5"))
CMD_END       = os.getenv("CMD_END", "/end@WordGridRobot")
CMD_NEW_HARD  = os.getenv("CMD_NEW_HARD", "/new_hard@WordGridRobot")

# ─── LOGGING ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(levelname)s │ %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("wordgrid")

# ─── TELETHON CLIENT & STATE ──────────────────────────────────────────────────
client = TelegramClient("wordgrid_session", API_ID, API_HASH)
state  = GameState()

# asyncio.Future set just before querying solver bot; resolved when reply arrives
_solver_future: asyncio.Future | None = None

# Lock so only one game loop runs at a time
_game_lock = asyncio.Lock()


# ─── SOLVER BOT REPLY CAPTURE ─────────────────────────────────────────────────

@client.on(events.NewMessage)
async def _capture_solver_reply(event):
    """
    Listens for solution messages from the solver bot (8808885201).
    Triggers when solver bot sends the full numbered solution list.
    Ignores: status messages, progress messages, individual bare-word messages.
    """
    sender = await event.get_sender()
    if not sender:
        return

    sender_id = str(getattr(sender, "id", ""))
    sender_uname = (getattr(sender, "username", "") or "").lower()
    target_solver = SOLVER_BOT.lower().lstrip("@")

    is_solver = (
        sender_id == target_solver or
        sender_uname == target_solver or
        sender_uname == "word_gridsbot" or
        sender_id == "8808885201"
    )

    if not is_solver:
        return

    text = event.message.text or ""

    # Ignore status / progress messages
    skip_phrases = [
        "Extracting grid", "Extracted Grid", "Loading dictionary",
        "Parsed", "Grid extracted", "clues!", "Words to forward",
        "New word #", "Sent directly", "Failed to send", "words sent",
        "Target GC", "Session reset", "Please ensure"
    ]
    if any(p in text for p in skip_phrases):
        return

    # Ignore single bare-word messages (individual word sends) — userbot already
    # submitted the full list from the numbered solution summary, no duplicates needed
    stripped = text.strip().upper()
    if re.match(r"^[A-Z]{3,20}$", stripped):
        log.info(f"⏭️  Ignoring single-word message from solver bot: '{stripped}' (already handled via full solution)")
        return

    words = parse_solver_words(text)
    if words:
        log.info(f"🧩 Solver solution received ({len(words)} words): {words}")
        state.active = True
        await submit_words(words)


_group_entity = None


async def get_group_entity():
    """Resolve and return the group entity safely from Telethon entity cache."""
    global _group_entity
    if _group_entity is None:
        try:
            _group_entity = await client.get_entity(GROUP_ID)
        except Exception:
            _group_entity = await client.get_entity(int(os.getenv("GROUP_ID", "-1002714592126")))
    return _group_entity


_solver_entity = None


async def get_solver_entity():
    """Resolve and cache solver bot entity (by numeric ID 8808885201 or username)."""
    global _solver_entity
    if _solver_entity is None:
        solver_setting = os.getenv("SOLVER_BOT", "8808885201").strip().lstrip("@")
        try:
            if solver_setting.isdigit():
                _solver_entity = await client.get_entity(int(solver_setting))
            else:
                _solver_entity = await client.get_entity(solver_setting)
        except Exception:
            try:
                _solver_entity = await client.get_entity(8808885201)
            except Exception as e:
                log.error(f"Failed to resolve solver bot entity (8808885201): {e}")
                raise
    return _solver_entity


async def ask_solver(grid_msg, clue_text: str):
    """
    Automatically forward the grid image + clue text to the solver bot.
    The solver bot will reply with the solution, which _capture_solver_reply picks up.
    """
    try:
        solver_target = await get_solver_entity()
        log.info("📤 Auto-forwarding grid image to solver bot...")

        # Forward the grid photo as a document/image to solver bot with clues as caption
        if grid_msg.photo:
            # Download the photo and resend (to avoid "Forwarded from" label in solver DM)
            photo_bytes = await client.download_media(grid_msg, bytes)
            await client.send_file(
                solver_target,
                photo_bytes,
                caption=clue_text or "",
                force_document=False
            )
            log.info("✅ Grid image + clues sent to solver bot!")
        elif clue_text:
            # No photo, just send clue text
            await client.send_message(solver_target, clue_text)
            log.info("✅ Clue text sent to solver bot!")

    except Exception as e:
        log.error(f"❌ Failed to send grid to solver bot: {e}")


_requested_clue_nums = set()


async def sync_unselected_clues():
    """
    Scans the latest clue list message from @WordGridRobot in GC,
    counts line-by-line (1..14) to find which clues are NOT checkmarked (☑️ / ✅),
    and sends those line numbers to solver bot (8808885201) in DM to get option 2, 3, etc.!
    """
    clue_text = ""
    try:
        async for msg in client.iter_messages(GROUP_ID, limit=20):
            sender = await msg.get_sender()
            uname = (getattr(sender, "username", "") or "").lower() if sender else ""
            if uname == WORD_GRID_BOT.lower():
                t = (msg.text or msg.caption or "").strip()
                if has_clue_pattern(t) or "Find these words" in t:
                    clue_text = t
                    break
    except Exception as e:
        log.warning(f"Failed to fetch clue list from GC: {e}")
        return

    if not clue_text:
        return

    unselected_nums = extract_missing_clue_numbers(clue_text)
    if not unselected_nums:
        log.info("🎉 All clue lines are checkmarked/solved!")
        _requested_clue_nums.clear()
        return

    to_request = [n for n in unselected_nums if n not in _requested_clue_nums]
    if not to_request:
        log.info(f"⏳ Unselected clues {unselected_nums} already requested from solver bot, waiting for reply...")
        return

    log.info(f"📋 Unselected clue line numbers in GC: {unselected_nums} (requesting alternate options for: {to_request})")
    solver_target = await get_solver_entity()
    for num in to_request:
        _requested_clue_nums.add(num)
        log.info(f"📨 Sending clue line #{num} to solver bot (8808885201) for next candidate...")
        await client.send_message(solver_target, str(num))
        await asyncio.sleep(2.0)


# ─── WORD SUBMISSION ──────────────────────────────────────────────────────────

_word_confirm_events: dict[str, asyncio.Event] = {}


async def submit_words(words: list[str]):
    """
    Type words in the group chat sequentially as the real user account.
    No bot name, no "Forwarded from" — completely anonymous!
    Waits for Word Grid Bot's reply confirmation (☑️ You found WORD) per word.
    After completing all words, syncs with GC clue list to request alternate candidates only for UNCHECKMARKED clues!
    """
    group_target = await get_group_entity()
    submitted = 0

    # Refresh history to get latest checkmarks
    await _scan_recent_history()

    for idx, word in enumerate(words):
        clue_num = idx + 1
        wu = word.upper()

        if wu in state.guessed_words:
            log.info(f"⏭️  Skipping #{clue_num} '{wu}' — already checkmarked/guessed")
            continue

        evt = asyncio.Event()
        _word_confirm_events[wu] = evt

        log.info(f"⌨️  Sending word #{clue_num} '{wu}' to group...")
        await client.send_message(group_target, wu)
        submitted += 1

        # Wait up to 3.5 seconds for confirmation reply from Word Grid Bot
        try:
            await asyncio.wait_for(evt.wait(), timeout=3.5)
            log.info(f"🎉 Word #{clue_num} '{wu}' CONFIRMED by Word Grid Bot!")
            state.guessed_words.add(wu)
        except asyncio.TimeoutError:
            log.warning(f"⚠️ Word #{clue_num} '{wu}' received NO reply from Word Grid Bot! Requesting alternate from solver...")
            solver_target = await get_solver_entity()
            await client.send_message(solver_target, str(clue_num))
            await asyncio.sleep(1.5)
        finally:
            _word_confirm_events.pop(wu, None)

        # Brief 1s pause before next word
        await asyncio.sleep(1.0)

    log.info(f"✅ Finished word batch ({submitted} submitted). Syncing unselected clues from GC...")
    await asyncio.sleep(2.0)
    await sync_unselected_clues()


# ─── GROUP CHAT HANDLER ───────────────────────────────────────────────────────

@client.on(events.NewMessage(chats=GROUP_ID))
@client.on(events.MessageEdited(chats=GROUP_ID))
async def handle_group_message(event):
    """
    Main event handler — watches the group for:
      - Word Grid Bot game messages (new game, word found, message edits, game over)
      - Other players typing words (to mark as guessed)
    """
    msg    = event.message
    sender = await event.get_sender()
    if not sender:
        return

    uname  = (getattr(sender, "username", "") or "").lower()
    text   = (msg.text or msg.caption or "").strip()
    is_wgb = uname == WORD_GRID_BOT.lower()

    # ── Track words typed by OTHER players ───────────────────
    if not is_wgb and not msg.out and state.active:
        bare = text.upper().strip()
        if re.match(r"^[A-Z]{3,20}$", bare):
            state.guessed_words.add(bare)
            log.info(f"👤 Other player typed: {bare} (marked as guessed)")

    if not is_wgb:
        return  # Everything below is only for Word Grid Bot messages

    # ─────────────────────────────────────────────────────────
    # From this point: msg is from @WordGridRobot
    # ─────────────────────────────────────────────────────────

    async with _game_lock:

        # 1. GAME OVER ─────────────────────────────────────────
        if is_game_over(text):
            log.info("🏁 Game over detected! Resetting game state.")
            state.reset()
            _requested_clue_nums.clear()
            return

        # 2. NEW GAME (photo + clue text) — AUTO-FORWARD TO SOLVER BOT ────────
        if msg.photo and has_clue_pattern(text) and not state.active:
            log.info("🎮 NEW GAME DETECTED! Auto-forwarding grid to solver bot...")
            state.reset()
            state.active = True
            state.grid_message = msg
            state.clue_text = text
            await _scan_recent_history()
            # Auto-send grid image + clues to solver bot (no manual forwarding needed!)
            asyncio.create_task(ask_solver(msg, text))
            return

        # 3. NORMAL GAME OVERRIDE ─────────────────────────────
        if is_normal_game(text) and not state.active:
            log.info("ℹ️ Normal game detected in group.")
            return

        # ── Active-game-only handlers ──────────────────────────
        if not state.active:
            return

        # 4. WORD FOUND CONFIRMATION ──────────────────────────
        confirmed = extract_confirmed_word(text)
        if confirmed:
            state.guessed_words.add(confirmed)
            log.info(f"✅ Word confirmed by bot: {confirmed}")
            if confirmed in _word_confirm_events:
                _word_confirm_events[confirmed].set()

        # 5. MISSING / UNSOLVED CLUES ─────────────────────────
        #    Whenever Word Grid Bot posts or edits the clue list, sync unselected clue line numbers!
        if has_clue_pattern(text) or "Find these words" in text:
            await sync_unselected_clues()
            return

        # 6. NEW HINT (text-only message with clue pattern) ───
        #    Word Grid Bot replied to our number with a new/harder hint
        if not msg.photo and has_clue_pattern(text) and state.grid_message:
            log.info(f"💡 New hint received: {text[:120]}")
            asyncio.create_task(ask_solver(state.grid_message, text))
            return


# ─── HISTORY & EXISTING GAME SCANNER ─────────────────────────────────────────

async def _scan_recent_history():
    """
    Scan the last 100 group messages to pre-populate guessed words.
    Crucially extracts all checkmarked words (✅ TILL, ☑️ SNOW, etc.) directly from clue lists!
    """
    try:
        async for msg in client.iter_messages(GROUP_ID, limit=100):
            text = (msg.text or msg.caption or "").strip()
            if not text:
                continue

            # 1. Checkmarked words from clue list lines
            solved_from_clues = extract_all_solved_words(text)
            for w in solved_from_clues:
                state.guessed_words.add(w)

            # 2. Confirmation reply messages
            confirmed = extract_confirmed_word(text)
            if confirmed:
                state.guessed_words.add(confirmed)

            # 3. Raw word guesses typed in chat
            t = text.upper()
            if re.match(r"^[A-Z]{3,20}$", t):
                state.guessed_words.add(t)
    except Exception as e:
        log.warning(f"History scan failed: {e}")
    log.info(f"📚 Pre-loaded {len(state.guessed_words)} solved/guessed word(s) from chat history")


async def check_existing_game():
    """
    Check if a game is ALREADY active in the chat when the userbot starts.
    If so, immediately resumes solving and playing!
    """
    async with _game_lock:
        if state.active:
            return

        grid_msg = None
        clue_text = ""
        game_ended = False

        try:
            async for msg in client.iter_messages(GROUP_ID, limit=50):
                sender = await msg.get_sender()
                uname = (getattr(sender, "username", "") or "").lower() if sender else ""
                is_wgb = uname == WORD_GRID_BOT.lower()
                text = (msg.text or msg.caption or "").strip()

                if is_wgb and is_game_over(text):
                    game_ended = True
                    break

                if is_wgb and msg.photo and has_clue_pattern(text):
                    grid_msg = msg
                    clue_text = text
                    break

            if grid_msg and not game_ended:
                log.info("🎯 ACTIVE GAME DETECTED IN CHAT HISTORY! Resuming game...")
                state.reset()
                state.active = True
                state.grid_message = grid_msg
                state.clue_text = clue_text

                await _scan_recent_history()
                log.info("ℹ️  Forward the grid image manually to @word_gridsbot if you haven't already!")
            else:
                log.info("ℹ️  No active game found in recent history.")
        except Exception as e:
            log.warning(f"Failed to check existing game: {e}")


# ─── ENTRY POINT ─────────────────────────────────────────────────────────────

async def main():
    print()
    print("  ==========================================")
    print("   AUGRAM WORD GRID USERBOT")
    print("   Hard Mode Word Search Automation")
    print("  ==========================================")
    print()

    if not API_ID or not API_HASH:
        print("  ❌  TELEGRAM_API_ID / TELEGRAM_API_HASH missing in .env!")
        print("      Get them from: https://my.telegram.org\n")
        return

    await client.start()
    me = await client.get_me()

    log.info("⏳ Fetching dialogs cache...")
    await client.get_dialogs()
    await get_group_entity()

    log.info(f"✅  Logged in as: {me.first_name} (@{me.username})")
    log.info(f"👁️   Watching group : {GROUP_ID}")
    log.info(f"🤖  Word Grid Bot  : @{WORD_GRID_BOT}")
    log.info(f"🔧  Solver Bot     : @{SOLVER_BOT}")
    log.info(f"⏱️   Word delay     : {WORD_DELAY}s (+random jitter)")
    log.info("─" * 55)

    # Check if there is an active game already running in the chat
    await check_existing_game()

    log.info("Waiting for game events... (Ctrl+C to stop)")
    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
