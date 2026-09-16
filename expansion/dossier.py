"""Structured dossier schemas for Keep Expansion agents.

Canonical dossier = vendor-defined product data (pre-install background).
Living dossier = observed tendencies from real post-install history (user data)
with evidence/provenance — never fabricated owner memories.

These are structured fields, not one giant prompt.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Optional

from expansion.versions import DOSSIER_SCHEMA_VERSION
from expansion.vulnerabilities import VulnerabilityProfile, validate_vulnerability_profile


@dataclass
class IdentityBlock:
    display_name: str = ''
    short_bio: str = ''
    pronouns: str = ''
    presentation: str = ''


@dataclass
class BackgroundBlock:
    origin_summary: str = ''          # original Keep-universe lore only
    history: str = ''
    education_training: str = ''
    career: str = ''


@dataclass
class CharacterBlock:
    role: str = ''
    archetype: str = ''
    values: tuple = ()
    morals: tuple = ()
    communication_style: str = ''
    humor_style: str = ''


@dataclass
class CapabilityTraits:
    strengths: tuple = ()
    weaknesses: tuple = ()
    blind_spots: tuple = ()
    failure_modes: tuple = ()


@dataclass
class SocialTraits:
    attachment_style: str = ''
    jealousy_sensitivity: float = 0.5   # 0..1
    possessiveness: float = 0.5
    trust_behavior: str = ''
    conflict_behavior: str = ''
    rivalry_behavior: str = ''


@dataclass
class PreferenceBlock:
    likes: tuple = ()
    dislikes: tuple = ()
    interests: tuple = ()
    preferences: dict = field(default_factory=dict)


@dataclass
class StressProfile:
    stress_behavior: str = ''
    recovery_behavior: str = ''
    emotional_baseline: dict = field(default_factory=dict)
    relationship_tendencies: dict = field(default_factory=dict)


@dataclass
class PermissionBlock:
    tool_permissions: tuple = ()
    room_permissions: tuple = ()
    role_permissions: tuple = ()


@dataclass
class CanonicalDossier:
    """Product-data dossier. Immutable in production releases."""
    schema_version: int
    agent_id: str
    identity: IdentityBlock = field(default_factory=IdentityBlock)
    background: BackgroundBlock = field(default_factory=BackgroundBlock)
    character: CharacterBlock = field(default_factory=CharacterBlock)
    capabilities: CapabilityTraits = field(default_factory=CapabilityTraits)
    vulnerabilities: VulnerabilityProfile = field(default_factory=VulnerabilityProfile)
    social: SocialTraits = field(default_factory=SocialTraits)
    preferences: PreferenceBlock = field(default_factory=PreferenceBlock)
    stress: StressProfile = field(default_factory=StressProfile)
    permissions: PermissionBlock = field(default_factory=PermissionBlock)
    # Explicit: canonical history must not invent post-install owner memories
    canonical_history_notes: str = (
        'Pre-install Keep-universe background only. No fabricated owner memories.'
    )


@dataclass
class ObservedTrait:
    trait: str
    value: str
    confidence: float
    evidence_event_ids: tuple = ()
    updated_at: float = 0.0


@dataclass
class LivingDossier:
    """User-data dossier of observed tendencies. Requires provenance."""
    schema_version: int
    agent_id: str
    observed_traits: tuple = ()  # ObservedTrait
    notes: str = ''
    updated_at: float = 0.0


def _tupleize(value) -> tuple:
    if value is None:
        return ()
    if isinstance(value, tuple):
        return value
    if isinstance(value, list):
        return tuple(value)
    return (value,)


def validate_canonical_dossier(d: CanonicalDossier) -> list:
    errors = []
    if d.schema_version != DOSSIER_SCHEMA_VERSION:
        errors.append(f'unsupported dossier schema_version {d.schema_version}')
    if not d.agent_id:
        errors.append('agent_id required')
    if not (0.0 <= d.social.jealousy_sensitivity <= 1.0):
        errors.append('jealousy_sensitivity must be in [0,1]')
    if not (0.0 <= d.social.possessiveness <= 1.0):
        errors.append('possessiveness must be in [0,1]')
    errors.extend(validate_vulnerability_profile(d.vulnerabilities))
    return errors


def validate_living_dossier(d: LivingDossier) -> list:
    errors = []
    if d.schema_version != DOSSIER_SCHEMA_VERSION:
        errors.append(f'unsupported dossier schema_version {d.schema_version}')
    if not d.agent_id:
        errors.append('agent_id required')
    for i, t in enumerate(d.observed_traits):
        trait = t if isinstance(t, ObservedTrait) else ObservedTrait(**t)
        if not trait.evidence_event_ids:
            errors.append(f'observed_traits[{i}] requires evidence_event_ids provenance')
        if not (0.0 <= trait.confidence <= 1.0):
            errors.append(f'observed_traits[{i}] confidence must be in [0,1]')
    return errors


def empty_canonical_dossier(agent_id: str, display_name: str = '', **kwargs) -> CanonicalDossier:
    identity = kwargs.pop('identity', None) or IdentityBlock(display_name=display_name)
    return CanonicalDossier(
        schema_version=DOSSIER_SCHEMA_VERSION,
        agent_id=agent_id,
        identity=identity,
        **kwargs,
    )


def to_dict(obj) -> dict:
    return asdict(obj)


def canonical_from_dict(d: dict) -> CanonicalDossier:
    from expansion.vulnerabilities import vulnerability_from_dict
    d = dict(d)
    if isinstance(d.get('identity'), dict):
        d['identity'] = IdentityBlock(**d['identity'])
    if isinstance(d.get('background'), dict):
        d['background'] = BackgroundBlock(**d['background'])
    if isinstance(d.get('character'), dict):
        ch = dict(d['character'])
        ch['values'] = _tupleize(ch.get('values'))
        ch['morals'] = _tupleize(ch.get('morals'))
        d['character'] = CharacterBlock(**ch)
    if isinstance(d.get('capabilities'), dict):
        cap = dict(d['capabilities'])
        for k in ('strengths', 'weaknesses', 'blind_spots', 'failure_modes'):
            cap[k] = _tupleize(cap.get(k))
        d['capabilities'] = CapabilityTraits(**cap)
    if isinstance(d.get('vulnerabilities'), dict):
        d['vulnerabilities'] = vulnerability_from_dict(d['vulnerabilities'])
    if isinstance(d.get('social'), dict):
        d['social'] = SocialTraits(**d['social'])
    if isinstance(d.get('preferences'), dict):
        pref = dict(d['preferences'])
        for k in ('likes', 'dislikes', 'interests'):
            pref[k] = _tupleize(pref.get(k))
        d['preferences'] = PreferenceBlock(**pref)
    if isinstance(d.get('stress'), dict):
        d['stress'] = StressProfile(**d['stress'])
    if isinstance(d.get('permissions'), dict):
        perm = dict(d['permissions'])
        for k in ('tool_permissions', 'room_permissions', 'role_permissions'):
            perm[k] = _tupleize(perm.get(k))
        d['permissions'] = PermissionBlock(**perm)
    fields = CanonicalDossier.__dataclass_fields__
    return CanonicalDossier(**{k: v for k, v in d.items() if k in fields})
