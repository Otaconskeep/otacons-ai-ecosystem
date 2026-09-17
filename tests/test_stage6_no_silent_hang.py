#!/usr/bin/env python3
"""Regression: Stage 6 must not silently hang; elevation via wsl -u root (no NOPASSWD:ALL)."""

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

    # --- Linux installer: phases + no permanent NOPASSWD:ALL ---
    must("OTACON_INSTALL_PHASE" in SH, "install phase env documented/used", fails)
    must("phase_privileged" in SH and "phase_finalize" in SH, "privileged + finalize phases exist", fails)
    must('INSTALL_PHASE" == "user"' in SH, "user phase branch exists", fails)
    must("wsl -u root" in SH, "documents wsl -u root elevation", fails)
    must("no sudoers changes were made" in SH, "privileged phase asserts no sudoers changes", fails)
    must("tee /etc/sudoers.d" not in SH, "installer must not write sudoers.d", fails)
    must("/etc/sudoers.d/otacon" not in SH, "installer must not create otacon sudoers drop-in", fails)
    must("Acquire::http::Timeout" in SH, "apt HTTP timeout configured", fails)
    must("DEBIAN_FRONTEND=noninteractive" in SH, "apt noninteractive", fails)
    must("NEEDRESTART_MODE" in SH, "needrestart noninteractive", fails)
    must("run_watched" in SH and "HEARTBEAT" in SH, "run_watched heartbeats exist", fails)
    must("[STAGE]" in SH or "stage()" in SH, "STAGE markers exist", fails)
    must('log "Checking Linux build dependencies"' in SH, "build-deps log line still present", fails)
    must("run_apt" in SH and "install_apt_packages" in SH, "run_apt / install_apt_packages used", fails)
    must("apt/dpkg lock" in SH.lower() or "wait_for_apt_lock" in SH, "apt lock wait/fail", fails)
    must(re.search(r"run_apt\s+600\s+\"apt-get update\"", SH) is not None, "apt-get update bounded", fails)
    must(re.search(r"run_apt\s+1200\s+\"apt-get install", SH) is not None, "apt-get install bounded", fails)
    must("repair_interrupted_dpkg" in SH and "dpkg --configure -a" in SH, "interrupted dpkg self-heal before apt", fails)
    must("ollama pull" in SH and "--soft" in SH, "ollama pull soft-watched", fails)
    must("SERVICE_DRAFT_NAME" in SH and "otacon.service.draft" in SH, "systemd unit draft for finalize", fails)
    must("user phase must not run as root" in SH, "user phase rejects root", fails)
    must("privileged phase requires root" in SH, "privileged requires root", fails)

    i_need = SH.find("NEED_PRIVILEGED_HELPER")
    i_apt = SH.find("install_apt_packages")
    must(i_need != -1 and i_apt != -1 and i_need < i_apt, "elevation decision precedes apt install helper", fails)

    # --- Windows: three-phase via wsl -u root; NO passwordless-sudo gate ---
    must("Ensure-WslPasswordlessSudo" not in PS1, "Windows must NOT require Ensure-WslPasswordlessSudo", fails)
    must("Test-WslPasswordlessSudo" not in PS1, "no passwordless-sudo preflight test", fails)
    must("sudoers.d/otacon" not in PS1, "no otacon sudoers drop-in guidance", fails)
    must("ALL=(ALL) NOPASSWD:ALL" not in PS1, "Windows must NOT instruct permanent NOPASSWD:ALL", fails)
    must("Invoke-WslInstallPhase" in PS1, "Windows phase runner exists", fails)
    must("Format-StartProcessArgumentList" in PS1, "Start-Process ArgumentList quoting helper exists", fails)
    must("Start-OtaconWslBashCProcess" in PS1, "production bash -c launcher quotes payload", fails)
    must('-Phase "privileged"' in PS1, "Windows runs privileged phase", fails)
    must('-Phase "user"' in PS1, "Windows runs user phase", fails)
    must('-Phase "finalize"' in PS1, "Windows runs finalize phase", fails)
    must('-AsUser "root"' in PS1, "Windows uses wsl -u root for privileged steps", fails)
    must("Get-WslDefaultUser" in PS1, "Windows resolves default WSL user for ownership", fails)
    must("Ensure-WslTargetUser" in PS1, "Windows auto-provisions missing WSL target user", fails)
    must("Show-Stage6Panel" in PS1, "Stage 6 substep panel", fails)
    must("stallTimeoutMin" in PS1 or "STALL" in PS1, "Stage 6 stall timeout", fails)
    must("overallTimeoutMin" in PS1 or "OVERALL" in PS1, "Stage 6 overall timeout", fails)
    must("phaseStarted" in PS1 and "phase-local clock" in PS1, "phase overall timeout uses phase-local clock not Stage 6 start", fails)
    must("STAGE" in PS1 and "-match" in PS1 and ("Current substep" in PS1 or "CURRENT :" in PS1 or "MISSION :" in PS1), "Windows UI parses STAGE markers", fails)
    must("Get-WindowsNvidiaName" in PS1 and "Get-WslNvidiaName" in PS1, "Windows+WSL GPU probe in Stage 6 UI", fails)
    must("last 50 log lines" in PS1 or "linux-install-tail.log" in PS1, "failure dumps last log lines", fails)
    must("Current substep" in PS1 or "CURRENT :" in PS1 or "MISSION :" in PS1, "UI shows current substep", fails)
    must("Show-OtaconProgressBar" in PS1, "Stage 6 has progress bar", fails)
    must("LIVE FEED" not in PS1, "Stage 6 does not dump live apt/test feed to user", fails)
    must("OTACON_CHAT_PORT" in PS1 and "IsNullOrWhiteSpace" in PS1, "blank OTACON_CHAT_PORT not injected", fails)

    print("=" * 60)
    if fails:
        print(f"{len(fails)} regression check(s) failed")
        return 1
    print("Stage-6 hang / elevation regressions: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
