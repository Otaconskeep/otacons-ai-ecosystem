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
    from core.platform import _nvidia_smi_env, _resolve_nvidia_smi
    smi = _resolve_nvidia_smi()
    if not smi:
        return False
    try:
        r = subprocess.run(
            [smi],
            capture_output=True,
            timeout=8,
            check=False,
            env=_nvidia_smi_env(),
        )
        return r.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _docker_bin() -> str | None:
    from core.platform import _resolve_docker
    return _resolve_docker()


def _docker_image_present() -> bool:
    docker = _docker_bin()
    if not docker:
        return False
    from core.platform import docker_env
    try:
        r = subprocess.run(
            [docker, 'image', 'inspect', 'piper-voice-trainer:gpu'],
            capture_output=True,
            timeout=8,
            check=False,
            env=docker_env(),
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


_INSTALL_MARKER = Path('/tmp/otacon-genome-install.status')
_INSTALL_LOG = Path('/tmp/otacon-genome-install.log')
_INSTALLER_URL = os.environ.get(
    'OTACON_VOICE_TRAINER_URL',
    'https://raw.githubusercontent.com/Otaconskeep/otacon-voice-trainer/main/install_voice_trainer.sh',
)


def genome_install_status() -> dict:
    """Status of a background Genome install kicked off from Setup."""
    home = _vt_home()
    installed = home.is_dir() and any(home.iterdir())
    marker = ''
    if _INSTALL_MARKER.is_file():
        try:
            marker = _INSTALL_MARKER.read_text(encoding='utf-8', errors='replace').strip()
        except OSError:
            marker = ''
    return {
        'installed': installed,
        'path': str(home),
        'marker': marker,
        'log': str(_INSTALL_LOG) if _INSTALL_LOG.is_file() else '',
        'gpu': _gpu_usable(),
    }


def install_voice_trainer(*, wait_sec: float = 0.0) -> dict:
    """Install Genome Voice Trainer (same script Expansion uses when GPU is visible).

    Runs in the background by default so the UI does not hang on docker pulls.
    Poll via genome_install_status() / capabilities until path exists.
    """
    home = _vt_home()
    if home.is_dir() and any(home.iterdir()):
        ui = ensure_voice_trainer_ui()
        return {
            'ok': True,
            'action': 'already_installed',
            'path': str(home),
            **{k: ui[k] for k in ('url',) if k in ui},
        }
    if not _gpu_usable():
        return {
            'ok': False,
            'action': 'no_gpu',
            'error': 'NVIDIA not visible to this process (nvidia-smi).',
            'hint': (
                'Home SYSTEMS may still show a GPU via a hardened probe. '
                'Run Fix-Otacon-GPU.bat, reopen Ubuntu, soft-update Expansion, then Install Genome again.'
            ),
        }
    # Already installing?
    if _INSTALL_MARKER.is_file():
        try:
            st = _INSTALL_MARKER.read_text(encoding='utf-8', errors='replace').strip()
        except OSError:
            st = 'running'
        if st.startswith('running') or st.startswith('started'):
            return {
                'ok': True,
                'action': 'installing',
                'path': str(home),
                'log': str(_INSTALL_LOG),
                'hint': 'Genome install already in progress — wait, then Start Genome.',
            }

    env = dict(os.environ)
    try:
        from core.platform import docker_env, _nvidia_smi_env
        env.update(_nvidia_smi_env())
        env.update(docker_env())
    except Exception:
        pass
    env['OTACON_VT_DIR'] = str(home)
    env['OTACON_VT_SKIP_UI'] = '1'
    env['HOME'] = str(Path.home())

    try:
        _INSTALL_MARKER.write_text('started\n', encoding='utf-8')
        logf = open(_INSTALL_LOG, 'ab')
        proc = subprocess.Popen(
            ['bash', '-c', f'curl -fsSL --connect-timeout 30 --max-time 120 "{_INSTALLER_URL}" | bash'],
            env=env,
            stdout=logf,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    except OSError as exc:
        try:
            _INSTALL_MARKER.write_text(f'fail {exc}\n', encoding='utf-8')
        except OSError:
            pass
        return {'ok': False, 'action': 'start_failed', 'error': str(exc)}

    def _watch():
        rc = proc.wait()
        try:
            if rc == 0 and home.is_dir():
                _INSTALL_MARKER.write_text('ok\n', encoding='utf-8')
                ensure_voice_trainer_ui()
            else:
                _INSTALL_MARKER.write_text(f'fail rc={rc}\n', encoding='utf-8')
        except OSError:
            pass

    import threading
    threading.Thread(target=_watch, daemon=True, name='genome-install').start()

    if wait_sec and wait_sec > 0:
        import time
        deadline = time.time() + wait_sec
        while time.time() < deadline:
            if home.is_dir() and any(home.iterdir()):
                return {
                    'ok': True,
                    'action': 'installed',
                    'path': str(home),
                    **ensure_voice_trainer_ui(),
                }
            time.sleep(1.0)

    return {
        'ok': True,
        'action': 'installing',
        'pid': proc.pid,
        'path': str(home),
        'log': str(_INSTALL_LOG),
        'hint': (
            'Genome install started in the background (docker pull can take several minutes). '
            'Stay on this page — Status flips when ~/otacon-voice-trainer appears, then click Start Genome.'
        ),
    }
