import tempfile, unittest
from pathlib import Path
from core.arbiter import ResourceArbiter, ComputeResource
from core.image import ImageProductionManager, ImageGenerationRequest, TestImageProvider, validate_png, StableDiffusionProvider
class ImageTests(unittest.TestCase):
 def test_test_provider_manager_and_artifact(self):
  with tempfile.TemporaryDirectory() as d:
   a=ResourceArbiter([ComputeResource('gpu',capacity={'vram_gb':24})]); r=ImageProductionManager(a,TestImageProvider(),root=d).generate(ImageGenerationRequest('r1','observatory','draft',agent_id='a',user_id='u'))
   self.assertEqual(r.status,'COMPLETED'); self.assertTrue(Path(r.artifacts[0]['path']).is_file()); self.assertEqual(validate_png(Path(r.artifacts[0]['path']).read_bytes()),(512,512)); self.assertFalse(str(r.artifacts[0]['path']).startswith(str(Path(__file__).parent)))
 def test_insufficient_vram_skips_provider(self):
  a=ResourceArbiter([ComputeResource('gpu',capacity={'vram_gb':4})]); r=ImageProductionManager(a,TestImageProvider()).generate(ImageGenerationRequest('r2','x','quality')); self.assertEqual(r.status,'WAITING_RESOURCE')
 def test_production_provider_does_not_fake_success(self):
  self.assertEqual(StableDiffusionProvider().health('model')[0],'OFFLINE')
 def test_profiles(self):
  from core.image import PROFILES
  self.assertLess(PROFILES['draft']['vram_gb'],PROFILES['quality']['vram_gb'])
if __name__=='__main__': unittest.main()
