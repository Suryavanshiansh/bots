@echo off
title Local Bots Launcher - All Bots
echo ===================================================
echo 🚀 Launching All Local Telegram Bots
echo ===================================================

echo.
echo 1. Starting Secret Whisper Bot...
if exist "f:\bots\whisper_bot\bot.py" (
    start "Secret Whisper Bot" cmd /k "cd /d f:\bots\whisper_bot && python bot.py"
)

echo.
echo 2. Starting Word Solver Bot...
if exist "f:\bots\word-solver-bot\index.js" (
    start "Word Solver Bot" cmd /k "cd /d f:\bots\word-solver-bot && node index.js"
)

echo.
echo 3. Starting Augram Userbot...
if exist "f:\bots\augram-userbot\userbot.py" (
    start "Augram Userbot" cmd /k "cd /d f:\bots\augram-userbot && python userbot.py"
)

echo.
echo 4. Starting AFK Bot...
if exist "f:\bots\afk_bot\bot.py" (
    start "AFK Bot" cmd /k "cd /d f:\bots\afk_bot && python bot.py"
)

echo.
echo 5. Starting Edit Guardian Bot...
if exist "f:\bots\edit_guardian_bot\bot.py" (
    start "Edit Guardian Bot" cmd /k "cd /d f:\bots\edit_guardian_bot && python bot.py"
)

echo.
echo 6. Starting Word Guess Bot...
if exist "f:\bots\word_guess\bot.py" (
    start "Word Guess Bot" cmd /k "cd /d f:\bots\word_guess && python bot.py"
)

echo.
echo ===================================================
echo ✅ All 6 bots launched in separate windows!
echo Keep the terminal windows open while running your bots.
echo ===================================================
pause
