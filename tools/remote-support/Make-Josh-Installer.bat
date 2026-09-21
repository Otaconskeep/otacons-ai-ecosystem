@echo off
REM ============================================================
REM  YOU: double-click this to make Josh's installer.
REM  Then send Desktop\SEND-TO-JOSH.bat to Josh.
REM  Josh: Run as administrator → Yes → Done.
REM  Designed by Antonio G. Garcia // Otaconskeep
REM ============================================================
setlocal EnableExtensions
title Make Josh installer - OtaconsKeep
cd /d "%~dp0"

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
