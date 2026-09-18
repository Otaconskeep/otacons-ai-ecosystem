"""ComfyUI prompt submitter for Expansion Muse Creative.

Honest contract:
  - Never invent RUNNING creative jobs without a Comfy /prompt prompt_id.
  - Probe required models before queueing.
  - Fail stale fake creative jobs that lack prompt_id evidence.
"""
from __future__ import annotations

import json
import os
import random
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Optional

from expansion.capabilities.video_studio import probe_video_studio
from expansion.jobs import JobStatus, JobStore
from expansion.state_layout import StateLayout, resolve_layout

_DEFAULT_UNET = 'z_image_turbo_bf16.safetensors'
_DEFAULT_CLIP = 'qwen_3_4b.safetensors'
_DEFAULT_VAE = 'ae.safetensors'
_EVIDENCE_PROMPT = 'comfy:prompt_id='
_POLL_LOCK = threading.Lock()
_POLL_STARTED = False


def _studio_endpoint() -> str:
    vs = probe_video_studio(clear_stale=False)
    disc = vs.discovery or {}
    return str(disc.get('endpoint') or os.environ.get('OTACON_COMFY_URL') or 'http://127.0.0.1:8188').rstrip('/')


def _http_json(method: str, url: str, body: Optional[dict] = None, timeout: float = 30.0) -> tuple[int, Any]:
    data = None
    headers = {'Accept': 'application/json'}
    if body is not None:
        data = json.dumps(body).encode('utf-8')
        headers['Content-Type'] = 'application/json'
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode('utf-8', errors='replace')
            try:
                parsed = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                parsed = {'raw': raw}
            return int(resp.status), parsed
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode('utf-8', errors='replace') if exc.fp else ''
        try:
            parsed = json.loads(raw) if raw else {'error': str(exc)}
        except json.JSONDecodeError:
            parsed = {'error': raw or str(exc)}
        return int(exc.code), parsed
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return 0, {'error': str(exc)}


def list_models(endpoint: str, kind: str) -> list[str]:
    code, data = _http_json('GET', f'{endpoint}/models/{kind}', timeout=8.0)
    if code == 200 and isinstance(data, list):
        return [str(x) for x in data]
    return []


def image_workflow_status(endpoint: Optional[str] = None) -> dict[str, Any]:
    """Probe whether Z-Image Turbo assets exist on the live ComfyUI."""
    ep = (endpoint or _studio_endpoint()).rstrip('/')
    unets = list_models(ep, 'diffusion_models') or list_models(ep, 'unet')
    clips = list_models(ep, 'text_encoders') or list_models(ep, 'clip')
    vaes = list_models(ep, 'vae')
    # Prefer lighter indexed files first (8 GB laptop path → nvfp4 / fp4).
    unet = ''
    for candidate in (
        'z_image_turbo_nvfp4.safetensors',
        'z_image_turbo_int8_convrot.safetensors',
        _DEFAULT_UNET,
    ):
        hit = next((u for u in unets if u == candidate or u.endswith('/' + candidate)), '')
        if hit:
            unet = hit
            break
    if not unet:
        unet = next((u for u in unets if 'z_image' in u.lower()), '')
    clip = ''
    for candidate in (
        'qwen_3_4b_fp4_mixed.safetensors',
        'qwen_3_4b_fp8_mixed.safetensors',
        _DEFAULT_CLIP,
    ):
        hit = next((c for c in clips if c == candidate or c.endswith('/' + candidate)), '')
        if hit:
            clip = hit
            break
    if not clip:
        clip = next((c for c in clips if 'qwen_3_4b' in c.lower()), '')
    vae = next((v for v in vaes if v == _DEFAULT_VAE or v.endswith('/ae.safetensors') or v == 'ae.safetensors'), '')
    if not vae and _DEFAULT_VAE in vaes:
        vae = _DEFAULT_VAE
    ready = bool(unet and clip and vae)
    missing = []
    if not unet:
        missing.append('diffusion_models/z_image_turbo_*.safetensors')
    if not clip:
        missing.append('text_encoders/qwen_3_4b*.safetensors')
    if not vae:
        missing.append('vae/ae.safetensors')
    return {
        'ok': ready,
        'modality': 'image',
        'engine': 'z-image-turbo',
        'endpoint': ep,
        'unet': unet,
        'clip': clip,
        'vae': vae,
        'missing': missing,
        'assets_ready': ready,
        'detail': (
            'Z-Image assets indexed by ComfyUI'
            if ready
            else ('Studio connected, but image workflow models are not installed yet: ' + ', '.join(missing))
        ),
    }


def build_z_image_prompt(
    *,
    positive: str,
    negative: str = '',
    width: int = 1024,
    height: int = 1024,
    steps: int = 8,
    cfg: float = 1.0,
    seed: Optional[int] = None,
    unet: str = _DEFAULT_UNET,
    clip: str = _DEFAULT_CLIP,
    vae: str = _DEFAULT_VAE,
    filename_prefix: str = 'otacon_muse',
) -> dict[str, Any]:
    """API-format graph matching Keep workshop Z-Image Turbo."""
    seed_i = int(seed) if seed is not None else random.randint(1, 2**31 - 1)
    # Negative conditioning: zero-out positive when no negative text (Keep pattern).
    graph = {
        '30': {
            'class_type': 'CLIPLoader',
            'inputs': {'clip_name': clip, 'type': 'lumina2', 'device': 'default'},
        },
        '29': {
            'class_type': 'VAELoader',
            'inputs': {'vae_name': vae},
        },
        '28': {
            'class_type': 'UNETLoader',
            'inputs': {'unet_name': unet, 'weight_dtype': 'default'},
        },
        '27': {
            'class_type': 'CLIPTextEncode',
            'inputs': {'text': positive, 'clip': ['30', 0]},
        },
        '33': {
            'class_type': 'ConditioningZeroOut',
            'inputs': {'conditioning': ['27', 0]},
        },
        '13': {
            'class_type': 'EmptySD3LatentImage',
            'inputs': {'width': int(width), 'height': int(height), 'batch_size': 1},
        },
        '11': {
            'class_type': 'ModelSamplingAuraFlow',
            'inputs': {'model': ['28', 0], 'shift': 3},
        },
        '3': {
            'class_type': 'KSampler',
            'inputs': {
                'model': ['11', 0],
                'positive': ['27', 0],
                'negative': ['33', 0],
                'latent_image': ['13', 0],
                'seed': seed_i,
                'steps': int(steps),
                'cfg': float(cfg),
                'sampler_name': 'res_multistep',
                'scheduler': 'simple',
                'denoise': 1,
            },
        },
        '8': {
            'class_type': 'VAEDecode',
            'inputs': {'samples': ['3', 0], 'vae': ['29', 0]},
        },
        '9': {
            'class_type': 'SaveImage',
            'inputs': {'images': ['8', 0], 'filename_prefix': filename_prefix},
        },
    }
    if (negative or '').strip():
        graph['34'] = {
            'class_type': 'CLIPTextEncode',
            'inputs': {'text': negative.strip(), 'clip': ['30', 0]},
        }
        graph['3']['inputs']['negative'] = ['34', 0]
    return graph


def submit_image_job(
    *,
    prompt: str,
    negative: str = '',
    tuning: Optional[dict] = None,
    endpoint: Optional[str] = None,
    client_id: str = 'otacon-expansion-muse',
) -> dict[str, Any]:
    """Submit Z-Image to ComfyUI. Returns ok+prompt_id or honest error (no job side effects)."""
    from expansion.capabilities.video_studio import comfy_endpoint_healthy

    # Do not clear stale prefs during submit — a transient probe must not wipe
    # a working endpoint between UI READY and Generate.
    vs = probe_video_studio(clear_stale=False)
    disc = vs.discovery or {}
    ep = (endpoint or disc.get('endpoint') or _studio_endpoint()).rstrip('/')
    ok, health_detail = comfy_endpoint_healthy(ep, timeout=4.0)
    if not ok:
        try:
            from expansion.capabilities.comfy_sidecar import detect_local_comfy
            detected = detect_local_comfy(timeout=2.0)
            cand = str((detected or {}).get('endpoint') or '').rstrip('/')
            if cand:
                ok2, detail2 = comfy_endpoint_healthy(cand, timeout=4.0)
                if ok2:
                    ep = cand
                    ok, health_detail = True, detail2
                    try:
                        from expansion.capabilities.comfy_sidecar import save_studio_endpoint
                        save_studio_endpoint(ep)
                    except Exception:
                        pass
        except Exception:
            pass
    if not ok:
        return {
            'ok': False,
            'queued': False,
            'error': 'creative workflow submitter: ComfyUI not reachable',
            'detail': (
                'Image generate needs a live ComfyUI. '
                f'Last check: {health_detail}. '
                'Open Creative → Set Up if Studio shows SETUP, or start Comfy on :8188.'
            ),
            'studio_state': vs.state,
            'endpoint': ep,
            'http_status': 503,
        }
    probe = image_workflow_status(ep)
    if not probe.get('ok'):
        try:
            from expansion.capabilities.studio_packs import soft_block_payload
            block = soft_block_payload()
        except Exception:
            block = {
                'ok': False,
                'queued': False,
                'soft_block': True,
                'action': 'install_packs',
                'error': 'creative_packs_needed',
                'detail': probe.get('detail') or (
                    'Creative packs are not installed yet. Tap Install packs — '
                    'Generate stays quiet until packs are ready.'
                ),
                'http_status': 409,
            }
        block.update({
            'missing': probe.get('missing') or [],
            'studio_state': vs.state,
            'endpoint': ep,
            'workflow': probe,
        })
        return block
    tuning = tuning if isinstance(tuning, dict) else {}
    width, height = 1024, 1024
    res = str(tuning.get('resolution') or '').lower()
    if '1280x720' in res or res == '1280x720':
        width, height = 1280, 720
    elif '768x1344' in res:
        width, height = 768, 1344
    elif 'x' in res:
        try:
            a, b = res.split('x', 1)
            width, height = int(a), int(b)
        except ValueError:
            pass
    aspect = str(tuning.get('aspect') or '')
    if aspect == '16:9':
        width, height = 1280, 720
    elif aspect == '9:16':
        width, height = 768, 1344
    elif aspect == '1:1':
        width, height = 1024, 1024
    seed = tuning.get('seed')
    try:
        seed_i = int(seed) if seed not in (None, '', 'random') else None
    except (TypeError, ValueError):
        seed_i = None
    try:
        steps = int(tuning.get('steps') or 8)
    except (TypeError, ValueError):
        steps = 8
    try:
        cfg = float(tuning.get('cfg') or 1)
    except (TypeError, ValueError):
        cfg = 1.0

    graph = build_z_image_prompt(
        positive=prompt,
        negative=negative,
        width=width,
        height=height,
        steps=max(1, min(steps, 50)),
        cfg=cfg,
        seed=seed_i,
        unet=probe['unet'],
        clip=probe['clip'],
        vae=probe['vae'],
    )
    code, data = _http_json(
        'POST',
        f'{ep}/prompt',
        {'prompt': graph, 'client_id': client_id},
        timeout=60.0,
    )
    prompt_id = ''
    if isinstance(data, dict):
        prompt_id = str(data.get('prompt_id') or '')
    if code != 200 or not prompt_id:
        err = ''
        if isinstance(data, dict):
            err = str(data.get('error') or data.get('node_errors') or data)
        return {
            'ok': False,
            'queued': False,
            'soft_block': True,
            'error': 'comfy_prompt_not_accepted',
            'detail': (
                'ComfyUI did not accept that graph — usually a missing custom node '
                'or model path. Open ComfyUI / Install packs, then try again. '
                f'Technical: {err[:400]}'
            ),
            'studio_state': vs.state,
            'endpoint': ep,
            'http_status': 502 if code else 503,
            'comfy_status': code,
        }
    return {
        'ok': True,
        'queued': True,
        'prompt_id': prompt_id,
        'endpoint': ep,
        'studio_state': vs.state,
        'engine': 'z-image-turbo',
        'modality': 'image',
        'workflow': probe,
        'message': f'Submitted to ComfyUI · prompt_id={prompt_id}',
    }


def prompt_id_from_job(job) -> str:
    for item in (getattr(job, 'evidence', None) or []):
        s = str(item)
        if s.startswith(_EVIDENCE_PROMPT):
            return s[len(_EVIDENCE_PROMPT):]
    return ''


def endpoint_from_job(job) -> str:
    for item in (getattr(job, 'evidence', None) or []):
        s = str(item)
        if s.startswith('comfy:endpoint='):
            return s.split('=', 1)[1].rstrip('/')
    return _studio_endpoint()


def outputs_from_job(job) -> list[str]:
    files: list[str] = []
    for item in (getattr(job, 'evidence', None) or []):
        s = str(item)
        if s.startswith('comfy:output='):
            files.append(s.split('=', 1)[1])
    # Also parse "ComfyUI outputs: a.png, b.png" from result text.
    result = str(getattr(job, 'result', '') or '')
    if 'ComfyUI outputs:' in result and not files:
        tail = result.split('ComfyUI outputs:', 1)[1]
        files = [x.strip() for x in tail.split(',') if x.strip()]
    return files


def comfy_view_url(endpoint: str, filename: str) -> str:
    """Direct Comfy /view URL — browser clients often get 403; prefer proxy routes."""
    ep = (endpoint or _studio_endpoint()).rstrip('/')
    from urllib.parse import quote
    return f'{ep}/view?filename={quote(filename)}&type=output'


def comfy_output_roots() -> list[Path]:
    roots: list[Path] = []
    env = (os.environ.get('COMFYUI_OUTPUT_DIR') or os.environ.get('OTACON_COMFY_OUTPUT') or '').strip()
    if env:
        roots.append(Path(env).expanduser())
    # Common local layouts (WSL / native).
    for cand in (
        Path.home() / 'ComfyUI' / 'output',
        Path('/root/ComfyUI/output'),
        Path('/opt/ComfyUI/output'),
        Path.home() / 'comfyui' / 'output',
    ):
        if cand not in roots:
            roots.append(cand)
    return roots


def resolve_output_file(filename: str) -> Optional[Path]:
    name = Path(str(filename or '')).name
    if not name or name in ('.', '..'):
        return None
    for root in comfy_output_roots():
        try:
            p = (root / name).resolve()
            if not str(p).startswith(str(root.resolve())):
                continue
            if p.is_file():
                return p
        except OSError:
            continue
    return None


def fetch_comfy_output_bytes(
    *,
    filename: str,
    endpoint: Optional[str] = None,
    timeout: float = 20.0,
) -> tuple[Optional[bytes], str, str]:
    """Load a Comfy output for proxying through Otacon (:5757).

    Prefer on-disk ComfyUI/output (no CORS/403). Fall back to server-side GET
    of Comfy /view (localhost → Comfy, never the browser).
    """
    name = Path(str(filename or '')).name
    if not name:
        return None, '', ''
    mime = 'application/octet-stream'
    low = name.lower()
    if low.endswith(('.png',)):
        mime = 'image/png'
    elif low.endswith(('.jpg', '.jpeg')):
        mime = 'image/jpeg'
    elif low.endswith(('.webp',)):
        mime = 'image/webp'
    elif low.endswith(('.gif',)):
        mime = 'image/gif'
    elif low.endswith(('.mp4', '.webm')):
        mime = 'video/mp4' if low.endswith('.mp4') else 'video/webm'
    elif low.endswith(('.mp3', '.wav', '.flac', '.ogg')):
        mime = 'audio/mpeg' if low.endswith('.mp3') else 'audio/wav'

    disk = resolve_output_file(name)
    if disk is not None:
        try:
            return disk.read_bytes(), mime, name
        except OSError:
            pass

    ep = (endpoint or _studio_endpoint()).rstrip('/')
    from urllib.parse import quote
    url = f'{ep}/view?filename={quote(name)}&type=output'
    req = urllib.request.Request(url, headers={'Accept': '*/*'}, method='GET')
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
            ct = (resp.headers.get('Content-Type') or mime).split(';')[0].strip() or mime
            if data[:1] in (b'{', b'[') and 'json' in ct:
                return None, ct, name
            return data, ct, name
    except (urllib.error.URLError, TimeoutError, OSError, urllib.error.HTTPError):
        return None, mime, name


def public_creative_job(job) -> dict[str, Any]:
    """Job dict for Creative / Workshop UI — includes openable output URLs."""
    from dataclasses import asdict
    d = asdict(job) if hasattr(job, '__dataclass_fields__') else dict(job)
    files = outputs_from_job(job)
    ep = endpoint_from_job(job)
    jid = getattr(job, 'job_id', None) or d.get('job_id') or d.get('id')
    # Same-origin proxies — never point the browser at Comfy :8188 /view (403).
    proxy = f'/api/expansion/creative/jobs/{jid}/output' if jid else ''
    workshop_proxy = f'/video-studio/api/jobs/{jid}/output' if jid else ''
    d['outputs'] = files
    d['output_urls'] = [proxy] if proxy and files else []
    d['preview_url'] = proxy if files else ''
    d['output_proxy'] = proxy if files else ''
    d['workshop_output'] = workshop_proxy if files else ''
    d['prompt_id'] = prompt_id_from_job(job)
    d['comfy_endpoint'] = ep
    return d


def fail_stale_fake_creative_jobs(
    *,
    layout: Optional[StateLayout] = None,
    reason: str = (
        'Creative job never received a ComfyUI prompt_id '
        '(was accepted by UI but never submitted to ComfyUI).'
    ),
) -> dict[str, Any]:
    """Mark QUEUED/ASSIGNED/RUNNING creative jobs without prompt_id as FAILED."""
    store = JobStore(layout=layout)
    marked: list[str] = []
    for job in store.list(limit=500):
        if job.domain not in ('creative', 'media'):
            continue
        if job.status not in (
            JobStatus.QUEUED.value,
            JobStatus.ASSIGNED.value,
            JobStatus.RUNNING.value,
            JobStatus.WAITING.value,
        ):
            continue
        if prompt_id_from_job(job):
            continue
        store.transition(
            job.job_id,
            JobStatus.FAILED.value,
            error=reason,
            evidence=list(job.evidence or []) + ['comfy:never_submitted'],
        )
        marked.append(job.job_id)
    return {'ok': True, 'marked_failed': len(marked), 'job_ids': marked}


def migrate_stuck_creative_jobs(*, layout: Optional[StateLayout] = None) -> dict[str, Any]:
    """Installer / soft-update hook: fail historic fake RUNNING creative jobs."""
    out = fail_stale_fake_creative_jobs(
        layout=layout,
        reason=(
            'Migrated stuck creative job: never received a ComfyUI prompt_id '
            '(pre-submitter / fake RUNNING).'
        ),
    )
    # Also advance any real prompt_ids that already finished in Comfy.
    try:
        poll = poll_creative_jobs_once(layout=layout)
    except Exception as exc:  # noqa: BLE001
        poll = {'ok': False, 'error': str(exc)}
    return {**out, 'poll': poll}


def _history_outputs(endpoint: str, prompt_id: str) -> list[str]:
    code, data = _http_json('GET', f'{endpoint}/history/{prompt_id}', timeout=8.0)
    if code != 200 or not isinstance(data, dict):
        return []
    entry = data.get(prompt_id) if prompt_id in data else data
    if not isinstance(entry, dict):
        return []
    outputs = entry.get('outputs') or {}
    files: list[str] = []
    if isinstance(outputs, dict):
        for node_out in outputs.values():
            if not isinstance(node_out, dict):
                continue
            for img in node_out.get('images') or []:
                if isinstance(img, dict) and img.get('filename'):
                    files.append(str(img.get('filename')))
    return files


def poll_creative_jobs_once(*, layout: Optional[StateLayout] = None) -> dict[str, Any]:
    """Advance RUNNING creative jobs that have Comfy prompt_ids."""
    store = JobStore(layout=layout)
    ep = _studio_endpoint()
    completed = 0
    failed = 0
    for job in store.list(limit=200):
        if job.domain not in ('creative', 'media'):
            continue
        if job.status != JobStatus.RUNNING.value:
            continue
        pid = prompt_id_from_job(job)
        if not pid:
            continue
        files = _history_outputs(ep, pid)
        if files:
            store.transition(
                job.job_id,
                JobStatus.COMPLETE.value,
                result=f'ComfyUI outputs: {", ".join(files[:6])}',
                evidence=list(job.evidence or []) + [f'comfy:output={f}' for f in files[:8]],
                confidence=0.9,
            )
            completed += 1
            try:
                from expansion.capabilities.workshop_api import sync_expansion_job_to_workshop
                sync_expansion_job_to_workshop(store.get(job.job_id))
            except Exception:
                pass
            continue
        # Still queued/running in Comfy — leave RUNNING.
        code, q = _http_json('GET', f'{ep}/queue', timeout=5.0)
        if code != 200:
            continue
        running_ids = []
        pending_ids = []
        if isinstance(q, dict):
            for row in q.get('queue_running') or []:
                if isinstance(row, (list, tuple)) and len(row) > 1:
                    running_ids.append(str(row[1]))
            for row in q.get('queue_pending') or []:
                if isinstance(row, (list, tuple)) and len(row) > 1:
                    pending_ids.append(str(row[1]))
        if pid not in running_ids and pid not in pending_ids and not files:
            # Not in queue and no history yet — brief grace; if aged, fail.
            age = time.time() - (job.started_at or job.created_at or time.time())
            if age > 120:
                store.transition(
                    job.job_id,
                    JobStatus.FAILED.value,
                    error=f'ComfyUI prompt {pid} left queue without outputs',
                    evidence=list(job.evidence or []),
                )
                failed += 1
    return {'ok': True, 'completed': completed, 'failed': failed}


def ensure_creative_poller() -> None:
    global _POLL_STARTED
    with _POLL_LOCK:
        if _POLL_STARTED:
            return
        _POLL_STARTED = True

        def _loop() -> None:
            while True:
                try:
                    fail_stale_fake_creative_jobs()
                    poll_creative_jobs_once()
                except Exception:
                    pass
                time.sleep(4.0)

        threading.Thread(target=_loop, daemon=True, name='muse-comfy-poll').start()
