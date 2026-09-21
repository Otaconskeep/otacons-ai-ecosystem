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

# Shared risk guide + medium/high preflight (network / disk / Docker).
$guidePath = Join-Path $KeepDir "TROUBLESHOOTING.txt"
$guideBody = @"
OTACONSKEEP EXPANSION - QUICK TROUBLESHOOTING
Generated: $(Get-Date -Format o)
Log: $LogFile

1) NETWORK (WSL cannot reach GitHub while Windows works)
   - Disconnect extra VPNs temporarily; fix Hyper-V dead routes
   - wsl --shutdown then: ping github.com inside Ubuntu
   - See also Lite Setup TROUBLESHOOTING.txt section 2

2) DISK (LTX-2 / 24GB GPUs need ~100 GB free)
   - Free space on C: / WSL drive; avoid storing models on /mnt/c

3) DOCKER (Video Studio / Comfy / Home Assistant)
   - Setup auto-installs via: winget -> official Installer.exe -> choco
   - Then waits for docker info (engine Ready) before continuing
   - If that still fails: docker.com + WSL Integration + reboot if asked
   - docker version inside your Ubuntu distro
   - Leave Docker Desktop Running before Set Up Video Studio

4) ENTITLEMENT / PREMIUM LOGIN
   - Exact username/email; hard-refresh Codec; re-run Expansion after login

5) GPU
   - Fix-Otacon-GPU.bat; never install Linux nvidia drivers inside WSL

6) HOME ASSISTANT
   - Expansion starts otacon-homeassistant on http://127.0.0.1:8123 after Docker
   - Open UI once, create account, paste long-lived token in Ops -> Home Assistant

Discord: https://discord.gg/cZDeqECzX
"@
try {
    [System.IO.File]::WriteAllText($guidePath, $guideBody, (New-Object System.Text.UTF8Encoding $false))
} catch {}

$netOk = $false
try {
    $netProbe = 'set +e; (getent hosts github.com >/dev/null 2>&1 && echo OK); (curl -fsSI --max-time 8 https://github.com >/dev/null 2>&1 && echo OK)'
    $netOut = & wsl.exe -d $distro -- bash -lc $netProbe 2>$null
    if (($netOut | Out-String) -match 'OK') { $netOk = $true }
} catch {}
if (-not $netOk) {
    Write-Host ""
    Write-Host " ################################################################" -ForegroundColor Red
    Write-Host " #  !!!  ACTION REQUIRED - NETWORK  !!!" -ForegroundColor Red
    Write-Host " #  WSL CANNOT REACH GITHUB" -ForegroundColor Yellow
    Write-Host " ################################################################" -ForegroundColor Red
    Write-Host "     Expansion will likely fail until WSL can reach github.com." -ForegroundColor White
    Write-Host "  >>> YOU MUST: fix WSL DNS/VPN/route (see TROUBLESHOOTING.txt), then retry" -ForegroundColor Yellow
    Write-Host ("  Guide: {0}" -f $guidePath) -ForegroundColor DarkCyan
    Write-Host " ################################################################" -ForegroundColor Red
    Write-Host ""
    try { Write-Host "  Press Enter to try Expansion anyway..." -ForegroundColor Cyan; [void](Read-Host) } catch { Start-Sleep -Seconds 5 }
}

$freeGb = -1
try {
    $drv = Get-PSDrive -Name C -ErrorAction SilentlyContinue
    if ($drv) { $freeGb = [math]::Round(([double]$drv.Free) / 1GB, 1) }
} catch {}
if ($freeGb -ge 0 -and $freeGb -lt 100) {
    Write-Host ""
    Write-Host " ################################################################" -ForegroundColor Red
    Write-Host " #  !!!  ACTION REQUIRED - DISK  !!!" -ForegroundColor Red
    Write-Host (" #  LOW FREE SPACE ON C: (~{0} GB) - LTX NEEDS ~100 GB" -f $freeGb) -ForegroundColor Yellow
    Write-Host " ################################################################" -ForegroundColor Red
    Write-Host "  >>> YOU MUST: free disk space before large Studio pack downloads" -ForegroundColor Yellow
    Write-Host ("  Guide: {0}" -f $guidePath) -ForegroundColor DarkCyan
    Write-Host " ################################################################" -ForegroundColor Red
    Write-Host ""
    try { Write-Host "  Press Enter to continue anyway..." -ForegroundColor Cyan; [void](Read-Host) } catch { Start-Sleep -Seconds 4 }
}

$dockerReady = $false
function Update-ExpDockerPath {
    try {
        $machine = [Environment]::GetEnvironmentVariable("Path", "Machine")
        $user = [Environment]::GetEnvironmentVariable("Path", "User")
        if ($machine -or $user) { $env:Path = (@($machine, $user) | Where-Object { $_ }) -join ";" }
        foreach ($e in @(
            (Join-Path $env:ProgramFiles "Docker\Docker\resources\bin"),
            (Join-Path $env:ProgramFiles "Docker\Docker"),
            (Join-Path $env:ProgramData "DockerDesktop\version-bin")
        )) {
            if ($e -and (Test-Path -LiteralPath $e) -and ($env:Path -notlike "*$e*")) { $env:Path = "$e;$env:Path" }
        }
    } catch {}
}
function Test-ExpDockerPresent {
    Update-ExpDockerPath
    try { if (Get-Command docker -ErrorAction SilentlyContinue) { return $true } } catch {}
    foreach ($p in @(
        (Join-Path $env:ProgramFiles "Docker\Docker\Docker Desktop.exe"),
        (Join-Path ${env:ProgramFiles(x86)} "Docker\Docker\Docker Desktop.exe")
    )) { if ($p -and (Test-Path -LiteralPath $p)) { return $true } }
    return $false
}
function Test-ExpDockerEngineReady {
    Update-ExpDockerPath
    try {
        $docker = Get-Command docker -ErrorAction SilentlyContinue
        if (-not $docker) { return $false }
        $out = Join-Path $env:TEMP "otacon-exp-docker-info-out.txt"
        $err = Join-Path $env:TEMP "otacon-exp-docker-info-err.txt"
        $p = Start-Process -FilePath $docker.Source -ArgumentList @("info") -Wait -PassThru -NoNewWindow `
            -RedirectStandardOutput $out -RedirectStandardError $err
        return ($p.ExitCode -eq 0)
    } catch { return $false }
}
function Start-ExpDockerDesktop {
    $exe = Join-Path $env:ProgramFiles "Docker\Docker\Docker Desktop.exe"
    if (-not (Test-Path -LiteralPath $exe)) {
        $exe = Join-Path ${env:ProgramFiles(x86)} "Docker\Docker\Docker Desktop.exe"
    }
    if (-not (Test-Path -LiteralPath $exe)) { return $false }
    try { Start-Process -FilePath $exe -ErrorAction SilentlyContinue | Out-Null } catch {}
    try { Start-Service -Name "com.docker.service" -ErrorAction SilentlyContinue | Out-Null } catch {}
    return $true
}
function Wait-ExpDockerEngineReady {
    param([int]$TimeoutSec = 300, [int]$PollSec = 5)
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    $n = 0
    while ((Get-Date) -lt $deadline) {
        $n++
        [void](Start-ExpDockerDesktop)
        Update-ExpDockerPath
        if (Test-ExpDockerEngineReady) {
            Write-ExpLog "Docker engine ready after ~$($n * $PollSec)s"
            return $true
        }
        if (($n % 6) -eq 1) {
            Write-Host ("  Still waiting for Docker engine... ({0}s elapsed)" -f ($n * $PollSec)) -ForegroundColor DarkCyan
        }
        Start-Sleep -Seconds $PollSec
    }
    return $false
}

Update-ExpDockerPath
if (Test-ExpDockerPresent) {
    [void](Start-ExpDockerDesktop)
    if (Wait-ExpDockerEngineReady -TimeoutSec 120) { $dockerReady = $true }
}

if (-not $dockerReady -and -not (Test-ExpDockerPresent)) {
    Write-Host ""
    Write-Host " ################################################################" -ForegroundColor Cyan
    Write-Host " #  DOCKER DESKTOP MISSING - INSTALLING AUTOMATICALLY            #" -ForegroundColor Cyan
    Write-Host " #  Path 1: winget  2: official installer  3: chocolatey         #" -ForegroundColor Cyan
    Write-Host " #  Leave this window open (several minutes)                     #" -ForegroundColor Yellow
    Write-Host " ################################################################" -ForegroundColor Cyan
    Write-Host ""
    Write-OtaconSay "Docker Desktop is required for Video Studio. I'm installing it for you..." "work"

    # Path 1: winget
    $winget = $null
    try { $winget = (Get-Command winget -ErrorAction SilentlyContinue).Source } catch {}
    if (-not $winget) {
        $wg = Join-Path $env:LOCALAPPDATA "Microsoft\WindowsApps\winget.exe"
        if (Test-Path -LiteralPath $wg) { $winget = $wg }
    }
    if ($winget) {
        try {
            Start-Process -FilePath $winget -ArgumentList @("source", "update", "--disable-interactivity") -Wait -PassThru -NoNewWindow | Out-Null
        } catch {}
        try {
            $p = Start-Process -FilePath $winget -ArgumentList @(
                "install", "-e", "--id", "Docker.DockerDesktop",
                "--accept-package-agreements", "--accept-source-agreements",
                "--disable-interactivity", "--scope", "machine"
            ) -Wait -PassThru -NoNewWindow
            Write-ExpLog ("winget Docker.DockerDesktop exit={0}" -f $p.ExitCode)
        } catch {
            Write-ExpLog ("winget docker install error: {0}" -f $_.Exception.Message)
        }
        Update-ExpDockerPath
    }

    # Path 2: official silent installer
    if (-not (Test-ExpDockerPresent)) {
        $url = "https://desktop.docker.com/win/main/amd64/Docker%20Desktop%20Installer.exe"
        $destDir = Join-Path $env:LOCALAPPDATA "OtaconsKeep\installer"
        $dest = Join-Path $destDir "DockerDesktopInstaller.exe"
        try { New-Item -ItemType Directory -Force -Path $destDir | Out-Null } catch {}
        Write-OtaconSay "Downloading official Docker Desktop installer..." "work"
        $dlOk = $false
        try {
            if (Get-Command curl.exe -ErrorAction SilentlyContinue) {
                & curl.exe -L --retry 3 --retry-delay 2 -o $dest -- $url
                if ((Test-Path -LiteralPath $dest) -and ((Get-Item -LiteralPath $dest).Length -gt 1MB)) { $dlOk = $true }
            }
        } catch {}
        if (-not $dlOk) {
            try {
                Invoke-WebRequest -Uri $url -OutFile $dest -UseBasicParsing -TimeoutSec 600
                if ((Test-Path -LiteralPath $dest) -and ((Get-Item -LiteralPath $dest).Length -gt 1MB)) { $dlOk = $true }
            } catch {
                Write-ExpLog ("direct docker download failed: {0}" -f $_.Exception.Message)
            }
        }
        if ($dlOk) {
            try {
                $p2 = Start-Process -FilePath $dest -ArgumentList @(
                    "install", "--quiet", "--accept-license", "--backend=wsl-2"
                ) -Wait -PassThru -NoNewWindow
                Write-ExpLog ("DockerDesktopInstaller exit={0}" -f $p2.ExitCode)
            } catch {
                Write-ExpLog ("DockerDesktopInstaller error: {0}" -f $_.Exception.Message)
            }
            Update-ExpDockerPath
        }
    }

    # Path 3: chocolatey
    if (-not (Test-ExpDockerPresent)) {
        $choco = $null
        try { $choco = (Get-Command choco -ErrorAction SilentlyContinue).Source } catch {}
        if ($choco) {
            try {
                $p3 = Start-Process -FilePath $choco -ArgumentList @("install", "docker-desktop", "-y", "--no-progress") -Wait -PassThru -NoNewWindow
                Write-ExpLog ("choco docker-desktop exit={0}" -f $p3.ExitCode)
            } catch {
                Write-ExpLog ("choco docker error: {0}" -f $_.Exception.Message)
            }
            Update-ExpDockerPath
        }
    }
}

if (Test-ExpDockerPresent) {
    [void](Start-ExpDockerDesktop)
    Write-OtaconSay "Waiting for Docker engine to become Ready..." "work"
    if (Wait-ExpDockerEngineReady -TimeoutSec 360) {
        $dockerReady = $true
        Write-Host " ################################################################" -ForegroundColor Green
        Write-Host " #  DOCKER ENGINE READY                                          #" -ForegroundColor Green
        Write-Host " ################################################################" -ForegroundColor Green
        Write-Host ""
    } else {
        Write-Host " ################################################################" -ForegroundColor Yellow
        Write-Host " #  DOCKER INSTALLED - ENGINE NOT READY YET                      #" -ForegroundColor Yellow
        Write-Host " #  Enable WSL Integration; reboot if Docker asks                #" -ForegroundColor Yellow
        Write-Host " ################################################################" -ForegroundColor Yellow
        Write-Host ""
        try { Write-Host "  Press Enter when Docker Desktop shows Running (or to continue)..." -ForegroundColor Cyan; [void](Read-Host) } catch { Start-Sleep -Seconds 8 }
        if (Wait-ExpDockerEngineReady -TimeoutSec 90) { $dockerReady = $true }
    }
} else {
    Write-Host ""
    Write-Host " ################################################################" -ForegroundColor Red
    Write-Host " #  !!!  ACTION REQUIRED - DOCKER  !!!" -ForegroundColor Red
    Write-Host " #  AUTOMATIC INSTALL DID NOT FINISH" -ForegroundColor Yellow
    Write-Host " ################################################################" -ForegroundColor Red
    Write-Host "     Tried winget + official installer + chocolatey." -ForegroundColor White
    Write-Host "     Foundation can still install; Video Studio needs Docker." -ForegroundColor White
    Write-Host "  >>> YOU MUST: install Docker Desktop from docker.com + WSL Integration" -ForegroundColor Yellow
    Write-Host ("  Guide: {0}" -f $guidePath) -ForegroundColor DarkCyan
    Write-Host " ################################################################" -ForegroundColor Red
    Write-Host ""
    try { Write-Host "  Press Enter to continue foundation install..." -ForegroundColor Cyan; [void](Read-Host) } catch { Start-Sleep -Seconds 4 }
}

# GPU hint: Expansion Studio packs need the same Windows->WSL bridge as Lite.
$gpuWin = "not visible"
$gpuWinVram = "0"
try {
    $o = & nvidia-smi --query-gpu=name --format=csv,noheader 2>$null
    if ($o) { $gpuWin = (($o | Select-Object -First 1).ToString().Trim()) }
} catch {}
try {
    $o2 = & nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits 2>$null
    if ($o2) {
        $mb = 0.0
        if ([double]::TryParse((($o2 | Select-Object -First 1).ToString().Trim()), [ref]$mb) -and $mb -gt 0) {
            $gpuWinVram = [string]([math]::Round($mb / 1024.0, 1))
        }
    }
} catch {}
$gpuWsl = "not visible"
try {
    $probe = 'export PATH=/usr/lib/wsl/lib:$PATH; export LD_LIBRARY_PATH=/usr/lib/wsl/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}; SMI=$(command -v nvidia-smi 2>/dev/null); [ -z "$SMI" ] && [ -x /usr/lib/wsl/lib/nvidia-smi ] && SMI=/usr/lib/wsl/lib/nvidia-smi; [ -n "$SMI" ] && "$SMI" --query-gpu=name --format=csv,noheader 2>/dev/null | head -n1'
    $o3 = & wsl.exe -d $distro -- bash -lc $probe 2>$null
    if ($o3) { $s = ($o3 | Out-String).Trim(); if ($s) { $gpuWsl = $s } }
} catch {}
Write-ExpLog "GPU windows='$gpuWin' vram=$gpuWinVram wsl='$gpuWsl'"
if ($gpuWin -ne "not visible" -and $gpuWsl -eq "not visible") {
    Write-Host ""
    Write-Host " ################################################################" -ForegroundColor Red
    Write-Host " #  !!!  ACTION REQUIRED - GPU  !!!" -ForegroundColor Red
    Write-Host " #  WINDOWS SEES GPU - LINUX DOES NOT" -ForegroundColor Yellow
    Write-Host " ################################################################" -ForegroundColor Red
    Write-Host ("     Windows NVIDIA: {0}" -f $gpuWin) -ForegroundColor White
    Write-Host "     Linux (WSL): NOT VISIBLE" -ForegroundColor White
    Write-Host "     Expansion will CONTINUE with a Windows GPU hint." -ForegroundColor Yellow
    Write-Host "  >>> YOU MUST (after install): update NVIDIA driver, wsl --update && wsl --shutdown, then Fix-Otacon-GPU.bat" -ForegroundColor Yellow
    Write-Host " ################################################################" -ForegroundColor Red
    Write-Host ""
    Write-OtaconSay "Windows sees '$gpuWin' but WSL GPU is dark - continuing with hint. Fix-Otacon-GPU.bat if Studio still says no GPU." "warn"
}
$gpuWinEsc = $gpuWin.Replace("'", "'\''")
$gpuVramEsc = $gpuWinVram.Replace("'", "'\''")

# Bash body: only expand PowerShell $linuxSh / $runTests; escape bash vars with backtick-dollar.
$bash = @"
set -Eeuo pipefail
echo "stage=expansion-foundation"
export OTACON_RUN_TESTS=$runTests
export OTACON_SKIP_NVIDIA_SMI=0
export OTACON_WINDOWS_GPU_HINT='$gpuWinEsc'
export OTACON_WINDOWS_GPU_VRAM_GB='$gpuVramEsc'
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
    $tip = "See the expansion installer log for the Linux error, then rerun Expansion Setup."
    $networkHint = $false
    if ($out -match 'EXP_FAIL=wsl_network' -or $out -match 'EXP_FAIL=git_fetch' `
        -or $out -match 'Could not resolve host' -or $out -match 'cannot_resolve_github' `
        -or $out -match 'WSL/Linux cannot reach github' -or $installExit -eq 128) {
        $networkHint = $true
        $tip = (
            "WSL/Linux cannot reach GitHub (DNS or default route). " +
            "Windows downloads can succeed while WSL has no internet - fix WSL networking " +
            "(.wslconfig / default route / VPN adapters), then rerun Expansion. " +
            "This is not a missing Lite install."
        )
    } elseif ($out -match 'EXP_FAIL=missing_install_script') {
        $tip = "Expansion install script missing from the bootstrap bundle. Re-download Expansion Setup and retry."
    } elseif ($out -match 'Core is not installed' -or $out -match 'no otacon-ai-ecosystem') {
        $tip = "Lite/Core was not found in WSL. Finish OtaconsKeep Lite first, then rerun Expansion Setup."
    } elseif ($out -match 'virtual environment wasn.t found' -or $out -match 'Re-run Core') {
        $tip = "Core's Python environment looks broken. Run OtaconsKeep-Setup.bat --fix-codec, then Expansion again."
    }
    Write-Host "  Tip: $tip"
    if ($networkHint) {
        Write-Host "  Note: Core was already healthy above - do not reinstall Lite for this error."
    }
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
    Write-Host ""
    Write-Host " ################################################################" -ForegroundColor Red
    Write-Host " #  !!!  ACTION REQUIRED - EXPANSION HEALTH  !!!" -ForegroundColor Red
    Write-Host " ################################################################" -ForegroundColor Red
    Write-Host ("  enabled={0}" -f $(if ($status) { $status.enabled } else { 'n/a' })) -ForegroundColor White
    Write-Host ("  foundation_ready={0}" -f $(if ($status) { $status.foundation_ready } else { 'n/a' })) -ForegroundColor White
    Write-Host ("  expansion_entitled={0}" -f $entitled) -ForegroundColor White
    Write-Host ("  agents={0}  missing={1}" -f $agentCount, ($missing -join ',')) -ForegroundColor White
    Write-Host ("  base={0}" -f $(if ($base) { $base } else { 'unreachable' })) -ForegroundColor White
    if ($out -match 'EXP_FAIL=wsl_network|cannot_resolve_github|git_fetch') {
        Write-Host "  Likely cause: WSL cannot reach GitHub (see TROUBLESHOOTING.txt section 1)." -ForegroundColor Yellow
    }
    Write-Host "  >>> YOU MUST: open the guide, fix network/GPU/Docker as listed, wait, then rerun Expansion Setup" -ForegroundColor Yellow
    Write-Host ("  Guide: {0}" -f (Join-Path $KeepDir "TROUBLESHOOTING.txt")) -ForegroundColor DarkCyan
    Write-Host ("  Log: {0}" -f $LogFile) -ForegroundColor DarkCyan
    Write-Host " ################################################################" -ForegroundColor Red
    Write-Host ""
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
    Write-Host ""
    Write-Host " ################################################################" -ForegroundColor Red
    Write-Host " #  !!!  ACTION REQUIRED - ENTITLEMENT  !!!" -ForegroundColor Red
    Write-Host " #  FOUNDATION OK - PREMIUM FEATURES STILL LOCKED" -ForegroundColor Yellow
    Write-Host " ################################################################" -ForegroundColor Red
    Write-Host ("     entitlement_reason={0}" -f $entMsg) -ForegroundColor White
    Write-Host "     War Room / REX / Learning stay locked until entitlement is true." -ForegroundColor White
    Write-Host "  >>> YOU MUST: log in with the exact Premium username/email Otaconskeep issued" -ForegroundColor Yellow
    Write-Host "      then hard-refresh Codec (Ctrl+Shift+R) and re-run Expansion Setup if needed" -ForegroundColor Yellow
    Write-Host ("  Guide: {0}" -f (Join-Path $KeepDir "TROUBLESHOOTING.txt")) -ForegroundColor DarkCyan
    Write-Host " ################################################################" -ForegroundColor Red
    Write-Host ""
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

# Desktop + Start Menu launcher (Lite may have created Open-Otacon.bat; Expansion upgrades label)
$launcherPs1 = Join-Path $InstDir "deploy\install-desktop-launcher.ps1"
if (-not (Test-Path -LiteralPath $launcherPs1)) {
    $launcherPs1 = Join-Path (Join-Path (Resolve-RepoRoot) "deploy") "install-desktop-launcher.ps1"
}
if (Test-Path -LiteralPath $launcherPs1) {
    $launchLabel = if ($entitled) { "OtaconsKeep Premium" } else { "OtaconsKeep" }
    $launchUrl = if ($base) { "$base/" } else { "http://127.0.0.1:$Port/" }
    try {
        Write-OtaconSay "Adding a Desktop launcher so you can open the Keep in one click..." "work"
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $launcherPs1 `
            -Port $Port -Url $launchUrl.TrimEnd('/') -Label $launchLabel | ForEach-Object { Write-ExpLog $_ }
    } catch {
        Write-ExpLog "desktop launcher warn: $($_.Exception.Message)"
    }
}

if ($OpenBrowser -and -not $Unattended -and $env:OTACON_UNATTENDED -ne "1") {
    try { Start-Process "$base/" } catch {}
}
exit 0
