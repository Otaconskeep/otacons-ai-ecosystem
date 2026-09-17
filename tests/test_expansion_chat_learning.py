"""Chat-turn learning — Keep-parity classify → mutate → inject → write."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from expansion.bootstrap import bootstrap_runtime_state
from expansion.chat_learning import (
    after_reply,
    before_reply,
    classify_chat_intent,
    extract_remember_fact,
)
from expansion.emotion_store import EmotionStore
from expansion.learning import LearningEngine, PATTERN_THRESHOLD
from expansion.memory_bridge import ExpansionMemory
from expansion.runtime import ExpansionRuntime
from expansion.state_layout import resolve_layout


class ChatLearningCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        env = {
            'OTACON_EXPANSION_CONFIG_ROOT': str(self.root / 'cfg'),
            'OTACON_EXPANSION_DATA_ROOT': str(self.root / 'data'),
            'OTACON_EXPANSION_DATA_DIR': str(self.root / 'cfg' / 'agents'),
            'OTACON_EXPANSION_PRODUCT_ROOT': str(
                Path(__file__).resolve().parents[1] / 'expansion'
            ),
        }
        self._cm = mock.patch.dict(os.environ, env, clear=False)
        self._cm.start()
        self.layout = resolve_layout()
        self.layout.ensure_user_dirs()
        bootstrap_runtime_state(self.layout)

    def tearDown(self):
        self._cm.stop()
        self.tmp.cleanup()

    def test_classify_intents(self):
        self.assertEqual(classify_chat_intent('thank you, that was brilliant'), 'praise')
        self.assertEqual(classify_chat_intent("that's wrong — I said Tuesday"), 'correct')
        self.assertEqual(classify_chat_intent('please keep it concise'), 'preference')
        self.assertEqual(classify_chat_intent('remember that my dog is named Rex'), 'remember')
        self.assertEqual(classify_chat_intent('what is the status'), 'chat')

    def test_extract_remember_fact(self):
        self.assertEqual(
            extract_remember_fact('Remember that I prefer dark mode'),
            'I prefer dark mode',
        )
        self.assertIsNone(extract_remember_fact('what is status'))

    def test_praise_mutates_emotion_before_context(self):
        emo = EmotionStore(self.layout).get_or_create('aria')
        before_joy = float(emo.dimensions.get('joy') or 0)
        pre = before_reply('aria', 'thank you, good job', layout=self.layout)
        self.assertEqual(pre['intent'], 'praise')
        self.assertTrue(pre['event_id'])
        self.assertTrue(pre['emotion_updates'])
        emo2 = EmotionStore(self.layout).get('aria')
        self.assertGreater(float(emo2.dimensions.get('joy') or 0), before_joy)
        ctx = ExpansionRuntime(self.layout).assemble_context('aria', user_message='hi')
        self.assertIn('Learned claims', ctx.system_prompt)

    def test_correction_mutates_and_learns(self):
        pre = before_reply('aria', "that's wrong, I meant the other one", layout=self.layout)
        self.assertEqual(pre['intent'], 'correct')
        self.assertTrue(pre['learning_observation_id'])
        eng = LearningEngine(self.layout)
        obs = eng.store.list_observations(agent_id='aria', scope='private', limit=20)
        self.assertTrue(any('corrected' in (o.text or '').lower() for o in obs))

    def test_remember_intercept_and_important_memory(self):
        pre = before_reply(
            'aria', 'Remember that my callsign is Otacon', layout=self.layout,
        )
        self.assertTrue(pre['intercept'])
        self.assertIn('Otacon', pre['reply'])
        mems = ExpansionMemory(self.layout).retrieve('aria', 'callsign', limit=5)
        self.assertTrue(any('Otacon' in m.content for m in mems))

    def test_preference_graduates_after_threshold(self):
        for i in range(PATTERN_THRESHOLD):
            before_reply('aria', f'please keep it concise ({i})', layout=self.layout)
        claims = LearningEngine(self.layout).store.list_claims(
            scope='shared', learning_type='owner_preference',
        )
        self.assertTrue(claims)
        self.assertIn('concise', claims[0].claim)

    def test_after_reply_writes_episodic(self):
        pre = before_reply('aria', 'status check', layout=self.layout)
        post = after_reply(
            'aria', 'status check', 'Holding the line.',
            layout=self.layout, event_id=pre['event_id'], intent='chat',
        )
        self.assertTrue(post['memory_id'])
        mems = ExpansionMemory(self.layout).retrieve('aria', 'Holding the line', limit=5)
        self.assertTrue(any('Holding the line' in m.content for m in mems))

    def test_next_turn_sees_learning(self):
        before_reply('aria', 'thank you, you did great', layout=self.layout)
        ctx = ExpansionRuntime(self.layout).assemble_context(
            'aria', user_message='how are we',
        )
        # Living observations or learned claims should appear after social turn
        blob = ctx.system_prompt.lower()
        self.assertTrue(
            'appreciated' in blob
            or 'appreciation' in blob
            or 'learned claims' in blob
        )


if __name__ == '__main__':
    unittest.main()
