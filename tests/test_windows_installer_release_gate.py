#!/usr/bin/env python3
"""Release-gate static contracts for the Windows OtaconsKeep installer.

These tests assert the source contracts for gates A–J without weakening
fixtures. They do not claim a live Windows run succeeded.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSISTANT = (ROOT / "deploy" / "windows-setup-assistant.ps1").read_text(encoding="utf-8", errors="replace")
FIND_UBUNTU = (ROOT / "deploy" / "find-ubuntu.ps1").read_text(encoding="utf-8", errors="replace")
CHECK_ENC = (ROOT / "deploy" / "check-bat-encoding.ps1").read_text(encoding="utf-8", errors="replace")
WAKE = (ROOT / "deploy" / "wake-otacon.ps1").read_text(encoding="utf-8", errors="replace")
INSTALL_BAT = (ROOT / "install_otacon.bat").read_text(encoding="utf-8", errors="replace")
SETUP_BAT = (ROOT / "OtaconsKeep-Setup.bat").read_text(encoding="utf-8", errors="replace")
SERVER = (ROOT / "installer" / "server.py").read_text(encoding="utf-8", errors="replace")
README = (ROOT / "README.md").read_text(encoding="utf-8", errors="replace")
INSTALL_SH = (ROOT / "install_otacon.sh").read_text(encoding="utf-8", errors="replace")
TAURI = (ROOT / "src-tauri" / "tauri.conf.json").read_text(encoding="utf-8", errors="replace")


def test_A_ready_choice_panel_and_force():
    assert "[switch]$Force" in ASSISTANT
    assert "[switch]$Repair" in ASSISTANT
    assert "[switch]$Reinstall" in ASSISTANT
    # AutoPilot: happy-path READY opens Codec — no O/P/R/X menu.
    assert "$script:AutoPilot = $true" in ASSISTANT or "AutoPilot = $true" in ASSISTANT
    assert "no O/F/P/R menu" in ASSISTANT or "no O/P/R/X" in ASSISTANT.lower() or "AutoPilot opens Codec" in ASSISTANT
    assert "Choice [O/P/R/X]" not in ASSISTANT
    assert "Force/Repair/Reinstall bypass of READY short-circuit" in ASSISTANT
    assert re.search(r"if \(\$snap\.web_health\) \{\s*Show-Box \"OTACON IS READY\".*press O to open otacon\s*.*press X to finish\s*\).*return 0", ASSISTANT, re.S) is None
    assert "-Force" in INSTALL_BAT
    assert "SET_FORCE" in INSTALL_BAT


def test_B_health_requires_branding_identity():
    assert "function Test-OtaconIdentity" in ASSISTANT
    assert 'product_name' in ASSISTANT
    assert '$pname -eq "Otacon"' in ASSISTANT
    assert "occupied_non_otacon" in ASSISTANT
    assert "Port $Port is occupied by a non-Otacon service." in ASSISTANT or "Port $Port is occupied by a non-Otacon service." in ASSISTANT.replace("`", "")
    assert "Port $Port is occupied by a non-Otacon service." in ASSISTANT
    # Old weak path must be gone
    assert "branding optional" not in ASSISTANT
    assert "api/branding" in WAKE
    assert 'product_name -eq "Otacon"' in WAKE or "-eq \"Otacon\"" in WAKE


def test_C_failed_bootstrap_keeps_failed_state():
    assert 'stage = "failed"' in ASSISTANT
    assert "last_error" in ASSISTANT
    assert "linux-install-tail.log" in ASSISTANT
    # Success path must not leave prior error
    assert "function Save-InstallerComplete" in ASSISTANT
    assert "last_error = $null" in ASSISTANT or "last_error=$null" in ASSISTANT.replace(" ", "")


def test_C3_honest_exit_code_never_blank_success():
    """Blank/null PowerShell exit must not become BAT exit 0 after FAILED."""
    assert "function ConvertTo-InstallerExitCode" in ASSISTANT
    assert "exit (ConvertTo-InstallerExitCode" in ASSISTANT
    setup = SETUP_BAT
    assert "--update" in setup
    # Installer cache: existence/pin alone is never freshness; always refresh bundle.
    assert "always refreshes installer bundle" in setup.lower() or "ALWAYS refreshing bootstrap-fetch.ps1" in setup
    assert "otacon-new" in setup
    fetch = (ROOT / "deploy" / "bootstrap-fetch.ps1").read_text(encoding="utf-8", errors="replace")
    assert "installer-revision.txt" in fetch
    assert "repair-otacon-core.ps1" in fetch
    assert "wsl-bash-file.ps1" in fetch
    assert "MISSING REQUIRED" in fetch or "required helpers present" in fetch
    assert "BOOTSTRAP_OK" in fetch
    assert "installer_version" in fetch


def test_C2_wsl_phase_uses_file_script_and_exit_marker():
    """Privileged exit 42 must not become blank Start-Process ExitCode."""
    assert "wsl-phase-" in ASSISTANT
    assert "OTACON_PHASE_EXIT" in ASSISTANT
    assert "fromMarker" in ASSISTANT
    assert "WriteAllText" in ASSISTANT
    assert '", "-c",' in ASSISTANT
    assert "Format-StartProcessArgumentList" in ASSISTANT
    assert "Start-OtaconWslBashCProcess" in ASSISTANT
    # Stale waiting_for_reboot must yield when Ubuntu is already ready
    assert "ubuntuReady -and -not $rebootPending" in ASSISTANT
    fetch = (ROOT / "deploy" / "bootstrap-fetch.ps1").read_text(encoding="utf-8", errors="replace")
    assert "install_otacon.sh" in fetch


def test_D_success_clears_last_error():
    assert "Save-InstallerComplete" in ASSISTANT
    assert 'last_step  = "complete"' in ASSISTANT or 'last_step = "complete"' in ASSISTANT
    # Old bare complete write without clear should not be the only success path
    assert ASSISTANT.count("Save-InstallerComplete") >= 2


def test_E_dedicated_wsl_no_silent_first_ubuntu():
    assert "Ubuntu-Otacon" in ASSISTANT
    assert "Resolve-OtaconDistroInteractive" in ASSISTANT
    # AutoPilot: no R/C/A distro menu; create dedicated beside existing Ubuntu*.
    assert "AutoPilot: never ask R/C/A" in ASSISTANT
    assert "WSL DISTRIBUTION CHOICE" not in ASSISTANT
    assert "I'll add $PreferredDistro beside it" in ASSISTANT or "beside it so nothing else is changed" in ASSISTANT
    assert "AllowFirstMatch" in FIND_UBUNTU
    assert "Select-Object -First 1" in FIND_UBUNTU  # only under AllowFirstMatch path
    # Default find-ubuntu must NOT auto-pick first Ubuntu without -AllowFirstMatch
    assert "-AllowFirstMatch" in FIND_UBUNTU
    assert "Never silently" in FIND_UBUNTU or "never silently" in FIND_UBUNTU.lower()
    assert "wsl -l -v" in ASSISTANT or "wsl.exe -l -v" in ASSISTANT


def test_F_port_5757_canonical_no_operational_8787_fallback():
    assert "$Port      = 5757" in ASSISTANT or "$Port = 5757" in ASSISTANT.replace(" ", "")
    assert "OTACON_PORT', '5757')" in SERVER or 'OTACON_PORT\', \'5757\')' in SERVER
    assert "getenv('OTACON_PORT', '8787')" not in SERVER
    assert "127.0.0.1:5757" in README
    assert "checks http://127.0.0.1:5757" in INSTALL_SH
    assert "5757" in TAURI
    # Remaining 8787 must be explicitly legacy/smoke, not operational default
    for chunk in (SERVER,):
        assert "8787" not in chunk or "legacy" in chunk.lower()
    # install_otacon.sh may mention 8787 only as retired/legacy or smoke 18787
    if "8787" in INSTALL_SH:
        assert "legacy" in INSTALL_SH.lower() or "18787" in INSTALL_SH


def test_G_elevation_and_runonce_pass_resume():
    assert '" --resume"' in ASSISTANT or "' --resume'" in ASSISTANT or '--resume' in ASSISTANT
    assert 'ArgumentList $elevateArgs' in ASSISTANT or 'ArgumentList @("--resume")' in ASSISTANT
    assert "RunOnce registered for $cmd" in ASSISTANT or "--resume" in ASSISTANT
    # Ensure-Admin must pass --resume
    assert re.search(r"Ensure-Admin[\s\S]*--resume", ASSISTANT) is not None
    assert re.search(r"Register-ResumeAfterReboot[\s\S]*--resume", ASSISTANT) is not None


def test_I_encoding_rejects_bare_lf():
    assert "bare LF" in CHECK_ENC or "bareLf" in CHECK_ENC or "0x0A" in CHECK_ENC
    assert "exit 5" in CHECK_ENC
    assert "bare LF" in INSTALL_BAT or "Unix line endings" in INSTALL_BAT
    assert "Unix line endings" in SETUP_BAT
    # BAT must reject UTF-8 BOM (breaks @echo off); must not require BOM.
    assert "not allowed" in CHECK_ENC.lower() and "BOM" in CHECK_ENC
    assert "missing UTF-8 BOM" not in CHECK_ENC
    assert "UTF-8 BOM is not allowed" in SETUP_BAT or "BOM is not allowed" in SETUP_BAT


def test_J_ready_requires_identity_and_no_fatal_error():
    assert "identity_ok" in ASSISTANT or "Test-OtaconIdentity" in ASSISTANT
    assert "PORT_CONFLICT" in ASSISTANT
    assert "staleFail" in ASSISTANT or "last_error" in ASSISTANT
    assert "identity check passed" in ASSISTANT.lower() or "identity health ok" in ASSISTANT.lower() or "Identity OK" in ASSISTANT


def test_P0_tts_finalize_hard_fail_no_soft_success():
    assert "function Test-OtaconTts" in ASSISTANT
    assert "DEGRADED_TTS" in ASSISTANT
    assert "Invoke-RepairTtsAndWake" in ASSISTANT
    assert "hard FAIL" in ASSISTANT or "Finalize failed" in ASSISTANT
    # Soft-success anti-pattern must be gone
    assert "if ($userCode -eq 0 -or $userCode -eq 2) { return $userCode }" not in ASSISTANT
    assert "otacon-tts.service" in INSTALL_SH
    assert "failed to become active after finalize" in INSTALL_SH
    assert "otacon-tts" in WAKE
    assert "wyoming-piper" in WAKE


def test_P0_ready_requires_tts_not_web_alone():
    assert "tts_ok" in ASSISTANT
    assert 'Write-Host $(if ($s.web_health) { "READY" } else { $s.overall })' not in ASSISTANT
    # AutoPilot repairs TTS without a repair-choice menu when web is up but voice is down.
    assert "Chat is up, but voice needs a tune-up" in ASSISTANT or "I'll repair that automatically" in ASSISTANT
    assert "Invoke-RepairTtsAndWake" in ASSISTANT
    assert "Choice [O/F/P/R]" not in ASSISTANT
    assert "OTACON NEEDS REPAIR" not in ASSISTANT


def test_P0_autopilot_otacon_ui():
    assert "function Show-OtaconRain" in ASSISTANT
    assert "function Write-OtaconSay" in ASSISTANT
    assert "function Repair-WslLinuxUser" in ASSISTANT
    assert "function ConvertFrom-WslPasswdRecord" in ASSISTANT
    assert "You don't need to know Linux" in ASSISTANT or "you don't need to know Linux" in ASSISTANT
    assert "I'm handling the installation" in ASSISTANT or "I am handling the installation" in ASSISTANT
    assert "I'm repairing it now" in ASSISTANT
    assert "I'm leaving your Linux account unchanged" in ASSISTANT
    assert "Back on track. Continuing installation" in ASSISTANT
    assert "Continuing - Stage 6 will retry" not in ASSISTANT
    assert "creating fallback user=otacon" not in ASSISTANT
    assert "Choice [I/F/X]" not in ASSISTANT
    assert "Choice [R/L]" not in ASSISTANT
    assert "press I to continue setup" not in ASSISTANT
    # Exhausted-failure UI is Enter/L/Q, not R/O/X
    help_start = ASSISTANT.find("function Show-SetupNeedsHelp")
    help_end = ASSISTANT.find("function Register-ResumeAfterReboot", help_start)
    help_fn = ASSISTANT[help_start:help_end]
    assert "Choice [R/O/X]" not in help_fn
    assert "ENTER" in help_fn
    diag_start = ASSISTANT.find("function Get-WslLinuxUserDiagnosis")
    diag_end = ASSISTANT.find("function Get-WslEffectiveDefaultUser", diag_start)
    diag_fn = ASSISTANT[diag_start:diag_end]
    assert "--exec getent passwd" in diag_fn
    assert "bash -lc" not in diag_fn


def test_P1_doctor_and_uninstall_cover_tts():
    doctor = (ROOT / "installer" / "doctor.py").read_text(encoding="utf-8", errors="replace")
    uninstall = (ROOT / "uninstall_otacon.bat").read_text(encoding="utf-8", errors="replace")
    css = (ROOT / "ui" / "codec.css").read_text(encoding="utf-8", errors="replace")
    assert "otacon_tts" in doctor
    assert "voice_preview" in doctor or "wyoming_port" in doctor
    assert "otacon-tts.service" in uninstall
    assert "object-fit:contain" in css
    assert "object-fit:cover" not in css.split(".codec-port")[1].split("@media")[0]


def test_no_weak_health_fallback_true_on_branding_failure():
    # The exact anti-pattern from the live bug
    assert "root answered; branding optional" not in ASSISTANT
    assert "catch {\n            # root answered; branding optional\n            return $true" not in ASSISTANT


if __name__ == "__main__":
    import sys
    import traceback

    tests = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except Exception as exc:
            failed += 1
            print(f"FAIL {t.__name__}: {exc}")
            traceback.print_exc()
    print(f"{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
