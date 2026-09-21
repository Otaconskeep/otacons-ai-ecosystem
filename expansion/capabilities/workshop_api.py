"""Keep Workshop API bridge for Expansion `/video-studio`.

Serves the same route shapes the vendored Keep Workshop UI expects
(`/video-studio/api/...`) backed by Expansion Comfy submit, JobStore,
and preferences — so friends get the real Workshop look + core generate
path without needing otacon-executor.
"""
from __future__ import annotations

import hashlib
import json
import re
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Optional
from urllib.parse import unquote

from expansion.persist import atomic_write_json, read_json
from expansion.state_layout import StateLayout, resolve_layout

SendJson = Callable[..., None]
SendBytes = Callable[..., None]

# Bounded in-process cache for Workshop output bytes (preview poll storm).
_OUTPUT_CACHE: dict[str, tuple[float, bytes, str, str]] = {}
_OUTPUT_CACHE_BYTES = 0
_OUTPUT_CACHE_MAX = 64 * 1024 * 1024
_OUTPUT_CACHE_LOCK = threading.Lock()


def _cache_get(key: str) -> Optional[tuple[bytes, str, str]]:
    with _OUTPUT_CACHE_LOCK:
        hit = _OUTPUT_CACHE.get(key)
        if not hit:
            return None
        _ts, data, mime, name = hit
        return data, mime, name


def _cache_put(key: str, data: bytes, mime: str, name: str) -> None:
    global _OUTPUT_CACHE_BYTES
    if not data or len(data) > _OUTPUT_CACHE_MAX // 2:
        return
    with _OUTPUT_CACHE_LOCK:
        old = _OUTPUT_CACHE.pop(key, None)
        if old:
            _OUTPUT_CACHE_BYTES -= len(old[1])
        while _OUTPUT_CACHE and _OUTPUT_CACHE_BYTES + len(data) > _OUTPUT_CACHE_MAX:
            _k, ev = next(iter(_OUTPUT_CACHE.items()))
            del _OUTPUT_CACHE[_k]
            _OUTPUT_CACHE_BYTES -= len(ev[1])
        _OUTPUT_CACHE[key] = (time.time(), data, mime, name)
        _OUTPUT_CACHE_BYTES += len(data)


def _prefs(layout: Optional[StateLayout] = None) -> Path:
    layout = layout or resolve_layout()
    layout.user_preferences.mkdir(parents=True, exist_ok=True)
    return layout.user_preferences


def _actors_path(layout: Optional[StateLayout] = None) -> Path:
    return _prefs(layout) / 'workshop_actors.json'


def _actors_media_dir(layout: Optional[StateLayout] = None) -> Path:
    d = _prefs(layout) / 'workshop_actor_media'
    d.mkdir(parents=True, exist_ok=True)
    return d


def _sync_actor_portrait_status(actor: dict[str, Any], layout: Optional[StateLayout] = None) -> dict[str, Any]:
    """Refresh portrait_status from the linked image job when still generating."""
    jid = str(actor.get('portrait_job_id') or '')
    if not jid:
        return actor
    if actor.get('portrait_status') == 'ready':
        return actor
    job = _get_job(jid, layout)
    if not job:
        return actor
    job = _refresh_image_job(dict(job), layout)
    st = job.get('status')
    if st == 'completed':
        actor['portrait_status'] = 'ready'
        actor['portrait_error'] = ''
        imgs = dict(actor.get('images') or {})
        imgs['portrait'] = f"/video-studio/api/generate-image-v1/{jid}/output"
        actor['images'] = imgs
    elif st == 'failed':
        actor['portrait_status'] = 'failed'
        actor['portrait_error'] = job.get('error') or 'portrait failed'
    else:
        actor['portrait_status'] = 'generating'
    return actor


def _actors_public(layout: Optional[StateLayout] = None) -> list[dict[str, Any]]:
    actors = _load_list(_actors_path(layout))
    out = []
    dirty = False
    for a in actors:
        synced = _sync_actor_portrait_status(dict(a), layout)
        if synced != a:
            dirty = True
        out.append(synced)
    if dirty:
        _save_list(_actors_path(layout), out)
    return out


def _portrait_prompt_for_actor(actor: dict[str, Any]) -> str:
    name = str(actor.get('name') or 'character').strip()
    desc = str(
        actor.get('description')
        or actor.get('note')
        or ''
    ).strip()
    personality = str(actor.get('personality') or '').strip()
    base = (
        f"identity-preserving portrait of {name}, natural lighting, sharp eyes, "
        "clean background, single subject, head and shoulders, high detail"
    )
    bits = [base]
    if desc:
        bits.append(desc)
    if personality:
        bits.append(f"personality cues: {personality}")
    return '. '.join(bits)



def _styles_path(layout: Optional[StateLayout] = None) -> Path:
    return _prefs(layout) / 'workshop_styles.json'


def _jobs_path(layout: Optional[StateLayout] = None) -> Path:
    return _prefs(layout) / 'workshop_jobs.json'


def _load_list(path: Path) -> list[dict[str, Any]]:
    data = read_json(path, default=[])
    return data if isinstance(data, list) else []


def _save_list(path: Path, items: list[dict[str, Any]]) -> None:
    atomic_write_json(path, items)


def _seed_actors_styles(layout: Optional[StateLayout] = None) -> None:
    """Seed from keep_defaults.json; refresh when still on legacy Keep Film set."""
    ap = _actors_path(layout)
    sp = _styles_path(layout)
    defaults: dict[str, Any] = {}
    try:
        dpath = Path(__file__).resolve().parents[1] / 'product' / 'studio' / 'keep_defaults.json'
        if dpath.is_file():
            defaults = json.loads(dpath.read_text(encoding='utf-8'))
    except Exception:
        defaults = {}

    def _style_rows() -> list[dict[str, Any]]:
        styles = []
        for s in defaults.get('styles') or []:
            sid = str(s.get('id') or uuid.uuid4().hex[:10])
            prompt = str(s.get('prompt') or s.get('note') or '')
            styles.append({
                'id': sid,
                'name': s.get('label') or s.get('name') or sid,
                'prompt': prompt,
                'description': prompt,
                'created_at': time.time(),
            })
        return styles

    if not ap.is_file():
        actors = []
        for a in defaults.get('actors') or []:
            aid = str(a.get('id') or uuid.uuid4().hex[:10])
            actors.append({
                'id': aid,
                'name': a.get('label') or a.get('name') or aid,
                'note': a.get('note') or a.get('tag') or '',
                'description': a.get('note') or '',
                'images': {},
                'ref_slots': {},
                'reference_images': [],
                'created_at': time.time(),
            })
        _save_list(ap, actors)
    else:
        # Scrub seeded OtaconsKeep / Metal Gear agent cameos from Workshop cast.
        scrub_ids = {
            'muse_self', 'aria_cameo', 'vector_cameo', 'ledger_cameo', 'sentry_cameo',
            'albedo', 'otacon', 'mei_ling', 'solid_snake', 'naomi_hunter', 'kurumi', 'gray_fox',
            'muse', 'aria', 'vector', 'ledger', 'sentry',
        }
        scrub_names = {
            'muse', 'aria', 'vector', 'ledger', 'sentry', 'albedo', 'otacon',
            'mei ling', 'solid snake', 'naomi hunter', 'kurumi', 'gray fox',
        }
        existing_actors = _load_list(ap)
        cleaned = []
        changed_actors = False
        for a in existing_actors:
            aid = str(a.get('id') or '').lower()
            name = str(a.get('name') or a.get('label') or '').strip().lower()
            if aid in scrub_ids or name in scrub_names:
                changed_actors = True
                continue
            cleaned.append(a)
        if changed_actors:
            if not cleaned:
                for a in defaults.get('actors') or []:
                    cleaned.append({
                        'id': str(a.get('id') or uuid.uuid4().hex[:10]),
                        'name': a.get('label') or a.get('name') or 'Actor',
                        'note': a.get('note') or '',
                        'description': a.get('note') or '',
                        'images': {},
                        'ref_slots': {},
                        'reference_images': [],
                        'created_at': time.time(),
                    })
            _save_list(ap, cleaned)

    desired = _style_rows()
    if not desired:
        return
    if not sp.is_file():
        _save_list(sp, desired)
        return
    existing = _load_list(sp)
    ids = {str(s.get('id') or '') for s in existing}
    # Legacy Keep Film / noir set without anime → replace with anime/comic/cinema defaults.
    legacy = bool(ids & {'keep_film', 'noir', 'docu', 'editorial', 'handheld', 'anamorphic'})
    modern = bool(ids & {'anime', 'comic', 'cinema', 'anime_cinema'})
    if legacy and not modern:
        _save_list(sp, desired)
        return
    # Ensure description mirrors prompt for Workshop prompt composition.
    changed = False
    for s in existing:
        if s.get('prompt') and not s.get('description'):
            s['description'] = s['prompt']
            changed = True
    if changed:
        _save_list(sp, existing)


def _workshop_jobs(layout: Optional[StateLayout] = None) -> list[dict[str, Any]]:
    return _load_list(_jobs_path(layout))


def _save_jobs(jobs: list[dict[str, Any]], layout: Optional[StateLayout] = None) -> None:
    _save_list(_jobs_path(layout), jobs[-200:])


def _upsert_job(job: dict[str, Any], layout: Optional[StateLayout] = None) -> dict[str, Any]:
    jobs = _workshop_jobs(layout)
    found = False
    for i, j in enumerate(jobs):
        if j.get('id') == job.get('id'):
            jobs[i] = {**j, **job}
            found = True
            break
    if not found:
        jobs.insert(0, job)
    _save_jobs(jobs, layout)
    return job


def sync_expansion_job_to_workshop(job: Any, layout: Optional[StateLayout] = None) -> dict[str, Any]:
    """Mirror an Expansion JobStore creative job into Workshop log cards."""
    if job is None:
        return {}
    from expansion.capabilities.comfy_submit import (
        endpoint_from_job,
        outputs_from_job,
        prompt_id_from_job,
        public_creative_job,
    )
    status_map = {
        'QUEUED': 'queued',
        'ASSIGNED': 'queued',
        'WAITING': 'waiting_gpu',
        'RUNNING': 'running',
        'COMPLETE': 'completed',
        'FAILED': 'failed',
        'CANCELLED': 'cancelled',
    }
    st = status_map.get(str(getattr(job, 'status', '') or '').upper(), 'queued')
    files = outputs_from_job(job)
    ep = endpoint_from_job(job)
    pub = public_creative_job(job)
    created = float(getattr(job, 'created_at', None) or time.time())
    card = {
        'id': getattr(job, 'job_id', '') or pub.get('job_id'),
        'type': 'image_v1',
        'job_type': 'image_v1',
        'status': st,
        'prompt': getattr(job, 'request', '') or '',
        'agent_id': getattr(job, 'assigned_agent', None) or 'muse',
        'created_at': created,
        'created_ts': created,
        'stage': st,
        'prompt_id': prompt_id_from_job(job),
        'endpoint': ep,
        'outputs': files,
        'output_file': files[0] if files else '',
        'preview_url': pub.get('preview_url') or pub.get('workshop_output') or '',
        'expansion': True,
        'width': 512,
        'height': 512,
        'error': getattr(job, 'error', '') or '',
    }
    return _upsert_job(card, layout)



def promote_workshop_job_to_expansion(
    job: dict[str, Any],
    *,
    layout: Optional[StateLayout] = None,
    modality: str = 'image',
) -> Optional[Any]:
    """Mirror Workshop-created jobs into JobStore so /creative lists them.

    /creative and War Room read Expansion JobStore; Workshop UI historically
    wrote only workshop_jobs.json — successful renders looked like silent fails.
    """
    if not isinstance(job, dict) or not job.get('id'):
        return None
    try:
        from expansion.capabilities.comfy_submit import ensure_creative_poller
        from expansion.events import new_event
        from expansion.jobs import Job, JobStatus, JobStore, JOB_SCHEMA_VERSION
        from expansion.pipeline import LivingPipeline
    except Exception:
        return None
    ensure_creative_poller()
    layout = layout or resolve_layout()
    store = JobStore(layout=layout)
    jid = str(job['id'])
    existing = store.get(jid)
    prompt = str(job.get('prompt') or job.get('tags') or '').strip()
    engine = {
        'image': 'z-image-turbo',
        'video': 'wan-2.2-5b',
        'music': 'ace-step-1.5',
    }.get(modality, modality)
    request = f"[Muse Studio · {modality} · {engine}] {prompt}"[:2000]
    pid = str(job.get('prompt_id') or '')
    ep = str(job.get('endpoint') or '')
    if existing is None:
        # Create with the Workshop id so both stores share one key.
        ej = Job(
            schema_version=JOB_SCHEMA_VERSION,
            job_id=jid if jid.startswith('job_') else jid,
            requester='user_primary',
            coordinator='aria',
            assigned_agent='muse',
            domain='creative',
            priority=5,
            status=JobStatus.QUEUED.value,
            created_at=float(job.get('created_at') or time.time()),
            request=request,
        )
        store.update(ej)
        created = new_event(
            'job.created', actor='aria', subject='muse',
            payload={'job_id': ej.job_id, 'domain': 'creative', 'request': request,
                     'comfy_prompt_id': pid, 'workshop': True},
        )
        try:
            LivingPipeline().apply_event(created, write_diary=False)
        except Exception:
            pass
        store.transition(ej.job_id, JobStatus.ASSIGNED.value, event_id=created.event_id)
        evidence = []
        if pid:
            evidence.append(f'comfy:prompt_id={pid}')
        if ep:
            evidence.append(f'comfy:endpoint={ep}')
        if job.get('status') == 'failed':
            store.transition(
                ej.job_id, JobStatus.FAILED.value,
                error=str(job.get('error') or 'workshop submit failed'),
                event_id=created.event_id,
            )
        elif pid:
            store.transition(
                ej.job_id, JobStatus.RUNNING.value,
                evidence=evidence, event_id=created.event_id,
            )
        return store.get(ej.job_id)
    # Update existing
    if job.get('status') == 'completed':
        files = job.get('outputs') or ([job['output_file']] if job.get('output_file') else [])
        store.transition(
            jid, JobStatus.COMPLETE.value,
            result=f"ComfyUI outputs: {', '.join(str(f) for f in files[:6])}",
            evidence=list(existing.evidence or []) + [f'comfy:output={f}' for f in files[:8]],
            confidence=0.9,
        )
    elif job.get('status') == 'failed':
        store.transition(jid, JobStatus.FAILED.value, error=str(job.get('error') or 'failed'))
    elif pid and existing.status in (JobStatus.QUEUED.value, JobStatus.ASSIGNED.value):
        evidence = list(existing.evidence or [])
        if pid and f'comfy:prompt_id={pid}' not in evidence:
            evidence.append(f'comfy:prompt_id={pid}')
        store.transition(jid, JobStatus.RUNNING.value, evidence=evidence)
    return store.get(jid)


def _expansion_jobs_as_workshop(layout: Optional[StateLayout] = None) -> list[dict[str, Any]]:
    try:
        from expansion.capabilities.comfy_submit import (
            endpoint_from_job,
            outputs_from_job,
            prompt_id_from_job,
            public_creative_job,
        )
        from expansion.jobs import JobStore
    except Exception:
        return []
    status_map = {
        'QUEUED': 'queued',
        'ASSIGNED': 'queued',
        'WAITING': 'waiting_gpu',
        'RUNNING': 'running',
        'COMPLETE': 'completed',
        'FAILED': 'failed',
        'CANCELLED': 'cancelled',
    }
    out: list[dict[str, Any]] = []
    for job in JobStore(layout=layout).list(limit=80):
        if job.domain not in ('creative', 'media'):
            continue
        files = outputs_from_job(job)
        pub = public_creative_job(job)
        created = float(job.created_at or 0)
        out.append({
            'id': job.job_id,
            'type': 'image_v1',
            'job_type': 'image_v1',
            'status': status_map.get(job.status, 'queued'),
            'prompt': job.request or '',
            'agent_id': job.assigned_agent or 'muse',
            'created_at': created,
            'created_ts': created,
            'stage': job.status,
            'prompt_id': prompt_id_from_job(job),
            'endpoint': endpoint_from_job(job),
            'outputs': files,
            'output_file': files[0] if files else '',
            'preview_url': pub.get('preview_url') or pub.get('workshop_output') or '',
            'expansion': True,
            'width': 512,
            'height': 512,
            'error': job.error or '',
        })
    return out


def _get_job(job_id: str, layout: Optional[StateLayout] = None) -> Optional[dict[str, Any]]:
    for j in _workshop_jobs(layout):
        if j.get('id') == job_id:
            return j
    return None


def _health() -> dict[str, Any]:
    from expansion.capabilities.video_studio import probe_video_studio, comfy_endpoint_healthy
    from expansion.capabilities.studio_setup import studio_hardware_snapshot
    from expansion.capabilities.comfy_submit import image_workflow_status, _studio_endpoint
    # clear_stale=False — health must not wipe a working endpoint mid-session.
    vs = probe_video_studio(clear_stale=False)
    hw = studio_hardware_snapshot()
    disc = vs.discovery or {}
    endpoint = str(disc.get('endpoint') or _studio_endpoint() or '').rstrip('/')
    comfy_ok = False
    if endpoint:
        comfy_ok, _ = comfy_endpoint_healthy(endpoint, timeout=2.0)
    if not comfy_ok:
        try:
            from expansion.capabilities.comfy_sidecar import detect_local_comfy
            detected = detect_local_comfy(timeout=1.5) or {}
            cand = str(detected.get('endpoint') or '').rstrip('/')
            if cand:
                ok2, _ = comfy_endpoint_healthy(cand, timeout=2.0)
                if ok2:
                    endpoint, comfy_ok = cand, True
        except Exception:
            pass
    packs: dict[str, Any] = {}
    try:
        from expansion.capabilities.studio_packs import packs_status
        packs = packs_status(endpoint=endpoint or None, hw=hw) or {}
    except Exception:
        packs = {}
    workflow: dict[str, Any] = {}
    try:
        workflow = image_workflow_status(endpoint or None) if endpoint else {}
    except Exception:
        workflow = {}
    video_ready = bool(
        (packs.get('packs') or {}).get('wan', {}).get('ok')
        or (packs.get('packs') or {}).get('ltx2', {}).get('ok')
    )
    image_ready = bool(
        packs.get('image_ready')
        or (packs.get('packs') or {}).get('z_image', {}).get('ok')
        or workflow.get('ok')
    )
    music_ready = bool((packs.get('packs') or {}).get('ace_step', {}).get('ok'))
    if not music_ready and endpoint:
        try:
            from expansion.capabilities.comfy_submit import music_workflow_status
            music_ready = bool(music_workflow_status(endpoint).get('ok'))
        except Exception:
            pass
    studio_ready = bool(comfy_ok or vs.state == 'READY')
    # Image generation must not wait on video/music packs or a READY-only label.
    generation_ready = bool(studio_ready and image_ready)
    return {
        'cuda_available': bool(hw.get('cuda_available') or studio_ready),
        'ready': generation_ready,
        'gpu_name': hw.get('gpu_model') or 'GPU',
        'vram_total_gb': float(hw.get('marketed_vram_gb') or hw.get('vram_gb') or 0),
        'vram_free_gb': float(hw.get('marketed_vram_gb') or hw.get('vram_gb') or 0) * 0.55,
        'backend': 'Otacon Expansion · Muse Creative',
        'studio_state': vs.state,
        'endpoint': endpoint,
        'queue_running': 0,
        'queue_pending': 0,
        'comfyui_warm': studio_ready,
        'expansion': True,
        'studio_ready': studio_ready,
        'assets_ready': image_ready,
        'generation_ready': generation_ready,
        'image_ready': image_ready,
        'video_ready': video_ready,
        'music_ready': music_ready,
        # Keep has the full movie/projects worker; Expansion Workshop UI is
        # Keep-parity but the backend is not ported yet. Surface that honestly
        # so the UI can hide One-click Movie instead of offering a 501 path.
        'projects_ready': False,
        'projects_detail': (
            'Project / movie production API is Keep-parity UI-ready; '
            'Expansion worker wiring is not shipped yet.'
        ),
        'preferred_mode': 'image' if (image_ready and not video_ready) else 'video',
        'packs_aria': packs.get('aria') or '',
    }


def _telemetry() -> dict[str, Any]:
    h = _health()
    return {
        'ok': True,
        'gpu_name': h.get('gpu_name'),
        'vram_total_gb': h.get('vram_total_gb'),
        'vram_free_gb': h.get('vram_free_gb'),
        'cpu_pct': 0,
        'ram_pct': 0,
        'queue_running': h.get('queue_running') or 0,
        'queue_pending': h.get('queue_pending') or 0,
        'studio_state': h.get('studio_state'),
        'backend': h.get('backend'),
    }


def _create_image_job(
    *,
    prompt: str,
    width: int = 1024,
    height: int = 1024,
    negative: str = '',
    actor_ids: Optional[list[str]] = None,
    style_id: str = '',
    layout: Optional[StateLayout] = None,
) -> dict[str, Any]:
    from expansion.capabilities.comfy_submit import submit_image_job

    job_id = uuid.uuid4().hex[:12]
    now = time.time()
    job = {
        'id': job_id,
        'type': 'image_v1',
        'job_type': 'image_v1',
        'status': 'queued',
        'prompt': prompt,
        'negative': negative,
        'width': width,
        'height': height,
        'actor_ids': actor_ids or [],
        'style_id': style_id or '',
        'agent_id': 'workshop',
        'created_at': now,
        'created_ts': now,
        'stage': 'submitting',
    }
    _upsert_job(job, layout)

    submitted = submit_image_job(
        prompt=prompt,
        negative=negative,
        tuning={'resolution': f'{width}x{height}', 'steps': 8, 'cfg': 1},
    )
    if not submitted.get('ok') or not submitted.get('prompt_id'):
        job.update({
            'status': 'failed',
            'error': submitted.get('detail') or submitted.get('error') or 'packs or Comfy not ready',
            'soft_block': bool(submitted.get('soft_block')),
            'action': submitted.get('action') or '',
            'stage': 'failed',
        })
        _upsert_job(job, layout)
        try:
            promote_workshop_job_to_expansion(job, layout=layout, modality='image')
        except Exception:
            pass
        return job

    job.update({
        'status': 'running',
        'stage': 'comfy',
        'prompt_id': submitted['prompt_id'],
        'endpoint': submitted.get('endpoint') or '',
    })
    _upsert_job(job, layout)
    try:
        promote_workshop_job_to_expansion(job, layout=layout, modality='image')
    except Exception:
        pass
    return job


def _refresh_image_job(job: dict[str, Any], layout: Optional[StateLayout] = None) -> dict[str, Any]:
    if job.get('status') in ('completed', 'failed', 'cancelled') or not job.get('prompt_id'):
        return job
    from expansion.capabilities.comfy_submit import _history_outputs, _studio_endpoint
    ep = job.get('endpoint') or _studio_endpoint()
    files = _history_outputs(ep, str(job['prompt_id']))
    if files:
        job['status'] = 'completed'
        job['stage'] = 'done'
        job['outputs'] = files
        job['output_file'] = files[0]
        _upsert_job(job, layout)
        try:
            promote_workshop_job_to_expansion(job, layout=layout, modality='image')
        except Exception:
            pass
    return job


def _create_music_job(
    *,
    tags: str,
    lyrics: str = '',
    duration: float = 60,
    bpm: Optional[float] = None,
    seed: Optional[int] = None,
    tuning: Optional[dict] = None,
    layout: Optional[StateLayout] = None,
) -> dict[str, Any]:
    from expansion.capabilities.comfy_submit import submit_music_job

    job_id = uuid.uuid4().hex[:12]
    now = time.time()
    job = {
        'id': job_id,
        'type': 'music_v1',
        'job_type': 'music_v1',
        'status': 'queued',
        'prompt': tags,
        'tags': tags,
        'lyrics': lyrics or '',
        'duration': duration,
        'bpm': bpm,
        'seed': seed,
        'audio_format': 'mp3',
        'agent_id': 'workshop',
        'created_at': now,
        'created_ts': now,
        'stage': 'submitting',
    }
    _upsert_job(job, layout)
    submitted = submit_music_job(
        tags=tags,
        lyrics=lyrics,
        duration_sec=duration,
        bpm=bpm,
        seed=seed,
        tuning=tuning or {},
    )
    if not submitted.get('ok') or not submitted.get('prompt_id'):
        job.update({
            'status': 'failed',
            'error': submitted.get('detail') or submitted.get('error') or 'music packs or Comfy not ready',
            'soft_block': bool(submitted.get('soft_block')),
            'action': submitted.get('action') or '',
            'stage': 'failed',
        })
        _upsert_job(job, layout)
        return job
    job.update({
        'status': 'queued',
        'stage': 'comfy',
        'prompt_id': submitted['prompt_id'],
        'endpoint': submitted.get('endpoint') or '',
        'duration': submitted.get('duration') or duration,
    })
    _upsert_job(job, layout)
    try:
        promote_workshop_job_to_expansion(job, layout=layout, modality='music')
    except Exception:
        pass
    return job


def _send_job_output(
    jid: str,
    layout: Optional[StateLayout],
    send_json: SendJson,
    send_redirect: Optional[Callable[[str, int], None]] = None,
    send_bytes: Optional[Callable[..., None]] = None,
) -> bool:
    from expansion.capabilities.comfy_submit import (
        endpoint_from_job,
        fetch_comfy_output_bytes,
        outputs_from_job,
    )

    def _proxy(fname: str, endpoint: str) -> bool:
        cache_key = f'{endpoint}|{fname}'
        cached = _cache_get(cache_key)
        if cached:
            data, mime, name = cached
        else:
            data, mime, name = fetch_comfy_output_bytes(filename=fname, endpoint=endpoint)
            if data is None:
                send_json({
                    'error': 'output not ready',
                    'detail': (
                        'Could not load that file through Otacon. '
                        'If Comfy finished, try Generate again or open Creative after soft-update.'
                    ),
                    'filename': name or fname,
                }, 404)
                return True
            _cache_put(cache_key, data, mime, name or fname)
        if send_bytes:
            etag = '"' + hashlib.sha256(data).hexdigest()[:32] + '"'
            try:
                send_bytes(
                    data,
                    mime,
                    name or fname,
                    cache_control='public, max-age=31536000, immutable',
                    etag=etag,
                )
            except TypeError:
                # Older send_bytes without cache kwargs
                send_bytes(data, mime, name or fname)
            return True
        # Never fall back to JSON for media routes — browsers treat that as a
        # broken <img>/<video>. Callers (installer.server) must pass send_bytes.
        send_json({
            'error': 'byte_sender_missing',
            'detail': (
                'Workshop output proxy needs send_bytes from installer.server. '
                'Soft-update Expansion and restart otacon.service.'
            ),
            'filename': name or fname,
            'content_type': mime,
        }, 500)
        return True

    job = _get_job(jid, layout)
    if job:
        job = _refresh_image_job(dict(job), layout)
        if job.get('status') != 'completed':
            send_json({'error': 'output not ready', 'status': job.get('status')}, 404)
            return True
        ep = (job.get('endpoint') or 'http://127.0.0.1:8188').rstrip('/')
        fname = job.get('output_file') or ((job.get('outputs') or [None])[0])
        if not fname:
            send_json({'error': 'no output'}, 404)
            return True
        return _proxy(str(fname), ep)
    try:
        from expansion.jobs import JobStore
        ej = JobStore(layout=layout).get(jid)
    except Exception:
        ej = None
    if not ej:
        send_json({'error': 'not found'}, 404)
        return True
    files = outputs_from_job(ej)
    if not files:
        send_json({'error': 'output not ready', 'status': getattr(ej, 'status', '')}, 404)
        return True
    return _proxy(files[0], endpoint_from_job(ej))



def _create_video_job(
    *,
    prompt: str,
    negative: str = '',
    width: int = 512,
    height: int = 320,
    frames: int = 25,
    fps: int = 16,
    steps: int = 20,
    layout: Optional[StateLayout] = None,
) -> dict[str, Any]:
    from expansion.capabilities.comfy_submit import submit_video_job

    job_id = uuid.uuid4().hex[:12]
    now = time.time()
    job = {
        'id': job_id,
        'type': 'video_v1',
        'job_type': 'video_v1',
        'status': 'queued',
        'prompt': prompt,
        'negative': negative,
        'width': width,
        'height': height,
        'frames': frames,
        'fps': fps,
        'agent_id': 'workshop',
        'created_at': now,
        'created_ts': now,
        'stage': 'submitting',
    }
    _upsert_job(job, layout)
    submitted = submit_video_job(
        prompt=prompt,
        negative=negative,
        tuning={
            'resolution': f'{width}x{height}',
            'frames': frames,
            'fps': fps,
            'steps': steps,
            'cfg': 5,
        },
    )
    if not submitted.get('ok') or not submitted.get('prompt_id'):
        job.update({
            'status': 'failed',
            'error': submitted.get('detail') or submitted.get('error') or 'video packs or Comfy not ready',
            'soft_block': bool(submitted.get('soft_block')),
            'action': submitted.get('action') or '',
            'stage': 'failed',
        })
        _upsert_job(job, layout)
        try:
            promote_workshop_job_to_expansion(job, layout=layout, modality='video')
        except Exception:
            pass
        return job
    job.update({
        'status': 'running',
        'stage': 'comfy',
        'prompt_id': submitted['prompt_id'],
        'endpoint': submitted.get('endpoint') or '',
    })
    _upsert_job(job, layout)
    try:
        promote_workshop_job_to_expansion(job, layout=layout, modality='video')
    except Exception:
        pass
    return job


def _refresh_video_job(job: dict[str, Any], layout: Optional[StateLayout] = None) -> dict[str, Any]:
    if job.get('status') in ('completed', 'failed', 'cancelled') or not job.get('prompt_id'):
        return job
    from expansion.capabilities.comfy_submit import _history_outputs, _studio_endpoint
    ep = job.get('endpoint') or _studio_endpoint()
    files = _history_outputs(ep, str(job['prompt_id']))
    if files:
        job['status'] = 'completed'
        job['stage'] = 'done'
        job['outputs'] = files
        job['output_file'] = files[0]
        _upsert_job(job, layout)
        try:
            promote_workshop_job_to_expansion(job, layout=layout, modality='video')
        except Exception:
            pass
    return job


def handle_workshop_get(
    path: str,
    send_json: SendJson,
    send_redirect: Optional[Callable[[str, int], None]] = None,
    send_bytes: Optional[Callable[..., None]] = None,
) -> bool:
    """Return True if handled. path has no query string."""
    if not path.startswith('/video-studio/api/'):
        return False
    _seed_actors_styles()
    layout = resolve_layout()
    rel = path[len('/video-studio/api/'):].strip('/')

    if rel in ('health',):
        send_json(_health())
        return True
    if rel in ('telemetry',):
        send_json(_telemetry())
        return True
    if rel == 'actors':
        send_json(_actors_public(layout))
        return True
    if rel == 'styles':
        send_json(_load_list(_styles_path(layout)))
        return True

    m = re.match(r'actors/([^/]+)/media/([^/]+)$', rel)
    if m and send_bytes:
        aid = unquote(m.group(1))
        name = unquote(m.group(2))
        # Path traversal guard
        if '/' in name or '\\' in name or name.startswith('.'):
            send_json({'error': 'bad name'}, 400)
            return True
        fpath = _actors_media_dir(layout) / aid / name
        if not fpath.is_file():
            send_json({'error': 'not found'}, 404)
            return True
        data = fpath.read_bytes()
        mime = 'image/png'
        low = name.lower()
        if low.endswith(('.jpg', '.jpeg')):
            mime = 'image/jpeg'
        elif low.endswith('.webp'):
            mime = 'image/webp'
        elif low.endswith('.gif'):
            mime = 'image/gif'
        etag = '"' + hashlib.sha256(data).hexdigest()[:32] + '"'
        try:
            send_bytes(data, mime, name, cache_control='public, max-age=86400', etag=etag)
        except TypeError:
            send_bytes(data, mime, name)
        return True
    if rel == 'jobs':
        local = []
        for j in _workshop_jobs(layout)[:80]:
            jj = dict(j)
            jt = str(jj.get('type') or jj.get('job_type') or '')
            if jt.startswith('video'):
                local.append(_refresh_video_job(jj, layout))
            else:
                local.append(_refresh_image_job(jj, layout))
        merged: dict[str, dict[str, Any]] = {}
        for j in _expansion_jobs_as_workshop(layout) + local:
            jid = str(j.get('id') or '')
            if not jid:
                continue
            prev = merged.get(jid)
            # Prefer completed expansion cards with outputs.
            if not prev or (j.get('status') == 'completed' and j.get('outputs')):
                merged[jid] = j
            elif prev and not prev.get('outputs') and j.get('outputs'):
                merged[jid] = {**prev, **j}
        jobs = sorted(
            merged.values(),
            key=lambda x: float(x.get('created_at') or 0),
            reverse=True,
        )[:80]
        try:
            from expansion.capabilities.comfy_submit import annotate_jobs_with_queue_position
            # Refresh in-flight image/music cards, then overlay live Comfy positions.
            refreshed = []
            for j in jobs:
                jt = j.get('job_type') or j.get('type') or ''
                if jt in ('image_v1', 'hidream_v1', 'music_v1') and j.get('prompt_id'):
                    refreshed.append(_refresh_image_job(dict(j), layout))
                else:
                    refreshed.append(j)
            jobs = annotate_jobs_with_queue_position(refreshed)
        except Exception:
            pass
        send_json(jobs)
        return True
    if rel == 'scripts':
        send_json([])
        return True
    if rel == 'projects':
        send_json([])
        return True
    if rel == 'tuning-defaults':
        send_json({
            'image': {'steps': 8, 'cfg': 1.0, 'width': 1024, 'height': 1024},
            'video': {'steps': 6, 'cfg': 1.0, 'fps': 16, 'duration': 4},
            'music': {'duration': 60, 'bpm': 90},
        })
        return True

    m = re.match(r'actors/([^/]+)$', rel)
    if m:
        aid = unquote(m.group(1))
        for a in _load_list(_actors_path(layout)):
            if a.get('id') == aid:
                send_json(a)
                return True
        send_json({'error': 'not found'}, 404)
        return True

    m = re.match(r'jobs/([^/]+)/output$', rel)
    if m:
        jid = unquote(m.group(1))
        return _send_job_output(jid, layout, send_json, send_redirect, send_bytes)

    m = re.match(r'jobs/([^/]+)$', rel)
    if m:
        jid = unquote(m.group(1))
        job = _get_job(jid, layout)
        if job:
            send_json(_refresh_image_job(dict(job), layout))
            return True
        try:
            from expansion.jobs import JobStore
            ej = JobStore(layout=layout).get(jid)
        except Exception:
            ej = None
        if ej:
            send_json(sync_expansion_job_to_workshop(ej, layout))
            return True
        send_json({'error': 'not found'}, 404)
        return True

    m = re.match(r'generate-image-v1/([^/]+)$', rel)
    if m:
        jid = unquote(m.group(1))
        job = _get_job(jid, layout)
        if job:
            send_json(_refresh_image_job(dict(job), layout))
            return True
        try:
            from expansion.jobs import JobStore
            ej = JobStore(layout=layout).get(jid)
        except Exception:
            ej = None
        if ej:
            send_json(sync_expansion_job_to_workshop(ej, layout))
            return True
        send_json({'error': 'not found'}, 404)
        return True

    m = re.match(r'generate-image-v1/([^/]+)/output$', rel)
    if m:
        return _send_job_output(unquote(m.group(1)), layout, send_json, send_redirect, send_bytes)

    m = re.match(r'generate-music-v1/([^/]+)$', rel)
    if m:
        jid = unquote(m.group(1))
        job = _get_job(jid, layout)
        if job:
            send_json(_refresh_image_job(dict(job), layout))
            return True
        send_json({'error': 'not found'}, 404)
        return True

    m = re.match(r'generate-music-v1/([^/]+)/output$', rel)
    if m:
        return _send_job_output(unquote(m.group(1)), layout, send_json, send_redirect, send_bytes)

    # Soft stubs for modalities not fully wired yet — keep UI from hard-failing.
    if rel.startswith('generate-v2/') or rel.startswith('generate-hidream'):
        send_json({'error': 'job not found', 'expansion_stub': True}, 404)
        return True

    send_json({'error': 'not found', 'path': path}, 404)
    return True


def _cancel_job(jid: str, layout: Optional[StateLayout] = None) -> tuple[dict[str, Any], int]:
    """Cancel a Workshop/Expansion image job and stop GPU work in Comfy when possible."""
    from expansion.capabilities.comfy_submit import cancel_comfy_prompt

    layout = layout or resolve_layout()
    job = _get_job(jid, layout)
    expansion_job = None
    try:
        from expansion.jobs import JobStore, JobStatus
        expansion_job = JobStore(layout=layout).get(jid)
    except Exception:
        expansion_job = None

    if not job and not expansion_job:
        return {'ok': False, 'error': 'not found'}, 404

    status = ''
    if job:
        status = str(job.get('status') or '')
    elif expansion_job:
        status = str(getattr(expansion_job, 'status', '') or '').lower()
        if status == 'complete':
            status = 'completed'
        elif status == 'failed':
            status = 'failed'
        elif status == 'cancelled':
            status = 'cancelled'

    if status in ('completed', 'failed', 'cancelled', 'complete'):
        return {
            'ok': False,
            'error': 'already_finished',
            'detail': f'Job is already {status}; refusing to fake a cancel.',
            'status': status,
        }, 409

    prompt_id = ''
    endpoint = ''
    if job:
        prompt_id = str(job.get('prompt_id') or '')
        endpoint = str(job.get('endpoint') or '')
    if expansion_job and not prompt_id:
        try:
            from expansion.capabilities.comfy_submit import prompt_id_from_job, endpoint_from_job
            prompt_id = prompt_id_from_job(expansion_job)
            endpoint = endpoint_from_job(expansion_job)
        except Exception:
            pass

    if not prompt_id:
        # Never reached Comfy — local cancel is enough.
        if job:
            job = dict(job)
            job['status'] = 'cancelled'
            job['stage'] = 'cancelled'
            job['error'] = 'Cancelled before Comfy received the prompt.'
            _upsert_job(job, layout)
        if expansion_job:
            try:
                from expansion.jobs import JobStore, JobStatus
                JobStore(layout=layout).transition(
                    jid, JobStatus.CANCELLED.value, error='Cancelled before Comfy submit',
                )
            except Exception:
                pass
        return {
            'ok': True,
            'gpu_stopped': False,
            'queue_state': 'not_submitted',
            'action': 'mark_cancelled',
            'id': jid,
        }, 200

    result = cancel_comfy_prompt(prompt_id=prompt_id, endpoint=endpoint or None)
    if not result.get('ok'):
        return {
            'ok': False,
            'error': result.get('error') or 'cancel_failed',
            'detail': result.get('detail') or '',
            'queue_state': result.get('queue_state') or '',
            'prompt_id': prompt_id,
        }, int(result.get('http_status') or 502)

    if job:
        job = dict(job)
        job['status'] = 'cancelled'
        job['stage'] = 'cancelled'
        job['error'] = 'Cancelled — GPU stop requested.'
        job['cancel'] = {
            'queue_state': result.get('queue_state'),
            'action': result.get('action'),
            'gpu_stopped': result.get('gpu_stopped'),
        }
        _upsert_job(job, layout)
    if expansion_job:
        try:
            from expansion.jobs import JobStore, JobStatus
            JobStore(layout=layout).transition(
                jid,
                JobStatus.CANCELLED.value,
                error='Cancelled by Workshop — Comfy interrupt/queue delete',
            )
        except Exception:
            pass

    return {
        'ok': True,
        'gpu_stopped': bool(result.get('gpu_stopped')),
        'queue_state': result.get('queue_state') or '',
        'action': result.get('action') or '',
        'prompt_id': prompt_id,
        'id': jid,
    }, 200


def handle_workshop_write(
    method: str,
    path: str,
    data: dict[str, Any],
    send_json: SendJson,
) -> bool:
    """POST/PUT/DELETE for Keep Workshop API shapes."""
    if not path.startswith('/video-studio/api/'):
        return False
    _seed_actors_styles()
    layout = resolve_layout()
    rel = path[len('/video-studio/api/'):].strip('/')
    method = (method or 'POST').upper()

    if rel == 'actors' and method == 'POST':
        actors = _load_list(_actors_path(layout))
        aid = str(data.get('id') or uuid.uuid4().hex[:10])
        actor = {
            'id': aid,
            'name': str(data.get('name') or data.get('label') or 'Actor'),
            'note': str(data.get('note') or ''),
            'description': str(data.get('description') or data.get('note') or ''),
            'personality': str(data.get('personality') or ''),
            'images': data.get('images') or {},
            'ref_slots': data.get('ref_slots') or {},
            'reference_images': data.get('reference_images') or [],
            'created_at': time.time(),
        }
        actors.insert(0, actor)
        _save_list(_actors_path(layout), actors)
        send_json(actor)
        return True

    m = re.match(r'actors/([^/]+)/generate-portrait$', rel)
    if m and method == 'POST':
        aid = unquote(m.group(1))
        actors = _load_list(_actors_path(layout))
        actor = next((a for a in actors if a.get('id') == aid), None)
        if not actor:
            send_json({'error': 'actor not found'}, 404)
            return True
        prompt = _portrait_prompt_for_actor(actor)
        job = _create_image_job(
            prompt=prompt,
            width=704,
            height=1216,
            negative='blurry, low quality, watermark, duplicate, montage, poster',
            actor_ids=[aid],
            style_id='',
            layout=layout,
        )
        for i, a in enumerate(actors):
            if a.get('id') == aid:
                actors[i] = {
                    **a,
                    'portrait_job_id': job['id'],
                    'portrait_status': 'failed' if job.get('status') == 'failed' else 'generating',
                    'portrait_error': job.get('error') or '',
                }
                actor = actors[i]
                break
        _save_list(_actors_path(layout), actors)
        code = 200 if job.get('status') != 'failed' else 409
        send_json({
            'ok': job.get('status') != 'failed',
            'id': job['id'],
            'job_id': job['id'],
            'actor': actor,
            'status': job.get('status'),
            'error': job.get('error') or '',
        }, code)
        return True

    m = re.match(r'actors/([^/]+)/reference-image$', rel)
    if m and method == 'POST':
        aid = unquote(m.group(1))
        actors = _load_list(_actors_path(layout))
        actor = next((a for a in actors if a.get('id') == aid), None)
        if not actor:
            send_json({'error': 'actor not found'}, 404)
            return True
        files = data.get('_files') if isinstance(data.get('_files'), dict) else {}
        file_info = files.get('file') or files.get('image') or {}
        raw = file_info.get('data') if isinstance(file_info, dict) else None
        if not isinstance(raw, (bytes, bytearray)) or not raw:
            send_json({'error': 'file required'}, 400)
            return True
        role = str(data.get('role') or 'display_headshot').strip() or 'display_headshot'
        orig = str(file_info.get('filename') or 'ref.png')
        ext = Path(orig).suffix.lower() or '.png'
        if ext not in ('.png', '.jpg', '.jpeg', '.webp', '.gif'):
            ext = '.png'
        safe_name = f'{role}{ext}'
        dest_dir = _actors_media_dir(layout) / aid
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / safe_name
        dest.write_bytes(bytes(raw))
        url = f'/video-studio/api/actors/{aid}/media/{safe_name}'
        imgs = dict(actor.get('images') or {})
        slots = dict(actor.get('ref_slots') or {})
        if role == 'display_headshot':
            imgs['display_headshot'] = url
            slots['face_closeup'] = url
        elif role == 'generation_reference':
            imgs['generation_reference'] = url
            slots['canonical_fullbody'] = url
        else:
            imgs[role] = url
            slots[role] = url
        for i, a in enumerate(actors):
            if a.get('id') == aid:
                actors[i] = {**a, 'images': imgs, 'ref_slots': slots}
                actor = actors[i]
                break
        _save_list(_actors_path(layout), actors)
        send_json({'ok': True, 'actor': actor, 'url': url})
        return True

    m = re.match(r'actors/([^/]+)$', rel)
    if m:
        aid = unquote(m.group(1))
        actors = _load_list(_actors_path(layout))
        if method == 'DELETE':
            actors = [a for a in actors if a.get('id') != aid]
            _save_list(_actors_path(layout), actors)
            send_json({'ok': True})
            return True
        if method in ('PUT', 'POST', 'PATCH'):
            updated = None
            for i, a in enumerate(actors):
                if a.get('id') == aid:
                    actors[i] = {**a, **{k: v for k, v in data.items() if k != 'id'}, 'id': aid}
                    updated = actors[i]
                    break
            if not updated:
                send_json({'error': 'not found'}, 404)
                return True
            _save_list(_actors_path(layout), actors)
            send_json(updated)
            return True

    if rel == 'styles' and method == 'POST':
        styles = _load_list(_styles_path(layout))
        sid = str(data.get('id') or uuid.uuid4().hex[:10])
        style = {
            'id': sid,
            'name': str(data.get('name') or data.get('label') or 'Style'),
            'prompt': str(data.get('prompt') or data.get('note') or data.get('description') or ''),
            'description': str(data.get('description') or data.get('prompt') or data.get('note') or ''),
            'created_at': time.time(),
        }
        styles.insert(0, style)
        _save_list(_styles_path(layout), styles)
        send_json(style)
        return True

    m = re.match(r'styles/([^/]+)$', rel)
    if m:
        sid = unquote(m.group(1))
        styles = _load_list(_styles_path(layout))
        if method == 'DELETE':
            styles = [s for s in styles if s.get('id') != sid]
            _save_list(_styles_path(layout), styles)
            send_json({'ok': True})
            return True
        if method in ('PUT', 'POST', 'PATCH'):
            updated = None
            for i, s in enumerate(styles):
                if s.get('id') == sid:
                    styles[i] = {**s, **{k: v for k, v in data.items() if k != 'id'}, 'id': sid}
                    updated = styles[i]
                    break
            if not updated:
                send_json({'error': 'not found'}, 404)
                return True
            _save_list(_styles_path(layout), styles)
            send_json(updated)
            return True

    if rel == 'generate-image-v1' and method == 'POST':
        prompt = str(data.get('prompt') or '').strip()
        if not prompt:
            send_json({'ok': False, 'error': 'prompt required'}, 400)
            return True
        try:
            width = int(data.get('width') or 1024)
            height = int(data.get('height') or 1024)
        except (TypeError, ValueError):
            width, height = 1024, 1024
        actor_ids = data.get('actor_ids') or []
        if isinstance(actor_ids, str):
            actor_ids = [actor_ids]
        job = _create_image_job(
            prompt=prompt,
            width=width,
            height=height,
            negative=str(data.get('negative') or ''),
            actor_ids=list(actor_ids),
            style_id=str(data.get('style_id') or ''),
            layout=layout,
        )
        code = 200 if job.get('status') != 'failed' else 409
        send_json({
            'ok': job.get('status') != 'failed',
            'id': job['id'],
            'job_id': job['id'],
            'job': job,
            'status': job.get('status'),
            'error': job.get('error') or '',
        }, code)
        return True

    if rel == 'generate-music-v1' and method == 'POST':
        tags = str(data.get('tags') or data.get('prompt') or data.get('description') or '').strip()
        if not tags:
            send_json({'ok': False, 'error': 'tags required'}, 400)
            return True
        try:
            duration = float(data.get('duration') or 60)
        except (TypeError, ValueError):
            duration = 60.0
        bpm_raw = data.get('bpm')
        try:
            bpm = float(bpm_raw) if bpm_raw not in (None, '', 'null') else None
        except (TypeError, ValueError):
            bpm = None
        seed_raw = data.get('seed')
        try:
            seed = int(seed_raw) if seed_raw not in (None, '', 'null', '-1') else None
        except (TypeError, ValueError):
            seed = None
        job = _create_music_job(
            tags=tags,
            lyrics=str(data.get('lyrics') or ''),
            duration=duration,
            bpm=bpm,
            seed=seed,
            tuning={
                'cfg_scale': data.get('cfg_scale') or data.get('cfg') or 2,
                'key_scale': data.get('key_scale') or data.get('key') or '',
                'time_signature': data.get('time_signature') or '4',
                'language': data.get('language') or 'en',
                'max_duration_sec': 120,
            },
            layout=layout,
        )
        code = 200 if job.get('status') != 'failed' else 409
        send_json({
            'ok': job.get('status') != 'failed',
            'id': job['id'],
            'job_id': job['id'],
            'job': job,
            'status': job.get('status'),
            'error': job.get('error') or '',
            'action': job.get('action') or '',
            'soft_block': bool(job.get('soft_block')),
        }, code)
        return True

    if rel == 'install-packs' and method == 'POST':
        from expansion.capabilities.studio_packs import start_pack_install
        which = data.get('which')
        if isinstance(which, str):
            which = [which]
        if which is not None and not isinstance(which, list):
            which = None
        out = start_pack_install(layout=layout, which=which)
        send_json(out, 200 if out.get('started') or out.get('running') or out.get('ok') else 409)
        return True

    if rel == 'music-prompt-assist' and method == 'POST':
        desc = str(data.get('description') or data.get('prompt') or '').strip()
        send_json({
            'ok': True,
            'prompt': desc or 'cinematic ambient score, slow pulse, analog warmth',
            'lyrics': data.get('lyrics') or '',
            'bpm': data.get('bpm') or 90,
            'key': data.get('key') or 'Am',
        })
        return True

    if rel == 'expand-scene' and method == 'POST':
        scene = str(data.get('scene') or data.get('prompt') or '').strip()
        send_json({
            'ok': True,
            'expanded': scene,
            'prompt': scene,
            'negative': 'blurry, low quality, watermark',
        })
        return True

    if rel in ('write', 'scripts') and method == 'POST':
        send_json({
            'ok': True,
            'text': str(data.get('prompt') or data.get('text') or ''),
            'note': 'Write/script full pipeline ships with Keep executor; Expansion stores draft.',
        })
        return True

    # Video generate — Wan 2.2 TI2V text-to-video (image-conditioned variants: 501).
    if rel in (
        'generate-v2-start-end', 'generate-v2-auto-start-end',
        'generate-h3', 'generate-hidream-v1',
    ) and method == 'POST':
        send_json({
            'ok': False,
            'error': 'submitter_not_implemented',
            'detail': (
                'This video mode needs an image-conditioned Wan graph that is not wired yet. '
                'Use text-to-video Generate (or generate-v2 / generate-v2-direct-t2v) instead.'
            ),
            'projects_ready': False,
        }, 501)
        return True

    if rel in ('generate', 'generate-v2', 'generate-v2-direct-t2v') and method == 'POST':
        prompt = str(data.get('prompt') or data.get('positive') or '').strip()
        if not prompt:
            send_json({'ok': False, 'error': 'prompt required'}, 400)
            return True
        try:
            width = int(data.get('width') or 512)
            height = int(data.get('height') or 320)
        except (TypeError, ValueError):
            width, height = 512, 320
        try:
            frames = int(data.get('frames') or data.get('length') or 25)
        except (TypeError, ValueError):
            frames = 25
        try:
            fps = int(data.get('fps') or 16)
        except (TypeError, ValueError):
            fps = 16
        try:
            steps = int(data.get('steps') or 20)
        except (TypeError, ValueError):
            steps = 20
        job = _create_video_job(
            prompt=prompt,
            negative=str(data.get('negative') or ''),
            width=width,
            height=height,
            frames=frames,
            fps=fps,
            steps=steps,
            layout=layout,
        )
        code = 200 if job.get('status') != 'failed' else int(
            409 if job.get('soft_block') or job.get('action') == 'install_packs' else 502
        )
        send_json({
            'ok': job.get('status') != 'failed',
            'id': job['id'],
            'job_id': job['id'],
            'job': job,
            'status': job.get('status'),
            'prompt_id': job.get('prompt_id') or '',
            'error': job.get('error') or '',
            'detail': job.get('error') or '',
            'action': job.get('action') or '',
            'soft_block': bool(job.get('soft_block')),
        }, code)
        return True

    if rel.startswith('projects') and method == 'POST':
        send_json({
            'ok': False,
            'error': 'movie_production_pending',
            'detail': (
                'Project / movie production is not wired in Expansion yet '
                '(Keep-parity UI only). Image, video, and music generate still work.'
            ),
            'projects_ready': False,
        }, 501)
        return True

    m = re.match(r'jobs/([^/]+)/cancel$', rel)
    if m and method in ('POST', 'DELETE'):
        body, code = _cancel_job(unquote(m.group(1)), layout)
        send_json(body, code)
        return True

    m = re.match(r'jobs/([^/]+)$', rel)
    if m and method == 'DELETE':
        # Legacy Cancel button sent bare DELETE /jobs/<id> (not purge).
        body, code = _cancel_job(unquote(m.group(1)), layout)
        send_json(body, code)
        return True

    m = re.match(r'jobs/([^/]+)/purge$', rel)
    if m and method in ('POST', 'DELETE'):
        jid = unquote(m.group(1))
        jobs = [j for j in _workshop_jobs(layout) if j.get('id') != jid]
        _save_jobs(jobs, layout)
        send_json({'ok': True})
        return True

    send_json({'error': 'not found', 'path': path, 'method': method}, 404)
    return True


def parse_form_or_json(handler) -> dict[str, Any]:
    """Parse JSON or multipart/form-data body from BaseHTTPRequestHandler."""
    ctype = (handler.headers.get('Content-Type') or '').lower()
    n = int(handler.headers.get('Content-Length') or 0)
    raw = handler.rfile.read(n) if n else b''
    if 'application/json' in ctype or (not ctype and raw[:1] in (b'{', b'[')):
        try:
            return json.loads(raw.decode('utf-8') or '{}')
        except json.JSONDecodeError:
            return {}
    if 'multipart/form-data' in ctype:
        return _parse_multipart(ctype, raw)
    if 'application/x-www-form-urlencoded' in ctype:
        from urllib.parse import parse_qs
        qs = parse_qs(raw.decode('utf-8', errors='replace'), keep_blank_values=True)
        return {k: (v[0] if len(v) == 1 else v) for k, v in qs.items()}
    try:
        return json.loads(raw.decode('utf-8') or '{}')
    except Exception:
        return {}


def _parse_multipart(content_type: str, raw: bytes) -> dict[str, Any]:
    """Minimal multipart parser (text fields + file metadata). No cgi dependency."""
    m = re.search(r'boundary=([^;\s]+)', content_type, re.I)
    if not m:
        return {}
    boundary = m.group(1).strip().strip('"').encode('ascii', errors='ignore')
    if not boundary:
        return {}
    out: dict[str, Any] = {}
    parts = raw.split(b'--' + boundary)
    for part in parts:
        if not part or part in (b'--', b'--\r\n', b'\r\n'):
            continue
        if part.startswith(b'--'):
            continue
        if part.startswith(b'\r\n'):
            part = part[2:]
        header_blob, _, body = part.partition(b'\r\n\r\n')
        if not body and b'\n\n' in part:
            header_blob, _, body = part.partition(b'\n\n')
        headers = header_blob.decode('utf-8', errors='replace')
        # strip trailing boundary CRLF
        if body.endswith(b'\r\n'):
            body = body[:-2]
        disp = ''
        for line in headers.splitlines():
            if line.lower().startswith('content-disposition:'):
                disp = line
                break
        name_m = re.search(r'name="([^"]+)"', disp)
        if not name_m:
            continue
        key = name_m.group(1)
        file_m = re.search(r'filename="([^"]*)"', disp)
        if file_m is not None:
            out.setdefault('_files', {})[key] = {
                'filename': file_m.group(1),
                'bytes': len(body),
                'data': body,
            }
            continue
        val = body.decode('utf-8', errors='replace')
        if key in out:
            prev = out[key]
            if isinstance(prev, list):
                prev.append(val)
            else:
                out[key] = [prev, val]
        else:
            out[key] = val
    return out
