# -*- coding: utf-8 -*-
"""Conversational affect — user message → emotion/relationship mutation + dual-affect prompt.

Clean-room Keep-parity for public Expansion agents only.
"""
from __future__ import annotations

import re
import time
from typing import Any, Optional

from expansion.state_layout import StateLayout, resolve_layout

_HOSTILE = re.compile(
    r'\b(?:you(?:\'re| are) (?:useless|lazy|stupid|dumb)|shut up|i hate you|'
    r'you suck|worst|idiot|not a good job|being lazy)\b',
    re.I,
)
_PRAISE = re.compile(
    r'\b(?:thank(?:s| you)|good job|well done|proud|love (?:you|that)|'
    r'amazing|brilliant|perfect|appreciate)\b',
    re.I,
)
_CRITIQUE = re.compile(
    r'\b(?:that(?:\'s| is) wrong|incorrect|fix (?:that|this)|you messed up|'
    r'not what i (?:said|meant)|do better|try again)\b',
    re.I,
)
_APOLOGY = re.compile(
    r'\b(?:i(?:\'m| am) sorry|i apologize|forgive me|my bad)\b',
    re.I,
)


def _f(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return float(default)


def _level_word(v: float, *, low: float = 0.22, mid: float = 0.40, high: float = 0.60) -> str:
    if v >= high:
        return 'elevated'
    if v >= mid:
        return 'noticeable'
    if v >= low:
        return 'mild'
    return 'low'


def _bond_word(v: float) -> str:
    if v >= 0.85:
        return 'very high'
    if v >= 0.70:
        return 'high'
    if v >= 0.50:
        return 'moderate'
    if v >= 0.35:
        return 'guarded'
    return 'low'


def classify_interpersonal_events(user_text: str) -> list[dict]:
    msg = user_text or ''
    out: list[dict] = []
    if _HOSTILE.search(msg):
        out.append({'event_type': 'user_hostile', 'intensity': 0.85})
    if _CRITIQUE.search(msg):
        out.append({'event_type': 'user_critique', 'intensity': 0.55})
    if _PRAISE.search(msg):
        out.append({'event_type': 'user_praise', 'intensity': 0.70})
    if _APOLOGY.search(msg):
        out.append({'event_type': 'user_apology', 'intensity': 0.60})
    return out


def apply_user_message_events(
    entity_id: str,
    user_text: str,
    *,
    layout: Optional[StateLayout] = None,
    target_id: str = 'user_primary',
) -> dict:
    """Mutate Expansion emotion + relationship from the user turn. Never raises."""
    from expansion.continuity.emotion_bridge import (
        apply_formula4_update,
        apply_formula7_residue,
        canonical_entity_id,
        get_emotion_vector,
        load_bond,
    )

    layout = layout or resolve_layout()
    eid = canonical_entity_id(entity_id)
    if eid not in ('aria', 'vector', 'ledger', 'muse', 'sentry'):
        return {'ok': False, 'applied': False, 'events': [], 'reason': 'invalid_entity'}

    before = get_emotion_vector(eid, layout=layout)
    bond = load_bond(eid, target_id, layout=layout)
    events = classify_interpersonal_events(user_text)
    if not events:
        return {
            'ok': True,
            'applied': False,
            'events': [],
            'vector_before': before,
            'vector_after': before,
            'reason': 'no_interpersonal_event',
        }

    trust = _f(bond.get('trust'), 0.5)
    slow = max(0.20, 1.0 - 0.55 * trust)
    fast = 0.90 + 0.15 * (1.0 - 0.4 * trust)

    dh = dc = de = 0.0
    residue_impact = 0.0
    dim_deltas: dict[str, float] = {}

    for ev in events:
        et = ev['event_type']
        inten = _f(ev.get('intensity'), 0.5)
        if et == 'user_hostile':
            dh -= 0.08 * inten * fast
            dc -= 0.04 * inten * slow
            de -= 0.03 * inten
            residue_impact -= 0.12 * inten * fast
            dim_deltas['anger'] = dim_deltas.get('anger', 0) + 0.12 * inten
            dim_deltas['stress'] = dim_deltas.get('stress', 0) + 0.10 * inten
            dim_deltas['joy'] = dim_deltas.get('joy', 0) - 0.08 * inten
            dim_deltas['attachment'] = dim_deltas.get('attachment', 0) - 0.03 * inten * slow
        elif et == 'user_critique':
            dh -= 0.04 * inten * fast
            dc -= 0.02 * inten
            residue_impact -= 0.05 * inten
            dim_deltas['frustration'] = dim_deltas.get('frustration', 0) + 0.08 * inten
            dim_deltas['pride'] = dim_deltas.get('pride', 0) - 0.04 * inten
        elif et == 'user_praise':
            dh += 0.07 * inten * fast
            dc += 0.04 * inten
            de += 0.03 * inten
            residue_impact += 0.08 * inten
            dim_deltas['joy'] = dim_deltas.get('joy', 0) + 0.10 * inten
            dim_deltas['pride'] = dim_deltas.get('pride', 0) + 0.08 * inten
            dim_deltas['attachment'] = dim_deltas.get('attachment', 0) + 0.04 * inten
        elif et == 'user_apology':
            dh += 0.05 * inten * (0.45 + 0.25 * trust)
            residue_impact += 0.06 * inten
            dim_deltas['anger'] = dim_deltas.get('anger', 0) - 0.06 * inten
            dim_deltas['stress'] = dim_deltas.get('stress', 0) - 0.05 * inten

    updated = apply_formula4_update(
        before['happiness'], before['confidence'], before['energy'],
        dh=dh, dc=dc, de=de,
    )
    new_residue = apply_formula7_residue(_f(before.get('residue'), 0.0), residue_impact)

    # Persist into Expansion EmotionStore dimensions
    try:
        from expansion.emotion_store import EmotionStore
        store = EmotionStore(layout)
        state = store.get_or_create(eid)
        for k, delta in dim_deltas.items():
            if k in state.dimensions:
                state.dimensions[k] = max(0.0, min(1.0, float(state.dimensions[k]) + delta))
        # Map formula4 vector hints into joy/confidence/stress
        state.dimensions['joy'] = max(0.0, min(1.0, 0.7 * state.dimensions.get('joy', 0.35)
                                               + 0.3 * updated['happiness']))
        state.dimensions['confidence'] = updated['confidence']
        state.dimensions['stress'] = max(0.0, min(1.0, state.dimensions.get('stress', 0.15)
                                                  + max(0.0, -new_residue) * 0.2))
        state.updated_at = time.time()
        state.last_event_at = time.time()
        store.save(state.clamp())
    except Exception:
        pass

    # Residue sidecar (owner-local)
    try:
        path = layout.user_data_root / 'emotion_residue' / f'{eid}.json'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            __import__('json').dumps({'residue': new_residue, 'updated_at': time.time()}, indent=2)
            + '\n',
            encoding='utf-8',
        )
    except Exception:
        pass

    # Relationship nudge
    try:
        from expansion.relationship_store import RelationshipStore
        rs = RelationshipStore(layout)
        rel = rs.get_or_create(eid, target_id)
        dims = dict(rel.dimensions or {})
        if any(e['event_type'] == 'user_hostile' for e in events):
            dims['trust'] = max(0.0, _f(dims.get('trust'), 0.5) - 0.04 * slow)
            dims['affinity'] = max(0.0, _f(dims.get('affinity'), 0.5) - 0.03 * slow)
        if any(e['event_type'] == 'user_praise' for e in events):
            dims['trust'] = min(1.0, _f(dims.get('trust'), 0.5) + 0.03)
            dims['affinity'] = min(1.0, _f(dims.get('affinity'), 0.5) + 0.04)
            dims['attachment'] = min(1.0, _f(dims.get('attachment'), 0.5) + 0.02)
        rel.dimensions = dims
        rs.save(rel)
    except Exception:
        pass

    after = get_emotion_vector(eid, layout=layout)
    return {
        'ok': True,
        'applied': True,
        'events': events,
        'vector_before': before,
        'vector_after': after,
        'reason': 'applied',
    }


def build_dual_affect_prompt_block(
    entity_id: str,
    *,
    layout: Optional[StateLayout] = None,
    recent_events: list | None = None,
) -> str:
    from expansion.continuity.emotion_bridge import (
        canonical_entity_id,
        get_emotion_vector,
        load_bond,
    )

    layout = layout or resolve_layout()
    eid = canonical_entity_id(entity_id)
    if not eid:
        return ''
    vec = get_emotion_vector(eid, layout=layout)
    bond = load_bond(eid, layout=layout)

    trust = _f(bond.get('trust'), 0.5)
    affection = _f(bond.get('affection'), 0.5)
    attachment = _f(bond.get('attachment'), 0.5)
    residue = bond.get('emotional_residue') if isinstance(bond.get('emotional_residue'), dict) else {}
    hurt = _f(residue.get('hurt'), max(0.0, -_f(vec.get('residue'), 0.0)))
    warmth = _f(residue.get('warmth_surge'), max(0.0, _f(vec.get('residue'), 0.0)))

    stress = max(0.0, 1.0 - _f(vec.get('happiness'), 0.55))
    anger = max(0.0, -_f(vec.get('residue'), 0.0))
    joy = _f(vec.get('happiness'), 0.55)
    short_hot = max(anger, hurt, stress * 0.85)

    lines = [
        '[AFFECT — LONG-TERM vs SHORT-TERM]',
        'LONG-TERM RELATIONSHIP (stable bond — do not erase because of one turn):',
        f'- trust: {_bond_word(trust)}',
        f'- affection: {_bond_word(affection)}',
        f'- attachment: {_bond_word(attachment)}',
        'CURRENT SHORT-TERM AFFECT (present tense — must color this reply):',
        f'- mood: {vec.get("mood")} (formula8={vec.get("formula8_score")})',
        f'- irritation/heat: {_level_word(short_hot)}',
        f'- hurt: {_level_word(hurt, low=0.12, mid=0.28, high=0.45)}',
        f'- pleasure/warmth: {_level_word(max(joy, warmth))}',
        f'- energy: {_level_word(_f(vec.get("energy"), 0.6))}',
        f'- confidence: {_level_word(_f(vec.get("confidence"), 0.55))}',
    ]

    praise_turn = any(
        isinstance(ev, dict) and ev.get('event_type') == 'user_praise'
        for ev in (recent_events or [])
    )
    if praise_turn and short_hot < 0.42:
        lines.append(
            'EXPRESSION RULE: They praised you. Let it land — warm, briefly pleased, '
            'in character. No receipt language ("noted", "logged").'
        )
    elif short_hot >= 0.28 or hurt >= 0.18:
        lines.append(
            'EXPRESSION RULE: Bond remains. Present feeling is irritated, hurt, or tense. '
            'Do not fake cheerfulness. Stay competent; color tone honestly.'
        )
    else:
        lines.append(
            'EXPRESSION RULE: Speak from present mood without dumping percentages or telemetry.'
        )
    return '\n'.join(lines) + '\n'
