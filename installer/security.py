"""Installer/server security helpers: bind mode, auth, path confinement."""
from __future__ import annotations

import hmac
import os
import secrets
from pathlib import Path

CONFIG_ROOT = Path.home() / '.config' / 'otacon'
TOKEN_PATH = CONFIG_ROOT / 'lan_token'
SAFE_WRITE_ROOTS = (
    CONFIG_ROOT.resolve(),
    (Path.home() / '.local' / 'share' / 'otacon').resolve(),
)


def is_loopback_host(host: str) -> bool:
    h = (host or '').strip().lower()
    return h in ('127.0.0.1', 'localhost', '::1', '')


def resolve_bind_host() -> tuple[str, str]:
    """Return (host, mode) where mode is 'local' or 'lan'.

    Auth/LAN mode is controlled ONLY by OTACON_LAN_MODE:
      - OTACON_LAN_MODE=1 → lan (bearer auth required on protected APIs)
      - OTACON_LAN_MODE=0 / unset → local (no bearer auth)

    Bind address is independent: WSL may bind 0.0.0.0 while staying in local
    auth mode so Windows can reach the UI without enabling LAN auth.
    """
    lan_mode = os.getenv('OTACON_LAN_MODE', '').strip().lower()
    host = os.getenv('OTACON_HOST', '').strip()

    if lan_mode in ('1', 'true', 'yes', 'lan'):
        return (host or '0.0.0.0'), 'lan'
    # Explicit local, or default: never treat bind-all / non-loopback host alone as LAN.
    return (host or '127.0.0.1'), 'local'


def ensure_lan_token() -> str:
    CONFIG_ROOT.mkdir(parents=True, exist_ok=True)
    if TOKEN_PATH.is_file():
        token = TOKEN_PATH.read_text(encoding='utf-8').strip()
        if token:
            return token
    token = secrets.token_urlsafe(32)
    TOKEN_PATH.write_text(token + '\n', encoding='utf-8')
    try:
        TOKEN_PATH.chmod(0o600)
    except OSError:
        pass
    return token


def load_lan_token() -> str | None:
    if not TOKEN_PATH.is_file():
        return None
    token = TOKEN_PATH.read_text(encoding='utf-8').strip()
    return token or None


def is_loopback_client(handler) -> bool:
    addr = ''
    try:
        addr = str((handler.client_address or ('',))[0] or '')
    except Exception:
        addr = ''
    a = addr.strip().lower()
    return a in ('127.0.0.1', '::1', 'localhost') or a.startswith('127.')


def extract_bearer(handler) -> str | None:
    auth = handler.headers.get('Authorization') or ''
    if auth.lower().startswith('bearer '):
        return auth[7:].strip() or None
    return (handler.headers.get('X-Otacon-Token') or '').strip() or None


def lan_auth_required(bind_mode: str) -> bool:
    return bind_mode == 'lan'


def check_lan_auth(handler, bind_mode: str, token: str | None) -> bool:
    if not lan_auth_required(bind_mode):
        return True
    if not token:
        return False
    provided = extract_bearer(handler)
    if not provided:
        return False
    return hmac.compare_digest(provided, token)


# Endpoints that change state or expose sensitive operations — require LAN token.
PROTECTED_PATHS = frozenset({
    '/api/save',
    '/api/preferences',
    '/api/agent/voice',
    '/api/chat_with_agent',
    '/api/conversation',
    '/api/conversation/delete',
    '/api/memory',
    '/api/memory/delete',
    '/api/synthesize_agent_speech',
    '/api/preview_voice',
    '/api/generate_image',
    '/api/generate_video',
    '/api/transcribe_audio',
    '/api/installer/voice_actions',
    '/api/installer/plan',
    '/api/plan',
    '/api/expansion/event',
    '/api/expansion/bootstrap',
    '/api/expansion/jobs/create',
    '/api/expansion/pages/register',
    '/api/expansion/rex/transition',
    '/api/expansion/rex/queue',
    '/api/expansion/rex/discover',
    '/api/expansion/rex/plan',
    '/api/expansion/rex/peer-review',
    '/api/expansion/policy/check',
    '/api/expansion/rex/tick',
    '/api/expansion/tools/invoke',
    '/api/expansion/learning/observe',
    '/api/expansion/learning/reinforce',
    '/api/expansion/learning/contradict',
    '/api/expansion/learning/revise',
})


def path_is_protected(path: str) -> bool:
    return path.split('?', 1)[0] in PROTECTED_PATHS


def safe_ui_path(ui_root: Path, request_path: str) -> Path | None:
    """Resolve a static UI path under ui_root; reject traversal."""
    rel = (request_path or '/').split('?', 1)[0].lstrip('/')
    if not rel:
        rel = 'index.html'
    if '..' in Path(rel).parts:
        return None
    candidate = (ui_root / rel).resolve()
    try:
        candidate.relative_to(ui_root.resolve())
    except ValueError:
        return None
    return candidate if candidate.is_file() else None


def safe_config_root(requested: str | Path | None) -> Path:
    """Confine writable config roots to known-safe directories."""
    if requested is None or str(requested).strip() == '':
        return CONFIG_ROOT.resolve()
    root = Path(requested).expanduser().resolve()
    for allowed in SAFE_WRITE_ROOTS:
        try:
            root.relative_to(allowed)
            return root
        except ValueError:
            continue
    # Only allow the canonical config root itself.
    if root == CONFIG_ROOT.resolve():
        return root
    raise ValueError('OUTPUT_PATH_FORBIDDEN')
