# 🐊 Crocodile Game / Wordle Telegram Solver Bot

A fast, intelligent Telegram Bot that helps you solve 5-letter word games like **Crocodile Game EN** and **Wordle**.

Simply forward any game message (or paste the lines containing colored blocks `🟩` `🟨` `🟥` and guessed words), and the bot will filter the dictionary of ~15,000 5-letter words and present the top suitable target words and recommended next guess!

---

## 🚀 Setup Instructions

### 1. Get a Telegram Bot Token
1. Open Telegram and search for [@BotFather](https://t.me/BotFather).
2. Send the command `/newbot`.
3. Follow the prompts to name your bot and choose a username (e.g., `MyWordleSolverBot`).
4. Copy the API Token provided by BotFather (looks like `1234567890:ABCdefGhIJKlmNoPQRsTUVwxyZ`).

### 2. Configure `.env`
Open the `.env` file in the project folder and paste your token:
```env
TELEGRAM_BOT_TOKEN=1234567890:ABCdefGhIJKlmNoPQRsTUVwxyZ
```

### 3. Install Dependencies
Run in your terminal:
```bash
pip install -r requirements.txt
```

### 4. Start the Bot
Run:
```bash
python bot.py
```

---

## 🎮 How to Use the Bot

1. Open your Telegram Bot in Telegram and press **Start** (`/start`).
2. **Forward any forwarded message** from Crocodile Game EN or any Wordle group.
3. The bot will automatically analyze:
   - 🟩 **Green**: Correct letter in exact position
   - 🟨 **Yellow**: Letter exists in word, wrong position
   - 🟥 **Red / Black / White**: Letter not in word
4. The bot will reply with all matching 5-letter target words and the best recommended next guess!

---

## 📁 File Structure
- `bot.py` - Main Telegram bot listener and command handler.
- `solver.py` - Core Wordle constraint solver and parser.
- `dictionary.txt` - Complete English 5-letter dictionary (~15,000 words).
- `test_solver.py` - Test script for verifying solver logic.
- `.env` - Environment file storing your Telegram bot token.
