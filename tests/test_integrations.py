import unittest
from core.integrations import *
class IntegrationTests(unittest.TestCase):
 def setUp(self):
  self.r=IntegrationRegistry(); self.i=self.r.register(Integration('i','Test','SMART_HOME','test',capabilities=['smart_home.read','smart_home.control'],permissions={'agent':{'read_status':True,'set_test_device_state':True}},metadata={'confirmation':{'set_test_device_state':ALWAYS_CONFIRM}})); self.m=IntegrationManager(self.r,{'test':TestIntegrationProvider()})
 def test_read_write_confirmation(self):
  self.assertEqual(self.m.execute(IntegrationActionRequest('1','i','read_status',agent_id='agent')).status,'SUCCEEDED'); x=self.m.execute(IntegrationActionRequest('2','i','set_test_device_state',agent_id='agent')); self.assertTrue(x.confirmation_required); self.assertEqual(self.m.execute(IntegrationActionRequest('2','i','set_test_device_state',agent_id='agent',confirmation_state='CONFIRMED')).status,'SUCCEEDED')
 def test_permission_and_disabled(self):
  self.i.permissions={'agent':{'read_status':False}}; self.assertEqual(self.m.execute(IntegrationActionRequest('1','i','read_status',agent_id='agent')).structured_error['code'],'PERMISSION_DENIED'); self.i.enabled=False; self.assertEqual(self.m.execute(IntegrationActionRequest('2','i','read_status')).structured_error['code'],'INTEGRATION_DISABLED')
 def test_secret_redaction(self): self.assertEqual(self.m.secrets.redact({'token':'x','url':'u'}),{'token':'[REDACTED]','url':'u'})
 def test_webhook_restricts_destination(self):
  i=Integration('w','Webhook','WEBHOOK','webhook',config={'url':'https://example.invalid/hook'},capabilities=['webhook.invoke']); m=IntegrationManager(IntegrationRegistry(),{'webhook':WebhookIntegrationProvider()}); m.registry.register(i); x=m.execute(IntegrationActionRequest('w','w','invoke',{'url':'https://other.invalid'})); self.assertEqual(x.structured_error['code'],'INTEGRATION_ACTION_FAILED')
 def test_external_data_is_data(self): self.assertEqual(TestIntegrationProvider().execute_action(self.i,IntegrationActionRequest('x','i','search_media')).get('items'),['Test Documentary'])
if __name__=='__main__': unittest.main()
