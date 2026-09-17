# Otacon Expansion

**Status: foundation layer real and one-command installable (schema,
formulas, validated default roster). The product itself — Dashboard,
Codec, War Room, Video Studio, and the rest — is specification complete,
not yet built. Not yet available to purchase.**

This document is the engineering contract for Otacon Expansion — the
premium, licensed multi-agent/emotional/orchestration layer that installs
on top of the free Otacon Core. It exists so the direction is public before
the full build is, in keeping with this project's policy of not shipping
marketing claims ahead of working software (see the [status
table](https://github.com/Otaconskeep/otacons-ai-ecosystem#readme) in the
main README) — and so far as the foundation layer goes, that policy is why
it ships as real, tested code and a real installer rather than a promise.
See *Install the foundation layer today*, below.

Companion page: https://otaconskeep.github.io/expansion/

## The commercial boundary

- **Otacon Core** — free, open source, self-hosted. No license key, no
  artificial limit, today or ever.
- **Otacon Expansion** — the premium multi-agent/emotional/orchestration
  layer. The *only* paid component in this entire system is the Expansion
  license itself.
- No functionality inside Expansion depends on a paid API. Every model —
  the LLM, Piper voices, Z-Image, LTX 2.3/2.5, music generation — runs
  locally on the user's own hardware. Every optional integration (Discord,
  Home Assistant, n8n) authenticates with credentials the installing user
  generates and stores themselves, never against Otaconskeep's own
  accounts or infrastructure.
- The developer's private Metal Gear Solid / Overlord / Date A Live–named
  roster (Mei Ling, Otacon, Solid Snake, Albedo, Kurumi, and the rest) is
  licensed third-party IP and will never ship as part of the public
  product. Expansion's defaults are five original characters: **Aria,
  Vector, Ledger, Muse, Sentry**.
- Personal infrastructure — the developer's Plex/Sonarr/Radarr stack, NAS
  layout, private IPs, file paths, credentials, account names, household
  topology — does not leak into the distributed product. Generic,
  user-supplied integrations are used instead where one makes sense.

## The five default agents

One coordinator, four domain specialists, each owning a real operational
room rather than being a tab in a generic chat UI:

| Agent | Role | Reports to | Room | Voice |
|---|---|---|---|---|
| **Aria** | Command Coordinator | — (rank 1) | Dashboard + Codec | `en_US-amy-medium` (f) |
| **Vector** | Systems & Infrastructure | Aria | War Room | `en_US-bryce-medium` (m) |
| **Ledger** | Data & Continuity | Aria | Intel Board | `en_US-joe-medium` (m) |
| **Muse** | Creative & Media Curation | Aria | Video Studio | `en_US-hfc_female-medium` (f) |
| **Sentry** | Security & Operations | Aria | Home Automation | `en_US-hfc_male-medium` (m) |

REX Board and the Dossier/Journal system stay Keep-wide rather than
single-owner — every agent files into REX, every agent gets a dossier.

Beyond the five defaults, the installer's agent-creation wizard hands
drafting to the user's already-installed local model (the one Core already
pulled), validated against the same canonical schema as the defaults —
never trusted as raw, unvalidated output. See *Canonical agent schema*
below.

## Canonical agent schema

A first implementation slice of this ships in this repo today, at
[`expansion/`](../expansion/), with a full test suite in
[`tests/test_expansion_*.py`](../tests/) (50 tests, all passing against
this repo's existing `pytest` setup as of this write-up):

- **`expansion/schema.py`** — the versioned `Agent` dataclass
  (`schema_version`, stable `agent_id`, `display_name`, `persona`, `role`,
  `domain`, `archetype`, `reporting_to`, `authority_rank`, `presentation`,
  `voice`, `room`, capabilities/integrations, emotional/relationship
  defaults, `motion_manifest`, timestamps) plus `validate_agent()`. Identity
  and role are deliberately separate: `agent_id` is the stable, immutable
  key; `display_name` can be renamed freely without touching hierarchy,
  authority, or room ownership. A display name is never used as a lookup
  key.
- **`expansion/hierarchy.py`** — cycle detection (`find_cycle`,
  `assert_acyclic`) over the `reporting_to` graph, and `reassign_orphans()`
  so deleting an agent never leaves a subordinate pointing at a dead ID.
- **`expansion/relationship.py`** — bounded, pure-function relationship and
  mood scoring. `trust`/`irritation` are always clamped to `[0, 1]`; no
  single event, however large, can push a relationship permanently out of
  recovery range. Irritation decays on a ~6-hour half-life, trust on a
  ~30-day half-life — a relationship doesn't forget years of trust because
  a day passed, but a flash of irritation fades well before that. A newly
  created agent's relationship to an existing one starts as
  `EvidenceType.INFERRED_BASELINE` — "no direct history yet, secondhand
  impression only" — modeled explicitly, never presented as a historical
  fact. `classify_affect()` and `explain()` are the same function used both
  to render UI state and to answer "why does the system believe this" —
  there is no second, separate explanation path generated after the fact.
- **`expansion/motion_manifest.py`** — a strict schema that makes a real,
  already-hit bug structurally impossible: a manifest candidate list handed
  to JavaScript's `fetch()` as a bare array silently comma-joins into a
  broken URL (this broke one agent's motion in the private Keep while every
  other agent kept working — the array happened to be single-element for
  the agents that still worked, masking the bug). `validate_manifest()`
  rejects any state whose `candidates` isn't a `tuple`;
  `resolve_candidates_for_frontend()` is the only sanctioned path to hand
  URLs to the frontend, and always returns a flat `list[str]`. Also encodes
  progressive motion-capability fallback (`CapabilityLevel` 0–3: static
  portrait → portrait+talking → idle/talking/thinking → full emotional
  pack) so an agent stays functional even when full motion generation
  isn't available.
- **`expansion/decision_audit.py`** — the record type behind the War
  Room's decision queue: session, input, classified intent/domain,
  selected owner, candidate agents, confidence (validated to `[0, 1]`),
  relevant memory IDs, relationship/emotional influence, tools
  considered/called, outcome, latency. This is what makes "why did Vector
  answer instead of Sentry" diagnosable from a record instead of a re-ask.
- **`expansion/readiness.py`** — machine-readable readiness state
  (`READY` / `LIMITED` / `NOT_CONFIGURED` / `OFFLINE` / `DEGRADED` /
  `UNAVAILABLE` / `FAILED`) per component. Required components
  (`CORE`, `AGENTS`, `VOICE`, `EMOTIONAL_ENGINE`, `RELATIONSHIPS`) gate
  "the Dashboard is healthy"; optional ones (`MOTION`, `VIDEO_STUDIO`,
  `DISCORD`, `HOME_ASSISTANT`, `N8N`, `INFRA_DASHBOARD`) never do — one
  optional subsystem being down must never make the rest look broken.
- **`expansion/seed_defaults.py`** — builds Aria/Vector/Ledger/Muse/Sentry
  through the schema above, validates each individually and the reporting
  hierarchy as a whole, and writes them to disk as JSON. Idempotent:
  `created_at` is preserved across reruns, only `updated_at` moves forward.

## Install the foundation layer today

This is real, and it's one command — but read the fine print. It installs
and verifies the schema/formula/roster layer above; it does **not** install
a Dashboard, Codec, War Room, Video Studio, or any UI wired to that roster.
Requires Otacon Core already installed (Expansion is never standalone):

```bash
curl -fsSL https://raw.githubusercontent.com/Otaconskeep/otacons-ai-ecosystem/main/install_otacon_expansion.sh | bash
```

What it does, end to end, verified working against a real clone of this
repo: confirms Core is installed, fast-forwards the same repository Core
already cloned, reuses Core's Python environment, runs the `expansion/`
test suite (50 tests) as a real acceptance gate, and generates + validates
the five default agents, writing them to
`~/.config/otacon/expansion/agents/`. Rerunning it is safe — the test
suite and roster are re-validated, and each agent's `created_at` is
preserved rather than reset. Exit codes: `0` = foundation ready, `2` =
roster written but the test suite didn't fully pass, `1` = failed (most
commonly: Core isn't installed yet, or `OTACON_INSTALL_DIR` doesn't match
where you installed it).

This is a first slice, not the whole system. Still to design and build as
concrete, testable modules on top of this foundation: the provisioning
transaction (below), migrations, the installer state machine, secrets
storage, licensing, GPU/ComfyUI capability detection and a pinned
dependency manifest, resumable/verified model downloads, and the full
acceptance-test suite described in the engineering contract this repo is
tracking toward.

## Agent creation is one transaction

Creating an agent — default or user-made — is not a row in a roster. A
successfully created agent must be fully provisioned:

1. roster/entity registration
2. unique, stable agent ID
3. persona/system-prompt storage
4. role/domain assignment
5. reporting hierarchy placement
6. greeting fast-path registration
7. voice binding (verified `.onnx` + `.onnx.json`, not just a filename)
8. avatar/motion manifest (validated against the schema above)
9. emotional-state initialization
10. relationship-graph initialization (`INFERRED_BASELINE`, see above)
11. dossier initialization
12. journal/state-history initialization
13. room/workspace ownership
14. Discord routing, if configured
15. decision-routing/domain registration, where applicable

Treated as one logical transaction. If step 9 fails after 1–8 succeed, the
agent is either cleanly rolled back or its provisioning state is marked
explicitly and safely resumable — never left in a state where the
Dashboard lists an agent Codec can't actually use.

## What ships

All ten of these already exist and run in the private Keep today. Shipping
them here is a UI/branding pass and a generalization effort — stripping
fixed IPs, personal file paths, and hardcoded personas — not new
invention: **Dashboard, Codec, REX Board, Intel Board, Voice Trainer
board, Automatic Dossier & Journal, Emotional State Matrix, War Room,
Video Studio, Infra Dashboard.**

War Room and the Infra Dashboard are deliberately not merged, despite both
carrying operational telemetry — they answer different questions. War Room
is scoped to the agent system: is an agent's reasoning behaving, are
alerts firing, is the decision queue backing up. The Infra Dashboard is
the machine underneath: host CPU/RAM/storage, container health.

## Video Studio — free, local, self-hosted, no paid API

- **Images — Z-Image.** Identity-preserving image-to-image generation.
- **Video — LTX 2.3 / 2.5.** Text-to-video and image-to-video, a two-pass
  draft-then-refine pipeline, plus start/end-frame interpolation.
- **Music.** Local generation, same job queue and UI.
- **Actors, styles, scripts.** A persistent library and a movie-project
  planner.

Everything above runs on open-weight models on the user's own GPU through
ComfyUI. This is deliberate: the Keep's Workshop also has an `H3` video
path (an external paid API tied to one account), and it is **not** part of
Expansion — every user would need their own account and key for it, which
breaks the "no paid API, ever" commitment above. LTX and Z-Image already
cover text-to-video, image-to-video, and refinement without it.

Video Studio has a real hardware floor (a GPU capable of running Z-Image
and LTX locally) and is the one surface expected to report `LIMITED` or
`UNAVAILABLE` in the readiness state on underpowered hardware — the rest
of Expansion stays usable when it does.

## Integrations — all optional, all user-owned credentials

| Integration | What it needs | Required? |
|---|---|---|
| Discord — outbound alerts (webhook) | A webhook URL the user generates | Optional |
| Discord — two-way bot | A bot token from the user's own Discord application | Optional |
| Home Assistant | The user's instance URL + a long-lived access token | Optional, offline-safe |
| n8n workflow layer | Bundled, pre-configured with a starter workflow | Included |
| Infra Dashboard | Bundled, pre-populated with Expansion's own containers | Included |

Home Assistant integration is offline-safe by construction — a smart-home
hub being powered down is routine, not exceptional, and every call
degrades to "Home Assistant is offline" rather than failing the agent
that asked. The same philosophy applies system-wide: Discord down still
means Codec works, ComfyUI down still means conversation works, n8n down
still means the Dashboard works. One optional subsystem going down must
never take the rest of the Keep with it.

## Installer status — Otacon Core, tested 2026-09-15

The Expansion is expected to ship through the same installer pipeline
Core already uses. Current status of that pipeline, from a real Windows
test pass:

**Verified — first install phase.** The installer, downloaded and
launched from this site's `/downloads/` path (not a raw GitHub Save-As),
handled a genuinely hostile real-world filename/path
(`Test User\Downloads\OtaconsKeep-Setup (1).bat`), elevated to admin
correctly, ran through to 100.0% completion, reported successful
operations, and correctly requested a reboot when WSL2 needed one.

**Not yet fully proven — post-reboot completion.** The full
"installed and usable after reboot" pass hasn't been independently
confirmed end-to-end. This is a **test-infrastructure limitation, not a
known product defect**: the automated Windows lab runs guests with nested
virtualization disabled by default (`dockurr`'s default `VMX=N`, a safety
default against a known guest-crash class). Otacon's setup needs WSL2,
which needs nested virt, so the lab guest hung at the Windows boot screen
after the WSL-enable reboot. The lab config
(`/mnt/data/otacon-installer-lab/windows/docker-compose.yml`) has since
been corrected (`VMX: "Y"`), but a corrected lab is not yet a green,
repeatable release-gate result on its own.

Classification: **Windows E2E blocked by test infrastructure, not
failed, and not a product defect.** Packaging, site delivery, hostile-path
handling, and GPU-skip semantics remain green. Release-gate criterion
before this is called fully proven: the same download → hostile-path →
double-click → WSL → reboot → resume → Core-ready → health-check sequence,
green on real Windows 11 hardware or a VM with genuinely proven nested
virtualization — the corrected lab can keep testing in the meantime, but
it is not the release authority until that matrix is green on proper
infrastructure.

## What's next

This document and the `expansion/` package are a foundation, not a
finished product. In rough sequence:

1. Migrations + versioning across every persisted shape (agents, personas,
   emotional state, relationships, journals, dossiers, integrations,
   motion manifests, voice bindings) — version-tagged, backed up before any
   destructive migration, never silently discarding unknown data.
2. The installer state machine (not installed → installing → installed →
   configured → healthy → degraded → failed → upgrade required), idempotent
   by construction — reruns must never duplicate agents, overwrite custom
   personas, destroy trained voices, or reset relationship/emotional
   history.
3. Secrets handling as a first-class concern: never in source, committed
   JSON, `localStorage`, frontend bundles, logs, or telemetry; frontend
   APIs return `configured: true`, never the credential itself.
4. Licensing that fails gracefully — an unreachable license server must
   never make a user's local install stop working or delete Expansion
   data; Core keeps running regardless.
5. Real GPU/ComfyUI capability detection (vendor, VRAM, driver, CUDA
   compatibility, disk/RAM) and a pinned dependency manifest for ComfyUI
   provisioning — exact repos, revisions, model files, and checksums, not
   "latest."
6. The full acceptance-test suite: every agent opens in Codec, every
   greeting fast-path works, every stock voice actually synthesizes audio,
   emotional-state/relationship/dossier/journal endpoints all answer, and
   "Installation complete" is never shown before this suite passes or
   returns an explicit degraded state.

Contributions and review welcome — see [CONTRIBUTING.md](../CONTRIBUTING.md).

---

*Designed & Engineered by Antonio G. Garcia.*
