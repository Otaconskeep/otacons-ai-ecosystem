"""Optional Discord / n8n integrations — user-owned credentials only.

No bundled private tokens or workflows. Failure must not break Expansion.

States (honest UX):
  NEEDS_CREDENTIAL — component supported; waiting for user token/URL
  NEEDS_AUTHORIZATION — credential present; bot invite / OAuth still needed
  NOT_INSTALLED — local service (e.g. n8n) not deployed yet
  INSTALLING — Otacon is deploying
  READY / LIMITED / FAILED — as before
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Optional

from expansion.capabilities import CapabilityReport, CapabilityState, _forbidden_private_paths
from expansion.persist import atomic_write_json, read_json
from expansion.secrets import has_secret_key, read_env_secret, write_env_secret
from expansion.state_layout import StateLayout, resolve_layout
from expansion.topology import load_topology

DISCORD_ID = 'discord'
N8N_ID = 'n8n'
OWNER_AGENT = 'aria'
DISCORD_SECRET = 'discord'
DISCORD_API = 'https://discord.com/api/v10'


def _discord_path(layout: StateLayout):
    return layout.user_preferences / 'discord.json'


def _n8n_path(layout: StateLayout):
    return layout.user_preferences / 'n8n.json'


def _discord_data_dir() -> Path:
    d = Path.home() / '.local' / 'share' / 'otacon' / 'discord'
    d.mkdir(parents=True, exist_ok=True)
    return d


def _bot_status_path() -> Path:
    return _discord_data_dir() / 'status.json'


def _repo_root() -> Path:
    env = (os.environ.get('OTACON_INSTALL_DIR') or '').strip()
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[2]


def _python_bin() -> str:
    root = _repo_root()
    for cand in (
        root / '.venv' / 'bin' / 'python',
        root / 'venv' / 'bin' / 'python',
        Path(sys.executable),
    ):
        if cand and Path(cand).is_file():
            return str(cand)
    return sys.executable or 'python3'


def _bot_token(layout: Optional[StateLayout] = None) -> str:
    secrets = read_env_secret(DISCORD_SECRET)
    if secrets.get('DISCORD_BOT_TOKEN'):
        return secrets['DISCORD_BOT_TOKEN'].strip()
    env = (os.environ.get('OTACON_DISCORD_BOT_TOKEN') or '').strip()
    if env:
        return env
    layout = layout or resolve_layout()
    raw = read_json(_discord_path(layout), default={}) or {}
    return str(raw.get('bot_token') or '').strip()


def _discord_token_present(layout: StateLayout) -> bool:
    raw = read_json(_discord_path(layout), default={}) or {}
    if raw.get('bot_token') or raw.get('webhook_url') or raw.get('bot_configured'):
        return True
    if os.environ.get('OTACON_DISCORD_BOT_TOKEN') or os.environ.get('OTACON_DISCORD_WEBHOOK'):
        return True
    if has_secret_key(DISCORD_SECRET, 'DISCORD_BOT_TOKEN'):
        return True
    if has_secret_key(DISCORD_SECRET, 'DISCORD_WEBHOOK_URL'):
        return True
    topo = load_topology()
    return bool(topo.discord_webhook_configured)


def read_bot_runtime_status() -> dict:
    path = _bot_status_path()
    if not path.is_file():
        return {'online': False}
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        return data if isinstance(data, dict) else {'online': False}
    except (OSError, json.JSONDecodeError):
        return {'online': False}


def validate_discord_token(token: str, *, timeout: float = 10.0) -> dict[str, Any]:
    """Validate bot token via Discord REST users/@me."""
    tok = (token or '').strip()
    if not tok or len(tok) < 20:
        return {'ok': False, 'error': 'token looks too short'}
    req = urllib.request.Request(
        f'{DISCORD_API}/users/@me',
        headers={
            'Authorization': f'Bot {tok}',
            'User-Agent': 'Otacon-Expansion (https://otaconskeep.github.io, 1.0)',
        },
        method='GET',
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode('utf-8', errors='replace') or '{}')
    except urllib.error.HTTPError as exc:
        return {'ok': False, 'error': f'Discord HTTP {exc.code}', 'status': exc.code}
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        return {'ok': False, 'error': str(exc)[:200]}
    if not isinstance(body, dict) or not body.get('id'):
        return {'ok': False, 'error': 'unexpected Discord response'}
    return {
        'ok': True,
        'bot_id': str(body.get('id')),
        'bot_username': str(body.get('username') or ''),
        'bot_discriminator': str(body.get('discriminator') or ''),
        'application_id': str(body.get('id')),  # bot user id == application id for classic bots
    }


def fetch_bot_guilds(token: str, *, timeout: float = 10.0) -> dict[str, Any]:
    tok = (token or '').strip()
    if not tok:
        return {'ok': False, 'guilds': [], 'error': 'no token'}
    req = urllib.request.Request(
        f'{DISCORD_API}/users/@me/guilds',
        headers={
            'Authorization': f'Bot {tok}',
            'User-Agent': 'Otacon-Expansion (https://otaconskeep.github.io, 1.0)',
        },
        method='GET',
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = json.loads(resp.read().decode('utf-8', errors='replace') or '[]')
    except urllib.error.HTTPError as exc:
        return {'ok': False, 'guilds': [], 'error': f'HTTP {exc.code}'}
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        return {'ok': False, 'guilds': [], 'error': str(exc)[:200]}
    guilds = []
    if isinstance(raw, list):
        for g in raw[:30]:
            if isinstance(g, dict) and g.get('id'):
                guilds.append({'id': str(g['id']), 'name': str(g.get('name') or '')})
    return {'ok': True, 'guilds': guilds, 'guild_count': len(guilds)}


def discord_invite_url(
    *,
    client_id: str = '',
    layout: Optional[StateLayout] = None,
) -> dict[str, Any]:
    layout = layout or resolve_layout()
    secrets = read_env_secret(DISCORD_SECRET)
    raw = read_json(_discord_path(layout), default={}) or {}
    cid = (
        (client_id or '').strip()
        or secrets.get('DISCORD_CLIENT_ID', '').strip()
        or str(raw.get('bot_id') or raw.get('application_id') or '').strip()
    )
    if not cid:
        tok = _bot_token(layout)
        if tok:
            v = validate_discord_token(tok)
            if v.get('ok'):
                cid = str(v.get('bot_id') or '')
                raw['bot_id'] = cid
                raw['application_id'] = cid
                atomic_write_json(_discord_path(layout), raw)
    if not cid:
        return {
            'ok': False,
            'error': 'bot client id unknown — paste a valid token first',
            'invite_url': '',
        }
    # bot + applications.commands
    perms = 2048 | 1024 | 3072  # send + view + optional; keep modest
    # Use standard invite with applications.commands scope
    q = urllib.parse.urlencode({
        'client_id': cid,
        'permissions': '274877975552',  # Send Messages, Embed, Read History, Use Slash
        'scope': 'bot applications.commands',
    })
    url = f'https://discord.com/oauth2/authorize?{q}'
    return {'ok': True, 'invite_url': url, 'client_id': cid, 'permissions': perms}


def probe_discord(layout: Optional[StateLayout] = None) -> CapabilityReport:
    layout = layout or resolve_layout()
    topo = load_topology()
    secrets = read_env_secret(DISCORD_SECRET)
    raw = read_json(_discord_path(layout), default={}) or {}
    runtime = read_bot_runtime_status()
    webhook = bool(
        raw.get('webhook_url')
        or os.environ.get('OTACON_DISCORD_WEBHOOK')
        or secrets.get('DISCORD_WEBHOOK_URL')
        or topo.discord_webhook_configured
    )
    bot = bool(
        raw.get('bot_token')
        or raw.get('bot_configured')
        or os.environ.get('OTACON_DISCORD_BOT_TOKEN')
        or secrets.get('DISCORD_BOT_TOKEN')
    )
    authorized = bool(
        raw.get('guild_authorized')
        or secrets.get('DISCORD_GUILD_ID')
        or (runtime.get('guild_count') or 0) > 0
    )
    online = bool(runtime.get('online') and runtime.get('ok'))
    service_ready = bool(raw.get('service_installed'))
    disc = {
        'webhook_configured': webhook,
        'bot_configured': bot,
        'guild_authorized': authorized,
        'bot_online': online,
        'service_installed': service_ready,
        'invite_url': (raw.get('invite_url') or ''),
        'auto_install': True,
        'user_action': 'credential' if not (webhook or bot) else (
            'authorization' if bot and not authorized else 'none'
        ),
    }
    if not webhook and not bot:
        return CapabilityReport(
            DISCORD_ID, OWNER_AGENT, CapabilityState.NEEDS_CREDENTIAL.value,
            detail=(
                'Discord is supported. Otacon can install the bot service — '
                'paste a bot token (or webhook) when ready.'
            ),
            discovery=disc,
        )
    if bot and not authorized:
        return CapabilityReport(
            DISCORD_ID, OWNER_AGENT, CapabilityState.NEEDS_AUTHORIZATION.value,
            detail=(
                'Discord bot token stored. Authorize the bot in your Discord server '
                '(Otacon can open the OAuth invite).'
            ),
            config_keys_present=['bot_token'],
            discovery=disc,
        )
    if bot and authorized and online:
        return CapabilityReport(
            DISCORD_ID, OWNER_AGENT, CapabilityState.READY.value,
            detail='Discord bot online and connected to a server.',
            config_keys_present=['bot_token', 'guild'],
            discovery=disc,
        )
    if bot and authorized:
        return CapabilityReport(
            DISCORD_ID, OWNER_AGENT, CapabilityState.LIMITED.value,
            detail=(
                'Discord authorized. Start the bot service to go READY '
                '(Otacon can enable restart-on-failure).'
            ),
            config_keys_present=['bot_token', 'guild'],
            discovery=disc,
        )
    return CapabilityReport(
        DISCORD_ID, OWNER_AGENT, CapabilityState.LIMITED.value,
        detail='Discord credentials present; outbound delivery not fully verified yet.',
        config_keys_present=[k for k, v in (
            ('webhook', webhook), ('bot_token', bot), ('guild', authorized),
        ) if v],
        discovery=disc,
    )


def save_discord_bot_token(token: str, *, layout: Optional[StateLayout] = None) -> dict:
    """Store bot token under secrets/ (0600) — never echo the secret."""
    layout = layout or resolve_layout()
    tok = (token or '').strip()
    if not tok:
        raise ValueError('bot token required')
    if len(tok) < 20:
        raise ValueError('token looks too short')
    validation = validate_discord_token(tok)
    write_env_secret(DISCORD_SECRET, {
        **read_env_secret(DISCORD_SECRET),
        'DISCORD_BOT_TOKEN': tok,
        **({'DISCORD_CLIENT_ID': validation['bot_id']} if validation.get('ok') else {}),
    })
    existing = read_json(_discord_path(layout), default={}) or {}
    existing['bot_configured'] = True
    existing.pop('bot_token', None)
    if validation.get('ok'):
        existing['bot_validated'] = True
        existing['bot_id'] = validation.get('bot_id')
        existing['application_id'] = validation.get('bot_id')
        existing['bot_username'] = validation.get('bot_username')
        inv = discord_invite_url(client_id=str(validation.get('bot_id') or ''), layout=layout)
        if inv.get('ok'):
            existing['invite_url'] = inv['invite_url']
        # Auto-detect existing guild membership
        g = fetch_bot_guilds(tok)
        if g.get('ok') and g.get('guilds'):
            existing['guild_authorized'] = True
            existing['guild_id'] = g['guilds'][0]['id']
            secrets = read_env_secret(DISCORD_SECRET)
            secrets['DISCORD_GUILD_ID'] = g['guilds'][0]['id']
            write_env_secret(DISCORD_SECRET, secrets)
    else:
        existing['bot_validated'] = False
        existing['validate_error'] = validation.get('error') or 'invalid'
    atomic_write_json(_discord_path(layout), existing)
    return {
        'ok': bool(validation.get('ok')),
        'bot_configured': True,
        'validated': bool(validation.get('ok')),
        'bot_username': validation.get('bot_username') or '',
        'invite_url': existing.get('invite_url') or '',
        'error': '' if validation.get('ok') else (validation.get('error') or 'invalid token'),
        'state': probe_discord(layout).state,
    }


def mark_discord_guild_authorized(guild_id: str = '', *, layout: Optional[StateLayout] = None) -> dict:
    layout = layout or resolve_layout()
    secrets = read_env_secret(DISCORD_SECRET)
    if guild_id:
        secrets['DISCORD_GUILD_ID'] = guild_id.strip()
        write_env_secret(DISCORD_SECRET, secrets)
    existing = read_json(_discord_path(layout), default={}) or {}
    existing['guild_authorized'] = True
    if guild_id:
        existing['guild_id'] = guild_id.strip()
    atomic_write_json(_discord_path(layout), existing)
    return {'ok': True, 'state': probe_discord(layout).state}


def install_discord_dependencies() -> dict:
    py = _python_bin()
    try:
        r = subprocess.run(
            [py, '-m', 'pip', 'install', '--quiet', 'discord.py>=2.3.0'],
            capture_output=True, text=True, timeout=300, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {'ok': False, 'error': str(exc)}
    if r.returncode != 0:
        return {'ok': False, 'error': ((r.stderr or r.stdout) or '')[-400:]}
    return {'ok': True, 'python': py}


def _write_discord_service_unit(*, layout: Optional[StateLayout] = None) -> dict:
    layout = layout or resolve_layout()
    py = _python_bin()
    root = _repo_root()
    data = _discord_data_dir()
    secrets_file = Path.home() / '.config' / 'otacon' / 'secrets' / 'discord.env'
    unit_dir = Path.home() / '.config' / 'otacon'
    unit_dir.mkdir(parents=True, exist_ok=True)
    draft = unit_dir / 'otacon-discord.service.draft'
    unit_body = f"""[Unit]
Description=Otacon Discord Bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory={root}
Environment=OTACON_INSTALL_DIR={root}
Environment=PYTHONPATH={root}
Environment=OTACON_DISCORD_STATUS={data / 'status.json'}
EnvironmentFile=-{secrets_file}
ExecStart={py} -m expansion.integrations.discord_bot
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
"""
    draft.write_text(unit_body, encoding='utf-8')
    try:
        os.chmod(draft, 0o600)
    except OSError:
        pass
    # User systemd if available (no root required)
    user_unit = Path.home() / '.config' / 'systemd' / 'user' / 'otacon-discord.service'
    installed_user = False
    try:
        user_unit.parent.mkdir(parents=True, exist_ok=True)
        user_unit.write_text(unit_body.replace('WantedBy=multi-user.target', 'WantedBy=default.target'), encoding='utf-8')
        subprocess.run(['systemctl', '--user', 'daemon-reload'], capture_output=True, timeout=15, check=False)
        subprocess.run(['systemctl', '--user', 'enable', '--now', 'otacon-discord.service'],
                       capture_output=True, timeout=30, check=False)
        installed_user = True
    except (OSError, subprocess.TimeoutExpired):
        installed_user = False

    existing = read_json(_discord_path(layout), default={}) or {}
    existing['service_installed'] = True
    existing['service_draft'] = str(draft)
    existing['service_user_unit'] = str(user_unit) if installed_user else ''
    atomic_write_json(_discord_path(layout), existing)
    return {
        'ok': True,
        'draft': str(draft),
        'user_unit': str(user_unit) if installed_user else '',
        'user_enabled': installed_user,
        'python': py,
    }


def setup_discord_service(*, layout: Optional[StateLayout] = None) -> dict:
    """Install deps, storage, service unit, routing prefs — token still user-supplied."""
    layout = layout or resolve_layout()
    steps = []
    deps = install_discord_dependencies()
    steps.append({'id': 'deps', 'ok': deps.get('ok'), 'detail': deps})
    data = _discord_data_dir()
    steps.append({'id': 'storage', 'ok': True, 'detail': str(data)})
    existing = read_json(_discord_path(layout), default={}) or {}
    existing.setdefault('agent_routing', {'default': 'aria', 'events': ['message', 'ready']})
    existing['service_prep'] = True
    atomic_write_json(_discord_path(layout), existing)
    steps.append({'id': 'routing', 'ok': True})
    unit = _write_discord_service_unit(layout=layout)
    steps.append({'id': 'service', 'ok': unit.get('ok'), 'detail': unit})
    # If token already present, try start + guild detect
    tok = _bot_token(layout)
    started = False
    if tok and unit.get('user_enabled'):
        try:
            subprocess.run(
                ['systemctl', '--user', 'restart', 'otacon-discord.service'],
                capture_output=True, timeout=30, check=False,
            )
            started = True
        except (OSError, subprocess.TimeoutExpired):
            started = False
    report = probe_discord(layout)
    return {
        'ok': all(s.get('ok') for s in steps),
        'steps': steps,
        'started': started,
        'state': report.state,
        'detail': report.detail,
        'discovery': report.discovery,
        'invite_url': (existing.get('invite_url') or discord_invite_url(layout=layout).get('invite_url') or ''),
    }


def start_discord_bot(*, layout: Optional[StateLayout] = None) -> dict:
    layout = layout or resolve_layout()
    if not _bot_token(layout):
        return {'ok': False, 'error': 'bot token required', 'state': probe_discord(layout).state}
    unit = _write_discord_service_unit(layout=layout)
    try:
        r = subprocess.run(
            ['systemctl', '--user', 'restart', 'otacon-discord.service'],
            capture_output=True, text=True, timeout=30, check=False,
        )
        ok = r.returncode == 0
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {'ok': False, 'error': str(exc), 'unit': unit, 'state': probe_discord(layout).state}
    # Brief wait for status file
    for _ in range(15):
        st = read_bot_runtime_status()
        if st.get('online'):
            break
        time.sleep(1)
    report = probe_discord(layout)
    return {
        'ok': ok or bool(read_bot_runtime_status().get('online')),
        'unit': unit,
        'runtime': read_bot_runtime_status(),
        'state': report.state,
        'detail': report.detail,
        'discovery': report.discovery,
    }


def probe_n8n(layout: Optional[StateLayout] = None) -> CapabilityReport:
    layout = layout or resolve_layout()
    raw = read_json(_n8n_path(layout), default={}) or {}
    url = (
        str(raw.get('url') or '').strip()
        or (os.environ.get('OTACON_N8N_URL') or '').strip()
    )
    key_set = bool(
        raw.get('api_key')
        or os.environ.get('OTACON_N8N_API_KEY')
        or has_secret_key('n8n', 'N8N_API_KEY')
    )
    installed = bool(raw.get('managed') or raw.get('installed'))
    healthy = False
    if url:
        try:
            from expansion.capabilities.n8n_sidecar import n8n_endpoint_healthy
            healthy, _ = n8n_endpoint_healthy(url)
        except Exception:
            healthy = False
    disc = {
        'url': url,
        'api_key_configured': key_set,
        'managed': installed,
        'healthy': healthy,
        'auto_install': True,
        'user_action': 'none' if (url or installed) else 'install',
    }
    forbidden = _forbidden_private_paths(url)
    if forbidden:
        return CapabilityReport(
            N8N_ID, OWNER_AGENT, CapabilityState.FAILED.value,
            detail=f'forbidden private topology: {forbidden[0]}',
            discovery={'url': url, 'api_key_configured': key_set},
        )
    if not url and not installed:
        return CapabilityReport(
            N8N_ID, OWNER_AGENT, CapabilityState.NOT_INSTALLED.value,
            detail=(
                'n8n is not installed yet. Otacon can deploy a local Docker n8n '
                '(no credential required for the base service).'
            ),
            discovery=disc,
        )
    if url and healthy:
        return CapabilityReport(
            N8N_ID, OWNER_AGENT, CapabilityState.READY.value,
            detail='n8n is running locally and registered with OtaconsKeep.',
            config_keys_present=['url'] + (['api_key'] if key_set else []),
            discovery=disc,
        )
    if url and not healthy:
        return CapabilityReport(
            N8N_ID, OWNER_AGENT, CapabilityState.LIMITED.value,
            detail='n8n URL registered but health check failed — start the sidecar.',
            config_keys_present=['url'],
            discovery=disc,
        )
    return CapabilityReport(
        N8N_ID, OWNER_AGENT, CapabilityState.NOT_INSTALLED.value,
        detail='n8n marked installed but no URL — redeploy.',
        discovery=disc,
    )


def save_discord_config(*, webhook_url: str = '', layout: Optional[StateLayout] = None) -> dict:
    layout = layout or resolve_layout()
    data = {'webhook_url': webhook_url}
    if _forbidden_private_paths(json.dumps(data)):
        raise ValueError('forbidden private topology in discord config')
    if webhook_url:
        write_env_secret(DISCORD_SECRET, {
            **read_env_secret(DISCORD_SECRET),
            'DISCORD_WEBHOOK_URL': webhook_url.strip(),
        })
        data = {'webhook_configured': True}
    atomic_write_json(_discord_path(layout), data)
    return {'webhook_configured': bool(webhook_url), 'state': probe_discord(layout).state}


def save_n8n_config(
    *,
    url: str,
    api_key: str = '',
    layout: Optional[StateLayout] = None,
    managed: bool = False,
) -> dict:
    layout = layout or resolve_layout()
    existing = read_json(_n8n_path(layout), default={}) or {}
    data = {
        'url': url.strip().rstrip('/'),
        'installed': True,
        'managed': bool(managed or existing.get('managed')),
        'api_key_configured': bool(api_key or existing.get('api_key') or has_secret_key('n8n', 'N8N_API_KEY')),
    }
    if api_key:
        write_env_secret('n8n', {
            **read_env_secret('n8n'),
            'N8N_API_KEY': api_key.strip(),
        })
        data['api_key_configured'] = True
    if _forbidden_private_paths(json.dumps({'url': data['url']})):
        raise ValueError('forbidden private topology in n8n config')
    # Never persist plaintext api_key in prefs
    existing_clean = {k: v for k, v in existing.items() if k != 'api_key'}
    existing_clean.update(data)
    atomic_write_json(_n8n_path(layout), existing_clean)
    return {
        'url': data['url'],
        'api_key_configured': data['api_key_configured'],
        'managed': data['managed'],
        'state': probe_n8n(layout).state,
    }


def probe_all_optional(layout: Optional[StateLayout] = None) -> dict:
    from expansion.capabilities.video_studio import probe_video_studio
    from expansion.capabilities.home_assistant import probe_home_assistant
    from expansion.capabilities.voice_trainer import probe_voice_trainer
    layout = layout or resolve_layout()
    return {
        'video_studio': probe_video_studio(layout).to_dict(),
        'voice_trainer': probe_voice_trainer().to_dict(),
        'home_assistant': probe_home_assistant(layout).to_dict(),
        'discord': probe_discord(layout).to_dict(),
        'n8n': probe_n8n(layout).to_dict(),
    }
