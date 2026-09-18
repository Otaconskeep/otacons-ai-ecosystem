"""Otacon Discord bot process — durable gateway presence + event bridge.

Run as:  python -m expansion.integrations.discord_bot
Reads DISCORD_BOT_TOKEN from the environment (systemd EnvironmentFile) or
~/.config/otacon/secrets/discord.env.

Requires discord.py (installed by Expansion Discord setup into the Otacon venv).
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path


def _load_token() -> str:
    tok = (os.environ.get('DISCORD_BOT_TOKEN') or os.environ.get('OTACON_DISCORD_BOT_TOKEN') or '').strip()
    if tok:
        return tok
    secrets = Path.home() / '.config' / 'otacon' / 'secrets' / 'discord.env'
    if secrets.is_file():
        for line in secrets.read_text(encoding='utf-8', errors='replace').splitlines():
            line = line.strip()
            if line.startswith('DISCORD_BOT_TOKEN='):
                return line.split('=', 1)[1].strip()
    return ''


def _status_path() -> Path:
    override = (os.environ.get('OTACON_DISCORD_STATUS') or '').strip()
    if override:
        return Path(override)
    return Path.home() / '.local' / 'share' / 'otacon' / 'discord' / 'status.json'


def _write_status(payload: dict) -> None:
    path = _status_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + '\n', encoding='utf-8')
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def main() -> int:
    token = _load_token()
    if not token:
        _write_status({'ok': False, 'online': False, 'error': 'DISCORD_BOT_TOKEN missing', 'ts': time.time()})
        print('DISCORD_BOT_TOKEN missing', file=sys.stderr)
        return 2
    try:
        import discord
    except ImportError:
        _write_status({
            'ok': False, 'online': False,
            'error': 'discord.py not installed — run Discord setup from Expansion',
            'ts': time.time(),
        })
        print('discord.py not installed', file=sys.stderr)
        return 3

    intents = discord.Intents.default()
    intents.message_content = True
    client = discord.Client(intents=intents)

    @client.event
    async def on_ready():
        guilds = [{'id': str(g.id), 'name': g.name} for g in client.guilds]
        _write_status({
            'ok': True,
            'online': True,
            'bot_user': str(client.user),
            'bot_id': str(client.user.id) if client.user else '',
            'guild_count': len(guilds),
            'guilds': guilds[:20],
            'ts': time.time(),
        })
        # Persist guild marker for Expansion probe (non-secret).
        try:
            from expansion.capabilities.discord_n8n import mark_discord_guild_authorized
            if guilds:
                mark_discord_guild_authorized(guilds[0]['id'])
        except Exception:
            pass

    @client.event
    async def on_disconnect():
        _write_status({'ok': False, 'online': False, 'error': 'disconnected', 'ts': time.time()})

    try:
        client.run(token, log_handler=None)
    except discord.LoginFailure:
        _write_status({'ok': False, 'online': False, 'error': 'invalid_token', 'ts': time.time()})
        return 4
    except Exception as exc:
        _write_status({'ok': False, 'online': False, 'error': str(exc)[:200], 'ts': time.time()})
        return 5
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
