# Otacon

Clean public foundation for a hardware-aware local AI setup wizard with provider-neutral Chat and TTS.

## Run the development wizard

```bash
TMPDIR=/mnt/data/tmp PYTHONPATH=. python3 -m installer.server
```

Open http://127.0.0.1:8787. Runtime configuration and TTS audio cache are written outside this repository.

## Validate voice (sandbox)

```bash
PYTHONPATH=. python3 -m installer.backend_entry validate-voice --agent Billy
```

Expected in sandbox: `TEST_TTS_PASS` and `REAL_TTS_ACCEPTANCE_PENDING`.

## Real Piper / Wyoming acceptance

When a Piper Wyoming endpoint is reachable (endpoint comes from env/config — never hardcoded in AgentService):

```bash
OTACON_TTS_PROVIDER=piper \
OTACON_TTS_ENDPOINT=wyoming://<host>:<port> \
OTACON_VOICE_ID=en_US-lessac-medium \
PYTHONPATH=. python3 -m installer.backend_entry validate-voice --agent Billy --real
```

If the environment blocks the endpoint, treat as:

`REAL_TTS_ACCEPTANCE_PENDING_EXTERNAL_ENVIRONMENT`

## Tests

```bash
PYTHONPATH=. python3 -m unittest discover -s tests -v
```

## Licensing note

Catalog entries `voice_001` / `voice_002` are **TEST FIXTURES**, not redistributable production Piper voices. Public Piper catalog entries carry upstream license/source metadata. Do not commit private trained voices or datasets.
