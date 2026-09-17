"""Topology and service-endpoint configuration for Keep Expansion.

All service URLs are user-supplied or localhost defaults. Private Keep LAN
addresses (192.168.50.x, /opt/otacon, household hostnames) must never appear
as defaults in the public product.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

from expansion.state_layout import resolve_layout

TOPOLOGY_SCHEMA_VERSION = 1

# Public product install markers — NEVER treat /opt/otacon as proof of install.
PUBLIC_INSTALL_MARKERS = (
    'cli_shim',          # ~/.local/bin/otacon
    'core_tree',         # $OTACON_INSTALL_DIR/core
    'config_json',       # ~/.config/otacon/config.json
    'branding_endpoint', # GET /api/branding on CHAT_PORT
)


@dataclass
class ServiceEndpoint:
    name: str
    base_url: str
    enabled: bool = True
    notes: str = ''


@dataclass
class TopologyConfig:
    schema_version: int = TOPOLOGY_SCHEMA_VERSION
    chat_bind: str = '127.0.0.1'
    chat_port: int = 5757
    ollama_url: str = 'http://127.0.0.1:11434'
    tts_url: str = ''
    comfyui_url: str = ''
    home_assistant_url: str = ''
    discord_webhook_configured: bool = False
    lan_mode: bool = False
    services: dict = field(default_factory=dict)  # name -> ServiceEndpoint as dict

    def chat_base_url(self) -> str:
        return f'http://{self.chat_bind}:{self.chat_port}'

    def validate(self) -> list:
        errors = []
        if self.schema_version != TOPOLOGY_SCHEMA_VERSION:
            errors.append(
                f'unsupported topology schema_version {self.schema_version}'
            )
        if self.chat_port < 1 or self.chat_port > 65535:
            errors.append('chat_port out of range')
        # Reject known private Keep defaults if somehow injected
        forbidden_substrings = (
            '192.168.50.219',
            '192.168.50.221',
            '192.168.50.192',
            '192.168.50.69',
            '/opt/otacon',
        )
        blob = json.dumps(asdict(self), default=str)
        for s in forbidden_substrings:
            if s in blob:
                errors.append(f'forbidden private-Keep topology fragment: {s}')
        return errors


def default_topology() -> TopologyConfig:
    raw_port = (os.environ.get('OTACON_CHAT_PORT') or '').strip() or '5757'
    return TopologyConfig(
        ollama_url=os.environ.get('OLLAMA_URL', 'http://127.0.0.1:11434'),
        chat_port=int(raw_port),
        chat_bind=os.environ.get('OTACON_CHAT_BIND', '127.0.0.1'),
    )


def topology_path(layout=None) -> Path:
    layout = layout or resolve_layout()
    return layout.user_preferences / 'topology.json'


def save_topology(cfg: TopologyConfig, path: Optional[Path] = None) -> Path:
    errors = cfg.validate()
    if errors:
        raise ValueError('; '.join(errors))
    path = path or topology_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(cfg), indent=2) + '\n', encoding='utf-8')
    return path


def load_topology(path: Optional[Path] = None) -> TopologyConfig:
    path = path or topology_path()
    if not path.exists():
        return default_topology()
    data = json.loads(path.read_text(encoding='utf-8'))
    return TopologyConfig(**{k: v for k, v in data.items() if k in TopologyConfig.__dataclass_fields__})


def public_core_install_present(
    home: Optional[Path] = None,
    install_dir: Optional[Path] = None,
) -> dict:
    """Semantic presence check for *public* Otacon Core.

    Returns a dict of marker -> bool. Presence of /opt/otacon is intentionally
    ignored — that path is the private Keep reference layout, not the product.
    """
    home = home or Path.home()
    install_dir = Path(
        install_dir
        or os.environ.get('OTACON_INSTALL_DIR', str(home / 'otacon-ai-ecosystem'))
    ).expanduser()
    markers = {
        'cli_shim': (home / '.local' / 'bin' / 'otacon').exists(),
        'core_tree': (install_dir / 'core').is_dir(),
        'config_json': (home / '.config' / 'otacon' / 'config.json').is_file(),
        'install_git': (install_dir / '.git').is_dir(),
    }
    markers['any_public_marker'] = any(
        markers[k] for k in ('cli_shim', 'core_tree', 'config_json')
    )
    markers['private_keep_path_ignored'] = True  # documentation flag for tests
    return markers


def shell_public_install_probe() -> str:
    """Bash snippet for Windows/Linux installers.

    Replaces legacy probes that treated /opt/otacon or ~/otacon as success.
    """
    return (
        'test -x "$HOME/.local/bin/otacon" '
        '|| test -d "${OTACON_INSTALL_DIR:-$HOME/otacon-ai-ecosystem}/core" '
        '|| test -f "$HOME/.config/otacon/config.json"'
    )
