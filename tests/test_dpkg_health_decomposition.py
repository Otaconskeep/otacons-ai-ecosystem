#!/usr/bin/env python3
"""Regression: decomposed dpkg/apt post-repair health check.

Reproduces the real report: dpkg --configure -a passes, apt-get -f install
passes (0 upgraded / 0 newly installed / 0 to remove), yet Stage 6.3r still
declared "package state still broken after repair". Root cause: the
updates-dir check treated ANY file under /var/lib/dpkg/updates as an active
interrupted-transaction fragment, when only pure-numeric filenames are
dpkg's real fragment-naming convention -- a stale/benign non-numeric file
was a false positive.

This test extracts the actual function bodies from install_otacon.sh (never
a hand-duplicated copy) so it can't silently drift from what ships.
"""

from __future__ import annotations

import re
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SH_PATH = ROOT / "install_otacon.sh"
SH = SH_PATH.read_text(encoding="utf-8")

FUNCTIONS = [
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
    """Pull `name() {` ... closing `}` (at column 0) verbatim out of the
    real script. Every function in this file closes on its own line with no
    leading whitespace, so this is exact, not approximate.
    """
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


def test_functions_exist(fails: list[str]) -> None:
    for name in FUNCTIONS:
        must(f"{name}()" in SH, f"{name} is defined in install_otacon.sh", fails)


def test_updates_dir_only_flags_numeric_fragments(fails: list[str]) -> None:
    must(
        re.search(r"\^\[0-9\]\+\$", SH) is not None
        or re.search(r"\^\[0-9\]+\$", SH) is not None,
        "updates-dir check matches pure-numeric filenames specifically",
        fails,
    )


def _write_exec(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _harness_prelude(td_path: Path, bin_dir: Path, install_log_dir: Path) -> str:
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
  exit 1
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
    # Real, unmodified function bodies -- but redirect the hardcoded
    # /var/lib/dpkg/updates path to a fake one via a shell variable the
    # extracted code doesn't know about, so we prefix each call site.
    src = "\n\n".join(extract_function(name) for name in FUNCTIONS)
    return src


def test_stale_non_numeric_file_is_not_a_false_positive(fails: list[str]) -> None:
    """The exact reported case: repair succeeds, a stale non-numeric file
    remains in updates/, and the installer must NOT report broken.
    """
    with tempfile.TemporaryDirectory(prefix="otacon-dpkg-health-") as td:
        td_path = Path(td)
        bin_dir = td_path / "bin"
        bin_dir.mkdir()
        updates = td_path / "var-lib-dpkg-updates"
        updates.mkdir()
        # Start genuinely interrupted: a real numbered fragment present.
        (updates / "0001").write_text("pending\n", encoding="utf-8")
        install_log_dir = td_path / "logs"
        repair_state = td_path / "repaired.flag"

        _write_exec(
            bin_dir / "dpkg",
            f"""#!/bin/bash
if [[ "$*" == *"--configure -a"* ]]; then
  # Real repair clears the numbered fragment but leaves a stale,
  # non-numeric artifact behind -- this is the reported scenario.
  rm -f "{updates}"/0*
  touch "{updates}/.dpkg-tmp-leftover"
  touch "{repair_state}"
  echo "Setting up leftover packages..."
  exit 0
fi
if [[ "$1" == "--audit" ]]; then
  exit 0
fi
if [[ "$1" == "--verify" ]]; then
  exit 0
fi
exit 0
""",
        )
        _write_exec(
            bin_dir / "dpkg-query",
            """#!/bin/bash
# Clean on every call: no half-states, no anomalies, no pending triggers.
exit 0
""",
        )
        _write_exec(
            bin_dir / "apt-get",
            f"""#!/bin/bash
if [[ "$1" == "check" ]]; then
  if [[ -f "{repair_state}" ]]; then
    exit 0
  fi
  echo "E: dpkg was interrupted, you must manually run 'dpkg --configure -a' to correct the problem." >&2
  exit 100
fi
if [[ "$*" == *"-f"* && "$*" == *"install"* ]]; then
  echo "Reading package lists..."
  echo "0 upgraded, 0 newly installed, 0 to remove and 0 not upgraded."
  exit 0
fi
exit 0
""",
        )
        _write_exec(
            bin_dir / "fuser",
            """#!/bin/bash
exit 1
""",
        )

        # Extract the real functions, then shadow the hardcoded path with a
        # wrapper that swaps in our fake updates dir for this test only.
        real_src = _real_functions()
        real_src = real_src.replace('local updates_dir="/var/lib/dpkg/updates"', f'local updates_dir="{updates}"')

        harness = td_path / "harness.sh"
        harness.write_text(
            _harness_prelude(td_path, bin_dir, install_log_dir)
            + "\n"
            + real_src
            + f"""

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
            and "BEHAVIORAL_DONE" in out
            and "REPAIR_RC=0" in out
            and "6.3r PASS dpkg/apt package state repaired" in out
        )
        if not ok:
            print(out)
        must(ok, "stale non-numeric file in updates/ does not cause a false 'still broken' verdict", fails)
        must(
            ".dpkg-tmp-leftover" in out and "not a pending-transaction signal" in out,
            "the stale file is named explicitly and explained, not silently ignored",
            fails,
        )


def test_genuine_numeric_fragment_still_fails(fails: list[str]) -> None:
    """Guard against over-correcting: a REAL leftover numbered fragment
    (genuine unresolved interruption) must still fail, twice, then die.
    """
    with tempfile.TemporaryDirectory(prefix="otacon-dpkg-genuine-") as td:
        td_path = Path(td)
        bin_dir = td_path / "bin"
        bin_dir.mkdir()
        updates = td_path / "var-lib-dpkg-updates"
        updates.mkdir()
        (updates / "0007").write_text("pending\n", encoding="utf-8")
        install_log_dir = td_path / "logs"

        _write_exec(
            bin_dir / "dpkg",
            f"""#!/bin/bash
if [[ "$*" == *"--configure -a"* ]]; then
  # Never actually clears the fragment -- genuinely still interrupted.
  echo "Setting up leftover packages..."
  exit 0
fi
exit 0
""",
        )
        _write_exec(
            bin_dir / "dpkg-query",
            """#!/bin/bash
exit 0
""",
        )
        _write_exec(
            bin_dir / "apt-get",
            f"""#!/bin/bash
if [[ "$1" == "check" ]]; then
  if [[ -n "$(ls -A '{updates}' 2>/dev/null)" ]]; then
    echo "E: dpkg was interrupted, you must manually run 'dpkg --configure -a' to correct the problem." >&2
    exit 100
  fi
  exit 0
fi
if [[ "$*" == *"-f"* && "$*" == *"install"* ]]; then
  exit 0
fi
exit 0
""",
        )
        _write_exec(bin_dir / "fuser", "#!/bin/bash\nexit 1\n")

        real_src = _real_functions()
        real_src = real_src.replace('local updates_dir="/var/lib/dpkg/updates"', f'local updates_dir="{updates}"')

        harness = td_path / "harness.sh"
        harness.write_text(
            _harness_prelude(td_path, bin_dir, install_log_dir)
            + "\n"
            + real_src
            + """

repair_interrupted_dpkg
echo UNREACHABLE
""",
            encoding="utf-8",
        )
        harness.chmod(harness.stat().st_mode | stat.S_IXUSR)
        proc = subprocess.run(["bash", str(harness)], capture_output=True, text=True, timeout=30)
        out = proc.stdout + proc.stderr

        ok = (
            proc.returncode == 1
            and "UNREACHABLE" not in out
            and out.count("Post-repair health check") == 2
            and "still reports an interrupted or broken package state after two automatic repair passes" in out
        )
        if not ok:
            print(out)
        must(ok, "a genuinely unresolved numeric fragment still fails after two bounded repair passes", fails)


def main() -> int:
    fails: list[str] = []
    test_functions_exist(fails)
    test_updates_dir_only_flags_numeric_fragments(fails)
    test_stale_non_numeric_file_is_not_a_false_positive(fails)
    test_genuine_numeric_fragment_still_fails(fails)
    print("=" * 60)
    if fails:
        print(f"{len(fails)} dpkg health decomposition regression(s) failed")
        return 1
    print("dpkg health decomposition regressions: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
