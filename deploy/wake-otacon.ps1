# Wakes the Otacon WSL environment and waits for it to answer, silently.
# No windows, no browser launch -- this only runs from a logon scheduled
# task so Otacon is already warm by the time someone opens it manually.
#
# P0-1: Always start otacon-tts before otacon. Kill orphan nohup Piper so
# systemd owns :10200. Branding identity required (not bare HTTP 200).
param(
    [Parameter(Mandatory = $true)][string]$DistroName,
    [int]$Port = 5757,
    [int]$TimeoutSeconds = 25
)

$logDir = "$env:LOCALAPPDATA\Otacon"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$logFile = Join-Path $logDir "wake-log.txt"

function Write-Log($msg) {
    "$(Get-Date -Format o)  $msg" | Out-File -FilePath $logFile -Append -Encoding utf8
}

function Test-Otacon {
    try {
        $brand = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/api/branding" -TimeoutSec 2 -UseBasicParsing -ErrorAction Stop
        if ($brand.StatusCode -lt 200 -or $brand.StatusCode -ge 300) { return $false }
        $json = $brand.Content | ConvertFrom-Json
        return ([string]$json.product_name -eq "Otacon")
    } catch {
        return $false
    }
}

function Start-OtaconStack {
    # Prefer systemd units. Clear orphan nohup piper that would mask a dead unit.
    $script = @'
set -e
pkill -f "wyoming-piper.*10200" 2>/dev/null || true
sleep 1
if systemctl list-unit-files otacon-tts.service >/dev/null 2>&1; then
  systemctl enable otacon-tts.service >/dev/null 2>&1 || true
  systemctl restart otacon-tts.service >/dev/null 2>&1 || systemctl start otacon-tts.service >/dev/null 2>&1 || true
fi
systemctl enable otacon.service >/dev/null 2>&1 || true
systemctl restart otacon.service >/dev/null 2>&1 || systemctl start otacon.service >/dev/null 2>&1 || true
# Soft ensure: if unit missing but piper venv exists, fall back once
if ! systemctl is-active --quiet otacon-tts.service 2>/dev/null; then
  if [ -x "$HOME/.local/bin/otacon" ] || [ -d "$HOME/otacon" ] || [ -d /opt/otacon ]; then
    true
  fi
fi
'@
    & wsl.exe -d $DistroName -u root -- bash -lc $script 2>$null | Out-Null
}

Write-Log "Waking $DistroName"
try {
    & wsl.exe -d $DistroName --exec /bin/true 2>$null | Out-Null
} catch {
    Write-Log "Initial wake command failed: $_"
}

$up = $false
$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
while ((Get-Date) -lt $deadline) {
    if (Test-Otacon) { $up = $true; break }
    Start-Sleep -Seconds 2
}

if (-not $up) {
    Write-Log "Not up after $TimeoutSeconds s — starting otacon-tts + otacon via systemd"
    try {
        Start-OtaconStack
    } catch {
        Write-Log "stack start failed: $_"
    }

    $deadline2 = (Get-Date).AddSeconds(20)
    while ((Get-Date) -lt $deadline2) {
        if (Test-Otacon) { $up = $true; break }
        Start-Sleep -Seconds 2
    }
} else {
    # Even when UI is already up, ensure TTS unit is running (P0-1)
    try {
        & wsl.exe -d $DistroName -u root -- bash -lc "systemctl is-active --quiet otacon-tts.service || systemctl start otacon-tts.service" 2>$null | Out-Null
    } catch {}
}

Write-Log "Result: up=$up"
