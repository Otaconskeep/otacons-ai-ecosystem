"""Studio creative packs — soft-block + manifest seeding."""
from __future__ import annotations

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from expansion.capabilities import studio_packs as sp


class StudioPacksTests(unittest.TestCase):
    def test_seed_workflow_assets(self):
        out = sp.seed_workflow_assets()
        self.assertTrue(out['ok'])
        root = Path(out['dir'])
        for name in (
            'z_image_turbo_api.meta.json',
            'wan_2_2_5b_api.meta.json',
            'ace_step_1_5_api.meta.json',
        ):
            self.assertTrue((root / name).is_file(), name)

    def test_packs_status_soft_block_when_missing(self):
        with TemporaryDirectory() as td:
            root = Path(td) / 'models'
            root.mkdir()
            with mock.patch.object(sp, 'resolve_models_root', return_value=root), \
                 mock.patch.object(sp, 'discover_comfy_container_models_dir', return_value={'ok': False}), \
                 mock.patch.object(sp, '_live_pack_status', return_value=None), \
                 mock.patch.object(sp, '_profile_pack_specs', return_value=[{
                     'id': 'zimage',
                     'kind': 'image',
                     'label': 'Z-Image Turbo',
                     'engine': 'z-image-turbo',
                     'files': sp.ZIMAGE_FILES,
                     'disk_gb': 25,
                     'priority': 1,
                 }]), \
                 mock.patch.dict(os.environ, {
                     'OTACON_EXPANSION_DATA_ROOT': str(Path(td) / 'data'),
                     'OTACON_EXPANSION_CONFIG_ROOT': str(Path(td) / 'cfg'),
                 }):
                from expansion.state_layout import resolve_layout
                layout = resolve_layout()
                layout.ensure_user_dirs()
                st = sp.packs_status(layout=layout, hw={'image': {'enabled': True}}, endpoint=None)
            self.assertFalse(st['ok'])
            self.assertTrue(st['soft_block'])
            self.assertEqual(st['action'], 'install_packs')
            self.assertTrue('2060' in st['aria'] or 'Install' in st['aria'] or 'download' in st['aria'].lower())
            low = st['aria'].lower()
            self.assertNotIn('generate unavailable', low)
            self.assertFalse(low.startswith('not queued'))

    def test_soft_block_payload_shape(self):
        block = sp.soft_block_payload({
            'aria': 'Tap Install packs — Generate stays quiet until packs are ready.',
            'packs': {},
            'needed': ['zimage'],
        })
        self.assertTrue(block['soft_block'])
        self.assertEqual(block['error'], 'creative_packs_needed')
        self.assertEqual(block['http_status'], 409)
        self.assertFalse(block['queued'])

    def test_pack_files_status_detects_present(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            dest = root / 'diffusion_models' / 'z_image_turbo_bf16.safetensors'
            dest.parent.mkdir(parents=True)
            dest.write_bytes(b'x' * 1_000_001)
            tiny = {**sp.ZIMAGE_FILES[0], 'min_bytes': 1_000_000}
            st = sp._pack_files_status([tiny], root)
            self.assertTrue(st['ok'])
            st2 = sp._pack_files_status(sp.ZIMAGE_FILES, root)
            self.assertFalse(st2['ok'])
            self.assertTrue(any('qwen' in m for m in st2['missing']))



    def test_2060_gets_wan_not_ltx(self):
        hw = {
            'vram_gb': 6, 'marketed_vram_gb': 6, 'ltx2_eligible': False,
            'image': {'enabled': True, 'tier': 'low_vram_quant', 'engine': 'z-image-turbo',
                      'settings': {
                          'unet': 'z_image_turbo_int8_convrot.safetensors',
                          'clip': 'qwen_3_4b_fp8_mixed.safetensors',
                          'vae': 'ae.safetensors',
                      }},
            'video': {'enabled': True, 'tier': 'low_vram_quant', 'engine': 'wan-2.2-5b-quant'},
            'music': {'enabled': True, 'tier': '2b_turbo_dit_int8', 'engine': 'ace-step-1.5'},
        }
        specs = {s['id']: s for s in sp._profile_pack_specs(hw)}
        self.assertIn('zimage', specs)
        self.assertIn('wan', specs)
        self.assertNotIn('ltx2', specs)
        names = [f['name'] for f in specs['zimage']['files']]
        self.assertTrue(any('int8' in n for n in names))
        self.assertTrue(all(f.get('url', '').startswith('https://huggingface.co/') for f in specs['wan']['files']))

    def test_3090_gets_ltx2_not_wan(self):
        hw = {
            'vram_gb': 24, 'marketed_vram_gb': 24, 'ltx2_eligible': True,
            'image': {'enabled': True, 'tier': 'full', 'engine': 'z-image-turbo',
                      'settings': {
                          'unet': 'z_image_turbo_bf16.safetensors',
                          'clip': 'qwen_3_4b.safetensors',
                          'vae': 'ae.safetensors',
                      }},
            'video': {'enabled': True, 'tier': 'distilled_24gb', 'engine': 'ltx-2'},
            'music': {'enabled': True, 'tier': 'xl_lm4b', 'engine': 'ace-step-1.5'},
        }
        specs = {s['id']: s for s in sp._profile_pack_specs(hw)}
        self.assertIn('ltx2', specs)
        self.assertNotIn('wan', specs)
        self.assertEqual(specs['ltx2']['comfy_docs'], sp.COMFY_DOCS['ltx2'])

    def test_compose_prefixed_volume_candidates(self):
        names = sp._compose_volume_candidates()
        self.assertIn('otacon-comfy-data', names)
        self.assertIn('comfyui_otacon-comfy-data', names)

    def test_packs_status_trusts_live_comfy_over_empty_host(self):
        with TemporaryDirectory() as td:
            root = Path(td) / 'models'
            root.mkdir()
            with mock.patch.object(sp, 'resolve_models_root', return_value=root), \
                 mock.patch.object(sp, 'discover_comfy_container_models_dir', return_value={'ok': False}), \
                 mock.patch.object(sp, '_profile_pack_specs', return_value=[{
                     'id': 'zimage',
                     'kind': 'image',
                     'label': 'Z-Image',
                     'engine': 'z-image-turbo',
                     'files': sp.ZIMAGE_NVFP4,
                     'disk_gb': 8,
                     'priority': 1,
                 }]), \
                 mock.patch('expansion.capabilities.comfy_submit.image_workflow_status', return_value={
                     'ok': True,
                     'unet': 'z_image_turbo_nvfp4.safetensors',
                     'clip': 'qwen_3_4b_fp4_mixed.safetensors',
                     'vae': 'ae.safetensors',
                     'detail': 'live',
                     'missing': [],
                 }), \
                 mock.patch.dict(os.environ, {
                     'OTACON_EXPANSION_DATA_ROOT': str(Path(td) / 'data'),
                     'OTACON_EXPANSION_CONFIG_ROOT': str(Path(td) / 'cfg'),
                 }):
                from expansion.state_layout import resolve_layout
                layout = resolve_layout()
                layout.ensure_user_dirs()
                st = sp.packs_status(
                    layout=layout,
                    endpoint='http://127.0.0.1:8188',
                    hw={'image': {'enabled': True}},
                )
            self.assertTrue(st['image_ready'])
            self.assertTrue(st['packs']['zimage']['ok'])
            self.assertTrue(st['packs']['zimage']['live_comfy'])
            self.assertFalse(st['soft_block'])
            self.assertEqual(st['models_root_role'], 'host_staging_then_docker_cp')

    def test_ensure_auto_install_continues_after_zimage(self):
        """8 GB profiles must keep pulling wan/ace after Z-Image is ready."""
        with TemporaryDirectory() as td:
            calls = []

            def fake_start(**kwargs):
                calls.append(kwargs.get('which'))
                return {'started': True, 'running': True}

            status = {
                'ok': False,
                'image_ready': True,
                'needed': ['wan', 'ace_step'],
                'running': False,
                'soft_block': False,
            }
            with mock.patch.object(sp, 'packs_status', return_value=status), \
                 mock.patch.object(sp, 'start_pack_install', side_effect=fake_start), \
                 mock.patch.object(sp, 'load_packs_state', return_value={}), \
                 mock.patch.object(sp, 'save_packs_state'):
                out = sp.ensure_auto_install(
                    studio_ready=True,
                    hw={'marketed_vram_gb': 8, 'vram_gb': 8},
                )
            self.assertTrue(out.get('auto_started') or out.get('started'))
            self.assertEqual(calls, [['wan', 'ace_step']])

    def test_ensure_auto_install_image_only_under_6gb(self):
        calls = []

        def fake_start(**kwargs):
            calls.append(kwargs.get('which'))
            return {'started': True, 'running': True}

        status = {
            'ok': False,
            'image_ready': False,
            'needed': ['zimage', 'wan'],
            'running': False,
            'soft_block': True,
        }
        with mock.patch.object(sp, 'packs_status', return_value=status), \
             mock.patch.object(sp, 'start_pack_install', side_effect=fake_start), \
             mock.patch.object(sp, 'load_packs_state', return_value={}), \
             mock.patch.object(sp, 'save_packs_state'):
            sp.ensure_auto_install(
                studio_ready=True,
                hw={'marketed_vram_gb': 4, 'vram_gb': 4},
            )
        self.assertEqual(calls, [['zimage']])


if __name__ == '__main__':
    unittest.main()
