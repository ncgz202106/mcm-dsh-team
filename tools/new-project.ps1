param([Parameter(Mandatory=$true)][string]$Destination)
$ErrorActionPreference = 'Stop'
$packageRoot = Split-Path -Parent $PSScriptRoot
$sourceRoot = (Resolve-Path -LiteralPath (Join-Path $packageRoot 'project-template')).Path
$targetRoot = [IO.Path]::GetFullPath($Destination)
if (Test-Path -LiteralPath $targetRoot) { throw "Destination already exists; choose a new directory: $targetRoot" }
New-Item -ItemType Directory -Path $targetRoot | Out-Null
Get-ChildItem -LiteralPath $sourceRoot -Force | Where-Object { $_.Name -notin @('.venv','build','__pycache__') } | ForEach-Object {
    Copy-Item -LiteralPath $_.FullName -Destination $targetRoot -Recurse
}
foreach ($relative in @('input\problem','input\attachments','data\raw','data\processed','models','tasks','drafts','audit','logs')) {
    New-Item -ItemType Directory -Force -Path (Join-Path $targetRoot $relative) | Out-Null
}
Write-Output "New project created: $targetRoot"
Write-Output 'Read AGENTS.md, prepare the environment with scripts/setup.ps1, then start a captain session with this project root.'
