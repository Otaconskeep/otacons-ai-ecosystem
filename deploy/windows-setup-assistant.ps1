# OtaconsKeep Windows Setup Assistant
# Guided, nontechnical installer UX for Otacon Core on Windows 11.
# Invoked by OtaconsKeep-Setup.bat / install_otacon.bat - do not store credentials.

[CmdletBinding()]
param(
    [switch]$Status,
    [switch]$Diagnostics,
    [switch]$Open,
    [switch]$Resume,
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

New-Item -ItemType Directory -Force -Path $KeepDir, $LogDir, $DiagDir | Out-Null

if (-not $RepoRoot) {
    $RepoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
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
    foreach ($k in $Fields.Keys) { $cur[$k] = $Fields[$k] }
    $cur["version"] = 1
    $cur["updated_at"] = (Get-Date).ToUniversalTime().ToString("o")
    ($cur | ConvertTo-Json -Depth 6) | Set-Content -Path $StateFile -Encoding UTF8
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
        $k = [Console]::ReadKey($true)
        Write-Host $k.KeyChar
        $ch = ($k.KeyChar.ToString()).ToUpperInvariant()
        if ($Allowed -contains $ch) { return $ch }
        # also accept Enter mapping if included
        if ($k.Key -eq "Enter" -and ($Allowed -contains "ENTER")) { return "ENTER" }
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

function Get-UbuntuDistroName {
    $finder = Join-Path $RepoRoot "deploy\find-ubuntu.ps1"
    if (Test-Path $finder) {
        $name = & powershell -NoProfile -ExecutionPolicy Bypass -File $finder 2>$null
        if ($name) { return ($name | Select-Object -First 1).ToString().Trim() }
    }
    try {
        $raw = & wsl.exe -l -q 2>$null
        $clean = $raw | ForEach-Object { $_ -replace "`0", "" } | Where-Object { $_.Trim() -ne "" }
        $match = $clean | Where-Object { $_ -match "(?i)^Ubuntu" -and $_ -notmatch "(?i)docker-desktop" } | Select-Object -First 1
        if ($match) { return $match.Trim() }
    } catch {}
    return $null
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
    & wsl.exe -d $Name -- bash -lc "test -x `$HOME/.local/bin/otacon || test -d `$HOME/otacon || test -d /opt/otacon" 2>$null | Out-Null
    return ($LASTEXITCODE -eq 0)
}

function Test-OtaconService {
    param([string]$Name)
    if (-not $Name) { return $false }
    $out = & wsl.exe -d $Name -- bash -lc "systemctl is-active otacon 2>/dev/null || true" 2>$null
    return (($out | Out-String) -match "active")
}

function Test-OtaconHealth {
    try {
        $r = Invoke-WebRequest -Uri $HealthUrl -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop
        if ($r.StatusCode -lt 200 -or $r.StatusCode -ge 500) { return $false }
        try {
            $b = Invoke-WebRequest -Uri $BrandUrl -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop
            if ($b.StatusCode -ge 200 -and $b.StatusCode -lt 500) { return $true }
        } catch {
            # root answered; branding optional
            return $true
        }
        return $true
    } catch { return $false }
}

function Get-WhereYouAre {
    $admin = Test-IsAdmin
    $wsl = Test-WslPresent
    $ubuntu = Get-UbuntuDistroName
    $ubuntuReady = Test-UbuntuReady $ubuntu
    $files = Test-OtaconFiles $ubuntu
    $svc = Test-OtaconService $ubuntu
    $health = Test-OtaconHealth
    $state = Get-InstallerState
    $rebootPending = $false
    try {
        $rb = Test-Path "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Component Based Servicing\RebootPending"
        $wu = Test-Path "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\RebootRequired"
        if ($rb -or $wu) { $rebootPending = $true }
    } catch {}
    if ($state["stage"] -eq "waiting_for_reboot") { $rebootPending = $true }

    $overall = "WORKING"
    if ($health -and $files) { $overall = "COMPLETE" }
    elseif (-not $wsl -or $rebootPending) { $overall = if ($rebootPending) { "WAITING_FOR_REBOOT" } else { "WAITING_FOR_WINDOWS" } }
    elseif ($wsl -and -not $ubuntuReady) { $overall = "WAITING_FOR_UBUNTU_SETUP" }
    elseif ($ubuntuReady -and -not $files) { $overall = "INSTALLING_OTACON" }
    elseif ($files -and -not $health) { $overall = "VERIFYING" }
    elseif ($health) { $overall = "READY" }

    return [ordered]@{
        admin           = $admin
        wsl             = $wsl
        ubuntu_name     = $ubuntu
        ubuntu_ready    = $ubuntuReady
        otacon_files    = $files
        otacon_service  = $svc
        web_health      = $health
        reboot_pending  = $rebootPending
        overall         = $overall
        state_stage     = $state["stage"]
    }
}

function Show-WhereYouAre {
    param($Snap)
    $wslL = if ($Snap.wsl) { "ready" } else { "not ready" }
    $rbL  = if ($Snap.reboot_pending) { "still required" } else { "not needed" }
    $ubL  = if ($Snap.ubuntu_ready) { "ready ($($Snap.ubuntu_name))" } elseif ($Snap.ubuntu_name) { "installed but not finished setup" } else { "not ready yet" }
    $otL  = if ($Snap.web_health) { "running" } elseif ($Snap.otacon_files) { "installed (starting)" } else { "not installed yet" }
    $webL = if ($Snap.web_health) { "responding" } else { "not available yet" }

    $next = "please wait - setup will continue"
    if ($Snap.overall -eq "COMPLETE" -or $Snap.web_health) {
        $next = "open http://localhost:$Port - Otacon is ready"
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
    Write-KeepLog "where-you-are overall=$($Snap.overall) wsl=$($Snap.wsl) ubuntu=$($Snap.ubuntu_ready) health=$($Snap.web_health)" -Stage "STATUS"
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
    Write-Host ""
    Write-Host "overall status" -ForegroundColor Yellow
    Write-Host ""
    Write-Host $(if ($s.web_health) { "READY" } else { $s.overall })
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
    # Quote for cmd.exe RunOnce; supports spaces and parentheses in the path.
    $cmd = '"' + $launcher + '"'
    reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\RunOnce" /v OtaconsKeepSetupResume /t REG_SZ /d $cmd /f | Out-Null
    Save-InstallerState @{ stage = "waiting_for_reboot"; resume_registered = $true }
    Write-KeepLog "RunOnce registered for $launcher" -Stage "WAITING_FOR_REBOOT"
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
    # Pass path as FilePath argument data - never concatenate into a -Command string.
    Start-Process -FilePath $bat -WorkingDirectory (Split-Path -Parent $bat) -Verb RunAs
    Write-Host ""
    Write-Host "  A new elevated Setup window should open after you click Yes." -ForegroundColor Green
    Write-Host "  You can close THIS window now - setup continues in the new one." -ForegroundColor Green
    Write-Host "  If you clicked No on the Windows popup, press X to exit, or R to try again." -ForegroundColor DarkYellow
    Write-Host ""
    while ($true) {
        $c = Read-Choice "  Choice [R/X]: " @("R","X")
        if ($c -eq "X") { return $false }
        if ($c -eq "R") {
            Start-Process -FilePath $bat -WorkingDirectory (Split-Path -Parent $bat) -Verb RunAs
            continue
        }
    }
}

function Step-EnableWsl {
    Write-KeepLog "wsl --install -d Ubuntu" -Stage "WAITING_FOR_WINDOWS"
    Save-InstallerState @{ stage = "waiting_for_windows"; step = 3 }
    $started = Get-Date
    Show-WorkingPanel -Step 3 -StepName "PREPARING WINDOWS" -Detail "Windows is currently enabling Linux support" -Started $started -Typical "2 to 10 minutes"
    $p = Start-Process -FilePath "wsl.exe" -ArgumentList "--install","-d","Ubuntu" -PassThru -NoNewWindow
    while (-not $p.HasExited) {
        Show-WorkingPanel -Step 3 -StepName "PREPARING WINDOWS" -Detail "Windows is currently enabling Linux support" -Started $started -Typical "2 to 10 minutes"
        Write-Host "  [ OTACON ] still working - do not close this window" -ForegroundColor DarkGray
        Start-Sleep -Seconds 4
    }
    Write-KeepLog "wsl --install exit=$($p.ExitCode)" -Stage "WAITING_FOR_WINDOWS"
    return $p.ExitCode
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

    $bash = @"
set -euo pipefail
TMP=`$(mktemp /tmp/otacon-install.XXXXXX.sh)
trap 'rm -f "`$TMP"' EXIT
curl -fsSL --connect-timeout 30 --max-time 120 https://raw.githubusercontent.com/Otaconskeep/otacons-ai-ecosystem/$Branch/install_otacon.sh -o "`$TMP"
test -s "`$TMP" || { echo 'Download failed or empty installer' >&2; exit 1; }
head -n1 "`$TMP" | grep -q bash || { echo 'Downloaded file does not look like the Otacon installer' >&2; exit 1; }
env $EnvPass OTACON_INSTALL_PHASE=$Phase $targetEnv bash "`$TMP"
"@

    if (Test-Path $LogPipe) { Remove-Item -LiteralPath $LogPipe -Force -ErrorAction SilentlyContinue }
    Write-KeepLog "starting linux phase=$Phase as=$AsUser target=$TargetUser in $Name" -Stage "INSTALLING_OTACON"

    $bashWrapped = $bash + " 2>&1"
    $argList = @("-d", $Name) + $userArg + @("--", "bash", "-lc", $bashWrapped)
    $proc = Start-Process -FilePath "wsl.exe" -ArgumentList $argList `
        -NoNewWindow -PassThru -RedirectStandardOutput $LogPipe

    $lastProgress = Get-Date
    $lastByteLen = 0L
    $currentSub = "phase $Phase starting"

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
                } elseif ($line -match '\[AGG::HEARTBEAT\]') {
                    $lastProgress = Get-Date
                    $currentSub = $line.Substring(0, [Math]::Min(90, $line.Length))
                } elseif ($line -match '\[AGG::PROGRESS\]') {
                    $lastProgress = Get-Date
                } elseif ($line -match 'pulling|Downloading|Get:|Unpacking|Setting up') {
                    $lastProgress = Get-Date
                }
            }
            $recent = @($all | Select-Object -Last 5)
        }

        Show-Stage6Panel -Started $Started -Substep ("[{0}] {1}" -f $Phase, $currentSub) -RecentLines $recent `
            -LastProgress $lastProgress -GpuWin $GpuWin -GpuWsl $GpuWsl

        $elapsedMin = ((Get-Date) - $Started).TotalMinutes
        $stallMin = ((Get-Date) - $lastProgress).TotalMinutes
        if ($elapsedMin -ge $OverallTimeoutMin) {
            try { Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue } catch {}
            Write-KeepLog "stage6 overall timeout ${OverallTimeoutMin}m phase=$Phase" -Level "ERROR" -Stage "INSTALLING_OTACON"
            return 124
        }
        if ($stallMin -ge $StallTimeoutMin) {
            try { Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue } catch {}
            Write-KeepLog "stage6 stall timeout ${StallTimeoutMin}m phase=$Phase substep=$currentSub" -Level "ERROR" -Stage "INSTALLING_OTACON"
            return 125
        }
        Start-Sleep -Seconds 5
    }

    $code = $proc.ExitCode
    Write-KeepLog "linux phase=$Phase exit=$code" -Stage "INSTALLING_OTACON"
    return $code
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
        break
    }
    if ($code -ne 0) {
        if (Test-Path $logPipe) {
            Write-Host "---- last 50 log lines (privileged) ----" -ForegroundColor Yellow
            Get-Content $logPipe -Tail 50 -ErrorAction SilentlyContinue | ForEach-Object { Write-Host $_ }
        }
        Show-SetupNeedsHelp -Step "installing otacon (privileged bootstrap)" -PlainError (
            "Root bootstrap failed (exit $code). No sudo password was required; this uses wsl -u root. Log: $logPipe"
        ) | Out-Null
        return $code
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
        return $code
    }
    $userCode = $code

    # --- Phase 3: finalize (wsl -u root) — install systemd unit drafted by user phase ---
    $code = Invoke-WslInstallPhase -Name $Name -Phase "finalize" -AsUser "root" -TargetUser $targetUser `
        -EnvPass $envPass -Started $started -GpuWin $gpuWin -GpuWsl $gpuWsl -LogPipe $logPipe `
        -OverallTimeoutMin 15 -StallTimeoutMin 10
    if ($code -ne 0) {
        if (Test-Path $logPipe) {
            Write-Host "---- last 50 log lines (finalize) ----" -ForegroundColor Yellow
            Get-Content $logPipe -Tail 50 -ErrorAction SilentlyContinue | ForEach-Object { Write-Host $_ }
        }
        Write-KeepLog "finalize failed exit=$code (user phase was $userCode); service may still be running via nohup" -Level "WARN" -Stage "INSTALLING_OTACON"
        # Degraded: user phase may have started Otacon via nohup; don't hard-fail READY if user was 0/2
        if ($userCode -eq 0 -or $userCode -eq 2) { return $userCode }
        return $code
    }

    return $userCode
}

function Step-RegisterWakeTask {
    param([string]$Name)
    $ps1 = Join-Path $RepoRoot "deploy\install-wake-task.ps1"
    if (-not (Test-Path $ps1)) {
        Write-KeepLog "install-wake-task.ps1 missing - skip" -Level "WARN" -Stage "STARTING"
        return $false
    }
    & powershell -NoProfile -ExecutionPolicy Bypass -File $ps1 -DistroName $Name -Port $Port | Out-Null
    # Also drop an Open Otacon launcher
    $openBat = Join-Path $KeepDir "Open-Otacon.bat"
    $assistant = Join-Path $RepoRoot "deploy\windows-setup-assistant.ps1"
    @"
@echo off
title Open Otacon
powershell -NoProfile -ExecutionPolicy Bypass -File "$assistant" -Open -RepoRoot "$RepoRoot"
"@ | Set-Content -Path $openBat -Encoding ASCII
    Write-KeepLog "wake task + Open-Otacon.bat registered" -Stage "STARTING"
    return $true
}

function Step-Verify {
    param([string]$Name)
    Save-InstallerState @{ stage = "verifying"; step = 8 }
    $started = Get-Date
    for ($i = 0; $i -lt 40; $i++) {
        Show-WorkingPanel -Step 8 -StepName "VERIFYING OTACON" -Detail "Performing final systems check on localhost:$Port" -Started $started -Typical "1 to 3 minutes"
        if (Test-OtaconHealth) { return $true }
        # try start service
        & wsl.exe -d $Name -u root -- systemctl start otacon 2>$null | Out-Null
        Start-Sleep -Seconds 3
    }
    return (Test-OtaconHealth)
}

# ---------------------------------------------------------------------------
# Main guided flow
# ---------------------------------------------------------------------------
function Start-GuidedSetup {
    Show-Banner
    Write-KeepLog "installer launch Resume=$Resume" -Stage "READY"

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

    if ($snap.web_health) {
        Show-Box "OTACON IS READY" @(
            "installation completed successfully",
            "",
            "otacon responded to its health check",
            "",
            "open otacon",
            "",
            "http://localhost:$Port",
            "",
            "press O to open otacon",
            "press X to finish"
        ) -Color Green
        Save-InstallerState @{ stage = "complete" }
        $c = Read-Choice "  Choice [O/X]: " @("O","X")
        if ($c -eq "O") { Start-Process $HealthUrl }
        return 0
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

    # [3/8] WSL
    Write-Host "  [3/$TotalSteps] checking wsl" -ForegroundColor Cyan
    $ubuntu = Get-UbuntuDistroName
    if (-not (Test-WslPresent) -or -not $ubuntu) {
        if (-not (Ensure-Admin)) { return 0 }
        Write-Host "  [ OTACON ] preparing linux environment" -ForegroundColor Cyan
        $code = Step-EnableWsl
        $ubuntu = Get-UbuntuDistroName
        if (-not (Test-UbuntuReady $ubuntu)) {
            # Often reboot required after feature enable
            $s2 = Get-WhereYouAre
            if (-not $s2.ubuntu_ready) {
                Request-RestartConfirmation
                return 0
            }
        }
    } else {
        Write-Host "  [ok] wsl already installed" -ForegroundColor Green
    }

    # [4/8] ubuntu
    Write-Host "  [4/$TotalSteps] installing / checking ubuntu (inside Windows)" -ForegroundColor Cyan
    $ubuntu = Get-UbuntuDistroName
    if (-not $ubuntu) {
        if (-not (Ensure-Admin)) { return 0 }
        Step-EnableWsl | Out-Null
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
    if (Test-OtaconFiles $ubuntu -and (Test-OtaconHealth)) {
        Write-Host "  [ok] otaconskeep already installed and healthy" -ForegroundColor Green
    } else {
        $rc = Step-InstallOtacon -Name $ubuntu
        if ($rc -ne 0 -and $rc -ne 2) {
            $act = Show-SetupNeedsHelp -Step "installing otacon" -PlainError "The Linux installer exited with code $rc. Your files were not wiped. You can retry."
            if ($act -eq "retry") { return (Start-GuidedSetup) }
            return $rc
        }
        if ($rc -eq 2) {
            Write-Host "  [warn] Otacon installed DEGRADED (core up, optional piece failed)" -ForegroundColor DarkYellow
        }
    }

    # [7/8] starting services
    Write-Host "  [7/$TotalSteps] starting services" -ForegroundColor Cyan
    Step-RegisterWakeTask -Name $ubuntu | Out-Null
    & wsl.exe -d $ubuntu -u root -- systemctl start otacon 2>$null | Out-Null
    Write-Host "  [ OTACON ] bringing the keep online" -ForegroundColor Cyan

    # [8/8] verify
    Write-Host "  [8/$TotalSteps] verifying otacon" -ForegroundColor Cyan
    Write-Host "  [ OTACON ] performing final systems check" -ForegroundColor Cyan
    if (-not (Step-Verify -Name $ubuntu)) {
        $act = Show-SetupNeedsHelp -Step "starting otacon" -PlainError "Otacon did not answer http://localhost:$Port yet. The install may still be finishing - retry in a minute."
        if ($act -eq "retry") { return (Start-GuidedSetup) }
        return 1
    }

    Save-InstallerState @{ stage = "complete"; step = 8 }
    Clear-ResumeMarkers
    Show-Box "OTACON IS READY" @(
        "installation completed successfully",
        "",
        "otacon responded to its health check",
        "",
        "open otacon",
        "",
        "http://localhost:$Port",
        "",
        "you can close this setup window now",
        "",
        "press O to open otacon",
        "press X to finish"
    ) -Color Green
    Write-KeepLog "COMPLETE health ok" -Stage "COMPLETE"
    $c = Read-Choice "  Choice [O/X]: " @("O","X")
    if ($c -eq "O") { Start-Process $HealthUrl }
    return 0
}

# ---------------------------------------------------------------------------
# Entry
# ---------------------------------------------------------------------------
try {
    if ($Status) { Show-StatusReport; exit 0 }
    if ($Diagnostics) { Write-DiagnosticsFile | Out-Null; exit 0 }
    if ($Open) {
        $cont = Open-OtaconIfReady
        if ($cont -and -not (Test-OtaconHealth)) { exit (Start-GuidedSetup) }
        exit 0
    }
    exit (Start-GuidedSetup)
} catch {
    Write-KeepLog "UNHANDLED $($_.Exception.Message)" -Level "ERROR" -Stage "FAILED"
    Show-SetupNeedsHelp -Step "unexpected error" -PlainError $_.Exception.Message | Out-Null
    exit 1
}
