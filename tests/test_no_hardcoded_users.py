#!/usr/bin/env python3
"""Hard-fail: production installer code must not embed user-specific literals.

Forbidden in production paths (deploy/, installer bats, install_otacon.sh, etc.):
  crist, xofyerg, C:\\Users\\, /home/crist, runuser -u crist, -u crist

Test fixtures under tests/ may include them only as explicit test data.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PRODUCTION_GLOBS = (
    "deploy/**/*.ps1",
    "deploy/**/*.bat",
    "deploy/**/*.cmd",
    "deploy/**/*.sh",
    "deploy/**/*.vbs",
    "OtaconsKeep-Setup.bat",
    "install_otacon.bat",
    "install_otacon.sh",
    "uninstall_otacon.bat",
    "Fix-Otacon-GPU.bat",
    "Reinstall-Otacon.bat",
    "installer/**/*.py",
)

# Patterns that must never appear in production installer code.
FORBIDDEN = [
    (re.compile(r"(?i)\bcrist\b"), "literal username 'crist'"),
    (re.compile(r"(?i)\bxofyerg\b"), "literal username 'xofyerg'"),
    (re.compile(r"(?i)C:\\\\Users\\"), r"hardcoded C:\Users\ path"),
    (re.compile(r"(?i)C:/Users/"), "hardcoded C:/Users/ path"),
    (re.compile(r"/home/crist\b"), "hardcoded /home/crist"),
    (re.compile(r"runuser\s+-u\s+crist\b"), "runuser -u crist"),
    (re.compile(r"(?<![A-Za-z0-9_-])-u\s+crist\b"), "-u crist"),
]


def iter_production_files() -> list[Path]:
    seen: set[Path] = set()
    out: list[Path] = []
    for pattern in PRODUCTION_GLOBS:
        for p in ROOT.glob(pattern):
            if not p.is_file():
                continue
            rp = p.resolve()
            if rp in seen:
                continue
            seen.add(rp)
            out.append(p)
    return sorted(out)


def main() -> int:
    fails: list[str] = []
    scanned = 0
    for path in iter_production_files():
        scanned += 1
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            fails.append(f"unreadable {path.relative_to(ROOT)}: {e}")
            continue
        rel = str(path.relative_to(ROOT)).replace("\\", "/")
        for rx, label in FORBIDDEN:
            for m in rx.finditer(text):
                # Allow comments that explicitly document the ban.
                line_start = text.rfind("\n", 0, m.start()) + 1
                line = text[line_start : text.find("\n", m.start())]
                if "must not" in line.lower() or "never assume" in line.lower() or "do not" in line.lower():
                    continue
                if "hardcoded" in line.lower() and ("forbid" in line.lower() or "ban" in line.lower()):
                    continue
                fails.append(f"{rel}: {label} at offset {m.start()}: {line.strip()[:120]}")

    print(f"Scanned {scanned} production installer file(s)")
    if fails:
        print(f"FAIL: {len(fails)} hardcoded-user literal(s)")
        for f in fails:
            print(f"  - {f}")
        return 1
    print("Hard-fail hardcoded-user scan: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
