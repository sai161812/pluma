<#
.SYNOPSIS
    Removes the current-user PLUMA installation without touching unrelated apps.
.DESCRIPTION
    The script requests authenticated graceful shutdown from the exact owned
    Core and waits for its verified exit. An open WinUI shell must be closed by
    the user; the script never terminates processes by name. User data is
    preserved unless -PurgeData is supplied and the exact canonical target path
    is typed at the prompt.
#>

[CmdletBinding()]
param (
    [string]$TargetDir = (Join-Path $env:LOCALAPPDATA 'PLUMA'),
    [switch]$PurgeData
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

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

function Test-PathWithin {
    param (
        [Parameter(Mandatory = $true)][string]$Parent,
        [Parameter(Mandatory = $true)][string]$Child
    )
    $parentCanonical = (Get-CanonicalPath -Path $Parent) + '\'
    $childCanonical = Get-CanonicalPath -Path $Child
    return $childCanonical.StartsWith($parentCanonical, [System.StringComparison]::OrdinalIgnoreCase)
}

function Assert-NoReparsePoints {
    param ([Parameter(Mandatory = $true)][string]$Path)
    $pending = [System.Collections.Generic.Stack[string]]::new()
    $pending.Push($Path)
    while ($pending.Count -gt 0) {
        $current = $pending.Pop()
        foreach ($item in Get-ChildItem -LiteralPath $current -Force -ErrorAction Stop) {
            if (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw "Refusing recursive removal through reparse point: $($item.FullName)"
            }
            if ($item.PSIsContainer) {
                $pending.Push($item.FullName)
            }
        }
    }
}

try {
    $targetPath = Get-CanonicalPath -Path $TargetDir
    Assert-NoReparseAncestors -Path $targetPath
    $targetRoot = [System.IO.Path]::GetPathRoot($targetPath).TrimEnd('\')
    if ([string]::IsNullOrWhiteSpace($targetPath) -or $targetPath -eq $targetRoot) {
        throw "Refusing unsafe uninstall target: $targetPath"
    }
    if (-not (Test-Path -LiteralPath $targetPath -PathType Container)) {
        throw "PLUMA install directory was not found: $targetPath"
    }
    $targetItem = Get-Item -LiteralPath $targetPath -Force
    if (($targetItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "Refusing an installation directory that is a reparse point: $targetPath"
    }

    $markerPath = Join-Path $targetPath '.pluma-install.json'
    if (-not (Test-Path -LiteralPath $markerPath -PathType Leaf)) {
        throw "No PLUMA ownership marker was found at $markerPath; no files or startup settings were changed."
    }
    $markerItem = Get-Item -LiteralPath $markerPath -Force
    if (($markerItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw 'The PLUMA ownership marker is a reparse point; refusing uninstall.'
    }
    $manifest = Get-Content -LiteralPath $markerPath -Raw | ConvertFrom-Json
    $manifestProperties = @($manifest.PSObject.Properties.Name)
    if ($manifest.schema_version -ne 1 -or
        (Get-CanonicalPath -Path $manifest.install_root) -ne $targetPath) {
        throw 'The PLUMA ownership marker is invalid or names a different install path.'
    }
    $venvPath = Join-Path $targetPath 'venv'
    $venvPython = Get-CanonicalPath -Path (Join-Path $venvPath 'Scripts\python.exe')
    $expectedExe = Get-CanonicalPath -Path (Join-Path $venvPath 'Scripts\pluma.exe')
    if ((Get-CanonicalPath -Path $manifest.executable) -ne $expectedExe) {
        throw 'The PLUMA ownership marker executable does not match the selected install path.'
    }
    if ($manifestProperties -contains 'venv_python' -and $manifest.venv_python -and
        (Get-CanonicalPath -Path $manifest.venv_python) -ne $venvPython) {
        throw 'The PLUMA ownership marker Python does not match the selected install path.'
    }

    $uiDir = Join-Path $targetPath 'ui'
    $expectedUiExe = Get-CanonicalPath -Path (Join-Path $uiDir 'PLUMA.UI.exe')
    $expectedUiShortcutFolder = Join-Path ([Environment]::GetFolderPath('Programs')) 'PLUMA'
    $expectedUiShortcut = Join-Path $expectedUiShortcutFolder 'PLUMA UI.lnk'
    $uiIsOwned = $false
    $hasUiDirectory = $manifestProperties -contains 'ui_directory'
    $hasUiExecutable = $manifestProperties -contains 'ui_executable'
    if (($hasUiDirectory -and $manifest.ui_directory) -or ($hasUiExecutable -and $manifest.ui_executable)) {
        if (-not $hasUiDirectory -or -not $hasUiExecutable -or -not $manifest.ui_directory -or -not $manifest.ui_executable -or
            (Get-CanonicalPath -Path $manifest.ui_directory) -ne (Get-CanonicalPath -Path $uiDir) -or
            (Get-CanonicalPath -Path $manifest.ui_executable) -ne $expectedUiExe) {
            throw 'The PLUMA UI ownership marker does not match the selected install path.'
        }
        $uiIsOwned = $true
        if (($manifestProperties -contains 'ui_shortcut') -and $manifest.ui_shortcut -and
            (Get-CanonicalPath -Path $manifest.ui_shortcut) -ne (Get-CanonicalPath -Path $expectedUiShortcut)) {
            throw 'The PLUMA UI shortcut marker does not match the current-user Start Menu location.'
        }
    }
    if (Test-Path -LiteralPath $uiDir -PathType Container) {
        $uiItem = Get-Item -LiteralPath $uiDir -Force
        if (($uiItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw 'The PLUMA UI directory is a reparse point; refusing uninstall.'
        }
        if ($uiIsOwned) { Assert-NoReparsePoints -Path $uiDir }
    }

    $processes = Get-CimInstance -ClassName Win32_Process -Filter "Name='pluma.exe' OR Name='python.exe' OR Name='PLUMA.UI.exe'" -ErrorAction Stop
    $runningUi = @(
        foreach ($process in $processes) {
            if ($process.Name -ne 'PLUMA.UI.exe') { continue }
            if ([string]::IsNullOrWhiteSpace([string]$process.ExecutablePath)) {
                throw "PLUMA.UI.exe PID $($process.ProcessId) has no readable path; refusing uninstall while ownership is uncertain."
            }
            if ($uiIsOwned -and (Get-CanonicalPath -Path $process.ExecutablePath) -eq $expectedUiExe) { $process }
        }
    )
    if ($runningUi.Count -gt 0) {
        throw "PLUMA UI is running (PID $($runningUi[0].ProcessId)). Close the UI and retry; no process was terminated."
    }
    $ownedPathProcesses = @(
        foreach ($process in $processes) {
            if ([string]::IsNullOrWhiteSpace([string]$process.ExecutablePath)) {
                if ($process.Name -eq 'pluma.exe') { throw "pluma.exe PID $($process.ProcessId) has no readable path; refusing uninstall while ownership is uncertain." }
                continue
            }
            $executablePath = Get-CanonicalPath -Path $process.ExecutablePath
            if (($executablePath -eq $expectedExe) -or
                (Test-PathWithin -Parent $targetPath -Child $executablePath)) {
                [pscustomobject]@{
                    ProcessId = $process.ProcessId
                    Name = $process.Name
                    ExecutablePath = $executablePath
                    CreationDate = $process.CreationDate
                }
            }
        }
    )
    $coreProcesses = @($ownedPathProcesses | Where-Object { $_.ExecutablePath -eq $expectedExe })
    $scriptsDir = Join-Path $venvPath 'Scripts'
    $venvProcesses = @($ownedPathProcesses | Where-Object {
        Test-PathWithin -Parent $scriptsDir -Child $_.ExecutablePath
    })
    $otherInstallProcesses = @($ownedPathProcesses | Where-Object {
        $_.ExecutablePath -ne $expectedExe -and
        -not (Test-PathWithin -Parent $scriptsDir -Child $_.ExecutablePath)
    })
    if ($otherInstallProcesses.Count -gt 0) {
        $ids = ($otherInstallProcesses | ForEach-Object { $_.ProcessId }) -join ', '
        throw "Processes are running from the selected PLUMA installation outside its Core environment (PID $ids); close them and retry."
    }
    if ($coreProcesses.Count -gt 1) {
        throw 'More than one process matches the installed PLUMA Core executable; no process was terminated.'
    }
    if ($coreProcesses.Count -eq 0 -and $venvProcesses.Count -gt 0) {
        $ids = ($venvProcesses | ForEach-Object { $_.ProcessId }) -join ', '
        throw "PLUMA environment processes are running without an authenticated Core host (PID $ids); close them and retry."
    }
    if ($coreProcesses.Count -eq 1) {
        if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) {
            throw 'The installed Core is running but its marked Python shutdown helper is missing.'
        }
        $shutdownScript = 'import sys; from pluma.core.host import request_owned_core_shutdown; request_owned_core_shutdown(int(sys.argv[1]), sys.argv[2], sys.argv[3])'
        & $venvPython -c $shutdownScript ([string]$coreProcesses[0].ProcessId) $targetPath $expectedExe
        $shutdownExitCode = $LASTEXITCODE
        if ($shutdownExitCode -ne 0) {
            throw "Authenticated graceful Core shutdown failed with exit code ${shutdownExitCode}; installation data was preserved."
        }
    }
    $afterShutdown = Get-CimInstance -ClassName Win32_Process -Filter "Name='pluma.exe' OR Name='python.exe'" -ErrorAction Stop
    $remainingOwned = @(
        foreach ($process in $afterShutdown) {
            if ([string]::IsNullOrWhiteSpace([string]$process.ExecutablePath)) {
                if ($process.Name -eq 'pluma.exe') { throw 'A pluma.exe process remains with unreadable identity after shutdown.' }
                continue
            }
            $executablePath = Get-CanonicalPath -Path $process.ExecutablePath
            if (Test-PathWithin -Parent $targetPath -Child $executablePath) { $process }
        }
    )
    if ($remainingOwned.Count -gt 0) {
        $ids = ($remainingOwned | ForEach-Object { $_.ProcessId }) -join ', '
        throw "PLUMA-owned processes remain after graceful Core shutdown (PID $ids). No process was terminated."
    }

    if ($PurgeData) {
        $confirmation = Read-Host "Type the full path '$targetPath' to permanently remove this installation and its user data"
        if (-not [string]::Equals($confirmation, $targetPath, [System.StringComparison]::OrdinalIgnoreCase)) {
            throw 'Purge confirmation did not match; all PLUMA files and startup settings were preserved.'
        }
        Assert-NoReparsePoints -Path $targetPath
    } else {
        $venvPath = Join-Path $targetPath 'venv'
        if (Test-Path -LiteralPath $venvPath) {
            if (-not (Test-PathWithin -Parent $targetPath -Child $venvPath)) {
                throw 'Resolved virtual environment path is outside the owned PLUMA directory.'
            }
            $venvItem = Get-Item -LiteralPath $venvPath -Force
            if (($venvItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw 'The virtual environment is a reparse point; refusing recursive removal.'
            }
            Assert-NoReparsePoints -Path $venvPath
        }
        if ($uiIsOwned -and (Test-Path -LiteralPath $uiDir)) {
            if (-not (Test-PathWithin -Parent $targetPath -Child $uiDir)) {
                throw 'Resolved WinUI path is outside the owned PLUMA directory.'
            }
            Assert-NoReparsePoints -Path $uiDir
        }
    }

    $startupFolder = [Environment]::GetFolderPath('Startup')
    if (-not [string]::IsNullOrWhiteSpace($startupFolder)) {
        $shortcutPath = Join-Path $startupFolder 'PLUMA.lnk'
        Assert-NoReparseAncestors -Path $shortcutPath
        if (Test-Path -LiteralPath $shortcutPath -PathType Leaf) {
            $shortcutItem = Get-Item -LiteralPath $shortcutPath -Force
            if (($shortcutItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
                Write-Host "Preserved $shortcutPath because it is a reparse point."
                $shortcut = $null
            } else {
                $shell = New-Object -ComObject WScript.Shell
                $shortcut = $shell.CreateShortcut($shortcutPath)
                if (-not [string]::IsNullOrWhiteSpace($shortcut.TargetPath) -and
                    (Get-CanonicalPath -Path $shortcut.TargetPath) -eq $expectedExe) {
                    Remove-Item -LiteralPath $shortcutPath -Force
                    if (Test-Path -LiteralPath $shortcutPath) {
                        throw 'The owned startup shortcut remained after removal.'
                    }
                    Write-Host 'Removed the startup shortcut owned by this PLUMA installation.'
                } else {
                    Write-Host "Preserved $shortcutPath because it points to another target."
                }
            }
        }
    }

    if ($uiIsOwned -and (Test-Path -LiteralPath $expectedUiShortcut -PathType Leaf)) {
        Assert-NoReparseAncestors -Path $expectedUiShortcut
        $uiShortcutItem = Get-Item -LiteralPath $expectedUiShortcut -Force
        if (($uiShortcutItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
            Write-Host "Preserved $expectedUiShortcut because it is a reparse point."
        } else {
            $shell = New-Object -ComObject WScript.Shell
            $uiShortcut = $shell.CreateShortcut($expectedUiShortcut)
            if (-not [string]::IsNullOrWhiteSpace($uiShortcut.TargetPath) -and
                (Get-CanonicalPath -Path $uiShortcut.TargetPath) -eq $expectedUiExe) {
                Remove-Item -LiteralPath $expectedUiShortcut -Force
                if (Test-Path -LiteralPath $expectedUiShortcut) {
                    throw 'The owned PLUMA UI shortcut remained after removal.'
                }
                $shortcutFolderItem = Get-Item -LiteralPath $expectedUiShortcutFolder -Force -ErrorAction SilentlyContinue
                if ($shortcutFolderItem -and $shortcutFolderItem.PSIsContainer -and
                    @(Get-ChildItem -LiteralPath $expectedUiShortcutFolder -Force).Count -eq 0) {
                    Remove-Item -LiteralPath $expectedUiShortcutFolder -Force
                }
            } else {
                Write-Host "Preserved $expectedUiShortcut because it points to another target."
            }
        }
    }

    if ($PurgeData) {
        Remove-Item -LiteralPath $targetPath -Recurse -Force
        if (Test-Path -LiteralPath $targetPath) {
            throw 'PLUMA target remained after the confirmed purge.'
        }
        Write-Host "Removed the owned PLUMA directory and its data: $targetPath" -ForegroundColor Yellow
    } else {
        $venvPath = Join-Path $targetPath 'venv'
        if (Test-Path -LiteralPath $venvPath) {
            Remove-Item -LiteralPath $venvPath -Recurse -Force
            if (Test-Path -LiteralPath $venvPath) {
                throw 'PLUMA virtual environment remained after removal.'
            }
        }
        if ($uiIsOwned -and (Test-Path -LiteralPath $uiDir)) {
            Remove-Item -LiteralPath $uiDir -Recurse -Force
            if (Test-Path -LiteralPath $uiDir) {
                throw 'PLUMA WinUI application files remained after removal.'
            }
        }
        $manifest.state = 'application_removed_data_preserved'
        $manifest.removed_at_utc = [DateTime]::UtcNow.ToString('o')
        $manifestTemp = "$markerPath.$([guid]::NewGuid().ToString('N')).tmp"
        [System.IO.File]::WriteAllText(
            $manifestTemp,
            ($manifest | ConvertTo-Json -Depth 4),
            [System.Text.UTF8Encoding]::new($false)
        )
        Move-Item -LiteralPath $manifestTemp -Destination $markerPath -Force
        $savedManifest = Get-Content -LiteralPath $markerPath -Raw | ConvertFrom-Json
        if ($savedManifest.state -ne 'application_removed_data_preserved') {
            throw 'Uninstall state marker did not read back with the expected state.'
        }
        Write-Host "Removed PLUMA's Core and UI application files. User data was preserved at $targetPath." -ForegroundColor Yellow
    }
} catch {
    Write-Host "PLUMA uninstall stopped safely: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
