from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
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

CONFIG_ROOT = Path.home() / '.config' / 'otacon'
MEMORY = MemoryStore(CONFIG_ROOT / 'runtime' / 'memory.sqlite')
NODES = NodeRegistry()


def _llm_settings() -> tuple[str, str, str]:
    """Return (provider, endpoint, ollama_model_tag) from env/config/hardware."""
    provider = os.getenv('OTACON_LLM_PROVIDER', 'ollama').strip().lower() or 'ollama'
    endpoint = os.getenv('OTACON_LLM_ENDPOINT', 'http://127.0.0.1:11434').rstrip('/')
    model = os.getenv('OTACON_LLM_MODEL', '').strip()

    cfg_path = CONFIG_ROOT / 'config.json'
    if cfg_path.is_file():
        try:
            cfg = json.loads(cfg_path.read_text())
            svc = cfg.get('llm_service') or {}
            provider = (svc.get('provider') or provider).strip().lower() or provider
            endpoint = (svc.get('endpoint') or endpoint).rstrip('/')
            model = (svc.get('model') or model).strip()
        except (OSError, json.JSONDecodeError):
            pass

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
        tts_endpoint=os.getenv('OTACON_TTS_ENDPOINT', 'test://tts'),
        tts_provider=os.getenv('OTACON_TTS_PROVIDER', 'test'),
    )


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
        {'id': 'agent_001', 'display_name': 'Billy', 'voice_id': 'voice_001'},
        {'id': 'agent_002', 'display_name': 'Sarah', 'voice_id': 'voice_002'},
    ]


def _agent_from_request(data: dict) -> dict:
    agents = _load_agents()
    agent = dict(data.get('agent') or {})
    if not agent.get('id'):
        agent['id'] = data.get('agent_id') or 'agent_001'
    if not agent.get('display_name'):
        agent['display_name'] = data.get('display_name') or next(
            (a['display_name'] for a in agents if a['id'] == agent['id']), 'Billy'
        )
    if not agent.get('voice_id'):
        saved = next((a for a in agents if a['id'] == agent['id']), None)
        agent['voice_id'] = data.get('voice_id') or (saved or {}).get('voice_id') or 'voice_001'
    return agent


class Handler(BaseHTTPRequestHandler):
    def send_json(self, data, status=200):
        b = json.dumps(data).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        if self.path == '/api/scan':
            h = detect()
            self.send_json({'hardware': recommend_hardware_plan(h), 'storage': volumes()})
        elif self.path == '/api/branding':
            self.send_json({
                'product_name': 'Otacon',
                'tagline': 'Local AI Command System',
                'creator': 'Antonio Garcia',
                'show_creator_credit': True,
            })
        elif self.path == '/api/voices':
            self.send_json({'voices': catalog_entries()})
        elif self.path == '/api/preferences':
            self.send_json(load_preferences(CONFIG_ROOT))
        elif self.path == '/api/resources':
            self.send_json({'resources': [r.__dict__ for r in default_resources()]})
        elif self.path == '/api/nodes':
            self.send_json({'nodes': [n.__dict__ for n in NODES.nodes.values()]})
        elif self.path == '/api/integrations/providers':
            self.send_json({'providers': [
                {'id':'webhook','type':'WEBHOOK','fields':[{'name':'url','kind':'url','required':True},{'name':'secret','kind':'secret'}]},
                {'id':'test','type':'SMART_HOME','fields':[{'name':'display_name','kind':'text'}]},
            ]})
        elif self.path == '/':
            self.path = '/index.html'
            self.serve()
        else:
            self.serve()

    def do_POST(self):
        n = int(self.headers.get('Content-Length', '0'))
        data = json.loads(self.rfile.read(n) or '{}')
        if self.path == '/api/plan':
            h = detect()
            st = data.get('storage') or recommended_volume()
            self.send_json({
                'config': build_config(
                    recommend_hardware_plan(h),
                    data.get('name', 'Assistant'),
                    data.get('features', []),
                    storage=st,
                    llm_service={
                        'id': 'service_llm_001',
                        'provider': 'ollama',
                        'endpoint': 'http://127.0.0.1:11434',
                        'model': recommend_model(h).source_id,
                        'model_id': recommend_model(h).id,
                    },
                ),
                'storage': st,
            })
        elif self.path == '/api/save':
            root = Path(data.get('output') or CONFIG_ROOT)
            self.send_json({'path': str(save(data['config'], root))})
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
            cid = data.get('conversation_id') or MEMORY.create_conversation(
                data.get('user_id', 'local_user'), agent['id']
            )
            try:
                result = chat_with_optional_speech(
                    d, agent, data.get('message', ''), cid,
                    provider=_chat_provider(), memory=MEMORY,
                    user_id=data.get('user_id', 'local_user'),
                    auto_speak=bool(auto_speak),
                )
                self.send_json(result)
            except Exception as e:
                self.send_json({
                    'error': {
                        'code': 'CHAT_UNAVAILABLE',
                        'message': 'Your AI service is unavailable.',
                        'technical': str(e),
                    }
                }, 503)
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
            text = data.get('text') or ('Hello, I am ' + agent.get('display_name', 'Billy'))
            d = _deployment()
            try:
                result = synthesize_voice(d, agent, text, purpose=purpose)
                self.send_json(public_result(result, include_audio_b64=True))
            except TTSError as e:
                self.send_json({
                    'status': 'error',
                    'code': e.code,
                    'message': 'Voice playback unavailable',
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
        p = Path(__file__).parent.parent / 'ui' / self.path.lstrip('/')
        if not p.is_file():
            self.send_error(404)
            return
        b = p.read_bytes()
        self.send_response(200)
        ctype = 'text/html' if p.suffix == '.html' else 'application/javascript'
        if p.suffix == '.css':
            ctype = 'text/css'
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def log_message(self, *a):
        pass


def main():
    port = int(os.getenv('OTACON_PORT', '8787'))
    print(f'Wizard: http://127.0.0.1:{port}')
    HTTPServer(('127.0.0.1', port), Handler).serve_forever()


if __name__ == '__main__':
    main()
