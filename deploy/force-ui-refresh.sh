#!/usr/bin/env bash
# Force-pull Lite UI + restart so Command Center / Codec actually load.
set -euo pipefail
INSTALL_DIR="${OTACON_INSTALL_DIR:-$HOME/otacon-ai-ecosystem}"
cd "$INSTALL_DIR"
echo "repo before: $(git rev-parse --short HEAD 2>/dev/null || echo none)"
git fetch --prune origin
git pull --ff-only || git reset --hard origin/main
echo "repo after : $(git rev-parse --short HEAD)"
echo "--- files ---"
ls -la ui/index.html ui/home.css ui/codec.css ui/wizard.js
echo "--- index title ---"
grep -E 'Command Center|home.css' ui/index.html | head -5
echo "--- restarting otacon ---"
if wsl.exe -u root -- systemctl restart otacon 2>/dev/null; then
  echo "restarted via wsl root"
elif command -v systemctl >/dev/null && [[ "$(id -u)" -eq 0 ]]; then
  systemctl restart otacon
else
  pkill -f 'installer.server' 2>/dev/null || true
  sleep 1
  nohup env PYTHONPATH="$INSTALL_DIR" OTACON_PORT=5757 \
    "$INSTALL_DIR/.venv/bin/python" -m installer.server \
    >"$HOME/.config/otacon/wizard.log" 2>&1 &
  echo "restarted via nohup pid $!"
fi
sleep 2
echo "--- served index (first 400 bytes) ---"
curl -s -m 5 http://127.0.0.1:5757/ | head -c 400; echo
echo "--- check ---"
if curl -s -m 5 http://127.0.0.1:5757/ | grep -q 'home.css'; then
  echo "OK: server is serving the new Command Center shell"
else
  echo "FAIL: server is NOT serving home.css — wrong install dir or old process still bound to :5757"
  echo "WorkingDirectory in unit:"; grep WorkingDirectory /etc/systemd/system/otacon.service 2>/dev/null || true
  ss -ltnp 2>/dev/null | grep 5757 || netstat -ltnp 2>/dev/null | grep 5757 || true
fi
echo
echo "Now open http://127.0.0.1:5757/ in a PRIVATE/Incognito window (or Ctrl+Shift+R)."
