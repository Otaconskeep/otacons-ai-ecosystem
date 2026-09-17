"""Learning Engine — evidence-backed, revisable learned claims.

Distinct from memory / living dossiers:
  memory = what happened
  living dossier = observed traits with evidence
  learning = patterned claims with confidence, contradiction, decay, revision

Shared Keep learning is curated primarily by Ledger; private learning stays
per-agent. Every claim must cite positive/negative evidence IDs.
"""
from __future__ import annotations

import hashlib
import re
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Optional

from expansion.persist import atomic_write_json, read_json, update_json
from expansion.policy import PolicyEngine
from expansion.state_layout import StateLayout, resolve_layout

LEARNING_SCHEMA_VERSION = 1

LEARNING_TYPES = (
    'owner_preference',
    'operational',
    'relationship',
    'environment',
    'task',
    'social',
)

# Min corroborating observations before a claim graduates from raw observation.
PATTERN_THRESHOLD = 3
CONF_FLOOR = 0.05
CONF_CEIL = 0.97
DEFAULT_HALF_LIFE_S = 60 * 60 * 24 * 45  # ~45 days


@dataclass
class LearningObservation:
    schema_version: int
    observation_id: str
    agent_id: str
    learning_type: str
    scope: str  # private | shared
    text: str
    evidence_ids: list = field(default_factory=list)
    created_at: float = 0.0
    pattern_key: str = ''

    def validate(self) -> list:
        errors = []
        if self.schema_version != LEARNING_SCHEMA_VERSION:
            errors.append('unsupported learning observation schema')
        if self.learning_type not in LEARNING_TYPES:
            errors.append(f'invalid learning_type {self.learning_type}')
        if self.scope not in ('private', 'shared'):
            errors.append('scope must be private|shared')
        if not self.text.strip():
            errors.append('text required')
        if not self.evidence_ids:
            errors.append('observation requires evidence_ids')
        return errors


@dataclass
class LearnedClaim:
    schema_version: int
    claim_id: str
    claim: str
    learning_type: str
    scope: str
    agent_id: str  # private owner, or 'keep' when shared
    confidence: float
    positive_evidence: list = field(default_factory=list)
    negative_evidence: list = field(default_factory=list)
    observation_ids: list = field(default_factory=list)
    status: str = 'active'  # active | weakened | retired
    pattern_key: str = ''
    created_at: float = 0.0
    last_updated: float = 0.0
    last_reinforced: float = 0.0
    contradiction_count: int = 0
    half_life_s: float = DEFAULT_HALF_LIFE_S
    curator: str = ''  # ledger for shared
    revision_history: list = field(default_factory=list)
    confidence_history: list = field(default_factory=list)

    def validate(self) -> list:
        errors = []
        if self.schema_version != LEARNING_SCHEMA_VERSION:
            errors.append('unsupported claim schema')
        if not self.claim.strip():
            errors.append('claim required')
        if self.learning_type not in LEARNING_TYPES:
            errors.append(f'invalid learning_type {self.learning_type}')
        if self.scope not in ('private', 'shared'):
            errors.append('scope must be private|shared')
        if not (CONF_FLOOR <= self.confidence <= 1.0 or self.confidence == 0.0):
            if not (0.0 <= self.confidence <= 1.0):
                errors.append('confidence must be in [0,1]')
        if not (self.positive_evidence or self.negative_evidence):
            errors.append('claim requires evidence')
        if self.status not in ('active', 'weakened', 'retired'):
            errors.append('invalid status')
        return errors


def pattern_key(learning_type: str, text: str) -> str:
    norm = re.sub(r'\s+', ' ', (text or '').strip().lower())
    norm = re.sub(r'[^a-z0-9 _./:-]', '', norm)[:160]
    digest = hashlib.sha1(f'{learning_type}:{norm}'.encode()).hexdigest()[:12]
    return f'{learning_type}:{digest}'


def _decayed_confidence(claim: LearnedClaim, now: Optional[float] = None) -> float:
    now = now or time.time()
    if claim.half_life_s <= 0 or claim.status == 'retired':
        return claim.confidence
    anchor = claim.last_reinforced or claim.last_updated or claim.created_at
    age = max(0.0, now - anchor)
    factor = 0.5 ** (age / claim.half_life_s)
    return max(CONF_FLOOR, claim.confidence * factor)


class LearningStore:
    def __init__(self, layout: Optional[StateLayout] = None):
        self.layout = layout or resolve_layout()
        self.layout.user_learning.mkdir(parents=True, exist_ok=True)

    def _private_path(self, agent_id: str):
        return self.layout.user_learning / f'private_{agent_id}.json'

    def _shared_path(self):
        return self.layout.user_learning / 'shared_keep.json'

    def _load_bucket(self, path) -> dict:
        return read_json(path, default={
            'schema_version': LEARNING_SCHEMA_VERSION,
            'observations': {},
            'claims': {},
        })

    def _save_bucket(self, path, data: dict) -> None:
        atomic_write_json(path, data)

    def list_observations(
        self,
        *,
        agent_id: Optional[str] = None,
        scope: Optional[str] = None,
        pattern_key: Optional[str] = None,
        limit: int = 100,
    ) -> list[LearningObservation]:
        out: list[LearningObservation] = []
        paths = []
        if scope in (None, 'shared'):
            paths.append(self._shared_path())
        if scope in (None, 'private'):
            if agent_id:
                paths.append(self._private_path(agent_id))
            else:
                paths.extend(sorted(self.layout.user_learning.glob('private_*.json')))
        for path in paths:
            raw = self._load_bucket(path)
            for o in (raw.get('observations') or {}).values():
                obs = LearningObservation(
                    **{k: o[k] for k in LearningObservation.__dataclass_fields__ if k in o}
                )
                if agent_id and obs.scope == 'private' and obs.agent_id != agent_id:
                    continue
                if pattern_key and obs.pattern_key != pattern_key:
                    continue
                out.append(obs)
        out.sort(key=lambda x: x.created_at, reverse=True)
        return out[:limit]

    def list_claims(
        self,
        *,
        agent_id: Optional[str] = None,
        scope: Optional[str] = None,
        learning_type: Optional[str] = None,
        include_decayed: bool = True,
        min_confidence: float = 0.0,
    ) -> list[LearnedClaim]:
        out: list[LearnedClaim] = []
        paths = []
        if scope in (None, 'shared'):
            paths.append(self._shared_path())
        if scope in (None, 'private'):
            if agent_id:
                paths.append(self._private_path(agent_id))
            else:
                paths.extend(sorted(self.layout.user_learning.glob('private_*.json')))
        for path in paths:
            raw = self._load_bucket(path)
            for c in (raw.get('claims') or {}).values():
                claim = LearnedClaim(**{k: c[k] for k in LearnedClaim.__dataclass_fields__ if k in c})
                if learning_type and claim.learning_type != learning_type:
                    continue
                if agent_id and claim.scope == 'private' and claim.agent_id != agent_id:
                    continue
                conf = _decayed_confidence(claim) if include_decayed else claim.confidence
                if conf < min_confidence and claim.status == 'active':
                    continue
                if include_decayed:
                    claim.confidence = round(conf, 4)
                out.append(claim)
        out.sort(key=lambda c: c.confidence, reverse=True)
        return out

    def get_claim(self, claim_id: str) -> Optional[LearnedClaim]:
        for claim in self.list_claims(include_decayed=False):
            if claim.claim_id == claim_id:
                claim.confidence = round(_decayed_confidence(claim), 4)
                return claim
        return None


class LearningEngine:
    """Observe → pattern → claim → reinforce/contradict/decay/revise."""

    def __init__(self, layout: Optional[StateLayout] = None):
        self.layout = layout or resolve_layout()
        self.store = LearningStore(self.layout)
        self.policy = PolicyEngine(self.layout)

    def _path_for(self, scope: str, agent_id: str):
        if scope == 'shared':
            return self.store._shared_path()
        return self.store._private_path(agent_id)

    def observe(
        self,
        agent_id: str,
        text: str,
        *,
        learning_type: str,
        evidence_ids: list,
        scope: str = 'private',
        actor: Optional[str] = None,
    ) -> LearningObservation:
        actor = actor or agent_id
        self.policy.require(actor, 'learning.observe')
        if scope == 'shared':
            self.policy.require(actor, 'learning.shared_write')
        obs = LearningObservation(
            schema_version=LEARNING_SCHEMA_VERSION,
            observation_id=f'lobs_{uuid.uuid4().hex[:10]}',
            agent_id=agent_id if scope == 'private' else 'keep',
            learning_type=learning_type,
            scope=scope,
            text=text.strip(),
            evidence_ids=list(evidence_ids),
            created_at=time.time(),
            pattern_key=pattern_key(learning_type, text),
        )
        errors = obs.validate()
        if errors:
            raise ValueError('; '.join(errors))

        path = self._path_for(scope, agent_id if scope == 'private' else 'keep')
        # Near-duplicate: same pattern_key + overlapping evidence → reinforce existing obs count only via graduate
        raw = self.store._load_bucket(path)
        for existing in (raw.get('observations') or {}).values():
            if existing.get('pattern_key') != obs.pattern_key:
                continue
            old_ev = set(existing.get('evidence_ids') or [])
            new_ev = set(obs.evidence_ids)
            if new_ev and new_ev.issubset(old_ev):
                # Exact duplicate evidence — do not create a second observation
                return LearningObservation(
                    **{k: existing[k] for k in LearningObservation.__dataclass_fields__ if k in existing}
                )
            if new_ev & old_ev and existing.get('text') == obs.text:
                # Near-duplicate text with shared evidence — merge evidence into existing
                merged = list(dict.fromkeys(list(old_ev) + list(new_ev)))
                existing['evidence_ids'] = merged[-40:]

                def _merge(data, eid=existing['observation_id'], row=existing):
                    data = data or {'schema_version': LEARNING_SCHEMA_VERSION, 'observations': {}, 'claims': {}}
                    data.setdefault('observations', {})[eid] = row
                    return data

                update_json(path, _merge, default={
                    'schema_version': LEARNING_SCHEMA_VERSION, 'observations': {}, 'claims': {},
                })
                merged_obs = LearningObservation(
                    **{k: existing[k] for k in LearningObservation.__dataclass_fields__ if k in existing}
                )
                self._maybe_graduate(merged_obs, actor=actor)
                return merged_obs

        def _mut(data):
            data = data or {'schema_version': LEARNING_SCHEMA_VERSION, 'observations': {}, 'claims': {}}
            data.setdefault('observations', {})[obs.observation_id] = asdict(obs)
            return data

        update_json(path, _mut, default={
            'schema_version': LEARNING_SCHEMA_VERSION, 'observations': {}, 'claims': {},
        })
        self._maybe_graduate(obs, actor=actor)
        return obs

    def _maybe_graduate(self, obs: LearningObservation, *, actor: str) -> Optional[LearnedClaim]:
        path = self._path_for(obs.scope, obs.agent_id if obs.scope == 'private' else 'keep')
        raw = self.store._load_bucket(path)
        peers = [
            LearningObservation(**{k: o[k] for k in LearningObservation.__dataclass_fields__ if k in o})
            for o in (raw.get('observations') or {}).values()
            if o.get('pattern_key') == obs.pattern_key
        ]
        if len(peers) < PATTERN_THRESHOLD:
            return None
        # Find existing claim with same pattern_key
        existing = None
        for c in (raw.get('claims') or {}).values():
            if c.get('pattern_key') == obs.pattern_key and c.get('status') != 'retired':
                existing = LearnedClaim(**{k: c[k] for k in LearnedClaim.__dataclass_fields__ if k in c})
                break
        evidence = []
        obs_ids = []
        for p in peers:
            evidence.extend(p.evidence_ids)
            obs_ids.append(p.observation_id)
        evidence = list(dict.fromkeys(evidence))
        obs_ids = list(dict.fromkeys(obs_ids))
        now = time.time()
        if existing:
            return self.reinforce(existing.claim_id, evidence[-1], actor=actor)

        claim = LearnedClaim(
            schema_version=LEARNING_SCHEMA_VERSION,
            claim_id=f'lrn_{uuid.uuid4().hex[:10]}',
            claim=obs.text,
            learning_type=obs.learning_type,
            scope=obs.scope,
            agent_id=obs.agent_id,
            confidence=min(0.55 + 0.07 * (len(peers) - PATTERN_THRESHOLD), 0.75),
            positive_evidence=evidence,
            negative_evidence=[],
            observation_ids=obs_ids,
            status='active',
            pattern_key=obs.pattern_key,
            created_at=now,
            last_updated=now,
            last_reinforced=now,
            curator='ledger' if obs.scope == 'shared' else '',
        )
        errors = claim.validate()
        if errors:
            raise ValueError('; '.join(errors))

        def _mut(data):
            data = data or {'schema_version': LEARNING_SCHEMA_VERSION, 'observations': {}, 'claims': {}}
            data.setdefault('claims', {})[claim.claim_id] = asdict(claim)
            return data

        update_json(path, _mut, default={
            'schema_version': LEARNING_SCHEMA_VERSION, 'observations': {}, 'claims': {},
        })
        return claim

    def reinforce(self, claim_id: str, evidence_id: str, *, actor: str = 'ledger') -> LearnedClaim:
        self.policy.require(actor, 'learning.reinforce')
        claim = self.store.get_claim(claim_id)
        if claim is None:
            raise KeyError(claim_id)
        if claim.scope == 'shared':
            self.policy.require(actor, 'learning.shared_write')
        now = time.time()
        pos = list(claim.positive_evidence)
        if evidence_id not in pos:
            pos.append(evidence_id)
        claim.positive_evidence = pos[-40:]
        before = claim.confidence
        claim.confidence = min(CONF_CEIL, _decayed_confidence(claim, now) + 0.06)
        claim.last_reinforced = now
        claim.last_updated = now
        hist = list(claim.confidence_history or [])
        hist.append({'at': now, 'confidence': claim.confidence, 'delta': round(claim.confidence - before, 4), 'op': 'reinforce', 'evidence_id': evidence_id})
        claim.confidence_history = hist[-30:]
        if claim.status == 'weakened' and claim.confidence >= 0.45:
            claim.status = 'active'
        return self._write_claim(claim)

    def contradict(self, claim_id: str, evidence_id: str, *, actor: str = 'ledger') -> LearnedClaim:
        self.policy.require(actor, 'learning.reinforce')
        claim = self.store.get_claim(claim_id)
        if claim is None:
            raise KeyError(claim_id)
        if claim.scope == 'shared':
            self.policy.require(actor, 'learning.shared_write')
        now = time.time()
        neg = list(claim.negative_evidence)
        if evidence_id not in neg:
            neg.append(evidence_id)
        claim.negative_evidence = neg[-40:]
        claim.contradiction_count = int(claim.contradiction_count or 0) + 1
        before = claim.confidence
        claim.confidence = max(CONF_FLOOR, _decayed_confidence(claim, now) - 0.12)
        claim.last_updated = now
        hist = list(claim.confidence_history or [])
        hist.append({'at': now, 'confidence': claim.confidence, 'delta': round(claim.confidence - before, 4), 'op': 'contradict', 'evidence_id': evidence_id})
        claim.confidence_history = hist[-30:]
        if claim.confidence < 0.35:
            claim.status = 'weakened'
        if claim.confidence <= CONF_FLOOR + 0.02 and claim.contradiction_count >= 3:
            claim.status = 'retired'
        return self._write_claim(claim)

    def revise(self, claim_id: str, new_claim_text: str, *, actor: str, evidence_id: str) -> LearnedClaim:
        """Contradictory evidence that replaces the claim wording while keeping lineage."""
        claim = self.contradict(claim_id, evidence_id, actor=actor)
        old_text = claim.claim
        claim.claim = new_claim_text.strip()
        claim.pattern_key = pattern_key(claim.learning_type, new_claim_text)
        claim.last_updated = time.time()
        rev = list(claim.revision_history or [])
        rev.append({
            'at': claim.last_updated,
            'from': old_text,
            'to': claim.claim,
            'evidence_id': evidence_id,
            'actor': actor,
        })
        claim.revision_history = rev[-20:]
        if claim.status == 'retired':
            claim.status = 'weakened'
            claim.confidence = max(0.4, claim.confidence)
        return self._write_claim(claim)

    def _write_claim(self, claim: LearnedClaim) -> LearnedClaim:
        path = self._path_for(claim.scope, claim.agent_id if claim.scope == 'private' else 'keep')

        def _mut(data):
            data = data or {'schema_version': LEARNING_SCHEMA_VERSION, 'observations': {}, 'claims': {}}
            data.setdefault('claims', {})[claim.claim_id] = asdict(claim)
            return data

        update_json(path, _mut, default={
            'schema_version': LEARNING_SCHEMA_VERSION, 'observations': {}, 'claims': {},
        })
        return claim

    def apply_decay(self, *, now: Optional[float] = None) -> int:
        """Apply time decay; optional `now` for tests."""
        n = 0
        for claim in self.store.list_claims(include_decayed=False):
            new_c = _decayed_confidence(claim, now)
            if abs(new_c - claim.confidence) > 0.001:
                claim.confidence = round(new_c, 4)
                claim.last_updated = now or time.time()
                if claim.confidence < 0.3 and claim.status == 'active':
                    claim.status = 'weakened'
                self._write_claim(claim)
                n += 1
        return n

    def claim_card(self, claim: LearnedClaim) -> dict:
        return {
            'claim_id': claim.claim_id,
            'claim': claim.claim,
            'learning_type': claim.learning_type,
            'scope': claim.scope,
            'scope_label': 'shared Keep' if claim.scope == 'shared' else f'private agent ({claim.agent_id})',
            'agent_id': claim.agent_id,
            'confidence': round(claim.confidence, 4),
            'status': claim.status,
            'evidence_count': len(claim.positive_evidence or []) + len(claim.negative_evidence or []),
            'positive_evidence_count': len(claim.positive_evidence or []),
            'negative_evidence_count': len(claim.negative_evidence or []),
            'contradictions': claim.contradiction_count,
            'last_updated': claim.last_updated,
            'last_reinforced': claim.last_reinforced,
            'curator': claim.curator,
            'observation_count': len(claim.observation_ids or []),
        }

    def why(self, claim_id: str) -> dict:
        claim = self.store.get_claim(claim_id)
        if claim is None:
            raise KeyError(claim_id)
        supporting = [
            asdict(o) for o in self.store.list_observations(
                scope=claim.scope,
                agent_id=claim.agent_id if claim.scope == 'private' else None,
                pattern_key=claim.pattern_key,
                limit=40,
            )
            if o.observation_id in (claim.observation_ids or [])
            or set(o.evidence_ids or []) & set(claim.positive_evidence or [])
        ]
        # Observations whose evidence appears only in negative set
        contradicting_obs = [
            asdict(o) for o in self.store.list_observations(
                scope=claim.scope,
                agent_id=claim.agent_id if claim.scope == 'private' else None,
                limit=80,
            )
            if set(o.evidence_ids or []) & set(claim.negative_evidence or [])
        ]
        return {
            'claim_id': claim.claim_id,
            'claim': claim.claim,
            'learning_type': claim.learning_type,
            'scope': claim.scope,
            'agent_id': claim.agent_id,
            'confidence': claim.confidence,
            'status': claim.status,
            'positive_evidence': list(claim.positive_evidence),
            'negative_evidence': list(claim.negative_evidence),
            'supporting_observations': supporting[:20],
            'contradicting_observations': contradicting_obs[:20],
            'source_events_jobs': list(dict.fromkeys(
                list(claim.positive_evidence) + list(claim.negative_evidence)
            ))[:40],
            'confidence_history': list(claim.confidence_history or [])[-20:],
            'revision_history': list(claim.revision_history or [])[-20:],
            'observation_ids': list(claim.observation_ids),
            'contradiction_count': claim.contradiction_count,
            'last_updated': claim.last_updated,
            'last_reinforced': claim.last_reinforced,
            'curator': claim.curator,
            'thresholds': {
                'pattern_threshold': PATTERN_THRESHOLD,
                'note': 'Weak evidence does not graduate until PATTERN_THRESHOLD observations.',
            },
            'rule': 'Learned state must be evidence-backed and revisable.',
            'separations': {
                'memory': 'what happened (episodes)',
                'living_dossier': 'observed traits with supporting IDs',
                'emotion': 'adaptive affective state',
                'learning': 'patterned claims with confidence, contradiction, decay, revision',
            },
        }

    def agent_learning_surface(self, agent_id: str) -> dict:
        private = [self.claim_card(c) for c in self.store.list_claims(
            agent_id=agent_id, scope='private', min_confidence=0.0,
        ) if c.status != 'retired']
        shared = [self.claim_card(c) for c in self.store.list_claims(
            scope='shared', min_confidence=0.35,
        ) if c.status != 'retired']
        return {
            'agent_id': agent_id,
            'title': "WHAT I'VE LEARNED",
            'private': private[:40],
            'shared_keep': shared[:40],
            'note': (
                'Private preferences stay with this agent. Shared Keep learning '
                '(Ledger-curated) is available where relevant.'
            ),
        }

    def board_payload(self) -> dict:
        shared = [self.claim_card(c) for c in self.store.list_claims(scope='shared') if c.status != 'retired']
        private_by_agent = {}
        for c in self.store.list_claims(scope='private'):
            if c.status == 'retired':
                continue
            private_by_agent.setdefault(c.agent_id, []).append(self.claim_card(c))
        return {
            'surface': 'learning',
            'summary': self.summary(),
            'shared_keep': shared[:60],
            'private_by_agent': private_by_agent,
            'separations': {
                'memory': '≠ learning',
                'living_dossier': '≠ learning',
                'emotion': '≠ learning',
            },
        }

    def context_lines(self, agent_id: str, *, limit: int = 8) -> list[str]:
        lines = []
        private = self.store.list_claims(agent_id=agent_id, scope='private', min_confidence=0.35)[: limit // 2 + 1]
        shared = self.store.list_claims(scope='shared', min_confidence=0.4)[: limit // 2 + 1]
        for c in private + shared:
            if c.status == 'retired':
                continue
            tag = 'shared' if c.scope == 'shared' else 'private'
            lines.append(
                f"- [{c.learning_type}/{tag}] {c.claim} (conf={c.confidence:.2f}, "
                f"+ev={len(c.positive_evidence)} -ev={len(c.negative_evidence)})"
            )
            if len(lines) >= limit:
                break
        return lines

    def summary(self) -> dict:
        private_n = 0
        for path in self.layout.user_learning.glob('private_*.json'):
            private_n += len((read_json(path, default={}).get('claims') or {}))
        shared = self.store.list_claims(scope='shared', include_decayed=False)
        return {
            'surface': 'learning_engine',
            'model': 'evidence_backed_revisable',
            'learning_types': list(LEARNING_TYPES),
            'pattern_threshold': PATTERN_THRESHOLD,
            'private_claims': private_n,
            'shared_claims': len(shared),
            'active_shared': sum(1 for c in shared if c.status == 'active'),
            'note': (
                'Learning ≠ memory. Claims graduate from repeated observations, '
                'carry confidence/evidence, and revise under contradiction.'
            ),
            'curator': 'ledger',
        }


def learn_from_autonomy_outcome(
    layout: Optional[StateLayout] = None,
    *,
    job,
    success: bool,
    method: str = '',
    peer_verdict: str = '',
    evidence_ids: Optional[list] = None,
) -> dict:
    """Explicit autonomy close path → learning observation / reinforce / contradict."""
    layout = layout or resolve_layout()
    engine = LearningEngine(layout)
    ev = list(evidence_ids or [])
    ev.append(job.job_id)
    if peer_verdict:
        ev.append(f'peer:{peer_verdict}:{job.job_id}')
    method = (method or getattr(job, 'result', None) or 'standard autonomous repair')[:100]
    domain = job.domain or 'coordination'
    actor = job.assigned_agent if job.assigned_agent in (
        'vector', 'sentry', 'aria', 'ledger', 'muse',
    ) else 'vector'
    out = {'observations': [], 'reinforced': [], 'contradicted': []}
    if success:
        obs = ingest_operational_success(
            engine, method=method, domain=domain, job_id=job.job_id, actor=actor,
        )
        out['observations'].append(obs.observation_id)
        for claim in engine.store.list_claims(scope='shared', learning_type='operational'):
            if claim.pattern_key == obs.pattern_key or job.job_id in (claim.positive_evidence or []):
                for eid in ev[1:]:
                    engine.reinforce(claim.claim_id, eid, actor='ledger')
                    out['reinforced'].append(claim.claim_id)
                break
    else:
        for claim in engine.store.list_claims(scope='shared', learning_type='operational'):
            if domain in claim.claim:
                engine.contradict(claim.claim_id, job.job_id, actor='ledger')
                out['contradicted'].append(claim.claim_id)
        obs = engine.observe(
            actor,
            f'operational caution: for {domain}, method "{method}" failed verification',
            learning_type='operational',
            evidence_ids=[job.job_id],
            scope='shared',
            actor='ledger',
        )
        out['observations'].append(obs.observation_id)
    return out


# --- Pattern helpers used by autonomy / pipeline ---

_CONCISE = re.compile(r'\b(concise|brief|short|tl;?dr|bullet)\b', re.I)
_VERBOSE = re.compile(r'\b(detailed|thorough|long.?form|elaborate)\b', re.I)


def ingest_owner_message(
    engine: LearningEngine,
    *,
    text: str,
    event_id: str,
    actor: str = 'ledger',
) -> Optional[LearningObservation]:
    if not text or not event_id:
        return None
    if _CONCISE.search(text):
        return engine.observe(
            'ledger',
            'owner prefers concise technical summaries',
            learning_type='owner_preference',
            evidence_ids=[event_id],
            scope='shared',
            actor=actor,
        )
    if _VERBOSE.search(text):
        return engine.observe(
            'ledger',
            'owner prefers detailed thorough explanations',
            learning_type='owner_preference',
            evidence_ids=[event_id],
            scope='shared',
            actor=actor,
        )
    return None


def ingest_operational_success(
    engine: LearningEngine,
    *,
    method: str,
    domain: str,
    job_id: str,
    actor: str = 'vector',
) -> LearningObservation:
    return engine.observe(
        actor,
        f'operational heuristic: for {domain}, prefer method "{method}"',
        learning_type='operational',
        evidence_ids=[job_id],
        scope='shared',
        actor=actor if actor in ('vector', 'sentry', 'aria', 'ledger') else 'vector',
    )
