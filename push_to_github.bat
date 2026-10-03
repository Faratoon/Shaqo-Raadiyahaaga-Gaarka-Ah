@echo off
title Push Shaqo Raadiyahaaga Gaarka Ah to GitHub
cd /d "%~dp0"
echo ================================================================
echo    Pushing Shaqo Raadiyahaaga Gaarka Ah to GitHub
echo ================================================================
echo.
echo Your GitHub username: Faratoon
echo.
echo Make sure you have created the repository on GitHub first:
echo 👉 https://github.com/new (Name: Shaqo-Raadiyahaaga-Gaarka-Ah)
echo.
set /p REPO_URL="Enter your GitHub Repo URL (or press Enter for https://github.com/Faratoon/Shaqo-Raadiyahaaga-Gaarka-Ah.git): "
if "%REPO_URL%"=="" set REPO_URL=https://github.com/Faratoon/Shaqo-Raadiyahaaga-Gaarka-Ah.git

echo.
echo Setting remote origin to: %REPO_URL%
git remote set-url origin %REPO_URL%

echo.
echo Pushing main branch to GitHub...
git push -u origin main

echo.
echo ================================================================
echo Done! Check your repo on GitHub.
echo ================================================================
pause
