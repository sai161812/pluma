$ErrorActionPreference = 'Stop'
$sourceRoot = Join-Path $PSScriptRoot 'PLUMA.UI'
[xml]$project = Get-Content -LiteralPath (Join-Path $sourceRoot 'PLUMA.UI.csproj') -Raw -Encoding UTF8
$pages = @($project.SelectNodes('//Page | //ApplicationDefinition'))
$properties = '//@Text | //@Content | //@Header | //@Title | //@Message | //@PrimaryButtonText | //@SecondaryButtonText | //@CloseButtonText'

foreach ($page in $pages) {
    $path = Join-Path $sourceRoot $page.Include
    [xml]$markup = Get-Content -LiteralPath $path -Raw -Encoding UTF8
    foreach ($attribute in $markup.SelectNodes($properties)) {
        $value = $attribute.Value
        if ($value.StartsWith('{')) { continue }
        if ($value.Contains([char]0x005F) -or $value.Contains([char]0x2014)) {
            throw "Visible text contains a forbidden separator: $($page.Include), $($attribute.Name)"
        }
    }
}
Write-Output "PASS $($pages.Count) compiled XAML files have no underscores or em dashes in visible strings."
