"""Expansion job / delegation store.

Aria coordinates by default. Domain routing is readiness-aware and overrideable.
Job completion/failure feeds journal, memory, emotion, relationships, living dossier.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Optional

from expansion.persist import atomic_write_json, read_json
from expansion.state_layout import StateLayout, resolve_layout

JOB_SCHEMA_VERSION = 1


class JobStatus(str, Enum):
    QUEUED = 'QUEUED'
    ASSIGNED = 'ASSIGNED'
    RUNNING = 'RUNNING'
    WAITING = 'WAITING'
    BLOCKED = 'BLOCKED'
    FAILED = 'FAILED'
    COMPLETE = 'COMPLETE'
    CANCELLED = 'CANCELLED'


DOMAIN_ROUTING = {
    'systems': 'vector',
    'infrastructure': 'vector',
    'technical': 'vector',
    'records': 'ledger',
    'research': 'ledger',
    'continuity': 'ledger',
    'creative': 'muse',
    'media': 'muse',
    'security': 'sentry',
    'monitoring': 'sentry',
    'coordination': 'aria',
}


@dataclass
class Job:
    schema_version: int
    job_id: str
    requester: str
    coordinator: str
    assigned_agent: str
    domain: str
    priority: int
    status: str
    created_at: float
    request: str
    started_at: float = 0.0
    completed_at: float = 0.0
    result: str = ''
    confidence: float = 0.0
    evidence: list = field(default_factory=list)
    error: str = ''
    parent_job: str = ''
    child_jobs: list = field(default_factory=list)
    event_ids: list = field(default_factory=list)

    def validate(self) -> list:
        errors = []
        if self.schema_version != JOB_SCHEMA_VERSION:
            errors.append('unsupported job schema_version')
        if self.status not in {s.value for s in JobStatus}:
            errors.append(f'invalid status {self.status}')
        if not self.job_id or not self.request:
            errors.append('job_id and request required')
        return errors


def route_domain(domain: str, *, overrides: Optional[dict] = None) -> str:
    overrides = overrides or {}
    key = (domain or '').strip().lower()
    if key in overrides:
        return overrides[key]
    if key in DOMAIN_ROUTING:
        return DOMAIN_ROUTING[key]
    # ambiguous → Aria coordinates
    return 'aria'


class JobStore:
    def __init__(self, layout: Optional[StateLayout] = None):
        self.layout = layout or resolve_layout()
        self.layout.user_jobs.mkdir(parents=True, exist_ok=True)
        self._path = self.layout.user_jobs / 'jobs.json'

    def _load_all(self) -> dict:
        return read_json(self._path, default={'schema_version': JOB_SCHEMA_VERSION, 'jobs': {}})

    def _save_all(self, data: dict) -> None:
        atomic_write_json(self._path, data)

    def create(
        self,
        request: str,
        *,
        domain: str,
        requester: str = 'user_primary',
        coordinator: str = 'aria',
        assigned_agent: Optional[str] = None,
        priority: int = 5,
        parent_job: str = '',
        routing_overrides: Optional[dict] = None,
    ) -> Job:
        agent = assigned_agent or route_domain(domain, overrides=routing_overrides)
        job = Job(
            schema_version=JOB_SCHEMA_VERSION,
            job_id=f'job_{uuid.uuid4().hex[:10]}',
            requester=requester,
            coordinator=coordinator,
            assigned_agent=agent,
            domain=domain,
            priority=priority,
            status=JobStatus.QUEUED.value,
            created_at=time.time(),
            request=request,
            parent_job=parent_job or '',
        )
        errors = job.validate()
        if errors:
            raise ValueError('; '.join(errors))
        data = self._load_all()
        data['jobs'][job.job_id] = asdict(job)
        self._save_all(data)
        return job

    def get(self, job_id: str) -> Optional[Job]:
        raw = (self._load_all().get('jobs') or {}).get(job_id)
        if not raw:
            return None
        return Job(**{k: raw[k] for k in Job.__dataclass_fields__ if k in raw})

    def list(
        self,
        *,
        status: Optional[str] = None,
        agent_id: Optional[str] = None,
        limit: int = 100,
    ) -> list[Job]:
        jobs = []
        for raw in (self._load_all().get('jobs') or {}).values():
            job = Job(**{k: raw[k] for k in Job.__dataclass_fields__ if k in raw})
            if status and job.status != status:
                continue
            if agent_id and job.assigned_agent != agent_id and job.coordinator != agent_id:
                continue
            jobs.append(job)
        jobs.sort(key=lambda j: j.created_at, reverse=True)
        return jobs[:limit]

    def update(self, job: Job) -> Job:
        errors = job.validate()
        if errors:
            raise ValueError('; '.join(errors))
        data = self._load_all()
        data['jobs'][job.job_id] = asdict(job)
        self._save_all(data)
        return job

    def transition(
        self,
        job_id: str,
        status: str,
        *,
        result: str = '',
        error: str = '',
        evidence: Optional[list] = None,
        event_id: str = '',
        confidence: float = 0.0,
    ) -> Job:
        job = self.get(job_id)
        if job is None:
            raise KeyError(job_id)
        now = time.time()
        job.status = status
        if status == JobStatus.RUNNING.value and not job.started_at:
            job.started_at = now
        if status in (JobStatus.COMPLETE.value, JobStatus.FAILED.value, JobStatus.CANCELLED.value):
            job.completed_at = now
        if result:
            job.result = result
        if error:
            job.error = error
        if evidence:
            job.evidence = list(evidence)
        if confidence:
            job.confidence = confidence
        if event_id:
            job.event_ids = list(job.event_ids) + [event_id]
        if status == JobStatus.ASSIGNED.value and job.status:
            job.status = JobStatus.ASSIGNED.value
        return self.update(job)
