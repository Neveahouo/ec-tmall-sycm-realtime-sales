<#
    以 debug 模式启动浏览器，供采集脚本连接。
    用法：
        .\scripts\start_browser_debug.ps1                 # 默认 Edge，端口 9222
        .\scripts\start_browser_debug.ps1 -Browser chrome
#>
param(
    [ValidateSet('edge', 'chrome')]
    [string]$Browser = 'edge',
    [int]$Port = 9222,
    [string]$ProfileDir = ''
)

$projectRoot = $PSScriptRoot
if (-not $ProfileDir) {
    $ProfileDir = Join-Path $projectRoot 'browser_profile'
}
if (-not (Test-Path -LiteralPath $ProfileDir)) {
    New-Item -ItemType Directory -Path $ProfileDir -Force | Out-Null
}

if ($Browser -eq 'chrome') {
    $candidates = @(
        Join-Path $env:ProgramFiles 'Google\Chrome\Application\chrome.exe'
        Join-Path ${env:ProgramFiles(x86)} 'Google\Chrome\Application\chrome.exe'
        Join-Path $env:LOCALAPPDATA 'Google\Chrome\Application\chrome.exe'
    )
} else {
    $candidates = @(
        Join-Path ${env:ProgramFiles(x86)} 'Microsoft\Edge\Application\msedge.exe'
        Join-Path $env:ProgramFiles 'Microsoft\Edge\Application\msedge.exe'
    )
}

$exe = $candidates | Where-Object { $_ -and (Test-Path -LiteralPath $_) } | Select-Object -First 1
if (-not $exe) {
    Write-Error "未找到 $Browser，请先安装后再运行。"
    exit 1
}

# 已有同 profile 的进程会让新参数失效，先提示
$running = Get-Process -Name $(if ($Browser -eq 'chrome') { 'chrome' } else { 'msedge' }) `
    -ErrorAction SilentlyContinue
if ($running) {
    Write-Host "提示：检测到浏览器已在运行。若它不是用本 profile 启动的，端口可能不生效。" -ForegroundColor Yellow
    Write-Host "      建议先完全退出该浏览器，再运行本脚本。" -ForegroundColor Yellow
}

Start-Process -FilePath $exe -ArgumentList @(
    "--remote-debugging-port=$Port"
    "--user-data-dir=$ProfileDir"
    'https://sycm.taobao.com/portal/home.htm'
)

Start-Sleep -Seconds 4
try {
    $ver = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/json/version" -TimeoutSec 5
    Write-Host "已启动：$exe" -ForegroundColor Green
    Write-Host "debug 端口：$Port（$($ver.Browser)）" -ForegroundColor Green
    Write-Host ""
    Write-Host "下一步：在弹出的窗口中登录生意参谋，停留在页面后保持窗口打开。" -ForegroundColor Cyan
} catch {
    Write-Host "端口 $Port 未就绪，请检查浏览器是否被已有进程复用。" -ForegroundColor Red
    exit 1
}
