/* Ядро расчётов прототипа: чистые функции без DOM и сети (UMD — глобальный PK.core в браузере, module.exports в Node).
 * Правило набора: числа на макетах = числа ядра. Каждая формула воспроизводит канон демо-данных
 * (fixtures/canon.json или <OUT>/data/demo-canon.json), тесты — js/core.test.js (node js/core.test.js).
 * Пример предметной функции — payback(): окупаемость личных усилий (часы разработки против сэкономленных часов).
 * Замените его функциями своего продукта, сохранив общие помощники и формат «Как посчитано». */
(function (root, factory) {
  var core = factory();
  if (typeof module === 'object' && module.exports) module.exports = core;
  else { root.PK = root.PK || {}; root.PK.core = core; }
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  var NBSP = ' ';

  function isNum(x) { return typeof x === 'number' && isFinite(x); }

  function num(x, name) {
    var v = typeof x === 'string' ? parseNumber(x) : x;
    if (!isNum(v)) throw new TypeError('не число: ' + (name || 'значение') + ' = ' + x);
    return v;
  }

  /* «1 234,5», «15,07 %», «−3,2» → число; не число → NaN. */
  function parseNumber(s) {
    if (isNum(s)) return s;
    var t = String(s == null ? '' : s).replace(/[\s  ]/g, '').replace(/[−–]/g, '-').replace(/[%₽$€]|руб\.?/g, '');
    if (/^-?\d+,\d+$/.test(t)) t = t.replace(',', '.');
    else t = t.replace(/,/g, '');
    return /^-?\d+(\.\d+)?$/.test(t) ? parseFloat(t) : NaN;
  }

  function round(x, digits) {
    var k = Math.pow(10, digits || 0);
    return Math.round((x + (x >= 0 ? 1e-12 : -1e-12)) * k) / k;
  }

  /* Округление вверх до шага (цена, лот, минута): roundUpToStep(10.03, 0.05) → 10.05. */
  function roundUpToStep(x, step) {
    num(x, 'x'); num(step, 'step');
    if (step <= 0) throw new RangeError('шаг должен быть > 0');
    return round(Math.ceil(round(x / step, 9)) * step, 10);
  }

  function pct(part, whole, digits) {
    num(part, 'part'); num(whole, 'whole');
    if (whole === 0) return null;
    return round(part / whole * 100, digits == null ? 2 : digits);
  }

  /* Формат по-русски: 1 234,5 (неразрывный пробел между разрядами, запятая). */
  function fmt(x, digits) {
    if (!isNum(x)) return '—';
    var d = digits == null ? (Math.abs(x) >= 100 ? 0 : 2) : digits;
    var s = round(Math.abs(x), d).toFixed(d);
    var p = s.split('.');
    p[0] = p[0].replace(/\B(?=(\d{3})+(?!\d))/g, NBSP);
    return (x < 0 ? '−' : '') + p[0] + (p[1] ? ',' + p[1].replace(/0+$/, '') : '').replace(/,$/, '');
  }

  /* Пример предметной функции. Окупаемость личных усилий:
   *   чистая экономия в неделю = сэкономлено − поддержка;   недель до окупаемости = часы сборки / чистая экономия. */
  function payback(input) {
    var build = num(input.buildHours, 'buildHours');
    var maintain = num(input.maintainHoursPerWeek || 0, 'maintainHoursPerWeek');
    var saved = num(input.savedHoursPerWeek, 'savedHoursPerWeek');
    var net = round(saved - maintain, 4);
    var weeks = net > 0 ? round(build / net, 2) : null;
    return {
      netSavedPerWeek: net,
      paybackWeeks: weeks,
      yearNetHours: round(net * 52 - build, 2),
      explain: [
        'чистая экономия = ' + fmt(saved) + ' − ' + fmt(maintain) + ' = ' + fmt(net) + ' ч/нед',
        weeks == null ? 'окупаемости нет: поддержка съедает экономию'
          : 'окупаемость = ' + fmt(build) + ' ч / ' + fmt(net) + ' ч/нед = ' + fmt(weeks) + ' нед'
      ]
    };
  }

  /* Сверка чисел ответа ИИ с фактами: модель чисел не считает, код проверяет каждое число текста.
   * facts — массив чисел или объект {имя: число}; допуск — относительный (по умолчанию 0,5 %) и по округлению показа.
   * → {total, matched, unmatched: [строки], label: "N из N сверены"} */
  function verifyNumbers(text, facts, opts) {
    var tol = (opts && opts.tolerance) || 0.005;
    var list = [];
    if (Array.isArray(facts)) list = facts.slice();
    else if (facts) Object.keys(facts).forEach(function (k) { list.push(facts[k]); });
    list = list.map(function (v) { return parseNumber(v); }).filter(isNum);
    var re = /[−–-]?\d{1,3}(?:[\s  ]\d{3})+(?:,\d+)?|[−–-]?\d+(?:[.,]\d+)?/g;
    var found = String(text || '').match(re) || [];
    var unmatched = [], matched = 0;
    found.forEach(function (raw) {
      var v = parseNumber(raw);
      if (!isNum(v)) return;
      var dec = (raw.split(/[.,]/)[1] || '').length;
      var half = 0.5 * Math.pow(10, -dec);
      var ok = list.some(function (f) {
        return Math.abs(f - v) <= Math.max(half, Math.abs(f) * tol) || Math.abs(Math.abs(f) - Math.abs(v)) <= half;
      });
      if (ok) matched += 1; else unmatched.push(raw.trim());
    });
    var total = matched + unmatched.length;
    return { total: total, matched: matched, unmatched: unmatched, label: matched + ' из ' + total + ' сверены' };
  }

  /* Фильтр запретных формулировок (право области, обещания): → {ok, hits: [фраза]} */
  function checkForbidden(text, phrases) {
    var t = String(text || '').toLowerCase();
    var hits = (phrases || []).filter(function (p) { return p && t.indexOf(String(p).toLowerCase()) !== -1; });
    return { ok: hits.length === 0, hits: hits };
  }

  /* Вычислить кейс канона по имени функции: {fn: "payback", inputs: {...}} → результат функции ядра. */
  function computeCase(c) {
    var fn = api[c.fn || 'payback'];
    if (typeof fn !== 'function') throw new Error('в ядре нет функции ' + c.fn);
    return fn(c.inputs || {});
  }

  var api = {
    version: '1.5.0',
    parseNumber: parseNumber, round: round, roundUpToStep: roundUpToStep, pct: pct, fmt: fmt,
    payback: payback, verifyNumbers: verifyNumbers, checkForbidden: checkForbidden, computeCase: computeCase
  };
  return api;
});
