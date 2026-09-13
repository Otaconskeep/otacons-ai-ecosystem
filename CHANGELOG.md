# Changelog

## Unreleased

- Installer installs Ollama by default and pulls a VRAM-sized chat model
  (`qwen2.5:1.5b` / `3b` / `7b` / `14b`), then wires Otacon chat to it.
- Chat API uses real `OllamaProvider` instead of the deterministic test double.
- `OTACON_INSTALL_OLLAMA=0` / `OTACON_LLM_MODEL=...` overrides available.

## 0.1.0 — Development

Otacon — Designed & Engineered by Antonio Garcia

- Hardware-aware native installer foundation.
- Layered deployment topology and capability routing.
- Persistent conversations and agent-scoped memory.
- Provider-neutral local chat and text-to-speech architecture.
- Deterministic test providers for restricted environments.

Copyright © 2026 Antonio Garcia.

The public edition is intentionally separate from Antonio Garcia's private Otacon Keep reference deployment. Private deployment capabilities are generalized and migrated only after they can be distributed safely without private state.
