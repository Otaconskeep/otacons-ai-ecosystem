"""Controlled-pilot REX governance for Expansion Premium (clean-room).

Ports the *intent* of Keep ``autonomous/rex_recovery.py`` on 192.168.50.219
(incl. 2026-09-22 sandbox capability widening) — not a verbatim copy:

  - default-deny domain allowlist for autonomous implementation
  - hard-blocked production domains
  - sandbox-research capability widening (request-text proof, not domain grant)
  - DoD requiring before/after + research deliverables on pilot work
  - graduation streak (N clean closes; rollback / poison scrub resets)
  - bootstrap that *preserves* pilot mode across restarts (no silent re-freeze)

Persists under user_jobs/pilot_governance.json.
"""
from __future__ import annotations

import re
import time
from pathlib import Path
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
    r'RAW AGENT OUTPUT',
)

# Keep 2026-09-22 capability widening (clean-room): sandbox-only research may
# dispatch outside the domain allowlist when the request text proves it.
_SANDBOX_DESTRUCTIVE_RE = re.compile(
    r'\b(delete|drop\s+table|drop\s+database|rm\s+-rf|destroy|purge|format|'
    r'truncate|wipe|overwrite\s+production|revoke|delete\s+user)\b',
    re.I,
)
_SANDBOX_CREDNET_RE = re.compile(
    r'\b(credential|password|api[- ]?key|firewall|nftables|iptables|\bdns\b|'
    r'ssl\s+cert|tls\s+cert|auth[ .-]?token|oauth\s+secret|production\s+deploy)\b',
    re.I,
)

# Domains whose close bar requires research_refs (not just repo.search + journal).
RESEARCH_OUTCOME_DOMAINS = frozenset({
    'research',
    'records',
    'continuity',
    'documentation',
})

# Evidence ids that only track pilot bookkeeping — never alone prove an outcome.
_BOOKKEEPING_EVIDENCE_PREFIXES = ('before:', 'after:', 'review:')


def substantive_evidence_ids(evidence: list | None) -> list[str]:
    """Return evidence ids that are not before:/after:/review: bookkeeping tags."""
    out: list[str] = []
    for raw in evidence or []:
        s = str(raw or '').strip()
        if not s:
            continue
        low = s.lower()
        if low.startswith(_BOOKKEEPING_EVIDENCE_PREFIXES):
            continue
        out.append(s)
    return out

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


# Known pre-fix fake closes that graduated the streak without outcome evidence.
_KNOWN_POISONED_CLOSE_JOBS = frozenset({
    'job_c6539bce2e',
})


def _recompute_clean_streak(history: list) -> int:
    streak = 0
    for entry in history or []:
        if entry.get('clean'):
            streak += 1
        else:
            streak = 0
    return streak


def scrub_poisoned_pilot_closes(layout: Optional[StateLayout] = None) -> dict:
    """Invalidate pre-DoD-v2 fake clean closes so they cannot graduate the pilot.

    One-shot (``poison_scrub_v1``). Marks known poison job ids dirty, and any
    still-on-disk job whose close left confidence≤0 / only bookkeeping evidence.
    """
    layout = layout or resolve_layout()
    st = load_status(layout)
    if st.get('poison_scrub_v1'):
        return st
    history = [dict(e) for e in (st.get('pilot_close_history') or [])]
    changed = False
    store = None
    try:
        from expansion.jobs import JobStore
        store = JobStore(layout)
    except Exception:
        store = None

    for entry in history:
        if not entry.get('clean'):
            continue
        jid = str(entry.get('job_id') or '')
        poison = jid in _KNOWN_POISONED_CLOSE_JOBS
        if not poison and store and jid:
            try:
                job = store.get(jid)
            except Exception:
                job = None
            if job is not None:
                conf = float(getattr(job, 'confidence', 0) or 0)
                ev = list(getattr(job, 'evidence', None) or [])
                tags = ' '.join(str(x) for x in ev).lower()
                substantive = substantive_evidence_ids(ev)
                if conf <= 0.0 and 'before:evidence=0' in tags:
                    poison = True
                elif not substantive and conf <= 0.0:
                    poison = True
        if poison:
            entry['clean'] = False
            entry['reason'] = 'scrubbed:pre_dod_v2_fake_close'
            entry['scrubbed'] = True
            changed = True

    streak = int(st.get('pilot_consecutive_clean_closes') or 0)
    if changed:
        # After invalidating a clean close, recompute trailing streak from history.
        streak = _recompute_clean_streak(history)
    target = int(st.get('pilot_graduation_min') or 3)
    updates = {
        'poison_scrub_v1': True,
        'pilot_close_history': history[-50:],
        'pilot_consecutive_clean_closes': streak,
        'pilot_graduated': streak >= target if changed else bool(st.get('pilot_graduated')),
    }
    if changed:
        updates['poison_scrub_at'] = _now()
        updates['pilot_graduated'] = streak >= target
    return save_status(updates, layout)


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
        # Preserve operator-approved pilot state across restarts, but scrub
        # any pre-fix fake closes that are still counting toward graduation.
        scrub_poisoned_pilot_closes(layout)
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


def sandbox_research_capability(
    request: str = '',
    *,
    item: dict | None = None,
) -> tuple[bool, str]:
    """Keep 2026-09-22 clean-room: prove sandbox-only research independent of domain.

    Requires explicit sandbox scope, no destructive/cred/net language, baseline,
    measurable criteria, rollback, and a peer/sandbox review mark.
    """
    text = (request or '').lower()
    item = item if isinstance(item, dict) else {}
    if (
        'no production mutation' not in text
        and 'sandbox/test only' not in text
        and 'sandbox only' not in text
    ):
        return False, 'not_explicitly_scoped_sandbox_only'
    if _SANDBOX_DESTRUCTIVE_RE.search(text):
        return False, 'destructive_action_language_present'
    if _SANDBOX_CREDNET_RE.search(text):
        return False, 'touches_credentials_network_or_security'
    if 'baseline' not in text:
        return False, 'no_baseline_captured'
    if not any(k in text for k in ('expected result', 'verification:', 'measurable')):
        return False, 'no_measurable_success_criteria'
    if 'rollback' not in text:
        return False, 'no_rollback_plan'
    reviews = item.get('peer_reviews') or []
    reviewed = bool(item.get('sandbox_reviewed')) or any(
        (r.get('verdict') or '').lower() == 'pass' for r in reviews if isinstance(r, dict)
    )
    if not reviewed:
        return False, 'awaiting_peer_or_sandbox_review'
    return True, 'sandbox_research_capability_ok'


def dispatch_gate(
    *,
    domain: str,
    stage: str = 'IN_PROGRESS',
    layout: Optional[StateLayout] = None,
    request: str = '',
    item: dict | None = None,
) -> dict[str, Any]:
    """Default-deny implementation dispatch under controlled_pilot.

    Mirrors Keep ``rex_recovery.dispatch_gate`` (2026-09-22): allowlisted domains
    plus sandbox-research capability widening — never a broad domain grant.
    """
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
        # Capability widening (Keep 2026-09-22): hard-blocked domains may still
        # run when the job text proves sandbox-only research with peer review.
        cap_ok, cap_reason = sandbox_research_capability(request, item=item)
        if cap_ok:
            return {
                'allow': True,
                'kind': 'pilot_sandbox_capability',
                'domain': dom,
                'capability_reason': cap_reason,
                'max_workers': int(st.get('max_concurrent_workers') or 0),
            }
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

    # Non-allowlisted, non-hard-blocked: still try sandbox capability.
    cap_ok, cap_reason = sandbox_research_capability(request, item=item)
    if cap_ok:
        return {
            'allow': True,
            'kind': 'pilot_sandbox_capability',
            'domain': dom,
            'capability_reason': cap_reason,
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
    """Keep-aligned: empty / theater-only verification never satisfies DoD."""
    blob = ' '.join(str(c) for c in (commands or [])) + ' ' + (summary or '')
    if not blob.strip() or blob.strip() in ('[]', '{}'):
        return True
    if 'RAW AGENT OUTPUT' in blob:
        return True
    for pat in WEAK_VERIFY_PATTERNS:
        if re.search(pat, blob, re.I):
            # Weak if *only* weak signals (no other substantial text)
            cleaned = re.sub('|'.join(WEAK_VERIFY_PATTERNS), '', blob, flags=re.I)
            if len(cleaned.strip()) < 12:
                return True
            if re.search(r'py_compile|compileall|/health', blob, re.I) and not re.search(
                r'test|pytest|acceptance|before|after|metric|deliverable', blob, re.I
            ):
                return True
    return False


def demote_research_without_deliverable(card: dict) -> tuple[dict, bool]:
    """Keep rex_completion clean-room: research 'DONE' without deliverable ≠ shipped."""
    card = dict(card or {})
    domain = domain_key(card.get('domain') or '')
    if domain not in RESEARCH_OUTCOME_DOMAINS:
        return card, False
    if (card.get('stage') or '') != 'DONE':
        return card, False
    evidence = list(card.get('evidence') or [])
    ev = card.get('implementation_evidence') if isinstance(card.get('implementation_evidence'), dict) else {}
    result = (card.get('result') or '').strip()
    has_deliverable = bool(
        ev.get('deliverable_path')
        or any(str(x).startswith('deliverable:') for x in evidence)
        or (len(result) >= 80 and not result.lower().startswith('autonomous close'))
    )
    if has_deliverable and (card.get('research_refs') or []):
        return card, False
    card['stage'] = 'REWORK'
    card['completion_correction'] = {
        'previous_status': 'DONE',
        'reason': 'Research acceptance does not establish a deliverable.',
    }
    card['implementation_pending'] = True
    return card, True


def definition_of_done(
    *,
    domain: str,
    evidence: list | None = None,
    result: str = '',
    peer_reviews: list | None = None,
    research_refs: list | None = None,
    implementation_evidence: dict | None = None,
    confidence: float | None = None,
    layout: Optional[StateLayout] = None,
) -> dict[str, Any]:
    """Machine-checkable close bar for Expansion jobs.

    Artifact/outcome evidence is required. Bookkeeping tags
    (``before:`` / ``after:`` / ``review:``) and a bare result string
    never alone satisfy DoD — that blocked the fake
    ``repo.search('journal')`` → journal → ``dod_passed`` streak path.
    """
    st = load_status(layout)
    ev = implementation_evidence if isinstance(implementation_evidence, dict) else {}
    evidence = list(evidence or [])
    reviews = list(peer_reviews or [])
    refs = list(research_refs or [])
    substantive = substantive_evidence_ids(evidence)
    passes = [r for r in reviews if (r.get('verdict') or '').lower() == 'pass']
    fails = [r for r in reviews if (r.get('verdict') or '').lower() == 'fail']
    dom = domain_key(domain)

    weak = is_weak_verification(evidence, result)
    checks = {
        # Outcome evidence only — not before:/after: tags or empty narration.
        'has_evidence': bool(substantive or refs),
        'peer_pass': bool(passes) and not (fails and not passes),
        'non_weak_verify': not weak,
        'result_present': bool((result or '').strip()),
    }
    if dom in RESEARCH_OUTCOME_DOMAINS:
        checks['research_outcome'] = bool(refs)
        result_l = (result or '').strip().lower()
        status_only = (
            not result_l
            or result_l.startswith('executed ')
            or (
                result_l.startswith('autonomous close')
                and 'deliverable:' not in result_l
                and '## answers' not in result_l
            )
        )
        has_deliverable = bool(
            (ev.get('deliverable_path') and ev.get('synthesis_ok') is not False)
            or any(str(x).startswith('deliverable:') for x in evidence)
            or (not status_only and '## answers' in result_l)
        )
        # Link-dump / chrome-only files must not pass (Keep: research ≠ shipped).
        if ev.get('synthesis_ok') is False:
            has_deliverable = False
        if has_deliverable and ev.get('deliverable_path'):
            try:
                body = Path(str(ev['deliverable_path'])).read_text(encoding='utf-8')
                if 'Next: turn sourced notes into an actionable plan' in body:
                    has_deliverable = False
                if '## Answers' not in body:
                    has_deliverable = False
            except Exception:
                pass
        checks['deliverable'] = has_deliverable

    # Derived confidence — job.confidence defaults to 0.0 and was never written,
    # so we score from artifacts. Explicit confidence<=0 from caller still fails.
    derived_confidence = 0.0
    if refs:
        derived_confidence += 0.50
    if substantive:
        derived_confidence += 0.35
    if passes:
        derived_confidence += 0.15
    derived_confidence = round(min(1.0, derived_confidence), 3)
    if confidence is not None and float(confidence) > 0.0:
        derived_confidence = max(derived_confidence, float(confidence))
    checks['confidence_positive'] = derived_confidence > 0.0

    pilot_scope = (
        st.get('mode') == 'controlled_pilot'
        and dom in PILOT_ALLOWED_DOMAINS
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
        # Research lane with zero prior evidence and no research_refs = fake close
        # (the journal-only continuity path).
        before_m = ev.get('before_metric')
        if before_m == 0 and not refs and dom in RESEARCH_OUTCOME_DOMAINS:
            checks['outcome_delta'] = False

    missing = [k for k, ok in checks.items() if not ok]
    return {
        'passed': not missing,
        'checks': checks,
        'missing': missing,
        'weak_verification': weak,
        'pilot_scope': pilot_scope,
        'derived_confidence': derived_confidence,
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
