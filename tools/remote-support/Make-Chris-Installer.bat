@echo off
REM ============================================================
REM  YOU: double-click this to make Chris's installer.
REM  Then send Desktop\SEND-TO-CHRIS.bat to Chris.
REM  Chris: Run as administrator → Yes → Done.
REM  Designed by Antonio G. Garcia // Otaconskeep
REM ============================================================
setlocal EnableExtensions
title Make Chris installer - OtaconsKeep
cd /d "%~dp0"

echo.
echo  Making Chris's remote-support installer...
echo  Browser will open Tailscale so you can create a one-time key.
echo  Paste that key when asked. Everything else is automatic.
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Build-RemoteSupportInstaller.ps1" -Recipient "Chris" -Alias "otacon-chris" -SshUser "Chris" -CopyToDesktop -OpenOutput -OpenTailscaleKeysPage
set "EC=%ERRORLEVEL%"

echo.
if not "%EC%"=="0" (
  echo  [FAIL] Could not build Chris's installer. Leave this window open and tell Xof.
) else (
  echo  Done. Send Desktop\SEND-TO-CHRIS.bat to Chris.
)
echo.
pause
exit /b %EC%
