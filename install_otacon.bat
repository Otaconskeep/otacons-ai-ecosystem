@echo off
REM Otacon Core one-click Windows installer (Antonio G. Garcia // Otaconskeep)
REM Double-click this file. It sets up WSL2 + Ubuntu if needed, walks you
REM through the one unavoidable manual step (Windows restart / first-time
REM Ubuntu username), automatically resumes itself after that, then runs
REM the real Linux installer (install_otacon.sh) inside WSL on its own.
setlocal enabledelayedexpansion
title Otacon Installer (Windows)

set "SCRIPT_DIR=%~dp0"
set "FIND_UBUNTU_PS1=%SCRIPT_DIR%deploy\find-ubuntu.ps1"

echo ============================================================
echo  OTACONSKEEP // OTACON CORE -- WINDOWS INSTALLER
echo  Designed by Antonio G. Garcia
echo ============================================================
echo.

set "RESUME_MARKER=%TEMP%\otacon_installer_resumed.flag"
set "RESUMED=0"
if exist "%RESUME_MARKER%" set "RESUMED=1"

call :FIND_UBUNTU
if defined UBUNTU_NAME (
    wsl.exe -d "%UBUNTU_NAME%" -- true >nul 2>&1
    if not errorlevel 1 (
        del "%RESUME_MARKER%" >nul 2>&1
        goto :RUN_INSTALL
    )
    echo Found %UBUNTU_NAME%, but it hasn't finished its one-time setup yet.
    goto :NEED_MANUAL_STEP
)

echo Windows Subsystem for Linux isn't set up yet. Setting it up now.
echo This needs Administrator permission and, on some PCs, one restart.
echo.

net session >nul 2>&1
if errorlevel 1 (
    echo Requesting administrator permission -- click Yes on the popup...
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

wsl.exe --install -d Ubuntu

call :FIND_UBUNTU
if defined UBUNTU_NAME (
    wsl.exe -d "%UBUNTU_NAME%" -- true >nul 2>&1
    if not errorlevel 1 (
        del "%RESUME_MARKER%" >nul 2>&1
        goto :RUN_INSTALL
    )
)

:NEED_MANUAL_STEP
if "%RESUMED%"=="1" (
    REM Already tried an automatic resume once. Don't keep relaunching on
    REM every future login -- just tell the user what's left and stop.
    del "%RESUME_MARKER%" >nul 2>&1
    echo.
    echo ============================================================
    echo  ONE LAST STEP
    echo ============================================================
    echo Open the "Ubuntu" app from your Start menu. The first time it
    echo opens it asks you to create a username and password -- type
    echo anything you want, it only matters inside that Ubuntu environment.
    echo.
    echo Then double-click install_otacon.bat one more time and it will
    echo finish automatically.
    pause
    exit /b
)

REM First time hitting this: arrange to resume automatically at next
REM login (RunOnce fires once, then Windows deletes the entry itself),
REM so the user doesn't have to remember to come back to this file.
echo. > "%RESUME_MARKER%"
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\RunOnce" /v OtaconInstallerResume /t REG_SZ /d "\"%~f0\"" /f >nul

echo.
echo ============================================================
echo  ONE MORE STEP (this is a one-time thing)
echo ============================================================
echo If Windows just told you it needs to restart, do that first.
echo.
echo Either way: look for a new "Ubuntu" app -- it may open by itself,
echo or open it yourself from the Start menu. The first time it opens
echo it will ask you to create a username and password. Type anything
echo you want; this only matters inside that Ubuntu environment, not
echo your Windows login.
echo.
echo Once that's done, this installer will continue automatically the
echo next time you log in to Windows -- you don't need to do anything
echo else. If it doesn't, just double-click install_otacon.bat again.
echo.
pause
exit /b

:RUN_INSTALL
echo.
echo Found a working Ubuntu environment: %UBUNTU_NAME%
echo Starting the Otacon installer inside it...
echo This takes 10-30 minutes the first time and will ask for your
echo Linux password once (that's sudo, for a handful of system packages).
echo It's completely safe to run this file again later; every step
echo skips whatever's already done, and it never resets an existing
echo Ubuntu environment.
echo.
wsl.exe -d "%UBUNTU_NAME%" -- bash -lc "curl -fsSL https://raw.githubusercontent.com/Otaconskeep/otacons-ai-ecosystem/main/install_otacon.sh | bash"

echo.
echo ============================================================
echo  OTACON SHOULD NOW BE RUNNING
echo ============================================================
echo Open this in your regular Windows browser:
echo   http://127.0.0.1:5757
echo.
echo (WSL shares that port with Windows automatically -- no extra
echo  setup needed.)
echo.
pause
exit /b

:FIND_UBUNTU
set "UBUNTU_NAME="
for /f "delims=" %%D in ('powershell -NoProfile -ExecutionPolicy Bypass -File "%FIND_UBUNTU_PS1%"') do set "UBUNTU_NAME=%%D"
exit /b
