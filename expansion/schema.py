"""Canonical Agent schema for Otacon Expansion.

Single source of truth for what an agent *is*. Every provisioning step
reads/writes this shape; nothing else invents its own agent record layout.
schema_version bumps whenever a field is added, removed, or changes
meaning -- migrations key off this number.

Identity and role are deliberately separate fields: agent_id is the stable,
immutable key; display_name can be renamed by the user at any time without
touching reporting_to, authority_rank, or anything else that depends on who
the agent structurally is.
"""
from __future__ import annotations

import re
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Optional

AGENT_SCHEMA_VERSION = 1

_ID_RE = re.compile(r'^[a-z][a-z0-9_]{1,63}$')

VALID_ARCHETYPES = (
    'coordinator', 'engineer', 'archivist', 'curator', 'sentinel', 'custom',
)

VALID_PRESENTATIONS = ('male', 'female', 'unspecified')


class SchemaError(ValueError):
    """Raised when an agent record fails validation against the canonical schema."""


@dataclass
class Voice:
    piper_voice: str
    gender: str  # 'male' | 'female' -- must match Agent.presentation when set
    onnx_verified: bool = False
    trained_override: Optional[str] = None  # path to a custom-trained voice, if any


@dataclass
class Room:
    route: str  # e.g. '/war-room'
    title: str
    shared: bool = False  # True for Keep-wide rooms like REX/Dossier


@dataclass
class MotionManifestRef:
    manifest_id: str
    capability_level: int = 0  # 0-3, see expansion.motion_manifest.CapabilityLevel


@dataclass
class Agent:
    schema_version: int
    agent_id: str
    display_name: str
    persona: str
    role: str
    domain: str
    archetype: str
    reporting_to: Optional[str]
    authority_rank: int
    presentation: str
    voice: Voice
    room: Room
    capabilities: tuple = ()
    integrations: tuple = ()
    emotional_defaults: dict = field(default_factory=dict)
    relationship_defaults: dict = field(default_factory=dict)
    motion_manifest: Optional[MotionManifestRef] = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def validate(self) -> None:
        errors = validate_agent(self)
        if errors:
            raise SchemaError('; '.join(errors))


def new_agent_id() -> str:
    return f'agent_{uuid.uuid4().hex[:12]}'


def validate_agent(a: Agent) -> list:
    """Pure validation. Returns a list of human-readable errors, empty if
    valid. Never raises -- callers decide whether errors are fatal (e.g. the
    LLM-assisted builder for agent #6+ treats any error as 'reject the
    proposal', while an interactive edit form can surface errors inline).
    """
    errors = []
    if a.schema_version != AGENT_SCHEMA_VERSION:
        errors.append(f'unsupported schema_version {a.schema_version}, expected {AGENT_SCHEMA_VERSION}')
    if not _ID_RE.match(a.agent_id or ''):
        errors.append(f'agent_id {a.agent_id!r} must match {_ID_RE.pattern} -- a display name is not a valid id')
    if not a.display_name or not a.display_name.strip():
        errors.append('display_name must not be empty')
    if not a.persona or len(a.persona.strip()) < 20:
        errors.append('persona must be a real system prompt, not empty/placeholder')
    if len(a.persona) > 8000:
        errors.append('persona exceeds 8000 chars -- reject pathologically long LLM-drafted prompts')
    if a.archetype not in VALID_ARCHETYPES:
        errors.append(f'archetype {a.archetype!r} not in {VALID_ARCHETYPES}')
    if a.authority_rank < 1:
        errors.append('authority_rank must be >= 1')
    if a.presentation not in VALID_PRESENTATIONS:
        errors.append(f'presentation {a.presentation!r} must be one of {VALID_PRESENTATIONS}')
    if a.presentation != 'unspecified' and a.voice and a.voice.gender != a.presentation:
        errors.append(f'voice.gender {a.voice.gender!r} does not match presentation {a.presentation!r}')
    if a.reporting_to == a.agent_id:
        errors.append('agent cannot report to itself')
    return errors


def to_dict(a: Agent) -> dict:
    return asdict(a)


def from_dict(d: dict) -> Agent:
    d = dict(d)
    if isinstance(d.get('voice'), dict):
        d['voice'] = Voice(**d['voice'])
    if isinstance(d.get('room'), dict):
        d['room'] = Room(**d['room'])
    if isinstance(d.get('motion_manifest'), dict):
        d['motion_manifest'] = MotionManifestRef(**d['motion_manifest'])
    if isinstance(d.get('capabilities'), list):
        d['capabilities'] = tuple(d['capabilities'])
    if isinstance(d.get('integrations'), list):
        d['integrations'] = tuple(d['integrations'])
    return Agent(**d)
