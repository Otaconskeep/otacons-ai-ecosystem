"""Controlled-pilot REX governance for Expansion Premium (clean-room).

Ports the *intent* of Keep's 2026-09-22 controlled pilot — not a copy of
``autonomous/rex_recovery.py``:

  - default-deny domain allowlist for autonomous implementation
  - hard-blocked production domains
  - DoD requiring before/after evidence on pilot work
  - graduation streak (N clean closes; any rollback resets)
  - bootstrap that *preserves* pilot mode across restarts (no silent re-freeze)

Persists under user_jobs/pilot_governance.json.
"""
from __future__ import annotations

import re
import time
from typing import Any, Optional

from expansion.persist import atomic_write_json, read_json
from expansion.state_layout import StateLayout, resolve_layout

# Positive allowlist — everything else stays gated in controlled_pilot mode.
PILOT_ALLOWED_DOMAINS = frozenset({
    'learning',
    'awareness',
    'observability',
    'documentation',
    'testing',
    'records',       # Expansion-native Ledger lane
    'research',
    'continuity',
    'coordination',  # Aria planning only; still needs DoD for close
})

# Production-impacting — never auto-implement in pilot (defense in depth).
HARD_BLOCKED_DOMAINS = frozenset({
    'infrastructure',
    'systems',
    'security',
    'monitoring',
    'creative',
    'media',
    'technical',
})

WEAK_VERIFY_PATTERNS = (
    r'py_compile',
    r'python\s+-m\s+py_compile',
    r'compileall',
    r'curl\s+.*(/health|/healthz)\b',
)

DEFAULT_PILOT = {
    'schema_version': 1,
    'active': True,
    'mode': 'controlled_pilot',
    'freeze_new_proposals': False,
    'golden_only_dispatch': True,
    'max_concurrent_workers': 2,
    'soak_dispatch_halted': False,
    'pilot_graduation_min': 3,
    'pilot_consecutive_clean_closes': 0,
    'pilot_close_history': [],
    'pilot_graduated': False,
    'auto_rollback_enabled': True,
    'started_at': 0.0,
    'updated_at': 0.0,
}


def _path(layout: StateLayout):
    return layout.user_jobs / 'pilot_governance.json'


def _now() -> float:
    return time.time()


def load_status(layout: Optional[StateLayout] = None) -> dict:
    layout = layout or resolve_layout()
    layout.ensure_user_dirs()
    raw = read_json(_path(layout), default=None)
    if not isinstance(raw, dict) or not raw.get('active'):
        data = dict(DEFAULT_PILOT)
        data['started_at'] = _now()
        data['updated_at'] = data['started_at']
        atomic_write_json(_path(layout), data)
        return data
    out = dict(DEFAULT_PILOT)
    out.update(raw)
    return out


def save_status(updates: dict, layout: Optional[StateLayout] = None) -> dict:
    layout = layout or resolve_layout()
    layout.ensure_user_dirs()
    cur = load_status(layout)
    cur.update(updates or {})
    cur['updated_at'] = _now()
    cur.setdefault('schema_version', 1)
    atomic_write_json(_path(layout), cur)
    return cur


def bootstrap_pilot(layout: Optional[StateLayout] = None) -> dict:
    """Idempotent bootstrap — never silently re-freeze an active controlled pilot."""
    layout = layout or resolve_layout()
    prev = read_json(_path(layout), default=None)
    if (
        isinstance(prev, dict)
        and prev.get('active')
        and prev.get('mode') == 'controlled_pilot'
        and not prev.get('soak_dispatch_halted')
    ):
        # Preserve operator-approved pilot state across restarts.
        return load_status(layout)
    if isinstance(prev, dict) and prev.get('soak_dispatch_halted'):
        return save_status({
            'active': True,
            'mode': prev.get('mode') or 'controlled_pilot',
            'freeze_new_proposals': True,
            'golden_only_dispatch': True,
            'max_concurrent_workers': 0,
            'soak_dispatch_halted': True,
        }, layout)
    return load_status(layout)


def enable_controlled_pilot(
    layout: Optional[StateLayout] = None,
    *,
    graduation_min: int = 3,
) -> dict:
    return save_status({
        'active': True,
        'mode': 'controlled_pilot',
        'freeze_new_proposals': False,
        'golden_only_dispatch': True,
        'max_concurrent_workers': 2,
        'soak_dispatch_halted': False,
        'pilot_graduation_min': int(graduation_min),
        'pilot_graduated': False,
        'auto_rollback_enabled': True,
    }, layout)


def domain_key(domain: str) -> str:
    return (domain or '').strip().lower()


def dispatch_gate(
    *,
    domain: str,
    stage: str = 'IN_PROGRESS',
    layout: Optional[StateLayout] = None,
) -> dict[str, Any]:
    """Default-deny implementation dispatch under controlled_pilot."""
    st = load_status(layout)
    dom = domain_key(domain)
    stage_u = (stage or '').upper()

    if not st.get('active') or st.get('mode') != 'controlled_pilot':
        return {'allow': True, 'kind': 'pilot_inactive', 'domain': dom}

    if st.get('soak_dispatch_halted') or int(st.get('max_concurrent_workers') or 0) <= 0:
        return {
            'allow': False,
            'kind': 'worker_cap_zero',
            'error': 'pilot soak halted or max_concurrent_workers=0',
            'domain': dom,
        }

    # Research/planning always allowed; gate bites at implementation.
    if stage_u in ('BACKLOG', 'READY', 'RESEARCHING', 'PLANNING', 'ASSIGNED'):
        return {'allow': True, 'kind': 'pre_implementation', 'domain': dom}

    if dom in HARD_BLOCKED_DOMAINS:
        return {
            'allow': False,
            'kind': 'production_gated',
            'error': f"pilot mode: domain '{dom}' is production-impacting",
            'domain': dom,
        }

    if dom in PILOT_ALLOWED_DOMAINS:
        return {
            'allow': True,
            'kind': 'pilot_allowlisted_domain',
            'domain': dom,
            'max_workers': int(st.get('max_concurrent_workers') or 0),
        }

    return {
        'allow': False,
        'kind': 'not_on_pilot_allowlist',
        'error': f"pilot mode: domain '{dom}' not on implementation allowlist",
        'domain': dom,
        'allowlist': sorted(PILOT_ALLOWED_DOMAINS),
    }


def is_weak_verification(commands: list | None, summary: str = '') -> bool:
    blob = ' '.join(str(c) for c in (commands or [])) + ' ' + (summary or '')
    if not blob.strip():
        return False
    for pat in WEAK_VERIFY_PATTERNS:
        if re.search(pat, blob, re.I):
            # Weak if *only* weak signals (no other substantial text)
            cleaned = re.sub('|'.join(WEAK_VERIFY_PATTERNS), '', blob, flags=re.I)
            if len(cleaned.strip()) < 12:
                return True
            if re.search(r'py_compile|compileall|/health', blob, re.I) and not re.search(
                r'test|pytest|acceptance|before|after|metric', blob, re.I
            ):
                return True
    return False


def definition_of_done(
    *,
    domain: str,
    evidence: list | None = None,
    result: str = '',
    peer_reviews: list | None = None,
    research_refs: list | None = None,
    implementation_evidence: dict | None = None,
    layout: Optional[StateLayout] = None,
) -> dict[str, Any]:
    """Machine-checkable close bar for Expansion jobs."""
    st = load_status(layout)
    ev = implementation_evidence if isinstance(implementation_evidence, dict) else {}
    evidence = list(evidence or [])
    reviews = list(peer_reviews or [])
    refs = list(research_refs or [])
    passes = [r for r in reviews if (r.get('verdict') or '').lower() == 'pass']
    fails = [r for r in reviews if (r.get('verdict') or '').lower() == 'fail']

    weak = is_weak_verification(evidence, result)
    checks = {
        'has_evidence': bool(evidence or refs or result.strip()),
        'peer_pass': bool(passes) and not (fails and not passes),
        'non_weak_verify': not weak,
        'result_present': bool((result or '').strip()),
    }

    pilot_scope = (
        st.get('mode') == 'controlled_pilot'
        and domain_key(domain) in PILOT_ALLOWED_DOMAINS
    )
    if pilot_scope:
        has_ba = bool(
            (ev.get('before_state') not in (None, '', {}) and ev.get('after_state') not in (None, '', {}))
            or (ev.get('before_metric') is not None and ev.get('after_metric') is not None)
        )
        # Also accept structured evidence ids tagged before:/after:
        tags = ' '.join(str(x) for x in evidence).lower()
        if 'before:' in tags and 'after:' in tags:
            has_ba = True
        checks['before_after_evidence'] = has_ba

    missing = [k for k, ok in checks.items() if not ok]
    return {
        'passed': not missing,
        'checks': checks,
        'missing': missing,
        'weak_verification': weak,
        'pilot_scope': pilot_scope,
        'evaluated_at': _now(),
    }


def record_pilot_close(
    *,
    job_id: str,
    clean: bool,
    reason: str = '',
    layout: Optional[StateLayout] = None,
) -> dict:
    """Graduation streak: N consecutive clean closes; any dirty resets to 0."""
    st = load_status(layout)
    if st.get('mode') != 'controlled_pilot':
        return st
    streak = int(st.get('pilot_consecutive_clean_closes') or 0)
    history = list(st.get('pilot_close_history') or [])
    streak = streak + 1 if clean else 0
    history.append({
        'job_id': job_id,
        'clean': bool(clean),
        'reason': reason,
        'at': _now(),
    })
    target = int(st.get('pilot_graduation_min') or 3)
    return save_status({
        'pilot_consecutive_clean_closes': streak,
        'pilot_close_history': history[-50:],
        'pilot_graduated': streak >= target,
    }, layout)


def attach_before_after(
    evidence: dict | None = None,
    *,
    before_state: Any = None,
    after_state: Any = None,
    before_metric: Any = None,
    after_metric: Any = None,
) -> dict:
    ev = dict(evidence or {})
    if before_state is not None:
        ev['before_state'] = before_state
    if after_state is not None:
        ev['after_state'] = after_state
    if before_metric is not None:
        ev['before_metric'] = before_metric
    if after_metric is not None:
        ev['after_metric'] = after_metric
    return ev


def auto_rollback_job(
    job_id: str,
    *,
    layout: Optional[StateLayout] = None,
    reason: str = 'verify_failed',
) -> dict:
    """Move job to REWORK and reset pilot streak (dirty close)."""
    layout = layout or resolve_layout()
    st = load_status(layout)
    rolled = False
    if st.get('auto_rollback_enabled', True):
        try:
            from expansion.rex import advance_stage
            advance_stage(
                job_id, 'REWORK', actor='sentry', layout=layout,
                note=f'pilot auto-rollback: {reason}',
            )
            rolled = True
        except Exception as exc:
            return {
                'rolled_back': False,
                'error': str(exc),
                'job_id': job_id,
            }
    record_pilot_close(
        job_id=job_id, clean=False,
        reason=f'auto_rollback:{reason}', layout=layout,
    )
    return {'rolled_back': rolled, 'job_id': job_id, 'reason': reason}


def status_payload(layout: Optional[StateLayout] = None) -> dict:
    st = bootstrap_pilot(layout)
    return {
        'surface': 'pilot_governance',
        'mode': st.get('mode'),
        'active': st.get('active'),
        'allowlist': sorted(PILOT_ALLOWED_DOMAINS),
        'hard_blocked': sorted(HARD_BLOCKED_DOMAINS),
        'graduation': {
            'streak': int(st.get('pilot_consecutive_clean_closes') or 0),
            'min': int(st.get('pilot_graduation_min') or 3),
            'graduated': bool(st.get('pilot_graduated')),
        },
        'freeze_new_proposals': bool(st.get('freeze_new_proposals')),
        'soak_dispatch_halted': bool(st.get('soak_dispatch_halted')),
        'auto_rollback_enabled': bool(st.get('auto_rollback_enabled', True)),
        'updated_at': st.get('updated_at'),
        'note': (
            'Controlled pilot — default-deny implementation allowlist, '
            'before/after DoD, graduation streak, restart-safe bootstrap.'
        ),
    }
