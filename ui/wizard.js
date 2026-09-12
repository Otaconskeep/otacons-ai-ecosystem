let state={step:0,scan:null,name:'Billy',features:['chat','memory','voice'],config:null,storage:null,conversation:null,voiceId:'voice_001',autoSpeak:false,voices:[],currentAudio:null,speakingMsg:null,recorder:null,recordingState:'MIC_READY',testMode:window.__OTACON_TEST_MODE__===true};
const page=document.getElementById('page');
const labels=['Welcome','System Scan','Hardware Recommendation','Storage','Agent Setup','Features','Review','Finish'];

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

function render(){
  let s=state.step; document.getElementById('title').textContent=labels[s];
  if(s===0) page.innerHTML='<p>This wizard configures your local AI system. No Docker or YAML knowledge is required.</p><button onclick="next()">Get Started</button><button onclick="showChat()">Open Chat</button>';
  if(s===1) page.innerHTML='<p>Detect your computer, GPUs, storage, and available capacity.</p><button onclick="scan()">Scan My System</button>';
  if(s===2){let h=state.scan.hardware.hardware,g=state.scan.hardware.gpu_roles; page.innerHTML=`<div class=card>System: ${h.os}<br>CPU: ${h.cpu.model} (${h.cpu.cores} cores)<br>Memory: ${h.ram_gb} GB</div>`+(h.gpus.length?h.gpus.map(x=>`<div class=card>${x.model} — ${x.vram_gb} GB VRAM — ${x.capability}</div>`).join(''):'<div class=card>CPU fallback (no GPU detected)</div>')+`<p class=muted>Recommended primary: ${g.primary_gpu}</p><button onclick="next()">Use Recommended Setup</button>`;}
  if(s===3){let v=state.scan.storage.find(x=>x.recommended)||state.scan.storage[0]||{}; page.innerHTML=`<div class=card><b>Recommended storage</b><br>${v.path||'Unavailable'}<br>${v.free_gb||0} GB free</div><button onclick="next()">Use Recommended Storage</button>`;}
  if(s===4) page.innerHTML=agentSetupHtml();
  if(s===5) page.innerHTML=[['chat','Chat','SUPPORTED'],['memory','Memory','SUPPORTED'],['voice','Voice Output','SUPPORTED'],['speech_to_text','Speech Input','IN DEVELOPMENT'],['image_generation','Image Generation','COMING LATER'],['video_generation','Video Generation','COMING LATER'],['web_search','Web Search','COMING LATER']].map(([f,label,status])=>`<label><input type=checkbox value=${f} ${state.features.includes(f)?'checked':''} ${status==='COMING LATER'?'disabled':''}> ${label} <span class=muted>— ${status}</span></label>`).join('')+'<button onclick="setFeatures()">Continue</button>';
  if(s===6) page.innerHTML=`<div class=card>Agent: ${state.name}<br>Voice: ${voiceLabel(state.voiceId)}<br>Features: ${state.features.join(', ')}<br>Storage: ${(state.scan.storage.find(x=>x.recommended)||state.scan.storage[0]||{}).path||'Unavailable'}</div><button onclick="build()">Create Configuration</button>`;
  if(s===7) page.innerHTML=`<p>${state.name} is configured.</p><p class=muted>Open chat to talk and use voice playback.</p><div class=card>${state.config?.saved||''}</div><button onclick="showChat()">Open Chat</button>`;
}

function voiceLabel(id){
  let v=(state.voices||[]).find(x=>x.id===id); return v?v.display_name:id;
}
function agentSetupHtml(){
  let opts=(state.voices||[]).map(v=>`<option value="${v.id}" ${v.id===state.voiceId?'selected':''}>${v.display_name}${v.fixture?' (test)':''}</option>`).join('');
  return `<label>Agent name<br><input id=name value="${state.name||'Billy'}"></label>
<label>Voice<br><select id=voiceSelect>${opts||'<option value="voice_001">Warm Male</option>'}</select></label>
<button type=button onclick="previewSelectedVoice()">Preview</button>
<p class=muted id=previewStatus></p>
<label>Role<br><input value="Primary Assistant" disabled></label>
<button onclick="setName()">Continue</button>`;
}

async function previewSelectedVoice(){
  let sel=document.getElementById('voiceSelect'); state.voiceId=sel?sel.value:state.voiceId;
  let st=document.getElementById('previewStatus'); if(st) st.textContent='Synthesizing…';
  let r=await api('/api/preview_voice',{agent:{id:'agent_001',display_name:state.name||'Billy',voice_id:state.voiceId},text:`Hello, I am ${state.name||'Billy'}.`});
  if(!r.ok||r.data.status==='error'){ if(st) st.textContent='Voice preview unavailable'; return }
  if(st) st.textContent='Playing preview';
  playAudio(r.data.audio_base64);
}

function next(){state.step++;render()}
async function scan(){state.scan=await apiGet('/api/scan');state.storage=state.scan.storage.find(x=>x.recommended)||state.scan.storage[0];state.step=2;render()}
async function setName(){
  state.name=document.getElementById('name').value.trim()||'Assistant';
  let sel=document.getElementById('voiceSelect'); if(sel) state.voiceId=sel.value;
  await api('/api/agent/voice',{agent_id:'agent_001',display_name:state.name,voice_id:state.voiceId});
  next();
}
function setFeatures(){state.features=[...document.querySelectorAll('input[type=checkbox]:checked')].map(x=>x.value);next()}
async function build(){
  let p=await api('/api/plan',{name:state.name,features:state.features,storage:state.storage});
  let cfg=p.data.config; if(cfg.agents&&cfg.agents[0]) cfg.agents[0].voice_id=state.voiceId;
  let s=await api('/api/save',{config:cfg}); state.config={saved:s.data.path}; next();
}

function stopAudio(){
  if(state.currentAudio){try{state.currentAudio.pause(); state.currentAudio.currentTime=0}catch(e){} state.currentAudio=null}
  if(state.speakingMsg!=null){
    let b=document.querySelector(`[data-speak-btn="${state.speakingMsg}"]`);
    if(b){b.textContent='▶'; b.dataset.state='idle'}
    state.speakingMsg=null;
  }
}
function playAudio(b64, msgId){
  stopAudio();
  let a=new Audio('data:audio/wav;base64,'+b64);
  state.currentAudio=a;
  if(msgId!=null){
    state.speakingMsg=msgId;
    let b=document.querySelector(`[data-speak-btn="${msgId}"]`);
    if(b){b.textContent='■'; b.dataset.state='playing'}
  }
  a.onended=()=>stopAudio();
  a.play().catch(()=>{ if(msgId!=null){ let e=document.querySelector(`[data-speak-err="${msgId}"]`); if(e) e.textContent='Voice playback unavailable';} stopAudio();});
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
    return `<div class=msg><p><b>${role==='user'?'You':role}:</b> ${escapeHtml(content)}</p></div>`;
  }
  return `<div class=msg data-msg="${msgId}">
    <p><b>${state.name}:</b> ${escapeHtml(content)}</p>
    <button type=button class=speak data-speak-btn="${msgId}" data-state=idle onclick='toggleSpeak(${msgId}, ${JSON.stringify(content)})' title="Play voice">▶</button>
    <span class=muted data-speak-err="${msgId}"></span>
  </div>`;
}
function escapeHtml(s){return String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}

async function showChat(){
  await loadPrefs(); await loadVoices();
  let cs=(await api('/api/conversations',{agent_id:'agent_001'})).data;
  state.conversation=(cs[0]||{}).id||(await api('/api/conversation',{agent_id:'agent_001'})).data.id;
  let voiceOpts=(state.voices||[]).map(v=>`<option value="${v.id}" ${v.id===state.voiceId?'selected':''}>${v.display_name}</option>`).join('');
  page.innerHTML=`<h2>${state.name}</h2>
<div class=card>
  <label>Voice
    <select id=chatVoice onchange="assignVoice(this.value)">${voiceOpts}</select>
  </label>
  <button type=button onclick="previewSelectedVoiceChat()">Preview</button>
  <label><input type=checkbox id=autoSpeak ${state.autoSpeak?'checked':''} onchange="setAutoSpeak(this.checked)"> Auto Speak Responses</label>
</div>
<button onclick="newConversation()">+ New Conversation</button>
<button onclick="loadMemories()">Memory</button>
<div class=card><b>Create an image</b><br><input id=imagePrompt placeholder="Describe an image"><select id=imageProfile><option value="draft">Draft</option><option value="standard" selected>Standard</option><option value="quality">Quality</option></select><button onclick="generateImage()">Generate</button><span id=imageStatus class=muted></span></div>
<div class=card><b>Create a video</b><br><input id=videoPrompt placeholder="Describe a short video"><select id=videoProfile><option value="draft">Draft</option><option value="normal" selected>Normal</option><option value="final">Final</option></select><button onclick="generateVideo()">Generate</button><span id=videoStatus class=muted></span></div>
<div id=conversation-list>${(cs||[]).map((c,i)=>`<button onclick="openConversation('${c.id}')">${c.title||'Conversation '+(i+1)}</button>`).join('')}</div>
<div id=messages class=card></div>
<input id=chat placeholder="Message ${state.name}">
<button type=button id=micButton onclick="toggleRecording()" title="Record a message">🎤</button><button onclick="sendChat()">Send</button><span id=micStatus class=muted></span>
<div id=memory-panel class=card><b>Memories ${state.name} Keeps</b><p class=muted>Memories are details ${state.name} can use in future conversations.</p><div id=memories></div><input id=memory placeholder="Add a memory"><button onclick="addMemory()">Save Memory</button></div>`;
  openConversation(state.conversation); loadMemories();
}

async function assignVoice(vid){
  state.voiceId=vid;
  await api('/api/agent/voice',{agent_id:'agent_001',display_name:state.name,voice_id:vid});
}
async function previewSelectedVoiceChat(){
  let r=await api('/api/preview_voice',{agent:{id:'agent_001',display_name:state.name,voice_id:state.voiceId},text:`Hello, I am ${state.name}.`});
  if(!r.ok||r.data.status==='error'){alert('Voice preview unavailable');return}
  playAudio(r.data.audio_base64);
}
async function setAutoSpeak(on){
  state.autoSpeak=!!on;
  await api('/api/preferences',{auto_speak:state.autoSpeak});
}

async function newConversation(){state.conversation=(await api('/api/conversation',{agent_id:'agent_001'})).data.id;document.getElementById('messages').innerHTML=''}
async function openConversation(id){
  state.conversation=id;
  let r=(await api('/api/conversation/get',{id,agent_id:'agent_001'})).data;
  let box=document.getElementById('messages');
  box.innerHTML='';
  (r.messages||[]).forEach((x,i)=>{ box.insertAdjacentHTML('beforeend', messageHtml(x.role,x.content,i)); });
}
async function loadMemories(){let r=(await api('/api/memories',{agent_id:'agent_001'})).data;let e=document.getElementById('memories');if(e)e.innerHTML=(r||[]).map(x=>`<p>${escapeHtml(x.content)} <button onclick="delMemory(${x.id})">Delete</button></p>`).join('')||'<p>None stored.</p>'}
async function addMemory(){let e=document.getElementById('memory');if(e.value.trim())await api('/api/memory',{agent_id:'agent_001',content:e.value.trim()});e.value='';loadMemories()}
async function delMemory(id){await api('/api/memory/delete',{agent_id:'agent_001',id});loadMemories()}
async function generateImage(){let p=document.getElementById('imagePrompt').value.trim(), s=document.getElementById('imageStatus'); if(!p)return; s.textContent='Creating image…'; let r=await api('/api/generate_image',{prompt:p,profile:document.getElementById('imageProfile').value,agent_id:'agent_001',conversation_id:state.conversation,test_mode:state.testMode}); if(!r.ok){s.textContent=r.data?.error?.message||'Image generation unavailable.';return} let a=r.data.artifacts?.[0]; if(a){s.innerHTML=`<br><img src="file://${a.path}" alt="Generated image" style="max-width:100%">`; } }
async function generateVideo(){let p=document.getElementById('videoPrompt').value.trim(), s=document.getElementById('videoStatus'); if(!p)return; s.textContent='Creating video…'; let r=await api('/api/generate_video',{prompt:p,profile:document.getElementById('videoProfile').value,agent_id:'agent_001',conversation_id:state.conversation,test_mode:state.testMode}); if(!r.ok){s.textContent=r.data?.error?.message||'Video generation unavailable.';return} let a=r.data.artifacts?.[0]; if(a)s.textContent='Video ready: '+a.path; }

async function sendChat(){
  let el=document.getElementById('chat'), box=document.getElementById('messages'), m=el.value.trim();
  if(!m) return;
  let uid=box.querySelectorAll('.msg').length;
  box.insertAdjacentHTML('beforeend', `<div class=msg><p><b>You:</b> ${escapeHtml(m)}</p></div><p id=wait class=muted>Waiting…</p>`);
  el.value='';
  let r=await api('/api/chat_with_agent',{
    agent:{id:'agent_001',display_name:state.name,voice_id:state.voiceId},
    message:m, conversation_id:state.conversation, auto_speak:state.autoSpeak
  });
  document.getElementById('wait')?.remove();
  if(!r.ok){
    box.insertAdjacentHTML('beforeend', `<div class=msg><p><b>${state.name}:</b> Your AI service is unavailable.</p></div>`);
    return;
  }
  let d=r.data;
  let mid=uid+1;
  box.insertAdjacentHTML('beforeend', messageHtml('assistant', d.text, mid));
  if(d.voice && d.voice.status==='error'){
    let err=document.querySelector(`[data-speak-err="${mid}"]`);
    if(err) err.textContent='Voice playback unavailable';
  } else if(state.autoSpeak && d.voice && d.voice.audio_base64){
    let b=document.querySelector(`[data-speak-btn="${mid}"]`);
    if(b) b.dataset.audio=d.voice.audio_base64;
    playAudio(d.voice.audio_base64, mid);
  }
}

async function toggleRecording(){
  const button=document.getElementById('micButton'), status=document.getElementById('micStatus');
  if(state.recorder && state.recorder.state==='recording'){ state.recorder.stop(); return; }
  if(!navigator.mediaDevices || !window.MediaRecorder){ state.recordingState='MIC_UNAVAILABLE'; if(status) status.textContent='Microphone is unavailable in this environment.'; return; }
  try {
    const stream=await navigator.mediaDevices.getUserMedia({audio:true});
    const chunks=[]; state.recorder=new MediaRecorder(stream); state.recordingState='RECORDING';
    button.textContent='■ Stop'; button.dataset.state='recording'; if(status) status.textContent='Recording…';
    state.recorder.ondataavailable=e=>{if(e.data.size) chunks.push(e.data)};
    state.recorder.onstop=async()=>{
      stream.getTracks().forEach(t=>t.stop()); state.recordingState='PROCESSING'; button.textContent='🎤'; button.dataset.state='processing'; if(status) status.textContent='Transcribing…';
      try {
        const blob=new Blob(chunks,{type:state.recorder.mimeType||'audio/webm'}); const reader=new FileReader();
        reader.onload=async()=>{ const b64=String(reader.result).split(',')[1]||''; const r=await api('/api/transcribe_audio',{audio_base64:b64,test_mode:state.testMode});
          if(!r.ok || !r.data.text) throw new Error(r.data?.error?.message||'TRANSCRIPTION_FAILED');
          document.getElementById('chat').value=r.data.text; state.recordingState='TRANSCRIPTION_READY'; if(status) status.textContent='Review the transcription, then press Send.';
          button.dataset.state='ready';
        }; reader.readAsDataURL(blob);
      } catch(e){state.recordingState='TRANSCRIPTION_FAILED'; button.dataset.state='error'; if(status) status.textContent='We could not transcribe that recording.';}
    }; state.recorder.start();
  } catch(e){ state.recordingState=e.name==='NotAllowedError'?'MIC_PERMISSION_DENIED':'MIC_UNAVAILABLE'; if(status) status.textContent=state.recordingState==='MIC_PERMISSION_DENIED'?'Otacon needs microphone permission to hear you.':'Microphone is unavailable in this environment.'; }
}

(async()=>{ await loadPrefs(); await loadVoices(); render(); })();
