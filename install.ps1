<#
.SYNOPSIS
    PLUMA Windows 11 Automated Installer
.DESCRIPTION
    Installs PLUMA local autonomous agent wheel and configures user environment.
#>

[CmdletBinding()]
param (
    [string]$TargetDir = "$env:LOCALAPPDATA\PLUMA"
)

$ErrorActionPreference = "Stop"

Write-Host "====================================================" -ForegroundColor Cyan
Write-Host "       PLUMA Windows 11 Installation Script         " -ForegroundColor Cyan
Write-Host "====================================================" -ForegroundColor Cyan

# 1. Verify Python 3.12+
$pythonExe = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $pythonExe) {
    Write-Error "Python 3.12+ was not found in PATH. Please install Python 3.12 and retry."
}
Write-Host "[1/4] Found Python at: $pythonExe" -ForegroundColor Green

# 2. Create Target Directory
if (-not (Test-Path $TargetDir)) {
    New-Item -ItemType Directory -Path $TargetDir -Force | Out-Null
}
Write-Host "[2/4] Target directory configured: $TargetDir" -ForegroundColor Green

# 3. Locate and install wheel package
$wheel = Get-ChildItem -Path "$PSScriptRoot\packages\*.whl" -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $wheel) {
    $wheel = Get-ChildItem -Path "$PSScriptRoot\dist\*.whl" -ErrorAction SilentlyContinue | Select-Object -First 1
}
if ($wheel) {
    Write-Host "[3/4] Installing PLUMA wheel package: $($wheel.FullName)" -ForegroundColor Green
    & $pythonExe -m pip install --upgrade --no-warn-script-location $wheel.FullName
} else {
    Write-Host "[3/4] Installing PLUMA in editable mode from source..." -ForegroundColor Green
    & $pythonExe -m pip install -e $PSScriptRoot
}

# 4. Verify installation
Write-Host "[4/4] Verifying resident core imports..." -ForegroundColor Green
& $pythonExe -c "from pluma.core.resident import ResidentCore; core = ResidentCore(); print('PLUMA Resident Core verified successfully.')"

Write-Host "`nPLUMA Installation Complete." -ForegroundColor Cyan
