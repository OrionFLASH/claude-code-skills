# Журнал изменений

Формат — [Keep a Changelog](https://keepachangelog.com/ru/1.1.0/). Версии отдельных скилов — в их собственных `CHANGELOG.md`.

## [Unreleased]
- `site-qa-audit` 1.6.0 и `android-qa-audit` 1.4.0: принудительный запуск из запроса (хук плагина + `shared/scripts/qa_force.py`): метки `!qa` / `qa:` / `!site-qa` / `!android-qa` с опциями `autopilot` и `smoke|standard|deep`, фраза «запусти скилл …»; вопрос о намерении снимается, публикация не включается.
### Добавлено
- `typesafe-triage` 2.4.2: принудительный запуск триажа из запроса — слэш-вызов `/typesafe-triage:typesafe-triage <задача>` (раньше хук пропускал его как команду), метка `triage:` / `!триаж opus/high`, фраза «сделай триаж»; снимает пропуски хука, выбор модели не меняет.
### Исправлено
- `typesafe-triage` 2.4.1: хук пропускал настоящие запросы, начинавшиеся с `<` (в VSCode — с `<system-reminder>`/`<ide_selection>`); теперь служебные блоки вырезаются, остальное оценивается и в TypeSafe не уходит. «Don't use opus» больше не читается как «без субагента».

## 2026-10-09 (3)
### Добавлено
- `site-qa-audit` 1.5.0 — реестр вкладок во всех node-скриптах (`tabs.json`, `--owner`, `--run-dir`), проверка права push заранее и запасной путь для скриншотов (`publish_shots.py plan/local`), достижимость в мобильном WebKit, запуск e2e-заготовок под guard (`e2e_run.js`), отдельный Playwright MCP для `file://` с guard (`browser_mode.py mcp`), проверка видимого окна.
- `android-qa-audit` 1.3.0 — график PSS (SVG) и спарклайн в отчёте, контактный лист скриншотов (`annotate_android.py sheet`), корректный `job stop` (в том числе на Windows), честное описание loopback на Windows.
- `typesafe-triage` 2.4.0 — автозапись факта через хуки плагина (`PostToolUse`/`SubagentStop`, опция `TYPESAFE_TRIAGE_AUTO_FACT=on`), признаки сессии (доля записи, накопленные факты, профиль) из служебных полей стенограммы.
- Общие тестовые модули `shared/tests` (`doc_commands.py`, `doc_zsh.py`) с вендорингом через `.shared` и проверкой `validate`.
### Исправлено
- `site-qa-audit`: `reachability.js` на телефоне решал по колесу мыши (контейнер с `touch-action: none` считался достижимым); `publish_shots.py` падал без gh и терял сведения об уже загруженном.
- `android-qa-audit`: `annotate_android.py render` с относительными путями; ссылки HTML-листа на macOS; повторный SIGTERM мог оборвать запись сводки soak.

## 2026-10-09 (2)
### Добавлено
- `android-qa-audit` 1.2.0 — по отзывам реального прогона (диктофон): подача звука в микрофон эмулятора (`mic-inject`: gRPC с токеном, loopback, файл; `avd_manager start --mic-inject`, `--extra-args` с белым списком), нажатия без дерева элементов (`tap X Y --no-ui`), `dump-ui --retry/--texts/--grep`, `find` с границами, неоднозначность `tap`, `soak` и `job` (долгие сценарии с проверкой предусловий), исправленные `notifications`, аннотированные скриншоты (`screenshot --mark`, `finding.py`), публикация по GitHub issue forms, документы «известно», вложения веткой, `disclosure: tool|none` (по умолчанию `tool`), `import-file`/`push-media`/`ime`, обёртка `qa` для zsh, матрица с существующими `qa-*` AVD и профилем 8 ГБ, `intake --lite`, чек-лист `audio-voice`.
- `site-qa-audit` 1.4.0 — локальные приложения по `file://` (`site.local_roots`, fail closed), `browser.headed`/`slowmo` в run-config, копия скила и приложения в RUN_DIR, автопилот, варианты данных и стенды, единый формат результата исполнителей (`validate_findings.py --array`, `dup_check`, срез реестра), метрики и вторая волна по потокам, группы находок по первопричине и блок «Как проверить», заготовки e2e, скриншоты в приватный репозиторий через API.
- `typesafe-triage` 2.3.0 — заметка начинается с «ДЕЙСТВИЕ: сам | Agent(model, effort) | спросить» и выдаётся реже (продолжения молчат), модель сессии из стенограммы, `--check` проверяет реальную регистрацию хука и имя для Skill, `--batch` с конфликтами по путям, шаблон промпта исполнителя, журнал решений `triage-log.jsonl` (опция) и `--fact`.
- Общие модули `shared/scripts`: `qa_issueforms.py`, `qa_known.py`, `qa_attachments.py`, `qa_snapshot.py`, `qa_threads.py`.
### Исправлено
- `site-qa-audit`: JS-зеркало охраны (`lib.js navAllowed`) пропускало любой хост при пустом `allowed_domains`; `a11y.js` открывал страницы без проверки `url_guard`.
- `typesafe-triage`: уровень зависел от версии Python при нагрузке ровно на пороге; INSTALL советовал класть резервную копию в `~/.claude/skills` (создавала «призрак» скилла).
- `android-qa-audit`: `guard.py emulator-args` принимал цель, начинающуюся с «-», за опцию.

## 2026-10-09
### Добавлено
- `site-qa-audit` 1.3.0 — по обратной связи боевого прогона (S-1…S-9, G-1…G-12): fail closed у `url_guard.py`/`guard.js` (код 4 = стоп), `nav --read-only`, стабильный `SKILL_DIR` (`skill_dir.py`, `SITE_QA_AUDIT_DIR`), безопасная выгрузка состояния входа (фильтр cookie, localStorage, chmod 600, удаление), эмуляция телефона с проверкой `pointer: coarse`, находки JSON-блоком (`ingest_findings.py`), реестр вкладок `tabs.py`, поле `repro` и обязательная перепроверка (`recheck.py`), предусловия аккаунта в `claims.py`, направление `legal-ui` (`legal_guest.js`, `--locales`), `rtl.js`, `targets.js`, фильтры `occlusion.js`, группировка и тип `suggestion`, режим `direct` публикации, `publish_web.mjs --attach-to`, видимое окно браузера по умолчанию (`SITE_QA_HEADLESS`, `SITE_QA_SLOWMO`).
- `android-qa-audit` 1.1.0 — перенос: fail closed (`guard.py`, `adb_helpers.py` код 6), находки блоком, `repro`/`recheck`, direct-publish, реестр стендов, запрет `adb kill-server`.
- `typesafe-triage` 2.2.0 — хук не молчит без причины («триаж пропущен: …»), метка обработки в два состояния, `--where`, пути через `${CLAUDE_SKILL_DIR}`, активная задача из `TASKS.md`, тип `qa`, сигнал общего интерактивного состояния, наследование оценки короткими «продолжай».
- Общие модули `shared/scripts`: `qa_ingest.py`, `qa_recheck.py`, `qa_direct.py`.
### Исправлено
- `site-qa-audit`: пустой `site.allowed_domains` больше не пропускает внешние хосты в `url_guard.py nav`.

## 2026-10-08 (6)
### Исправлено
- `android-qa-audit` 1.0.1 — по первому боевому прогону: падения чужих процессов (UiAutomation от `dump-ui`, сервисы Google, system_server) больше не считаются падениями приложения (`other_processes`); `dump-ui` после поворота берёт фактический размер экрана (нет ложных `visual.offscreen`); `matrix.py` с `hardware: []` строит только свои профили; `install-image --run-dir`; шум Java -ea скрывается при успешной команде; logcat по умолчанию только по приложению (`--all` — весь); `text --translit` / `--adbkeyboard`; темы запретов (камера, QR, точка доступа, микрофон, геолокация, уведомления…) сразу с типовыми текстами; правило «запрет против сценария»; новый скил виден только в новой сессии — как продолжить.
### Изменено
- Обязательное правило для `android-qa-audit` 1.0.1 и `site-qa-audit` 1.2.1: без явного разрешения пользователя коммитить результаты `qa-runs/` сразу, до создания папки прогона, попадает в `.gitignore` (`gitignore_helper.py ensure`; у Android — ещё `*.apk`, `*.aab`, `*.apks`, `*.xapk`, `*.keystore`, `*.jks`, отдельно `git.allow_commit_apk`); вопрос про `.gitignore` в конце прогона убран; уже закоммиченные результаты не удаляются без «да». `report_destinations: folder` получает только итоговые файлы (`export_results.py`).
- `shared/scripts/qa_gitignore.py`: `ensure`, `untrack`, `commit_permission()` (явное разрешение в запросе, RU/EN); новый `shared/scripts/qa_export.py`. `site-qa-audit` переведён на общий `qa_gitignore.py`.

## 2026-10-08 (5)
### Добавлено
- Скил `android-qa-audit` 1.0.0 (статус «в разработке»): QA-тестирование Android-приложений по APK, split APK, `.apks`, AAB или установленному пакету на эмуляторах и устройствах через adb — «брат» `site-qa-audit`: подтверждение намерения при автозапуске, опрос (версии Android, ОЗУ, ядра, экран, шрифт, тема, язык, сеть, батарея), память о приложении `.app-context/<package>/`, разбор APK (`apk_info.py`), стенды и AVD `qa-*` (`avd_manager.py`, чужие AVD не меняются), управление устройством под guard (`adb_helpers.py`, `guard.py`: покупки, внешние аккаунты, звонки и SMS — запрет; реальные устройства — только с согласием), матрица «API × железо × вариации» и до 4 потоков (`matrix.py`), черновики issues (dry-run), отчёт, вопрос про `.gitignore` для `qa-runs/` и `*.apk`, уборка эмуляторов; `INSTALL.md` с настройкой Android SDK для macOS, Windows и Linux.
- `shared/scripts/runjournal.py` (журнал прогона — общий модуль, тот же, что `site-qa-audit/scripts/journal.py`) и `shared/scripts/qa_gitignore.py` (несколько шаблонов, режимы gitignore/exclude/keep); пока вендорятся только в `android-qa-audit`.
### Изменено
- README: ссылка на `android-qa-audit/INSTALL.md`.

## 2026-10-08 (4)
### Добавлено
- Скил `site-qa-audit` 1.2.0: автозапуск по обычным формулировкам о тестировании сайта (RU/EN) с подтверждением намерения, расширенный опрос (что тестируем, успех, куда не переходить, запреты, источники о сайте), память о сайте `.site-context/<host>/context.md`, `report_destinations` (папка, GitHub, Artifact), вопрос про `qa-runs/` в `.gitignore` (`gitignore_helper.py`), до 4 параллельных потоков, `INSTALL.md` (macOS, Windows, промпты для Claude Code). Включает 1.1.1–1.1.2: все файлы прогона только в папке прогона, папка результатов по умолчанию — `<cwd>/qa-runs/`.
### Изменено
- `typesafe-triage` 2.1.3: `INSTALL.md` и `UPDATE.md` объединены в один `INSTALL.md` «Установка и обновление».
- README: ссылки на `INSTALL.md` скилов; репозиторий публичный.

## 2026-10-08 (3)
### Исправлено
- `typesafe-triage` 2.1.2: заметка учитывает, что у `Agent` может не быть параметра `effort` (условная формулировка, фраза глубины для промпта агента, команда `--run` для критичных задач); слова в кавычках, коде, пересказе и вставленных отчётах больше не считаются явными указаниями модели/effort; указания в причинах не дублируются.

## 2026-10-08 (2)
### Исправлено
- `typesafe-triage` 2.1.1: таймаут хука 5 с, один повтор при 5xx/529, первая пауза после сбоя 1 мин.
### Добавлено
- Скил `typesafe-triage` 2.1.0: вторая ось триажа — reasoning effort `low…max` (низкий и максимальный — только с подтверждения пользователя), слоистая оценка (TypeSafe, текст, окружение, история сессии, правила согласованности с моделью), явные указания пользователя, `--run --effort`, `--calibrate`, идемпотентность хука и хук плагина `hooks/hooks.json`.
- Скил `site-qa-audit` 1.1.0: перепроверка заявленных исправлений (`claims.py`), правила безопасности в браузерных действиях (`guard.js`), защита от побочных эффектов (`invariants.js`, `side_effects.md`), детекторы перекрытий и достижимости, устройства и вход `manual-cdp`, iframe, снимок с разметкой через CDP (`shot.js`), направление `content-i18n`, настройки раскрытия и шкалы серьёзности для чужих репозиториев, публикация скриншотов через веб-форму GitHub (`screenshots: web-upload`), `report.md` и журнал прогона из файлов; папка результатов `SITE_QA_OUTPUT_DIR` и аннотированные скриншоты (бывший 1.0.4).

### Изменено
- Скил `typesafe-triage` 2.0.0: универсальный триаж любых задач (не только код), уровни haiku/sonnet/opus/fable (haiku и fable — только с подтверждения пользователя), локальные эвристики и запасной вариант без TypeSafe, короткая императивная заметка хука.

## 2026-10-08
### Добавлено
- Скил `typesafe-triage` 1.0.0: триаж задач разработки через TypeSafe, перенесён из `~/.claude/skills`.

## 2026-10-07
### Добавлено
- Скил `site-qa-audit` 1.0.0 → 1.0.1 (dry-run на демо-стенде, исправления guard и черновиков).
- `shared/scripts`: `miniyaml.py` (подмножество YAML на stdlib), `envcheck.py`; вендоринг общих модулей в скилы через `.shared` (`tools/validate.sh --fix`).
- Каркас репозитория: README, CONVENTIONS, маркетплейс, `shared/`, `tools/` (install, new-skill, validate).
