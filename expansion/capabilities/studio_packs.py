"""Studio creative pack installer — Z-Image / Wan·LTX-2 / ACE-Step weights.

Keep Workshop parity: download the same Comfy-Org split files into the live
ComfyUI models tree. Setup may kick this; Workshop exposes Install packs.

Honest UX contract:
  - Missing packs are a soft block (install CTA), never a confusing rejected job.
  - Connectivity READY ≠ packs installed.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Optional

from expansion.persist import atomic_write_json
from expansion.state_layout import StateLayout, resolve_layout

# Official Comfy-Org template assets (same sources as Keep Workshop downloaders).
ZIMAGE_FILES = [
    {
        'repo': 'Comfy-Org/z_image_turbo',
        'remote': 'split_files/diffusion_models/z_image_turbo_bf16.safetensors',
        'subdir': 'diffusion_models',
        'name': 'z_image_turbo_bf16.safetensors',
        'min_bytes': 1_000_000_000,
    },
    {
        'repo': 'Comfy-Org/z_image_turbo',
        'remote': 'split_files/text_encoders/qwen_3_4b.safetensors',
        'subdir': 'text_encoders',
        'name': 'qwen_3_4b.safetensors',
        'min_bytes': 100_000_000,
    },
    {
        'repo': 'Comfy-Org/z_image_turbo',
        'remote': 'split_files/vae/ae.safetensors',
        'subdir': 'vae',
        'name': 'ae.safetensors',
        'min_bytes': 100_000,
    },
]

WAN_FILES = [
    {
        'repo': 'Comfy-Org/Wan_2.2_ComfyUI_Repackaged',
        'remote': 'split_files/diffusion_models/wan2.2_ti2v_5B_fp16.safetensors',
        'subdir': 'diffusion_models',
        'name': 'wan2.2_ti2v_5B_fp16.safetensors',
        'min_bytes': 1_000_000_000,
    },
    {
        'repo': 'Comfy-Org/Wan_2.2_ComfyUI_Repackaged',
        'remote': 'split_files/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors',
        'subdir': 'text_encoders',
        'name': 'umt5_xxl_fp8_e4m3fn_scaled.safetensors',
        'min_bytes': 100_000_000,
    },
    {
        'repo': 'Comfy-Org/Wan_2.2_ComfyUI_Repackaged',
        'remote': 'split_files/vae/wan2.2_vae.safetensors',
        'subdir': 'vae',
        'name': 'wan2.2_vae.safetensors',
        'min_bytes': 100_000,
    },
]

# Distilled LTX-2.3 path used on high-VRAM Keep hosts (Keep downloader parity).
LTX2_FILES = [
    {
        'repo': 'Kijai/LTX2.3_comfy',
        'remote': 'diffusion_models/ltx-2.3-22b-distilled-1.1_transformer_only_mxfp8_block32.safetensors',
        'subdir': 'diffusion_models',
        'name': 'ltx-2.3-22b-distilled-1.1_transformer_only_mxfp8_block32.safetensors',
        'min_bytes': 1_000_000_000,
    },
    {
        'repo': 'Kijai/LTX2.3_comfy',
        'remote': 'vae/taeltx2_3.safetensors',
        'subdir': 'vae',
        'name': 'taeltx2_3.safetensors',
        'min_bytes': 100_000,
    },
    {
        'repo': 'Kijai/LTX2.3_comfy',
        'remote': 'text_encoders/ltx-2.3_text_projection_bf16.safetensors',
        'subdir': 'checkpoints',
        'name': 'ltx-2.3_text_projection_bf16.safetensors',
        'min_bytes': 1_000_000,
    },
    {
        'repo': 'Comfy-Org/ltx-2',
        'remote': 'split_files/text_encoders/gemma_3_12B_it_fp4_mixed.safetensors',
        'subdir': 'text_encoders',
        'name': 'gemma_3_12B_it_fp4_mixed.safetensors',
        'min_bytes': 100_000_000,
    },
]

ACE_FILES = [
    {
        'repo': 'Comfy-Org/ace_step_1.5_ComfyUI_files',
        'remote': 'checkpoints/ace_step_1.5_turbo_aio.safetensors',
        'subdir': 'checkpoints',
        'name': 'ace_step_1.5_turbo_aio.safetensors',
        'min_bytes': 100_000_000,
    },
]

_INSTALL_LOCK = threading.Lock()
_INSTALL_THREAD: Optional[threading.Thread] = None


def _packs_state_path(layout: Optional[StateLayout] = None) -> Path:
    layout = layout or resolve_layout()
    layout.user_preferences.mkdir(parents=True, exist_ok=True)
    return layout.user_preferences / 'studio_packs.json'


def load_packs_state(layout: Optional[StateLayout] = None) -> dict[str, Any]:
    path = _packs_state_path(layout)
    if not path.is_file():
        return {
            'phase': 'NOT_STARTED',
            'running': False,
            'ok': False,
            'packs': {},
            'aria': '',
            'message': '',
            'models_root': '',
            'updated_at': 0,
        }
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {'phase': 'UNKNOWN', 'running': False, 'ok': False, 'packs': {}}


def save_packs_state(state: dict[str, Any], layout: Optional[StateLayout] = None) -> None:
    state = dict(state)
    state['updated_at'] = time.time()
    atomic_write_json(_packs_state_path(layout), state)


def _docker_bin() -> Optional[str]:
    try:
        from core.platform import _resolve_docker
        return _resolve_docker()
    except Exception:
        return shutil.which('docker')


def _docker_volume_mountpoint(name: str) -> Optional[Path]:
    docker = _docker_bin()
    if not docker:
        return None
    try:
        out = subprocess.check_output(
            [docker, 'volume', 'inspect', name, '--format', '{{.Mountpoint}}'],
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=8,
        ).strip()
        if out and out != '<no value>':
            p = Path(out)
            if p.is_dir():
                return p
    except (subprocess.SubprocessError, OSError, FileNotFoundError):
        return None
    return None


def _container_models_via_exec() -> Optional[Path]:
    """Return None — used only to discover path string inside container."""
    return None


def resolve_models_root() -> Path:
    """Host path where ComfyUI model files should land."""
    env = (os.environ.get('OTACON_COMFY_MODELS') or '').strip()
    if env:
        p = Path(env).expanduser()
        p.mkdir(parents=True, exist_ok=True)
        return p

    for vol in ('otacon-comfy-models', 'otacon-comfy-data'):
        mp = _docker_volume_mountpoint(vol)
        if not mp:
            continue
        if vol.endswith('models'):
            mp.mkdir(parents=True, exist_ok=True)
            return mp
        for cand in (
            mp / 'ComfyUI' / 'models',
            mp / 'comfyui' / 'models',
            mp / 'models',
        ):
            parent = cand.parent
            if parent.is_dir() or vol == 'otacon-comfy-data':
                cand.mkdir(parents=True, exist_ok=True)
                return cand

    # Host cache; sync into container after download when possible.
    fallback = Path.home() / '.local' / 'share' / 'otacon' / 'comfy' / 'models'
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


def _file_ok(path: Path, min_bytes: int = 1) -> bool:
    try:
        return path.is_file() and path.stat().st_size >= min_bytes
    except OSError:
        return False


def _pack_files_status(files: list[dict[str, Any]], root: Path) -> dict[str, Any]:
    present: list[str] = []
    missing: list[str] = []
    for spec in files:
        dest = root / spec['subdir'] / spec['name']
        if _file_ok(dest, int(spec.get('min_bytes') or 1)):
            present.append(spec['name'])
        else:
            missing.append(f"{spec['subdir']}/{spec['name']}")
    return {
        'ok': not missing,
        'present': present,
        'missing': missing,
        'files_total': len(files),
        'files_ready': len(present),
    }


def _profile_pack_specs(hw: Optional[dict[str, Any]] = None) -> list[dict[str, Any]]:
    """Which packs this host should install (hardware_profile driven)."""
    if hw is None:
        try:
            from expansion.capabilities.studio_setup import studio_hardware_snapshot
            hw = studio_hardware_snapshot()
        except Exception:
            hw = {}
    img = hw.get('image') if isinstance(hw.get('image'), dict) else {}
    vid = hw.get('video') if isinstance(hw.get('video'), dict) else {}
    mus = hw.get('music') if isinstance(hw.get('music'), dict) else {}
    specs: list[dict[str, Any]] = []
    if img.get('enabled', True):
        specs.append({
            'id': 'zimage',
            'kind': 'image',
            'label': 'Z-Image Turbo',
            'engine': img.get('engine') or 'z-image-turbo',
            'files': ZIMAGE_FILES,
            'disk_gb': 25,
            'priority': 1,
        })
    if vid.get('enabled', True):
        ltx2 = bool(hw.get('ltx2_eligible'))
        if ltx2:
            specs.append({
                'id': 'ltx2',
                'kind': 'video',
                'label': 'LTX-2',
                'engine': vid.get('engine') or 'ltx-2',
                'files': LTX2_FILES,
                'disk_gb': 100,
                'priority': 2,
                'note': 'High-VRAM LTX-2 distilled weights',
            })
        else:
            specs.append({
                'id': 'wan',
                'kind': 'video',
                'label': 'Wan 2.2 5B',
                'engine': vid.get('engine') or 'wan-2.2-5b',
                'files': WAN_FILES,
                'disk_gb': 45,
                'priority': 2,
            })
    if mus.get('enabled') and mus.get('tier') != 'deferred':
        specs.append({
            'id': 'ace_step',
            'kind': 'music',
            'label': 'ACE-Step 1.5',
            'engine': mus.get('engine') or 'ace-step',
            'files': ACE_FILES,
            'disk_gb': 12,
            'priority': 3,
        })
    elif not mus or mus.get('enabled', True):
        # Default: still offer ACE when profile silent (friends expect music pack).
        if not any(s['id'] == 'ace_step' for s in specs):
            specs.append({
                'id': 'ace_step',
                'kind': 'music',
                'label': 'ACE-Step 1.5',
                'engine': 'ace-step',
                'files': ACE_FILES,
                'disk_gb': 12,
                'priority': 3,
            })
    specs.sort(key=lambda s: int(s.get('priority') or 99))
    return specs


def seed_workflow_assets() -> dict[str, Any]:
    """Ensure Expansion ships workflow meta stubs next to the Z-Image API graph."""
    root = Path(__file__).resolve().parents[1] / 'product' / 'studio' / 'workflows'
    root.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    metas = {
        'z_image_turbo_api.meta.json': {
            'id': 'z_image_turbo_api',
            'modality': 'image',
            'engine': 'z-image-turbo',
            'required_models': {
                'unet': 'z_image_turbo_bf16.safetensors',
                'clip': 'qwen_3_4b.safetensors',
                'vae': 'ae.safetensors',
            },
            'notes': 'API-format Z-Image Turbo graph (Keep workshop parity).',
        },
        'wan_2_2_5b_api.meta.json': {
            'id': 'wan_2_2_5b_api',
            'modality': 'video',
            'engine': 'wan-2.2-5b',
            'required_models': {
                'unet': 'wan2.2_ti2v_5B_fp16.safetensors',
                'clip': 'umt5_xxl_fp8_e4m3fn_scaled.safetensors',
                'vae': 'wan2.2_vae.safetensors',
            },
            'notes': 'Wan 2.2 TI2V 5B pack (weights + future submitter).',
        },
        'ltx2_api.meta.json': {
            'id': 'ltx2_api',
            'modality': 'video',
            'engine': 'ltx-2',
            'required_models': {
                'unet': 'ltx-2.3-22b-distilled-1.1_transformer_only_mxfp8_block32.safetensors',
            },
            'notes': 'LTX-2 distilled pack for high-VRAM hosts.',
        },
        'ace_step_1_5_api.meta.json': {
            'id': 'ace_step_1_5_api',
            'modality': 'music',
            'engine': 'ace-step',
            'required_models': {
                'checkpoint': 'ace_step_1.5_turbo_aio.safetensors',
            },
            'notes': 'ACE-Step 1.5 AIO music pack (Keep workshop parity).',
        },
    }
    for name, body in metas.items():
        path = root / name
        if not path.is_file():
            path.write_text(json.dumps(body, indent=2) + '\n', encoding='utf-8')
            written.append(name)
    return {'ok': True, 'dir': str(root), 'written': written}


def packs_status(
    *,
    layout: Optional[StateLayout] = None,
    endpoint: Optional[str] = None,
    hw: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Live status of creative packs (disk + optional Comfy probe for image)."""
    seed_workflow_assets()
    root = resolve_models_root()
    specs = _profile_pack_specs(hw)
    state = load_packs_state(layout)
    packs: dict[str, Any] = {}
    all_ok = True
    needed: list[str] = []
    for spec in specs:
        disk = _pack_files_status(spec['files'], root)
        # Image: also trust live Comfy listing when READY (models may live only in container).
        live_ok = False
        if spec['id'] == 'zimage' and endpoint:
            try:
                from expansion.capabilities.comfy_submit import image_workflow_status
                live = image_workflow_status(endpoint)
                live_ok = bool(live.get('ok'))
                if live_ok:
                    disk = {
                        **disk,
                        'ok': True,
                        'missing': [],
                        'live_comfy': True,
                        'detail': live.get('detail'),
                    }
            except Exception:
                pass
        ok = bool(disk.get('ok'))
        if not ok:
            all_ok = False
            needed.append(spec['id'])
        packs[spec['id']] = {
            'id': spec['id'],
            'kind': spec['kind'],
            'label': spec['label'],
            'engine': spec['engine'],
            'disk_gb': spec.get('disk_gb'),
            'ok': ok,
            'missing': disk.get('missing') or [],
            'present': disk.get('present') or [],
            'files_ready': disk.get('files_ready', 0),
            'files_total': disk.get('files_total', 0),
            'live_comfy': bool(disk.get('live_comfy')),
        }
    image_ok = bool((packs.get('zimage') or {}).get('ok'))
    running = bool(state.get('running'))
    phase = state.get('phase') or ('READY' if all_ok else 'MISSING')
    if running:
        phase = state.get('phase') or 'DOWNLOADING'
    if image_ok and not all_ok:
        aria = (
            'Z-Image is ready. Video / music packs are still optional — '
            'tap Install packs if you want those too.'
        )
    elif image_ok and all_ok:
        aria = 'Creative packs are installed. Generate is ready when Studio is LIVE.'
    elif running:
        aria = state.get('aria') or (
            'Downloading creative packs now — Z-Image first, then video and music. '
            'Generate will unlock when Z-Image finishes.'
        )
    else:
        aria = (
            'Creative model packs are not installed yet. Tap Install packs — '
            'I will download Z-Image (and video / music for this PC). '
            'Generate stays quiet until packs are ready; nothing is queued.'
        )
    return {
        'ok': all_ok,
        'image_ready': image_ok,
        'generate_ready': image_ok,
        'needed': needed,
        'packs': packs,
        'models_root': str(root),
        'phase': phase,
        'running': running,
        'progress': state.get('progress') or {},
        'aria': aria,
        'message': state.get('message') or aria,
        'soft_block': not image_ok,
        'action': '' if image_ok else 'install_packs',
        'workflows': seed_workflow_assets(),
    }


def _hf_url(repo: str, remote: str) -> str:
    return f'https://huggingface.co/{repo}/resolve/main/{remote}'


def _download_file(url: str, dest: Path, *, min_bytes: int = 1) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(dest.suffix + '.part')
    headers = {'User-Agent': 'Otacon-Expansion-StudioPacks/1.0'}
    token = (os.environ.get('HF_TOKEN') or os.environ.get('HUGGING_FACE_HUB_TOKEN') or '').strip()
    if token:
        headers['Authorization'] = f'Bearer {token}'
    # Resume if partial exists.
    existing = part.stat().st_size if part.is_file() else 0
    if existing:
        headers['Range'] = f'bytes={existing}-'
    req = urllib.request.Request(url, headers=headers, method='GET')
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            mode = 'ab' if existing and resp.status == 206 else 'wb'
            if mode == 'wb' and part.is_file():
                part.unlink(missing_ok=True)
            with open(part, mode) as fh:
                while True:
                    chunk = resp.read(1024 * 1024)
                    if not chunk:
                        break
                    fh.write(chunk)
    except urllib.error.HTTPError as exc:
        if exc.code == 416 and part.is_file():
            pass  # already complete range
        else:
            raise
    if not _file_ok(part, min_bytes):
        raise RuntimeError(f'download incomplete: {dest.name} ({part.stat().st_size if part.is_file() else 0} bytes)')
    part.replace(dest)


def _try_hf_hub(spec: dict[str, Any], dest_dir: Path) -> bool:
    try:
        from huggingface_hub import hf_hub_download  # type: ignore
    except ImportError:
        return False
    dest_dir.mkdir(parents=True, exist_ok=True)
    path = hf_hub_download(
        repo_id=spec['repo'],
        filename=spec['remote'],
        local_dir=str(dest_dir),
        token=os.environ.get('HF_TOKEN') or os.environ.get('HUGGING_FACE_HUB_TOKEN'),
    )
    flat = dest_dir / spec['name']
    p = Path(path)
    if p.resolve() != flat.resolve():
        if flat.exists():
            flat.unlink()
        # hf may nest under local_dir/remote path
        nested = dest_dir / spec['remote']
        src = nested if nested.is_file() else p
        if src.is_file():
            shutil.move(str(src), str(flat))
            # prune empty nest
            try:
                if nested.parent != dest_dir and nested.parent.is_dir():
                    shutil.rmtree(nested.parent, ignore_errors=True)
            except OSError:
                pass
    return _file_ok(flat, int(spec.get('min_bytes') or 1))


def _sync_into_comfy_container(root: Path) -> dict[str, Any]:
    """If models landed on host cache, docker cp into running otacon-comfyui."""
    docker = _docker_bin()
    if not docker:
        return {'ok': False, 'action': 'no_docker'}
    try:
        running = subprocess.check_output(
            [docker, 'inspect', '-f', '{{.State.Running}}', 'otacon-comfyui'],
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=8,
        ).strip()
    except (subprocess.SubprocessError, OSError):
        return {'ok': False, 'action': 'no_container'}
    if running != 'true':
        return {'ok': False, 'action': 'container_stopped'}
    # Discover models path inside container
    candidates = [
        '/root/ComfyUI/models',
        '/ComfyUI/models',
        '/root/models',
    ]
    target = ''
    for cand in candidates:
        try:
            code = subprocess.call(
                [docker, 'exec', 'otacon-comfyui', 'test', '-d', cand],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=8,
            )
            if code == 0:
                target = cand
                break
        except (subprocess.SubprocessError, OSError):
            continue
    if not target:
        # create default
        target = '/root/ComfyUI/models'
        try:
            subprocess.check_call(
                [docker, 'exec', 'otacon-comfyui', 'mkdir', '-p', target],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=15,
            )
        except (subprocess.SubprocessError, OSError) as exc:
            return {'ok': False, 'action': 'mkdir_failed', 'error': str(exc)}
    copied = 0
    for sub in ('diffusion_models', 'text_encoders', 'vae', 'checkpoints', 'loras'):
        src = root / sub
        if not src.is_dir():
            continue
        try:
            subprocess.check_call(
                [docker, 'exec', 'otacon-comfyui', 'mkdir', '-p', f'{target}/{sub}'],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=15,
            )
            for f in src.iterdir():
                if not f.is_file() or f.name.endswith('.part'):
                    continue
                subprocess.check_call(
                    [docker, 'cp', str(f), f'otacon-comfyui:{target}/{sub}/{f.name}'],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=600,
                )
                copied += 1
        except (subprocess.SubprocessError, OSError):
            continue
    return {'ok': True, 'action': 'docker_cp', 'copied': copied, 'target': target}


def _install_one_file(spec: dict[str, Any], root: Path, on_progress) -> None:
    dest = root / spec['subdir'] / spec['name']
    if _file_ok(dest, int(spec.get('min_bytes') or 1)):
        on_progress(f"already present: {spec['name']}")
        return
    on_progress(f"fetching {spec['name']}…")
    if _try_hf_hub(spec, root / spec['subdir']):
        on_progress(f"ready: {spec['name']}")
        return
    url = _hf_url(spec['repo'], spec['remote'])
    _download_file(url, dest, min_bytes=int(spec.get('min_bytes') or 1))
    on_progress(f"ready: {spec['name']}")


def _run_install(
    *,
    layout: StateLayout,
    which: Optional[list[str]] = None,
    hw: Optional[dict[str, Any]] = None,
) -> None:
    root = resolve_models_root()
    specs = _profile_pack_specs(hw)
    if which:
        wanted = set(which)
        specs = [s for s in specs if s['id'] in wanted]
    # Always prefer Z-Image first when present in selection
    specs.sort(key=lambda s: (0 if s['id'] == 'zimage' else int(s.get('priority') or 99)))

    state = load_packs_state(layout)
    state.update({
        'running': True,
        'ok': False,
        'phase': 'DOWNLOADING',
        'models_root': str(root),
        'aria': (
            'Downloading creative packs — Z-Image first so Generate can unlock, '
            'then video and music.'
        ),
        'message': 'Downloading creative packs…',
        'progress': {'pack': '', 'file': '', 'done': 0, 'total': 0},
        'error': '',
    })
    save_packs_state(state, layout)

    total_files = sum(len(s['files']) for s in specs) or 1
    done = 0

    def on_progress(msg: str) -> None:
        nonlocal done
        st = load_packs_state(layout)
        st['message'] = msg
        st['aria'] = msg
        st['progress'] = {
            **(st.get('progress') or {}),
            'file': msg,
            'done': done,
            'total': total_files,
        }
        save_packs_state(st, layout)

    try:
        for spec in specs:
            on_progress(f"Installing {spec['label']}…")
            st = load_packs_state(layout)
            st['progress'] = {
                'pack': spec['id'],
                'label': spec['label'],
                'done': done,
                'total': total_files,
            }
            st['phase'] = 'DOWNLOADING'
            save_packs_state(st, layout)
            for fspec in spec['files']:
                try:
                    _install_one_file(fspec, root, on_progress)
                except Exception as exc:  # noqa: BLE001
                    # LTX optional failure should not kill Z-Image success path
                    if spec['id'] in ('ltx2', 'wan') and any(
                        s['id'] == 'zimage' for s in specs
                    ):
                        on_progress(f"{spec['label']} deferred: {exc}")
                        break
                    raise
                done += 1
                on_progress(f"{spec['label']}: {done}/{total_files} files")

        sync = _sync_into_comfy_container(root)
        status = packs_status(layout=layout, hw=hw)
        st = load_packs_state(layout)
        st.update({
            'running': False,
            'ok': bool(status.get('image_ready')),
            'phase': 'READY' if status.get('ok') else ('PARTIAL' if status.get('image_ready') else 'FAILED'),
            'packs': status.get('packs') or {},
            'sync': sync,
            'aria': status.get('aria') or '',
            'message': (
                'Creative packs ready.'
                if status.get('image_ready')
                else 'Pack install finished with missing files — open Diagnostics.'
            ),
            'error': '' if status.get('image_ready') else 'packs incomplete',
        })
        save_packs_state(st, layout)
    except Exception as exc:  # noqa: BLE001
        st = load_packs_state(layout)
        st.update({
            'running': False,
            'ok': False,
            'phase': 'FAILED',
            'error': str(exc)[:500],
            'aria': (
                "I couldn't finish downloading creative packs. "
                'Check network / disk, then tap Install packs again.'
            ),
            'message': f'Pack install failed: {exc}',
        })
        save_packs_state(st, layout)


def start_pack_install(
    *,
    force: bool = False,
    which: Optional[list[str]] = None,
    layout: Optional[StateLayout] = None,
    hw: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Kick background pack download. Idempotent while already running."""
    layout = layout or resolve_layout()
    seed_workflow_assets()
    status = packs_status(layout=layout, hw=hw)
    if status.get('ok') and not force and not which:
        return {
            **status,
            'started': False,
            'detail': 'packs already installed',
        }
    if status.get('image_ready') and which == ['zimage'] and not force:
        return {**status, 'started': False, 'detail': 'zimage already ready'}

    global _INSTALL_THREAD
    with _INSTALL_LOCK:
        if _INSTALL_THREAD and _INSTALL_THREAD.is_alive():
            st = load_packs_state(layout)
            return {
                **packs_status(layout=layout, hw=hw),
                'started': False,
                'detail': 'install already running',
                'running': True,
                'phase': st.get('phase') or 'DOWNLOADING',
            }

        def _target() -> None:
            _run_install(layout=layout, which=which, hw=hw)

        _INSTALL_THREAD = threading.Thread(target=_target, name='studio-packs', daemon=True)
        _INSTALL_THREAD.start()

    return {
        **packs_status(layout=layout, hw=hw),
        'started': True,
        'running': True,
        'phase': 'DOWNLOADING',
        'aria': (
            'Downloading creative packs — Z-Image first so Generate can unlock, '
            'then video and music.'
        ),
        'action': 'install_packs',
        'soft_block': True,
    }


def soft_block_payload(status: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """API-shaped soft block when Generate is refused for missing packs."""
    st = status or packs_status()
    return {
        'ok': False,
        'queued': False,
        'soft_block': True,
        'action': 'install_packs',
        'error': 'creative_packs_needed',
        'detail': st.get('aria') or (
            'Creative packs are not installed yet. Tap Install packs — '
            'Generate stays quiet until packs are ready.'
        ),
        'packs': st.get('packs') or {},
        'needed': st.get('needed') or [],
        'http_status': 409,
    }
