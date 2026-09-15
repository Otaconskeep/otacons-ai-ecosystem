import unittest

from expansion.motion_manifest import (
    CapabilityLevel, MotionManifest, MotionState, resolve_candidates_for_frontend,
    select_state_for_capability, validate_manifest,
)


def _full_manifest():
    states = {}
    for name in ('idle', 'talking'):
        states[name] = MotionState(name=name, candidates=(f'https://x/{name}.mp4',), loop=True)
    for name in ('happy', 'angry', 'rage', 'sad', 'sad_masked', 'thinking_hard', 'thinking'):
        states[name] = MotionState(
            name=name, candidates=(f'https://x/{name}.mp4',), loop=False,
            still_frame_after=f'https://x/{name}_hold.jpg',
        )
    return MotionManifest('aria', 'https://x/portrait.png', CapabilityLevel.FULL_EMOTIONAL_PACK, states)


class TestMotionManifest(unittest.TestCase):
    def test_full_manifest_is_valid(self):
        self.assertEqual(validate_manifest(_full_manifest()), [])

    def test_missing_required_state_is_rejected(self):
        m = _full_manifest()
        del m.states['idle']
        self.assertTrue(any('idle' in e for e in validate_manifest(m)))

    def test_looping_state_marked_one_shot_is_rejected(self):
        m = _full_manifest()
        m.states['idle'] = MotionState(name='idle', candidates=('https://x/idle.mp4',), loop=False)
        errors = validate_manifest(m)
        self.assertTrue(any('idle' in e and 'loop' in e for e in errors))

    def test_one_shot_state_without_still_frame_is_rejected(self):
        m = _full_manifest()
        m.states['rage'] = MotionState(name='rage', candidates=('https://x/rage.mp4',), loop=False)
        errors = validate_manifest(m)
        self.assertTrue(any('rage' in e and 'still_frame_after' in e for e in errors))

    def test_list_instead_of_tuple_candidates_is_rejected(self):
        m = _full_manifest()
        # this is the actual historical bug: a bare list/array of candidates
        m.states['idle'].candidates = ['https://x/idle.mp4', 'https://x/idle2.mp4']
        errors = validate_manifest(m)
        self.assertTrue(any('idle' in e and 'tuple' in e for e in errors))

    def test_resolve_candidates_always_flattens_even_malformed_input(self):
        st = MotionState(name='idle', candidates=(['a', 'b'], 'c'), loop=True)
        out = resolve_candidates_for_frontend(st)
        self.assertEqual(out, ['a', 'b', 'c'])
        self.assertIsInstance(out, list)
        self.assertTrue(all(isinstance(x, str) for x in out))

    def test_fallback_ladder_uses_portrait_for_static_agent(self):
        m = MotionManifest('vector', 'https://x/portrait.png', CapabilityLevel.STATIC_PORTRAIT, {})
        self.assertEqual(select_state_for_capability('rage', CapabilityLevel.STATIC_PORTRAIT, m), '__portrait__')

    def test_fallback_ladder_uses_talking_for_missing_affect_state(self):
        states = {'talking': MotionState('talking', ('https://x/talking.mp4',), True)}
        m = MotionManifest('vector', 'https://x/portrait.png', CapabilityLevel.PORTRAIT_PLUS_TALKING, states)
        self.assertEqual(select_state_for_capability('rage', CapabilityLevel.PORTRAIT_PLUS_TALKING, m), 'talking')


if __name__ == '__main__':
    unittest.main()
