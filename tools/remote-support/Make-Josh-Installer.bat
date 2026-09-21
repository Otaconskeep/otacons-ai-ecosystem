@echo off
REM ============================================================
REM  OtaconsKeep — Make Josh installer
REM  Double-click from ANYWHERE (Desktop, D:\, Downloads, repo).
REM  Designed by Antonio G. Garcia // Otaconskeep
REM ============================================================
setlocal EnableExtensions
title Make Josh installer - OtaconsKeep

echo.
echo  Making Josh's remote-support installer...
echo  Works from Desktop / D:\ / Downloads — no special folder needed.
echo.

set "LAUNCHER=%TEMP%\Otacon-Invoke-MakeFriendInstaller.ps1"
set "NEAR=%~dp0"

REM Prefer launcher next to this BAT (full repo). Else download from GitHub.
if exist "%NEAR%Invoke-MakeFriendInstaller.ps1" (
  copy /Y "%NEAR%Invoke-MakeFriendInstaller.ps1" "%LAUNCHER%" >nul
) else (
  echo  Downloading launcher from GitHub...
  powershell -NoProfile -ExecutionPolicy Bypass -Command " [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri 'https://raw.githubusercontent.com/Otaconskeep/otacons-ai-ecosystem/main/tools/remote-support/Invoke-MakeFriendInstaller.ps1' -OutFile $env:TEMP\Otacon-Invoke-MakeFriendInstaller.ps1 -UseBasicParsing "
  if errorlevel 1 (
    echo  [FAIL] Could not download launcher. Check internet / GitHub access.
    pause
    exit /b 1
  )
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%LAUNCHER%" -Recipient "Josh" -Alias "otacon-josh" -SshUser "Josh" -NearbyDir "%NEAR%"
set "EC=%ERRORLEVEL%"

echo.
if not "%EC%"=="0" (
  echo  [FAIL] Could not build Josh's installer. Leave this window open and tell Xof.
) else (
  echo  Done. Send Desktop\SEND-TO-JOSH.bat to Josh.
)
echo.
pause
exit /b %EC%
