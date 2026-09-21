"""Home Assistant managed Docker sidecar unit tests."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock
import urllib.error

from expansion.capabilities.home_assistant_sidecar import (
    DEFAULT_ENDPOINT,
    ensure_home_assistant_sidecar,
    ha_endpoint_healthy,
)
from expansion.state_layout import resolve_layout


class HomeAssistantSidecarTests(unittest.TestCase):
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
            'OTACON_HA_URL': '',
            'OTACON_HA_TOKEN': '',
        }
        self._env_patch = mock.patch.dict('os.environ', env, clear=False)
        self._env_patch.start()
        self.layout = resolve_layout()
        self.layout.ensure_user_dirs()

    def tearDown(self):
        self._env_patch.stop()
        self.tmp.cleanup()

    def test_already_running_registers_url(self):
        with mock.patch(
            'expansion.capabilities.home_assistant_sidecar.ha_endpoint_healthy',
            return_value=(True, 'HTTP 200'),
        ):
            out = ensure_home_assistant_sidecar(layout=self.layout, wait_sec=1)
        self.assertTrue(out['ok'])
        self.assertEqual(out['action'], 'already_running')
        self.assertEqual(out['endpoint'], DEFAULT_ENDPOINT)
        self.assertEqual(out['user_action'], 'onboard_token')
        cfg = (self.layout.user_preferences / 'home_assistant.json').read_text(encoding='utf-8')
        self.assertIn('127.0.0.1:8123', cfg)

    def test_docker_missing_is_honest(self):
        with mock.patch(
            'expansion.capabilities.home_assistant_sidecar.ha_endpoint_healthy',
            return_value=(False, 'down'),
        ):
            with mock.patch(
                'expansion.capabilities.comfy_sidecar.probe_docker_engine',
                return_value={'ok': False, 'detail': 'no docker', 'status': 'missing'},
            ):
                out = ensure_home_assistant_sidecar(layout=self.layout, wait_sec=1)
        self.assertFalse(out['ok'])
        self.assertEqual(out['action'], 'docker_missing')

    def test_ha_endpoint_healthy_accepts_auth_wall(self):
        with mock.patch(
            'expansion.capabilities.home_assistant_sidecar.urllib.request.urlopen',
            side_effect=urllib.error.HTTPError(
                DEFAULT_ENDPOINT + '/', 401, 'Unauthorized', hdrs=None, fp=None,
            ),
        ):
            ok, detail = ha_endpoint_healthy(timeout=0.5)
        self.assertTrue(ok)
        self.assertIn('401', detail)


if __name__ == '__main__':
    unittest.main()
