import logging
import os
import sys
import io
import threading
import time
import html
import urllib.request
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Optional

# Ensure UTF-8 output encoding for Windows console logs
if sys.platform == "win32":
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    except Exception:
        pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from dotenv import load_dotenv
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)

from database import (
    init_db,
    upsert_user,
    get_user_by_username,
    get_user_by_id,
    set_user_afk,
    remove_user_afk,
    get_user_afk,
    get_afk_user_by_username,
    get_bot_stats
)

# Load environment variables
env_path = os.path.join(BASE_DIR, ".env")
if os.path.exists(env_path):
    load_dotenv(env_path)
else:
    load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Initialize Database
init_db()

# Lightweight HTTP Health Check Server
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"AFK Bot is running!")

    def log_message(self, format, *args):
        return

def start_health_server():
    port = int(os.getenv("PORT", 8080))
    try:
        server = HTTPServer(("0.0.0.0", port), HealthHandler)
        logger.info(f"[HTTP] Health check server listening on port {port}")
        server.serve_forever()
    except Exception as e:
        logger.warning(f"[HTTP] Could not start health check server: {e}")

def keep_alive_heartbeat():
    time.sleep(10)
    port = int(os.getenv("PORT", 8080))
    url = f"http://127.0.0.1:{port}/"
    while True:
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'AFKBotKeepAlive/1.0'})
            with urllib.request.urlopen(req, timeout=5) as response:
                pass
        except Exception:
            pass
        time.sleep(600)

# --- HELPER FUNCTIONS ---

def format_afk_duration(seconds: float) -> str:
    seconds = int(seconds)
    if seconds < 5:
        return "a few seconds"
    if seconds < 60:
        return f"{seconds} second{'s' if seconds != 1 else ''}"
    
    minutes = seconds // 60
    hours = minutes // 60
    days = hours // 24
    
    rem_hours = hours % 24
    rem_minutes = minutes % 60
    rem_seconds = seconds % 60
    
    parts = []
    if days > 0:
        parts.append(f"{days} day{'s' if days != 1 else ''}")
    if rem_hours > 0:
        parts.append(f"{rem_hours} hour{'s' if rem_hours != 1 else ''}")
    if rem_minutes > 0:
        parts.append(f"{rem_minutes} minute{'s' if rem_minutes != 1 else ''}")
    if rem_seconds > 0 and days == 0 and rem_hours == 0:
        parts.append(f"{rem_seconds} second{'s' if rem_seconds != 1 else ''}")
        
    return ", ".join(parts) if parts else "a moment"

def get_message_link(chat, message_id: int) -> str:
    if not message_id or not chat:
        return ""
    if getattr(chat, 'username', None):
        return f"https://t.me/{chat.username}/{message_id}"
    cid_str = str(chat.id)
    if cid_str.startswith("-100"):
        cid = cid_str[4:]
        return f"https://t.me/c/{cid}/{message_id}"
    return ""

def parse_afk_time(afk_since_str: str) -> datetime:
    try:
        clean_str = str(afk_since_str).replace("Z", "+00:00")
        dt = datetime.fromisoformat(clean_str)
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt
    except Exception:
        return datetime.utcnow()

# --- COMMAND HANDLERS ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user:
        upsert_user(user.id, user.username or "", user.first_name or "", user.last_name or "")
    
    msg = (
        "💤 <b>Welcome to AFK Bot!</b>\n\n"
        "I help group members notify others when they are Away From Keyboard.\n\n"
        "<b>📌 How to use:</b>\n"
        "• Type <code>/afk [reason]</code> to go AFK.\n"
        "• Or reply to a message/sticker with <code>/afk</code>!\n"
        "• When someone tags or replies to you, I'll tell them you're AFK.\n"
        "• As soon as you type any message, I'll welcome you back!"
    )
    await update.effective_message.reply_text(msg, parse_mode="HTML")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "📖 <b>AFK Bot Command Guide:</b>\n\n"
        "• <code>/afk [reason]</code> — Set your AFK status\n"
        "• <code>/afk</code> (replying to a sticker/text) — Set replied item as reason\n"
        "• <code>/start</code> — Start the bot\n"
        "• <code>/help</code> — Show this help message"
    )
    await update.effective_message.reply_text(msg, parse_mode="HTML")

async def afk_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    user = update.effective_user
    if not msg or not user:
        return

    reason = " ".join(context.args).strip() if context.args else ""
    reason_msg_id = 0
    
    # If no reason typed, check if user replied to a message or sticker
    if msg.reply_to_message:
        reply_msg = msg.reply_to_message
        reason_msg_id = reply_msg.message_id
        if not reason:
            if reply_msg.text:
                reason = reply_msg.text.strip()
            elif reply_msg.caption:
                reason = reply_msg.caption.strip()
            elif reply_msg.sticker:
                emoji = reply_msg.sticker.emoji or ""
                reason = f"[Sticker {emoji}]".strip()
            elif reply_msg.photo:
                reason = "[Photo]"
            elif reply_msg.video:
                reason = "[Video]"
            elif reply_msg.animation:
                reason = "[GIF]"
            elif reply_msg.voice or reply_msg.audio:
                reason = "[Audio]"
            elif reply_msg.document:
                doc_name = reply_msg.document.file_name or ""
                reason = f"[Document] {doc_name}".strip()
            
    if not reason:
        reason = "Away"

    # Truncate reason if too long
    if len(reason) > 200:
        reason = reason[:197] + "..."

    upsert_user(user.id, user.username or "", user.first_name or "", user.last_name or "")
    set_user_afk(user.id, reason, reason_msg_id, update.effective_chat.id)

    safe_name = html.escape(user.first_name or "User")
    safe_reason = html.escape(reason)
    
    reason_html = f"<i>{safe_reason}</i>"
    if reason_msg_id:
        link = get_message_link(update.effective_chat, reason_msg_id)
        if link:
            reason_html = f'<a href="{link}"><i>{safe_reason}</i></a>'
    
    await msg.reply_text(
        f"💤 <b>{safe_name}</b> Qt💋 is now AFK!\nReason: {reason_html}",
        parse_mode="HTML"
    )

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if OWNER_ID != 0 and update.effective_user.id != OWNER_ID:
        return
    stats = get_bot_stats()
    msg = (
        "👑 <b>AFK Bot Owner Stats</b>\n\n"
        f"👥 <b>Total Cached Users:</b> <code>{stats['cached_users']}</code>\n"
        f"💤 <b>Active AFK Members:</b> <code>{stats['active_afks']}</code>"
    )
    await update.message.reply_text(msg, parse_mode="HTML")

# --- MESSAGE LISTENER (AFK RETURN & MENTIONS) ---

async def handle_afk_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    user = update.effective_user
    if not msg or not user:
        return

    # Skip processing if message is a command
    if msg.text and msg.text.strip().startswith("/"):
        return

    # Upsert sender into cached users table
    try:
        upsert_user(user.id, user.username or "", user.first_name or "", user.last_name or "")
    except Exception as e:
        logger.error(f"Error upserting user: {e}")

    # 1. Check if sender was AFK (Welcome back!)
    afk_info = remove_user_afk(user.id)
    if afk_info:
        try:
            afk_time = parse_afk_time(afk_info["afk_since"])
            elapsed = max(0.0, (datetime.utcnow() - afk_time).total_seconds())
            duration_str = format_afk_duration(elapsed)
            safe_name = html.escape(user.first_name or "User")
            await msg.reply_text(
                f" Welcome back,qt💋 <b>{safe_name}</b>! You were away for <b>{duration_str}</b>.",
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Error restoring AFK user {user.id}: {e}")

    # 2. Check if this message mentions or replies to an AFK user
    notified_user_ids = set()

    # Check Reply-to message
    if msg.reply_to_message and msg.reply_to_message.from_user:
        target_user = msg.reply_to_message.from_user
        if target_user.id != user.id:
            target_afk = get_user_afk(target_user.id)
            if target_afk:
                notified_user_ids.add(target_user.id)
                try:
                    afk_time = parse_afk_time(target_afk["afk_since"])
                    elapsed = max(0.0, (datetime.utcnow() - afk_time).total_seconds())
                    duration_str = format_afk_duration(elapsed)
                    target_name = html.escape(target_user.first_name or "User")
                    safe_reason = html.escape(target_afk["reason"] or "Away")
                    
                    reason_html = f"<i>{safe_reason}</i>"
                    r_msg_id = target_afk.get("reason_msg_id") or 0
                    if r_msg_id:
                        link = get_message_link(update.effective_chat, r_msg_id)
                        if link:
                            reason_html = f'<a href="{link}"><i>{safe_reason}</i></a>'

                    await msg.reply_text(
                        f"💤 <b>{target_name}</b> Qt💋 is currently AFK! (Away for <b>{duration_str}</b>)\nReason: {reason_html}",
                        parse_mode="HTML"
                    )
                except Exception as e:
                    logger.error(f"Error notifying AFK reply for user {target_user.id}: {e}")

    # Check Message Entities (@username or text_mention)
    if msg.entities:
        for entity in msg.entities:
            target_afk = None
            target_name = ""
            
            if entity.type == "text_mention" and entity.user:
                t_user = entity.user
                if t_user.id != user.id and t_user.id not in notified_user_ids:
                    target_afk = get_user_afk(t_user.id)
                    target_name = html.escape(t_user.first_name or "User")
                    if target_afk:
                        notified_user_ids.add(t_user.id)
                        
            elif entity.type == "mention" and msg.text:
                username_raw = msg.text[entity.offset:entity.offset + entity.length]
                target_afk = get_afk_user_by_username(username_raw)
                if target_afk and target_afk.get("user_id") != user.id and target_afk.get("user_id") not in notified_user_ids:
                    notified_user_ids.add(target_afk["user_id"])
                    target_name = html.escape(target_afk.get("first_name") or "User")

            if target_afk and target_name:
                try:
                    afk_time = parse_afk_time(target_afk.get("afk_since", ""))
                    elapsed = max(0.0, (datetime.utcnow() - afk_time).total_seconds())
                    duration_str = format_afk_duration(elapsed)
                    safe_reason = html.escape(target_afk.get("reason") or "Away")
                    
                    reason_html = f"<i>{safe_reason}</i>"
                    r_msg_id = target_afk.get("reason_msg_id") or 0
                    if r_msg_id:
                        link = get_message_link(update.effective_chat, r_msg_id)
                        if link:
                            reason_html = f'<a href="{link}"><i>{safe_reason}</i></a>'

                    await msg.reply_text(
                        f"💤 <b>{target_name}</b> is currently AFK! (Away for <b>{duration_str}</b>)\nReason: {reason_html}",
                        parse_mode="HTML"
                    )
                except Exception as e:
                    logger.error(f"Error notifying AFK mention for user: {e}")

async def global_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Exception while handling an update: {context.error}", exc_info=context.error)

# Main Application Entrypoint
def main():
    if not BOT_TOKEN or BOT_TOKEN == "YOUR_TELEGRAM_BOT_TOKEN_HERE":
        print("❌ Error: TELEGRAM_BOT_TOKEN is not set in .env file.")
        sys.exit(1)

    # Start optional background HTTP health check server for Render/Railway
    threading.Thread(target=start_health_server, daemon=True).start()
    threading.Thread(target=keep_alive_heartbeat, daemon=True).start()

    # Build python-telegram-bot application
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_error_handler(global_error_handler)

    # Register Command Handlers (Group 0)
    app.add_handler(CommandHandler("start", start_command), group=0)
    app.add_handler(CommandHandler("help", help_command), group=0)
    app.add_handler(CommandHandler(["afk"], afk_command), group=0)
    app.add_handler(CommandHandler("stats", stats_command), group=0)

    # Register AFK Return & Mention Listener (Group 1 - runs after commands)
    app.add_handler(MessageHandler(~filters.StatusUpdate.ALL, handle_afk_messages), group=1)

    print("🚀 Standalone AFK Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
