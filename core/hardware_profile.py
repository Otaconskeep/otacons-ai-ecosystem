"""VRAM-first Studio / creative hardware profiling.

Priority: VRAM → system RAM → GPU generation → free disk → CUDA.

Drives auto-selection for:
  - Z-Image (image)
  - Wan 2.2 5B / LTX-2 (video)
  - ACE-Step 1.5 (music)
  - ComfyUI sidecar image (CPU vs GPU)
  - Installer Studio profile id

No hardcoded usernames or fake GPU/VRAM values.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional


# Disk budgets (GB) — safe allocations the installer checks before auto-pull.
DISK_ZIMAGE_GB = 25
DISK_WAN_GB = 45
DISK_LTX2_GB = 100
DISK_ACESTEP_GB = 12


@dataclass
class CreativePath:
    """One creative modality recommendation."""
    enabled: bool
    engine: str
    tier: str
    detail: str
    settings: dict[str, Any] = field(default_factory=dict)
    prompts: dict[str, str] = field(default_factory=dict)


@dataclass
class StudioHardwareProfile:
    profile_id: str
    gpu_model: str
    vram_gb: float
    ram_gb: float
    free_disk_gb: float
    cuda_available: bool
    gpu_generation: str  # e.g. Ampere, Ada, Blackwell, Turing, unknown
    ram_tier: str  # unsupported | minimum | recommended | excellent
    auto_install_studio: bool
    comfy_runtime: str  # cpu | gpu
    image: CreativePath
    video: CreativePath
    music: CreativePath
    ltx2_eligible: bool
    warnings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d


# Keep-parity default prompts / settings (Expansion-owned; mirrors Keep intent).
_ZIMAGE_PROMPT = (
    "identity-preserving portrait, natural lighting, sharp eyes, "
    "consistent face, clean background, high detail"
)
_ZIMAGE_NEG = (
    "blurry, deformed face, extra limbs, watermark, text, low quality, oversaturated"
)
_WAN_PROMPT = (
    "cinematic motion, smooth camera, natural physics, coherent subject, "
    "stable identity across frames"
)
_WAN_NEG = "jitter, morphing face, flicker, text overlay, watermark, low fps look"
_LTX_PROMPT = (
    "high-fidelity cinematic shot, coherent motion, detailed lighting, "
    "stable subject, filmic color"
)
_MUSIC_PROMPT = (
    "instrumental bed, clean mix, no vocals unless requested, "
    "loop-friendly structure, emotional but controlled"
)


def _gpu_generation(model: str) -> str:
    m = (model or '').lower()
    if re.search(r'rtx\s*50\d{2}|blackwell', m):
        return 'Blackwell'
    if re.search(r'rtx\s*40\d{2}|ada', m):
        return 'Ada'
    if re.search(r'rtx\s*30\d{2}|a\d{4}|ampere', m):
        return 'Ampere'
    if re.search(r'rtx\s*20\d{2}|turing|gtx\s*16', m):
        return 'Turing'
    if 'nvidia' in m or 'rtx' in m or 'gtx' in m:
        return 'NVIDIA'
    return 'unknown'


def _is_fast_sku(model: str) -> bool:
    """Ti / Super / higher clocks within a VRAM class → *_FAST / *_ULTRA."""
    m = (model or '').lower()
    # Explicit matrix SKUs (user VRAM-first GPU table).
    if re.search(
        r'rtx\s*30\s*60\s*ti|rtx\s*3070|rtx\s*3070\s*ti|'
        r'rtx\s*4070\s*ti|rtx\s*4080|rtx\s*4090|'
        r'rtx\s*5060(?!\s*ti)|rtx\s*5070|rtx\s*5080|rtx\s*5090|'
        r'rtx\s*50\d{2}',
        m,
    ):
        return True
    return bool(re.search(r'\b(ti|super)\b', m))


def _ram_tier(ram_gb: float) -> tuple[str, bool, list[str]]:
    warnings: list[str] = []
    if ram_gb < 16:
        warnings.append(
            f'System RAM {ram_gb:.0f} GB is below the 16 GB Studio minimum — '
            'auto-install of Video Studio is disabled.'
        )
        return 'unsupported', False, warnings
    if ram_gb < 32:
        return 'minimum', True, warnings
    if ram_gb < 64:
        return 'recommended', True, warnings
    return 'excellent', True, warnings


def _zimage_path(vram_gb: float) -> CreativePath:
    if vram_gb < 6:
        return CreativePath(
            False, 'z-image', 'disabled',
            'VRAM below 6 GB — Z-Image not installed by default.',
            {}, {},
        )
    if vram_gb < 8:
        return CreativePath(
            True, 'z-image-turbo', 'low_vram_quant',
            '6–7 GB: Z-Image Turbo quantized / low-VRAM path only (slower).',
            {
                'precision': 'int8_quant',
                'low_vram': True,
                'resolution': 512,
                'steps': 4,
                'cfg': 1.0,
            },
            {'positive': _ZIMAGE_PROMPT, 'negative': _ZIMAGE_NEG},
        )
    if vram_gb < 10:
        return CreativePath(
            True, 'z-image-turbo', 'fp8_quant',
            '8 GB minimum path: Z-Image Turbo FP8 / quantized.',
            {
                'precision': 'fp8',
                'low_vram': True,
                'resolution': 768,
                'steps': 6,
                'cfg': 1.0,
            },
            {'positive': _ZIMAGE_PROMPT, 'negative': _ZIMAGE_NEG},
        )
    if vram_gb < 16:
        return CreativePath(
            True, 'z-image-turbo', 'recommended',
            '10–15 GB: recommended Z-Image Turbo quality.',
            {
                'precision': 'fp8',
                'low_vram': False,
                'resolution': 1024,
                'steps': 8,
                'cfg': 1.0,
            },
            {'positive': _ZIMAGE_PROMPT, 'negative': _ZIMAGE_NEG},
        )
    return CreativePath(
        True, 'z-image-turbo', 'full',
        '16 GB+: full-quality / high-performance Z-Image path.',
        {
            'precision': 'bf16',
            'low_vram': False,
            'resolution': 1024,
            'steps': 8,
            'cfg': 1.0,
            'batch': 2 if vram_gb >= 24 else 1,
        },
        {'positive': _ZIMAGE_PROMPT, 'negative': _ZIMAGE_NEG},
    )


def _video_path(vram_gb: float) -> tuple[CreativePath, bool, list[str]]:
    """Return (video path, ltx2_eligible, warnings)."""
    warnings: list[str] = []
    ltx2 = False
    if vram_gb < 6:
        return CreativePath(
            False, 'none', 'disabled',
            'VRAM below 6 GB — video workflows disabled by default.',
            {}, {},
        ), False, warnings
    if vram_gb < 8:
        return CreativePath(
            True, 'wan-2.2-5b-quant', 'low_vram_quant',
            '6–7 GB: very light / quantized video only.',
            {
                'workflow': 'wan_2_2_5b_low_vram',
                'width': 480, 'height': 272, 'frames': 33,
                'fps': 8, 'steps': 4, 'offload': True,
            },
            {'positive': _WAN_PROMPT, 'negative': _WAN_NEG},
        ), False, warnings
    if vram_gb < 12:
        return CreativePath(
            True, 'wan-2.2-5b', 'standard',
            '8–11 GB: Wan 2.2 5B (fits ~8 GB with native offload).',
            {
                'workflow': 'wan_2_2_5b',
                'width': 640, 'height': 352, 'frames': 49,
                'fps': 12, 'steps': 6, 'offload': True,
            },
            {'positive': _WAN_PROMPT, 'negative': _WAN_NEG},
        ), False, warnings
    if vram_gb < 16:
        return CreativePath(
            True, 'wan-2.2-5b', 'high_quality',
            '12–15 GB: Wan 2.2 5B high-quality profile.',
            {
                'workflow': 'wan_2_2_5b_hq',
                'width': 832, 'height': 480, 'frames': 65,
                'fps': 16, 'steps': 8, 'offload': False,
            },
            {'positive': _WAN_PROMPT, 'negative': _WAN_NEG},
        ), False, warnings
    if vram_gb < 24:
        return CreativePath(
            True, 'wan-2.2-5b', 'large_quant',
            '16–23 GB: larger / high-quality Wan profile.',
            {
                'workflow': 'wan_2_2_5b_large',
                'width': 960, 'height': 544, 'frames': 81,
                'fps': 16, 'steps': 10, 'offload': False,
            },
            {'positive': _WAN_PROMPT, 'negative': _WAN_NEG},
        ), False, warnings
    if vram_gb < 32:
        warnings.append(
            f'{vram_gb:.0f} GB VRAM is strong for consumer video but below '
            'official LTX-2 ComfyUI requirement (32 GB+). Using high-end Wan profile.'
        )
        return CreativePath(
            True, 'wan-2.2-5b', 'high_end_consumer',
            '24–31 GB: high-end consumer video (Wan). LTX-2 not auto-selected.',
            {
                'workflow': 'wan_2_2_5b_high_end',
                'width': 1280, 'height': 704, 'frames': 97,
                'fps': 24, 'steps': 12, 'offload': False,
            },
            {'positive': _WAN_PROMPT, 'negative': _WAN_NEG},
        ), False, warnings
    ltx2 = True
    return CreativePath(
        True, 'ltx-2', 'official',
        '32 GB+: LTX-2 eligible (official ComfyUI tier).',
        {
            'workflow': 'ltx2_official',
            'width': 1280, 'height': 704, 'frames': 121,
            'fps': 24, 'steps': 20, 'offload': False,
            'disk_gb_required': DISK_LTX2_GB,
        },
        {'positive': _LTX_PROMPT, 'negative': _WAN_NEG},
    ), True, warnings


def _music_path(vram_gb: float) -> CreativePath:
    """ACE-Step 1.5 default local music engine — VRAM-scaled."""
    if vram_gb <= 4:
        return CreativePath(
            True, 'ace-step-1.5', '2b_turbo_dit_int8',
            '≤4 GB: ACE-Step 2B Turbo, DiT-only, INT8 + heavy CPU offload.',
            {
                'model': 'ace_step_2b_turbo',
                'lm': 'none',
                'precision': 'int8',
                'offload': 'heavy_cpu',
                'max_duration_sec': 30,
                'batch': 1,
            },
            {'positive': _MUSIC_PROMPT},
        )
    if vram_gb < 6:
        return CreativePath(
            True, 'ace-step-1.5', '2b_turbo_dit_int8',
            '4–6 GB: ACE-Step 2B Turbo, DiT-only, INT8.',
            {
                'model': 'ace_step_2b_turbo',
                'lm': 'none',
                'precision': 'int8',
                'offload': 'cpu',
                'max_duration_sec': 60,
                'batch': 1,
            },
            {'positive': _MUSIC_PROMPT},
        )
    if vram_gb < 8:
        return CreativePath(
            True, 'ace-step-1.5', '2b_turbo_lm06',
            '6–8 GB: ACE-Step 2B Turbo + 0.6B LM.',
            {
                'model': 'ace_step_2b_turbo',
                'lm': '0.6b',
                'precision': 'fp16',
                'offload': 'light',
                'max_duration_sec': 90,
                'batch': 1,
            },
            {'positive': _MUSIC_PROMPT},
        )
    if vram_gb < 12:
        return CreativePath(
            True, 'ace-step-1.5', '2b_turbo_sft_lm06',
            '8–12 GB: ACE-Step 2B Turbo/SFT + 0.6B LM.',
            {
                'model': 'ace_step_2b_sft',
                'lm': '0.6b',
                'precision': 'fp16',
                'offload': False,
                'max_duration_sec': 120,
                'batch': 1,
            },
            {'positive': _MUSIC_PROMPT},
        )
    if vram_gb < 16:
        return CreativePath(
            True, 'ace-step-1.5', '2b_lm17_xl_offload',
            '12–16 GB: ACE-Step 2B + 1.7B LM; XL possible with offload.',
            {
                'model': 'ace_step_2b_sft',
                'lm': '1.7b',
                'precision': 'fp16',
                'xl_offload': True,
                'max_duration_sec': 180,
                'batch': 1,
            },
            {'positive': _MUSIC_PROMPT},
        )
    if vram_gb < 20:
        return CreativePath(
            True, 'ace-step-1.5', 'xl_offload_lm17',
            '16–20 GB: ACE-Step XL with CPU offload + 1.7B LM.',
            {
                'model': 'ace_step_xl',
                'lm': '1.7b',
                'precision': 'fp16',
                'offload': 'cpu',
                'max_duration_sec': 240,
                'batch': 1,
            },
            {'positive': _MUSIC_PROMPT},
        )
    if vram_gb < 24:
        return CreativePath(
            True, 'ace-step-1.5', 'xl_lm17',
            '20–24 GB: ACE-Step XL comfortably, 1.7B LM.',
            {
                'model': 'ace_step_xl',
                'lm': '1.7b',
                'precision': 'bf16',
                'offload': False,
                'max_duration_sec': 300,
                'batch': 1,
            },
            {'positive': _MUSIC_PROMPT},
        )
    return CreativePath(
        True, 'ace-step-1.5', 'xl_lm4b',
        '24 GB+: ACE-Step XL + 4B LM, best-quality local tier.',
        {
            'model': 'ace_step_xl',
            'lm': '4b',
            'precision': 'bf16',
            'offload': False,
            'max_duration_sec': 360,
            'batch': 2 if vram_gb >= 32 else 1,
        },
        {'positive': _MUSIC_PROMPT},
    )


def _profile_id(vram_gb: float, model: str, ltx2: bool) -> str:
    if vram_gb < 6:
        return 'DISABLED' if vram_gb < 4 else 'LOW_VRAM'
    if vram_gb < 8:
        return 'LOW_VRAM'
    fast = _is_fast_sku(model)
    gen = _gpu_generation(model)
    if vram_gb >= 32 or ltx2:
        return '32GB_LTX2'
    if vram_gb >= 24:
        return '24GB_FAST' if fast or gen in ('Ada', 'Blackwell') else '24GB'
    if vram_gb >= 16:
        if '5080' in (model or '').lower():
            return '16GB_ULTRA'
        return '16GB_FAST' if fast or gen in ('Ada', 'Blackwell') else '16GB'
    if vram_gb >= 12:
        return '12GB_FAST' if fast or gen in ('Ada', 'Blackwell') else '12GB'
    if vram_gb >= 10:
        return '10GB'
    return '8GB_FAST' if fast or gen in ('Ada', 'Blackwell') else '8GB'


def _cuda_available() -> bool:
    # nvidia-smi presence is a practical CUDA-path signal for WSL/Desktop.
    try:
        from core.platform import _resolve_nvidia_smi
        return bool(_resolve_nvidia_smi())
    except Exception:
        return False


def classify_studio_profile(
    *,
    vram_gb: float = 0.0,
    ram_gb: float = 0.0,
    free_disk_gb: float = 0.0,
    gpu_model: str = '',
    cuda_available: bool | None = None,
) -> StudioHardwareProfile:
    """Pure classifier — unit-testable without touching nvidia-smi."""
    cuda = _cuda_available() if cuda_available is None else bool(cuda_available)
    gen = _gpu_generation(gpu_model)
    ram_tier, auto_ok, warnings = _ram_tier(ram_gb)
    notes: list[str] = []

    image = _zimage_path(vram_gb)
    video, ltx2, vwarn = _video_path(vram_gb)
    warnings.extend(vwarn)
    music = _music_path(vram_gb)

    # Disk gates
    need = 0.0
    if image.enabled:
        need += DISK_ZIMAGE_GB
    if video.enabled:
        need += DISK_LTX2_GB if ltx2 else DISK_WAN_GB
    if music.enabled:
        need += DISK_ACESTEP_GB
    if free_disk_gb and need and free_disk_gb < need:
        warnings.append(
            f'Free disk {free_disk_gb:.0f} GB is below the ~{need:.0f} GB safe budget '
            f'for the selected Studio packs (Z-Image/Wan/ACE-Step'
            f'{"+LTX-2" if ltx2 else ""}).'
        )
        if ltx2 and free_disk_gb < DISK_LTX2_GB:
            warnings.append(
                f'LTX-2 needs ~{DISK_LTX2_GB} GB+ free — keeping LTX-2 eligible but '
                'do not auto-pull until disk is freed.'
            )
            notes.append('ltx2_disk_hold')

    if not cuda and vram_gb <= 0:
        warnings.append('CUDA / nvidia-smi not available — Studio stays CPU Comfy only.')
        auto_ok = False
        image = CreativePath(False, 'z-image', 'disabled', 'No CUDA — image pack off.', {}, {})
        video = CreativePath(False, 'none', 'disabled', 'No CUDA — video pack off.', {}, {})
        # Music can still suggest ACE-Step for later GPU hosts
        music = CreativePath(
            False, 'ace-step-1.5', 'deferred',
            'No CUDA now — music profile deferred until a GPU is visible.',
            {}, {},
        )

    profile_id = _profile_id(vram_gb, gpu_model, ltx2)
    if not auto_ok or profile_id in ('DISABLED',) or (vram_gb < 6 and not image.enabled and not video.enabled):
        if vram_gb < 6:
            profile_id = 'DISABLED' if vram_gb < 4 else 'LOW_VRAM'

    comfy = 'gpu' if (cuda and vram_gb >= 6 and auto_ok) else 'cpu'
    if ram_tier == 'unsupported':
        auto_ok = False
        comfy = 'cpu'

    notes.append(f'vram_first={vram_gb:.1f}G')
    notes.append(f'ram_second={ram_gb:.1f}G/{ram_tier}')
    notes.append(f'gpu_gen_third={gen}')

    return StudioHardwareProfile(
        profile_id=profile_id,
        gpu_model=gpu_model or '',
        vram_gb=float(vram_gb or 0.0),
        ram_gb=float(ram_gb or 0.0),
        free_disk_gb=float(free_disk_gb or 0.0),
        cuda_available=cuda,
        gpu_generation=gen,
        ram_tier=ram_tier,
        auto_install_studio=bool(auto_ok and (image.enabled or video.enabled or music.enabled)),
        comfy_runtime=comfy,
        image=image,
        video=video,
        music=music,
        ltx2_eligible=ltx2,
        warnings=warnings,
        notes=notes,
    )


def detect_studio_profile(hw: Any = None) -> StudioHardwareProfile:
    """Probe live hardware (or accept a core.platform.Hardware-like object)."""
    if hw is None:
        from core.platform import detect
        hw = detect()
    gpus = getattr(hw, 'gpus', None) or []
    primary = sorted(gpus, key=lambda g: getattr(g, 'vram_gb', 0.0), reverse=True)
    gpu = primary[0] if primary else None
    vram = float(getattr(gpu, 'vram_gb', 0.0) or 0.0) if gpu else 0.0
    model = str(getattr(gpu, 'model', '') or '') if gpu else ''
    ram = float(getattr(hw, 'ram_gb', 0.0) or 0.0)
    disk = float(getattr(hw, 'free_storage_gb', 0.0) or 0.0)
    det = getattr(hw, 'gpu_detection', None) or {}
    cuda = bool(gpus) and det.get('status') in ('detected', None, '')
    if det.get('status') == 'error':
        cuda = False
    elif det.get('status') == 'detected':
        cuda = True
    return classify_studio_profile(
        vram_gb=vram,
        ram_gb=ram,
        free_disk_gb=disk,
        gpu_model=model,
        cuda_available=cuda if gpus else False,
    )


def profile_asset_manifest(profile: StudioHardwareProfile) -> list[dict[str, str]]:
    """Declarative packs the installer / Studio setup should pull for this host."""
    assets: list[dict[str, str]] = []
    if profile.image.enabled:
        assets.append({
            'id': f"zimage:{profile.image.tier}",
            'kind': 'image',
            'engine': profile.image.engine,
            'tier': profile.image.tier,
            'disk_gb': str(DISK_ZIMAGE_GB),
        })
    if profile.video.enabled:
        assets.append({
            'id': f"video:{profile.video.engine}:{profile.video.tier}",
            'kind': 'video',
            'engine': profile.video.engine,
            'tier': profile.video.tier,
            'disk_gb': str(DISK_LTX2_GB if profile.ltx2_eligible else DISK_WAN_GB),
        })
    if profile.music.enabled and profile.music.tier != 'deferred':
        assets.append({
            'id': f"music:{profile.music.tier}",
            'kind': 'music',
            'engine': profile.music.engine,
            'tier': profile.music.tier,
            'disk_gb': str(DISK_ACESTEP_GB),
        })
    return assets


def persist_studio_profile(
    profile: StudioHardwareProfile,
    path: Optional[Path] = None,
) -> Path:
    """Write profile JSON under Otacon config (and optional bootstrap env snippet)."""
    if path is None:
        path = Path.home() / '.config' / 'otacon' / 'studio_hardware_profile.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(profile.to_dict(), indent=2) + '\n', encoding='utf-8')
    env_path = Path.home() / '.config' / 'otacon' / 'bootstrap-hardware.env'
    try:
        lines = []
        if env_path.is_file():
            lines = env_path.read_text(encoding='utf-8', errors='replace').splitlines()
        kv = {
            'OTACON_STUDIO_PROFILE': profile.profile_id,
            'OTACON_STUDIO_VRAM_GB': f'{profile.vram_gb:.1f}',
            'OTACON_STUDIO_RAM_GB': f'{profile.ram_gb:.1f}',
            'OTACON_STUDIO_COMFY': profile.comfy_runtime,
            'OTACON_STUDIO_IMAGE': profile.image.engine if profile.image.enabled else 'off',
            'OTACON_STUDIO_VIDEO': profile.video.engine if profile.video.enabled else 'off',
            'OTACON_STUDIO_MUSIC': profile.music.engine if profile.music.enabled else 'off',
            'OTACON_STUDIO_LTX2': '1' if profile.ltx2_eligible else '0',
            'OTACON_STUDIO_AUTO': '1' if profile.auto_install_studio else '0',
        }
        kept = [ln for ln in lines if ln.strip() and not any(ln.startswith(k + '=') for k in kv)]
        kept.extend(f'{k}={v}' for k, v in kv.items())
        env_path.write_text('\n'.join(kept) + '\n', encoding='utf-8')
    except OSError:
        pass
    return path


def load_studio_defaults() -> dict[str, Any]:
    """Optional on-disk Keep-parity defaults override."""
    here = Path(__file__).resolve().parents[1] / 'expansion' / 'product' / 'studio' / 'keep_defaults.json'
    if here.is_file():
        try:
            return json.loads(here.read_text(encoding='utf-8'))
        except (json.JSONDecodeError, OSError):
            pass
    return {}
