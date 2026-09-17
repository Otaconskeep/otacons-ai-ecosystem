let state={
  step:0,scan:null,name:'Aria',features:['chat','memory','voice'],config:null,storage:null,
  conversation:null,voiceId:'voice_aria',autoSpeak:false,voices:[],capabilities:null,
  currentAudio:null,speakingMsg:null,recorder:null,recordingState:'MIC_READY',
  testMode:window.__OTACON_TEST_MODE__===true,codecMode:'idle',codecBooted:false,lastModel:null,
  view:'codec',agentId:'agent_001',roster:[],expansion:null
};
const labels=['Welcome','System Scan','Hardware Recommendation','Storage','Agent Setup','Features','Review','Finish'];
const CODEC_FALLBACK={idle:'/assets/aria/aria-idle.mp4',thinking:'/assets/aria/aria-thinking.mp4',talking:'/assets/aria/aria-talking.mp4'};

function currentAgentId(){
  if(state.agentId && state.agentId!=='agent_001') return state.agentId;
  if(state.roster&&state.roster.length) return state.roster[0].id||state.roster[0].agent_id||'aria';
  return state.agentId||'aria';
}
function currentAgentName(){
  const r=(state.roster||[]).find(a=>a.id===state.agentId||a.agent_id===state.agentId);
  if(r) return r.display_name||r.id;
  return state.name||'Aria';
}
function currentPortraitId(){
  const aid=currentAgentId();
  if(aid==='agent_001') return 'aria';
  return aid||'aria';
}
function codecVideoFor(mode){
  const id=currentPortraitId();
  const m=mode||'idle';
  return `/assets/${id}/${id}-${m}.mp4`;
}
function roomKindFromRoute(route){
  const p=String(route||'').replace(/\/+$/,'')||'/';
  const map={
    '/dashboard':'dashboard','/war-room':'war-room','/intel':'intel',
    '/video-studio':'creative','/ha':'ops','/codec':'codec',
    '/emotion':'emotion','/emotions':'emotion','/page-builder':'page-builder',
    '/pages/builder':'page-builder','/ops':'ops','/creative':'creative'
  };
  return map[p]||'';
}
async function loadExpansion(){
  try{
    state.expansion=await apiGet('/api/expansion/status');
    if(state.expansion&&state.expansion.enabled&&(state.expansion.agents||[]).length){
      state.roster=state.expansion.agents.map(a=>({
        id:a.id||a.agent_id, display_name:a.display_name, role:a.role,
        voice_id:a.voice_id, room:a.room||a.room_route, room_title:a.room_title,
        avatar:a.avatar||`/assets/${a.id||a.agent_id}/${a.id||a.agent_id}.webp`
      }));
      if(!state.roster.find(a=>a.id===state.agentId) || state.agentId==='agent_001'){
        state.agentId=state.roster[0].id;
        state.name=state.roster[0].display_name;
        if(state.roster[0].voice_id) state.voiceId=state.roster[0].voice_id;
      }
    } else {
      state.roster=[];
    }
  }catch(e){ state.expansion=null; state.roster=[]; }
}

async function api(path,body,timeoutMs){
  const ctrl=typeof AbortController!=='undefined'?new AbortController():null;
  const ms=timeoutMs||45000;
  const timer=ctrl?setTimeout(()=>ctrl.abort(),ms):null;
  try{
    let r=await fetch(path,{method:'POST',headers:authHeaders(),body:JSON.stringify(body||{}),signal:ctrl?ctrl.signal:undefined});
    let data=null;
    try{ data=await r.json(); }catch(_e){ data={error:{code:'BAD_JSON',message:'Server returned a non-JSON response.'}}; }
    if(r.status===401&&data&&data.error&&data.error.code==='LAN_AUTH_REQUIRED'){
      state.lanAuthRequired=true;
    }
    return {ok:r.ok,status:r.status,data:data};
  }catch(err){
    const aborted=err&&(err.name==='AbortError'||/abort/i.test(String(err&&err.message||err)));
    return {
      ok:false,
      status:0,
      data:{
        error:{
          code: aborted?'TIMEOUT':'NETWORK_ERROR',
          message: aborted?'The request timed out.':'Could not reach the Otacon server.',
          technical:String(err&&err.message||err),
          exception:(err&&err.name)||'Error',
        }
      }
    };
  }finally{ if(timer) clearTimeout(timer); }
}
async function apiGet(path,timeoutMs){
  const ctrl=typeof AbortController!=='undefined'?new AbortController():null;
  const ms=timeoutMs==null?12000:timeoutMs;
  const timer=ctrl?setTimeout(()=>ctrl.abort(),ms):null;
  try{
    const headers={};
    const tok=getLanToken();
    if(tok) headers['Authorization']='Bearer '+tok;
    const r=await fetch(path,{headers:headers,signal:ctrl?ctrl.signal:undefined});
    if(!r.ok) throw new Error('HTTP '+r.status);
    return await r.json();
  }finally{ if(timer) clearTimeout(timer); }
}

const LAN_TOKEN_KEY='otacon_lan_token';
function getLanToken(){
  try{ return (sessionStorage.getItem(LAN_TOKEN_KEY)||'').trim(); }catch(_e){ return ''; }
}
function setLanToken(token){
  try{
    if(token) sessionStorage.setItem(LAN_TOKEN_KEY, String(token).trim());
    else sessionStorage.removeItem(LAN_TOKEN_KEY);
  }catch(_e){}
}
function authHeaders(extra){
  const h=Object.assign({'Content-Type':'application/json'}, extra||{});
  const tok=getLanToken();
  if(tok) h['Authorization']='Bearer '+tok;
  return h;
}
async function ensureLanAuthSession(){
  try{
    const st=await apiGet('/api/auth/status', 4000);
    state.bindMode=st&&st.bind_mode;
    state.lanAuthRequired=!!(st&&st.lan_auth_required);
    if(!state.lanAuthRequired) return true;
    if(st&&st.authenticated) return true;
    if(getLanToken()) return true;
    try{
      const boot=await apiGet('/api/auth/bootstrap', 4000);
      if(boot&&boot.token){ setLanToken(boot.token); return true; }
    }catch(_e){}
    return false;
  }catch(_e){
    return true;
  }
}
function showLanAuthMessage(box, detail){
  const msg=detail||'LAN mode requires a bearer token. Open Otacon on the host to bootstrap, or paste the token from ~/.config/otacon/lan_token.';
  if(box){
    box.insertAdjacentHTML('beforeend',
      `<div class="msg-row-bot"><div class="msg-bot"><div class="msg-bot-name">Network</div><div>${escapeHtml(msg)}</div>`+
      `<p class=muted style="margin-top:8px">Authentication / network mode — not a chat model failure.</p>`+
      `<button type=button id=lan-token-btn>Enter LAN token</button></div></div>`);
    const btn=document.getElementById('lan-token-btn');
    if(btn){
      btn.onclick=()=>{
        const t=window.prompt('Paste Otacon LAN token (from ~/.config/otacon/lan_token on the host):','');
        if(t&&t.trim()){ setLanToken(t.trim()); btn.textContent='Token saved — try again'; }
      };
    }
  }else{
    try{ window.alert(msg); }catch(_e){}
  }
}

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
  // Unknown/missing capabilities must NEVER look ready (CHAT READY lying).
  if(!state.capabilities) return false;
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
  await ensureLanAuthSession();
  await loadCapabilities();
  await loadExpansion();
  let scan=null;
  try{scan=await apiGet('/api/scan',8000)}catch(e){scan=null}
  const chatOk=capReady('chat'), ttsOk=capReady('tts'), sttOk=capReady('stt');
  const vtOk=capStatus('voice_trainer')==='ready';
  const model=(state.capabilities&&state.capabilities.llm_model)||'—';
  const hwHome=((scan&&scan.hardware&&scan.hardware.hardware)||{});
  const gpuDet=hwHome.gpu_detection||{};
  const expOn=!!(state.expansion&&state.expansion.enabled);
  const expReady=!!(state.expansion&&state.expansion.foundation_ready);
  const expAgents=(state.roster||[]).map(a=>a.display_name).join(' · ')||'—';
  const sem=((state.expansion&&state.expansion.report&&state.expansion.report.semantic)||{});
  const emotionOk=sem.emotion_engine==='READY';
  const relOk=sem.relationship_store==='READY';

  const agentRoomTiles=(state.roster||[]).map(a=>{
    const id=a.id||a.agent_id;
    const room=a.room_title||a.room||'Codec';
    return `<button type="button" class="svc" onclick="selectExpansionAgent('${escapeHtml(id)}')">
        <div class="svc-top"><div class="svc-ico">${escapeHtml(String(id).slice(0,3).toUpperCase())}</div><div class="svc-name">${escapeHtml(a.display_name||id)}</div></div>
        <p class="svc-desc">${escapeHtml(a.role||'')} · room ${escapeHtml(room)}</p>
        <span class="svc-pill ok">OPEN CODEC</span>
      </button>`;
  }).join('');

  const expansionSection=expOn?`
  <section class="home-group">
    <h2 class="home-group-title">Keep Expansion</h2>
    <div class="home-grid">
      <button type="button" class="svc" onclick="showChat()">
        <div class="svc-top"><div class="svc-ico">XP</div><div class="svc-name">Expansion Roster</div></div>
        <p class="svc-desc">${escapeHtml(expAgents)}</p>
        <span class="svc-pill ${expReady?'ok':'warn'}">${expReady?'FOUNDATION READY':'PARTIAL'}</span>
      </button>
      ${agentRoomTiles}
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
      <button type="button" class="svc" onclick="showExpansionSurface('rex')">
        <div class="svc-top"><div class="svc-ico">REX</div><div class="svc-name">Project REX</div></div>
        <p class="svc-desc">Autonomous work substrate — discover→verify→close under policy, not approvals.</p>
        <span class="svc-pill ok">AUTONOMY</span>
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
      <button type="button" class="svc" onclick="showExpansionSurface('learning')">
        <div class="svc-top"><div class="svc-ico">LRN</div><div class="svc-name">Learning Engine</div></div>
        <p class="svc-desc">Evidence-backed claims — private + shared Keep. Not memory. WHY provenance.</p>
        <span class="svc-pill ok">LEARNED</span>
      </button>
      <button type="button" class="svc" onclick="showExpansionSurface('dossiers')">
        <div class="svc-top"><div class="svc-ico">DOS</div><div class="svc-name">Dossiers</div></div>
        <p class="svc-desc">Canonical + living dossiers, vulnerabilities, learning, relationships.</p>
        <span class="svc-pill ok">DEPTH</span>
      </button>
      <button type="button" class="svc" onclick="showExpansionSurface('journal')">
        <div class="svc-top"><div class="svc-ico">JNL</div><div class="svc-name">Journal</div></div>
        <p class="svc-desc">Objective chronological history — what happened.</p>
        <span class="svc-pill ok">FACTS</span>
      </button>
      <button type="button" class="svc" onclick="showExpansionSurface('diary')">
        <div class="svc-top"><div class="svc-ico">DRY</div><div class="svc-name">Diary</div></div>
        <p class="svc-desc">Subjective interpretation — what it meant.</p>
        <span class="svc-pill ok">MEANING</span>
      </button>
      <button type="button" class="svc" onclick="showExpansionSurface('page-builder')">
        <div class="svc-top"><div class="svc-ico">PB</div><div class="svc-name">Page Builder</div></div>
        <p class="svc-desc">Allowlisted registry editor — no code injection.</p>
        <span class="svc-pill ok">REGISTRY</span>
      </button>
      <button type="button" class="svc" onclick="showExpansionSurface('rooms')">
        <div class="svc-top"><div class="svc-ico">RM</div><div class="svc-name">Rooms / Pages</div></div>
        <p class="svc-desc">Room registry + Page Builder (same allowlist).</p>
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
      <button type="button" class="svc" onclick="showExpansionSurface('command-center')">
        <div class="svc-top"><div class="svc-ico">HUD</div><div class="svc-name">Owner Overview</div></div>
        <p class="svc-desc">Roster emotions, autonomous jobs, alerts, learning, readiness — flagship dashboard.</p>
        <span class="svc-pill ${expOn?'ok':'warn'}">${expOn?'LIVE':'CORE'}</span>
      </button>
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
      <button type="button" class="svc ${vtOk?'':'svc-off'}" ${vtOk?'onclick="openVoiceTrainer()"':'disabled'}>
        <div class="svc-top"><div class="svc-ico">VT</div><div class="svc-name">Voice Trainer</div></div>
        <p class="svc-desc">${vtOk?'Opens Genome Voice Trainer (http://127.0.0.1:8765/) for Piper cloning/training.':'Not installed — Setup adds it when NVIDIA is detected.'}</p>
        <span class="svc-pill ${vtOk?'ok':'warn'}">${vtOk?'OPEN GENOME':'NOT INSTALLED'}</span>
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
  if(s===2){let h=state.scan.hardware.hardware,g=state.scan.hardware.gpu_roles,det=h.gpu_detection||{}; page.innerHTML=`<div class=card>System: ${h.os}<br>CPU: ${h.cpu.model} (${h.cpu.cores} cores)<br>Memory: ${h.ram_gb} GB</div>`+(h.gpus.length?h.gpus.map(x=>`<div class=card>${escapeHtml(x.model)} — ${x.vram_gb?x.vram_gb+' GB VRAM':'VRAM n/a'} — ${escapeHtml(x.capability||'')}</div>`).join(''):`<div class=card>${escapeHtml(det.message||'No NVIDIA GPU found by scan')}</div>`)+`<p class=muted>Recommended primary: ${g.primary_gpu}</p><button onclick="next()">Use Recommended Setup</button>`;}
  if(s===3){let v=state.scan.storage.find(x=>x.recommended)||state.scan.storage[0]||{}; page.innerHTML=`<div class=card><b>Recommended storage</b><br>${v.path||'Unavailable'}<br>${v.free_gb||0} GB free</div><button onclick="next()">Use Recommended Storage</button>`;}
  if(s===4){ page.innerHTML=agentSetupHtml(); updateSetupAvatar(); }
  if(s===5) page.innerHTML=featuresHtml()+'<button onclick="setFeatures()">Continue</button>';
  if(s===6) page.innerHTML=`<div class=card>Agent: ${state.name}<br>Voice: ${voiceLabel(state.voiceId)}<br>Features: ${state.features.join(', ')}<br>Storage: ${(state.scan.storage.find(x=>x.recommended)||state.scan.storage[0]||{}).path||'Unavailable'}</div><button onclick="build()">Create Configuration</button>`;
  if(s===7) page.innerHTML=`<p>${state.name} is configured.</p><p class=muted>Open Codec to talk — portrait stays in the right port, messages are text-only below.</p><div class=card>${state.config?.saved||''}</div><button onclick="showChat()">Open Codec</button>`;
}

function next(){state.step++;render()}
function _fallbackScan(){
  return {
    hardware:{hardware:{os:'Linux',cpu:{model:'unknown',cores:1},ram_gb:0,free_storage_gb:0,gpus:[]},gpu_roles:{primary_gpu:'cpu'}},
    storage:[{path:'.',free_gb:0,total_gb:0,recommended:true}]
  };
}
async function scan(){
  const page=document.getElementById('page');
  if(page) page.innerHTML='<p class=muted>Scanning hardware…</p>';
  try{
    state.scan=await apiGet('/api/scan',8000);
  }catch(e){
    state.scan=_fallbackScan();
    if(page) page.innerHTML='<p class=muted>GPU probe timed out — continuing with CPU defaults.</p>';
  }
  state.storage=(state.scan.storage||[]).find(x=>x.recommended)||(state.scan.storage||[])[0]||_fallbackScan().storage[0];
  state.step=2; render();
}
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
  const src=codecVideoFor(mode);
  const fallback=CODEC_FALLBACK[mode]||CODEC_FALLBACK.idle;
  if(!v.dataset.boundFallback){
    v.dataset.boundFallback='1';
    v.addEventListener('error', ()=>{
      if(v.src && !v.src.endsWith(fallback) && !String(v.src).includes('/assets/aria/')){
        v.src=fallback;
        v.play().catch(()=>{});
      }
    });
  }
  const cur=v.getAttribute('src')||'';
  if(cur!==src){ v.src=src; }
  v.play().catch(()=>{});
  const badge=document.getElementById('codecStatus');
  if(badge) badge.textContent=mode.toUpperCase();
  const lbl=document.getElementById('active-ai-label');
  if(lbl) lbl.textContent=mode==='idle'?'STANDBY':(currentAgentName()||'ARIA').toUpperCase();
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
  let r=await api('/api/synthesize_agent_speech',{
    agent:{id:currentAgentId(),display_name:currentAgentName(),voice_id:state.voiceId},
    text
  });
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
  // Paint Codec even if prefs/voices are slow. GPU scan has a hard timeout
  // (platform.detect abandons hung nvidia-smi) so we never skip it and lie.
  await Promise.allSettled([
    loadPrefs(),
    loadVoices(),
    loadCapabilities(),
    loadExpansion(),
  ]);
  let scan=null;
  try{ scan=await apiGet('/api/scan', 8000); }catch(_e){ scan=null; }
  const aid=currentAgentId();
  let cs;
  try{
    cs=(await api('/api/conversations',{agent_id:aid},8000)).data;
  }catch(e){ cs=[]; }
  try{
    state.conversation=(cs[0]||{}).id||(await api('/api/conversation',{agent_id:aid},8000)).data.id;
  }catch(e){
    state.conversation=null;
  }

  const ttsOk=capReady('tts'), chatOk=capReady('chat'), sttOk=capReady('stt');
  const voiceOk=chatOk&&ttsOk;
  const model=(state.capabilities&&state.capabilities.llm_model)||state.lastModel||'—';
  const hw=((scan&&scan.hardware&&scan.hardware.hardware)||{});
  const gpus=hw.gpus||[];
  const gpuDet=hw.gpu_detection||{};
  let gpuLine='GPU status unavailable';
  const st=(gpuDet&&gpuDet.status)?String(gpuDet.status):'';
  if(gpus.length){
    gpuLine=gpus.map(g=>{
      const name=g.model||g.name||'GPU';
      const vram=g.vram_gb?` · ${g.vram_gb} GB`:'';
      return `${name}${vram}`;
    }).join(' / ');
  }else if(st==='none'){
    gpuLine=(gpuDet&&gpuDet.message)?String(gpuDet.message):'No supported GPU detected';
  }else if(st==='error'||st==='unavailable'||st==='skipped'){
    gpuLine=(gpuDet&&gpuDet.message)?String(gpuDet.message):'GPU status unavailable';
  }else if(gpuDet&&gpuDet.message){
    gpuLine=String(gpuDet.message);
  }
  const vtOk=capStatus('voice_trainer')==='ready';
  const voiceOpts=(state.voices||[]).map(v=>`<option value="${v.id}" ${v.id===state.voiceId?'selected':''}>${v.display_name}</option>`).join('');
  const roster=state.roster&&state.roster.length?state.roster:[{id:aid,display_name:currentAgentName()}];
  const agentBtns=roster.map(a=>{
    const id=a.id||a.agent_id;
    const active=id===aid?' codec-ai-active':'';
    return `<button type=button class="codec-ai-btn${active}" title="${escapeHtml(a.display_name||id)}" onclick="selectExpansionAgent('${escapeHtml(id)}')">${escapeHtml(String(a.display_name||id).toUpperCase())}</button>`;
  }).join('');
  const agentName=currentAgentName();
  const portraitAgent=currentPortraitId();
  const idleSrc=`/assets/${portraitAgent}/${portraitAgent}-idle.mp4`;
  const agentRoom=(roster.find(a=>(a.id||a.agent_id)===aid)||{});
  const roomLabel=agentRoom.room_title||agentRoom.room||'Agent room';

  appRoot().innerHTML=`<div class="codec-cockpit">
  <header class="cc-mast">
    <div>
      <h1>Otacon // Codec</h1>
      <div class="cc-sub">${state.roster.length?'Expansion roster · voice · status':'Local Lite cockpit · voice · agent · status — not the full Keep'}</div>
      <div class="cc-greeble">
        <span>LINK LOCAL</span>
        <span>CHAT ${chatOk?'READY':'DOWN'}</span>
        <span>VOICE ${voiceOk?'READY':'DOWN'}</span>
        <span>MODEL ${escapeHtml(String(model))}</span>
        <span>AGENT ${escapeHtml(String(agentName).toUpperCase())}</span>
      </div>
    </div>
    <div class="cc-mast-actions">
      <button type=button class="cc-btn ghost" onclick="showHome()">Home</button>
      ${state.roster.length?`<button type=button class="cc-btn ghost" id="codec-open-room" onclick="openCurrentAgentRoom()">Open ${escapeHtml(roomLabel)}</button>`:''}
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
            <div class="codec-port port-left" id="port-operator">
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
        <p class=muted style="font-size:10px;margin:0 0 8px">${vtOk?'Genome Piper trainer on this machine. Training happens in Genome — not inside Codec chat.':'Not installed. Setup installs it when NVIDIA is detected.'}</p>
        ${vtOk?'<button type=button class="cc-btn" onclick="openVoiceTrainer()">Open Genome (8765)</button>':'<p class=muted style="font-size:10px;margin:0">Install Otacon with GPU to enable training.</p>'}
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
  if(state.conversation) await openConversation(state.conversation);
  try{ await loadMemories(); }catch(e){}
  setCodecMode('idle');
  bootCodecOnce();
  if(window.__codecFreqTimer) clearInterval(window.__codecFreqTimer);
  window.__codecFreqTimer=setInterval(animateFreq,900);
  const inp=document.getElementById('chat-inp'); if(inp) inp.focus();
}

async function selectExpansionAgent(id){
  if(!id) return;
  const same=id===state.agentId;
  state.agentId=id;
  const r=(state.roster||[]).find(a=>(a.id||a.agent_id)===id);
  if(r){
    state.name=r.display_name||id;
    if(r.voice_id) state.voiceId=r.voice_id;
  }
  state.codecBooted=false;
  await showChat();
  // Keep-like: switching agents stays in Codec with that agent's room ready via Open Room.
  if(!same){
    const roomBtn=document.getElementById('codec-open-room');
    if(roomBtn && r && r.room) roomBtn.textContent='Open '+(r.room_title||r.room);
  }
}

async function openCurrentAgentRoom(){
  const r=(state.roster||[]).find(a=>(a.id||a.agent_id)===currentAgentId());
  const route=(r&&r.room)||'';
  const kind=roomKindFromRoute(route);
  if(kind==='codec'||!kind){ await showChat(); return; }
  await showExpansionSurface(kind);
}

async function openVoiceTrainer(){
  const url=(state.capabilities&&state.capabilities.voice_trainer_url)||'http://127.0.0.1:8765/';
  try{
    const probe=await fetch(url,{mode:'no-cors',cache:'no-store'});
    void probe;
  }catch(_e){}
  window.open(url,'_blank','noopener');
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
  await ensureLanAuthSession();
  let uid=box.querySelectorAll('.msg-row-user,.msg-row-bot').length;
  box.insertAdjacentHTML('beforeend', `<div class="msg-row-user"><div class="msg-user">${escapeHtml(m)}</div></div><div class="msg-row-bot" id=wait><div class="msg-bot"><div class="typing-dots"><span></span><span></span><span></span></div></div></div>`);
  el.value='';
  box.scrollTop=box.scrollHeight;
  setCodecMode('thinking');
  let r=null;
  try{
    r=await api('/api/chat_with_agent',{
      agent:{id:currentAgentId(),display_name:currentAgentName(),voice_id:state.voiceId},
      message:m, conversation_id:state.conversation, auto_speak:state.autoSpeak
    });
  }catch(err){
    r={ok:false,data:{error:{code:'CLIENT_ERROR',message:String(err&&err.message||err),exception:(err&&err.name)||'Error'}}};
  }finally{
    document.getElementById('wait')?.remove();
    // Guaranteed: THINKING never sticks after any failure or success.
    if(!(r&&r.ok&&state.autoSpeak&&r.data&&r.data.voice&&r.data.voice.audio_base64)){
      setCodecMode('idle');
    }
  }
  if(!r||!r.ok){
    const err=r&&r.data&&r.data.error;
    const code=(err&&err.code)||'';
    if(code==='LAN_AUTH_REQUIRED'||r.status===401){
      showLanAuthMessage(box, (err&&err.message)||'');
      try{ console.warn('[CODEC] LAN_AUTH_REQUIRED'); }catch(_e){}
      box.scrollTop=box.scrollHeight;
      return;
    }
    const tech=(err&&(err.technical||err.message))||'';
    box.insertAdjacentHTML('beforeend', `<div class="msg-row-bot"><div class="msg-bot"><div class="msg-bot-name">${escapeHtml(currentAgentName())}</div><div>I couldn't complete that request.</div></div></div>`);
    try{ console.warn('[CODEC]', code||'CHAT_FAIL', (err&&err.exception)||'', tech); }catch(_e){}
    box.scrollTop=box.scrollHeight;
    return;
  }
  let d=r.data;
  if(d.model){ state.lastModel=d.model; const mEl=document.getElementById('codecModel'); if(mEl) mEl.textContent=d.model; }
  if(d.model_note){
    box.insertAdjacentHTML('beforeend', `<p class=muted style="font-size:10px">${escapeHtml(d.model_note)}</p>`);
  }
  if(d.conversation_id){ state.conversation=d.conversation_id; }
  let mid=uid+1;
  box.insertAdjacentHTML('beforeend', messageHtml('assistant', d.text, mid));
  box.scrollTop=box.scrollHeight;
  if(d.voice && d.voice.status==='error'){
    let err=document.querySelector(`[data-speak-err="${mid}"]`);
    if(err) err.textContent='Voice playback unavailable';
  } else if(state.autoSpeak && d.voice && d.voice.audio_base64){
    playAudio(d.voice.audio_base64, mid);
  } else {
    setCodecMode('idle');
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
  try{
    const pathMap={
      'war-room':'/war-room','dashboard':'/dashboard','intel':'/intel',
      'video-studio':'/video-studio','ha':'/ha','rex':'/rex','learning':'/learning',
      'creative':'/creative','ops':'/ops','reports':'/reports','dossiers':'/dossiers',
      'journal':'/journal','diary':'/diary','page-builder':'/page-builder','rooms':'/rooms',
      'relationships':'/relationships','emotion':'/emotion','command':'/command',
      'command-center':'/command-center'
    };
    const target=pathMap[kind]||('/'+String(kind||'').replace(/^\/+/,''));
    if(target && location.pathname!==target){
      history.pushState({expansion:kind}, '', target);
    }
  }catch(_e){}
  if(kind==='rex'){
    await showRexBoard();
    return;
  }
  if(kind==='learning'){
    let body='';
    try{
      const d=await apiGet('/api/expansion/learning');
      if(d && d.enabled===false){
        body=`<h2>Learning Engine</h2>
          <p class=err>${escapeHtml(d.message||'Expansion not entitled')}</p>
          <p class=muted>Open /api/expansion/entitlement for the denial reason. Foundation may be installed while surfaces stay locked.</p>`;
      }else{
      const sum=d.summary||{};
      const card=(c)=>`<div class="learn-claim card">
        <div class="svc-top"><div class="svc-name">LEARNED CLAIM</div><span class="svc-pill ok">${escapeHtml(String(c.confidence))}</span></div>
        <p><b>${escapeHtml(c.claim)}</b></p>
        <p class=muted>scope: ${escapeHtml(c.scope_label||c.scope)} · type ${escapeHtml(c.learning_type)} · status ${escapeHtml(c.status)}</p>
        <p class=muted>evidence ${escapeHtml(String(c.evidence_count||0))} (+${escapeHtml(String(c.positive_evidence_count||0))} / −${escapeHtml(String(c.negative_evidence_count||0))}) · contradictions ${escapeHtml(String(c.contradictions||0))}</p>
        <button type=button class="cc-btn" onclick="showLearningWhy('${escapeHtml(c.claim_id)}')">WHY?</button>
      </div>`;
      const shared=(d.shared_keep||[]).map(card).join('')||'<p class=muted>No shared Keep claims yet.</p>';
      const privBlocks=Object.entries(d.private_by_agent||{}).map(([aid,rows])=>
        `<h3>${escapeHtml(aid)} — private</h3>${(rows||[]).map(card).join('')||'<p class=muted>None</p>'}`
      ).join('')||'<p class=muted>No private agent claims yet.</p>';
      body=`<h2>Learning Engine</h2>
        <p class=muted>${escapeHtml(sum.note||'')}</p>
        <p class=muted>memory ≠ learning · living dossier ≠ learning · emotion ≠ learning · threshold ${escapeHtml(String(sum.pattern_threshold||3))}</p>
        <h3>Shared Keep learning</h3>${shared}
        <h3>Private agent learning</h3>${privBlocks}
        <div id="learn-why" class="card" style="display:none;margin-top:16px"></div>`;
      }
    }catch(e){ body=`<p class=err>${escapeHtml(String(e))}</p>`; }
    appRoot().innerHTML=`<div class="home"><header class="home-header"><div>
      <p class="home-kicker">Keep Expansion</p><h1 class="home-greeting">Learning</h1></div>
      <div class="home-meta"><button type=button class="cc-btn ghost" onclick="showHome()">Home</button>
      <button type=button class="cc-btn" onclick="showChat()">Codec</button></div></header>
      <section class="home-group">${body}</section></div>`;
    return;
  }
  const fn=(typeof FLOOR_KINDS!=='undefined' && FLOOR_KINDS[kind]) || null;
  if(fn){
    try{ await fn(); }catch(e){
      appRoot().innerHTML=`<div class="home"><p class=err>${escapeHtml(String(e))}</p>
        <button type=button class="cc-btn ghost" onclick="showHome()">Home</button></div>`;
    }
    return;
  }
  appRoot().innerHTML=`<div class="home"><p class=muted>Unknown surface: ${escapeHtml(kind)}</p>
    <button type=button class="cc-btn ghost" onclick="showHome()">Home</button></div>`;
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
async function showLearningWhy(claimId){
  const d=await apiGet('/api/expansion/learning/why/'+encodeURIComponent(claimId));
  const html=`<h3>WHY — ${escapeHtml(d.claim||claimId)}</h3>
    <p class=muted>confidence ${escapeHtml(String(d.confidence))} · status ${escapeHtml(d.status||'')} · contradictions ${escapeHtml(String(d.contradiction_count||0))}</p>
    <p><b>Supporting observations</b></p>
    <pre style="font-size:11px;white-space:pre-wrap">${escapeHtml(JSON.stringify(d.supporting_observations||[],null,2))}</pre>
    <p><b>Contradicting observations</b></p>
    <pre style="font-size:11px;white-space:pre-wrap">${escapeHtml(JSON.stringify(d.contradicting_observations||[],null,2))}</pre>
    <p><b>Source events / jobs</b></p>
    <pre style="font-size:11px;white-space:pre-wrap">${escapeHtml(JSON.stringify(d.source_events_jobs||[],null,2))}</pre>
    <p><b>Confidence history</b></p>
    <pre style="font-size:11px;white-space:pre-wrap">${escapeHtml(JSON.stringify(d.confidence_history||[],null,2))}</pre>
    <p><b>Revision history</b></p>
    <pre style="font-size:11px;white-space:pre-wrap">${escapeHtml(JSON.stringify(d.revision_history||[],null,2))}</pre>
    <p class=muted>${escapeHtml((d.separations&&JSON.stringify(d.separations))||d.rule||'')}</p>`;
  let el=document.getElementById('learn-why')||document.getElementById('exp-why');
  if(!el){
    // Reports surface uses exp-why container
    el=document.getElementById('exp-why');
  }
  if(el){ el.style.display='block'; el.innerHTML=html; el.scrollIntoView({behavior:'smooth',block:'nearest'}); }
  else window.alert('WHY: '+ (d.claim||claimId));
}

/* —— Project REX (autonomous coordination substrate) —— */
const REX_STATE={board:null, filter:'ACTIVE', archiveOpen:false, byId:{}, actor:'aria'};

function rexIndex(board){
  REX_STATE.byId={};
  (board.columns||[]).forEach(col=>{
    (col.cards||[]).forEach(c=>{ if(c&&c.job_id) REX_STATE.byId[c.job_id]=c; });
  });
}

function rexCardMatches(card, filter){
  if(!filter || filter==='ALL') return true;
  if(filter==='ACTIVE') return !card.archived && card.stage!=='CANCELLED';
  if(filter==='ARCHIVE') return !!card.archived || card.stage==='DONE';
  return (card.stage||card.status)===filter;
}

function rexRenderColumns(board){
  const filter=REX_STATE.filter||'ACTIVE';
  const cols=(board.columns||[]).filter(c=>!c.archived);
  return `<div class="rex-cork" role="list">${cols.map(col=>{
    const cards=(col.cards||[]).filter(c=>rexCardMatches(c, filter));
    const body=cards.length
      ? cards.map(c=>`<button type="button" class="rex-card tone-${escapeHtml(c.tone||'muted')}" data-job="${escapeHtml(c.job_id)}" role="listitem">
          <div class="rex-card-title">${escapeHtml(c.title||c.job_id)}</div>
          <div class="rex-card-meta">${escapeHtml(c.owner||'unassigned')} · ${escapeHtml(c.domain||'')}${c.attempt?` · try ${c.attempt}/${c.retry_budget}`:''}</div>
        </button>`).join('')
      : `<div class="rex-empty">Empty — ${escapeHtml(col.label)}</div>`;
    const oversight=col.oversight_only?' oversight':'';
    return `<div class="rex-col${oversight}" data-status="${escapeHtml(col.status)}">
      <div class="rex-col-h"><span class="label">${escapeHtml(col.label)}</span><span class="count">${cards.length}</span></div>
      ${body}
    </div>`;
  }).join('')}</div>`;
}

function rexRenderArchive(board){
  const archived=(board.columns||[]).filter(c=>c.archived);
  const cards=archived.flatMap(c=>c.cards||[]).filter(c=>rexCardMatches(c, REX_STATE.filter==='ACTIVE'?'ARCHIVE':REX_STATE.filter));
  const collapsed=REX_STATE.archiveOpen?'':' collapsed';
  return `<section class="rex-archive${collapsed}" id="rex-archive">
    <button type="button" class="rex-archive-h" onclick="rexToggleArchive()">
      <span>Done · closed work</span>
      <span class="muted">${cards.length} · ${REX_STATE.archiveOpen?'collapse':'expand'}</span>
    </button>
    <div class="rex-archive-body">${cards.length
      ? cards.map(c=>`<button type="button" class="rex-card tone-${escapeHtml(c.tone||'muted')}" data-job="${escapeHtml(c.job_id)}">
          <div class="rex-card-title">${escapeHtml(c.title||c.job_id)}</div>
          <div class="rex-card-meta">${escapeHtml(c.stage||c.status)} · ${escapeHtml(c.owner||'')}</div>
        </button>`).join('')
      : '<div class="rex-empty">No closed work yet.</div>'}</div>
  </section>`;
}

function rexRenderSignals(board){
  const vs=board.value_signals||{};
  const block=(title, rows)=>`<div class="rex-signal"><h3>${escapeHtml(title)}</h3><ul>${
    (rows||[]).length
      ? rows.map(c=>`<li data-job="${escapeHtml(c.job_id)}">${escapeHtml(c.title||c.job_id)} · ${escapeHtml(c.owner||'')}</li>`).join('')
      : '<li class="muted">None</li>'
  }</ul></div>`;
  return `<div class="rex-signals">${block('Hard blockers (oversight)', vs.hard_blockers)}${block('Rework / retry', vs.rework)}${block('Verifying (peer)', vs.verifying)}${block('Newly discovered', vs.discovered)}</div>`;
}

function rexRenderAutonomy(board){
  const m=(board.autonomy&&board.autonomy.metrics)||board.metrics||{};
  return `<section class="rex-autonomy">
    <h2>Keep Autonomy</h2>
    <p class="rex-autonomy-note">Observe outcomes — agents move cards under policy. No routine approve queue.</p>
    <div class="rex-metrics">
      <div class="rex-metric"><span class="n">${m.completed_overnight||m.completed_today||0}</span><span class="l">Completed overnight</span></div>
      <div class="rex-metric"><span class="n">${m.in_progress||0}</span><span class="l">In progress</span></div>
      <div class="rex-metric"><span class="n">${m.blocked||m.hard_blockers||0}</span><span class="l">Hard blocked</span></div>
      <div class="rex-metric"><span class="n">${m.newly_discovered||0}</span><span class="l">Newly discovered</span></div>
      <div class="rex-metric"><span class="n">${m.failed_retrying||0}</span><span class="l">Failed / retrying</span></div>
      <div class="rex-metric"><span class="n">${m.agents_working||0}</span><span class="l">Agents working</span></div>
      <div class="rex-metric"><span class="n">${m.jobs_active||0}</span><span class="l">Jobs active</span></div>
      <div class="rex-metric"><span class="n">${m.research_sessions||0}</span><span class="l">Researching</span></div>
    </div>
  </section>`;
}

function rexWireBoard(){
  document.querySelectorAll('.rex-card[data-job], .rex-signal li[data-job]').forEach(el=>{
    el.addEventListener('click', ()=>rexOpenJob(el.getAttribute('data-job')));
  });
  document.querySelectorAll('.rex-fb').forEach(btn=>{
    btn.addEventListener('click', ()=>{
      REX_STATE.filter=btn.getAttribute('data-filter')||'ACTIVE';
      showRexBoard({keepFilter:true});
    });
  });
  const actor=document.getElementById('rex-actor');
  if(actor) actor.addEventListener('change', ()=>{ REX_STATE.actor=actor.value; });
}

function rexToggleArchive(){
  REX_STATE.archiveOpen=!REX_STATE.archiveOpen;
  const el=document.getElementById('rex-archive');
  if(el) el.classList.toggle('collapsed', !REX_STATE.archiveOpen);
}

function rexCloseModal(){
  const m=document.getElementById('rex-modal');
  if(m) m.hidden=true;
  if(document.onkeydown) document.onkeydown=null;
}

function rexOpenJob(jobId){
  const c=REX_STATE.byId[jobId];
  const m=document.getElementById('rex-modal');
  if(!c||!m) return;
  const transitions=(c.allowed_transitions||[]).map(st=>{
    const cls=st==='CANCELLED'||st==='HARD_BLOCKED'?'danger':(st==='REWORK'?'warn':'');
    return `<button type="button" class="${cls}" onclick="rexTransition('${escapeHtml(c.job_id)}','${escapeHtml(st)}')">${escapeHtml(st)}</button>`;
  }).join('')||'<span class="muted">Terminal</span>';
  const plan=(c.coordination_plan||[]).length
    ? `<ol class="rex-plan">${c.coordination_plan.map(s=>`<li>${escapeHtml(typeof s==='string'?s:JSON.stringify(s))}</li>`).join('')}</ol>`
    : '<p class="muted">No Aria coordination plan yet.</p>';
  const reviews=(c.peer_reviews||[]).slice(-5).map(r=>
    `<div class="muted">${escapeHtml(r.reviewer)} · ${escapeHtml(r.verdict)} — ${escapeHtml(r.note||'')}</div>`
  ).join('')||'<p class="muted">No peer reviews yet.</p>';
  const trace=(c.decision_trace||[]).slice(-8).map(t=>
    `<div class="muted">${escapeHtml(t.actor)} · ${escapeHtml(t.action)} — ${escapeHtml(t.detail||'')}</div>`
  ).join('')||'<p class="muted">No decision trace.</p>';
  m.hidden=false;
  m.innerHTML=`<div class="rex-modal-panel" role="dialog" aria-modal="true">
    <h3>${escapeHtml(c.title||c.job_id)}</h3>
    <p class="rex-modal-meta">${escapeHtml(c.job_id)} · stage ${escapeHtml(c.stage||c.status)} · job ${escapeHtml(c.job_status||'')} · owner ${escapeHtml(c.owner||'—')} · ${escapeHtml(c.domain||'')}${c.discovered_by?` · discovered by ${escapeHtml(c.discovered_by)}`:''}</p>
    <p class="rex-modal-meta">Actor moving as: <b>${escapeHtml(REX_STATE.actor||'aria')}</b> (policy-gated)</p>
    <div class="rex-actions">${transitions}</div>
    <h4>Coordination plan</h4>${plan}
    <h4>Peer review</h4>${reviews}
    <div class="rex-actions">
      <button type="button" onclick="rexPeerReview('${escapeHtml(c.job_id)}','pass')">Peer pass</button>
      <button type="button" class="warn" onclick="rexPeerReview('${escapeHtml(c.job_id)}','fail')">Peer fail</button>
    </div>
    <h4>Decision trace</h4>${trace}
    <pre>${escapeHtml(JSON.stringify({
      result:c.result, error:c.error, evidence:c.evidence, research_refs:c.research_refs,
      attempt:c.attempt, retry_budget:c.retry_budget, follow_ups:c.follow_ups,
      awaiting_user_approval:c.awaiting_user_approval
    },null,2))}</pre>
    <button type="button" class="cc-btn ghost" data-close onclick="rexCloseModal()">Close</button>
  </div>`;
  m.onclick=(e)=>{ if(e.target===m) rexCloseModal(); };
  document.onkeydown=(e)=>{ if(e.key==='Escape') rexCloseModal(); };
  m.querySelector('[data-close]')?.focus();
}

async function rexTransition(jobId, stage){
  let note='';
  if(stage==='REWORK'||stage==='HARD_BLOCKED'||stage==='DONE'){
    note=window.prompt(stage==='DONE'?'Close note / result (optional):':'Note (optional):')||'';
  }
  const r=await api('/api/expansion/rex/transition',{
    job_id:jobId, stage, status:stage, note, actor:REX_STATE.actor||'aria'
  });
  if(!r.ok){
    window.alert((r.data&&r.data.error&&r.data.error.message)||'Transition failed');
    return;
  }
  rexCloseModal();
  await showRexBoard({keepFilter:true});
}

async function rexPeerReview(jobId, verdict){
  const note=window.prompt('Peer review note (optional):')||'';
  const r=await api('/api/expansion/rex/peer-review',{
    job_id:jobId, reviewer:REX_STATE.actor||'ledger', verdict, note
  });
  if(!r.ok){
    window.alert((r.data&&r.data.error&&r.data.error.message)||'Review failed');
    return;
  }
  await showRexBoard({keepFilter:true});
  rexOpenJob(jobId);
}

async function rexCreateJob(){
  const input=document.getElementById('rex-new-request');
  const domainEl=document.getElementById('rex-new-domain');
  const request=(input&&input.value||'').trim();
  if(!request){ window.alert('Describe the work first.'); return; }
  const domain=(domainEl&&domainEl.value)||'coordination';
  const actor=REX_STATE.actor||'aria';
  const r=await api('/api/expansion/rex/discover',{actor, request, domain});
  if(!r.ok){
    // Oversight inject: queue without discover grant
    const q=await api('/api/expansion/rex/queue',{request, domain, discovered_by:actor, stage:'BACKLOG'});
    if(!q.ok){
      window.alert((r.data&&r.data.error&&r.data.error.message)||'Create failed');
      return;
    }
  }
  if(input) input.value='';
  await showRexBoard({keepFilter:true});
}

async function rexAutonomyTick(){
  const btn=[...document.querySelectorAll('button')].find(b=>b.textContent&&b.textContent.includes('autonomy tick'));
  if(btn) btn.disabled=true;
  try{
    const r=await api('/api/expansion/rex/tick',{max_jobs:5, detect:true});
    if(!r.ok){
      window.alert((r.data&&r.data.error&&r.data.error.message)||'Autonomy tick failed');
      return;
    }
    const m=(r.data&&r.data.metrics)||{};
    window.alert(
      'Autonomy tick '+((r.data&&r.data.elapsed_ms)||'?')+'ms\\n'+
      'Discovered: '+((r.data&&r.data.discovered)||[]).length+'\\n'+
      'Processed: '+((r.data&&r.data.processed)||[]).length+'\\n'+
      'Completed today: '+(m.completed_today||0)+' · Active: '+(m.jobs_active||0)+' · Hard blocked: '+(m.hard_blockers||0)
    );
    await showRexBoard({keepFilter:true});
  } finally {
    if(btn) btn.disabled=false;
  }
}

async function showRexBoard(opts){
  opts=opts||{};
  state.view='expansion';
  setBodyMode('home');
  if(!opts.keepFilter){
    const params=new URLSearchParams(location.search);
    REX_STATE.filter=params.get('rex_filter')||'ACTIVE';
  }
  let board;
  try{
    board=await apiGet('/api/expansion/rex');
  }catch(e){
    appRoot().innerHTML=`<div class="home"><header class="home-header"><div>
      <p class="home-kicker">Keep Expansion</p><h1 class="home-greeting">Project REX</h1></div>
      <div class="home-meta"><button type=button class="cc-btn ghost" onclick="showHome()">Home</button></div></header>
      <p class=muted>Failed to load: ${escapeHtml(String(e))}</p></div>`;
    return;
  }
  if(board&&board.enabled===false){
    appRoot().innerHTML=`<div class="home"><header class="home-header"><div>
      <p class="home-kicker">Keep Expansion</p><h1 class="home-greeting">Project REX</h1></div>
      <div class="home-meta"><button type=button class="cc-btn ghost" onclick="showHome()">Home</button></div></header>
      <p class=muted>${escapeHtml(board.message||'Expansion not entitled')}</p></div>`;
    return;
  }
  REX_STATE.board=board;
  rexIndex(board);
  if(['ARCHIVE','DONE','CANCELLED'].includes(REX_STATE.filter)) REX_STATE.archiveOpen=true;
  const filters=['ALL','ACTIVE','ARCHIVE','BACKLOG','READY','RESEARCHING','PLANNING','ASSIGNED','IN_PROGRESS','VERIFYING','REWORK','DONE','HARD_BLOCKED'];
  const filterBar=filters.map(f=>`<button type="button" class="rex-fb${REX_STATE.filter===f?' on':''}" data-filter="${f}">${f}</button>`).join('');
  const loop=(board.loop||[]).join(' → ');
  appRoot().innerHTML=`<div class="home rex-page"><header class="home-header"><div>
    <p class="home-kicker">Keep Expansion · Autonomous substrate</p>
    <h1 class="home-greeting">Project REX</h1></div>
    <div class="home-meta">
      <button type=button class="cc-btn ghost" onclick="showHome()">Home</button>
      <button type=button class="cc-btn ghost" onclick="showExpansionSurface('war-room')">War Room</button>
      <button type=button class="cc-btn" onclick="showChat()">Codec</button>
    </div></header>
    <div class="rex">
      ${rexRenderAutonomy(board)}
      <section class="rex-guide">
        <h2>Autonomous work loop</h2>
        <p>${escapeHtml(board.note||'')}</p>
        <p class="muted" style="margin-top:.5rem">${escapeHtml(loop)}</p>
      </section>
      <div class="rex-compose">
        <select id="rex-actor" title="Acting agent (policy)">
          <option value="aria">Aria (coordinator)</option>
          <option value="vector">Vector</option>
          <option value="ledger">Ledger</option>
          <option value="muse">Muse</option>
          <option value="sentry">Sentry</option>
        </select>
        <input id="rex-new-request" type="text" placeholder="Discovered work / inject backlog…" maxlength="240" />
        <select id="rex-new-domain">
          <option value="coordination">coordination</option>
          <option value="infrastructure">infrastructure</option>
          <option value="records">records</option>
          <option value="creative">creative</option>
          <option value="security">security</option>
        </select>
        <button type="button" class="cc-btn" onclick="rexCreateJob()">Discover / queue</button>
        <button type="button" class="cc-btn" onclick="rexAutonomyTick()">Run autonomy tick</button>
      </div>
      <div class="rex-filters">${filterBar}</div>
      ${rexRenderColumns(board)}
      ${rexRenderArchive(board)}
      ${rexRenderSignals(board)}
    </div>
    <div id="rex-modal" class="rex-modal" hidden></div>
  </div>`;
  const actorEl=document.getElementById('rex-actor');
  if(actorEl){ actorEl.value=REX_STATE.actor||'aria'; }
  rexWireBoard();
  const focus=new URLSearchParams(location.search).get('focus');
  if(focus && REX_STATE.byId[focus]){
    setTimeout(()=>rexOpenJob(focus), 200);
  }
}

(async()=>{
  await ensureLanAuthSession();
  await loadCapabilities(); await loadPrefs(); await loadVoices(); await loadExpansion();
  function floorFromLocation(){
    const q=new URLSearchParams(location.search);
    if(q.get('floor')) return q.get('floor');
    if(q.get('surface')) return q.get('surface');
    const hash=(location.hash||'').replace(/^#/, '');
    if(hash && hash!=='codec') return hash;
    const p=(location.pathname||'/').replace(/\/+$/,'') || '/';
    const map={
      '/war-room':'war-room','/dashboard':'dashboard','/intel':'intel',
      '/video-studio':'creative','/ha':'ops','/rex':'rex','/learning':'learning',
      '/creative':'creative','/ops':'ops','/reports':'reports','/dossiers':'dossiers',
      '/journal':'journal','/diary':'diary','/page-builder':'page-builder','/rooms':'rooms',
      '/relationships':'relationships','/emotion':'emotion','/command':'command',
      '/command-center':'command-center','/codec':'codec','/expansion':'command'
    };
    return map[p]||'';
  }
  window.addEventListener('popstate', ()=>{
    const kind=floorFromLocation();
    if(kind==='codec') showChat();
    else if(kind) showExpansionSurface(kind);
    else showHome();
  });
  if(location.search.includes('setup=1')) render();
  else if(location.search.includes('codec=1') || location.hash==='#codec' || floorFromLocation()==='codec') showChat();
  else if(location.search.includes('rex=1') || location.hash==='#rex') showRexBoard();
  else {
    const kind=floorFromLocation();
    if(kind) await showExpansionSurface(kind);
    else showHome();
  }
})();
