from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import sqlite3
import time
from pathlib import Path

from core.platform import detect
from core.planner import recommend_hardware_plan
from core.config import build_config, save, load
from core.storage import volumes, recommended_volume
from core.deployment import local_deployment
from core.agent_service import chat, chat_with_optional_speech
from core.providers import TestProvider, OllamaProvider
from core.models import recommend as recommend_model
from core.voice import (
    synthesize_voice,
    public_result,
    TTSError,
    catalog_entries,
    profile_for,
    voice_status,
    CATALOG_AVAILABLE,
)
from core.memory import MemoryStore
from core.stt import TestSTTProvider, FasterWhisperProvider, normalize_wav
from core.preferences import load_preferences, save_preferences
from core.actions import action_plan, run_voice_actions
from core.arbiter import default_resources
from core.arbiter import ResourceArbiter, ComputeResource
from core.image import ImageProductionManager, ImageGenerationRequest, TestImageProvider, StableDiffusionProvider
from core.video import VideoProductionManager, VideoGenerationRequest, TestVideoProvider, ComfyUIProvider
from core.nodes import NodeRegistry
from installer.security import (
    CONFIG_ROOT,
    check_lan_auth,
    ensure_lan_token,
    is_loopback_client,
    load_lan_token,
    path_is_protected,
    resolve_bind_host,
    safe_config_root,
    safe_ui_path,
)

MEMORY = MemoryStore(CONFIG_ROOT / 'runtime' / 'memory.sqlite')
NODES = NodeRegistry()
BIND_HOST, BIND_MODE = resolve_bind_host()
LAN_TOKEN = ensure_lan_token() if BIND_MODE == 'lan' else load_lan_token()
UI_ROOT = Path(__file__).parent.parent / 'ui'
STATIC_CONTENT_TYPES = {
    '.html': 'text/html', '.js': 'application/javascript', '.css': 'text/css',
    '.webp': 'image/webp', '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
    '.mp4': 'video/mp4', '.svg': 'image/svg+xml', '.json': 'application/json',
}

_PIPER_RESTART_ATTEMPTED = False


def _try_restart_piper_once() -> bool:
    """P1-5: one local systemd restart before telling the user to Repair Setup."""
    global _PIPER_RESTART_ATTEMPTED
    if _PIPER_RESTART_ATTEMPTED:
        return False
    _PIPER_RESTART_ATTEMPTED = True
    import subprocess
    import time
    try:
        subprocess.run(
            ['systemctl', 'restart', 'otacon-tts.service'],
            capture_output=True, text=True, timeout=20, check=False,
        )
        time.sleep(2)
        return True
    except Exception:
        try:
            subprocess.run(
                ['systemctl', '--user', 'restart', 'otacon-tts.service'],
                capture_output=True, text=True, timeout=20, check=False,
            )
            time.sleep(2)
            return True
        except Exception:
            return False


def _tts_unreachable_message() -> str:
    return (
        'The voice engine is not running. Open OtaconsKeep Setup and choose Repair '
        '(or run with --repair) so Piper TTS and the wake task are restored.'
    )


def _llm_settings() -> tuple[str, str, str]:
    """Return (provider, endpoint, ollama_model_tag).

    Precedence (important for WSL/systemd installs):
      1. OTACON_LLM_* env from the installer/systemd unit (the model that was
         actually pulled) — must beat a stale config.json CPU-fallback.
      2. Saved config.json llm_service (user/wizard choice) when env unset.
      3. bootstrap-hardware.env from install.
      4. Live hardware recommendation / last-resort small model.
    """
    env_provider = os.getenv('OTACON_LLM_PROVIDER', 'ollama').strip().lower() or 'ollama'
    env_endpoint = os.getenv('OTACON_LLM_ENDPOINT', 'http://127.0.0.1:11434').rstrip('/')
    env_model = os.getenv('OTACON_LLM_MODEL', '').strip()

    cfg_provider = cfg_endpoint = cfg_model = ''
    cfg_path = CONFIG_ROOT / 'config.json'
    if cfg_path.is_file():
        try:
            cfg = json.loads(cfg_path.read_text())
            svc = cfg.get('llm_service') or {}
            cfg_provider = (svc.get('provider') or '').strip().lower()
            cfg_endpoint = (svc.get('endpoint') or '').rstrip('/')
            cfg_model = (svc.get('model') or '').strip()
        except (OSError, json.JSONDecodeError):
            pass

    provider = env_provider or cfg_provider or 'ollama'
    endpoint = env_endpoint or cfg_endpoint or 'http://127.0.0.1:11434'
    # Env model wins when set — prevents wizard "Create Configuration" from
    # locking chat onto qwen2.5:1.5b after a false-negative GPU scan.
    model = env_model or cfg_model

    if not model:
        boot = CONFIG_ROOT / 'bootstrap-hardware.env'
        if boot.is_file():
            for line in boot.read_text().splitlines():
                if line.startswith('OTACON_BOOTSTRAP_RECOMMENDED_MODEL='):
                    model = line.split('=', 1)[1].strip()
                    break
    if not model:
        try:
            model = recommend_model(detect()).source_id
        except Exception:
            model = 'qwen2.5:1.5b'
    return provider, endpoint, model


def _chat_provider():
    """Prefer real Ollama; opt into TestProvider with OTACON_USE_TEST_LLM=1."""
    if os.getenv('OTACON_USE_TEST_LLM', '').strip() in ('1', 'true', 'yes'):
        return TestProvider()
    provider, endpoint, _model = _llm_settings()
    if provider == 'test' or endpoint.startswith('test://'):
        return TestProvider()
    return OllamaProvider(endpoint)


def _deployment():
    provider, endpoint, model = _llm_settings()
    if os.getenv('OTACON_USE_TEST_LLM', '').strip() in ('1', 'true', 'yes'):
        provider, endpoint, model = 'test', 'test://', model or 'chat_small'
    return local_deployment(
        llm_provider=provider,
        llm_endpoint=endpoint,
        llm_model=model,
        tts_endpoint=os.getenv('OTACON_TTS_ENDPOINT', 'wyoming://127.0.0.1:10200'),
        tts_provider=os.getenv('OTACON_TTS_PROVIDER', 'piper'),
    )


def _expansion_runtime():
    """Lazy Expansion runtime; None when Expansion agents are not installed."""
    try:
        from expansion.runtime import ExpansionRuntime
        rt = ExpansionRuntime(core_memory=MEMORY)
        if not rt.expansion_enabled():
            return None
        return rt
    except Exception:
        return None


def _load_agents() -> list[dict]:
    cfg_path = CONFIG_ROOT / 'config.json'
    if cfg_path.is_file():
        try:
            cfg = json.loads(cfg_path.read_text())
            agents = cfg.get('agents') or []
            if agents:
                return agents
        except (OSError, json.JSONDecodeError):
            pass
    return [
        {'id': 'agent_001', 'display_name': 'Aria', 'voice_id': 'voice_aria', 'avatar': '/assets/aria/aria.webp'},
        {'id': 'agent_002', 'display_name': 'Sarah', 'voice_id': 'voice_002'},
    ]


def _agent_from_request(data: dict) -> dict:
    agents = _load_agents()
    agent = dict(data.get('agent') or {})
    if not agent.get('id'):
        agent['id'] = data.get('agent_id') or 'agent_001'
    # Expansion roster takes precedence when that agent_id is provisioned.
    rt = _expansion_runtime()
    if rt is not None and rt.get_agent(agent['id']) is not None:
        try:
            return rt.agent_dict_for_core(agent['id'])
        except Exception:
            pass
    if not agent.get('display_name'):
        agent['display_name'] = data.get('display_name') or next(
            (a['display_name'] for a in agents if a['id'] == agent['id']), 'Aria'
        )
    if not agent.get('voice_id'):
        saved = next((a for a in agents if a['id'] == agent['id']), None)
        agent['voice_id'] = data.get('voice_id') or (saved or {}).get('voice_id') or 'voice_aria'
    return agent


# Lightweight chat-probe cache: expensive inference must not run on every
# /api/capabilities poll, but installer acceptance and first Codec paint need truth.
_CHAT_PROBE_CACHE: dict = {'at': 0.0, 'ok': False, 'detail': '', 'model': ''}


def _memory_usable() -> tuple[bool, str]:
    try:
        MEMORY.ping()
        # Prove create/list path (the exact crash site before inference).
        cid = MEMORY.create_conversation('__health__', '__health__', title='health')
        MEMORY.list_conversations('__health__', '__health__')
        MEMORY.delete_conversation(cid, '__health__', '__health__')
        return True, ''
    except Exception as exc:  # noqa: BLE001
        return False, f'{type(exc).__name__}: {exc}'


def _chat_inference_probe(endpoint: str, model: str, *, force: bool = False) -> tuple[bool, str, str]:
    """Return (ok, detail, resolved_model). Cached ~90s unless force=True."""
    now = time.time()
    ttl = float(os.getenv('OTACON_CHAT_PROBE_TTL', '90') or '90')
    if (
        not force
        and (now - float(_CHAT_PROBE_CACHE.get('at') or 0)) < ttl
        and _CHAT_PROBE_CACHE.get('model') == model
        and _CHAT_PROBE_CACHE.get('at')
    ):
        return (
            bool(_CHAT_PROBE_CACHE.get('ok')),
            str(_CHAT_PROBE_CACHE.get('detail') or ''),
            str(_CHAT_PROBE_CACHE.get('resolved') or model),
        )
    try:
        prov = OllamaProvider(endpoint)
        resolved = model
        if hasattr(prov, 'resolve_model'):
            resolved, _note = prov.resolve_model(model)
        token = 'OTACON_OK'
        text = prov.generate(
            resolved,
            f'Reply with exactly: {token}',
        )
        ok = token in (text or '').replace(' ', '')
        detail = 'inference probe ok' if ok else f'unexpected reply: {(text or "")[:120]}'
        _CHAT_PROBE_CACHE.update({
            'at': now, 'ok': ok, 'detail': detail, 'model': model, 'resolved': resolved,
        })
        return ok, detail, str(resolved)
    except Exception as exc:  # noqa: BLE001
        detail = f'{type(exc).__name__}: {exc}'
        _CHAT_PROBE_CACHE.update({
            'at': now, 'ok': False, 'detail': detail, 'model': model, 'resolved': model,
        })
        return False, detail, model


def _capability_snapshot() -> dict:
    """Honest capability states for the UI (ready / not_configured / unavailable / degraded / error).

    CHAT READY requires:
      1) SQLite memory usable (create/list/delete)
      2) Ollama reachable and configured model present
      3) Lightweight inference probe (cached; force via OTACON_CHAT_PROBE=1)
    """
    caps = {
        'chat': 'not_configured',
        'tts': 'not_configured',
        'stt': 'not_configured',
        'image': 'not_configured',
        'video': 'not_configured',
        'bind_mode': BIND_MODE,
        'lan_auth_required': BIND_MODE == 'lan',
        'memory_ok': False,
        'ollama_ok': False,
        'chat_probe_ok': False,
    }
    mem_ok, mem_detail = _memory_usable()
    caps['memory_ok'] = mem_ok
    if not mem_ok:
        caps['chat'] = 'error'
        caps['chat_detail'] = f'memory unusable: {mem_detail}'
    else:
        try:
            provider, endpoint, model = _llm_settings()
            if os.getenv('OTACON_USE_TEST_LLM', '').strip() in ('1', 'true', 'yes') or provider == 'test':
                caps['chat'] = 'ready'
                caps['ollama_ok'] = True
                caps['chat_probe_ok'] = True
                caps['chat_detail'] = 'test LLM'
            elif model:
                try:
                    prov = OllamaProvider(endpoint)
                    resolved = model
                    try:
                        if hasattr(prov, 'resolve_model'):
                            resolved, _note = prov.resolve_model(model)
                        else:
                            health = prov.health(model)
                            if getattr(health, 'state', '') != 'ONLINE':
                                raise RuntimeError(getattr(health, 'detail', 'model offline'))
                        caps['ollama_ok'] = True
                    except Exception as exc:
                        caps['chat'] = 'unavailable'
                        caps['chat_detail'] = f'model missing/unreachable: {exc}'
                        caps['ollama_ok'] = False
                    if caps['ollama_ok']:
                        force = os.getenv('OTACON_CHAT_PROBE', '').strip().lower() in (
                            '1', 'true', 'yes', 'force',
                        )
                        # Always require a successful (possibly cached) probe for CHAT READY.
                        # First call after restart runs a real generate; later polls use cache.
                        probe_ok, probe_detail, resolved = _chat_inference_probe(
                            endpoint, model, force=force,
                        )
                        caps['chat_probe_ok'] = probe_ok
                        caps['llm_model_resolved'] = resolved
                        if probe_ok:
                            caps['chat'] = 'ready'
                            caps['chat_detail'] = probe_detail
                        else:
                            caps['chat'] = 'unavailable'
                            caps['chat_detail'] = f'chat probe failed: {probe_detail}'
                except Exception as exc:
                    caps['chat'] = 'error'
                    caps['chat_detail'] = str(exc)
            else:
                caps['chat'] = 'not_configured'
                caps['chat_detail'] = 'no LLM model configured'
        except Exception as exc:
            caps['chat'] = 'error'
            caps['chat_detail'] = str(exc)

    try:
        # TTS is ready only when the configured provider is reachable — catalog
        # alone must never mark speech "ready" (that caused silent beeps).
        from core.voice import provider_for_assignment, TTS_READY as _TTS_READY
        from core.router import resolve as _resolve_tts
        assignment = _resolve_tts(_deployment(), 'text_to_speech')
        prov = provider_for_assignment(assignment)
        health = prov.health()
        if health in (_TTS_READY, 'ONLINE') and caps.get('chat') == 'ready':
            caps['tts'] = 'ready'
        elif health in (_TTS_READY, 'ONLINE'):
            # Piper up but chat path not proven — VOICE READY requires chat.
            caps['tts'] = 'degraded'
            caps['tts_detail'] = 'TTS healthy; chat not ready yet'
        elif os.getenv('OTACON_ALLOW_TEST_TTS', '').lower() in ('1', 'true', 'yes'):
            caps['tts'] = 'ready'
            caps['tts_detail'] = 'test TTS allowed (OTACON_ALLOW_TEST_TTS=1)'
        else:
            caps['tts'] = 'unavailable'
            caps['tts_detail'] = f'TTS health={health}'
    except Exception as exc:
        caps['tts'] = 'error'
        caps['tts_detail'] = str(exc)

    try:
        stt = FasterWhisperProvider()
        state, detail = stt.health()
        if state == 'STT_READY':
            caps['stt'] = 'ready'
        elif state == 'STT_MODEL_MISSING':
            caps['stt'] = 'not_configured'
        else:
            # Package present but model lifecycle not production-ready.
            caps['stt'] = 'unavailable'
            caps['stt_detail'] = detail
    except Exception as exc:
        caps['stt'] = 'error'
        caps['stt_detail'] = str(exc)

    caps['image'] = 'not_configured'
    caps['video'] = 'not_configured'

    # Genome Voice Trainer is an optional GPU install — report honestly, no fake UI.
    vt_home = Path.home() / 'otacon-voice-trainer'
    vt_ok = vt_home.is_dir() and any(vt_home.iterdir()) if vt_home.is_dir() else False
    caps['voice_trainer'] = 'ready' if vt_ok else 'not_configured'
    caps['voice_trainer_path'] = str(vt_home) if vt_ok else ''
    caps['llm_model'] = ''
    try:
        caps['llm_model'] = _llm_settings()[2]
    except Exception:
        pass
    return caps


class Handler(BaseHTTPRequestHandler):
    def send_json(self, data, status=200):
        b = json.dumps(data).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(b)))
        # Localhost UI may call LAN-bound API; never reflect arbitrary Origin.
        self.send_header('Access-Control-Allow-Origin', 'null' if BIND_MODE == 'lan' else '*')
        self.end_headers()
        self.wfile.write(b)

    def _require_auth_if_needed(self) -> bool:
        if not path_is_protected(self.path.split('?', 1)[0]):
            return True
        if check_lan_auth(self, BIND_MODE, LAN_TOKEN):
            return True
        self.send_json({
            'error': {
                'code': 'LAN_AUTH_REQUIRED',
                'message': 'LAN mode requires Authorization: Bearer <token> (see ~/.config/otacon/lan_token).',
            }
        }, 401)
        return False

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin', 'null' if BIND_MODE == 'lan' else '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization, X-Otacon-Token')
        self.end_headers()

    def do_GET(self):
        path = self.path.split('?', 1)[0]
        if path == '/api/scan':
            h = detect()
            self.send_json({'hardware': recommend_hardware_plan(h), 'storage': volumes()})
        elif path == '/api/branding':
            self.send_json({
                'product_name': 'Otacon',
                'tagline': 'Local AI Command System',
                'creator': 'Antonio Garcia',
                'show_creator_credit': True,
                'bind_mode': BIND_MODE,
                'bind_host': BIND_HOST,
                'lan_auth_required': BIND_MODE == 'lan',
            })
        elif path == '/api/auth/status':
            authed = True
            if BIND_MODE == 'lan':
                authed = check_lan_auth(self, BIND_MODE, LAN_TOKEN)
            self.send_json({
                'bind_mode': BIND_MODE,
                'lan_auth_required': BIND_MODE == 'lan',
                'authenticated': bool(authed),
            })
        elif path == '/api/auth/bootstrap':
            # Same-machine bootstrap only: never expose the token to LAN peers.
            if BIND_MODE != 'lan':
                self.send_json({
                    'bind_mode': 'local',
                    'lan_auth_required': False,
                    'token': None,
                    'message': 'Local mode — no bearer token required.',
                })
            elif not is_loopback_client(self):
                self.send_json({
                    'error': {
                        'code': 'LAN_BOOTSTRAP_DENIED',
                        'message': 'Token bootstrap is only available from the Otacon host (loopback). Paste the token from ~/.config/otacon/lan_token.',
                    }
                }, 403)
            else:
                token = ensure_lan_token()
                self.send_json({
                    'bind_mode': 'lan',
                    'lan_auth_required': True,
                    'token': token,
                    'message': 'Store this token in the UI session (not in source).',
                })
        elif path == '/api/capabilities':
            self.send_json(_capability_snapshot())
        elif path == '/api/voices':
            self.send_json({'voices': catalog_entries()})
        elif path == '/api/expansion/status':
            try:
                from expansion.readiness import evaluate_foundation
                from expansion.runtime import ExpansionRuntime
                rt = ExpansionRuntime(core_memory=MEMORY)
                enabled = rt.expansion_enabled()
                report = evaluate_foundation() if enabled else None
                self.send_json({
                    'enabled': enabled,
                    'foundation_ready': bool(report and report.foundation_ready()),
                    'report': report.to_dict() if report else {},
                    'agents': [
                        {
                            'id': a.agent_id,
                            'display_name': a.display_name,
                            'role': a.role,
                            'room': a.room_route,
                            'voice_id': a.voice_id,
                        }
                        for a in (rt.load_roster() if enabled else [])
                    ],
                })
            except Exception as exc:
                self.send_json({'enabled': False, 'error': str(exc), 'agents': []})
        elif path == '/api/expansion/agents':
            try:
                from expansion.runtime import ExpansionRuntime
                rt = ExpansionRuntime(core_memory=MEMORY)
                if not rt.expansion_enabled():
                    self.send_json({'enabled': False, 'agents': []})
                else:
                    self.send_json({
                        'enabled': True,
                        'agents': [a.__dict__ for a in rt.load_roster()],
                    })
            except Exception as exc:
                self.send_json({'enabled': False, 'agents': [], 'error': str(exc)})
        elif path.startswith('/api/expansion/agent/') and path.endswith('/context'):
            agent_id = path[len('/api/expansion/agent/'):-len('/context')]
            try:
                from expansion.runtime import ExpansionRuntime
                rt = ExpansionRuntime(core_memory=MEMORY)
                ctx = rt.assemble_context(agent_id)
                self.send_json({
                    'agent_id': ctx.agent_id,
                    'display_name': ctx.display_name,
                    'archetype': ctx.archetype,
                    'emotion': ctx.emotion,
                    'relationships': ctx.relationships,
                    'memories': ctx.memories,
                    'vulnerabilities': ctx.vulnerabilities,
                    'dossier_summary': ctx.dossier_summary,
                    'provenance_hints': ctx.provenance_hints,
                })
            except Exception as exc:
                self.send_json({'error': str(exc)}, 404)
        elif path.startswith('/api/expansion/'):
            from expansion.api import handle_expansion_get
            if not handle_expansion_get(path, self.send_json):
                self.send_json({'error': 'not found'}, 404)
        elif path == '/api/preferences':
            if not self._require_auth_if_needed():
                return
            self.send_json(load_preferences(CONFIG_ROOT))
        elif path == '/api/resources':
            self.send_json({'resources': [r.__dict__ for r in default_resources()]})
        elif path == '/api/nodes':
            self.send_json({'nodes': [n.__dict__ for n in NODES.nodes.values()]})
        elif path == '/api/integrations/providers':
            self.send_json({'providers': [
                {'id':'webhook','type':'WEBHOOK','fields':[{'name':'url','kind':'url','required':True},{'name':'secret','kind':'secret'}]},
                {'id':'test','type':'SMART_HOME','fields':[{'name':'display_name','kind':'text'}]},
            ]})
        elif path == '/':
            self.path = '/index.html'
            self.serve()
        else:
            self.serve()

    def do_POST(self):
        if not self._require_auth_if_needed():
            return
        n = int(self.headers.get('Content-Length', '0'))
        # Cap request body to 32 MiB to avoid trivial DoS via huge uploads.
        if n > 32 * 1024 * 1024:
            self.send_json({'error': {'code': 'PAYLOAD_TOO_LARGE', 'message': 'Request body too large.'}}, 413)
            return
        data = json.loads(self.rfile.read(n) or '{}')
        if self.path == '/api/plan':
            h = detect()
            st = data.get('storage') or recommended_volume()
            # Prefer the installer-installed model (env) over a scan-time guess so
            # Create Configuration cannot lock chat onto a model that was never pulled.
            _prov, _ep, planned_model = _llm_settings()
            rec = recommend_model(h)
            if not os.getenv('OTACON_LLM_MODEL', '').strip():
                planned_model = rec.source_id
            self.send_json({
                'config': build_config(
                    recommend_hardware_plan(h),
                    data.get('name', 'Assistant'),
                    data.get('features', []),
                    storage=st,
                    llm_service={
                        'id': 'service_llm_001',
                        'provider': _prov or 'ollama',
                        'endpoint': _ep or 'http://127.0.0.1:11434',
                        'model': planned_model or rec.source_id,
                        'model_id': rec.id,
                    },
                    agents=[{
                        'id': 'agent_001',
                        'display_name': data.get('name') or 'Aria',
                        'voice_id': data.get('voice_id') or 'voice_aria',
                        'avatar': '/assets/aria/aria.webp',
                        'role': 'primary',
                        'personality': 'friendly',
                    }],
                ),
                'storage': st,
            })
        elif self.path == '/api/save':
            try:
                root = safe_config_root(data.get('output') or CONFIG_ROOT)
            except ValueError:
                self.send_json({
                    'error': {
                        'code': 'OUTPUT_PATH_FORBIDDEN',
                        'message': 'Config output must stay under ~/.config/otacon or ~/.local/share/otacon.',
                    }
                }, 400)
                return
            try:
                cfg = data.get('config') or {}
                if 'system' not in cfg or not isinstance(cfg.get('system'), dict):
                    cfg['system'] = dict(cfg.get('system') or {})
                self.send_json({'path': str(save(cfg, root))})
            except Exception as exc:
                self.send_json({
                    'error': {
                        'code': 'SAVE_FAILED',
                        'message': 'Could not save configuration.',
                        'technical': str(exc),
                    }
                }, 400)
        elif self.path == '/api/load_configuration':
            p = CONFIG_ROOT / 'config.json'
            self.send_json(json.loads(p.read_text()) if p.is_file() else {})
        elif self.path == '/api/preferences':
            path = save_preferences(data, CONFIG_ROOT)
            self.send_json({'ok': True, 'path': str(path), **load_preferences(CONFIG_ROOT)})
        elif self.path == '/api/agent/voice':
            # Persist voice assignment into config agents list
            agent_id = data.get('agent_id') or data.get('agent', {}).get('id') or 'agent_001'
            voice_id = data.get('voice_id')
            try:
                profile_for(voice_id)
            except Exception as e:
                self.send_json({'error': {'code': 'VOICE_NOT_AVAILABLE', 'message': str(e)}}, 400)
                return
            cfg_path = CONFIG_ROOT / 'config.json'
            cfg = json.loads(cfg_path.read_text()) if cfg_path.is_file() else {
                'agents': _load_agents(), 'system': {}, 'features': {},
            }
            agents = cfg.setdefault('agents', _load_agents())
            found = False
            for a in agents:
                if a.get('id') == agent_id:
                    a['voice_id'] = voice_id
                    found = True
            if not found:
                agents.append({
                    'id': agent_id,
                    'display_name': data.get('display_name') or agent_id,
                    'voice_id': voice_id,
                })
            cfg_path.parent.mkdir(parents=True, exist_ok=True)
            cfg_path.write_text(json.dumps(cfg, indent=2) + '\n')
            self.send_json({'ok': True, 'agent_id': agent_id, 'voice_id': voice_id})
        elif self.path == '/api/chat_with_agent':
            agent = _agent_from_request(data)
            d = _deployment()
            prefs = load_preferences(CONFIG_ROOT)
            auto_speak = data.get('auto_speak')
            if auto_speak is None:
                auto_speak = prefs.get('auto_speak', False)
            try:
                cid = data.get('conversation_id') or MEMORY.create_conversation(
                    data.get('user_id', 'local_user'), agent['id']
                )
                # Refresh Expansion context with the live user message when applicable.
                if agent.get('expansion'):
                    rt = _expansion_runtime()
                    if rt is not None:
                        try:
                            ctx = rt.assemble_context(agent['id'], user_message=data.get('message', ''))
                            agent['system_prompt'] = ctx.system_prompt
                            agent['_expansion_context'] = {
                                'emotion': ctx.emotion,
                                'relationships': ctx.relationships[:5],
                                'memories': ctx.memories,
                            }
                        except Exception:
                            pass
                result = chat_with_optional_speech(
                    d, agent, data.get('message', ''), cid,
                    provider=_chat_provider(), memory=MEMORY,
                    user_id=data.get('user_id', 'local_user'),
                    auto_speak=bool(auto_speak),
                )
                if agent.get('_expansion_context'):
                    result['expansion'] = agent['_expansion_context']
                self.send_json(result)
            except Exception as e:
                err_name = type(e).__name__
                detail = str(e) or err_name
                # Log the real failure class (never disguise pre-inference crashes
                # as MODEL_RESPONSE_MISSING_TOKEN downstream).
                print(f'[CHAT] {err_name}: {detail}', flush=True)
                code = 'MEMORY_ERROR' if 'sqlite' in err_name.lower() or 'memory' in err_name.lower() else 'CHAT_UNAVAILABLE'
                if isinstance(e, sqlite3.Error) or err_name.startswith('Programming'):
                    code = 'MEMORY_ERROR'
                self.send_json({
                    'error': {
                        'code': code,
                        'message': detail if detail else 'Your AI service is unavailable.',
                        'technical': f'{err_name}: {detail}',
                        'exception': err_name,
                    }
                }, 503)
        elif self.path == '/api/expansion/event':
            try:
                from expansion.api import handle_expansion_post
                if not handle_expansion_post(self.path, data, self.send_json):
                    self.send_json({'error': 'not found'}, 404)
            except Exception as exc:
                self.send_json({'error': {'code': 'EVENT_FAILED', 'message': str(exc)}}, 400)
        elif self.path in (
            '/api/expansion/jobs/create',
            '/api/expansion/pages/register',
            '/api/expansion/rex/transition',
            '/api/expansion/rex/queue',
            '/api/expansion/rex/discover',
            '/api/expansion/rex/plan',
            '/api/expansion/rex/peer-review',
            '/api/expansion/policy/check',
            '/api/expansion/rex/tick',
            '/api/expansion/tools/invoke',
            '/api/expansion/learning/observe',
            '/api/expansion/learning/reinforce',
            '/api/expansion/learning/contradict',
            '/api/expansion/learning/revise',
        ):
            try:
                from expansion.api import handle_expansion_post
                if not handle_expansion_post(self.path, data, self.send_json):
                    self.send_json({'error': 'not found'}, 404)
            except Exception as exc:
                self.send_json({'error': {'code': 'EXPANSION_POST_FAILED', 'message': str(exc)}}, 400)
        elif self.path == '/api/expansion/bootstrap':
            try:
                from expansion.bootstrap import bootstrap_runtime_state
                self.send_json({'ok': True, **bootstrap_runtime_state()})
            except Exception as exc:
                self.send_json({'error': {'code': 'BOOTSTRAP_FAILED', 'message': str(exc)}}, 500)
        elif self.path == '/api/conversation':
            self.send_json({
                'id': MEMORY.create_conversation(
                    data.get('user_id', 'local_user'),
                    data.get('agent_id', 'agent_001'),
                    data.get('title', 'New conversation'),
                )
            })
        elif self.path == '/api/conversations':
            self.send_json(MEMORY.list_conversations(
                data.get('user_id', 'local_user'), data.get('agent_id', 'agent_001')
            ))
        elif self.path == '/api/conversation/get':
            self.send_json(MEMORY.get_conversation(
                data['id'], data.get('user_id', 'local_user'), data.get('agent_id', 'agent_001')
            ))
        elif self.path == '/api/conversation/delete':
            MEMORY.delete_conversation(
                data['id'], data.get('user_id', 'local_user'), data.get('agent_id', 'agent_001')
            )
            self.send_json({'ok': True})
        elif self.path == '/api/memory':
            MEMORY.remember(
                data.get('user_id', 'local_user'),
                data.get('agent_id', 'agent_001'),
                data.get('content', ''),
            )
            self.send_json({'ok': True})
        elif self.path in ('/api/synthesize_agent_speech', '/api/preview_voice'):
            agent = _agent_from_request(data)
            purpose = 'preview' if self.path.endswith('preview_voice') else 'production'
            text = data.get('text') or ('Hello, I am ' + agent.get('display_name', 'Aria'))
            d = _deployment()
            is_preview = purpose == 'preview'
            try:
                result = synthesize_voice(d, agent, text, purpose=purpose)
                payload = public_result(result, include_audio_b64=True)
                if is_preview:
                    print(
                        f"[TTS PREVIEW] HTTP status=200 content-type=application/json "
                        f"bytes={payload.get('byte_count')} format={payload.get('format')} "
                        f"duration={payload.get('duration_sec')}",
                        flush=True,
                    )
                self.send_json(payload)
            except TTSError as e:
                if e.code == 'TTS_SERVICE_UNREACHABLE' and _try_restart_piper_once():
                    try:
                        result = synthesize_voice(d, agent, text, purpose=purpose)
                        payload = public_result(result, include_audio_b64=True)
                        if is_preview:
                            print('[TTS PREVIEW] recovered after otacon-tts restart', flush=True)
                        self.send_json(payload)
                        return
                    except TTSError as e2:
                        e = e2
                plain = e.message
                if e.code == 'TTS_SERVICE_UNREACHABLE':
                    plain = _tts_unreachable_message()
                elif 'test double' in (e.message or '').lower() or 'near-silent' in (e.message or '').lower() or 'too short' in (e.message or '').lower():
                    plain = (
                        'Voice preview cannot play spoken audio yet. '
                        'TTS is not producing real speech (test beep or silent placeholder). '
                        'Open OtaconsKeep Setup → Repair to install/start Piper, then try Preview again.'
                    )
                if is_preview:
                    print(f'[TTS PREVIEW] FAIL code={e.code} message={e.message}', flush=True)
                self.send_json({
                    'status': 'error',
                    'code': e.code,
                    'message': 'VOICE PREVIEW FAILED' if is_preview else 'Voice playback unavailable',
                    'reason': plain,
                    'technical': e.as_dict(),
                }, 503)
        elif self.path == '/api/voice_status':
            vid = data.get('voice_id', 'voice_001')
            self.send_json({
                'voice_id': vid,
                'status': voice_status(vid),
                'catalog': CATALOG_AVAILABLE,
            })
        elif self.path == '/api/generate_image':
            try:
                if not data.get('test_mode'):
                    self.send_json({'status':'FAILED','error':{'code':'IMAGE_SERVICE_NOT_CONFIGURED','message':'Image generation is not configured.'}},503); return
                request=ImageGenerationRequest(data.get('request_id') or os.urandom(8).hex(),data.get('prompt',''),data.get('profile','standard'),agent_id=data.get('agent_id'),user_id=data.get('user_id','local_user'),conversation_id=data.get('conversation_id'))
                manager=ImageProductionManager(ResourceArbiter([ComputeResource('gpu_test',capacity={'vram_gb':24})]),TestImageProvider())
                result=manager.generate(request); self.send_json(result.__dict__,200 if result.status=='COMPLETED' else 409)
            except Exception as exc: self.send_json({'status':'FAILED','error':{'code':'IMAGE_GENERATION_FAILED','message':'Image generation failed','technical':str(exc)}},500)
        elif self.path == '/api/generate_video':
            try:
                if not data.get('test_mode'):
                    self.send_json({'status':'FAILED','error':{'code':'VIDEO_SERVICE_NOT_CONFIGURED','message':'Video generation is not configured.'}},503); return
                request=VideoGenerationRequest(data.get('request_id') or os.urandom(8).hex(),data.get('prompt',''),data.get('mode','TEXT_TO_VIDEO'),data.get('profile','normal'),source_artifact_id=data.get('source_artifact_id'),agent_id=data.get('agent_id'),user_id=data.get('user_id','local_user'),conversation_id=data.get('conversation_id'))
                manager=VideoProductionManager(ResourceArbiter([ComputeResource('gpu_test',capacity={'vram_gb':24})]),TestVideoProvider())
                result=manager.generate(request); self.send_json(result.__dict__,200 if result.status=='COMPLETED' else 409)
            except Exception as exc: self.send_json({'status':'FAILED','error':{'code':'VIDEO_GENERATION_FAILED','message':'Video generation failed','technical':str(exc)}},500)
        elif self.path == '/api/transcribe_audio':
            try:
                import base64
                raw = base64.b64decode(data.get('audio_base64', ''), validate=True)
                audio = normalize_wav(raw)
                # Test provider is opt-in for deterministic development/UI tests.
                if data.get('test_mode') is True and os.getenv('OTACON_ALLOW_TEST_PROVIDERS', '1') == '1':
                    provider = TestSTTProvider()
                else:
                    provider = FasterWhisperProvider(data.get('model_id', 'stt_small'))
                result = provider.transcribe(audio, data.get('language'))
                self.send_json(result.__dict__)
            except ValueError as e:
                self.send_json({'status': 'TRANSCRIPTION_FAILED', 'error': {'message': 'We could not process that recording.', 'technical': str(e)}}, 400)
            except Exception as e:
                self.send_json({'status': 'TRANSCRIPTION_FAILED', 'error': {'message': 'Speech recognition is unavailable.', 'technical': str(e)}}, 503)
        elif self.path == '/api/installer/voice_actions':
            agent = _agent_from_request(data)
            d = _deployment()
            actions = run_voice_actions(d, agent)
            self.send_json({
                'actions': [
                    {
                        'id': a.id,
                        'label': a.label,
                        'state': a.state,
                        'result': a.result,
                        'error': a.error,
                    }
                    for a in actions
                ]
            })
        elif self.path == '/api/installer/plan':
            self.send_json({
                'actions': [{'id': a.id, 'label': a.label} for a in action_plan(data.get('features', ['chat', 'voice']))]
            })
        elif self.path == '/api/memories':
            self.send_json(MEMORY.list_memories(
                data.get('user_id', 'local_user'), data.get('agent_id', 'agent_001')
            ))
        elif self.path == '/api/memory/delete':
            MEMORY.delete_memory(
                data['id'], data.get('user_id', 'local_user'), data.get('agent_id', 'agent_001')
            )
            self.send_json({'ok': True})
        else:
            self.send_json({'error': 'not found'}, 404)

    def serve(self):
        p = safe_ui_path(UI_ROOT, self.path)
        if p is None:
            self.send_error(404)
            return
        b = p.read_bytes()
        self.send_response(200)
        ctype = STATIC_CONTENT_TYPES.get(p.suffix.lower(), 'application/octet-stream')
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(b)))
        suf = p.suffix.lower()
        if suf in ('.mp4', '.webp', '.png', '.jpg', '.jpeg'):
            # Static agent media never changes at runtime; safe to cache hard.
            self.send_header('Cache-Control', 'public, max-age=604800, immutable')
        elif suf in ('.html', '.js', '.css', '') or p.name in ('index.html',):
            # UI shell changes often during Lite iteration — never let the browser
            # keep a stale Command Center / Codec after git pull + restart.
            self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
            self.send_header('Pragma', 'no-cache')
            self.send_header('Expires', '0')
        self.end_headers()
        self.wfile.write(b)

    def log_message(self, *a):
        pass


def main():
    global BIND_HOST, BIND_MODE, LAN_TOKEN
    BIND_HOST, BIND_MODE = resolve_bind_host()
    # Canonical Otacon Core port is 5757. Legacy 8787 was an early wizard default only.
    port = int(os.getenv('OTACON_PORT', '5757'))
    if BIND_MODE == 'lan':
        LAN_TOKEN = ensure_lan_token()
        print(f'Otacon LAN mode: http://{BIND_HOST}:{port}')
        print(f'LAN auth token: {TOKEN_HINT}')
        print('Send Authorization: Bearer <token> (file: ~/.config/otacon/lan_token)')
        print('Firewall tip: allow TCP only from your LAN subnet to this port.')
    else:
        LAN_TOKEN = load_lan_token()
        print(f'Otacon local mode: http://127.0.0.1:{port} (not reachable from LAN)')
    # Threading so a hung GPU probe (WSL nvidia-smi D-state) cannot freeze Codec/UI.
    ThreadingHTTPServer((BIND_HOST, port), Handler).serve_forever()


# Avoid printing the full token into every log line; show a short hint only.
TOKEN_HINT = '(see ~/.config/otacon/lan_token)'


if __name__ == '__main__':
    main()
