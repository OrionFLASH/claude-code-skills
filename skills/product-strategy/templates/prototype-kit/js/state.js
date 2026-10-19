/* Общее состояние прототипа (UMD — window.PK.createStore / module.exports.createStore).
 *   var store = PK.createStore({mode: 'example', theme: 'auto'}, {storageKey: 'pk-state', hash: ['mode']});
 *   store.get() → копия состояния; store.set({theme: 'dark'}); var off = store.subscribe(function (state, changed) {…}); off();
 * Сохранение в localStorage и в #hash — в try/catch (file://, приватный режим, Safari): без хранилища всё работает. */
(function (root, factory) {
  var api = factory(root);
  if (typeof module === 'object' && module.exports) module.exports = api;
  else { root.PK = root.PK || {}; root.PK.createStore = api.createStore; }
})(typeof self !== 'undefined' ? self : this, function (root) {
  'use strict';

  function readHash(keys) {
    var out = {};
    try {
      var h = (root.location && root.location.hash || '').replace(/^#/, '');
      h.split('&').forEach(function (kv) {
        var p = kv.split('=');
        if (p[0] && keys.indexOf(p[0]) !== -1) out[p[0]] = decodeURIComponent(p[1] || '');
      });
    } catch (e) { /* нет location */ }
    return out;
  }

  function writeHash(state, keys) {
    try {
      if (!root.history || !root.location) return;
      var h = keys.filter(function (k) { return state[k] != null && state[k] !== ''; })
        .map(function (k) { return k + '=' + encodeURIComponent(state[k]); }).join('&');
      root.history.replaceState(null, '', '#' + h);
    } catch (e) { /* file:// в некоторых браузерах */ }
  }

  function createStore(initial, opts) {
    opts = opts || {};
    var keys = opts.hash || [];
    var state = Object.assign({}, initial || {});
    if (opts.storageKey) {
      try { Object.assign(state, JSON.parse(root.localStorage.getItem(opts.storageKey) || '{}')); } catch (e) { /* нет хранилища */ }
    }
    Object.assign(state, readHash(keys));
    var subs = [];
    return {
      get: function () { return Object.assign({}, state); },
      set: function (patch) {
        var changed = Object.keys(patch || {}).filter(function (k) { return state[k] !== patch[k]; });
        if (!changed.length) return;
        changed.forEach(function (k) { state[k] = patch[k]; });
        if (opts.storageKey) {
          try { root.localStorage.setItem(opts.storageKey, JSON.stringify(state)); } catch (e) { /* нет хранилища */ }
        }
        if (keys.length) writeHash(state, keys);
        subs.slice().forEach(function (fn) { try { fn(Object.assign({}, state), changed); } catch (e) { if (root.console) root.console.error(e); } });
      },
      subscribe: function (fn) {
        subs.push(fn);
        return function () { subs = subs.filter(function (x) { return x !== fn; }); };
      }
    };
  }

  return { createStore: createStore };
});
