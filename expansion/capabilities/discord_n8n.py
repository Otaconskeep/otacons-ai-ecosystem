"""Optional Discord / n8n integrations — user-owned credentials only.

No bundled private tokens or workflows. Failure must not break Expansion.
"""
from __future__ import annotations

import json
import os
from typing import Optional

from expansion.capabilities import CapabilityReport, CapabilityState, _forbidden_private_paths
from expansion.persist import atomic_write_json, read_json
from expansion.state_layout import StateLayout, resolve_layout
from expansion.topology import load_topology

DISCORD_ID = 'discord'
N8N_ID = 'n8n'
OWNER_AGENT = 'aria'


def _discord_path(layout: StateLayout):
    return layout.user_preferences / 'discord.json'


def _n8n_path(layout: StateLayout):
    return layout.user_preferences / 'n8n.json'


def probe_discord(layout: Optional[StateLayout] = None) -> CapabilityReport:
    layout = layout or resolve_layout()
    topo = load_topology()
    raw = read_json(_discord_path(layout), default={}) or {}
    webhook = bool(raw.get('webhook_url') or os.environ.get('OTACON_DISCORD_WEBHOOK'))
    bot = bool(raw.get('bot_token') or os.environ.get('OTACON_DISCORD_BOT_TOKEN'))
    configured = webhook or bot or bool(topo.discord_webhook_configured)
    disc = {
        'webhook_configured': webhook or bool(topo.discord_webhook_configured),
        'bot_configured': bot,
        # never return secrets
    }
    if not configured:
        return CapabilityReport(
            DISCORD_ID, OWNER_AGENT, CapabilityState.UNAVAILABLE.value,
            detail='Discord not configured (optional).',
            discovery=disc,
        )
    return CapabilityReport(
        DISCORD_ID, OWNER_AGENT, CapabilityState.LIMITED.value,
        detail='Discord credentials present; outbound delivery not verified by Expansion.',
        config_keys_present=[k for k, v in disc.items() if v],
        discovery=disc,
    )


def probe_n8n(layout: Optional[StateLayout] = None) -> CapabilityReport:
    layout = layout or resolve_layout()
    raw = read_json(_n8n_path(layout), default={}) or {}
    url = (
        str(raw.get('url') or '').strip()
        or (os.environ.get('OTACON_N8N_URL') or '').strip()
    )
    key_set = bool(raw.get('api_key') or os.environ.get('OTACON_N8N_API_KEY'))
    disc = {'url': url, 'api_key_configured': key_set}
    forbidden = _forbidden_private_paths(url)
    if forbidden:
        return CapabilityReport(
            N8N_ID, OWNER_AGENT, CapabilityState.FAILED.value,
            detail=f'forbidden private topology: {forbidden[0]}',
            discovery={'url': url, 'api_key_configured': key_set},
        )
    if not url:
        return CapabilityReport(
            N8N_ID, OWNER_AGENT, CapabilityState.UNAVAILABLE.value,
            detail='n8n not configured (optional).',
            discovery=disc,
        )
    if url and not key_set:
        return CapabilityReport(
            N8N_ID, OWNER_AGENT, CapabilityState.LIMITED.value,
            detail='n8n URL set but API key missing.',
            config_keys_present=['url'], discovery=disc,
        )
    return CapabilityReport(
        N8N_ID, OWNER_AGENT, CapabilityState.READY.value,
        detail='n8n URL and API key configured (workflow execution not bundled).',
        config_keys_present=['url', 'api_key'], discovery=disc,
    )


def save_discord_config(*, webhook_url: str = '', layout: Optional[StateLayout] = None) -> dict:
    layout = layout or resolve_layout()
    data = {'webhook_url': webhook_url}
    if _forbidden_private_paths(json.dumps(data)):
        raise ValueError('forbidden private topology in discord config')
    atomic_write_json(_discord_path(layout), data)
    return {'webhook_configured': bool(webhook_url)}


def save_n8n_config(*, url: str, api_key: str = '', layout: Optional[StateLayout] = None) -> dict:
    layout = layout or resolve_layout()
    existing = read_json(_n8n_path(layout), default={}) or {}
    data = {
        'url': url.strip(),
        'api_key': api_key if api_key else existing.get('api_key', ''),
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
