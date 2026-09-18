"""Local ComfyUI detect + optional Docker sidecar for Expansion Video Studio.

Public Expansion keeps Studio as an endpoint contract. This module:
  - auto-detects localhost :8188 / :8199
  - can start deploy/comfyui/docker-compose.yml (empty Comfy → READY)
  - saves the URL into preferences (same as manual config)

No LTX/model pack here — that stays a later Studio deps drop.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Optional

from expansion.capabilities.video_studio import comfy_endpoint_healthy, probe_video_studio
from expansion.persist import atomic_write_json
from expansion.state_layout import StateLayout, resolve_layout

DEFAULT_PORTS = (8188, 8199)
DEFAULT_ENDPOINT = 'http://127.0.0.1:8188'


def _repo_root() -> Path:
    env = (os.environ.get('OTACON_INSTALL_DIR') or '').strip()
    if env:
        return Path(env)
    # expansion/capabilities/comfy_sidecar.py → repo root
    return Path(__file__).resolve().parents[2]


def compose_file() -> Path:
    return _repo_root() / 'deploy' / 'comfyui' / 'docker-compose.yml'


def detect_local_comfy(timeout: float = 1.5) -> dict:
    """Probe common local Comfy ports. Prefer already-running Keep/user instances."""
    hits = []
    for port in DEFAULT_PORTS:
        url = f'http://127.0.0.1:{port}'
        ok, detail = comfy_endpoint_healthy(url, timeout=timeout)
        hits.append({'endpoint': url, 'ok': ok, 'detail': detail})
        if ok:
            return {
                'found': True,
                'endpoint': url,
                'detail': detail,
                'candidates': hits,
            }
    return {
        'found': False,
        'endpoint': '',
        'detail': 'No ComfyUI answering on :8188 or :8199',
        'candidates': hits,
    }


def save_studio_endpoint(endpoint: str, layout: Optional[StateLayout] = None) -> dict:
    layout = layout or resolve_layout()
    endpoint = (endpoint or '').strip().rstrip('/')
    if not endpoint:
        raise ValueError('endpoint required')
    layout.user_preferences.mkdir(parents=True, exist_ok=True)
    cfg_path = layout.user_preferences / 'video_studio.json'
    atomic_write_json(cfg_path, {
        'endpoint': endpoint,
        'comfyui_url': endpoint,
        'provider': 'comfyui',
        'managed_by': 'expansion',
    })
    try:
        from expansion.topology import load_topology, save_topology
        topo = load_topology()
        topo.comfyui_url = endpoint
        save_topology(topo)
    except Exception:
        pass
    report = probe_video_studio(layout)
    return {
        'ok': True,
        'endpoint': endpoint,
        'state': report.state,
        'detail': report.detail,
        'video_studio': report.to_dict(),
    }


def _docker_compose_cmd(compose: Path) -> list[str] | None:
    if not shutil.which('docker'):
        return None
    # Prefer `docker compose` plugin
    try:
        r = subprocess.run(
            ['docker', 'compose', 'version'],
            capture_output=True,
            timeout=8,
            check=False,
        )
        if r.returncode == 0:
            return ['docker', 'compose', '-f', str(compose)]
    except (OSError, subprocess.TimeoutExpired):
        pass
    if shutil.which('docker-compose'):
        return ['docker-compose', '-f', str(compose)]
    return None


def ensure_comfy_sidecar(
    *,
    wait_sec: float = 45.0,
    layout: Optional[StateLayout] = None,
) -> dict:
    """Start the Expansion Comfy docker compose on :8188 and save the endpoint."""
    # Already up?
    detected = detect_local_comfy()
    if detected.get('found'):
        saved = save_studio_endpoint(detected['endpoint'], layout=layout)
        return {
            'ok': True,
            'action': 'already_running',
            'endpoint': detected['endpoint'],
            **{k: saved[k] for k in ('state', 'detail', 'video_studio') if k in saved},
        }

    compose = compose_file()
    if not compose.is_file():
        return {
            'ok': False,
            'action': 'missing_compose',
            'error': f'Comfy compose missing at {compose}',
            'hint': 'Re-pull otacons-ai-ecosystem or set OTACON_INSTALL_DIR.',
        }

    cmd_base = _docker_compose_cmd(compose)
    if not cmd_base:
        return {
            'ok': False,
            'action': 'docker_missing',
            'error': 'Docker / docker compose not available',
            'hint': (
                'Install Docker Desktop (Windows/WSL2) or Docker Engine, then click Start Comfy again. '
                'Or install ComfyUI portable and use Detect / paste http://127.0.0.1:8188'
            ),
        }

    try:
        up = subprocess.run(
            cmd_base + ['up', '-d'],
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
            cwd=str(compose.parent),
        )
    except subprocess.TimeoutExpired:
        return {'ok': False, 'action': 'start_timeout', 'error': 'docker compose up timed out'}
    except OSError as exc:
        return {'ok': False, 'action': 'start_failed', 'error': str(exc)}

    if up.returncode != 0:
        return {
            'ok': False,
            'action': 'compose_failed',
            'error': (up.stderr or up.stdout or 'compose failed')[:800],
            'hint': 'Check docker logs: docker logs otacon-comfyui',
        }

    deadline = time.time() + max(5.0, wait_sec)
    last = 'waiting'
    while time.time() < deadline:
        ok, last = comfy_endpoint_healthy(DEFAULT_ENDPOINT, timeout=2.0)
        if ok:
            saved = save_studio_endpoint(DEFAULT_ENDPOINT, layout=layout)
            return {
                'ok': True,
                'action': 'started',
                'endpoint': DEFAULT_ENDPOINT,
                'state': saved.get('state'),
                'detail': saved.get('detail'),
                'video_studio': saved.get('video_studio'),
            }
        time.sleep(2.0)

    return {
        'ok': False,
        'action': 'started_but_unhealthy',
        'endpoint': DEFAULT_ENDPOINT,
        'error': f'Container up but Comfy not healthy yet: {last}',
        'hint': 'Wait 30s and click Detect, or: docker logs otacon-comfyui',
    }
