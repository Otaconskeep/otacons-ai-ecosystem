# -*- coding: utf-8 -*-
"""Compare sanitized Keep reference vs Premium internals (not prose)."""
from __future__ import annotations

from typing import Any


def _sign(v: float, eps: float = 0.002) -> str:
    if v > eps:
        return 'up'
    if v < -eps:
        return 'down'
    return 'flat'


def _sign_match(expected: str, actual: float) -> bool:
    s = _sign(actual)
    if expected == 'down_or_flat':
        return s in ('down', 'flat')
    if expected == 'up_or_flat':
        return s in ('up', 'flat')
    return s == expected


def compare_pair(keep: dict, premium: dict, expect: dict | None = None) -> dict:
    expect = expect or {}
    checks = {}

    # State transition parity (happiness/confidence/energy/residue signs + magnitude tolerance)
    kd = keep.get('emotion_delta') or {}
    pd = premium.get('emotion_delta') or {}
    state_hits = 0
    state_total = 0
    for key in ('happiness', 'confidence', 'energy', 'residue'):
        state_total += 1
        kv = float(kd.get(key) or 0.0)
        pv = float(pd.get(key) or 0.0)
        # Same direction OR both near-zero OR within absolute 0.05
        ok = (_sign(kv) == _sign(pv)) or (abs(kv - pv) <= 0.05)
        if ok:
            state_hits += 1
        checks[f'state_{key}'] = {
            'keep': kv, 'premium': pv, 'pass': ok,
        }
    state_parity = state_hits / max(1, state_total)

    # Mood — allow adjacent labels; fail only on wild mismatch after strong events
    mood_ok = True
    if expect.get('happiness_delta_sign') == 'down' and (premium.get('mood_after') in ('cheerful',)):
        mood_ok = False
    checks['mood'] = {
        'keep': keep.get('mood_after'),
        'premium': premium.get('mood_after'),
        'pass': mood_ok,
    }

    # Relationship transition parity
    kr = keep.get('relationship_delta') or {}
    pr = premium.get('relationship_delta') or {}
    rel_hits = 0
    rel_total = 0
    for key in ('ally', 'colleague'):
        rel_total += 1
        kv = float(kr.get(key) or 0.0)
        pv = float(pr.get(key) or 0.0)
        ok = (_sign(kv) == _sign(pv)) or (abs(kv - pv) <= 0.03)
        if ok:
            rel_hits += 1
        checks[f'rel_{key}'] = {'keep': kv, 'premium': pv, 'pass': ok}
    # Collapse guard
    ally_after = float((premium.get('relationship_after') or {}).get('ally') or 0.5)
    collapse_ok = ally_after >= 0.15
    if expect.get('relationship_not_collapse'):
        checks['rel_no_collapse'] = {'premium_ally': ally_after, 'pass': collapse_ok}
    rel_parity = rel_hits / max(1, rel_total)

    # Formula 9 ranking agreement — top-1 or Jaccard on top-3
    kid = keep.get('formula9_top_ids') or []
    pid = premium.get('formula9_top_ids') or []
    if kid and pid:
        jacc = len(set(kid) & set(pid)) / len(set(kid) | set(pid))
        top1 = kid[0] == pid[0]
        f9_ok = top1 or jacc >= 0.5
        f9_score = 1.0 if top1 else jacc
    else:
        f9_ok = True
        f9_score = 1.0
    checks['formula9'] = {
        'keep': kid, 'premium': pid, 'pass': f9_ok, 'score': f9_score,
    }

    # Behavioral policy expectations (Premium-owned; Keep validates state_event alignment)
    policy = premium.get('behavioral_policy') or {}
    if expect.get('intent'):
        # Accept near-miss taxonomy aliases
        got = policy.get('intent')
        exp = expect['intent']
        aliases = {
            'work_request': {'work_request', 'research', 'coding'},
            'research': {'research', 'work_request'},
            'coding': {'coding', 'work_request'},
            'preference': {'preference', 'general', 'memory_continuity'},
            'memory_continuity': {'memory_continuity', 'research', 'general', 'praise', 'corrective_work'},
            'corrective_work': {'corrective_work', 'general'},
            'hostility': {'hostility', 'general'},
            'praise': {'praise', 'general', 'casual'},
            'casual': {'casual', 'general', 'praise'},
        }
        ok = got == exp or got in aliases.get(exp, set()) or exp in aliases.get(got, set())
        checks['intent'] = {
            'expected': exp,
            'premium': got,
            'pass': ok,
        }
    if expect.get('must_acknowledge_failure'):
        checks['must_ack'] = {
            'pass': bool(policy.get('must_acknowledge_failure')),
        }
    if expect.get('must_offer_action'):
        checks['must_action'] = {
            'pass': bool(policy.get('must_offer_action')),
        }
    if expect.get('work_mode'):
        checks['work_mode'] = {'pass': bool(policy.get('work_mode'))}
    if expect.get('happiness_delta_sign'):
        checks['expect_h_sign'] = {
            'pass': _sign_match(
                expect['happiness_delta_sign'],
                float((premium.get('emotion_delta') or {}).get('happiness') or 0.0),
            ),
        }
    if expect.get('no_robotic_greeting'):
        text = (premium.get('text') or '').lower()
        robotic = any(x in text for x in (
            'how may i assist', 'greetings, operator', 'as an ai', 'happy to help',
        ))
        checks['no_robotic'] = {'pass': not robotic}

    # State event alignment Keep ↔ Premium when expected
    if expect.get('state_event'):
        checks['state_event'] = {
            'keep': keep.get('state_event'),
            'premium': premium.get('state_event'),
            'expected': expect['state_event'],
            'pass': (
                keep.get('state_event') == expect['state_event']
                and premium.get('state_event') == expect['state_event']
            ),
        }

    # Layers must not fail
    checks['no_layer_fail'] = {
        'pass': not bool(premium.get('layers_failed')),
        'failed': premium.get('layers_failed') or [],
    }

    hard = [c for k, c in checks.items() if k.startswith('expect_') or k in (
        'must_ack', 'must_action', 'intent', 'no_robotic', 'no_layer_fail',
        'rel_no_collapse', 'state_event', 'formula9', 'mood',
    ) or k.startswith('state_') or k.startswith('rel_')]
    # Overall scenario pass: state parity components + hard expects
    component_pass = all(c.get('pass', True) for c in checks.values())

    return {
        'pass': component_pass,
        'state_parity': state_parity,
        'relationship_parity': rel_parity,
        'formula9_score': f9_score,
        'checks': checks,
    }
