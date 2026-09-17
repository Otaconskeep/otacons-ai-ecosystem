# Keep Expansion — P5 Flagship UI Port Matrix

**Status:** P5 in progress — Flagship Keep + Autonomy + **Learning Engine**  
**Upstream checkpoints:** P0–P3 on origin; P4 qualification complete locally (commit when ready)  
**Rule:** Private Keep (`/opt/otacon`) is **behavior/visual reference only**. Clean-room rebuild. Never ship private lore, LAN, credentials, medical/household data, or third-party canon agent names.

---

## Roadmap position

```text
P0 foundation → P1 runtime → P2 living/command → P3 protected release → P4 qualification
  → P5 FLAGSHIP UI + AUTONOMY + LEARNING
  → RC1
  → clean-machine / user acceptance
  → fixes
  → 1.0 public flagship OtaconsKeep UI
```

### P5 — Flagship Keep + Autonomy + Learning (tracks)

| Track | Scope | Status |
|---|---|---|
| **A** Flagship UI port | Inventory + clean-room surfaces | Inventory ✅; port ongoing |
| **B** Project REX | Autonomous agile board wired to actions | ✅ |
| **C** Autonomous R&D | web/docs/github/repo tools | ✅ |
| **D** Autonomous execution | repo/shell/docker/services | ✅ |
| **E** Policy/authority engine | Pre-auth + hard boundaries | ✅ |
| **F** Self-created jobs / discovery | `discover_work` + detect tick | ✅ |
| **G** Peer review + retry loops | Cross-agent verify; HARD_BLOCKED | ✅ |
| **H** Learning engine | Observations → patterns → claims | ✅ implemented · ✅ tested · ✅ API · ✅ UI · ✅ runtime · ✅ provenance |
| **I** Shared Keep learning | Ledger-curated shared claims | ✅ implemented · ✅ tested · ✅ API · ✅ UI · ✅ runtime · ✅ provenance |
| **J** Agent-private learning | Per-agent preferences (no auto-leak) | ✅ implemented · ✅ tested · ✅ API · ✅ UI · ✅ runtime · ✅ provenance |
| **K** Provenance / WHY | Evidence, contradictions, revision, confidence history | ✅ implemented · ✅ tested · ✅ API · ✅ UI · ✅ runtime · ✅ provenance |

### Learning ≠ adaptive foundation

| Concept | What it is | What it is not |
|---|---|---|
| **Memory** | Episodes / what happened | Not patterned claims |
| **Living dossier** | Observed traits with supporting IDs | Not graduated heuristics with contradiction/decay |
| **Emotion** | Adaptive affective state | Not owner/operational learning |
| **Learning Engine** | Evidence-backed revisable claims (confidence, +/- evidence, decay, revision) | Not a single event becoming a permanent preference |

**Quality gate:** `PATTERN_THRESHOLD` (default 3) observations before a claim graduates. One event never creates a strong claim.

**Autonomy → learning path:** execute → verify → peer review → outcome → learning observation → reinforce/contradict → close/follow-up (`learn_from_autonomy_outcome`).

### Learning API (read + protected mutations)

| Method | Route | Role |
|---|---|---|
| GET | `/api/expansion/learning` | Board: shared + private_by_agent |
| GET | `/api/expansion/learning/shared` | Shared Keep claims |
| GET | `/api/expansion/learning/agent/{id}` | WHAT I'VE LEARNED |
| GET | `/api/expansion/learning/why/{claim_id}` | Full provenance |
| GET | `/api/expansion/learning/observations[/{agent}]` | Raw observations |
| POST | `/api/expansion/learning/observe` | Runtime/tests (protected) |
| POST | `/api/expansion/learning/reinforce` | Runtime/tests (protected) |
| POST | `/api/expansion/learning/contradict` | Runtime/tests (protected) |
| POST | `/api/expansion/learning/revise` | Runtime/tests (protected) |

UI is **read-only + WHY** — mutations stay on validated runtime/autonomy/pipeline paths.

**Classification**

| Layer | Meaning |
|---|---|
| P0–P3 | Autonomous-**capable** foundation (memory, jobs, living state, rooms) |
| P4 | Release qualification |
| **P5** | Full autonomy **+** Learning Engine (discover→close with tools; learn from outcomes) |
P5 process (this doc):

1. Inventory every page/component ✅  
2. Identify reusable HTML/CSS/JS/assets ✅  
3. Sanitize private assumptions ✅  
4. Map old agents → Expansion agents ✅  
5. Wire to real Expansion APIs/state (implementation phase)  
6. Visual parity testing (implementation phase)

---

## Agent map (private → public Expansion)

| Private Keep (reference architecture) | Public Expansion | Specialty room |
|---|---|---|
| Albedo (governance / command) | **Aria** | Command Floor `/command` |
| Solid Snake (ops / war boards) | **Vector** | War Room `/war-room` |
| Mei Ling (records / continuity) | **Ledger** | Intel `/intel` |
| Kurumi (creative / presence) | **Muse** | Creative Studio `/video-studio` |
| Psycho Mantis (awareness / HA) | **Sentry** | Operations `/ops` |
| Otacon (engineer / codec) | Folded into Core Lite + Aria Codec ownership | — |
| Xof / household principals | **Never ship** — public owner = installing user | — |
| Johnny, Nastasha, Naomi, Gray Fox, … | **Out of Expansion roster** (future packs / Hunter) | — |

---

## Surface parity matrix

| Flagship surface | Private Keep reference | Public today | P5 target |
|---|---|---|---|
| Command Center | `surfaces/dashboard_v2.py` + `dashboard-v2.*` | Lite `showHome()` | Keep-parity landing: brand-first, room launcher from **registry only**, no Homepage `.221` |
| Codec | `surfaces/codec_cockpit.py` + motion packs | Full Lite Codec + Expansion roster | Roster-aware Codec with per-agent motion packs; context from Expansion APIs |
| Relationships | `relationships_v2` | Thin matrix + WHY | Directional matrix floor + provenance drawer |
| Emotions | `emotional_state` (+ legacy emotions_v2) | Thin gauges + WHY | Emotional matrix with contribution breakdown |
| Dossiers | Genome + `data/dossiers/*` | API/product JSON only | Canonical + living dossier UI (public lore only) |
| Journals | Continuity journals (no dedicated page) | Embedded in Intel/Reports | Dedicated Journal browser (objective) |
| Diaries | Codec/private diary (intimate) | Embedded latest only | Dedicated Diary browser (subjective + WHY) |
| War Room | `war_room_v2` | Thin job cards | Jobs/decisions/recovery floor (not infra telemetry) |
| **Project REX** | Corkboard / agile | **Autonomous substrate** | Discover→close under policy; Keep Autonomy dashboard; no approval queue |
| Agent Reports | Monolith agent-reports | Thin report cards | Full provenance click-through |
| Aria Command | Throne / command patterns | Thin roster/jobs | Coordination floor (≠ Dashboard) |
| Intel | `intel_v2` | Partial journal/memories | Full continuity: living dossiers, evidence, events |
| Creative / Video Studio | `/video-studio` + Comfy | Shell + readiness | Muse room + Studio when capability READY/LIMITED |
| Ops | Mantis / HA floors | Thin HA + alerts | Sentry ops; HA optional UNAVAILABLE |
| Page Builder | `page_builder_v2` | API register only | Allowlisted registry UI (no code injection) |

---

## Reusable vs rewrite

### Reusable *patterns* (reimplement — do not copy private files)

| Pattern | Keep reference | Expansion action |
|---|---|---|
| Design tokens / ghost pastel HUD | `design-system.css`, `movie-fui.css`, `keep-hud-deck.*` | Extend `ui/home.css` + `ui/codec.css` tokens; no Keep filenames |
| Surface module shape | `surfaces/*_v2.py` + static JS boot | Prefer SPA rooms in `ui/` consuming `/api/expansion/*` |
| Motion portrait contract | `manifest.json` idle/listen/think/talk | Public assets under `ui/assets/{aria,vector,ledger,muse,sentry}/` |
| Room registry navigation | `_KEEP_WORLD_CONSTANTS['rooms']` | **Only** `expansion/rooms.py` `RoomRegistry` |
| Cross-links FAB pattern | `keep-crosslinks.js` | Registry-driven nav component |

### Must rewrite / never copy

- Agent-named rooms (Kurumi Clocktower, Albedo Throne, Sniper Nest, …)
- War Room REX/FoxDie/Xof approval copy
- LAN hardcodes (`192.168.50.*`, `/opt/otacon`, Homepage `:3003`)
- Private dossiers, diaries, medical/household, finance mounts
- Credentials, `.env`, Discord/n8n private workflows
- Mature/adult codec overlay
- Third-party canon names (Albedo, Kurumi, Snake, Mei Ling, …) in product UI strings

---

## Public UI current state (honest)

**Entry:** `/root/otacons-ai-ecosystem/ui/` — single SPA (`wizard.js` + `home.css` + `codec.css`).

| Exists (usable) | Thin stub (API→cards) | Missing UI (API exists) |
|---|---|---|
| Home Command Center | Aria Command, War Room, Ops, Creative | Dedicated Dossiers |
| Codec (strongest) | Intel (partial), Reports, Rooms list | Dedicated Journals / Diaries |
| **Project REX corkboard** | Relationships, Emotions | Page Builder editor |
| Setup wizard | | Video Studio floor |

Navigation is `showHome` / `showChat` / `showExpansionSurface(kind)` — **registry routes are metadata only**. P5 should add client routing keyed to `RoomRegistry` routes without duplicating hardcoded nav.

---

## Expansion APIs already available for wiring

| UI need | Endpoint |
|---|---|
| Command | `GET /api/expansion/command` |
| War Room | `GET /api/expansion/war-room` |
| Intel | `GET /api/expansion/intel` |
| Creative | `GET /api/expansion/creative` |
| Ops | `GET /api/expansion/ops` |
| Reports | `GET /api/expansion/reports` |
| Rooms | `GET /api/expansion/rooms` |
| Relationships + WHY | `GET /api/expansion/relationships…` |
| Emotion + WHY | `GET /api/expansion/emotion/…` |
| Journal | `GET /api/expansion/journal…` |
| Diary + explain | `GET /api/expansion/diary/…` |
| Living dossier + explain | `GET /api/expansion/living/…` |
| Capabilities | `GET /api/expansion/capabilities` |
| Jobs / events / pages | POST create/register (add UI carefully) |
| **Project REX board** | `GET /api/expansion/rex` |
| **REX transition / queue** | `POST /api/expansion/rex/transition`, `POST /api/expansion/rex/queue` |

### Project REX — autonomous substrate (shipped)

**Not an approval workflow.** Default loop:

`discover → research → plan → assign → execute → verify → repair → document → close → follow-up`

| Stage column | Meaning |
|---|---|
| BACKLOG → READY → RESEARCHING → PLANNING → ASSIGNED → IN_PROGRESS → VERIFYING | Autonomous progress |
| REWORK | Verify failed / retry (budgeted) |
| DONE | Closed; may spawn follow-up BACKLOG |
| HARD_BLOCKED | Rare oversight — policy escalate or retry budget exhausted |

| Agent | Autonomous responsibility |
|---|---|
| **Aria** | Prioritize, assign, resolve conflicts, approve plans *internally* |
| **Vector** | Code, infra, Docker, deployments, repairs, technical R&D |
| **Ledger** | Research, docs, evidence, continuity, verification |
| **Muse** | Creative / Video Studio / UI-media R&D |
| **Sentry** | Security, monitoring, incidents, follow-up discovery |

**Policy replaces approval:** `expansion/policy.py` — capability grants per agent; hard boundaries (`spend_money`, `destroy_user_data`, `publish_as_user`, `disable_audit`, …) escalate to owner.

| API | Role |
|---|---|
| `GET /api/expansion/rex` | Board + autonomy metrics |
| `GET /api/expansion/rex/autonomy` | Oversight dashboard payload |
| `GET /api/expansion/policy` | Grants + hard boundaries |
| `POST /api/expansion/rex/discover` | Agent creates work |
| `POST /api/expansion/rex/transition` | Agent moves card (`actor` + stage) |
| `POST /api/expansion/rex/plan` | Aria coordination plan |
| `POST /api/expansion/rex/peer-review` | Cross-agent validation |
| `POST /api/expansion/rex/tick` | **Full autonomy cycle** (detect→…→close) |
| `POST /api/expansion/tools/invoke` | Policy-gated tool call |

Home tile: **Project REX**. Deep link: `?rex=1&focus=<job_id>`. UI shows **Keep Autonomy** metrics (completed overnight / in progress / hard blocked / newly discovered) — not an APPROVE queue.

**Still hardening:** richer LLM planning text, broader shell allowlists, owner policy UI editor, scheduled daemon ticks (cron/systemd). Core loop is live via **Run autonomy tick**.
---

## Sanitization checklist (blocks merge if violated)

Scan every P5 UI change / release tree for:

- `/opt/otacon`
- `192.168.50.(219|221|192|69)`
- `Xof`, private household names
- Albedo / Kurumi / Solid Snake / Mei Ling / Psycho Mantis as **product** agent names
- Private dossier/diary verbatim text
- Credentials, webhooks, `.env`, source maps with secrets
- Medical/finance/grocery Keep modules

Use existing `expansion.qualify.leak_scan` on UI build output.

---

## P5 implementation order (recommended)

1. **Nav shell** — registry-driven room router + shared HUD chrome  
2. **Command Center** visual parity (brand-first, tiles from registry)  
3. **Codec** parity (per-agent assets + Expansion context)  
4. **Relationships + Emotions** floors (WHY drawers)  
5. **Journal + Diary + Dossier** dedicated browsers  
6. **War Room + Aria Command + Reports** operational depth  
7. **Intel** full continuity render  
8. **Ops + Creative** shells with honest capability states  
9. **Page Builder** allowlisted UI  
10. **Video Studio** only when capability ≠ UNAVAILABLE (keep LIMITED/UNAVAILABLE honest)

---

## Visual parity test plan (later)

For each surface: side-by-side private Keep (reference) vs Expansion — layout hierarchy, typography, motion, empty states, WHY/provenance, mobile. Pass = same *job* and *atmosphere*, not pixel clone of private IP.

---

## Out of scope for P5

- Hunter Pack UI merge  
- Private medical/household floors  
- Always-online licensing UI  
- Destructive anti-tamper  
- Rewriting P0–P4 runtime/security checkpoints  
