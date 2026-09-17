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
    [switch]$Unattended,
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

function Test-CoreHealthAt([string]$Base) {
    # Branding alone is not Core-healthy - installer.server also brands.
    # Require semantic /api/health (memory usable) so Expansion doesn't install on a hollow listener.
    try {
        if (-not (Test-BrandAt $Base)) { return $false }
        $r = Invoke-WebRequest -Uri "$Base/api/health" -UseBasicParsing -TimeoutSec 6 -ErrorAction Stop
        if ($r.StatusCode -lt 200 -or $r.StatusCode -ge 300) { return $false }
        $j = $r.Content | ConvertFrom-Json
        if ($j.ok -ne $true) { return $false }
        if ([string]$j.product_name -and [string]$j.product_name -ne "Otacon") { return $false }
        return $true
    } catch { return $false }
}

function Find-WorkingBase([string]$Name, [int]$PortNum, [switch]$RequireHealth) {
    $bases = @("http://127.0.0.1:$PortNum")
    $ip = Get-WslIp $Name
    if ($ip -match '^\d{1,3}(\.\d{1,3}){3}$') { $bases += "http://${ip}:$PortNum" }
    foreach ($b in $bases) {
        if (Test-CoreHealthAt $b) { return $b }
        if (-not $RequireHealth -and (Test-BrandAt $b)) {
            # Older tips may lack /api/health until Expansion sync refreshes Core.
            Write-ExpLog ("branding-only base={0} (semantic /api/health not ready yet)" -f $b)
            return $b
        }
    }
    return $null
}

function Get-ExpansionStatus([string]$Base) {
    try {
        $r = Invoke-WebRequest -Uri "$Base/api/expansion/status" -UseBasicParsing -TimeoutSec 8 -ErrorAction Stop
        return ($r.Content | ConvertFrom-Json)
    } catch {
        Write-ExpLog ("Get-ExpansionStatus failed base={0} err={1}" -f $Base, $_.Exception.Message)
        return $null
    }
}

function Wait-ExpansionHealthy([string]$Name, [int]$PortNum, [int]$Seconds) {
    $deadline = (Get-Date).AddSeconds([Math]::Max(15, $Seconds))
    $lastBase = $null
    $lastStatus = $null
    $attempt = 0
    do {
        $attempt++
        $base = Find-WorkingBase -Name $Name -PortNum $PortNum -RequireHealth
        if (-not $base) {
            Write-ExpLog ("health wait attempt={0} brand=unreachable" -f $attempt)
            Start-Sleep -Seconds 2
            continue
        }
        $lastBase = $base
        $status = Get-ExpansionStatus $base
        $lastStatus = $status
        $n = 0
        if ($status -and $status.agents) { $n = @($status.agents).Count }
        $en = if ($status) { $status.enabled } else { $false }
        $fr = if ($status) { $status.foundation_ready } else { $false }
        Write-ExpLog ("health wait attempt={0} base={1} enabled={2} foundation_ready={3} agents={4}" -f $attempt, $base, $en, $fr, $n)
        if ($status -and $en -and $fr -and $n -ge 5) {
            return @{ Base = $base; Status = $status }
        }
        # After service restart the brand may answer before Expansion status is loaded.
        Start-Sleep -Seconds 3
    } while ((Get-Date) -lt $deadline)
    return @{ Base = $lastBase; Status = $lastStatus }
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
try {
    $hr = Invoke-WebRequest -Uri "$base/api/health" -UseBasicParsing -TimeoutSec 4 -ErrorAction Stop
    $hj = $hr.Content | ConvertFrom-Json
    if ($hj.ok -eq $true) {
        Write-OtaconSay "Core is healthy (branding + /api/health). I'm adding the Expansion systems now..." "work"
    } else {
        Write-OtaconSay "Core is answering, but /api/health is not ok yet. Continuing - Expansion sync refreshes Core." "warn"
    }
} catch {
    Write-OtaconSay "Core branding is up. Semantic /api/health not on this tip yet - Expansion sync will refresh Core." "work"
}

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
# Honor -SkipTests. Default: run Expansion suite inside WSL (same as Linux).
# Pass -SkipTests to skip when iterating; foundation+API still verified below.
if ($PSBoundParameters.ContainsKey('SkipTests')) {
    $runTests = if ($SkipTests) { "0" } else { "1" }
} else {
    $runTests = "1"
}
if ($Unattended -or $env:OTACON_UNATTENDED -eq "1") {
    $OpenBrowser = $false
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

# Service just restarted inside the Linux helper; give Core time, then wake + poll.
Start-Sleep -Seconds 4
$wake = Join-Path $InstDir "deploy\wake-otacon.ps1"
if (-not (Test-Path -LiteralPath $wake)) {
    $wake = Join-Path (Join-Path (Resolve-RepoRoot) "deploy") "wake-otacon.ps1"
}
if ($wake -and (Test-Path -LiteralPath $wake)) {
    Write-ExpLog "post-install wake via $wake"
    try { & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $wake -DistroName $distro -Port $Port | Out-Null } catch {}
    Start-Sleep -Seconds 2
}

$waitSecs = [Math]::Max(90, $TimeoutSeconds)
$healthy = Wait-ExpansionHealthy -Name $distro -PortNum $Port -Seconds $waitSecs
$base = $healthy.Base
$status = $healthy.Status

# One extra wake+retry if install markers looked good but the API was still cold.
if ((-not $status -or -not $status.enabled -or -not $status.foundation_ready) -and $out -match 'EXP_FOUNDATION_READY=1') {
    Write-ExpLog "API cold after foundation markers; second wake+wait"
    if ($wake -and (Test-Path -LiteralPath $wake)) {
        try { & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $wake -DistroName $distro -Port $Port | Out-Null } catch {}
    }
    Start-Sleep -Seconds 5
    $healthy = Wait-ExpansionHealthy -Name $distro -PortNum $Port -Seconds 60
    $base = $healthy.Base
    $status = $healthy.Status
}

$agentCount = 0
if ($status -and $status.agents) { $agentCount = @($status.agents).Count }
$names = @()
if ($status -and $status.agents) {
    $names = @($status.agents | ForEach-Object { $_.display_name })
}

Write-ExpLog ("status enabled={0} foundation_ready={1} entitled={2} agents={3} base={4}" -f `
    $(if ($status) { $status.enabled } else { 'null' }), `
    $(if ($status) { $status.foundation_ready } else { 'null' }), `
    $(if ($status -and $status.expansion_entitled) { $status.expansion_entitled } elseif ($status -and $status.entitlement) { $status.entitlement.entitled } else { 'null' }), `
    $agentCount, `
    $(if ($base) { $base } else { 'null' }))

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
    Write-Host ("  base={0}" -f $(if ($base) { $base } else { 'unreachable' }))
    Write-Host ("  linux_markers EXP_FOUNDATION_READY / EXP_AGENT_COUNT in log: $LogFile")
    if ($out -match 'EXP_FOUNDATION_READY=(\d+)') { Write-Host ("  EXP_FOUNDATION_READY={0}" -f $Matches[1]) }
    if ($out -match 'EXP_AGENT_COUNT=(\d+)') { Write-Host ("  EXP_AGENT_COUNT={0}" -f $Matches[1]) }
    if ($out -match 'EXP_SERVICE_ACTIVE=(\S+)') { Write-Host ("  EXP_SERVICE_ACTIVE={0}" -f $Matches[1]) }
    Write-Host "  Tip: wait a few seconds and rerun deploy\install-otacon-expansion.ps1 (no reinstall needed)."
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
$story = $null
if ($status -and $status.report) { $story = $status.report.ready_story }
if ($story) { Write-Host ("   ready_story={0}" -f $story) }
$ocr = $false
if ($status -and $status.report) { $ocr = [bool]$status.report.overall_core_ready }
Write-Host ("   overall_core_ready={0} (foundation/entitled can be true while VOICE/etc. still LIMITED)" -f $ocr)
Write-Host " ============================================================"
Write-Host ""
if ($entitled) {
    Write-OtaconSay "Foundation is online and entitled. Talk to Aria - she learns on chat turns." "ok"
} else {
    Write-OtaconSay "Foundation installed. Entitlement is false - open entitlement API for the reason." "warn"
}
Write-ExpLog "SUCCESS foundation_ready=1 entitled=$entitled overall_core_ready=$ocr"

if ($OpenBrowser -and -not $Unattended -and $env:OTACON_UNATTENDED -ne "1") {
    try { Start-Process "$base/" } catch {}
}
exit 0
