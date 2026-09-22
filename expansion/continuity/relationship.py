# -*- coding: utf-8 -*-
"""Relationship Engine — Formula 5 for public Expansion Premium.

Bounded delta + slow drift toward neutral (0.50).
Clean-room Keep-parity. Public roster only — no private Keep edges / IP names.
Operator bond target is always ``user_primary`` (placeholder; no owner PII).
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Optional

from expansion.state_layout import StateLayout, resolve_layout

_NEUTRAL = 0.50
_DRIFT = 0.008

PUBLIC_AGENTS = frozenset({'aria', 'vector', 'ledger', 'muse', 'sentry'})
OPERATOR_ID = 'user_primary'

# Public display names for co-mention detection (product roster only)
_DISPLAY = {
    'aria': 'aria',
    'vector': 'vector',
    'ledger': 'ledger',
    'muse': 'muse',
    'sentry': 'sentry',
}

_EVENT_DELTAS: dict[str, list[tuple[str, float]]] = {
    'social_mention_positive': [('ally', +0.022), ('colleague', +0.012)],
    'social_mention_negative': [('rival', +0.022), ('adversary', +0.012), ('ally', -0.035)],
    'agent_ask_collaboration': [('ally', +0.012), ('colleague', +0.010)],
    'collaboration_success': [('ally', +0.012), ('colleague', +0.015)],
    'collaboration_failure': [('ally', -0.015), ('colleague', -0.020)],
    'operator_ask': [('ally', +0.006), ('colleague', +0.004)],
    'operator_ask_subjective': [('ally', +0.012), ('colleague', +0.006)],
    'user_praise': [('ally', +0.018), ('colleague', +0.010)],
    'user_gratitude': [('ally', +0.014), ('colleague', +0.008)],
    'user_hostile': [('ally', -0.035), ('rival', +0.020)],
    'user_hostility': [('ally', -0.035), ('rival', +0.020)],
    'user_critique': [('ally', -0.012), ('colleague', -0.006)],
    'user_apology': [('ally', +0.010), ('colleague', +0.006)],
    'social_reply_agree': [('ally', +0.010), ('colleague', +0.008)],
    'social_reply_disagree': [('rival', +0.014), ('ally', -0.010)],
}

# Mock org seed — Aria coordinates; others are peers (product fiction only)
_ORG_SEED: list[tuple[str, str, str, float]] = [
    ('vector', 'aria', 'subordinate', 0.68),
    ('ledger', 'aria', 'subordinate', 0.66),
    ('muse', 'aria', 'colleague', 0.62),
    ('sentry', 'aria', 'colleague', 0.60),
    ('aria', 'vector', 'mentor', 0.58),
    ('aria', 'ledger', 'mentor', 0.58),
    ('aria', 'muse', 'colleague', 0.55),
    ('aria', 'sentry', 'colleague', 0.55),
    ('vector', 'ledger', 'colleague', 0.52),
    ('ledger', 'vector', 'colleague', 0.52),
    ('muse', 'sentry', 'colleague', 0.50),
    ('sentry', 'muse', 'colleague', 0.50),
]

_lock = threading.Lock()


def _canon(raw: str | None) -> str:
    s = (raw or '').strip().lower().replace('-', '_').replace(' ', '_')
    if s in ('owner', 'user', 'operator'):
        return OPERATOR_ID
    return s


def apply_formula5(cur: float, delta: float) -> float:
    """Formula 5 — Relationship Update Model."""
    new = cur + delta - _DRIFT * (cur - _NEUTRAL)
    return round(max(0.0, min(1.0, new)), 4)


def _store_path(layout: StateLayout) -> Path:
    return Path(layout.user_data_root) / 'personnel_relationships.json'


def _load_edges(layout: StateLayout) -> list[dict]:
    path = _store_path(layout)
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        if isinstance(data, dict):
            edges = data.get('edges') or []
        elif isinstance(data, list):
            edges = data
        else:
            edges = []
        return [e for e in edges if isinstance(e, dict)]
    except Exception:
        return []


def _save_edges(layout: StateLayout, edges: list[dict]) -> None:
    path = _store_path(layout)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        'schema': 'expansion.continuity.formula5.v1',
        'updated_at': time.time(),
        'privacy': {'no_private_keep_data': True, 'operator_id': OPERATOR_ID},
        'edges': edges,
    }
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    tmp.replace(path)


class RelationshipEngine:
    """Formula 5 relationship graph for Premium Expansion."""

    @staticmethod
    def ensure_seeded(*, layout: Optional[StateLayout] = None) -> None:
        layout = layout or resolve_layout()
        with _lock:
            edges = _load_edges(layout)
            if edges:
                return
            seeded = []
            for frm, to, rtype, strength in _ORG_SEED:
                seeded.append({
                    'from': frm, 'to': to, 'type': rtype,
                    'strength': strength, 'notes': 'mock_org_seed',
                    'updated_at': time.time(),
                })
            # Neutral operator bonds for each public agent
            for aid in PUBLIC_AGENTS:
                seeded.append({
                    'from': aid, 'to': OPERATOR_ID, 'type': 'ally',
                    'strength': _NEUTRAL, 'notes': 'placeholder_operator_bond',
                    'updated_at': time.time(),
                })
                seeded.append({
                    'from': aid, 'to': OPERATOR_ID, 'type': 'colleague',
                    'strength': _NEUTRAL, 'notes': 'placeholder_operator_bond',
                    'updated_at': time.time(),
                })
            _save_edges(layout, seeded)

    @staticmethod
    def get(from_id: str, to_id: str, *, layout: Optional[StateLayout] = None) -> list[dict]:
        layout = layout or resolve_layout()
        RelationshipEngine.ensure_seeded(layout=layout)
        frm, to = _canon(from_id), _canon(to_id)
        return [r for r in _load_edges(layout) if r.get('from') == frm and r.get('to') == to]

    @staticmethod
    def strength(
        from_id: str, to_id: str, rel_type: str = '',
        *, layout: Optional[StateLayout] = None,
    ) -> float:
        rels = RelationshipEngine.get(from_id, to_id, layout=layout)
        if rel_type:
            rels = [r for r in rels if r.get('type') == rel_type]
        if not rels:
            return _NEUTRAL
        return max(float(r.get('strength', _NEUTRAL)) for r in rels)

    @staticmethod
    def add_relationship(
        from_id: str, to_id: str, rel_type: str, *,
        strength: float = _NEUTRAL, notes: str = '',
        layout: Optional[StateLayout] = None,
    ) -> None:
        layout = layout or resolve_layout()
        frm, to = _canon(from_id), _canon(to_id)
        if not frm or not to or frm == to:
            return
        with _lock:
            edges = _load_edges(layout)
            found = False
            for e in edges:
                if e.get('from') == frm and e.get('to') == to and e.get('type') == rel_type:
                    e['strength'] = round(max(0.0, min(1.0, float(strength))), 4)
                    e['notes'] = notes or e.get('notes') or ''
                    e['updated_at'] = time.time()
                    found = True
                    break
            if not found:
                edges.append({
                    'from': frm, 'to': to, 'type': rel_type,
                    'strength': round(max(0.0, min(1.0, float(strength))), 4),
                    'notes': notes, 'updated_at': time.time(),
                })
            _save_edges(layout, edges)

    @staticmethod
    def update_on_event(
        from_id: str, to_id: str, event_type: str,
        notes: str = '', *, layout: Optional[StateLayout] = None,
    ) -> dict:
        layout = layout or resolve_layout()
        RelationshipEngine.ensure_seeded(layout=layout)
        frm, to = _canon(from_id), _canon(to_id)
        if not frm or not to or frm == to:
            return {'ok': False, 'reason': 'invalid_pair'}
        type_deltas = _EVENT_DELTAS.get(event_type)
        if not type_deltas:
            return {'ok': False, 'reason': 'unknown_event', 'event_type': event_type}
        changed: dict[str, float] = {}
        for rel_type, delta in type_deltas:
            cur = RelationshipEngine.strength(frm, to, rel_type, layout=layout)
            # If typed edge missing, fall back to max any-type then seed
            if cur == _NEUTRAL and not any(
                r.get('type') == rel_type for r in RelationshipEngine.get(frm, to, layout=layout)
            ):
                cur = RelationshipEngine.strength(frm, to, layout=layout)
            new = apply_formula5(cur, delta)
            RelationshipEngine.add_relationship(
                frm, to, rel_type, strength=new, notes=notes or event_type, layout=layout,
            )
            changed[rel_type] = new
        return {'ok': True, 'from': frm, 'to': to, 'event_type': event_type, 'updated': changed}

    @staticmethod
    def relationships_for(entity_id: str, *, layout: Optional[StateLayout] = None) -> list[dict]:
        layout = layout or resolve_layout()
        RelationshipEngine.ensure_seeded(layout=layout)
        eid = _canon(entity_id)
        return [
            r for r in _load_edges(layout)
            if r.get('from') == eid or r.get('to') == eid
        ]

    @staticmethod
    def relationship_summary_for_prompt(
        entity_id: str, limit: int = 4, *, layout: Optional[StateLayout] = None,
    ) -> str:
        rels = RelationshipEngine.relationships_for(entity_id, layout=layout)
        meaningful = [r for r in rels if abs(float(r.get('strength', 0.5)) - 0.5) > 0.08]
        if not meaningful:
            return ''
        meaningful.sort(key=lambda r: abs(float(r.get('strength', 0.5)) - 0.5), reverse=True)
        lines = []
        eid = _canon(entity_id)
        for r in meaningful[:limit]:
            s = float(r.get('strength', 0.5))
            other = r.get('to') if r.get('from') == eid else r.get('from')
            # Never surface private Keep names — only public IDs
            if other not in PUBLIC_AGENTS and other != OPERATOR_ID:
                continue
            label = 'operator' if other == OPERATOR_ID else other
            dirn = '→' if r.get('from') == eid else '←'
            qual = 'strong' if s > 0.72 else ('strained' if s < 0.35 else 'moderate')
            lines.append(f"{dirn}{label} [{r.get('type', '?')} {qual} {s:.2f}]")
        return '[Relationships] ' + ', '.join(lines) if lines else ''

    @staticmethod
    def operator_rel_level(entity_id: str, *, layout: Optional[StateLayout] = None) -> str:
        ally_s = RelationshipEngine.strength(entity_id, OPERATOR_ID, 'ally', layout=layout)
        if ally_s > 0.63:
            return 'familiar'
        if ally_s < 0.40:
            return 'reserved'
        return 'neutral'

    @staticmethod
    def mentioned_agents_in_message(message: str) -> list[str]:
        lowered = (message or '').lower()
        found = []
        for eid, display in _DISPLAY.items():
            if display and len(display) > 2 and display in lowered:
                found.append(eid)
        return found

    @staticmethod
    def sync_dim_store(
        from_id: str, to_id: str, *, layout: Optional[StateLayout] = None,
    ) -> None:
        """Mirror Formula 5 ally/rival into Expansion RelationshipStore dimensions."""
        layout = layout or resolve_layout()
        try:
            from expansion.relationship_store import RelationshipStore
            ally = RelationshipEngine.strength(from_id, to_id, 'ally', layout=layout)
            rival = RelationshipEngine.strength(from_id, to_id, 'rival', layout=layout)
            rs = RelationshipStore(layout)
            rel = rs.get_or_create(_canon(from_id), _canon(to_id), use_triangle_presets=False)
            dims = dict(rel.dimensions or {})
            dims['trust'] = max(0.0, min(1.0, 0.35 + 0.55 * ally))
            dims['affinity'] = max(0.0, min(1.0, 0.30 + 0.55 * ally))
            dims['attachment'] = max(0.0, min(1.0, 0.30 + 0.50 * ally))
            dims['rivalry'] = max(0.0, min(1.0, rival))
            rel.dimensions = dims
            rs.save(rel)
        except Exception:
            pass
