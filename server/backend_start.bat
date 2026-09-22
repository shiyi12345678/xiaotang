@echo off
rem ==========================================================================
rem  NetEase Cloud Classroom - silent backend starter (for logon auto-start)
rem
rem  Called by backend_launch.vbs so the backend runs with no console window.
rem  For live logs while debugging, use start_server.bat instead.
rem
rem  Features:
rem    1. Idempotent - exits if port 8000 is already listening (never fights
rem       for the port with start_server.bat or a manual run)
rem    2. Logs to logs\backend.log (archived to backend.old.log past 5MB)
rem    3. Runs hidden (the vbs invokes it with window style 0)
rem
rem  NOTE: --reload is intentionally NOT used. With --reload uvicorn becomes a
rem        parent + child pair, and backend_stop.bat (which kills whatever PID
rem        owns port 8000) would only kill the child - the parent would respawn
rem        it, so the service could not be stopped. After editing backend code,
rem        run backend_stop.bat and then start it again.
rem
rem  Stop: backend_stop.bat      View log: backend_log.bat
rem
rem  !! KEEP THIS FILE PURE ASCII !!
rem  cmd.exe tracks its position in a .bat file by BYTE OFFSET, but re-decodes
rem  lines using the current code page. Non-ASCII (Chinese) bytes therefore
rem  desynchronise the parser and fragments of comments get executed as
rem  commands, silently breaking the whole script. Same rule for the .vbs.
rem ==========================================================================
setlocal
cd /d "%~dp0"

if not exist "logs" mkdir "logs"

rem ---------- idempotency: skip when something already listens on 8000 ----------
netstat -ano | findstr /r /c:":8000 .*LISTENING" >nul 2>&1
if not errorlevel 1 (
    echo [%date% %time%] backend already running, skip. >> "logs\backend.log"
    exit /b 0
)

rem ---------- preflight checks ----------
if not exist ".venv\Scripts\python.exe" (
    echo [%date% %time%] [ERROR] .venv\Scripts\python.exe not found >> "logs\backend.log"
    exit /b 1
)
if not exist ".env" (
    echo [%date% %time%] [ERROR] .env not found >> "logs\backend.log"
    exit /b 1
)

rem ---------- log rotation at 5 MB ----------
if exist "logs\backend.log" (
    for %%F in ("logs\backend.log") do if %%~zF GTR 5242880 (
        move /y "logs\backend.log" "logs\backend.old.log" >nul 2>&1
    )
)

rem ---------- start (blocks until the process exits) ----------
echo. >> "logs\backend.log"
echo ============================================================ >> "logs\backend.log"
echo [%date% %time%] starting backend host=0.0.0.0 port=8000 (silent mode) >> "logs\backend.log"
echo ============================================================ >> "logs\backend.log"

".venv\Scripts\python.exe" -m uvicorn app.main:app --host 0.0.0.0 --port 8000 >> "logs\backend.log" 2>&1

echo [%date% %time%] backend exited, code %errorlevel% >> "logs\backend.log"
exit /b 0
