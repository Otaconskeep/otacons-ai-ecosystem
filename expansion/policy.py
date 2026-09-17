"""Policy / authority engine — pre-authorized capability boundaries.

Replaces routine human approval with:
  agent wants action → policy checks → authorize | deny | escalate

Hard boundaries (never auto-approved) stay separate from domain autonomy.
"""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Optional

from expansion.persist import atomic_write_json, read_json
from expansion.state_layout import StateLayout, resolve_layout

POLICY_SCHEMA_VERSION = 1

# Tools / capabilities agents may request. Executors wire later; policy is SoT.
CAPABILITY_CATALOG = (
    # Research
    'web.search', 'web.fetch', 'docs.search', 'github.read', 'repo.search',
    # Repo / engineering
    'repo.read', 'repo.write', 'git.branch', 'git.commit', 'tests.run',
    'shell.execute', 'docker.inspect', 'docker.manage',
    'services.inspect', 'services.restart', 'logs.read', 'files.read', 'files.write',
    # REX / jobs
    'jobs.create', 'jobs.assign', 'jobs.reprioritize', 'jobs.cancel',
    'jobs.verify', 'jobs.close', 'jobs.move', 'jobs.discover',
    # Continuity / learning
    'docs.update', 'research.record', 'journal.write', 'continuity.update',
    'learning.observe', 'learning.reinforce', 'learning.shared_write', 'learning.read',
    # Security
    'security.scan', 'security.quarantine', 'security.verify',
    # Creative
    'creative.edit', 'studio.prepare',
)

# Never auto-authorized — escalate to installing owner.
HARD_BOUNDARIES = frozenset({
    'destroy_user_data',
    'spend_money',
    'change_ownership',
    'external_financial',
    'publish_as_user',
    'disable_audit',
    'disable_security_controls',
})

# Default Keep autonomy grants (owner can tighten later via preferences).
DEFAULT_AGENT_GRANTS = {
    'aria': frozenset({
        'web.search', 'web.fetch', 'docs.search', 'github.read', 'repo.search',
        'jobs.create', 'jobs.assign', 'jobs.reprioritize', 'jobs.cancel',
        'jobs.verify', 'jobs.close', 'jobs.move', 'jobs.discover',
        'journal.write', 'continuity.update',
        'learning.observe', 'learning.reinforce', 'learning.shared_write', 'learning.read',
    }),
    'vector': frozenset({
        'web.search', 'web.fetch', 'docs.search', 'github.read', 'repo.search',
        'repo.read', 'repo.write', 'git.branch', 'git.commit', 'tests.run',
        'shell.execute', 'docker.inspect', 'docker.manage',
        'services.inspect', 'services.restart', 'logs.read', 'files.read', 'files.write',
        'jobs.move', 'jobs.discover', 'research.record',
        'learning.observe', 'learning.reinforce', 'learning.shared_write', 'learning.read',
    }),
    'ledger': frozenset({
        'web.search', 'web.fetch', 'docs.search', 'github.read', 'repo.search',
        'repo.read', 'docs.update', 'research.record', 'journal.write',
        'continuity.update', 'jobs.verify', 'jobs.move', 'jobs.discover',
        'learning.observe', 'learning.reinforce', 'learning.shared_write', 'learning.read',
    }),
    'muse': frozenset({
        'web.search', 'web.fetch', 'docs.search',
        'repo.read', 'files.read', 'files.write', 'creative.edit', 'studio.prepare',
        'jobs.move', 'jobs.discover', 'research.record',
        'learning.observe', 'learning.reinforce', 'learning.read',
    }),
    'sentry': frozenset({
        'web.search', 'web.fetch', 'docs.search', 'github.read',
        'security.scan', 'security.quarantine', 'security.verify',
        'services.inspect', 'services.restart', 'logs.read', 'docker.inspect',
        'jobs.create', 'jobs.discover', 'jobs.move', 'jobs.verify', 'research.record',
        'learning.observe', 'learning.reinforce', 'learning.shared_write', 'learning.read',
    }),
}

AGENT_ROLES = {
    'aria': 'Prioritize work, assign agents, resolve conflicts, approve plans internally',
    'vector': 'Code, infrastructure, Docker, deployments, repairs, technical R&D',
    'ledger': 'Research, documentation, evidence, history, continuity, verification',
    'muse': 'Creative work, Video Studio, UI/media work, creative R&D',
    'sentry': 'Security, monitoring, health checks, incident detection and response',
}


@dataclass
class PolicyDecision:
    allowed: bool
    agent_id: str
    capability: str
    reason: str
    disposition: str  # authorize | deny | escalate
    checked_at: float = 0.0

    def __post_init__(self):
        if not self.checked_at:
            self.checked_at = time.time()


@dataclass
class PolicyBundle:
    schema_version: int = POLICY_SCHEMA_VERSION
    grants: dict = field(default_factory=dict)
    hard_boundaries: list = field(default_factory=list)
    updated_at: float = 0.0


class PolicyEngine:
    """Authority checks for autonomous agent actions."""

    def __init__(self, layout: Optional[StateLayout] = None):
        self.layout = layout or resolve_layout()
        self.layout.user_preferences.mkdir(parents=True, exist_ok=True)
        self._path = self.layout.user_preferences / 'autonomy_policy.json'

    def load(self) -> PolicyBundle:
        raw = read_json(self._path, default=None)
        if not raw:
            return self.seed_defaults()
        grants = {k: set(v) for k, v in (raw.get('grants') or {}).items()}
        return PolicyBundle(
            schema_version=raw.get('schema_version', POLICY_SCHEMA_VERSION),
            grants=grants,
            hard_boundaries=list(raw.get('hard_boundaries') or sorted(HARD_BOUNDARIES)),
            updated_at=float(raw.get('updated_at') or 0),
        )

    def seed_defaults(self) -> PolicyBundle:
        bundle = PolicyBundle(
            grants={k: set(v) for k, v in DEFAULT_AGENT_GRANTS.items()},
            hard_boundaries=sorted(HARD_BOUNDARIES),
            updated_at=time.time(),
        )
        self.save(bundle)
        return bundle

    def save(self, bundle: PolicyBundle) -> None:
        atomic_write_json(self._path, {
            'schema_version': bundle.schema_version,
            'grants': {k: sorted(v) for k, v in bundle.grants.items()},
            'hard_boundaries': list(bundle.hard_boundaries),
            'updated_at': bundle.updated_at or time.time(),
            'catalog': list(CAPABILITY_CATALOG),
            'roles': dict(AGENT_ROLES),
            'note': (
                'Policy replaces routine approval. Hard boundaries escalate to owner. '
                'Domain work inside grants is autonomous.'
            ),
        })

    def check(self, agent_id: str, capability: str) -> PolicyDecision:
        cap = (capability or '').strip()
        agent = (agent_id or '').strip().lower()
        if not agent or not cap:
            return PolicyDecision(
                False, agent, cap, 'agent_id and capability required', 'deny',
            )
        if cap in HARD_BOUNDARIES:
            return PolicyDecision(
                False, agent, cap,
                'hard boundary — owner oversight required',
                'escalate',
            )
        bundle = self.load()
        if cap in (bundle.hard_boundaries or []):
            return PolicyDecision(
                False, agent, cap,
                'hard boundary — owner oversight required',
                'escalate',
            )
        granted = bundle.grants.get(agent) or set()
        if isinstance(granted, list):
            granted = set(granted)
        if cap in granted:
            return PolicyDecision(
                True, agent, cap, 'pre-authorized by Keep policy', 'authorize',
            )
        return PolicyDecision(
            False, agent, cap,
            f'capability {cap!r} not granted to {agent}',
            'deny',
        )

    def require(self, agent_id: str, capability: str) -> PolicyDecision:
        decision = self.check(agent_id, capability)
        if not decision.allowed:
            raise PermissionError(
                f'{decision.disposition}: {agent_id}/{capability} — {decision.reason}'
            )
        return decision

    def summary(self) -> dict:
        bundle = self.load()
        return {
            'schema_version': bundle.schema_version,
            'roles': dict(AGENT_ROLES),
            'grants': {k: sorted(v) for k, v in bundle.grants.items()},
            'hard_boundaries': list(bundle.hard_boundaries),
            'catalog': list(CAPABILITY_CATALOG),
            'model': 'policy_replaces_approval',
        }
