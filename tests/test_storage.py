import unittest
from core.storage import volumes
class StorageTests(unittest.TestCase):
 def test_volume_shape(self):
  x=volumes(['/mnt/data','/']); self.assertTrue(x); self.assertIn('free_gb',x[0]); self.assertIn('path',x[0])
