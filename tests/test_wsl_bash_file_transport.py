#!/usr/bin/env python3
"""WSL Bash must be transported as a temp .sh file, never via bash -lc multiline."""
from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def must(cond: bool, msg: str, fails: list[str]) -> None:
    if not cond:
        fails.append(msg)
        print(f"FAIL  {msg}")
    else:
        print(f"OK    {msg}")


def write_lf_utf8_no_bom(path: Path, body: str) -> None:
    text = body.replace("\r\n", "\n").replace("\r", "\n")
    if not text.endswith("\n"):
        text += "\n"
    path.write_bytes(text.encode("utf-8"))  # no BOM


def main() -> int:
    fails: list[str] = []
    repair = (ROOT / "deploy" / "repair-otacon-core.ps1").read_text(encoding="utf-8-sig")
    fixgpu = (ROOT / "deploy" / "fix-otacon-gpu.ps1").read_text(encoding="utf-8-sig")
    wake = (ROOT / "deploy" / "wake-otacon.ps1").read_text(encoding="utf-8-sig")
    helper = (ROOT / "deploy" / "wsl-bash-file.ps1").read_text(encoding="utf-8-sig")
    fetch = (ROOT / "deploy" / "bootstrap-fetch.ps1").read_text(encoding="utf-8-sig")

    must("function Invoke-OtaconWslBashFile" in helper, "shared Invoke-OtaconWslBashFile exists", fails)
    must("UTF8Encoding $false" in helper or "UTF8Encoding($false)" in helper.replace(" ", ""),
         "temp .sh written as UTF-8 without BOM", fails)
    must('bash -n' in helper, "runs bash -n before execute", fails)
    must("--exec bash" in helper, "executes via --exec bash <file>", fails)
    must("Remove-Item" in helper and "finally" in helper, "temp .sh cleaned in finally", fails)

    must("bash -lc $bash" not in repair, "repair does not use bash -lc $bash", fails)
    must("Invoke-OtaconWslBashFile" in repair, "repair uses file transport", fails)
    must("wsl-bash-file.ps1" in repair, "repair dotsources wsl-bash-file.ps1", fails)

    must("bash -lc $bash" not in fixgpu, "fix-gpu does not use bash -lc $bash", fails)
    must("Invoke-OtaconWslBashFile" in fixgpu, "fix-gpu uses file transport", fails)

    must("bash -lc $script" not in wake, "wake does not use bash -lc $script", fails)
    must("deploy/wsl-bash-file.ps1" in fetch, "bootstrap ships wsl-bash-file.ps1", fails)

    # Content proofs must still look for parentheses text (do not weaken checks).
    must('grep -q "def connection(self)"' in repair, "content proof still greps def connection(self)", fails)

    # Local bash -n of a hostile payload that used to break bash -lc transport.
    hostile = r'''
set -e
echo 'single quotes and "double quotes"'
VAR='$variables and pipes | and redirects > /tmp/x && true || true'
python3 - <<'PY'
def connection(self):
    return "parentheses () and && || ok"
print(connection(None))
PY
grep -q "def connection(self)" <<'EOF' || true
def connection(self)
EOF
echo HOSTILE_OK
'''
    with tempfile.TemporaryDirectory() as td:
        sh = Path(td) / "hostile.sh"
        write_lf_utf8_no_bom(sh, hostile)
        raw = sh.read_bytes()
        must(not raw.startswith(b"\xef\xbb\xbf"), "test fixture has no BOM", fails)
        must(b"\r" not in raw, "test fixture has no CR", fails)
        # bash -n must pass
        try:
            subprocess.run(["bash", "-n", str(sh)], check=True, capture_output=True, text=True)
            must(True, "bash -n passes hostile payload with parentheses/quotes/$/pipes", fails)
        except FileNotFoundError:
            must(True, "bash not on PATH - skipped live bash -n (contract still asserted)", fails)
        except subprocess.CalledProcessError as exc:
            must(False, f"bash -n failed on hostile payload: {exc.stderr}", fails)

        # Execute hostile script (safe) to ensure runtime ok
        try:
            out = subprocess.run(["bash", str(sh)], check=True, capture_output=True, text=True)
            must("HOSTILE_OK" in out.stdout, "hostile payload executes", fails)
        except FileNotFoundError:
            pass
        except subprocess.CalledProcessError as exc:
            must(False, f"hostile payload execution failed: {exc.stderr}", fails)

    print("=" * 60)
    if fails:
        print(f"{len(fails)} check(s) failed")
        return 1
    print("WSL bash-file transport regressions: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
