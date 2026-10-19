/* _hotspots.js — подсказки к элементам HTML-макета: «что это и для чего» (набор макетов product-strategy 1.3).
   Копирует в <OUT>/mockups/concepts/ скрипт mockup_kit.py init; подключение — последней строкой <body> макета:
     <script src="_hotspots.js"></script>          (в галерее mockups/gallery.html — <script src="concepts/_hotspots.js"></script>)
   Разметка — атрибуты у существующих элементов макета (вид и вёрстку не меняют), стандарт — 12–25 элементов на экран:
     data-hs="id"                 элемент с подсказкой (id уникален в файле); тот же id без data-hs-title — «часть» (рамка = объединение);
     data-hs-title="…"            название элемента (обязательно у одного элемента с этим id);
     data-hs-what="…"             что это (одна-две фразы);  data-hs-why="…" — для чего (какую задачу пользователя решает);
     data-hs-p="P001 P019"        предложения реестра (P-id или черновики G8-01);  data-hs-sec="5 12" — разделы стратегии.
   Режим: кнопка «Подсказки» (слева внизу; не закрывает бейдж концепта) → рамки с номерами у всех размеченных элементов;
   наведение или фокус — подсказка; клик — подсказка закрепляется (ссылки на P-id и разделы, ‹ › — соседний элемент);
   «Список» — все элементы экрана с переходом; Esc — выключить. Ссылка #hs включает режим при открытии, #hs=<id> — ещё и
   закрепляет подсказку элемента. Ссылки ведут на страницу стратегии: window.PS_HS_STRATEGY (по умолчанию
   ../../deliverables/index.html), якоря #p/<P-id> и #s-<N>; имена разделов — window.PS_HS_SECTIONS = {5: '…'} (необязательно).
   Без сети и внешних библиотек, работает по file:// (Chrome, Safari, Firefox). Цвета — свои (контраст ≥ 4,5:1 в обеих темах).
   Под автоматизацией (navigator.webdriver — снимки shoot_mockups.mjs) кнопка не показывается, чтобы не попасть в PNG;
   режим тогда включается через #hs или window.PS_HS_FORCE = true. Зоны для страницы стратегии снимает shoot_mockups.mjs
   (data/mockups-check.<ключ>.json → hotspots.zones). API — window.PS_HS {items, on(), off(), pin(id), toggle()}. */
(function () {
  'use strict';
  if (window.PS_HS) return;
  var doc = document, root = doc.documentElement;
  var STRAT = window.PS_HS_STRATEGY || '../../deliverables/index.html';
  var SECT = window.PS_HS_SECTIONS || {};
  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); }
  function all(sel, r) { return Array.prototype.slice.call((r || doc).querySelectorAll(sel)); }
  function automated() { return !!navigator.webdriver && !window.PS_HS_FORCE; }

  /* ---------- галерея: у каждой карточки ссылка «с подсказками» ---------- */
  if (!doc.querySelector('[data-hs]')) {
    var links = all('a[href$=".html"]').filter(function (a) { return /(^|\/)concepts\/M[^/]*\.html$/.test(a.getAttribute('href') || ''); });
    if (!links.length) return;
    var done = {};
    links.forEach(function (a) {
      var href = a.getAttribute('href'); var box = a.closest('[data-card]') || a.parentNode;
      if (done[href] || !box || box.querySelector('[data-hs-ui]') || a.querySelector('img')) return;
      done[href] = 1;
      var l = doc.createElement('a'); l.href = href + '#hs'; l.setAttribute('data-hs-ui', ''); l.textContent = 'с подсказками ›';
      l.title = 'Открыть макет с подсветкой элементов: что это и для чего';
      a.parentNode.insertBefore(doc.createTextNode(' · '), a.nextSibling); a.parentNode.insertBefore(l, a.nextSibling.nextSibling);
    });
    window.PS_HS = { gallery: true, links: all('a[data-hs-ui]').length };
    return;
  }

  /* ---------- элементы ---------- */
  var ITEMS = [], BYID = {};
  all('[data-hs]').forEach(function (el) {
    var id = el.getAttribute('data-hs'); if (!id) return;
    var it = BYID[id];
    if (!it) { it = BYID[id] = { id: id, el: null, parts: [] }; ITEMS.push(it); }
    if (el.hasAttribute('data-hs-title') && !it.el) {
      it.el = el; it.title = el.getAttribute('data-hs-title') || id;
      it.what = el.getAttribute('data-hs-what') || ''; it.why = el.getAttribute('data-hs-why') || '';
      it.p = (el.getAttribute('data-hs-p') || '').split(/[\s,]+/).filter(function (x) { return /^(P\d{3,}|G\d+-\d{2,})$/.test(x); });
      it.sec = (el.getAttribute('data-hs-sec') || '').split(/[\s,]+/).filter(function (x) { return /^\d{1,2}$/.test(x); });
    } else it.parts.push(el);
  });
  ITEMS = ITEMS.filter(function (it) { return it.el; });
  ITEMS.forEach(function (it, i) { it.n = i + 1; });
  if (!ITEMS.length) return;

  /* ---------- стиль: свои цвета, не зависят от токенов макета ---------- */
  var CSS = [
    '#hs-ui,#hs-ui *{box-sizing:border-box;font-family:system-ui,-apple-system,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif;letter-spacing:normal;text-transform:none}',
    '#hs-ui{--hs-bg:#ffffff;--hs-fg:#14171c;--hs-mu:#4a5361;--hs-bd:#1f2937;--hs-ln:#1d4ed8}',
    '@media (prefers-color-scheme:dark){#hs-ui{--hs-bg:#151a21;--hs-fg:#eef1f5;--hs-mu:#b4bdc9;--hs-bd:#ffd60a;--hs-ln:#93b4ff}}',
    'html[data-theme="dark"] #hs-ui{--hs-bg:#151a21;--hs-fg:#eef1f5;--hs-mu:#b4bdc9;--hs-bd:#ffd60a;--hs-ln:#93b4ff}',
    'html[data-theme="light"] #hs-ui{--hs-bg:#ffffff;--hs-fg:#14171c;--hs-mu:#4a5361;--hs-bd:#1f2937;--hs-ln:#1d4ed8}',
    '#hs-ui button{font:inherit;cursor:pointer}',
    '#hs-ui [hidden]{display:none!important}',
    '#hs-fab{position:fixed;z-index:2147483640;left:12px;bottom:12px;display:flex;gap:6px}',
    '#hs-fab button{display:inline-flex;align-items:center;gap:7px;min-height:36px;padding:6px 14px;border-radius:999px;border:2px solid #ffd60a;background:#111827;color:#ffffff;font-size:13px;font-weight:650;box-shadow:0 2px 10px rgba(0,0,0,.35)}',
    '#hs-fab button[aria-pressed="true"]{background:#ffd60a;color:#111111;border-color:#111111}',
    '#hs-ui button:focus-visible,#hs-ui a:focus-visible{outline:3px solid #2563eb;outline-offset:2px}',
    '#hs-layer{position:fixed;inset:0;z-index:2147483500;pointer-events:none}',
    '#hs-layer .hs-box{position:fixed;pointer-events:auto;border:2px solid #ffd60a;border-radius:4px;background:rgba(255,214,10,.08);box-shadow:0 0 0 1.5px #111111;cursor:help}',
    '#hs-layer .hs-box:hover,#hs-layer .hs-box.hs-on{background:rgba(255,214,10,.22);border-width:3px}',
    '#hs-layer .hs-num{position:fixed;display:flex;align-items:center;justify-content:center;min-width:22px;height:22px;padding:0 5px;border-radius:11px;border:1.5px solid #111111;background:#ffd60a;color:#111111;font-size:11px;font-weight:750;pointer-events:auto;cursor:pointer}',
    '#hs-tip,#hs-list{position:fixed;z-index:2147483620;background:var(--hs-bg);color:var(--hs-fg);border:1.5px solid var(--hs-bd);border-radius:10px;box-shadow:0 10px 32px rgba(0,0,0,.38);font-size:13px;line-height:1.45}',
    '#hs-tip{max-width:min(360px,calc(100vw - 16px));padding:10px 12px;pointer-events:none}',
    '#hs-tip.hs-pin{pointer-events:auto}',
    '#hs-tip b{display:block;font-size:14px;margin-bottom:4px}',
    '#hs-tip .hs-k{color:var(--hs-mu);font-weight:650}',
    '#hs-tip p{margin:4px 0}',
    '#hs-tip a,#hs-list a{color:var(--hs-ln);text-decoration:underline}',
    '#hs-tip .hs-nav{display:flex;gap:6px;justify-content:flex-end;margin-top:6px}',
    '#hs-tip .hs-nav button,#hs-list button{min-height:32px;min-width:32px;padding:0 10px;border:1px solid var(--hs-bd);border-radius:8px;background:transparent;color:var(--hs-fg)}',
    '#hs-list{left:12px;bottom:60px;width:min(340px,calc(100vw - 24px));max-height:min(60vh,520px);overflow:auto;padding:8px}',
    '#hs-list ol{margin:0;padding:0 0 0 4px;list-style:none}',
    '#hs-list li button{display:flex;width:100%;gap:8px;align-items:center;text-align:left;border:0;margin:1px 0}',
    '#hs-list li button:hover{background:rgba(127,127,127,.15)}'
  ].join('\n');

  var ui = doc.createElement('div'); ui.id = 'hs-ui';
  ui.innerHTML = '<style>' + CSS + '</style><div id="hs-layer" hidden></div><div id="hs-tip" role="tooltip" hidden></div>' +
    '<div id="hs-list" role="dialog" aria-label="Элементы экрана" hidden></div>' +
    '<div id="hs-fab"><button type="button" id="hs-toggle" aria-pressed="false" title="Подсветить элементы макета (Esc — выключить)">Подсказки · ' + ITEMS.length + '</button>' +
    '<button type="button" id="hs-show-list" hidden>Список</button></div>';
  (doc.body || root).appendChild(ui);
  var layer = ui.querySelector('#hs-layer'), tip = ui.querySelector('#hs-tip'), list = ui.querySelector('#hs-list');
  var btn = ui.querySelector('#hs-toggle'), btnList = ui.querySelector('#hs-show-list');
  if (automated()) ui.querySelector('#hs-fab').hidden = true;
  var ON = false, PIN = null;

  function rectOf(it) {
    var x1 = Infinity, y1 = Infinity, x2 = -Infinity, y2 = -Infinity;
    [it.el].concat(it.parts).forEach(function (e) {
      var r = e.getBoundingClientRect(); if (!r.width && !r.height) return;
      x1 = Math.min(x1, r.left); y1 = Math.min(y1, r.top); x2 = Math.max(x2, r.right); y2 = Math.max(y2, r.bottom);
    });
    return x1 === Infinity ? null : { left: x1, top: y1, width: x2 - x1, height: y2 - y1 };
  }
  function body(it) {
    var a = [];
    it.p.forEach(function (p) { a.push('<a href="' + esc(STRAT) + '#p/' + esc(p) + '" target="_blank" rel="noopener">' + esc(p) + ' ↗</a>'); });
    it.sec.forEach(function (n) { a.push('<a href="' + esc(STRAT) + '#s-' + esc(n) + '" target="_blank" rel="noopener" title="' + esc(SECT[n] || '') + '">раздел ' + esc(n) + ' ↗</a>'); });
    return '<b>' + it.n + '. ' + esc(it.title) + '</b>' + (it.what ? '<p><span class="hs-k">Что это:</span> ' + esc(it.what) + '</p>' : '') +
      (it.why ? '<p><span class="hs-k">Для чего:</span> ' + esc(it.why) + '</p>' : '') + (a.length ? '<p>' + a.join(' · ') + '</p>' : '');
  }
  function place(it) {
    var r = rectOf(it); if (!r) return;
    tip.hidden = false;
    var w = tip.offsetWidth, h = tip.offsetHeight, vw = root.clientWidth, vh = root.clientHeight;
    var x = Math.min(Math.max(8, r.left), vw - w - 8), y = r.top + r.height + 8;
    if (y + h > vh - 8) y = Math.max(8, r.top - h - 8);
    tip.style.left = x + 'px'; tip.style.top = y + 'px';
  }
  function show(it, pin) {
    PIN = pin ? it : PIN;
    tip.className = pin ? 'hs-pin' : '';
    tip.innerHTML = body(it) + (pin ? '<div class="hs-nav"><button type="button" data-go="-1" aria-label="Предыдущий">‹</button><button type="button" data-go="1" aria-label="Следующий">›</button><button type="button" data-go="0" aria-label="Закрыть">✕</button></div>' : '');
    all('.hs-box', layer).forEach(function (b) { b.classList.toggle('hs-on', b.getAttribute('data-id') === it.id); });
    place(it);
  }
  function hide() { if (PIN) return; tip.hidden = true; all('.hs-box', layer).forEach(function (b) { b.classList.remove('hs-on'); }); }
  function draw() {
    if (!ON) return;
    layer.innerHTML = '';
    ITEMS.forEach(function (it) {
      var r = rectOf(it); if (!r) return;
      var b = doc.createElement('div'); b.className = 'hs-box'; b.setAttribute('data-id', it.id); b.tabIndex = 0;
      b.setAttribute('role', 'button'); b.setAttribute('aria-label', it.n + '. ' + it.title);
      b.style.cssText = 'left:' + (r.left - 3) + 'px;top:' + (r.top - 3) + 'px;width:' + (r.width + 6) + 'px;height:' + (r.height + 6) + 'px';
      var n = doc.createElement('div'); n.className = 'hs-num'; n.textContent = it.n; n.setAttribute('data-id', it.id);
      n.style.left = Math.max(2, r.left - 10) + 'px'; n.style.top = Math.max(2, r.top - 10) + 'px';
      layer.appendChild(b); layer.appendChild(n);
    });
    if (PIN) show(PIN, true);
  }
  function byId(id) { return BYID[id] && BYID[id].el ? BYID[id] : null; }
  function on() { ON = true; layer.hidden = false; btn.setAttribute('aria-pressed', 'true'); btnList.hidden = false; root.setAttribute('data-hs-on', ''); draw(); }
  function off() { ON = false; PIN = null; layer.hidden = true; tip.hidden = true; list.hidden = true; btn.setAttribute('aria-pressed', 'false'); btnList.hidden = true; root.removeAttribute('data-hs-on'); }
  function pin(id) { var it = byId(id); if (!it) return false; if (!ON) on(); it.el.scrollIntoView({ block: 'center' }); draw(); show(it, true); return true; }

  btn.addEventListener('click', function () { ON ? off() : on(); });
  btnList.addEventListener('click', function () {
    list.hidden = !list.hidden;
    if (!list.hidden) list.innerHTML = '<ol>' + ITEMS.map(function (it) { return '<li><button type="button" data-pin="' + esc(it.id) + '"><b>' + it.n + '.</b> ' + esc(it.title) + '</button></li>'; }).join('') + '</ol>';
  });
  list.addEventListener('click', function (e) { var b = e.target.closest('[data-pin]'); if (b) { list.hidden = true; pin(b.getAttribute('data-pin')); } });
  layer.addEventListener('mouseover', function (e) { var b = e.target.closest('[data-id]'); if (b && !PIN) show(byId(b.getAttribute('data-id')), false); });
  layer.addEventListener('mouseout', function () { hide(); });
  layer.addEventListener('focusin', function (e) { var b = e.target.closest('[data-id]'); if (b && !PIN) show(byId(b.getAttribute('data-id')), false); });
  layer.addEventListener('click', function (e) { var b = e.target.closest('[data-id]'); if (b) show(byId(b.getAttribute('data-id')), true); });
  layer.addEventListener('keydown', function (e) { if (e.key === 'Enter' || e.key === ' ') { var b = e.target.closest('[data-id]'); if (b) { e.preventDefault(); show(byId(b.getAttribute('data-id')), true); } } });
  tip.addEventListener('click', function (e) {
    var g = e.target.closest('[data-go]'); if (!g || !PIN) return;
    var d = +g.getAttribute('data-go');
    if (!d) { PIN = null; hide(); return; }
    pin(ITEMS[(PIN.n - 1 + d + ITEMS.length) % ITEMS.length].id);
  });
  doc.addEventListener('keydown', function (e) { if (e.key === 'Escape' && ON) { if (PIN) { PIN = null; hide(); } else off(); } });
  window.addEventListener('scroll', function () { if (ON) draw(); }, { passive: true });
  window.addEventListener('resize', function () { if (ON) draw(); });

  function fromHash() {
    var m = /^#hs(?:=(.+))?$/.exec(location.hash || '');
    if (!m) return;
    if (m[1]) pin(decodeURIComponent(m[1])); else on();
  }
  window.addEventListener('hashchange', fromHash);
  fromHash();
  window.PS_HS = { items: ITEMS.map(function (it) { return { id: it.id, n: it.n, title: it.title, what: it.what, why: it.why, p: it.p, sec: it.sec }; }),
    on: on, off: off, pin: pin, toggle: function () { ON ? off() : on(); }, isOn: function () { return ON; } };
})();
