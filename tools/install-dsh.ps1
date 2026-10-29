[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$DshCli,
    [string]$Profile = 'desktop',
    [switch]$CheckOnly
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'dsh-install-common.ps1')
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
$profileRoot = Join-Path $env:USERPROFILE ".dsh\profiles\$Profile"
foreach ($path in @($bundleRoot,$profileRoot)) { Assert-DshPlainPath $path }
$profilePackage = Join-Path $profileRoot 'package.json'
$lockAudit=$null
if (Test-Path -LiteralPath $profilePackage) {
    $profileConfig = Get-Content -LiteralPath $profilePackage -Raw | ConvertFrom-Json
    if ($profileConfig.dependencies -and $profileConfig.dependencies.PSObject.Properties['dsh-mcm-team']) {
        throw 'This profile already registers dsh-mcm-team outside the standard target. Inspect its actual path and plan a separately backed-up migration; a first-time install must not overwrite an unbacked-up registration.'
    }
    $lockAudit=Get-DshLockAudit $profileRoot
    if ($lockAudit.status -ne 'consistent') {
        throw "MCM_PROFILE_LOCK_REPAIR_REQUIRED: Existing profile direct lock audit is $($lockAudit.status). No CLI was called. Review the read-only check-profile-lock.py report and plan dependency repair separately."
    }
} elseif (Test-Path -LiteralPath $profileRoot) {
    if (@(Get-ChildItem -LiteralPath $profileRoot -Force).Count) { throw 'MCM_PROFILE_LOCK_REPAIR_REQUIRED: Existing nonempty profile lacks package.json; inspect its layout before installation.' }
}
$running = Get-Process -Name 'DeepSeek Harness' -ErrorAction SilentlyContinue
if (-not (Get-Command node -ErrorAction SilentlyContinue)) { throw 'Node.js is required for the bundle consistency check.' }
& node (Join-Path $bundleRoot 'src\build.mjs') --check
if ($LASTEXITCODE) { throw 'Bundle consistency check failed.' }
if ($CheckOnly) {
    [pscustomobject]@{source=$bundleRoot;profile=$Profile;installation='first_time';desktop_running=([bool]$running);existing_profile_lock_audit=$lockAudit;new_empty_profile=($null -eq $lockAudit);cli_will_run=$true;changed=$false} | ConvertTo-Json -Depth 10
    return
}
if ($running) { throw 'DSH desktop is still running. Save work and exit it normally first. This script will not stop the application or overwrite a live Host.' }
Invoke-DshProfileCli $cliPath $Profile @('add','--save-exact',"link:$($bundleRoot.Replace('\','/'))")
$version=(Read-DshJson (Join-Path $bundleRoot 'package.json')).version
Write-Output "Official installation command succeeded. Keep this bundle path stable. Start DSH and verify v$version, all 12 MCM presets, and an isolated new-session runtime test before using the captain. Existing paused projects remain paused."
