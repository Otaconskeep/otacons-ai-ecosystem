@echo off
REM ============================================================
REM  OtaconsKeep Windows Setup - entry point
REM  Double-click this file. Do not close the window unless asked.
REM  Designed by Antonio G. Garcia // Otaconskeep
REM  NEVER exits silently after fetch or PowerShell failure.
REM ============================================================
setlocal EnableExtensions EnableDelayedExpansion
title OtaconsKeep Setup

REM --- encoding check: NEVER append %~f0 after powershell -Command ---
REM powershell.exe concatenates tokens after -Command into script text.
REM Paths like OtaconsKeep-Setup (1).bat then parse as PowerShell code.
set "OTACON_SETUP_SELF=%~f0"
set "ENC_PS1=%~dp0deploy\check-bat-encoding.ps1"
if exist "%ENC_PS1%" goto ENC_VIA_FILE
goto ENC_VIA_ENV
:ENC_VIA_FILE
powershell -NoProfile -ExecutionPolicy Bypass -File "%ENC_PS1%" -Path "%~f0"
goto ENC_AFTER_CHECK
:ENC_VIA_ENV
powershell -NoProfile -ExecutionPolicy Bypass -Command "& { $p = $env:OTACON_SETUP_SELF; if ([string]::IsNullOrWhiteSpace($p)) { Write-Host 'ERROR: installer path missing'; exit 2 }; if (-not (Test-Path -LiteralPath $p)) { Write-Host 'ERROR: installer file not found'; exit 2 }; $b = [IO.File]::ReadAllBytes($p); if ($b.Length -lt 8) { Write-Host 'ERROR: installer file empty'; exit 2 }; if ($b[0] -eq 255 -and $b[1] -eq 254) { Write-Host 'ERROR: UTF-16 encoding'; exit 3 }; if ($b[0] -eq 254 -and $b[1] -eq 255) { Write-Host 'ERROR: UTF-16 encoding'; exit 3 }; if (-not ($b[0] -eq 239 -and $b[1] -eq 187 -and $b[2] -eq 191)) { Write-Host 'ERROR: missing UTF-8 BOM. Re-download from the Otaconskeep website.'; exit 4 }; $bare = 0; for ($i = 0; $i -lt $b.Length; $i++) { if ($b[$i] -eq 10 -and ($i -eq 0 -or $b[$i-1] -ne 13)) { $bare++ } }; if ($bare -gt 0) { Write-Host 'ERROR: Unix line endings (bare LF). Re-download OtaconsKeep-Setup.bat from the Otaconskeep website.'; exit 5 }; exit 0 }"
:ENC_AFTER_CHECK
if errorlevel 1 goto ENC_FAIL
goto ENC_OK
:ENC_FAIL
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
:ENC_OK

set "SCRIPT_DIR=%~dp0"
set "KEEP_DIR=%LOCALAPPDATA%\OtaconsKeep"
set "LOG_DIR=%KEEP_DIR%\Logs"
set "LOGFILE=%LOG_DIR%\installer.log"
set "ASSISTANT=%SCRIPT_DIR%deploy\windows-setup-assistant.ps1"
set "FETCH_PS1=%SCRIPT_DIR%deploy\bootstrap-fetch.ps1"
set "DOWNLOAD_ONE=%SCRIPT_DIR%deploy\download-one.ps1"
set "TAIL_LOG=%SCRIPT_DIR%deploy\tail-log.ps1"
set "BRANCH=main"
set "RAW=https://raw.githubusercontent.com/Otaconskeep/otacons-ai-ecosystem/%BRANCH%"
set "REPO_WEB=https://github.com/Otaconskeep/otacons-ai-ecosystem"
set "DEBUG="
set "MODE="
set "LAST_FAIL_CMD="
set "LAST_FAIL_REASON="
set "SYNTAX_ONLY="

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%" >nul 2>&1

:PARSE
if "%~1"=="" goto PARSE_DONE
if /I "%~1"=="--syntax-check" goto SET_SYNTAX
if /I "%~1"=="-syntax-check" goto SET_SYNTAX
if /I "%~1"=="--debug" goto SET_DEBUG
if /I "%~1"=="-debug" goto SET_DEBUG
if /I "%~1"=="--status" goto SET_STATUS
if /I "%~1"=="-status" goto SET_STATUS
if /I "%~1"=="--diagnostics" goto SET_DIAG
if /I "%~1"=="-diagnostics" goto SET_DIAG
if /I "%~1"=="--open" goto SET_OPEN
if /I "%~1"=="-open" goto SET_OPEN
if /I "%~1"=="--resume" goto SET_RESUME
if /I "%~1"=="-resume" goto SET_RESUME
if /I "%~1"=="--force" goto SET_FORCE
if /I "%~1"=="-force" goto SET_FORCE
if /I "%~1"=="--repair" goto SET_REPAIR
if /I "%~1"=="-repair" goto SET_REPAIR
if /I "%~1"=="--reinstall" goto SET_REINSTALL
if /I "%~1"=="-reinstall" goto SET_REINSTALL
if /I "%~1"=="--fix-codec" goto SET_FIXCODEC
if /I "%~1"=="-fix-codec" goto SET_FIXCODEC
if /I "%~1"=="--fix" goto SET_FIXCODEC
if /I "%~1"=="-fix" goto SET_FIXCODEC
goto PARSE_SHIFT
:SET_SYNTAX
set "SYNTAX_ONLY=1"
goto PARSE_SHIFT
:SET_DEBUG
set "DEBUG=1"
goto PARSE_SHIFT
:SET_STATUS
set "MODE=!MODE! -Status"
goto PARSE_SHIFT
:SET_DIAG
set "MODE=!MODE! -Diagnostics"
goto PARSE_SHIFT
:SET_OPEN
set "MODE=!MODE! -Open"
goto PARSE_SHIFT
:SET_RESUME
set "MODE=!MODE! -Resume"
goto PARSE_SHIFT
:SET_FORCE
set "MODE=!MODE! -Force"
goto PARSE_SHIFT
:SET_REPAIR
set "MODE=!MODE! -Repair"
goto PARSE_SHIFT
:SET_REINSTALL
set "MODE=!MODE! -Reinstall"
goto PARSE_SHIFT
:SET_FIXCODEC
set "MODE=!MODE! -FixCodec"
goto PARSE_SHIFT
:PARSE_SHIFT
shift
goto PARSE
:PARSE_DONE

if defined SYNTAX_ONLY goto SYNTAX_CHECK

call :LOG "==== install_otacon.bat start MODE=%MODE% DEBUG=%DEBUG% ===="

if defined DEBUG echo [DEBUG] env=Windows
if defined DEBUG echo [DEBUG] cwd=%CD%
if defined DEBUG echo [DEBUG] LOGFILE=%LOGFILE%
if defined DEBUG echo [DEBUG] ASSISTANT=%ASSISTANT%
if defined DEBUG echo [DEBUG] MODE=%MODE%

set "DEBUG_SWITCH="
if defined DEBUG set "DEBUG_SWITCH=-DebugMode"

:ENSURE_LOOP
call :ENSURE_ASSISTANT
set "RC=!ERRORLEVEL!"
if defined DEBUG echo [DEBUG] ENSURE_ASSISTANT errorlevel=!RC!
if "!RC!"=="0" goto ENSURE_OK
set "LAST_FAIL_CMD=download otaconskeep setup assistant files"
set "LAST_FAIL_REASON=Could not download required PowerShell setup scripts from GitHub."
call :CAPTURE_LAST_OUTPUT
call :SHOW_SETUP_STOPPED !RC!
if /I "!CHOICE!"=="R" goto ENSURE_LOOP
exit /b 1

:ENSURE_OK
if defined DEBUG echo [DEBUG] command=powershell -File windows-setup-assistant.ps1
call :LOG "launching assistant MODE=%MODE%"
powershell -NoProfile -ExecutionPolicy Bypass -File "%ASSISTANT%" %MODE% -RepoRoot "%SCRIPT_DIR:~0,-1%" -Branch "%BRANCH%" -RawBase "%RAW%"
set "RC=!ERRORLEVEL!"
call :LOG "assistant exit=!RC!"
if defined DEBUG echo [DEBUG] errorlevel=!RC!
if "!RC!"=="0" exit /b 0

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
echo  [L] open logs
echo  [X] exit
echo ============================================================
if defined DEBUG echo [DEBUG] never auto-exit on failure
:STAY_CHOICE
set /p "STAY=  Choice [L/X]: "
if /I "!STAY!"=="L" goto STAY_OPEN
if /I "!STAY!"=="X" exit /b !RC!
goto STAY_CHOICE
:STAY_OPEN
start "" explorer.exe "%LOG_DIR%"
goto STAY_CHOICE

:SYNTAX_CHECK
echo ============================================================
echo  OTACONSKEEP SYNTAX CHECK
echo ============================================================
call :CAPTURE_LAST_OUTPUT
echo  [OK] CAPTURE_LAST_OUTPUT
echo  SYNTAX_CHECK_OK
exit /b 0

:LOG
>>"%LOGFILE%" echo [%DATE% %TIME%] [BAT] %~1
exit /b 0

:CAPTURE_LAST_OUTPUT
set "LAST_FAIL_OUT="
if not exist "%LOGFILE%" exit /b 0
set "LASTOUT=%LOG_DIR%\last-output.txt"
if not exist "%TAIL_LOG%" goto CAPTURE_INLINE
powershell -NoProfile -ExecutionPolicy Bypass -File "%TAIL_LOG%" -LogFile "%LOGFILE%" -OutFile "%LASTOUT%" -Tail 12
set "LAST_FAIL_OUT=%LASTOUT%"
exit /b 0
:CAPTURE_INLINE
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-Content -LiteralPath $env:LOGFILE -Tail 12 | Set-Content -LiteralPath $env:LASTOUT -Encoding ASCII"
set "LAST_FAIL_OUT=%LASTOUT%"
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
if not exist "%LOG_DIR%\last-output.txt" goto SHOW_NO_LAST
type "%LOG_DIR%\last-output.txt"
goto SHOW_AFTER_LAST
:SHOW_NO_LAST
echo  see installer.log
:SHOW_AFTER_LAST
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
if /I "!CHOICE!"=="L" goto SS_OPEN_LOG
if /I "!CHOICE!"=="D" goto SS_DETAILS
if /I "!CHOICE!"=="R" exit /b 0
if /I "!CHOICE!"=="X" exit /b 0
goto SS_CHOICE
:SS_OPEN_LOG
start "" explorer.exe "%LOG_DIR%"
goto SS_CHOICE
:SS_DETAILS
echo.
echo  ---- technical details ----
if exist "%LOGFILE%" powershell -NoProfile -Command "Get-Content -LiteralPath $env:LOGFILE -Tail 40"
echo  ---- end ----
echo.
goto SS_CHOICE

:ENSURE_ASSISTANT
REM Always refresh bootstrap + deploy helpers. Existence is not freshness.
call :LOG "ENSURE_ASSISTANT always refreshing installer-owned deploy files"
goto ENSURE_NEED

:ENSURE_NEED
echo.
echo ============================================================
echo  OTACONSKEEP SETUP
echo ============================================================
echo  Refreshing setup files from GitHub...
echo  Do not close this window.
echo  source
echo    %REPO_WEB%
echo ============================================================
echo.
call :LOG "ENSURE_ASSISTANT downloading deploy scripts"

if not exist "%SCRIPT_DIR%deploy" mkdir "%SCRIPT_DIR%deploy" >nul 2>&1

set "FETCH_TMP=%FETCH_PS1%.otacon-new"
if exist "%FETCH_TMP%" del /f /q "%FETCH_TMP%" >nul 2>&1

:GET_FETCH
where curl.exe >nul 2>&1
if errorlevel 1 goto GET_FETCH_PS
call :LOG "curl ALWAYS refresh bootstrap-fetch.ps1"
echo  [0/n] preparing download helper
echo  status
echo    downloading...
if defined DEBUG echo [DEBUG] command=curl.exe bootstrap-fetch.ps1
curl.exe -fsSL --connect-timeout 20 --max-time 120 -o "%FETCH_TMP%" "%RAW%/deploy/bootstrap-fetch.ps1" >>"%LOGFILE%" 2>&1
set "RC=!ERRORLEVEL!"
call :LOG "curl helper exit=!RC!"
if defined DEBUG echo [DEBUG] errorlevel=!RC!
if not "!RC!"=="0" goto GET_FETCH_PS
if not exist "%FETCH_TMP%" goto GET_FETCH_PS
for %%A in ("%FETCH_TMP%") do if %%~zA LSS 40 goto GET_FETCH_PS
move /Y "%FETCH_TMP%" "%FETCH_PS1%" >nul
if errorlevel 1 goto GET_FETCH_PS
goto RUN_FETCH

:GET_FETCH_PS
call :LOG "powershell ALWAYS refresh bootstrap-fetch.ps1"
echo  status
echo    downloading via PowerShell...
if exist "%DOWNLOAD_ONE%" goto GET_FETCH_PS_FILE
powershell -NoProfile -ExecutionPolicy Bypass -Command "try{[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12}catch{}; $tmp=$env:FETCH_PS1+'.otacon-new'; Invoke-WebRequest -Uri ($env:RAW+'/deploy/bootstrap-fetch.ps1') -OutFile $tmp -UseBasicParsing -TimeoutSec 120; if(-not(Test-Path -LiteralPath $tmp)){exit 1}; if((Get-Item -LiteralPath $tmp).Length -lt 40){exit 1}; Move-Item -LiteralPath $tmp -Destination $env:FETCH_PS1 -Force; exit 0"
set "RC=!ERRORLEVEL!"
goto GET_FETCH_PS_DONE
:GET_FETCH_PS_FILE
powershell -NoProfile -ExecutionPolicy Bypass -File "%DOWNLOAD_ONE%" -Url "%RAW%/deploy/bootstrap-fetch.ps1" -OutFile "%FETCH_TMP%" -LogFile "%LOGFILE%"
set "RC=!ERRORLEVEL!"
if not "!RC!"=="0" goto GET_FETCH_PS_DONE
if not exist "%FETCH_TMP%" set "RC=2" & goto GET_FETCH_PS_DONE
move /Y "%FETCH_TMP%" "%FETCH_PS1%" >nul
if errorlevel 1 set "RC=2"
:GET_FETCH_PS_DONE
call :LOG "ps helper exit=!RC!"
if not "!RC!"=="0" exit /b !RC!

if not exist "%FETCH_PS1%" (
  call :LOG "helper still missing"
  exit /b 2
)

:RUN_FETCH
echo  status
echo    downloading...
if defined DEBUG echo [DEBUG] command=powershell -File bootstrap-fetch.ps1 -Manifest deploy
powershell -NoProfile -ExecutionPolicy Bypass -File "%FETCH_PS1%" -DestRoot "%SCRIPT_DIR:~0,-1%" -RawBase "%RAW%" -LogFile "%LOGFILE%" -Manifest deploy %DEBUG_SWITCH%
set "RC=!ERRORLEVEL!"
call :LOG "bootstrap-fetch deploy exit=!RC!"
if defined DEBUG echo [DEBUG] errorlevel=!RC!
if not "!RC!"=="0" exit /b !RC!

if not exist "%ASSISTANT%" (
  call :LOG "assistant missing after fetch"
  exit /b 2
)
if not exist "%SCRIPT_DIR%deploy\repair-otacon-core.ps1" (
  call :LOG "repair helper missing after fetch"
  exit /b 2
)
if not exist "%SCRIPT_DIR%deploy\wsl-bash-file.ps1" (
  call :LOG "wsl-bash-file.ps1 missing after fetch"
  exit /b 2
)
findstr /C:"Invoke-OtaconWslBashFile" "%SCRIPT_DIR%deploy\repair-otacon-core.ps1" >nul
if errorlevel 1 (
  call :LOG "repair helper stale after fetch"
  exit /b 2
)
findstr /C:"bash -lc $bash" "%SCRIPT_DIR%deploy\repair-otacon-core.ps1" >nul
if not errorlevel 1 (
  call :LOG "repair helper still has bash -lc after fetch"
  exit /b 2
)
for %%A in ("%ASSISTANT%") do if %%~zA LSS 40 (
  call :LOG "assistant too small"
  exit /b 2
)
echo  status
echo    verifying files... OK
exit /b 0
