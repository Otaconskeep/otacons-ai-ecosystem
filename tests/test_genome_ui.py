"""Genome actionable UI — not a static instruction page."""
from __future__ import annotations

import json
import threading
import unittest
from unittest import mock
from urllib.request import Request, urlopen

from expansion.capabilities import genome_ui as gui


class GenomeUiTests(unittest.TestCase):
    def tearDown(self):
        srv = gui._SERVER
        if srv is not None:
            try:
                srv.shutdown()
            except Exception:
                pass
        gui._SERVER = None
        gui._SERVER_THREAD = None
        with gui._TRAIN_LOCK:
            gui._TRAIN_STATE.update({
                'status': 'idle', 'name': '', 'urls': [], 'pid': None,
                'started_at': 0.0, 'finished_at': 0.0, 'error': '', 'log': '',
            })

    def test_ui_serves_train_form_and_api(self):
        # Bind an ephemeral port via patching DEFAULT and ensure
        port = 18765
        with mock.patch.object(gui, 'port_listening', side_effect=[False, True, True]):
            # First call in ensure: not listening; after start: listening checks
            pass

        # Direct server on high port to avoid collisions
        from http.server import ThreadingHTTPServer
        server = ThreadingHTTPServer(('127.0.0.1', 0), gui._GenomeHandler)
        port = server.server_address[1]
        th = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': 0.2}, daemon=True)
        th.start()
        try:
            html = urlopen(f'http://127.0.0.1:{port}/', timeout=2).read().decode('utf-8')
            self.assertIn('Start training', html)
            self.assertIn('/api/train', html)
            self.assertNotIn('Voice Trainer ready.', html)

            st = json.loads(urlopen(f'http://127.0.0.1:{port}/api/train-status', timeout=2).read())
            self.assertEqual(st.get('status'), 'idle')

            req = Request(
                f'http://127.0.0.1:{port}/api/train',
                data=json.dumps({'name': 'bad', 'urls': []}).encode('utf-8'),
                headers={'Content-Type': 'application/json'},
                method='POST',
            )
            # Expect 400 — no urls
            try:
                urlopen(req, timeout=2)
                self.fail('expected HTTPError')
            except Exception as exc:
                self.assertIn('400', str(exc) or type(exc).__name__ or '')
        finally:
            server.shutdown()
            server.server_close()

    def test_start_train_requires_gpu_and_image(self):
        with mock.patch.object(gui, '_gpu_ok', return_value=False):
            out = gui.start_train_job(name='voice_a', urls=['https://youtu.be/x'])
        self.assertFalse(out['ok'])
        self.assertIn('GPU', out.get('error') or '')


if __name__ == '__main__':
    unittest.main()
