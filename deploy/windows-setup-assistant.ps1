# OtaconsKeep Windows Setup Assistant
# Guided, nontechnical installer UX for Otacon Core on Windows 11.
# Invoked by OtaconsKeep-Setup.bat / install_otacon.bat - do not store credentials.

[CmdletBinding()]
param(
    [switch]$Status,
    [switch]$Diagnostics,
    [switch]$Open,
    [switch]$Resume,
    [switch]$Force,
    [switch]$Repair,
    [switch]$Reinstall,
    [string]$RepoRoot = "",
    [string]$Branch = "main",
    [string]$RawBase = "https://raw.githubusercontent.com/Otaconskeep/otacons-ai-ecosystem"
)

$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"

# ---------------------------------------------------------------------------
# Paths / constants
# ---------------------------------------------------------------------------
$KeepDir   = Join-Path $env:LOCALAPPDATA "OtaconsKeep"
$LogDir    = Join-Path $KeepDir "Logs"
$StateFile = Join-Path $KeepDir "installer-state.json"
$DiagDir   = Join-Path $KeepDir "Diagnostics"
$LogFile   = Join-Path $LogDir "installer.log"
$Port      = 5757
$HealthUrl = "http://127.0.0.1:$Port/"
$BrandUrl  = "http://127.0.0.1:$Port/api/branding"
$TotalSteps = 8
# Dedicated WSL distro - never silently mutate the user's first Ubuntu*.
$PreferredDistro = "Ubuntu-Otacon"
$PreferredDistroAliases = @("Ubuntu-Otacon", "OtaconsKeep")
# Script-scoped: when user chooses Repair/Reinstall/--force, skip early READY exit
# and do not treat an already-healthy install as "skip Step-InstallOtacon".
$script:ForceInstall = [bool]($Force -or $Repair -or $Reinstall)
$script:ChosenDistroMode = ""   # dedicated | reuse | ""
$script:ReinstallRequested = [bool]$Reinstall

New-Item -ItemType Directory -Force -Path $KeepDir, $LogDir, $DiagDir | Out-Null

if (-not $RepoRoot) {
    $RepoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
}

# P0-6: Prefer release.json ecosystem_ref over floating "main" when Branch was left default.
if ($Branch -eq "main") {
    $relPath = Join-Path $RepoRoot "release.json"
    if (Test-Path -LiteralPath $relPath) {
        try {
            $rel = Get-Content -LiteralPath $relPath -Raw | ConvertFrom-Json
            if ($rel.ecosystem_ref -and "$($rel.ecosystem_ref)" -ne "") {
                $Branch = [string]$rel.ecosystem_ref
            }
        } catch {}
    }
}

# ---------------------------------------------------------------------------
# Logging (no secrets)
# ---------------------------------------------------------------------------
function Write-KeepLog {
    param([string]$Message, [string]$Level = "INFO", [string]$Stage = "")
    $ts = Get-Date -Format "yyyy-MM-ddTHH:mm:ss.fffK"
    $line = "[$ts] [$Level] $(if($Stage){"[$Stage] "})$Message"
    Add-Content -Path $LogFile -Value $line -Encoding UTF8
}

function Get-InstallerState {
    $map = @{}
    if (-not (Test-Path $StateFile)) { return $map }
    try {
        $obj = Get-Content $StateFile -Raw | ConvertFrom-Json
        foreach ($p in $obj.PSObject.Properties) { $map[$p.Name] = $p.Value }
    } catch {}
    return $map
}

function Save-InstallerState {
    param([hashtable]$Fields)
    $cur = Get-InstallerState
    foreach ($k in $Fields.Keys) {
        # Explicit $null clears the key so COMPLETE cannot keep a stale last_error.
        if ($null -eq $Fields[$k]) {
            if ($cur.ContainsKey($k)) { [void]$cur.Remove($k) }
        } else {
            $cur[$k] = $Fields[$k]
        }
    }
    $cur["version"] = 1
    $cur["updated_at"] = (Get-Date).ToUniversalTime().ToString("o")
    ($cur | ConvertTo-Json -Depth 6) | Set-Content -Path $StateFile -Encoding UTF8
}

function Save-InstallerComplete {
    # Gate D/J: success must clear prior failure residue.
    Save-InstallerState @{
        stage      = "complete"
        step       = 8
        last_error = $null
        last_step  = "complete"
    }
}

# ---------------------------------------------------------------------------
# UI helpers
# ---------------------------------------------------------------------------
function Show-Banner {
    Clear-Host
    Write-Host ""
    Write-Host "============================================================" -ForegroundColor DarkYellow
    Write-Host "                 OTACONSKEEP SETUP" -ForegroundColor Yellow
    Write-Host "============================================================" -ForegroundColor DarkYellow
    Write-Host ""
    Write-Host "                 O T A C O N" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "          WINDOWS INSTALLATION ASSISTANT" -ForegroundColor White
    Write-Host ""
    Write-Host "============================================================" -ForegroundColor DarkYellow
    Write-Host ""
}

function Show-Box {
    param([string]$Title, [string[]]$Lines, [ConsoleColor]$Color = "Yellow")
    Write-Host ""
    Write-Host ("=" * 60) -ForegroundColor $Color
    Write-Host ("  {0}" -f $Title) -ForegroundColor $Color
    Write-Host ("=" * 60) -ForegroundColor $Color
    Write-Host ""
    foreach ($ln in $Lines) {
        if ($null -eq $ln) { Write-Host ""; continue }
        Write-Host ("  {0}" -f $ln)
    }
    Write-Host ""
    Write-Host ("=" * 60) -ForegroundColor $Color
    Write-Host ""
}

function Show-WorkingPanel {
    param(
        [int]$Step,
        [string]$StepName,
        [string]$Detail,
        [datetime]$Started,
        [string]$Typical = "a few minutes"
    )
    $elapsed = (Get-Date) - $Started
    $em = "{0:00}m {1:00}s" -f [int]$elapsed.TotalMinutes, $elapsed.Seconds
    Clear-Host
    Write-Host ""
    # Plain ASCII panel only -- CMD/console code pages break box-drawing glyphs.
    Write-Host ("+" + ("-" * 60) + "+") -ForegroundColor DarkYellow
    Write-Host ("|{0}|" -f ("OTACONSKEEP".PadLeft(35).PadRight(60))) -ForegroundColor Yellow
    Write-Host ("|{0}|" -f ("WINDOWS SETUP ASSISTANT".PadLeft(41).PadRight(60))) -ForegroundColor Yellow
    Write-Host ("+" + ("-" * 60) + "+") -ForegroundColor DarkYellow
    Write-Host ("|{0}|" -f ("").PadRight(60))
    $stepLabel = ("[{0}/{1}] {2}" -f $Step, $TotalSteps, $StepName.ToUpper())
    if ($stepLabel.Length -gt 58) { $stepLabel = $stepLabel.Substring(0, 58) }
    Write-Host ("|  {0}{1}|" -f $stepLabel, (" " * [Math]::Max(0, 58 - $stepLabel.Length))) -ForegroundColor Cyan
    Write-Host ("|{0}|" -f ("").PadRight(60))
    Write-Host ("|  Otacon is NOT ready yet{0}|" -f (" " * 35)) -ForegroundColor White
    Write-Host ("|{0}|" -f ("").PadRight(60))
    $detail = $Detail
    if ($detail.Length -gt 58) { $detail = $detail.Substring(0, 58) }
    Write-Host ("|  {0}{1}|" -f $detail, (" " * [Math]::Max(0, 58 - $detail.Length)))
    Write-Host ("|{0}|" -f ("").PadRight(60))
    Write-Host ("|  This is normal{0}|" -f (" " * 44))
    Write-Host ("|  Nothing has crashed{0}|" -f (" " * 39))
    Write-Host ("|  Do not close this window{0}|" -f (" " * 34)) -ForegroundColor Green
    Write-Host ("|{0}|" -f ("").PadRight(60))
    Write-Host ("|  Elapsed time     {0}{1}|" -f $em, (" " * [Math]::Max(0, 41 - $em.Length)))
    Write-Host ("|  Typical time     {0}{1}|" -f $Typical, (" " * [Math]::Max(0, 41 - $Typical.Length)))
    Write-Host ("|{0}|" -f ("").PadRight(60))
    Write-Host ("|  Your Ubuntu VM in Proxmox is separate{0}|" -f (" " * 21))
    Write-Host ("|  We prepare Ubuntu inside Windows automatically{0}|" -f (" " * 12))
    Write-Host ("|{0}|" -f ("").PadRight(60))
    Write-Host ("|{0}|" -f ("[ STILL WORKING ]".PadLeft(38).PadRight(60))) -ForegroundColor Green
    Write-Host ("|{0}|" -f ("").PadRight(60))
    Write-Host ("+" + ("-" * 60) + "+") -ForegroundColor DarkYellow
    Write-Host ""
}

function Read-Choice {
    param([string]$Prompt, [string[]]$Allowed)
    while ($true) {
        Write-Host -NoNewline $Prompt
        try {
            $k = [Console]::ReadKey($true)
            Write-Host $k.KeyChar
            $ch = ($k.KeyChar.ToString()).ToUpperInvariant()
            if ($Allowed -contains $ch) { return $ch }
            if ($k.Key -eq "Enter" -and ($Allowed -contains "ENTER")) { return "ENTER" }
        } catch {
            # No console (redirected/non-interactive): line input instead of ReadKey.
            $line = (Read-Host | Out-String).Trim()
            if ([string]::IsNullOrWhiteSpace($line) -and ($Allowed -contains "ENTER")) { return "ENTER" }
            if ($line.Length -ge 1) {
                $ch = $line.Substring(0, 1).ToUpperInvariant()
                if ($Allowed -contains $ch) { return $ch }
            }
        }
        Write-Host "  Please press one of: $($Allowed -join ', ')" -ForegroundColor DarkYellow
    }
}

function Invoke-WithHeartbeat {
    param(
        [scriptblock]$Script,
        [int]$Step,
        [string]$StepName,
        [string]$Detail,
        [string]$Typical = "5 to 15 minutes",
        [string]$Stage = "WORKING"
    )
    $started = Get-Date
    Save-InstallerState @{ stage = $Stage; step = $Step; step_name = $StepName }
    Write-KeepLog "begin: $StepName - $Detail" -Stage $Stage
    $job = Start-Job -ScriptBlock $Script
    try {
        while ($job.State -eq "Running") {
            Show-WorkingPanel -Step $Step -StepName $StepName -Detail $Detail -Started $started -Typical $Typical
            Write-Host "  [ OTACON ] still working - do not close this window" -ForegroundColor DarkGray
            Start-Sleep -Seconds 4
        }
        $result = Receive-Job $job -ErrorAction SilentlyContinue
        $ok = ($job.State -eq "Completed" -and -not $job.ChildJobs[0].Error)
        # Jobs that throw set Failed
        if ($job.State -eq "Failed") { $ok = $false }
        Write-KeepLog "end: $StepName state=$($job.State)" -Stage $Stage
        return @{ Ok = $ok; Output = $result; Job = $job }
    } finally {
        Remove-Job $job -Force -ErrorAction SilentlyContinue
    }
}

# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------
function Test-IsAdmin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    $p = New-Object Security.Principal.WindowsPrincipal($id)
    return $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Get-WslDistroState {
    param([string]$Name)
    try {
        $lines = & wsl.exe -l -v 2>$null | ForEach-Object { $_ -replace "`0", "" }
        foreach ($line in $lines) {
            $t = ("{0}" -f $line).Trim()
            if (-not $t -or $t -match '(?i)^NAME\s+STATE') { continue }
            # "* Ubuntu-22.04      Running         2"  or  "  Ubuntu            Stopped         2"
            if ($t -match '^\*?\s*(.+?)\s+(Running|Stopped|Starting|Installing)\s+(\d+)\s*$') {
                $n = $Matches[1].Trim()
                if ($n.Equals($Name, [System.StringComparison]::OrdinalIgnoreCase)) {
                    return $Matches[2]
                }
            }
        }
    } catch {}
    return "Unknown"
}

function Ensure-WslDistroRunning {
    <#
      wslpath / install phases require the distro to actually boot.
      A Stopped (or half-initialized) Ubuntu returns empty wslpath -> exit 997.
    #>
    param([string]$Name)
    $state = Get-WslDistroState -Name $Name
    Write-KeepLog "Ensure-WslDistroRunning name=$Name state=$state" -Stage "WSL"
    if ($state -eq "Running") { return $true }

    Write-KeepLog "starting WSL distro=$Name (was $state)" -Stage "WSL"
    try {
        # Cheap boot probe as root — works even when default user has no shell yet.
        & wsl.exe -d $Name -u root -- echo ok 1>$null 2>$null
    } catch {}
    Start-Sleep -Seconds 2
    $state2 = Get-WslDistroState -Name $Name
    if ($state2 -eq "Running") { return $true }

    # One more explicit start attempt
    try { & wsl.exe -d $Name --exec /bin/true 1>$null 2>$null } catch {}
    Start-Sleep -Seconds 2
    $state3 = Get-WslDistroState -Name $Name
    Write-KeepLog "Ensure-WslDistroRunning after-start state=$state3" -Stage "WSL"
    return ($state3 -eq "Running")
}

function Convert-WindowsPathToWsl {
    <#
      Map a Windows path into the distro. wslpath often returns empty when the
      target file does not exist yet (we delete exit markers before convert),
      so touch the path when needed and fall back to /mnt/<drive>/... mapping.
    #>
    param(
        [string]$Distro,
        [string]$WindowsPath,
        [switch]$EnsureExists
    )
    if (-not $WindowsPath) { return "" }
    if (-not (Ensure-WslDistroRunning -Name $Distro)) {
        Write-KeepLog "distro not running for wslpath distro=$Distro path=$WindowsPath" -Level "ERROR" -Stage "INSTALLING_OTACON"
        return ""
    }

    $full = $WindowsPath
    try { $full = [System.IO.Path]::GetFullPath($WindowsPath) } catch {}

    if ($EnsureExists) {
        try {
            $parent = [System.IO.Path]::GetDirectoryName($full)
            if ($parent -and -not (Test-Path -LiteralPath $parent)) {
                New-Item -ItemType Directory -Force -Path $parent | Out-Null
            }
            if (-not (Test-Path -LiteralPath $full)) {
                # Zero-byte placeholder so wslpath has a real inode to resolve.
                [System.IO.File]::WriteAllBytes($full, [byte[]]@())
            }
        } catch {
            Write-KeepLog "could not pre-create path for wslpath: $full err=$($_.Exception.Message)" -Level "WARN" -Stage "INSTALLING_OTACON"
        }
    }

    # 1) Native wslpath (prefer)
    foreach ($candidate in @($full, ($full -replace '\\', '/'))) {
        try {
            $out = & wsl.exe -d $Distro -u root -- wslpath -a $candidate 2>$null
            $line = @($out | ForEach-Object { ("{0}" -f $_).Trim() } | Where-Object { $_ -ne "" } | Select-Object -First 1)
            if ($line -and $line -match '^/') {
                Write-KeepLog "wslpath ok distro=$Distro win=$full wsl=$line" -Stage "INSTALLING_OTACON"
                return $line
            }
        } catch {}
    }

    # 2) Deterministic fallback: C:\foo\bar -> /mnt/c/foo/bar
    if ($full -match '^(?i)([A-Z]):[\\/](.*)$') {
        $drive = $Matches[1].ToLowerInvariant()
        $rest = ($Matches[2] -replace '\\', '/')
        $fallback = "/mnt/$drive/$rest"
        # Verify the mount is visible inside the distro
        try {
            $probe = & wsl.exe -d $Distro -u root -- bash -lc "test -d /mnt/$drive && echo OK" 2>$null
            if (("$probe".Trim()) -match 'OK') {
                Write-KeepLog "wslpath fallback distro=$Distro win=$full wsl=$fallback" -Level "WARN" -Stage "INSTALLING_OTACON"
                return $fallback
            }
        } catch {}
        Write-KeepLog "wslpath fallback unverified distro=$Distro win=$full wsl=$fallback (using anyway)" -Level "WARN" -Stage "INSTALLING_OTACON"
        return $fallback
    }

    Write-KeepLog "wslpath failed distro=$Distro path=$full" -Level "ERROR" -Stage "INSTALLING_OTACON"
    return ""
}

function Write-WslListVerbose {
    try {
        $list = & wsl.exe -l -v 2>$null | ForEach-Object { $_ -replace "`0", "" }
        Write-KeepLog ("wsl -l -v:`n" + (($list | Out-String).Trim())) -Stage "WSL"
    } catch {
        Write-KeepLog "wsl -l -v failed: $($_.Exception.Message)" -Level "WARN" -Stage "WSL"
    }
}

function Get-WslUbuntuFamilyNames {
    try {
        $raw = & wsl.exe -l -q 2>$null
        $clean = @(
            $raw | ForEach-Object { ($_ -replace "`0", "").Trim() } |
                Where-Object { $_ -ne "" -and $_ -notmatch '(?i)^docker-desktop|^docker-desktop-data|^podman-machine' }
        )
        return @($clean | Where-Object { $_ -match '(?i)Ubuntu|OtaconsKeep' })
    } catch { return @() }
}

function Get-UbuntuDistroName {
    # Prefer dedicated OtaconsKeep distro. Never silently return first Ubuntu*.
    $st = Get-InstallerState
    $stated = [string]$st["ubuntu_name"]
    $mode = [string]$st["ubuntu_mode"]
    if ($stated) {
        $isPreferred = [bool]($PreferredDistroAliases | Where-Object { $stated.Equals($_, [System.StringComparison]::OrdinalIgnoreCase) })
        if (($isPreferred -or $mode -eq "reuse") -and (Test-UbuntuReady $stated)) {
            return $stated
        }
    }
    $finder = Join-Path $RepoRoot "deploy\find-ubuntu.ps1"
    if (Test-Path $finder) {
        $name = & powershell -NoProfile -ExecutionPolicy Bypass -File $finder 2>$null
        if ($name) { return ($name | Select-Object -First 1).ToString().Trim() }
    }
    foreach ($want in $PreferredDistroAliases) {
        $family = Get-WslUbuntuFamilyNames
        $hit = $family | Where-Object { $_.Equals($want, [System.StringComparison]::OrdinalIgnoreCase) } | Select-Object -First 1
        if ($hit) { return $hit }
    }
    return $null
}

function Resolve-OtaconDistroInteractive {
    <#
      Gate E: existing Ubuntu is NOT silently mutated.
      Returns chosen distro name, or $null if aborted.
    #>
    Write-WslListVerbose
    $existing = Get-UbuntuDistroName
    if ($existing) {
        Write-KeepLog "using dedicated/known distro=$existing" -Stage "WSL"
        return $existing
    }

    $family = Get-WslUbuntuFamilyNames
    $others = @($family | Where-Object {
            $n = $_
            -not ($PreferredDistroAliases | Where-Object { $n.Equals($_, [System.StringComparison]::OrdinalIgnoreCase) })
        })

    if ($others.Count -eq 0) {
        # Virgin machine - create dedicated Ubuntu-Otacon
        $script:ChosenDistroMode = "dedicated"
        return $PreferredDistro
    }

    # Power-user PC with other Ubuntu* - require explicit choice
    $lines = @(
        "This PC already has Windows Linux (WSL) distributions:",
        ""
    )
    $idx = 1
    foreach ($d in $others) {
        $st = Get-WslDistroState -Name $d
        $mark = if ($st -eq "Running") { "RUNNING - prefer this" } else { $st.ToUpperInvariant() }
        $lines += ("  [{0}] {1}  ({2})" -f $idx, $d, $mark)
        $idx++
    }
    $lines += ""
    $lines += "Tip: pick a RUNNING Ubuntu if you have one (Stopped distros often fail)."
    $lines += "OtaconsKeep prefers a dedicated distro named $PreferredDistro"
    $lines += "so your existing Ubuntu is not silently changed."
    $lines += ""
    $lines += "[ R ] Reuse an existing distro (you choose which)"
    $lines += "[ C ] Create dedicated $PreferredDistro (side-by-side)"
    $lines += "[ A ] Abort setup"
    Show-Box "WSL DISTRIBUTION CHOICE" $lines -Color Yellow

    $c = Read-Choice "  Choice [R/C/A]: " @("R","C","A")
    if ($c -eq "A") {
        Write-KeepLog "user aborted WSL distro selection" -Stage "WSL"
        return $null
    }
    if ($c -eq "C") {
        $script:ChosenDistroMode = "dedicated"
        Write-KeepLog "user chose create dedicated $PreferredDistro" -Stage "WSL"
        return $PreferredDistro
    }

    # Reuse - pick which
    if ($others.Count -eq 1) {
        $script:ChosenDistroMode = "reuse"
        Save-InstallerState @{ ubuntu_name = $others[0]; ubuntu_mode = "reuse" }
        Write-KeepLog "user reused sole distro=$($others[0])" -Stage "WSL"
        return $others[0]
    }
    Write-Host "  Enter the number of the distro to reuse:" -ForegroundColor Cyan
    while ($true) {
        $raw = Read-Host "  Number"
        $n = 0
        if ([int]::TryParse($raw, [ref]$n) -and $n -ge 1 -and $n -le $others.Count) {
            $pick = $others[$n - 1]
            $script:ChosenDistroMode = "reuse"
            Save-InstallerState @{ ubuntu_name = $pick; ubuntu_mode = "reuse" }
            Write-KeepLog "user reused distro=$pick" -Stage "WSL"
            return $pick
        }
        Write-Host "  Invalid number." -ForegroundColor DarkYellow
    }
}

function Test-OtaconIdentity {
    <#
      Gate B/J: READY only when /api/branding positively identifies Otacon.
      Returns hashtable: ok, reason, product_name, occupied_non_otacon
    #>
    $result = @{
        ok                   = $false
        reason               = "unreachable"
        product_name         = ""
        occupied_non_otacon  = $false
        root_status          = $null
        brand_status         = $null
    }
    try {
        $root = Invoke-WebRequest -Uri $HealthUrl -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop
        $result.root_status = [int]$root.StatusCode
        if ($root.StatusCode -lt 200 -or $root.StatusCode -ge 500) {
            $result.reason = "root_bad_status"
            return $result
        }
    } catch {
        $result.reason = "root_unreachable"
        return $result
    }

    try {
        $b = Invoke-WebRequest -Uri $BrandUrl -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop
        $result.brand_status = [int]$b.StatusCode
        if ($b.StatusCode -lt 200 -or $b.StatusCode -ge 300) {
            $result.reason = "branding_bad_status"
            $result.occupied_non_otacon = $true
            return $result
        }
        $json = $null
        try { $json = $b.Content | ConvertFrom-Json } catch {
            $result.reason = "branding_invalid_json"
            $result.occupied_non_otacon = $true
            return $result
        }
        $pname = [string]($json.product_name)
        $result.product_name = $pname
        if ($pname -eq "Otacon") {
            $result.ok = $true
            $result.reason = "ok"
            return $result
        }
        $result.reason = "branding_wrong_product"
        $result.occupied_non_otacon = $true
        return $result
    } catch {
        # Root answered but branding missing/failed -> foreign service on 5757
        $result.reason = "branding_missing"
        $result.occupied_non_otacon = $true
        return $result
    }
}

function Test-OtaconHealth {
    $id = Test-OtaconIdentity
    return [bool]$id.ok
}

function Test-OtaconTts {
    <#
      P0-1: Voice engine must be reachable for green READY when Piper was installed.
      Returns hashtable: ok, reason, unit_active
    #>
    $result = @{ ok = $false; reason = 'unchecked'; unit_active = $false; preview_ok = $false }
    $ubuntu = Get-UbuntuDistroName
    if (-not $ubuntu) {
        $result.reason = 'no_distro'
        return $result
    }
    try {
        $unit = & wsl.exe -d $ubuntu -u root -- bash -lc "systemctl is-active otacon-tts.service 2>/dev/null || echo inactive" 2>$null
        $unitStr = (($unit | Out-String) -replace '\s+', '').Trim()
        $result.unit_active = ($unitStr -eq 'active')
    } catch {
        $result.unit_active = $false
    }
    # Preview / wyoming health via local API when Core is up
    try {
        $body = '{"text":"Otacon voice check.","purpose":"preview"}'
        $prev = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/api/preview_voice" `
            -Method POST -Body $body -ContentType 'application/json' `
            -UseBasicParsing -TimeoutSec 8 -ErrorAction Stop
        if ($prev.StatusCode -ge 200 -and $prev.StatusCode -lt 300) {
            $result.preview_ok = $true
            $result.ok = $true
            $result.reason = 'preview_ok'
            return $result
        }
    } catch {
        $result.reason = 'preview_unreachable'
    }
    if ($result.unit_active) {
        $result.ok = $true
        $result.reason = 'unit_active_preview_pending'
        return $result
    }
    # Piper never installed -> TTS not required for Core READY
    try {
        $draft = & wsl.exe -d $ubuntu -- bash -lc "test -f `$HOME/.config/otacon/otacon-tts.service.draft || test -d `$HOME/.config/otacon/piper; echo `$?" 2>$null
        if (($draft | Out-String).Trim() -match '1') {
            $result.ok = $true
            $result.reason = 'piper_not_configured'
            return $result
        }
    } catch {}
    $result.reason = 'tts_down'
    return $result
}

function Show-NonOtaconPortDiagnostic {
    param($Identity)
    Show-Box "PORT $Port OCCUPIED" @(
        "Port $Port is occupied by a non-Otacon service.",
        "",
        "Otacon identity check failed:",
        ("  {0}" -f $Identity.reason),
        $(if ($Identity.product_name) { "  product_name: $($Identity.product_name)" } else { "  /api/branding missing or invalid" }),
        "",
        "This installer will NOT kill the foreign process.",
        "",
        "Free or rebind port $Port, then rerun setup.",
        "",
        "press X to exit"
    ) -Color Red
    Write-KeepLog "non-otacon on :$Port reason=$($Identity.reason) product=$($Identity.product_name)" -Level "ERROR" -Stage "HEALTH"
    [void](Read-Choice "  Choice [X]: " @("X"))
}

function Test-WslPresent {
    try {
        $null = Get-Command wsl.exe -ErrorAction Stop
        & wsl.exe --status 2>$null | Out-Null
        return $true
    } catch { return $false }
}

function Test-UbuntuReady {
    param([string]$Name)
    if (-not $Name) { return $false }
    & wsl.exe -d $Name -- true 2>$null | Out-Null
    return ($LASTEXITCODE -eq 0)
}

function Test-OtaconFiles {
    param([string]$Name)
    if (-not $Name) { return $false }
    # Public Core markers only. Never treat /opt/otacon (private Keep) or
    # ~/otacon as proof of a product install.
    & wsl.exe -d $Name -- bash -lc "test -x `$HOME/.local/bin/otacon || test -d `"`${OTACON_INSTALL_DIR:-`$HOME/otacon-ai-ecosystem}/core`" || test -f `$HOME/.config/otacon/config.json" 2>$null | Out-Null
    return ($LASTEXITCODE -eq 0)
}

function Test-OtaconService {
    param([string]$Name)
    if (-not $Name) { return $false }
    $out = & wsl.exe -d $Name -- bash -lc "systemctl is-active otacon 2>/dev/null || true" 2>$null
    return (($out | Out-String) -match "active")
}

function Get-WhereYouAre {
    $admin = Test-IsAdmin
    $wsl = Test-WslPresent
    $ubuntu = Get-UbuntuDistroName
    $ubuntuReady = Test-UbuntuReady $ubuntu
    $files = Test-OtaconFiles $ubuntu
    $svc = Test-OtaconService $ubuntu
    $identity = Test-OtaconIdentity
    $health = [bool]$identity.ok
    $tts = Test-OtaconTts
    $state = Get-InstallerState
    $rebootPending = $false
    try {
        $rb = Test-Path "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Component Based Servicing\RebootPending"
        $wu = Test-Path "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\RebootRequired"
        if ($rb -or $wu) { $rebootPending = $true }
    } catch {}
    # Stale installer-state "waiting_for_reboot" must not stick after Ubuntu is
    # already usable (friend wall: overall=WAITING_FOR_REBOOT with ubuntu=True).
    # Trust the marker only when Windows still reports a reboot-required key, or
    # when Ubuntu is not ready yet (real post-feature reboot path).
    if ($state["stage"] -eq "waiting_for_reboot") {
        if ($ubuntuReady -and -not $rebootPending) {
            $rebootPending = $false
        } else {
            $rebootPending = $true
        }
    }

    # Gate J: never COMPLETE with unresolved fatal installer error
    $staleFail = ($state["stage"] -eq "failed") -or (
        $state["last_error"] -and $state["stage"] -ne "complete"
    )

    $overall = "WORKING"
    if ($identity.occupied_non_otacon) { $overall = "PORT_CONFLICT" }
    elseif ($health -and $files -and $tts.ok -and -not $staleFail) { $overall = "COMPLETE" }
    elseif ($health -and $files -and -not $tts.ok) { $overall = "DEGRADED_TTS" }
    elseif (-not $wsl -or $rebootPending) { $overall = if ($rebootPending) { "WAITING_FOR_REBOOT" } else { "WAITING_FOR_WINDOWS" } }
    elseif ($wsl -and -not $ubuntuReady) { $overall = "WAITING_FOR_UBUNTU_SETUP" }
    elseif ($ubuntuReady -and -not $files) { $overall = "INSTALLING_OTACON" }
    elseif ($files -and -not $health) { $overall = "VERIFYING" }
    elseif ($health -and -not $staleFail) { $overall = "READY" }

    return [ordered]@{
        admin                 = $admin
        wsl                   = $wsl
        ubuntu_name           = $ubuntu
        ubuntu_ready          = $ubuntuReady
        otacon_files          = $files
        otacon_service        = $svc
        web_health            = $health
        tts_ok                = [bool]$tts.ok
        tts_reason            = $tts.reason
        tts_unit_active       = [bool]$tts.unit_active
        identity_ok           = $health
        identity_reason       = $identity.reason
        occupied_non_otacon   = [bool]$identity.occupied_non_otacon
        reboot_pending        = $rebootPending
        overall               = $overall
        state_stage           = $state["stage"]
        last_error            = $state["last_error"]
    }
}

function Show-WhereYouAre {
    param($Snap)
    $wslL = if ($Snap.wsl) { "ready" } else { "not ready" }
    $rbL  = if ($Snap.reboot_pending) { "still required" } else { "not needed" }
    $ubL  = if ($Snap.ubuntu_ready) { "ready ($($Snap.ubuntu_name))" } elseif ($Snap.ubuntu_name) { "installed but not finished setup" } else { "not ready yet" }
    $otL  = if ($Snap.web_health) { "running" } elseif ($Snap.otacon_files) { "installed (starting)" } else { "not installed yet" }
    $webL = if ($Snap.web_health) { "responding" } else { "not available yet" }
    $ttsL = if ($Snap.tts_ok) { "ok ($($Snap.tts_reason))" } else { "down ($($Snap.tts_reason))" }

    $next = "please wait - setup will continue"
    if ($Snap.overall -eq "DEGRADED_TTS") {
        $next = "voice engine is down - choose Repair to restore Piper TTS"
    } elseif ($Snap.overall -eq "COMPLETE" -and $Snap.web_health -and $Snap.tts_ok) {
        $next = "open http://localhost:$Port - Otacon is ready"
    } elseif ($Snap.web_health -and -not $Snap.tts_ok) {
        $next = "chat may work but voice is down - Repair recommended"
    } elseif ($Snap.reboot_pending) {
        $next = "restart Windows, then this installer continues"
    } elseif (-not $Snap.ubuntu_ready) {
        $next = "finish the one-time Ubuntu username/password prompts if Windows shows them"
    } elseif (-not $Snap.otacon_files) {
        $next = "install Otacon inside Windows Ubuntu (automatic)"
    } elseif (-not $Snap.web_health) {
        $next = "start Otacon and wait for the website health check"
    }

    Show-Box "WHERE YOU ARE" @(
        "windows linux support      $wslL",
        "restart                    $rbL",
        "ubuntu (inside Windows)    $ubL",
        "otacon                     $otL",
        "website                    $webL",
        "voice (piper tts)          $ttsL",
        "",
        "overall state              $($Snap.overall)",
        "",
        "nothing is broken",
        "",
        "next step",
        "",
        $next,
        "",
        "Note: an Ubuntu VM in Proxmox is SEPARATE and is not used here."
    ) -Color Cyan
    Write-KeepLog "where-you-are overall=$($Snap.overall) wsl=$($Snap.wsl) ubuntu=$($Snap.ubuntu_ready) health=$($Snap.web_health) tts=$($Snap.tts_ok)" -Stage "STATUS"
}

function Show-StatusReport {
    $s = Get-WhereYouAre
    Write-Host ""
    Write-Host "otaconskeep setup status" -ForegroundColor Yellow
    Write-Host ""
    Write-Host ("windows            {0}" -f $(if ($s.admin) { "admin session" } else { "ready (will ask for admin if needed)" }))
    Write-Host ("virtualization     {0}" -f $(if ($s.wsl -or $s.reboot_pending) { "ready/pending" } else { "needed" }))
    Write-Host ("wsl                {0}" -f $(if ($s.wsl) { "ready" } else { "missing" }))
    Write-Host ("ubuntu             {0}" -f $(if ($s.ubuntu_ready) { "ready" } elseif ($s.ubuntu_name) { "needs setup" } else { "missing" }))
    Write-Host ("otacon files       {0}" -f $(if ($s.otacon_files) { "ready" } else { "missing" }))
    Write-Host ("otacon service     {0}" -f $(if ($s.otacon_service) { "running" } else { "stopped/unknown" }))
    Write-Host ("web interface      {0}" -f $(if ($s.web_health) { "responding" } else { "not responding" }))
    Write-Host ("voice (piper tts)  {0}" -f $(if ($s.tts_ok) { "ok ($($s.tts_reason))" } else { "down ($($s.tts_reason))" }))
    Write-Host ("wake task          {0}" -f $(if (Test-WakeTaskRegistered) { "registered" } else { "missing" }))
    Write-Host ""
    Write-Host "overall status" -ForegroundColor Yellow
    Write-Host ""
    # P0-2: web alone is not READY - require identity + TTS when Piper configured
    if ($s.overall -eq "COMPLETE") {
        Write-Host "READY"
    } elseif ($s.overall -eq "DEGRADED_TTS") {
        Write-Host "DEGRADED (voice engine down - run Setup with --repair)"
    } elseif ($s.web_health -and -not $s.tts_ok) {
        Write-Host "DEGRADED_TTS"
    } else {
        Write-Host $s.overall
    }
    Write-Host ""
}

function Write-DiagnosticsFile {
    $s = Get-WhereYouAre
    $path = Join-Path $DiagDir ("otaconskeep-diagnostics-{0:yyyyMMdd-HHmmss}.txt" -f (Get-Date))
    $wslList = (& wsl.exe -l -v 2>&1 | Out-String)
    $lines = @(
        "OtaconsKeep diagnostics",
        "generated: $((Get-Date).ToUniversalTime().ToString('o'))",
        "computer: $env:COMPUTERNAME",
        "user: $env:USERNAME",
        "overall: $($s.overall)",
        "wsl: $($s.wsl)",
        "ubuntu_name: $($s.ubuntu_name)",
        "ubuntu_ready: $($s.ubuntu_ready)",
        "otacon_files: $($s.otacon_files)",
        "otacon_service: $($s.otacon_service)",
        "web_health: $($s.web_health)",
        "tts_ok: $($s.tts_ok)",
        "tts_reason: $($s.tts_reason)",
        "tts_unit_active: $($s.tts_unit_active)",
        "wake_task: $(Test-WakeTaskRegistered)",
        "reboot_pending: $($s.reboot_pending)",
        "",
        "--- wsl -l -v ---",
        $wslList,
        "",
        "--- installer-state.json ---",
        $(if (Test-Path $StateFile) { Get-Content $StateFile -Raw } else { "(none)" }),
        "",
        "--- last 80 log lines ---"
    )
    if (Test-Path $LogFile) {
        $lines += Get-Content $LogFile -Tail 80
    } else {
        $lines += "(no log yet)"
    }
    $lines | Set-Content -Path $path -Encoding UTF8
    Write-Host "Diagnostics saved to:" -ForegroundColor Green
    Write-Host "  $path"
    return $path
}

# ---------------------------------------------------------------------------
# Failure UI
# ---------------------------------------------------------------------------
function Get-DpkgFailureSummary {
    # Best-effort parse of the Linux installer's log tail for a specific
    # broken-package signature, so the UI can name the actual package
    # instead of the generic "package state still broken after repair".
    # Never guesses: returns $null when nothing matches confidently.
    param([string]$LogPath)
    if (-not (Test-Path -LiteralPath $LogPath)) { return $null }
    $text = Get-Content -LiteralPath $LogPath -Raw -ErrorAction SilentlyContinue
    if (-not $text) { return $null }

    $package = $null
    $dpkgOp = $null
    $maintainerFailed = $false
    $exitCode = $null

    $m = [regex]::Match($text, 'dpkg:\s*error:?\s*processing package (\S+)\s*\(([^)]+)\)')
    if ($m.Success) {
        $package = $m.Groups[1].Value.Trim(':').Trim()
        $dpkgOp = $m.Groups[2].Value
    }
    $m2 = [regex]::Match($text, "package (\S+) \(--\S+\) returned error exit status (\d+)")
    if ($m2.Success) {
        if (-not $package) { $package = $m2.Groups[1].Value }
        $exitCode = $m2.Groups[2].Value
    }
    $m3 = [regex]::Match($text, "(post-installation|pre-removal|post-removal|pre-installation) script subprocess returned error exit status (\d+)")
    if ($m3.Success) {
        $maintainerFailed = $true
        if (-not $exitCode) { $exitCode = $m3.Groups[2].Value }
    }
    if (-not $package) {
        $m4 = [regex]::Match($text, 'Errors were encountered while processing:\s*\r?\n\s*(\S+)')
        if ($m4.Success) { $package = $m4.Groups[1].Value }
    }
    if (-not $package) {
        $m5 = [regex]::Match($text, '(?m)^Package:\r?\n([a-zA-Z0-9][a-zA-Z0-9+._-]+)')
        if ($m5.Success) { $package = $m5.Groups[1].Value }
    }
    if (-not $package) {
        $m6 = [regex]::Match($text, 'PACKAGE REPAIR FAILED pkg=(\S+)')
        if ($m6.Success -and $m6.Groups[1].Value -notmatch '^\(see') { $package = $m6.Groups[1].Value }
    }

    if (-not $package) { return $null }

    $lines = $text -split "`r?`n"
    $idx = -1
    for ($i = 0; $i -lt $lines.Length; $i++) {
        if ($lines[$i] -match [regex]::Escape($package) -and $lines[$i] -match 'dpkg|error') { $idx = $i; break }
    }
    $snippetStart = [Math]::Max(0, $idx - 2)
    $snippetEnd = if ($idx -ge 0) { [Math]::Min($lines.Length - 1, $idx + 5) } else { [Math]::Min($lines.Length - 1, $lines.Length - 1) }
    $snippet = if ($idx -ge 0) { ($lines[$snippetStart..$snippetEnd] -join "`n") } else { "" }

    return @{
        Package           = $package
        DpkgOp            = $dpkgOp
        MaintainerFailed  = $maintainerFailed
        ExitCode          = $exitCode
        Snippet           = $snippet
    }
}

function Show-PackageRepairFailed {
    param(
        [string]$Package,
        [string]$Problem,
        [string]$RepairAttempted,
        [string]$Result,
        [string]$LogPath
    )
    $lines = @(
        "Package:",
        $Package,
        "",
        "Problem:",
        $Problem,
        "",
        "Repair attempted:",
        $RepairAttempted,
        "",
        "Result:",
        $Result,
        "",
        "You do not need to reinstall Windows or Ubuntu.",
        "",
        "[R] retry repair",
        "[D] technical details",
        "[O] open logs",
        "[X] exit safely"
    )
    Write-KeepLog "PACKAGE_REPAIR_FAILED package=$Package problem=$Problem" -Level "ERROR" -Stage "FAILED"
    Save-InstallerState @{ stage = "failed"; last_error = "package repair failed: $Package"; last_step = "installing otacon" }
    while ($true) {
        Show-Box "PACKAGE REPAIR FAILED" $lines -Color Red
        $c = Read-Choice "  Choice [R/D/O/X]: " @("R", "D", "O", "X")
        if ($c -eq "D") {
            $detail = if (Test-Path -LiteralPath $LogPath) { Get-Content -LiteralPath $LogPath -Tail 60 -ErrorAction SilentlyContinue } else { @("(no log available at $LogPath)") }
            Show-Box "TECHNICAL DETAILS -- last 60 log lines" $detail -Color DarkYellow
            Write-Host "  Press any key to go back..." -ForegroundColor DarkGray
            [void][Console]::ReadKey($true)
            continue
        }
        if ($c -eq "O") { Start-Process explorer.exe $LogDir; continue }
        if ($c -eq "X") { return "exit" }
        if ($c -eq "R") { return "retry" }
    }
}

function ConvertTo-InstallerExitCode {
    <#
      PowerShell `exit ""` / `exit $null` becomes process exit 0 - which made the
      BAT log "Root bootstrap failed" then "assistant exit=0". Always emit an int.
    #>
    param($Code)
    $n = 0
    if ($null -eq $Code) { return 1 }
    if ($Code -is [int]) {
        if ($Code -eq 0) { return 0 }
        return [int]$Code
    }
    $s = [string]$Code
    if ([string]::IsNullOrWhiteSpace($s)) { return 1 }
    if ($s -eq "exit" -or $s -eq "failed") { return 1 }
    if ($s -eq "retry") { return 1 }
    if ([int]::TryParse($s, [ref]$n)) { return $n }
    return 1
}

function Show-SetupNeedsHelp {
    param([string]$Step, [string]$PlainError)
    Show-Box "SETUP NEEDS HELP" @(
        "otacon could not finish this step",
        "",
        "nothing was deleted",
        "",
        "step",
        $Step,
        "",
        "error",
        $PlainError,
        "",
        "technical details were saved here",
        "",
        $LogFile,
        "",
        "press R to retry this step",
        "press O to open the log folder",
        "press X to exit setup"
    ) -Color Red
    Write-KeepLog "FAILED step=$Step err=$PlainError" -Level "ERROR" -Stage "FAILED"
    Save-InstallerState @{ stage = "failed"; last_error = $PlainError; last_step = $Step }
    while ($true) {
        $c = Read-Choice "  Choice [R/O/X]: " @("R","O","X")
        if ($c -eq "O") { Start-Process explorer.exe $LogDir; continue }
        if ($c -eq "X") { return "exit" }
        if ($c -eq "R") { return "retry" }
    }
}

# ---------------------------------------------------------------------------
# Reboot / RunOnce
# ---------------------------------------------------------------------------
function Register-ResumeAfterReboot {
    $launcher = Join-Path $RepoRoot "OtaconsKeep-Setup.bat"
    if (-not (Test-Path -LiteralPath $launcher)) { $launcher = Join-Path $RepoRoot "install_otacon.bat" }
    # Quote for cmd.exe RunOnce; always pass --resume (Gate G).
    $cmd = '"' + $launcher + '" --resume'
    reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\RunOnce" /v OtaconsKeepSetupResume /t REG_SZ /d $cmd /f | Out-Null
    Save-InstallerState @{ stage = "waiting_for_reboot"; resume_registered = $true }
    Write-KeepLog "RunOnce registered for $cmd" -Stage "WAITING_FOR_REBOOT"
}

function Clear-ResumeMarkers {
    reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\RunOnce" /v OtaconsKeepSetupResume /f 2>$null | Out-Null
    Remove-Item (Join-Path $env:TEMP "otacon_installer_resumed.flag") -Force -ErrorAction SilentlyContinue
    $st = Get-InstallerState
    if ($st["stage"] -eq "waiting_for_reboot") {
        Save-InstallerState @{ stage = "working"; resume_registered = $false }
    }
}

function Request-RestartConfirmation {
    Show-Box "RESTART REQUIRED" @(
        "GOOD NEWS",
        "",
        "Everything is working normally",
        "",
        "Windows needs one restart before setup can continue",
        "",
        "OTACON IS NOT INSTALLED YET",
        "",
        "After you sign back into Windows",
        "this installer will automatically continue",
        "where it left off",
        "",
        "Save anything you are working on before restarting",
        "",
        "Your Proxmox Ubuntu VM is separate and will not be changed",
        "",
        "[ R ] RESTART NOW        [ L ] RESTART LATER"
    ) -Color Yellow
    Register-ResumeAfterReboot
    $c = Read-Choice "  Choice [R/L]: " @("R","L")
    if ($c -eq "R") {
        Write-KeepLog "user chose restart now" -Stage "WAITING_FOR_REBOOT"
        Write-Host "  Restarting Windows in a few seconds..." -ForegroundColor Yellow
        Start-Sleep -Seconds 2
        shutdown.exe /r /t 5 /c "OtaconsKeep setup needs one restart to finish Windows Linux support."
        return
    }
    Write-Host ""
    Write-Host "  OK - restart later when you can." -ForegroundColor Green
    Write-Host "  After you restart and sign in, setup should reopen by itself." -ForegroundColor Green
    Write-Host "  If it does not, double-click OtaconsKeep-Setup.bat again." -ForegroundColor Green
    Write-Host ""
    Write-Host "  Press any letter key to close this window (setup is paused, not failed)." -ForegroundColor DarkYellow
    [void][Console]::ReadKey($true)
}

# ---------------------------------------------------------------------------
# Open Otacon (launch guard)
# ---------------------------------------------------------------------------
function Open-OtaconIfReady {
    $s = Get-WhereYouAre
    if ($s.web_health) {
        Start-Process $HealthUrl
        return $true
    }
    Show-Box "HANG ON" @(
        "otacon isnt ready yet",
        "",
        "installation is currently at",
        "",
        "state: $($s.overall)",
        $(if ($s.ubuntu_ready) { "ubuntu: ready" } else { "ubuntu: not ready" }),
        $(if ($s.otacon_files) { "otacon files: present" } else { "otacon files: not installed" }),
        "",
        "launching the website now would not work",
        "",
        "continue installation instead",
        "",
        "press I to continue setup",
        "press X to exit"
    ) -Color Yellow
    $c = Read-Choice "  Choice [I/X]: " @("I","X")
    return ($c -eq "I")
}

# ---------------------------------------------------------------------------
# Core install steps
# ---------------------------------------------------------------------------
function Ensure-Admin {
    if (Test-IsAdmin) { return $true }
    Show-Box "ADMINISTRATOR PERMISSION" @(
        "Windows needs permission to enable Linux support.",
        "",
        "Click Yes on the next Windows popup.",
        "",
        "This does not install Otacon yet - it only unlocks the next step."
    ) -Color Yellow
    $bat = Join-Path $RepoRoot "OtaconsKeep-Setup.bat"
    if (-not (Test-Path -LiteralPath $bat)) { $bat = Join-Path $RepoRoot "install_otacon.bat" }
    # Pass --resume via ArgumentList (Gate G). Never concatenate into -Command.
    $elevateArgs = @("--resume")
    if ($script:ForceInstall) { $elevateArgs += "--force" }
    Start-Process -FilePath $bat -ArgumentList $elevateArgs -WorkingDirectory (Split-Path -Parent $bat) -Verb RunAs
    Write-Host ""
    Write-Host "  A new elevated Setup window should open after you click Yes." -ForegroundColor Green
    Write-Host "  You can close THIS window now - setup continues in the new one." -ForegroundColor Green
    Write-Host "  If you clicked No on the Windows popup, press X to exit, or R to try again." -ForegroundColor DarkYellow
    Write-Host ""
    while ($true) {
        $c = Read-Choice "  Choice [R/X]: " @("R","X")
        if ($c -eq "X") { return $false }
        if ($c -eq "R") {
            Start-Process -FilePath $bat -ArgumentList $elevateArgs -WorkingDirectory (Split-Path -Parent $bat) -Verb RunAs
            continue
        }
    }
}

function Step-EnableWsl {
    param([string]$DistroName = $PreferredDistro)
    Write-WslListVerbose
    Save-InstallerState @{ stage = "waiting_for_windows"; step = 3; target_distro = $DistroName }
    $started = Get-Date
    Show-WorkingPanel -Step 3 -StepName "PREPARING WINDOWS" -Detail "Windows is currently enabling Linux support" -Started $started -Typical "2 to 10 minutes"

    # Prefer dedicated name. Store Ubuntu may only offer "Ubuntu" - import path for side-by-side.
    $family = Get-WslUbuntuFamilyNames
    $already = $family | Where-Object { $_.Equals($DistroName, [System.StringComparison]::OrdinalIgnoreCase) } | Select-Object -First 1
    if ($already) {
        Write-KeepLog "distro already present: $already" -Stage "WAITING_FOR_WINDOWS"
        return 0
    }

    if ($DistroName -eq $PreferredDistro -and $family.Count -gt 0) {
        # Side-by-side dedicated create via Ubuntu WSL rootfs import
        $rc = Install-DedicatedUbuntuOtacon
        Write-KeepLog "dedicated import exit=$rc" -Stage "WAITING_FOR_WINDOWS"
        return $rc
    }

    Write-KeepLog "wsl --install -d Ubuntu (virgin path; will rename/use as dedicated when possible)" -Stage "WAITING_FOR_WINDOWS"
    $p = Start-Process -FilePath "wsl.exe" -ArgumentList "--install","-d","Ubuntu" -PassThru -NoNewWindow
    while (-not $p.HasExited) {
        Show-WorkingPanel -Step 3 -StepName "PREPARING WINDOWS" -Detail "Windows is currently enabling Linux support" -Started $started -Typical "2 to 10 minutes"
        Write-Host "  [ OTACON ] still working - do not close this window" -ForegroundColor DarkGray
        Start-Sleep -Seconds 4
    }
    Write-KeepLog "wsl --install exit=$($p.ExitCode)" -Stage "WAITING_FOR_WINDOWS"
    # On virgin machines the store distro is named Ubuntu - record intent for dedicated rename/import next run.
    if ($DistroName -eq $PreferredDistro) {
        Save-InstallerState @{ ubuntu_name = "Ubuntu"; ubuntu_mode = "virgin_ubuntu_pending_dedicated"; target_distro = $PreferredDistro }
    }
    return $p.ExitCode
}

function Install-DedicatedUbuntuOtacon {
    <#
      Create Ubuntu-Otacon beside existing Ubuntu* via rootfs import.
      Does not mutate existing distros.
    #>
    $destRoot = Join-Path $KeepDir "wsl\$PreferredDistro"
    $tarPath  = Join-Path $KeepDir "cache\ubuntu-wsl.rootfs.tar.gz"
    New-Item -ItemType Directory -Force -Path (Split-Path $destRoot), (Split-Path $tarPath) | Out-Null

    if (-not (Test-Path -LiteralPath $tarPath)) {
        $url = "https://cloud-images.ubuntu.com/wsl/releases/jammy/current/ubuntu-jammy-wsl-amd64-wsl.rootfs.tar.gz"
        Write-KeepLog "downloading Ubuntu WSL rootfs for $PreferredDistro from $url" -Stage "WAITING_FOR_WINDOWS"
        Write-Host "  Downloading dedicated Ubuntu image for $PreferredDistro ..." -ForegroundColor Cyan
        try {
            Invoke-WebRequest -Uri $url -OutFile $tarPath -UseBasicParsing -ErrorAction Stop
        } catch {
            Write-KeepLog "rootfs download failed: $($_.Exception.Message)" -Level "ERROR" -Stage "WAITING_FOR_WINDOWS"
            Show-Box "COULD NOT CREATE DEDICATED DISTRO" @(
                "Could not download the Ubuntu image for $PreferredDistro.",
                "",
                $_.Exception.Message,
                "",
                "You can Retry, or choose Reuse on the previous screen next time.",
                "",
                "Existing Ubuntu distributions were not changed."
            ) -Color Red
            return 1
        }
    }

    Write-KeepLog "wsl --import $PreferredDistro $destRoot $tarPath" -Stage "WAITING_FOR_WINDOWS"
    $p = Start-Process -FilePath "wsl.exe" -ArgumentList "--import",$PreferredDistro,$destRoot,$tarPath,"--version","2" -PassThru -NoNewWindow -Wait
    $code = $p.ExitCode
    if ($code -eq 0) {
        Save-InstallerState @{ ubuntu_name = $PreferredDistro; ubuntu_mode = "dedicated" }
    }
    return $code
}

function Step-WaitUbuntuInit {
    param([string]$Name)
    Show-Box "ONE SMALL WINDOWS SETUP STEP" @(
        "windows has installed ubuntu for otaconskeep",
        "",
        "this is NOT your proxmox ubuntu server",
        "",
        "windows may ask you to create",
        "",
        "a linux username",
        "a linux password",
        "",
        "this account only belongs to the local otaconskeep linux environment",
        "",
        "when linux asks for a password the screen will appear blank while you type",
        "THIS IS NORMAL",
        "your password is still being entered",
        "",
        "complete the prompts in the ubuntu window",
        "",
        "otaconskeep will continue after ubuntu is ready"
    ) -Color Cyan
    Save-InstallerState @{ stage = "waiting_for_ubuntu_setup"; ubuntu_name = $Name }
    try {
        Start-Process "wsl.exe" -ArgumentList "-d", $Name | Out-Null
    } catch {
        try { Start-Process "ubuntu.exe" } catch {}
    }
    $started = Get-Date
    Write-Host "  Waiting for Ubuntu inside Windows to finish first-time setup..." -ForegroundColor DarkYellow
    Write-Host "  (Proxmox Ubuntu is unrelated - ignore it for this installer.)" -ForegroundColor DarkGray
    for ($i = 0; $i -lt 180; $i++) {
        if (Test-UbuntuReady $Name) {
            Write-KeepLog "ubuntu ready: $Name" -Stage "WAITING_FOR_UBUNTU_SETUP"
            return $true
        }
        if (($i % 5) -eq 0) {
            Show-WorkingPanel -Step 4 -StepName "INSTALLING UBUNTU" -Detail "Waiting for Windows Ubuntu first-time setup" -Started $started -Typical "2 to 10 minutes"
            Write-Host "  [ OTACON ] still waiting for Ubuntu setup to finish" -ForegroundColor DarkGray
        }
        Start-Sleep -Seconds 3
        $Name = Get-UbuntuDistroName
        if (-not $Name) { continue }
    }
    return (Test-UbuntuReady (Get-UbuntuDistroName))
}

function Show-Stage6Panel {
    param(
        [datetime]$Started,
        [string]$Substep = "starting",
        [string[]]$RecentLines = @(),
        [datetime]$LastProgress,
        [string]$GpuWin = "unknown",
        [string]$GpuWsl = "unknown"
    )
    $elapsed = (Get-Date) - $Started
    $em = "{0:00}m {1:00}s" -f [int]$elapsed.TotalMinutes, $elapsed.Seconds
    $since = "n/a"
    if ($PSBoundParameters.ContainsKey('LastProgress') -and $LastProgress) {
        $sp = (Get-Date) - $LastProgress
        $since = ("{0:00}m {1:00}s ago" -f [int]$sp.TotalMinutes, $sp.Seconds)
    }
    Clear-Host
    Write-Host ""
    Write-Host ("+" + ("-" * 62) + "+") -ForegroundColor DarkYellow
    Write-Host ("|{0}|" -f ("OTACONSKEEP".PadLeft(36).PadRight(62))) -ForegroundColor Yellow
    Write-Host ("|{0}|" -f ("[6/8] INSTALLING OTACON".PadLeft(40).PadRight(62))) -ForegroundColor Cyan
    Write-Host ("+" + ("-" * 62) + "+") -ForegroundColor DarkYellow
    Write-Host ("|  Otacon is NOT ready yet{0}|" -f (" " * 37))
    Write-Host ("|  Do not close this window{0}|" -f (" " * 36)) -ForegroundColor Green
    Write-Host ("|{0}|" -f ("").PadRight(62))
    Write-Host ("|  Current substep:{0}|" -f (" " * 44))
    $sub = $Substep
    if ($sub.Length -gt 58) { $sub = $sub.Substring(0, 58) }
    Write-Host ("|    {0}{1}|" -f $sub, (" " * [Math]::Max(0, 58 - $sub.Length))) -ForegroundColor White
    Write-Host ("|{0}|" -f ("").PadRight(62))
    Write-Host ("|  Windows GPU : {0}{1}|" -f $GpuWin, (" " * [Math]::Max(0, 45 - $GpuWin.Length)))
    Write-Host ("|  WSL GPU     : {0}{1}|" -f $GpuWsl, (" " * [Math]::Max(0, 45 - $GpuWsl.Length)))
    Write-Host ("|  Elapsed     : {0}{1}|" -f $em, (" " * [Math]::Max(0, 45 - $em.Length)))
    Write-Host ("|  Last progress: {0}{1}|" -f $since, (" " * [Math]::Max(0, 44 - $since.Length)))
    Write-Host ("|{0}|" -f ("").PadRight(62))
    Write-Host ("|  Live log (tail):{0}|" -f (" " * 43))
    foreach ($t in $RecentLines) {
        if (-not $t) { continue }
        $line = $t.Trim()
        if ($line.Length -gt 58) { $line = $line.Substring(0, 58) }
        Write-Host ("|  > {0}{1}|" -f $line, (" " * [Math]::Max(0, 58 - $line.Length))) -ForegroundColor DarkGray
    }
    Write-Host ("+" + ("-" * 62) + "+") -ForegroundColor DarkYellow
}

function Get-WindowsNvidiaName {
    try {
        $o = & nvidia-smi --query-gpu=name --format=csv,noheader 2>$null
        if ($o) { return (($o | Select-Object -First 1).ToString().Trim()) }
    } catch {}
    return "not visible"
}

function Get-WslNvidiaName {
    param([string]$Name)
    try {
        $o = & wsl.exe -d $Name -- bash -lc "nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -n1" 2>$null
        if ($o) {
            $s = ($o | Out-String).Trim()
            if ($s) { return $s }
        }
    } catch {}
    return "not visible in WSL"
}

function Get-WslDefaultUser {
    param([string]$Name)
    $u = (& wsl.exe -d $Name -- bash -lc "whoami" 2>$null | Select-Object -Last 1)
    if ($u) { return ("{0}" -f $u).Trim() }
    return ""
}

function Invoke-WslInstallPhase {
    param(
        [string]$Name,
        [string]$Phase,
        [string]$AsUser,   # "" = default WSL user; "root" = -u root
        [string]$TargetUser,
        [string]$EnvPass,
        [datetime]$Started,
        [string]$GpuWin,
        [string]$GpuWsl,
        [string]$LogPipe,
        [int]$OverallTimeoutMin = 120,
        [int]$StallTimeoutMin = 25
    )

    $userArg = @()
    if ($AsUser -eq "root") {
        $userArg = @("-u", "root")
    } elseif ($AsUser -and $AsUser -ne "") {
        $userArg = @("-u", $AsUser)
    }

    $targetEnv = ""
    if ($TargetUser) { $targetEnv = "OTACON_TARGET_USER=$TargetUser" }

    # Prefer local package install_otacon.sh (pinned tree) over floating GitHub main.
    $localWin = Join-Path $RepoRoot "install_otacon.sh"
    $localWsl = ""
    if (Test-Path -LiteralPath $localWin) {
        $localWsl = Convert-WindowsPathToWsl -Distro $Name -WindowsPath $localWin -EnsureExists
    }
    $localEsc = if ($localWsl) { $localWsl.Replace("'", "'\''") } else { "" }

    # Write a LF phase script on disk and run `bash <path>`. Multiline
    # `bash -lc "..."` via Start-Process ArgumentList is fragile on Windows
    # (newlines/quoting), and Start-Process ExitCode can stay blank with
    # redirected stdout - which masked exit 42 (systemd enable -> terminate +
    # retry) as "Root bootstrap failed (exit )".
    $phaseScriptWin = Join-Path $LogDir ("wsl-phase-{0}.sh" -f $Phase)
    $exitMarkerWin = Join-Path $LogDir ("wsl-phase-{0}.exit" -f $Phase)
    foreach ($p in @($phaseScriptWin, $exitMarkerWin, $LogPipe)) {
        if (Test-Path -LiteralPath $p) {
            Remove-Item -LiteralPath $p -Force -ErrorAction SilentlyContinue
        }
    }

    # Pre-create exit marker so wslpath has a real file (empty wslpath on
    # missing paths is what produced exit 997 on Josh's Running Ubuntu).
    $exitMarkerWsl = Convert-WindowsPathToWsl -Distro $Name -WindowsPath $exitMarkerWin -EnsureExists
    if (-not $exitMarkerWsl) {
        $st = Get-WslDistroState -Name $Name
        Write-KeepLog "could not wslpath exit marker for phase=$Phase distro=$Name state=$st path=$exitMarkerWin" -Level "ERROR" -Stage "INSTALLING_OTACON"
        return 997
    }
    $exitMarkerEsc = $exitMarkerWsl.Replace("'", "'\''")

    # EnvPass is already a single-line KEY=VAL list from the caller.
    # Always emit_rc after the installer returns so Windows can read exit 42
    # (systemd enable) even when Start-Process ExitCode stays blank.
    $bashLines = @(
        '#!/bin/bash',
        'set -uo pipefail',
        ('EXIT_MARKER=''{0}''' -f $exitMarkerEsc),
        'emit_rc() { printf ''OTACON_PHASE_EXIT=%s\n'' "$1"; printf ''%s\n'' "$1" >"$EXIT_MARKER" 2>/dev/null || true; }',
        'TMP=$(mktemp /tmp/otacon-install.XXXXXX.sh)',
        'trap ''rm -f "$TMP"'' EXIT',
        ('LOCAL_SH=''{0}''' -f $localEsc),
        'if [ -n "$LOCAL_SH" ] && [ -s "$LOCAL_SH" ]; then',
        '  cp "$LOCAL_SH" "$TMP"',
        'else',
        ('  if ! curl -fsSL --connect-timeout 30 --max-time 120 https://raw.githubusercontent.com/Otaconskeep/otacons-ai-ecosystem/{0}/install_otacon.sh -o "$TMP"; then echo ''Download failed'' >&2; emit_rc 1; exit 1; fi' -f $Branch),
        'fi',
        'if [ ! -s "$TMP" ]; then echo ''Download failed or empty installer'' >&2; emit_rc 1; exit 1; fi',
        'if ! head -n1 "$TMP" | grep -q bash; then echo ''Downloaded file does not look like the Otacon installer'' >&2; emit_rc 1; exit 1; fi',
        'set +e',
        ('env {0} OTACON_INSTALL_PHASE={1} {2} bash "$TMP"' -f $EnvPass, $Phase, $targetEnv),
        'rc=$?',
        'emit_rc "$rc"',
        'exit "$rc"'
    )
    $bashText = ($bashLines -join "`n") + "`n"
    $utf8NoBom = New-Object System.Text.UTF8Encoding $false
    [System.IO.File]::WriteAllText($phaseScriptWin, $bashText, $utf8NoBom)

    $phaseScriptWsl = Convert-WindowsPathToWsl -Distro $Name -WindowsPath $phaseScriptWin -EnsureExists
    if (-not $phaseScriptWsl) {
        $st = Get-WslDistroState -Name $Name
        Write-KeepLog "could not wslpath phase script for phase=$Phase distro=$Name state=$st path=$phaseScriptWin" -Level "ERROR" -Stage "INSTALLING_OTACON"
        return 997
    }

    Write-KeepLog "starting linux phase=$Phase as=$AsUser target=$TargetUser in $Name branch=$Branch local=$([bool]$localWsl) script=$phaseScriptWsl" -Stage "INSTALLING_OTACON"

    # Run the file. Merge stderr inside bash - Windows cannot RedirectStandardOutput
    # and RedirectStandardError to the same path.
    $phaseScriptEsc = $phaseScriptWsl.Replace("'", "'\''")
    $runner = "bash '{0}' 2>&1" -f $phaseScriptEsc
    $argList = @("-d", $Name) + $userArg + @("--", "bash", "-c", $runner)
    $proc = Start-Process -FilePath "wsl.exe" -ArgumentList $argList `
        -NoNewWindow -PassThru -RedirectStandardOutput $LogPipe

    $lastProgress = Get-Date
    $lastByteLen = 0L
    $currentSub = "phase $Phase starting"
    # Overall timeout is per-phase, not from the start of Stage 6. Otherwise a
    # long privileged/user run (apt + voice trainer) immediately kills finalize
    # whose OverallTimeoutMin is only 15 minutes wall-clock from Stage 6 start.
    $phaseStarted = Get-Date

    while (-not $proc.HasExited) {
        $recent = @()
        if (Test-Path $LogPipe) {
            $item = Get-Item -LiteralPath $LogPipe -ErrorAction SilentlyContinue
            if ($item -and $item.Length -gt $lastByteLen) {
                $lastByteLen = $item.Length
                $lastProgress = Get-Date
            }
            $all = @(Get-Content $LogPipe -ErrorAction SilentlyContinue)
            foreach ($line in $all) {
                if ($line -match '\[STAGE\]\s+(\S+)\s+(\S+)\s+(.*)$') {
                    $currentSub = ("{0} [{1}] {2}" -f $Matches[1], $Matches[2], $Matches[3])
                    $lastProgress = Get-Date
                } elseif ($line -match '\[AGG::HEARTBEAT\]\s*(.+)$') {
                    $lastProgress = Get-Date
                    $hb = $Matches[1]
                    $currentSub = $hb.Substring(0, [Math]::Min(90, $hb.Length))
                } elseif ($line -match '\[AGG::PROGRESS\]\s*(.+)$') {
                    $lastProgress = Get-Date
                    $pg = $Matches[1]
                    $currentSub = $pg.Substring(0, [Math]::Min(90, $pg.Length))
                } elseif ($line -match '^(Get:|Hit:|Ign:|Fetched |Unpacking |Setting up |Processing triggers|Preparing to unpack)') {
                    $lastProgress = Get-Date
                    $t = $line.Trim()
                    $currentSub = $t.Substring(0, [Math]::Min(90, $t.Length))
                } elseif ($line -match 'pulling|Downloading|Enabling systemd|restart once') {
                    $lastProgress = Get-Date
                    $t = $line.Trim()
                    $currentSub = $t.Substring(0, [Math]::Min(90, $t.Length))
                }
            }
            $recent = @($all | Select-Object -Last 6)
        }

        Show-Stage6Panel -Started $Started -Substep ("[{0}] {1}" -f $Phase, $currentSub) -RecentLines $recent `
            -LastProgress $lastProgress -GpuWin $GpuWin -GpuWsl $GpuWsl

        $elapsedMin = ((Get-Date) - $phaseStarted).TotalMinutes
        $stallMin = ((Get-Date) - $lastProgress).TotalMinutes
        if ($elapsedMin -ge $OverallTimeoutMin) {
            try { Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue } catch {}
            Write-KeepLog "stage6 phase timeout ${OverallTimeoutMin}m phase=$Phase (phase-local clock)" -Level "ERROR" -Stage "INSTALLING_OTACON"
            return 124
        }
        if ($stallMin -ge $StallTimeoutMin) {
            try { Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue } catch {}
            Write-KeepLog "stage6 stall timeout ${StallTimeoutMin}m phase=$Phase substep=$currentSub" -Level "ERROR" -Stage "INSTALLING_OTACON"
            return 125
        }
        Start-Sleep -Seconds 3
    }

    # $proc.HasExited can flip true slightly before .NET has fully reaped the
    # process and populated ExitCode -- especially with redirected stdout
    # (-RedirectStandardOutput above), where the async reader thread needs to
    # finish draining first. Without WaitForExit(), .ExitCode has been
    # observed to read back as an unpopulated/blank value here, which is
    # exactly what produced "Root bootstrap failed (exit )" downstream.
    try {
        $proc.WaitForExit(15000) | Out-Null
    } catch {
        Write-KeepLog "WaitForExit threw for phase=$Phase : $($_.Exception.Message)" -Level "WARN" -Stage "INSTALLING_OTACON"
    }
    Start-Sleep -Milliseconds 200

    # Prefer durable markers: exit file > log line > Start-Process ExitCode.
    $fromMarker = $null
    if (Test-Path -LiteralPath $exitMarkerWin) {
        $rawMarker = (Get-Content -LiteralPath $exitMarkerWin -TotalCount 1 -ErrorAction SilentlyContinue)
        $tmpM = 0
        if ([int]::TryParse([string]$rawMarker, [ref]$tmpM)) { $fromMarker = $tmpM }
    }
    $fromLog = $null
    if (Test-Path -LiteralPath $LogPipe) {
        foreach ($line in @(Get-Content -LiteralPath $LogPipe -ErrorAction SilentlyContinue)) {
            if ($line -match 'OTACON_PHASE_EXIT=(\d+)') { $fromLog = [int]$Matches[1] }
            elseif ($line -match '\[STAGE\]\s+exit\s+CODE\s+(\d+)') { $fromLog = [int]$Matches[1] }
        }
    }

    $rawCode = $proc.ExitCode
    $code = 0
    if ($null -ne $fromMarker) {
        $code = [int]$fromMarker
    } elseif ($null -ne $fromLog) {
        $code = [int]$fromLog
    } elseif (-not [int]::TryParse([string]$rawCode, [ref]$code)) {
        Write-KeepLog "linux phase=$Phase exit code unreadable (raw='$rawCode') -- treating as failure, not blank" -Level "ERROR" -Stage "INSTALLING_OTACON"
        $code = 998
    }
    Write-KeepLog "linux phase=$Phase exit=$code (raw='$rawCode' marker='$fromMarker' log='$fromLog')" -Stage "INSTALLING_OTACON"

    if ($code -ne 0 -and $code -ne 42 -and (Test-Path -LiteralPath $LogPipe)) {
        Write-KeepLog "---- linux-install-tail (phase=$Phase, last 40) ----" -Level "ERROR" -Stage "INSTALLING_OTACON"
        foreach ($line in @(Get-Content -LiteralPath $LogPipe -Tail 40 -ErrorAction SilentlyContinue)) {
            Write-KeepLog $line -Level "ERROR" -Stage "LINUX_TAIL"
        }
    }
    return [int]$code
}

function Step-InstallOtacon {
    param([string]$Name)
    Save-InstallerState @{ stage = "installing_otacon"; step = 6; ubuntu_name = $Name }
    $started = Get-Date
    $gpuWin = Get-WindowsNvidiaName
    $gpuWsl = Get-WslNvidiaName -Name $Name
    Write-KeepLog "GPU windows='$gpuWin' wsl='$gpuWsl'" -Stage "INSTALLING_OTACON"

    # Elevation architecture: never configure NOPASSWD:ALL.
    # privileged + finalize run as WSL root via wsl.exe -u root; user phase runs as the normal account.
    $targetUser = Get-WslDefaultUser -Name $Name
    if (-not $targetUser -or $targetUser -eq "root") {
        Write-KeepLog "could not resolve non-root WSL default user (got='$targetUser')" -Level "ERROR" -Stage "INSTALLING_OTACON"
        Show-SetupNeedsHelp -Step "installing otacon (no default user)" -PlainError (
            "Could not determine the normal Ubuntu username. Finish Ubuntu first-run setup, then rerun OtaconsKeep Setup."
        ) | Out-Null
        return 1
    }
    Write-KeepLog "WSL default user=$targetUser (no NOPASSWD:ALL; using wsl -u root for privileged steps)" -Stage "INSTALLING_OTACON"

    Show-Stage6Panel -Started $started -Substep "Preparing Linux installer (root bootstrap)" -GpuWin $gpuWin -GpuWsl $gpuWsl -LastProgress $started

    $envPass = @(
        "OTACON_INSTALL_DEFAULT_MODEL=$($env:OTACON_INSTALL_DEFAULT_MODEL)",
        "OTACON_INSTALL_VOICE_TRAINER=$($env:OTACON_INSTALL_VOICE_TRAINER)",
        "OTACON_LLM_MODEL=$($env:OTACON_LLM_MODEL)",
        "OTACON_BUILD_NATIVE=$($env:OTACON_BUILD_NATIVE)",
        "OTACON_LAN_MODE=$($env:OTACON_LAN_MODE)",
        "OTACON_INSTALL_STT=$($env:OTACON_INSTALL_STT)",
        "OTACON_CHAT_HOST=$($env:OTACON_CHAT_HOST)",
        "OTACON_CHAT_PORT=$($env:OTACON_CHAT_PORT)",
        "OTACON_INSTALL_DIR=$($env:OTACON_INSTALL_DIR)",
        "OTACON_INSTALL_DEB=$($env:OTACON_INSTALL_DEB)",
        "OTACON_LAUNCH_WIZARD=$($env:OTACON_LAUNCH_WIZARD)",
        "OTACON_RUN_TESTS=$($env:OTACON_RUN_TESTS)",
        "OTACON_RELEASE=$($env:OTACON_RELEASE)"
    ) -join " "

    $logPipe = Join-Path $LogDir "linux-install-tail.log"
    $overallTimeoutMin = 120
    $stallTimeoutMin = 25
    if ($env:OTACON_STAGE6_OVERALL_MIN) { [void][int]::TryParse($env:OTACON_STAGE6_OVERALL_MIN, [ref]$overallTimeoutMin) }
    if ($env:OTACON_STAGE6_STALL_MIN) { [void][int]::TryParse($env:OTACON_STAGE6_STALL_MIN, [ref]$stallTimeoutMin) }

    # --- Phase 1: privileged (wsl -u root) ---
    $privAttempts = 0
    $userRepairRetries = 0
    while ($true) {
        $privAttempts++
        if ($privAttempts -gt 3) {
            Show-SetupNeedsHelp -Step "installing otacon (privileged)" -PlainError (
                "Privileged bootstrap kept requesting a WSL restart. Log: $logPipe"
            ) | Out-Null
            return 1
        }
        $code = Invoke-WslInstallPhase -Name $Name -Phase "privileged" -AsUser "root" -TargetUser $targetUser `
            -EnvPass $envPass -Started $started -GpuWin $gpuWin -GpuWsl $gpuWsl -LogPipe $logPipe `
            -OverallTimeoutMin $overallTimeoutMin -StallTimeoutMin $stallTimeoutMin
        if ($code -eq 42) {
            Write-Host "  Restarting the Windows Ubuntu environment once (systemd enable)..." -ForegroundColor Yellow
            & wsl.exe --terminate $Name 2>$null
            Start-Sleep -Seconds 3
            continue
        }
        if ($code -ne 0) {
            if (Test-Path $logPipe) {
                Write-Host "---- last 50 log lines (privileged) ----" -ForegroundColor Yellow
                Get-Content $logPipe -Tail 50 -ErrorAction SilentlyContinue | ForEach-Object { Write-Host $_ }
            }
            # This machine already progressed past Windows/WSL bootstrap into
            # real Linux package installation -- WSL/Ubuntu themselves are
            # fine. Never wipe/reinstall them here; only the failed package
            # state needs repair, and the existing WSL instance is reused
            # as-is on retry (Invoke-WslInstallPhase re-runs the same
            # installer against the same Ubuntu environment).
            $dpkgInfo = Get-DpkgFailureSummary -LogPath $logPipe
            if ($dpkgInfo) {
                $problem = if ($dpkgInfo.MaintainerFailed) {
                    "This package's own install script failed while configuring it" + $(if ($dpkgInfo.ExitCode) { " (exit $($dpkgInfo.ExitCode))" } else { "" }) + ". This is a package-specific problem, not a Windows or WSL problem."
                } else {
                    "dpkg could not finish setting up this package" + $(if ($dpkgInfo.DpkgOp) { " during $($dpkgInfo.DpkgOp)" } else { "" }) + "."
                }
                $act = Show-PackageRepairFailed -Package $dpkgInfo.Package -Problem $problem `
                    -RepairAttempted "dpkg --configure -a, then apt-get -f install -y (attempt $privAttempts)" `
                    -Result "Still not fully installed or removed after repair (exit $code)." `
                    -LogPath $logPipe
            } else {
                $hint997 = ""
                if ($code -eq 997) {
                    $st = Get-WslDistroState -Name $Name
                    $hint997 = " Windows could not map installer paths into WSL distro '$Name' (state=$st). Exit setup, then in PowerShell run: Remove-Item `"$env:LOCALAPPDATA\OtaconsKeep\installer-state.json`" -Force; then re-run OtaconsKeep-Setup.bat --update and choose Create dedicated Ubuntu-Otacon (or a RUNNING Ubuntu)."
                    # Forget the stuck reuse choice so the next launch re-asks.
                    try {
                        Save-InstallerState @{ ubuntu_name = ""; ubuntu_mode = ""; stage = "failed"; last_error = "wslpath/997" }
                    } catch {}
                }
                $act = Show-SetupNeedsHelp -Step "installing otacon (privileged bootstrap)" -PlainError (
                    "Root bootstrap failed (exit $code). No sudo password was required; this uses wsl -u root.$hint997 Log: $logPipe"
                )
            }
            if ($act -eq "retry" -and $userRepairRetries -lt 2) {
                $userRepairRetries++
                Write-Host "  Retrying the privileged install phase against the existing WSL environment..." -ForegroundColor Yellow
                continue
            }
            return (ConvertTo-InstallerExitCode $code)
        }
        break
    }

    # --- Phase 2: user (default WSL account) ---
    $code = Invoke-WslInstallPhase -Name $Name -Phase "user" -AsUser $targetUser -TargetUser $targetUser `
        -EnvPass $envPass -Started $started -GpuWin $gpuWin -GpuWsl $gpuWsl -LogPipe $logPipe `
        -OverallTimeoutMin $overallTimeoutMin -StallTimeoutMin $stallTimeoutMin
    if ($code -ne 0 -and $code -ne 2) {
        if (Test-Path $logPipe) {
            Write-Host "---- last 50 log lines (user) ----" -ForegroundColor Yellow
            Get-Content $logPipe -Tail 50 -ErrorAction SilentlyContinue | ForEach-Object { Write-Host $_ }
        }
        Show-SetupNeedsHelp -Step "installing otacon (user phase)" -PlainError (
            "User install phase failed (exit $code). Log: $logPipe"
        ) | Out-Null
        return (ConvertTo-InstallerExitCode $code)
    }
    $userCode = [int](ConvertTo-InstallerExitCode $code)
    if ($code -eq 2) { $userCode = 2 }

    # --- Phase 3: finalize (wsl -u root) - install systemd unit drafted by user phase ---
    $code = Invoke-WslInstallPhase -Name $Name -Phase "finalize" -AsUser "root" -TargetUser $targetUser `
        -EnvPass $envPass -Started $started -GpuWin $gpuWin -GpuWsl $gpuWsl -LogPipe $logPipe `
        -OverallTimeoutMin 15 -StallTimeoutMin 10
    if ($code -ne 0) {
        if (Test-Path $logPipe) {
            Write-Host "---- last 50 log lines (finalize) ----" -ForegroundColor Yellow
            Get-Content $logPipe -Tail 50 -ErrorAction SilentlyContinue | ForEach-Object { Write-Host $_ }
        }
        # P0-5: finalize soft-fail must NOT look like success. Durable systemd units
        # (otacon + otacon-tts) are installed only in finalize - never treat nohup as READY.
        Write-KeepLog "finalize failed exit=$code (user phase was $userCode) - hard FAIL" -Level "ERROR" -Stage "INSTALLING_OTACON"
        Save-InstallerState @{ stage = "failed"; last_error = "Finalize failed (exit $code). systemd units not durable." }
        Show-SetupNeedsHelp -Step "finalizing systemd services" -PlainError (
            "Finalize failed (exit $code). Otacon may be running temporarily but will not survive reboot. Log: $logPipe"
        ) | Out-Null
        return (ConvertTo-InstallerExitCode $code)
    }

    return [int]$userCode
}

function Test-WakeTaskRegistered {
    try {
        $task = Get-ScheduledTask -TaskName "OtaconAutoStart" -ErrorAction SilentlyContinue
        return [bool]$task
    } catch { return $false }
}

function Step-RegisterWakeTask {
    param([string]$Name)
    $ps1 = Join-Path $RepoRoot "deploy\install-wake-task.ps1"
    if (-not (Test-Path $ps1)) {
        Write-KeepLog "install-wake-task.ps1 missing - skip" -Level "WARN" -Stage "STARTING"
        return $false
    }
    # P0-3: Register-ScheduledTask needs elevation; surface errors (never Out-Null).
    $ok = $false
    $errText = ""
    try {
        $out = & powershell -NoProfile -ExecutionPolicy Bypass -File $ps1 -DistroName $Name -Port $Port 2>&1
        $ok = ($LASTEXITCODE -eq 0)
        if (-not $ok) { $errText = ($out | Out-String).Trim() }
    } catch {
        $ok = $false
        $errText = $_.Exception.Message
    }
    if (-not $ok -or -not (Test-WakeTaskRegistered)) {
        Write-KeepLog "wake task register failed: $errText - elevating" -Level "WARN" -Stage "STARTING"
        if (-not (Test-IsAdmin)) {
            if (-not (Ensure-Admin)) {
                Write-KeepLog "wake task: user declined elevation" -Level "ERROR" -Stage "STARTING"
                return $false
            }
        }
        try {
            $out2 = & powershell -NoProfile -ExecutionPolicy Bypass -File $ps1 -DistroName $Name -Port $Port 2>&1
            $ok = ($LASTEXITCODE -eq 0) -and (Test-WakeTaskRegistered)
            if (-not $ok) {
                Write-KeepLog "wake task still failed after elevation: $($out2 | Out-String)" -Level "ERROR" -Stage "STARTING"
                return $false
            }
        } catch {
            Write-KeepLog "wake task elevated register exception: $($_.Exception.Message)" -Level "ERROR" -Stage "STARTING"
            return $false
        }
    }
    # Also drop an Open Otacon launcher
    $openBat = Join-Path $KeepDir "Open-Otacon.bat"
    $assistant = Join-Path $RepoRoot "deploy\windows-setup-assistant.ps1"
    @"
@echo off
title Open Otacon
powershell -NoProfile -ExecutionPolicy Bypass -File "$assistant" -Open -RepoRoot "$RepoRoot"
"@ | Set-Content -Path $openBat -Encoding ASCII
    Write-KeepLog "wake task + Open-Otacon.bat registered ok=$(Test-WakeTaskRegistered)" -Stage "STARTING"
    return (Test-WakeTaskRegistered)
}

function Invoke-RepairTtsAndWake {
    <# P0-2 / P1-5: Repair path - promote TTS unit, start TTS+Core, register wake, spoken preview. #>
    param([string]$Name)
    Write-KeepLog "Repair: finalize TTS + wake + preview" -Stage "REPAIR"
    $targetUser = (& wsl.exe -d $Name -- bash -lc "whoami" 2>$null | Select-Object -First 1)
    if (-not $targetUser) { $targetUser = "root" }
    $logPipe = Join-Path $LogDir "repair-finalize.log"
    $started = Get-Date
    $gpuWin = Get-WindowsNvidiaName
    $gpuWsl = Get-WslNvidiaName -Name $Name
    $envPass = "OTACON_CHAT_PORT=$Port"
    $code = Invoke-WslInstallPhase -Name $Name -Phase "finalize" -AsUser "root" -TargetUser $targetUser `
        -EnvPass $envPass -Started $started -GpuWin $gpuWin -GpuWsl $gpuWsl -LogPipe $logPipe `
        -OverallTimeoutMin 15 -StallTimeoutMin 10
    if ($code -ne 0) {
        Write-KeepLog "Repair finalize exit=$code" -Level "WARN" -Stage "REPAIR"
    }
    & wsl.exe -d $Name -u root -- bash -lc "systemctl start otacon-tts.service 2>/dev/null; systemctl start otacon.service 2>/dev/null; true" 2>$null | Out-Null
    $wakeOk = Step-RegisterWakeTask -Name $Name
    Start-Sleep -Seconds 2
    $tts = Test-OtaconTts
    Write-KeepLog "Repair done wake=$wakeOk tts=$($tts.ok) reason=$($tts.reason)" -Stage "REPAIR"
    return ($tts.ok -and $wakeOk)
}

function Step-Verify {
    param([string]$Name)
    Save-InstallerState @{ stage = "verifying"; step = 8 }
    $started = Get-Date
    for ($i = 0; $i -lt 40; $i++) {
        Show-WorkingPanel -Step 8 -StepName "VERIFYING OTACON" -Detail "Performing final systems check on localhost:$Port" -Started $started -Typical "1 to 3 minutes"
        $tts = Test-OtaconTts
        if ((Test-OtaconHealth) -and $tts.ok) { return $true }
        # P0-1: start TTS then Core (wake path parity)
        & wsl.exe -d $Name -u root -- bash -lc "systemctl start otacon-tts.service 2>/dev/null; systemctl start otacon.service 2>/dev/null; true" 2>$null | Out-Null
        Start-Sleep -Seconds 3
    }
    $tts = Test-OtaconTts
    return ((Test-OtaconHealth) -and $tts.ok)
}

# ---------------------------------------------------------------------------
# Main guided flow
# ---------------------------------------------------------------------------
function Start-GuidedSetup {
    Show-Banner
    Write-KeepLog "installer launch Resume=$Resume Force=$($script:ForceInstall)" -Stage "READY"

    $st = Get-InstallerState
    if ($Resume -or $st["stage"] -eq "waiting_for_reboot" -or $st["resume_registered"]) {
        Show-Box "WELCOME BACK" @(
            "windows restarted successfully",
            "",
            "continuing otaconskeep installation",
            "",
            "you do not need to start over"
        ) -Color Green
        Clear-ResumeMarkers
        Start-Sleep -Seconds 2
    }

    $snap = Get-WhereYouAre
    Show-WhereYouAre $snap

    # Gate B: foreign HTTP on 5757 must never look like READY
    if ($snap.occupied_non_otacon) {
        Show-NonOtaconPortDiagnostic (Test-OtaconIdentity)
        return 1
    }

    # Gate A: healthy existing install -> Open / Repair / Reinstall (never silent exit)
    # P0-2 / P1-4: do NOT claim COMPLETE / clear errors if TTS is down.
    if ($snap.web_health -and -not $script:ForceInstall) {
        $ttsOk = [bool]$snap.tts_ok
        $title = if ($ttsOk) { "OTACON IS READY" } else { "OTACON NEEDS REPAIR" }
        $color = if ($ttsOk) { [ConsoleColor]::Green } else { [ConsoleColor]::Yellow }
        $lines = @(
            $(if ($ttsOk) { "otacon is already installed and responding" } else { "chat may be up, but the voice engine is not healthy" }),
            "",
            $(if ($ttsOk) { "identity check passed on localhost:$Port" } else { "voice reason: $($snap.tts_reason)" }),
            "",
            "http://localhost:$Port",
            "",
            "[ O ] Open Otacon",
            "[ P ] Repair  (TTS unit + wake + spoken preview)",
            "[ R ] Reinstall  (force reinstall path)",
            "[ X ] Exit"
        )
        Show-Box $title $lines -Color $color
        if ($ttsOk) {
            Save-InstallerComplete
        } else {
            Save-InstallerState @{ stage = "degraded"; last_error = "TTS down: $($snap.tts_reason)" }
        }
        $c = Read-Choice "  Choice [O/P/R/X]: " @("O","P","R","X")
        if ($c -eq "O") {
            Start-Process $HealthUrl
            return $(if ($ttsOk) { 0 } else { 2 })
        }
        if ($c -eq "X") { return $(if ($ttsOk) { 0 } else { 2 }) }
        if ($c -eq "P") {
            $script:ForceInstall = $true
            Write-KeepLog "user chose Repair" -Stage "READY"
            $ubuntu = Get-UbuntuDistroName
            if ($ubuntu) {
                if (Invoke-RepairTtsAndWake -Name $ubuntu) {
                    Save-InstallerComplete
                    Show-Box "REPAIR COMPLETE" @(
                        "voice engine and wake task restored",
                        "",
                        "http://localhost:$Port",
                        "",
                        "press O to open, X to finish"
                    ) -Color Green
                    $c2 = Read-Choice "  Choice [O/X]: " @("O","X")
                    if ($c2 -eq "O") { Start-Process $HealthUrl }
                    return 0
                }
                Write-Host "  Repair did not fully restore TTS - continuing into guided setup." -ForegroundColor DarkYellow
            }
        }
        if ($c -eq "R") {
            $script:ForceInstall = $true
            $script:ReinstallRequested = $true
            Write-KeepLog "user chose Reinstall" -Stage "READY"
        }
        # Fall through into guided install (do not return)
    } elseif ($snap.web_health -and $script:ForceInstall) {
        Write-KeepLog "Force/Repair/Reinstall bypass of READY short-circuit" -Stage "READY"
        if ($Repair -or ($script:ForceInstall -and -not $script:ReinstallRequested)) {
            $ubuntu = Get-UbuntuDistroName
            if ($ubuntu -and (Invoke-RepairTtsAndWake -Name $ubuntu)) {
                Save-InstallerComplete
                Show-Box "REPAIR COMPLETE" @(
                    "voice engine and wake task restored (--repair/--force)",
                    "",
                    "http://localhost:$Port",
                    "",
                    "press O to open, X to finish"
                ) -Color Green
                $c2 = Read-Choice "  Choice [O/X]: " @("O","X")
                if ($c2 -eq "O") { Start-Process $HealthUrl }
                return 0
            }
        }
    }

    Show-Box "BEFORE WE START" @(
        "otaconskeep uses windows subsystem for linux",
        "",
        "you do NOT need to already have ubuntu",
        "you do NOT need to know linux",
        "you do NOT need a separate linux computer",
        "",
        "if you already run ubuntu inside proxmox",
        "that is separate and will not be modified",
        "",
        "setup may require ONE windows restart",
        "",
        "typical setup time",
        "10 to 30 minutes",
        "",
        "your computer may appear busy during installation",
        "that is normal",
        "",
        "dont worry if you have never used linux before",
        "this installer will guide you through everything",
        "do not close this window unless we tell you to"
    ) -Color Yellow

    $go = Read-Choice "  Press I to install, X to cancel: " @("I","X")
    if ($go -eq "X") {
        Write-Host "  Cancelled. Nothing was changed." -ForegroundColor DarkYellow
        return 0
    }

    # [1/8] checking windows
    Write-Host "  [1/$TotalSteps] checking windows" -ForegroundColor Cyan
    Write-KeepLog "step1 windows ok" -Stage "WORKING"
    Write-Host "  [ok] Windows session detected" -ForegroundColor Green

    # [2/8] virtualization / admin for feature enable
    Write-Host "  [2/$TotalSteps] checking virtualization / permissions" -ForegroundColor Cyan

    # [3/8] WSL - Gate E: explicit distro choice
    Write-Host "  [3/$TotalSteps] checking wsl" -ForegroundColor Cyan
    Write-WslListVerbose
    $ubuntu = Resolve-OtaconDistroInteractive
    if ($null -eq $ubuntu) {
        Write-Host "  Aborted. Existing WSL distributions were not changed." -ForegroundColor DarkYellow
        return 1
    }
    $needCreate = -not (Get-WslUbuntuFamilyNames | Where-Object { $_.Equals($ubuntu, [System.StringComparison]::OrdinalIgnoreCase) })
    if (-not (Test-WslPresent) -or $needCreate) {
        if (-not (Ensure-Admin)) { return 0 }
        Write-Host "  [ OTACON ] preparing linux environment ($ubuntu)" -ForegroundColor Cyan
        $code = Step-EnableWsl -DistroName $ubuntu
        $ubuntu = Get-UbuntuDistroName
        if (-not $ubuntu) { $ubuntu = $PreferredDistro }
        if (-not (Test-UbuntuReady $ubuntu)) {
            $s2 = Get-WhereYouAre
            if (-not $s2.ubuntu_ready) {
                Request-RestartConfirmation
                return 0
            }
        }
    } else {
        Write-Host "  [ok] wsl already installed (distro=$ubuntu)" -ForegroundColor Green
        Save-InstallerState @{ ubuntu_name = $ubuntu }
    }

    # [4/8] ubuntu
    Write-Host "  [4/$TotalSteps] installing / checking ubuntu (inside Windows)" -ForegroundColor Cyan
    $ubuntu = Get-UbuntuDistroName
    if (-not $ubuntu) {
        if (-not (Ensure-Admin)) { return 0 }
        Step-EnableWsl -DistroName $PreferredDistro | Out-Null
        $ubuntu = Get-UbuntuDistroName
        if (-not $ubuntu) {
            $act = Show-SetupNeedsHelp -Step "installing ubuntu" -PlainError "Windows did not create an Ubuntu environment for OtaconsKeep yet. A restart may still be required."
            if ($act -eq "retry") { return (Start-GuidedSetup) }
            return 1
        }
    } else {
        Write-Host "  [ok] ubuntu distro present: $ubuntu" -ForegroundColor Green
    }

    # [5/8] prepare ubuntu
    Write-Host "  [5/$TotalSteps] preparing ubuntu" -ForegroundColor Cyan
    if (-not (Test-UbuntuReady $ubuntu)) {
        $ok = Step-WaitUbuntuInit -Name $ubuntu
        $ubuntu = Get-UbuntuDistroName
        if (-not $ok) {
            # Register resume so user can finish ubuntu and come back
            Register-ResumeAfterReboot
            Show-Box "ALMOST THERE" @(
                "Ubuntu inside Windows still needs its first-time username/password.",
                "",
                "Open the Ubuntu app from the Start menu, finish those prompts,",
                "then restart this installer (or wait for it to reopen).",
                "",
                "This is NOT your Proxmox Ubuntu VM."
            ) -Color Yellow
            Write-Host "  Press any letter key to close (paused - not failed)." -ForegroundColor DarkYellow
            [void][Console]::ReadKey($true)
            return 0
        }
    } else {
        Write-Host "  [ok] ubuntu already initialized" -ForegroundColor Green
    }

    Clear-ResumeMarkers

    # [6/8] install otacon
    Write-Host "  [6/$TotalSteps] installing otacon" -ForegroundColor Cyan
    $preTts = Test-OtaconTts
    if ((-not $script:ForceInstall) -and (Test-OtaconFiles $ubuntu) -and (Test-OtaconHealth) -and $preTts.ok) {
        Write-Host "  [ok] otaconskeep already installed and healthy (incl. voice)" -ForegroundColor Green
    } else {
        $rc = Step-InstallOtacon -Name $ubuntu
        if ($rc -ne 0 -and $rc -ne 2) {
            # Gate C: leave stage=failed with last_error (Show-SetupNeedsHelp already sets it)
            $tail = Join-Path $LogDir "linux-install-tail.log"
            $act = Show-SetupNeedsHelp -Step "installing otacon" -PlainError (
                "The Linux installer exited with code $rc. Your files were not wiped. You can retry. Log: $tail"
            )
            if ($act -eq "retry") { return (Start-GuidedSetup) }
            return (ConvertTo-InstallerExitCode $rc)
        }
        if ($rc -eq 2) {
            Write-Host "  [warn] Otacon installed DEGRADED (core up, optional piece failed - not green READY yet)" -ForegroundColor DarkYellow
            Save-InstallerState @{ stage = "degraded"; last_error = "Linux installer returned DEGRADED (exit 2)" }
        }
    }

    # [7/8] starting services
    Write-Host "  [7/$TotalSteps] starting services" -ForegroundColor Cyan
    $wakeOk = Step-RegisterWakeTask -Name $ubuntu
    if (-not $wakeOk) {
        Write-Host "  [warn] logon wake task not registered (Access Denied or missing) - voice may not survive reboot" -ForegroundColor DarkYellow
        Write-KeepLog "wake task missing before READY" -Level "WARN" -Stage "STARTING"
    }
    & wsl.exe -d $ubuntu -u root -- bash -lc "systemctl start otacon-tts.service 2>/dev/null; systemctl start otacon.service 2>/dev/null; true" 2>$null | Out-Null
    Write-Host "  [ OTACON ] bringing the keep online" -ForegroundColor Cyan

    # [8/8] verify - identity + TTS health required for green READY
    Write-Host "  [8/$TotalSteps] verifying otacon" -ForegroundColor Cyan
    Write-Host "  [ OTACON ] performing final systems check" -ForegroundColor Cyan
    if (-not (Step-Verify -Name $ubuntu)) {
        $id = Test-OtaconIdentity
        if ($id.occupied_non_otacon) {
            Show-NonOtaconPortDiagnostic $id
            Save-InstallerState @{ stage = "failed"; last_error = "Port $Port is occupied by a non-Otacon service."; last_step = "verifying otacon" }
            return 1
        }
        $tts = Test-OtaconTts
        if ((Test-OtaconHealth) -and -not $tts.ok) {
            Save-InstallerState @{ stage = "degraded"; last_error = "TTS down after verify: $($tts.reason)" }
            Show-Box "OTACON DEGRADED" @(
                "chat interface responded, but the voice engine did not",
                "",
                "reason: $($tts.reason)",
                "",
                "press P to repair voice now, X to finish (not green READY)"
            ) -Color Yellow
            $c = Read-Choice "  Choice [P/X]: " @("P","X")
            if ($c -eq "P") {
                if (Invoke-RepairTtsAndWake -Name $ubuntu) {
                    Save-InstallerComplete
                    Show-Box "OTACON IS READY" @(
                        "voice restored",
                        "",
                        "http://localhost:$Port",
                        "",
                        "press O to open, X to finish"
                    ) -Color Green
                    $c2 = Read-Choice "  Choice [O/X]: " @("O","X")
                    if ($c2 -eq "O") { Start-Process $HealthUrl }
                    return 0
                }
            }
            return 2
        }
        $act = Show-SetupNeedsHelp -Step "starting otacon" -PlainError "Otacon did not answer http://localhost:$Port/api/branding yet. The install may still be finishing - retry in a minute."
        if ($act -eq "retry") { return (Start-GuidedSetup) }
        return 1
    }

    if (-not (Test-WakeTaskRegistered)) {
        Write-Host "  [warn] OtaconAutoStart wake task still missing - registering once more" -ForegroundColor DarkYellow
        [void](Step-RegisterWakeTask -Name $ubuntu)
    }

    Save-InstallerComplete
    Clear-ResumeMarkers
    $ttsFinal = Test-OtaconTts
    $sttNote = "mic/STT: not installed by default (set OTACON_INSTALL_STT=1 to enable)"
    $readyLines = @(
        "installation completed successfully",
        "",
        "otacon identity check passed",
        "voice engine: $($ttsFinal.reason)",
        "wake task: $(if (Test-WakeTaskRegistered) { 'registered' } else { 'MISSING - reboot may not auto-start' })",
        $sttNote,
        "",
        "open otacon",
        "",
        "http://localhost:$Port",
        "",
        "you can close this setup window now",
        "",
        "press O to open otacon",
        "press X to finish"
    )
    Show-Box "OTACON IS READY" $readyLines -Color Green
    Write-KeepLog "COMPLETE identity+tts health ok wake=$(Test-WakeTaskRegistered)" -Stage "COMPLETE"
    $c = Read-Choice "  Choice [O/X]: " @("O","X")
    if ($c -eq "O") { Start-Process $HealthUrl }
    return 0
}

# ---------------------------------------------------------------------------
# Entry
# ---------------------------------------------------------------------------
try {
    $revFile = Join-Path $RepoRoot "deploy\installer-revision.txt"
    if (Test-Path -LiteralPath $revFile) {
        $rev = (Get-Content -LiteralPath $revFile -TotalCount 1 -ErrorAction SilentlyContinue)
        Write-KeepLog "installer revision=$rev assistantBytes=$((Get-Item -LiteralPath $MyInvocation.MyCommand.Path).Length)" -Stage "READY"
    }
    if ($Status) { Show-StatusReport; exit 0 }
    if ($Diagnostics) { Write-DiagnosticsFile | Out-Null; exit 0 }
    if ($Open) {
        $cont = Open-OtaconIfReady
        if ($cont -and -not (Test-OtaconHealth)) { exit (ConvertTo-InstallerExitCode (Start-GuidedSetup)) }
        exit 0
    }
    exit (ConvertTo-InstallerExitCode (Start-GuidedSetup))
} catch {
    Write-KeepLog "UNHANDLED $($_.Exception.Message)" -Level "ERROR" -Stage "FAILED"
    Show-SetupNeedsHelp -Step "unexpected error" -PlainError $_.Exception.Message | Out-Null
    exit 1
}
