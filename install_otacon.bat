@echo off
REM ============================================================
REM  OtaconsKeep Windows Setup - entry point
REM  Double-click this file. Do not close the window unless asked.
REM  Designed by Antonio G. Garcia // Otaconskeep
REM  NEVER exits silently after fetch or PowerShell failure.
REM ============================================================
setlocal EnableExtensions EnableDelayedExpansion
title OtaconsKeep Setup
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
set "KEEP_DIR=%LOCALAPPDATA%\OtaconsKeep"
set "LOG_DIR=%KEEP_DIR%\Logs"
set "LOGFILE=%LOG_DIR%\installer.log"
set "ASSISTANT=%SCRIPT_DIR%deploy\windows-setup-assistant.ps1"
set "FETCH_PS1=%SCRIPT_DIR%deploy\bootstrap-fetch.ps1"
set "BRANCH=main"
set "RAW=https://raw.githubusercontent.com/Otaconskeep/otacons-ai-ecosystem/%BRANCH%"
set "REPO_WEB=https://github.com/Otaconskeep/otacons-ai-ecosystem"
set "DEBUG="
set "MODE="
set "LAST_FAIL_CMD="
set "LAST_FAIL_REASON="

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%" >nul 2>&1

:PARSE
if "%~1"=="" goto PARSE_DONE
if /I "%~1"=="--debug" (
  set "DEBUG=1"
  shift
  goto PARSE
)
if /I "%~1"=="-debug" (
  set "DEBUG=1"
  shift
  goto PARSE
)
if /I "%~1"=="--status" set "MODE=-Status"
if /I "%~1"=="-status" set "MODE=-Status"
if /I "%~1"=="--diagnostics" set "MODE=-Diagnostics"
if /I "%~1"=="-diagnostics" set "MODE=-Diagnostics"
if /I "%~1"=="--open" set "MODE=-Open"
if /I "%~1"=="-open" set "MODE=-Open"
if /I "%~1"=="--resume" set "MODE=-Resume"
if /I "%~1"=="-resume" set "MODE=-Resume"
shift
goto PARSE
:PARSE_DONE

call :LOG "==== install_otacon.bat start MODE=%MODE% DEBUG=%DEBUG% SCRIPT_DIR=%SCRIPT_DIR% CD=%CD% ===="

if defined DEBUG (
  echo [DEBUG] env=Windows
  echo [DEBUG] cwd=%CD%
  echo [DEBUG] LOGFILE=%LOGFILE%
  echo [DEBUG] ASSISTANT=%ASSISTANT%
  echo [DEBUG] MODE=%MODE%
)

set "DEBUG_SWITCH="
if defined DEBUG set "DEBUG_SWITCH=-DebugMode"

:ENSURE_LOOP
call :ENSURE_ASSISTANT
set "RC=!ERRORLEVEL!"
if defined DEBUG echo [DEBUG] ENSURE_ASSISTANT errorlevel=!RC!
if not "!RC!"=="0" (
  set "LAST_FAIL_CMD=download otaconskeep setup assistant files"
  set "LAST_FAIL_REASON=Could not download required PowerShell setup scripts from GitHub."
  call :CAPTURE_LAST_OUTPUT
  call :SHOW_SETUP_STOPPED !RC!
  if /I "!CHOICE!"=="R" goto ENSURE_LOOP
  exit /b 1
)

if defined DEBUG (
  echo [DEBUG] env=Windows
  echo [DEBUG] command=powershell -NoProfile -ExecutionPolicy Bypass -File "%ASSISTANT%" %MODE% -RepoRoot "%SCRIPT_DIR:~0,-1%" -Branch "%BRANCH%"
)
call :LOG "launching assistant MODE=%MODE%"
powershell -NoProfile -ExecutionPolicy Bypass -File "%ASSISTANT%" %MODE% -RepoRoot "%SCRIPT_DIR:~0,-1%" -Branch "%BRANCH%"
set "RC=!ERRORLEVEL!"
call :LOG "assistant exit=!RC!"
if defined DEBUG echo [DEBUG] errorlevel=!RC!

if not "!RC!"=="0" (
  echo.
  echo ============================================================
  echo                  OTACON SETUP STOPPED
  echo ============================================================
  echo.
  echo  something went wrong during setup
  echo.
  echo  nothing has been damaged
  echo.
  echo  failed command
  echo  powershell -File deploy\windows-setup-assistant.ps1
  echo.
  echo  exit code
  echo  !RC!
  echo.
  echo  technical details
  echo  %LOGFILE%
  echo.
  echo  If you already answered R/O/X above, press a letter key to close.
  echo  [L] open logs now, then press X after
  echo ============================================================
  if defined DEBUG echo [DEBUG] never auto-exit on failure
  :STAY_CHOICE
  set /p "STAY=  Choice [L/X]: "
  if /I "!STAY!"=="L" (
    start "" explorer.exe "%LOG_DIR%"
    goto STAY_CHOICE
  )
  if /I "!STAY!"=="X" exit /b !RC!
  pause >nul
)

exit /b !RC!

REM ------------------------------------------------------------
:LOG
>>"%LOGFILE%" echo [%DATE% %TIME%] [BAT] %~1
exit /b 0

:CAPTURE_LAST_OUTPUT
if exist "%LOGFILE%" (
  powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "Get-Content -LiteralPath '%LOGFILE%' -Tail 12" >"%LOG_DIR%\last-output.txt" 2>nul
)
exit /b 0

:SHOW_SETUP_STOPPED
set "FAIL_RC=%~1"
set "CHOICE="
call :LOG "SHOW_SETUP_STOPPED rc=%FAIL_RC% cmd=%LAST_FAIL_CMD%"
echo.
echo ============================================================
echo                  OTACON SETUP STOPPED
echo ============================================================
echo.
echo  something went wrong while fetching otaconskeep
echo.
echo  nothing has been damaged
echo.
echo  failed command
echo  %LAST_FAIL_CMD%
echo.
echo  exit code
echo  %FAIL_RC%
echo.
echo  reason
echo  %LAST_FAIL_REASON%
echo.
echo  last output
if exist "%LOG_DIR%\last-output.txt" (
  type "%LOG_DIR%\last-output.txt"
) else (
  echo  ^(see installer.log^)
)
echo.
echo  technical details
echo  %LOGFILE%
echo.
echo  [R] retry this step
echo  [L] open installer log
echo  [D] show technical details
echo  [X] exit
echo.
echo ============================================================
echo.
:SS_CHOICE
set /p "CHOICE=  Choice [R/L/D/X]: "
if /I "!CHOICE!"=="L" (
  start "" explorer.exe "%LOG_DIR%"
  goto SS_CHOICE
)
if /I "!CHOICE!"=="D" (
  echo.
  echo  ---- technical details ----
  if exist "%LOGFILE%" powershell -NoProfile -Command "Get-Content -LiteralPath '%LOGFILE%' -Tail 40"
  echo  ---- end ----
  echo.
  goto SS_CHOICE
)
if /I "!CHOICE!"=="R" exit /b 0
if /I "!CHOICE!"=="X" exit /b 0
goto SS_CHOICE

:ENSURE_ASSISTANT
if exist "%ASSISTANT%" (
  for %%A in ("%ASSISTANT%") do if %%~zA GEQ 40 (
    call :LOG "assistant present"
    exit /b 0
  )
)

echo.
echo ============================================================
echo  OTACONSKEEP SETUP
echo ============================================================
echo  Downloading setup files ^(first run only^)...
echo  Do not close this window.
echo  source
echo    %REPO_WEB%
echo ============================================================
echo.
call :LOG "ENSURE_ASSISTANT downloading deploy scripts"

if not exist "%SCRIPT_DIR%deploy" mkdir "%SCRIPT_DIR%deploy" >nul 2>&1

if exist "%FETCH_PS1%" (
  for %%A in ("%FETCH_PS1%") do if %%~zA GEQ 40 goto RUN_FETCH
)

where curl.exe >nul 2>&1
if not errorlevel 1 (
  call :LOG "curl helper bootstrap-fetch.ps1"
  echo  [0/n] preparing download helper
  echo  status
  echo    downloading...
  if defined DEBUG echo [DEBUG] command=curl.exe ... bootstrap-fetch.ps1
  curl.exe -fsSL --connect-timeout 20 --max-time 120 -o "%FETCH_PS1%" "%RAW%/deploy/bootstrap-fetch.ps1" >>"%LOGFILE%" 2>&1
  set "RC=!ERRORLEVEL!"
  call :LOG "curl helper exit=!RC!"
  if defined DEBUG echo [DEBUG] errorlevel=!RC!
)

if not exist "%FETCH_PS1%" (
  call :LOG "powershell helper bootstrap-fetch.ps1"
  echo  status
  echo    downloading via PowerShell...
  powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$ErrorActionPreference='Stop';" ^
    "try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 -bor [Net.SecurityProtocolType]::Tls11 -bor [Net.SecurityProtocolType]::Tls } catch {};" ^
    "$out='%FETCH_PS1%'; $url='%RAW%/deploy/bootstrap-fetch.ps1'; $log='%LOGFILE%';" ^
    "try {" ^
    "  Add-Content $log ('['+(Get-Date -Format o)+'] GET '+$url);" ^
    "  $tmp=$out+'.otacon-download';" ^
    "  Invoke-WebRequest -Uri $url -OutFile $tmp -UseBasicParsing -TimeoutSec 120;" ^
    "  if(-not (Test-Path $tmp) -or ((Get-Item $tmp).Length -lt 40)){ throw 'helper too small' };" ^
    "  Move-Item -Force $tmp $out;" ^
    "  exit 0" ^
    "} catch { Add-Content $log ('ERROR '+$_.Exception.Message); Write-Host $_.Exception.Message; exit 1 }"
  set "RC=!ERRORLEVEL!"
  call :LOG "ps helper exit=!RC!"
  if not "!RC!"=="0" exit /b !RC!
)

if not exist "%FETCH_PS1%" (
  call :LOG "helper still missing"
  exit /b 2
)

:RUN_FETCH
echo  status
echo    downloading...
if defined DEBUG (
  echo [DEBUG] env=Windows
  echo [DEBUG] command=powershell -File "%FETCH_PS1%" -Manifest deploy
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%FETCH_PS1%" -DestRoot "%SCRIPT_DIR:~0,-1%" -RawBase "%RAW%" -LogFile "%LOGFILE%" -Manifest deploy %DEBUG_SWITCH%
set "RC=!ERRORLEVEL!"
call :LOG "bootstrap-fetch deploy exit=!RC!"
if defined DEBUG echo [DEBUG] errorlevel=!RC!
if not "!RC!"=="0" exit /b !RC!

if not exist "%ASSISTANT%" (
  call :LOG "assistant missing after fetch"
  exit /b 2
)
for %%A in ("%ASSISTANT%") do if %%~zA LSS 40 (
  call :LOG "assistant too small"
  exit /b 2
)
echo  status
echo    verifying files... OK
exit /b 0
