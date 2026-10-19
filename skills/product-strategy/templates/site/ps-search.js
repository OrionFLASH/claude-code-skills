/* ps-search.js — сквозной поиск по странице стратегии (product-strategy 1.5; SM, раздел 8). Встраивается build_html.py после
   ps-interact.js. Открытие: кнопка «Поиск по странице» в меню разделов и в мобильной шапке, клавиши «/» и Ctrl/Cmd+K, ссылка #q=<текст>.
   Индекс строится при первом открытии: текст разделов страницы (абзацы, пункты, строки таблиц, подписи, план, Kanban, макеты, модель,
   рынок, источники) + данные (реестр: название, описание, обоснование, шаги, KPI, доказательства, теги; конкуренты; блоки схем; задачи
   Ганта и карточки Kanban; пояснения графиков; глоссарий; прочие исследования research/*.md — блок d-docs, если сборщик его положил).
   Совпадения: начало слова («калькул» → «калькулятор»), формы слова («цена» → «цены», «ценой», но не «ценность»), «фраза в кавычках»,
   все слова в блоке (в любом порядке) или «любое из слов», флажок «внутри слова» — подстрока; регистр и е/ё не важны.
   Фильтры по виду блока, подсветка совпадений в выдаче и на странице после перехода (mark.pss-hit), ↑/↓ и Enter в выдаче.
   Без сети, по file://. Расширение может заменить поиск: PS.replace('search'). API — window.PS_SEARCH. */
(function () {
  'use strict';
  if (window.PS_SEARCH) return;
  var doc = document, PS = window.PS || {};
  function J(id) { if (PS.data) return PS.data(id); var D = window.PS_DATA; return D && Object.prototype.hasOwnProperty.call(D, id) ? D[id] : null; }
  function $(s, r) { return (r || doc).querySelector(s); }
  function $$(s, r) { return Array.prototype.slice.call((r || doc).querySelectorAll(s)); }
  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); }
  function safe(name, fn) { try { return fn(); } catch (e) { if (window.console) console.error('[ps-search] ' + name + ': ' + (e && e.message || e)); } }
  function txt(v) { if (v == null) return ''; if (Array.isArray(v)) return v.map(txt).join(' · '); if (typeof v === 'object') return Object.keys(v).map(function (k) { return txt(v[k]); }).filter(Boolean).join(' · '); return String(v); }
  function replaced() { return !!(PS.isReplaced && PS.isReplaced('search')); }

  /* нормализация без изменения длины: регистр, ё → е, пробельные → ' ' (позиции совпадают с исходным текстом) */
  function norm(s) {
    s = String(s == null ? '' : s);
    var l = s.toLowerCase();
    if (l.length === s.length) return l.replace(/ё/g, 'е').replace(/\s/g, ' ');
    var o = ''; for (var i = 0; i < s.length; i++) { var c = s.charAt(i), x = c.toLowerCase(); if (x.length !== 1) x = c; o += x === 'ё' ? 'е' : /\s/.test(x) ? ' ' : x; } return o;
  }
  var WORD = /[0-9a-zа-яґєіїўәөүңһ]+/g;
  /* основа слова: отрезать одно типичное окончание (не стемминг; «цена/цены/ценой» сходятся, «ценность» — нет) */
  var ENDS = ['иями', 'ями', 'ами', 'иях', 'ией', 'ого', 'его', 'ому', 'ему', 'ыми', 'ими', 'ешь', 'ишь', 'ете', 'ите', 'ает', 'яет', 'ует', 'ала', 'ила', 'ыла', 'али', 'или', 'ать', 'ять', 'ить', 'еть',
    'ют', 'ут', 'ат', 'ят', 'ая', 'яя', 'ое', 'ее', 'ые', 'ие', 'ый', 'ий', 'ой', 'ей', 'ую', 'юю', 'ов', 'ев', 'ам', 'ям', 'ах', 'ях', 'ом', 'ем', 'ою', 'ею', 'ию', 'ия', 'ья', 'ье', 'ьи', 'ью',
    'а', 'я', 'о', 'е', 'ы', 'и', 'у', 'ю', 'ь', 'й', 's'];
  function stem(w) {
    if (w.length < 4 || /^\d+$/.test(w)) return w;
    for (var i = 0; i < ENDS.length; i++) { var e = ENDS[i]; if (w.length - e.length >= 3 && w.slice(-e.length) === e) return w.slice(0, -e.length); }
    return w;
  }
  function tokens(n) { var out = [], m; WORD.lastIndex = 0; while ((m = WORD.exec(n))) out.push({ w: m[0], s: m.index, e: m.index + m[0].length }); return out; }
  function parseQuery(q) {
    var n = norm(q), terms = [], m, re = /"([^"]+)"|«([^»]+)»|(\S+)/g;
    while ((m = re.exec(n))) {
      var ph = m[1] || m[2];
      if (ph) { ph = ph.replace(/\s+/g, ' ').trim(); if (ph) terms.push({ k: 'ph', v: ph }); continue; }
      (m[3].match(WORD) || []).forEach(function (w) { if (w.length >= 2 || /\d/.test(w)) terms.push({ k: 'w', v: w, st: stem(w) }); });
    }
    return terms;
  }
  /* совпадения одного термина в тексте: [{s, e, sc}] (позиции в исходной строке) */
  function termHits(t, n, toks, sub) {
    var out = [];
    if (t.k === 'ph') { var i = 0; while ((i = n.indexOf(t.v, i)) >= 0) { var pre = i ? n.charAt(i - 1) : ' '; if (sub || !/[0-9a-zа-я]/.test(pre)) out.push({ s: i, e: i + t.v.length, sc: 4 }); i += t.v.length; } return out; }
    for (var k = 0; k < toks.length; k++) {
      var w = toks[k].w, sc = 0;
      if (w === t.v) sc = 3;
      else if (w.indexOf(t.v) === 0) sc = 2;
      else if (t.st.length >= 3 && stem(w) === t.st) sc = 1.5;
      else if (sub && w.indexOf(t.v) > 0) sc = 1;
      if (sc) out.push({ s: toks[k].s + (sc === 1 ? w.indexOf(t.v) : 0), e: toks[k].s + (sc === 1 ? w.indexOf(t.v) + t.v.length : sc === 1.5 ? w.length : t.v.length), sc: sc });
    }
    return out;
  }
  function matchText(text, Q) {
    var n = norm(text), toks = tokens(n), hits = [], score = 0, any = 0;
    for (var i = 0; i < Q.terms.length; i++) {
      var h = termHits(Q.terms[i], n, toks, Q.sub);
      if (h.length) { any++; score += Math.max.apply(null, h.map(function (x) { return x.sc; })) + Math.min(h.length - 1, 3) * 0.2; hits = hits.concat(h); }
      else if (!Q.any) return null;
    }
    if (!any) return null;
    return { score: score, hits: hits.sort(function (a, b) { return a.s - b.s; }) };
  }

  /* ---------- виды блоков ---------- */
  var TYPES = [['strategy', 'Стратегия'], ['registry', 'Реестр'], ['competitors', 'Конкуренты'], ['charts', 'Графики'], ['flows', 'Схемы'], ['plan', 'План и Kanban'],
    ['design', 'Макеты и дизайн'], ['market', 'Рынок, модель, источники'], ['glossary', 'Глоссарий'], ['docs', 'Исследования'], ['other', 'Прочее']];
  var TYPE_T = {}; TYPES.forEach(function (t) { TYPE_T[t[0]] = t[1]; });
  function typeOf(sid) {
    if (/^s-/.test(sid) || sid === 'top' || sid === 'viability' || sid === 'questions') return 'strategy';
    if (sid === 'registry' || sid === 'progress') return 'registry';
    if (sid === 'competitors') return 'competitors';
    if (sid === 'charts') return 'charts';
    if (sid === 'flows') return 'flows';
    if (sid === 'gantt' || sid === 'kanban') return 'plan';
    if (sid === 'mockups' || sid === 'design-refs' || sid === 'current') return 'design';
    if (sid === 'market' || sid === 'sources' || sid === 'model' || sid === 'scores') return 'market';
    if (sid === 'glossary') return 'glossary';
    return 'other';
  }
  function secLabel(sid) { var a = $('nav.side a[data-sec="' + sid + '"]'); if (a) return a.textContent.replace(/\s+/g, ' ').trim(); var s = doc.getElementById(sid), h = s && s.querySelector('h1,h2'); return h ? h.textContent.replace(/\s+/g, ' ').trim() : sid; }

  /* ---------- индекс ---------- */
  var IDX = null, CHARTS_ADDED = false;
  var BLOCK = 'h1,h2,h3,h4,p,li,tr,dt,dd,figcaption,blockquote,summary,pre,.kcard,.glabel,.kpi,.nchip,.gphase,.ph,.missing';
  var SKIP_IN = '#tb,#reg-head,#cgrid,#cmatrix,script,style,noscript,svg,.psi-zoom,.psi-cue,.psi-hint,.pss-nav,nav,.layer,#cp,select,option,button.ps-howto-btn';
  function addEntry(e) { e.n = norm(e.text); IDX.push(e); }
  function buildDom() {
    var main = $('#main') || $('main'); if (!main) return;
    var blocks = new Map(), order = [];
    var w = doc.createTreeWalker(main, NodeFilter.SHOW_TEXT, { acceptNode: function (t) { return t.nodeValue.trim() ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT; } });
    while (w.nextNode()) {
      var t = w.currentNode, p = t.parentNode; if (!p || p.nodeType !== 1) continue;
      if (p.closest(SKIP_IN)) continue;
      var b = p.closest(BLOCK); if (!b || !main.contains(b)) continue;
      if (!blocks.has(b)) { blocks.set(b, []); order.push(b); }
      blocks.get(b).push(t.nodeValue);
    }
    order.forEach(function (b) {
      var text = blocks.get(b).join(' ').replace(/\s+/g, ' ').trim(); if (text.length < 2) return;
      var s = b.closest('section[id]'); while (s && s.parentElement && s.parentElement.closest('section[id]')) s = s.parentElement.closest('section[id]');
      var sid = s ? s.id : '', head = /^H[1-4]$/.test(b.tagName);
      addEntry({ type: typeOf(sid), where: secLabel(sid), title: head ? text : '', text: text, el: b, head: head });
    });
  }
  function buildData() {
    (J('d-registry') || []).forEach(function (r) {
      var parts = [r.id, r.title, r.description, r.rationale, r.segment, r.current_feature, r.cheap_test, txt(r.steps), txt(r.effect_kpi), txt((r.evidence || []).map(function (e) { return e && typeof e === 'object' ? [e.title, e.note].join(' ') : e; })), (r.tags || []).join(' ')];
      addEntry({ type: 'registry', where: 'Реестр предложений', title: r.id + ' — ' + r.title, text: parts.filter(Boolean).join(' · '), go: function () { goTo('#p/' + r.id, function () { var tr = $('#tb tr.row[data-id="' + r.id + '"]'); return tr && tr.nextElementSibling && tr.nextElementSibling.classList.contains('detail') ? tr.nextElementSibling : tr; }); } });
    });
    (J('d-comp') || []).forEach(function (c) {
      if (c.self) return;
      var parts = [c.name, c.verdict, c.verdict_long, c.segment, c.price, c.monetization, c.design_note, txt(c.better_than_us), txt(c.we_better), txt(c.best_solutions), txt(c.complaints), txt(c.adopt), txt(c.avoid)];
      addEntry({ type: 'competitors', where: 'Конкуренты', title: c.name, text: parts.filter(Boolean).join(' · '), go: function () { goTo('#competitor/' + c.slug, function () { return $('#cgrid .ccard[data-slug="' + c.slug + '"]'); }); } });
    });
    var nodes = J('d-flows') || {};
    Object.keys(nodes).forEach(function (id) {
      var n = nodes[id] || {};
      addEntry({ type: 'flows', where: 'Схема «' + (n.flow || '') + '»', title: n.label || id, text: [n.label, n.what, n.now, txt(n.todo), n.metrics].filter(Boolean).join(' · '),
        go: function () { if (PS.openNode) { PS.openNode(id); hlLater(function () { return $('#imbody'); }); } } });
    });
    (J('d-gantt') || []).forEach(function (g, i) {
      addEntry({ type: 'plan', where: 'План и диаграмма Ганта', title: (g.id ? g.id + ' — ' : '') + g.task, text: [g.id, g.task, g.phase, g.done, g.owner, g.when].filter(Boolean).join(' · '),
        go: function () { if (PS.openGantt) { PS.openGantt(i); hlLater(function () { return $('#imbody'); }); } } });
    });
    (J('d-kanban') || []).forEach(function (k, i) {
      addEntry({ type: 'plan', where: 'Kanban · ' + (k.column || ''), title: (k.id ? k.id + ' — ' : '') + (k.title || ''), text: [k.id, k.title, txt(k.goal), txt(k.kpi), txt(k.steps), (k.tags || []).join(' ')].filter(Boolean).join(' · '),
        go: function () { if (PS.openKanban) { PS.openKanban(i); hlLater(function () { return $('#imbody'); }); } } });
    });
    (J('d-gloss') || []).forEach(function (g) {
      addEntry({ type: 'glossary', where: 'Глоссарий', title: g.label, text: [g.label, (g.forms || []).join(' '), g.what].filter(Boolean).join(' · '),
        go: function () { goTo('#gl/' + g.key, function () { return doc.getElementById('gl-' + g.key); }); } });
    });
    addDocs(J('d-docs') || window.PS_DOCS || []);
  }
  var DOCS_ADDED = false;
  function addDocs(list) {
    if (DOCS_ADDED || !list || !list.length) return; DOCS_ADDED = true;
    list.forEach(function (d) {
      String(d.text || '').split(/\n\s*\n/).forEach(function (para) {
        var t = para.replace(/\s+/g, ' ').trim(); if (t.length < 3) return;
        addEntry({ type: 'docs', where: 'Исследование · ' + (d.title || d.path), title: d.title || d.path, text: t, doc: d, go: function () { openDoc(d, t); } });
      });
    });
  }
  /* site: тексты исследований — assets/search-docs.js (<meta name="ps-docs">), подключается при первом поиске */
  var DOCS_LOADING = false;
  function loadDocs(cb) {
    var m = $('meta[name="ps-docs"]'); if (DOCS_ADDED || !m || DOCS_LOADING) { if (cb) cb(false); return; }
    if (window.PS_DOCS) { addDocs(window.PS_DOCS); if (cb) cb(true); return; }
    DOCS_LOADING = true; var sc = doc.createElement('script'); sc.src = m.getAttribute('content'); sc.async = true;
    sc.onload = function () { DOCS_LOADING = false; addDocs(window.PS_DOCS || []); if (cb) cb(true); };
    sc.onerror = function () { DOCS_LOADING = false; if (cb) cb(false); };
    doc.head.appendChild(sc);
  }
  function addCharts() {
    if (CHARTS_ADDED) return; var R = window.PS_ROUTER; if (!R || !R.meta) return;
    var keys = {}; $$('figure.ps-ichart[data-chart]').forEach(function (f) { keys[f.getAttribute('data-chart')] = 1; });
    var ok = true;
    Object.keys(keys).forEach(function (key) {
      var m = R.meta(key); if (!m) { ok = false; return; }
      (m.elements || []).forEach(function (e) {
        addEntry({ type: 'charts', where: 'График «' + (m.title || key) + '»', title: e.title || e.id, text: [e.title, e.summary, e.meaning, txt(e.actions), txt((e.metrics || []).map(function (x) { return x.label + ' ' + x.value; }))].filter(Boolean).join(' · '),
          go: function () { goTo('#chart/' + key + '/' + e.id, function () { return $('#cp-body'); }); } });
      });
    });
    CHARTS_ADDED = ok;
  }
  function ensureIndex(cb) {
    if (!IDX) { IDX = []; safe('dom', buildDom); safe('data', buildData); loadDocs(function (added) { if (added && L && L.classList.contains('open') && $('#pss-q', L).value) run(); }); }
    if (!CHARTS_ADDED) {
      var R = window.PS_ROUTER;
      if (R && R.loadAll && $('.ps-svg[data-ps-src]')) { R.loadAll(function () { safe('charts', addCharts); if (cb) cb(); }); addCharts(); return; }
      safe('charts', addCharts);
    }
    if (cb) cb();
  }

  /* ---------- окно поиска ---------- */
  var L = null, Q = null, RES = [], SEL = -1, FILTER = '';
  function build() {
    if (L) return L;
    L = doc.createElement('div'); L.id = 'pss'; L.className = 'layer modal'; L.setAttribute('role', 'dialog'); L.setAttribute('aria-modal', 'true');
    L.setAttribute('aria-labelledby', 'pss-title'); L.setAttribute('aria-hidden', 'true');
    L.innerHTML = '<div class="mbox pss-box"><div class="mhead"><div class="mtitle" id="pss-title">Поиск по странице</div>'
      + '<button type="button" data-close aria-label="Закрыть (Esc)">✕</button></div>'
      + '<div class="pss-bar" role="search"><input type="search" id="pss-q" data-autofocus autocomplete="off" spellcheck="false" placeholder="Слово, часть слова или «фраза в кавычках»…" aria-label="Что искать" aria-controls="pss-res">'
      + '<label class="chk"><input type="checkbox" id="pss-sub"> внутри слова</label><label class="chk"><input type="checkbox" id="pss-any"> любое из слов</label></div>'
      + '<div class="pss-filters" role="group" aria-label="Где искать"></div><div class="pss-count" id="pss-count" aria-live="polite"></div>'
      + '<p class="pss-help">Регистр и е/ё не важны; «цена» найдёт «цены» и «ценой», «калькул» — «калькулятор». ↑/↓ — по выдаче, Enter — перейти, Esc — закрыть.</p>'
      + '<ol class="pss-res" id="pss-res"></ol></div>';
    doc.body.appendChild(L);
    var q = $('#pss-q', L), deb = 0;
    q.addEventListener('input', function () { clearTimeout(deb); deb = setTimeout(run, 120); });
    $('#pss-sub', L).addEventListener('change', run); $('#pss-any', L).addEventListener('change', run);
    q.addEventListener('keydown', function (e) {
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') { e.preventDefault(); e.stopPropagation(); move(e.key === 'ArrowDown' ? 1 : -1); }
      /* переход — после того, как Enter отработал: иначе тот же Enter дойдёт до обработчиков страницы (элемент графика в фокусе) */
      else if (e.key === 'Enter') { e.preventDefault(); e.stopPropagation(); var i = SEL >= 0 ? SEL : 0; setTimeout(function () { openRes(i); }, 0); }
    });
    $('.pss-filters', L).addEventListener('click', function (e) { var b = e.target.closest('button[data-t]'); if (!b) return; FILTER = FILTER === b.getAttribute('data-t') ? '' : b.getAttribute('data-t'); SEL = -1; render();
      try { $('#pss-q', L).focus({ preventScroll: true }); } catch (x) { /* старый движок */ } });
    $('#pss-res', L).addEventListener('click', function (e) { var b = e.target.closest('button[data-i]'); if (b) { e.preventDefault(); e.stopPropagation(); var i = +b.getAttribute('data-i'); setTimeout(function () { openRes(i); }, 0); } });
    $('#pss-res', L).addEventListener('keydown', function (e) { if (e.key === 'ArrowDown' || e.key === 'ArrowUp') { e.preventDefault(); move(e.key === 'ArrowDown' ? 1 : -1, true); } });
    L.addEventListener('click', function (e) { if (e.target === L && PS.closeLayer) PS.closeLayer(L); });
    return L;
  }
  function open(text) {
    if (replaced()) return false;
    build(); clearMarks();
    if (PS.openLayer) PS.openLayer(L); else { L.classList.add('open'); L.setAttribute('aria-hidden', 'false'); }
    var q = $('#pss-q', L); if (text != null) q.value = text;
    try { q.focus({ preventScroll: true }); q.select(); } catch (e) { /* старый движок */ }
    ensureIndex(function () { if (q.value) run(); else render(); });
    if (PS.emit) PS.emit('search:open', { q: q.value });
    return true;
  }
  function close() { if (L && L.classList.contains('open') && PS.closeLayer) PS.closeLayer(L); }
  function run() {
    var q = $('#pss-q', L).value, terms = parseQuery(q);
    Q = { terms: terms, sub: $('#pss-sub', L).checked, any: $('#pss-any', L).checked, raw: q };
    RES = [];
    if (terms.length && IDX) {
      IDX.forEach(function (e, i) {
        var m = matchText(e.text, Q); if (!m) return;
        var sc = m.score * (e.head ? 1.5 : 1) + (e.title && matchText(e.title, Q) ? 2 : 0);
        RES.push({ e: e, m: m, sc: sc, i: i });
      });
      RES.sort(function (a, b) { return b.sc - a.sc || a.i - b.i; });
    }
    SEL = RES.length ? 0 : -1;
    render();
  }
  function snippet(text, hits) {
    var h0 = hits[0], start = Math.max(0, h0.s - 70);
    if (start) { var sp = text.lastIndexOf(' ', start); start = sp > start - 20 ? sp + 1 : start; }
    var end = Math.min(text.length, start + 230), out = '', pos = start;
    hits.forEach(function (h) { if (h.s < pos || h.e > end) return; out += esc(text.slice(pos, h.s)) + '<mark>' + esc(text.slice(h.s, h.e)) + '</mark>'; pos = h.e; });
    out += esc(text.slice(pos, end));
    return (start ? '…' : '') + out + (end < text.length ? '…' : '');
  }
  function render() {
    if (!L) return;
    var counts = {}; RES.forEach(function (r) { counts[r.e.type] = (counts[r.e.type] || 0) + 1; });
    $('.pss-filters', L).innerHTML = Q && Q.terms.length ? '<button type="button" data-t="" aria-pressed="' + (!FILTER) + '">Все · ' + RES.length + '</button>' + TYPES.filter(function (t) { return counts[t[0]]; }).map(function (t) {
      return '<button type="button" data-t="' + t[0] + '" aria-pressed="' + (FILTER === t[0]) + '">' + esc(t[1]) + ' · ' + counts[t[0]] + '</button>'; }).join('') : '';
    var shown = RES.filter(function (r) { return !FILTER || r.e.type === FILTER; });
    if (shown.length && (SEL < 0 || !RES[SEL] || (FILTER && RES[SEL].e.type !== FILTER))) SEL = RES.indexOf(shown[0]);
    var q = $('#pss-q', L).value.trim();
    $('#pss-count', L).textContent = !q ? 'Введите слово или фразу.' : !Q || !Q.terms.length ? 'Слишком короткий запрос.' : RES.length ? 'Найдено: ' + shown.length + (FILTER ? ' из ' + RES.length : '') + (shown.length > 200 ? ' (показаны первые 200)' : '') : 'Ничего не найдено — попробуйте часть слова или флажок «внутри слова».';
    $('#pss-res', L).innerHTML = shown.slice(0, 200).map(function (r) {
      var e = r.e, idx = RES.indexOf(r);
      return '<li><button type="button" data-i="' + idx + '"' + (idx === SEL ? ' class="on"' : '') + '><span class="pss-where">' + esc(TYPE_T[e.type] || '') + ' · ' + esc(e.where) + '</span>'
        + (e.title && !e.head ? '<span class="pss-ttl">' + esc(e.title.length > 120 ? e.title.slice(0, 117) + '…' : e.title) + '</span>' : '')
        + '<span class="pss-snip">' + snippet(e.text, r.m.hits) + '</span></button></li>';
    }).join('');
  }
  function move(d, focusBtn) {
    var btns = $$('#pss-res button[data-i]', L); if (!btns.length) return;
    var cur = btns.findIndex(function (b) { return +b.getAttribute('data-i') === SEL; }), nx = Math.max(0, Math.min(btns.length - 1, (cur < 0 ? -1 : cur) + d));
    btns.forEach(function (b) { b.classList.remove('on'); }); btns[nx].classList.add('on'); SEL = +btns[nx].getAttribute('data-i');
    btns[nx].scrollIntoView({ block: 'nearest' }); if (focusBtn) btns[nx].focus();
  }
  function openRes(i) {
    var r = RES[i]; if (!r) return;
    var e = r.e, Qs = Q;
    close();
    if (e.go) { e.go(); return; }
    if (e.el) reveal(e.el, Qs);
  }
  function openDetails(el) { for (var p = el; p; p = p.parentElement) { if (p.tagName === 'DETAILS' && !p.open) p.open = true; if (p.classList && p.classList.contains('ps-howto') && p.hidden) { var b = $('[aria-controls="' + p.id + '"]'); if (b) b.click(); else p.hidden = false; } } }
  function reveal(el, Qs) {
    openDetails(el);
    var k = $('#kbv-plan'); if (k && el.closest('.kb-facts')) { var f = $('#kbv-facts'); if (f) f.checked = true; }
    try { el.scrollIntoView({ behavior: 'instant', block: 'center' }); } catch (x) { el.scrollIntoView(); }
    markIn(el, Qs || Q);
    if (!el.hasAttribute('tabindex')) el.setAttribute('tabindex', '-1');
    try { el.focus({ preventScroll: true }); } catch (x) { /* не фокусируется */ }
  }
  function goTo(h, target) {
    var R = window.PS_ROUTER, Qs = Q;
    if (R && R.go) R.go(h);
    hlLater(target, Qs);
  }
  function hlLater(target, Qs) {
    Qs = Qs || Q;
    var n = 0;
    (function tick() {
      var el = target && target();
      if (el && el.getClientRects().length) { markIn(el, Qs); return; }
      if (++n < 30) setTimeout(tick, 60);
    })();
  }
  function openDoc(d, para) {
    if (!PS.openInfo) return;
    var link = d.href ? ' · <a href="' + esc(d.href) + '" target="_blank" rel="noopener">открыть файл ' + esc(d.path) + '</a>' : '';
    PS.openInfo('<span class="muted">Исследование</span> ' + esc(d.title || d.path), '<p class="muted small">' + esc(d.path) + link + '</p><div class="prose"><p>' + esc(para) + '</p></div>');
    hlLater(function () { return $('#imbody'); });
  }

  /* ---------- подсветка на странице ---------- */
  function clearMarks() {
    $$('mark.pss-hit').forEach(function (m) { var p = m.parentNode; if (!p) return; p.replaceChild(doc.createTextNode(m.textContent), m); p.normalize(); });
  }
  function markIn(root, Qs) {
    if (!root || !Qs || !Qs.terms || !Qs.terms.length) return 0;
    clearMarks();
    var w = doc.createTreeWalker(root, NodeFilter.SHOW_TEXT, { acceptNode: function (t) { var p = t.parentNode; return p && p.closest && !p.closest('script,style,svg,textarea') && t.nodeValue.trim() ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT; } });
    var list = []; while (w.nextNode()) list.push(w.currentNode);
    var first = null, count = 0;
    list.forEach(function (t) {
      var s = t.nodeValue, n = norm(s), toks = tokens(n), hits = [];
      Qs.terms.forEach(function (term) { hits = hits.concat(termHits(term, n, toks, Qs.sub)); });
      if (!hits.length) return;
      hits.sort(function (a, b) { return a.s - b.s; });
      var frag = doc.createDocumentFragment(), pos = 0;
      hits.forEach(function (h) { if (h.s < pos) return; frag.appendChild(doc.createTextNode(s.slice(pos, h.s))); var m = doc.createElement('mark'); m.className = 'pss-hit'; m.textContent = s.slice(h.s, h.e); frag.appendChild(m); if (!first) first = m; count++; pos = h.e; });
      frag.appendChild(doc.createTextNode(s.slice(pos)));
      t.parentNode.replaceChild(frag, t);
    });
    if (first) { first.classList.add('pss-cur'); try { first.scrollIntoView({ behavior: 'instant', block: 'center', inline: 'nearest' }); } catch (x) { /* старый движок */ } }
    return count;
  }

  /* ---------- кнопки и клавиши ---------- */
  function addButtons() {
    var nav = $('#nav');
    if (nav && !$('.pss-nav', nav)) {
      var box = doc.createElement('div'); box.className = 'pss-nav';
      box.innerHTML = '<button type="button" class="pss-open" data-pss-open aria-keyshortcuts="/ Control+K" title="Поиск по всей странице: разделы, реестр, конкуренты, графики, схемы, план">🔎 <span class="pss-t">Поиск по странице</span> <kbd>/</kbd></button>';
      var here = $('.here', nav); if (here && here.nextSibling) nav.insertBefore(box, here.nextSibling); else nav.insertBefore(box, nav.firstChild);
    }
    var bar = $('.mbar');
    if (bar && !$('.pss-open', bar)) {
      var b = doc.createElement('button'); b.type = 'button'; b.className = 'pss-open'; b.setAttribute('data-pss-open', ''); b.setAttribute('aria-label', 'Поиск по странице');
      b.innerHTML = '🔎<span class="pss-t"> Поиск</span>';
      var t = $('.theme-btn', bar); if (t) bar.insertBefore(b, t); else bar.appendChild(b);
    }
  }
  doc.addEventListener('click', function (e) { var b = e.target && e.target.closest && e.target.closest('[data-pss-open]'); if (b) { e.preventDefault(); if (doc.body.classList.contains('nav-open')) { doc.body.classList.remove('nav-open'); var nt = $('#navtoggle'); if (nt) nt.setAttribute('aria-expanded', 'false'); } open(); } });
  doc.addEventListener('keydown', function (e) {
    var a = doc.activeElement, typing = a && (/^(INPUT|TEXTAREA|SELECT)$/.test(a.tagName) || a.isContentEditable);
    if (((e.key === 'k' || e.key === 'K' || e.key === 'л' || e.key === 'Л') && (e.ctrlKey || e.metaKey)) || (e.key === '/' && !typing && !e.ctrlKey && !e.metaKey && !e.altKey)) {
      if ($('.layer.open') && !(L && L.classList.contains('open'))) return;
      if (window.PSI && window.PSI.isOpen && window.PSI.isOpen()) return;
      e.preventDefault(); open();
    }
  });
  function fromHash() { var h = location.hash || '', m = /^#q=(.*)$/.exec(h); if (m) { var t = m[1]; try { t = decodeURIComponent(t); } catch (x) { /* как есть */ } open(t); } }
  window.addEventListener('hashchange', fromHash);
  safe('buttons', addButtons);
  safe('hash', fromHash);
  window.PS_SEARCH = { open: open, close: close, query: function (q, opts) { opts = opts || {}; ensureIndex(); var Qs = { terms: parseQuery(q), sub: !!opts.sub, any: !!opts.any }; return (IDX || []).map(function (e) { var m = matchText(e.text, Qs); return m ? { type: e.type, where: e.where, title: e.title, text: e.text.slice(0, 200), score: m.score } : null; }).filter(Boolean); },
    parse: parseQuery, stem: stem, norm: norm, mark: function (el, q) { return markIn(el, { terms: parseQuery(q) }); }, clear: clearMarks, size: function () { ensureIndex(); return IDX.length; } };
})();
