from core.router import resolve
from core.providers import OllamaProvider
from core.voice import synthesize_voice, TTSError, public_result


def system_prompt(agent):
    return f"You are {agent['display_name']}, a local AI assistant. Be friendly, clear, and helpful."


def chat(deployment, agent, message, conversation_id='default', provider=None, memory=None, user_id='local_user'):
    assignment = resolve(deployment, 'conversational_llm')
    provider = provider or OllamaProvider(assignment.endpoint)
    health = provider.health(assignment.model)
    if health.state != 'ONLINE':
        raise RuntimeError(health.detail)
    context = ''
    if memory:
        prior = memory.messages(conversation_id)
        facts = memory.retrieve(user_id, agent['id'], message)
        context = '\n'.join(f"{x['role']}: {x['content']}" for x in prior[-10:])
        context += '\nRelevant memory: ' + '; '.join(x['content'] for x in facts)
    text = provider.generate(assignment.model, system_prompt(agent) + '\n' + context + '\nUser: ' + message)
    if memory:
        memory.append(conversation_id, user_id, agent['id'], 'user', message)
        memory.append(conversation_id, user_id, agent['id'], 'assistant', text)
    return {
        'conversation_id': conversation_id,
        'agent_id': agent['id'],
        'text': text,
        'service_id': assignment.service_id,
        'model': assignment.model,
    }


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
