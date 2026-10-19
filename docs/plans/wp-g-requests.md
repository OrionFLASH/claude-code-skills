# WP-G — запросы к чужим файлам (1.5.0)

Каждый пункт: файл (владелец) — что сделать — зачем. Ничего из этого WP-G не правил.

## D (оркестрация)
1. `scripts/render_brief.py` — **уже сделано D**: `brief_facets.install(RESOLVERS)` подключён (строки около `import brief_facets`). Проверить, что при `--list` источники новых ключей печатаются из `brief_facets.RESOLVERS` (они там есть). Ничего больше не нужно для рендера новых брифов без `--set`.
2. `scripts/render_brief.py` → `DIRECTIONS` (`{MISSING_INPUTS}`): в личном режиме (`project.audience` ∈ personal, circle) добавить строку «`data/keywords.json`, `research/keywords.md`, `data/events.json`, `research/events.md` — явно пропущено: личный режим (аудитории и продвижения нет)». Зачем: SM 6.2 и раздел «Личный режим» `concept-outline.md` — авторы пишут «явно пропущено, потому что…», а не «файла нет».
3. `scripts/render_brief.py` → `r_words`: в личном режиме подписывать раздел личным заголовком из таблицы «Личный режим» `references/concept-outline.md` (строки `| Раздел N | публичный | личный | … |`, 4 колонки; числа объёма — из основной таблицы, как сейчас). Зачем: в `{WORDS_MAX}` агент видит тот же заголовок, что должен написать.
4. `scripts/check_paths.py` → `brief_patterns`/`to_glob`: если папка прогона — корень репозитория (`{OUT}` = `.`), шаблоны получаются с ведущим `/` (`/research/integration.md`) и не совпадают с относительными путями. Повтор: демо `make_concept_demo.py <папка>` → рендер любого брифа → `check_paths.py <папка> --list-allowed --briefs build/briefs/research-ai.md`. Срезать ведущие `./` и `/`.
5. `scripts/build_all.py` — необязательный шаг `prototype` (если есть `<OUT>/prototype/js/core.test.js`): `node prototype/js/core.test.js [data/demo-canon.json]`, `node prototype/js/kit.test.js`, `python3 prototype/tools/check_canon.py prototype --core`; провал — предупреждение (в `--strict` — ошибка). Зачем: SM 7, правило «числа макетов = числа ядра» как ворота.
6. `scripts/report.py` / `templates/report.md` — строка «Источники от авторов разделов: N (фрагменты `data/sources-s*.json`)» (FB-011) и строка «Рабочий прототип: статус, режимы, тесты» из `data/prototype.json` (SM 7).
7. `scripts/dispatch.py` — виды/волны для новых брифов: C4 `research-integration`, `research-datasources`, `research-ai`, `research-owner-refs`; C7 `concept-ai-observability`, `concept-admin`, `strategy-summary` (последним); C8.5 `prototype-core` → `prototype-shell` → `prototype-mode-*` (параллельно, общих путей нет — проверено `check_paths.py --list-allowed`) → `prototype-regression`.
8. `references/phases.md`, `references/orchestration.md` — вставки из `docs/plans/wp-g-notes.md`, пп. 4–5.

## B (модель, план)
9. `scripts/plan_baseline.py` — читать `data/integration-options.json` (схема — в «Выдаче» `templates/briefs/research-integration.md`: `recommended`, `options[].{id,title,effort_days[min,max],risks[],value,mvp,queue}`, `platform_risks[]`) → `architecture` (рекомендованный вариант) и сроки интеграции в составе MVP. `brief_facets.r_arch` уже понимает `architecture` как строку, список или объект.
10. `scripts/summary_scaffold.py` — писать черновик раздела 1 в `build/summary-draft.md` (не в `build/parts/strategy-*.md`: `assemble_strategy.py` взял бы его как часть и раздел 1 задвоился бы). Бриф `strategy-summary.md` читает его оттуда.
11. `data/demo-canon.json` (B вместе с F) — формат, который понимают `prototype/js/core.test.js` и `prototype/tools/check_canon.py`: `{"label": "демо-данные", "cases": [{"id": "C01", "title": "…", "fn": "<функция ядра>", "inputs": {…}, "expected": {"поле": число|строка|null}, "mockups": ["M01-…"]}]}` (список кейсов без обёртки — тоже). Если формат B другой — нужен либо этот, либо ключи `id/expected` в каждом кейсе.
12. `model.py --profile personal` — на него ссылается раздел 8 личного режима в `concept-outline.md` («минимальный / обычный / с поддержкой», окупаемость личных усилий в неделях).

## C (реестр)
13. `references/data-contract.md`, `scripts/check_registry.py`, `scripts/merge_proposals.py` — зарезервировать группы черновиков: **G9** — ИИ и наблюдаемость (`concept-ai-observability.md`), **G10** — администрирование и эксплуатация (`concept-admin.md`), **G11** — референсы владельца (`research-owner-refs.md`); `--append G9,G10,G11` как у G7. Категории личного режима (`core, data-sources, reliability, privacy-security, ux, ai-quality, maintenance, personal-analytics`) и `evidence.kind: owner_prior_work` (класс не выше C) — их используют брифы.
14. `gap_audit.py --check` — бриф `gap-audit.md` теперь велит писать зависимости от `G7-NN` прямо в `data/gap-audit-deps.json` (`--check` их уже допускает, `--append G7` переводит). Если C меняет это поведение — сообщить, бриф поправит G.
15. `merged_from` у G7–G11: брифы по-прежнему говорят «не заполнять» (`check_registry.check_proposal(draft=True)` не предупреждает). Если C решит иначе — нужна правка брифов.

## E (страница)
16. `references/chart-glossary.ru.json` (названия разделов режима идеи) и `scripts/build_html.py` — в личном режиме (`project.audience` ∈ personal, circle, personal_then_public) подписи разделов по таблице «Личный режим» `concept-outline.md`; блок «Эксплуатация и поддержка» (раздел 9); ссылка «Рабочий прототип» на `prototype/index.html`, если есть `data/prototype.json` со `status` ≠ `failed`.

## F (дизайн, макеты)
17. `templates/briefs/concept-design.md`, `mockups.md`, `templates/mockup-kit/` — помечать числа макетов `data-canon="<кейс>.<поле>"` по канону демо-данных, повторяющиеся элементы графиков — `data-canon-item="<кейс>.<поле>"` (число элементов = значению канона; проверка — `prototype/tools/check_canon.py`, ловит «4 значка, в подписи 3»). Текст бейджа концепта в прототипе — «Концепт продукта, не существующая функция» (как в наборе макетов). Экраны ИИ (`M2x-ai-…`) и админки (`M3x-admin-…`) — из модулей C7 (`research/ai-observability.md`, `research/admin.md`, раздел «Экраны»), 12–25 элементов `data-hs-*` на экран.

## A (опрос)
18. Поля, которые читает `scripts/brief_facets.py` (все необязательны, без них — безопасный текст): `project.audience` (`personal|circle|personal_then_public|public`), `project.release_outward`, `idea.request_questions[] {id, text, kind}`, `idea.facets.{platform_dependency, platform_name, platform_urls[], platform_data_needs[], platform_access (official|community|manual|research|mixed), data_sources_needed[], owner_repos[], ai_role (или прежний ai), ai_where (local|server|cloud|hybrid|local_then_cloud), ai_hardware, admin_who, admin_settings[], admin_needed (bool), prototype_needed (bool), prototype_scope (core|one_screen|all_modes), stack}`, `design.modes[]`, `design.chosen`, `sources.owner_docs[] {url, role, status}`.

## Оркестратор (файлы без владельца)
19. `scripts/handoff.py` — если есть `prototype/HANDOFF.md` и `data/prototype.json`: раздел «Перенос рабочего прототипа» в `CLAUDE_CODE_TASKS.md` (ссылки на ядро `prototype/js/core.js`, тесты канона, список расхождений прототип ↔ боевая версия). Зачем: SM 7, п. 5 «связка с handoff».
20. `tests/README.md` — добавить строки про `test_briefs_concept.py` и `test_prototype_kit.py` (что проверяют — см. docstring файлов).
