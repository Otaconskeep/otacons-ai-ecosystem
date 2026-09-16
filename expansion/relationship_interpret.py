"""Higher-level relationship interpretation without destroying raw dimensions."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from expansion.relationship_store import RelationshipStore
from expansion.state_layout import StateLayout, resolve_layout


@dataclass
class RelationshipSummary:
    source_id: str
    target_id: str
    label: str
    narrative: str
    dimensions: dict
    provenance_event_ids: list


def interpret_edge(dims: dict) -> tuple[str, str]:
    rivalry = float(dims.get('rivalry', 0))
    jealousy = float(dims.get('jealousy', 0))
    trust = float(dims.get('trust', 0.5))
    affinity = float(dims.get('affinity', 0.5))
    attachment = float(dims.get('attachment', 0.5))
    conflict = float(dims.get('conflict', 0))
    respect = float(dims.get('respect', 0.5))

    if rivalry >= 0.55 and attachment >= 0.5:
        return 'competitive_attachment', (
            'High attachment coexists with rivalry — competitive bond, not static hatred.'
        )
    if jealousy >= 0.6 and attachment >= 0.45:
        return 'jealous_attachment', 'Jealousy is elevated alongside attachment.'
    if trust >= 0.7 and respect >= 0.65 and rivalry < 0.35:
        return 'trusted_ally', 'High trust and respect with low rivalry.'
    if conflict >= 0.55:
        return 'strained', 'Conflict is currently elevated.'
    if affinity >= 0.65 and trust >= 0.55:
        return 'warm_regard', 'Affinity and trust are both healthy.'
    if trust < 0.35:
        return 'wary', 'Trust is low; approach carefully.'
    return 'steady', 'No extreme derived pattern — raw dimensions dominate.'


class RelationshipInterpreter:
    def __init__(self, layout: Optional[StateLayout] = None):
        self.layout = layout or resolve_layout()
        self.store = RelationshipStore(self.layout)

    def summarize(self, source_id: str, target_id: str) -> RelationshipSummary:
        rel = self.store.get_or_create(source_id, target_id)
        label, narrative = interpret_edge(rel.dimensions)
        return RelationshipSummary(
            source_id=source_id,
            target_id=target_id,
            label=label,
            narrative=narrative,
            dimensions={k: round(v, 4) for k, v in rel.dimensions.items()},
            provenance_event_ids=list(rel.provenance_event_ids[-10:]),
        )

    def matrix(self, agent_ids: Optional[list] = None) -> list[dict]:
        agent_ids = agent_ids or ['aria', 'vector', 'ledger', 'muse', 'sentry', 'user_primary']
        out = []
        for src in agent_ids:
            for dst in agent_ids:
                if src == dst:
                    continue
                s = self.summarize(src, dst)
                out.append({
                    'source': s.source_id,
                    'target': s.target_id,
                    'label': s.label,
                    'narrative': s.narrative,
                    'dimensions': s.dimensions,
                    'provenance_event_ids': s.provenance_event_ids,
                })
        return out

    def why(self, source_id: str, target_id: str) -> dict:
        s = self.summarize(source_id, target_id)
        return {
            'source': source_id,
            'target': target_id,
            'label': s.label,
            'narrative': s.narrative,
            'dimensions': s.dimensions,
            'supporting_event_ids': s.provenance_event_ids,
            'rule': 'Derived labels summarize raw dimensions; they never replace them.',
        }
