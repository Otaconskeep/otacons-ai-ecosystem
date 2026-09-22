"""HTTP handlers for Expansion P2 surfaces (imported by installer.server).

Never returns full system prompts, credentials, or package keys.
"""
from __future__ import annotations

from dataclasses import asdict


def handle_expansion_get(path: str, send_json, send_bytes=None) -> bool:
    """Return True if handled.

    send_bytes(data, content_type, filename) is optional — used to proxy
    Creative job outputs through Otacon instead of redirecting to Comfy :8188.
    """
    if path == '/api/expansion/voice-trainer/install-status':
        from expansion.capabilities.voice_trainer import genome_install_status, probe_voice_trainer
        st = genome_install_status()
        report = probe_voice_trainer()
        send_json({
            **st,
            'state': report.state,
            'detail': report.detail,
            'discovery': report.discovery,
        })
        return True
    if path == '/api/expansion/voice-trainer/train-status':
        from expansion.capabilities.voice_trainer import genome_train_status, probe_voice_trainer
        report = probe_voice_trainer()
        send_json({
            'train': genome_train_status(),
            'state': report.state,
            'discovery': report.discovery,
        })
        return True
    if path == '/api/expansion/studio/hardware-profile':
        from expansion.capabilities.studio_setup import studio_hardware_snapshot
        send_json(studio_hardware_snapshot())
        return True
    if path == '/api/expansion/video-studio/hardware-profile':
        from expansion.capabilities.studio_setup import studio_hardware_snapshot
        send_json(studio_hardware_snapshot())
        return True
    if path == '/api/expansion/command':
        from expansion.floors import build_command_floor
        from expansion.runtime import ExpansionRuntime
        rt = ExpansionRuntime()
        if not rt.expansion_enabled():
            send_json({'enabled': False})
            return True
        send_json(build_command_floor())
        return True
    if path == '/api/expansion/dashboard':
        from expansion.floors import build_dashboard
        send_json(build_dashboard())
        return True
    if path == '/api/expansion/intel':
        from expansion.floors import build_intel_floor
        from expansion.runtime import ExpansionRuntime
        if not ExpansionRuntime().expansion_enabled():
            send_json({'enabled': False})
            return True
        send_json(build_intel_floor())
        return True
    if path == '/api/expansion/dossiers':
        from expansion.floors import build_dossiers_index
        from expansion.runtime import ExpansionRuntime
        if not ExpansionRuntime().expansion_enabled():
            send_json({'enabled': False, 'agents': []})
            return True
        send_json(build_dossiers_index())
        return True
    if path.startswith('/api/expansion/dossiers/'):
        from expansion.floors import build_dossier_card
        from expansion.canonical_dossiers import CANONICAL_AGENT_IDS
        agent_id = path.rsplit('/', 1)[-1]
        if agent_id not in CANONICAL_AGENT_IDS:
            send_json({'error': 'unknown agent'}, 404)
            return True
        send_json(build_dossier_card(agent_id))
        return True
    if path == '/api/expansion/creative':
        from expansion.jobs import JobStore
        from expansion.capabilities.video_studio import probe_video_studio, studio_runtime_context
        from expansion.capabilities.comfy_sidecar import detect_local_comfy
        from expansion.capabilities.comfy_submit import (
            ensure_creative_poller,
            fail_stale_fake_creative_jobs,
            image_workflow_status,
            poll_creative_jobs_once,
            public_creative_job,
        )
        from expansion.capabilities.studio_setup import setup_status, studio_hardware_snapshot
        from expansion.persist import read_json
        from expansion.release_info import release_identity
        from expansion.state_layout import resolve_layout
        from expansion.readiness import evaluate_foundation
        ensure_creative_poller()
        fail_stale_fake_creative_jobs()
        try:
            poll_creative_jobs_once()
        except Exception:
            pass
        jobs = [j for j in JobStore().list(agent_id='muse', limit=40)]
        pub_jobs = [public_creative_job(j) for j in jobs]
        vs = probe_video_studio()
        detected = detect_local_comfy()
        setup = setup_status()
        hw = studio_hardware_snapshot()
        layout = resolve_layout()
        creative_settings = read_json(
            layout.user_preferences / 'studio_creative_settings.json', default={}
        ) or {}
        defaults = {}
        try:
            from pathlib import Path
            import json as _json
            defaults_path = Path(__file__).resolve().parent / 'product' / 'studio' / 'keep_defaults.json'
            if defaults_path.is_file():
                defaults = _json.loads(defaults_path.read_text(encoding='utf-8'))
        except Exception:
            defaults = {}
        disc = vs.discovery if hasattr(vs, 'discovery') else (vs.to_dict().get('discovery') or {})
        endpoint = (
            (disc or {}).get('endpoint')
            or setup.get('endpoint')
            or detected.get('endpoint')
            or ''
        )
        workflow = image_workflow_status(endpoint or None)
        try:
            from expansion.capabilities.studio_packs import packs_status, ensure_auto_install
            packs = packs_status(layout=layout, endpoint=endpoint or None, hw=hw)
            # Continue auto-pull while any profile pack is needed — not only when
            # soft_block (Z-Image missing). Video/music must not stall after image.
            _need_more = bool(packs.get('needed')) and not packs.get('ok')
            if (
                vs.state == 'READY'
                and not packs.get('running')
                and (packs.get('soft_block') or _need_more)
            ):
                auto = ensure_auto_install(layout=layout, hw=hw, studio_ready=True)
                if auto.get('auto_started') or auto.get('running'):
                    packs = packs_status(layout=layout, endpoint=endpoint or None, hw=hw)
                    packs['auto_started'] = True
        except Exception as exc:  # noqa: BLE001
            packs = {
                'ok': False,
                'image_ready': bool(workflow.get('ok')),
                'soft_block': not bool(workflow.get('ok')),
                'action': '' if workflow.get('ok') else 'install_packs',
                'aria': str(exc)[:200],
                'packs': {},
            }
        # Three readiness levels — image gen must not wait on video/music packs
        # or a READY-only Studio label when Comfy + Z-Image assets are usable.
        from expansion.capabilities.video_studio import comfy_endpoint_healthy
        comfy_ok = False
        if endpoint:
            comfy_ok, _ = comfy_endpoint_healthy(endpoint, timeout=2.0)
        studio_ready = bool(comfy_ok or vs.state == 'READY')
        assets_ready = bool(workflow.get('ok') or packs.get('image_ready'))
        try:
            from expansion.capabilities.comfy_submit import submit_image_job as _submit_fn
            submitter_ready = callable(_submit_fn)
        except Exception:
            submitter_ready = False
        generation_ready = bool(studio_ready and assets_ready and submitter_ready)
        gen_ok = generation_ready
        if packs.get('running'):
            blocked = packs.get('aria') or (
                'Creative packs are downloading — Generate unlocks when Z-Image finishes.'
            )
        elif generation_ready:
            blocked = ''
        elif studio_ready and assets_ready and not submitter_ready:
            blocked = (
                'Z-Image assets are installed and ComfyUI is connected, '
                'but /creative still needs a Comfy workflow submitter.'
            )
        elif studio_ready and not assets_ready:
            blocked = packs.get('aria') or workflow.get('detail') or (
                'ComfyUI is connected, but Z-Image model assets are not installed yet.'
            )
        else:
            blocked = packs.get('aria') or (
                'Video Studio is not connected yet. Set up Studio first.'
            )
        readiness = {
            'studio_ready': studio_ready,
            'assets_ready': assets_ready,
            'generation_ready': generation_ready,
            'submitter_ready': submitter_ready,
        }
        rel_id = release_identity()
        send_json({
            'surface': 'muse_creative',
            'release': rel_id,
            'creative_queue': [j for j in pub_jobs
                               if j.get('status') in ('QUEUED', 'ASSIGNED', 'RUNNING')
                               and j.get('domain') in ('creative', 'media')],
            'active_renders': [j for j in pub_jobs
                               if j.get('status') == 'RUNNING'
                               and j.get('domain') in ('creative', 'media')],
            'recent_creative_jobs': [j for j in pub_jobs if j.get('domain') in ('creative', 'media')][:15],
            'recent_output': [j for j in pub_jobs
                              if j.get('status') == 'COMPLETE' and j.get('domain') in ('creative', 'media')][:10],
            'capabilities': {
                'generation': 'comfy_prompt' if gen_ok else 'packs_needed',
                'video_studio': vs.state,
                'voice_motion': 'readiness_dependent',
                'image_workflow': workflow,
                'packs': packs,
                'readiness': readiness,
            },
            'readiness': readiness,
            'video_studio': vs.to_dict(),
            'video_studio_readiness': vs.state,
            'comfy_detect': detected,
            'runtime_context': studio_runtime_context('muse'),
            'foundation': evaluate_foundation().to_dict(),
            'setup': {
                'phase': setup.get('phase'),
                'ok': setup.get('ok'),
                'running': setup.get('running'),
                'endpoint': endpoint,
                'source': setup.get('source') or '',
                'release_pin': rel_id.get('release_pin_short') or '',
                'repo_head': rel_id.get('repo_head_short') or '',
                'release_detail': rel_id.get('detail') or '',
            },
            'packs': packs,
            'studio': {
                'endpoint': endpoint,
                'healthy': bool((disc or {}).get('healthy') or vs.state == 'READY'),
                'hardware': hw,
                'settings': creative_settings,
                'engines': (defaults.get('engines') or {}),
                'optimal_prompts': (defaults.get('optimal_prompts') or {}),
                'actors': (defaults.get('actors') or []),
                'styles': (defaults.get('styles') or []),
                'music_advanced': (defaults.get('music_advanced') or {}),
                'image_widgets': (defaults.get('image_widgets') or []),
                'workflow': workflow,
                'packs': packs,
                'readiness': readiness,
                'studio_ready': studio_ready,
                'assets_ready': assets_ready,
                'generation_ready': generation_ready,
                'generate_enabled': gen_ok,
                'generate_blocked_reason': blocked,
                'soft_block': (not gen_ok) and bool(
                    packs.get('soft_block') or (studio_ready and not assets_ready)
                ),
                'action': packs.get('action') or ('' if gen_ok else 'install_packs'),
                'modalities': [
                    {
                        'id': 'image',
                        'label': 'Image',
                        'engine': ((hw.get('image') or {}).get('engine')
                                   or ((creative_settings.get('image') or {}).get('engine'))
                                   or 'z-image-turbo'),
                        'tier': ((hw.get('image') or {}).get('tier') or 'local'),
                        'workflow_ready': bool(workflow.get('ok') or packs.get('image_ready')),
                    },
                    {
                        'id': 'video',
                        'label': 'Video',
                        'engine': ((hw.get('video') or {}).get('engine')
                                   or ((creative_settings.get('video') or {}).get('engine'))
                                   or 'wan-2.2-5b'),
                        'tier': ((hw.get('video') or {}).get('tier') or 'local'),
                        'workflow_ready': bool((packs.get('packs') or {}).get('wan', {}).get('ok')
                                               or (packs.get('packs') or {}).get('ltx2', {}).get('ok')),
                    },
                    {
                        'id': 'music',
                        'label': 'Music',
                        'engine': ((hw.get('music') or {}).get('engine')
                                   or ((creative_settings.get('music') or {}).get('engine'))
                                   or 'ace-step-1.5'),
                        'tier': ((hw.get('music') or {}).get('tier') or 'local'),
                        'workflow_ready': bool((packs.get('packs') or {}).get('ace_step', {}).get('ok')),
                    },
                ],
            },
            'honest_note': (
                'Expansion Video Studio — READY when ComfyUI is connected. '
                'Generate unlocks after creative packs (Z-Image) are installed.'
            ),
            'note': 'Muse owns Video Studio. Missing packs soft-block Generate — never fake RUNNING.',
        })
        return True
    if path.startswith('/api/expansion/creative/jobs/') and path.endswith('/output'):
        from expansion.capabilities.comfy_submit import (
            endpoint_from_job,
            fetch_comfy_output_bytes,
            outputs_from_job,
            poll_creative_jobs_once,
        )
        from expansion.jobs import JobStore
        jid = path[len('/api/expansion/creative/jobs/'):-len('/output')].strip('/')
        if not jid:
            send_json({'error': 'job_id required'}, 400)
            return True
        try:
            poll_creative_jobs_once()
        except Exception:
            pass
        job = JobStore().get(jid)
        if not job:
            send_json({'error': 'not found'}, 404)
            return True
        files = outputs_from_job(job)
        if not files:
            send_json({
                'ok': False,
                'error': 'output not ready',
                'status': job.status,
                'job_id': jid,
            }, 404)
            return True
        data, mime, name = fetch_comfy_output_bytes(
            filename=files[0],
            endpoint=endpoint_from_job(job),
        )
        if data is None:
            send_json({
                'ok': False,
                'error': 'output not ready',
                'detail': 'Could not load Comfy output through Otacon proxy.',
                'filename': files[0],
                'job_id': jid,
            }, 404)
            return True
        if callable(send_bytes):
            send_bytes(data, mime, name or files[0])
            return True
        send_json({
            'ok': False,
            'error': 'byte_sender_missing',
            'detail': (
                'Creative output proxy needs send_bytes from installer.server. '
                'Soft-update Expansion and restart otacon.service.'
            ),
            'filename': name or files[0],
            'job_id': jid,
            'content_type': mime,
        }, 500)
        return True
    if path.startswith('/api/expansion/creative/jobs/'):
        from expansion.capabilities.comfy_submit import poll_creative_jobs_once, public_creative_job
        from expansion.jobs import JobStore
        jid = path.rsplit('/', 1)[-1]
        try:
            poll_creative_jobs_once()
        except Exception:
            pass
        job = JobStore().get(jid)
        if not job:
            send_json({'error': 'not found'}, 404)
            return True
        send_json(public_creative_job(job))
        return True
    if path == '/api/expansion/release':
        from expansion.release_info import release_identity
        send_json(release_identity())
        return True
    if path == '/api/expansion/creative/packs':
        from expansion.capabilities.studio_packs import packs_status
        from expansion.capabilities.studio_setup import studio_hardware_snapshot
        from expansion.capabilities.video_studio import probe_video_studio
        vs = probe_video_studio()
        ep = ((vs.discovery or {}).get('endpoint') or '')
        send_json(packs_status(endpoint=ep or None, hw=studio_hardware_snapshot()))
        return True
    if path == '/api/expansion/video-studio/detect':
        from expansion.capabilities.comfy_sidecar import detect_local_comfy, probe_docker_engine
        from expansion.capabilities.video_studio import probe_video_studio
        from expansion.capabilities.studio_setup import setup_status
        detected = detect_local_comfy()
        report = probe_video_studio()
        docker = probe_docker_engine()
        send_json({
            **detected,
            'configured_state': report.state,
            'configured_detail': report.detail,
            'video_studio': report.to_dict(),
            'docker': docker,
            'setup': setup_status(),
        })
        return True
    if path == '/api/expansion/video-studio/setup-status':
        from expansion.capabilities.studio_setup import setup_status
        send_json(setup_status())
        return True
    if path == '/api/expansion/ops':
        from expansion.floors import build_ops_floor
        send_json(build_ops_floor())
        return True
    if path == '/api/expansion/capabilities':
        from expansion.capabilities.discord_n8n import probe_all_optional
        send_json({'capabilities': probe_all_optional()})
        return True
    if path == '/api/expansion/integrations':
        from expansion.capabilities.integrations_setup import integrations_status
        send_json(integrations_status())
        return True
    if path == '/api/expansion/discord/invite':
        from expansion.capabilities.discord_n8n import discord_invite_url, probe_discord
        inv = discord_invite_url()
        report = probe_discord()
        send_json({**inv, 'state': report.state, 'discovery': report.discovery})
        return True
    if path == '/api/expansion/home-assistant/entities':
        from expansion.capabilities.home_assistant import verify_home_assistant, load_ha_config
        cfg = load_ha_config()
        if not cfg.get('url') or not cfg.get('token_configured'):
            send_json({'ok': False, 'error': 'HA not configured', 'config': cfg}, 400)
            return True
        send_json(verify_home_assistant())
        return True
    if path == '/api/expansion/rooms':
        from expansion.rooms import RoomRegistry
        rooms = RoomRegistry().seed_defaults()
        send_json({
            'rooms': [
                {
                    'page_id': r.page_id,
                    'name': r.name,
                    'route': r.route,
                    'owner_agent': r.owner_agent,
                    'icon': r.icon,
                    'description': r.description,
                    'required_capabilities': list(r.required_capabilities or ()),
                    'permissions': list(r.permissions or ()),
                    'health_source': r.health_source,
                    'enabled': r.enabled,
                    'shared': r.shared,
                    'kind': r.kind,
                }
                for r in rooms
            ]
        })
        return True
    if path == '/api/expansion/war-room':
        from expansion.entitlement import EntitlementGate
        from expansion.floors import build_war_room
        if not EntitlementGate().expansion_surfaces_allowed():
            send_json({'enabled': False, 'message': 'Expansion not entitled'})
            return True
        send_json(build_war_room())
        return True
    if path == '/api/expansion/rex':
        from expansion.entitlement import EntitlementGate
        from expansion.rex import build_rex_board
        if not EntitlementGate().expansion_surfaces_allowed():
            send_json({'enabled': False, 'message': 'Expansion not entitled'})
            return True
        send_json(build_rex_board())
        return True
    if path == '/api/expansion/rex/autonomy':
        from expansion.entitlement import EntitlementGate
        from expansion.rex import build_autonomy_dashboard
        from expansion.tools import ToolGateway
        if not EntitlementGate().expansion_surfaces_allowed():
            send_json({'enabled': False, 'message': 'Expansion not entitled'})
            return True
        payload = build_autonomy_dashboard()
        payload['recent_tool_actions'] = ToolGateway().recent(limit=25)
        send_json(payload)
        return True
    if path == '/api/expansion/launchpad':
        from expansion.launchpad import build_launchpad
        send_json(build_launchpad())
        return True
    if path == '/api/expansion/world-model':
        from expansion.entitlement import EntitlementGate
        from expansion.world_model import get_world_model
        if not EntitlementGate().expansion_surfaces_allowed():
            send_json({'enabled': False, 'message': 'Expansion not entitled'})
            return True
        send_json(get_world_model().get_world_state())
        return True
    if path == '/api/expansion/route-learning':
        from expansion.entitlement import EntitlementGate
        from expansion.route_learning import pool_summary
        if not EntitlementGate().expansion_surfaces_allowed():
            send_json({'enabled': False, 'message': 'Expansion not entitled'})
            return True
        send_json(pool_summary())
        return True
    if path == '/api/expansion/policy':
        from expansion.entitlement import EntitlementGate
        from expansion.policy import PolicyEngine
        if not EntitlementGate().expansion_surfaces_allowed():
            send_json({'enabled': False, 'message': 'Expansion not entitled'})
            return True
        send_json(PolicyEngine().summary())
        return True
    if path == '/api/expansion/learning':
        from expansion.entitlement import EntitlementGate
        from expansion.learning import LearningEngine
        if not EntitlementGate().expansion_surfaces_allowed():
            send_json({'enabled': False, 'message': 'Expansion not entitled'})
            return True
        send_json(LearningEngine().board_payload())
        return True
    if path == '/api/expansion/learning/shared':
        from expansion.entitlement import EntitlementGate
        from expansion.learning import LearningEngine
        if not EntitlementGate().expansion_surfaces_allowed():
            send_json({'enabled': False, 'message': 'Expansion not entitled'})
            return True
        eng = LearningEngine()
        claims = [eng.claim_card(c) for c in eng.store.list_claims(scope='shared') if c.status != 'retired']
        send_json({'scope': 'shared', 'curator': 'ledger', 'claims': claims})
        return True
    if path.startswith('/api/expansion/learning/agent/'):
        from expansion.entitlement import EntitlementGate
        from expansion.learning import LearningEngine
        if not EntitlementGate().expansion_surfaces_allowed():
            send_json({'enabled': False, 'message': 'Expansion not entitled'})
            return True
        agent_id = path.rsplit('/', 1)[-1]
        send_json(LearningEngine().agent_learning_surface(agent_id))
        return True
    if path.startswith('/api/expansion/learning/why/'):
        from expansion.entitlement import EntitlementGate
        from expansion.learning import LearningEngine
        if not EntitlementGate().expansion_surfaces_allowed():
            send_json({'enabled': False, 'message': 'Expansion not entitled'})
            return True
        claim_id = path.rsplit('/', 1)[-1]
        try:
            send_json(LearningEngine().why(claim_id))
        except KeyError:
            send_json({'error': 'claim not found'}, 404)
        return True
    if path.startswith('/api/expansion/learning/observations'):
        from expansion.entitlement import EntitlementGate
        from expansion.learning import LearningEngine
        from dataclasses import asdict as _asdict
        if not EntitlementGate().expansion_surfaces_allowed():
            send_json({'enabled': False, 'message': 'Expansion not entitled'})
            return True
        # /api/expansion/learning/observations or .../observations/{agent_id}
        parts = path.strip('/').split('/')
        agent_id = parts[4] if len(parts) > 4 else None
        eng = LearningEngine()
        obs = eng.store.list_observations(agent_id=agent_id, limit=80)
        send_json({'observations': [_asdict(o) for o in obs]})
        return True
    if path == '/api/expansion/reports':
        from expansion.reports import build_agent_report
        from expansion.runtime import ExpansionRuntime
        from expansion.learning import LearningEngine
        rt = ExpansionRuntime()
        if not rt.expansion_enabled():
            send_json({'enabled': False, 'reports': []})
            return True
        eng = LearningEngine()
        reports = []
        for a in rt.load_roster():
            rep = build_agent_report(a.agent_id)
            rep['learning'] = eng.agent_learning_surface(a.agent_id)
            reports.append(rep)
        send_json({'enabled': True, 'reports': reports})
        return True
    if path.startswith('/api/expansion/reports/'):
        from expansion.reports import build_agent_report
        agent_id = path.rsplit('/', 1)[-1]
        try:
            send_json(build_agent_report(agent_id))
        except KeyError:
            send_json({'error': 'unknown agent'}, 404)
        return True
    if path == '/api/expansion/journal' or path.startswith('/api/expansion/journal/'):
        from expansion.floors import build_journal_browser
        parts = path.strip('/').split('/')
        agent_id = parts[3] if len(parts) > 3 else None
        send_json(build_journal_browser(agent_id=agent_id))
        return True
    if path == '/api/expansion/diary':
        from expansion.floors import build_diary_index
        send_json(build_diary_index())
        return True
    if path.startswith('/api/expansion/diary/'):
        from expansion.diary import DiaryStore
        parts = path.strip('/').split('/')
        agent_id = parts[3] if len(parts) > 3 else ''
        if len(parts) > 4 and parts[4] == 'explain' and len(parts) > 5:
            try:
                send_json(DiaryStore().explain(agent_id, parts[5]))
            except KeyError:
                send_json({'error': 'not found'}, 404)
            return True
        from expansion.canonical_dossiers import get_canonical_dossier
        d = get_canonical_dossier(agent_id)
        send_json({
            'entries': DiaryStore().recent(agent_id, limit=50),
            'agent_id': agent_id,
            'diary_style': d.character.diary_style,
            'kind': 'diary',
            'rule': 'DIARY = WHAT IT MEANT',
        })
        return True
    if path.startswith('/api/expansion/living/'):
        from expansion.living_dossier import LivingDossierStore
        parts = path.strip('/').split('/')
        agent_id = parts[3]
        store = LivingDossierStore()
        if len(parts) > 4 and parts[4] == 'explain' and len(parts) > 5:
            try:
                send_json(store.explain(agent_id, parts[5]))
            except KeyError:
                send_json({'error': 'not found'}, 404)
            return True
        doc = store.load(agent_id)
        send_json({
            'agent_id': agent_id,
            'observations': [asdict(o) for o in doc.observations],
            'notes': doc.notes,
        })
        return True
    if path == '/api/expansion/emotion':
        from expansion.floors import build_emotion_roster
        send_json(build_emotion_roster())
        return True
    if path.startswith('/api/expansion/emotion/'):
        from expansion.emotion_store import EmotionStore
        from expansion.canonical_dossiers import get_canonical_dossier
        from expansion.emotion import EMOTION_DIMENSIONS
        parts = path.strip('/').split('/')
        agent_id = parts[3]
        emo = EmotionStore().get_or_create(agent_id)
        if len(parts) > 4 and parts[4] == 'why' and len(parts) > 5:
            send_json(emo.explain(parts[5]))
            return True
        dossier = get_canonical_dossier(agent_id)
        send_json({
            'agent_id': agent_id,
            'dimensions': emo.dimensions,
            'baseline': emo.baseline,
            'product_baseline': dict(dossier.stress.emotional_baseline or {}),
            'updated_at': emo.updated_at,
            'provenance': list(emo.provenance or [])[-20:],
            'primary': sorted(emo.dimensions.items(), key=lambda kv: kv[1], reverse=True)[:5],
            'secondary': sorted(emo.dimensions.items(), key=lambda kv: kv[1], reverse=True)[5:10],
            'all_dimensions': list(EMOTION_DIMENSIONS),
            'stress_behavior': dossier.stress.stress_behavior,
            'recovery_behavior': dossier.stress.recovery_behavior,
        })
        return True
    if path.startswith('/api/expansion/relationships'):
        from expansion.relationship_interpret import RelationshipInterpreter
        from expansion.canonical_dossiers import CANONICAL_AGENT_IDS
        interp = RelationshipInterpreter()
        parts = path.strip('/').split('/')
        if len(parts) >= 6 and parts[3] and parts[4] and parts[5] == 'why':
            send_json(interp.why(parts[3], parts[4]))
            return True
        if len(parts) >= 5 and parts[3] and parts[4]:
            s = interp.summarize(parts[3], parts[4])
            why = interp.why(parts[3], parts[4])
            payload = asdict(s)
            payload['why'] = why
            send_json(payload)
            return True
        agents = list(CANONICAL_AGENT_IDS) + ['user_primary']
        matrix = interp.matrix(agents)
        dims = (
            'trust', 'affinity', 'respect', 'familiarity', 'dependency',
            'conflict', 'rivalry', 'jealousy', 'protectiveness', 'reliability', 'attachment',
        )
        send_json({
            'surface': 'relationships',
            'agents': agents,
            'dimensions': list(dims),
            'matrix': matrix,
            'rule': 'Directional multi-dimension matrix — not a single score.',
        })
        return True
    if path == '/api/expansion/jobs':
        from expansion.jobs import JobStore
        send_json({'jobs': [asdict(j) for j in JobStore().list(limit=100)]})
        return True
    if path == '/api/expansion/entitlement':
        from expansion.entitlement import EntitlementGate
        g = EntitlementGate()
        st = g.current()
        send_json({
            'expansion_entitled': st.expansion_entitled,
            'source': st.source,
            'message': st.message,
            'user_data_accessible': g.user_data_accessible(),
            # Never expose keys/secrets
        })
        return True
    return False


def handle_expansion_post(path: str, data: dict, send_json) -> bool:
    if path == '/api/expansion/voice-trainer/start':
        from expansion.capabilities.voice_trainer import ensure_genome, probe_voice_trainer
        result = ensure_genome(auto_install=True)
        report = probe_voice_trainer()
        send_json({
            **result,
            'state': report.state,
            'detail': report.detail,
            'discovery': report.discovery,
        })
        return True
    if path == '/api/expansion/voice-trainer/install':
        from expansion.capabilities.voice_trainer import install_voice_trainer, probe_voice_trainer
        result = install_voice_trainer()
        report = probe_voice_trainer()
        send_json({
            **result,
            'state': report.state,
            'detail': report.detail,
            'discovery': report.discovery,
        })
        return True
    if path == '/api/expansion/voice-trainer/train':
        from expansion.capabilities.voice_trainer import start_genome_train, probe_voice_trainer
        name = str((data or {}).get('name') or '').strip()
        urls = (data or {}).get('urls') or []
        if isinstance(urls, str):
            urls = [u.strip() for u in urls.splitlines() if u.strip()]
        else:
            urls = [str(u).strip() for u in urls if str(u).strip()]
        result = start_genome_train(name=name, urls=urls)
        report = probe_voice_trainer()
        send_json({
            **result,
            'state': report.state,
            'discovery': report.discovery,
        })
        return True
    if path == '/api/expansion/discord/token':
        from expansion.capabilities.discord_n8n import save_discord_bot_token, probe_discord
        token = str((data or {}).get('token') or (data or {}).get('bot_token') or '').strip()
        try:
            result = save_discord_bot_token(token)
        except ValueError as exc:
            send_json({'ok': False, 'error': str(exc)}, 400)
            return True
        report = probe_discord()
        send_json({**result, 'detail': report.detail, 'discovery': report.discovery})
        return True
    if path == '/api/expansion/discord/authorized':
        from expansion.capabilities.discord_n8n import mark_discord_guild_authorized, probe_discord
        guild = str((data or {}).get('guild_id') or '').strip()
        result = mark_discord_guild_authorized(guild)
        report = probe_discord()
        send_json({**result, 'detail': report.detail, 'discovery': report.discovery})
        return True
    if path == '/api/expansion/discord/setup':
        from expansion.capabilities.integrations_setup import configure_integration
        send_json(configure_integration(
            'discord',
            token=str((data or {}).get('token') or (data or {}).get('bot_token') or ''),
            guild_id=str((data or {}).get('guild_id') or ''),
        ))
        return True
    if path == '/api/expansion/discord/start':
        from expansion.capabilities.discord_n8n import start_discord_bot
        send_json(start_discord_bot())
        return True
    if path == '/api/expansion/home-assistant/config':
        from expansion.capabilities.home_assistant import save_ha_config, probe_home_assistant
        from expansion.capabilities.integrations_setup import configure_integration
        url = str((data or {}).get('url') or '').strip()
        token = str((data or {}).get('token') or '').strip()
        verify = bool((data or {}).get('verify', True))
        if verify and url and token:
            send_json(configure_integration('home_assistant', url=url, token=token))
            return True
        try:
            cfg = save_ha_config(url, token=token)
        except ValueError as exc:
            send_json({'ok': False, 'error': str(exc)}, 400)
            return True
        report = probe_home_assistant()
        send_json({'ok': True, 'config': cfg, 'state': report.state, 'detail': report.detail})
        return True
    if path == '/api/expansion/home-assistant/verify':
        from expansion.capabilities.home_assistant import verify_home_assistant
        send_json(verify_home_assistant())
        return True
    if path == '/api/expansion/n8n/setup':
        from expansion.capabilities.integrations_setup import configure_integration
        send_json(configure_integration('n8n'))
        return True
    if path == '/api/expansion/n8n/config':
        from expansion.capabilities.discord_n8n import save_n8n_config, probe_n8n
        url = str((data or {}).get('url') or '').strip()
        key = str((data or {}).get('api_key') or '').strip()
        if not url:
            send_json({'ok': False, 'error': 'url required'}, 400)
            return True
        try:
            result = save_n8n_config(url=url, api_key=key)
        except ValueError as exc:
            send_json({'ok': False, 'error': str(exc)}, 400)
            return True
        report = probe_n8n()
        send_json({**result, 'ok': True, 'detail': report.detail, 'discovery': report.discovery})
        return True
    if path == '/api/expansion/integrations/configure':
        from expansion.capabilities.integrations_setup import configure_integration
        which = str((data or {}).get('component') or (data or {}).get('which') or '').strip()
        send_json(configure_integration(
            which,
            token=str((data or {}).get('token') or (data or {}).get('bot_token') or ''),
            url=str((data or {}).get('url') or ''),
            guild_id=str((data or {}).get('guild_id') or ''),
        ))
        return True
    if path == '/api/expansion/video-studio/config':
        from expansion.capabilities.comfy_sidecar import save_studio_endpoint
        endpoint = str(
            (data or {}).get('endpoint')
            or (data or {}).get('comfyui_url')
            or ''
        ).strip()
        if not endpoint:
            send_json({'ok': False, 'error': 'endpoint required'}, 400)
            return True
        try:
            send_json(save_studio_endpoint(endpoint))
        except ValueError as exc:
            send_json({'ok': False, 'error': str(exc)}, 400)
        return True
    if path == '/api/expansion/video-studio/start':
        # Back-compat: Start now means full orchestrated Setup.
        from expansion.capabilities.studio_setup import start_studio_setup
        send_json(start_studio_setup(
            force=bool((data or {}).get('force')),
            proceed_anyway=bool((data or {}).get('proceed_anyway') or (data or {}).get('acknowledge_under_spec')),
        ))
        return True
    if path == '/api/expansion/video-studio/setup':
        from expansion.capabilities.studio_setup import start_studio_setup
        send_json(start_studio_setup(
            force=bool((data or {}).get('force')),
            proceed_anyway=bool((data or {}).get('proceed_anyway') or (data or {}).get('acknowledge_under_spec')),
        ))
        return True
    if path == '/api/expansion/creative/packs/install':
        from expansion.capabilities.studio_packs import start_pack_install
        from expansion.capabilities.studio_setup import studio_hardware_snapshot
        which = (data or {}).get('which') or (data or {}).get('packs')
        if isinstance(which, str):
            which = [which]
        if which is not None and not isinstance(which, list):
            which = None
        send_json(start_pack_install(
            force=bool((data or {}).get('force')),
            which=which,
            hw=studio_hardware_snapshot(),
        ))
        return True
    if path == '/api/expansion/creative/generate':
        from expansion.capabilities.comfy_submit import (
            ensure_creative_poller,
            fail_stale_fake_creative_jobs,
            public_creative_job,
            submit_image_job,
        )
        from expansion.capabilities.video_studio import probe_video_studio
        from expansion.events import new_event
        from expansion.jobs import JobStatus, JobStore
        from expansion.pipeline import LivingPipeline

        ensure_creative_poller()
        fail_stale_fake_creative_jobs()

        modality = str((data or {}).get('modality') or 'image').strip().lower()
        if modality not in ('image', 'video', 'music', 'script'):
            modality = 'image'
        prompt = str((data or {}).get('prompt') or (data or {}).get('request') or '').strip()
        if not prompt:
            send_json({'ok': False, 'queued': False, 'error': 'prompt required'}, 400)
            return True
        engine = str((data or {}).get('engine') or '').strip()
        negative = str((data or {}).get('negative') or '').strip()
        tuning = (data or {}).get('tuning') or {}
        vs = probe_video_studio()
        endpoint = ((vs.discovery or {}).get('endpoint') or 'http://127.0.0.1:8188')

        submitted = None
        if modality == 'image':
            submitted = submit_image_job(
                prompt=prompt,
                negative=negative,
                tuning=tuning if isinstance(tuning, dict) else {},
                endpoint=endpoint,
            )
        elif modality == 'video':
            from expansion.capabilities.comfy_submit import submit_video_job
            submitted = submit_video_job(
                prompt=prompt,
                negative=negative,
                tuning=tuning if isinstance(tuning, dict) else {},
                endpoint=endpoint,
            )
        elif modality == 'music':
            from expansion.capabilities.comfy_submit import submit_music_job
            tun = tuning if isinstance(tuning, dict) else {}
            submitted = submit_music_job(
                tags=prompt,
                lyrics=str(tun.get('lyrics') or ''),
                duration_sec=float(tun.get('duration') or 60),
                bpm=tun.get('bpm'),
                tuning=tun,
                endpoint=endpoint,
            )
        else:
            send_json({
                'ok': False,
                'queued': False,
                'error': 'modality_not_supported',
                'detail': f'{modality.title()} generate is not wired on this surface yet.',
                'modality': modality,
                'studio_state': vs.state,
                'endpoint': endpoint,
            }, 501)
            return True
        if not submitted.get('ok') or not submitted.get('prompt_id'):
            status = int(submitted.get('http_status') or 409)
            payload = {
                'ok': False,
                'queued': False,
                'soft_block': bool(submitted.get('soft_block', True)),
                'action': submitted.get('action') or 'install_packs',
                'error': submitted.get('error') or 'creative_packs_needed',
                'detail': submitted.get('detail') or (
                    'Creative packs are not installed yet. Tap Install packs — '
                    'Generate stays quiet until packs are ready.'
                ),
                'missing': submitted.get('missing') or [],
                'packs': submitted.get('packs') or {},
                'needed': submitted.get('needed') or [],
                'modality': modality,
                'engine': engine or 'z-image-turbo',
                'studio_state': submitted.get('studio_state') or vs.state,
                'endpoint': submitted.get('endpoint') or endpoint,
            }
            send_json(payload, status)
            return True

        prompt_id = str(submitted['prompt_id'])
        _engine_default = {
            'image': 'z-image-turbo',
            'video': 'wan-2.2-5b',
            'music': 'ace-step-1.5',
        }.get(modality) or modality
        request = (
            f'[Muse Studio · {modality}'
            + f' · {engine or _engine_default}'
            + f'] {prompt}'
        )
        if negative:
            request += f' | negative: {negative[:240]}'
        pipe = LivingPipeline()
        job = pipe.jobs.create(
            request,
            domain='creative',
            assigned_agent='muse',
        )
        created = new_event(
            'job.created', actor='aria', subject='muse',
            payload={
                'job_id': job.job_id,
                'domain': 'creative',
                'request': request,
                'comfy_prompt_id': prompt_id,
            },
        )
        pipe.apply_event(created, write_diary=False)
        pipe.jobs.transition(job.job_id, JobStatus.ASSIGNED.value, event_id=created.event_id)
        pipe.jobs.transition(
            job.job_id,
            JobStatus.RUNNING.value,
            evidence=[f'comfy:prompt_id={prompt_id}', f'comfy:endpoint={endpoint}'],
            event_id=created.event_id,
        )
        job = pipe.jobs.get(job.job_id)
        try:
            from expansion.capabilities.workshop_api import sync_expansion_job_to_workshop
            sync_expansion_job_to_workshop(job)
        except Exception:
            pass
        pub = public_creative_job(job) if job else None
        send_json({
            'ok': True,
            'queued': True,
            'modality': modality,
            'engine': engine or 'z-image-turbo',
            'prompt_id': prompt_id,
            'endpoint': endpoint,
            'job': pub,
            'job_id': job.job_id if job else None,
            'output_proxy': (pub or {}).get('output_proxy') or '',
            'message': submitted.get('message') or f'Submitted to ComfyUI · prompt_id={prompt_id}',
        })
        return True
    if path == '/api/expansion/jobs/create':
        from expansion.pipeline import LivingPipeline
        pipe = LivingPipeline()
        # Production default: queue real work. Simulated COMPLETE/FAILED only when
        # the caller explicitly opts in (tests / qualify harness).
        simulate = bool(data.get('simulate', False))
        succeed = data.get('succeed')
        if succeed is not None:
            succeed = bool(succeed)
        out = pipe.create_and_run_job(
            data.get('request') or 'untitled job',
            domain=data.get('domain') or 'coordination',
            succeed=succeed,
            result_text=data.get('result') or '',
            error=data.get('error') or '',
            simulate=simulate,
            queue_only=bool(data.get('queue_only', False)),
        )
        job = out.get('job')
        send_json({
            'ok': True,
            'queued': bool(out.get('queued')),
            'simulated': bool(out.get('simulated')),
            'job': asdict(job) if job else None,
            'event_id': out.get('event_id'),
            'journal_ids': out.get('journal_ids'),
            'diary_ids': out.get('diary_ids'),
        })
        return True
    if path == '/api/expansion/event':
        from expansion.events import new_event
        from expansion.pipeline import LivingPipeline
        ev = new_event(
            data.get('event_type') or 'agent.message',
            actor=data.get('actor') or 'user',
            subject=data.get('subject') or '',
            payload=data.get('payload') or {},
        )
        out = LivingPipeline().apply_event(ev)
        send_json({'ok': True, **{k: out[k] for k in out if k != 'job'}})
        return True
    if path == '/api/expansion/pages/register':
        from expansion.rooms import RoomPage, RoomRegistry, ROOM_SCHEMA_VERSION
        page = RoomPage(
            schema_version=ROOM_SCHEMA_VERSION,
            page_id=data.get('page_id') or '',
            name=data.get('name') or '',
            route=data.get('route') or '',
            owner_agent=data.get('owner_agent') or 'aria',
            icon=data.get('icon') or 'PG',
            description=data.get('description') or '',
            required_capabilities=tuple(data.get('required_capabilities') or ()),
            permissions=tuple(data.get('permissions') or ()),
            health_source=data.get('health_source') or '',
            enabled=bool(data.get('enabled', True)),
            shared=bool(data.get('shared', False)),
            kind='page_builder',
        )
        try:
            RoomRegistry().seed_defaults()
            registered = RoomRegistry().register_page(page)
            send_json({'ok': True, 'page': asdict(registered)})
        except ValueError as exc:
            send_json({'error': {'code': 'PAGE_REJECTED', 'message': str(exc)}}, 400)
        return True
    if path == '/api/expansion/rex/transition':
        from dataclasses import asdict as _asdict
        from expansion.entitlement import EntitlementGate
        from expansion.rex import transition_rex_job
        if not EntitlementGate().expansion_surfaces_allowed():
            send_json({'enabled': False, 'message': 'Expansion not entitled'}, 403)
            return True
        job_id = (data.get('job_id') or '').strip()
        new_status = (data.get('status') or data.get('stage') or '').strip()
        note = (data.get('note') or '').strip()
        actor = (data.get('actor') or 'aria').strip() or 'aria'
        assign_to = (data.get('assign_to') or '').strip() or None
        if not job_id or not new_status:
            send_json({'error': {'code': 'REX_BAD_REQUEST', 'message': 'job_id and status/stage required'}}, 400)
            return True
        try:
            from expansion.rex import advance_stage
            if data.get('stage') or new_status in (
                'BACKLOG', 'READY', 'RESEARCHING', 'PLANNING', 'ASSIGNED',
                'IN_PROGRESS', 'VERIFYING', 'REWORK', 'DONE', 'HARD_BLOCKED', 'CANCELLED',
            ):
                job = advance_stage(
                    job_id, new_status, actor=actor, note=note, assign_to=assign_to,
                )
            else:
                job = transition_rex_job(job_id, new_status, note=note, actor=actor)
            send_json({'ok': True, 'job': _asdict(job)})
        except KeyError:
            send_json({'error': {'code': 'REX_NOT_FOUND', 'message': f'unknown job {job_id}'}}, 404)
        except PermissionError as exc:
            send_json({'error': {'code': 'REX_POLICY_DENIED', 'message': str(exc)}}, 403)
        except ValueError as exc:
            send_json({'error': {'code': 'REX_INVALID_TRANSITION', 'message': str(exc)}}, 400)
        return True
    if path == '/api/expansion/rex/queue':
        from dataclasses import asdict as _asdict
        from expansion.entitlement import EntitlementGate
        from expansion.rex import queue_rex_job
        if not EntitlementGate().expansion_surfaces_allowed():
            send_json({'enabled': False, 'message': 'Expansion not entitled'}, 403)
            return True
        request = (data.get('request') or '').strip()
        if not request:
            send_json({'error': {'code': 'REX_BAD_REQUEST', 'message': 'request required'}}, 400)
            return True
        try:
            job = queue_rex_job(
                request,
                domain=(data.get('domain') or 'coordination').strip() or 'coordination',
                assigned_agent=(data.get('assigned_agent') or None) or None,
                discovered_by=(data.get('discovered_by') or data.get('actor') or '') or '',
                stage=(data.get('stage') or 'BACKLOG'),
                priority=int(data.get('priority') or 5),
                coordination_plan=list(data.get('coordination_plan') or []),
            )
            send_json({'ok': True, 'job': _asdict(job)})
        except ValueError as exc:
            send_json({'error': {'code': 'REX_QUEUE_REJECTED', 'message': str(exc)}}, 400)
        return True
    if path == '/api/expansion/rex/discover':
        from dataclasses import asdict as _asdict
        from expansion.entitlement import EntitlementGate
        from expansion.rex import discover_work
        if not EntitlementGate().expansion_surfaces_allowed():
            send_json({'enabled': False, 'message': 'Expansion not entitled'}, 403)
            return True
        actor = (data.get('actor') or '').strip()
        request = (data.get('request') or '').strip()
        if not actor or not request:
            send_json({'error': {'code': 'REX_BAD_REQUEST', 'message': 'actor and request required'}}, 400)
            return True
        try:
            job = discover_work(
                actor, request,
                domain=(data.get('domain') or ''),
                priority=int(data.get('priority') or 5),
                assigned_agent=(data.get('assigned_agent') or None) or None,
            )
            send_json({'ok': True, 'job': _asdict(job)})
        except PermissionError as exc:
            send_json({'error': {'code': 'REX_POLICY_DENIED', 'message': str(exc)}}, 403)
        except ValueError as exc:
            send_json({'error': {'code': 'REX_DISCOVER_REJECTED', 'message': str(exc)}}, 400)
        return True
    if path == '/api/expansion/rex/plan':
        from expansion.entitlement import EntitlementGate
        from expansion.rex import set_coordination_plan
        if not EntitlementGate().expansion_surfaces_allowed():
            send_json({'enabled': False, 'message': 'Expansion not entitled'}, 403)
            return True
        job_id = (data.get('job_id') or '').strip()
        actor = (data.get('actor') or 'aria').strip() or 'aria'
        plan = list(data.get('plan') or data.get('coordination_plan') or [])
        if not job_id or not plan:
            send_json({'error': {'code': 'REX_BAD_REQUEST', 'message': 'job_id and plan required'}}, 400)
            return True
        try:
            item = set_coordination_plan(job_id, plan, actor=actor)
            send_json({'ok': True, 'item': item})
        except PermissionError as exc:
            send_json({'error': {'code': 'REX_POLICY_DENIED', 'message': str(exc)}}, 403)
        return True
    if path == '/api/expansion/rex/peer-review':
        from expansion.entitlement import EntitlementGate
        from expansion.rex import add_peer_review
        if not EntitlementGate().expansion_surfaces_allowed():
            send_json({'enabled': False, 'message': 'Expansion not entitled'}, 403)
            return True
        job_id = (data.get('job_id') or '').strip()
        reviewer = (data.get('reviewer') or data.get('actor') or '').strip()
        verdict = (data.get('verdict') or '').strip()
        if not job_id or not reviewer or verdict not in ('pass', 'fail', 'abstain'):
            send_json({
                'error': {
                    'code': 'REX_BAD_REQUEST',
                    'message': 'job_id, reviewer, verdict(pass|fail|abstain) required',
                }
            }, 400)
            return True
        try:
            item = add_peer_review(
                job_id, reviewer=reviewer, verdict=verdict,
                note=(data.get('note') or ''),
            )
            send_json({'ok': True, 'item': item})
        except PermissionError as exc:
            send_json({'error': {'code': 'REX_POLICY_DENIED', 'message': str(exc)}}, 403)
        return True
    if path == '/api/expansion/policy/check':
        from dataclasses import asdict as _asdict
        from expansion.policy import PolicyEngine
        decision = PolicyEngine().check(
            (data.get('agent_id') or data.get('actor') or '').strip(),
            (data.get('capability') or '').strip(),
        )
        send_json({'ok': True, 'decision': _asdict(decision)})
        return True
    if path == '/api/expansion/rex/tick':
        from expansion.entitlement import EntitlementGate
        from expansion.autonomy_loop import autonomy_tick
        if not EntitlementGate().expansion_surfaces_allowed():
            send_json({'enabled': False, 'message': 'Expansion not entitled'}, 403)
            return True
        try:
            out = autonomy_tick(
                max_jobs=int(data.get('max_jobs') or 5),
                detect=bool(data.get('detect', True)),
            )
            send_json(out)
        except Exception as exc:
            send_json({'error': {'code': 'AUTONOMY_TICK_FAILED', 'message': str(exc)}}, 500)
        return True
    if path == '/api/expansion/route-learning/ingest':
        from expansion.entitlement import EntitlementGate
        from expansion.route_learning import ingest_keeproute_exchange
        if not EntitlementGate().expansion_surfaces_allowed():
            send_json({'enabled': False, 'message': 'Expansion not entitled'}, 403)
            return True
        out = ingest_keeproute_exchange(
            prompt=(data.get('prompt') or '').strip(),
            response=(data.get('response') or data.get('reply') or '').strip(),
            agent=(data.get('agent') or '').strip(),
            model=(data.get('model') or '').strip(),
            source=(data.get('source') or 'keeproute').strip(),
            mission_id=(data.get('mission_id') or '').strip(),
            success=bool(data.get('success', True)),
            error=(data.get('error') or '').strip(),
            classification=(data.get('classification') or '').strip(),
            paid_or_local=(data.get('paid_or_local') or '').strip(),
            extra=data.get('extra') if isinstance(data.get('extra'), dict) else None,
        )
        code = 200 if out.get('ok') else 400
        send_json(out, code)
        return True
    if path == '/api/expansion/tools/invoke':
        from dataclasses import asdict as _asdict
        from expansion.entitlement import EntitlementGate
        from expansion.tools import ToolGateway
        if not EntitlementGate().expansion_surfaces_allowed():
            send_json({'enabled': False, 'message': 'Expansion not entitled'}, 403)
            return True
        agent_id = (data.get('agent_id') or data.get('actor') or '').strip()
        capability = (data.get('capability') or '').strip()
        if not agent_id or not capability:
            send_json({'error': {'code': 'TOOL_BAD_REQUEST', 'message': 'agent_id and capability required'}}, 400)
            return True
        kwargs = dict(data.get('args') or {})
        for k in ('query', 'q', 'url', 'path', 'content', 'command', 'cmd', 'unit', 'container', 'name', 'action', 'message'):
            if k in data and k not in kwargs:
                kwargs[k] = data[k]
        result = ToolGateway().invoke(agent_id, capability, **kwargs)
        send_json({'ok': result.ok, 'result': _asdict(result)}, 200 if result.ok else 403)
        return True
    # Learning mutations — runtime/tests only (protected). UI is read-only + WHY.
    if path == '/api/expansion/learning/observe':
        from dataclasses import asdict as _asdict
        from expansion.entitlement import EntitlementGate
        from expansion.learning import LearningEngine
        if not EntitlementGate().expansion_surfaces_allowed():
            send_json({'enabled': False, 'message': 'Expansion not entitled'}, 403)
            return True
        try:
            obs = LearningEngine().observe(
                (data.get('agent_id') or '').strip(),
                (data.get('text') or '').strip(),
                learning_type=(data.get('learning_type') or 'owner_preference').strip(),
                evidence_ids=list(data.get('evidence_ids') or []),
                scope=(data.get('scope') or 'private').strip(),
                actor=(data.get('actor') or data.get('agent_id') or '').strip(),
            )
            send_json({'ok': True, 'observation': _asdict(obs)})
        except PermissionError as exc:
            send_json({'error': {'code': 'LEARN_POLICY', 'message': str(exc)}}, 403)
        except ValueError as exc:
            send_json({'error': {'code': 'LEARN_BAD', 'message': str(exc)}}, 400)
        return True
    if path == '/api/expansion/learning/reinforce':
        from dataclasses import asdict as _asdict
        from expansion.entitlement import EntitlementGate
        from expansion.learning import LearningEngine
        if not EntitlementGate().expansion_surfaces_allowed():
            send_json({'enabled': False, 'message': 'Expansion not entitled'}, 403)
            return True
        try:
            claim = LearningEngine().reinforce(
                (data.get('claim_id') or '').strip(),
                (data.get('evidence_id') or '').strip(),
                actor=(data.get('actor') or 'ledger').strip(),
            )
            send_json({'ok': True, 'claim': _asdict(claim)})
        except PermissionError as exc:
            send_json({'error': {'code': 'LEARN_POLICY', 'message': str(exc)}}, 403)
        except KeyError:
            send_json({'error': {'code': 'LEARN_NOT_FOUND', 'message': 'claim not found'}}, 404)
        return True
    if path == '/api/expansion/learning/contradict':
        from dataclasses import asdict as _asdict
        from expansion.entitlement import EntitlementGate
        from expansion.learning import LearningEngine
        if not EntitlementGate().expansion_surfaces_allowed():
            send_json({'enabled': False, 'message': 'Expansion not entitled'}, 403)
            return True
        try:
            claim = LearningEngine().contradict(
                (data.get('claim_id') or '').strip(),
                (data.get('evidence_id') or '').strip(),
                actor=(data.get('actor') or 'ledger').strip(),
            )
            send_json({'ok': True, 'claim': _asdict(claim)})
        except PermissionError as exc:
            send_json({'error': {'code': 'LEARN_POLICY', 'message': str(exc)}}, 403)
        except KeyError:
            send_json({'error': {'code': 'LEARN_NOT_FOUND', 'message': 'claim not found'}}, 404)
        return True
    if path == '/api/expansion/learning/revise':
        from dataclasses import asdict as _asdict
        from expansion.entitlement import EntitlementGate
        from expansion.learning import LearningEngine
        if not EntitlementGate().expansion_surfaces_allowed():
            send_json({'enabled': False, 'message': 'Expansion not entitled'}, 403)
            return True
        try:
            claim = LearningEngine().revise(
                (data.get('claim_id') or '').strip(),
                (data.get('claim') or data.get('new_claim') or '').strip(),
                actor=(data.get('actor') or 'ledger').strip(),
                evidence_id=(data.get('evidence_id') or '').strip(),
            )
            send_json({'ok': True, 'claim': _asdict(claim)})
        except PermissionError as exc:
            send_json({'error': {'code': 'LEARN_POLICY', 'message': str(exc)}}, 403)
        except KeyError:
            send_json({'error': {'code': 'LEARN_NOT_FOUND', 'message': 'claim not found'}}, 404)
        except ValueError as exc:
            send_json({'error': {'code': 'LEARN_BAD', 'message': str(exc)}}, 400)
        return True
    return False
