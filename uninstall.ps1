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
Get-Process -Name "python" -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -match "pluma" } | Stop-Process -Force

# 2. Remove Startup Shortcut
$StartupFolder = [Environment]::GetFolderPath("Startup")
$ShortcutPath = "$StartupFolder\PLUMA.lnk"
if (Test-Path $ShortcutPath) {
    Write-Host "[2/3] Removing Windows Startup shortcut..." -ForegroundColor Green
    Remove-Item -Path $ShortcutPath -Force
}

# 3. Clean installation and runtime files
$dataDir = "$env:LOCALAPPDATA\PLUMA"
if (Test-Path $dataDir) {
    if ($PurgeData) {
        Write-Host "[3/3] Purging user data and virtual environment at $dataDir..." -ForegroundColor Yellow
        Remove-Item -Path $dataDir -Recurse -Force
    } else {
        Write-Host "[3/3] Removing virtual environment at $dataDir\venv..." -ForegroundColor Green
        if (Test-Path "$dataDir\venv") {
            Remove-Item -Path "$dataDir\venv" -Recurse -Force
        }
        Write-Host "      User database and preferences preserved." -ForegroundColor Green
    }
}

Write-Host "`nPLUMA Uninstallation Complete." -ForegroundColor Yellow
