# site-qa-audit

Полный QA-аудит любого сайта через браузер — без макета и исходного кода. Скил проходит сайт как пользователь и как инструменты (axe, Lighthouse, анализ заголовков и ссылок, детекторы перекрытий и достижимости), сверяет находки с issues в указанных GitHub-репозиториях, перепроверяет заявленные исправления и публикует результаты по заданным правилам — или складывает черновики (dry-run).

Внутри скила нет конкретных сайтов, репозиториев, логинов и токенов: всё передаётся на входе.

**Установка и обновление** (macOS, Windows, промпты для Claude Code) — [INSTALL.md](INSTALL.md).

**Запуск.** Командой `/site-qa-audit` или обычной просьбой протестировать, проверить, найти баги на сайте, в веб-приложении, интерфейсе (вёрстка, адаптивность, доступность, скорость, SEO), в том числе с URL. Если скил подхвачен по смыслу запроса, он сначала спрашивает: «Похоже, вы хотите протестировать <что понял>. Запустить QA-аудит?» — при «Нет, это другое» ничего не создаёт. На разработку сайта и написание кода тестов не срабатывает.

## Что проверяется
| Направление | Кратко |
|-------------|--------|
| `functional` | клики, ссылки (битые, 404), формы (без отправки людям), поиск, фильтры, интерактивные компоненты и карты, ошибки JS, ответы 4xx/5xx |
| `logic-state` | «Назад», обновление, состояние в URL и deep-link, localStorage/cookies, тупики, двойные клики, прерывания, граничный ввод, гонки |
| `ux` | задачи глазами персон, 10 эвристик Нильсена, законы UX, шаги до цели, понятность текстов, обратная связь |
| `visual-ui` | палитра, контраст, тач-зоны ≥ 44×44, типографика, отступы, сетка, состояния, темы, иконки |
| `responsive-cross-browser` | 360–1920 px, Chromium/Firefox/WebKit, ориентация, жесты |
| `accessibility` | WCAG 2.2 AA, axe-core, клавиатура, фокус, alt, ARIA, заголовки, язык |
| `performance` | Lighthouse mobile/desktop, Core Web Vitals, вес, кэш, сжатие, lazy-loading |
| `seo-content` | title, description, OG, canonical, robots, sitemap, hreflang, опечатки, перевод, ошибки в данных |
| `content-i18n` | смешение языков, форматы чисел и дат, терминология, дефис и тире, склонения, непереведённые строки |
| `security-passive` | HTTPS, HSTS, CSP и др. заголовки, mixed content, утечки, sourcemaps — **только пассивно** |
| `product` | user stories с критериями приёмки, предложения, редизайн с приоритетом эффект/усилия |

## Входные параметры (опрос)
Если параметр не передан в запросе, скил спросит его с вариантами ответа (подробно — `references/intake.md`).

| # | Параметр | По умолчанию |
|---|----------|--------------|
| 1 | Стартовые URL | — (обязательно) |
| 1a | Что тестируем (сценарии, раздел, форма, адаптив, доступность, скорость, SEO) и что считать успехом (`goal`) | основные сценарии; список проблем с приоритетами |
| 2 | Разрешённые домены для навигации; куда не переходить (разделы, URL, поддомены) | домен сайта и поддомены; сторонние ресурсы (CDN, тайлы, API, шрифты) грузятся, переходы на чужие страницы — нет |
| 3 | Авторизация: нет / тестовый аккаунт (env) / ручной вход / `manual-cdp` (пользователь уже вошёл в своём Chrome, подключение по CDP без очистки cookies) | нет |
| 4 | Охват: весь сайт / раздел / список URL / текущий экран | весь сайт |
| 5 | Направления | все |
| 6 | Глубина: smoke / standard / deep | standard (лимит страниц 50) |
| 7 | Устройства и браузеры | по глубине (`references/depth-matrix.md`) |
| 8 | Репозитории: URL, роли (`check`, `write-new`, `copies`, `comment`), стиль, метки, подтверждение, скриншоты (`commit` / `web-upload` / `none`), раскрытие (`disclosure`, `marker`), ссылки между репозиториями (`cross_links`), недоработка в закрытом issue (`closed_claims`), шкала серьёзности (`severity_map`) | нет |
| 9 | Запреты пользователя (свободный текст + чек-лист: покупки, оплата, регистрация, отправка форм, удаление, настройки аккаунта, рассылки, внешние ссылки…) | только базовые |
| 10 | Плагины: все установленные / выбрать / только свои чек-листы | все установленные |
| 11 | Язык отчётов и issues | русский |
| 12 | Параллельные потоки: независимые направления, группы страниц, гипотезы (`parallel.max_workers`, 1–4) | 2 (через playwright-cli; общая сессия входа — 1) |
| 13 | Режим: dry-run / боевой | dry-run |
| 14 | Побочные эффекты (публичный рейтинг, рассылка, необратимая загрузка) и защита от них (`side_effects`, `invariants`) | нет |
| 15 | Папка результатов | путь из запроса / `SITE_QA_OUTPUT_DIR` / `<cwd>/qa-runs/` |
| 16 | Откуда узнать о сайте (сам сайт, документация, GitHub, файл, описание) и что важно изучить (`context`) | сам сайт; сохранённая память о сайте — по выбору |
| 17 | Куда записать итоги, кроме локальной папки: другая папка, GitHub issues, страница-артефакт Claude (`report_destinations`) | только локальная папка |

Свободный запрос можно сразу разобрать в черновик конфига: `scripts/intake.py from-text` (черновик показывается на подтверждение).

Результаты — в `<OUTPUT_ROOT>/qa-runs/<YYYY-MM-DD>-<host>/` (`<OUTPUT_ROOT>` — путь из запроса, иначе переменная `SITE_QA_OUTPUT_DIR`, иначе папка запуска Claude Code; в репозиторий скилов не пишется): `run-config.yaml`, `findings.json`, `report.md`, `summary.md`, `journal.md`, `claims-plan.md`, `rechecks.json`, `side_effects.md`, `screenshots/`, `drafts/`, `raw/`, `logs/`. Память о сайте (назначение, роли, сценарии, термины, источники) — `<OUTPUT_ROOT>/qa-runs/.site-context/<host>/context.md`: при следующем прогоне скил показывает её и спрашивает «как есть / обновить / изучить заново». Если `qa-runs/` оказалась внутри git-репозитория и не игнорируется, в конце прогона скил один раз спрашивает, добавить ли её в `.gitignore` (или в `.git/info/exclude`).

## Примеры вызова
```text
/site-qa-audit
Протестируй сайт https://example.com — smoke, только functional и accessibility, без репозиториев.
QA-аудит https://shop.example.com, глубоко, сверить с owner/shop (только сверка) и записать копии всех находок
в owner/qa-notes. Ничего не покупать, не трогать раздел профиля. Dry-run.
Проверь удобство сайта https://app.example.com, вход тестовым аккаунтом из QA_USER / QA_PASS.
Find bugs on https://example.org, standard depth, English report.
Перепроверь исправления из owner/repo на https://app.example.com: я уже вошёл в своём Chrome (порт 9222),
телефон Pixel 7 и десктоп, не нажимай «Поддержать». Недоработки — комментарием в закрытых issues,
скриншоты загрузить через веб-форму, без упоминания скила и без ссылок на другие репозитории.
```

## Команды (основные)
Все пути — абсолютные; `<SKILL_DIR>` — папка скила, `<RUN_DIR>` — папка прогона. Подробности — в указанных `references/`.
```bash
# свободный запрос → черновик run-config.yaml (intake.md)
python3 <SKILL_DIR>/scripts/intake.py from-text --file request.txt --output-dir <OUTPUT_ROOT> --out <RUN_DIR>/run-config.yaml
# журнал прогона для продолжения после обрыва (run-files.md)
python3 <SKILL_DIR>/scripts/journal.py init <RUN_DIR> --todo "Разведка" --todo "Перепроверка заявлений"
python3 <SKILL_DIR>/scripts/journal.py status <RUN_DIR>
# перепроверка заявленных исправлений (claims.md)
python3 <SKILL_DIR>/scripts/claims.py extract <RUN_DIR>/registry.json --repo owner/repo --out <RUN_DIR>/claims.json
python3 <SKILL_DIR>/scripts/claims.py plan <RUN_DIR>/claims.json --site https://example.com/ --out <RUN_DIR>/claims-plan.md --json <RUN_DIR>/rechecks.json
python3 <SKILL_DIR>/scripts/claims.py set <RUN_DIR>/rechecks.json --number 14 --status NOT-CHECKED --reason other-account-type
# черновик для чужого репозитория без подписи скила и без ссылок (repo-sync.md §4)
python3 <SKILL_DIR>/scripts/render_draft.py detailed <RUN_DIR>/findings.json --id F-003 --config <RUN_DIR>/run-config.yaml --repo owner/repo --out <RUN_DIR>/drafts/owner__repo/03.md
# сводная таблица перед публикацией и отчёт (run-files.md)
python3 <SKILL_DIR>/scripts/build_report.py publish-table <RUN_DIR>
python3 <SKILL_DIR>/scripts/build_report.py report <RUN_DIR>
python3 <SKILL_DIR>/scripts/build_report.py summary <RUN_DIR>        # summary.md для других мест (report_destinations)
# qa-runs/ и git: 0 — ничего, 1 — спросить пользователя; apply — только после ответа (run-files.md)
python3 <SKILL_DIR>/scripts/gitignore_helper.py check <OUTPUT_ROOT>
python3 <SKILL_DIR>/scripts/gitignore_helper.py apply <OUTPUT_ROOT> --mode gitignore   # или exclude / keep
# проверка элемента правилами безопасности (browser-guard.md): код 0 allow, 2 confirm, 3 deny
node <SKILL_DIR>/scripts/node/guard.js check --url https://example.com/ --selector "text=Поддержать" --rules <RUN_DIR>/rules.json
# действие с побочным эффектом под инвариантом (side-effects.md)
node <SKILL_DIR>/scripts/node/invariants.js preflight --config <RUN_DIR>/run-config.yaml --url https://example.com/upload --run-dir <RUN_DIR>
node <SKILL_DIR>/scripts/node/invariants.js exec --config <RUN_DIR>/run-config.yaml --effect SE1 --url https://example.com/upload --file test.sav --run-dir <RUN_DIR> --rules <RUN_DIR>/rules.json
# перекрытия и достижимость (layout-detectors.md)
node <SKILL_DIR>/scripts/node/occlusion.js https://example.com/ --sizes 1440x900,1024x768,720x450 --device pixel7,iphone15 --frames all --rules <RUN_DIR>/rules.json --out <RUN_DIR>/raw/occlusion.json
node <SKILL_DIR>/scripts/node/reachability.js https://example.com/ --sizes 720x450 --device pixel7-landscape --out <RUN_DIR>/raw/reachability.json
# устройства со входом пользователя (devices-auth.md)
node <SKILL_DIR>/scripts/node/device_context.js state --cdp http://127.0.0.1:9222 --out <RUN_DIR>/logs/auth-state.json
node <SKILL_DIR>/scripts/node/device_context.js run --devices pixel7,iphone15 --url https://example.com/ --state <RUN_DIR>/logs/auth-state.json --rules <RUN_DIR>/rules.json --out <RUN_DIR>/raw/devices.json
# снимок с разметкой в одном вызове (screenshots.md)
node <SKILL_DIR>/scripts/node/shot.js --cdp http://127.0.0.1:9222 --page-match example.com --out <RUN_DIR>/screenshots/F-001-bell.png "#bell|Кнопка закрывает легенду|error" ".legend|@avoid"
# скриншоты в чужой/приватный репозиторий через веб-форму (web-upload.md): без --confirm-publish — только план
node <SKILL_DIR>/scripts/node/publish_web.mjs --repo owner/repo --title "<заголовок>" --body-file <RUN_DIR>/drafts/owner__repo/01.md --shot <RUN_DIR>/screenshots/F-001-annotated.png --cdp http://127.0.0.1:9222
node <SKILL_DIR>/scripts/node/comment_web.mjs --repo owner/repo --number 42 --body-file <RUN_DIR>/drafts/owner__repo/42-comment.md --shot <RUN_DIR>/screenshots/F-007-annotated.png --cdp http://127.0.0.1:9222
```

## Базовые запреты (всегда)
Не покупать, не платить, не подписываться, не донатить; не подтверждать OAuth/вход через внешние аккаунты; не удалять данные и аккаунты, не менять настройки боевого аккаунта; не отправлять формы реальным людям без разрешения на каждую; не принимать соглашения и не обходить капчу; никакой нагрузки, перебора, сканеров и инъекций; паузы между действиями; маскирование секретов и персональных данных. Подробно — `references/safety-rules.md`; проверка — `scripts/url_guard.py`.

## Статусы сверки с issues
`NEW`, `DUPLICATE-OPEN`, `FIXED-OK`, `FIXED-INSUFFICIENT`, `REGRESSION`, `ALREADY-COPIED`, `UNSURE-MATCH` (спросит); для перепроверки — `NOT-CHECKED` с причиной (нужен выход из аккаунта, другой тип аккаунта, запрет…). В каждом созданном issue — скрытый маркер `<!-- site-qa-audit:fp=… -->` (или нейтральный `<!-- qa-fp:… -->`, или без маркера при `disclosure: none`), поэтому повторный прогон не создаёт дублей.

## Зависимости
| Обязательно | Как поставить |
|-------------|---------------|
| git, Node.js ≥ 18, npm/npx, Python 3 | системно |
| Playwright MCP | `/plugin install playwright@claude-plugins-official` |
| playwright, @axe-core/playwright, lighthouse | `cd scripts/node && npm install` (локально) |
| Браузеры Playwright | `cd scripts/node && npx playwright install chromium webkit firefox` |
| gh CLI (для репозиториев) | https://cli.github.com, `gh auth login` |

| Желательно | Зачем |
|------------|-------|
| `@playwright/cli` (`npm i -g @playwright/cli@latest`) | параллельные изолированные браузерные потоки |
| Claude in Chrome | режим «текущий экран» во вкладке пользователя |
| Скилы/плагины: ux-audit (jezweb/claude-skills), e2e-test и ux-test (coderphonui/opentest), qa-skills (neonwatty), ux-heuristics, laws-of-ux, ux-design-principles, ui-audit-redesign (alpham8/agentic-webdev), frontend-design (Anthropic) | усиливают направления, см. `references/plugins-map.md` |

`scripts/check_env.sh` (`.ps1`) проверяет всё это при каждом запуске и показывает таблицу.

## Ограничения
- Только то, что видно через браузер: причина дефекта — гипотеза, код не анализируется.
- Playwright MCP нельзя делить между параллельными субагентами; параллельный браузер — только через `playwright-cli`, не больше 4 потоков (на опыте проверено 2).
- `--allowed-origins`/`--blocked-origins` Playwright MCP — не граница безопасности; основная защита — проверка `url_guard` перед каждым действием. Она не заменяет здравый смысл исполнителя.
- Капча, 2FA, вход через внешние аккаунты — только ручной вход пользователя.
- gh не прикладывает картинки к issue: скриншоты коммитятся в свой репозиторий (`commit`), загружаются через веб-форму GitHub в браузере пользователя (`web-upload`, нужен вход пользователя и Chrome с CDP-портом; интерфейс GitHub может измениться — тогда скрипт останавливается) или остаются локально.
- `guard.js` применяет правила проверяемого сайта; к браузеру GitHub при `web-upload` он не применяется — там защита: замок хоста, только кнопка «Comment», никогда Close/Reopen, явное `--confirm-publish`.
- `manual-cdp`: работа идёт в браузере пользователя — параллельные потоки запрещены, cookies не очищаются, файл `logs/auth-state.json` — секрет и удаляется в конце.
- Детекторы перекрытий и достижимости находят кандидатов; итоговую находку подтверждает исполнитель по скриншоту. В мобильном WebKit жесты недоступны — достижимость проверяется эмуляцией того же устройства в Chromium.
- Новые возможности 1.1.0 проверены на локальных фикстурах (`tests/`), не на реальных сайтах и не на github.com.
- Firefox может не запускаться в некоторых окружениях (см. `references/environment-notes.md`) — тогда помечается «не проверено».
- Безопасность — только пассивная; это не пентест.

## Структура
```text
SKILL.md                порядок работы
INSTALL.md              установка и обновление (macOS, Windows), промпты для Claude Code
references/             setup, intake, safety-rules, depth-matrix, parallelism, plugins-map, repo-sync,
                        severity, environment-notes, screenshots, claims, run-files, browser-guard,
                        side-effects, layout-detectors, devices-auth, web-upload, checklists/ (11 направлений)
templates/              run-config.example.yaml, finding.schema.json, issue-detailed.md,
                        issue-comment.md, user-story.md, run-report.md, site-context.md
scripts/                check_env, url_guard, intake, journal, fetch_issues, read_templates, claims,
                        fingerprint, render_draft, validate_findings, build_report, gitignore_helper, nav_lock, snap_mcp,
                        snap_cdp, node/ (a11y, lighthouse, headers, links, probe, annotate, shot, guard,
                        invariants, occlusion, reachability, device_context, frames, publish_web,
                        comment_web), shared/ (вендоренные модули)
tests/                  unit.sh (офлайн + наборы test_stream_a, test_v12, test_stream_b/c), фикстуры, сценарий dry-run
```
