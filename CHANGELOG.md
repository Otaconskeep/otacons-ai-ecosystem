# Changelog

## Unreleased

- Optional **Default Model** install: `OTACON_INSTALL_DEFAULT_MODEL=1` installs
  Ollama and pulls a VRAM-sized chat model (`qwen2.5:1.5b` / `3b` / `7b` / `14b`).
- One-click helpers: Linux env flag, `install_otacon_with_default_model.bat` on Windows.
- Chat API uses real `OllamaProvider` when a model is configured.
- `OTACON_INSTALL_OLLAMA` remains an alias; `OTACON_LLM_MODEL=...` overrides the tag.

## 0.1.0 — Development

Otacon — Designed & Engineered by Antonio Garcia

- Hardware-aware native installer foundation.
- Layered deployment topology and capability routing.
- Persistent conversations and agent-scoped memory.
- Provider-neutral local chat and text-to-speech architecture.
- Deterministic test providers for restricted environments.

Copyright © 2026 Antonio Garcia.

The public edition is intentionally separate from Antonio Garcia's private Otacon Keep reference deployment. Private deployment capabilities are generalized and migrated only after they can be distributed safely without private state.
