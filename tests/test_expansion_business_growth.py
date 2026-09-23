"""REX board fills itself with reviewed business drafts. No live model, no live web."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from expansion.bootstrap import bootstrap_runtime_state
from expansion.business_growth import (
    STREAMS,
    _parse_agent_json,
    business_tick,
    discover_business_work,
)
from expansion.jobs import JobStore
from expansion.rex import build_rex_board, get_item, job_to_card
from expansion.state_layout import resolve_layout


def _fake_web_search(query: str):
    return {
        'query': query,
        'results': [{
            'title': 'Public manufacturing note',
            'url': 'https://example.com/manufacturing',
            'snippet': 'Public source text for a local product draft. Not a machine log.',
        }],
    }, 'mock search'


def _fake_web_fetch(url: str):
    return {
        'url': url,
        'snippet': 'Fetched public page text used as evidence. Dashboard was not opened. ' + url,
        'title_guess': 'Example',
    }, 'mock fetch'


def _generate(_layout, actor, payload):
    schema = payload.get('response_schema') or {}
    if 'verdict' in schema:
        return {
            'verdict': 'pass',
            'feedback': (
                f'{actor} reviewed the local draft. Assumptions are labeled and the '
                'experiment has an acceptance check. This is not a production result.'
            ),
        }
    artifact = (
        f'<!-- local {actor} draft -->\n'
        + ('product line for Formless Envysion\n' * 12)
    )
    return {
        'summary': f'{actor} prepared a local draft from the fetched sources, not a live run.',
        'assumptions': 'Costs, kerf, and margins are assumptions until Chris measures them.',
        'experiment': 'Compare one sample against the written acceptance check before any sale.',
        'next_improvement': 'Fold the reviewer note into the next cycle without asking for a new idea.',
        'artifact_content': artifact,
    }


class BusinessGrowthCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        env = {
            'OTACON_EXPANSION_CONFIG_ROOT': str(self.root / 'cfg'),
            'OTACON_EXPANSION_DATA_ROOT': str(self.root / 'data'),
            'OTACON_EXPANSION_DATA_DIR': str(self.root / 'cfg' / 'agents'),
            'OTACON_EXPANSION_PRODUCT_ROOT': str(Path(__file__).resolve().parents[1] / 'expansion'),
            'OTACON_WORKSPACE': str(Path(__file__).resolve().parents[1]),
            'OTACON_BUSINESS_GROWTH': '1',
        }
        self._cm = mock.patch.dict(os.environ, env, clear=False)
        self._cm.start()
        self.layout = resolve_layout()
        self.layout.ensure_user_dirs()
        bootstrap_runtime_state(self.layout)
        self._web = mock.patch.multiple(
            'expansion.tools.web',
            web_search=_fake_web_search,
            web_fetch=_fake_web_fetch,
        )
        self._web.start()

    def tearDown(self):
        self._web.stop()
        self._cm.stop()
        self.tmp.cleanup()

    def test_board_receives_a_reviewed_business_cycle(self):
        out = business_tick(self.layout, generate=_generate, max_advance=1)
        self.assertEqual(len(out['created']), len(STREAMS))
        self.assertEqual(out['advanced'][0]['stage'], 'DONE')
        self.assertEqual(out['status']['website_url'], 'https://formlessenvysion.com/')
        again = discover_business_work(self.layout)
        self.assertEqual(again, [])
        board = build_rex_board(self.layout)
        self.assertTrue(board['business']['enabled'])
        cards = [c for col in board['columns'] for c in col['cards']]
        self.assertGreaterEqual(len(cards), len(STREAMS))
        done = [c for c in cards if c['stage'] == 'DONE']
        self.assertEqual(len(done), 1)
        card = done[0]
        self.assertTrue(card['business_stream'])
        self.assertTrue(card['agent_discussion'])
        self.assertTrue(any(m['kind'] == 'review' for m in card['agent_discussion']))
        item = get_item(card['job_id'], self.layout)
        artifact = Path(item['business_artifact'])
        self.assertTrue(artifact.is_file())
        self.assertGreaterEqual(len(artifact.read_text(encoding='utf-8')), 160)
        report = Path(item['business_report']).read_text(encoding='utf-8')
        self.assertIn('not deployed', report)
        speakers = {m['from'] for m in card['agent_discussion']}
        self.assertIn('aria', speakers)
        self.assertGreaterEqual(len(speakers), 2)
        job = JobStore(self.layout).get(card['job_id'])
        self.assertEqual(job_to_card(job, self.layout)['stage'], 'DONE')
        self.assertIn('cycle', card['title'])

    def test_wrapped_model_json_and_a_stalled_card_does_not_block_the_next(self):
        parsed = _parse_agent_json('Here is the review:\n```json\n{"verdict": "pass", "feedback": "ok"}\n```')
        self.assertEqual(parsed['verdict'], 'pass')

        def generate(layout, actor, payload):
            task = payload.get('task') or ''
            if 'Laser-cut' in task:
                raise ValueError('model returned prose')
            return _generate(layout, actor, payload)

        out = business_tick(self.layout, generate=generate, max_advance=1)
        self.assertTrue(any(row.get('error') for row in out['advanced']))
        self.assertTrue(any(row.get('stage') == 'DONE' for row in out['advanced']))
        board = build_rex_board(self.layout)
        cards = [c for col in board['columns'] for c in col['cards']]
        stalled = [c for c in cards if c.get('business_stream') == 'laser_wood']
        self.assertTrue(stalled)
        self.assertTrue(stalled[0].get('business_stall'))
