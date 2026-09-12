import tempfile, unittest
from pathlib import Path
from core.memory import MemoryStore
from core.topology import Deployment,Host,Service
from core.agent_service import chat
from core.providers import TestProvider
class MemoryTests(unittest.TestCase):
 def setUp(self): self.t=tempfile.TemporaryDirectory(); self.m=MemoryStore(Path(self.t.name)/'runtime'/'memory.sqlite'); self.d=Deployment('d',[Host('h')],services=[Service(id='s',service_type='llm',placement_resource_id='h',capabilities=['conversational_llm'],metadata={'endpoint':'test','model':'chat_small'})])
 def tearDown(self): self.m.close(); self.t.cleanup()
 def test_restart_and_isolation(self):
  c=self.m.create_conversation('u1','agent_001'); self.m.remember('u1','agent_001','My dog is Cooper.',c); self.m.close(); self.m=MemoryStore(Path(self.t.name)/'runtime'/'memory.sqlite'); self.assertTrue(self.m.retrieve('u1','agent_001','dog')); self.assertFalse(self.m.retrieve('u1','agent_002','dog')); self.assertFalse(self.m.retrieve('u2','agent_001','dog'))
 def test_prompt_path_persists_messages(self):
  c=self.m.create_conversation('u1','agent_001'); self.m.remember('u1','agent_001','My favorite color is blue.',c); r=chat(self.d,{'id':'agent_001','display_name':'Billy'},'What is my favorite color?',c,TestProvider(),self.m,'u1'); self.assertEqual(r['agent_id'],'agent_001'); self.assertEqual(len(self.m.messages(c)),2)
 def test_delete(self):
  self.m.remember('u1','a','fact'); mid=self.m.list_memories('u1','a')[0]['id']; self.m.delete_memory(mid,'u1','a'); self.assertEqual(self.m.list_memories('u1','a'),[])
