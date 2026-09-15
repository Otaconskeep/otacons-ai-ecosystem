import json
import tempfile
import unittest
from pathlib import Path

from expansion.hierarchy import find_cycle
from expansion.schema import validate_agent
from expansion.seed_defaults import build_default_roster, seed


class TestSeedDefaults(unittest.TestCase):
    def test_default_roster_has_five_agents(self):
        roster = build_default_roster()
        self.assertEqual(len(roster), 5)
        self.assertEqual(
            {a.agent_id for a in roster},
            {'aria', 'vector', 'ledger', 'muse', 'sentry'},
        )

    def test_every_default_agent_is_schema_valid(self):
        for a in build_default_roster():
            self.assertEqual(validate_agent(a), [], f'{a.agent_id} failed validation')

    def test_default_roster_hierarchy_has_no_cycle(self):
        roster = build_default_roster()
        graph = {a.agent_id: a.reporting_to for a in roster}
        self.assertIsNone(find_cycle(graph))

    def test_aria_is_the_only_rank_1_with_no_manager(self):
        roster = build_default_roster()
        roots = [a for a in roster if a.reporting_to is None]
        self.assertEqual([a.agent_id for a in roots], ['aria'])
        others = [a for a in roster if a.agent_id != 'aria']
        self.assertTrue(all(a.reporting_to == 'aria' for a in others))

    def test_voice_gender_matches_presentation_for_every_default(self):
        for a in build_default_roster():
            self.assertEqual(a.voice.gender, a.presentation)

    def test_seed_writes_five_valid_json_files(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)
            rc = seed(out)
            self.assertEqual(rc, 0)
            files = sorted(out.glob('default-*.json'))
            self.assertEqual(len(files), 5)
            for f in files:
                data = json.loads(f.read_text(encoding='utf-8'))
                self.assertIn('agent_id', data)
                self.assertIn('voice', data)
                self.assertIn('room', data)

    def test_rerun_preserves_original_created_at(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)
            seed(out)
            first = json.loads((out / 'default-aria.json').read_text(encoding='utf-8'))
            seed(out)
            second = json.loads((out / 'default-aria.json').read_text(encoding='utf-8'))
            self.assertEqual(first['created_at'], second['created_at'])

    def test_rerun_does_not_duplicate_or_drop_agents(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)
            seed(out)
            seed(out)
            files = sorted(out.glob('default-*.json'))
            self.assertEqual(len(files), 5)


if __name__ == '__main__':
    unittest.main()
