import logging
import os
import sys
import io
import threading
import time
import html
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
    get_user_by_id,
    get_bot_stats,
    get_all_chat_ids,
    set_user_afk,
    remove_user_afk,
    get_user_afk,
    get_afk_user_by_username
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

def keep_alive_heartbeat():
    url = os.getenv("RENDER_EXTERNAL_URL")
    if not url:
        return
    while True:
        time.sleep(300)  # Ping self every 5 minutes automatically
        try:
            urllib.request.urlopen(url, timeout=10)
        except Exception:
            pass

# Helper: Check if user is Group Admin or Bot Owner
async def is_group_admin(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int) -> bool:
    if OWNER_ID != 0 and user_id == OWNER_ID:
        return True
    if update.effective_chat.type == "private":
        return True
    try:
        member = await context.bot.get_chat_member(update.effective_chat.id, user_id)
        status_str = str(member.status).lower()
        return status_str in ["administrator", "creator", "owner"] or member.status in [ChatMember.ADMINISTRATOR, ChatMember.OWNER]
    except Exception as e:
        logger.error(f"Error checking admin status for user {user_id} in chat {update.effective_chat.id}: {e}")
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
    msg = update.effective_message
    if not msg or update.effective_chat.type == "private":
        if msg:
            await msg.reply_text("⚠️ This command can only be used in group chats.")
        return

    if not await is_group_admin(update, context, update.effective_user.id):
        await msg.reply_text("🚫 Only group administrators can use this command.")
        return

    if not context.args or not context.args[0].isdigit():
        await msg.reply_text("⚠️ Usage: <code>/set_delay &lt;minutes&gt;</code> (e.g., <code>/set_delay 30</code> or <code>/set_delay 0</code> for instant deletion)", parse_mode="HTML")
        return

    minutes = int(context.args[0])
    update_media_delay(update.effective_chat.id, minutes)
    await msg.reply_text(f"✅ Auto-delete delay for media/stickers updated to <b>{minutes} minutes</b>.", parse_mode="HTML")

async def get_delay_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if not msg or update.effective_chat.type == "private":
        if msg:
            await msg.reply_text("⚠️ This command can only be used in group chats.")
        return

    settings = get_chat_settings(update.effective_chat.id)
    delay = settings["media_delay_minutes"]
    edit_status = "Enabled 🟢" if settings["delete_edited"] else "Disabled 🔴"
    sticker_mode = settings["sticker_mode"]

    await msg.reply_text(
        f"⚙️ <b>Current Chat Guardian Settings:</b>\n\n"
        f"⏱️ <b>Media Delete Delay:</b> {delay} minutes\n"
        f"🚫 <b>Edit Guard Status:</b> {edit_status}\n"
        f"🏷️ <b>Sticker Guard Mode:</b> {sticker_mode}",
        parse_mode="HTML"
    )

async def edit_guard_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if not msg or update.effective_chat.type == "private":
        if msg:
            await msg.reply_text("⚠️ This command can only be used in group chats.")
        return

    if not await is_group_admin(update, context, update.effective_user.id):
        await msg.reply_text("🚫 Only group administrators can use this command.")
        return

    if not context.args:
        await msg.reply_text("⚠️ Usage: <code>/edit_guard on</code> or <code>/edit_guard off</code>", parse_mode="HTML")
        return

    arg = context.args[0].lower()
    if arg in ["on", "enable", "enabled", "1", "yes", "true"]:
        enabled = 1
    elif arg in ["off", "disable", "disabled", "0", "no", "false"]:
        enabled = 0
    else:
        await msg.reply_text("⚠️ Usage: <code>/edit_guard on</code> or <code>/edit_guard off</code>", parse_mode="HTML")
        return

    update_delete_edited(update.effective_chat.id, enabled)
    status_str = "Enabled 🟢 (Edited messages by unapproved users will be deleted)" if enabled else "Disabled 🔴"
    await msg.reply_text(f"✅ Edit Guard protection is now <b>{status_str}</b>.", parse_mode="HTML")

async def sticker_guard_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if not msg or update.effective_chat.type == "private":
        if msg:
            await msg.reply_text("⚠️ This command can only be used in group chats.")
        return

    if not await is_group_admin(update, context, update.effective_user.id):
        await msg.reply_text("🚫 Only group administrators can use this command.")
        return

    usage_msg = (
        "⚠️ Usage: <code>/sticker_guard &lt;nsfw_only|all|off&gt;</code>\n\n"
        "• <code>nsfw_only</code>: Filters adult/NSFW stickers for unapproved users.\n"
        "• <code>all</code>: Restricts all stickers for unapproved users.\n"
        "• <code>off</code>: Disables sticker restrictions."
    )

    if not context.args:
        await msg.reply_text(usage_msg, parse_mode="HTML")
        return

    arg = context.args[0].lower()
    if arg in ["nsfw_only", "nsfw", "18+", "18", "on"]:
        mode = "nsfw_only"
    elif arg in ["all", "every", "full"]:
        mode = "all"
    elif arg in ["off", "disable", "disabled", "none", "0"]:
        mode = "off"
    else:
        await msg.reply_text(usage_msg, parse_mode="HTML")
        return

    update_sticker_mode(update.effective_chat.id, mode)
    await msg.reply_text(f"✅ Sticker Guard mode set to <b>{mode}</b>.", parse_mode="HTML")

async def sticker_off_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if not msg or update.effective_chat.type == "private":
        if msg:
            await msg.reply_text("⚠️ This command can only be used in group chats.")
        return

    if not await is_group_admin(update, context, update.effective_user.id):
        await msg.reply_text("🚫 Only group administrators can use this command.")
        return

    update_sticker_mode(update.effective_chat.id, "off")
    await msg.reply_text("✅ Sticker Guard mode set to <b>off</b> (Sticker & NSFW restrictions disabled).", parse_mode="HTML")

async def sticker_on_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if not msg or update.effective_chat.type == "private":
        if msg:
            await msg.reply_text("⚠️ This command can only be used in group chats.")
        return

    if not await is_group_admin(update, context, update.effective_user.id):
        await msg.reply_text("🚫 Only group administrators can use this command.")
        return

    update_sticker_mode(update.effective_chat.id, "nsfw_only")
    await msg.reply_text("✅ Sticker Guard mode set to <b>nsfw_only</b> (18+ NSFW stickers will be deleted).", parse_mode="HTML")

async def auth_edit_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if not msg or update.effective_chat.type == "private":
        if msg:
            await msg.reply_text("⚠️ This command can only be used in group chats.")
        return

    if not await is_group_admin(update, context, update.effective_user.id):
        await msg.reply_text("🚫 Only group administrators can use this command.")
        return

    target_id, display_name = await get_target_user_info(update, context)
    if not target_id:
        if display_name and display_name.startswith("@"):
            clean_d = html.escape(display_name)
            await msg.reply_text(f"⚠️ User <b>{clean_d}</b> has not messaged in this chat yet. Please reply directly to their message to authorize them!", parse_mode="HTML")
        else:
            await msg.reply_text("⚠️ Usage: Reply to a user or pass username/user_id: <code>/auth_edit @username</code> or <code>/auth_edit &lt;user_id&gt;</code>", parse_mode="HTML")
        return

    if target_id == update.effective_user.id:
        await msg.reply_text("⚠️ You cannot authorize yourself! Another group administrator or the Bot Owner must authorize you.", parse_mode="HTML")
        return

    add_approved_edit_user(update.effective_chat.id, target_id)
    safe_name = html.escape(display_name)
    await msg.reply_text(f"✅ User <b>{safe_name}</b> is now authorized to edit messages without deletion.", parse_mode="HTML")

async def unauth_edit_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if not msg or update.effective_chat.type == "private":
        if msg:
            await msg.reply_text("⚠️ This command can only be used in group chats.")
        return

    if not await is_group_admin(update, context, update.effective_user.id):
        await msg.reply_text("🚫 Only group administrators can use this command.")
        return

    target_id, display_name = await get_target_user_info(update, context)
    if not target_id:
        if display_name and display_name.startswith("@"):
            clean_d = html.escape(display_name)
            await msg.reply_text(f"⚠️ User <b>{clean_d}</b> has not messaged in this chat yet. Please reply directly to their message!", parse_mode="HTML")
        else:
            await msg.reply_text("⚠️ Usage: Reply to a user or pass username/user_id: <code>/unauth_edit @username</code> or <code>/unauth_edit &lt;user_id&gt;</code>", parse_mode="HTML")
        return

    remove_approved_edit_user(update.effective_chat.id, target_id)
    safe_name = html.escape(display_name)
    await msg.reply_text(f"🚫 Edit authorization revoked for User <b>{safe_name}</b>.", parse_mode="HTML")

async def auth_sticker_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if not msg or update.effective_chat.type == "private":
        if msg:
            await msg.reply_text("⚠️ This command can only be used in group chats.")
        return

    if not await is_group_admin(update, context, update.effective_user.id):
        await msg.reply_text("🚫 Only group administrators can use this command.")
        return

    target_id, display_name = await get_target_user_info(update, context)
    if not target_id:
        if display_name and display_name.startswith("@"):
            clean_d = html.escape(display_name)
            await msg.reply_text(f"⚠️ User <b>{clean_d}</b> has not messaged in this chat yet. Please reply directly to their message to authorize them!", parse_mode="HTML")
        else:
            await msg.reply_text("⚠️ Usage: Reply to a user or pass username/user_id: <code>/auth_sticker @username</code> or <code>/auth_sticker &lt;user_id&gt;</code>", parse_mode="HTML")
        return

    if target_id == update.effective_user.id:
        await msg.reply_text("⚠️ You cannot authorize yourself! Another group administrator or the Bot Owner must authorize you.", parse_mode="HTML")
        return

    add_approved_sticker_user(update.effective_chat.id, target_id)
    safe_name = html.escape(display_name)
    await msg.reply_text(f"✅ User <b>{safe_name}</b> is now authorized to send stickers &amp; media.", parse_mode="HTML")


async def unauth_sticker_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if not msg or update.effective_chat.type == "private":
        if msg:
            await msg.reply_text("⚠️ This command can only be used in group chats.")
        return

    if not await is_group_admin(update, context, update.effective_user.id):
        await msg.reply_text("🚫 Only group administrators can use this command.")
        return

    target_id, display_name = await get_target_user_info(update, context)
    if not target_id:
        if display_name and display_name.startswith("@"):
            clean_d = html.escape(display_name)
            await msg.reply_text(f"⚠️ User <b>{clean_d}</b> has not messaged in this chat yet. Please reply directly to their message!", parse_mode="HTML")
        else:
            await msg.reply_text("⚠️ Usage: Reply to a user or pass username/user_id: <code>/unauth_sticker @username</code> or <code>/unauth_sticker &lt;user_id&gt;</code>", parse_mode="HTML")
        return

    remove_approved_sticker_user(update.effective_chat.id, target_id)
    safe_name = html.escape(display_name)
    await msg.reply_text(f"🚫 Sticker authorization revoked for User <b>{safe_name}</b>.", parse_mode="HTML")

async def list_approved_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if not msg or update.effective_chat.type == "private":
        if msg:
            await msg.reply_text("⚠️ This command can only be used in group chats.")
        return

    try:
        chat_id = update.effective_chat.id
        edit_users = get_approved_edit_users(chat_id)
        sticker_users = get_approved_sticker_users(chat_id)

        def format_user_entry(uid: int) -> str:
            try:
                db_u = get_user_by_id(uid)
                if db_u and isinstance(db_u, dict):
                    fname = db_u.get('first_name') or "User"
                    uname = db_u.get('username')
                    name = html.escape(str(fname))
                    uname_str = f" (@{html.escape(str(uname))})" if uname else ""
                    return f"• {name}{uname_str} (<code>{uid}</code>)"
            except Exception as e:
                logger.error(f"Error formatting user entry {uid}: {e}")
            return f"• User <code>{uid}</code>"

        edit_list = "\n".join([format_user_entry(uid) for uid in edit_users]) if edit_users else "None"
        sticker_list = "\n".join([format_user_entry(uid) for uid in sticker_users]) if sticker_users else "None"

        await msg.reply_text(
            f"📋 <b>Authorized Members in this Chat:</b>\n\n"
            f"✏️ <b>Approved Edit Users:</b>\n{edit_list}\n\n"
            f"🖼️ <b>Approved Sticker/Media Users:</b>\n{sticker_list}",
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Error in list_approved_command: {e}", exc_info=e)
        await msg.reply_text("⚠️ Unable to fetch approved members at this moment. Please try again.")


# --- AFK FEATURE LOGIC ---

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

    # Truncate reason if too long (max 200 chars)
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
        f"💤 <b>{safe_name}</b> is now AFK!\nReason: {reason_html}",
        parse_mode="HTML"
    )


from datetime import datetime, timezone

def parse_afk_time(afk_since_str: str) -> datetime:
    try:
        clean_str = str(afk_since_str).replace("Z", "+00:00")
        dt = datetime.fromisoformat(clean_str)
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt
    except Exception:
        return datetime.utcnow()

async def handle_afk_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    user = update.effective_user
    if not msg or not user:
        return

    # Upsert sender into cached users table
    try:
        upsert_user(user.id, user.username or "", user.first_name or "", user.last_name or "")
    except Exception as e:
        logger.error(f"Error upserting user in AFK handler: {e}")

    # 1. Check if sender was AFK (Welcome back!)
    # Skip if command starts with '/'
    if not (msg.text and msg.text.strip().startswith("/")):
        afk_info = remove_user_afk(user.id)
        if afk_info:
            try:
                afk_time = parse_afk_time(afk_info["afk_since"])
                elapsed = max(0.0, (datetime.utcnow() - afk_time).total_seconds())
                duration_str = format_afk_duration(elapsed)
                safe_name = html.escape(user.first_name or "User")
                await msg.reply_text(
                    f"👋 Welcome back <b>{safe_name}</b>! You were away for <b>{duration_str}</b>.",
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
                        f"💤 <b>{target_name}</b> is currently AFK! (Away for <b>{duration_str}</b>)\nReason: {reason_html}",
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



# --- BOT OWNER EXCLUSIVE COMMANDS ---


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if OWNER_ID != 0 and update.effective_user.id != OWNER_ID:
        return
    stats = get_bot_stats()
    msg = (
        "👑 **Edit Guardian Bot Owner Panel & Statistics**\n\n"
        f"👥 **Total Cached Users:** `{stats['cached_users']}`\n"
        f"💬 **Active Protected Chats:** `{stats['chats']}`\n"
        f"✏️ **Approved Edit Members:** `{stats['approved_edits']}`\n"
        f"🖼️ **Approved Sticker Members:** `{stats['approved_stickers']}`"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if OWNER_ID != 0 and update.effective_user.id != OWNER_ID:
        return
    if not context.args:
        await update.message.reply_text("⚠️ Usage: `/broadcast <your message>`", parse_mode="Markdown")
        return
    
    broadcast_text = " ".join(context.args)
    chat_ids = get_all_chat_ids()
    success = 0
    failed = 0
    
    for cid in chat_ids:
        try:
            await context.bot.send_message(
                chat_id=cid,
                text=f"📢 **Bot Owner Announcement:**\n\n{broadcast_text}",
                parse_mode="Markdown"
            )
            success += 1
        except Exception:
            failed += 1
            
    await update.message.reply_text(
        f"📢 **Broadcast Results:**\n\n"
        f"🟢 **Successfully Sent:** {success} chats\n"
        f"🔴 **Failed/Left:** {failed} chats",
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

async def send_deletion_notice(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user, reason_type: str = "edit", auto_delete_sec: int = 0):
    try:
        bot_user = await context.bot.get_me()
        bot_username = bot_user.username or "EditGuardianBot"
        
        # Always use User's First Name ONLY (No @username, No user ID)
        first_name = user.first_name if (user and user.first_name) else "USER"
        
        if reason_type == "edit":
            notice_text = f"***{first_name}*** **JUST EDIT A MESSAGE I DELETE IT 🤡.**"
        elif reason_type == "nsfw_sticker":
            notice_text = f"***{first_name}*** **SENT AN 18+ NSFW STICKER I DELETE IT 🤡.**"
        elif reason_type == "sticker_all":
            notice_text = f"***{first_name}*** **SENT A STICKER I DELETE IT 🤡.**"
        elif reason_type == "media_instant":
            notice_text = f"***{first_name}*** **SENT RESTRICTED MEDIA I DELETE IT 🤡.**"
        else:
            notice_text = f"***{first_name}*** **SENT RESTRICTED CONTENT I DELETE IT 🤡.**"

        keyboard = [
            [
                InlineKeyboardButton("ADD ME ↗️", url=f"https://t.me/{bot_username}?startgroup=true"),
                InlineKeyboardButton("SOLUTION ↗️", url=SUPPORT_CHAT_URL)
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await context.bot.send_message(
            chat_id=chat_id,
            text=notice_text,
            parse_mode="Markdown",
            reply_markup=reply_markup,
            disable_web_page_preview=True
        )
    except Exception as e:
        logger.warning(f"Could not send deletion notice in chat {chat_id}: {e}")

async def delete_media_job(context: ContextTypes.DEFAULT_TYPE):
    job_data = context.job.data
    chat_id = job_data["chat_id"]
    message_id = job_data["message_id"]
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
        logger.info(f"Auto-deleted scheduled media message {message_id} in chat {chat_id}")
    except Exception as e:
        logger.warning(f"Could not delete media message {message_id} in chat {chat_id}: {e}")

# --- UPDATE EVENT HANDLERS ---

async def handle_edited_message_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.edited_message or update.edited_message.chat.type == "private":
        return

    # Do NOT delete messages edited via inline bots (e.g., Whisper Bot / via_bot) or sent by bots
    if update.edited_message.via_bot or (update.edited_message.from_user and update.edited_message.from_user.is_bot):
        return

    chat_id = update.edited_message.chat.id
    user = update.edited_message.from_user
    user_id = user.id
    settings = get_chat_settings(chat_id)

    if not settings["delete_edited"]:
        return

    # Global Bot Owner Immunity Check
    if OWNER_ID != 0 and user_id == OWNER_ID:
        return

    # Check if user is explicitly authorized for edits (applies to both admins & regular members)
    if is_user_edit_approved(chat_id, user_id):
        return

    # User is unapproved -> delete edited message & send notice
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=update.edited_message.message_id)
        logger.info(f"Deleted edited message {update.edited_message.message_id} from unapproved user {user_id} in chat {chat_id}")
        await send_deletion_notice(
            context,
            chat_id,
            user,
            reason_type="edit"
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

    # Global Bot Owner Immunity Check
    if OWNER_ID != 0 and user_id == OWNER_ID:
        return

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
                return
            except Exception as e:
                logger.error(f"Failed to delete sticker in chat {chat_id}: {e}")
                return
        elif sticker_mode == "nsfw_only" and is_sticker_explicit(msg.sticker):
            try:
                await msg.delete()
                logger.info(f"Deleted NSFW sticker from unapproved user {user_id} in chat {chat_id}")
                return
            except Exception as e:
                logger.error(f"Failed to delete NSFW sticker in chat {chat_id}: {e}")
                return

    # Handle general media auto-deletion (photo, video, animation/gif, document, audio, voice)
    is_media = bool(msg.photo or msg.video or msg.animation or msg.document or msg.audio or msg.voice or msg.sticker)
    if is_media:
        delay_minutes = settings["media_delay_minutes"]
        first_name = user.first_name if (user and user.first_name) else "USER"
        if delay_minutes == 0:
            try:
                await msg.delete()
                logger.info(f"Instantly deleted media from unapproved user {user_id} in chat {chat_id}")
            except Exception as e:
                logger.error(f"Failed instant media deletion in chat {chat_id}: {e}")
        elif delay_minutes > 0 and context.job_queue:
            delay_seconds = delay_minutes * 60
            context.job_queue.run_once(
                delete_media_job,
                delay_seconds,
                data={"chat_id": chat_id, "message_id": msg.message_id, "first_name": first_name}
            )

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

    # Build python-telegram-bot application with JobQueue
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_error_handler(global_error_handler)

    # Register Command Handlers (with aliases)
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler(["set_delay", "setdelay", "set"], set_delay_command))
    app.add_handler(CommandHandler(["get_delay", "getdelay", "get"], get_delay_command))
    app.add_handler(CommandHandler(["edit_guard", "editguard", "edit"], edit_guard_command))
    app.add_handler(CommandHandler(["sticker_guard", "stickerguard", "sticker"], sticker_guard_command))
    app.add_handler(CommandHandler(["sticker_off", "stickeroff", "nsfw_off", "nsfwoff"], sticker_off_command))
    app.add_handler(CommandHandler(["sticker_on", "stickeron", "nsfw_on", "nsfwon"], sticker_on_command))
    app.add_handler(CommandHandler(["auth_edit", "authedit"], auth_edit_command))
    app.add_handler(CommandHandler(["unauth_edit", "unauthedit"], unauth_edit_command))
    app.add_handler(CommandHandler(["auth_sticker", "authsticker"], auth_sticker_command))
    app.add_handler(CommandHandler(["unauth_sticker", "unauthsticker"], unauth_sticker_command))
    app.add_handler(CommandHandler(["list_approved", "listapproved", "approved"], list_approved_command))
    app.add_handler(CommandHandler(["afk"], afk_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("broadcast", broadcast_command))

    # Register AFK Return & Mention Listener (Group 0 - runs first for all updates)
    app.add_handler(MessageHandler(~filters.StatusUpdate.ALL, handle_afk_messages), group=0)

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
