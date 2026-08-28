import logging
import os
import sys
import io
import uuid
import threading
import time
import urllib.request
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

from database import (
    init_db,
    save_whisper,
    get_whisper,
    mark_whisper_seen,
    get_all_past_targets,
    upsert_user,
    get_user_by_id,
    get_user_by_username
)

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
    print(f"[HTTP] Health check server listening on port {port}")
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
    if update.effective_user:
        upsert_user(
            update.effective_user.id,
            update.effective_user.username,
            update.effective_user.first_name,
            update.effective_user.last_name
        )

    bot_user = await context.bot.get_me()
    bot_username = bot_user.username or "whisperbot"

    welcome_text = (
        "🤫 <b>Welcome to Secret Whisper Bot!</b>\n\n"
        "I allow you to send secret <b>whisper messages</b> in any Telegram group or private chat! The message is hidden behind a button and can ONLY be opened by the intended recipient, the sender, or the owner.\n\n"
        "<b>✨ How to use me in 3 simple steps:</b>\n\n"
        "1️⃣ Open any Telegram chat or group.\n"
        "2️⃣ Type in message box:\n"
        "   <code>@{bot_username} [your secret message] @username</code>\n"
        "3️⃣ Tap the popup whisper card to send!\n\n"
        "<b>💡 Quick Examples:</b>\n"
        "• <code>@{bot_username} Meet me at 5 PM! @john_doe</code>\n"
        "• <code>@{bot_username} Secret code 9921 123456789</code> <i>(User ID method)</i>\n\n"
        "Tap the buttons below to try it out or read full instructions!"
    )

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✨ Try Sending a Whisper", switch_inline_query="Hello secret whisper! @username")
        ],
        [
            InlineKeyboardButton("📖 Detailed Guide", callback_data="guide_info"),
            InlineKeyboardButton("🆔 User ID Method", callback_data="id_info")
        ],
        [
            InlineKeyboardButton("➕ Add Me to a Group", url=f"https://t.me/{bot_username}?startgroup=true")
        ]
    ])

    await update.message.reply_text(welcome_text, parse_mode="HTML", reply_markup=keyboard)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)

def resolve_target_display_info(target_username: Optional[str], target_id: Optional[int]) -> tuple[str, str]:
    """
    Resolves target to (html_display, plain_name).
    Uses clean bold text for recipient names without @ symbols to prevent Rose Bot mention filters from deleting messages.
    """
    if target_id:
        db_u = get_user_by_id(target_id)
        if db_u and db_u.get("first_name"):
            name = db_u["first_name"].strip()
            return f'<b>{name}</b>', name
        elif target_username:
            uname = target_username.lstrip("@")
            return f'<b>{uname}</b>', uname
        else:
            return f'User ID {target_id}', f'User ID {target_id}'

    if target_username:
        clean_uname = target_username.lstrip("@")
        db_u = get_user_by_username(clean_uname)
        if db_u and db_u.get("first_name"):
            name = db_u["first_name"].strip()
            return f'<b>{name}</b>', name
        else:
            return f'<b>{clean_uname}</b>', clean_uname

    return "Anyone", "Anyone"

async def inline_whisper_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        query = update.inline_query.query.strip()
        sender = update.inline_query.from_user
        try:
            upsert_user(sender.id, sender.username, sender.first_name, sender.last_name)
        except Exception as e:
            logging.error(f"Error in upsert_user: {e}")

        bot_username = context.bot.username or "XXThc_bot"

        if not query:
            results = [
                InlineQueryResultArticle(
                    id="help",
                    title="🤫 How to send a Secret Whisper",
                    description=f"Format: @{bot_username} [secret message] @username or [user_id]",
                    input_message_content=InputTextMessageContent(
                        f"<b>🤫 Secret Whisper Guide:</b>\n\n"
                        f"Type in any chat:\n"
                        f"<code>@{bot_username} [secret message] @target_username</code>\n"
                        f"or\n"
                        f"<code>@{bot_username} [secret message] [target_user_id]</code>",
                        parse_mode="HTML"
                    )
                )
            ]
            await update.inline_query.answer(results, cache_time=0, is_personal=True)
            return

        words = query.split()
        target_username: Optional[str] = None
        target_id: Optional[int] = None
        secret_text = ""

        # Parse target username or target ID from anywhere in query (first, last, or middle)
        target_index = -1
        for i, word in enumerate(words):
            if word.startswith("@") and len(word) > 1:
                target_username = word[1:].lower()
                target_index = i
                break
            elif word.isdigit() and len(word) >= 5:
                target_id = int(word)
                target_index = i
                break

        if target_index != -1:
            secret_text = " ".join(words[:target_index] + words[target_index+1:])
        else:
            secret_text = query

        if not secret_text:
            secret_text = "Secret Message"

        results = []

        if target_index != -1 or target_username or target_id:
            # User explicitly specified a target in the query
            if target_id:
                try:
                    db_u = get_user_by_id(target_id)
                    if db_u and db_u.get("username"):
                        target_username = db_u["username"]
                except Exception as e:
                    logging.error(f"Error fetching user by id: {e}")
            elif target_username:
                try:
                    db_u = get_user_by_username(target_username)
                    if db_u and db_u.get("user_id"):
                        target_id = db_u["user_id"]
                except Exception as e:
                    logging.error(f"Error fetching user by username: {e}")

            whisper_id = uuid.uuid4().hex[:10]
            try:
                save_whisper(
                    whisper_id=whisper_id,
                    sender_id=sender.id,
                    sender_username=sender.username,
                    target_id=target_id,
                    target_username=target_username,
                    secret_text=secret_text
                )
            except Exception as e:
                logging.error(f"Error saving whisper: {e}")

            target_display, target_plain = resolve_target_display_info(target_username, target_id)

            message_content = (
                f"🎁 <b>A secret whisper has been sent to</b> {target_display}!\n"
                f"<i>Only</i> {target_display} <i>or the sender can open this whisper.</i>"
            )

            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔐 Show Secret Whisper 🤫", callback_data=f"ws_{whisper_id}")]
            ])
            results.append(
                InlineQueryResultArticle(
                    id=whisper_id,
                    title=f"🔒 Send Secret Whisper to {target_plain}",
                    description=f"Secret: {secret_text[:30]}...",
                    input_message_content=InputTextMessageContent(message_content, parse_mode="HTML"),
                    reply_markup=keyboard
                )
            )
        else:
            # No target explicitly typed, show past recipients list as quick selection options!
            past_targets = []
            try:
                past_targets = get_all_past_targets(sender.id)
            except Exception as e:
                logging.error(f"Error fetching past targets: {e}")

            for pt in past_targets:
                t_user = pt.get("target_username")
                t_id = pt.get("target_id")
                t_name = pt.get("target_name")

                w_id = uuid.uuid4().hex[:10]
                try:
                    save_whisper(
                        whisper_id=w_id,
                        sender_id=sender.id,
                        sender_username=sender.username,
                        target_id=t_id,
                        target_username=t_user,
                        secret_text=secret_text
                    )
                except Exception as e:
                    logging.error(f"Error saving past target whisper: {e}")

                t_disp, t_plain = resolve_target_display_info(t_user, t_id)
                if t_name:
                    t_plain = t_name.strip()
                    t_disp = f'<b>{t_plain}</b>'

                t_title = f"👤 Send to {t_plain}"

                m_content = (
                    f"🎁 <b>A secret whisper has been sent to</b> {t_disp}!\n"
                    f"<i>Only</i> {t_disp} <i>or the sender can open this whisper.</i>"
                )
                k_board = InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔐 Show Secret Whisper 🤫", callback_data=f"ws_{w_id}")]
                ])
                results.append(
                    InlineQueryResultArticle(
                        id=w_id,
                        title=t_title,
                        description=f"Secret: {secret_text[:30]}...",
                        input_message_content=InputTextMessageContent(m_content, parse_mode="HTML"),
                        reply_markup=k_board
                    )
                )

            # Always include option for Anyone as well
            anyone_id = uuid.uuid4().hex[:10]
            try:
                save_whisper(
                    whisper_id=anyone_id,
                    sender_id=sender.id,
                    sender_username=sender.username,
                    target_id=None,
                    target_username=None,
                    secret_text=secret_text
                )
            except Exception as e:
                logging.error(f"Error saving anyone whisper: {e}")

            anyone_content = (
                f"🎁 <b>A secret whisper has been sent to Anyone!</b>\n"
                f"<i>Only Anyone or the sender can open this whisper.</i>"
            )
            anyone_keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔐 Show Secret Whisper 🤫", callback_data=f"ws_{anyone_id}")]
            ])
            results.append(
                InlineQueryResultArticle(
                    id=anyone_id,
                    title="🌐 Send to Anyone",
                    description=f"Secret: {secret_text[:30]}...",
                    input_message_content=InputTextMessageContent(anyone_content, parse_mode="HTML"),
                    reply_markup=anyone_keyboard
                )
            )

        await update.inline_query.answer(results, cache_time=0, is_personal=True)
    except Exception as e:
        logging.error(f"Fatal error in inline_whisper_query: {e}", exc_info=True)
        try:
            whisper_id = uuid.uuid4().hex[:10]
            message_content = "🎁 <b>A secret whisper has been sent!</b>\n<i>Only the intended recipient or the sender can open this whisper.</i>"
            keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🔐 Show Secret Whisper 🤫", callback_data=f"ws_{whisper_id}")]])
            results = [InlineQueryResultArticle(
                id=whisper_id,
                title="🔒 Send Secret Whisper",
                description="Click to send secret whisper",
                input_message_content=InputTextMessageContent(message_content, parse_mode="HTML"),
                reply_markup=keyboard
            )]
            await update.inline_query.answer(results, cache_time=0, is_personal=True)
        except Exception:
            pass

async def handle_whisper_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    callback_data = query.data
    from_user = query.from_user
    upsert_user(from_user.id, from_user.username, from_user.first_name, from_user.last_name)

    if callback_data == "guide_info":
        guide_msg = (
            "📖 <b>Detailed Whisper Guide:</b>\n\n"
            "1️⃣ Go to any group or private chat.\n"
            "2️⃣ In the message typing field, start by typing your bot's handle:\n"
            "   <code>@yourbotusername Hello this is a secret! @friend_username</code>\n\n"
            "3️⃣ A box will pop up above your keyboard. Tap it to send the whisper card into the group!\n\n"
            "4️⃣ Only <b>@friend_username</b>, you, or the owner can click to open it!"
        )
        await query.answer()
        await query.message.reply_text(guide_msg, parse_mode="HTML")
        return

    if callback_data == "id_info":
        id_msg = (
            "🆔 <b>Targeting Users Without Username (User ID Method):</b>\n\n"
            "If the person does not have a Telegram `@username`, you can use their numeric <b>User ID</b> instead!\n\n"
            "<b>Format:</b>\n"
            "<code>@yourbotusername [secret message] [user_id]</code>\n\n"
            "<b>Example:</b>\n"
            "<code>@yourbotusername Meet me tonight! 123456789</code>\n\n"
            "<i>(You can get anyone's numeric User ID using user info bots like @userinfobot).</i>"
        )
        await query.answer()
        await query.message.reply_text(id_msg, parse_mode="HTML")
        return

    if not callback_data.startswith("ws_"):
        await query.answer()
        return

    whisper_id = callback_data[3:]
    whisper = get_whisper(whisper_id)

    if not whisper:
        await query.answer(text="❌ This secret whisper has expired or was not found.", show_alert=True)
        return

    from_user = query.from_user
    user_id = from_user.id
    user_username = (from_user.username or "").lower()

    # Permission check: Allowed if Sender, Target Username, Target ID, Anyone, or OWNER_ID
    is_sender = (user_id == whisper["sender_id"])
    is_owner = (OWNER_ID > 0 and user_id == OWNER_ID)
    is_target_id = (whisper["target_id"] is not None and user_id == whisper["target_id"])
    is_target_username = (
        whisper["target_username"] is not None and
        user_username == whisper["target_username"].lower()
    )
    is_anyone_target = (whisper["target_id"] is None and whisper["target_username"] is None)

    # Receiver definition: target user or non-sender viewer when target is Anyone
    is_receiver = is_target_id or is_target_username or (is_anyone_target and not is_sender)

    if is_sender or is_target_id or is_target_username or is_anyone_target or is_owner:
        role_label = ""
        if is_owner and not (is_sender or is_target_id or is_target_username or is_anyone_target):
            role_label = " 👑 [Owner View]"
        
        secret_text = whisper["secret_text"]
        await query.answer(text=f"🤫 Secret Whisper{role_label}:\n\n{secret_text}", show_alert=True)

        # If opened by receiver for the first time, mark as seen in database
        if is_receiver and not whisper.get("is_seen"):
            mark_whisper_seen(whisper_id)
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
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(InlineQueryHandler(inline_whisper_query))
    app.add_handler(CallbackQueryHandler(handle_whisper_callback))

    print("\n[BOT] Telegram Secret Whisper Bot is starting...")
    print(f"[BOT] Owner ID configured: {OWNER_ID if OWNER_ID > 0 else 'None'}")
    print("Press Ctrl+C to stop.\n")
    app.run_polling()

if __name__ == "__main__":
    main()
