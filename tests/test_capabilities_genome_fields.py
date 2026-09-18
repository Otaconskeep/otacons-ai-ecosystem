"""Capabilities must expose Genome discovery fields the deck UI reads."""
from __future__ import annotations

import unittest

from expansion.capabilities import CapabilityReport, CapabilityState
from installer import server as srv


class CapabilitiesGenomeFieldsTests(unittest.TestCase):
    def test_voice_trainer_discovery_copied_into_capabilities(self):
        report = CapabilityReport(
            capability_id='voice_trainer',
            owner_agent='muse',
            state=CapabilityState.READY.value,
            detail='Genome Voice Trainer READY',
            discovery={
                'path': '/home/crist/otacon-voice-trainer',
                'listening': True,
                'verified': True,
                'port': 8765,
                'url': 'http://127.0.0.1:8765/',
                'gpu': True,
                'gpu_name': 'NVIDIA GeForce RTX 3070 Laptop GPU',
                'gpu_vram_mb': 8192,
                'docker_image': 'piper-voice-trainer:gpu',
                'status': {
                    'ok': True,
                    'gpu': True,
                    'gpu_name': 'NVIDIA GeForce RTX 3070 Laptop GPU',
                    'gpu_vram_mb': 8192,
                    'image': 'piper-voice-trainer:gpu',
                },
            },
        )
        caps = srv._voice_trainer_capability_fields(report)
        self.assertEqual(caps.get('voice_trainer'), 'ready')
        self.assertTrue(caps.get('voice_trainer_gpu'))
        disc = caps.get('voice_trainer_discovery') or {}
        self.assertTrue(disc.get('gpu'))
        self.assertEqual(disc.get('url'), 'http://127.0.0.1:8765/')
        self.assertEqual(disc.get('port'), 8765)
        self.assertIn('3070', disc.get('gpu_name') or '')

    def test_genome_is_spa_route(self):
        self.assertTrue(srv.Handler._is_expansion_spa_route('/genome'))
        self.assertTrue(srv.Handler._is_expansion_spa_route('/voice-trainer'))
        self.assertFalse(srv.Handler._is_expansion_spa_route('/api/capabilities'))


if __name__ == '__main__':
    unittest.main()
