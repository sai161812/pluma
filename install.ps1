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
$script:InstallTransactionPrepared = $false
$script:InstallTransactionId = $null

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

function Write-JsonAtomically {
    param (
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][object]$Value
    )
    $temporaryPath = "$Path.$([guid]::NewGuid().ToString('N')).tmp"
    $json = ConvertTo-Json -InputObject $Value -Depth 10
    [System.IO.File]::WriteAllText($temporaryPath, $json, [System.Text.UTF8Encoding]::new($false))
    try {
        if (Test-Path -LiteralPath $Path -PathType Leaf) {
            [System.IO.File]::Replace($temporaryPath, $Path, $null)
        } else {
            [System.IO.File]::Move($temporaryPath, $Path)
        }
    } finally {
        if (Test-Path -LiteralPath $temporaryPath -PathType Leaf) {
            Remove-Item -LiteralPath $temporaryPath -Force
        }
    }
}

function Get-InstallTransactionPath {
    param (
        [Parameter(Mandatory = $true)][string]$Root,
        [Parameter(Mandatory = $true)][string]$TransactionId
    )
    if ($TransactionId -notmatch '\A[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\z') {
        throw 'The PLUMA install transaction identifier is malformed.'
    }
    $path = Join-Path $Root ".pluma-upgrade-$TransactionId"
    if (-not (Test-PathWithin -Parent $Root -Child $path)) {
        throw 'The PLUMA install transaction resolved outside its installation directory.'
    }
    return $path
}

function Read-InstallTransaction {
    param (
        [Parameter(Mandatory = $true)][string]$Root,
        [Parameter(Mandatory = $true)][string]$TransactionId
    )
    $transactionPath = Get-InstallTransactionPath -Root $Root -TransactionId $TransactionId
    if (-not (Test-Path -LiteralPath $transactionPath -PathType Container)) {
        return $null
    }
    Assert-NoReparseAncestors -Path $transactionPath
    Assert-NoReparseTree -Path $transactionPath
    $metadataPath = Join-Path $transactionPath 'transaction.json'
    if (-not (Test-Path -LiteralPath $metadataPath -PathType Leaf)) {
        if (@(Get-ChildItem -LiteralPath $transactionPath -Force).Count -eq 0) { return $null }
        throw 'The PLUMA upgrade transaction metadata is missing; recovery stopped without changing files.'
    }
    $metadataItem = Get-Item -LiteralPath $metadataPath -Force
    if (($metadataItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw 'The PLUMA upgrade transaction metadata is a reparse point.'
    }
    $metadata = Get-Content -LiteralPath $metadataPath -Raw | ConvertFrom-Json
    if ($metadata.schema_version -ne 1 -or
        [string]$metadata.transaction_id -ne $TransactionId -or
        (Get-CanonicalPath -Path $metadata.install_root) -ne (Get-CanonicalPath -Path $Root) -or
        $metadata.phase -notin @('prepared', 'restoring', 'restored', 'ready_to_commit')) {
        throw 'The PLUMA upgrade transaction metadata is invalid or names a different installation.'
    }
    return $metadata
}

function Remove-InstallTransactionDirectory {
    param (
        [Parameter(Mandatory = $true)][string]$Root,
        [Parameter(Mandatory = $true)][string]$TransactionId,
        [Parameter(Mandatory = $true)][string]$ExpectedPhase
    )
    $transactionPath = Get-InstallTransactionPath -Root $Root -TransactionId $TransactionId
    if (-not (Test-Path -LiteralPath $transactionPath -PathType Container)) { return }
    $transactionItem = Get-Item -LiteralPath $transactionPath -Force
    if (($transactionItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw 'The PLUMA transaction directory is a reparse point; preserving it.'
    }
    $metadataPath = Join-Path $transactionPath 'transaction.json'
    if (-not (Test-Path -LiteralPath $metadataPath -PathType Leaf)) {
        if (@(Get-ChildItem -LiteralPath $transactionPath -Force).Count -eq 0) {
            Remove-Item -LiteralPath $transactionPath -Force
            return
        }
        throw 'PLUMA transaction metadata is missing while transaction files remain; preserving them.'
    }
    $metadata = Read-InstallTransaction -Root $Root -TransactionId $TransactionId
    if (-not $metadata -or $metadata.phase -ne $ExpectedPhase) {
        throw 'The PLUMA transaction cleanup phase does not match its recorded ownership state.'
    }
    $allowedNames = @('transaction.json', 'previous-install.json', 'venv', 'ui', 'previous-startup.lnk', 'previous-ui.lnk')
    foreach ($child in Get-ChildItem -LiteralPath $transactionPath -Force) {
        if ($child.Name -notin $allowedNames) {
            throw "An unexpected file is present in the PLUMA transaction backup; preserving it: $($child.FullName)"
        }
        if ($child.Name -in @('venv', 'ui')) {
            if ($ExpectedPhase -ne 'ready_to_commit') {
                throw "An application payload remains in a $ExpectedPhase transaction; preserving it: $($child.FullName)"
            }
            Assert-NoReparseTree -Path $child.FullName
            Remove-Item -LiteralPath $child.FullName -Recurse -Force
        } elseif ($child.Name -ne 'transaction.json') {
            if (($child.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0 -or $child.PSIsContainer) {
                throw "A PLUMA transaction record is not a regular file; preserving it: $($child.FullName)"
            }
            Remove-Item -LiteralPath $child.FullName -Force
        }
    }
    Remove-Item -LiteralPath $metadataPath -Force
    if (@(Get-ChildItem -LiteralPath $transactionPath -Force).Count -ne 0) {
        throw 'The PLUMA transaction directory contains unexpected files after cleanup.'
    }
    Remove-Item -LiteralPath $transactionPath -Force
}

function Assert-NoInstallProcesses {
    param ([Parameter(Mandatory = $true)][string]$Root)
    $processes = @(Get-CimInstance -ClassName Win32_Process -Filter "Name='pluma.exe' OR Name='python.exe' OR Name='PLUMA.UI.exe'" -ErrorAction Stop)
    foreach ($process in $processes) {
        if ([string]::IsNullOrWhiteSpace([string]$process.ExecutablePath)) {
            if ($process.Name -in @('pluma.exe', 'python.exe', 'PLUMA.UI.exe')) {
                throw "$($process.Name) PID $($process.ProcessId) has no readable path; recovery refused while ownership is uncertain."
            }
        }
        if (Test-PathWithin -Parent $Root -Child $process.ExecutablePath) {
            throw "A PLUMA installation process is still running (PID $($process.ProcessId)); close it and retry recovery. No process was terminated."
        }
    }
}

function Restore-InstallShortcut {
    param (
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$BackupPath,
        [Parameter(Mandatory = $true)][bool]$HadPrevious,
        [Parameter(Mandatory = $true)][string]$ExpectedTarget
    )
    $parentPath = Split-Path -Parent $Path
    if ($HadPrevious -and -not (Test-Path -LiteralPath $parentPath -PathType Container)) {
        New-Item -ItemType Directory -Path $parentPath | Out-Null
    }
    Assert-NoReparseAncestors -Path $Path
    if (Test-Path -LiteralPath $Path) {
        $item = Get-Item -LiteralPath $Path -Force
        if (-not $item.PSIsContainer -and
            (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0)) {
            throw "Refusing to restore through a reparse-point shortcut: $Path"
        }
        if ($item.PSIsContainer) { throw "A directory now occupies the PLUMA shortcut path; preserving it: $Path" }
        $shell = New-Object -ComObject WScript.Shell
        $current = $shell.CreateShortcut($Path)
        if ([string]::IsNullOrWhiteSpace($current.TargetPath) -or
            (Get-CanonicalPath -Path $current.TargetPath) -ne (Get-CanonicalPath -Path $ExpectedTarget)) {
            Write-Warning "A shortcut changed during PLUMA installation and now belongs to another target; it was preserved: $Path"
            return
        }
    }
    if ($HadPrevious) {
        if (-not (Test-Path -LiteralPath $BackupPath -PathType Leaf)) {
            throw "The original PLUMA shortcut backup is missing: $BackupPath"
        }
        $backupItem = Get-Item -LiteralPath $BackupPath -Force
        if (($backupItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw 'The original PLUMA shortcut backup is a reparse point.'
        }
        Copy-Item -LiteralPath $BackupPath -Destination $Path -Force
    } elseif (Test-Path -LiteralPath $Path -PathType Leaf) {
        Remove-Item -LiteralPath $Path -Force
    }
}

function Restore-InstallTransaction {
    param (
        [Parameter(Mandatory = $true)][string]$Root,
        [Parameter(Mandatory = $true)][string]$ManifestPath,
        [Parameter(Mandatory = $true)][object]$Manifest
    )
    $properties = @($Manifest.PSObject.Properties.Name)
    if ($Manifest.state -ne 'installing' -or $properties -notcontains 'transaction_id' -or
        $properties -notcontains 'had_previous_manifest' -or $properties -notcontains 'had_venv' -or
        $properties -notcontains 'had_ui') {
        throw 'This interrupted installation predates transaction recovery metadata. Files were preserved; do not remove the target manually.'
    }
    $transactionId = [string]$Manifest.transaction_id
    $transactionPath = Get-InstallTransactionPath -Root $Root -TransactionId $transactionId
    $metadata = Read-InstallTransaction -Root $Root -TransactionId $transactionId
    if (-not $metadata -or
        [bool]$metadata.had_previous_manifest -ne [bool]$Manifest.had_previous_manifest -or
        [bool]$metadata.had_venv -ne [bool]$Manifest.had_venv -or
        [bool]$metadata.had_ui -ne [bool]$Manifest.had_ui) {
        throw 'The PLUMA upgrade backup does not match its ownership marker; recovery stopped without deleting files.'
    }
    $metadataProperties = @($metadata.PSObject.Properties.Name)
    if (($metadataProperties -notcontains 'had_startup_shortcut') -or
        ($metadataProperties -notcontains 'had_ui_shortcut') -or
        ($metadataProperties -notcontains 'had_ui_shortcut_folder') -or
        ($metadataProperties -notcontains 'startup_shortcut_path') -or
        ($metadataProperties -notcontains 'ui_shortcut_path')) {
        throw 'The PLUMA upgrade backup lacks shortcut recovery ownership; files were preserved.'
    }
    $startupFolder = [Environment]::GetFolderPath('Startup')
    $programsFolder = [Environment]::GetFolderPath('Programs')
    if ([string]::IsNullOrWhiteSpace($startupFolder) -or [string]::IsNullOrWhiteSpace($programsFolder) -or
        (Get-CanonicalPath -Path $metadata.startup_shortcut_path) -ne
            (Get-CanonicalPath -Path (Join-Path $startupFolder 'PLUMA.lnk')) -or
        (Get-CanonicalPath -Path $metadata.ui_shortcut_path) -ne
            (Get-CanonicalPath -Path (Join-Path (Join-Path $programsFolder 'PLUMA') 'PLUMA UI.lnk'))) {
        throw 'The recorded PLUMA shortcut paths do not match the current-user Windows locations; recovery stopped.'
    }
    Assert-NoInstallProcesses -Root $Root

    $metadata.phase = 'restoring'
    Write-JsonAtomically -Path (Join-Path $transactionPath 'transaction.json') -Value $metadata
    foreach ($payload in @(
        [pscustomobject]@{ Name = 'venv'; HadPrevious = [bool]$metadata.had_venv },
        [pscustomobject]@{ Name = 'ui'; HadPrevious = [bool]$metadata.had_ui }
    )) {
        $destination = Join-Path $Root $payload.Name
        $backup = Join-Path $transactionPath $payload.Name
        if (Test-Path -LiteralPath $backup) {
            Assert-NoReparseTree -Path $backup
            if (Test-Path -LiteralPath $destination) {
                Assert-NoReparseTree -Path $destination
                Remove-Item -LiteralPath $destination -Recurse -Force
            }
            Move-Item -LiteralPath $backup -Destination $destination
        } elseif ($payload.HadPrevious) {
            if (-not (Test-Path -LiteralPath $destination -PathType Container)) {
                throw "The previous PLUMA $($payload.Name) payload is missing from both its install path and recovery backup."
            }
        } elseif (Test-Path -LiteralPath $destination) {
            Assert-NoReparseTree -Path $destination
            Remove-Item -LiteralPath $destination -Recurse -Force
        }
    }

    Restore-InstallShortcut -Path $metadata.startup_shortcut_path `
        -BackupPath (Join-Path $transactionPath 'previous-startup.lnk') `
        -HadPrevious ([bool]$metadata.had_startup_shortcut) `
        -ExpectedTarget (Join-Path (Join-Path $Root 'venv') 'Scripts\pluma.exe')
    Restore-InstallShortcut -Path $metadata.ui_shortcut_path `
        -BackupPath (Join-Path $transactionPath 'previous-ui.lnk') `
        -HadPrevious ([bool]$metadata.had_ui_shortcut) `
        -ExpectedTarget (Join-Path (Join-Path $Root 'ui') 'PLUMA.UI.exe')
    $uiShortcutFolder = Split-Path -Parent $metadata.ui_shortcut_path
    if (-not [bool]$metadata.had_ui_shortcut_folder -and
        (Test-Path -LiteralPath $uiShortcutFolder -PathType Container)) {
        $folderItem = Get-Item -LiteralPath $uiShortcutFolder -Force
        if (($folderItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw 'The PLUMA UI shortcut folder became a reparse point during installation; preserving it.'
        }
        if (@(Get-ChildItem -LiteralPath $uiShortcutFolder -Force).Count -eq 0) {
            Remove-Item -LiteralPath $uiShortcutFolder -Force
        }
    }

    if ([bool]$metadata.had_previous_manifest) {
        $previousManifestPath = Join-Path $transactionPath 'previous-install.json'
        if (-not (Test-Path -LiteralPath $previousManifestPath -PathType Leaf)) {
            throw 'The previous PLUMA ownership marker is missing from the recovery backup.'
        }
        $previousItem = Get-Item -LiteralPath $previousManifestPath -Force
        if (($previousItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw 'The previous PLUMA ownership marker is a reparse point.'
        }
        $previousManifest = Get-Content -LiteralPath $previousManifestPath -Raw | ConvertFrom-Json
        $previousProperties = @($previousManifest.PSObject.Properties.Name)
        $expectedPreviousExe = Get-CanonicalPath -Path (Join-Path $Root 'venv\Scripts\pluma.exe')
        if ($previousManifest.schema_version -ne 1 -or
            $previousManifest.state -notin @('installed', 'application_removed_data_preserved') -or
            $previousProperties -notcontains 'install_id' -or
            [string]::IsNullOrWhiteSpace([string]$previousManifest.install_id) -or
            (Get-CanonicalPath -Path $previousManifest.install_root) -ne $Root -or
            (Get-CanonicalPath -Path $previousManifest.executable) -ne $expectedPreviousExe) {
            throw 'The previous PLUMA ownership marker is invalid or names a different installation; recovery stopped.'
        }
        $metadata.phase = 'restored'
        Write-JsonAtomically -Path (Join-Path $transactionPath 'transaction.json') -Value $metadata
        Write-JsonAtomically -Path $ManifestPath -Value $previousManifest
        Remove-InstallTransactionDirectory -Root $Root -TransactionId $transactionId -ExpectedPhase 'restored'
        Write-Host 'The previous PLUMA installation was restored after the interrupted upgrade.' -ForegroundColor Yellow
        return
    }

    $Manifest.state = 'rolled_back'
    $Manifest.updated_at_utc = [DateTime]::UtcNow.ToString('o')
    $metadata.phase = 'restored'
    Write-JsonAtomically -Path (Join-Path $transactionPath 'transaction.json') -Value $metadata
    Write-JsonAtomically -Path $ManifestPath -Value $Manifest
    Write-Host 'The incomplete first installation was rolled back. Rerun the installer to continue.' -ForegroundColor Yellow
}

function Remove-CompletedInstallTransaction {
    param (
        [Parameter(Mandatory = $true)][string]$Root,
        [Parameter(Mandatory = $true)][object]$Manifest
    )
    $properties = @($Manifest.PSObject.Properties.Name)
    if ($properties -notcontains 'transaction_id' -or -not $Manifest.transaction_id) { return }
    $transactionPath = Get-InstallTransactionPath -Root $Root -TransactionId ([string]$Manifest.transaction_id)
    if (-not (Test-Path -LiteralPath $transactionPath -PathType Container)) { return }
    $metadata = Read-InstallTransaction -Root $Root -TransactionId ([string]$Manifest.transaction_id)
    if (-not $metadata) {
        Remove-InstallTransactionDirectory -Root $Root -TransactionId ([string]$Manifest.transaction_id) -ExpectedPhase 'ready_to_commit'
        return
    }
    if (-not $metadata -or $Manifest.state -ne 'installed' -or $metadata.phase -ne 'ready_to_commit') {
        throw 'An uncommitted PLUMA upgrade backup is present; the installer will not remove it.'
    }
    Remove-InstallTransactionDirectory -Root $Root -TransactionId ([string]$Manifest.transaction_id) -ExpectedPhase 'ready_to_commit'
}

function Resolve-StaleInstallTransactions {
    param (
        [Parameter(Mandatory = $true)][string]$Root,
        [Parameter()][object]$Manifest
    )
    $activeId = if ($Manifest -and $Manifest.transaction_id) { [string]$Manifest.transaction_id } else { '' }
    foreach ($directory in Get-ChildItem -LiteralPath $Root -Directory -Force -Filter '.pluma-upgrade-*' -ErrorAction SilentlyContinue) {
        if ($directory.Name -notmatch '\A\.pluma-upgrade-([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})\z') {
            throw "An unrecognized PLUMA recovery directory is present; preserving it: $($directory.FullName)"
        }
        $transactionId = $Matches[1]
        $metadata = Read-InstallTransaction -Root $Root -TransactionId $transactionId
        if (-not $metadata) {
            Remove-InstallTransactionDirectory -Root $Root -TransactionId $transactionId -ExpectedPhase 'prepared'
            continue
        }
        if ($transactionId -eq $activeId) {
            if ($Manifest.state -eq 'installing') { continue }
            if ($Manifest.state -in @('installed', 'application_removed_data_preserved') -and
                $metadata.phase -eq 'ready_to_commit') {
                Remove-InstallTransactionDirectory -Root $Root -TransactionId $transactionId -ExpectedPhase 'ready_to_commit'
                continue
            }
            if ($Manifest.state -eq 'rolled_back' -and $metadata.phase -eq 'restored') {
                Remove-InstallTransactionDirectory -Root $Root -TransactionId $transactionId -ExpectedPhase 'restored'
                continue
            }
            throw 'The PLUMA ownership marker and recovery transaction disagree; preserving both.'
        }
        if ($metadata.phase -eq 'restored') {
            Remove-InstallTransactionDirectory -Root $Root -TransactionId $transactionId -ExpectedPhase 'restored'
            continue
        }
        if ($metadata.phase -eq 'prepared' -and
            -not (Test-Path -LiteralPath (Join-Path $directory.FullName 'venv')) -and
            -not (Test-Path -LiteralPath (Join-Path $directory.FullName 'ui'))) {
            Remove-InstallTransactionDirectory -Root $Root -TransactionId $transactionId -ExpectedPhase 'prepared'
            continue
        }
        throw "An incomplete PLUMA recovery directory is not linked to the ownership marker; preserving it: $($directory.FullName)"
    }
}

function Complete-RolledBackInstall {
    param (
        [Parameter(Mandatory = $true)][string]$Root,
        [Parameter(Mandatory = $true)][string]$ManifestPath,
        [Parameter(Mandatory = $true)][object]$Manifest
    )
    if ($Manifest.state -ne 'rolled_back' -or -not $Manifest.transaction_id) {
        throw 'The PLUMA rollback marker is invalid; preserving installation files.'
    }
    $transactionPath = Get-InstallTransactionPath -Root $Root -TransactionId ([string]$Manifest.transaction_id)
    $metadata = Read-InstallTransaction -Root $Root -TransactionId ([string]$Manifest.transaction_id)
    if ($metadata -and $metadata.phase -ne 'restored') {
        throw 'The PLUMA first-install rollback is incomplete; preserving files and recovery metadata.'
    }
    if (Test-Path -LiteralPath $transactionPath -PathType Container) {
        Remove-InstallTransactionDirectory -Root $Root -TransactionId ([string]$Manifest.transaction_id) -ExpectedPhase 'restored'
    }
    if (Test-Path -LiteralPath $ManifestPath -PathType Leaf) {
        $marker = Get-Item -LiteralPath $ManifestPath -Force
        if (($marker.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw 'The PLUMA rollback marker is a reparse point; preserving it.'
        }
        Remove-Item -LiteralPath $ManifestPath -Force
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
        $recoveryManifest = $null
        if (Test-Path -LiteralPath $installManifestPath -PathType Leaf) {
            $markerItem = Get-Item -LiteralPath $installManifestPath -Force
            if (($markerItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw 'The existing PLUMA ownership marker is a reparse point.'
            }
            $recoveryManifest = Get-Content -LiteralPath $installManifestPath -Raw | ConvertFrom-Json
            if ($recoveryManifest.state -eq 'installing') {
                Restore-InstallTransaction -Root $targetPath -ManifestPath $installManifestPath -Manifest $recoveryManifest
                $recoveryManifest = Get-Content -LiteralPath $installManifestPath -Raw | ConvertFrom-Json
            }
            if ($recoveryManifest.state -eq 'rolled_back') {
                Complete-RolledBackInstall -Root $targetPath -ManifestPath $installManifestPath -Manifest $recoveryManifest
                $recoveryManifest = $null
            } elseif ($recoveryManifest.state -eq 'installed') {
                Remove-CompletedInstallTransaction -Root $targetPath -Manifest $recoveryManifest
            }
            Resolve-StaleInstallTransactions -Root $targetPath -Manifest $recoveryManifest
        } else {
            Resolve-StaleInstallTransactions -Root $targetPath -Manifest $null
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
    if (Test-Path -LiteralPath $uiShortcutPath -PathType Container) {
        throw "A directory occupies the PLUMA UI shortcut path; it was preserved: $uiShortcutPath"
    }
    $startupFolder = [Environment]::GetFolderPath('Startup')
    if ([string]::IsNullOrWhiteSpace($startupFolder)) {
        throw 'Windows did not provide a Startup folder path; installation was not published.'
    }
    $shortcutPath = Join-Path $startupFolder 'PLUMA.lnk'
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
    if (Test-Path -LiteralPath $shortcutPath -PathType Container) {
        throw "A directory occupies the PLUMA startup shortcut path; it was preserved: $shortcutPath"
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
        transaction_id = ''
        had_previous_manifest = [bool](Test-Path -LiteralPath $installManifestPath -PathType Leaf)
        had_venv = [bool](Test-Path -LiteralPath $venvDir -PathType Container)
        had_ui = [bool](Test-Path -LiteralPath $uiDir -PathType Container)
        state = 'installing'
        updated_at_utc = [DateTime]::UtcNow.ToString('o')
    }
    if ($manifest.had_venv) { Assert-NoReparseTree -Path $venvDir }
    if ($manifest.had_ui) { Assert-NoReparseTree -Path $uiDir }
    $transactionId = [guid]::NewGuid().ToString('D')
    $transactionPath = Get-InstallTransactionPath -Root $targetPath -TransactionId $transactionId
    if (Test-Path -LiteralPath $transactionPath) {
        throw 'A PLUMA recovery transaction path collision occurred; no installation files were changed.'
    }
    New-Item -ItemType Directory -Path $transactionPath | Out-Null
    $script:InstallTransactionId = $transactionId
    $transactionMetadata = [ordered]@{
        schema_version = 1
        transaction_id = $transactionId
        install_root = $targetPath
        had_previous_manifest = [bool]$manifest.had_previous_manifest
        had_venv = [bool]$manifest.had_venv
        had_ui = [bool]$manifest.had_ui
        had_startup_shortcut = [bool](Test-Path -LiteralPath $shortcutPath -PathType Leaf)
        had_ui_shortcut = [bool](Test-Path -LiteralPath $uiShortcutPath -PathType Leaf)
        had_ui_shortcut_folder = [bool](Test-Path -LiteralPath $uiShortcutFolder -PathType Container)
        startup_shortcut_path = $shortcutPath
        ui_shortcut_path = $uiShortcutPath
        phase = 'prepared'
    }
    if ($manifest.had_previous_manifest) {
        Copy-Item -LiteralPath $installManifestPath -Destination (Join-Path $transactionPath 'previous-install.json')
    }
    if ($transactionMetadata.had_startup_shortcut) {
        Copy-Item -LiteralPath $shortcutPath -Destination (Join-Path $transactionPath 'previous-startup.lnk')
    }
    if ($transactionMetadata.had_ui_shortcut) {
        Copy-Item -LiteralPath $uiShortcutPath -Destination (Join-Path $transactionPath 'previous-ui.lnk')
    }
    Write-JsonAtomically -Path (Join-Path $transactionPath 'transaction.json') -Value $transactionMetadata
    $manifest.transaction_id = $transactionId
    Write-JsonAtomically -Path $installManifestPath -Value $manifest
    $script:InstallTransactionPrepared = $true

    if ($manifest.had_venv) { Move-Item -LiteralPath $venvDir -Destination (Join-Path $transactionPath 'venv') }
    if ($manifest.had_ui) { Move-Item -LiteralPath $uiDir -Destination (Join-Path $transactionPath 'ui') }

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

    $transactionMetadata.phase = 'ready_to_commit'
    Write-JsonAtomically -Path (Join-Path $transactionPath 'transaction.json') -Value $transactionMetadata
    $manifest.ui_executable_sha256 = $uiExecutableHash
    $manifest.state = 'installed'
    $manifest.updated_at_utc = [DateTime]::UtcNow.ToString('o')
    Write-JsonAtomically -Path $installManifestPath -Value $manifest
    $savedManifest = Get-Content -LiteralPath $installManifestPath -Raw | ConvertFrom-Json
    if ((Get-CanonicalPath -Path $savedManifest.install_root) -ne $targetPath -or
        $savedManifest.install_id -ne $installId -or $savedManifest.state -ne 'installed' -or
        $savedManifest.transaction_id -ne $transactionId -or
        (Get-CanonicalPath -Path $savedManifest.ui_directory) -ne (Get-CanonicalPath -Path $uiDir) -or
        (Get-CanonicalPath -Path $savedManifest.ui_executable) -ne (Get-CanonicalPath -Path $uiExe) -or
        $savedManifest.ui_executable_sha256 -ne $uiExecutableHash) {
        throw 'Installation ownership marker did not read back with the expected identity.'
    }
    $script:InstallTransactionPrepared = $false
    try {
        Remove-CompletedInstallTransaction -Root $targetPath -Manifest $savedManifest
    } catch {
        Write-Warning "Installation is verified, but the previous owned payload backup remains at '$transactionPath'. Rerun the installer to complete its cleanup. $($_.Exception.Message)"
    }

    Write-Host 'PLUMA Core installation verified; resident startup and explicit WinUI launch shortcuts published.' -ForegroundColor Green
} catch {
    Write-Host "PLUMA installation failed: $($_.Exception.Message)" -ForegroundColor Red
    if ($script:InstallTransactionPrepared -and $script:InstallTransactionId) {
        try {
            if (Test-Path -LiteralPath $installManifestPath -PathType Leaf) {
                $failedManifest = Get-Content -LiteralPath $installManifestPath -Raw | ConvertFrom-Json
                if ($failedManifest.state -eq 'installing') {
                    Restore-InstallTransaction -Root $targetPath -ManifestPath $installManifestPath -Manifest $failedManifest
                    $failedManifest = Get-Content -LiteralPath $installManifestPath -Raw | ConvertFrom-Json
                }
                if ($failedManifest.state -eq 'rolled_back') {
                    Complete-RolledBackInstall -Root $targetPath -ManifestPath $installManifestPath -Manifest $failedManifest
                }
            }
            $script:InstallTransactionPrepared = $false
        } catch {
            Write-Host "Automatic rollback needs recovery on the next installer run: $($_.Exception.Message)" -ForegroundColor Yellow
        }
    }
    exit 1
}
