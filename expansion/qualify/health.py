"""Formal health state definitions for Expansion components."""
from __future__ import annotations

from enum import Enum


class HealthState(str, Enum):
    READY = 'READY'
    DEGRADED = 'DEGRADED'
    FAILED = 'FAILED'
    LIMITED = 'LIMITED'
    UNAVAILABLE = 'UNAVAILABLE'


# Contract notes used by acceptance docs/tests
HEALTH_CONTRACT = {
    HealthState.READY.value: (
        'Component fully operable for its required function.'
    ),
    HealthState.DEGRADED.value: (
        'Required function works with reduced quality; product remains usable.'
    ),
    HealthState.FAILED.value: (
        'Required function broken (e.g. protected bundle cannot decrypt).'
    ),
    HealthState.LIMITED.value: (
        'Partially configured or externally unverified; not a global failure.'
    ),
    HealthState.UNAVAILABLE.value: (
        'Optional capability missing/unconfigured; base Expansion unaffected.'
    ),
}


def overall_expansion_health(component_states: dict) -> str:
    """Derive overall Expansion health from component map.

    Rules:
      - FAILED on required components → FAILED
      - optional UNAVAILABLE/LIMITED alone → READY (or DEGRADED if many limited)
      - Video Studio unavailable must NOT mark Expansion FAILED
    """
    required = {
        'CORE', 'AGENTS', 'EMOTIONAL_ENGINE', 'RELATIONSHIPS', 'PROTECTED_BUNDLE',
    }
    optional = {
        'VIDEO_STUDIO', 'HOME_ASSISTANT', 'DISCORD', 'N8N', 'MOTION',
    }
    for name in required:
        st = component_states.get(name)
        if st == HealthState.FAILED.value:
            # PROTECTED_BUNDLE only required in protected channel installs
            if name == 'PROTECTED_BUNDLE' and component_states.get('CHANNEL') == 'dev':
                continue
            return HealthState.FAILED.value
    # Degraded if any required is DEGRADED/LIMITED
    for name in required:
        st = component_states.get(name)
        if st in (HealthState.DEGRADED.value, HealthState.LIMITED.value):
            return HealthState.DEGRADED.value
    # Optional failures do not fail overall
    return HealthState.READY.value
