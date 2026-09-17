# Otacon Lite - repair chat from Windows PowerShell (no line wrapping).
# Usage: right-click -> Run with PowerShell, OR paste the whole file into PowerShell.
# Does not hardcode Windows or Linux usernames; resolves the install tree via getent homes.
$ErrorActionPreference = "Stop"

function Get-OtaconWslDistro {
    $prefer = @("Ubuntu-Otacon", "OtaconsKeep", "Ubuntu-22.04", "Ubuntu-24.04", "Ubuntu")
    $raw = & wsl.exe -l -q 2>$null
    $names = @()
    if ($raw) {
        $names = @($raw | ForEach-Object {
            ("{0}" -f $_).Replace([char]0, "").Trim()
        } | Where-Object { $_ })
    }
    foreach ($want in $prefer) {
        if ($names -contains $want) { return $want }
    }
    foreach ($n in $names) {
        if ($n -match '(?i)Ubuntu|Otacon') { return $n }
    }
    return ""
}

$Distro = Get-OtaconWslDistro
if (-not $Distro) {
    Write-Host "ERROR: No Ubuntu/Otacon WSL distro found. Run OtaconsKeep-Setup.bat first." -ForegroundColor Red
    exit 2
}

$findRoot = @'
set +e
ROOT=""
while IFS=: read -r _u _x _uid _gid _gecos home _shell; do
  case "$home" in ""|"/"|"/nonexistent") continue ;; esac
  if [ -d "$home/otacon-ai-ecosystem" ]; then ROOT="$home/otacon-ai-ecosystem"; break; fi
done <<EOF
$(getent passwd)
EOF
if [ -z "$ROOT" ] && [ -d /root/otacon-ai-ecosystem ]; then ROOT=/root/otacon-ai-ecosystem; fi
if [ -z "$ROOT" ] || [ ! -d "$ROOT" ]; then
  echo "NO_INSTALL_TREE"
  exit 2
fi
OWNER="$(stat -c '%U' "$ROOT" 2>/dev/null || true)"
echo "ROOT=$ROOT"
echo "OWNER=$OWNER"
'@

Write-Host "Locating Otacon install in WSL ($Distro)..." -ForegroundColor Cyan
$probe = & wsl.exe -d $Distro -u root -- bash -lc $findRoot 2>&1
$probeText = ($probe | Out-String)
if ($probeText -match 'NO_INSTALL_TREE' -or $LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Could not find otacon-ai-ecosystem under any passwd home." -ForegroundColor Red
    Write-Host $probeText
    exit 2
}
$Root = ""
$Owner = ""
if ($probeText -match 'ROOT=(\S+)') { $Root = $Matches[1] }
if ($probeText -match 'OWNER=(\S+)') { $Owner = $Matches[1] }
if (-not $Root -or -not $Owner -or $Owner -eq "root") {
    Write-Host "ERROR: Install tree owner unresolved (root=$Root owner=$Owner)." -ForegroundColor Red
    exit 2
}

Write-Host "Pulling latest Otacon Lite into WSL as $Owner..." -ForegroundColor Cyan
& wsl.exe -d $Distro -u root -- runuser -u $Owner -- git -C $Root pull --ff-only
if ($LASTEXITCODE -ne 0) { throw "git pull failed" }

Write-Host "Pulling Ollama model qwen2.5:7b (this can take a few minutes)..." -ForegroundColor Cyan
& wsl.exe -d $Distro -u $Owner -e ollama pull qwen2.5:7b

Write-Host "Restarting otacon service..." -ForegroundColor Cyan
& wsl.exe -d $Distro -u root -e systemctl restart otacon

Start-Sleep -Seconds 3

Write-Host "Testing chat..." -ForegroundColor Cyan
$body = '{"agent":{"id":"agent_001","display_name":"Aria","voice_id":"voice_aria"},"message":"hi","conversation_id":"repair1"}'
$tmp = Join-Path $env:TEMP "otacon-chat-repair.json"
Set-Content -Path $tmp -Value $body -Encoding Ascii
curl.exe -s -X POST "http://127.0.0.1:5757/api/chat_with_agent" -H "Content-Type: application/json" --data-binary "@$tmp"
Write-Host ""
Write-Host "If you see a JSON field named text, chat is fixed. Then Ctrl+F5 the browser." -ForegroundColor Green
