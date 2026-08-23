import sys
import os
import logging
import asyncio
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes
)

from config import BOT_TOKEN
from database import init_db
from handlers.group_handlers import (
    cmd_game, cmd_extend, cmd_start, cmd_stop, cmd_status
)
from handlers.dm_handlers import (
    cmd_profile, cmd_roles_info, callback_menu_rules,
    callback_owner_role_option, callback_custom_role_select,
    callback_night_action, callback_day_vote, handle_dm_last_word
)
from handlers.admin_handlers import cmd_gamelog

# Setup logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Lightweight HTTP Health Check Server for Render 24/7 keeping
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"OK - Mafia Syndicate Bot is alive!")

def run_health_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    logger.info(f"Health check server running on port {port}")
    server.serve_forever()

async def post_init(application):
    """Initialize database tables before bot starts polling."""
    await init_db()
    logger.info("Database initialized successfully.")

def main():
    if not BOT_TOKEN or BOT_TOKEN == "YOUR_TELEGRAM_BOT_TOKEN_HERE":
        print("❌ Error: Please specify a valid BOT_TOKEN in your .env file!")
        sys.exit(1)

    # Start health check server in background thread for Render
    threading.Thread(target=run_health_server, daemon=True).start()

    app = ApplicationBuilder().token(BOT_TOKEN).post_init(post_init).build()

    # Command Handlers (Group & DM)
    app.add_handler(CommandHandler(["game", "game_bot"], cmd_game))
    app.add_handler(CommandHandler(["extend", "extend_bot"], cmd_extend))
    app.add_handler(CommandHandler(["start", "start_bot"], cmd_start))
    app.add_handler(CommandHandler(["stop", "stop_bot"], cmd_stop))
    app.add_handler(CommandHandler(["status", "status_bot"], cmd_status))
    app.add_handler(CommandHandler("profile", cmd_profile))
    app.add_handler(CommandHandler(["roles", "help"], cmd_roles_info))
    app.add_handler(CommandHandler("gamelog", cmd_gamelog))

    # Callback Query Handlers (Menu & Game Buttons)
    app.add_handler(CallbackQueryHandler(callback_menu_rules, pattern=r"^menu_rules$"))
    app.add_handler(CallbackQueryHandler(cmd_roles_info, pattern=r"^menu_roles$"))
    app.add_handler(CallbackQueryHandler(cmd_profile, pattern=r"^menu_profile$"))

    app.add_handler(CallbackQueryHandler(callback_owner_role_option, pattern=r"^roleopt_"))
    app.add_handler(CallbackQueryHandler(callback_custom_role_select, pattern=r"^customset_"))
    app.add_handler(CallbackQueryHandler(callback_night_action, pattern=r"^nact_"))
    app.add_handler(CallbackQueryHandler(callback_day_vote, pattern=r"^dvote_"))

    # DM Text Handler (Last Words)
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & filters.TEXT & (~filters.COMMAND), handle_dm_last_word))

    print("🚀 Mafia Syndicate Bot is running... Press Ctrl+C to stop.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
