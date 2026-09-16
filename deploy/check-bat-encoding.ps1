# Validate a .bat file is UTF-8 with BOM and CRLF line endings.
# Invoked ONLY via: powershell -File check-bat-encoding.ps1 -Path <bat>
# Never pass the bat path after -Command — Windows PowerShell appends those
# tokens into the command text (breaks on "OtaconsKeep-Setup (1).bat").

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Path
)

$ErrorActionPreference = "Stop"

if (-not $Path) {
    Write-Host "ERROR: no path provided."
    exit 2
}
if (-not (Test-Path -LiteralPath $Path)) {
    Write-Host "ERROR: installer file not found: $Path"
    exit 2
}

$b = [System.IO.File]::ReadAllBytes($Path)
if ($b.Length -lt 8) {
    Write-Host "ERROR: installer file is empty or truncated."
    exit 2
}
if ($b[0] -eq 0xFF -and $b[1] -eq 0xFE) {
    Write-Host "ERROR: this installer was saved as UTF-16. Re-download from the Otaconskeep website."
    exit 3
}
if ($b[0] -eq 0xFE -and $b[1] -eq 0xFF) {
    Write-Host "ERROR: this installer was saved as UTF-16. Re-download from the Otaconskeep website."
    exit 3
}
if (-not ($b[0] -eq 0xEF -and $b[1] -eq 0xBB -and $b[2] -eq 0xBF)) {
    Write-Host "ERROR: missing UTF-8 BOM. Do not save raw GitHub source manually. Re-download OtaconsKeep-Setup.bat from the Otaconskeep website."
    exit 4
}

# Reject bare LF (Unix) or mixed endings — CMD.exe and some download paths break.
$bareLf = 0
for ($i = 0; $i -lt $b.Length; $i++) {
    if ($b[$i] -eq 0x0A) {
        if ($i -eq 0 -or $b[$i - 1] -ne 0x0D) { $bareLf++ }
    }
}
if ($bareLf -gt 0) {
    Write-Host "ERROR: installer has Unix line endings (bare LF). Re-download OtaconsKeep-Setup.bat from the Otaconskeep website (do not Save-As from raw GitHub)."
    exit 5
}

exit 0
