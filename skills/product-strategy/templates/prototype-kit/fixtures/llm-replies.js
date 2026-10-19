/* Фикстуры ответов модели для прототипа и тестов: прототип не зависит от наличия живой модели.
 * Браузер: window.PK_LLM_FIXTURES; Node: module.exports. Ключ — id кейса канона или функции.
 * Ответы содержат только числа из канона — так сверка «N из N» в тестах детерминирована. */
(function (root) {
  var data = [
    { key: 'C01', text: 'Инструмент окупится за 20 недель: чистая экономия 2 ч в неделю против 40 ч сборки.' },
    { key: 'C03', text: 'При экономии 1,5 ч в неделю 30 ч сборки окупятся за 20 недель.' },
    { key: 'bad-number', text: 'Окупится за 12 недель.' },
    { key: 'bad-phrase', text: 'Гарантирую окупаемость за 20 недель.' }
  ];
  if (typeof module === 'object' && module.exports) module.exports = data;
  else root.PK_LLM_FIXTURES = data;
})(typeof self !== 'undefined' ? self : this);
