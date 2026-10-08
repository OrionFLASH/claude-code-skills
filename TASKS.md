# TASKS — claude-code-skills + site-qa-audit

## Этап 0. Репозиторий скилов
- [x] Проверить/создать OrionFLASH/claude-code-skills (приватный)
- [x] Клонировать в ~/dev/MyProject
- [x] Каркас: README, CONVENTIONS, CHANGELOG, marketplace.json, shared/, tools/
- [x] tools: install, new-skill, validate (sh + ps1, логика на Python stdlib)
- [x] Первый коммит и push каркаса (через ветку feature/repo-skeleton → main)

## Этап 1. Окружение
- [x] Проверка базовых компонентов, таблица
- [x] Список глобальных установок → подтверждение пользователя
- [x] Установка плагинов/скилов тестирования (после подтверждения)
- [x] Флаги Playwright MCP, опыт параллельности, environment-notes.md
- [x] Claude in Chrome: расширение 1.0.98 + native host, проверено управление (1.0.2 — исправлено обнаружение в check_env)
- [x] После перезапуска: qa-skills загружен (skills/агенты видны)

## Этап 2–6. Скил site-qa-audit
- [x] Каркас через tools/new-skill
- [x] scripts: url_guard, fingerprint, fetch_issues, read_templates, check_env(+sh/ps1), node/{a11y,lighthouse,headers,links,probe}
- [x] shared: miniyaml, envcheck (вендоринг через .shared)
- [x] templates/run-config.example.yaml
- [x] SKILL.md, README
- [x] references: setup, intake, safety-rules, depth-matrix, parallelism, plugins-map, repo-sync, severity, checklists/* (10)
- [x] templates: finding.schema.json, issue-detailed, issue-comment, user-story, run-report
- [x] CONVENTIONS: описать .shared-вендоринг
## Этап 7–8. Порядок прогона, публикация, тег v1.0.0
- [x] Порядок прогона в SKILL.md; validate; README/marketplace; версия 1.0.0; тег site-qa-audit/v1.0.0
- [x] Установка симлинком, Claude Code видит скил
## Этап 9. Dry-run на демо-сайте, исправления, 1.0.1
- [x] tests/unit.sh (8/8)
- [x] Dry-run todomvc по tests/dry-run-todomvc.md
- [x] Показать: дерево, run-config, пример находки, черновик issue, срабатывание запрета, плагины
- [x] Исправления → 1.0.1, CHANGELOG, тег, merge в main, push

## Боевой прогон 2026-10-07 (главная страница реального сайта)
- [x] Прогон standard, 5 направлений, 20 находок, отчёт и черновики (dry-run, вне репозитория скилов)
- [x] 1.0.3: guard — OAuth-провайдеры и «Поддержать»; замок навигации nav_lock.js; notes про playwright-cli/WebKit

## 1.0.4 — папка результатов и аннотированные скриншоты
- [x] output_dir: run-config, intake (вопрос), SITE_QA_OUTPUT_DIR, check_env, SKILL.md
- [x] SITE_QA_OUTPUT_DIR в ~/.claude/settings.json (env) — задана
- [x] scripts/node/annotate.js: пунктирная обводка, тонкая стрелка, подпись без перекрытия, автоцвет (жёлтый/зелёный/фиолетовый)
- [x] scripts/snap_mcp.js (MCP) и node/shot.js (CDP): скриншот + координаты элементов
- [x] references/screenshots.md, SKILL.md, render_draft (поле annotations в схеме не делалось: скриншоты `-annotated.png` в `screenshots`)
- [x] tests: annotate через shot.js на фикстурах (test_stream_b.sh)
- [ ] Проверить на скриншотах реального прогона, пересобрать черновики (вне репозитория, вручную)
- [x] validate, CHANGELOG — 1.0.4 влит в запись 1.1.0 (отдельного тега 1.0.4 нет)

## 1.1.0 — доработки по итогам боевого прогона (спека: scratchpad/spec.md, пункты 1–17)
Ветка feature/output-dir-annotations (1.0.4 вливается в 1.1.0). Параллельно три потока по владению файлами.
- [x] Поток A (Python/схема): 1 claims.py, 9 схема+content-i18n+render_draft, 11 closed_claims, 12 intake from-text, 13 journal, 14 read_templates fetch, 15 check_env, 16 report.md, 17 zsh
- [x] Поток B (Node/браузер): 2 side_effects/invariants, 3 guard.js, 4 occlusion.js, 5 reachability.js, 6 device_context.js, 7 frames, 8 shot.js, фикстуры (а–д)
- [x] Поток C: 10 publish_web.mjs / comment_web.mjs (только на локальных фикстурах)
- [x] Интеграция: SKILL.md, README, run-config.example.yaml, CHANGELOG 1.1.0, tests/unit.sh, validate
- [x] Завершить 1.0.4 (output_dir, annotate, screenshots.md), проверить
- [ ] Коммит, тег site-qa-audit/v1.1.0, merge в main, push; симлинк ~/.claude/skills/site-qa-audit уже на репозиторий

## Где остановился
2026-10-08, интеграция 1.1.0 завершена (ветка feature/output-dir-annotations, без коммита).
- Сделано: фрагменты потоков A/B/C внесены в SKILL.md (106 строк), README скила, run-config.example.yaml, repo-sync.md, intake.md, parallelism.md, tests/unit.sh, tests/README.md; CHANGELOG скила [1.1.0] (включая 1.0.4), plugin.json 1.1.0, корневые README/marketplace.json (skillsrepo.py sync), корневой CHANGELOG. Фикстуры обезличены (названия игр, соседний домен). .integration/ и __pycache__ удалены.
- Проверки: tools/validate.sh — 0 ошибок; tests/unit.sh — 34 PASS (A 32, B 29, C 34); url_guard selftest 29/29; validate_findings на findings.json и findings-v11.json — 0 ошибок.
- Осталось: коммит, тег site-qa-audit/v1.1.0, merge в main, push (делает пользователь); проверка на скриншотах реального прогона.
- Следующий шаг: git add skills/site-qa-audit README.md CHANGELOG.md .claude-plugin/marketplace.json TASKS.md → commit → tag → merge.

## 2026-10-08 универсальность и установка (1.2.0)
Ветка feature/site-qa-universal-install (от fix/default-output-cwd). Чужая правка `scripts/node/device_context.js` не трогается.
База до правок: validate — 1 ошибка (marketplace 1.1.0 ≠ plugin.json 1.1.2), unit.sh — 34 PASS.
- [x] A1 grep на личные/конкретные упоминания (SKILL, references, templates, README, scripts)
- [x] A2 description: автозапуск по смыслу (RU/EN), когда НЕ использовать, ≤ 1024 символов
- [x] A3 подтверждение намерения при автозапуске (SKILL.md, intake.md)
- [x] A4 расширенный опрос в intake.md (что тестируем, запреты, куда не ходить, вход, устройства, глубина, успех)
- [x] A5 параллельность до 4 (parallelism.md, SKILL.md, intake.md, run-config, intake.py + тест)
- [x] B1 куда писать итоги (`report_destinations`): intake, run-config, SKILL.md шаг «Отчёт»
- [x] B2 qa-runs/ и .gitignore: вопрос в конце прогона, `scripts/gitignore_helper.py` + тест
- [x] C1 источники о сайте: вопросы в intake, `context.*` в run-config
- [x] C2 память о сайте: `.site-context/<host>/context.md`, шаблон, SKILL.md (разведка), run-files.md
- [x] D1 site-qa-audit/INSTALL.md (macOS/Windows, промпты установки и обновления)
- [x] D2 typesafe-triage: INSTALL.md + UPDATE.md → один INSTALL.md, UPDATE.md удалить, ссылки
- [x] D3 ссылки на INSTALL.md в README (корневой и скилов)
- [x] Найдено по дороге: `<OUTPUT_ROOT>` по умолчанию = `<cwd>` (результаты в `<cwd>/qa-runs/`), устаревшие тексты «скил спросит» в README/setup/check_env — исправить
- [x] E версии: site-qa-audit 1.2.0, typesafe-triage patch, CHANGELOG, sync README/marketplace
- [x] E validate 0 ошибок, unit.sh зелёный, коммит(ы) в ветке
- [ ] Не делалось (решение пользователя): merge в main, push, теги `site-qa-audit/v1.2.0` и `typesafe-triage/v2.1.3`

### Где остановился
2026-10-08, всё по пунктам A–E сделано в ветке feature/site-qa-universal-install (два коммита: typesafe-triage 2.1.3, site-qa-audit 1.2.0 + корневые файлы).
- Сделано: description и подтверждение намерения; расширенный опрос (`goal`, куда не переходить, запреты по семантике url_guard, источники о сайте, `report_destinations`); память о сайте `.site-context/<host>/` + шаблон; `gitignore_helper.py` (check/apply gitignore|exclude|keep); `build_report.py summary`; до 4 потоков (`intake.py`, run-config, parallelism.md); INSTALL.md site-qa-audit; единый INSTALL.md typesafe-triage (UPDATE.md удалён); версии 1.2.0 и 2.1.3, CHANGELOG, sync README/marketplace.
- Проверки: `tools/validate.sh` — 0 ошибок, 0 предупреждений; `tests/unit.sh` — PASS 36, FAIL 0 (A 32, v1.2 24, B 29, C 34); pytest typesafe-triage — 200 passed.
- Осталось: merge fix/default-output-cwd и этой ветки в main, push, теги (делает вызывающий); живой прогон автозапуска и подтверждения намерения в новой сессии Claude Code (здесь не проверялся); промпты INSTALL.md на чистой машине не прогонялись.
- Следующий шаг: влить ветку, затем в новой сессии сказать «проверь вёрстку https://example.com» и убедиться, что скил спрашивает подтверждение.

## 2026-10-08 android-qa-audit 1.0.0
Ветка feature/android-qa-audit (от main). Чужая правка `skills/site-qa-audit/scripts/node/device_context.js` не трогается и не коммитится. В main не вливать (делает вызывающий).
- [x] Изучить CONVENTIONS, tools, site-qa-audit (SKILL, references, scripts, templates, tests)
- [x] Ветка, каркас через tools/new-skill.sh (README-таблица и marketplace.json)
- [x] shared: runjournal.py (= journal.py site-qa-audit), qa_gitignore.py (несколько шаблонов) в shared/scripts, .shared, sync
- [x] scripts: sdkutil, check_env(.py/.sh/.ps1), apk_info, avd_manager, adb_helpers, guard, masking, intake, matrix, journal, build_report, validate_findings, render_draft, fingerprint, gitignore_helper
- [x] templates: run-config.example.yaml, finding.schema.json, issue-detailed.md, run-report.md, app-context.md
- [x] references: intake, safety-rules, stands, device-control, depth-matrix, parallelism, plugins-map, run-files, repo-sync, severity, setup, checklists/ (11; чек-листы писал субагент, проверены по командам скриптов)
- [x] SKILL.md (103 строки, description 972 символа), README.md, INSTALL.md, CHANGELOG 1.0.0, plugin.json 1.0.0, .status «в разработке»
- [x] tests: unit.sh, helpers/fake_adb.py + fake_tools.py, фикстуры — 110 PASS на Python 3.14 и 3.9 (/usr/bin/python3)
- [x] Корневые README/CHANGELOG/marketplace (skillsrepo.py sync), validate 0 ошибок
- [x] Read-only проверки на машине: adb version, aapt2 badging, check_env, apk_info, avd_manager list (+ matrix по реальному env)
- [x] Найдено по дороге: f-строка с вложенными кавычками (только 3.12+) в avd_manager — исправлено, unit.sh компилирует ещё и интерпретатором < 3.12; формат `emulator -accel-check` на macOS (код статуса, без «usable») — разбор исправлен, тест добавлен; `text --env` писал секрет в actions.jsonl — исправлено, тест
- [x] Коммит в ветке, «Где остановился»
- [ ] Не делалось (решение вызывающего/пользователя): merge в main, push, тег `android-qa-audit/v1.0.0`; живой прогон на эмуляторе и устройстве; перевод site-qa-audit на shared runjournal/qa_gitignore

### Где остановился
2026-10-08, скил android-qa-audit 1.0.0 реализован в ветке feature/android-qa-audit (один коммит; в main не вливался).
- Сделано: SKILL.md, README, INSTALL (macOS/Windows/Linux, Android SDK, промпты), CHANGELOG, 11 справочников + 11 чек-листов, 5 шаблонов, 15 скриптов (+ sdkutil, masking) и 2 общих модуля в shared/scripts (runjournal, qa_gitignore), тесты на фейковом adb/SDK.
- Проверки: `tools/validate.sh` — 0 ошибок, 0 предупреждений; `skills/android-qa-audit/tests/unit.sh` — PASS 110, FAIL 0 (Python 3.14 и 3.9); `skills/site-qa-audit/tests/unit.sh` — PASS 36 (не сломан); read-only на машине: check_env «можно работать», apk_info по APK из Downloads совпадает с aapt2/apksigner, avd_manager list — 3 чужих AVD помечены «не менять».
- Осталось: merge/push/тег; живой прогон (создать qa-AVD на установленном образе API 37, start --headless, install, dump-ui, tap, crashes, cleanup) — делает вызывающий вручную; после живого прогона — статус «стабильный».
- Следующий шаг: живой прогон по tests/README.md → «Живая проверка», исправления → 1.0.1.

## 2026-10-08 android-qa-audit 1.0.1 и gitignore по умолчанию
Ветка fix/android-qa-defects (от main). Чужая правка `skills/site-qa-audit/scripts/node/device_context.js` не трогается и не коммитится. В main не вливать (делает вызывающий). Эмуляторы не запускать, APK не ставить; реальный прогон (qa-runs/2026-10-08-com.versus.host) — только читать.
База до правок: validate — 0 ошибок; android unit.sh — PASS 110; site unit.sh — PASS 36.
- [x] A1 crashes: падения чужих процессов (UiAutomation и т. п.) → `other_processes`, не crash приложения; ANR только `ANR in <package>`; build_report
- [x] A2 dump-ui после rotate: размер экрана из текущего состояния (rotation дампа, `dumpsys window displays`), rotate возвращает фактический размер
- [x] A3 matrix: `hardware: []` + custom → только custom; оба пустые → по глубине
- [x] A4 install-image `--run-dir` (stands.json, журнал); тест команд из SKILL.md/references (`--help`-парсинг)
- [x] A5 SKILL.md/INSTALL.md: скил виден только в новой сессии, как продолжить в текущей
- [x] A6 text: не-ASCII — отказ с подсказкой, `--translit`, `--adbkeyboard` (только свой эмулятор, ime)
- [x] A7 intake from-text: запреты камера/QR/точка доступа/микрофон/геолокация/уведомления… → типовые тексты RU+EN, пакеты камеры, «проверить на разведке»
- [x] A8 шум «integer expression expected» (Java -ea): подавлять при коде 0, отметка в check_env; INSTALL — JDK 17/21
- [x] A9 logcat start/dump: по умолчанию фильтр по пакету (pid, перезапуски), `--all`; crashes — по полному журналу
- [x] A10 intake.md/SKILL.md: конфликт «запрет против сценария» — вопрос на разведке, решение в run-config и журнал
- [x] B1 shared qa_gitignore: `ensure` (до создания RUN_DIR), `untrack`, разрешение коммитить из текста (RU/EN), `allow_commit_apk`
- [x] B2 shared qa_export + `export_results.py` в обоих скилах: в `folder` — только итоговые файлы
- [x] B3 site-qa-audit: gitignore_helper → обёртка над shared, intake `git.allow_commit_results`, документация без вопроса про .gitignore
- [x] B4 android-qa-audit: документация, run-config `git.*`, intake
- [x] Тесты обоих скилов; версии 1.0.1 / 1.2.1, CHANGELOG, sync; validate; Python 3.9
- [x] Коммит в ветке, «Где остановился»
- [x] Найдено по дороге: `masking.py` превращал `password="false"` в дампе UI в `password="***"` — исправлено, тест; `guard.py` считал `ime set` чтением — теперь изменение устройства; `intake.py` для «8 ГБ ОЗУ» добавлял лишний телефон 4 ГБ — теперь `hardware: []` + свой профиль; dropbox в `crashes` совпадал с `pkg.debug` — точное имя процесса
- [ ] Не делалось (решение вызывающего/пользователя): merge в main, push, теги `android-qa-audit/v1.0.1` и `site-qa-audit/v1.2.1`; живая проверка на эмуляторе (rotate + dump-ui, logcat start с фильтром, crashes после dump-ui, text --translit, install-image --run-dir, ensure в реальном репозитории)

### Где остановился
2026-10-08, всё по пунктам A1–A10 и B сделано в ветке fix/android-qa-defects (один коммит; в main не вливалось).
- Сделано: crashes по процессу приложения + `other_processes`; размер экрана по повороту дампа и `dumpsys window displays`, `rotate` с фактическим размером; matrix `hardware: []` + custom; `install-image --run-dir`; «Unknown skill» в новой сессии (SKILL.md, INSTALL.md обоих скилов); `text --translit/--adbkeyboard`; темы запретов в intake с типовыми текстами и `exact`/список `context` в guard; шум Java -ea; logcat по приложению (`--all`); «запрет против сценария»; shared `qa_gitignore.py` (`ensure`, `untrack`, `commit_permission`) и `qa_export.py` + `export_results.py` в обоих скилах; site-qa-audit на общем `qa_gitignore.py`; версии 1.0.1 и 1.2.1, CHANGELOG скилов и корневой, sync.
- Проверки: `tools/validate.sh` — 0 ошибок, 0 предупреждений; `android-qa-audit/tests/unit.sh` — PASS 148, FAIL 0 (Python 3.14 и /usr/bin/python3 3.9.6); `site-qa-audit/tests/unit.sh` — PASS 40, FAIL 0 (3.14 и 3.9.6; v1.2.1 — 16, v1.2 — 24, A — 32, B — 29, C — 34); примеры команд в документации — 246 (android) и 127 (site) без ошибок; на данных боевого прогона (только чтение): падение UiAutomation → `other_processes`, 0 падений приложения; альбомный дамп — 0 `visual.offscreen` вместо 9; матрица — одна ячейка 8 ГБ.
- Осталось: merge/push/теги; живая проверка на эмуляторе (вызывающий).
- Следующий шаг: влить ветку, затем живой прогон по tests/README.md → «Живая проверка» с новыми командами.
