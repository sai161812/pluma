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

function Test-PathWithin {
    param (
        [Parameter(Mandatory = $true)][string]$Parent,
        [Parameter(Mandatory = $true)][string]$Child
    )
    $parentCanonical = (Get-CanonicalPath -Path $Parent) + '\'
    $childCanonical = Get-CanonicalPath -Path $Child
    return $childCanonical.StartsWith($parentCanonical, [System.StringComparison]::OrdinalIgnoreCase)
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

function Assert-NoReparseTree {
    param ([Parameter(Mandatory = $true)][string]$Path)
    $pending = [System.Collections.Generic.Stack[string]]::new()
    $pending.Push($Path)
    while ($pending.Count -gt 0) {
        $current = $pending.Pop()
        $item = Get-Item -LiteralPath $current -Force
        if (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "Refusing a package tree containing a reparse point: $($item.FullName)"
        }
        if ($item.PSIsContainer) {
            foreach ($child in Get-ChildItem -LiteralPath $current -Force) {
                $pending.Push($child.FullName)
            }
        }
    }
}

function Assert-PackageIntegrity {
    param (
        [Parameter(Mandatory = $true)][string]$PackageRoot,
        [Parameter(Mandatory = $true)][string[]]$RequiredPaths
    )
    $root = Get-CanonicalPath -Path $PackageRoot
    $manifestPath = Join-Path $root 'SHA256SUMS.txt'
    if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
        throw 'The package SHA256SUMS.txt manifest is missing; installation stopped before changes.'
    }
    $manifestItem = Get-Item -LiteralPath $manifestPath -Force
    if (($manifestItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw 'The package integrity manifest is a reparse point.'
    }
    $seen = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::OrdinalIgnoreCase)
    foreach ($line in [System.IO.File]::ReadAllLines($manifestPath)) {
        if ($line -notmatch '\A([0-9a-fA-F]{64})  ([A-Za-z0-9._/-]+)\z') {
            throw 'The package integrity manifest contains a malformed entry.'
        }
        $expectedHash = $Matches[1].ToLowerInvariant()
        $relativePath = $Matches[2]
        $segments = $relativePath.Split('/')
        if ([System.IO.Path]::IsPathRooted($relativePath) -or $segments -contains '..' -or
            $segments -contains '.' -or -not $seen.Add($relativePath)) {
            throw 'The package integrity manifest contains an unsafe or duplicate path.'
        }
        $candidate = [System.IO.Path]::GetFullPath((Join-Path $root ($relativePath -replace '/', [System.IO.Path]::DirectorySeparatorChar)))
        if (-not $candidate.StartsWith($root + '\', [System.StringComparison]::OrdinalIgnoreCase) -or
            -not (Test-Path -LiteralPath $candidate -PathType Leaf)) {
            throw "A declared package file is missing or outside the package root: $relativePath"
        }
        Assert-NoReparseAncestors -Path $candidate
        $actualHash = (Get-FileHash -LiteralPath $candidate -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($actualHash -ne $expectedHash) {
            throw "Package integrity check failed for $relativePath."
        }
    }
    if ($seen.Count -eq 0) { throw 'The package integrity manifest contains no files.' }
    foreach ($requiredPath in $RequiredPaths) {
        if (-not $seen.Contains($requiredPath)) {
            throw "The package integrity manifest does not cover required content: $requiredPath"
        }
    }
    foreach ($ownedPackageSubtree in @('packages', 'ui')) {
        $subtree = Join-Path $root $ownedPackageSubtree
        if (-not (Test-Path -LiteralPath $subtree -PathType Container)) {
            throw "Required package directory is missing: $ownedPackageSubtree"
        }
        Assert-NoReparseTree -Path $subtree
        foreach ($file in Get-ChildItem -LiteralPath $subtree -File -Recurse) {
            $relative = $file.FullName.Substring(($root + '\').Length).Replace('\', '/')
            if (-not $seen.Contains($relative)) {
                throw "Package payload contains an unhashed file: $relative"
            }
        }
    }
}

try {
    Write-Host 'PLUMA Windows user installation' -ForegroundColor Cyan

    $uiSourceDir = Join-Path $PSScriptRoot 'ui'
    $uiSourceExe = Join-Path $uiSourceDir 'PLUMA.UI.exe'
    if (-not (Test-Path -LiteralPath $uiSourceDir -PathType Container) -or
        -not (Test-Path -LiteralPath $uiSourceExe -PathType Leaf)) {
        throw 'The unified package must contain ui\PLUMA.UI.exe. No installation or startup setting was changed.'
    }
    Assert-NoReparseTree -Path $uiSourceDir
    $packagesDir = Join-Path $PSScriptRoot 'packages'
    $coreWheels = @(Get-ChildItem -LiteralPath $packagesDir -Filter 'pluma-*.whl' -File -ErrorAction SilentlyContinue)
    $allWheels = @(Get-ChildItem -LiteralPath $packagesDir -Filter '*.whl' -File -ErrorAction SilentlyContinue)
    if ($coreWheels.Count -ne 1 -or $allWheels.Count -eq 0) {
        throw 'The unified package must contain exactly one PLUMA Core wheel and its offline runtime wheelhouse.'
    }
    Assert-PackageIntegrity -PackageRoot $PSScriptRoot -RequiredPaths @(
        'install.ps1', 'uninstall.ps1', 'ui/PLUMA.UI.exe', 'PRODUCT_SCOPE.txt',
        "packages/$($coreWheels[0].Name)"
    )

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
        if (Test-Path -LiteralPath $installManifestPath -PathType Leaf) {
            $markerItem = Get-Item -LiteralPath $installManifestPath -Force
            if (($markerItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw 'The existing PLUMA ownership marker is a reparse point.'
            }
        }
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
    $uiDir = Join-Path $targetPath 'ui'
    $uiExe = Join-Path $uiDir 'PLUMA.UI.exe'
    $existingManifest = $null
    $existingManifestProperties = @()
    if (Test-Path -LiteralPath $installManifestPath -PathType Leaf) {
        $existingManifest = Get-Content -LiteralPath $installManifestPath -Raw | ConvertFrom-Json
        $existingManifestProperties = @($existingManifest.PSObject.Properties.Name)
    }
    if (($existingManifestProperties -contains 'ui_directory') -or
        ($existingManifestProperties -contains 'ui_executable') -or
        ($existingManifestProperties -contains 'ui_shortcut')) {
        if (($existingManifestProperties -notcontains 'ui_directory') -or
            ($existingManifestProperties -notcontains 'ui_executable') -or
            -not $existingManifest.ui_directory -or -not $existingManifest.ui_executable -or
            (Get-CanonicalPath -Path $existingManifest.ui_directory) -ne (Get-CanonicalPath -Path $uiDir) -or
            (Get-CanonicalPath -Path $existingManifest.ui_executable) -ne (Get-CanonicalPath -Path $uiExe) -or
            (($existingManifestProperties -contains 'ui_shortcut') -and
             (Get-CanonicalPath -Path $existingManifest.ui_shortcut) -ne (Get-CanonicalPath -Path $uiShortcutPath))) {
            throw 'The existing PLUMA UI ownership marker is incomplete or names a different path.'
        }
        if ($existingManifest.state -eq 'installed') {
            if (($existingManifestProperties -notcontains 'ui_executable_sha256') -or
                ([string]$existingManifest.ui_executable_sha256 -notmatch '\A[0-9a-fA-F]{64}\z') -or
                -not (Test-Path -LiteralPath $uiExe -PathType Leaf) -or
                (Get-FileHash -LiteralPath $uiExe -Algorithm SHA256).Hash -ne $existingManifest.ui_executable_sha256) {
                throw 'The installed PLUMA UI does not match its recorded executable identity; no update was applied.'
            }
        }
    }
    if (Test-Path -LiteralPath $uiDir) {
        if (-not $existingManifest -or $existingManifestProperties -notcontains 'ui_directory' -or
            -not $existingManifest.ui_directory -or
            (Get-CanonicalPath -Path $existingManifest.ui_directory) -ne (Get-CanonicalPath -Path $uiDir)) {
            throw "The existing ui directory is not recorded as owned by this PLUMA install; preserving it: $uiDir"
        }
        Assert-NoReparseTree -Path $uiDir
    }

    $uiShortcutFolder = Join-Path ([Environment]::GetFolderPath('Programs')) 'PLUMA'
    $uiShortcutPath = Join-Path $uiShortcutFolder 'PLUMA UI.lnk'
    Assert-NoReparseAncestors -Path $uiShortcutFolder
    Assert-NoReparseAncestors -Path $uiShortcutPath
    $shell = New-Object -ComObject WScript.Shell
    if (Test-Path -LiteralPath $uiShortcutPath -PathType Leaf) {
        $uiShortcutItem = Get-Item -LiteralPath $uiShortcutPath -Force
        if (($uiShortcutItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "Refusing to replace a reparse-point UI shortcut: $uiShortcutPath"
        }
        $existingUiShortcut = $shell.CreateShortcut($uiShortcutPath)
        if ([string]::IsNullOrWhiteSpace($existingUiShortcut.TargetPath) -or
            (Get-CanonicalPath -Path $existingUiShortcut.TargetPath) -ne (Get-CanonicalPath -Path $uiExe)) {
            throw "A different application already owns $uiShortcutPath; it was left unchanged."
        }
    }

    # Upgrade only the exact marked Core through authenticated graceful shutdown.
    # The UI is never closed or killed by the installer; the owner closes it.
    $expectedRunningUi = if ($existingManifest -and $existingManifestProperties -contains 'ui_executable' -and $existingManifest.ui_executable) {
        Get-CanonicalPath -Path $existingManifest.ui_executable
    } else { Get-CanonicalPath -Path $uiExe }
    $running = @(Get-CimInstance -ClassName Win32_Process -Filter "Name='pluma.exe' OR Name='python.exe' OR Name='PLUMA.UI.exe'" -ErrorAction Stop)
    $runningUi = @(
        foreach ($process in $running) {
            if ($process.Name -ne 'PLUMA.UI.exe') { continue }
            if ([string]::IsNullOrWhiteSpace([string]$process.ExecutablePath)) {
                throw "PLUMA.UI.exe PID $($process.ProcessId) has no readable path; refusing to update while ownership is uncertain."
            }
            if ((Get-CanonicalPath -Path $process.ExecutablePath) -eq $expectedRunningUi) { $process }
        }
    )
    if ($runningUi.Count -gt 0) {
        throw "PLUMA UI is running (PID $($runningUi[0].ProcessId)). Close the UI and retry; no process was terminated."
    }
    $scriptsDir = Join-Path $venvDir 'Scripts'
    $runningVenv = @(
        foreach ($process in $running) {
            if ([string]::IsNullOrWhiteSpace([string]$process.ExecutablePath)) { continue }
            if (Test-PathWithin -Parent $scriptsDir -Child $process.ExecutablePath) { $process }
        }
    )
    $runningOtherInstall = @(
        foreach ($process in $running) {
            if ([string]::IsNullOrWhiteSpace([string]$process.ExecutablePath)) { continue }
            if ((Test-PathWithin -Parent $targetPath -Child $process.ExecutablePath) -and
                -not (Test-PathWithin -Parent $scriptsDir -Child $process.ExecutablePath)) { $process }
        }
    )
    if ($runningOtherInstall.Count -gt 0) {
        throw "A PLUMA installation process outside its marked Core environment is running (PID $($runningOtherInstall[0].ProcessId)); no process was terminated."
    }
    $runningCore = @(
        foreach ($process in $running) {
            if ($process.Name -notin @('pluma.exe', 'python.exe')) { continue }
            if ([string]::IsNullOrWhiteSpace([string]$process.ExecutablePath)) {
                if ($process.Name -eq 'pluma.exe') {
                    throw "pluma.exe PID $($process.ProcessId) has no readable path; refusing to update while ownership is uncertain."
                }
                continue
            }
            if ((Get-CanonicalPath -Path $process.ExecutablePath) -eq (Get-CanonicalPath -Path $plumaExe)) { $process }
        }
    )
    if ($runningCore.Count -gt 1) {
        throw 'More than one process matches the installed PLUMA Core executable; no process was terminated.'
    }
    if ($runningCore.Count -eq 0 -and $runningVenv.Count -gt 0) {
        $ids = ($runningVenv | ForEach-Object { $_.ProcessId }) -join ', '
        throw "PLUMA environment processes are running without an authenticated Core host (PID $ids); close them and retry."
    }
    if ($runningCore.Count -eq 1) {
        if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) {
            throw 'The installed Core is running but its marked Python shutdown helper is missing.'
        }
        $shutdownScript = 'import sys; from pluma.core.host import request_owned_core_shutdown; request_owned_core_shutdown(int(sys.argv[1]), sys.argv[2], sys.argv[3])'
        Invoke-NativeCommand -FilePath $venvPython -Arguments @('-c', $shutdownScript,
            [string]$runningCore[0].ProcessId, $targetPath, (Get-CanonicalPath -Path $plumaExe))
        $afterShutdown = @(Get-CimInstance -ClassName Win32_Process -Filter "Name='pluma.exe' OR Name='python.exe'" -ErrorAction Stop)
        $scriptsPath = (Get-CanonicalPath -Path (Join-Path $venvDir 'Scripts')) + '\'
        foreach ($process in $afterShutdown) {
            if ([string]::IsNullOrWhiteSpace([string]$process.ExecutablePath)) {
                if ($process.Name -eq 'pluma.exe') { throw 'A pluma.exe process remains with unreadable identity after shutdown.' }
                continue
            }
            $actualPath = Get-CanonicalPath -Path $process.ExecutablePath
            if ($actualPath -eq (Get-CanonicalPath -Path $plumaExe) -or
                $actualPath.StartsWith($scriptsPath, [System.StringComparison]::OrdinalIgnoreCase)) {
                throw "A process remains in the installed PLUMA environment after graceful shutdown (PID $($process.ProcessId))."
            }
        }
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
        ui_directory = $uiDir
        ui_executable = $uiExe
        ui_executable_sha256 = ''
        ui_shortcut = $uiShortcutPath
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

    Write-Host 'Installing PLUMA Core and declared runtime dependencies from the bundled offline wheelhouse.'
    Invoke-NativeCommand -FilePath $venvPython -Arguments @('-m', 'pip', 'install', '--upgrade', '--no-cache-dir',
        '--no-index', '--find-links', $packagesDir, 'pluma[windows,media,stt,ocr]')

    $verifyScript = @'
import importlib.metadata as metadata
from pathlib import Path
import sys
from pluma.core.resident import ResidentCore
wheel_name = Path(sys.argv[1]).name
if not wheel_name.startswith("pluma-") or not wheel_name.endswith(".whl"):
    raise SystemExit("The selected Core wheel is not a PLUMA wheel.")
expected_version = wheel_name[len("pluma-"):].split("-", 1)[0]
if metadata.version("pluma") != expected_version:
    raise SystemExit("Installed Core version does not match the verified PLUMA wheel.")
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
    Invoke-NativeCommand -FilePath $venvPython -Arguments @('-c', $verifyScript, $coreWheels[0].FullName)

    if (-not (Test-Path -LiteralPath $plumaExe -PathType Leaf)) {
        throw "Installation verification did not produce the startup executable: $plumaExe"
    }
    if (-not (Test-Path -LiteralPath $uiDir -PathType Container)) {
        New-Item -ItemType Directory -Path $uiDir | Out-Null
    }
    Assert-NoReparseTree -Path $uiDir
    Copy-Item -Path (Join-Path $uiSourceDir '*') -Destination $uiDir -Recurse -Force
    if (-not (Test-Path -LiteralPath $uiExe -PathType Leaf)) {
        throw "WinUI installation did not produce its expected executable: $uiExe"
    }
    foreach ($sourceFile in Get-ChildItem -LiteralPath $uiSourceDir -File -Recurse) {
        $relativeFile = $sourceFile.FullName.Substring(((Get-CanonicalPath -Path $uiSourceDir) + '\').Length)
        $installedFile = Join-Path $uiDir $relativeFile
        if (-not (Test-Path -LiteralPath $installedFile -PathType Leaf) -or
            (Get-FileHash -LiteralPath $sourceFile.FullName -Algorithm SHA256).Hash -ne
            (Get-FileHash -LiteralPath $installedFile -Algorithm SHA256).Hash) {
            throw "Installed WinUI file did not read back with its package hash: $relativeFile"
        }
    }
    $uiExecutableHash = (Get-FileHash -LiteralPath $uiExe -Algorithm SHA256).Hash.ToLowerInvariant()
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
    $manifest.ui_executable_sha256 = $uiExecutableHash
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
        $savedManifest.install_id -ne $installId -or $savedManifest.state -ne 'installed' -or
        (Get-CanonicalPath -Path $savedManifest.ui_directory) -ne (Get-CanonicalPath -Path $uiDir) -or
        (Get-CanonicalPath -Path $savedManifest.ui_executable) -ne (Get-CanonicalPath -Path $uiExe) -or
        $savedManifest.ui_executable_sha256 -ne $uiExecutableHash) {
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

    if (-not (Test-Path -LiteralPath $uiShortcutFolder -PathType Container)) {
        New-Item -ItemType Directory -Path $uiShortcutFolder | Out-Null
    }
    $uiShortcut = $shell.CreateShortcut($uiShortcutPath)
    $uiShortcut.TargetPath = $uiExe
    $uiShortcut.WorkingDirectory = $uiDir
    $uiShortcut.IconLocation = $uiExe
    $uiShortcut.Save()
    $savedUiShortcut = $shell.CreateShortcut($uiShortcutPath)
    if ([string]::IsNullOrWhiteSpace($savedUiShortcut.TargetPath) -or
        (Get-CanonicalPath -Path $savedUiShortcut.TargetPath) -ne (Get-CanonicalPath -Path $uiExe)) {
        throw 'PLUMA UI shortcut did not read back with the expected executable.'
    }

    Write-Host 'PLUMA Core installation verified; resident startup and explicit WinUI launch shortcuts published.' -ForegroundColor Green
} catch {
    Write-Host "PLUMA installation failed: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
