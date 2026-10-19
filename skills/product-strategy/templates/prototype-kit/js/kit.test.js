/* Контрактные тесты оболочки прототипа без браузера и зависимостей: node js/kit.test.js
 * Реестр режимов (registerMode), общее состояние (subscribe), демо-данные (детерминированы, помечены),
 * объяснения ИИ на фикстурах (сверка чисел, запретные формулировки, откат на шаблон, только локальная модель).
 * Режимы-агенты добавляют свои проверки в tests/, не правя этот файл. Код выхода 0 — всё прошло. */
'use strict';
var assert = require('assert');
var modes = require('./modes.js');
var createStore = require('./state.js').createStore;
var data = require('./data.js');
var llm = require('./llm.js');
var fixtures = require('../fixtures/llm-replies.js');

var passed = 0, failed = 0, failures = [], pending = [];
function test(name, fn) {
  try {
    var r = fn();
    if (r && typeof r.then === 'function') {
      pending.push(r.then(function () { passed += 1; }, function (e) { failed += 1; failures.push(name + ': ' + e.message); }));
    } else passed += 1;
  } catch (e) { failed += 1; failures.push(name + ': ' + (e && e.message)); }
}

test('registerMode: проверка контракта', function () {
  modes.reset();
  assert.throws(function () { modes.registerMode({ id: 'Bad Id', title: 'x', mount: function () {} }); }, /id/);
  assert.throws(function () { modes.registerMode({ id: 'a', mount: function () {} }); }, /title/);
  assert.throws(function () { modes.registerMode({ id: 'a', title: 'A' }); }, /mount/);
  modes.registerMode({ id: 'a', title: 'A', order: 2, mount: function () {} });
  assert.throws(function () { modes.registerMode({ id: 'a', title: 'A2', mount: function () {} }); }, /уже/);
});
test('activate: mount нового и unmount прежнего режима', function () {
  modes.reset();
  var log = [];
  modes.registerMode({ id: 'one', title: 'Один', order: 2, mount: function (r, ctx) { log.push('m1:' + ctx.tag); r.innerHTML = 'one'; },
    unmount: function () { log.push('u1'); } });
  modes.registerMode({ id: 'two', title: 'Два', order: 1, mount: function (r) { log.push('m2'); r.innerHTML = 'two'; } });
  assert.deepStrictEqual(modes.list().map(function (m) { return m.id; }), ['two', 'one']);
  var root = { innerHTML: 'старое' };
  modes.activate('one', root, { tag: 't' });
  modes.activate('two', root, {});
  assert.deepStrictEqual(log, ['m1:t', 'u1', 'm2']);
  assert.strictEqual(root.innerHTML, 'two');
  assert.strictEqual(modes.active(), 'two');
  assert.throws(function () { modes.activate('nope', root, {}); }, /нет режима/);
});
test('createStore: set → subscribe с изменёнными ключами; без localStorage работает', function () {
  var s = createStore({ mode: 'a', theme: 'auto' }, { storageKey: 'pk-test', hash: ['mode'] });
  var seen = [];
  var off = s.subscribe(function (st, changed) { seen.push(changed.join(',') + '=' + st.mode); });
  s.set({ mode: 'b' });
  s.set({ mode: 'b' });                       // без изменений — без уведомления
  off();
  s.set({ mode: 'c' });
  assert.deepStrictEqual(seen, ['mode=b']);
  assert.strictEqual(s.get().mode, 'c');
});
test('data.generate: детерминированно и помечено как демо', function () {
  var a = data.generate(7), b = data.generate(7), c = data.generate(8);
  assert.deepStrictEqual(a, b);
  assert.notDeepStrictEqual(a.items, c.items);
  assert.ok(a.demo && a.items.length > 0 && a.items.every(function (x) { return x.demo === true; }));
  assert.strictEqual(a.label, 'демо-данные');
});
test('llm: фикстура со сверенными числами проходит', function () {
  return llm.explain({ weeks: 20, net: 2, build: 40 }, { mode: 'fixture', fixture: 'C01', fixtures: fixtures }).then(function (r) {
    assert.strictEqual(r.source, 'fixture');
    assert.strictEqual(r.verify.label, '3 из 3 сверены');
    assert.strictEqual(r.fallback, null);
  });
});
test('llm: несверенное число → откат на шаблон с причиной', function () {
  return llm.explain({ weeks: 20 }, { mode: 'fixture', fixture: 'bad-number', fixtures: fixtures }).then(function (r) {
    assert.strictEqual(r.source, 'template');
    assert.ok(/несверенные числа: 12/.test(r.fallback));
  });
});
test('llm: запретная формулировка → откат на шаблон', function () {
  return llm.explain({ weeks: 20 }, { mode: 'fixture', fixture: 'bad-phrase', fixtures: fixtures }).then(function (r) {
    assert.strictEqual(r.source, 'template');
    assert.ok(/запретная формулировка/.test(r.fallback));
  });
});
test('llm: живая модель — только локальная и только по действию пользователя', function () {
  assert.ok(llm.isLocalEndpoint('http://127.0.0.1:11434/api/chat'));
  assert.ok(!llm.isLocalEndpoint('https://api.example.org/v1'));
  return llm.explain({ weeks: 20 }, { mode: 'live', endpoint: 'http://127.0.0.1:11434/api/chat' }).then(function (r) {
    assert.strictEqual(r.source, 'template');                 // без userInitiated запрос не уходит
    return llm.explain({ weeks: 20 }, { mode: 'live', userInitiated: true, endpoint: 'https://api.example.org/v1' })
      .then(function () { throw new Error('внешний адрес не отклонён'); }, function (e) { assert.ok(/локальная модель/.test(e.message)); });
  });
});

Promise.all(pending).then(function () {
  console.log((failed ? 'FAILED' : 'OK') + ': ' + passed + ' passed, ' + failed + ' failed (контракт оболочки)');
  failures.forEach(function (f) { console.log('  ✗ ' + f); });
  process.exit(failed ? 1 : 0);
});
