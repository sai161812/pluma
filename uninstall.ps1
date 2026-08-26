<#
.SYNOPSIS
    PLUMA Windows 11 Automated Uninstaller
.DESCRIPTION
    Safely uninstalls PLUMA package, closes resident processes, and cleans temp directories.
#>

[CmdletBinding()]
param (
    [switch]$PurgeData = $false
)

$ErrorActionPreference = "Stop"

Write-Host "====================================================" -ForegroundColor Yellow
Write-Host "       PLUMA Windows 11 Uninstaller                 " -ForegroundColor Yellow
Write-Host "====================================================" -ForegroundColor Yellow

# 1. Stop resident processes
Write-Host "[1/3] Stopping any running PLUMA resident processes..." -ForegroundColor Green
Get-Process -Name "pluma" -ErrorAction SilentlyContinue | Stop-Process -Force

# 2. Uninstall pip package
$pythonExe = (Get-Command python -ErrorAction SilentlyContinue).Source
if ($pythonExe) {
    Write-Host "[2/3] Uninstalling PLUMA Python package..." -ForegroundColor Green
    & $pythonExe -m pip uninstall -y pluma
}

# 3. Clean runtime files if requested
if ($PurgeData) {
    $dataDir = "$env:LOCALAPPDATA\PLUMA"
    if (Test-Path $dataDir) {
        Write-Host "[3/3] Purging user data at $dataDir..." -ForegroundColor Yellow
        Remove-Item -Path $dataDir -Recurse -Force
    }
} else {
    Write-Host "[3/3] User database and preferences preserved." -ForegroundColor Green
}

Write-Host "`nPLUMA Uninstallation Complete." -ForegroundColor Yellow
