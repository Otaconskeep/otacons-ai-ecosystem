from dataclasses import dataclass, asdict

@dataclass(frozen=True)
class Model:
    id: str; display_name: str; runtime: str; source_id: str; storage_gb: float
    minimum_ram_gb: float; recommended_ram_gb: float; minimum_vram_gb: float
    cpu_supported: bool; capabilities: tuple[str, ...]; license: str

CATALOG = (
 Model('chat_small','Conversational Small','ollama','qwen2.5:1.5b',1.2,4,8,0,True,('conversational_llm',),'Apache-2.0'),
 Model('chat_standard','Conversational Standard','ollama','qwen2.5:7b',4.7,8,16,8,True,('conversational_llm',),'Apache-2.0'),
)
def recommend(hardware):
 status=getattr(hardware,'gpu_detection',{}).get('status')
 if status in ('error','unavailable') or not hardware.gpus: return CATALOG[0]
 return CATALOG[1] if max(g.vram_gb for g in hardware.gpus)>=8 else CATALOG[0]
def catalog(): return [asdict(x) for x in CATALOG]
