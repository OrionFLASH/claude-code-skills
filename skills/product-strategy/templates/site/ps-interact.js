/* ps-interact.js — слой интерактивности графиков и блок-схем страницы стратегии (product-strategy 1.5, FB-035).
   Встраивается build_html.py в общий скрипт страницы сразу после app.js (site: assets/app.js; single/lite: тот же
   встроенный скрипт, хеш CSP считается по всему тексту) — постобработка и обёртки сборки больше не нужны.
   Что даёт (чистый JS, без сети, по file:// в Safari 17+, Chromium, Firefox):
   - у каждого графика (figure.ps-ichart > .ps-svg) и схемы (.flowsvg) — обёртка .psi-wrap с видимой кнопкой «🔍 Увеличить»
     (разметку пишет сборщик; для старых страниц слой дорисует её сам), курсор zoom-in на фоне, плашка-подсказка;
   - просмотр на весь экран с ЖИВОЙ копией SVG: −/+/Сброс/Панель/✕; колесо, щипок трекпада (Safari gesture*, Chrome/Firefox
     Ctrl+колесо), щипок и двойное касание на телефоне, перетаскивание, +/−/0, стрелки; Esc закрывает, фокус не выходит из окна
     и возвращается на кнопку;
   - в просмотре каждый элемент графика и блок схемы наводится (подсказка, контур) и нажимается (панель: графики — «Что это /
     Что значит / Что делать / Метрики / Связанные предложения / Где на странице», схемы — «Что это / Как сейчас / Что сделать /
     Как измерять / Связанные предложения»); P-id открывают карточку ПОВЕРХ просмотра; ←/→ и «Пред./След.» — соседний элемент;
     без выбора — «Вывод», «Как читать» и список всех элементов (для мелких и перекрытых);
   - на странице у блоков схем и элементов графиков — мгновенная подсказка и контур при наведении и фокусе с клавиатуры;
   - строка «Графики и схемы кликабельны…» вверху страницы и в каждом разделе с графиками (пишет сборщик; запасной вариант — здесь).
   Данные: window.PS.data (app.js) — d-flows, d-registry, d-meta; пояснения графиков — PS_ROUTER.meta (assets/charts-*.js или d-charts).
   Повторный запуск ничего не делает (window.PSI). Расширение может заменить просмотр: PS.replace('viewer') — тогда кнопки
   и клики слоя не срабатывают (слой расширения обрабатывает их сам). API — window.PSI. */
(function () {
  'use strict';
  if (window.PSI) return;
  var doc = document, root = doc.documentElement;
  var PS = window.PS || {};
  function J(id) { if (PS.data) return PS.data(id); var D = window.PS_DATA; return D && Object.prototype.hasOwnProperty.call(D, id) ? D[id] : null; }
  var NODES = J('d-flows') || {};
  var REG = J('d-registry') || [];
  var LABELS = ((J('d-meta') || {}).labels) || {};
  var BYID = {}; REG.forEach(function (r) { if (r && r.id) BYID[r.id] = r; });
  var SVGNS = 'http://www.w3.org/2000/svg';
  var NARROW = window.matchMedia ? window.matchMedia('(max-width: 699px)') : { matches: false };
  var KIND_T = { stage: 'этап', point: 'точка', bar: 'столбец', node: 'узел', cell: 'ячейка', event: 'событие', link: 'связь', legend: 'легенда',
    axis: 'ось', area: 'область', line: 'линия', row: 'строка', column: 'столбец', shape: 'фигура' };
  var HINT = 'Графики и схемы кликабельны: наведите — подсказка, нажмите — подробности, 🔍 — увеличить.';

  function $(s, r) { return (r || doc).querySelector(s); }
  function $$(s, r) { return Array.prototype.slice.call((r || doc).querySelectorAll(s)); }
  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); }
  function txt(v) { if (v == null) return ''; if (Array.isArray(v)) return v.map(txt).join('; '); if (typeof v === 'object') return v.what || v.text || v.label || JSON.stringify(v); return String(v); }
  function clamp(v, a, b) { return Math.max(a, Math.min(b, v)); }
  function safe(name, fn) { try { return fn(); } catch (e) { if (window.console) console.error('[ps-interact] ' + name + ': ' + (e && e.message || e)); } }
  function cssq(s) { return window.CSS && CSS.escape ? CSS.escape(String(s)) : String(s).replace(/["\\\]\[]/g, '\\$&'); }
  function lab(g, v) { return (LABELS[g] && LABELS[g][v]) || (v == null ? '' : String(v)); }
  function replaced() { return !!(PS.isReplaced && PS.isReplaced('viewer')); }
  function emit(ev, arg) { if (PS.emit) safe('emit', function () { PS.emit(ev, arg); }); }
  function pidA(id) { var r = BYID[id]; return r ? '<a class="pid" href="#p=' + esc(id) + '" data-pid="' + esc(id) + '" title="' + esc(id + ' — ' + r.title) + '">' + esc(id) + '</a>' : esc(id); }
  function linkPids(s) { return esc(txt(s)).replace(/\bP\d{3}\b/g, function (id) { return BYID[id] ? pidA(id) : id; }); }
  function pidList(ids) {
    var seen = {};
    return (ids || []).filter(function (id) { if (seen[id]) return false; seen[id] = 1; return true; }).map(function (id) {
      var r = BYID[id];
      return '<li>' + pidA(id) + (r ? ' ' + esc(r.title) + (r.priority ? ' <span class="b b-' + esc(String(r.priority).replace(/[^\w-]/g, '-')) + '">' + esc(r.priority) + '</span>' : '')
        + (r.quadrant ? ' <span class="b b-' + esc(String(r.quadrant).replace(/[^\w-]/g, '-')) + '">' + esc(lab('quadrant', r.quadrant)) + '</span>' : '') : ' <span class="muted">(нет в реестре)</span>') + '</li>';
    }).join('');
  }
  function sec(title, body) { return body ? '<section><h4>' + esc(title) + '</h4>' + body + '</section>' : ''; }
  function para(s) { return s ? '<p>' + linkPids(s) + '</p>' : ''; }
  function ulist(a) { a = (a || []).filter(function (x) { return x != null && x !== ''; }); return a.length ? '<ul>' + a.map(function (x) { return '<li>' + linkPids(x) + '</li>'; }).join('') + '</ul>' : ''; }
  function firstSentence(s) { var w0 = String(s || ''), m = w0.match(/^[\s\S]*?[.!?](?=\s|$)/), w = m ? m[0] : w0; return w.length > 150 ? w.slice(0, 147) + '…' : w; }

  /* ---------- пояснения графиков (assets/charts-*.js или d-charts) ---------- */
  function chMeta(key) {
    var R = window.PS_ROUTER; if (R && R.meta) { var m = safe('meta', function () { return R.meta(key); }); if (m) return m; }
    var P = window.PS_CHARTS; return P && P[key] && P[key].meta || null;
  }
  function chEl(key, id) { var m = chMeta(key), a = (m && m.elements) || []; for (var i = 0; i < a.length; i++) if (a[i].id === id) return a[i]; return null; }

  /* ---------- геометрия: рамка элемента в координатах корневого <svg> (без учёта CSS-трансформаций) ---------- */
  function bboxInSvg(svg, el) {
    try {
      var b = el.getBBox(), m = svg.createSVGMatrix();
      for (var n = el; n && n !== svg && n.nodeType === 1; n = n.parentNode) {
        if (n.transform && n.transform.baseVal && n.transform.baseVal.numberOfItems) { var c = n.transform.baseVal.consolidate(); if (c) m = c.matrix.multiply(m); }
      }
      var xs = [], ys = [];
      [[b.x, b.y], [b.x + b.width, b.y], [b.x, b.y + b.height], [b.x + b.width, b.y + b.height]].forEach(function (p) {
        var q = svg.createSVGPoint(); q.x = p[0]; q.y = p[1]; q = q.matrixTransform(m); xs.push(q.x); ys.push(q.y);
      });
      var x0 = Math.min.apply(null, xs), y0 = Math.min.apply(null, ys);
      return { x: x0, y: y0, w: Math.max.apply(null, xs) - x0, h: Math.max.apply(null, ys) - y0 };
    } catch (e) { return null; }
  }
  function ovl(svg) {
    var g = svg.querySelector(':scope > g.psi-ovl');
    if (!g) { g = doc.createElementNS(SVGNS, 'g'); g.setAttribute('class', 'psi-ovl'); g.setAttribute('aria-hidden', 'true'); g.setAttribute('pointer-events', 'none'); svg.appendChild(g); }
    else if (g !== svg.lastElementChild) svg.appendChild(g);
    return g;
  }
  /* контур элемента: cls = psi-hov (наведение, пунктир) | psi-sel (выбран); k — масштаб толщины (1 / зум) */
  function ring(svg, el, cls, k) {
    if (!svg) return; var g = ovl(svg);
    $$('.' + cls, g).forEach(function (x) { g.removeChild(x); });
    if (!el) return;
    var b = bboxInSvg(svg, el); if (!b) return;
    k = k || 1; var pad = 4 * k, w = Math.max(b.w + 2 * pad, 10 * k), h = Math.max(b.h + 2 * pad, 10 * k);
    ['halo', 'line'].forEach(function (part) {
      var r = doc.createElementNS(SVGNS, 'rect');
      r.setAttribute('class', cls + ' ' + cls + '-' + part + ' psi-ring-' + part);
      r.setAttribute('x', b.x + b.w / 2 - w / 2); r.setAttribute('y', b.y + b.h / 2 - h / 2); r.setAttribute('width', w); r.setAttribute('height', h);
      r.setAttribute('rx', 4 * k); r.setAttribute('fill', 'none');
      r.style.strokeWidth = ((part === 'halo' ? 7 : 3) * k) + 'px';
      if (cls === 'psi-hov' && part === 'line') r.style.strokeDasharray = (6 * k) + ' ' + (4 * k);
      g.appendChild(r);
    });
  }
  function svgScaleOnPage(svg) { var vb = svg.viewBox && svg.viewBox.baseVal, r = svg.getBoundingClientRect(); return vb && vb.width && r.width ? vb.width / r.width : 1; }

  /* ---------- подсказка ---------- */
  var tip = doc.createElement('div'); tip.className = 'psi-tip'; tip.id = 'psi-tip'; tip.setAttribute('role', 'tooltip'); tip.hidden = true;
  function tipShow(html, x, y) {
    if (!html) { tip.hidden = true; return; }
    if (tip.getAttribute('data-h') !== html) { tip.innerHTML = html; tip.setAttribute('data-h', html); }
    tip.hidden = false; var w = tip.offsetWidth, h = tip.offsetHeight;
    tip.style.left = clamp(x + 14, 4, innerWidth - w - 4) + 'px';
    tip.style.top = clamp(y - h - 12 < 4 ? y + 20 : y - h - 12, 4, Math.max(4, innerHeight - h - 4)) + 'px';
  }
  function tipAtEl(html, el) { var r = el.getBoundingClientRect(); tipShow(html, r.left + Math.min(r.width / 2, 60), r.top); }
  function tipHide() { tip.hidden = true; }
  function kbFocus(el) { try { return el.matches(':focus-visible'); } catch (e) { return true; } }   /* фокус от касания/клика — без подсказки */
  function nodeTip(id, extra) {
    var n = NODES[id]; if (!n) return '';
    var w = firstSentence(n.what);
    return '<b>' + esc(n.label || id) + '</b>' + (w ? '<span>' + esc(w) + '</span>' : '') + '<em>' + esc(extra) + '</em>';
  }
  function chartTip(key, id, extra) {
    var e = chEl(key, id); if (!e) return '';
    var w = firstSentence(e.summary);
    return '<b>' + esc(e.title || id) + '</b>' + (w ? '<span>' + esc(w) + '</span>' : KIND_T[e.kind] ? '<span>' + esc(KIND_T[e.kind]) + '</span>' : '') + '<em>' + esc(extra) + '</em>';
  }

  /* ---------- обёртки на странице (сборщик пишет их в разметку; здесь — запасной вариант для старых страниц) ---------- */
  function boxTitle(box) {
    if (box.classList.contains('flowsvg')) return box.getAttribute('data-cap') || 'Схема';
    var fig = box.closest('figure.ps-ichart'), b = fig && fig.querySelector('figcaption b');
    return (b && b.textContent) || ((chMeta(fig && fig.getAttribute('data-chart')) || {}).title) || 'График';
  }
  function fixFlowSvg(box) {
    var svg = box.querySelector('svg'); if (!svg || svg.getAttribute('data-psi-a11y')) return;
    svg.setAttribute('data-psi-a11y', '1');
    if (svg.getAttribute('role') === 'img' || !svg.getAttribute('role')) svg.setAttribute('role', 'group');   /* role=img прячет блоки-кнопки от VoiceOver */
    var lb = (svg.getAttribute('aria-labelledby') || '').split(/\s+/).filter(function (id) { return id && doc.getElementById(id); });
    if (lb.length) svg.setAttribute('aria-labelledby', lb.join(' ')); else { svg.removeAttribute('aria-labelledby'); if (!svg.getAttribute('aria-label')) svg.setAttribute('aria-label', boxTitle(box)); }
    $$('.fnode[data-node]', svg).forEach(function (g) {
      var ti = null; for (var c = g.firstElementChild; c; c = c.nextElementSibling) if (c.localName === 'title') { ti = c; break; }
      var n = NODES[g.getAttribute('data-node')], label = (n && n.label) || (ti && ti.textContent) || '';
      if (label && !g.getAttribute('aria-label')) g.setAttribute('aria-label', label + ' — открыть расшифровку');
      if (ti) { g.setAttribute('data-psi-title', ti.textContent); g.removeChild(ti); }   /* системная подсказка <title> → мгновенная .psi-tip (без двойных подсказок) */
    });
  }
  function enhance(box) {
    var kind = box.classList.contains('flowsvg') ? 'flow' : 'chart';
    var wrap = box.parentNode;
    if (!wrap || !wrap.classList || !wrap.classList.contains('psi-wrap')) {
      wrap = doc.createElement('div'); wrap.className = 'psi-wrap psi-' + kind;
      var fa = doc.activeElement, had = fa && fa !== doc.body && box.contains(fa);   /* перенос узла снимает фокус внутри него */
      box.parentNode.insertBefore(wrap, box); wrap.appendChild(box);
      if (had && fa.focus) { try { fa.focus({ preventScroll: true }); } catch (e) { fa.focus(); } }
    }
    if (kind === 'flow') fixFlowSvg(box);
    if (!wrap.querySelector(':scope > .psi-zoom')) {
      var t = boxTitle(box), b = doc.createElement('button');
      b.type = 'button'; b.className = 'psi-zoom'; b.setAttribute('aria-label', 'Увеличить ' + (kind === 'flow' ? 'схему' : 'график') + ' «' + t + '» и открыть подробности');
      b.title = 'Открыть крупно: масштаб, подсказки и подробности по каждому элементу';
      b.innerHTML = '<span aria-hidden="true">🔍</span> Увеличить';
      wrap.appendChild(b);
      var h = doc.createElement('span'); h.className = 'psi-cue'; h.setAttribute('aria-hidden', 'true');
      h.textContent = kind === 'flow' ? 'Наведите на блок — подсказка · нажмите — расшифровка · фон — увеличить' : 'Наведите на элемент — подсказка · нажмите — подробности · фон — увеличить';
      wrap.appendChild(h);
    }
    return wrap;
  }
  function addHints() {
    var main = $('#main') || $('main'); if (!main) return;
    if (!$('.psi-hint[data-psi-top]') && $('.psi-wrap', main)) {
      var top = $('#top', main) || main.firstElementChild, p = doc.createElement('p');
      p.className = 'psi-hint'; p.setAttribute('data-psi-top', '1'); p.innerHTML = '<span aria-hidden="true">👆</span> ' + esc(HINT);
      var h1 = top && top.querySelector('h1');
      if (h1 && h1.parentNode) h1.parentNode.insertBefore(p, h1.nextSibling); else main.insertBefore(p, main.firstChild);
    }
    $$('section[id]', main).forEach(function (s) {
      if (s.id === 'top' || $(':scope > .psi-hint', s) || !$('.psi-wrap', s)) return;
      var p = doc.createElement('p'); p.className = 'psi-hint'; p.innerHTML = '<span aria-hidden="true">👆</span> ' + esc(HINT);
      var h2 = $(':scope > h2', s); if (h2) s.insertBefore(p, h2.nextSibling); else s.insertBefore(p, s.firstChild);
    });
  }

  /* ---------- просмотр ---------- */
  var LB = null, Z = { s: 1, x: 0, y: 0, W: 0, H: 0, fit: 1, atFit: true }, CUR = { wrap: null, kind: '', key: '', svg: null, ids: [], sel: null, opener: null, hov: null };
  function build() {
    if (LB) return LB;
    LB = doc.createElement('div'); LB.id = 'psi-lb'; LB.className = 'psi-lb'; LB.hidden = true;
    LB.setAttribute('role', 'dialog'); LB.setAttribute('aria-modal', 'true'); LB.setAttribute('aria-labelledby', 'psi-title');
    LB.innerHTML = '<div class="psi-bar"><b id="psi-title" class="psi-title"></b><span class="psi-tools">'
      + '<button type="button" data-psi-z="out" aria-label="Уменьшить (−)" title="Уменьшить (−)">−</button>'
      + '<span class="psi-pct" aria-live="polite">100 %</span>'
      + '<button type="button" data-psi-z="in" aria-label="Увеличить (+)" title="Увеличить (+)">+</button>'
      + '<button type="button" data-psi-z="reset" title="Вписать в экран (0)">Сброс</button>'
      + '<button type="button" data-psi-panel aria-pressed="true" title="Показать или скрыть панель подробностей">Панель</button>'
      + '<button type="button" data-psi-close class="psi-close" aria-label="Закрыть (Esc)" title="Закрыть (Esc)">✕ <span class="psi-close-t">Закрыть</span></button>'
      + '</span></div><div class="psi-main"><div class="psi-stage" tabindex="0" aria-label="Область просмотра: колесо или щипок — масштаб, перетаскивание — сдвиг, стрелки — сдвиг">'
      + '<div class="psi-canvas"></div><p class="psi-help">Колесо или щипок — масштаб · перетаскивание — сдвиг · двойной щелчок — ×2,5 · нажмите на элемент — подробности · Esc — закрыть</p></div>'
      + '<aside class="psi-panel" aria-label="Подробности"><div class="psi-ph"><button type="button" class="psi-grip" aria-expanded="true" aria-controls="psi-pb">'
      + '<span class="psi-kicker"></span><span class="psi-ptitle"></span><span class="psi-chev" aria-hidden="true">▾</span></button></div>'
      + '<div class="psi-pb" id="psi-pb" tabindex="-1"></div><div class="psi-pnav"><button type="button" data-psi-step="-1" aria-label="Предыдущий элемент (←)">← Пред.</button><span class="psi-pos"></span>'
      + '<button type="button" data-psi-step="1" aria-label="Следующий элемент (→)">След. →</button></div></aside></div>';
    doc.body.appendChild(LB);
    var stage = $('.psi-stage', LB);
    $$('[data-psi-z]', LB).forEach(function (b) { b.addEventListener('click', function () { var z = b.getAttribute('data-psi-z'); if (z === 'reset') fit(); else zoomStep(z === 'in' ? 1 : -1); }); });
    $('[data-psi-close]', LB).addEventListener('click', function () { close(); });
    $('[data-psi-panel]', LB).addEventListener('click', function () { setPanel(LB.classList.contains('psi-nopanel')); });
    $('.psi-grip', LB).addEventListener('click', function () { if (NARROW.matches) setSheet(!LB.classList.contains('psi-sheet-open')); });
    $$('[data-psi-step]', LB).forEach(function (b) { b.addEventListener('click', function () { step(+b.getAttribute('data-psi-step')); }); });
    $('.psi-pb', LB).addEventListener('click', panelClick);
    bindStage(stage);
    return LB;
  }
  function isOpen() { return !!(LB && !LB.hidden); }
  function setPanel(on) {
    LB.classList.toggle('psi-nopanel', !on); $('[data-psi-panel]', LB).setAttribute('aria-pressed', String(on));
    try { localStorage.setItem('psi-panel', on ? '1' : '0'); } catch (e) { /* приватный режим */ }
    if (Z.atFit) requestAnimationFrame(fit);
  }
  function setSheet(on) { LB.classList.toggle('psi-sheet-open', on); $('.psi-grip', LB).setAttribute('aria-expanded', String(on)); }
  function stageEl() { return $('.psi-stage', LB); }
  function apply() {
    var c = $('.psi-canvas', LB);
    c.style.transform = 'translate(' + Z.x.toFixed(1) + 'px,' + Z.y.toFixed(1) + 'px) scale(' + Z.s.toFixed(4) + ')';
    $('.psi-pct', LB).textContent = Math.round(Z.s / Z.fit * 100) + ' %';
    stageEl().setAttribute('data-scale', Z.s.toFixed(4));
    if (CUR.svg) {   /* толщина контуров на экране постоянна */
      var k = 1 / Z.s;
      $$('.psi-ovl rect', CUR.svg).forEach(function (r) { var halo = /halo/.test(r.getAttribute('class')); r.style.strokeWidth = ((halo ? 7 : 3) * k) + 'px'; });
    }
  }
  function visibleArea() {
    var r = stageEl().getBoundingClientRect(), bottom = r.bottom;
    if (NARROW.matches && !LB.classList.contains('psi-nopanel')) { var p = $('.psi-panel', LB).getBoundingClientRect(); if (p.top > r.top && p.top < r.bottom) bottom = p.top; }
    return { left: r.left, top: r.top, width: r.width, height: Math.max(80, bottom - r.top), full: r };
  }
  function fit() {
    if (!CUR.svg) return; var a = visibleArea(), pad = NARROW.matches ? 8 : 20;
    Z.fit = Math.max(0.02, Math.min((a.width - 2 * pad) / Z.W, (a.height - 2 * pad) / Z.H));
    Z.s = Z.fit; Z.x = (a.width - Z.W * Z.s) / 2; Z.y = (a.height - Z.H * Z.s) / 2; Z.atFit = true; apply();
  }
  function minS() { return Z.fit * 0.5; }
  function maxS() { return Math.max(Z.fit * 12, 4); }
  function zoomAt(f, cx, cy) {
    var ns = clamp(Z.s * f, minS(), maxS()); f = ns / Z.s; if (Math.abs(f - 1) < 1e-4) return;
    Z.x = cx - (cx - Z.x) * f; Z.y = cy - (cy - Z.y) * f; Z.s = ns; Z.atFit = false; apply();
  }
  function zoomStep(d) { var a = visibleArea(); zoomAt(d > 0 ? 1.4 : 1 / 1.4, a.width / 2, a.height / 2); }
  function panBy(dx, dy) { Z.x += dx; Z.y += dy; Z.atFit = false; apply(); }

  function uniqIds(svg, suf) {
    var map = {}, all = [svg].concat($$('*', svg));
    all.forEach(function (e) { if (e.id) { map[e.id] = e.id + suf; e.id = e.id + suf; } });
    if (!Object.keys(map).length) return;
    var attrs = ['fill', 'stroke', 'marker-start', 'marker-mid', 'marker-end', 'clip-path', 'mask', 'filter', 'href', 'xlink:href', 'style', 'aria-labelledby', 'aria-describedby'];
    all.forEach(function (e) {
      attrs.forEach(function (a) {
        var v = e.getAttribute(a); if (!v) return; var nv = v;
        if (a.indexOf('aria-') === 0) nv = v.split(/\s+/).map(function (id) { return map[id] || id; }).join(' ');
        else if ((a === 'href' || a === 'xlink:href') && v.charAt(0) === '#' && map[v.slice(1)]) nv = '#' + map[v.slice(1)];
        else nv = v.replace(/url\(\s*['"]?#([^)'"]+)['"]?\s*\)/g, function (m, id) { return map[id] ? 'url(#' + map[id] + ')' : m; });
        if (nv !== v) e.setAttribute(a, nv);
      });
    });
  }
  /* <style> схемы изолирован сборщиком селектором «#<область> …»: у копии другая область — переписать селекторы */
  function rescopeStyles(c, scopeId) {
    if (!scopeId) return;
    $$('style', c).forEach(function (st) { st.textContent = st.textContent.split('#' + scopeId + ' ').join('.psi-canvas ').split('#' + scopeId).join('.psi-canvas'); });
  }
  function elIdOf(el) { return el ? (el.getAttribute('data-ps-ref') || el.getAttribute('data-ps-el') || el.getAttribute('data-node')) : null; }
  function targetEl(t) { return t && t.closest ? t.closest('.psi-canvas .ps-el, .psi-canvas [data-ps-ref], .psi-canvas .fnode[data-node]') : null; }
  function findEl(id) {
    if (!CUR.svg || !id) return null;
    return CUR.kind === 'flow' ? CUR.svg.querySelector('.fnode[data-node="' + cssq(id) + '"]') : CUR.svg.querySelector('[data-ps-el="' + cssq(id) + '"]');
  }
  function srcSvg(wrap) { var box = wrap.querySelector('.ps-svg, .flowsvg'); return box && (box.querySelector('svg[data-ps-chart]') || (box.classList.contains('flowsvg') && box.querySelector('svg'))); }

  function open(wrap, opts) {
    opts = opts || {}; build();
    var kind = wrap.classList.contains('psi-flow') ? 'flow' : 'chart', box = wrap.querySelector('.ps-svg, .flowsvg');
    var fig = wrap.closest('figure.ps-ichart'), flow = wrap.closest('.flow');
    var key = kind === 'flow' ? ((flow && flow.getAttribute('data-flow')) || (box.getAttribute('data-imgkey') || '').replace(/^flow-/, '')) : (fig && fig.getAttribute('data-chart')) || '';
    var svg = srcSvg(wrap);
    if (!isOpen()) { CUR.opener = opts.opener || doc.activeElement; }
    CUR.wrap = wrap; CUR.kind = kind; CUR.key = key; CUR.sel = null; CUR.hov = null;
    LB.hidden = false; LB.setAttribute('data-kind', kind); LB.setAttribute('data-key', key);
    root.classList.add('psi-locked'); tipHide();
    var cpTip = $('#cp-tip'); if (cpTip) cpTip.hidden = true;
    $('#psi-title', LB).textContent = boxTitle(box);
    var pref = '1'; try { pref = localStorage.getItem('psi-panel') || '1'; } catch (e) { /* ignore */ }
    LB.classList.toggle('psi-nopanel', pref === '0' && !NARROW.matches); $('[data-psi-panel]', LB).setAttribute('aria-pressed', String(!LB.classList.contains('psi-nopanel')));
    setSheet(false);
    var canvas = $('.psi-canvas', LB); canvas.innerHTML = '';
    if (!svg) {        /* скрипт группы графиков ещё не подгружен: подгрузить все группы и открыть ещё раз */
      CUR.svg = null; canvas.innerHTML = '<p class="psi-wait">График загружается…</p>'; renderOverview();
      var R = window.PS_ROUTER;
      if (R && R.loadAll && !opts.retry) R.loadAll(function () { if (isOpen() && CUR.wrap === wrap) open(wrap, { retry: true, opener: CUR.opener, select: opts.select }); });
      else canvas.innerHTML = '<p class="psi-wait">График не загрузился — обновите страницу.</p>';
      focusFirst(); return;
    }
    var c = svg.cloneNode(true);
    $$('.ps-ovl, .psi-ovl', c).forEach(function (x) { x.parentNode.removeChild(x); });
    c.classList.remove('ps-hl-on'); $$('.ps-hl, .ps-on, .on', c).forEach(function (x) { x.classList.remove('ps-hl', 'ps-on', 'on'); });
    $$('title', c).forEach(function (t) { if (t.parentNode !== c) t.parentNode.removeChild(t); });
    if (kind === 'flow') rescopeStyles(c, box.id);
    uniqIds(c, '-psz');
    var vb = (svg.getAttribute('viewBox') || '').split(/[\s,]+/).map(Number);
    var W = vb.length === 4 && vb[2] > 0 ? vb[2] : (svg.getBoundingClientRect().width || 800), H = vb.length === 4 && vb[3] > 0 ? vb[3] : (svg.getBoundingClientRect().height || 600);
    c.setAttribute('width', W); c.setAttribute('height', H); c.removeAttribute('style'); c.style.width = W + 'px'; c.style.height = H + 'px';
    c.setAttribute('role', 'group'); c.setAttribute('aria-label', boxTitle(box)); c.removeAttribute('aria-labelledby');
    c.classList.add('psi-svg');
    canvas.appendChild(c); Z.W = W; Z.H = H; CUR.svg = c;
    var els = kind === 'flow' ? $$('.fnode[data-node]', c) : $$('.ps-el[data-ps-el]', c), seen = {};
    CUR.ids = [];
    if (kind === 'chart') { var m = chMeta(key); ((m && m.elements) || []).forEach(function (e) { if (!seen[e.id] && c.querySelector('[data-ps-el="' + cssq(e.id) + '"]')) { seen[e.id] = 1; CUR.ids.push(e.id); } }); }
    els.forEach(function (g) { var id = elIdOf(g); if (id && !seen[id]) { seen[id] = 1; CUR.ids.push(id); } });
    els.forEach(function (g) { g.setAttribute('tabindex', '-1'); g.setAttribute('role', 'button'); });
    var f0 = findEl(CUR.ids[0]); if (f0) f0.setAttribute('tabindex', '0');
    renderOverview();
    requestAnimationFrame(function () { fit(); if (opts.select) select(opts.select, { reveal: true }); });
    focusFirst();
    emit('viewer:open', { kind: kind, key: key });
  }
  function focusFirst() { var b = $('[data-psi-close]', LB); try { b.focus({ preventScroll: true }); } catch (e) { b.focus(); } }
  function close() {
    if (!isOpen()) return;
    var kind = CUR.kind, key = CUR.key;
    LB.hidden = true; root.classList.remove('psi-locked'); tipHide();
    $('.psi-canvas', LB).innerHTML = ''; CUR.svg = null; CUR.sel = null; CUR.wrap = null; CUR.hov = null;
    var o = CUR.opener; CUR.opener = null;
    if (o && doc.contains(o) && o.focus) { try { o.focus({ preventScroll: true }); } catch (e) { o.focus(); } }
    emit('viewer:close', { kind: kind, key: key });
  }

  /* ---------- панель подробностей ---------- */
  function setHead(kicker, title) { $('.psi-kicker', LB).textContent = kicker; $('.psi-ptitle', LB).textContent = title; }
  function setPos() {
    var i = CUR.sel ? CUR.ids.indexOf(CUR.sel) : -1;
    $('.psi-pos', LB).textContent = CUR.ids.length ? (i >= 0 ? (i + 1) + ' из ' + CUR.ids.length : 'элементов: ' + CUR.ids.length) : '';
    $$('[data-psi-step]', LB).forEach(function (b) { b.disabled = CUR.ids.length < 2; });
  }
  function elementList() {
    if (!CUR.ids.length) return '';
    return '<details class="psi-all"' + (CUR.ids.length <= 20 ? ' open' : '') + '><summary>Все элементы (' + CUR.ids.length + ') — удобно, если элемент мелкий или перекрыт</summary><ul class="psi-chips">'
      + CUR.ids.map(function (id) {
        var t = CUR.kind === 'flow' ? ((NODES[id] || {}).label || id) : ((chEl(CUR.key, id) || {}).title || id);
        return '<li><button type="button" class="psi-chip" data-psi-sel="' + esc(id) + '">' + esc(t.length > 70 ? t.slice(0, 67) + '…' : t) + '</button></li>';
      }).join('') + '</ul></details>';
  }
  function renderOverview() {
    var box = CUR.wrap && CUR.wrap.querySelector('.ps-svg, .flowsvg'), h = '';
    if (CUR.kind === 'chart') {
      var fig = CUR.wrap.closest('figure.ps-ichart'), cap = fig && fig.querySelector('figcaption');
      var capTxt = ''; if (cap) { var cc = cap.cloneNode(true); $$('.ps-acts, .zoom, button', cc).forEach(function (x) { if (x.parentNode) x.parentNode.removeChild(x); });
        var bt = cc.querySelector('b'), lead = bt ? bt.textContent.trim() : ''; if (bt) bt.parentNode.removeChild(bt);
        capTxt = cc.textContent.replace(/\s+/g, ' ').replace(/\s*·\s*$/, '').replace(/^\s*—\s*/, '').trim();
        capTxt = lead && capTxt ? lead + '. ' + capTxt : lead || capTxt; }
      var how = fig && fig.querySelector('.ps-howto'), howH = '';
      if (how) { var hc = how.cloneNode(true); $$('p.small', hc).forEach(function (x) { x.parentNode.removeChild(x); }); howH = hc.innerHTML; }
      h += sec('Вывод', capTxt ? '<p>' + linkPids(capTxt) + '</p>' : '');
      h += sec('Как читать', howH || '<p>Наведите на точку, столбец или ячейку — появится подсказка; нажмите — здесь откроются подробности.</p>');
      setHead('График', (chMeta(CUR.key) || {}).title || boxTitle(box));
    } else {
      var d = box && box.querySelector('svg > desc'), flow = CUR.wrap.closest('.flow'), hint = flow && flow.querySelector('p.muted');
      h += sec('О схеме', d && d.textContent ? '<p>' + linkPids(d.textContent) + '</p>' : '');
      h += sec('Как читать', '<p>Прямоугольник — блок процесса или системы, стрелка — поток (данных, денег или действий пользователя); подписи на стрелках — условия перехода.</p>'
        + (hint ? '<p class="muted">' + esc(hint.textContent.replace(/⤢.*$/, '').trim()) + '</p>' : ''));
      setHead('Схема', boxTitle(box));
    }
    h += '<p class="psi-tipline">Нажмите на ' + (CUR.kind === 'flow' ? 'блок схемы' : 'точку, столбец или ячейку графика') + ' или выберите элемент в списке ниже — здесь появятся подробности: что это, что делать, метрики и связанные предложения.</p>' + elementList();
    var pb = $('.psi-pb', LB); pb.innerHTML = h; pb.scrollTop = 0; setPos();
  }
  function renderChartEl(id) {
    var e = chEl(CUR.key, id) || {}, h = '';
    var el = findEl(id); if (!e.title && el) e = { title: el.getAttribute('data-tip') || id };
    h += sec('Что это', para(e.summary));
    h += sec('Что значит', para(e.meaning));
    h += sec('Что делать', ulist(e.actions));
    if ((e.metrics || []).length) h += sec('Метрики', '<dl class="psi-mx">' + e.metrics.map(function (x) { return '<dt>' + esc(x.label) + '</dt><dd>' + esc(x.value === '' || x.value == null ? '—' : x.value) + (x.tag ? ' <span class="tag">' + esc(x.tag) + '</span>' : '') + '</dd>'; }).join('') + '</dl>');
    var pids = [], links = [];
    if (/^P\d{3}$/.test(id) && BYID[id]) pids.push(id);
    (e.links || []).forEach(function (l) { var hr = String(l.href || ''), m = hr.match(/^#p[\/=](P\d{3})$/); if (m && BYID[m[1]]) pids.push(m[1]); else if (/^#[\w\/?=&.-]+$/.test(hr)) links.push(l); });
    h += sec('Связанные предложения', pids.length ? '<ul class="psi-pids">' + pidList(pids) + '</ul>' : '');
    h += sec('Где на странице', links.length ? '<ul>' + links.map(function (l) { return '<li><a href="' + esc(l.href) + '" data-psi-nav>' + esc(l.label || l.href) + '</a></li>'; }).join('') + '</ul>' : '');
    if (!h) h = '<p class="muted">Пояснение к элементу не задано.</p>';
    setHead(KIND_T[e.kind] || 'элемент', e.title || id);
    return h;
  }
  function renderNode(id) {
    var n = NODES[id] || {}, h = '';
    h += sec('Что это', para(n.what) || '<p class="muted">не задано</p>');
    h += sec('Как сейчас', para(n.now));
    h += sec('Что сделать', ulist(n.todo) || '<p class="muted">не задано</p>');
    h += sec('Как измерять', para(n.metrics));
    h += sec('Связанные предложения', (n.proposals || []).length ? '<ul class="psi-pids">' + pidList(n.proposals) + '</ul>' : '');
    setHead('блок схемы', n.label || id);
    return h;
  }
  function select(id, o) {
    o = o || {}; if (!CUR.svg || !id) return false;
    var el = findEl(id); if (!el && CUR.ids.indexOf(id) < 0) return false;
    CUR.sel = id;
    $$('.psi-on', CUR.svg).forEach(function (x) { x.classList.remove('psi-on'); });
    CUR.svg.classList.remove('ps-hl-on'); $$('.ps-hl', CUR.svg).forEach(function (x) { x.classList.remove('ps-hl'); });
    if (el) { el.classList.add('psi-on'); ring(CUR.svg, el, 'psi-sel', 1 / Z.s); ring(CUR.svg, null, 'psi-hov'); }
    if (CUR.kind === 'chart') {
      var e = chEl(CUR.key, id), grp = (e && e.highlight) || (el && el.getAttribute('data-ps-highlight')) || '';
      if (grp) { var n = 0; $$('[data-ps-group]', CUR.svg).forEach(function (x) { if ((' ' + x.getAttribute('data-ps-group') + ' ').indexOf(' ' + grp + ' ') >= 0) { x.classList.add('ps-hl'); n++; } }); if (n) CUR.svg.classList.add('ps-hl-on'); }
    }
    var pb = $('.psi-pb', LB);
    pb.innerHTML = (CUR.kind === 'flow' ? renderNode(id) : renderChartEl(id)) + '<p class="psi-back"><button type="button" class="linkbtn" data-psi-overview>← Как читать и все элементы</button></p>';
    if (PS.linkify) safe('linkify', function () { PS.linkify(pb); });
    pb.scrollTop = 0; setPos();
    if (LB.classList.contains('psi-nopanel')) setPanel(true);
    if (NARROW.matches) { setSheet(true); o.reveal = true; }      /* нижний лист закрывает низ сцены */
    if (el) {
      $$('[tabindex="0"]', CUR.svg).forEach(function (x) { if (x !== el) x.setAttribute('tabindex', '-1'); }); el.setAttribute('tabindex', '0');
      if (o.focus) { try { el.focus({ preventScroll: true }); } catch (x) { el.focus(); } }
      if (o.reveal !== false) requestAnimationFrame(function () { reveal(el); });
    }
    emit('viewer:select', { kind: CUR.kind, key: CUR.key, id: id });
    return true;
  }
  function reveal(el) {
    if (!el || !isOpen()) return; var a = visibleArea(), r = el.getBoundingClientRect(), m = 24;
    var vx0 = a.left + m, vx1 = a.left + a.width - m, vy0 = a.top + m, vy1 = a.top + a.height - m;
    if (r.left >= vx0 && r.right <= vx1 && r.top >= vy0 && r.bottom <= vy1) return;
    panBy((a.left + a.width / 2) - (r.left + r.width / 2), (a.top + a.height / 2) - (r.top + r.height / 2));
  }
  function step(d) {
    if (!CUR.ids.length) return; var i = CUR.sel ? CUR.ids.indexOf(CUR.sel) : -1;
    var j = i < 0 ? (d > 0 ? 0 : CUR.ids.length - 1) : (i + d + CUR.ids.length) % CUR.ids.length;
    select(CUR.ids[j], { focus: CUR.svg && CUR.svg.contains(doc.activeElement), reveal: true });
  }
  function panelClick(e) {
    var t = e.target; if (!t.closest) return;
    var sb = t.closest('[data-psi-sel]'); if (sb) { e.preventDefault(); select(sb.getAttribute('data-psi-sel'), { reveal: true }); return; }
    if (t.closest('[data-psi-overview]')) { e.preventDefault(); CUR.sel = null; if (CUR.svg) { ring(CUR.svg, null, 'psi-sel'); $$('.psi-on', CUR.svg).forEach(function (x) { x.classList.remove('psi-on'); }); CUR.svg.classList.remove('ps-hl-on'); } renderOverview(); return; }
    var a = t.closest('a[href^="#"]');
    /* P-id → карточка предложения ПОВЕРХ просмотра (окно app.js, z-index ≥ 1000); прочие ссылки страницы → просмотр закрывается, переходит роутер */
    if (a && !a.hasAttribute('data-pid')) close();
  }

  /* ---------- ввод на сцене: мышь, колесо, щипок трекпада (Safari gesture*), щипок пальцами, двойное касание, клавиатура ---------- */
  function bindStage(stage) {
    var ptrs = {}, drag = null, pinch = null, moved = false, gest = null, lastTap = { t: 0, x: 0, y: 0 };
    function rel(x, y) { var r = stage.getBoundingClientRect(); return { x: x - r.left, y: y - r.top }; }
    function two() { var k = Object.keys(ptrs); return k.length >= 2 ? [ptrs[k[0]], ptrs[k[1]]] : null; }
    var lastType = 'mouse', lastDbl = 0;
    stage.addEventListener('pointerdown', function (e) {
      lastType = e.pointerType || 'mouse';
      if (e.pointerType === 'mouse' && e.button !== 0) return;
      ptrs[e.pointerId] = { x: e.clientX, y: e.clientY };
      var p = two();
      if (p) { var m = rel((p[0].x + p[1].x) / 2, (p[0].y + p[1].y) / 2); pinch = { d0: Math.max(10, Math.hypot(p[0].x - p[1].x, p[0].y - p[1].y)), s0: Z.s, x0: Z.x, y0: Z.y, mx: m.x, my: m.y }; drag = null; moved = true; }
      else { drag = { id: e.pointerId, x0: e.clientX, y0: e.clientY, tx: Z.x, ty: Z.y, on: false }; moved = false; }
    });
    stage.addEventListener('pointermove', function (e) {
      if (!ptrs[e.pointerId]) { hover(e); return; }
      ptrs[e.pointerId] = { x: e.clientX, y: e.clientY };
      if (pinch) {
        var p = two(); if (!p) return; var m = rel((p[0].x + p[1].x) / 2, (p[0].y + p[1].y) / 2);
        var ns = clamp(pinch.s0 * Math.hypot(p[0].x - p[1].x, p[0].y - p[1].y) / pinch.d0, minS(), maxS()), f = ns / pinch.s0;
        Z.s = ns; Z.x = m.x - (pinch.mx - pinch.x0) * f; Z.y = m.y - (pinch.my - pinch.y0) * f; Z.atFit = false; apply(); return;
      }
      if (drag && drag.id === e.pointerId) {
        var dx = e.clientX - drag.x0, dy = e.clientY - drag.y0;
        if (!drag.on && Math.abs(dx) + Math.abs(dy) > 5) { drag.on = true; moved = true; stage.classList.add('psi-grabbing'); tipHide(); try { stage.setPointerCapture(e.pointerId); } catch (x) { /* ignore */ } }
        if (drag.on) { Z.x = drag.tx + dx; Z.y = drag.ty + dy; Z.atFit = false; apply(); }
      }
    });
    function up(e) {
      var had = !!ptrs[e.pointerId]; delete ptrs[e.pointerId];
      if (pinch) { if (!two()) { pinch = null; var k = Object.keys(ptrs); drag = k.length ? { id: +k[0], x0: ptrs[k[0]].x, y0: ptrs[k[0]].y, tx: Z.x, ty: Z.y, on: true } : null; } return; }
      if (drag && drag.id === e.pointerId) { drag = null; stage.classList.remove('psi-grabbing'); }
      if (had && e.type === 'pointerup' && e.pointerType !== 'mouse' && !moved) {          /* двойное касание → масштаб */
        var now = Date.now();
        if (now - lastTap.t < 320 && Math.abs(e.clientX - lastTap.x) < 30 && Math.abs(e.clientY - lastTap.y) < 30) { lastTap.t = 0; dbl(e.clientX, e.clientY); }
        else lastTap = { t: now, x: e.clientX, y: e.clientY };
      }
    }
    stage.addEventListener('pointerup', up); stage.addEventListener('pointercancel', up);
    stage.addEventListener('pointerleave', function (e) { if (e.pointerType === 'mouse') { tipHide(); if (CUR.svg) ring(CUR.svg, null, 'psi-hov'); CUR.hov = null; } });
    function dbl(x, y) { lastDbl = Date.now(); var p = rel(x, y); if (Z.s > Z.fit * 1.05) fit(); else zoomAt(2.5, p.x, p.y); }
    /* двойной щелчок мышью; двойное касание — в pointerup (синтетический dblclick браузера пропускается) */
    stage.addEventListener('dblclick', function (e) { e.preventDefault(); if (lastType !== 'mouse' || Date.now() - lastDbl < 600) return; dbl(e.clientX, e.clientY); });
    stage.addEventListener('click', function (e) {
      e.stopPropagation();                               /* обработчики app.js не должны видеть клики по копии */
      if (moved) { moved = false; e.preventDefault(); return; }
      var el = targetEl(e.target); if (el) { e.preventDefault(); select(elIdOf(el), { focus: false, reveal: false }); }
    });
    stage.addEventListener('wheel', function (e) {
      e.preventDefault(); if (gest) return;
      var p = rel(e.clientX, e.clientY);
      if (!e.ctrlKey && Math.abs(e.deltaX) > Math.abs(e.deltaY)) { panBy(-e.deltaX, 0); return; }
      var k = e.deltaMode === 1 ? 0.05 : e.deltaMode === 2 ? 0.5 : 0.0022;
      zoomAt(clamp(Math.exp(-e.deltaY * k * (e.ctrlKey ? 4 : 1)), 0.5, 2), p.x, p.y);
    }, { passive: false });
    /* Safari (трекпад macOS, iOS): нестандартные gesture-события; во время щипка указателями не используются */
    stage.addEventListener('gesturestart', function (e) { e.preventDefault(); if (pinch) return; gest = { s0: Z.s }; });
    stage.addEventListener('gesturechange', function (e) {
      e.preventDefault(); if (!gest || pinch) return;
      var r = stage.getBoundingClientRect(), cx = (e.clientX != null ? e.clientX : r.left + r.width / 2) - r.left, cy = (e.clientY != null ? e.clientY : r.top + r.height / 2) - r.top;
      zoomAt(clamp(gest.s0 * e.scale, minS(), maxS()) / Z.s, cx, cy);
    });
    stage.addEventListener('gestureend', function (e) { e.preventDefault(); gest = null; });
    function hover(e) {
      if (e.pointerType === 'touch' || !CUR.svg) return;
      var el = targetEl(e.target);
      if (!el) { tipHide(); ring(CUR.svg, null, 'psi-hov'); CUR.hov = null; return; }
      var id = elIdOf(el), html = CUR.kind === 'flow' ? nodeTip(id, 'Нажмите — расшифровка справа') : (chartTip(CUR.key, id, 'Нажмите — подробности') || '<b>' + esc(el.getAttribute('data-tip') || id) + '</b>');
      tipShow(html, e.clientX, e.clientY);
      if (CUR.hov !== el) { CUR.hov = el; if (id !== CUR.sel) ring(CUR.svg, el, 'psi-hov', 1 / Z.s); else ring(CUR.svg, null, 'psi-hov'); }
    }
    stage.addEventListener('focusin', function (e) { var el = targetEl(e.target); if (el && CUR.svg && kbFocus(el)) { ring(CUR.svg, el, 'psi-hov', 1 / Z.s); var id = elIdOf(el); tipAtEl(CUR.kind === 'flow' ? nodeTip(id, 'Enter — расшифровка') : chartTip(CUR.key, id, 'Enter — подробности'), el); } });
    stage.addEventListener('focusout', function () { tipHide(); });
  }

  /* клавиатура при открытом просмотре: фаза захвата — обработчики app.js (Esc, ←/→ панели страницы) не срабатывают */
  window.addEventListener('keydown', function (e) {
    if (!isOpen()) return;
    if ($('.layer.open')) return;                       /* карточка предложения и т. п. поверх просмотра — клавиши у app.js */
    var k = e.key, a = doc.activeElement, stage = stageEl(), onEl = !!targetEl(a), inStage = stage.contains(a);
    var handled = true;
    if (k === 'Escape') close();
    else if (k === 'Tab') {
      var f = $$('button:not([disabled]), a[href], [tabindex="0"], summary', LB).filter(function (x) { return x.offsetParent !== null || x === stage || (CUR.svg && CUR.svg.contains(x)); });
      if (!f.length) return; var i = f.indexOf(a);
      if (e.shiftKey && (i <= 0)) f[f.length - 1].focus(); else if (!e.shiftKey && (i < 0 || i === f.length - 1)) f[0].focus(); else handled = false;
    }
    else if (k === '+' || k === '=') zoomStep(1);
    else if (k === '-' || k === '_') zoomStep(-1);
    else if (k === '0') fit();
    else if (onEl && (k === 'Enter' || k === ' ')) select(elIdOf(targetEl(a)), { focus: true });
    else if (onEl && (k === 'ArrowRight' || k === 'ArrowDown')) { if (CUR.sel) step(1); else moveFocus(a, 1); }
    else if (onEl && (k === 'ArrowLeft' || k === 'ArrowUp')) { if (CUR.sel) step(-1); else moveFocus(a, -1); }
    else if (inStage && !onEl && /^Arrow/.test(k)) panBy(k === 'ArrowLeft' ? 60 : k === 'ArrowRight' ? -60 : 0, k === 'ArrowUp' ? 60 : k === 'ArrowDown' ? -60 : 0);
    else if (!inStage && (k === 'ArrowRight' || k === 'ArrowLeft') && CUR.sel && !/^(INPUT|SELECT|TEXTAREA)$/.test((a && a.tagName) || '')) step(k === 'ArrowRight' ? 1 : -1);
    else handled = false;
    if (handled) { e.preventDefault(); e.stopPropagation(); }
  }, true);
  function moveFocus(a, d) {
    var id = elIdOf(targetEl(a)), i = CUR.ids.indexOf(id), n = CUR.ids.length; if (!n) return;
    var el = findEl(CUR.ids[((i < 0 ? 0 : i) + d + n) % n]); if (!el) return;
    $$('[tabindex="0"]', CUR.svg).forEach(function (x) { x.setAttribute('tabindex', '-1'); }); el.setAttribute('tabindex', '0');
    try { el.focus({ preventScroll: true }); } catch (x) { el.focus(); } reveal(el);
  }

  /* ---------- события страницы ---------- */
  /* кнопка «🔍 Увеличить», клик по фону графика/схемы; старые кнопки «⤢ увеличить» (button.lb c-*, flow-*) → тот же просмотр */
  window.addEventListener('click', function (e) {
    if (e.defaultPrevented || e.button !== 0 || replaced()) return;
    var t = e.target; if (!t || !t.closest) return;
    var b = t.closest('button.lb[data-key^="c-"], button.lb[data-key^="flow-"]');
    if (b) {
      var w = null, k = b.getAttribute('data-key');
      if (/^c-/.test(k)) { var fig = b.closest('figure.ps-ichart'); w = fig && fig.querySelector('.psi-wrap'); }
      else { var fl = b.closest('.flow'); w = fl && fl.querySelector('.psi-wrap'); }
      if (w) { e.preventDefault(); e.stopPropagation(); open(w, { opener: b }); }
      return;
    }
    var z = t.closest('.psi-zoom'); if (z) { e.preventDefault(); e.stopPropagation(); open(z.parentNode, { opener: z }); return; }
    var wrap = t.closest('.psi-wrap');
    if (wrap && !t.closest('.ps-el, [data-ps-ref], .fnode, [data-node], a, button, input, select, summary')) {
      var sel = window.getSelection && String(window.getSelection() || ''); if (sel) return;
      e.preventDefault(); open(wrap, { opener: wrap.querySelector('.psi-zoom') });
    }
  }, true);
  /* подсказка и контур на странице: блоки схем (подсказка .psi-tip) и элементы графиков (контур; подсказка — #cp-tip app.js) */
  var pageHov = null;
  function pageHover(e) {
    if (isOpen() || e.pointerType === 'touch') return;
    var t = e.target, n = t && t.closest ? t.closest('.psi-wrap .flowsvg .fnode[data-node]') : null;
    var c = !n && t && t.closest ? t.closest('.psi-wrap .ps-svg svg[data-ps-chart] .ps-el') : null;
    var el = n || c;
    if (el !== pageHov) {
      if (pageHov && pageHov.ownerSVGElement) ring(pageHov.ownerSVGElement, null, 'psi-hov');
      pageHov = el;
      if (el && el.ownerSVGElement) ring(el.ownerSVGElement, el, 'psi-hov', svgScaleOnPage(el.ownerSVGElement));
    }
    if (n) tipShow(nodeTip(n.getAttribute('data-node'), 'Нажмите — расшифровка'), e.clientX, e.clientY);
    else if (!tip.hidden) tipHide();
  }
  doc.addEventListener('pointerover', pageHover, { passive: true });
  doc.addEventListener('pointermove', pageHover, { passive: true });
  window.addEventListener('scroll', function () { if (!isOpen() && !tip.hidden) tipHide(); }, { passive: true });
  doc.addEventListener('focusin', function (e) {
    var n = e.target && e.target.matches && e.target.matches('.psi-wrap .flowsvg .fnode[data-node]') ? e.target : null;
    if (n && !isOpen() && kbFocus(n)) { ring(n.ownerSVGElement, n, 'psi-hov', svgScaleOnPage(n.ownerSVGElement)); tipAtEl(nodeTip(n.getAttribute('data-node'), 'Enter — расшифровка'), n); }
  });
  doc.addEventListener('focusout', function (e) {
    var n = e.target && e.target.matches && e.target.matches('.psi-wrap .flowsvg .fnode[data-node]') ? e.target : null;
    if (n && !isOpen()) { ring(n.ownerSVGElement, null, 'psi-hov'); tipHide(); }
  });
  window.addEventListener('resize', function () { if (isOpen() && Z.atFit) fit(); });
  if (NARROW.addEventListener) NARROW.addEventListener('change', function () { if (isOpen()) { setSheet(false); requestAnimationFrame(fit); } });
  window.addEventListener('beforeprint', function () { close(); });

  function wrapOf(target) {
    if (typeof target !== 'string') return target;
    var fig = $('figure.ps-ichart.ps-primary[data-chart="' + cssq(target) + '"] .psi-wrap') || $('figure.ps-ichart[data-chart="' + cssq(target) + '"] .psi-wrap');
    if (fig) return fig;
    var fl = $('#flows .flow[data-flow="' + cssq(target) + '"] .psi-wrap') || $('.flow[data-flow="' + cssq(target) + '"] .psi-wrap');
    if (fl) return fl;
    var box = $('.flowsvg[data-imgkey="flow-' + cssq(target) + '"]');
    return box ? box.parentNode : null;
  }
  function init() {
    doc.body.appendChild(tip);
    $$('figure.ps-ichart .ps-svg, .flowsvg').forEach(function (box) { safe('enhance', function () { enhance(box); }); });
    safe('hints', addHints);
    root.classList.add('psi-ready');
  }
  window.PSI = {
    version: '1.5', open: function (target, sel) {
      var w = wrapOf(target);
      if (w && w.classList && w.classList.contains('psi-wrap')) { open(w, { select: sel }); return true; } return false;
    },
    close: close, select: function (id) { return select(id, { reveal: true }); }, fit: function () { fit(); }, zoom: zoomStep, isOpen: isOpen,
    state: function () { return { open: isOpen(), kind: CUR.kind, key: CUR.key, scale: Z.s, fit: Z.fit, x: Z.x, y: Z.y, sel: CUR.sel, ids: CUR.ids.slice() }; }
  };
  /* слой идёт в том же скрипте сразу после app.js: DOM готов — обёртки на месте до глубокой ссылки #chart/… и ленивых графиков */
  if (doc.body && (doc.getElementById('main') || doc.readyState !== 'loading')) init(); else doc.addEventListener('DOMContentLoaded', init);
})();
