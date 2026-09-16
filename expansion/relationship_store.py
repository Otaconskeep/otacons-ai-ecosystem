"""Persistent directional relationship store (user data)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from expansion.relationship import EvidenceType
from expansion.relationship_graph import (
    DirectionalRelationship, new_directional, to_dict as rel_to_dict,
)
from expansion.state_layout import StateLayout, resolve_layout


def _key(source_id: str, target_id: str) -> str:
    return f'{source_id}__{target_id}'


def _from_dict(d: dict) -> DirectionalRelationship:
    from expansion.relationship import RelationshipState
    d = dict(d)
    legacy = d.get('legacy')
    if isinstance(legacy, dict):
        ev = legacy.get('evidence', EvidenceType.INFERRED_BASELINE.value)
        if isinstance(ev, str):
            try:
                ev = EvidenceType(ev)
            except ValueError:
                ev = EvidenceType.INFERRED_BASELINE
        legacy = RelationshipState(
            trust=float(legacy.get('trust', 0.5)),
            irritation=float(legacy.get('irritation', 0.0)),
            evidence=ev,
            event_count=int(legacy.get('event_count', 0)),
            last_event_at=float(legacy.get('last_event_at', 0.0)),
        )
        d['legacy'] = legacy
    if isinstance(d.get('provenance_event_ids'), list):
        d['provenance_event_ids'] = tuple(d['provenance_event_ids'])
    fields = DirectionalRelationship.__dataclass_fields__
    return DirectionalRelationship(**{k: v for k, v in d.items() if k in fields}).clamp()


class RelationshipStore:
    def __init__(self, layout: Optional[StateLayout] = None):
        self.layout = layout or resolve_layout()
        self.layout.user_relationships.mkdir(parents=True, exist_ok=True)

    def _path(self, source_id: str, target_id: str) -> Path:
        return self.layout.user_relationships / f'{_key(source_id, target_id)}.json'

    def get(self, source_id: str, target_id: str) -> Optional[DirectionalRelationship]:
        path = self._path(source_id, target_id)
        if not path.is_file():
            return None
        return _from_dict(json.loads(path.read_text(encoding='utf-8')))

    def get_or_create(
        self,
        source_id: str,
        target_id: str,
        *,
        use_triangle_presets: bool = True,
    ) -> DirectionalRelationship:
        existing = self.get(source_id, target_id)
        if existing is not None:
            return existing
        rel = new_directional(
            source_id, target_id, use_triangle_presets=use_triangle_presets,
        )
        self.save(rel)
        return rel

    def save(self, rel: DirectionalRelationship) -> Path:
        path = self._path(rel.source_id, rel.target_id)
        path.write_text(json.dumps(rel_to_dict(rel), indent=2) + '\n', encoding='utf-8')
        return path

    def all_for(self, agent_id: str) -> list[DirectionalRelationship]:
        out = []
        for path in sorted(self.layout.user_relationships.glob('*.json')):
            try:
                rel = _from_dict(json.loads(path.read_text(encoding='utf-8')))
            except (json.JSONDecodeError, OSError, TypeError, KeyError):
                continue
            if rel.source_id == agent_id or rel.target_id == agent_id:
                out.append(rel)
        return out

    def ensure_roster_graph(self, agent_ids: list[str]) -> list[DirectionalRelationship]:
        """Create directed edges for every ordered pair (no self-edges)."""
        created = []
        for src in agent_ids:
            for dst in agent_ids:
                if src == dst:
                    continue
                created.append(self.get_or_create(src, dst))
        # Also ensure user edges for each agent (agent → user_primary, user_primary → agent)
        for aid in agent_ids:
            created.append(self.get_or_create(aid, 'user_primary', use_triangle_presets=False))
            created.append(self.get_or_create('user_primary', aid, use_triangle_presets=False))
        return created
