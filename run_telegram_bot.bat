@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
title Shaqo Raadiyaha Dhalinyarada Soomaaliyeed - Telegram Bot
cd /d "%~dp0"
echo ================================================================
echo    Shaqo Raadiyaha Dhalinyarada Soomaaliyeed - Telegram Bot
echo    Starting bot polling for interactive careers & courses...
echo ================================================================
echo.
call .\venv_portal\Scripts\activate.bat
python telegram_career_bot.py
pause
