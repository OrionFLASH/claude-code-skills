# Контракт данных product-strategy

Единственный источник правды о том, где что лежит и какой формы. Все скрипты скилла читают и пишут только по этому контракту; субагенты сдают выдачу строго в этих схемах. Изменение схемы — MINOR-версия скилла и правка этого файла в том же коммите.

## Обозначения
- `<SKILL_DIR>` — папка установленного скилла (`python3 <SKILL_DIR>/scripts/skill_dir.py` печатает её).
- `<OUT>` — папка прогона (выбирается в опросе; по умолчанию `<repo>/strategy/<YYYY-MM-DD>/`).
- Все JSON — UTF-8, `ensure_ascii=False`, отступ 2. Даты — ISO `YYYY-MM-DD`. Деньги — объект `{min, max, currency, note}`.
- Метки достоверности чисел в текстах: `[факт: источник, дата]`, `[оценка: метод]`, `[допущение]`.

## Структура `<OUT>`
```
<OUT>/
  build/            run-config.json, STATUS.md, env.json, briefs/*.md, node/ (локальные npm-модули прогона)
  research/         product-understanding.md, ui-inventory.md, repo-scan.md, market.md, communities.md,
                    methodology.md, strategy.md, specs/*.md, experiments/*.md, questions-owner.md, glossary.md
  data/             все JSON/CSV по схемам ниже
  charts/           *.svg (генерирует charts.py), charts-index.json
  mockups/          tokens.css, current/*.png (скриншоты факта), concepts/*.html + *.png (макеты)
  design-refs/      NN-slug.md + NN-slug.json + NN-slug.png, README.md
  competitors/      shots/*.png (скриншоты конкурентов)
  deliverables/     index.html (+ assets/, data/ в режиме site — по умолчанию), strategy.xlsx, strategy.pptx, strategy.pdf, REPORT.md, README.md
```

## build/run-config.json (пишет `intake.py`)
```json
{
  "version": 1,
  "created": "2026-10-10",
  "author": {"name": "", "nick": "", "copyright": ""},
  "repo": {"path": "/abs/path", "name": "repo", "remote": "owner/repo|null", "analyze": true},
  "product": {"name": "", "url": "", "local_run": "auto|command|none", "run_command": "", "type": "auto|saas|consumer|devtool|oss|content|game|bot|mobile|desktop|other", "known_facts": ""},
  "strategy": {"kind": "growth|gtm|monetization|tech-roadmap|oss-community|full", "goal": "", "depth": "quick|standard|deep|exhaustive",
               "proposals_min": 100, "horizon_months": 12, "vision_years": 3, "markets": ["ru", "en"],
               "budget": {"variants": ["zero", "small", "medium"], "note": ""}, "paid_tier": "auto|yes|no", "constraints": "",
               "categories_na": ["localization"]},
  "scope": {"repo_analysis": true, "app_run": true, "competitors": true, "competitors_min": 10, "communities": true, "keywords": true,
            "events": true, "legal": true, "issues": true, "design_mockups": true, "mockups_min": 12, "design_refs": true,
            "unit_economics": true, "experiments": 8, "specs_top": 10, "kanban_cards": 40},
  "sources": {"repo": true, "issues": true, "web_search": true, "web_search_budget_per_hour": 100, "analytics_exports": [],
              "owner_docs": [], "competitor_list": [], "other": ""},
  "formats": {"html": true, "xlsx": true, "pptx": true, "pdf": true, "md": true},
  "tools": {"typesafe": "auto|on|off", "browser": "auto|playwright|chrome|none", "subagents": true, "max_parallel_agents": 5,
            "install": "local-auto|ask|never"},
  "output": {"dir": "/abs/<OUT>", "inside_repo": true, "git_branch": "docs/strategy-YYYY-MM-DD"},
  "language": "ru",
  "autopilot": false,
  "assumptions": []
}
```

## data/repo-scan.json (пишет `repo_scan.py`)
```json
{
  "repo": {"name": "", "path": "", "remote": null, "default_branch": "", "license": ""},
  "stack": {"languages": {"Python": 12345}, "frameworks": ["react"], "package_managers": ["npm"], "manifests": ["package.json"]},
  "entrypoints": [{"kind": "web|cli|api|mobile|desktop|lib|bot", "file": "", "line": 1, "note": ""}],
  "routes": [{"path": "/pricing", "file": "", "line": 1}],
  "features": [{"name": "", "evidence": [{"file": "", "line": 1}], "ui_visible": "yes|no|unknown"}],
  "i18n": {"locales": ["ru", "en"], "files": []},
  "integrations": {"analytics": [], "payments": [], "auth": [], "ads": [], "crash": [], "feature_flags": []},
  "quality": {"tests": {"files": 0, "frameworks": []}, "ci": [], "lint": [], "docker": false},
  "docs": {"readme": "", "changelog": "", "docs_dirs": []},
  "git": {"commits": 0, "first": "", "last": "", "authors": 0, "commits_90d": 0, "tags": [], "monthly": {"2026-09": 12}},
  "todo_markers": 0,
  "secrets_skipped": ["имена файлов, которые не читались"],
  "notes": []
}
```

## data/proposals.json — реестр (список объектов)
Черновики генераторов: `data/proposals-draft-<group>.json` той же схемы с `id` вида `<group>-NN`. После `merge_proposals.py` — `P001…` и поле `merged_from`.
```json
{
  "id": "P001",
  "title": "Короткое название (до 90 знаков)",
  "category": "product|acquisition|conversion|retention|monetization|analytics|partnerships|localization|new_lines|platform",
  "segment": "кому (аудитория/рынок)",
  "description": "что именно сделать",
  "rationale": "почему это сработает",
  "evidence": [{"kind": "competitor|community|issue|docs|repo|research|analytics|own_app", "url": "https://… или null", "file": "path:line или null",
                "title": "", "note": "цитата < 15 слов или пересказ", "checked": "2026-10-10"}],
  "evidence_class": "A|B|C|D",
  "current_feature": "что есть сейчас (файл/скриншот) или «нет»",
  "effect_kpi": [{"kpi": "D30 retention", "direction": "up", "range": "+1..3 п.п.", "label": "оценка"}],
  "steps": [{"what": "", "where": "", "how": "", "doc_url": "https://… или null"}],
  "dependencies": ["P007"],
  "effort_days": [3, 8],
  "cost_money": {"min": 0, "max": 500, "currency": "USD", "note": ""},
  "risks": {"legal": 1, "ip": 1, "platform": 1, "privacy": 1, "tech": 2, "reputation": 1, "note": ""},
  "time_to_first_result_days": 14,
  "cheap_test": "как проверить дёшево",
  "scores": {"value": 4, "cost": 2, "risk": 2, "confidence": 3,
             "reach": 3, "impact": 4, "acquisition": 3, "activation": 2, "conversion": 2, "retention": 3, "revenue": 2,
             "virality": 2, "seo": 1, "trust": 3, "moat": 2, "fit": 4, "demand": 3, "season": 3},
  "kano": "must|linear|delight|indifferent",
  "horizon": "now|next|later|vision",
  "horizon_years": 0,
  "tags": [],
  "mockup": "concepts/<key>.html или null",
  "source_group": "G1",
  "merged_from": ["G1-03", "G4-11"]
}
```
Необязательные поля шкал для формулы уверенности: `scores.testability` (1–5, можно ли дёшево проверить) и `scores.spread` (1–5, разброс оценок экспертов/агентов). `strategy.categories_na` — категории, неприменимые к продукту: минимумы для них не проверяются (причину — в отчёт).

Шкалы 1–5; `cost` и `risk`: 1 — дёшево/безопасно, 5 — дорого/опасно. Подшкалы `reach…season` необязательны (по умолчанию = `value`). `horizon`: now — 0–3 мес, next — 3–12 мес, later — 1–2 года, vision — 2+ года.

## data/scores.json (пишет `score.py`)
Список объектов: `{"id", "rank", "rice", "ice", "wsjf", "value_per_effort", "risk_adjusted", "confidence_calc", "composite", "quadrant": "quick_win|big_bet|filler|money_pit", "priority": "P0|P1|P2|P3", "moscow": "must|should|could|wont", "labels": ["important", "effective", "expensive", "risky", "fast", "slow", "strategic", "tempting_weak"], "typesafe": {…} | null}`.
Сопутствующие: `data/weights.json` (веса формул), `data/sensitivity.json` (`{"tornado": [{"param", "low_rank_shift", "high_rank_shift"}], "top20_stability": 0.0..1.0, "runs": N}`).

## data/model.json (пишет `model.py`)
`{"scenarios": {"pessimistic|base|optimistic": {"assumptions": {…}, "funnel": [{"stage", "value"}], "monthly": [{"month", "users", "paying", "revenue", "cost"}], "cac", "ltv", "payback_months", "arpu", "churn", "roi"}}, "notes": []}`. Все входы — допущения с метками.

## data/competitors.json
Список: `{"slug", "name", "url", "type": "direct|indirect|substitute", "segment", "price", "monetization", "languages", "audience", "freshness", "traffic": "оценка или null", "features": {"feature": true}, "better_than_us": [], "we_better": [], "best_solutions": [], "design_note", "complaints": [], "adopt": [], "avoid": [], "verdict", "shot": "competitors/shots/<slug>.png|null", "shot_blocked": false, "sources": ["https://…"]}`. Первый объект может быть `"self": true` — наш продукт для матрицы.

## data/communities.json, data/keywords.json, data/events.json
- communities: `{"name", "url", "platform", "language", "audience_size": "оценка|null", "self_promo_rules", "allowed_formats": [], "ban_risk": 1..5, "source"}`
- keywords: `{"query", "lang", "cluster", "intent", "volume": null|число, "volume_source", "competition": null|1..5}`
- events: `{"date", "date_end", "title", "kind", "relevance", "source", "verified": true}`

## data/sources.json
`{"id": "S001", "url", "title", "date_checked", "used_for", "status": 200|null, "note"}`. `check_links.py` обновляет `status`.

## data/gantt.json
`[{"id": "G01", "phase", "task", "proposal_ids": [], "start_month": 1, "end_month": 3, "type": "task|milestone", "owner", "done_criteria", "dependencies": []}]` — месяцы от 1 до `horizon_months` (+ годы видения как месяцы 13…36, `phase: "vision"`).

## data/kanban.json
`{"columns": [{"name": "Идеи", "wip": null}, {"name": "Проверка", "wip": 5}, {"name": "Готово к разработке", "wip": 8}, {"name": "В работе", "wip": 4}, {"name": "Запуск", "wip": 3}, {"name": "Измерение", "wip": 6}, {"name": "Закрыто", "wip": null}], "cards": [{"id": "P001", "title", "column", "goal", "steps": [], "kpi", "links": [], "tags": [], "priority", "effort_days": [min, max]}]}`

## data/flows.json
`[{"key": "user-journey", "title", "svg": "charts/flows/<key>.svg", "nodes": [{"id": "user-journey:1", "label", "what", "now", "todo": [], "proposals": [], "metrics"}]}]`. Узлы в SVG помечаются `data-node="<id>"`.

## data/mockups-index.json
`[{"key": "M01-onboarding", "html": "mockups/concepts/M01-onboarding.html", "png": "mockups/concepts/M01-onboarding.png", "title", "proposals": ["P003"], "viewport": "1440x900|390x844", "kind": "concept|current"}]`. Каждый концепт несёт бейдж «Концепт, не существующая функция».

## design-refs/NN-slug.json
`{"file": "mockups/concepts/…html", "png": "design-refs/NN-slug.png", "scale": 1, "width": 1440, "height": 900, "title", "proposals": [], "kind": "page|mobile|component|external", "summary", "entry", "shared": [], "new_elements": [], "hotspots": [{"n": 1, "x": 0, "y": 0, "w": 100, "h": 40, "title", "text", "proposal": "P003", "state": "new|changed|shared"}], "todo": [], "questions": []}` + `NN-slug.md` (Что это / Как выглядит / Как взаимодействовать / Что нужно доделать / Элементы / Открытые вопросы). Координаты — CSS-пиксели исходного размера.

## charts/charts-index.json (пишет `charts.py`)
`[{"key": "effort-impact", "svg": "charts/effort-impact.svg", "title", "caption": "вывод одной фразой", "section": "scores"}]`.

## research/strategy.md
Markdown, разделы `## N. Заголовок` (порядок — `references/strategy-outline.md`). Ссылки на предложения — `P\d{3}` в тексте (веб-страница делает их кликабельными). Вставка графика — строка `![[chart:<key>]]`, макета — `![[mockup:<key>]]`, референса — `![[ref:NN-slug]]`.

## data/typesafe-jev.json (необязательно, `typesafe_eval.py`)
`{"model": "jev", "date", "questions": [{"key", "text", "kind": "p|score|choice"}], "items": {"P001": {"p_success": 0.0, "p_user_value": 0.0, "risk": 0.0, "…": …}}, "skipped": "причина|null"}`. Ключ — только из переменной `TYPESAFE_API_KEY`, в файлы не пишется.

## Дополнительные поля и файлы (1.0)
Скрипты пишут больше, чем требует схема выше; поля только добавляются, существующие не меняются. Читатели (веб-страница, XLSX, колода) используют их, если они есть.
- `data/repo-scan.json`: `repo.remote_host|is_git|readme_title|readme_summary`, `stack.data_languages|dependencies_count|large_files_bytes`, `routes[].framework|kind(page|api)|method`, `features[].kind`, `i18n.libraries`, `quality.deploy`, `docs.other`, `git.tags_total|tags_recent`, `integrations_evidence{cat:{name:[{file,line,source,weak}]}}`, `todo_top_files`, `scan{seconds,files,truncated}`. `entrypoints[].kind` дополнительно: `extension|plugin|game`.
- `data/scores.json`: дублирует `title, category, evidence_class, horizon, kano` и пишет `value_index, cost_index, risk_index, effort_days_mid, reach_units, cost_of_delay, n_*` (нормированные метрики).
- `data/weights.json`: схема — `references/scoring.md` (композит `{"composite": {rice, ice, wsjf, risk_adj}}`, подшкалы `value|cost|risk`).
- `data/sensitivity.json`: дополнительно `*_top_overlap, swing, top_n, always_top20`.
- `data/model.json`: `currency, revenue_model, arppu, ltv_cac, breakeven_month, totals`; в `monthly[]` — `cum_margin, cum_cost, visitors, signups, marketing`. Параметры — `build/model-params.json`.
- `data/sources.json`: `status` — фактический HTTP-код (200/403/404…) или `null`; анти-бот помечается в `note`. `check_links.py` пишет `data/links-check.csv` (`url, status, verdict, final_url, checked, origins`).
- `data/competitors.json`: `shot_error` (строка или null), `shot_blocked` пишется всегда.
- `charts/charts-index.json`: ключи `effort-impact, bubble, metrics-heatmap, radar-top10, pareto, tornado, dist-category, dist-evidence, dist-horizon, gantt, funnel, forecast-fan, cac-ltv, payback, keywords-volume, events-calendar, competitors-heatmap`; секции `scores|registry|plan|model|market`. Гант — ключ `gantt`.
- Служебные: `build/merge-report.json` (merge_proposals), `data/registry-check.json` (check_registry), `data/issues.json` + `data/issues-demand.csv` + `research/issues-demand.md` (issues_export), `data/site-audit.json` (audit_site), `data/mockups-check.json` (shoot_mockups), `build/deck.json` + `build/deck.html` (колода: `{meta, slides[{type: title|section|bullets|image|stats|table|card, appendix, notes, sources}]}`).
- Вставка блок-схемы в `research/strategy.md`: `![[flow:<key>]]` (ключ из `data/flows.json`).
- Фрагменты параллельных агентов: `data/sources-<group>.json`, `data/competitors-cards-<N>.json`, `build/parts/*.md` — оркестратор сводит их в основные файлы.

## Дополнения 1.1 (обратная связь по реальному прогону, issues #80–#92)
Все поля необязательны; отсутствие = поведение 1.0.
- **run-config**: `project: {goal: personal|oss|commercial|internal|nonprofit|auto, repo_visibility: public|private|unknown, publish_code: yes|no|undecided, currency: "RUB|USD|EUR|…", price_hint: null|число, traffic_hint: null|число, team_size: 1}`; `strategy.profile: standard|zero-budget-solo` (профиль «нулевой бюджет, один разработчик»: метрики усилий вместо CAC, ёмкость разработчика дни/мес как ограничение плана, режим «личный → открытый проект»); `strategy.markets` и `product.type` после `apply` всегда конкретные (не `auto`); `phases.gap_audit: true`; `tools.node_dir: null|путь` (по умолчанию `~/.cache/product-strategy/node`).
- **data/competitors.json**: `verdict` ≤ 45 знаков, длинное — `verdict_long`; `features_labels: {ключ_функции: "Русское название"}` (подписи графиков и матрицы берутся из него; ключи snake_case в подписи не выводятся).
- **data/scores.json**: `blocked_by: [id]` (все транзитивные предпосылки из `dependencies` и из gap-audit), `unlocks: [id]`, `dep_rank` (ранг с учётом зависимостей: предложение не раньше своих предпосылок, разблокирующее получает бонус), `critical_path: bool`. Сводка — `data/critical-path.json` `{"order": [id…], "edges": [[a,b]…]}`.
- **data/charts-index.json**: ключи дополнены `critical-path`, `channel-mix`, `kpi-tree`, `keywords-clusters` (запасной график спроса, если объёмов нет); `charts.py --list-keys` печатает JSON-список допустимых ключей и пропущенных с причиной; `gantt` строится из `data/gantt.json` сразу после её записи.
- **research/strategy.md**: плейсхолдер `{rank:P032}` подставляет сборщик (актуальный ранг, `dep_rank` — `{deprank:P032}`); `![[mockup:?P058]]` — «макет предложения P058, если он есть» (разрешается по `proposals[].mockup`); битый маркер = ошибка сборки.
- **research/gap-audit.md** и **data/proposals-draft-G7.json** (фаза 5.5, черновики пробелов), **data/fact-check.json** (расхождения фактов между агентами и фазой 1), **data/repo-facts.json** (видимость, лицензия, звёзды, темы, платформенная совместимость, цены, отслеживаемые секретоподобные файлы — только имена).
- **mockups**: `data/mockups-index.json` создаётся автообнаружением `concepts/*.html` (`data-viewport`), `data/mockups-check.<key>.json` по ключу + агрегат `data/mockups-check.json`.
- **Папка прогона**: чек-лист один (1.5, FB-040) — блок фаз в `TASKS.md` владельца (если он есть в корне репозитория или его требует CLAUDE.md; run-config `output.tasks_file` / `owner_rules.tasks_file`) между метками `<!-- product-strategy:phases <OUT> -->`, иначе `STRATEGY_TASKS.md`; пути в брифах и README относительные (`<OUT>`/`<repo>`), абсолютные подставляются при выполнении; `init_run.py <OUT> --relocate <NEW>`.

### Уточнения по итогам 1.1 (поля, которые скрипты уже пишут и читают)
- **run-config**: `strategy.categories_required: [..]` (категории, обязательные в профиле solo), `strategy.north_star` или файл `data/north-star.json` `{"metric", "inputs": [строка | {name, match}]}`.
- **data/gap-audit-deps.json** `{id: [предпосылки]}`; **data/proposals-draft-G7.json** (id `G7-NN`; `merge_proposals.py --append G7` дописывает без перенумерации, затем зависимости от G7 переводятся на новые P-id); **data/gap-audit-facts.json** (фактура для аудитора: `top[]`, `bets`, `prerequisites[]`, `dependency_warnings[]`, `keyword_flags[]`, `similar_pairs[]`, `free_vs_paid[]`, `coverage{…}`, `critical_path`, `cycles`, `constraints`, `project`, `profile`).
- **data/critical-path.json**: кроме `order`, `edges` — `top_n, value, nodes, cycles, dropped_edges, unknown, warnings, params`. **scores.json**: дополнительно `dep_bonus`. **model.json**: `currency_symbol, profile, solo, capacity`, у solo — `roi_note`, `cac_note`.
- **data/repo-scan.json** (1.1): `prices[{file,line,value,currency,context,kind: table|constant|literal,period?,currency_from}]`, `trials[]`, `platform_compat{declared,declared_sources,unix_only[{module,file,line,guarded}],windows_only,mismatch,note}`; `scan{source: git|walk, duration_s, files_seen, files_listed, tracked, untracked, files_not_visited, skipped_dirs[{path,reason,files}], skipped_dirs_by_reason, warnings}` (вместо `seconds/files/truncated`).
- **data/repo-facts.json** (`repo_facts.py`): `github | {skipped}`, `visibility`, `license{file,spdx,github,note}`, `issues`, `tests{static,claims,check_needed,recommendation}`, `tracked_secret_like[{file,mask,kind}]` (только имена), `platform_compat`, `prices`, `trials`. **data/issues-summary.json**: `{open, closed, total, limit_reached, detailed, note | skipped}`.
- **data/site-audit.json** (1.1): в `pages[]` — `slug, theme, theme_method, states[], clicks_skipped[]`; в `tokens` — `source, custom_properties, dark{source,vars,from}`; сверху — `routes_from, themes, clicks`. **mockups/tokens.css**: тёмный блок первым (`:root[data-theme="dark"], [data-theme="dark"]:not(:root)`, `rgb()`), светлый последним (`:root, [data-theme="light"]`): сборщики берут последнее значение переменной.
- **proposals[].mockup** — `concepts/<key>.html` (путь от `mockups/`), `mockups` — список таких путей (`link_mockups.py`); в `mockups-index.json` поле `html` с префиксом `mockups/`.
- **Части стратегии**: `build/parts/strategy-NN.md` или `research/strategy-part*.md` (`assemble_strategy.py`); отчёты скриптов — `build/assemble-report.json`, `build/merge-sources-report.json`, `build/relocate-report.json`.
- **data/fact-check.json**: список `{claim, was, now, source, status}` (`facts_scaffold.py` читает терпимо: список или словарь с `items`/`discrepancies`/`checks`).
- **data/sources.json**: `date_checked: null` допустим у записей, добавленных скриптом; `title` не равен URL (иначе «без названия» в `note`). **data/links-check.csv**: колонки `url,status,verdict,final_url,checked,origins,files`.
- **Страница** (`build_html.py --lite`): `deliverables/assets/` с манифестом `.ps-assets.json`.
- **Сайт** (`build_html.py`, режим `site` по умолчанию): `deliverables/index.html` (оболочка) + `assets/app.css|app.js|data.js|head.js` (+ `charts.js`, `extra.css|js` из `<OUT>/build/extra.css|js` — только если файлы есть), `assets/img/` (`thumbs/` — миниатюры), `data/` (`proposals.json|csv`, `scores.csv`, `competitors.csv`, `gantt.csv`, `kanban.csv`, `sources.csv`), по `--zip` — `strategy-site.zip`. Список созданных файлов — `deliverables/.ps-site.json`; пересборка в другом режиме (`--single`, `--lite`) удаляет их, чужие файлы не трогает. `--single` — прежний автономный `index.html`.

## Отслеживание выполнения (1.2, issues #93–#95)
Режим «Отслеживание»: по готовой стратегии (`<OUT>` прошлого прогона) сверить реализованное в репозитории и в GitHub с планом, отметить статусы и просроченное, предложить корректировки. Движок — `scripts/strategy_track.py` (`discover`, `check`, `set`, `link`, `ask-list`, `report`, `apply-to-strategy`); сама стратегия остаётся историей, статусы лежат рядом. Все файлы — в `<OUT>` исходной стратегии.

- **data/progress.json** (последний срез; пишет `strategy_track.py check`):
```json
{"version": 1,
 "baseline": {"strategy_dir": ".", "created": "2026-10-10", "proposals": 127, "git_head": "<sha на дату стратегии|null>", "scan": "data/repo-scan.json"},
 "checked": "2026-12-01", "months_elapsed": 1.7, "month_index": 2,
 "sources": {"repo": true, "git_log": true, "scan_diff": true, "issues": true, "prs": true, "gh": "ok|skipped: причина"},
 "summary": {"total": 127, "done": 12, "partial": 5, "in_progress": 9, "planned": 7, "not_started": 85, "blocked": 4, "dropped": 3, "obsolete": 1, "unknown": 1,
             "percent_done": 9.4, "by_horizon": {"now": {"total": 40, "done": 8}}, "by_priority": {"P0": {"total": 15, "done": 5}}, "by_category": {"product": {"total": 38, "done": 4}}},
 "items": {"P001": {"status": "done|partial|in_progress|planned|not_started|blocked|dropped|obsolete|unknown", "suggested": "то же, что вычислил движок (до overrides)",
           "confidence": 0.0, "source": "auto|override|link",
           "issues": [{"number": 12, "state": "open|closed", "state_reason": "completed|not_planned|null", "title": "", "url": "", "labels": [], "closed_at": null, "match": "explicit|saved|similar", "score": 0.0}],
           "prs": [{"number": 30, "state": "merged|open|closed", "title": "", "url": "", "merged_at": null, "match": "explicit|saved|similar"}],
           "commits": [{"sha": "abc1234", "date": "", "subject": "", "match": "explicit|files|terms"}],
           "code": [{"file": "path", "kind": "path|route|feature", "evidence": "что найдено"}], "scan_diff": ["+route /pricing"],
           "blocked_by_open": ["P032"], "note": "", "since": "дата смены статуса относительно прошлого среза"}},
 "outside_strategy": [{"kind": "issue|pr", "number": 55, "title": "", "state": "open|closed|merged", "url": "", "suggest": "candidate-proposal|bug|chore", "similar_to": ["P040"]}],
 "facts_changed": [{"fact": "repo_visibility|license|tests|prices|platform|…", "was": "", "now": "", "affects": ["P032"]}],
 "next_actions": ["P045"],
 "overdue": [{"task": "G03", "proposals": ["P001"], "planned_end_month": 3, "status": "behind"}],
 "warnings": []}
```
Статусы: `done` — закрыт issue с причиной completed (или влит PR, или сильные следы в коде), `partial` — часть шагов/issue закрыта, `in_progress` — есть открытый issue/PR с активностью, `planned` — issue заведён без активности, `not_started` — следов нет, `blocked` — предпосылки (`dependencies`) не выполнены, `dropped` — закрыт как not_planned / решение владельца, `obsolete` — условие предложения изменилось (например, репозиторий уже открыт), `unknown` — противоречивые следы.
- **data/progress-overrides.json** `{id: {"status", "note", "date", "by": "owner"}}` — решение владельца побеждает движок; `strategy_track.py set <OUT> P031 done --note …`.
- **data/issue-links.json** `{id: [номера issues]}` — сохранённые связи (ручные и из подтверждённых совпадений): сопоставление стабильно между запусками; `strategy_track.py link <OUT> P031 12 13`.
- **data/gantt-progress.json** `[{"id": "G01", "task", "proposal_ids": [], "start_month", "end_month", "status": "done|partial|on_track|behind|upcoming", "progress": 0.0, "done_ids": [], "open_ids": []}]` формат — объект `{"current_month": 2, "checked": "…", "tasks": [...]}` (читатели принимают и просто список задач); **data/kanban-progress.json** `{"moves": [{"id", "from", "to", "reason"}], "columns": {"Идеи": [id…], …}}` (колонки как в `kanban.json`, перенос не записывается в `kanban.json`).
- **data/revision.json** `[{"type": "mark_done|obsolete|reprioritize|add|reschedule|unblock|drop", "id": "P031|null", "text": "что изменить в стратегии", "reason": "", "evidence": ["issue #12", "commit abc1234"], "sections": [10, 14]}]` — вход для брифа `templates/briefs/strategy-update.md`.
- **data/issues-drafts.md** — черновики issues для `next_actions` без заведённого issue (в формате репозитория, с P-id в теле для стабильного сопоставления); **создавать issues только по явной просьбе** (`gh issue create`), движок их не создаёт.
- **tracking/<YYYY-MM-DD>/** — снимки среза (`progress.json`, `progress.md`, `strategy.md` до правок) и **tracking/history.json** `[{"date", "summary": {…}, "git_head"}]` для динамики.
- **research/progress.md** — читаемый отчёт: сводка, по горизонтам 30/60/90 дней, 6/12 месяцев, годы; сделано, в работе, отстаёт, заблокировано; изменившиеся факты; работа вне стратегии; следующие шаги; расхождения «считали отсутствующим, а оно уже есть».
- **research/strategy.md**: автоблок `<!-- progress:start --> … <!-- progress:end -->` в разделе 14 (таблица статусов по срокам), пишет `strategy_track.py apply-to-strategy` идемпотентно; прежний текст до правок — в `tracking/<дата>/strategy.md`.
- **run-config**: `tracking: {baseline: "<путь к <OUT> исходной стратегии>", mode: "auto|ask", last_checked: null}`; в опросе — режим (`intake.py detect`).
- **Сопоставление issue ↔ предложение**: явное упоминание P-id в заголовке/теле/метках → `explicit`; сохранённая связь → `saved`; сходство (tf-idf/триграммы заголовка и шагов предложения с заголовком и телом issue; порог из `progress.json → sources.match_threshold`) → `similar`, требует подтверждения при уверенности < 0,6 (`ask-list`).

### Уточнения по итогам реализации отслеживания (1.2)
Движок пишет больше, чем описано выше; поля только добавляются.
- **data/issue-links-rejected.json** `{id: [номера]}` — «не связано» (ответ владельца): сопоставление по сходству их больше не предлагает.
- **progress.json**: `items[].title|horizon|priority|issues_before|mentions` (P-id, упомянутые в эпиках и списках кандидатов, — на статус не влияют); у issue — `sim`, `kind: pr`; на верхнем уровне — `facts_now`, `scan_diff`, `discrepancies`, `notes`, `remote`, `baseline.git_head_source` (`scan|file|date`); `sources.scan_mode` (`archive|stored|same-head`), `git_range`, `issues_count`, `prs_count`, `commits_count`, `since`, `match_threshold`; `summary.by_term`, `outside_strategy`, `changed_since_last`, `previous_check`; во всех группах `by_*` — также `in_progress`, `partial`, `blocked`.
- **gantt-progress.json**: `checked`, `tasks[].phase`; **kanban-progress.json**: `off_board`, `checked`; **tracking/history.json**: `month_index`.
- **data/repo-scan.json**: `repo.head` (sha на момент скана) — точка отсчёта git-лога и сравнения сканов (режим `archive`: `git archive` HEAD стратегии и текущего HEAD сравниваются одним сканером; без `head` сравнение идёт с сохранённым `repo-scan.json`, числовые факты тогда не сравниваются).
- **Явные P-id** распознаются в виде `P031`, `p031`, `P-031`, `#P031`, `feature/p031_x`; P-id в заголовке, метке или имени ветки — связь; в теле при ≤ 3 разных — тоже; в эпиках (> 3 разных или у issue уже есть свой P-id в заголовке) — только `mentions`.
- **Переменные окружения**: `PS_GH_BIN` (подмена `gh` в тестах), `PS_STRATEGY_DIR` (папка стратегии или папка со стратегиями для `discover`).
- Подробности формул уверенности и порогов — в docstring `scripts/strategy_track.py`.
- **Подозрительные тексты**: `suspicious: true` у issue, PR и `outside_strategy[]` — в тексте похоже на обращение к агенту; на странице «⚠ проверить», текст не исполняется. `outside_strategy[].best_score`, `outside_strategy[].labels`; `kanban-progress.off_board`: `[{"id", "status", "to"}]` — карточки, которых нет на доске, но уже в работе или сделаны.
- **Демо и проверка**: `scripts/make_progress_demo.py <OUT>` пишет все файлы выше по контракту (для тестов и показа), настоящий движок — `strategy_track.py check`.

## Режим «Идея → концепция продукта» (1.3, `references/concept-mode.md`)
Включается полем `run-config.json → mode: "concept"`; без него всё как выше. Продукта и репозитория нет: файлы скана (`repo-scan.json`, `repo-facts.json`, `issues*.json`, `progress.json`) не создаются, читатели обходятся без них.
- **run-config** (пишут `intake.py concept-apply` / `concept-defaults`): `mode: "concept"`; `product.stage: "idea"`; `product.type` — из ответа «Форма»; `strategy.kind: "full"`, `strategy.monetization: "freemium|one_time|commission|donations|<свой текст>"`, `strategy.success_criteria`; `scope.repo_analysis=false`, `scope.app_run=false`, `scope.issues=false`, `sources.repo=false`, `repo.analyze=false`; `scope.legal=true` при чувствительной области (здоровье, деньги, дети, персональные данные). Объёмы по глубине: quick 50/8/6, **standard 60/10/8**, deep 80/15/12 (предложений / аналогов / макетов), горизонт 6 мес + видение 2 года. `output.inside_repo` — по фактическому положению папки (внутри git-репозитория → `git_branch: "docs/concept-<slug>"`, иначе `false` и `""`); `output.folder_conflict` — слова запроса расходятся с папкой.
- **run-config → idea**: `{"pitch", "name", "slug", "questions_count": 15..40, "answers": {"c01": {"theme", "header", "question", "answer": "label|[label]|свой текст", "custom": bool, "default": bool?}}, "unanswered": ["c05"], "not_asked": ["c30"], "facets": {"pain", "segment", "mvp", "sensitive": [], …}, "folder_choice": "here|sibling|home|custom", "folder_custom"?, "inspiration"?: [], "created"}`. Банк — 40 вопросов `c01…c40` в 9 темах (`intake.CONCEPT_BANK`); заданные, но пропущенные вопросы — в `unanswered` и в `assumptions` («не отвечено → допущение …»).
- **data/idea.json** (`concept_dossier.py`): `{version, date, mode, stage, pitch, name, slug, product_type, product_type_label, segment, segment_label, markets, currency, monetization, monetization_label, paid_tier, price_hint, budget, budget_note, team_size, hours_week, profile, legal, sensitive, success_criteria, horizon_months, vision_years, competitor_list, inspiration, facets, answers, questions_count, unanswered, not_asked, open_questions: [{id, theme, question, kind: unanswered|custom|autopilot|check, assumed}], autopilot}`. Рядом: `research/idea-dossier.md`, `research/product-understanding.md` (копия досье с шапкой «Продукта ещё нет»), `build/search-plan.md`, `build/seeds.md`; markdown с маркером `generated-by: concept_dossier.py`, ручная правка не затирается (`*.generated.md`).
- **data/typesafe-concept.json** (`typesafe_concept.py`): `{version, date, source: "jev|heuristic", model, confidence: "medium|low", skipped: "причина|null", api_error: "…|null", idea, questions: [{key, label, text, good: "high|low"}], items: {pain|reach|switch|distinct|feasible|revenue|timing|ban_risk: {p: 0..1, note, based_on: [id], label}}, viability, risk, verdict: "green|yellow|red", verdict_label, weak: [key], check_first: [label], thresholds, note}`. Пороги — в docstring скрипта.
- **data/competitors.json** в режиме идеи: дополнительно `kind: "self|direct|indirect|substitute|analog|inspiration|anti"`, у первой записи `self: true, planned: true` (планируемая идея), у остальных `lessons: []`, `why_it_worked_or_failed`, для `analog|inspiration|anti` — `sphere`; `type` остаётся из `direct|indirect|substitute` (для `analog|inspiration|anti` — `indirect`).
- **data/swot.json** `{strengths|weaknesses|opportunities|threats: [{text, basis, label: факт|оценка|допущение, source}]}`, **data/personas.json** — список персон (схема — бриф `templates/briefs/concept-canvas.md`).
- **data/proposals.json** в режиме идеи: `current_feature: "нет (продукта ещё нет)"`, теги `mvp|v1|later`; доказательства `repo`/`own_app` — предупреждение `check_registry.py`.
- **build/STATUS.md**: фазы `C0…C9` и `C5.5` (`init_run.py <OUT> --done 3` = `C3`); **data/gap-audit-facts.json**: `mode: "concept"` и семейства предпосылок `legal_entity`, `prototype`, `first_users`, `platform_accounts`.
- **Демо**: `scripts/make_concept_demo.py <OUT>` пишет все файлы выше; затем `build_all.py <OUT> --strict` (шаги `dossier`, `viability`; `track` в режиме идеи не выполняется).

## Передача в разработку: файл задач для Claude Code (`handoff.py`, `references/handoff.md`)
Необязательно; отсутствие блока = файл не собирается автоматически (скрипт можно запустить вручную).
- **run-config → handoff**: `{"enabled": true|false, "scope": ["all"] | ["ui", "product", …], "detail": "links|brief|full", "horizon": "now|next|all", "ask_at_end": true|false}`. Разделы: `ui, product, platform, acquisition, conversion, retention, analytics, monetization, localization, compliance, experiments` (`all` — все). По умолчанию `scope: ["all"]`, `detail: "brief"`, `horizon: "next"`. `ask_at_end` — оркестратор спрашивает в конце прогона, нужен ли файл и какие разделы; флаги `handoff.py` главнее run-config.
- **deliverables/CLAUDE_CODE_TASKS.md** (UTF-8 Markdown без HTML): шапка, инструкция для Claude Code (`templates/handoff-tasks.md`), карта материалов, эпики по разделам с задачами-чекбоксами (`P-id`, `U01…` — общие работы по дизайну, `E01…` — эксперименты, `CT-P…` — дешёвые проверки), макеты и референсы, эксперименты, приложение (таблицы соответствия эпиков и задач issue №, предпосылки вне выбранного, не вошедшие предложения с причиной, пропущенные материалы). Пути — от корня git-репозитория (`strategy/<дата>/…`), вне репозитория — от `<OUT>`. Последняя строка — `generated-by: handoff.py · sha256:<…>`; правленный вручную файл не затирается (`CLAUDE_CODE_TASKS.generated.md`, `--force`).
- Читает (всё, кроме реестра, необязательно): `data/proposals.json`, `data/scores.json` (`priority`, `blocked_by`, `dep_rank`), `data/gantt.json`, `data/mockups-index.json`, `design-refs/*.json|md`, `data/flows.json`, `research/strategy.md`, `research/specs/<P-id>-*.md` (разделы «Критерии приёмки»/«Требования»), `research/experiments/E*.md` («Гипотеза», «Метрики», P-id в первых строках), `mockups/tokens.css`, `data/issue-links.json`.
- `handoff.py <OUT> --list-sections --json` → `[{id, title, tasks, tasks_all_horizons, p0, p1, has_mockups, mockups, strategy_sections, approx_chars, approx_lines, about, summary}]` для карточек выбора.

## Реестр: карта id, ручные правки, решения слияния, брифы (1.4, обратная связь прогонов QA Helper и «Слышно»)
- **build/id-map.json** (`merge_proposals.py`, накопительно): `{"G1-03": "P012", "G7-05": "P141", …}` — id черновика → P-id; дополняется при каждом слиянии и `--append` (не затирается), слитые черновики указывают на P-id победителя. Без файла карта восстанавливается из `id_map` прежнего `build/merge-report.json` и `merged_from` реестра. При полном слиянии прежние P-id сохраняются (новые — после наибольшего номера карты); `--renumber` — заново, прежняя карта → `build/id-map.prev.json`. По карте переводятся ссылки `G\d+-\d+` во всех строковых полях предложений, в `dependencies`, `tags` (кроме `merged:…`) и в `data/gap-audit-deps.json` (`gap_audit.py --remap` — то же отдельно); `id`, `merged_from`, `source_group` не меняются. Оставшиеся ссылки — ошибка `check_registry.py`.
- **build/merge-report.json** — дополнительно: `id_map` (накопленная карта), `id_map_run` (этот запуск), `translated_refs`, `unresolved_refs: [{id, field, ref}]`, `overrides: {file, applied, unknown}`, `gap_audit_deps: {changed, unresolved}`, `semantic_candidates: [{a, b, semantic, similarity, shared, verbs, same_category, a_title, b_title}]`, `semantic_warnings: [{a, b, a_objects, b_objects, text}]`; в режиме `--append` — `allow_merge`, `candidates: [{drop, keep, merge, similarity, semantic, source}]`, `not_merged`, `skipped_already_in_registry`.
- **build/merge-candidates.json** (пишет `--dry-run`): `{"mode": "merge|append", "help", "decisions": [{"drop", "keep", "merge": true|false, "similarity", "semantic", "drop_title", "keep_title", "source": "auto|manual|lexical|semantic: …|decision"}]}`; `merge: true` — слить `drop` в `keep`. Читает `--pairs-from-dry-run [FILE]` (по умолчанию этот файл); вместо JSON можно сохранённый вывод `--dry-run` с отметками `[x]`.
- **build/overrides.json** (ручные правки, пишет человек или оркестратор; скрипты только читают): `{"_comment": "…", "P012": {"scores": {"value": 4, "_delete": ["seo"]}, "dependencies": ["P003"], "tags": ["…"], "horizon": "next"}, "G2-05": {…}}` — ключ P-id или id черновика из карты; словари сливаются рекурсивно, прочие значения заменяются; `"_delete": ["seo", "scores.revenue"]` — удалить ключи (точка — путь вглубь); `id` не меняется. Применяется после каждого слияния (`merge_proposals.py`, в т. ч. `--append`); `--apply-overrides FILE …` — к готовому реестру без слияния (тот же формат у `build/calibration-patch.json`).
- **data/proposals.json → scores_na** (необязательно): список неприменимых подшкал ценности (`["seo", "revenue"]`); то же — значение `null` подшкалы в `scores`. Исключаются из индекса ценности (`references/methodology-anchors.md`).
- **build/briefs/<шаблон>[-<группа|часть>].md** (пишет `render_brief.py`): готовый бриф с подставленными плейсхолдерами; справочная строка «Плейсхолдеры: …» не раскрывается; пути — от корня репозитория (`{OUT}`), `{SKILL_DIR}` — через `~`.

## Интерактивные графики: разметка SVG и пояснения (1.4, `references/interactive-site.md`, п. 2.1–2.2)
- **charts/<ключ>.svg** (`charts.py`): корень `<svg data-ps-chart="<ключ>" role="group" aria-label="<заголовок>" class="ps-chart">` с `<title>`/`<desc>`; каждый значимый элемент — `<g data-ps-el="<id>" tabindex="0" role="button" aria-label="<название по-русски>" class="ps-el ps-<вид>">` с `<title>` (подсказка без JS). Id уникален внутри графика: `P018` (предложение), `stage-activation`, `cat-acquisition`, `class-A`, `horizon-now`, `quad-quick_win`, `kpi-north-star`, `kpi-<семейство>`, `leaf-<семейство>-P018`, `edge-P006-P019`, `cell-P018-value_index`, `col-<метрика>`, `competitor-<slug>`, `feature-<ключ>`, `cell-<slug>-<ключ>`, `G01`, `phase-1`, `ev-01`, `kw-01`, `cluster-1`, `ch-seo`, `param-composite.rice`, `scen-base`, `cac-base`, `margin-base`, `be-base`, `legend-…`, `axis-x`. Дополнительно: `data-ps-ref="<id>"` (class `ps-ref`) — подпись или строка, относящаяся к элементу (клик = тот же элемент); `data-ps-group="<g-…> …"` — группы для подсветки; `data-ps-highlight="<g-…>"` у пунктов легенды и квадрантов — какую группу подсветить. Внешний вид SVG не меняется (обёртки `<g>`, невидимые широкие обводки тонких линий `stroke-opacity="0"`).
- **charts/<ключ>.meta.json** (`charts.py` → `chart_meta.py`, компактный JSON): `{"key", "title", "caption", "section", "mode": "product|concept", "howto", "legend": [{"label", "text"}], "links": [{"label", "href"}], "elements": {"<id>": {"title", "kind": "stage|point|bar|node|cell|event|link|legend|axis|area|line|row|column|shape", "summary", "meaning", "actions": [≤ 4], "metrics": [{"label", "value", "tag": "факт|оценка|допущение|расчёт|план|…"}], "links": [{"label", "href"}], "highlight"?: "<g-…>", "sources": ["notes"|"data"|"glossary"]}}, "generic": ["<id>" — пояснение только из глоссария], "warnings": ["пояснение не задано: <ключ>/<id>", "ссылка без цели пропущена: …"]}`. Каждый `data-ps-el` имеет запись в `elements` и наоборот.
- **Ссылки** (все цели проверяются; ссылка без цели не пишется): `#s<N>` — раздел стратегии 1…17 (номера одинаковы в `strategy-outline.md` и `concept-outline.md`; категории: acquisition/partnerships/localization → 6, conversion → 7, monetization → 8, retention → 9, product → 10, platform → 11, analytics → 12, new_lines → 15; темы: рынок и конкуренты → 3, сообщества, события, запросы → 4, позиционирование → 5, риски → 13, план → 14, видение → 15, методология → 17), `#p/<P-id>`, `#registry?category=…&horizon=…&class=…&quadrant=…&priority=…` (`class` — `evidence_class`), `#chart/<ключ>/<id>`, `#competitor/<slug>`, `#gantt/<G-id>`, `#kanban/<P-id>`, `#flow/<ключ>`, `#mockup/<ключ>`. На странице разделы сейчас имеют id `s-<N>` — сопоставление `#s<N>` → раздел делает обработчик ссылок страницы.
- **charts/charts-index.json**: у записи дополнительно `"meta": "charts/<ключ>.meta.json"` (прежние поля без изменений).
- **data/chart-notes.json** (необязательно; пишет автор или агент по брифу `templates/briefs/chart-notes.md`): `{"<ключ>": {"_chart": {"howto", "legend"}, "<id>": {"title"?, "summary"?, "meaning"?, "actions"?: [], "metrics"?: [], "links"?: []}}}` — перекрывает поля (заметки → данные прогона → глоссарий `references/chart-glossary.ru.json`); `actions`/`metrics` заменяют список, `links` дополняют (первыми); ссылки без цели отбрасываются с предупреждением.
- **references/chart-glossary.ru.json** — статические определения: разделы (`sections`, `sections_concept`), соответствие категорий и тем разделам, категории, стадии AARRR (с подблоком `concept` для режима идеи), квадранты, классы доказательств, горизонты, сценарии, метрики оценки (RICE, ICE, WSJF, composite…), оси радара, каналы, семейства KPI, термины (торнадо, критический путь, North Star, CAC, LTV, окупаемость…), для каждого графика — `howto` (+ `howto_concept`), `legend`, `sections`, тексты статичных элементов.
- **Страница** (`build_html.py`, п. 2.3): график с `meta` и SVG встраивается как SVG с панелью пояснений; без `meta` (старый прогон) — статичная картинка, как раньше, и предупреждение «графики без пояснений». Режим **site**: **deliverables/assets/charts-<группа>.js** — по файлу на группу графиков (`section` из `charts-index.json`: `scores`, `registry`, `plan`, `model`, `market`…), строки вида `(window.PS_CHARTS=window.PS_CHARTS||{})["<ключ>"]={"svg": "<svg …>", "meta": {"title", "elements": [{"id", "title", "kind", "summary", "meaning", "actions", "metrics", "links", "highlight"}]}};` (пустые поля опущены, `sources`/`generic`/`warnings` не переносятся, порядок `elements` — порядок `meta.elements`, он же порядок ←/→); в оболочке вместо SVG — `<div class="ps-svg" data-chart="<ключ>" data-ps-src="assets/charts-<группа>.js?v=<хеш>">`, файл подключается динамическим `<script src>` при приближении графика к экрану или по глубокой ссылке (по `file://` `fetch()` запрещён; CSP `script-src 'self'`). Режимы **single/lite**: SVG — в разметке раздела, пояснения — блок `<script type="application/json" id="d-charts">` `{ключ: meta}` того же вида. Разметка графика: `<figure class="ps-ichart[ ps-primary]" data-chart="<ключ>" [id="chart-<ключ>"]>` (основной экземпляр — в разделе «Графики», цель глубоких ссылок; вставка `![[chart:…]]` в тексте — второй экземпляр), кнопки «Как читать график» (`howto` + `legend`, разметка сервера) и «увеличить» (лайтбокс, ключ `c-<ключ>`).
- **Цели ссылок на странице** (роутер `hashchange` в скрипте страницы, функции `window.PS_ROUTER.parse|resolve|go`): `#s<N>` → `<section id="s-N">`; `#p/<P-id>` → раскрытая строка реестра; `#registry?category|horizon|class|quadrant|priority=…` → фильтры реестра (`class` → `evidence_class`; `#registry` без `?` — обычный якорь); `#gantt/<G>` → `.grow[data-gid]`; `#kanban/<P>` → `.kcard[data-kid]` доски «Как в плане»; `#competitor/<slug>` → `.ccard[data-slug]` (фильтры конкурентов сбрасываются) или строка матрицы `tr[data-slug]`; `#mockup/<ключ>` → `[data-mock]` (раздел макетов, затем «Текущее состояние»); `#flow/<ключ>` → `.flow[data-flow]`; `#chart/<ключ>[/<id>]` → график и выбранный элемент. Прежние `#p=<P-id>` (окно карточки), `#s-N`, `#lb=<картинка>` работают; `#lb=c-<ключ>` интерактивного графика ведёт к графику. Переход к цели вне графика закрывает панель. Сборщик проверяет каждую `links[].href` по собранной странице: ссылка без цели (например, раздела нет в `research/strategy.md`) в панель не попадает, печатается предупреждение со списком; `build_html.py --strict` — код выхода 1.
- **Проверка**: `charts.py <OUT>` после сборки печатает «Проверка пояснений графиков: ок (N элементов)» или список проблем и выходит с кодом 1; `charts.py <OUT> --check-meta` — только проверка (код 1: элемент без записи или запись без элемента, повтор id, нет `tabindex`/`role`/`aria-label`/`ps-el`, нет `howto`/`legend`, `#p/` на несуществующий P-id, `#s<N>` вне 1…17, любая другая ссылка без цели, SVG не разбирается как XML); `charts.py <OUT> --list-generic` — JSON `[{"chart", "id", "title", "reason": "только глоссарий|нет пояснения"}]` для брифа `chart-notes.md`.

## Реестр, отчёты агентов, fact-check (1.5, обратная связь прогонов «ARC Raiders» и «Smart Market Lens»)
Все поля необязательны; отсутствие = поведение 1.4.
- **run-config → registry** `{passes: 1|2, capacity_cap: bool, cap_factor: 1.3, now_months: число, category_minimums: "count"|"priority", ab_min_share: 0..1}` — `passes` попадает в `merge-report.json → registry_passes`; `capacity_cap` включает `merge_proposals.py --cap-now` при каждом слиянии и минимумы `priority`; формулы — `references/scoring.md` §11–12.
- **run-config → project.audience** (`personal|circle|personal_then_public|public`): в личном режиме категории реестра — `core, data-sources, reliability, privacy-security, ux, ai-quality, maintenance, personal-analytics` (поле `category` принимает их в любом режиме; в публичном — предупреждение). Подписи по-русски — `check_registry.CATEGORY_LABELS_RU`, список категорий прогона — `check_registry.active_categories(cfg)`.
- **run-config → slicing** `{enabled, queues: [{id: "Q1", name, goal, enter_when}]}` → **proposals[].queue** (`"Q1"` или `null`) и **scores.json → queue** (колонка есть у всех строк, если хоть одно предложение в очереди); `registry-check.json → by_queue {Q1: {count, effort_days, ids}}`.
- **proposals[].horizon_reason** — почему горизонт сменён скриптом: «перенесено из now: ёмкость …» (`--cap-now`) или «решение владельца (decisions.forks.F1): …».
- **proposals[].evidence[].kind** += `owner_prior_work` — прежние работы, репозитории и замеры владельца (внутреннее доказательство): класс предложения только на таких доказательствах — не выше C; в режиме идеи допустимо (в отличие от `repo`/`own_app`).
- **Черновики G7/G8** (`data/proposals-draft-G7.json`, `-G8.json`): `merged_from` и `source_group` не заполняются (их пишет слияние; проверки `gap_audit.py --check` и `check_registry.check_proposal(draft=True)` не предупреждают); необязательное поле **unlocks** `["P013"]` — черновик нужен до этих P-id (после `--append` попадает в `data/gap-audit-deps.json`).
- **research/gap-audit.md**: зависимости от черновиков можно писать текстом — `P035 ← G7-02, P031` (или `<-`) в любом месте и строками таблицы раздела «Предпосылки» (`| P035 | G7-02 | почему |`, в первой ячейке ровно один id); `merge_proposals.py --append G7` и `gap_audit.py --remap` дописывают их в `data/gap-audit-deps.json` уже в P-id (`merge-report.json → gap_audit_deps.added_from_text|skipped_from_text`).
- **data/decisions.json → horizons[]** `{proposals: [P-id], horizon: now|next|later|vision, tag?: mvp|v1|v2|later, why?, date?}` и **forks[].apply** `{proposals, horizon, tag?}` (или список; действует, только когда у развилки задан `decision`) — решения владельца о горизонтах. `merge_proposals.py` применяет их после overrides при каждом слиянии и отдельно — `--sync-decisions` (`build/sync-report.json`); расхождение реестра с решением — ошибка `check_registry.py` (`registry-check.json → decision_conflicts`).
- **build/overrides.json** — патч понимает `"_add": {"dependencies": ["P033"], "tags": ["…"]}`: дописать в список без повторов (самоссылка пропускается). Пример правки текстового поля (ошибка цитаты ≥ 15 слов): `{"P064": {"description": "Пользователи жалуются на ручной ввод «…» [факт: …]"}}`; заготовку пишет `check_registry.py <OUT> --suggest-overrides` → **build/overrides.suggested.json** (цитаты сокращены до 10 слов, переносится в `overrides.json` вручную).
- **build/merge-map.json** — кроме ручной правки, пишет `merge_proposals.py --write-distinct [FILE]` (решения `[ ]` → `distinct`, `[x]` → `merge`; `_comment` с пометкой `--write-distinct`).
- **build/merge-report.json** — дополнительно `decisions_sync[]`, `cap_now{…}` (или `null`), `remapped_files {путь: замен}` (после `--append`: ссылки на черновики добавленных групп переводятся в `mockups/concepts/*.html`, `design-refs/*.json|*.md`, `data/mockups-index.json`, `data/fact-check.json`; `--no-remap-files` — не трогать), `registry_passes`.
- **registry-check.json** — дополнительно `audience, categories_active, category_mode, ab_share_checked, ab_min_share, owner_only[], now_capacity{…}|null, by_queue{}, decision_conflicts[]`; у `category_minimums[кат.]` — `nominal`, `mode`.
- **Строки в отчётах агентов** (разбирает `collect_reports.py`; хвост брифов `templates/briefs/_report-footer.md`):
  - `ПРЕДПОСЫЛКА: P038 ← P033, P111 | почему` — предпосылка, которой нет в реестре (авторы разделов, C7) → `collect_reports.py <OUT> --deps [--into-overrides]` → **build/deps-patch.json** `{"_comment", "_summary": {generated, reports, lines, added, proposals, skipped: [{pair, why, where}], by_report}, "_reasons": {P-id: [{prereq, why, where, agent}]}, "P038": {"_add": {"dependencies": [...]}}}` → `merge_proposals.py <OUT> --apply-overrides build/deps-patch.json` → `score.py` и Гант (шаг C7.5). Пропускаются неизвестные id, самоссылки, уже записанные пары и пары, замыкающие цикл.
  - блок `## Отступления от брифа` (строки списка или `нет`) → ретроспектива.
  - строки макетов в `design-refs/*.md` (пишут агенты макетов, разбирает `link_mockups.py --collect-gaps`): `НУЖНО-ПРЕДЛОЖЕНИЕ: <заголовок> | <категория> | <связанные P-id через запятую>` → черновик `data/proposals-draft-G8.json` (полный объект по контракту, класс D с цепочкой рассуждения в `note`, `source_group` не заполнять) → `merge_proposals.py <OUT> --append G8`; `РАСХОЖДЕНИЕ: <P-id> | <ключ макета M08> | <суть>` → запись `data/fact-check.json` с `kind: "mockup_vs_registry"` (читатели принимают и `"mockup"`; поля — раздел 1.5 ниже).
- **data/fact-check.json** (запись; читатели принимают список или объект с `items|discrepancies|checks`): `{fact|claim, phase1_value, agent_value, source, resolved_value, note, kind?, fix?: {file, path, value, op?: set|append|merge|delete} | [..], fix_hint?: {file, select|path, fields?}, text_only?: true, applied?: bool, applied_at?, previous?: [..]}`. `collect_reports.py --fact-check` (= `--merge`) дописывает кандидатов с `fix: null, applied: false` и подсказкой `fix_hint`. **scripts/apply_fact_check.py** `<OUT> [--dry-run]` применяет `fix` к JSON внутри `<OUT>` (путь: ключи через точку, номер `0`/`[0]`, выбор `[slug=metaforge]`), ставит `applied: true`, `applied_at`, `previous`; отчёт **build/fact-check-apply.json**. `--check` (ворота `build_all --strict`): код 1, если есть подтверждённая запись (`resolved_value` или `fix`) без `applied: true` и без `text_only: true` (или «только текст» в `note`).
- **build/interventions.jsonl** (пишет `init_run.py <OUT> --intervention "что | почему | файл" --by owner|orchestrator|agent [--kind …]`, смена решения — `init_run.py --impact` с `kind: decision-change`; читают `collect_reports.py --retro` и `report.py`): строка JSON `{"ts": "<ISO>", "by": "owner|orchestrator|agent", "what", "why", "file" | "files": [], "phase"?: "C5", "kind"?: "brief|data-edit|file-edit|decision-change|other"}` (прежние `edit|decision` тоже принимаются); строка не JSON сохраняется как `what` с `by: "не указано"`.
- **build/retro.md**, **build/retro.json** (`collect_reports.py <OUT> --retro`): `{version, generated, entries: [{by, what, why, file, phase?, kind?, ts?, source}], journal, auto, by_owner, by_orchestrator, deviations: [{agent, text, where}], gates: [{step, status, note}], fact_check_open: [факт], deps_added, build_all: {date, summary}}`. Автообнаружение (если файла нет в журнале): ручные брифы (`build/briefs/*.md`, имя которых не начинается с имени шаблона `templates/briefs/*.md`), `build/overrides.json`, `build/model-params.json` (параметры с меткой не «допущение» или файл новее `data/model.json`), `build/merge-map.json` без пометки `--write-distinct`. Разделы `retro.md`: 1 — владелец, 2 — оркестратор вне скилла, 3 — отступления агентов, 4 — дефекты скриптов и ворота (`build/build-all-last.json`), 5 — данные после текстов (второй раунд зависимостей, неприменённый fact-check).

## Опрос, план, оркестрация, дизайн, прототип (1.5, все поля необязательны)
Без поля — поведение 1.4. Пишет `intake.py concept-apply` (опрос), если не сказано иное; в 1.4 некоторые поля были строками — читатели принимают оба вида.
- **run-config → project**: `audience: public|personal|circle|personal_then_public` (первая карточка «Для кого приложение?»), `release_outward: bool`, `audience_note`; `capacity {hours_per_week (на человека), dev_share, day_hours, source}` — одна величина рабочего дня (`project.hours_in_day` не вводится; расчёт — `scripts/capacity.py`); `tax_regime?: npd|usn6|none` (рынок ru; задаётся `--set`).
- **run-config → registry** (дополнение к разделу выше): `{passes: 1|2 (1 — quick и deep, 2 — standard и exhaustive), capacity_cap: bool, category_minimums: count|priority, auto_keys: []}` — `auto_keys` — поля, выставленные автоматически (заданное `--set` не перезаписывается).
- **run-config → product / strategy**: `product.forms[]` (`web`, `mobile_web` — адаптив и PWA, `mobile`, `bot`, `desktop`, `extension`, `devtool`), `product.future_forms[]` (формы «на потом», мобильный задел); `strategy.markets_note`; `strategy.payment_channel: direct|store|donations|none` (профиль модели: `direct` и `mobile_web` → `web-direct`, `store` → `mobile-app`, `donations` → `oss`); `strategy.fast_concept: bool` (быстрая концепция ≈ 10 агентов).
- **run-config → tools.agents** `{model_policy: triage|default|custom, effort_policy: explicit|none, note?}` — `dispatch.py ready` выдаёт `effort` только при `explicit`; `custom` — правила владельца в `note`.
- **run-config → idea** (дополнение к разделу 1.3): `request` (исходный запрос), `request_questions[] {id: RQ01…, text, kind: research|deliverable|format, source}`, `keywords[]`, `keywords_source: auto|owner`, `topic_en`, `topic_en_for` (версия идеи, к которой относится перевод), `name_source: given|auto`, `interview_mode: standard|fast|deep`, `prefill_raw?`, `block_answers {id: {block, header, question, answer, custom, prefilled?, confirmed?}}`, `blocks_answered[]`, `replaced[]`, `checks[] {id, severity, message, header, question, options[{label, key, set}]}`, `decisions {id: ключ}`, `decisions_applied {}`, `version`, `pitch_v2`, `history[]` (пишет `pivot_check.py`); у `answers[*]` — необязательные `prefilled`, `confirmed`, `quote`, `confirmed_default`, `card_default`, `correction`, `exclusive_conflict`; вопросы личного режима — id `p01…p10`.
- **run-config → idea.facets.*** (условные блоки опроса): `platform_*` (dependency, name, kind, urls[], data_needs[], access: official|community|manual|research|mixed, allowed, fallback), `data_*` (sources_needed[], license, keys, fallback, jurisdiction, delivery, history), `ai_*` (role[] — прежнее `ai`, where: local|server|cloud|hybrid|local_then_cloud, data, error_cost, guardrails[], hardware, eval, output, latency, observability[], security[], models, versioning), `admin_*` (who, settings[], backup, log, alerts, updates, roles, support, legal, needed: bool), `law_*`, `fin_*`, `crypto_*`, `health_*`, `children_*`, `pd_*`, `ui_*`, `prototype_needed: bool`, `prototype_scope: core|one_screen|all_modes`, `stack`, `view`, `handoff_extras[]`, `owner_repos[]`, `owner_data`, `tool_limits[]`, `personal_job`, `personal_frequency`, `personal_value`, `reliability_need`, `data_location`, `ownership_budget`, `support_hours_month`, `project_lifetime`, `doc_features[]` (hotspots, search, zoom).
- **run-config → design** `{pointer_first: bool, directions_count: 1..7, modes[] (["beginner", "pro"] или пусто), modes_decide_later?, default_mode?, forms[], mobile_reserve?, gallery?}`; `chosen`, `chosen_name`, `chosen_by: owner|default`, `chosen_at` пишет `mockup_kit.py choose`.
- **run-config → sources**: `owner_docs[] {url | path, kind: platform_site|competitor|document|artifact|repo|data|other, role: base|follow|ref, status: not_attempted|read|blocked, tool, note, source}` (в 1.4 — строки; `build_all --strict`: запись со `status: not_attempted` — «нет» в воротах `owner_materials`, строки пропускаются); `competitor_list[]`, `external.site`.
- **run-config → git / output / owner_rules**: `git {state: no_repo|unborn|normal, has_origin, branch, default_branch, visibility}`; `output.branch_status: created|switched|current|skipped|failed|planned`, `output.branch_note` (`init_run.py --show/--status` сверяет текущую ветку с `output.git_branch` и показывает их); `output.tasks_file: TASKS.md|STRATEGY_TASKS.md|auto`, `output.dir_rel`, `output.competitor_shots: git|local|previews` (вопрос до «Начинаю?», если репозиторий не приватный; читает `check_gitignore.py`); `owner_rules {sources[], branch_per_task, merge, push_after_merge, delete_branches, tasks_file, language, lines[]}` (из CLAUDE.md; `tasks_file` — чек-лист по умолчанию внутри git-репозитория).
- **run-config → slicing** (дополнение к разделу выше) `{enabled, decision: slice|continue|refine|stop, source, mvp, cut_rule, queues[] {id: alpha|beta|v1|v2, name, goal, enter_when, months, capacity_days, capacity_line}, priorities[] {weak, label, cheap_test}}`.
- **run-config → phases** `{pivot_check: true (C4.5), deps_round: true (C7.5), prototype: false (C8.5; или idea.facets.prototype_needed)}`.
- **data/idea.json** (дополнение): `audience, release_outward, forms, future_forms, markets_note, request_questions, owner_docs, keywords, keywords_source, topic_en, topic_en_stale, capacity {dev_days, day_hours, hours_per_week, line}, block_answers, checks, slicing, idea_version, pitch_v2, history, premises, pivot_decision, pitch_effective, replaced`; `version` — версия идеи (1, после пивота 2…).
- **data/premises.json** (`pivot_check.py`, C4.5) — схема в docstring скрипта: `premises[] {id, kind, key, text, status: confirmed|refuted|partial|null, evidence, source}`, `decision: keep|narrow|stop`, `pitch_v2`, `by`.
- **data/plan-baseline.json** (`plan_baseline.py`): `start_date, capacity, milestones {beta, launch, mvp, paid, horizon_end}, mvp {ids, only_in_registry}, kill[], north_star, goal, events[], architecture {id, name, days, risks, value, mvp_options[], mvp_days [min, max], queue, platform_risks[], source} (из data/integration-options.json), months[] {month, period: plan|gap|vision, tasks, milestones, load_days, capacity_days, over_capacity}, gantt_contract {ok, gap_months, plan_months_without_tasks, over_capacity_months, messages}`. Задачи Ганта — необязательное поле `milestone: beta|launch|mvp|paid`. Контракт Ганта: месяцы 1…горизонт и видение до горизонт + 12 × vision_years без пропусков. `plan_baseline.py <OUT> --check` → **build/consistency-report.json**; код 0 — согласовано, 1 — расхождения.
- **data/integration-options.json** (бриф `research-integration`): `{recommended: "<id>", options[] {id, title, effort_days: [min, max], risks[], value, mvp: bool, queue}, platform_risks[]}`.
- **data/demo-canon.json** (`facts_scaffold.py <OUT> --demo-canon`, до волны макетов): `{label: "демо-данные", rule, values {ключ: {value, source}}, entities[], screens{}, cases[] {id, title, fn, inputs, expected, mockups[]}}` — `values` для макетов (`data-canon="ключ"`), `cases` — кейсы ядра прототипа (`data-canon="<кейс>.<поле>"`, `prototype/js/core.test.js`, `prototype/tools/check_canon.py`; пустой список — кейсы берутся из `prototype/fixtures/canon.json`).
- **data/decisions.json** → `draft` (черновик `facts_scaffold.py --draft` / `decisions.py --init --draft`; подтвердить и удалить). **data/model.json** — ключи `capacity` (все профили: `line, day_hours, dev_days_total, source…`), `illustration`, `scenarios.*.illustrative`, `reconciliation {items[]}` (`init_run.py --status` и `report.py` показывают их открытыми пунктами), `personal` (профиль `personal`), `breakeven_note`.
- **build/summary-draft.md** — черновик раздела 1 (`summary_scaffold.py <OUT>`; не в `build/parts/`), вход брифа `strategy-summary.md`; `--to-part` — `build/parts/strategy-01.md`.
- **build/owner-materials.md** (`init_run.py <OUT> --owner-materials`, шаг C0.6): раздел `## <url>` на ссылку со строкой `Статус: read|blocked|not_attempted`, инструментом, выжимкой и «как используется».
- **build/agents.json** (`dispatch.py`): задания `{id, wave, phase, kind, brief, model, effort, deps, paths, budget, actual, status, model_actual, tokens, minutes, result, attempts, triage}`; виды заданий 1.5 — `integration, datasources, ai, owner_refs, module, summary, prototype_core, prototype_shell, prototype_mode, prototype_regression` (вид и волна выводятся из имени нового брифа, если `--kind` не задан).
- **build/build-all-last.json** → `completeness[] {code, check, status: да|нет|н/п, detail, todo, accepted, warn_only?}` (код `start_decisions` — нерешённые находки `idea.checks[]`, только предупреждение), `accepted_known[]`, `pdf`, `demo`, `strict`, `warned[]`; шаги 1.5 — `kitverify`, `prototype`, `baseline`, `consistency`, `factcheck`.
- **Группы черновиков реестра**: G1–G6 — генераторы, G7 — аудит пробелов, G8 — пробелы макетов, **G9** — ИИ и наблюдаемость (`concept-ai-observability.md`), **G10** — администрирование и эксплуатация (`concept-admin.md`), **G11** — референсы владельца (`research-owner-refs.md`); `merge_proposals.py <OUT> --append G9,G10,G11` — как у G7 (без перенумерации, `merged_from`/`source_group` в черновиках не заполняются).
- **data/proposals-draft-G8.json** (`link_mockups.py <OUT> --collect-gaps`): полные объекты контракта с `id` `G8-NN`, `source_group: "G8"`, `evidence_class: "D"` (цепочка рассуждения — в `evidence[].note`), `tags: ["G8", "from-mockups"]`, `needs_details: true` (оценки, шаги и `effort_days` дописываются до `merge_proposals.py --append G8`; иначе слияние предупреждает «оценки не дописаны»), доп. поля `related[]`, `origin`.
- **data/fact-check.json → kind: "mockup_vs_registry"** (из строк `РАСХОЖДЕНИЕ:`): `{proposal, mockup, summary, status: open|resolved, decision, resolved_value: null, fix: null, applied: false}` плюс совместимые `fact|claim|phase1_value|agent_value|was|now|source`; закрывается `apply_fact_check.py` (`fix`) или `text_only: true`. Итог сбора — **build/collect-gaps.json** `{date, drafts_added[], fact_check_added[], skipped, errors, warnings, drafts_total, mismatches_open}`.
- **data/competitors.json → cookie: hidden|accepted|none** (`shoot_competitors.mjs`): по умолчанию баннер согласия скрыт стилем без кликов; `accepted` — только с `--accept-cookies` (причина — в отчёте; `references/safety.md`, §1).
- **data/mockups-check.<ключ>.json** (`shoot_mockups.mjs`) → `hotspots {count, untitled, duplicates, incomplete, scale, zones[{id, n, title, what, why, p, sec, x, y, w, h}]}` (CSS px от угла PNG; `scale` 2 у мобильных), `targets`, `layout`, `other_theme {png}`, `badge_by`, `badge_truncated`; подсветка в макете — атрибуты `data-hs`, `data-hs-title`, `data-hs-what`, `data-hs-why` (12–25 элементов на экран). Страница может читать и `mockups/hotspots.json` `{version, mockups: {<ключ>: {items: [{n, id, title, what, why, p, sec, r: [x, y, w, h] — доли 0…1]}}}}`.
- **Файлы дизайна**: `mockups/gallery.html` (`mockup_kit.py gallery`: 2–3 рабочих экрана на направление), `mockups/tokens-<режим>.css` (токены режима, `data-mode`), `mockups/concepts/M00-design-language.html`, `build/kit.lock` (`mockup_kit.py init`; `mockup_kit.py verify` — набор не менялся: код 0 / 1 — изменённые файлы / 2 — нет lock); бейдж концепта — элемент `.ps-concept-badge` с текстом «Концепт, не существующая функция · <продукт> · <дата>».
- **Рабочий прототип** (C8.5, `references/prototype.md`): `prototype/` (`index.html`, `js/core.js` + `core.test.js`, `js/kit.test.js`, `tools/check_canon.py`, `HANDOFF.md`), **data/prototype.json** `{status: ok|partial|failed, path, modes[], core_tests {passed, failed}, kit_tests, smoke {chromium, webkit}, canon {cases, checked, errors}, handoff}`; `build_all.py` шаг `prototype`, `handoff.py` — раздел «Перенос рабочего прототипа».
- **Личный режим**: категории реестра `core, data-sources, reliability, privacy-security, ux, ai-quality, maintenance, personal-analytics` — подписи по-русски берут `check_registry.CATEGORY_LABELS_RU` (страница, XLSX, колода, `handoff.py`; неизвестная категория выводится как есть); разделы эпиков `handoff.py`: core, ai-quality → product; data-sources, reliability, maintenance → platform; privacy-security → compliance; ux → ui; personal-analytics → analytics.
