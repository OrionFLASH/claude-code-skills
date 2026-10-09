# site-qa-audit

Полный QA-аудит любого сайта или локального веб-приложения (`file://`, без сервера) через браузер — без макета и исходного кода. Скил проходит сайт как пользователь и как инструменты (axe, Lighthouse, анализ заголовков и ссылок, детекторы перекрытий и достижимости), сверяет находки с issues в указанных GitHub-репозиториях, перепроверяет заявленные исправления и публикует результаты по заданным правилам — или складывает черновики (dry-run).

Внутри скила нет конкретных сайтов, репозиториев, логинов и токенов: всё передаётся на входе.

**Установка и обновление** (macOS, Windows, промпты для Claude Code) — [INSTALL.md](INSTALL.md).

**Запуск.** Командой `/site-qa-audit` или обычной просьбой протестировать, проверить, найти баги на сайте, в веб-приложении, интерфейсе (вёрстка, адаптивность, доступность, скорость, SEO), в том числе с URL. Если скил подхвачен по смыслу запроса, он сначала спрашивает: «Похоже, вы хотите протестировать <что понял>. Запустить QA-аудит?» — при «Нет, это другое» ничего не создаёт. На разработку сайта и написание кода тестов не срабатывает. **Автопилот** — `/site-qa-audit` с подробной задачей и словом «автопилот» / «без вопросов»: без опроса и «старт», решения по умолчанию записываются в журнал, запреты и dry-run не ослабляются.

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
| `legal-ui` (по запросу) | что сайт сохраняет у гостя до согласия, сторонние сервисы, cookie-баннер и его кнопки, согласия при входе, документы, сведения об операторе, возрастная маркировка — **только факты**; нормы права — со второй проверкой и пометкой «проверить юристом» |

**Главные гарантии.** Защита не открывается при сбое (код 4 «guard недоступен» = стоп), скил на весь прогон — копия в папке прогона (`<RUN_DIR>/skill`: обновление плагина посреди прогона не ломает исполнителей), состояние входа — только cookie проверяемого сайта, телефон — с настоящей эмуляцией касаний (`pointer: coarse`), каждая находка перепроверяется независимо до публикации (`repro` + `recheck.py`), исполнители возвращают находки текстом (блок `qa-findings`, массив с `dup_check`) и не плодят вкладки.

**Что нового в 1.5.0.** Node-скрипты сами пишут свои вкладки в реестр прогона `tabs.json` (свой браузер — по `pid`, вкладка в браузере пользователя по CDP — по target id) и при завершении закрывают только свои; `tabs.py cleanup` убирает вкладки упавшего скрипта. Достижимость на телефоне решает жест касания (а не колесо), мобильный WebKit проверяется ещё и в настоящем WebKit моделью касания (`touch-action`, `overscroll-behavior`). Заготовки e2e запускаются настоящим Playwright Test скила под guard прогона (`node/e2e_run.js --expect fail|pass`, без установки `@playwright/test`), видимое окно проверено вживую. Отдельный Playwright MCP для `file://` с guard в каждой вкладке (`browser_mode.py mcp --check`). `publish_shots.py` заранее проверяет gh, вход, доступ и право push и даёт запасной путь `local` (скриншоты при отчёте, `results/`); вход в GitHub скил не автоматизирует.

**Что нового в 1.4.0.** Локальные приложения: `file://` и каталоги на диске (`site.local_roots`; `..`, симлинки и соседние папки — запрет), все детекторы принимают `--url file:///…`, копия приложения в прогоне (`local_app.py`). Окно браузера — одна настройка на прогон (`browser.headed`, `browser_mode.py set` посреди прогона). Задание исполнителю целиком одной командой (`brief.py`: правила, срез реестра issues, формат результата, лимит времени), одно место правды для результатов потоков (`findings/<поток>.json`, `coverage/<поток>.md`), метрики потоков автоматически и вторая волна по «не проверено» (`thread_coverage.py again`). Варианты данных и стенды в охвате, автопилот. Один issue на первопричину (`render_draft.py group --map`), блок «Как проверить», заготовка регрессионного теста (`e2e_stub.py`), скриншоты в приватный репозиторий без браузера (`publish_shots.py`), независимое ревью диффа после доработок (`references/fix-cycle.md`).

## Входные параметры (опрос)
Если параметр не передан в запросе, скил спросит его с вариантами ответа (подробно — `references/intake.md`).

| # | Параметр | По умолчанию |
|---|----------|--------------|
| 1 | Стартовые URL (`https://…`, `file:///…` или путь к HTML-файлу на диске) | — (обязательно) |
| 1a | Что тестируем (сценарии, раздел, форма, адаптив, доступность, скорость, SEO) и что считать успехом (`goal`) | основные сценарии; список проблем с приоритетами |
| 2 | Разрешённые домены для навигации; куда не переходить (разделы, URL, поддомены) | домен сайта и поддомены; сторонние ресурсы (CDN, тайлы, API, шрифты) грузятся, переходы на чужие страницы — нет |
| 3 | Авторизация: нет / тестовый аккаунт (env) / ручной вход / `manual-cdp` (пользователь уже вошёл в своём Chrome, подключение по CDP без очистки cookies) | нет |
| 2a | Варианты данных и стенды (тестовый / предпромышленный / боевой стенд, наборы данных, роли) — каждый входит в охват (`variants`) | один |
| 3a | Платные уровни и состояния аккаунта (гость / без Pro / с Pro), можно ли переключать — **заранее**; план проходится в каждом состоянии (`auth.paid_tiers`, `auth.account_states`) | только текущее |
| 4 | Охват: весь сайт / раздел / список URL / текущий экран | весь сайт |
| 5 | Направления | все |
| 6 | Глубина: smoke / standard / deep | standard (лимит страниц 50) |
| 7 | Устройства и браузеры; окно браузера видно или в фоне (`browser.headed`, можно поменять посреди прогона) | по глубине (`references/depth-matrix.md`); окно видно |
| 8 | Репозитории: URL, роли (`check`, `write-new`, `copies`, `comment`), стиль, метки, подтверждение, скриншоты (`commit` / `web-upload` / `none`), раскрытие (`disclosure`, `marker`), ссылки между репозиториями (`cross_links`), недоработка в закрытом issue (`closed_claims`), шкала серьёзности (`severity_map`) | нет |
| 9 | Запреты пользователя (свободный текст + чек-лист: покупки, оплата, регистрация, отправка форм, удаление, настройки аккаунта, рассылки, внешние ссылки…) | только базовые |
| 10 | Плагины: все установленные / выбрать / только свои чек-листы | все установленные |
| 11 | Язык отчётов и issues | русский |
| 12 | Параллельные потоки: независимые направления, группы страниц, гипотезы (`parallel.max_workers`, 1–4) | 2 (через playwright-cli; общая сессия входа — 1) |
| 13 | Режим: dry-run / боевой; в боевом — черновики и сводная таблица (`publish_mode: batch`) или прямая публикация по одной находке (`direct`: воспроизвести дважды → дубли → issue → скриншоты) | dry-run, batch |
| 14 | Побочные эффекты (публичный рейтинг, рассылка, необратимая загрузка) и защита от них (`side_effects`, `invariants`) | нет |
| 15 | Папка результатов | путь из запроса / `SITE_QA_OUTPUT_DIR` / `<cwd>/qa-runs/` |
| 16 | Откуда узнать о сайте (сам сайт, документация, GitHub, файл, описание) и что важно изучить (`context`) | сам сайт; сохранённая память о сайте — по выбору |
| 17 | Куда записать итоги, кроме локальной папки: другая папка, GitHub issues, страница-артефакт Claude (`report_destinations`) | только локальная папка |

Свободный запрос можно сразу разобрать в черновик конфига: `scripts/intake.py from-text` (черновик показывается на подтверждение).

Результаты — в `<OUTPUT_ROOT>/qa-runs/<YYYY-MM-DD>-<host>/` (`<OUTPUT_ROOT>` — путь из запроса, иначе переменная `SITE_QA_OUTPUT_DIR`, иначе папка запуска Claude Code; в репозиторий скилов не пишется): `run-config.yaml`, `findings.json`, `run.json`, `report.md`, `summary.md`, `journal.md`, `claims-plan.md`, `rechecks.json`, `side_effects.md`, `skill/` (копия скила), `app/` (копия локального приложения), `briefs/`, `findings/` и `coverage/` (результаты и охват потоков), `waves/` (вторая волна), `screenshots/`, `drafts/`, `raw/`, `logs/`. Память о сайте (назначение, роли, сценарии, термины, источники) — `<OUTPUT_ROOT>/qa-runs/.site-context/<host>/context.md`: при следующем прогоне скил показывает её и спрашивает «как есть / обновить / изучить заново». Если `qa-runs/` оказалась внутри git-репозитория, скил сразу, до первой записи, добавляет её в `.gitignore` этого репозитория — без вопроса, если вы в запросе явно не разрешили класть результаты в репозиторий («коммить результаты», `git.allow_commit_results`); уже закоммиченные результаты не удаляет, а спрашивает про `git rm -r --cached`. «Другая папка» для итогов (`report_destinations: folder`) получает только `summary.md`, `report.md`, `findings.json` и скриншоты находок.

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
Проверь юридически значимые элементы https://example.com для гостя: cookie-баннер, согласия, документы,
на русском, английском и немецком. Страницы входа и оплаты — только прочитать.
Протестируй https://app.example.com без Pro и с Pro и заводи находки сразу в репозиторий owner/feedback.
!qa deep autopilot https://example.com — проверить вёрстку и доступность, без публикации.
!site-qa:smoke https://example.com
Запусти скилл site-qa-audit на https://example.com — только functional и SEO.
/site-qa-audit автопилот: проверь офлайн-редактор file:///abs/path/app/index.html на копии, 4 потока,
с открытым окном; стенды — тестовые и боевые данные; не нажимай «Удалить».
```

Принудительный запуск без вопроса «Запустить QA-аудит?» (с 1.6.0, хук плагина): метка `!qa …` / `qa: …` / `!site-qa …` или фраза «запусти скилл site-qa-audit»; в метке допустимы `autopilot` и глубина `smoke|standard|deep`. Без названия (`!qa`) скил выбирается по содержимому (URL, сайт → site-qa-audit; APK, эмулятор → android-qa-audit). Публикацию в GitHub метка не включает.

## Команды (основные)
Все пути — абсолютные; `<SKILL_DIR>` — папка скила, `<RUN_DIR>` — папка прогона. Подробности — в указанных `references/`.
```bash
# путь установленного скила и его копия в прогоне — SKILL_DIR для run-config и заданий (setup.md, run-files.md)
python3 <SKILL_DIR>/scripts/skill_dir.py                       # --json — все варианты, --check PATH — проверка
python3 <SKILL_DIR>/scripts/skill_snapshot.py <RUN_DIR> --update-config
# локальное приложение: копия в прогоне и детекторы по file:// (local-files.md)
python3 <SKILL_DIR>/scripts/local_app.py copy /abs/path/to/app <RUN_DIR> --update-config
node <SKILL_DIR>/scripts/node/occlusion.js --url file:///abs/path/app/index.html --frames all --rules <RUN_DIR>/rules.json
# окно браузера на весь прогон (devices-auth.md)
python3 <SKILL_DIR>/scripts/browser_mode.py set <RUN_DIR> --headed --slowmo 400
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
# qa-runs/ и git — до создания <RUN_DIR>: qa-runs/ в .gitignore, если нет явного разрешения коммитить (run-files.md)
python3 <SKILL_DIR>/scripts/gitignore_helper.py ensure <OUTPUT_ROOT>                 # 1 — файлы уже в индексе: спросить про untrack
python3 <SKILL_DIR>/scripts/gitignore_helper.py untrack <OUTPUT_ROOT> --yes          # только после «да» пользователя
# report_destinations: folder — только итоговые файлы и скриншоты находок
python3 <SKILL_DIR>/scripts/export_results.py <RUN_DIR> --to /abs/path/reports
# проверка элемента правилами безопасности (browser-guard.md): код 0 allow, 2 confirm, 3 deny, 4 guard недоступен (стоп)
node <SKILL_DIR>/scripts/node/guard.js check --url https://example.com/ --selector "text=Поддержать" --rules <RUN_DIR>/rules.json
# действие с побочным эффектом под инвариантом (side-effects.md)
node <SKILL_DIR>/scripts/node/invariants.js preflight --config <RUN_DIR>/run-config.yaml --url https://example.com/upload --run-dir <RUN_DIR>
node <SKILL_DIR>/scripts/node/invariants.js exec --config <RUN_DIR>/run-config.yaml --effect SE1 --url https://example.com/upload --file test.sav --run-dir <RUN_DIR> --rules <RUN_DIR>/rules.json
# перекрытия и достижимость (layout-detectors.md)
node <SKILL_DIR>/scripts/node/occlusion.js https://example.com/ --sizes 1440x900,1024x768,720x450 --device pixel7,iphone15 --frames all --rules <RUN_DIR>/rules.json --out <RUN_DIR>/raw/occlusion.json
node <SKILL_DIR>/scripts/node/reachability.js https://example.com/ --sizes 720x450 --device pixel7-landscape --out <RUN_DIR>/raw/reachability.json
# устройства со входом пользователя (devices-auth.md)
node <SKILL_DIR>/scripts/node/device_context.js state --cdp http://127.0.0.1:9222 --rules <RUN_DIR>/rules.json --out <RUN_DIR>/logs/auth-state.json
node <SKILL_DIR>/scripts/node/device_context.js run --devices pixel7,iphone15 --url https://example.com/ --state <RUN_DIR>/logs/auth-state.json --rules <RUN_DIR>/rules.json --out <RUN_DIR>/raw/devices.json
# снимок с разметкой в одном вызове (screenshots.md)
node <SKILL_DIR>/scripts/node/shot.js --cdp http://127.0.0.1:9222 --page-match example.com --out <RUN_DIR>/screenshots/F-001-bell.png "#bell|Кнопка закрывает легенду|error" ".legend|@avoid"
# скриншоты в чужой/приватный репозиторий через веб-форму (web-upload.md): без --confirm-publish — только план
node <SKILL_DIR>/scripts/node/publish_web.mjs --repo owner/repo --title "<заголовок>" --body-file <RUN_DIR>/drafts/owner__repo/01.md --shot <RUN_DIR>/screenshots/F-001-annotated.png --cdp http://127.0.0.1:9222
node <SKILL_DIR>/scripts/node/comment_web.mjs --repo owner/repo --number 42 --body-file <RUN_DIR>/drafts/owner__repo/42-comment.md --shot <RUN_DIR>/screenshots/F-007-annotated.png --cdp http://127.0.0.1:9222
node <SKILL_DIR>/scripts/node/publish_web.mjs --attach-to 12 --repo owner/repo --shots-dir <RUN_DIR>/screenshots   # в существующий issue
# задание исполнителю, его результат, охват и вторая волна (parallelism.md)
python3 <SKILL_DIR>/scripts/brief.py <RUN_DIR> --thread qa-ux --directions ux,product --minutes 25
python3 <SKILL_DIR>/scripts/ingest_findings.py <RUN_DIR> --from <RUN_DIR>/raw/qa-ux-message.md --thread qa-ux
python3 <SKILL_DIR>/scripts/validate_findings.py --array <RUN_DIR>/findings/qa-ux.json --run <RUN_DIR>/run.json
python3 <SKILL_DIR>/scripts/thread_coverage.py summary <RUN_DIR>
python3 <SKILL_DIR>/scripts/thread_coverage.py again <RUN_DIR> --minutes 25
# независимая перепроверка и допуск к публикации; правовые нормы — вторая проверка (parallelism.md, legal-ui.md)
python3 <SKILL_DIR>/scripts/recheck.py run <RUN_DIR>
python3 <SKILL_DIR>/scripts/recheck.py set <RUN_DIR> --id F-004 --status confirmed --by "qa-verify: Chrome 1440×900, шаги 1–3"
python3 <SKILL_DIR>/scripts/recheck.py legal <RUN_DIR> --id F-007 --by "второй исполнитель qa-legal" --result confirmed
python3 <SKILL_DIR>/scripts/recheck.py gate <RUN_DIR>
# один issue на первопричину; мелкие находки по теме; заготовка теста; скриншоты без браузера (repo-sync.md)
python3 <SKILL_DIR>/scripts/render_draft.py suggest-groups <RUN_DIR>/findings.json --out <RUN_DIR>/groups.yaml
python3 <SKILL_DIR>/scripts/render_draft.py group <RUN_DIR>/findings.json --map <RUN_DIR>/groups.yaml --run-dir <RUN_DIR>
python3 <SKILL_DIR>/scripts/render_draft.py group <RUN_DIR>/findings.json --ids F-003,F-007,F-009 --out <RUN_DIR>/drafts/owner__repo/group.md
python3 <SKILL_DIR>/scripts/e2e_stub.py <RUN_DIR>/findings.json --id F-001 --out <RUN_DIR>/drafts/e2e/F-001.spec.ts
python3 <SKILL_DIR>/scripts/publish_shots.py plan <RUN_DIR> --repo owner/repo     # push … --confirm-push — после «да»
python3 <SKILL_DIR>/scripts/publish_shots.py local <RUN_DIR>                      # нельзя в репозиторий — скриншоты при отчёте (results/)
# заготовка e2e под Playwright Test скила с guard: до правки падает на дефекте, после — проходит три раза (fix-cycle.md)
node <SKILL_DIR>/scripts/node/e2e_run.js <RUN_DIR>/drafts/e2e/F-001.spec.ts --rules <RUN_DIR>/rules.json --app-url file:///…/app/ --expect fail
# локальное приложение через отдельный Playwright MCP с guard в каждой вкладке (local-files.md); добавляет сервер пользователь
python3 <SKILL_DIR>/scripts/browser_mode.py mcp <RUN_DIR> --check
python3 <SKILL_DIR>/scripts/direct_publish.py check <RUN_DIR> --id F-001 --repo owner/repo
python3 <SKILL_DIR>/scripts/direct_publish.py record <RUN_DIR> --id F-001 --repo owner/repo --number 12 --url https://github.com/owner/repo/issues/12
# вкладки прогона: одна на профиль устройства, уборка только своих (parallelism.md); node-скрипты пишут в реестр сами
python3 <SKILL_DIR>/scripts/tabs.py open <RUN_DIR> --owner qa-ux --profile pixel7 --tool cli
node <SKILL_DIR>/scripts/node/occlusion.js --url https://example.com/ --rules <RUN_DIR>/rules.json --owner qa-ux   # вкладка -> tabs.json
python3 <SKILL_DIR>/scripts/tabs.py cleanup <RUN_DIR> --owner qa-ux
# страница покупки/входа только для чтения (safety-rules.md §3.13)
python3 <SKILL_DIR>/scripts/url_guard.py nav https://example.com/donate --config <RUN_DIR>/run-config.yaml --read-only --log <RUN_DIR>/logs/read-only.jsonl
# цели нажатия, юридически значимые элементы, RTL (layout-detectors.md, legal-ui.md, content-i18n.md)
node <SKILL_DIR>/scripts/node/targets.js https://example.com/ --device pixel7 --rules <RUN_DIR>/rules.json --out <RUN_DIR>/raw/targets.json
node <SKILL_DIR>/scripts/node/legal_guest.js https://example.com/ --rules <RUN_DIR>/rules.json --locales ru-RU,en-US,de-DE --out <RUN_DIR>/raw/legal-guest.json
node <SKILL_DIR>/scripts/node/rtl.js https://example.com/ --locales ar-SA --rules <RUN_DIR>/rules.json --out <RUN_DIR>/raw/rtl.json
# проверка эмуляции касаний и удаление файла состояния входа (devices-auth.md)
node <SKILL_DIR>/scripts/node/device_context.js media --devices pixel7,412x915@mobile
node <SKILL_DIR>/scripts/node/device_context.js state-rm --out <RUN_DIR>/logs/auth-state.json
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
- gh не прикладывает картинки к issue: скриншоты загружаются в репозиторий с правом push через API в отдельную ветку (`publish_shots.py`, без браузера; в публичном репозитории они станут публичными), через веб-форму GitHub в браузере пользователя (`web-upload`, нужен вход пользователя и Chrome с CDP-портом; интерфейс GitHub может измениться — тогда скрипт останавливается) или остаются при отчёте (`publish_shots.py local`: `results/screenshots/` и архив, контактный лист в сводке). `plan` заранее проверяет gh, вход, доступ и право push. **Вход в GitHub (gh или браузер, 2FA, SSO) скил не автоматизирует** — его выполняет только пользователь.
- `file://`: Playwright MCP и playwright-cli по умолчанию блокируют локальные файлы — скил даёт playwright-cli разрешение файлом `<RUN_DIR>/playwright-cli.json` (граница — `url_guard.py` перед каждым переходом), MCP-поток для локального приложения заменяется node-скриптами или отдельным MCP прогона с guard в каждой вкладке (`browser_mode.py mcp`, добавляет пользователь); `headers.js` и `lighthouse.js` для `file://` не применимы.
- Метрики потоков считаются по журналу проверок guard (`--trace`): действия, сделанные без проверки guard, в них не попадут.
- `guard.js` применяет правила проверяемого сайта; к браузеру GitHub при `web-upload` он не применяется — там защита: замок хоста, только кнопка «Comment», никогда Close/Reopen, явное `--confirm-publish`.
- `manual-cdp`: работа идёт в браузере пользователя — параллельные потоки запрещены, cookies не очищаются, файл `logs/auth-state.json` — секрет и удаляется в конце.
- Детекторы перекрытий и достижимости находят кандидатов; итоговую находку подтверждает исполнитель по скриншоту. В мобильном WebKit Playwright не даёт ни колеса, ни жеста — достижимость проверяется эмуляцией того же устройства в Chromium и моделью касания в настоящем WebKit (это модель прокрутки и стилей, не сенсорный ввод Safari).
- Новые возможности 1.1.0–1.5.0 проверены на локальных фикстурах (`tests/`, в том числе приложение на `file://`, браузер-заглушка «пользователя» по CDP, Playwright MCP по stdio), не на реальных сайтах и не на github.com (`publish_shots.py` — на поддельном gh).
- `legal-ui` фиксирует факты, а не даёт юридическое заключение: нормы права — «возможно применимо», вторая проверка другим исполнителем и юристом обязательна.
- `recheck.py` запускает только скрипты скила; многошаговые сценарии перепроверяет отдельный исполнитель (`recheck.py set`).
- `rtl.js` и `legal_guest.js` дают кандидатов и факты для ручной проверки по скриншоту.
- Firefox может не запускаться в некоторых окружениях (см. `references/environment-notes.md`) — тогда помечается «не проверено».
- Безопасность — только пассивная; это не пентест.

## Структура
```text
SKILL.md                порядок работы
INSTALL.md              установка и обновление (macOS, Windows), промпты для Claude Code
references/             setup, intake, safety-rules, depth-matrix, parallelism, plugins-map, repo-sync,
                        severity, environment-notes, screenshots, claims, run-files, browser-guard,
                        side-effects, layout-detectors, devices-auth, web-upload, local-files, fix-cycle,
                        checklists/ (12 направлений)
templates/              run-config.example.yaml, finding.schema.json, issue-detailed.md,
                        issue-comment.md, user-story.md, run-report.md, site-context.md
scripts/                check_env, skill_dir, skill_snapshot, local_app, browser_mode, url_guard, intake, journal,
                        fetch_issues, read_templates, claims, fingerprint, render_draft, e2e_stub, publish_shots,
                        validate_findings, build_report, gitignore_helper, export_results, brief, coverage,
                        ingest_findings, recheck, direct_publish, tabs, runcfg, nav_lock, snap_mcp,
                        snap_cdp, node/ (a11y, lighthouse, headers, links, probe, annotate, shot, guard,
                        invariants, occlusion, reachability, targets, legal_guest, rtl, repro, device_context,
                        frames, publish_web, comment_web, e2e_run + e2e/ (конфиг и обёртка Playwright Test),
                        mcp_guard, mcp_check), shared/ (вендоренные модули)
tests/                  unit.sh (офлайн + наборы test_stream_a, test_v12, test_v121, test_v130, test_v140,
                        test_v150, test_stream_b/c, test_v130_browser, test_v140_browser — file://, test_v150_browser),
                        фикстуры, сценарий dry-run
```
