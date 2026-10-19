/* Режим-образец: калькулятор окупаемости личных усилий на ядре PK.core.payback. Замените своим режимом
 * (скопируйте файл в js/mode-<id>.js, поменяйте id/title и разметку). Значения по умолчанию = канон C01
 * (fixtures/canon.json): макет M01-example показывает те же числа — «числа макетов = числа ядра». */
(function (root) {
  'use strict';
  var PK = root.PK;
  var DEFAULTS = { buildHours: 40, maintainHoursPerWeek: 0.5, savedHoursPerWeek: 2.5 };   // = канон C01
  var off = null;

  function field(id, label, value, step) {
    return '<label class="pk-field" for="' + id + '"><span>' + label + '</span>' +
      '<input id="' + id + '" name="' + id + '" type="number" inputmode="decimal" min="0" step="' + step + '" value="' + value + '"></label>';
  }

  PK.registerMode({
    id: 'example',
    title: 'Пример: окупаемость',
    order: 1,
    mount: function (rootEl, ctx) {
      var s = ctx.store.get();
      var v = {
        buildHours: s.buildHours != null ? s.buildHours : DEFAULTS.buildHours,
        maintainHoursPerWeek: s.maintainHoursPerWeek != null ? s.maintainHoursPerWeek : DEFAULTS.maintainHoursPerWeek,
        savedHoursPerWeek: s.savedHoursPerWeek != null ? s.savedHoursPerWeek : DEFAULTS.savedHoursPerWeek
      };
      rootEl.innerHTML =
        '<section class="pk-card" aria-labelledby="ex-h"><h1 id="ex-h">Окупится ли свой инструмент</h1>' +
        '<form class="pk-form" id="ex-form">' +
        field('buildHours', 'Часов на сборку', v.buildHours, 1) +
        field('maintainHoursPerWeek', 'Поддержка, ч/нед', v.maintainHoursPerWeek, 0.25) +
        field('savedHoursPerWeek', 'Экономия, ч/нед', v.savedHoursPerWeek, 0.25) +
        '</form>' +
        '<output class="pk-result" id="ex-out" aria-live="polite"></output>' +
        '<details class="pk-how"><summary>Как посчитано</summary><ul id="ex-how"></ul></details>' +
        '<div class="pk-actions"><button type="button" class="pk-btn" id="ex-explain">Объяснить (шаблон)</button></div>' +
        '<p class="pk-ai" id="ex-ai" aria-live="polite"></p></section>';
      var form = rootEl.querySelector('#ex-form');
      function read() {
        return {
          buildHours: ctx.core.parseNumber(form.buildHours.value),
          maintainHoursPerWeek: ctx.core.parseNumber(form.maintainHoursPerWeek.value),
          savedHoursPerWeek: ctx.core.parseNumber(form.savedHoursPerWeek.value)
        };
      }
      function render() {
        var input = read(), out = rootEl.querySelector('#ex-out');
        try {
          var r = ctx.core.payback(input);
          out.textContent = r.paybackWeeks == null ? 'Не окупится: поддержка больше экономии'
            : 'Окупится за ' + ctx.core.fmt(r.paybackWeeks) + ' нед · за год +' + ctx.core.fmt(r.yearNetHours) + ' ч';
          rootEl.querySelector('#ex-how').innerHTML = r.explain.map(function (x) { return '<li>' + x + '</li>'; }).join('');
          ctx.store.set(input);
        } catch (e) { out.textContent = 'Проверьте ввод: ' + e.message; }
      }
      form.addEventListener('input', render);
      rootEl.querySelector('#ex-explain').addEventListener('click', function () {
        var r = ctx.core.payback(read());
        ctx.llm.explain({ weeks: r.paybackWeeks, net: r.netSavedPerWeek, build: read().buildHours }, {
          mode: 'template',
          template: function (f) {
            return f.weeks == null ? 'Окупаемости нет.' : 'Окупится за ' + ctx.core.fmt(f.weeks) + ' нед при экономии ' +
              ctx.core.fmt(f.net) + ' ч в неделю и ' + ctx.core.fmt(f.build) + ' ч сборки.';
          }
        }).then(function (a) {
          rootEl.querySelector('#ex-ai').textContent = a.text + ' (' + a.verify.label + (a.fallback ? '; ' + a.fallback : '') + ')';
        });
      });
      off = ctx.store.subscribe(function () { /* место для реакции на общее состояние */ });
      render();
    },
    unmount: function () { if (off) off(); off = null; }
  });
})(typeof self !== 'undefined' ? self : this);
