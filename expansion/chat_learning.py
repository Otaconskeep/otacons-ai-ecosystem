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
from expansion.jobs import DOMAIN_ROUTING
from expansion.learning import LearningEngine, ingest_owner_message
from expansion.living_dossier import LivingDossierStore
from expansion.memory_bridge import ExpansionMemory, new_memory
from expansion.pipeline import LivingPipeline
from expansion.state_layout import StateLayout, resolve_layout

CANONICAL_AGENTS = ('aria', 'vector', 'ledger', 'muse', 'sentry')

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
_APOLOGY = re.compile(
    r'\b(?:i(?:\'m| am) sorry|i apologize|forgive me|sorry (?:for|about)|'
    r'my (?:bad|apologies)|i was (?:wrong|harsh|unfair))\b',
    re.I,
)
_INSULT = re.compile(
    r'\b(?:you(?:\'re| are) (?:useless|worthless|stupid|dumb|an idiot|pathetic)|'
    r'useless|shut up|i hate you|you suck|worst (?:agent|assistant)|'
    r'dumb (?:bot|ai)|idiot)\b',
    re.I,
)
_AGENT_ALT = '|'.join(CANONICAL_AGENTS)
_COMPARE = re.compile(
    rf'\b({_AGENT_ALT})\s+is\s+(?:smarter|better|faster|stronger|cooler|more\s+\w+)\s+than\s+(?:you|({_AGENT_ALT}))\b',
    re.I,
)
_COMPARE_YOU = re.compile(
    rf'\b(?:you(?:\'re| are)|you)\s+(?:smarter|better|worse|dumber)\s+than\s+({_AGENT_ALT})\b',
    re.I,
)
_TASK_NAMED = re.compile(
    rf'^\s*({_AGENT_ALT})\s*[,:]?\s+'
    r'(?:please\s+)?(?:handle|take care of|do|run|ship|fix|deploy|own|manage|work on)\s+(.+)$',
    re.I | re.S,
)
_TASK_HAVE = re.compile(
    rf'^\s*(?:please\s+)?(?:have|ask|tell)\s+({_AGENT_ALT})\s+to\s+(.+)$',
    re.I | re.S,
)
_TASK_GENERIC = re.compile(
    r'^\s*(?:please\s+)?(?:handle|ship|deploy|fix|release|take care of)\s+(.+)$',
    re.I | re.S,
)

_DOMAIN_HINTS = (
    ('security', 'security'),
    ('scan', 'security'),
    ('infra', 'infrastructure'),
    ('docker', 'infrastructure'),
    ('deploy', 'systems'),
    ('release', 'coordination'),
    ('research', 'research'),
    ('creative', 'creative'),
    ('video', 'media'),
    ('write', 'creative'),
)


def resolve_mentioned_agent(message: str) -> Optional[str]:
    low = (message or '').lower()
    for aid in CANONICAL_AGENTS:
        if re.search(rf'\b{aid}\b', low):
            return aid
    return None


def extract_comparison(message: str) -> Optional[dict]:
    """Return {favored_agent, rival_agent, subject_hint} or None."""
    msg = (message or '').strip()
    if not msg:
        return None
    m = _COMPARE.search(msg)
    if m:
        favored = m.group(1).lower()
        other = (m.group(2) or '').lower()
        return {
            'favored_agent': favored,
            'rival_agent': favored,
            'other_agent': other or '',
            'subject_hint': other or '',  # addressed "you" when other empty
        }
    m = _COMPARE_YOU.search(msg)
    if m:
        other = m.group(1).lower()
        low = msg.lower()
        favored_is_you = bool(re.search(r'\b(?:smarter|better)\s+than\b', low))
        worse = bool(re.search(r'\b(?:worse|dumber)\s+than\b', low))
        if worse:
            return {
                'favored_agent': other,
                'rival_agent': other,
                'other_agent': other,
                'subject_hint': '',
            }
        if favored_is_you:
            return {
                'favored_agent': '',  # filled with speaking agent later
                'rival_agent': other,
                'other_agent': other,
                'subject_hint': '',
            }
    return None


def extract_task_delegation(message: str, *, default_agent: str = 'aria') -> Optional[dict]:
    """Return {agent_id, request, domain} when the message authorizes a task."""
    msg = (message or '').strip()
    if not msg:
        return None
    agent = ''
    request = ''
    for pat in (_TASK_NAMED, _TASK_HAVE):
        m = pat.match(msg)
        if m:
            agent = m.group(1).lower()
            request = (m.group(2) or '').strip().rstrip('.')
            break
    if not agent:
        m = _TASK_GENERIC.match(msg)
        if m and not extract_comparison(msg):
            # Avoid treating "Muse is smarter..." as a task.
            agent = (default_agent or 'aria').lower()
            request = (m.group(1) or '').strip().rstrip('.')
    if not agent or len(request) < 3:
        return None
    if agent not in CANONICAL_AGENTS:
        return None
    domain = 'coordination'
    low = request.lower()
    for needle, dom in _DOMAIN_HINTS:
        if needle in low:
            domain = dom
            break
    # Named agent overrides routing when they own the domain; else use domain route
    # but keep the named assignee as coordinator intent via assigned_agent.
    return {
        'agent_id': agent,
        'request': request[:500],
        'domain': domain if domain in DOMAIN_ROUTING or domain == 'coordination' else 'coordination',
    }


def classify_chat_intent(message: str) -> str:
    """Return remember|praise|correct|preference|apology|insult|comparison|task|chat."""
    msg = (message or '').strip()
    if not msg:
        return 'chat'
    if extract_remember_fact(msg):
        return 'remember'
    if extract_task_delegation(msg):
        return 'task'
    if extract_comparison(msg):
        return 'comparison'
    if _APOLOGY.search(msg):
        return 'apology'
    if _INSULT.search(msg):
        return 'insult'
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


def _ack_task(agent_id: str, request: str, job_id: str) -> str:
    return (
        f'Queued for {agent_id}: {request} '
        f'(job {job_id}; status RUNNING — not marked complete until executed).'
    )


def before_reply(
    agent_id: str,
    user_message: str,
    *,
    layout: Optional[StateLayout] = None,
) -> dict:
    """Mutate continuity stores before prompt assembly. May intercept remember/task."""
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
        'job_id': '',
        'task': {},
    }
    if not msg:
        return out

    intent = classify_chat_intent(msg)
    out['intent'] = intent
    # Layered affect before prompt assembly (Hermes/emotion bridge path)
    try:
        from expansion.continuity.conversational_affect import apply_user_message_events
        affect = apply_user_message_events(aid, msg, layout=layout)
        out['affect'] = {
            'applied': bool(affect.get('applied')),
            'events': affect.get('events') or [],
        }
    except Exception:
        out['affect'] = {'applied': False, 'events': []}
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

    # Explicit task delegation — queue real work (no fake COMPLETE)
    if intent == 'task':
        task = extract_task_delegation(msg, default_agent=aid) or {}
        out['task'] = task
        assignee = task.get('agent_id') or aid
        request = task.get('request') or msg
        domain = task.get('domain') or 'coordination'
        job_out = pipe.create_and_run_job(
            request,
            domain=domain,
            simulate=False,
            queue_only=True,
            assigned_agent=assignee,
        )
        job = job_out.get('job')
        job_id = getattr(job, 'job_id', '') if job else ''
        ev = new_event(
            'job.delegated',
            actor='user',
            subject=assignee,
            payload={
                'text': msg,
                'intent': 'task',
                'request': request,
                'domain': domain,
                'job_id': job_id,
                'authorized': True,
            },
        )
        applied = pipe.apply_event(ev, write_diary=True)
        out.update({
            'event_id': applied.get('event_id') or ev.event_id,
            'emotion_updates': applied.get('emotion_updates') or [],
            'relationship_updates': applied.get('relationship_updates') or [],
            'journal_ids': applied.get('journal_ids') or [],
            'job_id': job_id,
            'intercept': True,
            'reply': _ack_task(assignee, request, job_id or 'pending'),
        })
        try:
            engine.observe(
                assignee,
                f'operator delegated task: {request}',
                learning_type='operational',
                evidence_ids=[out['event_id'] or job_id],
                scope='private',
                actor=assignee,
            )
        except Exception:
            pass
        return out

    event_type = {
        'praise': 'user.praised_agent',
        'correct': 'user.corrected_agent',
        'apology': 'user.apologized_to_agent',
        'insult': 'user.insulted_agent',
        'comparison': 'user.compared_agents',
        'preference': 'agent.message',
        'chat': 'agent.message',
    }.get(intent, 'agent.message')

    payload: dict = {'text': msg, 'intent': intent}
    subject = aid
    if intent == 'comparison':
        cmp = extract_comparison(msg) or {}
        favored = (cmp.get('favored_agent') or '').strip().lower()
        rival = (cmp.get('rival_agent') or cmp.get('other_agent') or '').strip().lower()
        # "Muse is smarter than you" → subject = speaking agent (aid), rival = muse
        if favored and not cmp.get('subject_hint') and favored != aid:
            subject = aid
            payload.update({
                'favored_agent': favored,
                'rival_agent': favored,
                'other_agent': favored,
            })
        elif favored == '' and rival:
            # "you are smarter than Muse"
            subject = aid
            payload.update({
                'favored_agent': aid,
                'rival_agent': rival,
                'other_agent': rival,
            })
        else:
            payload.update({
                'favored_agent': favored or rival,
                'rival_agent': rival or favored,
                'other_agent': rival or favored,
            })

    ev = new_event(
        event_type,
        actor='user',
        subject=subject,
        payload=payload,
    )
    write_diary = intent in (
        'praise', 'correct', 'preference', 'apology', 'insult', 'comparison',
    )
    applied = pipe.apply_event(ev, write_diary=write_diary)
    out.update({
        'event_id': applied.get('event_id') or ev.event_id,
        'emotion_updates': applied.get('emotion_updates') or [],
        'relationship_updates': applied.get('relationship_updates') or [],
        'journal_ids': applied.get('journal_ids') or [],
        'learning_observation_id': applied.get('learning_observation_id') or '',
    })

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
        elif intent == 'apology':
            obs = engine.observe(
                aid,
                f'operator apologized to {aid}; conflict recovery',
                learning_type='relationship',
                evidence_ids=[out['event_id']],
                scope='private',
                actor=aid,
            )
            out['learning_observation_id'] = out['learning_observation_id'] or obs.observation_id
            LivingDossierStore(layout).upsert_observation(
                aid,
                category='recent_social',
                value='operator apologized; tension easing',
                confidence=0.55,
                event_ids=(out['event_id'],),
                persistence='decaying',
            )
        elif intent == 'insult':
            obs = engine.observe(
                aid,
                f'operator insulted {aid}; do not invent reconciliation',
                learning_type='relationship',
                evidence_ids=[out['event_id']],
                scope='private',
                actor=aid,
            )
            out['learning_observation_id'] = out['learning_observation_id'] or obs.observation_id
            LivingDossierStore(layout).upsert_observation(
                aid,
                category='recent_frustration',
                value='operator insult landed; stay composed',
                confidence=0.6,
                event_ids=(out['event_id'],),
                persistence='decaying',
            )
        elif intent == 'comparison':
            rival = (payload.get('rival_agent') or '').strip()
            obs = engine.observe(
                aid,
                f'operator compared agents (rival={rival or "unknown"})',
                learning_type='relationship',
                evidence_ids=[out['event_id']],
                scope='private',
                actor=aid,
            )
            out['learning_observation_id'] = out['learning_observation_id'] or obs.observation_id
        elif intent == 'preference':
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
    if intent in ('remember', 'task'):
        return out

    snippet_u = user if len(user) <= 220 else user[:217] + '…'
    snippet_a = reply if len(reply) <= 280 else reply[:277] + '…'
    importance = 0.55 if intent in (
        'praise', 'correct', 'preference', 'apology', 'insult', 'comparison',
    ) else 0.35
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
