import unittest

from expansion.schema import (
    AGENT_SCHEMA_VERSION, Agent, Room, Voice, from_dict, new_agent_id,
    to_dict, validate_agent,
)


def _aria():
    return Agent(
        schema_version=AGENT_SCHEMA_VERSION,
        agent_id='agent_aria0001',
        display_name='Aria',
        persona='You are Aria, the composed and decisive coordinator of the Keep. ' * 2,
        role='Command Coordinator',
        domain='coordination',
        archetype='coordinator',
        reporting_to=None,
        authority_rank=1,
        presentation='female',
        voice=Voice(piper_voice='en_US-amy-medium', gender='female', onnx_verified=True),
        room=Room(route='/dashboard', title='Dashboard'),
    )


class TestAgentSchema(unittest.TestCase):
    def test_valid_agent_has_no_errors(self):
        self.assertEqual(validate_agent(_aria()), [])

    def test_rejects_wrong_schema_version(self):
        a = _aria()
        a.schema_version = 99
        self.assertTrue(any('schema_version' in e for e in validate_agent(a)))

    def test_rejects_display_name_used_as_id(self):
        a = _aria()
        a.agent_id = 'Aria Display Name'
        self.assertTrue(any('agent_id' in e for e in validate_agent(a)))

    def test_rejects_placeholder_persona(self):
        a = _aria()
        a.persona = 'TODO'
        self.assertTrue(any('persona' in e for e in validate_agent(a)))

    def test_rejects_pathologically_long_persona(self):
        a = _aria()
        a.persona = 'x' * 9000
        self.assertTrue(any('persona' in e for e in validate_agent(a)))

    def test_rejects_self_report(self):
        a = _aria()
        a.reporting_to = a.agent_id
        self.assertTrue(any('report to itself' in e for e in validate_agent(a)))

    def test_rejects_voice_gender_mismatch(self):
        a = _aria()
        a.voice = Voice(piper_voice='en_US-bryce-medium', gender='male')
        self.assertTrue(any('voice.gender' in e for e in validate_agent(a)))

    def test_renaming_display_name_preserves_identity(self):
        a = _aria()
        original_id = a.agent_id
        a.display_name = 'Nova'
        self.assertEqual(validate_agent(a), [])
        self.assertEqual(a.agent_id, original_id)

    def test_roundtrip_to_dict_from_dict(self):
        a = _aria()
        b = from_dict(to_dict(a))
        self.assertEqual(a.agent_id, b.agent_id)
        self.assertEqual(a.voice.piper_voice, b.voice.piper_voice)
        self.assertEqual(a.room.route, b.room.route)

    def test_new_agent_id_is_unique(self):
        ids = {new_agent_id() for _ in range(500)}
        self.assertEqual(len(ids), 500)


if __name__ == '__main__':
    unittest.main()
