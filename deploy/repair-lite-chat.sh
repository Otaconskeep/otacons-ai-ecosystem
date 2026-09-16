#!/usr/bin/env bash
# Repair Lite chat: pull code + ensure an Ollama model exists + restart otacon.
# Run from WSL as the install user, e.g.:
#   bash ~/otacon-ai-ecosystem/deploy/repair-lite-chat.sh
set -euo pipefail
INSTALL_DIR="${OTACON_INSTALL_DIR:-$HOME/otacon-ai-ecosystem}"
CFG="$HOME/.config/otacon/config.json"

echo "== Otacon Lite chat repair =="
echo "install: $INSTALL_DIR"

if [[ -d "$INSTALL_DIR/.git" ]]; then
  git -C "$INSTALL_DIR" fetch --prune origin
  git -C "$INSTALL_DIR" pull --ff-only || git -C "$INSTALL_DIR" reset --hard origin/main
  echo "repo: $(git -C "$INSTALL_DIR" rev-parse --short HEAD)"
else
  echo "WARN: no git checkout at $INSTALL_DIR"
fi

WANT=""
if [[ -f /etc/systemd/system/otacon.service ]]; then
  WANT="$(grep -E '^Environment=OTACON_LLM_MODEL=' /etc/systemd/system/otacon.service | head -1 | cut -d= -f3 || true)"
fi
if [[ -z "$WANT" && -f "$CFG" ]]; then
  WANT="$(python3 -c "import json;print(json.load(open('$CFG')).get('llm_service',{}).get('model','') or '')" 2>/dev/null || true)"
fi
WANT="${WANT:-qwen2.5:7b}"
echo "target model: $WANT"

if ! command -v ollama >/dev/null 2>&1; then
  echo "FAIL: ollama not on PATH inside WSL"
  exit 1
fi

echo "--- ollama list (before) ---"
ollama list || true

# Pull if missing (ollama pull is safe/idempotent).
if ! ollama list 2>/dev/null | awk 'NR>1{print $1}' | grep -qx "$WANT"; then
  # Also accept longer tags that start with WANT-
  if ! ollama list 2>/dev/null | awk 'NR>1{print $1}' | grep -q "^${WANT}"; then
    echo "pulling $WANT ..."
    ollama pull "$WANT"
  fi
fi

echo "--- ollama list (after) ---"
ollama list || true

# Patch stale config model to the one we know exists.
if [[ -f "$CFG" ]]; then
  python3 - "$CFG" "$WANT" <<'PY'
import json, sys
path, model = sys.argv[1], sys.argv[2]
cfg = json.load(open(path))
svc = cfg.setdefault('llm_service', {})
old = svc.get('model')
svc['provider'] = svc.get('provider') or 'ollama'
svc['endpoint'] = svc.get('endpoint') or 'http://127.0.0.1:11434'
svc['model'] = model
json.dump(cfg, open(path, 'w'), indent=2)
open(path, 'a').write('\n')
print(f"config model: {old!r} -> {model!r}")
PY
fi

if command -v systemctl >/dev/null 2>&1 && [[ -d /run/systemd/system ]]; then
  if [[ "${EUID:-$(id -u)}" -eq 0 ]]; then
    systemctl restart otacon.service || systemctl restart otacon
  else
    echo "restarting otacon via wsl root..."
    wsl.exe -u root -- systemctl restart otacon.service 2>/dev/null \
      || sudo systemctl restart otacon.service 2>/dev/null \
      || sudo systemctl restart otacon 2>/dev/null \
      || echo "WARN: could not restart systemd unit — kill/restart Otacon manually"
  fi
  sleep 2
  systemctl is-active otacon.service 2>/dev/null || systemctl is-active otacon 2>/dev/null || true
fi

echo "--- chat probe ---"
curl -sS -m 120 -X POST http://127.0.0.1:5757/api/chat_with_agent \
  -H 'Content-Type: application/json' \
  -d '{"agent":{"id":"agent_001","display_name":"Aria","voice_id":"voice_aria"},"message":"hi","conversation_id":"repair1"}' \
  || true
echo
echo "Done. Hard-refresh the browser (Ctrl+F5)."
