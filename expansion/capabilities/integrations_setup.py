"""Recommended integrations checklist — Otacon installs; user supplies credentials once.

Surfaces Discord / Home Assistant / n8n as Configure-now flows for Ops + installer.
"""
from __future__ import annotations

from typing import Any, Optional

from expansion.capabilities.discord_n8n import (
    discord_invite_url,
    probe_discord,
    probe_n8n,
    save_discord_bot_token,
    setup_discord_service,
    start_discord_bot,
    mark_discord_guild_authorized,
)
from expansion.capabilities.home_assistant import (
    load_ha_config,
    probe_home_assistant,
    save_ha_config,
    verify_home_assistant,
)
from expansion.state_layout import StateLayout, resolve_layout

RECOMMENDED = (
    ('core', 'Core', True, False),
    ('agents', 'Agents', True, False),
    ('voice', 'Voice', True, False),
    ('expansion', 'Expansion', True, False),
    ('video_studio', 'Video Studio', True, False),
    ('image_studio', 'Image Studio', True, False),
    ('music_studio', 'Music Studio', True, False),
    ('n8n', 'n8n', True, False),
    ('discord', 'Discord', True, True),
    ('home_assistant', 'Home Assistant', True, True),
)


def integrations_status(layout: Optional[StateLayout] = None) -> dict[str, Any]:
    layout = layout or resolve_layout()
    discord = probe_discord(layout).to_dict()
    ha = probe_home_assistant(layout).to_dict()
    n8n = probe_n8n(layout).to_dict()
    items = []
    for key, label, auto, needs_cred in RECOMMENDED:
        if key == 'discord':
            st = discord.get('state')
            action = (discord.get('discovery') or {}).get('user_action') or 'none'
            items.append({
                'id': key, 'label': label, 'auto_install': auto,
                'needs_credential': needs_cred or action == 'credential',
                'state': st,
                'user_action': action,
                'detail': discord.get('detail'),
                'invite_url': (discord.get('discovery') or {}).get('invite_url') or '',
            })
        elif key == 'home_assistant':
            st = ha.get('state')
            action = (ha.get('discovery') or {}).get('user_action') or 'none'
            items.append({
                'id': key, 'label': label, 'auto_install': auto,
                'needs_credential': True,
                'state': st,
                'user_action': action,
                'detail': ha.get('detail'),
            })
        elif key == 'n8n':
            st = n8n.get('state')
            items.append({
                'id': key, 'label': label, 'auto_install': auto,
                'needs_credential': False,
                'state': st,
                'user_action': (n8n.get('discovery') or {}).get('user_action') or 'none',
                'detail': n8n.get('detail'),
                'url': (n8n.get('discovery') or {}).get('url') or '',
            })
        else:
            items.append({
                'id': key, 'label': label, 'auto_install': auto,
                'needs_credential': False,
                'state': 'READY',
                'user_action': 'none',
                'detail': 'Installed with Core / Expansion.',
            })
    return {
        'ok': True,
        'aria': (
            'I can handle Discord, Home Assistant, and n8n. '
            'I only ask for credentials when they are actually required.'
        ),
        'recommended': items,
        'discord': discord,
        'home_assistant': ha,
        'n8n': n8n,
    }


def configure_integration(
    which: str,
    *,
    token: str = '',
    url: str = '',
    guild_id: str = '',
    layout: Optional[StateLayout] = None,
) -> dict[str, Any]:
    """Run the Otacon configure flow for one integration."""
    layout = layout or resolve_layout()
    which = (which or '').strip().lower().replace('-', '_')
    if which in ('discord', 'discord_bot'):
        prep = setup_discord_service(layout=layout)
        out: dict[str, Any] = {'ok': prep.get('ok'), 'component': 'discord', 'prep': prep}
        if token.strip():
            saved = save_discord_bot_token(token, layout=layout)
            out['token'] = {k: saved[k] for k in saved if k != 'token'}
            if not saved.get('ok'):
                out['ok'] = False
                out['error'] = saved.get('error') or 'token validation failed'
                out['state'] = saved.get('state')
                return out
        if guild_id.strip():
            out['authorized'] = mark_discord_guild_authorized(guild_id, layout=layout)
        inv = discord_invite_url(layout=layout)
        out['invite'] = inv
        # Start bot if token present
        if _has_discord_token(layout):
            out['start'] = start_discord_bot(layout=layout)
        report = probe_discord(layout)
        out['state'] = report.state
        out['detail'] = report.detail
        out['discovery'] = report.discovery
        out['checklist'] = _discord_checklist(report.to_dict(), prep, out)
        return out

    if which in ('home_assistant', 'ha', 'hass'):
        from expansion.capabilities.home_assistant_sidecar import ensure_home_assistant_sidecar

        # Easiest path: if caller did not supply credentials, deploy the managed
        # container first (same pattern as n8n), then ask only for the token.
        deploy = None
        if not url.strip() and not token.strip():
            deploy = ensure_home_assistant_sidecar(layout=layout)
            if not deploy.get('ok'):
                report = probe_home_assistant(layout)
                return {
                    'ok': False,
                    'component': 'home_assistant',
                    'error': deploy.get('error') or 'Home Assistant container deploy failed',
                    'deploy': deploy,
                    'state': report.state,
                    'detail': report.detail,
                    'prompt': {
                        'url': 'Home Assistant URL (auto: http://127.0.0.1:8123 after Docker)',
                        'token': 'Long-lived access token (after HA onboarding)',
                    },
                    'checklist': [
                        {'id': 'docker', 'label': 'Docker available', 'done': deploy.get('action') != 'docker_missing'},
                        {'id': 'deploy', 'label': 'HA container deployed', 'done': False},
                        {'id': 'token', 'label': 'Token stored securely', 'done': False},
                    ],
                }
            # Container up — still need token unless already saved.
            if not load_ha_config(layout).get('token_configured'):
                report = probe_home_assistant(layout)
                return {
                    'ok': True,
                    'component': 'home_assistant',
                    'deploy': deploy,
                    'state': report.state,
                    'detail': report.detail,
                    'discovery': report.discovery,
                    'prompt': {
                        'url': deploy.get('endpoint') or 'http://127.0.0.1:8123',
                        'token': 'Long-lived access token (Profile → Long-Lived Access Tokens)',
                    },
                    'checklist': [
                        {'id': 'docker', 'label': 'Docker available', 'done': True},
                        {'id': 'deploy', 'label': 'HA container deployed', 'done': True},
                        {'id': 'ui', 'label': 'HA UI answering', 'done': True},
                        {'id': 'token', 'label': 'Token stored securely', 'done': False},
                        {'id': 'verify', 'label': 'Connection verified', 'done': False},
                    ],
                }

        if not url.strip():
            url = str((deploy or {}).get('endpoint') or load_ha_config(layout).get('url') or '')
        if not url.strip() and not token.strip():
            report = probe_home_assistant(layout)
            return {
                'ok': False,
                'component': 'home_assistant',
                'error': 'url and token required',
                'state': report.state,
                'detail': report.detail,
                'prompt': {
                    'url': 'Home Assistant URL (e.g. http://127.0.0.1:8123)',
                    'token': 'Long-lived access token',
                },
            }
        try:
            save_ha_config(url, token=token, layout=layout)
        except ValueError as exc:
            return {'ok': False, 'component': 'home_assistant', 'error': str(exc)}
        verified = verify_home_assistant(layout=layout) if token.strip() or load_ha_config(layout).get('token_configured') else {'ok': False}
        report = probe_home_assistant(layout)
        return {
            'ok': bool(verified.get('ok')),
            'component': 'home_assistant',
            'deploy': deploy,
            'verify': verified,
            'state': report.state,
            'detail': report.detail,
            'discovery': report.discovery,
            'checklist': [
                {'id': 'docker', 'label': 'Docker / HA container', 'done': True},
                {'id': 'url', 'label': 'HA URL saved', 'done': True},
                {'id': 'token', 'label': 'Token stored securely', 'done': bool(load_ha_config(layout).get('token_configured'))},
                {'id': 'verify', 'label': 'Connection verified', 'done': bool(verified.get('ok'))},
                {
                    'id': 'entities',
                    'label': f"Entities discovered ({verified.get('entity_count') or 0})",
                    'done': bool(verified.get('ok')),
                },
            ],
        }

    if which == 'n8n':
        from expansion.capabilities.n8n_sidecar import ensure_n8n_sidecar
        result = ensure_n8n_sidecar(layout=layout)
        report = probe_n8n(layout)
        return {
            'ok': bool(result.get('ok')),
            'component': 'n8n',
            'deploy': result,
            'state': report.state,
            'detail': report.detail,
            'discovery': report.discovery,
            'checklist': [
                {'id': 'docker', 'label': 'Docker available', 'done': result.get('action') != 'docker_missing'},
                {'id': 'deploy', 'label': 'n8n container deployed', 'done': bool(result.get('ok'))},
                {'id': 'volume', 'label': 'Persistent volume', 'done': bool(result.get('ok'))},
                {'id': 'health', 'label': 'Health check', 'done': bool(result.get('ok'))},
                {'id': 'register', 'label': 'Registered with Keep', 'done': bool(result.get('ok'))},
            ],
        }

    return {'ok': False, 'error': f'unknown integration: {which}'}


def _has_discord_token(layout: StateLayout) -> bool:
    from expansion.capabilities.discord_n8n import _bot_token
    return bool(_bot_token(layout))


def _discord_checklist(report: dict, prep: dict, out: dict) -> list[dict]:
    disc = report.get('discovery') or {}
    steps_ok = {s.get('id'): s.get('ok') for s in (prep.get('steps') or [])}
    return [
        {'id': 'deps', 'label': 'Installing Discord dependencies', 'done': bool(steps_ok.get('deps'))},
        {'id': 'config', 'label': 'Creating service configuration', 'done': bool(steps_ok.get('service'))},
        {'id': 'storage', 'label': 'Creating persistent bot storage', 'done': bool(steps_ok.get('storage'))},
        {'id': 'routing', 'label': 'Wiring Discord events into OtaconsKeep', 'done': bool(steps_ok.get('routing'))},
        {'id': 'restart', 'label': 'Configuring restart-on-failure', 'done': bool(steps_ok.get('service'))},
        {'id': 'token', 'label': 'Token stored securely', 'done': bool(disc.get('bot_configured'))},
        {'id': 'auth_token', 'label': 'Bot authenticated', 'done': report.get('state') not in (
            'NEEDS_CREDENTIAL',
        ) and bool(disc.get('bot_configured'))},
        {'id': 'authorize', 'label': 'Server connected', 'done': bool(disc.get('guild_authorized'))},
        {'id': 'online', 'label': 'Bot online', 'done': bool(disc.get('bot_online'))},
    ]
