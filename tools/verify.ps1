# 一键自检：对全部 .vue 做静态检查（模板配平 / JS 语法 / SCSS 括号 / 变量 / 路由 / 组件 / 图标）
# 用法（在项目根目录执行）：powershell -File tools\verify.ps1
# 注意：本文件需以 UTF-8 BOM 保存，否则 Windows PowerShell 5.1 读取中文会乱码

$ErrorActionPreference = 'Continue'
$root = Split-Path -Parent $PSScriptRoot
if (-not $root) { $root = (Get-Location).Path }

Write-Host "项目根目录：$root`n" -ForegroundColor Cyan

$failed = 0
foreach ($script in @('check-vue.js', 'check-scss-vars.js', 'check-routes.js', 'check-components.js', 'check-icons.js')) {
	Write-Host "===== $script =====" -ForegroundColor Yellow
	node (Join-Path $PSScriptRoot $script) $root
	if ($LASTEXITCODE -ne 0) { $failed++ }
	Write-Host ""
}

if ($failed -gt 0) {
	Write-Host "自检完成：有 $failed 项未通过，请按上面的提示修复。" -ForegroundColor Red
	exit 1
}
Write-Host "自检完成：全部通过。" -ForegroundColor Green
