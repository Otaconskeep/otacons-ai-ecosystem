# -*- coding: utf-8 -*-
"""Tests for Hermes + emotion bridge + conversational affect (public Expansion)."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path


class LayeredIntelligenceTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.mkdtemp()
        os.environ['OTACON_EXPANSION_CONFIG_ROOT'] = str(Path(self._td) / 'cfg')
        os.environ['OTACON_EXPANSION_DATA_ROOT'] = str(Path(self._td) / 'data')
        os.environ['HERMES_PERSONALITY_RUNTIME_ENABLED'] = 'true'

    def test_formula8_and_bridge(self):
        from expansion.continuity.emotion_bridge import (
            formula8_score,
            formula_catalog,
            get_emotion_vector,
            normalize_vector,
        )
        score = formula8_score(0.55, 0.55, 0.60, 0.0)
        self.assertGreater(score, 0.5)
        self.assertLess(score, 0.6)
        vec = normalize_vector({'happiness': 70, 'confidence': 55, 'energy': 60})
        self.assertEqual(vec['raw_scale_detected'], 'legacy_0_100')
        self.assertLessEqual(vec['happiness'], 1.0)
        live = get_emotion_vector('aria')
        self.assertIn(live['mood'], {
            'cheerful', 'pleased', 'focused', 'neutral', 'brooding',
            'anxious', 'volatile', 'detached',
        })
        self.assertIn('formula_8', formula_catalog())

    def test_conversational_affect_mutates(self):
        from expansion.continuity.conversational_affect import (
            apply_user_message_events,
            build_dual_affect_prompt_block,
        )
        from expansion.continuity.emotion_bridge import get_emotion_vector
        before = get_emotion_vector('aria')
        result = apply_user_message_events(
            'aria', 'you are being lazy and this is not a good job',
        )
        self.assertTrue(result['ok'])
        self.assertTrue(result['applied'])
        after = get_emotion_vector('aria')
        self.assertIsInstance(after['formula8_score'], float)
        block = build_dual_affect_prompt_block('aria')
        self.assertIn('LONG-TERM', block)
        self.assertIn('SHORT-TERM', block)
        # Hostile should not raise happiness
        self.assertLessEqual(after['happiness'], before['happiness'] + 0.05)

    def test_hermes_packet_and_scrub(self):
        from expansion.hermes.personality_runtime import (
            apply_final_persona_safety_scrub,
            build_personality_runtime_packet,
            classify_persona_intent,
            layered_system_prompt_section,
            render_persona_text_via_hermes,
        )
        self.assertEqual(classify_persona_intent('hi'), 'greeting')
        self.assertEqual(
            classify_persona_intent('research and build me a plan'),
            'work_request',
        )
        packet = build_personality_runtime_packet(
            'aria', 'how do you feel?',
        )
        self.assertEqual(packet['agent_id'], 'aria')
        self.assertTrue(packet['privacy']['no_private_keep_data'])
        self.assertNotIn('albedo', str(packet).lower())
        self.assertNotIn('192.168', str(packet))
        self.assertIsNone(
            apply_final_persona_safety_scrub(
                'Greetings, Operator. How may I assist you today?',
                'aria', 'greeting',
            )
        )
        ok = apply_final_persona_safety_scrub(
            'I am focused and ready to plan your shirt designs.',
            'aria', 'work_request',
        )
        self.assertIsNotNone(ok)
        section = layered_system_prompt_section('muse', 'help me design')
        self.assertIn('HERMES PERSONALITY RUNTIME', section)
        rendered = render_persona_text_via_hermes(
            'aria', 'hi', candidate_text='Hello there.',
        )
        self.assertTrue(rendered['ok'])
        self.assertTrue(rendered['text'])


if __name__ == '__main__':
    unittest.main()
