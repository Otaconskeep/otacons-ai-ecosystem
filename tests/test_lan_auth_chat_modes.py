#!/usr/bin/env python3
"""LAN auth vs local mode for /api/chat_with_agent + update mode preservation."""
from __future__ import annotations

import json
import os
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]


class ChatAuthModeTests(unittest.TestCase):
    def setUp(self):
        self._env = {k: v for k, v in os.environ.items() if k.startswith('OTACON_')}
        for k in list(os.environ):
            if k.startswith('OTACON_'):
                del os.environ[k]
        os.environ['OTACON_USE_TEST_LLM'] = '1'
        os.environ['OTACON_PORT'] = '0'
        self._tmpdir = tempfile.TemporaryDirectory()
        self._cfg = Path(self._tmpdir.name) / 'otacon'
        self._cfg.mkdir(parents=True)
        self._token_path = self._cfg / 'lan_token'

    def tearDown(self):
        for k in list(os.environ):
            if k.startswith('OTACON_'):
                del os.environ[k]
        os.environ.update(self._env)
        self._tmpdir.cleanup()

    def _start_server(self, lan: bool):
        if lan:
            os.environ['OTACON_LAN_MODE'] = '1'
            os.environ['OTACON_HOST'] = '127.0.0.1'
        else:
            os.environ['OTACON_LAN_MODE'] = '0'
            os.environ['OTACON_HOST'] = '0.0.0.0'

        import installer.security as sec
        import installer.server as srv

        # Point token file at temp config
        sec.CONFIG_ROOT = self._cfg
        sec.TOKEN_PATH = self._token_path

        srv.BIND_HOST, srv.BIND_MODE = sec.resolve_bind_host()
        if srv.BIND_MODE == 'lan':
            srv.LAN_TOKEN = sec.ensure_lan_token()
        else:
            srv.LAN_TOKEN = sec.load_lan_token()

        httpd = ThreadingHTTPServer(('127.0.0.1', 0), srv.Handler)
        port = httpd.server_address[1]
        t = threading.Thread(target=httpd.serve_forever, daemon=True)
        t.start()
        self.addCleanup(httpd.shutdown)
        return port, srv.LAN_TOKEN, srv.BIND_MODE

    def _post(self, port: int, path: str, body: dict, token: str | None = None):
        import urllib.request

        data = json.dumps(body).encode()
        req = urllib.request.Request(
            f'http://127.0.0.1:{port}{path}',
            data=data,
            method='POST',
            headers={'Content-Type': 'application/json'},
        )
        if token:
            req.add_header('Authorization', f'Bearer {token}')
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status, json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            payload = exc.read().decode()
            try:
                parsed = json.loads(payload)
            except Exception:
                parsed = {'raw': payload}
            return exc.code, parsed

    def test_local_mode_chat_without_token(self):
        port, _token, mode = self._start_server(lan=False)
        self.assertEqual(mode, 'local')
        status, data = self._post(
            port,
            '/api/chat_with_agent',
            {
                'agent': {'id': 'agent_001', 'display_name': 'Aria', 'voice_id': 'aria'},
                'message': 'hello',
            },
        )
        self.assertEqual(status, 200, data)
        self.assertTrue(data.get('text') or data.get('reply') or 'error' not in data or data.get('ok', True))

    def test_lan_mode_chat_without_token_401(self):
        port, token, mode = self._start_server(lan=True)
        self.assertEqual(mode, 'lan')
        self.assertTrue(token)
        status, data = self._post(
            port,
            '/api/chat_with_agent',
            {
                'agent': {'id': 'agent_001', 'display_name': 'Aria', 'voice_id': 'aria'},
                'message': 'hello',
            },
        )
        self.assertEqual(status, 401)
        self.assertEqual((data.get('error') or {}).get('code'), 'LAN_AUTH_REQUIRED')

    def test_lan_mode_chat_with_valid_token(self):
        port, token, mode = self._start_server(lan=True)
        self.assertEqual(mode, 'lan')
        status, data = self._post(
            port,
            '/api/chat_with_agent',
            {
                'agent': {'id': 'agent_001', 'display_name': 'Aria', 'voice_id': 'aria'},
                'message': 'hello',
            },
            token=token,
        )
        self.assertEqual(status, 200, data)

    def test_lan_mode_chat_with_invalid_token(self):
        port, _token, mode = self._start_server(lan=True)
        self.assertEqual(mode, 'lan')
        status, data = self._post(
            port,
            '/api/chat_with_agent',
            {
                'agent': {'id': 'agent_001', 'display_name': 'Aria', 'voice_id': 'aria'},
                'message': 'hello',
            },
            token='not-the-real-token',
        )
        self.assertEqual(status, 401)
        self.assertEqual((data.get('error') or {}).get('code'), 'LAN_AUTH_REQUIRED')


class UpdateNetworkModePreservationTests(unittest.TestCase):
    def test_repair_preserves_lan_mode_markers(self):
        repair = (ROOT / 'deploy' / 'repair-otacon-core.ps1').read_text(encoding='utf-8-sig')
        self.assertIn('NETWORK_MODE_PRESERVED', repair)
        self.assertIn('OTACON_LAN_MODE=${PRESERVE_LAN}', repair)
        self.assertIn('EXISTING_LAN', repair)
        # Must not force LAN=1
        self.assertNotRegex(repair, r'OTACON_LAN_MODE=1(?!\})')

    def test_repair_defaults_missing_mode_to_local(self):
        repair = (ROOT / 'deploy' / 'repair-otacon-core.ps1').read_text(encoding='utf-8-sig')
        self.assertIn('PRESERVE_LAN=0', repair)

    def test_fix_gpu_preserves_mode(self):
        fix = (ROOT / 'deploy' / 'fix-otacon-gpu.ps1').read_text(encoding='utf-8-sig')
        self.assertIn('NETWORK_MODE_PRESERVED', fix)
        self.assertIn('OTACON_LAN_MODE=${PRESERVE_LAN}', fix)

    def test_wizard_sends_authorization_and_handles_lan_auth(self):
        wiz = (ROOT / 'ui' / 'wizard.js').read_text(encoding='utf-8')
        self.assertIn("Authorization", wiz)
        self.assertIn('Bearer ', wiz)
        self.assertIn('LAN_AUTH_REQUIRED', wiz)
        self.assertIn('sessionStorage', wiz)
        self.assertIn('otacon_lan_token', wiz)
        self.assertIn('/api/auth/bootstrap', wiz)
        # Token must not be hardcoded
        self.assertNotRegex(wiz, r'Bearer [A-Za-z0-9_-]{20,}')

    def test_simulated_unit_rewrite_local_stays_local(self):
        """Existing local-only unit stays OTACON_LAN_MODE=0 after repair logic."""
        with tempfile.TemporaryDirectory() as td:
            unit = Path(td) / 'otacon.service'
            unit.write_text(
                '[Service]\n'
                'Environment=OTACON_HOST=127.0.0.1\n'
                'Environment=OTACON_LAN_MODE=0\n'
                'Environment=OTACON_PORT=5757\n',
                encoding='utf-8',
            )
            script = f'''
set -e
UNIT="{unit}"
EXISTING_LAN="$(sed -n 's/^Environment=OTACON_LAN_MODE=//p' "$UNIT" 2>/dev/null | tail -n1)"
case "$(echo "${{EXISTING_LAN:-0}}" | tr '[:upper:]' '[:lower:]')" in
  1|true|yes|lan) PRESERVE_LAN=1 ;;
  *) PRESERVE_LAN=0 ;;
esac
sed -i '/OTACON_LAN_MODE=/d' "$UNIT"
sed -i "/\\[Service\\]/a Environment=OTACON_LAN_MODE=${{PRESERVE_LAN}}" "$UNIT"
sed -i "s|^Environment=OTACON_HOST=.*|Environment=OTACON_HOST=0.0.0.0|" "$UNIT"
grep OTACON_LAN_MODE= "$UNIT"
grep OTACON_HOST= "$UNIT"
'''
            import subprocess
            out = subprocess.check_output(['bash', '-c', script], text=True)
            self.assertIn('OTACON_LAN_MODE=0', out)
            self.assertIn('OTACON_HOST=0.0.0.0', out)

    def test_simulated_unit_rewrite_lan_stays_lan(self):
        with tempfile.TemporaryDirectory() as td:
            unit = Path(td) / 'otacon.service'
            unit.write_text(
                '[Service]\n'
                'Environment=OTACON_HOST=0.0.0.0\n'
                'Environment=OTACON_LAN_MODE=1\n',
                encoding='utf-8',
            )
            script = f'''
set -e
UNIT="{unit}"
EXISTING_LAN="$(sed -n 's/^Environment=OTACON_LAN_MODE=//p' "$UNIT" 2>/dev/null | tail -n1)"
case "$(echo "${{EXISTING_LAN:-0}}" | tr '[:upper:]' '[:lower:]')" in
  1|true|yes|lan) PRESERVE_LAN=1 ;;
  *) PRESERVE_LAN=0 ;;
esac
sed -i '/OTACON_LAN_MODE=/d' "$UNIT"
sed -i "/\\[Service\\]/a Environment=OTACON_LAN_MODE=${{PRESERVE_LAN}}" "$UNIT"
grep OTACON_LAN_MODE= "$UNIT"
'''
            import subprocess
            out = subprocess.check_output(['bash', '-c', script], text=True)
            self.assertIn('OTACON_LAN_MODE=1', out)


if __name__ == '__main__':
    unittest.main()
