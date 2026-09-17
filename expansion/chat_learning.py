# -*- coding: utf-8 -*-
"""Chat-turn learning loop for Expansion agents (Keep parity shape).

Order matches private Keep codec:
  user message
  → classify intent
  → mutate emotion / relationships / learning / memory (before_reply)
  → assemble_context / LLM sees fresh state
  → after_reply writes episodic turn memory

Does not invent owner history. Does not import private Keep modules.
"""
from __future__ import annotations

import re
from typing import Optional

from expansion.events import new_event
from expansion.learning import LearningEngine, ingest_owner_message
from expansion.living_dossier import LivingDossierStore
from expansion.memory_bridge import ExpansionMemory, new_memory
from expansion.pipeline import LivingPipeline
from expansion.state_layout import StateLayout, resolve_layout

_REMEMBER = re.compile(
    r'^\s*(?:please\s+)?(?:remember|note|don\'t forget|do not forget)\s*(?:that\s+|this[:\s]+)?(.+)$',
    re.I | re.S,
)
_REMEMBER_ALT = re.compile(
    r'^\s*(?:you should know|from now on|always remember)\s*[:\-]?\s*(.+)$',
    re.I | re.S,
)
_CORRECT = re.compile(
    r'\b(?:that(?:\'s| is) wrong|you(?:\'re| are) wrong|incorrect|not what i (?:said|meant)|'
    r'i (?:said|meant|told you)|don\'t (?:say|do) that|stop (?:saying|doing)|'
    r'bad (?:answer|reply)|fix (?:that|this)|you messed up|'
    r'that hurt|that was (?:mean|harsh|cruel)|how dare you)\b',
    re.I,
)
_PRAISE = re.compile(
    r'\b(?:thank(?:s| you)|good job|well done|proud of you|you did great|'
    r'appreciate (?:you|it)|i love (?:you|that)|you\'re the best|amazing|brilliant|'
    r'nice work|perfect|love that)\b',
    re.I,
)
_PREFERENCE = re.compile(
    r'\b(?:prefer|always|never|from now on|please (?:be|keep|use)|'
    r'i (?:like|dislike|hate|want) (?:you to|when)|call me)\b',
    re.I,
)


def classify_chat_intent(message: str) -> str:
    """Return remember | praise | correct | preference | chat."""
    msg = (message or '').strip()
    if not msg:
        return 'chat'
    if extract_remember_fact(msg):
        return 'remember'
    if _CORRECT.search(msg):
        return 'correct'
    if _PRAISE.search(msg):
        return 'praise'
    if _PREFERENCE.search(msg):
        return 'preference'
    return 'chat'


def extract_remember_fact(message: str) -> Optional[str]:
    msg = (message or '').strip()
    if not msg:
        return None
    for pat in (_REMEMBER, _REMEMBER_ALT):
        m = pat.match(msg)
        if m:
            fact = (m.group(1) or '').strip().rstrip('.')
            if len(fact) >= 3:
                return fact[:500]
    return None


def _ack_remember(agent_id: str, fact: str) -> str:
    if agent_id == 'aria':
        return f'Noted. I will hold that: {fact}.'
    return f"I'll remember that: {fact}."


def before_reply(
    agent_id: str,
    user_message: str,
    *,
    layout: Optional[StateLayout] = None,
) -> dict:
    """Mutate continuity stores before prompt assembly. May intercept remember."""
    layout = layout or resolve_layout()
    layout.ensure_user_dirs()
    aid = (agent_id or '').strip().lower() or 'aria'
    msg = (user_message or '').strip()
    out: dict = {
        'intent': 'chat',
        'event_id': '',
        'intercept': False,
        'reply': '',
        'memory_id': '',
        'learning_observation_id': '',
        'emotion_updates': [],
        'relationship_updates': [],
        'journal_ids': [],
    }
    if not msg:
        return out

    intent = classify_chat_intent(msg)
    out['intent'] = intent
    pipe = LivingPipeline(layout)
    engine = LearningEngine(layout)
    mem = ExpansionMemory(layout)

    # Explicit remember — durable important memory + optional short-circuit reply
    if intent == 'remember':
        fact = extract_remember_fact(msg) or msg
        rec = mem.add(new_memory(
            aid, fact,
            kind='important',
            source='remember_command',
            importance=0.9,
            confidence=0.95,
            entities=('user_primary',),
        ))
        out['memory_id'] = rec.memory_id
        # Soft praise-adjacent bump so holding a fact feels relational
        ev = new_event(
            'agent.message',
            actor='user',
            subject=aid,
            payload={'text': msg, 'remember_fact': fact, 'memory_id': rec.memory_id},
        )
        applied = pipe.apply_event(ev, write_diary=False)
        out.update({
            'event_id': applied.get('event_id') or ev.event_id,
            'emotion_updates': applied.get('emotion_updates') or [],
            'relationship_updates': applied.get('relationship_updates') or [],
            'journal_ids': applied.get('journal_ids') or [],
            'learning_observation_id': applied.get('learning_observation_id') or '',
            'intercept': True,
            'reply': _ack_remember(aid, fact),
        })
        try:
            engine.observe(
                aid,
                f'operator asked me to remember: {fact}',
                learning_type='relationship',
                evidence_ids=[out['event_id'] or rec.memory_id],
                scope='private',
                actor=aid,
            )
        except Exception:
            pass
        return out

    event_type = {
        'praise': 'user.praised_agent',
        'correct': 'user.corrected_agent',
        'preference': 'agent.message',
        'chat': 'agent.message',
    }.get(intent, 'agent.message')

    ev = new_event(
        event_type,
        actor='user',
        subject=aid,
        payload={'text': msg, 'intent': intent},
    )
    # Diary on interpersonal turns; skip on plain chat noise to reduce churn
    write_diary = intent in ('praise', 'correct', 'preference')
    applied = pipe.apply_event(ev, write_diary=write_diary)
    out.update({
        'event_id': applied.get('event_id') or ev.event_id,
        'emotion_updates': applied.get('emotion_updates') or [],
        'relationship_updates': applied.get('relationship_updates') or [],
        'journal_ids': applied.get('journal_ids') or [],
        'learning_observation_id': applied.get('learning_observation_id') or '',
    })

    # Relationship / social learning beyond preference regex
    try:
        if intent == 'praise':
            obs = engine.observe(
                aid,
                f'operator expressed appreciation toward {aid}',
                learning_type='relationship',
                evidence_ids=[out['event_id']],
                scope='private',
                actor=aid,
            )
            out['learning_observation_id'] = out['learning_observation_id'] or obs.observation_id
            LivingDossierStore(layout).upsert_observation(
                aid,
                category='recent_social',
                value='felt appreciated by the operator',
                confidence=0.55,
                event_ids=(out['event_id'],),
                persistence='decaying',
            )
        elif intent == 'correct':
            obs = engine.observe(
                aid,
                f'operator corrected {aid}; watch tone and accuracy',
                learning_type='relationship',
                evidence_ids=[out['event_id']],
                scope='private',
                actor=aid,
            )
            out['learning_observation_id'] = out['learning_observation_id'] or obs.observation_id
            LivingDossierStore(layout).upsert_observation(
                aid,
                category='recent_frustration',
                value='operator correction landed; tighten accuracy',
                confidence=0.55,
                event_ids=(out['event_id'],),
                persistence='decaying',
            )
        elif intent == 'preference':
            # Pipeline already runs ingest_owner_message; add a private social note
            if not out.get('learning_observation_id'):
                obs = ingest_owner_message(
                    engine, text=msg, event_id=out['event_id'], actor='ledger',
                )
                if obs:
                    out['learning_observation_id'] = obs.observation_id
                else:
                    obs = engine.observe(
                        aid,
                        f'owner preference signal: {msg[:160]}',
                        learning_type='owner_preference',
                        evidence_ids=[out['event_id']],
                        scope='private',
                        actor=aid,
                    )
                    out['learning_observation_id'] = obs.observation_id
    except Exception:
        pass

    return out


def after_reply(
    agent_id: str,
    user_message: str,
    assistant_text: str,
    *,
    layout: Optional[StateLayout] = None,
    event_id: str = '',
    intent: str = 'chat',
) -> dict:
    """Write episodic turn memory after the assistant reply."""
    layout = layout or resolve_layout()
    layout.ensure_user_dirs()
    aid = (agent_id or '').strip().lower() or 'aria'
    user = (user_message or '').strip()
    reply = (assistant_text or '').strip()
    out = {'memory_id': '', 'reinforced': False}
    if not user or not reply:
        return out
    # Skip if before_reply already stored an important remember fact only
    if intent == 'remember':
        return out

    snippet_u = user if len(user) <= 220 else user[:217] + '…'
    snippet_a = reply if len(reply) <= 280 else reply[:277] + '…'
    importance = 0.55 if intent in ('praise', 'correct', 'preference') else 0.35
    try:
        mem = ExpansionMemory(layout)
        rec = mem.add(new_memory(
            aid,
            f'User: {snippet_u} / Me: {snippet_a}',
            kind='episodic',
            source='chat_turn',
            importance=importance,
            confidence=0.75,
            event_id=event_id or '',
            entities=('user_primary',),
        ))
        out['memory_id'] = rec.memory_id
    except Exception:
        return out

    # Reinforce matching relationship claims when praise lands again
    if intent == 'praise' and event_id:
        try:
            engine = LearningEngine(layout)
            for claim in engine.store.list_claims(
                agent_id=aid, scope='private', learning_type='relationship',
            ):
                if 'appreciation' in (claim.claim or '').lower() and claim.status == 'active':
                    engine.reinforce(claim.claim_id, event_id, actor=aid)
                    out['reinforced'] = True
                    break
        except Exception:
            pass
    return out
