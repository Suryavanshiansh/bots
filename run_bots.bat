@echo off
title Local Bots Launcher
echo ===================================================
echo 🚀 Launching Local Telegram Bots
echo ===================================================

echo.
echo 1. Starting Secret Whisper Bot...
start "Secret Whisper Bot" cmd /k "cd /d f:\bots\whisper_bot && python bot.py"

echo.
echo 2. Starting Word Solver Bot...
start "Word Solver Bot" cmd /k "cd /d f:\bots\word-solver-bot && node index.js"

echo.
echo 3. Starting Augram Userbot...
if exist "f:\bots\augram-userbot\userbot.py" (
    start "Augram Userbot" cmd /k "cd /d f:\bots\augram-userbot && python userbot.py"
)

echo.
echo ===================================================
echo ✅ All bots launched in separate windows!
echo Keep the terminal windows open while running your bots.
echo ===================================================
pause
