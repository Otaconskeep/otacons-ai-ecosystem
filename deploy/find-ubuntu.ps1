# Prints the name of an installed Ubuntu-family WSL distro, or nothing.
# Prefers Ubuntu*; skips Docker Desktop utility distros and non-Ubuntu defaults.
$raw = & wsl.exe -l -q 2>$null
$clean = $raw | ForEach-Object { $_ -replace "`0", "" } | Where-Object { $_.Trim() -ne "" }
$exclude = { $_ -match "(?i)docker-desktop|docker-desktop-data|podman-machine" }
$match = $clean | Where-Object { $_ -match "(?i)^Ubuntu" -and -not (& $exclude) } | Select-Object -First 1
if (-not $match) {
  $match = $clean | Where-Object { $_ -match "(?i)Ubuntu" -and -not (& $exclude) } | Select-Object -First 1
}
if ($match) { Write-Output $match.Trim() }
