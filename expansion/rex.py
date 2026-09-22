"""Project REX — autonomous work coordination substrate.

Lifecycle (no routine human-approval stage):

  BACKLOG → READY → RESEARCHING → PLANNING → ASSIGNED → IN_PROGRESS
       → VERIFYING → (REWORK | DONE) → optional FOLLOW-UP job

JobStore status remains the durable engine state; REX stage is the agile
projection agents move. WAITING means peer/autonomous verify — not human approval.
"""
from __future__ import annotations

import time
import uuid
from typing import Optional

from expansion.jobs import Job, JobStatus, JobStore, route_domain
from expansion.persist import read_json, update_json
from expansion.policy import PolicyEngine
from expansion.state_layout import StateLayout, resolve_layout

# Agile columns (left → right). No AWAITING_APPROVAL.
REX_STAGES = (
    ('BACKLOG', 'Backlog'),
    ('READY', 'Ready'),
    ('RESEARCHING', 'Researching'),
    ('PLANNING', 'Planning'),
    ('ASSIGNED', 'Assigned'),
    ('IN_PROGRESS', 'In Progress'),
    ('VERIFYING', 'Verifying · Peer Review'),
    ('REWORK', 'Rework'),
    ('DONE', 'Done'),
)

ARCHIVE_STAGES = frozenset({'DONE'})
ACTIVE_STAGES = frozenset({
    'BACKLOG', 'READY', 'RESEARCHING', 'PLANNING', 'ASSIGNED',
    'IN_PROGRESS', 'VERIFYING', 'REWORK',
})
# Hard blockers only — policy escalate / retry budget exhausted.
HARD_BLOCK_STAGE = 'HARD_BLOCKED'

REX_STAGE_TRANSITIONS = {
    'BACKLOG': ('READY', 'CANCELLED'),
    'READY': ('RESEARCHING', 'PLANNING', 'ASSIGNED', 'CANCELLED'),
    'RESEARCHING': ('PLANNING', 'ASSIGNED', 'REWORK', HARD_BLOCK_STAGE),
    'PLANNING': ('ASSIGNED', 'RESEARCHING', HARD_BLOCK_STAGE),
    'ASSIGNED': ('IN_PROGRESS', 'READY', 'CANCELLED'),
    'IN_PROGRESS': ('VERIFYING', 'REWORK', HARD_BLOCK_STAGE),
    'VERIFYING': ('DONE', 'REWORK'),
    'REWORK': ('RESEARCHING', 'PLANNING', 'ASSIGNED', 'IN_PROGRESS'),
    'DONE': (),
    HARD_BLOCK_STAGE: ('REWORK', 'READY', 'CANCELLED'),
    'CANCELLED': ('BACKLOG',),
}

# Map REX stage → JobStatus for living-layer compatibility.
STAGE_TO_JOB_STATUS = {
    'BACKLOG': JobStatus.QUEUED.value,
    'READY': JobStatus.QUEUED.value,
    'RESEARCHING': JobStatus.RUNNING.value,
    'PLANNING': JobStatus.RUNNING.value,
    'ASSIGNED': JobStatus.ASSIGNED.value,
    'IN_PROGRESS': JobStatus.RUNNING.value,
    'VERIFYING': JobStatus.WAITING.value,  # peer verify — not human approval
    'REWORK': JobStatus.FAILED.value,
    'DONE': JobStatus.COMPLETE.value,
    HARD_BLOCK_STAGE: JobStatus.BLOCKED.value,
    'CANCELLED': JobStatus.CANCELLED.value,
}

# Legacy JobStatus → REX stage (migration / jobs without meta).
JOB_STATUS_TO_STAGE = {
    JobStatus.QUEUED.value: 'BACKLOG',
    JobStatus.ASSIGNED.value: 'ASSIGNED',
    JobStatus.RUNNING.value: 'IN_PROGRESS',
    JobStatus.WAITING.value: 'VERIFYING',
    JobStatus.BLOCKED.value: HARD_BLOCK_STAGE,
    JobStatus.FAILED.value: 'REWORK',
    JobStatus.COMPLETE.value: 'DONE',
    JobStatus.CANCELLED.value: 'CANCELLED',
}

DEFAULT_RETRY_BUDGET = 3

# Back-compat aliases used by older tests/UI strings.
REX_COLUMNS = REX_STAGES
ARCHIVE_STATUSES = ARCHIVE_STAGES
ACTIVE_STATUSES = ACTIVE_STAGES
REX_TRANSITIONS = REX_STAGE_TRANSITIONS


def _meta_path(layout: StateLayout):
    layout.user_jobs.mkdir(parents=True, exist_ok=True)
    return layout.user_jobs / 'rex_meta.json'


def _load_meta(layout: StateLayout) -> dict:
    return read_json(_meta_path(layout), default={'schema_version': 1, 'items': {}})


def _update_meta(layout: StateLayout, mut) -> dict:
    return update_json(
        _meta_path(layout), mut,
        default={'schema_version': 1, 'items': {}},
    )


def _default_item(job_id: str, stage: str = 'BACKLOG') -> dict:
    return {
        'job_id': job_id,
        'stage': stage,
        'attempt': 0,
        'retry_budget': DEFAULT_RETRY_BUDGET,
        'discovered_by': '',
        'proposal_source': '',
        'coordination_plan': [],
        'peer_reviews': [],
        'research_refs': [],
        'decision_trace': [],
        'follow_up_of': '',
        'follow_ups': [],
        'updated_at': time.time(),
    }


def get_item(job_id: str, layout: Optional[StateLayout] = None) -> dict:
    layout = layout or resolve_layout()
    items = (_load_meta(layout).get('items') or {})
    return dict(items.get(job_id) or {})


def ensure_item(job: Job, layout: StateLayout) -> dict:
    existing = get_item(job.job_id, layout)
    if existing:
        return existing
    stage = JOB_STATUS_TO_STAGE.get(job.status, 'BACKLOG')
    item = _default_item(job.job_id, stage)

    def _mut(data):
        data = data or {'schema_version': 1, 'items': {}}
        data.setdefault('items', {})
        if job.job_id not in data['items']:
            data['items'][job.job_id] = item
        return data

    _update_meta(layout, _mut)
    return item


def _tone(stage: str) -> str:
    if stage == HARD_BLOCK_STAGE:
        return 'hot'  # rare owner oversight
    if stage in ('REWORK',):
        return 'warn'
    if stage in ('VERIFYING', 'IN_PROGRESS', 'RESEARCHING'):
        return 'info'
    if stage == 'DONE':
        return 'ok'
    return 'muted'


def _owner(job: Job) -> str:
    return job.assigned_agent or job.coordinator or 'unassigned'


def job_to_card(job: Job, layout: Optional[StateLayout] = None) -> dict:
    layout = layout or resolve_layout()
    item = ensure_item(job, layout)
    stage = item.get('stage') or JOB_STATUS_TO_STAGE.get(job.status, 'BACKLOG')
    allowed = list(REX_STAGE_TRANSITIONS.get(stage, ()))
    return {
        'job_id': job.job_id,
        'title': job.request,
        'status': stage,  # board column key
        'stage': stage,
        'job_status': job.status,
        'owner': _owner(job),
        'coordinator': job.coordinator,
        'requester': job.requester,
        'domain': job.domain,
        'priority': job.priority,
        'tone': _tone(stage),
        'result': job.result or '',
        'error': job.error or '',
        'evidence': list(job.evidence or []),
        'event_ids': list(job.event_ids or []),
        'created_at': job.created_at,
        'started_at': job.started_at,
        'completed_at': job.completed_at,
        'confidence': job.confidence,
        'parent_job': job.parent_job or '',
        'child_jobs': list(job.child_jobs or []),
        'allowed_transitions': allowed,
        'archived': stage in ARCHIVE_STAGES or stage == 'CANCELLED',
        'attempt': item.get('attempt', 0),
        'retry_budget': item.get('retry_budget', DEFAULT_RETRY_BUDGET),
        'discovered_by': item.get('discovered_by') or '',
        'proposal_source': item.get('proposal_source') or '',
        'coordination_plan': list(item.get('coordination_plan') or []),
        'peer_reviews': list(item.get('peer_reviews') or []),
        'research_refs': list(item.get('research_refs') or []),
        'decision_trace': list(item.get('decision_trace') or [])[-12:],
        'follow_up_of': item.get('follow_up_of') or '',
        'follow_ups': list(item.get('follow_ups') or []),
        'awaiting_user_approval': False,
    }


def verification_ready(card: dict) -> tuple[bool, str]:
    """Autonomous close requires cross-agent peer pass + research/execution evidence."""
    reviews = card.get('peer_reviews') or []
    passes = [r for r in reviews if r.get('verdict') == 'pass']
    fails = [r for r in reviews if r.get('verdict') == 'fail']
    if fails and not passes:
        return False, 'peer review failed'
    if not passes:
        return False, 'needs peer review pass before close'
    owner = card.get('owner') or ''
    if passes and all(r.get('reviewer') == owner for r in passes):
        return False, 'peer review must be cross-agent'
    if not (card.get('research_refs') or card.get('evidence')):
        return False, 'needs research or execution evidence'
    return True, 'verified'


def _day_start(ts: Optional[float] = None) -> float:
    t = time.localtime(ts or time.time())
    return time.mktime((t.tm_year, t.tm_mon, t.tm_mday, 0, 0, 0, 0, 0, t.tm_isdst))


def build_autonomy_dashboard(layout: Optional[StateLayout] = None, *, limit: int = 200) -> dict:
    layout = layout or resolve_layout()
    store = JobStore(layout)
    jobs = store.list(limit=limit)
    cards = [job_to_card(j, layout) for j in jobs]
    overnight = _day_start()
    completed_overnight = [
        c for c in cards
        if c['stage'] == 'DONE' and (c.get('completed_at') or 0) >= overnight
    ]
    in_progress = [c for c in cards if c['stage'] in ('IN_PROGRESS', 'RESEARCHING', 'PLANNING', 'VERIFYING')]
    hard_blocked = [c for c in cards if c['stage'] == HARD_BLOCK_STAGE]
    newly = [
        c for c in cards
        if c['stage'] in ('BACKLOG', 'READY') and (c.get('created_at') or 0) >= overnight
    ]
    retrying = [c for c in cards if c['stage'] == 'REWORK']
    agents_working = {c['owner'] for c in in_progress if c['owner'] != 'unassigned'}
    world_payload = {}
    route_payload = {}
    try:
        from expansion.route_learning import pool_summary
        from expansion.world_model import get_world_model
        route_payload = pool_summary(layout)
        wm = get_world_model(layout).get_world_state()
        world_payload = {
            'risks': len(wm.get('risks') or []),
            'insights': len(wm.get('insights') or []),
            'domains': len(wm.get('domains') or []),
            'trace_entities': len(wm.get('trace_stats') or {}),
            'global_pool': True,
        }
    except Exception:
        world_payload = {'available': False}
    pilot_payload = None
    try:
        from expansion.pilot_governance import status_payload as pilot_status
        pilot_payload = pilot_status(layout)
    except Exception:
        pilot_payload = None
    return {
        'surface': 'keep_autonomy',
        'model': 'observe_not_approve',
        'note': (
            'Keep Autonomy — agents manage work under policy. '
            'Owner role is oversight and hard-boundary escalation, not routine approval. '
            'KeepRoute/OmniRoute outcomes feed a global learning pool → world model → '
            'world_model:* REX proposals. Controlled pilot gates implementation domains.'
        ),
        'metrics': {
            'agents_working': len(agents_working),
            'jobs_active': len([c for c in cards if c['stage'] in ACTIVE_STAGES]),
            'completed_overnight': len(completed_overnight),
            'completed_today': len(completed_overnight),
            'in_progress': len(in_progress),
            'blocked': len(hard_blocked),
            'newly_discovered': len(newly),
            'failed_retrying': len(retrying),
            'hard_blockers': len(hard_blocked),
            'research_sessions': sum(1 for c in cards if c['stage'] == 'RESEARCHING'),
            'repairs_performed': sum(1 for c in cards if c['stage'] == 'REWORK' or c.get('attempt', 0) > 0),
            'world_model_risks': world_payload.get('risks', 0),
            'route_learning_records': route_payload.get('records', 0),
            'pilot_streak': (pilot_payload or {}).get('graduation', {}).get('streak', 0),
        },
        'agents_working_ids': sorted(agents_working),
        'hard_blockers': hard_blocked[:12],
        'policy': PolicyEngine(layout).summary(),
        'world_model': world_payload,
        'route_learning': route_payload,
        'pilot': pilot_payload,
    }


def build_rex_board(layout: Optional[StateLayout] = None, *, limit: int = 200) -> dict:
    layout = layout or resolve_layout()
    store = JobStore(layout)
    jobs = store.list(limit=limit)
    cards = [job_to_card(j, layout) for j in jobs]

    columns = []
    for stage, label in REX_STAGES:
        col_cards = [c for c in cards if c['stage'] == stage]
        columns.append({
            'status': stage,
            'stage': stage,
            'label': label,
            'archived': stage in ARCHIVE_STAGES,
            'count': len(col_cards),
            'cards': col_cards,
        })
    # Hard blocked lane (oversight only) — not a routine column.
    hb = [c for c in cards if c['stage'] == HARD_BLOCK_STAGE]
    if hb:
        columns.append({
            'status': HARD_BLOCK_STAGE,
            'stage': HARD_BLOCK_STAGE,
            'label': 'Hard Blocked',
            'archived': False,
            'oversight_only': True,
            'count': len(hb),
            'cards': hb,
        })

    by_owner: dict = {}
    for c in cards:
        if c['archived'] or c['stage'] == 'CANCELLED':
            continue
        by_owner.setdefault(c['owner'], 0)
        by_owner[c['owner']] += 1

    autonomy = build_autonomy_dashboard(layout, limit=limit)
    return {
        'surface': 'project_rex',
        'model': 'autonomous_work_system',
        'note': (
            'Project REX — autonomous coordination substrate. '
            'Aria coordinates; domain agents move their own cards under policy. '
            'No routine awaiting-user-approval stage.'
        ),
        'loop': [
            'discover', 'research', 'plan', 'assign', 'execute',
            'verify', 'repair', 'document', 'close', 'follow_up',
        ],
        'columns': columns,
        'metrics': autonomy['metrics'],
        'autonomy': autonomy,
        'value_signals': {
            'hard_blockers': hb[:8],
            'rework': [c for c in cards if c['stage'] == 'REWORK'][:8],
            'verifying': [c for c in cards if c['stage'] == 'VERIFYING'][:8],
            'discovered': [c for c in cards if c['stage'] in ('BACKLOG', 'READY')][:8],
        },
        'filters': [s for s, _ in REX_STAGES] + [
            HARD_BLOCK_STAGE, 'ALL', 'ACTIVE', 'ARCHIVE',
        ],
        'roles': PolicyEngine(layout).summary()['roles'],
    }


def _append_trace(item: dict, actor: str, action: str, detail: str = '') -> None:
    trace = list(item.get('decision_trace') or [])
    trace.append({
        'at': time.time(),
        'actor': actor,
        'action': action,
        'detail': detail,
    })
    item['decision_trace'] = trace[-40:]
    item['updated_at'] = time.time()


def queue_rex_job(
    request: str,
    *,
    domain: str = 'coordination',
    layout: Optional[StateLayout] = None,
    assigned_agent: Optional[str] = None,
    discovered_by: str = '',
    stage: str = 'BACKLOG',
    priority: int = 5,
    parent_job: str = '',
    coordination_plan: Optional[list] = None,
    proposal_source: str = '',
) -> Job:
    """Create work in BACKLOG/READY — agents discover; humans rarely queue."""
    layout = layout or resolve_layout()
    store = JobStore(layout)
    job = store.create(
        request,
        domain=domain,
        assigned_agent=assigned_agent,
        priority=priority,
        parent_job=parent_job,
        requester=discovered_by or 'system',
        coordinator='aria',
    )
    item = _default_item(job.job_id, stage if stage in dict(REX_STAGES) or stage == HARD_BLOCK_STAGE else 'BACKLOG')
    item['discovered_by'] = discovered_by or ''
    if proposal_source:
        item['proposal_source'] = str(proposal_source)
    if coordination_plan:
        item['coordination_plan'] = list(coordination_plan)
    if parent_job:
        item['follow_up_of'] = parent_job
    _append_trace(item, discovered_by or 'system', 'discover', request[:160])

    def _mut(data):
        data = data or {'schema_version': 1, 'items': {}}
        data.setdefault('items', {})
        data['items'][job.job_id] = item
        if parent_job and parent_job in data['items']:
            parent = data['items'][parent_job]
            fus = list(parent.get('follow_ups') or [])
            if job.job_id not in fus:
                fus.append(job.job_id)
            parent['follow_ups'] = fus
        return data

    _update_meta(layout, _mut)
    # Align JobStatus with stage
    target = STAGE_TO_JOB_STATUS.get(item['stage'], JobStatus.QUEUED.value)
    if target != job.status:
        job = store.transition(job.job_id, target)
    return job


def discover_work(
    actor: str,
    request: str,
    *,
    domain: str = '',
    layout: Optional[StateLayout] = None,
    priority: int = 5,
    assigned_agent: Optional[str] = None,
    proposal_source: str = '',
) -> Job:
    """Agent observes a problem and creates REX work under policy."""
    layout = layout or resolve_layout()
    PolicyEngine(layout).require(actor, 'jobs.discover')
    dom = domain or (
        'security' if actor == 'sentry' else
        'infrastructure' if actor == 'vector' else
        'records' if actor == 'ledger' else
        'creative' if actor == 'muse' else
        'coordination'
    )
    return queue_rex_job(
        request,
        domain=dom,
        layout=layout,
        assigned_agent=assigned_agent or route_domain(dom),
        discovered_by=actor,
        stage='BACKLOG',
        priority=priority,
        proposal_source=proposal_source,
    )


def set_coordination_plan(
    job_id: str,
    plan: list,
    *,
    actor: str = 'aria',
    layout: Optional[StateLayout] = None,
) -> dict:
    layout = layout or resolve_layout()
    PolicyEngine(layout).require(actor, 'jobs.assign')
    holder = {'item': None}

    def _mut(data):
        data = data or {'schema_version': 1, 'items': {}}
        items = data.setdefault('items', {})
        item = items.get(job_id) or _default_item(job_id)
        item['coordination_plan'] = list(plan)
        _append_trace(item, actor, 'plan', f'{len(plan)} steps')
        items[job_id] = item
        holder['item'] = item
        return data

    _update_meta(layout, _mut)
    return holder['item']


def advance_stage(
    job_id: str,
    new_stage: str,
    *,
    actor: str,
    layout: Optional[StateLayout] = None,
    note: str = '',
    assign_to: Optional[str] = None,
) -> Job:
    """Agent-driven card move. Policy-gated; no human approval hop."""
    layout = layout or resolve_layout()
    store = JobStore(layout)
    job = store.get(job_id)
    if job is None:
        raise KeyError(job_id)

    PolicyEngine(layout).require(actor, 'jobs.move')
    item = ensure_item(job, layout)
    cur = item.get('stage') or JOB_STATUS_TO_STAGE.get(job.status, 'BACKLOG')
    allowed = REX_STAGE_TRANSITIONS.get(cur, ())
    if new_stage not in allowed:
        raise ValueError(
            f'invalid stage transition {cur} → {new_stage}; allowed={list(allowed)}'
        )

    if new_stage == 'REWORK':
        item['attempt'] = int(item.get('attempt') or 0) + 1
        budget = int(item.get('retry_budget') or DEFAULT_RETRY_BUDGET)
        if item['attempt'] >= budget:
            new_stage = HARD_BLOCK_STAGE
            note = (note or '') + f' (retry budget {budget} exhausted → escalate)'

    if assign_to:
        PolicyEngine(layout).require(actor, 'jobs.assign')

    if new_stage == 'DONE':
        card = {
            'peer_reviews': list(item.get('peer_reviews') or []),
            'research_refs': list(item.get('research_refs') or []),
            'evidence': list(job.evidence or []),
            'owner': job.assigned_agent or job.coordinator or '',
        }
        ok, reason = verification_ready(card)
        if not ok:
            raise ValueError(f'cannot close: {reason}')

    item['stage'] = new_stage
    _append_trace(item, actor, 'advance', f'{cur}→{new_stage}' + (f' {note}' if note else ''))

    def _mut(data):
        data = data or {'schema_version': 1, 'items': {}}
        data.setdefault('items', {})[job_id] = item
        return data

    _update_meta(layout, _mut)

    job_status = STAGE_TO_JOB_STATUS.get(new_stage, JobStatus.RUNNING.value)
    kwargs = {}
    if note and new_stage in ('REWORK', HARD_BLOCK_STAGE):
        kwargs['error'] = note
    if note and new_stage == 'DONE':
        kwargs['result'] = note
    if assign_to:
        job = store.get(job_id)
        job.assigned_agent = assign_to
        store.update(job)

    return store.transition(job_id, job_status, **kwargs)


def transition_rex_job(
    job_id: str,
    new_status: str,
    *,
    layout: Optional[StateLayout] = None,
    note: str = '',
    actor: str = 'aria',
) -> Job:
    """UI/API compatibility: accept stage name or legacy JobStatus."""
    layout = layout or resolve_layout()
    stage = new_status
    if new_status in JOB_STATUS_TO_STAGE and new_status not in dict(REX_STAGES):
        # Map legacy status button to stage
        stage = JOB_STATUS_TO_STAGE[new_status]
        if new_status == JobStatus.QUEUED.value:
            stage = 'BACKLOG'
        elif new_status == JobStatus.RUNNING.value:
            stage = 'IN_PROGRESS'
        elif new_status == JobStatus.WAITING.value:
            stage = 'VERIFYING'
        elif new_status == JobStatus.FAILED.value:
            stage = 'REWORK'
        elif new_status == JobStatus.COMPLETE.value:
            stage = 'DONE'
        elif new_status == JobStatus.BLOCKED.value:
            stage = HARD_BLOCK_STAGE
    return advance_stage(job_id, stage, actor=actor, layout=layout, note=note)


def add_peer_review(
    job_id: str,
    *,
    reviewer: str,
    verdict: str,
    note: str = '',
    layout: Optional[StateLayout] = None,
) -> dict:
    layout = layout or resolve_layout()
    PolicyEngine(layout).require(reviewer, 'jobs.verify')
    holder = {'item': None}

    def _mut(data):
        data = data or {'schema_version': 1, 'items': {}}
        items = data.setdefault('items', {})
        job = JobStore(layout).get(job_id)
        item = items.get(job_id) or (
            ensure_item(job, layout) if job else _default_item(job_id)
        )
        reviews = list(item.get('peer_reviews') or [])
        reviews.append({
            'review_id': f'rev_{uuid.uuid4().hex[:8]}',
            'reviewer': reviewer,
            'verdict': verdict,  # pass | fail | abstain
            'note': note,
            'at': time.time(),
        })
        item['peer_reviews'] = reviews[-20:]
        _append_trace(item, reviewer, 'peer_review', f'{verdict}: {note[:120]}')
        items[job_id] = item
        holder['item'] = item
        return data

    _update_meta(layout, _mut)
    return holder['item']


def close_with_follow_up(
    job_id: str,
    *,
    actor: str,
    result: str = '',
    follow_up_request: str = '',
    follow_up_domain: str = '',
    layout: Optional[StateLayout] = None,
) -> dict:
    layout = layout or resolve_layout()
    job = advance_stage(job_id, 'DONE', actor=actor, layout=layout, note=result)
    follow = None
    if follow_up_request:
        parent = JobStore(layout).get(job_id)
        follow = queue_rex_job(
            follow_up_request,
            domain=follow_up_domain or (parent.domain if parent else 'coordination'),
            layout=layout,
            discovered_by=actor,
            stage='BACKLOG',
            parent_job=job_id,
        )
    return {'job': job, 'follow_up': follow}
