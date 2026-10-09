# Раунд 2: заметки исполнителя (site-qa-audit 1.4.0)

Ветка: `feature/site-qa-1-4-0` (от `docs/feedback-round2`). Источник: отзыв реального прогона (раздел 1 и раздел 3 «Общий процесс»), GitHub issues №22–№26.

## Чек-лист

### #22 file:// и локальные каталоги (P0)
- [x] `url_guard.py`: `site.local_roots`, `allowed_domains: [file]` (+ каталоги `file://` стартовых URL), `file:///…` в `allowed_domains`; fail closed: `..`, выход за каталог, симлинки, хост в `file://` — deny; относительный, `/`, корень диска, домашняя папка — код 4
- [x] `lib.js`: зеркало проверки (`navAllowed`, `resourceBlocked`), `guard.js` route и мост к Python передают `local_roots`
- [x] детекторы принимают `--url file://…` (и путь к файлу): occlusion, reachability, a11y (теперь через guard), shot, targets, rtl, legal_guest, device_context run, repro, invariants, guard check; links.js обходит локальные страницы с диска; headers.js и lighthouse.js — «не применимо»
- [x] fingerprint: шаблон URL для file:// от каталога; черновики: каталог → `<app>`, домашняя папка → `~`
- [x] `intake.py from-text`: `file:///…` и пути → `start_urls`, `local_roots`
- [x] тесты (Python и браузерные на фикстуре `file://` с iframe), документация `references/local-files.md`

### #23 browser.headed/slowmo, копия скила в RUN_DIR (P0)
- [x] `browser.headed` / `browser.slowmo` → `rules.json` → `launchOptions` (флаг команды > run-config > env > видимое окно); `a11y.js` и `legal_guest.js` через `launchOptions`
- [x] `browser_mode.py show|set` + `<RUN_DIR>/playwright-cli.json` (окно и доступ к `file://` для playwright-cli)
- [x] строка про окно в блоке правил §4 и шаблоне задания
- [x] `skill_snapshot.py` + `shared/scripts/qa_snapshot.py`: копия скила целиком (scripts с node_modules — жёсткими ссылками) в `<RUN_DIR>/skill`, `run-config.skill_dir` на копию
- [x] `local_app.py copy` — копия локального приложения
- [x] тесты, документация

### #24 autopilot, варианты данных/стендов, вторая волна, метрики, ревью диффа (P1/P2)
- [x] `autopilot` в run-config и `intake.py from-text --autopilot [--journal]`, `journal.py decide`; безопасность не ослабляется
- [x] вопрос 2a «варианты данных и стенды» → `variants`, поле `variant`, правило охвата, раздел отчёта
- [x] `thread_coverage.py again <RUN_DIR>` (вторая волна по «не проверено»)
- [x] метрики потока автоматически (`url_guard.py --trace` + `threads.json` + время приёма → `thread_coverage.py build|summary`), подсказка «потоки по 20–30 минут», ход потока до результата
- [x] `references/fix-cycle.md`: независимое ревью диффа (шаблон задания ревьюеру), три прогона новых e2e, варианты данных
- [x] тесты

### #25 единый формат результата исполнителей (P1)
- [x] `validate_findings.py --array` (файл, stdin, сообщение с блоком) + `--run run.json`; `run.json` пишет ingest
- [x] `dup_check: done|skipped` (+ `dup_of`, `dup_candidates`) в схеме; обязательно у находок исполнителей; ingest ставит `skipped` с предупреждением
- [x] `fetch_issues.py brief` — срез реестра; `brief.py` — задание исполнителю целиком
- [x] место правды `findings/<поток>.json` + `coverage/<поток>.md`, повторное уведомление — «уже принято» (`shared/scripts/qa_threads.py`)
- [x] тесты

### #26 группировка по первопричине, «Как проверить», e2e, скриншоты (P1/P2)
- [x] `render_draft.py group --map groups.yaml` и `suggest-groups`
- [x] блок «Как проверить» в шаблоне issue, в группах по теме и по первопричине
- [x] `e2e_stub.py` — заготовка Playwright из `steps[]` и `repro`
- [x] `publish_shots.py` — скриншоты в репозиторий с push через API (своя ветка, dry-run по умолчанию)
- [x] тесты на фейковом gh

### Выпуск
- [x] SKILL.md (173 строки), README, INSTALL, CHANGELOG, plugin.json 1.4.0, tests/README.md
- [x] validate (на копии после `skillsrepo.py sync`), unit.sh на Python 3.14 и /usr/bin/python3, живая проверка file://

## Отложено и почему
| Пункт | Что не сделано | Почему |
|-------|----------------|--------|
| №26 «автоматический путь скриншотов (web-upload)» | Загрузка через веб-форму GitHub по-прежнему требует входа пользователя в браузере | Без права push у REST API нет вложений, а войти за пользователя скил не должен. Сделан автоматический путь для случая из отзыва — приватный репозиторий с правом push: `publish_shots.py` через `gh api` contents в отдельную ветку, без браузера. Без push остаются веб-форма или контактный лист в сводке |
| Отзыв 1.3 «WebKit-специфика» | Колесо и жесты в мобильном WebKit | Ограничение Playwright/WebKit, в issues №22–№26 не входит; как и раньше, достижимость проверяется эмуляцией в Chromium |
| Раздел 3: «Что нового» фрагментами, нумерация ROADMAP | Скрипта сборки фрагментов нет | Это процесс проекта, а не QA-аудита: в `fix-cycle.md` — рекомендация хранить «Что нового» файлами-фрагментами; нумерация ROADMAP — конкретика проекта (правило универсальности) |
| Playwright MCP и `file://` | Флаг `--allow-unrestricted-file-access` на лету не включается | MCP настраивается при запуске и флаг расширяет доступ к файлам вообще; для локального приложения MCP-поток заменяется node-скриптами и playwright-cli (`local-files.md`) |
| `local_roots` и разные написания одного пути | `/tmp/…` и `/private/tmp/…` (macOS) — разные каталоги для guard | Сравнение по написанию из адреса и `realpath` каталога; адрес с другим написанием запрещается — это fail closed, не дыра. Описано в `local-files.md` |
| Страница после оборванного перехода | После того как guard оборвал переход скриптом страницы, вкладка показывает страницу ошибки Chromium | Так было и для http(s) (поведение `route.abort`); детекторы сообщают о запрете в журнале, страницу не подменяем, чтобы не скрыть, что переход был |

## Найдено по дороге
- **Исправлено:** `lib.js navAllowed` (route-обработчики `guard.js`) разрешал переход на любой хост при пустом `allowed_domains` — в `url_guard.py` это закрыли в 6909c2e, а зеркало в JS осталось открытым; теперь `base:no-allowlist`. Покрыто тестом паритета `lib.js` и `url_guard.py`.
- **Исправлено:** `a11y.js` открывал страницы без проверки `url_guard` (только route-перехват) и всегда без окна (`launch()` без `launchOptions`) — теперь через `guardedPage.goto` и общее окно.
- **Исправлено по ходу:** `thread_coverage.py build` до результата потока создавал `coverage/<поток>.json` без полей, и последующий `ingest_findings.py` падал бы на нём — `qa_threads.py` дополняет поля; есть тест.
- **Исправлено по ходу:** черновик `intake.py from-text` в папку прогона после `skill_snapshot.py` / `local_app.py` возвращал в run-config установленную папку скила и оригинал приложения — теперь берёт копии; есть тест.
- **Переименовано:** `coverage.py` → `thread_coverage.py`, чтобы скрипт скила не подменял пакет `coverage` (coverage.py) при импорте и не путался с ним в документации.
- **Обнаружено:** `playwright-cli` 0.1.22 по умолчанию запрещает `file://` («Access to "file:" protocol is blocked»), Playwright MCP — тоже (флаг `--allow-unrestricted-file-access`). Решение — `<RUN_DIR>/playwright-cli.json` с `allowUnrestrictedFileAccess` только для прогонов с `local_roots`; граница — `url_guard.py nav`.
- **Обнаружено:** Chromium и WebKit в Playwright 1.63 перехватывают `file://` через `context.route` (навигации, кадры, ресурсы) — поэтому guard каталога работает и для переходов скриптом страницы.
- Папка scratchpad сессии общая для параллельных агентов (мои временные файлы перезаписывались чужими) — свои временные файлы держать в подпапке.

## Где остановился
2026-10-09, всё по №22–№26 сделано в ветке `feature/site-qa-1-4-0` (9 коммитов), в main не вливалось.
- Проверки: `tools/validate.sh` на копии после `skillsrepo.py sync` — 0 ошибок; `tests/unit.sh` — FAIL 0 на Python 3.14 и /usr/bin/python3 (3.9.6); живая проверка `file://` — детекторы на копии фикстуры (вывод в отчёте исполнителя).
- Следующий шаг (оркестратор): слить ветку, `python3 tools/lib/skillsrepo.py sync` (marketplace.json и README корня — версия 1.4.0 и описание), корневой CHANGELOG, тег `site-qa-audit/v1.4.0`, `npm install` в папке новой версии плагина после обновления.
