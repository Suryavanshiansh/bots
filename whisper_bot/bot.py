import logging
import os
import sys
import uuid
import threading
import time
import urllib.request
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Optional

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from dotenv import load_dotenv
from telegram import (
    Update,
    InlineQueryResultArticle,
    InputTextMessageContent,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    InlineQueryHandler,
    CallbackQueryHandler,
    ContextTypes
)

from database import init_db, save_whisper, get_whisper

# Load environment variables
env_path = os.path.join(BASE_DIR, ".env")
if os.path.exists(env_path):
    load_dotenv(env_path)
else:
    load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))

# Initialize database
init_db()

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# HTTP Health check server for Render Web Service
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Whisper Bot is running!")

    def log_message(self, format, *args):
        return

def start_health_server():
    port = int(os.getenv("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    print(f"🌐 Health check HTTP server listening on port {port}")
    server.serve_forever()

def keep_alive_heartbeat():
    url = os.getenv("RENDER_EXTERNAL_URL")
    if not url:
        return
    while True:
        time.sleep(600)  # 10 minutes
        try:
            urllib.request.urlopen(url, timeout=10)
        except Exception:
            pass

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = (
        "🤫 <b>Welcome to Secret Whisper Bot!</b>\n\n"
        "Send secret messages in any Telegram group or private chat that ONLY the recipient, sender, or owner can read!\n\n"
        "<b>How to use me in any chat:</b>\n"
        "Type in any message box:\n"
        "• <code>@botusername [your secret message] @username</code>\n"
        "• <code>@botusername [your secret message] [user_id]</code>\n\n"
        "<b>Example:</b>\n"
        "<code>@mywhisperbot Hello, meet me at 5 PM! @john_doe</code>\n\n"
        "I will create a secret button in the group chat. Only the intended target can click and view the message! 🔒"
    )
    await update.message.reply_text(welcome_text, parse_mode="HTML")

async def inline_whisper_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.inline_query.query.strip()
    sender = update.inline_query.from_user
    
    if not query:
        results = [
            InlineQueryResultArticle(
                id="help",
                title="🤫 How to send a Secret Whisper",
                description="Format: @botusername [secret message] @username or [user_id]",
                input_message_content=InputTextMessageContent(
                    "<b>🤫 Secret Whisper Guide:</b>\n\n"
                    "Type in any chat:\n"
                    "<code>@botusername [secret message] @target_username</code>\n"
                    "or\n"
                    "<code>@botusername [secret message] [target_user_id]</code>",
                    parse_mode="HTML"
                )
            )
        ]
        await update.inline_query.answer(results, cache_time=1)
        return

    words = query.split()
    target_username: Optional[str] = None
    target_id: Optional[int] = None
    secret_text = ""

    last_word = words[-1]
    if last_word.startswith("@") and len(last_word) > 1:
        target_username = last_word[1:].lower()
        secret_text = " ".join(words[:-1])
    elif last_word.isdigit():
        target_id = int(last_word)
        secret_text = " ".join(words[:-1])
    else:
        # No target specified, treat whole query as secret text for anyone
        secret_text = query

    if not secret_text:
        secret_text = "Secret Message"

    whisper_id = uuid.uuid4().hex[:10]

    # Save to database
    save_whisper(
        whisper_id=whisper_id,
        sender_id=sender.id,
        sender_username=sender.username,
        target_id=target_id,
        target_username=target_username,
        secret_text=secret_text
    )

    # Format recipient display name
    if target_username:
        target_display = f"@{target_username}"
    elif target_id:
        target_display = f"User ID {target_id}"
    else:
        target_display = "Anyone"

    message_content = (
        f"🎁 <b>A secret whisper has been sent for {target_display}!</b>\n"
        f"<i>Only {target_display}, the sender, or owner can open this whisper.</i>"
    )

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔐 Show Secret Whisper 🤫", callback_data=f"ws_{whisper_id}")]
    ])

    results = [
        InlineQueryResultArticle(
            id=whisper_id,
            title=f"🔒 Send Secret Whisper to {target_display}",
            description=f"Secret: {secret_text[:30]}...",
            input_message_content=InputTextMessageContent(message_content, parse_mode="HTML"),
            reply_markup=keyboard
        )
    ]

    await update.inline_query.answer(results, cache_time=1)

async def handle_whisper_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    callback_data = query.data

    if not callback_data.startswith("ws_"):
        return

    whisper_id = callback_data[3:]
    whisper = get_whisper(whisper_id)

    if not whisper:
        await query.answer(text="❌ This secret whisper has expired or was not found.", show_alert=True)
        return

    from_user = query.from_user
    user_id = from_user.id
    user_username = (from_user.username or "").lower()

    # Permission check: Allowed if Sender, Target Username, Target ID, or OWNER_ID
    is_sender = (user_id == whisper["sender_id"])
    is_owner = (OWNER_ID > 0 and user_id == OWNER_ID)
    is_target_id = (whisper["target_id"] is not None and user_id == whisper["target_id"])
    is_target_username = (
        whisper["target_username"] is not None and
        user_username == whisper["target_username"].lower()
    )

    if is_sender or is_target_id or is_target_username or is_owner:
        role_label = ""
        if is_owner and not (is_sender or is_target_id or is_target_username):
            role_label = " 👑 [Owner View]"
        
        secret_text = whisper["secret_text"]
        await query.answer(text=f"🤫 Secret Whisper{role_label}:\n\n{secret_text}", show_alert=True)
    else:
        await query.answer(
            text="❌ This secret whisper is not for you! Only the intended recipient or sender can open it.",
            show_alert=True
        )

def main():
    if not BOT_TOKEN or BOT_TOKEN == "YOUR_TELEGRAM_BOT_TOKEN_HERE":
        print("\n=======================================================")
        print("❌ ERROR: TELEGRAM_BOT_TOKEN is missing in .env file!")
        print(f"Please edit {os.path.join(BASE_DIR, '.env')} and paste your bot token from @BotFather")
        print("=======================================================\n")
        return

    # Start health check server & keep-alive for Render
    threading.Thread(target=start_health_server, daemon=True).start()
    threading.Thread(target=keep_alive_heartbeat, daemon=True).start()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(InlineQueryHandler(inline_whisper_query))
    app.add_handler(CallbackQueryHandler(handle_whisper_callback))

    print("\n🤫 Telegram Secret Whisper Bot is starting...")
    print(f"👑 Owner ID configured: {OWNER_ID if OWNER_ID > 0 else 'None'}")
    print("Press Ctrl+C to stop.\n")
    app.run_polling()

if __name__ == "__main__":
    main()
