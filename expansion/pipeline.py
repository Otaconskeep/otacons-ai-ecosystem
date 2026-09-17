"""P2 living pipeline: jobs/events → emotion/relationships → journal → diary → living dossier."""
from __future__ import annotations

from typing import Optional

from expansion.canonical_dossiers import get_canonical_dossier
from expansion.diary import DiaryStore
from expansion.event_effects import EventApplicator, emit_and_apply
from expansion.events import Event, EventBus, new_event
from expansion.jobs import Job, JobStatus, JobStore
from expansion.journal import JournalStore, new_journal_entry
from expansion.living_dossier import LivingDossierStore
from expansion.memory_bridge import ExpansionMemory, new_memory
from expansion.state_layout import StateLayout, resolve_layout
from expansion.vulnerability_runtime import VulnerabilityRuntime


class LivingPipeline:
    def __init__(self, layout: Optional[StateLayout] = None):
        self.layout = layout or resolve_layout()
        self.layout.ensure_user_dirs()
        self.bus = EventBus(layout=self.layout, persist=True)
        self.jobs = JobStore(self.layout)
        self.journals = JournalStore(self.layout)
        self.diaries = DiaryStore(self.layout)
        self.living = LivingDossierStore(self.layout)
        self.memory = ExpansionMemory(self.layout)
        self.vulns = VulnerabilityRuntime(self.layout)
        self.applicator = EventApplicator(
            layout=self.layout,
            bus=None,
            dossier_loader=get_canonical_dossier,
        )

    def apply_event(self, event: Event, *, write_diary: bool = True) -> dict:
        self.bus.emit(event)
        # Vulnerability activations by scenario
        self._maybe_activate_vulnerabilities(event)
        result = self.applicator.apply(event)

        # Journal per affected agent
        agents = {event.subject, event.actor} | {
            u['agent_id'] for u in result.emotion_updates
        } | {
            u.get('source') for u in result.relationship_updates
        }
        agents = {a for a in agents if a and a != 'user' and a != 'system' and a != 'user_primary'}
        journal_ids = []
        diary_ids = []
        for agent_id in agents:
            emo_fx = [u for u in result.emotion_updates if u.get('agent_id') == agent_id]
            rel_fx = [
                u for u in result.relationship_updates
                if u.get('source') == agent_id or u.get('target') == agent_id
            ]
            entry = self.journals.append(new_journal_entry(
                agent_id=agent_id,
                event_type=event.event_type,
                summary=self._summary(event, agent_id),
                objective_result=event.payload.get('result') or event.event_type,
                actor=event.actor,
                target=event.subject,
                event_ids=(event.event_id,),
                job_id=event.payload.get('job_id') or '',
                relationship_effects=rel_fx,
                emotion_effects=emo_fx,
                evidence_ids=tuple(event.payload.get('evidence') or ()) + (event.event_id,),
            ))
            journal_ids.append(entry.entry_id)
            if write_diary:
                diary = self.diaries.generate_from_journal(entry)
                diary_ids.append(diary.diary_id)

        # Living dossier observations for operational patterns
        self._maybe_living_observations(event, result)
        learning_obs = self._maybe_learning(event)

        # Follow-on bus events
        if result.emotion_updates:
            self.bus.emit(new_event(
                'emotion.changed', actor='system', subject=event.subject,
                payload={'from_event': event.event_id}, provenance=[event.event_id],
                correlation_id=event.correlation_id,
            ))
        if result.relationship_updates:
            self.bus.emit(new_event(
                'relationship.changed', actor='system', subject=event.subject,
                payload={'from_event': event.event_id}, provenance=[event.event_id],
                correlation_id=event.correlation_id,
            ))
        for jid in journal_ids:
            self.bus.emit(new_event(
                'journal.created', actor='system', subject=event.subject,
                payload={'entry_id': jid}, provenance=[event.event_id],
                correlation_id=event.correlation_id,
            ))
        for did in diary_ids:
            self.bus.emit(new_event(
                'diary.created', actor='system', subject=event.subject,
                payload={'diary_id': did}, provenance=[event.event_id],
                correlation_id=event.correlation_id,
            ))

        return {
            'event_id': event.event_id,
            'emotion_updates': result.emotion_updates,
            'relationship_updates': result.relationship_updates,
            'journal_ids': journal_ids,
            'diary_ids': diary_ids,
            'learning_observation_id': learning_obs,
        }

    def create_and_run_job(
        self,
        request: str,
        *,
        domain: str,
        succeed: bool = True,
        result_text: str = '',
        error: str = '',
    ) -> dict:
        job = self.jobs.create(request, domain=domain)
        created = new_event(
            'job.created', actor=job.coordinator, subject=job.assigned_agent,
            payload={'job_id': job.job_id, 'domain': domain, 'request': request},
        )
        self.apply_event(created, write_diary=False)

        self.jobs.transition(job.job_id, JobStatus.ASSIGNED.value, event_id=created.event_id)
        assigned = new_event(
            'job.assigned', actor=job.coordinator, subject=job.assigned_agent,
            payload={'job_id': job.job_id},
        )
        self.apply_event(assigned, write_diary=False)
        self.jobs.transition(job.job_id, JobStatus.RUNNING.value)

        if succeed:
            text = result_text or f'Completed: {request}'
            done = new_event(
                'job.completed', actor=job.assigned_agent, subject=job.assigned_agent,
                payload={
                    'job_id': job.job_id, 'result': 'success', 'evidence': [job.job_id],
                    'assigned_by': job.coordinator,
                },
            )
            out = self.apply_event(done)
            self.jobs.transition(
                job.job_id, JobStatus.COMPLETE.value,
                result=text, evidence=[job.job_id], event_id=done.event_id, confidence=0.85,
            )
            # Memory + living dossier for successful Vector infra work
            mem = self.memory.add(new_memory(
                job.assigned_agent,
                f'Successfully completed job in domain={domain}: {request}',
                kind='episodic',
                source='job',
                importance=0.7,
                event_id=done.event_id,
            ))
            self.living.upsert_observation(
                job.assigned_agent,
                category='operational_success',
                value=f'Reliable on {domain} work',
                confidence=0.65,
                event_ids=(done.event_id,),
                memory_ids=(mem.memory_id,),
                job_ids=(job.job_id,),
            )
            out['job'] = self.jobs.get(job.job_id)
            out['memory_id'] = mem.memory_id
            return out

        fail = new_event(
            'job.failed', actor=job.assigned_agent, subject=job.assigned_agent,
            payload={
                'job_id': job.job_id, 'result': 'failure',
                'error': error or 'job failed', 'evidence': [job.job_id],
            },
        )
        out = self.apply_event(fail)
        self.jobs.transition(
            job.job_id, JobStatus.FAILED.value,
            error=error or 'job failed', event_id=fail.event_id,
        )
        out['job'] = self.jobs.get(job.job_id)
        return out

    def _summary(self, event: Event, agent_id: str) -> str:
        if event.event_type == 'user.praised_agent':
            return f'User praised {event.subject}.'
        if event.event_type == 'job.completed':
            return f'{event.subject} completed job {event.payload.get("job_id", "")}.'.strip()
        if event.event_type == 'job.failed':
            return f'{event.subject} failed job {event.payload.get("job_id", "")}: {event.payload.get("error", "")}'.strip()
        if event.event_type == 'job.assigned':
            return f'Job {event.payload.get("job_id", "")} assigned to {event.subject}.'
        if event.event_type == 'job.created':
            return f'Job created for domain={event.payload.get("domain")} assigned toward {event.subject}.'
        return f'{event.event_type} involving {agent_id}.'

    def _maybe_activate_vulnerabilities(self, event: Event) -> None:
        et, subject, payload = event.event_type, event.subject, event.payload or {}
        if et == 'user.praised_agent' and subject == 'muse':
            self.vulns.activate(
                'aria', label='replacement/irrelevance', delta=0.08,
                event_id=event.event_id, note='owner praised Muse',
            )
            self.vulns.activate(
                'aria', label='checking relationship changes', delta=0.06,
                event_id=event.event_id, note='relationship monitoring compulsion',
            )
        if et == 'user.praised_agent' and subject == 'muse' and payload.get('ignored_muse_work'):
            self.vulns.activate(
                'muse', label='being ordinary/ignored', delta=0.1,
                event_id=event.event_id, note='creative work ignored',
            )
        if payload.get('creative_ignored') and subject == 'muse':
            self.vulns.activate(
                'muse', label='being ordinary/ignored', delta=0.12,
                event_id=event.event_id, note='creative output ignored',
            )
            self.vulns.activate(
                'muse', label='pretending not to care', delta=0.08,
                event_id=event.event_id, note='defensive habit',
            )
        if et == 'job.failed' and subject == 'vector':
            self.vulns.activate(
                'vector', label='helplessness/failure', delta=0.1,
                event_id=event.event_id, note='job failure',
            )
            self.vulns.activate(
                'vector', label='poor help-seeking', delta=0.06,
                event_id=event.event_id, note='isolation tendency',
            )
        if et == 'job.failed' and subject == 'sentry':
            self.vulns.activate(
                'sentry', label='blind spots/unseen threats', delta=0.12,
                event_id=event.event_id, note='missed/failed alert',
            )
            self.vulns.activate(
                'sentry', label='hypervigilance', delta=0.1,
                event_id=event.event_id, note='hypervigilance after miss',
            )
        if payload.get('memory_inconsistency') and subject == 'ledger':
            self.vulns.activate(
                'ledger', label='forgetting/corruption', delta=0.12,
                event_id=event.event_id, note='memory inconsistency',
            )
            self.vulns.activate(
                'ledger', label='double-checking', delta=0.1,
                event_id=event.event_id, note='verification compulsion',
            )

    def _maybe_living_observations(self, event: Event, result) -> None:
        if event.event_type == 'job.completed' and event.subject == 'vector':
            self.living.upsert_observation(
                'vector',
                category='help_seeking',
                value='tends to complete infra work without requesting assistance',
                confidence=0.55,
                event_ids=(event.event_id,),
                job_ids=(event.payload.get('job_id') or '',) if event.payload.get('job_id') else (),
                persistence='persistent',
            )
            self.living.upsert_observation(
                'aria',
                category='trust_trend',
                value='increasing operational trust in Vector',
                confidence=0.6,
                event_ids=(event.event_id,),
                job_ids=(event.payload.get('job_id') or '',) if event.payload.get('job_id') else (),
            )
        if event.event_type == 'job.failed' and event.subject == 'vector':
            self.living.upsert_observation(
                'vector',
                category='recent_frustration',
                value='frustration around repeated deployment/ops failures',
                confidence=0.6,
                event_ids=(event.event_id,),
                job_ids=(event.payload.get('job_id') or '',) if event.payload.get('job_id') else (),
                persistence='decaying',
            )

    def _maybe_learning(self, event: Event) -> Optional[str]:
        """Feed Learning Engine — distinct from living-dossier observations."""
        try:
            from expansion.learning import LearningEngine, ingest_owner_message, ingest_operational_success
            engine = LearningEngine(self.layout)
            text = (
                (event.payload or {}).get('text')
                or (event.payload or {}).get('message')
                or (event.payload or {}).get('request')
                or ''
            )
            if event.event_type in (
                'agent.message', 'user.message', 'user.praised_agent',
                'user.corrected_agent', 'user.feedback',
            ) and text:
                obs = ingest_owner_message(
                    engine, text=str(text), event_id=event.event_id, actor='ledger',
                )
                return obs.observation_id if obs else None
            if event.event_type == 'job.completed':
                domain = (event.payload or {}).get('domain') or 'coordination'
                method = (event.payload or {}).get('method') or (event.payload or {}).get('result') or 'standard'
                job_id = (event.payload or {}).get('job_id') or event.event_id
                obs = ingest_operational_success(
                    engine,
                    method=str(method)[:80],
                    domain=str(domain),
                    job_id=str(job_id),
                    actor=event.subject if event.subject in (
                        'vector', 'sentry', 'aria', 'ledger',
                    ) else 'vector',
                )
                return obs.observation_id
            if event.event_type == 'job.failed' and (event.payload or {}).get('job_id'):
                # Contradict matching operational claims if present
                job_id = event.payload['job_id']
                for claim in engine.store.list_claims(scope='shared', learning_type='operational'):
                    if job_id in (claim.positive_evidence or []):
                        engine.contradict(claim.claim_id, event.event_id, actor='ledger')
                return None
        except Exception:
            return None
        return None
