---
name: site-qa-audit
description: >
  Полный QA-аудит любого сайта через браузер без макета и исходников: функциональность, логика и состояние,
  UX, UI, адаптивность и кросс-браузерность, доступность (WCAG 2.2 AA), производительность, SEO и контент,
  пассивная безопасность, продуктовые предложения. Сверяет находки с issues указанных GitHub-репозиториев,
  определяет статусы (новое, дубль, исправлено, недостаточно исправлено, регрессия) и публикует по заданным
  правилам или пишет черновики (dry-run). Соблюдает базовые и пользовательские запреты (покупки, OAuth,
  удаление, отправка форм людям, выход за домен). Используй, когда просят «протестируй сайт», «QA-аудит»,
  «проверь удобство сайта», «найди баги на сайте», «проверь доступность/скорость/SEO сайта»,
  «site audit», «QA this website», «test my site», «find bugs on the site», «website usability review».
  Вызов: /site-qa-audit.
---

# site-qa-audit

Универсальный QA-аудит сайта через браузер. Скил не содержит конкретных сайтов, репозиториев и учётных данных — всё получает на входе.

`<SKILL_DIR>` — папка этого файла. `<RUN_DIR>` — `./qa-runs/<YYYY-MM-DD>-<host>/` в текущей рабочей папке.

## Главное правило
**Безопасность важнее полноты.** До любых действий в браузере прочитай `references/safety-rules.md`. Перед каждым переходом и каждым кликом/отправкой/подтверждением — `scripts/url_guard.py` (`nav` / `action`). Блок правил §4 — дословно в задание каждого субагента и агента плагина. Запрещённое не выполняется, а попадает в отчёт как «не проверено: запрет <правило>».

## Порядок работы

1. **Окружение** — `references/setup.md`: `scripts/check_env.sh` (Windows: `check_env.ps1`). Обязательное не в порядке → предложить исправление; глобальные установки только после подтверждения; нужен перезапуск Claude Code → сказать и остановиться.
2. **Опрос и конфиг** — `references/intake.md`: спросить недостающее (по 1–3 вопроса, с вариантами), не переспрашивать переданное. Разобрать запреты пользователя в правила (`safety-rules.md` §2) и показать на подтверждение. Записать `<RUN_DIR>/run-config.yaml` (схема — `templates/run-config.example.yaml`), `url_guard.py export … --out <RUN_DIR>/rules.json`, повторить `check_env --fast --no-browsers --json <RUN_DIR>/env.json`. Показать сводку, ждать «старт».
3. **Репозитории** — `references/repo-sync.md` §1–2: права (`fetch_issues.py meta`), шаблоны и CONTRIBUTING (`read_templates.py fetch`), выгрузка всех issues с комментариями (`fetch_issues.py sync`), реестр (`fetch_issues.py registry`). Не хватает прав на роль → сообщить, предложить варианты.
4. **Разведка**: **чистое состояние** — профиль Playwright MCP постоянный, поэтому на старте для целевого origin записать и очистить cookies/localStorage тестового браузера (`browser_run_code_unsafe`: `page.context().clearCookies()` + `localStorage.clear()`), если прогон без авторизации или вход ещё не выполнен. Все пути файлов для MCP (скриншоты, снимки) — **абсолютные** `<RUN_DIR>/…`: относительные разрешаются от папки запуска Claude Code. Открыть стартовые URL (Playwright MCP); при охвате «только эти страницы» или запрете переходов — сразу включить **замок навигации** `scripts/nav_lock.js` (`safety-rules.md` §3.11). Затем в фоне `node/links.js` (карта, внешние ссылки). Собрать: карту страниц и шаблонов, ключевые элементы и сценарии, формы, интерактивные компоненты, сторонние источники ресурсов (`browser_network_requests` → хосты). Уточнить тексты запрещённых кнопок на языках сайта. Показать карту, план (направления × страницы × устройства по `references/depth-matrix.md`) и список сторонних ресурсов; спросить исключения → `scope.exclude_patterns`.
5. **Прогон** — `references/parallelism.md` + `references/plugins-map.md` + `references/checklists/<направление>.md`:
   - скриптовые проверки в фоне (`node/headers.js`, `links.js`, `a11y.js`, `lighthouse.js` → `<RUN_DIR>/raw/`);
   - MCP-поток (оркестратор): functional, logic-state и сценарии с состоянием;
   - CLI-потоки (субагенты, `playwright-cli -s=qa-<id>`, до `parallel.max_workers`): остальные браузерные направления;
   - собственный чек-лист выполняется всегда; усилители из `env.json → enhancers` только дополняют; запрещённые (`banned`) не используются.
   Каждая находка → `<RUN_DIR>/findings.json` по `templates/finding.schema.json` (id, direction, check_id, type, severity по `references/severity.md`, title, url, element, steps, expected, actual, environment, screenshots, console, network, hypothesis, suggestion, sources). Секреты и персональные данные — маскировать сразу. Статический обход (`links.js`) не видит контент SPA: его SEO/структурные сигналы (нет h1, пустые meta) подтверждать в браузере перед записью находки.
6. **Дедупликация**: свести находки субагентов, плагинов и скриптов; `fingerprint.py compute` → `fingerprint.py dedupe` → `validate_findings.py findings.json` (схема, дубли id, плейсхолдеры, немаскированные e-mail/токены). Противоречия между источниками — перепроверить вручную, неясно — спросить.
7. **Сверка** — `repo-sync.md` §2–3: `fingerprint.py match findings.json registry.json --out matches.json`, кандидатов прочитать и проверить вручную; присвоить статусы NEW / DUPLICATE-OPEN / FIXED-OK / FIXED-INSUFFICIENT / REGRESSION / ALREADY-COPIED / UNSURE-MATCH. Отдельно перепроверить все issues с заявленным исправлением.
8. **Вопросы по ходу** (не копить до конца, если блокируют): баг или задумано; нужен вход; запрет блокирует важную проверку; совпадение под вопросом; confirm-действие от `url_guard`.
9. **Публикация** — `repo-sync.md` §4: сводная таблица → подтверждение (если включено) → по ролям: их шаблон (`read_templates.py render` для форм) / своя подробная копия (`render_draft.py detailed`) / комментарии (`render_draft.py comment`); маркер `<!-- site-qa-audit:fp=… -->`; перекрёстные ссылки; скриншоты коммитом; лимиты API. В dry-run — только черновики в `<RUN_DIR>/drafts/`.
10. **Отчёт** — `templates/run-report.md` → `<RUN_DIR>/report.md`; при репозитории-копии — итоговый issue. Обязательно: статистика по статусам и severity, сводка по направлениям, что не проверено и почему, сработавшие запреты, задействованные плагины. Удалить `logs/auth-state.json`, закрыть сессии `playwright-cli`.

## Режимы охвата
- **Весь сайт / раздел / список URL** — как выше.
- **Только текущий экран** — Claude in Chrome во вкладке пользователя, если доступен (`setup.md`), иначе URL экрана в Playwright. Только наблюдение; действия — под теми же правилами.

## Справочники
| Файл | Когда читать |
|------|--------------|
| `references/setup.md` | шаг 1 |
| `references/intake.md` | шаг 2 |
| `references/safety-rules.md` | **всегда, до браузера**; блок §4 — в задания исполнителей |
| `references/depth-matrix.md` | план прогона |
| `references/parallelism.md` | распределение потоков, задание субагенту |
| `references/plugins-map.md` | выбор усилителей |
| `references/checklists/*.md` | выполнение направлений (10 файлов, check_id) |
| `references/severity.md` | оценка находок |
| `references/repo-sync.md` | шаги 3, 7, 9 |
| `references/environment-notes.md` | известные ограничения среды |

## Скрипты (`scripts/`)
| Скрипт | Назначение |
|--------|-----------|
| `check_env.sh/.ps1` | окружение, браузеры (реальный запуск), усилители → таблица и `env.json` |
| `url_guard.py` | `nav` / `resource` / `action` / `export` / `blocked-origins` / `selftest`; коды 0 allow, 2 confirm, 3 deny |
| `fetch_issues.py` | `meta` / `sync` (инкрементально) / `registry` |
| `read_templates.py` | `fetch` / `parse` / `render` шаблонов issues (.md и YAML forms) |
| `fingerprint.py` | `compute` / `dedupe` / `match` / `one` |
| `render_draft.py` | черновики issue (подробный шаблон) и комментариев |
| `validate_findings.py` | проверка findings.json по схеме и на немаскированные данные |
| `nav_lock.js` | замок навигации для Playwright MCP (`browser_run_code_unsafe`): только разрешённые URL, блок pushState/window.open |
| `node/*.js` | `a11y.js` (axe), `lighthouse.js`, `headers.js`, `links.js`, `probe.js`; зависимости — `cd scripts/node && npm install` |

Python — только стандартная библиотека; `scripts/shared/` — вендоренные общие модули репозитория скилов.
