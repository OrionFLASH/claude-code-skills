# Инструменты: проверка, установка, замены

## Проверка в начале каждого прогона
```bash
python3 <SKILL_DIR>/scripts/check_env.py --out <OUT> --json <OUT>/build/env.json --session-skills "<скиллы из списка сессии через запятую>"
python3 <SKILL_DIR>/scripts/check_env.py --plan --out <OUT>      # что поставить самому, что спросить
```
`--session-skills` — имена скиллов из системного списка текущей сессии (например `superpowers:brainstorming,data:analyze,dataviz`): плагины, подключённые не через `installed_plugins.json`, иначе не видны.

## Политика установки (`run-config.tools.install`)
| Что | `local-auto` (по умолчанию) | `ask` | `never` |
|---|---|---|---|
| Node-модули прогона (playwright, pptxgenjs) в `<OUT>/build/node` и Chromium в кэш Playwright: `check_env.py --install-node <OUT>` | ставить без вопроса | спросить | не ставить |
| Python-пакеты (`pip install --user certifi openpyxl`) | спросить | спросить | не ставить |
| Системные (`brew install node gh`, Python) | спросить | спросить | не ставить |
| Плагины и скиллы Claude Code (`claude plugin install …`) | спросить одним вопросом списком | спросить | не ставить |
| Вход в аккаунты (`gh auth login`, ключ TypeSafe) | только пользователь сам | — | — |

Спрашивай **одним** `AskUserQuestion` с мультивыбором: «Не хватает: X (зачем), Y (зачем). Что поставить?» — варианты по компонентам + «Ничего, работать с заменами». Если пользователь в режиме «Work» (без pip, см. его CLAUDE.md) — Python-пакеты не предлагать, все скрипты скилла работают на стандартной библиотеке.

## Карта инструментов по фазам и замены
| Фаза | Основное | Усилители (если есть) | Замена при отсутствии |
|---|---|---|---|
| 0 План | `intake.py`, `init_run.py`, `check_env.py` | `superpowers:brainstorming`, `superpowers:writing-plans` | план по `references/phases.md` |
| 1 Репозиторий | `repo_scan.py`, `issues_export.py` (gh) | Explore-агент для широкого поиска | без gh — Issues пропускаются, отметить в отчёте |
| 2 Приложение | `node/audit_site.mjs` (Playwright) | Claude in Chrome, Playwright MCP, `ux-audit`, `ux-heuristics`, `laws-of-ux`, `cro-audit-and-test-kit:page-audit`/`flow-audit`, `site-qa-audit` | без браузера — по коду, README и скриншотам из репозитория; уверенность ниже |
| 3–4 Рынок | WebSearch/WebFetch, субагенты по брифам `templates/briefs/research-*.md` | `marketing:competitive-brief`, `product-management:synthesize-research`, `seo-*` (`seo-plan`, `seo-cluster`, `seo-competitor-pages`, `seo-geo`), `node/shoot_competitors.mjs` | без веб-поиска — только известные владельцу конкуренты и общие знания с пометкой `[допущение]`, класс D |
| 5 Реестр | генераторы по `templates/briefs/registry-generator.md`, `merge_proposals.py`, `check_registry.py`, `references/growth-library.md` | `product-management:product-brainstorming`, `marketing-ideas-kit:idea-shortlist`/`idea-ranking` | — |
| 6 Оценка | `score.py`, `validate_scores.py`, `model.py`, `charts.py` | `typesafe_eval.py` (TypeSafe Jev, ключ), `typesafe-triage --batch` для выбора моделей агентов, `data:statistical-analysis`, `data:validate-data`, `marketing-ideas-kit:idea-payback-check` | без ключа TypeSafe — колонка «не оценивалось», методика RICE+ICE+WSJF+чувствительность |
| 7 Стратегия | субагенты `strategy-section.md`, `specs.md`, `experiments.md` | `product-management:write-spec`, `cro-audit-and-test-kit:ab-test-plan`, `churn-prevention-kit:*`, `marketing:campaign-plan` | — |
| 8 Дизайн | HTML-макеты на `mockups/tokens.css`, `node/shoot_mockups.mjs`, `node/measure_hotspots.mjs` | `frontend-design`, `ui-ux-pro-max`, `design-system`, `brand`, `dataviz` | без браузера — HTML-макеты без PNG (страница покажет их во фрейме) |
| 9 Сборка | `build_all.py` → `build_html.py`, `build_xlsx.py`, `build_deck_json.py`, `node/build_pptx.mjs`, `node/deck_pdf.mjs`, `check_links.py`, `node/smoke_html.mjs` | `anthropic-skills:pptx`/`xlsx`/`pdf` (проверка), Artifact (публикация страницы — только по просьбе) | без node — HTML и XLSX (stdlib) всё равно собираются; PPTX/PDF — в отчёт «не собрано» |

Отсутствие усилителя — не ошибка: отметь в отчёте (п. 3 REPORT), какие скиллы применялись, какие отсутствовали и чем заменены. Не выдумывай названия скиллов и не подменяй один другим.

## TypeSafe
- **Выбор моделей субагентов** — `typesafe-triage` (`python3 <путь>/typesafe_triage.py --batch tasks.json`): по таблице `model`/`effort` для каждой подзадачи; `model` у `Agent` — всегда явно.
- **Оценка предложений** — `typesafe_eval.py <OUT>` (ключ только из `TYPESAFE_API_KEY`, не печатать): отдельная колонка и раздел, в composite не смешивается.
