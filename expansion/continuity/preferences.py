# -*- coding: utf-8 -*-
"""Persistent user + agent preferences (owner-local, starts empty).

Learns across conversations without shipping any private Keep history.
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any, Optional

from expansion.state_layout import StateLayout, resolve_layout

_lock = threading.Lock()


def _path(layout: StateLayout, kind: str, entity_id: str) -> Path:
    root = Path(layout.user_data_root) / 'preferences' / kind
    root.mkdir(parents=True, exist_ok=True)
    safe = (entity_id or 'unknown').replace('/', '_')[:80]
    return root / f'{safe}.json'


def _load(path: Path) -> dict:
    if not path.is_file():
        return {'schema': 'expansion.preferences.v1', 'updated_at': 0, 'prefs': {}}
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        return data if isinstance(data, dict) else {'prefs': {}}
    except Exception:
        return {'prefs': {}}


def _save(path: Path, data: dict) -> None:
    data = dict(data)
    data['updated_at'] = time.time()
    data['privacy'] = {'no_private_keep_data': True}
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    tmp.replace(path)


class PreferenceStore:
    def __init__(self, layout: Optional[StateLayout] = None):
        self.layout = layout or resolve_layout()

    def get_user_prefs(self, user_id: str = 'user_primary') -> dict:
        return _load(_path(self.layout, 'user', user_id)).get('prefs') or {}

    def get_agent_prefs(self, agent_id: str) -> dict:
        return _load(_path(self.layout, 'agent', agent_id)).get('prefs') or {}

    def set_user_pref(self, key: str, value: Any, user_id: str = 'user_primary') -> None:
        with _lock:
            path = _path(self.layout, 'user', user_id)
            data = _load(path)
            prefs = dict(data.get('prefs') or {})
            prefs[key] = value
            data['prefs'] = prefs
            _save(path, data)

    def set_agent_pref(self, agent_id: str, key: str, value: Any) -> None:
        with _lock:
            path = _path(self.layout, 'agent', agent_id)
            data = _load(path)
            prefs = dict(data.get('prefs') or {})
            prefs[key] = value
            data['prefs'] = prefs
            _save(path, data)

    def learn_from_message(self, agent_id: str, user_message: str) -> list[str]:
        """Extract simple preference cues. Synthetic-safe; no private Keep import."""
        msg = (user_message or '').strip()
        low = msg.lower()
        learned = []
        # "I prefer X" / "please always Y"
        import re
        m = re.search(r'\bi prefer ([^.!?\n]{3,80})', low)
        if m:
            val = m.group(1).strip()
            self.set_user_pref('prefer_statement', val)
            self.set_agent_pref(agent_id, 'last_user_prefer', val)
            learned.append(f'prefer:{val}')
        m = re.search(r'\balways ([^.!?\n]{3,60})', low)
        if m and 'always at your' not in low:
            val = m.group(1).strip()
            self.set_user_pref('always_request', val)
            learned.append(f'always:{val}')
        m = re.search(r'\bnever ([^.!?\n]{3,60})', low)
        if m:
            val = m.group(1).strip()
            self.set_user_pref('never_request', val)
            learned.append(f'never:{val}')
        if 'be brief' in low or 'keep it short' in low:
            self.set_user_pref('verbosity', 'short')
            self.set_agent_pref(agent_id, 'preferred_verbosity', 'short')
            learned.append('verbosity:short')
        if 'be detailed' in low or 'more detail' in low:
            self.set_user_pref('verbosity', 'detailed')
            self.set_agent_pref(agent_id, 'preferred_verbosity', 'detailed')
            learned.append('verbosity:detailed')
        return learned

    def prompt_block(self, agent_id: str, user_id: str = 'user_primary') -> str:
        up = self.get_user_prefs(user_id)
        ap = self.get_agent_prefs(agent_id)
        if not up and not ap:
            return ''
        lines = ['[Learned preferences — owner-local; may be incomplete]']
        for k, v in list(up.items())[:8]:
            lines.append(f'- user.{k}: {v}')
        for k, v in list(ap.items())[:6]:
            lines.append(f'- agent.{k}: {v}')
        return '\n'.join(lines) + '\n'
