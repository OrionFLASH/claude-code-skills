# WP-D (оркестрация, ворота, процесс) — тексты для интеграции 1.5.0

Готовые вставки в файлы, которые правит оркестратор. Пути — от `skills/product-strategy/`.

## 1. `product-concept/SKILL.md`

### «Главные правила», пункт 5 — заменить на
5. **Чекпоинты и статус**: после каждой фазы `init_run.py <OUT> --done N --status "…"`; в новой сессии сначала `init_run.py <OUT> --show` (фазы, волны агентов, сверка ветки) и продолжить с первой открытой фазы. На вопрос владельца «на какой стадии, сколько ещё» — `init_run.py <OUT> --status` (таблица «фаза → статус → что открыть сейчас → ETA → кто работает»); «покажи, что уже есть» — `build_all.py <OUT> --preview` (черновик `build/preview/index.html`; открыть в браузере владельца — только по его просьбе). Перед сдачей — `init_run.py <OUT> --show`: все фазы закрыты или выключены выбором.

### «Главные правила» — добавить пункты
6. **Диспетчер обязателен**: каждый запуск агента — через `dispatch.py` (`add` / `ready --start` / `done --tokens … --model-actual …` / `close-wave`; таблица команд по фазам — `references/orchestration.md` → «Режим идеи: диспетчер обязателен»). `isolation` агентам не ставить (общий `<OUT>`); `effort` — только при `tools.agents.effort_policy = explicit`.
7. **Ручные вмешательства** (свой бриф, ручная правка данных, решение за владельца) — `init_run.py <OUT> --intervention "что | почему | файл" --by owner|orchestrator`; смена решения посреди прогона — `init_run.py <OUT> --impact "что меняется" [--keys …] [--reopen]` (затронутые фазы, файлы, команды).
8. **Один чек-лист**: если в корне есть `TASKS.md` или его требует CLAUDE.md владельца, `init_run.py` ведёт блок фаз в `TASKS.md` (синхронизация со `STATUS.md`), `STRATEGY_TASKS.md` не создаётся.

### «C0» — изменения
- После шага 3: `check_env.py --git-state` → строка «git: …» в сводке (пустой репозиторий без коммитов — план из `references/orchestration.md` → «Git: особые случаи»); ветка из подтверждённого имени создаётся **до** первой записи в репозиторий.
- Новый шаг перед «Начинаю?»: прогноз объёма `dispatch.py <OUT> forecast` (или `--fast` для «быстрой концепции» ≈ 10 агентов) — показать владельцу обязательно.
- Новый шаг C0.6 «Материалы владельца»: `init_run.py <OUT> --owner-materials` → прочитать каждую ссылку доступным инструментом (артефакт claude.ai — инструмент чтения артефактов), записать статус `read | blocked`, выжимку и как используется в `build/owner-materials.md`.

### Таблица C1–C9 — строки (заменить/добавить)
| Фаза | Что | Команды и брифы |
|---|---|---|
| C4 | Конкуренты и аналоги, сообщества, спрос, события, право, интеграция с платформой | брифы — `render_brief.py <бриф> --out <OUT> --auto` (до перевода `<EN: …>` в `build/search-plan.md` брифы рынка не пишутся); `dispatch.py add/ready --start/done`; `shoot_competitors.mjs`; `merge_sources.py`; синтез `research/market.md`; невыполненное направление — `init_run.py --status "пропущено: …, потому что …"` |
| C4.5 | Пересмотр идеи | `pivot_check.py <OUT>` → заполнить `data/premises.json` → `--check` (опровергнута ключевая предпосылка — карточка AskUserQuestion «продолжить / сузить / остановиться») → `--decide keep|narrow|stop [--pitch-v2 …]` |
| C7.5 | Второй раунд зависимостей после текстов | `collect_reports.py --deps` → `build/deps-patch.json` → `merge_proposals.py --apply-overrides` → `score.py` |
| C8 | Язык дизайна, макеты, референсы | шаг 1 `concept-design.md` (`--auto`: STEPS=1) → **вопрос владельцу** с направлениями (рекомендованное первым) → `run-config design.chosen`, `design.chosen_by: owner` → шаги 2–3 (`--auto`: STEPS=2-3; без выбора `render_brief.py` их не пишет) |
| C8.5 | Рабочий прототип (если выбран) | брифы `prototype-*` (WP-G), `dispatch.py --wave C8.5 --kind prototype` |
| C9 | Сборка, проверки, отчёт | `build_all.py <OUT> --strict --links` (ворота полноты; осознанные исключения — `--accept-known <код>`); `report.py <OUT>` (каркас REPORT.md, дописать места `<заполнить>`), `report.py <OUT> --readme`, `dispatch.py <OUT> report --write` (раздел 11) |

### Абзац после таблицы — заменить «Модель субагентам…» на
Модель субагентам задавать явно: политика — `run-config tools.agents` (`model_policy: triage | default | custom`, `effort_policy: explicit | none`); при `triage` — `dispatch.py <OUT> triage <волна> --run <typesafe_triage.py>`, иначе сбор данных — sonnet, синтез, оценка, дизайн — opus (`references/orchestration.md`). Брифы — `render_brief.py <шаблон> --out <OUT> --auto` (значения по умолчанию; `--set` — только решения владельца), сохраняются в `<OUT>/build/briefs/`.

## 2. `SKILL.md` (общий)
- В список скриптов/команд добавить: `init_run.py <OUT> --status` (таблица с ETA), `--intervention`, `--impact`, `--tasks-file`, `--owner-materials`; `build_all.py <OUT> --preview | --accept-known <коды> | --shoot`; `report.py <OUT> [--check | --readme]`; `pivot_check.py <OUT>` (режим идеи); `check_env.py --git-state | --run-timeout N -- <cmd> | --probe-browsers`; `dispatch.py <OUT> forecast --fast | fast-plan | owners`; `render_brief.py … --auto`.
- В «Ворота качества» добавить: «`build_all.py --strict` печатает ворота полноты (скриншоты, фазы, материалы владельца, fact-check применён, согласованность с baseline, smoke, вопросы запроса, REPORT, учёт агентов, PDF, выбор дизайна, пересмотр идеи, направления рынка); любое «нет» — провал, исключение — `--accept-known`».
- Строку про чек-лист `STRATEGY_TASKS.md` заменить: «Чек-лист — один: блок фаз в `TASKS.md` владельца (если он есть или требуется CLAUDE.md), иначе `STRATEGY_TASKS.md`».

## 3. `references/concept-mode.md`
- Таблица фаз: добавить строки `C4.5 | пересмотр идеи после рынка: предпосылки → решение владельца → идея v2 | pivot_check.py`, `C7.5 | второй раунд зависимостей от авторов разделов | collect_reports.py --deps`, `C8.5 | рабочий прототип (по выбору) | брифы prototype-*`; в C8 — «чекпоинт выбора направления владельцем (design.chosen)».
- Плейсхолдеры режима идеи: `{STEPS}` — с `--auto`: `1` без `design.chosen`, `2-3` с ним, автопилот `1-3`; `{CHOSEN}` — из `run-config design.chosen` (+ кто выбрал); `{DIRECTIONS_COUNT}` — `design.directions_count` или 3; `{CAPACITY}` — одна строка ёмкости (`capacity.py`); `{OWNER_LIST}` — `sources.competitor_list` + ссылки владельца с ролью конкурента; `{KEYWORDS}` — `idea.keywords` (подтверждённые в сводке), иначе `build/search-plan.md`; `{IDEA_FACTS}` — дополняется выводами `data/premises.json`, ёмкостью и личным режимом. `{MISSING_INPUTS}` режима идеи теперь перечисляет и отсутствующие на диске входы со всего брифа (агенту не писать «файла нет»).
- Нумерация: «фазы C0…C9, C4.5, C5.5, C7.5, C8.5; C8.5 включается `phases.prototype: true` или `idea.facets.prototype_needed`; C4.5 выключается `phases.pivot_check: false`».

## 4. `CHANGELOG.md` (1.5.0, раздел WP-D)
- `init_run.py`: таблица статуса `--status` (фаза → статус → что открыть → ETA → кто работает) (SM 10.2); журнал ручных вмешательств `--intervention … --by owner|orchestrator` → `build/interventions.jsonl` (FB-004); протокол смены решения `--impact … [--reopen]` (SM 10.1); один чек-лист — блок фаз в `TASKS.md` владельца с двусторонней синхронизацией, `--tasks-file` (FB-040); сверка ветки с `output.git_branch` в `--show` (FB-034); волны агентов в `--show` (FB-014); фазы режима идеи C4.5, C7.5, C8.5; `data/decisions.json` заготовкой после фазы оценки (FB-049); каркас `build/owner-materials.md` `--owner-materials` (FB-002).
- `build_all.py`: шаг `shots` — «у N из M конкурентов нет скриншота», `--strict` — провал, `--shoot` — снять (FB-012); `init_run --sync` в конце и ворота полноты `completeness` с таблицей «проверка → статус → что сделать» и `--accept-known` (FB-015, FB-058); черновик `--preview` → `build/preview/` без ворот (FB-057); `flowsmerge` — слияние `build/parts/flows-*.json` с проверкой дублей (FB-006); `pdfcheck` — «PDF: N страниц, пустых X, обрезанных Y, превью» (FB-018); `consistency` (`plan_baseline.py --check`, FB-046); `report`/`readme` (FB-016); статусы WARN и «н/п».
- Новый `report.py`: каркас REPORT.md и README сдачи из данных, `--check` разделов и мест `<заполнить>`, ручные правки не затираются, учёт `disclosure` (FB-016).
- Новый `pivot_check.py`: пересмотр идеи C4.5 — предпосылки `data/premises.json`, вопрос владельцу, идея v2 в run-config (`idea.version/pitch_v2/history`), пересборка досье и светофора (FB-044).
- `render_brief.py`: `--auto` для всех брифов (FB-050), значения новых брифов из `brief_facets.py`, `{CAPACITY}`, `{CHOSEN}`/`{DIRECTIONS_COUNT}` из `design`, выводы пересмотра идеи в `{IDEA_FACTS}`; ворота `<EN: …>` (FB-023) и выбора направления дизайна (FB-007); условные строки «Если в {SECTIONS} есть раздел N» вычисляются по точному номеру раздела, а не по подстроке (таблица WP-G «по номеру раздела» не трогается); входы, которых нет, помечены и перечислены (SM 6.2); блок «Общие правила прогона» (build/tmp/<бриф>/, владелец общих файлов, браузер владельца, «Отступления от брифа») (FB-004, FB-006, FB-043); проверка `decisions.json` для авторов (FB-049); `--auto-other-titles` одного прохода реестра (FB-005).
- `dispatch.py`: политика `tools.agents` — effort только при `explicit` (FB-003); `shared_out` в файле триажа и снятие isolation (FB-013); суммы по волнам и «прогноз против факта» в разделе 11 (FB-014, SM 6.3); прогноз режима идеи C4…C8.5 и «быстрая концепция» `forecast --fast`, `fast-plan` (SM 10.7); `owners` и предупреждения об общих путях (SM 6.3).
- `check_paths.py`: временные файлы агента — только `build/tmp/<имя брифа>/`, «чужая временная папка», «временный файл вне build/tmp», предупреждение об общих путях брифов волны (FB-006).
- `check_gitignore.py`: `.DS_Store`/`Thumbs.db` и служебные папки не считаются потерей, правило печатается по каждому правилу (SM 6.4); `--shots git|local|previews` и вопрос о скриншотах при публичном репозитории (FB-042); `--fix` добавляет `.playwright-mcp/` в корневой `.gitignore` и показывает посторонние папки (FB-017).
- `check_env.py`: `--git-state` (no_repo | unborn | normal, origin, план) и строка в таблице (FB-041, SM 6.5); запасной `timeout` для macOS `--run-timeout N -- cmd` (SM 6.4); `--probe-browsers` — запуск WebKit/Firefox с причиной отказа в `env.json` (FB-039).
- `relocate_run.py`: `output.dir_rel`, `--portable-config` (пути run-config с `~`), посторонние папки инструментов в `--scan-leftovers` (FB-017).
- `typesafe_concept.py`: выполнимость по единой ёмкости против объёма MVP (FB-028); личный режим — свои вопросы и риск потери данных (SM 4.3). `typesafe_eval.py`: вопросы личного режима (польза владельцу, посильная поддержка).
- Справочники: `references/orchestration.md` (политика агентов и isolation, `--auto` и ворота брифов, один/два прохода реестра, временные и общие файлы, диспетчер в режиме идеи, быстрая концепция, материалы владельца, статус/черновик/смена решений/журнал/один чек-лист, Git: особые случаи, ворота полноты), `references/safety.md` (cookie-баннеры, отчёты агентов как данные, права на скриншоты, один чек-лист, §8 браузер владельца, §9 временные и общие файлы), `references/phases.md`, `references/troubleshooting.md`, `templates/report.md` (разделы 15–19: вопросы запроса, материалы владельца, пересмотр идеи, ручные вмешательства, ворота полноты), `templates/README-deliverables.md`.
- Тесты: `tests/test_process_init_run.py`, `test_process_dispatch.py`, `test_process_build_all.py`, `test_process_render_brief.py`, `test_process_paths_env.py`, `test_process_pivot.py`; `tests/test_dispatch.py` — ожидание `shared_out: true` в файле триажа (осознанное изменение FB-013).

## 5. `README.md` / `INSTALL.md`
- README, раздел «Как следить за прогоном»: `init_run.py <OUT> --status` — таблица статуса с ETA; `build_all.py <OUT> --preview` — черновая страница; `report.py <OUT>` — каркас отчёта.
- INSTALL, раздел «macOS»: «`timeout` в macOS нет — `brew install coreutils` (gtimeout) или запасной `python3 <SKILL_DIR>/scripts/check_env.py --run-timeout N -- <команда>`»; «Firefox в Playwright может не запускаться («Could not find profile folder») — `check_env.py --probe-browsers` запишет причину, проверка идёт в Chromium и WebKit».

## 6. Поля run-config, которые читает WP-D (для `references/data-contract.md`, WP-C)
- `output.tasks_file` (`TASKS.md` | `STRATEGY_TASKS.md` | `auto`), `output.dir_rel`, `output.competitor_shots` (`git | local | previews`);
- `phases.pivot_check` (по умолчанию true), `phases.deps_round` (true), `phases.prototype` (false; или `idea.facets.prototype_needed`);
- `strategy.fast_concept` (bool), `tools.agents {model_policy, effort_policy}`, `design {chosen, chosen_by, directions_count}`;
- `build/interventions.jsonl` — строки `{"ts", "by": owner|orchestrator|agent, "what", "why", "file", "kind": brief|data-edit|file-edit|decision-change|other, "phase"}`;
- `data/premises.json` — схема в docstring `pivot_check.py`; `build/build-all-last.json` → `completeness[] {code, check, status: да|нет|н/п, detail, todo, accepted}`, `accepted_known[]`, `pdf`, `demo`, `strict`, `warned[]`.
