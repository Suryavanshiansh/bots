# 🤖 Telegram Bots Repository

A central repository containing multiple specialized Telegram bots:

---

## 📁 Bots Collection

### 1. 🐊 `word_guess/` (Crocodile Game & Wordle Solver Bot)
- **Tech Stack**: Python (`python-telegram-bot`)
- **Description**: Parses color block feedback (`🟩`, `🟨`, `🟥`) and 5-letter guessed words from Crocodile Game EN or Wordle messages, filtering ~15,000 words to output exact valid target words.
- **Run Locally**: `cd word_guess && python bot.py`

---

### 2. 🔠 `word-solver-bot/` (Word Search Grid Matrix Solver Bot)
- **Tech Stack**: Node.js (`telegraf`, `@google/generative-ai`)
- **Description**: Accepts photo grid images of 10x10 word search puzzles, uses Gemini AI vision to extract letters, and solves word search clue patterns (like `B--- (4)`).
- **Run Locally**: `cd word-solver-bot && npm start`

---

### 3. 🤫 `whisper_bot/` (Secret Whisper Bot)
- **Tech Stack**: Python (`python-telegram-bot`, `sqlite3`)
- **Description**: Allows sending secret "whisper" messages in any Telegram group or chat (`@bot [secret] @user` or `[user_id]`). Hidden behind a button and can ONLY be opened by the target recipient, sender, or Owner (`OWNER_ID`).
- **Run Locally**: `cd whisper_bot && python bot.py`

### 4. 🎵 `music_bot/` (Telegram Voice Chat Music & Video Bot)
- **Tech Stack**: Python (`pyrogram`, `pytgcalls`, `yt-dlp`, `aiosqlite`)
- **Description**: Feature-packed Telegram voice chat music & video bot supporting audio (`/play`) and video (`/vplay`), track queues, controls (`/pause`, `/resume`, `/skip`, `/end`, `/loop`, `/seek`, `/seekback`), and group authorization (`/auth`, `/unauth`, `/reboot`).
- **Run Locally**: `cd music_bot && python bot.py`

---

## 🔐 Environment Variables

Ensure `.env` files are kept private and never committed to GitHub.

- **`word_guess/.env`**:
  ```env
  TELEGRAM_BOT_TOKEN=your_bot_token_here
  ```
- **`word-solver-bot/.env`**:
  ```env
  TELEGRAM_BOT_TOKEN=your_bot_token_here
  GEMINI_API_KEY=your_gemini_api_key_here
  ```
- **`whisper_bot/.env`**:
  ```env
  TELEGRAM_BOT_TOKEN=your_bot_token_here
  ```
- **`music_bot/.env`**:
  ```env
  API_ID=12345678
  API_HASH=your_api_hash_here
  BOT_TOKEN=your_bot_token_here
  STRING_SESSION=your_pyrogram_string_session_here
  OWNER_ID=your_telegram_id_here
  ```

---

## ☁️ Deploying Subfolder Bots on Render / Railway

When deploying a specific bot from a multi-bot GitHub repository on Render:
1. Set **Root Directory** in Render settings:
   - For Wordle Bot: `word_guess`
   - For Word Search Bot: `word-solver-bot`
   - For Whisper Bot: `whisper_bot`
   - For Music Bot: `music_bot`
2. Set Build & Start commands for that bot:
   - Build: `pip install -r requirements.txt` (or `npm install`)
   - Start: `python bot.py` (or `node index.js`)

