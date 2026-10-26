# Shared cooperative update guards. They do not change DSH permissions or stop processes.
$DshProfileFiles = @('package.json','pnpm-lock.yaml','pnpm-workspace.yaml','cordis.yml','cordis.patch.yml')
function Get-AbsoluteDshPath([string]$Path) { [IO.Path]::GetFullPath($Path).TrimEnd([char[]]@('\','/')) }
function Test-DshPathWithin([string]$Child,[string]$Parent) {
    $childPath=Get-AbsoluteDshPath $Child; $parentPath=Get-AbsoluteDshPath $Parent
    return $childPath.Equals($parentPath,[StringComparison]::OrdinalIgnoreCase) -or $childPath.StartsWith($parentPath+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)
}
function Assert-DshDisjoint([string]$First,[string]$Second) {
    if ((Test-DshPathWithin $First $Second) -or (Test-DshPathWithin $Second $First)) { throw "Backup/source/target paths overlap: $First ; $Second" }
}
function Assert-DshPlainPath([string]$Path) {
    $current=Get-AbsoluteDshPath $Path
    while ($current) {
        if (Test-Path -LiteralPath $current) {
            $item=Get-Item -LiteralPath $current -Force
            if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "Reparse points are not accepted in install paths: $current" }
        }
        $next=Split-Path -Parent $current
        if ($next -eq $current) { break };$current=$next
    }
}
function Assert-DshClosed {
    if (@(Get-Process -Name 'DeepSeek Harness' -ErrorAction SilentlyContinue).Count) { throw 'DSH is running. Save work and exit normally; no forced stop is permitted.' }
}
function Read-DshJson([string]$Path) { Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json -AsHashtable }
function Get-DshHash([string]$Path) { (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant() }
function Save-DshReceipt([string]$Path,$Receipt) {
    $temporary=$Path+'.tmp'
    [IO.File]::WriteAllText($temporary,($Receipt | ConvertTo-Json -Depth 40)+"`n",[Text.UTF8Encoding]::new($false))
    [IO.File]::Move($temporary,$Path,$true)
}
function Get-DshTreeHashes([string]$Root) {
    Assert-DshPlainPath $Root
    $hashes=[ordered]@{}
    foreach ($item in Get-ChildItem -LiteralPath $Root -Force -Recurse) {
        if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "Backup tree contains a reparse point: $($item.FullName)" }
        if (-not $item.PSIsContainer) { $hashes[[IO.Path]::GetRelativePath($Root,$item.FullName).Replace('\','/')]=Get-DshHash $item.FullName }
    }
    return $hashes
}
function Assert-DshTreeHashes([string]$Root,$Expected) {
    $actual=Get-DshTreeHashes $Root
    if (-not $Expected -or $actual.Count -ne $Expected.Count) { throw "Tree file set differs from its fingerprint: $Root" }
    foreach ($key in $Expected.Keys) { if ($actual[$key] -ne $Expected[$key]) { throw "Tree fingerprint mismatch: $Root/$key" } }
}
function Get-DshProfileState([string]$Root) {
    $state=[ordered]@{}
    foreach ($name in $DshProfileFiles) {
        $p=Join-Path $Root $name; Assert-DshPlainPath $p
        $state[$name]=if(Test-Path -LiteralPath $p -PathType Leaf) { Get-DshHash $p } else { $null }
    }
    return $state
}
function Assert-DshProfileState([string]$Root,$Expected) {
    $actual=Get-DshProfileState $Root
    foreach ($name in $DshProfileFiles) {
        if (-not $Expected.Contains($name) -or $actual[$name] -ne $Expected[$name]) { throw "Profile file changed or missing: $name" }
    }
}
function Assert-DshUnrelatedPackage($Before,$After) {
    foreach ($section in @('dependencies','devDependencies','optionalDependencies','peerDependencies')) {
        $left=$Before[$section];$right=$After[$section]
        $keys=@(@($left.Keys)+@($right.Keys) | Where-Object { $_ -and $_ -ne 'dsh-mcm-team' } | Sort-Object -Unique)
        foreach ($key in $keys) { if ($left[$key] -ne $right[$key]) { throw "Unrelated dependency changed: $section/$key" } }
    }
    if (($Before.dsh.profile.bundles | ConvertTo-Json -Compress -Depth 30) -ne ($After.dsh.profile.bundles | ConvertTo-Json -Compress -Depth 30)) { throw 'The DSH bundle registration list changed.' }
    if (@($After.dsh.profile.bundles | Where-Object { $_ -eq 'dsh-mcm-team' }).Count -ne 1) { throw 'Exactly one existing MCM registration is required.' }
}
function Get-DshUnrelatedRuntime([string]$ProfileRoot,$Package) {
    $state=[ordered]@{}
    foreach ($section in @('dependencies','devDependencies','optionalDependencies')) {
        foreach ($name in $Package[$section].Keys) {
            if ($name -eq 'dsh-mcm-team') { continue }
            if ($name -notmatch '^(@[a-zA-Z0-9_.-]+/)?[a-zA-Z0-9_.-]+$') { throw "Unexpected dependency path: $name" }
            $p=Join-Path (Join-Path $ProfileRoot 'node_modules') "$name/package.json"
            $state[$name]=if(Test-Path -LiteralPath $p -PathType Leaf) { Get-DshHash $p } else { $null }
        }
    }
    return $state
}
function Assert-DshUnrelatedRuntime([string]$ProfileRoot,$Package,$Expected) {
    $actual=Get-DshUnrelatedRuntime $ProfileRoot $Package
    foreach ($name in $Expected.Keys) { if ($actual[$name] -ne $Expected[$name]) { throw "Unrelated installed package changed: $name" } }
}
function Invoke-DshProfileCli([string]$Cli,[string]$Profile,[string[]]$Arguments) {
    Assert-DshClosed
    $previous=$env:DSH_HOME
    try {
        $env:DSH_HOME=Join-Path $env:USERPROFILE '.dsh'
        & $Cli plugin --profile $Profile @Arguments
        if ($LASTEXITCODE -ne 0) { throw "Official DSH profile CLI failed with exit code $LASTEXITCODE" }
    } finally { $env:DSH_HOME=$previous }
}
function Assert-DshResolvedPlugin([string]$ProfileRoot,[string]$PluginRoot) {
    $resolved=Join-Path $ProfileRoot 'node_modules/dsh-mcm-team'
    foreach ($name in @('package.json','cordis.patch.yml')) {
        $a=Join-Path $resolved $name;$b=Join-Path $PluginRoot $name
        if (-not (Test-Path -LiteralPath $a -PathType Leaf) -or (Get-DshHash $a) -ne (Get-DshHash $b)) { throw "Profile does not resolve the expected MCM plugin bytes: $name" }
    }
}
function Restore-DshProfileFiles([string]$ProfileRoot,[string]$SavedRoot,$Expected,[string]$DisplacedRoot) {
    Assert-DshClosed
    New-Item -ItemType Directory -Path $DisplacedRoot -Force | Out-Null
    foreach ($name in $DshProfileFiles) {
        $destination=Join-Path $ProfileRoot $name
        if ($Expected[$name]) { Copy-Item -LiteralPath (Join-Path $SavedRoot $name) -Destination $destination -Force }
        elseif (Test-Path -LiteralPath $destination) { Move-Item -LiteralPath $destination -Destination (Join-Path $DisplacedRoot $name) }
    }
    Assert-DshProfileState $ProfileRoot $Expected
}
function Assert-DshBackup([string]$Backup,$Receipt) {
    if ($Receipt.format_version -ne 2 -or (Get-AbsoluteDshPath $Receipt.backup) -ne (Get-AbsoluteDshPath $Backup)) { throw 'Expected a v2 receipt bound to this exact backup directory.' }
    foreach ($name in $DshProfileFiles) { if (-not $Receipt.profile_state_before.Contains($name)) { throw "Missing profile snapshot state: $name" } }
    foreach ($key in $Receipt.profile_state_before.Keys) { if ($key -notin $DshProfileFiles) { throw "Unexpected profile snapshot filename: $key" } }
    Assert-DshTreeHashes (Join-Path $Backup 'plugin') $Receipt.plugin_hashes_before
    Assert-DshProfileState (Join-Path $Backup 'profile') $Receipt.profile_state_before
    $saved=Read-DshJson (Join-Path $Backup 'plugin/package.json')
    if ($saved.name -ne 'dsh-mcm-team' -or $saved.version -ne $Receipt.old_version) { throw 'Plugin backup identity differs from the receipt.' }
}
