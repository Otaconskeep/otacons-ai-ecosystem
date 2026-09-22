# -*- coding: utf-8 -*-
"""Tests for Keep-parity behavior spine (public Expansion)."""
from __future__ import annotations

import unittest

from expansion.behavior_spine import (
    delivery_rules_block,
    is_execute_imperative,
    is_greeting_only,
    is_social_or_affect_turn,
    layered_intelligence_block,
    scrub_robotic_delivery,
    wants_work_deliverable,
    work_mode_directive,
)


class BehaviorSpineTests(unittest.TestCase):
    def test_greeting_only(self):
        self.assertTrue(is_greeting_only('hi'))
        self.assertTrue(is_greeting_only('Hello!'))
        self.assertFalse(is_greeting_only('hi I need a plan for shirts'))

    def test_work_detect(self):
        self.assertTrue(wants_work_deliverable(
            'help me with research and build me a plan for t shirt design'
        ))
        self.assertFalse(wants_work_deliverable('hi'))
        self.assertFalse(wants_work_deliverable('lets talk about your day\nwhat do you feel?'))
        self.assertTrue(wants_work_deliverable('do it'))

    def test_social_and_execute(self):
        self.assertTrue(is_social_or_affect_turn('what do you feel?'))
        self.assertTrue(is_social_or_affect_turn('lets talk about your day'))
        self.assertTrue(is_execute_imperative('do it'))
        self.assertTrue(is_execute_imperative('go ahead'))
        self.assertFalse(is_execute_imperative('do it later with the fabric plan'))

    def test_work_mode_injects(self):
        d = work_mode_directive('I want you to research and build me a plan')
        self.assertIn('WORK MODE', d)
        self.assertIn('numbered steps', d)
        self.assertEqual(work_mode_directive('hi'), '')
        social = work_mode_directive('lets talk about your day\nwhat do you feel?')
        self.assertIn('SOCIAL', social)
        self.assertNotIn('WORK MODE', social)
        exe = work_mode_directive('do it')
        self.assertIn('EXECUTE', exe)

    def test_scrub_robotic(self):
        raw = (
            'Greetings, Chris. How may I assist you today? '
            'Your skills matter in this Keep.'
        )
        out = scrub_robotic_delivery(raw)
        self.assertNotRegex(out, r'(?i)^greetings')
        self.assertNotRegex(out, r'(?i)how may i assist you today')
        self.assertIn('household', out.lower())
        self.assertTrue(out.lower().startswith('your skills') or 'skills' in out.lower())

    def test_scrub_name_meta(self):
        raw = (
            'Chris, Ledger will research fabrics. Also, just a heads up—some users '
            'prefer being called by their actual names out of respect. '
            'How do you feel about that, Chris?'
        )
        out = scrub_robotic_delivery(raw)
        self.assertNotRegex(out, r'(?i)prefer being called')
        self.assertNotRegex(out, r'(?i)how do you feel about')
        self.assertIn('Ledger', out)

    def test_delivery_and_layered(self):
        block = delivery_rules_block(agent_id='aria')
        self.assertIn('DELIVERY RULES', block)
        self.assertIn('never lecture', block.lower())
        layered = layered_intelligence_block(
            emotion_summary="{'trust': 0.4}",
            learn_lines=['- name=chris', '- craft=laser'],
            journal_lines=['- started shirt plan'],
        )
        self.assertIn('LAYERED INTELLIGENCE', layered)
        self.assertIn('chris', layered)


if __name__ == '__main__':
    unittest.main()
