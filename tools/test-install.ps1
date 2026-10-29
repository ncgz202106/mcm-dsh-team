# Isolated filesystem regressions. Official CLI and process inventory are mocked here only.
# Run with PowerShell 7. No real DSH process is stopped and no user installation is touched.
[CmdletBinding()]
param([string]$FixtureRoot)
$ErrorActionPreference='Stop'
$previousFixtureState=Get-Variable -Name McmInstallerFixtureState -Scope Global -ErrorAction SilentlyContinue
$global:McmInstallerFixtureState=@{Root=$null;Running=$false;MoveFailures=@()}
. (Join-Path $PSScriptRoot 'dsh-install-common.ps1')
if ($PSVersionTable.PSVersion.Major -lt 7) { throw 'Run this fixture suite with PowerShell 7 (pwsh).' }
if (-not $FixtureRoot) { $FixtureRoot=Join-Path ([IO.Path]::GetTempPath()) ('mcm-installer-tests-'+[guid]::NewGuid().ToString('N')) }
$global:McmInstallerFixtureState.Root=Get-AbsoluteDshPath $FixtureRoot
if (Test-Path -LiteralPath $global:McmInstallerFixtureState.Root) { throw 'Use a new empty fixture root.' }
New-Item -ItemType Directory -Path $global:McmInstallerFixtureState.Root | Out-Null
$savedUser=$env:USERPROFILE
$global:McmInstallerFixtureState.Running=$false;$global:McmInstallerFixtureState.MoveFailures=@();$script:CaseNumber=0
$script:BundlePackage=Read-DshJson (Join-Path (Split-Path -Parent $PSScriptRoot) 'bundle/package.json')
function Get-Process {
    param([string]$Name,[string]$ErrorAction)
    if ($global:McmInstallerFixtureState.Running) { [pscustomobject]@{ProcessName='fixture-only-dsh'} }
}
# A test-scope cmdlet wrapper, never a production fault switch. Each rule throws once.
function Move-Item {
    param([string]$LiteralPath,[string]$Destination,[switch]$Force)
    foreach ($p in @($LiteralPath,$Destination)) {
        if (-not (Test-DshPathWithin $p $global:McmInstallerFixtureState.Root)) { throw 'Fixture Move-Item cannot operate outside its isolated root.' }
    }
    foreach ($rule in $global:McmInstallerFixtureState.MoveFailures) {
        if (-not $rule.fired -and (Get-AbsoluteDshPath $Destination) -eq $rule.destination -and $LiteralPath -match $rule.source_pattern) {
            $rule.fired=$true;throw "Fixture-only move fault: $LiteralPath -> $Destination"
        }
    }
    Microsoft.PowerShell.Management\Move-Item -LiteralPath $LiteralPath -Destination $Destination -Force:$Force
    $edit=$global:McmInstallerFixtureState.ProfileEdit
    if($edit -and $Destination -eq $edit.destination -and $LiteralPath -match $edit.source_pattern) {
        if(-not(Test-DshPathWithin $edit.path $global:McmInstallerFixtureState.Root)){throw 'Unsafe fixture edit path'}
        [IO.File]::AppendAllText($edit.path,' concurrent-user-edit')
        $global:McmInstallerFixtureState.ProfileEdit=$null
    }
}
function Set-TestMoveFault($Fixture,[string[]]$Patterns) {
    $global:McmInstallerFixtureState.MoveFailures=@($Patterns | ForEach-Object { @{destination=(Get-AbsoluteDshPath $Fixture.plugin);source_pattern=$_;fired=$false} })
}
function Assert-TestMoveFaultsFired {
    Assert-Test (@($global:McmInstallerFixtureState.MoveFailures | Where-Object { -not $_.fired }).Count -eq 0) 'A configured move fault never ran.'
    $global:McmInstallerFixtureState.MoveFailures=@()
}
function Write-TestJson([string]$Path,$Value) { [IO.File]::WriteAllText($Path,($Value | ConvertTo-Json -Depth 40)+"`n",[Text.UTF8Encoding]::new($false)) }
function Assert-Test([bool]$Passed,[string]$Message) { if (-not $Passed) { throw $Message } }
function Expect-TestFailure([scriptblock]$Action,[string]$Pattern) {
    $failed=$false;$message=''
    try { & $Action | Out-Null } catch { $failed=$true;$message=$_.Exception.Message }
    Assert-Test $failed 'Expected rejection or injected failure was accepted.'
    if ($Pattern) { Assert-Test ($message -match $Pattern) "Unexpected failure: $message" }
}
function Convert-TestOutputToJson($Lines) {
    $message=(@($Lines) | ForEach-Object { [string]$_ }) -join "`n";$start=$message.IndexOf('{')
    Assert-Test ($start -ge 0) "Expected JSON output: $message"
    return $message.Substring($start) | ConvertFrom-Json -AsHashtable
}
function Get-TestSnapshot([string]$Root) {
    $snapshot=[ordered]@{};$pending=[Collections.Generic.Stack[string]]::new();$pending.Push($Root)
    while ($pending.Count) {
        foreach ($entry in Get-ChildItem -LiteralPath $pending.Pop() -Force) {
            $relative=[IO.Path]::GetRelativePath($Root,$entry.FullName).Replace('\','/')
            if ($entry.Attributes -band [IO.FileAttributes]::ReparsePoint) { $snapshot[$relative]='link:'+($entry.Target -join '|') }
            elseif ($entry.PSIsContainer) { $snapshot[$relative]='directory';$pending.Push($entry.FullName) }
            else { $snapshot[$relative]=Get-DshHash $entry.FullName }
        }
    }
    return $snapshot
}
function Assert-TestSnapshot([string]$Root,$Before) {
    $after=Get-TestSnapshot $Root
    Assert-Test ($after.Count -eq $Before.Count) "Fixture file set changed unexpectedly: $Root"
    foreach ($name in $Before.Keys) { Assert-Test ($after[$name] -eq $Before[$name]) "Fixture changed unexpectedly: $name" }
}
function Assert-TestNoCli($Fixture) { Assert-Test (-not (Test-Path -LiteralPath $Fixture.cli_marker)) 'The official CLI poison stub was invoked.' }
function Assert-TestProfileReceiptUnchanged($Receipt) {
    Assert-Test ($Receipt.profile_state_before.Count -eq $Receipt.profile_state_after.Count) 'Profile fingerprint file set changed.'
    foreach ($name in $Receipt.profile_state_before.Keys) {
        Assert-Test ($Receipt.profile_state_before[$name] -eq $Receipt.profile_state_after[$name]) "Receipt recorded a profile mutation: $name"
    }
}
function New-TestFixture {
    param([ValidateSet('consistent','mismatch','unknown')][string]$LockState='consistent',[switch]$FirstTime)
    $script:CaseNumber++;$base=Join-Path $global:McmInstallerFixtureState.Root ('case-'+$script:CaseNumber)
    $user=Join-Path $base 'user';$plugin=Join-Path $user '.dsh/plugins/dsh-mcm-team';$profile=Join-Path $user '.dsh/profiles/desktop'
    foreach ($p in @($profile,(Join-Path $profile 'node_modules/other-plugin'))) { New-Item -ItemType Directory -Path $p -Force | Out-Null }
    $dependencies=[ordered]@{'other-plugin'='1.2.3'};$bundles=@('other-plugin')
    if (-not $FirstTime) {
        New-Item -ItemType Directory -Path $plugin -Force | Out-Null
        # The old manifest derives from the bundle; version is its only difference.
        $old=Read-DshJson (Join-Path (Split-Path -Parent $PSScriptRoot) 'bundle/package.json');$old.version='0.2.1'
        Write-TestJson (Join-Path $plugin 'package.json') $old
        [IO.File]::WriteAllText((Join-Path $plugin 'cordis.patch.yml'),'# isolated old fixture')
        $dependencies['dsh-mcm-team']="link:$($plugin.Replace('\','/'))";$bundles+=@('dsh-mcm-team')
        New-Item -ItemType Junction -Path (Join-Path $profile 'node_modules/dsh-mcm-team') -Target $plugin | Out-Null
    }
    Write-TestJson (Join-Path $profile 'package.json') @{name='fixture';private=$true;dependencies=$dependencies;dsh=@{profile=@{bundles=$bundles}}}
    Write-TestJson (Join-Path $profile 'node_modules/other-plugin/package.json') @{name='other-plugin';version='1.2.3'}
    $otherSpecifier=if ($LockState -eq 'mismatch') { '99.0.0' } else { '1.2.3' }
    $mcmLock=if ($FirstTime) { '' } else { @"
      dsh-mcm-team:
        specifier: 'link:$($plugin.Replace('\','/'))'
        version: 'link:../../plugins/dsh-mcm-team'
"@ }
    $lock=@"
lockfileVersion: '9.0'

settings:
  autoInstallPeers: true
  excludeLinksFromLockfile: false

importers:
  .:
    dependencies:
      other-plugin:
        specifier: '$otherSpecifier'
        version: 1.2.3
$mcmLock

packages:
  other-plugin@1.2.3:
    resolution: {integrity: sha512-Zml4dHVyZQ==}

snapshots:
  other-plugin@1.2.3: {}
"@
    if ($LockState -eq 'unknown') { $lock="lockfileVersion: '9.0'`n# Deliberately missing root importer.`n" }
    [IO.File]::WriteAllText((Join-Path $profile 'pnpm-lock.yaml'),$lock,[Text.UTF8Encoding]::new($false))
    [IO.File]::WriteAllText((Join-Path $profile 'cordis.yml'),'# fixture profile')
    $cli=Join-Path $base 'dsh.cmd';$marker=Join-Path $base 'cli-called.marker'
    [IO.File]::WriteAllText($cli,"@echo off`r`necho The official CLI must not run in this suite.>`"%~dp0cli-called.marker`"`r`nexit /b 97`r`n")
    $env:USERPROFILE=$user
    return @{base=$base;user=$user;plugin=$plugin;profile=$profile;cli=$cli;cli_marker=$marker;backups=(Join-Path $base 'backups')}
}
function Get-TestReceipt($Fixture) {
    $p=Get-ChildItem -LiteralPath $Fixture.backups -Filter installation.json -Recurse | Select-Object -First 1
    Assert-Test ([bool]$p) 'An installation receipt was not created.'
    return @{path=$p.FullName;data=(Read-DshJson $p.FullName);directory=$p.DirectoryName}
}
function Get-TestRestoreReceipt($Receipt) {
    $p=Get-ChildItem -LiteralPath $Receipt.directory -Filter restore.json -Recurse | Select-Object -First 1
    Assert-Test ([bool]$p) 'A restore attempt receipt was not created.'
    return Read-DshJson $p.FullName
}
function Invoke-TestUpdate($Fixture,[switch]$CheckOnly) {
    return Convert-TestOutputToJson (& (Join-Path $PSScriptRoot 'update-dsh.ps1') -DshCli $Fixture.cli -BackupRoot $Fixture.backups -CheckOnly:$CheckOnly)
}
function Invoke-TestRestore($Receipt,[switch]$CheckOnly) {
    return Convert-TestOutputToJson (& (Join-Path $PSScriptRoot 'restore-dsh.ps1') -BackupDirectory $Receipt.directory -CheckOnly:$CheckOnly)
}
$checks=@()
try {
    $f=New-TestFixture;$original=Get-DshTreeHashes $f.plugin;$profileBefore=Get-DshProfileState $f.profile;$snapshot=Get-TestSnapshot $f.base
    $preflight=Invoke-TestUpdate $f -CheckOnly
    Assert-Test ($preflight.status -eq 'upgrade_preflight_passed' -and $preflight.install_mode -eq 'registered_link_file_swap') 'Unexpected update preflight mode.'
    Assert-Test ($preflight.dependency_install_performed -eq $false -and $preflight.cli_will_run -eq $false) 'Preflight permits dependency installation.'
    Assert-Test ($preflight.lockfile_audit.status -eq 'consistent') 'Real pnpm9 root importer was not audited as consistent.'
    Assert-TestSnapshot $f.base $snapshot;Assert-TestNoCli $f;$checks+='update_check_only_is_read_only_and_announces_no_cli'
    $result=Invoke-TestUpdate $f;$r=Get-TestReceipt $f
    Assert-Test ($result.status -eq 'installed_pending_runtime_verification') 'Upgrade incorrectly claims runtime verification.'
    Assert-Test ($r.data.format_version -eq 3 -and $r.data.install_mode -eq 'registered_link_file_swap' -and $r.data.dependency_install_performed -eq $false) 'Upgrade receipt is not v3 file-only evidence.'
    Assert-Test ((Read-DshJson (Join-Path $f.plugin 'package.json')).version -eq $script:BundlePackage.version) 'Fixture version not upgraded.'
    Assert-TestProfileReceiptUnchanged $r.data;Assert-DshProfileState $f.profile $profileBefore;Assert-TestNoCli $f
    $checks+='same_contract_update_has_v3_receipt_and_preserves_exact_profile_and_lock_bytes'
    $snapshot=Get-TestSnapshot $f.base;$null=Invoke-TestRestore $r -CheckOnly;Assert-TestSnapshot $f.base $snapshot;$checks+='restore_check_only_is_read_only'
    $p=Join-Path $r.directory 'profile/package.json';$bytes=[IO.File]::ReadAllBytes($p);[IO.File]::AppendAllText($p,' ')
    Expect-TestFailure { Invoke-TestRestore $r -CheckOnly } 'Profile file changed';[IO.File]::WriteAllBytes($p,$bytes)
    $p=Join-Path $r.directory 'plugin/cordis.patch.yml';$bytes=[IO.File]::ReadAllBytes($p);[IO.File]::AppendAllText($p,' tampered')
    Expect-TestFailure { Invoke-TestRestore $r -CheckOnly } 'fingerprint';[IO.File]::WriteAllBytes($p,$bytes)
    Assert-DshProfileState $f.profile $profileBefore;Assert-TestNoCli $f;$checks+='tampered_plugin_and_profile_backups_are_rejected'
    $p=Join-Path $f.profile 'cordis.yml';$bytes=[IO.File]::ReadAllBytes($p);[IO.File]::AppendAllText($p,' later-user-change');$snapshot=Get-TestSnapshot $f.base
    Expect-TestFailure { Invoke-TestRestore $r } 'Profile file changed|MCM_RESTORE_MIGRATION_REQUIRED'
    Assert-TestSnapshot $f.base $snapshot;[IO.File]::WriteAllBytes($p,$bytes);$checks+='later_user_profile_change_is_preserved_and_restore_is_refused'
    $global:McmInstallerFixtureState.Running=$true;$snapshot=Get-TestSnapshot $f.base
    Expect-TestFailure { Invoke-TestRestore $r } 'DSH.*running'
    Assert-TestSnapshot $f.base $snapshot;$global:McmInstallerFixtureState.Running=$false;$checks+='running_desktop_refuses_restore_without_writes'
    $result=Invoke-TestRestore $r;$restore=Get-TestRestoreReceipt $r
    Assert-Test ($result.status -eq 'restored_verified' -and $restore.restore_scope -eq 'plugin_files_only' -and $restore.dependency_install_performed -eq $false) 'Restore is not a verified plugin-only operation.'
    Assert-Test ($restore.legacy_dependency_tree_unverified -eq $false) 'v3 restore incorrectly carries legacy dependency evidence.'
    Assert-DshTreeHashes $f.plugin $original;Assert-DshProfileState $f.profile $profileBefore;Assert-TestNoCli $f
    $checks+='same_contract_restore_preserves_exact_profile_and_lock_bytes_and_never_calls_cli'
    foreach ($auditState in @('mismatch','unknown')) {
        $f=New-TestFixture -LockState $auditState;$profileBefore=Get-DshProfileState $f.profile;$original=Get-DshTreeHashes $f.plugin;$snapshot=Get-TestSnapshot $f.base
        $preflight=Invoke-TestUpdate $f -CheckOnly
        Assert-Test ($preflight.lockfile_audit.status -eq $auditState) "Preflight concealed $auditState root importer evidence."
        Assert-TestSnapshot $f.base $snapshot;$null=Invoke-TestUpdate $f;$r=Get-TestReceipt $f
        Assert-Test ($r.data.lockfile_audit.status -eq $auditState) "Receipt concealed $auditState root importer evidence."
        Assert-Test ($r.data.dependency_install_performed -eq $false) 'Bad-lock update attempted to repair dependencies.'
        Assert-TestProfileReceiptUnchanged $r.data;Assert-DshProfileState $f.profile $profileBefore
        $null=Invoke-TestRestore $r;Assert-DshTreeHashes $f.plugin $original;Assert-DshProfileState $f.profile $profileBefore;Assert-TestNoCli $f
        $checks+="${auditState}_root_importer_is_disclosed_without_lock_repair_or_cli"
    }
    $contractCases=[ordered]@{
        dependencies=@{'fixture-contract-dependency'='1.0.0'};devDependencies=@{'fixture-contract-dev'='1.0.0'}
        optionalDependencies=@{'fixture-contract-optional'='1.0.0'};peerDependencies=@{'@deepseek-ai/dsh'='0.2.0'}
        peerDependenciesMeta=@{'@deepseek-ai/dsh'=@{optional=$true}};bundledDependencies=@('fixture-contract-bundled')
        bundleDependencies=@('fixture-contract-bundle-alias');engines=@{node='>=99'};os=@('fixture-os');cpu=@('fixture-cpu');libc=@('fixture-libc')
        packageManager='pnpm@99.0.0';overrides=@{'fixture-contract-override'='1.0.0'};pnpm=@{overrides=@{'fixture-contract-pnpm'='1.0.0'}}
    }
    foreach ($section in $contractCases.Keys) {
        $f=New-TestFixture;$p=Join-Path $f.plugin 'package.json';$old=Read-DshJson $p;$old[$section]=$contractCases[$section];Write-TestJson $p $old;$snapshot=Get-TestSnapshot $f.base
        Expect-TestFailure { Invoke-TestUpdate $f -CheckOnly } 'MCM_DEPENDENCY_MIGRATION_REQUIRED'
        Expect-TestFailure { Invoke-TestUpdate $f } 'MCM_DEPENDENCY_MIGRATION_REQUIRED'
        Assert-Test (-not (Test-Path -LiteralPath $f.backups)) "Changed $section wrote a backup."
        Assert-TestSnapshot $f.base $snapshot;Assert-TestNoCli $f;$checks+="changed_${section}_requires_migration_before_any_write"
    }
    $f=New-TestFixture;$snapshot=Get-TestSnapshot $f.base
    Expect-TestFailure { & (Join-Path $PSScriptRoot 'update-dsh.ps1') -DshCli $f.cli -BackupRoot (Join-Path $f.plugin 'nested-backup') -CheckOnly } 'overlap'
    Assert-TestSnapshot $f.base $snapshot;Assert-TestNoCli $f;$checks+='nested_backup_path_is_rejected_without_writes'
    $link=Join-Path $f.profile 'node_modules/dsh-mcm-team';[IO.Directory]::Delete($link);Copy-Item -LiteralPath $f.plugin -Destination $link -Recurse;$snapshot=Get-TestSnapshot $f.base
    Expect-TestFailure { Invoke-TestUpdate $f } 'canonical link'
    Assert-TestSnapshot $f.base $snapshot;Assert-TestNoCli $f;$checks+='byte_identical_node_modules_copy_is_not_a_canonical_link'
    $f=New-TestFixture;$link=Join-Path $f.profile 'node_modules/dsh-mcm-team';[IO.Directory]::Delete($link)
    $wrong=Join-Path $f.base 'wrong-target';Copy-Item -LiteralPath $f.plugin -Destination $wrong -Recurse
    New-Item -ItemType Junction -Path $link -Target $wrong | Out-Null;$snapshot=Get-TestSnapshot $f.base
    Expect-TestFailure { Invoke-TestUpdate $f } 'canonical link'
    Assert-TestSnapshot $f.base $snapshot;Assert-TestNoCli $f;$checks+='junction_to_identical_noncanonical_plugin_is_rejected'
    $f=New-TestFixture;$global:McmInstallerFixtureState.Running=$true;$snapshot=Get-TestSnapshot $f.base
    Expect-TestFailure { Invoke-TestUpdate $f } 'DSH.*running'
    Assert-TestSnapshot $f.base $snapshot;Assert-TestNoCli $f;$global:McmInstallerFixtureState.Running=$false;$checks+='running_desktop_refuses_update_without_writes'
    foreach ($auditState in @('mismatch','unknown')) {
        $f=New-TestFixture -FirstTime -LockState $auditState;$snapshot=Get-TestSnapshot $f.base
        Expect-TestFailure { & (Join-Path $PSScriptRoot 'install-dsh.ps1') -DshCli $f.cli -CheckOnly } 'MCM_PROFILE_LOCK_REPAIR_REQUIRED'
        Expect-TestFailure { & (Join-Path $PSScriptRoot 'install-dsh.ps1') -DshCli $f.cli } 'MCM_PROFILE_LOCK_REPAIR_REQUIRED'
        Assert-TestSnapshot $f.base $snapshot;Assert-TestNoCli $f;$checks+="first_time_${auditState}_root_importer_refuses_before_cli"
    }
    $f=New-TestFixture;$null=Invoke-TestUpdate $f;$r=Get-TestReceipt $f;$profileBefore=Get-DshProfileState $f.profile;$original=Get-DshTreeHashes (Join-Path $r.directory 'plugin')
    $r.data.format_version=2
    foreach($key in @('install_mode','dependency_install_performed','lockfile_audit','verified_scope')){$r.data.Remove($key)}
    Write-TestJson $r.path $r.data;$result=Invoke-TestRestore $r;$restore=Get-TestRestoreReceipt $r
    Assert-Test ($result.status -eq 'restored_plugin_files_verified' -and $restore.legacy_dependency_tree_unverified -eq $true) 'Legacy receipt incorrectly certifies its old dependency tree.'
    Assert-Test ($restore.restore_scope -eq 'plugin_files_only' -and $restore.dependency_install_performed -eq $false) 'Legacy receipt attempted dependency restoration.'
    Assert-DshTreeHashes $f.plugin $original;Assert-DshProfileState $f.profile $profileBefore;Assert-TestNoCli $f
    $checks+='legacy_v2_restore_is_explicitly_plugin_only_with_dependency_tree_unverified'
    $f=New-TestFixture;$null=Invoke-TestUpdate $f;$r=Get-TestReceipt $f
    $p=Join-Path $r.directory 'profile/cordis.yml';[IO.File]::AppendAllText($p,' legitimate-old-profile-difference')
    $r.data.profile_state_before['cordis.yml']=Get-DshHash $p;Write-TestJson $r.path $r.data;$snapshot=Get-TestSnapshot $f.base
    Expect-TestFailure { Invoke-TestRestore $r } 'MCM_RESTORE_MIGRATION_REQUIRED'
    Assert-TestSnapshot $f.base $snapshot;Assert-TestNoCli $f;$checks+='restore_that_requires_profile_migration_is_refused_without_writes'
    $f=New-TestFixture;$null=Invoke-TestUpdate $f;$r=Get-TestReceipt $f
    $p=Join-Path $r.directory 'plugin/package.json';$old=Read-DshJson $p;$old.dependencies=@{'fixture-old-dependency'='1.0.0'};Write-TestJson $p $old
    $r.data.plugin_hashes_before=Get-DshTreeHashes (Join-Path $r.directory 'plugin');Write-TestJson $r.path $r.data;$snapshot=Get-TestSnapshot $f.base
    Expect-TestFailure { Invoke-TestRestore $r } 'MCM_RESTORE_MIGRATION_REQUIRED'
    Assert-TestSnapshot $f.base $snapshot;Assert-TestNoCli $f;$checks+='restore_that_requires_dependency_migration_is_refused_without_writes'
    $f=New-TestFixture;$original=Get-DshTreeHashes $f.plugin;$profileBefore=Get-DshProfileState $f.profile
    Set-TestMoveFault $f @('dsh-mcm-team\.next-');Expect-TestFailure { Invoke-TestUpdate $f } 'rolled_back_verified';Assert-TestMoveFaultsFired;$r=Get-TestReceipt $f
    Assert-Test ($r.data.status -eq 'rolled_back_verified') 'Update move failure was not reported as verified rollback.'
    Assert-DshTreeHashes $f.plugin $original;Assert-DshProfileState $f.profile $profileBefore;Assert-TestNoCli $f;$checks+='update_stage_move_failure_rolls_back_exact_plugin_without_cli'
    $f=New-TestFixture;$profileBefore=Get-DshProfileState $f.profile
    Set-TestMoveFault $f @('dsh-mcm-team\.next-','dsh-mcm-team\.previous-');Expect-TestFailure { Invoke-TestUpdate $f } 'rollback_partial';Assert-TestMoveFaultsFired;$r=Get-TestReceipt $f
    Assert-Test ($r.data.status -eq 'rollback_partial' -and $r.data.rollback_errors.Count -gt 0) 'Failed update recovery was falsely certified.'
    Assert-DshTreeHashes (Join-Path $r.directory 'plugin') $r.data.plugin_hashes_before;Assert-DshProfileState $f.profile $profileBefore;Assert-TestNoCli $f
    $checks+='update_recovery_move_failure_reports_partial_and_preserves_hashed_backup'
    $f=New-TestFixture;$null=Invoke-TestUpdate $f;$r=Get-TestReceipt $f;$current=Get-DshTreeHashes $f.plugin;$profileBefore=Get-DshProfileState $f.profile
    Set-TestMoveFault $f @('dsh-mcm-team\.restore-next-');Expect-TestFailure { Invoke-TestRestore $r } 'restore_failed_current_version_recovered';Assert-TestMoveFaultsFired;$restore=Get-TestRestoreReceipt $r
    Assert-Test ($restore.status -eq 'restore_failed_current_version_recovered') 'Restore move failure did not certify recovery of the current plugin.'
    Assert-DshTreeHashes $f.plugin $current;Assert-DshProfileState $f.profile $profileBefore;Assert-TestNoCli $f;$checks+='restore_stage_move_failure_recovers_exact_current_plugin_without_cli'
    $f=New-TestFixture;$null=Invoke-TestUpdate $f;$r=Get-TestReceipt $f;$profileBefore=Get-DshProfileState $f.profile
    Set-TestMoveFault $f @('dsh-mcm-team\.restore-next-','dsh-mcm-team\.before-restore-');Expect-TestFailure { Invoke-TestRestore $r } 'restore_failed_recovery_partial';Assert-TestMoveFaultsFired;$restore=Get-TestRestoreReceipt $r
    Assert-Test ($restore.status -eq 'restore_failed_recovery_partial' -and $restore.recovery_errors.Count -gt 0) 'Failed restore recovery was falsely certified.'
    Assert-DshTreeHashes (Join-Path $r.directory 'plugin') $r.data.plugin_hashes_before;Assert-DshProfileState $f.profile $profileBefore;Assert-TestNoCli $f
    $checks+='restore_recovery_move_failure_reports_partial_and_preserves_hashed_backup'
    $f=New-TestFixture;$snapshot=Get-TestSnapshot $f.base
    $p=Join-Path $f.profile 'package.json';$manifest=Read-DshJson $p;$manifest.dependencies['dsh-mcm-team']='link:../../plugins/wrong-plugin';Write-TestJson $p $manifest
    $snapshot=Get-TestSnapshot $f.base
    Expect-TestFailure { Invoke-TestUpdate $f } 'canonical link'
    Assert-TestSnapshot $f.base $snapshot;Assert-TestNoCli $f;$checks+='manifest_link_and_actual_junction_must_agree'
    foreach($operation in @('update','restore')) {
        $f=New-TestFixture
        if($operation -eq 'restore'){$null=Invoke-TestUpdate $f;$r=Get-TestReceipt $f}
        $prior=Get-DshTreeHashes $f.plugin;$p=Join-Path $f.profile 'cordis.yml';$priorText=[IO.File]::ReadAllText($p)
        $pattern=if($operation -eq 'update'){'dsh-mcm-team\.next-'}else{'dsh-mcm-team\.restore-next-'}
        $global:McmInstallerFixtureState.ProfileEdit=@{destination=$f.plugin;source_pattern=$pattern;path=$p}
        if($operation -eq 'update'){Expect-TestFailure { Invoke-TestUpdate $f } 'rollback_partial'}
        else {Expect-TestFailure { Invoke-TestRestore $r } 'restore_failed_recovery_partial'}
        Assert-Test ($null -eq $global:McmInstallerFixtureState.ProfileEdit) 'Concurrent edit injection did not run'
        Assert-Test ([IO.File]::ReadAllText($p) -eq ($priorText+' concurrent-user-edit')) 'Recovery overwrote a concurrent user profile edit'
        Assert-DshTreeHashes $f.plugin $prior;Assert-TestNoCli $f
        $checks+="${operation}_recovery_preserves_concurrent_profile_edit_and_reports_partial"
    }
    Assert-Test (@(Get-ChildItem -LiteralPath $global:McmInstallerFixtureState.Root -Filter cli-called.marker -Recurse).Count -eq 0) 'At least one fixture invoked the official CLI poison stub.'
    [pscustomobject]@{passed=$true;checks=$checks;count=$checks.Count;fixture_root=$global:McmInstallerFixtureState.Root;official_cli_mocked=$true;official_cli_invocations=0;process_inventory_mocked=$true;filesystem_fault_injection_scope='fixture_only';actual_user_plugin_modified=$false;private_backups_uploaded=$false} | ConvertTo-Json -Depth 5
} finally {
    $env:USERPROFILE=$savedUser
    if($previousFixtureState){$global:McmInstallerFixtureState=$previousFixtureState.Value}else{Remove-Variable -Name McmInstallerFixtureState -Scope Global}
}
