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

## Где остановился
Скил site-qa-audit 1.0.3 в main, теги v1.0.0–v1.0.3, установлен симлинком; Claude in Chrome подключён.
Идеи на будущее: lighthouse.js — LCP-элемент из insights Lighthouse 13 (старое поле largest-contentful-paint-element пустое);
эмуляция touch (--device) для deep; a11y.js с подготовкой состояния; публикация в боевом режиме не опробована на реальном репозитории.
Вопрос пользователю — удалять ли влитые ветки.
