# OtaconsKeep WSL keepalive - keeps the selected distro from idling out.
# Paths and distro are always dynamic (never hardcoded usernames or Ubuntu-Otacon).
#
# Equivalent durable behavior to: wsl.exe -d <distro> --exec sleep infinity
# - single instance via named mutex
# - hidden (launched by Startup VBS / scheduled task)
# - retry with backoff after unexpected exit
# - logs to %LOCALAPPDATA%\OtaconsKeep\keepalive.log
# - does not busy-loop

param(
    [Parameter(Mandatory = $true)][string]$DistroName,
    [int]$Port = 5757,
    [switch]$Once
)

$ErrorActionPreference = "Continue"
$InstallerRoot = Join-Path $env:LOCALAPPDATA "OtaconsKeep"
New-Item -ItemType Directory -Force -Path $InstallerRoot | Out-Null
$logFile = Join-Path $InstallerRoot "keepalive.log"

function Write-KeepAliveLog([string]$Message) {
    $line = "$(Get-Date -Format o)  $Message"
    try { Add-Content -LiteralPath $logFile -Value $line -Encoding utf8 } catch {}
}

# Duplicate prevention: only one keepalive per Windows user session.
$mutexName = "Local\OtaconsKeep.WSL.KeepAlive.$($env:USERNAME)"
$created = $false
$mutex = $null
try {
    $mutex = New-Object System.Threading.Mutex($false, $mutexName, [ref]$created)
} catch {
    Write-KeepAliveLog "mutex create failed: $($_.Exception.Message)"
    exit 1
}
if (-not $mutex.WaitOne(0)) {
    Write-KeepAliveLog "another keepalive already running for user=$($env:USERNAME) - exiting"
    exit 0
}

Write-KeepAliveLog "keepalive start distro=$DistroName port=$Port user=$($env:USERNAME) profile=$($env:USERPROFILE)"

function Start-OtaconUnits {
    try {
        & wsl.exe -d $DistroName -u root --exec systemctl start otacon-tts.service 2>$null | Out-Null
    } catch {}
    try {
        & wsl.exe -d $DistroName -u root --exec systemctl start otacon.service 2>$null | Out-Null
    } catch {}
}

$backoffSec = 5
try {
    while ($true) {
        # Soft wake + ensure managed units (idempotent).
        try {
            & wsl.exe -d $DistroName --exec /bin/true 2>$null | Out-Null
        } catch {
            Write-KeepAliveLog "distro wake failed: $($_.Exception.Message)"
        }
        Start-OtaconUnits

        # Hold the distro open (Codex-proven pattern). Selected distro only.
        Write-KeepAliveLog "holding WSL with: wsl -d $DistroName --exec sleep infinity"
        $p = $null
        try {
            $p = Start-Process -FilePath "wsl.exe" `
                -ArgumentList @("-d", $DistroName, "--exec", "sleep", "infinity") `
                -WindowStyle Hidden -PassThru
            $p.WaitForExit()
            $code = [int]$p.ExitCode
            Write-KeepAliveLog "sleep infinity exited code=$code"
        } catch {
            Write-KeepAliveLog "sleep infinity launch failed: $($_.Exception.Message)"
            $code = 1
        }

        if ($Once) { break }

        # Backoff before retry (no busy-loop). Cap at 5 minutes.
        Write-KeepAliveLog "retry after ${backoffSec}s"
        Start-Sleep -Seconds $backoffSec
        if ($backoffSec -lt 300) { $backoffSec = [Math]::Min(300, $backoffSec * 2) }
    }
} finally {
    try { [void]$mutex.ReleaseMutex() } catch {}
    try { $mutex.Dispose() } catch {}
    Write-KeepAliveLog "keepalive stop"
}
