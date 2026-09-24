@echo off
title OmniNovel - Local Novel to EPUB Server
setlocal enabledelayedexpansion

echo ===================================================
echo           Starting OmniNovel Local Server          
echo ===================================================
echo.

:: Change directory to where this script is located
cd /d "%~dp0"

:: Check if Python is available
where python >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Python was not found in your PATH!
    echo Please install Python 3.10+ and make sure it is added to your PATH.
    echo.
    pause
    exit /b 1
)

:: Install / check required dependencies
echo [1/3] Checking dependencies...
python -m pip install -q -r requirements.txt
if %ERRORLEVEL% neq 0 (
    echo [WARNING] Could not install all packages silently. Continuing...
)

echo [2/3] Launching web server on http://127.0.0.1:5000 ...
echo [3/3] Opening default web browser...

:: Open browser in background after 1.5 seconds delay
start "" cmd /c "timeout /t 2 /nobreak >nul & start http://127.0.0.1:5000"

echo.
echo ===================================================
echo  OmniNovel is running at http://127.0.0.1:5000
echo  Press Ctrl+C in this terminal window to stop.
echo ===================================================
echo.

:: Run the Flask application
python web_app.py

pause
