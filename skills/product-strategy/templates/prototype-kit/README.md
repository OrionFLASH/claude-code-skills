# Рабочий прототип — набор `prototype-kit`

Каркас фазы C8.5 «Рабочий прототип» скилла `product-strategy:product-concept` (правила — `references/prototype.md` скилла).
Копируется в `<OUT>/prototype/` агентом брифа `prototype-core` (`cp -Rn <SKILL_DIR>/templates/prototype-kit/. <OUT>/prototype/`)
и дорабатывается брифами `prototype-shell`, `prototype-mode`, `prototype-regression`.

Прототип — **концепт**, не продукт: бейдж «Концепт, не существующая функция» (та же константа, что у макетов, + « · <продукт> · <дата>»; элемент с
классом `ps-concept-badge`), все данные вымышлены и помечены
«демо-данные», внешних запросов нет.

## Как открыть
Двойной щелчок по `index.html` (Safari, Chrome, Firefox) — работает по `file://`: обычные `<script src>`, без ES-модулей,
сборки, npm и CDN. Интеграция с локальной моделью ИИ (если нужна) — с локального сервера (`python3 -m http.server`),
потому что браузер по `file://` может блокировать запросы к `127.0.0.1`; это ограничение прототипа, а не продукта.

## Структура
| Файл | Что | Кто правит |
|---|---|---|
| `js/core.js` | ядро расчётов: чистые функции без DOM и сети (UMD: `window.PK.core` / `module.exports`) | агент ядра |
| `js/core.test.js` | тесты ядра: воспроизводят канон демо-данных — `node js/core.test.js [канон]` | агент ядра |
| `fixtures/canon.json` | кейсы ядра (`cases`): канон демо-данных, если нет `<OUT>/data/demo-canon.json` или в нём только значения показа (`values`) | агент ядра |
| `tools/check_canon.py` | «числа макетов = числа канона = числа ядра»: `python3 tools/check_canon.py . --core` (макеты без прототипа — `check_canon.py <OUT>`) | — |
| `js/data.js` | детерминированные демо-данные (seed), каждая запись `demo: true` | агент ядра |
| `js/state.js` | общее состояние: `PK.createStore(...)` → `get / set / subscribe`; localStorage и `#hash` в try/catch | агент оболочки |
| `js/modes.js` | реестр режимов: `PK.registerMode({...})`, `PK.modes.list / activate` | агент оболочки |
| `js/llm.js`, `fixtures/llm-replies.js` | объяснения ИИ: шаблон, фикстуры, локальная модель только по клику; сверка чисел и запретных фраз | агент оболочки |
| `js/app.js`, `index.html`, `css/base.css` | оболочка: переключатель режимов, тема, бейджи, токены | агент оболочки |
| `js/mode-<id>.js`, `css/mode-<id>.css`, `tests/smoke-<id>.mjs` | режим интерфейса | агент режима `<id>` (только свои файлы) |
| `js/kit.test.js` | контракт оболочки: режимы, состояние, демо-данные, ИИ на фикстурах — `node js/kit.test.js` | агент оболочки |
| `tests/smoke.mjs` | смоук в браузере: `node tests/smoke.mjs [--webkit] [--mode <id>]` → `shots/` | агент регрессии |
| `HANDOFF.md` | что переносить в боевой стек и расхождения прототип ↔ продукт (создаёт агент регрессии) | агент регрессии |

## Контракт режима
```js
PK.registerMode({
  id: 'terminal',                 // латиница, цифры, дефис; уникален
  title: 'Терминал',              // подпись переключателя
  order: 2,                       // порядок (необязательно)
  mount: function (root, ctx) {   // ctx = {core, data, store, llm, demoLabel}
    // рисовать только внутри root; числа — только из ctx.core и канона; подписки — ctx.store.subscribe(fn)
  },
  unmount: function (root) {}     // снять подписки и таймеры
});
```
Подключение: `<script src="js/mode-<id>.js"></script>` в `index.html` перед `js/app.js` (правит агент оболочки или
регрессии — общий файл). Токены режима — `css/tokens-<id>.css` с селектором `:root[data-mode="<id>"]` (оболочка ставит
`data-mode` на `<html>`).

## Правила
- Числа макетов = числа ядра: значения на макетах помечаются `data-canon="<ключ>"`, повторяющиеся элементы графика —
  `data-canon-item="<ключ>"`; ключ — `<кейс>.<поле>` кейса ядра (`C01.paybackWeeks`) или ключ `values` канона прогона
  (`model.price_month` — черновик `facts_scaffold.py <OUT> --demo-canon`); ядро и макеты сверяются с одним каноном
  (`tools/check_canon.py`). Канон прогона `data/demo-canon.json` главный; если в нём только значения показа (`values`) без
  кейсов (`cases`), кейсы ядра лежат в `fixtures/canon.json` (их ожидаемые числа — те же, что в `values`), и
  `core.test.js`/`check_canon.py` берут их оттуда сами.
- Демо-данные помечены (`demo: true`, бейдж); реальные названия брендов — только в справочниках, цены и объёмы вымышлены.
- Без внешних запросов: единственное исключение — локальная модель (`127.0.0.1` / `localhost`) по действию пользователя.
- Тесты не зависят от живой модели: ответы ИИ — из фикстур; тест с живой моделью — отдельный и необязательный.
- Общие файлы (`index.html`, `js/app.js`, `js/state.js`, `js/modes.js`, `css/base.css`, `tests/smoke.mjs`, `README.md`)
  правит один владелец; агенты режимов пишут только свои `mode-<id>.*` и снимки `shots/<браузер>-<id>-*.png`.
