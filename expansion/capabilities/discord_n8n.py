"""Optional Discord / n8n integrations — user-owned credentials only.

No bundled private tokens or workflows. Failure must not break Expansion.

States (honest UX):
  NEEDS_CREDENTIAL — component supported; waiting for user token/URL
  NEEDS_AUTHORIZATION — credential present; bot invite / OAuth still needed
  NOT_INSTALLED — local service (e.g. n8n) not deployed yet
  READY / LIMITED / FAILED — as before
"""
from __future__ import annotations

import json
import os
from typing import Optional

from expansion.capabilities import CapabilityReport, CapabilityState, _forbidden_private_paths
from expansion.persist import atomic_write_json, read_json
from expansion.secrets import has_secret_key, read_env_secret, write_env_secret
from expansion.state_layout import StateLayout, resolve_layout
from expansion.topology import load_topology

DISCORD_ID = 'discord'
N8N_ID = 'n8n'
OWNER_AGENT = 'aria'
DISCORD_SECRET = 'discord'


def _discord_path(layout: StateLayout):
    return layout.user_preferences / 'discord.json'


def _n8n_path(layout: StateLayout):
    return layout.user_preferences / 'n8n.json'


def _discord_token_present(layout: StateLayout) -> bool:
    raw = read_json(_discord_path(layout), default={}) or {}
    if raw.get('bot_token') or raw.get('webhook_url'):
        return True
    if os.environ.get('OTACON_DISCORD_BOT_TOKEN') or os.environ.get('OTACON_DISCORD_WEBHOOK'):
        return True
    if has_secret_key(DISCORD_SECRET, 'DISCORD_BOT_TOKEN'):
        return True
    if has_secret_key(DISCORD_SECRET, 'DISCORD_WEBHOOK_URL'):
        return True
    topo = load_topology()
    return bool(topo.discord_webhook_configured)


def probe_discord(layout: Optional[StateLayout] = None) -> CapabilityReport:
    layout = layout or resolve_layout()
    topo = load_topology()
    secrets = read_env_secret(DISCORD_SECRET)
    raw = read_json(_discord_path(layout), default={}) or {}
    webhook = bool(
        raw.get('webhook_url')
        or os.environ.get('OTACON_DISCORD_WEBHOOK')
        or secrets.get('DISCORD_WEBHOOK_URL')
        or topo.discord_webhook_configured
    )
    bot = bool(
        raw.get('bot_token')
        or os.environ.get('OTACON_DISCORD_BOT_TOKEN')
        or secrets.get('DISCORD_BOT_TOKEN')
    )
    authorized = bool(raw.get('guild_authorized') or secrets.get('DISCORD_GUILD_ID'))
    disc = {
        'webhook_configured': webhook,
        'bot_configured': bot,
        'guild_authorized': authorized,
        'auto_install': True,
        'user_action': 'credential' if not (webhook or bot) else (
            'authorization' if bot and not authorized else 'none'
        ),
        # never return secrets
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
    return CapabilityReport(
        DISCORD_ID, OWNER_AGENT, CapabilityState.LIMITED.value,
        detail='Discord credentials present; outbound delivery not fully verified yet.',
        config_keys_present=[k for k, v in (
            ('webhook', webhook), ('bot_token', bot), ('guild', authorized),
        ) if v],
        discovery=disc,
    )


def save_discord_bot_token(token: str, *, layout: Optional[StateLayout] = None) -> dict:
    """Store bot token under secrets/ (0600) — never in git or product JSON with the secret echoed."""
    layout = layout or resolve_layout()
    tok = (token or '').strip()
    if not tok:
        raise ValueError('bot token required')
    if len(tok) < 20:
        raise ValueError('token looks too short')
    write_env_secret(DISCORD_SECRET, {
        **read_env_secret(DISCORD_SECRET),
        'DISCORD_BOT_TOKEN': tok,
    })
    # Non-secret marker in preferences
    existing = read_json(_discord_path(layout), default={}) or {}
    existing['bot_configured'] = True
    existing.pop('bot_token', None)  # never keep plaintext token in prefs
    atomic_write_json(_discord_path(layout), existing)
    return {'ok': True, 'bot_configured': True, 'state': probe_discord(layout).state}


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


def probe_n8n(layout: Optional[StateLayout] = None) -> CapabilityReport:
    layout = layout or resolve_layout()
    raw = read_json(_n8n_path(layout), default={}) or {}
    url = (
        str(raw.get('url') or '').strip()
        or (os.environ.get('OTACON_N8N_URL') or '').strip()
    )
    key_set = bool(raw.get('api_key') or os.environ.get('OTACON_N8N_API_KEY'))
    installed = bool(raw.get('managed') or raw.get('installed'))
    disc = {
        'url': url,
        'api_key_configured': key_set,
        'managed': installed,
        'auto_install': True,
        'user_action': 'none' if url else 'install',
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
    if url and not key_set:
        return CapabilityReport(
            N8N_ID, OWNER_AGENT, CapabilityState.NEEDS_CREDENTIAL.value,
            detail='n8n URL set but API key missing (optional for local-only use).',
            config_keys_present=['url'], discovery=disc,
        )
    return CapabilityReport(
        N8N_ID, OWNER_AGENT, CapabilityState.READY.value,
        detail='n8n URL configured (workflow execution not bundled).',
        config_keys_present=['url'] + (['api_key'] if key_set else []),
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


def save_n8n_config(*, url: str, api_key: str = '', layout: Optional[StateLayout] = None) -> dict:
    layout = layout or resolve_layout()
    existing = read_json(_n8n_path(layout), default={}) or {}
    data = {
        'url': url.strip(),
        'api_key': api_key if api_key else existing.get('api_key', ''),
        'installed': True,
        'managed': bool(existing.get('managed')),
    }
    if _forbidden_private_paths(json.dumps({'url': data['url']})):
        raise ValueError('forbidden private topology in n8n config')
    atomic_write_json(_n8n_path(layout), data)
    return {'url': data['url'], 'api_key_configured': bool(data.get('api_key'))}


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
