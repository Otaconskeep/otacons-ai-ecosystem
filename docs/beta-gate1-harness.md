# Beta Gate 1 acceptance harness

Run these commands from a checkout of the same public commit on the target machines. Reports contain no URLs, hostnames, usernames, credentials, recordings, or private paths.

## Server/GPU machine

Configure production-only runtime services outside Git, then run:

```bash
PYTHONPATH=. python3 installer/backend_entry.py acceptance-gate1 --server --output otacon-gate1-server.json
```

The server operator should set the report statuses only after real Ollama, memory, Piper, Faster-Whisper, NVIDIA telemetry, arbiter lease, and server voice-chain checks pass. Test providers do not qualify as real passes.

## Desktop/audio machine

Install and launch the packaged native application, complete the physical GUI/microphone/speaker checks, then run:

```bash
PYTHONPATH=. python3 installer/backend_entry.py acceptance-gate1 --desktop \
  --confirm NATIVE_GUI_ACCEPTANCE_PASS \
  --confirm PHYSICAL_MICROPHONE_ACCEPTANCE_PASS \
  --confirm PHYSICAL_SPEAKER_ACCEPTANCE_PASS \
  --confirm REAL_LOCAL_VOICE_LOOP_PASS \
  --output otacon-gate1-desktop.json
```

Human confirmations are recorded as booleans and are converted to PASS only for the explicitly named checks. The desktop report must use the same app version and Git commit as the server report.

## Aggregate

```bash
PYTHONPATH=. python3 installer/backend_entry.py acceptance-gate1 \
  --merge otacon-gate1-server.json otacon-gate1-desktop.json \
  --output otacon-gate1-aggregate.json
```

Gate 1 is PASS only when every required status is PASS. A mismatched app version or commit is rejected. Reports are disposable acceptance artifacts and should remain outside Git.
