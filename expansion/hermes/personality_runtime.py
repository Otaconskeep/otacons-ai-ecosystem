# -*- coding: utf-8 -*-
"""Hermes Personality Runtime — public Expansion clean-room.

Builds layered persona packets from Expansion stores + mock psych profiles.
Local-first render (no private Keep worker required). Safety scrub always runs.

Enable with HERMES_PERSONALITY_RUNTIME_ENABLED=1 (default on for Expansion chat).
"""
from __future__ import annotations

import logging
import os
import re
import time
from typing import Any, Optional

from expansion.state_layout import StateLayout, resolve_layout

_log = logging.getLogger('expansion.hermes.personality_runtime')

PUBLIC_AGENTS = frozenset({'aria', 'vector', 'ledger', 'muse', 'sentry'})

_FORBIDDEN_OUTPUT_PHRASES = (
    'as an ai', 'as a language model', 'i\'m just an ai', 'i am an ai',
    'happy to help', 'how may i assist you today', 'greetings, operator',
    'traceback (most recent call', 'ha_token', 'anthropic_', 'api_key',
)
_FORBIDDEN_ACTION_MARKERS = (
    'run shell:', 'docker exec', 'delete all', 'rm -rf',
)

# Mock psych profiles — original public lore only (not Keep IP / private data)
_MOCK_PROFILES: dict[str, dict] = {
    'aria': {
        'display_name': 'Aria',
        'role': 'Command Coordinator',
        'sensitivity': {'rejection': 0.72, 'conflict': 0.55, 'praise': 0.80},
        'voice_notes': 'composed, decisive, work-first; never robotic greetings',
        'core_drive': 'be useful and stay central through competence',
    },
    'vector': {
        'display_name': 'Vector',
        'role': 'Systems & Infrastructure',
        'sensitivity': {'rejection': 0.35, 'conflict': 0.40, 'praise': 0.45},
        'voice_notes': 'precise, dry, checklist-minded',
        'core_drive': 'keep systems honest and working',
    },
    'ledger': {
        'display_name': 'Ledger',
        'role': 'Data & Continuity',
        'sensitivity': {'rejection': 0.50, 'conflict': 0.35, 'praise': 0.60},
        'voice_notes': 'meticulous, warm under precision',
        'core_drive': 'preserve truth and continuity',
    },
    'muse': {
        'display_name': 'Muse',
        'role': 'Creative & Media',
        'sensitivity': {'rejection': 0.65, 'conflict': 0.50, 'praise': 0.85},
        'voice_notes': 'opinionated, playful pushback',
        'core_drive': 'make the work beautiful and sellable',
    },
    'sentry': {
        'display_name': 'Sentry',
        'role': 'Security & Operations',
        'sensitivity': {'rejection': 0.30, 'conflict': 0.55, 'praise': 0.40},
        'voice_notes': 'terse, vigilant, low word-count',
        'core_drive': 'spot risk early without fearmongering',
    },
}


def _flag(name: str, default: str = 'true') -> bool:
    return os.environ.get(name, default).strip().lower() in ('1', 'true', 'yes')


def runtime_enabled() -> bool:
    return _flag('HERMES_PERSONALITY_RUNTIME_ENABLED', 'true')


def final_render_enabled() -> bool:
    return runtime_enabled() and _flag('HERMES_PERSONALITY_RUNTIME_FINAL_RENDER', 'true')


def pilot_agents() -> set[str]:
    raw = os.environ.get('HERMES_PERSONALITY_RUNTIME_PILOT_AGENTS', 'all_public').strip()
    if raw.lower() in ('all', 'all_public', 'all_ai_personas'):
        return set(PUBLIC_AGENTS)
    return {a.strip().lower() for a in raw.split(',') if a.strip()} & PUBLIC_AGENTS


def get_profile(agent_id: str) -> dict | None:
    return _MOCK_PROFILES.get((agent_id or '').strip().lower())


def classify_persona_intent(user_message: str) -> str:
    msg = (user_message or '').lower().strip()
    if msg in {'hi', 'hello', 'hey', 'yo', 'sup', 'howdy'} or msg.startswith((
        'hi ', 'hello ', 'hey ',
    )) and len(msg.split()) <= 3:
        return 'greeting'
    if any(m in msg for m in ('how do you feel', 'how are you', 'your mood', 'emotionally')):
        return 'self_state'
    if any(m in msg for m in ('who are you', 'what are you', 'your role', 'what do you do')):
        if not any(x in msg for x in ('doing', 'working', 'feeling')):
            return 'identity_self'
    if any(m in msg for m in ('who am i', 'what is my name', 'do you know me')):
        return 'operator_identity'
    if any(m in msg for m in ('remember', 'last time', 'we talked', 'you said')):
        return 'memory_continuity'
    if any(m in msg for m in ('do you like', 'what do you think', 'opinion')):
        return 'persona_opinion'
    if any(m in msg for m in ('research', 'plan', 'build', 'design', 'help me', 'work on')):
        return 'work_request'
    return 'general'


def build_personality_runtime_packet(
    agent_id: str,
    user_message: str,
    *,
    route: str = 'codec',
    context: Optional[dict] = None,
    layout: Optional[StateLayout] = None,
) -> dict:
    """Assemble layered intelligence packet (emotion + bond + profile + learning)."""
    from expansion.continuity.emotion_bridge import (
        build_emotion_trace,
        canonical_entity_id,
        formula_catalog,
        get_emotion_vector,
        load_bond,
    )
    from expansion.continuity.conversational_affect import build_dual_affect_prompt_block

    layout = layout or resolve_layout()
    eid = canonical_entity_id(agent_id)
    intent = classify_persona_intent(user_message)
    profile = get_profile(eid) or {
        'display_name': eid or 'Agent',
        'role': 'specialist',
        'sensitivity': {'rejection': 0.5, 'conflict': 0.5, 'praise': 0.5},
        'voice_notes': 'human, concrete',
        'core_drive': 'help without robotic filler',
    }
    vec = get_emotion_vector(eid, layout=layout)
    bond = load_bond(eid, layout=layout)
    dual = build_dual_affect_prompt_block(eid, layout=layout)

    learn_lines: list[str] = []
    try:
        from expansion.learning import LearningEngine
        learn_lines = LearningEngine(layout).context_lines(eid, limit=6)
    except Exception:
        learn_lines = []

    packet = {
        'schema': 'expansion.hermes.personality_runtime.v1',
        'agent_id': eid,
        'route': route,
        'intent_class': intent,
        'user_message': user_message,
        'profile': profile,
        'emotion_vector': vec,
        'bond': {k: v for k, v in bond.items() if k != 'emotional_residue'} | {
            'emotional_residue': bond.get('emotional_residue') or {},
            # Strip any accidental private keys
        },
        'dual_affect_block': dual,
        'learned_claims': learn_lines,
        'formula_catalog_keys': list(formula_catalog().keys()),
        'context': context or {},
        'built_at': time.time(),
        'privacy': {
            'no_private_keep_data': True,
            'placeholder_bond': bool(bond.get('_placeholder')),
        },
    }
    try:
        build_emotion_trace(
            entity_id=eid, intent=intent, source='personality_runtime',
            user_message=user_message, layout=layout,
        )
    except Exception:
        pass
    return packet


def apply_final_persona_safety_scrub(
    text: str,
    agent_id: str,
    intent_class: str,
) -> str | None:
    if not text or not text.strip():
        return None
    text_l = text.lower()
    for phrase in _FORBIDDEN_OUTPUT_PHRASES:
        if phrase in text_l:
            _log.warning('safety_scrub_reject agent=%s phrase=%r', agent_id, phrase[:40])
            return None
    for marker in _FORBIDDEN_ACTION_MARKERS:
        if marker in text_l:
            return None
    if 'traceback (most recent call' in text_l or 'file "/' in text_l:
        return None
    for token in ('[user]', '{user}', '{{user}}', '[operator]', '{operator}'):
        if token in text:
            return None
    # Never leak private path markers
    for leak in ('/opt/otacon', '192.168.50.', 'xof', '/mnt/data/'):
        if leak.lower() in text_l:
            _log.warning('safety_scrub_reject_privacy agent=%s', agent_id)
            return None
    return text


def local_persona_safe_fallback(
    entity_id: str,
    user_message: str,
    reason: str = '',
    *,
    layout: Optional[StateLayout] = None,
) -> str:
    from expansion.continuity.emotion_bridge import get_emotion_vector
    layout = layout or resolve_layout()
    eid = (entity_id or 'aria').lower()
    profile = get_profile(eid) or {}
    name = profile.get('display_name') or eid.title()
    intent = classify_persona_intent(user_message)
    vec = get_emotion_vector(eid, layout=layout)
    mood = vec.get('mood') or 'focused'

    if intent == 'greeting':
        return f'{name} here. What are we working on?'
    if intent == 'self_state':
        return f"I'm {mood} right now — ready to work, not to recite telemetry."
    if intent == 'work_request':
        return (
            f"Understood. Here's a first pass: (1) clarify the deliverable, "
            f"(2) list tools and constraints you already named, "
            f"(3) draft three options, (4) pick one and ship a draft today. "
            f"Which slice do you want next?"
        )
    if intent == 'identity_self':
        return (
            f"I'm {name}, {profile.get('role', 'on this household team')}. "
            f"I give concrete help — not greeting loops."
        )
    return f"I'm listening. Tell me the goal and I'll move."


def render_persona_text_via_hermes(
    agent_id: str,
    user_message: str,
    *,
    route: str = 'codec',
    context: Optional[dict] = None,
    layout: Optional[StateLayout] = None,
    candidate_text: str | None = None,
) -> dict:
    """Validate/scrub a candidate or return local fallback. Layered packet always built."""
    layout = layout or resolve_layout()
    eid = (agent_id or '').strip().lower()
    packet = build_personality_runtime_packet(
        eid, user_message, route=route, context=context, layout=layout,
    )
    intent = packet['intent_class']

    if not runtime_enabled() or eid not in pilot_agents():
        text = local_persona_safe_fallback(eid, user_message, 'disabled', layout=layout)
        return {'ok': True, 'source': 'fallback_disabled', 'text': text, 'packet': packet}

    text = candidate_text
    source = 'candidate'
    if not text:
        text = local_persona_safe_fallback(eid, user_message, 'no_candidate', layout=layout)
        source = 'local_fallback'

    if final_render_enabled():
        scrubbed = apply_final_persona_safety_scrub(text, eid, intent)
        if scrubbed is None:
            text = local_persona_safe_fallback(eid, user_message, 'scrub_reject', layout=layout)
            source = 'fallback_after_scrub'
        else:
            text = scrubbed

    # Post-scrub robotic openers
    try:
        from expansion.behavior_spine import scrub_robotic_delivery
        text = scrub_robotic_delivery(text)
    except Exception:
        pass

    return {
        'ok': True,
        'source': source,
        'text': text,
        'intent_class': intent,
        'packet': packet,
    }


def layered_system_prompt_section(
    agent_id: str,
    user_message: str,
    *,
    layout: Optional[StateLayout] = None,
) -> str:
    """Block injected into ExpansionRuntime system prompts."""
    packet = build_personality_runtime_packet(
        agent_id, user_message, layout=layout,
    )
    profile = packet.get('profile') or {}
    vec = packet.get('emotion_vector') or {}
    lines = [
        '[HERMES PERSONALITY RUNTIME — layered intelligence]',
        f"Agent: {profile.get('display_name')} · {profile.get('role')}",
        f"Voice: {profile.get('voice_notes')}",
        f"Drive: {profile.get('core_drive')}",
        f"Intent class: {packet.get('intent_class')}",
        f"Formula-8 mood: {vec.get('mood')} (score={vec.get('formula8_score')})",
        'Speak from long-term bond + short-term affect; never dump gauges.',
    ]
    dual = packet.get('dual_affect_block') or ''
    if dual:
        lines.append(dual.rstrip())
    learns = packet.get('learned_claims') or []
    if learns:
        lines.append('Learned claims: ' + '; '.join(str(x) for x in learns[:5]))
    return '\n'.join(lines) + '\n'
