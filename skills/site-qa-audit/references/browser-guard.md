# Правила безопасности в браузерных действиях: `guard.js`

`url_guard.py` оценивает строку. Когда исполнитель работает с Playwright напрямую (CDP, node-скрипты, `setup.js` для `shot.js`), правила применяет `scripts/node/guard.js` — автоматически, перед каждым действием. Для Playwright MCP по-прежнему: `url_guard.py` вручную + `nav_lock.js` (`safety-rules.md` §3).

## Что подключить
```bash
python3 <SKILL_DIR>/scripts/url_guard.py export --config <RUN_DIR>/run-config.yaml --out <RUN_DIR>/rules.json
```
```js
const { loadGuardRules, guardContext, guardedPage } = require('<SKILL_DIR>/scripts/node/guard.js');
const rules = loadGuardRules('<RUN_DIR>/rules.json');
await guardContext(context, rules, { logFile: '<RUN_DIR>/logs/blocked.jsonl' });
const g = guardedPage(page, rules, { logFile: '<RUN_DIR>/logs/blocked.jsonl' });
await g.goto('https://example.com/');
await g.click('text=Поддержать');   // deny → не нажато, событие в blocked.jsonl
```
Все node-скрипты скила (`occlusion.js`, `reachability.js`, `shot.js`, `device_context.js run`, `invariants.js`) принимают `--rules rules.json` и `--log blocked.jsonl` и подключают guard сами.

## `guardContext(context, rules, opts)` — уровень контекста
| Что | Как |
|-----|-----|
| Ресурсы с `forbidden_domains` и базовых `blocked_origins` | `context.route` → `abort('blockedbyclient')`, событие `resource` |
| Навигация главного фрейма за пределы правил (`allowed_domains`, `forbidden_url_patterns`, `exclude_patterns`, базовые хосты входа/оплаты и пути `/checkout`, `/oauth/authorize`…) | abort на уровне route, событие `nav` — даже если исполнитель вызвал «голый» `page.goto` |
| Документ iframe | блокируется только при явном запрете (запрещённый домен, путь, базовый хост); внешние встроенные приложения разрешены |
| Новые вкладки и popup (`window.open`, `target=_blank`) на чужой домен | первая навигация блокируется, вкладка закрывается, событие `tab` |
| Нативные диалоги (`confirm`, `beforeunload`) | отклоняются, событие `dialog` |

Опции: `logFile` (JSONL), `log` (массив), `onEvent(ev)`.

## `guardedPage(page, rules, opts)` — уровень действия
Обёртки `click`, `dblclick`, `fill`, `check`, `uncheck`, `selectOption`, `setInputFiles`, `press`, `goto`; цель — селектор (в том числе `iframe#app >>> button`) или Locator.

Перед действием из элемента берутся: роль (явная или неявная), доступное имя (`aria-label`, `aria-labelledby`, `<label>`, `title`, `alt`, `value` у кнопок), видимый текст, контекст (ближайший диалог/форма/раздел: заголовок и до 300 символов текста, заголовок страницы), адрес ссылки. Решение принимает **тот же код**, что `url_guard.py action` (мост `python3 -c` к `url_guard.check_action`; правила из `rules.json`). Ссылка дополнительно проверяется как переход (`nav`).

| Решение | Что происходит |
|---------|----------------|
| allow | действие выполняется |
| deny | действие пропускается, событие в `blocked.jsonl`, возвращается `{performed: false, decision: 'deny', rule, reason}` |
| confirm | действие не выполняется; бросается `GuardConfirmError` с `question` — вопрос пользователю (или `{performed:false, question}` при `confirmMode: 'return'`). `opts.onConfirm(ev)` → `true` разрешает один раз |

Особенности:
- `fill` и `press` (кроме Enter) — ввод не отправляет данные, поэтому confirm-категории (`send-to-people`, `destructive`) снимаются; deny действует.
- Цель из `side_effects` (`opts.sideEffects`, см. `side-effects.md`) в обход `invariants.js` → confirm с правилом `side_effect:<id>`.
- `goto`: проверка до перехода и после редиректа (`safety-rules.md` §3.5); за пределами правил — назад.
- `throttleMs` (по умолчанию `throttle_ms` из `rules.json`) — пауза перед каждым действием.
- **Fail closed.** Мост недоступен (нет Python, нет `url_guard.py`, ошибка правил, неверный ответ) → решение `unavailable` с правилом `guard:unavailable`, событие в `blocked.jsonl` и `GuardUnavailableError` (`exitCode` 4): действие и переход **не выполняются**, сценарий останавливается. `--rules` с несуществующим или битым файлом — тоже код 4 (а не «правил нет»). Ошибка в обработчике маршрута для навигации — переход обрывается. Скрипты скила завершаются с кодом 4; исполнитель при коде 4 останавливается (`safety-rules.md` §3 п. 0).
- **Только чтение** (`safety-rules.md` §3.13): `guardContext(context, rules, { readOnly: true })` пропускает переход на страницы покупки/доната и `rules.read_only_urls`, обрывает запросы кроме GET/HEAD/OPTIONS; `guardedPage(page, rules, { readOnly: true })` — `goto` разрешён (событие `read-only` «прочитано без действий»), любое действие — deny `read-only`.

## Журнал `blocked.jsonl`
Одна строка — одно событие: `{ts, type: resource|nav|subframe|tab|redirect|dialog|action, decision, rule, reason, url, element?, question?}`. Переносится в отчёт в раздел «Сработавшие запреты».

## Ручная проверка элемента
```bash
node <SKILL_DIR>/scripts/node/guard.js check --url https://example.com/ --selector "text=Поддержать" --rules <RUN_DIR>/rules.json
# код 0 allow, 2 confirm, 3 deny, 4 guard недоступен (стоп); JSON: роль, имя, контекст, решение
```

## Ограничения
- Guard не видит смысла иконки без доступного имени: правило «по смыслу» из `safety-rules.md` §1 остаётся за исполнителем.
- В режиме `--cdp` без устройства (`shot.js`, `occlusion.js`) route на браузер пользователя не ставится — действуют только обёртки `guardedPage` (действия `setup.js`). Переходы вне скрипта пользователь делает сам.
- Блокировка `pushState`/`window.open` внутри SPA — задача `nav_lock.js` (MCP) или `opts` охвата; guard блокирует сетевую навигацию и вкладки.
