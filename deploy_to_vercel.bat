@echo off
title Deploy Mohamed Job Portal to Vercel
cd /d "%~dp0"
echo ================================================================
echo    Deploying Mohamed Job Portal to Vercel (Live URL for Phone)
echo ================================================================
echo.
echo Checking Vercel CLI...
vercel --prod
pause
