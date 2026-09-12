import tempfile, unittest, hashlib
from pathlib import Path
from datetime import datetime, timezone, timedelta
from core.secure_transport import *
from core.artifact_transfer import receive_artifact
from core.worker import WorkerState
class HardeningTests(unittest.TestCase):
 def test_certificate_trust_and_revoke(self):
  ca=CertificateAuthority(); c=ca.enroll('node'); self.assertTrue(ca.authenticate(c)); ca.revoke(c.fingerprint); self.assertFalse(ca.authenticate(c))
 def test_artifact_integrity_and_atomic_transfer(self):
  with tempfile.TemporaryDirectory() as d:
   b=b'RIFF AVI data'; dest=Path(d)/'x.avi'; kw={'workload_id':'w','expected_workload_id':'w','mime':'video/x-msvideo','checksum':hashlib.sha256(b).hexdigest()}; self.assertEqual(receive_artifact(b,dest,**kw),dest)
   with self.assertRaises(ValueError): receive_artifact(b,Path(d)/'bad',**{**kw,'checksum':'bad'})
   with self.assertRaises(ValueError): receive_artifact(b,Path(d)/'bad',**{**kw,'workload_id':'other'})
 def test_worker_persistence_duplicate_and_cancel(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'worker.json'; w=WorkerState(p); first=w.accept('id',{'capability':'image'}); self.assertIs(w.accept('id',{}),first); self.assertEqual(w.cancel('id',1,'control-plane'),'CANCELED'); self.assertEqual(WorkerState(p).reconcile('id')['state'],'CANCELED')
if __name__=='__main__': unittest.main()
