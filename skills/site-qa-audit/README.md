# site-qa-audit

Полный QA-аудит любого сайта через браузер — без макета и исходного кода. Скил проходит сайт как пользователь и как инструменты (axe, Lighthouse, анализ заголовков и ссылок), сверяет находки с issues в указанных GitHub-репозиториях и публикует результаты по заданным правилам — или складывает черновики (dry-run).

Внутри скила нет конкретных сайтов, репозиториев, логинов и токенов: всё передаётся на входе.

## Что проверяется
| Направление | Кратко |
|-------------|--------|
| `functional` | клики, ссылки (битые, 404), формы (без отправки людям), поиск, фильтры, интерактивные компоненты и карты, ошибки JS, ответы 4xx/5xx |
| `logic-state` | «Назад», обновление, состояние в URL и deep-link, localStorage/cookies, тупики, двойные клики, прерывания, граничный ввод, гонки |
| `ux` | задачи глазами персон, 10 эвристик Нильсена, законы UX, шаги до цели, понятность текстов, обратная связь |
| `visual-ui` | палитра, контраст, тач-зоны ≥ 44×44, типографика, отступы, сетка, состояния, темы, иконки |
| `responsive-cross-browser` | 360–1920 px, Chromium/Firefox/WebKit, ориентация, жесты |
| `accessibility` | WCAG 2.2 AA, axe-core, клавиатура, фокус, alt, ARIA, заголовки, язык |
| `performance` | Lighthouse mobile/desktop, Core Web Vitals, вес, кэш, сжатие, lazy-loading |
| `seo-content` | title, description, OG, canonical, robots, sitemap, hreflang, опечатки, перевод, ошибки в данных |
| `security-passive` | HTTPS, HSTS, CSP и др. заголовки, mixed content, утечки, sourcemaps — **только пассивно** |
| `product` | user stories с критериями приёмки, предложения, редизайн с приоритетом эффект/усилия |

## Входные параметры (опрос)
Если параметр не передан в запросе, скил спросит его с вариантами ответа (подробно — `references/intake.md`).

| # | Параметр | По умолчанию |
|---|----------|--------------|
| 1 | Стартовые URL | — (обязательно) |
| 2 | Разрешённые домены для навигации | домен сайта и поддомены; сторонние ресурсы (CDN, тайлы, API, шрифты) грузятся, переходы на чужие страницы — нет |
| 3 | Авторизация: нет / тестовый аккаунт (env) / ручной вход | нет |
| 4 | Охват: весь сайт / раздел / список URL / текущий экран | весь сайт |
| 5 | Направления | все |
| 6 | Глубина: smoke / standard / deep | standard (лимит страниц 50) |
| 7 | Устройства и браузеры | по глубине (`references/depth-matrix.md`) |
| 8 | Репозитории: URL, роли (`check`, `write-new`, `copies`, `comment`), стиль, метки, подтверждение, скриншоты | нет |
| 9 | Запреты пользователя (свободный текст + чек-лист) | только базовые |
| 10 | Плагины: все установленные / выбрать / только свои чек-листы | все установленные |
| 11 | Язык отчётов и issues | русский |
| 12 | Параллельные браузерные потоки | 2 (через playwright-cli) |
| 13 | Режим: dry-run / боевой | dry-run |

Результаты — в `./qa-runs/<YYYY-MM-DD>-<host>/` текущей рабочей папки: `run-config.yaml`, `findings.json`, `report.md`, `screenshots/`, `drafts/`, `raw/`, `logs/`.

## Примеры вызова
```text
/site-qa-audit
Протестируй сайт https://example.com — smoke, только functional и accessibility, без репозиториев.
QA-аудит https://shop.example.com, глубоко, сверить с owner/shop (только сверка) и записать копии всех находок
в owner/qa-notes. Ничего не покупать, не трогать раздел профиля. Dry-run.
Проверь удобство сайта https://app.example.com, вход тестовым аккаунтом из QA_USER / QA_PASS.
Find bugs on https://example.org, standard depth, English report.
```

## Базовые запреты (всегда)
Не покупать, не платить, не подписываться, не донатить; не подтверждать OAuth/вход через внешние аккаунты; не удалять данные и аккаунты, не менять настройки боевого аккаунта; не отправлять формы реальным людям без разрешения на каждую; не принимать соглашения и не обходить капчу; никакой нагрузки, перебора, сканеров и инъекций; паузы между действиями; маскирование секретов и персональных данных. Подробно — `references/safety-rules.md`; проверка — `scripts/url_guard.py`.

## Статусы сверки с issues
`NEW`, `DUPLICATE-OPEN`, `FIXED-OK`, `FIXED-INSUFFICIENT`, `REGRESSION`, `ALREADY-COPIED`, `UNSURE-MATCH` (спросит). В каждом созданном issue — скрытый маркер `<!-- site-qa-audit:fp=… -->`, поэтому повторный прогон не создаёт дублей.

## Зависимости
| Обязательно | Как поставить |
|-------------|---------------|
| git, Node.js ≥ 18, npm/npx, Python 3 | системно |
| Playwright MCP | `/plugin install playwright@claude-plugins-official` |
| playwright, @axe-core/playwright, lighthouse | `cd scripts/node && npm install` (локально) |
| Браузеры Playwright | `cd scripts/node && npx playwright install chromium webkit firefox` |
| gh CLI (для репозиториев) | https://cli.github.com, `gh auth login` |

| Желательно | Зачем |
|------------|-------|
| `@playwright/cli` (`npm i -g @playwright/cli@latest`) | параллельные изолированные браузерные потоки |
| Claude in Chrome | режим «текущий экран» во вкладке пользователя |
| Скилы/плагины: ux-audit (jezweb/claude-skills), e2e-test и ux-test (coderphonui/opentest), qa-skills (neonwatty), ux-heuristics, laws-of-ux, ux-design-principles, ui-audit-redesign (alpham8/agentic-webdev), frontend-design (Anthropic) | усиливают направления, см. `references/plugins-map.md` |

`scripts/check_env.sh` (`.ps1`) проверяет всё это при каждом запуске и показывает таблицу.

## Ограничения
- Только то, что видно через браузер: причина дефекта — гипотеза, код не анализируется.
- Playwright MCP нельзя делить между параллельными субагентами; параллельный браузер — только через `playwright-cli`.
- `--allowed-origins`/`--blocked-origins` Playwright MCP — не граница безопасности; основная защита — проверка `url_guard` перед каждым действием. Она не заменяет здравый смысл исполнителя.
- Капча, 2FA, вход через внешние аккаунты — только ручной вход пользователя.
- gh не прикладывает картинки к issue: скриншоты коммитятся в репозиторий или остаются локально.
- Firefox может не запускаться в некоторых окружениях (см. `references/environment-notes.md`) — тогда помечается «не проверено».
- Безопасность — только пассивная; это не пентест.

## Структура
```text
SKILL.md                порядок работы
references/             setup, intake, safety-rules, depth-matrix, parallelism, plugins-map,
                        repo-sync, severity, environment-notes, checklists/ (10 направлений)
templates/              run-config.example.yaml, finding.schema.json, issue-detailed.md,
                        issue-comment.md, user-story.md, run-report.md
scripts/                check_env, url_guard, fetch_issues, read_templates, fingerprint, render_draft,
                        node/ (a11y, lighthouse, headers, links, probe), shared/ (вендоренные модули)
tests/                  сценарии самопроверки
```
