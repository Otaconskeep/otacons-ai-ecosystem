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
ROOT="$(ls -d /home/*/otacon-ai-ecosystem 2>/dev/null | head -n1)"
if [ -z "$ROOT" ] && [ -d /root/otacon-ai-ecosystem ]; then ROOT=/root/otacon-ai-ecosystem; fi
echo "ROOT=$ROOT"
if [ -z "$ROOT" ] || [ ! -d "$ROOT" ]; then
  echo "NO_INSTALL_TREE"
  echo "APP_REV_FAIL=no_install_tree"
  exit 2
fi
OWNER="$(stat -c %U "$ROOT" 2>/dev/null || echo root)"
echo "OWNER=$OWNER"

BEFORE="none"
if [ -d "$ROOT/.git" ]; then
  BEFORE="$(git -C "$ROOT" rev-parse HEAD 2>/dev/null || echo none)"
fi
echo "APP_REV_BEFORE=$BEFORE"

UPDATE_CMD="git fetch + reset --hard"
echo "UPDATE_CMD=$UPDATE_CMD"
if [ -d "$ROOT/.git" ]; then
  echo "=== git hard sync ==="
  git -C "$ROOT" fetch --prune origin > /tmp/otacon-git-fetch.log 2>&1
  FETCH_EC=$?
  echo "FETCH_EXIT=$FETCH_EC"
  cat /tmp/otacon-git-fetch.log | tail -n 20
  git -C "$ROOT" checkout -B main origin/main > /tmp/otacon-git-checkout.log 2>&1
  echo "CHECKOUT_EXIT=$?"
  git -C "$ROOT" reset --hard origin/main > /tmp/otacon-git-reset.log 2>&1
  RESET_EC=$?
  echo "RESET_EXIT=$RESET_EC"
  cat /tmp/otacon-git-reset.log | tail -n 10
  if [ "$FETCH_EC" -ne 0 ] || [ "$RESET_EC" -ne 0 ]; then
    echo "APP_REV_FAIL=git_sync_failed fetch=$FETCH_EC reset=$RESET_EC"
    exit 3
  fi
else
  echo "NO_GIT_DIR"
  echo "APP_REV_FAIL=no_git"
  exit 3
fi

AFTER="$(git -C "$ROOT" rev-parse HEAD 2>/dev/null || echo none)"
ORIGIN_TIP="$(git -C "$ROOT" rev-parse origin/main 2>/dev/null || echo none)"
echo "APP_REV_AFTER=$AFTER"
echo "ORIGIN_MAIN=$ORIGIN_TIP"

# Revision gate: tip must equal origin/main after hard sync.
# installer-revision.txt may name the parent content commit (bump commit is tip),
# so accept: after==origin/main AND (no target | after has target as ancestor | prefix match).
REV_OK=0
if [ "$AFTER" != "none" ] && [ "$AFTER" = "$ORIGIN_TIP" ]; then
  REV_OK=1
fi
if [ "$REV_OK" -eq 1 ] && [ -n "$TARGET" ]; then
  AFTER_SHORT="$(echo "$AFTER" | cut -c1-12)"
  TARGET_SHORT="$(echo "$TARGET" | cut -c1-12)"
  if [ "$AFTER" = "$TARGET" ] || [ "$AFTER_SHORT" = "$TARGET_SHORT" ]; then
    echo "TARGET_MATCHES_TIP=1"
  elif git -C "$ROOT" merge-base --is-ancestor "$TARGET" "$AFTER" 2>/dev/null; then
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

# Content proofs for known Linux-side fixes
MEM="$ROOT/core/memory.py"
WIZ="$ROOT/ui/wizard.js"
PROOF_MEMORY=0
PROOF_SCAN=0
PROOF_THINK=0
if [ -f "$MEM" ] && grep -q "def connection(self)" "$MEM" && ! grep -q "check_same_thread=False" "$MEM"; then PROOF_MEMORY=1; fi
if [ -f "$WIZ" ] && ! grep -q "repair: never block Codec on GPU scan" "$WIZ"; then PROOF_SCAN=1; fi
if [ -f "$WIZ" ] && grep -q "setCodecMode('thinking')" "$WIZ" && grep -q "}finally{" "$WIZ"; then PROOF_THINK=1; fi
echo "PROOF_MEMORY_CONNECTION=$PROOF_MEMORY"
echo "PROOF_NO_SCAN_NULL_PATCH=$PROOF_SCAN"
echo "PROOF_THINKING_FINALLY=$PROOF_THINK"
if [ "$PROOF_MEMORY" -ne 1 ] || [ "$PROOF_SCAN" -ne 1 ] || [ "$PROOF_THINK" -ne 1 ]; then
  echo "APP_REV_FAIL=content_proofs memory=$PROOF_MEMORY scan=$PROOF_SCAN think=$PROOF_THINK"
  exit 5
fi
echo "CONTENT_PROOFS_OK=1"

UNIT=/etc/systemd/system/otacon.service
systemctl stop otacon.service 2>/dev/null || true
pkill -9 -f "python -m installer.server" 2>/dev/null || true
pkill -9 -f "installer.server" 2>/dev/null || true
sleep 1

if [ -f "$UNIT" ]; then
  sed -i '/OTACON_SKIP_NVIDIA_SMI=/d' "$UNIT"
  sed -i "/\[Service\]/a Environment=OTACON_SKIP_NVIDIA_SMI=0" "$UNIT"
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
  echo "unit_skip=$(grep OTACON_SKIP_NVIDIA_SMI= "$UNIT" || echo missing)"
fi

systemctl enable otacon.service 2>/dev/null || true
systemctl enable otacon-tts.service 2>/dev/null || true
systemctl restart otacon-tts.service 2>/dev/null || systemctl start otacon-tts.service 2>/dev/null || true
systemctl restart otacon.service 2>/dev/null || systemctl start otacon.service 2>/dev/null || true
sleep 2
systemctl is-active otacon.service 2>/dev/null || echo "unit_not_active"

alive=0
if curl -fsS --max-time 3 "http://127.0.0.1:${PORT}/api/branding" >/dev/null 2>&1; then alive=1; fi
if [ "$alive" -ne 1 ] && [ -x "$ROOT/.venv/bin/python" ]; then
  echo "manual_start"
  mkdir -p "/home/${OWNER}/.config/otacon" /root/.config/otacon 2>/dev/null || true
  LOGF="/home/${OWNER}/.config/otacon/wizard.log"
  if [ "$OWNER" = "root" ]; then LOGF=/root/.config/otacon/wizard.log; fi
  if command -v runuser >/dev/null 2>&1 && [ "$OWNER" != "root" ]; then
    runuser -u "$OWNER" -- env \
      OTACON_HOST=0.0.0.0 OTACON_PORT="$PORT" PYTHONPATH="$ROOT" \
      PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/usr/lib/wsl/lib" \
      LD_LIBRARY_PATH="/usr/lib/wsl/lib" \
      bash -lc "cd \"$ROOT\" && unset OTACON_SKIP_NVIDIA_SMI && nohup \"$ROOT/.venv/bin/python\" -m installer.server >\"$LOGF\" 2>&1 & echo \$! >\"\$HOME/.config/otacon/wizard.pid\""
  else
    cd "$ROOT" || exit 3
    unset OTACON_SKIP_NVIDIA_SMI
    export OTACON_HOST=0.0.0.0 OTACON_PORT="$PORT" PYTHONPATH="$ROOT"
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

$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
$base = $null
while ((Get-Date) -lt $deadline) {
    $base = Find-WorkingBase -Name $distro -PortNum $Port
    if ($base) { break }
    Start-Sleep -Seconds 2
}

if (-not $base) {
    Write-RepairLog "FAILED: revision OK but Otacon not answering HTTP after restart."
    Write-RepairLog "Log: $LogFile"
    Write-Host ""
    Write-Host "  Press any key to close." -ForegroundColor DarkYellow
    try { [void][Console]::ReadKey($true) } catch { Start-Sleep 3 }
    exit 1
}

$openUrl = if ($Codec -or $OpenBrowser) { "$base/?codec=1" } else { "$base/" }
Write-RepairLog "OK base=$base revision proof passed"
Write-Host ""
Write-Host "  Otacon app updated and verified." -ForegroundColor Green
Write-Host "  $base" -ForegroundColor Green
Write-Host ""

if ($OpenBrowser -or $Codec) {
    try { Start-Process $openUrl } catch { Write-RepairLog "Start-Process failed: $_" }
}

try {
    $urlFile = Join-Path $KeepDir "last-otacon-url.txt"
    Set-Content -LiteralPath $urlFile -Value $base -Encoding ASCII
} catch {}

exit 0
