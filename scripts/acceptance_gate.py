#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""OtaconsKeep Premium Capability-Parity Acceptance Gate.

System-level acceptance against real Keep formula engines (isolated synthetic data).
Does NOT declare PASS unless all release gates clear.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))

from parity import acceptance as A


GATES = {
    'architecture_coverage': 1.0,
    'differential_scenarios': 0.95,
    'relationship_parity': 0.95,
    'memory_ranking_parity': 0.95,
    'persistence': 1.0,
    'restart_reboot_recovery': 1.0,
    'fresh_install_isolation': 1.0,
    'privacy_leaks': 0,
    'silent_failures_critical': 0,
    'double_state_mutation': 0,  # must be exactly 1 update => pass flag
    'soak_100': 1.0,
}


def main() -> int:
    t0 = time.time()
    os.environ['KEEP_REFERENCE_ROOT'] = os.environ.get(
        'KEEP_REFERENCE_ROOT', '/opt/otacon/otacon-executor',
    )
    print('=== OtaconsKeep Premium Capability-Parity Acceptance Gate ===')

    arch = A.architecture_coverage()
    print('architecture', arch['pass'], arch.get('live_path_hooks'))

    diff = A.run_differential_suite()
    print('differential', {
        k: diff[k] for k in (
            'scenario_count', 'scenarios_passed', 'scenario_pass_rate',
            'state_transition_parity', 'relationship_transition_parity',
            'formula9_agreement',
        )
    })

    emotion_ok = diff['state_transition_parity'] >= GATES['differential_scenarios']
    rel_ok = diff['relationship_transition_parity'] >= GATES['relationship_parity']
    mem_ok = diff['formula9_agreement'] >= GATES['memory_ranking_parity']

    double = A.double_mutation_test()
    print('double_mutation', double)

    fail_inj = A.failure_injection_test()
    print('failure_injection', fail_inj['pass'], fail_inj.get('layers_failed'))

    learn = A.learning_affects_later()
    print('learning', learn['pass'], learn.get('policy_verbosity'))

    iso = A.fresh_user_isolation()
    print('chris_josh_isolation', iso['pass'], {
        'chris_h': iso.get('chris_happiness'), 'josh_h': iso.get('josh_happiness'),
    })

    persist = A.persistence_and_reboot()
    print('persistence_reboot', persist['pass'], {
        'soft': persist.get('soft_restart'), 'hard': persist.get('hard_reboot_continue'),
    })

    install = A.installer_update_preserves_state()
    print('installer_update', install['pass'])

    soak25 = A.long_conversation_soak(25)
    soak50 = A.long_conversation_soak(50)
    soak100 = A.long_conversation_soak(100)
    print('soak', {'25': soak25['pass'], '50': soak50['pass'], '100': soak100['pass']})

    lifetime = A.lifetime_growth_test()
    print('lifetime_growth', lifetime['pass'], {
        'mid_refs': (lifetime.get('mid') or {}).get('refs'),
        'end_refs': (lifetime.get('end') or {}).get('refs'),
        'end_ally': (lifetime.get('end') or {}).get('ally'),
    })

    models = A.model_robustness()
    print('model_robustness', models['pass'], models.get('intents'))

    privacy = A.privacy_scan()
    print('privacy', privacy['pass'], privacy['count'])

    silent = {
        'pass': True,  # covered by failure_injection + LayerGuard critical scan
    }
    # Reuse parity silent scan
    from scripts import parity_gate as pg  # may fail — inline
    try:
        # duplicate minimal critical scan
        offenders = []
        for rel in ('expansion/hermes/behavior_pipeline.py', 'expansion/continuity/state_engine.py',
                    'expansion/continuity/health.py', 'expansion/hermes/behavioral_policy.py'):
            p = ROOT / rel
            lines = p.read_text().splitlines()
            for i, line in enumerate(lines):
                if line.strip() in ('except Exception:', 'except:') and i + 1 < len(lines) and lines[i + 1].strip() == 'pass':
                    offenders.append(f'{rel}:{i+1}')
        silent = {'pass': len(offenders) == 0, 'critical_offenders': offenders}
    except Exception as exc:
        silent = {'pass': False, 'error': str(exc)}

    # Chris / Josh install columns — both PremiumSession sandboxes
    chris_pass = iso['pass'] and persist['pass'] and soak100['pass']
    josh_pass = iso['pass'] and persist['pass'] and soak100['pass']

    matrix = [
        {'capability': 'Architecture (live chat path)', 'real_keep': '✓', 'chris_premium': '✓' if arch['pass'] else '✗', 'josh_premium': '✓' if arch['pass'] else '✗', 'result': 'PASS' if arch['pass'] else 'FAIL'},
        {'capability': 'StateEngine F4/7/8', 'real_keep': '✓', 'chris_premium': '✓', 'josh_premium': '✓', 'result': 'PASS' if emotion_ok else 'FAIL'},
        {'capability': 'Formula 5 relationships', 'real_keep': '✓', 'chris_premium': '✓', 'josh_premium': '✓', 'result': 'PASS' if rel_ok else 'FAIL'},
        {'capability': 'Formula 9 memory ranking', 'real_keep': '✓', 'chris_premium': '✓', 'josh_premium': '✓', 'result': 'PASS' if mem_ok else 'FAIL'},
        {'capability': 'Hermes behavioral policy', 'real_keep': '✓', 'chris_premium': '✓' if arch['pass'] else '✗', 'josh_premium': '✓' if arch['pass'] else '✗', 'result': 'PASS' if diff['scenario_pass_rate'] >= 0.95 else 'FAIL'},
        {'capability': 'Conversational affect', 'real_keep': '✓', 'chris_premium': '✓', 'josh_premium': '✓', 'result': 'PASS' if emotion_ok else 'FAIL'},
        {'capability': 'Learning / preferences', 'real_keep': '✓', 'chris_premium': '✓' if learn['pass'] else '✗', 'josh_premium': '✓' if learn['pass'] else '✗', 'result': 'PASS' if learn['pass'] else 'FAIL'},
        {'capability': 'Persistent memory', 'real_keep': '✓', 'chris_premium': '✓' if persist['pass'] else '✗', 'josh_premium': '✓' if persist['pass'] else '✗', 'result': 'PASS' if persist['pass'] else 'FAIL'},
        {'capability': 'Relationship growth', 'real_keep': '✓', 'chris_premium': '✓' if lifetime['pass'] else '✗', 'josh_premium': '✓' if lifetime['pass'] else '✗', 'result': 'PASS' if lifetime['pass'] else 'FAIL'},
        {'capability': 'Reboot recovery', 'real_keep': '✓', 'chris_premium': '✓' if persist.get('hard_reboot_continue') else '✗', 'josh_premium': '✓' if persist.get('hard_reboot_continue') else '✗', 'result': 'PASS' if persist.get('hard_reboot_continue') else 'FAIL'},
        {'capability': 'Fresh-user isolation', 'real_keep': 'N/A', 'chris_premium': '✓' if iso['pass'] else '✗', 'josh_premium': '✓' if iso['pass'] else '✗', 'result': 'PASS' if iso['pass'] else 'FAIL'},
        {'capability': 'Privacy (zero personal Keep data)', 'real_keep': 'N/A', 'chris_premium': '✓' if privacy['pass'] else '✗', 'josh_premium': '✓' if privacy['pass'] else '✗', 'result': 'PASS' if privacy['pass'] else 'FAIL'},
        {'capability': 'Double state mutation', 'real_keep': '✓', 'chris_premium': '✓' if double['pass'] else '✗', 'josh_premium': '✓' if double['pass'] else '✗', 'result': 'PASS' if double['pass'] else 'FAIL'},
        {'capability': 'Failure surfacing', 'real_keep': '✓', 'chris_premium': '✓' if fail_inj['pass'] else '✗', 'josh_premium': '✓' if fail_inj['pass'] else '✗', 'result': 'PASS' if fail_inj['pass'] else 'FAIL'},
        {'capability': 'Model-robust Hermes decisions', 'real_keep': '✓', 'chris_premium': '✓' if models['pass'] else '✗', 'josh_premium': '✓' if models['pass'] else '✗', 'result': 'PASS' if models['pass'] else 'FAIL'},
        {'capability': 'Installer/update preserves state', 'real_keep': '✓', 'chris_premium': '✓' if install['pass'] else '✗', 'josh_premium': '✓' if install['pass'] else '✗', 'result': 'PASS' if install['pass'] else 'FAIL'},
        {'capability': '25-turn soak', 'real_keep': 'Ref', 'chris_premium': f"{100 if soak25['pass'] else 0}%", 'josh_premium': f"{100 if soak25['pass'] else 0}%", 'result': 'PASS' if soak25['pass'] else 'FAIL'},
        {'capability': '50-turn soak', 'real_keep': 'Ref', 'chris_premium': f"{100 if soak50['pass'] else 0}%", 'josh_premium': f"{100 if soak50['pass'] else 0}%", 'result': 'PASS' if soak50['pass'] else 'FAIL'},
        {'capability': '100-turn behavior', 'real_keep': 'Ref', 'chris_premium': f"{100 if soak100['pass'] else 0}%", 'josh_premium': f"{100 if soak100['pass'] else 0}%", 'result': 'PASS' if soak100['pass'] else 'FAIL'},
        {'capability': 'Lifetime growth 100+50', 'real_keep': 'Ref', 'chris_premium': '✓' if lifetime['pass'] else '✗', 'josh_premium': '✓' if lifetime['pass'] else '✗', 'result': 'PASS' if lifetime['pass'] else 'FAIL'},
        {'capability': 'Chris install sandbox', 'real_keep': 'N/A', 'chris_premium': '✓' if chris_pass else '✗', 'josh_premium': '—', 'result': 'PASS' if chris_pass else 'FAIL'},
        {'capability': 'Josh install sandbox', 'real_keep': 'N/A', 'chris_premium': '—', 'josh_premium': '✓' if josh_pass else '✗', 'result': 'PASS' if josh_pass else 'FAIL'},
        {'capability': 'Differential scenarios', 'real_keep': '✓', 'chris_premium': f"{diff['scenario_pass_rate']*100:.1f}%", 'josh_premium': f"{diff['scenario_pass_rate']*100:.1f}%", 'result': 'PASS' if diff['scenario_pass_rate'] >= 0.95 else 'FAIL'},
    ]

    gate_pass = all([
        arch['pass'],
        diff['scenario_pass_rate'] >= GATES['differential_scenarios'],
        rel_ok, mem_ok, emotion_ok,
        persist['pass'],
        persist.get('hard_reboot_continue'),
        iso['pass'],
        privacy['pass'],
        silent['pass'],
        double['pass'],
        fail_inj['pass'],
        soak25['pass'], soak50['pass'], soak100['pass'],
        lifetime['pass'],
        learn['pass'],
        models['pass'],
        install['pass'],
        chris_pass, josh_pass,
        diff['scenario_count'] >= 150,
    ])

    report = {
        'generated_at': time.time(),
        'elapsed_sec': round(time.time() - t0, 2),
        'gates': GATES,
        'gate_pass': gate_pass,
        'architecture': arch,
        'differential': {k: diff[k] for k in (
            'scenario_count', 'scenarios_passed', 'scenario_pass_rate',
            'state_transition_parity', 'relationship_transition_parity',
            'formula9_agreement',
        )},
        'differential_samples': diff.get('records_sample'),
        'differential_failures': diff.get('failures'),
        'double_mutation': double,
        'failure_injection': fail_inj,
        'learning': learn,
        'isolation': iso,
        'persistence': persist,
        'installer_update': {'pass': install['pass']},
        'soak': {'25': soak25, '50': soak50, '100': soak100},
        'lifetime': lifetime,
        'model_robustness': models,
        'privacy': privacy,
        'silent': silent,
        'matrix': matrix,
        # Honest remaining Keep-only gaps
        'known_gaps_not_claimed': [
            'Keep emotional_matrix (~1.5k) not ported',
            'Keep Formula RB / URE deep bond engine not ported',
            'Keep life_continuity not ported',
            'Keep Hermes external LM final-render worker not ported',
            'Literal Windows host reboot / Chris-Josh physical installs not executed on this runner',
        ],
    }

    out = ROOT / 'tests' / 'parity' / 'out' / 'acceptance_report.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')

    print('\nFINAL MATRIX')
    print(f"{'Capability':<40} {'Real':<6} {'Chris':<8} {'Josh':<8} {'Result'}")
    print('-' * 80)
    for row in matrix:
        print(f"{row['capability']:<40} {row['real_keep']:<6} {row['chris_premium']:<8} {row['josh_premium']:<8} {row['result']}")
    print(f"\nACCEPTANCE GATE: {'PASS' if gate_pass else 'FAIL'}  report={out}")
    if not gate_pass:
        print('Do NOT claim Keep parity. Fix failures listed in acceptance_report.json')
    return 0 if gate_pass else 1


if __name__ == '__main__':
    raise SystemExit(main())
