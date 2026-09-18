"""Comfy submitter honesty + Z-Image graph builder."""
from __future__ import annotations

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from expansion.capabilities import comfy_submit as cs
from expansion.jobs import JobStatus, JobStore


class ComfySubmitTests(unittest.TestCase):
    def test_build_z_image_prompt_has_required_nodes(self):
        g = cs.build_z_image_prompt(positive='a lantern in rain', steps=8)
        self.assertEqual(g['28']['class_type'], 'UNETLoader')
        self.assertEqual(g['27']['inputs']['text'], 'a lantern in rain')
        self.assertEqual(g['3']['inputs']['steps'], 8)

    def test_submit_refuses_without_models(self):
        with mock.patch.object(cs, 'probe_video_studio') as pvs, \
             mock.patch.object(cs, 'image_workflow_status', return_value={
                 'ok': False,
                 'detail': 'missing models',
                 'missing': ['z_image'],
             }):
            pvs.return_value = mock.Mock(state='READY', discovery={'endpoint': 'http://127.0.0.1:8188'})
            out = cs.submit_image_job(prompt='test')
        self.assertFalse(out['ok'])
        self.assertFalse(out['queued'])
        self.assertTrue(out.get('soft_block'))
        self.assertEqual(out['error'], 'creative_packs_needed')
        self.assertEqual(out.get('action'), 'install_packs')
        self.assertEqual(out.get('http_status'), 409)

    def test_submit_requires_prompt_id_before_ok(self):
        with mock.patch.object(cs, 'probe_video_studio') as pvs, \
             mock.patch.object(cs, 'image_workflow_status', return_value={
                 'ok': True, 'unet': 'z.safetensors', 'clip': 'c.safetensors', 'vae': 'ae.safetensors',
             }), \
             mock.patch.object(cs, '_http_json', return_value=(200, {'prompt_id': 'abc-123'})):
            pvs.return_value = mock.Mock(state='READY', discovery={'endpoint': 'http://127.0.0.1:8188'})
            out = cs.submit_image_job(prompt='hero portrait')
        self.assertTrue(out['ok'])
        self.assertEqual(out['prompt_id'], 'abc-123')

    def test_fail_stale_fake_creative_jobs(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            with mock.patch.dict(os.environ, {
                'OTACON_EXPANSION_DATA_ROOT': str(root / 'data'),
                'OTACON_EXPANSION_CONFIG_ROOT': str(root / 'cfg'),
            }):
                from expansion.state_layout import resolve_layout
                layout = resolve_layout()
                layout.ensure_user_dirs()
                store = JobStore(layout=layout)
                fake = store.create('fake creative', domain='creative', assigned_agent='muse')
                store.transition(fake.job_id, JobStatus.RUNNING.value)
                real = store.create('real creative', domain='creative', assigned_agent='muse')
                store.transition(
                    real.job_id, JobStatus.RUNNING.value,
                    evidence=['comfy:prompt_id=keep-me'],
                )
                out = cs.fail_stale_fake_creative_jobs(layout=layout)
                self.assertEqual(out['marked_failed'], 1)
                self.assertEqual(store.get(fake.job_id).status, JobStatus.FAILED.value)
                self.assertEqual(store.get(real.job_id).status, JobStatus.RUNNING.value)

    def test_public_creative_job_exposes_output_urls(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            with mock.patch.dict(os.environ, {
                'OTACON_EXPANSION_DATA_ROOT': str(root / 'data'),
                'OTACON_EXPANSION_CONFIG_ROOT': str(root / 'cfg'),
            }):
                from expansion.state_layout import resolve_layout
                layout = resolve_layout()
                layout.ensure_user_dirs()
                store = JobStore(layout=layout)
                job = store.create('done creative', domain='creative', assigned_agent='muse')
                store.transition(
                    job.job_id, JobStatus.RUNNING.value,
                    evidence=[
                        'comfy:prompt_id=pid-1',
                        'comfy:endpoint=http://127.0.0.1:8188',
                    ],
                )
                store.transition(
                    job.job_id, JobStatus.COMPLETE.value,
                    result='ComfyUI outputs: otacon_muse00001.png',
                    evidence=[
                        'comfy:prompt_id=pid-1',
                        'comfy:endpoint=http://127.0.0.1:8188',
                        'comfy:output=otacon_muse00001.png',
                    ],
                )
                pub = cs.public_creative_job(store.get(job.job_id))
                self.assertEqual(pub['outputs'], ['otacon_muse00001.png'])
                self.assertEqual(
                    pub['preview_url'],
                    f'/api/expansion/creative/jobs/{job.job_id}/output',
                )
                self.assertNotIn('8188', pub['preview_url'])
                self.assertEqual(
                    pub['output_proxy'],
                    f'/api/expansion/creative/jobs/{job.job_id}/output',
                )

    def test_fetch_comfy_output_bytes_from_disk(self):
        with TemporaryDirectory() as td:
            outdir = Path(td) / 'output'
            outdir.mkdir()
            img = outdir / 'burger.png'
            img.write_bytes(b'\x89PNG\r\n\x1a\n' + b'\x00' * 16)
            with mock.patch.dict(os.environ, {'COMFYUI_OUTPUT_DIR': str(outdir)}):
                data, mime, name = cs.fetch_comfy_output_bytes(filename='burger.png')
            self.assertEqual(name, 'burger.png')
            self.assertEqual(mime, 'image/png')
            self.assertTrue(data.startswith(b'\x89PNG'))

    def test_submit_uses_healthy_comfy_even_if_studio_not_ready_label(self):
        with mock.patch.object(cs, 'probe_video_studio') as pvs, \
             mock.patch.object(cs, 'image_workflow_status', return_value={
                 'ok': True, 'unet': 'z.safetensors', 'clip': 'c.safetensors', 'vae': 'ae.safetensors',
             }), \
             mock.patch('expansion.capabilities.video_studio.comfy_endpoint_healthy', return_value=(True, '/system_stats → 200')), \
             mock.patch.object(cs, '_http_json', return_value=(200, {'prompt_id': 'pid-ok'})):
            pvs.return_value = mock.Mock(
                state='LIMITED',
                discovery={'endpoint': 'http://127.0.0.1:8188'},
            )
            out = cs.submit_image_job(prompt='a man eating a burger')
        self.assertTrue(out['ok'])
        self.assertEqual(out['prompt_id'], 'pid-ok')

    def test_migrate_stuck_creative_jobs(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            with mock.patch.dict(os.environ, {
                'OTACON_EXPANSION_DATA_ROOT': str(root / 'data'),
                'OTACON_EXPANSION_CONFIG_ROOT': str(root / 'cfg'),
            }):
                from expansion.state_layout import resolve_layout
                layout = resolve_layout()
                layout.ensure_user_dirs()
                store = JobStore(layout=layout)
                stuck = store.create('stuck', domain='creative', assigned_agent='muse')
                store.transition(stuck.job_id, JobStatus.RUNNING.value)
                with mock.patch.object(cs, 'poll_creative_jobs_once', return_value={'ok': True}):
                    out = cs.migrate_stuck_creative_jobs(layout=layout)
                self.assertEqual(out['marked_failed'], 1)
                self.assertEqual(store.get(stuck.job_id).status, JobStatus.FAILED.value)
                self.assertIn('Migrated stuck', store.get(stuck.job_id).error or '')


    def test_cancel_comfy_prompt_pending_deletes_queue(self):
        with mock.patch.object(cs, '_studio_endpoint', return_value='http://127.0.0.1:8188'), \
             mock.patch.object(cs, '_http_json') as http, \
             mock.patch.object(cs, '_history_outputs', return_value=[]):
            http.side_effect = [
                (200, {'queue_running': [], 'queue_pending': [[1, 'pid-p']]}),
                (200, {}),
            ]
            out = cs.cancel_comfy_prompt(prompt_id='pid-p')
        self.assertTrue(out['ok'])
        self.assertEqual(out['queue_state'], 'pending')
        self.assertTrue(out['gpu_stopped'])

    def test_cancel_comfy_prompt_running_interrupts(self):
        with mock.patch.object(cs, '_studio_endpoint', return_value='http://127.0.0.1:8188'), \
             mock.patch.object(cs, '_http_json') as http, \
             mock.patch.object(cs, '_history_outputs', return_value=[]):
            http.side_effect = [
                (200, {'queue_running': [[0, 'pid-r']], 'queue_pending': []}),
                (200, {}),  # interrupt
                (200, {}),  # queue delete best-effort
            ]
            out = cs.cancel_comfy_prompt(prompt_id='pid-r')
        self.assertTrue(out['ok'])
        self.assertEqual(out['queue_state'], 'running')
        self.assertEqual(out['action'], 'interrupt')


class ReleaseInfoTests(unittest.TestCase):
    def test_release_identity_keys(self):
        from expansion.release_info import release_identity
        info = release_identity()
        self.assertIn('release_pin', info)
        self.assertIn('repo_head', info)
        self.assertIn('detail', info)
        self.assertIn('feature pin', info['detail'].lower())


if __name__ == '__main__':
    unittest.main()
