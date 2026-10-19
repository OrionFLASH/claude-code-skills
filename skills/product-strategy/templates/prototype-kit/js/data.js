/* Детерминированные демо-данные прототипа (UMD — window.PK.data / module.exports). Все записи помечены demo: true,
 * на экране — бейдж «демо-данные». Одинаковый seed → одинаковые данные (снимки и тесты стабильны).
 * Числа, которые показаны на макетах, берутся не отсюда, а из канона (fixtures/canon.json или data/demo-canon.json). */
(function (root, factory) {
  var data = factory();
  if (typeof module === 'object' && module.exports) module.exports = data;
  else { root.PK = root.PK || {}; root.PK.data = data; }
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';
  var LABEL = 'демо-данные';

  /* mulberry32: быстрый детерминированный генератор [0, 1). */
  function rng(seed) {
    var a = seed >>> 0;
    return function () {
      a = (a + 0x6D2B79F5) >>> 0;
      var t = a;
      t = Math.imul(t ^ (t >>> 15), t | 1);
      t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  /* Пример: сценарии «сколько часов экономит инструмент» для списка задач владельца. Замените своей предметной областью. */
  function generate(seed, count) {
    var r = rng(seed == null ? 7 : seed);
    var tasks = ['Сверка данных', 'Отчёт недели', 'Подбор вариантов', 'Проверка расчёта', 'Поиск в архиве', 'Планирование'];
    var items = [];
    for (var i = 0; i < (count || 12); i++) {
      var saved = Math.round((0.5 + r() * 3) * 4) / 4;
      items.push({
        id: 'D' + String(i + 1).padStart(2, '0'),
        title: tasks[i % tasks.length] + ' ' + (Math.floor(i / tasks.length) + 1),
        savedHoursPerWeek: saved,
        maintainHoursPerWeek: Math.round(r() * 0.75 * 4) / 4,
        buildHours: Math.round(10 + r() * 50),
        demo: true
      });
    }
    return { label: LABEL, seed: seed == null ? 7 : seed, demo: true, items: items };
  }

  return { LABEL: LABEL, rng: rng, generate: generate };
});
