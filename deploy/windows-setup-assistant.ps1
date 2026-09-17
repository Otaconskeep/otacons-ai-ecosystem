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
    [switch]$FixCodec,
    [switch]$ProbeWslLauncher,
    [string]$ProbeDistro = "",
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
# Last base URL that answered /api/branding (localhost or WSL IP).
$script:OtaconOpenBase = "http://127.0.0.1:$Port"
# AutoPilot: no I/R/C menus on the happy path - Otacon runs the install.
$script:AutoPilot = $true
$script:OtaconUiReady = $false

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
# UI helpers - Otacon sci-fi console (CMD/PowerShell constrained)
# ---------------------------------------------------------------------------
function Initialize-OtaconConsole {
    if ($script:OtaconUiReady) { return }
    try {
        $Host.UI.RawUI.WindowTitle = "OTACON // OTACONSKEEP LINK"
        # Dark console when we can (ignore failures under redirected hosts).
        try { [Console]::BackgroundColor = "Black" } catch {}
        try { [Console]::ForegroundColor = "Cyan" } catch {}
        try { Clear-Host } catch {}
    } catch {}
    $script:OtaconUiReady = $true
}

function Get-OtaconGlyphs {
    return @(
        "0","1","7","A","C","E","F","X","|",":","+","*","#","@",
        "01","AF","7F","::","[]","<>","/\"
    )
}

function Show-OtaconRain {
    param([int]$Frames = 14, [int]$DelayMs = 45)
    Initialize-OtaconConsole
    $glyphs = Get-OtaconGlyphs
    $width = 72
    try {
        $w = [Console]::WindowWidth
        if ($w -gt 40) { $width = [Math]::Min(96, $w - 1) }
    } catch {}
    $height = 12
    $cols = New-Object int[] $width
    $rnd = New-Object System.Random
    for ($i = 0; $i -lt $width; $i++) { $cols[$i] = $rnd.Next(-$height, $height) }
    for ($f = 0; $f -lt $Frames; $f++) {
        try { [Console]::SetCursorPosition(0, 0) } catch { Clear-Host }
        Write-Host ""
        Write-Host ("  " + ("=" * ($width - 4))) -ForegroundColor DarkCyan
        Write-Host ("  OTACON UPLINK  //  MATRIX CHANNEL  //  FRAME {0:D2}" -f $f) -ForegroundColor Cyan
        Write-Host ("  " + ("=" * ($width - 4))) -ForegroundColor DarkCyan
        for ($row = 0; $row -lt $height; $row++) {
            $line = New-Object System.Text.StringBuilder ($width)
            for ($c = 0; $c -lt $width; $c++) {
                $head = $cols[$c]
                if ($row -eq $head) {
                    [void]$line.Append($glyphs[$rnd.Next(0, $glyphs.Count)])
                } elseif ($row -lt $head -and $row -gt ($head - 4)) {
                    [void]$line.Append($glyphs[$rnd.Next(0, [Math]::Min(8, $glyphs.Count))])
                } else {
                    [void]$line.Append(" ")
                }
            }
            $color = if (($row % 3) -eq 0) { "Green" } elseif (($row % 3) -eq 1) { "DarkGreen" } else { "DarkCyan" }
            Write-Host ("  " + $line.ToString()) -ForegroundColor $color
        }
        for ($c = 0; $c -lt $width; $c++) {
            $cols[$c]++
            if ($cols[$c] -gt ($height + 2)) { $cols[$c] = $rnd.Next(-$height, 0) }
        }
        Start-Sleep -Milliseconds $DelayMs
    }
}

function Write-OtaconSay {
    param(
        [Parameter(Mandatory = $true)][string]$Message,
        [string]$Mood = "info",  # info | ok | warn | alert | work
        [switch]$NoType
    )
    Initialize-OtaconConsole
    $tagColor = switch ($Mood) {
        "ok"    { "Green" }
        "warn"  { "Yellow" }
        "alert" { "Red" }
        "work"  { "DarkCyan" }
        default { "Cyan" }
    }
    $msgColor = switch ($Mood) {
        "ok"    { "Green" }
        "warn"  { "Yellow" }
        "alert" { "Magenta" }
        "work"  { "Gray" }
        default { "White" }
    }
    Write-Host ""
    Write-Host -NoNewline "  [" -ForegroundColor DarkCyan
    Write-Host -NoNewline "OTACON" -ForegroundColor $tagColor
    Write-Host -NoNewline "] " -ForegroundColor DarkCyan
    if ($NoType -or $Message.Length -gt 140) {
        Write-Host $Message -ForegroundColor $msgColor
    } else {
        foreach ($ch in $Message.ToCharArray()) {
            Write-Host -NoNewline $ch -ForegroundColor $msgColor
            Start-Sleep -Milliseconds 8
        }
        Write-Host ""
    }
    Write-KeepLog "OTACON: $Message" -Stage "OTACON"
}

function Show-OtaconRule {
    param([ConsoleColor]$Color = "DarkCyan")
    Write-Host ("  " + ("-" * 62)) -ForegroundColor $Color
}

function Show-Banner {
    Initialize-OtaconConsole
    Clear-Host
    Show-OtaconRain -Frames 10 -DelayMs 35
    Clear-Host
    Write-Host ""
    Show-OtaconRule -Color Cyan
    Write-Host "   ####    #####    #    ####    ####   #   #" -ForegroundColor Cyan
    Write-Host "  #    #     #     # #  #    #  #    #  ##  #" -ForegroundColor Cyan
    Write-Host "  #    #     #    #   #  #      #    #  # # #" -ForegroundColor Green
    Write-Host "  #    #     #    #####  #      #    #  #  ##" -ForegroundColor Green
    Write-Host "   ####      #    #   #   ####   ####   #   #" -ForegroundColor Yellow
    Show-OtaconRule -Color Cyan
    Write-Host "   OTACONSKEEP  //  WINDOWS LINK  //  AUTO-INSTALL" -ForegroundColor Yellow
    Write-Host "   You do not need Linux. I am handling the installation." -ForegroundColor DarkCyan
    Show-OtaconRule -Color Cyan
    Write-Host ""
    Write-OtaconSay "Hi. I'm Otacon. Sit tight - I'll set everything up for you." -Mood "info"
    Write-OtaconSay "No menus. No Linux homework. Just leave this window open." -Mood "work" -NoType
}

function Show-Box {
    param([string]$Title, [string[]]$Lines, [ConsoleColor]$Color = "Cyan")
    Initialize-OtaconConsole
    Write-Host ""
    Show-OtaconRule -Color $Color
    Write-Host ("  >> {0}" -f $Title.ToUpperInvariant()) -ForegroundColor $Color
    Show-OtaconRule -Color DarkCyan
    foreach ($ln in $Lines) {
        if ($null -eq $ln) { Write-Host ""; continue }
        Write-Host ("     {0}" -f $ln) -ForegroundColor Gray
    }
    Show-OtaconRule -Color $Color
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
    Initialize-OtaconConsole
    $elapsed = (Get-Date) - $Started
    $em = "{0:00}m {1:00}s" -f [int]$elapsed.TotalMinutes, $elapsed.Seconds
    Clear-Host
    Write-Host ""
    Show-OtaconRule -Color Cyan
    Write-Host ("  OTACON  //  LINK ACTIVE  //  STEP {0}/{1}" -f $Step, $TotalSteps) -ForegroundColor Cyan
    Write-Host ("  MISSION : {0}" -f $StepName.ToUpperInvariant()) -ForegroundColor Yellow
    Show-OtaconRule -Color DarkCyan
    Write-Host ("  STATUS  : WORKING - do not close this window") -ForegroundColor Green
    $detail = "$Detail"
    if ($detail.Length -gt 58) { $detail = $detail.Substring(0, 58) }
    Write-Host ("  DETAIL  : {0}" -f $detail) -ForegroundColor White
    Write-Host ("  ELAPSED : {0}   typical {1}" -f $em, $Typical) -ForegroundColor DarkCyan
    Show-OtaconRule -Color Cyan
    # Mini rain strip
    $glyphs = Get-OtaconGlyphs
    $rnd = New-Object System.Random
    $strip = -join (0..61 | ForEach-Object { $glyphs[$rnd.Next(0, 8)] })
    Write-Host ("  {0}" -f $strip) -ForegroundColor DarkGreen
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
        # Cheap boot probe as root - works even when default user has no shell yet.
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
      # Josh-997-fallback-v2
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
    # Prefer dedicated OtaconsKeep / versioned distros.
    # Stock "Ubuntu" is OK when it is the only available distro and it actually boots
    # (virgin wsl --install -d Ubuntu creates that name - ignoring it caused reboot loops).
    $st = Get-InstallerState
    $stated = [string]$st["ubuntu_name"]
    $mode = [string]$st["ubuntu_mode"]
    if ($stated -and $stated.Equals("Ubuntu", [System.StringComparison]::OrdinalIgnoreCase)) {
        if (Test-UbuntuReady $stated) {
            Write-KeepLog "using stock Ubuntu (ready) mode=$mode" -Stage "WSL"
            return $stated
        }
        Write-KeepLog "ignoring saved stock Ubuntu (not ready) mode=$mode" -Level "WARN" -Stage "WSL"
        Save-InstallerState @{ ubuntu_name = $null; ubuntu_mode = $null }
        $stated = ""
        $mode = ""
    }
    if ($stated) {
        $isPreferred = [bool]($PreferredDistroAliases | Where-Object { $stated.Equals($_, [System.StringComparison]::OrdinalIgnoreCase) })
        if (($isPreferred -or $mode -eq "reuse") -and (Test-UbuntuReady $stated)) {
            return $stated
        }
    }
    $finder = Join-Path $RepoRoot "deploy\find-ubuntu.ps1"
    if (Test-Path $finder) {
        $name = & powershell -NoProfile -ExecutionPolicy Bypass -File $finder 2>$null
        if ($name) {
            $n = ($name | Select-Object -First 1).ToString().Trim()
            if ($n -and -not $n.Equals("Ubuntu", [System.StringComparison]::OrdinalIgnoreCase)) {
                if (Test-UbuntuReady $n) { return $n }
            }
        }
    }
    foreach ($want in ($PreferredDistroAliases + @("Ubuntu-22.04", "Ubuntu-24.04"))) {
        $family = Get-WslUbuntuFamilyNames
        $hit = $family | Where-Object { $_.Equals($want, [System.StringComparison]::OrdinalIgnoreCase) } | Select-Object -First 1
        if ($hit -and (Test-UbuntuReady $hit)) { return $hit }
    }
    # Last resort: stock Store "Ubuntu" if it boots (post wsl --install -d Ubuntu).
    $family = Get-WslUbuntuFamilyNames
    $stock = $family | Where-Object { $_.Equals("Ubuntu", [System.StringComparison]::OrdinalIgnoreCase) } | Select-Object -First 1
    if ($stock) {
        [void](Ensure-WslDistroRunning -Name $stock)
        if (Test-UbuntuReady $stock) {
            Save-InstallerState @{ ubuntu_name = $stock; ubuntu_mode = "reuse" }
            Write-KeepLog "accepting stock Ubuntu as reuse (only available ready distro)" -Stage "WSL"
            return $stock
        }
    }
    return $null
}

function Resolve-OtaconDistroInteractive {
    <#
      AutoPilot: never ask R/C/A. Prefer Ubuntu-Otacon, else create it.
      Existing Ubuntu is not silently mutated when other distros exist -
      we create dedicated Ubuntu-Otacon beside them.
    #>
    Write-WslListVerbose
    $existing = Get-UbuntuDistroName
    if ($existing) {
        Write-OtaconSay "Found your Linux environment: $existing. I'll use that." -Mood "ok" -NoType
        Write-KeepLog "autopilot using dedicated/known distro=$existing" -Stage "WSL"
        return $existing
    }

    $family = Get-WslUbuntuFamilyNames
    $preferredHit = $family | Where-Object {
        $n = $_
        [bool]($PreferredDistroAliases | Where-Object { $n.Equals($_, [System.StringComparison]::OrdinalIgnoreCase) })
    } | Select-Object -First 1
    if ($preferredHit) {
        $script:ChosenDistroMode = "dedicated"
        Write-OtaconSay "Linked to $preferredHit." -Mood "ok" -NoType
        return $preferredHit
    }

    $others = @($family | Where-Object {
            $n = $_
            -not ($PreferredDistroAliases | Where-Object { $n.Equals($_, [System.StringComparison]::OrdinalIgnoreCase) })
        })

    if ($others.Count -eq 0) {
        $script:ChosenDistroMode = "dedicated"
        Write-OtaconSay "No Otacon Linux yet. I'll create $PreferredDistro for you - you don't need to know Linux." -Mood "work" -NoType
        return $PreferredDistro
    }

    # Stock Ubuntu alone: reuse it (wsl --install -d Ubuntu creates this name).
    $onlyStock = @($others | Where-Object { $_.Equals("Ubuntu", [System.StringComparison]::OrdinalIgnoreCase) })
    $nonStock = @($others | Where-Object { -not $_.Equals("Ubuntu", [System.StringComparison]::OrdinalIgnoreCase) })
    if ($nonStock.Count -eq 0 -and $onlyStock.Count -ge 1) {
        $script:ChosenDistroMode = "reuse"
        Save-InstallerState @{ ubuntu_name = "Ubuntu"; ubuntu_mode = "reuse" }
        Write-OtaconSay "I'll use the Ubuntu already on this PC." -Mood "ok" -NoType
        Write-KeepLog "autopilot only stock Ubuntu present - reusing" -Stage "WSL"
        return "Ubuntu"
    }

    # Other Ubuntu* present - do not mutate them; create dedicated side-by-side.
    $script:ChosenDistroMode = "dedicated"
    Write-OtaconSay "You already have Linux on Windows. I'll add $PreferredDistro beside it so nothing else is changed." -Mood "work" -NoType
    Write-KeepLog "autopilot creating dedicated $PreferredDistro beside existing=$($nonStock -join ',')" -Stage "WSL"
    return $PreferredDistro
}

function Get-WslPrimaryIp {
    param([string]$Name)
    if (-not $Name) { return "" }
    try {
        $raw = (& wsl.exe -d $Name -- hostname -I 2>$null | Out-String).Trim()
        if (-not $raw) { return "" }
        $ip = ($raw -split '\s+')[0]
        if ($ip -match '^\d{1,3}(\.\d{1,3}){3}$') { return $ip }
    } catch {}
    return ""
}

function Get-OtaconBaseUrlCandidates {
    $list = New-Object System.Collections.Generic.List[string]
    [void]$list.Add("http://127.0.0.1:$Port")
    $ubuntu = $null
    try { $ubuntu = Get-UbuntuDistroName } catch {}
    if ($ubuntu) {
        $ip = Get-WslPrimaryIp -Name $ubuntu
        if ($ip) { [void]$list.Add("http://${ip}:$Port") }
    }
    # Last good URL from prior repair
    try {
        $f = Join-Path $KeepDir "last-otacon-url.txt"
        if (Test-Path -LiteralPath $f) {
            $prev = (Get-Content -LiteralPath $f -TotalCount 1 -ErrorAction SilentlyContinue).Trim()
            if ($prev -and $prev -match '^https?://' -and -not $list.Contains($prev)) {
                [void]$list.Add($prev)
            }
        }
    } catch {}
    return @($list)
}

function Get-OtaconOpenUrl {
    param([switch]$Codec)
    $base = $script:OtaconOpenBase
    if (-not $base) { $base = "http://127.0.0.1:$Port" }
    if ($Codec) { return "$base/?codec=1" }
    return "$base/"
}

function Invoke-OtaconCoreRepair {
    <#
      Revive Core when connection refused / Codec dud / scan hang.
      Prefer deploy/repair-otacon-core.ps1; falls back to inline wake.
    #>
    param(
        [string]$Name = "",
        [switch]$OpenBrowser,
        [switch]$Codec
    )
    if (-not $Name) { $Name = Get-UbuntuDistroName }
    $ps1 = Join-Path $RepoRoot "deploy\repair-otacon-core.ps1"
    if (Test-Path -LiteralPath $ps1) {
        Write-KeepLog "Invoke-OtaconCoreRepair via repair-otacon-core.ps1 distro=$Name" -Stage "REPAIR"
        $argList = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $ps1, "-Port", "$Port", "-TimeoutSeconds", "45")
        if ($Name) { $argList += @("-DistroName", $Name) }
        if ($OpenBrowser) { $argList += "-OpenBrowser" }
        if ($Codec) { $argList += "-Codec" }
        & powershell @argList
        $ok = ($LASTEXITCODE -eq 0)
        if ($ok) {
            try {
                $f = Join-Path $KeepDir "last-otacon-url.txt"
                if (Test-Path -LiteralPath $f) {
                    $script:OtaconOpenBase = (Get-Content -LiteralPath $f -TotalCount 1).Trim()
                }
            } catch {}
            # Refresh identity against whatever answered
            [void](Test-OtaconIdentity)
        }
        return $ok
    }
    Write-KeepLog "repair-otacon-core.ps1 missing - inline wake" -Level "WARN" -Stage "REPAIR"
    if ($Name) {
        & wsl.exe -d $Name -u root -- bash -lc "systemctl restart otacon-tts.service 2>/dev/null; systemctl restart otacon.service 2>/dev/null; true" 2>$null | Out-Null
        Start-Sleep -Seconds 3
    }
    $id = Test-OtaconIdentity
    if ($id.ok -and ($OpenBrowser -or $Codec)) {
        Start-Process (Get-OtaconOpenUrl -Codec:$Codec)
    }
    return [bool]$id.ok
}

function Test-OtaconIdentity {
    <#
      Gate B/J: READY only when /api/branding positively identifies Otacon.
      Tries localhost first, then WSL IP (Windows localhost forwarding can break).
      Returns hashtable: ok, reason, product_name, occupied_non_otacon
    #>
    $result = @{
        ok                   = $false
        reason               = "unreachable"
        product_name         = ""
        occupied_non_otacon  = $false
        root_status          = $null
        brand_status         = $null
        base_url             = ""
    }
    $bases = Get-OtaconBaseUrlCandidates
    $sawHttp = $false
    foreach ($base in $bases) {
        $rootOk = $false
        try {
            $root = Invoke-WebRequest -Uri "$base/" -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop
            $result.root_status = [int]$root.StatusCode
            if ($root.StatusCode -ge 200 -and $root.StatusCode -lt 500) {
                $rootOk = $true
                $sawHttp = $true
            } else {
                continue
            }
        } catch {
            continue
        }
        if (-not $rootOk) { continue }

        try {
            $b = Invoke-WebRequest -Uri "$base/api/branding" -UseBasicParsing -TimeoutSec 4 -ErrorAction Stop
            $result.brand_status = [int]$b.StatusCode
            if ($b.StatusCode -lt 200 -or $b.StatusCode -ge 300) {
                $result.reason = "branding_bad_status"
                $result.occupied_non_otacon = $true
                $result.base_url = $base
                return $result
            }
            $json = $null
            try { $json = $b.Content | ConvertFrom-Json } catch {
                $result.reason = "branding_invalid_json"
                $result.occupied_non_otacon = $true
                $result.base_url = $base
                return $result
            }
            $pname = [string]($json.product_name)
            $result.product_name = $pname
            $result.base_url = $base
            if ($pname -eq "Otacon") {
                $result.ok = $true
                $result.reason = "ok"
                $script:OtaconOpenBase = $base
                $script:HealthUrl = "$base/"
                $script:BrandUrl = "$base/api/branding"
                try {
                    Set-Content -LiteralPath (Join-Path $KeepDir "last-otacon-url.txt") -Value $base -Encoding ASCII
                } catch {}
                return $result
            }
            $result.reason = "branding_wrong_product"
            $result.occupied_non_otacon = $true
            return $result
        } catch {
            # Root answered but branding missing -> may be foreign; try next base first
            $result.reason = "branding_missing"
            $result.occupied_non_otacon = $true
            $result.base_url = $base
            # Keep looking at other bases before concluding
            continue
        }
    }
    if ($sawHttp -and $result.occupied_non_otacon) { return $result }
    $result.reason = "root_unreachable"
    return $result
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

function Test-ComponentStoreCorruptMessage {
    param([string]$Text)
    if (-not $Text) { return $false }
    return [bool]($Text -match '(?i)\b14098\b|0x80073712|component store has been corrupted|ERROR_SXS_COMPONENT_STORE_CORRUPT')
}

function Show-ComponentStoreCorruptHelp {
    param([string]$Detail = "")
    $ubuntu = Get-UbuntuDistroName
    $hasFiles = $false
    if ($ubuntu) { $hasFiles = Test-OtaconFiles $ubuntu }
    $lines = @(
        "Windows reports error 14098",
        "The component store has been corrupted",
        "",
        "This is a WINDOWS problem (not Otacon).",
        "It blocks enabling Linux / WSL features.",
        "",
        $(if ($Detail) { "detail: $Detail" } else { "" }),
        $(if ($Detail) { "" } else { $null }),
        "If Otacon was already installed on this PC:",
        "press F to wake Codec only (skip Windows repair)",
        "",
        "STOP pressing I - that only repeats 14098.",
        "",
        "Otherwise fix Windows first (Admin Command Prompt):",
        "",
        "  DISM /Online /Cleanup-Image /StartComponentCleanup",
        "  DISM /Online /Cleanup-Image /RestoreHealth",
        "  sfc /scannow",
        "",
        "Then reboot and run OtaconsKeep Setup again.",
        "",
        "If DISM still says 14098: use Microsoft's Windows",
        "Installation Assistant / ISO and choose",
        "Upgrade this PC (keep files and apps).",
        "",
        "[ F ] Fix Codec only (if already installed)",
        "[ R ] Retry this step",
        "[ O ] Open installer log folder",
        "[ X ] Exit"
    ) | Where-Object { $_ -ne $null }
    Show-Box "WINDOWS COMPONENT STORE CORRUPT" $lines -Color Red
    Write-KeepLog "Component store corrupt 14098 detail=$Detail hasFiles=$hasFiles" -Level "ERROR" -Stage "FAILED"
    Save-InstallerState @{ stage = "failed"; last_error = "Windows error 14098 component store corrupt"; last_step = "preparing windows" }
    while ($true) {
        $c = Read-Choice "  Choice [F/R/O/X]: " @("F","R","O","X")
        if ($c -eq "O") { Start-Process explorer.exe $LogDir; continue }
        if ($c -eq "X") { return "exit" }
        if ($c -eq "R") { return "retry" }
        if ($c -eq "F") {
            if ($ubuntu -and (Invoke-OtaconCoreRepair -Name $ubuntu -Codec)) {
                Save-InstallerComplete
                return "fixed"
            }
            Write-Host "  Could not wake Codec - Otacon may not be installed yet. Fix Windows with DISM first." -ForegroundColor DarkYellow
            continue
        }
    }
}

function Show-SetupNeedsHelp {
    param([string]$Step, [string]$PlainError)
    if (Test-ComponentStoreCorruptMessage $PlainError) {
        return (Show-ComponentStoreCorruptHelp -Detail $PlainError)
    }
    Show-Box "SETUP NEEDS HELP" @(
        "[OTACON] I hit a snag - nothing was deleted.",
        "",
        "step",
        $Step,
        "",
        "error",
        $PlainError,
        "",
        "log",
        $LogFile,
        "",
        "[ R ] Retry    [ O ] Open logs    [ X ] Exit"
    ) -Color Red
    Write-OtaconSay "I need a decision here. Press R to retry, O for logs, or X to exit." -Mood "alert" -NoType
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
    Register-ResumeAfterReboot
    Write-OtaconSay "Windows needs one restart before I can continue. I'll reopen setup after you sign in." -Mood "warn"
    Show-Box "RESTART REQUIRED" @(
        "Otacon is NOT installed yet - this restart unlocks Linux support.",
        "Setup will auto-continue after sign-in.",
        "Your Proxmox Ubuntu VM is separate and will not be changed.",
        "",
        "Restarting in 8 seconds... (close this window to cancel)"
    ) -Color Yellow
    Write-KeepLog "autopilot scheduling restart" -Stage "WAITING_FOR_REBOOT"
    for ($i = 8; $i -ge 1; $i--) {
        Write-Host ("  [OTACON] restart in {0}..." -f $i) -ForegroundColor Cyan
        Start-Sleep -Seconds 1
    }
    shutdown.exe /r /t 3 /c "OtaconsKeep setup needs one restart to finish Windows Linux support."
}

# ---------------------------------------------------------------------------
# Open Otacon (launch guard)
# ---------------------------------------------------------------------------
function Open-OtaconIfReady {
    $ubuntu = Get-UbuntuDistroName
    # Always attempt core repair first - fixes connection refused / wedged scan / dead unit.
    if ($ubuntu) {
        Write-OtaconSay "Making sure Otacon is awake..." -Mood "work" -NoType
        [void](Invoke-OtaconCoreRepair -Name $ubuntu -Codec)
    }
    $s = Get-WhereYouAre
    if ($s.web_health -or (Test-OtaconHealth)) {
        $url = Get-OtaconOpenUrl -Codec
        Write-OtaconSay "You're online. Opening Codec." -Mood "ok"
        Start-Process $url
        return $true
    }
    # AutoPilot: not ready yet - continue install without I/F/X menu.
    Write-OtaconSay "Not ready to open yet (state: $($s.overall)). I'll finish the installation." -Mood "warn" -NoType
    Show-Box "LINK PENDING" @(
        "Otacon isn't answering yet.",
        "",
        "state: $($s.overall)",
        $(if ($s.ubuntu_ready) { "ubuntu: ready" } else { "ubuntu: not ready" }),
        $(if ($s.otacon_files) { "otacon files: present" } else { "otacon files: not installed" }),
        "",
        "Continuing setup automatically..."
    ) -Color Yellow
    return $true
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
    Write-OtaconSay "Windows will show a permission popup - click Yes. Setup continues in the new elevated window." -Mood "warn"
    Write-Host "  You can close THIS window once the elevated one appears." -ForegroundColor DarkCyan
    Write-Host "  If you clicked No, press R to try again or X to exit." -ForegroundColor DarkYellow
    while ($true) {
        $c = Read-Choice "  Choice [R/X]: " @("R","X")
        if ($c -eq "X") { return $false }
        if ($c -eq "R") {
            Start-Process -FilePath $bat -ArgumentList $elevateArgs -WorkingDirectory (Split-Path -Parent $bat) -Verb RunAs
            continue
        }
    }
}

function Get-WslOnlineDistroNames {
    <#
      Parse `wsl.exe --list --online` (same as -l -o).
      Returns installable NAME tokens (first column), e.g. Ubuntu-22.04, Ubuntu, Debian.
    #>
    $names = New-Object System.Collections.Generic.List[string]
    try {
        $raw = & wsl.exe --list --online 2>$null
        if (-not $raw) { $raw = & wsl.exe -l -o 2>$null }
        foreach ($line in @($raw)) {
            $t = (("{0}" -f $line) -replace "`0", "").Trim()
            if (-not $t) { continue }
            if ($t -match '(?i)^NAME\s+FRIENDLY') { continue }
            if ($t -match '(?i)^The following') { continue }
            if ($t -match '(?i)^Install ') { continue }
            # "Ubuntu-22.04    Ubuntu 22.04 LTS" or "Ubuntu          Ubuntu"
            if ($t -match '^(\S+)\s+\S+') {
                $n = $Matches[1].Trim()
                if ($n -and -not $names.Contains($n)) { [void]$names.Add($n) }
            }
        }
    } catch {
        Write-KeepLog "wsl --list --online failed: $($_.Exception.Message)" -Level "WARN" -Stage "WSL"
    }
    Write-KeepLog ("online distros: " + ($names -join ", ")) -Stage "WSL"
    return @($names)
}

function Select-BestOnlineUbuntuInstallName {
    <# Prefer versioned Ubuntu from the online catalog; avoid bare Ubuntu when possible. #>
    $online = @(Get-WslOnlineDistroNames)
    foreach ($want in @("Ubuntu-22.04", "Ubuntu-24.04", "Ubuntu-20.04")) {
        $hit = $online | Where-Object { $_.Equals($want, [StringComparison]::OrdinalIgnoreCase) } | Select-Object -First 1
        if ($hit) { return $hit }
    }
    $any = $online | Where-Object { $_ -match '(?i)^Ubuntu' } | Select-Object -First 1
    if ($any) { return $any }
    return "Ubuntu-22.04"
}

function Step-EnableWsl {
    param([string]$DistroName = $PreferredDistro)
    Write-WslListVerbose
    Save-InstallerState @{ stage = "waiting_for_windows"; step = 3; target_distro = $DistroName }
    $started = Get-Date
    Show-WorkingPanel -Step 3 -StepName "PREPARING WINDOWS" -Detail "Preparing Linux for Otacon" -Started $started -Typical "2 to 10 minutes"

    $family = Get-WslUbuntuFamilyNames
    $already = $family | Where-Object { $_.Equals($DistroName, [System.StringComparison]::OrdinalIgnoreCase) } | Select-Object -First 1
    if ($already) {
        Write-KeepLog "distro already present: $already" -Stage "WAITING_FOR_WINDOWS"
        return 0
    }

    # If WSL is already enabled, NEVER call `wsl --install` again - that re-touches
    # Windows optional features and hits error 14098 (corrupt component store) in a loop.
    # Import a rootfs instead (no DISM feature enable).
    if (Test-WslPresent) {
        Write-KeepLog "WSL already present - importing $PreferredDistro rootfs (skip wsl --install / 14098)" -Stage "WAITING_FOR_WINDOWS"
        Write-Host "  Linux support is already on this PC." -ForegroundColor Green
        Write-Host "  Adding Ubuntu by download/import (avoids Windows error 14098)..." -ForegroundColor Cyan
        $rc = Install-DedicatedUbuntuOtacon
        Write-KeepLog "import-while-wsl-present exit=$rc" -Stage "WAITING_FOR_WINDOWS"
        if ($rc -eq 0) { return 0 }
        Write-Host "  Import failed - will try Microsoft catalog next." -ForegroundColor DarkYellow
    }

    if ($DistroName -eq $PreferredDistro -and $family.Count -gt 0) {
        $rc = Install-DedicatedUbuntuOtacon
        Write-KeepLog "dedicated import exit=$rc" -Stage "WAITING_FOR_WINDOWS"
        return $rc
    }

    # Last resort: catalog install via wsl --list --online
    $installName = Select-BestOnlineUbuntuInstallName
    Write-KeepLog "wsl --list --online chose install -d $installName (requested=$DistroName)" -Stage "WAITING_FOR_WINDOWS"
    Write-Host "  Installing Linux distro from Microsoft catalog: $installName" -ForegroundColor Cyan
    $p = Start-Process -FilePath "wsl.exe" -ArgumentList "--install","-d",$installName -PassThru -NoNewWindow
    while (-not $p.HasExited) {
        Show-WorkingPanel -Step 3 -StepName "PREPARING WINDOWS" -Detail "Installing $installName from Windows catalog" -Started $started -Typical "2 to 10 minutes"
        Write-Host "  [ OTACON ] still working - do not close this window" -ForegroundColor DarkGray
        Start-Sleep -Seconds 4
    }
    Write-KeepLog "wsl --install -d $installName exit=$($p.ExitCode)" -Stage "WAITING_FOR_WINDOWS"
    if ($p.ExitCode -eq 14098 -or $p.ExitCode -eq -2146498798) {
        Write-KeepLog "14098 from wsl --install - falling back to rootfs import" -Level "WARN" -Stage "WAITING_FOR_WINDOWS"
        if (Test-WslPresent) {
            $rc2 = Install-DedicatedUbuntuOtacon
            if ($rc2 -eq 0) { return 0 }
        }
        $act = Show-ComponentStoreCorruptHelp -Detail "wsl --install exit=14098 - do NOT press I again; Windows must be repaired OR use import"
        if ($act -eq "fixed") { return 0 }
        if ($act -eq "retry") { return (Install-DedicatedUbuntuOtacon) }
        return 14098
    }
    Start-Sleep -Seconds 2
    $familyAfter = Get-WslUbuntuFamilyNames
    $created = $familyAfter | Where-Object { $_.Equals($installName, [StringComparison]::OrdinalIgnoreCase) } | Select-Object -First 1
    if (-not $created) {
        $created = $familyAfter | Where-Object { $_ -match '(?i)Ubuntu' } | Select-Object -First 1
    }
    if ($created) {
        Save-InstallerState @{ ubuntu_name = $created; ubuntu_mode = "reuse"; target_distro = $created }
        Write-KeepLog "post-install: distro=$created present" -Stage "WAITING_FOR_WINDOWS"
        [void](Ensure-WslDistroRunning -Name $created)
        return 0
    }
    if ($DistroName -eq $PreferredDistro) {
        Save-InstallerState @{ ubuntu_name = $null; ubuntu_mode = "virgin_ubuntu_pending_dedicated"; target_distro = $PreferredDistro }
    }
    return $(if ($null -eq $p.ExitCode) { 0 } else { $p.ExitCode })
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
        # Imported rootfs has only root - provision the expected non-root user now.
        [void](Ensure-WslDistroRunning -Name $PreferredDistro)
        $prov = Ensure-WslTargetUser -Name $PreferredDistro
        if (-not $prov.AccountValid -or -not $prov.DefaultOk) {
            Write-KeepLog "dedicated import user provision incomplete account=$($prov.AccountValid) default=$($prov.DefaultOk) err=$($prov.Error)" -Level "WARN" -Stage "WAITING_FOR_WINDOWS"
        } else {
            Write-KeepLog "dedicated import user provisioned=$($prov.User)" -Stage "WAITING_FOR_WINDOWS"
        }
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
    Initialize-OtaconConsole
    $elapsed = (Get-Date) - $Started
    $em = "{0:00}m {1:00}s" -f [int]$elapsed.TotalMinutes, $elapsed.Seconds
    $since = "n/a"
    if ($PSBoundParameters.ContainsKey('LastProgress') -and $LastProgress) {
        $sp = (Get-Date) - $LastProgress
        $since = ("{0:00}m {1:00}s ago" -f [int]$sp.TotalMinutes, $sp.Seconds)
    }
    Clear-Host
    Write-Host ""
    Show-OtaconRule -Color Cyan
    Write-Host "  OTACON  //  DEEP INSTALL  //  [6/8] LINUX PAYLOAD" -ForegroundColor Cyan
    Show-OtaconRule -Color DarkCyan
    Write-Host "  LINK    : ACTIVE - leave this window open" -ForegroundColor Green
    $sub = "$Substep"
    if ($sub.Length -gt 58) { $sub = $sub.Substring(0, 58) }
    Write-Host ("  CURRENT : {0}" -f $sub) -ForegroundColor Yellow
    Write-Host ("  GPU WIN : {0}" -f $GpuWin) -ForegroundColor DarkCyan
    Write-Host ("  GPU WSL : {0}" -f $GpuWsl) -ForegroundColor DarkCyan
    Write-Host ("  ELAPSED : {0}   last pulse {1}" -f $em, $since) -ForegroundColor Gray
    Write-Host "  OTACON  : Installing Core - you don't need to touch anything." -ForegroundColor Cyan
    Show-OtaconRule -Color Cyan
    Write-Host "  LIVE FEED / FALLING CODE:" -ForegroundColor DarkCyan
    $shown = 0
    foreach ($t in $RecentLines) {
        if (-not $t) { continue }
        $line = $t.Trim()
        if ($line.Length -gt 58) { $line = $line.Substring(0, 58) }
        Write-Host ("    > {0}" -f $line) -ForegroundColor DarkGreen
        $shown++
        if ($shown -ge 6) { break }
    }
    if ($shown -eq 0) {
        Write-Host "    (awaiting Linux output...)" -ForegroundColor DarkGreen
    }
    $glyphs = Get-OtaconGlyphs
    $rnd = New-Object System.Random
    for ($r = 0; $r -lt 3; $r++) {
        $strip = -join (0..61 | ForEach-Object { $glyphs[$rnd.Next(0, $glyphs.Count)] })
        $c = if ($r -eq 0) { "Green" } elseif ($r -eq 1) { "DarkGreen" } else { "DarkCyan" }
        Write-Host ("  {0}" -f $strip) -ForegroundColor $c
    }
    Show-OtaconRule -Color Cyan
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

function ConvertTo-OtaconLinuxUsername {
    param([string]$Raw)
    if (-not $Raw) { $Raw = "" }
    $s = $Raw.Trim().ToLowerInvariant()
    $s = [regex]::Replace($s, '[^a-z0-9_-]', '')
    $s = [regex]::Replace($s, '^[^a-z_]+', '')
    if ($s.Length -gt 32) { $s = $s.Substring(0, 32) }
    if (-not $s -or $s -eq "root") { $s = "otacon" }
    return $s
}

function Get-OtaconExpectedWslUsername {
    <#
      Expected Linux username for dedicated Ubuntu-Otacon.
      Prefer OTACON_TARGET_USER, else sanitize the Windows username, else "otacon".
    #>
    $raw = ""
    if ($env:OTACON_TARGET_USER) { $raw = [string]$env:OTACON_TARGET_USER }
    if (-not $raw) { $raw = [string]$env:USERNAME }
    if (-not $raw) { $raw = "otacon" }
    return (ConvertTo-OtaconLinuxUsername -Raw $raw)
}

function Test-WslUserExists {
    param([string]$Name, [string]$User)
    if (-not $Name -or -not $User) { return $false }
    $esc = $User.Replace("'", "'\''")
    $out = & wsl.exe -d $Name -u root --exec id -u $User 2>$null
    if ($LASTEXITCODE -ne 0) { return $false }
    return $true
}

function Test-WslLinuxUserValid {
    <#
      State A - account validity only:
        user exists, is not root, home directory and login shell are usable.
      Does NOT check whether this account is the distro's effective default.
    #>
    param([string]$Name, [string]$User)
    if (-not $Name -or -not $User) { return $false }
    if ($User -eq "root") { return $false }
    $esc = $User.Replace("'", "'\''")
    $check = @"
u='$esc'
id "`$u" >/dev/null 2>&1 || exit 1
uid=`$(id -u "`$u")
home=`$(getent passwd "`$u" | cut -d: -f6)
shell=`$(getent passwd "`$u" | cut -d: -f7)
[ -n "`$uid" ] && [ "`$uid" -ge 1000 ] && [ "`$uid" -lt 65534 ] || exit 2
[ -n "`$home" ] && [ -d "`$home" ] || exit 3
case "`$shell" in */bash|*/sh|*/zsh|*/fish) ;; *) exit 4 ;; esac
echo ACCOUNT_VALID
"@
    $out = & wsl.exe -d $Name -u root -- bash -lc $check 2>$null
    return (("$out" | Out-String) -match 'ACCOUNT_VALID')
}

function Get-WslEffectiveDefaultUser {
    <#
      State B - effective default-user verification.
      Uses: wsl -d <distro> --exec id -un
    #>
    param([string]$Name)
    if (-not $Name) { return "" }
    try {
        $raw = & wsl.exe -d $Name --exec id -un 2>$null
        $u = (("{0}" -f ($raw | Select-Object -First 1))).Trim()
        if ($u) { return $u }
    } catch {}
    return ""
}

function Test-WslEffectiveDefaultUser {
    param([string]$Name, [string]$User)
    if (-not $Name -or -not $User -or $User -eq "root") { return $false }
    $eff = Get-WslEffectiveDefaultUser -Name $Name
    return ($eff -eq $User)
}

function Get-WslDefaultUser {
    <#
      Resolve a candidate non-root account for install targeting.
      Prefers effective default (B), then wsl.conf, then first uid>=1000 home user.
      Account validity (A) is checked separately by callers.
    #>
    param([string]$Name)
    if (-not $Name) { return "" }
    $eff = Get-WslEffectiveDefaultUser -Name $Name
    if ($eff -and $eff -ne "root") { return $eff }
    try {
        $conf = (& wsl.exe -d $Name -u root -- bash -lc "awk -F= '/^[[:space:]]*default=/ {gsub(/[[:space:]]/,\"\",`$2); print `$2; exit}' /etc/wsl.conf 2>/dev/null" 2>$null | Select-Object -Last 1)
        $cu = if ($conf) { ("{0}" -f $conf).Trim() } else { "" }
        if ($cu -and $cu -ne "root") {
            if (Test-WslUserExists -Name $Name -User $cu) { return $cu }
        }
    } catch {}
    try {
        $cand = (& wsl.exe -d $Name -u root -- bash -lc "getent passwd | awk -F: '`$3>=1000 && `$3<65534 && `$6 ~ /^\/home\// {print `$1; exit}'" 2>$null | Select-Object -Last 1)
        $c = if ($cand) { ("{0}" -f $cand).Trim() } else { "" }
        if ($c -and $c -ne "root") { return $c }
    } catch {}
    return ""
}

function Invoke-WslRootBashFile {
    param([string]$Name, [string]$ScriptWin)
    $scriptWsl = Convert-WindowsPathToWsl -Distro $Name -WindowsPath $ScriptWin -EnsureExists
    if (-not $scriptWsl) { return @{ Ok = $false; Output = "wslpath-failed" } }
    $scriptEsc = $scriptWsl.Replace("'", "'\''")
    $out = & wsl.exe -d $Name -u root -- bash -c "bash '$scriptEsc'" 2>&1
    return @{ Ok = $true; Output = (($out | Out-String)); ScriptWsl = $scriptWsl }
}

function Set-WslDefaultUser {
    <#
      Write /etc/wsl.conf [user] default= only. Does not touch passwords.
      -EnsureGroups is for newly created accounts; skip for already-valid users.
    #>
    param(
        [string]$Name,
        [string]$User,
        [switch]$EnsureGroups
    )
    if (-not $Name -or -not $User -or $User -eq "root") { return $false }
    $escUser = $User.Replace("'", "'\''")
    $groupBlock = if ($EnsureGroups) {
        @(
            'for g in sudo adm video render plugdev users audio cdrom dip docker; do',
            '  if getent group "$g" >/dev/null 2>&1; then usermod -aG "$g" "$USER_NAME" || true; fi',
            'done'
        )
    } else { @() }
    $bashLines = @(
        '#!/bin/bash',
        'set -euo pipefail',
        ("USER_NAME='{0}'" -f $escUser),
        'id "$USER_NAME" >/dev/null 2>&1 || exit 1'
    ) + $groupBlock + @(
        'WSL_CONF=/etc/wsl.conf',
        'touch "$WSL_CONF"',
        'if grep -qE "^[[:space:]]*\[user\]" "$WSL_CONF"; then',
        '  if grep -qE "^[[:space:]]*default[[:space:]]*=" "$WSL_CONF"; then',
        '    sed -i -E "s/^[[:space:]]*default[[:space:]]*=.*/default=${USER_NAME}/" "$WSL_CONF"',
        '  else',
        '    sed -i -E "/^[[:space:]]*\[user\]/a default=${USER_NAME}" "$WSL_CONF"',
        '  fi',
        'else',
        '  printf "\n[user]\ndefault=%s\n" "$USER_NAME" >>"$WSL_CONF"',
        'fi',
        'echo "OTACON_DEFAULT_SET=$USER_NAME"',
        'exit 0'
    )
    $scriptWin = Join-Path $LogDir "wsl-set-default-user.sh"
    $utf8NoBom = New-Object System.Text.UTF8Encoding $false
    [System.IO.File]::WriteAllText($scriptWin, (($bashLines -join "`n") + "`n"), $utf8NoBom)
    $result = Invoke-WslRootBashFile -Name $Name -ScriptWin $scriptWin
    return ($result.Ok -and ($result.Output -match 'OTACON_DEFAULT_SET'))
}

function Ensure-WslEffectiveDefaultUser {
    param([string]$Name, [string]$User)
    if (Test-WslEffectiveDefaultUser -Name $Name -User $User) { return $true }
    Write-KeepLog "Ensure-WslEffectiveDefaultUser: setting default=$User (account already valid)" -Stage "WSL_USER"
    if (-not (Set-WslDefaultUser -Name $Name -User $User)) { return $false }
    try { & wsl.exe --terminate $Name 2>$null | Out-Null } catch {}
    Start-Sleep -Seconds 2
    [void](Ensure-WslDistroRunning -Name $Name)
    return (Test-WslEffectiveDefaultUser -Name $Name -User $User)
}

function New-WslLinuxUser {
    <#
      Create a missing account only. Never runs against an existing user.
      New accounts may be passwordless (adduser --disabled-password / passwd -d
      only inside the create branch) because privileged install uses wsl -u root.
      Never clears an existing user's password.
    #>
    param([string]$Name, [string]$User)
    if (-not $Name -or -not $User -or $User -eq "root") { return $false }
    if (Test-WslUserExists -Name $Name -User $User) {
        Write-KeepLog "New-WslLinuxUser: refuse create; user already exists user=$User" -Stage "WSL_USER"
        return $false
    }
    $escUser = $User.Replace("'", "'\''")
    $bashLines = @(
        '#!/bin/bash',
        'set -euo pipefail',
        ("USER_NAME='{0}'" -f $escUser),
        'if id "$USER_NAME" >/dev/null 2>&1; then',
        '  echo "OTACON_USER_EXISTS=$USER_NAME"',
        '  exit 0',
        'fi',
        'if command -v adduser >/dev/null 2>&1; then',
        '  adduser --disabled-password --gecos "OtaconsKeep" "$USER_NAME"',
        'else',
        '  useradd -m -s /bin/bash -c "OtaconsKeep" "$USER_NAME"',
        '  # Passwordless only for brand-new accounts (no existing shadow entry).',
        '  passwd -d "$USER_NAME" >/dev/null 2>&1 || true',
        'fi',
        'HOME_DIR="$(getent passwd "$USER_NAME" | cut -d: -f6)"',
        'if [ -z "$HOME_DIR" ]; then echo "OTACON_USER_FAIL=no-home"; exit 1; fi',
        'if [ ! -d "$HOME_DIR" ]; then mkdir -p "$HOME_DIR"; chown "$USER_NAME":"$USER_NAME" "$HOME_DIR"; fi',
        'chsh -s /bin/bash "$USER_NAME" >/dev/null 2>&1 || usermod -s /bin/bash "$USER_NAME"',
        'for g in sudo adm video render plugdev users audio cdrom dip docker; do',
        '  if getent group "$g" >/dev/null 2>&1; then usermod -aG "$g" "$USER_NAME" || true; fi',
        'done',
        'uid="$(id -u "$USER_NAME")"',
        'shell="$(getent passwd "$USER_NAME" | cut -d: -f7)"',
        'groups="$(id -nG "$USER_NAME" | tr " " ",")"',
        'echo "OTACON_USER_CREATED=$USER_NAME uid=$uid home=$HOME_DIR shell=$shell groups=$groups"',
        'exit 0'
    )
    $scriptWin = Join-Path $LogDir "wsl-create-user.sh"
    $utf8NoBom = New-Object System.Text.UTF8Encoding $false
    [System.IO.File]::WriteAllText($scriptWin, (($bashLines -join "`n") + "`n"), $utf8NoBom)
    $result = Invoke-WslRootBashFile -Name $Name -ScriptWin $scriptWin
    Write-KeepLog "New-WslLinuxUser output: $($result.Output.Trim())" -Stage "WSL_USER"
    if ($result.Output -match 'OTACON_USER_EXISTS') { return (Test-WslLinuxUserValid -Name $Name -User $User) }
    return ($result.Ok -and ($result.Output -match 'OTACON_USER_CREATED') -and (Test-WslLinuxUserValid -Name $Name -User $User))
}

function Ensure-WslTargetUser {
    <#
      Resolve install target user with separate A/B states:
        A) account validity (exists, not root, home/shell)
        B) effective default (`wsl -d Distro --exec id -un` == target)
      Creates the account only when missing. Never clears an existing password.
      Does not recreate or group-modify an already-valid account.
    #>
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [string]$PreferredUser = ""
    )
    if (-not (Ensure-WslDistroRunning -Name $Name)) {
        Write-KeepLog "Ensure-WslTargetUser: distro not running name=$Name" -Level "ERROR" -Stage "WSL_USER"
        return @{ User = ""; AccountValid = $false; DefaultOk = $false; Error = "distro_not_running" }
    }

    $preferred = if ($PreferredUser) {
        ConvertTo-OtaconLinuxUsername -Raw $PreferredUser
    } else {
        Get-OtaconExpectedWslUsername
    }

    $candidate = $preferred
    if (-not (Test-WslUserExists -Name $Name -User $preferred)) {
        $alt = Get-WslDefaultUser -Name $Name
        if ($alt -and $alt -ne "root" -and (Test-WslLinuxUserValid -Name $Name -User $alt)) {
            Write-KeepLog "Ensure-WslTargetUser: preferred missing; reusing valid existing user=$alt" -Stage "WSL_USER"
            $candidate = $alt
        }
    }

    # --- State A: account validity ---
    if (-not (Test-WslLinuxUserValid -Name $Name -User $candidate)) {
        if (Test-WslUserExists -Name $Name -User $candidate) {
            Write-KeepLog "Ensure-WslTargetUser: ACCOUNT_INVALID user=$candidate (exists but home/shell/uid failed)" -Level "ERROR" -Stage "WSL_USER"
            return @{ User = $candidate; AccountValid = $false; DefaultOk = $false; Error = "account_invalid" }
        }
        Write-KeepLog "Ensure-WslTargetUser: ACCOUNT_MISSING user=$candidate - creating" -Stage "WSL_USER"
        Write-Host "  Creating Linux user '$candidate' in $Name..." -ForegroundColor Cyan
        if (-not (New-WslLinuxUser -Name $Name -User $candidate)) {
            Write-KeepLog "Ensure-WslTargetUser: create failed user=$candidate" -Level "ERROR" -Stage "WSL_USER"
            return @{ User = $candidate; AccountValid = $false; DefaultOk = $false; Error = "account_create_failed" }
        }
        # Groups + default for brand-new accounts only
        [void](Set-WslDefaultUser -Name $Name -User $candidate -EnsureGroups)
        try { & wsl.exe --terminate $Name 2>$null | Out-Null } catch {}
        Start-Sleep -Seconds 2
        [void](Ensure-WslDistroRunning -Name $Name)
    } else {
        Write-KeepLog "Ensure-WslTargetUser: ACCOUNT_VALID user=$candidate (not recreated; password untouched)" -Stage "WSL_USER"
    }

    if (-not (Test-WslLinuxUserValid -Name $Name -User $candidate)) {
        return @{ User = $candidate; AccountValid = $false; DefaultOk = $false; Error = "account_invalid" }
    }

    # --- State B: effective default-user ---
    $defaultOk = Test-WslEffectiveDefaultUser -Name $Name -User $candidate
    if (-not $defaultOk) {
        Write-KeepLog "Ensure-WslTargetUser: DEFAULT_MISMATCH want=$candidate effective=$(Get-WslEffectiveDefaultUser -Name $Name)" -Stage "WSL_USER"
        $defaultOk = Ensure-WslEffectiveDefaultUser -Name $Name -User $candidate
    } else {
        Write-KeepLog "Ensure-WslTargetUser: DEFAULT_OK user=$candidate (wsl --exec id -un)" -Stage "WSL_USER"
    }

    if (-not $defaultOk) {
        Write-KeepLog "Ensure-WslTargetUser: effective default still not $candidate" -Level "ERROR" -Stage "WSL_USER"
        return @{ User = $candidate; AccountValid = $true; DefaultOk = $false; Error = "default_mismatch" }
    }

    Write-Host "  [ok] Linux user ready: $candidate (account valid, effective default verified)" -ForegroundColor Green
    Save-InstallerState @{ wsl_user = $candidate }
    return @{ User = $candidate; AccountValid = $true; DefaultOk = $true; Error = "" }
}

function Format-StartProcessArgumentList {
    <#
      PowerShell Start-Process -ArgumentList <string[]> joins elements with spaces
      and does NOT quote tokens that contain whitespace or metacharacters. That
      splits a bash -c payload (spaces, pipes, redirects, &&/||/; ) across argv,
      so WSL starts but bash never runs the intended command.

      Return one Arguments string for Start-Process where each original token is
      preserved as a single CreateProcess argument (Windows CRT: quote when
      needed; double embedded quotes).
    #>
    param(
        [Parameter(Mandatory = $true)]
        [AllowEmptyCollection()]
        [string[]]$Arguments
    )
    $parts = New-Object System.Collections.Generic.List[string]
    foreach ($arg in $Arguments) {
        if ($null -eq $arg) { $arg = "" }
        $s = [string]$arg
        if ($s.Length -eq 0) {
            [void]$parts.Add('""')
            continue
        }
        if ($s -match '[\s"]') {
            [void]$parts.Add('"' + ($s.Replace('"', '""')) + '"')
        } else {
            [void]$parts.Add($s)
        }
    }
    return ($parts -join ' ')
}

function Start-OtaconWslBashCProcess {
    <#
      Production Windows -> WSL -> bash -c launcher.
      Always formats ArgumentList so the complete bash -c payload stays one argv.
      Captures stdout and stderr to separate files (Start-Process cannot redirect
      both streams to the same path).
    #>
    param(
        [Parameter(Mandatory = $true)][string]$Distro,
        [string[]]$UserArg = @(),
        [Parameter(Mandatory = $true)][string]$BashCommand,
        [Parameter(Mandatory = $true)][string]$StdoutPath,
        [string]$StderrPath = ""
    )
    if (-not $StderrPath) {
        $StderrPath = "$StdoutPath.stderr"
    }
    foreach ($p in @($StdoutPath, $StderrPath)) {
        if (Test-Path -LiteralPath $p) {
            Remove-Item -LiteralPath $p -Force -ErrorAction SilentlyContinue
        }
        try {
            $parent = [System.IO.Path]::GetDirectoryName($p)
            if ($parent -and -not (Test-Path -LiteralPath $parent)) {
                New-Item -ItemType Directory -Force -Path $parent | Out-Null
            }
            [System.IO.File]::WriteAllBytes($p, [byte[]]@())
        } catch {}
    }

    $rawArgs = @("-d", $Distro) + @($UserArg) + @("--", "bash", "-c", $BashCommand)
    # CRITICAL: pass one pre-quoted string - never a bare string[] - to Start-Process.
    $argString = Format-StartProcessArgumentList -Arguments $rawArgs
    $proc = Start-Process -FilePath "wsl.exe" -ArgumentList $argString `
        -NoNewWindow -PassThru `
        -RedirectStandardOutput $StdoutPath `
        -RedirectStandardError $StderrPath
    return @{
        Proc         = $proc
        StderrPath   = $StderrPath
        ArgumentList = $argString
        RawArgs      = $rawArgs
    }
}

function Get-OtaconMergedLogLines {
    param([string]$StdoutPath, [string]$StderrPath = "")
    $lines = New-Object System.Collections.Generic.List[string]
    foreach ($p in @($StdoutPath, $StderrPath)) {
        if (-not $p -or -not (Test-Path -LiteralPath $p)) { continue }
        foreach ($line in @(Get-Content -LiteralPath $p -ErrorAction SilentlyContinue)) {
            [void]$lines.Add([string]$line)
        }
    }
    return @($lines)
}

function Test-OtaconWslBashCLauncher {
    <#
      Harmless regression probe through the exact production launcher.
      Proves quoted args, spaces, pipes, redirects, and shell operators survive
      Windows -> WSL -> bash -c, with stdout+stderr+exit captured.
    #>
    param(
        [string]$Distro = "",
        [string]$OutDir = ""
    )
    if (-not $Distro) {
        try { $Distro = Get-UbuntuDistroName } catch { $Distro = "" }
    }
    if (-not $Distro) {
        Write-Host "FAIL ProbeWslLauncher: no WSL distro available"
        return 1
    }
    if (-not $OutDir) { $OutDir = $LogDir }
    New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

    $okOut = Join-Path $OutDir "wsl-bash-c-probe-ok.out"
    $okMarker = Join-Path $OutDir "wsl-bash-c-probe-ok.exit"
    $failOut = Join-Path $OutDir "wsl-bash-c-probe-fail.out"
    $failMarker = Join-Path $OutDir "wsl-bash-c-probe-fail.exit"
    foreach ($p in @($okOut, "$okOut.stderr", $okMarker, $failOut, "$failOut.stderr", $failMarker)) {
        if (Test-Path -LiteralPath $p) { Remove-Item -LiteralPath $p -Force -ErrorAction SilentlyContinue }
    }

    # Touch markers so wslpath-style paths are not required; write via bash redirect.
    [System.IO.File]::WriteAllBytes($okMarker, [byte[]]@())
    [System.IO.File]::WriteAllBytes($failMarker, [byte[]]@())
    $okMarkerWsl = Convert-WindowsPathToWsl -Distro $Distro -WindowsPath $okMarker -EnsureExists
    $failMarkerWsl = Convert-WindowsPathToWsl -Distro $Distro -WindowsPath $failMarker -EnsureExists
    if (-not $okMarkerWsl -or -not $failMarkerWsl) {
        Write-Host "FAIL ProbeWslLauncher: could not map exit marker paths into WSL"
        return 1
    }
    $okEsc = $okMarkerWsl.Replace("'", "'\''")
    $failEsc = $failMarkerWsl.Replace("'", "'\''")

    # Spaces + pipe + redirect + && / ; must remain one bash -c argv.
    $okCmd = ('set +e; echo "hello world" | tr a-z A-Z; echo PROBE_ERR >&2; true && echo PROBE_OK; rc=$?; printf ''%s\n'' "$rc" > ''{0}''; exit "$rc"' -f $okEsc)
    $launchOk = Start-OtaconWslBashCProcess -Distro $Distro -BashCommand $okCmd -StdoutPath $okOut
    $procOk = $launchOk.Proc
    if (-not $procOk.WaitForExit(120000)) {
        try { Stop-Process -Id $procOk.Id -Force -ErrorAction SilentlyContinue } catch {}
        Write-Host "FAIL ProbeWslLauncher: ok probe timed out"
        return 1
    }
    Start-Sleep -Milliseconds 200
    $okLines = Get-OtaconMergedLogLines -StdoutPath $okOut -StderrPath $launchOk.StderrPath
    $okText = ($okLines -join "`n")
    $okMarkerRaw = (Get-Content -LiteralPath $okMarker -TotalCount 1 -ErrorAction SilentlyContinue)
    $okCode = 0
    if (-not [int]::TryParse([string]$okMarkerRaw, [ref]$okCode)) { $okCode = 998 }

    $okPass = $true
    if ($okText -notmatch 'HELLO WORLD') {
        Write-Host "FAIL ProbeWslLauncher: stdout missing HELLO WORLD (pipe/spaces broken)"
        $okPass = $false
    }
    if ($okText -notmatch 'PROBE_ERR') {
        Write-Host "FAIL ProbeWslLauncher: stderr missing PROBE_ERR (redirect broken)"
        $okPass = $false
    }
    if ($okText -notmatch 'PROBE_OK') {
        Write-Host "FAIL ProbeWslLauncher: missing PROBE_OK (shell operators broken)"
        $okPass = $false
    }
    if ($okCode -ne 0) {
        Write-Host "FAIL ProbeWslLauncher: expected exit 0, marker='$okMarkerRaw' proc=$($procOk.ExitCode)"
        $okPass = $false
    }
    if ($launchOk.ArgumentList -notmatch '"set \+e;') {
        Write-Host "FAIL ProbeWslLauncher: ArgumentList did not quote bash -c payload"
        $okPass = $false
    }

    $failCmd = ('set +e; echo FAIL_OUT; echo FAIL_ERR >&2; false; rc=$?; printf ''%s\n'' "$rc" > ''{0}''; exit "$rc"' -f $failEsc)
    $launchFail = Start-OtaconWslBashCProcess -Distro $Distro -BashCommand $failCmd -StdoutPath $failOut
    $procFail = $launchFail.Proc
    if (-not $procFail.WaitForExit(120000)) {
        try { Stop-Process -Id $procFail.Id -Force -ErrorAction SilentlyContinue } catch {}
        Write-Host "FAIL ProbeWslLauncher: fail probe timed out"
        return 1
    }
    Start-Sleep -Milliseconds 200
    $failLines = Get-OtaconMergedLogLines -StdoutPath $failOut -StderrPath $launchFail.StderrPath
    $failText = ($failLines -join "`n")
    $failMarkerRaw = (Get-Content -LiteralPath $failMarker -TotalCount 1 -ErrorAction SilentlyContinue)
    $failCode = 0
    if (-not [int]::TryParse([string]$failMarkerRaw, [ref]$failCode)) { $failCode = 998 }

    $failPass = $true
    if ($failText -notmatch 'FAIL_OUT') {
        Write-Host "FAIL ProbeWslLauncher: failing command stdout missing"
        $failPass = $false
    }
    if ($failText -notmatch 'FAIL_ERR') {
        Write-Host "FAIL ProbeWslLauncher: failing command stderr missing"
        $failPass = $false
    }
    if ($failCode -eq 0) {
        Write-Host "FAIL ProbeWslLauncher: expected nonzero exit, marker='$failMarkerRaw'"
        $failPass = $false
    }

    if ($okPass -and $failPass) {
        Write-Host "PASS ProbeWslLauncher distro=$Distro ok_exit=$okCode fail_exit=$failCode"
        Write-KeepLog "ProbeWslLauncher PASS distro=$Distro ok=$okCode fail=$failCode" -Stage "PROBE"
        return 0
    }
    Write-Host "---- ok probe output ----"
    Write-Host $okText
    Write-Host "---- fail probe output ----"
    Write-Host $failText
    Write-KeepLog "ProbeWslLauncher FAIL distro=$Distro" -Level "ERROR" -Stage "PROBE"
    return 1
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

    # Run via production launcher. bash -c payload stays one quoted argv
    # (Format-StartProcessArgumentList). Merge script stderr with 2>&1 inside
    # bash, and also RedirectStandardError for wsl/bash startup noise.
    # Outer wrapper always writes EXIT_MARKER even if the phase script dies
    # before emit_rc.
    $phaseScriptEsc = $phaseScriptWsl.Replace("'", "'\''")
    $runner = ('set +e; bash ''{0}'' 2>&1; rc=$?; printf ''%s\n'' "$rc" > ''{1}''; exit "$rc"' -f $phaseScriptEsc, $exitMarkerEsc)
    $launch = Start-OtaconWslBashCProcess -Distro $Name -UserArg $userArg `
        -BashCommand $runner -StdoutPath $LogPipe
    $proc = $launch.Proc
    $errPipe = $launch.StderrPath
    Write-KeepLog "wsl bash -c payload preserved as one quoted ArgumentList token" -Stage "INSTALLING_OTACON"

    $lastProgress = Get-Date
    $lastByteLen = 0L
    $currentSub = "phase $Phase starting"
    # Overall timeout is per-phase, not from the start of Stage 6. Otherwise a
    # long privileged/user run (apt + voice trainer) immediately kills finalize
    # whose OverallTimeoutMin is only 15 minutes wall-clock from Stage 6 start.
    $phaseStarted = Get-Date

    while (-not $proc.HasExited) {
        $recent = @()
        $byteLen = 0L
        foreach ($pipePath in @($LogPipe, $errPipe)) {
            if (Test-Path -LiteralPath $pipePath) {
                $item = Get-Item -LiteralPath $pipePath -ErrorAction SilentlyContinue
                if ($item) { $byteLen += $item.Length }
            }
        }
        if ($byteLen -gt $lastByteLen) {
            $lastByteLen = $byteLen
            $lastProgress = Get-Date
        }
        $all = @(Get-OtaconMergedLogLines -StdoutPath $LogPipe -StderrPath $errPipe)
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
    foreach ($line in @(Get-OtaconMergedLogLines -StdoutPath $LogPipe -StderrPath $errPipe)) {
        if ($line -match 'OTACON_PHASE_EXIT=(\d+)') { $fromLog = [int]$Matches[1] }
        elseif ($line -match '\[STAGE\]\s+exit\s+CODE\s+(\d+)') { $fromLog = [int]$Matches[1] }
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

    if ($code -ne 0 -and $code -ne 42) {
        Write-KeepLog "---- linux-install-tail (phase=$Phase, last 40) ----" -Level "ERROR" -Stage "INSTALLING_OTACON"
        foreach ($line in @((Get-OtaconMergedLogLines -StdoutPath $LogPipe -StderrPath $errPipe) | Select-Object -Last 40)) {
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
    # Dedicated Ubuntu-Otacon imports start with only root - auto-provision the expected user.
    # Keep account validity (A) and effective default-user (B) as separate failure states.
    $prov = Ensure-WslTargetUser -Name $Name
    $targetUser = [string]$prov.User
    if (-not $prov.AccountValid) {
        $acctErr = switch ($prov.Error) {
            "account_invalid" { "Linux user '$targetUser' exists but is not a valid install account (home/shell/uid). The password was not changed." }
            "account_create_failed" { "Could not create Linux user '$targetUser' in $Name." }
            "distro_not_running" { "WSL distro '$Name' is not running, so the Linux account could not be checked." }
            default { "Linux account for OtaconsKeep is missing or invalid in '$Name' (got='$targetUser')." }
        }
        Write-KeepLog "WSL ACCOUNT_VALID=false user='$targetUser' err=$($prov.Error)" -Level "ERROR" -Stage "INSTALLING_OTACON"
        Show-SetupNeedsHelp -Step "installing otacon (linux account invalid)" -PlainError (
            "$acctErr Check Logs under %LOCALAPPDATA%\OtaconsKeep\Logs, then rerun Setup."
        ) | Out-Null
        return 1
    }
    if (-not $prov.DefaultOk) {
        $eff = Get-WslEffectiveDefaultUser -Name $Name
        Write-KeepLog "WSL DEFAULT_OK=false want='$targetUser' effective='$eff' (account is valid)" -Level "ERROR" -Stage "INSTALLING_OTACON"
        Show-SetupNeedsHelp -Step "installing otacon (WSL default user mismatch)" -PlainError (
            "Linux account '$targetUser' is valid, but the effective WSL default user is '$eff' (expected '$targetUser' from: wsl -d $Name --exec id -un). Account validity passed; only the distro default-user setting failed. Check /etc/wsl.conf [user] default= and rerun Setup."
        ) | Out-Null
        return 1
    }
    Write-KeepLog "WSL user=$targetUser account_valid=true default_ok=true (no NOPASSWD:ALL; using wsl -u root for privileged steps)" -Stage "INSTALLING_OTACON"

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
    # Also drop Open Otacon + Fix Codec launchers (double-click, no pasting)
    $assistant = Join-Path $RepoRoot "deploy\windows-setup-assistant.ps1"
    $repairPs1 = Join-Path $RepoRoot "deploy\repair-otacon-core.ps1"
    $openBat = Join-Path $KeepDir "Open-Otacon.bat"
    @"
@echo off
title Open Otacon Codec
powershell -NoProfile -ExecutionPolicy Bypass -File "$assistant" -Open -RepoRoot "$RepoRoot"
if errorlevel 1 pause
"@ | Set-Content -Path $openBat -Encoding ASCII
    $fixBat = Join-Path $KeepDir "Fix-Otacon-Codec.bat"
    @"
@echo off
title Fix Otacon Codec
echo Reviving Otacon Core / Codec - do not close this window.
powershell -NoProfile -ExecutionPolicy Bypass -File "$repairPs1" -OpenBrowser -Codec -Port $Port
echo.
echo Done. Press any key to close.
pause >nul
"@ | Set-Content -Path $fixBat -Encoding ASCII
    Write-KeepLog "wake task + Open-Otacon.bat + Fix-Otacon-Codec.bat registered ok=$(Test-WakeTaskRegistered)" -Stage "STARTING"
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
    Write-KeepLog "installer launch Resume=$Resume Force=$($script:ForceInstall) AutoPilot=$($script:AutoPilot)" -Stage "READY"

    $st = Get-InstallerState
    if ($Resume -or $st["stage"] -eq "waiting_for_reboot" -or $st["resume_registered"]) {
        Write-OtaconSay "Welcome back. Windows restarted cleanly - picking up right where we left off." -Mood "ok"
        Clear-ResumeMarkers
        Start-Sleep -Seconds 1
    }

    $snap = Get-WhereYouAre
    # Quiet status strip (no interactive menu)
    Write-OtaconSay ("Scan complete. Overall: {0}" -f $snap.overall) -Mood "work" -NoType

    # Gate B: foreign HTTP on 5757 must never look like READY
    if ($snap.occupied_non_otacon) {
        Write-OtaconSay "Port $Port is occupied by something that isn't me. I can't safely continue." -Mood "alert"
        Show-NonOtaconPortDiagnostic (Test-OtaconIdentity)
        return 1
    }

    # Gate A: healthy existing install - AutoPilot opens Codec; no O/F/P/R menu.
    if ($snap.web_health -and -not $script:ForceInstall) {
        $ttsOk = [bool]$snap.tts_ok
        if ($ttsOk) {
            Save-InstallerComplete
            Write-OtaconSay "You're already online. Opening Codec now." -Mood "ok"
            $ubuntuOpen = Get-UbuntuDistroName
            if ($ubuntuOpen) { [void](Invoke-OtaconCoreRepair -Name $ubuntuOpen) }
            try { Start-Process (Get-OtaconOpenUrl -Codec) } catch {}
            Show-Box "LINK ESTABLISHED" @(
                "Otacon is ready.",
                (Get-OtaconOpenUrl -Codec),
                "",
                "You can close this window."
            ) -Color Green
            return 0
        }
        # TTS down - auto-repair without asking
        Save-InstallerState @{ stage = "degraded"; last_error = "TTS down: $($snap.tts_reason)" }
        Write-OtaconSay "Chat is up, but voice needs a tune-up. I'll repair that automatically." -Mood "warn"
        $script:ForceInstall = $true
        $ubuntu = Get-UbuntuDistroName
        if ($ubuntu -and (Invoke-RepairTtsAndWake -Name $ubuntu)) {
            Save-InstallerComplete
            Write-OtaconSay "Voice restored. Opening Codec." -Mood "ok"
            try { Start-Process (Get-OtaconOpenUrl -Codec) } catch {}
            return 0
        }
        Write-OtaconSay "Quick repair wasn't enough - continuing full setup." -Mood "work" -NoType
    } elseif ($snap.web_health -and $script:ForceInstall) {
        Write-KeepLog "Force/Repair/Reinstall bypass of READY short-circuit" -Stage "READY"
        Write-OtaconSay "Force/repair mode engaged. I'll handle it." -Mood "work" -NoType
        if ($Repair -or ($script:ForceInstall -and -not $script:ReinstallRequested)) {
            $ubuntu = Get-UbuntuDistroName
            if ($ubuntu -and (Invoke-RepairTtsAndWake -Name $ubuntu)) {
                Save-InstallerComplete
                Write-OtaconSay "Repair complete. Opening Codec." -Mood "ok"
                try { Start-Process (Get-OtaconOpenUrl -Codec) } catch {}
                return 0
            }
        }
    } elseif (-not $snap.web_health) {
        $ubuntuDead = Get-UbuntuDistroName
        if ($ubuntuDead -and (Test-OtaconFiles $ubuntuDead)) {
            Write-OtaconSay "I found Otacon files, but the service is asleep. Waking it..." -Mood "work"
            Write-KeepLog "auto core repair (web down, files present) distro=$ubuntuDead" -Stage "REPAIR"
            if (Invoke-OtaconCoreRepair -Name $ubuntuDead -Codec) {
                Save-InstallerComplete
                Write-OtaconSay "Back online. Opening Codec." -Mood "ok"
                try { Start-Process (Get-OtaconOpenUrl -Codec) } catch {}
                return 0
            }
            Write-OtaconSay "Wake attempt failed - continuing full install path." -Mood "warn" -NoType
        }
    }

    Write-OtaconSay "You don't need to know Linux. I'm handling the installation." -Mood "info"
    Write-OtaconSay "This can take 10-30 minutes. Your PC may look busy - that's normal. Don't close this window." -Mood "work" -NoType
    Start-Sleep -Milliseconds 800

    # [1/8] checking windows
    Write-OtaconSay "[1/$TotalSteps] Checking Windows..." -Mood "work" -NoType
    Write-KeepLog "step1 windows ok" -Stage "WORKING"
    Write-Host "  [ok] Windows session detected" -ForegroundColor Green

    # [2/8] virtualization / admin for feature enable
    Write-OtaconSay "[2/$TotalSteps] Checking permissions / virtualization..." -Mood "work" -NoType

    # [3/8] WSL - AutoPilot distro selection (no R/C/A menu)
    Write-OtaconSay "[3/$TotalSteps] Checking Windows Linux (WSL)..." -Mood "work" -NoType
    Write-WslListVerbose
    $ubuntu = Resolve-OtaconDistroInteractive
    if ($null -eq $ubuntu) {
        Write-OtaconSay "I couldn't choose a Linux environment. Existing installs were left alone." -Mood "alert"
        return 1
    }
    $needCreate = -not (Get-WslUbuntuFamilyNames | Where-Object { $_.Equals($ubuntu, [System.StringComparison]::OrdinalIgnoreCase) })
    if (-not (Test-WslPresent) -or $needCreate) {
        Write-OtaconSay "Windows may ask for administrator permission - click Yes when prompted." -Mood "warn"
        if (-not (Ensure-Admin)) { return 0 }
        Write-OtaconSay "Preparing Linux environment ($ubuntu)..." -Mood "work" -NoType
        $code = Step-EnableWsl -DistroName $ubuntu
        $ubuntu = Get-UbuntuDistroName
        if (-not $ubuntu) {
            # Prefer stock Ubuntu if wsl --install created it but first-boot not finished.
            $fam = Get-WslUbuntuFamilyNames
            $stock = $fam | Where-Object { $_.Equals("Ubuntu", [StringComparison]::OrdinalIgnoreCase) } | Select-Object -First 1
            if ($stock) { $ubuntu = $stock; Save-InstallerState @{ ubuntu_name = $stock; ubuntu_mode = "reuse" } }
            else { $ubuntu = $PreferredDistro }
        }
        if (-not (Test-UbuntuReady $ubuntu)) {
            $fam2 = Get-WslUbuntuFamilyNames
            if ($fam2.Count -gt 0) {
                # Distro listed but not ready - finish first-time Ubuntu setup (no more reboot loop).
                Write-KeepLog "distro present but not ready - waiting for Ubuntu init ($ubuntu)" -Stage "WAITING_FOR_UBUNTU_SETUP"
                Write-OtaconSay "Finishing first-time Linux boot. You shouldn't need to type anything." -Mood "work" -NoType
                [void](Step-WaitUbuntuInit -Name $ubuntu)
            } else {
                $s2 = Get-WhereYouAre
                if (-not $s2.ubuntu_ready) {
                    Request-RestartConfirmation
                    return 0
                }
            }
        }
    } else {
        Write-OtaconSay "WSL already online (distro=$ubuntu)." -Mood "ok" -NoType
        Save-InstallerState @{ ubuntu_name = $ubuntu }
    }

    # [4/8] ubuntu
    Write-OtaconSay "[4/$TotalSteps] Checking Ubuntu inside Windows..." -Mood "work" -NoType
    $ubuntu = Get-UbuntuDistroName
    if (-not $ubuntu) {
        Write-OtaconSay "Windows may ask for administrator permission - click Yes." -Mood "warn"
        if (-not (Ensure-Admin)) { return 0 }
        Step-EnableWsl -DistroName $PreferredDistro | Out-Null
        $ubuntu = Get-UbuntuDistroName
        if (-not $ubuntu) {
            $act = Show-SetupNeedsHelp -Step "installing ubuntu" -PlainError "Windows did not create an Ubuntu environment for OtaconsKeep yet. A restart may still be required."
            if ($act -eq "retry") { return (Start-GuidedSetup) }
            return 1
        }
    } else {
        Write-OtaconSay "Ubuntu environment present: $ubuntu" -Mood "ok" -NoType
    }

    # [5/8] prepare ubuntu - AutoPilot provisions user; no password prompts
    Write-OtaconSay "[5/$TotalSteps] Preparing your Linux user (no password needed)..." -Mood "work" -NoType
    if (-not (Test-UbuntuReady $ubuntu)) {
        Write-OtaconSay "Bringing the Linux environment online..." -Mood "work" -NoType
        [void](Ensure-WslDistroRunning -Name $ubuntu)
        $ubuntu = Get-UbuntuDistroName
    }
    $prov = Ensure-WslTargetUser -Name $ubuntu
    if (-not $prov.AccountValid -or -not $prov.DefaultOk) {
        if (-not (Test-UbuntuReady $ubuntu)) {
            $ok = Step-WaitUbuntuInit -Name $ubuntu
            $ubuntu = Get-UbuntuDistroName
            if (-not $ok) {
                Register-ResumeAfterReboot
                Write-OtaconSay "Almost there - Windows may need one restart. I'll reopen setup after you sign back in." -Mood "warn"
                Show-Box "RESTART PENDING" @(
                    "Leave the rest to me after reboot.",
                    "This is NOT your Proxmox Ubuntu VM."
                ) -Color Yellow
                Request-RestartConfirmation
                return 0
            }
            $prov = Ensure-WslTargetUser -Name $ubuntu
        }
    }
    if ($prov.AccountValid -and $prov.DefaultOk) {
        Write-OtaconSay "Linux user ready: $($prov.User)" -Mood "ok" -NoType
    } else {
        Write-OtaconSay "Linux account setup incomplete (account=$($prov.AccountValid) default=$($prov.DefaultOk)). Continuing - Stage 6 will retry." -Mood "warn" -NoType
    }

    Clear-ResumeMarkers

    # [6/8] install otacon
    Write-OtaconSay "[6/$TotalSteps] Installing Otacon Core into Linux. This is the long part - falling code means I'm working." -Mood "work"
    $preTts = Test-OtaconTts
    if ((-not $script:ForceInstall) -and (Test-OtaconFiles $ubuntu) -and (Test-OtaconHealth) -and $preTts.ok) {
        Write-OtaconSay "Otacon is already installed and healthy." -Mood "ok" -NoType
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
            Write-OtaconSay "Core is up, but an optional piece failed - not fully green yet." -Mood "warn" -NoType
            Save-InstallerState @{ stage = "degraded"; last_error = "Linux installer returned DEGRADED (exit 2)" }
        }
    }

    # [7/8] starting services
    Write-OtaconSay "[7/$TotalSteps] Starting services and wake task..." -Mood "work" -NoType
    $wakeOk = Step-RegisterWakeTask -Name $ubuntu
    if (-not $wakeOk) {
        Write-OtaconSay "Wake task didn't register (permissions). Voice may need a manual start after reboot." -Mood "warn" -NoType
        Write-KeepLog "wake task missing before READY" -Level "WARN" -Stage "STARTING"
    }
    & wsl.exe -d $ubuntu -u root -- bash -lc "systemctl start otacon-tts.service 2>/dev/null; systemctl start otacon.service 2>/dev/null; true" 2>$null | Out-Null
    Write-OtaconSay "Bringing the Keep online..." -Mood "work" -NoType

    # [8/8] verify - identity + TTS health required for green READY
    Write-OtaconSay "[8/$TotalSteps] Final systems check..." -Mood "work" -NoType
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
            Write-OtaconSay "Chat answered, but voice needs repair. Fixing automatically..." -Mood "warn"
            if (Invoke-RepairTtsAndWake -Name $ubuntu) {
                Save-InstallerComplete
                Write-OtaconSay "Voice restored. Opening Codec." -Mood "ok"
                try { Start-Process (Get-OtaconOpenUrl -Codec) } catch {}
                return 0
            }
            Write-OtaconSay "Voice still degraded. You can rerun Setup with --repair later." -Mood "warn"
            return 2
        }
        $act = Show-SetupNeedsHelp -Step "starting otacon" -PlainError "Otacon did not answer http://localhost:$Port/api/branding yet. The install may still be finishing - retry in a minute."
        if ($act -eq "retry") { return (Start-GuidedSetup) }
        return 1
    }

    if (-not (Test-WakeTaskRegistered)) {
        Write-OtaconSay "Wake task still missing - registering once more." -Mood "warn" -NoType
        [void](Step-RegisterWakeTask -Name $ubuntu)
    }

    Save-InstallerComplete
    Clear-ResumeMarkers
    $ttsFinal = Test-OtaconTts
    $readyUrl = Get-OtaconOpenUrl -Codec
    Write-OtaconSay "Installation complete. Identity OK. Voice: $($ttsFinal.reason)." -Mood "ok"
    Show-OtaconRain -Frames 8 -DelayMs 30
    Show-Box "LINK ESTABLISHED" @(
        "Otacon is ready.",
        "",
        $readyUrl,
        "",
        "Opening Codec automatically.",
        "You can close this window."
    ) -Color Green
    Write-KeepLog "COMPLETE identity+tts health ok wake=$(Test-WakeTaskRegistered)" -Stage "COMPLETE"
    try { Start-Process $readyUrl } catch {}
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
    if ($ProbeWslLauncher) {
        exit (Test-OtaconWslBashCLauncher -Distro $ProbeDistro)
    }
    if ($Diagnostics) { Write-DiagnosticsFile | Out-Null; exit 0 }
    if ($FixCodec) {
        $ubuntu = Get-UbuntuDistroName
        $ok = Invoke-OtaconCoreRepair -Name $ubuntu -OpenBrowser -Codec
        exit $(if ($ok) { 0 } else { 1 })
    }
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
