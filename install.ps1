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

Write-Host "[3/4] Creating virtual environment and installing PLUMA..." -ForegroundColor Green
& $pythonExe -m venv "$TargetDir\venv"
$venvPython = "$TargetDir\venv\Scripts\python.exe"
$venvPip = "$TargetDir\venv\Scripts\pip.exe"

if ($wheel) {
    Write-Host "      Installing wheel package: $($wheel.FullName)"
    & $venvPip install --upgrade "$($wheel.FullName)[windows,media]"
} else {
    Write-Host "      Installing in editable mode from source..."
    & $venvPip install -e "$PSScriptRoot[windows,media]"
}

# 4. Verify installation and setup startup shortcut
Write-Host "[4/4] Verifying installation and creating startup shortcut..." -ForegroundColor Green
& $venvPython -c "from pluma.core.resident import ResidentCore; print('PLUMA Resident Core verified successfully.')"

# Create shortcut in Startup folder
$WshShell = New-Object -ComObject WScript.Shell
$StartupFolder = [Environment]::GetFolderPath("Startup")
$Shortcut = $WshShell.CreateShortcut("$StartupFolder\PLUMA.lnk")
$Shortcut.TargetPath = "$TargetDir\venv\Scripts\pluma.exe"
$Shortcut.WorkingDirectory = "$TargetDir"
$Shortcut.IconLocation = "$TargetDir\venv\Scripts\pluma.exe"
$Shortcut.WindowStyle = 7 # Minimized
$Shortcut.Save()
Write-Host "      Added PLUMA to Windows Startup."

Write-Host "`nPLUMA Installation Complete." -ForegroundColor Cyan
