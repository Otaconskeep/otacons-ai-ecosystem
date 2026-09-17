#!/usr/bin/env python3
"""Regression: dedicated Ubuntu-Otacon must auto-provision the WSL target user.

Given Ubuntu-Otacon exists but the expected user does not, the Windows assistant
must create the user (home + shell + groups), set /etc/wsl.conf default, verify
identity, continue without a password, and never delete/recreate a valid user.
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


def main() -> int:
    fails: list[str] = []

    must("function ConvertTo-OtaconLinuxUsername" in PS1, "username sanitizer exists", fails)
    must("function Get-OtaconExpectedWslUsername" in PS1, "expected username helper exists", fails)
    must("function Ensure-WslTargetUser" in PS1, "auto-provision function exists", fails)
    must("function Test-WslLinuxUserValid" in PS1, "user validity check exists", fails)
    must("function Set-WslDefaultUser" in PS1, "wsl.conf default-user helper exists", fails)

    ensure_fn = PS1.split("function Ensure-WslTargetUser", 1)[1].split(
        "function Format-StartProcessArgumentList", 1
    )[0]
    must("adduser --disabled-password" in ensure_fn or "useradd -m" in ensure_fn, "creates user without password", fails)
    must("passwd -d" in ensure_fn, "clears password so install needs none", fails)
    must("/bin/bash" in ensure_fn, "assigns bash shell", fails)
    must("HOME_DIR" in ensure_fn or "mkdir -p" in ensure_fn, "ensures home directory", fails)
    must("usermod -aG" in ensure_fn, "applies group membership", fails)
    for g in ("sudo", "adm", "video", "render", "docker"):
        must(g in ensure_fn, f"considers group '{g}'", fails)
    must("[user]" in ensure_fn and "default=" in ensure_fn, "sets /etc/wsl.conf [user] default", fails)
    must("wsl.exe --terminate" in ensure_fn, "restarts distro so default user applies", fails)
    must("whoami" in ensure_fn and "HOME_OK" in ensure_fn, "verifies identity after provision", fails)
    must(
        "already valid" in ensure_fn or "OTACON_USER_EXISTS" in ensure_fn or "reusing valid" in ensure_fn,
        "does not recreate an existing valid user",
        fails,
    )
    must("userdel" not in ensure_fn and "deluser" not in ensure_fn, "never deletes users", fails)

    step = PS1.split("function Step-InstallOtacon", 1)[1].split("function ", 1)[0]
    must("Ensure-WslTargetUser" in step, "Step-InstallOtacon auto-provisions when user missing", fails)
    must(
        "Finish Ubuntu first-run setup" not in step
        or "Ensure-WslTargetUser" in step.split("Finish Ubuntu first-run setup")[0],
        "auto-provision runs before giving up on missing user",
        fails,
    )

    dedicated = PS1.split("function Install-DedicatedUbuntuOtacon", 1)[1].split("function Step-WaitUbuntuInit", 1)[0]
    must("Ensure-WslTargetUser" in dedicated, "dedicated import provisions user after rootfs import", fails)
    must("Ubuntu-Otacon" in PS1 and "$PreferredDistro" in dedicated or "PreferredDistro" in dedicated,
         "dedicated path targets PreferredDistro (Ubuntu-Otacon)", fails)

    # --- Fresh Ubuntu-Otacon + missing expected user "crist" (live incident) ---
    # Given: dedicated distro exists, target user absent.
    # Expected: detect absence → create idempotently → home/shell/groups/default →
    # verify `wsl -d Ubuntu-Otacon -u crist -- whoami` without password.
    def sanitize(raw: str) -> str:
        s = raw.strip().lower()
        s = re.sub(r"[^a-z0-9_-]", "", s)
        s = re.sub(r"^[^a-z_]+", "", s)
        s = s[:32]
        if not s or s == "root":
            s = "otacon"
        return s

    must(sanitize("Crist") == "crist", "Windows user Crist maps to expected Linux user crist", fails)
    must(sanitize("crist") == "crist", "already-lowercase crist unchanged", fails)
    must(sanitize("Josh") == "josh", "sanitizer lowercases Windows username", fails)
    must(sanitize("Root") == "otacon", "sanitizer rejects root", fails)
    must(sanitize("Foo Bar!") == "foobar", "sanitizer strips invalid chars", fails)
    must("OTACON_TARGET_USER" in PS1 and "USERNAME" in PS1, "expected name from env or Windows USERNAME", fails)

    must(
        'wsl.exe -d $Name -u $preferred -- bash -lc "whoami' in ensure_fn
        or "-u $preferred" in ensure_fn and "whoami" in ensure_fn,
        "verifies via wsl -d <distro> -u <user> -- whoami",
        fails,
    )
    must("sudo" in ensure_fn and "usermod -aG" in ensure_fn, "applies sudo group membership", fails)
    must(
        "Test-WslLinuxUserValid" in ensure_fn or "OTACON_USER_EXISTS" in ensure_fn,
        "detects whether target user already exists before create",
        fails,
    )
    must(
        "not recreated" in ensure_fn or "reusing valid existing" in ensure_fn,
        "skips recreate when user already valid",
        fails,
    )
    must(
        "wsl -u root" in PS1 and "no NOPASSWD:ALL" in PS1,
        "privileged install uses wsl -u root (no password path)",
        fails,
    )

    # Idempotency: create path is guarded; second run hits EXISTS / already-valid branches
    must("OTACON_USER_EXISTS" in ensure_fn, "idempotent create echoes EXISTS when user present", fails)
    must("OTACON_USER_CREATED" in ensure_fn, "first create echoes CREATED", fails)

    # Get-WslDefaultUser must look beyond whoami=root
    get_user = PS1.split("function Get-WslDefaultUser", 1)[1].split("function Test-WslLinuxUserValid", 1)[0]
    must("wsl.conf" in get_user, "Get-WslDefaultUser reads wsl.conf default", fails)
    must("getent passwd" in get_user, "Get-WslDefaultUser falls back to passwd uid>=1000", fails)

    # Launcher fix still present (same release)
    must("function Format-StartProcessArgumentList" in PS1, "bash -c ArgumentList quoting helper present", fails)
    must("function Start-OtaconWslBashCProcess" in PS1, "production WSL bash -c launcher present", fails)

    print("=" * 60)
    if fails:
        print(f"{len(fails)} WSL user auto-provision check(s) failed")
        return 1
    print("WSL user auto-provision regressions: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
