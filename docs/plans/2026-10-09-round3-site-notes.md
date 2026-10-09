# Раунд 3: заметки исполнителя (site-qa-audit 1.5.0)

Ветка: `feature/site-qa-1-4-1` (от `main`). Источник: GitHub issues №9, №26 (остаток), №34. Версия — **1.5.0** (MINOR: новые возможности — реестр вкладок в node-скриптах, `e2e_run.js`, `browser_mode.py mcp`, `publish_shots.py local`, WebKit в `reachability.js`).

## Чек-лист

### №9 реестр вкладок в node-скриптах
- [x] `tabs.py`: инструмент `node` (свой браузер скрипта, pid), `cleanup` — завершённый процесс → закрыта, живой — не трогать; записи `node` не мешают правилу «одна вкладка на профиль»
- [x] `lib.js`: общий реестр (`tabs()`, `trackPage`, `closeTab`) в формате `tabs.py`, тот же lock-файл; RUN_DIR из `--run-dir` / `SITE_QA_RUN_DIR` / папки `--rules`; `--owner` / `SITE_QA_OWNER`; `--no-tabs` / `SITE_QA_TABS=0`
- [x] `device_context.js` (`openDevice`, `attachCdp`) → все детекторы; `a11y.js`, `legal_guest.js` (и `--cdp`), `lighthouse.js`, `guard.js check`, `e2e_run.js`; `links.js`, `headers.js` браузер не открывают — не нужно
- [x] тесты: офлайн (формат, lock с `tabs.py` при параллельной записи, SIGKILL, чужие записи) и браузерные (file://, CDP-заглушка браузера пользователя, сбой скрипта)
- [x] `brief.py`/шаблон `parallelism.md`: node-скрипты с `--rules <RUN_DIR>/rules.json --owner <поток>`

### №26 скриншоты в приватный репозиторий
- [x] `publish_shots.py plan`: заранее и без записи — gh есть / вошёл (scope `repo`) / репозиторий виден / push; режим `local` с причиной вместо ошибки
- [x] запасной путь `publish_shots.py local`: `results/screenshots/` + `index.md` + `screenshots.zip`, строка для issue; `build_report.py` ссылается
- [x] отказ записи (403) при `push` — понятная причина, загруженное сохраняется, запасной путь; `--fallback-local`
- [x] документация: почему вход в GitHub не автоматизируется (`repo-sync.md`, `web-upload.md`, README, docstring)

### №34 отложенное из 1.4.0
- [x] WebKit: колесо (десктопный WebKit) и модель жеста касания (мобильный WebKit) в `reachability.js`; заодно исправлен вердикт на телефоне (решает жест)
- [x] Playwright MCP и `file://`: `browser_mode.py mcp` (отдельный сервер прогона, guard в каждой вкладке через `browser.initPage`), проверка по stdio (`mcp_check.js`, `--check`)
- [x] запуск e2e-заготовок через Playwright Test (`e2e_run.js`): до исправления падает на дефекте, после — проходит три раза; guard внутри теста
- [x] видимое окно (`--headed`, slowMo): прогон на фикстуре `file://` вживую (UA без `HeadlessChrome`), тест под `QA_HEADED=1`

### Выпуск
- [x] SKILL.md (174 строки), README, INSTALL, CHANGELOG, plugin.json 1.5.0, tests/README.md, references (parallelism, run-files, layout-detectors, local-files, fix-cycle, repo-sync, web-upload, devices-auth)
- [x] validate (на копии после `skillsrepo.py sync` — 0 ошибок; в рабочем дереве — только ожидаемая версия marketplace.json), unit.sh на Python 3.14 и /usr/bin/python3

## Решения
- **Реестр в JS, а не вызов `tabs.py`.** Запись при выходе процесса должна быть синхронной (`process.on('exit')`), поэтому `lib.js` пишет `tabs.json` сам — тем же форматом, тем же lock-файлом (`tabs.json.lock`, O_EXCL, устаревший через 60 с) и тем же tmp+rename. Совместимость проверяется тестом параллельной записи (3 node-процесса + 2 цикла `tabs.py`: 70 записей, без потерь и повторов id).
- **`@playwright/test` не ставится.** В `playwright` 1.63 уже есть Playwright Test (`playwright test`, `playwright/test`); `@playwright/test` — только переэкспорт. Заготовки импортируют `@playwright/test` — `NODE_PATH` указывает на обёртку `scripts/node/e2e/shim/@playwright/test`, которая отдаёт `playwright/test` + guard прогона в контексте. Папка не называется `node_modules` (в `.gitignore`), `NODE_PATH` ищет модули в любой папке. Заготовки копируются во временную папку, чтобы рядом не оказалось `node_modules` проекта пользователя (иначе — второй экземпляр Playwright Test).
- **MCP-обёртка.** У Playwright MCP 1.63 есть `browser.initPage` (модуль, вызываемый для каждой новой вкладки с `{ page }`) — через него к контексту подключается тот же `guardContext`, что у node-скриптов. Так флаг `allowUnrestrictedFileAccess` (без него MCP не открывает `file://`) не открывает весь диск. Сервер добавляет пользователь (`claude mcp add …`), `~/.claude` скил не трогает.
- **WebKit.** Playwright: `mouse.wheel` в мобильном WebKit бросает «Mouse wheel is not supported in mobile WebKit», `touchscreen` умеет только `tap`. Настоящего жеста нет — сделана модель касания в странице (цепочка прокрутки, `overscroll-behavior`, `touch-action`); она согласуется с жестом CDP в Chromium на трёх фикстурах (scroll / hidden / touch-action).

## Отложено и почему
| Пункт | Что не сделано | Почему |
|-------|----------------|--------|
| №26 автоматическая загрузка без права push | Загрузка через веб-форму GitHub без входа пользователя | Вход (пароль, 2FA, SSO) делает только пользователь — правило безопасности, а не техническое ограничение. Сделано всё, что без входа возможно: проверки заранее, понятные причины, запасной путь `local` (артефакт при отчёте), документация. Предлагается закрыть №26 (текст комментария — ниже) |
| №34 настоящий сенсорный ввод WebKit | Инерция, нативная прокрутка Safari, панель инструментов iOS (`100vh`) | Playwright не даёт в мобильном WebKit ни колеса, ни жеста; нужна реальная iOS или симулятор Xcode — вне рамок скила. Реализована модель касания в настоящем WebKit (раскладка и стили WebKit) + эмуляция в Chromium с настоящим жестом |
| №34 MCP-обёртка внутри сессии Claude Code | Подключение сервера к живой сессии | Добавление MCP-сервера меняет настройки пользователя (`~/.claude`, `.mcp.json`) — только по его решению; проверено тем же сервером по stdio (`mcp_check.js`: initialize → `browser_navigate` → `browser_close`) |
| `e2e_run.js` для ESM-заготовок (`.mjs`) | Запуск через обёртку | `NODE_PATH` не действует на `import` в ESM; `e2e_stub.py` выдаёт только `.spec.ts` и CommonJS `.spec.js` |
| `e2e_run.js --browser firefox` | Проверка | Firefox 155 (playwright 1.63) не запускается на macOS 27 (`environment-notes.md`) |

## Найдено по дороге
- **Исправлено:** `reachability.js` на сенсорных конфигурациях брал вердикт по колесу мыши — панель внутри `touch-action: none` считалась достижимой на телефоне, хотя пальцем её не прокрутить (жест CDP touch её действительно не двигает — проверено). Теперь на телефоне жест выполняется всегда и решает он; десктоп без изменений. Фикстура `reach-touch-action.html`, тест.
- **Исправлено:** `publish_shots.py` без установленного `gh` падал с трассировкой `FileNotFoundError`; ошибка записи на середине загрузки теряла сведения об уже загруженных файлах (`shots-published.json` не писался).
- **Изменено поведение:** `publish_shots.py plan` при недоступном репозитории — режим `local` (код 0) с причиной вместо кода 3; тест 1.4.0 обновлён.
- **Обнаружено:** JSON-отчёт Playwright Test при `--repeat-each` даёт повторы отдельными записями `tests[]` — `e2e_run.js` сводит их в `runs[]` одной строки.
- **Обнаружено:** страница, переход которой оборвал guard, показывает `chrome-error://chromewebdata/` (известно с 1.4.0) — проверки «остались ли в приложении» надо писать как «не открылся файл вне каталога».
- **Обнаружено:** в пакете `playwright` 1.63 есть и Playwright Test, и сервер Playwright MCP (`playwright mcp`) — ни `@playwright/test`, ни `@playwright/mcp` ставить не нужно.
- **Окружение:** worktree создаётся без `node_modules` — для браузерных тестов `npm ci` в `skills/site-qa-audit/scripts/node` (локально, из кэша npm за 1 с).

## Текст комментария для №26 (предлагается закрыть)
> Сделано в site-qa-audit 1.5.0: `publish_shots.py plan` заранее и без записи проверяет `gh`, вход `gh` (scope `repo`), видимость репозитория и право push и называет причину; `push` при отказе записи (403: токен без Contents: write, SSO, правила веток) останавливается с понятной причиной, сохраняет уже загруженное и печатает запасной путь; новая команда `publish_shots.py local` — скриншоты при отчёте (`results/screenshots/`, `index.md`, `screenshots.zip`, ссылка в сводке, строка для issue), `push --fallback-local`. Полностью автоматическая загрузка без права push не делается намеренно: она требует входа на GitHub в браузере (пароль, 2FA, SSO), а вход выполняет только пользователь — скил не вводит учётные данные, не берёт cookie github.com и не управляет страницей входа (описано в `references/repo-sync.md` и `references/web-upload.md`).

## Где остановился
2026-10-09, всё по №9, №26, №34 сделано в ветке `feature/site-qa-1-4-1`, в main не вливалось.
- Проверки: `tools/validate.sh` на копии после `skillsrepo.py sync` — 0 ошибок (в рабочем дереве — ожидаемая ошибка версии marketplace.json 1.4.0 ≠ 1.5.0); `tests/unit.sh` — PASS 77, FAIL 0 на Python 3.14 и /usr/bin/python3 (3.9.6): v1.5.0 офлайн 26/26, v1.5.0 browser 18 PASS + 1 SKIP (видимое окно — только с `QA_HEADED=1`; запущен отдельно вживую — PASS); прежние наборы без регрессий.
- Следующий шаг (оркестратор): слить ветку, `python3 tools/lib/skillsrepo.py sync` (marketplace.json и README корня — 1.5.0), корневой CHANGELOG, тег `site-qa-audit/v1.5.0`, `npm install` в папке новой версии плагина; комментарии в №9, №26 (текст выше), №34 и закрытие.
