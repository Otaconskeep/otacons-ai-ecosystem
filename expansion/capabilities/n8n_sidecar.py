"""Managed local n8n Docker sidecar for Expansion."""
from __future__ import annotations

import os
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

from expansion.capabilities.discord_n8n import probe_n8n, save_n8n_config
from expansion.state_layout import StateLayout, resolve_layout

DEFAULT_ENDPOINT = 'http://127.0.0.1:5678'
N8N_PULL_TIMEOUT_SEC = int(os.environ.get('OTACON_N8N_PULL_TIMEOUT') or '600')


def _repo_root() -> Path:
    env = (os.environ.get('OTACON_INSTALL_DIR') or '').strip()
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[2]


def compose_file() -> Path:
    return _repo_root() / 'deploy' / 'n8n' / 'docker-compose.yml'


def _docker_bin_and_env():
    try:
        from core.platform import _resolve_docker, docker_env
        return _resolve_docker(), docker_env()
    except Exception:
        return shutil.which('docker'), os.environ.copy()


def _docker_compose_cmd(compose: Path) -> list[str] | None:
    docker, env = _docker_bin_and_env()
    if not docker:
        return None
    try:
        r = subprocess.run(
            [docker, 'compose', 'version'],
            capture_output=True, timeout=8, check=False, env=env,
        )
        if r.returncode == 0:
            return [docker, 'compose', '-f', str(compose)]
    except (OSError, subprocess.TimeoutExpired):
        pass
    compose_bin = shutil.which('docker-compose')
    if compose_bin:
        return [compose_bin, '-f', str(compose)]
    return None


def n8n_endpoint_healthy(url: str = DEFAULT_ENDPOINT, timeout: float = 2.0) -> tuple[bool, str]:
    base = (url or DEFAULT_ENDPOINT).rstrip('/')
    for path in ('/healthz', '/healthz/', '/'):
        try:
            req = urllib.request.Request(
                base + path,
                headers={'User-Agent': 'Otacon-Expansion/n8n-probe'},
                method='GET',
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                code = getattr(resp, 'status', None) or resp.getcode()
                if 200 <= int(code) < 500:
                    return True, f'HTTP {code} at {path}'
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                return True, f'HTTP {exc.code} (auth wall — service up)'
            continue
        except (urllib.error.URLError, TimeoutError, OSError):
            continue
    return False, 'n8n not answering'


def ensure_n8n_sidecar(
    *,
    wait_sec: float = 90.0,
    layout: Optional[StateLayout] = None,
) -> dict:
    """Deploy local n8n via Docker, health-check, register endpoint with Keep."""
    layout = layout or resolve_layout()
    ok, detail = n8n_endpoint_healthy()
    if ok:
        saved = save_n8n_config(url=DEFAULT_ENDPOINT, layout=layout, managed=True)
        return {
            'ok': True,
            'action': 'already_running',
            'endpoint': DEFAULT_ENDPOINT,
            'detail': detail,
            'state': probe_n8n(layout).state,
            **saved,
        }

    compose = compose_file()
    if not compose.is_file():
        return {
            'ok': False,
            'action': 'missing_compose',
            'error': f'n8n compose missing at {compose}',
        }

    try:
        from expansion.capabilities.comfy_sidecar import probe_docker_engine
        docker_st = probe_docker_engine()
    except Exception:
        docker_st = {'ok': False, 'detail': 'docker probe failed'}
    if not docker_st.get('ok'):
        return {
            'ok': False,
            'action': 'docker_missing',
            'error': docker_st.get('detail') or 'Docker not ready',
            'docker': docker_st,
        }

    cmd_base = _docker_compose_cmd(compose)
    if not cmd_base:
        return {
            'ok': False,
            'action': 'docker_missing',
            'error': 'Docker / docker compose not available',
            'docker': docker_st,
        }

    docker, env = _docker_bin_and_env()
    # Pre-pull
    try:
        subprocess.run(
            [docker, 'pull', 'n8nio/n8n:latest'],
            capture_output=True, timeout=N8N_PULL_TIMEOUT_SEC, check=False, env=env,
        )
    except (OSError, subprocess.TimeoutExpired):
        pass

    try:
        up = subprocess.run(
            cmd_base + ['up', '-d'],
            capture_output=True, text=True, timeout=180, check=False, env=env,
        )
    except subprocess.TimeoutExpired:
        return {'ok': False, 'action': 'compose_timeout', 'error': 'docker compose up timed out'}
    except OSError as exc:
        return {'ok': False, 'action': 'compose_failed', 'error': str(exc)}

    if up.returncode != 0:
        err = ((up.stderr or '') + (up.stdout or ''))[-800:]
        return {'ok': False, 'action': 'compose_failed', 'error': err or f'exit {up.returncode}'}

    deadline = time.time() + wait_sec
    last = 'waiting'
    while time.time() < deadline:
        ok, last = n8n_endpoint_healthy(timeout=1.5)
        if ok:
            saved = save_n8n_config(url=DEFAULT_ENDPOINT, layout=layout, managed=True)
            return {
                'ok': True,
                'action': 'started',
                'endpoint': DEFAULT_ENDPOINT,
                'detail': last,
                'state': probe_n8n(layout).state,
                **saved,
            }
        time.sleep(2.0)

    return {
        'ok': False,
        'action': 'health_timeout',
        'error': f'n8n did not become healthy: {last}',
        'endpoint': DEFAULT_ENDPOINT,
    }
