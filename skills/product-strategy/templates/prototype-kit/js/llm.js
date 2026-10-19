/* Клиент «объяснений ИИ» прототипа (UMD — window.PK.llm / module.exports). Правило: модель чисел не считает —
 * числа приходят из ядра, текст ответа сверяется с ними (core.verifyNumbers) и с запретными формулировками
 * (core.checkForbidden); не прошёл — откат на шаблон с причиной.
 * Источники текста: 'template' (по умолчанию, детерминированный), 'fixture' (fixtures/llm-replies.js — для тестов и
 * снимков), 'live' — только локальная модель (127.0.0.1 / localhost) и только по действию пользователя
 * (opts.userInitiated === true). Других внешних запросов прототип не делает. */
(function (root, factory) {
  var api = factory(root);
  if (typeof module === 'object' && module.exports) module.exports = api;
  else { root.PK = root.PK || {}; root.PK.llm = api; }
})(typeof self !== 'undefined' ? self : this, function (root) {
  'use strict';
  var core = (root.PK && root.PK.core) || (typeof require === 'function' ? require('./core.js') : null);
  var DEFAULT_FORBIDDEN = ['гарантирую', 'гарантированно', 'без риска', 'точно заработаете'];

  function isLocalEndpoint(url) {
    try {
      var u = new URL(url);
      return (u.protocol === 'http:' || u.protocol === 'https:') && (u.hostname === '127.0.0.1' || u.hostname === 'localhost' || u.hostname === '[::1]');
    } catch (e) { return false; }
  }

  function templateText(facts, opts) {
    if (opts && typeof opts.template === 'function') return opts.template(facts);
    return Object.keys(facts || {}).map(function (k) { return k + ': ' + core.fmt(facts[k]); }).join('; ') + '.';
  }

  function fixtureText(opts) {
    var list = (opts && opts.fixtures) || root.PK_LLM_FIXTURES || (typeof require === 'function' ? safeRequire('../fixtures/llm-replies.js') : []) || [];
    var key = opts && opts.fixture;
    var hit = list.filter(function (x) { return x.key === key; })[0] || list[0];
    return hit ? hit.text : '';
  }

  function safeRequire(p) { try { return require(p); } catch (e) { return null; } }

  function check(text, facts, opts) {
    var v = core.verifyNumbers(text, facts);
    var f = core.checkForbidden(text, (opts && opts.forbidden) || DEFAULT_FORBIDDEN);
    var reason = !f.ok ? 'запретная формулировка: ' + f.hits.join(', ')
      : v.unmatched.length ? 'несверенные числа: ' + v.unmatched.join(', ') : null;
    return { verify: v, forbidden: f, reason: reason };
  }

  function finish(text, source, facts, opts) {
    var c = check(text, facts, opts);
    if (c.reason && source !== 'template') {
      var t = templateText(facts, opts);
      var c2 = check(t, facts, opts);
      return { text: t, source: 'template', fallback: c.reason, verify: c2.verify, forbidden: c2.forbidden };
    }
    return { text: text, source: source, fallback: null, verify: c.verify, forbidden: c.forbidden };
  }

  /* explain(facts, opts) → Promise<{text, source, fallback, verify: {label…}, forbidden}> */
  function explain(facts, opts) {
    opts = opts || {};
    var mode = opts.mode || 'template';
    if (mode === 'fixture') return Promise.resolve(finish(fixtureText(opts), 'fixture', facts, opts));
    if (mode === 'live') {
      if (!opts.userInitiated) return Promise.resolve(finish(templateText(facts, opts), 'template', facts, Object.assign({}, opts)));
      if (!isLocalEndpoint(opts.endpoint)) return Promise.reject(new Error('разрешена только локальная модель (127.0.0.1/localhost)'));
      var ctrl = typeof AbortController !== 'undefined' ? new AbortController() : null;
      var timer = ctrl ? setTimeout(function () { ctrl.abort(); }, opts.timeoutMs || 90000) : null;
      return fetch(opts.endpoint, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, signal: ctrl ? ctrl.signal : undefined,
        body: JSON.stringify(opts.body || { facts: facts })
      }).then(function (r) { return r.json(); }).then(function (j) {
        var text = (opts.pick ? opts.pick(j) : (j && (j.text || (j.message && j.message.content) || j.response))) || '';
        return finish(String(text), 'live', facts, opts);
      }).catch(function (e) {
        var r = finish(templateText(facts, opts), 'template', facts, opts);
        r.fallback = 'модель недоступна: ' + (e && e.message);
        return r;
      }).finally(function () { if (timer) clearTimeout(timer); });
    }
    return Promise.resolve(finish(templateText(facts, opts), 'template', facts, opts));
  }

  return { explain: explain, isLocalEndpoint: isLocalEndpoint, DEFAULT_FORBIDDEN: DEFAULT_FORBIDDEN };
});
