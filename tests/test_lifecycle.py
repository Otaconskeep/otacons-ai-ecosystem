import tempfile, unittest, hashlib
from pathlib import Path
from core.lifecycle import *
from core.nodes import NodeRegistry
class LifecycleTests(unittest.TestCase):
 def test_backup_restore_manifest(self):
  with tempfile.TemporaryDirectory() as d:
   s=Path(d)/'s'; s.mkdir(); (s/'a').write_text('x'); a=Path(d)/'a.zip'; BackupManager().create(s,a); out=Path(d)/'o'; m=RestoreManager().restore(a,out); self.assertEqual((out/'a').read_text(),'x'); self.assertEqual(m['format_version'],1)
 def test_bad_update_rejected(self):
  with tempfile.NamedTemporaryFile() as f:
   f.write(b'x'); f.flush()
   with self.assertRaises(ValueError): UpdateManager().verify({'sha256':'bad','version':'1','package_identity':'otacon'},f.name)
 def test_health_and_diagnostics_redact(self): self.assertEqual(HealthManager().aggregate([{'status':'HEALTHY'}])['status'],'HEALTHY'); self.assertIn('secrets',Diagnostics().bundle([])['redacted_fields'])
 def test_node_registry_persists(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'nodes.json'; r=NodeRegistry(p); n,_=r.approve_pairing(r.create_pairing(),'Worker'); r2=NodeRegistry(p); self.assertIn(n.node_id,r2.nodes)
 def test_uninstall_preserves_by_default(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'data'; p.mkdir(); (p/'x').write_text('x'); self.assertFalse(uninstall(p)['user_data_deleted']); self.assertTrue((p/'x').exists())
if __name__=='__main__': unittest.main()
