import unittest

from expansion.decision_audit import new_decision


class TestDecisionAudit(unittest.TestCase):
    def test_confidence_out_of_range_rejected(self):
        with self.assertRaises(ValueError):
            new_decision('s1', 'hi', 'greeting', 'general', 'aria', ('aria',), 1.5)

    def test_valid_decision_has_pending_outcome(self):
        d = new_decision('s1', 'turn off the lights', 'device_control', 'home_assistant',
                          'sentry', ('sentry', 'vector'), 0.91)
        self.assertEqual(d.outcome, 'pending')
        self.assertTrue(d.decision_id.startswith('dec_'))

    def test_finalize_records_outcome_and_latency(self):
        d = new_decision('s1', 'hi', 'greeting', 'general', 'aria', ('aria',), 0.99)
        d.finalize(outcome='success', latency_ms=42.5)
        self.assertEqual(d.outcome, 'success')
        self.assertEqual(d.latency_ms, 42.5)
        self.assertIsNone(d.error)


if __name__ == '__main__':
    unittest.main()
