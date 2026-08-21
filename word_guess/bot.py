import logging
import os
import sys

# Ensure the folder containing this file is in sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

try:
    from solver import WordleSolver
except ImportError:
    from word_guess.solver import WordleSolver

# Load environment variables (.env in BASE_DIR or current working dir)
env_path = os.path.join(BASE_DIR, ".env")
if os.path.exists(env_path):
    load_dotenv(env_path)
else:
    load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Initialize solver with default paths (auto-located relative to BASE_DIR)
solver = WordleSolver()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = (
        "🐊 <b>Welcome to Crocodile / Wordle Solver Bot!</b> 🎯\n\n"
        "Simply <b>forward</b> or <b>copy & paste</b> any message from Crocodile Game EN / Wordle containing color blocks and guessed words!\n\n"
        "<b>Color Guide:</b>\n"
        "🟩 / 🟢 Green: Correct letter & position\n"
        "🟨 / 🟡 Yellow: Correct letter, wrong position\n"
        "🟥 / 🔴 Red/Black: Letter not in word\n\n"
        "<b>Example:</b>\n"
        "Forward a message like this:\n"
        "<code>🟩🟩🟥🟥🟥 MANGO</code>\n"
        "<code>🟨🟥🟨🟥🟥 ADIEU</code>\n"
        "<code>🟩🟩🟨🟥🟥 MAIZE</code>\n\n"
        "I will immediately find the right valid target words for you! 💡"
    )
    await update.message.reply_text(welcome_text, parse_mode="HTML")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "📖 <b>How to use Crocodile Wordle Solver:</b>\n\n"
        "1️⃣ <b>Forwarding:</b> Forward any game update message directly from Crocodile Game EN to this chat.\n"
        "2️⃣ <b>Pasting:</b> Copy-paste lines with colored blocks (🟩🟨🟥) and words.\n"
        "3️⃣ <b>Manual Command:</b> Use <code>/solve [WORD] [COLORS]</code>\n"
        "   Example: <code>/solve MANGO 🟩🟩🟥🟥🟥 ADIEU 🟨🟥🟨🟥🟥</code>\n\n"
        "The bot will calculate all position constraints and return only valid 5-letter target words!"
    )
    await update.message.reply_text(help_text, parse_mode="HTML")

async def solve_manual(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = " ".join(context.args)
    if not text:
        await update.message.reply_text(
            "Please provide word & colors, e.g.:\n<code>/solve MANGO 🟩🟩🟥🟥🟥 ADIEU 🟨🟥🟨🟥🟥</code>",
            parse_mode="HTML"
        )
        return
    await process_game_text(update, text)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    text = update.message.text
    await process_game_text(update, text)

async def process_game_text(update: Update, text: str):
    attempts = solver.parse_message(text)
    
    if not attempts:
        await update.message.reply_text(
            "❌ No valid guess lines detected.\n"
            "Make sure to forward a message containing colored blocks (🟩🟨🟥) and 5-letter words!\n\n"
            "Send /help to see examples.",
            parse_mode="HTML"
        )
        return

    # Solve constraints
    common_matches, rare_matches = solver.solve(attempts)
    
    # Format response
    parsed_summary = "\n".join([f"• <code>{''.join(cols)} {w.upper()}</code>" for cols, w in attempts])
    
    reply = f"🔍 <b>Parsed Guesses:</b>\n{parsed_summary}\n\n"
    
    total_matches = len(common_matches) + len(rare_matches)

    if total_matches == 0:
        reply += "❌ <b>No matching 5-letter words found!</b> Check if any letter or color block was typed incorrectly."
    elif len(common_matches) == 1 and len(rare_matches) == 0:
        reply += f"🎉 <b>Target Word Found:</b>\n👉 <code><b>{common_matches[0].upper()}</b></code>"
    else:
        if common_matches:
            top_common = [f"<code>{w.upper()}</code>" for w in common_matches[:25]]
            reply += f"✅ <b>Valid Target Words ({len(common_matches)}):</b>\n"
            reply += " ".join(top_common)
            if len(common_matches) > 25:
                reply += f"\n\n<i>...and {len(common_matches) - 25} more.</i>"
            
            reply += f"\n\n💡 <b>Recommended Best Guess:</b> <code><b>{common_matches[0].upper()}</b></code>"

        if rare_matches:
            if not common_matches:
                top_rare = [f"<code>{w.upper()}</code>" for w in rare_matches[:25]]
                reply += f"⚠️ <b>Other Possible Words ({len(rare_matches)}):</b>\n"
                reply += " ".join(top_rare)
                reply += f"\n\n💡 <b>Recommended Best Guess:</b> <code><b>{rare_matches[0].upper()}</b></code>"
            else:
                reply += f"\n\n🔹 <i>({len(rare_matches)} uncommon/rare dictionary words omitted)</i>"

    await update.message.reply_text(reply, parse_mode="HTML")

def main():
    if not BOT_TOKEN or BOT_TOKEN == "YOUR_TELEGRAM_BOT_TOKEN_HERE":
        print("\n=======================================================")
        print("❌ ERROR: TELEGRAM_BOT_TOKEN is missing in .env file!")
        print(f"Please edit {os.path.join(BASE_DIR, '.env')} and paste your bot token from @BotFather")
        print("=======================================================\n")
        return

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("solve", solve_manual))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    
    print("\n🤖 Telegram Wordle / Crocodile Game Solver Bot is starting...")
    print("Press Ctrl+C to stop.\n")
    app.run_polling()

if __name__ == "__main__":
    main()
