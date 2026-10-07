# Журнал изменений site-qa-audit

Формат — [Keep a Changelog](https://keepachangelog.com/ru/1.1.0/), версии — SemVer, теги `site-qa-audit/vX.Y.Z`.

## [1.0.0] — 2026-10-07
### Добавлено
- SKILL.md: порядок прогона из 10 шагов (окружение → опрос → репозитории → разведка → прогон → дедупликация → сверка → вопросы → публикация → отчёт).
- references: setup, intake, safety-rules (базовые и пользовательские запреты, блок правил для исполнителей, маскирование), depth-matrix, parallelism (MCP-поток + изолированные playwright-cli потоки), plugins-map (усилители и запреты), repo-sync (роли, права, статусы, публикация), severity, environment-notes, checklists для 10 направлений со стабильными check_id.
- templates: run-config.example.yaml, finding.schema.json, issue-detailed, issue-comment, user-story, run-report.
- scripts: check_env (sh/ps1, реальный запуск браузеров), url_guard (selftest), fetch_issues (инкрементальный кэш), read_templates (.md и YAML issue forms, render), fingerprint (compute/dedupe/match), render_draft, node-проверки a11y/lighthouse/headers/links/probe.
- tests: сценарий dry-run на demo.playwright.dev/todomvc.
