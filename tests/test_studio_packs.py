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
                st = sp.packs_status(layout=layout, hw={'image': {'enabled': True}})
            self.assertFalse(st['ok'])
            self.assertTrue(st['soft_block'])
            self.assertEqual(st['action'], 'install_packs')
            self.assertIn('Install packs', st['aria'])
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


if __name__ == '__main__':
    unittest.main()
