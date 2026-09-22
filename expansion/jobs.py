"""Expansion job / delegation store.

Aria coordinates by default. Domain routing is readiness-aware and overrideable.
Job completion/failure feeds journal, memory, emotion, relationships, living dossier.
"""
from __future__ import annotations

import re
import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Optional

from expansion.persist import atomic_write_json, read_json, update_json
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

_OPEN_STATUSES = frozenset({
    JobStatus.QUEUED.value,
    JobStatus.ASSIGNED.value,
    JobStatus.RUNNING.value,
    JobStatus.WAITING.value,
    JobStatus.BLOCKED.value,
})


def request_fingerprint(request: str) -> str:
    """Normalize a job request for open-board dedupe."""
    text = (request or '').lower().strip()
    text = re.sub(r'[^\w\s]+', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    # Drop filler so "help me research X" ≈ "Research X"
    for filler in (
        'please ', 'help me ', 'can you ', 'could you ', 'go ahead and ',
        'the pending plan from our recent conversation',
    ):
        if text.startswith(filler):
            text = text[len(filler):].strip()
    return text[:220]


def find_open_job_for_request(
    request: str,
    *,
    layout: Optional[StateLayout] = None,
    assigned_agent: Optional[str] = None,
    domain: Optional[str] = None,
) -> Optional['Job']:
    """Return an open job with the same fingerprint, if any."""
    fp = request_fingerprint(request)
    if len(fp) < 8:
        return None
    store = JobStore(layout or resolve_layout())
    for job in store.list(limit=80):
        if job.status not in _OPEN_STATUSES:
            continue
        if assigned_agent and job.assigned_agent != assigned_agent:
            continue
        if domain and job.domain != domain:
            continue
        if request_fingerprint(job.request) == fp:
            return job
        # Soft overlap: same significant tokens (fabric research clones)
        a = set(fp.split())
        b = set(request_fingerprint(job.request).split())
        if len(a) >= 4 and len(b) >= 4:
            overlap = len(a & b) / max(1, len(a | b))
            if overlap >= 0.72:
                return job
    return None


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

        def _mut(data):
            data = data or {'schema_version': JOB_SCHEMA_VERSION, 'jobs': {}}
            data.setdefault('jobs', {})
            data['jobs'][job.job_id] = asdict(job)
            return data

        update_json(self._path, _mut, default={'schema_version': JOB_SCHEMA_VERSION, 'jobs': {}})
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

        def _mut(data):
            data = data or {'schema_version': JOB_SCHEMA_VERSION, 'jobs': {}}
            data.setdefault('jobs', {})
            data['jobs'][job.job_id] = asdict(job)
            return data

        update_json(self._path, _mut, default={'schema_version': JOB_SCHEMA_VERSION, 'jobs': {}})
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
        now = time.time()
        holder = {'job': None}

        def _mut(data):
            data = data or {'schema_version': JOB_SCHEMA_VERSION, 'jobs': {}}
            jobs = data.setdefault('jobs', {})
            raw = jobs.get(job_id)
            if not raw:
                raise KeyError(job_id)
            job = Job(**{k: raw[k] for k in Job.__dataclass_fields__ if k in raw})
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
            jobs[job_id] = asdict(job)
            holder['job'] = job
            return data

        try:
            update_json(self._path, _mut, default={'schema_version': JOB_SCHEMA_VERSION, 'jobs': {}})
        except KeyError:
            raise
        return holder['job']
