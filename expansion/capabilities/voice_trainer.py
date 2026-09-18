"""Genome Voice Trainer — Expansion premium capability.

Genome is part of the Expansion premium product. Status is honest:
  ready         — trainer UI listening on :8765
  offline       — installed (dir/image) but not listening
  unavailable   — no usable NVIDIA GPU
  not_configured — not installed yet

The :8765 UI is an actionable trainer (YouTube → Piper), not a static
"Voice Trainer ready" instruction page.
"""
from __future__ import annotations

import os
import socket
import subprocess
import threading
from pathlib import Path

from expansion.capabilities import CapabilityReport, CapabilityState
from expansion.capabilities.genome_ui import (
    start_train_job,
    train_state,
)

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


def ensure_voice_trainer_ui(port: int = DEFAULT_PORT) -> dict:
    """Write status.json, serve from install ui/ (or Genome trainer), verify READY gates."""
    from expansion.capabilities.voice_trainer_status import ensure_status_and_ui
    return ensure_status_and_ui(install_dir=_vt_home(), port=port, prefer_genome_ui=True)


def probe_voice_trainer() -> CapabilityReport:
    from expansion.capabilities.voice_trainer_status import (
        port_listening,
        verify_ui,
        write_status_json,
    )
    home = _vt_home()
    installed = home.is_dir() and any(home.iterdir())
    image = _docker_image_present()
    gpu = _gpu_usable()
    live = port_listening(DEFAULT_PORT)
    verified = False
    status_doc: dict = {}
    if live:
        # Repair missing status.json automatically when files exist.
        if installed and not (home / 'ui' / 'status.json').is_file():
            try:
                write_status_json(home)
            except OSError:
                pass
        check = verify_ui(DEFAULT_PORT, timeout=1.5)
        verified = bool(check.get('ok'))
        status_doc = check.get('status') or {}
        if not verified and installed:
            try:
                write_status_json(home)
                check = verify_ui(DEFAULT_PORT, timeout=1.5)
                verified = bool(check.get('ok'))
                status_doc = check.get('status') or {}
            except OSError:
                pass

    disc = {
        'path': str(home) if installed else '',
        'listening': live,
        'verified': verified,
        'port': DEFAULT_PORT,
        'url': f'http://127.0.0.1:{DEFAULT_PORT}/' if verified else '',
        'gpu': gpu,
        'docker_image': image,
        'premium': True,
        'product': 'expansion',
        'train': train_state(),
        'status': status_doc,
    }
    keys = [k for k, v in (('path', installed), ('docker_image', image), ('listening', live), ('gpu', gpu)) if v]

    if verified:
        return CapabilityReport(
            CAPABILITY_ID, OWNER_AGENT, CapabilityState.READY.value,
            detail='Genome Voice Trainer READY — / and status.json verified.',
            config_keys_present=keys, discovery=disc,
        )
    if live and not verified:
        return CapabilityReport(
            CAPABILITY_ID, OWNER_AGENT, CapabilityState.DEGRADED.value,
            detail=(
                'UI on :8765 but status.json missing or invalid — Start Genome repairs it '
                '(no reinstall needed).'
            ),
            config_keys_present=keys, discovery=disc,
        )
    if installed or image:
        return CapabilityReport(
            CAPABILITY_ID, OWNER_AGENT, CapabilityState.DEGRADED.value,
            detail='Genome installed but trainer UI not verified on :8765 — Start Genome.',
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
        'train': train_state(),
    }


def start_genome_train(*, name: str, urls: list[str]) -> dict:
    """Public train entry — Expansion API and Genome UI both use this."""
    return start_train_job(name=name, urls=list(urls or []))


def genome_train_status() -> dict:
    return train_state()


def ensure_genome(*, auto_install: bool = True) -> dict:
    """Autonomous path: install if needed (GPU), then start trainer UI."""
    report = probe_voice_trainer()
    home = _vt_home()
    installed = home.is_dir() and any(home.iterdir())
    if report.state == CapabilityState.READY.value:
        return {
            'ok': True,
            'action': 'ready',
            'url': (report.discovery or {}).get('url'),
            'state': report.state,
        }
    if not installed and auto_install and _gpu_usable():
        inst = install_voice_trainer()
        if not inst.get('ok') and inst.get('action') not in (
            'installing', 'already_installed', 'installed',
        ):
            return {**inst, 'state': probe_voice_trainer().state}
        if inst.get('action') == 'installing':
            return {**inst, 'state': 'INSTALLING'}
    if installed or _docker_image_present():
        ui = ensure_voice_trainer_ui()
        return {**ui, 'state': probe_voice_trainer().state}
    return {
        'ok': False,
        'action': 'not_ready',
        'state': report.state,
        'detail': report.detail,
    }


def install_voice_trainer(*, wait_sec: float = 0.0) -> dict:
    """Install Genome Voice Trainer (same script Expansion uses when GPU is visible).

    Runs in the background by default so the UI does not hang on docker pulls.
    After success, starts the actionable trainer UI automatically.
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
                'hint': 'Genome install already in progress — wait; trainer UI opens when done.',
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
            'Genome install started (docker image build can take several minutes). '
            'Stay on this page — the trainer UI opens on :8765 when ready.'
        ),
    }
