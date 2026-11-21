# SunPower back end (Windows). Creates .venv on first run, installs packages,
# then serves the API on http://localhost:8001. The SQLite database lives in
# backend\data\sunpower.db and is filled with demo data on first start.
#   powershell -ExecutionPolicy Bypass -File .\backend\run.ps1 [-Port 8001] [-Reset]
param([int]$Port = 8001, [switch]$Reset)
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

$py = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    $installed = (& py -0 | Out-String)
    $ver = $null
    foreach ($v in @("3.12", "3.13", "3.11")) { if ($installed -match [regex]::Escape("-V:$v")) { $ver = $v; break } }
    if (-not $ver) { throw "Python 3.11-3.13 not found (install it from python.org)." }
    & py "-$ver" -m venv .venv
    & $py -m pip install --upgrade pip
    & $py -m pip install -r requirements.txt
}
if ($Reset) {
    Remove-Item -Force -ErrorAction SilentlyContinue "data\sunpower.db", "data\sunpower.db-wal", "data\sunpower.db-shm"
    Write-Host "Database reset: demo data will be loaded again."
}
Write-Host "SunPower back end on http://localhost:$Port  (API docs: /api/docs)"
& $py -m uvicorn app.main:app --host 127.0.0.1 --port $Port
