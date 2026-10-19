/* Тесты ядра без зависимостей: node js/core.test.js [путь к канону]
 * Канон по умолчанию — ../fixtures/canon.json; канон прогона — node js/core.test.js ../../data/demo-canon.json
 * (или переменная PK_CANON). Каждый кейс канона: {id, fn, inputs, expected} — ядро обязано выдать expected
 * (числа с допуском по округлению показа, null — строго null). Код выхода 0 — все тесты прошли. */
'use strict';
var fs = require('fs');
var path = require('path');
var assert = require('assert');
var core = require('./core.js');

var passed = 0, failed = 0, failures = [];
function test(name, fn) {
  try { fn(); passed += 1; } catch (e) { failed += 1; failures.push(name + ': ' + (e && e.message)); }
}
function near(actual, expected, msg) {
  if (expected === null) { assert.strictEqual(actual, null, msg + ': ожидалось null, получено ' + actual); return; }
  if (typeof expected === 'number') {
    var dec = (String(expected).split('.')[1] || '').length;
    var tol = Math.max(0.5 * Math.pow(10, -Math.max(dec, 2)), Math.abs(expected) * 1e-9);
    assert.ok(typeof actual === 'number' && Math.abs(actual - expected) <= tol, msg + ': ожидалось ' + expected + ', получено ' + actual);
    return;
  }
  assert.deepStrictEqual(actual, expected, msg);
}

// ---------------------------------------------------------------- помощники
test('parseNumber: русский формат', function () {
  assert.strictEqual(core.parseNumber('1 234,5'), 1234.5);
  assert.strictEqual(core.parseNumber('15,07 %'), 15.07);
  assert.strictEqual(core.parseNumber('−3,2'), -3.2);
  assert.ok(isNaN(core.parseNumber('abc')));
});
test('roundUpToStep: вверх до шага', function () {
  assert.strictEqual(core.roundUpToStep(10.03, 0.05), 10.05);
  assert.strictEqual(core.roundUpToStep(10, 0.05), 10);
  assert.throws(function () { core.roundUpToStep(1, 0); });
});
test('fmt: разряды и запятая', function () {
  assert.strictEqual(core.fmt(1234.5, 1), '1 234,5');
  assert.strictEqual(core.fmt(20), '20');
  assert.strictEqual(core.fmt(-2.5), '−2,5');
});
test('verifyNumbers: «N из N сверены» и несверенные числа', function () {
  var ok = core.verifyNumbers('Окупится за 20 недель при экономии 2 ч в неделю.', { weeks: 20, net: 2 });
  assert.strictEqual(ok.label, '2 из 2 сверены');
  var bad = core.verifyNumbers('Окупится за 25 недель.', [20]);
  assert.deepStrictEqual(bad.unmatched, ['25']);
});
test('checkForbidden: запретные формулировки', function () {
  assert.deepStrictEqual(core.checkForbidden('Гарантирую результат', ['гарантирую']).hits, ['гарантирую']);
  assert.ok(core.checkForbidden('Расчёт по вашим данным', ['гарантирую']).ok);
});

// ---------------------------------------------------------------- канон: числа макетов = числа ядра
var fixturePath = path.join(__dirname, '..', 'fixtures', 'canon.json');
var canonPath = process.argv[2] || process.env.PK_CANON || fixturePath;
var canon, casesFrom = canonPath;
try { canon = JSON.parse(fs.readFileSync(canonPath, 'utf8')); } catch (e) { failed += 1; failures.push('канон ' + canonPath + ': ' + e.message); }
var cases = canon ? (Array.isArray(canon) ? canon : canon.cases || []) : [];
// Канон прогона из facts_scaffold.py --demo-canon — только значения показа (values) без кейсов ядра:
// кейсы берутся из fixtures/canon.json прототипа (их пишет агент prototype-core).
if (!cases.length && canon && !Array.isArray(canon) && canon.values && path.resolve(canonPath) !== path.resolve(fixturePath)) {
  try {
    var fx = JSON.parse(fs.readFileSync(fixturePath, 'utf8'));
    cases = Array.isArray(fx) ? fx : fx.cases || [];
    casesFrom = fixturePath;
  } catch (e) { /* нет фикстуры — тест «канон не пуст» скажет об этом */ }
}
test('канон не пуст', function () { assert.ok(cases.length > 0, 'в каноне нет кейсов ядра (cases) — их пишет агент prototype-core'); });
cases.forEach(function (c) {
  test('канон ' + c.id + ' (' + (c.title || c.fn || '') + ')', function () {
    var r = core.computeCase(c);
    Object.keys(c.expected || {}).forEach(function (k) { near(r[k], c.expected[k], c.id + '.' + k); });
  });
});

console.log((failed ? 'FAILED' : 'OK') + ': ' + passed + ' passed, ' + failed + ' failed (канон: ' + path.basename(canonPath) + (casesFrom !== canonPath ? ', кейсы: ' + path.basename(casesFrom) : '') + ', кейсов ' + cases.length + ')');
failures.forEach(function (f) { console.log('  ✗ ' + f); });
process.exit(failed ? 1 : 0);
