# Wakes the Otacon WSL environment and waits for it to answer, silently.
# No windows, no browser launch -- this only runs from a logon scheduled
# task so Otacon is already warm by the time someone opens it manually.
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
        $resp = Invoke-WebRequest -Uri "http://localhost:$Port/" -TimeoutSec 2 -UseBasicParsing -ErrorAction Stop
        return ($resp.StatusCode -ge 200 -and $resp.StatusCode -lt 500)
    } catch {
        return $false
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
    Write-Log "Not up after $TimeoutSeconds s, explicitly starting the systemd service"
    try {
        & wsl.exe -d $DistroName -u root -- systemctl start otacon 2>$null | Out-Null
    } catch {
        Write-Log "systemctl start failed: $_"
    }

    $deadline2 = (Get-Date).AddSeconds(15)
    while ((Get-Date) -lt $deadline2) {
        if (Test-Otacon) { $up = $true; break }
        Start-Sleep -Seconds 2
    }
}

Write-Log "Result: up=$up"
