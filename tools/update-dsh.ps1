[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$DshCli,
    [string]$PluginRoot = (Join-Path $env:USERPROFILE '.dsh\plugins\dsh-mcm-team'),
    [string]$Profile = 'desktop',
    [string]$BackupRoot,
    [switch]$CheckOnly
)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'dsh-install-common.ps1')
$kitRoot=Split-Path -Parent $PSScriptRoot
$sourceRoot=(Resolve-Path -LiteralPath (Join-Path $kitRoot 'bundle')).Path
$cliPath=(Resolve-Path -LiteralPath $DshCli).Path
$pluginAbsolute=Get-AbsoluteDshPath $PluginRoot
$pluginParent=Get-AbsoluteDshPath (Join-Path $env:USERPROFILE '.dsh/plugins')
if ($pluginAbsolute -ne (Join-Path $pluginParent 'dsh-mcm-team')) { throw 'Upgrade target must be the current user named .dsh/plugins/dsh-mcm-team directory.' }
if ($Profile -notmatch '^[a-zA-Z0-9_-]+$') { throw 'Invalid profile name.' }
$profileRoot=Join-Path (Join-Path $env:USERPROFILE '.dsh/profiles') $Profile
foreach ($p in @($sourceRoot,$pluginAbsolute,$profileRoot)) { Assert-DshPlainPath $p }
if (-not (Test-Path -LiteralPath (Join-Path $profileRoot 'package.json'))) { throw 'Existing DSH profile not found; this is an upgrade, not first-time installation.' }
if (-not (Test-Path -LiteralPath (Join-Path $pluginAbsolute 'package.json'))) { throw 'Installed MCM plugin is missing.' }
$package=Read-DshJson (Join-Path $sourceRoot 'package.json')
$installedBefore=Read-DshJson (Join-Path $pluginAbsolute 'package.json')
if ($package.name -ne 'dsh-mcm-team' -or $package.version -ne '0.2.2' -or $installedBefore.name -ne 'dsh-mcm-team') { throw 'Unexpected source/installed package identity.' }
& node (Join-Path $sourceRoot 'src/build.mjs') --check
if ($LASTEXITCODE) { throw 'Generated preset configuration is not current.' }
$before=Read-DshJson (Join-Path $profileRoot 'package.json')
Assert-DshUnrelatedPackage $before $before
if (-not $before.dependencies['dsh-mcm-team']) { throw 'Expected an existing MCM profile dependency.' }
Assert-DshResolvedPlugin $profileRoot $pluginAbsolute
if (-not $BackupRoot) { $BackupRoot=Join-Path (Split-Path -Parent (Split-Path -Parent $kitRoot)) 'work/v020-install-backups' }
$stamp=Get-Date -Format 'yyyyMMdd-HHmmss-fff'
$backup=Join-Path (Get-AbsoluteDshPath $BackupRoot) $stamp
Assert-DshPlainPath $backup
foreach ($p in @($sourceRoot,$pluginAbsolute,$profileRoot)) { Assert-DshDisjoint $backup $p }
$active=@(Get-Process -Name 'DeepSeek Harness' -ErrorAction SilentlyContinue)
if ($CheckOnly) {
    [pscustomobject]@{version=$package.version;source=$sourceRoot;target=$pluginAbsolute;profile=$Profile;backup_parent=(Get-AbsoluteDshPath $BackupRoot);desktop_running=($active.Count -gt 0);requires_normal_exit=($active.Count -gt 0);changed=$false} | ConvertTo-Json
    return
}
Assert-DshClosed
$stage=Join-Path $pluginParent "dsh-mcm-team.next-$stamp"
$retired=Join-Path $pluginParent "dsh-mcm-team.previous-$stamp"
$failed=Join-Path $pluginParent "dsh-mcm-team.failed-$stamp"
foreach ($p in @($stage,$retired,$failed)) {
    if ((Split-Path -Parent (Get-AbsoluteDshPath $p)) -ne $pluginParent -or (Test-Path -LiteralPath $p)) { throw 'Unsafe or existing staging/rollback path.' }
}
if (Test-Path -LiteralPath $backup) { throw 'Backup already exists.' }
$pluginHashes=Get-DshTreeHashes $pluginAbsolute
$sourceHashes=Get-DshTreeHashes $sourceRoot
$profileState=Get-DshProfileState $profileRoot
$unrelatedRuntime=Get-DshUnrelatedRuntime $profileRoot $before
New-Item -ItemType Directory -Path $backup | Out-Null
Copy-Item -LiteralPath $pluginAbsolute -Destination (Join-Path $backup 'plugin') -Recurse
$profileBackup=Join-Path $backup 'profile';New-Item -ItemType Directory -Path $profileBackup | Out-Null
foreach ($name in $DshProfileFiles) { if ($profileState[$name]) { Copy-Item -LiteralPath (Join-Path $profileRoot $name) -Destination (Join-Path $profileBackup $name) } }
$receipt=[ordered]@{format_version=2;started_at=[DateTimeOffset]::UtcNow.ToString('o');status='backed_up';source=$sourceRoot;target=$pluginAbsolute;profile=$Profile;profile_root=$profileRoot;backup=$backup;retired=$retired;cli_path=$cliPath;old_version=$installedBefore.version;new_version=$package.version;plugin_hashes_before=$pluginHashes;source_hashes=$sourceHashes;profile_state_before=$profileState;unrelated_runtime_before=$unrelatedRuntime;original_rehearsal_resumed=$false}
$receiptPath=Join-Path $backup 'installation.json'
Save-DshReceipt $receiptPath $receipt
Assert-DshBackup $backup $receipt
$swapped=$false;$cliAttempted=$false
try {
    Copy-Item -LiteralPath $sourceRoot -Destination $stage -Recurse
    Assert-DshTreeHashes $stage $sourceHashes
    # A user may have reopened the app during backup; check again before switching.
    Assert-DshClosed
    Assert-DshTreeHashes $pluginAbsolute $pluginHashes
    Assert-DshProfileState $profileRoot $profileState
    Move-Item -LiteralPath $pluginAbsolute -Destination $retired
    $swapped=$true
    Move-Item -LiteralPath $stage -Destination $pluginAbsolute
    $cliAttempted=$true
    Invoke-DshProfileCli $cliPath $Profile @('add','--save-exact',"link:$($pluginAbsolute.Replace('\','/'))")
    $after=Read-DshJson (Join-Path $profileRoot 'package.json')
    Assert-DshUnrelatedPackage $before $after
    Assert-DshUnrelatedRuntime $profileRoot $after $unrelatedRuntime
    Assert-DshTreeHashes $pluginAbsolute $sourceHashes
    Assert-DshResolvedPlugin $profileRoot $pluginAbsolute
    $receipt.status='installed_pending_runtime_verification'
    $receipt.completed_at=[DateTimeOffset]::UtcNow.ToString('o')
    $receipt.profile_state_after=Get-DshProfileState $profileRoot
    $receipt.patch_sha256=Get-DshHash (Join-Path $pluginAbsolute 'cordis.patch.yml')
    Save-DshReceipt $receiptPath $receipt
    [pscustomobject]@{status=$receipt.status;version=$package.version;backup=$backup;receipt=$receiptPath;original_rehearsal_resumed=$false} | ConvertTo-Json
} catch {
    $failure=$_.Exception.Message;$rollbackErrors=@()
    try {
        Assert-DshClosed
        Assert-DshBackup $backup $receipt
        if ($swapped) {
            if (Test-Path -LiteralPath $pluginAbsolute) { Move-Item -LiteralPath $pluginAbsolute -Destination $failed }
            if (-not (Test-Path -LiteralPath $retired)) { throw 'Retired plugin is missing; preserve backup for manual recovery.' }
            Move-Item -LiteralPath $retired -Destination $pluginAbsolute
        }
        Restore-DshProfileFiles $profileRoot $profileBackup $profileState (Join-Path $backup 'rollback-displaced-profile')
        if ($cliAttempted) {
            if (-not $profileState['pnpm-lock.yaml']) { throw 'No saved pnpm lockfile; dependency rollback cannot be certified automatically.' }
            Invoke-DshProfileCli $cliPath $Profile @('install','--offline','--frozen-lockfile')
        }
        Assert-DshProfileState $profileRoot $profileState
        Assert-DshTreeHashes $pluginAbsolute $pluginHashes
        Assert-DshResolvedPlugin $profileRoot $pluginAbsolute
        Assert-DshUnrelatedRuntime $profileRoot $before $unrelatedRuntime
    } catch { $rollbackErrors += $_.Exception.Message }
    $receipt.status=if($rollbackErrors.Count) { 'rollback_partial' } else { 'rolled_back_verified' }
    $receipt.error=$failure;$receipt.rollback_errors=$rollbackErrors;$receipt.failed_at=[DateTimeOffset]::UtcNow.ToString('o')
    Save-DshReceipt $receiptPath $receipt
    throw "Upgrade failed; recovery status=$($receipt.status). Cause: $failure. Recovery details: $($rollbackErrors -join '; '). Receipt: $receiptPath"
}
