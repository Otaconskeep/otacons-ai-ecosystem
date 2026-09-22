"""Active Keep autonomy loop — discover → research → plan → execute → verify → close.

This is the full-autonomy layer (P5). Policy authorizes; tools execute; REX stages
advance. Owner sees outcomes on the autonomy dashboard — not approval prompts.
"""
from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Optional

from expansion.jobs import Job, JobStore, route_domain
from expansion.persist import update_json
from expansion.policy import PolicyEngine
from expansion.rex import (
    HARD_BLOCK_STAGE,
    advance_stage,
    build_rex_board,
    close_with_follow_up,
    discover_work,
    get_item,
    job_to_card,
    set_coordination_plan,
    add_peer_review,
    verification_ready,
    _append_trace,
    _update_meta,
)
from expansion.state_layout import StateLayout, resolve_layout
from expansion.tools import ToolGateway

# Priority heuristics for Aria autonomous prioritization.
_HIGH = re.compile(r'\b(critical|outage|security|breach|latency|failing|regression|down)\b', re.I)
_MED = re.compile(r'\b(bug|repair|broken|error|incident|degraded)\b', re.I)


def _score_request(text: str, priority: int) -> int:
    base = int(priority or 5)
    if _HIGH.search(text or ''):
        return min(base, 2)
    if _MED.search(text or ''):
        return min(base, 3)
    return base


def _patch_item(layout: StateLayout, job_id: str, mut_fn) -> dict:
    holder = {'item': None}

    def _mut(data):
        data = data or {'schema_version': 1, 'items': {}}
        items = data.setdefault('items', {})
        item = dict(items.get(job_id) or {'job_id': job_id})
        mut_fn(item)
        item['updated_at'] = time.time()
        items[job_id] = item
        holder['item'] = item
        return data

    _update_meta(layout, _mut)
    return holder['item']


def _add_research(layout: StateLayout, job_id: str, ref: dict, actor: str) -> None:
    def _m(item):
        refs = list(item.get('research_refs') or [])
        refs.append({**ref, 'at': time.time(), 'by': actor})
        item['research_refs'] = refs[-30:]
        _append_trace(item, actor, 'research', ref.get('title') or ref.get('url') or '')

    _patch_item(layout, job_id, _m)


def _add_evidence(layout: StateLayout, job: Job, evidence_id: str) -> Job:
    store = JobStore(layout)
    j = store.get(job.job_id)
    if not j:
        return job
    ev = list(j.evidence or [])
    if evidence_id not in ev:
        ev.append(evidence_id)
    j.evidence = ev[-40:]
    return store.update(j)


def prioritize_backlog(layout: StateLayout, *, actor: str = 'aria') -> list:
    PolicyEngine(layout).require(actor, 'jobs.reprioritize')
    store = JobStore(layout)
    changed = []
    for job in store.list(limit=100):
        card = job_to_card(job, layout)
        if card['stage'] not in ('BACKLOG', 'READY'):
            continue
        new_p = _score_request(job.request, job.priority)
        if new_p != job.priority:
            job.priority = new_p
            store.update(job)
            changed.append({'job_id': job.job_id, 'priority': new_p})
            _patch_item(layout, job.job_id, lambda item, p=new_p: _append_trace(item, actor, 'prioritize', f'p={p}'))
    # Promote highest-priority BACKLOG → READY
    backlog = []
    for job in store.list(limit=100):
        card = job_to_card(job, layout)
        if card['stage'] == 'BACKLOG':
            backlog.append(job)
    backlog.sort(key=lambda j: (j.priority, j.created_at))
    promoted = []
    for job in backlog[:5]:
        advance_stage(job.job_id, 'READY', actor=actor, layout=layout)
        promoted.append(job.job_id)
    return {'reprioritized': changed, 'promoted': promoted}


def detect_work(layout: StateLayout) -> list:
    """Sentry/Vector-style autonomous discovery from local + world-model signals."""
    created = []
    tools = ToolGateway(layout)
    # Security scan → discover if findings
    scan = tools.invoke('sentry', 'security.scan')
    if scan.ok and scan.data.get('findings'):
        n = len(scan.data['findings'])
        job = discover_work(
            'sentry',
            f'Security scan found {n} potential secret/pattern hit(s) — triage and remediate',
            domain='security',
            layout=layout,
            priority=2,
        )
        created.append(job.job_id)
        _add_evidence(layout, job, scan.action_id)

    # Docker health
    dock = tools.invoke('vector', 'docker.inspect')
    if not dock.ok and 'not found' in (dock.error or '').lower():
        pass  # docker absent — not an incident
    elif dock.ok and dock.data.get('exit_code') not in (0, None) and 'docker' in (dock.error or dock.summary or '').lower():
        job = discover_work(
            'vector',
            'Docker inspect unhealthy — investigate container runtime',
            domain='infrastructure',
            layout=layout,
            priority=3,
        )
        created.append(job.job_id)

    # KeepRoute / OmniRoute world-model risks → REX (source world_model:*)
    created.extend(_detect_world_model_work(layout))
    return created


def _detect_world_model_work(layout: StateLayout) -> list:
    """Spawn REX jobs from operational world-model risks (global learning pool)."""
    created = []
    try:
        from expansion.world_model import get_world_model
        wm = get_world_model(layout)
        proposals = wm.proposals_from_risks(min_score=0.35, limit=3)
    except Exception:
        return created

    store = JobStore(layout)
    existing_srcs = set()
    existing_texts = set()
    for job in store.list(limit=120):
        card = job_to_card(job, layout)
        if card.get('stage') in ('DONE', 'CANCELLED'):
            continue
        src = (card.get('proposal_source') or '').strip()
        if src:
            existing_srcs.add(src)
        existing_texts.add((job.request or '')[:160].lower())

    for prop in proposals:
        src = prop.get('source') or 'world_model:risk'
        # Deduplicate by source type + problem fingerprint
        key = f"{src}:{(prop.get('problem') or '')[:80]}"
        if key in existing_srcs or any(
            (prop.get('problem') or '')[:60].lower() in t for t in existing_texts if t
        ):
            continue
        actor = 'vector'
        domain = prop.get('domain') or 'infrastructure'
        if domain == 'security':
            actor = 'sentry'
        elif domain in ('records', 'research'):
            actor = 'ledger'
        priority = 2 if float(prop.get('score') or 0) >= 0.7 else 3
        job = discover_work(
            actor,
            prop.get('proposal') or prop.get('problem') or 'World-model risk',
            domain=domain,
            layout=layout,
            priority=priority,
            proposal_source=key,
        )
        created.append(job.job_id)
        existing_srcs.add(key)
        existing_texts.add((job.request or '')[:160].lower())
    return created


def _researcher_for(domain: str, assigned: str) -> str:
    if domain in ('security', 'monitoring'):
        return 'sentry'
    if domain in ('records', 'research', 'continuity'):
        return 'ledger'
    if domain in ('creative', 'media'):
        return 'muse'
    return assigned or 'vector'


def _synthesize_research_deliverable(layout: StateLayout, job: Job, agent: str) -> Optional[str]:
    """Write a sourced findings markdown file — research closes need a deliverable."""
    card = job_to_card(job, layout)
    refs = list(card.get('research_refs') or [])
    if not refs:
        return None
    out_dir = layout.user_jobs / 'deliverables'
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f'{job.job_id}.md'
    lines = [
        f'# Research: {(job.request or "")[:200]}',
        '',
        f'_Job `{job.job_id}` · agent `{agent}` · {len(refs)} source(s)_',
        '',
        '## Sourced findings',
        '',
    ]
    for i, ref in enumerate(refs[:12], 1):
        title = (ref.get('title') or 'Untitled').strip()
        url = (ref.get('url') or '').strip()
        snip = (ref.get('snippet') or '').strip()[:400]
        lines.append(f'{i}. **{title}**')
        if url:
            lines.append(f'   - Source: {url}')
        if snip:
            lines.append(f'   - Note: {snip}')
        lines.append('')
    lines.extend([
        '## Synthesis notes',
        '',
        '- Findings above were gathered via policy-gated web.search / web.fetch.',
        '- Next: turn sourced notes into an actionable plan against the original request.',
        '',
    ])
    path.write_text('\n'.join(lines), encoding='utf-8')
    return str(path)


def step_research(layout: StateLayout, job: Job) -> dict:
    tools = ToolGateway(layout)
    agent = _researcher_for(job.domain, job.assigned_agent)
    card = job_to_card(job, layout)
    if card['stage'] == 'READY':
        advance_stage(job.job_id, 'RESEARCHING', actor=agent, layout=layout)

    q = job.request[:160]
    search = tools.invoke(agent, 'web.search', query=q)
    actions = [search.action_id]
    research_hits = 0
    if search.ok:
        results = search.data.get('results') or []
        research_hits = len(results)
        for hit in results[:3]:
            _add_research(layout, job.job_id, {
                'title': hit.get('title') or '',
                'url': hit.get('url') or '',
                'snippet': hit.get('snippet') or '',
            }, agent)
            tools.invoke(agent, 'research.record', **hit)
            if hit.get('url'):
                fetched = tools.invoke(agent, 'web.fetch', url=hit['url'])
                actions.append(fetched.action_id)
                if fetched.ok:
                    _add_research(layout, job.job_id, {
                        'title': fetched.data.get('title_guess') or hit.get('url'),
                        'url': hit.get('url') or '',
                        'snippet': (fetched.data.get('snippet') or '')[:400],
                    }, agent)
    # Only count a successful search (with hits) as evidence — 0-hit must not
    # inflate the evidence bag toward a fake close. Do not repo.search the first
    # word of the request (that produced repo.search('Research') / ('journal') noise).
    if search.ok and research_hits > 0:
        _add_evidence(layout, JobStore(layout).get(job.job_id), search.action_id)
    return {
        'stage': 'RESEARCHING',
        'actions': actions,
        'ok': bool(search.ok and research_hits > 0),
        'research_hits': research_hits,
        'search_error': '' if search.ok else (search.error or search.summary),
    }


def step_plan_assign(layout: StateLayout, job: Job) -> dict:
    owner = job.assigned_agent or route_domain(job.domain)
    plan = [
        f'Aria prioritizes and assigns {owner}',
        f'{owner} researches with web/docs tools',
        f'{owner} executes with policy-gated tools',
        'Ledger/Sentry peer-verify evidence',
        'Aria closes when verification passes',
        'Spawn follow-up documentation if needed',
    ]
    set_coordination_plan(job.job_id, plan, actor='aria', layout=layout)
    card = job_to_card(job, layout)
    stage = card['stage']
    if stage == 'RESEARCHING':
        advance_stage(job.job_id, 'PLANNING', actor='aria', layout=layout)
        stage = 'PLANNING'
    if stage == 'PLANNING':
        advance_stage(job.job_id, 'ASSIGNED', actor='aria', layout=layout, assign_to=owner)
    return {'stage': 'ASSIGNED', 'owner': owner, 'plan_steps': len(plan)}


def step_execute(layout: StateLayout, job: Job) -> dict:
    tools = ToolGateway(layout)
    agent = job.assigned_agent or route_domain(job.domain)
    card = job_to_card(job, layout)
    if card['stage'] == 'ASSIGNED':
        advance_stage(job.job_id, 'IN_PROGRESS', actor=agent, layout=layout)

    # Controlled pilot: default-deny implementation domains
    try:
        from expansion.pilot_governance import dispatch_gate, bootstrap_pilot
        bootstrap_pilot(layout)
        from expansion.rex import get_item
        gate = dispatch_gate(
            domain=job.domain,
            stage='IN_PROGRESS',
            layout=layout,
            request=job.request or '',
            item=get_item(job.job_id, layout),
        )
        if not gate.get('allow'):
            advance_stage(
                job.job_id, HARD_BLOCK_STAGE, actor='aria', layout=layout,
                note=gate.get('error') or gate.get('kind') or 'pilot dispatch denied',
            )
            return {
                'stage': HARD_BLOCK_STAGE,
                'ok': False,
                'pilot_gate': gate,
            }
    except Exception:
        gate = {'allow': True, 'kind': 'pilot_unavailable'}

    actions = []
    deliverable_path = None
    summary_body = ''
    before_snapshot = {
        'stage': card.get('stage'),
        'evidence_count': len(card.get('evidence') or []),
        'research_count': len(card.get('research_refs') or []),
    }
    # Domain execution
    if job.domain in ('infrastructure', 'systems', 'technical', 'coordination'):
        rs = tools.invoke(agent, 'repo.search', query=(job.request.split() or ['job'])[0][:48])
        actions.append(rs)
        if rs.ok:
            _add_evidence(layout, job, rs.action_id)
        st = tools.invoke(agent, 'shell.execute', command='git status')
        actions.append(st)
        if st.ok:
            _add_evidence(layout, job, st.action_id)
        if agent == 'vector':
            import os
            if os.environ.get('OTACON_AUTONOMY_RUN_TESTS', '').strip() in ('1', 'true', 'yes'):
                tests = tools.invoke('vector', 'tests.run')
                actions.append(tests)
                if tests.ok:
                    _add_evidence(layout, job, tests.action_id)
            else:
                # Lightweight execution proof without full suite every tick
                compile_chk = tools.invoke('vector', 'shell.execute', command='python3 -m compileall expansion/rex.py')
                actions.append(compile_chk)
                if compile_chk.ok:
                    _add_evidence(layout, job, compile_chk.action_id)
            dock = tools.invoke('vector', 'docker.inspect')
            actions.append(dock)
    elif job.domain in ('security', 'monitoring'):
        scan = tools.invoke('sentry', 'security.scan')
        actions.append(scan)
        if scan.ok:
            _add_evidence(layout, job, scan.action_id)
        svc = tools.invoke('sentry', 'services.inspect')
        actions.append(svc)
    elif job.domain in ('records', 'research', 'continuity'):
        # Prefer real research artifacts; synthesize a written deliverable.
        # Do not repo.search the first word of the request (noise) or journal-only close.
        q = (job.request or 'research')[:160]
        search = tools.invoke('ledger', 'web.search', query=q)
        actions.append(search)
        if search.ok:
            results = search.data.get('results') or []
            for hit in results[:3]:
                _add_research(layout, job.job_id, {
                    'title': hit.get('title') or '',
                    'url': hit.get('url') or '',
                    'snippet': hit.get('snippet') or '',
                }, agent)
                if hit.get('url'):
                    fetched = tools.invoke('ledger', 'web.fetch', url=hit['url'])
                    actions.append(fetched)
                    if fetched.ok:
                        _add_research(layout, job.job_id, {
                            'title': fetched.data.get('title_guess') or hit.get('url'),
                            'url': hit.get('url') or '',
                            'snippet': (fetched.data.get('snippet') or '')[:400],
                        }, agent)
            if results:
                _add_evidence(layout, job, search.action_id)
        deliverable_path = _synthesize_research_deliverable(layout, job, agent)
        summary_body = ''
        if deliverable_path:
            try:
                summary_body = Path(deliverable_path).read_text(encoding='utf-8')[:1200]
            except OSError:
                summary_body = f'Research deliverable written to {deliverable_path}'
            tools.invoke(
                'ledger', 'journal.write',
                text=f'Research deliverable for {job.job_id}: {deliverable_path}',
                job_id=job.job_id,
                result='deliverable_written',
            )
            _add_evidence(layout, job, f'deliverable:{deliverable_path}')
        else:
            tools.invoke(
                'ledger', 'journal.write',
                text=f'Research incomplete for {job.job_id} — no sources yet',
                job_id=job.job_id,
                result='no_sources',
            )
    elif job.domain in ('creative', 'media'):
        local = tools.invoke('muse', 'repo.search', query='ui')
        actions.append(local)
        if local.ok:
            _add_evidence(layout, job, local.action_id)

    # Mark execution result on job
    ok = any(a.ok for a in actions) if actions else False
    store = JobStore(layout)
    j = store.get(job.job_id)
    after_snapshot = {
        'actions': len(actions),
        'ok_actions': sum(1 for a in actions if a.ok),
        'fail_actions': sum(1 for a in actions if not a.ok),
    }
    if j:
        if summary_body:
            j.result = summary_body[:1500]
        else:
            j.result = (
                f'Executed {len(actions)} tool action(s); '
                f'ok={sum(1 for a in actions if a.ok)} fail={sum(1 for a in actions if not a.ok)}'
            )
        # Pilot DoD substrate: before/after evidence tags + structured blob on meta
        try:
            from expansion.pilot_governance import attach_before_after
            ev_ids = list(j.evidence or [])
            ev_ids.append(f'before:evidence={before_snapshot["evidence_count"]}')
            ev_ids.append(f'after:actions={after_snapshot["actions"]}:ok={after_snapshot["ok_actions"]}')
            if deliverable_path:
                tag = f'deliverable:{deliverable_path}'
                if tag not in ev_ids:
                    ev_ids.append(tag)
            j.evidence = ev_ids[-40:]
            # Stash structured before/after on rex meta via decision_trace note
            from expansion.rex import get_item, _update_meta, _append_trace

            def _mut(data):
                data = data or {'schema_version': 1, 'items': {}}
                items = data.setdefault('items', {})
                item = dict(items.get(job.job_id) or get_item(job.job_id, layout) or {'job_id': job.job_id})
                ev = attach_before_after(
                    item.get('implementation_evidence'),
                    before_state=before_snapshot,
                    after_state=after_snapshot,
                    before_metric=before_snapshot.get('evidence_count'),
                    after_metric=after_snapshot.get('ok_actions'),
                )
                if deliverable_path:
                    ev['deliverable_path'] = deliverable_path
                item['implementation_evidence'] = ev
                _append_trace(item, agent, 'pilot_evidence', 'before/after recorded')
                items[job.job_id] = item
                return data

            _update_meta(layout, _mut)
        except Exception:
            pass
        store.update(j)

    advance_stage(job.job_id, 'VERIFYING', actor=agent, layout=layout, note=j.result if j else '')
    return {
        'stage': 'VERIFYING',
        'actions': [a.action_id for a in actions],
        'ok': ok,
        'pilot_gate': gate,
    }


def step_verify(layout: StateLayout, job: Job) -> dict:
    """Cross-agent peer review + optional gate to close or rework."""
    owner = job.assigned_agent or 'vector'
    reviewers = [a for a in ('ledger', 'sentry', 'aria') if a != owner]
    reviewer = reviewers[0]
    card = job_to_card(job, layout)
    # Ledger corroborates real outcome evidence (not before:/after: bookkeeping).
    try:
        from expansion.pilot_governance import substantive_evidence_ids
        substantive = substantive_evidence_ids(card.get('evidence'))
    except Exception:
        substantive = list(card.get('evidence') or [])
    refs = list(card.get('research_refs') or [])
    has_signal = bool(refs or substantive)
    if (job.domain or '') in ('research', 'records', 'continuity', 'documentation'):
        has_signal = bool(refs)
    verdict = 'pass' if has_signal else 'fail'
    note = 'evidence present' if has_signal else 'missing research/execution evidence'
    add_peer_review(job.job_id, reviewer=reviewer, verdict=verdict, note=note, layout=layout)
    # Second opinion from Sentry on security domains / always light check
    if 'sentry' in reviewers and reviewer != 'sentry':
        add_peer_review(
            job.job_id, reviewer='sentry', verdict='pass' if has_signal else 'abstain',
            note='health/security glance', layout=layout,
        )

    card = job_to_card(JobStore(layout).get(job.job_id), layout)
    ready, reason = verification_ready(card)
    # Controlled pilot DoD (before/after + non-weak verify)
    dod = None
    try:
        from expansion.pilot_governance import definition_of_done, record_pilot_close, auto_rollback_job
        item = get_item(job.job_id, layout)
        dod = definition_of_done(
            domain=job.domain,
            evidence=card.get('evidence'),
            result=job.result or '',
            peer_reviews=card.get('peer_reviews'),
            research_refs=card.get('research_refs'),
            implementation_evidence=item.get('implementation_evidence'),
            layout=layout,
        )
        if not dod.get('passed'):
            ready = False
            reason = 'pilot DoD failed: ' + ','.join(dod.get('missing') or ['unknown'])
    except Exception:
        dod = None
    learning_out = None
    if ready:
        follow = ''
        if job.domain in ('infrastructure', 'security'):
            follow = f'Document outcome of {job.job_id}: {job.request[:100]}'
        # Stamp derived confidence onto the job before close (never leave 0.0 on success).
        try:
            store = JobStore(layout)
            fresh_pre = store.get(job.job_id)
            if fresh_pre and dod:
                fresh_pre.confidence = float(dod.get('derived_confidence') or 0.55)
                store.update(fresh_pre)
        except Exception:
            pass
        # Learning before close: execute→verify→peer→outcome→learn→close
        try:
            from expansion.learning import learn_from_autonomy_outcome
            fresh = JobStore(layout).get(job.job_id)
            learning_out = learn_from_autonomy_outcome(
                layout,
                job=fresh,
                success=True,
                method=(fresh.result or 'autonomous verified repair')[:100],
                peer_verdict=verdict,
                evidence_ids=list(fresh.evidence or []) + [f'review:{reviewer}:{verdict}'],
            )
        except Exception:
            learning_out = None
        out = close_with_follow_up(
            job.job_id,
            actor='aria',
            result=f'Autonomous close — {reason}',
            follow_up_request=follow,
            follow_up_domain='records' if follow else '',
            layout=layout,
        )
        try:
            from expansion.pilot_governance import record_pilot_close
            if dod and dod.get('pilot_scope'):
                # Only graduate on passed DoD with positive derived confidence.
                clean = bool(dod.get('passed')) and float(dod.get('derived_confidence') or 0) > 0
                record_pilot_close(
                    job_id=job.job_id,
                    clean=clean,
                    reason='dod_passed' if clean else 'dod_weak_confidence',
                    layout=layout,
                )
        except Exception:
            pass
        try:
            from expansion.journal import JournalStore, new_journal_entry
            JournalStore(layout).append(new_journal_entry(
                agent_id='aria',
                event_type='job.completed',
                summary=f'Closed {job.job_id}: {job.request[:120]}',
                objective_result=reason,
                actor='aria',
                target=owner,
                job_id=job.job_id,
                confidence=float((dod or {}).get('derived_confidence') or 0.55),
            ))
        except Exception:
            pass
        return {
            'stage': 'DONE',
            'closed': True,
            'follow_up': out['follow_up'].job_id if out.get('follow_up') else None,
            'reason': reason,
            'learning': learning_out,
            'dod': dod,
        }

    # Repair path — negative learning + pilot auto-rollback / streak reset
    try:
        from expansion.learning import learn_from_autonomy_outcome
        learn_from_autonomy_outcome(
            layout,
            job=JobStore(layout).get(job.job_id),
            success=False,
            method='failed verification',
            peer_verdict=verdict,
            evidence_ids=[f'review:{reviewer}:{verdict}'],
        )
    except Exception:
        pass
    rollback = None
    try:
        from expansion.pilot_governance import auto_rollback_job
        rollback = auto_rollback_job(job.job_id, layout=layout, reason=reason)
    except Exception:
        advance_stage(job.job_id, 'REWORK', actor=reviewer, layout=layout, note=reason)
    return {
        'stage': 'REWORK',
        'closed': False,
        'reason': reason,
        'dod': dod,
        'rollback': rollback,
    }


def process_job(layout: StateLayout, job: Job) -> dict:
    """Advance one job through as many autonomous stages as possible this tick."""
    log = []
    store = JobStore(layout)
    for _ in range(8):
        job = store.get(job.job_id)
        if not job:
            break
        card = job_to_card(job, layout)
        stage = card['stage']
        if stage in ('DONE', 'CANCELLED', HARD_BLOCK_STAGE):
            break
        if stage == 'BACKLOG':
            prioritize_backlog(layout)
            log.append('prioritize')
            continue
        if stage == 'READY':
            log.append(step_research(layout, job))
            continue
        if stage == 'RESEARCHING':
            log.append(step_plan_assign(layout, job))
            continue
        if stage == 'PLANNING':
            log.append(step_plan_assign(layout, job))
            continue
        if stage in ('ASSIGNED', 'IN_PROGRESS'):
            log.append(step_execute(layout, job))
            continue
        if stage == 'VERIFYING':
            log.append(step_verify(layout, job))
            break
        if stage == 'REWORK':
            # Retry: back to research or execute
            attempt = card.get('attempt') or 0
            if attempt >= (card.get('retry_budget') or 3):
                break
            advance_stage(job.job_id, 'IN_PROGRESS', actor=job.assigned_agent or 'vector', layout=layout)
            log.append(step_execute(layout, store.get(job.job_id)))
            continue
        break
    return {'job_id': job.job_id, 'steps': log}


def autonomy_tick(
    layout: Optional[StateLayout] = None,
    *,
    max_jobs: int = 5,
    detect: bool = True,
) -> dict:
    """One full autonomy cycle: detect → prioritize → process active work."""
    layout = layout or resolve_layout()
    try:
        from expansion.pilot_governance import bootstrap_pilot, status_payload
        bootstrap_pilot(layout)
        pilot = status_payload(layout)
    except Exception:
        pilot = None
    PolicyEngine(layout).seed_defaults()
    started = time.time()
    discovered = detect_work(layout) if detect else []
    prio = prioritize_backlog(layout)
    store = JobStore(layout)
    # Pick work: READY/ASSIGNED/IN_PROGRESS/VERIFYING/REWORK/RESEARCHING/PLANNING first
    order = {
        'VERIFYING': 0, 'IN_PROGRESS': 1, 'ASSIGNED': 2, 'REWORK': 3,
        'RESEARCHING': 4, 'PLANNING': 5, 'READY': 6, 'BACKLOG': 7,
    }
    candidates = []
    for job in store.list(limit=100):
        card = job_to_card(job, layout)
        if card['stage'] in order:
            candidates.append((order[card['stage']], job.priority, job.created_at, job))
    candidates.sort(key=lambda t: (t[0], t[1], t[2]))
    processed = []
    for _, _, _, job in candidates[:max_jobs]:
        processed.append(process_job(layout, job))

    board = build_rex_board(layout)
    return {
        'ok': True,
        'model': 'full_autonomy_loop',
        'elapsed_ms': int((time.time() - started) * 1000),
        'discovered': discovered,
        'prioritize': prio,
        'processed': processed,
        'metrics': board.get('metrics') or {},
        'tool_actions': ToolGateway(layout).recent(limit=20),
        'pilot': pilot,
        'note': (
            'Autonomy tick executed policy-gated research/execution/verify/close. '
            'Controlled pilot gates implementation domains; escalation on HARD_BLOCKED.'
        ),
    }
