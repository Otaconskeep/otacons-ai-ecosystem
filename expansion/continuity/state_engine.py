# -*- coding: utf-8 -*-
"""State Engine — Formula 4 / 7 / 8 for public Expansion Premium.

Clean-room Keep-parity. Persists happiness/confidence/energy/_residue/mood
in owner-local agent_states (never private Keep data).
Public agents: aria, vector, ledger, muse, sentry.
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any, Optional

from expansion.state_layout import StateLayout, resolve_layout

_BASELINE = {'confidence': 0.55, 'happiness': 0.55, 'energy': 0.60}
_DECAY = 0.015
_RESIDUE_DECAY = 0.88
_EMO_W = {'happiness': 0.40, 'confidence': 0.35, 'energy': 0.15, 'residue': 0.10}

PUBLIC_AGENTS = frozenset({'aria', 'vector', 'ledger', 'muse', 'sentry'})

_RESIDUE_IMPACT: dict[str, float] = {
    'agent_ask': 0.0,
    'operator_ask': 0.0,
    'operator_ask_subjective': +0.04,
    'user_mild_criticism': -0.03,
    'user_dismissal': -0.08,
    'user_insult': -0.20,
    'user_hostility': -0.28,
    'user_hostile': -0.28,
    'user_critique': -0.05,
    'user_apology': +0.10,
    'user_repair': +0.08,
    'user_praise': +0.16,
    'user_gratitude': +0.10,
    'user_acknowledged_agent': +0.12,
    'memory_reflection': 0.0,
    'collaboration_success': +0.06,
    'collaboration_failure': -0.08,
}

_DELTAS: dict[str, dict[str, float]] = {
    'agent_ask': {'energy': +0.01},
    'operator_ask': {'energy': +0.01},
    'operator_ask_subjective': {'happiness': +0.012, 'energy': +0.008},
    'user_mild_criticism': {'happiness': -0.008},
    'user_dismissal': {'happiness': -0.022, 'confidence': -0.010},
    'user_insult': {'happiness': -0.065, 'confidence': -0.035, 'energy': +0.020},
    'user_hostility': {'happiness': -0.090, 'confidence': -0.050, 'energy': +0.030},
    'user_hostile': {'happiness': -0.090, 'confidence': -0.050, 'energy': +0.030},
    'user_critique': {'happiness': -0.040, 'confidence': -0.020},
    'user_apology': {'happiness': +0.020, 'confidence': +0.010},
    'user_repair': {'happiness': +0.018, 'confidence': +0.012},
    'user_praise': {'happiness': +0.055, 'confidence': +0.025, 'energy': +0.012},
    'user_gratitude': {'happiness': +0.035, 'confidence': +0.015},
    'user_acknowledged_agent': {'happiness': +0.040, 'confidence': +0.018},
    'memory_reflection': {'energy': +0.018},
    'collaboration_success': {'happiness': +0.025, 'confidence': +0.015},
    'collaboration_failure': {'happiness': -0.030, 'confidence': -0.020},
}

_lock = threading.Lock()


def _canon(raw: str | None) -> str:
    s = (raw or '').strip().lower().replace('-', '_').replace(' ', '_')
    if s in ('owner', 'user', 'operator'):
        return 'user_primary'
    return s


def _states_dir(layout: StateLayout) -> Path:
    d = Path(layout.user_data_root) / 'agent_states'
    d.mkdir(parents=True, exist_ok=True)
    return d


def _path(layout: StateLayout, entity_id: str) -> Path:
    return _states_dir(layout) / f'{_canon(entity_id)}.json'


def _safe_load(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _safe_save(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    tmp.replace(path)


def derive_mood_label(
    happiness: float, confidence: float, energy: float, residue: float = 0.0,
) -> str:
    score = (
        happiness * _EMO_W['happiness']
        + confidence * _EMO_W['confidence']
        + energy * _EMO_W['energy']
        + residue * _EMO_W['residue']
    )
    if score >= 0.72:
        return 'cheerful'
    if score >= 0.62:
        return 'pleased'
    if score >= 0.52:
        return 'focused' if energy >= 0.55 else 'neutral'
    if score >= 0.42:
        return 'brooding' if confidence < 0.42 else 'neutral'
    if score >= 0.30:
        return 'anxious' if residue < -0.15 else 'brooding'
    if energy < 0.28:
        return 'detached'
    return 'volatile'


def _apply_formula4(cur: float, delta: float, key: str) -> float:
    baseline = _BASELINE.get(key, 0.5)
    new = cur + delta - _DECAY * (cur - baseline)
    return round(max(0.0, min(1.0, new)), 4)


def _apply_residue_decay(prev: float, impact: float) -> float:
    return round(max(-1.0, min(1.0, prev * _RESIDUE_DECAY + impact)), 4)


class StateEngine:
    """Formula 4 + 7 + 8 state manager for Premium Expansion agents."""

    @staticmethod
    def get(entity_id: str, *, layout: Optional[StateLayout] = None) -> dict:
        layout = layout or resolve_layout()
        eid = _canon(entity_id)
        raw = _safe_load(_path(layout, eid)) if eid else {}
        out = {
            'entity_id': eid,
            'mood': raw.get('mood', 'neutral'),
            'confidence': float(raw.get('confidence', _BASELINE['confidence'])),
            'happiness': float(raw.get('happiness', _BASELINE['happiness'])),
            'energy': float(raw.get('energy', _BASELINE['energy'])),
            '_residue': float(raw.get('_residue', raw.get('residue', 0.0))),
            'updated_at': float(raw.get('updated_at', 0.0)),
            'last_event': str(raw.get('last_event') or ''),
        }
        for k, v in raw.items():
            if k not in out:
                out[k] = v
        if not raw:
            out['last_event'] = 'mock_baseline'
            out['_seeded'] = True
        return out

    @staticmethod
    def update_from_event(
        entity_id: str,
        event_type: str,
        payload: dict | None = None,
        *,
        layout: Optional[StateLayout] = None,
    ) -> dict:
        layout = layout or resolve_layout()
        eid = _canon(entity_id)
        if eid not in PUBLIC_AGENTS:
            return StateEngine.get(eid, layout=layout)
        payload = payload or {}
        state = StateEngine.get(eid, layout=layout)

        event_key = event_type
        deltas = _DELTAS.get(event_key, {})
        updates: dict[str, Any] = {}
        for key in ('confidence', 'happiness', 'energy'):
            cur = float(state.get(key, _BASELINE.get(key, 0.5)))
            updates[key] = _apply_formula4(cur, deltas.get(key, 0.0), key)

        # Soft floors for conversational hits
        if event_key in ('user_hostile', 'user_hostility', 'user_insult', 'user_critique'):
            updates['happiness'] = max(0.12, updates['happiness'])
            updates['confidence'] = max(0.15, updates['confidence'])

        prev_residue = float(state.get('_residue', 0.0))
        impact = float(_RESIDUE_IMPACT.get(event_key, 0.0))
        # Allow intensity scale from payload
        inten = payload.get('intensity')
        if inten is not None:
            try:
                impact = impact * float(inten)
            except (TypeError, ValueError):
                pass
        new_residue = _apply_residue_decay(prev_residue, impact)
        updates['_residue'] = new_residue
        updates['mood'] = derive_mood_label(
            updates['happiness'], updates['confidence'], updates['energy'], new_residue,
        )
        updates['updated_at'] = time.time()
        updates['last_event'] = event_type
        updates['entity_id'] = eid

        merged = dict(state)
        merged.update(updates)
        with _lock:
            _safe_save(_path(layout, eid), {
                k: merged[k] for k in (
                    'entity_id', 'mood', 'confidence', 'happiness', 'energy',
                    '_residue', 'updated_at', 'last_event',
                )
            })
        return StateEngine.get(eid, layout=layout)

    @staticmethod
    def apply_vector_nudge(
        entity_id: str,
        *,
        dh: float = 0.0,
        dc: float = 0.0,
        de: float = 0.0,
        residue_impact: float = 0.0,
        event_type: str = 'vector_nudge',
        layout: Optional[StateLayout] = None,
    ) -> dict:
        """Direct Formula 4/7 nudge when deltas are precomputed (affect bridge)."""
        layout = layout or resolve_layout()
        eid = _canon(entity_id)
        if eid not in PUBLIC_AGENTS:
            return StateEngine.get(eid, layout=layout)
        state = StateEngine.get(eid, layout=layout)
        updates = {
            'happiness': _apply_formula4(float(state['happiness']), dh, 'happiness'),
            'confidence': _apply_formula4(float(state['confidence']), dc, 'confidence'),
            'energy': _apply_formula4(float(state['energy']), de, 'energy'),
        }
        new_residue = _apply_residue_decay(float(state.get('_residue', 0.0)), residue_impact)
        updates['_residue'] = new_residue
        updates['mood'] = derive_mood_label(
            updates['happiness'], updates['confidence'], updates['energy'], new_residue,
        )
        updates['updated_at'] = time.time()
        updates['last_event'] = event_type
        updates['entity_id'] = eid
        with _lock:
            _safe_save(_path(layout, eid), updates)
        return StateEngine.get(eid, layout=layout)

    @staticmethod
    def is_stressed(entity_id: str, *, layout: Optional[StateLayout] = None) -> bool:
        state = StateEngine.get(entity_id, layout=layout)
        return (
            float(state.get('confidence', 0.5)) < 0.35
            or float(state.get('happiness', 0.5)) < 0.30
            or float(state.get('_residue', 0.0)) < -0.35
            or state.get('mood', '') in ('brooding', 'anxious', 'detached', 'volatile')
        )

    @staticmethod
    def summary_for_prompt(entity_id: str, *, layout: Optional[StateLayout] = None) -> str:
        state = StateEngine.get(entity_id, layout=layout)
        mood = state.get('mood', 'neutral')
        confidence = float(state.get('confidence', 0.5))
        happiness = float(state.get('happiness', 0.5))
        energy = float(state.get('energy', 0.6))
        residue = float(state.get('_residue', 0.0))
        conf_w = 'high' if confidence > 0.70 else ('low' if confidence < 0.38 else 'moderate')
        ener_w = 'high' if energy > 0.70 else ('low' if energy < 0.38 else 'moderate')
        line = (
            f'[State] mood={mood}, confidence={conf_w} ({confidence:.2f}), '
            f'energy={ener_w} ({energy:.2f}), happiness={happiness:.2f}'
        )
        if abs(residue) > 0.20:
            valence = 'positive' if residue > 0 else 'negative'
            line += f', emotional-residue={valence} ({residue:+.2f})'
        return line
