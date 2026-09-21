@echo off
REM ============================================================
REM  YOU: double-click this INSIDE the repo folder:
REM       otacons-ai-ecosystem\tools\remote-support\
REM  Do NOT copy this BAT alone to Desktop/D:\ — it needs the
REM  other files in this same folder.
REM  Then send Desktop\SEND-TO-JOSH.bat to Josh.
REM  Designed by Antonio G. Garcia // Otaconskeep
REM ============================================================
setlocal EnableExtensions
title Make Josh installer - OtaconsKeep
cd /d "%~dp0"

if not exist "%~dp0Build-RemoteSupportInstaller.ps1" (
  echo.
  echo  [FAIL] Build-RemoteSupportInstaller.ps1 is missing next to this BAT.
  echo.
  echo  You must run this from the full repo folder:
  echo    otacons-ai-ecosystem\tools\remote-support\Make-Josh-Installer.bat
  echo.
  echo  Do not copy Make-Josh-Installer.bat by itself to D:\ or Desktop.
  echo  Open the GitHub repo folder on your PC, go to tools\remote-support,
  echo  then double-click Make-Josh-Installer.bat there.
  echo.
  echo  Looking for: %~dp0Build-RemoteSupportInstaller.ps1
  echo.
  pause
  exit /b 1
)

echo.
echo  Making Josh's remote-support installer...
echo  Browser will open Tailscale so you can create a one-time key.
echo  Paste that key when asked. Everything else is automatic.
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Build-RemoteSupportInstaller.ps1" -Recipient "Josh" -Alias "otacon-josh" -SshUser "Josh" -CopyToDesktop -OpenOutput -OpenTailscaleKeysPage
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
