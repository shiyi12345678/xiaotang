@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

rem ==========================================================================
rem  网易云课堂 - 后端服务一键启动脚本
rem
rem  作用：激活 server\.venv 虚拟环境，用 uvicorn 启动 FastAPI 服务
rem  用法：双击本文件即可；窗口必须保持打开，关闭窗口等于停止服务
rem
rem  ⚠️ 为什么需要这个脚本：
rem     uvicorn 是常驻进程，必须在固定终端窗口长期运行。
rem     若服务没启动，前端 AI 助手会「不回答」——因为 WebSocket 连不上。
rem ==========================================================================

rem 切到脚本所在目录（server\），保证 .env 与 .venv 路径可被正确解析
cd /d "%~dp0"

echo ==========================================================
echo   网易云课堂 后端服务启动器
echo ==========================================================
echo.

rem ---------- 前置检查 1：虚拟环境 ----------
if not exist ".venv\Scripts\python.exe" (
    echo [错误] 未找到虚拟环境：.venv\Scripts\python.exe
    echo        请先在 server 目录执行：python -m venv .venv
    echo        然后执行：.venv\Scripts\pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)

rem ---------- 前置检查 2：配置文件 ----------
rem .env 里有数据库密码与 AI 密钥，缺失则服务无法工作
if not exist ".env" (
    echo [错误] 未找到配置文件 .env
    echo        服务需要它读取数据库连接与 AI 密钥，无法启动。
    echo.
    pause
    exit /b 1
)

rem ---------- 自动探测本机局域网 IP ----------
rem 手机真机调试时需要用局域网 IP 访问电脑，IP 可能被路由器重新分配，故动态获取
rem 探测逻辑放在同目录的 print_lan_ip.py 中：
rem   比在 .bat 里嵌套 PowerShell 稳定得多（后者需要 ^| ^> 等多层转义，易静默失败）
set "LANIP="
for /f "delims=" %%i in ('.venv\Scripts\python.exe print_lan_ip.py') do set "LANIP=%%i"
if "!LANIP!"=="" set "LANIP=127.0.0.1"

echo   本机访问    http://127.0.0.1:8000
echo   局域网访问  http://!LANIP!:8000
echo   接口文档    http://127.0.0.1:8000/docs
echo.
echo   若前端 common\config.js 里的 IP 与此处不一致，请改成上面的局域网地址
echo.
echo   提示：本窗口不要关闭，关闭即停止服务。按 Ctrl+C 可主动停止。
echo ----------------------------------------------------------
echo.

rem ---------- 启动服务 ----------
rem --host 0.0.0.0  允许局域网/真机访问（只写 127.0.0.1 则手机连不上）
rem --reload        监听代码变化自动重启，方便开发（生产环境请去掉）
.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

echo.
echo ----------------------------------------------------------
echo   [服务已退出] 若上方出现 Traceback 报错，请截图排查
echo ----------------------------------------------------------
pause
