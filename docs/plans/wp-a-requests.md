# WP-A — запросы на правку чужих файлов (1.5.0)

Каждый пункт: файл (владелец) → что → зачем. Всё, что пишет WP-A, необязательно для читателей: без поля — поведение 1.4.

## D (оркестрация, ворота)

1. **`scripts/render_brief.py`** (FB-023) — брифы C4 (`concept-analogs`, `research-*`) не рендерить (код 1), пока в `build/search-plan.md` есть `<EN:`; сообщение: «в плане поиска заглушки <EN: …> — `concept_dossier.py <OUT> --topic-en "<перевод темы>"`». `{KEYWORDS}`: брать `run-config idea.keywords` (подтверждённые, `idea.keywords_source`), запасной путь — строка «Ключевые слова идеи:» плана поиска (она уже из `idea.keywords`).
2. **`scripts/build_all.py --strict`, шаг `completeness`** (FB-002, FB-058) — запись `sources.owner_docs[]` со `status: "not_attempted"` → «нет» (что сделать: шаг C0.6, `build/owner-materials.md`); записи-строки (формат 1.4) пропускать. Нерешённые находки `idea.checks[]` (есть `options`, нет `idea.decisions[id]`) — предупреждение «решение владельца до старта не получено».
3. **`scripts/init_run.py --show/--status`** (FB-034, FB-040) — сверять текущую ветку (`git symbolic-ref --short HEAD`) с `output.git_branch`, показывать `output.branch_status` / `branch_note`; если в run-config есть `owner_rules.tasks_file` — по умолчанию вести чек-лист там (`--tasks-file`), `STRATEGY_TASKS.md` не создавать.
4. **`references/orchestration.md`, раздел «Git: особые случаи»** (FB-041, SM 6.5) — текст: «Состояние — `run-config.git.state` (пишет `intake.py concept-apply`): `unborn` — первый коммит в ветку прогона (`concept-apply` уже включил её), основная ветка создаётся при слиянии: `git switch -c main` от ветки прогона (или `git branch main docs/concept-<slug>`), `git push -u origin main`, затем ветка прогона сохраняется по правилам владельца; `no_repo` — работать вне git или `git init` по решению владельца и повторить `concept-apply`; ветка прогона создаётся скриптом только с основной ветки или в пустом репозитории (`output.branch_status`), иначе — вручную. Правила владельца — `run-config.owner_rules` (из CLAUDE.md)».
5. **`scripts/dispatch.py`** (FB-003) — `dispatch.py ready` выдаёт `effort` только при `run-config.tools.agents.effort_policy == "explicit"`; модель — по `tools.agents.model_policy` (`triage` → typesafe-triage, `default` → правила скилла, `custom` → `tools.agents.note`).
6. **`scripts/typesafe_concept.py`** (SM 4.3 C2) — в личном режиме (`project.audience` ∈ personal, circle, personal_then_public) вопросы `reach`/`revenue` заменить на «решит ли боль владельца быстрее обходного пути» и «реально ли поддерживать в одиночку» (факты: `idea.facets.personal_job, personal_frequency, support_hours_month, ownership_budget`); `feasible` — по `capacity.capacity(cfg, mvp_weeks/4.33)` и решению `idea.decisions.mvp_capacity`.
7. **`scripts/pivot_check.py --decide narrow`** (FB-044) — `concept_dossier.py --refresh` уже есть и читает `idea.version/pitch_v2/history` и `data/premises.json`. Если тема идеи изменилась — принять `--topic-en "<перевод>"` и записать `idea.topic_en` + `idea.topic_en_for = <новая версия>`; без него досье предупредит, что перевод относится к прежней версии, и вернёт заглушки `<EN: …>`. `data/idea.json → version` = версия идеи (так пишет и `concept_dossier.py`).
8. **`scripts/report.py` / `templates/report.md`** (FB-001, FB-002) — таблица «Вопросы запроса»: `idea.request_questions[]` → раздел/файл с маркером `[RQxx]` → короткий ответ; строки «Материалы владельца: N (прочитано / заблокировано / не прочитано)», «Решения до старта» (`idea.decisions`), «Нарезка на очереди» (`slicing.queues`).

## B (модель, сборка текста)

9. **`scripts/assemble_strategy.py`** (FB-001) — для каждого `idea.request_questions[]` с `kind ∈ {research, deliverable}` в собранном тексте должен быть маркер `[RQ01]`; нет — ошибка (в `--lenient` — предупреждение). Источник id — run-config (`idea.request_questions[].id`).
10. **`scripts/model.py`** — `product.forms` от WP-A: `web`, `mobile_web` (адаптив, PWA), `mobile`, `bot`, `desktop`, `extension`, `devtool`; формы «на потом» — `product.future_forms`. `select_profile` уже ловит `web`; `mobile_web` тоже означает оплату на сайте. `strategy.payment_channel` — из блока «Оплата» (`direct|store|donations|none`). Необязательный `project.tax_regime` WP-A не спрашивает (нет вопроса в фидбэках) — при необходимости `--set project.tax_regime=npd`.
11. **`scripts/facts_scaffold.py`** (FB-044, FB-048) — блок «ВЫВОДЫ ИССЛЕДОВАНИЯ» строить из `data/idea.json`: `pitch_v2`, `premises[]` (подтверждена / опровергнута / частично + источник), а «вопросы запроса» — из `request_questions[]`.

## C (реестр, контракт)

12. **`references/data-contract.md`, раздел «Режим идеи»** — дописать поля run-config (пишет `intake.py concept-apply`):
    - `project.audience: public|personal|circle|personal_then_public`, `project.release_outward: bool`, `project.audience_note`;
    - `project.capacity {hours_per_week (на человека), dev_share, day_hours, source}`; `registry {passes: 1|2, capacity_cap: bool, category_minimums: count|priority, auto_keys: []}`;
    - `product.forms[]`, `product.future_forms[]`, `strategy.markets_note`, `strategy.payment_channel: direct|store|donations|none`;
    - `tools.agents {model_policy: triage|default|custom, effort_policy: explicit|none, note?}`;
    - `idea.{request, request_questions[] {id, text, kind: research|deliverable|format, source}, keywords[], keywords_source: auto|owner, topic_en, topic_en_for, name_source: given|auto, interview_mode: standard|fast|deep, prefill_raw?, block_answers {id: {block, header, question, answer, custom, prefilled?, confirmed?}}, blocks_answered[], replaced[], checks[] {id, severity, message, header, question, options[{label, key, set}]}, decisions {id: ключ}, decisions_applied {}}`; `idea.answers[*]` — плюс необязательные `prefilled`, `confirmed`, `quote`, `confirmed_default`, `card_default`, `correction`, `exclusive_conflict`; вопросы личного режима — id `p01…p10`;
    - `idea.facets.*` блоков: platform_* (dependency, name, kind, urls[], data_needs[], access, allowed, fallback), data_* (sources_needed[], license, keys, fallback, jurisdiction, delivery, history), ai_* (role[], where, data, error_cost, guardrails[], hardware, eval, output, latency, observability[], security[], models, versioning), admin_* (who, settings[], backup, log, alerts, updates, roles, support, legal, needed), law_*/fin_*/crypto_*/health_*/children_*/pd_*, ui_*, prototype_needed, prototype_scope, stack, view, handoff_extras[], owner_repos[], owner_data, tool_limits[], personal_* (job, frequency, value), reliability_need, data_location, ownership_budget, support_hours_month, project_lifetime;
    - `design {pointer_first, directions_count, modes[], modes_decide_later?}`;
    - `sources.owner_docs[] {url|path, kind: platform_site|competitor|document|artifact|repo|data|other, role: base|follow|ref, status: not_attempted|read|blocked, tool, note, source}` (в 1.4 — строки; читатели принимают оба вида); `idea.facets.platform_urls[]`;
    - `git {state: no_repo|unborn|normal, has_origin, branch, default_branch, visibility}`, `output.branch_status: created|switched|current|skipped|failed|planned`, `output.branch_note`, `owner_rules {sources[], branch_per_task, merge, push_after_merge, delete_branches, tasks_file, language, lines[]}`;
    - `slicing {enabled, decision: slice|continue|refine|stop, source, mvp, cut_rule, queues[] {id: alpha|beta|v1|v2, name, goal, enter_when, months, capacity_days, capacity_line}, priorities[] {weak, label, cheap_test}}`;
    - `data/idea.json` — плюс `audience, release_outward, forms, future_forms, markets_note, request_questions, owner_docs, keywords, keywords_source, topic_en, topic_en_stale, capacity {dev_days, day_hours, hours_per_week, line}, block_answers, checks, slicing, idea_version, pitch_v2, history, premises, pivot_decision, pitch_effective, replaced`; `version` — версия идеи (1, после пивота 2…).
13. **`scripts/merge_proposals.py` / `check_registry.py`** — `registry.passes` от WP-A: 1 для quick и deep, 2 для standard и exhaustive (как в вашем запросе 16); `capacity_cap` — если MVP не помещается в ёмкость (`idea.decisions.mvp_capacity` или проверка), включена нарезка или личный режим; `category_minimums` — priority в личном режиме и при потолке.

## G (брифы)

14. **`templates/briefs/concept-analogs.md`** (FB-022) — карточка «self» в `data/competitors.json` получает имя из `{PRODUCT}` (= `run-config.product.name`, подтверждённое в сводке; `idea.name_source = given` — от владельца); при `name_source = auto` — пометка «рабочее имя».
15. **`templates/briefs/research-owner-refs.md`** (FB-002) — входы: `sources.owner_docs[]` с ролью и статусом, `build/owner-materials.md` (шаг C0.6); материалы с ролью `base` — только как основа вопросов.

## F (дизайн)

16. Поля от опроса (блок «Интерфейс»): `design.directions_count` (1–7), `design.modes[]` (`["beginner", "pro"]` или пусто), `design.modes_decide_later`, `design.pointer_first`, `product.future_forms` (мобильный «задел»), `idea.facets.doc_features[]` (hotspots, search, zoom). `design.chosen`/`chosen_by` WP-A не пишет.

## Оркестратор

17. Наблюдение при прогоне связанных тестов: `tests/test_concept.py::test_concept_demo_build_all_strict`, `tests/test_site_mode.py::test_concept_demo_build_all[site|single]`, `tests/test_core.py::test_build_all_new_steps_and_statuses` падают на шаге `flowcheck` («node_no_title 1: … элементом <g data-node> (текст — из nodes[].what)») — это `scripts/node/check_flow.mjs` / схема демо (WP-E, FB-038), а не опрос: файлы WP-A шаг `flowcheck` не затрагивают.
