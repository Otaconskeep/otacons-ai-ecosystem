#!/usr/bin/env python3
"""Fail if BAT files append paths after powershell -Command.

powershell.exe treats tokens after -Command as part of the command text
(not reliable $args). Paths like OtaconsKeep-Setup (1).bat then parse as code.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BOM = b"\xef\xbb\xbf"


def logical_commands(text: str) -> list[tuple[int, str]]:
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    out: list[tuple[int, str]] = []
    buf: list[str] = []
    start = 1
    for i, line in enumerate(lines, 1):
        if not buf:
            start = i
        stripped = line.rstrip()
        if stripped.endswith("^"):
            buf.append(stripped[:-1])
            continue
        buf.append(line)
        out.append((start, "\n".join(buf)))
        buf = []
    if buf:
        out.append((start, "\n".join(buf)))
    return out


def check(path: Path) -> list[str]:
    raw = path.read_bytes()
    if raw.startswith(BOM):
        raw = raw[3:]
    text = raw.decode("ascii", errors="replace")
    errs: list[str] = []
    for start, cmd in logical_commands(text):
        code_lines = []
        for line in cmd.split("\n"):
            s = line.lstrip()
            if s.upper().startswith("REM ") or s.upper() == "REM":
                continue
            code_lines.append(line)
        cmd = "\n".join(code_lines)
        if not cmd.strip():
            continue
        if "powershell" not in cmd.lower():
            continue
        if not re.search(r"(?i)-Command\b", cmd):
            continue
        if re.search(r"(?i)%~f0|%~dpnx0|%~nx0|%~0\b", cmd):
            errs.append(
                f"{path.name}:{start}: powershell -Command must not include %~f0 "
                f"(path becomes script text). Use -File helper.ps1 -Path \"%~f0\" "
                f"or $env:VAR with no trailing args."
            )
        flat = cmd.replace("\n", " ")
        if re.search(r'(?i)-Command\s+"[^"]*"\s+"[A-Za-z]:\\', flat):
            errs.append(
                f"{path.name}:{start}: powershell -Command has a trailing path argument; "
                f"use -File or env var instead."
            )
    return errs


def main() -> int:
    bats = sorted(p for p in ROOT.rglob("*.bat") if ".git" not in p.parts)
    bad: list[str] = []
    for p in bats:
        bad.extend(check(p))
    if bad:
        print("BAT PowerShell argument-boundary check FAIL")
        for e in bad:
            print(" ", e)
        return 1
    print("BAT PowerShell argument-boundary check PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
