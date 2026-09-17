import unittest

from expansion.readiness import ReadinessReport, ReadinessState


class TestReadiness(unittest.TestCase):
    def test_core_ready_ignores_optional_components(self):
        r = ReadinessReport()
        for c in ('CORE', 'AGENTS', 'VOICE', 'EMOTIONAL_ENGINE', 'RELATIONSHIPS'):
            r.set(c, ReadinessState.READY)
        r.set('DISCORD', ReadinessState.NOT_CONFIGURED)
        r.set('VIDEO_STUDIO', ReadinessState.UNAVAILABLE)
        self.assertTrue(r.overall_core_ready())

    def test_core_not_ready_if_required_component_down(self):
        r = ReadinessReport()
        r.set('CORE', ReadinessState.READY)
        r.set('AGENTS', ReadinessState.DEGRADED)
        self.assertFalse(r.overall_core_ready())

    def test_to_dict_serializes_enum_values(self):
        r = ReadinessReport()
        r.set('CORE', ReadinessState.READY)
        self.assertEqual(r.to_dict()['CORE'], 'READY')

    def test_ready_story_separates_foundation_from_core(self):
        r = ReadinessReport()
        r.set_semantic('agents_load', ReadinessState.READY)
        r.set_semantic('registry_validates', ReadinessState.READY)
        r.set_semantic('entitlement', ReadinessState.READY)
        r.set('CORE', ReadinessState.READY)
        r.set('AGENTS', ReadinessState.READY)
        r.set('VOICE', ReadinessState.LIMITED)
        r.set('EMOTIONAL_ENGINE', ReadinessState.READY)
        r.set('RELATIONSHIPS', ReadinessState.READY)
        self.assertTrue(r.foundation_ready())
        self.assertTrue(r.expansion_entitled())
        self.assertFalse(r.overall_core_ready())
        story = r.ready_story()
        self.assertIn('foundation_ready', story)
        self.assertIn('entitled', story)
        self.assertIn('VOICE:LIMITED', story)


if __name__ == '__main__':
    unittest.main()
