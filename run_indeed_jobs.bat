@echo off
title Curated Job Finder - Edmonton & Remote (Indeed, ZipRecruiter, Glassdoor)
cd /d "%~dp0"
echo ================================================================
echo    Daily 5-Job Application Assistant (No LinkedIn Login Needed)
echo    Platforms: Indeed Canada, ZipRecruiter, Glassdoor
echo    Target: Edmonton, AB and Remote
echo    Daily Limit: Exactly 5 Jobs Tailored with AI
echo ================================================================
echo.
call .\venv\Scripts\activate.bat
python auto_job_finder.py
pause
