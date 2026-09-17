"""Contracts for the real Otacon Expansion Windows installer."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BAT = (ROOT / "OtaconExpansion-Setup.bat").read_bytes()
PS1 = (ROOT / "deploy" / "install-otacon-expansion.ps1").read_bytes()
SH = (ROOT / "install_otacon_expansion.sh").read_text(encoding="utf-8")
FETCH = (ROOT / "deploy" / "bootstrap-fetch.ps1").read_text(encoding="utf-8", errors="replace")
BUILD = (ROOT / "deploy" / "build-release-manifest.py").read_text(encoding="utf-8")


def must(cond: bool, msg: str, fails: list[str]) -> None:
    if not cond:
        fails.append(msg)


def test_expansion_windows_installer_contracts():
    fails: list[str] = []

    must(BAT and not BAT.startswith(b"\xef\xbb\xbf"), "Setup bat has no UTF-8 BOM", fails)
    must(BAT.count(b"\n") == BAT.count(b"\r\n"), "Setup bat is CRLF", fails)
    must(b"crist" not in BAT.lower(), "Setup bat has no hardcoded crist", fails)
    must(b"C:\\Users\\crist" not in BAT and b"/home/crist" not in BAT, "Setup bat has no hardcoded home", fails)
    must(b"NOT ready yet" not in BAT and b"PLACEHOLDER" not in BAT, "Setup bat is not a placeholder", fails)
    must(b"install-otacon-expansion.ps1" in BAT, "Setup bat launches Expansion PS1", fails)
    must(b"bootstrap-fetch.ps1" in BAT, "Setup bat refreshes versioned bundle", fails)
    must(b"pause >nul" in BAT and b"exit /b" in BAT, "Setup bat stays open on failure", fails)

    must(PS1.startswith(b"\xef\xbb\xbf"), "Expansion PS1 has UTF-8 BOM", fails)
    ps1 = PS1[3:].decode("utf-8")
    must(ps1.count("\n") == ps1.count("\r\n"), "Expansion PS1 is CRLF", fails)
    must("crist" not in ps1.lower(), "Expansion PS1 has no hardcoded crist", fails)
    must("Invoke-OtaconWslBashFile" in ps1, "uses temp .sh WSL transport", fails)
    must("not bash -lc" in ps1.lower() or "bash -lc" not in ps1.replace("not bash -lc", ""),
         "does not use bash -lc transport", fails)
    # Stronger: no Invoke with bash -lc
    must("bash -lc $" not in ps1 and "bash -lc \"$bash\"" not in ps1,
         "no bash -lc script invocation", fails)
    must("expansion-installer.log" in ps1, "logs under OtaconsKeep Logs", fails)
    must("/api/expansion/status" in ps1, "verifies Expansion status API", fails)
    must("foundation_ready" in ps1 and "enabled" in ps1, "checks enabled+foundation_ready", fails)
    must("Aria" in ps1 and "Vector" in ps1 and "Ledger" in ps1, "expects public roster names", fails)
    must("Muse" in ps1 and "Sentry" in ps1, "expects full five-agent roster", fails)
    must("I found your existing Keep" in ps1, "OtaconSay UX present", fails)
    must("Resolve-Distro" in ps1 and "Get-CandidateDistros" in ps1, "dynamic distro discovery", fails)

    must("discover_core_root" in SH, "Linux installer discovers Core dynamically", fails)
    must("run_as_owner" in SH or "runuser" in SH, "Linux installer uses repo owner for git/python", fails)
    must("EXP_FOUNDATION_READY" in SH, "Linux installer emits foundation marker", fails)
    must("Aria" in SH and "Sentry" in SH, "Linux seeds public roster", fails)
    must("Albedo" not in SH and "Nazarick" not in SH, "no private IP personas in public installer", fails)

    must("OtaconExpansion-Setup.bat" in FETCH, "bootstrap-fetch includes Expansion Setup bat", fails)
    must("install-otacon-expansion.ps1" in FETCH, "bootstrap-fetch includes Expansion PS1", fails)
    must("install_otacon_expansion.sh" in FETCH, "bootstrap-fetch includes foundation sh", fails)
    must("OtaconExpansion-Setup.bat" in BUILD, "release manifest builder includes Expansion bat", fails)
    must("install-otacon-expansion.ps1" in BUILD, "release manifest builder includes Expansion PS1", fails)

    if fails:
        raise AssertionError("Expansion Windows installer contracts failed:\n- " + "\n- ".join(fails))


if __name__ == "__main__":
    test_expansion_windows_installer_contracts()
    print("OK expansion windows installer contracts")
