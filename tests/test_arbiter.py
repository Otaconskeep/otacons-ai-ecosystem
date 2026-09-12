import unittest
from core.arbiter import *
class ArbiterTests(unittest.TestCase):
 def setUp(self): self.a=ResourceArbiter([ComputeResource('a',capacity={'vram_gb':24}),ComputeResource('b',capacity={'vram_gb':16})])
 def test_multi_gpu_and_capacity(self):
  x=self.a.request(WorkloadRequest('w1','INTERACTIVE_CHAT','llm',{'vram_gb':18},preemptible=False,owner_id='o')); self.assertEqual(x['lease'].resource_id,'a')
  y=self.a.request(WorkloadRequest('w2','INTERACTIVE_CHAT','llm',{'vram_gb':10},owner_id='o')); self.assertEqual(y['lease'].resource_id,'b')
  self.assertIn(self.a.request(WorkloadRequest('w3','IMAGE_GENERATION','image',{'vram_gb':20}))['status'],('RESOURCE_BUSY','INSUFFICIENT_VRAM'))
 def test_lease_owner_and_release(self):
  x=self.a.request(WorkloadRequest('w','TEXT_TO_SPEECH','tts',{'vram_gb':2},owner_id='owner')); l=x['lease']; self.assertEqual(self.a.release(l.lease_id,'wrong')['status'],'LEASE_CONFLICT'); self.assertEqual(self.a.release(l.lease_id,'owner')['status'],'RELEASED')
 def test_reclaim_idle_residency(self):
  self.a.resources['a'].used={'vram_gb':14}; self.a.residency=[Residency('a','svc','model',14)]
  self.assertEqual(self.a.reclaim_idle(10),14); self.assertEqual(self.a.resources['a'].used['vram_gb'],0)
 def test_circuit_breaker(self):
  for _ in range(3): result=self.a.record_failure('svc','same')
  self.assertEqual(result['state'],'CIRCUIT_OPEN')
 def test_passthrough_exposure(self):
  r=ComputeResource('gpu','GPU','host',exposed_to=['vm','docker'],capacity={'vram_gb':24}); self.assertIn('vm',r.exposed_to); self.assertEqual(r.owner_resource_id,'host')
if __name__=='__main__': unittest.main()
