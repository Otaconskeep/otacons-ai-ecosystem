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

# ---------------------------------------------------------------------------
# Official ComfyUI docs → Comfy-Org Hugging Face download catalog.
# Docs:
#   Z-Image: https://docs.comfy.org/tutorials/image/z-image/z-image-turbo
#   Wan 2.2: https://docs.comfy.org/tutorials/video/wan/wan2_2
#   LTX-2:   https://docs.comfy.org/tutorials/video/ltx/ltx-2
#   ACE:     https://docs.comfy.org/tutorials/audio/ace-step/ace-step-v1-5
# ---------------------------------------------------------------------------

def _f(repo: str, remote: str, subdir: str, name: str, min_bytes: int = 1_000_000) -> dict:
    return {
        'repo': repo,
        'remote': remote,
        'subdir': subdir,
        'name': name,
        'min_bytes': min_bytes,
        'url': f'https://huggingface.co/{repo}/resolve/main/{remote}',
    }


# Z-Image Turbo — Comfy-Org/z_image_turbo (official template files).
ZIMAGE_BF16 = [
    _f('Comfy-Org/z_image_turbo', 'split_files/diffusion_models/z_image_turbo_bf16.safetensors',
       'diffusion_models', 'z_image_turbo_bf16.safetensors', 1_000_000_000),
    _f('Comfy-Org/z_image_turbo', 'split_files/text_encoders/qwen_3_4b.safetensors',
       'text_encoders', 'qwen_3_4b.safetensors', 100_000_000),
    _f('Comfy-Org/z_image_turbo', 'split_files/vae/ae.safetensors',
       'vae', 'ae.safetensors', 100_000),
]
ZIMAGE_FP8 = [
    _f('Comfy-Org/z_image_turbo', 'split_files/diffusion_models/z_image_turbo_bf16.safetensors',
       'diffusion_models', 'z_image_turbo_bf16.safetensors', 1_000_000_000),
    _f('Comfy-Org/z_image_turbo', 'split_files/text_encoders/qwen_3_4b_fp8_mixed.safetensors',
       'text_encoders', 'qwen_3_4b_fp8_mixed.safetensors', 100_000_000),
    _f('Comfy-Org/z_image_turbo', 'split_files/vae/ae.safetensors',
       'vae', 'ae.safetensors', 100_000),
]
# 8 GB / 8GB_FAST — Crist-validated laptop path (RTX 3070 Laptop).
ZIMAGE_NVFP4 = [
    _f('Comfy-Org/z_image_turbo', 'split_files/diffusion_models/z_image_turbo_nvfp4.safetensors',
       'diffusion_models', 'z_image_turbo_nvfp4.safetensors', 500_000_000),
    _f('Comfy-Org/z_image_turbo', 'split_files/text_encoders/qwen_3_4b_fp4_mixed.safetensors',
       'text_encoders', 'qwen_3_4b_fp4_mixed.safetensors', 100_000_000),
    _f('Comfy-Org/z_image_turbo', 'split_files/vae/ae.safetensors',
       'vae', 'ae.safetensors', 100_000),
]
ZIMAGE_INT8 = [
    _f('Comfy-Org/z_image_turbo', 'split_files/diffusion_models/z_image_turbo_int8_convrot.safetensors',
       'diffusion_models', 'z_image_turbo_int8_convrot.safetensors', 500_000_000),
    _f('Comfy-Org/z_image_turbo', 'split_files/text_encoders/qwen_3_4b_fp8_mixed.safetensors',
       'text_encoders', 'qwen_3_4b_fp8_mixed.safetensors', 100_000_000),
    _f('Comfy-Org/z_image_turbo', 'split_files/vae/ae.safetensors',
       'vae', 'ae.safetensors', 100_000),
]
# Back-compat alias used by unit tests / callers expecting ZIMAGE_FILES.
ZIMAGE_FILES = ZIMAGE_BF16

# Wan 2.2 TI2V 5B — official Comfy docs (fits ~8 GB with offload). Never LTX on these hosts.
WAN_FILES = [
    _f('Comfy-Org/Wan_2.2_ComfyUI_Repackaged',
       'split_files/diffusion_models/wan2.2_ti2v_5B_fp16.safetensors',
       'diffusion_models', 'wan2.2_ti2v_5B_fp16.safetensors', 1_000_000_000),
    _f('Comfy-Org/Wan_2.2_ComfyUI_Repackaged',
       'split_files/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors',
       'text_encoders', 'umt5_xxl_fp8_e4m3fn_scaled.safetensors', 100_000_000),
    _f('Comfy-Org/Wan_2.2_ComfyUI_Repackaged',
       'split_files/vae/wan2.2_vae.safetensors',
       'vae', 'wan2.2_vae.safetensors', 100_000),
]

# LTX-2 distilled consumer path (24 GB+ / 3090 class). Official Comfy LTX-2 docs +
# Keep's Ampere-safe mxfp8 transformer (Kijai) + Comfy-Org Gemma text encoder.
LTX2_FILES = [
    _f('Kijai/LTX2.3_comfy',
       'diffusion_models/ltx-2.3-22b-distilled-1.1_transformer_only_mxfp8_block32.safetensors',
       'diffusion_models',
       'ltx-2.3-22b-distilled-1.1_transformer_only_mxfp8_block32.safetensors',
       1_000_000_000),
    _f('Kijai/LTX2.3_comfy', 'vae/taeltx2_3.safetensors',
       'vae', 'taeltx2_3.safetensors', 100_000),
    _f('Kijai/LTX2.3_comfy', 'text_encoders/ltx-2.3_text_projection_bf16.safetensors',
       'checkpoints', 'ltx-2.3_text_projection_bf16.safetensors', 1_000_000),
    _f('Comfy-Org/ltx-2', 'split_files/text_encoders/gemma_3_12B_it_fp4_mixed.safetensors',
       'text_encoders', 'gemma_3_12B_it_fp4_mixed.safetensors', 100_000_000),
]

# ACE-Step 1.5 AIO — official Comfy recommended checkpoint.
ACE_FILES = [
    _f('Comfy-Org/ace_step_1.5_ComfyUI_files',
       'checkpoints/ace_step_1.5_turbo_aio.safetensors',
       'checkpoints', 'ace_step_1.5_turbo_aio.safetensors', 100_000_000),
]

COMFY_DOCS = {
    'zimage': 'https://docs.comfy.org/tutorials/image/z-image/z-image-turbo',
    'wan': 'https://docs.comfy.org/tutorials/video/wan/wan2_2',
    'ltx2': 'https://docs.comfy.org/tutorials/video/ltx/ltx-2',
    'ace_step': 'https://docs.comfy.org/tutorials/audio/ace-step/ace-step-v1-5',
}

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


def _path_writable(path: Path) -> bool:
    """True when this process can create files under path (rootless-safe)."""
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / '.otacon_write_probe'
        probe.write_text('ok', encoding='utf-8')
        probe.unlink(missing_ok=True)
        return True
    except OSError:
        return False


def _compose_volume_candidates() -> list[str]:
    """Docker Compose prefixes volumes with the project name (dir name by default)."""
    project = (
        (os.environ.get('COMPOSE_PROJECT_NAME') or '').strip()
        or 'comfyui'
    )
    base = ('otacon-comfy-models', 'otacon-comfy-data')
    names: list[str] = []
    for b in base:
        names.append(b)
        names.append(f'{project}_{b}')
        # Common accidental prefixes from other compose dirs.
        for alt in ('deploy', 'otacon', 'otacons'):
            names.append(f'{alt}_{b}')
    # Dedupe preserve order
    seen: set[str] = set()
    out: list[str] = []
    for n in names:
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out


def discover_comfy_container_models_dir() -> dict[str, Any]:
    """Authoritative models path inside otacon-comfyui (docker exec / inspect)."""
    docker = _docker_bin()
    if not docker:
        return {'ok': False, 'action': 'no_docker'}
    candidates = [
        '/root/ComfyUI/models',
        '/ComfyUI/models',
        '/root/models',
    ]
    # Prefer Mounts from inspect when they point at a models tree.
    try:
        raw = subprocess.check_output(
            [docker, 'inspect', '-f', '{{json .Mounts}}', 'otacon-comfyui'],
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=8,
        ).strip()
        mounts = json.loads(raw) if raw else []
        for m in mounts if isinstance(mounts, list) else []:
            dest = str(m.get('Destination') or '')
            if dest.rstrip('/').endswith('/models') or dest.rstrip('/').endswith('ComfyUI/models'):
                candidates.insert(0, dest)
    except (subprocess.SubprocessError, OSError, json.JSONDecodeError):
        pass
    for cand in candidates:
        try:
            code = subprocess.call(
                [docker, 'exec', 'otacon-comfyui', 'test', '-d', cand],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=8,
            )
            if code == 0:
                return {'ok': True, 'container_path': cand, 'container': 'otacon-comfyui'}
        except (subprocess.SubprocessError, OSError):
            continue
    return {'ok': False, 'action': 'models_dir_missing', 'tried': candidates}


def host_models_staging_root() -> Path:
    """Writable host staging dir — downloads land here, then docker cp into Comfy."""
    env = (os.environ.get('OTACON_COMFY_MODELS') or '').strip()
    if env:
        p = Path(env).expanduser()
        p.mkdir(parents=True, exist_ok=True)
        return p
    fallback = Path.home() / '.local' / 'share' / 'otacon' / 'comfy' / 'models'
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


def resolve_models_root() -> Path:
    """Host staging path for pack downloads (always writable by the installer user).

    Never return a root-owned Docker volume mountpoint (0700 under
    /var/lib/docker/volumes/...) — Compose prefixes make those names easy to
    miss, and even the correct name is unusable rootless. Downloads go to the
    host cache; `_sync_into_comfy_container` is the path into ComfyUI.
    """
    staging = host_models_staging_root()
    # Optional: if a *writable* bind/volume models tree exists, prefer it so
    # packs land where a bind-mounted Comfy already reads — still never use
    # an unreadable volume silently.
    for vol in _compose_volume_candidates():
        mp = _docker_volume_mountpoint(vol)
        if not mp or not _path_writable(mp):
            continue
        if vol.endswith('models') or vol.endswith('_models'):
            return mp
        for cand in (
            mp / 'ComfyUI' / 'models',
            mp / 'comfyui' / 'models',
            mp / 'models',
        ):
            if _path_writable(cand.parent) or _path_writable(cand):
                cand.mkdir(parents=True, exist_ok=True)
                return cand
    return staging


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


def _zimage_files_for_tier(tier: str) -> list[dict[str, Any]]:
    t = (tier or '').lower()
    if t in ('low_vram_quant', 'int8', 'int8_quant'):
        return ZIMAGE_INT8
    if t in ('nvfp4', 'fp8_quant', '8gb_fast'):
        return ZIMAGE_NVFP4
    if t in ('fp8', 'recommended'):
        return ZIMAGE_FP8
    return ZIMAGE_BF16


def _profile_pack_specs(hw: Optional[dict[str, Any]] = None) -> list[dict[str, Any]]:
    """Pick packs from live hardware_profile — user never chooses models."""
    if hw is None:
        try:
            from expansion.capabilities.studio_setup import studio_hardware_snapshot
            hw = studio_hardware_snapshot()
        except Exception:
            hw = {}
    img = hw.get('image') if isinstance(hw.get('image'), dict) else {}
    vid = hw.get('video') if isinstance(hw.get('video'), dict) else {}
    mus = hw.get('music') if isinstance(hw.get('music'), dict) else {}
    img_settings = img.get('settings') if isinstance(img.get('settings'), dict) else {}
    vram = float(hw.get('marketed_vram_gb') or hw.get('vram_gb') or 0)
    ltx2 = bool(hw.get('ltx2_eligible'))
    # Hard safety: never pull LTX under 24 GB even if a stale profile claims eligible.
    if vram and vram < 24:
        ltx2 = False

    specs: list[dict[str, Any]] = []
    if img.get('enabled', True):
        tier = str(img.get('tier') or img_settings.get('precision') or 'full')
        files = _zimage_files_for_tier(tier)
        # Prefer explicit filenames from hardware_profile settings when present.
        unet = str(img_settings.get('unet') or '')
        clip = str(img_settings.get('clip') or '')
        vae = str(img_settings.get('vae') or '')
        if unet and clip and vae:
            files = [
                _f('Comfy-Org/z_image_turbo', f'split_files/diffusion_models/{unet}',
                   'diffusion_models', unet, 500_000_000),
                _f('Comfy-Org/z_image_turbo', f'split_files/text_encoders/{clip}',
                   'text_encoders', clip, 100_000_000),
                _f('Comfy-Org/z_image_turbo', f'split_files/vae/{vae}',
                   'vae', vae, 100_000),
            ]
        specs.append({
            'id': 'zimage',
            'kind': 'image',
            'label': f"Z-Image Turbo ({tier})",
            'engine': img.get('engine') or 'z-image-turbo',
            'tier': tier,
            'files': files,
            'disk_gb': 25,
            'priority': 1,
            'comfy_docs': COMFY_DOCS['zimage'],
            'hf_repo': 'Comfy-Org/z_image_turbo',
        })

    if vid.get('enabled', True):
        if ltx2:
            specs.append({
                'id': 'ltx2',
                'kind': 'video',
                'label': f"LTX-2 ({vid.get('tier') or 'distilled'})",
                'engine': vid.get('engine') or 'ltx-2',
                'tier': vid.get('tier') or 'distilled_24gb',
                'files': LTX2_FILES,
                'disk_gb': 100,
                'priority': 2,
                'comfy_docs': COMFY_DOCS['ltx2'],
                'note': '24 GB+ auto path (3090/4090 class). Not installed under 24 GB.',
            })
        else:
            specs.append({
                'id': 'wan',
                'kind': 'video',
                'label': f"Wan 2.2 5B ({vid.get('tier') or 'standard'})",
                'engine': vid.get('engine') or 'wan-2.2-5b',
                'tier': vid.get('tier') or 'standard',
                'files': WAN_FILES,
                'disk_gb': 45,
                'priority': 2,
                'comfy_docs': COMFY_DOCS['wan'],
                'hf_repo': 'Comfy-Org/Wan_2.2_ComfyUI_Repackaged',
                'note': 'Official Wan 2.2 5B — LTX-2 skipped on this VRAM.',
            })

    music_ok = bool(mus.get('enabled')) and mus.get('tier') != 'deferred'
    if music_ok or not mus:
        specs.append({
            'id': 'ace_step',
            'kind': 'music',
            'label': 'ACE-Step 1.5 AIO',
            'engine': mus.get('engine') or 'ace-step-1.5',
            'tier': mus.get('tier') or 'aio',
            'files': ACE_FILES,
            'disk_gb': 12,
            'priority': 3,
            'comfy_docs': COMFY_DOCS['ace_step'],
            'hf_repo': 'Comfy-Org/ace_step_1.5_ComfyUI_files',
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


def _live_comfy_filenames(endpoint: str, kind: str) -> list[str]:
    try:
        from expansion.capabilities.comfy_submit import list_models
        return list_models(endpoint, kind) or []
    except Exception:
        return []


def _name_in_listing(name: str, listing: list[str]) -> bool:
    n = (name or '').strip()
    if not n:
        return False
    for item in listing:
        s = str(item)
        if s == n or s.endswith('/' + n) or s.endswith('\\' + n):
            return True
    return False


def _live_pack_status(spec: dict[str, Any], endpoint: Optional[str]) -> Optional[dict[str, Any]]:
    """Verify pack against what ComfyUI can load (authoritative when endpoint is up)."""
    if not endpoint:
        return None
    sid = spec.get('id')
    try:
        if sid == 'zimage':
            from expansion.capabilities.comfy_submit import image_workflow_status
            live = image_workflow_status(endpoint)
            if live.get('ok'):
                return {
                    'ok': True,
                    'missing': [],
                    'present': [live.get('unet'), live.get('clip'), live.get('vae')],
                    'live_comfy': True,
                    'detail': live.get('detail'),
                }
            return {
                'ok': False,
                'missing': live.get('missing') or [],
                'present': [],
                'live_comfy': True,
                'detail': live.get('detail'),
            }
        # Map pack files → Comfy /models/<kind> listings.
        kind_map = {
            'diffusion_models': 'diffusion_models',
            'text_encoders': 'text_encoders',
            'vae': 'vae',
            'checkpoints': 'checkpoints',
            'loras': 'loras',
            'audio_encoders': 'audio_encoders',
        }
        listings: dict[str, list[str]] = {}
        missing: list[str] = []
        present: list[str] = []
        for f in spec.get('files') or []:
            sub = str(f.get('subdir') or '')
            name = str(f.get('name') or '')
            kind = kind_map.get(sub) or sub
            if kind not in listings:
                listings[kind] = _live_comfy_filenames(endpoint, kind)
                # Fallbacks some Comfy builds use
                if not listings[kind] and kind == 'diffusion_models':
                    listings[kind] = _live_comfy_filenames(endpoint, 'unet')
                if not listings[kind] and kind == 'text_encoders':
                    listings[kind] = _live_comfy_filenames(endpoint, 'clip')
            if _name_in_listing(name, listings[kind]):
                present.append(name)
            else:
                missing.append(f'{sub}/{name}')
        return {
            'ok': not missing,
            'missing': missing,
            'present': present,
            'live_comfy': True,
            'detail': 'indexed by ComfyUI' if not missing else 'missing from Comfy model index',
        }
    except Exception as exc:  # noqa: BLE001
        return {
            'ok': False,
            'missing': [f'live_probe:{exc}'],
            'present': [],
            'live_comfy': False,
        }


def packs_status(
    *,
    layout: Optional[StateLayout] = None,
    endpoint: Optional[str] = None,
    hw: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Live status of creative packs — prefer Comfy index over host disk.

    Host staging under ~/.local/share/otacon/comfy/models is often empty even
    when weights already live inside the container volume. Disk checks are the
    offline fallback only.
    """
    seed_workflow_assets()
    root = resolve_models_root()
    root_writable = _path_writable(root)
    specs = _profile_pack_specs(hw)
    state = load_packs_state(layout)
    if not endpoint:
        try:
            from expansion.capabilities.comfy_submit import _studio_endpoint
            endpoint = _studio_endpoint()
        except Exception:
            endpoint = None
    packs: dict[str, Any] = {}
    all_ok = True
    needed: list[str] = []
    for spec in specs:
        disk = _pack_files_status(spec['files'], root)
        live = _live_pack_status(spec, endpoint)
        if live is not None and live.get('live_comfy'):
            # Authoritative when Comfy answered — do not require host staging files.
            merged = {
                **disk,
                'ok': bool(live.get('ok')),
                'missing': live.get('missing') if not live.get('ok') else [],
                'present': live.get('present') or disk.get('present') or [],
                'live_comfy': True,
                'detail': live.get('detail'),
                'files_ready': len(live.get('present') or []) if live.get('ok') else disk.get('files_ready', 0),
            }
            # If live says missing but disk has files, still report missing in Comfy
            # (install sync may be needed) — keep disk present for diagnostics.
            if not live.get('ok') and disk.get('ok'):
                merged['detail'] = (
                    'Files are on the host staging dir but not indexed by ComfyUI yet — '
                    'sync into the container (docker cp) and refresh object_info.'
                )
                merged['host_staging_ok'] = True
            disk = merged
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
            'detail': disk.get('detail') or '',
        }
    image_ok = bool((packs.get('zimage') or {}).get('ok'))
    music_ok = bool((packs.get('ace_step') or {}).get('ok'))
    running = bool(state.get('running'))
    phase = state.get('phase') or ('READY' if all_ok else 'MISSING')
    if running:
        phase = state.get('phase') or 'DOWNLOADING'
    if image_ok and not all_ok:
        aria = (
            'Z-Image is ready for this GPU. Optional video/music packs are still '
            'installing or pending — Generate is unlocked.'
        )
    elif image_ok and all_ok:
        aria = 'Creative packs for this PC are installed. Generate is ready when Studio is LIVE.'
    elif running:
        aria = state.get('aria') or (
            'Downloading the ComfyUI models matched to this GPU — Z-Image first, '
            'then the right video pack (Wan on mid-VRAM, LTX-2 only on 24 GB+).'
        )
    else:
        aria = (
            'Creative models are not on this PC yet. Otacon will download the official '
            'ComfyUI weights for this VRAM profile automatically — a 2060 gets Wan + '
            'Z-Image INT8; a 3090 gets LTX-2 distilled. Generate stays quiet until ready.'
        )
    container = discover_comfy_container_models_dir()
    return {
        'ok': all_ok,
        'image_ready': image_ok,
        'music_ready': music_ok,
        'generate_ready': image_ok,
        'needed': needed,
        'packs': packs,
        'models_root': str(root),
        'models_root_writable': root_writable,
        'models_root_role': 'host_staging_then_docker_cp',
        'container_models': container,
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
    """Copy host staging models into running otacon-comfyui (primary install path)."""
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
    found = discover_comfy_container_models_dir()
    target = str(found.get('container_path') or '')
    if not target:
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
    errors: list[str] = []
    for sub in ('diffusion_models', 'text_encoders', 'vae', 'checkpoints', 'loras', 'audio_encoders'):
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
                try:
                    subprocess.check_call(
                        [docker, 'cp', str(f), f'otacon-comfyui:{target}/{sub}/{f.name}'],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        timeout=600,
                    )
                    copied += 1
                except (subprocess.SubprocessError, OSError) as exc:
                    errors.append(f'{sub}/{f.name}: {exc}')
        except (subprocess.SubprocessError, OSError) as exc:
            errors.append(f'{sub}: {exc}')
            continue
    return {
        'ok': copied > 0 or not errors,
        'action': 'docker_cp',
        'copied': copied,
        'target': target,
        'errors': errors[:8],
    }


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


def ensure_auto_install(
    *,
    layout: Optional[StateLayout] = None,
    hw: Optional[dict[str, Any]] = None,
    studio_ready: bool = False,
) -> dict[str, Any]:
    """If Studio is READY and packs missing, kick hardware-matched downloads (no UI pick).

    Pulls the full profile set (Z-Image + video + music) when VRAM ≥ 6 GB.
    Below 6 GB: image-only. Does **not** stop after Z-Image if video/music remain needed.
    """
    layout = layout or resolve_layout()
    if hw is None:
        try:
            from expansion.capabilities.studio_setup import studio_hardware_snapshot
            hw = studio_hardware_snapshot()
        except Exception:
            hw = {}
    status = packs_status(layout=layout, hw=hw)
    needed = list(status.get('needed') or [])
    if status.get('ok') or not needed:
        return {**status, 'auto_started': False, 'detail': 'packs already ready'}
    if status.get('running'):
        return {**status, 'auto_started': False, 'detail': 'already downloading'}
    if not studio_ready:
        return {**status, 'auto_started': False, 'detail': 'studio not READY'}
    vram = float((hw or {}).get('marketed_vram_gb') or (hw or {}).get('vram_gb') or 0)
    # <6 GB: image unblock only. 6 GB+ profiles include Wan 5B / ACE — pull them.
    if vram and vram < 6:
        which = ['zimage']
    elif status.get('image_ready') and needed:
        which = [p for p in needed if p != 'zimage'] or needed
    else:
        which = None  # full profile order (Z-Image first)
    out = start_pack_install(layout=layout, hw=hw, which=which)
    st = load_packs_state(layout)
    st['auto_kicked'] = True
    save_packs_state(st, layout)
    return {**out, 'auto_started': bool(out.get('started') or out.get('running'))}


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
            'Creative packs are not installed yet — matching this PC\'s VRAM profile '
            'and downloading from official ComfyUI sources. Generate stays quiet until ready.'
        ),
        'packs': st.get('packs') or {},
        'needed': st.get('needed') or [],
        'http_status': 409,
    }
