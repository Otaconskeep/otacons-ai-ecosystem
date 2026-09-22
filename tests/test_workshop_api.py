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
        self.assertIn('CREATIVE', html.upper())
        self.assertIn('data-telem-endpoint="/video-studio/api/telemetry"', html)
        self.assertNotIn('data-telem-endpoint="/api/executor/telemetry"', html)

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

    def test_job_output_uses_send_bytes_for_png(self):
        """Regression: output must be image/png bytes, never JSON, when send_bytes is wired."""
        with TemporaryDirectory() as td:
            root = Path(td)
            outdir = root / 'comfy_out'
            outdir.mkdir()
            png = outdir / 'burger.png'
            png.write_bytes(b'\x89PNG\r\n\x1a\n' + b'\x00' * 24)
            with mock.patch.dict(os.environ, {
                'OTACON_EXPANSION_DATA_ROOT': str(root / 'data'),
                'OTACON_EXPANSION_CONFIG_ROOT': str(root / 'cfg'),
                'COMFYUI_OUTPUT_DIR': str(outdir),
            }):
                from expansion.state_layout import resolve_layout
                layout = resolve_layout()
                layout.ensure_user_dirs()
                wa._upsert_job({
                    'id': 'img1',
                    'type': 'image_v1',
                    'job_type': 'image_v1',
                    'status': 'completed',
                    'outputs': ['burger.png'],
                    'output_file': 'burger.png',
                    'endpoint': 'http://127.0.0.1:8188',
                    'created_at': 1.0,
                    'created_ts': 1.0,
                }, layout)
                got = {}

                def send_json(data, status=200):
                    got['json'] = data
                    got['status'] = status

                def send_bytes(data, content_type='application/octet-stream', filename=''):
                    got['bytes'] = data
                    got['ctype'] = content_type
                    got['filename'] = filename

                with mock.patch.object(wa, 'resolve_layout', return_value=layout):
                    ok = wa.handle_workshop_get(
                        '/video-studio/api/generate-image-v1/img1/output',
                        send_json,
                        send_redirect=None,
                        send_bytes=send_bytes,
                    )
                self.assertTrue(ok)
                self.assertNotIn('json', got)
                self.assertEqual(got.get('ctype'), 'image/png')
                self.assertTrue(got.get('bytes', b'').startswith(b'\x89PNG'))

                # Without send_bytes → explicit 500, not a fake ok JSON body.
                got2 = {}
                def send_json2(data, status=200):
                    got2['json'] = data
                    got2['status'] = status
                with mock.patch.object(wa, 'resolve_layout', return_value=layout):
                    ok2 = wa.handle_workshop_get(
                        '/video-studio/api/jobs/img1/output',
                        send_json2,
                        send_redirect=None,
                        send_bytes=None,
                    )
                self.assertTrue(ok2)
                self.assertEqual(got2.get('status'), 500)
                self.assertEqual(got2['json'].get('error'), 'byte_sender_missing')

    def test_health_ready_when_comfy_ok_even_if_studio_not_ready_label(self):
        """Image-only boxes: health must not stay ready:false when Comfy+Z-Image work."""
        vs = mock.Mock(state='NOT_CONFIGURED', discovery={'endpoint': ''})
        with mock.patch('expansion.capabilities.video_studio.probe_video_studio', return_value=vs), \
             mock.patch('expansion.capabilities.studio_setup.studio_hardware_snapshot', return_value={
                 'cuda_available': True, 'gpu_model': 'RTX 3070', 'vram_gb': 8,
             }), \
             mock.patch('expansion.capabilities.comfy_submit._studio_endpoint', return_value='http://127.0.0.1:8188'), \
             mock.patch('expansion.capabilities.video_studio.comfy_endpoint_healthy', return_value=(True, 'ok')), \
             mock.patch('expansion.capabilities.comfy_submit.image_workflow_status', return_value={
                 'ok': True, 'unet': 'z.safetensors',
             }), \
             mock.patch('expansion.capabilities.studio_packs.packs_status', return_value={
                 'image_ready': True,
                 'packs': {'z_image': {'ok': True}, 'wan': {'ok': False}, 'ace_step': {'ok': False}},
             }), \
             mock.patch('expansion.capabilities.comfy_submit.music_workflow_status', return_value={
                 'ok': False,
                 'missing': ['checkpoints/ace_step_1.5_turbo_aio.safetensors'],
             }):
            h = wa._health()
        self.assertTrue(h['studio_ready'])
        self.assertTrue(h['image_ready'])
        self.assertTrue(h['generation_ready'])
        self.assertTrue(h['ready'])
        self.assertEqual(h['endpoint'], 'http://127.0.0.1:8188')
        self.assertEqual(h['preferred_mode'], 'image')
        self.assertFalse(h['music_ready'])
        self.assertFalse(h['video_ready'])
        self.assertFalse(h['projects_ready'])

    def test_generate_portrait_queues_image_job(self):
        with TemporaryDirectory() as td:
            with mock.patch.dict(os.environ, {
                'OTACON_EXPANSION_DATA_ROOT': str(Path(td) / 'data'),
                'OTACON_EXPANSION_CONFIG_ROOT': str(Path(td) / 'cfg'),
            }):
                from expansion.state_layout import resolve_layout
                layout = resolve_layout()
                layout.ensure_user_dirs()
                actors = [{
                    'id': 'act1',
                    'name': 'Nova',
                    'description': 'silver hair, teal jacket',
                    'images': {},
                    'ref_slots': {},
                }]
                wa._save_list(wa._actors_path(layout), actors)
                got = {}

                def send(data, status=200):
                    got['data'] = data
                    got['status'] = status

                with mock.patch.object(wa, 'resolve_layout', return_value=layout), \
                     mock.patch.object(wa, '_create_image_job', return_value={
                         'id': 'pjob1',
                         'status': 'running',
                         'error': '',
                     }):
                    ok = wa.handle_workshop_write(
                        'POST',
                        '/video-studio/api/actors/act1/generate-portrait',
                        {'agent_id': 'muse'},
                        send,
                    )
                self.assertTrue(ok)
                self.assertEqual(got.get('status'), 200)
                self.assertTrue(got['data'].get('ok'))
                self.assertEqual(got['data'].get('job_id'), 'pjob1')
                saved = wa._load_list(wa._actors_path(layout))
                self.assertEqual(saved[0].get('portrait_job_id'), 'pjob1')
                self.assertEqual(saved[0].get('portrait_status'), 'generating')

    def test_cancel_running_job_interrupts_comfy(self):
        with TemporaryDirectory() as td:
            with mock.patch.dict(os.environ, {
                'OTACON_EXPANSION_DATA_ROOT': str(Path(td) / 'data'),
                'OTACON_EXPANSION_CONFIG_ROOT': str(Path(td) / 'cfg'),
            }):
                from expansion.state_layout import resolve_layout
                layout = resolve_layout()
                layout.ensure_user_dirs()
                job = {
                    'id': 'run1',
                    'type': 'image_v1',
                    'job_type': 'image_v1',
                    'status': 'running',
                    'prompt_id': 'pid-run',
                    'endpoint': 'http://127.0.0.1:8188',
                    'created_at': 1,
                }
                wa._save_jobs([job], layout)
                got = {}

                def send(data, status=200):
                    got['data'] = data
                    got['status'] = status

                with mock.patch.object(wa, 'resolve_layout', return_value=layout), \
                     mock.patch(
                         'expansion.capabilities.comfy_submit.cancel_comfy_prompt',
                         return_value={
                             'ok': True,
                             'gpu_stopped': True,
                             'queue_state': 'running',
                             'action': 'interrupt',
                         },
                     ):
                    ok = wa.handle_workshop_write(
                        'POST', '/video-studio/api/jobs/run1/cancel', {}, send,
                    )
                self.assertTrue(ok)
                self.assertEqual(got.get('status'), 200)
                self.assertTrue(got['data'].get('ok'))
                self.assertTrue(got['data'].get('gpu_stopped'))
                saved = wa._get_job('run1', layout)
                self.assertEqual(saved.get('status'), 'cancelled')

    def test_cancel_completed_job_refuses(self):
        with TemporaryDirectory() as td:
            with mock.patch.dict(os.environ, {
                'OTACON_EXPANSION_DATA_ROOT': str(Path(td) / 'data'),
                'OTACON_EXPANSION_CONFIG_ROOT': str(Path(td) / 'cfg'),
            }):
                from expansion.state_layout import resolve_layout
                layout = resolve_layout()
                layout.ensure_user_dirs()
                wa._save_jobs([{
                    'id': 'done1', 'status': 'completed', 'prompt_id': 'x', 'created_at': 1,
                }], layout)
                got = {}

                def send(data, status=200):
                    got['data'] = data
                    got['status'] = status

                with mock.patch.object(wa, 'resolve_layout', return_value=layout):
                    ok = wa.handle_workshop_write(
                        'DELETE', '/video-studio/api/jobs/done1', {}, send,
                    )
                self.assertTrue(ok)
                self.assertEqual(got.get('status'), 409)
                self.assertEqual(got['data'].get('error'), 'already_finished')

    def test_vendored_page_has_no_requesting_agent(self):
        html = (
            Path(__file__).resolve().parents[1] / 'ui' / 'video-studio' / 'index.html'
        ).read_text(encoding='utf-8')
        self.assertNotIn('Requesting agent', html)
        self.assertNotIn('value="albedo"', html)
        self.assertNotIn('value="otacon"', html)
        self.assertIn('jobs/${jobId}/cancel', html)
        self.assertIn('VS_WORKSHOP_CLIENT', html)
        self.assertIn('jobs_ahead', html)
        self.assertIn('install-packs', html)

    def test_generate_music_queues_when_submitter_ok(self):
        with TemporaryDirectory() as td:
            with mock.patch.dict(os.environ, {
                'OTACON_EXPANSION_DATA_ROOT': str(Path(td) / 'data'),
                'OTACON_EXPANSION_CONFIG_ROOT': str(Path(td) / 'cfg'),
            }):
                from expansion.state_layout import resolve_layout
                layout = resolve_layout()
                layout.ensure_user_dirs()
                got = {}

                def send(data, status=200):
                    got['data'] = data
                    got['status'] = status

                with mock.patch.object(wa, 'resolve_layout', return_value=layout), \
                     mock.patch.object(wa, '_create_music_job', return_value={
                         'id': 'm1', 'status': 'queued', 'prompt_id': 'mpid', 'error': '',
                     }):
                    ok = wa.handle_workshop_write(
                        'POST', '/video-studio/api/generate-music-v1',
                        {'tags': 'warm pads', 'duration': 30},
                        send,
                    )
                self.assertTrue(ok)
                self.assertEqual(got.get('status'), 200)
                self.assertTrue(got['data'].get('ok'))
                self.assertEqual(got['data'].get('job_id'), 'm1')


if __name__ == '__main__':
    unittest.main()
