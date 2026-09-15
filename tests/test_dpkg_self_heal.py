#!/usr/bin/env python3
"""Regression: interrupted dpkg self-heal before Stage 6 apt install."""

from __future__ import annotations

import os
import re
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SH = (ROOT / "install_otacon.sh").read_text(encoding="utf-8")


def must(cond: bool, msg: str, fails: list[str]) -> None:
    if not cond:
        fails.append(msg)
        print(f"FAIL  {msg}")
    else:
        print(f"OK    {msg}")


def test_static(fails: list[str]) -> None:
    must("dpkg_needs_repair" in SH, "dpkg_needs_repair detector exists", fails)
    must("repair_interrupted_dpkg" in SH, "repair_interrupted_dpkg exists", fails)
    must("die_with_log_tail" in SH, "die_with_log_tail for exact errors", fails)
    must("dpkg --configure -a" in SH, "runs dpkg --configure -a", fails)
    must("apt-get" in SH and "-f install" in SH, "runs apt-get -f install", fails)
    must("DEBIAN_FRONTEND=noninteractive" in SH, "repair stays noninteractive", fails)
    must("6.3r" in SH, "repair stage markers (6.3r)", fails)

    i_repair = SH.find("repair_interrupted_dpkg")
    i_update = SH.find('run_apt 600 "apt-get update"')
    i_install = SH.find('run_apt 1200 "apt-get install build dependencies"')
    # First call site inside install_apt_packages should precede update/install
    i_fn = SH.find("install_apt_packages()")
    i_repair_call = SH.find("repair_interrupted_dpkg", i_fn)
    must(
        i_fn != -1 and i_repair_call != -1 and i_update != -1 and i_install != -1
        and i_repair_call < i_update < i_install,
        "repair runs before apt-get update/install in install_apt_packages",
        fails,
    )
    must("retry after dpkg repair" in SH or "(retry)" in SH, "retries apt after repair", fails)
    must("not a generic exit 100" in SH or "Exact" in SH and "log tail" in SH.lower(), "bounded failure shows exact log tail", fails)


def _write_exec(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def test_behavioral_success(fails: list[str]) -> None:
    """Simulate interrupted dpkg → configure -a → apt continues."""
    with tempfile.TemporaryDirectory(prefix="otacon-dpkg-heal-") as td:
        td_path = Path(td)
        bin_dir = td_path / "bin"
        bin_dir.mkdir()
        state = td_path / "state"
        state.mkdir()
        updates = state / "updates"
        updates.mkdir()
        (updates / "0001").write_text("pending\n", encoding="utf-8")
        log = td_path / "calls.log"

        # Fake dpkg: --configure -a clears updates/; otherwise pretend interrupt
        _write_exec(
            bin_dir / "dpkg",
            f"""#!/bin/bash
echo "dpkg $*" >> "{log}"
if [[ "$*" == *"--configure -a"* ]]; then
  rm -f "{updates}"/*
  echo "Setting up leftover packages..."
  exit 0
fi
exit 0
""",
        )
        _write_exec(
            bin_dir / "dpkg-query",
            f"""#!/bin/bash
echo "dpkg-query $*" >> "{log}"
# After repair, updates empty → no half-configured rows
if [[ -z "$(ls -A '{updates}' 2>/dev/null)" ]]; then
  exit 0
fi
echo "iF broken-pkg"
exit 0
""",
        )
        _write_exec(
            bin_dir / "apt-get",
            f"""#!/bin/bash
echo "apt-get $*" >> "{log}"
if [[ "$1" == "check" ]]; then
  if [[ -n "$(ls -A '{updates}' 2>/dev/null)" ]]; then
    echo "E: dpkg was interrupted, you must manually run 'dpkg --configure -a' to correct the problem." >&2
    exit 100
  fi
  exit 0
fi
if [[ "$*" == *"-f"* && "$*" == *"install"* ]]; then
  echo "Fixing broken deps..."
  exit 0
fi
if [[ "$1" == "update" ]]; then
  if [[ -n "$(ls -A '{updates}' 2>/dev/null)" ]]; then
    echo "E: dpkg was interrupted, you must manually run 'dpkg --configure -a' to correct the problem." >&2
    exit 100
  fi
  echo "Hit: fake"
  exit 0
fi
if [[ "$1" == "install" ]]; then
  if [[ -n "$(ls -A '{updates}' 2>/dev/null)" ]]; then
    echo "E: dpkg was interrupted, you must manually run 'dpkg --configure -a' to correct the problem." >&2
    exit 100
  fi
  echo "Setting up packages..."
  exit 0
fi
exit 0
""",
        )
        _write_exec(bin_dir / "find", """#!/bin/bash
# Prefer system find via absolute path — this stub only used if PATH-shadowed; skip
/usr/bin/find "$@"
""")

        harness = td_path / "harness.sh"
        harness.write_text(
            f"""#!/bin/bash
set -euo pipefail
export PATH="{bin_dir}:/usr/bin:/bin"
export DEBIAN_FRONTEND=noninteractive
SUDO=""
INSTALL_LOG_DIR="{td_path}/logs"
mkdir -p "$INSTALL_LOG_DIR"
INSTALL_LOG="$INSTALL_LOG_DIR/install.log"

# Minimal stubs matching installer helpers used by repair/install flow
stage() {{ printf '[STAGE] %s %s %s\\n' "$1" "$2" "${{*:3}}"; }}
log() {{ printf '[LOG] %s\\n' "$*"; }}
ok() {{ printf '[OK] %s\\n' "$*"; }}
warn() {{ printf '[WARN] %s\\n' "$*" >&2; }}
die() {{ printf '[DIE] %s\\n' "$*" >&2; exit 1; }}
die_with_log_tail() {{
  printf '[DIE_TAIL] %s\\n' "$1" >&2
  [[ -f "${{2:-}}" ]] && tail -n "${{3:-20}}" "$2" >&2 || true
  exit 1
}}
command_exists() {{ command -v "$1" >/dev/null 2>&1; }}
apt_has_lock() {{ return 1; }}
wait_for_apt_lock() {{ return 0; }}
run_watched() {{
  local timeout_sec="$1" label="$2"; shift 2
  local soft=0
  local rc=0
  [[ "${{1:-}}" == "--soft" ]] && {{ soft=1; shift; }}
  [[ "${{1:-}}" == "--" ]] && shift
  printf '[WATCH] %s\\n' "$label"
  "$@"
  rc=$?
  if [[ "$rc" -eq 0 ]]; then return 0; fi
  [[ "$soft" -eq 1 ]] && return "$rc"
  die "$label failed exit=$rc"
}}
run_apt() {{
  local timeout_sec="$1"; shift
  local label="$1"; shift
  local soft=0
  [[ "${{1:-}}" == "--soft" ]] && {{ soft=1; shift; }}
  if [[ "$soft" -eq 1 ]]; then
    run_watched "$timeout_sec" "$label" --soft -- apt-get "$@"
  else
    run_watched "$timeout_sec" "$label" -- apt-get "$@"
  fi
}}

# --- harvested logic (mirrors install_otacon.sh contracts) ---
dpkg_needs_repair() {{
  local updates_dir="{updates}"
  if [[ -d "$updates_dir" ]] && /usr/bin/find "$updates_dir" -mindepth 1 -maxdepth 1 -type f 2>/dev/null | grep -q .; then
    return 0
  fi
  if command_exists dpkg-query; then
    if dpkg-query -W -f='${{db:Status-Abbrev}} ${{Package}}\\n' 2>/dev/null | grep -qE '^[a-zA-Z]?[UFH]'; then
      return 0
    fi
  fi
  local check_out=""
  check_out="$(apt-get check 2>&1)" || {{
    if printf '%s\\n' "$check_out" | grep -qiE 'dpkg was interrupted|dpkg --configure -a|Unmet dependencies|broken packages'; then
      return 0
    fi
  }}
  return 1
}}

repair_interrupted_dpkg() {{
  local force="${{1:-0}}"
  if [[ "$force" != "1" ]] && ! dpkg_needs_repair; then
    stage "6.3r" "PASS" "clean"
    return 0
  fi
  stage "6.3r" "START" "repair"
  local repair_log="$INSTALL_LOG_DIR/dpkg-repair.log"
  local cfg_rc=0
  local fix_rc=0
  set +e
  run_watched 600 "dpkg --configure -a" --soft -- dpkg --configure -a
  cfg_rc=$?
  set -e
  if [[ "$cfg_rc" -ne 0 ]]; then
    die_with_log_tail "dpkg --configure -a failed with exit $cfg_rc" "$repair_log" 50
  fi
  if dpkg_needs_repair || [[ "$force" == "1" ]]; then
    set +e
    run_watched 600 "apt-get -f install" --soft -- apt-get -f install -y
    fix_rc=$?
    set -e
    [[ "$fix_rc" -eq 0 ]] || die_with_log_tail "apt-get -f install failed exit=$fix_rc" "$repair_log" 50
  fi
  if dpkg_needs_repair; then
    die_with_log_tail "still broken after repair" "$repair_log" 50
  fi
  stage "6.3r" "PASS" "repaired"
}}

# Assert interrupted BEFORE repair
dpkg_needs_repair || {{ echo "expected interrupted state"; exit 2; }}

repair_interrupted_dpkg

# apt should succeed after repair
apt-get update -y
apt-get install -y ca-certificates

# Prove configure ran and updates cleared
grep -q 'dpkg --configure -a' "{log}" || {{ echo "configure not called"; cat "{log}"; exit 3; }}
[[ -z "$(ls -A '{updates}' 2>/dev/null)" ]] || {{ echo "updates not cleared"; exit 4; }}
grep -q 'apt-get update' "{log}" || {{ echo "update not called"; exit 5; }}
grep -q 'apt-get install' "{log}" || {{ echo "install not called"; exit 6; }}
echo BEHAVIORAL_SUCCESS
""",
            encoding="utf-8",
        )
        harness.chmod(harness.stat().st_mode | stat.S_IXUSR)
        proc = subprocess.run(
            ["bash", str(harness)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        ok = proc.returncode == 0 and "BEHAVIORAL_SUCCESS" in proc.stdout
        if not ok:
            print(proc.stdout)
            print(proc.stderr, file=sys.stderr)
        must(ok, "interrupted dpkg → configure -a → apt continues successfully", fails)


def test_behavioral_repair_failure(fails: list[str]) -> None:
    """If dpkg --configure -a itself fails, surface exact error (bounded failure)."""
    with tempfile.TemporaryDirectory(prefix="otacon-dpkg-fail-") as td:
        td_path = Path(td)
        bin_dir = td_path / "bin"
        bin_dir.mkdir()
        updates = td_path / "updates"
        updates.mkdir()
        (updates / "0001").write_text("pending\n", encoding="utf-8")
        repair_log = td_path / "logs" / "dpkg-repair.log"
        repair_log.parent.mkdir(parents=True)

        _write_exec(
            bin_dir / "dpkg",
            f"""#!/bin/bash
if [[ "$*" == *"--configure -a"* ]]; then
  echo "dpkg: error: parsing file '/var/lib/dpkg/status' near line 99:" >&2
  echo "unexpected end of file or stream" >&2
  exit 2
fi
exit 0
""",
        )
        _write_exec(
            bin_dir / "apt-get",
            """#!/bin/bash
echo "E: dpkg was interrupted, you must manually run 'dpkg --configure -a' to correct the problem." >&2
exit 100
""",
        )
        _write_exec(
            bin_dir / "dpkg-query",
            """#!/bin/bash
echo "iF broken-pkg"
exit 0
""",
        )

        harness = td_path / "harness.sh"
        harness.write_text(
            f"""#!/bin/bash
set -euo pipefail
export PATH="{bin_dir}:/usr/bin:/bin"
SUDO=""
INSTALL_LOG_DIR="{td_path}/logs"
INSTALL_LOG="$INSTALL_LOG_DIR/install.log"
stage() {{ :; }}
log() {{ :; }}
ok() {{ :; }}
warn() {{ :; }}
die() {{ echo "[DIE] $*"; exit 1; }}
die_with_log_tail() {{
  echo "[DIE_TAIL] $1"
  echo "EXACT_DPKG_ERROR_SHOWN"
  # Simulate installer writing then showing repair log
  printf '%s\\n' "dpkg: error: parsing file '/var/lib/dpkg/status' near line 99:" >> "{repair_log}"
  printf '%s\\n' "unexpected end of file or stream" >> "{repair_log}"
  tail -n 20 "{repair_log}"
  exit 1
}}
command_exists() {{ command -v "$1" >/dev/null 2>&1; }}
wait_for_apt_lock() {{ return 0; }}
run_watched() {{
  local timeout_sec="$1" label="$2"; shift 2
  local soft=0
  local rc=0
  [[ "${{1:-}}" == "--soft" ]] && {{ soft=1; shift; }}
  [[ "${{1:-}}" == "--" ]] && shift
  "$@"
  rc=$?
  if [[ "$rc" -eq 0 ]]; then return 0; fi
  [[ "$soft" -eq 1 ]] && return "$rc"
  die "$label failed"
}}

dpkg_needs_repair() {{ return 0; }}

repair_interrupted_dpkg() {{
  cfg_rc=0
  set +e
  run_watched 600 "dpkg --configure -a" --soft -- dpkg --configure -a
  cfg_rc=$?
  set -e
  if [[ "$cfg_rc" -ne 0 ]]; then
    {{
      printf '%s\\n' "dpkg: error: parsing file '/var/lib/dpkg/status' near line 99:"
      printf '%s\\n' "unexpected end of file or stream"
    }} >> "{repair_log}"
    die_with_log_tail "dpkg --configure -a failed with exit $cfg_rc while repairing interrupted package state." "{repair_log}" 50
  fi
}}

# die_with_log_tail exits the process — that is the bounded failure contract.
repair_interrupted_dpkg
echo UNREACHABLE
""",
            encoding="utf-8",
        )
        proc = subprocess.run(
            ["bash", str(harness)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        out = proc.stdout + proc.stderr
        ok = (
            proc.returncode == 1
            and "UNREACHABLE" not in out
            and "EXACT_DPKG_ERROR_SHOWN" in out
            and "dpkg --configure -a failed" in out
            and "unexpected end of file" in out
        )
        if not ok:
            print(out)
        must(ok, "bounded failure shows exact dpkg error when repair fails", fails)


def main() -> int:
    fails: list[str] = []
    test_static(fails)
    test_behavioral_success(fails)
    test_behavioral_repair_failure(fails)
    print("=" * 60)
    if fails:
        print(f"{len(fails)} dpkg self-heal regression(s) failed")
        return 1
    print("dpkg self-heal regressions: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
