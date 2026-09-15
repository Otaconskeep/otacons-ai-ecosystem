import unittest

from expansion.hierarchy import HierarchyError, assert_acyclic, find_cycle, reassign_orphans


class TestHierarchy(unittest.TestCase):
    def test_valid_tree_has_no_cycle(self):
        g = {'aria': None, 'vector': 'aria', 'ledger': 'aria', 'muse': 'aria', 'sentry': 'aria'}
        self.assertIsNone(find_cycle(g))
        assert_acyclic(g)

    def test_direct_cycle_detected(self):
        g = {'aria': 'vector', 'vector': 'ledger', 'ledger': 'aria'}
        self.assertIsNotNone(find_cycle(g))
        with self.assertRaises(HierarchyError):
            assert_acyclic(g)

    def test_self_report_detected(self):
        self.assertIsNotNone(find_cycle({'aria': 'aria'}))

    def test_dangling_parent_is_not_a_cycle(self):
        g = {'vector': 'ghost_agent'}
        self.assertIsNone(find_cycle(g))

    def test_orphans_reassigned_on_delete(self):
        g = {'aria': None, 'vector': 'aria', 'ledger': 'vector'}
        out = reassign_orphans(g, 'vector', fallback_id='aria')
        self.assertEqual(out['ledger'], 'aria')
        self.assertNotIn('vector', out)

    def test_reassign_orphans_does_not_mutate_input(self):
        g = {'aria': None, 'vector': 'aria', 'ledger': 'vector'}
        reassign_orphans(g, 'vector', fallback_id='aria')
        self.assertEqual(g['ledger'], 'vector')


if __name__ == '__main__':
    unittest.main()
