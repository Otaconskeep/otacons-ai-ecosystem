from core.router import resolve
from core.providers import OllamaProvider, ProviderError
from core.voice import synthesize_voice, TTSError, public_result


def system_prompt(agent):
    # Expansion runtime may supply a full context-assembled prompt.
    if agent.get('system_prompt'):
        return agent['system_prompt']
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
    try:
        text = provider.generate(model, system_prompt(agent) + '\n' + context + '\nUser: ' + message)
    except ProviderError as e:
        raise RuntimeError(str(e)) from e
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
