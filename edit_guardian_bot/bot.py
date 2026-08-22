import logging
import os
import sys
import io
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
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ChatMember
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    TypeHandler,
    ContextTypes,
    filters
)

from database import (
    init_db,
    get_chat_settings,
    update_media_delay,
    update_delete_edited,
    update_sticker_mode,
    add_approved_edit_user,
    remove_approved_edit_user,
    is_user_edit_approved,
    add_approved_sticker_user,
    remove_approved_sticker_user,
    is_user_sticker_approved,
    get_approved_edit_users,
    get_approved_sticker_users,
    upsert_user,
    get_user_by_username,
    get_user_by_id
)

# Load environment variables
env_path = os.path.join(BASE_DIR, ".env")
if os.path.exists(env_path):
    load_dotenv(env_path)
else:
    load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))
UPDATE_CHANNEL_URL = os.getenv("UPDATE_CHANNEL_URL", "https://t.me/telegram")
SUPPORT_CHAT_URL = os.getenv("SUPPORT_CHAT_URL", "https://t.me/telegram")

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Initialize SQLite database
init_db()

# Lightweight HTTP Health Check Server
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Edit Guardian Bot is running!")

    def log_message(self, format, *args):
        return

def start_health_server():
    port = int(os.getenv("PORT", 8080))
    try:
        server = HTTPServer(("0.0.0.0", port), HealthHandler)
        logger.info(f"[HTTP] Health check server listening on port {port}")
        server.serve_forever()
    except Exception as e:
        logger.warning(f"[HTTP] Health server could not start on port {port}: {e}")

# Helper: Check if user is Group Admin or Owner
async def is_group_admin(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int) -> bool:
    if update.effective_chat.type == "private":
        return True
    try:
        member = await context.bot.get_chat_member(update.effective_chat.id, user_id)
        return member.status in [ChatMember.ADMINISTRATOR, ChatMember.OWNER]
    except Exception as e:
        logger.error(f"Error checking admin status: {e}")
        return False

# Helper: Parse target user from command (via reply, username, or user_id argument)
async def get_target_user_info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> tuple[Optional[int], str]:
    if update.message and update.message.reply_to_message:
        u = update.message.reply_to_message.from_user
        upsert_user(u.id, u.username, u.first_name, u.last_name)
        display = u.first_name or (f"@{u.username}" if u.username else str(u.id))
        return u.id, display

    if context.args and len(context.args) > 0:
        arg = context.args[0].strip()
        if arg.isdigit():
            uid = int(arg)
            db_u = get_user_by_id(uid)
            if db_u:
                display = db_u['first_name'] or (f"@{db_u['username']}" if db_u['username'] else str(uid))
            else:
                display = str(uid)
            return uid, display
        
        # Username specified (e.g. @Toxicityiskey or Toxicityiskey)
        clean_username = arg.lstrip('@')
        db_u = get_user_by_username(clean_username)
        if db_u:
            display = db_u['first_name'] or f"@{db_u['username']}"
            return db_u['user_id'], display
        
        return None, f"@{clean_username}"

    return None, ""

# Known explicit / adult sticker set keywords / emojis indicator check
EXPLICIT_STICKER_KEYWORDS = [
    "nsfw", "18+", "adult", "hentai", "naked", "sex", "erotic", "boobs", "dick", "pussy", "ecchi", "xxx", "lewd"
]

def is_sticker_explicit(sticker) -> bool:
    if not sticker:
        return False
    set_name = (sticker.set_name or "").lower()
    for kw in EXPLICIT_STICKER_KEYWORDS:
        if kw in set_name:
            return True
    return False

# --- COMMAND HANDLERS ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user:
        u = update.effective_user
        upsert_user(u.id, u.username, u.first_name, u.last_name)
    user = update.effective_user
    first_name = user.first_name if user else "Friend"
    bot_user = await context.bot.get_me()
    bot_username = bot_user.username or "EditGuardianBot"

    text = (
        f"Hello {first_name} 👋, I'm your **Edit Guardian Bot**, here to maintain "
        f"a secure environment for our discussions!\n\n"
        f"🛡️ **WHAT CAN THIS BOT DO?**\n"
        f"🚫 **Edited Message Deletion:** Auto-removes edited messages to maintain transparency.\n"
        f"🔞 **NSFW Sticker Protection:** Deletes 18+ NSFW adult stickers sent by unapproved users.\n"
        f"⏱️ **Media Auto-Delete:** Automatically removes photos, gifs, stickers after a set delay.\n\n"
        f"📖 **HOW TO USE THIS BOT:**\n"
        f"1️⃣ Click **Add Group** below to add me to your group.\n"
        f"2️⃣ Promote me to **Administrator** with **Delete Messages** permission.\n"
        f"3️⃣ I'll start protecting your group instantly!\n\n"
        f"⚙️ **COMMANDS & ADMIN CONTROLS:**\n"
        f"• `/set_delay <minutes>` — Change auto-delete timer for media/stickers.\n"
        f"• `/get_delay` — View current chat settings.\n"
        f"• `/edit_guard <on|off>` — Toggle edited message deletion.\n"
        f"• `/sticker_guard <nsfw_only|all|off>` — Set sticker filtering mode.\n"
        f"• `/auth_edit` — Authorize member to edit messages safely.\n"
        f"• `/unauth_edit` — Revoke edit authorization.\n"
        f"• `/auth_sticker` — Authorize member to send stickers/media.\n"
        f"• `/unauth_sticker` — Revoke sticker authorization.\n"
        f"• `/list_approved` — View authorized members list.\n\n"
        f"➡️ Click on **Add Group** below to add me and keep our group safe!"
    )

    keyboard = [
        [
            InlineKeyboardButton("Update 🚀", url=UPDATE_CHANNEL_URL),
            InlineKeyboardButton("Support 💬", url=SUPPORT_CHAT_URL)
        ],
        [
            InlineKeyboardButton("✨ Add Group", url=f"https://t.me/{bot_username}?startgroup=true")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        text=text,
        parse_mode="Markdown",
        reply_markup=reply_markup,
        disable_web_page_preview=True
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🛡️ **Edit Guardian Bot Commands & Features**\n\n"
        "**⚙️ Admin Settings Commands:**\n"
        "• `/set_delay <minutes>` - Set auto-delete delay for media/stickers (0 for instant deletion).\n"
        "• `/get_delay` - Check current auto-delete timer setting.\n"
        "• `/edit_guard <on|off>` - Enable or disable edited message deletion.\n"
        "• `/sticker_guard <nsfw_only|all|off>` - Choose sticker restriction mode.\n\n"
        "**🔐 Member Authentication Commands:**\n"
        "• `/auth_edit` (or `/auth_edit @username` / `/auth_edit <user_id>`) - Authorize member to edit messages without deletion.\n"
        "• `/unauth_edit` (or `/unauth_edit @username` / `/unauth_edit <user_id>`) - Revoke edit authorization for a member.\n"
        "• `/auth_sticker` (or `/auth_sticker @username` / `/auth_sticker <user_id>`) - Authorize member to send stickers & media.\n"
        "• `/unauth_sticker` (or `/unauth_sticker @username` / `/unauth_sticker <user_id>`) - Revoke sticker authorization for a member.\n"
        "• `/list_approved` - View all authorized group members.\n\n"
        "💡 *Note:* You can reply to a message or pass `@username` / `user_id` with any auth command!"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

async def set_delay_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == "private":
        await update.message.reply_text("⚠️ This command can only be used in group chats.")
        return

    if not await is_group_admin(update, context, update.effective_user.id):
        await update.message.reply_text("🚫 Only group administrators can use this command.")
        return

    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("⚠️ Usage: `/set_delay <minutes>` (e.g., `/set_delay 30` or `/set_delay 0` for instant deletion)", parse_mode="Markdown")
        return

    minutes = int(context.args[0])
    update_media_delay(update.effective_chat.id, minutes)
    await update.message.reply_text(f"✅ Auto-delete delay for media/stickers updated to **{minutes} minutes**.", parse_mode="Markdown")

async def get_delay_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == "private":
        await update.message.reply_text("⚠️ This command can only be used in group chats.")
        return

    settings = get_chat_settings(update.effective_chat.id)
    delay = settings["media_delay_minutes"]
    edit_status = "Enabled 🟢" if settings["delete_edited"] else "Disabled 🔴"
    sticker_mode = settings["sticker_mode"]

    await update.message.reply_text(
        f"⚙️ **Current Chat Guardian Settings:**\n\n"
        f"⏱️ **Media Delete Delay:** {delay} minutes\n"
        f"🚫 **Edit Guard Status:** {edit_status}\n"
        f"🏷️ **Sticker Guard Mode:** {sticker_mode}",
        parse_mode="Markdown"
    )

async def edit_guard_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == "private":
        await update.message.reply_text("⚠️ This command can only be used in group chats.")
        return

    if not await is_group_admin(update, context, update.effective_user.id):
        await update.message.reply_text("🚫 Only group administrators can use this command.")
        return

    if not context.args or context.args[0].lower() not in ["on", "off"]:
        await update.message.reply_text("⚠️ Usage: `/edit_guard on` or `/edit_guard off`", parse_mode="Markdown")
        return

    enabled = 1 if context.args[0].lower() == "on" else 0
    update_delete_edited(update.effective_chat.id, enabled)
    status_str = "Enabled 🟢 (Edited messages by unapproved users will be deleted)" if enabled else "Disabled 🔴"
    await update.message.reply_text(f"✅ Edit Guard protection is now **{status_str}**.", parse_mode="Markdown")

async def sticker_guard_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == "private":
        await update.message.reply_text("⚠️ This command can only be used in group chats.")
        return

    if not await is_group_admin(update, context, update.effective_user.id):
        await update.message.reply_text("🚫 Only group administrators can use this command.")
        return

    if not context.args or context.args[0].lower() not in ["nsfw_only", "all", "off"]:
        await update.message.reply_text(
            "⚠️ Usage: `/sticker_guard <nsfw_only|all|off>`\n\n"
            "• `nsfw_only`: Filters adult/NSFW stickers for unapproved users.\n"
            "• `all`: Restricts all stickers for unapproved users.\n"
            "• `off`: Disables sticker restrictions.",
            parse_mode="Markdown"
        )
        return

    mode = context.args[0].lower()
    update_sticker_mode(update.effective_chat.id, mode)
    await update.message.reply_text(f"✅ Sticker Guard mode set to **{mode}**.", parse_mode="Markdown")

async def auth_edit_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == "private":
        await update.message.reply_text("⚠️ This command can only be used in group chats.")
        return

    if not await is_group_admin(update, context, update.effective_user.id):
        await update.message.reply_text("🚫 Only group administrators can use this command.")
        return

    target_id, display_name = await get_target_user_info(update, context)
    if not target_id:
        if display_name and display_name.startswith("@"):
            await update.message.reply_text(f"⚠️ User {display_name} has not messaged in this chat yet. Please reply directly to their message to authorize them!", parse_mode="Markdown")
        else:
            await update.message.reply_text("⚠️ Usage: Reply to a user or pass username/user_id: `/auth_edit @username` or `/auth_edit <user_id>`", parse_mode="Markdown")
        return

    add_approved_edit_user(update.effective_chat.id, target_id)
    await update.message.reply_text(f"✅ User {display_name} is now authorized to edit messages without deletion.", parse_mode="Markdown")

async def unauth_edit_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == "private":
        await update.message.reply_text("⚠️ This command can only be used in group chats.")
        return

    if not await is_group_admin(update, context, update.effective_user.id):
        await update.message.reply_text("🚫 Only group administrators can use this command.")
        return

    target_id, display_name = await get_target_user_info(update, context)
    if not target_id:
        if display_name and display_name.startswith("@"):
            await update.message.reply_text(f"⚠️ User {display_name} has not messaged in this chat yet. Please reply directly to their message!", parse_mode="Markdown")
        else:
            await update.message.reply_text("⚠️ Usage: Reply to a user or pass username/user_id: `/unauth_edit @username` or `/unauth_edit <user_id>`", parse_mode="Markdown")
        return

    remove_approved_edit_user(update.effective_chat.id, target_id)
    await update.message.reply_text(f"🚫 Edit authorization revoked for User {display_name}.", parse_mode="Markdown")

async def auth_sticker_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == "private":
        await update.message.reply_text("⚠️ This command can only be used in group chats.")
        return

    if not await is_group_admin(update, context, update.effective_user.id):
        await update.message.reply_text("🚫 Only group administrators can use this command.")
        return

    target_id, display_name = await get_target_user_info(update, context)
    if not target_id:
        if display_name and display_name.startswith("@"):
            await update.message.reply_text(f"⚠️ User {display_name} has not messaged in this chat yet. Please reply directly to their message to authorize them!", parse_mode="Markdown")
        else:
            await update.message.reply_text("⚠️ Usage: Reply to a user or pass username/user_id: `/auth_sticker @username` or `/auth_sticker <user_id>`", parse_mode="Markdown")
        return

    add_approved_sticker_user(update.effective_chat.id, target_id)
    await update.message.reply_text(f"✅ User {display_name} is now authorized to send stickers & media.", parse_mode="Markdown")

async def unauth_sticker_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == "private":
        await update.message.reply_text("⚠️ This command can only be used in group chats.")
        return

    if not await is_group_admin(update, context, update.effective_user.id):
        await update.message.reply_text("🚫 Only group administrators can use this command.")
        return

    target_id, display_name = await get_target_user_info(update, context)
    if not target_id:
        if display_name and display_name.startswith("@"):
            await update.message.reply_text(f"⚠️ User {display_name} has not messaged in this chat yet. Please reply directly to their message!", parse_mode="Markdown")
        else:
            await update.message.reply_text("⚠️ Usage: Reply to a user or pass username/user_id: `/unauth_sticker @username` or `/unauth_sticker <user_id>`", parse_mode="Markdown")
        return

    remove_approved_sticker_user(update.effective_chat.id, target_id)
    await update.message.reply_text(f"🚫 Sticker authorization revoked for User {display_name}.", parse_mode="Markdown")

async def list_approved_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == "private":
        await update.message.reply_text("⚠️ This command can only be used in group chats.")
        return

    chat_id = update.effective_chat.id
    edit_users = get_approved_edit_users(chat_id)
    sticker_users = get_approved_sticker_users(chat_id)

    def format_user_entry(uid: int) -> str:
        db_u = get_user_by_id(uid)
        if db_u:
            name = db_u['first_name'] or "User"
            uname = f" (@{db_u['username']})" if db_u['username'] else ""
            return f"• {name}{uname} (`{uid}`)"
        return f"• User `{uid}`"

    edit_list = "\n".join([format_user_entry(uid) for uid in edit_users]) if edit_users else "None"
    sticker_list = "\n".join([format_user_entry(uid) for uid in sticker_users]) if sticker_users else "None"

    await update.message.reply_text(
        f"📋 **Authorized Members in this Chat:**\n\n"
        f"✏️ **Approved Edit Users:**\n{edit_list}\n\n"
        f"🖼️ **Approved Sticker/Media Users:**\n{sticker_list}",
        parse_mode="Markdown"
    )

# --- JOB QUEUE AUTO-DELETE TASK ---

async def delete_notice_job(context: ContextTypes.DEFAULT_TYPE):
    job_data = context.job.data
    chat_id = job_data["chat_id"]
    message_id = job_data["message_id"]
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception:
        pass

async def send_deletion_notice(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user, reason: str, auto_delete_sec: int = 10):
    try:
        bot_user = await context.bot.get_me()
        bot_name = bot_user.first_name or "Edit Guardian Bot"
        username = f"@{user.username}" if (user and user.username) else (user.first_name if user else "User")
        
        notice_text = (
            f"🛡️ **{bot_name}** deleted a message from **{username}**\n"
            f"📌 **Reason:** {reason}"
        )
        notice_msg = await context.bot.send_message(chat_id=chat_id, text=notice_text, parse_mode="Markdown")
        
        if auto_delete_sec > 0 and context.job_queue:
            context.job_queue.run_once(
                delete_notice_job,
                auto_delete_sec,
                data={"chat_id": chat_id, "message_id": notice_msg.message_id}
            )
    except Exception as e:
        logger.warning(f"Could not send deletion notice in chat {chat_id}: {e}")

async def delete_media_job(context: ContextTypes.DEFAULT_TYPE):
    job_data = context.job.data
    chat_id = job_data["chat_id"]
    message_id = job_data["message_id"]
    username = job_data.get("username", "User")
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
        logger.info(f"Auto-deleted scheduled media message {message_id} in chat {chat_id}")
        
        bot_user = await context.bot.get_me()
        bot_name = bot_user.first_name or "Edit Guardian Bot"
        notice_text = (
            f"🛡️ **{bot_name}** deleted a message from **{username}**\n"
            f"📌 **Reason:** Media auto-delete timer expired"
        )
        notice_msg = await context.bot.send_message(chat_id=chat_id, text=notice_text, parse_mode="Markdown")
        if context.job_queue:
            context.job_queue.run_once(
                delete_notice_job,
                10,
                data={"chat_id": chat_id, "message_id": notice_msg.message_id}
            )
    except Exception as e:
        logger.warning(f"Could not delete message {message_id} in chat {chat_id}: {e}")

# --- UPDATE EVENT HANDLERS ---

async def handle_edited_message_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.edited_message or update.edited_message.chat.type == "private":
        return

    chat_id = update.edited_message.chat.id
    user = update.edited_message.from_user
    user_id = user.id
    settings = get_chat_settings(chat_id)

    if not settings["delete_edited"]:
        return

    # Check if user is admin or explicitly authorized for edits
    if await is_group_admin(update, context, user_id) or is_user_edit_approved(chat_id, user_id):
        return

    # User is unapproved -> delete edited message & send notice
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=update.edited_message.message_id)
        logger.info(f"Deleted edited message {update.edited_message.message_id} from unapproved user {user_id} in chat {chat_id}")
        await send_deletion_notice(
            context,
            chat_id,
            user,
            "Edited message deletion condition (unapproved member)"
        )
    except Exception as e:
        logger.error(f"Failed to delete edited message in chat {chat_id}: {e}")

async def handle_media_and_stickers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or update.message.chat.type == "private":
        return

    chat_id = update.message.chat.id
    user = update.message.from_user
    user_id = user.id
    msg = update.message
    settings = get_chat_settings(chat_id)

    # Check if user is admin or authorized for stickers/media
    if await is_group_admin(update, context, user_id) or is_user_sticker_approved(chat_id, user_id):
        return

    # User is unapproved -> Check sticker rules & media rules
    sticker_mode = settings["sticker_mode"]
    
    if msg.sticker:
        if sticker_mode == "all":
            try:
                await msg.delete()
                logger.info(f"Deleted sticker from unapproved user {user_id} in chat {chat_id}")
                await send_deletion_notice(context, chat_id, user, "Sticker restriction condition (unapproved member)")
                return
            except Exception as e:
                logger.error(f"Failed to delete sticker in chat {chat_id}: {e}")
                return
        elif sticker_mode == "nsfw_only" and is_sticker_explicit(msg.sticker):
            try:
                await msg.delete()
                logger.info(f"Deleted NSFW sticker from unapproved user {user_id} in chat {chat_id}")
                await send_deletion_notice(context, chat_id, user, "18+ NSFW sticker condition (unapproved member)")
                return
            except Exception as e:
                logger.error(f"Failed to delete NSFW sticker in chat {chat_id}: {e}")
                return

    # Handle general media auto-deletion (photo, video, animation/gif, document, audio, voice)
    is_media = bool(msg.photo or msg.video or msg.animation or msg.document or msg.audio or msg.voice or msg.sticker)
    if is_media:
        delay_minutes = settings["media_delay_minutes"]
        username = f"@{user.username}" if (user and user.username) else (user.first_name if user else "User")
        if delay_minutes == 0:
            try:
                await msg.delete()
                logger.info(f"Instantly deleted media from unapproved user {user_id} in chat {chat_id}")
                await send_deletion_notice(context, chat_id, user, "Media auto-delete condition (instant deletion)")
            except Exception as e:
                logger.error(f"Failed instant media deletion in chat {chat_id}: {e}")
        elif delay_minutes > 0 and context.job_queue:
            delay_seconds = delay_minutes * 60
            context.job_queue.run_once(
                delete_media_job,
                delay_seconds,
                data={"chat_id": chat_id, "message_id": msg.message_id, "username": username}
            )

# Main Application Entrypoint
def main():
    if not BOT_TOKEN or BOT_TOKEN == "YOUR_TELEGRAM_BOT_TOKEN_HERE":
        print("❌ Error: TELEGRAM_BOT_TOKEN is not set in .env file.")
        sys.exit(1)

    # Start optional background HTTP health check server for Render/Railway
    threading.Thread(target=start_health_server, daemon=True).start()

    # Build python-telegram-bot application with JobQueue
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Register Command Handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("set_delay", set_delay_command))
    app.add_handler(CommandHandler("get_delay", get_delay_command))
    app.add_handler(CommandHandler("edit_guard", edit_guard_command))
    app.add_handler(CommandHandler("sticker_guard", sticker_guard_command))
    app.add_handler(CommandHandler("auth_edit", auth_edit_command))
    app.add_handler(CommandHandler("unauth_edit", unauth_edit_command))
    app.add_handler(CommandHandler("auth_sticker", auth_sticker_command))
    app.add_handler(CommandHandler("unauth_sticker", unauth_sticker_command))
    app.add_handler(CommandHandler("list_approved", list_approved_command))

    # Register Edited Message Listener (Group 1)
    app.add_handler(TypeHandler(Update, handle_edited_message_update), group=1)

    # Register Media & Sticker Listener (Group 2)
    media_filter = (
        filters.PHOTO | filters.VIDEO | filters.ANIMATION | 
        filters.ATTACHMENT | filters.Sticker.ALL | filters.AUDIO | filters.VOICE
    )
    app.add_handler(MessageHandler(filters.ChatType.GROUPS & media_filter, handle_media_and_stickers), group=2)

    print("🚀 Edit Guardian Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
