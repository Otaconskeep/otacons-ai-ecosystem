"""VRAM-first Studio hardware profile matrix regressions."""
from __future__ import annotations

import os
import unittest
from pathlib import Path

from core.hardware_profile import (
    classify_studio_profile,
    comfy_gpu_image_candidates,
    profile_asset_manifest,
    resolve_comfy_gpu_image,
)


class HardwareProfileMatrixTests(unittest.TestCase):
    def test_vram_under_6_disables_image_video(self):
        p = classify_studio_profile(
            vram_gb=4, ram_gb=32, free_disk_gb=200,
            gpu_model='GTX 1650', cuda_available=True,
        )
        self.assertFalse(p.image.enabled)
        self.assertFalse(p.video.enabled)
        self.assertIn(p.profile_id, ('DISABLED', 'LOW_VRAM'))

    def test_6gb_low_vram_zimage_quant(self):
        p = classify_studio_profile(
            vram_gb=6, ram_gb=32, free_disk_gb=200,
            gpu_model='NVIDIA GeForce RTX 2060', cuda_available=True,
        )
        self.assertTrue(p.image.enabled)
        self.assertEqual(p.image.tier, 'low_vram_quant')
        self.assertTrue(p.video.enabled)
        self.assertIn('quant', p.video.engine + p.video.tier)
        self.assertEqual(p.music.engine, 'ace-step-1.5')
        self.assertFalse(p.ltx2_eligible)

    def test_8gb_wan_not_ltx2(self):
        p = classify_studio_profile(
            vram_gb=8, ram_gb=32, free_disk_gb=200,
            gpu_model='NVIDIA GeForce RTX 3070', cuda_available=True,
        )
        self.assertEqual(p.profile_id, '8GB_FAST')
        self.assertEqual(p.video.engine, 'wan-2.2-5b')
        self.assertFalse(p.ltx2_eligible)
        self.assertEqual(p.image.tier, 'fp8_quant')

    def test_12gb_recommended_zimage(self):
        p = classify_studio_profile(
            vram_gb=12, ram_gb=32, free_disk_gb=200,
            gpu_model='NVIDIA GeForce RTX 3060', cuda_available=True,
        )
        self.assertEqual(p.profile_id, '12GB')
        self.assertEqual(p.image.tier, 'recommended')
        self.assertEqual(p.video.tier, 'high_quality')

    def test_24gb_warns_ltx2_below_official(self):
        p = classify_studio_profile(
            vram_gb=24, ram_gb=64, free_disk_gb=200,
            gpu_model='NVIDIA GeForce RTX 4090', cuda_available=True,
        )
        self.assertTrue(p.profile_id.startswith('24GB'))
        self.assertFalse(p.ltx2_eligible)
        self.assertTrue(any('LTX-2' in w or '32 GB' in w for w in p.warnings))
        self.assertEqual(p.music.tier, 'xl_lm4b')

    def test_32gb_ltx2_eligible(self):
        p = classify_studio_profile(
            vram_gb=32, ram_gb=64, free_disk_gb=200,
            gpu_model='NVIDIA GeForce RTX 5090', cuda_available=True,
        )
        self.assertEqual(p.profile_id, '32GB_LTX2')
        self.assertTrue(p.ltx2_eligible)
        self.assertEqual(p.video.engine, 'ltx-2')

    def test_ram_under_15_soft_under_spec_not_hard_brick(self):
        p = classify_studio_profile(
            vram_gb=12, ram_gb=8, free_disk_gb=200,
            gpu_model='RTX 3060', cuda_available=True,
        )
        self.assertEqual(p.ram_tier, 'below_minimum')
        self.assertFalse(p.auto_install_studio)
        self.assertTrue(p.under_spec)
        self.assertTrue(p.can_proceed_anyway)
        self.assertIn("I'm sorry", p.performance_disclaimer)
        # Do not force CPU solely because RAM is soft-under when CUDA+VRAM exist
        self.assertEqual(p.comfy_runtime, 'gpu')

    def test_ram_15_2_gib_treated_as_marketed_16(self):
        p = classify_studio_profile(
            vram_gb=15.9, ram_gb=15.2, free_disk_gb=200,
            gpu_model='NVIDIA GeForce RTX 5070 Ti', cuda_available=True,
        )
        self.assertEqual(p.ram_tier, 'minimum')
        self.assertTrue(p.auto_install_studio)
        self.assertFalse(p.under_spec)
        self.assertEqual(p.marketed_ram_gb, 16.0)
        self.assertEqual(p.marketed_vram_gb, 16.0)
        self.assertEqual(p.profile_id, '16GB_FAST')
        self.assertEqual(p.comfy_runtime, 'gpu')

    def test_no_fake_vram_or_crist_path(self):
        p = classify_studio_profile(
            vram_gb=10, ram_gb=32, free_disk_gb=100,
            gpu_model='NVIDIA GeForce RTX 3080', cuda_available=True,
        )
        blob = str(p.to_dict())
        self.assertNotIn('8192', blob)
        self.assertNotIn('/home/crist', blob)
        self.assertNotIn('RTX 3070', blob)  # must not invent a different SKU
        self.assertEqual(p.gpu_model, 'NVIDIA GeForce RTX 3080')
        self.assertEqual(p.vram_gb, 10.0)

    def test_asset_manifest_includes_ace_step(self):
        p = classify_studio_profile(
            vram_gb=16, ram_gb=32, free_disk_gb=200,
            gpu_model='RTX 4060 Ti', cuda_available=True,
        )
        assets = profile_asset_manifest(p)
        kinds = {a['kind'] for a in assets}
        self.assertEqual(kinds, {'image', 'video', 'music'})
        self.assertTrue(any(a['engine'] == 'ace-step-1.5' for a in assets))

    def test_prompts_present_for_keep_parity(self):
        p = classify_studio_profile(
            vram_gb=12, ram_gb=32, free_disk_gb=200,
            gpu_model='RTX 4070', cuda_available=True,
        )
        self.assertIn('positive', p.image.prompts)
        self.assertIn('positive', p.video.prompts)
        self.assertIn('positive', p.music.prompts)
        self.assertTrue(p.image.settings)
        self.assertTrue(p.video.settings)
        self.assertTrue(p.music.settings)

    def test_cuda_missing_disables_creative(self):
        p = classify_studio_profile(
            vram_gb=0, ram_gb=32, free_disk_gb=200,
            gpu_model='', cuda_available=False,
        )
        self.assertFalse(p.image.enabled)
        self.assertFalse(p.video.enabled)
        self.assertEqual(p.comfy_runtime, 'cpu')


class ComfyGpuImageTagTests(unittest.TestCase):
    """RTX 20–50 series must resolve to Hub-real tags (never bare :cu124)."""

    def tearDown(self):
        os.environ.pop('OTACON_COMFY_GPU_IMAGE', None)

    def test_never_emits_bare_cu124(self):
        for model in (
            'NVIDIA GeForce RTX 2060',
            'NVIDIA GeForce RTX 3070',
            'NVIDIA GeForce RTX 3080',
            'NVIDIA GeForce RTX 4060 Ti',
            'NVIDIA GeForce RTX 4090',
            'NVIDIA GeForce RTX 5070 Ti',
            'NVIDIA GeForce RTX 5090',
            '',
        ):
            for tag in comfy_gpu_image_candidates(model):
                self.assertFalse(
                    tag.endswith(':cu124'),
                    f'{model} candidate must not be bare cu124, got {tag}',
                )
            primary = resolve_comfy_gpu_image(model)
            self.assertFalse(primary.endswith(':cu124'))
            self.assertTrue(primary.startswith('yanwk/comfyui-boot:'))

    def test_rtx20_turing_cu126(self):
        self.assertEqual(resolve_comfy_gpu_image('RTX 2080 Ti'), 'yanwk/comfyui-boot:cu126-slim')
        cands = comfy_gpu_image_candidates('NVIDIA GeForce RTX 2060')
        self.assertEqual(cands[0], 'yanwk/comfyui-boot:cu126-slim')
        self.assertIn('yanwk/comfyui-boot:cu124-slim', cands)
        self.assertIn('yanwk/comfyui-boot:cu121', cands)

    def test_rtx30_ampere_cu126(self):
        self.assertEqual(resolve_comfy_gpu_image('RTX 3060'), 'yanwk/comfyui-boot:cu126-slim')
        self.assertEqual(resolve_comfy_gpu_image('RTX 3090'), 'yanwk/comfyui-boot:cu126-slim')

    def test_rtx40_ada_cu126(self):
        self.assertEqual(resolve_comfy_gpu_image('RTX 4070'), 'yanwk/comfyui-boot:cu126-slim')
        self.assertEqual(resolve_comfy_gpu_image('RTX 4090'), 'yanwk/comfyui-boot:cu126-slim')

    def test_rtx50_blackwell_cu130_not_cu126(self):
        # cu126 has no Blackwell sm_120 — must use cu130 family
        img = resolve_comfy_gpu_image('NVIDIA GeForce RTX 5070 Ti')
        self.assertEqual(img, 'yanwk/comfyui-boot:cu130-slim-v2')
        cands = comfy_gpu_image_candidates('RTX 5090')
        self.assertEqual(cands[0], 'yanwk/comfyui-boot:cu130-slim-v2')
        self.assertTrue(any('cu130' in c or 'cu128' in c for c in cands))
        self.assertFalse(any(c.endswith(':cu126-slim') for c in cands))

    def test_profile_embeds_gpu_image_when_gpu_runtime(self):
        p = classify_studio_profile(
            vram_gb=15.9, ram_gb=15.2, free_disk_gb=200,
            gpu_model='NVIDIA GeForce RTX 5070 Ti', cuda_available=True,
        )
        self.assertEqual(p.comfy_runtime, 'gpu')
        self.assertEqual(p.comfy_gpu_image, 'yanwk/comfyui-boot:cu130-slim-v2')
        self.assertEqual(p.gpu_generation, 'Blackwell')

    def test_dead_cu124_env_override_ignored(self):
        os.environ['OTACON_COMFY_GPU_IMAGE'] = 'yanwk/comfyui-boot:cu124'
        self.assertEqual(
            resolve_comfy_gpu_image('RTX 4070'),
            'yanwk/comfyui-boot:cu126-slim',
        )

    def test_compose_gpu_yml_default_not_bare_cu124(self):
        root = Path(__file__).resolve().parents[1]
        text = (root / 'deploy' / 'comfyui' / 'docker-compose.gpu.yml').read_text(encoding='utf-8')
        self.assertNotIn('yanwk/comfyui-boot:cu124\n', text)
        self.assertNotIn('yanwk/comfyui-boot:cu124"', text)
        self.assertNotIn(':-yanwk/comfyui-boot:cu124}', text)
        self.assertIn('OTACON_COMFY_GPU_IMAGE', text)


if __name__ == '__main__':
    unittest.main()
