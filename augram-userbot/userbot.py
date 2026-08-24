"""
Augram Word Forwarder Userbot
=============================
Simple workflow:
1. You forward word messages into your Personal GC (or Saved Messages).
2. Userbot detects the words you forwarded/sent.
3. Userbot immediately types and posts only those words into the Target Group Chat.
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

# Delay between sending words to target GC (seconds)
raw_delay = os.getenv("WORD_DELAY", "0.5").strip()
clean_delay = re.sub(r"[^\d.]", "", raw_delay)
SEND_DELAY = float(clean_delay) if clean_delay else 0.5

# Optional: ID or title of your Personal GC (Leave None to use 'me' / Saved Messages, or set PERSONAL_GC_ID in .env)
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
    
    # Clean text lines
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

_send_lock = asyncio.Lock()

@client.on(events.NewMessage(chats=PERSONAL_GC))
async def handle_personal_gc_message(event):
    """
    Fires whenever a message is forwarded/sent into your Personal GC (or Saved Messages).
    Queues words, waits for SEND_DELAY (with typing indicator), then posts to Target GC.
    """
    text = event.message.text or ""
    words = extract_words(text)
    
    if not words:
        return
        
    target = await get_target_entity()
    
    async with _send_lock:
        for word in words:
            log.info(f"⏳ Waiting {SEND_DELAY}s before sending '{word}'...")
            try:
                async with client.action(target, "typing"):
                    await asyncio.sleep(SEND_DELAY)
            except Exception:
                await asyncio.sleep(SEND_DELAY)

            log.info(f"📤 Forwarding word '{word}' -> Target Group Chat ({TARGET_GC_ID})...")
            await client.send_message(target, word)

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
    log.info("Ready! Forward words to your Personal GC / Saved Messages, and they will post to the Target GC automatically.")

    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
