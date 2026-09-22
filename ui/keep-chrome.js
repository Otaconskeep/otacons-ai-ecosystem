/* Shared Keep chrome — top tabs + Command Center tile homescreen.
   Depends on wizard.js globals: escapeHtml, showHome, showChat, showExpansionSurface, otSfx, otArmAudio, apiGet, api, appRoot, setBodyMode, render, state */
(function (global) {
  'use strict';

  var _launchpadCache = null;
  var _launchpadAt = 0;

  function esc(s) {
    return typeof escapeHtml === 'function' ? escapeHtml(s == null ? '' : s) : String(s == null ? '' : s);
  }

  async function loadLaunchpad(force) {
    var now = Date.now();
    if (!force && _launchpadCache && now - _launchpadAt < 15000) return _launchpadCache;
    try {
      var data = await apiGet('/api/launchpad', 8000);
      _launchpadCache = data;
      _launchpadAt = now;
      return data;
    } catch (_e) {
      try {
        var d2 = await apiGet('/api/expansion/launchpad', 8000);
        _launchpadCache = d2;
        _launchpadAt = now;
        return d2;
      } catch (_e2) {
        return _launchpadCache || { tabs: defaultTabs(), groups: [], tiles: [], edition: 'lite' };
      }
    }
  }

  function defaultTabs() {
    return [
      { id: 'homescreen', label: 'Homescreen', action: 'homescreen' },
      { id: 'codec', label: 'Codec', action: 'codec' },
    ];
  }

  function tabClickAttr(tab) {
    var action = tab.action || tab.id;
    if (action === 'homescreen' || action === 'home') {
      return "otArmAudio();otSfx('click');showHome()";
    }
    if (action === 'codec') {
      return "otArmAudio();otSfx('transmit');showChat()";
    }
    if (action === 'setup') {
      return "otSfx('click');render()";
    }
    if (action === 'external' && tab.href) {
      return "otSfx('ok');window.open('" + esc(tab.href).replace(/'/g, "\\'") + "','_blank','noopener')";
    }
    return "otSfx('click');typeof showExpansionSurface==='function'&&showExpansionSurface('" + esc(action) + "')";
  }

  function keepTopTabsHtml(activeId, tabs) {
    var list = tabs && tabs.length ? tabs : null;
    if (!list && _launchpadCache && _launchpadCache.tabs && _launchpadCache.tabs.length) {
      list = _launchpadCache.tabs;
    }
    if (!list || !list.length) list = defaultTabs();
    var bits = list.map(function (t) {
      var id = t.id || '';
      var on = id === activeId || (activeId === 'home' && id === 'homescreen') ? ' on' : '';
      var live = t.live ? ' live' : '';
      return (
        '<button type="button" class="kc-tab' + on + live + '" data-tab="' + esc(id) + '" onclick="' +
        tabClickAttr(t) + '">' + esc(t.label || id) + '</button>'
      );
    });
    return (
      '<nav class="kc-tabs" aria-label="Keep navigation">' +
      '<div class="kc-tabs-brand" onclick="otArmAudio();otSfx(\'click\');showHome()" title="Homescreen">' +
      '<span class="kc-mark">OT</span><span class="kc-brand-t">COMMAND CENTER</span></div>' +
      '<div class="kc-tabs-row">' + bits.join('') + '</div></nav>'
    );
  }

  function tileClickAttr(tile) {
    if (tile.kind === 'external') {
      if (tile.href) {
        return "otSfx('ok');window.open('" + esc(tile.href).replace(/'/g, "\\'") + "','_blank','noopener')";
      }
      return "otSfx('error');typeof keepChromePromptCompanion==='function'&&keepChromePromptCompanion('" + esc(tile.id) + "')";
    }
    var action = tile.action || tile.id;
    if (action === 'codec') return "otArmAudio();otSfx('transmit');showChat()";
    if (action === 'setup') return "otSfx('click');render()";
    if (action === 'homescreen') return "otSfx('click');showHome()";
    return "otSfx('click');typeof showExpansionSurface==='function'&&showExpansionSurface('" + esc(action) + "')";
  }

  function renderHomescreen(lp) {
    var edition = (lp && lp.edition) || 'lite';
    var brand = edition === 'premium' ? 'Otaconskeep · Premium' : 'Otaconskeep · Lite';
    var groups = (lp && lp.groups) || [];
    var groupHtml = groups.map(function (g) {
      var tiles = (g.tiles || []).map(function (t) {
        var live = t.live ? ' live' : (t.available ? ' dim' : ' ghost');
        var hint = t.hint ? '<em class="kc-tile-hint">' + esc(t.hint) + '</em>' : '';
        var status = t.live ? 'LIVE' : (t.available ? 'READY' : 'ADD');
        return (
          '<button type="button" class="kc-tile' + live + '" onclick="' + tileClickAttr(t) + '">' +
          '<span class="kc-tile-icon">' + esc(t.icon || '·') + '</span>' +
          '<span class="kc-tile-body"><strong>' + esc(t.title) + '</strong>' +
          '<span>' + esc(t.desc || '') + '</span>' + hint + '</span>' +
          '<span class="kc-tile-st">' + status + '</span></button>'
        );
      }).join('');
      return (
        '<section class="kc-group"><h2>' + esc(g.name || 'Tiles') + '</h2>' +
        '<div class="kc-tile-grid">' + tiles + '</div></section>'
      );
    }).join('');

    return (
      '<div class="home kc-home">' +
      keepTopTabsHtml('homescreen', lp && lp.tabs) +
      '<header class="kc-hero">' +
      '<p class="kc-kicker">' + brand + '</p>' +
      '<h1>Command Center</h1>' +
      '<p class="kc-intro">' + esc((lp && lp.note) || 'Launchpad — Codec, rooms, and companion products.') + '</p>' +
      '</header>' +
      '<div class="kc-body">' + groupHtml + '</div>' +
      '<p class="home-foot">Otaconskeep · Designed &amp; Engineered by Antonio G. Garcia · discord.gg/cZDeqECzX</p>' +
      '</div>'
    );
  }

  async function showHomescreen() {
    if (typeof setBodyMode === 'function') setBodyMode('home');
    if (typeof state !== 'undefined') state.view = 'home';
    try { otArmAudio(); otSfx('boot'); } catch (_e) {}
    var lp = await loadLaunchpad(true);
    appRoot().innerHTML = renderHomescreen(lp);
    try { if (typeof otAmbientStart === 'function') otAmbientStart(); } catch (_e2) {}
  }

  function keepChromePromptCompanion(id) {
    var keyMap = {
      keep_desk: 'keep_desk_url',
      keeproute: 'keeproute_url',
      omniroute: 'omniroute_url',
    };
    var key = keyMap[id];
    if (!key) return;
    var url = window.prompt(
      'Paste the local URL for this companion (example http://127.0.0.1:20129/). Leave blank to clear.',
      ''
    );
    if (url == null) return;
    var body = {};
    body[key] = String(url).trim();
    Promise.resolve(api('/api/launchpad/configure', body, 8000))
      .then(function () { showHomescreen(); })
      .catch(function () { showHomescreen(); });
  }

  /** Prefix existing page HTML with top tabs (floors / rex / codec shells). */
  function withTopTabs(activeId, innerHtml, tabs) {
    return '<div class="kc-page">' + keepTopTabsHtml(activeId, tabs) + (innerHtml || '') + '</div>';
  }

  global.keepTopTabsHtml = keepTopTabsHtml;
  global.keepChromeLoadLaunchpad = loadLaunchpad;
  global.keepChromeShowHomescreen = showHomescreen;
  global.keepChromePromptCompanion = keepChromePromptCompanion;
  global.keepChromeWithTabs = withTopTabs;
  global.keepChromeRenderHomescreen = renderHomescreen;
})(typeof window !== 'undefined' ? window : this);
