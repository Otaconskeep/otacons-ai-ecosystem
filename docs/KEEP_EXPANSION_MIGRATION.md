# Keep Expansion — Current → Target Migration Matrix

**Status:** P0 baseline (accepted audit + locked product decisions)  
**Source of truth:** Public Expansion schema in this repository  
**Behavior reference:** Private Keep at `/opt/otacon` (never shipped)  
**Rule:** Clean-room ports guided by observed behavior and tests. Do not copy
`otacon-executor.py`, third-party-IP modules, private LAN topology, credentials,
household/medical/financial data, or private agent canon names/lore.

---

## Product boundary (locked)

```text
Otacon Core          free base/runtime
Keep Expansion       paid persistent-agent environment
Hunter Pack          separate media product/repo (otaconskeep-media)
Future packs         Home, Monitoring, others — optional, separate
```

Hunter Pack remains separate. Do not fold media automation into Expansion.

---

## Repository landscape

| Tree | Role |
|---|---|
| `otacons-ai-ecosystem` (this repo) | Canonical public Core + Expansion product |
| Private Keep (`/opt/otacon`) | Behavior/reference only |
| `otaconskeep-site` | Marketing / downloads |
| `otaconskeep-media` | Hunter Pack candidate (Media Fabric) |
| `otacon-voice-trainer` | Genome (usually bundled with Core) |
| `AI9` | Sibling Windows GPU product |

---

## Installer architecture (current)

| Path | What it does |
|---|---|
| `install_otacon.sh` / `OtaconsKeep-Setup.bat` | Core → `~/otacon-ai-ecosystem`, config `~/.config/otacon`, UI `:5757` |
| Core gates | READY(0) / DEGRADED(2) / FAILED(1) |
| `install_otacon_expansion.sh` | Foundation: tests + seed roster under user state |
| Expansion gates | FOUNDATION READY / DEGRADED / FAILED |

A live port or HTTP 200 is **not** proof of a correct Expansion install.
Semantic health checks (see Readiness) are mandatory.

---

## Five public Expansion agents (locked)

Public-facing lore must be original Keep-universe lore. Behavioral
*architecture* may be inspired by private Keep agents; biographies must not
be renames of third-party canon.

| Agent | Role | Archetype | Behavioral inspiration (private Keep architecture only) | Room |
|---|---|---|---|---|
| **Aria** | Command coordinator | devoted / yandere-lite commander | Albedo architecture | Dashboard + Codec |
| **Vector** | Systems / operator | stoic / kuudere operator | Solid Snake architecture | War Room |
| **Ledger** | Records / intelligence / continuity | warm intellectual / support | Mei Ling architecture | Intel Board |
| **Muse** | Creative / media | tsundere creative | Kurumi architecture | Video Studio |
| **Sentry** | Security / awareness | quiet observer / dandere protector | Psycho Mantis architecture | Home Automation (+ Page Builder registry participation) |

Primary expressive triangle: **Aria / Muse / Ledger**. Vector is the stoic
counterweight; Sentry is the quiet pattern detector. Initial relationship
parameters + evolving events — never hardcoded static hatred/love.

---

## Page Builder (in Expansion)

Page Builder is a **premium Keep Expansion surface** (with Rooms / Studio /
Codec), not a future pack.

Requirements:

- Sanitize `page_builder_v2` patterns via clean-room port
- Allowlisted registry/schema only
- No arbitrary executable code injection
- No arbitrary JS/Python loading
- Pages register through the same room/page registry as Expansion UI

---

## Feature matrix (audit baseline)

| Capability | Private Keep | Public today | Target |
|---|---|---|---|
| Agents / personality | Mature IP roster | Schema + Aria–Sentry seed | Original lore + structured dossiers |
| Emotion | Multi-layer live | Formulas only | Full engine + provenance |
| Relationships | Dual engines | trust/irritation formulas | Directional multi-dimension + events |
| Memory | Fragmented stores | Core SQLite | Working / episodic / semantic / important |
| Journal / diary | Mature | Spec | Journal = objective events; Diary = subjective |
| Jobs / REX | Mature ops | `decision_audit` type | Expansion job store + War Room |
| Rooms / War Room | Cinematic floors | Room metadata | Navigable Expansion rooms |
| Codec | Full | Lite Aria preview | Multi-agent Codec |
| Video Studio | Full | Spec + Core stub | Local Z-Image/LTX/music (no paid H3) |
| Page Builder | Live | Absent | Expansion surface via registry |
| keep-gate | Demo | Absent | Optional / defer |

---

## Hardcoded private-env risks (do not ship)

| Class | Examples |
|---|---|
| LAN | `.219` / `.221` / HA `.192` / NAS `.69` / Echo / AI9 |
| Paths | `/opt/otacon`, `/mnt/pve/*`, lab `/mnt/data` assumptions as install proof |
| Operator | `Xof`, household automation |
| IP roster | Snake, Albedo, Kurumi, … |
| PII | Medical journal, finance, credentials |

Public hygiene: `/opt/otacon` must never be treated as proof of a public
Core/Expansion install.

---

## Canonical data model decisions (locked)

### Dossier (structured, not one prompt)

Every default agent supports structured fields for identity, background,
history, education/training, career, role, archetype, values, morals,
communication style, humor style; strengths / weaknesses / blind spots /
failure modes; fears / anxieties / insecurities / self-conscious traits /
shame points / secrets (where appropriate); crutches / coping mechanisms /
compulsions / bad habits / avoidance / addictive tendencies; attachment /
jealousy / possessiveness / trust / conflict / rivalry behavior; likes /
dislikes / interests / preferences; stress / recovery behavior; emotional
baseline; relationship tendencies; tool / room / role permissions.

### Vulnerability modeling (first-class)

Distinguish: weakness, crutch, compulsion, addictive tendency, fear,
anxiety, insecurity, self-conscious area, avoidance behavior. These
influence diary, relationships, emotional transitions, and conversation —
without making operational agents intentionally unreliable.

### Canonical vs living history

- **Canonical history** — vendor-defined pre-install background (product data)
- **Living history** — actual post-install events (user data)
- Never ship fake memories involving a new owner

### Canonical vs living dossier

- **Canonical dossier** — product, signed/versioned
- **Living dossier** — observed tendencies with evidence/provenance (user data)

### Journal vs diary

- **Journal** — objective event record; reconstructable from system events
- **Diary** — subjective interpretation from personality + emotion +
  relationships + memory + recent history; never fabricate user history

### Relationships (directional)

`Aria → Muse ≠ Muse → Aria`. Minimum dimensions: trust, affinity, respect,
familiarity, dependency, conflict, rivalry, jealousy, protectiveness,
reliability, attachment. Significant changes require event provenance.

### Emotional engine

Dimensions include at least: joy, sadness, anger, fear, stress, confidence,
curiosity, frustration, satisfaction, attachment, jealousy, insecurity,
concern, pride, loneliness. Flow:

```text
event → weights → personality modifiers → relationship modifiers
     → emotional state → decay/recovery → behavior context
```

### Traceability

Dynamic state must answer WHY (emotion, relationship, living-dossier,
memory importance, preferences, major shifts) via provenance references —
no unexplained personality mutation.

### Memory kinds

Working, episodic, semantic, important — with metadata (timestamp, source,
agent, entities, importance, confidence, event ref, relationship/emotion
impact). Not an infinitely growing prompt blob.

### Event bus (foundation)

Initial event types: `job.*`, `agent.selected`, `agent.message`,
`relationship.changed`, `emotion.changed`, `service.failed`,
`service.recovered`, `user.praised_agent`, `user.corrected_agent`,
`memory.created`, `journal.created`, `diary.created`. Consumers: memory,
emotion, relationships, journal, living dossier, UI, notifications.

### Product data vs user data

| Product data | User data |
|---|---|
| Signed, versioned, encrypted in production release, mostly immutable | Memories, journals, diaries, relationships, living dossier, jobs, preferences, owner config |
| Agent definitions, presets, emotional model config, premium assets | Lives under user state roots only |

Never store user-generated state inside the product bundle.

---

## Security / protected release (formal requirements)

- Protected materials (agent defs, prompts, personality profiles, relationship
  presets, emotional model config, premium orchestration, templates, assets,
  workflows) must not ship as convenient plaintext in production.
- Pipeline: private source → tests → compile/bundle → integration tests →
  obfuscate selective modules → strip debug metadata → package → compress →
  authenticated encryption (AES-256-GCM or XChaCha20-Poly1305) → sign →
  protected-release smoke test → publish. Test the **protected** artifact.
- Product bundle keys are independently random. Password-derived keys use
  salt + Argon2id when needed. Windows: DPAPI / OS key storage. Never
  hardcode plaintext package keys in BAT/PS1/Python/JS/config.
- Hybrid compile candidates (Nuitka/Cython/native): agent runtime, emotion,
  relationship, orchestration, protected-resource loader, entitlement —
  evaluate; do not blindly compile everything.
- Frontend production: bundle, minify, no source maps, no credentials, no
  private paths.
- Signed manifest authenticates runtime, protected modules, encrypted
  bundles, versions, hashes, schema. Tamper → fail safe + repair/reinstall.
  Never delete user data, damage the machine, kill unrelated processes, or
  use destructive anti-debugging.
- No uncontrolled mod path (`plugins/*.py`, `custom_system_prompt.txt`,
  `personality_override.json`, arbitrary JS/DLL loading) unless a safe
  extension system is designed later.

### Update architecture (mandatory from day one)

Track independently: **Core version**, **Expansion version**, **Schema version**.

Flow: fetch signed manifest → verify → download → verify hash/signature →
snapshot user state → stage → migrate → health checks → restart →
post-restart health → commit. Failure → rollback to previous known-good
package (+ schema snapshot if needed). User memories/relationships survive.
Never overwrite the sole working version in place.

---

## Current → target migration matrix

| # | Capability | Current | Target | Strategy | Preserve | Phase |
|---|---|---|---|---|---|---|
| 0 | Packaging boundary | Foundation installer | Licensed Expansion on Core | Extend expansion installer + protected package | Core Lite | P0 |
| 1 | Agent schema / roster | Public schema + seed | Aria–Sentry + structured dossiers | Public schema SoT; Keep = behavior oracle | `expansion/schema.py` + tests | P0→P1 |
| 2 | Hierarchy | Lib + tests | Live graph | Wire to user-state store | `hierarchy.py` | P0→P1 |
| 3 | Topology / config | Some lab probes | Env/config only | Abstract services; fix `/opt/otacon` probe | Core install paths | **P0** |
| 4 | Versions / manifest | `release.json` Core-ish | Core + Expansion + Schema + signed package manifest | New version + manifest modules | `release.json` | **P0** |
| 5 | Migrations | Spec | Versioned persisted shapes | Migration skeleton + registry | Existing agent JSON | **P0** |
| 6 | Product vs user state | Agents under `~/.config` | Explicit roots; product immutable | `state_layout` | Seed path compat | **P0** |
| 7 | Provision transaction | Seed only | 15-step tx stub | `provision.py` skeleton | Idempotent seed | **P0** |
| 8 | Readiness | Enum lib | Semantic Expansion health | Wire checks; required vs optional | Core READY gates | **P0** |
| 9 | Event bus | Absent | Common event model | `events.py` skeleton | — | **P0** |
| 10 | Dossier / vulnerability schemas | Spec | Structured models | Schema modules; content later | — | **P0** schema / P1 content |
| 11 | Personality runtime | Keep Hermes; Core thin | Per-agent runtime | Clean-room from Hermes patterns | Core `agent_service` | P1 |
| 12 | Emotion engine | Keep mature | Required component + Matrix | Clean-room formulas + provenance | Public affect helpers | P1 |
| 13 | Relationship engine | trust/irritation | Full directional dimensions | Extend compatibly; provenance | Existing relationship tests | P1 |
| 14 | Memory | Core SQLite | Layered memory kinds | Bridge + Expansion store | Core memory | P1–P2 |
| 15 | Codec multi-agent | Lite Aria | Roster-aware Codec | Evolve Lite; flag Expansion | Lite Codec | P1 |
| 16 | Dashboard | Lite Command Center | Expansion home + readiness | Additive tiles | Core tiles | P1 |
| 17 | Journal / diary | Keep mature | Objective / subjective split | Clean-room; event-reconstructable journal | — | P2 |
| 18 | Living dossier | Keep patterns | Evidence-backed observations | User-state only | — | P2 |
| 19 | War Room / REX / jobs | Keep mature | Decision queue + jobs | `decision_audit` + new store | — | P2 |
| 20 | Intel / specialty rooms | Keep IP floors | Aria–Sentry rooms | Shared work-room shell patterns | — | P2 |
| 21 | Page Builder | Keep live | Expansion registry surface | Sanitize; allowlist; no code injection | — | P2 |
| 22 | Licensing | Spec | Fail-open for local data | Gates Expansion surfaces only | Core free | P2 |
| 23 | Protected build / crypto | Spec | Signed encrypted release | Established AEAD only | Dev plaintext OK in tree | P2–P3 |
| 24 | Video Studio | Keep + Comfy | Local studio; readiness LIMITED | Pin Comfy; no H3 | Core `video.py` | P3 |
| 25 | HA / Discord / n8n / Infra | Keep wired | Optional user credentials | Offline-safe HA | — | P3 |
| 26 | keep-gate | Demo | Defer / optional shell | Configurable dest | — | Defer |
| 27 | Hunter Pack | Media scaffold | Separate product | No merge into Expansion | Expansion installer | Parallel |

---

## Phase plan

### P0 — Foundation (this document’s implementation gate)

Complete before visible Expansion UI work:

1. This migration document  
2. Topology/config abstraction  
3. `/opt/otacon` probe correction  
4. Version / schema model  
5. Migration skeleton  
6. Package manifest contract  
7. Product / user-state separation  
8. Provision transaction skeleton  
9. Readiness integration (semantic checks)  
10. Event model skeleton  
11. Dossier + vulnerability schema foundations  
12. Tests for all of the above  

**Do not begin P1 until P0 is green.**

### P1 — Runtime spine

Provision filled out; emotion + relationship stores; multi-agent Codec;
Dashboard tiles; voice/motion for defaults; acceptance suite slice.

### P2 — Command surfaces

War Room, REX/delegation, dossiers/journals living layer, Intel, Page
Builder, licensing fail-open, protected packaging start.

### P3 — Heavy / optional

Video Studio, HA/Discord/n8n, Infra Dashboard, full protected release pipeline.

---

## Non-negotiables

1. Public Expansion schema is product SoT; private Keep is behavior reference.  
2. Do not copy or ship the monolith or IP-named modules.  
3. Prefer incremental migration + compatibility layers over rewrites.  
4. Core-only installs must keep working unchanged.  
5. Private Keep on developer machines is out of scope for public installers.  
6. User data never lives inside the product bundle.  
7. Updates are staged + verifiable + rollbackable.

---

*Designed & Engineered by Antonio G. Garcia (Otaconskeep).*
