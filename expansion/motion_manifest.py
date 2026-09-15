"""Motion manifest schema + validator for Otacon Expansion.

Exists specifically to make one historical bug structurally impossible: a
manifest value holding more than one candidate URL, handed to JavaScript's
fetch() as a raw array, silently comma-joins into a broken URL. Every
candidate is resolved server-side into an explicit flat list[str]; the
frontend never receives a value it could implicitly coerce.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum


class CapabilityLevel(IntEnum):
    STATIC_PORTRAIT = 0
    PORTRAIT_PLUS_TALKING = 1
    IDLE_TALKING_THINKING = 2
    FULL_EMOTIONAL_PACK = 3


REQUIRED_STATES_BY_LEVEL = {
    CapabilityLevel.STATIC_PORTRAIT: (),
    CapabilityLevel.PORTRAIT_PLUS_TALKING: ('talking',),
    CapabilityLevel.IDLE_TALKING_THINKING: ('idle', 'talking', 'thinking'),
    CapabilityLevel.FULL_EMOTIONAL_PACK: (
        'idle', 'talking', 'thinking', 'thinking_hard',
        'happy', 'angry', 'rage', 'sad', 'sad_masked',
    ),
}

LOOPING_STATES = frozenset({'idle', 'talking'})
ONE_SHOT_STATES = frozenset({'happy', 'angry', 'rage', 'sad', 'sad_masked', 'thinking_hard', 'thinking'})


class ManifestError(ValueError):
    pass


@dataclass
class MotionState:
    name: str
    candidates: tuple
    loop: bool
    fallback: str = None
    still_frame_after: str = None  # held-frame tail URL for one-shot states


@dataclass
class MotionManifest:
    agent_id: str
    portrait_url: str
    capability_level: CapabilityLevel
    states: dict = field(default_factory=dict)


def validate_manifest(m: MotionManifest) -> list:
    errors = []
    if not m.portrait_url:
        errors.append('portrait_url is required at every capability level')
    required = REQUIRED_STATES_BY_LEVEL[m.capability_level]
    for state_name in required:
        if state_name not in m.states:
            errors.append(f'capability_level {m.capability_level.name} requires state {state_name!r}')
    for name, st in m.states.items():
        if name != st.name:
            errors.append(f'state key {name!r} does not match MotionState.name {st.name!r}')
        if not st.candidates:
            errors.append(f'state {name!r} has no candidate URLs')
        elif not isinstance(st.candidates, tuple):
            errors.append(
                f'state {name!r} candidates must be a tuple, not {type(st.candidates).__name__} -- '
                f'a bare list/array reaching the frontend is exactly the historical fetch()-coercion bug'
            )
        if name in LOOPING_STATES and not st.loop:
            errors.append(f'state {name!r} is expected to loop')
        if name in ONE_SHOT_STATES and st.loop:
            errors.append(f'state {name!r} is a one-shot reaction and must not loop')
        if name in ONE_SHOT_STATES and not st.still_frame_after:
            errors.append(
                f'one-shot state {name!r} must define still_frame_after so it does not '
                f'replay from the top while the affect holds'
            )
        if st.fallback and st.fallback not in m.states and st.fallback != 'idle':
            errors.append(f'state {name!r} fallback {st.fallback!r} does not resolve to a known state')
    return errors


def resolve_candidates_for_frontend(state: MotionState) -> list:
    """The only sanctioned way to hand a state's URLs to the frontend.
    Always returns a flat list[str] -- even a malformed nested-list upstream
    value flattens cleanly instead of leaking a sub-array into the result.
    """
    out = []
    for c in state.candidates:
        if isinstance(c, (list, tuple)):
            out.extend(str(x) for x in c)
        else:
            out.append(str(c))
    return out


def select_state_for_capability(requested: str, level: CapabilityLevel, manifest: MotionManifest) -> str:
    """Graceful fallback ladder: if the requested state doesn't exist at this
    agent's capability level, degrade to the closest available state rather
    than showing a broken frame.
    """
    if requested in manifest.states:
        return requested
    if level == CapabilityLevel.STATIC_PORTRAIT:
        return '__portrait__'
    if requested in ONE_SHOT_STATES and 'talking' in manifest.states:
        return 'talking'
    if 'idle' in manifest.states:
        return 'idle'
    return '__portrait__'
