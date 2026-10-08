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

Также принимаются `WxH` (только окно) и любое имя из `playwright.devices`. Устройства Apple по умолчанию запускаются **отдельным WebKit**; `--browser chromium` — эмуляция в Chromium (нужна для `reachability.js`: в мобильном WebKit нет колеса и CDP-жестов).

## Режимы входа
| `auth.mode` | Как получить состояние |
|-------------|------------------------|
| `none` | гостевой контекст |
| `test-account` | вход в MCP-потоке, затем `storageState` (`parallelism.md`) |
| `manual` | пользователь входит в окне Playwright MCP |
| **`manual-cdp`** | пользователь уже вошёл в **своём** браузере (Chrome с `--remote-debugging-port=9222`); скил присоединяется по CDP и **ничего не чистит и никуда не переходит** — шаг 4 SKILL.md «очистить cookies/localStorage» в этом режиме не выполняется |

```bash
# состояние из браузера пользователя (только счётчики в выводе, файл с правами 600)
node <SKILL_DIR>/scripts/node/device_context.js state --cdp http://127.0.0.1:9222 --out <RUN_DIR>/logs/auth-state.json
# один сценарий — список устройств, строго последовательно
node <SKILL_DIR>/scripts/node/device_context.js run --devices pixel7,iphone15,ipad,pixel7-landscape \
  --url https://example.com/ --state <RUN_DIR>/logs/auth-state.json --scenario scenario.js \
  --rules <RUN_DIR>/rules.json --out <RUN_DIR>/raw/devices.json
```
Вместо `--state` можно `--cdp URL` — состояние берётся в память на время запуска. `scenario.js`: `module.exports = async ({ page, guarded, device, context }) => ({ … })` — действия через `guarded` (правила безопасности). Без сценария — заголовок, размеры окна и горизонтальное переполнение.

`auth-state.json` — секрет: не печатать, не коммитить, не прикладывать к issues; удалить в конце прогона.

API: `openDevice({ device, browser, cdp, storageState, rules, logFile })` → `{ browser, context, page, device, close }`; `attachCdp(cdpUrl, pageMatch)` — вкладка пользователя как есть; `configsFrom({ sizes, devices })` — для `--sizes/--device` детекторов.

## Параллельность
Сессия входа общая → устройства в `run` идут по очереди. Правила — `parallelism.md` «Когда параллельные потоки запрещены».
