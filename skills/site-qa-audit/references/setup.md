# Проверка окружения при каждом запуске

## Команда
```bash
<SKILL_DIR>/scripts/check_env.sh --json <RUN_DIR>/env.json          # macOS/Linux
pwsh <SKILL_DIR>/scripts/check_env.ps1 --json <RUN_DIR>/env.json    # Windows
```
`<SKILL_DIR>` — папка этого скила (где лежит SKILL.md). До опроса папки прогона ещё нет — тогда без `--json`, а после создания папки повторить с `--fast --no-browsers --json` (быстро).
Если Bash работает в песочнице и запуск браузеров падает — повторить вне песочницы (см. environment-notes.md).

## Что проверяется
| Компонент | Обязательно | Если нет |
|-----------|-------------|----------|
| git, Node.js ≥ 18, npm, npx, Python 3 | да | установить; скил не стартует |
| gh + авторизация (scope `repo` или `public_repo`) | только при работе с репозиториями | `gh auth login` / `gh auth refresh -s repo` |
| Playwright MCP | да | `/plugin install playwright@claude-plugins-official` или `claude mcp add --transport stdio --scope user playwright -- npx -y @playwright/mcp@latest`; нужен перезапуск Claude Code |
| node-зависимости в `scripts/node` | да | `cd <SKILL_DIR>/scripts/node && npm install` (локально) |
| Браузеры Chromium / WebKit / Firefox | Chromium — да | `cd <SKILL_DIR>/scripts/node && npx playwright install <browser>`; не запускающийся браузер → «не проверено» в отчёте |
| playwright-cli | нет | `npm i -g @playwright/cli@latest`; без него браузерный поток один |
| Claude in Chrome | нет | расширение «Claude» (Anthropic) в Google Chrome + перезапуск `claude --chrome` (или `/chrome`); native host есть, а инструментов в сессии нет → перезапустить сессию с `--chrome`; без него режим «текущий экран» — через Playwright |
| Плагины-усилители | нет | работа по собственным чек-листам |
| `SITE_QA_OUTPUT_DIR` | нет | папка результатов по умолчанию; без неё скил спросит (`intake.md` → «Папка прогона») |

Проверка браузеров — реальный запуск (`node/probe.js`), а не поиск файлов.

**Какие браузерные инструменты доступны в этой сессии.** «Playwright MCP: OK» означает только, что он настроен. Чтобы увидеть, что можно вызвать сейчас, агент передаёт имена своих инструментов:
```bash
<SKILL_DIR>/scripts/check_env.sh --browser-tools-only --session-tools "mcp__plugin_playwright_playwright__browser_navigate,mcp__plugin_playwright_playwright__browser_run_code_unsafe"
```
Раздел «Браузерные инструменты»: Playwright MCP и Claude in Chrome (есть ли в сессии, каких ключевых инструментов нет; без `browser_run_code_unsafe` не работают `nav_lock.js` и `snap_mcp.js`), playwright-cli, браузер с отладочным портом на localhost (`--cdp-ports 9222`, для `auth: manual-cdp`). Последняя строка — «Доступно в этой сессии: …». В `env.json` — ключ `browser_tools`.

## Поведение
- FAIL в обязательном → показать таблицу, предложить команду исправления, **глобальные установки — только после подтверждения пользователя** (одним списком).
- Установка MCP/плагина требует перезапуска Claude Code → сказать об этом и остановиться до «продолжай».
- WARN → продолжать, записать ограничение в отчёт («Firefox не проверялся: …»).
- `env.json` → источник списка реально доступных усилителей (`enhancers`) и запрещённых (`banned`) для `plugins-map.md`.

## Режим «текущий экран»
- Есть Claude in Chrome (`claude_in_chrome: true` и инструменты `mcp__claude-in-chrome__*` в сессии) → сначала загрузить скил `claude-in-chrome`, `tabs_context_mcp`, работать в своей вкладке группы MCP (вкладку пользователя — только если он явно попросил); консоль — `read_console_messages` с первого вызова, затем перезагрузка; **только чтение и навигация в пределах правил**; никаких действий от имени пользователя на боевом аккаунте без подтверждения каждого.
- Нет → спросить URL текущего экрана и открыть его в Playwright (если нужен вход — режим ручного входа).
