[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$BackupDirectory,[string]$DshCli,[switch]$CheckOnly)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'dsh-install-common.ps1')
$backup=(Resolve-Path -LiteralPath $BackupDirectory).Path
Assert-DshPlainPath $backup
$receiptPath=Join-Path $backup 'installation.json'
$receipt=Read-DshJson $receiptPath
$target=Get-AbsoluteDshPath $receipt.target
$expectedParent=Get-AbsoluteDshPath (Join-Path $env:USERPROFILE '.dsh/plugins')
if ($target -ne (Join-Path $expectedParent 'dsh-mcm-team')) { throw 'Receipt target must be the current user named MCM plugin.' }
if ($receipt.profile -notmatch '^[a-zA-Z0-9_-]+$') { throw 'Receipt profile name is invalid.' }
$profile=Get-AbsoluteDshPath $receipt.profile_root
$expectedProfile=Get-AbsoluteDshPath (Join-Path (Join-Path $env:USERPROFILE '.dsh/profiles') $receipt.profile)
if ($profile -ne $expectedProfile) { throw 'Receipt profile escaped the expected profile path.' }
foreach ($p in @($target,$profile)) { Assert-DshPlainPath $p;Assert-DshDisjoint $backup $p }
Assert-DshBackup $backup $receipt
if ($receipt.status -notin @('installed_pending_runtime_verification','installed_verified')) { throw "Receipt is not an installed restore point: $($receipt.status)" }
if (-not $receipt.profile_state_after) { throw 'Missing post-install profile fingerprints; do not overwrite potentially changed user configuration.' }
Assert-DshProfileState $profile $receipt.profile_state_after
Assert-DshTreeHashes $target $receipt.source_hashes
$oldPackage=Read-DshJson (Join-Path $backup 'profile/package.json')
Assert-DshUnrelatedPackage $oldPackage (Read-DshJson (Join-Path $profile 'package.json'))
Assert-DshUnrelatedRuntime $profile $oldPackage $receipt.unrelated_runtime_before
if (-not $receipt.profile_state_before['pnpm-lock.yaml']) { throw 'Saved lockfile is required for a verified dependency restore.' }
if (-not $DshCli) { $DshCli=$receipt.cli_path }
$cli=(Resolve-Path -LiteralPath $DshCli).Path
$active=@(Get-Process -Name 'DeepSeek Harness' -ErrorAction SilentlyContinue)
if ($CheckOnly) {
    [pscustomobject]@{status='restore_preflight_passed';target=$target;backup=$backup;old_version=$receipt.old_version;requires_normal_exit=($active.Count -gt 0);changed=$false} | ConvertTo-Json
    return
}
Assert-DshClosed
$stamp=Get-Date -Format 'yyyyMMdd-HHmmss-fff'
$stage=Join-Path $expectedParent "dsh-mcm-team.restore-next-$stamp"
$displaced=Join-Path $expectedParent "dsh-mcm-team.before-restore-$stamp"
$failed=Join-Path $expectedParent "dsh-mcm-team.failed-restore-$stamp"
foreach ($p in @($stage,$displaced,$failed)) {
    if ((Split-Path -Parent (Get-AbsoluteDshPath $p)) -ne $expectedParent -or (Test-Path -LiteralPath $p)) { throw 'Unsafe/existing restore staging path.' }
}
$runBackup=Join-Path $backup "restore-$stamp"
New-Item -ItemType Directory -Path $runBackup | Out-Null
$currentProfile=Get-DshProfileState $profile
$currentProfileBackup=Join-Path $runBackup 'profile';New-Item -ItemType Directory -Path $currentProfileBackup | Out-Null
foreach ($name in $DshProfileFiles) { if ($currentProfile[$name]) { Copy-Item -LiteralPath (Join-Path $profile $name) -Destination (Join-Path $currentProfileBackup $name) } }
$restoreReceipt=[ordered]@{format_version=1;status='prepared';started_at=[DateTimeOffset]::UtcNow.ToString('o');backup=$backup;target=$target;current_profile_state=$currentProfile;original_rehearsal_resumed=$false}
$runReceipt=Join-Path $runBackup 'restore.json';Save-DshReceipt $runReceipt $restoreReceipt
$swapped=$false
try {
    Copy-Item -LiteralPath (Join-Path $backup 'plugin') -Destination $stage -Recurse
    Assert-DshTreeHashes $stage $receipt.plugin_hashes_before
    Assert-DshProfileState $currentProfileBackup $currentProfile
    Assert-DshClosed
    Assert-DshProfileState $profile $currentProfile
    Move-Item -LiteralPath $target -Destination $displaced;$swapped=$true
    Move-Item -LiteralPath $stage -Destination $target
    Restore-DshProfileFiles $profile (Join-Path $backup 'profile') $receipt.profile_state_before (Join-Path $runBackup 'displaced-profile')
    Invoke-DshProfileCli $cli $receipt.profile @('install','--offline','--frozen-lockfile')
    Assert-DshProfileState $profile $receipt.profile_state_before
    Assert-DshTreeHashes $target $receipt.plugin_hashes_before
    Assert-DshResolvedPlugin $profile $target
    Assert-DshUnrelatedRuntime $profile $oldPackage $receipt.unrelated_runtime_before
    $restoreReceipt.status='restored_verified';$restoreReceipt.completed_at=[DateTimeOffset]::UtcNow.ToString('o')
    Save-DshReceipt $runReceipt $restoreReceipt
    [pscustomobject]@{status='restored_verified';version=$receipt.old_version;backup=$backup;restore_receipt=$runReceipt;original_rehearsal_resumed=$false} | ConvertTo-Json
} catch {
    $failure=$_.Exception.Message;$recoveryErrors=@()
    try {
        Assert-DshClosed
        if ($swapped) {
            if (Test-Path -LiteralPath $target) { Move-Item -LiteralPath $target -Destination $failed }
            if (-not (Test-Path -LiteralPath $displaced)) { throw 'Current-version displaced plugin is missing.' }
            Move-Item -LiteralPath $displaced -Destination $target
        }
        Restore-DshProfileFiles $profile $currentProfileBackup $currentProfile (Join-Path $runBackup 'recovery-displaced-profile')
        if ($swapped) {
            if (-not $currentProfile['pnpm-lock.yaml']) { throw 'Current-version lockfile is missing; dependency recovery is unverified.' }
            Invoke-DshProfileCli $cli $receipt.profile @('install','--offline','--frozen-lockfile')
        }
        Assert-DshTreeHashes $target $receipt.source_hashes
        Assert-DshProfileState $profile $currentProfile
        Assert-DshResolvedPlugin $profile $target
        Assert-DshUnrelatedRuntime $profile $oldPackage $receipt.unrelated_runtime_before
    } catch { $recoveryErrors += $_.Exception.Message }
    $restoreReceipt.status=if($recoveryErrors.Count) { 'restore_failed_recovery_partial' } else { 'restore_failed_current_version_recovered' }
    $restoreReceipt.error=$failure;$restoreReceipt.recovery_errors=$recoveryErrors
    Save-DshReceipt $runReceipt $restoreReceipt
    throw "Restore failed; status=$($restoreReceipt.status). Cause: $failure. Details: $($recoveryErrors -join '; '). Receipt: $runReceipt"
}
