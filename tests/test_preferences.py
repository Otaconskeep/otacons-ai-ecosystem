import tempfile,unittest
from core.preferences import Preferences
class PreferenceTests(unittest.TestCase):
 def test_persistence_and_isolation(self):
  p=tempfile.NamedTemporaryFile(); a=Preferences(p.name); a.set_auto_speak('u','b',True); b=Preferences(p.name); self.assertTrue(b.get_auto_speak('u','b')); self.assertFalse(b.get_auto_speak('u','s'))
