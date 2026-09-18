"""Genome Voice Trainer — Expansion premium capability.

Genome is part of the Expansion premium product. Status is honest:
  ready         — UI listening on :8765
  offline       — installed (dir/image) but not listening
  unavailable   — no usable NVIDIA GPU
  not_configured — not installed yet
"""
from __future__ import annotations

import os
import shutil
import socket
import subprocess
from pathlib import Path
from typing import Optional

from expansion.capabilities import CapabilityReport, CapabilityState

CAPABILITY_ID = 'voice_trainer'
OWNER_AGENT = 'aria'
DEFAULT_PORT = 8765


def _vt_home() -> Path:
    override = (os.environ.get('OTACON_VT_DIR') or '').strip()
    if override:
        return Path(override).expanduser()
    return Path.home() / 'otacon-voice-trainer'


def _port_listening(port: int = DEFAULT_PORT, host: str = '127.0.0.1') -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.4):
            return True
    except OSError:
        return False


def _gpu_usable() -> bool:
    if not shutil.which('nvidia-smi'):
        return False
    try:
        r = subprocess.run(
            ['nvidia-smi'],
            capture_output=True,
            timeout=8,
            check=False,
        )
        return r.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _docker_image_present() -> bool:
    if not shutil.which('docker'):
        return False
    try:
        r = subprocess.run(
            ['docker', 'image', 'inspect', 'piper-voice-trainer:gpu'],
            capture_output=True,
            timeout=8,
            check=False,
        )
        return r.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def probe_voice_trainer() -> CapabilityReport:
    home = _vt_home()
    installed = home.is_dir() and any(home.iterdir())
    image = _docker_image_present()
    live = _port_listening()
    gpu = _gpu_usable()
    disc = {
        'path': str(home) if installed else '',
        'listening': live,
        'port': DEFAULT_PORT,
        'url': f'http://127.0.0.1:{DEFAULT_PORT}/' if live else '',
        'gpu': gpu,
        'docker_image': image,
        'premium': True,
        'product': 'expansion',
    }
    keys = [k for k, v in (('path', installed), ('docker_image', image), ('listening', live), ('gpu', gpu)) if v]

    if live:
        return CapabilityReport(
            CAPABILITY_ID, OWNER_AGENT, CapabilityState.READY.value,
            detail='Genome Voice Trainer UI listening (Expansion premium).',
            config_keys_present=keys, discovery=disc,
        )
    if installed or image:
        # Installed but UI down — Start is valid even if nvidia-smi is flaky in WSL.
        return CapabilityReport(
            CAPABILITY_ID, OWNER_AGENT, CapabilityState.DEGRADED.value,
            detail='Genome installed but UI not listening on :8765 — Start Genome (WSL GPU optional for UI).',
            config_keys_present=keys, discovery=disc,
        )
    if not gpu:
        return CapabilityReport(
            CAPABILITY_ID, OWNER_AGENT, CapabilityState.UNAVAILABLE.value,
            detail=(
                'Genome training needs NVIDIA visible in WSL (nvidia-smi). '
                'If Windows shows a GPU but WSL does not, run Fix-Otacon-GPU.bat, then re-open Ubuntu. '
                'You can still open Setup for guided steps.'
            ),
            config_keys_present=keys, discovery=disc,
        )
    return CapabilityReport(
        CAPABILITY_ID, OWNER_AGENT, CapabilityState.NOT_CONFIGURED.value,
        detail='Genome Voice Trainer not installed — Expansion premium; run guided Setup.',
        config_keys_present=keys, discovery=disc,
    )


def ensure_voice_trainer_ui(port: int = DEFAULT_PORT) -> dict:
    """Best-effort start of the Genome status UI if installed and not listening."""
    home = _vt_home()
    ui = home / 'ui'
    if _port_listening(port):
        return {'ok': True, 'action': 'already_listening', 'url': f'http://127.0.0.1:{port}/'}
    if not ui.is_dir():
        return {'ok': False, 'action': 'missing_ui', 'path': str(home)}
    log = Path('/tmp/otacon-vt-ui.log')
    try:
        proc = subprocess.Popen(
            ['python3', '-m', 'http.server', str(port), '--bind', '127.0.0.1'],
            cwd=str(ui),
            stdout=open(log, 'ab'),
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    except OSError as exc:
        return {'ok': False, 'action': 'start_failed', 'error': str(exc)}
    import time
    time.sleep(0.8)
    live = _port_listening(port)
    return {
        'ok': live,
        'action': 'started' if live else 'start_pending',
        'pid': proc.pid,
        'url': f'http://127.0.0.1:{port}/' if live else '',
        'log': str(log),
    }
