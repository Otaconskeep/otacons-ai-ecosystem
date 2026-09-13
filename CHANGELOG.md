# Changelog

## Unreleased

- Normal Otacon one-click includes **Default Model** (Ollama + VRAM-tier chat)
  and **Genome Voice Trainer**. Skip with `OTACON_INSTALL_DEFAULT_MODEL=0` /
  `OTACON_INSTALL_VOICE_TRAINER=0`.
- Chat API uses real `OllamaProvider` when a model is configured.
- `OTACON_LLM_MODEL=...` overrides the auto-picked Ollama tag.

## 0.1.0 — Development

Otacon — Designed & Engineered by Antonio Garcia

- Hardware-aware native installer foundation.
- Layered deployment topology and capability routing.
- Persistent conversations and agent-scoped memory.
- Provider-neutral local chat and text-to-speech architecture.
- Deterministic test providers for restricted environments.

Copyright © 2026 Antonio Garcia.

The public edition is intentionally separate from Antonio Garcia's private Otacon Keep reference deployment. Private deployment capabilities are generalized and migrated only after they can be distributed safely without private state.
