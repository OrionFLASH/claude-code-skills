# Устройства и состояние входа: `device_context.js`

Эмуляция устройств и размеров окна — одна из самых ценных частей прогона. Модуль открывает эмулированное устройство с входом пользователя или без него и запускает один сценарий на списке устройств.

## Каталог
`node <SKILL_DIR>/scripts/node/device_context.js list`

| Имя | Окно (CSS px) | Движок | Примечание |
|-----|---------------|--------|-----------|
| `desktop` | 1440×900 | chromium | |
| `desktop-1280` | 1280×720 | chromium | |
| `laptop` | 1024×768 | chromium | |
| `low` | 720×450 | chromium | низкое окно — обязательный прогон достижимости |
| `pixel7` / `pixel7-landscape` | 412×839 / 863×360 | chromium | Playwright `Pixel 7` |
| `iphone15` / `iphone15-landscape` | 393×659 / 734×343 | webkit | Playwright `iPhone 15` |
| `ipad` / `ipad-landscape` | 810×1080 / 1080×810 | webkit | Playwright `iPad (gen 7)` |
| `360x640` / `640x360` | 360×640 / 640×360 | chromium | малый телефон, мобильный UA |

Также принимаются любое имя из `playwright.devices`, **`WxH` — десктопное окно** этого размера (без касаний, `pointer: fine`) и **`WxH@mobile` — телефон** этого размера (`isMobile`, `hasTouch`, мобильный UA). Устройства Apple по умолчанию запускаются **отдельным WebKit**; `--browser chromium` — эмуляция в Chromium (нужна для `reachability.js`: в мобильном WebKit нет колеса и CDP-жестов).

## Окно браузера
Одно место на весь прогон — `run-config.yaml → browser` (`headed: true|false|null`, `slowmo: <мс>|null`), его видят все браузерные скрипты скила через `rules.json`. Переключить **посреди прогона** (например, пользователь попросил «проводи тесты с открытым окном») — одна команда, без сообщений исполнителям:
```bash
python3 <SKILL_DIR>/scripts/browser_mode.py set <RUN_DIR> --headed --slowmo 400   # или --headless / --default
python3 <SKILL_DIR>/scripts/browser_mode.py show <RUN_DIR>                         # что действует и откуда
playwright-cli -s=qa-ux open <URL> $(python3 <SKILL_DIR>/scripts/browser_mode.py show <RUN_DIR> --cli)
```
Порядок (первое заданное): флаг команды `--headed` / `--headless` / `--slowmo <мс>` (любой браузерный node-скрипт) → `run-config.yaml → browser` → `SITE_QA_HEADLESS=1` (скрыть) и `SITE_QA_SLOWMO=<мс>` → по умолчанию окно **видно**, замедление 250 мс. Следующий запуск любого node-скрипта берёт новый режим сам; уже открытые сессии `playwright-cli` — после переоткрытия своей сессии; Playwright MCP настраивается при запуске (`--headless`) и не переключается (отдельный MCP прогона берёт окно из `browser_mode.py mcp` при создании конфига). Заготовки e2e (`node/e2e_run.js`) — тот же порядок. Видимое окно проверено вживую на macOS (1.5.0): `--headed --slowmo` даёт браузер не в режиме headless (в `navigator.userAgent` нет `HeadlessChrome`), профиль — временный, окна пользователя не затрагиваются; тест — `QA_HEADED=1 tests/test_v150_browser.sh "видимое окно"`. Служебные запуски (`guard.js check`, `device_context.js media`, рендер аннотаций) всегда без окна. Тесты скила ставят `SITE_QA_HEADLESS=1` сами.

## Эмуляция касаний: `pointer: coarse` (обязательная проверка)
Многие сайты включают крупные цели нажатия и мобильную раскладку только при `@media (pointer: coarse)` / `(hover: none)`. Окно шириной телефона без эмуляции касаний показывает **десктопную** раскладку — измерения на нём дают ложные находки («кнопка 15×12 px»).
- Каждое устройство, открытое через `openDevice` (`run`, `occlusion.js`, `reachability.js`, `targets.js`, `shot.js --device`), получает проверку `matchMedia('(pointer: coarse)')`; результат — поле `media`: `pointerCoarse`, `hoverNone`, `maxTouchPoints`, `expectsTouch`, `touchValid`, `warning`. Если у телефона касания не включились, Chromium получает `Emulation.setEmulatedMedia` (`forced: true`).
- `touchValid: false` → измерения целей нажатия и «мобильной» вёрстки на этой конфигурации **недействительны** (чек-лист `responsive-cross-browser.md` → `rsp.touch-emulation`).
- Быстрая проверка: `node <SKILL_DIR>/scripts/node/device_context.js media --devices pixel7,iphone15,412x915@mobile`.
- В браузере пользователя по CDP вкладку не эмулировать (размер окна не включает касаний, а эмуляция остаётся на вкладке): `--cdp <URL> --device pixel7` открывает отдельный эмулированный контекст с тем же входом.

## Режимы входа
| `auth.mode` | Как получить состояние |
|-------------|------------------------|
| `none` | гостевой контекст |
| `test-account` | вход в MCP-потоке, затем `storageState` (`parallelism.md`) |
| `manual` | пользователь входит в окне Playwright MCP |
| **`manual-cdp`** | пользователь уже вошёл в **своём** браузере (Chrome с `--remote-debugging-port=9222`); скил присоединяется по CDP и **ничего не чистит и никуда не переходит** — шаг 4 SKILL.md «очистить cookies/localStorage» в этом режиме не выполняется |

```bash
# состояние из браузера пользователя: только cookie allowed_domains, localStorage/sessionStorage открытых вкладок сайта
node <SKILL_DIR>/scripts/node/device_context.js state --cdp http://127.0.0.1:9222 \
  --rules <RUN_DIR>/rules.json --out <RUN_DIR>/logs/auth-state.json
# один сценарий — список устройств, строго последовательно; --delete-state удаляет файл и при ошибке
node <SKILL_DIR>/scripts/node/device_context.js run --devices pixel7,iphone15,ipad,pixel7-landscape \
  --url https://example.com/ --state <RUN_DIR>/logs/auth-state.json --scenario scenario.js \
  --rules <RUN_DIR>/rules.json --out <RUN_DIR>/raw/devices.json
# удалить файл состояния (перезапись и удаление) — в конце прогона или сразу после последнего использования
node <SKILL_DIR>/scripts/node/device_context.js state-rm --out <RUN_DIR>/logs/auth-state.json
```
Вместо `--state` можно `--cdp URL` — состояние берётся в память на время запуска (тоже только cookie `allowed_domains` из `--rules`). `scenario.js`: `module.exports = async ({ page, guarded, device, context }) => ({ … })` — действия через `guarded` (правила безопасности). Без сценария — заголовок, размеры окна и горизонтальное переполнение.

**`state` — что выгружается и как хранится:**
| Что | Как |
|-----|-----|
| Фильтр доменов | обязателен: `--rules rules.json` / `--config run-config.yaml` (`site.allowed_domains`) / `--domains example.com,*.example.com`; без него команда отказывает. Cookie других сайтов (почта, поиск, соцсети) не попадают в файл — в выводе только их число (`dropped`), не имена доменов |
| Cookie домена-родителя | `.example.com` сохраняется, если разрешён `app.example.com` (браузер отправляет её поддомену) |
| localStorage, sessionStorage | из **открытых вкладок** сайта в браузере пользователя (по CDP Playwright не видит `origins` — раньше было `origins: 0`); нет вкладки — предупреждение в `warnings`. sessionStorage переносится в эмулированный контекст скриптом при загрузке страницы |
| Файл | права 600 с момента создания, запись атомарно (временный файл → переименование; при ошибке временный файл удаляется), значения не печатаются |
| Удаление | `state-rm` (перезапись нулями и удаление), `run --delete-state` (после прогона и при ошибке/прерывании), шаг 11 SKILL.md |

`auth-state.json` — секрет: не печатать, не коммитить, не прикладывать к issues и **не передавать исполнителям содержимое** (только путь к файлу, если исполнитель запускает скрипт сам); удалить сразу после использования и в конце прогона.

API: `openDevice({ device, browser, cdp, storageState, rules, logFile, locale, readOnly })` → `{ browser, context, page, device, media, close }` (`locale` — язык контекста и `Accept-Language`); `attachCdp(cdpUrl, pageMatch)` — вкладка пользователя как есть; `configsFrom({ sizes, devices })` — для `--sizes/--device` детекторов.

## Параллельность
Сессия входа общая → устройства в `run` идут по очереди. Правила — `parallelism.md` «Когда параллельные потоки запрещены».
