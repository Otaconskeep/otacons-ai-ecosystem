# -*- coding: utf-8 -*-
"""Tests for Keep-parity behavior spine (public Expansion)."""
from __future__ import annotations

import unittest

from expansion.behavior_spine import (
    delivery_rules_block,
    is_greeting_only,
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

    def test_work_mode_injects(self):
        d = work_mode_directive('I want you to research and build me a plan')
        self.assertIn('WORK MODE', d)
        self.assertIn('numbered steps', d)
        self.assertEqual(work_mode_directive('hi'), '')

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

    def test_delivery_and_layered(self):
        self.assertIn('DELIVERY RULES', delivery_rules_block(agent_id='aria'))
        block = layered_intelligence_block(
            emotion_summary="{'trust': 0.4}",
            learn_lines=['- name=chris', '- craft=laser'],
            journal_lines=['- started shirt plan'],
        )
        self.assertIn('LAYERED INTELLIGENCE', block)
        self.assertIn('chris', block)


if __name__ == '__main__':
    unittest.main()
