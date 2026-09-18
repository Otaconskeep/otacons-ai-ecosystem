"""Voice Trainer status.json writer + UI verify/repair (Expansion).

Install directory is always resolved from the live user/env — never hardcoded
usernames like /home/crist/... .
"""
from __future__ import annotations

import json
import os
import shutil
import signal
import socket
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


DEFAULT_PORT = int(os.environ.get('OTACON_VT_UI_PORT') or '8765')
PID_NAME = '.otacon-vt-ui.pid'
LOG_PATH = Path('/tmp/otacon-vt-ui.log')


def resolve_install_dir(explicit: str | Path | None = None) -> Path:
    if explicit is not None and str(explicit).strip():
        return Path(str(explicit)).expanduser().resolve()
    env = (os.environ.get('OTACON_VT_DIR') or '').strip()
    if env:
        return Path(env).expanduser().resolve()
    return (Path.home() / 'otacon-voice-trainer').resolve()


def _nvidia_smi_bin() -> str | None:
    try:
        from core.platform import _resolve_nvidia_smi
        found = _resolve_nvidia_smi()
        if found:
            return found
    except Exception:
        pass
    wsl = Path('/usr/lib/wsl/lib/nvidia-smi')
    if wsl.is_file() and os.access(wsl, os.X_OK):
        return str(wsl)
    return shutil.which('nvidia-smi')


def _nvidia_env() -> dict[str, str]:
    env = dict(os.environ)
    try:
        from core.platform import _nvidia_smi_env
        env.update(_nvidia_smi_env())
    except Exception:
        lib = '/usr/lib/wsl/lib'
        if Path(lib).is_dir():
            prev = env.get('PATH', '')
            if lib not in prev.split(':'):
                env['PATH'] = f'{lib}:{prev}' if prev else lib
    return env


def probe_gpu() -> dict[str, Any]:
    smi = _nvidia_smi_bin()
    if not smi:
        return {
            'gpu_state': 'cpu_only',
            'gpu_name': None,
            'gpu_vram_mb': None,
            'gpu_probe_error': None,
        }
    try:
        r = subprocess.run(
            [smi, '--query-gpu=name,memory.total', '--format=csv,noheader,nounits'],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
            env=_nvidia_env(),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            'gpu_state': 'probe_failed',
            'gpu_name': None,
            'gpu_vram_mb': None,
            'gpu_probe_error': str(exc),
        }
    if r.returncode != 0:
        err = (r.stderr or r.stdout or f'nvidia-smi exit {r.returncode}').strip()[:500]
        return {
            'gpu_state': 'probe_failed',
            'gpu_name': None,
            'gpu_vram_mb': None,
            'gpu_probe_error': err or 'nvidia-smi failed',
        }
    lines = (r.stdout or '').strip().splitlines()
    if not lines:
        return {
            'gpu_state': 'probe_failed',
            'gpu_name': None,
            'gpu_vram_mb': None,
            'gpu_probe_error': 'nvidia-smi returned empty GPU list',
        }
    parts = [p.strip() for p in lines[0].split(',')]
    name = parts[0] if parts else ''
    vram: int | None = None
    if len(parts) > 1:
        try:
            vram = int(float(parts[1]))
        except ValueError:
            vram = None
    if not name:
        return {
            'gpu_state': 'probe_failed',
            'gpu_name': None,
            'gpu_vram_mb': None,
            'gpu_probe_error': 'nvidia-smi returned blank GPU name',
        }
    return {
        'gpu_state': 'gpu_detected',
        'gpu_name': name,
        'gpu_vram_mb': vram,
        'gpu_probe_error': None,
    }


def detect_image() -> str | None:
    try:
        from core.platform import _resolve_docker, docker_env
        docker = _resolve_docker()
        env = docker_env()
    except Exception:
        docker, env = shutil.which('docker'), None
    if not docker:
        return None
    for tag in ('piper-voice-trainer:gpu', 'piper-voice-trainer:latest'):
        try:
            r = subprocess.run(
                [docker, 'image', 'inspect', tag],
                capture_output=True,
                timeout=8,
                check=False,
                env=env,
            )
            if r.returncode == 0:
                return tag
        except (OSError, subprocess.TimeoutExpired):
            continue
    return None


def build_status(install_dir: Path | None = None) -> dict[str, Any]:
    root = resolve_install_dir(install_dir)
    gpu = probe_gpu()
    image = detect_image()
    ui_dir = root / 'ui'
    installed = root.is_dir() and (ui_dir.is_dir() or any(root.iterdir()) if root.is_dir() else False)
    payload: dict[str, Any] = {
        'ok': bool(installed or image),
        'product': 'Otacon Voice Trainer',
        'gpu_name': gpu['gpu_name'],
        'gpu_vram_mb': gpu['gpu_vram_mb'],
        'gpu_state': gpu['gpu_state'],
        'image': image,
        'install_dir': str(root),
        'wsl': _is_wsl(),
        'docs': 'https://github.com/Otaconskeep/otacon-voice-trainer',
        'site': 'https://otaconskeep-site.otaconskeep.workers.dev/otacon/#voice-trainer',
    }
    if gpu.get('gpu_probe_error'):
        payload['gpu_probe_error'] = gpu['gpu_probe_error']
    return payload


def _is_wsl() -> bool:
    if Path('/proc/sys/fs/binfmt_misc/WSLInterop').exists():
        return True
    try:
        return 'microsoft' in Path('/proc/version').read_text(encoding='utf-8', errors='ignore').lower()
    except OSError:
        return False


def write_status_json(install_dir: Path | None = None) -> dict[str, Any]:
    root = resolve_install_dir(install_dir)
    ui_dir = root / 'ui'
    ui_dir.mkdir(parents=True, exist_ok=True)
    payload = build_status(root)
    # Prefer ok=true once ui/ exists (repair path).
    if ui_dir.is_dir():
        payload['ok'] = True
    path = ui_dir / 'status.json'
    path.write_text(json.dumps(payload, indent=2) + '\n', encoding='utf-8')
    return {'path': str(path), 'status': payload, 'install_dir': str(root)}


def port_listening(port: int = DEFAULT_PORT, host: str = '127.0.0.1') -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.4):
            return True
    except OSError:
        return False


def verify_ui(port: int = DEFAULT_PORT, timeout: float = 3.0) -> dict[str, Any]:
    base = f'http://127.0.0.1:{port}'
    out: dict[str, Any] = {
        'ok': False,
        'index_ok': False,
        'status_ok': False,
        'status': None,
        'error': '',
    }
    deadline = time.time() + timeout
    last_err = ''
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f'{base}/', timeout=1.5) as resp:
                out['index_ok'] = int(resp.status) == 200
            with urllib.request.urlopen(f'{base}/status.json', timeout=1.5) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                out['status'] = data
                out['status_ok'] = int(resp.status) == 200 and isinstance(data, dict) and bool(data.get('ok'))
            if out['index_ok'] and out['status_ok']:
                out['ok'] = True
                return out
            last_err = 'index or status.json check failed'
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError, OSError) as exc:
            last_err = str(exc)
        time.sleep(0.2)
    out['error'] = last_err or 'verify timeout'
    return out


def _read_pid(ui_dir: Path) -> int | None:
    path = ui_dir / PID_NAME
    if not path.is_file():
        return None
    try:
        return int(path.read_text(encoding='utf-8').strip())
    except (OSError, ValueError):
        return None


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _cmdline(pid: int) -> str:
    try:
        return Path(f'/proc/{pid}/cmdline').read_bytes().replace(b'\x00', b' ').decode('utf-8', 'replace')
    except OSError:
        return ''


def _cwd(pid: int) -> str:
    try:
        return os.readlink(f'/proc/{pid}/cwd')
    except OSError:
        return ''


def _is_owned_server(pid: int, ui_dir: Path) -> bool:
    if _read_pid(ui_dir) == pid:
        return True
    cmd = _cmdline(pid)
    if 'http.server' not in cmd and 'start_ui' not in cmd:
        return False
    cwd = _cwd(pid)
    return bool(cwd) and Path(cwd).resolve() == ui_dir.resolve()


def _start_http_from_ui(ui_dir: Path, port: int) -> int:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    logf = open(LOG_PATH, 'ab')
    proc = subprocess.Popen(
        ['python3', '-m', 'http.server', str(port), '--bind', '127.0.0.1'],
        cwd=str(ui_dir),
        stdout=logf,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    (ui_dir / PID_NAME).write_text(str(proc.pid) + '\n', encoding='utf-8')
    return proc.pid


def ensure_status_and_ui(
    *,
    install_dir: Path | None = None,
    port: int = DEFAULT_PORT,
    prefer_genome_ui: bool = True,
) -> dict[str, Any]:
    """Write status.json, ensure UI serves from install ui/, verify READY gates."""
    root = resolve_install_dir(install_dir)
    ui_dir = root / 'ui'
    written = write_status_json(root)

    # Prefer Expansion genome trainer UI when available (train form + status.json).
    if prefer_genome_ui:
        try:
            from expansion.capabilities.genome_ui import ensure_genome_ui
            # genome_ui will call back into build_status via status_payload after we patch it.
            g = ensure_genome_ui(port=port)
            if g.get('ok'):
                # Always refresh on-disk status.json for static clients / repair.
                write_status_json(root)
                check = verify_ui(port)
                if check['ok']:
                    return {
                        'ok': True,
                        'action': g.get('action') or 'genome_ui',
                        'url': g.get('url') or f'http://127.0.0.1:{port}/',
                        'install_dir': str(root),
                        'status_json': written['path'],
                        'verify': check,
                    }
                # Port may be foreign genome-less server — fall through to repair.
                if g.get('action') == 'port_busy_foreign':
                    return {
                        'ok': False,
                        'action': 'port_conflict',
                        'error': g.get('error') or f'Port {port} occupied by unrelated process',
                        'hint': g.get('hint') or 'Free the port; refusing to kill foreign process.',
                        'install_dir': str(root),
                    }
        except Exception:
            pass

    if not ui_dir.is_dir():
        return {
            'ok': False,
            'action': 'missing_ui',
            'error': f'UI directory missing at {ui_dir}',
            'install_dir': str(root),
            'status_json': written['path'],
        }

    if port_listening(port):
        check = verify_ui(port)
        if check['ok']:
            return {
                'ok': True,
                'action': 'already_ready',
                'url': f'http://127.0.0.1:{port}/',
                'install_dir': str(root),
                'status_json': written['path'],
                'verify': check,
            }
        # Repair: regenerate status.json without killing anything.
        write_status_json(root)
        check2 = verify_ui(port, timeout=2.0)
        if check2['ok']:
            return {
                'ok': True,
                'action': 'repaired_status_json',
                'url': f'http://127.0.0.1:{port}/',
                'install_dir': str(root),
                'status_json': written['path'],
                'verify': check2,
            }
        owned = _read_pid(ui_dir)
        if owned and _pid_alive(owned) and _is_owned_server(owned, ui_dir):
            try:
                os.kill(owned, signal.SIGTERM)
            except OSError:
                pass
            time.sleep(0.4)
        elif port_listening(port):
            return {
                'ok': False,
                'action': 'port_conflict',
                'error': (
                    f'Port {port} is in use by another process and does not serve valid '
                    f'status.json. Refusing to kill it.'
                ),
                'hint': f'Stop the foreign listener on :{port}, then Start Genome again.',
                'install_dir': str(root),
                'verify': check2,
            }

    if port_listening(port):
        return {
            'ok': False,
            'action': 'port_conflict',
            'error': f'Port {port} still occupied',
            'install_dir': str(root),
        }

    pid = _start_http_from_ui(ui_dir, port)
    time.sleep(0.5)
    check = verify_ui(port)
    if not check['ok']:
        return {
            'ok': False,
            'action': 'verify_failed',
            'pid': pid,
            'error': check.get('error') or 'UI started but / or status.json failed',
            'install_dir': str(root),
            'status_json': written['path'],
            'verify': check,
            'log': str(LOG_PATH),
        }
    return {
        'ok': True,
        'action': 'started',
        'pid': pid,
        'url': f'http://127.0.0.1:{port}/',
        'install_dir': str(root),
        'status_json': written['path'],
        'verify': check,
    }
