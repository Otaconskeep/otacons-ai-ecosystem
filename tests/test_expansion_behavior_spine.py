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

    def test_praise_not_work_mode(self):
        from expansion.behavior_spine import classify_delivery_mode
        # Central failure Crist reported: praise recognized but WORK still injected
        for msg in (
            'thank you, that was brilliant',
            'great work on the plan',
            'nice work',
            'good job on the research',
        ):
            self.assertEqual(classify_delivery_mode(msg), 'praise', msg)
            self.assertFalse(wants_work_deliverable(msg), msg)
            d = work_mode_directive(msg)
            self.assertIn('PRAISE', d, msg)
            self.assertNotIn('[WORK MODE', d, msg)

    def test_greeting_and_hostility_modes(self):
        from expansion.behavior_spine import classify_delivery_mode
        self.assertEqual(classify_delivery_mode('hey chris'), 'greeting')
        self.assertIn('GREETING', work_mode_directive('hi'))
        self.assertEqual(classify_delivery_mode('fuck you'), 'hostility')
        self.assertEqual(classify_delivery_mode("youre a bitch!"), 'hostility')
        self.assertEqual(classify_delivery_mode("im sorry"), 'apology')
        self.assertIn('HOSTILITY', work_mode_directive('you suck'))
        self.assertIn('HOSTILITY', work_mode_directive("youre a bitch!"))
        self.assertFalse(wants_work_deliverable('fuck you'))

    def test_scrub_plan_restatement_on_praise(self):
        from expansion.behavior_spine import scrub_plan_restatement
        raw = (
            'I appreciate the honesty, Chris. Let\'s get back on track with your '
            'shirt project. Here\'s what we\'ll do next: 1. **Clarify the design '
            'concepts** 2. **Research fabric blends** 3. **Update inventory**'
        )
        out = scrub_robotic_delivery(raw, user_message='great work on the plan')
        self.assertNotRegex(out, r'(?i)here\'?s what we')
        self.assertNotRegex(out, r'(?i)1\.\s+\*?Clarify')
        self.assertNotRegex(out, r'(?i)get back on track')
        self.assertIn('appreciate', out.lower())
        # WORK mode keeps the plan
        kept = scrub_plan_restatement(raw, delivery_mode='work')
        self.assertIn('1.', kept)

    def test_scrub_fake_teammate_starts(self):
        raw = (
            'Chris, Vector will compile platform fees. '
            'Muse is currently analyzing competitor strategies. '
            'Ledger has already begun researching fabrics.'
        )
        out = scrub_robotic_delivery(raw)
        self.assertNotRegex(out, r'(?i)vector will compile')
        self.assertNotRegex(out, r'(?i)muse is currently analyzing')
        self.assertNotRegex(out, r'(?i)ledger has already begun')
        # Surviving stem should still be addressable
        self.assertTrue(out.startswith('Chris') or 'Chris' in out or out == '')

    def test_social_and_execute(self):
        self.assertTrue(is_social_or_affect_turn('what do you feel?'))
        self.assertTrue(is_social_or_affect_turn('lets talk about your day'))
        self.assertTrue(is_execute_imperative('do it'))
        self.assertTrue(is_execute_imperative('go ahead'))
        self.assertFalse(is_execute_imperative('do it later with the fabric plan'))

    def test_social_near_miss_regex_gaps(self):
        from expansion.behavior_spine import (
            is_day_or_conversation_invite,
            is_feeling_query_only,
        )
        # Near-misses that previously fell through to WORK lock-in
        for msg in (
            'are you doing okay?',
            'you doing alright?',
            'whats on your mind',
            'tell me something about yourself',
        ):
            self.assertTrue(is_social_or_affect_turn(msg), msg)
            self.assertFalse(wants_work_deliverable(msg), msg)
        self.assertTrue(is_day_or_conversation_invite('lets talk about your day'))
        self.assertTrue(is_day_or_conversation_invite('whats on your mind'))
        self.assertFalse(is_feeling_query_only('lets talk about your day'))
        self.assertTrue(is_feeling_query_only('what do you feel?'))
        self.assertTrue(is_feeling_query_only('are you doing okay?'))
        social = work_mode_directive('are you doing okay?')
        self.assertIn('SOCIAL', social)
        invite = work_mode_directive('lets talk about your day')
        self.assertIn('invited conversation', invite)

    def test_work_mode_injects(self):
        d = work_mode_directive('I want you to research and build me a plan')
        self.assertIn('WORK MODE', d)
        self.assertIn('numbered steps', d)
        self.assertIn('GREETING', work_mode_directive('hi'))
        social = work_mode_directive('lets talk about your day\nwhat do you feel?')
        self.assertIn('SOCIAL', social)
        self.assertNotIn('[WORK MODE', social)
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
