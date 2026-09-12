from core.router import resolve
from core.providers import OllamaProvider
def system_prompt(agent):
 return f"You are {agent['display_name']}, a local AI assistant. Be friendly, clear, and helpful."
def chat(deployment, agent, message, conversation_id='default', provider=None, memory=None, user_id='local_user'):
 assignment=resolve(deployment,'conversational_llm')
 provider=provider or OllamaProvider(assignment.endpoint)
 health=provider.health(assignment.model)
 if health.state != 'ONLINE': raise RuntimeError(health.detail)
 context=''
 if memory:
  prior=memory.messages(conversation_id); facts=memory.retrieve(user_id,agent['id'],message)
  context='\n'.join(f"{x['role']}: {x['content']}" for x in prior[-10:])
  context+='\nRelevant memory: '+'; '.join(x['content'] for x in facts)
 text=provider.generate(assignment.model,system_prompt(agent)+'\n'+context+'\nUser: '+message)
 if memory: memory.append(conversation_id,user_id,agent['id'],'user',message); memory.append(conversation_id,user_id,agent['id'],'assistant',text)
 return {'conversation_id':conversation_id,'agent_id':agent['id'],'text':text,'service_id':assignment.service_id,'model':assignment.model}
