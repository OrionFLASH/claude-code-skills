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
- [~] Claude in Chrome: /chrome выполнен (claudeInChromeDefaultEnabled=true), но расширения в профиле Chrome нет, native host нет — ждёт пользователя; не блокирует
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

## Где остановился
Всё по этапам 0–9 сделано: скил site-qa-audit 1.0.1 в main, теги v1.0.0 и v1.0.1, установлен симлинком.
Осталось вне блокировки: Claude in Chrome — расширение не обнаружено в профиле Chrome (нужно действие пользователя);
вопрос пользователю — удалять ли ветки feature/repo-skeleton и feature/site-qa-audit.
Идеи на будущее: эмуляция touch (--device) для deep; a11y.js с подготовкой состояния; публикация в боевом режиме не опробована на реальном репозитории.
