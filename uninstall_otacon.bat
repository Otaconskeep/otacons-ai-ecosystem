@echo off
REM Disables Otacon auto-start only (Windows logon task + systemd unit).
REM Does NOT remove binaries, the Otacon install directory, venv, or data.
REM Full uninstall is manual - see the messages at the end (and README).
setlocal enabledelayedexpansion
title Otacon Uninstaller (auto-start only - not a full uninstall)
REM --- encoding check: NEVER append %~f0 after powershell -Command ---
REM powershell.exe concatenates tokens after -Command into script text.
REM Paths like OtaconsKeep-Setup (1).bat then parse as PowerShell code.
set "OTACON_SETUP_SELF=%~f0"
set "ENC_PS1=%~dp0deploy\check-bat-encoding.ps1"
if exist "%ENC_PS1%" goto ENC_VIA_FILE
goto ENC_VIA_ENV
:ENC_VIA_FILE
powershell -NoProfile -ExecutionPolicy Bypass -File "%ENC_PS1%" -Path "%~f0"
goto ENC_AFTER_CHECK
:ENC_VIA_ENV
powershell -NoProfile -ExecutionPolicy Bypass -Command "& { $p = $env:OTACON_SETUP_SELF; if ([string]::IsNullOrWhiteSpace($p)) { Write-Host 'ERROR: installer path missing'; exit 2 }; if (-not (Test-Path -LiteralPath $p)) { Write-Host 'ERROR: installer file not found'; exit 2 }; $b = [IO.File]::ReadAllBytes($p); if ($b.Length -lt 8) { Write-Host 'ERROR: installer file empty'; exit 2 }; if ($b[0] -eq 255 -and $b[1] -eq 254) { Write-Host 'ERROR: UTF-16 encoding'; exit 3 }; if ($b[0] -eq 254 -and $b[1] -eq 255) { Write-Host 'ERROR: UTF-16 encoding'; exit 3 }; if ($b[0] -eq 239 -and $b[1] -eq 187 -and $b[2] -eq 191) { Write-Host 'ERROR: UTF-8 BOM is not allowed in .bat files (breaks @echo off). Re-download from the Otaconskeep website.'; exit 4 }; exit 0 }"
:ENC_AFTER_CHECK
if errorlevel 1 goto ENC_FAIL
goto ENC_OK
:ENC_FAIL
echo.
echo ============================================================
echo                  OTACON SETUP STOPPED
echo ============================================================
echo.
echo  This installer file is damaged or was saved with the wrong encoding.
echo.
echo  nothing has been damaged on your PC
echo.
echo  What to do
echo  1. Delete this .bat file
echo  2. Open the Otaconskeep website
echo  3. Click Download OtaconsKeep Setup
echo  4. Run the new file from Downloads
echo.
echo  Do NOT open raw.githubusercontent.com and use Save As.
echo.
echo ============================================================
echo  This window will stay open. Press a letter key to exit.
echo ============================================================
pause >nul
exit /b 1
:ENC_OK

set "SCRIPT_DIR=%~dp0"
set "FIND_UBUNTU_PS1=%SCRIPT_DIR%deploy\find-ubuntu.ps1"

echo ============================================================
echo  OTACONSKEEP // REMOVE OTACON AUTO-START ONLY
echo ============================================================
echo This removes:
echo   - the Windows logon task that wakes Otacon
echo   - the otacon.service systemd unit inside WSL
echo   - the otacon-tts.service systemd unit inside WSL
echo.
echo This does NOT remove binaries, your Ubuntu/WSL environment,
echo your Otacon install folder, your venv, or any of your data.
echo Full uninstall is a separate manual step (shown at the end).
echo.

echo Removing the Windows logon task and keepalive...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Unregister-ScheduledTask -TaskName 'OtaconAutoStart' -Confirm:$false -ErrorAction SilentlyContinue"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$s=[Environment]::GetFolderPath('Startup'); if($s){ Remove-Item -LiteralPath (Join-Path $s 'OtaconsKeep-KeepAlive.vbs') -Force -ErrorAction SilentlyContinue }; $k=Join-Path $env:LOCALAPPDATA 'OtaconsKeep'; Remove-Item -LiteralPath (Join-Path $k 'keep-ubuntu-awake.ps1') -Force -ErrorAction SilentlyContinue; Remove-Item -LiteralPath (Join-Path $k 'OtaconsKeep-KeepAlive.vbs') -Force -ErrorAction SilentlyContinue; Remove-Item -LiteralPath (Join-Path $k 'wake-otacon.ps1') -Force -ErrorAction SilentlyContinue"
if exist "%LOCALAPPDATA%\Otacon" rd /s /q "%LOCALAPPDATA%\Otacon" >nul 2>&1
echo Done.

set "UBUNTU_NAME="
for /f "delims=" %%D in ('powershell -NoProfile -ExecutionPolicy Bypass -File "%FIND_UBUNTU_PS1%"') do set "UBUNTU_NAME=%%D"

if defined UBUNTU_NAME (
    echo.
    echo Removing otacon.service and otacon-tts.service inside %UBUNTU_NAME%...
    wsl.exe -d "%UBUNTU_NAME%" -u root -- bash -lc "systemctl disable --now otacon-tts.service >/dev/null 2>&1; systemctl disable --now otacon.service >/dev/null 2>&1; pkill -f 'wyoming-piper.*10200' 2>/dev/null || true; rm -f /etc/systemd/system/otacon-tts.service /etc/systemd/system/otacon.service; systemctl daemon-reload; echo removed"
) else (
    echo.
    echo No Ubuntu environment found -- nothing to remove on the Linux side.
)

echo.
echo ============================================================
echo  DONE - AUTO-START DISABLED
echo ============================================================
echo Otacon will no longer start automatically. Install files and
echo data are untouched. To bring auto-start back, run
echo install_otacon.bat again.
echo.
echo Full uninstall (manual - binaries/data are NOT removed above):
echo   In Ubuntu/WSL:
echo     systemctl disable --now otacon-tts.service otacon.service
echo     sudo rm -f /etc/systemd/system/otacon-tts.service /etc/systemd/system/otacon.service
echo     sudo systemctl daemon-reload
echo     pkill -f 'wyoming-piper' 2>/dev/null || true
echo     rm -rf ~/otacon-ai-ecosystem ~/.config/otacon ~/.local/share/otacon
echo     rm -f ~/.local/bin/otacon
echo.
pause
