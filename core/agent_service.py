import json, urllib.request
from core.router import resolve
def system_prompt(agent):
 return f"You are {agent['display_name']}, a local AI assistant. Be friendly, clear, and helpful."
def chat(deployment, agent, message, conversation_id='default'):
 assignment=resolve(deployment,'conversational_llm')
 payload={'model':assignment.model,'prompt':system_prompt(agent)+'\nUser: '+message,'stream':False}
 req=urllib.request.Request(assignment.endpoint.rstrip('/')+'/api/generate',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
 with urllib.request.urlopen(req,timeout=120) as response:
  data=json.loads(response.read()); text=data.get('response','').strip()
 if not text: raise RuntimeError('LLM returned an empty response')
 return {'conversation_id':conversation_id,'agent_id':agent['id'],'text':text,'service_id':assignment.service_id,'model':assignment.model}
