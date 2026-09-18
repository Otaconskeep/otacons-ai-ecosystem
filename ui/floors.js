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


  var ASSET_V = 'roster-art-2';
  function agentAsset(id, file) {
    return '/assets/' + id + '/' + file + '?v=' + ASSET_V;
  }
  function readinessHud(obj) {
    var o = obj || {};
    var keys = Object.keys(o);
    if (!keys.length) return empty('No readiness signals yet.');
    return '<div class="fl-ready-grid">' + keys.map(function (k) {
      var v = o[k];
      var state = '';
      var detail = '';
      if (v && typeof v === 'object') {
        state = String(v.state || v.status || v.ready || v.ok || '').toLowerCase();
        detail = String(v.detail || v.message || v.reason || v.note || '');
        if (!detail) {
          try { detail = JSON.stringify(v).slice(0, 140); } catch (e) { detail = ''; }
        }
      } else {
        state = String(v == null ? '' : v).toLowerCase();
        detail = String(v == null ? '—' : v);
      }
      var cls = 'warn';
      if (/ready|ok|true|live|online|pass|1/.test(state)) cls = 'ok';
      else if (/fail|error|down|false|unavailable|missing|0/.test(state)) cls = 'bad';
      else if (/limited|degraded|offline|pending|setup|not_configured|not_installed|needs_credential|needs_authorization|needs_setup|installing/.test(state)) cls = 'warn';
      var label = state ? state.toUpperCase() : 'SIGNAL';
      return '<div class="fl-ready ' + cls + '"><div class="fl-ready-top"><b></b><span>' + esc(k.replace(/_/g, ' ')) +
        '</span><em>' + esc(label) + '</em></div><p>' + esc(detail || '—') + '</p></div>';
    }).join('') + '</div>';
  }

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
      '.fl-note{font-size:.78rem;color:var(--ot-muted);margin:0 0 .75rem}',
      '.fl-diary-page{font-family:Georgia,"Times New Roman",serif;font-size:1.05rem;line-height:1.75;color:#e8f0ee;',
      'background:linear-gradient(180deg,rgba(18,28,32,.92),rgba(8,14,18,.96));',
      'border:1px solid rgba(46,230,214,.22);padding:1.1rem 1.25rem;margin:.55rem 0;',
      'box-shadow:inset 0 0 40px rgba(46,230,214,.04)}',
      '.fl-diary-page .when{font-family:var(--ot-mono);font-size:.68rem;letter-spacing:.08em;color:var(--ot-muted);margin:0 0 .55rem}',
      '.fl-room-war .fl-strip{gap:.75rem}',
      '.fl-gauge{min-width:88px;padding:.55rem .7rem;border:1px solid rgba(255,77,154,.35);background:rgba(20,8,14,.55)}',
      '.fl-gauge .n{font-size:1.25rem;color:#ff8fb8;font-weight:700}',
      '.fl-gauge .l{font-size:.65rem;letter-spacing:.1em;text-transform:uppercase;color:var(--ot-muted)}'
    ].join('');
    document.head.appendChild(s);
  }

  function foundationShellBanner() {
    return '';
  }

  function floorShell(title, kicker, bodyHtml, extraMeta, theme) {
    ensureFloorStyles();
    setBodyMode('home');
    var themeCls = theme ? (' fl-theme-' + String(theme)) : '';
    var meta = (extraMeta || '') +
      btn('Home', 'showHome()', true) +
      btn('Codec', "typeof showChat==='function'&&showChat()", false);
    appRoot().innerHTML =
      '<div class="home fl' + themeCls + '">' +
      '<header class="fl-mast"><div><p class="kicker">' + esc(kicker || 'Keep Expansion') +
      '</p><h1>' + esc(title) + '</h1></div><div class="meta">' + meta + '</div></header>' +
      '<div class="fl-body">' + foundationShellBanner() + (bodyHtml || '') + '</div>' +
      '<div id="fl-drawer" class="fl-drawer" hidden><div class="fl-drawer-panel" role="dialog" aria-modal="true">' +
      '<div style="display:flex;justify-content:space-between;gap:.5rem;align-items:center;margin-bottom:.5rem">' +
      '<h3 id="fl-drawer-title">WHY</h3>' + btn('Close', 'closeFloorDrawer()', true) +
      '</div><div id="fl-drawer-body"></div></div></div></div>';
    if (theme === 'intel') setTimeout(function () { startPsalmRain('fl-matrix-rain'); }, 30);
    if (theme === 'studio' || theme === 'ops' || theme === 'emotion' || theme === 'genome') {
      try { if (typeof otSfx === 'function') otSfx('transmit'); } catch (_e) {}
    }
  }

  /* Psalms fragments (KJV public domain) for Intel matrix rain */
  var PSALM_RAIN = [
    'The Lord is my shepherd I shall not want',
    'He maketh me to lie down in green pastures',
    'He leadeth me beside the still waters',
    'He restoreth my soul',
    'Yea though I walk through the valley of the shadow of death',
    'I will fear no evil for thou art with me',
    'Thy rod and thy staff they comfort me',
    'Thou preparest a table before me',
    'My cup runneth over',
    'Surely goodness and mercy shall follow me',
    'I will lift up mine eyes unto the hills',
    'From whence cometh my help',
    'My help cometh from the Lord',
    'The Lord is thy keeper',
    'The Lord shall preserve thee from all evil',
    'Create in me a clean heart O God',
    'Renew a right spirit within me',
    'Cast me not away from thy presence',
    'Restore unto me the joy of thy salvation',
    'Bless the Lord O my soul',
    'Who forgiveth all thine iniquities',
    'Who healeth all thy diseases',
    'Who redeemeth thy life from destruction',
    'The heavens declare the glory of God',
    'Day unto day uttereth speech',
    'Night unto night sheweth knowledge',
    'The law of the Lord is perfect',
    'The testimony of the Lord is sure',
    'More to be desired are they than gold',
    'Let the words of my mouth be acceptable',
    'God is our refuge and strength',
    'A very present help in trouble',
    'Be still and know that I am God',
    'O give thanks unto the Lord for he is good',
    'For his mercy endureth for ever',
    'Thy word is a lamp unto my feet',
    'And a light unto my path',
    'Search me O God and know my heart',
    'Try me and know my thoughts',
    'Lead me in the way everlasting'
  ];

  function startPsalmRain(canvasParentId) {
    var wrap = document.getElementById(canvasParentId);
    if (!wrap) return;
    wrap.innerHTML = '';
    var canvas = document.createElement('canvas');
    wrap.appendChild(canvas);
    var ctx = canvas.getContext('2d');
    if (!ctx) return;
    var w = 0, h = 0, cols = [], font = 13;
    function resize() {
      w = canvas.width = Math.max(wrap.clientWidth || 800, 320);
      h = canvas.height = Math.max(wrap.clientHeight || 480, 320);
      var n = Math.floor(w / font);
      cols = [];
      for (var i = 0; i < n; i++) {
        cols.push({
          y: Math.random() * h,
          speed: 0.6 + Math.random() * 1.8,
          text: PSALM_RAIN[i % PSALM_RAIN.length],
          offset: Math.floor(Math.random() * 40)
        });
      }
    }
    resize();
    if (window.__psalmRainRaf) cancelAnimationFrame(window.__psalmRainRaf);
    function tick() {
      ctx.fillStyle = 'rgba(2,6,10,0.12)';
      ctx.fillRect(0, 0, w, h);
      ctx.font = font + 'px "Courier New", monospace';
      for (var i = 0; i < cols.length; i++) {
        var c = cols[i];
        var ch = c.text[(Math.floor(c.y / font) + c.offset) % c.text.length] || '·';
        var x = i * font;
        ctx.fillStyle = i % 7 === 0 ? 'rgba(255,120,140,0.85)' : 'rgba(46,230,214,0.55)';
        ctx.fillText(ch, x, c.y);
        c.y += c.speed * font * 0.35;
        if (c.y > h + 40) {
          c.y = -Math.random() * 80;
          c.text = PSALM_RAIN[Math.floor(Math.random() * PSALM_RAIN.length)];
        }
      }
      window.__psalmRainRaf = requestAnimationFrame(tick);
    }
    tick();
    window.addEventListener('resize', function () {
      if (document.getElementById(canvasParentId)) resize();
    }, { once: false });
  }

  function cineHero(eyebrow, title, copy) {
    return '<div class="fl-cine-hero"><p class="eyebrow">' + esc(eyebrow) + '</p><h2>' +
      esc(title) + '</h2><p>' + esc(copy) + '</p></div>';
  }

  function cineWidgets(items) {
    return '<div class="fl-cine-widgets">' + (items || []).map(function (it) {
      return '<button type="button" class="fl-cine-w" ' +
        (it.onclick ? ('onclick="' + it.onclick + '"') : '') +
        '><span class="k">' + esc(it.k) + '</span><span class="v ' + esc(it.cls || '') + '">' +
        esc(it.v) + '</span></button>';
    }).join('') + '</div>';
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

  function ariaGuideCard(who, text) {
    var id = String(who || 'aria').toLowerCase();
    if (id !== 'muse' && id !== 'aria') id = 'aria';
    var label = id === 'muse' ? 'Muse // guiding' : 'Aria // guiding';
    var src = agentAsset(id, id + '.webp');
    var fallback = agentAsset('aria', 'aria.webp');
    return '<div class="fl-aria-guide">' +
      '<img src="' + src + '" alt="" width="72" height="72" ' +
      'onerror="this.onerror=null;this.src=\'' + fallback.replace(/'/g, '') + '\'">' +
      '<div><p class="fl-aria-kicker">' + esc(label) + '</p>' +
      '<p class="fl-aria-copy">' + esc(text || '') + '</p></div></div>';
  }

  /* —— Dossiers (Central Agency / secret-agent folder) —— */
  function dosRow(label, value) {
    if (value == null || value === '' || (Array.isArray(value) && !value.length)) {
      return '<tr><th>' + esc(label) + '</th><td class="fl-dos-empty">—</td></tr>';
    }
    var v = Array.isArray(value) ? value.map(function (x) { return esc(String(x)); }).join(', ') : esc(String(value));
    return '<tr><th>' + esc(label) + '</th><td>' + v + '</td></tr>';
  }

  function dosTable(title, rowsHtml) {
    return '<section class="fl-dos-panel"><h3 class="fl-dos-h">◆ ' + esc(title) + '</h3>' +
      '<table class="fl-dos-table"><tbody>' + rowsHtml + '</tbody></table></section>';
  }

  function dosChips(arr) {
    if (!arr || !arr.length) return '<span class="fl-dos-empty">—</span>';
    return '<div class="fl-dos-chips">' + arr.map(function (x) {
      return '<span class="fl-dos-chip">' + esc(String(x)) + '</span>';
    }).join('') + '</div>';
  }

  function dosRedact(text, absent) {
    if (absent) return '<span class="fl-dos-redact" title="Not emphasized in this product dossier">████████</span>';
    return esc(text || '—');
  }

  function renderVulnGroups(byKind) {
    var bk = byKind || {};
    return VULN_KINDS.map(function (kind) {
      var items = bk[kind] || [];
      var body = items.length ? items.map(function (v) {
        var absent = !!v.intentional_absence;
        return '<div class="fl-dos-vuln' + (absent ? ' muted-abs' : '') + '">' +
          '<div><b>' + esc(v.label || kind) + '</b> ' + pill(kind) +
          (absent ? ' ' + pill('REDACTED') : '') +
          (v.intensity != null ? ' ' + pill('i=' + v.intensity) : '') + '</div>' +
          '<p>' + dosRedact(v.description || '', absent) + '</p>' +
          (v.triggers && v.triggers.length && !absent
            ? '<p class="muted">triggers: ' + esc(v.triggers.join(', ')) + '</p>' : '') +
          '</div>';
      }).join('') : '<p class="fl-dos-empty">No entries for ' + esc(kind) + '.</p>';
      return dosTable(kind.replace(/_/g, ' ').toUpperCase(), '<tr><td colspan="2">' + body + '</td></tr>');
    }).join('');
  }

  function renderPolaroidBank(card) {
    var id = card.agent_id;
    var src = agentAsset(id, id + '.webp');
    var shots = [
      { cap: 'Front Profile', rot: -6, filter: '' },
      { cap: 'Operations Board', rot: 4, filter: 'fl-pol-ops' },
      { cap: 'Surveillance Still', rot: -3, filter: 'fl-pol-surv' },
      { cap: 'Agency Archive', rot: 7, filter: 'fl-pol-arch' }
    ];
    return '<aside class="fl-dos-photos">' +
      '<div class="fl-dos-ribbon">TOP SECRET</div>' +
      '<p class="fl-dos-photo-sub">FIELD IMAGERY / POLAROID STACK</p>' +
      '<div class="fl-dos-polaroids">' + shots.map(function (s, i) {
        return '<figure class="fl-dos-polaroid" style="--rot:' + s.rot + 'deg">' +
          '<div class="fl-dos-polaroid-frame ' + s.filter + '">' +
          '<img src="' + src + '" alt="" loading="eager">' +
          '<i class="fl-dos-classified">CLASSIFIED</i><i class="fl-dos-scan"></i></div>' +
          '<figcaption>' + esc(s.cap) + '</figcaption></figure>';
      }).join('') + '</div></aside>';
  }

  function renderDossierBody(card) {
    if (!card) return empty('Agent dossier unavailable.');
    var id = card.agent_id;
    var ident = card.identity || {};
    var ch = card.character || {};
    var bg = card.background || {};
    var caps = card.capabilities || {};
    var social = card.social || {};
    var stress = card.stress || {};
    var prefs = card.preferences || {};
    var fw = card.frameworks || {};
    var phys = card.physical || {};
    var taste = card.taste || {};
    var culture = card.culture || {};
    var presence = card.social_presence || {};
    var living = (card.living && card.living.observations) || [];
    var learn = card.learning || {};
    var claims = [].concat(learn.private || [], learn.shared_keep || learn.shared || []);
    var base = card.emotional_baseline || {};
    var cur = card.current_emotion || {};
    var dims = [];
    Object.keys(base).forEach(function (k) { if (dims.indexOf(k) < 0) dims.push(k); });
    Object.keys(cur).forEach(function (k) { if (dims.indexOf(k) < 0) dims.push(k); });
    dims = dims.slice(0, 12);
    var roles = ((card.permissions || {}).role_permissions) || [];
    var rooms = ((card.permissions || {}).room_permissions) || [];

    var mast = '<header class="fl-dos-mast">' +
      '<div class="fl-dos-stamps"><span class="fl-dos-stamp ok">ACTIVE FILE</span>' +
      '<span class="fl-dos-stamp">KEEP ROSTER</span>' +
      (roles[0] ? '<span class="fl-dos-stamp">' + esc(String(roles[0]).toUpperCase()) + '</span>' : '') +
      '</div>' +
      '<p class="fl-dos-agency">CENTRAL AGENCY DOSSIER</p>' +
      '<h2 class="fl-dos-codename">' + esc(ident.display_name || id) + '</h2>' +
      '<p class="fl-dos-tag">' + esc(ch.role || ident.short_bio || '') + ' · ' +
      esc(ch.archetype || '') + ' · ' + esc(ident.pronouns || '') + '</p>' +
      '</header>';

    var identity = dosTable('IDENTITY',
      dosRow('Codename', ident.display_name) +
      dosRow('Role', ch.role) +
      dosRow('Archetype', ch.archetype) +
      dosRow('Pronouns', ident.pronouns) +
      dosRow('Presentation', ident.presentation) +
      dosRow('Alignment', (ch.values || []).slice(0, 3).join(' · ')) +
      dosRow('Authority', roles.join(', ')) +
      dosRow('Duty rooms', rooms.join(', ')) +
      dosRow('Specialties', (prefs.interests || []).slice(0, 6).join(', ')) +
      dosRow('Skills', (caps.strengths || []).join(', ')) +
      dosRow('Education', card.education || bg.education_training) +
      dosRow('Short bio', ident.short_bio)
    );

    var physical = dosTable('PHYSICAL TRAITS',
      dosRow('Build', phys.build) +
      dosRow('Distinguishing', phys.distinguishing) +
      dosRow('Field notes', phys.presentation_notes) +
      dosRow('Presentation', ident.presentation)
    );

    var professional = dosTable('PROFESSIONAL PROFILE',
      dosRow('Role', ch.role) +
      dosRow('Origin', bg.origin_summary) +
      dosRow('History', bg.history || card.biography) +
      dosRow('Career', Array.isArray(card.career) ? card.career : bg.career) +
      dosRow('Culture', culture.background || culture.upbringing) +
      dosRow('Strengths', caps.strengths) +
      dosRow('Weaknesses', caps.weaknesses) +
      dosRow('Blind spots', caps.blind_spots) +
      dosRow('Failure modes', caps.failure_modes)
    );

    var psych = dosTable('PSYCHOLOGICAL PROFILE',
      dosRow('Temperament', ch.communication_style) +
      dosRow('Humor', ch.humor_style) +
      dosRow('Diary voice', ch.diary_style) +
      dosRow('Emotional truth', card.emotional_truth) +
      dosRow('Core wound', card.core_wound) +
      dosRow('Trust behavior', social.trust_behavior) +
      dosRow('Conflict', social.conflict_behavior) +
      dosRow('Stress behavior', stress.stress_behavior) +
      dosRow('Recovery', stress.recovery_behavior) +
      dosRow('Values', ch.values) +
      dosRow('Morals', ch.morals)
    );

    var frameworks = dosTable('PERSONALITY FRAMEWORKS',
      dosRow('MBTI', fw.mbti) +
      dosRow('Enneagram', fw.enneagram) +
      dosRow('Archetype', ch.archetype) +
      dosRow('Notes', fw.big_five_note)
    );

    var tasteHtml = dosTable('TASTE & MUSIC',
      dosRow('Music', taste.music) +
      dosRow('Film', taste.film) +
      dosRow('Games', taste.games) +
      dosRow('Food', taste.food) +
      dosRow('Pop culture', taste.pop_culture) +
      dosRow('Likes', prefs.likes) +
      dosRow('Dislikes', prefs.dislikes) +
      dosRow('Interests', prefs.interests)
    );

    var socialMedia = '<section class="fl-dos-panel"><h3 class="fl-dos-h">◆ SOCIAL PRESENCE</h3>' +
      '<p class="fl-dos-note">Keep-native channels — not a third-party feed clone.</p>' +
      '<div class="fl-dos-social">' +
      ((presence.channels || []).map(function (c) {
        return '<article class="fl-dos-social-card">' +
          '<div class="fl-dos-social-net">' + esc(c.network || '') + '</div>' +
          '<div class="fl-dos-social-handle">' + esc(c.handle || '') + '</div>' +
          '<p>' + esc(c.style || '') + '</p></article>';
      }).join('') || '<p class="fl-dos-empty">No channels on file.</p>') +
      '</div></section>';

    var trauma = dosTable('TRAUMA / STRESS PROFILE',
      dosRow('Core wound', card.core_wound) +
      dosRow('Stress behavior', stress.stress_behavior) +
      dosRow('Recovery', stress.recovery_behavior) +
      dosRow('Attachment', social.attachment_style) +
      dosRow('Jealousy sensitivity', social.jealousy_sensitivity) +
      dosRow('Possessiveness', social.possessiveness) +
      dosRow('Rivalry', social.rivalry_behavior)
    );

    var keyRel = dosTable('KEY RELATIONSHIPS',
      '<tr><td colspan="2"><ul class="fl-dos-list">' +
      ((card.key_relationships || []).map(function (r) {
        return '<li>' + esc(r) + '</li>';
      }).join('') || '<li class="fl-dos-empty">—</li>') +
      '</ul></td></tr>'
    );

    var emoCmp = dims.length ? '<div class="fl-dos-emo">' + dims.map(function (k) {
      return '<div class="fl-dos-emo-row"><b>' + esc(k) + '</b>' +
        bar('now', cur[k] != null ? cur[k] : 0, { onclick: oc('floorEmotionWhy', id, k) }) +
        '<span class="muted">base ' + esc(String(base[k] != null ? base[k] : '—')) + '</span></div>';
    }).join('') + '</div>' : empty('No emotion dimensions.');

    var livingHtml = listCards(living, function (o) {
      return '<div class="fl-card"><b>' + esc(o.category || 'obs') + '</b> · conf ' +
        esc(String(o.confidence)) + '<p>' + esc(o.value || '') + '</p>' +
        btn('WHY', oc('floorLivingWhy', id, o.observation_id), true) + '</div>';
    }, 'No living observations yet.');

    var learnHtml = listCards(claims, function (c) {
      return '<div class="fl-card"><b>' + esc(c.claim || '') + '</b>' +
        '<p class="muted">conf ' + esc(String(c.confidence)) + '</p>' +
        btn('WHY', oc('floorLearningWhy', c.claim_id), true) + '</div>';
    }, 'No graduated learning claims.');

    var relHtml = listCards(card.relationship_highlights || [], function (r) {
      return '<div class="fl-card"><b>' + esc(id) + ' → ' + esc(r.target) + '</b> · ' + esc(r.label || '') +
        '<p class="muted">' + esc(r.narrative || '') + '</p>' +
        btn('Rel WHY', oc('floorRelWhy', id, r.target), true) + '</div>';
    }, 'No relationship highlights.');

    var left = '<div class="fl-dos-col">' + identity + physical + professional + psych +
      frameworks + tasteHtml + socialMedia + trauma + keyRel +
      '<section class="fl-dos-panel"><h3 class="fl-dos-h">◆ VULNERABILITY GROUPS</h3>' +
      renderVulnGroups((card.vulnerabilities || {}).by_kind) + '</section>' +
      '<section class="fl-dos-panel"><h3 class="fl-dos-h">◆ EMOTIONAL BASELINE VS LIVE</h3>' + emoCmp + '</section>' +
      '<section class="fl-dos-panel"><h3 class="fl-dos-h">◆ LIVING OBSERVATIONS</h3>' + livingHtml + '</section>' +
      '<section class="fl-dos-panel"><h3 class="fl-dos-h">◆ LEARNING</h3>' + learnHtml + '</section>' +
      '<section class="fl-dos-panel"><h3 class="fl-dos-h">◆ RELATIONSHIP HIGHLIGHTS</h3>' + relHtml + '</section>' +
      '<p class="fl-dos-foot">' + esc(card.canonical_history_notes || '') + '</p></div>';

    return '<div class="fl-dos-shell">' + mast +
      '<div class="fl-dos-grid">' + left + renderPolaroidBank(card) + '</div></div>';
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
    floorShell('Central Agency Dossiers', 'Personnel · classified field files',
      ariaGuideCard('Aria', 'These are personnel files — not chat bios. Flip agents above. Polaroids are field imagery. Redacted bars mean we chose not to emphasize that wound in product.') +
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
    floorShell('Mission Journal', 'CASEFILE · WHAT HAPPENED',
      ariaGuideCard('Ledger', 'Objective continuity only — stamps, not feelings. Tap a card for the full mission packet.') +
      '<p class="fl-note">' + esc(d.rule || 'JOURNAL = objective continuity.') + '</p>' +
      filters + '<div class="fl-stack fl-journal-casefile" id="fl-journal-list"></div>');
    var list = document.getElementById('fl-journal-list');
    if (!list) return;
    if (!entries.length) { list.innerHTML = empty('No journal entries match these filters.'); return; }
    FL._journalById = {};
    list.innerHTML = entries.map(function (e) {
      FL._journalById[e.entry_id] = e;
      return '<button type="button" class="fl-card clickable fl-journal-card" onclick="' +
        oc('floorOpenJournal', e.entry_id) + '">' +
        '<div class="fl-journal-stamp">CASEFILE</div>' +
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
      var aid = block.agent_id;
      var thumb = agentAsset(aid, aid + '.webp');
      body = '<div class="fl-diary-desk">' +
        '<aside class="fl-diary-polaroid"><div class="fl-dos-polaroid-frame">' +
        '<img src="' + thumb + '" alt=""><i class="fl-dos-classified">PRIVATE</i></div>' +
        '<figcaption>' + esc(block.display_name || aid) + '</figcaption></aside>' +
        '<div class="fl-diary-stack">' +
        '<p class="fl-diary-meta">diary voice: <i>' + esc(block.diary_style || '—') + '</i> · ' +
        esc(String(block.count || entries.length)) + ' entries</p>' +
        listCards(entries, function (e) {
          var snap = e.emotional_state_snapshot || {};
          var top = topDims(snap, 4).map(function (kv) { return kv[0] + '=' + kv[1]; }).join(', ');
          var refs = (e.relationship_refs || []).map(function (r) {
            if (typeof r === 'string') return r;
            return (r.target || r.agent_id || '') + ':' + (r.label || r.dim || '');
          }).join(', ');
          return '<article class="fl-diary-page"><div class="fl-diary-pin"></div>' +
            '<p class="when">' + esc(fmtTs(e.timestamp)) + '</p><p>' +
            esc(e.text || '(empty — diary not populated yet)') + '</p>' +
            '<p class="muted" style="font-style:normal;font-family:var(--ot-mono);font-size:.7rem">snapshot: ' +
            esc(top || '—') + ' · rel: ' + esc(refs || '—') + '</p>' +
            btn('WHY', oc('floorDiaryWhy', block.agent_id, e.diary_id), true) + '</article>';
        }, 'No diary entries for this agent yet — live meaning accumulates as they journal.') +
        '</div></div>';
    }
    floorShell('Private Diaries', 'WHAT IT MEANT',
      ariaGuideCard('Ledger', 'Diaries are subjective — ink and meaning. Journal is the casefile. WHY opens the evidence drawer.') +
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
    catch (e) { floorShell('Emotions', 'Affective state', empty('Failed: ' + e), '', 'emotion'); return; }
    var agents = d.agents || [];
    var blocks = [];
    var palette = ['#ff8fb8', '#7dc8ff', '#f2d596', '#b8db94', '#979fec'];
    for (var i = 0; i < agents.length; i++) {
      var a = agents[i];
      var detail = null;
      try { detail = await apiGet('/api/expansion/emotion/' + encodeURIComponent(a.agent_id)); }
      catch (e) { detail = null; }
      var primary = a.primary || (detail && detail.primary) || topDims(a.dimensions, 5);
      var cur = a.dimensions || {};
      var id = a.agent_id;
      var rings = (primary || []).slice(0, 5).map(function (kv, idx) {
        var pct = Math.max(4, Math.min(100, Math.round(Number(kv[1]) * 100)));
        return '<div class="fl-emo-orbit" style="--pct:' + pct + '%;--c:' + palette[idx % palette.length] +
          '"><span>' + esc(kv[0]) + '<br>' + pct + '%</span></div>';
      }).join('');
      var stress = (detail && detail.stress_behavior) || '';
      var recovery = (detail && detail.recovery_behavior) || '';
      blocks.push(
        '<article class="fl-emo-card">' +
        '<div class="fl-emo-head"><img class="fl-emo-avatar" src="' + agentAsset(esc(id), esc(id) + '.webp') +
        '" alt="" onerror="this.onerror=null;this.src=agentAsset(\'aria\',\'aria.webp\')">' +
        '<div><h3 style="margin:0;letter-spacing:.06em">' + esc(a.display_name || id) + '</h3>' +
        '<p class="muted" style="margin:4px 0 0">live affect · baseline delta · provenance</p></div></div>' +
        '<div class="fl-emo-rings">' + (rings || empty('—')) + '</div>' +
        '<div class="fl-grid" style="position:relative;z-index:1">' +
        Object.keys(cur).slice(0, 8).map(function (k) {
          return bar(k, cur[k], { onclick: oc('floorEmotionWhy', id, k) });
        }).join('') + '</div>' +
        (stress || recovery
          ? '<p class="muted" style="position:relative;z-index:1">stress: ' + esc(stress || '—') +
            '<br>recovery: ' + esc(recovery || '—') + '</p>'
          : '') +
        '</article>'
      );
    }
    var body =
      cineHero('Affective continuum', 'Emotion Lab',
        'Each agent is a living signal — rings pulse with primary affect. Tap any bar for WHY provenance.') +
      cineWidgets([
        { k: 'Roster', v: String(agents.length), cls: 'ok' },
        { k: 'Mode', v: 'LIVE DECAY', cls: 'warn' },
        { k: 'Board', v: 'MULTI-AGENT', cls: 'ok' },
        { k: 'Signal', v: 'CODEC LINK', cls: 'ok' }
      ]) +
      '<div class="fl-symbol-row"><span class="fl-symbol">♥</span><span class="fl-symbol">◎</span><span class="fl-symbol">◇</span><span class="fl-symbol">⚡</span></div>' +
      '<div class="fl-emo-board">' + (blocks.join('') || empty('No agent emotion state loaded.')) + '</div>';
    floorShell('Emotional State', 'Runtime EmotionStore', body, '', 'emotion');
  }

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
    var strip = '<div class="fl-strip fl-room-war">' +
      '<div class="fl-gauge"><div class="n">' + esc(String(metrics.active != null ? metrics.active : (ops.active || []).length)) + '</div><div class="l">active</div></div>' +
      '<div class="fl-gauge"><div class="n">' + esc(String((ops.failed || []).length)) + '</div><div class="l">failed</div></div>' +
      '<div class="fl-gauge"><div class="n">' + esc(String(verifying.length)) + '</div><div class="l">verifying</div></div>' +
      '<div class="fl-gauge"><div class="n">' + esc(String(rework.length)) + '</div><div class="l">rework</div></div>' +
      '<div class="fl-gauge"><div class="n">' + esc(String(hard.length)) + '</div><div class="l">hard block</div></div></div>';
    var trace = listCards(d.decision_trace || [], function (j) {
      return '<div class="fl-card"><b>' + esc(j.job_id) + '</b> · ' + esc(j.status) + ' · ' +
        esc(j.assigned_agent || '') + '<p class="muted">' + esc(j.request || '') + '</p>' +
        '<p class="muted">evidence: ' + esc((j.evidence || []).join(', ') || '—') +
        (j.error ? ' · err ' + esc(j.error) : '') + '</p>' + jobLink(j.job_id) + '</div>';
    }, 'No decision trace yet.');
    floorShell('War Room', 'Vector · tactical board',
      cineHero('Tactical theater', 'War Room', 'Job boards, verification, and hard blocks — military sci-fi command glass.') +
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
      panel('Decision / evidence trace', trace),
      '', 'ops');
  }

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
      var aid = a.agent_id || a.id || '';
      return '<div class="fl-card fl-agent-card"><img class="fl-avatar" src="' + agentAsset(esc(aid), esc(aid) + '.webp') +
        '" alt="" onerror="this.onerror=null;this.src=agentAsset(\'aria\',\'aria.webp\')">' +
        '<div><b>' + esc(a.display_name || aid) + '</b> · ' + esc(a.role || '') +
        '<p class="muted">open jobs: ' +
        esc(String(a.open_jobs != null ? a.open_jobs : wl[aid] || 0)) + '</p>' +
        '<p class="muted">emotion: ' + esc(Object.keys(a.emotion_highlights || {}).map(function (k) {
          return k + '=' + a.emotion_highlights[k];
        }).join(', ') || '—') + '</p></div></div>';
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
      panel('Readiness', readinessHud(ready)) +
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

  async function renderIntelFloor() {
    var d;
    try { d = await apiGet('/api/expansion/intel'); }
    catch (e) { floorShell('Intel', 'Ledger continuity', empty('Failed: ' + e), '', 'intel'); return; }
    if (d && d.enabled === false) {
      floorShell('Intel', 'Ledger continuity', empty('Expansion not enabled.'), '', 'intel');
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
    var relEv = (d.relationship_evidence || []).filter(function (x) {
      return match([x.source, x.target, x.label, x.narrative]);
    }).slice(0, 24);
    var livingKeys = Object.keys(d.living_dossiers || {});

    var body =
      '<div class="fl-intel-shell">' +
      '<div class="fl-matrix-rain" id="fl-matrix-rain" aria-hidden="true"></div>' +
      '<div class="fl-intel-fore">' +
      cineHero('Central Agency · Continuity', 'Classified Intel Deck',
        'Ledger continuity under Psalms rain. Memories, claims, and relationship evidence — agency-grade, not a spreadsheet.') +
      '<span class="fl-intel-stamp">TOP SECRET</span><span class="fl-intel-stamp">NEED-TO-KNOW</span>' +
      cineWidgets([
        { k: 'Memories', v: String(mems.length), cls: mems.length ? 'ok' : 'warn' },
        { k: 'Events', v: String(events.length), cls: 'ok' },
        { k: 'Claims', v: String(shared.length), cls: shared.length ? 'ok' : 'warn' },
        { k: 'Living', v: String(livingKeys.length), cls: 'ok' }
      ]) +
      '<div class="fl-filters"><input id="fl-intel-q" placeholder="search continuity…" value="' +
      esc(FL.intelQ) +
      '" onkeydown="if(event.key===\'Enter\'){FL.intelQ=this.value;renderIntelFloor()}">' +
      btn('Filter', "FL.intelQ=document.getElementById('fl-intel-q').value;renderIntelFloor()", true) +
      '</div>' +
      '<div class="fl-panel fl-intel-panel"><h3 class="fl-h">Important memories</h3>' +
      (mems.map(function (m) {
        return '<div class="fl-intel-card"><b>' + esc(m.agent_id) + '</b> · imp ' + esc(String(m.importance)) +
          '<div>' + esc(m.content || '') + '</div><div class="muted">' + esc(m.memory_id || '') + '</div></div>';
      }).join('') || empty('No high-importance memories.')) + '</div>' +
      '<div class="fl-panel fl-intel-panel"><h3 class="fl-h">Recent events</h3>' +
      (events.slice(0, 24).map(function (e) {
        return '<div class="fl-intel-card"><b>' + esc(e.event_type) + '</b> · ' + esc(e.actor) +
          ' → ' + esc(e.subject || '') +
          '<div class="muted">' + esc(e.event_id) + ' · ' + fmtTs(e.timestamp) + '</div></div>';
      }).join('') || empty('No events.')) + '</div>' +
      '<div class="fl-panel fl-intel-panel"><h3 class="fl-h">Learned claims</h3>' +
      (shared.map(function (c) {
        return '<div class="fl-intel-card"><b>' + esc(c.claim) + '</b>' +
          '<div class="muted">conf ' + esc(String(c.confidence)) + '</div>' +
          btn('WHY', oc('floorLearningWhy', c.claim_id), true) + '</div>';
      }).join('') || empty('No shared claims.')) + '</div>' +
      '<div class="fl-panel fl-intel-panel"><h3 class="fl-h">Relationship evidence</h3>' +
      (relEv.map(function (x) {
        return '<div class="fl-intel-card"><b>' + esc(x.source) + ' → ' + esc(x.target) + '</b> · ' +
          esc(x.label || '') + '<div class="muted">' + esc(x.narrative || '') + '</div>' +
          btn('WHY', oc('floorRelWhy', x.source, x.target), true) + '</div>';
      }).join('') || empty('No relationship evidence.')) + '</div>' +
      '<div class="fl-panel fl-intel-panel"><h3 class="fl-h">Journal timeline</h3>' +
      (journal.slice(0, 30).map(function (e) {
        return '<div class="fl-intel-card"><b>JOURNAL</b> ' + esc(e.summary || '') +
          '<div class="muted">' + esc(e.agent_id) + ' · ' + fmtTs(e.timestamp) + '</div></div>';
      }).join('') || empty('Journal empty.')) + '</div>' +
      '</div></div>';
    floorShell('Intel / Continuity', 'Ledger · Secret Agency', body, '', 'intel');
  }

  async function renderReportsFloor() {
    var d;
    try { d = await apiGet('/api/expansion/reports'); }
    catch (e) { floorShell('Agent Reports', 'Full depth', empty('Failed: ' + e), '', 'reports'); return; }
    if (d && d.enabled === false) {
      floorShell('Agent Reports', 'Full depth', empty('Expansion not enabled.'), '', 'reports');
      return;
    }
    var pages = (d.reports || []).map(function (r) {
      var emo = r.emotion || {};
      var m = r.metrics || {};
      var learn = r.learning || {};
      var claims = [].concat(learn.private || [], learn.shared_keep || []);
      var lines = [];
      lines.push('CLASSIFICATION: KEEP INTERNAL');
      lines.push('SUBJECT: ' + (r.display_name || r.agent_id) + ' — ' + (r.role || ''));
      lines.push('ARCHETYPE: ' + (r.archetype || '—'));
      lines.push('RUNTIME: ' + (r.runtime_status || '—'));
      lines.push('SUCCESS: ' + (m.success_rate != null ? (Math.round(m.success_rate * 100) + '%') : 'n/a') +
        ' · DONE ' + (m.completed || 0) + ' · FAILED ' + (m.failed || 0));
      lines.push('');
      lines.push('EMOTION SNAPSHOT');
      Object.keys(emo).map(function (k) { return [k, emo[k]]; })
        .sort(function (a, b) { return b[1] - a[1]; }).slice(0, 6)
        .forEach(function (kv) {
          lines.push('  · ' + kv[0] + ': ' + (Math.round(Number(kv[1]) * 1000) / 1000));
        });
      lines.push('');
      lines.push('RELATIONSHIP HIGHLIGHTS');
      (r.relationship_highlights || []).slice(0, 5).forEach(function (h) {
        lines.push('  · → ' + (h.target || '') + ' · ' + (h.label || '') +
          (h.narrative ? (' — ' + h.narrative) : ''));
      });
      if (!(r.relationship_highlights || []).length) lines.push('  · (none on file)');
      lines.push('');
      lines.push('LATEST DIARY');
      lines.push(r.latest_diary && r.latest_diary.text
        ? String(r.latest_diary.text).slice(0, 600)
        : '  · (no diary yet)');
      lines.push('');
      lines.push('LEARNED CLAIMS');
      claims.slice(0, 6).forEach(function (c) { lines.push('  · ' + (c.claim || '')); });
      if (!claims.length) lines.push('  · (none)');
      var text = lines.join('\n');
      return '<article class="fl-rpt-page">' +
        '<h3 class="fl-rpt-title">' + esc(r.display_name || r.agent_id) + '</h3>' +
        '<p class="fl-rpt-meta">FIELD REPORT · ' + esc(r.agent_id) + ' · ' + esc(r.role || '') + '</p>' +
        '<div class="fl-rpt-section">Typewritten record</div>' +
        '<pre class="fl-rpt-body fl-rpt-type">' + esc(text) + '</pre>' +
        '<div class="fl-rail" style="margin-top:10px">' +
        btn('jealousy WHY', oc('floorEmotionWhy', r.agent_id, 'jealousy'), true) +
        btn('stress WHY', oc('floorEmotionWhy', r.agent_id, 'stress'), true) +
        (r.latest_diary && r.latest_diary.diary_id
          ? btn('Diary WHY', oc('floorDiaryWhy', r.agent_id, r.latest_diary.diary_id), true) : '') +
        '</div></article>';
    }).join('') || empty('No reports.');
    var body =
      '<div class="fl-rpt-desk">' +
      '<p style="margin:0 0 1rem;letter-spacing:.18em;text-transform:uppercase;font-size:11px;color:#6b1f2c">Central Agency · Typewriter bureau</p>' +
      pages + '</div>';
    floorShell('Agent Reports', 'Typewriter bureau', body, '', 'reports');
  }

  /* —— Creative / Muse Video Studio (Keep Workshop parity) —— */
  var FL_STUDIO = { modality: 'image', actors: {}, style: '' };

  function studioEndpointHost(ep) {
    try {
      var u = String(ep || '');
      if (!u) return '—';
      return u.replace(/^https?:\/\//, '').replace(/\/$/, '');
    } catch (e) { return String(ep || '—'); }
  }

  function studioPromptDefaults(engines, modality) {
    var map = { image: 'z-image-turbo', video: 'wan-2.2-5b', music: 'ace-step-1.5' };
    var key = map[modality] || map.image;
    var eng = (engines && engines[key]) || {};
    Object.keys(engines || {}).forEach(function (k) {
      if (modality === 'image' && /image|z-image/i.test(k)) key = k;
      if (modality === 'video' && /wan|ltx|video/i.test(k)) key = k;
      if (modality === 'music' && /ace|music/i.test(k)) key = k;
    });
    eng = (engines && engines[key]) || eng;
    return {
      engine: key,
      positive: eng.default_positive || '',
      negative: eng.default_negative || '',
      role: eng.role || ''
    };
  }

  function floorStudioCloseModals() {
    ['flVsOptimalModal', 'flVsFillModal'].forEach(function (id) {
      var el = document.getElementById(id);
      if (el) el.hidden = true;
    });
  }

  function floorStudioOpenOptimal() {
    var m = document.getElementById('flVsOptimalModal');
    if (m) m.hidden = false;
  }

  function floorStudioOpenFill() {
    var m = document.getElementById('flVsFillModal');
    if (m) m.hidden = false;
  }

  async function floorStudioSetModality(mod) {
    FL_STUDIO.modality = mod || 'image';
    document.querySelectorAll('.fl-vs-mode').forEach(function (t) {
      t.classList.toggle('on', t.getAttribute('data-mod') === FL_STUDIO.modality);
    });
    var defs = FL_STUDIO._defaults || {};
    var d = studioPromptDefaults(defs, FL_STUDIO.modality);
    var prompt = document.getElementById('fl-studio-prompt');
    var neg = document.getElementById('fl-studio-negative');
    var eng = document.getElementById('fl-studio-engine');
    var role = document.getElementById('fl-studio-engine-role');
    if (prompt && !prompt.dataset.dirty) prompt.value = d.positive || '';
    if (neg && !neg.dataset.dirty) neg.value = d.negative || '';
    if (eng) eng.textContent = d.engine || '—';
    if (role) role.textContent = d.role || '';
    var tuneVideo = document.getElementById('fl-tune-video');
    var tuneImage = document.getElementById('fl-tune-image');
    var tuneMusic = document.getElementById('fl-tune-music');
    var musicPanel = document.getElementById('fl-vs-music-panel');
    var imgWidgets = document.getElementById('fl-studio-image-widgets');
    var drop = document.getElementById('fl-vs-drop');
    if (tuneVideo) tuneVideo.hidden = FL_STUDIO.modality !== 'video';
    if (tuneImage) tuneImage.hidden = FL_STUDIO.modality === 'music';
    if (tuneMusic) tuneMusic.hidden = FL_STUDIO.modality !== 'music';
    if (musicPanel) musicPanel.hidden = FL_STUDIO.modality !== 'music';
    if (imgWidgets) imgWidgets.hidden = FL_STUDIO.modality !== 'image';
    if (drop) drop.hidden = FL_STUDIO.modality === 'music';
    var packs = (FL_STUDIO._optimal && FL_STUDIO._optimal[FL_STUDIO.modality]) || [];
    var optBox = document.getElementById('fl-studio-optimal');
    if (optBox) {
      optBox.innerHTML = packs.length
        ? packs.map(function (p) {
            return '<button type="button" class="fl-vs-preset" title="' + esc(p.note || p.text || '') +
              '" onclick=\'floorStudioApplyOptimal(' + JSON.stringify(p.text || '') + ');floorStudioCloseModals()\'>' +
              esc(p.label || p.id) + '</button>';
          }).join('')
        : '<span class="muted">No optimal packs for this mode yet.</span>';
    }
    try { if (typeof otSfx === 'function') otSfx('click'); } catch (_e) {}
  }

  function floorStudioApplyOptimal(text) {
    var prompt = document.getElementById('fl-studio-prompt');
    if (!prompt) return;
    prompt.value = String(text || '');
    prompt.dataset.dirty = '1';
  }

  function floorStudioFillApply() {
    var topic = (document.getElementById('fl-vs-fill-topic') || {}).value || '';
    var mood = (document.getElementById('fl-vs-fill-mood') || {}).value || 'cinematic';
    var prompt = document.getElementById('fl-studio-prompt');
    if (!prompt) return;
    var bits = [];
    if (topic) bits.push(String(topic).trim());
    bits.push(mood + ' lighting');
    bits.push('coherent subject');
    bits.push('high detail');
    if (FL_STUDIO.modality === 'video') bits.push('smooth natural motion');
    if (FL_STUDIO.modality === 'music') bits.push('clean mix, loop-friendly structure');
    prompt.value = bits.join(', ');
    prompt.dataset.dirty = '1';
    floorStudioCloseModals();
  }

  function floorStudioToggleActor(id) {
    FL_STUDIO.actors = FL_STUDIO.actors || {};
    FL_STUDIO.actors[id] = !FL_STUDIO.actors[id];
    var el = document.querySelector('[data-actor="' + id + '"]');
    if (el) el.classList.toggle('on', !!FL_STUDIO.actors[id]);
  }

  function floorStudioPickStyle(id) {
    FL_STUDIO.style = id;
    document.querySelectorAll('[data-style]').forEach(function (el) {
      el.classList.toggle('on', el.getAttribute('data-style') === id);
    });
  }

  function floorStudioAddActor() {
    var name = ((document.getElementById('fl-vs-actor-name') || {}).value || '').trim();
    var note = ((document.getElementById('fl-vs-actor-desc') || {}).value || '').trim();
    if (!name) return;
    var id = 'custom_' + name.toLowerCase().replace(/[^a-z0-9]+/g, '_').slice(0, 24);
    FL_STUDIO._actors = FL_STUDIO._actors || [];
    FL_STUDIO._actors.push({ id: id, label: name, note: note || 'Custom cast', tag: 'custom', portrait: '' });
    renderCreativeFloor();
  }

  function floorStudioAddStyle() {
    var name = ((document.getElementById('fl-vs-style-name') || {}).value || '').trim();
    if (!name) return;
    var id = 'style_' + name.toLowerCase().replace(/[^a-z0-9]+/g, '_').slice(0, 24);
    FL_STUDIO._styles = FL_STUDIO._styles || [];
    FL_STUDIO._styles.push({ id: id, label: name });
    FL_STUDIO.style = id;
    renderCreativeFloor();
  }

  async function floorStudioInstallPacks() {
    var msg = document.getElementById('fl-studio-msg');
    var log = document.getElementById('fl-vs-log');
    function say(t) {
      if (msg) msg.textContent = t;
      if (log) log.textContent = (log.textContent ? log.textContent + '\n' : '') + '[' + new Date().toLocaleTimeString() + '] ' + t;
    }
    say('Starting creative pack download (Z-Image first)…');
    try {
      if (typeof otSfx === 'function') otSfx('ok');
      var r = await api('/api/expansion/creative/packs/install', { force: false });
      var aria = (r.data && (r.data.aria || r.data.message || r.data.detail)) || '';
      if (!r.ok) {
        say(aria || ('Could not start pack install: ' + r.status));
        return;
      }
      say(aria || 'Downloading creative packs… Generate unlocks when Z-Image finishes.');
      if (window._flPacksPoll) clearInterval(window._flPacksPoll);
      window._flPacksPoll = setInterval(async function () {
        try {
          var st = await apiGet('/api/expansion/creative/packs');
          if (st && !st.running && (st.image_ready || st.ok)) {
            clearInterval(window._flPacksPoll);
            window._flPacksPoll = null;
            renderCreativeFloor();
          } else if (st && st.message) {
            say(st.message);
          }
        } catch (e) { /* keep polling */ }
      }, 4000);
      setTimeout(function () { renderCreativeFloor(); }, 1200);
    } catch (e) {
      say(String(e));
    }
  }

  async function floorStudioGenerate() {
    var msg = document.getElementById('fl-studio-msg');
    var log = document.getElementById('fl-vs-log');
    function say(t) {
      if (msg) msg.textContent = t;
      if (log) log.textContent = (log.textContent ? log.textContent + '\n' : '') + '[' + new Date().toLocaleTimeString() + '] ' + t;
    }
    var promptEl = document.getElementById('fl-studio-prompt');
    var negEl = document.getElementById('fl-studio-negative');
    var musicDesc = document.getElementById('fl-vs-music-simple-desc');
    var prompt = promptEl ? String(promptEl.value || '').trim() : '';
    if (FL_STUDIO.modality === 'music' && musicDesc && String(musicDesc.value || '').trim()) {
      prompt = String(musicDesc.value || '').trim();
      if (promptEl) { promptEl.value = prompt; promptEl.dataset.dirty = '1'; }
    }
    if (!prompt) { say('Write a prompt first — or tap Fill This In.'); return; }
    var engEl = document.getElementById('fl-studio-engine');
    var engine = engEl ? String(engEl.textContent || '').trim() : '';
    var tuning = {
      steps: (document.getElementById('fl-tune-steps') || {}).value,
      cfg: (document.getElementById('fl-tune-cfg') || {}).value,
      resolution: (document.getElementById('fl-tune-res') || {}).value,
      seed: (document.getElementById('fl-tune-seed') || {}).value,
      duration: (document.getElementById('fl-tune-dur') || {}).value ||
        (document.getElementById('fl-vs-music-dur') || {}).value,
      fps: (document.getElementById('fl-tune-fps') || {}).value,
      quality: (document.getElementById('fl-tune-quality') || {}).value,
      bpm: (document.getElementById('fl-tune-bpm') || {}).value,
      key: (document.getElementById('fl-tune-key') || {}).value,
      bars: (document.getElementById('fl-tune-bars') || {}).value,
      lyrics: (document.getElementById('fl-vs-music-lyrics') || {}).value,
      aspect: (document.getElementById('fl-img-aspect') || {}).value,
      identity_lock: (document.getElementById('fl-img-lock') || {}).value,
      batch: (document.getElementById('fl-img-batch') || {}).value,
      style: FL_STUDIO.style || '',
      actors: Object.keys(FL_STUDIO.actors || {}).filter(function (k) { return FL_STUDIO.actors[k]; }),
      ref_image: (document.getElementById('fl-vs-ref-name') || {}).textContent || ''
    };
    say('Submitting to ComfyUI…');
    try {
      if (typeof otSfx === 'function') otSfx('ok');
      var r = await api('/api/expansion/creative/generate', {
        modality: FL_STUDIO.modality || 'image',
        prompt: prompt,
        negative: negEl ? String(negEl.value || '').trim() : '',
        engine: engine,
        tuning: tuning
      });
      if (!r.ok || !(r.data && r.data.ok)) {
        var soft = r.data && r.data.soft_block;
        var err = (r.data && (r.data.detail || r.data.error)) || r.status;
        if (soft || (r.data && r.data.action === 'install_packs')) {
          say(err || 'Creative packs are not ready yet — tap Install packs. Generate stays quiet until then.');
          return;
        }
        say('Could not queue: ' + err);
        return;
      }
      if (!(r.data.prompt_id || r.data.queued)) {
        say('ComfyUI did not return a prompt_id yet — try again in a moment.');
        return;
      }
      say((r.data.message || ('Submitted · prompt_id=' + r.data.prompt_id)));
      setTimeout(function () { renderCreativeFloor(); }, 800);
    } catch (e) {
      say(String(e));
    }
  }

  function floorStudioApplyChip(text) {
    var prompt = document.getElementById('fl-studio-prompt');
    if (!prompt) return;
    var t = String(text || '').trim();
    if (!t) return;
    prompt.value = prompt.value ? (prompt.value.replace(/\s+$/, '') + ', ' + t) : t;
    prompt.dataset.dirty = '1';
  }

  function floorStudioOnDrop(ev) {
    if (ev && ev.preventDefault) ev.preventDefault();
    var f = ev.dataTransfer && ev.dataTransfer.files && ev.dataTransfer.files[0];
    var label = document.getElementById('fl-vs-ref-name');
    if (f && label) label.textContent = f.name;
  }

  async function renderCreativeFloor() {
    var d;
    try { d = await apiGet('/api/expansion/creative'); }
    catch (e) { floorShell('Creative Studio', 'Muse', empty('Failed: ' + e), '', 'studio'); return; }
    var state = String(d.video_studio_readiness || (d.video_studio && d.video_studio.state) || 'UNAVAILABLE').toUpperCase();
    var vs = d.video_studio || {};
    var studio = d.studio || {};
    var hw = studio.hardware || {};
    var engines = studio.engines || {};
    FL_STUDIO._defaults = engines;
    var endpoint = studio.endpoint || (vs.discovery && vs.discovery.endpoint) || '';
    var ready = state === 'READY';
    var needsSetup = state === 'UNAVAILABLE' || state === 'NOT_CONFIGURED' || state === 'NEEDS_SETUP';

    var actors = (FL_STUDIO._actors && FL_STUDIO._actors.length)
      ? FL_STUDIO._actors
      : (studio.actors || []).map(function (a) {
          var aid = (a.id || '').replace(/_cameo|_self|_a|_b|_c/g, '').replace('muse', 'muse').replace('aria', 'aria');
          var portraitId = /aria/i.test(a.id || a.label || '') ? 'aria'
            : (/muse/i.test(a.id || a.label || '') ? 'muse'
              : (/vector/i.test(a.id || '') ? 'vector'
                : (/ledger/i.test(a.id || '') ? 'ledger'
                  : (/sentry/i.test(a.id || '') ? 'sentry' : ''))));
          return Object.assign({}, a, {
            portrait: portraitId ? agentAsset(portraitId, portraitId + '.webp') : ''
          });
        });
    FL_STUDIO._actors = actors;
    var styles = (FL_STUDIO._styles && FL_STUDIO._styles.length) ? FL_STUDIO._styles : (studio.styles || []);
    FL_STUDIO._styles = styles;
    FL_STUDIO._optimal = studio.optimal_prompts || {};
    FL_STUDIO.actors = FL_STUDIO.actors || {};
    if (!FL_STUDIO.modality) FL_STUDIO.modality = 'image';

    var mods = studio.modalities || [
      { id: 'image', label: 'Image' },
      { id: 'video', label: 'Video' },
      { id: 'music', label: 'Music' }
    ];
    var defs = studioPromptDefaults(engines, FL_STUDIO.modality);
    mods.forEach(function (m) {
      if (m.id === FL_STUDIO.modality && m.engine) defs.engine = m.engine;
    });
    var musicAdv = studio.music_advanced || {};
    var imgWidgets = studio.image_widgets || [];
    var optPacks = (studio.optimal_prompts && studio.optimal_prompts[FL_STUDIO.modality]) || [];
    var vram = hw.marketed_vram_gb || hw.vram_gb || '?';
    var chips = ['identity-preserving', 'cinematic lighting', 'stable subject', 'natural motion', 'clean background', 'film grain'];
    var genOk = studio.generate_enabled !== false && !!studio.generate_enabled;
    // When field absent (older tips), fall back to READY + workflow.ok
    if (studio.generate_enabled == null) {
      genOk = ready && !!(studio.workflow && studio.workflow.ok);
    }
    var packs = studio.packs || d.packs || {};
    var packsRunning = !!packs.running;
    var genBlock = studio.generate_blocked_reason ||
      (FL_STUDIO.modality !== 'image'
        ? (FL_STUDIO.modality.charAt(0).toUpperCase() + FL_STUDIO.modality.slice(1) +
          ' packs are not ready yet — install creative packs first.')
        : (packs.aria || (studio.workflow && studio.workflow.detail) ||
          'Creative packs are not installed yet. Tap Install packs — Generate stays quiet until packs are ready.'));
    var showInstallPacks = !canGenerate && ready;
    if (showInstallPacks && packsRunning && !window._flPacksPoll) {
      window._flPacksPoll = setInterval(function () { renderCreativeFloor(); }, 5000);
    }
    if (canGenerate && window._flPacksPoll) {
      clearInterval(window._flPacksPoll);
      window._flPacksPoll = null;
    }

    if (needsSetup) {
      floorShell('The Workshop', 'Muse · Video Studio',
        '<div class="fl-workshop">' +
        '<div class="fl-vs-hero"><div class="fl-vs-byline"><img src="' + agentAsset('muse', 'muse.webp') +
        '" alt=""><span>Muse // The Workshop</span></div>' +
        '<h2>THE WORKSHOP</h2><p>Video Studio is not armed yet. Tap Set Up — Aria installs Comfy. Then you get the full Keep Workshop: actors, styles, optimal prompts, music, tuning gauges.</p>' +
        '<div class="fl-vs-gpu"><i></i> ' + esc(state) + '</div></div>' +
        '<div class="fl-rail">' +
        btn('Set Up Video Studio', "typeof showVideoStudioSetup==='function'&&showVideoStudioSetup()", false) +
        btn('Start setup', "typeof startStudioSetup==='function'?startStudioSetup():(typeof showVideoStudioSetup==='function'&&showVideoStudioSetup())", true) +
        '</div></div>', '', 'studio');
      return;
    }

    var body =
      '<div class="fl-workshop">' +
      '<div class="fl-vs-hero"><div class="fl-vs-byline"><img src="' + agentAsset('muse', 'muse.webp') +
      '" alt=""><span>Muse // The Workshop</span></div>' +
      '<h2>THE WORKSHOP</h2>' +
      '<p>Keep Production Studio on Expansion — Image, Video, Music. Actors, styles, optimal prompts, tuning rack, workshop log. Same soul as OtaconsKeep.</p>' +
      '<div class="fl-vs-gpu' + (ready ? ' ready' : '') + '"><i></i> ' +
      esc(ready ? ('LIVE · ' + studioEndpointHost(endpoint) + ' · ' + vram + ' GB') : state) +
      '</div></div>' +

      '<div class="fl-vs-rings">' +
      '<div class="fl-vs-ring"><div class="g" style="--p:' + (ready ? '82' : '28') +
      '%"><b>' + (ready ? 'OK' : '…') + '</b></div><div class="l">GPU</div></div>' +
      '<div class="fl-vs-ring"><div class="g" style="--p:45%"><b>Q</b></div><div class="l">Queue</div></div>' +
      '<div class="fl-vs-ring"><div class="g" style="--p:60%"><b>28</b></div><div class="l">Steps</div></div>' +
      '<div class="fl-vs-ring"><div class="g" style="--p:70%"><b>' + esc(String(vram)) +
      '</b></div><div class="l">VRAM</div></div></div>' +

      '<div class="fl-vs-card"><h3>Actors</h3><div class="fl-vs-actors">' +
      actors.map(function (a) {
        var on = FL_STUDIO.actors[a.id] ? ' on' : '';
        var img = a.portrait
          ? ('<img src="' + esc(a.portrait) + '" alt="" onerror="this.style.display=\'none\'">')
          : '<div class="ph">REF</div>';
        return '<button type="button" class="fl-vs-actor' + on + '" data-actor="' + esc(a.id) +
          '" onclick="floorStudioToggleActor(\'' + esc(a.id) + '\')">' + img +
          '<div class="nm">' + esc(a.label || a.id) + '</div>' +
          '<div class="ds">' + esc(a.note || a.tag || '') + '</div></button>';
      }).join('') + '</div>' +
      '<div class="fl-form" style="margin-top:12px">' +
      '<label>Name<input id="fl-vs-actor-name" placeholder="New actor"></label>' +
      '<label>Note<input id="fl-vs-actor-desc" placeholder="Personality / look"></label>' +
      '</div><div class="fl-rail" style="margin-top:8px">' +
      '<button type="button" class="fl-vs-submit ghost" onclick="floorStudioAddActor()">Add actor</button></div></div>' +

      '<div class="fl-vs-card"><h3>Styles</h3><div class="fl-vs-styles">' +
      styles.map(function (s) {
        var on = FL_STUDIO.style === s.id ? ' on' : '';
        return '<button type="button" class="fl-vs-style' + on + '" data-style="' + esc(s.id) +
          '" onclick="floorStudioPickStyle(\'' + esc(s.id) + '\')"><b>' + esc(s.label || s.id) +
          '</b></button>';
      }).join('') + '</div>' +
      '<div class="fl-form" style="margin-top:12px"><label>New style<input id="fl-vs-style-name" placeholder="e.g. Soft noir"></label></div>' +
      '<div class="fl-rail" style="margin-top:8px"><button type="button" class="fl-vs-submit ghost" onclick="floorStudioAddStyle()">Add style</button></div></div>' +

      '<div class="fl-vs-card"><h3>New Entry</h3>' +
      '<div class="fl-vs-modes">' + mods.map(function (m) {
        return '<button type="button" class="fl-vs-mode' + (m.id === FL_STUDIO.modality ? ' on' : '') +
          '" data-mod="' + esc(m.id) + '" onclick="floorStudioSetModality(\'' + esc(m.id) + '\')">' +
          esc(m.label || m.id) + '</button>';
      }).join('') + '</div>' +
      '<p class="muted">Agent <b>Muse</b> · Engine <b id="fl-studio-engine">' + esc(defs.engine || '—') +
      '</b> · <span id="fl-studio-engine-role">' + esc(defs.role || '') + '</span></p>' +
      '<div class="fl-rail" style="margin:.55rem 0">' +
      '<button type="button" class="fl-vs-submit ghost" onclick="floorStudioOpenOptimal()">Optimal prompts</button>' +
      '<button type="button" class="fl-vs-submit ghost" onclick="floorStudioOpenFill()">✦ Fill This In For Me</button>' +
      '</div>' +
      '<div class="fl-rail" style="margin:0 0 .75rem">' + chips.map(function (c) {
        return '<button type="button" class="fl-vs-preset" onclick=\'floorStudioApplyChip(' +
          JSON.stringify(c) + ')\'>' + esc(c) + '</button>';
      }).join('') + '</div>' +
      '<div class="fl-vs-drop" id="fl-vs-drop" ondragover="event.preventDefault()" ondrop="floorStudioOnDrop(event)">' +
      'Drop a reference image here (identity / start frame)<div id="fl-vs-ref-name" class="muted" style="margin-top:6px">No file</div></div>' +
      '<div class="fl-vs-field"><label>Prompt</label><textarea id="fl-studio-prompt" rows="5" oninput="this.dataset.dirty=\'1\'">' +
      esc(defs.positive || '') + '</textarea></div>' +
      '<div class="fl-vs-field"><label>Negative</label><textarea id="fl-studio-negative" rows="2" oninput="this.dataset.dirty=\'1\'">' +
      esc(defs.negative || '') + '</textarea></div>' +

      '<div id="fl-vs-music-panel" ' + (FL_STUDIO.modality === 'music' ? '' : 'hidden') + '>' +
      '<div class="fl-vs-field"><label>Describe the music</label>' +
      '<textarea id="fl-vs-music-simple-desc" placeholder="Dark 1980s thriller score, slow pulsing synth…"></textarea></div>' +
      '<div class="fl-form"><label>Duration (sec)<input id="fl-vs-music-dur" type="number" value="60" min="10" max="240"></label>' +
      '<label>BPM<input id="fl-tune-bpm" type="number" value="' + esc(String(musicAdv.bpm || 90)) + '"></label>' +
      '<label>Key<input id="fl-tune-key" type="text" value="' + esc(musicAdv.key || 'Am') + '"></label>' +
      '<label>Bars<input id="fl-tune-bars" type="number" value="' + esc(String(musicAdv.bars || 8)) + '"></label></div>' +
      '<div class="fl-vs-field"><label>Lyrics (optional)</label>' +
      '<textarea id="fl-vs-music-lyrics" placeholder="[Verse 1]…"></textarea></div></div>' +

      '<div id="fl-studio-image-widgets" ' + (FL_STUDIO.modality === 'image' ? '' : 'hidden') + '>' +
      '<div class="fl-vs-tune-grid">' + imgWidgets.map(function (w) {
        var opts = (w.options || []).map(function (o) { return '<option>' + esc(o) + '</option>'; }).join('');
        var id = w.id === 'aspect' ? 'fl-img-aspect'
          : (w.id === 'ref_strength' ? 'fl-img-lock' : (w.id === 'batch' ? 'fl-img-batch' : ('fl-img-' + w.id)));
        return '<div class="fl-vs-tune-slot"><label>' + esc(w.label || w.id) +
          '</label><select id="' + id + '">' + opts + '</select></div>';
      }).join('') + '</div></div>' +

      '<div class="fl-rail" style="margin-top:12px">' +
      (canGenerate
        ? '<button type="button" class="fl-vs-submit" onclick="floorStudioGenerate()">Generate</button>'
        : (showInstallPacks
          ? '<button type="button" class="fl-vs-submit" ' + (packsRunning ? 'disabled ' : '') +
            'onclick="floorStudioInstallPacks()">' +
            (packsRunning ? 'Installing packs…' : 'Install creative packs') + '</button>'
          : '<button type="button" class="fl-vs-submit" disabled title="' + esc(genBlock) +
            '">Generate locked</button>')) +
      '<button type="button" class="fl-vs-submit ghost" onclick="floorStudioSetModality((window.FL_STUDIO&&window.FL_STUDIO.modality)||\'image\')">Optimal defaults</button>' +
      btn('Setup / Advanced', "typeof showVideoStudioSetup==='function'&&showVideoStudioSetup()", true) +
      btn('Open ComfyUI', "window.open(" + JSON.stringify(endpoint || 'http://127.0.0.1:8188/') + ",'_blank','noopener')", true) +
      '</div><p id="fl-studio-msg" class="muted" style="margin-top:8px">' +
      (canGenerate ? '' : esc(genBlock)) + '</p></div>' +

      '<div class="fl-vs-card"><h3>Tuning Parameters</h3>' +
      '<div class="fl-vs-tune-grid" id="fl-tune-image">' +
      '<div class="fl-vs-tune-slot"><label>Steps</label><input id="fl-tune-steps" type="number" value="28"></div>' +
      '<div class="fl-vs-tune-slot"><label>CFG</label><input id="fl-tune-cfg" type="number" value="5" step="0.5"></div>' +
      '<div class="fl-vs-tune-slot"><label>Resolution</label><select id="fl-tune-res"><option>1024x1024</option><option>1280x720</option><option>768x1344</option></select></div>' +
      '<div class="fl-vs-tune-slot"><label>Seed</label><input id="fl-tune-seed" placeholder="random"></div>' +
      '<div class="fl-vs-tune-slot"><label>Quality</label><select id="fl-tune-quality"><option>standard</option><option>high</option><option>draft</option></select></div>' +
      '</div>' +
      '<div class="fl-vs-tune-grid" id="fl-tune-video" hidden>' +
      '<div class="fl-vs-tune-slot"><label>Duration (s)</label><input id="fl-tune-dur" type="number" value="4"></div>' +
      '<div class="fl-vs-tune-slot"><label>FPS</label><input id="fl-tune-fps" type="number" value="24"></div>' +
      '</div>' +
      '<div id="fl-tune-music" hidden></div></div>' +

      '<div class="fl-vs-card"><h3>Workshop Log</h3><pre class="fl-vs-log" id="fl-vs-log">Ready.</pre>' +
      '<div class="fl-two" style="margin-top:12px">' +
      panel('Queue', listCards(d.creative_queue || [], jobCard, 'Queue empty.')) +
      panel('Active', listCards(d.active_renders || [], jobCard, 'No active renders.')) +
      '</div>' +
      panel('Recent output', listCards(d.recent_output || d.recent_creative_jobs || [], jobCard, 'No completed jobs yet.')) +
      '</div>' +

      '<div class="fl-vs-modal" id="flVsOptimalModal" hidden onclick="if(event.target===this)floorStudioCloseModals()">' +
      '<div class="fl-vs-modal-card"><h3 style="margin-top:0;color:#f2d596">Optimal prompts</h3>' +
      '<p class="muted">One-tap Keep starters for ' + esc(FL_STUDIO.modality) + '.</p>' +
      '<div class="fl-vs-presets" id="fl-studio-optimal">' +
      (optPacks.map(function (p) {
        return '<button type="button" class="fl-vs-preset" onclick=\'floorStudioApplyOptimal(' +
          JSON.stringify(p.text || '') + ');floorStudioCloseModals()\'>' + esc(p.label || p.id) + '</button>';
      }).join('') || '<span class="muted">—</span>') +
      '</div><button type="button" class="fl-vs-submit ghost" onclick="floorStudioCloseModals()">Close</button></div></div>' +

      '<div class="fl-vs-modal" id="flVsFillModal" hidden onclick="if(event.target===this)floorStudioCloseModals()">' +
      '<div class="fl-vs-modal-card"><h3 style="margin-top:0;color:#f2d596">✦ Fill This In For Me</h3>' +
      '<p class="muted">Describe the vibe — Muse drafts a workshop-ready prompt.</p>' +
      '<div class="fl-vs-field"><label>Topic / scene</label><input id="fl-vs-fill-topic" placeholder="rainy neon alley, lone courier"></div>' +
      '<div class="fl-vs-field"><label>Mood</label><select id="fl-vs-fill-mood">' +
      '<option>cinematic</option><option>tender</option><option>tense</option><option>hopeful</option><option>noir</option></select></div>' +
      '<div class="fl-rail"><button type="button" class="fl-vs-submit" onclick="floorStudioFillApply()">Apply</button>' +
      '<button type="button" class="fl-vs-submit ghost" onclick="floorStudioCloseModals()">Cancel</button></div></div></div>' +

      '</div>';

    floorShell('The Workshop', 'Muse · Keep Video Studio', body, '', 'studio');
    floorStudioSetModality(FL_STUDIO.modality);
  }

  /* —— Ops —— */
  async function floorConfigureIntegration(which) {
    var msg = document.getElementById('fl-int-msg');
    function say(t) { if (msg) msg.textContent = t; }
    try {
      if (which === 'discord') {
        say('Aria: I\'ll set up Discord for you. Just paste the bot token when asked — nothing else.');
        var prep = await api('/api/expansion/discord/setup', {});
        var tokenEl = document.getElementById('fl-discord-token');
        var token = tokenEl ? String(tokenEl.value || '').trim() : '';
        if (!token && !(prep.data && prep.data.discovery && prep.data.discovery.bot_configured)) {
          say('Aria: I need one thing — paste your Discord bot token in the box, then tap Configure again.');
          return;
        }
        if (token) {
          say('Aria: Saving your token privately…');
          prep = await api('/api/expansion/discord/setup', { token: token });
          if (tokenEl) tokenEl.value = '';
        }
        var inv = (prep.data && (prep.data.invite_url || (prep.data.invite && prep.data.invite.invite_url))) || '';
        if (!inv && prep.data && prep.data.discovery) inv = prep.data.discovery.invite_url || '';
        if (inv) {
          say('Aria: Almost done — a Discord window will open. Click Authorize on your server.');
          try { window.open(inv, '_blank', 'noopener'); } catch (e) {}
        }
        say('Aria: Discord status → ' + ((prep.data && prep.data.state) || (prep.ok ? 'ok' : 'check token')));
      } else if (which === 'home_assistant' || which === 'ha') {
        var urlEl = document.getElementById('fl-ha-url');
        var tokEl = document.getElementById('fl-ha-token');
        var url = urlEl ? String(urlEl.value || '').trim() : '';
        var tok = tokEl ? String(tokEl.value || '').trim() : '';
        if (!url || !tok) {
          say('Aria: Two boxes — your Home Assistant address (like http://homeassistant.local:8123) and a long-lived token from HA → Profile → Long-Lived Access Tokens.');
          return;
        }
        say('Aria: Checking the connection…');
        var ha = await api('/api/expansion/home-assistant/config', { url: url, token: tok, verify: true });
        if (tokEl) tokEl.value = '';
        var n = (ha.data && ha.data.verify && ha.data.verify.entity_count) || 0;
        say('Aria: Home Assistant → ' + ((ha.data && ha.data.state) || '') + (n ? (' · found ' + n + ' devices/entities') : ''));
      } else if (which === 'n8n') {
        say('Aria: Installing n8n with Docker for you — no password needed for the base service.');
        var n8 = await api('/api/expansion/n8n/setup', {});
        if (!n8.ok && n8.status === 404) {
          say('Aria: Server needs a restart to pick up the n8n installer route. Soft-update again, then retry.');
          return;
        }
        say('Aria: n8n → ' + ((n8.data && n8.data.state) || (n8.ok ? 'READY' : 'failed')) +
          (n8.data && n8.data.deploy && n8.data.deploy.endpoint ? (' · ' + n8.data.deploy.endpoint) : ''));
      }
      setTimeout(function () { renderOpsFloor(); }, 500);
    } catch (e) {
      say(String(e));
    }
  }

  function integrationCard(id, v, extra) {
    v = v || {};
    var st = v.state || 'unknown';
    var disc = v.discovery || {};
    var action = disc.user_action || '';
    var needs = /NEEDS_CREDENTIAL|NEEDS_AUTHORIZATION|NOT_INSTALLED|LIMITED/i.test(st);
    var body = '<div class="fl-card" id="fl-int-' + esc(id) + '"><b>' + esc(id.replace(/_/g, ' ')) + '</b> ' +
      pill(st) +
      '<p class="muted">' + esc(v.detail || v.note || v.message || '') + '</p>';
    if (id === 'discord' && needs) {
      body += '<p class="fl-note">Aria: Paste your Discord bot token below. I install the rest. Then authorize once in your server.</p>' +
        '<label>Bot token<input id="fl-discord-token" type="password" autocomplete="off" placeholder="paste token — never shared"></label>' +
        '<div class="fl-rail" style="margin-top:8px">' +
        btn('Configure Discord', "floorConfigureIntegration('discord')", false) +
        (disc.invite_url
          ? btn('Open authorize', "window.open(" + JSON.stringify(disc.invite_url) + ",'_blank','noopener')", true)
          : '') + '</div>';
    } else if (id === 'home_assistant' && needs) {
      body += '<p class="fl-note">Aria: Two fields only — the address of Home Assistant, and a long-lived token from HA Profile.</p>' +
        '<label>HA URL<input id="fl-ha-url" placeholder="http://homeassistant.local:8123" value="' +
        esc(disc.url || 'http://homeassistant.local:8123') + '"></label>' +
        '<label>Long-lived token<input id="fl-ha-token" type="password" autocomplete="off" placeholder="from HA → Profile → Long-Lived Access Tokens"></label>' +
        '<div class="fl-rail" style="margin-top:8px">' +
        btn('Connect HA', "floorConfigureIntegration('ha')", false) + '</div>';
    } else if (id === 'n8n' && needs) {
      body += '<p class="fl-note">Aria: One click. I deploy n8n with Docker. No account needed for the base service.</p>' +
        '<div class="fl-rail" style="margin-top:8px">' +
        btn('Install n8n', "floorConfigureIntegration('n8n')", false) + '</div>';
    }
    if (extra) body += extra;
    return body + '</div>';
  }

  async function renderOpsFloor() {
    var d;
    try { d = await apiGet('/api/expansion/ops'); }
    catch (e) { floorShell('Operations', 'Sentry', empty('Failed: ' + e)); return; }
    var ha = (d.service_readiness && d.service_readiness.home_assistant) || d.home_assistant || {};
    var health = d.health_observations || {};
    var emo = health.emotion || {};
    var services = d.service_readiness || { home_assistant: ha };
    var integ = d.integrations || {};
    var recommended = (integ.recommended || []).filter(function (x) {
      return x && (x.id === 'discord' || x.id === 'home_assistant' || x.id === 'n8n');
    });
    var checklist = recommended.length
      ? '<div class="fl-panel"><h3 class="fl-h">Recommended integrations</h3>' +
        ariaGuideCard(
          'Aria',
          'These are optional. Tap Configure — I do the hard parts. You only paste a secret when Discord or Home Assistant asks. n8n needs no password for the basic install.'
        ) +
        '<p class="fl-note">' + esc(integ.aria || 'Otacon installs what it can; credentials only when required.') + '</p>' +
        '<div class="fl-grid">' + recommended.map(function (it) {
          return '<div class="fl-card"><b>' + esc(it.label || it.id) + '</b> ' +
            pill(it.state || '') +
            '<p class="muted">' + esc(it.detail || '') + '</p>' +
            (it.needs_credential || it.user_action === 'credential' || it.user_action === 'authorization' || it.user_action === 'install'
              ? '<div class="fl-rail">' + btn('Configure now', "floorConfigureIntegration('" +
                (it.id === 'home_assistant' ? 'ha' : it.id) + "')", false) + '</div>'
              : '') + '</div>';
        }).join('') + '</div></div>'
      : '';
    var openN = (d.monitoring_state && d.monitoring_state.sentry_open_jobs) || 0;
    var failN = (d.monitoring_state && d.monitoring_state.failed) || 0;
    var incN = (d.active_incidents || []).length;
    var findN = (d.security_findings || []).length;
    floorShell('Sentry Operations', 'Military sci-fi perimeter',
      cineHero('Perimeter command', 'Sentry Operations',
        'Futuristic military ops glass — incidents, remediation, and optional integrations under green TAC lighting.') +
      '<div class="fl-ops-tac fl-ops-scanline">' +
      '<div class="fl-ops-tile"><div class="n">' + esc(String(incN)) + '</div><div class="l">incidents</div></div>' +
      '<div class="fl-ops-tile"><div class="n">' + esc(String(findN)) + '</div><div class="l">findings</div></div>' +
      '<div class="fl-ops-tile"><div class="n">' + esc(String(openN)) + '</div><div class="l">open jobs</div></div>' +
      '<div class="fl-ops-tile"><div class="n">' + esc(String(failN)) + '</div><div class="l">failed</div></div>' +
      '<div class="fl-ops-tile"><div class="n">' + esc(String(Object.keys(services).length)) + '</div><div class="l">services</div></div>' +
      '</div>' +
      '<div class="fl-symbol-row"><span class="fl-symbol">⚔</span><span class="fl-symbol">🛡</span><span class="fl-symbol">📡</span><span class="fl-symbol">⚙</span></div>' +
      ariaGuideCard(
        'Aria',
        'Ops is where optional extras live. Discord, Home Assistant, and n8n are not required for chat. When you want one, use Configure — I walk you through it in plain language.'
      ) +
      '<p class="fl-note">' + esc(d.note || 'Home Assistant remains optional.') + '</p>' +
      checklist +
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
        metric(openN, 'open') + metric(failN, 'failed') + '</div>') +
      panel('Service readiness', '<div class="fl-grid">' + Object.keys(services).map(function (k) {
        return integrationCard(k, services[k] || {});
      }).join('') + '</div><div id="fl-int-msg" class="muted" style="margin-top:8px"></div>') +
      panel('Evidence', listCards(d.evidence || [], function (e) {
        return '<div class="fl-card"><b>' + esc(e.job_id) + '</b>' +
          '<p class="muted">' + esc((e.evidence_ids || []).join(', ') || '—') +
          (e.error ? ' · ' + esc(e.error) : '') + '</p>' + jobLink(e.job_id) + '</div>';
      }, 'No evidence rows.')),
      '', 'ops');
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
      panel('Readiness', readinessHud(ready)) +
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
    'video-studio': renderCreativeFloor,
    videostudio: renderCreativeFloor,
    studio: renderCreativeFloor,
    muse: renderCreativeFloor,
    ops: renderOpsFloor,
    ha: renderOpsFloor,
    'home-assistant': renderOpsFloor,
    rooms: renderPageBuilderFloor,
    'page-builder': renderPageBuilderFloor,
    dashboard: renderCommandCenterFloor,
    'command-center': renderCommandCenterFloor
  };

  Object.assign(window, {
    FL: FL,
    FL_STUDIO: FL_STUDIO,
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
    floorConfigureIntegration: floorConfigureIntegration,
    floorStudioSetModality: floorStudioSetModality,
    floorStudioGenerate: floorStudioGenerate,
    floorStudioInstallPacks: floorStudioInstallPacks,
    floorStudioApplyChip: floorStudioApplyChip,
    floorStudioOpenOptimal: floorStudioOpenOptimal,
    floorStudioOpenFill: floorStudioOpenFill,
    floorStudioFillApply: floorStudioFillApply,
    floorStudioAddActor: floorStudioAddActor,
    floorStudioAddStyle: floorStudioAddStyle,
    floorStudioOnDrop: floorStudioOnDrop,
    floorStudioCloseModals: floorStudioCloseModals,
    startPsalmRain: startPsalmRain,
    floorStudioApplyOptimal: floorStudioApplyOptimal,
    floorStudioToggleActor: floorStudioToggleActor,
    floorStudioPickStyle: floorStudioPickStyle,
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
