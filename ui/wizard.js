let state={
  step:0,scan:null,name:'Aria',features:['chat','memory','voice'],config:null,storage:null,
  conversation:null,voiceId:'voice_aria',autoSpeak:false,voices:[],capabilities:null,
  currentAudio:null,speakingMsg:null,recorder:null,recordingState:'MIC_READY',
  testMode:window.__OTACON_TEST_MODE__===true,codecMode:'idle',codecBooted:false,lastModel:null,
  view:'codec',agentId:'aria',roster:[],expansion:null
};
const labels=['Welcome','System Scan','Hardware Recommendation','Storage','Agent Setup','Features','Review','Finish'];
const CODEC_FALLBACK={idle:'/assets/aria/aria-idle.mp4',thinking:'/assets/aria/aria-thinking.mp4',talking:'/assets/aria/aria-talking.mp4'};

function currentAgentId(){
  if(state.agentId && state.agentId!=='agent_001') return state.agentId;
  if(state.roster&&state.roster.length) return state.roster[0].id||state.roster[0].agent_id||'aria';
  // Wizard / Lite default: Aria — never leave agent_001 on preview/setup paths.
  return 'aria';
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
function agentAsset(id, file){
  return `/assets/${id}/${file}?v=roster-art-2`;
}
function codecVideoFor(mode){
  const id=currentPortraitId();
  const m=mode||'idle';
  return agentAsset(id, `${id}-${m}.mp4`);
}
function codecPortraitUrl(id){
  const aid=id||currentPortraitId();
  return agentAsset(aid, `${aid}.webp`);
}
function bindCodecVideoFallback(v){
  if(!v||v.dataset.boundPortraitFallback) return;
  v.dataset.boundPortraitFallback='1';
  v.addEventListener('error', ()=>{
    const id=currentPortraitId();
    const port=document.getElementById('port-active');
    if(!port) return;
    // Prefer this agent's still portrait over swapping to Aria's motion pack.
    if(!port.querySelector('img.codec-still')){
      const img=document.createElement('img');
      img.className='codec-still';
      img.alt=currentAgentName()||id;
      img.src=codecPortraitUrl(id);
      img.onerror=()=>{ img.src=agentAsset('aria','aria.webp'); };
      v.style.display='none';
      port.insertBefore(img, v);
    }
  });
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
        avatar:a.avatar||agentAsset(a.id||a.agent_id, `${a.id||a.agent_id}.webp`)
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

/** Honest hardware scan: never invent "no GPU" from a timed-out/failed request. */
async function loadHardwareScan(timeoutMs){
  const ms=timeoutMs==null?15000:timeoutMs;
  try{
    const data=await apiGet('/api/scan', ms);
    const hw=((data&&data.hardware&&data.hardware.hardware)||{});
    const det=hw.gpu_detection||(data&&data.hardware&&data.hardware.gpu_detection)||{};
    const status=String(det.status||'');
    const failed=status==='error'||status==='unavailable'||status==='skipped'||data.hardware&&data.hardware.scan_ok===false;
    return {
      ok:!failed,
      data:data,
      hardware:hw,
      gpu_detection:det,
      timed_out:false,
      error: failed?(det.message||'GPU detection unavailable — retry'):''
    };
  }catch(err){
    const timed=!!(err&&(err.name==='AbortError'||/aborted/i.test(String(err&&err.message||err))));
    return {
      ok:false,
      data:null,
      hardware:{},
      gpu_detection:{status:'unavailable',message:timed
        ?'GPU detection unavailable — scan timed out. Retry.'
        :('GPU detection unavailable — retry ('+String(err&&err.message||err)+')')},
      timed_out:timed,
      error:String(err&&err.message||err)
    };
  }
}

function formatGpuLine(scan){
  if(!scan||!scan.ok){
    const msg=(scan&&scan.gpu_detection&&scan.gpu_detection.message)||'GPU detection unavailable — retry';
    return msg;
  }
  const gpus=(scan.hardware&&scan.hardware.gpus)||[];
  const det=scan.gpu_detection||{};
  const st=String(det.status||'');
  if(gpus.length){
    return gpus.map(g=>{
      const name=g.model||g.name||'GPU';
      const vram=g.vram_gb?` · ${g.vram_gb} GB`:'';
      return `${name}${vram}`;
    }).join(' / ');
  }
  if(st==='none') return det.message||'No supported GPU detected';
  return det.message||'GPU detection unavailable — retry';
}

function renderMoodStrip(mood){
  const el=document.getElementById('codec-mood');
  if(!el) return;
  if(!mood||(!mood.line&&!(mood.elevated||[]).length)){
    el.innerHTML='<span class="muted">Mood offline</span>';
    return;
  }
  const chips=(mood.elevated||[]).slice(0,5).map(x=>{
    const id=escapeHtml(String(x.id||''));
    const hot=Number(x.value)>=0.6?' mood-hot':'';
    return `<span class="mood-chip${hot}" title="${id}">${id}</span>`;
  }).join('');
  el.innerHTML=`<div class="mood-line">${escapeHtml(mood.line||'Present.')}</div><div class="mood-chips">${chips}</div>`;
}

async function refreshCodecMood(){
  if(!state.roster||!state.roster.length) return;
  const aid=currentAgentId();
  try{
    const ctx=await apiGet('/api/expansion/agent/'+encodeURIComponent(aid)+'/context', 8000);
    if(ctx&&ctx.mood_summary) renderMoodStrip(ctx.mood_summary);
    else if(ctx&&ctx.emotion){
      renderMoodStrip({
        line:'',
        elevated:Object.keys(ctx.emotion.dimensions||{}).map(k=>({id:k,value:ctx.emotion.dimensions[k]}))
          .sort((a,b)=>b.value-a.value).slice(0,5)
      });
    }
  }catch(_e){
    const el=document.getElementById('codec-mood');
    if(el) el.innerHTML='<span class="muted">Mood unavailable</span>';
  }
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

/* WebAudio pack — boot sting, transmit thump, codec ring, ambient bed */
let _otAudioCtx=null,_otAmb=null;
function otAudio(){
  try{
    const AC=window.AudioContext||window.webkitAudioContext;
    if(!AC) return null;
    if(!_otAudioCtx) _otAudioCtx=new AC();
    if(_otAudioCtx.state==='suspended') _otAudioCtx.resume();
    return _otAudioCtx;
  }catch(_e){ return null; }
}
function otTone(ctx,type,f0,f1,t0,atk,dur,vol){
  const o=ctx.createOscillator(), g=ctx.createGain();
  o.type=type||'square';
  o.connect(g); g.connect(ctx.destination);
  o.frequency.setValueAtTime(f0, t0);
  if(f1 && f1!==f0) o.frequency.exponentialRampToValueAtTime(Math.max(40,f1), t0+dur);
  g.gain.setValueAtTime(0.0001, t0);
  g.gain.exponentialRampToValueAtTime(vol||0.04, t0+atk);
  g.gain.exponentialRampToValueAtTime(0.0001, t0+dur);
  o.start(t0); o.stop(t0+dur+0.03);
}
function otNoiseThump(ctx,t0,dur,vol){
  const n=Math.floor(ctx.sampleRate*dur);
  const buf=ctx.createBuffer(1,n,ctx.sampleRate);
  const d=buf.getChannelData(0);
  for(let i=0;i<n;i++) d[i]=(Math.random()*2-1)*Math.pow(1-i/n,2.4);
  const src=ctx.createBufferSource(), g=ctx.createGain(), f=ctx.createBiquadFilter();
  f.type='lowpass'; f.frequency.value=180;
  src.buffer=buf; src.connect(f); f.connect(g); g.connect(ctx.destination);
  g.gain.setValueAtTime(vol||0.12, t0);
  g.gain.exponentialRampToValueAtTime(0.0001, t0+dur);
  src.start(t0); src.stop(t0+dur+0.02);
}
function otAmbientStart(){
  const ctx=otAudio();
  if(!ctx||_otAmb) return;
  try{
    const master=ctx.createGain();
    master.gain.value=0.012;
    master.connect(ctx.destination);
    const mk=(freq,type,detune)=>{
      const o=ctx.createOscillator(), g=ctx.createGain(), lfo=ctx.createOscillator(), lg=ctx.createGain();
      o.type=type; o.frequency.value=freq; o.detune.value=detune||0;
      g.gain.value=0.35;
      lfo.frequency.value=0.07+Math.random()*0.05;
      lg.gain.value=0.12;
      lfo.connect(lg); lg.connect(g.gain);
      o.connect(g); g.connect(master);
      o.start(); lfo.start();
      return [o,lfo];
    };
    _otAmb={master, nodes:[...mk(55,'sine',0),...mk(82.5,'triangle',6),...mk(110,'sine',-4)]};
  }catch(_e){ _otAmb=null; }
}
function otAmbientStop(){
  if(!_otAmb) return;
  try{
    _otAmb.nodes.forEach(n=>{ try{n.stop();}catch(_e){} });
    _otAmb.master.disconnect();
  }catch(_e){}
  _otAmb=null;
}
function otSfx(kind){
  try{
    const ctx=otAudio();
    if(!ctx) return;
    const t=ctx.currentTime;
    if(kind==='boot'){
      [[196,0],[247,0.07],[294,0.14],[392,0.22],[523,0.32]].forEach(([f,off])=>{
        otTone(ctx,'square',f,f*1.02,t+off,0.02,0.16,0.035);
      });
      otTone(ctx,'sawtooth',98,196,t,0.04,0.45,0.02);
      return;
    }
    if(kind==='transmit'){
      otNoiseThump(ctx,t,0.14,0.14);
      otTone(ctx,'square',620,180,t+0.02,0.01,0.1,0.05);
      return;
    }
    if(kind==='switch'||kind==='ring'){
      // Codec agent-switch ring
      otTone(ctx,'square',880,880,t,0.01,0.08,0.05);
      otTone(ctx,'square',660,660,t+0.1,0.01,0.1,0.045);
      otTone(ctx,'triangle',1320,990,t+0.22,0.01,0.16,0.03);
      return;
    }
    if(kind==='error'){
      otTone(ctx,'sawtooth',180,70,t,0.02,0.22,0.055);
      return;
    }
    if(kind==='ok'){
      otTone(ctx,'square',440,660,t,0.02,0.12,0.04);
      otTone(ctx,'triangle',660,880,t+0.08,0.02,0.14,0.03);
      return;
    }
    // click default
    otTone(ctx,'square',720,380,t,0.008,0.05,0.028);
  }catch(_e){}
}
function hudGauge(label, pct, tone){
  const p=Math.max(0,Math.min(100,Number(pct)||0));
  const r=34, c=40, circ=2*Math.PI*r;
  const dash=circ*((100-p)/100);
  const col=tone==='warn'?'var(--ot-amber)':(tone==='bad'?'var(--ot-magenta)':'var(--ot-cyan)');
  return `<div class="hud-gauge" title="${escapeHtml(label)}">
    <svg viewBox="0 0 80 80" aria-hidden="true">
      <circle class="g-bg" cx="${c}" cy="${c}" r="${r}"/>
      <circle class="g-fg" cx="${c}" cy="${c}" r="${r}" style="stroke:${col};stroke-dasharray:${circ};stroke-dashoffset:${dash}"/>
    </svg>
    <b>${p|0}</b><span>${escapeHtml(label)}</span>
  </div>`;
}
function hudRadarHtml(threat){
  const blips=[[38,22],[62,48],[28,58],[70,28],[48,70]].map((xy,i)=>
    `<i class="blip" style="left:${xy[0]}%;top:${xy[1]}%;animation-delay:${i*0.4}s"></i>`).join('');
  return `<div class="hud-radar ${threat?'threat':''}">
    <div class="radar-face"><div class="radar-sweep"></div>${blips}</div>
    <div class="radar-lbl">SCAN · ${threat?'AMBER':'CLEAR'}</div>
  </div>`;
}
function hudSeqHtml(){
  const bars=Array.from({length:16},(_,i)=>`<i style="--h:${30+((i*37)%70)}%;animation-delay:${(i%8)*0.08}s"></i>`).join('');
  return `<div class="hud-seq" aria-hidden="true">${bars}</div>`;
}
function hudTeleHtml(lines){
  const row=(lines||[]).map(l=>`<span>${escapeHtml(l)}</span>`).join('');
  return `<div class="hud-tele"><div class="hud-tele-track">${row}${row}</div></div>`;
}
async function linkOperatorCam(){
  otSfx('click');
  const port=document.getElementById('port-operator');
  if(!port) return;
  try{
    if(window.__opCamStream){
      window.__opCamStream.getTracks().forEach(t=>t.stop());
      window.__opCamStream=null;
    }
    const stream=await navigator.mediaDevices.getUserMedia({video:{facingMode:'user',width:{ideal:480}},audio:false});
    window.__opCamStream=stream;
    port.innerHTML=`<video id="opCam" autoplay playsinline muted></video><div class="codec-port-crt"></div><div class="codec-port-lbl">OPERATOR</div>`;
    const v=document.getElementById('opCam');
    if(v){ v.srcObject=stream; }
    otSfx('ok');
  }catch(_e){
    port.innerHTML=`<div class="op-port-fill op-port-live">
      <div class="op-sil"></div>
      <span>OPERATOR · LINK DENIED</span>
      <button type="button" class="op-cam-btn" onclick="linkOperatorCam()">Retry camera</button>
    </div><div class="codec-port-crt"></div><div class="codec-port-lbl">YOU</div>`;
    otSfx('error');
  }
}
function operatorPortHtml(){
  return `<div class="op-port-fill op-port-live">
    <div class="op-sil" aria-hidden="true"></div>
    <div class="op-scan"></div>
    <span>OPERATOR · STANDBY</span>
    <button type="button" class="op-cam-btn" onclick="linkOperatorCam()">Link camera</button>
  </div>
  <div class="codec-port-crt"></div>
  <div class="codec-port-lbl">YOU</div>`;
}

function agentRoomKind(a){
  const id=a.id||a.agent_id||'';
  const fromRoute=roomKindFromRoute(a.room||a.room_route||'');
  if(fromRoute && fromRoute!=='codec') return fromRoute;
  return ({aria:'command',vector:'war-room',ledger:'intel',muse:'creative',sentry:'ops'})[id]||'codec';
}
function openAgentRoom(id){
  otSfx('switch');
  const a=(state.roster||[]).find(x=>(x.id||x.agent_id)===id)||{id};
  selectExpansionAgent(id);
  const kind=agentRoomKind(a);
  if(kind==='codec') showChat();
  else showExpansionSurface(kind==='creative'?'creative':kind);
}
function hudMeter(label, pct, value){
  const p=Math.max(0,Math.min(100,Number(pct)||0));
  return `<div class="hud-meter"><div class="hud-meter-h"><span>${escapeHtml(label)}</span><span>${escapeHtml(String(value||(p|0)+'%'))}</span></div>
    <div class="hud-meter-track"><i style="width:${p}%"></i></div></div>`;
}
function hudLed(label, ok, warn){
  const cls=ok?'ok':(warn?'warn':'bad');
  return `<div class="hud-led ${cls}"><b></b><span>${escapeHtml(label)}</span></div>`;
}
function scanMeterRows(scanPack){
  const pack=scanPack||{};
  const h=pack.hardware||{};
  const ram=Number(h.ram_gb||0);
  const free=Number(h.free_storage_gb||0);
  const gpu=Array.isArray(h.gpus)&&h.gpus[0]?h.gpus[0]:null;
  const cpuCores=h.cpu&&h.cpu.cores?Number(h.cpu.cores):0;
  return {
    cpu: hudMeter('CPU', cpuCores?Math.min(100,cpuCores*8):12, cpuCores?cpuCores+' cores':'—'),
    ram: hudMeter('RAM', ram?Math.min(100,Math.round((ram/64)*100)):8, ram?ram+' GB':'—'),
    disk: hudMeter('DISK', free?Math.min(100,Math.round((free/1000)*100)):8, free?Math.round(free)+' GB free':'—'),
    gpu: hudMeter('GPU', gpu?Math.min(100,Math.round(((gpu.vram_gb||0)/24)*100)):(pack.ok?6:0),
      gpu?(gpu.model||'GPU')+(gpu.vram_gb?(' · '+gpu.vram_gb+' GB'):''):(pack.ok?'none':'scan…'))
  };
}

function resourceBarsHtml(scanOrPack){
  // Accept either raw /api/scan JSON or loadHardwareScan() pack.
  const pack=scanOrPack&&scanOrPack.hardware&&!scanOrPack.hardware.hardware
    ?scanOrPack
    :null;
  const data=pack?pack.data:scanOrPack;
  const h=pack? (pack.hardware||{}) : ((data&&data.hardware&&data.hardware.hardware)||{});
  const scanFailed=!!(pack&&!pack.ok);
  const ram=Number(h.ram_gb||0);
  const free=Number(h.free_storage_gb||0);
  const gpu=Array.isArray(h.gpus)&&h.gpus[0]?h.gpus[0]:null;
  const rows=[
    ['CPU', h.cpu&&h.cpu.cores?`${h.cpu.cores} cores`:(scanFailed?'scan failed':'—'), h.cpu&&h.cpu.cores?Math.min(100,h.cpu.cores*8):0],
    ['RAM', ram?`${ram} GB`:(scanFailed?'—':'—'), ram?Math.min(100, Math.round((ram/64)*100)):0],
    ['DISK', free?`${Math.round(free)} GB free`:'—', free?Math.min(100, Math.round((free/1000)*100)):0],
  ];
  if(gpu){
    rows.push(['GPU', `${gpu.model||'GPU'}${gpu.vram_gb?` · ${gpu.vram_gb} GB`:''}`, Math.min(100, Math.round(((gpu.vram_gb||0)/24)*100))]);
  }else if(scanFailed){
    rows.push(['GPU', 'detection unavailable — retry', 0]);
  }
  return rows.map(([k,v,pct])=>`<div class="home-res-item"><div class="lbl"><span>${k}</span><span>${escapeHtml(String(v))}</span></div><div class="home-res-bar"><i style="width:${pct}%"></i></div></div>`).join('');
}

async function showHome(){
  state.view='home';
  setBodyMode('home');
  await ensureLanAuthSession();
  await loadCapabilities();
  await loadExpansion();
  let scanPack=await loadHardwareScan(15000);
  state.scan=scanPack.data;
  state.scanStatus=scanPack;
  const chatOk=capReady('chat'), ttsOk=capReady('tts');
  const vtStatus=capStatus('voice_trainer');
  const vtOk=vtStatus==='ready';
  const vtOffline=vtStatus==='offline';
  const videoStatus=capStatus('video');
  const videoOk=videoStatus==='ready';
  const expOn=!!(state.expansion&&state.expansion.enabled);
  const expEntitled=!!(state.expansion&&(state.expansion.expansion_entitled||state.expansion.surfaces_ready||expOn));
  const model=(state.capabilities&&state.capabilities.llm_model)||'—';
  const gpuHomeLine=formatGpuLine(scanPack);
  const brandLine=expOn?'Otaconskeep · Expansion':'Otaconskeep · Lite';
  const footLine=expOn
    ?'Otaconskeep Expansion · Designed &amp; Engineered by Antonio G. Garcia · discord.gg/cZDeqECzX'
    :'Otaconskeep Lite · Designed &amp; Engineered by Antonio G. Garcia · discord.gg/cZDeqECzX';
  const meters=scanMeterRows(scanPack);
  const vtLed=vtOk?'Genome live':(vtOffline?'Genome offline — start':(expEntitled?'Genome setup':'Genome locked'));
  const vsLed=videoOk?'Studio READY':(videoStatus==='limited'?'Studio limited':'Studio needs Comfy');
  const ariaLine=expOn
    ?'Priority channels are live. Open Codec to talk to the roster, Genome for voice training, Studio when Comfy is up.'
    :'Core deck online. Expansion unlocks the five-agent roster and premium rooms.';
  const threat=!chatOk||!ttsOk||(expOn&&!videoOk);
  const hScan=(scanPack&&scanPack.hardware)||{};
  const cpuCoresN=hScan.cpu&&hScan.cpu.cores?Number(hScan.cpu.cores):0;
  const ramGbN=Number(hScan.ram_gb||0);
  const instruments=`<div class="hud-instruments">
    ${hudRadarHtml(threat)}
    <div class="hud-gauge-row">
      ${hudGauge('CORE', chatOk?88:22, chatOk?'':'bad')}
      ${hudGauge('VOICE', ttsOk?76:18, ttsOk?'':'warn')}
      ${hudGauge('LOAD', cpuCoresN?Math.min(100,cpuCoresN*8):12, '')}
      ${hudGauge('MEM', ramGbN?Math.min(100,Math.round((ramGbN/64)*100)):8, '')}
    </div>
    ${hudSeqHtml()}
    ${hudTeleHtml([
      'LINK '+ (chatOk?'UP':'DOWN'),
      'TTS '+ (ttsOk?'READY':'WAIT'),
      'GENOME '+ (vtOk?'LIVE':(vtOffline?'START':'SETUP')),
      'STUDIO '+ (videoOk?'READY':'LIMITED'),
      'MODEL '+ String(model).slice(0,24),
      gpuHomeLine.slice(0,28)
    ])}
  </div>`;

  const agentStrip=(state.roster||[]).map(a=>{
    const id=a.id||a.agent_id;
    const room=a.room_title||a.room||agentRoomKind(a);
    const img=agentAsset(id, `${id}.webp`);
    return `<button type="button" class="hud-agent" onclick="openAgentRoom('${escapeHtml(id)}')">
      <img src="${img}" alt="" loading="eager" decoding="async" onerror="this.onerror=null;this.src='${agentAsset('aria','aria.webp')}'">
      <div><div class="n">${escapeHtml(a.display_name||id)}</div><div class="r">${escapeHtml(String(room))}</div></div>
      <span class="mood" title="mood"></span>
    </button>`;
  }).join('')||'<p class="muted">No roster yet.</p>';

  const primaryOps=expOn?`
  <section class="hud-ops">
    <h3>Priority surfaces</h3>
    <div class="hud-ops-grid">
      <button type="button" class="svc" onclick="otSfx('click');${vtOk?'openVoiceTrainer()':(vtOffline?'startVoiceTrainer()':'showGenomeSetup()')}">
        <div class="svc-top"><div class="svc-ico">GN</div><div class="svc-name">Genome</div></div>
        <p class="svc-desc">Voice Trainer + Piper voices — Expansion premium.</p>
        <span class="svc-pill ${vtOk?'ok':'warn'}">${vtOk?'OPEN':(vtOffline?'START':'SETUP')}</span>
      </button>
      <button type="button" class="svc" onclick="otSfx('click');showVideoStudioSetup()">
        <div class="svc-top"><div class="svc-ico">VS</div><div class="svc-name">Video Studio</div></div>
        <p class="svc-desc">Muse / ComfyUI — Aria will walk you through it.</p>
        <span class="svc-pill ${videoOk?'ok':'warn'}">${videoOk?'READY':'SETUP'}</span>
      </button>
      <button type="button" class="svc" onclick="otSfx('click');showExpansionSurface('war-room')">
        <div class="svc-top"><div class="svc-ico">WR</div><div class="svc-name">War Room</div></div>
        <p class="svc-desc">Vector ops board — jobs, failures, threat strip.</p>
        <span class="svc-pill ok">ENTER</span>
      </button>
      <button type="button" class="svc" onclick="otSfx('click');showExpansionSurface('command')">
        <div class="svc-top"><div class="svc-ico">CMD</div><div class="svc-name">Aria Command</div></div>
        <p class="svc-desc">Coordination floor — roster workload + alerts.</p>
        <span class="svc-pill ok">ENTER</span>
      </button>
    </div>
  </section>
  <section class="home-group">
    <h2 class="home-group-title">More rooms</h2>
    <div class="home-grid compact">
      <button type="button" class="svc" onclick="otSfx('click');showExpansionSurface('rex')"><div class="svc-top"><div class="svc-ico">REX</div><div class="svc-name">REX</div></div><p class="svc-desc">Autonomy loop</p><span class="svc-pill ok">ENTER</span></button>
      <button type="button" class="svc" onclick="otSfx('click');showExpansionSurface('intel')"><div class="svc-top"><div class="svc-ico">INT</div><div class="svc-name">Intel</div></div><p class="svc-desc">Ledger continuity</p><span class="svc-pill ok">ENTER</span></button>
      <button type="button" class="svc" onclick="otSfx('click');showExpansionSurface('emotion')"><div class="svc-top"><div class="svc-ico">EM</div><div class="svc-name">Emotion</div></div><p class="svc-desc">Affect board</p><span class="svc-pill ok">ENTER</span></button>
      <button type="button" class="svc" onclick="otSfx('click');showExpansionSurface('dossiers')"><div class="svc-top"><div class="svc-ico">DOS</div><div class="svc-name">Dossiers</div></div><p class="svc-desc">Memory lives here</p><span class="svc-pill ok">ENTER</span></button>
      <button type="button" class="svc" onclick="otSfx('click');showExpansionSurface('diary')"><div class="svc-top"><div class="svc-ico">DRY</div><div class="svc-name">Diary</div></div><p class="svc-desc">What it meant</p><span class="svc-pill ok">ENTER</span></button>
      <button type="button" class="svc" onclick="otSfx('click');showExpansionSurface('reports')"><div class="svc-top"><div class="svc-ico">RPT</div><div class="svc-name">Reports</div></div><p class="svc-desc">Live state</p><span class="svc-pill ok">ENTER</span></button>
      <button type="button" class="svc" onclick="otSfx('click');showExpansionSurface('ops')"><div class="svc-top"><div class="svc-ico">OPS</div><div class="svc-name">Ops</div></div><p class="svc-desc">Sentry</p><span class="svc-pill ok">ENTER</span></button>
      <button type="button" class="svc" onclick="otSfx('click');render()"><div class="svc-top"><div class="svc-ico">SU</div><div class="svc-name">Setup</div></div><p class="svc-desc">First-run wizard</p><span class="svc-pill">WIZARD</span></button>
    </div>
  </section>`:`
  <section class="hud-ops">
    <h3>Core surfaces</h3>
    <div class="hud-ops-grid">
      <button type="button" class="svc" onclick="otSfx('click');showChat()"><div class="svc-top"><div class="svc-ico">CC</div><div class="svc-name">Codec</div></div><p class="svc-desc">Talk to Aria</p><span class="svc-pill ${chatOk?'ok':'warn'}">${chatOk?'ONLINE':'DOWN'}</span></button>
      <button type="button" class="svc" onclick="otSfx('click');render()"><div class="svc-top"><div class="svc-ico">SU</div><div class="svc-name">Setup</div></div><p class="svc-desc">Hardware + voice</p><span class="svc-pill">WIZARD</span></button>
    </div>
  </section>`;

  appRoot().innerHTML=`<div class="home hud">
  <header class="home-header">
    <div>
      <p class="home-kicker">${brandLine}</p>
      <h1 class="home-greeting">Command Deck</h1>
    </div>
    <div class="home-meta">
      <div class="home-datetime" id="homeClock">${escapeHtml(formatNow())}</div>
    </div>
  </header>

  <div class="hud-deck">
    <aside class="hud-rail">
      <h3>Systems</h3>
      ${meters.cpu}${meters.ram}${meters.gpu}${meters.disk}
      ${hudLed('Chat / Ollama', chatOk, !chatOk)}
      ${hudLed('TTS / Piper', ttsOk, !ttsOk)}
      ${hudLed(vtLed, vtOk, !vtOk)}
      ${hudLed(vsLed, videoOk, !videoOk)}
      <p class="muted" style="font-size:9px;margin-top:10px;letter-spacing:.06em">GPU ${escapeHtml(gpuHomeLine)} · model ${escapeHtml(String(model))}</p>
    </aside>
    <main class="hud-center">
      <div class="hud-hero">
        <img src="${agentAsset('aria','aria.webp')}" alt="Aria">
        <div>
          <p class="sub">Aria // Command</p>
          <p class="line">${escapeHtml(ariaLine)}</p>
          <div class="hud-cta-row">
            <button type="button" class="hud-cta primary" onclick="otSfx('transmit');showChat()">Open Codec</button>
            ${expOn?`<button type="button" class="hud-cta" onclick="otSfx('click');${vtOk?'openVoiceTrainer()':(vtOffline?'startVoiceTrainer()':'showGenomeSetup()')}">Genome</button>
            <button type="button" class="hud-cta warn" onclick="otSfx('click');showVideoStudioSetup()">Studio</button>`:''}
          </div>
        </div>
      </div>
      ${instruments}
    </main>
    <aside class="hud-agents">
      <h3>${expOn?'Roster':'Agent'}</h3>
      ${agentStrip}
    </aside>
  </div>

  ${primaryOps}
  <p class="home-foot">${footLine}</p>
</div>`;

  if(window.__homeClock) clearInterval(window.__homeClock);
  window.__homeClock=setInterval(()=>{
    const el=document.getElementById('homeClock'); if(el) el.textContent=formatNow();
  },1000);

  if(!document.getElementById('ot-boot') && !sessionStorage.getItem('ot_boot_done')){
    otSfx('boot');
    const boot=document.createElement('div');
    boot.id='ot-boot';
    boot.innerHTML=`<div class="frame"><div class="kicker">Otaconskeep</div><div class="title">Command Deck</div><div class="sub">Booting ${expOn?'Expansion':'Lite'} HUD…</div></div>`;
    document.body.appendChild(boot);
    setTimeout(()=>{ boot.classList.add('done'); sessionStorage.setItem('ot_boot_done','1'); setTimeout(()=>boot.remove(),700); },900);
  }
  otAmbientStart();
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
  if(s===2){
    const pack=state.scanStatus||{};
    const scanOk=pack.ok!==false && state.scan && state.scan.hardware;
    if(!scanOk||!state.scan||!state.scan.hardware||!state.scan.hardware.hardware){
      const msg=(pack.gpu_detection&&pack.gpu_detection.message)||'GPU detection unavailable — retry';
      page.innerHTML=`<div class=card>${escapeHtml(msg)}</div>
        <p class=muted>Hardware scan did not complete. Do not treat this as “no NVIDIA GPU.”</p>
        <button onclick="scan()">Retry Scan</button>
        <button class=ghost onclick="next()">Continue without GPU proof</button>`;
    }else{
      let h=state.scan.hardware.hardware,g=state.scan.hardware.gpu_roles||{},det=h.gpu_detection||{};
      const detStatus=String(det.status||'');
      const gpuBlock=h.gpus&&h.gpus.length
        ? h.gpus.map(x=>`<div class=card>${escapeHtml(x.model)} — ${x.vram_gb?x.vram_gb+' GB VRAM':'VRAM n/a'} — ${escapeHtml(x.capability||'')}</div>`).join('')
        : (detStatus==='error'||detStatus==='unavailable'||detStatus==='skipped'
          ? `<div class=card>${escapeHtml(det.message||'GPU detection unavailable — retry')}</div>`
          : `<div class=card>${escapeHtml(det.message||'No supported GPU detected')}</div>`);
      page.innerHTML=`<div class=card>System: ${escapeHtml(h.os||'')}<br>CPU: ${escapeHtml((h.cpu&&h.cpu.model)||'')} (${(h.cpu&&h.cpu.cores)||'?'} cores)<br>Memory: ${h.ram_gb||0} GB</div>`
        +gpuBlock
        +`<p class=muted>Recommended primary: ${escapeHtml(String(g.primary_gpu||'—'))}</p>
         <button onclick="next()">Use Recommended Setup</button>
         <button class=ghost onclick="scan()">Rescan</button>`;
    }
  }
  if(s===3){
    const vols=(state.scan&&state.scan.storage)||[];
    let v=vols.find(x=>x.recommended)||vols[0]||{};
    page.innerHTML=`<div class=card><b>Recommended storage</b><br>${escapeHtml(v.path||'Unavailable')}<br>${v.free_gb||0} GB free</div><button onclick="next()">Use Recommended Storage</button>`;
  }
  if(s===4){ page.innerHTML=agentSetupHtml(); updateSetupAvatar(); }
  if(s===5) page.innerHTML=featuresHtml()+'<button onclick="setFeatures()">Continue</button>';
  if(s===6) page.innerHTML=`<div class=card>Agent: ${escapeHtml(state.name)}<br>Voice: ${escapeHtml(voiceLabel(state.voiceId))}<br>Features: ${escapeHtml(state.features.join(', '))}<br>Storage: ${escapeHtml(((state.scan&&state.scan.storage||[]).find(x=>x.recommended)||(state.scan&&state.scan.storage||[])[0]||{}).path||'Unavailable')}</div><button onclick="build()">Create Configuration</button>`;
  if(s===7) page.innerHTML=`<p>${state.name} is configured.</p><p class=muted>Open Codec to talk — portrait stays in the right port, messages are text-only below.</p><div class=card>${state.config?.saved||''}</div><button onclick="showChat()">Open Codec</button>`;
}

function next(){state.step++;render()}
async function scan(){
  const page=document.getElementById('page');
  if(page) page.innerHTML='<p class=muted>Scanning hardware…</p>';
  const pack=await loadHardwareScan(15000);
  state.scanStatus=pack;
  state.scan=pack.data;
  if(!pack.ok||!pack.data){
    // Preserve failure — do NOT substitute a fake CPU-only hardware profile.
    state.scan=null;
    if(page){
      page.innerHTML=`<div class=card>${escapeHtml((pack.gpu_detection&&pack.gpu_detection.message)||'GPU detection unavailable — retry')}</div>
        <p class=muted>Scan failed or timed out. This is not proof that no NVIDIA GPU exists.</p>
        <button onclick="scan()">Retry Scan</button>
        <button class=ghost onclick="state.step=2;render()">Continue (detection unproven)</button>`;
    }
    return;
  }
  state.storage=(state.scan.storage||[]).find(x=>x.recommended)||(state.scan.storage||[])[0]||null;
  state.step=2; render();
}
async function setName(){
  state.name=document.getElementById('name').value.trim()||'Aria';
  let sel=document.getElementById('voiceSelect'); if(sel) state.voiceId=sel.value;
  await api('/api/agent/voice',{agent_id:currentAgentId(),display_name:state.name,voice_id:state.voiceId});
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
    let r=await api('/api/preview_voice',{agent:{id:currentAgentId(),display_name:agentName,voice_id:voiceId},text});
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
  bindCodecVideoFallback(v);
  const still=port&&port.querySelector('img.codec-still');
  if(still){ still.remove(); v.style.display=''; }
  const src=codecVideoFor(mode);
  const cur=v.getAttribute('src')||'';
  v.setAttribute('poster', codecPortraitUrl());
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
  otSfx('boot');
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
  let scanPack=await loadHardwareScan(15000);
  state.scan=scanPack.data;
  state.scanStatus=scanPack;
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
  const gpuLine=formatGpuLine(scanPack);
  const vtStatus=capStatus('voice_trainer');
  const vtOk=vtStatus==='ready';
  const vtOffline=vtStatus==='offline';
  const voiceOpts=(state.voices||[]).map(v=>`<option value="${v.id}" ${v.id===state.voiceId?'selected':''}>${v.display_name}</option>`).join('');
  const roster=state.roster&&state.roster.length?state.roster:[{id:aid,display_name:currentAgentName()}];
  const agentBtns=roster.map(a=>{
    const id=a.id||a.agent_id;
    const active=id===aid?' codec-ai-active':'';
    return `<button type=button class="codec-ai-btn${active}" title="${escapeHtml(a.display_name||id)}" onclick="selectExpansionAgent('${escapeHtml(id)}')">${escapeHtml(String(a.display_name||id).toUpperCase())}</button>`;
  }).join('');
  const agentName=currentAgentName();
  const portraitAgent=currentPortraitId();
  const idleSrc=agentAsset(portraitAgent, `${portraitAgent}-idle.mp4`);
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
      <div id="codec-mood" class="codec-mood"><span class="muted">Loading mood…</span></div>
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
        <div id="codec-bar">OTACON CODEC · ${state.roster.length?'EXPANSION':'LITE'} · TRANSMISSION LOCAL · TACTICAL HUD</div>
        <div id="codec-header">
          <div class="codec-inner code-border-inner">
            <div class="codec-port port-left" id="port-operator">
              ${operatorPortHtml()}
            </div>
            <div class="codec-mid">
              <div class="codec-title">CODEC</div>
              <div class="codec-freq-line">FREQ&nbsp;<span id="codec-freq">140.85</span>&nbsp;MHz</div>
              <div class="codec-wave" aria-hidden="true"><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i></div>
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
              <video id=codecVideo autoplay loop muted playsinline poster="${codecPortraitUrl(portraitAgent)}" src="${idleSrc}"></video>
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
      <div class="cc-rack">
        <div class="cc-rack-h">LINK · INSTRUMENTS</div>
        <div class="cc-led-bank">
          <div class="cc-led ${chatOk?'on':''}"><b></b><span>CHAT</span><em>${chatOk?'RDY':'DN'}</em></div>
          <div class="cc-led ${ttsOk?'on':''}"><b></b><span>VOICE</span><em>${ttsOk?'RDY':'DN'}</em></div>
          <div class="cc-led ${sttOk?'on':''}"><b></b><span>MIC</span><em>${sttOk?'RDY':'OFF'}</em></div>
          <div class="cc-led ${vtOk?'on':(vtOffline?'warn':'')}"><b></b><span>GNM</span><em>${vtOk?'LIVE':(vtOffline?'STRT':'—')}</em></div>
        </div>
        <div class="cc-mini-meters">
          <div class="cc-mm"><span>TX</span><i style="width:${chatOk?72:12}%"></i></div>
          <div class="cc-mm"><span>RX</span><i style="width:${ttsOk?64:10}%"></i></div>
          <div class="cc-mm"><span>CPU</span><i id="ccCpuBar" style="width:40%"></i></div>
        </div>
        <div class="cc-kv tight">
          <span class=muted>MODEL</span><b id=codecModel>${escapeHtml(String(model))}</b>
          <span class=muted>GPU</span><b>${escapeHtml(gpuLine)}</b>
          <span class=muted>STATE</span><b id=codecStatus>IDLE</b>
        </div>
      </div>
      <div class="cc-rack">
        <div class="cc-rack-h">VOICE · CHANNEL</div>
        <div class="cc-knob-row">
          <label class="cc-knob"><span>PROFILE</span>
            <select id=chatVoice onchange="assignVoice(this.value)">${voiceOpts}</select>
          </label>
          <label class="cc-tog"><input type=checkbox id=autoSpeak ${state.autoSpeak?'checked':''} onchange="setAutoSpeak(this.checked)"><span>AUTO SPEAK</span></label>
        </div>
        <button type=button class="cc-btn" onclick="otSfx('click');previewSelectedVoiceChat()">Preview</button>
        <p class=muted id=sidePreviewStatus style="font-size:10px;margin-top:8px;white-space:pre-wrap"></p>
      </div>
      <div class="cc-rack">
        <div class="cc-rack-h">THREADS</div>
        <div id=conversation-list></div>
        <div class="cc-links"><button type=button class="cc-btn" onclick="otSfx('click');newConversation()">New Thread</button></div>
      </div>
      <div class="cc-rack" id=memory-panel>
        <div class="cc-rack-h">MEMORY · ${escapeHtml(String(agentName).toUpperCase())}</div>
        <div id=memories></div>
        <input id=memory placeholder="Add a memory">
        <button type=button class="cc-btn" onclick="addMemory()" style="margin-top:8px">Save Memory</button>
      </div>
      <div class="cc-rack">
        <div class="cc-rack-h">GENOME</div>
        <p class=muted style="font-size:10px;margin:0 0 8px">${vtOk?'Voice Trainer on :8765.':vtOffline?'Installed — start UI.':'Open Setup to install/start.'}</p>
        ${vtOk?'<button type=button class="cc-btn" onclick="otSfx(\'click\');openVoiceTrainer()">Open :8765</button>':(vtOffline?'<button type=button class="cc-btn" onclick="otSfx(\'ok\');startVoiceTrainer()">Start Genome</button>':'<button type=button class="cc-btn" onclick="otSfx(\'click\');showGenomeSetup()">Setup Genome</button>')}
      </div>
    </aside>
  </div>
</div>`;

  await refreshConversationList();
  if(state.conversation) await openConversation(state.conversation);
  try{ await loadMemories(); }catch(e){}
  setCodecMode('idle');
  bindCodecVideoFallback(document.getElementById('codecVideo'));
  bootCodecOnce();
  refreshCodecMood();
  otAmbientStart();
  if(window.__codecFreqTimer) clearInterval(window.__codecFreqTimer);
  window.__codecFreqTimer=setInterval(animateFreq,900);
  const inp=document.getElementById('chat-inp'); if(inp) inp.focus();
}

async function selectExpansionAgent(id){
  if(!id) return;
  const same=id===state.agentId;
  if(!same) otSfx('ring');
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
  const url=(state.capabilities&&state.capabilities.voice_trainer_url)||'';
  if(!url || capStatus('voice_trainer')!=='ready'){
    showGenomeSetup();
    return;
  }
  try{
    const probe=await fetch(url,{mode:'no-cors',cache:'no-store'});
    void probe;
  }catch(_e){}
  window.open(url,'_blank','noopener');
}
async function startVoiceTrainer(){
  try{
    const r=await api('/api/expansion/voice-trainer/start',{});
    await loadCapabilities();
    if(r&&r.ok&&(r.data&&r.data.ok)){
      if(capStatus('voice_trainer')==='ready') openVoiceTrainer();
      else alert('Genome start requested — wait a second and open Voice Trainer again.');
    }else{
      showGenomeSetup();
    }
  }catch(e){
    showGenomeSetup();
  }
}
function btnHome(){
  return `<button type="button" class="hud-cta" onclick="showHome()">Home</button>`;
}
async function showGenomeSetup(){
  state.view='home';
  setBodyMode('home');
  await loadCapabilities();
  otSfx('click');
  const note=(state.capabilities&&state.capabilities.voice_trainer_note)||'';
  const st=capStatus('voice_trainer');
  const path=(state.capabilities&&state.capabilities.voice_trainer_path)||'~/otacon-voice-trainer';
  appRoot().innerHTML=`<div class="home">
  <header class="home-header"><div><p class="home-kicker">Expansion · Genome</p><h1 class="home-greeting">Voice Trainer</h1></div>
  <div class="home-meta">${btnHome()}</div></header>
  <section class="home-group">
    <div class="guide-aria">
      <img src="/assets/aria/aria.webp" alt="Aria">
      <div>
        <p class="sub" style="letter-spacing:.14em;text-transform:uppercase;color:var(--ot-cyan);font-size:10px;margin:0 0 8px">Aria // guiding</p>
        <p style="margin:0 0 10px;line-height:1.5">You already have Expansion. Genome is the voice lab — it needs a GPU path in WSL, then a short install. Piper TTS for Codec still works without Genome.</p>
        <p><b>Status:</b> ${escapeHtml(st)}</p>
        <p class="muted">${escapeHtml(note)}</p>
      </div>
    </div>
    <ol class="guide-steps">
      <li><b>Check Windows GPU</b> — open a Windows terminal and run <code>nvidia-smi</code>. If that works but WSL fails, download <code>Fix-Otacon-GPU.bat</code> from the Otaconskeep downloads page, run it, then reopen Ubuntu.</li>
      <li><b>Check WSL GPU</b> — in Ubuntu: <code>nvidia-smi</code>. You want a GPU name, not an error.</li>
      <li><b>Install Genome</b> — paste this in Ubuntu:<br><code>curl -fsSL https://raw.githubusercontent.com/Otaconskeep/otacon-voice-trainer/main/install_voice_trainer.sh | bash</code></li>
      <li><b>Or</b> re-run Expansion Setup on this PC after GPU is visible — Expansion installs Genome automatically when NVIDIA works.</li>
      <li><b>Start the UI</b> — click Start Genome below so <code>http://127.0.0.1:8765/</code> answers.</li>
    </ol>
    <p class="muted" style="margin-top:10px">Install path: <code>${escapeHtml(path)}</code></p>
    <div class="hud-cta-row" style="margin-top:14px">
      <button type="button" class="hud-cta primary" onclick="otSfx('ok');startVoiceTrainer()">Start Genome</button>
      <button type="button" class="hud-cta" onclick="otSfx('transmit');openVoiceTrainer()">Open :8765</button>
      <button type="button" class="hud-cta" onclick="showHome()">Back to deck</button>
    </div>
  </section>
</div>`;
}
async function showVideoStudioSetup(){
  state.view='home';
  setBodyMode('home');
  await loadCapabilities();
  otSfx('click');
  let detect={found:false,endpoint:'',detail:'Detecting…',candidates:[]};
  try{ detect=await apiGet('/api/expansion/video-studio/detect', 6000); }catch(_e){}
  const detail=(state.capabilities&&state.capabilities.video_detail)||'';
  const st=capStatus('video');
  const ep=(detect&&detect.endpoint)||(state.capabilities&&state.capabilities.video_endpoint)||'http://127.0.0.1:8188';
  const found=!!(detect&&detect.found);
  const foundBlock=found
    ? `<div class="card" style="margin:12px 0;padding:12px;border:1px solid rgba(46,230,214,.35)">
        <p style="margin:0 0 8px"><b>Found ComfyUI</b> at <code>${escapeHtml(detect.endpoint)}</code></p>
        <p class="muted" style="margin:0 0 10px">${escapeHtml(detect.detail||'')}</p>
        <button type="button" class="hud-cta primary" onclick="otSfx('ok');useDetectedComfy('${escapeHtml(detect.endpoint)}')">Use this → READY</button>
      </div>`
    : `<div class="card" style="margin:12px 0;padding:12px;border:1px solid rgba(245,165,36,.35)">
        <p style="margin:0 0 8px"><b>No Comfy on :8188 / :8199</b></p>
        <p class="muted" style="margin:0">${escapeHtml((detect&&detect.detail)||'Not answering yet.')}</p>
      </div>`;
  appRoot().innerHTML=`<div class="home">
  <header class="home-header"><div><p class="home-kicker">Expansion · Muse</p><h1 class="home-greeting">Video Studio</h1></div>
  <div class="home-meta">${btnHome()}</div></header>
  <section class="home-group">
    <div class="guide-aria">
      <img src="/assets/aria/aria.webp" alt="Aria">
      <div>
        <p class="sub" style="letter-spacing:.14em;text-transform:uppercase;color:var(--ot-cyan);font-size:10px;margin:0 0 8px">Aria // guiding</p>
        <p style="margin:0 0 10px;line-height:1.5">Studio is Expansion premium — same idea as Genome. I look for Comfy on this PC first. If it is not up, Start Comfy pulls our Docker sidecar on port 8188. Models/LTX come later; READY only needs Comfy answering.</p>
        <p><b>Configured:</b> ${escapeHtml(st)} · ${escapeHtml(detail||'—')}</p>
      </div>
    </div>
    ${foundBlock}
    <div class="hud-cta-row" style="margin-top:8px">
      <button type="button" class="hud-cta primary" onclick="otSfx('ok');startComfySidecar()">Start / Install Comfy</button>
      <button type="button" class="hud-cta" onclick="otSfx('click');showVideoStudioSetup()">Detect again</button>
      <button type="button" class="hud-cta" onclick="otSfx('click');showExpansionSurface('creative')">Open Muse room</button>
    </div>
    <details style="margin-top:16px">
      <summary style="cursor:pointer;color:var(--ot-muted);font-size:11px;letter-spacing:.08em;text-transform:uppercase">Advanced — paste URL</summary>
      <label style="display:block;margin:12px 0 6px;font-size:10px;letter-spacing:.12em;text-transform:uppercase;color:var(--ot-muted)">ComfyUI URL</label>
      <input id="comfyUrl" value="${escapeHtml(ep)}" style="width:100%;max-width:520px;padding:10px;background:#020508;border:1px solid rgba(46,230,214,.35);color:var(--ot-text);font:inherit">
      <div class="hud-cta-row" style="margin-top:10px">
        <button type="button" class="hud-cta" onclick="otSfx('ok');saveComfyUrl()">Save &amp; probe</button>
      </div>
      <ol class="guide-steps">
        <li>Docker Desktop / Engine required for <b>Start Comfy</b> (WSL2 on Windows).</li>
        <li>Or install <a href="https://github.com/comfyanonymous/ComfyUI" target="_blank" rel="noopener">ComfyUI portable</a> yourself, then Detect / Use this.</li>
        <li>Keep-style GPU Comfy on :8199 is also auto-detected if already running.</li>
      </ol>
    </details>
    <div class="hud-cta-row" style="margin-top:14px">
      <button type="button" class="hud-cta" onclick="showHome()">Back to deck</button>
    </div>
  </section>
</div>`;
}
async function useDetectedComfy(endpoint){
  const el=document.getElementById('comfyUrl');
  if(el) el.value=endpoint;
  else{
    const hidden=document.createElement('input');
    hidden.id='comfyUrl'; hidden.type='hidden'; hidden.value=endpoint;
    document.body.appendChild(hidden);
  }
  await saveComfyUrl();
}
async function startComfySidecar(){
  try{
    const status=document.querySelector('.guide-aria .muted');
    if(status) status.textContent='Starting Comfy sidecar (first pull can take a few minutes)…';
    const r=await api('/api/expansion/video-studio/start',{});
    await loadCapabilities();
    if(r&&r.ok&&r.data&&r.data.ok){
      otSfx('ok');
      alert('Comfy '+(r.data.action||'ready')+': '+(r.data.endpoint||'')+' · '+((r.data.state)||''));
      if(String(r.data.state||'').toUpperCase()==='READY') showExpansionSurface('creative');
      else showVideoStudioSetup();
    }else{
      otSfx('error');
      const msg=(r&&r.data&&(r.data.error||r.data.hint||r.data.action))||'Start failed';
      alert(msg);
      showVideoStudioSetup();
    }
  }catch(e){
    otSfx('error');
    alert('Start failed: '+String(e&&e.message||e));
  }
}
async function saveComfyUrl(){
  const el=document.getElementById('comfyUrl');
  const endpoint=(el&&el.value||'').trim();
  if(!endpoint){ alert('Enter a ComfyUI URL'); return; }
  try{
    const r=await api('/api/expansion/video-studio/config',{endpoint});
    await loadCapabilities();
    if(r&&r.ok){
      const st=(r.data&&r.data.state)||capStatus('video');
      otSfx('ok');
      if(String(st).toUpperCase()==='READY'||st==='ready') showExpansionSurface('creative');
      else{
        alert('Saved. Video Studio state: '+st);
        showVideoStudioSetup();
      }
    }else{
      alert((r&&r.data&&r.data.error)||'Save failed');
    }
  }catch(e){
    alert('Save failed: '+String(e&&e.message||e));
  }
}
async function saveComfyUrlFromFloor(){
  const el=document.getElementById('fl-comfy-url');
  if(el){
    const wrap=document.getElementById('comfyUrl');
    if(!wrap){
      const hidden=document.createElement('input');
      hidden.id='comfyUrl';
      hidden.type='hidden';
      hidden.value=el.value;
      document.body.appendChild(hidden);
    }else{
      wrap.value=el.value;
    }
  }
  await saveComfyUrl();
  if(typeof renderCreativeFloor==='function') renderCreativeFloor();
  else showExpansionSurface('creative');
}
async function showComputeNodes(){
  state.view='home';
  setBodyMode('home');
  let nodes={}, resources={};
  try{ nodes=await apiGet('/api/nodes'); }catch(_e){ nodes={}; }
  try{ resources=await apiGet('/api/resources'); }catch(_e){ resources={}; }
  const list=Array.isArray(nodes)?nodes:(nodes.nodes||nodes.items||[]);
  const rows=list.length
    ? list.map(n=>`<div class="card"><b>${escapeHtml(n.name||n.id||'node')}</b><p class="muted">${escapeHtml(JSON.stringify(n).slice(0,240))}</p></div>`).join('')
    : `<div class="card"><b>local</b><p class="muted">This Expansion host is the active compute node. Remote pairing ships in a later Expansion pack.</p>
       <pre class="muted" style="white-space:pre-wrap">${escapeHtml(JSON.stringify(resources||{},null,2).slice(0,1200))}</pre></div>`;
  appRoot().innerHTML=`<div class="home">
  <header class="home-header"><div><p class="home-kicker">Expansion</p><h1 class="home-greeting">Compute Nodes</h1></div>
  <div class="home-meta">${btnHome()}</div></header>
  <section class="home-group">${rows}
  <button type="button" class="cc-btn" onclick="showHome()">Back</button></section></div>`;
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
  otSfx('transmit');
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
  if(d.expansion&&d.expansion.mood_summary){
    renderMoodStrip(d.expansion.mood_summary);
  }else if(d.expansion&&d.expansion.emotion){
    refreshCodecMood();
  }
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
  if(state.expansion&&state.expansion.enabled) return showComputeNodes();
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
