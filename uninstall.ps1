<#
.SYNOPSIS
    Removes the current-user PLUMA installation without touching unrelated apps.
.DESCRIPTION
    Running PLUMA processes must be closed by the user first. The script never
    terminates processes by name. User data is preserved unless -PurgeData is
    supplied and the exact canonical target path is typed at the prompt.
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
    if ($manifest.schema_version -ne 1 -or
        (Get-CanonicalPath -Path $manifest.install_root) -ne $targetPath) {
        throw 'The PLUMA ownership marker is invalid or names a different install path.'
    }
    $expectedExe = Get-CanonicalPath -Path (Join-Path $targetPath 'venv\Scripts\pluma.exe')
    if ((Get-CanonicalPath -Path $manifest.executable) -ne $expectedExe) {
        throw 'The PLUMA ownership marker executable does not match the selected install path.'
    }

    $processes = Get-CimInstance -ClassName Win32_Process -Filter "Name='pluma.exe' OR Name='python.exe'" -ErrorAction Stop
    $ownedPathProcesses = @(
        foreach ($process in $processes) {
            if ([string]::IsNullOrWhiteSpace([string]$process.ExecutablePath)) { continue }
            $executablePath = Get-CanonicalPath -Path $process.ExecutablePath
            if (($executablePath -eq $expectedExe) -or
                (Test-PathWithin -Parent (Join-Path $targetPath 'venv\Scripts') -Child $executablePath)) {
                [pscustomobject]@{
                    ProcessId = $process.ProcessId
                    Name = $process.Name
                    ExecutablePath = $executablePath
                    CreationDate = $process.CreationDate
                }
            }
        }
    )
    if ($ownedPathProcesses.Count -gt 0) {
        $ids = ($ownedPathProcesses | ForEach-Object { $_.ProcessId }) -join ', '
        throw "PLUMA-owned installation processes are still running (PID $ids). Close PLUMA and retry. No process was terminated."
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
        Write-Host "Removed PLUMA's virtual environment. User data was preserved at $targetPath." -ForegroundColor Yellow
    }
} catch {
    Write-Host "PLUMA uninstall stopped safely: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
