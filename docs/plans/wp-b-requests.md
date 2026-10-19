# WP-B — запросы на правку чужих файлов

Каждый пункт: файл → что → зачем. Код WP-B уже поддерживает описанное (скрипты и тесты готовы: `capacity.py`, `model.py`,
`plan_baseline.py`, `decisions.py`, `facts_scaffold.py`, `summary_scaffold.py`, `assemble_strategy.py`), правки ниже замыкают процесс.

## WP-A (опрос и вход прогона)

1. **`scripts/intake.py` (`concept-apply`)** — FB-028, SM 6.1: записывать `project.capacity = {hours_per_week, dev_share, day_hours, source}`
   из ответа c32 (`idea.facets.hours_week`) или вопроса «Ёмкость»; `day_hours` — одна величина (по умолчанию 8), поле `project.hours_in_day`
   не вводить. `capacity.py` уже читает `idea.facets.hours_week` как запасной путь, но явное поле убирает разночтения.
2. **`scripts/intake.py` (банк вопросов)** — FB-026: вопрос «Как будете принимать оплату?» → `strategy.payment_channel`:
   `direct` (платёжный сервис на сайте: ЮKassa, CloudPayments…) | `store` (магазин приложений) | `donations` | `none`.
   Профиль модели по нему выбирает `model.select_profile(cfg)` (`direct` → `web-direct`, `store` → `mobile-app`, `donations` → `oss`).
   Для «веб + мобильная версия» (FB-024) писать `product.forms: ["web", "mobile"]` — при `product.type = mobile` и веб-форме
   модель тоже берёт `web-direct`.
3. **Сводка «Начинаю?» (`intake.py show` / concept-apply)** — FB-026: строка «Модель: <профиль> (<почему>)» —
   `import model; model.select_profile(cfg)` возвращает `(профиль, причина)`; и строка «Ёмкость: <capacity.capacity(cfg, horizon)['line']>».
4. **`project.audience`** (SM разд. 4) — уже в контракте; `model.py` по `personal | circle | personal_then_public` выбирает профиль `personal`.
   Необязательное поле `project.tax_regime` (`npd | usn6 | none`, рынок ru) — если владелец знает налоговый статус (вопрос 5.3/5.8 или
   «Резидентство»), модель возьмёт ставку из пакета локали.
5. **`scripts/concept_checks.py`** — `mvp_capacity` считает `per_week = hours_per_week × dev_share / day_hours` без `team_size`; с 1.5
   `capacity()` умножает на `team_size` (поле `team_size` в результате, `dev_days_month` — готовое значение). Брать `c["dev_days_month"]`
   или умножать на `c["team_size"]`, чтобы команда из 2+ человек не занижала ёмкость.

## WP-D (оркестрация, брифы, ворота)

6. **`scripts/render_brief.py`** — FB-028: плейсхолдер `{CAPACITY}` = `capacity.capacity(cfg, horizon)["line"]` во всех брифах авторов
   (strategy-section, specs, experiments, gap-audit, registry-generator); FB-046: `{PLAN_BASELINE}` = краткая сводка
   `plan_baseline.summary_lines(plan_baseline.load(out))` или «нет data/plan-baseline.json — запустите plan_baseline.py»;
   FB-049: перед рендером `strategy-section` запускать `decisions.py <OUT> --check` — нет файла → подсказка
   `facts_scaffold.py <OUT> --draft` (создаёт черновик решений).
7. **`scripts/build_all.py`** — FB-046: шаг `consistency` после `assemble`: `plan_baseline.py <OUT> --check` (с `--strict` сборки —
   `--check --strict`); шаг `baseline` до `facts`/`assemble`, если есть `data/gantt.json` и нет свежего `data/plan-baseline.json`
   (`plan_baseline.py <OUT>`). Сборка `assemble_strategy.py` уже сверяет то же и пишет `plan_consistency` в отчёт.
8. **`scripts/typesafe_concept.py`** — FB-028: оценку `feasible` строить на `capacity.capacity(cfg, months)` (`dev_days` за срок MVP),
   а не на сыром `facets.hours_week`, чтобы предпроверка и модель видели одну ёмкость.
9. **`scripts/init_run.py --status` / `report.py`** — показывать `model.json → reconciliation.items` (расхождения модели с планом
   и реестром) и `data/plan-baseline.json → gantt_contract.messages` (дыры в Ганте) как открытые пункты.
10. **`references/phases.md` (фаза 7 / C7)** — порядок: `gantt.json` → `plan_baseline.py <OUT>` → `facts_scaffold.py <OUT> --draft`
    (создаёт черновик `decisions.json`) → подтверждение решений (удалить `draft`) → снова `plan_baseline.py` → авторы разделов
    (сроки только `{plan:…}`) → `summary_scaffold.py <OUT> --to-part` → `plan_baseline.py <OUT> --check` → `assemble_strategy.py`.
    До волны макетов (C8): `facts_scaffold.py <OUT> --demo-canon`.

## WP-C (реестр, контракт данных)

11. **`references/data-contract.md`** — описать новые файлы и поля (тексты — в `references/decisions.md` §3а–3в, §7):
    `data/plan-baseline.json` (`start_date, capacity, milestones{beta,launch,mvp,paid,horizon_end}, mvp{ids, only_in_registry},
    kill[], north_star, goal, events[], architecture, months[{month, period plan|gap|vision, tasks, milestones, load_days,
    capacity_days, over_capacity}], gantt_contract{ok, gap_months, plan_months_without_tasks, over_capacity_months, messages}`);
    `data/demo-canon.json` (`values{ключ:{value, source}}, entities[], screens{}, rule`); `data/decisions.json → draft`;
    `data/model.json` — новые ключи `capacity` (все профили; `line, day_hours, dev_days_total, source…`), `illustration`,
    `scenarios.*.illustrative`, `reconciliation{items[]}`, `personal` (профиль personal), `breakeven_note`; задачи Ганта — необязательное
    поле `milestone: beta|launch|mvp|paid` (явная веха вместо распознавания по словам). Контракт Ганта: месяцы 1…горизонт и видение
    до горизонт + 12 × vision_years без пропусков.
12. **`references/scoring.md`** (раздел про модель) — профили `web-direct` и `personal`, `common.tax_rate` и `revenue_start_month`,
    блоки `illustration` / `reconciliation` (текст — `references/decisions.md` §7 и docstring `scripts/model.py`).

## WP-E (страница, графики)

13. **`scripts/charts.py`** — профиль `personal`: в `model.json` нет воронки, LTV и `monthly` в сценариях (графики `funnel`, `cac-ltv`,
    `payback`, `forecast-fan` пропускаются с причиной). Нужен график «Окупаемость личных усилий» по `model.json → personal.scenarios.*.monthly`
    (`cum_value` против `cum_cost`, подписи сценариев — `personal.scenario_labels`). Режим sensitivity-only: в подписи денежных
    графиков добавить «[иллюстрация при допущениях]» (`model.json → illustration.label`).
14. **Гант на весь горизонт (`charts.py ch_gantt`, страница)** — SM 6.1: рисовать все месяцы из `data/plan-baseline.json → months`
    (период `gap` — затенённая зона «после горизонта», `vision` — годы видения), вехи — `months[].milestones`; затенение видения —
    с месяца `horizon_months + 1`, а не жёстко после 12-го (сейчас подпись «после 12-го месяца» при горизонте 6 неверна).

## WP-F (макеты)

15. **`templates/briefs/{concept-design,mockups,design-refs}.md`, `templates/mockup-kit/`** — SM 11: «канон демо-данных»: числа,
    имена и даты демо — только из `data/demo-canon.json` (`facts_scaffold.py <OUT> --demo-canon` создаёт черновик до волны макетов);
    у элемента с числом — `data-canon="ключ"`; новые демо-сущности — в `entities` канона, а не в макете. `shoot_mockups.mjs`
    может сверять текст элементов `[data-canon]` со значениями канона.

## WP-G (брифы)

16. **`templates/briefs/strategy-section.md`, `specs.md`, `experiments.md`** — FB-046/FB-028: «сроки, состав MVP и ёмкость — только
    `{plan:beta}`, `{plan:launch}`, `{plan:mvp_ids}`, `{plan:kill.N.date}`, `{plan:capacity}`; другое определение рабочего дня
    сборка отметит (`workday_mismatch`)»; FB-027: «модель в режиме sensitivity-only — числа выручки/ROI/LTV только `{model:…}`
    (метку иллюстрации ставит сборка) или с меткой «[иллюстрация при допущениях]»».
17. **Бриф `templates/briefs/strategy-summary.md`** (FB-047, альтернатива) — вход: `build/strategy-summary.md` от
    `summary_scaffold.py <OUT>` (каркас с плейсхолдерами), задача агента — связки и формулировки без новых чисел и дат.
18. **Личный режим в брифах экспериментов/метрик** — для `model_profile = personal` плейсхолдеры `{model:base.value|money}`,
    `{model:base.net_value}`, `{model:base.breakeven_month}`, `{model:base.hours_saved_per_week_to_break_even|1}`
    (раздел 8 «Стоимость владения и порог окупаемости личных усилий»).
