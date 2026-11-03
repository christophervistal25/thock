/* Thock typing test: plays the app's own samples with Web Audio as you type.
   Mirrors thock/engine.py: key-down + key-up per key, Space/Enter/Backspace samples,
   stereo position by key, ±3% pitch / ±8% volume variation, optional mouse clicks,
   optional sound on key repeat. Nothing typed leaves the page. */
(function () {
  'use strict';
  var root = document.getElementById('tt');
  if (!root) return;

  var BASE = 'assets/packs/';
  var DEFAULTS = { pack: 'tactile-brown', volume: 0.6, tone: 0, mouse: true, spatial: true, variation: true, repeat: false };
  var REPEAT_GAIN = 0.85, REPEAT_MIN = 0.025, MOUSE_PAN = 0.78, MOUSE_PITCH = { 0: 1.0, 1: 0.93, 2: 1.07 };
  var TEXTS = [
    'The quick brown fox jumps over the lazy dog while the keyboard hums along.',
    'Good switches make every word feel deliberate, from the first press to the last release.',
    'Pack my box with five dozen liquor jugs, then type it again a little faster.',
    'A quiet room, a warm cup of coffee and the steady sound of keys going down.',
    'Sphinx of black quartz, judge my vow, and listen to how each key lands.'
  ];

  // ---- settings ------------------------------------------------------
  var cfg = Object.assign({}, DEFAULTS);
  try { Object.assign(cfg, JSON.parse(localStorage.getItem('thock-web') || '{}')); } catch (e) {}
  function save() { try { localStorage.setItem('thock-web', JSON.stringify(cfg)); } catch (e) {} }

  // ---- key positions (same layout as thock/keymap.py) ------------------
  var EV = {Escape:1,Backquote:41,Minus:12,Equal:13,Backspace:14,Tab:15,BracketLeft:26,BracketRight:27,Backslash:43,
    CapsLock:58,Semicolon:39,Quote:40,Enter:28,ShiftLeft:42,Comma:51,Period:52,Slash:53,ShiftRight:54,
    ControlLeft:29,MetaLeft:125,AltLeft:56,Space:57,AltRight:100,MetaRight:126,ContextMenu:127,ControlRight:97};
  '1234567890'.split('').forEach(function (d, i) { EV['Digit' + d] = 2 + i; });
  'QWERTYUIOP'.split('').forEach(function (c, i) { EV['Key' + c] = 16 + i; });
  'ASDFGHJKL'.split('').forEach(function (c, i) { EV['Key' + c] = 30 + i; });
  'ZXCVBNM'.split('').forEach(function (c, i) { EV['Key' + c] = 44 + i; });
  var ROWS = [
    [[41,1],[2,1],[3,1],[4,1],[5,1],[6,1],[7,1],[8,1],[9,1],[10,1],[11,1],[12,1],[13,1],[14,2]],
    [[15,1.5],[16,1],[17,1],[18,1],[19,1],[20,1],[21,1],[22,1],[23,1],[24,1],[25,1],[26,1],[27,1],[43,1.5]],
    [[58,1.75],[30,1],[31,1],[32,1],[33,1],[34,1],[35,1],[36,1],[37,1],[38,1],[39,1],[40,1],[28,2.25]],
    [[42,2.25],[44,1],[45,1],[46,1],[47,1],[48,1],[49,1],[50,1],[51,1],[52,1],[53,1],[54,2.75]],
    [[29,1.25],[125,1.25],[56,1.25],[57,6.25],[100,1.25],[126,1.25],[127,1.25],[97,1.25]]
  ];
  var POS = { 1: 0.5 / 15 };
  ROWS.forEach(function (row) { var x = 0; row.forEach(function (k) { POS[k[0]] = (x + k[1] / 2) / 15; x += k[1]; }); });
  function keyX(code) { return 0.06 + (code in POS ? POS[code] : 0.5) * 0.82; }

  // ---- audio ---------------------------------------------------------
  var ctx = null, bus = null, low = null, high = null, master = null;
  var index = null, indexP = null, bytes = {}, buffers = {}, pending = {};
  var pack = null;          // current pack entry from packs.json
  var held = {};            // event.code -> {down, up, t}
  var buttons = {};

  function loadIndex() {
    if (!indexP) indexP = fetch(BASE + 'packs.json').then(function (r) { return r.json(); }).then(function (j) { index = j; fillPacks(); return j; });
    return indexP;
  }
  function fetchBytes(file) {
    if (!bytes[file]) bytes[file] = fetch(BASE + file).then(function (r) { if (!r.ok) throw new Error(r.status); return r.arrayBuffer(); });
    return bytes[file];
  }
  function decoded(file) {
    if (buffers[file]) return Promise.resolve(buffers[file]);
    if (!pending[file]) pending[file] = fetchBytes(file).then(function (ab) {
      return new Promise(function (ok, bad) { ctx.decodeAudioData(ab.slice(0), ok, bad); });
    }).then(function (b) { buffers[file] = b; return b; });
    return pending[file];
  }
  function findPack(id) {
    for (var i = 0; i < index.packs.length; i++) if (index.packs[i].id === id) return index.packs[i];
    return index.packs[0];
  }
  // Fetch (but do not decode or play) the selected pack ahead of the first keystroke.
  function prefetch() {
    loadIndex().then(function () { fetchBytes(findPack(cfg.pack).file); fetchBytes(index.mouse.file); }).catch(function () {});
  }
  function unlock() {
    if (ctx) { if (ctx.state === 'suspended') ctx.resume(); return; }
    var AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) { status('This browser has no Web Audio support.'); return; }
    ctx = new AC({ latencyHint: 'interactive' });
    master = ctx.createGain();
    low = ctx.createBiquadFilter(); low.type = 'lowshelf'; low.frequency.value = 500;
    high = ctx.createBiquadFilter(); high.type = 'highshelf'; high.frequency.value = 3000;
    var lim = ctx.createDynamicsCompressor();
    lim.threshold.value = -4; lim.knee.value = 2; lim.ratio.value = 20; lim.attack.value = 0.001; lim.release.value = 0.08;
    master.connect(low); low.connect(high); high.connect(lim); lim.connect(ctx.destination);
    bus = master;
    applyTone();
    if (ctx.state === 'suspended') ctx.resume();
    usePack(cfg.pack);
  }
  function usePack(id) {
    if (!ctx) return;
    loadIndex().then(function () {
      var p = findPack(id);
      status('Loading ' + p.name + '…');
      return Promise.all([decoded(p.file), decoded(index.mouse.file)]).then(function () {
        if (cfg.pack === p.id) { pack = p; status(''); }
      });
    }).catch(function () { status('Could not load the sound pack. Check your connection and reload.'); });
  }
  function applyTone() {
    if (!ctx) return;
    // Tilt EQ like the app: thock (-1) lifts lows and softens highs, clack (+1) the opposite.
    var t = cfg.tone, now = ctx.currentTime;
    low.gain.setTargetAtTime(-t * 9, now, 0.02);
    high.gain.setTargetAtTime(t * 9, now, 0.02);
    master.gain.setTargetAtTime(1.4 * Math.pow(cfg.volume, 1.6) * Math.pow(10, -Math.abs(t) * 3 / 20), now, 0.02);
  }
  function play(file, ref, gain, x, pitch) {
    var buf = buffers[file];
    if (!ctx || !buf || !ref) return;
    pitch = pitch || 1;
    if (cfg.variation) { pitch *= 1 + (Math.random() * 0.06 - 0.03); gain *= 1 + (Math.random() * 0.16 - 0.08); }
    var src = ctx.createBufferSource(); src.buffer = buf; src.playbackRate.value = pitch;
    var g = ctx.createGain(); g.gain.value = gain;
    src.connect(g);
    var out = g;
    if (ctx.createStereoPanner) {
      var p = ctx.createStereoPanner(); p.pan.value = cfg.spatial ? x * 2 - 1 : 0; g.connect(p); out = p;
    }
    out.connect(bus);
    src.start(0, ref[0], ref[1]);
  }
  function pick(code) {
    var k = pack.keys[String(code)];
    if (k) return k;
    return pack.default[Math.floor(Math.random() * pack.default.length)] || [null, null];
  }
  function keyDown(e) {
    unlock();
    if (!pack) return;
    var id = e.code || ('k' + e.key);
    var code = EV[e.code] || 0;
    var now = ctx.currentTime, gain = 1, h = held[id];
    if (h) {
      if (!cfg.repeat || now - h.t < REPEAT_MIN) return;
      h.t = now; gain = REPEAT_GAIN;
    } else {
      var s = pick(code);
      h = held[id] = { down: s[0], up: s[1], t: now, file: pack.file };
    }
    play(h.file, h.down, gain, keyX(code));
  }
  function keyUp(e) {
    var id = e.code || ('k' + e.key);
    var h = held[id]; delete held[id];
    if (h && h.up) play(h.file, h.up, 1, keyX(EV[e.code] || 0));
  }
  function mouse(e, down) {
    if (down) unlock();
    if (!(e.button in MOUSE_PITCH) || e.pointerType === 'touch') return;
    if (down) { if (buttons[e.button]) return; buttons[e.button] = 1; }
    else { if (!buttons[e.button]) return; delete buttons[e.button]; }
    if (!cfg.mouse || !pack) return;
    play(index.mouse.file, down ? index.mouse.down : index.mouse.up, 0.9, MOUSE_PAN, MOUSE_PITCH[e.button]);
  }

  // ---- typing test ---------------------------------------------------
  var input = root.querySelector('.tt-input'), textEl = root.querySelector('.tt-text');
  var wpmEl = root.querySelector('[data-stat=wpm]'), accEl = root.querySelector('[data-stat=acc]'), timeEl = root.querySelector('[data-stat=time]');
  var statusEl = root.querySelector('.tt-status'), area = root.querySelector('.tt-area');
  var target = '', spans = [], typed = '', strokes = 0, errors = 0, t0 = 0, done = false, timer = 0, ti = 0, sawKey = false;

  function status(s) { statusEl.textContent = s; statusEl.hidden = !s; }
  function newText(next) {
    if (next) ti = (ti + 1) % TEXTS.length;
    target = TEXTS[ti]; typed = ''; strokes = 0; errors = 0; t0 = 0; done = false;
    input.value = ''; input.maxLength = target.length;
    textEl.textContent = '';
    spans = target.split('').map(function (c) { var s = document.createElement('span'); s.textContent = c; textEl.appendChild(s); return s; });
    root.classList.remove('is-done');
    render(); stats();
  }
  function render() {
    for (var i = 0; i < spans.length; i++) {
      var c = i < typed.length ? (typed[i] === target[i] ? 'ok' : 'bad') : (i === typed.length ? 'cur' : '');
      if (spans[i].className !== c) spans[i].className = c;
    }
  }
  function stats() {
    var secs = t0 ? ((done ? done : performance.now()) - t0) / 1000 : 0;
    var correct = 0;
    for (var i = 0; i < typed.length; i++) if (typed[i] === target[i]) correct++;
    wpmEl.textContent = (secs > 1 || (done && secs > 0)) ? Math.round(correct / 5 / (secs / 60)) : '0';
    accEl.textContent = strokes ? Math.max(0, Math.round((strokes - errors) / strokes * 100)) + '%' : '100%';
    timeEl.textContent = secs.toFixed(1) + 's';
  }
  input.addEventListener('input', function () {
    var v = input.value;
    if (done) { input.value = typed; return; }
    if (!t0 && v.length) { t0 = performance.now(); timer = setInterval(stats, 250); }
    if (v.length > typed.length) {
      for (var i = typed.length; i < v.length; i++) { strokes++; if (v[i] !== target[i]) errors++; }
    }
    // touch keyboards often send no usable key events: give them a press sound anyway
    if (!sawKey) unlock();
    if (!sawKey && pack) { var s = pick(0); play(pack.file, s[0], 1, 0.47); var f = pack.file; setTimeout(function () { play(f, s[1], 1, 0.47); }, 70); }
    sawKey = false;
    typed = v; render();
    if (typed.length >= target.length) { done = performance.now(); clearInterval(timer); root.classList.add('is-done'); }
    stats();
  });
  input.addEventListener('keydown', function (e) {
    if (e.key === 'Unidentified' || e.key === 'Process' || e.isComposing) return;
    sawKey = true;
    if (e.key === 'Escape') { e.preventDefault(); clearInterval(timer); newText(false); }
    if (e.key === 'Enter' && done) { e.preventDefault(); clearInterval(timer); newText(true); }
    keyDown(e);
  });
  input.addEventListener('keyup', keyUp);
  input.addEventListener('blur', function () { held = {}; root.classList.remove('is-focused'); });
  input.addEventListener('focus', function () { root.classList.add('is-focused'); prefetch(); });
  area.addEventListener('pointerdown', function (e) { mouse(e, true); });
  area.addEventListener('pointerup', function (e) { mouse(e, false); });
  area.addEventListener('contextmenu', function (e) { e.preventDefault(); });
  area.addEventListener('pointerenter', prefetch, { once: true });
  root.querySelector('[data-act=restart]').addEventListener('click', function () { clearInterval(timer); newText(false); input.focus(); });
  root.querySelector('[data-act=next]').addEventListener('click', function () { clearInterval(timer); newText(true); input.focus(); });

  // ---- settings panel ------------------------------------------------
  var sel = root.querySelector('[name=pack]'), desc = root.querySelector('.tt-desc');
  function fillPacks() {
    sel.textContent = '';
    index.packs.forEach(function (p) { var o = document.createElement('option'); o.value = p.id; o.textContent = p.name; sel.appendChild(o); });
    sel.value = findPack(cfg.pack).id; cfg.pack = sel.value;
    describe();
  }
  function describe() { if (index) desc.textContent = findPack(cfg.pack).description; }
  sel.addEventListener('change', function () { cfg.pack = sel.value; save(); describe(); pack = null; held = {}; if (ctx) usePack(cfg.pack); else prefetch(); });
  root.querySelectorAll('input[type=range]').forEach(function (r) {
    r.value = cfg[r.name];
    r.addEventListener('input', function () { cfg[r.name] = parseFloat(r.value); save(); applyTone(); });
  });
  root.querySelectorAll('input[type=checkbox]').forEach(function (c) {
    c.checked = !!cfg[c.name];
    c.addEventListener('change', function () { cfg[c.name] = c.checked; save(); });
  });
  root.querySelector('[data-act=reset]').addEventListener('click', function () {
    cfg = Object.assign({}, DEFAULTS); save();
    root.querySelectorAll('input[type=range]').forEach(function (r) { r.value = cfg[r.name]; });
    root.querySelectorAll('input[type=checkbox]').forEach(function (c) { c.checked = !!cfg[c.name]; });
    if (index) { sel.value = cfg.pack; describe(); }
    applyTone(); if (ctx) usePack(cfg.pack);
  });

  if (window.matchMedia && matchMedia('(pointer: coarse)').matches) root.classList.add('is-touch');
  newText(false);
  loadIndex().catch(function () { status('Sound packs could not be loaded.'); });
})();
