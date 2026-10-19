# WP-D — запросы к чужим файлам

Пути — от `skills/product-strategy/`. Каждая правка нужна, чтобы закрыть пункт WP-D целиком; без неё WP-D работает в обход (указано, как).

## WP-A (`scripts/intake.py`, `scripts/concept_dossier.py`)
1. **`concept_dossier.idea_facts`: брать `version`, `pitch_v2`, `history` из run-config `idea.*`** (FB-044). Сейчас `data/idea.json` пересобирается с `"version": 1` при каждом шаге `dossier` в `build_all.py`; WP-D возвращает поля после шага (`pivot_check.sync_idea_json`), но правильнее — в источнике. Желательно, чтобы после пивота затравки и план поиска строились по `pitch_v2`. Флаг `concept_dossier.py --refresh` `pivot_check.py` вызывает, если он есть (иначе — без флагов).
2. **`intake.write_config` и чтение `output.dir`/`repo.path` — через `Path(...).expanduser()`** (FB-017): тогда `relocate_run.py <OUT> --portable-config` (пути run-config с `~` без имени пользователя) безопасен для `intake.py update`. До этой правки `--portable-config` — только опция, по умолчанию пути абсолютные.
3. **Вопрос «Скриншоты конкурентов: в git / только локально / сжатые превью»** в сводке «Начинаю?», если `project.repo_visibility` не `private` (FB-042) → `output.competitor_shots: git | local | previews`; `check_gitignore.py` читает это поле.
4. В сводке «Начинаю?» показать: прогноз `dispatch.py <OUT> forecast` (или `--fast`), состояние git `check_env.py --git-state` (строка «git: пустой репозиторий (нет коммитов)» и план), чек-лист (`init_run.tasks_target(out, cfg)` → `TASKS.md` владельца или `STRATEGY_TASKS.md`).
5. `idea.keywords` (подтверждённые ключевые слова) — `render_brief.py` берёт `{KEYWORDS}` из этого поля в первую очередь (FB-023).
6. Тест `tests/test_render_brief.py::test_concept_briefs[concept-analogs]` ждёт ключевые слова «демо, обмена, книгами» — после изменения `concept_dossier.keywords` (FB-022) порядок другой («обмена, книгами, соседями…»): обновить ожидание (поведение WP-D здесь не менялось).

## WP-B (`scripts/plan_baseline.py`)
7. **`plan_baseline.py <OUT> --check`**: код 0 — даты и числа вех в частях текста совпадают с `data/plan-baseline.json` (или заданы `{plan:…}`), код 1 — расхождения (последняя строка — сводка). Шаг `consistency` в `build_all.py` вызывает именно эту команду: код 1 — WARN, в `--strict` — провал (FB-046).

## WP-C (`references/data-contract.md`, `scripts/collect_reports.py`, `scripts/merge_proposals.py`)
8. `data-contract.md:174` («`STRATEGY_TASKS.md` вместо `TASKS.md`») → «чек-лист один: блок фаз в `TASKS.md` владельца (если есть или требует CLAUDE.md) между метками `<!-- product-strategy:phases <OUT> -->`, иначе `STRATEGY_TASKS.md`» (FB-040). Добавить поля из `docs/plans/wp-d-notes.md`, раздел 6.
9. `collect_reports.py --retro` читает `build/interventions.jsonl` в формате `{"ts", "by", "what", "why", "file", "kind", "phase"}` (пишет `init_run.py --intervention`; `kind: decision-change` — от `init_run.py --impact`).
10. `fact-check.json`: ворота `build_all.py --strict` считают запись закрытой, если `applied: true`, или `note` содержит «только текст», или `text_only: true` (FB-052).
11. `references/orchestration.md` ссылается на `merge_proposals.py --suggest --write-distinct` (FB-005: отвергнутые пары → `merge-map.json` без ручной правки) — если флаг назван иначе, сообщите, поправлю текст.

## WP-E (`scripts/node/check_flow.mjs`, `scripts/build_html.py`, `scripts/node/smoke_html.mjs`)
12. Новая проверка `node_no_title` в `check_flow.mjs` (FB-038) роняет демо-схемы `make_demo.py`/`make_concept_demo.py` (у их узлов нет `<title>`), и при установленном Playwright падают тесты `test_core::test_build_all_new_steps_and_statuses`, `test_concept::test_concept_demo_build_all_strict(_full)`, `test_site_mode::test_concept_demo_build_all` (шаг `flowcheck` FAIL; поведение WP-D здесь не менялось — при `--skip flowcheck` сборка демо «всё собрано»). Нужны `<title>` в демо-схемах (файлы демо ничьи — см. п. 15) или исключение для демо.
13. `smoke_html.mjs` (FB-039): причина, по которой Firefox не запускается, — в `build/env.json → browsers.firefox {ok, why}` (пишет `check_env.py --probe-browsers`); smoke может ставить skip с этой причиной.
14. На момент проверки `build_html.py` не компилировался (`SyntaxError` около строки 3717) — тесты, собирающие страницу, временно падали; после исправления повторить `tests/test_process_build_all.py`.

## Оркестратор (файлы без владельца)
15. `scripts/make_demo.py`, `scripts/make_concept_demo.py`: `<title>` у узлов демо-схем (см. п. 12).
16. `references/report-template.md`: в таблицу «Разделы и откуда брать данные» добавить строки 15–19 (вопросы запроса — `idea.request_questions` и маркеры `[RQnn]`; материалы владельца — `sources.owner_docs`, `build/owner-materials.md`; пересмотр идеи — `data/premises.json`; ручные вмешательства — `build/interventions.jsonl`, `build/retro.md`; ворота полноты — `build/build-all-last.json → completeness`) и строку «каркас — `report.py <OUT>`».
17. `scripts/app_scan.py:620` — `Path(repo.path).expanduser()` (для `--portable-config`, см. п. 2).

## WP-F (`templates/briefs/mockups.md` и др.) — по желанию
18. В брифах набора «Временные файлы — только в `build/tmp/<ключ агента>/`»: `render_brief.py` уточняет конкретную папку `build/tmp/<имя брифа>/` блоком «Общие правила прогона», `check_paths.py` разрешает и её, и папку, явно названную в брифе. Если хотите единообразия — `build/tmp/<имя брифа>/`.
