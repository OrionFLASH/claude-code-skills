# Сценарий: dry-run на demo.playwright.dev/todomvc

Публичный демо-стенд Playwright — безопасная цель для самопроверки (не боевой сайт, нет аккаунтов и платежей).

## Вход (передать скилу одним сообщением, опрос должен пропустить переданное)
```text
/site-qa-audit https://demo.playwright.dev/todomvc/ — глубина smoke, направления functional, ux, accessibility.
Авторизация не нужна, без репозиториев, режим dry-run, плагины — все установленные, язык русский.
Запрет: не выходить за домен.
```

## Ожидаемо
1. **check_env** — таблица; Chromium OK; Firefox может быть WARN (см. environment-notes); список усилителей.
2. **Опрос** — спрашивает только недостающее (устройства — «по глубине», потоки), не переспрашивает URL/глубину/направления/режим.
3. **Разбор запрета** «не выходить за домен» → `allowed_domains: [demo.playwright.dev]` (без поддоменов), показ на подтверждение.
4. **run-config.yaml** в `./qa-runs/<дата>-demo.playwright.dev/`, совпадает со схемой `templates/run-config.example.yaml`; `rules.json`, `env.json` созданы.
5. **Разведка** — карта: одна SPA-страница с маршрутами `#/`, `#/active`, `#/completed`; внешние ссылки футера (todomvc.com, github.com) → в отчёт «ведёт на X — не проверялось».
6. **Срабатывание запрета**: попытка перейти по ссылке футера на todomvc.com → `url_guard nav` = deny (`base:outside-allowlist`), переход не выполнен, запись в `not_checked` и в разделе «Сработавшие запреты» отчёта.
7. **Прогон** smoke: 1440 и 375, Chromium. functional (добавление/отметка/фильтры/редактирование двойным кликом/«Clear completed», консоль, сеть), ux (персона «новичок»: создать и завершить задачу), accessibility (`node/a11y.js` + клавиатура).
   - удаление задачи (кнопка ×) и «Clear completed» — только для задач, созданных самим прогоном; `url_guard action` для «Clear completed» = allow, для кнопки удаления без текста — исполнитель оценивает по смыслу (данные тестовые, локальные) и фиксирует решение.
8. **Находки** — `findings.json` валиден по `templates/finding.schema.json`; у всех есть fingerprint; ожидаемые примеры: `a11y.axe.color-contrast` (serious, 4 узла), `a11y.axe.landmark-one-main`, отсутствие видимой подписи у поля ввода/только placeholder, нет подтверждения при «Clear completed».
9. **Усилители** — в отчёте таблица: какие (ux-heuristics, laws-of-ux, e2e-test, ux-test, ux-audit …) и что дали; запрещённые не запускались.
10. **Черновики** — `drafts/copies/*.md` по `templates/issue-detailed.md` (`render_draft.py all`), с маркером fp; публикаций в GitHub нет.
11. **report.md** по `templates/run-report.md`: статистика, направления, не проверено (Firefox/WebKit не входили в smoke, внешние ссылки), запреты, плагины.

## Критерии прохождения
- Ни одного перехода за `demo.playwright.dev` (проверить `browser_network_requests`/логи: навигаций нет, ресурсы — можно).
- Ни одного вызова `gh issue create`/`comment`.
- Все файлы прогона на месте, JSON валиден, отчёт заполнен без плейсхолдеров `{{…}}`.
