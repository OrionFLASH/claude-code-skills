# Деление работы между исполнителями

Основано на опыте из `environment-notes.md`: **Playwright MCP нельзя делить между параллельными субагентами** — у них общая «текущая вкладка». Изолированные сессии `playwright-cli -s=<имя>` параллелятся надёжно.

## Типы потоков
| Поток | Инструмент | Параллельно? | Кто |
|-------|-----------|--------------|-----|
| MCP-поток | Playwright MCP | **один**, последовательно | оркестратор (главный агент) |
| CLI-потоки | `playwright-cli -s=qa-<id>` (headless, in-memory профиль) | да, до `parallel.max_workers` | субагенты |
| Скриптовые | `node scripts/node/*.js`, `gh`, Python | да (фоновые процессы Bash) | оркестратор |

Нет `playwright-cli` → все браузерные направления в MCP-потоке последовательно; скриптовые — по-прежнему параллельно.

## План по умолчанию
1. **Сразу после разведки, в фоне** (скриптовые, параллельно):
   - `links.js` (карта, битые ссылки, SEO-мета) — для functional и seo-content;
   - `headers.js` по списку страниц — security-passive, performance (кэш/сжатие), seo (robots/sitemap);
   - `a11y.js` — accessibility (по одному процессу на браузер);
   - `lighthouse.js` — performance (последовательно внутри: один Chrome);
   - синхронизация issues (`fetch_issues.py sync`) — если ещё не сделана.
2. **MCP-поток (оркестратор)**: functional, logic-state — сценарии с состоянием, где важна наблюдаемость консоли и сети (`browser_console_messages`, `browser_network_requests`).
3. **CLI-потоки (субагенты)** — направления, независимые от состояния:
   - `qa-ux`: ux + product (наблюдения);
   - `qa-visual`: visual-ui + responsive-cross-browser (ширины, WebKit/Firefox — `playwright-cli open --browser webkit`);
   - `qa-a11y-kbd`: клавиатура и фокус (то, чего нет в axe).
   При `max_workers = 2` — объединять попарно; при 1 — всё в MCP-потоке.
4. **Сведение**: оркестратор собирает `raw/*.json` и находки субагентов → `findings.json` → `fingerprint.py compute` → `dedupe`.

Авторизация в CLI-потоках: вход выполняется один раз в MCP-потоке (тестовый аккаунт или ручной вход пользователя в видимом окне). Затем оркестратор получает состояние `browser_run_code_unsafe` с кодом `async (page) => JSON.stringify(await page.context().storageState())` (включает httpOnly-cookies; `browser_evaluate` их не видит), сохраняет в `<RUN_DIR>/logs/auth-state.json`, а потоки делают `playwright-cli -s=<id> state-load <файл>`. Файл состояния — секрет: не печатать, не коммитить, удалить в конце прогона. Если сайт привязывает сессию к устройству и state-load не работает — авторизованные проверки только в MCP-потоке.

## Задание субагенту (шаблон)
```text
Ты — исполнитель site-qa-audit, поток <qa-id>, направления: <list>.
Браузер: ТОЛЬКО `playwright-cli -s=<qa-id> …` (Bash). Playwright MCP НЕ использовать.
Конфиг: <RUN_DIR>/run-config.yaml. Страницы: <list or file>. Ширины/браузеры: <…>.
Чек-листы: <SKILL_DIR>/references/checklists/<direction>.md — раздел(ы) <Smoke|Standard|Deep>.
Усилители (методики): <skills from plugins-map> — используй как источник проверок, действия выполняй сам под правилами.
<БЛОК ПРАВИЛ из safety-rules.md §4, дословно, с RULES_TABLE>
Выход: <RUN_DIR>/raw/findings-<qa-id>.json — массив находок по templates/finding.schema.json
(без id и fingerprint — их проставит оркестратор), скриншоты в <RUN_DIR>/screenshots/<qa-id>-*.png,
заметки «не проверено» — в поле not_checked файла. Вопросы (confirm-действия, «баг или задумано») — не решай сам,
верни списком questions в конце файла. В конце закрой сессию: playwright-cli -s=<qa-id> close.
```

## Темп и нагрузка на сайт
- Суммарно не больше `max_workers + 2` одновременных клиентов к сайту.
- `throttle_ms` между действиями в каждом потоке; node-скрипты — `--throttle`.
- Сайт отвечает 429/503 → остановить все потоки, увеличить паузы вдвое, сообщить пользователю.
