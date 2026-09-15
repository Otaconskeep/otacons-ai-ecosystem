# Write the last N lines of a log file to an output path (Windows helper).
# Keeps parentheses out of BAT IF (...) blocks.

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$LogFile,
    [Parameter(Mandatory = $true)][string]$OutFile,
    [int]$Tail = 12
)

$ErrorActionPreference = "Stop"
if (-not (Test-Path -LiteralPath $LogFile)) { exit 0 }
$dir = Split-Path -Parent $OutFile
if ($dir) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
Get-Content -LiteralPath $LogFile -Tail $Tail | Set-Content -LiteralPath $OutFile -Encoding ASCII
exit 0
