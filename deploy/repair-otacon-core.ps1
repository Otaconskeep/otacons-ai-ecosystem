# Fix false "No GPU detected" and other Linux-side drift by hard-syncing
# the WSL Otacon application to the Windows installer target revision.
#
# Success requires PROOF that the Linux app revision matches target.
# Branding-only / restart-only recovery is NOT success.
#
# Usage:
#   powershell -File deploy\repair-otacon-core.ps1 -OpenBrowser -Codec
# Or via OtaconsKeep-Setup.bat --fix-codec / READY soft-refresh.

[CmdletBinding()]
param(
    [string]$DistroName = "",
    [int]$Port = 5757,
    [switch]$OpenBrowser,
    [switch]$Codec,
    [int]$TimeoutSeconds = 90,
    [string]$TargetRevision = ""
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
    try { & wsl.exe -d $Name --exec /bin/true 2>$null | Out-Null } catch {}
    Start-Sleep -Seconds 1
    try {
        & wsl.exe -d $Name --exec /bin/true 2>$null | Out-Null
        return ($LASTEXITCODE -eq 0)
    } catch { return $false }
}

function Resolve-TargetRevision {
    param([string]$Explicit)
    if ($Explicit -and $Explicit.Trim().Length -ge 7) { return $Explicit.Trim() }
    $candidates = @(
        (Join-Path $PSScriptRoot "installer-revision.txt"),
        (Join-Path (Split-Path -Parent $PSScriptRoot) "deploy\installer-revision.txt"),
        (Join-Path $KeepDir "installer\deploy\installer-revision.txt")
    )
    foreach ($p in $candidates) {
        if (Test-Path -LiteralPath $p) {
            $line = (Get-Content -LiteralPath $p -TotalCount 1 -ErrorAction SilentlyContinue)
            if ($line -and $line.Trim().Length -ge 7) {
                Write-RepairLog "target revision from $p = $($line.Trim())"
                return $line.Trim()
            }
        }
    }
    Write-RepairLog "WARN: no installer-revision.txt; will require match to origin/main tip"
    return ""
}

function Invoke-WslAppUpdate {
    param(
        [string]$Name,
        [int]$PortNum,
        [string]$TargetRev
    )
    $bash = @'
set +e
PORT="__PORT__"
TARGET="__TARGET__"
echo "=== repair-otacon-core begin ==="
echo "APP_REV_TARGET=${TARGET:-origin/main}"
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
  echo "APP_REV_FAIL=no_install_tree"
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
# "root" is only valid when the tree is actually uid 0.
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

# Git must run as the repository owner to satisfy ownership checks. Privileged ops stay root.
git_as_owner() {
  if [ "$OWNER" = "root" ]; then
    git -C "$ROOT" "$@"
  else
    runuser -u "$OWNER" -- git -C "$ROOT" "$@"
  fi
}

BEFORE="unknown/query_failed"
if [ -d "$ROOT/.git" ]; then
  echo "stage=git-rev-parse"
  BEFORE="$(git_as_owner rev-parse HEAD 2>/tmp/otacon-git-revparse-before.err)"
  RP_EC=$?
  echo "git_exit=$RP_EC"
  if [ "$RP_EC" -ne 0 ] || [ -z "$BEFORE" ]; then
    BEFORE="unknown/query_failed"
    echo "APP_REV_BEFORE=$BEFORE"
    echo "APP_REV_FAIL=git_revparse_failed exit=$RP_EC"
    tail -n 20 /tmp/otacon-git-revparse-before.err 2>/dev/null || true
    exit 3
  fi
else
  echo "NO_GIT_DIR"
  echo "APP_REV_BEFORE=$BEFORE"
  echo "APP_REV_FAIL=no_git"
  exit 3
fi
echo "APP_REV_BEFORE=$BEFORE"

UPDATE_CMD="git fetch + reset --hard (as $OWNER)"
echo "UPDATE_CMD=$UPDATE_CMD"
echo "=== git hard sync as owner=$OWNER ==="

echo "stage=git-fetch"
git_as_owner fetch --prune origin > /tmp/otacon-git-fetch.log 2>&1
FETCH_EC=$?
echo "git_exit=$FETCH_EC"
echo "FETCH_EXIT=$FETCH_EC"
tail -n 20 /tmp/otacon-git-fetch.log
if [ "$FETCH_EC" -ne 0 ]; then
  echo "APP_REV_FAIL=git_fetch_failed exit=$FETCH_EC"
  exit 3
fi

echo "stage=git-checkout"
git_as_owner checkout -B main origin/main > /tmp/otacon-git-checkout.log 2>&1
CHECKOUT_EC=$?
echo "git_exit=$CHECKOUT_EC"
echo "CHECKOUT_EXIT=$CHECKOUT_EC"
tail -n 10 /tmp/otacon-git-checkout.log
if [ "$CHECKOUT_EC" -ne 0 ]; then
  echo "APP_REV_FAIL=git_checkout_failed exit=$CHECKOUT_EC"
  exit 3
fi

echo "stage=git-reset"
git_as_owner reset --hard origin/main > /tmp/otacon-git-reset.log 2>&1
RESET_EC=$?
echo "git_exit=$RESET_EC"
echo "RESET_EXIT=$RESET_EC"
tail -n 10 /tmp/otacon-git-reset.log
if [ "$RESET_EC" -ne 0 ]; then
  echo "APP_REV_FAIL=git_reset_failed exit=$RESET_EC"
  exit 3
fi

echo "stage=git-rev-parse-after"
AFTER="$(git_as_owner rev-parse HEAD 2>/tmp/otacon-git-revparse-after.err)"
AFTER_EC=$?
echo "git_exit=$AFTER_EC"
if [ "$AFTER_EC" -ne 0 ] || [ -z "$AFTER" ]; then
  AFTER="unknown/query_failed"
fi
ORIGIN_TIP="$(git_as_owner rev-parse origin/main 2>/dev/null || echo unknown/query_failed)"
echo "APP_REV_AFTER=$AFTER"
echo "ORIGIN_MAIN=$ORIGIN_TIP"

# Revision gate: tip must equal origin/main after hard sync.
# installer-revision.txt may name the parent content commit (bump commit is tip),
# so accept: after==origin/main AND (no target | after has target as ancestor | prefix match).
REV_OK=0
if [ "$AFTER" != "unknown/query_failed" ] && [ "$AFTER" = "$ORIGIN_TIP" ]; then
  REV_OK=1
fi
if [ "$REV_OK" -eq 1 ] && [ -n "$TARGET" ]; then
  AFTER_SHORT="$(echo "$AFTER" | cut -c1-12)"
  TARGET_SHORT="$(echo "$TARGET" | cut -c1-12)"
  if [ "$AFTER" = "$TARGET" ] || [ "$AFTER_SHORT" = "$TARGET_SHORT" ]; then
    echo "TARGET_MATCHES_TIP=1"
  elif git_as_owner merge-base --is-ancestor "$TARGET" "$AFTER" 2>/dev/null; then
    echo "TARGET_INCLUDED_IN_TIP=1"
  else
    echo "APP_REV_FAIL=target_not_in_history target=$TARGET after=$AFTER"
    REV_OK=0
  fi
fi

if [ "$REV_OK" -ne 1 ]; then
  echo "APP_REV_FAIL=revision_mismatch before=$BEFORE target=${TARGET:-none} after=$AFTER origin=$ORIGIN_TIP"
  exit 4
fi
echo "APP_REV_OK=1"
echo "stage=content-proofs"

# Content proofs for known Linux-side fixes
MEM="$ROOT/core/memory.py"
WIZ="$ROOT/ui/wizard.js"
PROOF_MEMORY=0
PROOF_SCAN=0
PROOF_THINK=0
if [ -f "$MEM" ] && grep -q "def connection(self)" "$MEM" && ! grep -q "check_same_thread=False" "$MEM"; then PROOF_MEMORY=1; fi
if [ -f "$WIZ" ] && ! grep -q "repair: never block Codec on GPU scan" "$WIZ"; then PROOF_SCAN=1; fi
if [ -f "$WIZ" ] && grep -q "setCodecMode('thinking')" "$WIZ" && grep -q "}finally{" "$WIZ"; then PROOF_THINK=1; fi
PROOF_LAN_UI=0
if [ -f "$WIZ" ] && grep -q "LAN_AUTH_REQUIRED" "$WIZ" && grep -q "Authorization" "$WIZ" && grep -q "otacon_lan_token" "$WIZ"; then PROOF_LAN_UI=1; fi
PROOF_AUTH_BOOT=0
if [ -f "$WIZ" ] && grep -q "/api/auth/bootstrap" "$WIZ" && grep -q "sessionStorage" "$WIZ"; then PROOF_AUTH_BOOT=1; fi
echo "PROOF_MEMORY_CONNECTION=$PROOF_MEMORY"
echo "PROOF_NO_SCAN_NULL_PATCH=$PROOF_SCAN"
echo "PROOF_THINKING_FINALLY=$PROOF_THINK"
echo "PROOF_LAN_AUTH_UI=$PROOF_LAN_UI"
echo "PROOF_AUTH_BOOTSTRAP=$PROOF_AUTH_BOOT"
if [ "$PROOF_MEMORY" -ne 1 ] || [ "$PROOF_SCAN" -ne 1 ] || [ "$PROOF_THINK" -ne 1 ] || [ "$PROOF_LAN_UI" -ne 1 ] || [ "$PROOF_AUTH_BOOT" -ne 1 ]; then
  echo "APP_REV_FAIL=content_proofs memory=$PROOF_MEMORY scan=$PROOF_SCAN think=$PROOF_THINK lan_ui=$PROOF_LAN_UI auth_boot=$PROOF_AUTH_BOOT"
  exit 5
fi
echo "CONTENT_PROOFS_OK=1"

echo "stage=retire-stale-fallback"
UNIT=/etc/systemd/system/otacon.service
PRESERVE_LAN=0
WANT_HOST="127.0.0.1"

# Managed MainPID (0 if inactive/missing). Never kill this as a "fallback".
UNIT_PID="$(systemctl show -p MainPID --value otacon.service 2>/dev/null || echo 0)"
case "$UNIT_PID" in ''|*[!0-9]*) UNIT_PID=0 ;; esac
echo "UNIT_MAINPID=$UNIT_PID"

# Collect PIDs listening on PORT (ss preferred).
LISTEN_PIDS=""
if command -v ss >/dev/null 2>&1; then
  LISTEN_PIDS="$(ss -lntp 2>/dev/null | awk -v p=":$PORT" '
    index($0, p) {
      while (match($0, /pid=[0-9]+/)) {
        print substr($0, RSTART+4, RLENGTH-4)
        $0 = substr($0, RSTART+RLENGTH)
      }
    }' | sort -u)"
elif command -v lsof >/dev/null 2>&1; then
  LISTEN_PIDS="$(lsof -iTCP:$PORT -sTCP:LISTEN -t 2>/dev/null | sort -u)"
fi
echo "LISTEN_PIDS=${LISTEN_PIDS:-none}"

is_otacon_fallback_proc() {
  # True only for installer-owned nohup/fallback Otacon servers - not foreign apps.
  local pid="$1" cmd=""
  [ -n "$pid" ] && [ "$pid" -gt 1 ] 2>/dev/null || return 1
  [ "$pid" = "$UNIT_PID" ] && return 1
  cmd="$(tr '\0' ' ' <"/proc/$pid/cmdline" 2>/dev/null || true)"
  case "$cmd" in
    *"installer.server"*|*" -m installer.server"*|*"python"*"installer/server"*) ;;
    *) return 1 ;;
  esac
  # Prefer evidence of Otacon ownership: cwd under an otacon tree, or tracked wizard.pid.
  local cwd=""
  cwd="$(readlink -f "/proc/$pid/cwd" 2>/dev/null || true)"
  case "$cwd" in
    *otacon-ai-ecosystem*|*otacons-ai-ecosystem*|*OtaconsKeep*) return 0 ;;
  esac
  if [ -f /tmp/otacon-wizard.pid ] && [ "$(cat /tmp/otacon-wizard.pid 2>/dev/null)" = "$pid" ]; then
    return 0
  fi
  local home owner_home
  while IFS=: read -r _u _x _uid _gid _gecos home _; do
    case "$home" in ""|"/"|"/nonexistent") continue ;; esac
    if [ -f "$home/.config/otacon/wizard.pid" ] && [ "$(cat "$home/.config/otacon/wizard.pid" 2>/dev/null)" = "$pid" ]; then
      return 0
    fi
  done <<EOF
$(getent passwd)
EOF
  # cmdline alone is enough when it is clearly installer.server (not a random python app).
  return 0
}

RETIRED=0
for pid in $LISTEN_PIDS; do
  if is_otacon_fallback_proc "$pid"; then
    echo "RETIRE_FALLBACK_PID=$pid"
    kill -TERM "$pid" 2>/dev/null || true
    sleep 1
    if kill -0 "$pid" 2>/dev/null; then
      kill -KILL "$pid" 2>/dev/null || true
    fi
    RETIRED=$((RETIRED + 1))
  else
    echo "KEEP_LISTENER_PID=$pid (not an Otacon fallback)"
  fi
done
echo "FALLBACK_RETIRED=$RETIRED"

# Stop managed unit cleanly before rewriting the unit file.
systemctl stop otacon.service 2>/dev/null || true
sleep 1

# Re-check port: refuse to proceed if a non-Otacon foreign process still owns it.
FOREIGN=0
if command -v ss >/dev/null 2>&1; then
  for pid in $(ss -lntp 2>/dev/null | awk -v p=":$PORT" '
    index($0, p) {
      while (match($0, /pid=[0-9]+/)) {
        print substr($0, RSTART+4, RLENGTH-4)
        $0 = substr($0, RSTART+RLENGTH)
      }
    }' | sort -u); do
    if ! is_otacon_fallback_proc "$pid"; then
      # Still listening and not our fallback: foreign or lingering managed.
      UNIT_PID2="$(systemctl show -p MainPID --value otacon.service 2>/dev/null || echo 0)"
      if [ "$pid" != "$UNIT_PID2" ] && [ "$pid" != "0" ]; then
        cmd2="$(tr '\0' ' ' <"/proc/$pid/cmdline" 2>/dev/null || true)"
        case "$cmd2" in
          *"installer.server"*) kill -TERM "$pid" 2>/dev/null || true ;;
          *) echo "FOREIGN_LISTENER_PID=$pid cmd=$cmd2"; FOREIGN=1 ;;
        esac
      fi
    fi
  done
fi
if [ "$FOREIGN" -eq 1 ]; then
  echo "APP_REV_FAIL=port_occupied_by_foreign_process"
  exit 6
fi

echo "stage=reconcile-unit"
if [ -f "$UNIT" ]; then
  # Safe backup before any mutation (idempotent timestamped + stable alias).
  cp -a "$UNIT" "${UNIT}.before-otacon-repair" 2>/dev/null || true
  cp -a "$UNIT" "${UNIT}.before-otacon-repair.$(date +%Y%m%d%H%M%S)" 2>/dev/null || true
  echo "UNIT_BACKUP=${UNIT}.before-otacon-repair"

  EXISTING_LAN="$(sed -n 's/^Environment=OTACON_LAN_MODE=//p' "$UNIT" 2>/dev/null | tail -n1)"
  EXISTING_HOST="$(sed -n 's/^Environment=OTACON_HOST=//p' "$UNIT" 2>/dev/null | tail -n1)"
  case "$(echo "${EXISTING_LAN:-0}" | tr '[:upper:]' '[:lower:]')" in
    1|true|yes|lan) PRESERVE_LAN=1 ;;
    *) PRESERVE_LAN=0 ;;
  esac
  # Coherent network mode: never force LAN; never leave HOST vs LAN_MODE contradictory.
  if [ "$PRESERVE_LAN" -eq 1 ]; then
    WANT_HOST="0.0.0.0"
  else
    case "$(echo "${EXISTING_HOST:-}" | tr '[:upper:]' '[:lower:]')" in
      127.0.0.1|localhost|::1) WANT_HOST="127.0.0.1" ;;
      0.0.0.0) WANT_HOST="0.0.0.0" ;;
      *)
        if grep -qi microsoft /proc/version 2>/dev/null; then WANT_HOST="0.0.0.0"; else WANT_HOST="127.0.0.1"; fi
        ;;
    esac
  fi
  echo "NETWORK_MODE_BEFORE=lan=${EXISTING_LAN:-unset};host=${EXISTING_HOST:-unset}"
  echo "NETWORK_MODE_PRESERVED=$PRESERVE_LAN"
  echo "NETWORK_HOST_RECONCILED=$WANT_HOST"

  sed -i '/OTACON_SKIP_NVIDIA_SMI=/d' "$UNIT"
  sed -i "/\[Service\]/a Environment=OTACON_SKIP_NVIDIA_SMI=0" "$UNIT"
  if grep -q "OTACON_HOST=" "$UNIT"; then
    sed -i "s|^Environment=OTACON_HOST=.*|Environment=OTACON_HOST=${WANT_HOST}|" "$UNIT"
  else
    sed -i "/\[Service\]/a Environment=OTACON_HOST=${WANT_HOST}" "$UNIT"
  fi
  sed -i '/OTACON_LAN_MODE=/d' "$UNIT"
  sed -i "/\[Service\]/a Environment=OTACON_LAN_MODE=${PRESERVE_LAN}" "$UNIT"
  if grep -q "OTACON_PORT=" "$UNIT"; then
    sed -i "s|^Environment=OTACON_PORT=.*|Environment=OTACON_PORT=${PORT}|" "$UNIT"
  else
    sed -i "/\[Service\]/a Environment=OTACON_PORT=${PORT}" "$UNIT"
  fi
  echo "unit_skip=$(grep OTACON_SKIP_NVIDIA_SMI= "$UNIT" || echo missing)"
  echo "unit_lan=$(grep OTACON_LAN_MODE= "$UNIT" || echo missing)"
  echo "unit_host=$(grep OTACON_HOST= "$UNIT" || echo missing)"
fi

echo "stage=systemd-restart"
systemctl daemon-reload 2>/dev/null || true
systemctl enable otacon.service 2>/dev/null || true
systemctl enable otacon-tts.service 2>/dev/null || true
systemctl restart otacon-tts.service 2>/dev/null || systemctl start otacon-tts.service 2>/dev/null || true
systemctl restart otacon.service 2>/dev/null || systemctl start otacon.service 2>/dev/null || true
sleep 2

ACTIVE="$(systemctl is-active otacon.service 2>/dev/null || echo inactive)"
ENABLED="$(systemctl is-enabled otacon.service 2>/dev/null || echo disabled)"
echo "UNIT_ACTIVE=$ACTIVE"
echo "UNIT_ENABLED=$ENABLED"
if [ "$ACTIVE" != "active" ]; then
  echo "APP_REV_FAIL=otacon_service_not_active state=$ACTIVE"
  systemctl status otacon.service --no-pager -l 2>/dev/null | head -n 40 || true
  exit 7
fi
case "$ENABLED" in
  enabled|enabled-runtime|static) echo "UNIT_ENABLED_OK=1" ;;
  *)
    echo "APP_REV_FAIL=otacon_service_not_enabled state=$ENABLED"
    exit 7
    ;;
esac

echo "stage=e2e-health"
E2E_OK=1
brand="$(curl -fsS --max-time 8 "http://127.0.0.1:${PORT}/api/branding" 2>/dev/null || true)"
echo "=== branding ==="
echo "$brand"
case "$brand" in
  *'"product_name": "Otacon"'*|*"\"product_name\":\"Otacon\""*) echo "BRANDING_OK=1" ;;
  *) echo "BRANDING_FAIL"; E2E_OK=0 ;;
esac

scan="$(curl -fsS --max-time 20 "http://127.0.0.1:${PORT}/api/scan" 2>/dev/null || true)"
echo "=== scan (gpu) ==="
printf '%s' "$scan" > /tmp/otacon-repair-scan.json
python3 - <<'PY'
import json
try:
    d=json.load(open("/tmp/otacon-repair-scan.json"))
except Exception as e:
    print("SCAN_PARSE_FAIL", e)
    open("/tmp/otacon-repair-scan-ok","w").write("0")
    raise SystemExit(0)
h=((d.get("hardware") or {}).get("hardware") or d.get("hardware") or {})
gpus=h.get("gpus") or []
print("GPU_COUNT", len(gpus))
for g in gpus:
    print("GPU", g.get("model"), g.get("vram_gb"))
det=(h.get("gpu_detection") or {})
print("DET", det.get("status"), det.get("message"))
open("/tmp/otacon-repair-scan-ok","w").write("1" if gpus else "0")
PY
SCAN_OK="$(cat /tmp/otacon-repair-scan-ok 2>/dev/null || echo 0)"
echo "SCAN_OK=$SCAN_OK"
# GPU absence is not an automatic hard fail on CPU-only hosts, but SKIP must not force empty.
if grep -q 'OTACON_SKIP_NVIDIA_SMI=1' "$UNIT" 2>/dev/null; then
  echo "APP_REV_FAIL=gpu_skip_still_enabled"
  E2E_OK=0
fi

caps="$(curl -fsS --max-time 12 "http://127.0.0.1:${PORT}/api/capabilities" 2>/dev/null || true)"
echo "=== capabilities ==="
echo "$caps" | head -c 800; echo
case "$caps" in
  *"\"chat\": \"ready\""*|*"\"chat\":\"ready\""*) echo "CHAT_CAP_OK=1" ;;
  *) echo "CHAT_CAP_WARN"; ;;
esac

# Memory + Aria chat twice (honest probes; not bare HTTP 200).
chat_once() {
  local tag="$1"
  local body='{"agent":{"id":"agent_001","display_name":"Aria","voice_id":"voice_aria"},"message":"ping '"$tag"'","conversation_id":"repair-'"$tag"'","auto_speak":false}'
  local resp
  resp="$(curl -fsS --max-time 120 -X POST "http://127.0.0.1:${PORT}/api/chat_with_agent" \
    -H 'Content-Type: application/json' -d "$body" 2>/dev/null || true)"
  echo "CHAT_${tag}_RAW=${resp}" | head -c 500; echo
  case "$resp" in
    *'"text":'*|*"\"text\":"*)
      if echo "$resp" | grep -q '"error"'; then
        echo "CHAT_${tag}_FAIL=error_payload"
        return 1
      fi
      echo "CHAT_${tag}_OK=1"
      return 0
      ;;
    *)
      echo "CHAT_${tag}_FAIL=no_text"
      return 1
      ;;
  esac
}
if chat_once "1"; then :; else E2E_OK=0; fi
if chat_once "2"; then :; else E2E_OK=0; fi

# Service must still be active after chats.
ACTIVE2="$(systemctl is-active otacon.service 2>/dev/null || echo inactive)"
echo "UNIT_ACTIVE_AFTER_CHAT=$ACTIVE2"
if [ "$ACTIVE2" != "active" ]; then
  echo "APP_REV_FAIL=otacon_inactive_after_chat"
  E2E_OK=0
fi

echo "=== listen ==="
ss -lntp 2>/dev/null | grep ":${PORT}" || netstat -lntp 2>/dev/null | grep ":${PORT}" || echo NOT_LISTENING

if [ "$E2E_OK" -ne 1 ]; then
  echo "E2E_HEALTH_FAIL=1"
  exit 8
fi
echo "E2E_HEALTH_OK=1"
echo "=== done ==="
exit 0
'@
    $bash = $bash.Replace("__PORT__", [string]$PortNum).Replace("__TARGET__", [string]$TargetRev)
    Write-RepairLog "Running Linux app update via temp .sh (not bash -lc)..."
    Write-RepairLog "UPDATE_CMD=wsl --exec bash <temp.sh> (git fetch/reset --hard)"
    $helper = Join-Path $PSScriptRoot "wsl-bash-file.ps1"
    if (-not (Test-Path -LiteralPath $helper)) {
        throw "missing deploy/wsl-bash-file.ps1"
    }
    . $helper
    $run = Invoke-OtaconWslBashFile -Distro $Name -ScriptBody $bash -User "root" -Label "otacon-repair"
    Write-RepairLog ("WSL stage={0} exit={1} win={2} linux={3}" -f $run.Stage, $run.ExitCode, $run.WindowsPath, $run.LinuxPath)
    if ($run.Output) { Write-RepairLog ($run.Output.Trim()) }
    if (-not $run.Ok) {
        Write-RepairLog ("UPDATE FAILED at stage={0} exit={1}" -f $run.Stage, $run.ExitCode)
        # Propagate transport/syntax failure immediately (do not treat as soft missing markers).
        $script:OtaconWslTransportExit = [int]$run.ExitCode
        if ($script:OtaconWslTransportExit -eq 0) { $script:OtaconWslTransportExit = 1 }
        return [string]$run.Output
    }
    # Surface explicit Git stage markers from the Linux script (separate from transport OK).
    if ($run.Output -match 'stage=(git-[^\r\n]+)') {
        Write-RepairLog ("Linux git stage marker: {0}" -f $Matches[1])
    }
    if ($run.Output -match 'APP_REV_FAIL=git_') {
        Write-RepairLog "Linux Git operation failed (see stage=/git_exit= markers above)"
    }
    return [string]$run.Output
}

# --- main ---
Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  OTACON CORE REPAIR / APP UPDATE" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

$distro = Resolve-Distro -Preferred $DistroName
if (-not $distro) {
    Write-RepairLog "ERROR: No Ubuntu/Otacon WSL distro found. Run OtaconsKeep-Setup.bat first."
    exit 2
}
Write-RepairLog "DISTRO=$distro"

$target = Resolve-TargetRevision -Explicit $TargetRevision
Write-RepairLog "APP_REV_TARGET=$target"

if (-not (Ensure-DistroRunning $distro)) {
    Write-RepairLog "WARN: distro may still be starting"
    Start-Sleep -Seconds 3
}

$script:OtaconWslTransportExit = 0
$text = Invoke-WslAppUpdate -Name $distro -PortNum $Port -TargetRev $target
if ([int]$script:OtaconWslTransportExit -ne 0) {
    Write-RepairLog "UPDATE FAILED: WSL bash file transport/syntax (stage exit=$($script:OtaconWslTransportExit))"
    Write-Host ""
    Write-Host "  UPDATE FAILED - WSL Bash transport error (temp .sh / bash -n)." -ForegroundColor Red
    Write-Host "  Log: $LogFile" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "  Press any key to close." -ForegroundColor DarkYellow
    try { [void][Console]::ReadKey($true) } catch { Start-Sleep 3 }
    exit ([int]$script:OtaconWslTransportExit)
}

$revOk = ($text -match 'APP_REV_OK=1')
$contentOk = ($text -match 'CONTENT_PROOFS_OK=1')
$e2eOk = ($text -match 'E2E_HEALTH_OK=1')
$unitActive = ($text -match 'UNIT_ACTIVE=active')
$unitEnabled = ($text -match 'UNIT_ENABLED_OK=1')
if (-not $revOk -or -not $contentOk) {
    Write-RepairLog "UPDATE FAILED: Linux application revision/content proofs not satisfied."
    Write-RepairLog "installer updated != application updated"
    Write-Host ""
    Write-Host "  UPDATE FAILED - Linux Otacon app did not reach the target revision." -ForegroundColor Red
    Write-Host "  Log: $LogFile" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "  Press any key to close." -ForegroundColor DarkYellow
    try { [void][Console]::ReadKey($true) } catch { Start-Sleep 3 }
    exit 4
}
if (-not $unitActive -or -not $unitEnabled) {
    Write-RepairLog "UPDATE FAILED: otacon.service not active+enabled after repair."
    Write-Host ""
    Write-Host "  UPDATE FAILED - systemd unit not healthy." -ForegroundColor Red
    Write-Host "  Log: $LogFile" -ForegroundColor Yellow
    try { [void][Console]::ReadKey($true) } catch { Start-Sleep 3 }
    exit 7
}
if (-not $e2eOk) {
    Write-RepairLog "UPDATE FAILED: end-to-end health probes did not pass (branding/chat)."
    Write-Host ""
    Write-Host "  UPDATE FAILED - Otacon answered incompletely after repair." -ForegroundColor Red
    Write-Host "  Log: $LogFile" -ForegroundColor Yellow
    try { [void][Console]::ReadKey($true) } catch { Start-Sleep 3 }
    exit 8
}

# G. Install durable WSL keepalive (user-scoped Startup + LOCALAPPDATA).
$wakeInstaller = Join-Path $PSScriptRoot "install-wake-task.ps1"
$keepaliveOk = $false
if (Test-Path -LiteralPath $wakeInstaller) {
    try {
        $wakeOut = & powershell -NoProfile -ExecutionPolicy Bypass -File $wakeInstaller -DistroName $distro -Port $Port 2>&1
        Write-RepairLog ("keepalive install: " + (($wakeOut | Out-String).Trim()))
        $keepaliveOk = ($LASTEXITCODE -eq 0)
    } catch {
        Write-RepairLog "keepalive install exception: $($_.Exception.Message)"
        $keepaliveOk = $false
    }
} else {
    Write-RepairLog "WARN: install-wake-task.ps1 missing"
}
$keepScript = Join-Path $KeepDir "keep-ubuntu-awake.ps1"
$startupDir = [Environment]::GetFolderPath("Startup")
$startupVbs = if ($startupDir) { Join-Path $startupDir "OtaconsKeep-KeepAlive.vbs" } else { "" }
if (-not (Test-Path -LiteralPath $keepScript)) {
    Write-RepairLog "WARN: keepalive script missing at $keepScript"
    $keepaliveOk = $false
}
if ($startupVbs -and -not (Test-Path -LiteralPath $startupVbs)) {
    Write-RepairLog "WARN: Startup launcher missing at $startupVbs"
    $keepaliveOk = $false
}
Write-RepairLog "KEEPALIVE_OK=$keepaliveOk script=$keepScript startup=$startupVbs"

# Mark reboot-persistence pending until a later Setup/Open verifies post-sign-in health.
try {
    $statePath = Join-Path $KeepDir "installer-state.json"
    $state = @{}
    if (Test-Path -LiteralPath $statePath) {
        try {
            $obj = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
            foreach ($p in $obj.PSObject.Properties) { $state[$p.Name] = $p.Value }
        } catch {}
    }
    $state["reboot_persistence"] = "pending"
    $state["reboot_persistence_note"] = "Verify after next Windows sign-in: keepalive + otacon.service + Aria chat"
    $state["updated_at"] = (Get-Date).ToUniversalTime().ToString("o")
    ($state | ConvertTo-Json -Depth 6) | Set-Content -LiteralPath $statePath -Encoding UTF8
    Write-RepairLog "reboot_persistence=pending (clear after post-sign-in health)"
} catch {
    Write-RepairLog "WARN: could not persist reboot_persistence state: $($_.Exception.Message)"
}

$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
$base = $null
while ((Get-Date) -lt $deadline) {
    $base = Find-WorkingBase -Name $distro -PortNum $Port
    if ($base) { break }
    Start-Sleep -Seconds 2
}

if (-not $base) {
    Write-RepairLog "FAILED: revision+E2E OK markers but Otacon not answering HTTP from Windows."
    Write-RepairLog "Log: $LogFile"
    Write-Host ""
    Write-Host "  Press any key to close." -ForegroundColor DarkYellow
    try { [void][Console]::ReadKey($true) } catch { Start-Sleep 3 }
    exit 1
}

$openUrl = if ($Codec -or $OpenBrowser) { "$base/?codec=1" } else { "$base/" }
Write-RepairLog "OK base=$base revision+e2e+systemd proof passed keepalive=$keepaliveOk"
Write-Host ""
Write-Host "  Otacon app updated and verified." -ForegroundColor Green
Write-Host "  $base" -ForegroundColor Green
if (-not $keepaliveOk) {
    Write-Host "  WARN: WSL keepalive not fully installed - chat may pause when WSL idles." -ForegroundColor Yellow
}
Write-Host "  Reboot persistence: pending (will verify after next Windows sign-in)." -ForegroundColor DarkYellow
Write-Host ""

if ($OpenBrowser -or $Codec) {
    try { Start-Process $openUrl } catch { Write-RepairLog "Start-Process failed: $_" }
}

try {
    $urlFile = Join-Path $KeepDir "last-otacon-url.txt"
    Set-Content -LiteralPath $urlFile -Value $base -Encoding ASCII
} catch {}

exit 0
