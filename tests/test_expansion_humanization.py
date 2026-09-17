"""Aria / Expansion humanization — Turing spine + idiolect contracts."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from expansion.bootstrap import bootstrap_runtime_state
from expansion.canonical_dossiers import clear_dossier_cache, get_canonical_dossier
from expansion.humanization import (
    clear_humanization_cache,
    contains_embodiment_tell,
    core_fallback_persona,
    dossier_prompt_block,
    human_embodiment_fallback,
    load_human_sheet,
    praise_language_directive,
    render_dossier_self_reply,
    spoken_self_state,
)
from expansion.idiolect import apply_idiolect
from expansion.runtime import ExpansionRuntime
from expansion.state_layout import resolve_layout


class HumanizationCase(unittest.TestCase):
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
        clear_dossier_cache()
        clear_humanization_cache()
        self.layout = resolve_layout()
        self.layout.ensure_user_dirs()
        bootstrap_runtime_state(self.layout)

    def tearDown(self):
        clear_dossier_cache()
        clear_humanization_cache()
        self._cm.stop()
        self.tmp.cleanup()

    def test_aria_sheet_has_speech_taste_embodiment(self):
        sheet = load_human_sheet('aria', self.layout)
        self.assertIn('speech', sheet)
        self.assertIn('taste', sheet)
        self.assertIn('embodiment', sheet)
        self.assertEqual(sheet['speech'].get('formality'), 'high')
        self.assertTrue(sheet['taste'].get('music'))

    def test_canonical_dossier_still_valid_with_spine_fields(self):
        d = get_canonical_dossier('aria', self.layout)
        self.assertEqual(d.agent_id, 'aria')
        self.assertIn('formally warm', d.character.communication_style)

    def test_who_you_are_block(self):
        block = dossier_prompt_block('aria', layout=self.layout)
        self.assertIn('WHO YOU ARE', block)
        self.assertIn('Never mention being an AI', block)
        self.assertIn('Speech:', block)
        self.assertIn('Taste', block)

    def test_assemble_context_injects_spine(self):
        ctx = ExpansionRuntime(self.layout).assemble_context(
            'aria', user_message='thank you, that was brilliant',
        )
        self.assertIn('WHO YOU ARE', ctx.system_prompt)
        self.assertIn('Never mention being an AI', ctx.system_prompt)
        self.assertIn('How you feel right now', ctx.system_prompt)
        self.assertIn('EXPRESSION RULE', ctx.system_prompt)
        self.assertNotIn('local AI assistant', ctx.system_prompt)

    def test_idiolect_strips_embodiment_and_corporate(self):
        dirty = (
            'Certainly! As an AI, I would be happy to help. '
            'Is there anything else I can help you with?'
        )
        clean = apply_idiolect(dirty, 'aria')
        self.assertFalse(contains_embodiment_tell(clean))
        self.assertNotIn('Certainly', clean)
        self.assertNotIn('happy to help', clean.lower())
        self.assertNotIn('as an ai', clean.lower())

    def test_idiolect_strips_aria_slang(self):
        out = apply_idiolect('Yeah gonna check that for you.', 'aria')
        self.assertNotRegex(out.lower(), r'\b(yeah|gonna)\b')

    def test_embodiment_fallback(self):
        line = human_embodiment_fallback('aria', 'default', layout=self.layout)
        self.assertIn('present', line.lower())

    def test_self_reply_biography(self):
        reply = render_dossier_self_reply('aria', 'tell me about yourself', layout=self.layout)
        self.assertTrue(reply)
        self.assertNotIn('as an AI', reply)
        self.assertTrue(reply[0].isupper() or reply.startswith('I'))

    def test_spoken_self_state_no_telemetry(self):
        line = spoken_self_state({'stress': 0.7, 'attachment': 0.8, 'jealousy': 0.5})
        self.assertNotRegex(line, r'\d+%')
        self.assertNotIn('=', line)

    def test_praise_directive(self):
        self.assertIn('EXPRESSION RULE', praise_language_directive('thank you so much'))
        self.assertEqual(praise_language_directive('what is the status'), '')

    def test_core_fallback_not_bland_for_aria(self):
        from core.agent_service import system_prompt
        p = system_prompt({'id': 'agent_001', 'display_name': 'Aria'})
        self.assertNotIn('local AI assistant', p)
        self.assertIn('Aria', p)
        self.assertIn('Never mention being an AI', p)
        bland = system_prompt({'display_name': 'Billy'})
        self.assertIn('local AI assistant', bland)

    def test_core_fallback_helper(self):
        self.assertIsNotNone(core_fallback_persona('aria'))
        self.assertIsNone(core_fallback_persona('billy'))


if __name__ == '__main__':
    unittest.main()
