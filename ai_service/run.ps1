# SunPower AI service launcher (Windows, no Docker).
# Creates .venv on first run, installs requirements, then starts uvicorn on port 8000.
# Usage:  powershell -ExecutionPolicy Bypass -File .\run.ps1 [-Port 8000] [-Reinstall]
param(
    [int]$Port = 8000,
    [switch]$Reinstall
)
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

$venvPy = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) {
    # Prefer 3.12/3.11 if present (widest wheel support), else whatever 'py' defaults to (3.13 works with TF 2.20).
    $installed = (& py -0 | Out-String)
    $pyVer = $null
    foreach ($v in @("3.12", "3.11", "3.13")) {
        if ($installed -match [regex]::Escape("-V:$v")) { $pyVer = $v; break }
    }
    if (-not $pyVer) { throw "No Python 3.11-3.13 found via the 'py' launcher." }
    Write-Host "Creating venv with Python $pyVer ..."
    & py "-$pyVer" -m venv .venv
    $Reinstall = $true
}

if (-not $Reinstall) {
    # venv exists but deps may be missing (e.g. an interrupted install)
    $ErrorActionPreference = "Continue"
    & $venvPy -c "import fastapi, uvicorn, huggingface_hub, dotenv, multipart, PIL, numpy" 2>$null
    if ($LASTEXITCODE -ne 0) { $Reinstall = $true }
    $ErrorActionPreference = "Stop"
}

if ($Reinstall) {
    Write-Host "Installing requirements (TensorFlow is large; first install takes a few minutes) ..."
    & $venvPy -m pip install --upgrade pip
    & $venvPy -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw "pip install failed" }
}

if (-not (Test-Path (Join-Path $PSScriptRoot "..\.env"))) {
    Write-Warning "..\.env not found - HF_TOKEN missing, remote AI endpoints will return errors."
}

Write-Host "Starting SunPower AI service on http://localhost:$Port ..."
& $venvPy -m uvicorn main:app --host 127.0.0.1 --port $Port
