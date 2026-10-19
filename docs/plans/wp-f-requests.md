# WP-F — запросы к чужим файлам

## D (оркестрация, ворота)

1. **`references/safety.md`** (FB-031) — в раздел «Внешний мир — только чтение» добавить: «Скриншоты конкурентов: `shoot_competitors.mjs` по умолчанию ничего не нажимает на чужих сайтах — баннер согласия на cookie скрывается стилем только в нашей копии страницы (`cookie: hidden`). Клик «Принять» (`--accept-cookies`) — согласие от имени пользователя: только осознанно, с причиной в отчёте; карточка получает `cookie: accepted`.»
2. **`scripts/check_paths.py` / `scripts/build_all.py`** (FB-008, критерий «параллельные агенты макетов не меняют файлы набора») — после волны макетов вызывать `python3 scripts/mockup_kit.py verify <OUT>` (код 1 — список изменённых файлов набора; нет `build/kit.lock` — код 2, пропустить). Разрешённые пути брифов уже запрещают набор (в «Выдаче» брифов — «не трогать»); `verify` ловит правки и вне снимка волны.
3. **`scripts/report.py`** (FB-009) — в «Расхождения и решения» вывести числа из `build/collect-gaps.json` (`drafts_added`, `fact_check_added`, `mismatches_open`) и решения по записям `data/fact-check.json` с `kind: mockup_vs_registry` (`status`, `decision`). Вывод `design.chosen_by` уже есть — спасибо.
4. **`scripts/render_brief.py`** — ворота FB-007 уже сделаны; просьба: (а) в сообщении об отказе (строка ≈1380) назвать команды `mockup_kit.py directions <OUT>` и `mockup_kit.py choose <OUT> --direction <id> --by owner` (или вызвать `mockup_kit.design_gate(cfg, steps)` — одна формулировка); (б) `{KIT_CLASSES}` — добавить классы набора 1.3 (`ps-chart`, `ps-legend`, `ps-level`, `ps-kbd`, `ps-slider`, `ps-fresh`, `ps-stepper`, `ps-counter`, `ps-msg`, `ps-fn`, `ps-yes/no/unk`, `ps-site-header/footer`, `ps-actionbar`, `pm-actionbar`), если резолвер берёт список не из `_kit.css` автоматически.
5. **`scripts/init_run.py --status`** — «что открыть сейчас» на C8: `mockups/gallery.html` (после `mockup_kit.py gallery`) и `design/directions.md`.
6. **`tests/test_assemble.py::test_relocate_run`** падает после правки `relocate_run.py` (новое поле `dir_rel` в результате) — не WP-F, отмечаю для полного прогона.

## C (реестр, контракт данных)

1. **`references/data-contract.md`** — описать: черновики `data/proposals-draft-G8.json` (пишет `link_mockups.py --collect-gaps`: схема контракта, `id` `G8-NN`, `source_group: G8`, `evidence_class: D`, `needs_details: true` — оценки/шаги/effort дописываются до `merge_proposals.py --append G8`; доп. поля `related`, `origin`); записи `data/fact-check.json` с `kind: mockup_vs_registry` (`proposal`, `mockup`, `summary`, `status: open|resolved`, `decision`, плюс совместимые `fact/claim/phase1_value/agent_value/was/now/source/resolved_value`); `build/collect-gaps.json`; поле `cookie: hidden|accepted|none` в `data/competitors.json`; `data/mockups-check.<ключ>.json` → `hotspots {count, untitled, duplicates, incomplete, scale, zones[{id,n,title,what,why,p,sec,x,y,w,h}]}`, `targets`, `layout`, `other_theme`, `badge_by`, `badge_truncated`; файлы `mockups/gallery.html`, `mockups/tokens-<режим>.css`, `build/kit.lock`.
2. **`check_registry.py` / `merge_proposals.py`** — черновик G8 с `needs_details: true` при `--append` стоит предупредить «оценки не дописаны» (сейчас сливается молча с пустыми `scores`/`effort_days: null`). Проверено: `merge_proposals.py --append G8` принимает черновики `--collect-gaps` и пишет `build/id-map.json`.

## E (страница стратегии)

1. Подсветка элементов макетов в лайтбоксе (SM 8): зоны уже снимает `shoot_mockups.mjs` → `data/mockups-check.json → items[].hotspots.zones` (CSS px от угла PNG; `scale` = 2 у мобильных). Ссылка «Открыть интерактивный макет» → `mockups/concepts/<ключ>.html#hs` (включает подсказки `_hotspots.js`; `#hs=<id>` — конкретный элемент). Галерея вариантов — `mockups/gallery.html` (ссылкой из раздела дизайна). Снимок второй темы — `mockups/concepts/<ключ>.theme-<тема>.png` (`items[].other_theme.png`).
2. `templates/README-deliverables.md` — упомянуть `mockups/gallery.html`.

## G (брифы, прототип)

1. FB-033 (один текст бейджа во всём `templates/`): `templates/briefs/prototype-shell.md`, `templates/prototype-kit/README.md`, `templates/prototype-kit/index.html` используют «Концепт продукта, не существующая функция» — заменить на константу набора «Концепт, не существующая функция» (+ « · <продукт> · <дата>»), элемент — с классом `ps-concept-badge`. После замены можно расширить тест `tests/test_design_fb_kit.py::test_fb033_single_badge_text_in_templates` на весь `templates/` (сейчас — только файлы WP-F).
2. `templates/briefs/specs.md` (FB-010, «индекс макетов заранее») — индекс без браузера: `python3 {SKILL_DIR}/scripts/link_mockups.py {OUT} --index-only`.

## Без владельца

- `scripts/make_concept_demo.py:181` — бейдж демо-макетов «Концепт продукта, не существующая функция» без класса `ps-concept-badge` (shoot_mockups найдёт по тексту с предупреждением). Для единообразия — текст-константа и класс; тест `tests/test_concept.py:393` ищет старый текст — менять вместе.
