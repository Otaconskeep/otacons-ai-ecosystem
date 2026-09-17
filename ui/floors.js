/* Expansion flagship floors — Keep HUD (fl-*), loaded after wizard.js.
   Globals: apiGet, api, escapeHtml, appRoot, setBodyMode, showHome,
   showExpansionSurface, showEmotionWhy, showRelWhy, showLearningWhy, showRexBoard. */
(function () {
  'use strict';

  var AGENTS = ['aria', 'vector', 'ledger', 'muse', 'sentry'];
  var VULN_KINDS = [
    'fear', 'anxiety', 'insecurity', 'self_conscious',
    'crutch', 'compulsion', 'addictive_tendency'
  ];
  var REL_DIMS = [
    'trust', 'affinity', 'respect', 'familiarity', 'dependency',
    'conflict', 'rivalry', 'jealousy', 'protectiveness', 'reliability', 'attachment'
  ];

  var FL = {
    dossierTab: 'aria',
    diaryTab: 'aria',
    journal: { agent: '', event_type: '', job_id: '' },
    intelQ: '',
    relFocus: null,
    _journalById: {},
    _relByEdge: {}
  };

  function esc(s) { return escapeHtml(s == null ? '' : s); }
  function fmtTs(t) {
    if (t == null || t === '') return '—';
    var n = Number(t);
    if (!Number.isFinite(n)) return esc(String(t));
    try { return esc(new Date(n > 1e12 ? n : n * 1000).toISOString()); }
    catch (e) { return esc(String(t)); }
  }
  function pct(v) {
    var n = Number(v);
    if (!Number.isFinite(n)) return 0;
    return Math.max(0, Math.min(100, Math.round(n * 100)));
  }
  function empty(msg) {
    return '<p class="fl-empty">' + esc(msg || 'Nothing recorded yet.') + '</p>';
  }
  function metric(n, l) {
    return '<div class="fl-metric"><span class="n">' + esc(String(n)) +
      '</span><span class="l">' + esc(l) + '</span></div>';
  }
  function bar(label, value, opts) {
    var p = pct(value);
    var click = opts && opts.onclick
      ? ' role="button" tabindex="0" onclick="' + opts.onclick + '"' : '';
    var shown = value == null ? '—' : String(Math.round(Number(value) * 1000) / 1000);
    return '<div class="fl-bar"' + click + '><div class="fl-bar-h"><span>' + esc(label) +
      '</span><span>' + esc(shown) + '</span></div>' +
      '<div class="fl-bar-track"><i style="width:' + p + '%"></i></div></div>';
  }
  function btn(label, onclick, ghost) {
    return '<button type="button" class="cc-btn' + (ghost ? ' ghost' : '') +
      '" onclick="' + onclick + '">' + esc(label) + '</button>';
  }
  function jobLink(jobId) {
    if (!jobId) return '';
    var id = esc(jobId);
    var focus = "location.search='?rex=1&focus=" + encodeURIComponent(jobId) +
      "';if(typeof showRexBoard==='function')showRexBoard()";
    var rex = typeof showRexBoard === 'function' ? btn('REX', 'showRexBoard()', true) : '';
    return '<span class="fl-job">' + id + ' ' + btn('Focus', focus, true) + ' ' + rex + '</span>';
  }
  function pill(t, kind) {
    return '<span class="fl-pill' + (kind ? ' ' + kind : '') + '">' + esc(t) + '</span>';
  }
  function panel(title, body, extra) {
    return '<section class="fl-panel">' +
      (title ? '<h3 class="fl-h">' + esc(title) + '</h3>' : '') +
      (extra || '') + (body || '') + '</section>';
  }
  function listCards(rows, renderOne, emptyMsg) {
    if (!rows || !rows.length) return empty(emptyMsg);
    return '<div class="fl-stack">' + rows.map(renderOne).join('') + '</div>';
  }
  function effectsLine(arr) {
    if (!arr || !arr.length) return '<span class="muted">none</span>';
    return esc(arr.map(function (e) {
      if (typeof e === 'string') return e;
      if (e && typeof e === 'object') {
        return Object.keys(e).map(function (k) { return k + ':' + e[k]; }).join(' ');
      }
      return String(e);
    }).join(' · '));
  }
  function topDims(dims, n) {
    var d = dims || {};
    return Object.keys(d).map(function (k) { return [k, d[k]]; })
      .sort(function (a, b) { return Number(b[1]) - Number(a[1]); }).slice(0, n);
  }
  function oc() {
    /* build onclick string: oc('fn', a, b) => fn('a','b') */
    var fn = arguments[0];
    var args = [];
    for (var i = 1; i < arguments.length; i++) args.push("'" + esc(arguments[i]) + "'");
    return fn + '(' + args.join(',') + ')';
  }

  function ensureFloorStyles() {
    if (document.getElementById('fl-styles')) return;
    var s = document.createElement('style');
    s.id = 'fl-styles';
    s.textContent = [
      '.fl{max-width:1480px;margin:0 auto;display:flex;flex-direction:column;gap:1rem;padding:0 0 2rem}',
      '.fl-mast{display:flex;justify-content:space-between;align-items:flex-start;gap:1rem;flex-wrap:wrap;',
      'padding:1rem 1.15rem;border:1px solid var(--ot-line);border-radius:14px;',
      'background:linear-gradient(180deg,rgba(28,26,40,.98),rgba(16,14,24,.96));box-shadow:0 16px 36px rgba(0,0,0,.32)}',
      '.fl-mast .kicker{margin:0 0 6px;font-size:10px;letter-spacing:.22em;text-transform:uppercase;color:var(--ot-lilac)}',
      '.fl-mast h1{margin:0;font-size:clamp(1.2rem,2.6vw,1.7rem);letter-spacing:.04em}',
      '.fl-mast .meta{display:flex;flex-wrap:wrap;gap:.5rem;align-items:center}',
      '.fl-strip{display:flex;flex-wrap:wrap;gap:.55rem}',
      '.fl-rail{display:flex;flex-wrap:wrap;gap:.4rem}',
      '.fl-tabs{display:flex;flex-wrap:wrap;gap:.35rem;margin:0 0 .75rem}',
      '.fl-tab{cursor:pointer;font:inherit;font-size:.72rem;letter-spacing:.08em;text-transform:uppercase;',
      'color:var(--ot-muted);background:rgba(10,8,16,.55);border:1px solid rgba(151,159,236,.16);',
      'border-radius:999px;padding:.35rem .7rem}',
      '.fl-tab.on,.fl-tab:hover{color:var(--ot-text);border-color:#7dffc3}',
      '.fl-panel{background:rgba(18,16,24,.94);border:1px solid rgba(151,159,236,.22);border-radius:12px;padding:.85rem 1rem}',
      '.fl-h{margin:0 0 .55rem;font-size:.72rem;letter-spacing:.12em;text-transform:uppercase;color:var(--ot-lilac)}',
      '.fl-stack{display:flex;flex-direction:column;gap:.55rem}',
      '.fl-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:.65rem}',
      '.fl-card{background:rgba(8,6,12,.55);border:1px solid rgba(151,159,236,.16);border-radius:10px;padding:.7rem .8rem}',
      '.fl-card.muted-abs{opacity:.55;border-style:dashed}',
      '.fl-card.clickable{cursor:pointer;text-align:left;width:100%;font:inherit;color:inherit}',
      '.fl-card.clickable:hover{border-color:var(--ot-cyan)}',
      '.fl-empty,.fl .muted{color:var(--ot-muted);font-size:.82rem}',
      '.fl-metric{min-width:88px;padding:.5rem .7rem;background:rgba(18,16,24,.94);border:1px solid rgba(151,159,236,.22);border-radius:10px}',
      '.fl-metric .n{display:block;font-size:1.1rem;font-weight:700;color:#7dffc3}',
      '.fl-metric .l{font-size:.68rem;letter-spacing:.1em;text-transform:uppercase;color:var(--ot-muted)}',
      '.fl-bar{margin:0 0 .45rem}',
      '.fl-bar-h{display:flex;justify-content:space-between;font-size:.72rem;color:var(--ot-muted);margin-bottom:3px}',
      '.fl-bar-track{height:5px;border-radius:99px;background:rgba(228,230,251,.12);overflow:hidden}',
      '.fl-bar-track>i{display:block;height:100%;background:linear-gradient(90deg,var(--ot-cyan),var(--ot-lilac));width:0}',
      '.fl-bar[role=button]{cursor:pointer}',
      '.fl-pill{display:inline-block;font-size:.68rem;letter-spacing:.06em;padding:.15rem .45rem;border-radius:999px;',
      'border:1px solid rgba(151,159,236,.28);color:var(--ot-lilac);margin-right:.25rem}',
      '.fl-pill.warn{color:var(--ot-rose);border-color:rgba(224,149,181,.4)}',
      '.fl-pill.ok{color:#7dffc3;border-color:rgba(125,255,195,.35)}',
      '.fl-filters{display:flex;flex-wrap:wrap;gap:.5rem;align-items:center;margin:0 0 .75rem}',
      '.fl-filters input,.fl-filters select,.fl-form input,.fl-form select{font:inherit;font-size:.85rem;color:var(--ot-text);',
      'background:rgba(8,6,12,.85);border:1px solid rgba(151,159,236,.22);border-radius:8px;padding:.45rem .65rem}',
      '.fl-form{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:.55rem;align-items:end}',
      '.fl-form label{display:flex;flex-direction:column;gap:.25rem;font-size:.68rem;letter-spacing:.08em;text-transform:uppercase;color:var(--ot-muted)}',
      '.fl-form .chk{flex-direction:row;align-items:center;gap:.4rem;text-transform:none;letter-spacing:0;font-size:.82rem}',
      '.fl-matrix{width:100%;border-collapse:collapse;font-size:.72rem}',
      '.fl-matrix th,.fl-matrix td{border:1px solid rgba(151,159,236,.18);padding:.4rem;text-align:center;vertical-align:top}',
      '.fl-matrix th{color:var(--ot-lilac);font-weight:600;letter-spacing:.06em}',
      '.fl-matrix td.fl-cell{cursor:pointer;background:rgba(8,6,12,.4)}',
      '.fl-matrix td.fl-cell:hover{background:rgba(151,159,236,.12)}',
      '.fl-matrix .diag{background:transparent;opacity:.35}',
      '.fl-diary-entry{font-style:italic;font-family:Georgia,"Times New Roman",serif;line-height:1.55;',
      'background:linear-gradient(180deg,rgba(40,32,28,.9),rgba(22,18,16,.95));',
      'border:1px solid rgba(224,149,181,.22);border-radius:8px;padding:.85rem 1rem;color:#f0e6dc}',
      '.fl-drawer{position:fixed;inset:0;z-index:10060;display:grid;justify-items:end;background:rgba(4,2,8,.62)}',
      '.fl-drawer[hidden]{display:none!important}',
      '.fl-drawer-panel{width:min(420px,100%);height:100%;overflow:auto;padding:1.1rem 1.2rem;',
      'background:linear-gradient(180deg,#1a1722,#100e16);border-left:1px solid rgba(151,159,236,.28);box-shadow:-24px 0 60px rgba(0,0,0,.45)}',
      '.fl-drawer-panel h3{margin:0 0 .5rem;font-size:1rem}',
      '.fl-nav-tiles{display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:.45rem}',
      '.fl-nav-tiles button{cursor:pointer;font:inherit;text-align:left;padding:.65rem .75rem;border-radius:10px;',
      'border:1px solid rgba(151,159,236,.2);background:rgba(10,8,16,.55);color:var(--ot-text)}',
      '.fl-nav-tiles button:hover{border-color:#7dffc3}',
      '.fl-nav-tiles .t{display:block;font-size:.72rem;letter-spacing:.1em;text-transform:uppercase;color:var(--ot-lilac)}',
      '.fl-nav-tiles .d{font-size:.7rem;color:var(--ot-muted);margin-top:.2rem}',
      '.fl-two{display:grid;grid-template-columns:1.2fr .8fr;gap:.75rem}',
      '@media(max-width:900px){.fl-two{grid-template-columns:1fr}}',
      '.fl-job{display:inline-flex;flex-wrap:wrap;gap:.25rem;align-items:center}',
      '.fl-note{font-size:.78rem;color:var(--ot-muted);margin:0 0 .75rem}'
    ].join('');
    document.head.appendChild(s);
  }

  function foundationShellBanner() {
    return '<div class="fl-panel" style="margin-bottom:.75rem"><span class="fl-pill warn">EXPANSION</span>' +
      '<p class="fl-note">Premium Expansion surfaces. Genome Voice Trainer and Video Studio go live when their ' +
      'runtime is present (GPU Genome on :8765; ComfyUI via OTACON_COMFYUI_URL). Thin pills mean that runtime is not up yet — not that the feature is Keep-only.</p></div>';
  }

  function floorShell(title, kicker, bodyHtml, extraMeta) {
    ensureFloorStyles();
    setBodyMode('home');
    var meta = (extraMeta || '') +
      btn('Home', 'showHome()', true) +
      btn('Codec', "typeof showChat==='function'&&showChat()", false);
    appRoot().innerHTML =
      '<div class="home fl">' +
      '<header class="fl-mast"><div><p class="kicker">' + esc(kicker || 'Keep Expansion') +
      '</p><h1>' + esc(title) + '</h1></div><div class="meta">' + meta + '</div></header>' +
      '<div class="fl-body">' + foundationShellBanner() + (bodyHtml || '') + '</div>' +
      '<div id="fl-drawer" class="fl-drawer" hidden><div class="fl-drawer-panel" role="dialog" aria-modal="true">' +
      '<div style="display:flex;justify-content:space-between;gap:.5rem;align-items:center;margin-bottom:.5rem">' +
      '<h3 id="fl-drawer-title">WHY</h3>' + btn('Close', 'closeFloorDrawer()', true) +
      '</div><div id="fl-drawer-body"></div></div></div></div>';
  }

  function showFloorDrawer(title, html) {
    ensureFloorStyles();
    var el = document.getElementById('fl-drawer');
    if (!el) {
      var wrap = document.createElement('div');
      wrap.innerHTML =
        '<div id="fl-drawer" class="fl-drawer" hidden><div class="fl-drawer-panel" role="dialog" aria-modal="true">' +
        '<div style="display:flex;justify-content:space-between;gap:.5rem;align-items:center;margin-bottom:.5rem">' +
        '<h3 id="fl-drawer-title">WHY</h3>' + btn('Close', 'closeFloorDrawer()', true) +
        '</div><div id="fl-drawer-body"></div></div></div>';
      document.body.appendChild(wrap.firstElementChild);
      el = document.getElementById('fl-drawer');
    }
    var t = document.getElementById('fl-drawer-title');
    var b = document.getElementById('fl-drawer-body');
    if (t) t.textContent = title || 'WHY';
    if (b) b.innerHTML = html || empty('No provenance payload.');
    el.hidden = false;
  }

  function closeFloorDrawer() {
    var el = document.getElementById('fl-drawer');
    if (el) el.hidden = true;
  }

  function formatWhyObj(d) {
    if (!d || typeof d !== 'object') return empty('Empty WHY response.');
    if (d.error) return '<p class="fl-empty">' + esc(d.error) + '</p>';
    var bits = [];
    if (d.claim) bits.push('<p><b>' + esc(d.claim) + '</b></p>');
    if (d.label || d.narrative) {
      bits.push('<p><b>' + esc(d.label || '') + '</b></p><p class="muted">' + esc(d.narrative || '') + '</p>');
    }
    if (d.value != null) bits.push('<p>value: <b>' + esc(String(d.value)) + '</b></p>');
    if (d.confidence != null) {
      bits.push('<p class="muted">confidence ' + esc(String(d.confidence)) + ' · ' + esc(d.status || '') + '</p>');
    }
    if (d.dimensions) {
      bits.push('<div>' + Object.keys(d.dimensions).map(function (k) {
        return bar(k, d.dimensions[k]);
      }).join('') + '</div>');
    }
    function idBlock(label, rows) {
      if (!rows || !rows.length) return;
      bits.push('<h4 class="fl-h">' + esc(label) + '</h4><ul>' + rows.map(function (r) {
        if (typeof r === 'string') return '<li class="muted">' + esc(r) + '</li>';
        var txt = r.text || r.claim || r.observation_id || r.event_id || r.job_id || JSON.stringify(r);
        return '<li class="muted">' + esc(String(txt).slice(0, 240)) + '</li>';
      }).join('') + '</ul>');
    }
    idBlock('supporting_event_ids', d.supporting_event_ids || d.provenance_event_ids);
    idBlock('supporting_observations', d.supporting_observations);
    idBlock('contradicting_observations', d.contradicting_observations);
    idBlock('source_events_jobs', d.source_events_jobs);
    idBlock('source_journal_ids', d.source_journal_ids);
    idBlock('supporting_memory_ids', d.supporting_memory_ids);
    idBlock('supporting_job_ids', d.supporting_job_ids);
    idBlock('evidence_ids', d.evidence_ids);
    if (d.rule) bits.push('<p class="fl-note">' + esc(d.rule) + '</p>');
    if (d.explanation || d.why || d.reason) {
      bits.push('<p>' + esc(d.explanation || d.why || d.reason) + '</p>');
    }
    if (d.contributions && d.contributions.length) {
      bits.push('<h4 class="fl-h">contributions</h4>' + listCards(d.contributions, function (c) {
        return '<div class="fl-card"><b>' + esc(c.source || c.kind || 'contrib') + '</b>' +
          '<p class="muted">' + esc(c.detail || c.note || c.event_id || '') +
          ' · Δ ' + esc(String(c.delta != null ? c.delta : c.amount != null ? c.amount : '')) + '</p></div>';
      }, 'No contributions.'));
    }
    if (!bits.length) {
      Object.keys(d).slice(0, 24).forEach(function (k) {
        if (k === 'schema_version') return;
        var v = d[k];
        if (v == null) return;
        if (typeof v === 'object') {
          bits.push('<div class="fl-card"><b>' + esc(k) + '</b><p class="muted">' +
            esc(JSON.stringify(v).slice(0, 320)) + '</p></div>');
        } else {
          bits.push('<div class="fl-card"><b>' + esc(k) + '</b> · ' + esc(String(v)) + '</div>');
        }
      });
    }
    return bits.join('') || empty('No provenance fields.');
  }

  async function floorLivingWhy(agentId, obsId) {
    try {
      var d = await apiGet('/api/expansion/living/' + encodeURIComponent(agentId) +
        '/explain/' + encodeURIComponent(obsId));
      showFloorDrawer('Living · ' + agentId, formatWhyObj(d));
    } catch (e) { showFloorDrawer('Living WHY', empty(String(e))); }
  }

  async function floorDiaryWhy(agentId, diaryId) {
    try {
      var d = await apiGet('/api/expansion/diary/' + encodeURIComponent(agentId) +
        '/explain/' + encodeURIComponent(diaryId));
      showFloorDrawer('Diary · ' + agentId, formatWhyObj(d));
    } catch (e) { showFloorDrawer('Diary WHY', empty(String(e))); }
  }

  async function floorEmotionWhy(agentId, dim) {
    if (typeof showEmotionWhy === 'function') {
      try {
        await showEmotionWhy(agentId, dim);
        var legacy = document.getElementById('exp-why');
        if (legacy && legacy.innerHTML) {
          showFloorDrawer(agentId + '.' + dim, legacy.innerHTML);
          return;
        }
      } catch (e) { /* fall through */ }
    }
    try {
      var d = await apiGet('/api/expansion/emotion/' + encodeURIComponent(agentId) +
        '/why/' + encodeURIComponent(dim));
      showFloorDrawer(agentId + ' · ' + dim, formatWhyObj(d));
    } catch (e) { showFloorDrawer('Emotion WHY', empty(String(e))); }
  }

  async function floorRelWhy(src, dst) {
    if (typeof showRelWhy === 'function') {
      try {
        await showRelWhy(src, dst);
        var legacy = document.getElementById('exp-why');
        if (legacy && legacy.innerHTML) {
          showFloorDrawer(src + ' → ' + dst, legacy.innerHTML);
          return;
        }
      } catch (e) { /* fall through */ }
    }
    try {
      var d = await apiGet('/api/expansion/relationships/' + encodeURIComponent(src) +
        '/' + encodeURIComponent(dst) + '/why');
      showFloorDrawer(src + ' → ' + dst, formatWhyObj(d));
    } catch (e) { showFloorDrawer('Relationship WHY', empty(String(e))); }
  }

  function floorLearningWhy(claimId) {
    if (typeof showLearningWhy === 'function') {
      showLearningWhy(claimId);
      setTimeout(function () {
        var el = document.getElementById('learn-why') || document.getElementById('exp-why');
        if (el && el.innerHTML) showFloorDrawer('Learning WHY', el.innerHTML);
      }, 80);
      return;
    }
    apiGet('/api/expansion/learning/why/' + encodeURIComponent(claimId)).then(function (d) {
      showFloorDrawer('Learning WHY', formatWhyObj(d));
    }).catch(function (e) { showFloorDrawer('Learning WHY', empty(String(e))); });
  }

  function floorNavTiles(exclude) {
    var tiles = [
      ['dashboard', 'Command Center', 'Owner overview'],
      ['command', 'Aria Command', 'Coordination'],
      ['war-room', 'War Room', 'Ops / decisions'],
      ['rex', 'Project REX', 'Autonomy board'],
      ['dossiers', 'Dossiers', 'Canonical + living'],
      ['journal', 'Journal', 'What happened'],
      ['diary', 'Diary', 'What it meant'],
      ['relationships', 'Relationships', 'Directional matrix'],
      ['emotion', 'Emotions', 'Affective state'],
      ['intel', 'Intel', 'Continuity'],
      ['reports', 'Reports', 'Per-agent depth'],
      ['creative', 'Creative', 'Muse / Studio'],
      ['ops', 'Ops', 'Sentry'],
      ['rooms', 'Page Builder', 'Registry'],
      ['learning', 'Learning', 'Claims + WHY']
    ];
    return '<div class="fl-nav-tiles">' + tiles.filter(function (t) {
      return t[0] !== exclude;
    }).map(function (t) {
      return '<button type="button" onclick="showExpansionSurface(\'' + t[0] + '\')">' +
        '<span class="t">' + esc(t[1]) + '</span><span class="d">' + esc(t[2]) + '</span></button>';
    }).join('') + '</div>';
  }

  function jobCard(j) {
    if (!j) return '';
    return '<div class="fl-card"><b>' + esc(j.job_id || j.title || '') + '</b> ' +
      pill(j.status || j.stage || '') + ' ' + pill(j.assigned_agent || j.owner || '') +
      '<p>' + esc(j.request || j.title || '') + '</p>' +
      '<p class="muted">' + esc(j.domain || '') + (j.error ? ' · ' + esc(j.error) : '') + '</p>' +
      (j.job_id ? jobLink(j.job_id) : '') + '</div>';
  }

  function kvPre(obj, max) {
    try {
      return '<div class="fl-card"><pre style="margin:0;font-size:11px;white-space:pre-wrap">' +
        esc(JSON.stringify(obj || {}, null, 2).slice(0, max || 900)) + '</pre></div>';
    } catch (e) {
      return empty('Unable to render status object.');
    }
  }

  /* —— Dossiers —— */
  function renderVulnGroups(byKind) {
    var bk = byKind || {};
    return VULN_KINDS.map(function (kind) {
      var items = bk[kind] || [];
      var body = items.length ? items.map(function (v) {
        var absent = !!v.intentional_absence;
        return '<div class="fl-card' + (absent ? ' muted-abs' : '') + '">' +
          '<div><b>' + esc(v.label || kind) + '</b> ' + pill(kind) +
          (absent ? ' ' + pill('not emphasized') : '') +
          (v.intensity != null ? ' ' + pill('i=' + v.intensity) : '') + '</div>' +
          '<p class="muted">' + esc(absent
            ? (v.description || 'Intentional absence — not emphasized in this product dossier.')
            : (v.description || '')) + '</p>' +
          (v.triggers && v.triggers.length
            ? '<p class="muted">triggers: ' + esc(v.triggers.join(', ')) + '</p>' : '') +
          '</div>';
      }).join('') : empty('No entries for ' + kind + '.');
      return panel(kind.replace(/_/g, ' '), body);
    }).join('');
  }

  function renderDossierBody(card) {
    if (!card) return empty('Agent dossier unavailable.');
    var id = card.agent_id;
    var ident = card.identity || {};
    var ch = card.character || {};
    var caps = card.capabilities || {};
    var social = card.social || {};
    var living = (card.living && card.living.observations) || [];
    var learn = card.learning || {};
    var claims = [].concat(learn.private || [], learn.shared_keep || learn.shared || []);
    var base = card.emotional_baseline || {};
    var cur = card.current_emotion || {};
    var dims = [];
    Object.keys(base).forEach(function (k) { if (dims.indexOf(k) < 0) dims.push(k); });
    Object.keys(cur).forEach(function (k) { if (dims.indexOf(k) < 0) dims.push(k); });
    dims = dims.slice(0, 16);

    var identityHtml = '<div class="fl-card"><b>' + esc(ident.display_name || id) + '</b> · ' +
      esc(ident.role || '') + ' · ' + esc(ch.archetype || '') +
      '<p class="muted">' + esc(ident.tagline || ident.summary || '') + '</p>' +
      '<p class="muted">' + esc((card.background &&
        (card.background.public_summary || card.background.origin)) || '') + '</p></div>';

    var personality = '<div class="fl-card"><p>' + esc(ch.personality || ch.summary || ch.voice || '') +
      '</p><p class="muted">diary style: ' + esc(ch.diary_style || '—') +
      ' · humor: ' + esc(ch.humor || '—') + '</p></div>';

    function bulletList(arr) {
      if (!arr || !arr.length) return empty('None listed.');
      return '<ul>' + arr.map(function (x) { return '<li>' + esc(x) + '</li>'; }).join('') + '</ul>';
    }
    var sw = '<div class="fl-grid"><div class="fl-card"><h4 class="fl-h">strengths</h4>' +
      bulletList(caps.strengths) + '</div><div class="fl-card"><h4 class="fl-h">weaknesses</h4>' +
      bulletList(caps.weaknesses) + '</div></div>';

    var attach = '<div class="fl-grid">' +
      '<div class="fl-card"><b>attachment</b><p class="muted">' + esc(social.attachment_style || '—') + '</p></div>' +
      '<div class="fl-card"><b>jealousy</b><p class="muted">' +
      esc(String(social.jealousy_sensitivity != null ? social.jealousy_sensitivity : '—')) +
      '</p><p class="muted">' + esc(social.jealousy_behavior || '') + '</p></div>' +
      '<div class="fl-card"><b>rivalry</b><p class="muted">' + esc(social.rivalry_behavior || '—') + '</p></div></div>';

    var emoCmp = dims.length ? dims.map(function (k) {
      return '<div class="fl-card"><b>' + esc(k) + '</b>' +
        '<div class="fl-bar-h"><span>baseline</span><span>' +
        esc(String(base[k] != null ? base[k] : '—')) + '</span></div>' +
        bar('current', cur[k] != null ? cur[k] : 0, { onclick: oc('floorEmotionWhy', id, k) }) +
        '</div>';
    }).join('') : empty('No emotion dimensions loaded.');

    var livingHtml = listCards(living, function (o) {
      return '<div class="fl-card"><b>' + esc(o.category || 'obs') + '</b> · conf ' +
        esc(String(o.confidence)) + '<p>' + esc(o.value || '') + '</p>' +
        '<p class="muted">' + fmtTs(o.last_updated || o.first_observed) + '</p>' +
        btn('WHY', oc('floorLivingWhy', id, o.observation_id), true) + '</div>';
    }, 'No living observations yet.');

    var learnHtml = listCards(claims, function (c) {
      return '<div class="fl-card"><b>' + esc(c.claim || '') + '</b>' +
        '<p class="muted">conf ' + esc(String(c.confidence)) + ' · ' +
        esc(c.scope_label || c.scope || '') + ' · ev ' + esc(String(c.evidence_count || 0)) + '</p>' +
        btn('WHY', oc('floorLearningWhy', c.claim_id), true) + '</div>';
    }, 'No graduated learning claims.');

    var relHtml = listCards(card.relationship_highlights || [], function (r) {
      var tops = topDims(r.dimensions, 3).map(function (kv) { return kv[0] + '=' + kv[1]; }).join(', ');
      return '<div class="fl-card"><b>' + esc(id) + ' → ' + esc(r.target) + '</b> · ' + esc(r.label || '') +
        '<p class="muted">' + esc(r.narrative || '') + '</p>' +
        '<p class="muted">' + esc(tops) + '</p>' +
        btn('Rel WHY', oc('floorRelWhy', id, r.target), true) + '</div>';
    }, 'No relationship highlights.');

    return panel('Identity', identityHtml) +
      panel('Personality', personality) +
      panel('Strengths / weaknesses', sw) +
      panel('Vulnerability groups', renderVulnGroups((card.vulnerabilities || {}).by_kind)) +
      panel('Attachment / jealousy / rivalry', attach) +
      panel('Emotional baseline vs current', '<div class="fl-grid">' + emoCmp + '</div>') +
      panel('Living observations', livingHtml) +
      panel('Learning claims', learnHtml) +
      panel('Relationship highlights', relHtml) +
      '<p class="fl-note">' + esc(card.canonical_history_notes || '') + '</p>';
  }

  async function renderDossiersFloor() {
    var d;
    try { d = await apiGet('/api/expansion/dossiers'); }
    catch (e) { floorShell('Dossiers', 'Keep Expansion', empty('Failed to load: ' + e)); return; }
    if (d && d.enabled === false) {
      floorShell('Dossiers', 'Keep Expansion', empty('Expansion not enabled.'));
      return;
    }
    var agents = d.agents || [];
    if (!FL.dossierTab || !agents.some(function (a) { return a.agent_id === FL.dossierTab; })) {
      FL.dossierTab = (agents[0] && agents[0].agent_id) || 'aria';
    }
    var tabs = AGENTS.map(function (a) {
      var on = FL.dossierTab === a ? ' on' : '';
      return '<button type="button" class="fl-tab' + on +
        '" onclick="FL.dossierTab=\'' + a + '\';renderDossiersFloor()">' + esc(a) + '</button>';
    }).join('');
    var card = agents.filter(function (a) { return a.agent_id === FL.dossierTab; })[0] || agents[0];
    floorShell('Agent Dossiers', 'Canonical + living',
      '<p class="fl-note">' + esc(d.rule || 'Canonical = product lore; living = observed with evidence.') + '</p>' +
      '<div class="fl-tabs">' + tabs + '</div>' + renderDossierBody(card));
  }

  /* —— Journal —— */
  function journalMatches(e, f) {
    if (f.agent && e.agent_id !== f.agent) return false;
    if (f.event_type && String(e.event_type || '').toLowerCase().indexOf(f.event_type.toLowerCase()) < 0) return false;
    if (f.job_id && String(e.job_id || '').toLowerCase().indexOf(f.job_id.toLowerCase()) < 0) return false;
    return true;
  }

  function journalDetailHtml(e) {
    return '<div class="fl-stack"><p><b>' + esc(e.summary || '') + '</b></p>' +
      '<p class="muted">' + esc(e.agent_id) + ' · ' + esc(e.event_type) + ' · ' + fmtTs(e.timestamp) + '</p>' +
      '<p><b>objective_result</b><br>' + esc(e.objective_result || '—') + '</p>' +
      '<p><b>emotion_effects</b><br>' + effectsLine(e.emotion_effects) + '</p>' +
      '<p><b>relationship_effects</b><br>' + effectsLine(e.relationship_effects) + '</p>' +
      '<p class="muted">entry ' + esc(e.entry_id || '') + '</p>' +
      '<p class="muted">events: ' + esc((e.event_ids || []).join(', ') || '—') + '</p>' +
      '<p class="muted">evidence: ' + esc((e.evidence_ids || []).join(', ') || '—') + '</p>' +
      '<p class="muted">job: ' + esc(e.job_id || '—') + ' · conf ' +
      esc(String(e.confidence != null ? e.confidence : '—')) + '</p></div>';
  }

  function floorOpenJournal(entryId) {
    var e = (FL._journalById || {})[entryId];
    if (!e) { showFloorDrawer('Journal', empty('Entry not loaded.')); return; }
    showFloorDrawer('Journal · ' + entryId, journalDetailHtml(e));
  }

  async function renderJournalFloor() {
    var d;
    try { d = await apiGet('/api/expansion/journal'); }
    catch (e) { floorShell('Journal', 'Continuity', empty('Failed: ' + e)); return; }
    var f = FL.journal;
    var agents = d.agents || AGENTS;
    var entries = (d.entries || []).filter(function (e) { return journalMatches(e, f); })
      .sort(function (a, b) { return Number(b.timestamp || 0) - Number(a.timestamp || 0); });
    var filters = '<div class="fl-filters"><select id="fl-j-agent" onchange="FL.journal.agent=this.value;renderJournalFloor()">' +
      '<option value="">all agents</option>' +
      agents.map(function (a) {
        return '<option value="' + esc(a) + '"' + (f.agent === a ? ' selected' : '') + '>' + esc(a) + '</option>';
      }).join('') + '</select>' +
      '<input id="fl-j-et" placeholder="event_type" value="' + esc(f.event_type) +
      '" onkeydown="if(event.key===\'Enter\'){FL.journal.event_type=this.value;renderJournalFloor()}">' +
      '<input id="fl-j-job" placeholder="job_id" value="' + esc(f.job_id) +
      '" onkeydown="if(event.key===\'Enter\'){FL.journal.job_id=this.value;renderJournalFloor()}">' +
      btn('Apply',
        "FL.journal.event_type=document.getElementById('fl-j-et').value;" +
        "FL.journal.job_id=document.getElementById('fl-j-job').value;renderJournalFloor()", true) +
      '</div>';
    floorShell('Journal Browser', 'WHAT HAPPENED',
      '<p class="fl-note">' + esc(d.rule || 'JOURNAL = objective continuity.') + '</p>' +
      filters + '<div class="fl-stack" id="fl-journal-list"></div>');
    var list = document.getElementById('fl-journal-list');
    if (!list) return;
    if (!entries.length) { list.innerHTML = empty('No journal entries match these filters.'); return; }
    FL._journalById = {};
    list.innerHTML = entries.map(function (e) {
      FL._journalById[e.entry_id] = e;
      return '<button type="button" class="fl-card clickable" onclick="' +
        oc('floorOpenJournal', e.entry_id) + '">' +
        '<div><b>JOURNAL</b> ' + pill(e.agent_id || '') + ' ' + pill(e.event_type || '') + '</div>' +
        '<p>' + esc(e.summary || '') + '</p>' +
        '<p class="muted">' + esc(e.objective_result || '') + '</p>' +
        '<p class="muted">emotion: ' + effectsLine(e.emotion_effects) +
        ' · rel: ' + effectsLine(e.relationship_effects) + '</p>' +
        '<p class="muted">' + fmtTs(e.timestamp) + ' · ' + esc(e.entry_id || '') +
        ' · job ' + esc(e.job_id || '—') +
        ' · evidence ' + esc((e.evidence_ids || []).slice(0, 3).join(', ') || '—') + '</p></button>';
    }).join('');
  }

  /* —— Diary —— */
  async function renderDiaryFloor() {
    var d;
    try { d = await apiGet('/api/expansion/diary'); }
    catch (e) { floorShell('Diary', 'WHAT IT MEANT', empty('Failed: ' + e)); return; }
    var agents = d.agents || [];
    if (!FL.diaryTab || !agents.some(function (a) { return a.agent_id === FL.diaryTab; })) {
      FL.diaryTab = (agents[0] && agents[0].agent_id) || 'aria';
    }
    var tabs = agents.map(function (a) {
      var on = FL.diaryTab === a.agent_id ? ' on' : '';
      return '<button type="button" class="fl-tab' + on +
        '" onclick="FL.diaryTab=\'' + esc(a.agent_id) + '\';renderDiaryFloor()">' +
        esc(a.display_name || a.agent_id) + '</button>';
    }).join('');
    var block = agents.filter(function (a) { return a.agent_id === FL.diaryTab; })[0] || agents[0];
    var entries = (block && block.entries) || [];
    var body;
    if (!block) body = empty('No diary agents.');
    else {
      body = '<p class="muted">diary_style: ' + esc(block.diary_style || '—') + ' · ' +
        esc(String(block.count || entries.length)) + ' entries</p>' +
        listCards(entries, function (e) {
          var snap = e.emotional_state_snapshot || {};
          var top = topDims(snap, 4).map(function (kv) { return kv[0] + '=' + kv[1]; }).join(', ');
          var refs = (e.relationship_refs || []).map(function (r) {
            if (typeof r === 'string') return r;
            return (r.target || r.agent_id || '') + ':' + (r.label || r.dim || '');
          }).join(', ');
          return '<article class="fl-diary-entry"><p>' + esc(e.text || '') + '</p>' +
            '<p class="muted" style="font-style:normal;font-family:var(--ot-mono)">snapshot: ' +
            esc(top || '—') + '</p>' +
            '<p class="muted" style="font-style:normal;font-family:var(--ot-mono)">relationships: ' +
            esc(refs || '—') + '</p>' +
            '<p class="muted" style="font-style:normal;font-family:var(--ot-mono)">journals: ' +
            esc((e.source_journal_ids || []).join(', ') || '—') + ' · events: ' +
            esc((e.source_event_ids || []).join(', ') || '—') + ' · ' + fmtTs(e.timestamp) + '</p>' +
            btn('WHY', oc('floorDiaryWhy', block.agent_id, e.diary_id), true) + '</article>';
        }, 'No diary entries for this agent yet.');
    }
    floorShell('Diary Browser', 'WHAT IT MEANT',
      '<p class="fl-note">' + esc(d.rule || 'DIARY = subjective meaning; Journal = objective facts.') + '</p>' +
      '<div class="fl-tabs">' + tabs + '</div>' + body);
  }

  /* —— Relationships —— */
  function floorRelDrillHtml(src, dst) {
    var edge = (FL._relByEdge || {})[src + '|' + dst];
    if (!edge) return empty('Edge not found.');
    var dims = edge.dimensions || {};
    var bars = REL_DIMS.map(function (k) {
      return bar(k, dims[k] != null ? dims[k] : 0);
    }).join('');
    return '<h3 class="fl-h">' + esc(src) + ' → ' + esc(dst) + '</h3>' +
      '<p><b>' + esc(edge.label || '') + '</b></p>' +
      '<p class="muted">' + esc(edge.narrative || '') + '</p>' + bars +
      btn('WHY', oc('floorRelWhy', src, dst), false) +
      '<p class="fl-note">All listed dimensions shown — affinity/trust alone are not the bond.</p>';
  }

  function floorRelDrill(src, dst) {
    FL.relFocus = { src: src, dst: dst };
    var el = document.getElementById('fl-rel-drill');
    if (el) el.innerHTML = floorRelDrillHtml(src, dst);
    else renderRelationshipsFloor();
  }

  async function renderRelationshipsFloor() {
    var d;
    try { d = await apiGet('/api/expansion/relationships'); }
    catch (e) { floorShell('Relationships', 'Directional', empty('Failed: ' + e)); return; }
    var agents = d.agents || AGENTS.concat(['user_primary']);
    var matrix = d.matrix || [];
    var byEdge = {};
    matrix.forEach(function (x) { byEdge[x.source + '|' + x.target] = x; });
    FL._relByEdge = byEdge;

    var head = '<tr><th></th>' + agents.map(function (a) {
      return '<th>' + esc(a) + '</th>';
    }).join('') + '</tr>';
    var rows = agents.map(function (src) {
      var cells = agents.map(function (dst) {
        if (src === dst) return '<td class="diag">—</td>';
        var edge = byEdge[src + '|' + dst];
        if (!edge) return '<td class="muted">·</td>';
        var tops = topDims(edge.dimensions, 2);
        var cell;
        if (tops.length) {
          cell = tops.map(function (kv) {
            return esc(kv[0]) + ' ' + (Math.round(Number(kv[1]) * 100) / 100);
          }).join('<br>');
        } else {
          var dims = edge.dimensions || {};
          cell = 'aff ' + (dims.affinity != null ? dims.affinity : '—') +
            '<br>trust ' + (dims.trust != null ? dims.trust : '—');
        }
        return '<td class="fl-cell" onclick="' + oc('floorRelDrill', src, dst) + '">' +
          cell + '<div class="muted">' + esc(edge.label || '') + '</div></td>';
      }).join('');
      return '<tr><th>' + esc(src) + '</th>' + cells + '</tr>';
    }).join('');

    var drill = FL.relFocus
      ? floorRelDrillHtml(FL.relFocus.src, FL.relFocus.dst)
      : empty('Click a matrix cell for full dimensions.');

    floorShell('Directional Relationships', 'Multi-dimension matrix',
      '<p class="fl-note">' + esc(d.rule || 'Never reduce to one score.') + '</p>' +
      '<div class="fl-two"><div class="fl-panel" style="overflow:auto"><table class="fl-matrix">' +
      head + rows + '</table></div>' +
      '<div class="fl-panel" id="fl-rel-drill">' + drill + '</div></div>');
  }

  /* —— Emotions —— */
  async function renderEmotionsFloor() {
    var d;
    try { d = await apiGet('/api/expansion/emotion'); }
    catch (e) { floorShell('Emotions', 'Affective state', empty('Failed: ' + e)); return; }
    var agents = d.agents || [];
    var blocks = [];
    for (var i = 0; i < agents.length; i++) {
      var a = agents[i];
      var detail = null;
      try { detail = await apiGet('/api/expansion/emotion/' + encodeURIComponent(a.agent_id)); }
      catch (e) { detail = null; }
      var primary = a.primary || (detail && detail.primary) || topDims(a.dimensions, 5);
      var secondary = a.secondary || (detail && detail.secondary) || topDims(a.dimensions, 10).slice(5);
      var base = a.baseline || a.product_baseline || {};
      var cur = a.dimensions || {};
      var prov = a.provenance_tail || (detail && detail.provenance) || [];
      var stress = (detail && detail.stress_behavior) || '';
      var recovery = (detail && detail.recovery_behavior) || '';
      var id = a.agent_id;
      blocks.push('<section class="fl-panel"><h3 class="fl-h">' + esc(a.display_name || id) + '</h3>' +
        '<div class="fl-grid"><div><h4 class="fl-h">primary</h4>' +
        ((primary || []).map(function (kv) {
          return bar(kv[0], kv[1], { onclick: oc('floorEmotionWhy', id, kv[0]) });
        }).join('') || empty('—')) +
        '</div><div><h4 class="fl-h">secondary</h4>' +
        ((secondary || []).map(function (kv) {
          return bar(kv[0], kv[1], { onclick: oc('floorEmotionWhy', id, kv[0]) });
        }).join('') || empty('—')) +
        '</div></div><h4 class="fl-h">baseline vs current</h4><div class="fl-grid">' +
        Object.keys(cur).slice(0, 12).map(function (k) {
          return '<div class="fl-card"><b>' + esc(k) + '</b><p class="muted">base ' +
            esc(String(base[k] != null ? base[k] : '—')) + '</p>' +
            bar('now', cur[k], { onclick: oc('floorEmotionWhy', id, k) }) + '</div>';
        }).join('') + '</div>' +
        (stress || recovery
          ? '<p class="muted">stress: ' + esc(stress || '—') + '<br>recovery: ' + esc(recovery || '—') + '</p>'
          : '') +
        '<h4 class="fl-h">provenance tail</h4>' +
        listCards(prov.slice(-8), function (p) {
          if (typeof p === 'string') return '<div class="fl-card muted">' + esc(p) + '</div>';
          return '<div class="fl-card"><span class="muted">' + esc(p.dim || p.dimension || '') +
            ' · ' + esc(p.source || p.kind || '') + ' · ' + fmtTs(p.ts || p.timestamp) +
            '</span><p>' + esc(p.note || p.detail || p.event_id || JSON.stringify(p).slice(0, 160)) +
            '</p></div>';
        }, 'No provenance events yet.') + '</section>');
    }
    floorShell('Emotional State', 'Runtime EmotionStore',
      '<p class="fl-note">' + esc(d.rule || 'Baselines from product + live decay/recovery.') + '</p>' +
      (blocks.join('') || empty('No agent emotion state loaded.')));
  }

  /* —— War Room —— */
  async function renderWarRoomFloor() {
    var d;
    try { d = await apiGet('/api/expansion/war-room'); }
    catch (e) { floorShell('War Room', 'Vector', empty('Failed: ' + e)); return; }
    if (d && d.enabled === false) {
      floorShell('War Room', 'Vector', empty(d.message || 'Expansion not entitled.'));
      return;
    }
    var ops = d.operations || {};
    var rex = d.rex || {};
    var verifying = (rex.verifying && rex.verifying.cards) || ops.waiting_verify || [];
    var rework = (rex.rework && rex.rework.cards) || (d.recovery && d.recovery.rework_cards) || [];
    var hard = (rex.hard_blocked && rex.hard_blocked.cards) || [];
    var metrics = rex.metrics || {};
    var strip = '<div class="fl-strip">' +
      metric(metrics.active != null ? metrics.active : (ops.active || []).length, 'active') +
      metric((ops.failed || []).length, 'failed') +
      metric(verifying.length, 'verifying') +
      metric(rework.length, 'rework') +
      metric(hard.length, 'hard block') + '</div>';
    var trace = listCards(d.decision_trace || [], function (j) {
      return '<div class="fl-card"><b>' + esc(j.job_id) + '</b> · ' + esc(j.status) + ' · ' +
        esc(j.assigned_agent || '') + '<p class="muted">' + esc(j.request || '') + '</p>' +
        '<p class="muted">evidence: ' + esc((j.evidence || []).join(', ') || '—') +
        (j.error ? ' · err ' + esc(j.error) : '') + '</p>' + jobLink(j.job_id) + '</div>';
    }, 'No decision trace yet.');
    floorShell('War Room', 'Jobs / decisions — not infra telemetry',
      '<div class="fl-panel"><p class="fl-note">Foundation War Room shell — job/decision boards, not the full Keep ops deck.</p></div>' +
      '<p class="fl-note">' + esc(d.note || '') + ' ' +
      esc(d.peer_review_note || rex.peer_review_note || '') + '</p>' + strip +
      '<div class="fl-rail" style="margin:.5rem 0">' +
      btn('Open REX board', "typeof showRexBoard==='function'&&showRexBoard()", false) + '</div>' +
      panel('Active ops', listCards(ops.active || d.active || [], jobCard, 'No active operations.')) +
      panel('Verifying / peer review', listCards(verifying, jobCard, 'Nothing in VERIFYING.')) +
      panel('Blocked', listCards([].concat(ops.blocked || [], hard), jobCard, 'No blockers.')) +
      panel('Failures', listCards(ops.failed || d.failed || [], jobCard, 'No failures.')) +
      panel('Retries / rework', listCards([].concat(rework, (d.recovery && d.recovery.retrying) || []),
        jobCard, 'No rework.')) +
      panel('Incidents', listCards(d.incidents || [], jobCard, 'No incidents.')) +
      panel('Recovery', listCards((d.recovery && d.recovery.retrying) || [], jobCard, 'No recovery queue.')) +
      panel('Decision / evidence trace', trace));
  }

  /* —— Aria Command —— */
  async function renderCommandFloor() {
    var d;
    try { d = await apiGet('/api/expansion/command'); }
    catch (e) { floorShell('Aria Command', 'Coordination floor', empty('Failed: ' + e)); return; }
    if (d && d.enabled === false) {
      floorShell('Aria Command', 'Coordination floor', empty('Expansion not enabled.'));
      return;
    }
    var wl = d.workload || {};
    var roster = listCards(d.roster || [], function (a) {
      return '<div class="fl-card"><b>' + esc(a.display_name || a.agent_id) + '</b> · ' + esc(a.role || '') +
        '<p class="muted">open jobs: ' +
        esc(String(a.open_jobs != null ? a.open_jobs : wl[a.agent_id] || 0)) + '</p>' +
        '<p class="muted">emotion: ' + esc(Object.keys(a.emotion_highlights || {}).map(function (k) {
          return k + '=' + a.emotion_highlights[k];
        }).join(', ') || '—') + '</p></div>';
    }, 'Roster empty.');
    var ready = d.readiness || {};
    var shifts = listCards(d.relationship_shifts || d.emotion_shifts || [], function (s) {
      return '<div class="fl-card"><b>' + esc(s.source) + ' → ' + esc(s.target) + '</b> · ' +
        esc(s.label || '') + '<p class="muted">' + esc(s.narrative || '') + '</p>' +
        btn('WHY', oc('floorRelWhy', s.source, s.target), true) + '</div>';
    }, 'No notable shifts.');
    var auto = Object.keys(d.autonomous_summary || {}).slice(0, 8).map(function (k) {
      return metric(d.autonomous_summary[k], k);
    }).join('') || empty('No REX metrics.');
    floorShell('Aria Command Floor', 'Coordination — not Dashboard',
      '<p class="fl-note">' + esc(d.note ||
        'Aria Command = agent coordination; Dashboard = owner overview.') + '</p>' +
      panel('Roster + workload', roster) +
      panel('Delegations', listCards(d.delegations || [], function (x) {
        return '<div class="fl-card">' + esc(x.from || 'aria') + ' → <b>' + esc(x.to || '') +
          '</b> · ' + esc(x.status || '') + ' · ' + esc(x.domain || '') +
          '<p>' + esc(x.request || '') + '</p>' + jobLink(x.job_id) + '</div>';
      }, 'No delegations.')) +
      panel('Readiness', kvPre(ready, 800)) +
      panel('Alerts', listCards(d.major_alerts || [], jobCard, 'No major alerts.')) +
      panel('Relationship / emotion shifts', shifts) +
      panel('Pending decisions', listCards(d.pending_decisions || [], jobCard, 'None pending.')) +
      panel('Autonomous summary', '<div class="fl-strip">' + auto + '</div>') +
      panel('Blockers', listCards(d.blockers || [], function (c) {
        return jobCard(c.job_id ? c : {
          job_id: c.job_id || c.id, title: c.title,
          status: c.stage || c.status, assigned_agent: c.owner, request: c.title
        });
      }, 'No blockers.')));
  }

  /* —— Intel —— */
  async function renderIntelFloor() {
    var d;
    try { d = await apiGet('/api/expansion/intel'); }
    catch (e) { floorShell('Intel', 'Ledger continuity', empty('Failed: ' + e)); return; }
    if (d && d.enabled === false) {
      floorShell('Intel', 'Ledger continuity', empty('Expansion not enabled.'));
      return;
    }
    var q = (FL.intelQ || '').toLowerCase();
    function match(parts) {
      return !q || parts.join(' ').toLowerCase().indexOf(q) >= 0;
    }
    var mems = (d.important_memories || []).filter(function (m) {
      return match([m.agent_id, m.content, m.memory_id]);
    });
    var events = (d.recent_events || []).filter(function (e) {
      return match([e.event_type, e.actor, e.subject, e.event_id]);
    });
    var journal = (d.journal_timeline || []).filter(function (e) {
      return match([e.summary, e.agent_id, e.event_type, e.job_id]);
    });
    var shared = ((d.learned_claims || {}).shared || []).filter(function (c) {
      return match([c.claim, c.claim_id]);
    });
    var priv = Object.keys((d.learned_claims || {}).private_by_agent || {});
    var livingKeys = Object.keys(d.living_dossiers || {});
    var relEv = (d.relationship_evidence || []).filter(function (x) {
      return match([x.source, x.target, x.label, x.narrative]);
    }).slice(0, 24);

    var privHtml = priv.map(function (aid) {
      var rows = ((d.learned_claims.private_by_agent[aid]) || []).filter(function (c) {
        return match([c.claim, aid]);
      });
      return panel('Private · ' + aid, listCards(rows, function (c) {
        return '<div class="fl-card"><b>' + esc(c.claim) + '</b> ' +
          btn('WHY', oc('floorLearningWhy', c.claim_id), true) + '</div>';
      }, 'None.'));
    }).join('');

    var livingHtml = livingKeys.map(function (aid) {
      var rows = (d.living_dossiers[aid] || []).filter(function (o) {
        return match([aid, o.category, o.value, o.observation_id]);
      });
      return '<div class="fl-card"><b>' + esc(aid) + '</b>' + listCards(rows, function (o) {
        return '<div style="margin-top:.4rem"><span class="muted">' + esc(o.category) + '</span> ' +
          esc(o.value || '') + ' ' +
          btn('WHY', oc('floorLivingWhy', aid, o.observation_id), true) + '</div>';
      }, 'No observations.') + '</div>';
    }).join('') || empty('No living dossiers.');

    floorShell('Intel / Continuity', 'Ledger',
      '<p class="fl-note">' + esc(d.note || '') + ' ' + esc(d.continuity_search_hint || '') + '</p>' +
      '<div class="fl-filters"><input id="fl-intel-q" placeholder="search filter" value="' +
      esc(FL.intelQ) +
      '" onkeydown="if(event.key===\'Enter\'){FL.intelQ=this.value;renderIntelFloor()}">' +
      btn('Filter', "FL.intelQ=document.getElementById('fl-intel-q').value;renderIntelFloor()", true) +
      '</div>' +
      panel('Important memories', listCards(mems, function (m) {
        return '<div class="fl-card"><b>' + esc(m.agent_id) + '</b> · imp ' + esc(String(m.importance)) +
          '<p>' + esc(m.content || '') + '</p><p class="muted">' + esc(m.memory_id || '') + '</p></div>';
      }, 'No high-importance memories.')) +
      panel('Recent events', listCards(events, function (e) {
        return '<div class="fl-card"><b>' + esc(e.event_type) + '</b> · ' + esc(e.actor) +
          ' → ' + esc(e.subject || '') +
          '<p class="muted">' + esc(e.event_id) + ' · ' + fmtTs(e.timestamp) + '</p></div>';
      }, 'No events.')) +
      panel('Journal timeline', listCards(journal.slice(0, 40), function (e) {
        return '<div class="fl-card"><b>JOURNAL</b> ' + esc(e.summary || '') +
          '<p class="muted">' + esc(e.agent_id) + ' · ' + esc(e.event_type) + ' · ' +
          fmtTs(e.timestamp) + '</p></div>';
      }, 'Journal empty.')) +
      panel('Learned claims (shared)', listCards(shared, function (c) {
        return '<div class="fl-card"><b>' + esc(c.claim) + '</b>' +
          '<p class="muted">conf ' + esc(String(c.confidence)) + '</p>' +
          btn('WHY', oc('floorLearningWhy', c.claim_id), true) + '</div>';
      }, 'No shared claims.')) +
      privHtml +
      panel('Living dossiers', livingHtml) +
      panel('Relationship evidence', listCards(relEv, function (x) {
        return '<div class="fl-card"><b>' + esc(x.source) + ' → ' + esc(x.target) + '</b> · ' +
          esc(x.label || '') + '<p class="muted">' + esc(x.narrative || '') + '</p>' +
          btn('WHY', oc('floorRelWhy', x.source, x.target), true) + '</div>';
      }, 'No relationship evidence rows.')));
  }

  /* —— Reports —— */
  async function renderReportsFloor() {
    var d;
    try { d = await apiGet('/api/expansion/reports'); }
    catch (e) { floorShell('Agent Reports', 'Full depth', empty('Failed: ' + e)); return; }
    if (d && d.enabled === false) {
      floorShell('Agent Reports', 'Full depth', empty('Expansion not enabled.'));
      return;
    }
    var body = (d.reports || []).map(function (r) {
      var emo = r.emotion || {};
      var m = r.metrics || {};
      var learn = r.learning || {};
      var claims = [].concat(learn.private || [], learn.shared_keep || []);
      var caps = r.capabilities || {};
      var emoBars = Object.keys(emo).map(function (k) { return [k, emo[k]]; })
        .sort(function (a, b) { return b[1] - a[1]; }).slice(0, 8)
        .map(function (kv) {
          return bar(kv[0], kv[1], { onclick: oc('floorEmotionWhy', r.agent_id, kv[0]) });
        }).join('') || empty('—');
      var diary = r.latest_diary
        ? '<article class="fl-diary-entry">' + esc(r.latest_diary.text || '') +
          (r.latest_diary.diary_id
            ? btn('WHY', oc('floorDiaryWhy', r.agent_id, r.latest_diary.diary_id), true) : '') +
          '</article>'
        : empty('No diary yet.');
      return '<section class="fl-panel"><h3 class="fl-h">' + esc(r.display_name || r.agent_id) +
        ' — ' + esc(r.role || '') + ' · ' + esc(r.archetype || '') + '</h3>' +
        '<p class="muted">runtime ' + esc(r.runtime_status || '—') + ' · success ' +
        (m.success_rate != null ? esc(String(Math.round(m.success_rate * 100)) + '%') : 'n/a') +
        ' · done ' + esc(String(m.completed || 0)) + ' · failed ' + esc(String(m.failed || 0)) + '</p>' +
        '<div class="fl-strip">' + metric((r.active_jobs || []).length, 'active jobs') +
        metric(m.completed || 0, 'completed') + metric(m.failed || 0, 'failed') + '</div>' +
        '<h4 class="fl-h">emotion</h4><div class="fl-grid">' + emoBars + '</div>' +
        '<div class="fl-rail">' + ['jealousy', 'stress', 'concern', 'confidence'].map(function (dim) {
          return btn(dim + ' WHY', oc('floorEmotionWhy', r.agent_id, dim), true);
        }).join('') + '</div>' +
        '<h4 class="fl-h">relationships</h4>' +
        listCards(r.relationship_highlights || [], function (h) {
          return '<div class="fl-card"><b>→ ' + esc(h.target) + '</b> · ' + esc(h.label || '') +
            '<p class="muted">' + esc(h.narrative || '') + '</p>' +
            btn('Rel WHY', oc('floorRelWhy', r.agent_id, h.target), true) + '</div>';
        }, 'None.') +
        '<h4 class="fl-h">journal</h4>' +
        listCards(r.recent_journal || [], function (j) {
          return '<div class="fl-card">' + esc(j.summary || '') +
            '<p class="muted">' + fmtTs(j.timestamp) + '</p></div>';
        }, 'No recent journal.') +
        '<h4 class="fl-h">diary</h4>' + diary +
        '<h4 class="fl-h">living</h4>' +
        listCards(r.living_observations || [], function (o) {
          return '<div class="fl-card"><b>' + esc(o.category || '') + '</b> ' + esc(o.value || '') +
            (o.observation_id
              ? ' ' + btn('WHY', oc('floorLivingWhy', r.agent_id, o.observation_id), true) : '') +
            '</div>';
        }, 'None.') +
        '<h4 class="fl-h">learning</h4>' +
        listCards(claims, function (c) {
          return '<div class="fl-card"><b>' + esc(c.claim) + '</b> ' +
            btn('WHY', oc('floorLearningWhy', c.claim_id), true) + '</div>';
        }, 'No claims yet.') +
        '<h4 class="fl-h">capabilities</h4><div class="fl-card"><p class="muted">voice ' +
        esc(caps.voice || '—') + ' · room ' + esc(caps.room || '—') + '</p>' +
        '<p>strengths: ' + esc((caps.strengths || []).join(', ') || '—') + '</p>' +
        '<p>weaknesses: ' + esc((caps.weaknesses || []).join(', ') || '—') + '</p></div></section>';
    }).join('') || empty('No reports.');
    floorShell('Agent Reports', 'Full provenance depth', body);
  }

  /* —— Creative —— */
  async function renderCreativeFloor() {
    var d;
    try { d = await apiGet('/api/expansion/creative'); }
    catch (e) { floorShell('Creative Studio', 'Muse', empty('Failed: ' + e)); return; }
    var state = d.video_studio_readiness || (d.video_studio && d.video_studio.state) || 'UNAVAILABLE';
    var vs = d.video_studio || {};
    var studio;
    if (state === 'UNAVAILABLE' || state === 'NOT_CONFIGURED') {
      studio = '<div class="fl-panel"><h3 class="fl-h">Video Studio</h3>' +
        pill(state || 'NOT_CONFIGURED', 'warn') +
        '<p class="fl-note">' + esc(d.honest_note || '') + '</p>' +
        '<p class="muted">' + esc(vs.detail || vs.note || vs.message || d.note ||
          'Set a ComfyUI URL to go READY.') + '</p>' +
        '<label>ComfyUI URL</label>' +
        '<input id="fl-comfy-url" value="http://127.0.0.1:8188" style="width:100%;max-width:420px;padding:.4rem;margin:.4rem 0">' +
        '<div class="fl-rail">' +
        btn('Save & probe', "typeof saveComfyUrlFromFloor==='function'&&saveComfyUrlFromFloor()", false) +
        btn('Open setup', "typeof showVideoStudioSetup==='function'&&showVideoStudioSetup()", true) +
        '</div></div>';
    } else {
      studio = '<div class="fl-panel"><h3 class="fl-h">Video Studio</h3>' +
        pill(state, state === 'READY' ? 'ok' : 'warn') +
        '<p class="fl-note">' + esc(d.honest_note || '') + '</p>' +
        (state === 'READY'
          ? '<p class="fl-note">ComfyUI is healthy — Muse Studio endpoint is live. Queue creative jobs below; LTX/music widgets continue to land with Studio deps.</p>'
          : '<p class="muted">Endpoint configured but not healthy yet — check ComfyUI is running.</p>') +
        panel('Queue', listCards(d.creative_queue || [], jobCard, 'Queue empty.')) +
        panel('Active renders', listCards(d.active_renders || [], jobCard, 'No active renders.')) +
        panel('Capabilities', kvPre(d.capabilities || {}, 600)) +
        panel('Discovery', kvPre(vs.discovery || d.video_studio || {}, 800)) +
        panel('Recent output', listCards(d.recent_output || d.recent_creative_jobs || [],
          jobCard, 'No completed creative jobs.')) +
        panel('Runtime context', kvPre(d.runtime_context || {}, 1200)) + '</div>';
    }
    floorShell('Muse Creative Studio', 'Expansion premium — Video Studio',
      '<p class="fl-note">' + esc(d.note || '') + '</p>' +
      '<div class="fl-panel"><h3 class="fl-h">Premium scope</h3>' +
      pill(state === 'READY' ? 'STUDIO LIVE' : 'NEEDS COMFY', state === 'READY' ? 'ok' : 'warn') +
      '<p class="fl-note">Video Studio is an <b>Expansion premium</b> surface. Wire ComfyUI via ' +
      '<span class="mono">OTACON_COMFYUI_URL</span> for READY. Piper TTS does not require Studio.</p></div>' +
      studio +
      panel('Muse creative queue', listCards(d.creative_queue || d.recent_creative_jobs || [],
        jobCard, 'No Muse creative jobs yet.')));
  }

  /* —— Ops —— */
  async function renderOpsFloor() {
    var d;
    try { d = await apiGet('/api/expansion/ops'); }
    catch (e) { floorShell('Operations', 'Sentry', empty('Failed: ' + e)); return; }
    var ha = (d.service_readiness && d.service_readiness.home_assistant) || d.home_assistant || {};
    var health = d.health_observations || {};
    var emo = health.emotion || {};
    var services = d.service_readiness || { home_assistant: ha };
    floorShell('Sentry Operations', 'Security / monitoring',
      '<p class="fl-note">' + esc(d.note || 'Home Assistant remains optional.') + '</p>' +
      panel('Active incidents', listCards(d.active_incidents || [], jobCard, 'No active incidents.')) +
      panel('Resolved incidents', listCards(d.resolved_incidents || [], jobCard, 'No resolved incidents.')) +
      panel('Health observations',
        '<div class="fl-grid">' + (Object.keys(emo).map(function (k) {
          return bar(k, emo[k], { onclick: oc('floorEmotionWhy', 'sentry', k) });
        }).join('') || empty('No health emotion dims.')) + '</div>' +
        '<div class="fl-rail">' +
        btn('concern WHY', oc('floorEmotionWhy', 'sentry', 'concern'), true) +
        btn('fear WHY', oc('floorEmotionWhy', 'sentry', 'fear'), true) + '</div>') +
      panel('Security findings', listCards(d.security_findings || [], jobCard, 'No findings.')) +
      panel('Remediation', listCards(d.autonomous_remediation || [], function (t) {
        return '<div class="fl-card"><b>' + esc(t.capability || t.action || 'tool') + '</b> · ' +
          esc(t.agent_id || '') + '<p class="muted">' +
          esc(t.ok === false ? 'denied/fail' : 'ok') + ' · ' +
          esc(String(t.summary || t.message || t.result || '').slice(0, 200)) + '</p></div>';
      }, 'No remediation actions.')) +
      panel('Monitoring', '<div class="fl-strip">' +
        metric((d.monitoring_state && d.monitoring_state.sentry_open_jobs) || 0, 'open') +
        metric((d.monitoring_state && d.monitoring_state.failed) || 0, 'failed') + '</div>') +
      panel('Service readiness', '<div class="fl-grid">' + Object.keys(services).map(function (k) {
        var v = services[k] || {};
        return '<div class="fl-card"><b>' + esc(k) + '</b> ' +
          pill(v.state || v.status || 'unknown') +
          '<p class="muted">' + esc(v.note || v.message || '') + '</p></div>';
      }).join('') + '</div><p class="muted">HA: ' +
        esc(ha.status || ha.state || 'unknown') + ' — optional</p>') +
      panel('Evidence', listCards(d.evidence || [], function (e) {
        return '<div class="fl-card"><b>' + esc(e.job_id) + '</b>' +
          '<p class="muted">' + esc((e.evidence_ids || []).join(', ') || '—') +
          (e.error ? ' · ' + esc(e.error) : '') + '</p>' + jobLink(e.job_id) + '</div>';
      }, 'No evidence rows.')));
  }

  /* —— Page Builder —— */
  async function floorRegisterPage(ev) {
    if (ev && ev.preventDefault) ev.preventDefault();
    var form = document.getElementById('fl-page-form');
    if (!form) return false;
    var fd = new FormData(form);
    function split(s) {
      return String(s || '').split(',').map(function (x) { return x.trim(); }).filter(Boolean);
    }
    var payload = {
      page_id: fd.get('page_id'),
      name: fd.get('name'),
      route: fd.get('route'),
      owner_agent: fd.get('owner_agent') || 'aria',
      icon: fd.get('icon') || 'PG',
      description: fd.get('description') || '',
      required_capabilities: split(fd.get('required_capabilities')),
      permissions: split(fd.get('permissions')),
      health_source: fd.get('health_source') || '',
      enabled: form.querySelector('[name=enabled]').checked
    };
    var msg = document.getElementById('fl-page-msg');
    try {
      var r = await api('/api/expansion/pages/register', payload);
      if (msg) {
        msg.textContent = r.ok
          ? ('Registered ' + ((r.data && r.data.page && r.data.page.page_id) || payload.page_id))
          : ('Rejected: ' + ((r.data && r.data.error && r.data.error.message) || r.status));
      }
      if (r.ok) setTimeout(function () { renderPageBuilderFloor(); }, 400);
    } catch (e) {
      if (msg) msg.textContent = String(e);
    }
    return false;
  }

  async function renderPageBuilderFloor() {
    var d;
    try { d = await apiGet('/api/expansion/rooms'); }
    catch (e) { floorShell('Page Builder', 'Registry', empty('Failed: ' + e)); return; }
    var rooms = d.rooms || [];
    var list = listCards(rooms, function (r) {
      var route = r.route || '';
      var kind = (typeof roomKindFromRoute === 'function') ? roomKindFromRoute(route) : '';
      var openBtn = kind
        ? '<button type="button" class="cc-btn" onclick="showExpansionSurface(\'' + esc(kind) + '\')">Open</button>'
        : '<span class="muted">no SPA route</span>';
      return '<div class="fl-card"><b>' + esc(r.name || r.page_id) + '</b> ' +
        pill(r.enabled ? 'enabled' : 'disabled', r.enabled ? 'ok' : 'warn') +
        '<p class="muted">' + esc(route) + ' · owner ' + esc(r.owner_agent) + ' · ' +
        esc(r.icon || '') + ' · ' + esc(r.kind || '') + '</p>' +
        '<p class="muted">' + esc(r.description || '') + '</p>' +
        '<p class="muted">caps: ' + esc((r.required_capabilities || []).join(', ') || '—') +
        ' · perms: ' + esc((r.permissions || []).join(', ') || '—') + '</p>' +
        '<p class="muted">health: ' + esc(r.health_source || '—') + '</p>' +
        '<div style="margin-top:8px">' + openBtn + '</div></div>';
    }, 'Registry empty.');
    var form =
      '<form class="fl-form" id="fl-page-form" onsubmit="return floorRegisterPage(event)">' +
      '<label>page_id<input name="page_id" required></label>' +
      '<label>name<input name="name" required></label>' +
      '<label>route<input name="route" required placeholder="/my-room"></label>' +
      '<label>owner_agent<select name="owner_agent">' +
      AGENTS.map(function (a) { return '<option value="' + a + '">' + a + '</option>'; }).join('') +
      '</select></label>' +
      '<label>icon<input name="icon" value="PG"></label>' +
      '<label>description<input name="description"></label>' +
      '<label>required_capabilities<input name="required_capabilities" placeholder="comma,separated"></label>' +
      '<label>permissions<input name="permissions" placeholder="comma,separated"></label>' +
      '<label>health_source<input name="health_source"></label>' +
      '<label class="chk"><input type="checkbox" name="enabled" checked> enabled</label>' +
      '<div>' + btn('Register page', "document.getElementById('fl-page-form').requestSubmit()", false) +
      '</div></form>' +
      '<p class="fl-note">Allowlisted registry fields only — no code injection.</p>' +
      '<div id="fl-page-msg" class="muted"></div>';
    floorShell('Page / Room Registry', 'Page Builder',
      panel('Registered pages', list) + panel('Register page', form));
  }

  /* —— Command Center —— */
  async function composeDashboardFallback() {
    var out = {
      enabled: true, surface: 'command_center_composed',
      note: 'Composed fallback — dashboard endpoint disabled or empty.'
    };
    try { out.command = await apiGet('/api/expansion/command'); } catch (e) { out.command = {}; }
    try { out.emotion = await apiGet('/api/expansion/emotion'); } catch (e) { out.emotion = { agents: [] }; }
    try { out.war = await apiGet('/api/expansion/war-room'); } catch (e) { out.war = {}; }
    try { out.learn = await apiGet('/api/expansion/learning'); } catch (e) { out.learn = {}; }
    var cmd = out.command || {};
    out.owner = { id: 'user_primary', label: 'Owner' };
    out.system_status = { foundation: cmd.readiness || {}, rex_metrics: cmd.autonomous_summary || {} };
    out.roster = (out.emotion.agents || cmd.roster || []).map(function (a) {
      var emo = {};
      var src = a.primary || Object.keys(a.emotion_highlights || {}).map(function (k) {
        return [k, a.emotion_highlights[k]];
      }) || [];
      (src || []).slice(0, 5).forEach(function (kv) {
        if (Array.isArray(kv)) emo[kv[0]] = kv[1];
      });
      if (!Object.keys(emo).length && a.emotion_highlights) emo = a.emotion_highlights;
      return {
        agent_id: a.agent_id,
        display_name: a.display_name || a.agent_id,
        role: a.role || '',
        emotion: emo,
        baseline: a.baseline || {}
      };
    });
    out.active_autonomous_jobs = cmd.active_jobs ||
      (out.war.operations && out.war.operations.active) || [];
    out.alerts = cmd.major_alerts || out.war.failed || [];
    out.recent_events = [];
    out.relationship_shifts = cmd.relationship_shifts || [];
    out.learning_highlights = (out.learn.shared_keep || []).slice(0, 8);
    out.package_readiness = cmd.readiness || {};
    return out;
  }

  async function renderCommandCenterFloor() {
    var d;
    try {
      d = await apiGet('/api/expansion/dashboard');
      if (!d || d.enabled === false) d = await composeDashboardFallback();
    } catch (e) {
      d = await composeDashboardFallback();
    }
    var owner = d.owner || {};
    var sys = d.system_status || {};
    var ready = d.package_readiness || sys.foundation || {};
    var metrics = sys.rex_metrics || {};
    var readyLabel = ready.overall || ready.status ||
      (ready.ok != null ? (ready.ok ? 'ready' : 'limited') : 'status');
    floorShell('Command Center', 'Owner overview',
      '<p class="fl-note">' + esc(d.note ||
        'Dashboard = owner overview. Aria Command = coordination floor.') + '</p>' +
      '<div class="fl-strip">' +
      '<div class="fl-card" style="min-width:160px"><span class="fl-h">Owner</span><div><b>' +
      esc(owner.label || owner.id || 'Owner') + '</b></div></div>' +
      metric(metrics.active != null ? metrics.active : (d.active_autonomous_jobs || []).length, 'autonomous') +
      metric((d.alerts || []).length, 'alerts') +
      metric((d.roster || []).length, 'agents') +
      pill(readyLabel, 'ok') + '</div>' +
      panel('System status', kvPre({ foundation: sys.foundation || ready, rex: metrics }, 1000)) +
      panel('Five-agent roster', '<div class="fl-grid">' +
        ((d.roster || []).map(function (a) {
          return '<div class="fl-card"><b>' + esc(a.display_name || a.agent_id) + '</b> · ' +
            esc(a.role || '') + '<p class="muted">' +
            esc(Object.keys(a.emotion || {}).map(function (k) {
              return k + '=' + a.emotion[k];
            }).join(', ') || '—') + '</p></div>';
        }).join('') || empty('Roster empty.')) + '</div>') +
      panel('Active autonomous jobs',
        listCards(d.active_autonomous_jobs || [], jobCard, 'No autonomous jobs running.')) +
      panel('Alerts', listCards(d.alerts || [], jobCard, 'No alerts.')) +
      panel('Recent events', listCards(d.recent_events || [], function (e) {
        return '<div class="fl-card"><b>' + esc(e.event_type) + '</b> ' + esc(e.actor) +
          ' · ' + esc(e.subject || '') +
          '<p class="muted">' + fmtTs(e.timestamp) + ' · ' + esc(e.event_id || '') + '</p></div>';
      }, 'No recent events.')) +
      panel('Relationship shifts', listCards(d.relationship_shifts || [], function (s) {
        return '<div class="fl-card"><b>' + esc(s.source) + ' → ' + esc(s.target) + '</b> · ' +
          esc(s.label || '') + '<p class="muted">' + esc(s.narrative || '') + '</p>' +
          btn('WHY', oc('floorRelWhy', s.source, s.target), true) + '</div>';
      }, 'No shifts flagged.')) +
      panel('Learning highlights', listCards(d.learning_highlights || [], function (c) {
        return '<div class="fl-card"><b>' + esc(c.claim || '') + '</b> ' +
          (c.claim_id ? btn('WHY', oc('floorLearningWhy', c.claim_id), true) : '') + '</div>';
      }, 'No shared learning highlights.')) +
      panel('Readiness', kvPre(ready, 900)) +
      panel('Floor navigation', floorNavTiles('dashboard')));
  }

  var FLOOR_KINDS = {
    dossiers: renderDossiersFloor,
    journal: renderJournalFloor,
    diary: renderDiaryFloor,
    relationships: renderRelationshipsFloor,
    emotion: renderEmotionsFloor,
    emotions: renderEmotionsFloor,
    'war-room': renderWarRoomFloor,
    command: renderCommandFloor,
    intel: renderIntelFloor,
    reports: renderReportsFloor,
    creative: renderCreativeFloor,
    ops: renderOpsFloor,
    rooms: renderPageBuilderFloor,
    'page-builder': renderPageBuilderFloor,
    dashboard: renderCommandCenterFloor,
    'command-center': renderCommandCenterFloor
  };

  Object.assign(window, {
    FL: FL,
    FLOOR_KINDS: FLOOR_KINDS,
    floorShell: floorShell,
    showFloorDrawer: showFloorDrawer,
    closeFloorDrawer: closeFloorDrawer,
    floorLivingWhy: floorLivingWhy,
    floorDiaryWhy: floorDiaryWhy,
    floorEmotionWhy: floorEmotionWhy,
    floorRelWhy: floorRelWhy,
    floorLearningWhy: floorLearningWhy,
    floorOpenJournal: floorOpenJournal,
    floorRelDrill: floorRelDrill,
    floorRegisterPage: floorRegisterPage,
    renderDossiersFloor: renderDossiersFloor,
    renderJournalFloor: renderJournalFloor,
    renderDiaryFloor: renderDiaryFloor,
    renderRelationshipsFloor: renderRelationshipsFloor,
    renderEmotionsFloor: renderEmotionsFloor,
    renderWarRoomFloor: renderWarRoomFloor,
    renderCommandFloor: renderCommandFloor,
    renderIntelFloor: renderIntelFloor,
    renderReportsFloor: renderReportsFloor,
    renderCreativeFloor: renderCreativeFloor,
    renderOpsFloor: renderOpsFloor,
    renderPageBuilderFloor: renderPageBuilderFloor,
    renderCommandCenterFloor: renderCommandCenterFloor
  });
})();
