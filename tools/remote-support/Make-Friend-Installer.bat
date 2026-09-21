@echo off
REM ============================================================
REM  YOU: pick a friend, paste one Tailscale key, get a BAT to send.
REM  Designed by Antonio G. Garcia // Otaconskeep
REM ============================================================
setlocal EnableExtensions
title Make friend installer - OtaconsKeep
cd /d "%~dp0"

echo.
echo  Who is this for?
echo    1  Josh
echo    2  Chris
echo.
set /p "CHOICE=Type 1 or 2 then Enter: "

if "%CHOICE%"=="1" goto JOSH
if /I "%CHOICE%"=="Josh" goto JOSH
if "%CHOICE%"=="2" goto CHRIS
if /I "%CHOICE%"=="Chris" goto CHRIS

echo  Unknown choice.
pause
exit /b 1

:JOSH
call "%~dp0Make-Josh-Installer.bat"
exit /b %ERRORLEVEL%

:CHRIS
call "%~dp0Make-Chris-Installer.bat"
exit /b %ERRORLEVEL%
