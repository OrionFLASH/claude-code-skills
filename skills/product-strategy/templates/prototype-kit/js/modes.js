/* Реестр режимов интерфейса (UMD — window.PK.registerMode / window.PK.modes; module.exports в Node).
 * Контракт режима (один файл js/mode-<id>.js на режим, свой css/mode-<id>.css):
 *   PK.registerMode({
 *     id: 'terminal',            // латиница, цифры, дефис; уникален
 *     title: 'Терминал',         // подпись на переключателе
 *     order: 1,                  // порядок на переключателе (необязательно)
 *     mount: function (root, ctx) { … },   // нарисовать режим в root; ctx = {core, data, store, llm, demoLabel}
 *     unmount: function (root) { … }       // снять подписки и таймеры (необязательно)
 *   });
 * Режим не трогает чужие режимы и общие файлы; общее состояние — только через ctx.store (get/set/subscribe). */
(function (root, factory) {
  var api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else { root.PK = root.PK || {}; root.PK.modes = api; root.PK.registerMode = api.registerMode; }
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';
  var ID_RE = /^[a-z][a-z0-9-]{0,30}$/;
  var registry = [];
  var current = null;

  function registerMode(def) {
    if (!def || typeof def !== 'object') throw new TypeError('registerMode: нужен объект режима');
    if (!ID_RE.test(String(def.id || ''))) throw new TypeError('registerMode: id «' + def.id + '» — латиница, цифры, дефис');
    if (!def.title || typeof def.title !== 'string') throw new TypeError('registerMode: нет title у режима ' + def.id);
    if (typeof def.mount !== 'function') throw new TypeError('registerMode: нет mount(root, ctx) у режима ' + def.id);
    if (def.unmount != null && typeof def.unmount !== 'function') throw new TypeError('registerMode: unmount — функция');
    if (registry.some(function (m) { return m.id === def.id; })) throw new Error('registerMode: режим ' + def.id + ' уже зарегистрирован');
    registry.push({ id: def.id, title: def.title, order: def.order == null ? 100 + registry.length : def.order, def: def });
    return def.id;
  }

  function list() {
    return registry.slice().sort(function (a, b) { return a.order - b.order; })
      .map(function (m) { return { id: m.id, title: m.title, order: m.order }; });
  }

  function get(id) {
    var m = registry.filter(function (x) { return x.id === id; })[0];
    return m ? m.def : null;
  }

  function activate(id, rootEl, ctx) {
    var def = get(id);
    if (!def) throw new Error('нет режима ' + id + ' (есть: ' + list().map(function (m) { return m.id; }).join(', ') + ')');
    if (current && current.def.unmount) {
      try { current.def.unmount(current.root); } catch (e) { if (typeof console !== 'undefined') console.error(e); }
    }
    if (rootEl && 'innerHTML' in rootEl) rootEl.innerHTML = '';
    current = { id: id, def: def, root: rootEl };
    def.mount(rootEl, ctx || {});
    return id;
  }

  function active() { return current ? current.id : null; }

  function reset() { registry = []; current = null; }      // для тестов

  return { registerMode: registerMode, list: list, get: get, activate: activate, active: active, reset: reset };
});
