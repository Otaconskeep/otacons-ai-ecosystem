/* Movie FUI kit — radar rings, constellation, glow button helpers */
(function (global) {
  'use strict';

  function clamp(n, a, b) { return Math.max(a, Math.min(b, n)); }

  function drawRadar(canvas, opts) {
    if (!canvas) return;
    var dpr = window.devicePixelRatio || 1;
    var size = canvas.clientWidth || 120;
    canvas.width = size * dpr;
    canvas.height = size * dpr;
    var ctx = canvas.getContext('2d');
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    var cx = size / 2, cy = size / 2, r = size * 0.46;
    var t = (opts && opts.t) || 0;
    var accent = (opts && opts.accent) || '#979fec';
    var mag = (opts && opts.magenta) || '#cd9dcf';

    ctx.clearRect(0, 0, size, size);
    ctx.strokeStyle = accent;
    ctx.fillStyle = 'rgba(151,159,236,0.06)';
    ctx.beginPath();
    ctx.arc(cx, cy, r, 0, Math.PI * 2);
    ctx.fill();
    ctx.lineWidth = 1.2;
    ctx.stroke();

    for (var i = 1; i <= 4; i++) {
      ctx.beginPath();
      ctx.arc(cx, cy, r * (i / 4), 0, Math.PI * 2);
      ctx.globalAlpha = 0.25 + i * 0.08;
      ctx.stroke();
    }
    ctx.globalAlpha = 1;

    // crosshair
    ctx.beginPath();
    ctx.moveTo(cx - r, cy); ctx.lineTo(cx + r, cy);
    ctx.moveTo(cx, cy - r); ctx.lineTo(cx, cy + r);
    ctx.globalAlpha = 0.35;
    ctx.stroke();
    ctx.globalAlpha = 1;

    // sweep
    var ang = (t * 0.8) % (Math.PI * 2);
    var grad = ctx.createRadialGradient(cx, cy, 0, cx, cy, r);
    grad.addColorStop(0, 'rgba(151,159,236,0.0)');
    grad.addColorStop(1, 'rgba(151,159,236,0.38)');
    ctx.fillStyle = grad;
    ctx.beginPath();
    ctx.moveTo(cx, cy);
    ctx.arc(cx, cy, r, ang - 0.55, ang);
    ctx.closePath();
    ctx.fill();

    // blips
    for (var b = 0; b < 5; b++) {
      var ba = t * 0.3 + b * 1.3;
      var br = r * (0.25 + ((b * 37) % 60) / 100);
      var bx = cx + Math.cos(ba) * br;
      var by = cy + Math.sin(ba) * br;
      ctx.fillStyle = b % 2 ? mag : accent;
      ctx.shadowColor = ctx.fillStyle;
      ctx.shadowBlur = 8;
      ctx.beginPath();
      ctx.arc(bx, by, 2.2, 0, Math.PI * 2);
      ctx.fill();
      ctx.shadowBlur = 0;
    }

    // core
    ctx.fillStyle = mag;
    ctx.shadowColor = mag;
    ctx.shadowBlur = 12;
    ctx.beginPath();
    ctx.arc(cx, cy, 3.5, 0, Math.PI * 2);
    ctx.fill();
    ctx.shadowBlur = 0;
  }

  function drawConstellation(canvas, opts) {
    if (!canvas) return;
    var dpr = window.devicePixelRatio || 1;
    var w = canvas.clientWidth || 160;
    var h = canvas.clientHeight || 110;
    canvas.width = w * dpr;
    canvas.height = h * dpr;
    var ctx = canvas.getContext('2d');
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    var t = (opts && opts.t) || 0;
    var nodes = [];
    var seed = 7;
    for (var i = 0; i < 12; i++) {
      seed = (seed * 1103515245 + 12345) & 0x7fffffff;
      var nx = 12 + (seed % Math.max(1, w - 24));
      seed = (seed * 1103515245 + 12345) & 0x7fffffff;
      var ny = 10 + (seed % Math.max(1, h - 20));
      nodes.push({ x: nx, y: ny + Math.sin(t + i) * 2 });
    }
    ctx.clearRect(0, 0, w, h);
    ctx.strokeStyle = 'rgba(205,157,207,0.4)';
    ctx.lineWidth = 1;
    for (var a = 0; a < nodes.length; a++) {
      for (var b = a + 1; b < nodes.length; b++) {
        var dx = nodes[a].x - nodes[b].x;
        var dy = nodes[a].y - nodes[b].y;
        if (dx * dx + dy * dy < 3600) {
          ctx.beginPath();
          ctx.moveTo(nodes[a].x, nodes[a].y);
          ctx.lineTo(nodes[b].x, nodes[b].y);
          ctx.stroke();
        }
      }
    }
    nodes.forEach(function (n, idx) {
      ctx.fillStyle = idx % 3 === 0 ? '#979fec' : '#cd9dcf';
      ctx.shadowColor = ctx.fillStyle;
      ctx.shadowBlur = 8;
      ctx.beginPath();
      ctx.arc(n.x, n.y, idx === 0 ? 3.2 : 2, 0, Math.PI * 2);
      ctx.fill();
      ctx.shadowBlur = 0;
    });
  }


  var HEX_GREEBLE = [
    'A7 9F EC  D9 B6 FD  E0 95 B5  07 05 06',
    'C0 DE C0  50 219  50 220  50 221',
    '4F 54 41  43 4F 4E  4B 45 45 50',
    '50 56 45  37 30 35  30 2E 32 32 30'
  ];

  var KEEP_LOGO_FRAMES = [
    '      /\\\n     /██\\\n    /████\\\n    ██▓▓██\n    █ ■■ █\n    ██████\n  OTACONSKEEP',
    '     /\\_\n    /██ \\\n    █████\\\n    █▓▓███\n    █ ■ █\n    █████\n  OTACONSKEEP',
    '      /|\n     /█|\n     ███|\n     █▓█|\n     █■█|\n     ███|\n     KEEP',
    '      ||\n      ██\n      ██\n      ■■\n      ██\n      ██\n     KEEP',
    '     |\\\n     |█\\\n     |███\\\n     |█▓█\n     |█■█\n     |███\n     KEEP',
    '     _/\\\n    / ██\\\n   /█████\n   ███▓▓█\n    █ ■ █\n    █████\n  OTACONSKEEP',
    '      /\\\n     /██\\\n    /████\\\n    ██  ██\n    █ ■■ █\n    ██████\n  KEEPOTACON',
    '     /\\\n    /██\\\n   /████\\\n   ██▓▓██\n   █ ■■ █\n   ██████\n  OTACONSKEEP'
  ];

  var COMPILE_LINES = [
    'cc -c keep_boot.c -O2 -o keep_boot.o',
    'as -o cluster_iff.o cluster_iff.S',
    'ld -T otaconskeep.ld *.o -o keep.elf',
    'strip --strip-unneeded keep.elf',
    'objcopy -O binary keep.elf keep.img',
    'clang -emit-llvm codec_uplink.c -o uplink.bc',
    'nasm -f elf64 section9.asm -o section9.o',
    'make -j8 SURFACE=ghost-pastel',
    '[ 18%] Building CXX object hud/boot.cpp.o',
    '[ 27%] Building CXX object hud/chamfer.cpp.o',
    '[ 41%] Building CXX object iff/mesh.cpp.o',
    '[ 58%] Linking CXX executable otaconskeep',
    '[ 66%] Generating ghost_pastel.inc',
    '[ 79%] Built target cluster_iff',
    '[ 91%] Built target foxhound_v3',
    '[100%] SURFACE ONLINE',
    'OK  otaconskeep.elf    entry 0xC0DEC0DE',
    'IFF  .219 OtaconsKeep   UP',
    'IFF  .220 OptiPlex      UP',
    'IFF  .221 docker-offload UP',
    'mount /opt/otacon/otacon-executor  ok',
    'tokens  void=#070506  lav=#979fec',
    'arm fui  corner-brackets / chamfers',
    'codec link  SECTION-9 uplink  stable',
    'greeble  scan-sweep · ticker · pips',
    'ld.lld keep.elf --gc-sections',
    'ranlib libghostpastel.a',
    'install -m 0755 keep.bin /boot/keep',
    'sysctl net.iff.mesh=otaconskeep',
    'echo LINK LIVE > /proc/otacon/state'
  ];

  var THEME_BOOT_BRAND = {
    war: 'OTACON // WAR ROOM',
    albedo: 'OTACON // ALBEDO LAIR',
    'ha-mantis': 'OTACON // PSYCHO MANTIS',
    office: 'OTACON // COMMAND CENTER',
    executor: 'OTACON // MONOLITH IDE',
    command: 'OTACON // COMMAND CLI',
    'video-studio': 'OTACON // VIDEO STUDIO',
    intel: 'OTACON // INTEL HUB',
    social: 'OTACON // SOCIAL',
    relationships: 'OTACON // RELATIONSHIPS',
    rex: 'OTACON // PROJECT REX',
    admin: 'OTACON // FIELD MANUAL',
    'page-builder': 'OTACON // PAGE BUILDER',
    lab: 'OTACON // GENOME',
    genome: 'OTACON // GENOME'
  };

  function escText(s) {
    return String(s || '').replace(/[&<>"']/g, function (c) {
      return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c];
    });
  }

  function bootBrand(opts) {
    opts = opts || {};
    var html = document.documentElement;
    var brand = (opts.brand || html.getAttribute('data-mf-loader-brand') || '').trim();
    if (brand) return brand.replace(/\s+/g, ' ');
    var theme = html.getAttribute('data-theme') || '';
    if (THEME_BOOT_BRAND[theme]) return THEME_BOOT_BRAND[theme];
    if (html.hasAttribute('data-keep-theme') || (document.body && document.body.classList.contains('theme-page'))) {
      return 'OTACON // GLOBAL THEME';
    }
    var title = (document.title || '')
      .replace(/^OTACON\s*[—–-]+\s*/i, '')
      .replace(/\s*[—–-]+\s*The Keep\s*$/i, '')
      .replace(/\s*\/\/.*$/, '')
      .trim();
    if (title) return 'OTACON // ' + title.toUpperCase();
    return 'OTACON COMMAND CENTER';
  }

  function bootTitle(brand) {
    var b = String(brand || 'OTACON COMMAND CENTER');
    if (!/^OTACON/i.test(b)) b = 'OTACON // ' + b;
    if (!/BOOT$/i.test(b)) b = b + ' · BOOT';
    return '◈ ' + b;
  }

  function bootFrames(brand) {
    var room = String(brand || 'COMMAND CENTER').replace(/^OTACON\s*\/\/\s*/i, '');
    return [
      'SYSCHK············ MOUNT /opt/otacon/otacon-executor\nOTACONSKEEP      .219  …… WAIT\nOPTIPLEX         .220  …… WAIT\nOFFLOAD docker    .221  …… WAIT',
      'SYSCHK············ TOKENS  void #070506\nOTACONSKEEP      .219  …… PING\nOPTIPLEX         .220  …… PING\nOFFLOAD docker    .221  …… PING',
      'ARM FUI·········· CORNER BRACKETS / CHAMFERS\nOTACONSKEEP      .219  · OtaconsKeep   UP\nOPTIPLEX         .220  · OptiPlex      …\nOFFLOAD docker    .221  · homepage      …',
      'CLUSTER IFF······ OTACONSKEEP + OPTIPLEX MESH\nOTACONSKEEP      .219  · OtaconsKeep   UP\nOPTIPLEX         .220  · OptiPlex      UP\nOFFLOAD docker    .221  · homepage      …',
      'CODEC LINK······· SECTION-9 UPLINK\nOTACONSKEEP      .219  · OtaconsKeep   UP\nOPTIPLEX         .220  · OptiPlex      UP\nOFFLOAD docker    .221  · homepage      UP',
      'HUD PRESET······· LAVENDER / LILAC / ROSE\nOTACONSKEEP      .219  · :8006 LIVE\nOPTIPLEX         .220  · :8006 LIVE\nOFFLOAD docker    .221  · :3003 LIVE',
      'GREEBLE·········· SCAN SWEEP · TICKER · PIPS\n┌ NODE1 .219 pve OtaconsKeep\n├ OPTIPLEX .220\n└ OFFLOAD .221 docker-offload',
      '◈ LINK LIVE · ENTERING ' + room + '\nCLUSTER ARMED · OtaconsKeep + OptiPlex + offload\nSFX GESTURE-GATED · MUTE TOGGLE READY\nSURFACE ONLINE'
    ];
  }

  function ensureLoader(opts) {
    opts = opts || {};
    var html = document.documentElement;
    if (html && html.hasAttribute('data-mf-skip-loader')) return null;

    var existingRun = document.getElementById('ot-boot');
    if (existingRun && existingRun.getAttribute('data-ot-boot-run') === '1') {
      document.querySelectorAll('#ot-boot, .mf-loader').forEach(function (n) {
        if (n !== existingRun && n.parentNode) n.parentNode.removeChild(n);
      });
      return existingRun;
    }

    var extras = document.querySelectorAll('#ot-boot, .mf-loader');
    var el = existingRun || extras[0] || null;
    for (var i = 0; i < extras.length; i++) {
      if (extras[i] !== el && extras[i].parentNode) extras[i].parentNode.removeChild(extras[i]);
    }

    var brand = bootBrand(opts);
    var title = bootTitle(brand);
    var created = false;
    if (!el) {
      el = document.createElement('div');
      created = true;
    }
    el.id = 'ot-boot';
    el.className = 'mf-loader';
    el.setAttribute('aria-busy', 'true');
    el.setAttribute('aria-live', 'polite');
    el.innerHTML =
      '<div class="ot-boot-deck ot-boot-deck-t"><div class="ot-boot-deck-h">SYS // COMPILE · PIPELINE</div><pre class="ot-boot-deck-body" id="ot-boot-deck-t"></pre></div>' +
      '<div class="ot-boot-deck ot-boot-deck-l"><div class="ot-boot-deck-h">SYS // CC1 · FOXHOUND</div><pre class="ot-boot-deck-body" id="ot-boot-deck-l"></pre></div>' +
      '<div class="ot-boot-deck ot-boot-deck-r"><div class="ot-boot-deck-h">SYS // LD · CLUSTER IFF</div><pre class="ot-boot-deck-body" id="ot-boot-deck-r"></pre></div>' +
      '<div class="ot-boot-deck ot-boot-deck-b"><div class="ot-boot-deck-h">SYS // LINK · OTACONSKEEP</div><pre class="ot-boot-deck-body" id="ot-boot-deck-b"></pre></div>' +
      '<div class="ot-boot-center">' +
      '<div class="ot-boot-logo-wrap">' +
      '<div class="ot-boot-logo-ring" aria-hidden="true"></div>' +
      '<div class="ot-boot-logo-ring-2" aria-hidden="true"></div>' +
      '<pre class="ot-boot-logo" id="ot-boot-logo">' + KEEP_LOGO_FRAMES[0] + '</pre>' +
      '<div class="ot-boot-logo-tag">OTACONSKEEP · PVE · .219</div>' +
      '</div>' +
      '<div class="ot-boot-frame">' +
      '<div class="ot-boot-kicker">SECTION-9 · GHOST PASTEL · CLUSTER IFF</div>' +
      '<div class="ot-boot-title">' + escText(title) + '</div>' +
      '<div class="ot-boot-bar"><div class="ot-boot-fill" id="ot-boot-fill"></div></div>' +
      '<div class="ot-boot-ascii" id="ot-boot-ascii">INITIALIZING GHOST PASTEL HUD…</div>' +
      '<div class="ot-boot-hex" id="ot-boot-hex">' + HEX_GREEBLE[0] + '</div>' +
      '</div></div>';

    if (created) {
      var host = document.body || document.documentElement;
      if (host) host.appendChild(el);
      else {
        document.addEventListener('DOMContentLoaded', function () {
          if (!document.getElementById('ot-boot')) (document.body || document.documentElement).appendChild(el);
        });
      }
    }

    el.setAttribute('data-ot-boot-run', '1');

    var fill = el.querySelector('#ot-boot-fill');
    var ascii = el.querySelector('#ot-boot-ascii');
    var hex = el.querySelector('#ot-boot-hex');
    var logo = el.querySelector('#ot-boot-logo');
    var deckL = el.querySelector('#ot-boot-deck-l');
    var deckR = el.querySelector('#ot-boot-deck-r');
    var deckT = el.querySelector('#ot-boot-deck-t');
    var deckB = el.querySelector('#ot-boot-deck-b');
    var frames = bootFrames(brand);
    var reduce = false;
    try { reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches; } catch (e1) {}
    var p = 0;
    var fi = 0;
    var logoI = 0;
    var bufL = [];
    var bufR = [];
    var tickMs = reduce ? 40 : 90;
    function pushCompile(buf, node, max, offset) {
      var line = COMPILE_LINES[(Math.floor(Date.now() / 70) + offset) % COMPILE_LINES.length];
      if (Math.random() < 0.22) line = line + '  0x' + (Date.now() & 0xffff).toString(16).toUpperCase();
      buf.push(line);
      if (buf.length > max) buf.shift();
      if (node) node.textContent = buf.join('\n');
    }
    var compileTick = setInterval(function () {
      pushCompile(bufL, deckL, 16, 0);
      pushCompile(bufR, deckR, 16, 7);
      if (deckT) deckT.textContent = COMPILE_LINES[Math.floor(Date.now() / 120) % COMPILE_LINES.length];
      if (deckB) deckB.textContent = COMPILE_LINES[Math.floor(Date.now() / 160 + 4) % COMPILE_LINES.length];
    }, reduce ? 120 : 55);
    var logoTick = setInterval(function () {
      if (reduce) return;
      logoI = (logoI + 1) % KEEP_LOGO_FRAMES.length;
      if (logo) logo.textContent = KEEP_LOGO_FRAMES[logoI];
    }, 90);
    var tick = setInterval(function () {
      p += reduce ? 18 : (3 + Math.floor(Math.random() * 4));
      if (p > 100) p = 100;
      if (fill) fill.style.width = p + '%';
      var nextFi = Math.min(frames.length - 1, Math.floor(p / (100 / frames.length)));
      if (nextFi !== fi && ascii) {
        fi = nextFi;
        ascii.textContent = frames[fi];
      }
      if (hex) hex.textContent = HEX_GREEBLE[Math.floor(Date.now() / 180) % HEX_GREEBLE.length];
      if (p >= 100) {
        clearInterval(tick);
        clearInterval(compileTick);
        clearInterval(logoTick);
        if (ascii) ascii.textContent = frames[frames.length - 1];
        setTimeout(function () {
          el.classList.add('ot-boot-done', 'is-done');
          el.setAttribute('aria-busy', 'false');
          setTimeout(function () {
            if (el && el.parentNode) el.parentNode.removeChild(el);
          }, 750);
        }, reduce ? 80 : 520);
      }
    }, tickMs);
    return el;
  }

  function boot(root) {
    root = root || document;
    try {
      ensureLoader({
        brand: document.documentElement.getAttribute('data-mf-loader-brand') || '',
        sub: document.documentElement.getAttribute('data-mf-loader-sub') || ''
      });
    } catch (e) {}
    var radars = root.querySelectorAll('[data-mf-radar]');
    var nets = root.querySelectorAll('[data-mf-constellation]');
    var start = performance.now();

    function frame(now) {
      var t = (now - start) / 1000;
      radars.forEach(function (c) { drawRadar(c, { t: t }); });
      nets.forEach(function (c) { drawConstellation(c, { t: t }); });
      requestAnimationFrame(frame);
    }
    if (radars.length || nets.length) requestAnimationFrame(frame);

    // SFX wiring for mf-btn if OtaconSFX present
    root.addEventListener('click', function (ev) {
      var btn = ev.target.closest('.mf-btn, [data-ot-sfx]');
      if (!btn) return;
      if (global.OtaconSFX && typeof global.OtaconSFX.play === 'function') {
        var kind = btn.classList.contains('danger') ? 'alert' : 'click';
        try { global.OtaconSFX.play(kind); } catch (e) {}
      }
    }, true);
  }


  /* —— Live cyberdeck telemetry mount (polls /api/executor/telemetry) —— */
  var ARC_LEN = 180;

  function telemHtml(opts) {
    opts = opts || {};
    var compact = !!opts.compact;
    var title = opts.title || 'SYS // LIVE TELEMETRY · PROC otacon-executor';
    var id = opts.id || ('mf-telem-' + Math.random().toString(36).slice(2, 8));
    return (
      '<div class="mf-telem-deck' + (compact ? ' compact' : '') + '" id="' + id + '" data-mf-cyberdeck-ready="1" aria-live="polite">' +
      '<span class="mf-telem-corner tl"></span><span class="mf-telem-corner tr"></span>' +
      '<span class="mf-telem-corner bl"></span><span class="mf-telem-corner br"></span>' +
      '<div class="mf-telem-head"><span class="tag">' + title + '</span>' +
      '<span class="mf-telem-link live" data-telem-link><span class="pulse"></span><span data-telem-link-txt>LINK LIVE</span></span></div>' +
      '<div class="mf-telem-gauges">' +
      gaugeBlock('cpu', 'CPU LOAD', '%') +
      gaugeBlock('rss', 'RSS MEMORY', 'MB') +
      (compact ? (gaugeBlock('load', 'LOAD 1M', '') + gaugeBlock('fds', 'OPEN FDs', '')) : '') +
      '</div></div>'
    );
  }

  function gaugeBlock(key, label, unit) {
    return (
      '<div class="mf-cyber-gauge" data-g="' + key + '">' +
      '<div class="cg-arc-wrap"><svg class="cg-arc" viewBox="0 0 132 78" aria-hidden="true">' +
      '<defs><linearGradient id="mfTelemGrad" x1="0%" y1="0%" x2="100%" y2="0%">' +
      '<stop offset="0%" stop-color="#648ed0"/><stop offset="55%" stop-color="#979fec"/><stop offset="100%" stop-color="#d9b6fd"/>' +
      '</linearGradient></defs>' +
      '<path class="cg-track" d="M16 70 A50 50 0 0 1 116 70"/>' +
      '<path class="cg-fill" data-arc d="M16 70 A50 50 0 0 1 116 70"/>' +
      '</svg><div class="cg-val" data-val>—' + (unit ? '<span class="unit">' + unit + '</span>' : '') + '</div></div>' +
      '<div class="cg-label">' + label + '</div>' +
      '<div class="cg-meta" data-meta>polling…</div>' +
      '<canvas class="cg-spark" data-spark width="200" height="28"></canvas></div>'
    );
  }

  function setArc(el, pct) {
    if (!el) return;
    var p = clamp(Number(pct) || 0, 0, 100);
    el.style.strokeDasharray = String(ARC_LEN);
    el.style.strokeDashoffset = String(ARC_LEN * (1 - p / 100));
  }

  function drawSpark(canvas, arr, color) {
    if (!canvas || !arr || !arr.length) return;
    var ctx = canvas.getContext('2d');
    if (!ctx) return;
    var w = canvas.width, h = canvas.height;
    ctx.clearRect(0, 0, w, h);
    var min = Math.min.apply(null, arr), max = Math.max.apply(null, arr);
    var span = Math.max(1e-6, max - min);
    ctx.strokeStyle = color || '#979fec';
    ctx.lineWidth = 1.5;
    ctx.shadowColor = color || '#979fec';
    ctx.shadowBlur = 4;
    ctx.beginPath();
    arr.forEach(function (v, i) {
      var x = (i / Math.max(1, arr.length - 1)) * (w - 2) + 1;
      var y = h - 2 - ((v - min) / span) * (h - 4);
      if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    });
    ctx.stroke();
    ctx.shadowBlur = 0;
    ctx.lineTo(w - 1, h - 1);
    ctx.lineTo(1, h - 1);
    ctx.closePath();
    ctx.fillStyle = 'rgba(151,159,236,0.08)';
    ctx.fill();
  }

  function mountCyberdeck(target, opts) {
    opts = opts || {};
    var el = typeof target === 'string' ? document.querySelector(target) : target;
    if (!el) return null;
    var endpoint = opts.endpoint || '/api/executor/telemetry';
    var interval = opts.interval || 1500;
    if (!el.getAttribute('data-mf-cyberdeck-ready')) {
      el.innerHTML = telemHtml(opts);
      // if target itself should BE the deck, replace:
      var deck = el.querySelector('.mf-telem-deck') || el;
      if (el.classList.contains('mf-telem-host')) {
        el.innerHTML = telemHtml(opts);
      }
    }
    var root = el.classList.contains('mf-telem-deck') ? el : (el.querySelector('.mf-telem-deck') || el);
    var hist = { cpu: [], rss: [], load: [], fds: [] };
    var lastOk = 0;

    function push(k, v) {
      if (v == null || isNaN(v)) return;
      hist[k].push(Number(v));
      if (hist[k].length > 36) hist[k].shift();
    }

    function setLink(ok, detail) {
      var link = root.querySelector('[data-telem-link]');
      var txt = root.querySelector('[data-telem-link-txt]');
      if (!link) return;
      if (ok) {
        link.className = 'mf-telem-link live';
        if (txt) txt.textContent = 'LINK LIVE';
        lastOk = Date.now();
      } else {
        link.className = 'mf-telem-link stale';
        if (txt) txt.textContent = detail || 'LINK STALE';
      }
    }

    function apply(st) {
      if (!st) return;
      var cpu = st.cpu_percent != null ? st.cpu_percent : st.cpu_pct;
      var rss = st.rss_mb;
      var gCpu = root.querySelector('[data-g="cpu"]');
      var gRss = root.querySelector('[data-g="rss"]');
      var gLoad = root.querySelector('[data-g="load"]');
      var gFds = root.querySelector('[data-g="fds"]');
      if (gCpu) {
        var v = gCpu.querySelector('[data-val]');
        if (v) v.innerHTML = (cpu != null ? Number(cpu).toFixed(1) : '—') + '<span class="unit">%</span>';
        setArc(gCpu.querySelector('[data-arc]'), cpu != null ? cpu : 0);
        push('cpu', cpu);
        drawSpark(gCpu.querySelector('[data-spark]'), hist.cpu, '#979fec');
        var m = gCpu.querySelector('[data-meta]');
        if (m) {
          var host = st.host_cpu_percent != null ? (' · host ' + st.host_cpu_percent + '%') : '';
          var load = st.load_1m != null ? (' · load ' + st.load_1m) : '';
          m.textContent = 'PROC' + (st.fake ? ' ~est' : '') + host + load;
        }
      }
      if (gRss) {
        var vr = gRss.querySelector('[data-val]');
        if (vr) vr.innerHTML = (rss != null ? Number(rss).toFixed(1) : '—') + '<span class="unit">MB</span>';
        setArc(gRss.querySelector('[data-arc]'), rss != null ? Math.min(100, (rss / 2048) * 100) : 0);
        push('rss', rss);
        drawSpark(gRss.querySelector('[data-spark]'), hist.rss, '#d9b6fd');
        var mr = gRss.querySelector('[data-meta]');
        if (mr) {
          var mem = st.mem_percent != null ? (' · ' + st.mem_percent + '% mem') : '';
          var fds = st.open_fds != null ? (' · fd ' + st.open_fds) : '';
          var up = st.uptime_s != null ? (' · up ' + Math.round(st.uptime_s) + 's') : '';
          mr.textContent = 'RSS' + mem + fds + up;
        }
      }
      if (gLoad) {
        var ld = st.load_1m != null ? st.load_1m : st.loadavg;
        var vl = gLoad.querySelector('[data-val]');
        if (vl) vl.innerHTML = (ld != null ? Number(ld).toFixed(2) : '—');
        setArc(gLoad.querySelector('[data-arc]'), ld != null ? Math.min(100, ld * 25) : 0);
        push('load', ld);
        drawSpark(gLoad.querySelector('[data-spark]'), hist.load, '#a7c1e8');
        var ml = gLoad.querySelector('[data-meta]');
        if (ml) ml.textContent = 'host loadavg 1m';
      }
      if (gFds) {
        var fd = st.open_fds;
        var vf = gFds.querySelector('[data-val]');
        if (vf) vf.innerHTML = (fd != null ? String(fd) : '—');
        setArc(gFds.querySelector('[data-arc]'), fd != null ? Math.min(100, (fd / 512) * 100) : 0);
        push('fds', fd);
        drawSpark(gFds.querySelector('[data-spark]'), hist.fds, '#d9b6fd');
        var mf = gFds.querySelector('[data-meta]');
        if (mf) mf.textContent = 'proc fd count';
      }
    }

    function poll() {
      fetch(endpoint, { cache: 'no-store' })
        .then(function (r) {
          if (!r.ok) throw new Error('HTTP ' + r.status);
          return r.json();
        })
        .then(function (j) {
          var st = j.telemetry || j.stats || j;
          if (j.ok === false) throw new Error(j.error || 'telemetry fail');
          apply(st);
          setLink(true);
        })
        .catch(function () {
          if (Date.now() - lastOk > 4000) setLink(false, 'LINK WARN');
        });
    }

    poll();
    var timer = setInterval(poll, interval);
    return { root: root, poll: poll, stop: function () { clearInterval(timer); }, apply: apply };
  }

  function mountServiceProbes(target, opts) {
    opts = opts || {};
    var el = typeof target === 'string' ? document.querySelector(target) : target;
    if (!el) return null;
    var endpoint = opts.endpoint || '/api/intel/service-probes';
    var interval = opts.interval || 4000;

    function render(services) {
      var cards = (services || []).map(function (s) {
        var st = (s.status || 'unknown').toLowerCase();
        var cls = st === 'up' ? 'up' : (st === 'down' ? 'down' : 'unknown');
        var lat = s.latency_ms != null ? (s.latency_ms + 'ms') : '—';
        var code = s.http_code != null ? ('HTTP ' + s.http_code) : '';
        var open = s.url ? ('<a class="svc-open" href="' + s.url + '" target="_blank" rel="noopener">Open surface</a>') : '';
        return (
          '<article class="mf-svc-card ' + cls + '">' +
          '<div class="svc-top"><span class="svc-name">' + (s.name || 'SERVICE') + '</span>' +
          '<span class="svc-state">' + st + '</span></div>' +
          '<div class="svc-endpoint">' + (s.endpoint || s.url || '') + '</div>' +
          '<div class="svc-meta">' + lat + (code ? (' · ' + code) : '') + (s.detail ? (' · ' + s.detail) : '') + '</div>' +
          open + '</article>'
        );
      }).join('');
      el.innerHTML =
        '<div class="mf-svc-head"><h3>Keep Service Link · Live Probes</h3>' +
        '<span class="hint">OtaconsKeep .219 · OptiPlex .220 · offload .221 · Beszel · Kuma · VPN</span></div>' +
        '<div class="mf-svc-grid">' + cards + '</div>';
    }

    function poll() {
      fetch(endpoint, { cache: 'no-store' })
        .then(function (r) { return r.json(); })
        .then(function (j) {
          if (j && j.services) render(j.services);
        })
        .catch(function () {});
    }
    poll();
    var timer = setInterval(poll, interval);
    return { stop: function () { clearInterval(timer); }, poll: poll };
  }


  function ensureHudKit() {
    if (document.getElementById('mf-hud-overlay')) return;
    var html = document.documentElement;
    if (!(html.classList.contains('movie-fui-kit') || document.body.classList.contains('mf-page') || html.hasAttribute('data-mf-loader'))) return;
    if (html.getAttribute('data-db2') === '1' || document.body.classList.contains('db2-body')) return;
    var el = document.createElement('div');
    el.id = 'mf-hud-overlay';
    el.className = 'mf-hud-overlay';
    el.setAttribute('aria-hidden', 'true');
    el.innerHTML =
      '<div class="hud-word">HUD</div>' +
      '<div class="hud-rings"></div>' +
      '<div class="hud-eq"><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i></div>' +
      '<div class="hud-circuit"></div>' +
      '<div class="hud-rings-r">' +
        '<div class="hud-ring"><span>100</span></div>' +
        '<div class="hud-ring"><span>100</span></div>' +
        '<div class="hud-ring"><span>100</span></div>' +
        '<div class="hud-ring"><span>72</span></div>' +
        '<div class="hud-ring"><span>100</span></div>' +
        '<div class="hud-ring"><span>100</span></div>' +
      '</div>' +
      '<div class="hud-faders"><b></b><b></b><b></b><b></b></div>';
    document.body.appendChild(el);
  }

  // Auto-mount hosts marked in HTML
  var _oldBoot = boot;
  boot = function (root) {
    _oldBoot(root);
    try {
      root.querySelectorAll('[data-mf-cyberdeck]').forEach(function (node) {
        if (node.getAttribute('data-mf-cyberdeck-mounted')) return;
        node.setAttribute('data-mf-cyberdeck-mounted', '1');
        var compact = node.getAttribute('data-mf-cyberdeck') === 'compact' || node.hasAttribute('data-compact');
        var title = node.getAttribute('data-telem-title') || undefined;
        var endpoint = node.getAttribute('data-telem-endpoint') || undefined;
        if (!node.classList.contains('mf-telem-deck') && !node.querySelector('.mf-telem-deck')) {
          node.classList.add('mf-telem-host');
          node.innerHTML = telemHtml({ compact: compact, title: title });
        }
        mountCyberdeck(node, { compact: compact, title: title, endpoint: endpoint });
      });
      root.querySelectorAll('[data-mf-service-probes]').forEach(function (node) {
        if (node.getAttribute('data-mf-probes-mounted')) return;
        node.setAttribute('data-mf-probes-mounted', '1');
        mountServiceProbes(node, {});
      });
      ensureHudKit();
    } catch (e) {}
  };

  global.MovieFUI = {
    boot: boot,
    drawRadar: drawRadar,
    drawConstellation: drawConstellation,
    ensureLoader: ensureLoader,
    clamp: clamp,
    mountCyberdeck: mountCyberdeck,
    mountServiceProbes: mountServiceProbes,
    telemHtml: telemHtml,
    ensureHudKit: ensureHudKit
  };

  try { if (document.body) ensureLoader(); } catch (e0) {}

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () { boot(document); });
  } else {
    boot(document);
  }
})(window);
