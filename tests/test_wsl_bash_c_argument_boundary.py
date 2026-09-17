#!/usr/bin/env python3
"""Regression: Windows Start-Process must not split bash -c payloads.

Root cause of privileged-bootstrap stall/exit 125:
  Start-Process -ArgumentList <string[]> joins with spaces and does not quote
  tokens containing spaces/pipes/redirects/operators. WSL starts, bash never
  runs the installer, the exit marker stays empty, and the 25m stall watchdog
  returns synthetic 125.

This test proves the production quoting helper keeps the complete bash -c
payload as one argument, and that Invoke-WslInstallPhase uses that launcher
(stdout+stderr+exit marker) without raising the stall timeout.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PS1 = (ROOT / "deploy" / "windows-setup-assistant.ps1").read_text(encoding="utf-8")


def must(cond: bool, msg: str, fails: list[str]) -> None:
    if not cond:
        fails.append(msg)
        print(f"FAIL  {msg}")
    else:
        print(f"OK    {msg}")


def format_start_process_argument_list(arguments: list[str]) -> str:
    """Python twin of Format-StartProcessArgumentList (Windows CRT argv rules)."""
    parts: list[str] = []
    for arg in arguments:
        s = "" if arg is None else str(arg)
        if len(s) == 0:
            parts.append('""')
            continue
        if re.search(r'[\s"]', s):
            parts.append('"' + s.replace('"', '""') + '"')
        else:
            parts.append(s)
    return " ".join(parts)


def main() -> int:
    fails: list[str] = []

    must("function Format-StartProcessArgumentList" in PS1, "quoting helper exists", fails)
    must("function Start-OtaconWslBashCProcess" in PS1, "production WSL bash -c launcher exists", fails)
    must("function Test-OtaconWslBashCLauncher" in PS1, "harmless probe uses production launcher", fails)

    phase_fn = PS1.split("function Invoke-WslInstallPhase", 1)[1].split("function Step-InstallOtacon", 1)[0]
    launcher_fn = PS1.split("function Start-OtaconWslBashCProcess", 1)[1].split(
        "function Get-OtaconMergedLogLines", 1
    )[0]
    probe_fn = PS1.split("function Test-OtaconWslBashCLauncher", 1)[1].split(
        "function Invoke-WslInstallPhase", 1
    )[0]
    helper_fn = PS1.split("function Format-StartProcessArgumentList", 1)[1].split(
        "function Start-OtaconWslBashCProcess", 1
    )[0]

    must(
        "Start-OtaconWslBashCProcess" in phase_fn,
        "Invoke-WslInstallPhase uses Start-OtaconWslBashCProcess",
        fails,
    )
    must(
        "Format-StartProcessArgumentList" in launcher_fn,
        "Start-OtaconWslBashCProcess formats ArgumentList before Start-Process",
        fails,
    )
    must(
        re.search(
            r"Start-Process\s+-FilePath\s+\"wsl\.exe\"\s+-ArgumentList\s+\$argString",
            launcher_fn,
        )
        is not None,
        "Start-Process receives one pre-quoted ArgumentList string",
        fails,
    )
    must(
        re.search(
            r"Start-Process\s+-FilePath\s+\"wsl\.exe\"\s+-ArgumentList\s+\$argList\b",
            phase_fn,
        )
        is None,
        "Invoke-WslInstallPhase must not pass bare $argList array to Start-Process",
        fails,
    )

    must("RedirectStandardOutput" in launcher_fn, "stdout redirected", fails)
    must("RedirectStandardError" in launcher_fn, "stderr redirected", fails)
    must("2>&1" in phase_fn, "phase runner merges script stderr into captured stream", fails)
    must("emit_rc" in phase_fn and "EXIT_MARKER" in phase_fn, "phase script emits exit marker", fails)
    must(
        'printf \'\'%s\\n\'\' "$rc" > \'\'{1}\'\'' in phase_fn
        or ("printf ''%s\\n'' \"$rc\"" in phase_fn and "exitMarkerEsc" in phase_fn),
        "outer bash -c wrapper always writes exit marker",
        fails,
    )
    must(
        "[int]$StallTimeoutMin = 25" in PS1 or "$StallTimeoutMin = 25" in PS1,
        "stall watchdog remains 25 minutes (not raised to hide the bug)",
        fails,
    )
    must("$ProbeWslLauncher" in PS1 and "Test-OtaconWslBashCLauncher" in PS1, "probe switch exposed", fails)

    # --- Quoting boundary cases (spaces, pipes, redirects, operators) ---
    payload = (
        "set +e; echo hello world | tr a-z A-Z; bash '/mnt/c/Users/Test User/AppData/Local/OtaconsKeep/Logs/"
        "wsl-phase-privileged.sh' 2>&1; rc=$?; printf '%s\\n' \"$rc\" > "
        "'/mnt/c/Users/Test User/exit'; true && echo OK || echo BAD; exit \"$rc\""
    )
    must("|" in payload and "2>&1" in payload, "fixture includes pipe and redirect", fails)
    must("&&" in payload and "||" in payload and ";" in payload, "fixture includes shell operators", fails)
    must("/Test User/" in payload, "fixture includes path spaces", fails)

    # Demonstrate the bug shape: unquoted join lets the payload fracture after -c.
    naive = " ".join(["-d", "Ubuntu-Otacon", "-u", "root", "--", "bash", "-c", payload])
    must(
        naive.startswith("-d Ubuntu-Otacon -u root -- bash -c set +e;"),
        "naive Start-Process-style join fractures bash -c at the first space",
        fails,
    )

    quoted = format_start_process_argument_list(
        ["-d", "Ubuntu-Otacon", "-u", "root", "--", "bash", "-c", payload]
    )
    must(quoted.startswith("-d Ubuntu-Otacon -u root -- bash -c "), "safe tokens stay unquoted", fails)
    must(quoted.endswith('"' + payload.replace('"', '""') + '"'), "bash -c payload is one trailing quoted arg", fails)
    after_c = quoted.split(" -c ", 1)[1]
    must(after_c.startswith('"') and after_c.endswith('"'), "payload wrapper quotes present", fails)
    inner = after_c[1:-1].replace('""', '"')
    must(inner == payload, "quoted payload round-trips through CRT escaping", fails)
    must("/Test User/" in after_c, "path spaces preserved inside payload", fails)
    must("|" in after_c and "2>&1" in after_c and "&&" in after_c and "||" in after_c, "pipe/redirects/operators preserved inside payload", fails)

    must("Start-OtaconWslBashCProcess" in probe_fn, "probe calls exact production launcher", fails)
    must("| tr " in probe_fn or "tr a-z A-Z" in probe_fn, "probe includes pipe", fails)
    must(">&2" in probe_fn, "probe includes stderr redirect", fails)
    must("&&" in probe_fn, "probe includes shell operators", fails)
    must("HELLO WORLD" in probe_fn, "probe asserts stdout from piped command", fails)
    must("PROBE_ERR" in probe_fn, "probe asserts stderr capture", fails)
    must("expected nonzero" in probe_fn, "probe asserts nonzero failure exit", fails)

    must(".Replace('\"', '\"\"')" in helper_fn or '""' in helper_fn, "embedded quotes doubled", fails)
    must("-match" in helper_fn and '[\\s"]' in helper_fn, "whitespace/quote detection present", fails)

    print("=" * 60)
    if fails:
        print(f"{len(fails)} bash -c argument-boundary check(s) failed")
        return 1
    print("WSL bash -c argument-boundary regressions: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
