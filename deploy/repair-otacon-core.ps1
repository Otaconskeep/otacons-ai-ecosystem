# Revive Otacon Core inside WSL when Codec / localhost:5757 is dead.
# Handles: hung nvidia-smi wedging the server, service killed, localhost
# forwarding broken (use WSL IP), Open Codec blocked on /api/scan.
#
# Usage (from OtaconsKeep-Setup.bat / install_otacon.bat):
#   --fix-codec
# Or:
#   powershell -File deploy\repair-otacon-core.ps1 -OpenBrowser

[CmdletBinding()]
param(
    [string]$DistroName = "",
    [int]$Port = 5757,
    [switch]$OpenBrowser,
    [switch]$Codec,
    [int]$TimeoutSeconds = 45
)

$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"

$KeepDir = Join-Path $env:LOCALAPPDATA "OtaconsKeep"
$LogDir = Join-Path $KeepDir "Logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$LogFile = Join-Path $LogDir "repair-otacon-core.log"

function Write-RepairLog([string]$Message) {
    $line = "$(Get-Date -Format o)  $Message"
    try { Add-Content -LiteralPath $LogFile -Value $line -Encoding utf8 } catch {}
    Write-Host "  $Message"
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
    # Last resort: any Ubuntu* except bare stock "Ubuntu" (often broken)
    $family = Get-CandidateDistros | Where-Object { -not $_.Equals("Ubuntu", [StringComparison]::OrdinalIgnoreCase) }
    if ($family.Count -gt 0) { return $family[0] }
    $stock = Get-CandidateDistros | Where-Object { $_.Equals("Ubuntu", [StringComparison]::OrdinalIgnoreCase) } | Select-Object -First 1
    return $stock
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
    if ($ip -match '^\d{1,3}(\.\d{1,3}){3}$') {
        $bases += "http://${ip}:$PortNum"
    }
    foreach ($b in $bases) {
        if (Test-BrandAt $b) { return $b }
    }
    return $null
}

function Ensure-DistroRunning([string]$Name) {
    Write-RepairLog "Ensuring WSL distro running: $Name"
    try {
        & wsl.exe -d $Name --exec /bin/true 2>$null | Out-Null
    } catch {}
    Start-Sleep -Seconds 1
    try {
        & wsl.exe -d $Name --exec /bin/true 2>$null | Out-Null
        return ($LASTEXITCODE -eq 0)
    } catch { return $false }
}

function Invoke-WslCoreRepair([string]$Name, [int]$PortNum) {
    # Single-quoted bash body — no PowerShell && / & parsing pitfalls.
    # Pulls latest GitHub tree, removes the old SKIP_NVIDIA / scan=null patches
    # that falsely showed "No GPU reported", then restarts Codec.
    $bash = @'
set +e
PORT="__PORT__"
echo "=== repair-otacon-core begin ==="
ROOT="$(ls -d /home/*/otacon-ai-ecosystem 2>/dev/null | head -n1)"
if [ -z "$ROOT" ] && [ -d /root/otacon-ai-ecosystem ]; then ROOT=/root/otacon-ai-ecosystem; fi
echo "ROOT=$ROOT"
if [ -z "$ROOT" ] || [ ! -d "$ROOT" ]; then
  echo "NO_INSTALL_TREE"
  exit 2
fi
OWNER="$(stat -c %U "$ROOT" 2>/dev/null || echo root)"
echo "OWNER=$OWNER"
UNIT=/etc/systemd/system/otacon.service

# Pull the pushed fix (memory/THINKING/GPU) — restart alone is not enough.
if [ -d "$ROOT/.git" ]; then
  echo "=== git pull ==="
  echo "before=$(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || echo none)"
  git -C "$ROOT" fetch --prune origin 2>&1 | tail -n 5
  if ! git -C "$ROOT" pull --ff-only origin main 2>&1; then
    echo "ff-only failed; hard reset to origin/main"
    git -C "$ROOT" reset --hard origin/main 2>&1 | tail -n 5
  fi
  echo "after=$(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || echo none)"
  echo "revision_file=$(cat "$ROOT/deploy/installer-revision.txt" 2>/dev/null | head -n1)"
fi

# Stop wedged server (nvidia-smi D-state can pin a single-thread handler forever)
systemctl stop otacon.service 2>/dev/null || true
pkill -9 -f "python -m installer.server" 2>/dev/null || true
pkill -9 -f "installer.server" 2>/dev/null || true
sleep 1

if [ -f "$UNIT" ]; then
  # REMOVE legacy skip — it forced "No GPU reported" even when CUDA worked.
  if grep -q "OTACON_SKIP_NVIDIA_SMI=" "$UNIT"; then
    sed -i '/OTACON_SKIP_NVIDIA_SMI=/d' "$UNIT"
    echo "removed_OTACON_SKIP_NVIDIA_SMI_from_unit"
  fi
  # Pin skip=0 so a later wake/login cannot reintroduce the lie.
  sed -i "/\[Service\]/a Environment=OTACON_SKIP_NVIDIA_SMI=0" "$UNIT"
  echo "pinned_OTACON_SKIP_NVIDIA_SMI=0"
  # Prefer all-interfaces bind so Windows can use localhost OR the WSL IP
  if grep -q "OTACON_HOST=" "$UNIT"; then
    sed -i "s|^Environment=OTACON_HOST=.*|Environment=OTACON_HOST=0.0.0.0|" "$UNIT"
  else
    sed -i "/\[Service\]/a Environment=OTACON_HOST=0.0.0.0" "$UNIT"
  fi
  if grep -q "OTACON_PORT=" "$UNIT"; then
    sed -i "s|^Environment=OTACON_PORT=.*|Environment=OTACON_PORT=${PORT}|" "$UNIT"
  else
    sed -i "/\[Service\]/a Environment=OTACON_PORT=${PORT}" "$UNIT"
  fi
  systemctl daemon-reload 2>/dev/null || true
  systemctl enable otacon.service 2>/dev/null || true
  systemctl enable otacon-tts.service 2>/dev/null || true
  systemctl restart otacon-tts.service 2>/dev/null || systemctl start otacon-tts.service 2>/dev/null || true
  systemctl restart otacon.service 2>/dev/null || systemctl start otacon.service 2>/dev/null || true
  sleep 2
  systemctl is-active otacon.service 2>/dev/null || echo "unit_not_active"
fi

# Undo old repair hot-patch that forced scan=null (lied about GPU).
# Timed /api/scan is safe: platform.detect abandons hung nvidia-smi.
WIZARD="$ROOT/ui/wizard.js"
if [ -f "$WIZARD" ]; then
  python3 - "$WIZARD" <<'PY'
import pathlib, sys
p = pathlib.Path(sys.argv[1])
t = p.read_text(encoding="utf-8", errors="replace")
orig = t
bad = "scan=null; /* repair: never block Codec on GPU scan */"
good = "try{scan=await apiGet('/api/scan',8000)}catch(e){scan=null}"
if bad in t:
    t = t.replace(bad, good)
    print("unpatched_wizard_scan_null")
else:
    print("wizard_scan_ok")
if t != orig:
    p.write_text(t, encoding="utf-8")
PY
fi

# Manual start if systemd did not bring branding up
alive=0
if curl -fsS --max-time 3 "http://127.0.0.1:${PORT}/api/branding" >/dev/null 2>&1; then
  alive=1
fi
if [ "$alive" -ne 1 ] && [ -x "$ROOT/.venv/bin/python" ]; then
  echo "manual_start"
  mkdir -p "/home/${OWNER}/.config/otacon" /root/.config/otacon 2>/dev/null || true
  LOGF="/home/${OWNER}/.config/otacon/wizard.log"
  if [ "$OWNER" = "root" ]; then LOGF=/root/.config/otacon/wizard.log; fi
  # Do NOT set OTACON_SKIP_NVIDIA_SMI — GPU detect has its own timeout.
  if command -v runuser >/dev/null 2>&1 && [ "$OWNER" != "root" ]; then
    runuser -u "$OWNER" -- env \
      OTACON_HOST=0.0.0.0 \
      OTACON_PORT="$PORT" \
      PYTHONPATH="$ROOT" \
      PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/usr/lib/wsl/lib" \
      LD_LIBRARY_PATH="/usr/lib/wsl/lib" \
      bash -lc "cd \"$ROOT\" && nohup \"$ROOT/.venv/bin/python\" -m installer.server >\"$LOGF\" 2>&1 & echo \$! >\"\$HOME/.config/otacon/wizard.pid\""
  else
    cd "$ROOT" || exit 3
    export OTACON_HOST=0.0.0.0 OTACON_PORT="$PORT" PYTHONPATH="$ROOT"
    unset OTACON_SKIP_NVIDIA_SMI
    export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/usr/lib/wsl/lib:$PATH"
    export LD_LIBRARY_PATH="/usr/lib/wsl/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
    nohup "$ROOT/.venv/bin/python" -m installer.server >/tmp/otacon-wizard.log 2>&1 &
    echo $! >/tmp/otacon-wizard.pid
  fi
  sleep 3
fi

echo "=== listen ==="
ss -lntp 2>/dev/null | grep ":${PORT}" || netstat -lntp 2>/dev/null | grep ":${PORT}" || echo NOT_LISTENING
echo "=== branding ==="
curl -fsS --max-time 5 "http://127.0.0.1:${PORT}/api/branding" || echo BRANDING_FAIL
echo
echo "=== scan gpu ==="
curl -fsS --max-time 12 "http://127.0.0.1:${PORT}/api/scan" 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); h=((d.get('hardware') or {}).get('hardware') or {}); print('gpus', h.get('gpus')); print('det', h.get('gpu_detection'))" 2>/dev/null || echo SCAN_FAIL
echo "=== done ==="
'@
    $bash = $bash.Replace("__PORT__", [string]$PortNum)
    Write-RepairLog "Running in-WSL core repair (git pull + undo GPU skip)..."
    $out = & wsl.exe -d $Name -u root -- bash -lc $bash 2>&1
    $text = ($out | Out-String)
    Write-RepairLog ($text.Trim())
    return $text
}

# --- main ---
Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  OTACON CORE REPAIR" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

$distro = Resolve-Distro -Preferred $DistroName
if (-not $distro) {
    Write-RepairLog "ERROR: No Ubuntu/Otacon WSL distro found. Run OtaconsKeep-Setup.bat first."
    exit 2
}
Write-RepairLog "DISTRO=$distro"

if (-not (Ensure-DistroRunning $distro)) {
    Write-RepairLog "WARN: distro may still be starting"
    Start-Sleep -Seconds 3
}

[void](Invoke-WslCoreRepair -Name $distro -PortNum $Port)

$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
$base = $null
while ((Get-Date) -lt $deadline) {
    $base = Find-WorkingBase -Name $distro -PortNum $Port
    if ($base) { break }
    Start-Sleep -Seconds 2
}

if (-not $base) {
    Write-RepairLog "FAILED: Otacon still not answering on localhost or WSL IP after repair."
    Write-RepairLog "Log: $LogFile"
    Write-Host ""
    Write-Host "  Press any key to close." -ForegroundColor DarkYellow
    try { [void][Console]::ReadKey($true) } catch { Start-Sleep 3 }
    exit 1
}

$openUrl = if ($Codec -or $OpenBrowser) { "$base/?codec=1" } else { "$base/" }
Write-RepairLog "OK base=$base"
Write-Host ""
Write-Host "  Otacon is up: $base" -ForegroundColor Green
Write-Host "  Codec:       $base/?codec=1" -ForegroundColor Green
Write-Host ""

if ($OpenBrowser -or $Codec) {
    try { Start-Process $openUrl } catch { Write-RepairLog "Start-Process failed: $_" }
}

# Persist last good URL for Open-Otacon.bat helpers
try {
    $urlFile = Join-Path $KeepDir "last-otacon-url.txt"
    Set-Content -LiteralPath $urlFile -Value $base -Encoding ASCII
} catch {}

exit 0
