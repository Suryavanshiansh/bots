@echo off
title Augram Word Grid Userbot
color 0A
echo.
echo  ============================================
echo   AUGRAM WORD GRID USERBOT - HARD MODE AUTO
echo  ============================================
echo.

cd /d "%~dp0"

:: Check .env exists
if not exist ".env" (
    echo  [!] .env file not found!
    echo      Copy .env.example to .env and fill in your details.
    echo.
    pause
    exit /b 1
)

:: Install dependencies if needed
pip show telethon >nul 2>&1
if errorlevel 1 (
    echo  [*] Installing dependencies...
    pip install -r requirements.txt
    echo.
)

echo  [*] Starting userbot...
echo  [*] Press Ctrl+C to stop.
echo.

python userbot.py
pause
