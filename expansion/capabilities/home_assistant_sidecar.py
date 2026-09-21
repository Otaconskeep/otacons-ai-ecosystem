"""Managed local Home Assistant Docker sidecar for Expansion.

Mirrors n8n_sidecar: after Docker is available, pull + compose up
otacon-homeassistant on :8123, register URL with Keep. Long-lived token
still needs one user paste after HA onboarding (cannot invent owner account).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Optional

from expansion.capabilities.home_assistant import load_ha_config, probe_home_assistant, save_ha_config
from expansion.state_layout import StateLayout, resolve_layout

DEFAULT_ENDPOINT = 'http://127.0.0.1:8123'
HA_IMAGE = os.environ.get('OTACON_HA_IMAGE') or 'ghcr.io/home-assistant/home-assistant:stable'
HA_PULL_TIMEOUT_SEC = int(os.environ.get('OTACON_HA_PULL_TIMEOUT') or '900')
HA_CONTAINER = 'otacon-homeassistant'


def _repo_root() -> Path:
    env = (os.environ.get('OTACON_INSTALL_DIR') or '').strip()
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[2]


def compose_file() -> Path:
    return _repo_root() / 'deploy' / 'homeassistant' / 'docker-compose.yml'


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


def ha_endpoint_healthy(url: str = DEFAULT_ENDPOINT, timeout: float = 2.5) -> tuple[bool, str]:
    """True when HA HTTP answers (onboarding page counts — no token required)."""
    base = (url or DEFAULT_ENDPOINT).rstrip('/')
    for path in ('/', '/api/', '/onboarding.html'):
        try:
            req = urllib.request.Request(
                base + path,
                headers={'User-Agent': 'Otacon-Expansion/ha-probe'},
                method='GET',
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                code = getattr(resp, 'status', None) or resp.getcode()
                if 200 <= int(code) < 500:
                    return True, f'HTTP {code} at {path}'
        except urllib.error.HTTPError as exc:
            # Auth wall or API without token still means the container is up.
            if exc.code in (401, 403, 405):
                return True, f'HTTP {exc.code} (service up)'
            continue
        except (urllib.error.URLError, TimeoutError, OSError):
            continue
    return False, 'Home Assistant not answering'


def _container_running() -> bool:
    docker, env = _docker_bin_and_env()
    if not docker:
        return False
    try:
        r = subprocess.run(
            [docker, 'inspect', '-f', '{{.State.Running}}', HA_CONTAINER],
            capture_output=True, text=True, timeout=8, check=False, env=env,
        )
        return r.returncode == 0 and (r.stdout or '').strip().lower() == 'true'
    except (OSError, subprocess.TimeoutExpired):
        return False


def ensure_home_assistant_sidecar(
    *,
    wait_sec: float = 180.0,
    layout: Optional[StateLayout] = None,
) -> dict[str, Any]:
    """Deploy local HA via Docker, wait for HTTP, register URL (token still optional)."""
    layout = layout or resolve_layout()
    ok, detail = ha_endpoint_healthy()
    if ok:
        try:
            save_ha_config(DEFAULT_ENDPOINT, token='', layout=layout)
        except ValueError as exc:
            return {'ok': False, 'action': 'save_failed', 'error': str(exc), 'endpoint': DEFAULT_ENDPOINT}
        cfg = load_ha_config(layout)
        return {
            'ok': True,
            'action': 'already_running',
            'endpoint': DEFAULT_ENDPOINT,
            'detail': detail,
            'token_configured': bool(cfg.get('token_configured')),
            'user_action': 'none' if cfg.get('token_configured') else 'onboard_token',
            'state': probe_home_assistant(layout).state,
            'config': cfg,
        }

    compose = compose_file()
    if not compose.is_file():
        return {
            'ok': False,
            'action': 'missing_compose',
            'error': f'Home Assistant compose missing at {compose}',
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
    try:
        subprocess.run(
            [docker, 'pull', HA_IMAGE],
            capture_output=True, timeout=HA_PULL_TIMEOUT_SEC, check=False, env=env,
        )
    except (OSError, subprocess.TimeoutExpired):
        pass

    try:
        up = subprocess.run(
            cmd_base + ['up', '-d'],
            capture_output=True, text=True, timeout=240, check=False, env=env,
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
        ok, last = ha_endpoint_healthy(timeout=2.0)
        if ok:
            try:
                save_ha_config(DEFAULT_ENDPOINT, token='', layout=layout)
            except ValueError as exc:
                return {
                    'ok': False,
                    'action': 'save_failed',
                    'error': str(exc),
                    'endpoint': DEFAULT_ENDPOINT,
                    'detail': last,
                }
            cfg = load_ha_config(layout)
            return {
                'ok': True,
                'action': 'started',
                'endpoint': DEFAULT_ENDPOINT,
                'detail': last,
                'container_running': _container_running(),
                'token_configured': bool(cfg.get('token_configured')),
                'user_action': 'none' if cfg.get('token_configured') else 'onboard_token',
                'state': probe_home_assistant(layout).state,
                'config': cfg,
            }
        time.sleep(3.0)

    return {
        'ok': False,
        'action': 'health_timeout',
        'error': f'Home Assistant did not become healthy: {last}',
        'endpoint': DEFAULT_ENDPOINT,
        'container_running': _container_running(),
    }
