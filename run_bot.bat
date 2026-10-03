@echo off
title AIHawk - Auto Job Applier (5 Applications Daily Limit)
cd /d "%~dp0"
echo ================================================================
echo    AIHawk LinkedIn Auto-Apply Bot
echo    Target: Edmonton / Remote / Canada
echo    Daily Application Limit: 5 Jobs Maximum
echo ================================================================
echo.
echo Activating Python 3.11 environment...
call .\venv\Scripts\activate.bat

echo.
echo Launching Job Applier...
python main.py --resume data_folder\output\Mohamed_Yasin_Mohamoud_Resume.pdf
pause
