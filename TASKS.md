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
