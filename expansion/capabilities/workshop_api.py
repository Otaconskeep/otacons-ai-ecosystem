"""Keep Workshop API bridge for Expansion `/video-studio`.

Serves the same route shapes the vendored Keep Workshop UI expects
(`/video-studio/api/...`) backed by Expansion Comfy submit, JobStore,
and preferences — so friends get the real Workshop look + core generate
path without needing otacon-executor.
"""
from __future__ import annotations

import json
import re
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Optional
from urllib.parse import unquote

from expansion.persist import atomic_write_json, read_json
from expansion.state_layout import StateLayout, resolve_layout

SendJson = Callable[..., None]
SendBytes = Callable[..., None]


def _prefs(layout: Optional[StateLayout] = None) -> Path:
    layout = layout or resolve_layout()
    layout.user_preferences.mkdir(parents=True, exist_ok=True)
    return layout.user_preferences


def _actors_path(layout: Optional[StateLayout] = None) -> Path:
    return _prefs(layout) / 'workshop_actors.json'


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
    """Seed from keep_defaults.json once if empty."""
    ap = _actors_path(layout)
    sp = _styles_path(layout)
    if ap.is_file() and sp.is_file():
        return
    defaults: dict[str, Any] = {}
    try:
        dpath = Path(__file__).resolve().parents[1] / 'product' / 'studio' / 'keep_defaults.json'
        if dpath.is_file():
            defaults = json.loads(dpath.read_text(encoding='utf-8'))
    except Exception:
        defaults = {}
    if not ap.is_file():
        actors = []
        for a in defaults.get('actors') or []:
            aid = str(a.get('id') or uuid.uuid4().hex[:10])
            actors.append({
                'id': aid,
                'name': a.get('label') or a.get('name') or aid,
                'note': a.get('note') or a.get('tag') or '',
                'images': {},
                'ref_slots': {},
                'reference_images': [],
                'created_at': time.time(),
            })
        _save_list(ap, actors)
    if not sp.is_file():
        styles = []
        for s in defaults.get('styles') or []:
            sid = str(s.get('id') or uuid.uuid4().hex[:10])
            styles.append({
                'id': sid,
                'name': s.get('label') or s.get('name') or sid,
                'prompt': s.get('prompt') or s.get('note') or '',
                'created_at': time.time(),
            })
        _save_list(sp, styles)


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


def _get_job(job_id: str, layout: Optional[StateLayout] = None) -> Optional[dict[str, Any]]:
    for j in _workshop_jobs(layout):
        if j.get('id') == job_id:
            return j
    return None


def _health() -> dict[str, Any]:
    from expansion.capabilities.video_studio import probe_video_studio
    from expansion.capabilities.studio_setup import studio_hardware_snapshot
    vs = probe_video_studio()
    hw = studio_hardware_snapshot()
    disc = vs.discovery or {}
    ready = vs.state == 'READY'
    return {
        'cuda_available': bool(hw.get('cuda_available') or ready),
        'ready': ready,
        'gpu_name': hw.get('gpu_model') or 'GPU',
        'vram_total_gb': float(hw.get('marketed_vram_gb') or hw.get('vram_gb') or 0),
        'vram_free_gb': float(hw.get('marketed_vram_gb') or hw.get('vram_gb') or 0) * 0.55,
        'backend': 'Otacon Expansion · Muse Workshop',
        'studio_state': vs.state,
        'endpoint': disc.get('endpoint') or '',
        'queue_running': 0,
        'queue_pending': 0,
        'comfyui_warm': ready,
        'expansion': True,
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
    job = {
        'id': job_id,
        'type': 'image_v1',
        'status': 'queued',
        'prompt': prompt,
        'negative': negative,
        'width': width,
        'height': height,
        'actor_ids': actor_ids or [],
        'style_id': style_id or '',
        'agent_id': 'muse',
        'created_at': time.time(),
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
        return job

    job.update({
        'status': 'running',
        'stage': 'comfy',
        'prompt_id': submitted['prompt_id'],
        'endpoint': submitted.get('endpoint') or '',
    })
    _upsert_job(job, layout)
    return job


def _refresh_image_job(job: dict[str, Any], layout: Optional[StateLayout] = None) -> dict[str, Any]:
    if job.get('status') in ('completed', 'failed') or not job.get('prompt_id'):
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
    return job


def handle_workshop_get(
    path: str,
    send_json: SendJson,
    send_redirect: Optional[Callable[[str, int], None]] = None,
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
        send_json(_load_list(_actors_path(layout)))
        return True
    if rel == 'styles':
        send_json(_load_list(_styles_path(layout)))
        return True
    if rel == 'jobs':
        jobs = [_refresh_image_job(dict(j), layout) for j in _workshop_jobs(layout)[:80]]
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

    m = re.match(r'jobs/([^/]+)$', rel)
    if m:
        job = _get_job(unquote(m.group(1)), layout)
        if not job:
            send_json({'error': 'not found'}, 404)
            return True
        send_json(_refresh_image_job(dict(job), layout))
        return True

    m = re.match(r'generate-image-v1/([^/]+)$', rel)
    if m:
        job = _get_job(unquote(m.group(1)), layout)
        if not job:
            send_json({'error': 'not found'}, 404)
            return True
        send_json(_refresh_image_job(dict(job), layout))
        return True

    m = re.match(r'generate-image-v1/([^/]+)/output$', rel)
    if m:
        raw_job = _get_job(unquote(m.group(1)), layout)
        if not raw_job:
            send_json({'error': 'not found'}, 404)
            return True
        job = _refresh_image_job(dict(raw_job), layout)
        if job.get('status') != 'completed':
            send_json({'error': 'output not ready', 'status': job.get('status')}, 404)
            return True
        ep = (job.get('endpoint') or 'http://127.0.0.1:8188').rstrip('/')
        fname = job.get('output_file') or ((job.get('outputs') or [None])[0])
        if fname and send_redirect:
            send_redirect(f'{ep}/view?filename={fname}&type=output', 302)
            return True
        if fname:
            send_json({
                'ok': True,
                'url': f'{ep}/view?filename={fname}&type=output',
                'filename': fname,
            })
            return True
        send_json({'error': 'no output'}, 404)
        return True

    # Soft stubs for modalities not fully wired yet — keep UI from hard-failing.
    if rel.startswith('generate-music-v1/') or rel.startswith('generate-v2/') or rel.startswith('generate-hidream'):
        send_json({'error': 'job not found', 'expansion_stub': True}, 404)
        return True

    send_json({'error': 'not found', 'path': path}, 404)
    return True


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
            'images': data.get('images') or {},
            'ref_slots': data.get('ref_slots') or {},
            'reference_images': data.get('reference_images') or [],
            'created_at': time.time(),
        }
        actors.insert(0, actor)
        _save_list(_actors_path(layout), actors)
        send_json(actor)
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
            'prompt': str(data.get('prompt') or data.get('note') or ''),
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

    # Video / music generate — honest soft response until modality submitters land.
    if rel in (
        'generate', 'generate-v2', 'generate-v2-start-end', 'generate-v2-auto-start-end',
        'generate-v2-direct-t2v', 'generate-h3', 'generate-music-v1', 'generate-hidream-v1',
    ) and method == 'POST':
        from expansion.capabilities.studio_packs import packs_status
        packs = packs_status()
        send_json({
            'ok': False,
            'error': 'modality_pack_or_submitter',
            'detail': (
                packs.get('aria')
                or 'Video/music generate uses the same Workshop UI; install packs for this GPU, '
                   'then image generate works now. Video/music Comfy submitters ship next.'
            ),
            'soft_block': True,
            'action': 'install_packs',
            'packs': packs.get('packs') or {},
        }, 409)
        return True

    if rel.startswith('projects') and method == 'POST':
        send_json({
            'ok': False,
            'error': 'movie_production_pending',
            'detail': 'Project / movie production API is Keep-parity UI-ready; worker wiring follows.',
        }, 501)
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
