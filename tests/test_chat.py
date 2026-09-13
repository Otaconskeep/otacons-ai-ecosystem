import unittest
from unittest.mock import patch
from types import SimpleNamespace
from core.models import recommend
from core.topology import Deployment,Host,Service
from core.agent_service import system_prompt
from core.router import resolve
from core.providers import TestProvider
from core.agent_service import chat

class ChatTests(unittest.TestCase):
 def test_conservative_model_when_gpu_inspection_errors(self):
  h=SimpleNamespace(gpus=[],gpu_detection={'status':'error'}); self.assertEqual(recommend(h).id,'chat_small')
 def test_vram_tiers(self):
  from core.models import recommend_from_vram_gb
  self.assertEqual(recommend_from_vram_gb(0).source_id,'qwen2.5:1.5b')
  self.assertEqual(recommend_from_vram_gb(6).source_id,'qwen2.5:3b')
  self.assertEqual(recommend_from_vram_gb(8).source_id,'qwen2.5:7b')
  self.assertEqual(recommend_from_vram_gb(16).source_id,'qwen2.5:14b')
  g=lambda v: SimpleNamespace(gpus=[SimpleNamespace(vram_gb=v)],gpu_detection={'status':'detected'})
  self.assertEqual(recommend(g(24)).id,'chat_large')
 def test_capability_router_is_placement_independent(self):
  d=Deployment('d',[Host('host_a')],services=[Service(id='svc',service_type='llm',placement_resource_id='host_a',capabilities=['conversational_llm'],metadata={'endpoint':'http://service','model':'chat_small'})])
  a=resolve(d,'conversational_llm'); self.assertEqual(a.placement,'host_a'); self.assertEqual(a.endpoint,'http://service')
 def test_identity_prompt_is_generic(self):
  p=system_prompt({'id':'agent_001','display_name':'Billy'}); self.assertIn('Billy',p); self.assertNotIn('Otacon',p)
 def test_end_to_end_test_provider_for_two_agents(self):
  d=Deployment('d',[Host('host_a')],services=[Service(id='svc',service_type='llm',placement_resource_id='host_a',capabilities=['conversational_llm'],metadata={'endpoint':'test://','model':'chat_small'})])
  for i,name in enumerate(('Billy','Sarah'),1):
   r=chat(d,{'id':f'agent_{i:03d}','display_name':name},'What is your name?',provider=TestProvider())
   self.assertEqual(r['text'],f'My name is {name}.'); self.assertEqual(r['service_id'],'svc')

if __name__=='__main__': unittest.main()
