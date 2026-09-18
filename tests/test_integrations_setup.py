"""Integrations auto-setup: Discord / HA / n8n readiness + configure flows."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from expansion.bootstrap import bootstrap_runtime_state
from expansion.capabilities.discord_n8n import (
    discord_invite_url,
    probe_discord,
    probe_n8n,
    save_discord_bot_token,
    save_n8n_config,
)
from expansion.capabilities.home_assistant import (
    load_ha_config,
    probe_home_assistant,
    save_ha_config,
    verify_home_assistant,
)
from expansion.capabilities.integrations_setup import configure_integration, integrations_status
from expansion.secrets import read_env_secret
from expansion.state_layout import resolve_layout


class IntegrationsCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        env = {
            'OTACON_EXPANSION_CONFIG_ROOT': str(self.root / 'cfg'),
            'OTACON_EXPANSION_DATA_ROOT': str(self.root / 'data'),
            'OTACON_EXPANSION_DATA_DIR': str(self.root / 'cfg' / 'agents'),
            'OTACON_EXPANSION_SECRETS_ROOT': str(self.root / 'cfg' / 'secrets'),
            'OTACON_SECRETS_DIR': str(self.root / 'cfg' / 'secrets'),
            'OTACON_EXPANSION_PRODUCT_ROOT': str(
                Path(__file__).resolve().parents[1] / 'expansion'
            ),
            'OTACON_DISCORD_BOT_TOKEN': '',
            'OTACON_DISCORD_WEBHOOK': '',
            'OTACON_HA_URL': '',
            'OTACON_HA_TOKEN': '',
            'OTACON_N8N_URL': '',
            'OTACON_N8N_API_KEY': '',
        }
        self._cm = mock.patch.dict(os.environ, env, clear=False)
        self._cm.start()
        self.layout = resolve_layout()
        self.layout.ensure_user_dirs()
        bootstrap_runtime_state(self.layout)

    def tearDown(self):
        self._cm.stop()
        self.tmp.cleanup()

    def test_integrations_status_checklist(self):
        st = integrations_status(self.layout)
        self.assertTrue(st['ok'])
        ids = [x['id'] for x in st['recommended']]
        self.assertIn('discord', ids)
        self.assertIn('home_assistant', ids)
        self.assertIn('n8n', ids)
        self.assertEqual(st['discord']['state'], 'NEEDS_CREDENTIAL')
        self.assertEqual(st['n8n']['state'], 'NOT_INSTALLED')

    def test_ha_token_goes_to_secrets_not_prefs(self):
        save_ha_config('http://127.0.0.1:8123', token='ha-secret-token-value-long', layout=self.layout)
        prefs = json.loads((self.layout.user_preferences / 'home_assistant.json').read_text())
        self.assertNotIn('token', prefs)
        self.assertTrue(prefs.get('token_configured'))
        secrets = read_env_secret('home_assistant')
        self.assertEqual(secrets.get('HA_TOKEN'), 'ha-secret-token-value-long')
        self.assertEqual(probe_home_assistant(self.layout).state, 'LIMITED')

    def test_ha_verify_marks_ready(self):
        save_ha_config('http://127.0.0.1:8123', token='ha-secret-token-value-long', layout=self.layout)

        class _Resp:
            def __init__(self, payload, code=200):
                self._payload = payload
                self.status = code

            def read(self):
                return self._payload

            def getcode(self):
                return self.status

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        def fake_urlopen(req, timeout=8.0):
            url = getattr(req, 'full_url', None) or str(req)
            if url.endswith('/api/'):
                return _Resp(b'{"message":"API running."}')
            if url.endswith('/api/states'):
                return _Resp(json.dumps([
                    {'entity_id': 'light.kitchen', 'state': 'on', 'attributes': {'friendly_name': 'Kitchen'}},
                    {'entity_id': 'switch.fan', 'state': 'off', 'attributes': {}},
                ]).encode())
            raise AssertionError(url)

        with mock.patch('urllib.request.urlopen', side_effect=fake_urlopen):
            out = verify_home_assistant(layout=self.layout)
        self.assertTrue(out['ok'])
        self.assertEqual(out['entity_count'], 2)
        self.assertEqual(probe_home_assistant(self.layout).state, 'READY')
        self.assertEqual(load_ha_config(self.layout)['entity_count'], 2)

    def test_discord_token_validate_and_invite(self):
        class _Resp:
            status = 200

            def __init__(self, payload):
                self._payload = payload

            def read(self):
                return self._payload

            def getcode(self):
                return 200

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        def fake_urlopen(req, timeout=10.0):
            url = getattr(req, 'full_url', None) or str(req)
            if url.endswith('/users/@me'):
                return _Resp(json.dumps({'id': '123456789012345678', 'username': 'otacon-bot'}).encode())
            if url.endswith('/users/@me/guilds'):
                return _Resp(b'[]')
            raise AssertionError(url)

        with mock.patch('urllib.request.urlopen', side_effect=fake_urlopen):
            saved = save_discord_bot_token('x' * 40, layout=self.layout)
        self.assertTrue(saved['ok'])
        self.assertTrue(saved['validated'])
        self.assertIn('discord.com/oauth2/authorize', saved.get('invite_url') or '')
        self.assertEqual(probe_discord(self.layout).state, 'NEEDS_AUTHORIZATION')
        secrets = read_env_secret('discord')
        self.assertEqual(secrets.get('DISCORD_BOT_TOKEN'), 'x' * 40)
        inv = discord_invite_url(layout=self.layout)
        self.assertTrue(inv['ok'])

    def test_n8n_managed_config(self):
        save_n8n_config(url='http://127.0.0.1:5678', layout=self.layout, managed=True)
        with mock.patch(
            'expansion.capabilities.n8n_sidecar.n8n_endpoint_healthy',
            return_value=(False, 'down'),
        ):
            self.assertEqual(probe_n8n(self.layout).state, 'LIMITED')
        with mock.patch(
            'expansion.capabilities.n8n_sidecar.n8n_endpoint_healthy',
            return_value=(True, 'ok'),
        ):
            self.assertEqual(probe_n8n(self.layout).state, 'READY')

    def test_configure_n8n_uses_sidecar(self):
        save_n8n_config(url='http://127.0.0.1:5678', layout=self.layout, managed=True)
        with mock.patch(
            'expansion.capabilities.n8n_sidecar.ensure_n8n_sidecar',
            return_value={'ok': True, 'action': 'started', 'endpoint': 'http://127.0.0.1:5678'},
        ), mock.patch(
            'expansion.capabilities.n8n_sidecar.n8n_endpoint_healthy',
            return_value=(True, 'ok'),
        ):
            out = configure_integration('n8n', layout=self.layout)
        self.assertTrue(out['ok'])
        self.assertEqual(out['component'], 'n8n')
        self.assertTrue(any(c['id'] == 'health' and c['done'] for c in out['checklist']))


if __name__ == '__main__':
    unittest.main()
