import unittest
from core.voice import *
class VoiceTests(unittest.TestCase):
 def test_profiles_and_isolation(self):
  a=synthesize({'voice_id':'voice_001'},'x'); b=synthesize({'voice_id':'voice_002'},'x'); self.assertNotEqual(a['voice_id'],b['voice_id']); self.assertEqual(a['synthesis']['length_scale'],1.0); self.assertEqual(b['synthesis']['length_scale'],1.25)
 def test_invalid_profile(self):
  with self.assertRaises(ValueError): VoiceProfile('x','x','test','x',synthesis={'noise_w':0}).validate()
 def test_audio_result(self): self.assertTrue(synthesize({'voice_id':'voice_001'},'x')['bytes'].startswith(b'RIFF'))
 def test_missing_voice(self):
  with self.assertRaises(LookupError): synthesize({'voice_id':'missing'},'x')
