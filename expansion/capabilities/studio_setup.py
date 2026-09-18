"""Video Studio setup orchestrator — Expansion premium.

UI/agents speak INTENT ("Set up Video Studio"). This module owns Docker,
ComfyUI, ports, prefs, and health. CLI/env/config paths stay under Advanced.
"""
from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Optional

from expansion.capabilities.comfy_sidecar import (
    DEFAULT_ENDPOINT,
    DEFAULT_PORTS,
    compose_file,
    detect_local_comfy,
    ensure_comfy_sidecar,
    probe_docker_engine,
    save_studio_endpoint,
)
from expansion.capabilities.video_studio import comfy_endpoint_healthy, probe_video_studio
from expansion.persist import atomic_write_json
from expansion.state_layout import StateLayout, resolve_layout

# Public setup states (persisted + API).
NOT_CHECKED = 'NOT_CHECKED'
CHECKING = 'CHECKING'
DOCKER_MISSING = 'DOCKER_MISSING'
DOCKER_STOPPED = 'DOCKER_STOPPED'
DOCKER_READY = 'DOCKER_READY'
COMFY_NOT_FOUND = 'COMFY_NOT_FOUND'
INSTALLING_COMFY = 'INSTALLING_COMFY'
STARTING_COMFY = 'STARTING_COMFY'
WAITING_FOR_COMFY = 'WAITING_FOR_COMFY'
COMFY_READY = 'COMFY_READY'
CONFIGURING = 'CONFIGURING'
INSTALLING_MODELS = 'INSTALLING_MODELS'
VERIFYING = 'VERIFYING'
READY = 'READY'
DEGRADED = 'DEGRADED'
FAILED = 'FAILED'

_ACTIVE_STATES = frozenset({
    CHECKING, DOCKER_STOPPED, INSTALLING_COMFY, STARTING_COMFY,
    WAITING_FOR_COMFY, CONFIGURING, INSTALLING_MODELS, VERIFYING,
})

_LOCK = threading.Lock()
_WORKER: threading.Thread | None = None

# Progress checklist keys shown in the UI (human, ordered).
_CHECKLIST_ORDER = (
    ('docker', 'Docker ready'),
    ('comfy_install', 'ComfyUI installed'),
    ('comfy_start', 'Studio service started'),
    ('comfy_wait', 'Waiting for ComfyUI'),
    ('connected', 'Connected'),
    ('config', 'Configuration saved'),
    ('components', 'Required components verified'),
)


def _setup_path(layout: Optional[StateLayout] = None) -> Path:
    layout = layout or resolve_layout()
    layout.user_preferences.mkdir(parents=True, exist_ok=True)
    return layout.user_preferences / 'studio_setup.json'


def _default_state() -> dict[str, Any]:
    return {
        'phase': NOT_CHECKED,
        'ok': False,
        'running': False,
        'endpoint': '',
        'source': '',  # managed | detected | saved
        'message': '',
        'aria': 'Video Studio is not set up yet. I can set it up for you.',
        'user_action': '',
        'error': '',
        'technical': '',
        'checklist': {k: False for k, _ in _CHECKLIST_ORDER},
        'checklist_labels': {k: label for k, label in _CHECKLIST_ORDER},
        'updated_at': 0.0,
        'attempt': 0,
        'docker_launch_tried': False,
        'managed': True,
    }


def load_setup_state(layout: Optional[StateLayout] = None) -> dict[str, Any]:
    path = _setup_path(layout)
    base = _default_state()
    if not path.is_file():
        return base
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        if isinstance(data, dict):
            base.update({k: data[k] for k in base if k in data})
            # Preserve extra diagnostic keys
            for k, v in data.items():
                if k not in base:
                    base[k] = v
    except (json.JSONDecodeError, OSError):
        pass
    return base


def save_setup_state(state: dict[str, Any], layout: Optional[StateLayout] = None) -> dict[str, Any]:
    state = dict(state)
    state['updated_at'] = time.time()
    atomic_write_json(_setup_path(layout), state)
    return state


def _set_phase(
    state: dict[str, Any],
    phase: str,
    *,
    aria: str = '',
    message: str = '',
    user_action: str = '',
    error: str = '',
    technical: str = '',
    checklist_key: str | None = None,
    layout: Optional[StateLayout] = None,
) -> dict[str, Any]:
    state['phase'] = phase
    if aria:
        state['aria'] = aria
    if message:
        state['message'] = message
    state['user_action'] = user_action
    if error:
        state['error'] = error
    if technical:
        state['technical'] = technical[:2000]
    if checklist_key:
        state.setdefault('checklist', {})
        state['checklist'][checklist_key] = True
    state['running'] = phase in _ACTIVE_STATES
    state['ok'] = phase == READY
    return save_setup_state(state, layout=layout)


def required_studio_assets() -> list[dict[str, str]]:
    """Required model/asset pack for READY.

    Base empty Comfy answering on :8188 is enough for Studio READY today.
    Model/LTX packs are a later product drop — return empty so we do not
    redownload or block Setup.
    """
    return []


def docker_desktop_exe_candidates() -> list[Path]:
    cands = [
        Path('/mnt/c/Program Files/Docker/Docker/Docker Desktop.exe'),
        Path('/mnt/c/Program Files/Docker/Docker/DockerDesktop.exe'),
    ]
    # Native Windows path if somehow running outside WSL with that layout
    for p in (
        Path(r'C:\Program Files\Docker\Docker\Docker Desktop.exe'),
        Path(os.path.expandvars(r'%ProgramFiles%\Docker\Docker\Docker Desktop.exe')),
    ):
        if str(p) not in {str(x) for x in cands}:
            cands.append(p)
    return cands


def docker_desktop_installed() -> bool:
    return any(p.is_file() for p in docker_desktop_exe_candidates())


def try_start_docker_desktop() -> dict[str, Any]:
    """Best-effort launch of Docker Desktop (Windows via WSL path)."""
    exe = next((p for p in docker_desktop_exe_candidates() if p.is_file()), None)
    if not exe:
        return {'ok': False, 'action': 'not_installed', 'detail': 'Docker Desktop not found'}
    try:
        # Prefer cmd start so Windows associates correctly from WSL.
        if Path('/mnt/c/Windows/System32/cmd.exe').is_file():
            subprocess.Popen(
                ['/mnt/c/Windows/System32/cmd.exe', '/c', 'start', '', str(exe).replace('/', '\\')],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        else:
            subprocess.Popen(
                [str(exe)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        return {'ok': True, 'action': 'launched', 'path': str(exe)}
    except OSError as exc:
        return {'ok': False, 'action': 'launch_failed', 'detail': str(exc), 'path': str(exe)}


def _managed_container_status() -> dict[str, Any]:
    """Inspect otacon-comfyui without pulling."""
    try:
        from core.platform import _resolve_docker, docker_env
        docker = _resolve_docker()
        env = docker_env()
    except Exception:
        docker, env = None, None
    if not docker:
        return {'exists': False, 'running': False, 'detail': 'no docker'}
    try:
        r = subprocess.run(
            [docker, 'inspect', '-f', '{{.State.Running}}', 'otacon-comfyui'],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
            env=env,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {'exists': False, 'running': False, 'detail': str(exc)}
    if r.returncode != 0:
        return {'exists': False, 'running': False, 'detail': (r.stderr or r.stdout or '')[:200]}
    running = (r.stdout or '').strip().lower() in ('true', '1')
    return {'exists': True, 'running': running, 'detail': 'running' if running else 'stopped'}


def _prefer_endpoint(layout: Optional[StateLayout] = None) -> dict[str, Any]:
    """Discovery preference: saved healthy → managed → local ports."""
    layout = layout or resolve_layout()
    report = probe_video_studio(layout)
    disc = report.discovery or {}
    saved = (disc.get('endpoint') or '').strip()
    if saved:
        ok, detail = comfy_endpoint_healthy(saved, timeout=2.0)
        if ok:
            return {
                'found': True,
                'endpoint': saved.rstrip('/'),
                'source': 'saved',
                'detail': detail,
            }

    managed = _managed_container_status()
    if managed.get('running'):
        ok, detail = comfy_endpoint_healthy(DEFAULT_ENDPOINT, timeout=2.0)
        if ok:
            return {
                'found': True,
                'endpoint': DEFAULT_ENDPOINT,
                'source': 'managed',
                'detail': detail,
            }

    detected = detect_local_comfy(timeout=1.5)
    if detected.get('found'):
        return {
            'found': True,
            'endpoint': detected['endpoint'],
            'source': 'detected',
            'detail': detected.get('detail') or '',
        }

    # Stale saved endpoint — keep it as candidate for repair, but not found
    return {
        'found': False,
        'endpoint': saved,
        'source': 'stale' if saved else '',
        'detail': 'No healthy ComfyUI on saved URL or :8188/:8199',
        'managed': managed,
    }


def setup_status(layout: Optional[StateLayout] = None) -> dict[str, Any]:
    """Snapshot for UI poll — merges live probe when already READY."""
    layout = layout or resolve_layout()
    state = load_setup_state(layout)
    live = probe_video_studio(layout)
    docker = probe_docker_engine(timeout=4.0)
    found = _prefer_endpoint(layout)

    if live.state == 'READY' and not state.get('running'):
        state = _set_phase(
            state,
            READY,
            aria='Done. Video Studio is connected and ready.',
            message='Video Studio is ready.',
            checklist_key='connected',
            layout=layout,
        )
        for k, _ in _CHECKLIST_ORDER:
            state.setdefault('checklist', {})[k] = True
        state['endpoint'] = (live.discovery or {}).get('endpoint') or state.get('endpoint') or ''
        state['source'] = state.get('source') or 'saved'
        state['ok'] = True
        state['running'] = False
        state = save_setup_state(state, layout=layout)

    diagnostics = {
        'docker': docker,
        'capability': live.to_dict() if hasattr(live, 'to_dict') else {
            'state': live.state, 'detail': live.detail, 'discovery': live.discovery,
        },
        'discovery': found,
        'managed_container': _managed_container_status() if docker.get('ok') else {},
        'compose': str(compose_file()),
        'ports': list(DEFAULT_PORTS),
        'desktop_installed': docker_desktop_installed(),
    }
    return {
        **state,
        'capability_state': live.state,
        'need_setup': live.state not in ('READY',),
        'diagnostics': diagnostics,
        'steps': [
            {'id': k, 'label': label, 'done': bool((state.get('checklist') or {}).get(k))}
            for k, label in _CHECKLIST_ORDER
        ],
    }


def start_studio_setup(
    *,
    layout: Optional[StateLayout] = None,
    force: bool = False,
    background: bool = True,
) -> dict[str, Any]:
    """Kick off (or resume) the orchestrator. Idempotent — one worker at a time."""
    global _WORKER
    layout = layout or resolve_layout()
    with _LOCK:
        state = load_setup_state(layout)
        live = probe_video_studio(layout)
        if live.state == 'READY' and not force:
            st = setup_status(layout)
            return {**st, 'action': 'already_ready'}

        # In-process dedupe: prefer live worker over persisted flags (avoids races).
        if _WORKER is not None and _WORKER.is_alive():
            return {**setup_status(layout), 'action': 'already_running'}

        state['attempt'] = int(state.get('attempt') or 0) + 1
        state['running'] = True
        state['error'] = ''
        state['technical'] = ''
        state['docker_launch_tried'] = False
        state = _set_phase(
            state,
            CHECKING,
            aria=(
                "I'm setting up Video Studio now. The first launch takes a little longer "
                "because I'm downloading the Studio components."
            ),
            message='Preparing Video Studio…',
            layout=layout,
        )

        def _run():
            try:
                _orchestrate(layout)
            except Exception as exc:  # noqa: BLE001
                st = load_setup_state(layout)
                _set_phase(
                    st,
                    FAILED,
                    aria="I couldn't finish Video Studio setup. Open Diagnostics if you need the technical details.",
                    message='Video Studio setup failed.',
                    error=str(exc),
                    technical=repr(exc),
                    layout=layout,
                )

        if background:
            _WORKER = threading.Thread(target=_run, daemon=True, name='studio-setup')
            _WORKER.start()
            return {**setup_status(layout), 'action': 'started'}

        _run()
        return {**setup_status(layout), 'action': 'completed'}


def _wait_docker_ready(
    state: dict[str, Any],
    layout: StateLayout,
    *,
    timeout_sec: float = 180.0,
) -> tuple[bool, dict[str, Any]]:
    """Poll Docker engine; attempt Desktop launch once if stopped."""
    deadline = time.time() + timeout_sec
    launched = False
    while time.time() < deadline:
        docker = probe_docker_engine(timeout=5.0)
        if docker.get('ok'):
            return True, docker
        status = docker.get('status') or ''
        if status == 'missing' and not docker_desktop_installed():
            _set_phase(
                state,
                DOCKER_MISSING,
                aria=(
                    'Video Studio needs Docker Desktop. Install Docker Desktop for Windows '
                    'with the WSL2 backend, then click Set Up Video Studio again.'
                ),
                message='Docker Desktop is not installed.',
                user_action='Install Docker Desktop, then click Set Up Video Studio.',
                error=docker.get('detail') or '',
                technical=json.dumps(docker)[:1500],
                layout=layout,
            )
            return False, docker

        if not launched and not state.get('docker_launch_tried'):
            launch = try_start_docker_desktop()
            state['docker_launch_tried'] = True
            launched = bool(launch.get('ok'))
            state = _set_phase(
                state,
                DOCKER_STOPPED,
                aria=(
                    "Docker Desktop isn't running yet. I'm starting it for you — "
                    "leave this page open and I'll continue when it's ready."
                ),
                message='Starting Docker Desktop…',
                user_action='Leave this page open while Docker Desktop starts.',
                technical=json.dumps({'docker': docker, 'launch': launch})[:1500],
                layout=layout,
            )
        else:
            state = _set_phase(
                state,
                DOCKER_STOPPED,
                aria=(
                    "Docker Desktop needs to finish starting. Leave this page open — "
                    "I'll continue when it's ready."
                ),
                message='Waiting for Docker Desktop…',
                user_action='Leave Docker Desktop open until it says Running.',
                layout=layout,
            )
        time.sleep(4.0)
        state = load_setup_state(layout)
    docker = probe_docker_engine(timeout=5.0)
    _set_phase(
        state,
        FAILED if not docker.get('ok') else DOCKER_READY,
        aria=(
            "I couldn't start Video Studio because Docker hasn't finished starting yet. "
            "Once Docker Desktop is Running, click Set Up Video Studio and I'll continue."
        ) if not docker.get('ok') else 'Docker is ready.',
        message='Docker did not become ready in time.' if not docker.get('ok') else 'Docker ready',
        user_action='Start Docker Desktop, wait until Running, then click Set Up again.',
        error=docker.get('detail') or 'docker timeout',
        technical=json.dumps(docker)[:1500],
        layout=layout,
    )
    return bool(docker.get('ok')), docker


def _orchestrate(layout: StateLayout) -> None:
    state = load_setup_state(layout)
    state = _set_phase(
        state,
        CHECKING,
        aria='Checking Video Studio…',
        message='Detecting Studio state…',
        layout=layout,
    )

    # Fast path: already healthy somewhere
    found = _prefer_endpoint(layout)
    if found.get('found'):
        endpoint = found['endpoint']
        state = _set_phase(
            state,
            CONFIGURING,
            aria='I found ComfyUI on this PC. Connecting Video Studio…',
            message='Connecting to existing ComfyUI…',
            checklist_key='docker',
            layout=layout,
        )
        for k in ('docker', 'comfy_install', 'comfy_start', 'comfy_wait', 'connected'):
            state.setdefault('checklist', {})[k] = True
        save_studio_endpoint(endpoint, layout=layout)
        state['endpoint'] = endpoint
        state['source'] = found.get('source') or 'detected'
        state = _set_phase(
            state,
            CONFIGURING,
            checklist_key='config',
            layout=layout,
        )
        _finish_components_and_ready(state, layout, endpoint)
        return

    # Stale saved endpoint — clear running flag path and rediscover via provision
    if found.get('source') == 'stale' and found.get('endpoint'):
        state['technical'] = f"stale endpoint {found['endpoint']}; rediscovering"
        state = save_setup_state(state, layout=layout)

    ok_docker, docker = _wait_docker_ready(state, layout)
    state = load_setup_state(layout)
    if not ok_docker:
        return

    state = _set_phase(
        state,
        DOCKER_READY,
        aria='Docker is ready, so I can set up Video Studio for you.',
        message='Docker ready',
        checklist_key='docker',
        layout=layout,
    )

    managed = _managed_container_status()
    if managed.get('exists') and not managed.get('running'):
        state = _set_phase(
            state,
            STARTING_COMFY,
            aria="Studio's ComfyUI is installed but stopped. Starting it…",
            message='Starting Studio service…',
            checklist_key='comfy_install',
            layout=layout,
        )
    else:
        state = _set_phase(
            state,
            INSTALLING_COMFY,
            aria=(
                "I'm setting up Video Studio now. The first launch takes a little longer "
                "because I'm downloading the Studio components."
            ),
            message='Installing ComfyUI…',
            layout=layout,
        )

    # Idempotent compose up (also starts stopped managed container)
    result = ensure_comfy_sidecar(wait_sec=90.0, layout=layout)
    state = load_setup_state(layout)
    if not result.get('ok'):
        action = result.get('action') or 'failed'
        hint = result.get('hint') or result.get('error') or 'Setup failed'
        tech = result.get('error') or ''
        # Daemon dropped mid-flight — re-enter wait rather than hard fail when Desktop exists
        if action in ('daemon_down', 'docker_daemon_down', 'missing', 'daemon_timeout'):
            state['docker_launch_tried'] = False
            ok2, _ = _wait_docker_ready(state, layout, timeout_sec=120.0)
            if ok2:
                result = ensure_comfy_sidecar(wait_sec=90.0, layout=layout)
                state = load_setup_state(layout)
        if not result.get('ok'):
            _set_phase(
                state,
                FAILED,
                aria=hint if len(hint) < 220 else (
                    "I couldn't start Video Studio. "
                    "If Docker Desktop is still starting, leave it open and try Set Up again."
                ),
                message='Could not start ComfyUI.',
                error=hint,
                technical=tech,
                user_action='Open Diagnostics for details, or try Set Up again after Docker is Running.',
                layout=layout,
            )
            return

    endpoint = (result.get('endpoint') or DEFAULT_ENDPOINT).rstrip('/')
    state = _set_phase(
        state,
        WAITING_FOR_COMFY,
        aria='Waiting for ComfyUI to answer…',
        message='Waiting for ComfyUI…',
        checklist_key='comfy_install',
        layout=layout,
    )
    state.setdefault('checklist', {})['comfy_start'] = True
    state.setdefault('checklist', {})['comfy_wait'] = True
    save_setup_state(state, layout=layout)

    # Bounded readiness (ensure_comfy already waited; quick re-check)
    ok, detail = comfy_endpoint_healthy(endpoint, timeout=3.0)
    if not ok:
        deadline = time.time() + 60.0
        while time.time() < deadline and not ok:
            time.sleep(3.0)
            ok, detail = comfy_endpoint_healthy(endpoint, timeout=2.0)
        if not ok:
            _set_phase(
                state,
                DEGRADED,
                aria=(
                    "Studio's service started but ComfyUI isn't answering yet. "
                    "I'll keep this page ready — click Set Up again in a minute."
                ),
                message='ComfyUI is starting slowly.',
                error=detail,
                technical=detail,
                layout=layout,
            )
            state = load_setup_state(layout)
            state['endpoint'] = endpoint
            save_setup_state(state, layout=layout)
            return

    state = load_setup_state(layout)
    state['endpoint'] = endpoint
    state['source'] = 'managed'
    state = _set_phase(
        state,
        COMFY_READY,
        aria='Connected to ComfyUI.',
        message='Connected',
        checklist_key='connected',
        layout=layout,
    )
    state = _set_phase(
        state,
        CONFIGURING,
        aria='Saving Video Studio configuration…',
        message='Saving configuration…',
        layout=layout,
    )
    save_studio_endpoint(endpoint, layout=layout)
    state = _set_phase(
        state,
        CONFIGURING,
        checklist_key='config',
        layout=layout,
    )
    _finish_components_and_ready(state, layout, endpoint)


def _finish_components_and_ready(
    state: dict[str, Any],
    layout: StateLayout,
    endpoint: str,
) -> None:
    state = _set_phase(
        state,
        INSTALLING_MODELS,
        aria='Checking required Studio components…',
        message='Verifying components…',
        layout=layout,
    )
    # Empty required set → nothing to download (idempotent, no redownload).
    _ = required_studio_assets()
    state = _set_phase(
        state,
        VERIFYING,
        aria='Verifying Video Studio…',
        message='Running health checks…',
        checklist_key='components',
        layout=layout,
    )
    report = probe_video_studio(layout)
    if report.state == 'READY':
        state['endpoint'] = endpoint
        _set_phase(
            state,
            READY,
            aria='Done. Video Studio is connected and ready.',
            message='Video Studio is ready.',
            layout=layout,
        )
        state = load_setup_state(layout)
        for k, _ in _CHECKLIST_ORDER:
            state.setdefault('checklist', {})[k] = True
        state['ok'] = True
        state['running'] = False
        state['endpoint'] = endpoint
        save_setup_state(state, layout=layout)
        return
    _set_phase(
        state,
        DEGRADED if report.state == 'LIMITED' else FAILED,
        aria=(
            "Video Studio is almost ready, but the connection check didn't pass yet. "
            "Click Set Up again in a moment."
        ),
        message=report.detail or 'Verification incomplete',
        error=report.detail,
        technical=json.dumps(report.discovery or {})[:1500],
        layout=layout,
    )
