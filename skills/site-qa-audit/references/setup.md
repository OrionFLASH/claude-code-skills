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
| Claude in Chrome | нет | расширение «Claude» (Anthropic) в Google Chrome + `/chrome`; без него режим «текущий экран» — через Playwright |
| Плагины-усилители | нет | работа по собственным чек-листам |

Проверка браузеров — реальный запуск (`node/probe.js`), а не поиск файлов.

## Поведение
- FAIL в обязательном → показать таблицу, предложить команду исправления, **глобальные установки — только после подтверждения пользователя** (одним списком).
- Установка MCP/плагина требует перезапуска Claude Code → сказать об этом и остановиться до «продолжай».
- WARN → продолжать, записать ограничение в отчёт («Firefox не проверялся: …»).
- `env.json` → источник списка реально доступных усилителей (`enhancers`) и запрещённых (`banned`) для `plugins-map.md`.

## Режим «текущий экран»
- Есть Claude in Chrome (`claude_in_chrome: true` и инструменты `mcp__claude-in-chrome__*` в сессии) → сначала загрузить скил `claude-in-chrome`, работать во вкладке пользователя; **только чтение и навигация в пределах правил**; никаких действий от имени пользователя на боевом аккаунте без подтверждения каждого.
- Нет → спросить URL текущего экрана и открыть его в Playwright (если нужен вход — режим ручного входа).
