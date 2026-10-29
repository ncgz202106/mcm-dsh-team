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
if (-not (Test-DshProfileStatesEqual $receipt.profile_state_before $receipt.profile_state_after)) {
    throw 'MCM_RESTORE_MIGRATION_REQUIRED: Saved profile states differ. A plugin-only restore cannot reverse profile/dependency migrations; preserve the files and plan recovery separately.'
}
if ($receipt.format_version -eq 3 -and ($receipt.install_mode -ne 'registered_link_file_swap' -or $receipt.dependency_install_performed -ne $false)) {
    throw 'MCM_RESTORE_MIGRATION_REQUIRED: Unsupported v3 dependency operation.'
}
Assert-DshProfileState $profile $receipt.profile_state_after
Assert-DshTreeHashes $target $receipt.source_hashes
Assert-DshResolvedPlugin $profile $target
$savedPlugin=Read-DshJson (Join-Path $backup 'plugin/package.json')
$currentPlugin=Read-DshJson (Join-Path $target 'package.json')
Assert-DshSameDependencyContract $currentPlugin $savedPlugin 'MCM_RESTORE_MIGRATION_REQUIRED'
$oldPackage=Read-DshJson (Join-Path $backup 'profile/package.json')
Assert-DshUnrelatedPackage $oldPackage (Read-DshJson (Join-Path $profile 'package.json'))
Assert-DshUnrelatedRuntime $profile $oldPackage $receipt.unrelated_runtime_before
$legacy=($receipt.format_version -eq 2)
$lockAudit=Get-DshLockAudit $profile
Write-DshLockAuditWarning $lockAudit
if ($legacy) { Write-Warning 'MCM_LEGACY_RESTORE_SCOPE: Only plugin files/profile fingerprints and direct manifests will be checked. Any transitive dependency changes made by the old installer are not reversed or certified.' }
$active=@(Get-Process -Name 'DeepSeek Harness' -ErrorAction SilentlyContinue)
if ($CheckOnly) {
    [pscustomobject]@{status='restore_preflight_passed';target=$target;backup=$backup;old_version=$receipt.old_version;requires_normal_exit=($active.Count -gt 0);restore_scope='plugin_files_only';dependency_install_performed=$false;legacy_dependency_tree_unverified=$legacy;lockfile_audit=$lockAudit;changed=$false} | ConvertTo-Json -Depth 10
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
$restoreReceipt=[ordered]@{format_version=2;status='prepared';started_at=[DateTimeOffset]::UtcNow.ToString('o');backup=$backup;target=$target;current_profile_state=$currentProfile;restore_scope='plugin_files_only';dependency_install_performed=$false;legacy_dependency_tree_unverified=$legacy;lockfile_audit=$lockAudit;verified_scope=@('plugin_tree','profile_files','unrelated_direct_manifests');original_rehearsal_resumed=$false}
$runReceipt=Join-Path $runBackup 'restore.json';Save-DshReceipt $runReceipt $restoreReceipt
$swapped=$false
try {
    Copy-Item -LiteralPath (Join-Path $backup 'plugin') -Destination $stage -Recurse
    Assert-DshTreeHashes $stage $receipt.plugin_hashes_before
    Assert-DshProfileState $currentProfileBackup $currentProfile
    Assert-DshClosed
    Assert-DshProfileState $profile $currentProfile
    Assert-DshTreeHashes $target $receipt.source_hashes
    Move-Item -LiteralPath $target -Destination $displaced;$swapped=$true
    Move-Item -LiteralPath $stage -Destination $target
    # Link and dependency requirements are unchanged. A global install here can
    # prune other plugins and cannot be justified by a plugin-only backup.
    Assert-DshProfileState $profile $receipt.profile_state_before
    Assert-DshTreeHashes $target $receipt.plugin_hashes_before
    Assert-DshResolvedPlugin $profile $target
    Assert-DshUnrelatedRuntime $profile $oldPackage $receipt.unrelated_runtime_before
    $restoreReceipt.status=if($legacy) { 'restored_plugin_files_verified' } else { 'restored_verified' };$restoreReceipt.completed_at=[DateTimeOffset]::UtcNow.ToString('o')
    Save-DshReceipt $runReceipt $restoreReceipt
    [pscustomobject]@{status=$restoreReceipt.status;version=$receipt.old_version;backup=$backup;restore_receipt=$runReceipt;restore_scope='plugin_files_only';dependency_install_performed=$false;legacy_dependency_tree_unverified=$legacy;original_rehearsal_resumed=$false} | ConvertTo-Json
} catch {
    $failure=$_.Exception.Message;$recoveryErrors=@()
    try {
        Assert-DshClosed
        if ($swapped) {
            if (Test-Path -LiteralPath $target) { Assert-DshTreeHashes $target $receipt.plugin_hashes_before;Move-Item -LiteralPath $target -Destination $failed }
            if (-not (Test-Path -LiteralPath $displaced)) { throw 'Current-version displaced plugin is missing.' }
            Assert-DshTreeHashes $displaced $receipt.source_hashes
            Move-Item -LiteralPath $displaced -Destination $target
        }
        # Preserve later user changes; this transaction never wrote the profile.
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
