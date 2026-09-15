"""Machine-readable readiness state for the Otacon Expansion Dashboard.

Required components must all read READY for the Dashboard to call itself
healthy. Optional components (Discord, Home Assistant, Video Studio, n8n,
the infra dashboard) never block that -- one optional subsystem being down
must never make the rest look broken.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ReadinessState(str, Enum):
    READY = 'READY'
    LIMITED = 'LIMITED'
    NOT_CONFIGURED = 'NOT_CONFIGURED'
    OFFLINE = 'OFFLINE'
    DEGRADED = 'DEGRADED'
    UNAVAILABLE = 'UNAVAILABLE'
    FAILED = 'FAILED'


REQUIRED_COMPONENTS = (
    'CORE', 'AGENTS', 'VOICE', 'EMOTIONAL_ENGINE', 'RELATIONSHIPS',
)
OPTIONAL_COMPONENTS = (
    'MOTION', 'VIDEO_STUDIO', 'DISCORD', 'HOME_ASSISTANT', 'N8N', 'INFRA_DASHBOARD',
)


@dataclass
class ReadinessReport:
    components: dict = field(default_factory=dict)  # name -> ReadinessState

    def set(self, name: str, state: ReadinessState) -> None:
        self.components[name] = state

    def overall_core_ready(self) -> bool:
        return all(self.components.get(c) == ReadinessState.READY for c in REQUIRED_COMPONENTS)

    def to_dict(self) -> dict:
        return {k: (v.value if isinstance(v, ReadinessState) else v) for k, v in self.components.items()}
