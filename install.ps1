<#
.SYNOPSIS
    Installs PLUMA for the current Windows user.
.DESCRIPTION
    Verifies Python and every native command before publishing the startup
    shortcut. Runtime model files remain external and are not downloaded here.
#>

[CmdletBinding()]
param (
    [string]$TargetDir = (Join-Path $env:LOCALAPPDATA 'PLUMA')
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Invoke-NativeCommand {
    param (
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter(Mandatory = $true)][string[]]$Arguments
    )

    & $FilePath @Arguments
    $nativeExitCode = $LASTEXITCODE
    if ($nativeExitCode -ne 0) {
        throw "Command failed with exit code ${nativeExitCode}: $FilePath $($Arguments -join ' ')"
    }
}

function Get-CanonicalPath {
    param ([Parameter(Mandatory = $true)][string]$Path)
    return [System.IO.Path]::GetFullPath($Path).TrimEnd('\')
}

function Assert-NoReparseAncestors {
    param ([Parameter(Mandatory = $true)][string]$Path)
    $current = [System.IO.Path]::GetFullPath($Path)
    while (-not [string]::IsNullOrWhiteSpace($current)) {
        if (Test-Path -LiteralPath $current) {
            $item = Get-Item -LiteralPath $current -Force
            if (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw "Refusing a target path beneath a reparse point: $($item.FullName)"
            }
        }
        $parent = [System.IO.Directory]::GetParent($current)
        if (-not $parent) { break }
        $current = $parent.FullName
    }
}

try {
    Write-Host 'PLUMA Windows user installation' -ForegroundColor Cyan

    $pythonCommand = Get-Command python -CommandType Application -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if (-not $pythonCommand -or -not (Test-Path -LiteralPath $pythonCommand.Source -PathType Leaf)) {
        throw 'Python 3.12 or newer was not found. No installation or startup setting was changed.'
    }
    $pythonExe = $pythonCommand.Source
    $versionText = & $pythonExe -c 'import json,sys; print(json.dumps(list(sys.version_info[:3])))'
    $versionExitCode = $LASTEXITCODE
    if ($versionExitCode -ne 0) {
        throw "Python version check failed with exit code ${versionExitCode}."
    }
    $pythonVersion = @($versionText | ConvertFrom-Json)
    if (($pythonVersion.Count -lt 2) -or ($pythonVersion[0] -lt 3) -or
        (($pythonVersion[0] -eq 3) -and ($pythonVersion[1] -lt 12))) {
        throw "Python 3.12 or newer is required; found $($pythonVersion -join '.')."
    }
    Write-Host "Using Python $($pythonVersion -join '.') at $pythonExe"

    $targetPath = Get-CanonicalPath -Path $TargetDir
    $targetRoot = [System.IO.Path]::GetPathRoot($targetPath).TrimEnd('\')
    if ([string]::IsNullOrWhiteSpace($targetPath) -or $targetPath -eq $targetRoot) {
        throw "Refusing unsafe installation target: $targetPath"
    }
    Assert-NoReparseAncestors -Path $targetPath
    if (Test-Path -LiteralPath $targetPath) {
        $targetItem = Get-Item -LiteralPath $targetPath -Force
        if (-not $targetItem.PSIsContainer -or
            (($targetItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0)) {
            throw "Installation target must be a real directory, not a file or reparse point: $targetPath"
        }
    }

    $installManifestPath = Join-Path $targetPath '.pluma-install.json'
    if (Test-Path -LiteralPath $targetPath) {
        $existingItems = @(Get-ChildItem -LiteralPath $targetPath -Force)
        if ($existingItems.Count -gt 0 -and -not (Test-Path -LiteralPath $installManifestPath -PathType Leaf)) {
            throw "The target contains unmarked data. Refusing to adopt or overwrite it: $targetPath"
        }
        if (Test-Path -LiteralPath $installManifestPath -PathType Leaf) {
            $priorManifest = Get-Content -LiteralPath $installManifestPath -Raw | ConvertFrom-Json
            if ((Get-CanonicalPath -Path $priorManifest.install_root) -ne $targetPath) {
                throw 'The existing PLUMA installation marker names a different path.'
            }
            $expectedMarkerExe = Get-CanonicalPath -Path (Join-Path $targetPath 'venv\Scripts\pluma.exe')
            if ($priorManifest.schema_version -ne 1 -or
                [string]::IsNullOrWhiteSpace([string]$priorManifest.install_id) -or
                (Get-CanonicalPath -Path $priorManifest.executable) -ne $expectedMarkerExe) {
                throw 'The existing PLUMA installation marker is incomplete or invalid.'
            }
        }
    } else {
        New-Item -ItemType Directory -Path $targetPath | Out-Null
    }

    $venvDir = Join-Path $targetPath 'venv'
    $venvPython = Join-Path $venvDir 'Scripts\python.exe'
    $plumaExe = Join-Path $venvDir 'Scripts\pluma.exe'
    $existingManifest = $null
    if (Test-Path -LiteralPath $installManifestPath -PathType Leaf) {
        $existingManifest = Get-Content -LiteralPath $installManifestPath -Raw | ConvertFrom-Json
    }
    $installId = if ($existingManifest -and $existingManifest.install_id) {
        [string]$existingManifest.install_id
    } else {
        [guid]::NewGuid().ToString('D')
    }
    $manifest = [ordered]@{
        schema_version = 1
        install_id = $installId
        install_root = $targetPath
        executable = $plumaExe
        venv_python = $venvPython
        state = 'installing'
        updated_at_utc = [DateTime]::UtcNow.ToString('o')
    }
    $manifestTemp = "$installManifestPath.$([guid]::NewGuid().ToString('N')).tmp"
    [System.IO.File]::WriteAllText(
        $manifestTemp,
        ($manifest | ConvertTo-Json -Depth 4),
        [System.Text.UTF8Encoding]::new($false)
    )
    Move-Item -LiteralPath $manifestTemp -Destination $installManifestPath -Force

    if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) {
        Invoke-NativeCommand -FilePath $pythonExe -Arguments @('-m', 'venv', $venvDir)
    }
    if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) {
        throw "Virtual environment creation returned without producing $venvPython"
    }

    $wheel = Get-ChildItem -LiteralPath (Join-Path $PSScriptRoot 'packages') -Filter '*.whl' -File -ErrorAction SilentlyContinue |
        Sort-Object Name |
        Select-Object -First 1
    if (-not $wheel) {
        $wheel = Get-ChildItem -LiteralPath (Join-Path $PSScriptRoot 'dist') -Filter '*.whl' -File -ErrorAction SilentlyContinue |
            Sort-Object Name |
            Select-Object -First 1
    }

    $runtimeExtras = '[windows,media,stt,ocr]'
    if ($wheel) {
        $packageSpec = "$($wheel.FullName)$runtimeExtras"
    } elseif (Test-Path -LiteralPath (Join-Path $PSScriptRoot 'pyproject.toml') -PathType Leaf) {
        $packageSpec = "$PSScriptRoot$runtimeExtras"
    } else {
        throw 'No PLUMA wheel was found and this directory is not a source checkout.'
    }
    Write-Host "Installing declared PLUMA runtime dependencies from $packageSpec"
    Invoke-NativeCommand -FilePath $venvPython -Arguments @('-m', 'pip', 'install', '--upgrade', '--no-cache-dir', $packageSpec)

    $verifyScript = @'
import importlib.metadata as metadata
from pluma.core.resident import ResidentCore
required = ("pluma", "pydantic", "PyYAML", "psutil", "jsonschema", "websockets", "pywin32", "pycaw", "comtypes", "pywinauto", "sounddevice", "numpy", "Pillow", "pywhispercpp", "paddleocr", "onnxruntime")
missing = []
for name in required:
    try:
        metadata.version(name)
    except metadata.PackageNotFoundError:
        missing.append(name)
if missing:
    raise SystemExit("Required distributions are missing: " + ", ".join(missing))
'@
    Invoke-NativeCommand -FilePath $venvPython -Arguments @('-c', $verifyScript)

    if (-not (Test-Path -LiteralPath $plumaExe -PathType Leaf)) {
        throw "Installation verification did not produce the startup executable: $plumaExe"
    }
    $startupFolder = [Environment]::GetFolderPath('Startup')
    if ([string]::IsNullOrWhiteSpace($startupFolder)) {
        throw 'Windows did not provide a Startup folder path; installation was not published.'
    }
    $shortcutPath = Join-Path $startupFolder 'PLUMA.lnk'
    $shell = New-Object -ComObject WScript.Shell
    Assert-NoReparseAncestors -Path $shortcutPath
    if (Test-Path -LiteralPath $shortcutPath -PathType Leaf) {
        $shortcutItem = Get-Item -LiteralPath $shortcutPath -Force
        if (($shortcutItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "Refusing to replace a reparse-point startup shortcut: $shortcutPath"
        }
        $existingShortcut = $shell.CreateShortcut($shortcutPath)
        if ([string]::IsNullOrWhiteSpace($existingShortcut.TargetPath) -or
            (Get-CanonicalPath -Path $existingShortcut.TargetPath) -ne (Get-CanonicalPath -Path $plumaExe)) {
            throw "A different application already owns $shortcutPath; it was left unchanged."
        }
    }
    $manifest.state = 'installed'
    $manifest.updated_at_utc = [DateTime]::UtcNow.ToString('o')
    $manifestTemp = "$installManifestPath.$([guid]::NewGuid().ToString('N')).tmp"
    [System.IO.File]::WriteAllText(
        $manifestTemp,
        ($manifest | ConvertTo-Json -Depth 4),
        [System.Text.UTF8Encoding]::new($false)
    )
    Move-Item -LiteralPath $manifestTemp -Destination $installManifestPath -Force
    $savedManifest = Get-Content -LiteralPath $installManifestPath -Raw | ConvertFrom-Json
    if ((Get-CanonicalPath -Path $savedManifest.install_root) -ne $targetPath -or
        $savedManifest.install_id -ne $installId -or $savedManifest.state -ne 'installed') {
        throw 'Installation ownership marker did not read back with the expected identity.'
    }

    $shortcut = $shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = $plumaExe
    $shortcut.WorkingDirectory = $targetPath
    $shortcut.IconLocation = $plumaExe
    $shortcut.WindowStyle = 7
    $shortcut.Save()
    $savedShortcut = $shell.CreateShortcut($shortcutPath)
    if ([string]::IsNullOrWhiteSpace($savedShortcut.TargetPath) -or
        (Get-CanonicalPath -Path $savedShortcut.TargetPath) -ne (Get-CanonicalPath -Path $plumaExe)) {
        throw 'Startup shortcut did not read back with the expected PLUMA executable.'
    }

    Write-Host 'PLUMA installation verified; startup shortcut published.' -ForegroundColor Green
} catch {
    Write-Host "PLUMA installation failed: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
