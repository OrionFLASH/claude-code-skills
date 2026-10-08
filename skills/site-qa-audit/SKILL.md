---
name: site-qa-audit
description: >
  QA-аудит любого сайта или веб-приложения через браузер, без исходников: функциональность, логика,
  UX/UI, вёрстка и адаптивность, кросс-браузерность, доступность (WCAG 2.2), скорость, SEO, тексты,
  пассивная безопасность; сверка с GitHub issues, перепроверка исправлений, черновики или публикация;
  строгие запреты (покупки, OAuth, удаление, отправка форм). Используй, когда просят протестировать,
  проверить или найти баги на сайте, в веб-приложении или интерфейсе, особенно с URL: «протестируй
  сайт», «проверь https://…», «найди баги», «QA сайта», «проверь вёрстку, адаптив, мобильную версию,
  доступность, скорость, SEO», «оцени удобство интерфейса», «перепроверь исправления»; "test this
  website", "QA https://…", "find bugs on the site", "website audit", "check responsiveness,
  accessibility, page speed". Не используй для разработки и правки сайта, написания кода тестов
  (Playwright, E2E, unit), дизайна с нуля, ревью кода, нагрузочного теста и пентеста. Вызов без
  /site-qa-audit — сначала подтвердить намерение.
---

# site-qa-audit

Универсальный QA-аудит сайта через браузер. Скил не содержит конкретных сайтов, репозиториев и учётных данных — всё получает на входе.

`<SKILL_DIR>` — папка этого файла. `<RUN_DIR>` — `<OUTPUT_ROOT>/qa-runs/<YYYY-MM-DD>-<host>/`; `<OUTPUT_ROOT>` — путь из запроса, иначе `SITE_QA_OUTPUT_DIR`, иначе `<cwd>` — результаты в `<cwd>/qa-runs/` (`references/intake.md` → «Папка прогона»). Не в репозитории скилов.

**Одно место для всего.** Всё, что порождает прогон, лежит только в `<RUN_DIR>`: `run-config.yaml`, выгрузка issues, находки, перепроверки, скриншоты (в т.ч. разовые), вывод своих скриптов проекта. Не создавать `findings/`, `screenshots/`, `reports/` в корне проекта. Исключение одно: скриншоты, которые пользователь выбрал коммитить (`screenshots: commit`). Свои разовые скрипты принимают папку вывода аргументом (`<RUN_DIR>/raw`, `<RUN_DIR>/screenshots`), а не хардкодят путь в проект.

## Запуск: подтверждение намерения
- **Явный вызов** — пользователь набрал `/site-qa-audit` (в ходе есть `<command-name>/site-qa-audit</command-name>`): подтверждение не нужно, сразу «Порядок работы».
- **Скил подхвачен по смыслу запроса** (без команды): **первым действием**, до `check_env`, файлов и браузера — один вопрос `AskUserQuestion`: «Похоже, вы хотите протестировать <что понято: URL или интерфейс>. Запустить QA-аудит?» В тексте вопроса пересказать понятое: объект, направления, устройства, запреты — только то, что названо. Варианты: «Да, запустить аудит (Recommended)» / «Да, но сначала уточнить задачу» / «Нет, это другое».
  - «Да» → обычный порядок, понятое из запроса не переспрашивать; «уточнить» → опрос с вопроса «Что именно тестируем»;
  - «Нет» → скил прекращает работу и **ничего не создаёт** (ни папок, ни файлов, ни проверок), запрос выполняется как обычный, без скила. Нет ответа — не начинать.
  Подробно — `references/intake.md` → «Подтверждение намерения».

## Главное правило
**Безопасность важнее полноты.** До любых действий в браузере прочитай `references/safety-rules.md`. Перед каждым переходом и каждым кликом/отправкой/подтверждением — `scripts/url_guard.py` (`nav` / `action`). При работе через Playwright/CDP (node-скрипты, setup.js, shot.js) правила применяет `scripts/node/guard.js` автоматически (`guardContext` + `guardedPage`, журнал `<RUN_DIR>/logs/blocked.jsonl`) — `references/browser-guard.md`. Действия с побочными эффектами (загрузка с публичным результатом, рассылки, привязки) — только через `node/invariants.js exec` под инвариантами из run-config — `references/side-effects.md`. Блок правил §4 — дословно в задание каждого субагента и агента плагина. Запрещённое не выполняется, а попадает в отчёт как «не проверено: запрет <правило>».

**Журнал** `<RUN_DIR>/journal.md` (`scripts/journal.py`, `references/run-files.md`): после каждого крупного шага — `done`, новые задачи — `todo`. В новой сессии сначала `journal.py status <RUN_DIR>` и продолжить с первого открытого пункта.

В командах не использовать разделители из знаков равенства (`echo =====`): в zsh они ломают команду (`environment-notes.md` → «Оболочка zsh»).

## Порядок работы

1. **Окружение** — `references/setup.md`: `scripts/check_env.sh` (Windows: `check_env.ps1`). Обязательное не в порядке → предложить исправление; глобальные установки только после подтверждения; нужен перезапуск Claude Code → сказать и остановиться. Какие браузерные инструменты есть именно в этой сессии: `check_env.sh --browser-tools-only --session-tools "<имена своих инструментов через запятую>"`.
2. **Опрос и конфиг** — `references/intake.md`. **Сначала память о сайте**: как только известен хост, найти `<OUTPUT_ROOT>/qa-runs/.site-context/<host>/context.md`; есть — прочитать, показать резюме в 3–6 строк (назначение, роли, сценарии, дата и источники) и спросить «Использовать как есть (Recommended)» / «Обновить» / «Изучить заново» → `context.reuse` (`intake.md` → «Память о сайте»). Если запрос — свободный текст с параметрами, сначала `scripts/intake.py from-text --file <запрос> --output-dir <OUTPUT_ROOT> --out <RUN_DIR>/run-config.yaml`: черновик показать пользователю, недостающее спросить (`intake.md` → «Черновик из свободного запроса»). Сразу завести журнал: `scripts/journal.py init <RUN_DIR> --todo …`. Спросить недостающее (по 1–3 вопроса, с вариантами), не переспрашивать переданное: что тестируем и что считать успехом (`goal`), куда не переходить, вход, устройства, глубина, откуда узнать о сайте (`context`), запреты, потоки (1–4), куда записать итоги (`report_destinations`). Разобрать запреты пользователя в правила (`safety-rules.md` §2) и показать на подтверждение. Побочные эффекты и защита — вопрос из `intake.md` («Побочные эффекты») → `side_effects` / `invariants`. Записать `<RUN_DIR>/run-config.yaml` (схема — `templates/run-config.example.yaml`), `url_guard.py export … --out <RUN_DIR>/rules.json`, повторить `check_env --fast --no-browsers --json <RUN_DIR>/env.json`. Показать сводку, ждать «старт».
3. **Репозитории** — `references/repo-sync.md` §1–2: права (`fetch_issues.py meta`), шаблоны и CONTRIBUTING (`read_templates.py fetch`), выгрузка всех issues с комментариями (`fetch_issues.py sync`), реестр (`fetch_issues.py registry`). Прочитать документы, которые скачал `read_templates.py fetch` (ссылки из форм и config.yml); шкалу серьёзности записать в `repos[].severity_map`. Перепроверка заявленных исправлений: `claims.py extract` → `claims.py plan` → `<RUN_DIR>/claims-plan.md` (`references/claims.md`). Не хватает прав на роль → сообщить, предложить варианты.
4. **Разведка**: **чистое состояние** — если `auth.mode` не `manual-cdp`: профиль Playwright MCP постоянный, поэтому на старте для целевого origin записать и очистить cookies/localStorage тестового браузера (`browser_run_code_unsafe`: `page.context().clearCookies()` + `localStorage.clear()`), если прогон без авторизации или вход ещё не выполнен. При `auth: manual-cdp` (пользователь уже вошёл в своём Chrome, CDP `http://127.0.0.1:9222`) **ничего не очищать и никуда не переходить без нужды**: присоединиться по CDP, состояние для устройств — `node/device_context.js state --cdp … --out <RUN_DIR>/logs/auth-state.json` (`references/devices-auth.md`). Все пути файлов для MCP (скриншоты, снимки) — **абсолютные** `<RUN_DIR>/…`: относительные разрешаются от папки запуска Claude Code. Открыть стартовые URL (Playwright MCP); при охвате «только эти страницы» или запрете переходов — сразу включить **замок навигации** `scripts/nav_lock.js` (`safety-rules.md` §3.11). Затем в фоне `node/links.js` (карта, внешние ссылки). Собрать: карту страниц и шаблонов, ключевые элементы и сценарии, формы, интерактивные компоненты, сторонние источники ресурсов (`browser_network_requests` → хосты), вложенные приложения во iframe. Уточнить тексты запрещённых кнопок на языках сайта. Показать карту, план (направления × страницы × устройства по `references/depth-matrix.md`) и список сторонних ресурсов; спросить исключения → `scope.exclude_patterns`.
   **Контекст сайта** (`context.reuse` не `as-is`): изучить источники из `context.sources` — сам сайт по ссылкам (под `url_guard`), документацию/FAQ (только чтение; чужой домен — без браузера, через загрузку страницы, или с разрешения добавить в `allowed_domains`), GitHub-репозиторий (`gh`, только чтение: README, docs, заголовки issues), файл на диске, описание из чата; учесть `context.notes`. Записать **до прогона** `<OUTPUT_ROOT>/qa-runs/.site-context/<host>/context.md` по `templates/site-context.md` (назначение, роли и состояния аккаунта, основные сценарии, терминология, особенности и ограничения, источники и дата) и `sources.json`; путь к нему передать исполнителям. Не сохранять секреты, cookies, e-mail, имена людей и данные личных кабинетов (`references/run-files.md` → «Память о сайте»).
5. **Прогон** — `references/parallelism.md` + `references/plugins-map.md` + `references/checklists/<направление>.md`:
   - скриптовые проверки в фоне (`node/headers.js`, `links.js`, `a11y.js`, `lighthouse.js` → `<RUN_DIR>/raw/`);
   - детекторы раскладки в фоне (`references/layout-detectors.md`): `node/occlusion.js` (перекрытия, по `--sizes 1440x900,1024x768,768x1024,720x450` и `--device pixel7,iphone15`) и `node/reachability.js` (достижимость; обязательно низкие окна ≤ 450 px и landscape) → `<RUN_DIR>/raw/`; страницы с приложением во iframe — `--frames all` во всех детекторах (a11y.js — по умолчанию);
   - MCP-поток (оркестратор): functional, logic-state и сценарии с состоянием;
   - CLI-потоки (субагенты, `playwright-cli -s=qa-<id>`, до `parallel.max_workers`: по умолчанию 2, **максимум 4**): остальные браузерные направления, группы страниц и независимые гипотезы одновременно; общая сессия входа (`manual`, `manual-cdp`) — один браузерный поток (`parallelism.md`);
   - устройства со входом пользователя — `node/device_context.js run --devices … --state …`, строго последовательно (общая сессия — `parallelism.md` «Когда параллельные потоки запрещены»);
   - действия с побочными эффектами — только `node/invariants.js exec` (перед первым — `invariants.js preflight`: словарь защитных элементов сверяется с прошлым прогоном, расхождение → остановка и вопрос); каждое действие — строка в `<RUN_DIR>/side_effects.md` (что загружено/включено, что осталось в браузере);
   - собственный чек-лист выполняется всегда; усилители из `env.json → enhancers` только дополняют; запрещённые (`banned`) не используются.
   Каждая находка → `<RUN_DIR>/findings.json` по `templates/finding.schema.json` (id, direction, check_id, type, severity по `references/severity.md`, title, url, element, steps, expected, actual, environment, screenshots, console, network, hypothesis, suggestion, sources; по возможности frequency, account_state, platform; для перепроверки — claim_ref {repo, number, quote}; оценка внешней системы — triage; поля чужой формы — target_forms {repo: {area, severity_label}}). Секреты и персональные данные — маскировать сразу. Скриншоты находок — **аннотированные**: пунктирная обводка, тонкая стрелка, короткая подпись, цвет авто (жёлтый/зелёный/фиолетовый) — `references/screenshots.md`: в Playwright MCP `scripts/snap_mcp.js` + `scripts/node/annotate.js`; без MCP (CDP/Playwright) — `scripts/node/shot.js` (= `snap_cdp.js`): снимок, координаты, разметка, автопроверка и контактный лист в одном вызове. Статический обход (`links.js`) не видит контент SPA: его SEO/структурные сигналы (нет h1, пустые meta) подтверждать в браузере перед записью находки.
6. **Дедупликация**: свести находки субагентов, плагинов и скриптов; `fingerprint.py compute` → `fingerprint.py dedupe` → `validate_findings.py findings.json` (схема, дубли id, плейсхолдеры, немаскированные e-mail/токены). Противоречия между источниками — перепроверить вручную, неясно — спросить.
7. **Сверка** — `repo-sync.md` §2–3: `fingerprint.py match findings.json registry.json --out matches.json`, кандидатов прочитать и проверить вручную; присвоить статусы NEW / DUPLICATE-OPEN / FIXED-OK / FIXED-INSUFFICIENT / REGRESSION / ALREADY-COPIED / UNSURE-MATCH. Отдельно перепроверить все issues с заявленным исправлением по плану `claims-plan.md`; результат каждого — `claims.py set` (FIXED-OK / FIXED-INSUFFICIENT / REGRESSION / NOT-CHECKED с причиной).
8. **Вопросы по ходу** (не копить до конца, если блокируют): баг или задумано; нужен вход; запрет блокирует важную проверку; совпадение под вопросом; confirm-действие от `url_guard`/`guard.js`; расхождение словаря интерфейса или нарушенный инвариант.
9. **Публикация** — `repo-sync.md` §4: сводная таблица `build_report.py publish-table <RUN_DIR>` (с политикой `closed_claims`) → подтверждение (если включено) → по ролям: их шаблон (`read_templates.py render … --format body`) / своя подробная копия (`render_draft.py detailed --config <RUN_DIR>/run-config.yaml --repo owner/repo`) / комментарии (`render_draft.py comment …`). Раскрытие, ссылки, маркер и шкала серьёзности берутся из `repos[]` (`disclosure`, `cross_links`, `marker`, `severity_map`). Скриншоты — по `screenshots` репозитория: `commit` (свой репозиторий, `push`) или `web-upload` (чужой/приватный: `node/publish_web.mjs` для issue, `node/comment_web.mjs` для комментария, в браузере пользователя с выполненным входом по CDP; по умолчанию dry-run, реально — `--confirm-publish` после «да»; `references/web-upload.md`). `guard.js` к браузеру GitHub не применяется (правила прогона описывают проверяемый сайт): защита там — замок хоста `--base-url`, нажимается только кнопка ровно «Comment», Close/Reopen — никогда, согласие `--confirm-publish`. Лимиты API. В dry-run — только черновики в `<RUN_DIR>/drafts/`.
10. **Отчёт** — `build_report.py report <RUN_DIR>` → `<RUN_DIR>/report.md` (находки, таблица перепроверки «№, статус, что проверено, чем», side_effects.md, сработавшие запреты из blocked.jsonl) и `build_report.py summary <RUN_DIR>` → `<RUN_DIR>/summary.md` (сводка: итог, статистика, направления); при необходимости дописать итог вручную (`templates/run-report.md`), вывод — по `goal.success` (список проблем / прошли ли сценарии / есть ли блокеры релиза); при репозитории-копии — итоговый issue. Обязательно: статистика по статусам и severity, сводка по направлениям, что не проверено и почему, сработавшие запреты, содержимое side_effects.md (что осталось в браузере и на сайте), задействованные плагины.
11. **Итоги, память, уборка** (`references/run-files.md`):
   - **Куда записать итоги** — по `report_destinations` (по умолчанию только `<RUN_DIR>`): `folder` — скопировать `report.md` и `summary.md` в `<path>/<YYYY-MM-DD>-<host>/`; `github` — существующая логика `repo-sync.md` §4–5 (итоговый issue со сводкой, подтверждение по сводной таблице, в dry-run — черновик в `drafts/`); `artifact` — если в сессии есть инструмент `Artifact`, опубликовать страницу из `report.md` (без `evidence.sensitive`, секретов и персональных данных), иначе пропуск; `custom` — описанное пользователем, после подтверждения. В конце `report.md` дописать раздел «Куда записаны итоги» (путь, ссылка или «пропущено: причина»), затем копировать в папки.
   - **Память о сайте** — дополнить `.site-context/<host>/context.md`: новые сценарии, термины, ответы «баг или задумано», известные проблемы, дата и строка в «Истории»; обновить `sources.json`. Без секретов и персональных данных.
   - **qa-runs/ и git** — `scripts/gitignore_helper.py check <OUTPUT_ROOT>`: код 1 (папка внутри git-репозитория, `qa-runs/` не игнорируется) → **один** вопрос «Добавить qa-runs/ в .gitignore этого репозитория?» — «Да (Recommended)» / «Нет, буду коммитить» / «Использовать .git/info/exclude (локально, без правки репозитория)» → `gitignore_helper.py apply <OUTPUT_ROOT> --mode gitignore|keep|exclude` (`keep` только запоминает ответ, репозиторий не трогает); нет ответа — ничего не править. Код 0 — вопроса нет.
   - Удалить `logs/auth-state.json`, закрыть сессии `playwright-cli`, отметить в журнале завершение.

## Режимы охвата
- **Весь сайт / раздел / список URL** — как выше.
- **Только текущий экран** — Claude in Chrome во вкладке пользователя, если доступен (`setup.md`), иначе URL экрана в Playwright. Только наблюдение; действия — под теми же правилами.
- **Перепроверка исправлений** — шаги 1–3 и 7 по `claims.md` без полного обхода; итог — таблица перепроверки в report.md.

## Справочники
| Файл | Когда читать |
|------|--------------|
| `references/setup.md` | шаг 1 |
| `references/intake.md` | шаг 2 |
| `references/safety-rules.md` | **всегда, до браузера**; блок §4 — в задания исполнителей |
| `references/browser-guard.md` | node-скрипты и Playwright/CDP: правила в действиях (`guard.js`) |
| `references/side-effects.md` | действия с последствиями, инварианты, `side_effects.md` |
| `references/devices-auth.md` | устройства, `auth: manual-cdp`, storageState |
| `references/depth-matrix.md` | план прогона |
| `references/parallelism.md` | распределение потоков, когда параллельность запрещена, задание субагенту |
| `references/plugins-map.md` | выбор усилителей |
| `references/checklists/*.md` | выполнение направлений (11 файлов, check_id) |
| `references/layout-detectors.md` | перекрытия, достижимость, iframe (`--frames all`) |
| `references/severity.md` | оценка находок |
| `references/screenshots.md` | аннотированные скриншоты находок (MCP и `shot.js`) |
| `references/claims.md` | перепроверка заявленных исправлений (шаги 3, 7) |
| `references/repo-sync.md` | шаги 3, 7, 9, 11 (`report_destinations: github`) |
| `references/web-upload.md` | публикация скриншотов через веб-форму GitHub (`screenshots: web-upload`) |
| `references/run-files.md` | journal.md, report.md, summary.md, сводная таблица перед публикацией, куда записать итоги, память о сайте, qa-runs/ и git (шаги 2, 4, 9–11) |
| `references/environment-notes.md` | известные ограничения среды, zsh |
| `templates/site-context.md` | память о сайте `.site-context/<host>/context.md` (шаги 2, 4, 11) |
| `INSTALL.md` | установка и обновление (macOS, Windows), промпты для Claude Code |

## Скрипты (`scripts/`)
| Скрипт | Назначение |
|--------|-----------|
| `check_env.sh/.ps1` | окружение, браузеры (реальный запуск), усилители → таблица и `env.json`; `--session-tools` — какие браузерные инструменты есть в этой сессии |
| `url_guard.py` | `nav` / `resource` / `action` / `export` / `blocked-origins` / `selftest`; коды 0 allow, 2 confirm, 3 deny |
| `intake.py` | `from-text`: свободный запрос → черновик run-config.yaml на подтверждение |
| `journal.py` | `init` / `todo` / `done` / `note` / `status`: журнал прогона journal.md |
| `fetch_issues.py` | `meta` / `sync` (инкрементально) / `registry` |
| `read_templates.py` | `fetch` (+ документы по ссылкам из форм и config.yml, `--local`) / `parse` / `render --format json\|body\|draft` |
| `claims.py` | `extract` / `plan` / `set`: заявления владельца из комментариев → план перепроверки → результат (rechecks.json) |
| `fingerprint.py` | `compute` / `dedupe` / `match` / `one` |
| `render_draft.py` | черновики issue и комментариев; `--config/--repo`, `--disclosure none`, `--no-links`, `--marker neutral\|none`; `severity` |
| `validate_findings.py` | проверка findings.json по схеме и на немаскированные данные |
| `build_report.py` | `report` (report.md из findings.json, перепроверки, side_effects.md, blocked.jsonl) / `summary` (summary.md: итог, статистика, направления) / `publish-table` |
| `gitignore_helper.py` | `check <OUTPUT_ROOT>` (код 1 — `qa-runs/` в git-репозитории не игнорируется) / `apply <OUTPUT_ROOT> --mode gitignore\|exclude\|keep` |
| `snap_mcp.js` | скриншот + координаты элементов для аннотации (Playwright MCP); селекторы `iframe … >>> …` |
| `snap_cdp.js` | CDP-аналог `snap_mcp.js` (входная точка `node/shot.js`) |
| `nav_lock.js` | замок навигации для Playwright MCP (`browser_run_code_unsafe`): только разрешённые URL, блок pushState/window.open |
| `node/annotate.js` | аннотация PNG: пунктир, стрелка, подпись, автоцвет, размещение без перекрытий |
| `node/shot.js` | снимок + разметка: `--cdp`, `--device`, `--setup`, `@avoid`, авто-соседи, автопроверка, `--batch`, `sheet` |
| `node/guard.js` | `guardContext` / `guardedPage`: правила url_guard в route и в каждом действии, `blocked.jsonl`; `check` — проверка элемента |
| `node/invariants.js` | `preflight` / `exec` / `log`: побочные эффекты под инвариантами, `side_effects.md`, `vocabulary.json` |
| `node/occlusion.js` | перекрытия интерактивных элементов (elementFromPoint, 5 точек, iframe), `--sizes` / `--device` |
| `node/reachability.js` | достижимость элементов за краем окна (колесо, жест) |
| `node/device_context.js` | `list` / `state` (из CDP) / `run` (сценарий × устройства) |
| `node/frames.js` | общие функции кадров (смещения, `iframe >>> sel`, текст по кадрам) |
| `node/publish_web.mjs` | issue со скриншотами через веб-форму GitHub (CDP, плейсхолдер → вложение → проверка по API) |
| `node/comment_web.mjs` | комментарий со скриншотами; нажимает только «Comment», закрытый issue остаётся закрытым |
| `node/*.js` | `a11y.js` (axe), `lighthouse.js`, `headers.js`, `links.js`, `probe.js`; зависимости — `cd scripts/node && npm install` |

Python — только стандартная библиотека; `scripts/shared/` — вендоренные общие модули репозитория скилов. Тесты — `tests/unit.sh` (офлайн; браузерные наборы `test_stream_b.sh`, `test_stream_c.sh` пропускаются без Playwright).
