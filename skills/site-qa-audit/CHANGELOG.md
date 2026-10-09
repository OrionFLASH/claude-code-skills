# Журнал изменений site-qa-audit

Формат — [Keep a Changelog](https://keepachangelog.com/ru/1.1.0/), версии — SemVer, теги `site-qa-audit/vX.Y.Z`.

## [1.6.0] — 2026-10-09
Принудительный запуск из запроса (по аналогии с typesafe-triage 2.4.2). Старые вызовы работают как раньше; без метки и фразы хук молчит.

### Добавлено
- **Хук `UserPromptSubmit` плагина** (`hooks/hooks.json` → `scripts/shared/qa_force.py`, общий модуль `shared/scripts/qa_force.py`; без сети, stdlib, не блокирует запрос, код 0, при ошибке молчит). Распознаёт явный вызов и добавляет в контекст строку «ЯВНЫЙ ВЫЗОВ (qa-force)»: вызвать скил первым действием, вопрос о намерении («Запустить …?») не задавать.
- **Метки в начале запроса:** `!qa …`, `qa: …`, `!site-qa …`, `!site-qa-audit …`. Без названия (`!qa`) скил выбирается по содержимому: URL, сайт → site-qa-audit; APK, эмулятор, пакет `com.…` → android-qa-audit; неясно — один вопрос пользователю (от обоих хуков одна и та же строка). Метка `qa:` без URL и APK («qa: deep dive …») — обычный текст.
- **Опции метки:** `autopilot` / `auto` / `автопилот` (режим «Автопилот» из `SKILL.md`) и глубина `smoke` / `standard` / `deep` (в run-config, не переспрашивается): `!qa deep autopilot https://…`, `!site-qa:smoke …`, `qa:deep …` (для `qa:` — вплотную к двоеточию). Публикация в GitHub метками **не включается**.
- **Фраза в тексте:** «запусти/используй/вызови скилл site-qa-audit», «через site-qa-audit», "use the site-qa-audit skill" — вне кавычек, `кода` и блоков кода; название как объект задачи («почини баг в site-qa-audit») вызовом не считается.
- `SKILL.md`: пункт «Принудительный запуск» в разделе «Запуск: подтверждение намерения»; `README.md`, `INSTALL.md` — примеры и проверка хука.

### Тесты
- `shared/tests/qa_force_check.py` (26 проверок: метки и опции, выбор скила, фразы и ложные срабатывания, хук как процесс) — в `tests/unit.sh`; `claude plugin validate` — «Validation passed». Хук в настоящей сессии Claude Code не запускался (нужен перезапуск после обновления плагина).

## [1.5.0] — 2026-10-09
Открытые issues №9, №26 (остаток), №34. Новые флаги и команды необязательные, старые вызовы работают как раньше. Изменения поведения намеренные: на сенсорных конфигурациях достижимость решает жест, а не колесо; `publish_shots.py plan` без доступа к репозиторию отвечает режимом `local` (код 0), а не ошибкой gh (код 3); `reachability.js` для мобильного WebKit по умолчанию делает два прогона (эмуляция в Chromium + WebKit).

### Добавлено
- **Реестр вкладок в node-скриптах (№9).** `lib.js` → `tabs()` / `trackPage()` / `closeTab()`: каждая страница, которую открывает скрипт, — запись в `<RUN_DIR>/tabs.json` в формате `tabs.py` и под тем же lock-файлом. Папка прогона — `--run-dir`, `SITE_QA_RUN_DIR` или папка `--rules` (рядом `run-config.yaml`); владелец — `--owner <qa-id>` / `SITE_QA_OWNER`; выключить — `--no-tabs` / `SITE_QA_TABS=0`. Свой браузер скрипта — инструмент `node` (`pid`, `script`, первый и последний адрес), закрывается вместе с ним, при выходе скрипт закрывает в реестре только свои записи; страница, созданная в браузере пользователя по CDP, — `cdp` с target id (скрипт закрывает её сам, после сбоя — `tabs.py cleanup --cdp --yes`, только её). Охвачены все детекторы через `openDevice`/`attachCdp`, а также `a11y.js`, `legal_guest.js` (в том числе `--cdp`), `lighthouse.js`, `guard.js check`, `e2e_run.js`. `tabs.py`: инструмент `node`, проверка процесса по `pid` (без сигналов на Windows), `cleanup` — завершённый скрипт «уже закрыта», работающий не трогается; записи `node` не срабатывают на правило «одна вкладка на профиль». Задание исполнителю (`brief.py`): node-скрипты — с `--rules <RUN_DIR>/rules.json --owner <поток>`.
- **WebKit: колесо и жесты (№34).** `reachability.js`: мобильный WebKit без `--browser` — `--webkit both` (по умолчанию: эмуляция в Chromium и настоящий WebKit), `chromium`, `webkit`. В WebKit, где Playwright не даёт ни колеса, ни жеста, — модель касания в странице: палец двигает пользовательский прокручиваемый контейнер под собой (цепочка прокрутки, `overscroll-behavior`), `touch-action` на пути блокирует; поля `gestureMethod` (`cdp` / `touch-model`), `gestureBlocked`. Фикстура `reach-touch-action.html`.
- **Заготовки e2e под Playwright Test (№34).** `node/e2e_run.js`: заготовки `e2e_stub.py` (`.spec.ts`, `.spec.js`) запускаются Playwright Test из пакета `playwright` скила — `@playwright/test` ставить не нужно; импорт `@playwright/test` направляется (`NODE_PATH`) на обёртку `scripts/node/e2e/shim`, которая добавляет guard прогона к каждому контексту теста; адреса заготовки проверяются до запуска (код 3), без `--rules` — код 4. `--expect fail` (до правки: падение на проверке дефекта, а не на переходе или таймауте) / `--expect pass` (после: все повторы, `--repeat-each` 3 по умолчанию); `test.fixme` проходом не считается. Окно — как у всех скриптов (`--headed`, `--slowmo`, run-config, env); видимое окно проверено вживую на macOS.
- **Playwright MCP и `file://` (№34).** `browser_mode.py mcp <RUN_DIR> [--check]`: конфиг отдельного MCP-сервера прогона `playwright-mcp.json` (Chromium скила, профиль в памяти, окно прогона, `allowUnrestrictedFileAccess` только при `local_roots`, `browser.initPage` = `mcp-guard.js` → `node/mcp_guard.js`: guard прогона в каждой вкладке, fail closed без `rules.json`), команды `claude mcp add …` / `.mcp.json` для пользователя (настройки Claude Code скил не меняет). `--check` (`node/mcp_check.js`) запускает тот же сервер по stdio: стартовый адрес открывается, файл вне каталога блокируется с записью guard.
- **Скриншоты: проверки заранее и запасной путь (№26).** `publish_shots.py plan` без записи проверяет `gh`, вход (`gh auth status`, scope `repo` у классического токена), видимость репозитория и `push`; вывод — `checks[]`, `mode` (`api-commit` / `web-upload` / `local`), причина и `fallback`. `push`: отказ записи по дороге (403 — токен без Contents: write, SSO, правила веток) — понятная причина, загруженное сохраняется в `shots-published.json`, запасной путь (код 3); `--fallback-local`. Новая команда `local`: скриншоты находок (без `evidence.sensitive`) в `<RUN_DIR>/results/screenshots/` с `index.md` и архивом `results/screenshots.zip`, строка для issue; `build_report.py` ссылается на них в «Скриншоты находок». Вход в GitHub (gh, браузер, 2FA, SSO) скил не автоматизирует — описано в `repo-sync.md` и `web-upload.md`.

### Исправлено
- `reachability.js`: на телефоне (касания) вердикт брался по колесу мыши — контейнер с `touch-action: none` считался достижимым, хотя пальцем его не прокрутить. Теперь на сенсорных конфигурациях жест выполняется всегда и решает он; десктоп — как раньше.
- `publish_shots.py`: при отсутствии `gh` скрипт падал с трассировкой (`FileNotFoundError`), при ошибке записи на середине терял сведения об уже загруженных файлах.

### Тесты
- `tests/test_v150.sh` (офлайн, Python 3.9 и 3.14): `tabs.py` с инструментом `node` (живой и завершённый процесс, `cleanup`, правило одной вкладки), `lib.js` (`tabsConfig`, `--no-tabs`, формат записей, SIGKILL, чужие записи, общий lock с `tabs.py` — 3 node-процесса и 2 цикла Python параллельно), `brief.py`, логика `e2e_run.js` (адреса, вердикты, коды 2/4), `publish_shots.py` на поддельном gh (нет gh, нет входа, нет scope, 403 на втором файле, `local`, `--fallback-local`, ссылка в отчёте), `browser_mode.py mcp`, `mcp_guard.js` без правил.
- `tests/test_v150_browser.sh` + `v150.test.js`: реестр вкладок у occlusion/a11y/shot/device_context/repro/targets/legal_guest/lighthouse, сбой (`process.exit`, SIGKILL), браузер-заглушка «пользователя» по CDP (закрывается только вкладка скрипта), достижимость в WebKit и `touch-action`, `e2e_run.js` (до/после исправления, три повтора, `fixme`, guard внутри теста, коды 3/4, `--base-url` на локальном http), Playwright MCP по stdio с guard и без него; видимое окно — `QA_HEADED=1`.
- `doc_node_flags.py` учитывает флаги реестра вкладок `lib.js` (`--owner`, `--run-dir`, `--no-tabs`).

## [1.4.0] — 2026-10-09
По отзыву реального прогона (локальный веб-редактор на `file://`, 4 потока, 73 находки → 25 issues; issues №22–№26). Все новые поля run-config и схемы находок необязательные: старые `run-config.yaml` и `findings.json` проходят без изменений. Изменения поведения намеренные: `file://` запрещён, пока не задан каталог (`local_roots`); зеркало guard в `lib.js` больше не разрешает переходы при пустом `allowed_domains`; повторное то же сообщение исполнителя не принимается второй раз.

### Добавлено
- **Локальные приложения (`file://`, №22).** `site.local_roots` (абсолютный путь или `file:///…`; `allowed_domains: [file]` — каталоги `file://`-адресов из `start_urls`; `file:///каталог/` в `allowed_domains`). `url_guard.py`: переход и загрузка — только внутри каталога; `..` (и `%2e%2e`), выход за каталог, симлинк внутри каталога, `file://хост/` — запрет; относительный каталог, `/`, корень диска, домашняя папка — код 4; базовые запреты путей — по пути от каталога. `lib.js` (route-обработчики `guard.js`: навигация, кадры, ресурсы) — то же; Chromium и WebKit перехватывают `file://`. Все браузерные скрипты принимают `--url` (несколько раз) и путь к файлу без схемы; `a11y.js` открывает страницы через guard. `links.js` обходит локальные страницы с диска (нет файла — битая ссылка 404), `headers.js` и `lighthouse.js` — «не применимо» для `file://`. `local_app.py copy` — копия приложения в `<RUN_DIR>/app` и перевод run-config на неё. `intake.py from-text` распознаёт `file:///…` и пути к `.html`. Отпечатки находок `file://` — от каталога (копия в другой папке — те же отпечатки), в черновиках каталог → `<app>`, домашняя папка → `~`. Справочник `references/local-files.md` (в том числе: playwright-cli и Playwright MCP блокируют `file://` — `playwright-cli.json`).
- **Окно браузера в run-config (№23).** `browser.headed` / `browser.slowmo` → `rules.json` → все браузерные скрипты (флаг команды `--headed`/`--headless`/`--slowmo` > run-config > `SITE_QA_HEADLESS`/`SITE_QA_SLOWMO` > видимое окно). `browser_mode.py show|set` — переключить окно для всего прогона одной командой, в том числе посреди прогона; `<RUN_DIR>/playwright-cli.json` — окно и доступ к `file://` для `playwright-cli open --config`; строка в блоке правил §4 и в задании исполнителю. `intake.py`: «с открытым окном», «в фоне», «замедли».
- **Копия скила в прогоне (№23).** `skill_snapshot.py <RUN_DIR> --update-config` → `<RUN_DIR>/skill` (полный `SKILL_DIR`, `node_modules` — жёсткими ссылками, остальное — копии; `skill_source` хранит оригинал): длинный прогон не зависит от обновления или уборки установленной папки. Черновик `intake.py from-text` в папку прогона с копиями (`skill/`, `app/`) сразу указывает на них. Общий модуль `shared/scripts/qa_snapshot.py`.
- **Автопилот (№24).** `intake.py from-text --autopilot` (или «автопилот», «без вопросов», `--autopilot` в запросе; `autopilot: true` в run-config): без подтверждения, опроса и «старт», значения по умолчанию, каждое решение — «Решение автопилота» и `journal.py decide --auto`; безопасность не ослабляется (запреты, fail closed, dry-run, confirm-действия — в `questions.json`). `journal.py decide`.
- **Варианты данных и стенды (№24).** Вопрос 2a опроса, `variants` в run-config, распознавание стендов и наборов данных в запросе, правило охвата в `depth-matrix.md` (smoke на каждом варианте), поле `variant` у находок, раздел в отчёте.
- **Задание исполнителю целиком (№25).** `brief.py` собирает задание из шаблона `parallelism.md` (плейсхолдеры `{{…}}`), блока правил §4 дословно с таблицей правил прогона, среза реестра issues (`fetch_issues.py brief`), формата результата (`ingest_findings.py example`), окна браузера и лимита времени; поток регистрируется в `threads.json`.
- **Единый формат результата и одно место правды (№25).** В блоке `qa-findings` — массив находок с `dup_check` (`done`/`skipped`), `checked`, `not_checked` с `category`, `metrics`. `validate_findings.py --array FILE|-` (и сообщение с блоком на stdin), `--run run.json`. `ingest_findings.py` пишет `findings/<поток>.json` (массив с id), `coverage/<поток>.json` и `.md`, `run.json`; повторное уведомление тем же сообщением — «уже принято», ничего не меняется; без `dup_check` — `skipped` с предупреждением. Схема: `dup_check`, `dup_of`, `dup_candidates`, `variant`, `verify`, `group`, `not_checked.category`. Общий модуль `shared/scripts/qa_threads.py`.
- **Метрики потоков и вторая волна (№24).** `url_guard.py --trace` — строка на каждое решение (без значений query и текста контекста); `thread_coverage.py build|summary` — время от задания до результата (⚠ больше лимита), переходы и страницы, проверенные действия и элементы, запреты; `thread_coverage.py again` — вторая волна по «не проверено» (категории, запреты — на решение пользователя, потоки по лимиту времени, задачи для `brief.py --items`, todo в журнале). `build_report.py`: «Охват по потокам», варианты, скриншоты находок, несверенные находки.
- **Первопричины и «Как проверить» (№26).** `render_draft.py group --map groups.yaml` — один issue на первопричину (проявления таблицей, шаги основного, гипотеза, «Как проверить» по каждому проявлению, маркер на каждую находку, `groups.json`); `suggest-groups` — черновик `groups.yaml`. Блок «Как проверить» во всех черновиках (из `verify`, `repro`, шагов). `e2e_stub.py` — заготовка регрессионного теста Playwright из `steps[]` и `repro`.
- **Скриншоты в приватный репозиторий без браузера (№26).** `publish_shots.py plan|push`: при праве push — загрузка через `gh api` contents в отдельную ветку (пробный запуск по умолчанию, `--confirm-push` после «да», в основную ветку — никогда, `evidence.sensitive` — не загружается), `--screenshot-base` для черновиков; без push — веб-форма (`web-upload.md`).
- **После доработок (№24, раздел «Общий процесс» отзыва).** `references/fix-cycle.md`: тест, падающий до правки, проверка на всех вариантах данных, три прогона нового e2e, обязательное независимое ревью диффа отдельным агентом (шаблон задания ревьюеру), закрытие с «что изменено / чем проверено».

### Исправлено
- `lib.js navAllowed` (route-обработчики `guard.js`) разрешал переход на любой хост при пустом `allowed_domains` — теперь запрет, как в `url_guard.py` (`base:no-allowlist`).
- `lib.js parseArgs`: `--headed` / `--headless` не забирают следующий аргумент (URL оставался бы «значением флага»).

### Тесты
- `tests/test_v140.sh` (офлайн, на Python 3.9 и 3.14): `file://` в `url_guard` (каталоги, `..`, симлинки, хост, широкие и относительные каталоги, базовые запреты от каталога, ресурсы, export), `intake` (локальные пути, окно, автопилот, стенды), отпечатки и маскирование путей, `skill_snapshot` (жёсткие ссылки, удаление источника посреди прогона, версии), `local_app`, `browser_mode` и порядок `browserMode`, `validate_findings --array`, `ingest` (файлы потоков, повтор сообщения, `dup_check`), `--trace`, `fetch_issues brief`, `brief.py`, `coverage` (метрики на фиксированном времени, `summary`, `again`), `build_report`, `journal decide`, `group --map`, `suggest-groups`, «Как проверить», `e2e_stub` (`node --check` для JS), `publish_shots` на поддельном `gh` (`tests/helpers/fake_gh_contents.py`).
- `tests/test_v140_browser.sh` + `v140.test.js` — без сервера, приложение-фикстура `tests/fixtures/local-app` по `file://`: occlusion (в том числе перекрытие кнопки в iframe), reachability, targets, a11y, shot, rtl, device_context, repro, links, headers/lighthouse, обрыв перехода скриптом на файл вне каталога, симлинк (страница и ресурс), паритет `lib.js` и `url_guard.py`.
- `doc_node_flags.py` учитывает флаги общих помощников `lib.js` (`--url`, `--headed`, `--slowmo`).

## [1.3.0] — 2026-10-09
По обратной связи боевого прогона 08–09.10.2026 (пункты S-1…S-9, G-1…G-12). Все новые поля run-config и схемы находок необязательные: старые `run-config.yaml` и `findings.json` проходят без изменений. Несовместимое поведение одно и намеренное: guard больше не «пропускает» при сбое (код 4).

### Безопасность (исправлено)
- **Fail closed (S-2).** `url_guard.py`: любая ошибка — нет `--config` или файла, битый YAML, неверный регэксп в правилах, неверные аргументы (раньше код 2 argparse читался как «confirm»), внутренняя ошибка — даёт `{"decision": "unavailable"}` и **код 4**; `nav`/`action`/`export` без `--config` больше не разрешают всё подряд. `guard.js`: сбой моста к Python — решение `unavailable` и `GuardUnavailableError` (раньше `confirm`), действие и переход не выполняются; ошибка правил в обработчике маршрута обрывает навигацию; `--rules` с несуществующим файлом — код 4; node-скрипты передают код 4 наружу. Блок правил §4 и задание исполнителю: «код 4, любой другой код, “No such file”, пустой вывод = СТОП».
- **Пустой `site.allowed_domains`.** `url_guard.py nav` раньше пропускал любой внешний хост, если список разрешённых доменов не задан; теперь переход запрещён (код 3, `base:no-allowlist`). Найдено живой проверкой S-2 после реализации.
- **Состояние входа (S-3).** `device_context.js state` сохраняет только cookie `allowed_domains` (фильтр обязателен: `--rules`/`--config`/`--domains`; чужие — только числом), выгружает localStorage и sessionStorage открытых вкладок сайта (раньше `origins: 0`), пишет файл атомарно с правами 600; `state-rm` (перезапись и удаление), `run --delete-state` (и при ошибке/прерывании); sessionStorage переносится в эмулированный контекст.
- **Сессии и вкладки (S-6, S-7).** Запрет `close-all`/`kill-all` и чужих сессий в §4 и задании; `scripts/tabs.py` — реестр вкладок `tabs.json` (одна вкладка на профиль устройства, `audit` дублей по CDP, `cleanup` только своих).

### Добавлено
- **Один путь скила (S-1).** `scripts/skill_dir.py`: `SITE_QA_AUDIT_DIR` → своя папка (не рабочая копия репозитория) → установленный плагин (`installed_plugins.json`) → новейшая версия в кэше плагина → `~/.claude/skills` → `.claude/skills` проекта → рабочая копия с предупреждением; `--check`, `--json`, `--export`. `check_env` печатает и проверяет `SKILL_DIR`, пишет его в `env.json`, команды исправления указывают на него; `run-config.yaml → skill_dir` (`intake.py` заполняет); исполнитель проверяет путь и `url_guard.py selftest` до работы.
- **Эмуляция телефона (S-4).** Проверка `matchMedia('(pointer: coarse)')` у каждого устройства (`media.touchValid`), принудительная эмуляция медиа в Chromium при необходимости; `WxH@mobile` — телефон произвольного размера (`WxH` — десктопное окно); `device_context.js media`; чек-лист `rsp.touch-emulation`: без `pointer: coarse` измерения целей нажатия недействительны.
- **Находки текстом (S-5).** Исполнитель возвращает находки блоком ```` ```qa-findings ```` в последнем сообщении; `scripts/ingest_findings.py` проверяет по схеме, присваивает id, переносит `not_checked`, вопросы — в `questions.json`, сообщение — в `raw/messages/` (общий модуль `shared/scripts/qa_ingest.py`).
- **Независимая перепроверка (S-9).** Поле `repro` у находки; `scripts/recheck.py` (`run` — дважды, только скрипты скила; `set` — ручная проверка другим исполнителем; `legal`; `gate`), `node/repro.js` (`--js` / `--selector --assert`); `build_report.py publish-table` — колонка «Перепроверка», без подтверждения — «НЕ публиковать» (общий модуль `qa_recheck.py`).
- **Юридическое.** Правовые и финансовые утверждения — только «возможно применимо» (`legal.norms`), вторая проверка другим исполнителем (`recheck.py legal`), «требуется проверка юристом» в тексте issue (`render_draft.py`); без этого gate закрыт. SKILL.md, `safety-rules.md` §6a.
- **Диалог из радио-кнопок (G-2).** `invariants.js`: `dialog: {choose, confirm, then}` — каждый вариант нажимается через guard и должен стать `aria-checked="true"`, только потом «Готово»; затем проверяется флажок в панели; любой сбой — остановка до подтверждения. ARIA-флажки читаются по `aria-checked`.
- **Предусловия аккаунта (G-3, G-4).** `claims.py plan`: у каждого пункта «Предусловия» (гость / без Pro / с Pro / другая роль / нужны данные), сводная таблица вверху, `--account-states`; `intake.md` вопрос 5b и `auth.paid_tiers` — платные уровни и проход в каждом состоянии заранее.
- **Только чтение (S-8).** `url_guard.py nav --read-only [--log]` и `guard.js` `readOnly`: страницы покупки/доната и `rules.read_only_urls` можно открыть и прочитать; клики, ввод и запросы кроме GET/HEAD/OPTIONS запрещены; OAuth, выход, удаление аккаунта, шлюзы и чужие хосты — никогда.
- **legal-ui (G-1, G-9).** Направление и чек-лист `checklists/legal-ui.md`; `node/legal_guest.js` — гость в чистом профиле (cookie и хранилище сразу и через N секунд, сторонние хосты, баннер и его кнопки, документы, оператор, возрастная маркировка, `--locales`, `--cdp` в обычном Chrome, пометка `navigator.webdriver`). `--locales` у `shot.js`, `a11y.js`, `occlusion.js`.
- **Группировка (G-5).** `render_draft.py group` / `groups`: несколько мелких находок или предложений одной темы — один issue (таблица, подробности, маркер на каждую находку), тип `suggestion`; `--body-only`.
- **Прямая публикация (G-6).** `publish_mode: direct`; `scripts/direct_publish.py` (`check` — gate и дубли через `fingerprint.py match`, `record` → `published.json`, `next`, `status`); `repo-sync.md` §4a (общий модуль `qa_direct.py`).
- **Скриншоты (G-7).** Портретные снимки — подписи в поле справа (`--gutter auto|on|off`, `canvas` в ответе); пример `shot.js "селектор|подпись"` — в начале SKILL.md; перерисовка из сырого PNG и `spec.json`.
- **Скриншоты в существующий issue (G-8).** `publish_web.mjs --attach-to N` — плейсхолдеры `**[Скриншот: файл]**` и `{{qa-shot:файл}}` → вложения, один номер за вызов, повтор при 404.
- **RTL (G-10).** `node/rtl.js` (`dir`, незеркальные панели, имена без bidi-изоляции, «слева/справа» в тексте, `text-align: left`) и пункт `i18n.rtl` в `content-i18n.md`.
- **Перекрытия (G-11).** `occlusion.js`: `--min-area` (по умолчанию 16 px²), пропуск `pointer-events: none`, пометка невидимого закрывающего, счётчики `filtered`.
- **Цели нажатия (G-12).** `node/targets.js`: «N из M меньше 24×24 (по типам); меньше 44×44: K» одной строкой, ссылки в тексте — исключение 2.5.8.
- Окно браузера эмулированных устройств видимое по умолчанию (`SITE_QA_HEADLESS=1` — скрыть, `SITE_QA_SLOWMO` — замедлить) — теперь общий `launchOptions` в `lib.js`; описано в INSTALL.md вместе с `SITE_QA_AUDIT_DIR` и шагами обновления через маркетплейс.

### Тесты
- `tests/test_v130.sh` (офлайн): fail closed `url_guard`, `--read-only`, `skill_dir.py` на изолированном HOME, `ingest_findings.py`, `recheck.py` (confirmed / not-reproduced / refused / error, gate, ручная и правовая проверка), `render_draft.py group`, `direct_publish.py`, `claims.py` предусловия, `intake.py`, `tabs.py` с поддельным CDP.
- `tests/test_v130_browser.sh` + `v130.test.js` (локальные фикстуры): `targets.js`, фильтры `occlusion.js`, диалог из радио-кнопок, `shot.js` (поле подписей, `--locales`), `a11y.js --locales`, `legal_guest.js`, `rtl.js`, `repro.js` + `recheck.py`.
- `stream_b.test.js`: fail closed `guard.js`, режим только чтения, фильтр cookie и localStorage/sessionStorage в `state`, `state-rm`, `--delete-state`, `media`. `test_stream_c.sh`: `--attach-to`. Тесты браузера запускаются с `SITE_QA_HEADLESS=1`.

## [1.2.1] — 2026-10-08
Правило «папка результатов по умолчанию в `.gitignore`» и итоги в другую папку — только итоговые файлы. Старые `run-config.yaml` работают без изменений (`git` необязателен, по умолчанию `allow_commit_results: false`).

### Изменено
- Результаты и git: если пользователь в запросе явно не разрешил класть результаты в репозиторий, `qa-runs/` обязана быть в `.gitignore`. `gitignore_helper.py ensure <OUTPUT_ROOT>` — сразу после выбора папки и **до создания `<RUN_DIR>`** (папки может ещё не быть): строка `/<путь>/qa-runs/` в `.gitignore` репозитория без вопроса; `git.allow_commit_results: true` (только явное разрешение) — `.gitignore` не трогается. Уже отслеживаемые файлы `qa-runs/` не удаляются: код 1, команда `git rm -r --cached` и один вопрос → `untrack --yes` после «да». Вопрос «Добавить qa-runs/ в .gitignore?» в конце прогона убран; старый ответ «буду коммитить» (`.gitignore-decision`) сам больше не действует.
- `scripts/gitignore_helper.py` — тонкая обёртка над общим `shared/scripts/qa_gitignore.py` (вендорится через `.shared`), как в `android-qa-audit`; `check` и `apply` работают как раньше.
- `report_destinations: folder`: `scripts/export_results.py` (общий `shared/scripts/qa_export.py`) копирует в `<path>/<YYYY-MM-DD>-<host>/` только `summary.md`, `report.md`, `findings.json` и скриншоты находок — без `raw/`, `logs/`, `drafts/`; конфликт имён — код 1 без записи, `--overwrite` после «да».

### Добавлено
- `intake.py from-text`: `git.allow_commit_results` — `true` только при явном разрешении в запросе (RU/EN: «коммить результаты», «положи результаты в репозиторий», "commit the results", «не добавляй qa-runs в .gitignore»), отрицания — `false`; такие фразы больше не превращаются в запрет кнопки.
- SKILL.md, INSTALL.md: после установки скил виден только в новой сессии Claude Code (в текущей — «Unknown skill»); как продолжить в той же сессии.

### Тесты
- `tests/test_v121.sh` (16 проверок, вызывается из `unit.sh`): `ensure` по умолчанию, с разрешением из флага, текста и run-config, вне git, уже отслеживаемые файлы и `untrack`; `git.allow_commit_results` в `intake.py`; `export_results.py`; SKILL.md без вопроса про `.gitignore` в конце. `unit.sh` проверяет синтаксис новых скриптов и вендоренных модулей.

## [1.2.0] — 2026-10-08
Универсальность, автозапуск по смыслу запроса, расширенный опрос, память о сайте, куда записывать итоги, установка. Все новые поля run-config необязательные: старые `run-config.yaml` и `findings.json` проходят без изменений.

### Добавлено
- Автозапуск: `description` перечисляет обычные формулировки (RU/EN) — протестировать, проверить, найти баги на сайте, в веб-приложении, интерфейсе; вёрстка, адаптив, доступность, скорость, SEO; URL в запросе — и когда скил **не** использовать (разработка и правка сайта, код тестов, дизайн с нуля, ревью кода, нагрузка, пентест).
- Подтверждение намерения: если скил подхвачен по смыслу, а не командой `/site-qa-audit`, первое действие — вопрос «Похоже, вы хотите протестировать <что понято>. Запустить QA-аудит?» («Да, запустить аудит» / «Да, но сначала уточнить задачу» / «Нет, это другое»); при «Нет» скил ничего не создаёт (SKILL.md, `intake.md`).
- Опрос (`intake.md`): что именно тестируем и что считать успехом (`goal.focus`, `goal.success`), куда не переходить (разделы, URL, поддомены), откуда узнать о сайте и что важно изучить (`context.sources`, `context.notes`), куда записать итоги (`report_destinations`), расширенный чек-лист запретов (регистрация, отправка любых форм, удаление, настройки аккаунта, рассылки, внешние ссылки, реклама) с правилами, проверенными по семантике `url_guard` (`context` — подстрока, не регэксп); порядок порций вопросов и лимит вариантов `AskUserQuestion`.
- Память о сайте: `<OUTPUT_ROOT>/qa-runs/.site-context/<host>/context.md` + `sources.json` (шаблон `templates/site-context.md`): в начале прогона скил показывает резюме и спрашивает «как есть / обновить / изучить заново», на разведке изучает источники, в конце дополняет; секреты и персональные данные не хранятся (`run-files.md`). Путь передаётся субагентам.
- Куда записать итоги: `report_destinations` — `local`, `folder` (копии `report.md` и `summary.md`), `github` (итоговый issue со сводкой по `repo-sync.md` §5), `artifact` (страница через инструмент Artifact, если он есть, иначе пропуск с пометкой), `custom`; раздел «Куда записаны итоги» в `report.md`. `build_report.py summary` → `summary.md`.
- `scripts/gitignore_helper.py` (`check` / `apply --mode gitignore|exclude|keep`): после отчёта, если `qa-runs/` внутри git-репозитория и не игнорируется, — один вопрос «Добавить qa-runs/ в .gitignore?»; запись только после ответа, идемпотентно, уже отслеживаемые файлы не трогаются (печатается команда `git rm -r --cached`), ответ «буду коммитить» запоминается.
- Параллельность до 4 потоков: независимые направления, группы страниц, гипотезы и перепроверки (`parallelism.md` → «Сколько потоков»); `parallel.max_workers` 1–4, по умолчанию 2, общая сессия входа — 1. `intake.py` распознаёт «в 3 потока», «четыре потока», «parallel: 4», «последовательно» и ограничивает максимумом 4.
- `INSTALL.md` — установка и обновление для macOS и Windows: маркетплейс, клон + `tools/install.sh` / `tools/install.ps1`, копия; Node-зависимости и браузеры; `check_env`; обновление и откат; `SITE_QA_OUTPUT_DIR` (в т. ч. пути Windows в JSON); частые проблемы; промпты для Claude Code на установку и на обновление.

### Изменено
- `templates/run-config.example.yaml`: разделы `goal`, `context`, `report_destinations`; `parallel.max_workers: 2` (1–4).
- `<OUTPUT_ROOT>` по умолчанию — папка запуска `<cwd>`, результаты в `<cwd>/qa-runs/` (раньше формулировка «`<cwd>/qa-runs`» читалась как `qa-runs/qa-runs`); устаревшие тексты «скил спросит, куда сохранять» в README, `setup.md`, `check_env.py` исправлены.
- SKILL.md: раздел «Запуск: подтверждение намерения», память о сайте в шагах 2 и 4, шаг 11 «Итоги, память, уборка».

### Тесты
- `tests/test_v12.sh` (24 проверки, без сети; вызывается из `unit.sh`): `gitignore_helper.py` на временных git-репозиториях с изолированным HOME (вне git, не игнорируется, `.gitignore`, `.git/info/exclude` в подпапке, идемпотентность, правило «!», `keep`, уже отслеживаемые файлы, ошибки), `intake.py` — `max_workers` не больше 4, разделы run-config 1.2.0, `build_report.py summary`, шаблон `site-context.md`.

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
