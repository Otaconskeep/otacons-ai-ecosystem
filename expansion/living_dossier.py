"""Living dossier — evidence-backed observations after activation.

Canonical dossier remains vendor product data. Living dossier never invents
owner memories; every observation requires supporting event/memory/job IDs.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Optional

from expansion.persist import atomic_write_json, read_json
from expansion.state_layout import StateLayout, resolve_layout
from expansion.versions import DOSSIER_SCHEMA_VERSION

LIVING_OBS_SCHEMA_VERSION = 1


@dataclass
class LivingObservation:
    schema_version: int
    observation_id: str
    agent_id: str
    category: str
    value: str
    confidence: float
    first_observed: float
    last_updated: float
    supporting_event_ids: tuple = ()
    supporting_memory_ids: tuple = ()
    supporting_job_ids: tuple = ()
    persistence: str = 'persistent'  # persistent | decaying
    decay_half_life_s: float = 0.0

    def validate(self) -> list:
        errors = []
        if self.schema_version != LIVING_OBS_SCHEMA_VERSION:
            errors.append('unsupported living observation schema_version')
        if not self.observation_id or not self.agent_id:
            errors.append('observation_id and agent_id required')
        if not self.category or not self.value:
            errors.append('category and value required')
        if not (0.0 <= self.confidence <= 1.0):
            errors.append('confidence must be in [0,1]')
        if not (self.supporting_event_ids or self.supporting_memory_ids or self.supporting_job_ids):
            errors.append('observation requires supporting evidence IDs')
        if self.persistence not in ('persistent', 'decaying'):
            errors.append('persistence must be persistent|decaying')
        return errors


@dataclass
class LivingDossierDoc:
    schema_version: int
    agent_id: str
    observations: list = field(default_factory=list)
    notes: str = ''
    updated_at: float = 0.0


class LivingDossierStore:
    def __init__(self, layout: Optional[StateLayout] = None):
        self.layout = layout or resolve_layout()
        self.layout.user_living_dossiers.mkdir(parents=True, exist_ok=True)

    def _path(self, agent_id: str):
        return self.layout.user_living_dossiers / f'{agent_id}.json'

    def load(self, agent_id: str) -> LivingDossierDoc:
        raw = read_json(self._path(agent_id), default=None)
        if not raw:
            return LivingDossierDoc(
                schema_version=DOSSIER_SCHEMA_VERSION,
                agent_id=agent_id,
                observations=[],
                notes='No observed traits yet — living history starts at install.',
                updated_at=time.time(),
            )
        obs = []
        for o in raw.get('observations') or raw.get('observed_traits') or []:
            if 'observation_id' not in o and 'trait' in o:
                # P1 ObservedTrait compatibility
                o = {
                    'schema_version': LIVING_OBS_SCHEMA_VERSION,
                    'observation_id': f'obs_{uuid.uuid4().hex[:8]}',
                    'agent_id': agent_id,
                    'category': o.get('trait') or 'trait',
                    'value': o.get('value') or '',
                    'confidence': float(o.get('confidence') or 0.5),
                    'first_observed': float(o.get('updated_at') or time.time()),
                    'last_updated': float(o.get('updated_at') or time.time()),
                    'supporting_event_ids': tuple(o.get('evidence_event_ids') or ()),
                    'supporting_memory_ids': (),
                    'supporting_job_ids': (),
                    'persistence': 'persistent',
                    'decay_half_life_s': 0.0,
                }
            for k in ('supporting_event_ids', 'supporting_memory_ids', 'supporting_job_ids'):
                if isinstance(o.get(k), list):
                    o[k] = tuple(o[k])
            fields = LivingObservation.__dataclass_fields__
            obs.append(LivingObservation(**{k: o[k] for k in fields if k in o}))
        return LivingDossierDoc(
            schema_version=int(raw.get('schema_version', DOSSIER_SCHEMA_VERSION)),
            agent_id=agent_id,
            observations=obs,
            notes=raw.get('notes') or '',
            updated_at=float(raw.get('updated_at') or time.time()),
        )

    def save(self, doc: LivingDossierDoc) -> None:
        payload = {
            'schema_version': doc.schema_version,
            'agent_id': doc.agent_id,
            'notes': doc.notes,
            'updated_at': doc.updated_at,
            'observations': [asdict(o) for o in doc.observations],
        }
        atomic_write_json(self._path(doc.agent_id), payload)

    def upsert_observation(
        self,
        agent_id: str,
        *,
        category: str,
        value: str,
        confidence: float,
        event_ids: tuple = (),
        memory_ids: tuple = (),
        job_ids: tuple = (),
        persistence: str = 'persistent',
    ) -> LivingObservation:
        doc = self.load(agent_id)
        now = time.time()
        existing = next(
            (o for o in doc.observations if o.category == category and o.value == value),
            None,
        )
        if existing:
            existing.confidence = max(existing.confidence, confidence)
            existing.last_updated = now
            existing.supporting_event_ids = tuple(
                dict.fromkeys(existing.supporting_event_ids + tuple(event_ids))
            )
            existing.supporting_memory_ids = tuple(
                dict.fromkeys(existing.supporting_memory_ids + tuple(memory_ids))
            )
            existing.supporting_job_ids = tuple(
                dict.fromkeys(existing.supporting_job_ids + tuple(job_ids))
            )
            obs = existing
        else:
            obs = LivingObservation(
                schema_version=LIVING_OBS_SCHEMA_VERSION,
                observation_id=f'obs_{uuid.uuid4().hex[:12]}',
                agent_id=agent_id,
                category=category,
                value=value,
                confidence=confidence,
                first_observed=now,
                last_updated=now,
                supporting_event_ids=tuple(event_ids),
                supporting_memory_ids=tuple(memory_ids),
                supporting_job_ids=tuple(job_ids),
                persistence=persistence,
            )
            errors = obs.validate()
            if errors:
                raise ValueError('; '.join(errors))
            doc.observations.append(obs)
        doc.updated_at = now
        self.save(doc)
        return obs

    def explain(self, agent_id: str, observation_id: str) -> dict:
        doc = self.load(agent_id)
        for o in doc.observations:
            if o.observation_id == observation_id:
                return {
                    'observation_id': o.observation_id,
                    'category': o.category,
                    'value': o.value,
                    'confidence': o.confidence,
                    'first_observed': o.first_observed,
                    'last_updated': o.last_updated,
                    'supporting_event_ids': list(o.supporting_event_ids),
                    'supporting_memory_ids': list(o.supporting_memory_ids),
                    'supporting_job_ids': list(o.supporting_job_ids),
                    'persistence': o.persistence,
                    'rule': 'Living traits require evidence; no unexplained mutation.',
                }
        raise KeyError(observation_id)
