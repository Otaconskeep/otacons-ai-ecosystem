"""Provider-neutral integrations with explicit policy and secret boundaries."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
import hashlib, json, urllib.parse, urllib.request

READY='READY'; DEGRADED='DEGRADED'; UNAVAILABLE='UNAVAILABLE'; AUTH_REQUIRED='AUTH_REQUIRED'; MISCONFIGURED='MISCONFIGURED'
NO_CONFIRMATION='NO_CONFIRMATION'; CONFIRM_ONCE='CONFIRM_ONCE'; ALWAYS_CONFIRM='ALWAYS_CONFIRM'; HIGH_RISK_CONFIRMATION='HIGH_RISK_CONFIRMATION'
@dataclass
class Integration:
 integration_id:str; display_name:str; integration_type:str; provider:str; enabled:bool=True; capabilities:list[str]=field(default_factory=list); permissions:dict=field(default_factory=dict); secret_ref:str|None=None; status:str='UNKNOWN'; config:dict=field(default_factory=dict); metadata:dict=field(default_factory=dict)
@dataclass
class IntegrationActionRequest:
 request_id:str; integration_id:str; action:str; parameters:dict=field(default_factory=dict); user_id:str='local_user'; agent_id:str|None=None; conversation_id:str|None=None; confirmation_state:str='UNCONFIRMED'; timeout:float=10
@dataclass
class IntegrationActionResult:
 request_id:str; status:str; integration_id:str; action:str; result_data:dict=field(default_factory=dict); provider:str=''; duration:float|None=None; confirmation_required:bool=False; structured_error:dict|None=None; metadata:dict=field(default_factory=dict)
class IntegrationProvider:
 provider_id='unknown'
 def health(self,integration): return READY,'ready'
 def capabilities(self): return []
 def validate_configuration(self,integration): return True
 def execute_action(self,integration,request): raise NotImplementedError
class TestIntegrationProvider(IntegrationProvider):
 provider_id='test'
 def capabilities(self): return ['smart_home.read','smart_home.control','messaging.send','media.search','media.play','notifications.send']
 def execute_action(self,i,r):
  if r.action=='read_status': return {'entity_id':r.parameters.get('entity_id'),'state':'off'}
  if r.action=='set_test_device_state': return {'state':r.parameters.get('state','on')}
  if r.action=='send_message': return {'destination_id':r.parameters.get('destination_id'),'sent':True}
  if r.action=='search_media': return {'items':['Test Documentary']}
  if r.action=='play': return {'playing':True}
  if r.action=='send_notification': return {'delivered':True}
  raise ValueError('ACTION_NOT_SUPPORTED')
class SmartHomeProvider(TestIntegrationProvider): provider_id='smart_home'
class MessagingProvider(TestIntegrationProvider): provider_id='messaging'
class MediaProvider(TestIntegrationProvider): provider_id='media'
class NotificationProvider(TestIntegrationProvider): provider_id='notifications'
class WebhookIntegrationProvider(IntegrationProvider):
 provider_id='webhook'
 def health(self,i): return (MISCONFIGURED,'endpoint is not configured') if not i.config.get('url') else READY,'configured'
 def capabilities(self): return ['webhook.invoke']
 def execute_action(self,i,r):
  url=i.config.get('url',''); parsed=urllib.parse.urlparse(url)
  if parsed.scheme not in ('https','http') or not parsed.hostname: raise ValueError('WEBHOOK_URL_INVALID')
  if r.parameters.get('url') and r.parameters['url']!=url: raise ValueError('WEBHOOK_DESTINATION_BLOCKED')
  body=json.dumps(r.parameters.get('body',{})).encode(); req=urllib.request.Request(url,body=body,headers={'Content-Type':'application/json'},method='POST')
  with urllib.request.urlopen(req,timeout=min(r.timeout,30)) as response:
   if int(response.headers.get('Content-Length','0') or 0)>1048576: raise ValueError('WEBHOOK_RESPONSE_TOO_LARGE')
   return {'http_status':response.status,'body':response.read(1048576).decode(errors='replace')}
class SecretStore:
 def __init__(self): self._values={}
 def put(self,ref,value): self._values[ref]=value; return ref
 def get(self,ref): return self._values.get(ref)
 def delete(self,ref): self._values.pop(ref,None)
 def redact(self,obj):
  if isinstance(obj,dict): return {k:('[REDACTED]' if 'secret' in k or 'token' in k else self.redact(v)) for k,v in obj.items()}
  return obj
class IntegrationRegistry:
 def __init__(self): self.items={}
 def register(self,i): self.items[i.integration_id]=i; return i
 def remove(self,id): self.items.pop(id,None)
 def get(self,id): return self.items.get(id)
class IntegrationManager:
 def __init__(self,registry,providers=None,secrets=None): self.registry=registry; self.providers=providers or {}; self.secrets=secrets or SecretStore(); self.audit=[]
 def _provider(self,i):
  p=self.providers.get(i.provider)
  if not p: raise ValueError('INTEGRATION_PROVIDER_UNAVAILABLE')
  return p
 def execute(self,r):
  i=self.registry.get(r.integration_id)
  if not i or not i.enabled: return IntegrationActionResult(r.request_id,'FAILED',r.integration_id,r.action,structured_error={'code':'INTEGRATION_DISABLED'})
  p=self._provider(i)
  family='read' if r.action.startswith(('read','get','list','search','browse')) else ('control' if r.action in ('turn_on','turn_off','set_test_device_state','play','pause','stop') else 'send')
  capability=next((c for c in i.capabilities if c.endswith('.'+family) or c==r.action or c.endswith('.'+r.action)),None)
  if not capability: return IntegrationActionResult(r.request_id,'FAILED',i.integration_id,r.action,provider=p.provider_id,structured_error={'code':'PERMISSION_DENIED'})
  policy=i.permissions.get(r.agent_id or '*',{}); allowed=policy.get(r.action,True)
  if not allowed:return IntegrationActionResult(r.request_id,'FAILED',i.integration_id,r.action,provider=p.provider_id,structured_error={'code':'PERMISSION_DENIED'})
  risk=i.metadata.get('confirmation',{}).get(r.action,NO_CONFIRMATION)
  if risk!=NO_CONFIRMATION and r.confirmation_state!='CONFIRMED': return IntegrationActionResult(r.request_id,'CONFIRMATION_REQUIRED',i.integration_id,r.action,provider=p.provider_id,confirmation_required=True,metadata={'policy':risk})
  try: data=p.execute_action(i,r); result=IntegrationActionResult(r.request_id,'SUCCEEDED',i.integration_id,r.action,data,provider=p.provider_id); self.audit.append({'request_id':r.request_id,'integration_id':i.integration_id,'action':r.action,'status':result.status}); return result
  except Exception as e: return IntegrationActionResult(r.request_id,'FAILED',i.integration_id,r.action,provider=p.provider_id,structured_error={'code':'INTEGRATION_ACTION_FAILED','detail':str(e)})
