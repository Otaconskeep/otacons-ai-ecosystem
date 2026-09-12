from core.router import resolve
from core.providers import OllamaProvider
def system_prompt(agent):
 return f"You are {agent['display_name']}, a local AI assistant. Be friendly, clear, and helpful."
def chat(deployment, agent, message, conversation_id='default', provider=None):
 assignment=resolve(deployment,'conversational_llm')
 provider=provider or OllamaProvider(assignment.endpoint)
 health=provider.health(assignment.model)
 if health.state != 'ONLINE': raise RuntimeError(health.detail)
 text=provider.generate(assignment.model,system_prompt(agent)+'\nUser: '+message)
 return {'conversation_id':conversation_id,'agent_id':agent['id'],'text':text,'service_id':assignment.service_id,'model':assignment.model}
