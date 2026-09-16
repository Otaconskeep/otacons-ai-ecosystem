let state={
  step:0,scan:null,name:'Aria',features:['chat','memory','voice'],config:null,storage:null,
  conversation:null,voiceId:'voice_aria',autoSpeak:false,voices:[],capabilities:null,
  currentAudio:null,speakingMsg:null,recorder:null,recordingState:'MIC_READY',
  testMode:window.__OTACON_TEST_MODE__===true,codecMode:'idle',codecBooted:false,lastModel:null,
  view:'codec',agentId:'agent_001',roster:[],expansion:null
};
const labels=['Welcome','System Scan','Hardware Recommendation','Storage','Agent Setup','Features','Review','Finish'];
const CODEC_VIDEOS={idle:'/assets/aria/aria-idle.mp4',thinking:'/assets/aria/aria-thinking.mp4',talking:'/assets/aria/aria-talking.mp4'};

function currentAgentId(){ return state.agentId || 'agent_001'; }
function currentAgentName(){
  const r=(state.roster||[]).find(a=>a.id===state.agentId||a.agent_id===state.agentId);
  if(r) return r.display_name||r.id;
  return state.name||'Aria';
}
async function loadExpansion(){
  try{
    state.expansion=await apiGet('/api/expansion/status');
    if(state.expansion&&state.expansion.enabled&&(state.expansion.agents||[]).length){
      state.roster=state.expansion.agents.map(a=>({
        id:a.id||a.agent_id, display_name:a.display_name, role:a.role,
        voice_id:a.voice_id, room:a.room||a.room_route
      }));
      if(!state.roster.find(a=>a.id===state.agentId)){
        state.agentId=state.roster[0].id;
        state.name=state.roster[0].display_name;
        if(state.roster[0].voice_id) state.voiceId=state.roster[0].voice_id;
      }
    } else {
      state.roster=[];
    }
  }catch(e){ state.expansion=null; state.roster=[]; }
}

async function api(path,body){
  let r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body||{})});
  return {ok:r.ok,status:r.status,data:await r.json()};
}
async function apiGet(path){return (await fetch(path)).json()}

async function loadPrefs(){
  try{let p=await apiGet('/api/preferences'); state.autoSpeak=!!p.auto_speak}catch(e){state.autoSpeak=false}
}
async function loadVoices(){
  try{let v=await apiGet('/api/voices'); state.voices=v.voices||[]}catch(e){state.voices=[]}
}
async function loadCapabilities(){
  try{state.capabilities=await apiGet('/api/capabilities')}catch(e){state.capabilities=null}
}
function capStatus(key){
  let c=state.capabilities; if(!c) return 'unknown';
  return c[key]||'not_configured';
}
function capReady(key){
  if(!state.capabilities) return key==='chat'||key==='tts';
  return capStatus(key)==='ready';
}
function capAnnotate(key, readyLabel, fallback){
  let s=capStatus(key);
  if(s==='ready') return readyLabel||'READY';
  if(s==='unknown') return fallback||'STATUS UNKNOWN';
  return String(s).replace(/_/g,' ').toUpperCase();
}
function escapeHtml(s){return String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
function voiceLabel(id){
  let v=(state.voices||[]).find(x=>x.id===id); return v?v.display_name:id;
}
function appRoot(){return document.getElementById('app')}
function setBodyMode(mode){
  document.body.classList.toggle('home-body', mode==='home');
}

function formatNow(){
  try{
    return new Date().toLocaleString(undefined,{dateStyle:'long',timeStyle:'short',hour12:true});
  }catch(e){ return new Date().toISOString(); }
}

function resourceBarsHtml(scan){
  const h=(scan&&scan.hardware&&scan.hardware.hardware)||{};
  const ram=Number(h.ram_gb||0);
  const free=Number(h.free_storage_gb||0);
  // Lite scan has no live CPU%, so show capacity markers honestly.
  const gpu=Array.isArray(h.gpus)&&h.gpus[0]?h.gpus[0]:null;
  const rows=[
    ['CPU', h.cpu&&h.cpu.cores?`${h.cpu.cores} cores`:'—', h.cpu&&h.cpu.cores?Math.min(100,h.cpu.cores*8):0],
    ['RAM', ram?`${ram} GB`:'—', ram?Math.min(100, Math.round((ram/64)*100)):0],
    ['DISK', free?`${Math.round(free)} GB free`:'—', free?Math.min(100, Math.round((free/1000)*100)):0],
  ];
  if(gpu) rows.push(['GPU', `${gpu.vram_gb} GB`, Math.min(100, Math.round((gpu.vram_gb/24)*100))]);
  return rows.map(([k,v,pct])=>`<div class="home-res-item"><div class="lbl"><span>${k}</span><span>${escapeHtml(String(v))}</span></div><div class="home-res-bar"><i style="width:${pct}%"></i></div></div>`).join('');
}

async function showHome(){
  state.view='home';
  setBodyMode('home');
  await loadCapabilities();
  await loadExpansion();
  let scan=null;
  try{scan=await apiGet('/api/scan')}catch(e){}
  const chatOk=capReady('chat'), ttsOk=capReady('tts'), sttOk=capReady('stt');
  const vtOk=capStatus('voice_trainer')==='ready';
  const model=(state.capabilities&&state.capabilities.llm_model)||'—';
  const gpuDet=((scan&&scan.hardware&&scan.hardware.hardware&&scan.hardware.hardware.gpu_detection)||{});
  const expOn=!!(state.expansion&&state.expansion.enabled);
  const expReady=!!(state.expansion&&state.expansion.foundation_ready);
  const expAgents=(state.roster||[]).map(a=>a.display_name).join(' · ')||'—';
  const sem=((state.expansion&&state.expansion.report&&state.expansion.report.semantic)||{});
  const emotionOk=sem.emotion_engine==='READY';
  const relOk=sem.relationship_store==='READY';

  const expansionSection=expOn?`
  <section class="home-group">
    <h2 class="home-group-title">Keep Expansion</h2>
    <div class="home-grid">
      <button type="button" class="svc" onclick="showChat()">
        <div class="svc-top"><div class="svc-ico">XP</div><div class="svc-name">Expansion Roster</div></div>
        <p class="svc-desc">${escapeHtml(expAgents)}</p>
        <span class="svc-pill ${expReady?'ok':'warn'}">${expReady?'FOUNDATION READY':'PARTIAL'}</span>
      </button>
      <button type="button" class="svc" onclick="showExpansionSurface('command')">
        <div class="svc-top"><div class="svc-ico">CMD</div><div class="svc-name">Aria Command</div></div>
        <p class="svc-desc">Roster, delegations, readiness, relationship shifts — coordination floor.</p>
        <span class="svc-pill ok">ARIA</span>
      </button>
      <button type="button" class="svc" onclick="showExpansionSurface('war-room')">
        <div class="svc-top"><div class="svc-ico">WR</div><div class="svc-name">War Room</div></div>
        <p class="svc-desc">Active jobs, failures, decision queue — Vector ops / Aria command.</p>
        <span class="svc-pill ok">JOBS</span>
      </button>
      <button type="button" class="svc" onclick="showExpansionSurface('intel')">
        <div class="svc-top"><div class="svc-ico">INT</div><div class="svc-name">Intel / Continuity</div></div>
        <p class="svc-desc">Memories, journals, living dossiers, relationship evidence — Ledger.</p>
        <span class="svc-pill ok">LEDGER</span>
      </button>
      <button type="button" class="svc" onclick="showExpansionSurface('creative')">
        <div class="svc-top"><div class="svc-ico">CRE</div><div class="svc-name">Creative Studio</div></div>
        <p class="svc-desc">Creative queue and Studio readiness shell — Muse (heavy Studio later).</p>
        <span class="svc-pill ok">MUSE</span>
      </button>
      <button type="button" class="svc" onclick="showExpansionSurface('ops')">
        <div class="svc-top"><div class="svc-ico">OPS</div><div class="svc-name">Operations</div></div>
        <p class="svc-desc">Alerts, security jobs, HA optional — Sentry.</p>
        <span class="svc-pill ok">SENTRY</span>
      </button>
      <button type="button" class="svc" onclick="showExpansionSurface('reports')">
        <div class="svc-top"><div class="svc-ico">RPT</div><div class="svc-name">Agent Reports</div></div>
        <p class="svc-desc">Emotion, jobs, journal, diary, living observations with provenance.</p>
        <span class="svc-pill ok">LIVE STATE</span>
      </button>
      <button type="button" class="svc" onclick="showExpansionSurface('rooms')">
        <div class="svc-top"><div class="svc-ico">RM</div><div class="svc-name">Rooms / Pages</div></div>
        <p class="svc-desc">Command, Intel, Creative, Ops + allowlisted Page Builder registry.</p>
        <span class="svc-pill ok">REGISTRY</span>
      </button>
      <button type="button" class="svc" onclick="showExpansionSurface('relationships')">
        <div class="svc-top"><div class="svc-ico">REL</div><div class="svc-name">Relationships</div></div>
        <p class="svc-desc">Directional matrix with WHY provenance — not a single unexplained score.</p>
        <span class="svc-pill ${relOk?'ok':'warn'}">${relOk?'READY':'NOT READY'}</span>
      </button>
      <button type="button" class="svc" onclick="showExpansionSurface('emotion')">
        <div class="svc-top"><div class="svc-ico">EM</div><div class="svc-name">Emotion</div></div>
        <p class="svc-desc">Real EmotionStore dimensions with clickable WHY.</p>
        <span class="svc-pill ${emotionOk?'ok':'warn'}">${emotionOk?'READY':'NOT READY'}</span>
      </button>
      <button type="button" class="svc" onclick="showChat()">
        <div class="svc-top"><div class="svc-ico">CX</div><div class="svc-name">Multi-Agent Codec</div></div>
        <p class="svc-desc">Select Aria, Vector, Ledger, Muse, or Sentry in Codec.</p>
        <span class="svc-pill ok">ROSTER-AWARE</span>
      </button>
    </div>
  </section>`:'';

  appRoot().innerHTML=`<div class="home">
  <header class="home-header">
    <div>
      <p class="home-kicker">Otaconskeep · Lite · build c30c1d2</p>
      <h1 class="home-greeting">Otacon Command Center</h1>
    </div>
    <div class="home-meta">
      <div class="home-res">${resourceBarsHtml(scan)}</div>
      <div class="home-datetime" id="homeClock">${escapeHtml(formatNow())}</div>
    </div>
  </header>

  <section class="home-group">
    <h2 class="home-group-title">Command Center</h2>
    <div class="home-grid">
      <button type="button" class="svc" onclick="showChat()">
        <div class="svc-top"><div class="svc-ico">CC</div><div class="svc-name">Codec</div></div>
        <p class="svc-desc">${expOn?'Talk to the Expansion roster — dual-port Codec, local Ollama, Piper voice.':'Talk to Aria — dual-port Codec, local Ollama, Piper voice.'}</p>
        <span class="svc-pill ${chatOk?'ok':'warn'}">${chatOk?'ONLINE':'CHAT DOWN'}</span>
      </button>
      <button type="button" class="svc" onclick="render()">
        <div class="svc-top"><div class="svc-ico">SU</div><div class="svc-name">Setup</div></div>
        <p class="svc-desc">Hardware scan, agent voice, features, and first-run configuration.</p>
        <span class="svc-pill">WIZARD</span>
      </button>
      <button type="button" class="svc" onclick="showChat()">
        <div class="svc-top"><div class="svc-ico">MEM</div><div class="svc-name">Memory</div></div>
        <p class="svc-desc">Persistent facts agents keep across conversations (inside Codec).</p>
        <span class="svc-pill ok">LOCAL SQLITE</span>
      </button>
      <button type="button" class="svc" onclick="showChat()">
        <div class="svc-top"><div class="svc-ico">VOX</div><div class="svc-name">Voice</div></div>
        <p class="svc-desc">Piper TTS preview and Auto Speak — Warm Male / Measured Female / Aria.</p>
        <span class="svc-pill ${ttsOk?'ok':'warn'}">${ttsOk?'TTS READY':'TTS NOT READY'}</span>
      </button>
    </div>
  </section>

  ${expansionSection}

  <section class="home-group">
    <h2 class="home-group-title">System</h2>
    <div class="home-grid">
      <button type="button" class="svc" onclick="showHome()">
        <div class="svc-top"><div class="svc-ico">SYS</div><div class="svc-name">Status</div></div>
        <p class="svc-desc">Model ${escapeHtml(String(model))} · STT ${sttOk?'ready':'off'} · GPU ${escapeHtml(gpuDet.status||'unknown')}${expOn?' · Expansion on':''}</p>
        <span class="svc-pill ${chatOk&&ttsOk?'ok':'warn'}">${chatOk&&ttsOk?'HEALTHY':'CHECK SERVICES'}</span>
      </button>
      <button type="button" class="svc ${vtOk?'':'svc-off'}" ${vtOk?'onclick="showHome()"':'disabled'}>
        <div class="svc-top"><div class="svc-ico">VT</div><div class="svc-name">Voice Trainer</div></div>
        <p class="svc-desc">${vtOk?'Genome Voice Trainer is installed under ~/otacon-voice-trainer (GPU Piper).':'Not installed — Setup adds it when NVIDIA is detected.'}</p>
        <span class="svc-pill ${vtOk?'ok':'warn'}">${vtOk?'INSTALLED':'NOT INSTALLED'}</span>
      </button>
      <button type="button" class="svc svc-off" disabled>
        <div class="svc-top"><div class="svc-ico">IMG</div><div class="svc-name">Images / Video</div></div>
        <p class="svc-desc">Not configured in Lite. Providers are architecture-only until you add them.</p>
        <span class="svc-pill warn">NOT CONFIGURED</span>
      </button>
      <button type="button" class="svc svc-off" disabled>
        <div class="svc-top"><div class="svc-ico">NODES</div><div class="svc-name">Compute Nodes</div></div>
        <p class="svc-desc">Remote pairing is Keep-direction — this Lite box is the local node.</p>
        <span class="svc-pill warn">LOCAL ONLY</span>
      </button>
    </div>
  </section>

  <p class="home-foot">Otaconskeep Lite · Designed &amp; Engineered by Antonio G. Garcia · discord.gg/cZDeqECzX</p>
</div>`;

  if(window.__homeClock) clearInterval(window.__homeClock);
  window.__homeClock=setInterval(()=>{
    const el=document.getElementById('homeClock'); if(el) el.textContent=formatNow();
  },1000);

  // One-shot boot splash matching Homelab HUD
  if(!document.getElementById('ot-boot') && !sessionStorage.getItem('ot_boot_done')){
    const boot=document.createElement('div');
    boot.id='ot-boot';
    boot.innerHTML=`<div class="frame"><div class="kicker">Otaconskeep</div><div class="title">Command Center</div><div class="sub">Booting local Lite deck…</div></div>`;
    document.body.appendChild(boot);
    setTimeout(()=>{ boot.classList.add('done'); sessionStorage.setItem('ot_boot_done','1'); setTimeout(()=>boot.remove(),700); },900);
  }
}

/* ---------------- Setup wizard ---------------- */
function renderProgress(){
  const bar=document.getElementById('progress');
  if(!bar) return;
  const s=state.step;
  const segs=labels.map((_,i)=>`<span class="step-seg${i<s?' done':''}${i===s?' active':''}"></span>`).join('');
  bar.innerHTML=`<div class=steps>${segs}</div><div class=step-label><span>Step ${s+1} of ${labels.length}</span><span class=current>${labels[s]}</span></div>`;
}

function featuresHtml(){
  const rows=[
    ['chat','Chat','chat','SUPPORTED'],
    ['memory','Memory',null,'SUPPORTED'],
    ['voice','Voice Output','tts','SUPPORTED'],
    ['speech_to_text','Speech Input','stt','REQUIRES PROVIDER'],
    ['web_search','Web Search',null,'COMING LATER'],
  ];
  return rows.map(([f,label,capKey,fallback])=>{
    const coming=f==='web_search';
    const ready=!capKey||capReady(capKey);
    const status=capKey?capAnnotate(capKey,fallback,fallback):(coming?'COMING LATER':fallback);
    const disabled=coming||(!!capKey&&!ready);
    const checked=state.features.includes(f)&&!disabled;
    return `<label class="${disabled?'cap-off':''}"><input type=checkbox value=${f} ${checked?'checked':''} ${disabled?'disabled':''}> ${label} <span class=muted>— ${status}</span></label>`;
  }).join('');
}

function agentSetupHtml(){
  let opts=(state.voices||[]).map(v=>`<option value="${v.id}" ${v.id===state.voiceId?'selected':''}>${v.display_name}${v.fixture?' (test)':''}</option>`).join('');
  return `<div class="setup-avatar-row">
  <img id=setupAvatar class=setup-avatar alt="Agent portrait" src="/assets/aria/aria.webp">
  <div>
    <label>Agent name<br><input id=name value="${state.name||'Aria'}"></label>
    <label>Voice<br><select id=voiceSelect onchange="updateSetupAvatar()">${opts||'<option value="voice_aria">Aria</option>'}</select></label>
    <button type=button onclick="previewSelectedVoice()">Preview</button>
    <p class=muted id=previewStatus></p>
  </div>
</div>
<label>Role<br><input value="Primary Assistant" disabled></label>
<button onclick="setName()">Continue</button>`;
}
function updateSetupAvatar(){
  const sel=document.getElementById('voiceSelect'); const vid=sel?sel.value:state.voiceId;
  const av=document.getElementById('setupAvatar'); if(!av) return;
  if(vid==='voice_aria'){ av.src='/assets/aria/aria.webp'; av.hidden=false; } else { av.hidden=true; }
}

function render(){
  state.view='setup';
  setBodyMode('setup');
  const root=appRoot();
  root.innerHTML=`<div class="setup-shell">
    <div class="setup-top">
      <div class="setup-brand">Otaconskeep · Core</div>
      <div>
        <button type=button class="cc-btn ghost" onclick="showHome()">Home</button>
        <button type=button class="cc-btn" onclick="showChat()">Open Codec</button>
      </div>
    </div>
    <p class="muted" style="letter-spacing:.14em;text-transform:uppercase;font-size:10px;margin:0 0 8px">Local AI Setup</p>
    <h1 id="title">${labels[state.step]}</h1>
    <p id="tag" class="muted">Local AI Command System</p>
    <div id="progress"></div>
    <section id="page"></section>
    <p class="muted" style="margin-top:28px;font-size:10px;letter-spacing:.08em;text-align:center">Otaconskeep · Designed &amp; Engineered by Antonio G. Garcia</p>
  </div>`;
  const page=document.getElementById('page');
  renderProgress();
  let s=state.step;
  if(s===0) page.innerHTML='<p class=muted>This wizard configures your local AI system. No Docker or YAML knowledge is required.</p><button onclick="next()">Get Started</button><button onclick="showChat()">Open Codec</button>';
  if(s===1) page.innerHTML='<p class=muted>Detect your computer, GPUs, storage, and available capacity.</p><button onclick="scan()">Scan My System</button>';
  if(s===2){let h=state.scan.hardware.hardware,g=state.scan.hardware.gpu_roles; page.innerHTML=`<div class=card>System: ${h.os}<br>CPU: ${h.cpu.model} (${h.cpu.cores} cores)<br>Memory: ${h.ram_gb} GB</div>`+(h.gpus.length?h.gpus.map(x=>`<div class=card>${x.model} — ${x.vram_gb} GB VRAM — ${x.capability}</div>`).join(''):'<div class=card>CPU fallback (no GPU detected)</div>')+`<p class=muted>Recommended primary: ${g.primary_gpu}</p><button onclick="next()">Use Recommended Setup</button>`;}
  if(s===3){let v=state.scan.storage.find(x=>x.recommended)||state.scan.storage[0]||{}; page.innerHTML=`<div class=card><b>Recommended storage</b><br>${v.path||'Unavailable'}<br>${v.free_gb||0} GB free</div><button onclick="next()">Use Recommended Storage</button>`;}
  if(s===4){ page.innerHTML=agentSetupHtml(); updateSetupAvatar(); }
  if(s===5) page.innerHTML=featuresHtml()+'<button onclick="setFeatures()">Continue</button>';
  if(s===6) page.innerHTML=`<div class=card>Agent: ${state.name}<br>Voice: ${voiceLabel(state.voiceId)}<br>Features: ${state.features.join(', ')}<br>Storage: ${(state.scan.storage.find(x=>x.recommended)||state.scan.storage[0]||{}).path||'Unavailable'}</div><button onclick="build()">Create Configuration</button>`;
  if(s===7) page.innerHTML=`<p>${state.name} is configured.</p><p class=muted>Open Codec to talk — portrait stays in the right port, messages are text-only below.</p><div class=card>${state.config?.saved||''}</div><button onclick="showChat()">Open Codec</button>`;
}

function next(){state.step++;render()}
async function scan(){state.scan=await apiGet('/api/scan');state.storage=state.scan.storage.find(x=>x.recommended)||state.scan.storage[0];state.step=2;render()}
async function setName(){
  state.name=document.getElementById('name').value.trim()||'Aria';
  let sel=document.getElementById('voiceSelect'); if(sel) state.voiceId=sel.value;
  await api('/api/agent/voice',{agent_id:'agent_001',display_name:state.name,voice_id:state.voiceId});
  next();
}
function setFeatures(){state.features=[...document.querySelectorAll('#page input[type=checkbox]:checked')].map(x=>x.value);next()}
async function build(){
  let p=await api('/api/plan',{name:state.name,features:state.features,storage:state.storage,voice_id:state.voiceId});
  let cfg=p.data.config; if(cfg.agents&&cfg.agents[0]){ cfg.agents[0].voice_id=state.voiceId; cfg.agents[0].display_name=state.name; cfg.agents[0].avatar='/assets/aria/aria.webp'; }
  let s=await api('/api/save',{config:cfg}); state.config={saved:s.data.path}; next();
}

/* ---------------- Voice preview / playback ---------------- */
async function previewSelectedVoice(){
  let sel=document.getElementById('voiceSelect'); state.voiceId=sel?sel.value:state.voiceId;
  let st=document.getElementById('previewStatus'); if(st) st.textContent='Synthesizing…';
  await runVoicePreview({statusEl:st});
}
async function previewSelectedVoiceChat(){
  let st=document.getElementById('sidePreviewStatus');
  await runVoicePreview({statusEl:st});
}
async function runVoicePreview({statusEl}={}){
  const agentName=state.name||'Aria';
  const voiceId=state.voiceId;
  const text=`Hello, I am ${agentName}.`;
  try{
    let r=await api('/api/preview_voice',{agent:{id:'agent_001',display_name:agentName,voice_id:voiceId},text});
    if(!r.ok||r.data.status==='error'||!r.data.audio_base64){
      const reason=(r.data&&(r.data.reason||r.data.message))||'Voice preview unavailable';
      const msg='VOICE PREVIEW FAILED\n'+reason;
      if(statusEl) statusEl.textContent=msg; else alert(msg);
      return false;
    }
    const bytes=Math.floor((r.data.audio_base64.length*3)/4);
    const dur=Number(r.data.duration_sec||0);
    if(!r.data.audio_base64||bytes<4000||dur>0&&dur<0.35){
      const msg='VOICE PREVIEW FAILED\nReturned audio is too short or empty to be spoken speech.';
      if(statusEl) statusEl.textContent=msg; else alert(msg);
      return false;
    }
    if(statusEl) statusEl.textContent='Playing preview…';
    await playAudioAsync(r.data.audio_base64);
    if(statusEl) statusEl.textContent='Preview played';
    return true;
  }catch(err){
    const msg='VOICE PREVIEW FAILED\n'+(err&&err.message?err.message:String(err));
    if(statusEl) statusEl.textContent=msg; else alert(msg);
    return false;
  }
}

function setCodecMode(mode){
  const v=document.getElementById('codecVideo');
  const port=document.getElementById('port-active');
  state.codecMode=mode;
  if(port) port.classList.toggle('codec-talking', mode==='talking');
  if(!v) return;
  const src=CODEC_VIDEOS[mode]||CODEC_VIDEOS.idle;
  if(!v.currentSrc||!v.currentSrc.endsWith(src)){ v.src=src; }
  v.play().catch(()=>{});
  const badge=document.getElementById('codecStatus');
  if(badge) badge.textContent=mode.toUpperCase();
  const lbl=document.getElementById('active-ai-label');
  if(lbl) lbl.textContent=mode==='idle'?'STANDBY':(state.name||'ARIA').toUpperCase();
}

function playAudioAsync(b64, msgId){
  return new Promise((resolve,reject)=>{
    stopAudio();
    let a=new Audio('data:audio/wav;base64,'+b64);
    state.currentAudio=a;
    setCodecMode('talking');
    if(msgId!=null){
      state.speakingMsg=msgId;
      let b=document.querySelector(`[data-speak-btn="${msgId}"]`);
      if(b){b.textContent='■'; b.dataset.state='playing'}
    }
    a.onended=()=>{ stopAudio(); resolve(true); };
    a.onerror=()=>{ stopAudio(); reject(new Error('browser could not decode/play WAV audio')); };
    a.play().then(()=>{}).catch(err=>{
      if(msgId!=null){ let e=document.querySelector(`[data-speak-err="${msgId}"]`); if(e) e.textContent='Voice playback unavailable';}
      stopAudio();
      reject(err||new Error('HTMLAudioElement.play() failed'));
    });
  });
}
function playAudio(b64, msgId){ playAudioAsync(b64, msgId).catch(()=>{}); }
function stopAudio(){
  if(state.currentAudio){try{state.currentAudio.pause(); state.currentAudio.currentTime=0}catch(e){} state.currentAudio=null}
  if(state.speakingMsg!=null){
    let b=document.querySelector(`[data-speak-btn="${state.speakingMsg}"]`);
    if(b){b.textContent='▶'; b.dataset.state='idle'}
    state.speakingMsg=null;
  }
  setCodecMode('idle');
}

async function toggleSpeak(msgId, text){
  let b=document.querySelector(`[data-speak-btn="${msgId}"]`);
  if(!b) return;
  if(b.dataset.state==='playing'){ stopAudio(); return }
  if(b.dataset.state==='waiting') return;
  b.dataset.state='waiting'; b.textContent='…';
  let err=document.querySelector(`[data-speak-err="${msgId}"]`); if(err) err.textContent='';
  let r=await api('/api/synthesize_agent_speech',{agent:{id:'agent_001',display_name:state.name,voice_id:state.voiceId},text});
  if(!r.ok||r.data.status==='error'||!r.data.audio_base64){
    b.dataset.state='idle'; b.textContent='▶';
    if(err) err.textContent='Voice playback unavailable';
    return;
  }
  b.dataset.audio=r.data.audio_base64;
  playAudio(r.data.audio_base64, msgId);
}

function messageHtml(role, content, msgId){
  if(role!=='assistant' && role!==state.name){
    return `<div class="msg-row-user"><div class="msg-user">${escapeHtml(content)}</div></div>`;
  }
  return `<div class="msg-row-bot" data-msg="${msgId}">
    <div class="msg-bot">
      <div class="msg-bot-name">${escapeHtml(state.name||'Aria')}</div>
      <div>${escapeHtml(content)}</div>
      <button type=button class=speak data-speak-btn="${msgId}" data-state=idle onclick='toggleSpeak(${msgId}, ${JSON.stringify(content)})' title="Play voice">▶</button>
      <span class=muted data-speak-err="${msgId}"></span>
    </div>
  </div>`;
}

function bootCodecOnce(){
  if(state.codecBooted) return;
  state.codecBooted=true;
  const el=document.createElement('div');
  el.className='codec-boot';
  el.innerHTML=`<div class=codec-boot-line>OTACON // CODEC</div><div class="codec-boot-line muted">ESTABLISHING LOCAL LINK…</div>`;
  document.body.appendChild(el);
  setTimeout(()=>{ el.classList.add('codec-boot-out'); setTimeout(()=>el.remove(),400); },900);
}

function animateFreq(){
  const el=document.getElementById('codec-freq');
  if(!el) return;
  const base=140.85;
  el.textContent=(base+(Math.random()*0.08-0.04)).toFixed(2);
}

/* ---------------- Codec cockpit (primary UI) ---------------- */
async function showChat(){
  state.view='codec';
  setBodyMode('codec');
  await loadPrefs(); await loadVoices(); await loadCapabilities(); await loadExpansion();
  let scan=null;
  try{scan=await apiGet('/api/scan')}catch(e){}
  const aid=currentAgentId();
  let cs=(await api('/api/conversations',{agent_id:aid})).data;
  state.conversation=(cs[0]||{}).id||(await api('/api/conversation',{agent_id:aid})).data.id;

  const ttsOk=capReady('tts'), chatOk=capReady('chat'), sttOk=capReady('stt');
  const model=(state.capabilities&&state.capabilities.llm_model)||state.lastModel||'—';
  const gpus=((scan&&scan.hardware&&scan.hardware.hardware&&scan.hardware.hardware.gpus)||[]);
  const gpuLine=gpus.length?gpus.map(g=>`${g.model} · ${g.vram_gb} GB`).join(' / '):'No GPU reported';
  const vtOk=capStatus('voice_trainer')==='ready';
  const voiceOpts=(state.voices||[]).map(v=>`<option value="${v.id}" ${v.id===state.voiceId?'selected':''}>${v.display_name}</option>`).join('');
  const roster=state.roster&&state.roster.length?state.roster:[{id:aid,display_name:currentAgentName()}];
  const agentBtns=roster.map(a=>{
    const id=a.id||a.agent_id;
    const active=id===aid?' codec-ai-active':'';
    return `<button type=button class="codec-ai-btn${active}" title="${escapeHtml(a.display_name||id)}" onclick="selectExpansionAgent('${escapeHtml(id)}')">${escapeHtml(String(a.display_name||id).toUpperCase())}</button>`;
  }).join('');
  const agentName=currentAgentName();
  const portraitAgent=(roster.find(a=>(a.id||a.agent_id)===aid)||{}).id||'aria';
  const idleSrc=`/assets/${portraitAgent}/${portraitAgent}-idle.mp4`;

  appRoot().innerHTML=`<div class="codec-cockpit">
  <header class="cc-mast">
    <div>
      <h1>Otacon // Codec</h1>
      <div class="cc-sub">${state.roster.length?'Expansion roster · voice · status':'Local Lite cockpit · voice · agent · status — not the full Keep'}</div>
      <div class="cc-greeble">
        <span>LINK LOCAL</span>
        <span>CHAT ${chatOk?'READY':'DOWN'}</span>
        <span>TTS ${ttsOk?'READY':'DOWN'}</span>
        <span>MODEL ${escapeHtml(String(model))}</span>
        <span>AGENT ${escapeHtml(String(agentName).toUpperCase())}</span>
      </div>
    </div>
    <div class="cc-mast-actions">
      <button type=button class="cc-btn ghost" onclick="showHome()">Home</button>
      <button type=button class="cc-btn ghost" onclick="render()">Setup</button>
      <button type=button class="cc-btn" onclick="newConversation()">New Thread</button>
    </div>
  </header>

  <div class="cc-layout">
    <div id="codec-room-body">
      <div id="codec-wrap">
        <div id="codec-bar">OTACON CODEC · ${state.roster.length?'EXPANSION':'LITE'} · TRANSMISSION LOCAL · GHOST PASTEL HUD</div>
        <div id="codec-header">
          <div class="codec-inner code-border-inner">
            <div class="codec-port port-left" id="port-xof">
              <div class="op-port-fill"><span>Operator</span></div>
              <div class="codec-port-crt"></div>
              <div class="codec-port-lbl">YOU</div>
            </div>
            <div class="codec-mid">
              <div class="codec-title">CODEC</div>
              <div class="codec-freq-line">FREQ&nbsp;<span id="codec-freq">140.85</span>&nbsp;MHz</div>
              <div class="codec-sigs">
                <div class="codec-sig-b" style="height:40%"></div>
                <div class="codec-sig-b" style="height:70%"></div>
                <div class="codec-sig-b" style="height:100%"></div>
                <div class="codec-sig-b" style="height:60%"></div>
                <div class="codec-sig-b" style="height:80%"></div>
              </div>
              <div class="codec-ai-btns">
                ${agentBtns}
              </div>
            </div>
            <div class="codec-port port-right" id="port-active">
              <video id=codecVideo autoplay loop muted playsinline src="${idleSrc}" onerror="this.src='/assets/aria/aria-idle.mp4'"></video>
              <div class="codec-port-crt"></div>
              <div class="codec-port-lbl" id="active-ai-label">STANDBY</div>
            </div>
          </div>
        </div>
        <div id="chat-msgs"></div>
        <div id="input-row">
          <span id="input-prompt">&gt;</span>
          <input id="chat-inp" type="text" placeholder="Transmit message…" autocomplete="off" onkeydown="if(event.key==='Enter')sendChat()">
          <button type=button id="micButton" ${sttOk?'':'disabled'} onclick="toggleRecording()" title="${sttOk?'Record':'Speech input not ready'}">MIC</button>
          <button type=button id="send-btn" onclick="sendChat()">TRANSMIT</button>
        </div>
      </div>
    </div>

    <aside class="cc-side">
      <div class="cc-panel">
        <h2>Link status</h2>
        <div class="cc-kv">
          <span class=muted>CHAT</span><b class="${chatOk?'cc-ok':'cc-warn'}">${chatOk?'READY':'UNAVAILABLE'}</b>
          <span class=muted>VOICE</span><b class="${ttsOk?'cc-ok':'cc-warn'}">${ttsOk?'READY':'NOT READY'}</b>
          <span class=muted>MODEL</span><b id=codecModel>${escapeHtml(String(model))}</b>
          <span class=muted>GPU</span><b>${escapeHtml(gpuLine)}</b>
          <span class=muted>STATE</span><b id=codecStatus>IDLE</b>
        </div>
      </div>
      <div class="cc-panel">
        <h2>Voice</h2>
        <label class=muted style="display:block;margin-bottom:6px;font-size:10px;letter-spacing:.1em">PROFILE
          <select id=chatVoice onchange="assignVoice(this.value)" style="width:100%;margin-top:6px;background:#050406;border:1px solid rgba(151,159,236,.25);color:var(--mf-text);padding:8px;font:inherit">${voiceOpts}</select>
        </label>
        <label class=muted style="display:flex;gap:8px;align-items:center;font-size:10px;letter-spacing:.08em;margin:10px 0">
          <input type=checkbox id=autoSpeak ${state.autoSpeak?'checked':''} onchange="setAutoSpeak(this.checked)"> AUTO SPEAK
        </label>
        <button type=button class="cc-btn" onclick="previewSelectedVoiceChat()">Preview</button>
        <p class=muted id=sidePreviewStatus style="font-size:10px;margin-top:8px;white-space:pre-wrap"></p>
      </div>
      <div class="cc-panel">
        <h2>Threads</h2>
        <div id=conversation-list></div>
        <div class="cc-links"><button type=button class="cc-btn" onclick="newConversation()">New Thread</button></div>
      </div>
      <div class="cc-panel" id=memory-panel>
        <h2>Memory</h2>
        <p class=muted style="font-size:10px;margin:0 0 8px">Facts ${escapeHtml(agentName)} keeps for later.</p>
        <div id=memories></div>
        <input id=memory placeholder="Add a memory">
        <button type=button class="cc-btn" onclick="addMemory()" style="margin-top:8px">Save Memory</button>
      </div>
      <div class="cc-panel">
        <h2>Voice Trainer</h2>
        <p class=muted style="font-size:10px;margin:0">${vtOk?'Installed on this machine (GPU Piper). Open ~/otacon-voice-trainer in WSL — not a Codec chat feature.':'Not installed. Setup installs it when NVIDIA is detected.'}</p>
      </div>
      <div class="cc-panel">
        <h2>How to run</h2>
        <ol>
          <li><strong>Transmit</strong> — chat hits local Ollama, then Piper TTS if Auto Speak is on.</li>
          <li><strong>Portrait</strong> stays in the right port — never in chat rows.</li>
          <li><strong>Setup</strong> for hardware scan / first-run config.</li>
        </ol>
      </div>
    </aside>
  </div>
</div>`;

  await refreshConversationList();
  await openConversation(state.conversation);
  await loadMemories();
  setCodecMode('idle');
  bootCodecOnce();
  if(window.__codecFreqTimer) clearInterval(window.__codecFreqTimer);
  window.__codecFreqTimer=setInterval(animateFreq,900);
  const inp=document.getElementById('chat-inp'); if(inp) inp.focus();
}

async function selectExpansionAgent(id){
  if(!id||id===state.agentId) return;
  state.agentId=id;
  const r=(state.roster||[]).find(a=>(a.id||a.agent_id)===id);
  if(r){
    state.name=r.display_name||id;
    if(r.voice_id) state.voiceId=r.voice_id;
  }
  state.codecBooted=false;
  await showChat();
}

async function assignVoice(vid){
  state.voiceId=vid;
  await api('/api/agent/voice',{agent_id:currentAgentId(),display_name:currentAgentName(),voice_id:vid});
}
async function setAutoSpeak(on){
  state.autoSpeak=!!on;
  await api('/api/preferences',{auto_speak:state.autoSpeak});
}

async function refreshConversationList(){
  let cs=(await api('/api/conversations',{agent_id:currentAgentId()})).data||[];
  let el=document.getElementById('conversation-list');
  if(el){
    el.innerHTML=cs.map((c,i)=>{
      const active=c.id===state.conversation?' active':'';
      const title=escapeHtml(c.title||('Thread '+(i+1)));
      return `<button type=button class="conv-btn${active}" onclick="openConversation('${c.id}')">${title}</button>`;
    }).join('')||'<p class=muted style="font-size:10px">No threads yet.</p>';
  }
  return cs;
}
async function newConversation(){
  try{
    let r=await api('/api/conversation',{agent_id:currentAgentId(),title:'New conversation'});
    if(!r.ok||!r.data||!r.data.id){ alert('Could not create conversation'); return; }
    state.conversation=r.data.id;
    let box=document.getElementById('chat-msgs'); if(box) box.innerHTML='';
    await refreshConversationList();
    await openConversation(state.conversation);
  }catch(err){ alert(String(err&&err.message||err)); }
}
async function openConversation(id){
  state.conversation=id;
  let r=(await api('/api/conversation/get',{id,agent_id:currentAgentId()})).data;
  let box=document.getElementById('chat-msgs');
  if(!box) return;
  box.innerHTML='';
  (r.messages||[]).forEach((x,i)=>{ box.insertAdjacentHTML('beforeend', messageHtml(x.role,x.content,i)); });
  box.scrollTop=box.scrollHeight;
  await refreshConversationList();
}
async function loadMemories(){
  let r=(await api('/api/memories',{agent_id:currentAgentId()})).data;
  let e=document.getElementById('memories');
  if(e) e.innerHTML=(r||[]).map(x=>`<p>${escapeHtml(x.content)} <button type=button onclick="delMemory(${x.id})">Delete</button></p>`).join('')||'<p class=muted style="font-size:10px">None stored.</p>';
}
async function addMemory(){
  let e=document.getElementById('memory');
  if(e&&e.value.trim()) await api('/api/memory',{agent_id:currentAgentId(),content:e.value.trim()});
  if(e) e.value='';
  loadMemories();
}
async function delMemory(id){await api('/api/memory/delete',{agent_id:currentAgentId(),id});loadMemories()}

async function sendChat(){
  let el=document.getElementById('chat-inp'), box=document.getElementById('chat-msgs'), m=el&&el.value.trim();
  if(!m||!box) return;
  let uid=box.querySelectorAll('.msg-row-user,.msg-row-bot').length;
  box.insertAdjacentHTML('beforeend', `<div class="msg-row-user"><div class="msg-user">${escapeHtml(m)}</div></div><div class="msg-row-bot" id=wait><div class="msg-bot"><div class="typing-dots"><span></span><span></span><span></span></div></div></div>`);
  el.value='';
  box.scrollTop=box.scrollHeight;
  setCodecMode('thinking');
  let r=await api('/api/chat_with_agent',{
    agent:{id:currentAgentId(),display_name:currentAgentName(),voice_id:state.voiceId},
    message:m, conversation_id:state.conversation, auto_speak:state.autoSpeak
  });
  document.getElementById('wait')?.remove();
  if(!r.ok){
    const err=r.data&&r.data.error;
    const tech=(err&&(err.message||err.technical))||'Your AI service is unavailable.';
    box.insertAdjacentHTML('beforeend', `<div class="msg-row-bot"><div class="msg-bot"><div class="msg-bot-name">${escapeHtml(currentAgentName())}</div><div>${escapeHtml(tech)}</div></div></div>`);
    setCodecMode('idle');
    box.scrollTop=box.scrollHeight;
    return;
  }
  let d=r.data;
  if(d.model){ state.lastModel=d.model; const mEl=document.getElementById('codecModel'); if(mEl) mEl.textContent=d.model; }
  if(d.model_note){
    box.insertAdjacentHTML('beforeend', `<p class=muted style="font-size:10px">${escapeHtml(d.model_note)}</p>`);
  }
  let mid=uid+1;
  box.insertAdjacentHTML('beforeend', messageHtml('assistant', d.text, mid));
  box.scrollTop=box.scrollHeight;
  setCodecMode('idle');
  if(d.voice && d.voice.status==='error'){
    let err=document.querySelector(`[data-speak-err="${mid}"]`);
    if(err) err.textContent='Voice playback unavailable';
  } else if(state.autoSpeak && d.voice && d.voice.audio_base64){
    playAudio(d.voice.audio_base64, mid);
  }
}

async function toggleRecording(){
  if(!capReady('stt')) return;
  const button=document.getElementById('micButton');
  if(state.recorder && state.recorder.state==='recording'){ state.recorder.stop(); return; }
  if(!navigator.mediaDevices || !window.MediaRecorder){ return; }
  try {
    const stream=await navigator.mediaDevices.getUserMedia({audio:true});
    const chunks=[]; state.recorder=new MediaRecorder(stream); state.recordingState='RECORDING';
    button.dataset.state='recording'; button.textContent='STOP';
    state.recorder.ondataavailable=e=>{if(e.data.size) chunks.push(e.data)};
    state.recorder.onstop=async()=>{
      stream.getTracks().forEach(t=>t.stop()); button.textContent='MIC'; button.dataset.state='processing';
      try {
        const blob=new Blob(chunks,{type:state.recorder.mimeType||'audio/webm'}); const reader=new FileReader();
        reader.onload=async()=>{ const b64=String(reader.result).split(',')[1]||''; const r=await api('/api/transcribe_audio',{audio_base64:b64,test_mode:state.testMode});
          if(!r.ok || !r.data.text) throw new Error(r.data?.error?.message||'TRANSCRIPTION_FAILED');
          document.getElementById('chat-inp').value=r.data.text; button.dataset.state='ready';
        }; reader.readAsDataURL(blob);
      } catch(e){ button.dataset.state='error'; button.textContent='MIC'; }
    }; state.recorder.start();
  } catch(e){ button.dataset.state='error'; }
}

async function showNodes(){
  // Kept for welcome-step compatibility; Codec is primary.
  render();
}

async function showExpansionSurface(kind){
  state.view='expansion';
  setBodyMode('home');
  let body='';
  try{
    if(kind==='war-room'){
      const d=await apiGet('/api/expansion/war-room');
      const rows=(d.active||[]).concat(d.failed||[]).slice(0,30);
      body=`<h2>War Room</h2><p class=muted>Jobs/decisions — not infra telemetry.</p>`+
        (rows.map(j=>`<div class=card><b>${escapeHtml(j.job_id)}</b> · ${escapeHtml(j.status)} · ${escapeHtml(j.assigned_agent)}<br>${escapeHtml(j.request||'')}</div>`).join('')||'<p class=muted>No jobs yet.</p>');
    } else if(kind==='command'){
      const d=await apiGet('/api/expansion/command');
      body=`<h2>Aria Command Floor</h2><p class=muted>${escapeHtml(d.note||'')}</p>`+
        `<h3>Roster</h3>`+(d.roster||[]).map(a=>`<div class=card><b>${escapeHtml(a.display_name)}</b> · ${escapeHtml(a.role)}<pre style="font-size:11px">${escapeHtml(JSON.stringify(a.emotion_highlights||{}))}</pre></div>`).join('')+
        `<h3>Active jobs</h3>`+((d.active_jobs||[]).map(j=>`<div class=card>${escapeHtml(j.job_id)} → ${escapeHtml(j.assigned_agent)} · ${escapeHtml(j.status)}</div>`).join('')||'<p class=muted>None</p>');
    } else if(kind==='intel'){
      const d=await apiGet('/api/expansion/intel');
      body=`<h2>Intel / Continuity</h2><p class=muted>${escapeHtml(d.note||'')}</p>`+
        `<h3>JOURNAL timeline</h3>`+((d.journal_timeline||[]).slice(0,12).map(e=>`<div class=card><b>JOURNAL</b> ${escapeHtml(e.summary||'')}<br><span class=muted>${escapeHtml(e.agent_id)} · ${escapeHtml(e.event_type)}</span></div>`).join('')||'<p class=muted>Empty</p>')+
        `<h3>Important memories</h3>`+((d.important_memories||[]).slice(0,8).map(m=>`<div class=card>${escapeHtml(m.agent_id)}: ${escapeHtml(m.content||'')}</div>`).join('')||'<p class=muted>None</p>');
    } else if(kind==='creative'){
      const d=await apiGet('/api/expansion/creative');
      body=`<h2>Muse Creative Studio</h2><p class=muted>${escapeHtml(d.note||'')}</p>`+
        `<p>Video Studio: ${escapeHtml(d.video_studio_readiness||'unknown')}</p>`+
        ((d.recent_creative_jobs||[]).map(j=>`<div class=card>${escapeHtml(j.job_id)} · ${escapeHtml(j.status)} · ${escapeHtml(j.request||'')}</div>`).join('')||'<p class=muted>No creative jobs yet.</p>');
    } else if(kind==='ops'){
      const d=await apiGet('/api/expansion/ops');
      const ha=d.home_assistant||{};
      body=`<h2>Sentry Operations</h2>`+
        `<p class=muted>Home Assistant: ${escapeHtml(ha.status||'unknown')} — ${escapeHtml(ha.note||'')}</p>`+
        ((d.alerts||[]).map(j=>`<div class=card><b>ALERT</b> ${escapeHtml(j.job_id)} · ${escapeHtml(j.error||j.request||'')}</div>`).join('')||'<p class=muted>No failed security jobs.</p>');
    } else if(kind==='reports'){
      const d=await apiGet('/api/expansion/reports');
      body=`<h2>Agent Reports</h2>`+(d.reports||[]).map(r=>{
        const emo=Object.entries(r.emotion||{}).sort((a,b)=>b[1]-a[1]).slice(0,4).map(([k,v])=>`${k}=${v}`).join(', ');
        const j=(r.recent_journal||[])[0];
        const diary=r.latest_diary;
        return `<div class=card>
          <b>${escapeHtml(r.display_name)}</b> — ${escapeHtml(r.role)} · ${escapeHtml(r.archetype||'')}
          <p class=muted>Emotion: ${escapeHtml(emo||'—')}</p>
          <p class=muted>Jobs active: ${(r.active_jobs||[]).length} · success ${(r.metrics&&r.metrics.success_rate!=null)?(r.metrics.success_rate*100).toFixed(0)+'%':'n/a'}</p>
          <p><b>JOURNAL</b> ${escapeHtml((j&&j.summary)||'—')}</p>
          <p><b>DIARY</b> ${escapeHtml((diary&&diary.text)||'—')}</p>
          <button type=button class="cc-btn ghost" onclick="showEmotionWhy('${escapeHtml(r.agent_id)}','jealousy')">Emotion WHY</button>
          <button type=button class="cc-btn ghost" onclick="showRelWhy('${escapeHtml(r.agent_id)}','muse')">Rel → Muse WHY</button>
        </div>`;
      }).join('')||'<p class=muted>No reports.</p>';
    } else if(kind==='rooms'){
      const d=await apiGet('/api/expansion/rooms');
      body=`<h2>Room / Page Registry</h2>`+(d.rooms||[]).map(r=>
        `<div class=card><b>${escapeHtml(r.name)}</b> <span class=muted>${escapeHtml(r.route)}</span><br>Owner: ${escapeHtml(r.owner_agent)} · ${escapeHtml(r.kind)}<br>${escapeHtml(r.description||'')}</div>`
      ).join('');
    } else if(kind==='relationships'){
      const d=await apiGet('/api/expansion/relationships');
      const focus=(d.matrix||[]).filter(x=>['aria','muse','ledger'].includes(x.source)&&['aria','muse','ledger','user_primary'].includes(x.target)).slice(0,18);
      body=`<h2>Directional Relationships</h2>`+focus.map(x=>
        `<div class=card><b>${escapeHtml(x.source)} → ${escapeHtml(x.target)}</b> · ${escapeHtml(x.label)}
        <p class=muted>${escapeHtml(x.narrative||'')}</p>
        <pre style="font-size:11px;white-space:pre-wrap">${escapeHtml(JSON.stringify(x.dimensions,null,2))}</pre>
        <button type=button class="cc-btn ghost" onclick="showRelWhy('${escapeHtml(x.source)}','${escapeHtml(x.target)}')">WHY</button></div>`
      ).join('');
    } else if(kind==='emotion'){
      const agents=(state.roster||[]).map(a=>a.id);
      const blocks=[];
      for(const id of agents){
        const d=await apiGet('/api/expansion/emotion/'+id);
        const top=Object.entries(d.dimensions||{}).sort((a,b)=>b[1]-a[1]).slice(0,6);
        blocks.push(`<div class=card><b>${escapeHtml(id)}</b><pre style="font-size:11px">${escapeHtml(top.map(([k,v])=>k+': '+v).join('\\n'))}</pre>
          <button type=button class="cc-btn ghost" onclick="showEmotionWhy('${escapeHtml(id)}','jealousy')">jealousy WHY</button>
          <button type=button class="cc-btn ghost" onclick="showEmotionWhy('${escapeHtml(id)}','stress')">stress WHY</button></div>`);
      }
      body=`<h2>Emotional State</h2>`+blocks.join('');
    } else {
      body='<p class=muted>Unknown surface.</p>';
    }
  }catch(e){ body=`<p class=muted>Failed to load: ${escapeHtml(String(e))}</p>`; }

  appRoot().innerHTML=`<div class="home"><header class="home-header"><div>
    <p class="home-kicker">Keep Expansion</p><h1 class="home-greeting">${escapeHtml(kind)}</h1></div>
    <div class="home-meta"><button type=button class="cc-btn ghost" onclick="showHome()">Home</button>
    <button type=button class="cc-btn" onclick="showChat()">Codec</button></div></header>
    <section class="home-group">${body}</section>
    <div id="exp-why" class="card" style="display:none;margin:16px"></div>
  </div>`;
}

async function showEmotionWhy(agentId, dim){
  const d=await apiGet(`/api/expansion/emotion/${agentId}/why/${dim}`);
  const el=document.getElementById('exp-why');
  if(el){ el.style.display='block'; el.innerHTML=`<b>${escapeHtml(agentId)}.${escapeHtml(dim)} = ${d.value}</b><pre style="font-size:11px;white-space:pre-wrap">${escapeHtml(JSON.stringify(d,null,2))}</pre>`; }
}
async function showRelWhy(src, dst){
  const d=await apiGet(`/api/expansion/relationships/${src}/${dst}/why`);
  const el=document.getElementById('exp-why');
  if(el){ el.style.display='block'; el.innerHTML=`<b>${escapeHtml(src)} → ${escapeHtml(dst)}</b><pre style="font-size:11px;white-space:pre-wrap">${escapeHtml(JSON.stringify(d,null,2))}</pre>`; }
}

(async()=>{
  await loadCapabilities(); await loadPrefs(); await loadVoices(); await loadExpansion();
  if(location.search.includes('setup=1')) render();
  else if(location.search.includes('codec=1') || location.hash==='#codec') showChat();
  else showHome();
})();
