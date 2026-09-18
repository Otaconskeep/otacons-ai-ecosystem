"""Muse-owned Video Studio capability — Expansion premium feature.

Requires a reachable ComfyUI (or compatible) endpoint. Importing core.video
contracts alone is NOT enough for LIMITED/READY — that was a false green.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

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


def comfy_endpoint_healthy(endpoint: str, timeout: float = 3.0) -> tuple[bool, str]:
    """Return (ok, detail) for a public ComfyUI-style HTTP endpoint."""
    url = (endpoint or '').strip().rstrip('/')
    if not url:
        return False, 'no endpoint'
    try:
        parsed = urlparse(url if '://' in url else f'http://{url}')
        if parsed.scheme not in ('http', 'https'):
            return False, f'unsupported scheme {parsed.scheme!r}'
        if not parsed.hostname:
            return False, 'missing host'
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)
    last = 'unreachable'
    for path in ('/system_stats', '/object_info', '/'):
        try:
            req = urllib.request.Request(
                url + path,
                headers={'Accept': 'application/json, text/plain, */*'},
                method='GET',
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                code = getattr(resp, 'status', None) or resp.getcode()
                if 200 <= int(code) < 500:
                    return True, f'{path} → {code}'
                last = f'{path} → {code}'
        except urllib.error.HTTPError as exc:
            # Comfy often 404s /; treat 2xx–4xx (except 5xx) on known paths as alive.
            if exc.code < 500 and path in ('/system_stats', '/object_info'):
                return True, f'{path} → HTTP {exc.code}'
            last = f'{path} → HTTP {exc.code}'
        except Exception as exc:  # noqa: BLE001
            last = str(exc)
    return False, last


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

    endpoint = disc.get('endpoint') or ''
    if not endpoint:
        return CapabilityReport(
            CAPABILITY_ID, OWNER_AGENT, CapabilityState.NOT_CONFIGURED.value,
            detail='Video Studio is not connected yet. Use Set Up Video Studio to finish.',
            config_keys_present=keys, discovery=disc,
        )

    ok, health_detail = comfy_endpoint_healthy(endpoint)
    disc = dict(disc)
    disc['health'] = health_detail
    disc['healthy'] = ok
    if ok:
        return CapabilityReport(
            CAPABILITY_ID, OWNER_AGENT, CapabilityState.READY.value,
            detail=f'ComfyUI endpoint healthy ({health_detail}).',
            config_keys_present=keys, discovery=disc,
        )
    return CapabilityReport(
        CAPABILITY_ID, OWNER_AGENT, CapabilityState.LIMITED.value,
        detail=f'Endpoint configured but not healthy: {health_detail}',
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
