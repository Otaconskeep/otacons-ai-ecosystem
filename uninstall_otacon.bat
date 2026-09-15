@echo off
REM Disables Otacon auto-start only (Windows logon task + systemd unit).
REM Does NOT remove binaries, the Otacon install directory, venv, or data.
REM Full uninstall is manual - see the messages at the end (and README).
setlocal enabledelayedexpansion
title Otacon Uninstaller (auto-start only - not a full uninstall)
REM --- encoding / integrity self-check (must stay ASCII) ---
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$b=[System.IO.File]::ReadAllBytes($args[0]);" ^
  "if($b.Length -lt 8){ Write-Host 'ERROR: installer file is empty or truncated.'; exit 2 };" ^
  "if($b[0] -eq 0xFF -and $b[1] -eq 0xFE){ Write-Host 'ERROR: this installer was saved as UTF-16. Re-download from the Otaconskeep website.'; exit 3 };" ^
  "if($b[0] -eq 0xFE -and $b[1] -eq 0xFF){ Write-Host 'ERROR: this installer was saved as UTF-16. Re-download from the Otaconskeep website.'; exit 3 };" ^
  "if(-not ($b[0] -eq 0xEF -and $b[1] -eq 0xBB -and $b[2] -eq 0xBF)){ Write-Host 'ERROR: missing UTF-8 BOM. Do not save raw GitHub source manually. Re-download OtaconsKeep-Setup.bat from the Otaconskeep website.'; exit 4 };" ^
  "exit 0" ^
  "%~f0"
if errorlevel 1 (
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
)

set "SCRIPT_DIR=%~dp0"
set "FIND_UBUNTU_PS1=%SCRIPT_DIR%deploy\find-ubuntu.ps1"

echo ============================================================
echo  OTACONSKEEP // REMOVE OTACON AUTO-START ONLY
echo ============================================================
echo This removes:
echo   - the Windows logon task that wakes Otacon
echo   - the otacon.service systemd unit inside WSL
echo.
echo This does NOT remove binaries, your Ubuntu/WSL environment,
echo your Otacon install folder, your venv, or any of your data.
echo Full uninstall is a separate manual step (shown at the end).
echo.

echo Removing the Windows logon task...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Unregister-ScheduledTask -TaskName 'OtaconAutoStart' -Confirm:$false -ErrorAction SilentlyContinue"
if exist "%LOCALAPPDATA%\Otacon" rd /s /q "%LOCALAPPDATA%\Otacon" >nul 2>&1
echo Done.

set "UBUNTU_NAME="
for /f "delims=" %%D in ('powershell -NoProfile -ExecutionPolicy Bypass -File "%FIND_UBUNTU_PS1%"') do set "UBUNTU_NAME=%%D"

if defined UBUNTU_NAME (
    echo.
    echo Removing the otacon.service systemd unit inside %UBUNTU_NAME%...
    wsl.exe -d "%UBUNTU_NAME%" -u root -- bash -lc "systemctl disable --now otacon.service >/dev/null 2>&1; rm -f /etc/systemd/system/otacon.service; systemctl daemon-reload; echo removed"
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
echo     systemctl disable --now otacon.service
echo     sudo rm -f /etc/systemd/system/otacon.service
echo     sudo systemctl daemon-reload
echo     rm -rf ~/otacon-ai-ecosystem ~/.config/otacon ~/.local/share/otacon
echo     rm -f ~/.local/bin/otacon
echo.
pause
