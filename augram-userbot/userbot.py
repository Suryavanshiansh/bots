"""
Augram Word Forwarder Userbot
=============================
Workflow:
1. Listens to Target GC to track words already guessed (by other members or bot confirmations/clue checkmarks).
2. Listens to your Personal GC / Saved Messages where you forward single words.
3. If a word you forwarded has ALREADY been sent/solved in the Target GC by someone else, it SKIPS sending it!
4. Otherwise, types & posts the word into Target GC cleanly.
"""

import asyncio
import logging
import os
import sys
import re

# Force UTF-8 output on Windows console
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv
from telethon import TelegramClient, events

load_dotenv()

# ─── CONFIGURATION ────────────────────────────────────────────────────────────
API_ID       = int(os.getenv("TELEGRAM_API_ID", "0"))
API_HASH     = os.getenv("TELEGRAM_API_HASH", "")
TARGET_GC_ID = int(os.getenv("GROUP_ID", "-1002714592126"))
WORD_GRID_BOT = os.getenv("WORD_GRID_BOT", "WordGridRobot").lstrip("@")

# Delay between sending words to target GC (seconds)
raw_delay = os.getenv("WORD_DELAY", "0.5").strip()
clean_delay = re.sub(r"[^\d.]", "", raw_delay)
SEND_DELAY = float(clean_delay) if clean_delay else 0.5

# Personal GC ID or 'me' (Saved Messages)
PERSONAL_GC  = os.getenv("PERSONAL_GC_ID", "me")
if PERSONAL_GC.lstrip("-").isdigit():
    PERSONAL_GC = int(PERSONAL_GC)

# ─── LOGGING ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(levelname)s │ %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("word_relay")

# ─── TELETHON CLIENT ──────────────────────────────────────────────────────────
client = TelegramClient("wordgrid_session", API_ID, API_HASH)

_target_entity = None
guessed_words = set()

async def get_target_entity():
    global _target_entity
    if _target_entity is None:
        _target_entity = await client.get_entity(TARGET_GC_ID)
    return _target_entity

def extract_words(text: str) -> list[str]:
    """
    Extract uppercase word(s) from message text.
    Handles single words ("DECK") or multiple words separated by newlines/spaces.
    """
    if not text:
        return []
    
    lines = text.strip().splitlines()
    found_words = []
    
    for line in lines:
        cleaned = line.strip().upper()
        # Remove numbers or prefixes if present (e.g. "1. DECK" -> "DECK")
        cleaned = re.sub(r"^\d+[\.\)\s\-]+", "", cleaned).strip()
        # Check if line is a valid word (3 to 20 letters)
        if re.match(r"^[A-Z]{3,20}$", cleaned):
            found_words.append(cleaned)
            
    return found_words

def extract_all_solved_words(text: str) -> list[str]:
    """Extract checkmarked words (☑️ WORD or ✅ WORD) from clue list lines."""
    words = []
    if not text:
        return words
    lines = text.splitlines()
    for line in lines:
        if "☑" in line or "✅" in line:
            m = re.search(r"[☑✅]\s*(?:[A-Z0-9.\-\s]+)?\s*([A-Z]{3,20})", line, re.IGNORECASE)
            if m:
                words.append(m.group(1).upper())
    return words

# ─── LISTEN TO TARGET GC MESSAGES (TRACK OTHER MEMBERS' GUESSES) ───────────────

@client.on(events.NewMessage(chats=TARGET_GC_ID))
@client.on(events.MessageEdited(chats=TARGET_GC_ID))
async def track_target_gc_messages(event):
    """Tracks words typed by other members or confirmed by WordGridRobot in Target GC."""
    text = (event.message.text or event.message.caption or "").strip()
    if not text:
        return

    # 1. Track single words typed in chat by any member
    bare = text.upper().strip()
    if re.match(r"^[A-Z]{3,20}$", bare):
        if bare not in guessed_words:
            guessed_words.add(bare)
            log.info(f"👥 Tracked word typed in GC: '{bare}'")

    # 2. Track checkmarked words from bot clue lists (☑️ WORD / ✅ WORD)
    solved_words = extract_all_solved_words(text)
    for w in solved_words:
        if w not in guessed_words:
            guessed_words.add(w)
            log.info(f"✅ Tracked solved word from GC clue list: '{w}'")

    # 3. If game reset/over message detected, clear old guessed words cache
    if "game over" in text.lower() or "winner" in text.lower() or "congratulations" in text.lower():
        log.info("🏁 Game over detected in GC! Clearing tracked words cache.")
        guessed_words.clear()

async def scan_recent_gc_history():
    """Pre-loads recent words typed in GC on startup."""
    try:
        async for msg in client.iter_messages(TARGET_GC_ID, limit=50):
            text = (msg.text or msg.caption or "").strip()
            if not text:
                continue
            bare = text.upper().strip()
            if re.match(r"^[A-Z]{3,20}$", bare):
                guessed_words.add(bare)
            for w in extract_all_solved_words(text):
                guessed_words.add(w)
        log.info(f"📚 Pre-loaded {len(guessed_words)} already guessed/solved words from GC history.")
    except Exception as e:
        log.warning(f"Could not pre-scan GC history: {e}")

# ─── LISTEN TO PERSONAL GC MESSAGES ───────────────────────────────────────────

_send_lock = asyncio.Lock()

@client.on(events.NewMessage(chats=PERSONAL_GC))
async def handle_personal_gc_message(event):
    """
    Fires whenever a message is forwarded/sent into your Personal GC (or Saved Messages).
    Checks if word was already sent/guessed in Target GC. Skips if already sent!
    """
    text = event.message.text or ""
    words = extract_words(text)
    
    if not words:
        return
        
    target = await get_target_entity()
    
    async with _send_lock:
        for word in words:
            word_upper = word.upper()
            if word_upper in guessed_words:
                log.info(f"⏭️ SKIPPING '{word_upper}' — already sent/guessed in GC by someone else!")
                continue

            log.info(f"⏳ Waiting {SEND_DELAY}s before sending '{word_upper}'...")
            try:
                async with client.action(target, "typing"):
                    await asyncio.sleep(SEND_DELAY)
            except Exception:
                await asyncio.sleep(SEND_DELAY)

            log.info(f"📤 Forwarding word '{word_upper}' -> Target Group Chat ({TARGET_GC_ID})...")
            await client.send_message(target, word_upper)
            guessed_words.add(word_upper)

async def main():
    print()
    print("  ==========================================")
    print("   WORD FORWARDER USERBOT RELAY")
    print("  ==========================================")
    print()

    if not API_ID or not API_HASH:
        print("  ❌ TELEGRAM_API_ID / TELEGRAM_API_HASH missing in .env!")
        return

    await client.start()
    me = await client.get_me()

    log.info("⏳ Fetching chat info...")
    await client.get_dialogs()
    target_ent = await get_target_entity()
    target_name = getattr(target_ent, 'title', str(TARGET_GC_ID))

    log.info(f"✅ Logged in as : {me.first_name} (@{me.username})")
    log.info(f"📥 Listening in : {PERSONAL_GC} (Saved Messages / Personal GC)")
    log.info(f"📤 Posting to   : {target_name} ({TARGET_GC_ID})")
    log.info(f"⏱️  Send Delay  : {SEND_DELAY}s")
    log.info("─" * 55)

    await scan_recent_gc_history()

    log.info("Ready! Forward words to your Personal GC / Saved Messages. Words already typed in GC by others will be automatically skipped.")

    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
