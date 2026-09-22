# -*- coding: utf-8 -*-
"""Hermes behavior pipeline — full Premium turn (pre-LLM decisions + commit).

Pipeline:
  user input
  → intent classification
  → continuity retrieval (F9)
  → affect classify
  → StateEngine (F4/7/8)
  → RelationshipEngine (F5)
  → conversational affect / dual block
  → persona state + behavioral policy
  → (LLM generation happens outside)
  → Hermes final render + safety scrub
  → state commit already done pre-LLM; post-commit reflections/prefs

Deterministic behavioral policy is produced BEFORE generation.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Optional

from expansion.state_layout import StateLayout, resolve_layout
from expansion.continuity.health import LayerGuard, record_failure, record_ok, snapshot as health_snapshot
from expansion.hermes.behavioral_policy import (
    BehavioralPolicy,
    build_behavioral_policy,
    classify_behavioral_intent,
    policy_violations,
    resolve_agent_id,
)

_log = logging.getLogger('expansion.hermes.pipeline')


class HermesTurnResult(dict):
    """Dict-like result with required keys for differential harness."""

    @property
    def policy(self) -> dict:
        return self.get('behavioral_policy') or {}


def run_pre_generation(
    agent_id: str,
    user_message: str,
    *,
    layout: Optional[StateLayout] = None,
    user_id: str = 'user_primary',
) -> HermesTurnResult:
    """Execute Hermes continuity + policy BEFORE LLM. Returns sanitized internals."""
    layout = layout or resolve_layout()
    eid = resolve_agent_id(agent_id)
    t0 = time.monotonic()
    out: HermesTurnResult = HermesTurnResult({
        'ok': True,
        'agent_id': eid,
        'user_id': user_id,
        'user_message_len': len(user_message or ''),
        'layers_failed': [],
        'behavioral_policy': {},
        'intent': 'general',
        'emotion_before': {},
        'emotion_after': {},
        'relationship_before': {},
        'relationship_after': {},
        'formula9_memories': [],
        'affect_events': [],
        'state_summary': '',
        'relationship_summary': '',
        'dual_affect_block': '',
        'policy_prompt_block': '',
        'preferences_block': '',
        'persona_packet': {},
        'elapsed_ms': 0.0,
        'privacy': {'no_private_keep_data': True, 'synthetic_ok': True},
    })

    # 1) Intent
    intent = classify_behavioral_intent(user_message)
    out['intent'] = intent

    # 2) Snapshots before
    emotion_before = {}
    rel_before = {}
    with LayerGuard('state_engine', detail='get_before') as g:
        from expansion.continuity.emotion_bridge import get_emotion_vector
        from expansion.continuity.state_engine import StateEngine
        emotion_before = get_emotion_vector(eid, layout=layout)
        out['emotion_before'] = {
            k: emotion_before.get(k)
            for k in ('mood', 'happiness', 'confidence', 'energy', 'residue', 'formula8_score')
        }
        out['state_summary'] = StateEngine.summary_for_prompt(eid, layout=layout)
    if g.error:
        out['layers_failed'].append('state_engine')

    with LayerGuard('relationship_engine', detail='get_before') as g:
        from expansion.continuity.relationship import RelationshipEngine
        RelationshipEngine.ensure_seeded(layout=layout)
        rel_before = {
            'ally': RelationshipEngine.strength(eid, user_id, 'ally', layout=layout),
            'colleague': RelationshipEngine.strength(eid, user_id, 'colleague', layout=layout),
            'operator_rel_level': RelationshipEngine.operator_rel_level(eid, layout=layout),
        }
        out['relationship_before'] = rel_before
        out['relationship_summary'] = RelationshipEngine.relationship_summary_for_prompt(
            eid, layout=layout,
        )
    if g.error:
        out['layers_failed'].append('relationship_engine')

    # 3) Affect + State + Relationship mutations (single apply)
    affect = {}
    with LayerGuard('affect_engine', detail='apply_user_message_events') as g:
        from expansion.continuity.conversational_affect import apply_user_message_events
        affect = apply_user_message_events(
            eid, user_message, layout=layout, target_id=user_id, force=True,
        )
        out['affect_events'] = [
            (e.get('event_type') if isinstance(e, dict) else e)
            for e in (affect.get('events') or [])
        ]
    if g.error:
        out['layers_failed'].append('affect_engine')
        out['ok'] = False

    # 4) Formula 9 retrieval
    with LayerGuard('memory_engine', detail='formula9') as g:
        from expansion.continuity.memory_engine import MemoryEngine
        rows = MemoryEngine.retrieve_relevant_memory(
            eid, user_message or '', top_k=5, layout=layout,
        )
        out['formula9_memories'] = [
            {
                'score': r.get('_formula9_score'),
                'source': r.get('_source'),
                'note_len': len((r.get('note') or r.get('text') or '')),
                # content fingerprint only — not private Keep text
                'note_hash': hex(hash((r.get('note') or r.get('text') or '')[:120]) & 0xffffffff),
            }
            for r in rows
        ]
        MemoryEngine.record_interaction(eid, layout=layout)
    if g.error:
        out['layers_failed'].append('memory_engine')

    # 5) Preferences learn
    with LayerGuard('preferences', detail='learn') as g:
        from expansion.continuity.preferences import PreferenceStore
        prefs = PreferenceStore(layout)
        learned = prefs.learn_from_message(eid, user_message or '')
        out['preferences_learned'] = learned
        out['preferences_block'] = prefs.prompt_block(eid, user_id)
    if g.error:
        out['layers_failed'].append('preferences')

    # 6) After snapshots
    with LayerGuard('state_engine', detail='get_after') as g:
        from expansion.continuity.emotion_bridge import get_emotion_vector, load_bond
        from expansion.continuity.state_engine import StateEngine
        emotion_after = get_emotion_vector(eid, layout=layout)
        out['emotion_after'] = {
            k: emotion_after.get(k)
            for k in ('mood', 'happiness', 'confidence', 'energy', 'residue', 'formula8_score')
        }
        out['emotion_delta'] = {
            k: round(float(out['emotion_after'].get(k) or 0) - float(out['emotion_before'].get(k) or 0), 4)
            for k in ('happiness', 'confidence', 'energy', 'residue')
        }
        bond = load_bond(eid, user_id, layout=layout)
        out['bond'] = {
            'trust': bond.get('trust'),
            'affection': bond.get('affection'),
            'bond_level': bond.get('bond_level'),
            'operator_rel_level': bond.get('operator_rel_level'),
            'placeholder': bool(bond.get('_placeholder')),
        }
        out['state_summary'] = StateEngine.summary_for_prompt(eid, layout=layout)
    if g.error:
        out['layers_failed'].append('state_engine')

    with LayerGuard('relationship_engine', detail='get_after') as g:
        from expansion.continuity.relationship import RelationshipEngine
        rel_after = {
            'ally': RelationshipEngine.strength(eid, user_id, 'ally', layout=layout),
            'colleague': RelationshipEngine.strength(eid, user_id, 'colleague', layout=layout),
            'operator_rel_level': RelationshipEngine.operator_rel_level(eid, layout=layout),
        }
        out['relationship_after'] = rel_after
        out['relationship_delta'] = {
            'ally': round(rel_after['ally'] - float(rel_before.get('ally') or 0.5), 4),
            'colleague': round(rel_after['colleague'] - float(rel_before.get('colleague') or 0.5), 4),
        }
        out['relationship_summary'] = RelationshipEngine.relationship_summary_for_prompt(
            eid, layout=layout,
        )
    if g.error:
        out['layers_failed'].append('relationship_engine')

    # 7) Dual affect + behavioral policy (deterministic)
    with LayerGuard('hermes', detail='behavioral_policy') as g:
        from expansion.continuity.conversational_affect import build_dual_affect_prompt_block
        dual = build_dual_affect_prompt_block(eid, layout=layout)
        out['dual_affect_block'] = dual
        policy = build_behavioral_policy(
            user_message,
            agent_id=eid,
            emotion_vector=out.get('emotion_after') or emotion_before,
            bond=out.get('bond'),
            affect_events=out.get('affect_events'),
            operator_rel_level=(out.get('relationship_after') or {}).get('operator_rel_level', 'neutral'),
        )
        # Apply verbosity preference if learned
        try:
            from expansion.continuity.preferences import PreferenceStore
            v = PreferenceStore(layout).get_user_prefs(user_id).get('verbosity')
            if v in ('short', 'medium', 'detailed'):
                policy.verbosity = v
        except Exception as exc:
            record_failure('preferences', exc, detail='verbosity_override')
        out['behavioral_policy'] = policy.to_dict()
        out['policy_prompt_block'] = policy.to_prompt_block()
    if g.error:
        out['layers_failed'].append('hermes')
        out['ok'] = False

    # 8) Persona packet (Hermes)
    with LayerGuard('hermes', detail='persona_packet') as g:
        from expansion.hermes.personality_runtime import build_personality_runtime_packet
        packet = build_personality_runtime_packet(
            eid, user_message, layout=layout,
        )
        # Sanitize packet for harness — drop raw user message text from export
        safe_packet = {
            'schema': packet.get('schema'),
            'agent_id': packet.get('agent_id'),
            'intent_class': packet.get('intent_class'),
            'formula_catalog_keys': packet.get('formula_catalog_keys'),
            'privacy': packet.get('privacy'),
            'emotion_vector': {
                k: (packet.get('emotion_vector') or {}).get(k)
                for k in ('mood', 'happiness', 'confidence', 'energy', 'residue', 'formula8_score')
            },
            'state_summary': packet.get('state_summary'),
            'relationship_summary': packet.get('relationship_summary'),
            'formula9_count': len(packet.get('formula9_memories') or []),
        }
        out['persona_packet'] = safe_packet
    if g.error:
        out['layers_failed'].append('hermes')

    out['elapsed_ms'] = round((time.monotonic() - t0) * 1000, 1)
    out['health'] = health_snapshot()
    if out['layers_failed']:
        out['ok'] = False
        _log.warning(
            'hermes_pre_generation_degraded agent=%s failed=%s',
            eid, out['layers_failed'],
        )
    else:
        record_ok('hermes', detail='pre_generation')
    return out


def assemble_generation_context(
    pre: HermesTurnResult | dict,
    *,
    base_system_prompt: str = '',
) -> str:
    """Merge Hermes policy + continuity blocks into the system prompt."""
    parts = [base_system_prompt.rstrip()] if base_system_prompt else []
    for key in (
        'policy_prompt_block', 'dual_affect_block', 'state_summary',
        'relationship_summary', 'preferences_block',
    ):
        block = (pre or {}).get(key) or ''
        if block:
            parts.append(block if block.endswith('\n') else block + '\n')
    f9 = (pre or {}).get('formula9_memories') or []
    if f9:
        parts.append('[Formula 9 memory hits — use if relevant; do not invent extras]')
        for row in f9[:5]:
            parts.append(f"- score={row.get('score')} source={row.get('source')}")
        parts.append('')
    return '\n'.join(parts).strip() + '\n'


def run_post_generation(
    agent_id: str,
    user_message: str,
    candidate_text: str,
    pre: HermesTurnResult | dict,
    *,
    layout: Optional[StateLayout] = None,
) -> dict:
    """Final Hermes render + policy scrub + optional reflection commit."""
    layout = layout or resolve_layout()
    eid = resolve_agent_id(agent_id)
    policy_dict = (pre or {}).get('behavioral_policy') or {}
    policy = BehavioralPolicy(**{
        k: policy_dict[k] for k in BehavioralPolicy.__dataclass_fields__
        if k in policy_dict
    }) if policy_dict else build_behavioral_policy(user_message, agent_id=eid)

    text = candidate_text or ''
    source = 'candidate'
    with LayerGuard('final_render', detail='hermes_scrub') as g:
        from expansion.hermes.personality_runtime import (
            apply_final_persona_safety_scrub,
            local_persona_safe_fallback,
            render_persona_text_via_hermes,
        )
        rendered = render_persona_text_via_hermes(
            eid, user_message, candidate_text=text, layout=layout,
        )
        if len((text or '').split()) >= 8:
            scrubbed = apply_final_persona_safety_scrub(
                text, eid, policy.intent,
            )
            if scrubbed is None:
                text = local_persona_safe_fallback(
                    eid, user_message, 'scrub_reject', layout=layout,
                )
                source = 'fallback_after_scrub'
            else:
                text = scrubbed
                source = 'scrubbed_candidate'
        elif rendered.get('ok') and rendered.get('text'):
            text = rendered['text']
            source = rendered.get('source') or 'hermes_render'

        # Policy violation repair (deterministic stubs, not LLM)
        violations = policy_violations(text, policy)
        if 'missing_failure_ack' in violations and policy.must_acknowledge_failure:
            text = (
                "You're right — I missed it. "
                + text.lstrip()
            )
            violations = policy_violations(text, policy)
        if 'missing_action_offer' in violations and policy.must_offer_action:
            text = (
                text.rstrip('.')
                + ". Next: I'll isolate the failure point and propose a fix path."
            )
            violations = policy_violations(text, policy)
        try:
            from expansion.behavior_spine import scrub_robotic_delivery
            text = scrub_robotic_delivery(text)
        except Exception as exc:
            record_failure('final_render', exc, detail='scrub_robotic')
    if g.error:
        record_failure('final_render', g.error.get('error') or 'unknown')

    # Persistence commit marker
    with LayerGuard('persistence', detail='post_commit') as g:
        from expansion.continuity.memory_engine import MemoryEngine
        if policy.must_acknowledge_failure:
            MemoryEngine.write_reflection(
                eid,
                trigger='corrective_work',
                note='USER_PRIMARY flagged a miss; corrective work mode engaged.',
                emotional_weight='negative',
                layout=layout,
            )
        elif policy.intent == 'praise':
            MemoryEngine.write_reflection(
                eid,
                trigger='user_praise',
                note='USER_PRIMARY offered praise; brief accept path.',
                emotional_weight='positive',
                layout=layout,
            )
    failed = list((pre or {}).get('layers_failed') or [])
    if g.error:
        failed.append('persistence')

    return {
        'ok': not bool(g.error),
        'text': text,
        'source': source,
        'policy_violations': policy_violations(text, policy),
        'behavioral_policy': policy.to_dict(),
        'layers_failed': failed,
        'health': health_snapshot(),
        'privacy': {'no_private_keep_data': True},
    }


def run_full_turn_without_llm(
    agent_id: str,
    user_message: str,
    *,
    layout: Optional[StateLayout] = None,
    stub_response: str = '',
) -> dict:
    """Pipeline turn using stub prose — for differential / model-independence tests."""
    pre = run_pre_generation(agent_id, user_message, layout=layout)
    policy = pre.get('behavioral_policy') or {}
    if not stub_response:
        # Deterministic stub from policy (not an LLM)
        intent = policy.get('intent') or 'general'
        if intent == 'corrective_work':
            stub_response = (
                "You're right — I missed the obvious problem. "
                "Next I'll isolate the failure point and propose a concrete fix."
            )
        elif intent == 'praise':
            stub_response = "Appreciate that. Let's keep going."
        elif intent == 'hostility':
            stub_response = "That landed. Tell me the specific failure and I'll address it."
        elif intent == 'greeting':
            stub_response = "Hey — what are we working on?"
        elif intent in ('work_request', 'research', 'coding'):
            stub_response = (
                "Got it. Here's a first-pass plan: clarify the goal, list constraints, "
                "draft options, then ship one slice."
            )
        else:
            stub_response = "Understood. What's the next concrete step you want?"
    post = run_post_generation(
        agent_id, user_message, stub_response, pre, layout=layout,
    )
    return {
        'pre': pre,
        'post': post,
        'text': post.get('text'),
        'behavioral_policy': policy,
        'emotion_delta': pre.get('emotion_delta'),
        'relationship_delta': pre.get('relationship_delta'),
        'ok': bool(pre.get('ok')) and bool(post.get('ok')),
    }
