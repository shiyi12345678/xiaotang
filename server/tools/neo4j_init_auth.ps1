<#
.SYNOPSIS
    初始化本机 Neo4j 的认证存储（只需运行一次，之后 GraphRAG 才能连上图谱库）。

.DESCRIPTION
    背景：Neo4j 默认开启认证，但「初始密码」必须在首次使用前显式设置一次。
    没设过密码时，data\dbms\auth.ini 不存在，此时【任何账号都登不进去】，
    表现为连接时报 401 Unauthorized / "authentication failure"。

    本脚本做的事（顺序固定，中途失败会尽量把服务恢复起来）：
        1. 校验管理员权限与 Neo4j 安装目录
        2. 若认证存储已存在 → 不覆盖，直接退出（避免把你在用的密码改掉）
        3. 停止 Neo4j 服务（改动认证存储时服务必须停）
        4. neo4j-admin dbms set-initial-password <密码>   写入 data\dbms\auth.ini
        5. 启动 Neo4j 服务并等待端口就绪
        6. 用项目虚拟环境里的 neo4j 驱动实测一次登录（成功即证明可用）

.PARAMETER Password
    要设置的 neo4j 用户密码（至少 8 位）。
    建议只用字母 / 数字 / -  _  . ：这些字符在 .env、Cypher 参数、docker 环境变量里都不需要转义。

.PARAMETER Neo4jHome
    Neo4j 安装目录（默认 D:\cheng du shi xi\neo4j-community-2026.08.1）。

.PARAMETER ServiceName
    Windows 服务名（默认 neo4j）。

.EXAMPLE
    # 以【管理员】身份打开 PowerShell 后执行：
    powershell -ExecutionPolicy Bypass -File .\tools\neo4j_init_auth.ps1 -Password 'Gph-xxxxxxxx'

.NOTES
    忘记密码时如何重置：停止服务 → 删除 <Neo4jHome>\data\dbms\auth.ini → 重新运行本脚本。
    ⚠️ 该操作会清空所有 Neo4j 账号（图数据本身不受影响）。
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Password,

    [string]$Neo4jHome = 'D:\cheng du shi xi\neo4j-community-2026.08.1',

    [string]$ServiceName = 'neo4j',

    [string]$BoltUri = 'bolt://127.0.0.1:7687',

    [string]$VerifyPython = (Join-Path $PSScriptRoot '..\.venv\Scripts\python.exe')
)

$ErrorActionPreference = 'Stop'
$script:Failed = $false

function Write-Step { param([string]$Msg) Write-Host "==> $Msg" -ForegroundColor Cyan }
function Write-Ok   { param([string]$Msg) Write-Host "  OK  $Msg" -ForegroundColor Green }
function Write-Warn2{ param([string]$Msg) Write-Host "  !!  $Msg" -ForegroundColor Yellow }

# ----------------------------------------------------------
# 0) 前置校验
# ----------------------------------------------------------
if ($Password.Length -lt 8) {
    Write-Host "密码至少 8 位（Neo4j 的硬性要求）" -ForegroundColor Red
    exit 2
}

$identity  = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "需要管理员权限：请右键 PowerShell『以管理员身份运行』后重试。" -ForegroundColor Red
    exit 3
}

$adminBat = Join-Path $Neo4jHome 'bin\neo4j-admin.bat'
if (-not (Test-Path $adminBat)) {
    Write-Host "找不到 neo4j-admin：$adminBat（请用 -Neo4jHome 指定实际安装目录）" -ForegroundColor Red
    exit 4
}

$authFile = Join-Path $Neo4jHome 'data\dbms\auth.ini'
if (Test-Path $authFile) {
    Write-Warn2 "认证存储已存在（$authFile），本脚本不覆盖已有密码。"
    Write-Host "  如果你忘了密码，请：停止服务 → 删除该文件 → 重新运行本脚本。" -ForegroundColor Yellow
    exit 0
}

$svc = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if (-not $svc) {
    Write-Host "找不到服务 $ServiceName（可用 Get-Service 确认服务名）" -ForegroundColor Red
    exit 5
}

# ----------------------------------------------------------
# 1) 停服务
# ----------------------------------------------------------
Write-Step "停止服务 $ServiceName"
try {
    if ($svc.Status -ne 'Stopped') {
        Stop-Service -Name $ServiceName -Force
        $svc.WaitForStatus('Stopped', [TimeSpan]::FromSeconds(90))
    }
    Write-Ok "服务已停止"
} catch {
    Write-Host "停止服务失败：$($_.Exception.Message)" -ForegroundColor Red
    exit 6
}

# ----------------------------------------------------------
# 2) 写入初始密码
#    ⚠️ 必须用 cmd 做重定向，不要用 PowerShell 的 2>&1：
#       PS 5.1 在 $ErrorActionPreference='Stop' 下，会把原生命令写到 stderr 的
#       普通警告（例如 Java 的 "WARNING: Using incubator modules"）
#       当成终止性错误抛出，导致真正的报错信息被吞掉、退出码也读错位置
#       （本脚本第一版就踩过这个坑：命令其实成功了，却报告失败）。
# ----------------------------------------------------------
$logFile = Join-Path $env:TEMP ("neo4j_setpw_{0}.log" -f $PID)
Write-Step "neo4j-admin dbms set-initial-password"

cmd.exe /c "`"$adminBat`" dbms set-initial-password $Password > `"$logFile`" 2>&1"
$code = $LASTEXITCODE
if (Test-Path $logFile) {
    Get-Content $logFile -ErrorAction SilentlyContinue | ForEach-Object { "      $_" }
    Remove-Item $logFile -Force -ErrorAction SilentlyContinue
}

if ($code -ne 0) {
    Write-Host "设置初始密码失败（exit=$code）" -ForegroundColor Red
    Write-Warn2 "Neo4j 2026.x 需要 Java 21+；请确认 JAVA_HOME 指向 JDK 21 或更高版本。"
    Write-Warn2 "若提示认证存储已存在，请先停服务并删除 $authFile，再重跑本脚本。"
    $script:Failed = $true
} else {
    Write-Ok "已为 neo4j 用户写入初始密码（$authFile）"
}

# ----------------------------------------------------------
# 3) 起服务（无论上一步成败都要把服务恢复起来，别让环境停在半死状态）
# ----------------------------------------------------------
Write-Step "启动服务 $ServiceName"
try {
    Start-Service -Name $ServiceName
    $deadline = (Get-Date).AddSeconds(180)
    $ready = $false
    while ((Get-Date) -lt $deadline) {
        Start-Sleep -Seconds 3
        if ((Test-NetConnection -ComputerName 127.0.0.1 -Port 7687 -InformationLevel Quiet -WarningAction SilentlyContinue)) {
            $ready = $true
            break
        }
    }
    if ($ready) { Write-Ok "Bolt 端口 7687 已就绪" }
    else { Write-Warn2 "等待 180 秒仍未见 7687 就绪，请查看 $Neo4jHome\logs\neo4j.log" }
} catch {
    Write-Host "启动服务失败：$($_.Exception.Message)" -ForegroundColor Red
    exit 7
}

if ($script:Failed) { exit 8 }

# ----------------------------------------------------------
# 4) 实测登录（用项目虚拟环境的 neo4j 驱动，验证「真的能连上」）
# ----------------------------------------------------------
if (Test-Path $VerifyPython) {
    Write-Step "实测连接（neo4j 驱动）"
    $env:NEO4J_TEST_PASSWORD = $Password
    $py = @'
import os, sys
from neo4j import GraphDatabase
pw = os.environ.get("NEO4J_TEST_PASSWORD", "")
try:
    with GraphDatabase.driver("bolt://127.0.0.1:7687", auth=("neo4j", pw)) as d:
        d.verify_connectivity()
        rec = d.execute_query("CALL dbms.components() YIELD name, versions RETURN name, versions[0] AS v")
        row = rec.records[0]
        print(f"      连接成功：{row['name']} {row['v']}")
except Exception as e:
    print(f"      连接失败：{type(e).__name__}: {e}")
    sys.exit(1)
'@
    $py | & $VerifyPython -
    if ($LASTEXITCODE -eq 0) { Write-Ok "认证初始化完成，GraphRAG 可以连库了" }
    else { Write-Warn2 "驱动连接失败：请确认 server\.env 里的 NEO4J_PASSWORD 与本次设置的密码一致" }
    Remove-Item Env:\NEO4J_TEST_PASSWORD -ErrorAction SilentlyContinue
} else {
    Write-Warn2 "未找到虚拟环境 Python（$VerifyPython），跳过实测连接"
}

Write-Host ""
Write-Host "下一步：把下面这一行写进 server\.env（若已存在则替换其值）" -ForegroundColor Cyan
Write-Host "    NEO4J_PASSWORD=<本次设置的密码>" -ForegroundColor White
