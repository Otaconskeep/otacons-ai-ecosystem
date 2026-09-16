# Resolve the OtaconsKeep WSL distro name (stdout) or nothing.
# Never silently mutate / pick the first random Ubuntu* on power-user PCs.
#
# Preference order:
#   1. Explicit -Prefer / state override
#   2. Dedicated Ubuntu-Otacon or OtaconsKeep (if installed)
#   3. Nothing (caller must prompt Reuse / Create / Abort)
#
# -AllowFirstMatch is opt-in for legacy callers / tests only.

[CmdletBinding()]
param(
    [string]$Prefer = "",
    [switch]$AllowFirstMatch,
    [switch]$ListAll
)

$ErrorActionPreference = "Continue"

function Get-WslNames {
    $raw = & wsl.exe -l -q 2>$null
    if (-not $raw) { return @() }
    $clean = @(
        $raw | ForEach-Object { ($_ -replace "`0", "").Trim() } |
            Where-Object { $_ -ne "" }
    )
    $exclude = '(?i)^docker-desktop|^docker-desktop-data|^podman-machine'
    return @($clean | Where-Object { $_ -notmatch $exclude })
}

$names = Get-WslNames
if ($ListAll) {
    $names | ForEach-Object { Write-Output $_ }
    exit 0
}

$preferred = @(
    'Ubuntu-Otacon',
    'OtaconsKeep'
)
if ($Prefer) { $preferred = @($Prefer) + $preferred }

foreach ($want in $preferred) {
    $hit = $names | Where-Object { $_.Equals($want, [System.StringComparison]::OrdinalIgnoreCase) } | Select-Object -First 1
    if ($hit) {
        Write-Output $hit
        exit 0
    }
}

if ($AllowFirstMatch) {
    $match = $names | Where-Object { $_ -match '(?i)^Ubuntu' } | Select-Object -First 1
    if (-not $match) {
        $match = $names | Where-Object { $_ -match '(?i)Ubuntu' } | Select-Object -First 1
    }
    if ($match) {
        Write-Output $match
        exit 0
    }
}

# No dedicated distro and no silent first-match — caller must decide.
exit 0
