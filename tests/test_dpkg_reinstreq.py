#!/usr/bin/env python3
"""Regression: reinst-required packages need an explicit reinstall, not just
dpkg --configure -a.

Reproduces a real report: a friend's machine (Josh, RTX 4090) hit
"1 not fully installed or removed" for libgraphite2-3:amd64, status
"install reinstreq half-installed". dpkg --configure -a and apt-get -f
install both exited 0 (nothing to configure/fix from their point of view --
dpkg deliberately skips reinst-required packages) yet the health check
correctly kept failing across both repair passes, because nothing was
actually reinstalling the package.

Also reproduces the accompanying bug: dpkg_primary_broken_package()'s old
Status-Abbrev regex only matched 2-character abbrevs (e.g. "iF"), so a
reinst-required package's 3-character abbrev ("iHR") was never matched,
and the failure report fell back to the generic "(see dpkg --audit /
half-state lines above)" text instead of naming the package -- even though
the health check itself, querying the same data differently, found it fine.
"""

from __future__ import annotations

import stat
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SH_PATH = ROOT / "install_otacon.sh"
SH = SH_PATH.read_text(encoding="utf-8")

FUNCTIONS = [
    "dpkg_primary_broken_package",
    "dpkg_reinstreq_packages",
    "dpkg_reinstall_reinstreq",
    "dpkg_check_audit",
    "dpkg_check_verify",
    "dpkg_check_apt_get_check",
    "dpkg_check_updates_dir",
    "dpkg_check_half_states",
    "dpkg_check_status_anomalies",
    "dpkg_check_pending_triggers",
    "dpkg_check_lock_state",
    "dpkg_health_report",
    "dpkg_needs_repair",
    "repair_interrupted_dpkg",
]


def extract_function(name: str) -> str:
    lines = SH.splitlines()
    start = None
    for i, line in enumerate(lines):
        if line.startswith(f"{name}()"):
            start = i
            break
    if start is None:
        raise AssertionError(f"function {name!r} not found in install_otacon.sh")
    for j in range(start + 1, len(lines)):
        if lines[j] == "}":
            return "\n".join(lines[start : j + 1])
    raise AssertionError(f"no closing brace found for function {name!r}")


def must(cond: bool, msg: str, fails: list[str]) -> None:
    if not cond:
        fails.append(msg)
        print(f"FAIL  {msg}")
    else:
        print(f"OK    {msg}")


def _write_exec(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _harness_prelude(install_log_dir: Path, bin_dir: Path) -> str:
    return f"""#!/bin/bash
set -euo pipefail
export PATH="{bin_dir}:/usr/bin:/bin"
export DEBIAN_FRONTEND=noninteractive
SUDO=""
INSTALL_LOG_DIR="{install_log_dir}"
mkdir -p "$INSTALL_LOG_DIR"
INSTALL_LOG="$INSTALL_LOG_DIR/install.log"

stage() {{ printf '[STAGE] %s %s %s\\n' "$1" "$2" "${{*:3}}"; }}
log() {{ printf '[LOG] %s\\n' "$*"; }}
ok() {{ printf '[OK] %s\\n' "$*"; }}
warn() {{ printf '[WARN] %s\\n' "$*" >&2; }}
die() {{ printf '[DIE] %s\\n' "$*" >&2; exit 1; }}
die_with_log_tail() {{
  printf '[DIE_TAIL] %s\\n' "$1" >&2
  [[ -f "${{2:-}}" ]] && tail -n "${{3:-20}}" "$2" >&2 || true
  exit "${{4:-1}}"
}}
command_exists() {{ command -v "$1" >/dev/null 2>&1; }}
wait_for_apt_lock() {{ return 0; }}
run_watched() {{
  local timeout_sec="$1" label="$2"; shift 2
  local soft=0 rc=0
  [[ "${{1:-}}" == "--soft" ]] && {{ soft=1; shift; }}
  [[ "${{1:-}}" == "--" ]] && shift
  printf '[WATCH] %s\\n' "$label"
  "$@"
  rc=$?
  if [[ "$rc" -eq 0 ]]; then return 0; fi
  [[ "$soft" -eq 1 ]] && return "$rc"
  die "$label failed exit=$rc"
}}
"""


def _real_functions() -> str:
    return "\n\n".join(extract_function(name) for name in FUNCTIONS)


def test_reinstreq_package_is_actually_repaired(fails: list[str]) -> None:
    """The exact reported case: libgraphite2-3 stuck reinst-required.
    A working fix must call apt-get install --reinstall for it and then
    report the health check as passing.
    """
    with tempfile.TemporaryDirectory(prefix="otacon-reinstreq-") as td:
        td_path = Path(td)
        bin_dir = td_path / "bin"
        bin_dir.mkdir()
        install_log_dir = td_path / "logs"
        state = td_path / "state"  # 'broken' while present, reinstall clears it
        state.write_text("broken\n", encoding="utf-8")
        reinstall_log = td_path / "reinstall_calls.log"

        _write_exec(bin_dir / "dpkg", """#!/bin/bash
if [[ "$*" == *"--configure -a"* ]]; then
  echo "Setting up libgraphite2-3:amd64 (1.3.14-1build2) ..."
  exit 0
fi
if [[ "$1" == "--audit" ]]; then
  if [[ -f "%s" ]]; then
    echo "The following packages are in a mess due to serious problems during"
    echo "installation.  They must be reinstalled for them (and any packages"
    echo "that depend on them) to function properly:"
    echo " libgraphite2-3:amd64 Font rendering engine for Complex Scripts -- library"
  fi
  exit 0
fi
if [[ "$1" == "--verify" ]]; then
  exit 0
fi
exit 0
""" % state)

        _write_exec(bin_dir / "dpkg-query", """#!/bin/bash
case "$*" in
  *'Triggers-Pending'*) exit 0 ;;
esac
if [[ -f "%s" ]]; then
  echo -e "install reinstreq half-installed\\tlibgraphite2-3"
fi
exit 0
""" % state)

        _write_exec(bin_dir / "apt-get", """#!/bin/bash
if [[ "$1" == "check" ]]; then
  exit 0
fi
if [[ "$1" == "install" && "$2" == "--reinstall" ]]; then
  shift 2
  echo "$*" >> "%s"
  rm -f "%s"
  echo "Setting up libgraphite2-3:amd64 (1.3.14-1build2) ..."
  exit 0
fi
if [[ "$*" == *"-f"* && "$*" == *"install"* ]]; then
  echo "Reading package lists..."
  echo "0 upgraded, 0 newly installed, 0 to remove and 194 not upgraded."
  if [[ -f "%s" ]]; then
    echo "1 not fully installed or removed."
  fi
  exit 0
fi
exit 0
""" % (reinstall_log, state, state))

        _write_exec(bin_dir / "fuser", "#!/bin/bash\nexit 1\n")

        real_src = _real_functions()

        harness = td_path / "harness.sh"
        harness.write_text(
            _harness_prelude(install_log_dir, bin_dir)
            + "\n"
            + real_src
            + """

repair_interrupted_dpkg
echo "REPAIR_RC=$?"
echo BEHAVIORAL_DONE
""",
            encoding="utf-8",
        )
        harness.chmod(harness.stat().st_mode | stat.S_IXUSR)
        proc = subprocess.run(["bash", str(harness)], capture_output=True, text=True, timeout=30)
        out = proc.stdout + proc.stderr

        ok = (
            proc.returncode == 0
            and "REPAIR_RC=0" in out
            and "6.3r PASS dpkg/apt package state repaired" in out
        )
        if not ok:
            print(out)
        must(ok, "reinstreq package is actually repaired via explicit reinstall, not just configure -a", fails)

        called_reinstall = reinstall_log.exists() and "libgraphite2-3" in reinstall_log.read_text(encoding="utf-8")
        must(called_reinstall, "apt-get install --reinstall was actually invoked for the named package", fails)


def test_broken_package_name_extracted_from_3char_abbrev(fails: list[str]) -> None:
    """dpkg_primary_broken_package must name a reinst-required package
    (3-char Status-Abbrev, e.g. "iHR") instead of falling back to the
    generic '(see dpkg --audit / half-state lines above)' text.
    """
    with tempfile.TemporaryDirectory(prefix="otacon-pkgname-") as td:
        td_path = Path(td)
        bin_dir = td_path / "bin"
        bin_dir.mkdir()

        _write_exec(bin_dir / "dpkg-query", """#!/bin/bash
echo -e "install reinstreq half-installed\\tlibgraphite2-3"
""")
        _write_exec(bin_dir / "dpkg", """#!/bin/bash
exit 0
""")

        script = f"""#!/bin/bash
set -euo pipefail
export PATH="{bin_dir}:/usr/bin:/bin"
SUDO=""
command_exists() {{ command -v "$1" >/dev/null 2>&1; }}
{extract_function('dpkg_primary_broken_package')}
dpkg_primary_broken_package
"""
        path = td_path / "check.sh"
        path.write_text(script, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)
        proc = subprocess.run(["bash", str(path)], capture_output=True, text=True, timeout=10)
        name = proc.stdout.strip()
        must(name == "libgraphite2-3", f"extracts 'libgraphite2-3' from a 3-char abbrev (got {name!r})", fails)


def main() -> int:
    fails: list[str] = []
    test_broken_package_name_extracted_from_3char_abbrev(fails)
    test_reinstreq_package_is_actually_repaired(fails)
    print("=" * 60)
    if fails:
        print(f"{len(fails)} dpkg reinstreq regression(s) failed")
        return 1
    print("dpkg reinstreq regressions: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
