"""Muse-owned Video Studio capability — heavy deps optional.

Personality/emotion always come from Expansion runtime, never duplicated here.
No private Comfy/AI9/LAN defaults — discovery via topology/env only.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

from expansion.capabilities import CapabilityReport, CapabilityState, _forbidden_private_paths
from expansion.state_layout import StateLayout, resolve_layout
from expansion.topology import load_topology


CAPABILITY_ID = 'video_studio'
OWNER_AGENT = 'muse'


def _discover_endpoint(layout: Optional[StateLayout] = None) -> dict:
    layout = layout or resolve_layout()
    topo = load_topology()
    env_url = (os.environ.get('OTACON_COMFYUI_URL') or os.environ.get('COMFYUI_URL') or '').strip()
    url = (topo.comfyui_url or env_url or '').strip()
    cfg_path = layout.user_preferences / 'video_studio.json'
    cfg = {}
    if cfg_path.is_file():
        try:
            cfg = json.loads(cfg_path.read_text(encoding='utf-8'))
        except (json.JSONDecodeError, OSError):
            cfg = {}
    if not url:
        url = str(cfg.get('endpoint') or cfg.get('comfyui_url') or '').strip()
    provider = str(cfg.get('provider') or ('comfyui' if url else 'none'))
    return {
        'endpoint': url,
        'provider': provider,
        'config_path': str(cfg_path) if cfg_path.is_file() else '',
        'core_video_module': _core_video_available(),
    }


def _core_video_available() -> bool:
    try:
        from core.video import VideoProvider, TestVideoProvider  # noqa: F401
        return True
    except Exception:
        return False


def probe_video_studio(layout: Optional[StateLayout] = None) -> CapabilityReport:
    layout = layout or resolve_layout()
    disc = _discover_endpoint(layout)
    blob = json.dumps(disc)
    forbidden = _forbidden_private_paths(blob)
    if forbidden:
        return CapabilityReport(
            CAPABILITY_ID, OWNER_AGENT, CapabilityState.FAILED.value,
            detail=f'forbidden private topology fragment: {forbidden[0]}',
            discovery=disc,
        )
    keys = []
    if disc.get('endpoint'):
        keys.append('endpoint')
    if disc.get('core_video_module'):
        keys.append('core.video')

    if not disc.get('endpoint') and not disc.get('core_video_module'):
        return CapabilityReport(
            CAPABILITY_ID, OWNER_AGENT, CapabilityState.UNAVAILABLE.value,
            detail='No video endpoint configured; Core video contracts optional.',
            config_keys_present=keys, discovery=disc,
        )
    if disc.get('endpoint') and disc.get('core_video_module'):
        # Endpoint present but external health not verified in Expansion — LIMITED
        return CapabilityReport(
            CAPABILITY_ID, OWNER_AGENT, CapabilityState.LIMITED.value,
            detail='Endpoint configured; external provider health not verified by Expansion.',
            config_keys_present=keys, discovery=disc,
        )
    if disc.get('core_video_module') and not disc.get('endpoint'):
        return CapabilityReport(
            CAPABILITY_ID, OWNER_AGENT, CapabilityState.LIMITED.value,
            detail='Core video contracts available; no external Studio endpoint (test/local only).',
            config_keys_present=keys, discovery=disc,
        )
    return CapabilityReport(
        CAPABILITY_ID, OWNER_AGENT, CapabilityState.NOT_CONFIGURED.value,
        detail='Video Studio not configured.',
        config_keys_present=keys, discovery=disc,
    )


def studio_runtime_context(agent_id: str = 'muse') -> dict:
    """Bounded Studio context — pulls personality from shared runtime, not local copies."""
    from expansion.runtime import ExpansionRuntime
    rt = ExpansionRuntime()
    if not rt.expansion_enabled():
        return {'agent_id': agent_id, 'persona_source': 'none', 'note': 'Expansion not enabled'}
    try:
        ctx = rt.assemble_context(agent_id)
        return {
            'agent_id': agent_id,
            'persona_source': 'expansion.runtime',
            'archetype': ctx.archetype,
            'emotion_highlights': dict(list(ctx.emotion.get('dimensions', {}).items())[:6]),
            'note': 'Studio must not duplicate persona/dossier definitions.',
        }
    except KeyError:
        return {'agent_id': agent_id, 'persona_source': 'missing', 'note': 'agent not in roster'}
