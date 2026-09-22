@echo off
rem ==========================================================================
rem  NetEase Cloud Classroom - stop the backend
rem
rem  Works by finding whichever PID owns port 8000 and killing that one.
rem  Safer than killing every python.exe - it will not touch your other
rem  Python programs.
rem
rem  NOTE: if the backend was started by start_server.bat (which uses
rem        --reload), press Ctrl+C in that window instead: that run has a
rem        parent + child pair and this script can only kill the child.
rem
rem  !! KEEP THIS FILE PURE ASCII !!  (see backend_start.bat for the reason)
rem ==========================================================================
setlocal enabledelayedexpansion

set "TARGET_PID="
for /f "tokens=5" %%p in ('netstat -ano ^| findstr /r /c:":8000 .*LISTENING"') do set "TARGET_PID=%%p"

if not defined TARGET_PID (
    echo.
    echo Backend is not running ^(nothing is listening on port 8000^).
    echo.
    pause
    exit /b 0
)

echo.
echo Stopping backend process PID=!TARGET_PID! ...
taskkill /pid !TARGET_PID! /f

if errorlevel 1 (
    echo.
    echo [FAILED] Could not kill the process. Try running as Administrator.
) else (
    echo.
    echo [OK] Backend stopped.
)
echo.
pause
exit /b 0
