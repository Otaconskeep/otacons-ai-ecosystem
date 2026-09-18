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
    clear_studio_endpoint,
    compose_file,
    detect_local_comfy,
    ensure_comfy_sidecar,
    heal_docker_hub_auth,
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
UNDER_SPEC = 'UNDER_SPEC'

_ACTIVE_STATES = frozenset({
    CHECKING, DOCKER_STOPPED, INSTALLING_COMFY, STARTING_COMFY,
    WAITING_FOR_COMFY, CONFIGURING, INSTALLING_MODELS, VERIFYING,
})

_LOCK = threading.Lock()
_WORKER: threading.Thread | None = None

# Stuck INSTALLING_COMFY with no docker provision → retry/fail.
_INSTALL_STALE_SEC = 30.0
_INSTALL_MAX_DISPATCH = 2

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

_INSTALL_IDLE = 'idle'
_INSTALL_REQUESTED = 'requested'
_INSTALL_STARTED = 'started'
_INSTALL_COMPLETED = 'completed'
_INSTALL_FAILED = 'failed'


def _default_install_action() -> dict[str, Any]:
    return {
        'status': _INSTALL_IDLE,
        'error': '',
        'requested_at': 0.0,
        'started_at': 0.0,
        'completed_at': 0.0,
        'dispatch_attempts': 0,
    }


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
        # True when ensure_comfy_sidecar / docker compose up is actually invoked.
        'docker_launch_tried': False,
        # True when Docker Desktop launch was attempted (WSL path).
        'desktop_launch_tried': False,
        'install_action': _default_install_action(),
        'installing_since': 0.0,
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
            ia = data.get('install_action')
            if isinstance(ia, dict):
                merged = _default_install_action()
                merged.update({k: ia[k] for k in merged if k in ia})
                base['install_action'] = merged
            # Back-compat: older tips used docker_launch_tried for Desktop.
            if 'desktop_launch_tried' not in data and data.get('docker_launch_tried'):
                # Ambiguous — do not invent Desktop history; leave False.
                pass
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
    """Model/asset packs for this host from VRAM-first hardware_profile.

    Connectivity READY still only needs Comfy answering. Packs listed here
    are what Setup should install next (Z-Image / Wan / LTX-2 / ACE-Step)
    without blocking the empty-Comfy connect path.
    """
    try:
        from core.hardware_profile import detect_studio_profile, profile_asset_manifest
        return profile_asset_manifest(detect_studio_profile())
    except Exception:
        return []


def studio_hardware_snapshot() -> dict[str, Any]:
    """Live Studio profile for UI / setup_status."""
    try:
        from core.hardware_profile import (
            detect_studio_profile,
            persist_studio_profile,
            profile_asset_manifest,
            load_studio_defaults,
        )
        profile = detect_studio_profile()
        persist_studio_profile(profile)
        return {
            **profile.to_dict(),
            'assets': profile_asset_manifest(profile),
            'defaults': load_studio_defaults(),
        }
    except Exception as exc:  # noqa: BLE001
        return {'profile_id': 'UNKNOWN', 'error': str(exc), 'assets': []}


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


def _worker_alive() -> bool:
    return _WORKER is not None and _WORKER.is_alive()


def _mark_install_action(
    state: dict[str, Any],
    status: str,
    *,
    error: str = '',
    layout: Optional[StateLayout] = None,
) -> dict[str, Any]:
    ia = dict(state.get('install_action') or _default_install_action())
    now = time.time()
    ia['status'] = status
    if status == _INSTALL_REQUESTED:
        ia['requested_at'] = now
        ia['error'] = ''
        ia['dispatch_attempts'] = int(ia.get('dispatch_attempts') or 0) + 1
    elif status == _INSTALL_STARTED:
        ia['started_at'] = now
        ia['error'] = ''
    elif status == _INSTALL_COMPLETED:
        ia['completed_at'] = now
        ia['error'] = ''
    elif status == _INSTALL_FAILED:
        ia['completed_at'] = now
        if error:
            ia['error'] = error[:2000]
    state['install_action'] = ia
    return save_setup_state(state, layout=layout)


def _transition_to_installing_comfy(
    state: dict[str, Any],
    layout: StateLayout,
    *,
    aria: str,
    message: str,
) -> dict[str, Any]:
    """Atomic enter INSTALLING_COMFY: request → accept → expose phase.

    Never leave phase=INSTALLING_COMFY without install_action started and
    docker_launch_tried=True (caller must invoke provision immediately after).
    """
    state = _mark_install_action(state, _INSTALL_REQUESTED, layout=layout)
    state = load_setup_state(layout)
    # Accept dispatch in-process (same worker that will call ensure_comfy).
    state['docker_launch_tried'] = True
    state['installing_since'] = time.time()
    state = _mark_install_action(state, _INSTALL_STARTED, layout=layout)
    state = load_setup_state(layout)
    return _set_phase(
        state,
        INSTALLING_COMFY,
        aria=aria,
        message=message,
        layout=layout,
    )


def _fail_install_did_not_start(
    state: dict[str, Any],
    layout: StateLayout,
    *,
    detail: str = '',
) -> dict[str, Any]:
    err = 'ComfyUI installation did not start'
    if detail:
        err = f'{err}: {detail}'
    state = _mark_install_action(state, _INSTALL_FAILED, error=err, layout=layout)
    state = load_setup_state(layout)
    state['running'] = False
    return _set_phase(
        state,
        FAILED,
        aria=(
            "I couldn't start installing ComfyUI. "
            "Open Diagnostics for the technical detail, then click Set Up again."
        ),
        message=err,
        error=err,
        technical=detail or err,
        user_action='Click Set Up Video Studio again after Docker is Running.',
        layout=layout,
    )


def _heal_stale_installing(layout: StateLayout, state: dict[str, Any]) -> dict[str, Any]:
    """Watchdog: INSTALLING_COMFY without a real docker launch must not stick."""
    if state.get('phase') != INSTALLING_COMFY:
        return state
    if state.get('docker_launch_tried'):
        return state
    if _worker_alive():
        return state

    ia = state.get('install_action') or {}
    anchor = float(
        ia.get('requested_at')
        or state.get('installing_since')
        or state.get('updated_at')
        or 0.0
    )
    age = time.time() - anchor if anchor else _INSTALL_STALE_SEC + 1.0
    if age < _INSTALL_STALE_SEC:
        return state

    attempts = int(ia.get('dispatch_attempts') or 0)
    # Bound retries via start_studio_setup; fail hard after max.
    if attempts >= _INSTALL_MAX_DISPATCH:
        return _fail_install_did_not_start(
            state,
            layout,
            detail=f'stale {age:.0f}s without docker_launch_tried after {attempts} dispatch attempts',
        )

    # Re-dispatch (start_studio_setup preserves/increments dispatch_attempts).
    try:
        start_studio_setup(layout=layout, force=False, background=True)
    except Exception as exc:  # noqa: BLE001
        return _fail_install_did_not_start(state, layout, detail=repr(exc))
    return load_setup_state(layout)


def setup_status(layout: Optional[StateLayout] = None) -> dict[str, Any]:
    """Snapshot for UI poll — merges live probe when already READY."""
    layout = layout or resolve_layout()
    state = load_setup_state(layout)

    # Heal persisted running=true with dead worker (Cristo stuck INSTALLING_COMFY).
    if state.get('running') and not _worker_alive() and state.get('phase') in _ACTIVE_STATES:
        if state.get('phase') == INSTALLING_COMFY and not state.get('docker_launch_tried'):
            state = _heal_stale_installing(layout, state)
        else:
            # Worker died mid-flight with a real attempt — surface failure rather than spin.
            age = time.time() - float(state.get('updated_at') or 0.0)
            if age > max(_INSTALL_STALE_SEC * 4, 120.0) and state.get('phase') != READY:
                state['running'] = False
                if not state.get('error'):
                    state['error'] = 'Setup worker stopped unexpectedly'
                state = _set_phase(
                    state,
                    FAILED,
                    aria=(
                        "Video Studio setup stopped unexpectedly. "
                        "Click Set Up Video Studio to try again."
                    ),
                    message=state.get('error') or 'Setup interrupted',
                    error=state.get('error') or 'Setup worker stopped unexpectedly',
                    layout=layout,
                )
            else:
                state['running'] = False
                state = save_setup_state(state, layout=layout)

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
        'install_action': state.get('install_action') or _default_install_action(),
        'worker_alive': _worker_alive(),
        'hardware_profile': studio_hardware_snapshot(),
    }
    return {
        **state,
        'capability_state': live.state,
        'need_setup': live.state not in ('READY',),
        'under_spec': bool(state.get('under_spec') or (state.get('phase') == UNDER_SPEC)),
        'can_proceed_anyway': bool(
            state.get('can_proceed_anyway', True)
            or ((state.get('hardware_profile') or {}).get('can_proceed_anyway', True))
        ),
        'diagnostics': diagnostics,
        'steps': [
            {'id': k, 'label': label, 'done': bool((state.get('checklist') or {}).get(k))}
            for k, label in _CHECKLIST_ORDER
        ],
    }


def _clear_stale_studio_endpoint(layout: StateLayout) -> None:
    """After FAIL, drop prefs so caps show SETUP instead of sticky LIMITED."""
    try:
        clear_studio_endpoint(layout)
    except Exception:
        pass


def _kick_genome_install() -> None:
    """Genome is Expansion premium — Set Up Studio should not leave it not_configured on GPU hosts."""
    try:
        from expansion.capabilities.voice_trainer import ensure_genome
        ensure_genome(auto_install=True)
    except Exception:
        pass


def start_studio_setup(
    *,
    layout: Optional[StateLayout] = None,
    force: bool = False,
    background: bool = True,
    proceed_anyway: bool = False,
) -> dict[str, Any]:
    """Kick off (or resume) the orchestrator. Idempotent — one worker at a time.

    proceed_anyway: user acknowledged Aria's under-spec disclaimer and asked to
    bypass soft hardware guards (RAM GiB floor / performance warnings).
    """
    global _WORKER
    layout = layout or resolve_layout()
    with _LOCK:
        state = load_setup_state(layout)
        live = probe_video_studio(layout)
        if live.state == 'READY' and not force:
            st = setup_status(layout)
            return {**st, 'action': 'already_ready'}

        # In-process dedupe: prefer live worker over persisted flags (avoids races).
        if _worker_alive():
            return {**setup_status(layout), 'action': 'already_running'}

        state['attempt'] = int(state.get('attempt') or 0) + 1
        state['running'] = True
        state['error'] = ''
        state['technical'] = ''
        if proceed_anyway:
            state['proceed_anyway'] = True
            state['under_spec_acknowledged'] = True
        prior_dispatch = int((state.get('install_action') or {}).get('dispatch_attempts') or 0)
        state['docker_launch_tried'] = False
        state['desktop_launch_tried'] = False
        state['installing_since'] = 0.0
        state['install_action'] = _default_install_action()
        state['install_action']['dispatch_attempts'] = prior_dispatch
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
                # Parallel: Genome install on GPU hosts (does not block Comfy).
                threading.Thread(
                    target=_kick_genome_install, daemon=True, name='genome-with-studio',
                ).start()
                _orchestrate(layout, proceed_anyway=bool(proceed_anyway or state.get('proceed_anyway')))
            except Exception as exc:  # noqa: BLE001
                st = load_setup_state(layout)
                _mark_install_action(st, _INSTALL_FAILED, error=str(exc), layout=layout)
                st = load_setup_state(layout)
                _clear_stale_studio_endpoint(layout)
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
            if not _worker_alive():
                st = load_setup_state(layout)
                st = _fail_install_did_not_start(
                    st, layout, detail='background worker thread failed to start',
                )
                return {**setup_status(layout), 'action': 'dispatch_failed'}
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

        if not launched and not state.get('desktop_launch_tried'):
            launch = try_start_docker_desktop()
            state['desktop_launch_tried'] = True
            # Keep docker_launch_tried for Comfy provision only — do not set here.
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


def _orchestrate(layout: StateLayout, *, proceed_anyway: bool = False) -> None:
    state = load_setup_state(layout)
    if state.get('proceed_anyway') or state.get('under_spec_acknowledged'):
        proceed_anyway = True
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

    # VRAM-first Studio profile → CPU vs GPU compose + pack selection
    hw = studio_hardware_snapshot()
    try:
        os.environ['OTACON_STUDIO_COMFY'] = str(hw.get('comfy_runtime') or 'cpu')
        os.environ['OTACON_STUDIO_PROFILE'] = str(hw.get('profile_id') or '')
    except Exception:
        pass
    state['hardware_profile'] = {
        'profile_id': hw.get('profile_id'),
        'vram_gb': hw.get('vram_gb'),
        'marketed_vram_gb': hw.get('marketed_vram_gb'),
        'ram_gb': hw.get('ram_gb'),
        'marketed_ram_gb': hw.get('marketed_ram_gb'),
        'comfy_runtime': hw.get('comfy_runtime'),
        'under_spec': hw.get('under_spec'),
        'under_spec_reasons': hw.get('under_spec_reasons') or [],
        'performance_disclaimer': hw.get('performance_disclaimer') or '',
        'can_proceed_anyway': hw.get('can_proceed_anyway', True),
        'warnings': hw.get('warnings') or [],
    }
    save_setup_state(state, layout=layout)

    # Soft under-spec: pause for Aria disclaimer unless user already acknowledged.
    needs_ack = bool(hw.get('under_spec')) and not proceed_anyway
    # Also pause when auto_install is false due to soft RAM floor but packs exist.
    if needs_ack:
        disclaimer = hw.get('performance_disclaimer') or (
            "I'm sorry — this PC is under the comfortable Studio floor. "
            "You can still proceed, but performance may suffer."
        )
        state = _set_phase(
            state,
            UNDER_SPEC,
            aria=disclaimer,
            message='Hardware under recommended Studio floor — Aria needs your OK.',
            user_action='Read Aria’s note, then click “I understand — proceed anyway” if you want to continue.',
            error='',
            technical=json.dumps({
                'reasons': hw.get('under_spec_reasons') or [],
                'warnings': hw.get('warnings') or [],
                'ram_gb': hw.get('ram_gb'),
                'vram_gb': hw.get('vram_gb'),
            })[:1500],
            layout=layout,
        )
        state['running'] = False
        state['under_spec'] = True
        state['can_proceed_anyway'] = bool(hw.get('can_proceed_anyway', True))
        save_setup_state(state, layout=layout)
        return

    profile_aria = (
        f"Docker is ready. Hardware profile {hw.get('profile_id')} "
        f"({hw.get('marketed_vram_gb') or hw.get('vram_gb', 0):.0f} GB VRAM) — "
        f"Comfy {hw.get('comfy_runtime')}, "
        f"image={(hw.get('image') or {}).get('tier')}, "
        f"video={(hw.get('video') or {}).get('engine')}, "
        f"music={(hw.get('music') or {}).get('tier')}."
    )
    if proceed_anyway and hw.get('under_spec'):
        profile_aria = (
            "Understood — proceeding anyway with your acknowledgment. "
            + profile_aria
        )
    state = _set_phase(
        state,
        DOCKER_READY,
        aria=profile_aria,
        message=f"Docker ready · profile {hw.get('profile_id')}",
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
        # Still an actionable docker launch — mark before ensure.
        state = _mark_install_action(state, _INSTALL_REQUESTED, layout=layout)
        state = load_setup_state(layout)
        state['docker_launch_tried'] = True
        state = _mark_install_action(state, _INSTALL_STARTED, layout=layout)
        state = load_setup_state(layout)
    else:
        state = _transition_to_installing_comfy(
            state,
            layout,
            aria=(
                "Docker is ready. I'm setting up ComfyUI now — "
                "pulling the image and creating the otacon-comfyui container."
            ),
            message='Installing ComfyUI…',
        )

    # Immediate provision — INSTALLING_COMFY is never display-only.
    try:
        heal_docker_hub_auth()
        result = ensure_comfy_sidecar(wait_sec=90.0, layout=layout)
    except Exception as exc:  # noqa: BLE001
        state = load_setup_state(layout)
        _mark_install_action(state, _INSTALL_FAILED, error=str(exc), layout=layout)
        state = load_setup_state(layout)
        _set_phase(
            state,
            FAILED,
            aria="I couldn't start ComfyUI. Open Diagnostics for the Docker error.",
            message='ComfyUI provision failed.',
            error=str(exc),
            technical=repr(exc),
            layout=layout,
        )
        _clear_stale_studio_endpoint(layout)
        return

    state = load_setup_state(layout)
    if not result.get('ok'):
        action = result.get('action') or 'failed'
        hint = result.get('hint') or result.get('error') or 'Setup failed'
        tech = result.get('error') or ''
        # Daemon dropped mid-flight — re-enter wait rather than hard fail when Desktop exists
        if action in ('daemon_down', 'docker_daemon_down', 'missing', 'daemon_timeout'):
            state['desktop_launch_tried'] = False
            ok2, _ = _wait_docker_ready(state, layout, timeout_sec=120.0)
            if ok2:
                state = load_setup_state(layout)
                state['docker_launch_tried'] = True
                state = save_setup_state(state, layout=layout)
                result = ensure_comfy_sidecar(wait_sec=90.0, layout=layout)
                state = load_setup_state(layout)
        if not result.get('ok'):
            err = hint if hint else (result.get('error') or 'ComfyUI install failed')
            _mark_install_action(state, _INSTALL_FAILED, error=err, layout=layout)
            state = load_setup_state(layout)
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
            _clear_stale_studio_endpoint(layout)
            return

    _mark_install_action(state, _INSTALL_COMPLETED, layout=layout)
    state = load_setup_state(layout)

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
                FAILED,
                aria=(
                    "Studio's container started but ComfyUI never became healthy "
                    "(startup timeout). Check docker logs otacon-comfyui, then Set Up again."
                ),
                message='ComfyUI startup timeout.',
                error=f'endpoint never healthy: {detail}',
                technical=detail,
                layout=layout,
            )
            state = load_setup_state(layout)
            state['endpoint'] = ''
            save_setup_state(state, layout=layout)
            _clear_stale_studio_endpoint(layout)
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
    hw = studio_hardware_snapshot()
    assets = hw.get('assets') or required_studio_assets()
    state['hardware_profile'] = {
        'profile_id': hw.get('profile_id'),
        'vram_gb': hw.get('vram_gb'),
        'ram_gb': hw.get('ram_gb'),
        'comfy_runtime': hw.get('comfy_runtime'),
        'image': (hw.get('image') or {}).get('tier') if isinstance(hw.get('image'), dict) else None,
        'video': (hw.get('video') or {}).get('engine') if isinstance(hw.get('video'), dict) else None,
        'music': (hw.get('music') or {}).get('tier') if isinstance(hw.get('music'), dict) else None,
        'ltx2_eligible': hw.get('ltx2_eligible'),
        'assets': assets,
        'warnings': hw.get('warnings') or [],
    }
    save_setup_state(state, layout=layout)

    pack_bits = []
    img = hw.get('image') if isinstance(hw.get('image'), dict) else {}
    vid = hw.get('video') if isinstance(hw.get('video'), dict) else {}
    mus = hw.get('music') if isinstance(hw.get('music'), dict) else {}
    if img.get('enabled'):
        pack_bits.append(f"Z-Image ({img.get('tier')})")
    if vid.get('enabled'):
        pack_bits.append(f"{vid.get('engine')} ({vid.get('tier')})")
    if mus.get('enabled') and mus.get('tier') != 'deferred':
        pack_bits.append(f"ACE-Step ({mus.get('tier')})")
    pack_line = ', '.join(pack_bits) if pack_bits else 'connectivity only (packs deferred)'
    packs_note = (
        f' Profile packs: {pack_line}. '
        'Downloading creative weights into Comfy now (Z-Image first).'
        if pack_bits else
        ' Connectivity only for now (creative packs deferred on this profile).'
    )

    state = _set_phase(
        state,
        INSTALLING_MODELS,
        aria=(
            f"Hardware profile {hw.get('profile_id') or 'UNKNOWN'} "
            f"({hw.get('vram_gb', 0):.0f} GB VRAM).{packs_note}"
        ),
        message=f"Studio profile {hw.get('profile_id')} — installing creative packs…",
        layout=layout,
    )
    # Kick pack download (Z-Image / Wan·LTX-2 / ACE-Step). Non-blocking.
    pack_start: dict = {}
    try:
        from expansion.capabilities.studio_packs import start_pack_install, packs_status
        pack_start = start_pack_install(hw=hw, layout=layout)
        state['packs'] = packs_status(layout=layout, hw=hw, endpoint=endpoint)
        state['packs_started'] = bool(pack_start.get('started') or pack_start.get('running'))
        save_setup_state(state, layout=layout)
    except Exception as exc:  # noqa: BLE001
        state['packs_error'] = str(exc)[:240]
        save_setup_state(state, layout=layout)
    _ = assets
    state = _set_phase(
        state,
        VERIFYING,
        aria='Verifying Video Studio…',
        message='Running health checks…',
        checklist_key='components',
        layout=layout,
    )
    report = probe_video_studio(layout, clear_stale=False)
    if report.state == 'READY':
        state['endpoint'] = endpoint
        warn = (hw.get('warnings') or [])[:2]
        extra = (' ' + ' '.join(warn)) if warn else ''
        packs_ready = False
        packs_aria = ''
        try:
            from expansion.capabilities.studio_packs import packs_status as _ps
            pst = _ps(layout=layout, hw=hw, endpoint=endpoint)
            packs_ready = bool(pst.get('image_ready'))
            packs_aria = pst.get('aria') or ''
            state['packs'] = pst
        except Exception:
            packs_ready = False
        if packs_ready:
            ready_aria = (
                f"Done. Video Studio is connected (profile {hw.get('profile_id')}). "
                f"ComfyUI is healthy and Z-Image packs are ready.{extra}"
            )
            ready_msg = 'Video Studio ready — creative packs installed.'
        else:
            ready_aria = (
                f"Done. Video Studio is connected (profile {hw.get('profile_id')}). "
                f"ComfyUI is healthy. {packs_aria or packs_note}{extra}"
            )
            ready_msg = (
                'Video Studio connected — install creative packs in The Workshop '
                'before Generate unlocks.'
            )
        _set_phase(
            state,
            READY,
            aria=ready_aria,
            message=ready_msg,
            layout=layout,
        )
        state = load_setup_state(layout)
        for k, _ in _CHECKLIST_ORDER:
            state.setdefault('checklist', {})[k] = True
        state['ok'] = True
        state['running'] = False
        state['endpoint'] = endpoint
        state['hardware_profile'] = state.get('hardware_profile') or hw
        # Persist Keep-parity prompts/settings for Muse Creative
        try:
            from expansion.persist import atomic_write_json as _aw
            prefs = layout.user_preferences
            prefs.mkdir(parents=True, exist_ok=True)
            _aw(prefs / 'studio_creative_settings.json', {
                'profile_id': hw.get('profile_id'),
                'image': img,
                'video': vid,
                'music': mus,
                'defaults': hw.get('defaults') or {},
            })
        except Exception:
            pass
        save_setup_state(state, layout=layout)
        return
    _set_phase(
        state,
        FAILED if report.state != 'READY' else DEGRADED,
        aria=(
            "Video Studio is almost ready, but the connection check didn't pass yet. "
            "Click Set Up again in a moment."
        ),
        message=report.detail or 'Verification incomplete',
        error=report.detail,
        technical=json.dumps(report.discovery or {})[:1500],
        layout=layout,
    )
    _clear_stale_studio_endpoint(layout)
