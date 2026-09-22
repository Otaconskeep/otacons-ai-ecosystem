# -*- coding: utf-8 -*-
"""Tests for Hermes + Formula 4/5/7/8/9 layered intelligence (public Expansion)."""
from __future__ import annotations

import os
import tempfile
import time
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
        cat = formula_catalog()
        for key in ('formula_4', 'formula_5', 'formula_7', 'formula_8', 'formula_9'):
            self.assertIn(key, cat)

    def test_praise_raises_happiness_via_state_engine(self):
        from expansion.continuity.conversational_affect import apply_user_message_events
        from expansion.continuity.emotion_bridge import get_emotion_vector

        before = get_emotion_vector('aria')
        result = apply_user_message_events(
            'aria', 'you are amazing, great work', force=True,
        )
        self.assertTrue(result['ok'])
        self.assertTrue(result['applied'])
        after = get_emotion_vector('aria')
        self.assertGreaterEqual(after['happiness'], before['happiness'])
        self.assertGreater(after['happiness'], 0.50)

    def test_hostile_classifier_and_drop(self):
        from expansion.continuity.conversational_affect import (
            apply_user_message_events,
            classify_interpersonal_events,
        )
        from expansion.continuity.emotion_bridge import get_emotion_vector

        self.assertTrue(classify_interpersonal_events('this is garbage and you failed'))
        before = get_emotion_vector('aria')
        apply_user_message_events(
            'aria', 'this is garbage and you failed', force=True,
        )
        after = get_emotion_vector('aria')
        self.assertLessEqual(after['happiness'], before['happiness'])

    def test_dedupe_blocks_double_apply(self):
        from expansion.continuity.conversational_affect import apply_user_message_events
        from expansion.continuity.emotion_bridge import get_emotion_vector

        apply_user_message_events('aria', 'you suck at this', force=True)
        mid = get_emotion_vector('aria')['happiness']
        # Same message without force within TTL — should not drop further
        r2 = apply_user_message_events('aria', 'you suck at this')
        self.assertEqual(r2.get('reason'), 'deduped_same_turn')
        after = get_emotion_vector('aria')['happiness']
        self.assertAlmostEqual(mid, after, places=3)

    def test_formula5_relationship_engine(self):
        from expansion.continuity.relationship import RelationshipEngine, apply_formula5

        self.assertAlmostEqual(apply_formula5(0.80, 0.0), 0.80 - 0.008 * (0.80 - 0.50), places=3)
        RelationshipEngine.ensure_seeded()
        before = RelationshipEngine.strength('aria', 'user_primary', 'ally')
        RelationshipEngine.update_on_event('aria', 'user_primary', 'user_praise')
        after = RelationshipEngine.strength('aria', 'user_primary', 'ally')
        self.assertGreater(after, before)
        level = RelationshipEngine.operator_rel_level('aria')
        self.assertIn(level, ('familiar', 'reserved', 'neutral'))
        summary = RelationshipEngine.relationship_summary_for_prompt('aria')
        self.assertNotIn('albedo', summary.lower())
        self.assertNotIn('192.168', summary)

    def test_formula9_memory_scoring(self):
        from expansion.continuity.memory_engine import (
            MemoryEngine,
            score_memory_entry,
            score_and_rank,
        )

        MemoryEngine.write_reflection(
            'aria', trigger='test', note='Built a research plan about routers.',
            emotional_weight='positive',
        )
        MemoryEngine.write_reflection(
            'aria', trigger='test', note='Unrelated weather chat.',
            emotional_weight='neutral',
        )
        rows = MemoryEngine.retrieve_relevant_memory(
            'aria', 'research plan routers', top_k=2,
        )
        self.assertTrue(rows)
        self.assertIn('research', (rows[0].get('note') or '').lower())
        s = score_memory_entry(
            {'note': 'research plan', 'sentiment': 'positive', 'id': 'a'},
            ['research', 'plan'], 'aria', 0, set(),
        )
        self.assertGreater(s, 0.3)
        ranked = score_and_rank(
            [
                {'note': 'research plan', 'sentiment': 'positive', 'id': 'a'},
                {'note': 'cats', 'sentiment': 'neutral', 'id': 'b'},
            ],
            ['research'], 'aria', top_k=1,
        )
        self.assertEqual(ranked[0]['id'], 'a')

    def test_state_engine_formulas(self):
        from expansion.continuity.state_engine import StateEngine

        s1 = StateEngine.get('aria')
        s2 = StateEngine.update_from_event('aria', 'user_praise')
        self.assertGreaterEqual(s2['happiness'], s1['happiness'])
        self.assertIn(s2['mood'], {
            'cheerful', 'pleased', 'focused', 'neutral', 'brooding',
            'anxious', 'volatile', 'detached',
        })
        line = StateEngine.summary_for_prompt('aria')
        self.assertIn('[State]', line)

    def test_hermes_packet_includes_formulas(self):
        from expansion.hermes.personality_runtime import (
            apply_final_persona_safety_scrub,
            build_personality_runtime_packet,
            classify_persona_intent,
            layered_system_prompt_section,
            render_persona_text_via_hermes,
        )
        self.assertEqual(classify_persona_intent('hi'), 'greeting')
        packet = build_personality_runtime_packet('aria', 'how do you feel?')
        self.assertEqual(packet['agent_id'], 'aria')
        self.assertTrue(packet['privacy']['no_private_keep_data'])
        keys = packet.get('formula_catalog_keys') or []
        for k in ('formula_4', 'formula_5', 'formula_7', 'formula_8', 'formula_9'):
            self.assertIn(k, keys)
        blob = str(packet).lower()
        self.assertNotIn('albedo', blob)
        self.assertNotIn('192.168', blob)
        self.assertIsNone(
            apply_final_persona_safety_scrub(
                'Greetings, Operator. How may I assist you today?',
                'aria', 'greeting',
            )
        )
        section = layered_system_prompt_section('aria', 'build a plan')
        self.assertIn('HERMES', section)
        rend = render_persona_text_via_hermes('aria', 'hi', candidate_text='')
        self.assertTrue(rend.get('ok'))
        self.assertTrue(rend.get('text'))


if __name__ == '__main__':
    unittest.main()
