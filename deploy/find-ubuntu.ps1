# Prints the name of an installed Ubuntu-family WSL distro, or nothing.
# wsl.exe writes UTF-16LE with embedded nulls when redirected; strip them
# before matching, otherwise every comparison silently fails.
$raw = & wsl.exe -l -q 2>$null
$clean = $raw | ForEach-Object { $_ -replace "`0", "" } | Where-Object { $_.Trim() -ne "" }
$match = $clean | Where-Object { $_ -match "Ubuntu" } | Select-Object -First 1
if ($match) { Write-Output $match.Trim() }
