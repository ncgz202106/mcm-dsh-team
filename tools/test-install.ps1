# Isolated filesystem fault injection. Official CLI and process inventory are mocked here only.
[CmdletBinding()]
param([string]$FixtureRoot)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'dsh-install-common.ps1')
if (-not $FixtureRoot) { $FixtureRoot=Join-Path ([IO.Path]::GetTempPath()) ('mcm-installer-tests-'+[guid]::NewGuid().ToString('N')) }
$suite=Get-AbsoluteDshPath $FixtureRoot
if (Test-Path -LiteralPath $suite) { throw 'Use a new empty fixture root.' }
New-Item -ItemType Directory -Path $suite | Out-Null
$savedUser=$env:USERPROFILE
$savedAdd=$env:MCM_INSTALL_TEST_FAIL_ADD;$savedRestore=$env:MCM_INSTALL_TEST_FAIL_RESTORE;$savedMutate=$env:MCM_INSTALL_TEST_MUTATE_OTHER
$savedRunning=$env:MCM_INSTALL_TEST_RUNNING;$env:MCM_INSTALL_TEST_RUNNING=$null
function Get-Process { param([string]$Name,[string]$ErrorAction);if($env:MCM_INSTALL_TEST_RUNNING -eq '1') { [pscustomobject]@{ProcessName='fixture-only'} } }
function Write-TestJson([string]$Path,$Value) { [IO.File]::WriteAllText($Path,($Value | ConvertTo-Json -Depth 20),[Text.UTF8Encoding]::new($false)) }
function Assert-Test([bool]$Passed,[string]$Message) { if(-not $Passed) { throw $Message } }
function Expect-TestFailure([scriptblock]$Action,[string]$Pattern) {
    $failed=$false;$message=''
    try { & $Action | Out-Null } catch { $failed=$true;$message=$_.Exception.Message }
    Assert-Test $failed 'Expected injected failure was accepted.'
    if($Pattern) { Assert-Test ($message -match $Pattern) "Unexpected failure: $message" }
}
$script:CaseNumber=0
function New-TestFixture {
    $script:CaseNumber++
    $base=Join-Path $suite ('case-'+$script:CaseNumber)
    $user=Join-Path $base 'user';$plugin=Join-Path $user '.dsh/plugins/dsh-mcm-team';$profile=Join-Path $user '.dsh/profiles/desktop'
    foreach($p in @($plugin,$profile,(Join-Path $profile 'node_modules/other-plugin'))) { New-Item -ItemType Directory -Path $p -Force | Out-Null }
    Write-TestJson (Join-Path $plugin 'package.json') @{name='dsh-mcm-team';version='0.1.0'}
    [IO.File]::WriteAllText((Join-Path $plugin 'cordis.patch.yml'),'# isolated old fixture')
    Write-TestJson (Join-Path $profile 'package.json') @{name='fixture';private=$true;dependencies=@{'dsh-mcm-team'="link:$($plugin.Replace('\','/'))";'other-plugin'='1.2.3'};dsh=@{profile=@{bundles=@('other-plugin','dsh-mcm-team')}}}
    Write-TestJson (Join-Path $profile 'node_modules/other-plugin/package.json') @{name='other-plugin';version='1.2.3'}
    New-Item -ItemType Junction -Path (Join-Path $profile 'node_modules/dsh-mcm-team') -Target $plugin | Out-Null
    [IO.File]::WriteAllText((Join-Path $profile 'pnpm-lock.yaml'),'lockfileVersion: 9.0')
    [IO.File]::WriteAllText((Join-Path $profile 'cordis.yml'),'# fixture profile')
    $stub=Join-Path $base 'fixture-cli.ps1'
    [IO.File]::WriteAllText($stub,@'
$ErrorActionPreference='Stop'
if($args[3] -eq 'add') {
    if($env:MCM_INSTALL_TEST_FAIL_ADD -eq '1') { exit 41 }
    if($env:MCM_INSTALL_TEST_MUTATE_OTHER -eq '1') {
        $p=Join-Path $env:DSH_HOME 'profiles/desktop/package.json'
        $x=Get-Content -LiteralPath $p -Raw | ConvertFrom-Json -AsHashtable
        $x.dependencies['other-plugin']='99.0.0';$x.dsh.profile.bundles=@('dsh-mcm-team')
        [IO.File]::WriteAllText($p,($x | ConvertTo-Json -Depth 15))
    }
}
if($args[3] -eq 'install' -and $env:MCM_INSTALL_TEST_FAIL_RESTORE -eq '1') { exit 42 }
exit 0
'@)
    $cli=Join-Path $base 'dsh.cmd'
    [IO.File]::WriteAllText($cli,"@echo off`r`npwsh -NoProfile -File `"%~dp0fixture-cli.ps1`" %*`r`nexit /b %ERRORLEVEL%`r`n")
    $env:USERPROFILE=$user
    return @{base=$base;plugin=$plugin;profile=$profile;cli=$cli;backups=(Join-Path $base 'backups')}
}
function Get-TestReceipt($Fixture) {
    $p=Get-ChildItem -LiteralPath $Fixture.backups -Filter installation.json -Recurse | Select-Object -First 1
    return @{path=$p.FullName;data=(Read-DshJson $p.FullName);directory=$p.DirectoryName}
}
$checks=@()
try {
    $f=New-TestFixture
    $original=Get-DshTreeHashes $f.plugin
    & (Join-Path $PSScriptRoot 'update-dsh.ps1') -DshCli $f.cli -BackupRoot $f.backups | Out-Null
    $r=Get-TestReceipt $f
    Assert-Test ($r.data.status -eq 'installed_pending_runtime_verification') 'Upgrade did not produce its pending runtime state.'
    Assert-Test ((Read-DshJson (Join-Path $f.plugin 'package.json')).version -eq '0.2.0') 'Fixture version not upgraded.'
    $checks+='isolated_successful_upgrade_and_hashed_backup'
    & (Join-Path $PSScriptRoot 'restore-dsh.ps1') -BackupDirectory $r.directory -CheckOnly | Out-Null
    $checks+='restore_check_only_has_no_mutation'
    $p=Join-Path $r.directory 'profile/package.json';$bytes=[IO.File]::ReadAllBytes($p)
    [IO.File]::AppendAllText($p,' ')
    Expect-TestFailure { & (Join-Path $PSScriptRoot 'restore-dsh.ps1') -BackupDirectory $r.directory -CheckOnly } 'Profile file changed'
    Assert-Test ((Read-DshJson (Join-Path $f.plugin 'package.json')).version -eq '0.2.0') 'Tampered backup changed live fixture.'
    [IO.File]::WriteAllBytes($p,$bytes);$checks+='tampered_backup_rejected_before_switch'
    $p=Join-Path $f.profile 'cordis.yml';$bytes=[IO.File]::ReadAllBytes($p);[IO.File]::AppendAllText($p,' user-change')
    Expect-TestFailure { & (Join-Path $PSScriptRoot 'restore-dsh.ps1') -BackupDirectory $r.directory -CheckOnly } 'Profile file changed'
    [IO.File]::WriteAllBytes($p,$bytes);$checks+='later_user_configuration_change_preserved'
    & (Join-Path $PSScriptRoot 'restore-dsh.ps1') -BackupDirectory $r.directory | Out-Null
    Assert-DshTreeHashes $f.plugin $original
    $checks+='verified_restore_returns_exact_old_fixture_bytes'
    $f=New-TestFixture
    Expect-TestFailure { & (Join-Path $PSScriptRoot 'update-dsh.ps1') -DshCli $f.cli -BackupRoot (Join-Path $f.plugin 'nested-backup') -CheckOnly } 'overlap'
    $checks+='nested_backup_path_rejected'
    $env:MCM_INSTALL_TEST_FAIL_ADD='1'
    Expect-TestFailure { & (Join-Path $PSScriptRoot 'update-dsh.ps1') -DshCli $f.cli -BackupRoot $f.backups } 'rolled_back_verified'
    Assert-Test ((Get-TestReceipt $f).data.status -eq 'rolled_back_verified') 'Failed add did not verify rollback.'
    Assert-Test ((Read-DshJson (Join-Path $f.plugin 'package.json')).version -eq '0.1.0') 'Failed upgrade left new plugin installed.'
    $checks+='failed_add_rolls_back_exact_plugin_profile_and_dependency_resolution'
    $f=New-TestFixture;$env:MCM_INSTALL_TEST_FAIL_RESTORE='1'
    Expect-TestFailure { & (Join-Path $PSScriptRoot 'update-dsh.ps1') -DshCli $f.cli -BackupRoot $f.backups } 'rollback_partial'
    Assert-Test ((Get-TestReceipt $f).data.status -eq 'rollback_partial') 'Dependency rollback failure was misreported as success.'
    $checks+='dependency_recovery_failure_reports_partial'
    $env:MCM_INSTALL_TEST_FAIL_ADD=$null;$env:MCM_INSTALL_TEST_FAIL_RESTORE=$null
    $f=New-TestFixture;$env:MCM_INSTALL_TEST_MUTATE_OTHER='1'
    Expect-TestFailure { & (Join-Path $PSScriptRoot 'update-dsh.ps1') -DshCli $f.cli -BackupRoot $f.backups } 'rolled_back_verified'
    Assert-Test ((Read-DshJson (Join-Path $f.profile 'package.json')).dependencies['other-plugin'] -eq '1.2.3') 'Other plugin was not restored.'
    $checks+='unrelated_dependency_and_bundle_mutation_rejected_and_restored'
    $env:MCM_INSTALL_TEST_MUTATE_OTHER=$null;$f=New-TestFixture;$env:MCM_INSTALL_TEST_RUNNING='1'
    Expect-TestFailure { & (Join-Path $PSScriptRoot 'update-dsh.ps1') -DshCli $f.cli -BackupRoot $f.backups } 'DSH is running'
    Assert-Test (-not (Test-Path -LiteralPath $f.backups)) 'Running-host rejection wrote a backup.'
    $checks+='running_host_refuses_mutation'
    [pscustomobject]@{passed=$true;checks=$checks;count=$checks.Count;fixture_root=$suite;official_cli_mocked=$true;process_inventory_mocked=$true;actual_user_plugin_modified=$false} | ConvertTo-Json -Depth 5
} finally {
    $env:USERPROFILE=$savedUser;$env:MCM_INSTALL_TEST_FAIL_ADD=$savedAdd;$env:MCM_INSTALL_TEST_FAIL_RESTORE=$savedRestore;$env:MCM_INSTALL_TEST_MUTATE_OTHER=$savedMutate
    $env:MCM_INSTALL_TEST_RUNNING=$savedRunning
}
