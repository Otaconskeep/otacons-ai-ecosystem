"""Local ComfyUI detect + optional Docker sidecar for Expansion Video Studio.

Public Expansion keeps Studio as an endpoint contract. This module:
  - auto-detects localhost :8188 / :8199
  - starts deploy/comfyui/docker-compose.yml (CPU) or docker-compose.gpu.yml
    when hardware_profile selects comfy_runtime=gpu
  - saves the URL into preferences (same as manual config)

Model packs (Z-Image / Wan / LTX-2 / ACE-Step) are selected by
core.hardware_profile and surfaced via studio_setup.
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


def compose_file(*, runtime: str | None = None) -> Path:
    """Pick CPU or GPU compose from Studio hardware profile (VRAM-first)."""
    root = _repo_root() / 'deploy' / 'comfyui'
    rt = (runtime or '').strip().lower()
    if not rt:
        rt = (os.environ.get('OTACON_STUDIO_COMFY') or '').strip().lower()
    if not rt:
        try:
            from core.hardware_profile import detect_studio_profile
            rt = detect_studio_profile().comfy_runtime
        except Exception:
            rt = 'cpu'
    gpu_compose = root / 'docker-compose.gpu.yml'
    if rt == 'gpu' and gpu_compose.is_file():
        return gpu_compose
    return root / 'docker-compose.yml'


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


def _docker_bin_and_env() -> tuple[str | None, dict | None]:
    try:
        from core.platform import _resolve_docker, docker_env
        return _resolve_docker(), docker_env()
    except Exception:
        return shutil.which('docker'), None


def probe_docker_engine(*, timeout: float = 6.0) -> dict:
    """Honest Docker readiness for Studio Setup (CLI vs daemon).

    Friends often see ``unable to get image … error during connect`` when
    Docker Desktop is installed but the engine is stopped — that is not a
    bad Comfy image, it is a dead Docker pipe.
    """
    docker, env = _docker_bin_and_env()
    if not docker:
        return {
            'ok': False,
            'status': 'missing',
            'docker': '',
            'detail': 'Docker CLI not found in PATH / WSL candidates',
            'hint': (
                'Install Docker Desktop for Windows (WSL2 backend), start it, '
                'then reopen Ubuntu. Or skip Docker and run ComfyUI portable on :8188.'
            ),
        }
    try:
        r = subprocess.run(
            [docker, 'info', '--format', '{{.ServerVersion}}'],
            capture_output=True,
            text=True,
            timeout=max(2.0, timeout),
            check=False,
            env=env,
        )
    except subprocess.TimeoutExpired:
        return {
            'ok': False,
            'status': 'daemon_timeout',
            'docker': docker,
            'detail': 'docker info timed out',
            'hint': (
                'Docker CLI is present but the engine did not answer. '
                'Start Docker Desktop on Windows, wait until it says Running, then Detect again.'
            ),
        }
    except OSError as exc:
        return {
            'ok': False,
            'status': 'exec_failed',
            'docker': docker,
            'detail': str(exc),
            'hint': 'Could not run docker. Reinstall Docker Desktop or use ComfyUI portable.',
        }
    out = ((r.stdout or '') + '\n' + (r.stderr or '')).strip()
    if r.returncode == 0 and (r.stdout or '').strip():
        return {
            'ok': True,
            'status': 'ready',
            'docker': docker,
            'detail': f'Docker engine {(r.stdout or "").strip()}',
            'hint': '',
        }
    low = out.lower()
    if _docker_connect_failure(low):
        return {
            'ok': False,
            'status': 'daemon_down',
            'docker': docker,
            'detail': (out or 'docker engine not reachable')[:400],
            'hint': (
                'Docker Desktop is not running (or WSL cannot reach it). '
                'Open Docker Desktop on Windows → wait until the whale is steady → '
                'then click Start / Install Comfy again. '
                'No Docker? Install ComfyUI portable and use Detect.'
            ),
        }
    return {
        'ok': False,
        'status': 'unhealthy',
        'docker': docker,
        'detail': (out or f'docker info exit {r.returncode}')[:400],
        'hint': 'Fix Docker, then Start Comfy — or use ComfyUI portable on :8188.',
    }


def _docker_connect_failure(text: str) -> bool:
    low = (text or '').lower()
    needles = (
        'error during connect',
        'cannot connect',
        'could not connect',
        'is the docker daemon running',
        'dockerdesktop',
        'pipe/dockerdesktop',
        'npipe:////./pipe',
        'connectex',
        'connection refused',
        'no such file or directory',  # missing docker.sock
        'cannot find the file specified',
        'open //./pipe/docker_engine',
    )
    return any(n in low for n in needles)


def _compose_failure_hint(err: str) -> tuple[str, str]:
    """Return (action, hint) for a failed docker compose up."""
    low = (err or '').lower()
    if _docker_connect_failure(low) or 'unable to get image' in low and 'connect' in low:
        return (
            'docker_daemon_down',
            (
                'Could not pull Comfy because Docker’s engine is not connected. '
                'Start Docker Desktop on Windows, wait until it is healthy, then Start / Install Comfy again. '
                'This is not a bad yanwk/comfyui-boot image — the pull never reached the registry.'
            ),
        )
    if 'pull access denied' in low or 'not found' in low and 'manifest' in low:
        return (
            'image_pull_denied',
            'Docker could not pull yanwk/comfyui-boot:cpu — check network / Hub login, or use ComfyUI portable.',
        )
    if 'no space' in low or 'disk' in low:
        return 'disk_full', 'Free disk space on the Docker drive, then Start Comfy again.'
    if 'port is already allocated' in low or 'bind for 0.0.0.0:8188' in low:
        return (
            'port_busy',
            'Port 8188 is already in use. Click Detect — another Comfy may already be running.',
        )
    return 'compose_failed', 'Check: docker logs otacon-comfyui — or use ComfyUI portable on :8188.'


def _docker_compose_cmd(compose: Path) -> list[str] | None:
    docker, env = _docker_bin_and_env()
    if not docker:
        return None
    # Prefer `docker compose` plugin
    try:
        r = subprocess.run(
            [docker, 'compose', 'version'],
            capture_output=True,
            timeout=8,
            check=False,
            env=env,
        )
        if r.returncode == 0:
            return [docker, 'compose', '-f', str(compose)]
    except (OSError, subprocess.TimeoutExpired):
        pass
    compose_bin = shutil.which('docker-compose')
    if compose_bin:
        return [compose_bin, '-f', str(compose)]
    return None


def ensure_comfy_sidecar(
    *,
    wait_sec: float = 45.0,
    layout: Optional[StateLayout] = None,
) -> dict:
    """Start the Expansion Comfy docker compose on :8188 and save the endpoint."""
    # Already healthy?
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

    docker_st = probe_docker_engine()
    if not docker_st.get('ok'):
        return {
            'ok': False,
            'action': docker_st.get('status') or 'docker_missing',
            'error': docker_st.get('detail') or 'Docker not ready',
            'hint': docker_st.get('hint') or '',
            'docker': docker_st,
        }

    cmd_base = _docker_compose_cmd(compose)
    if not cmd_base:
        return {
            'ok': False,
            'action': 'docker_missing',
            'error': 'Docker / docker compose not available',
            'hint': (
                'Start Docker Desktop (Windows) so the engine is up, then click Start Comfy again. '
                'Or install ComfyUI portable and use Detect / paste http://127.0.0.1:8188'
            ),
            'docker': docker_st,
        }

    try:
        from core.platform import docker_env, _resolve_docker
        run_env = docker_env()
        docker = _resolve_docker()
    except Exception:
        run_env = None
        docker = None

    # Heal Restarting / wrong-image managed container (common after CPU→GPU profile flip).
    if docker:
        try:
            insp = subprocess.run(
                [docker, 'inspect', '-f',
                 '{{.State.Status}}|{{.State.Running}}|{{.Config.Image}}',
                 'otacon-comfyui'],
                capture_output=True, text=True, timeout=8, check=False, env=run_env,
            )
            if insp.returncode == 0:
                status, running, image = (insp.stdout or '').strip().split('|', 2)
                want_gpu = 'gpu' in compose.name or 'cu' in (compose.read_text(encoding='utf-8', errors='ignore')[:800].lower())
                wrong = want_gpu and 'cpu' in (image or '').lower() and 'cu' not in (image or '').lower()
                unhealthy = status.lower() in ('restarting', 'exited', 'dead') or running.lower() not in ('true', '1')
                if wrong or unhealthy:
                    subprocess.run(
                        cmd_base + ['down', '--remove-orphans'],
                        capture_output=True, text=True, timeout=120, check=False,
                        cwd=str(compose.parent), env=run_env,
                    )
        except (OSError, subprocess.TimeoutExpired, ValueError):
            pass

    try:
        up = subprocess.run(
            cmd_base + ['up', '-d', '--force-recreate'],
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
            cwd=str(compose.parent),
            env=run_env,
        )
    except subprocess.TimeoutExpired:
        return {
            'ok': False,
            'action': 'start_timeout',
            'error': 'docker compose up timed out (first image pull can be large)',
            'hint': (
                'Leave Docker Desktop running and try again. '
                'Or install ComfyUI portable if pulls keep timing out.'
            ),
            'docker': docker_st,
        }
    except OSError as exc:
        return {'ok': False, 'action': 'start_failed', 'error': str(exc), 'docker': docker_st}

    if up.returncode != 0:
        err = (up.stderr or up.stdout or 'compose failed')[:800]
        action, hint = _compose_failure_hint(err)
        return {
            'ok': False,
            'action': action,
            'error': err,
            'hint': hint,
            'docker': docker_st,
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
                'compose': str(compose),
            }
        time.sleep(2.0)

    return {
        'ok': False,
        'action': 'started_but_unhealthy',
        'endpoint': DEFAULT_ENDPOINT,
        'error': f'Container up but Comfy not healthy yet: {last}',
        'hint': 'Wait 30s and click Detect, or: docker logs otacon-comfyui',
        'compose': str(compose),
    }
