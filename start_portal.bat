@echo off
title Mohamed Yasin - Career & Job Portal (Localhost:5050)
cd /d "%~dp0"
echo ================================================================
echo    Mohamed Yasin Mohamoud - Localhost Job Portal UI
echo    Opening http://localhost:5050 in your browser...
echo ================================================================
echo.
call .\venv_portal\Scripts\activate.bat
python portal_app.py
pause
