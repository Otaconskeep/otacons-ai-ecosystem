@echo off
REM Removes Otacon's Windows auto-start task and its systemd service.
REM Does NOT touch your WSL/Ubuntu environment, your Otacon install
REM directory, your venv, or any of your data. Safe to run more than once.
setlocal enabledelayedexpansion
title Otacon Uninstaller (Windows startup pieces only)

set "SCRIPT_DIR=%~dp0"
set "FIND_UBUNTU_PS1=%SCRIPT_DIR%deploy\find-ubuntu.ps1"

echo ============================================================
echo  OTACONSKEEP // REMOVE OTACON AUTO-START
echo ============================================================
echo This removes:
echo   - the Windows logon task that wakes Otacon
echo   - the otacon.service systemd unit inside WSL
echo.
echo This does NOT remove your Ubuntu/WSL environment, your Otacon
echo install folder, your venv, or any of your data.
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
echo  DONE
echo ============================================================
echo Otacon will no longer start automatically. Your install, your
echo agents, and your data are untouched. To bring auto-start back,
echo just run install_otacon.bat again.
echo.
pause
