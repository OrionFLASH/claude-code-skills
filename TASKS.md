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
- [ ] Claude in Chrome: пользователь ставит расширение + /chrome, перезапуск, проверка
- [ ] После перезапуска: убедиться, что qa-skills загружен (skills/агенты видны)

## Этап 2–6. Скил site-qa-audit
- [x] Каркас через tools/new-skill
- [x] scripts: url_guard, fingerprint, fetch_issues, read_templates, check_env(+sh/ps1), node/{a11y,lighthouse,headers,links,probe}
- [x] shared: miniyaml, envcheck (вендоринг через .shared)
- [x] templates/run-config.example.yaml
- [ ] SKILL.md, README
- [ ] references: setup, intake, safety-rules, depth-matrix, parallelism, plugins-map, repo-sync, severity, checklists/* (10)
- [ ] templates: finding.schema.json, issue-detailed, issue-comment, user-story, run-report
- [ ] CONVENTIONS: описать .shared-вендоринг
## Этап 7–8. Порядок прогона, публикация, тег v1.0.0
## Этап 9. Dry-run на демо-сайте, исправления, 1.0.1

## Где остановился
Этап 1 закончен, кроме Claude in Chrome (нужны действия пользователя и перезапуск). Скрипты скила написаны и проверены
на demo.playwright.dev. Следующий шаг после «продолжай»: check_env, затем references/templates/SKILL.md (этапы 2–7).
