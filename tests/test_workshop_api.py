"""Keep Workshop API bridge — health, actors, image generate soft-path."""
from __future__ import annotations

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from expansion.capabilities import workshop_api as wa


class WorkshopApiTests(unittest.TestCase):
    def test_vendored_workshop_page_exists(self):
        root = Path(__file__).resolve().parents[1] / 'ui' / 'video-studio'
        self.assertTrue((root / 'index.html').is_file())
        self.assertTrue((root / 'static' / 'css' / 'video-studio-hud.css').is_file())
        self.assertTrue((root / 'static' / 'js' / 'video-studio-hud.js').is_file())
        html = (root / 'index.html').read_text(encoding='utf-8')
        self.assertIn('data-theme="video-studio"', html)
        self.assertIn('/video-studio/static/css/video-studio-hud.css', html)
        self.assertIn('THE WORKSHOP', html.upper())

    def test_health_and_actors(self):
        with TemporaryDirectory() as td:
            with mock.patch.dict(os.environ, {
                'OTACON_EXPANSION_DATA_ROOT': str(Path(td) / 'data'),
                'OTACON_EXPANSION_CONFIG_ROOT': str(Path(td) / 'cfg'),
            }):
                from expansion.state_layout import resolve_layout
                layout = resolve_layout()
                layout.ensure_user_dirs()
                with mock.patch.object(wa, 'resolve_layout', return_value=layout), \
                     mock.patch.object(wa, '_health', return_value={
                         'ready': True, 'cuda_available': True, 'gpu_name': 'RTX',
                         'vram_total_gb': 24, 'vram_free_gb': 12, 'backend': 'test',
                     }):
                    out = {}
                    def send(data, status=200):
                        out['data'] = data
                        out['status'] = status
                    self.assertTrue(wa.handle_workshop_get('/video-studio/api/health', send))
                    self.assertTrue(out['data']['ready'])
                    self.assertTrue(wa.handle_workshop_get('/video-studio/api/actors', send))
                    self.assertIsInstance(out['data'], list)

    def test_generate_image_uses_job_id(self):
        with TemporaryDirectory() as td:
            with mock.patch.dict(os.environ, {
                'OTACON_EXPANSION_DATA_ROOT': str(Path(td) / 'data'),
                'OTACON_EXPANSION_CONFIG_ROOT': str(Path(td) / 'cfg'),
            }):
                from expansion.state_layout import resolve_layout
                layout = resolve_layout()
                layout.ensure_user_dirs()
                with mock.patch.object(wa, 'resolve_layout', return_value=layout), \
                     mock.patch.object(wa, '_create_image_job', return_value={
                         'id': 'abc123', 'status': 'running', 'type': 'image_v1',
                     }):
                    out = {}
                    def send(data, status=200):
                        out['data'] = data
                        out['status'] = status
                    ok = wa.handle_workshop_write(
                        'POST', '/video-studio/api/generate-image-v1',
                        {'prompt': 'a lantern', 'width': '1024', 'height': '1024'},
                        send,
                    )
                    self.assertTrue(ok)
                    self.assertEqual(out['data']['job_id'], 'abc123')
                    self.assertTrue(out['data']['ok'])

    def test_multipart_parse(self):
        class H:
            headers = {
                'Content-Type': 'multipart/form-data; boundary=bound123',
                'Content-Length': '0',
            }
            class R:
                def read(self, n):
                    body = (
                        b'--bound123\r\n'
                        b'Content-Disposition: form-data; name="prompt"\r\n\r\n'
                        b'hello workshop\r\n'
                        b'--bound123\r\n'
                        b'Content-Disposition: form-data; name="width"\r\n\r\n'
                        b'1024\r\n'
                        b'--bound123--\r\n'
                    )
                    self._b = body
                    return body
            rfile = R()
        # Fix Content-Length
        raw = (
            b'--bound123\r\n'
            b'Content-Disposition: form-data; name="prompt"\r\n\r\n'
            b'hello workshop\r\n'
            b'--bound123\r\n'
            b'Content-Disposition: form-data; name="width"\r\n\r\n'
            b'1024\r\n'
            b'--bound123--\r\n'
        )
        H.headers['Content-Length'] = str(len(raw))
        H.rfile = type('R', (), {'read': lambda self, n: raw})()
        data = wa.parse_form_or_json(H())
        self.assertEqual(data.get('prompt'), 'hello workshop')
        self.assertEqual(data.get('width'), '1024')


if __name__ == '__main__':
    unittest.main()
