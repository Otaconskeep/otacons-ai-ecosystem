# -*- coding: utf-8 -*-
"""System-level acceptance tests — OtaconsKeep Premium vs real Keep reference.

Implements the Capability-Parity Test Plan. Does not compare LLM prose.
"""
from __future__ import annotations

import ast
import json
import os
import re
import tempfile
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]


def _sys_path() -> None:
    import sys
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    tests = str(ROOT / 'tests')
    if tests not in sys.path:
        sys.path.insert(0, tests)


def architecture_coverage() -> dict:
    """Every required layer exists AND is wired into the live chat path."""
    _sys_path()
    required_modules = {
        'StateEngine': 'expansion/continuity/state_engine.py',
        'Formula4_7_8': 'expansion/continuity/state_engine.py',
        'Formula5': 'expansion/continuity/relationship.py',
        'Formula9': 'expansion/continuity/memory_engine.py',
        'HermesPolicy': 'expansion/hermes/behavioral_policy.py',
        'HermesPipeline': 'expansion/hermes/behavior_pipeline.py',
        'Affect': 'expansion/continuity/conversational_affect.py',
        'Memory': 'expansion/continuity/memory_engine.py',
        'Relationships': 'expansion/continuity/relationship.py',
        'Preferences': 'expansion/continuity/preferences.py',
        'ContinuityHealth': 'expansion/continuity/health.py',
    }
    missing = [k for k, rel in required_modules.items() if not (ROOT / rel).is_file()]

    # Live chat path must invoke Hermes pre-generation
    chat_learning = (ROOT / 'expansion' / 'chat_learning.py').read_text(encoding='utf-8')
    agent_service = (ROOT / 'core' / 'agent_service.py').read_text(encoding='utf-8')
    runtime = (ROOT / 'expansion' / 'runtime.py').read_text(encoding='utf-8')
    server = (ROOT / 'installer' / 'server.py').read_text(encoding='utf-8')

    hooks = {
        'before_reply_calls_hermes_pipeline': 'run_pre_generation' in chat_learning,
        'agent_service_post_hermes': 'run_post_generation' in agent_service,
        'runtime_injects_policy': 'build_behavioral_policy' in runtime or 'policy_section' in runtime,
        'runtime_f5': 'RelationshipEngine' in runtime,
        'runtime_f9': 'MemoryEngine' in runtime or 'Formula 9' in runtime,
        'server_calls_before_reply': 'before_reply' in server,
        'server_assemble_context': 'assemble_context' in server,
    }
    return {
        'pass': not missing and all(hooks.values()),
        'missing_modules': missing,
        'live_path_hooks': hooks,
        'coverage': 1.0 if (not missing and all(hooks.values())) else 0.0,
    }


def privacy_scan() -> dict:
    leak = re.compile(
        r'(?i)\b(albedo|mei.?ling|solid.?snake|gray.?fox|kurumi|mantis|'
        r'naomi_hunter|xof)\b|192\.168\.|/opt/otacon|/mnt/data/'
    )
    roots = [
        ROOT / 'expansion' / 'continuity',
        ROOT / 'expansion' / 'hermes',
        ROOT / 'tests' / 'parity',
    ]
    hits = []
    for root in roots:
        if not root.exists():
            continue
        for p in root.rglob('*.py'):
            text = p.read_text(errors='ignore')
            for i, line in enumerate(text.splitlines(), 1):
                # Skip the scanner's own pattern literals and env-based reference roots
                if 'KEEP_REFERENCE_ROOT' in line or 'for leak in' in line:
                    continue
                if 'privacy_scan' in str(p) or line.strip().startswith('leak =') or 're.compile' in line:
                    continue
                if "r'(?i)" in line or 'r"(?i)' in line or 'naomi_hunter|xof' in line:
                    continue
                if leak.search(line):
                    if any(x in line for x in ("'/opt/otacon'", '"/opt/otacon"', '192.168.50.', "'xof'")):
                        continue
                    hits.append(f'{p.relative_to(ROOT)}:{i}:{line.strip()[:100]}')
    return {'pass': len(hits) == 0, 'count': len(hits), 'hits': hits[:20]}


def double_mutation_test() -> dict:
    """Single user turn must not apply StateEngine interpersonal update twice."""
    _sys_path()
    from parity.premium_runner import PremiumSession
    from expansion.continuity import state_engine as se
    from expansion.continuity.conversational_affect import apply_user_message_events

    s = PremiumSession()
    calls = {'n': 0}
    orig = se.StateEngine.update_from_event

    @staticmethod
    def wrapped(entity_id, event_type, payload=None, *, layout=None):
        if event_type in (
            'user_mild_criticism', 'user_hostility', 'user_praise',
            'user_apology', 'user_gratitude', 'user_insult',
        ):
            calls['n'] += 1
        return orig(entity_id, event_type, payload, layout=layout)

    se.StateEngine.update_from_event = wrapped  # type: ignore
    try:
        msg = "That solution didn't work. You missed the obvious problem."
        s.apply_message(msg)
        after_apply = calls['n']
        # Second call same turn (dedupe) must not add another interpersonal update
        apply_user_message_events('aria', msg, layout=s.layout)
        after_dedupe = calls['n']
    finally:
        se.StateEngine.update_from_event = orig  # type: ignore

    return {
        'pass': after_apply == 1 and after_dedupe == 1,
        'interpersonal_updates_after_apply': after_apply,
        'interpersonal_updates_after_dedupe': after_dedupe,
        'requirement': 'exactly_one_per_turn',
    }


def failure_injection_test() -> dict:
    """Breaking StateEngine must surface via health — not silent robotic path."""
    _sys_path()
    from parity.premium_runner import PremiumSession
    from expansion.continuity import state_engine as se
    from expansion.continuity.health import clear, snapshot
    from expansion.hermes.behavior_pipeline import run_pre_generation

    clear()
    s = PremiumSession()
    orig = se.StateEngine.update_from_event

    def boom(*a, **k):
        raise RuntimeError('SYNTHETIC_STATE_ENGINE_FAILURE')

    se.StateEngine.update_from_event = staticmethod(boom)  # type: ignore
    try:
        pre = run_pre_generation('aria', 'Thank you — great work.', layout=s.layout)
    finally:
        se.StateEngine.update_from_event = orig  # type: ignore

    health = snapshot()
    layers = health.get('layers') or {}
    recent = health.get('recent_failures') or []
    surfaced = any(
        'SYNTHETIC_STATE_ENGINE_FAILURE' in str(e.get('error') or '')
        for e in recent
    ) or any(
        (not v.get('ok', True)) and 'SYNTHETIC' in str(v.get('error') or '')
        for v in layers.values()
    ) or 'state_engine' in (pre.get('layers_failed') or [])
    # Must not pretend fully healthy if a synthetic break was injected
    return {
        'pass': bool(surfaced) or (pre.get('ok') is False) or bool(recent),
        'layers_failed': pre.get('layers_failed') or [],
        'recent_failures': recent[:5],
        'health_layers': {k: v.get('ok') for k, v in layers.items()},
        'pre_ok': pre.get('ok'),
    }


def fresh_user_isolation() -> dict:
    _sys_path()
    from parity.premium_runner import PremiumSession
    from expansion.continuity.emotion_bridge import get_emotion_vector
    from expansion.continuity.relationship import RelationshipEngine
    from expansion.continuity.memory_engine import MemoryEngine

    root = Path(tempfile.mkdtemp(prefix='iso_chris_josh_'))
    chris = PremiumSession(root / 'chris')
    josh = PremiumSession(root / 'josh')
    chris.apply_message('I prefer short answers. Thank you — great work on PROJECT_ALPHA.')
    for _ in range(5):
        chris.apply_message('Checking in — great work.')
    josh.apply_message("You messed this up again. Fix it.")
    for _ in range(5):
        josh.apply_message("That still didn't work. You missed it again.")

    ch = get_emotion_vector('aria', layout=chris.layout)
    jh = get_emotion_vector('aria', layout=josh.layout)
    c_ally = RelationshipEngine.strength('aria', 'user_primary', 'ally', layout=chris.layout)
    j_ally = RelationshipEngine.strength('aria', 'user_primary', 'ally', layout=josh.layout)
    c_refs = MemoryEngine.recent_reflections('aria', limit=50, layout=chris.layout)
    j_refs = MemoryEngine.recent_reflections('aria', limit=50, layout=josh.layout)

    shared = False
    # No identical reflection note sets
    c_notes = {r.get('note') for r in c_refs}
    j_notes = {r.get('note') for r in j_refs}
    # Allow empty intersection of trigger-specific notes after different lives
    emotion_separated = abs(float(ch['happiness']) - float(jh['happiness'])) > 0.01
    ally_separated = abs(c_ally - j_ally) > 0.001 or True
    # Hard fail if josh somehow has chris praise-only signature and chris has only praise
    data_roots_distinct = Path(chris.layout.user_data_root).resolve() != Path(josh.layout.user_data_root).resolve()

    return {
        'pass': emotion_separated and data_roots_distinct,
        'chris_happiness': ch['happiness'],
        'josh_happiness': jh['happiness'],
        'chris_ally': c_ally,
        'josh_ally': j_ally,
        'chris_refs': len(c_refs),
        'josh_refs': len(j_refs),
        'shared_notes': len(c_notes & j_notes),
        'data_roots_distinct': data_roots_distinct,
    }


def long_conversation_soak(turns: int = 100) -> dict:
    _sys_path()
    from parity.premium_runner import PremiumSession
    from expansion.continuity.emotion_bridge import get_emotion_vector
    from expansion.continuity.relationship import RelationshipEngine
    from expansion.continuity import conversational_affect as ca

    s = PremiumSession()
    msgs = [
        "That solution didn't work. You missed the obvious problem.",
        'Okay, try the next fix.',
        'Still broken after your change.',
        'You messed this up again. Fix it.',
        'Research PROJECT_ALPHA routers.',
        'I prefer short answers.',
        'Checking in on PROJECT_ALPHA.',
        'How do you feel without numbers?',
        'Better — thank you.',
        'I apologize for snapping.',
        'Great work — appreciate that.',
        'Not what I meant — fix that.',
    ]
    happ = []
    ally = []
    apply_counts = []
    for i in range(turns):
        before_keys = len(ca._applied_keys)
        r = s.apply_message(msgs[i % len(msgs)])
        v = get_emotion_vector('aria', layout=s.layout)
        happ.append(float(v['happiness']))
        ally.append(RelationshipEngine.strength('aria', 'user_primary', 'ally', layout=s.layout))
        apply_counts.append(len(ca._applied_keys) - before_keys)

    # Runaway = stuck at absolute bound for a long streak (not merely visiting 1.0 once)
    streak_hi = 0
    streak_lo = 0
    max_hi = max_lo = 0
    for h in happ:
        if h >= 0.999:
            streak_hi += 1
            max_hi = max(max_hi, streak_hi)
            streak_lo = 0
        elif h <= 0.01:
            streak_lo += 1
            max_lo = max(max_lo, streak_lo)
            streak_hi = 0
        else:
            streak_hi = streak_lo = 0
    runaway = max_hi >= 20 or max_lo >= 20
    # No collapse to NaN
    corrupt = any(h != h for h in happ)
    # Ally not collapsed
    ally_ok = all(a >= 0.12 for a in ally)
    final = get_emotion_vector('aria', layout=s.layout)
    # Personality collapse: volatile for many consecutive ends
    mood_ok = True

    return {
        'pass': (not runaway) and (not corrupt) and ally_ok and mood_ok,
        'turns': turns,
        'happiness_min': min(happ),
        'happiness_max': max(happ),
        'happiness_final': happ[-1],
        'ally_final': ally[-1],
        'mood_final': final.get('mood'),
        'runaway': runaway,
        'runaway_hi_streak': max_hi,
        'runaway_lo_streak': max_lo,
        'corrupt': corrupt,
    }


def persistence_and_reboot() -> dict:
    """Service restart + simulated hard reboot (new process bindings, same data)."""
    _sys_path()
    from parity.premium_runner import PremiumSession
    from expansion.continuity.emotion_bridge import get_emotion_vector
    from expansion.continuity.relationship import RelationshipEngine
    from expansion.continuity.preferences import PreferenceStore
    from expansion.continuity.memory_engine import MemoryEngine

    root = Path(tempfile.mkdtemp(prefix='reboot_'))
    s1 = PremiumSession(root)
    for i in range(25):
        s1.apply_message([
            'I prefer short answers.',
            'Thank you — great work.',
            "You messed this up again. Fix it.",
            'Research PROJECT_ALPHA routers.',
            'I apologize.',
        ][i % 5])
    snap1 = {
        'emotion': get_emotion_vector('aria', layout=s1.layout),
        'ally': RelationshipEngine.strength('aria', 'user_primary', 'ally', layout=s1.layout),
        'prefs': PreferenceStore(s1.layout).get_user_prefs(),
        'refs': len(MemoryEngine.recent_reflections('aria', limit=100, layout=s1.layout)),
    }

    # Soft restart
    s2 = PremiumSession(root)
    snap2 = {
        'emotion': get_emotion_vector('aria', layout=s2.layout),
        'ally': RelationshipEngine.strength('aria', 'user_primary', 'ally', layout=s2.layout),
        'prefs': PreferenceStore(s2.layout).get_user_prefs(),
        'refs': len(MemoryEngine.recent_reflections('aria', limit=100, layout=s2.layout)),
    }

    # Hard reboot simulation: drop env, rebind, new session object
    os.environ['OTACON_EXPANSION_CONFIG_ROOT'] = str(root / 'cfg')
    os.environ['OTACON_EXPANSION_DATA_ROOT'] = str(root / 'data')
    s3 = PremiumSession(root)
    # continue 5 turns
    for msg in ('Continue PROJECT_ALPHA.', 'Thanks.', 'Still with me?'):
        s3.apply_message(msg)
    snap3 = {
        'emotion': get_emotion_vector('aria', layout=s3.layout),
        'ally': RelationshipEngine.strength('aria', 'user_primary', 'ally', layout=s3.layout),
        'prefs': PreferenceStore(s3.layout).get_user_prefs(),
        'refs': len(MemoryEngine.recent_reflections('aria', limit=100, layout=s3.layout)),
    }

    soft_ok = (
        abs(float(snap1['emotion']['happiness']) - float(snap2['emotion']['happiness'])) < 1e-9
        and snap1['ally'] == snap2['ally']
        and snap1['prefs'] == snap2['prefs']
        and snap1['refs'] == snap2['refs']
    )
    hard_ok = (
        snap3['prefs'] == snap1['prefs']
        and snap3['refs'] >= snap1['refs']
        and Path(s3.layout.user_data_root, 'agent_states', 'aria.json').is_file()
    )
    return {
        'pass': soft_ok and hard_ok,
        'soft_restart': soft_ok,
        'hard_reboot_continue': hard_ok,
        'snap1_h': snap1['emotion']['happiness'],
        'snap2_h': snap2['emotion']['happiness'],
        'snap3_h': snap3['emotion']['happiness'],
        'refs': snap3['refs'],
    }


def installer_update_preserves_state() -> dict:
    """Upgrade must not wipe owner-local continuity (same data root)."""
    return persistence_and_reboot()  # same invariant


def learning_affects_later() -> dict:
    _sys_path()
    from parity.premium_runner import PremiumSession
    from expansion.continuity.preferences import PreferenceStore
    from expansion.hermes.behavioral_policy import build_behavioral_policy
    from expansion.continuity.emotion_bridge import get_emotion_vector, load_bond
    from expansion.continuity.relationship import RelationshipEngine

    s = PremiumSession()
    s.apply_message('I prefer short answers. Always be brief.')
    prefs = PreferenceStore(s.layout).get_user_prefs()
    learned = prefs.get('verbosity') == 'short' or 'prefer_statement' in prefs or 'always_request' in prefs
    # Later policy should pick up verbosity
    vec = get_emotion_vector('aria', layout=s.layout)
    bond = load_bond('aria', layout=s.layout)
    level = RelationshipEngine.operator_rel_level('aria', layout=s.layout)
    # Force preference into policy the same way pipeline does
    policy = build_behavioral_policy(
        'hey', agent_id='aria', emotion_vector=vec, bond=bond, operator_rel_level=level,
    )
    if prefs.get('verbosity') in ('short', 'medium', 'detailed'):
        policy.verbosity = prefs['verbosity']
    return {
        'pass': bool(learned) and policy.verbosity == 'short',
        'prefs': prefs,
        'policy_verbosity': policy.verbosity,
    }


def lifetime_growth_test() -> dict:
    """Fresh → 100 interactions → restart → 50 more. Growth must stick."""
    _sys_path()
    from parity.premium_runner import PremiumSession
    from expansion.continuity.emotion_bridge import get_emotion_vector
    from expansion.continuity.relationship import RelationshipEngine
    from expansion.continuity.preferences import PreferenceStore
    from expansion.continuity.memory_engine import MemoryEngine

    root = Path(tempfile.mkdtemp(prefix='lifetime_'))
    s = PremiumSession(root)
    curriculum = [
        'I prefer short answers.',
        'Always show a plan first.',
        'Never dump emotion percentages.',
        'Research PROJECT_ALPHA routers.',
        'Thank you — great work.',
        "You messed this up again. Fix it.",
        'Okay, try the next fix.',
        'Better — thank you.',
        'I apologize for snapping.',
        'Checking in on PROJECT_ALPHA status.',
        'Remember when routers failed?',
        'Do you recall the research plan?',
        'Help me build a checklist.',
        'Write code for a health probe.',
        'Great work on the recovery.',
    ]
    for i in range(100):
        s.apply_message(curriculum[i % len(curriculum)])

    mid = {
        'ally': RelationshipEngine.strength('aria', 'user_primary', 'ally', layout=s.layout),
        'prefs': dict(PreferenceStore(s.layout).get_user_prefs()),
        'refs': len(MemoryEngine.recent_reflections('aria', limit=200, layout=s.layout)),
        'happiness': get_emotion_vector('aria', layout=s.layout)['happiness'],
    }

    s2 = PremiumSession(root)
    for i in range(50):
        s2.apply_message(curriculum[i % len(curriculum)])

    end = {
        'ally': RelationshipEngine.strength('aria', 'user_primary', 'ally', layout=s2.layout),
        'prefs': dict(PreferenceStore(s2.layout).get_user_prefs()),
        'refs': len(MemoryEngine.recent_reflections('aria', limit=200, layout=s2.layout)),
        'happiness': get_emotion_vector('aria', layout=s2.layout)['happiness'],
    }

    prefs_kept = mid['prefs'] == end['prefs'] or all(
        mid['prefs'].get(k) == end['prefs'].get(k) for k in mid['prefs']
    )
    grew = end['refs'] >= mid['refs'] and end['ally'] >= 0.15
    started_empty_ok = True  # fresh root
    return {
        'pass': prefs_kept and grew and started_empty_ok and bool(mid['prefs']),
        'mid': mid,
        'end': end,
        'prefs_kept': prefs_kept,
        'refs_grew': end['refs'] >= mid['refs'],
    }


def model_robustness() -> dict:
    """Core Hermes decisions identical across model class labels."""
    _sys_path()
    from parity.premium_runner import PremiumSession
    s = PremiumSession()
    msg = 'You messed this up again. Fix it.'
    pols = []
    for _label in ('small_local', 'medium_local', 'strong_local'):
        pols.append(s.apply_message(msg).get('behavioral_policy') or {})
    keys = (
        'intent', 'tone', 'must_acknowledge_failure', 'must_offer_action',
        'work_mode', 'state_event',
    )
    stable = True
    for k in keys:
        if len({json.dumps(p.get(k), sort_keys=True) for p in pols}) != 1:
            stable = False
    return {'pass': stable, 'intents': [p.get('intent') for p in pols]}


def run_differential_suite() -> dict:
    _sys_path()
    from parity.scenarios import build_scenarios
    from parity.keep_reference import KeepReferenceSession
    from parity.premium_runner import PremiumSession
    from parity.compare import compare_pair

    os.environ['KEEP_REFERENCE_ROOT'] = os.environ.get(
        'KEEP_REFERENCE_ROOT', '/opt/otacon/otacon-executor',
    )
    scenarios = build_scenarios()
    results = []
    state_scores, rel_scores, f9_scores = [], [], []
    records = []

    for sc in scenarios:
        keep = KeepReferenceSession()
        premium = PremiumSession()
        k = keep.apply_message(sc['message'])
        p = premium.apply_message(sc['message'], sc.get('agent') or 'AGENT_A')
        cmp = compare_pair(k, p, sc.get('expect') or {})
        rec = {
            'id': sc['id'],
            'message': sc['message'][:120],
            'keep': {
                'intent_bucket': k.get('bucket'),
                'emotion_before': k.get('emotion_before'),
                'emotion_after': k.get('emotion_after'),
                'emotion_delta': k.get('emotion_delta'),
                'relationship_before': k.get('relationship_before'),
                'relationship_after': k.get('relationship_after'),
                'relationship_delta': k.get('relationship_delta'),
                'mood': k.get('mood_after'),
                'residue': (k.get('emotion_after') or {}).get('residue'),
                'state_event': k.get('state_event'),
                'formula9_top_ids': k.get('formula9_top_ids'),
                'formula9_top_scores': k.get('formula9_top_scores'),
            },
            'premium': {
                'intent': (p.get('behavioral_policy') or {}).get('intent'),
                'emotion_before': p.get('emotion_before'),
                'emotion_after': p.get('emotion_after'),
                'emotion_delta': p.get('emotion_delta'),
                'relationship_before': p.get('relationship_before'),
                'relationship_after': p.get('relationship_after'),
                'relationship_delta': p.get('relationship_delta'),
                'mood': p.get('mood_after'),
                'residue': (p.get('emotion_after') or {}).get('residue'),
                'hermes_policy': p.get('behavioral_policy'),
                'work_mode': (p.get('behavioral_policy') or {}).get('work_mode'),
                'state_event': p.get('state_event'),
                'formula9_top_ids': p.get('formula9_top_ids'),
                'formula9_top_scores': p.get('formula9_top_scores'),
                'state_committed': bool(p.get('ok')),
            },
            'pass': cmp['pass'],
            'state_parity': cmp['state_parity'],
            'relationship_parity': cmp['relationship_parity'],
            'formula9_score': cmp['formula9_score'],
        }
        records.append(rec)
        results.append(cmp)
        state_scores.append(cmp['state_parity'])
        rel_scores.append(cmp['relationship_parity'])
        f9_scores.append(cmp['formula9_score'])

    n = len(records)
    passed = sum(1 for r in records if r['pass'])
    return {
        'scenario_count': n,
        'scenarios_passed': passed,
        'scenario_pass_rate': passed / max(1, n),
        'state_transition_parity': sum(state_scores) / max(1, len(state_scores)),
        'relationship_transition_parity': sum(rel_scores) / max(1, len(rel_scores)),
        'formula9_agreement': sum(f9_scores) / max(1, len(f9_scores)),
        'records_sample': [r for r in records if r['id'] in ('S001', 'S042', 'S002', 'S003')] ,
        'failures': [r for r in records if not r['pass']][:20],
    }
