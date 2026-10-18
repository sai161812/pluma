param([switch]$Export)

$ErrorActionPreference = 'Stop'
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$projectPath = Join-Path $PSScriptRoot 'PLUMA.UI/PLUMA.UI.csproj'

& dotnet build $projectPath -p:Platform=x64 -p:SurfaceGalleryPreview=true --no-restore -v:minimal
if ($LASTEXITCODE -ne 0) { throw 'Preview build failed. Restore PLUMA.UI dependencies before retrying.' }

$previewExe = Join-Path $repositoryRoot 'output/ui-gallery-preview/PLUMA.UI.exe'
$previewArguments = @('--surface-gallery')
if ($Export) {
    $exportDirectory = Join-Path $repositoryRoot 'output/ui-surface-gallery'
    $previewArguments += @('--surface-gallery-export', ('"{0}"' -f $exportDirectory))
}
# A visible window is intentional: this script is explicitly for owner visual review.
$previewProcess = Start-Process -FilePath $previewExe -ArgumentList $previewArguments -WorkingDirectory $repositoryRoot -PassThru
Write-Output "Surface gallery started (PID $($previewProcess.Id)). No backend or microphone is started."
if ($Export) { Write-Output "Preview exports: $exportDirectory/index.html (available after rendering completes)." }
