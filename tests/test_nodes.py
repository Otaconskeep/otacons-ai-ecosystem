import unittest
from datetime import datetime, timezone, timedelta
from core.nodes import NodeRegistry, TestNodeAgent
class NodeTests(unittest.TestCase):
 def test_pair_single_use_and_revoke(self):
  r=NodeRegistry(); c=r.create_pairing(); n,e=r.approve_pairing(c,'Worker'); self.assertEqual(n.trust_state,'TRUSTED'); self.assertIsNone(r.approve_pairing(c,'Again')[0]); self.assertTrue(r.revoke(n.node_id)); self.assertEqual(r.heartbeat(n.node_id)['status'],'NODE_AUTH_FAILED')
 def test_heartbeat_offline_and_reconnect(self):
  r=NodeRegistry(); n,_=r.approve_pairing(r.create_pairing(),'Worker'); r.heartbeat(n.node_id); n.last_seen=(datetime.now(timezone.utc)-timedelta(seconds=1000)).isoformat(); self.assertIn(n.node_id,r.mark_offline(90)); self.assertEqual(r.heartbeat(n.node_id)['status'],'OK'); self.assertEqual(n.status,'ONLINE')
 def test_dispatch_idempotency_and_service(self):
  r=NodeRegistry(); n,_=r.approve_pairing(r.create_pairing(),'Worker'); r.heartbeat(n.node_id,services=[{'capabilities':['image_generation'],'health':'READY'}]); w,e=r.dispatch(n.node_id,'w','image_generation',{'prompt':'x'}); self.assertIsNone(e); same,e=r.dispatch(n.node_id,'w','image_generation',{}); self.assertEqual(e,'DUPLICATE'); self.assertIs(same,w)
 def test_untrusted_and_missing_service(self):
  r=NodeRegistry(); n,_=r.approve_pairing(r.create_pairing(),'Worker'); r.heartbeat(n.node_id); self.assertEqual(r.dispatch(n.node_id,'w','video_generation',{})[1],'NODE_SERVICE_UNAVAILABLE')
 def test_structured_agent_execution(self):
  r=NodeRegistry(); n,_=r.approve_pairing(r.create_pairing(),'Worker'); agent=TestNodeAgent(r,n.node_id,[{'capabilities':['conversational_llm'],'health':'READY'}]); agent.connect(); w,_=r.dispatch(n.node_id,'w','conversational_llm',{}); self.assertEqual(agent.execute(w)['status'],'COMPLETED')
if __name__=='__main__': unittest.main()
