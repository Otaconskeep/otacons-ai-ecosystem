"""Optional Home Assistant capability — Sentry-owned.

Config is URL + token only (user-owned). Missing HA must not degrade base Expansion.
No private household automations or data ship in product.
"""
from __future__ import annotations

import json
import os
from typing import Optional

from expansion.capabilities import CapabilityReport, CapabilityState, _forbidden_private_paths
from expansion.persist import atomic_write_json, read_json
from expansion.state_layout import StateLayout, resolve_layout
from expansion.topology import load_topology

CAPABILITY_ID = 'home_assistant'
OWNER_AGENT = 'sentry'


def _config_path(layout: Optional[StateLayout] = None):
    layout = layout or resolve_layout()
    return layout.user_preferences / 'home_assistant.json'


def load_ha_config(layout: Optional[StateLayout] = None) -> dict:
    """Return non-secret view + whether token is present (never return token)."""
    layout = layout or resolve_layout()
    topo = load_topology()
    raw = read_json(_config_path(layout), default={}) or {}
    url = (
        str(raw.get('url') or '').strip()
        or (topo.home_assistant_url or '').strip()
        or (os.environ.get('OTACON_HA_URL') or '').strip()
    )
    token_set = bool(raw.get('token') or os.environ.get('OTACON_HA_TOKEN'))
    return {
        'url': url,
        'token_configured': token_set,
        # never expose token
    }


def save_ha_config(url: str, token: str = '', layout: Optional[StateLayout] = None) -> dict:
    """Persist URL; token stored only under user preferences (not product)."""
    layout = layout or resolve_layout()
    path = _config_path(layout)
    existing = read_json(path, default={}) or {}
    data = {
        'url': (url or '').strip(),
        'token': token if token else existing.get('token', ''),
    }
    forbidden = _forbidden_private_paths(json.dumps(data))
    if forbidden:
        raise ValueError(f'forbidden private topology: {forbidden[0]}')
    atomic_write_json(path, data)
    return load_ha_config(layout)


def probe_home_assistant(layout: Optional[StateLayout] = None) -> CapabilityReport:
    layout = layout or resolve_layout()
    cfg = load_ha_config(layout)
    forbidden = _forbidden_private_paths(cfg.get('url') or '')
    if forbidden:
        return CapabilityReport(
            CAPABILITY_ID, OWNER_AGENT, CapabilityState.FAILED.value,
            detail=f'forbidden private topology: {forbidden[0]}',
            discovery=cfg,
        )
    keys = []
    if cfg.get('url'):
        keys.append('url')
    if cfg.get('token_configured'):
        keys.append('token')
    if not cfg.get('url'):
        return CapabilityReport(
            CAPABILITY_ID, OWNER_AGENT, CapabilityState.NEEDS_CREDENTIAL.value,
            detail=(
                'Home Assistant is supported. Otacon needs your HA URL and a '
                'long-lived access token once — then it can verify and wire entities.'
            ),
            config_keys_present=keys, discovery={**cfg, 'auto_install': True, 'user_action': 'credential'},
        )
    if cfg.get('url') and not cfg.get('token_configured'):
        return CapabilityReport(
            CAPABILITY_ID, OWNER_AGENT, CapabilityState.NEEDS_CREDENTIAL.value,
            detail='HA URL set but long-lived access token missing.',
            config_keys_present=keys,
            discovery={**cfg, 'auto_install': True, 'user_action': 'credential'},
        )
    return CapabilityReport(
        CAPABILITY_ID, OWNER_AGENT, CapabilityState.READY.value,
        detail='HA URL and token configured (connectivity not probed by Expansion core).',
        config_keys_present=keys,
        discovery={**cfg, 'auto_install': True, 'user_action': 'none'},
    )
