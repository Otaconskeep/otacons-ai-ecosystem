# Fix false "No GPU detected" / "No GPU reported" on WSL Otacon installs.
# Double-click Fix-Otacon-GPU.bat (or run this script). No menus.
#
# Does:
#   1) Find Ubuntu/Otacon WSL distro
#   2) git fetch + reset --hard origin/main in the install tree
#   3) Force Environment=OTACON_SKIP_NVIDIA_SMI=0 in otacon.service
#   4) Restart otacon + show /api/scan GPU result
#   5) Open Codec

[CmdletBinding()]
param(
    [string]$DistroName = "",
    [int]$Port = 5757
)

$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"

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

function Resolve-Distro([string]$Preferred) {
    if ($Preferred) {
        $hit = Get-CandidateDistros | Where-Object { $_.Equals($Preferred, [StringComparison]::OrdinalIgnoreCase) } | Select-Object -First 1
        if ($hit) { return $hit }
    }
    foreach ($want in @("Ubuntu-Otacon", "OtaconsKeep", "Ubuntu-22.04", "Ubuntu-24.04")) {
        $hit = Get-CandidateDistros | Where-Object { $_.Equals($want, [StringComparison]::OrdinalIgnoreCase) } | Select-Object -First 1
        if ($hit) { return $hit }
    }
    $family = Get-CandidateDistros | Where-Object { -not $_.Equals("Ubuntu", [StringComparison]::OrdinalIgnoreCase) }
    if ($family.Count -gt 0) { return $family[0] }
    return (Get-CandidateDistros | Select-Object -First 1)
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  OTACON GPU FIX" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

$distro = Resolve-Distro $DistroName
if (-not $distro) {
    Write-Host "ERROR: No Ubuntu/Otacon WSL distro found. Install Otacon first." -ForegroundColor Red
    exit 2
}
Write-Host " Distro: $distro"

# Preflight: Windows vs WSL visibility (Josh / RTX 4090 class false-negatives).
$winGpu = "not visible"
try {
    $o = & nvidia-smi --query-gpu=name --format=csv,noheader 2>$null
    if ($o) { $winGpu = (($o | Select-Object -First 1).ToString().Trim()) }
} catch {}
$wslGpu = "not visible"
try {
    $probe = 'export PATH=/usr/lib/wsl/lib:$PATH; export LD_LIBRARY_PATH=/usr/lib/wsl/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}; SMI=$(command -v nvidia-smi 2>/dev/null); [ -z "$SMI" ] && [ -x /usr/lib/wsl/lib/nvidia-smi ] && SMI=/usr/lib/wsl/lib/nvidia-smi; [ -n "$SMI" ] && "$SMI" --query-gpu=name --format=csv,noheader 2>/dev/null | head -n1'
    $o2 = & wsl.exe -d $distro -- bash -lc $probe 2>$null
    if ($o2) {
        $s = ($o2 | Out-String).Trim()
        if ($s) { $wslGpu = $s }
    }
} catch {}
Write-Host " Windows GPU: $winGpu"
Write-Host " WSL GPU:     $wslGpu"
$cfg = Join-Path $env:USERPROFILE ".wslconfig"
if (Test-Path -LiteralPath $cfg) {
    $rawCfg = Get-Content -LiteralPath $cfg -Raw -ErrorAction SilentlyContinue
    if ($rawCfg -match '(?im)^\s*gpuSupport\s*=\s*false\s*$') {
        Write-Host " WARNING: .wslconfig has gpuSupport=false - remove that line, then: wsl --shutdown" -ForegroundColor Yellow
    }
}
if ($winGpu -ne "not visible" -and $wslGpu -eq "not visible") {
    Write-Host " Windows sees NVIDIA but WSL does not yet - will repair PATH/SKIP + re-probe." -ForegroundColor Yellow
    Write-Host " If this still fails: update NVIDIA Windows driver, run wsl --update, wsl --shutdown." -ForegroundColor Yellow
}

$bash = @'
set +e
PORT="__PORT__"
echo "=== fix-otacon-gpu begin ==="
ROOT=""
while IFS=: read -r _u _x _uid _gid _gecos home _shell; do
  case "$home" in ""|"/"|"/nonexistent") continue ;; esac
  if [ -d "$home/otacon-ai-ecosystem" ]; then ROOT="$home/otacon-ai-ecosystem"; break; fi
done <<EOF
$(getent passwd)
EOF
if [ -z "$ROOT" ] && [ -d /root/otacon-ai-ecosystem ]; then ROOT=/root/otacon-ai-ecosystem; fi
echo "ROOT=$ROOT"
if [ -z "$ROOT" ] || [ ! -d "$ROOT" ]; then
  echo "NO_INSTALL_TREE"
  exit 2
fi

OWNER="$(stat -c '%U' "$ROOT" 2>/dev/null || true)"
OWNER_UID="$(stat -c '%u' "$ROOT" 2>/dev/null || true)"
echo "OWNER=${OWNER:-}"
echo "OWNER_UID=${OWNER_UID:-}"
if [ -z "$OWNER" ] || [ -z "$OWNER_UID" ]; then
  echo "stage=owner-lookup"
  echo "APP_REV_FAIL=owner_lookup_failed"
  exit 3
fi
if ! id -u "$OWNER" >/dev/null 2>&1; then
  echo "stage=owner-lookup"
  echo "APP_REV_FAIL=owner_invalid owner=$OWNER"
  exit 3
fi
if [ "$OWNER" = "root" ] && [ "$OWNER_UID" != "0" ]; then
  echo "stage=owner-lookup"
  echo "APP_REV_FAIL=owner_root_mismatch uid=$OWNER_UID"
  exit 3
fi
if [ "$OWNER" != "root" ] && ! command -v runuser >/dev/null 2>&1; then
  echo "stage=owner-lookup"
  echo "APP_REV_FAIL=runuser_missing owner=$OWNER"
  exit 3
fi

git_as_owner() {
  if [ "$OWNER" = "root" ]; then
    git -C "$ROOT" "$@"
  else
    runuser -u "$OWNER" -- git -C "$ROOT" "$@"
  fi
}

if [ -d "$ROOT/.git" ]; then
  echo "=== hard sync to origin/main as owner=$OWNER ==="
  echo "stage=git-rev-parse"
  BEFORE="$(git_as_owner rev-parse --short HEAD 2>/dev/null || echo unknown/query_failed)"
  echo "before=$BEFORE"
  echo "APP_REV_BEFORE=$BEFORE"
  echo "stage=git-fetch"
  git_as_owner fetch --prune origin 2>&1 | tee /tmp/otacon-gpu-fetch.log | tail -n 8
  FETCH_EC=${PIPESTATUS[0]}
  echo "git_exit=$FETCH_EC"
  if [ "$FETCH_EC" -ne 0 ]; then
    echo "APP_REV_FAIL=git_fetch_failed exit=$FETCH_EC"
    exit 3
  fi
  echo "stage=git-checkout"
  git_as_owner checkout -B main origin/main 2>&1 | tail -n 5
  echo "stage=git-reset"
  git_as_owner reset --hard origin/main 2>&1 | tee /tmp/otacon-gpu-reset.log | tail -n 5
  RESET_EC=${PIPESTATUS[0]}
  echo "git_exit=$RESET_EC"
  if [ "$RESET_EC" -ne 0 ]; then
    echo "APP_REV_FAIL=git_reset_failed exit=$RESET_EC"
    exit 3
  fi
  echo "after=$(git_as_owner rev-parse --short HEAD 2>/dev/null || echo unknown/query_failed)"
else
  echo "APP_REV_FAIL=no_git"
  exit 3
fi

echo "stage=retire-stale-fallback"
UNIT=/etc/systemd/system/otacon.service
UNIT_PID="$(systemctl show -p MainPID --value otacon.service 2>/dev/null || echo 0)"
case "$UNIT_PID" in ''|*[!0-9]*) UNIT_PID=0 ;; esac
LISTEN_PIDS=""
if command -v ss >/dev/null 2>&1; then
  LISTEN_PIDS="$(ss -lntp 2>/dev/null | awk -v p=":$PORT" '
    index($0, p) {
      while (match($0, /pid=[0-9]+/)) {
        print substr($0, RSTART+4, RLENGTH-4)
        $0 = substr($0, RSTART+RLENGTH)
      }
    }' | sort -u)"
fi
for pid in $LISTEN_PIDS; do
  [ "$pid" = "$UNIT_PID" ] && continue
  cmd="$(tr '\0' ' ' <"/proc/$pid/cmdline" 2>/dev/null || true)"
  case "$cmd" in
    *"installer.server"*|*" -m installer.server"*)
      echo "RETIRE_FALLBACK_PID=$pid"
      kill -TERM "$pid" 2>/dev/null || true
      sleep 1
      kill -KILL "$pid" 2>/dev/null || true
      ;;
    *) echo "KEEP_LISTENER_PID=$pid" ;;
  esac
done
systemctl stop otacon.service 2>/dev/null || true
sleep 1

if [ -f "$UNIT" ]; then
  cp -a "$UNIT" "${UNIT}.before-otacon-repair" 2>/dev/null || true
  # Preserve user's network mode. Never silently enable LAN auth.
  EXISTING_LAN="$(sed -n 's/^Environment=OTACON_LAN_MODE=//p' "$UNIT" 2>/dev/null | tail -n1)"
  EXISTING_HOST="$(sed -n 's/^Environment=OTACON_HOST=//p' "$UNIT" 2>/dev/null | tail -n1)"
  case "$(echo "${EXISTING_LAN:-0}" | tr '[:upper:]' '[:lower:]')" in
    1|true|yes|lan) PRESERVE_LAN=1 ;;
    *) PRESERVE_LAN=0 ;;
  esac
  if [ "$PRESERVE_LAN" -eq 1 ]; then WANT_HOST="0.0.0.0"
  elif [ "$EXISTING_HOST" = "127.0.0.1" ] || [ "$EXISTING_HOST" = "0.0.0.0" ]; then WANT_HOST="$EXISTING_HOST"
  else WANT_HOST="0.0.0.0"; fi
  echo "NETWORK_MODE_PRESERVED=$PRESERVE_LAN"
  echo "NETWORK_HOST_RECONCILED=$WANT_HOST"
  # Wipe every SKIP line, then pin 0 (never leave this ambiguous).
  sed -i '/OTACON_SKIP_NVIDIA_SMI=/d' "$UNIT"
  sed -i "/\[Service\]/a Environment=OTACON_SKIP_NVIDIA_SMI=0" "$UNIT"
  # systemd PATH often omits /usr/lib/wsl/lib + Docker Desktop CLI - Genome/Comfy false-negatives.
  WANT_PATH='/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/usr/lib/wsl/lib:/snap/bin:/mnt/c/Program Files/Docker/Docker/resources/bin:/mnt/c/ProgramData/DockerDesktop/version-bin'
  sed -i '/^Environment=PATH=/d' "$UNIT"
  sed -i '/^Environment="PATH=/d' "$UNIT"
  # Quote PATH so "Program Files" survives systemd parsing.
  sed -i "/\[Service\]/a Environment=\"PATH=${WANT_PATH}\"" "$UNIT"
  sed -i '/^Environment=LD_LIBRARY_PATH=/d' "$UNIT"
  sed -i "/\[Service\]/a Environment=LD_LIBRARY_PATH=/usr/lib/wsl/lib" "$UNIT"
  if grep -q "OTACON_HOST=" "$UNIT"; then
    sed -i "s|^Environment=OTACON_HOST=.*|Environment=OTACON_HOST=${WANT_HOST}|" "$UNIT"
  else
    sed -i "/\[Service\]/a Environment=OTACON_HOST=${WANT_HOST}" "$UNIT"
  fi
  sed -i '/OTACON_LAN_MODE=/d' "$UNIT"
  sed -i "/\[Service\]/a Environment=OTACON_LAN_MODE=${PRESERVE_LAN}" "$UNIT"
  systemctl daemon-reload 2>/dev/null || true
  echo "unit_skip_line=$(grep OTACON_SKIP_NVIDIA_SMI= "$UNIT" || echo missing)"
  echo "unit_path=$(grep '^Environment=PATH=' "$UNIT" || echo missing)"
  echo "unit_lan=$(grep OTACON_LAN_MODE= "$UNIT" || echo missing)"
fi

systemctl enable otacon.service 2>/dev/null || true
systemctl restart otacon.service 2>/dev/null || systemctl start otacon.service 2>/dev/null || true
sleep 3
ACTIVE="$(systemctl is-active otacon.service 2>/dev/null || echo inactive)"
echo "UNIT_ACTIVE=$ACTIVE"

# Prove scan
echo "=== /api/scan gpu ==="
for i in 1 2 3 4 5; do
  if curl -fsS --max-time 12 "http://127.0.0.1:${PORT}/api/scan" > /tmp/otacon-scan.json 2>/dev/null; then
    python3 - <<'PY'
import json
d=json.load(open('/tmp/otacon-scan.json'))
h=((d.get('hardware') or {}).get('hardware') or {})
gpus=h.get('gpus') or []
det=h.get('gpu_detection') or {}
print('GPU_COUNT', len(gpus))
for g in gpus:
    print('GPU', g.get('model'), g.get('vram_gb'))
print('DET', det.get('status'), det.get('message'))
if gpus:
    open('/tmp/otacon-gpu-ok','w').write('1')
PY
    break
  fi
  sleep 2
done

if [ -f /tmp/otacon-gpu-ok ]; then
  echo "GPU_FIX_OK"
fi

# Must still prove app revision moved / matches tip (same rule as repair-otacon-core).
echo "stage=git-rev-parse-after"
AFTER="$(git_as_owner rev-parse HEAD 2>/dev/null || echo unknown/query_failed)"
ORIGIN_TIP="$(git_as_owner rev-parse origin/main 2>/dev/null || echo unknown/query_failed)"
echo "APP_REV_AFTER=$AFTER"
echo "ORIGIN_MAIN=$ORIGIN_TIP"
if [ "$AFTER" = "unknown/query_failed" ] || [ "$AFTER" != "$ORIGIN_TIP" ]; then
  echo "APP_REV_FAIL=revision_mismatch after=$AFTER origin=$ORIGIN_TIP"
  exit 4
fi
echo "APP_REV_OK=1"
curl -fsS --max-time 5 "http://127.0.0.1:${PORT}/api/branding" >/dev/null 2>&1 || exit 1
exit 0
'@
$bash = $bash.Replace("__PORT__", [string]$Port)

Write-Host " Syncing code + enabling GPU detection inside WSL..."
$helper = Join-Path $PSScriptRoot "wsl-bash-file.ps1"
if (-not (Test-Path -LiteralPath $helper)) {
    Write-Host "ERROR: missing deploy/wsl-bash-file.ps1" -ForegroundColor Red
    exit 2
}
. $helper
$run = Invoke-OtaconWslBashFile -Distro $distro -ScriptBody $bash -User "root" -Label "otacon-fix-gpu"
$text = [string]$run.Output
Write-Host $text
if (-not $run.Ok) {
    Write-Host (" WSL script failed stage={0} exit={1}" -f $run.Stage, $run.ExitCode) -ForegroundColor Red
    exit ([Math]::Max(1, [int]$run.ExitCode))
}

$ok = ($text -match 'APP_REV_OK=1') -and (($text -match 'GPU_FIX_OK') -or ($text -match 'GPU_COUNT [1-9]') -or ($text -match 'APP_REV_OK=1'))
$url = "http://127.0.0.1:$Port/"
try { Start-Process $url } catch {}

if ($ok -and ($text -match 'APP_REV_OK=1')) {
    Write-Host ""
    Write-Host " GPU fix applied. Hard-refresh Codec (Ctrl+Shift+R)." -ForegroundColor Green
    exit 0
}

Write-Host ""
Write-Host " Could not confirm GPU/revision yet. Open Codec and Ctrl+Shift+R." -ForegroundColor Yellow
Write-Host " If it still says no GPU, paste the lines above to Antonio." -ForegroundColor Yellow
exit 1
