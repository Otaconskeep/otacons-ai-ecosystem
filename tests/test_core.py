import json,tempfile,unittest
from pathlib import Path
from core.platform import GPU,Hardware
from core.planner import recommend_hardware_plan
from core.config import build_config,save
class T(unittest.TestCase):
 def h(self,g): return Hardware('Linux','CPU',8,32,100,g)
 def test_no_gpu(self): self.assertEqual(recommend_hardware_plan(self.h([]))['gpu_roles']['primary_gpu'],'cpu')
 def test_one_gpu(self): self.assertEqual(recommend_hardware_plan(self.h([GPU('gpu_001','nvidia','x',24,'GPU_HIGH_END')]))['gpu_roles']['primary_gpu'],'gpu_001')
 def test_two_gpu(self): self.assertEqual(recommend_hardware_plan(self.h([GPU('gpu_001','nvidia','x',6),GPU('gpu_002','nvidia','y',24)]))['gpu_roles']['primary_gpu'],'gpu_002')
 def test_name(self): self.assertNotIn('Otacon',json.dumps(build_config(recommend_hardware_plan(self.h([])),'Billy',['chat'])['agents']))
 def test_roundtrip(self):
  with tempfile.TemporaryDirectory() as d: self.assertEqual(json.loads(save(build_config(recommend_hardware_plan(self.h([])),'Sarah',['memory']),Path(d)).read_text())['agents'][0]['display_name'],'Sarah')
