/* Оболочка прототипа: состояние, переключатель режимов, тема, бейджи. Общий файл — правит только агент оболочки
 * (бриф prototype-shell); режимы подключаются строкой <script src="js/mode-<id>.js"> в index.html и PK.registerMode. */
(function (root) {
  'use strict';
  var PK = root.PK, doc = root.document;
  var THEMES = ['auto', 'light', 'dark'], THEME_LABEL = { auto: 'авто', light: 'светлая', dark: 'тёмная' };

  function applyTheme(t) {
    if (t === 'auto') doc.documentElement.removeAttribute('data-theme');
    else doc.documentElement.setAttribute('data-theme', t);
    var b = doc.getElementById('pk-theme');
    if (b) { b.textContent = 'Тема: ' + THEME_LABEL[t]; b.setAttribute('aria-label', 'Тема: ' + THEME_LABEL[t] + ' (сменить)'); }
  }

  function boot() {
    var modes = PK.modes.list();
    var store = PK.createStore({ mode: modes.length ? modes[0].id : null, theme: 'auto' }, { storageKey: 'pk-state', hash: ['mode'] });
    var ctx = { core: PK.core, data: PK.data, store: store, llm: PK.llm, demoLabel: PK.data.LABEL };
    var nav = doc.getElementById('pk-modes'), view = doc.getElementById('pk-view');
    var demo = doc.getElementById('pk-demo');
    if (demo) demo.textContent = PK.data.LABEL;
    nav.setAttribute('role', 'tablist');
    nav.innerHTML = modes.map(function (m) {
      return '<button type="button" role="tab" class="pk-btn pk-mode" data-mode="' + m.id + '" aria-selected="false">' + m.title + '</button>';
    }).join('');
    function show(id) {
      if (!PK.modes.get(id)) id = modes[0] && modes[0].id;
      if (!id) { view.textContent = 'Режимов нет: зарегистрируйте режим PK.registerMode({...}).'; return; }
      Array.prototype.forEach.call(nav.querySelectorAll('[data-mode]'), function (b) {
        b.setAttribute('aria-selected', String(b.getAttribute('data-mode') === id));
      });
      doc.documentElement.setAttribute('data-mode', id);
      PK.modes.activate(id, view, ctx);
    }
    nav.addEventListener('click', function (e) {
      var b = e.target.closest('[data-mode]');
      if (b) { store.set({ mode: b.getAttribute('data-mode') }); }
    });
    doc.getElementById('pk-theme').addEventListener('click', function () {
      var t = store.get().theme;
      store.set({ theme: THEMES[(THEMES.indexOf(t) + 1) % THEMES.length] });
    });
    store.subscribe(function (s, changed) {
      if (changed.indexOf('mode') !== -1) show(s.mode);
      if (changed.indexOf('theme') !== -1) applyTheme(s.theme);
    });
    applyTheme(store.get().theme);
    show(store.get().mode);
  }

  if (doc.readyState === 'loading') doc.addEventListener('DOMContentLoaded', boot);
  else boot();
})(typeof self !== 'undefined' ? self : this);
