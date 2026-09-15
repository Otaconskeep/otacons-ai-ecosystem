import unittest

from expansion.relationship import (
    NEUTRAL_IRRITATION, NEUTRAL_TRUST, EvidenceType, RelationshipState,
    apply_decay, apply_event, classify_affect, new_relationship,
)


class TestRelationshipFormulas(unittest.TestCase):
    def test_no_history_is_inferred_baseline(self):
        s = new_relationship()
        self.assertEqual(s.evidence, EvidenceType.INFERRED_BASELINE)
        self.assertEqual(s.trust, NEUTRAL_TRUST)
        self.assertEqual(classify_affect(s), 'neutral')

    def test_neutral_baseline_classifies_neutral(self):
        self.assertEqual(classify_affect(RelationshipState()), 'neutral')

    def test_positive_interaction_raises_trust(self):
        s = new_relationship()
        apply_event(s, 'compliment', now=1000.0)
        self.assertGreater(s.trust, NEUTRAL_TRUST)
        self.assertEqual(s.evidence, EvidenceType.DIRECT_INTERACTION)

    def test_insult_raises_irritation_but_stays_bounded(self):
        s = new_relationship()
        apply_event(s, 'insult', now=1000.0)
        self.assertGreater(s.irritation, NEUTRAL_IRRITATION)
        self.assertLessEqual(s.irritation, 1.0)

    def test_repeated_insult_does_not_exceed_bounds(self):
        s = new_relationship()
        t = 1000.0
        for _ in range(50):
            apply_event(s, 'insult', now=t)
            t += 1
        self.assertTrue(0.0 <= s.trust <= 1.0)
        self.assertTrue(0.0 <= s.irritation <= 1.0)

    def test_recovery_over_time_decays_irritation_toward_neutral(self):
        s = new_relationship()
        apply_event(s, 'insult', now=1000.0)
        irritated = s.irritation
        apply_decay(s, now=1000.0 + 999 * 3600)
        self.assertLess(s.irritation, irritated)
        self.assertAlmostEqual(s.irritation, NEUTRAL_IRRITATION, delta=0.05)

    def test_one_insult_does_not_permanently_destroy_trust(self):
        s = new_relationship()
        apply_event(s, 'insult', now=1000.0)
        self.assertGreater(s.trust, 0.0)

    def test_conflicting_evidence_direct_overrides_inferred(self):
        s = new_relationship(evidence=EvidenceType.SECONDHAND_REPORT)
        self.assertEqual(s.evidence, EvidenceType.SECONDHAND_REPORT)
        apply_event(s, 'help_given', now=1000.0, evidence=EvidenceType.DIRECT_INTERACTION)
        self.assertEqual(s.evidence, EvidenceType.DIRECT_INTERACTION)

    def test_high_trust_plus_negative_event_does_not_go_negative(self):
        s = RelationshipState(trust=0.95, irritation=0.05, last_event_at=1000.0)
        apply_event(s, 'insult', now=1000.0)
        self.assertTrue(0.0 <= s.trust <= 1.0)

    def test_low_trust_plus_positive_events_does_not_exceed_one(self):
        s = RelationshipState(trust=0.05, irritation=0.1, last_event_at=1000.0)
        for i in range(20):
            apply_event(s, 'compliment', now=1000.0 + i)
        self.assertLessEqual(s.trust, 1.0)

    def test_high_irritation_classifies_rage(self):
        self.assertEqual(classify_affect(RelationshipState(trust=0.5, irritation=0.8)), 'rage')

    def test_moderate_irritation_with_trust_masks_as_sad_masked(self):
        self.assertEqual(classify_affect(RelationshipState(trust=0.6, irritation=0.3)), 'sad_masked')


if __name__ == '__main__':
    unittest.main()
