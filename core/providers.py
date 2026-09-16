import json, urllib.request, urllib.error
from dataclasses import dataclass

class ProviderError(RuntimeError): pass
@dataclass
class Health: state:str; detail:str=''
class LLMProvider:
 def resource_requirements(self, model): return {}
 def health(self, model): raise NotImplementedError
 def generate(self, model, prompt): raise NotImplementedError
class OllamaProvider(LLMProvider):
 def __init__(self, endpoint='http://127.0.0.1:11434', timeout=120): self.endpoint=endpoint.rstrip('/'); self.timeout=timeout
 def list_models(self):
  req=urllib.request.Request(self.endpoint+'/api/tags')
  with urllib.request.urlopen(req,timeout=5) as r: data=json.loads(r.read())
  return [x.get('name') for x in data.get('models',[]) if x.get('name')]
 @staticmethod
 def _model_ready(names, model):
  if not model: return False
  if model in names: return True
  # Accept "qwen2.5:1.5b" when tags list "qwen2.5:1.5b-..." or bare name match
  base = model.split(':', 1)[0]
  for n in names:
    if n == model or n.startswith(model + '-') or n.startswith(model + '_'):
      return True
    if n.split(':', 1)[0] == base and (model in n or n.startswith(base + ':')):
      # Prefer exact tag when model includes one
      if ':' in model:
        if n == model or n.startswith(model):
          return True
      else:
        return True
  return False
 @classmethod
 def _match_installed(cls, names, model):
  """Return the installed tag that satisfies model, or None."""
  if not model or not names:
    return None
  if model in names:
    return model
  for n in names:
    if n.startswith(model + '-') or n.startswith(model + '_'):
      return n
  if ':' in model:
    for n in names:
      if n.startswith(model):
        return n
  else:
    base = model.split(':', 1)[0]
    for n in names:
      if n.split(':', 1)[0] == base:
        return n
  return None
 @staticmethod
 def _prefer_fallback(names):
  """When the configured model is missing, pick the best already-pulled chat model."""
  if not names:
    return None
  ranked = []
  for n in names:
    score = 0
    low = n.lower()
    if 'qwen2.5' in low or low.startswith('qwen'):
      score += 100
    for tag, pts in (('14b', 40), ('7b', 30), ('3b', 20), ('1.5b', 10), ('0.5b', 5)):
      if tag in low:
        score += pts
        break
    if 'embed' in low or 'whisper' in low:
      score -= 1000
    ranked.append((score, n))
  ranked.sort(reverse=True)
  return ranked[0][1] if ranked and ranked[0][0] >= 0 else names[0]
 def resolve_model(self, requested):
  """Return (usable_tag, note). note is None when requested is ready as-is."""
  try:
    names = self.list_models()
  except Exception as e:
    raise ProviderError(f'Ollama connection failed while listing models: {type(e).__name__}') from e
  if not names:
    raise ProviderError(
      'Ollama is running but has no models pulled. '
      'Re-run OtaconsKeep Setup (Default Model), or: ollama pull qwen2.5:7b'
    )
  matched = self._match_installed(names, requested)
  if matched:
    return matched, None
  fallback = self._prefer_fallback(names)
  note = (
    f'Configured model {requested!r} is not installed; using {fallback!r} instead. '
    f'Installed: {", ".join(names[:8])}{"…" if len(names)>8 else ""}'
  )
  return fallback, note
 def health(self, model):
  try:
   names=self.list_models()
   ready=self._model_ready(names, model)
   return Health('ONLINE' if ready else 'DEGRADED','model ready' if ready else 'runtime reachable; model missing')
  except Exception as e: return Health('OFFLINE',f'runtime unreachable: {type(e).__name__}')
 def generate(self, model, prompt):
  try:
   req=urllib.request.Request(self.endpoint+'/api/generate',data=json.dumps({'model':model,'prompt':prompt,'stream':False}).encode(),headers={'Content-Type':'application/json'})
   with urllib.request.urlopen(req,timeout=self.timeout) as r: data=json.loads(r.read())
   if not isinstance(data.get('response'),str) or not data['response'].strip(): raise ProviderError('malformed Ollama response')
   return data['response'].strip()
  except urllib.error.URLError as e: raise ProviderError(f'Ollama connection failed: {e.reason}') from e
  except (TimeoutError, TimeoutError): raise ProviderError('Ollama request timed out')
  except json.JSONDecodeError as e: raise ProviderError('malformed Ollama JSON response') from e
class TestProvider(LLMProvider):
 def health(self, model): return Health('ONLINE','deterministic test provider')
 def list_models(self): return ['test']
 def resolve_model(self, requested): return requested or 'test', None
 def generate(self, model, prompt):
  name='Assistant'
  for line in prompt.splitlines():
   if line.startswith('You are '): name=line.split('You are ',1)[1].split(',',1)[0]
  if 'what is your name' in prompt.lower(): return f'My name is {name}.'
  if "dog's name" in prompt.lower() and 'cooper' in prompt.lower(): return "Your dog's name is Cooper."
  return f'{name} received your message.'
