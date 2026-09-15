#!/usr/bin/env python3
"""Regression: Stage 6 must not silently hang (sudo/apt/progress markers)."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SH = (ROOT / "install_otacon.sh").read_text(encoding="utf-8")
PS1 = (ROOT / "deploy" / "windows-setup-assistant.ps1").read_text(encoding="utf-8")


def must(cond: bool, msg: str, fails: list[str]) -> None:
    if not cond:
        fails.append(msg)
        print(f"FAIL  {msg}")
    else:
        print(f"OK    {msg}")


def main() -> int:
    fails: list[str] = []

    must("$SUDO -n" in SH or "sudo -n" in SH or "-n true" in SH, "install_otacon.sh uses sudo -n / passwordless check", fails)
    must("passwordless sudo" in SH.lower() or "NOPASSWD" in SH, "clear passwordless sudo failure guidance", fails)
    must("Acquire::http::Timeout" in SH, "apt HTTP timeout configured", fails)
    must("DEBIAN_FRONTEND=noninteractive" in SH, "apt noninteractive", fails)
    must("NEEDRESTART_MODE" in SH, "needrestart noninteractive", fails)
    must("run_watched" in SH and "HEARTBEAT" in SH, "run_watched heartbeats exist", fails)
    must("[STAGE]" in SH or "stage()" in SH, "STAGE markers exist", fails)
    must('log "Checking Linux build dependencies"' in SH, "build-deps log line still present", fails)
    must("run_apt" in SH, "run_apt wrapper used", fails)
    must("apt/dpkg lock" in SH.lower() or "wait_for_apt_lock" in SH, "apt lock wait/fail", fails)
    must(re.search(r"run_apt\s+600\s+\"apt-get update\"", SH) is not None, "apt-get update bounded", fails)
    must(re.search(r"run_apt\s+1200\s+\"apt-get install", SH) is not None, "apt-get install bounded", fails)
    must("ollama pull" in SH and "--soft" in SH, "ollama pull soft-watched", fails)

    must("Ensure-WslPasswordlessSudo" in PS1, "Windows preflight for passwordless sudo", fails)
    must("Show-Stage6Panel" in PS1, "Stage 6 substep panel", fails)
    must("stallTimeoutMin" in PS1 or "STALL" in PS1, "Stage 6 stall timeout", fails)
    must("overallTimeoutMin" in PS1 or "OVERALL" in PS1, "Stage 6 overall timeout", fails)
    must("STAGE" in PS1 and "-match" in PS1 and "Current substep" in PS1, "Windows UI parses STAGE markers", fails)
    must("Get-WindowsNvidiaName" in PS1 and "Get-WslNvidiaName" in PS1, "Windows+WSL GPU probe in Stage 6 UI", fails)
    must("last 50 log lines" in PS1, "failure dumps last log lines", fails)
    # Must not rely only on vague STILL WORKING without substep plumbing
    must("Current substep" in PS1, "UI shows current substep", fails)

    # Ordering: passwordless gate must run before apt install wrapper calls
    i_gate = SH.find('Verifying passwordless sudo')
    i_apt_log = SH.find('log "Checking Linux build dependencies"')
    i_runapt = SH.find('run_apt 600')
    must(i_gate != -1 and i_apt_log != -1 and i_runapt != -1 and i_gate < i_apt_log < i_runapt,
         "passwordless sudo check precedes apt build-deps", fails)

    print("=" * 60)
    if fails:
        print(f"{len(fails)} regression check(s) failed")
        return 1
    print("Stage-6 hang regressions: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
