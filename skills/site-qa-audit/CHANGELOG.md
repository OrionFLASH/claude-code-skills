# Журнал изменений site-qa-audit

Формат — [Keep a Changelog](https://keepachangelog.com/ru/1.1.0/), версии — SemVer, теги `site-qa-audit/vX.Y.Z`.

## [1.0.1] — 2026-10-07
По итогам dry-run на demo.playwright.dev/todomvc (этап 9).
### Исправлено
- url_guard: кнопки-иконки (×, ✕, 🗑) и доступное имя (`--name`, aria-label) теперь проверяются — раньше «×» проходил как allow; категория `destructive-icon` → confirm.
- render_draft: пустая строка перед заголовками; локальные ссылки на скриншоты из `drafts/copies/` (`../../screenshots/…`).
### Добавлено
- `preapproved_actions` в run-config: заранее одобренные пользователем confirm-действия (например, удаление записей, созданных прогоном); запреты deny не снимаются. Вопрос об этом в опросе.
- `scripts/validate_findings.py`: проверка findings.json по схеме (stdlib), дубли id/fingerprint, плейсхолдеры, немаскированные e-mail/токены.
- SKILL.md: шаг «чистое состояние» (постоянный профиль Playwright MCP переносит данные между прогонами), абсолютные пути для файлов MCP, подтверждение в браузере SEO-сигналов статического обхода SPA.
- environment-notes: состояние и пути Playwright MCP.
- tests: эталонный run-config dry-run, 3 новых unit-проверки (всего 11).

## [1.0.0] — 2026-10-07
### Добавлено
- SKILL.md: порядок прогона из 10 шагов (окружение → опрос → репозитории → разведка → прогон → дедупликация → сверка → вопросы → публикация → отчёт).
- references: setup, intake, safety-rules (базовые и пользовательские запреты, блок правил для исполнителей, маскирование), depth-matrix, parallelism (MCP-поток + изолированные playwright-cli потоки), plugins-map (усилители и запреты), repo-sync (роли, права, статусы, публикация), severity, environment-notes, checklists для 10 направлений со стабильными check_id.
- templates: run-config.example.yaml, finding.schema.json, issue-detailed, issue-comment, user-story, run-report.
- scripts: check_env (sh/ps1, реальный запуск браузеров), url_guard (selftest), fetch_issues (инкрементальный кэш), read_templates (.md и YAML issue forms, render), fingerprint (compute/dedupe/match), render_draft, node-проверки a11y/lighthouse/headers/links/probe.
- tests: сценарий dry-run на demo.playwright.dev/todomvc.
