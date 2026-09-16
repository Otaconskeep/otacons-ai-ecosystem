"""First-class vulnerability modeling for Expansion agents.

Distinguishes weakness / crutch / compulsion / addictive tendency / fear /
anxiety / insecurity / self-conscious area / avoidance behavior.

These values influence diary, relationships, emotional transitions, and
conversational behavior — they must NOT make operational agents
intentionally unreliable at their jobs.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum


class VulnerabilityKind(str, Enum):
    WEAKNESS = 'weakness'
    CRUTCH = 'crutch'
    COMPULSION = 'compulsion'
    ADDICTIVE_TENDENCY = 'addictive_tendency'
    FEAR = 'fear'
    ANXIETY = 'anxiety'
    INSECURITY = 'insecurity'
    SELF_CONSCIOUS = 'self_conscious'
    SELF_CONSCIOUS_AREA = 'self_conscious_area'  # P2 alias / required surface name
    AVOIDANCE = 'avoidance'
    AVOIDANCE_BEHAVIOR = 'avoidance_behavior'  # P2 alias / required surface name
    SHAME_POINT = 'shame_point'
    BLIND_SPOT = 'blind_spot'
    SECRET = 'secret'
    BAD_HABIT = 'bad_habit'
    COPING_MECHANISM = 'coping_mechanism'


# Kinds that may color social/emotional behavior but must not degrade job reliability.
OPERATIONAL_SAFE_KINDS = frozenset(VulnerabilityKind)


@dataclass
class Vulnerability:
    kind: str
    label: str
    intensity: float = 0.5          # 0..1
    description: str = ''
    triggers: tuple = ()
    affects_operations: bool = False  # must remain False for default product agents


@dataclass
class VulnerabilityProfile:
    items: tuple = ()
    # Explicit product rule: defaults never mark operational unreliability
    allow_operational_impairment: bool = False


def validate_vulnerability(v: Vulnerability) -> list:
    errors = []
    kinds = {k.value for k in VulnerabilityKind}
    if v.kind not in kinds:
        errors.append(f'unknown vulnerability kind {v.kind!r}')
    if not v.label or not v.label.strip():
        errors.append('vulnerability label required')
    if not (0.0 <= v.intensity <= 1.0):
        errors.append('intensity must be in [0,1]')
    if v.affects_operations:
        errors.append(
            'affects_operations=True forbidden for Expansion defaults — '
            'vulnerabilities must not make agents operationally unreliable'
        )
    return errors


def validate_vulnerability_profile(p: VulnerabilityProfile) -> list:
    errors = []
    if p.allow_operational_impairment:
        errors.append('allow_operational_impairment must be False for product dossiers')
    for i, item in enumerate(p.items):
        v = item if isinstance(item, Vulnerability) else Vulnerability(**item)
        for err in validate_vulnerability(v):
            errors.append(f'items[{i}]: {err}')
    return errors


def vulnerability_from_dict(d: dict) -> VulnerabilityProfile:
    items = []
    for raw in d.get('items') or ():
        if isinstance(raw, Vulnerability):
            items.append(raw)
        else:
            rd = dict(raw)
            if isinstance(rd.get('triggers'), list):
                rd['triggers'] = tuple(rd['triggers'])
            items.append(Vulnerability(**rd))
    return VulnerabilityProfile(
        items=tuple(items),
        allow_operational_impairment=bool(d.get('allow_operational_impairment', False)),
    )


def to_dict(p: VulnerabilityProfile) -> dict:
    return asdict(p)
