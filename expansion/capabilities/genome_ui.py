"""Local Genome Voice Trainer UI + train API on :8765.

Replaces the static http.server status page with an actionable trainer:
  GET  /           — train form (name + YouTube URLs)
  GET  /status.json — install/GPU/image status
  GET  /api/train-status — active job status
  POST /api/train  — launch piper-voice-trainer:gpu pipeline
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Optional
from urllib.parse import parse_qs

DEFAULT_PORT = 8765
_TRAIN_IMAGE = 'piper-voice-trainer:gpu'
_JOB_NAME_RE = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9_-]{1,47}$')

_SERVER: ThreadingHTTPServer | None = None
_SERVER_THREAD: threading.Thread | None = None
_TRAIN_LOCK = threading.Lock()
_TRAIN_STATE: dict[str, Any] = {
    'status': 'idle',  # idle|starting|running|completed|failed
    'name': '',
    'urls': [],
    'pid': None,
    'started_at': 0.0,
    'finished_at': 0.0,
    'error': '',
    'log': '',
}


def _vt_home() -> Path:
    override = (os.environ.get('OTACON_VT_DIR') or '').strip()
    if override:
        return Path(override).expanduser()
    return Path.home() / 'otacon-voice-trainer'


def _jobs_root() -> Path:
    root = _vt_home() / 'jobs'
    root.mkdir(parents=True, exist_ok=True)
    return root


def _train_log_path() -> Path:
    return Path('/tmp/otacon-genome-train.log')


def train_state() -> dict[str, Any]:
    with _TRAIN_LOCK:
        return dict(_TRAIN_STATE)


def _set_train(**kwargs: Any) -> None:
    with _TRAIN_LOCK:
        _TRAIN_STATE.update(kwargs)


def _docker_bin() -> str | None:
    try:
        from core.platform import _resolve_docker
        return _resolve_docker()
    except Exception:
        return None


def _docker_env() -> dict[str, str] | None:
    try:
        from core.platform import docker_env
        return docker_env()
    except Exception:
        return None


def _gpu_ok() -> bool:
    try:
        from core.platform import _nvidia_smi_env, _resolve_nvidia_smi
        smi = _resolve_nvidia_smi()
        if not smi:
            return False
        r = subprocess.run(
            [smi], capture_output=True, timeout=8, check=False, env=_nvidia_smi_env(),
        )
        return r.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _image_ok() -> bool:
    docker = _docker_bin()
    if not docker:
        return False
    try:
        r = subprocess.run(
            [docker, 'image', 'inspect', _TRAIN_IMAGE],
            capture_output=True, timeout=8, check=False, env=_docker_env(),
        )
        return r.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def status_payload() -> dict[str, Any]:
    from expansion.capabilities.voice_trainer_status import build_status, write_status_json
    home = _vt_home()
    try:
        write_status_json(home)
    except OSError:
        pass
    base = build_status(home)
    base['listening'] = True
    base['train'] = train_state()
    # Keep legacy keys used by older UI snippets
    if 'gpu' not in base:
        base['gpu'] = base.get('gpu_state') == 'gpu_detected'
    return base


def ensure_genome_ui(port: int = DEFAULT_PORT) -> dict[str, Any]:
    """Start the actionable Genome UI if not already listening."""
    global _SERVER, _SERVER_THREAD
    from expansion.capabilities.voice_trainer_status import write_status_json
    try:
        write_status_json(_vt_home())
    except OSError:
        pass

    if port_listening(port):
        # Confirm it is our trainer (not the old static http.server page).
        try:
            import urllib.request
            with urllib.request.urlopen(
                f'http://127.0.0.1:{port}/api/train-status', timeout=1.5,
            ) as resp:
                if resp.status == 200:
                    return {
                        'ok': True,
                        'action': 'already_listening',
                        'url': f'http://127.0.0.1:{port}/',
                    }
        except Exception:
            # Might be classic status UI — caller may repair status.json without killing.
            return {
                'ok': False,
                'action': 'port_busy_foreign',
                'error': f'Port {port} is in use by another process (not Expansion Genome trainer).',
                'hint': (
                    f'If it is the classic Voice Trainer status UI, status.json will be repaired '
                    f'without killing it. Otherwise free :{port} and Start Genome again.'
                ),
            }

    try:
        server = ThreadingHTTPServer(('127.0.0.1', port), _GenomeHandler)
    except OSError as exc:
        return {'ok': False, 'action': 'bind_failed', 'error': str(exc)}

    _SERVER = server

    def _serve() -> None:
        try:
            server.serve_forever(poll_interval=0.5)
        except Exception:
            pass

    _SERVER_THREAD = threading.Thread(target=_serve, daemon=True, name='genome-ui')
    _SERVER_THREAD.start()
    time.sleep(0.35)
    live = port_listening(port)
    return {
        'ok': live,
        'action': 'started' if live else 'start_pending',
        'url': f'http://127.0.0.1:{port}/' if live else '',
        'product': 'genome-trainer',
    }


def start_train_job(*, name: str, urls: list[str]) -> dict[str, Any]:
    """Launch GPU pipeline in docker. One job at a time."""
    name = (name or '').strip()
    urls = [u.strip() for u in (urls or []) if u and u.strip()]
    if not _JOB_NAME_RE.match(name):
        return {
            'ok': False,
            'error': 'Voice name must be 2–48 chars: letters, numbers, _ or -',
        }
    if not urls:
        return {'ok': False, 'error': 'At least one YouTube URL is required'}
    if not _gpu_ok():
        return {
            'ok': False,
            'error': 'NVIDIA GPU not visible (nvidia-smi). Run Fix-Otacon-GPU.bat in WSL.',
        }
    if not _image_ok():
        return {
            'ok': False,
            'error': f'{_TRAIN_IMAGE} image missing — Install Genome first.',
        }
    docker = _docker_bin()
    if not docker:
        return {'ok': False, 'error': 'Docker not available'}

    with _TRAIN_LOCK:
        if _TRAIN_STATE.get('status') in ('starting', 'running'):
            return {
                'ok': False,
                'error': f"Training already in progress for '{_TRAIN_STATE.get('name')}'",
                'train': dict(_TRAIN_STATE),
            }

    job_host = _jobs_root() / name
    job_host.mkdir(parents=True, exist_ok=True)
    log = _train_log_path()
    try:
        log.write_text('', encoding='utf-8')
    except OSError:
        pass

    cmd = [
        docker, 'run', '--rm', '--gpus', 'all',
        '--name', f'otacon-genome-{name}',
        '-v', f'{job_host}:/workspace/jobs/{name}',
        '-v', f'{_vt_home() / "voices"}:/workspace/voices',
        _TRAIN_IMAGE,
        '--name', name,
        '--urls', *urls,
    ]
    (_vt_home() / 'voices').mkdir(parents=True, exist_ok=True)

    _set_train(
        status='starting',
        name=name,
        urls=urls,
        pid=None,
        started_at=time.time(),
        finished_at=0.0,
        error='',
        log=str(log),
    )

    try:
        logf = open(log, 'ab')
        proc = subprocess.Popen(
            cmd,
            stdout=logf,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            env=_docker_env(),
        )
    except OSError as exc:
        _set_train(status='failed', error=str(exc), finished_at=time.time())
        return {'ok': False, 'error': str(exc), 'train': train_state()}

    _set_train(status='running', pid=proc.pid)

    def _watch() -> None:
        rc = proc.wait()
        if rc == 0:
            _set_train(status='completed', finished_at=time.time(), error='')
        else:
            _set_train(
                status='failed',
                finished_at=time.time(),
                error=f'docker/pipeline exit {rc} — see {log}',
            )

    threading.Thread(target=_watch, daemon=True, name='genome-train').start()
    return {
        'ok': True,
        'action': 'started',
        'name': name,
        'pid': proc.pid,
        'log': str(log),
        'train': train_state(),
        'hint': 'Training runs in Docker (GPU). This can take a long time — leave the PC on.',
    }


_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Otacon Genome · Voice Trainer</title>
<style>
  :root {
    --bg0:#07140c; --bg1:#0c1f14; --ink:#d7f5df; --muted:#8fb89a;
    --accent:#3dff9a; --line:rgba(61,255,154,.22); --warn:#ffb86b; --bad:#ff6b6b;
  }
  *{box-sizing:border-box}
  body{
    margin:0;min-height:100vh;font-family:"IBM Plex Mono",ui-monospace,monospace;color:var(--ink);
    background:radial-gradient(ellipse at 50% 0%,#123221 0%,var(--bg0) 55%),linear-gradient(180deg,var(--bg1),var(--bg0));
  }
  .wrap{max-width:720px;margin:0 auto;padding:36px 20px 64px}
  .eyebrow{letter-spacing:.22em;font-size:11px;color:var(--muted);text-transform:uppercase}
  h1{font-size:clamp(1.6rem,4vw,2.3rem);margin:10px 0 8px;letter-spacing:.04em}
  p{color:var(--muted);line-height:1.55}
  .card{margin-top:18px;padding:16px;border:1px solid var(--line);border-radius:14px;background:rgba(0,0,0,.28)}
  label{display:block;font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:var(--muted);margin:12px 0 6px}
  input,textarea{
    width:100%;padding:10px 12px;border-radius:10px;border:1px solid var(--line);
    background:#050b08;color:var(--ink);font:inherit
  }
  textarea{min-height:88px;resize:vertical}
  .btn{
    display:inline-block;margin-top:16px;margin-right:8px;padding:10px 14px;border-radius:999px;
    border:1px solid var(--line);color:var(--ink);background:rgba(61,255,154,.1);cursor:pointer;font:inherit
  }
  .btn:hover{background:rgba(61,255,154,.18)}
  .btn:disabled{opacity:.45;cursor:not-allowed}
  .row{display:flex;justify-content:space-between;gap:12px;padding:8px 0;border-bottom:1px solid rgba(255,255,255,.06)}
  .row:last-child{border-bottom:0}
  .k{color:var(--muted)}.v{color:var(--accent);text-align:right;word-break:break-all}
  .ok{color:var(--accent)}.bad{color:var(--bad)}.warn{color:var(--warn)}
  pre{margin-top:12px;padding:12px;overflow:auto;border-radius:10px;border:1px solid var(--line);background:#050b08;font-size:12px;white-space:pre-wrap}
</style>
</head>
<body>
<div class="wrap">
  <p class="eyebrow">Otaconskeep · Genome · local GPU</p>
  <h1>Voice Trainer</h1>
  <p>Clone a voice from YouTube into a Piper ONNX model. Training is <strong class="ok">GPU-only</strong>.</p>

  <div class="card" id="status-card">
    <div class="row"><span class="k">Install</span><span class="v" id="st-ok">…</span></div>
    <div class="row"><span class="k">GPU</span><span class="v" id="st-gpu">—</span></div>
    <div class="row"><span class="k">Image</span><span class="v" id="st-img">—</span></div>
    <div class="row"><span class="k">Job</span><span class="v" id="st-job">idle</span></div>
  </div>

  <div class="card">
    <p class="eyebrow">Start a clone</p>
    <label for="voice">Voice name</label>
    <input id="voice" placeholder="e.g. mei_ling" autocomplete="off">
    <label for="urls">YouTube URL(s) — one per line</label>
    <textarea id="urls" placeholder="https://www.youtube.com/watch?v=…"></textarea>
    <button class="btn" id="trainBtn" type="button">Start training</button>
    <p id="trainMsg" class="muted" style="margin-top:12px"></p>
  </div>

  <div class="card">
    <p class="eyebrow">Job log (tail)</p>
    <pre id="logTail">No job yet.</pre>
  </div>
</div>
<script>
async function refresh(){
  try{
    const d=await (await fetch('/status.json',{cache:'no-store'})).json();
    const ok=!!d.ok;
    const el=document.getElementById('st-ok');
    el.textContent=ok?'READY':'NOT READY';
    el.className='v '+(ok?'ok':'bad');
    document.getElementById('st-gpu').textContent=d.gpu?'visible':'missing';
    document.getElementById('st-gpu').className='v '+(d.gpu?'ok':'bad');
    document.getElementById('st-img').textContent=d.image||'missing';
    const t=d.train||{};
    const job=document.getElementById('st-job');
    job.textContent=(t.status||'idle')+(t.name?(' · '+t.name):'');
    job.className='v '+(t.status==='failed'?'bad':(t.status==='completed'?'ok':'warn'));
    if(t.error) document.getElementById('trainMsg').textContent=t.error;
  }catch(e){
    document.getElementById('st-ok').textContent='status failed';
    document.getElementById('st-ok').className='v bad';
  }
  try{
    const s=await (await fetch('/api/train-status',{cache:'no-store'})).json();
    if(s.log_tail) document.getElementById('logTail').textContent=s.log_tail;
  }catch(_e){}
}
document.getElementById('trainBtn').onclick=async()=>{
  const btn=document.getElementById('trainBtn');
  const msg=document.getElementById('trainMsg');
  const name=(document.getElementById('voice').value||'').trim();
  const urls=(document.getElementById('urls').value||'').split(/\n/).map(s=>s.trim()).filter(Boolean);
  btn.disabled=true; msg.textContent='Starting…';
  try{
    const r=await fetch('/api/train',{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({name,urls})
    });
    const d=await r.json();
    msg.textContent=d.hint||d.error||d.action||JSON.stringify(d);
    if(!d.ok) btn.disabled=false;
  }catch(e){
    msg.textContent=String(e);
    btn.disabled=false;
  }
  refresh();
};
refresh();
setInterval(refresh,4000);
</script>
</body>
</html>
"""


class _GenomeHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: Any) -> None:  # noqa: A003
        return

    def _send(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, payload: dict) -> None:
        raw = json.dumps(payload).encode('utf-8')
        self._send(code, raw, 'application/json; charset=utf-8')

    def do_GET(self) -> None:  # noqa: N802
        path = (self.path or '/').split('?', 1)[0]
        if path in ('/', '/index.html'):
            self._send(200, _HTML.encode('utf-8'), 'text/html; charset=utf-8')
            return
        if path == '/status.json':
            self._json(200, status_payload())
            return
        if path == '/api/train-status':
            st = train_state()
            tail = ''
            log = st.get('log') or ''
            if log and Path(log).is_file():
                try:
                    raw = Path(log).read_bytes()
                    tail = raw[-8000:].decode('utf-8', errors='replace')
                except OSError:
                    tail = ''
            self._json(200, {**st, 'log_tail': tail})
            return
        self._json(404, {'ok': False, 'error': 'not found'})

    def do_POST(self) -> None:  # noqa: N802
        path = (self.path or '/').split('?', 1)[0]
        if path != '/api/train':
            self._json(404, {'ok': False, 'error': 'not found'})
            return
        length = int(self.headers.get('Content-Length') or 0)
        raw = self.rfile.read(length) if length else b'{}'
        name = ''
        urls: list[str] = []
        ctype = (self.headers.get('Content-Type') or '').lower()
        try:
            if 'application/json' in ctype:
                data = json.loads(raw.decode('utf-8') or '{}')
                name = str(data.get('name') or '')
                u = data.get('urls') or []
                if isinstance(u, str):
                    urls = [x.strip() for x in u.splitlines() if x.strip()]
                else:
                    urls = [str(x).strip() for x in u if str(x).strip()]
            else:
                qs = parse_qs(raw.decode('utf-8'))
                name = (qs.get('name') or [''])[0]
                urls = [x for x in (qs.get('urls') or [''])[0].splitlines() if x.strip()]
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            self._json(400, {'ok': False, 'error': str(exc)})
            return
        result = start_train_job(name=name, urls=urls)
        self._json(200 if result.get('ok') else 400, result)


def port_listening(port: int = DEFAULT_PORT, host: str = '127.0.0.1') -> bool:
    import socket
    try:
        with socket.create_connection((host, port), timeout=0.4):
            return True
    except OSError:
        return False
