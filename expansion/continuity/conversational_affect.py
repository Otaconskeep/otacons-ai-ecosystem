# -*- coding: utf-8 -*-
"""Conversational affect — user message → Formula 4/5/7 mutation + dual-affect prompt.

Clean-room Keep-parity for public Expansion Premium agents only.
Applies once per turn (call from chat_learning.before_reply — not from assemble_context).
"""
from __future__ import annotations

import re
import time
from typing import Any, Optional

from expansion.state_layout import StateLayout, resolve_layout

_HOSTILE = re.compile(
    r'\b(?:you(?:\'re| are) (?:useless|lazy|stupid|dumb|garbage|worthless)|'
    r'shut up|i hate you|you suck|worst|idiot|not a good job|being lazy|'
    r'this is garbage|you failed|absolute garbage)\b',
    re.I,
)
_PRAISE = re.compile(
    r'\b(?:thank(?:s| you)|good job|well done|proud|love (?:you|that|working)|'
    r'amazing|brilliant|perfect|appreciate|great work|nice work|awesome|'
    r'excellent|you(?:\'re| are) (?:great|the best|helpful))\b',
    re.I,
)
_CRITIQUE = re.compile(
    r'\b(?:that(?:\'s| is) wrong|incorrect|fix (?:that|this)|you messed up|'
    r'not what i (?:said|meant)|do better|try again|missed the point|'
    r'that failed|this failed|not good enough)\b',
    re.I,
)
_APOLOGY = re.compile(
    r'\b(?:i(?:\'m| am) sorry|i apologize|forgive me|my bad)\b',
    re.I,
)
_GRATITUDE = re.compile(
    r'\b(?:thanks|thank you|grateful|appreciate (?:it|you|that))\b',
    re.I,
)

# Turn-local de-dupe so before_reply + accidental second call don't double-hit
_applied_keys: dict[str, float] = {}
_DEDUP_TTL_SEC = 2.5


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
    elif _GRATITUDE.search(msg):
        out.append({'event_type': 'user_gratitude', 'intensity': 0.55})
    if _APOLOGY.search(msg):
        out.append({'event_type': 'user_apology', 'intensity': 0.60})
    return out


def is_praise_duty_boilerplate(text: str) -> bool:
    """Detect hollow praise-duty loops (Keep-parity scrub helper)."""
    t = (text or '').lower()
    markers = (
        'it is my duty', 'i am honored to serve', 'as your loyal',
        'always at your service', 'my purpose is to serve',
        'pleasure to be of service',
    )
    return any(m in t for m in markers)


def build_praise_language_directive(agent_id: str = '') -> str:
    return (
        '[Praise language] If the operator compliments you, accept it briefly in character — '
        'no duty speeches, no telemetry dumps, no "as an AI" hedges.'
    )


def apply_user_message_events(
    entity_id: str,
    user_text: str,
    *,
    layout: Optional[StateLayout] = None,
    target_id: str = 'user_primary',
    force: bool = False,
) -> dict:
    """Mutate StateEngine (F4/7/8) + RelationshipEngine (F5). Never raises."""
    from expansion.continuity.emotion_bridge import (
        canonical_entity_id,
        get_emotion_vector,
        load_bond,
    )
    from expansion.continuity.state_engine import StateEngine
    from expansion.continuity.relationship import RelationshipEngine
    from expansion.continuity.memory_engine import MemoryEngine

    layout = layout or resolve_layout()
    eid = canonical_entity_id(entity_id)
    if eid not in ('aria', 'vector', 'ledger', 'muse', 'sentry'):
        return {'ok': False, 'applied': False, 'events': [], 'reason': 'invalid_entity'}

    # De-dupe same entity+message within a short window (fixes double-apply)
    dedupe_key = f'{eid}::{hash((user_text or "")[:240])}'
    now = time.time()
    if not force:
        last = _applied_keys.get(dedupe_key, 0.0)
        if now - last < _DEDUP_TTL_SEC:
            before = get_emotion_vector(eid, layout=layout)
            return {
                'ok': True,
                'applied': False,
                'events': [],
                'vector_before': before,
                'vector_after': before,
                'reason': 'deduped_same_turn',
            }
        # prune old
        dead = [k for k, ts in _applied_keys.items() if now - ts > 30]
        for k in dead:
            _applied_keys.pop(k, None)

    before = get_emotion_vector(eid, layout=layout)
    bond = load_bond(eid, target_id, layout=layout)
    events = classify_interpersonal_events(user_text)

    # Always tick Formula 5 operator_ask + Formula 9 interaction counter
    subjective = bool(events) or any(
        w in (user_text or '').lower()
        for w in ('feel', 'love', 'hate', 'lonely', 'proud', 'sorry', 'miss')
    )
    try:
        RelationshipEngine.update_on_event(
            eid, target_id,
            'operator_ask_subjective' if subjective else 'operator_ask',
            notes='premium_chat',
            layout=layout,
        )
        RelationshipEngine.sync_dim_store(eid, target_id, layout=layout)
    except Exception:
        pass
    try:
        MemoryEngine.record_interaction(eid, layout=layout)
    except Exception:
        pass

    # Co-mention Formula 5 updates between public agents
    try:
        for other in RelationshipEngine.mentioned_agents_in_message(user_text or ''):
            if other == eid:
                continue
            RelationshipEngine.update_on_event(
                eid, other, 'social_mention_positive', notes='co_mention', layout=layout,
            )
    except Exception:
        pass

    if not events:
        after = get_emotion_vector(eid, layout=layout)
        _applied_keys[dedupe_key] = now
        return {
            'ok': True,
            'applied': True,
            'events': [{'event_type': 'operator_ask', 'intensity': 0.3}],
            'vector_before': before,
            'vector_after': after,
            'reason': 'operator_ask_only',
        }

    trust = _f(bond.get('trust'), 0.5)
    slow = max(0.20, 1.0 - 0.55 * trust)
    fast = 0.90 + 0.15 * (1.0 - 0.4 * trust)

    # Map interpersonal events through StateEngine event table (canonical F4/7)
    event_map = {
        'user_hostile': 'user_hostile',
        'user_critique': 'user_critique',
        'user_praise': 'user_praise',
        'user_gratitude': 'user_gratitude',
        'user_apology': 'user_apology',
    }
    for ev in events:
        et = event_map.get(ev['event_type'], ev['event_type'])
        try:
            StateEngine.update_from_event(
                eid, et,
                {'intensity': _f(ev.get('intensity'), 0.5), 'trust': trust, 'slow': slow, 'fast': fast},
                layout=layout,
            )
        except Exception:
            pass
        try:
            RelationshipEngine.update_on_event(
                eid, target_id, et, notes='conversational_affect', layout=layout,
            )
            RelationshipEngine.sync_dim_store(eid, target_id, layout=layout)
        except Exception:
            pass

    # Soft mirror into EmotionStore dims for UI (does not own Formula vector)
    try:
        from expansion.emotion_store import EmotionStore
        store = EmotionStore(layout)
        state = store.get_or_create(eid)
        after_vec = get_emotion_vector(eid, layout=layout)
        state.dimensions['joy'] = float(after_vec.get('happiness', 0.55))
        state.dimensions['confidence'] = float(after_vec.get('confidence', 0.55))
        state.dimensions['satisfaction'] = max(
            0.0, min(1.0, float(after_vec.get('happiness', 0.55)) * 0.9),
        )
        stress = max(0.0, -float(after_vec.get('residue', 0.0))) * 0.5
        state.dimensions['stress'] = max(0.0, min(1.0, 0.15 + stress))
        state.updated_at = time.time()
        state.last_event_at = time.time()
        store.save(state.clamp())
    except Exception:
        pass

    # Reflect significant interpersonal hits into Formula 9 memory
    try:
        for ev in events:
            if ev['event_type'] in ('user_hostile', 'user_praise', 'user_apology'):
                sentiment = 'negative' if 'hostile' in ev['event_type'] else 'positive'
                MemoryEngine.write_reflection(
                    eid,
                    trigger=ev['event_type'],
                    note=f'Operator interaction marked {ev["event_type"]} (intensity={ev.get("intensity")}).',
                    emotional_weight=sentiment,
                    layout=layout,
                )
    except Exception:
        pass

    after = get_emotion_vector(eid, layout=layout)
    _applied_keys[dedupe_key] = now
    return {
        'ok': True,
        'applied': True,
        'events': events,
        'vector_before': before,
        'vector_after': after,
        'reason': 'applied',
        'operator_rel_level': RelationshipEngine.operator_rel_level(eid, layout=layout),
    }


def build_dual_affect_prompt_block(
    entity_id: str,
    *,
    layout: Optional[StateLayout] = None,
) -> str:
    from expansion.continuity.emotion_bridge import get_emotion_vector, load_bond
    from expansion.continuity.state_engine import StateEngine
    from expansion.continuity.relationship import RelationshipEngine

    layout = layout or resolve_layout()
    vec = get_emotion_vector(entity_id, layout=layout)
    bond = load_bond(entity_id, layout=layout)
    h = _f(vec.get('happiness'), 0.55)
    c = _f(vec.get('confidence'), 0.55)
    e = _f(vec.get('energy'), 0.60)
    r = _f(vec.get('residue'), 0.0)
    trust = _f(bond.get('trust'), 0.5)
    aff = _f(bond.get('affection'), 0.5)
    level = bond.get('operator_rel_level') or RelationshipEngine.operator_rel_level(
        entity_id, layout=layout,
    )
    state_line = StateEngine.summary_for_prompt(entity_id, layout=layout)
    rel_line = RelationshipEngine.relationship_summary_for_prompt(entity_id, layout=layout)

    long_term = (
        f'LONG-TERM bond with operator: trust={_bond_word(trust)}, '
        f'affection={_bond_word(aff)}, posture={level}.'
    )
    short_term = (
        f'SHORT-TERM affect: mood={vec.get("mood")}, happiness={_level_word(h)}, '
        f'confidence={_level_word(c)}, energy={_level_word(e)}, '
        f'residue={_level_word(abs(r))} ({"warm" if r >= 0 else "raw"}).'
    )
    parts = [
        '[Dual affect — feel both; do not recite numbers]',
        long_term,
        short_term,
        state_line,
        build_praise_language_directive(entity_id),
    ]
    if rel_line:
        parts.append(rel_line)
    return '\n'.join(parts)
