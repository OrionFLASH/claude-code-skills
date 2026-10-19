/* ps-ents.js — кликабельные сущности текста страницы стратегии (product-strategy 1.5; SM, раздел 8). Встраивается build_html.py
   после ps-search.js. P-id делает app.js (linkifyEl); здесь — остальное, что раньше было мёртвым текстом:
   - «раздел N», «разделе 5», «разделы 5 и 7», «разд. 3» → переход к разделу стратегии (если он есть на странице);
   - G-id задач Ганта → окно задачи; M-ключи макетов (M01) → макет; названия конкурентов → карточка конкурента;
   - ID из первой ячейки строк таблиц текста (H1, E03, R12, K4, PS2…) → строка таблицы (подсветка) с подсказкой;
   - термины глоссария (d-gloss: research/glossary.md от build_appendix.py) → подсказка с определением и окно «что это,
     где ещё упоминается», переход к строке раздела «Глоссарий» (#gl/<ключ>).
   ID — каждое упоминание; имена и термины — первое упоминание в блоке (абзац, пункт, ячейка). Текст не меняется (только
   обёртки <a>), поиск и подсветка работают как прежде. Подсказка — при наведении и фокусе с клавиатуры.
   Аудит «мёртвых» сущностей — PS_ENTS.audit() (smoke_html.mjs). Расширение может заменить слой: PS.replace('entities'). */
(function () {
  'use strict';
  if (window.PS_ENTS) return;
  var doc = document, PS = window.PS || {};
  function J(id) { if (PS.data) return PS.data(id); var D = window.PS_DATA; return D && Object.prototype.hasOwnProperty.call(D, id) ? D[id] : null; }
  function $(s, r) { return (r || doc).querySelector(s); }
  function $$(s, r) { return Array.prototype.slice.call((r || doc).querySelectorAll(s)); }
  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); }
  function safe(name, fn) { try { return fn(); } catch (e) { if (window.console) console.error('[ps-ents] ' + name + ': ' + (e && e.message || e)); } }
  function reEsc(s) { return String(s).replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); }
  function cut(s, n) { s = String(s || '').replace(/\s+/g, ' ').trim(); return s.length > n ? s.slice(0, n - 1).replace(/\s+\S*$/, '') + '…' : s; }
  function first(s) { var m = String(s || '').match(/^[\s\S]*?[.!?](?=\s|$)/); return cut(m ? m[0] : s, 160); }
  function replaced() { return !!(PS.isReplaced && PS.isReplaced('entities')); }
  var L = '0-9A-Za-zА-Яа-яЁё_';

  var REG = J('d-registry') || [], GANTT = J('d-gantt') || [], COMP = J('d-comp') || [], GLOSS = J('d-gloss') || [];
  var BYID = {}; REG.forEach(function (r) { BYID[r.id] = r; });
  var GBY = {}; GANTT.forEach(function (g, i) { if (g && g.id && !(g.id in GBY)) GBY[g.id] = i; });
  var TERMS = {}; GLOSS.forEach(function (g) { if (g && g.key) TERMS[g.key] = g; });

  /* ---------- справочники со страницы ---------- */
  var SECS = {}; $$('main section[id^="s-"]').forEach(function (s) { var n = +s.id.slice(2); if (n) SECS[n] = s; });
  function secTitle(n) { var s = SECS[n], h = s && s.querySelector('h2'); return h ? h.textContent.replace(/\s+/g, ' ').trim() : 'Раздел ' + n; }
  var MOCK = {};          /* «M01» → ключ макета (если однозначно) */
  (function () {
    var cnt = {};
    $$('main [data-mock]').forEach(function (f) { var k = f.getAttribute('data-mock'), m = /^(M\d{2,3})(?:[-_.]|$)/.exec(k); if (m) { (cnt[m[1]] = cnt[m[1]] || {})[k] = f; } });
    Object.keys(cnt).forEach(function (s) { var ks = Object.keys(cnt[s]); if (ks.length === 1) MOCK[s] = ks[0]; });
  })();
  var ROWS = {};          /* ID из первой ячейки строк таблиц текста → строка */
  var ID_RE = /^(?:[A-ZА-Я]{1,3}-?\d{1,3}(?:\.\d{1,2})?)$/;
  $$('main section .tbl table tbody tr').forEach(function (tr) {
    var c = tr.cells[0]; if (!c) return;
    var t = c.textContent.replace(/\s+/g, ' ').trim();
    if (!ID_RE.test(t) || /^P\d{3}$/.test(t) || t in ROWS) return;
    if (/^G\d/.test(t) && t in GBY) return;                 /* задача Ганта — каноническая цель */
    if (!tr.id) tr.id = 'ent-' + t.replace(/[^\w.-]/g, '_');
    tr.classList.add('ps-row-target');
    ROWS[t] = tr;
  });
  var COMPN = [];         /* [название, slug] без «мы» */
  COMP.forEach(function (c) {
    if (!c || c.self || !c.name || !c.slug) return;
    [c.name].concat(Array.isArray(c.aliases) ? c.aliases : []).forEach(function (n) { n = String(n || '').trim(); if (n.length >= 3) COMPN.push([n, c.slug]); });
  });

  /* ---------- шаблоны поиска ---------- */
  var idList = Object.keys(GBY).concat(Object.keys(MOCK), Object.keys(ROWS)).filter(function (x, i, a) { return a.indexOf(x) === i; }).sort(function (a, b) { return b.length - a.length; });
  var ID_PAT = idList.length ? new RegExp('(^|[^' + L + '-])(' + idList.map(reEsc).join('|') + ')(?![' + L + '-])', 'g') : null;
  var SEC_PAT = /(^|[^0-9A-Za-zА-Яа-яЁё_])((?:[Рр]аздел(?:ы|а|е|у|ом|ов|ах|ам)?|[Рр]азд\.)\s+)(\d{1,2})((?:\s*(?:,|и|–|—|-)\s*\d{1,2}(?![0-9]))*)/g;
  var NAMES = [];         /* [форма, тип, ключ, ci] — термины и конкуренты */
  GLOSS.forEach(function (g) { (g.forms && g.forms.length ? g.forms : [g.label]).forEach(function (f) { f = String(f || '').trim(); if (f.length >= 2) NAMES.push([f, 'term', g.key, g.ci !== false && /^[\x00-\x7f]+$/.test(f)]); }); });
  COMPN.forEach(function (x) { NAMES.push([x[0], 'comp', x[1], false]); });
  NAMES.sort(function (a, b) { return b[0].length - a[0].length; });
  var NAME_PAT = NAMES.length ? new RegExp('(^|[^' + L + '])(' + NAMES.map(function (n) { return reEsc(n[0]); }).join('|') + ')(?![' + L + '])', 'gi') : null;
  function nameOf(s) { for (var i = 0; i < NAMES.length; i++) { var n = NAMES[i]; if (n[3] ? n[0].toLowerCase() === s.toLowerCase() : n[0] === s) return n; } return null; }

  var SKIP = 'a,button,code,pre,script,style,svg,textarea,input,select,option,label,h1,h2,nav,.ps-ent,.ps-term,.pid,.gid,.kid,.pss-nav,.psi-zoom,.psi-cue,.psi-hint,#ps-etip,#cp-tip,#psi-tip,[data-no-ents],#reg-head,thead,.gscale,tr.ps-row-target > td:first-child,.gl-table td:first-child';
  var BLOCK = 'p,li,td,th,dd,dt,figcaption,blockquote,summary,h3,h4,.kcard,.glabel,.kpi';
  var seen = new WeakMap();
  function link(text, root) {
    var m, out = [], used = seen;
    function blockOf(t) { var p = t.parentNode; return (p && p.closest && p.closest(BLOCK)) || root; }
    var w = doc.createTreeWalker(root, NodeFilter.SHOW_TEXT, { acceptNode: function (t) { var p = t.parentNode; return p && p.closest && !p.closest(SKIP) && t.nodeValue.trim() ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT; } });
    var nodes = []; while (w.nextNode()) nodes.push(w.currentNode);
    var n = 0;
    nodes.forEach(function (t) {
      var s = t.nodeValue, hits = [];
      if (SEC_PAT) { SEC_PAT.lastIndex = 0; while ((m = SEC_PAT.exec(s))) {
        var at = m.index + m[1].length, num = +m[3];
        if (SECS[num]) hits.push({ s: at, e: at + m[2].length + m[3].length, k: 'sec', v: num });
        if (m[4]) { var base = at + m[2].length + m[3].length, re = /\d{1,2}/g, mm; while ((mm = re.exec(m[4]))) { var v = +mm[0]; if (SECS[v]) hits.push({ s: base + mm.index, e: base + mm.index + mm[0].length, k: 'sec', v: v }); } }
      } }
      if (ID_PAT) { ID_PAT.lastIndex = 0; while ((m = ID_PAT.exec(s))) { var a = m.index + m[1].length, id = m[2]; hits.push({ s: a, e: a + id.length, k: id in GBY ? 'gantt' : id in MOCK ? 'mock' : 'row', v: id }); } }
      if (NAME_PAT) {
        var blk = blockOf(t), set = used.get(blk); if (!set) { set = {}; used.set(blk, set); }
        NAME_PAT.lastIndex = 0; while ((m = NAME_PAT.exec(s))) { var b = m.index + m[1].length, nm = nameOf(m[2]); if (!nm) continue; var key = nm[1] + ':' + nm[2]; if (set[key]) continue; set[key] = 1; hits.push({ s: b, e: b + m[2].length, k: nm[1], v: nm[2] }); }
      }
      if (!hits.length) return;
      hits.sort(function (x, y) { return x.s - y.s || (y.e - y.s) - (x.e - x.s); });
      var frag = doc.createDocumentFragment(), pos = 0;
      hits.forEach(function (h) {
        if (h.s < pos) return;
        frag.appendChild(doc.createTextNode(s.slice(pos, h.s)));
        frag.appendChild(anchor(h, s.slice(h.s, h.e)));
        pos = h.e; n++;
      });
      frag.appendChild(doc.createTextNode(s.slice(pos)));
      t.parentNode.replaceChild(frag, t);
    });
    return n;
  }
  function anchor(h, label) {
    var a = doc.createElement('a'); a.textContent = label; a.className = h.k === 'term' ? 'ps-term' : 'ps-ent';
    if (h.k === 'sec') { a.href = '#s' + h.v; a.setAttribute('data-ent', 'sec:' + h.v); }
    else if (h.k === 'gantt') { a.href = '#gantt'; a.setAttribute('data-g-open', String(GBY[h.v])); a.setAttribute('data-ent', 'gantt:' + h.v); }
    else if (h.k === 'mock') { a.href = '#mockup/' + MOCK[h.v]; a.setAttribute('data-ent', 'mock:' + MOCK[h.v]); }
    else if (h.k === 'row') { a.href = '#' + ROWS[h.v].id; a.setAttribute('data-ent', 'row:' + h.v); }
    else if (h.k === 'comp') { a.href = '#competitor/' + h.v; a.setAttribute('data-ent', 'comp:' + h.v); }
    else if (h.k === 'term') { a.href = '#gl/' + h.v; a.setAttribute('data-term', h.v); a.setAttribute('data-ent', 'term:' + h.v); }
    return a;
  }
  function run(root) { if (replaced() || !root) return 0; return safe('link', function () { return link(null, root); }) || 0; }

  /* ---------- подсказки ---------- */
  var tip = doc.createElement('div'); tip.id = 'ps-etip'; tip.setAttribute('role', 'tooltip'); tip.hidden = true;
  function tipHtml(a) {
    var e = (a.getAttribute('data-ent') || '').split(':'), k = e[0], v = e.slice(1).join(':');
    if (k === 'sec') return '<b>' + esc(secTitle(+v)) + '</b><span>Перейти к разделу</span>';
    if (k === 'gantt') { var g = GANTT[GBY[v]] || {}; return '<b>' + esc(v + ' — ' + (g.task || '')) + '</b><span>' + esc(g.when || '') + (g.done ? ' · готово, когда: ' + esc(cut(g.done, 90)) : '') + '</span>'; }
    if (k === 'mock') { var f = $('main [data-mock="' + v + '"]'), cap = f && (f.getAttribute('data-cap') || (f.querySelector('figcaption b') || {}).textContent); return '<b>' + esc(cap || v) + '</b><span>Макет: открыть и рассмотреть</span>'; }
    if (k === 'row') { var tr = ROWS[v]; return '<b>' + esc(v) + '</b><span>' + esc(cut(tr ? tr.textContent.replace(/\s+/g, ' ').replace(new RegExp('^\\s*' + reEsc(v)), '') : '', 160)) + '</span>'; }
    if (k === 'comp') { var c = COMP.filter(function (x) { return x.slug === v; })[0] || {}; return '<b>' + esc(c.name || v) + '</b><span>' + esc(c.verdict_short || c.verdict || 'Карточка конкурента') + '</span>'; }
    if (k === 'term') { var t = TERMS[v] || {}; return '<b>' + esc(t.label || v) + '</b><span>' + esc(first(t.what)) + '</span>'; }
    return '';
  }
  function showTip(a, x, y) {
    var h = tipHtml(a); if (!h) return;
    tip.innerHTML = h; tip.hidden = false; var w = tip.offsetWidth, hh = tip.offsetHeight;
    tip.style.left = Math.max(4, Math.min(innerWidth - w - 4, x + 12)) + 'px';
    tip.style.top = Math.max(4, y - hh - 10 < 4 ? y + 18 : y - hh - 10) + 'px';
  }
  doc.addEventListener('pointerover', function (e) { var a = e.target && e.target.closest && e.target.closest('a.ps-ent,a.ps-term'); if (a && e.pointerType !== 'touch') showTip(a, e.clientX, e.clientY); else if (!tip.hidden) tip.hidden = true; }, { passive: true });
  doc.addEventListener('focusin', function (e) { var a = e.target && e.target.closest && e.target.closest('a.ps-ent,a.ps-term'); if (a) { var r = a.getBoundingClientRect(); showTip(a, r.left, r.top); } });
  doc.addEventListener('focusout', function () { tip.hidden = true; });
  window.addEventListener('scroll', function () { if (!tip.hidden) tip.hidden = true; }, { passive: true });

  /* ---------- действия ---------- */
  function flash(el) { if (!el) return; el.classList.remove('ps-flash'); void el.offsetWidth; el.classList.add('ps-flash'); setTimeout(function () { el.classList.remove('ps-flash'); }, 2300); }
  function mentions(key) {
    var by = {}; $$('main a.ps-term[data-term="' + key + '"]').forEach(function (a) { var s = a.closest('section[id]'); if (s) by[s.id] = (by[s.id] || 0) + 1; });
    return Object.keys(by).map(function (id) { var lab = ($('nav.side a[data-sec="' + id + '"]') || {}).textContent || id; return '<li><a href="#' + esc(id) + '">' + esc(lab) + '</a>' + (by[id] > 1 ? ' <span class="muted">×' + by[id] + '</span>' : '') + '</li>'; }).join('');
  }
  function openTerm(key) {
    var t = TERMS[key]; if (!t || !PS.openInfo) return false;
    var ments = mentions(key), row = doc.getElementById('gl-' + key);
    PS.openInfo('<span class="muted">Глоссарий</span> ' + esc(t.label),
      '<h4>Что это</h4><p>' + esc(t.what) + '</p>' + ((t.forms || []).length > 1 ? '<p class="muted small">Также: ' + esc(t.forms.filter(function (f) { return f !== t.label; }).join(', ')) + '</p>' : '')
      + (t.src ? '<p class="muted small">Источник: ' + esc(t.src) + '</p>' : '') + (ments ? '<h4>Где упоминается</h4><ul>' + ments + '</ul>' : '')
      + (row ? '<p><a href="#gl-' + esc(key) + '" data-gl-row="' + esc(key) + '">Строка в разделе «Глоссарий» →</a></p>' : ''));
    return true;
  }
  function goRow(id) { var el = doc.getElementById(id); if (!el) return false; for (var p = el; p; p = p.parentElement) if (p.tagName === 'DETAILS') p.open = true; el.scrollIntoView({ behavior: 'instant', block: 'center' }); flash(el); return true; }
  doc.addEventListener('click', function (e) {
    if (e.defaultPrevented || e.button !== 0 || e.ctrlKey || e.metaKey || e.shiftKey) return;
    var t = e.target; if (!t || !t.closest) return;
    var term = t.closest('a.ps-term[data-term]');
    if (term) { e.preventDefault(); tip.hidden = true; openTerm(term.getAttribute('data-term')); return; }
    var gr = t.closest('a[data-gl-row]');
    if (gr) { e.preventDefault(); if (PS.closeAll) PS.closeAll(); goRow('gl-' + gr.getAttribute('data-gl-row')); return; }
    var row = t.closest('a.ps-ent[data-ent^="row:"]');
    if (row) { e.preventDefault(); if (PS.closeAll) PS.closeAll(); goRow(row.getAttribute('href').slice(1)); }
  }, true);
  function fromHash() { var m = /^#gl\/(.+)$/.exec(location.hash || ''); if (m) { var k = m[1]; try { k = decodeURIComponent(k); } catch (x) { /* как есть */ } if (!goRow('gl-' + k)) openTerm(k); } }
  window.addEventListener('hashchange', fromHash);

  /* ---------- аудит «мёртвых» сущностей: известные ID и «раздел N» вне ссылок ---------- */
  function audit() {
    var main = $('#main') || $('main'), res = { pid: 0, gantt: 0, sec: 0, row: 0, terms_linked: $$('main a.ps-term').length, ents_linked: $$('main a.ps-ent').length, examples: [] };
    if (!main) return res;
    var w = doc.createTreeWalker(main, NodeFilter.SHOW_TEXT, { acceptNode: function (t) { var p = t.parentNode; return p && p.closest && !p.closest(SKIP + ',.hint,#tb,#cgrid,#cmatrix') && t.nodeValue.trim() ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT; } });
    var m;
    while (w.nextNode()) {
      var s = w.currentNode.nodeValue;
      var re = /(^|[^0-9A-Za-zА-Яа-яЁё_-])(P\d{3})(?![0-9A-Za-zА-Яа-яЁё_-])/g; while ((m = re.exec(s))) if (BYID[m[2]]) { res.pid++; if (res.examples.length < 8) res.examples.push(m[2]); }
      if (ID_PAT) { ID_PAT.lastIndex = 0; while ((m = ID_PAT.exec(s))) { var k = m[2] in GBY ? 'gantt' : m[2] in ROWS ? 'row' : null; if (k) { res[k]++; if (res.examples.length < 8) res.examples.push(m[2]); } } }
      SEC_PAT.lastIndex = 0; while ((m = SEC_PAT.exec(s))) if (SECS[+m[3]]) { res.sec++; if (res.examples.length < 8) res.examples.push(m[2] + m[3]); }
    }
    res.inert = res.pid + res.gantt + res.sec + res.row;
    return res;
  }

  function init() {
    doc.body.appendChild(tip);
    if (replaced()) return;
    $$('main > section').forEach(function (s) { if (s.id !== 'registry' && s.id !== 'competitors') run(s); });
    fromHash();
  }
  window.PS_ENTS = { run: run, audit: audit, openTerm: openTerm, terms: function () { return Object.keys(TERMS); }, rows: function () { return Object.keys(ROWS); } };
  if (PS) PS.ents = run;
  safe('init', init);
})();
