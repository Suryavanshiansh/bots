@echo off
title Stop Bot
echo Stopping Python Telegram Bot...
taskkill /FI "WINDOWTITLE eq Crocodile Wordle Telegram Bot*" /F /T 2>nul
taskkill /IM python.exe /F 2>nul
echo Bot stopped!
pause
