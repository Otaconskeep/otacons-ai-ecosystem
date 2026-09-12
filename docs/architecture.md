# Foundation architecture

The core detects normalized hardware without exposing CUDA IDs, assigns logical GPU roles by capability, builds data-driven agents, and writes runtime configuration outside the repository.

## Capability routing

Chat and TTS share the same deployment-graph pattern:

1. Register a `Service` with capabilities (`conversational_llm` or `text_to_speech`)
2. Resolve via `core.router.resolve(deployment, capability)`
3. Hand the assignment endpoint/metadata to a provider (`OllamaProvider` / `PiperProvider` / test doubles)

Agent logic never hardcodes host addresses, Wyoming ports, or container names.

## TTS path (Milestone 6)

Agent text → VoiceProfile → `text_to_speech` → TTS service → PiperProvider → Wyoming transport → audio cache → UI playback.

Voice Preview and production speech both call `synthesize_voice(...)`.

Synthesis precedence (permanent):

1. explicit per-voice production override
2. VoiceProfile.synthesis
3. TTS service defaults
4. provider built-in defaults

## External Piper acceptance

Sandbox `validate-voice` uses TestTTSProvider and reports `TEST_TTS_PASS` / `REAL_TTS_ACCEPTANCE_PENDING`.

Where Piper/Wyoming is reachable:

```bash
OTACON_TTS_PROVIDER=piper \
OTACON_TTS_ENDPOINT=wyoming://<host>:<port> \
OTACON_VOICE_ID=en_US-lessac-medium \
PYTHONPATH=. python3 -m installer.backend_entry validate-voice --agent Billy --real
```

Pending marker when the environment cannot reach the endpoint:

`REAL_TTS_ACCEPTANCE_PENDING_EXTERNAL_ENVIRONMENT`
