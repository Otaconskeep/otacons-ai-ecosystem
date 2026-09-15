#!/usr/bin/env python3
"""Detect CMD parenthesized-block traps in Windows .bat files.

Known CMD quirk: inside an IF/FOR (...) block, a ')' can close the block even
when it appears inside double quotes. Embedding PowerShell -Command strings
that contain ')' inside those blocks yields:
  ) was unexpected at this time.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def audit(path: Path) -> list[dict]:
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    lines = raw.decode("ascii", errors="replace").replace("\r\n", "\n").split("\n")
    issues: list[dict] = []
    depth = 0
    stack: list[tuple[int, str]] = []

    for lineno, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.upper().startswith("REM"):
            continue
        in_dq = False
        j = 0
        while j < len(line):
            ch = line[j]
            if ch == "^" and j + 1 < len(line):
                j += 2
                continue
            if ch == '"':
                in_dq = not in_dq
                j += 1
                continue
            if ch == "(":
                if in_dq and depth == 0:
                    j += 1
                    continue
                if not in_dq:
                    depth += 1
                    stack.append((lineno, stripped[:120]))
                j += 1
                continue
            if ch == ")":
                if in_dq and depth == 0:
                    j += 1
                    continue
                if in_dq and depth > 0:
                    issues.append(
                        {
                            "file": str(path.relative_to(ROOT)),
                            "line": lineno,
                            "kind": "PAREN_IN_QUOTES_INSIDE_BLOCK",
                            "block": stack[-1] if stack else None,
                            "text": stripped[:200],
                        }
                    )
                    depth -= 1
                    if stack:
                        stack.pop()
                    j += 1
                    continue
                if not in_dq:
                    if depth <= 0:
                        issues.append(
                            {
                                "file": str(path.relative_to(ROOT)),
                                "line": lineno,
                                "kind": "UNEXPECTED_CLOSE",
                                "block": None,
                                "text": stripped[:200],
                            }
                        )
                    else:
                        depth -= 1
                        if stack:
                            stack.pop()
                j += 1
                continue
            j += 1

    if depth:
        issues.append(
            {
                "file": str(path.relative_to(ROOT)),
                "line": len(lines),
                "kind": "UNBALANCED_EOF",
                "block": stack[-1] if stack else None,
                "text": f"depth={depth}",
            }
        )
    return issues


def main() -> int:
    bats = sorted(p for p in ROOT.rglob("*.bat") if ".git" not in p.parts)
    all_issues: list[dict] = []
    for path in bats:
        all_issues.extend(audit(path))
    if not all_issues:
        print("BAT CMD structural check PASS")
        return 0
    print("BAT CMD structural check FAIL")
    for iss in all_issues:
        print(f"  {iss['file']}:{iss['line']} [{iss['kind']}] {iss['text']}")
        if iss.get("block"):
            print(f"    block opened at {iss['block'][0]}: {iss['block'][1]}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
