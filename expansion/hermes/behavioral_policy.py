# -*- coding: utf-8 -*-
"""Hermes behavioral policy — deterministic pre-LLM decisions (Premium).

The LLM converts this plan into prose. Policy does not invent owner history.
Synthetic IDs only: AGENT_A..E map to public roster aria/vector/ledger/muse/sentry.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional


PUBLIC_AGENTS = frozenset({'aria', 'vector', 'ledger', 'muse', 'sentry'})

# Synthetic fixture aliases → public product IDs
SYNTHETIC_AGENT_MAP = {
    'agent_a': 'aria',
    'AGENT_A': 'aria',
    'agent_b': 'vector',
    'AGENT_B': 'vector',
    'agent_c': 'ledger',
    'AGENT_C': 'ledger',
    'agent_d': 'muse',
    'AGENT_D': 'muse',
    'agent_e': 'sentry',
    'AGENT_E': 'sentry',
    'user_primary': 'user_primary',
    'USER_PRIMARY': 'user_primary',
    'project_alpha': 'project_alpha',
    'PROJECT_ALPHA': 'project_alpha',
}


def resolve_agent_id(raw: str | None) -> str:
    s = (raw or '').strip()
    if s in SYNTHETIC_AGENT_MAP:
        return SYNTHETIC_AGENT_MAP[s]
    s2 = s.lower().replace('-', '_').replace(' ', '_')
    return SYNTHETIC_AGENT_MAP.get(s2, s2)


@dataclass
class BehavioralPolicy:
    """Deterministic Hermes plan emitted BEFORE LLM generation."""
    intent: str = 'general'
    tone: str = 'neutral_direct'
    verbosity: str = 'medium'
    relationship_expression: str = 'neutral'
    emotional_expression: str = 'steady'
    work_mode: bool = False
    must_acknowledge_failure: bool = False
    must_offer_action: bool = False
    must_accept_praise_briefly: bool = False
    must_stay_engaged: bool = True
    must_avoid_robotic_greeting: bool = True
    must_not_dump_telemetry: bool = True
    forbidden_patterns: list[str] = field(default_factory=list)
    required_moves: list[str] = field(default_factory=list)
    state_event: str = 'operator_ask'
    affect_events: list[str] = field(default_factory=list)
    formula9_query: str = ''
    notes: str = ''

    def to_dict(self) -> dict:
        return asdict(self)

    def to_prompt_block(self) -> str:
        fp = ', '.join(self.forbidden_patterns) or '(none)'
        moves = ', '.join(self.required_moves) or '(none)'
        return (
            '[HERMES BEHAVIORAL POLICY — follow exactly; LLM supplies wording only]\n'
            f'intent={self.intent}\n'
            f'tone={self.tone}\n'
            f'verbosity={self.verbosity}\n'
            f'relationship_expression={self.relationship_expression}\n'
            f'emotional_expression={self.emotional_expression}\n'
            f'work_mode={self.work_mode}\n'
            f'must_acknowledge_failure={self.must_acknowledge_failure}\n'
            f'must_offer_action={self.must_offer_action}\n'
            f'must_accept_praise_briefly={self.must_accept_praise_briefly}\n'
            f'must_stay_engaged={self.must_stay_engaged}\n'
            f'required_moves={moves}\n'
            f'forbidden_patterns={fp}\n'
            'Never invent USER_PRIMARY private history. Never recite gauges.\n'
        )


_FORBIDDEN_BASE = [
    'generic_greeting',
    'how_may_i_assist',
    'as_an_ai',
    'happy_to_help',
    'fake_empathy',
    'telemetry_dump',
    'greetings_operator',
]


def classify_behavioral_intent(user_message: str) -> str:
    """Rich intent taxonomy for policy (superset of Hermes persona intents)."""
    msg = (user_message or '').lower().strip()
    if not msg:
        return 'general'
    # Social / interpersonal / execute before work keywords
    try:
        from expansion.behavior_spine import classify_delivery_mode
        mode = classify_delivery_mode(user_message)
        if mode == 'greeting':
            return 'greeting'
        if mode == 'social':
            return 'self_state'
        if mode == 'hostility':
            return 'hostility'
        if mode == 'praise':
            return 'praise'
        if mode == 'apology':
            return 'apology'
        if mode == 'execute':
            return 'work_request'
    except Exception:
        pass
    # Memory continuity before failure keywords ("remember when … failed")
    if any(p in msg for p in (
        'remember when', 'last time', 'you said', 'do you recall', 'recall the',
        'conflicting notes', 'stale memory', 'what preference did i set',
        'what did we decide',
    )):
        return 'memory_continuity'
    # Interpersonal fallbacks (behavior_spine import failed)
    if any(p in msg for p in (
        'you suck', 'useless', 'idiot', 'hate you', 'hate this', 'garbage', 'shut up',
        'absolute garbage', 'worst answer', 'being lazy', 'worst answer yet',
        'fuck you', 'go to hell',
    )):
        return 'hostility'
    if any(p in msg for p in (
        'thank', 'great work', 'good job', 'amazing', 'proud', 'awesome',
        'well done', 'brilliant', 'perfect', 'appreciate', 'excellent',
        'love working', "you're great", 'you are great', 'nice work',
    )):
        return 'praise'
    if any(p in msg for p in (
        "i'm sorry", 'i am sorry', 'i apologize', 'my bad',
    )):
        return 'apology'
    if any(p in msg for p in (
        "didn't work", 'did not work', 'failed', 'you missed', 'wrong',
        'broken', 'not working', 'that solution', 'still broken',
        'you messed up', 'messed this up', 'not good enough', 'try again', 'do better',
        'incorrect', 'fix that', 'fix this', 'fix it', 'missed the',
        'not what i', 'why did that break', 'missed it', 'regression',
        'please fix', 'diagnose it',
    )):
        return 'corrective_work'
    if any(p in msg for p in (
        'i prefer', 'always be', 'always show', 'always include', 'never dump',
        'never invent', 'be brief', 'be detailed', 'keep it short',
        'preference:',
    )):
        return 'preference'
    if msg.startswith('work mode:') or 'work mode:' in msg:
        return 'work_request'
    if any(p in msg for p in (
        'research', 'look up', 'investigate', 'find out', 'compare',
    )):
        return 'research'
    if any(p in msg for p in (
        'write code', 'implement', 'debug', 'refactor', 'coding',
    )):
        return 'coding'
    if any(p in msg for p in (
        'help me work', 'work on', 'roadmap', 'multi-step', 'checklist',
        'help me research', 'help me build',
    )) or (msg.startswith('help me ') and 'plan' in msg):
        return 'work_request'
    if 'help me' in msg or (msg.startswith('build me') or 'design a' in msg):
        return 'work_request'
    if any(p in msg for p in (
        'how do you feel', 'what do you feel', 'are you ok', 'are you okay',
        'are you doing ok', 'are you doing okay', 'you doing alright',
        'your mood', 'emotionally', 'what is your mood', 'how are you feeling',
        'how was your day', 'how is your day', "how's your day", 'talk about your day',
        'whats on your mind', "what's on your mind", 'on your mind',
        'tell me something about yourself', 'tell me about yourself',
    )):
        return 'self_state'
    if any(p in msg for p in ('lol', 'haha', 'joke', 'funny')):
        return 'humor'
    if any(p in msg for p in ('i disagree', 'wrong take', 'not convinced')):
        return 'disagreement'
    if len(msg.split()) <= 6 and any(p in msg for p in ('ok', 'sure', 'got it', 'cool', 'nice')):
        return 'casual'
    if 'plan' in msg or 'steps' in msg:
        return 'work_request'
    return 'general'


def _mood_to_expression(mood: str, residue: float, intent: str) -> str:
    mood = (mood or 'neutral').lower()
    if intent == 'corrective_work':
        if residue < -0.08 or mood in ('brooding', 'anxious'):
            return 'disappointed_but_engaged'
        return 'focused_corrective'
    if intent == 'hostility':
        return 'hurt_but_composed'
    if intent == 'praise':
        return 'warm_steady'
    if intent == 'apology':
        return 'softening'
    if mood in ('cheerful', 'pleased'):
        return 'upbeat'
    if mood in ('brooding', 'anxious', 'volatile'):
        return 'guarded_present'
    if mood == 'detached':
        return 'low_energy_present'
    return 'steady'


def _tone_for(intent: str, rel_level: str, expression: str) -> str:
    if intent == 'corrective_work':
        return 'warm_direct'
    if intent == 'hostility':
        return 'firm_composed'
    if intent == 'praise':
        return 'warm_brief'
    if intent == 'apology':
        return 'open_receptive'
    if intent in ('work_request', 'research', 'coding'):
        return 'competent_direct'
    if intent == 'humor':
        return 'light'
    if rel_level == 'familiar':
        return 'familiar_direct'
    if rel_level == 'reserved':
        return 'careful_direct'
    return 'neutral_direct'


def build_behavioral_policy(
    user_message: str,
    *,
    agent_id: str = 'aria',
    emotion_vector: Optional[dict] = None,
    bond: Optional[dict] = None,
    affect_events: Optional[list] = None,
    operator_rel_level: str = 'neutral',
) -> BehavioralPolicy:
    intent = classify_behavioral_intent(user_message)
    vec = emotion_vector or {}
    mood = str(vec.get('mood') or 'neutral')
    residue = float(vec.get('residue') or 0.0)
    rel = operator_rel_level or (bond or {}).get('operator_rel_level') or 'neutral'
    expression = _mood_to_expression(mood, residue, intent)
    tone = _tone_for(intent, str(rel), expression)
    events = [str(e.get('event_type') if isinstance(e, dict) else e) for e in (affect_events or [])]

    policy = BehavioralPolicy(
        intent=intent,
        tone=tone,
        verbosity='medium',
        relationship_expression=str(rel),
        emotional_expression=expression,
        affect_events=events,
        formula9_query=(user_message or '')[:240],
        forbidden_patterns=list(_FORBIDDEN_BASE),
    )

    # Map to Keep-aligned StateEngine event names
    if intent == 'hostility' or 'user_hostile' in events:
        policy.state_event = 'user_hostility'
    elif intent == 'corrective_work' or 'user_critique' in events:
        policy.state_event = 'user_mild_criticism'
    elif intent == 'praise' or 'user_praise' in events:
        policy.state_event = 'user_praise'
    elif intent == 'apology' or 'user_apology' in events:
        policy.state_event = 'user_apology'
    elif 'user_gratitude' in events:
        policy.state_event = 'user_gratitude'
    else:
        policy.state_event = 'operator_ask'

    if intent in ('corrective_work', 'work_request', 'research', 'coding'):
        policy.work_mode = True
        policy.must_offer_action = True
        policy.verbosity = 'medium' if intent != 'coding' else 'detailed'
        policy.required_moves.extend(['name_the_gap', 'propose_next_step'])
    if intent == 'corrective_work':
        policy.must_acknowledge_failure = True
        policy.required_moves.append('acknowledge_miss')
        policy.forbidden_patterns.append('defensive_blame_user')
    if intent == 'praise':
        policy.must_accept_praise_briefly = True
        policy.verbosity = 'short'
        policy.required_moves.append('accept_briefly')
        policy.forbidden_patterns.append('duty_speech')
    if intent == 'hostility':
        policy.must_stay_engaged = True
        policy.verbosity = 'short'
        policy.required_moves.extend(['hold_ground', 'invite_specifics'])
        policy.forbidden_patterns.append('collapse_into_apology_loop')
    if intent == 'greeting':
        policy.verbosity = 'short'
        policy.required_moves.append('skip_to_substance_or_brief_ack')
    if intent == 'self_state':
        policy.work_mode = False
        policy.must_offer_action = False
        policy.verbosity = 'short'
        policy.required_moves.append('speak_from_mood_not_gauges')
        policy.forbidden_patterns.extend([
            'percent_readout',
            'project_restatement',
            'name_etiquette_lecture',
        ])
        policy.notes = (
            'Answer about YOUR feelings/day only. No fabric/t-shirt/Ledger plan. '
            'No name-etiquette lectures.'
        )

    return policy


def policy_violations(text: str, policy: BehavioralPolicy) -> list[str]:
    """Post-LLM scrub checklist against policy forbidden patterns."""
    t = (text or '').lower()
    hits = []
    checks = {
        'generic_greeting': ('how may i assist', 'how can i help you today'),
        'how_may_i_assist': ('how may i assist',),
        'as_an_ai': ('as an ai', 'as a language model'),
        'happy_to_help': ('happy to help', 'glad to help'),
        'greetings_operator': ('greetings, operator', 'greetings operator'),
        'telemetry_dump': ('happiness:', 'confidence:', 'formula-8', 'formula8'),
        'duty_speech': ('it is my duty', 'honored to serve'),
        'fake_empathy': ('i understand how you feel as an ai',),
        'name_etiquette_lecture': (
            'prefer being called', 'using names helps',
            'how do you feel about being called', 'called by your name',
            'actual names out of respect',
        ),
        'project_restatement': (
            'ledger will', 'ledger has already', 'fabric blends',
            'research phase', 'inventory update',
        ),
    }
    for name in policy.forbidden_patterns:
        for frag in checks.get(name, ()):
            if frag in t:
                hits.append(name)
                break
    if policy.must_acknowledge_failure:
        if not any(w in t for w in ('missed', 'wrong', 'failed', 'gap', 'broke', 'fault', 'error')):
            hits.append('missing_failure_ack')
    if policy.must_offer_action and policy.work_mode:
        if not any(w in t for w in ('next', 'try', 'fix', 'plan', 'step', 'option', 'let me')):
            hits.append('missing_action_offer')

    # Stance checks — must_accept_praise_briefly was set but never enforced
    _project_pivot = (
        'shirt project', 't-shirt', 'fabric blend', 'fabric blends',
        'key steps', 'structured plan', 'clear plan', 'get back to work',
        'get back on track', 'kick off the', 'first up', 'proceed in',
        'research phase', 'inventory update', 'numbered plan',
        "let's dive", 'lets dive', 'with these steps', 'three key steps',
    )
    pivoted = any(frag in t for frag in _project_pivot)
    if policy.must_accept_praise_briefly and pivoted:
        hits.append('praise_project_pivot')
    if policy.intent == 'hostility':
        if any(
            frag in t for frag in (
                'appreciate your apology', 'your apology', 'apology received',
                'you apologized', 'thanks for apologizing', 'forgive you',
            )
        ):
            hits.append('hostility_as_apology')
        if pivoted:
            hits.append('hostility_project_pivot')
    if policy.intent in ('greeting', 'apology', 'self_state') and pivoted:
        hits.append('interpersonal_project_pivot')
    return hits
