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


if __name__ == '__main__':
    unittest.main()
