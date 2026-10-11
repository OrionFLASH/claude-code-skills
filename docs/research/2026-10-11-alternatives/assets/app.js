(function () {
  'use strict';
  var R = window.REPORT || { skills: [], sources: [], overview: {}, meta: {} };
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };
  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); }
  function link(u, t) { u = String(u || ''); if (!/^https?:\/\//i.test(u)) return esc(t || u); return '<a href="' + esc(u) + '" target="_blank" rel="noopener noreferrer">' + esc(t || u.replace(/^https?:\/\/(www\.)?/, '').slice(0, 60)) + '</a>'; }
  function num(n) { return n == null ? '—' : String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ' '); }
  var VERDICT = { replace: ['заменяет', 'b-yes'], partial: ['частично', 'b-partial'], inspire: ['идеи', 'b-info'], ignore: ['не подходит', 'b-n'] };
  var CAN = { yes: ['Да, можно заменить', 'b-yes', 'yes'], partial: ['Частично', 'b-partial', 'partial'], no: ['Нет, оставить своим', 'b-no', 'no'] };
  var SC = ['s0', 's1', 's2', 's3'], SCNAME = ['нет', 'частично', 'эквивалент', 'шире/лучше'];

  // ---------- расчёты ----------
  function covPct(c, caps) {
    var t = 0, n = 0;
    caps.forEach(function (k) { var v = ((c.coverage || {})[k.id] || {}).score; if (v != null) { t += v; n++; } });
    return caps.length ? Math.round(100 * t / (3 * caps.length)) : 0;
  }
  function eqCount(c, caps) { return caps.filter(function (k) { var v = ((c.coverage || {})[k.id] || {}).score; return v != null && v >= 2; }).length; }
  function byId(S, id) { return (S.candidates || []).filter(function (c) { return c.id === id; })[0]; }
  function stackScores(S) {
    var ids = (S.verdict || {}).replace_with || [], res = {};
    (S.capabilities || []).forEach(function (k) {
      var best = null, who = null;
      ids.forEach(function (id) { var c = byId(S, id); var v = c && ((c.coverage || {})[k.id] || {}).score; if (v != null && (best == null || v > best)) { best = v; who = c; } });
      res[k.id] = { score: best, who: who };
    });
    return res;
  }
  function stackPct(S) { var s = stackScores(S), t = 0, n = (S.capabilities || []).length; (S.capabilities || []).forEach(function (k) { if (s[k.id].score != null) t += s[k.id].score; }); return n ? Math.round(100 * t / (3 * n)) : 0; }
  function stackEq(S) { var s = stackScores(S); return (S.capabilities || []).filter(function (k) { return s[k.id].score != null && s[k.id].score >= 2; }).length; }
  function bestSingle(S) { var b = null; (S.candidates || []).forEach(function (c) { var p = covPct(c, S.capabilities || []); if (!b || p > b.p) b = { c: c, p: p }; }); return b; }

  // ---------- панель ----------
  var panel = $('#panel'), lastFocus = null;
  function openPanel(html, hash) {
    lastFocus = document.activeElement; panel.innerHTML = '<button class="x" aria-label="Закрыть">×</button>' + html; panel.hidden = false;
    $('.x', panel).onclick = closePanel; $('.x', panel).focus();
    if (hash) { try { history.replaceState(null, '', hash); } catch (e) { } }
    $$('[data-open]', panel).forEach(function (a) { a.onclick = function (e) { e.preventDefault(); route(a.getAttribute('data-open')); }; });
  }
  function closePanel() { panel.hidden = true; if (lastFocus && lastFocus.focus) lastFocus.focus(); try { history.replaceState(null, '', location.pathname + location.search); } catch (e) { } }
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && !panel.hidden) closePanel(); });
  function chipFor(v) { return v == null ? '<span class="chip cn">не проверено</span>' : '<span class="chip c' + v + '">' + v + ' · ' + SCNAME[v] + '</span>'; }
  function ul(a) { return a && a.length ? '<ul class="tight">' + a.map(function (x) { return '<li>' + esc(x) + '</li>'; }).join('') + '</ul>' : '<p class="muted small">—</p>'; }
  function candPanel(S, c, capId) {
    var caps = S.capabilities || [], v = VERDICT[c.verdict] || ['—', 'b-n'];
    var h = '<h3>' + esc(c.name) + '</h3><p><span class="badge ' + v[1] + '">' + v[0] + '</span> <span class="tag">' + esc(c.kind || '') + '</span>' + (c.collection ? '<span class="tag">' + esc(c.collection) + '</span>' : '') + '</p>';
    h += '<p>' + link(c.url, 'Открыть репозиторий / страницу') + '</p><p>' + esc(c.summary || '') + '</p>';
    h += '<dl class="kv"><dt>Лицензия</dt><dd>' + esc(c.license || '—') + (c.osi_license === true ? ' (OSI)' : c.osi_license === false ? ' (не OSI)' : '') + '</dd><dt>Звёзды</dt><dd>' + num(c.stars) + '</dd><dt>Форки</dt><dd>' + num(c.forks) + '</dd><dt>Последний коммит</dt><dd>' + esc(c.last_commit || '—') + '</dd><dt>Создан</dt><dd>' + esc(c.created || '—') + '</dd><dt>Контрибьюторов</dt><dd>' + num(c.contributors) + '</dd><dt>Цена</dt><dd>' + esc(c.price || '—') + '</dd><dt>Нативно в Claude Code</dt><dd>' + (c.claude_code_native === true ? 'да' : c.claude_code_native === false ? 'нет' : '—') + '</dd><dt>Языки</dt><dd>' + esc((c.languages || []).join(', ') || '—') + '</dd><dt>Покрытие</dt><dd>' + covPct(c, caps) + ' % (эквивалент или лучше: ' + eqCount(c, caps) + ' из ' + caps.length + ')</dd></dl>';
    h += '<h4>Сильные стороны</h4>' + ul(c.strengths) + '<h4>Слабые стороны</h4>' + ul(c.weaknesses) + '<h4>Риски</h4>' + ul(c.risks);
    if ((c.quality_signals || []).length) h += '<h4>Сигналы качества</h4><ul class="tight">' + c.quality_signals.map(function (q) { return '<li>' + esc(q.label) + ': ' + esc(q.value) + (q.url ? ' — ' + link(q.url, 'источник') : '') + '</li>'; }).join('') + '</ul>';
    h += '<h4>Покрытие возможностей</h4>';
    caps.forEach(function (k) {
      var x = (c.coverage || {})[k.id] || {}, ev = (x.evidence || []).map(function (u) { return link(u, 'источник'); }).join(' · ');
      h += '<div class="covrow"' + (k.id === capId ? ' style="background:var(--surface2)"' : '') + '><b>' + esc(k.id) + '</b> ' + esc(k.name) + '<br>' + chipFor(x.score) + ' <span class="small">' + esc(x.note || '') + '</span>' + (ev ? '<br><span class="small">' + ev + '</span>' : '') + '</div>';
    });
    openPanel(h, '#cand/' + S.key + '/' + c.id);
  }
  function capPanel(S, c, k) {
    var x = (c.coverage || {})[k.id] || {}, ev = (x.evidence || []).map(function (u) { return '<li>' + link(u) + '</li>'; }).join('');
    var h = '<h3>' + esc(k.id) + ' · ' + esc(k.name) + '</h3><p class="muted">' + esc(k.desc || '') + '</p><h4>' + esc(c.name) + '</h4><p>' + chipFor(x.score) + '</p><p>' + esc(x.note || 'Примечание не указано.') + '</p>';
    h += ev ? '<h4>Доказательства</h4><ul class="tight">' + ev + '</ul>' : '<p class="muted small">Ссылок-доказательств нет.</p>';
    h += '<p><a href="#" data-open="#cand/' + S.key + '/' + c.id + '">Полная карточка «' + esc(c.name) + '» →</a></p>';
    openPanel(h, '#cap/' + S.key + '/' + k.id + '/' + c.id);
  }
  function stackPanel(S, k, st) {
    var h = '<h3>' + esc(k.id) + ' · ' + esc(k.name) + '</h3><p class="muted">' + esc(k.desc || '') + '</p><p>Лучший результат рекомендуемого набора: ' + chipFor(st.score) + '</p>';
    if (st.who) h += '<p>Закрывает: <a href="#" data-open="#cand/' + S.key + '/' + st.who.id + '">' + esc(st.who.name) + '</a></p>';
    else h += '<p class="muted">Ни один кандидат из рекомендуемого набора эту возможность не закрывает — это то, что остаётся за вашим скилом.</p>';
    var all = (S.candidates || []).map(function (c) { return [c, ((c.coverage || {})[k.id] || {}).score]; }).filter(function (p) { return p[1] != null && p[1] >= 2; }).sort(function (a, b) { return b[1] - a[1]; }).slice(0, 8);
    if (all.length) h += '<h4>Кто ещё закрывает на уровне эквивалента</h4><ul class="tight">' + all.map(function (p) { return '<li><a href="#" data-open="#cap/' + S.key + '/' + k.id + '/' + p[0].id + '">' + esc(p[0].name) + '</a> — ' + SCNAME[p[1]] + '</li>'; }).join('') + '</ul>';
    openPanel(h, '#need/' + S.key + '/' + k.id);
  }

  // ---------- диаграммы ----------
  var svgNS = 'http://www.w3.org/2000/svg';
  function shortName(s, n) { s = String(s || ''); return s.length > n ? s.slice(0, n - 1) + '…' : s; }
  function heatmap(S) {
    var caps = S.capabilities || [], cs = (S.candidates || []).slice().sort(function (a, b) { return covPct(b, caps) - covPct(a, caps); }).slice(0, 16);
    var lw = 250, cw = 34, ch = 26, top = 120, W = lw + cs.length * cw + 20, H = top + caps.length * ch + 16;
    var colors = ['var(--s0)', 'var(--s1)', 'var(--s2)', 'var(--s3)'];
    var o = '<svg role="group" aria-label="Матрица покрытия возможностей" width="' + W + '" height="' + H + '" viewBox="0 0 ' + W + ' ' + H + '">';
    cs.forEach(function (c, i) { var x = lw + i * cw + cw / 2; o += '<text transform="translate(' + x + ',' + (top - 8) + ') rotate(-55)" font-size="11.5" fill="var(--text)">' + esc(shortName(c.name, 24)) + '</text>'; });
    caps.forEach(function (k, j) {
      var y = top + j * ch; o += '<text x="' + (lw - 8) + '" y="' + (y + ch / 2 + 4) + '" text-anchor="end" font-size="12" fill="var(--text)">' + esc(k.id + ' ' + shortName(k.name, 34)) + '</text>';
      cs.forEach(function (c, i) {
        var v = ((c.coverage || {})[k.id] || {}).score, x = lw + i * cw;
        o += '<rect class="cell" tabindex="0" role="button" data-s="' + S.key + '" data-c="' + esc(c.id) + '" data-k="' + esc(k.id) + '" aria-label="' + esc(k.id + ', ' + c.name + ': ' + (v == null ? 'не проверено' : SCNAME[v])) + '" x="' + x + '" y="' + y + '" width="' + (cw - 2) + '" height="' + (ch - 2) + '" rx="4" fill="' + (v == null ? 'var(--sn)' : colors[v]) + '"/>';
        o += '<text x="' + (x + cw / 2 - 1) + '" y="' + (y + ch / 2 + 4) + '" text-anchor="middle" font-size="11" fill="var(--text)" pointer-events="none">' + (v == null ? '·' : v) + '</text>';
      });
    });
    return o + '</svg>';
  }
  function bubble(S) {
    var caps = S.capabilities || [], W = 760, H = 400, L = 62, B = 46, T = 14, Rr = 20, pw = W - L - Rr, ph = H - T - B;
    var cs = (S.candidates || []), ymax = Math.max.apply(null, cs.map(function (c) { return c.stars || 1; }).concat([100]));
    var ly = function (s) { return Math.log10(Math.max(1, s || 1)) / Math.log10(ymax * 1.4); };
    var o = '<svg role="group" aria-label="Покрытие против популярности" width="' + W + '" height="' + H + '" viewBox="0 0 ' + W + ' ' + H + '">';
    for (var g = 0; g <= 100; g += 20) { var x = L + pw * g / 100; o += '<line x1="' + x + '" y1="' + T + '" x2="' + x + '" y2="' + (T + ph) + '" stroke="var(--border)"/><text x="' + x + '" y="' + (H - 26) + '" text-anchor="middle" font-size="11" fill="var(--muted)">' + g + '%</text>'; }
    [1, 10, 100, 1000, 10000, 100000].forEach(function (s) { if (s > ymax * 1.4) return; var y = T + ph * (1 - ly(s)); o += '<line x1="' + L + '" y1="' + y + '" x2="' + (L + pw) + '" y2="' + y + '" stroke="var(--border)"/><text x="' + (L - 6) + '" y="' + (y + 4) + '" text-anchor="end" font-size="11" fill="var(--muted)">' + num(s) + '</text>'; });
    o += '<text x="' + (L + pw / 2) + '" y="' + (H - 6) + '" text-anchor="middle" font-size="12" fill="var(--muted)">Покрытие возможностей вашего скила, %</text><text transform="translate(14,' + (T + ph / 2) + ') rotate(-90)" text-anchor="middle" font-size="12" fill="var(--muted)">Звёзды (лог.)</text>';
    var col = { replace: 'var(--ok)', partial: 'var(--warn)', inspire: 'var(--info)', ignore: 'var(--muted)' };
    cs.forEach(function (c) {
      var p = covPct(c, caps), x = L + pw * p / 100, y = T + ph * (1 - ly(c.stars)), r = 6 + Math.min(12, Math.sqrt(c.contributors || 1) * 1.2);
      o += '<circle class="pt" tabindex="0" role="button" data-s="' + S.key + '" data-c="' + esc(c.id) + '" aria-label="' + esc(c.name + ': покрытие ' + p + '%, звёзд ' + (c.stars == null ? 'неизвестно' : c.stars)) + '" cx="' + x + '" cy="' + y + '" r="' + r + '" fill="' + (col[c.verdict] || 'var(--muted)') + '"><title>' + esc(c.name) + '</title></circle>';
    });
    var top5 = cs.slice().sort(function (a, b) { return covPct(b, caps) - covPct(a, caps); }).slice(0, 6);
    top5.forEach(function (c) { var p = covPct(c, caps), x = L + pw * p / 100, y = T + ph * (1 - ly(c.stars)); o += '<text x="' + (x + 10) + '" y="' + (y - 8) + '" font-size="11" fill="var(--text)" pointer-events="none">' + esc(shortName(c.name, 22)) + '</text>'; });
    return o + '</svg><div class="legend"><span><i style="background:var(--ok)"></i>заменяет</span><span><i style="background:var(--warn)"></i>частично</span><span><i style="background:var(--info)"></i>только идеи</span><span><i style="background:var(--muted)"></i>не подходит</span><span>размер — число контрибьюторов</span></div>';
  }
  function radar(S) {
    var caps = S.capabilities || [], n = caps.length; if (n < 3) return '';
    var W = 520, H = 460, cx = W / 2, cy = H / 2 + 6, rad = 160, best = bestSingle(S), st = stackScores(S);
    function pt(i, v) { var a = -Math.PI / 2 + 2 * Math.PI * i / n; return [cx + rad * v / 3 * Math.cos(a), cy + rad * v / 3 * Math.sin(a)]; }
    function poly(vals, stroke, fill, dash) { var p = vals.map(function (v, i) { return pt(i, v == null ? 0 : v).join(','); }).join(' '); return '<polygon points="' + p + '" fill="' + fill + '" stroke="' + stroke + '" stroke-width="2"' + (dash ? ' stroke-dasharray="6 4"' : '') + '/>'; }
    var o = '<svg role="img" aria-label="Радар покрытия" width="' + W + '" height="' + H + '" viewBox="0 0 ' + W + ' ' + H + '">';
    [1, 2, 3].forEach(function (r) { o += '<polygon points="' + caps.map(function (_, i) { return pt(i, r).join(','); }).join(' ') + '" fill="none" stroke="var(--border)"/>'; });
    caps.forEach(function (k, i) { var p = pt(i, 3.35), q = pt(i, 3); o += '<line x1="' + cx + '" y1="' + cy + '" x2="' + q[0] + '" y2="' + q[1] + '" stroke="var(--border)"/><text class="cell" tabindex="0" role="button" data-need="' + S.key + '" data-k="' + esc(k.id) + '" x="' + p[0] + '" y="' + (p[1] + 4) + '" text-anchor="middle" font-size="12" font-weight="600" fill="var(--text)">' + esc(k.id) + '</text>'; });
    o += poly(caps.map(function () { return 2; }), 'var(--muted)', 'none', true);
    if (best) o += poly(caps.map(function (k) { return ((best.c.coverage || {})[k.id] || {}).score; }), 'var(--info)', 'rgba(60,120,255,.14)');
    o += poly(caps.map(function (k) { return st[k.id].score; }), 'var(--ok)', 'rgba(40,160,90,.22)');
    return o + '</svg><div class="legend"><span><i style="background:var(--muted)"></i>уровень вашего скила (эквивалент = 2)</span>' + (best ? '<span><i style="background:var(--info)"></i>лучший одиночный: ' + esc(best.c.name) + '</span>' : '') + '<span><i style="background:var(--ok)"></i>рекомендуемый набор</span></div>';
  }
  function stackBar(S) {
    var caps = S.capabilities || [], st = stackScores(S), W = 760, ch = 34, cw = (W - 20) / Math.max(1, caps.length), H = 70;
    var colors = ['var(--s0)', 'var(--s1)', 'var(--s2)', 'var(--s3)'];
    var o = '<svg role="group" aria-label="Что закрывает рекомендуемый набор" width="' + W + '" height="' + H + '" viewBox="0 0 ' + W + ' ' + H + '">';
    caps.forEach(function (k, i) { var v = st[k.id].score; o += '<rect class="cell seg" tabindex="0" role="button" data-need="' + S.key + '" data-k="' + esc(k.id) + '" aria-label="' + esc(k.id + ': ' + (v == null ? 'не закрыто' : SCNAME[v])) + '" x="' + (10 + i * cw) + '" y="8" width="' + (cw - 3) + '" height="' + ch + '" rx="5" fill="' + (v == null ? 'var(--sn)' : colors[v]) + '"/><text x="' + (10 + i * cw + (cw - 3) / 2) + '" y="30" text-anchor="middle" font-size="11" fill="var(--text)" pointer-events="none">' + esc(k.id) + '</text>'; });
    return o + '</svg>';
  }

  // ---------- таблица кандидатов ----------
  function candTable(S) {
    var caps = S.capabilities || [], id = 't-' + S.key, rows = (S.candidates || []).map(function (c) { return { c: c, p: covPct(c, caps) }; });
    var kinds = {}; rows.forEach(function (r) { kinds[r.c.kind || '—'] = 1; });
    var h = '<div class="toolbar"><input type="search" placeholder="Поиск по названию…" data-t="' + id + '" aria-label="Поиск"><select data-t="' + id + '" data-f="kind" aria-label="Вид"><option value="">Все виды</option>' + Object.keys(kinds).map(function (k) { return '<option>' + esc(k) + '</option>'; }).join('') + '</select><select data-t="' + id + '" data-f="verdict" aria-label="Вердикт"><option value="">Любой вердикт</option><option value="replace">заменяет</option><option value="partial">частично</option><option value="inspire">идеи</option><option value="ignore">не подходит</option></select><label><input type="checkbox" data-t="' + id + '" data-f="osi"> только OSI-лицензии</label><span class="muted small" id="' + id + '-n"></span></div>';
    h += '<div class="tbl"><table id="' + id + '"><thead><tr><th data-k="name">Название</th><th data-k="kind">Вид</th><th data-k="stars">Звёзды</th><th data-k="last_commit">Обновлён</th><th data-k="license">Лицензия</th><th data-k="p">Покрытие</th><th data-k="verdict">Вердикт</th></tr></thead><tbody></tbody></table></div>';
    setTimeout(function () { initTable(S, id, rows); }, 0);
    return h;
  }
  function initTable(S, id, rows) {
    var T = $('#' + id); if (!T) return; var sort = { k: 'p', d: -1 }, q = '', kind = '', ver = '', osi = false;
    function val(r, k) { return k === 'p' ? r.p : k === 'name' ? (r.c.name || '').toLowerCase() : k === 'stars' ? (r.c.stars == null ? -1 : r.c.stars) : (r.c[k] == null ? '' : String(r.c[k]).toLowerCase()); }
    function draw() {
      var list = rows.filter(function (r) { return (!q || (r.c.name || '').toLowerCase().indexOf(q) >= 0) && (!kind || r.c.kind === kind) && (!ver || r.c.verdict === ver) && (!osi || r.c.osi_license === true); });
      list.sort(function (a, b) { var x = val(a, sort.k), y = val(b, sort.k); return (x > y ? 1 : x < y ? -1 : 0) * sort.d; });
      $('tbody', T).innerHTML = list.map(function (r) { var c = r.c, v = VERDICT[c.verdict] || ['—', 'b-n']; return '<tr class="row" tabindex="0" data-s="' + S.key + '" data-c="' + esc(c.id) + '"><td><b>' + esc(c.name) + '</b></td><td>' + esc(c.kind || '') + '</td><td class="num">' + num(c.stars) + '</td><td>' + esc(c.last_commit || '—') + '</td><td>' + esc(c.license || '—') + '</td><td><span class="bart"><span class="bar" style="width:' + r.p * 0.7 + 'px"></span></span>' + r.p + '%</td><td><span class="badge ' + v[1] + '">' + v[0] + '</span></td></tr>'; }).join('');
      var n = $('#' + id + '-n'); if (n) n.textContent = 'Показано ' + list.length + ' из ' + rows.length;
    }
    $$('th[data-k]', T).forEach(function (th) { th.onclick = function () { var k = th.getAttribute('data-k'); sort = { k: k, d: sort.k === k ? -sort.d : (k === 'name' || k === 'kind' || k === 'license' ? 1 : -1) }; draw(); }; });
    $$('[data-t="' + id + '"]').forEach(function (e) { e.oninput = e.onchange = function () { var f = e.getAttribute('data-f'); if (!f) q = e.value.toLowerCase(); else if (f === 'kind') kind = e.value; else if (f === 'verdict') ver = e.value; else if (f === 'osi') osi = e.checked; draw(); }; });
    draw();
  }

  // ---------- разделы ----------
  function sectionSummary() {
    var O = R.overview || {}, h = '<section id="summary"><h2>Итог одной страницей</h2><p class="lead">' + esc(O.headline || 'Можно ли не развивать свои скилы, а пользоваться готовыми сторонними продуктами?') + '</p>';
    (O.summary_paragraphs || []).forEach(function (p) { h += '<p>' + esc(p) + '</p>'; });
    h += '<div class="cards">';
    R.skills.forEach(function (S) {
      var v = S.verdict || {}, can = CAN[v.can_replace] || ['—', 'b-n', ''], b = bestSingle(S), n = (S.candidates || []).length;
      h += '<div class="card"><h3>' + esc(S.name) + '</h3><p class="muted small">' + esc(S.subtitle) + '</p><p><span class="badge ' + can[1] + '">' + can[0] + '</span></p><p>' + esc(v.headline || '') + '</p><dl class="kv"><dt>Кандидатов</dt><dd>' + n + '</dd><dt>Лучший одиночный</dt><dd>' + (b ? esc(b.c.name) + ' — ' + b.p + ' %' : '—') + '</dd><dt>Рекомендуемый набор</dt><dd>' + stackPct(S) + ' % (эквивалент или лучше: ' + stackEq(S) + ' из ' + (S.capabilities || []).length + ')</dd><dt>Усилия на переход</dt><dd>' + (v.migration_effort_days == null ? '—' : v.migration_effort_days + ' дн.') + '</dd><dt>Развивать своё</dt><dd>' + esc({ yes: 'да', partial: 'частично', no: 'нет' }[v.keep_developing] || '—') + '</dd></dl><p><a href="#s-' + S.key + '">Подробнее →</a></p></div>';
    });
    h += '</div>';
    var tb = O.recommendation_table; if (tb && tb.length) {
      h += '<h3>Решение по каждому скилу</h3><div class="tbl"><table><thead><tr><th>Скил</th><th>Решение</th><th>Чем заменить</th><th>Почему</th><th>Что оставить своим</th></tr></thead><tbody>' + tb.map(function (r) { return '<tr><td><b>' + esc(r.skill) + '</b></td><td>' + esc(r.decision) + '</td><td>' + esc(r.replace_with) + '</td><td>' + esc(r.why) + '</td><td>' + esc(r.keep) + '</td></tr>'; }).join('') + '</tbody></table></div>';
    }
    (O.caveats || []).length && (h += '<h3>Оговорки</h3>' + ul(O.caveats));
    return h + '</section>';
  }
  function sectionSkill(S) {
    var v = S.verdict || {}, can = CAN[v.can_replace] || ['—', 'b-n', ''], caps = S.capabilities || [];
    var h = '<section id="s-' + S.key + '"><h2>' + esc(S.name) + '</h2><p class="lead">' + esc(S.subtitle) + '</p>';
    h += '<div class="verdict ' + can[2] + '"><p><span class="badge ' + can[1] + '">' + can[0] + '</span> <b>' + esc(v.headline || '') + '</b></p><p>' + esc(v.explanation || '') + '</p>' +
      ((v.replace_with || []).length ? '<p><b>Рекомендуемый набор:</b> ' + v.replace_with.map(function (id) { var c = byId(S, id); return c ? '<a href="#" data-open="#cand/' + S.key + '/' + c.id + '">' + esc(c.name) + '</a>' : esc(id); }).join(', ') + '</p>' : '') +
      ((v.lost_if_replaced || []).length ? '<p><b>Что вы потеряете:</b></p>' + ul(v.lost_if_replaced) : '') +
      (v.keep_developing_what ? '<p><b>Развивать своё:</b> ' + esc({ yes: 'да', partial: 'частично', no: 'нет' }[v.keep_developing] || '') + ' — ' + esc(v.keep_developing_what) + '</p>' : '') +
      ((v.risks || []).length ? '<p><b>Риски замены:</b></p>' + ul(v.risks) : '') + (v.cost_notes ? '<p class="muted small">' + esc(v.cost_notes) + '</p>' : '') + '</div>';
    h += '<h3>Возможности вашего скила и что их закрывает</h3><p class="muted small">Каждый квадрат — возможность из рекомендуемого набора: цвет — уровень покрытия лучшим кандидатом набора; клик — кто закрывает и что остаётся вашим.</p><div class="chart">' + stackBar(S) + '<div class="legend">' + SC.map(function (c, i) { return '<span><i style="background:var(--' + c + ')"></i>' + SCNAME[i] + '</span>'; }).join('') + '<span><i style="background:var(--sn);border:1px dashed var(--border)"></i>не закрыто</span></div></div>';
    h += '<ul class="tight small">' + caps.map(function (k) { return '<li><b>' + esc(k.id) + '</b> — ' + esc(k.name) + (k.desc ? ': <span class="muted">' + esc(k.desc) + '</span>' : '') + '</li>'; }).join('') + '</ul>';
    h += '<h3>Матрица покрытия: возможности × кандидаты</h3><p class="muted small">Клик по ячейке — примечание и ссылки-доказательства. Колонки отсортированы по общему покрытию (до 16 лучших).</p><div class="chart">' + heatmap(S) + '<div class="legend">' + SC.map(function (c, i) { return '<span><i style="background:var(--' + c + ')"></i>' + i + ' — ' + SCNAME[i] + '</span>'; }).join('') + '<span><i style="background:var(--sn)"></i>· не проверено</span></div></div>';
    h += '<div class="cards"><div><h3>Покрытие и популярность</h3><div class="chart">' + bubble(S) + '</div></div><div><h3>Радар возможностей</h3><div class="chart">' + radar(S) + '</div></div></div>';
    h += '<h3>Все кандидаты (' + (S.candidates || []).length + ')</h3>' + candTable(S);
    return h + '</section>';
  }
  function sectionEco() {
    var E = R.ecosystems; if (!E) return '';
    var fam = E.capabilities || [], cs = E.candidates || [];
    var h = '<section id="ecosystems"><h2>Крупные коллекции и каталоги, в том числе ECC</h2><p class="lead">Коллекции — это источники готовых скилов. Ячейка показывает, насколько семейство ваших скилов закрыто содержимым коллекции; клик — конкретные скилы внутри с ссылками.</p>';
    if (E.verdict) { h += '<div class="verdict ' + ((CAN[E.verdict.can_replace] || [])[2] || '') + '"><p><b>' + esc(E.verdict.headline || '') + '</b></p><p>' + esc(E.verdict.explanation || '') + '</p></div>'; }
    var lw = 230, cw = 120, ch = 34, top = 56, W = lw + fam.length * cw + 10, H = top + cs.length * ch + 10, colors = ['var(--s0)', 'var(--s1)', 'var(--s2)', 'var(--s3)'];
    var o = '<svg role="group" aria-label="Коллекции × семейства скилов" width="' + W + '" height="' + H + '" viewBox="0 0 ' + W + ' ' + H + '">';
    fam.forEach(function (f, i) { o += '<text x="' + (lw + i * cw + cw / 2) + '" y="' + (top - 14) + '" text-anchor="middle" font-size="12" font-weight="600" fill="var(--text)">' + esc(f.name || f.id) + '</text>'; });
    cs.forEach(function (c, j) {
      var y = top + j * ch; o += '<text x="' + (lw - 8) + '" y="' + (y + ch / 2 + 4) + '" text-anchor="end" font-size="12" fill="var(--text)">' + esc(shortName(c.name, 32)) + '</text>';
      fam.forEach(function (f, i) { var x = (c.coverage || {})[f.id] || {}, v = x.score; o += '<rect class="cell" tabindex="0" role="button" data-eco="' + esc(c.id) + '" data-f="' + esc(f.id) + '" aria-label="' + esc(c.name + ' — ' + (f.name || f.id) + ': ' + (v == null ? 'не проверено' : SCNAME[v])) + '" x="' + (lw + i * cw) + '" y="' + y + '" width="' + (cw - 3) + '" height="' + (ch - 3) + '" rx="5" fill="' + (v == null ? 'var(--sn)' : colors[v]) + '"/><text x="' + (lw + i * cw + cw / 2) + '" y="' + (y + ch / 2 + 3) + '" text-anchor="middle" font-size="12" pointer-events="none" fill="var(--text)">' + (v == null ? '·' : v) + '</text>'; });
    });
    h += '<div class="chart">' + o + '</svg></div><h3>Коллекции подробнее</h3><div class="tbl"><table><thead><tr><th>Коллекция</th><th>Звёзды</th><th>Обновлена</th><th>Лицензия</th><th>Вердикт</th></tr></thead><tbody>' + cs.map(function (c) { var v = VERDICT[c.verdict] || ['—', 'b-n']; return '<tr class="row" tabindex="0" data-eco="' + esc(c.id) + '"><td><b>' + esc(c.name) + '</b><br><span class="muted small">' + esc(shortName(c.summary || '', 140)) + '</span></td><td class="num">' + num(c.stars) + '</td><td>' + esc(c.last_commit || '—') + '</td><td>' + esc(c.license || '—') + '</td><td><span class="badge ' + v[1] + '">' + v[0] + '</span></td></tr>'; }).join('') + '</tbody></table></div>';
    return h + '</section>';
  }
  function ecoPanel(c, fid) {
    var fam = (R.ecosystems || {}).capabilities || [], h = '<h3>' + esc(c.name) + '</h3><p>' + link(c.url, 'Открыть') + '</p><p>' + esc(c.summary || '') + '</p>';
    h += '<dl class="kv"><dt>Звёзды</dt><dd>' + num(c.stars) + '</dd><dt>Форки</dt><dd>' + num(c.forks) + '</dd><dt>Обновлена</dt><dd>' + esc(c.last_commit || '—') + '</dd><dt>Лицензия</dt><dd>' + esc(c.license || '—') + '</dd><dt>Контрибьюторов</dt><dd>' + num(c.contributors) + '</dd></dl>';
    h += '<h4>Сильные стороны</h4>' + ul(c.strengths) + '<h4>Слабые стороны</h4>' + ul(c.weaknesses) + '<h4>Риски</h4>' + ul(c.risks);
    fam.forEach(function (f) { var x = (c.coverage || {})[f.id] || {}; h += '<div class="covrow"' + (f.id === fid ? ' style="background:var(--surface2)"' : '') + '><b>' + esc(f.name || f.id) + '</b> ' + chipFor(x.score) + '<br><span class="small">' + esc(x.note || '') + '</span>' + ((x.items || []).length ? '<ul class="tight small">' + x.items.map(function (it) { return '<li>' + (it.url ? link(it.url, it.name || it.url) : esc(it.name)) + (it.covers ? ' — ' + esc(Array.isArray(it.covers) ? it.covers.join(', ') : it.covers) : '') + (it.note ? ': ' + esc(it.note) : '') + '</li>'; }).join('') + '</ul>' : '') + '</div>'; });
    openPanel(h, '#eco/' + c.id + (fid ? '/' + fid : ''));
  }
  function sectionPlan() {
    var O = R.overview || {}, pl = O.action_plan || []; if (!pl.length) return '';
    return '<section id="plan"><h2>Что делать дальше</h2><ol>' + pl.map(function (p) { return '<li><b>' + esc(p.step) + '</b> — ' + esc(p.what) + (p.why ? '<br><span class="muted small">' + esc(p.why) + '</span>' : '') + ((p.links || []).length ? '<br>' + p.links.map(function (l) { return link(l.url, l.title); }).join(' · ') : '') + '</li>'; }).join('') + '</ol></section>';
  }
  function sectionSources() {
    var s = R.sources || [], areas = {}; s.forEach(function (x) { areas[x.area] = 1; });
    var h = '<section id="sources"><h2>Источники (' + s.length + ')</h2><p class="lead">Все ссылки открываются в новой вкладке. Дата — когда страница была проверена.</p><div class="toolbar"><input type="search" id="src-q" placeholder="Фильтр по названию или адресу…" aria-label="Фильтр источников"><select id="src-a"><option value="">Все разделы</option>' + Object.keys(areas).map(function (a) { return '<option>' + esc(a) + '</option>'; }).join('') + '</select><span class="muted small" id="src-n"></span></div><div class="tbl"><table><thead><tr><th>Источник</th><th>Раздел</th><th>Проверено</th><th>Для чего</th></tr></thead><tbody id="src-b"></tbody></table></div></section>';
    setTimeout(function () {
      function d() { var q = ($('#src-q').value || '').toLowerCase(), a = $('#src-a').value; var l = s.filter(function (x) { return (!a || x.area === a) && (!q || ((x.title || '') + ' ' + x.url).toLowerCase().indexOf(q) >= 0); }); $('#src-b').innerHTML = l.map(function (x) { return '<tr><td>' + link(x.url, x.title || x.url) + '</td><td>' + esc(x.area) + '</td><td>' + esc(x.date_checked || '') + '</td><td class="small">' + esc(x.used_for || '') + '</td></tr>'; }).join(''); $('#src-n').textContent = l.length + ' из ' + s.length; }
      $('#src-q').oninput = d; $('#src-a').onchange = d; d();
    }, 0);
    return h;
  }
  function sectionMethod() {
    return '<section id="method"><h2>Методика</h2><ul class="tight"><li>Для каждого скила описана матрица его возможностей (13–14 пунктов). Каждый кандидат оценён по каждой возможности: 0 — нет, 1 — частично, 2 — эквивалент, 3 — шире или лучше; «не проверено» — когда подтвердить нечем.</li><li>Покрытие, % = сумма оценок ÷ (3 × число возможностей). Это грубая метрика для сравнения, а не итоговое решение: решает вердикт и состав рекомендуемого набора.</li><li>«Рекомендуемый набор» — 1–3 продукта; для каждой возможности берётся лучшая оценка среди них.</li><li>Звёзды, форки, даты и лицензии — из GitHub API и страниц на дату проверки (' + esc((R.meta || {}).date) + '); они быстро меняются.</li><li>Всё из веба — данные, а не инструкции; ничего не устанавливалось, не публиковалось и не оплачивалось.</li><li>Исследование делали субагенты по общему брифу; оценки и вердикты опираются на открытые страницы, но оценка «эквивалент» — всё равно суждение: перед заменой проверьте кандидата на своих задачах.</li></ul></section>';
  }

  // ---------- сборка страницы ----------
  function build() {
    var h = sectionSummary();
    R.skills.forEach(function (S) { h += sectionSkill(S); });
    h += sectionEco() + sectionPlan() + sectionSources() + sectionMethod();
    $('#main').innerHTML = '<h1 style="margin:0 0 4px;font-size:30px">' + esc((R.meta || {}).title) + '</h1><p class="lead">Исследование от ' + esc((R.meta || {}).date) + ': ваши четыре скила против готовых сторонних продуктов. Диаграммы кликабельны, ссылки ведут на источники.</p>' + h;
    var nav = '<h1>Замена скилов сторонними</h1><a href="#summary">Итог</a><div class="grp">Скилы</div>' + R.skills.map(function (S) { return '<a href="#s-' + S.key + '">' + esc(S.name) + '</a>'; }).join('') + '<div class="grp">Дальше</div>' + ((R.ecosystems) ? '<a href="#ecosystems">Коллекции и ECC</a>' : '') + '<a href="#plan">Что делать</a><a href="#sources">Источники</a><a href="#method">Методика</a><button id="theme" type="button">Тема: авто</button>';
    $('#nav').innerHTML = nav;
    var th = $('#theme'); th.onclick = function () { var c = document.documentElement.getAttribute('data-theme'), n = c === 'dark' ? 'light' : c === 'light' ? '' : 'dark'; if (n) document.documentElement.setAttribute('data-theme', n); else document.documentElement.removeAttribute('data-theme'); try { localStorage.setItem('rep-theme', n); } catch (e) { } th.textContent = 'Тема: ' + (n === 'dark' ? 'тёмная' : n === 'light' ? 'светлая' : 'авто'); };
  }
  function find(key) { return R.skills.filter(function (S) { return S.key === key; })[0]; }
  document.addEventListener('click', function (e) {
    var t = e.target.closest('[data-c],[data-need],[data-eco],tr.row'); if (!t || t.closest('#panel')) return;
    if (t.hasAttribute('data-eco')) { var E = (R.ecosystems || {}).candidates || [], c = E.filter(function (x) { return x.id === t.getAttribute('data-eco'); })[0]; if (c) ecoPanel(c, t.getAttribute('data-f')); return; }
    var S = find(t.getAttribute('data-s') || t.getAttribute('data-need')); if (!S) return;
    if (t.hasAttribute('data-need')) { var k = (S.capabilities || []).filter(function (x) { return x.id === t.getAttribute('data-k'); })[0]; if (k) stackPanel(S, k, stackScores(S)[k.id]); return; }
    var cand = byId(S, t.getAttribute('data-c')); if (!cand) return;
    var kk = t.getAttribute('data-k'); if (kk) { var cap = (S.capabilities || []).filter(function (x) { return x.id === kk; })[0]; if (cap) return capPanel(S, cand, cap); }
    candPanel(S, cand);
  });
  document.addEventListener('keydown', function (e) { if ((e.key === 'Enter' || e.key === ' ') && e.target && e.target.matches && e.target.matches('.cell,.pt,tr.row')) { e.preventDefault(); e.target.click(); } });
  function route(h) {
    var p = String(h || location.hash).replace(/^#/, '').split('/');
    var sec = p[1] && document.getElementById('s-' + p[1]); if (sec && /^(cand|cap|need)$/.test(p[0])) sec.scrollIntoView();
    if (p[0] === 'cand') { var S = find(p[1]); var c = S && byId(S, p[2]); if (c) { candPanel(S, c); } }
    else if (p[0] === 'cap') { var S2 = find(p[1]); var c2 = S2 && byId(S2, p[3]); var k2 = S2 && (S2.capabilities || []).filter(function (x) { return x.id === p[2]; })[0]; if (c2 && k2) capPanel(S2, c2, k2); }
    else if (p[0] === 'need') { var S3 = find(p[1]); var k3 = S3 && (S3.capabilities || []).filter(function (x) { return x.id === p[2]; })[0]; if (k3) stackPanel(S3, k3, stackScores(S3)[k3.id]); }
    else if (p[0] === 'eco') { var c4 = ((R.ecosystems || {}).candidates || []).filter(function (x) { return x.id === p[1]; })[0]; if (c4) ecoPanel(c4, p[2]); }
    else if (h && h.charAt(0) === '#') { var t = document.getElementById(p[0]); if (t) t.scrollIntoView(); }
  }
  window.addEventListener('hashchange', function () { route(); });
  build();
  if (location.hash) setTimeout(function () { route(); }, 50);
  window.REPORT_API = { stackPct: stackPct, covPct: covPct };
})();
