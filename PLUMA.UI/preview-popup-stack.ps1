param([switch]$Audit)
$ErrorActionPreference = 'Stop'
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$projectPath = Join-Path $PSScriptRoot 'PLUMA.UI/PLUMA.UI.csproj'
& dotnet build $projectPath -p:Platform=x64 -p:SurfaceGalleryPreview=true --no-restore -v:minimal
if ($LASTEXITCODE -ne 0) { throw 'Popup preview build failed.' }
$previewExe = Join-Path $repositoryRoot 'output/ui-gallery-preview/PLUMA.UI.exe'
$previewArguments = @('--popup-stack-preview')
if ($Audit) {
    $auditDirectory = Join-Path $repositoryRoot ('output/popup-stack-audit-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
    $previewArguments += @('--popup-stack-audit', ('"{0}"' -f $auditDirectory))
}
# A visible fixture controller and owned popup windows are intentional for this preview.
$previewProcess = Start-Process -FilePath $previewExe -ArgumentList $previewArguments -WorkingDirectory $repositoryRoot -PassThru
Write-Output "Popup preview started (PID $($previewProcess.Id)). No microphone or backend is started."
if ($Audit) { Write-Output "Audit output: $auditDirectory" }
