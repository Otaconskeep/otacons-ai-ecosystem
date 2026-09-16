"""HTTP handlers for Expansion P2 surfaces (imported by installer.server).

Never returns full system prompts, credentials, or package keys.
"""
from __future__ import annotations

from dataclasses import asdict


def handle_expansion_get(path: str, send_json) -> bool:
    """Return True if handled."""
    if path == '/api/expansion/command':
        from expansion.jobs import JobStore
        from expansion.runtime import ExpansionRuntime
        from expansion.emotion_store import EmotionStore
        from expansion.relationship_interpret import RelationshipInterpreter
        from expansion.readiness import evaluate_foundation
        rt = ExpansionRuntime()
        if not rt.expansion_enabled():
            send_json({'enabled': False})
            return True
        jobs = JobStore()
        emo = EmotionStore()
        interp = RelationshipInterpreter()
        roster = []
        for a in rt.load_roster():
            e = emo.get_or_create(a.agent_id)
            top = sorted(e.dimensions.items(), key=lambda kv: kv[1], reverse=True)[:4]
            roster.append({
                'agent_id': a.agent_id,
                'display_name': a.display_name,
                'role': a.role,
                'emotion_highlights': {k: round(v, 3) for k, v in top},
            })
        shifts = []
        for edge in (('aria', 'muse'), ('aria', 'vector'), ('muse', 'aria')):
            s = interp.summarize(*edge)
            if s.label in ('competitive_attachment', 'jealous_attachment', 'strained'):
                shifts.append({
                    'source': s.source_id, 'target': s.target_id,
                    'label': s.label, 'narrative': s.narrative,
                })
        send_json({
            'surface': 'aria_command_floor',
            'note': 'Aria Command = agent coordination; Dashboard = owner overview.',
            'roster': roster,
            'active_jobs': [asdict(j) for j in jobs.list(limit=30)
                            if j.status in ('QUEUED', 'ASSIGNED', 'RUNNING', 'WAITING', 'BLOCKED')],
            'delegations': [
                {'job_id': j.job_id, 'from': j.coordinator, 'to': j.assigned_agent,
                 'domain': j.domain, 'status': j.status}
                for j in jobs.list(limit=30)
            ],
            'readiness': evaluate_foundation().to_dict(),
            'relationship_shifts': shifts,
            'pending_decisions': [
                asdict(j) for j in jobs.list(status='WAITING', limit=10)
            ] + [asdict(j) for j in jobs.list(status='BLOCKED', limit=10)],
        })
        return True
    if path == '/api/expansion/intel':
        from expansion.journal import JournalStore
        from expansion.memory_bridge import ExpansionMemory
        from expansion.living_dossier import LivingDossierStore
        from expansion.relationship_interpret import RelationshipInterpreter
        from expansion.events import EventBus
        mem = ExpansionMemory()
        important = []
        for aid in ('aria', 'vector', 'ledger', 'muse', 'sentry'):
            for m in mem.list(aid)[:20]:
                if m.importance >= 0.7:
                    important.append({
                        'agent_id': aid, 'memory_id': m.memory_id,
                        'content': m.content, 'importance': m.importance,
                    })
        living = {}
        store = LivingDossierStore()
        for aid in ('aria', 'vector', 'ledger', 'muse', 'sentry'):
            doc = store.load(aid)
            living[aid] = [{'category': o.category, 'value': o.value,
                            'confidence': o.confidence} for o in doc.observations[:8]]
        send_json({
            'surface': 'ledger_intel',
            'important_memories': sorted(important, key=lambda x: -x['importance'])[:30],
            'journal_timeline': [asdict(e) for e in JournalStore().recent(limit=40)],
            'living_dossiers': living,
            'relationship_evidence': RelationshipInterpreter().matrix(
                ['aria', 'muse', 'ledger', 'user_primary']
            )[:12],
            'recent_events': [
                {'event_id': e.event_id, 'event_type': e.event_type,
                 'actor': e.actor, 'subject': e.subject}
                for e in EventBus(persist=True).recent(limit=30)
            ],
            'note': 'No private medical/household data.',
        })
        return True
    if path == '/api/expansion/creative':
        from expansion.jobs import JobStore
        jobs = [j for j in JobStore().list(agent_id='muse', limit=40)]
        send_json({
            'surface': 'muse_creative',
            'creative_queue': [asdict(j) for j in jobs
                               if j.status in ('QUEUED', 'ASSIGNED', 'RUNNING') and j.domain in ('creative', 'media')],
            'recent_creative_jobs': [asdict(j) for j in jobs if j.domain in ('creative', 'media')][:15],
            'capabilities': {
                'generation': 'local_template_ready',
                'video_studio': 'deferred_p3',
                'voice_motion': 'readiness_dependent',
            },
            'video_studio_readiness': 'not_ported',
            'note': 'Heavy Video Studio remains P3; this is the room shell.',
        })
        return True
    if path == '/api/expansion/ops':
        from expansion.jobs import JobStore
        from expansion.emotion_store import EmotionStore
        jobs = JobStore()
        security = [j for j in jobs.list(agent_id='sentry', limit=40)
                    if j.domain in ('security', 'monitoring')]
        emo = EmotionStore().get_or_create('sentry')
        send_json({
            'surface': 'sentry_ops',
            'alerts': [asdict(j) for j in security if j.status == 'FAILED'][:20],
            'security_jobs': [asdict(j) for j in security][:20],
            'health_incidents': [asdict(j) for j in jobs.list(status='FAILED', limit=20)
                                 if j.assigned_agent == 'sentry'],
            'observations': {
                'emotion': {k: round(v, 3) for k, v in emo.dimensions.items()
                            if k in ('concern', 'fear', 'stress', 'confidence')},
            },
            'home_assistant': {
                'status': 'unavailable_optional',
                'note': 'Home Assistant integration is optional; absence is not a failure.',
            },
            'package_readiness': 'consult /api/expansion/status',
        })
        return True
    if path == '/api/expansion/rooms':
        from expansion.rooms import RoomRegistry
        rooms = RoomRegistry().seed_defaults()
        send_json({
            'rooms': [
                {
                    'page_id': r.page_id,
                    'name': r.name,
                    'route': r.route,
                    'owner_agent': r.owner_agent,
                    'icon': r.icon,
                    'description': r.description,
                    'enabled': r.enabled,
                    'shared': r.shared,
                    'kind': r.kind,
                }
                for r in rooms
            ]
        })
        return True
    if path == '/api/expansion/war-room':
        from expansion.jobs import JobStore
        from expansion.entitlement import EntitlementGate
        if not EntitlementGate().expansion_surfaces_allowed():
            send_json({'enabled': False, 'message': 'Expansion not entitled'})
            return True
        jobs = JobStore()
        send_json({
            'active': [asdict(j) for j in jobs.list(limit=50)
                       if j.status in ('QUEUED', 'ASSIGNED', 'RUNNING', 'WAITING', 'BLOCKED')],
            'failed': [asdict(j) for j in jobs.list(status='FAILED', limit=20)],
            'complete': [asdict(j) for j in jobs.list(status='COMPLETE', limit=20)],
            'owner': 'vector',
            'commander': 'aria',
            'note': 'War Room = jobs/decisions; Infra Dashboard is separate telemetry.',
        })
        return True
    if path == '/api/expansion/reports':
        from expansion.reports import build_agent_report
        from expansion.runtime import ExpansionRuntime
        rt = ExpansionRuntime()
        if not rt.expansion_enabled():
            send_json({'enabled': False, 'reports': []})
            return True
        reports = []
        for a in rt.load_roster():
            reports.append(build_agent_report(a.agent_id))
        send_json({'enabled': True, 'reports': reports})
        return True
    if path.startswith('/api/expansion/reports/'):
        from expansion.reports import build_agent_report
        agent_id = path.rsplit('/', 1)[-1]
        try:
            send_json(build_agent_report(agent_id))
        except KeyError:
            send_json({'error': 'unknown agent'}, 404)
        return True
    if path.startswith('/api/expansion/journal'):
        from expansion.journal import JournalStore
        store = JournalStore()
        # /api/expansion/journal? handled via path only — agent optional in path
        parts = path.strip('/').split('/')
        agent_id = parts[3] if len(parts) > 3 else None
        entries = store.recent(limit=50, agent_id=agent_id)
        send_json({
            'entries': [asdict(e) for e in entries],
            'kind': 'journal',
            'rule': 'JOURNAL = WHAT HAPPENED',
        })
        return True
    if path.startswith('/api/expansion/diary/'):
        from expansion.diary import DiaryStore
        parts = path.strip('/').split('/')
        agent_id = parts[3] if len(parts) > 3 else ''
        if len(parts) > 4 and parts[4] == 'explain' and len(parts) > 5:
            try:
                send_json(DiaryStore().explain(agent_id, parts[5]))
            except KeyError:
                send_json({'error': 'not found'}, 404)
            return True
        send_json({
            'entries': DiaryStore().recent(agent_id, limit=50),
            'kind': 'diary',
            'rule': 'DIARY = WHAT IT MEANT',
        })
        return True
    if path.startswith('/api/expansion/living/'):
        from expansion.living_dossier import LivingDossierStore
        parts = path.strip('/').split('/')
        agent_id = parts[3]
        store = LivingDossierStore()
        if len(parts) > 4 and parts[4] == 'explain' and len(parts) > 5:
            try:
                send_json(store.explain(agent_id, parts[5]))
            except KeyError:
                send_json({'error': 'not found'}, 404)
            return True
        doc = store.load(agent_id)
        send_json({
            'agent_id': agent_id,
            'observations': [asdict(o) for o in doc.observations],
            'notes': doc.notes,
        })
        return True
    if path.startswith('/api/expansion/emotion/'):
        from expansion.emotion_store import EmotionStore
        parts = path.strip('/').split('/')
        agent_id = parts[3]
        emo = EmotionStore().get_or_create(agent_id)
        if len(parts) > 4 and parts[4] == 'why' and len(parts) > 5:
            send_json(emo.explain(parts[5]))
            return True
        send_json({
            'agent_id': agent_id,
            'dimensions': emo.dimensions,
            'baseline': emo.baseline,
            'updated_at': emo.updated_at,
        })
        return True
    if path.startswith('/api/expansion/relationships'):
        from expansion.relationship_interpret import RelationshipInterpreter
        interp = RelationshipInterpreter()
        parts = path.strip('/').split('/')
        if len(parts) >= 6 and parts[3] and parts[4] and parts[5] == 'why':
            send_json(interp.why(parts[3], parts[4]))
            return True
        if len(parts) >= 5 and parts[3] and parts[4]:
            s = interp.summarize(parts[3], parts[4])
            send_json(asdict(s))
            return True
        send_json({'matrix': interp.matrix()})
        return True
    if path == '/api/expansion/jobs':
        from expansion.jobs import JobStore
        send_json({'jobs': [asdict(j) for j in JobStore().list(limit=100)]})
        return True
    if path == '/api/expansion/entitlement':
        from expansion.entitlement import EntitlementGate
        g = EntitlementGate()
        st = g.current()
        send_json({
            'expansion_entitled': st.expansion_entitled,
            'source': st.source,
            'message': st.message,
            'user_data_accessible': g.user_data_accessible(),
            # Never expose keys/secrets
        })
        return True
    return False


def handle_expansion_post(path: str, data: dict, send_json) -> bool:
    if path == '/api/expansion/jobs/create':
        from expansion.pipeline import LivingPipeline
        pipe = LivingPipeline()
        succeed = bool(data.get('succeed', True))
        out = pipe.create_and_run_job(
            data.get('request') or 'untitled job',
            domain=data.get('domain') or 'coordination',
            succeed=succeed,
            result_text=data.get('result') or '',
            error=data.get('error') or '',
        )
        job = out.get('job')
        send_json({
            'ok': True,
            'job': asdict(job) if job else None,
            'event_id': out.get('event_id'),
            'journal_ids': out.get('journal_ids'),
            'diary_ids': out.get('diary_ids'),
        })
        return True
    if path == '/api/expansion/event':
        from expansion.events import new_event
        from expansion.pipeline import LivingPipeline
        ev = new_event(
            data.get('event_type') or 'agent.message',
            actor=data.get('actor') or 'user',
            subject=data.get('subject') or '',
            payload=data.get('payload') or {},
        )
        out = LivingPipeline().apply_event(ev)
        send_json({'ok': True, **{k: out[k] for k in out if k != 'job'}})
        return True
    if path == '/api/expansion/pages/register':
        from expansion.rooms import RoomPage, RoomRegistry, ROOM_SCHEMA_VERSION
        page = RoomPage(
            schema_version=ROOM_SCHEMA_VERSION,
            page_id=data.get('page_id') or '',
            name=data.get('name') or '',
            route=data.get('route') or '',
            owner_agent=data.get('owner_agent') or 'aria',
            icon=data.get('icon') or 'PG',
            description=data.get('description') or '',
            required_capabilities=tuple(data.get('required_capabilities') or ()),
            permissions=tuple(data.get('permissions') or ()),
            health_source=data.get('health_source') or '',
            enabled=bool(data.get('enabled', True)),
            shared=bool(data.get('shared', False)),
            kind='page_builder',
        )
        try:
            RoomRegistry().seed_defaults()
            registered = RoomRegistry().register_page(page)
            send_json({'ok': True, 'page': asdict(registered)})
        except ValueError as exc:
            send_json({'error': {'code': 'PAGE_REJECTED', 'message': str(exc)}}, 400)
        return True
    return False
