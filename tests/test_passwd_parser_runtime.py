#!/usr/bin/env python3
"""Execute ConvertFrom-WslPasswdRecord in real PowerShell (not static text).

Also lints windows-setup-assistant.ps1 for assignments to automatic/read-only
variables that collide under PowerShell's case-insensitive names.
"""
from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSISTANT = ROOT / "deploy" / "windows-setup-assistant.ps1"
PWSH = Path("/opt/microsoft/powershell/7/pwsh")
if not PWSH.is_file():
    PWSH = Path("/usr/local/bin/pwsh")

# Automatic / read-only names that must not be assigned as locals.
# Do not include $null/$true/$false — idiomatic discards like `$null = Get-Command`.
FORBIDDEN_ASSIGN = {
    "home",  # collides with $HOME
    "pid",
    "host",
    "error",  # $Error automatic collection
    "args",
    "input",
    "matches",  # assigning $Matches = ... is unsafe; reading after -match is OK
    "psitem",
    "pwd",
    "shellid",
    "myinvocation",
    "psversiontable",
}


def must(cond: bool, msg: str, fails: list[str]) -> None:
    if not cond:
        fails.append(msg)
        print(f"FAIL  {msg}")
    else:
        print(f"OK    {msg}")


def extract_function(src: str, name: str) -> str:
    marker = f"function {name}"
    start = src.find(marker)
    if start < 0:
        raise RuntimeError(f"missing function {name}")
    # Next top-level function after this one
    nxt = re.search(r"\nfunction\s+[\w-]+", src[start + len(marker) :])
    end = start + len(marker) + nxt.start() if nxt else len(src)
    return src[start:end].strip() + "\n"


def lint_reserved_assignments(src: str, fails: list[str]) -> None:
    # Strip strings roughly to reduce false positives from bash payloads.
    # Keep it simple: flag `$name =` at statement start / after separators.
    assign_re = re.compile(
        r"(?i)(?:^|[;{\n])\s*\$(" + "|".join(FORBIDDEN_ASSIGN) + r")\s*=",
        re.M,
    )
    hits = []
    for m in assign_re.finditer(src):
        # Allow `$Matches[1]` reads — only assignments matched above.
        line_no = src.count("\n", 0, m.start()) + 1
        name = m.group(1)
        # Skip comment lines
        line = src.splitlines()[line_no - 1].lstrip()
        if line.startswith("#"):
            continue
        hits.append(f"line {line_no}: ${name} =")
    must(not hits, "no assignments to automatic/read-only locals " + (str(hits) if hits else ""), fails)
    # Explicit: the known crash pattern must be gone
    must(re.search(r"(?i)\$home\s*=", src) is None, "$home assignment fully removed", fails)
    must("$linuxHome" in src, "$linuxHome used instead", fails)
    must(re.search(r"Home\s*=\s*\$linuxHome", src) is not None, "property .Home still populated from $linuxHome", fails)


def run_pwsh_parser_test(src: str, fails: list[str]) -> None:
    if not PWSH.is_file():
        fails.append("pwsh not installed — cannot execute parser")
        print("FAIL  pwsh not installed — cannot execute parser")
        return

    # Drop BOM for extraction
    text = src
    if text.startswith("\ufeff"):
        text = text[1:]

    convert_text = extract_function(text, "ConvertTo-OtaconWslText")
    convert_passwd = extract_function(text, "ConvertFrom-WslPasswdRecord")

    harness = r"""
$ErrorActionPreference = 'Stop'
""" + convert_text + "\n" + convert_passwd + r"""

$record = 'crist:x:1000:1000::/home/crist:/bin/bash'
$r = ConvertFrom-WslPasswdRecord -Record $record -ExpectedUser 'crist' -HomeExists:$true -HomeChecked:$true
if ($r.Status -ne 'VALID') { throw "Status=$($r.Status) Detail=$($r.Detail)" }
if (-not $r.Ok) { throw 'Ok=false' }
if ($r.Uid -ne '1000') { throw "Uid=$($r.Uid)" }
if ($r.Home -ne '/home/crist') { throw "Home=$($r.Home)" }
if ($r.Shell -ne '/bin/bash') { throw "Shell=$($r.Shell)" }
# Prove assignment path does not throw on $HOME collision
$null = ConvertFrom-WslPasswdRecord -Record $record -ExpectedUser 'crist' -HomeExists:$true -HomeChecked:$true

$ot = ConvertFrom-WslPasswdRecord -Record 'otacon:x:1001:1001::/home/otacon:/bin/bash' -ExpectedUser 'otacon' -HomeExists:$true -HomeChecked:$true
if ($ot.Status -ne 'VALID' -or $ot.Uid -ne '1001') { throw "otacon status=$($ot.Status) uid=$($ot.Uid)" }

$bad = ConvertFrom-WslPasswdRecord -Record "EXISTS=1`nHOME=SHELL=" -ExpectedUser 'crist' -HomeExists:$false -HomeChecked:$true
if ($bad.Status -ne 'DIAGNOSTIC_ERROR') { throw "malformed status=$($bad.Status)" }
if ($bad.DefectConfirmed) { throw 'malformed must not confirm defect' }

Write-Output ("PASS name=crist uid={0} home={1} shell={2} valid={3}" -f $r.Uid, $r.Home, $r.Shell, $r.Ok)
"""

    with tempfile.NamedTemporaryFile("w", suffix=".ps1", delete=False, encoding="utf-8") as f:
        f.write(harness)
        path = f.name

    proc = subprocess.run(
        [str(PWSH), "-NoProfile", "-File", path],
        capture_output=True,
        text=True,
        timeout=60,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    must(proc.returncode == 0, f"pwsh parser exit 0 (got {proc.returncode}): {out.strip()[-500:]}", fails)
    must("uid=1000" in out and "home=/home/crist" in out and "shell=/bin/bash" in out,
         "pwsh output shows crist VALID fields", fails)
    must("Cannot overwrite variable HOME" not in out, "no HOME overwrite crash", fails)
    if proc.returncode == 0:
        print(out.strip())


def main() -> int:
    fails: list[str] = []
    raw = ASSISTANT.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        src = raw[3:].decode("utf-8")
    else:
        src = raw.decode("utf-8")

    lint_reserved_assignments(src, fails)
    run_pwsh_parser_test(src, fails)

    # Static contract still present
    must("function ConvertFrom-WslPasswdRecord" in src, "parser function present", fails)
    must("--exec getent passwd" in src, "getent --exec still used", fails)

    print("=" * 60)
    if fails:
        print(f"{len(fails)} check(s) failed")
        for f in fails:
            print(f"  - {f}")
        return 1
    print("passwd parser runtime + reserved-var lint: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
