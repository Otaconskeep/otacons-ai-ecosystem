# Project REX ↔ KeepRoute / OmniRoute learning

**Status:** Ships in **Otacon Expansion Premium** (v1.3.2+) · same loop verified earlier on operator Keep  
**Privacy:** Architecture-only. No private Keep memories, hostnames, or live risk text.

## Verdict

| Question | Answer |
|---|---|
| Does KeepRoute/OmniRoute aid REX R&D? | **Yes** — exchange outcomes become learning records |
| Does it drive REX? | **Yes** — world-model risks/insights become `world_model:*` proposal sources on the REX board |
| Does it make REX smarter over time? | **Yes** — success dilutes stale failure signal; failures become risk entries |
| Global or local? | **Global per Expansion install** — shared pool under user learning data; `domain: keeproute` is a tag, not a silo |

## Public Premium path (v1.3.2+)

| Module | Role |
|---|---|
| `expansion/route_learning.py` | `record_resolution` / `ingest_keeproute_exchange` → shared records + traces |
| `expansion/world_model.py` | Rebuilds risks / insights / per-entity stats from that pool |
| `expansion/autonomy_loop.py` | On detect tick, spawns REX jobs tagged `world_model:*` |
| API | `POST /api/expansion/route-learning/ingest` · `GET /api/expansion/world-model` |
| KeepRoute UI | Optional `OTACON_EXPANSION_URL` / vault `expansion_url` → fail-open POST after each mission |

## Wire-up

1. Run Expansion Premium (entitled roster).
2. Point KeepRoute at it: `export OTACON_EXPANSION_URL=http://127.0.0.1:<expansion-port>` (or set vault `expansion_url`).
3. Run missions through KeepRoute / OmniRoute — outcomes land in the global pool.
4. REX autonomy tick (`POST /api/expansion/rex/tick`) discovers world-model risks as board work.

Site: https://otaconskeep.github.io/keeproute/#rex-learning
