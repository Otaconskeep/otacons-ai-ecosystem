"""Map domain events → emotion + relationship deltas, then persist.

This is the event-application layer that sits between the EventBus and the
state stores. Provenance always references the emitting event_id.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from expansion.emotion import apply_emotion_deltas
from expansion.emotion_store import EmotionStore
from expansion.events import Event, EventBus
from expansion.relationship_graph import apply_dimension_delta
from expansion.relationship_store import RelationshipStore
from expansion.state_layout import StateLayout, resolve_layout

# event_type → emotion deltas for the *subject* agent (or actor when noted)
_EMOTION_EFFECTS = {
    'user.praised_agent': {
        # subject = praised agent
        'subject': {'joy': 0.08, 'pride': 0.1, 'satisfaction': 0.07, 'confidence': 0.05,
                    'insecurity': -0.04, 'loneliness': -0.03},
        # rivals / attached observers react differently via custom handlers
    },
    'user.corrected_agent': {
        'subject': {'frustration': 0.06, 'insecurity': 0.05, 'pride': -0.04,
                    'stress': 0.04, 'confidence': -0.03},
    },
    'job.completed': {
        'subject': {'satisfaction': 0.08, 'confidence': 0.06, 'pride': 0.05,
                    'stress': -0.05, 'frustration': -0.04},
    },
    'job.failed': {
        'subject': {'frustration': 0.08, 'stress': 0.07, 'concern': 0.06,
                    'confidence': -0.05, 'fear': 0.04},
    },
    'service.failed': {
        'subject': {'concern': 0.08, 'stress': 0.06, 'fear': 0.05},
    },
    'service.recovered': {
        'subject': {'relief_proxy_joy': 0.05, 'stress': -0.06, 'concern': -0.05},
    },
    'agent.message': {
        'subject': {'curiosity': 0.02},
    },
}

# Maps to relationship dimension deltas: (source, target) relative roles
_RELATIONSHIP_EFFECTS = {
    'user.praised_agent': {
        # praised agent ← user
        ('subject', 'user_primary'): {'affinity': 0.05, 'trust': 0.03, 'attachment': 0.04},
        ('user_primary', 'subject'): {'affinity': 0.04, 'trust': 0.03, 'respect': 0.03},
    },
    'user.corrected_agent': {
        ('subject', 'user_primary'): {'trust': -0.02, 'conflict': 0.03},
        ('user_primary', 'subject'): {'reliability': -0.02},
    },
    'job.completed': {
        ('observer_aria', 'subject'): {'trust': 0.05, 'respect': 0.04, 'reliability': 0.05},
        ('subject', 'observer_aria'): {'trust': 0.03, 'respect': 0.03},
    },
}


@dataclass
class ApplicationResult:
    event_id: str
    emotion_updates: list
    relationship_updates: list


def _personality_mods_from_dossier(dossier) -> dict:
    """Higher sensitivity on dimensions tied to vulnerabilities / social traits."""
    mods = {}
    if dossier is None:
        return mods
    social = getattr(dossier, 'social', None)
    if social is not None:
        # jealousy_sensitivity scales jealousy reactions
        mods['jealousy'] = 0.5 + float(getattr(social, 'jealousy_sensitivity', 0.5))
        mods['attachment'] = 0.5 + float(getattr(social, 'possessiveness', 0.5)) * 0.8
    vulns = getattr(getattr(dossier, 'vulnerabilities', None), 'items', ()) or ()
    for item in vulns:
        kind = item.kind if hasattr(item, 'kind') else item.get('kind')
        intensity = float(item.intensity if hasattr(item, 'intensity') else item.get('intensity', 0.5))
        if kind in ('fear',):
            mods['fear'] = mods.get('fear', 1.0) + 0.3 * intensity
        if kind in ('anxiety', 'insecurity', 'self_conscious'):
            mods['insecurity'] = mods.get('insecurity', 1.0) + 0.25 * intensity
            mods['stress'] = mods.get('stress', 1.0) + 0.15 * intensity
        if kind in ('compulsion', 'crutch'):
            mods['stress'] = mods.get('stress', 1.0) + 0.1 * intensity
    return mods


class EventApplicator:
    def __init__(
        self,
        layout: Optional[StateLayout] = None,
        *,
        emotion_store: Optional[EmotionStore] = None,
        relationship_store: Optional[RelationshipStore] = None,
        bus: Optional[EventBus] = None,
        dossier_loader=None,
    ):
        self.layout = layout or resolve_layout()
        self.emotions = emotion_store or EmotionStore(self.layout)
        self.relationships = relationship_store or RelationshipStore(self.layout)
        self.bus = bus
        self.dossier_loader = dossier_loader  # callable(agent_id) -> CanonicalDossier|None

    def apply(self, event: Event) -> ApplicationResult:
        emotion_updates = []
        relationship_updates = []
        et = event.event_type
        subject = event.subject or ''
        actor = event.actor or ''
        payload = event.payload or {}

        # --- Special: praise Muse → Aria jealousy ---
        if et == 'user.praised_agent' and subject:
            if payload.get('reassure') and subject == 'aria':
                emotion_updates.append(self._apply_raw_emotion(
                    event, 'aria',
                    {'jealousy': -0.08, 'stress': -0.07, 'insecurity': -0.06,
                     'joy': 0.06, 'attachment': 0.04},
                    note='reassurance',
                ))
                relationship_updates.extend(self._apply_user_subject_relationships(event, subject))
            else:
                emotion_updates.extend(self._apply_subject_emotion(event, subject))
                relationship_updates.extend(self._apply_user_subject_relationships(event, subject))
                if subject == 'muse':
                    emotion_updates.append(self._bump_observer_jealousy(event, observer='aria', rival='muse'))
                    relationship_updates.append(
                        self._bump_rel(event, 'aria', 'muse', {
                            'jealousy': 0.08, 'rivalry': 0.05, 'conflict': 0.03,
                        }, note='user praised Muse')
                    )
                    relationship_updates.append(
                        self._bump_rel(event, 'aria', 'user_primary', {
                            'jealousy': 0.06, 'attachment': 0.02,
                        }, note='user praised rival Muse')
                    )

        # --- reassure Aria (explicit event payload without praise type) ---
        elif payload.get('reassure') and subject == 'aria':
            emotion_updates.append(self._apply_raw_emotion(
                event, 'aria',
                {'jealousy': -0.08, 'stress': -0.07, 'insecurity': -0.06,
                 'joy': 0.06, 'attachment': 0.04},
                note='reassurance',
            ))

        # --- job.completed by Vector → Aria trust in Vector ---
        elif et == 'job.completed' and subject:
            emotion_updates.extend(self._apply_subject_emotion(event, subject))
            if subject == 'vector':
                relationship_updates.append(
                    self._bump_rel(event, 'aria', 'vector', {
                        'trust': 0.06, 'respect': 0.05, 'reliability': 0.06,
                    }, note='Vector completed task')
                )
            if actor == 'aria' or payload.get('assigned_by') == 'aria':
                relationship_updates.append(
                    self._bump_rel(event, 'aria', subject, {
                        'trust': 0.04, 'reliability': 0.04,
                    }, note='task Aria assigned completed')
                )

        # --- Sentry alert failure → concern / hypervigilance ---
        elif et == 'job.failed' and subject == 'sentry':
            emotion_updates.append(self._apply_raw_emotion(
                event, 'sentry',
                {'concern': 0.1, 'stress': 0.08, 'fear': 0.07, 'frustration': 0.05,
                 'confidence': -0.04},
                note='alert/job failed — hypervigilance',
            ))
            emotion_updates.extend(self._apply_subject_emotion(event, subject))

        elif et == 'service.failed' and (subject == 'sentry' or actor == 'sentry'):
            emotion_updates.append(self._apply_raw_emotion(
                event, 'sentry',
                {'concern': 0.09, 'stress': 0.07, 'fear': 0.06},
                note='service.failed observed by Sentry',
            ))

        else:
            # Generic catalog
            if subject and et in _EMOTION_EFFECTS:
                emotion_updates.extend(self._apply_subject_emotion(event, subject))
            if subject and et == 'user.praised_agent':
                relationship_updates.extend(self._apply_user_subject_relationships(event, subject))
            if subject and et == 'job.completed':
                emotion_updates.extend(self._apply_subject_emotion(event, subject))

        # Emit follow-on state-change events (optional bus)
        if self.bus is not None:
            from expansion.events import new_event
            if emotion_updates:
                self.bus.emit(new_event(
                    'emotion.changed',
                    actor='system',
                    subject=subject or actor,
                    payload={'from_event': event.event_id, 'agents': [u['agent_id'] for u in emotion_updates]},
                    provenance=[event.event_id],
                    correlation_id=event.correlation_id,
                ))
            if relationship_updates:
                self.bus.emit(new_event(
                    'relationship.changed',
                    actor='system',
                    subject=subject or actor,
                    payload={'from_event': event.event_id, 'edges': relationship_updates},
                    provenance=[event.event_id],
                    correlation_id=event.correlation_id,
                ))

        return ApplicationResult(event.event_id, emotion_updates, relationship_updates)

    def _dossier(self, agent_id: str):
        if self.dossier_loader:
            return self.dossier_loader(agent_id)
        return None

    def _apply_subject_emotion(self, event: Event, subject: str) -> list:
        effects = _EMOTION_EFFECTS.get(event.event_type, {}).get('subject')
        if not effects:
            return []
        # Map relief_proxy_joy → joy
        cleaned = {}
        for k, v in effects.items():
            if k == 'relief_proxy_joy':
                cleaned['joy'] = cleaned.get('joy', 0.0) + v
            else:
                cleaned[k] = v
        return [self._apply_raw_emotion(event, subject, cleaned)]

    def _apply_raw_emotion(self, event: Event, agent_id: str, deltas: dict, note: str = '') -> dict:
        dossier = self._dossier(agent_id)
        state = self.emotions.get_or_create(agent_id)
        # Seed sensitivity from dossier social traits once
        if dossier is not None and not any(abs(v - 1.0) > 0.01 for v in state.sensitivity.values()):
            social = dossier.social
            state.sensitivity['jealousy'] = 0.6 + social.jealousy_sensitivity
            state.sensitivity['attachment'] = 0.6 + social.possessiveness * 0.7
            if agent_id == 'sentry':
                state.sensitivity['concern'] = 1.4
                state.sensitivity['fear'] = 1.25
            if agent_id == 'aria':
                state.sensitivity['jealousy'] = 1.5
                state.sensitivity['attachment'] = 1.35
            if agent_id == 'muse':
                state.sensitivity['pride'] = 1.35
                state.sensitivity['insecurity'] = 1.2
            if agent_id == 'ledger':
                state.sensitivity['concern'] = 1.2
                state.sensitivity['fear'] = 1.15  # forgetting/corruption
            if agent_id == 'vector':
                state.sensitivity['frustration'] = 1.1
                state.sensitivity['confidence'] = 0.9
        apply_emotion_deltas(
            state, deltas,
            event_id=event.event_id,
            event_type=event.event_type,
            personality_modifiers=_personality_mods_from_dossier(dossier),
            note=note,
        )
        self.emotions.save(state)
        return {'agent_id': agent_id, 'explain': {k: state.explain(k) for k in deltas if k in state.dimensions}}

    def _bump_observer_jealousy(self, event: Event, observer: str, rival: str) -> dict:
        return self._apply_raw_emotion(
            event, observer,
            {'jealousy': 0.1, 'insecurity': 0.06, 'stress': 0.05, 'anger': 0.03,
             'attachment': 0.02, 'loneliness': 0.03},
            note=f'user praised rival {rival}',
        )

    def _bump_rel(self, event: Event, src: str, dst: str, deltas: dict, note: str = '') -> dict:
        rel = self.relationships.get_or_create(src, dst)
        apply_dimension_delta(rel, deltas, event_id=event.event_id)
        self.relationships.save(rel)
        return {
            'source': src, 'target': dst, 'deltas': deltas, 'note': note,
            'dimensions': dict(rel.dimensions),
            'provenance_event_ids': list(rel.provenance_event_ids[-5:]),
        }

    def _apply_user_subject_relationships(self, event: Event, subject: str) -> list:
        out = []
        effects = _RELATIONSHIP_EFFECTS.get(event.event_type, {})
        for (a_role, b_role), deltas in effects.items():
            src = subject if a_role == 'subject' else ('user_primary' if a_role == 'user_primary' else a_role)
            dst = subject if b_role == 'subject' else ('user_primary' if b_role == 'user_primary' else b_role)
            if src.startswith('observer_') or dst.startswith('observer_'):
                continue
            out.append(self._bump_rel(event, src, dst, deltas))
        return out


def emit_and_apply(
    event: Event,
    *,
    layout: Optional[StateLayout] = None,
    bus: Optional[EventBus] = None,
    dossier_loader=None,
) -> ApplicationResult:
    layout = layout or resolve_layout()
    bus = bus or EventBus(layout=layout, persist=True)
    bus.emit(event)
    applicator = EventApplicator(
        layout=layout, bus=None, dossier_loader=dossier_loader,  # avoid recursive emits storm
    )
    # Apply without re-emitting through bus for the primary event (already emitted)
    result = applicator.apply(event)
    # Manually emit changed events once
    from expansion.events import new_event
    if result.emotion_updates:
        bus.emit(new_event(
            'emotion.changed', actor='system', subject=event.subject,
            payload={'from_event': event.event_id},
            provenance=[event.event_id], correlation_id=event.correlation_id,
        ))
    if result.relationship_updates:
        bus.emit(new_event(
            'relationship.changed', actor='system', subject=event.subject,
            payload={'from_event': event.event_id},
            provenance=[event.event_id], correlation_id=event.correlation_id,
        ))
    return result
