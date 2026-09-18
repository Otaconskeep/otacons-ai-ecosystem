"""Optional Home Assistant capability — Sentry-owned.

Config is URL + long-lived token (user-owned). Token lives in
~/.config/otacon/secrets/home_assistant.env (0600), never in product JSON.
Missing HA must not degrade base Expansion.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Optional

from expansion.capabilities import CapabilityReport, CapabilityState, _forbidden_private_paths
from expansion.persist import atomic_write_json, read_json
from expansion.secrets import has_secret_key, read_env_secret, write_env_secret
from expansion.state_layout import StateLayout, resolve_layout
from expansion.topology import load_topology

CAPABILITY_ID = 'home_assistant'
OWNER_AGENT = 'sentry'
HA_SECRET = 'home_assistant'


def _config_path(layout: Optional[StateLayout] = None):
    layout = layout or resolve_layout()
    return layout.user_preferences / 'home_assistant.json'


def _token(layout: Optional[StateLayout] = None) -> str:
    secrets = read_env_secret(HA_SECRET)
    if secrets.get('HA_TOKEN'):
        return secrets['HA_TOKEN'].strip()
    env = (os.environ.get('OTACON_HA_TOKEN') or '').strip()
    if env:
        return env
    # Legacy plaintext prefs (migrate on next save)
    layout = layout or resolve_layout()
    raw = read_json(_config_path(layout), default={}) or {}
    return str(raw.get('token') or '').strip()


def load_ha_config(layout: Optional[StateLayout] = None) -> dict:
    """Return non-secret view + whether token is present (never return token)."""
    layout = layout or resolve_layout()
    topo = load_topology()
    raw = read_json(_config_path(layout), default={}) or {}
    secrets = read_env_secret(HA_SECRET)
    url = (
        str(raw.get('url') or secrets.get('HA_URL') or '').strip()
        or (topo.home_assistant_url or '').strip()
        or (os.environ.get('OTACON_HA_URL') or '').strip()
    )
    token_set = bool(
        raw.get('token')
        or secrets.get('HA_TOKEN')
        or os.environ.get('OTACON_HA_TOKEN')
        or has_secret_key(HA_SECRET, 'HA_TOKEN')
    )
    return {
        'url': url,
        'token_configured': token_set,
        'entity_count': int(raw.get('entity_count') or 0),
        'verified': bool(raw.get('verified')),
        'auto_install': True,
        'user_action': 'credential' if not (url and token_set) else 'none',
    }


def save_ha_config(url: str, token: str = '', layout: Optional[StateLayout] = None) -> dict:
    """Persist URL in prefs; token under secrets/ (0600)."""
    layout = layout or resolve_layout()
    path = _config_path(layout)
    existing = read_json(path, default={}) or {}
    url_s = (url or '').strip().rstrip('/')
    forbidden = _forbidden_private_paths(url_s)
    if forbidden:
        raise ValueError(f'forbidden private topology: {forbidden[0]}')
    tok = (token or '').strip()
    if tok:
        write_env_secret(HA_SECRET, {
            **read_env_secret(HA_SECRET),
            'HA_URL': url_s,
            'HA_TOKEN': tok,
        })
    elif url_s:
        secrets = read_env_secret(HA_SECRET)
        if secrets:
            secrets['HA_URL'] = url_s
            write_env_secret(HA_SECRET, secrets)
    data = {
        'url': url_s,
        'token_configured': bool(tok or existing.get('token') or has_secret_key(HA_SECRET, 'HA_TOKEN')),
        'entity_count': int(existing.get('entity_count') or 0),
        'verified': False,
    }
    data.pop('token', None)
    # Drop legacy plaintext token from prefs if present
    atomic_write_json(path, data)
    return load_ha_config(layout)


def verify_home_assistant(
    *,
    layout: Optional[StateLayout] = None,
    timeout: float = 8.0,
) -> dict[str, Any]:
    """Hit HA /api/ then discover entities via /api/states."""
    layout = layout or resolve_layout()
    cfg = load_ha_config(layout)
    url = (cfg.get('url') or '').strip().rstrip('/')
    tok = _token(layout)
    if not url or not tok:
        return {'ok': False, 'error': 'url and token required', 'config': cfg}
    headers = {
        'Authorization': f'Bearer {tok}',
        'Content-Type': 'application/json',
        'User-Agent': 'Otacon-Expansion/ha',
    }
    try:
        req = urllib.request.Request(url + '/api/', headers=headers, method='GET')
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode('utf-8', errors='replace')
            api_ok = 200 <= int(getattr(resp, 'status', None) or resp.getcode()) < 300
    except urllib.error.HTTPError as exc:
        return {'ok': False, 'error': f'HA API HTTP {exc.code}', 'config': cfg}
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return {'ok': False, 'error': f'HA unreachable: {exc}', 'config': cfg}

    entities: list[dict] = []
    entity_count = 0
    try:
        req2 = urllib.request.Request(url + '/api/states', headers=headers, method='GET')
        with urllib.request.urlopen(req2, timeout=timeout) as resp2:
            raw = json.loads(resp2.read().decode('utf-8', errors='replace') or '[]')
            if isinstance(raw, list):
                entity_count = len(raw)
                for row in raw[:50]:
                    if not isinstance(row, dict):
                        continue
                    entities.append({
                        'entity_id': row.get('entity_id'),
                        'state': str(row.get('state') or '')[:80],
                        'friendly_name': ((row.get('attributes') or {}) or {}).get('friendly_name'),
                    })
    except Exception as exc:
        return {
            'ok': api_ok,
            'error': f'API ok but entity discovery failed: {exc}',
            'entity_count': 0,
            'entities': [],
            'config': cfg,
        }

    path = _config_path(layout)
    existing = read_json(path, default={}) or {}
    existing.update({
        'url': url,
        'token_configured': True,
        'verified': True,
        'entity_count': entity_count,
        'last_verify_ts': __import__('time').time(),
    })
    existing.pop('token', None)
    atomic_write_json(path, existing)
    return {
        'ok': True,
        'message': body[:200] if api_ok else 'connected',
        'entity_count': entity_count,
        'entities': entities,
        'config': load_ha_config(layout),
        'state': probe_home_assistant(layout).state,
    }


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
    disc = {**cfg, 'auto_install': True}
    if not cfg.get('url') or not cfg.get('token_configured'):
        disc['user_action'] = 'credential'
        return CapabilityReport(
            CAPABILITY_ID, OWNER_AGENT, CapabilityState.NEEDS_CREDENTIAL.value,
            detail=(
                'Home Assistant is supported. Otacon needs your HA URL and a '
                'long-lived access token once — then it can verify and wire entities.'
            ),
            config_keys_present=keys, discovery=disc,
        )
    if cfg.get('verified') and cfg.get('entity_count', 0) >= 0:
        disc['user_action'] = 'none'
        n = int(cfg.get('entity_count') or 0)
        return CapabilityReport(
            CAPABILITY_ID, OWNER_AGENT, CapabilityState.READY.value,
            detail=f'Home Assistant connected — {n} entities discovered.',
            config_keys_present=keys, discovery=disc,
        )
    # Credentials present but not verified yet
    disc['user_action'] = 'verify'
    return CapabilityReport(
        CAPABILITY_ID, OWNER_AGENT, CapabilityState.LIMITED.value,
        detail='HA credentials stored — run verify to confirm connectivity and discover entities.',
        config_keys_present=keys, discovery=disc,
    )
