"""Optional Expansion capability contracts.

Heavy integrations (Video Studio, Home Assistant, Discord/n8n) must never
block Core or base Expansion. Missing config → UNAVAILABLE / NOT_CONFIGURED,
not FAILED for the rest of the product.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Optional


class CapabilityState(str, Enum):
    READY = 'READY'
    LIMITED = 'LIMITED'
    UNAVAILABLE = 'UNAVAILABLE'
    NOT_CONFIGURED = 'NOT_CONFIGURED'
    DEGRADED = 'DEGRADED'
    FAILED = 'FAILED'


@dataclass
class CapabilityReport:
    capability_id: str
    owner_agent: str
    state: str
    detail: str = ''
    config_keys_present: list = field(default_factory=list)
    discovery: dict = field(default_factory=dict)
    optional: bool = True

    def to_dict(self) -> dict:
        return asdict(self)


def _forbidden_private_paths(blob: str) -> list:
    bad = (
        '192.168.50.219', '192.168.50.221', '192.168.50.192', '192.168.50.69',
        '/opt/otacon', 'ai9.local',
    )
    return [s for s in bad if s in (blob or '')]
