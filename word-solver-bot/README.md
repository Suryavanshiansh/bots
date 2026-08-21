# 🔥 Telegram Word Search Challenge Solver Bot 🔥

A Node.js Telegram Bot that automatically solves **🔥 HARD MODE CHALLENGE 🔥** word search puzzles from image grid uploads and text clue list messages.

---

## ✨ Features

- 🖼️ **Image Grid Extraction (OCR)**: Uses Google Gemini Vision API to extract letter grids from uploaded or forwarded puzzle images.
- 🧩 **8-Directional Word Search**: Searches horizontally, vertically, and diagonally (forwards & backwards) across 370k+ English words.
- 📋 **Flexible Pattern Parsing**: Supports clue lists formatted like `B--- (4)`, `C----- (6)`, `S-------- (9)`, etc.
- 🔄 **Interactive Candidate Swapping**: If any word is wrong or not accepted by the game, simply reply with its number (e.g. `5` or `5 wrong`) to switch to another valid word match!
- 👥 **Multi-User Session Support**: Handles state per chat ID so multiple Telegram users/groups can solve puzzles at the same time.

---

## 🚀 Setup & Setup Instructions

### 1️⃣ Get API Credentials

1. **Telegram Bot Token**:
   - Open Telegram and search for [@BotFather](https://t.me/BotFather).
   - Send `/newbot` and follow the prompts to name your bot.
   - Copy the HTTP API Access Token.

2. **Google Gemini API Key**:
   - Visit [Google AI Studio](https://aistudio.google.com/).
   - Click **Get API Key** -> **Create API Key**.
   - Copy your key.

---

### 2️⃣ Configure Environment Variables

Create or edit `.env` in the `word-solver-bot` directory:

```env
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyZ
GEMINI_API_KEY=AIzaSyYourGeminiApiKeyHere
```

---

### 3️⃣ Start the Bot

Run the following command in your terminal:

```bash
cd e:/portfolio/word-solver-bot
npm start
```

You should see:
```
🚀 Loading dictionary...
Loaded 369652 words into dictionary.
🤖 Telegram bot is running!
```

---

## 📱 How to Use in Telegram

1. Open your Telegram bot.
2. Send or forward the **Grid Image** (or an image with the challenge message as caption).
3. Send or forward the **Word List Message** (e.g. `B--- (4)`, `G--- (4)`, etc.).
4. The bot will reply with all solved words, their grid coordinates (Row, Column), and search directions!
5. **If a word is wrong**: Reply to the bot message with `5` or `5 wrong` to try the next valid word!

---

## 🧪 Running Tests

To verify the solver logic offline without launching the Telegram bot:

```bash
npm test
```
