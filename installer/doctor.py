"""otacon doctor — inspect local install health without claiming READY falsely."""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import urllib.request
from pathlib import Path

from installer.security import CONFIG_ROOT, load_lan_token, resolve_bind_host


def _check(name: str, ok: bool, detail: str) -> dict:
    return {'name': name, 'status': 'PASS' if ok else 'FAIL', 'detail': detail}


def _warn(name: str, detail: str) -> dict:
    return {'name': name, 'status': 'WARNING', 'detail': detail}


def main(argv=None) -> int:
    results = []
    host, mode = resolve_bind_host()
    port = int(os.getenv('OTACON_PORT', os.getenv('OTACON_CHAT_PORT', '5757')))
    results.append(_check('bind_mode', True, f'{mode} @ {host}:{port}'))

    # Port listening
    sock_ok = False
    try:
        with socket.create_connection(('127.0.0.1', port), timeout=2):
            sock_ok = True
    except OSError:
        sock_ok = False
    results.append(_check('local_port', sock_ok, f'127.0.0.1:{port}'))

    # Branding
    try:
        with urllib.request.urlopen(f'http://127.0.0.1:{port}/api/branding', timeout=3) as r:
            branding = json.loads(r.read().decode())
        results.append(_check('http_branding', branding.get('product_name') == 'Otacon', str(branding)[:120]))
    except Exception as exc:
        results.append(_check('http_branding', False, str(exc)))

    # Capabilities
    try:
        with urllib.request.urlopen(f'http://127.0.0.1:{port}/api/capabilities', timeout=5) as r:
            caps = json.loads(r.read().decode())
        results.append(_check('capabilities', True, json.dumps(caps)[:200]))
    except Exception as exc:
        results.append(_warn('capabilities', str(exc)))

    # Ollama
    endpoint = os.getenv('OTACON_LLM_ENDPOINT', 'http://127.0.0.1:11434')
    try:
        with urllib.request.urlopen(endpoint.rstrip('/') + '/api/tags', timeout=3) as r:
            tags = json.loads(r.read().decode())
        models = [m.get('name') for m in tags.get('models', [])]
        results.append(_check('ollama', True, f'{len(models)} model(s)'))
    except Exception as exc:
        results.append(_check('ollama', False, str(exc)))

    cfg = CONFIG_ROOT / 'config.json'
    if cfg.is_file():
        try:
            data = json.loads(cfg.read_text())
            model = (data.get('llm_service') or {}).get('model', '')
            results.append(_check('config', True, f'model={model}'))
        except Exception as exc:
            results.append(_check('config', False, str(exc)))
    else:
        results.append(_warn('config', f'missing {cfg}'))

    # systemd
    try:
        cp = subprocess.run(
            ['systemctl', 'is-active', 'otacon.service'],
            capture_output=True, text=True, timeout=5,
        )
        active = cp.stdout.strip() == 'active'
        results.append(_check('systemd', active, cp.stdout.strip() or cp.stderr.strip()))
    except Exception as exc:
        results.append(_warn('systemd', str(exc)))

    if mode == 'lan':
        token = load_lan_token()
        results.append(_check('lan_token', bool(token), str(CONFIG_ROOT / 'lan_token')))

    # Resources
    try:
        mem = Path('/proc/meminfo').read_text()
        for line in mem.splitlines():
            if line.startswith('MemTotal:'):
                ram_gb = int(line.split()[1]) / 1024 / 1024
                results.append(_check('ram', ram_gb >= 4, f'{ram_gb:.1f} GB'))
                break
    except Exception as exc:
        results.append(_warn('ram', str(exc)))

    print('=== otacon doctor ===')
    failed = 0
    for r in results:
        print(f"[{r['status']}] {r['name']}: {r['detail']}")
        if r['status'] == 'FAIL':
            failed += 1
    print('=== end ===')
    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
