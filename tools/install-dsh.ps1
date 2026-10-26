[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$DshCli,
    [string]$Profile = 'desktop',
    [switch]$CheckOnly
)
$ErrorActionPreference = 'Stop'
$packageRoot = Split-Path -Parent $PSScriptRoot
$bundleRoot = (Resolve-Path -LiteralPath (Join-Path $packageRoot 'bundle')).Path
$cliPath = (Resolve-Path -LiteralPath $DshCli).Path
$installedRoot = Join-Path $env:USERPROFILE '.dsh\plugins\dsh-mcm-team'
if ($Profile -notmatch '^[a-zA-Z0-9_-]+$') { throw 'Invalid profile name.' }
# Existing canonical installs use the backup/rollback updater; preserve the old invocation.
if (Test-Path -LiteralPath $installedRoot) {
    & (Join-Path $PSScriptRoot 'update-dsh.ps1') -DshCli $cliPath -Profile $Profile -PluginRoot $installedRoot -CheckOnly:$CheckOnly
    return
}
$profilePackage = Join-Path $env:USERPROFILE ".dsh\profiles\$Profile\package.json"
if (Test-Path -LiteralPath $profilePackage) {
    $profileConfig = Get-Content -LiteralPath $profilePackage -Raw | ConvertFrom-Json
    if ($profileConfig.dependencies -and $profileConfig.dependencies.PSObject.Properties['dsh-mcm-team']) {
        throw 'This profile already registers dsh-mcm-team outside the standard target. Inspect its actual path and use update-dsh.ps1 -PluginRoot with that path; a first-time install must not overwrite an unbacked-up registration.'
    }
}
$running = Get-Process -Name 'DeepSeek Harness' -ErrorAction SilentlyContinue
if (-not (Get-Command node -ErrorAction SilentlyContinue)) { throw 'Node.js is required for the bundle consistency check.' }
& node (Join-Path $bundleRoot 'src\build.mjs') --check
if ($LASTEXITCODE) { throw 'Bundle consistency check failed.' }
if ($CheckOnly) {
    [pscustomobject]@{source=$bundleRoot;profile=$Profile;installation='first_time';desktop_running=([bool]$running);changed=$false} | ConvertTo-Json
    return
}
if ($running) { throw 'DSH desktop is still running. Save work and exit it normally first. This script will not stop the application or overwrite a live Host.' }
& $cliPath plugin --profile $Profile add --save-exact "link:$($bundleRoot.Replace('\','/'))"
if ($LASTEXITCODE) { throw 'DSH plugin installation failed. Inspect the CLI output; do not assume the presets are active.' }
Write-Output 'Official installation command succeeded. Keep this bundle path stable. Start DSH and verify v0.2.0, all 12 MCM presets, and an isolated new-session runtime test before using the captain. Existing paused projects remain paused.'
