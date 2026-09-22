"""Homescreen launchpad — Command Center tile map for Lite + Premium.

Mirrors operator Homepage (:3003) *organization*: grouped tiles, live/grey
states, companion products (Keep Desk / KeepRoute) auto-appear when discovered
or configured. No private LAN IPs hardcoded.
"""
from __future__ import annotations

import json
import os
import socket
import time
from typing import Any, Optional
from urllib.parse import urlparse

from expansion.persist import atomic_write_json, read_json
from expansion.state_layout import StateLayout, resolve_layout

# Localhost probes only — never bake lab hostnames into public packages.
_COMPANION_DEFAULTS = (
    {
        'id': 'keep_desk',
        'title': 'Keep Desk',
        'desc': 'Not a separate product yet — use KeepRoute',
        'group': 'Keep products',
        'env': 'OTACON_KEEP_DESK_URL',
        'pref_key': 'keep_desk_url',
        # No shipped listener — 5765/5766 were phantom probe ports only.
        'ports': (),
        'shipped': False,
        'icon': 'DESK',
    },
    {
        'id': 'keeproute',
        'title': 'KeepRoute',
        'desc': 'Mission orchestration on OmniRoute',
        'group': 'Keep products',
        'env': 'OTACON_KEEPROUTE_URL',
        'pref_key': 'keeproute_url',
        'ports': (20129,),
        'shipped': True,
        'icon': 'ROUTE',
    },
    {
        'id': 'omniroute',
        'title': 'OmniRoute',
        'desc': 'Upstream routing data plane',
        'group': 'Keep products',
        'env': 'OMNIROUTE_HOST',
        'pref_key': 'omniroute_url',
        'ports': (20128, 20127),
        'shipped': True,
        'icon': 'OMNI',
    },
)


def _prefs_path(layout: StateLayout):
    return layout.user_preferences / 'launchpad.json'


def load_prefs(layout: Optional[StateLayout] = None) -> dict:
    layout = layout or resolve_layout()
    layout.ensure_user_dirs()
    raw = read_json(_prefs_path(layout), default={}) or {}
    return raw if isinstance(raw, dict) else {}


def save_prefs(updates: dict, layout: Optional[StateLayout] = None) -> dict:
    layout = layout or resolve_layout()
    layout.ensure_user_dirs()
    cur = load_prefs(layout)
    companion_keys = {s['pref_key'] for s in _COMPANION_DEFAULTS}
    for k, v in (updates or {}).items():
        if v is None:
            cur.pop(k, None)
        elif k in companion_keys:
            normalized = _normalize_companion_url(str(v))
            if normalized:
                cur[k] = normalized
            else:
                # Reject scheme-less junk (e.g. "127.0.0.1:98") so discovery works.
                cur.pop(k, None)
        else:
            cur[k] = v
    cur['updated_at'] = time.time()
    atomic_write_json(_prefs_path(layout), cur)
    return cur


def _tcp_open(host: str, port: int, timeout: float = 0.35) -> bool:
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True
    except OSError:
        return False


def _normalize_companion_url(raw: str) -> str:
    """Accept only http(s) URLs. Scheme-less host:port values are rejected.

    urlparse('127.0.0.1:99') treats '127.0.0.1' as the scheme and falls back to
    port 80 — always dead — and used to permanently mask port discovery.
    """
    u = (raw or '').strip()
    if not u:
        return ''
    parsed = urlparse(u)
    if parsed.scheme in ('http', 'https') and (parsed.hostname or parsed.netloc):
        return u
    return ''


def _probe_url(url: str) -> bool:
    normalized = _normalize_companion_url(url)
    if not normalized:
        return False
    try:
        u = urlparse(normalized)
        host = u.hostname or '127.0.0.1'
        port = u.port or (443 if u.scheme == 'https' else 80)
        return _tcp_open(host, port)
    except Exception:
        return False


def _resolve_companion(spec: dict, prefs: dict) -> dict[str, Any]:
    raw = (
        (os.environ.get(spec['env']) or '').strip()
        or str(prefs.get(spec['pref_key']) or '').strip()
    )
    url = _normalize_companion_url(raw)
    live = False
    source = 'missing'
    if raw and not url:
        # Configured junk — ignore and fall through to port discovery.
        source = 'invalid_config'
    if url:
        live = _probe_url(url)
        source = 'configured'
    elif spec.get('shipped', True):
        for port in spec.get('ports') or ():
            if _tcp_open('127.0.0.1', int(port)):
                url = f'http://127.0.0.1:{port}/'
                live = True
                source = 'discovered'
                break
    if not spec.get('shipped', True) and not url:
        source = 'missing'
        hint = 'Not shipped as a separate product — open KeepRoute instead'
    elif not url:
        hint = f'Set {spec["env"]} or launchpad pref {spec["pref_key"]}'
    else:
        hint = 'LIVE' if live else 'Configured · unreachable'
    return {
        'id': spec['id'],
        'title': spec['title'],
        'desc': spec['desc'],
        'group': spec['group'],
        'icon': spec['icon'],
        'kind': 'external',
        'href': url or '',
        'live': bool(live and url),
        'available': bool(url),
        'source': source,
        'shipped': bool(spec.get('shipped', True)),
        'hint': hint,
    }


def _core_tiles(*, expansion_on: bool, lite: bool) -> list[dict]:
    tiles = [
        {
            'id': 'codec',
            'title': 'Codec',
            'desc': 'Talk to your agents',
            'group': 'Front doors',
            'icon': 'CDC',
            'kind': 'internal',
            'action': 'codec',
            'live': True,
            'available': True,
        },
        {
            'id': 'setup',
            'title': 'Setup Wizard',
            'desc': 'Hardware · agent · features',
            'group': 'Front doors',
            'icon': 'SET',
            'kind': 'internal',
            'action': 'setup',
            'live': True,
            'available': True,
        },
    ]
    if expansion_on:
        tiles.extend([
            {
                'id': 'war-room',
                'title': 'War Room',
                'desc': 'Jobs · recovery · decisions',
                'group': 'Expansion rooms',
                'icon': 'WAR',
                'kind': 'internal',
                'action': 'war-room',
                'live': True,
                'available': True,
            },
            {
                'id': 'rex',
                'title': 'Project REX',
                'desc': 'Autonomous work board',
                'group': 'Expansion rooms',
                'icon': 'REX',
                'kind': 'internal',
                'action': 'rex',
                'live': True,
                'available': True,
            },
            {
                'id': 'intel',
                'title': 'Intel',
                'desc': 'Continuity · journals · dossiers',
                'group': 'Expansion rooms',
                'icon': 'INT',
                'kind': 'internal',
                'action': 'intel',
                'live': True,
                'available': True,
            },
            {
                'id': 'command',
                'title': 'Aria Command',
                'desc': 'Roster · readiness · delegations',
                'group': 'Expansion rooms',
                'icon': 'CMD',
                'kind': 'internal',
                'action': 'command',
                'live': True,
                'available': True,
            },
            {
                'id': 'creative',
                'title': 'Creative Studio',
                'desc': 'Muse workshop / video studio',
                'group': 'Expansion rooms',
                'icon': 'CRE',
                'kind': 'internal',
                'action': 'creative',
                'live': True,
                'available': True,
            },
            {
                'id': 'genome',
                'title': 'Genome',
                'desc': 'Voice trainer',
                'group': 'Expansion rooms',
                'icon': 'GNM',
                'kind': 'internal',
                'action': 'genome',
                'live': True,
                'available': True,
            },
            {
                'id': 'learning',
                'title': 'Learning',
                'desc': 'Evidence-backed claims',
                'group': 'Expansion rooms',
                'icon': 'LRN',
                'kind': 'internal',
                'action': 'learning',
                'live': True,
                'available': True,
            },
            {
                'id': 'ops',
                'title': 'Ops / Security',
                'desc': 'Sentry monitoring',
                'group': 'Expansion rooms',
                'icon': 'OPS',
                'kind': 'internal',
                'action': 'ops',
                'live': True,
                'available': True,
            },
            {
                'id': 'relationships',
                'title': 'Relationships',
                'desc': 'Directional matrix',
                'group': 'Expansion rooms',
                'icon': 'REL',
                'kind': 'internal',
                'action': 'relationships',
                'live': True,
                'available': True,
            },
            {
                'id': 'emotions',
                'title': 'Emotions',
                'desc': 'Affect floor + WHY',
                'group': 'Expansion rooms',
                'icon': 'EMO',
                'kind': 'internal',
                'action': 'emotion',
                'live': True,
                'available': True,
            },
        ])
    else:
        tiles.append({
            'id': 'expansion',
            'title': 'Expansion Premium',
            'desc': 'Five-agent roster · REX · floors — run Expansion Setup',
            'group': 'Front doors',
            'icon': 'EXP',
            'kind': 'internal',
            'action': 'setup',
            'live': False,
            'available': True,
            'hint': 'Lite · unlock with Expansion',
        })
    if lite and not expansion_on:
        pass
    return tiles


def build_launchpad(layout: Optional[StateLayout] = None) -> dict[str, Any]:
    layout = layout or resolve_layout()
    prefs = load_prefs(layout)
    expansion_on = False
    try:
        from expansion.entitlement import EntitlementGate
        expansion_on = EntitlementGate(layout).expansion_surfaces_allowed()
        # Roster present counts as Expansion UX even in local_dev
        if not expansion_on and layout.user_agents.is_dir():
            expansion_on = any(layout.user_agents.glob('default-*.json'))
    except Exception:
        expansion_on = False

    tiles = _core_tiles(expansion_on=expansion_on, lite=not expansion_on)
    companions = [_resolve_companion(spec, prefs) for spec in _COMPANION_DEFAULTS]
    # Always show companion slots (grey until discovered/configured) — like Homepage.
    tiles.extend(companions)

    # Extra user bookmarks (no code injection — href + title only)
    for row in prefs.get('bookmarks') or []:
        if not isinstance(row, dict):
            continue
        href = str(row.get('href') or '').strip()
        title = str(row.get('title') or '').strip()
        if not href or not title or href.lower().startswith('javascript:'):
            continue
        tiles.append({
            'id': f"bm_{(row.get('id') or title).lower().replace(' ', '_')[:32]}",
            'title': title[:64],
            'desc': str(row.get('desc') or 'Bookmark')[:120],
            'group': str(row.get('group') or 'Bookmarks')[:48],
            'icon': str(row.get('icon') or 'LNK')[:8],
            'kind': 'external',
            'href': href,
            'live': _probe_url(href),
            'available': True,
            'source': 'bookmark',
        })

    groups: dict[str, list] = {}
    for t in tiles:
        groups.setdefault(t.get('group') or 'Other', []).append(t)

    tabs = [
        {'id': 'homescreen', 'label': 'Homescreen', 'action': 'homescreen'},
        {'id': 'codec', 'label': 'Codec', 'action': 'codec'},
    ]
    if expansion_on:
        tabs.extend([
            {'id': 'war-room', 'label': 'War', 'action': 'war-room'},
            {'id': 'rex', 'label': 'REX', 'action': 'rex'},
            {'id': 'intel', 'label': 'Intel', 'action': 'intel'},
            {'id': 'creative', 'label': 'Studio', 'action': 'creative'},
            {'id': 'genome', 'label': 'Genome', 'action': 'genome'},
        ])
    for c in companions:
        if c.get('available'):
            tabs.append({
                'id': c['id'],
                'label': c['title'],
                'action': 'external',
                'href': c.get('href') or '',
                'live': c.get('live'),
            })

    return {
        'surface': 'command_center',
        'title': 'Otacon Command Center',
        'note': (
            'Homescreen launchpad — same organization idea as operator Homepage: '
            'grouped tiles, live/grey companions, click SFX. Keep Desk / KeepRoute '
            'tiles appear when discovered on localhost or configured via env/prefs.'
        ),
        'expansion': expansion_on,
        'edition': 'premium' if expansion_on else 'lite',
        'tabs': tabs,
        'groups': [{'name': g, 'tiles': items} for g, items in groups.items()],
        'tiles': tiles,
        'prefs': {
            'keep_desk_url': prefs.get('keep_desk_url') or '',
            'keeproute_url': prefs.get('keeproute_url') or '',
            'omniroute_url': prefs.get('omniroute_url') or '',
        },
    }
