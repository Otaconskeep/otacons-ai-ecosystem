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
    # Prefer systemd units. GPU probe has its own hang timeout in platform.detect -
    # do NOT force OTACON_SKIP_NVIDIA_SMI (that caused false "no GPU detected").
    $script = @'
set +e
pkill -f "wyoming-piper.*10200" 2>/dev/null || true
sleep 1
UNIT=/etc/systemd/system/otacon.service
if [ -f "$UNIT" ]; then
  if grep -q "OTACON_SKIP_NVIDIA_SMI=" "$UNIT"; then
    sed -i '/OTACON_SKIP_NVIDIA_SMI=/d' "$UNIT"
  fi
  grep -q "OTACON_HOST=0.0.0.0" "$UNIT" || sed -i "s|^Environment=OTACON_HOST=.*|Environment=OTACON_HOST=0.0.0.0|" "$UNIT"
  # Preserve LAN auth mode; default local (0) if unset. Bind-all != LAN auth.
  if ! grep -q "OTACON_LAN_MODE=" "$UNIT"; then
    sed -i "/\[Service\]/a Environment=OTACON_LAN_MODE=0" "$UNIT"
  fi
  systemctl daemon-reload >/dev/null 2>&1 || true
fi
if systemctl list-unit-files otacon-tts.service >/dev/null 2>&1; then
  systemctl enable otacon-tts.service >/dev/null 2>&1 || true
  systemctl restart otacon-tts.service >/dev/null 2>&1 || systemctl start otacon-tts.service >/dev/null 2>&1 || true
fi
systemctl enable otacon.service >/dev/null 2>&1 || true
systemctl restart otacon.service >/dev/null 2>&1 || systemctl start otacon.service >/dev/null 2>&1 || true
sleep 2
if ! curl -fsS --max-time 2 http://127.0.0.1:5757/api/branding >/dev/null 2>&1; then
  ROOT="$(ls -d /home/*/otacon-ai-ecosystem 2>/dev/null | head -n1)"
  if [ -n "$ROOT" ] && [ -x "$ROOT/.venv/bin/python" ]; then
    OWNER="$(stat -c %U "$ROOT" 2>/dev/null || echo root)"
    mkdir -p "/home/${OWNER}/.config/otacon" 2>/dev/null || true
    if command -v runuser >/dev/null 2>&1 && [ "$OWNER" != "root" ]; then
      runuser -u "$OWNER" -- env OTACON_HOST=0.0.0.0 OTACON_LAN_MODE=0 OTACON_PORT=5757 PYTHONPATH="$ROOT" \
        bash -lc "cd \"$ROOT\" && unset OTACON_SKIP_NVIDIA_SMI && nohup \"$ROOT/.venv/bin/python\" -m installer.server >\$HOME/.config/otacon/wizard.log 2>&1 &"
    fi
  fi
fi
'@
    $helper = Join-Path $PSScriptRoot "wsl-bash-file.ps1"
    if (Test-Path -LiteralPath $helper) {
        . $helper
        $run = Invoke-OtaconWslBashFile -Distro $DistroName -ScriptBody $script -User "root" -Label "otacon-wake"
        Write-Log ("wake wsl stage={0} exit={1}" -f $run.Stage, $run.ExitCode)
    } else {
        # Last-resort short commands only (never multiline bash -lc payloads).
        Write-Log "wsl-bash-file.ps1 missing; using short --exec commands"
        & wsl.exe -d $DistroName -u root --exec bash -c "systemctl restart otacon-tts.service 2>/dev/null; systemctl restart otacon.service 2>/dev/null; true" 2>$null | Out-Null
    }
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
    Write-Log "Not up after $TimeoutSeconds s - starting otacon-tts + otacon via systemd"
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
