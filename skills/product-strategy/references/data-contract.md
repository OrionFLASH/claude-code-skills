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
               "budget": {"variants": ["zero", "small", "medium"], "note": ""}, "paid_tier": "auto|yes|no", "constraints": ""},
  "scope": {"repo_analysis": true, "app_run": true, "competitors": true, "competitors_min": 10, "communities": true, "keywords": true,
            "events": true, "legal": true, "issues": true, "design_mockups": true, "mockups_min": 12, "design_refs": true,
            "unit_economics": true, "experiments": 8, "specs_top": 10, "kanban_cards": 40},
  "sources": {"repo": true, "issues": true, "web_search": true, "web_search_budget_per_hour": 100, "analytics_exports": [],
              "owner_docs": [], "competitor_list": [], "other": ""},
  "formats": {"html": true, "xlsx": true, "pptx": true, "pdf": true, "md": true},
  "tools": {"typesafe": "auto|on|off", "browser": "auto|playwright|chrome|none", "subagents": true, "max_parallel_agents": 5},
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
