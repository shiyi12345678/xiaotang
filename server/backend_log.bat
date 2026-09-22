@echo off
rem ==========================================================================
rem  NetEase Cloud Classroom - view the backend log
rem
rem  When the backend auto-starts in silent mode there is no console window,
rem  so everything is written to:
rem      server\logs\backend.log      current log
rem      server\logs\backend.old.log  previous one (rotated past 5MB)
rem
rem  For live logs while editing code, use start_server.bat instead.
rem
rem  !! KEEP THIS FILE PURE ASCII !!  (see backend_start.bat for the reason)
rem ==========================================================================
cd /d "%~dp0"

if not exist "logs\backend.log" (
    echo.
    echo No log file yet - the backend has never been started in silent mode.
    echo To watch live logs right now, run start_server.bat instead.
    echo.
    pause
    exit /b 0
)

start "" notepad "logs\backend.log"
exit /b 0
