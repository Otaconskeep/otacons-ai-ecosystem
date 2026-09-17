# Download a single raw GitHub file to a destination path (Windows helper).
# Avoids embedding parentheses-heavy PowerShell inside BAT IF (...) blocks.

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Url,
    [Parameter(Mandatory = $true)][string]$OutFile,
    [string]$LogFile = ""
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

try {
    [Net.ServicePointManager]::SecurityProtocol = `
        [Net.SecurityProtocolType]::Tls12 -bor `
        [Net.SecurityProtocolType]::Tls11 -bor `
        [Net.SecurityProtocolType]::Tls
} catch {}

function Write-Log([string]$Message) {
    if (-not $LogFile) { return }
    $ts = Get-Date -Format "yyyy-MM-ddTHH:mm:ss.fffK"
    try { Add-Content -Path $LogFile -Value "[$ts] [FETCH] $Message" -Encoding UTF8 } catch {}
}

$dir = Split-Path -Parent $OutFile
if ($dir) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }

$tmp = "$OutFile.otacon-download"
if (Test-Path -LiteralPath $tmp) { Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue }

Write-Log "GET $Url -> $OutFile"
try {
    Invoke-WebRequest -Uri $Url -OutFile $tmp -UseBasicParsing -TimeoutSec 120
    if (-not (Test-Path -LiteralPath $tmp) -or ((Get-Item -LiteralPath $tmp).Length -lt 40)) {
        throw "downloaded file missing or too small"
    }
    Move-Item -LiteralPath $tmp -Destination $OutFile -Force
    Write-Log "OK bytes=$((Get-Item -LiteralPath $OutFile).Length)"
    exit 0
} catch {
    Write-Log "ERROR $($_.Exception.Message)"
    Write-Host $_.Exception.Message
    if (Test-Path -LiteralPath $tmp) { Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue }
    exit 1
}
