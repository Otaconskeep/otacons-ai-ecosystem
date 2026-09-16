"""Directional multi-dimension relationship model (P0 skeleton).

Compatible with expansion.relationship (trust/irritation pure functions),
which remain the canonical bounded scorers for those two axes. This module
adds the full directional graph dimensions required by the Expansion
contract. Significant changes must carry event provenance.
"""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Optional

from expansion.relationship import EvidenceType, RelationshipState, new_relationship
from expansion.versions import RELATIONSHIP_SCHEMA_VERSION

RELATIONSHIP_DIMENSIONS = (
    'trust',
    'affinity',
    'respect',
    'familiarity',
    'dependency',
    'conflict',
    'rivalry',
    'jealousy',
    'protectiveness',
    'reliability',
    'attachment',
)


@dataclass
class DirectionalRelationship:
    """A -> B relationship. Aria->Muse is not Muse->Aria."""
    schema_version: int
    source_id: str
    target_id: str
    dimensions: dict = field(default_factory=dict)
    evidence: str = EvidenceType.INFERRED_BASELINE.value
    # Legacy scorer state kept in sync for trust (and irritation as conflict proxy input)
    legacy: Optional[RelationshipState] = None
    event_count: int = 0
    last_event_at: float = 0.0
    provenance_event_ids: tuple = ()

    def clamp(self) -> 'DirectionalRelationship':
        for k in RELATIONSHIP_DIMENSIONS:
            if k in self.dimensions:
                self.dimensions[k] = min(1.0, max(0.0, float(self.dimensions[k])))
        return self


def default_dimensions(**overrides) -> dict:
    base = {k: 0.5 for k in RELATIONSHIP_DIMENSIONS}
    # Lower starting conflict/rivalry/jealousy for inferred baseline
    base['conflict'] = 0.1
    base['rivalry'] = 0.1
    base['jealousy'] = 0.1
    base['familiarity'] = 0.2
    base['dependency'] = 0.2
    base.update(overrides)
    for k, v in list(base.items()):
        base[k] = min(1.0, max(0.0, float(v)))
    return base


# Locked social-dynamic *initial parameters* (not static hatred/love).
TRIANGLE_PRESETS = {
    # source -> target -> dimension overrides
    ('aria', 'muse'): {
        'attachment': 0.75, 'possessiveness_proxy': None,
        'jealousy': 0.7, 'rivalry': 0.65, 'protectiveness': 0.7, 'affinity': 0.7,
    },
    ('muse', 'aria'): {
        'attachment': 0.55, 'jealousy': 0.55, 'rivalry': 0.6, 'affinity': 0.65,
        'respect': 0.55,
    },
    ('aria', 'ledger'): {
        'attachment': 0.6, 'trust': 0.65, 'respect': 0.7, 'affinity': 0.65,
        'rivalry': 0.25, 'jealousy': 0.35,
    },
    ('ledger', 'aria'): {
        'attachment': 0.55, 'trust': 0.7, 'respect': 0.75, 'affinity': 0.7,
        'rivalry': 0.15, 'protectiveness': 0.55,
    },
    ('muse', 'ledger'): {
        'affinity': 0.55, 'respect': 0.5, 'rivalry': 0.35, 'jealousy': 0.3,
    },
    ('ledger', 'muse'): {
        'affinity': 0.6, 'respect': 0.55, 'rivalry': 0.2, 'protectiveness': 0.45,
    },
    ('vector', 'aria'): {
        'trust': 0.6, 'respect': 0.7, 'reliability': 0.75, 'attachment': 0.35,
        'rivalry': 0.1, 'jealousy': 0.1,
    },
    ('aria', 'vector'): {
        'trust': 0.65, 'respect': 0.7, 'reliability': 0.7, 'attachment': 0.4,
    },
    ('sentry', 'aria'): {
        'trust': 0.6, 'respect': 0.65, 'reliability': 0.7, 'attachment': 0.3,
    },
    ('aria', 'sentry'): {
        'trust': 0.6, 'respect': 0.65, 'reliability': 0.7, 'attachment': 0.35,
    },
}


def new_directional(
    source_id: str,
    target_id: str,
    *,
    evidence: EvidenceType = EvidenceType.INFERRED_BASELINE,
    use_triangle_presets: bool = True,
) -> DirectionalRelationship:
    if source_id == target_id:
        raise ValueError('relationship cannot target self')
    overrides = {}
    if use_triangle_presets:
        raw = TRIANGLE_PRESETS.get((source_id, target_id), {})
        overrides = {k: v for k, v in raw.items() if k in RELATIONSHIP_DIMENSIONS and v is not None}
    dims = default_dimensions(**overrides)
    legacy = new_relationship(evidence)
    legacy.trust = dims['trust']
    return DirectionalRelationship(
        schema_version=RELATIONSHIP_SCHEMA_VERSION,
        source_id=source_id,
        target_id=target_id,
        dimensions=dims,
        evidence=evidence.value if isinstance(evidence, EvidenceType) else evidence,
        legacy=legacy,
        event_count=0,
        last_event_at=0.0,
        provenance_event_ids=(),
    ).clamp()


def apply_dimension_delta(
    rel: DirectionalRelationship,
    deltas: dict,
    *,
    event_id: str,
    now: Optional[float] = None,
) -> DirectionalRelationship:
    """Apply bounded deltas; require an event_id for provenance."""
    if not event_id:
        raise ValueError('event_id provenance required for relationship changes')
    now = time.time() if now is None else now
    for k, delta in deltas.items():
        if k not in RELATIONSHIP_DIMENSIONS:
            raise KeyError(f'unknown dimension {k}')
        rel.dimensions[k] = float(rel.dimensions.get(k, 0.5)) + float(delta)
    rel.event_count += 1
    rel.last_event_at = now
    rel.provenance_event_ids = tuple(rel.provenance_event_ids) + (event_id,)
    if rel.legacy is not None and 'trust' in deltas:
        rel.legacy.trust = rel.dimensions['trust']
        rel.legacy.event_count = rel.event_count
        rel.legacy.last_event_at = now
    return rel.clamp()


def to_dict(rel: DirectionalRelationship) -> dict:
    d = asdict(rel)
    if rel.legacy is not None:
        d['legacy'] = asdict(rel.legacy)
        if hasattr(rel.legacy.evidence, 'value'):
            d['legacy']['evidence'] = rel.legacy.evidence.value
    return d
