# Otacon Expansion Windows installer.
# Detects Core Keep, runs install_otacon_expansion.sh via temp .sh transport,
# verifies /api/expansion/status. No hardcoded usernames or home paths.
#
# Usage:
#   powershell -File deploy\install-otacon-expansion.ps1
# Or via OtaconExpansion-Setup.bat

[CmdletBinding()]
param(
    [string]$DistroName = "",
    [int]$Port = 5757,
    [string]$RepoRoot = "",
    [string]$Branch = "main",
    [string]$RawBase = "",
    [switch]$SkipTests,
    [switch]$OpenBrowser,
    [int]$TimeoutSeconds = 180
)

$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"

$KeepDir = Join-Path $env:LOCALAPPDATA "OtaconsKeep"
$LogDir = Join-Path $KeepDir "Logs"
$InstDir = Join-Path $KeepDir "installer"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$LogFile = Join-Path $LogDir "expansion-installer.log"

function Write-ExpLog([string]$Message) {
    $line = "$(Get-Date -Format o)  $Message"
    try { Add-Content -LiteralPath $LogFile -Value $line -Encoding utf8 } catch {}
}

function Write-OtaconSay {
    param([string]$Text, [string]$Mood = "work")
    Write-Host ""
    Write-Host " [OTACON] $Text"
    Write-ExpLog "[$Mood] $Text"
}

function Get-CandidateDistros {
    try {
        $raw = & wsl.exe -l -q 2>$null
        return @(
            $raw | ForEach-Object { ($_ -replace "`0", "").Trim() } |
                Where-Object {
                    $_ -ne "" -and
                    $_ -notmatch '(?i)^docker-desktop|^docker-desktop-data|^podman-machine' -and
                    $_ -match '(?i)Ubuntu|Otacon|OtaconsKeep'
                }
        )
    } catch { return @() }
}

function Resolve-Distro {
    param([string]$Preferred)
    if ($Preferred) {
        $hit = Get-CandidateDistros | Where-Object { $_.Equals($Preferred, [StringComparison]::OrdinalIgnoreCase) } | Select-Object -First 1
        if ($hit) { return $hit }
    }
    foreach ($want in @("Ubuntu-Otacon", "OtaconsKeep", "Ubuntu-22.04", "Ubuntu-24.04")) {
        $hit = Get-CandidateDistros | Where-Object { $_.Equals($want, [StringComparison]::OrdinalIgnoreCase) } | Select-Object -First 1
        if ($hit) { return $hit }
    }
    $family = @(Get-CandidateDistros | Where-Object { -not $_.Equals("Ubuntu", [StringComparison]::OrdinalIgnoreCase) })
    if ($family.Count -gt 0) { return $family[0] }
    $stock = @(Get-CandidateDistros | Where-Object { $_.Equals("Ubuntu", [StringComparison]::OrdinalIgnoreCase) } | Select-Object -First 1)
    if ($stock.Count -gt 0) { return $stock[0] }
    return $null
}

function Get-WslIp([string]$Name) {
    try {
        $raw = (& wsl.exe -d $Name -- hostname -I 2>$null | Out-String).Trim()
        if (-not $raw) { return "" }
        return ($raw -split '\s+')[0]
    } catch { return "" }
}

function Test-BrandAt([string]$Base) {
    try {
        $r = Invoke-WebRequest -Uri "$Base/api/branding" -UseBasicParsing -TimeoutSec 4 -ErrorAction Stop
        if ($r.StatusCode -lt 200 -or $r.StatusCode -ge 300) { return $false }
        $j = $r.Content | ConvertFrom-Json
        return ([string]$j.product_name -eq "Otacon")
    } catch { return $false }
}

function Find-WorkingBase([string]$Name, [int]$PortNum) {
    $bases = @("http://127.0.0.1:$PortNum")
    $ip = Get-WslIp $Name
    if ($ip -match '^\d{1,3}(\.\d{1,3}){3}$') { $bases += "http://${ip}:$PortNum" }
    foreach ($b in $bases) { if (Test-BrandAt $b) { return $b } }
    return $null
}

function Get-ExpansionStatus([string]$Base) {
    try {
        $r = Invoke-WebRequest -Uri "$Base/api/expansion/status" -UseBasicParsing -TimeoutSec 8 -ErrorAction Stop
        return ($r.Content | ConvertFrom-Json)
    } catch { return $null }
}

function Ensure-DistroRunning([string]$Name) {
    try { & wsl.exe -d $Name --exec /bin/true 2>$null | Out-Null } catch {}
    Start-Sleep -Seconds 1
    try {
        & wsl.exe -d $Name --exec /bin/true 2>$null | Out-Null
        return ($LASTEXITCODE -eq 0)
    } catch { return $false }
}

function Resolve-RepoRoot {
    if ($RepoRoot -and (Test-Path -LiteralPath (Join-Path $RepoRoot "deploy\wsl-bash-file.ps1"))) {
        return (Resolve-Path -LiteralPath $RepoRoot).Path
    }
    $here = $PSScriptRoot
    if ($here -and (Test-Path -LiteralPath (Join-Path $here "wsl-bash-file.ps1"))) {
        return (Resolve-Path -LiteralPath (Split-Path -Parent $here)).Path
    }
    if (Test-Path -LiteralPath (Join-Path $InstDir "deploy\wsl-bash-file.ps1")) {
        return $InstDir
    }
    return $null
}

Write-ExpLog "=== expansion installer begin ==="
Write-Host ""
Write-Host " ============================================================"
Write-Host "   OTACON EXPANSION SETUP"
Write-Host "   Otaconskeep Premium - Designed by Antonio G. Garcia"
Write-Host " ============================================================"
Write-Host ""

if (-not (Get-Command wsl.exe -ErrorAction SilentlyContinue)) {
    Write-OtaconSay "WSL is required. Install OtaconsKeep Lite first, then rerun Expansion Setup." "alert"
    exit 2
}

$distro = Resolve-Distro -Preferred $DistroName
if (-not $distro) {
    Write-OtaconSay "I could not find your OtaconsKeep Ubuntu. Install Lite first (OtaconsKeep-Setup.bat)." "alert"
    exit 2
}
Write-ExpLog "distro=$distro"
if (-not (Ensure-DistroRunning $distro)) {
    Write-OtaconSay "Your Keep distro would not start ($distro)." "alert"
    exit 3
}

Write-OtaconSay "I found your existing Keep ($distro)." "ok"

$base = Find-WorkingBase -Name $distro -PortNum $Port
if (-not $base) {
    Write-OtaconSay "Core is installed but not answering yet. Trying a gentle wake..." "work"
    $wake = Join-Path $InstDir "deploy\wake-otacon.ps1"
    if (-not (Test-Path -LiteralPath $wake)) {
        $wake = Join-Path (Join-Path (Resolve-RepoRoot) "deploy") "wake-otacon.ps1"
    }
    if ($wake -and (Test-Path -LiteralPath $wake)) {
        try { & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $wake -DistroName $distro -Port $Port | Out-Null } catch {}
        Start-Sleep -Seconds 3
        $base = Find-WorkingBase -Name $distro -PortNum $Port
    }
}
if (-not $base) {
    Write-OtaconSay "Core API is not healthy. Run OtaconsKeep-Setup.bat --fix-codec, then Expansion again." "alert"
    exit 4
}
Write-ExpLog "core_base=$base"
Write-OtaconSay "Core is healthy. I'm adding the Expansion systems now..." "work"

$root = Resolve-RepoRoot
if (-not $root) {
    Write-OtaconSay "Installer helpers are missing. Re-download Expansion Setup from the website." "alert"
    exit 5
}
$wslBash = Join-Path $root "deploy\wsl-bash-file.ps1"
if (-not (Test-Path -LiteralPath $wslBash)) {
    Write-OtaconSay "WSL transport helper missing. Re-download from the website." "alert"
    exit 5
}
. $wslBash

$expShWin = Join-Path $root "install_otacon_expansion.sh"
if (-not (Test-Path -LiteralPath $expShWin)) {
    if (-not $RawBase) {
        $RawBase = "https://raw.githubusercontent.com/Otaconskeep/otacons-ai-ecosystem/$Branch"
    }
    $url = "$RawBase/install_otacon_expansion.sh"
    Write-ExpLog "fetch expansion sh $url"
    try {
        New-Item -ItemType Directory -Force -Path $root | Out-Null
        Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $expShWin -TimeoutSec 60
    } catch {
        Write-OtaconSay "Could not download the Expansion foundation installer." "alert"
        Write-ExpLog "FAIL fetch: $($_.Exception.Message)"
        exit 6
    }
}
if (-not (Test-Path -LiteralPath $expShWin)) {
    Write-OtaconSay "Expansion foundation installer not found on disk." "alert"
    exit 6
}

$linuxSh = ConvertTo-OtaconLinuxPath -Distro $distro -WindowsPath $expShWin -User "root"
# Honor -SkipTests. Default (omitted): skip full suite; Windows verifies foundation+API.
# Pass -SkipTests:$false to run the Expansion unittest suite inside WSL.
if ($PSBoundParameters.ContainsKey('SkipTests')) {
    $runTests = if ($SkipTests) { "0" } else { "1" }
} else {
    $runTests = "0"
}

Write-OtaconSay "Setting up dossiers..." "work"
Write-OtaconSay "Initializing relationships..." "work"
Write-OtaconSay "Preparing journals and diaries..." "work"
Write-OtaconSay "Bringing the agent roster online..." "work"

# Bash body: only expand PowerShell $linuxSh / $runTests; escape bash vars with backtick-dollar.
$bash = @"
set -Eeuo pipefail
echo "stage=expansion-foundation"
export OTACON_RUN_TESTS=$runTests
SCRIPT='$linuxSh'
if [ ! -f "`$SCRIPT" ]; then
  echo "EXP_FAIL=missing_install_script"
  exit 6
fi
bash "`$SCRIPT"
EC=`$?
echo "EXP_INSTALL_EXIT=`$EC"
exit `$EC
"@

Write-ExpLog "Running Expansion foundation via temp .sh (not bash -lc)..."
$result = Invoke-OtaconWslBashFile -Distro $distro -ScriptBody $bash -User "root" -Label "otacon-expansion"
Write-ExpLog "stage=$($result.Stage) exit=$($result.ExitCode)"
Write-ExpLog ($result.Output)

$out = [string]$result.Output
$installExit = [int]$result.ExitCode
if ($out -match 'EXP_INSTALL_EXIT=(\d+)') {
    $installExit = [int]$Matches[1]
}

if ($installExit -ne 0 -and $installExit -ne 2) {
    Write-OtaconSay "Expansion foundation failed (exit $installExit). See log: $LogFile" "alert"
    Write-Host "  Tip: finish Lite install first, then rerun Expansion Setup."
    exit 7
}

if ($installExit -eq 2) {
    Write-OtaconSay "Roster written, but some foundation checks were soft-warn. Verifying APIs..." "warn"
} else {
    Write-OtaconSay "Foundation install finished. Verifying Expansion health..." "ok"
}

$deadline = (Get-Date).AddSeconds([Math]::Max(30, $TimeoutSeconds))
$status = $null
do {
    $base = Find-WorkingBase -Name $distro -PortNum $Port
    if ($base) { $status = Get-ExpansionStatus $base }
    if ($status -and $status.enabled -and $status.foundation_ready) { break }
    Start-Sleep -Seconds 2
} while ((Get-Date) -lt $deadline)

$agentCount = 0
if ($status -and $status.agents) { $agentCount = @($status.agents).Count }
$names = @()
if ($status -and $status.agents) {
    $names = @($status.agents | ForEach-Object { $_.display_name })
}

Write-ExpLog ("status enabled={0} foundation_ready={1} entitled={2} agents={3}" -f `
    $(if ($status) { $status.enabled } else { 'null' }), `
    $(if ($status) { $status.foundation_ready } else { 'null' }), `
    $(if ($status -and $status.expansion_entitled) { $status.expansion_entitled } elseif ($status -and $status.entitlement) { $status.entitlement.entitled } else { 'null' }), `
    $agentCount)

$need = @('Aria', 'Vector', 'Ledger', 'Muse', 'Sentry')
$missing = @($need | Where-Object { $names -notcontains $_ })

$entitled = $false
if ($status -and $null -ne $status.expansion_entitled) {
    $entitled = [bool]$status.expansion_entitled
} elseif ($status -and $status.entitlement) {
    $entitled = [bool]$status.entitlement.entitled
}

if (-not $status -or -not $status.enabled -or -not $status.foundation_ready -or $agentCount -lt 5 -or $missing.Count -gt 0) {
    Write-OtaconSay "Expansion foundation is not healthy yet." "alert"
    Write-Host ("  enabled={0}" -f $(if ($status) { $status.enabled } else { 'n/a' }))
    Write-Host ("  foundation_ready={0}" -f $(if ($status) { $status.foundation_ready } else { 'n/a' }))
    Write-Host ("  expansion_entitled={0}" -f $entitled)
    Write-Host ("  agents={0}  missing={1}" -f $agentCount, ($missing -join ','))
    Write-Host "  Log: $LogFile"
    exit 8
}

Write-Host ""
Write-Host " ============================================================"
if ($entitled) {
    Write-Host "   FOUNDATION INSTALLED + ENTITLED"
} else {
    Write-Host "   FOUNDATION INSTALLED"
}
Write-Host " ============================================================"
Write-Host "   enabled=true"
Write-Host "   foundation_ready=true"
Write-Host ("   expansion_entitled={0}" -f $entitled)
if (-not $entitled) {
    $entMsg = if ($status -and $status.entitlement) { $status.entitlement.message } else { 'check /api/expansion/entitlement' }
    Write-Host ("   entitlement_reason={0}" -f $entMsg)
    Write-Host "   War Room / REX / Learning stay locked until entitlement resolves."
}
Write-Host ("   agents: {0}" -f ($names -join ', '))
Write-Host "   Core remains healthy at $base"
Write-Host " ============================================================"
Write-Host ""
if ($entitled) {
    Write-OtaconSay "Foundation is online and entitled. Talk to Aria - she learns on chat turns." "ok"
} else {
    Write-OtaconSay "Foundation installed. Entitlement is false - open entitlement API for the reason." "warn"
}
Write-ExpLog "SUCCESS foundation_ready=1 entitled=$entitled"

if ($OpenBrowser) {
    try { Start-Process "$base/" } catch {}
}
exit 0
