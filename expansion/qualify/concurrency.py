"""Concurrency / persistence stress helpers for JSON stores."""
from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from typing import Optional

from expansion.emotion_store import EmotionStore
from expansion.events import new_event
from expansion.jobs import JobStore
from expansion.journal import JournalStore, new_journal_entry
from expansion.living_dossier import LivingDossierStore
from expansion.pipeline import LivingPipeline
from expansion.relationship_store import RelationshipStore
from expansion.state_layout import StateLayout, resolve_layout


@dataclass
class StressReport:
    ok: bool
    workers: int
    iterations: int
    errors: list = field(default_factory=list)
    duration_s: float = 0.0
    notes: str = ''

    def to_dict(self) -> dict:
        return asdict(self)


def stress_concurrent_writes(
    layout: Optional[StateLayout] = None,
    *,
    workers: int = 8,
    iterations: int = 20,
) -> StressReport:
    """Hammer journal/emotion/relationship/job/living stores concurrently."""
    layout = layout or resolve_layout()
    layout.ensure_user_dirs()
    pipe = LivingPipeline(layout)
    errors: list = []
    lock = threading.Lock()

    def worker(wid: int) -> None:
        emo = EmotionStore(layout)
        rels = RelationshipStore(layout)
        jobs = JobStore(layout)
        living = LivingDossierStore(layout)
        journals = JournalStore(layout)
        for i in range(iterations):
            try:
                ev = new_event(
                    'agent.message', actor='user', subject='aria',
                    payload={'text': f'stress-{wid}-{i}', 'n': i},
                )
                pipe.apply_event(ev, write_diary=(i % 5 == 0))
                state = emo.get_or_create('aria')
                emo.save(state)
                r = rels.get_or_create('aria', 'muse')
                rels.save(r)
                job = jobs.create(f'stress job {wid}-{i}', domain='coordination')
                jobs.transition(job.job_id, 'RUNNING')
                living.upsert_observation(
                    'aria',
                    category='stress_probe',
                    value=f'worker-{wid}',
                    confidence=0.4,
                    event_ids=(ev.event_id,),
                    persistence='decaying',
                )
                # Read-back sanity
                journals.recent(agent_id='aria', limit=5)
                emo.get('aria')
                rels.get('aria', 'muse')
            except Exception as exc:  # noqa: BLE001
                with lock:
                    errors.append(f'w{wid}/{i}: {exc}')

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(worker, w) for w in range(workers)]
        for f in as_completed(futs):
            f.result()
    duration = time.time() - t0

    # Integrity checks: JSON readable
    try:
        EmotionStore(layout).get('aria')
        RelationshipStore(layout).get('aria', 'muse')
        JournalStore(layout).recent(limit=10)
        JobStore(layout).list(limit=10)
        LivingDossierStore(layout).load('aria')
    except Exception as exc:  # noqa: BLE001
        errors.append(f'integrity: {exc}')

    notes = (
        'JSON+flock survived stress; document limits: '
        f'{workers} workers × {iterations} iters.'
        if not errors else
        'Corruption or races detected — consider SQLite for hot stores.'
    )
    return StressReport(
        ok=not errors,
        workers=workers,
        iterations=iterations,
        errors=errors[:20],
        duration_s=round(duration, 3),
        notes=notes,
    )
