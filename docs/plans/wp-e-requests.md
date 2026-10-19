# WP-E → правки чужих файлов (для оркестратора)

## 1. Демо-генераторы: `<title>` у блоков схем (обязательно — иначе падают 4 существующих теста)
`check_flow.mjs` 1.5 (FB-038) падает на блоке схемы без `<title>`, если блок описан в `data/flows.json` (есть `label` или `what`).
Демо-схемы `make_demo.py` и `make_concept_demo.py` описаны (`label`, `what`), а `<title>` в SVG нет → шаг `flowcheck` в `build_all.py`
(когда есть Playwright, например `~/.cache/product-strategy/node`) возвращает код 1, и падают:
`tests/test_site_mode.py::test_concept_demo_build_all[site|single]`, `tests/test_concept.py::test_concept_demo_build_all_strict`,
`tests/test_concept.py::test_concept_demo_build_all_strict_full`.

Правка (одна строка в каждом генераторе) — `<title>` первым дочерним элементом `<g data-node>`:

- `scripts/make_demo.py`, функция `main()`, строка с `<g data-node="user-journey:%d">`:
  было `'<g data-node="user-journey:%d"><rect ...'` → стало `'<g data-node="user-journey:%d"><title>%s: демо</title><rect ...'`
  и в кортеж форматирования добавить подпись блока (`lab`) вторым элементом: `% (k + 1, lab, 10 + 220 * k, fill, 100 + 220 * k, lab)`.
- `scripts/make_concept_demo.py`, строка с `<g data-node="first-use:%d">` (≈ стр. 165–170) — так же: `<title>%s: демо</title>` с подписью блока.

Проверка: `python3 -m pytest tests/test_site_mode.py tests/test_concept.py -q -k build_all` (при установленном Playwright).

Если генераторы трогать нельзя — запасной вариант: в `build_all.py` (WP-D) шаг `flowcheck` запускать с `--no-fail` для демо-прогонов
(`run-config.demo == true`); но правильнее — правка генераторов (демо должно соответствовать брифу flows.md).

## 2. WP-F (`scripts/node/shoot_mockups.mjs`, `templates/mockup-kit/**`): контракт для просмотра макетов на странице
`build_html.py` 1.5 уже читает (необязательно, без данных — прежнее поведение):
- **Вторая тема снимка** — в записи `data/mockups-index.json`: `"themes": {"light": "mockups/concepts/M01.png", "dark": "mockups/concepts/M01-dark.png"}`
  (или короче `png_dark` / `png_light` / `png_alt`). В просмотре появляется кнопка «Тема».
- **Координаты подсказок `data-hs-*`** — `mockups/hotspots.json`:
  `{"version": 1, "mockups": {"<ключ макета>": {"items": [{"n": 1, "id": "cta", "title": "…", "what": "…", "why": "…", "p": ["P001"], "sec": [5], "r": [x, y, w, h]}]}}}`,
  `r` — доли ширины и высоты PNG (0…1). Просьба: при снимке `shoot_mockups.mjs` мерить `[data-hs][data-hs-title]` (рамка — объединение
  с частями `[data-hs="<тот же id>"]`) и писать этот файл. Без файла страница берёт описания прямо из атрибутов HTML (список без зон).
- Ссылка «Открыть интерактивный макет» ведёт на `<html макета>#hs` — режим подсказок `_hotspots.js` (если шаблон его поддерживает).
- Ссылки на `mockups/gallery.html` и `prototype/index.html` (WP-G) показываются в разделе «Макеты», если файлы есть.

## 3. WP-D (`scripts/check_env.py`): причина недоступности Firefox в `build/env.json`
`smoke_html.mjs` 1.5 при неудачном запуске Firefox ставит `engine-load-firefox: skip` с причиной и дописывает причину из `build/env.json`,
если она там есть: первое поле `reason` | `error` | `why` | `note` у ключа, в имени которого есть `firefox`
(например `{"browsers": {"firefox": {"ok": false, "reason": "Could not find profile folder"}}}`). Просьба — записывать так в `check_env.py`.

## 4. WP-D (`scripts/build_all.py`): необязательно
- Порядок шагов: `build_appendix.py --only glossary` до шага `html` — тогда на странице появляются раздел «Глоссарий» и кликабельные термины
  (без файла `research/glossary.md` их нет, страница прежняя).
- Флаг для схем: `check_flow.mjs --strict-titles` в `--strict` (требует `<title>` и у блоков без описания в flows.json) — по желанию.

## 5. WP-G (`templates/briefs/flows.md`): одна фраза
В требования к SVG схемы: «у каждого `<g data-node>` первым дочерним элементом — `<title>` с текстом из `nodes[].what` (подсказка и имя для
экранного диктора); `check_flow.mjs` проверяет».
