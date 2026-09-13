# Otacon

**A local-first platform for building persistent, voice-enabled AI agents.**

**Designed & Engineered by Antonio Garcia (Otaconskeep)**

**💬 Join the community: [discord.gg/cZDeqECzX](https://discord.gg/cZDeqECzX)**

> **Otacon Core**
>
> This repository is **Otacon Core**: free, full source, self-hosted. Antonio Garcia's private **Otacon Keep** is the larger reference deployment this project is built from; see [Otacon Core, the Keep Blueprint, and Otaconskeep Services](#otacon-core-the-keep-blueprint-and-otaconskeep-services) below for how the pieces relate.

## Install Otacon Core (no experience required)

**You do not need to know Linux, Python, Docker, Rust, or WSL to do this.**
Pick your OS:

### Windows

1. Download [`install_otacon.bat`](install_otacon.bat) (right-click →
   Save Link As, or clone the repo).
2. Double-click it.

That's it. It checks whether WSL2 and an Ubuntu environment are already set
up; if not, it sets them up for you, walks you through the one unavoidable
manual step (a Windows restart and/or a one-time Ubuntu username/password,
which is Microsoft's own requirement, not something any script can skip),
then automatically continues and finishes the real install the moment
that's done. You do not need to know what WSL or Ubuntu even are.

**Install once, and Otacon starts itself from then on.** The installer sets
Otacon up as a real background service and adds a small Windows task that
wakes it at logon, so after that first install: shut your PC down, turn it
back on tomorrow, sign in, and open `http://localhost:5757`: Otacon is
already running. No terminal, no "start the server," nothing to remember.

### Linux (Ubuntu 22.04/24.04, or already inside WSL)

Copy the block below exactly, paste it into a terminal, and press Enter:

```bash
curl -fsSL https://raw.githubusercontent.com/Otaconskeep/otacons-ai-ecosystem/main/install_otacon.sh | bash
```

**Supported OS:** Ubuntu 22.04/24.04 supported. Debian 12 supported if verified.
Linux Mint / Pop!_OS best-effort. Older releases are unsupported unless you set
`OTACON_ALLOW_UNSUPPORTED_OS=1` (Core web-only may still work).

**New to terminals? Here's the whole thing, step by step:**

1. Open a terminal. (On Ubuntu Desktop: press the `Super`/Windows key, type
   `terminal`, press Enter. On a server you're already SSH'd into, you're
   already there.)
2. Click into the black window, then paste the command above (right-click →
   Paste, or `Ctrl+Shift+V`).
3. Press Enter.
4. Wait. The first run takes 10-30 minutes: it's installing everything
   needed (Python, build tools, Rust, and Otacon itself) and building the
   app for your machine. It will ask for your password once, to install a
   few system packages (this is normal; that's what `sudo` is for).
5. When it finishes, it prints a web address (`http://127.0.0.1:5757`) and
   tries to open it in your browser automatically. If it doesn't open on
   its own, copy that address into your browser yourself.

That's the entire Otacon install. Default profile is **CORE**
(`OTACON_PROFILE=core`, `OTACON_BUILD_NATIVE=0`): it detects your GPU (if
NVIDIA), installs Ollama, pulls a default chat model sized to your VRAM
(`qwen2.5:1.5b` / `3b` / `7b` / `14b`), installs Genome Voice Trainer when
possible, runs self-tests, and registers `otacon.service` to start on boot.
Desktop/native `.deb` packaging is opt-in via `OTACON_PROFILE=desktop` or
`OTACON_BUILD_NATIVE=1`. When it finishes, open Otacon and chat.

Installer final states: **READY** (exit 0), **DEGRADED** (exit 2 — core up,
optional component failed), **FAILED** (exit 1). Health check anytime:
`otacon doctor` (`~/.local/bin/otacon doctor`).

**Default bind is localhost only.** LAN access requires `OTACON_LAN_MODE=1`,
writes `~/.config/otacon/lan_token`, and requires
`Authorization: Bearer <token>` for API mutations/chat. Optional bind host:
`OTACON_CHAT_HOST` (defaults to `127.0.0.1`; becomes `0.0.0.0` when LAN is on).

Skip pieces if you want a lighter install:

```bash
OTACON_INSTALL_DEFAULT_MODEL=0 OTACON_INSTALL_VOICE_TRAINER=0 curl -fsSL \
  https://raw.githubusercontent.com/Otaconskeep/otacons-ai-ecosystem/main/install_otacon.sh | bash
```

Override the chat model tag with `OTACON_LLM_MODEL=qwen2.5:7b` if needed.

**Both paths are completely safe to run more than once.** If anything
interrupts it, or you just want to update later, run the same
`install_otacon.bat` / `install_otacon.sh` again: every step skips whatever's
already done, and neither one resets or deletes an existing install.

Prefer to download the script first and read it before running it (always a
reasonable thing to do with any installer)? Grab
[`install_otacon.sh`](install_otacon.sh) from this repo, then run:

```bash
chmod +x install_otacon.sh
./install_otacon.sh
```

### Windows/WSL manual path (only if the `.bat` doesn't work for you)

`install_otacon.bat` automates all of this, so you shouldn't normally need
it, but if you want to do it by hand or something goes wrong:

1. Open PowerShell **as Administrator**, run `wsl --install`, and restart
   if it asks you to.
2. Open the new **Ubuntu** app from your Start menu. The first time it
   opens, it asks you to create a username and password; type anything you
   want, it only matters inside that Ubuntu environment.
3. Run the Linux install command from the section above inside that Ubuntu
   window.

On a Mac, you'll need an Ubuntu VM (UTM, Parallels, VMware) or a real Linux
box; native macOS support isn't here yet.

**Optional settings** (set as environment variables before running, only if
you want to change the defaults):

| Variable | Default | What it changes |
|---|---|---|
| `OTACON_INSTALL_DIR` | `~/otacon-ai-ecosystem` | Where Otacon gets installed |
| `OTACON_PROFILE` | `core` | `core` (default) or `desktop` (enables native `.deb` build) |
| `OTACON_BUILD_NATIVE` | `0` | Default 0 for CORE; set `1` (or `OTACON_PROFILE=desktop`) to build the native `.deb` |
| `OTACON_LAN_MODE` | `0` | Set `1` to bind for LAN; writes `~/.config/otacon/lan_token` and requires Bearer auth |
| `OTACON_CHAT_HOST` | `127.0.0.1` | Bind host; overridden to `0.0.0.0` when LAN mode=1 |
| `OTACON_INSTALL_DEB` | `0` | Set to `1` to also install the built `.deb` automatically |
| `OTACON_LAUNCH_WIZARD` | `1` | Set to `0` to skip auto-launching the web UI at the end |
| `OTACON_RUN_TESTS` | `1` | Set to `0` to skip the self-test suite (faster, less safe) |
| `OTACON_ALLOW_UNSUPPORTED_OS` | `0` | Set `1` to continue on unsupported distros |

### How the always-on part actually works (Windows)

`install_otacon.bat` sets up two things beyond the base install, both purely
additive, neither touching your Ubuntu distro's identity or data:

- **Inside WSL**: a systemd service (`otacon.service`), enabled so it starts
  whenever that Linux environment boots, and restarts itself automatically
  if it ever crashes.
- **On Windows**: a logon task (`OtaconAutoStart`, visible in Task
  Scheduler) that quietly wakes your WSL environment right after you sign
  in, which in turn boots systemd and starts the already-enabled service.
  It never opens a terminal window and never opens your browser for you.

**Repair.** Something not starting right, or you skipped the auto-start
setup earlier? Just run `install_otacon.bat` again. It re-checks and
re-creates the systemd service and the logon task if either is missing,
without resetting your existing install, your agents, or your WSL distro.

**Uninstall auto-start only.** Run
[`uninstall_otacon.bat`](uninstall_otacon.bat). It removes the
`OtaconAutoStart` logon task and the `otacon.service` systemd unit only.
It does **not** remove binaries, your Ubuntu environment, your Otacon install
directory, your venv, or your data — only stops automatic start.

**Full uninstall is manual** (after disabling auto-start), for example in
Ubuntu/WSL:

```bash
systemctl disable --now otacon.service
sudo rm -f /etc/systemd/system/otacon.service
sudo systemctl daemon-reload
rm -rf ~/otacon-ai-ecosystem ~/.config/otacon ~/.local/share/otacon
rm -f ~/.local/bin/otacon
```

## Otacon Core, the Keep Blueprint, and Otaconskeep Services

| | **Otacon Core** (this repo) | **Keep Blueprint** | **Otaconskeep Services** |
|---|---|---|---|
| What it is | Free, open source, self-hosted | The broader ecosystem architecture demonstrated by Antonio's real Keep (agent rooms, media/home automation, remote GPU nodes, and more) | Architecture, deployment, and support engagements |
| Status | Install today, this repo | Direction the architecture is heading, not a public installer yet | Available now |
| Price | Free | Not offered publicly yet | Contact for scope/pricing |

There's no license key or artificial limit baked into Otacon Core. It's the
real, complete public platform as it stands today. **Otacon Core installs
the foundation. The Keep Blueprint shows what that foundation can become.**
Questions about any of the three, or want to talk deployment/consulting:

### 💬 [discord.gg/cZDeqECzX](https://discord.gg/cZDeqECzX)

## Public Edition vs. the Full Otacon Keep

This repository contains the public, portable edition of Otacon. It is based on the architecture and lessons learned from **Antonio Garcia's private Otacon Keep**, a significantly larger distributed AI environment used as the reference deployment for the project.

The private Keep includes capabilities and infrastructure that are not yet part of the public release. The goal of the public project is not to copy that deployment file-for-file. Capabilities are being rebuilt as safe, configurable, hardware-independent modules for other users to install on their own systems.

**The private Keep is the reference implementation. The public edition is the portable product.**

## The Full Reference Deployment

Antonio Garcia's private Otacon Keep is a distributed, multi-node AI environment rather than a single application on one computer. Conceptually it spans a primary compute host, a virtualization host, and a worker/offload VM, with multiple physical resources, Proxmox, virtual machines, Docker runtimes, GPU-backed workloads, persistent agents, local models, speech recognition, text-to-speech, resource arbitration, image and video generation, smart-home and messaging integrations, media integrations, automated health/recovery tooling, and backup/reporting infrastructure.

```text
              ANTONIO GARCIA'S OTACON KEEP
                         │
          ┌──────────────┼──────────────┐
          │              │              │
    Primary Host    Virtualization     Worker /
                        Host          Offload VM
          │              │              │
       Docker         Proxmox         Docker
          └──────────────┼──────────────┘
                         │
                 Capability Router
                         │
       LLM · STT · TTS · Image · Video
                         │
                   Agents / Memory
```

This is a conceptual, redacted representation. No private network identifiers or deployment state are included.

## What You Get in the Public Edition

The public repository contains the clean platform foundation: graphical installer, hardware discovery, deployment planning, agent creation, provider-neutral agent architecture, capability routing, persistent conversations, long-term memory, user and agent isolation, provider-neutral LLM and TTS interfaces, per-agent voices, per-voice synthesis profiles, voice preview/playback architecture, distributed topology/resource modeling, and public configuration/model/voice catalogs.

| Capability | Antonio's Private Keep | Public Otacon |
|---|---|---|
| Agent chat | Production | Implemented; external runtime validation pending |
| Persistent conversations | Production | Complete |
| Long-term memory | Production | Complete |
| Per-agent voices | Production | Complete |
| Piper TTS | Production | Architecture complete; external validation pending |
| Speech-to-text | Production | Architecture complete; real provider validation pending |
| Resource arbitration | Production | Architecture complete; real hardware validation pending |
| Image generation | Production reference | Public architecture complete; real provider validation pending |
| Video generation | Production reference | Public architecture complete; real provider validation pending |
| Remote compute nodes | Production reference | Pairing/registration architecture complete; multi-machine validation pending |
| Distributed compute | Production | Resource model complete; onboarding planned |
| GPU/resource arbitration | Production | Planned |
| Image/video generation | Production | Planned |
| Smart-home, messaging, and media integrations | Production | Planned |
| Recovery, updates, and backup workflows | Private tooling | Planned |
| Public installer | Evolved manually | Primary public goal |

## Why Isn't Everything From the Keep Here?

The private Otacon Keep evolved as a real working AI environment with infrastructure specific to Antonio Garcia's hardware, network, services, agents, and workflows. Publishing it directly would expose private configuration and produce software that would be difficult for anyone else to install.

The public version therefore extracts the architecture, removes machine-specific assumptions, replaces private addresses and service names with logical resources, separates secrets and runtime state from source code, and adds capabilities behind stable provider interfaces one at a time. The public version may temporarily have fewer capabilities, while remaining a real portable platform.

**Capabilities proven in the private Keep are being generalized and migrated into the public edition over time.**

## From the Keep to the Public Edition

Public foundation ✅  · Chat ✅  · Persistent memory ✅  · Voice output ✅ architecture  · Speech input → next  · Wake word, resource arbitration, remote nodes, image/video, integrations, and operations tooling → later.

Many roadmap items are demonstrated capabilities in the private reference deployment; they are being redesigned for safe public distribution rather than copied with private state.

The public deployment model understands:

```text
Physical Host → VM → Container Runtime → Service → Capability
```

This allows a future installation on one computer to pair another computer and route workloads to its resources without changing agent identity.

The reference voice system also demonstrated that each voice needs its own validated synthesis profile. Public Otacon therefore treats synthesis settings as per-voice configuration instead of applying one global profile to every voice.

Otacon was designed and engineered by Antonio Garcia, based on architecture developed and operated in his private Otacon Keep reference environment.

Otacon is intended to feel like consumer software: download, install, detect hardware, configure an agent, choose capabilities, and start talking without learning Docker, CUDA, Python environments, YAML, or model-server plumbing.

## Current status

| Capability | Status |
|---|---|
| Native installer foundation, hardware planning, agent architecture | Complete |
| Capability routing, persistent conversations, long-term memory | Complete |
| Provider-neutral LLM/TTS, per-agent voices, synthesis profiles | Complete |
| Ollama + VRAM-tier default chat model | Included with Otacon (skip: `OTACON_INSTALL_DEFAULT_MODEL=0`) |
| Genome Voice Trainer (GPU Piper) | Included with Otacon (skip: `OTACON_INSTALL_VOICE_TRAINER=0`) |
| Real Piper / STT / image acceptance | Pending external validation |
| Speech-to-text and microphone | Next milestone |
| Image/video generation and remote-node onboarding | Planned |

## Architecture

```text
User → Agent (identity, memory, voice, preferences)
     → Capability Router → Deployment Services
       → conversational_llm / text_to_speech → Providers / Compute
```

Otacon: Designed & Engineered by Antonio Garcia

## Resource arbitration

Milestone 8 adds a provider-neutral resource arbiter beneath capability routing. Workloads request logical CPU, RAM, GPU, or VRAM resources and receive leases that respect placement, runtime exposure, priority, and health. Idle model residency can be reclaimed gracefully; active non-preemptible work is protected. This supports bare metal, virtual machines, containers, and future remote workers without making agents aware of device indexes or network addresses.

Validate the architecture without launching heavy workloads:

```bash
PYTHONPATH=. python3 installer/backend_entry.py validate-resources
PYTHONPATH=. python3 installer/backend_entry.py validate-arbiter
```

Real hardware telemetry remains `REAL_RESOURCE_ACCEPTANCE_PENDING_EXTERNAL_ENVIRONMENT` where the execution environment cannot expose accelerators.

## Voice satellites

The final planned feature milestone adds a provider-neutral VoiceSatellite boundary: local wake detection gates transient capture, then the existing STT → Agent Conversation → Memory/LLM → TTS path is reused. Satellites have explicit trust, mute, heartbeat, and assigned-agent state; they do not contain a separate assistant brain. Physical microphone, wake-word, and speaker validation remains `REAL_SATELLITE_ACCEPTANCE_PENDING_EXTERNAL_ENVIRONMENT`.

## Lifecycle and beta readiness

Public Otacon includes versioned state migration, manifest-based backup/restore, update checksum and package identity verification, diagnostics redaction, safe uninstall semantics, repair/install validation, and persistent node registry support. `beta-readiness` reports warnings rather than claiming readiness while real provider, native service, TLS, and multi-machine acceptance remain pending.

## Integrations

Otacon uses provider-neutral integration adapters for optional smart-home, messaging, media, notifications, and configured webhooks. Actions are permission-checked, distinguish reads from writes, and can require explicit confirmation. Secrets remain referenced outside source control, and arbitrary agent-generated URLs or shell commands are not allowed. Deterministic validation passes; real external integrations remain `REAL_INTEGRATION_ACCEPTANCE_PENDING_EXTERNAL_ENVIRONMENT`.

## Remote compute nodes

Public Otacon can represent trusted worker nodes with stable logical identities, explicit single-use pairing codes, revocation, heartbeats, resource and service advertisements, and structured workload dispatch. Nodes report CPU, RAM, GPU, storage, runtimes, and capabilities into the same topology, router, and resource arbiter used locally. Runtime communication is designed around authenticated Otacon APIs rather than arbitrary remote shell access. Deterministic validation passes; real multi-machine operation remains `REAL_DISTRIBUTED_ACCEPTANCE_PENDING_EXTERNAL_ENVIRONMENT`.

## Video production

The public `video_generation` capability uses a provider-neutral `VideoProductionManager` with Draft, Normal, and Final profiles (640×352, 864×480, and 1344×768 reference resolutions). Provider adapters translate those intents into compatible execution plans, including accelerated-path fallback, while the resource arbiter protects active workloads and releases leases. Generated video artifacts stay in runtime storage outside Git. Run `validate-video` for the deterministic architecture check; real model execution remains `REAL_VIDEO_ACCEPTANCE_PENDING_EXTERNAL_ENVIRONMENT`.

## Image generation

Public Otacon provides an `image_generation` capability, quality profiles (Draft, Standard, Quality), an arbiter-backed `ImageProductionManager`, provider-neutral artifacts, and a deterministic test provider. Generated files live in the application data directory outside the repository. A production image service is intentionally configured separately; deterministic fixtures never silently replace it. Run `validate-image` for the architecture check. Real provider/model execution remains `REAL_IMAGE_ACCEPTANCE_PENDING_EXTERNAL_ENVIRONMENT`.

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

When a Piper Wyoming endpoint is reachable (endpoint comes from env/config, never hardcoded in AgentService):

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

## Support

Installer issue, a question about self-hosting on your own hardware, or
interested in the Keep Blueprint / Otaconskeep Services? One channel covers
all of it:

### 💬 [discord.gg/cZDeqECzX](https://discord.gg/cZDeqECzX)

When reporting an install problem, include your OS/distro, the exact error
text, and whether it happened during `install_otacon.sh` or after launch.
That's usually enough to triage quickly.

## About the Engineer

**Antonio G. Garcia ("Otaconskeep")** designs and engineers distributed,
local-first AI systems: the kind of infrastructure most teams either buy
as a SaaS subscription or never build at all. Otacon's architecture reflects
that: a provider-neutral capability router that treats LLM/TTS/STT backends
as swappable resources rather than hardcoded vendors, a resource arbiter
that leases CPU/RAM/GPU/VRAM across bare metal, VMs, and remote nodes without
agents ever touching a device index, per-agent voice profiles instead of one
global synthesis setting, and a native installer/updater with versioned
state migration and manifest-based backup. It's the unglamorous plumbing
that decides whether a platform survives contact with someone else's
hardware.

This public repository is the portable edition of a larger private
reference deployment (the "Otacon Keep") spanning multiple physical hosts,
Proxmox virtualization, and GPU-backed workloads in production use.

Available for consulting on local-first AI architecture, resource
orchestration, and voice-agent systems. Reach out in Discord above.

## License

Apache-2.0. Copyright © 2026 Antonio Garcia.

## Licensing note

Catalog entries `voice_001` / `voice_002` are **TEST FIXTURES**, not redistributable production Piper voices. Public Piper catalog entries carry upstream license/source metadata. Do not commit private trained voices or datasets.
