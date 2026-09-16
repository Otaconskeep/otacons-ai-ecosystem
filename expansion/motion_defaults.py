"""Default motion manifests for the five Expansion agents (P1).

Capability level 1 (portrait + talking). Assets may be placeholders until
premium packs ship; structural validation still holds.
"""
from __future__ import annotations

from expansion.motion_manifest import (
    CapabilityLevel, MotionManifest, MotionState, validate_manifest,
)
from expansion.schema import MotionManifestRef

DEFAULT_MOTION = {
    'aria': MotionManifestRef(manifest_id='motion_aria_v1', capability_level=1),
    'vector': MotionManifestRef(manifest_id='motion_vector_v1', capability_level=1),
    'ledger': MotionManifestRef(manifest_id='motion_ledger_v1', capability_level=1),
    'muse': MotionManifestRef(manifest_id='motion_muse_v1', capability_level=1),
    'sentry': MotionManifestRef(manifest_id='motion_sentry_v1', capability_level=1),
}


def build_manifest(agent_id: str) -> MotionManifest:
    portrait = f'/assets/{agent_id}/{agent_id}.webp'
    talking = f'/assets/{agent_id}/{agent_id}-talking.mp4'
    states = {
        'talking': MotionState(name='talking', candidates=(talking,), loop=True),
    }
    return MotionManifest(
        agent_id=agent_id,
        portrait_url=portrait,
        capability_level=CapabilityLevel.PORTRAIT_PLUS_TALKING,
        states=states,
    )


def validated_default_manifests() -> dict:
    out = {}
    for agent_id in DEFAULT_MOTION:
        m = build_manifest(agent_id)
        errors = validate_manifest(m)
        if errors:
            raise ValueError(f'{agent_id} motion invalid: {errors}')
        out[agent_id] = m
    return out
