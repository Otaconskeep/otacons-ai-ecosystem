import tempfile, unittest
from pathlib import Path
from core.arbiter import ResourceArbiter, ComputeResource
from core.video import *
class VideoTests(unittest.TestCase):
 def test_profiles_and_provider_translation(self):
  self.assertEqual((VIDEO_PROFILES['draft']['width'],VIDEO_PROFILES['draft']['height'],VIDEO_PROFILES['draft']['inference_steps_reference']),(640,352,4)); self.assertEqual(VIDEO_PROFILES['final']['inference_steps_reference'],35)
  p=TestVideoProvider().execution_plan(VideoGenerationRequest('x','p','TEXT_TO_VIDEO','draft')); self.assertEqual(p['acceleration_mode'],'provider_resolved')
 def test_t2v_artifact_and_lease_release(self):
  with tempfile.TemporaryDirectory() as d:
   a=ResourceArbiter([ComputeResource('g',capacity={'vram_gb':24})]); r=VideoProductionManager(a,TestVideoProvider(),root=d).generate(VideoGenerationRequest('x','p','TEXT_TO_VIDEO','draft',agent_id='b',user_id='u'))
   self.assertEqual(r.status,'COMPLETED'); validate_video(Path(r.artifacts[0]['path']).read_bytes()); self.assertTrue(all(x.state=='RELEASED' for x in a.leases.values()))
 def test_i2v_requires_source(self):
  r=VideoProductionManager(ResourceArbiter([ComputeResource('g',capacity={'vram_gb':24})]),TestVideoProvider()).generate(VideoGenerationRequest('x','p','IMAGE_TO_VIDEO','draft')); self.assertEqual(r.error['code'],'VIDEO_SOURCE_INVALID')
 def test_insufficient_vram(self):
  r=VideoProductionManager(ResourceArbiter([ComputeResource('g',capacity={'vram_gb':4})]),TestVideoProvider()).generate(VideoGenerationRequest('x','p','TEXT_TO_VIDEO','final')); self.assertEqual(r.status,'WAITING_RESOURCE')
 def test_production_unavailable_is_honest(self): self.assertEqual(ComfyUIProvider().health('x')[0],'OFFLINE')
if __name__=='__main__': unittest.main()
