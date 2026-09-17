# Registers (or re-registers) the "OtaconAutoStart" logon task that wakes
# WSL so Otacon is already running by the time the user opens it. Safe to
# run more than once -- it replaces any existing registration rather than
# duplicating it.
param(
    [Parameter(Mandatory = $true)][string]$DistroName,
    [int]$Port = 5757
)

$ErrorActionPreference = "Stop"

$otaconDir = "$env:LOCALAPPDATA\Otacon"
New-Item -ItemType Directory -Force -Path $otaconDir | Out-Null

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$wakeSrc = Join-Path $scriptRoot "wake-otacon.ps1"
$wakeDst = Join-Path $otaconDir "wake-otacon.ps1"
Copy-Item -Path $wakeSrc -Destination $wakeDst -Force

$vbsPath = Join-Path $otaconDir "wake-otacon.vbs"
$psArgs = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$wakeDst`" -DistroName `"$DistroName`" -Port $Port"
$vbsLine = "CreateObject(""WScript.Shell"").Run ""powershell.exe $($psArgs.Replace('"','""'))"", 0, False"
Set-Content -Path $vbsPath -Value $vbsLine -Encoding ASCII

$taskName = "OtaconAutoStart"
Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue

$action = New-ScheduledTaskAction -Execute "wscript.exe" -Argument "`"$vbsPath`""
$trigger = New-ScheduledTaskTrigger -AtLogOn
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 5)

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Description "Wakes the Otacon WSL environment at logon so Otacon is ready at http://localhost:$Port" | Out-Null

Write-Output "OK"
