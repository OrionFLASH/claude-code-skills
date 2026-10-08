# Журнал изменений site-qa-audit

Формат — [Keep a Changelog](https://keepachangelog.com/ru/1.1.0/), версии — SemVer, теги `site-qa-audit/vX.Y.Z`.

## [1.1.2] — 2026-10-08
### Изменено
- Папка результатов по умолчанию: если путь не задан в запросе, `output_dir` и `SITE_QA_OUTPUT_DIR`, берётся `<cwd>/qa-runs` без вопроса (вопрос остаётся только для домашней папки и репозитория скилов). Убрано предупреждение `intake.py` о папке внутри git-репозитория.

## [1.1.1] — 2026-10-08
### Исправлено
- Результаты прогона и разовые перепроверки оказывались в `findings/` и `screenshots/` рядом с `qa-runs`. Правило «всё только в `<RUN_DIR>`» вынесено в SKILL.md и `intake.md`.

## [1.1.0] — 2026-10-08
По итогам боевого прогона (сайт со входом вручную, чужой репозиторий с формами issues, перепроверка исправлений, телефон и десктоп). Включает незавершённый ранее 1.0.4 (папка результатов и аннотированные скриншоты). Все новые поля схемы и разделы run-config необязательные: старые `findings.json` и `run-config.yaml` проходят без изменений.

### Добавлено — папка результатов и скриншоты (бывший 1.0.4)
- Папка результатов `<OUTPUT_ROOT>`: путь из запроса → `output_dir` в run-config → переменная `SITE_QA_OUTPUT_DIR` → вопрос пользователю (`intake.md` → «Папка прогона»); результаты никогда не пишутся в репозиторий скилов. `check_env` показывает `SITE_QA_OUTPUT_DIR` и пишет `output_dir` в `env.json`; кэш issues — `<OUTPUT_ROOT>/qa-runs/.cache/issues/`.
- `scripts/node/annotate.js`: аннотация PNG — пунктирная обводка, тонкая стрелка, короткая подпись, автоцвет (жёлтый/зелёный/фиолетовый), размещение подписи без перекрытий.
- `scripts/snap_mcp.js`: скриншот и координаты элементов для аннотации из Playwright MCP (`browser_run_code_unsafe`).
- `references/screenshots.md`: правила оформления и порядок съёмки. `render_draft.py`: если есть `X-annotated.png`, оригинал `X.png` в черновик не выводится.

### Добавлено — перепроверка исправлений, схема, черновики, отчёт (Python)
- `scripts/claims.py` (`extract` / `plan` / `set`): перепроверка заявленных исправлений. Из комментариев владельца берутся заявления («Исправили (vX.Y.Z): …», «Частично», «Осталось: …»), пункты списка, URL и пути, тексты в кавычках; из тела issue — раздел, шаги, ожидаемое. План — чек-лист `claims-plan.md` с цитатой заявления, результат — `rechecks.json`. На обезличенном реестре из 48 issues с fix_claimed план содержит 48 пунктов, у каждого есть цитата.
- Статус `NOT-CHECKED` с причиной (`not_checked_reason`: logout-required, other-account-type, forbidden, steps-unclear, environment, other) и поле `claim_ref {repo, number, quote}`; раздел `rechecks` в findings.json.
- Поля находки `frequency`, `account_state`, `platform`, `triage {severity, confidence, kind, note}`, `target_forms {repo: {area, severity_label}}` (необязательные); в `issue-detailed.md` — строки «Частота», «Аккаунт», «Платформа», «Внешняя оценка» и раздел «Заявленное исправление».
- Направление `content-i18n` (смешение языков, форматы чисел и дат, термины, дефис и тире, падежи, непереведённые строки) и чек-лист `references/checklists/content-i18n.md` (всего 11 направлений).
- `render_draft.py`: `--config/--repo` (настройки репозитория из run-config), `--disclosure none`, `--no-links`, `--marker skill|neutral|none`, шкала `severity_map`, команда `severity`. Нейтральный маркер `<!-- qa-fp:… -->` распознают `fingerprint.py` и `fetch_issues.py`. При `disclosure: none` и `cross_links: false` в тексте нет «site-qa-audit», «Claude», номеров issues другого репозитория и маркера.
- `run-config.yaml → repos[]`: `disclosure`, `cross_links`, `marker`, `closed_claims` (comment | new | skip — что делать с недоработкой закрытого issue, показывается в сводной таблице), `severity_map`; `auth.account_states`.
- `scripts/build_report.py`: `report` собирает report.md из findings.json, таблицы перепроверки («№, статус, что проверено, чем»), side_effects.md и logs/blocked.jsonl; `publish-table` — сводная таблица перед публикацией с действием по closed_claims.
- `scripts/intake.py from-text`: свободный запрос → черновик run-config.yaml (URL, репозитории и роли, устройства, вход, состояния аккаунта, запреты, побочные эффекты) на подтверждение.
- `scripts/journal.py` (`init` / `todo` / `done` / `note` / `status`): журнал прогона journal.md для продолжения после обрыва.
- `read_templates.py fetch` скачивает документы репозитория, на которые ссылаются формы, config.yml и CONTRIBUTING (`<out>-docs/`), и перечисляет внешние ссылки; `--local` для офлайн-проверки; `render --format json|body|draft`.
- `check_env`: раздел «Браузерные инструменты» — что доступно именно в этой сессии (`--session-tools`, `--browser-tools-only`): Playwright MCP, Claude in Chrome с недостающими ключевыми инструментами, playwright-cli, браузер с CDP-портом на localhost; `env.json → browser_tools`.
- references: `claims.md`, `run-files.md`; раздел «Оболочка zsh» в `environment-notes.md` (в командах нет разделителей из знаков равенства — проверяется тестом).

### Добавлено — безопасность в браузере, побочные эффекты, детекторы, устройства (Node)
- `scripts/node/guard.js`: правила безопасности прямо в браузерных действиях — `guardContext` (блок ресурсов и навигации на уровне route, документы iframe, закрытие вкладок на чужие домены, отклонение диалогов) и `guardedPage` (click/fill/check/setInputFiles/goto…: роль, доступное имя и контекст элемента → тот же `url_guard.check_action`; deny — пропуск и `blocked.jsonl`, confirm — остановка и вопрос). Node-скрипты принимают `--rules` и `--log`.
- Побочные эффекты: разделы `side_effects` и `invariants` в run-config, `scripts/node/invariants.js` (`preflight` — сверка словаря защитных элементов с прошлым прогоном; `exec` — действие под инвариантом «после загрузки за N мс появился и отмечен флажок», иначе остановка; `log`), журнал `side_effects.md` (что загружено, включено, что осталось в браузере), `vocabulary.json`; вопрос о побочных эффектах в опросе.
- `scripts/node/occlusion.js`: детерминированный детектор перекрытий — `elementFromPoint` в 5 точках видимой части, пара «закрыт/закрывает», площадь и z-index; временные перекрытия закреплёнными панелями не считаются дефектом; iframe; `--sizes`, `--device`.
- `scripts/node/reachability.js`: достижимость элементов за краем окна (прокручиваемые предки, колесо, `Input.synthesizeScrollGesture`), вердикт «достижим/недостижим»; по умолчанию 720×450 и Pixel 7 landscape.
- `scripts/node/device_context.js`: каталог устройств (Pixel 7, iPhone 15, iPad, 360×640, landscape, низкие окна), режим `auth: manual-cdp` (storageState из браузера пользователя без очистки cookies), отдельный WebKit, один сценарий на списке устройств; `run-config → auth.cdp_url`, `devices.emulate`.
- `scripts/node/shot.js` и `scripts/snap_cdp.js`: снимок и разметка в одном вызове через CDP/Playwright — `--cdp`, `--device`, `--setup`, цели `selector|подпись|kind`, `@avoid`, авто-avoid соседних элементов, перебор ширины и места подписи при высоком overlapCost, автопроверка (подпись в кадре, не закрывает чужие рамки, контраст), контактный лист.
- Iframe: `frames: main|all` в run-config, `--frames all` в occlusion/reachability/a11y (по умолчанию)/links, селекторы `iframe … >>> …` в shot.js и snap_mcp.js с прибавлением координат кадра; `scripts/node/frames.js`.
- references: `browser-guard.md`, `side-effects.md`, `layout-detectors.md`, `devices-auth.md`; `parallelism.md` — когда параллельные потоки запрещены (общая сессия входа, CDP, побочные эффекты).

### Добавлено — публикация со скриншотами в чужой репозиторий
- Стратегия `screenshots: web-upload` (`repos[].screenshots`, `repos[].web_upload {cdp, base_url}`): `scripts/node/publish_web.mjs` (issue: плейсхолдер → загрузка через веб-форму GitHub → замена → проверка по API) и `scripts/node/comment_web.mjs` (комментарий, в том числе к закрытому issue), общая логика — `web_upload_lib.mjs`. Работают в браузере пользователя с выполненным входом (CDP), логины и токены не обрабатывают; нет входа — остановка с сообщением; по умолчанию dry-run, реальное действие — `--confirm-publish`. Устойчивые селекторы нового интерфейса GitHub с запасными вариантами; нажимается только кнопка ровно «Comment», Close/Reopen — никогда; после комментария проверяется, что состояние issue не изменилось. `guard.js` к браузеру GitHub намеренно не применяется (правила прогона описывают проверяемый сайт) — защита: замок хоста `--base-url`, запрет Close/Reopen/Delete, `--confirm-publish`. Описание — `references/web-upload.md`, права — `repo-sync.md` §1.

### Изменено
- Схема: `actual` не обязателен для `proposal` и `user-story` (if/else в схеме; `validate_findings.py` понимает `if/then/else` и `additionalProperties`).
- `validate_findings.py` и маскирование в `render_draft.py` не принимают имена файлов вида `F-012-bell-over-legend-annotated` за токены.
- `fetch_issues.py sync` сохраняет автора issue и `author_association` комментариев (для определения владельца в claims.py).
- `scripts/node/annotate.js`: ширина подписи `labelWidth`, в отчёте `contrast`, `inside`, `covers`; `render()` для повторов без перезапуска браузера.
- `scripts/node/lib.js`: маски «хост/путь» в `forbidden_domains` и базовых хостах (как в url_guard.py), `kind: 'subframe'`; `guardContext` делегирует в guard.js; `loadRunConfig`, `multiArg`, `appendJsonl`.
- SKILL.md: шаги 1–10 дополнены новыми командами, режим «Перепроверка исправлений», справочники и таблица скриптов; `intake.md` (from-text, побочные эффекты, `manual-cdp`, раскрытие, ссылки, closed_claims, severity_map, скриншоты `web-upload`), `repo-sync.md`, `severity.md`, `setup.md`, `depth-matrix.md`, `plugins-map.md`.
- `templates/run-config.example.yaml`: `auth.mode: manual-cdp`, `auth.cdp_url`, `auth.account_states`, `devices.emulate`, `frames`, `side_effects`, `invariants`, пример репозитория с `screenshots: commit|web-upload|none`, `web_upload`, `disclosure`, `cross_links`, `marker`, `closed_claims`, `severity_map`.
- Пункт 17 спецификации: в документации скила не нашлось команд с разделителями из знаков равенства; добавлено правило и проверка в тестах.

### Тесты
- `tests/unit.sh` (34 проверки): прежние офлайн-проверки, синтаксис новых Python- и Node-скриптов, разделы run-config 1.1.0, вызов наборов A/B/C; браузерные B и C пропускаются (SKIP), если нет node, Playwright или Chromium (`QA_SKIP_BROWSER=1` — пропустить явно).
- `tests/test_stream_a.sh` (32 проверки, без сети): claims, схема, render_draft, intake, journal, build_report, read_templates, check_env; фикстуры `registry-claims.json` (обезличенный реестр), `findings-v11.json`, `run-config-foreign.yaml`, `repo-templates/`.
- `tests/test_stream_b.sh` + `stream_b.test.js` (29 браузерных тестов на локальных фикстурах через `python3 -m http.server`): перекрытие 36×20, список под закреплённой панелью, панель выше окна с overflow hidden/auto, iframe-приложение, защитный флажок через 1 с / не появляется / переименован, guard, устройства, shot.
- `tests/test_stream_c.sh` (34 офлайн-теста): имитация нового интерфейса GitHub (`gh-new-issue.html`, `gh-closed-issue.html`), headless Chromium с CDP вместо браузера пользователя, `tests/helpers/fake_gh.py` вместо `gh`.

### Не сделано
- Отдельное поле `annotations` в схеме находки (из плана 1.0.4) не добавлено: аннотированные скриншоты передаются в `screenshots` с суффиксом `-annotated.png`.
- Web-upload и детекторы проверены только на локальных фикстурах, не на github.com и не на реальном сайте.

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
