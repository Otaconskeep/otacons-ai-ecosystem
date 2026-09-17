"""Canonical room / page registry for Keep Expansion.

All navigation surfaces register here. Page Builder uses the same allowlist.
No arbitrary code execution, JS injection, or filesystem source loading.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Optional

from expansion.persist import atomic_write_json, read_json
from expansion.state_layout import StateLayout, resolve_layout

ROOM_SCHEMA_VERSION = 1
_ID_RE = re.compile(r'^[a-z][a-z0-9_-]{1,63}$')
_ROUTE_RE = re.compile(r'^/[a-z0-9][a-z0-9_/-]{0,127}$')


@dataclass
class RoomPage:
    schema_version: int
    page_id: str
    name: str
    route: str
    owner_agent: str
    icon: str
    description: str
    required_capabilities: tuple = ()
    permissions: tuple = ()
    health_source: str = ''
    enabled: bool = True
    shared: bool = False
    kind: str = 'room'  # room | shared_surface | page_builder

    def validate(self) -> list:
        errors = []
        if self.schema_version != ROOM_SCHEMA_VERSION:
            errors.append('unsupported room schema_version')
        if not _ID_RE.match(self.page_id or ''):
            errors.append(f'invalid page_id {self.page_id!r}')
        if not _ROUTE_RE.match(self.route or ''):
            errors.append(f'invalid route {self.route!r}')
        if not self.name.strip():
            errors.append('name required')
        # Forbidden patterns — no executable injection surfaces
        blob = f'{self.page_id} {self.route} {self.description}'.lower()
        for banned in ('javascript:', 'eval(', '<script', 'importlib', 'subprocess', '.dll'):
            if banned in blob:
                errors.append(f'forbidden injection pattern {banned!r}')
        return errors


DEFAULT_ROOMS = (
    RoomPage(ROOM_SCHEMA_VERSION, 'aria_command', 'Aria Command Floor', '/command',
             'aria', 'CMD', 'Roster, delegations, readiness, pending decisions.',
             required_capabilities=('AGENTS',), permissions=('coordinator',),
             health_source='readiness', kind='room'),
    RoomPage(ROOM_SCHEMA_VERSION, 'war_room', 'War Room', '/war-room',
             'vector', 'WR', 'Active jobs, failures, decision queue, recovery.',
             required_capabilities=('AGENTS',), permissions=('engineer',),
             health_source='jobs', kind='room'),
    RoomPage(ROOM_SCHEMA_VERSION, 'project_rex', 'Project REX', '/rex',
             'aria', 'REX',
             'Autonomous job coordination substrate — discover→close under policy, not approvals.',
             required_capabilities=('AGENTS',), permissions=('coordinator',),
             health_source='jobs', shared=True, kind='shared_surface'),
    RoomPage(ROOM_SCHEMA_VERSION, 'intel', 'Intel / Continuity', '/intel',
             'ledger', 'INT', 'Memories, journals, living dossiers, event search.',
             required_capabilities=('AGENTS',), permissions=('archivist',),
             health_source='journal', kind='room'),
    RoomPage(ROOM_SCHEMA_VERSION, 'learning', 'Learning Engine', '/learning',
             'ledger', 'LRN',
             'Evidence-backed learned claims — private + shared Keep; WHY provenance.',
             required_capabilities=('AGENTS',), permissions=('archivist',),
             health_source='journal', shared=True, kind='shared_surface'),
    RoomPage(ROOM_SCHEMA_VERSION, 'creative', 'Creative Studio', '/video-studio',
             'muse', 'CRE', 'Creative queue and Studio readiness (heavy Studio is P3).',
             required_capabilities=('MOTION',), permissions=('curator',),
             health_source='video_studio', kind='room'),
    RoomPage(ROOM_SCHEMA_VERSION, 'ops', 'Operations / Security', '/ops',
             'sentry', 'OPS', 'Alerts, monitoring jobs, package/service readiness.',
             required_capabilities=('AGENTS',), permissions=('sentinel',),
             health_source='jobs', kind='room'),
    RoomPage(ROOM_SCHEMA_VERSION, 'dashboard', 'Dashboard', '/dashboard',
             'aria', 'DASH', 'Owner overview of Expansion runtime.',
             shared=True, kind='shared_surface', health_source='readiness'),
    RoomPage(ROOM_SCHEMA_VERSION, 'codec', 'Codec', '/codec',
             'aria', 'CDC', 'Multi-agent Codec conversation surface.',
             shared=True, kind='shared_surface', health_source='codec_reaches_agent'),
    RoomPage(ROOM_SCHEMA_VERSION, 'agent_reports', 'Agent Reports', '/reports',
             'aria', 'RPT', 'Per-agent operational reports with provenance.',
             shared=True, kind='shared_surface', health_source='jobs'),
    RoomPage(ROOM_SCHEMA_VERSION, 'page_builder', 'Page Builder', '/pages/builder',
             'aria', 'PB', 'Allowlisted custom pages via registry only.',
             shared=True, kind='page_builder', health_source='readiness'),
)


class RoomRegistry:
    def __init__(self, layout: Optional[StateLayout] = None):
        self.layout = layout or resolve_layout()
        self.layout.user_pages.mkdir(parents=True, exist_ok=True)
        self._path = self.layout.user_pages / 'registry.json'

    def seed_defaults(self) -> list[RoomPage]:
        data = read_json(self._path, default={'schema_version': ROOM_SCHEMA_VERSION, 'pages': {}})
        pages = data.setdefault('pages', {})
        for room in DEFAULT_ROOMS:
            errors = room.validate()
            if errors:
                raise ValueError(f'{room.page_id}: {errors}')
            if room.page_id not in pages:
                pages[room.page_id] = asdict(room)
        # normalize tuples
        for pid, raw in list(pages.items()):
            for k in ('required_capabilities', 'permissions'):
                if isinstance(raw.get(k), list):
                    raw[k] = tuple(raw[k])
            pages[pid] = raw
        atomic_write_json(self._path, data)
        return self.list()

    def list(self) -> list[RoomPage]:
        data = read_json(self._path, default={'pages': {}})
        out = []
        for raw in (data.get('pages') or {}).values():
            for k in ('required_capabilities', 'permissions'):
                if isinstance(raw.get(k), list):
                    raw[k] = tuple(raw[k])
            out.append(RoomPage(**{k: raw[k] for k in RoomPage.__dataclass_fields__ if k in raw}))
        out.sort(key=lambda p: p.route)
        return out

    def get(self, page_id: str) -> Optional[RoomPage]:
        for p in self.list():
            if p.page_id == page_id:
                return p
        return None

    def register_page(self, page: RoomPage) -> RoomPage:
        """Page Builder path — allowlisted schema only, no code injection."""
        errors = page.validate()
        if errors:
            raise ValueError('; '.join(errors))
        data = read_json(self._path, default={'schema_version': ROOM_SCHEMA_VERSION, 'pages': {}})
        pages = data.setdefault('pages', {})
        # Collision checks
        for existing in pages.values():
            if existing.get('page_id') == page.page_id:
                raise ValueError(f'page_id collision: {page.page_id}')
            if existing.get('route') == page.route:
                raise ValueError(f'route collision: {page.route}')
        if page.kind not in ('room', 'shared_surface', 'page_builder'):
            raise ValueError('invalid kind')
        pages[page.page_id] = asdict(page)
        atomic_write_json(self._path, data)
        return page
