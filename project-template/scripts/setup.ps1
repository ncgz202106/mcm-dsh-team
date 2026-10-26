param([string]$Python312 = '', [switch]$SkipDependencies)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
if (-not $Python312) {
    $candidates = @()
    if (Get-Command py -ErrorAction SilentlyContinue) {
        $listed = & py -0p 2>&1
        foreach ($line in $listed) {
            if ("$line" -match '3\.12.*?([A-Za-z]:\\.+python\.exe)\s*$') { $candidates += $Matches[1] }
        }
    }
    $uvPython = Join-Path $env:APPDATA 'uv\python'
    if (Test-Path -LiteralPath $uvPython) {
        $candidates += Get-ChildItem -LiteralPath $uvPython -Directory -Filter '*3.12*' | ForEach-Object { Join-Path $_.FullName 'python.exe' }
    }
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate) { $Python312 = $candidate; break }
    }
}
if (-not $Python312) { throw 'Python 3.12 not found. Pass -Python312 C:\path\python.exe after installing it.' }
$version = & $Python312 -c 'import sys; print("%d.%d" % sys.version_info[:2])'
if ($version -ne '3.12') { throw "Expected Python 3.12, found $version" }
$venvRoot = Join-Path $projectRoot '.venv'
$venvPython = Join-Path $venvRoot 'Scripts\python.exe'
if (-not (Test-Path -LiteralPath $venvPython)) { & $Python312 -m venv $venvRoot; if ($LASTEXITCODE) { throw 'venv creation failed' } }
if (-not $SkipDependencies) {
    $requirementsFile = Join-Path $projectRoot 'requirements.lock.txt'
    if (-not (Test-Path -LiteralPath $requirementsFile)) { $requirementsFile = Join-Path $projectRoot 'requirements.txt' }
    & $venvPython -m pip install -r $requirementsFile
    if ($LASTEXITCODE) { throw 'Dependency installation failed' }
}
& $venvPython (Join-Path $PSScriptRoot 'mcm.py') --root $projectRoot doctor
if ($LASTEXITCODE) { throw 'Project doctor failed; inspect the reported dependencies' }
Write-Output "Ready: $venvPython"
