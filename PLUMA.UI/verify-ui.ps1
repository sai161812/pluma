#Requires -Version 7.2
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repositoryRoot = Split-Path -Parent $PSScriptRoot
$runDirectory = Join-Path $repositoryRoot ('output/ui-verification/' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + [Guid]::NewGuid().ToString('N').Substring(0, 8))
$null = New-Item -ItemType Directory -Path $runDirectory -Force
$dotnetPath = (Get-Command dotnet -ErrorAction Stop).Source
$summary = [ordered]@{ status = 'running'; commit = (& git -C $repositoryRoot rev-parse HEAD); startedUtc = [DateTimeOffset]::UtcNow.ToString('O'); windows = [Environment]::OSVersion.VersionString; userInteractive = [Environment]::UserInteractive; stage = 'initializing' }

function Start-OwnedProcess([string]$Executable, [string[]]$Arguments, [string]$Label) {
    $info = [Diagnostics.ProcessStartInfo]::new()
    $info.FileName = $Executable
    $info.WorkingDirectory = $repositoryRoot
    $info.UseShellExecute = $false
    $info.CreateNoWindow = $true
    $info.RedirectStandardOutput = $true
    $info.RedirectStandardError = $true
    foreach ($argument in $Arguments) { $info.ArgumentList.Add($argument) }
    $process = [Diagnostics.Process]::new()
    $process.StartInfo = $info
    try { if (-not $process.Start()) { throw "Could not start $Label." } }
    catch { $process.Dispose(); throw }
    $record = [pscustomobject]@{ Process = $process; Id = $process.Id; Created = $process.StartTime.ToUniversalTime(); Executable = [IO.Path]::GetFullPath($Executable); Label = $Label; Out = $process.StandardOutput.ReadToEndAsync(); Err = $process.StandardError.ReadToEndAsync() }
    [pscustomobject]@{ id = $record.Id; createdUtc = $record.Created; executable = $record.Executable; label = $Label } | ConvertTo-Json -Compress | Add-Content (Join-Path $runDirectory 'owned-processes.jsonl')
    return $record
}

function Finish-OwnedProcess($Record) {
    $process = $Record.Process
    try {
        if (-not $process.HasExited) {
            $null = $process.CloseMainWindow()
            if (-not $process.WaitForExit(5000)) {
                $current = Get-Process -Id $Record.Id -ErrorAction SilentlyContinue
                if ($null -eq $current -or $current.StartTime.ToUniversalTime() -ne $Record.Created -or $current.Path -ne $Record.Executable) { throw 'Owned process identity changed; cleanup refused.' }
                $process.Kill($true)
                if (-not $process.WaitForExit(5000)) { throw 'Owned process did not exit after termination.' }
            }
        }
        $Record.Out.GetAwaiter().GetResult() | Set-Content (Join-Path $runDirectory ($Record.Label + '.out.log'))
        $Record.Err.GetAwaiter().GetResult() | Set-Content (Join-Path $runDirectory ($Record.Label + '.err.log'))
    }
    finally { $process.Dispose() }
}

function Invoke-Dotnet([string]$Label, [string[]]$Arguments) {
    $summary.stage = $Label
    Write-Host "Running $Label"
    $record = Start-OwnedProcess $dotnetPath $Arguments $Label
    try {
        if (-not $record.Process.WaitForExit(600000)) { throw "$Label exceeded its ten-minute timeout." }
        if ($record.Process.ExitCode -ne 0) { throw "$Label failed with exit code $($record.Process.ExitCode)." }
    }
    finally { Finish-OwnedProcess $record }
    Get-Content (Join-Path $runDirectory ($Label + '.out.log')) | Write-Host
}

function Assert-Report([string]$Path, [string]$Completion) {
    if (-not (Test-Path -LiteralPath $Path)) { throw "Missing verification report: $Path" }
    $content = Get-Content -LiteralPath $Path -Raw
    if ($content -match '(?m)^FAIL\b' -or $content -notmatch $Completion) { throw "Incomplete or failed verification report: $Path" }
    return $content
}

function Invoke-PreviewAudit([string]$Label, [string[]]$Arguments, [string]$Directory, [string]$Report, [string]$Completion, [string]$ErrorFile) {
    $summary.stage = $Label
    $null = New-Item -ItemType Directory -Path $Directory -Force
    $record = Start-OwnedProcess $script:previewExecutable $Arguments $Label
    try {
        $deadline = [DateTimeOffset]::UtcNow.AddSeconds(150)
        while ([DateTimeOffset]::UtcNow -lt $deadline) {
            if (Test-Path -LiteralPath (Join-Path $Directory $ErrorFile)) { throw (Get-Content (Join-Path $Directory $ErrorFile) -Raw) }
            $reportPath = Join-Path $Directory $Report
            if (Test-Path -LiteralPath $reportPath) {
                $content = Get-Content -LiteralPath $reportPath -Raw
                if ($content -match '(?m)^FAIL\b') { throw "Native assertion failed. See $reportPath" }
                if ($content -match $Completion) { return (Assert-Report $reportPath $Completion) }
            }
            if ($record.Process.HasExited) { throw "$Label exited before completing its report (exit $($record.Process.ExitCode))." }
            Start-Sleep -Milliseconds 250
        }
        throw "$Label did not produce a completed report within 150 seconds."
    }
    finally { Finish-OwnedProcess $record }
}

try {
    Invoke-Dotnet 'popup-layout' @('run', '--project', 'PLUMA.UI/PopupStack.Tests/PopupStack.Tests.csproj', '--verbosity', 'quiet')
    Invoke-Dotnet 'surface-contracts' @('run', '--project', 'PLUMA.UI/SurfaceContracts.Tests/SurfaceContracts.Tests.csproj', '--verbosity', 'quiet')
    Invoke-Dotnet 'audio-visualizer' @('run', '--project', 'PLUMA.UI/AudioVisualizer.Tests/AudioVisualizer.Tests.csproj', '--verbosity', 'quiet')
    Invoke-Dotnet 'core-ipc' @('run', '--project', 'PLUMA.UI/CoreIpc.Tests/CoreIpc.Tests.csproj', '--verbosity', 'quiet', '-p:UseSharedCompilation=false')
    $ipc = Assert-Report (Join-Path $runDirectory 'core-ipc.out.log') '(?m)^\d+ IPC checks passed\.'
    $summary.ipcResult = ($ipc -split '\r?\n' | Where-Object { $_ -match '^\d+ IPC checks passed\.' }) -join ''
    & (Join-Path $PSScriptRoot 'check-surface-copy.ps1')
    $previewDirectory = Join-Path $repositoryRoot 'output/ui-verification-build'
    $outDirectory = $previewDirectory.Replace('\', '/') + '/'
    Invoke-Dotnet 'ui-build' @('build', 'PLUMA.UI/PLUMA.UI/PLUMA.UI.csproj', '-p:Platform=x64', '-p:SurfaceGalleryPreview=true', "-p:OutDir=$outDirectory", '-v:minimal', '-nr:false', '-p:UseSharedCompilation=false')
    Invoke-Dotnet 'controls-build' @('build', 'PLUMA.UI/SurfaceControls.Tests/SurfaceControls.Tests.csproj', '-p:Platform=x64', '-v:minimal', '-nr:false', '-p:UseSharedCompilation=false')
    $script:previewExecutable = Join-Path $previewDirectory 'PLUMA.UI.exe'
    $summary.executableSha256 = (Get-FileHash -LiteralPath $previewExecutable -Algorithm SHA256).Hash
    $summary.signature = (Get-AuthenticodeSignature -LiteralPath $previewExecutable).Status.ToString()

    $popupDirectory = Join-Path $runDirectory 'popup-stack'
    $popupReport = Invoke-PreviewAudit 'native-popup' @('--popup-stack-audit', $popupDirectory) $popupDirectory 'popup-stack-audit.txt' '(?m)^\d+ native popup checks passed\.' 'audit-error.txt'
    if (@(Get-ChildItem $popupDirectory -Filter 'surface-*-dark.png').Count -ne 15) { throw 'Expected 15 native popup fixture renders.' }
    $summary.popupResult = ($popupReport -split '\r?\n' | Where-Object { $_ -match '^\d+ native popup checks passed\.' }) -join ''

    $galleryDirectory = Join-Path $runDirectory 'gallery'
    $null = Invoke-PreviewAudit 'native-gallery' @('--surface-gallery', '--surface-gallery-export', $galleryDirectory) $galleryDirectory 'gallery-report.txt' '26 dark component renders exported\. Formatting audit passed' 'export-error.txt'
    $formatting = Assert-Report (Join-Path $galleryDirectory 'formatting-checks.txt') '(?m)^\d+ formatting checks passed\.'
    if (@(Get-ChildItem $galleryDirectory -Filter 'surface-*-dark.png').Count -ne 26) { throw 'Expected 26 native gallery renders.' }
    $summary.formattingResult = ($formatting -split '\r?\n' | Where-Object { $_ -match '^\d+ formatting checks passed\.' }) -join ''

    $summary.stage = 'native-controls'
    $controlsExecutable = Join-Path $repositoryRoot 'PLUMA.UI/SurfaceControls.Tests/bin/x64/Debug/net8.0-windows10.0.19041.0/win-x64/SurfaceControls.Tests.exe'
    $controls = Start-OwnedProcess $controlsExecutable @() 'native-controls'
    try {
        if (-not $controls.Process.WaitForExit(45000)) { throw 'Native control checks exceeded 45 seconds.' }
        if ($controls.Process.ExitCode -ne 0) { throw "Native control runner failed with exit code $($controls.Process.ExitCode)." }
    }
    finally {
        Finish-OwnedProcess $controls
        $controlsLog = Join-Path (Split-Path $controlsExecutable -Parent) 'control-tests.txt'
        if (Test-Path $controlsLog) { Copy-Item -LiteralPath $controlsLog -Destination (Join-Path $runDirectory 'control-tests.txt') }
    }
    $controlReport = Assert-Report (Join-Path $runDirectory 'control-tests.txt') '(?m)^\d+ UI checks passed\.'
    $summary.controlsResult = ($controlReport -split '\r?\n' | Where-Object { $_ -match '^\d+ UI checks passed\.' }) -join ''
    $summary.status = 'passed'
    $summary.stage = 'complete'
    Write-Host 'Native popup, gallery formatting and control checks passed. Physical Windows 11 taskbar/DPI/accessibility review remains separate.'
}
catch {
    $summary.status = 'failed'
    $summary.error = $_.Exception.Message
    $_ | Out-String | Set-Content (Join-Path $runDirectory 'verification-error.txt')
    throw
}
finally {
    $summary.finishedUtc = [DateTimeOffset]::UtcNow.ToString('O')
    $summary | ConvertTo-Json -Depth 5 | Set-Content (Join-Path $runDirectory 'verification-summary.json')
    Write-Host "Verification artifacts: $runDirectory"
}
