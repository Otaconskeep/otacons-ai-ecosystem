from dataclasses import dataclass, asdict


@dataclass(frozen=True)
class Model:
    id: str
    display_name: str
    runtime: str
    source_id: str
    storage_gb: float
    minimum_ram_gb: float
    recommended_ram_gb: float
    minimum_vram_gb: float
    cpu_supported: bool
    capabilities: tuple[str, ...]
    license: str


# Default Ollama chat models by VRAM. Installer pulls source_id automatically.
CATALOG = (
    Model(
        'chat_small', 'Conversational Small', 'ollama', 'qwen2.5:1.5b',
        1.2, 4, 8, 0, True, ('conversational_llm',), 'Apache-2.0',
    ),
    Model(
        'chat_medium', 'Conversational Medium', 'ollama', 'qwen2.5:3b',
        2.0, 6, 12, 6, True, ('conversational_llm',), 'Apache-2.0',
    ),
    Model(
        'chat_standard', 'Conversational Standard', 'ollama', 'qwen2.5:7b',
        4.7, 8, 16, 8, True, ('conversational_llm',), 'Apache-2.0',
    ),
    Model(
        'chat_large', 'Conversational Large', 'ollama', 'qwen2.5:14b',
        9.0, 16, 32, 16, False, ('conversational_llm',), 'Apache-2.0',
    ),
)


def recommend(hardware):
    """Pick a default chat model from detected GPU VRAM (or CPU-safe small)."""
    status = (getattr(hardware, 'gpu_detection', None) or {}).get('status')
    gpus = getattr(hardware, 'gpus', None) or []
    if status in ('error', 'unavailable') or not gpus:
        return CATALOG[0]
    vram = max(float(getattr(g, 'vram_gb', 0) or 0) for g in gpus)
    if vram >= 16:
        return CATALOG[3]
    if vram >= 8:
        return CATALOG[2]
    if vram >= 6:
        return CATALOG[1]
    return CATALOG[0]


def recommend_from_vram_gb(vram_gb: float):
    """Same tiers as recommend(), for the bash installer (no Hardware object)."""
    v = float(vram_gb or 0)
    if v >= 16:
        return CATALOG[3]
    if v >= 8:
        return CATALOG[2]
    if v >= 6:
        return CATALOG[1]
    return CATALOG[0]


def catalog():
    return [asdict(x) for x in CATALOG]
