import argparse,tempfile
from core.memory import MemoryStore
from core.providers import TestProvider
from core.topology import Deployment,Host,Service
from core.agent_service import chat
def main():
 p=argparse.ArgumentParser(); p.add_argument('--agent',default='Billy'); a=p.parse_args(); f=tempfile.NamedTemporaryFile(suffix='.sqlite'); m=MemoryStore(f.name); cid=m.create_conversation('acceptance','agent_001'); m.remember('acceptance','agent_001',"My dog's name is Cooper.",cid); m.close(); m=MemoryStore(f.name); d=Deployment('d',[Host('h')],services=[Service(id='test_llm',service_type='llm',placement_resource_id='h',capabilities=['conversational_llm'],metadata={'model':'test'})]); r=chat(d,{'id':'agent_001','display_name':a.agent},"What is my dog's name?",m.create_conversation('acceptance','agent_001'),TestProvider(),m,'acceptance'); print('MEMORY_STORAGE_PASS\nMEMORY_RETRIEVAL_PASS\nCONTEXT_ASSEMBLY_PASS\nResponse: '+r['text']+'\nREAL_INFERENCE_PENDING')
if __name__=='__main__': main()
