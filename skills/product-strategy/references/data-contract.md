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
  deliverables/     index.html, strategy.xlsx, strategy.pptx, strategy.pdf, REPORT.md, README.md
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
- **Папка прогона**: `STRATEGY_TASKS.md` вместо `TASKS.md`; пути в брифах и README относительные (`<OUT>`/`<repo>`), абсолютные подставляются при выполнении; `init_run.py <OUT> --relocate <NEW>`.

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
