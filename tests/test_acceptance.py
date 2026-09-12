import unittest
from core.acceptance import report,merge,REQUIRED
class AcceptanceTests(unittest.TestCase):
 def test_sanitized_report(self):
  r=report('server',{'REAL_OLLAMA_INFERENCE_PASS':'PASS'},commit='abc',failures={'REAL_TTS_ACCEPTANCE_PASS':'secret-url-token'}); s=str(r); self.assertNotIn('secret-url-token',s); self.assertEqual(r['app_version'],'0.1.0')
 def test_merge_requires_matching_build(self):
  a=report('server',{},commit='a'); b=report('desktop',{},commit='b'); self.assertEqual(merge([a,b])['reason'],'MISMATCHED_PUBLIC_BUILD')
 def test_merge_and_gate_calculation(self):
  a=report('server',{k:'PASS' for k in REQUIRED},commit='a'); self.assertEqual(merge([a])['result'],'PASS')
 def test_human_confirmation_is_boolean(self): self.assertIs(report('desktop',{},commit='a',confirmations={'NATIVE_GUI_ACCEPTANCE_PASS':True})['confirmations']['NATIVE_GUI_ACCEPTANCE_PASS'],True)
 def test_unavailable_is_pending(self): self.assertEqual(report('server',{'REAL_RESOURCE_ACCEPTANCE_PASS':'PENDING'},commit='a')['result'],'PARTIAL')
if __name__=='__main__': unittest.main()
