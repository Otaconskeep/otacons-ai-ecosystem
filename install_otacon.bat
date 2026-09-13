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
    exit /b 1
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
exit /b 0

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

REM Preflight: WSL version + systemd tip (non-fatal)
wsl.exe -d "%UBUNTU_NAME%" -- bash -lc "grep -qi microsoft /proc/version && echo WSL_OK; command -v systemctl >/dev/null && systemctl is-system-running 2>/dev/null || true"

call :RUN_LINUX_INSTALLER
set "INSTALL_RC=%errorlevel%"

if "%INSTALL_RC%"=="42" (
    echo.
    echo Enabling a Linux feature Otacon needs to auto-start. Restarting
    echo ONLY the target distro ^(%UBUNTU_NAME%^) once...
    wsl.exe --terminate "%UBUNTU_NAME%"
    timeout /t 3 /nobreak >nul
    call :RUN_LINUX_INSTALLER
    set "INSTALL_RC=!errorlevel!"
)

if not "%INSTALL_RC%"=="0" (
    if "%INSTALL_RC%"=="2" (
        echo.
        echo ============================================================
        echo  OTACON INSTALLED ^(DEGRADED^)
        echo ============================================================
        echo Core works, but an optional component failed. Scroll up for
        echo details. Exit code 2 = DEGRADED.
        pause
        exit /b 2
    )
    echo.
    echo ============================================================
    echo  SOMETHING WENT WRONG
    echo ============================================================
    echo The installer exited with code %INSTALL_RC% inside Ubuntu. Scroll
    echo up to see what it said, or come share it in Discord.
    pause
    exit /b %INSTALL_RC%
)

echo.
echo Setting up Otacon to start automatically with Windows...
powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%deploy\install-wake-task.ps1" -DistroName "%UBUNTU_NAME%" -Port 5757 >nul 2>&1
if errorlevel 1 (
    echo Couldn't register the auto-start task ^(this doesn't affect the
    echo install itself -- Otacon still works, you'll just need to open
    echo it manually after a restart^). See README.md for the manual steps.
) else (
    echo Done. Otacon will already be running the next time you log in.
)

echo.
echo ============================================================
echo  OTACON IS READY
echo ============================================================
echo Open Otacon:  http://localhost:5757
echo Selected WSL distro: %UBUNTU_NAME%
echo.
echo Come back to this address any time -- Otacon starts itself with
echo Windows from now on. Run this file again if you ever need to
echo repair or update the install; it's always safe to rerun.
echo.
pause
exit /b 0

:RUN_LINUX_INSTALLER
REM Download installer to a temp file inside WSL, verify non-empty, then
REM execute with env vars attached to bash (NOT to curl). Prevents both
REM the Windows ENV= curl|bash propagation bug and empty-script execution.
wsl.exe -d "%UBUNTU_NAME%" -- bash -lc "set -euo pipefail; TMP=$(mktemp /tmp/otacon-install.XXXXXX.sh); trap 'rm -f \"$TMP\"' EXIT; curl -fsSL https://raw.githubusercontent.com/Otaconskeep/otacons-ai-ecosystem/main/install_otacon.sh -o \"$TMP\"; test -s \"$TMP\" || { echo 'Download failed or empty installer' >&2; exit 1; }; head -n1 \"$TMP\" | grep -q bash || { echo 'Downloaded file does not look like the Otacon installer' >&2; exit 1; }; env OTACON_INSTALL_DEFAULT_MODEL='%OTACON_INSTALL_DEFAULT_MODEL%' OTACON_INSTALL_VOICE_TRAINER='%OTACON_INSTALL_VOICE_TRAINER%' OTACON_LLM_MODEL='%OTACON_LLM_MODEL%' OTACON_BUILD_NATIVE='%OTACON_BUILD_NATIVE%' OTACON_LAN_MODE='%OTACON_LAN_MODE%' OTACON_INSTALL_STT='%OTACON_INSTALL_STT%' OTACON_CHAT_HOST='%OTACON_CHAT_HOST%' OTACON_CHAT_PORT='%OTACON_CHAT_PORT%' OTACON_INSTALL_DIR='%OTACON_INSTALL_DIR%' OTACON_INSTALL_DEB='%OTACON_INSTALL_DEB%' OTACON_LAUNCH_WIZARD='%OTACON_LAUNCH_WIZARD%' OTACON_RUN_TESTS='%OTACON_RUN_TESTS%' OTACON_RELEASE='%OTACON_RELEASE%' bash \"$TMP\""
exit /b %errorlevel%

:FIND_UBUNTU
set "UBUNTU_NAME="
if exist "%FIND_UBUNTU_PS1%" (
  for /f "delims=" %%D in ('powershell -NoProfile -ExecutionPolicy Bypass -File "%FIND_UBUNTU_PS1%"') do set "UBUNTU_NAME=%%D"
) else (
  REM Fallback when bat is downloaded alone without deploy/
  for /f "delims=" %%D in ('powershell -NoProfile -Command "$raw = & wsl.exe -l -q 2>$null; $clean = $raw | ForEach-Object { $_ -replace \"`0\", \"\" } | Where-Object { $_.Trim() -ne \"\" }; $match = $clean | Where-Object { $_ -match \"Ubuntu\" } | Select-Object -First 1; if ($match) { Write-Output $match.Trim() }"') do set "UBUNTU_NAME=%%D"
)
if defined UBUNTU_NAME echo Using WSL distro: %UBUNTU_NAME%
exit /b
