/* Shared, gesture-gated interface sound for Otacon room shells. */
window.OtaconSFX = (function () {
  'use strict';
  var sounds = {
    click: '/static/audio/ui_click.wav',
    success: '/static/audio/ui_success.wav',
    alert: '/static/audio/ui_alert.wav',
    connect: '/static/audio/ui_connect.wav'
  };
  var muted = localStorage.getItem('otacon-sfx-muted') === 'true';
  var userActed = false;
  var lastPlay = 0;
  var bootPlayed = sessionStorage.getItem('otacon-sfx-boot') === '1';
  var CLICK_SEL = '.ot-nav a, .ot-nav-links a, button, a.ot-btn, .ot-card a, .ot-card, a.card, .card a, [role="button"], [data-ot-sfx]';

  function play(kind, volume) {
    if (muted || !userActed) return;
    var now = Date.now();
    if (kind === 'click' && now - lastPlay < 70) return;
    if (kind === 'click') lastPlay = now;
    var audio = new Audio(sounds[kind] || sounds.click);
    audio.preload = 'auto';
    audio.volume = typeof volume === 'number' ? volume : 0.75;
    var result = audio.play();
    if (result && result.catch) result.catch(function () {});
  }

  function playBootOnce() {
    if (muted || bootPlayed) return;
    bootPlayed = true;
    try { sessionStorage.setItem('otacon-sfx-boot', '1'); } catch (e) {}
    var audio = new Audio(sounds.connect);
    audio.preload = 'auto';
    audio.volume = 0.8;
    var result = audio.play();
    if (result && result.catch) result.catch(function () {});
  }

  function updateToggle() {
    var button = document.getElementById('ot-sfx-toggle');
    if (!button) return;
    button.setAttribute('aria-pressed', muted ? 'false' : 'true');
    button.textContent = muted ? 'SFX OFF' : 'SFX ON';
    button.classList.toggle('is-on', !muted);
    button.classList.toggle('is-off', muted);
    button.title = muted ? 'Enable interface sounds' : 'Mute interface sounds';
  }

  function setMuted(value) {
    muted = !!value;
    localStorage.setItem('otacon-sfx-muted', String(muted));
    updateToggle();
  }

  function onFirstGesture() {
    if (userActed) return;
    userActed = true;
    playBootOnce();
  }

  function bind() {
    ['pointerdown', 'keydown', 'touchstart'].forEach(function (eventName) {
      document.addEventListener(eventName, onFirstGesture, { once: true, passive: true });
    });
    document.addEventListener('click', function (event) {
      var target = event.target.closest(CLICK_SEL);
      if (!target) return;
      if (target.id === 'ot-sfx-toggle' || target.id === 'ot-ambient-toggle') return;
      if (target.classList && target.classList.contains('ot-nav-audio-toggle')) return;
      if (target.classList && target.classList.contains('ot-shell-banner-dismiss')) return;
      userActed = true;
      playBootOnce();
      play(target.getAttribute('data-ot-sfx') || 'click');
    });
    var button = document.getElementById('ot-sfx-toggle');
    if (button && !button.getAttribute('data-ot-bound')) {
      button.setAttribute('data-ot-bound', '1');
      button.addEventListener('click', function (event) {
        event.preventDefault();
        userActed = true;
        setMuted(!muted);
        if (!muted) play('click');
      });
    }
    updateToggle();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', bind);
  } else {
    bind();
  }
  return {
    play: play,
    click: function () { play('click'); },
    success: function () { play('success'); },
    alert: function () { play('alert'); },
    connect: function () { play('connect', 0.8); },
    setMuted: setMuted,
    isMuted: function () { return muted; }
  };
}());