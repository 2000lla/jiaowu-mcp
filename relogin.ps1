#!/usr/bin/env pwsh
# 一键重新扫码登录（Windows）。
#
# 解决 DSH 桌面版下的两个环境问题（详见 docs/windows-deploy.md）：
#   1. 工作区内的可执行文件被降为 Low 完整性，无法写 Temp / ~/.cache（Medium），
#      导致 Selenium Manager 报"拒绝访问" —— 改用工作区外的系统 Python，
#      并通过 CHROMEDRIVER 显式指定驱动，完全绕开 Selenium Manager。
#   2. chromedriver 不随仓库分发 —— 缺失时自动从 npmmirror 下载与本机 Chrome
#      匹配的版本（精确版本缺失时取同 build 最接近的版本）。
#
# 用法：
#   .\relogin.ps1                  # 重新扫码登录
#   .\relogin.ps1 --from-session   # 先尝试复用 .session.json 里的票据
#   .\relogin.ps1 --timeout 600    # 其余参数透传给 qr_login.py
#
# 前提：已建好 .venv 并填好 config.local.json（见 README / docs/windows-deploy.md）。
$ErrorActionPreference = 'Stop'
$dir = $PSScriptRoot

# ---- 0. 基本检查 ----
$venvPy = Join-Path $dir '.venv\Scripts\python.exe'
if (-not (Test-Path $venvPy)) {
    throw '缺少 .venv，请先执行: python -m venv .venv; .\.venv\Scripts\python.exe -m pip install -r requirements-mcp.txt'
}
if (-not (Test-Path (Join-Path $dir 'config.local.json'))) {
    throw '缺少 config.local.json，请先从 config.example.json 复制并填写学校信息'
}
New-Item -ItemType Directory -Path (Join-Path $dir 'outputs') -Force | Out-Null

# ---- 1. 选 Python：优先工作区外的系统 Python（避免 Low 完整性）----
$py = $venvPy
$sys = Get-Command python -ErrorAction SilentlyContinue
if ($sys -and -not $sys.Source.StartsWith($dir, [StringComparison]::OrdinalIgnoreCase)) {
    $py = $sys.Source
    $env:PYTHONPATH = Join-Path $dir '.venv\Lib\site-packages'
    Write-Host "==> 使用系统 Python: $py"
} else {
    Write-Host '==> 使用 venv Python（非 DSH 环境无完整性问题）'
}

# ---- 2. 登录依赖（selenium / pillow），缺失则装入 venv ----
$sp = Join-Path $dir '.venv\Lib\site-packages'
if (-not (Test-Path (Join-Path $sp 'selenium')) -or -not (Test-Path (Join-Path $sp 'PIL'))) {
    Write-Host '==> 安装登录依赖 (selenium / pillow)'
    & $venvPy -m pip install -r (Join-Path $dir 'requirements-login.txt') `
        --timeout 15 --retries 2 --no-input --disable-pip-version-check
    if ($LASTEXITCODE -ne 0) { throw '登录依赖安装失败' }
}

# ---- 3. 定位 / 下载 chromedriver ----
$driver = $env:CHROMEDRIVER
if (-not $driver -or -not (Test-Path $driver)) {
    foreach ($c in @((Join-Path $dir 'chromedriver-win64\chromedriver.exe'),
                     (Join-Path $env:USERPROFILE '.cache\selenium\chromedriver-win64\chromedriver.exe'))) {
        if (Test-Path $c) { $driver = $c; break }
    }
}
if (-not $driver -or -not (Test-Path $driver)) {
    $chrome = @("$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
                "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
                "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe") |
              Where-Object { Test-Path $_ } | Select-Object -First 1
    if (-not $chrome) { throw '未找到 Chrome，请先安装，或手动设置 CHROMEDRIVER 环境变量' }
    $ver = (Get-Item $chrome).VersionInfo.ProductVersion
    $prefix = ($ver -split '\.')[0..2] -join '.'
    Write-Host "==> Chrome $ver，从 npmmirror 获取 chromedriver"
    $cache = Join-Path $env:USERPROFILE '.cache\selenium'
    New-Item -ItemType Directory -Path $cache -Force | Out-Null
    $zip = Join-Path $cache 'chromedriver-win64.zip'
    $base = 'https://cdn.npmmirror.com/binaries/chrome-for-testing'
    $ok = $false
    try {
        Invoke-WebRequest "$base/$ver/win64/chromedriver-win64.zip" -OutFile $zip -UseBasicParsing -TimeoutSec 120
        $ok = $true
    } catch { }
    if (-not $ok) {
        # 精确版本常缺失（如浏览器 .74 而镜像只有 .73/.80），取同 build 最接近的版本
        $list = Invoke-RestMethod 'https://registry.npmmirror.com/-/binary/chrome-for-testing/' -TimeoutSec 60
        $cand = $list | ForEach-Object { $_.name.TrimEnd('/') } | Where-Object { $_ -like "$prefix.*" }
        if (-not $cand) { throw "npmmirror 上没有 $prefix.x 的 chromedriver" }
        $pick = $cand | Sort-Object { [version]$_ } |
                Where-Object { [version]$_ -le [version]$ver } | Select-Object -Last 1
        if (-not $pick) { $pick = $cand | Sort-Object { [version]$_ } | Select-Object -First 1 }
        Write-Host "==> 精确版本缺失，改用 $pick（主版本一致即可兼容）"
        Invoke-WebRequest "$base/$pick/win64/chromedriver-win64.zip" -OutFile $zip -UseBasicParsing -TimeoutSec 120
    }
    Expand-Archive $zip -DestinationPath $cache -Force
    $driver = Join-Path $cache 'chromedriver-win64\chromedriver.exe'
}
$env:CHROMEDRIVER = $driver
Write-Host "==> chromedriver: $driver"

# ---- 4. 登录 ----
$env:PYTHONIOENCODING = 'utf-8'
& $py (Join-Path $dir 'qr_login.py') @args
exit $LASTEXITCODE
