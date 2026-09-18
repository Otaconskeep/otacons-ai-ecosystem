/* Video Studio HUD 5 — Ref 004/005 dashboard. Additive; does not replace workshop JS. */
(function (global) {
  'use strict';

  var DEFAULTS = {
    ok: true,
    engine: 'h3',
    resolution: '1344x768',
    duration_sec: 5,
    fps: 24,
    h3_steps_auto: 6,
    h3_steps_fast: 4,
    h3_steps_quality: 8,
    h3_steps_no_turbo: 35,
    turbo_available: true,
    turbo_lora: 'minimax_h3_turbo_v4_step600_ema.safetensors',
    cfg_scale_default: 2,
    cfg_note: 'Guidance is how tightly OtaconsKeep Engine Foxhound V3 follows your prompt (1–8).',
    weights: {
      h3_turbo_lora: 'minimax_h3_turbo_v4_step600_ema.safetensors',
      hidream_note: 'Still pictures use Otacons Image Generator Mk IV. Video uses OtaconsKeep Engine Foxhound V3. Draft clips use Otacons Video Gen X.'
    },
    workers_note: 'UI only — this endpoint does not start GPU workers'
  };

  var JOB_ETA = {
    keyframe: 90,
    image_v1: 90,
    hidream_v1: 120,
    h3_final_render: 480,
    video_v2: 180,
    video_v2_default: 180,
    video_v2_start_end: 240,
    video_v2_auto_start_end: 300,
    video_v2_direct_t2v: 180,
    video_v2_ltx25: 180,
    music_v1: 90,
    project: 600,
    text: 20,
    script: 45
  };

  var state = {
    health: null,
    jobs: [],
    telem: null,
    vramHist: [],
    queueHist: [],
    t0: Date.now(),
    waveRaf: 0,
    clockTimer: 0,
    mode: 'video'
  };

  function $(id) { return document.getElementById(id); }

  function playClick() {
    try {
      if (global.OtaconSFX && typeof global.OtaconSFX.play === 'function') {
        global.OtaconSFX.play('click');
      }
    } catch (e) {}
  }

  function clamp(n, a, b) {
    n = Number(n);
    if (isNaN(n)) return a;
    return Math.max(a, Math.min(b, n));
  }

  function fmtMMSS(sec) {
    sec = Number(sec) || 0;
    var sign = sec < 0 ? '-' : '';
    var abs = Math.round(Math.abs(sec));
    var m = Math.floor(abs / 60);
    var s = abs % 60;
    return sign + m + ':' + String(s).padStart(2, '0');
  }

  function jobStatus(j) {
    return String((j && j.status) || '').toLowerCase();
  }

  function isActiveJob(j) {
    if (!j) return false;
    var st = jobStatus(j);
    if (['completed', 'failed', 'cancelled', 'ready', 'needs_attention'].indexOf(st) >= 0) return false;
    return true;
  }

  function activeJobs(jobs) {
    return (jobs || []).filter(isActiveJob);
  }

  function etaFor(j) {
    if (!j) return JOB_ETA.video_v2_default;
    if (j.eta_seconds != null && Number(j.eta_seconds) > 0) return Number(j.eta_seconds);
    var t = j.job_type || '';
    if (JOB_ETA[t] != null) return JOB_ETA[t];
    if (t.indexOf('image') >= 0) return JOB_ETA.image_v1;
    if (t.indexOf('music') >= 0) return JOB_ETA.music_v1;
    if (t.indexOf('video') >= 0 || t.indexOf('h3') >= 0) return JOB_ETA.video_v2_default;
    if (t === 'project') return JOB_ETA.project;
    return JOB_ETA.video_v2_default;
  }

  function jobKindLabel(j) {
    if (!j) return 'job';
    var t = j.job_type || '';
    if (t === 'h3_final_render' || t.indexOf('video') === 0) return 'video';
    if (t === 'image_v1' || t === 'hidream_v1' || t === 'image') return 'image';
    if (t === 'music_v1') return 'music';
    if (t === 'project') return (j.project_mode === 'movie') ? 'movie' : 'project';
    if (t === 'script') return 'script';
    if (t === 'text') return 'write';
    return t || 'job';
  }

  function currentMode() {
    if (typeof global.vsMode === 'string' && global.vsMode) return global.vsMode;
    var active = document.querySelector('.vs-mode-btn.active');
    return (active && active.getAttribute('data-mode')) || state.mode || 'video';
  }

  function ensureLoader() {
    if (global.MovieFUI && typeof global.MovieFUI.ensureLoader === 'function') {
      global.MovieFUI.ensureLoader({
        brand: document.documentElement.getAttribute('data-mf-loader-brand') || 'OTACON // VIDEO STUDIO',
        sub: document.documentElement.getAttribute('data-mf-loader-sub') || 'ARMING WORKSHOP TUNING DECK'
      });
    }
  }

  function mountTelem() {
    var host = $('vs-telem-host');
    if (!host) return;
    if (global.MovieFUI && typeof global.MovieFUI.mountCyberdeck === 'function') {
      if (!host.getAttribute('data-mf-cyberdeck-mounted')) {
        host.setAttribute('data-mf-cyberdeck', 'full');
        host.setAttribute('data-mf-cyberdeck-mounted', '1');
        global.MovieFUI.mountCyberdeck(host, {
          compact: false,
          title: host.getAttribute('data-telem-title') || 'SYS // VIDEO STUDIO CYBERDECK · PROC otacon-executor',
          endpoint: host.getAttribute('data-telem-endpoint') || '/api/executor/telemetry'
        });
      }
      return;
    }
    if (global.MovieFUI && typeof global.MovieFUI.telemHtml === 'function' && !host.querySelector('.mf-telem-deck')) {
      host.innerHTML = global.MovieFUI.telemHtml({
        compact: false,
        title: 'SYS // VIDEO STUDIO CYBERDECK · PROC otacon-executor'
      });
    }
  }

  function bindPair(a, b) {
    if (!a || !b || a === b) return;
    function copy(from, to) {
      if (from.value !== to.value) to.value = from.value;
    }
    a.addEventListener('input', function () { copy(a, b); });
    a.addEventListener('change', function () { copy(a, b); });
    b.addEventListener('input', function () { copy(b, a); });
    b.addEventListener('change', function () { copy(b, a); });
    if (a.value) copy(a, b);
    else if (b.value) copy(b, a);
  }

  function rehomeField(srcId, slotId) {
    var src = $(srcId);
    var slot = $(slotId);
    if (!src || !slot) return false;
    var field = src.closest('.vs-field') || src;
    if (slot.contains(field)) return true;
    slot.appendChild(field);
    return true;
  }

  function why(el, text) {
    if (!el) return;
    var host = el.closest('.vs-field') || el.parentElement;
    if (!host) return;
    if (host.querySelector('.vs-why')) return;
    var cap = document.createElement('span');
    cap.className = 'vs-why';
    cap.textContent = text;
    host.appendChild(cap);
  }

  function setTurboReadout(d) {
    var el = $('vs-turbo-readout');
    if (!el) return;
    var avail = !!d.turbo_available;
    var html = '<strong>OtaconsKeep Engine Foxhound V3</strong>';
    if (avail) {
      html += 'Turbo path is live. Auto uses 6 steps, Fast 4, Quality 8.';
    } else {
      html += 'Turbo path is off. Jobs use the full-quality <b>35-step</b> Foxhound V3 graph.';
    }
    html += '<br>Stills: Otacons Image Generator Mk IV. Draft video: Otacons Video Gen X.';
    el.innerHTML = html;
  }

  function applyDefaults(d) {
    d = d || DEFAULTS;
    var steps = $('vs-tune-steps');
    var cfg = $('vs-tune-cfg');
    var dur = $('vs-vid-duration') || $('vs-tune-duration');
    var fps = $('vs-vid-fps') || $('vs-tune-fps');
    var aspect = $('vs-vid-aspect') || $('vs-tune-aspect');
    if (steps && !steps.dataset.userTouched) steps.value = String(d.h3_steps_auto || 6);
    if (cfg && !cfg.dataset.userTouched) cfg.value = String(d.cfg_scale_default || 2);
    if (dur && !dur.value) dur.value = String(d.duration_sec || 5);
    if (fps && !fps.value) fps.value = String(d.fps || 24);
    if (aspect && d.resolution) {
      var opt = Array.prototype.find.call(aspect.options || [], function (o) { return o.value === d.resolution; });
      if (opt && !aspect.dataset.userTouched) aspect.value = d.resolution;
    }
    var cfgNote = $('vs-tune-cfg-note');
    if (cfgNote) {
      cfgNote.textContent = 'Guidance is how tightly OtaconsKeep Engine Foxhound V3 follows your prompt (1–8).';
    }
    setTurboReadout(d);
    var q = $('vs-render-quality');
    if (q && steps) {
      function syncStepsFromQuality() {
        if (steps.dataset.userTouched) return;
        if (q.value === 'fast') steps.value = String(d.h3_steps_fast || 4);
        else if (q.value === 'quality') steps.value = String(d.h3_steps_quality || 8);
        else steps.value = String(d.turbo_available ? (d.h3_steps_auto || 6) : (d.h3_steps_no_turbo || 35));
        syncFaders();
        drawHudRings();
      }
      q.addEventListener('change', syncStepsFromQuality);
    }
    syncFaders();
    drawHudRings();
  }

  function syncHudToLegacy() {
    [
      ['vs-tune-aspect', 'vs-vid-aspect'],
      ['vs-tune-duration', 'vs-vid-duration'],
      ['vs-tune-fps', 'vs-vid-fps'],
      ['vs-tune-seed', 'vs-vid-seed'],
      ['vs-tune-quality', 'vs-render-quality'],
      ['vs-tune-resolution', 'vs-resolution']
    ].forEach(function (pair) {
      var a = $(pair[0]), b = $(pair[1]);
      if (a && b && a.value !== '') b.value = a.value;
    });
  }

  function vsAppendTuning(fd) {
    if (!fd) return fd;
    syncHudToLegacy();
    var stepsEl = $('vs-tune-steps');
    var cfgEl = $('vs-tune-cfg');
    if (stepsEl && stepsEl.value !== '') {
      try { fd.append('h3_steps', stepsEl.value); } catch (e) {}
      try { fd.append('steps', stepsEl.value); } catch (e) {}
    }
    if (cfgEl && cfgEl.value !== '') {
      try { fd.append('cfg_scale', cfgEl.value); } catch (e) {}
    }
    return fd;
  }

  function wireHowTo() {
    document.querySelectorAll('[data-vs-jump]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        playClick();
        var sel = btn.getAttribute('data-vs-jump');
        var target = sel ? document.querySelector(sel) : null;
        if (target) {
          target.scrollIntoView({ behavior: 'smooth', block: 'start' });
          target.classList.add('vs-jump-flash');
          setTimeout(function () { target.classList.remove('vs-jump-flash'); }, 900);
        }
      });
    });
  }

  function markTouched(id) {
    var el = $(id);
    if (!el) return;
    el.addEventListener('input', function () { el.dataset.userTouched = '1'; });
    el.addEventListener('change', function () { el.dataset.userTouched = '1'; });
  }

  function buildRackIfMissing() {
    if ($('vs-tuning-rack')) return;
    var form = $('vs-form');
    var host = document.createElement('div');
    host.className = 'vs-card vs-tuning-rack mf-mod';
    host.id = 'vs-tuning-rack';
    host.innerHTML =
      '<div class="mf-mod-h">MODULE · TUNING RACK · PIPELINE KNOBS<span class="vs-mod-live">LIVE</span></div>' +
      '<h2>Tuning Parameters</h2>' +
      '<p class="vs-tune-lede">Pipeline knobs for this shot. Generate reads these values.</p>' +
      '<div class="vs-tune-grid">' +
      '<div class="vs-tune-slot" id="vs-tune-slot-aspect"></div>' +
      '<div class="vs-tune-slot" id="vs-tune-slot-resolution"></div>' +
      '<div class="vs-tune-slot" id="vs-tune-slot-duration"></div>' +
      '<div class="vs-tune-slot" id="vs-tune-slot-fps"></div>' +
      '<div class="vs-tune-slot" id="vs-tune-slot-seed"></div>' +
      '<div class="vs-tune-slot" id="vs-tune-slot-quality"></div>' +
      '<div class="vs-field"><label for="vs-tune-steps">Render steps</label>' +
      '<input type="number" id="vs-tune-steps" min="4" max="35" value="6" step="1">' +
      '<span class="vs-why">How many denoising passes OtaconsKeep Engine Foxhound V3 runs. Auto=6, Fast=4, Quality=8, full=35. More steps = slower, usually cleaner motion.</span></div>' +
      '<div class="vs-field"><label for="vs-tune-cfg">Guidance</label>' +
      '<input type="number" id="vs-tune-cfg" min="1" max="8" value="2" step="0.1">' +
      '<span class="vs-why">How tightly Foxhound V3 follows the prompt (1–8). Higher = closer to the text, sometimes stiffer motion.</span></div>' +
      '</div>' +
      '<div class="vs-turbo-readout" id="vs-turbo-readout"></div>' +
      '<p class="vs-tune-cfg-note vs-why" id="vs-tune-cfg-note"></p>';
    if (form && form.parentNode) form.parentNode.insertBefore(host, form.nextSibling);
    else {
      var wrap = document.querySelector('.vs-wrap');
      if (wrap) wrap.appendChild(host);
    }
  }

  function rehomeKnownFields() {
    rehomeField('vs-resolution', 'vs-tune-slot-resolution');
    rehomeField('vs-render-quality', 'vs-tune-slot-quality');
    why($('vs-resolution'), 'Still / image canvas. Video uses Aspect Ratio, not this selector.');
    why($('vs-render-quality'), 'Auto picks 6 turbo steps. Fast=4, Quality=8. A raw Steps value overrides this.');
    bindPair($('vs-tune-aspect'), $('vs-vid-aspect'));
    bindPair($('vs-tune-resolution'), $('vs-resolution'));
    bindPair($('vs-tune-duration'), $('vs-vid-duration'));
    bindPair($('vs-tune-fps'), $('vs-vid-fps'));
    bindPair($('vs-tune-seed'), $('vs-vid-seed'));
    bindPair($('vs-tune-quality'), $('vs-render-quality'));
  }

  function fetchDefaults() {
    return fetch('/video-studio/api/tuning-defaults', { cache: 'no-store', credentials: 'same-origin' })
      .then(function (r) { return r.json(); })
      .then(function (j) {
        if (j && j.ok) return j;
        throw new Error('defaults not ok');
      })
      .catch(function () { return DEFAULTS; });
  }

  /* ── Canvas widgets ─────────────────────────────────────────────── */
  function prepCanvas(canvas, cssW, cssH) {
    if (!canvas) return null;
    var dpr = window.devicePixelRatio || 1;
    var w = cssW || canvas.clientWidth || canvas.width || 120;
    var h = cssH || canvas.clientHeight || canvas.height || 120;
    canvas.width = Math.max(1, Math.round(w * dpr));
    canvas.height = Math.max(1, Math.round(h * dpr));
    var ctx = canvas.getContext('2d');
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    return { ctx: ctx, w: w, h: h };
  }

  function drawTripleRing(canvas, pct, color, needle) {
    var g = prepCanvas(canvas, canvas.clientWidth, canvas.clientHeight);
    if (!g) return;
    var ctx = g.ctx, w = g.w, h = g.h, cx = w / 2, cy = h / 2;
    var r = Math.min(cx, cy) - 8;
    var p = clamp(pct, 0, 100) / 100;
    ctx.clearRect(0, 0, w, h);

    ctx.strokeStyle = 'rgba(151,159,236,0.16)';
    ctx.lineWidth = 1;
    for (var ring = 0; ring < 3; ring++) {
      ctx.beginPath();
      ctx.arc(cx, cy, r - ring * (r * 0.18), 0, Math.PI * 2);
      ctx.stroke();
    }

    ctx.strokeStyle = 'rgba(151,159,236,0.35)';
    ctx.lineWidth = 1;
    for (var i = 0; i < 60; i++) {
      var a = (i / 60) * Math.PI * 2 - Math.PI / 2;
      var inner = r - (i % 5 === 0 ? 10 : 5);
      ctx.beginPath();
      ctx.moveTo(cx + Math.cos(a) * inner, cy + Math.sin(a) * inner);
      ctx.lineTo(cx + Math.cos(a) * r, cy + Math.sin(a) * r);
      ctx.stroke();
    }

    ctx.strokeStyle = 'rgba(151,159,236,0.18)';
    ctx.lineWidth = 8;
    ctx.beginPath();
    ctx.arc(cx, cy, r - 16, 0, Math.PI * 2);
    ctx.stroke();

    ctx.strokeStyle = color || '#979fec';
    ctx.lineCap = 'round';
    ctx.lineWidth = 8;
    ctx.shadowColor = color || '#979fec';
    ctx.shadowBlur = 10;
    ctx.beginPath();
    ctx.arc(cx, cy, r - 16, -Math.PI / 2, -Math.PI / 2 + p * Math.PI * 2);
    ctx.stroke();
    ctx.shadowBlur = 0;

    ctx.strokeStyle = '#d9b6fd';
    ctx.lineWidth = 3;
    ctx.beginPath();
    ctx.arc(cx, cy, r - 28, -Math.PI / 2, -Math.PI / 2 + p * Math.PI * 1.15);
    ctx.stroke();

    if (needle) {
      var na = -Math.PI / 2 + p * Math.PI * 2;
      ctx.strokeStyle = '#e4e6fb';
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(cx, cy);
      ctx.lineTo(cx + Math.cos(na) * (r - 22), cy + Math.sin(na) * (r - 22));
      ctx.stroke();
      ctx.fillStyle = '#e095b5';
      ctx.beginPath();
      ctx.arc(cx, cy, 4, 0, Math.PI * 2);
      ctx.fill();
    }
  }

  function drawWave(canvas, histA, histB, t) {
    var g = prepCanvas(canvas, canvas.clientWidth, 168);
    if (!g) return;
    var ctx = g.ctx, w = g.w, h = g.h;
    ctx.clearRect(0, 0, w, h);
    ctx.strokeStyle = 'rgba(151,159,236,0.12)';
    ctx.lineWidth = 1;
    for (var gy = 0; gy < 5; gy++) {
      var y = (h / 5) * gy + 8;
      ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(w, y); ctx.stroke();
    }
    function layer(amp, freq, phase, color, alpha) {
      ctx.beginPath();
      for (var x = 0; x <= w; x += 3) {
        var y2 = h * 0.55 + Math.sin(x * freq + phase) * amp + Math.sin(x * freq * 0.37 + phase * 1.7) * amp * 0.35;
        if (x === 0) ctx.moveTo(x, y2); else ctx.lineTo(x, y2);
      }
      ctx.strokeStyle = color;
      ctx.globalAlpha = alpha;
      ctx.lineWidth = 1.4;
      ctx.stroke();
      ctx.globalAlpha = 1;
    }
    layer(h * 0.18, 0.018, t * 0.9, 'rgba(100,142,208,0.85)', 0.55);
    layer(h * 0.14, 0.024, t * 1.2 + 1, 'rgba(151,159,236,0.9)', 0.7);
    layer(h * 0.10, 0.031, t * 0.7 + 2, 'rgba(217,182,253,0.8)', 0.55);

    function series(arr, color) {
      if (!arr || arr.length < 2) return;
      ctx.beginPath();
      for (var i = 0; i < arr.length; i++) {
        var x = (i / (arr.length - 1)) * w;
        var y = h - 10 - clamp(arr[i], 0, 100) / 100 * (h - 20);
        if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
      }
      ctx.strokeStyle = color;
      ctx.lineWidth = 2;
      ctx.shadowColor = color;
      ctx.shadowBlur = 8;
      ctx.stroke();
      ctx.shadowBlur = 0;
    }
    series(histA, '#a7c1e8');
    series(histB, '#e095b5');
  }

  function drawSpark(canvas, arr, color) {
    var g = prepCanvas(canvas, canvas.clientWidth, 42);
    if (!g) return;
    var ctx = g.ctx, w = g.w, h = g.h;
    ctx.clearRect(0, 0, w, h);
    if (!arr || !arr.length) return;
    var max = 1;
    for (var i = 0; i < arr.length; i++) if (arr[i] > max) max = arr[i];
    ctx.beginPath();
    for (var j = 0; j < arr.length; j++) {
      var x = (j / Math.max(1, arr.length - 1)) * w;
      var y = h - 2 - (arr[j] / max) * (h - 4);
      if (j === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    }
    ctx.strokeStyle = color || '#979fec';
    ctx.lineWidth = 1.6;
    ctx.stroke();
  }

  function drawHBars(canvas, items) {
    var g = prepCanvas(canvas, canvas.clientWidth, Math.max(54, (items.length || 1) * 14));
    if (!g) return;
    var ctx = g.ctx, w = g.w;
    ctx.clearRect(0, 0, w, g.h);
    items.forEach(function (it, idx) {
      var y = idx * 14 + 2;
      ctx.fillStyle = 'rgba(151,159,236,0.12)';
      ctx.fillRect(0, y, w, 9);
      ctx.fillStyle = it.color || '#979fec';
      ctx.fillRect(0, y, w * clamp(it.pct, 0, 100) / 100, 9);
    });
  }

  function drawVBars(canvas, values, colors) {
    var g = prepCanvas(canvas, canvas.clientWidth, 72);
    if (!g) return;
    var ctx = g.ctx, w = g.w, h = g.h;
    ctx.clearRect(0, 0, w, h);
    var n = values.length || 1;
    var bw = Math.max(3, (w / n) - 3);
    var max = 1;
    values.forEach(function (v) { if (v > max) max = v; });
    values.forEach(function (v, i) {
      var bh = (v / max) * (h - 4);
      ctx.fillStyle = (colors && colors[i]) || (i % 2 ? '#979fec' : '#648ed0');
      ctx.fillRect(i * (bw + 3), h - bh, bw, bh);
    });
  }

  function drawPie(canvas, slices) {
    var g = prepCanvas(canvas, canvas.clientWidth, 88);
    if (!g) return;
    var ctx = g.ctx, cx = g.w / 2, cy = g.h / 2, r = Math.min(cx, cy) - 4;
    ctx.clearRect(0, 0, g.w, g.h);
    var total = 0;
    slices.forEach(function (s) { total += s.n; });
    if (total <= 0) {
      ctx.strokeStyle = 'rgba(151,159,236,0.3)';
      ctx.beginPath(); ctx.arc(cx, cy, r, 0, Math.PI * 2); ctx.stroke();
      return;
    }
    var a = -Math.PI / 2;
    slices.forEach(function (s) {
      var da = (s.n / total) * Math.PI * 2;
      ctx.beginPath();
      ctx.moveTo(cx, cy);
      ctx.arc(cx, cy, r, a, a + da);
      ctx.closePath();
      ctx.fillStyle = s.color;
      ctx.fill();
      a += da;
    });
  }

  function drawDonut(canvas, pct, color) {
    var g = prepCanvas(canvas, canvas.clientWidth, 88);
    if (!g) return;
    var ctx = g.ctx, cx = g.w / 2, cy = g.h / 2, r = Math.min(cx, cy) - 6;
    var p = clamp(pct, 0, 100) / 100;
    ctx.clearRect(0, 0, g.w, g.h);
    ctx.strokeStyle = 'rgba(151,159,236,0.16)';
    ctx.lineWidth = 10;
    ctx.beginPath(); ctx.arc(cx, cy, r, 0, Math.PI * 2); ctx.stroke();
    ctx.strokeStyle = color || '#979fec';
    ctx.lineCap = 'round';
    ctx.beginPath();
    ctx.arc(cx, cy, r, -Math.PI / 2, -Math.PI / 2 + p * Math.PI * 2);
    ctx.stroke();
    ctx.fillStyle = '#e4e6fb';
    ctx.font = '12px JetBrains Mono, monospace';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(Math.round(clamp(pct, 0, 100)) + '%', cx, cy);
  }

  function drawConstellation(canvas, t) {
    if (global.MovieFUI && typeof global.MovieFUI.drawConstellation === 'function') {
      try { global.MovieFUI.drawConstellation(canvas, { t: t }); return; } catch (e) {}
    }
    var g = prepCanvas(canvas, canvas.clientWidth, 78);
    if (!g) return;
    var ctx = g.ctx, w = g.w, h = g.h;
    ctx.clearRect(0, 0, w, h);
    var nodes = [];
    var seed = 11;
    for (var i = 0; i < 10; i++) {
      seed = (seed * 1103515245 + 12345) & 0x7fffffff;
      nodes.push({
        x: 8 + (seed % Math.max(1, w - 16)),
        y: 8 + ((seed >> 8) % Math.max(1, h - 16)) + Math.sin(t + i) * 2
      });
    }
    ctx.strokeStyle = 'rgba(151,159,236,0.4)';
    ctx.lineWidth = 1;
    for (var a = 0; a < nodes.length; a++) {
      for (var b = a + 1; b < nodes.length; b++) {
        var dx = nodes[a].x - nodes[b].x, dy = nodes[a].y - nodes[b].y;
        if (dx * dx + dy * dy < 2800) {
          ctx.beginPath();
          ctx.moveTo(nodes[a].x, nodes[a].y);
          ctx.lineTo(nodes[b].x, nodes[b].y);
          ctx.stroke();
        }
      }
    }
    nodes.forEach(function (n, idx) {
      ctx.fillStyle = idx % 2 ? '#d9b6fd' : '#979fec';
      ctx.beginPath(); ctx.arc(n.x, n.y, 2, 0, Math.PI * 2); ctx.fill();
    });
  }

  /* ── Dashboard DOM ──────────────────────────────────────────────── */
  function widget(title, bodyHtml) {
    return '<article class="vs-w"><div class="vs-wk">' + title + '</div>' + bodyHtml + '</article>';
  }

  function ensureDash() {
    if ($('vs-hud-dash')) return;
    var host = document.createElement('section');
    host.className = 'vs-hud-dash mf-mod';
    host.id = 'vs-hud-dash';
    host.setAttribute('data-vs-hud-dash', '1');
    var hero = document.querySelector('.vs-hero');
    var wrap = document.querySelector('.vs-wrap');
    if (hero && hero.parentNode) hero.parentNode.insertBefore(host, hero.nextSibling);
    else if (wrap) wrap.insertBefore(host, wrap.firstChild);
    else if (document.body) document.body.insertBefore(host, document.body.firstChild);
    fillDashSkeleton(host);
  }

  function fillDashSkeleton(host) {
    host = host || $('vs-hud-dash');
    if (!host) return;
    if (host.getAttribute('data-vs-hud-built') === '1') return;
    host.setAttribute('data-vs-hud-built', '1');
    host.innerHTML =
      '<div class="mf-mod-h">MODULE · FOXHOUND V3 · GPU / QUEUE / STEPS<span class="vs-mod-live">LIVE</span></div>' +
      '<div class="vs-hud-dash-grid">' +
        '<aside class="vs-hud-rail" id="vs-hud-rail-l"></aside>' +
        '<div class="vs-hud-stage">' +
          '<div class="vs-tr-rings">' +
            '<div class="vs-tr"><canvas id="vs-ring-gpu" width="132" height="132"></canvas><div class="vs-tr-val" id="vs-ring-gpu-val">—</div><div class="vs-tr-lab">VRAM USED</div><div class="vs-tr-why">Household GPU memory in use. Climbs while a render holds VRAM.</div></div>' +
            '<div class="vs-tr hero"><canvas id="vs-ring-queue" width="176" height="176"></canvas><div class="vs-tr-val" id="vs-ring-queue-val">—</div><div class="vs-tr-lab">QUEUE DEPTH</div><div class="vs-tr-why">Live jobs waiting or running. One active job fills half the ring.</div></div>' +
            '<div class="vs-tr"><canvas id="vs-ring-steps" width="132" height="132"></canvas><div class="vs-tr-val" id="vs-ring-steps-val">—</div><div class="vs-tr-lab" id="vs-ring-steps-lab">JOB PROGRESS</div><div class="vs-tr-why" id="vs-ring-steps-why">Elapsed vs typical finish time for the active job. Idle = empty.</div></div>' +
          '</div>' +
          '<div class="vs-jobclock" id="vs-hud-jobclock">' +
            '<div class="vs-jobclock-idle" id="vs-hud-job-idle">NO ACTIVE JOB · elapsed and T-minus appear here when something is queued or running</div>' +
            '<div class="vs-codec-readout vs-jobclock-live" id="vs-hud-job-live" hidden>' +
              '<span class="vs-codec-dot"></span>' +
              '<span class="vs-codec-status" id="vs-hud-job-status">STANDBY</span>' +
              '<span class="vs-codec-seg"><span class="vs-codec-label">Elapsed</span><span class="vs-codec-big" id="vs-hud-elapsed">0:00</span></span>' +
              '<span class="vs-codec-seg"><span class="vs-codec-label">T-Minus</span><span class="vs-codec-big" id="vs-hud-eta">--:--</span></span>' +
              '<span class="vs-codec-seg"><span class="vs-codec-label">Kind</span><span class="vs-codec-big" id="vs-hud-job-kind">—</span></span>' +
              '<span class="vs-codec-seg"><span class="vs-codec-label">Stage</span><span class="vs-codec-big" id="vs-hud-job-stage">—</span></span>' +
            '</div>' +
          '</div>' +
          '<canvas id="vs-hud-wave" class="vs-hud-wave" width="900" height="168" aria-hidden="true"></canvas>' +
          '<div class="vs-hud-dual">' +
            '<div><div class="vs-hud-pct" id="vs-hud-vram-pct">—</div><div class="vs-tr-why">GPU VRAM used</div></div>' +
            '<div><div class="vs-hud-pct" id="vs-hud-cpu-pct">—</div><div class="vs-tr-why">CPU load</div></div>' +
            '<div><div class="vs-hud-pct dim" id="vs-hud-q-pct">—</div><div class="vs-tr-why">Queue / T-minus</div></div>' +
          '</div>' +
          '<div class="vs-compute" id="vs-compute-path">VIDEO PATH · GPU check pending</div>' +
          '<div class="vs-hud-foot" id="vs-hud-foot">polling /video-studio/api/health + /video-studio/api/jobs</div>' +
        '</div>' +
        '<aside class="vs-hud-rail" id="vs-hud-rail-r"></aside>' +
      '</div>';
    var L = $('vs-hud-rail-l');
    var R = $('vs-hud-rail-r');
    if (L) {
      L.innerHTML =
        widget('GPU MEMORY', '<div class="vs-wv" id="vs-w-gpu-name">—</div><div class="vs-ws" id="vs-w-gpu-sub">Keep GPU gate</div><div class="vs-hud-bar"><i id="vs-w-vram-bar"></i></div><div class="vs-tr-why">Bar = memory in use on the household GPU.</div>') +
        '<div class="vs-stat-row">' +
          widget('FREE GB', '<div class="vs-wv" id="vs-w-free">—</div><div class="vs-tr-why">VRAM still free</div>') +
          widget('TOTAL GB', '<div class="vs-wv" id="vs-w-total">—</div><div class="vs-tr-why">VRAM installed</div>') +
        '</div>' +
        widget('QUEUE MIX', '<canvas id="vs-w-hbars" width="220" height="56"></canvas><div class="vs-ws" id="vs-w-qmix">running / pending / done</div>') +
        widget('VRAM SPARK', '<canvas id="vs-w-spark" width="220" height="42"></canvas>') +
        widget('JOB TYPES', '<canvas id="vs-w-pie" width="220" height="88"></canvas>') +
        widget('SIGNAL', '<div class="vs-eq"><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i></div>');
    }
    if (R) {
      R.innerHTML =
        widget('LAST 10 STATUSES', '<canvas id="vs-w-vbars" width="220" height="72"></canvas>') +
        widget('LOG TAIL', '<table class="vs-mini-table" id="vs-w-table"><tbody></tbody></table>') +
        widget('CORE / GUIDANCE / FPS', '<div class="vs-chip3"><b id="vs-w-turbo">—</b><b id="vs-w-cfg">—</b><b id="vs-w-fps">—</b></div><div class="vs-tr-why">Turbo on/off · guidance 1–8 · frames per second</div>') +
        widget('READY DONUT', '<canvas id="vs-w-donut" width="220" height="88"></canvas>') +
        widget('LINK MAP', '<canvas id="vs-w-map" width="220" height="78"></canvas>') +
        widget('PIPS', '<div class="vs-dots" id="vs-w-dots"></div>');
    }
  }

  function decorateModules() {
    var specs = [
      ['vs-actors-card', 'MODULE · ACTORS · CAST BANK'],
      ['vs-styles-card', 'MODULE · STYLES · LOOK DEV'],
      ['vs-new-entry-card', 'MODULE · NEW ENTRY · PROMPT DECK'],
      ['vs-tuning-rack', 'MODULE · TUNING RACK · PIPELINE KNOBS'],
      ['vs-queue-card', 'MODULE · QUEUE · WORKSHOP LOG']
    ];
    var styles = $('vs-styles-card');
    if (!styles) {
      document.querySelectorAll('.vs-card').forEach(function (card) {
        var h2 = card.querySelector('h2');
        if (h2 && /styles/i.test(h2.textContent || '') && !card.id) {
          card.id = 'vs-styles-card';
        }
      });
    }
    specs.forEach(function (s) {
      var el = $(s[0]);
      if (!el) return;
      el.classList.add('mf-mod', 'vs-card');
      if (!el.querySelector(':scope > .mf-mod-h')) {
        var h = document.createElement('div');
        h.className = 'mf-mod-h';
        h.innerHTML = s[1] + '<span class="vs-mod-live">LIVE</span>';
        el.insertBefore(h, el.firstChild);
      }
    });
    var actors = $('vs-actors-card');
    var st = $('vs-styles-card');
    if (actors && st && !actors.parentElement.classList.contains('vs-hud-cast')) {
      var row = document.createElement('div');
      row.className = 'vs-hud-cast';
      actors.parentNode.insertBefore(row, actors);
      row.appendChild(actors);
      row.appendChild(st);
    }
    var wrap = document.querySelector('.vs-wrap');
    if (wrap) wrap.classList.add('vs-hud-kit');
  }

  function ensureTuneHud() {
    var rack = $('vs-tuning-rack');
    if (!rack || $('vs-tune-hud')) return;
    var hud = document.createElement('div');
    hud.className = 'vs-tune-hud';
    hud.id = 'vs-tune-hud';
    hud.innerHTML =
      '<div class="vs-tune-rings">' +
        '<div class="vs-tune-mini"><canvas id="vs-tune-ring-steps" width="88" height="88"></canvas><span id="vs-tune-ring-steps-val">6</span></div>' +
      '</div>' +
      '<div class="vs-fader-bank" id="vs-fader-bank"></div>' +
      '<div class="vs-tune-rings">' +
        '<div class="vs-tune-mini"><canvas id="vs-tune-ring-cfg" width="88" height="88"></canvas><span id="vs-tune-ring-cfg-val">2</span></div>' +
      '</div>';
    var lede = rack.querySelector('.vs-tune-lede');
    if (lede && lede.nextSibling) rack.insertBefore(hud, lede.nextSibling);
    else rack.insertBefore(hud, rack.querySelector('.vs-tune-grid') || rack.firstChild.nextSibling);

    var bank = $('vs-fader-bank');
    if (!bank) return;
    var faders = [
      { id: 'vs-fader-steps', label: 'RENDER STEPS', src: 'vs-tune-steps', min: 4, max: 35, step: 1 },
      { id: 'vs-fader-cfg', label: 'CFG', src: 'vs-tune-cfg', min: 1, max: 8, step: 0.1 },
      { id: 'vs-fader-dur', label: 'DURATION', src: 'vs-tune-duration', min: 4, max: 10, step: 1 },
      { id: 'vs-fader-fps', label: 'FPS', src: 'vs-tune-fps', min: 8, max: 60, step: 1 }
    ];
    faders.forEach(function (f) {
      var row = document.createElement('div');
      row.className = 'vs-fader';
      row.innerHTML =
        '<label for="' + f.id + '">' + f.label + '</label>' +
        '<input type="range" id="' + f.id + '" min="' + f.min + '" max="' + f.max + '" step="' + f.step + '" value="0">' +
        '<span class="vs-fader-val" data-for="' + f.id + '">—</span>';
      bank.appendChild(row);
      var range = row.querySelector('input');
      var src = $(f.src);
      if (!range) return;
      function fromSrc() {
        if (!src) return;
        range.value = src.value || range.min;
        var lab = row.querySelector('.vs-fader-val');
        if (lab) lab.textContent = range.value;
      }
      range.addEventListener('input', function () {
        if (src) {
          src.value = range.value;
          src.dataset.userTouched = '1';
          src.dispatchEvent(new Event('input', { bubbles: true }));
          src.dispatchEvent(new Event('change', { bubbles: true }));
        }
        var lab = row.querySelector('.vs-fader-val');
        if (lab) lab.textContent = range.value;
        drawHudRings();
      });
      if (src) {
        src.addEventListener('input', fromSrc);
        src.addEventListener('change', fromSrc);
      }
      fromSrc();
    });
  }

  function syncFaders() {
    ['vs-fader-steps', 'vs-fader-cfg', 'vs-fader-dur', 'vs-fader-fps'].forEach(function (id) {
      var range = $(id);
      if (!range) return;
      var map = {
        'vs-fader-steps': 'vs-tune-steps',
        'vs-fader-cfg': 'vs-tune-cfg',
        'vs-fader-dur': 'vs-tune-duration',
        'vs-fader-fps': 'vs-tune-fps'
      };
      var src = $(map[id]);
      if (src && src.value !== '') range.value = src.value;
      var lab = document.querySelector('.vs-fader-val[data-for="' + id + '"]');
      if (lab && range) lab.textContent = range.value;
    });
  }

  function jobCounts(jobs) {
    var c = { running: 0, queued: 0, completed: 0, failed: 0, other: 0, types: {} };
    (jobs || []).forEach(function (j) {
      var st = (j.status || '').toLowerCase();
      if (st === 'running' || st === 'waiting_gpu') c.running += 1;
      else if (st === 'queued') c.queued += 1;
      else if (st === 'completed' || st === 'ready') c.completed += 1;
      else if (st === 'failed' || st === 'cancelled') c.failed += 1;
      else c.other += 1;
      var t = j.job_type || 'video';
      c.types[t] = (c.types[t] || 0) + 1;
    });
    return c;
  }

  function gpuPct(h) {
    if (!h) return 0;
    var tot = Number(h.vram_total_gb) || 0;
    var free = Number(h.vram_free_gb) || 0;
    if (tot <= 0) return (h.ready || h.cuda_available) ? 6 : 3;
    return clamp(((tot - free) / tot) * 100, 0, 100);
  }

  function queuePct(h, jobs) {
    var running = Number((h && h.queue_running) || 0);
    var pending = Number((h && h.queue_pending) || 0);
    var counts = jobCounts(jobs);
    var live = activeJobs(jobs).length;
    var depth = Math.max(running + pending, counts.running + counts.queued, live);
    return clamp(depth / 2 * 100, 0, 100);
  }

  function stepsPct() {
    var el = $('vs-tune-steps');
    var n = el ? Number(el.value) : 6;
    return clamp(n / 35 * 100, 0, 100);
  }

  function jobProgressPct() {
    var live = activeJobs(state.jobs);
    if (!live.length) return 0;
    var j = live[0];
    var elapsed = j.created_ts ? Math.max(0, Date.now() / 1000 - Number(j.created_ts)) : 0;
    var eta = etaFor(j);
    if (eta <= 0) return 8;
    return clamp((elapsed / eta) * 100, 2, 99);
  }

  function drawHudRings() {
    var h = state.health;
    var live = activeJobs(state.jobs);
    var busy = live.length > 0;
    var gp = gpuPct(h);
    var qp = queuePct(h, state.jobs);
    var jp = jobProgressPct();
    var dash = $('vs-hud-dash');
    if (dash) dash.classList.toggle('is-busy', busy);
    drawTripleRing($('vs-ring-gpu'), gp, busy ? '#e095b5' : '#979fec', false);
    drawTripleRing($('vs-ring-queue'), qp, busy ? '#d9b6fd' : '#a7c1e8', true);
    drawTripleRing($('vs-ring-steps'), jp, busy ? '#e095b5' : '#d9b6fd', false);
    setTxt('vs-ring-gpu-val', Math.round(gp) + '%');
    setTxt('vs-ring-queue-val', String(live.length || Math.round(qp / 50)));
    if (busy) {
      setTxt('vs-ring-steps-val', Math.round(jp) + '%');
      setTxt('vs-ring-steps-lab', 'JOB PROGRESS');
      setTxt('vs-ring-steps-why', 'Elapsed vs typical finish for the active job. Ring fills as the clock runs.');
    } else {
      setTxt('vs-ring-steps-val', 'IDLE');
      setTxt('vs-ring-steps-lab', 'JOB PROGRESS');
      setTxt('vs-ring-steps-why', 'Empty until a job is queued or running. Tuning knobs live in the rack below.');
    }
    var tunePct = stepsPct();
    var stepsEl = $('vs-tune-steps');
    drawTripleRing($('vs-tune-ring-steps'), tunePct, '#d9b6fd', false);
    setTxt('vs-tune-ring-steps-val', stepsEl ? stepsEl.value : '—');
    var cfgEl = $('vs-tune-cfg');
    var cfg = cfgEl ? Number(cfgEl.value) : 2;
    drawTripleRing($('vs-tune-ring-cfg'), clamp(cfg / 8 * 100, 0, 100), '#e095b5', false);
    setTxt('vs-tune-ring-cfg-val', cfgEl ? cfgEl.value : '—');
  }

  function setTxt(id, v) {
    var el = $(id);
    if (el) el.textContent = v == null || v === '' ? '—' : String(v);
  }

  function setBar(id, pct) {
    var el = $(id);
    if (el) el.style.width = clamp(pct, 0, 100) + '%';
  }

  function renderRails() {
    var h = state.health || {};
    var jobs = state.jobs || [];
    var counts = jobCounts(jobs);
    setTxt('vs-w-gpu-name', h.gpu_name || (h.ready ? 'GPU' : 'NO GPU'));
    setTxt('vs-w-gpu-sub', (h.ready ? 'READY' : 'NOT READY') +
      (h.queue_running != null ? (' · running ' + h.queue_running + ' / waiting ' + h.queue_pending) : ''));
    var used = 0;
    if (h.vram_total_gb) used = clamp(100 - (Number(h.vram_free_gb) / Number(h.vram_total_gb) * 100), 0, 100);
    setBar('vs-w-vram-bar', used);
    setTxt('vs-w-free', h.vram_free_gb != null ? h.vram_free_gb : '—');
    setTxt('vs-w-total', h.vram_total_gb != null ? h.vram_total_gb : '—');
    setTxt('vs-hud-vram-pct', Math.round(used) + '%');
    var cpu = state.telem && (state.telem.cpu_percent != null ? state.telem.cpu_percent : state.telem.cpu_pct);
    if (cpu == null && state.telem && state.telem.host_cpu_percent != null) cpu = state.telem.host_cpu_percent;
    setTxt('vs-hud-cpu-pct', cpu != null ? (Math.round(Number(cpu)) + '%') : '—');
    setTxt('vs-hud-q-pct', Math.round(queuePct(h, jobs)) + '%');
    tickJobClock();
    var live = activeJobs(jobs);
    var gpuOk = !!(h.ready || h.cuda_available);
    var pathEl = $('vs-compute-path');
    if (pathEl) {
      if (live.length && gpuOk) {
        pathEl.textContent = 'VIDEO PATH · GPU · ' + (h.gpu_name || 'CUDA') + ' · VRAM ' + Math.round(used) + '% · not CPU';
        pathEl.className = 'vs-compute is-gpu';
      } else if (live.length && !gpuOk) {
        pathEl.textContent = 'VIDEO PATH · GPU NOT READY · Foxhound V3 will not run on CPU';
        pathEl.className = 'vs-compute is-wait';
      } else if (gpuOk) {
        pathEl.textContent = 'VIDEO PATH · GPU READY · ' + (h.gpu_name || 'CUDA') + ' · idle';
        pathEl.className = 'vs-compute';
      } else {
        pathEl.textContent = 'VIDEO PATH · GPU NOT VISIBLE · will not fall back to CPU';
        pathEl.className = 'vs-compute is-wait';
      }
    }
    var foot = (h.gpu_name || 'GPU') + ' · VRAM ' + Math.round(used) + '% · CPU ' +
      (cpu != null ? Math.round(Number(cpu)) + '%' : '—') + ' · ' +
      (h.vram_free_gb != null ? h.vram_free_gb : '?') + '/' +
      (h.vram_total_gb != null ? h.vram_total_gb : '?') + ' GB · ' +
      live.length + ' live / ' + jobs.length + ' in Workshop log';
    if (live[0]) {
      var elapsed = live[0].created_ts ? Math.max(0, Date.now() / 1000 - Number(live[0].created_ts)) : 0;
      var remain = etaFor(live[0]) - elapsed;
      foot += ' · elapsed ' + fmtMMSS(elapsed) + ' · T-minus ' + (remain > 5 ? fmtMMSS(remain) : '--:--');
    }
    setTxt('vs-hud-foot', foot);

    var n = jobs.length || 1;
    drawHBars($('vs-w-hbars'), [
      { pct: counts.running / n * 100, color: '#979fec' },
      { pct: counts.queued / n * 100, color: '#d9b6fd' },
      { pct: counts.completed / n * 100, color: '#a7c1e8' },
      { pct: counts.failed / n * 100, color: '#e095b5' }
    ]);
    setTxt('vs-w-qmix', 'run ' + counts.running + ' · queue ' + counts.queued + ' · done ' + counts.completed + ' · fail ' + counts.failed);
    drawSpark($('vs-w-spark'), state.vramHist, '#979fec');

    var typeSlices = [];
    var palette = ['#979fec', '#d9b6fd', '#e095b5', '#648ed0', '#a7c1e8', '#cd9dcf'];
    var ti = 0;
    Object.keys(counts.types).forEach(function (k) {
      typeSlices.push({ n: counts.types[k], color: palette[ti % palette.length] });
      ti += 1;
    });
    drawPie($('vs-w-pie'), typeSlices);

    var last = jobs.slice(0, 10);
    var statusVal = last.map(function (j) {
      var st = (j.status || '').toLowerCase();
      if (st === 'completed' || st === 'ready') return 8;
      if (st === 'running') return 6;
      if (st === 'queued' || st === 'waiting_gpu') return 4;
      if (st === 'failed' || st === 'cancelled') return 2;
      return 3;
    });
    var statusCol = last.map(function (j) {
      var st = (j.status || '').toLowerCase();
      if (st === 'completed' || st === 'ready') return '#a7c1e8';
      if (st === 'running') return '#979fec';
      if (st === 'failed' || st === 'cancelled') return '#e095b5';
      return '#d9b6fd';
    });
    drawVBars($('vs-w-vbars'), statusVal.length ? statusVal : [1, 2, 3, 2, 4], statusCol);

    var tb = document.querySelector('#vs-w-table tbody');
    if (tb) {
      tb.innerHTML = last.slice(0, 5).map(function (j) {
        var st = (j.status || '—').replace(/</g, '');
        var p = (j.prompt || j.job_type || j.id || '').toString().replace(/</g, '').slice(0, 28);
        return '<tr><td>' + p + '</td><td>' + st + '</td></tr>';
      }).join('') || '<tr><td>no jobs</td><td>—</td></tr>';
    }

    setTxt('vs-w-turbo', (h.ready ? 'RDY' : 'WAIT'));
    var cfgEl = $('vs-tune-cfg');
    setTxt('vs-w-cfg', 'CFG ' + (cfgEl && cfgEl.value ? cfgEl.value : '2'));
    var fpsEl = $('vs-tune-fps');
    setTxt('vs-w-fps', (fpsEl && fpsEl.value ? fpsEl.value : '24') + ' FPS');
    drawDonut($('vs-w-donut'), gpuPct(h), activeJobs(jobs).length ? '#e095b5' : (h.ready ? '#a7c1e8' : '#e095b5'));
    drawConstellation($('vs-w-map'), (Date.now() - state.t0) / 1000);

    var dots = $('vs-w-dots');
    if (dots && !dots.childElementCount) {
      var html = '';
      for (var d = 0; d < 18; d++) html += '<i></i>';
      dots.innerHTML = html;
    }
    if (dots) {
      Array.prototype.forEach.call(dots.children, function (el, idx) {
        el.className = idx < counts.completed % 18 ? 'on' : (idx < (counts.failed % 18) ? 'warn' : '');
      });
    }
  }

  function pushHist(arr, v) {
    arr.push(clamp(v, 0, 100));
    if (arr.length > 48) arr.shift();
  }

  function tickWave() {
    var t = (Date.now() - state.t0) / 1000;
    drawWave($('vs-hud-wave'), state.vramHist, state.queueHist, t);
    state.waveRaf = requestAnimationFrame(tickWave);
  }

  function tickJobClock() {
    var live = activeJobs(state.jobs);
    var idle = $('vs-hud-job-idle');
    var box = $('vs-hud-job-live');
    var meta = $('vs-v2-progress-meta');
    if (!live.length) {
      if (idle) idle.hidden = false;
      if (box) box.hidden = true;
      return;
    }
    var j = live[0];
    var elapsed = j.created_ts ? Math.max(0, Date.now() / 1000 - Number(j.created_ts)) : 0;
    var eta = etaFor(j);
    var remain = eta - elapsed;
    var hot = remain <= 5;
    if (idle) idle.hidden = true;
    if (box) {
      box.hidden = false;
      box.classList.toggle('vs-codec-hot', hot);
    }
    setTxt('vs-hud-job-status', hot ? 'RUNNING LONG' : ((j.stage || j.status || 'RUNNING').toString().replace(/_/g, ' ')));
    setTxt('vs-hud-elapsed', fmtMMSS(elapsed));
    setTxt('vs-hud-eta', remain > 5 ? fmtMMSS(remain) : '--:--');
    setTxt('vs-hud-job-kind', jobKindLabel(j));
    setTxt('vs-hud-job-stage', (j.stage || j.status || 'working').toString().replace(/_/g, ' '));
    if (meta && !vsProgressOwned()) {
      meta.style.display = 'flex';
      meta.classList.toggle('vs-codec-hot', hot);
      meta.innerHTML =
        '<span class="vs-codec-dot"></span>' +
        '<span class="vs-codec-status">' + (hot ? 'RUNNING LONG — LINK STILL STABLE' : 'SIGNAL ACTIVE') + '</span>' +
        '<span class="vs-codec-seg"><span class="vs-codec-label">Elapsed</span><span class="vs-codec-big">' + fmtMMSS(elapsed) + '</span></span>' +
        '<span class="vs-codec-seg"><span class="vs-codec-label">T-Minus</span><span class="vs-codec-big">' + (remain > 5 ? fmtMMSS(remain) : '--:--') + '</span></span>';
    }
  }

  function vsProgressOwned() {
    return !!(global.vsProgressStartTs);
  }

  function pollHud() {
    var healthP = fetch('/video-studio/api/health', { cache: 'no-store', credentials: 'same-origin' })
      .then(function (r) { return r.json(); })
      .catch(function () { return null; });
    var jobsP = fetch('/video-studio/api/jobs', { cache: 'no-store', credentials: 'same-origin' })
      .then(function (r) { return r.json(); })
      .catch(function () { return []; });
    var telP = fetch('/api/executor/telemetry', { cache: 'no-store', credentials: 'same-origin' })
      .then(function (r) { return r.json(); })
      .catch(function () { return null; });
    Promise.all([healthP, jobsP, telP]).then(function (pair) {
      state.health = pair[0];
      state.jobs = Array.isArray(pair[1]) ? pair[1] : [];
      state.telem = pair[2] || state.telem;
      pushHist(state.vramHist, gpuPct(state.health));
      pushHist(state.queueHist, queuePct(state.health, state.jobs));
      drawHudRings();
      renderRails();
    });
  }

  var TUNE_LEDE = {
    video: 'Video knobs for this shot — aspect, duration, fps, steps, guidance. Generate reads these values.',
    image: 'Still-camera knobs — canvas size and seed. Otacons Image Generator Mk IV uses resolution + seed on generate.',
    music: 'Score knobs — duration, BPM, key, lyrics, format, guidance. Generate Music sends whatever is here.',
    project: 'Movie / story knobs — target runtime for the director. Scene lists open in a popup, not this rack.',
    write: 'Write mode is text only. GPU render knobs stay hidden until you switch to image, video, or music.',
    script: 'Script mode is text only. Open Scenes from a finished script card if you want the scene list.'
  };

  function ensureModeTuneGroups() {
    var grid = document.querySelector('#vs-tuning-rack .vs-tune-grid');
    if (!grid || $('vs-tune-mode-groups')) return;
    var extra = document.createElement('div');
    extra.id = 'vs-tune-mode-groups';
    extra.innerHTML =
      '<div class="vs-tune-group" data-tune="image" hidden>' +
        '<div class="vs-field"><label>Still canvas</label>' +
        '<p class="vs-why">Resolution lives in the slot above. Seed repeats a look. Otacons Image Generator Mk IV does not take video duration or fps.</p></div>' +
      '</div>' +
      '<div class="vs-tune-group" data-tune="music" id="vs-tune-music-group" hidden>' +
        '<div class="vs-tune-slot" id="vs-tune-slot-music-dur"></div>' +
        '<div class="vs-tune-slot" id="vs-tune-slot-music-bpm"></div>' +
        '<div class="vs-tune-slot" id="vs-tune-slot-music-key"></div>' +
        '<div class="vs-tune-slot" id="vs-tune-slot-music-sig"></div>' +
        '<div class="vs-tune-slot" id="vs-tune-slot-music-lang"></div>' +
        '<div class="vs-tune-slot" id="vs-tune-slot-music-cfg"></div>' +
        '<div class="vs-tune-slot" id="vs-tune-slot-music-format"></div>' +
        '<div class="vs-tune-slot" id="vs-tune-slot-music-seed"></div>' +
        '<div class="vs-tune-slot" id="vs-tune-slot-music-lyrics" style="grid-column:1/-1"></div>' +
      '</div>' +
      '<div class="vs-tune-group" data-tune="project" id="vs-tune-project-group" hidden>' +
        '<div class="vs-tune-slot" id="vs-tune-slot-runtime"></div>' +
        '<div class="vs-field"><label>Movie / story director</label>' +
        '<p class="vs-why">Target runtime is the advanced control for a project. Auto Plan and Import live in New Entry. Scenes open from the Scenes button, not inline.</p></div>' +
      '</div>' +
      '<div class="vs-tune-group" data-tune="write script" hidden>' +
        '<div class="vs-field"><label>No GPU knobs in this mode</label>' +
        '<p class="vs-why">Write and Script only send prompt + agent + style. Switch to Image, Video, Music, or Project to populate render controls.</p></div>' +
      '</div>';
    grid.appendChild(extra);
  }

  function markTuneAttrs() {
    var map = [
      ['vs-tune-slot-aspect', 'video'],
      ['vs-tune-slot-duration', 'video'],
      ['vs-tune-slot-fps', 'video'],
      ['vs-tune-slot-quality', 'video'],
      ['vs-tune-steps-field', 'video'],
      ['vs-tune-cfg-field', 'video'],
      ['vs-tune-slot-resolution', 'image'],
      ['vs-tune-slot-seed', 'video image']
    ];
    map.forEach(function (pair) {
      var el = $(pair[0]);
      if (el && !el.getAttribute('data-tune')) el.setAttribute('data-tune', pair[1]);
    });
    var turbo = $('vs-turbo-readout');
    if (turbo && !turbo.getAttribute('data-tune')) turbo.setAttribute('data-tune', 'video');
    var cfgNote = $('vs-tune-cfg-note');
    if (cfgNote && !cfgNote.getAttribute('data-tune')) cfgNote.setAttribute('data-tune', 'video');
    var hud = $('vs-tune-hud');
    if (hud && !hud.getAttribute('data-tune')) hud.setAttribute('data-tune', 'video');
  }

  function rehomeMusicKnobs(on) {
    var slots = {
      'vs-music-adv-duration': 'vs-tune-slot-music-dur',
      'vs-music-adv-bpm': 'vs-tune-slot-music-bpm',
      'vs-music-adv-key': 'vs-tune-slot-music-key',
      'vs-music-adv-timesig': 'vs-tune-slot-music-sig',
      'vs-music-adv-lang': 'vs-tune-slot-music-lang',
      'vs-music-adv-cfg': 'vs-tune-slot-music-cfg',
      'vs-music-adv-format': 'vs-tune-slot-music-format',
      'vs-music-adv-seed': 'vs-tune-slot-music-seed',
      'vs-music-adv-lyrics': 'vs-tune-slot-music-lyrics'
    };
    var panel = document.querySelector('#vs-music-panel [data-panel="advanced"]');
    Object.keys(slots).forEach(function (srcId) {
      var src = $(srcId);
      if (!src) return;
      var field = src.closest('.vs-field') || src;
      if (on) {
        var slot = $(slots[srcId]);
        if (slot && !slot.contains(field)) slot.appendChild(field);
      } else if (panel && !panel.contains(field)) {
        panel.appendChild(field);
      }
    });
  }

  function applyModeTuning(mode) {
    mode = mode || currentMode();
    state.mode = mode;
    var rack = $('vs-tuning-rack');
    if (!rack) return;
    rack.setAttribute('data-mode', mode);
    ensureModeTuneGroups();
    markTuneAttrs();
    var lede = rack.querySelector('.vs-tune-lede');
    if (lede) lede.textContent = TUNE_LEDE[mode] || TUNE_LEDE.video;
    var h2 = rack.querySelector('h2');
    if (h2) {
      h2.textContent = ({
        video: 'Video tuning',
        image: 'Picture tuning',
        music: 'Music tuning',
        project: 'Movie / project tuning',
        write: 'Write — no render knobs',
        script: 'Script — no render knobs'
      })[mode] || 'Tuning Parameters';
    }
    rack.querySelectorAll('[data-tune]').forEach(function (el) {
      var modes = (el.getAttribute('data-tune') || '').split(/\s+/);
      var show = modes.indexOf(mode) >= 0 || modes.indexOf('all') >= 0;
      if (el.hasAttribute('hidden') || el.getAttribute('data-tune')) {
        el.hidden = !show;
        el.style.display = show ? '' : 'none';
      }
    });
    // 2026-09-11 fix: music's advanced knobs (lyrics, BPM, key, etc.) used to
    // get reparented into the Tuning Rack card, which the 2026-09-09 card-deck
    // change turned into a click-to-open popup module -- so those fields
    // became unreachable (no visible path to them) and the Simple/Advanced
    // tab buttons were being force-hidden on top of that. Keep them in their
    // own always-in-flow panel with the original Simple/Advanced tab toggle
    // instead of relying on the now-hidden-by-default Tuning module.
    rehomeMusicKnobs(false);
    if (mode === 'image') rehomeField('vs-resolution', 'vs-tune-slot-resolution');
    if (mode === 'project') rehomeField('vs-duration-select', 'vs-tune-slot-runtime');
    var simpleDur = document.getElementById('vs-music-simple-duration');
    if (simpleDur && simpleDur.closest('.vs-row')) {
      simpleDur.closest('.vs-row').style.display = mode === 'music' ? 'none' : '';
    }
    document.querySelectorAll('.vs-fader').forEach(function (row) {
      var src = row.getAttribute('data-tune') || 'video';
      row.style.display = src.split(/\s+/).indexOf(mode) >= 0 ? '' : 'none';
    });
    var scenesBtn = $('vs-open-scenes-btn');
    if (scenesBtn) scenesBtn.style.display = (mode === 'video' || mode === 'project' || mode === 'script') ? '' : 'none';
    var simpleRow = $('vs-simple-scene-row');
    if (simpleRow) simpleRow.style.display = 'none';
  }

  function ensureScenesOverlay() {
    if ($('vs-scenes-overlay')) return;
    var el = document.createElement('div');
    el.id = 'vs-scenes-overlay';
    el.className = 'vs-scenes-overlay';
    el.hidden = true;
    el.innerHTML =
      '<div class="vs-scenes-card vs-card" role="dialog" aria-modal="true" aria-labelledby="vs-scenes-title">' +
        '<div class="vs-scenes-h">' +
          '<span id="vs-scenes-title">SCENES</span>' +
          '<button type="button" class="vs-scenes-x" id="vs-scenes-close" aria-label="Close">×</button>' +
        '</div>' +
        '<div class="vs-scenes-body" id="vs-scenes-body"></div>' +
      '</div>';
    document.body.appendChild(el);
    el.addEventListener('click', function (e) {
      if (e.target === el) closeScenes();
    });
    var x = $('vs-scenes-close');
    if (x) x.addEventListener('click', closeScenes);
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && !el.hidden) closeScenes();
    });
  }

  var scenesHome = null;

  function openScenes(html, title, homeEl) {
    ensureScenesOverlay();
    playClick();
    var overlay = $('vs-scenes-overlay');
    var body = $('vs-scenes-body');
    var t = $('vs-scenes-title');
    if (t) t.textContent = title || 'SCENES';
    if (homeEl) {
      scenesHome = { el: homeEl, parent: homeEl.parentNode, next: homeEl.nextSibling };
      body.innerHTML = '';
      body.appendChild(homeEl);
      homeEl.style.display = '';
    } else if (html != null) {
      scenesHome = null;
      body.innerHTML = html;
    }
    overlay.hidden = false;
    overlay.classList.add('is-open');
  }

  function closeScenes() {
    var overlay = $('vs-scenes-overlay');
    if (!overlay) return;
    overlay.hidden = true;
    overlay.classList.remove('is-open');
    if (scenesHome && scenesHome.el && scenesHome.parent) {
      if (scenesHome.next) scenesHome.parent.insertBefore(scenesHome.el, scenesHome.next);
      else scenesHome.parent.appendChild(scenesHome.el);
      scenesHome.el.style.display = 'none';
    }
    scenesHome = null;
  }

  function openSimpleScenes() {
    var row = $('vs-simple-scene-row');
    var box = $('vs-simple-scene-box');
    var tog = $('vs-simple-scene-toggle');
    if (tog) tog.checked = true;
    if (box) box.style.display = '';
    if (row) openScenes(null, 'SCENE DESK', row);
    else openScenes('<p class="vs-why">No scene desk in this mode.</p>', 'SCENES');
  }

  function wireScenesChrome() {
    ensureScenesOverlay();
    var host = document.querySelector('#vs-new-entry-card .vs-mode-toggle') || $('vs-optimal-prompts-row');
    if (host && !$('vs-open-scenes-btn')) {
      var btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'vs-submit vs-submit-sm';
      btn.id = 'vs-open-scenes-btn';
      btn.textContent = 'Scenes';
      btn.addEventListener('click', function () {
        var mode = currentMode();
        if (mode === 'video') openSimpleScenes();
        else if (mode === 'project') {
          var panel = document.querySelector('[id^="vs-project-tabs-"] [data-panel="scenes"]');
          if (panel) openScenes(panel.innerHTML, 'PROJECT SCENES');
          else openScenes('<p class="vs-why">Queue or open a project first — scenes appear here instead of inline.</p>', 'PROJECT SCENES');
        } else if (mode === 'script') {
          openScenes('<p class="vs-why">Open Scenes from a script card in the Workshop log. The list stays in a popup, not on the card.</p>', 'SCRIPT SCENES');
        }
      });
      host.appendChild(btn);
    }
    document.addEventListener('click', function (e) {
      var b = e.target.closest && e.target.closest('.vs-open-job-scenes');
      if (!b) return;
      e.preventDefault();
      var src = document.getElementById(b.getAttribute('data-src') || '');
      openScenes(src ? src.innerHTML : '<p class="vs-why">No scenes on this job.</p>', b.getAttribute('data-title') || 'SCENES');
    });
  }

  function wrapGlobal(name, after) {
    var orig = global[name];
    if (typeof orig !== 'function' || orig._vsHudWrapped) return;
    var wrapped = function () {
      var r = orig.apply(this, arguments);
      try { after.apply(this, arguments); } catch (e) {}
      return r;
    };
    wrapped._vsHudWrapped = true;
    global[name] = wrapped;
  }

  function wireModeAndWatchers() {
    wrapGlobal('vsApplyMode', function () {
      var prog = $('vs-v2-progress');
      if (prog && (global.vsActiveJobId || activeJobs(state.jobs).length)) {
        prog.style.display = '';
      }
      applyModeTuning(currentMode());
    });
    var origTab = global.vsSwitchProjectTab;
    if (typeof origTab === 'function' && !origTab._vsHudScenes) {
      global.vsSwitchProjectTab = function (containerId, tab) {
        if (tab === 'scenes') {
          var container = document.getElementById(containerId);
          var panel = container && container.querySelector('[data-panel="scenes"]');
          if (container) {
            container.querySelectorAll('.vs-ptab').forEach(function (b) {
              b.classList.toggle('active', b.dataset.tab === tab);
            });
            container.querySelectorAll('.vs-ptab-panel').forEach(function (p) { p.style.display = 'none'; });
          }
          openScenes(panel ? panel.innerHTML : '<p class="vs-why">No scenes yet.</p>', 'PROJECT SCENES');
          return;
        }
        return origTab.apply(this, arguments);
      };
      global.vsSwitchProjectTab._vsHudScenes = true;
    }
    var origMusic = global.vsGenerateMusic;
    if (typeof origMusic === 'function' && !origMusic._vsHudMusic) {
      global.vsGenerateMusic = function () {
        var desc = $('vs-music-simple-desc');
        var tags = $('vs-music-adv-tags');
        if (desc && tags && !tags.value.trim() && desc.value.trim()) tags.value = desc.value.trim();
        var dS = $('vs-music-simple-duration');
        var dA = $('vs-music-adv-duration');
        if (dS && dA && dS.value) dA.value = dS.value;
        return origMusic.call(this, true);
      };
      global.vsGenerateMusic._vsHudMusic = true;
    }
    applyModeTuning(currentMode());
    document.querySelectorAll('.vs-mode-btn').forEach(function (btn) {
      btn.addEventListener('click', function () {
        setTimeout(function () { applyModeTuning(currentMode()); }, 0);
      });
    });
  }

  function boot() {
    ensureLoader();
    buildRackIfMissing();
    rehomeKnownFields();
    markTouched('vs-tune-steps');
    markTouched('vs-tune-cfg');
    markTouched('vs-vid-aspect');
    wireHowTo();
    mountTelem();
    decorateModules();
    ensureDash();
    fillDashSkeleton();
    ensureTuneHud();
    ensureModeTuneGroups();
    markTuneAttrs();
    wireScenesChrome();
    wireModeAndWatchers();
    fetchDefaults().then(applyDefaults);
    pollHud();
    setInterval(pollHud, 4000);
    if (!state.clockTimer) state.clockTimer = setInterval(function () {
      tickJobClock();
      if (activeJobs(state.jobs).length) drawHudRings();
    }, 1000);
    if (!state.waveRaf) tickWave();
    ['vs-tune-steps', 'vs-tune-cfg', 'vs-tune-duration', 'vs-tune-fps'].forEach(function (id) {
      var el = $(id);
      if (!el) return;
      el.addEventListener('input', function () { syncFaders(); drawHudRings(); });
      el.addEventListener('change', function () { syncFaders(); drawHudRings(); });
    });
    if (global.MovieFUI && typeof global.MovieFUI.boot === 'function') {
      try { global.MovieFUI.boot(document); } catch (e) {}
    }
    try {
      if (localStorage.getItem('vsActiveVideoJob') || sessionStorage.getItem('vsFocusHud')) {
        var dash = $('vs-hud-dash') || document.querySelector('.vs-hero');
        window.scrollTo({ top: 0, behavior: 'smooth' });
        if (dash && dash.scrollIntoView) dash.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    } catch (e) {}
  }

  global.vsAppendTuning = vsAppendTuning;
  global.vsOpenScenesOverlay = openScenes;
  global.vsCloseScenesOverlay = closeScenes;
  global.VideoStudioHUD = {
    boot: boot,
    appendTuning: vsAppendTuning,
    applyDefaults: applyDefaults,
    applyMode: applyModeTuning,
    poll: pollHud,
    openScenes: openScenes,
    closeScenes: closeScenes
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})(window);


/* ── HUD 8 · 2026-09-09 card deck → module popups ───────────────── */
(function (global) {
  'use strict';
  var HUD = global.VideoStudioHUD || (global.VideoStudioHUD = {});
  var MODULES = [
    { id: 'actors', sel: '#vs-actors-card', title: 'ACTORS', k: '01 · CAST', sub: 'Faces + reference art for every shot', statId: 'vs-deck-stat-actors', statLabel: 'Cast' },
    { id: 'styles', sel: '#vs-styles-card', title: 'STYLES', k: '02 · LOOK', sub: 'Reusable lighting / grain / palette locks', statId: 'vs-deck-stat-styles', statLabel: 'Looks' },
    { id: 'entry', sel: '#vs-new-entry-card', title: 'NEW ENTRY', k: '03 · PROMPT', sub: 'Write · Image · Video · Music · Project', statId: 'vs-deck-stat-entry', statLabel: 'Mode' },
    { id: 'tuning', sel: '#vs-tuning-rack', title: 'TUNING', k: '04 · RACK', sub: 'Resolution, steps, CFG, duration, FPS', statId: 'vs-deck-stat-tuning', statLabel: 'Steps' },
    { id: 'queue', sel: '#vs-queue-card', title: 'QUEUE', k: '05 · LOG', sub: 'Workshop jobs · GPU wait · outputs', statId: 'vs-deck-stat-queue', statLabel: 'Jobs' }
  ];
  var home = null;
  var openId = null;

  function $(id) { return document.getElementById(id); }
  function playClick() {
    try {
      if (global.OtaconSFX && typeof global.OtaconSFX.play === 'function') global.OtaconSFX.play('click');
    } catch (e) {}
  }

  function ensureOverlay() {
    if ($('vs-module-overlay')) return;
    var o = document.createElement('div');
    o.id = 'vs-module-overlay';
    o.className = 'vs-module-overlay';
    o.hidden = true;
    o.innerHTML =
      '<div class="vs-module-shell mf-mod" role="dialog" aria-modal="true" aria-labelledby="vs-module-title">' +
      '<div class="vs-module-h"><span id="vs-module-title">MODULE</span>' +
      '<button type="button" class="vs-module-x" id="vs-module-close" aria-label="Close">×</button></div>' +
      '<div class="vs-module-body" id="vs-module-body"></div></div>';
    document.body.appendChild(o);
    o.addEventListener('click', function (e) {
      if (e.target === o) closeModule();
    });
    $('vs-module-close').addEventListener('click', function () { closeModule(); });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && openId) closeModule();
    });
  }

  function restoreHome() {
    if (!home || !home.el || !home.parent) return;
    if (home.next && home.next.parentNode === home.parent) home.parent.insertBefore(home.el, home.next);
    else home.parent.appendChild(home.el);
    home = null;
  }

  function closeModule() {
    var o = $('vs-module-overlay');
    if (!o) return;
    o.classList.remove('is-open');
    o.hidden = true;
    restoreHome();
    openId = null;
    document.querySelectorAll('.vs-deck-tile.is-open').forEach(function (t) { t.classList.remove('is-open'); });
    playClick();
  }

  function openModule(id) {
    ensureOverlay();
    var meta = MODULES.filter(function (m) { return m.id === id; })[0];
    if (!meta) return;
    var el = document.querySelector(meta.sel);
    if (!el) return;
    playClick();
    if (openId && openId !== id) {
      restoreHome();
    }
    var body = $('vs-module-body');
    var title = $('vs-module-title');
    if (title) title.textContent = 'MODULE · ' + meta.title;
    if (home && home.el === el) {
      // already open
    } else {
      restoreHome();
      home = { el: el, parent: el.parentNode, next: el.nextSibling };
      body.innerHTML = '';
      body.appendChild(el);
    }
    openId = id;
    var o = $('vs-module-overlay');
    o.hidden = false;
    o.classList.add('is-open');
    document.querySelectorAll('.vs-deck-tile').forEach(function (t) {
      t.classList.toggle('is-open', t.getAttribute('data-vs-module') === id);
    });
    try { el.scrollTop = 0; } catch (e) {}
  }

  function buildDeck() {
    if ($('vs-card-deck')) return;
    var dash = $('vs-hud-dash');
    var host = document.createElement('section');
    host.id = 'vs-card-deck';
    host.className = 'vs-card-deck';
    host.setAttribute('data-vs-card-deck', '1');
    host.setAttribute('aria-label', 'Workshop module cards');
    var hint = document.createElement('div');
    hint.className = 'vs-deck-hint';
    hint.id = 'vs-deck-hint';
    hint.textContent = 'Click a card · module opens as Ghost Pastel popup · Esc / × closes';
    MODULES.forEach(function (m) {
      var btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'vs-deck-tile';
      btn.setAttribute('data-vs-module', m.id);
      btn.setAttribute('data-ot-sfx', 'click');
      btn.innerHTML =
        '<span class="vs-deck-k">' + m.k + '</span>' +
        '<span class="vs-deck-title">' + m.title + '</span>' +
        '<span class="vs-deck-sub">' + m.sub + '</span>' +
        '<span class="vs-deck-stat"><span>' + m.statLabel + '</span><b id="' + m.statId + '">—</b></span>';
      btn.addEventListener('click', function () { openModule(m.id); });
      host.appendChild(btn);
    });
    if (dash && dash.parentNode) {
      dash.parentNode.insertBefore(hint, dash.nextSibling);
      dash.parentNode.insertBefore(host, hint.nextSibling);
    } else {
      var wrap = document.querySelector('.vs-wrap');
      if (wrap) { wrap.appendChild(hint); wrap.appendChild(host); }
    }
  }

  function wireHowToPopups() {
    document.querySelectorAll('[data-vs-jump]').forEach(function (btn) {
      if (btn._vsDeckWired) return;
      btn._vsDeckWired = true;
      btn.addEventListener('click', function (e) {
        var sel = btn.getAttribute('data-vs-jump') || '';
        var map = {
          '#vs-actors-card': 'actors',
          '#vs-styles-card': 'styles',
          '#vs-new-entry-card': 'entry',
          '#vs-tuning-rack': 'tuning',
          '#vs-queue-card': 'queue'
        };
        var id = map[sel];
        if (!id) return;
        e.preventDefault();
        e.stopPropagation();
        openModule(id);
      }, true);
    });
  }

  function countKids(sel, childSel) {
    var root = document.querySelector(sel);
    if (!root) return 0;
    return root.querySelectorAll(childSel).length;
  }

  function refreshDeckStats() {
    var a = countKids('#vs-actors', '.vs-actor-card');
    var s = countKids('#vs-styles', '.vs-style-card');
    var jobs = countKids('#vs-jobs', '.vs-job');
    var modeBtn = document.querySelector('.vs-mode-btn.active');
    var mode = modeBtn ? (modeBtn.getAttribute('data-mode') || modeBtn.textContent || '—') : '—';
    var steps = ($('vs-tune-steps') && $('vs-tune-steps').value) || 'auto';
    var elA = $('vs-deck-stat-actors'); if (elA) elA.textContent = String(a);
    var elS = $('vs-deck-stat-styles'); if (elS) elS.textContent = String(s);
    var elE = $('vs-deck-stat-entry'); if (elE) elE.textContent = String(mode).toUpperCase();
    var elT = $('vs-deck-stat-tuning'); if (elT) elT.textContent = String(steps);
    var elQ = $('vs-deck-stat-queue'); if (elQ) elQ.textContent = String(jobs);
  }

  function enableDeckMode() {
    document.documentElement.classList.add('vs-deck-mode');
    ensureOverlay();
    buildDeck();
    wireHowToPopups();
    refreshDeckStats();
    setInterval(refreshDeckStats, 2000);
  }

  function bootDeck() {
    try { enableDeckMode(); } catch (e) { console.warn('vs deck', e); }
  }

  HUD.openModule = openModule;
  HUD.closeModule = closeModule;
  HUD.refreshDeckStats = refreshDeckStats;

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', bootDeck);
  else bootDeck();
  // Re-run after original HUD boot paints dash
  setTimeout(bootDeck, 50);
  setTimeout(bootDeck, 400);
})(window);
