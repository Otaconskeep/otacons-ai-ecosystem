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

$bash = @'
set +e
PORT="__PORT__"
echo "=== fix-otacon-gpu begin ==="
ROOT="$(ls -d /home/*/otacon-ai-ecosystem 2>/dev/null | head -n1)"
if [ -z "$ROOT" ] && [ -d /root/otacon-ai-ecosystem ]; then ROOT=/root/otacon-ai-ecosystem; fi
echo "ROOT=$ROOT"
if [ -z "$ROOT" ] || [ ! -d "$ROOT" ]; then
  echo "NO_INSTALL_TREE"
  exit 2
fi

if [ -d "$ROOT/.git" ]; then
  echo "=== hard sync to origin/main ==="
  echo "before=$(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || echo none)"
  git -C "$ROOT" fetch --prune origin 2>&1 | tail -n 8
  git -C "$ROOT" checkout -B main origin/main 2>&1 | tail -n 5
  git -C "$ROOT" reset --hard origin/main 2>&1 | tail -n 5
  echo "after=$(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || echo none)"
fi

UNIT=/etc/systemd/system/otacon.service
systemctl stop otacon.service 2>/dev/null || true
pkill -9 -f "installer.server" 2>/dev/null || true
sleep 1

if [ -f "$UNIT" ]; then
  # Wipe every SKIP line, then pin 0 (never leave this ambiguous).
  sed -i '/OTACON_SKIP_NVIDIA_SMI=/d' "$UNIT"
  sed -i "/\[Service\]/a Environment=OTACON_SKIP_NVIDIA_SMI=0" "$UNIT"
  if grep -q "OTACON_HOST=" "$UNIT"; then
    sed -i "s|^Environment=OTACON_HOST=.*|Environment=OTACON_HOST=0.0.0.0|" "$UNIT"
  else
    sed -i "/\[Service\]/a Environment=OTACON_HOST=0.0.0.0" "$UNIT"
  fi
  systemctl daemon-reload 2>/dev/null || true
  echo "unit_skip_line=$(grep OTACON_SKIP_NVIDIA_SMI= "$UNIT" || echo missing)"
fi

systemctl restart otacon.service 2>/dev/null || systemctl start otacon.service 2>/dev/null || true
sleep 3

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
AFTER="$(git -C "$ROOT" rev-parse HEAD 2>/dev/null || echo none)"
ORIGIN_TIP="$(git -C "$ROOT" rev-parse origin/main 2>/dev/null || echo none)"
echo "APP_REV_AFTER=$AFTER"
echo "ORIGIN_MAIN=$ORIGIN_TIP"
if [ "$AFTER" = "none" ] || [ "$AFTER" != "$ORIGIN_TIP" ]; then
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
