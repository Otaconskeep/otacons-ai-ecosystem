#!/usr/bin/env bash
# Gate for publishing Windows installer bats.
# Must PASS before OtaconsKeep-Setup.bat is copied to the website.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "== encoding / BOM / CRLF / ASCII =="
python3 deploy/verify-bat-encoding.py

echo "== CMD structural paren traps =="
python3 deploy/verify-bat-cmd-syntax.py

echo "== PowerShell -Command argument boundaries =="
python3 deploy/verify-bat-ps-boundaries.py

echo "== website download copy must match ecosystem BAT =="
SITE_BAT="${SITE_BAT_PATH:-}"
if [[ -z "$SITE_BAT" && -f /root/otaconskeep-site/downloads/OtaconsKeep-Setup.bat ]]; then
  SITE_BAT=/root/otaconskeep-site/downloads/OtaconsKeep-Setup.bat
fi
if [[ "${SKIP_SITE_CHECK:-}" == "1" ]]; then
  echo "SKIP site identity check (SKIP_SITE_CHECK=1)"
elif [[ -n "$SITE_BAT" && -f "$SITE_BAT" ]]; then
  if ! cmp -s OtaconsKeep-Setup.bat "$SITE_BAT"; then
    echo "FAIL: $SITE_BAT differs from OtaconsKeep-Setup.bat"
    echo "Copy the validated BAT to the site downloads/ folder before publish."
    exit 1
  fi
  echo "OK site copy matches"
else
  echo "WARN: site BAT path not found; skipped identity check"
fi

echo "ALL WINDOWS INSTALLER VALIDATION CHECKS PASSED"
