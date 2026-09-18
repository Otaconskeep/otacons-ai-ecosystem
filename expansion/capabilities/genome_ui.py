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
import signal
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


def _genome_api_live(port: int) -> bool:
    """True when :port serves Expansion Genome /api/train-status (not classic status page)."""
    try:
        import urllib.request
        with urllib.request.urlopen(
            f'http://127.0.0.1:{port}/api/train-status', timeout=1.5,
        ) as resp:
            return int(resp.status) == 200
    except Exception:
        return False


def _reclaim_classic_vt_port(port: int) -> dict[str, Any]:
    """Stop Otacon-owned classic python -m http.server on VT ui/ so Genome can bind.

    Safe: only kills PID file / http.server whose cwd is the Voice Trainer ui/.
    Never kills unrelated listeners.
    """
    from expansion.capabilities.voice_trainer_status import (
        _is_owned_server,
        _pid_alive,
        _read_pid,
        resolve_install_dir,
    )
    ui_dir = resolve_install_dir() / 'ui'
    stopped: list[int] = []
    owned = _read_pid(ui_dir)
    if owned and _pid_alive(owned) and _is_owned_server(owned, ui_dir):
        try:
            os.kill(owned, signal.SIGTERM)
            stopped.append(owned)
        except OSError:
            pass
    # Sweep lingering http.server with VT ui cwd (pid file missing / stale).
    try:
        for proc in Path('/proc').iterdir():
            if not proc.name.isdigit():
                continue
            pid = int(proc.name)
            try:
                cmd = (proc / 'cmdline').read_bytes().replace(b'\x00', b' ').decode('utf-8', 'replace')
            except OSError:
                continue
            if 'http.server' not in cmd and 'start_ui' not in cmd:
                continue
            try:
                cwd = os.readlink(f'/proc/{pid}/cwd')
            except OSError:
                continue
            if Path(cwd).resolve() != ui_dir.resolve():
                continue
            if pid in stopped:
                continue
            try:
                os.kill(pid, signal.SIGTERM)
                stopped.append(pid)
            except OSError:
                pass
    except OSError:
        pass
    if stopped:
        time.sleep(0.45)
    return {'stopped': stopped, 'ui_dir': str(ui_dir)}


def ensure_genome_ui(port: int = DEFAULT_PORT) -> dict[str, Any]:
    """Start the actionable Genome UI if not already listening.

    Replaces the classic green "Voice Trainer ready" status http.server when it
    owns :8765 — that page is not Genome (no train form /api).
    """
    global _SERVER, _SERVER_THREAD
    from expansion.capabilities.voice_trainer_status import write_status_json
    try:
        write_status_json(_vt_home())
    except OSError:
        pass

    if port_listening(port):
        if _genome_api_live(port):
            return {
                'ok': True,
                'action': 'already_listening',
                'url': f'http://127.0.0.1:{port}/',
                'product': 'genome-trainer',
            }
        # Classic VT status UI (or stale listener) — reclaim if Otacon-owned.
        reclaim = _reclaim_classic_vt_port(port)
        if port_listening(port):
            # Still busy after reclaim → foreign process; do not kill.
            return {
                'ok': False,
                'action': 'port_busy_foreign',
                'error': f'Port {port} is in use by a non-Otacon process (not Genome trainer).',
                'hint': f'Free :{port}, then Start Genome again.',
                'reclaim': reclaim,
            }
        # Port free — fall through to bind.
        if reclaim.get('stopped'):
            action_prefix = 'reclaimed_classic'
        else:
            action_prefix = 'port_freed'
    else:
        action_prefix = 'started'
        reclaim = {'stopped': []}

    try:
        server = ThreadingHTTPServer(('127.0.0.1', port), _GenomeHandler)
    except OSError as exc:
        return {'ok': False, 'action': 'bind_failed', 'error': str(exc), 'reclaim': reclaim}

    _SERVER = server

    def _serve() -> None:
        try:
            server.serve_forever(poll_interval=0.5)
        except Exception:
            pass

    _SERVER_THREAD = threading.Thread(target=_serve, daemon=True, name='genome-ui')
    _SERVER_THREAD.start()
    time.sleep(0.35)
    live = port_listening(port) and _genome_api_live(port)
    return {
        'ok': live,
        'action': action_prefix if live else 'start_pending',
        'url': f'http://127.0.0.1:{port}/' if live else '',
        'product': 'genome-trainer',
        'reclaim': reclaim,
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
  :root{
    --bg0:#03070a;--bg1:#08121a;--ink:#e8eef2;--muted:#7a8f9a;
    --cyan:#2ee6d6;--line:rgba(46,230,214,.28);--warn:#f5a524;--bad:#ff4d9a;
    --panel:rgba(8,18,26,.94);
  }
  *{box-sizing:border-box}
  body{
    margin:0;min-height:100vh;font-family:ui-monospace,"IBM Plex Mono",Consolas,monospace;color:var(--ink);
    background:
      radial-gradient(ellipse at 20% 0%,rgba(46,230,214,.12),transparent 45%),
      radial-gradient(ellipse at 80% 100%,rgba(151,159,236,.08),transparent 40%),
      linear-gradient(180deg,var(--bg1),var(--bg0));
  }
  .wrap{max-width:980px;margin:0 auto;padding:28px 18px 72px}
  .mast{display:flex;justify-content:space-between;gap:1rem;flex-wrap:wrap;align-items:flex-start;margin-bottom:1rem}
  .eyebrow{margin:0;letter-spacing:.22em;font-size:10px;color:var(--cyan);text-transform:uppercase}
  h1{margin:6px 0 4px;font-size:clamp(1.5rem,3.5vw,2.1rem);letter-spacing:.06em}
  .sub{margin:0;color:var(--muted);line-height:1.5;max-width:42rem;font-size:.9rem}
  .widgets{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:.65rem;margin:1rem 0}
  @media(max-width:800px){.widgets{grid-template-columns:1fr 1fr}}
  .widget{
    position:relative;padding:.75rem .8rem;background:var(--panel);border:1px solid var(--line);
    clip-path:polygon(8px 0,calc(100% - 8px) 0,100% 8px,100% calc(100% - 8px),calc(100% - 8px) 100%,8px 100%,0 calc(100% - 8px),0 8px);
    cursor:pointer;transition:border-color .15s,box-shadow .15s;text-align:left;width:100%;font:inherit;color:inherit;
  }
  .widget:hover{border-color:rgba(46,230,214,.55);box-shadow:0 0 24px rgba(46,230,214,.12)}
  .widget .k{font-size:9px;letter-spacing:.16em;text-transform:uppercase;color:var(--muted)}
  .widget .v{margin-top:6px;font-size:1rem;color:var(--cyan);word-break:break-word}
  .widget .v.bad{color:var(--bad)}.widget .v.warn{color:var(--warn)}.widget .v.ok{color:var(--cyan)}
  .grid{display:grid;grid-template-columns:1.2fr .8fr;gap:.75rem}
  @media(max-width:860px){.grid{grid-template-columns:1fr}}
  .panel{
    position:relative;padding:1rem;background:var(--panel);border:1px solid var(--line);
    clip-path:polygon(12px 0,calc(100% - 12px) 0,100% 12px,100% calc(100% - 12px),calc(100% - 12px) 100%,12px 100%,0 calc(100% - 12px),0 12px);
  }
  .panel h2{margin:0 0 .55rem;font-size:.72rem;letter-spacing:.16em;text-transform:uppercase;color:var(--cyan)}
  .panel p{margin:0 0 .75rem;color:var(--muted);font-size:.85rem;line-height:1.5}
  .btns{display:flex;flex-wrap:wrap;gap:.45rem}
  .btn{
    appearance:none;font:inherit;cursor:pointer;padding:.55rem .9rem;
    border:1px solid var(--line);background:rgba(46,230,214,.08);color:var(--ink);
    letter-spacing:.06em;text-transform:uppercase;font-size:.72rem;
  }
  .btn.primary{background:rgba(46,230,214,.22);border-color:rgba(46,230,214,.55);color:var(--cyan)}
  .btn:hover{background:rgba(46,230,214,.18)}
  .btn:disabled{opacity:.4;cursor:not-allowed}
  .btn.ghost{background:transparent}
  pre{
    margin:0;max-height:220px;overflow:auto;padding:.75rem;font-size:11px;line-height:1.45;
    background:#020508;border:1px solid rgba(46,230,214,.18);color:var(--ink);white-space:pre-wrap;
  }
  .guide{display:flex;gap:12px;align-items:flex-start;margin:0 0 1rem;padding:.85rem;
    border:1px solid rgba(46,230,214,.25);background:rgba(3,10,14,.85)}
  .guide .kick{margin:0 0 4px;font-size:10px;letter-spacing:.16em;text-transform:uppercase;color:var(--cyan)}
  .guide .copy{margin:0;font-size:.9rem;line-height:1.45;color:var(--ink)}
  .modal{position:fixed;inset:0;z-index:50;display:none;align-items:center;justify-content:center;
    background:rgba(2,6,10,.72);padding:18px}
  .modal.open{display:flex}
  .modal-card{
    width:min(520px,100%);max-height:min(90vh,720px);overflow:auto;padding:1.1rem 1.15rem;
    background:linear-gradient(165deg,rgba(10,22,30,.98),rgba(3,8,12,.99));
    border:1px solid rgba(46,230,214,.4);box-shadow:0 24px 64px rgba(0,0,0,.55);
    clip-path:polygon(14px 0,calc(100% - 14px) 0,100% 14px,100% calc(100% - 14px),calc(100% - 14px) 100%,14px 100%,0 calc(100% - 14px),0 14px);
  }
  .modal-card h3{margin:0 0 .35rem;letter-spacing:.08em;font-size:1.05rem}
  .modal-card .hint{margin:0 0 .85rem;color:var(--muted);font-size:.82rem;line-height:1.45}
  label{display:block;font-size:10px;letter-spacing:.12em;text-transform:uppercase;color:var(--muted);margin:10px 0 5px}
  input,textarea{
    width:100%;padding:10px 12px;border:1px solid var(--line);background:#020508;color:var(--ink);font:inherit;border-radius:0;
  }
  textarea{min-height:96px;resize:vertical}
  .modal-actions{display:flex;flex-wrap:wrap;gap:.45rem;margin-top:14px}
  .toast{margin-top:10px;font-size:.82rem;color:var(--muted);white-space:pre-wrap}
  .steps{margin:0;padding-left:1.1rem;color:var(--muted);font-size:.85rem;line-height:1.55}
  .steps li{margin:.25rem 0}
</style>
</head>
<body>
<div class="wrap">
  <header class="mast">
    <div>
      <p class="eyebrow">Otaconskeep · Genome · local GPU</p>
      <h1>Voice Trainer</h1>
      <p class="sub">Clone a voice from YouTube into Piper. Tap a widget for details. Training opens in a popup — no command lines.</p>
    </div>
    <div class="btns">
      <button type="button" class="btn primary" id="openTrain">Clone a voice</button>
      <button type="button" class="btn ghost" id="openLog">Job log</button>
    </div>
  </header>

  <div class="guide">
    <div>
      <p class="kick">Aria // guiding</p>
      <p class="copy">Three taps: make sure GPU is green, open Clone a voice, paste a YouTube link, press Start training. Leave the PC on — it can take a while.</p>
    </div>
  </div>

  <div class="widgets" id="widgets">
    <button type="button" class="widget" data-pop="status"><div class="k">Install</div><div class="v" id="st-ok">…</div></button>
    <button type="button" class="widget" data-pop="status"><div class="k">GPU</div><div class="v" id="st-gpu">—</div></button>
    <button type="button" class="widget" data-pop="status"><div class="k">Trainer image</div><div class="v" id="st-img">—</div></button>
    <button type="button" class="widget" data-pop="job"><div class="k">Job</div><div class="v" id="st-job">idle</div></button>
  </div>

  <div class="grid">
    <section class="panel">
      <h2>Quick start</h2>
      <p>Use the popup form for training. Status tiles update every few seconds. Open Job log anytime to watch progress.</p>
      <div class="btns">
        <button type="button" class="btn primary" id="openTrain2">Start training…</button>
        <button type="button" class="btn" id="refreshBtn">Refresh status</button>
      </div>
      <p class="toast" id="trainMsg"></p>
    </section>
    <section class="panel">
      <h2>How it works</h2>
      <ol class="steps">
        <li>GPU must show visible (nvidia-smi in WSL).</li>
        <li>Trainer image builds once, then reuses.</li>
        <li>Name the voice → paste YouTube URL(s) → Start training.</li>
        <li>When complete, the voice lands in Genome jobs for Piper.</li>
      </ol>
    </section>
  </div>
</div>

<div class="modal" id="modalTrain" role="dialog" aria-modal="true">
  <div class="modal-card">
    <h3>Clone a voice</h3>
    <p class="hint">Pick a short name (letters, numbers, _ or -). Paste one or more YouTube URLs. GPU only.</p>
    <label for="voice">Voice name</label>
    <input id="voice" placeholder="e.g. mei_ling" autocomplete="off">
    <label for="urls">YouTube URL(s) — one per line</label>
    <textarea id="urls" placeholder="https://www.youtube.com/watch?v=…"></textarea>
    <div class="modal-actions">
      <button type="button" class="btn primary" id="trainBtn">Start training</button>
      <button type="button" class="btn ghost" data-close="modalTrain">Cancel</button>
    </div>
    <p class="toast" id="modalTrainMsg"></p>
  </div>
</div>

<div class="modal" id="modalStatus" role="dialog" aria-modal="true">
  <div class="modal-card">
    <h3>System status</h3>
    <p class="hint">Live probe from this machine. If GPU is missing, fix WSL NVIDIA first.</p>
    <div id="statusDetail" class="toast">Loading…</div>
    <div class="modal-actions">
      <button type="button" class="btn ghost" data-close="modalStatus">Close</button>
    </div>
  </div>
</div>

<div class="modal" id="modalLog" role="dialog" aria-modal="true">
  <div class="modal-card" style="width:min(720px,100%)">
    <h3>Job log</h3>
    <p class="hint">Tail of the active training log. Updates while a job runs.</p>
    <pre id="logTail">No job yet.</pre>
    <div class="modal-actions">
      <button type="button" class="btn" id="refreshLog">Refresh</button>
      <button type="button" class="btn ghost" data-close="modalLog">Close</button>
    </div>
  </div>
</div>

<script>
function openModal(id){ const el=document.getElementById(id); if(el) el.classList.add('open'); }
function closeModal(id){ const el=document.getElementById(id); if(el) el.classList.remove('open'); }
document.querySelectorAll('[data-close]').forEach(b=>b.onclick=()=>closeModal(b.getAttribute('data-close')));
document.querySelectorAll('.modal').forEach(m=>m.addEventListener('click',e=>{ if(e.target===m) m.classList.remove('open'); }));
document.getElementById('openTrain').onclick=()=>openModal('modalTrain');
document.getElementById('openTrain2').onclick=()=>openModal('modalTrain');
document.getElementById('openLog').onclick=()=>{ openModal('modalLog'); refresh(); };
document.getElementById('refreshBtn').onclick=()=>refresh();
document.getElementById('refreshLog').onclick=()=>refresh();
document.querySelectorAll('.widget').forEach(w=>{
  w.onclick=()=>{
    const pop=w.getAttribute('data-pop');
    if(pop==='job') openModal('modalLog');
    else openModal('modalStatus');
  };
});

async function refresh(){
  try{
    const d=await (await fetch('/status.json',{cache:'no-store'})).json();
    const ok=!!d.ok;
    const el=document.getElementById('st-ok');
    el.textContent=ok?'READY':'NOT READY';
    el.className='v '+(ok?'ok':'bad');
    const gpu=document.getElementById('st-gpu');
    gpu.textContent=d.gpu?(d.gpu_name||'visible'):'missing';
    gpu.className='v '+(d.gpu?'ok':'bad');
    document.getElementById('st-img').textContent=d.image||'missing';
    document.getElementById('st-img').className='v '+(d.image?'ok':'warn');
    const t=d.train||{};
    const job=document.getElementById('st-job');
    job.textContent=(t.status||'idle')+(t.name?(' · '+t.name):'');
    job.className='v '+(t.status==='failed'?'bad':(t.status==='completed'?'ok':(t.status==='running'||t.status==='starting'?'warn':'')));
    document.getElementById('statusDetail').textContent=
      'Install: '+(ok?'READY':'NOT READY')+'\n'+
      'GPU: '+(d.gpu?(d.gpu_name||'visible'):'missing')+(d.gpu_vram_mb?(' · '+d.gpu_vram_mb+' MiB'):'')+'\n'+
      'Image: '+(d.image||'—')+'\n'+
      'Dir: '+(d.install_dir||'—')+'\n'+
      'Job: '+(t.status||'idle')+(t.name?(' · '+t.name):'')+(t.error?('\nError: '+t.error):'');
    if(t.error) document.getElementById('trainMsg').textContent=t.error;
  }catch(e){
    document.getElementById('st-ok').textContent='status failed';
    document.getElementById('st-ok').className='v bad';
  }
  try{
    const s=await (await fetch('/api/train-status',{cache:'no-store'})).json();
    if(s.log_tail) document.getElementById('logTail').textContent=s.log_tail;
    const btn=document.getElementById('trainBtn');
    if(btn && (s.status==='completed'||s.status==='failed'||s.status==='idle')) btn.disabled=false;
  }catch(_e){}
}
document.getElementById('trainBtn').onclick=async()=>{
  const btn=document.getElementById('trainBtn');
  const msg=document.getElementById('modalTrainMsg');
  const name=(document.getElementById('voice').value||'').trim();
  const urls=(document.getElementById('urls').value||'').split(/\n/).map(s=>s.trim()).filter(Boolean);
  btn.disabled=true; msg.textContent='Starting GPU job…';
  try{
    const r=await fetch('/api/train',{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({name,urls})
    });
    const d=await r.json();
    msg.textContent=d.hint||d.error||d.action||JSON.stringify(d);
    document.getElementById('trainMsg').textContent=msg.textContent;
    if(!d.ok) btn.disabled=false;
    else openModal('modalLog');
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
