"""Persisted application/user preferences (Auto Speak, etc.)."""
from __future__ import annotations

import json
from pathlib import Path


DEFAULTS = {
    'auto_speak': False,
}


class Preferences:
    """Per-user / per-agent preference store (JSON file)."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._data = {'auto_speak': {}}
        self._load()

    def _load(self) -> None:
        if not self.path.is_file():
            return
        try:
            loaded = json.loads(self.path.read_text())
            if isinstance(loaded, dict):
                if isinstance(loaded.get('auto_speak'), dict):
                    self._data['auto_speak'] = loaded['auto_speak']
                elif 'auto_speak' in loaded:
                    # Legacy global bool → map under local_user/default
                    self._data['auto_speak'] = {
                        'local_user': {'default': bool(loaded['auto_speak'])}
                    }
                for k, v in loaded.items():
                    if k != 'auto_speak':
                        self._data[k] = v
        except (OSError, json.JSONDecodeError):
            pass

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._data, indent=2) + '\n')

    def set_auto_speak(self, user_id: str, agent_id: str, enabled: bool) -> None:
        bucket = self._data.setdefault('auto_speak', {})
        user = bucket.setdefault(user_id, {})
        user[agent_id] = bool(enabled)
        self._save()

    def get_auto_speak(self, user_id: str, agent_id: str) -> bool:
        return bool(self._data.get('auto_speak', {}).get(user_id, {}).get(agent_id, False))


def prefs_path(root: Path | None = None) -> Path:
    base = root or (Path.home() / '.config' / 'otacon')
    return Path(base) / 'user_preferences.json'


def load_preferences(root: Path | None = None, user_id: str = 'local_user', agent_id: str = 'agent_001') -> dict:
    path = prefs_path(root)
    prefs = Preferences(path)
    return {
        'auto_speak': prefs.get_auto_speak(user_id, agent_id),
        'user_id': user_id,
        'agent_id': agent_id,
    }


def save_preferences(data: dict, root: Path | None = None) -> Path:
    path = prefs_path(root)
    prefs = Preferences(path)
    user_id = data.get('user_id', 'local_user')
    agent_id = data.get('agent_id', 'agent_001')
    if 'auto_speak' in data:
        prefs.set_auto_speak(user_id, agent_id, bool(data.get('auto_speak')))
    return path
