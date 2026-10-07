# Журнал изменений site-qa-audit

Формат — [Keep a Changelog](https://keepachangelog.com/ru/1.1.0/), версии — SemVer, теги `site-qa-audit/vX.Y.Z`.

## [1.0.3] — 2026-10-07
По итогам первого боевого прогона (одна страница реального сайта, standard).
### Исправлено
- url_guard: кнопки провайдеров входа («Google», «Яндекс», «VK», «Steam»…) рядом с «войдите через / sign in with» теперь deny (`base:action:oauth-provider`) — раньше проходили как allow, потому что правило искало только «войти через»; «Поддержать / Support us» — в категории донатов.
### Добавлено
- `scripts/nav_lock.js` — замок навигации для Playwright MCP: обрывает переходы документа вне разрешённых URL и блокирует pushState/replaceState/window.open SPA-роутеров; описан в safety-rules §3.11 и SKILL.md.
- environment-notes: playwright-cli требует свою сборку WebKit; запасной путь — локальный Playwright скила.
- tests: проверки oauth-provider/«Поддержать» в selftest (29), синтаксис nav_lock.js в unit.sh.

## [1.0.2] — 2026-10-07
### Исправлено
- check_env: Claude in Chrome не обнаруживался на macOS — `Path.glob` молча возвращал пусто из-за защиты папки профиля Chrome (TCC); теперь `os.listdir` конкретной папки native host, плюс Linux (chromium) и Windows (реестр).
### Изменено
- setup.md и environment-notes: подключение Claude in Chrome проверено (навигация, JS, чтение страницы), правила работы в группе вкладок MCP, особенность чтения консоли, перезапуск с `--chrome`.

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
