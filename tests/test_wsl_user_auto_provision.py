#!/usr/bin/env python3
"""Regression: WSL account validity (A) vs effective default-user (B).

Cases:
  1. missing user          → create only (passwordless new account OK)
  2. existing valid user   → do not recreate / do not clear password
  3. valid default user    → wsl -d Distro --exec id -un must equal target
  4. root rejected         → root is never a valid install account
  5. existing password preserved → no unconditional passwd -d on existing users
  6. invalid existing user → Repair-WslLinuxUser auto-fixes home/shell (no R/O/X)

A and B must remain separate failure states in Step-InstallOtacon.
Autopilot must repair before asking the user anything.
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


def main() -> int:
    fails: list[str] = []

    must("function Test-WslLinuxUserValid" in PS1, "A: Test-WslLinuxUserValid exists", fails)
    must("function Get-WslLinuxUserDiagnosis" in PS1, "A: Get-WslLinuxUserDiagnosis exists", fails)
    must("function ConvertFrom-WslPasswdRecord" in PS1, "A: ConvertFrom-WslPasswdRecord exists", fails)
    must("function Test-WslEffectiveDefaultUser" in PS1, "B: Test-WslEffectiveDefaultUser exists", fails)
    must("function Get-WslEffectiveDefaultUser" in PS1, "B: Get-WslEffectiveDefaultUser exists", fails)
    must("function New-WslLinuxUser" in PS1, "create-only helper exists", fails)
    must("function Repair-WslLinuxUser" in PS1, "6. Repair-WslLinuxUser exists", fails)
    must("function Ensure-WslTargetUser" in PS1, "Ensure-WslTargetUser exists", fails)

    valid_fn = fn_body("Test-WslLinuxUserValid", "Get-WslLinuxUserDiagnosis")
    must("Get-WslLinuxUserDiagnosis" in valid_fn, "A validity delegates to diagnosis", fails)
    must("--exec id -un" not in valid_fn, "A does not collapse into effective-default check", fails)

    diag_fn = fn_body("Get-WslLinuxUserDiagnosis", "Get-WslEffectiveDefaultUser")
    must("--exec getent passwd" in diag_fn, "A diagnosis uses getent passwd via --exec", fails)
    must("bash -lc" not in diag_fn, "A diagnosis does not use bash -lc", fails)
    must("DIAGNOSTIC_ERROR" in diag_fn, "A can return DIAGNOSTIC_ERROR", fails)
    must('User -eq "root"' in diag_fn or "$User -eq \"root\"" in diag_fn, "A rejects root", fails)

    parse_fn = fn_body("ConvertFrom-WslPasswdRecord", "Test-WslLinuxUserValid")
    must("UidOk" in parse_fn and "HomeOk" in parse_fn and "ShellOk" in parse_fn, "A parser covers uid/home/shell", fails)
    must("DefectConfirmed" in parse_fn, "A parser marks confirmed defects", fails)

    eff_get = fn_body("Get-WslEffectiveDefaultUser", "Test-WslEffectiveDefaultUser")
    must("--exec id -un" in eff_get, "B uses wsl -d <distro> --exec id -un", fails)

    eff_test = fn_body("Test-WslEffectiveDefaultUser", "Get-WslFirstNormalUser")
    must("Get-WslEffectiveDefaultUser" in eff_test, "B compares effective default to target", fails)

    new_fn = fn_body("New-WslLinuxUser", "Repair-WslLinuxUser")
    must("Test-WslUserExists" in new_fn, "1. missing-user path detects existence first", fails)
    must("refuse create" in new_fn or "already exists" in new_fn, "2. refuse create when user exists", fails)
    must("adduser --disabled-password" in new_fn or "useradd -m" in new_fn, "1. creates missing user", fails)
    must("OTACON_USER_CREATED" in new_fn, "1. create success marker", fails)
    must("/bin/bash" in new_fn, "assigns shell on create", fails)
    must("HOME_DIR" in new_fn, "creates/ensures home on create", fails)
    must("usermod -aG" in new_fn and "sudo" in new_fn, "applies sudo/groups on create", fails)

    repair_fn = fn_body("Repair-WslLinuxUser", "Ensure-WslTargetUser")
    must("OTACON_USER_REPAIRED" in repair_fn, "6. repair success marker", fails)
    must("mkdir -p" in repair_fn, "6. repair creates missing home", fails)
    must("/bin/bash" in repair_fn, "6. repair sets bash shell", fails)
    must("passwd -d" not in repair_fn, "6. repair never clears passwords", fails)
    must("I'm repairing it now" not in repair_fn, "repair helper stays low-level (narration in Ensure)", fails)

    # 5. password preservation: passwd -d only inside brand-new useradd branch, never after EXISTS
    passwd_lines = [ln for ln in new_fn.splitlines() if "passwd -d" in ln and "USER_NAME" in ln]
    must(len(passwd_lines) >= 1, "new accounts may clear password once at create", fails)
    after_exists = new_fn.split("OTACON_USER_EXISTS", 1)
    if len(after_exists) > 1:
        exists_exit_chunk = after_exists[1].split("fi", 1)[0]
        must("passwd -d" not in exists_exit_chunk, "5. no passwd -d on existing-user EXISTS path", fails)
    ensure_fn = fn_body("Ensure-WslTargetUser", "Format-StartProcessArgumentList")
    must("passwd -d" not in ensure_fn, "5. Ensure-WslTargetUser never clears passwords", fails)
    active_passwd = []
    for ln in PS1.splitlines():
        s = ln.strip()
        if "passwd -d" not in s:
            continue
        if s.startswith("#") or s.startswith("'#") or "Passwordless only" in s or "may be passwordless" in s:
            continue
        if s.startswith("'") and "passwd -d" in s and "USER_NAME" in s:
            active_passwd.append(s)
    must(len(active_passwd) == 1, "5. exactly one passwd -d (new useradd branch only)", fails)
    must(all("USER_NAME" in s for s in active_passwd), "5. passwd -d targets new USER_NAME only", fails)
    must("password untouched" in ensure_fn, "2. existing valid user password untouched", fails)
    must("not recreated" in ensure_fn or "ACCOUNT_VALID" in ensure_fn, "2. existing valid user not recreated", fails)
    must("ACCOUNT_MISSING" in ensure_fn, "1. missing user logged as ACCOUNT_MISSING", fails)
    must("ACCOUNT_INVALID" in ensure_fn and "Repair-WslLinuxUser" in ensure_fn, "6. invalid account triggers repair", fails)
    must("DefectConfirmed" in ensure_fn, "6. repair gated on confirmed defect", fails)
    must("creating fallback user=otacon" not in ensure_fn, "6. no otacon fallback from bad diagnosis", fails)
    must("leaving your Linux account unchanged" in ensure_fn, "6. UNKNOWN leaves account unchanged", fails)
    must("I'm repairing it now" in ensure_fn, "6. Otacon narrates auto-repair", fails)
    must("MaxRepairAttempts" in ensure_fn, "6. bounded repair attempts", fails)
    must("DEFAULT_OK" in ensure_fn and "DEFAULT_MISMATCH" in ensure_fn, "3. default-user state separate from account", fails)
    must("Get-WslEffectiveDefaultUser" in ensure_fn or "Test-WslEffectiveDefaultUser" in ensure_fn, "3. verifies effective default", fails)
    must("--exec id -un" in ensure_fn or "wsl --exec id -un" in ensure_fn, "3. default check references --exec id -un", fails)
    must("Back on track" in ensure_fn, "6. narrates recovery after repair", fails)
    must("Continuing - Stage 6 will retry" not in PS1, "must not soft-continue past broken account", fails)

    # 4. root rejected
    must(re.search(r'\$User -eq ["\']root["\']', diag_fn) is not None or "root_rejected" in parse_fn, "4. root rejected by account validity", fails)
    must(
        re.search(r'\$User -eq ["\']root["\']', eff_test) is not None
        or "root" in eff_test,
        "4. root rejected as effective default target",
        fails,
    )
    sanitize = fn_body("ConvertTo-OtaconLinuxUsername", "Get-OtaconSanitizedWindowsUsername")
    must('"root"' in sanitize and "otacon" in sanitize, "4. sanitizer maps root → otacon", fails)

    def sanitize_py(raw: str) -> str:
        s = raw.strip().lower()
        s = re.sub(r"[^a-z0-9_-]", "", s)
        s = re.sub(r"^[^a-z_]+", "", s)
        s = s[:32]
        if not s or s == "root":
            s = "otacon"
        return s

    must(sanitize_py("Crist") == "crist", "Crist → crist expected target", fails)
    must(sanitize_py("Alice Smith") == "alicesmith", "Alice Smith → alicesmith", fails)
    must(sanitize_py("John.Smith") == "johnsmith", "John.Smith → johnsmith", fails)
    must(sanitize_py("Root") == "otacon", "4. Root → otacon", fails)

    must("D_windows_derive" in ensure_fn, "D create path from Windows username", fails)
    must("B_effective" in ensure_fn, "B prefers effective id -un when valid", fails)
    must("C_getent" in ensure_fn, "C falls back to getent normal user", fails)
    must("Get-OtaconSanitizedWindowsUsername" in ensure_fn, "D uses sanitized Windows username", fails)

    # Step-InstallOtacon: separate A vs B failures (not one generic "no default user")
    step = PS1.split("function Step-InstallOtacon", 1)[1].split("function ", 1)[0]
    must("AccountValid" in step, "Step separates AccountValid (A)", fails)
    must("DefaultOk" in step, "Step separates DefaultOk (B)", fails)
    must("linux account invalid" in step, "A failure step label distinct", fails)
    must("default user mismatch" in step or "WSL default user mismatch" in step, "B failure step label distinct", fails)
    must("no default user" not in step, "must not collapse A/B into generic 'no default user'", fails)
    must("--exec id -un" in step, "B failure message cites --exec id -un", fails)
    must("password was not changed" in step or "password untouched" in ensure_fn, "5. messaging preserves existing password", fails)
    must("return 100" in step and "return 101" in step, "guided help maps retry/exit without double prompt", fails)

    # Guided failure UI (only after autopilot exhausted)
    help_fn = fn_body("Show-SetupNeedsHelp", "Register-ResumeAfterReboot")
    must("GUIDED RECOVERY" in help_fn or "couldn't repair this automatically" in help_fn, "guided failure copy", fails)
    must("Choice [R/O/X]" not in help_fn, "no R/O/X after autopilot", fails)
    must("ENTER" in help_fn and "Q" in help_fn, "ENTER retry / Q exit", fails)

    # EnsureGroups only for newly created accounts
    must("-EnsureGroups" in ensure_fn, "groups applied on new create path", fails)
    must("Ensure-WslEffectiveDefaultUser" in ensure_fn, "B fix uses default-only helper", fails)
    default_only = fn_body("Ensure-WslEffectiveDefaultUser", "New-WslLinuxUser")
    must("Set-WslDefaultUser" in default_only, "B default fix writes wsl.conf", fails)
    must("-EnsureGroups" not in default_only, "B default fix does not force group rewrite", fails)

    print("=" * 60)
    if fails:
        print(f"{len(fails)} WSL A/B user-state check(s) failed")
        for f in fails:
            print(f"  - {f}")
        return 1
    print("WSL account(A)/default(B) regressions: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
