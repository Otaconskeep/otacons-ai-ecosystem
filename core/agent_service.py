from core.router import resolve
from core.providers import OllamaProvider, ProviderError
from core.voice import synthesize_voice, TTSError, public_result


def _human_agent_id(agent) -> str:
    """Map Core wizard ids (agent_001 + display Aria) onto Expansion human sheets."""
    aid = (agent.get('id') or '').strip().lower()
    if aid in ('aria', 'vector', 'ledger', 'muse', 'sentry'):
        return aid
    name = (agent.get('display_name') or '').strip().lower()
    if name in ('aria', 'vector', 'ledger', 'muse', 'sentry'):
        return name
    return aid


def system_prompt(agent):
    # Expansion runtime may supply a full context-assembled prompt.
    if agent.get('system_prompt'):
        return agent['system_prompt']
    try:
        from expansion.humanization import core_fallback_persona
        human = core_fallback_persona(
            _human_agent_id(agent),
            agent.get('display_name') or '',
        )
        if human:
            return human
    except Exception:
        pass
    return f"You are {agent['display_name']}, a local AI assistant. Be friendly, clear, and helpful."


def chat(deployment, agent, message, conversation_id='default', provider=None, memory=None, user_id='local_user'):
    assignment = resolve(deployment, 'conversational_llm')
    provider = provider or OllamaProvider(assignment.endpoint)
    requested = assignment.model
    model_note = None
    # Prefer a model that is actually installed. Stale wizard configs often point
    # at qwen2.5:1.5b after a false-negative GPU scan even when 7b was pulled.
    if hasattr(provider, 'resolve_model'):
        try:
            model, model_note = provider.resolve_model(requested)
        except ProviderError as e:
            raise RuntimeError(str(e)) from e
    else:
        health = provider.health(requested)
        if health.state != 'ONLINE':
            raise RuntimeError(health.detail)
        model = requested
    context = ''
    if memory:
        prior = memory.messages(conversation_id)
        facts = memory.retrieve(user_id, agent['id'], message)
        context = '\n'.join(f"{x['role']}: {x['content']}" for x in prior[-10:])
        context += '\nRelevant memory: ' + '; '.join(x['content'] for x in facts)

    human_id = _human_agent_id(agent)

    # Chat-turn learning when Expansion is on and the HTTP layer hasn't already run it
    learning_owned_here = bool(agent.get('expansion')) and agent.get('_chat_learning') is None
    pre = agent.get('_chat_learning')
    if learning_owned_here:
        try:
            from expansion.chat_learning import before_reply
            from expansion.state_layout import resolve_layout
            pre = before_reply(human_id, message, layout=resolve_layout())
            agent['_chat_learning'] = pre
        except Exception:
            pre = None
            learning_owned_here = False

    # Deterministic dossier answers for past/taste/self — never a list dump
    text = None
    if pre and pre.get('intercept') and pre.get('reply'):
        text = pre['reply']
    else:
        try:
            from expansion.humanization import (
                render_dossier_self_reply,
                is_self_state_query,
                spoken_self_state,
            )
            text = render_dossier_self_reply(human_id, message)
            if text is None and is_self_state_query(message):
                dims = {}
                exp = agent.get('_expansion_context') or {}
                emo = exp.get('emotion') or {}
                dims = emo.get('dimensions') or {}
                if dims:
                    text = spoken_self_state(dims, agent_id=human_id)
        except Exception:
            text = None

        if text is None:
            try:
                text = provider.generate(model, system_prompt(agent) + '\n' + context + '\nUser: ' + message)
            except ProviderError as e:
                raise RuntimeError(str(e)) from e

    # Idiolect post-pass — scrub embodiment / corporate closers / briefing loops
    try:
        from expansion.idiolect import apply_idiolect
        text = apply_idiolect(text, human_id)
    except Exception:
        pass
    # Hermes personality runtime — final scrub + layered fallback if thin
    try:
        from expansion.hermes.personality_runtime import (
            apply_final_persona_safety_scrub,
            render_persona_text_via_hermes,
        )
        rendered = render_persona_text_via_hermes(
            human_id, message, candidate_text=text,
        )
        intent = (rendered or {}).get('intent_class') or 'general'
        if len((text or '').split()) >= 25:
            scrubbed = apply_final_persona_safety_scrub(text, human_id, intent)
            if scrubbed:
                text = scrubbed
            elif rendered.get('text'):
                text = rendered['text']
        elif rendered.get('ok') and rendered.get('text'):
            text = rendered['text']
    except Exception:
        pass
    try:
        from expansion.behavior_spine import scrub_robotic_delivery, wants_work_deliverable
        text = scrub_robotic_delivery(text)
        if wants_work_deliverable(message) and text and len(text.split()) < 25:
            text = (
                text.rstrip('.')
                + ". Here is a first-pass plan: (1) clarify the deliverable, "
                "(2) list tools and constraints you already named, "
                "(3) draft three options, (4) pick one and ship a draft today. "
                "Tell me which slice you want next and I will go deeper."
            )
            text = scrub_robotic_delivery(text)
    except Exception:
        pass

    if learning_owned_here and pre is not None:
        try:
            from expansion.chat_learning import after_reply
            from expansion.state_layout import resolve_layout
            after_reply(
                human_id, message, text,
                layout=resolve_layout(),
                event_id=(pre or {}).get('event_id') or '',
                intent=(pre or {}).get('intent') or 'chat',
            )
        except Exception:
            pass

    if memory:
        memory.append(conversation_id, user_id, agent['id'], 'user', message)
        memory.append(conversation_id, user_id, agent['id'], 'assistant', text)
    out = {
        'conversation_id': conversation_id,
        'agent_id': agent['id'],
        'text': text,
        'service_id': assignment.service_id,
        'model': model,
        'model_requested': requested,
    }
    if model_note:
        out['model_note'] = model_note
    if pre:
        out['learning'] = {
            'intent': pre.get('intent'),
            'event_id': pre.get('event_id'),
            'learning_observation_id': pre.get('learning_observation_id'),
            'intercept': bool(pre.get('intercept')),
        }
    return out


def chat_with_optional_speech(
    deployment,
    agent,
    message,
    conversation_id='default',
    provider=None,
    memory=None,
    user_id='local_user',
    *,
    auto_speak: bool = False,
    tts_provider=None,
):
    """Chat always succeeds on text; TTS failures are reported separately."""
    result = chat(
        deployment, agent, message, conversation_id,
        provider=provider, memory=memory, user_id=user_id,
    )
    result['voice'] = None
    if not auto_speak:
        return result
    try:
        speech = synthesize_voice(
            deployment, agent, result['text'],
            provider=tts_provider, purpose='production',
        )
        result['voice'] = public_result(speech, include_audio_b64=True)
    except TTSError as e:
        result['voice'] = {
            'status': 'error',
            'code': e.code,
            'message': 'Voice playback unavailable',
            'technical': e.as_dict(),
        }
    except Exception as e:
        result['voice'] = {
            'status': 'error',
            'code': 'SYNTHESIS_FAILED',
            'message': 'Voice playback unavailable',
            'technical': {'message': str(e)},
        }
    return result
