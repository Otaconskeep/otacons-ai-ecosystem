# Beta Acceptance Gate 1

This document records environment-dependent acceptance separately from deterministic architecture tests. Runtime endpoints, credentials, model state, conversations, and audio remain outside the repository.

## Current results

| Check | Result |
|---|---|
| Public OllamaProvider inference | `REAL_OLLAMA_INFERENCE_PASS` |
| Persistent memory with real Ollama | `REAL_MEMORY_INFERENCE_PASS` |
| Piper synthesis | `REAL_TTS_ACCEPTANCE_PENDING_EXTERNAL_ENVIRONMENT` |
| Faster-Whisper transcription | `REAL_STT_ACCEPTANCE_PENDING_EXTERNAL_ENVIRONMENT` |
| GPU telemetry/resource validation | `REAL_RESOURCE_ACCEPTANCE_PENDING_EXTERNAL_ENVIRONMENT` |
| Native desktop GUI | `NATIVE_GUI_ACCEPTANCE_PENDING_EXTERNAL_ENVIRONMENT` |
| Physical microphone/speaker | `PHYSICAL_AUDIO_ACCEPTANCE_PENDING_EXTERNAL_ENVIRONMENT` |
| Complete local voice loop | `REAL_LOCAL_VOICE_LOOP_PENDING_EXTERNAL_ENVIRONMENT` |

The Ollama and memory checks used a disposable acceptance identity and a public local model. No private deployment configuration or user data was copied into this repository. The remaining checks require a host exposing the corresponding production runtime or physical devices.

## Repeating real checks

Configure runtime-only service definitions, then run:

```bash
PYTHONPATH=. python3 installer/backend_entry.py validate-chat --agent Billy
```

Real Piper, Faster-Whisper, microphone, and native GUI validation should be performed on the target desktop/worker host. Preserve the distinction between `ARCHITECTURE_TEST_PASS` and real-provider acceptance statuses.
