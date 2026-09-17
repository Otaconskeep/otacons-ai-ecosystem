#!/usr/bin/env python3
"""Matrix + contract tests for dynamic Windows/Linux user resolution.

Covers:
  - sanitize matrix (Alice Smith → alicesmith, John.Smith → johnsmith, …)
  - A/B/C/D resolution order (state/explicit → effective → getent → create)
  - repo OWNER via stat + runuser (not assumed = WSL default)
  - home via getent field 6 (not /home/<name>)
  - keepalive paths from LOCALAPPDATA + Startup GetFolderPath
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PS1 = (ROOT / "deploy" / "windows-setup-assistant.ps1").read_text(encoding="utf-8")
WAKE_TASK = (ROOT / "deploy" / "install-wake-task.ps1").read_text(encoding="utf-8")
REPAIR = (ROOT / "deploy" / "repair-otacon-core.ps1").read_text(encoding="utf-8")
WAKE = (ROOT / "deploy" / "wake-otacon.ps1").read_text(encoding="utf-8")
GPU = (ROOT / "deploy" / "fix-otacon-gpu.ps1").read_text(encoding="utf-8")
LITE = (ROOT / "deploy" / "repair-lite-chat.ps1").read_text(encoding="utf-8")
INSTALL_SH = (ROOT / "install_otacon.sh").read_text(encoding="utf-8")


def must(cond: bool, msg: str, fails: list[str]) -> None:
    if not cond:
        fails.append(msg)
        print(f"FAIL  {msg}")
    else:
        print(f"OK    {msg}")


def sanitize_py(raw: str) -> str:
    s = raw.strip().lower()
    s = re.sub(r"[^a-z0-9_-]", "", s)
    s = re.sub(r"^[^a-z_]+", "", s)
    s = s[:32]
    if not s or s == "root":
        s = "otacon"
    return s


def fn_body(name: str, nxt: str) -> str:
    return PS1.split(f"function {name}", 1)[1].split(f"function {nxt}", 1)[0]


def main() -> int:
    fails: list[str] = []

    matrix = [
        ("crist", "crist"),
        ("Josh", "josh"),
        ("Alice Smith", "alicesmith"),
        ("John.Smith", "johnsmith"),
        ("xofyerg", "xofyerg"),
        ("Root", "otacon"),
        ("", "otacon"),
    ]
    for win, expect in matrix:
        got = sanitize_py(win)
        must(got == expect, f"sanitize Windows '{win}' → '{expect}' (got '{got}')", fails)

    # Distinct Linux users must remain possible when Windows name differs
    must(sanitize_py("Josh") != "block", "Josh sanitize is josh (block is existing Linux user via B/C)", fails)
    must(sanitize_py("Alice Smith") == "alicesmith", "Alice Smith → alicesmith create target", fails)

    must("function Get-OtaconSanitizedWindowsUsername" in PS1, "D helper Get-OtaconSanitizedWindowsUsername", fails)
    must("function Get-WslFirstNormalUser" in PS1, "C helper Get-WslFirstNormalUser", fails)

    ensure = fn_body("Ensure-WslTargetUser", "Format-StartProcessArgumentList")
    must("A_explicit" in ensure or "source = \"A_explicit\"" in ensure or 'source = "A_explicit"' in ensure,
         "Ensure logs A_explicit source", fails)
    must("B_effective" in ensure, "Ensure tries B effective default", fails)
    must("C_getent" in ensure, "Ensure tries C getent scan", fails)
    must("D_windows_derive" in ensure, "Ensure falls back to D Windows-derived create", fails)
    must("Get-OtaconSanitizedWindowsUsername" in ensure, "D uses Windows sanitize helper", fails)
    must("Get-WslFirstNormalUser" in ensure, "C uses Get-WslFirstNormalUser", fails)
    must("wsl_user" in ensure and "Get-InstallerState" in ensure, "A reads installer-state wsl_user", fails)
    must('ls -d /home/*/' not in ensure, "Ensure does not assume /home/*/ layout", fails)

    first = fn_body("Get-WslFirstNormalUser", "Get-WslDefaultUser")
    must("/home/" not in first or '~ /^\\/home\\//' not in first.replace("`", ""),
         "C scan must not require home under /home/", fails)
    must("65534" in first, "C rejects UID 65534", fails)
    must("nologin" in first, "C rejects nologin shells", fails)

    # Repo owner vs WSL default
    for label, blob in (("repair", REPAIR), ("wake", WAKE), ("gpu", GPU)):
        must("stat -c" in blob and "OWNER=" in blob, f"{label}: detects OWNER via stat", fails)
        must("runuser -u" in blob and "$OWNER" in blob, f"{label}: ops via runuser OWNER", fails)
        must("/home/${OWNER}" not in blob, f"{label}: no /home/${{OWNER}} assumption", fails)
        must("getent passwd" in blob, f"{label}: resolves homes via getent", fails)
        must("ls -d /home/*/" not in blob, f"{label}: no /home/*/otacon glob", fails)

    must("xofyerg" not in LITE, "repair-lite-chat.ps1 has no hardcoded xofyerg", fails)
    must("stat -c" in LITE and "getent passwd" in LITE, "repair-lite-chat resolves owner/home dynamically", fails)
    must("runuser -u" in LITE, "repair-lite-chat runs git as OWNER", fails)

    must("GetFolderPath(\"Startup\")" in WAKE_TASK or "GetFolderPath('Startup')" in WAKE_TASK
         or 'GetFolderPath("Startup")' in WAKE_TASK,
         "keepalive uses [Environment]::GetFolderPath(Startup)", fails)
    must("LOCALAPPDATA" in WAKE_TASK and "OtaconsKeep" in WAKE_TASK,
         "keepalive uses LOCALAPPDATA\\OtaconsKeep", fails)
    must("keep-ubuntu-awake.ps1" in WAKE_TASK, "keepalive script name keep-ubuntu-awake.ps1", fails)
    must("OtaconsKeep-KeepAlive.vbs" in WAKE_TASK, "Startup launcher OtaconsKeep-KeepAlive.vbs", fails)
    keep = (ROOT / "deploy" / "keep-ubuntu-awake.ps1").read_text(encoding="utf-8-sig")
    must("sleep infinity" in keep, "keepalive uses wsl --exec sleep infinity", fails)
    must("Mutex" in keep, "keepalive uses named mutex", fails)
    must(r"C:\Users\\" not in WAKE_TASK and "C:\\Users\\" not in WAKE_TASK,
         "install-wake-task has no C:\\Users\\ literal", fails)

    must("LOCALAPPDATA" in WAKE and "OtaconsKeep" in WAKE, "wake-otacon logs under LOCALAPPDATA\\OtaconsKeep", fails)

    # install_otacon.sh: getent home, no /home/ prefix requirement for candidate scan
    must("$6 ~ /^\\/home\\/" not in INSTALL_SH, "install_otacon.sh candidate scan not /home/-only", fails)
    must("getent passwd" in INSTALL_SH and "cut -d: -f6" in INSTALL_SH,
         "install_otacon.sh reads home from getent field 6", fails)

    print("=" * 60)
    if fails:
        print(f"{len(fails)} user-matrix / dynamic-path check(s) failed")
        for f in fails:
            print(f"  - {f}")
        return 1
    print("User matrix + dynamic path regressions: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
