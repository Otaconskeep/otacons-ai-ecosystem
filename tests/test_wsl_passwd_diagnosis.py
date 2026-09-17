#!/usr/bin/env python3
"""Regression: getent passwd diagnosis — UNKNOWN ≠ BROKEN.

Mirrors ConvertFrom-WslPasswdRecord / Get-WslLinuxUserDiagnosis contracts.
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


def fn_body(name: str, nxt: str) -> str:
    return PS1.split(f"function {name}", 1)[1].split(f"function {nxt}", 1)[0]


def convert_from_wsl_passwd_record(
    record: str,
    expected_user: str,
    home_exists: bool = False,
    home_checked: bool = False,
) -> dict:
    """Python mirror of ConvertFrom-WslPasswdRecord."""
    result = {
        "Status": "DIAGNOSTIC_ERROR",
        "Exists": False,
        "Uid": "",
        "Home": "",
        "Shell": "",
        "UidOk": False,
        "HomeOk": False,
        "ShellOk": False,
        "Ok": False,
        "DefectConfirmed": False,
        "FixableHome": False,
        "FixableShell": False,
        "Detail": "diagnostic_error",
    }
    if not expected_user:
        result["Detail"] = "missing_args"
        return result
    if expected_user == "root":
        result["Status"] = "ROOT_REJECTED"
        result["Detail"] = "root_rejected"
        return result
    line = (record or "").strip()
    if not line:
        result["Status"] = "NOT_FOUND"
        result["Detail"] = "not_found"
        return result
    if re.search(r"[\r\n]", line) or re.match(r"^(EXISTS|UID|HOME|SHELL)=", line) or line.count(":") < 6:
        result["Detail"] = "malformed_passwd_record"
        return result
    parts = line.split(":")
    if len(parts) < 7:
        result["Detail"] = "malformed_passwd_record"
        return result
    name, _pw, uid, _gid, _gecos, home, shell = parts[:7]
    if name != expected_user:
        result["Detail"] = "username_mismatch"
        return result
    result["Exists"] = True
    result["Uid"] = uid
    result["Home"] = home
    result["Shell"] = shell
    try:
        uid_num = int(uid)
        result["UidOk"] = uid_num != 0
    except ValueError:
        result["UidOk"] = False
    result["ShellOk"] = bool(shell.strip())
    home_nonempty = bool(home.strip())
    if not home_checked:
        result["Status"] = "PARSED"
        result["Detail"] = "home_check_pending"
        return result
    result["HomeOk"] = home_nonempty and home_exists
    if result["UidOk"] and result["HomeOk"] and result["ShellOk"]:
        result["Status"] = "VALID"
        result["Ok"] = True
        result["Detail"] = "ok"
        return result
    result["Status"] = "INVALID"
    result["DefectConfirmed"] = True
    bits = []
    if not result["UidOk"]:
        bits.append("uid")
    if not home_nonempty:
        bits.append("home_empty")
        result["FixableHome"] = True
    elif not home_exists:
        bits.append("home_missing")
        result["FixableHome"] = True
    if not result["ShellOk"]:
        bits.append("shell_empty")
        result["FixableShell"] = True
    result["Detail"] = ",".join(bits)
    return result


def main() -> int:
    fails: list[str] = []

    must("function ConvertFrom-WslPasswdRecord" in PS1, "passwd parser helper exists", fails)
    must("function Get-WslLinuxUserDiagnosis" in PS1, "diagnosis helper exists", fails)
    must("function ConvertTo-OtaconWslText" in PS1, "WSL text normalizer exists", fails)

    diag_fn = fn_body("Get-WslLinuxUserDiagnosis", "Get-WslEffectiveDefaultUser")
    must("--exec getent passwd" in diag_fn, "diagnosis uses wsl --exec getent passwd", fails)
    must("--exec test -d" in diag_fn, "home probe uses wsl --exec test -d", fails)
    must("-- bash -lc" not in diag_fn and "bash -lc" not in diag_fn, "diagnosis must NOT use bash -lc", fails)
    must("EXISTS=1" not in diag_fn, "legacy EXISTS=1 marker gone from diagnosis", fails)
    must("DIAGNOSTIC_ERROR" in diag_fn, "diagnosis can return DIAGNOSTIC_ERROR", fails)

    parse_fn = fn_body("ConvertFrom-WslPasswdRecord", "Test-WslLinuxUserValid")
    must("malformed_passwd_record" in parse_fn, "malformed output => DIAGNOSTIC_ERROR", fails)
    must("DefectConfirmed" in parse_fn, "positive defects flagged", fails)
    must("UNKNOWN" in PS1 or "DIAGNOSTIC_ERROR" in PS1, "UNKNOWN/DIAGNOSTIC_ERROR vocabulary present", fails)

    ensure_fn = fn_body("Ensure-WslTargetUser", "Format-StartProcessArgumentList")
    must("DIAGNOSTIC_ERROR" in ensure_fn, "Ensure handles DIAGNOSTIC_ERROR", fails)
    must("leaving your Linux account unchanged" in ensure_fn, "Otacon leaves account unchanged on UNKNOWN", fails)
    must("creating fallback user=otacon" not in ensure_fn, "no otacon fallback on diagnosis failure", fails)
    must("DefectConfirmed" in ensure_fn, "repair gated on DefectConfirmed", fails)
    must("passwd -d" not in ensure_fn, "Ensure never clears passwords", fails)

    repair_fn = fn_body("Repair-WslLinuxUser", "Ensure-WslTargetUser")
    must("refuse mutate on diagnostic_error" in repair_fn, "repair refuses DIAGNOSTIC_ERROR", fails)
    must("DefectConfirmed" in repair_fn, "repair requires confirmed defect", fails)
    must("passwd -d" not in repair_fn, "repair never clears passwords", fails)

    # --- Pure parser cases (machine-accurate passwd lines) ---
    crist = convert_from_wsl_passwd_record(
        "crist:x:1000:1000:OtaconsKeep:/home/crist:/bin/bash",
        "crist",
        home_exists=True,
        home_checked=True,
    )
    must(crist["Status"] == "VALID", "valid crist => VALID", fails)
    must(crist["Ok"] is True, "valid crist => Ok", fails)
    must(crist["Uid"] == "1000", "crist uid=1000", fails)
    must(crist["Home"] == "/home/crist", "crist home=/home/crist", fails)
    must(crist["Shell"] == "/bin/bash", "crist shell=/bin/bash", fails)
    must(crist["DefectConfirmed"] is False, "valid crist no defect", fails)

    otacon = convert_from_wsl_passwd_record(
        "otacon:x:1001:1001:OtaconsKeep:/home/otacon:/bin/bash",
        "otacon",
        home_exists=True,
        home_checked=True,
    )
    must(otacon["Status"] == "VALID", "valid otacon UID 1001 => VALID", fails)
    must(otacon["Uid"] == "1001", "otacon uid=1001", fails)

    root = convert_from_wsl_passwd_record("root:x:0:0:root:/root:/bin/bash", "root", True, True)
    must(root["Status"] == "ROOT_REJECTED", "root => INVALID/ROOT_REJECTED", fails)

    missing = convert_from_wsl_passwd_record("", "crist", False, True)
    must(missing["Status"] == "NOT_FOUND", "empty getent => NOT_FOUND", fails)

    mangled = convert_from_wsl_passwd_record(
        "EXISTS=1\nUID=\nHOME=SHELL=\nSHELL=",
        "crist",
        home_exists=False,
        home_checked=True,
    )
    must(mangled["Status"] == "DIAGNOSTIC_ERROR", "malformed KEY=VALUE blob => DIAGNOSTIC_ERROR", fails)
    must(mangled["DefectConfirmed"] is False, "malformed => NO confirmed defect / NO MUTATION", fails)
    must(mangled["Home"] != "SHELL=", "malformed must not set Home=SHELL=", fails)

    garbage = convert_from_wsl_passwd_record("not-a-passwd-line", "crist", False, True)
    must(garbage["Status"] == "DIAGNOSTIC_ERROR", "garbage line => DIAGNOSTIC_ERROR", fails)
    must(garbage["DefectConfirmed"] is False, "garbage => NO MUTATION", fails)

    # Confirmed fixable defect still allowed
    nohome = convert_from_wsl_passwd_record(
        "crist:x:1000:1000::/home/crist:/bin/bash",
        "crist",
        home_exists=False,
        home_checked=True,
    )
    must(nohome["Status"] == "INVALID", "missing home dir => INVALID", fails)
    must(nohome["DefectConfirmed"] is True and nohome["FixableHome"] is True, "missing home is fixable", fails)

    print("=" * 60)
    print("Simulated real diagnostic (crist passwd line):")
    print(f"  account.valid = {str(crist['Ok']).lower()}")
    print(f"  account.uid = {crist['Uid']}")
    print(f"  account.home = {crist['Home']}")
    print(f"  account.shell = {crist['Shell']}")
    print("  default_user = crist  # via wsl --exec id -un (separate B check)")
    print("=" * 60)

    if fails:
        print(f"{len(fails)} passwd-diagnosis check(s) failed")
        for f in fails:
            print(f"  - {f}")
        return 1
    print("passwd diagnosis regressions: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
