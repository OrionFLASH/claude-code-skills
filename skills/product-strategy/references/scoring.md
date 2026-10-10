# Формулы оценки и веса по умолчанию

Единственный источник правды — `scripts/score.py` (`DEFAULT_WEIGHTS`); этот файл повторяет его дословно и правится в том же коммите. Независимая сверка — `scripts/validate_scores.py` (свой код, без импорта `score.py`). Якоря шкал 1–5 — в `references/methodology-anchors.md`.

Действующие веса прогона пишутся в `<OUT>/data/weights.json`. Порядок наложения: встроенные → прежний `data/weights.json` (если есть; `--reset-weights` его игнорирует) → файл `--weights` (частичный JSON, сливается рекурсивно). Убрать слагаемое — поставить вес 0. Свои подшкалы ценности и ключи риска можно добавить в веса: значение берётся из `scores.<ключ>` / `risks.<ключ>`, при отсутствии — из `value` / `risk`.

Обозначения: `s` = `scores` предложения; `clamp` — ограничение шкалы 1–5; `wmean(x, w)` = Σ xₖ·wₖ / Σ wₖ; `half_up(x)` = ⌊x + 0,5⌋.

## 1. Индексы (1–5)

### Ценность `value_index` (выше — лучше)
`value_index = wmean(подшкалы, W.value)`; нет подшкалы → берётся `s.value`. Если в предложении есть только `value`, индекс равен `value`.

| ключ | вес | | ключ | вес |
|---|---|---|---|---|
| value (экспертная) | 2,0 | | revenue | 1,0 |
| reach | 1,0 | | virality | 0,6 |
| impact | 1,0 | | seo | 0,6 |
| acquisition | 0,8 | | trust | 0,6 |
| activation | 1,0 | | moat | 0,8 |
| conversion | 1,0 | | fit | 0,8 |
| retention | 1,0 | | demand | 1,0 |
| | | | season | 0,4 |

### Стоимость `cost_index` (выше — дороже)
`cost_index = wmean(части, W.cost)`; числовые поля переводятся в 1–5 по порогам `maps` (значение ≤ k-го порога → балл k, больше всех порогов → 5); нет поля → берётся `s.cost`.

| часть | вес | источник | пороги → 1, 2, 3, 4 (иначе 5) |
|---|---|---|---|
| cost | 2,0 | `s.cost` | — |
| effort_days | 1,5 | середина `effort_days` | ≤ 2, 5, 15, 40 чел.-дней |
| money | 0,8 | `cost_money.max` | ≤ 0, 500, 5 000, 25 000 (в валюте предложения, без конвертации) |
| time_to_result | 0,8 | `time_to_first_result_days` | ≤ 7, 30, 90, 180 дней |
| dependencies | 0,4 | число `dependencies` | ≤ 0, 1, 2, 3 |

### Риск `risk_index` (выше — опаснее)
`risk_index = wmean(части, W.risk)`; ключ `risks.*` отсутствует → берётся `s.risk`.

| часть | вес | | часть | вес |
|---|---|---|---|---|
| risk (экспертный) | 2,0 | | privacy | 1,2 |
| legal | 1,2 | | tech | 0,8 |
| ip | 1,0 | | reputation | 1,0 |
| platform | 1,0 | | | |

## 2. Уверенность `confidence_calc` (0…1)
```
confidence_calc = 0,6·E(evidence_class) + 0,25·testability/5 + 0,15·(6 − spread)/5
E: A = 1,0 · B = 0,8 · C = 0,55 · D = 0,35   (неизвестный класс → как D)
testability = s.testability (1–5: 5 — проверяется за день без кода), по умолчанию s.confidence
spread      = s.spread      (1–5: 1 — независимые оценки сходятся), по умолчанию 3
```
Смысл слагаемых: сила доказательства (60 %), возможность дёшево проверить (25 %), согласие оценщиков (15 %). Без `testability`/`spread` экспертная `confidence` работает как проверяемость, а разброс считается средним.

## 3. Составные показатели
| показатель | формула |
|---|---|
| RICE | `reach_units[half_up(reach)] × impact_map[half_up(impact)] × confidence_calc / max(effort_mid, 0,5)`; `effort_mid` — середина `effort_days`, нет поля → `5·s.cost`; `reach`, `impact` — подшкалы (по умолчанию `value`) |
| reach_units | 1 → 50 · 2 → 300 · 3 → 1 250 · 4 → 6 000 · 5 → 20 000 условных пользователей/мес (оценка; калибровать данными) |
| impact_map | 1 → 0,25 · 2 → 0,5 · 3 → 1 · 4 → 2 · 5 → 3 (конвенция Intercom) |
| ICE | `value_index × (confidence_calc·5) × (6 − cost_index)` — влияние × уверенность × лёгкость |
| WSJF | `cost_of_delay / cost_index`; `cost_of_delay = BV + TC + RR`: BV = `value_index`; TC (срочность) = `(season + (6 − балл time_to_result)) / 2`; RR (снижение риска / открытие возможностей) = `(moat + trust) / 2` |
| value_per_effort | `value_index / cost_index` |
| risk_adjusted | `value_index × (1 − 0,5·(risk_index − 1)/4)` — риск 5 срезает до половины ценности |
| composite | `Σ wₖ·n(xₖ) / Σ wₖ`, n — минимакс-нормировка 0–1 по реестру (все равны → 0); **RICE нормируется по `log(1 + RICE)`** (тяжёлый хвост) |

Веса composite: RICE 0,30 · ICE 0,20 · WSJF 0,25 · risk_adjusted 0,25.

Ранг — по убыванию `round(composite, 9)`, при равенстве — по id. В `scores.json` значения округлены (composite — до 6 знаков), ранги считаются по неокруглённым.

## 4. Квадрант, приоритет, MoSCoW
- **Квадрант** по медианам реестра: `value_index ≥ медианы` и `cost_index ≤ медианы` → `quick_win`; ценность ≥, стоимость > → `big_bet`; ценность <, стоимость ≤ → `filler`; иначе `money_pit`.
- **P0** — первые `max(1, half_up(0,15·N))` предложений по рангу **только из `quick_win` и `big_bet`** (иначе P0 забивают дешёвые заполнители). Остальные по доле ранга q = rank/N: q ≤ 0,40 → P1, q ≤ 0,70 → P2, иначе P3.
- **MoSCoW**: P0 → must, P1 → should, P2 → could, P3 → wont.

## 5. Метки
| метка | условие |
|---|---|
| important | `value_index ≥ 3,6` |
| effective | `value_per_effort ≥` значения на позиции `int(0,75·N)` отсортированного по возрастанию списка (верхняя четверть) |
| expensive | `cost_index ≥ 3,6` или `cost_money.max ≥ 10 000` |
| risky | `risk_index ≥ 3,0` |
| fast | `time_to_first_result_days ≤ 14` (нет поля → `s.cost ≤ 2`) |
| slow | `time_to_first_result_days ≥ 90` (нет поля → `s.cost ≥ 4`) |
| strategic | подшкала `moat ≥ 4` и `horizon ∈ {next, later, vision}` |
| tempting_weak | `value_index ≥ 3,3` и (`confidence_calc < 0,55` или класс D) |

## 6. Чувствительность (`data/sensitivity.json`)
Каждый вес групп `composite`, `value`, `cost`, `risk` поочерёдно умножается на 0,5 и 1,5 (прочие веса прежние), реестр переранжируется.
- `tornado[]`: `param` (`группа.ключ`), `low_rank_shift` / `high_rank_shift` — средний модуль сдвига ранга по всем предложениям при ×0,5 / ×1,5, `low_top_overlap` / `high_top_overlap` — сколько из базового топ-N осталось, `swing` = сумма сдвигов; сортировка по `swing`.
- `top20_stability` — доля базового топ-N (N = min(20, число предложений)), не выпавшая из топ-N **ни в одном** прогоне; `always_top20` — эти id; `runs` — число прогонов.

## 7. TypeSafe Jev (необязательно)
`typesafe_eval.py` пишет `data/typesafe-jev.json`; `score.py` кладёт оценку предложения в поле `typesafe` (ошибка запроса или нет оценки → `null`). **В composite, ранги и приоритеты не входит** — отдельная колонка для сверки. Вопросы: `p_success`, `p_user_value`, `risk`, `p_fit`, `p_cheap_test`, `p_acquisition`, `p_revenue` (вероятности 0–1), `impact`, `effort` (1–5, уровень ответа + 1), `kano` (must | linear | delight | indifferent).

## 8. Модель юнит-экономики (`model.py`)
Параметры — `build/model-params.json` (создаётся с допущениями по умолчанию), каждый вход `{value, label, note}`. Существующий файл — источник правды; если `project.currency` в run-config с ним расходится, `model.py` предупреждает (удалить файл — пересоздать).

**Валюта и подсказки** (только при создании файла): валюта — `project.currency` (иначе USD). Денежные дефолты (`price_month`, `price_one_time`, `fixed_cost_month`, `cost_per_paid_signup`, ставка часа) пересчитываются пресетом валюты: USD-значение × множитель уровня цен, округление до двух значащих цифр — это допущение, не курс. Множители: USD 1 · EUR 0,92 · GBP 0,8 · RUB 32 · KZT 230 · UAH 16 · BYN 1,2 · PLN 2,6 · INR 25 · BRL 2,5 · TRY 15 · CNY 3,5 · JPY 110; нет пресета → суммы в масштабе USD и заметка в `notes`. `project.price_hint` → `price_month` (метка «оценка»); `project.traffic_hint` → `visitors_month` базового сценария, пессимистичный ×0,5, оптимистичный ×3. В `model.json` добавлены `currency_symbol` и `profile`.

Помесячно m = 1…горизонт:
```
visitors_m   = visitors_month·(1 + traffic_growth)^(m−1)
signups_m    = visitors_m·visit_to_signup + referred_{m−1}
activated_m  = signups_m·signup_to_active
active_m     = active_{m−1}·retention_monthly + activated_m
new_paying_m = activated_m·active_to_paying
paying_m     = paying_{m−1}·(1 − churn_monthly) + new_paying_m        (подписка; разовая: = new_paying_m)
revenue_m    = paying_m·price_month  |  new_paying_m·price_one_time
net_m        = revenue_m·(1 − payment_fee)·(1 − refund_rate)
referred_m   = active_m·referral_rate
cost_m       = fixed_cost_month + signups_m·paid_share·cost_per_paid_signup
CAC  = Σ маркетинга / Σ new_paying            ARPU = Σ net / Σ active      ARPPU = Σ net / Σ paying
LTV  = price_month·(1 − fee)(1 − refund)·gross_margin·min(1/churn, ltv_cap_months)          (подписка)
     = price_one_time·(1 − fee)(1 − refund)·gross_margin·(1 + repeat_purchase_rate)           (разовая)
payback_months  = CAC / (price_month·(1 − fee)(1 − refund)·gross_margin); 0 при CAC = 0; нет платящих → null
                  (разовая покупка: 0, если LTV ≥ CAC, иначе null)
breakeven_month = первый месяц, где Σ net·gross_margin ≥ Σ cost
ROI  = (Σ net·gross_margin − Σ cost) / Σ cost
```
Воронка AARRR (`funnel`) — суммы за горизонт: посетители, активированные, средняя активная база, новые платящие, регистрации по приглашениям.

### Профиль «нулевой бюджет, один разработчик» (`strategy.profile: zero-budget-solo`)
Платных каналов нет (`paid_share = 0`), дефолтный трафик 300 / 800 / 2 500 посетителей в первый месяц (рост 3 / 6 / 10 %), постоянные затраты 0 / 6 / 12 USD × множитель валюты. Параметры блока `solo` (все — допущения, правятся в `model-params.json`): `days_per_month` 12, `hours_per_day` 6, `team_size` = `project.team_size` (1), `hourly_rate` — ставка часа из пресета валюты (USD 40, RUB 1 500 …), `growth_time_share` 0,3, `support_hours_per_paying_month` 0,5, `support_hours_per_active_month` 0,02, `support_capacity_alert` 0,5.
```
ёмкость_ч/мес          = team_size · days_per_month · hours_per_day
hours_per_activated    = ёмкость_ч/мес · месяцев · growth_time_share / Σ activated          (вместо CAC)
support_hours_m        = paying_m · support_hours_per_paying_month + active_m · support_hours_per_active_month
support_capacity_month = первый m: support_hours_m / ёмкость_ч/мес ≥ support_capacity_alert
margin_after_support   = price_month·(1 − fee)(1 − refund)·gross_margin − support_hours_per_paying_month·hourly_rate
                         (≤ 0 → support_eats_revenue = true; разовая покупка — против поддержки за 12 мес.)
free_actives_per_paying = margin_after_support / (support_hours_per_active_month·hourly_rate)
time_breakeven_month   = первый m: Σ net·gross_margin ≥ m·ёмкость_ч/мес·hourly_rate + Σ fixed_cost   (безубыточность по времени)
revenue_per_hour       = (Σ net·gross_margin − Σ fixed_cost) / (ёмкость_ч/мес · месяцев)
capacity.dev_days_available = team_size·days_per_month·месяцев − Σ support_hours(база) / hours_per_day
capacity.p0_p1         = предложения P0–P1 по dep_rank (иначе rank) с серединой effort_days; помещаются — строгий префикс,
                         сумма середин ≤ dev_days_available; utilization = Σ середин / dev_days_available
```
В сценариях: `roi` = «неприменимо (нулевой бюджет)» + `roi_note`, `cac` = null + `cac_note`, `ltv_cac` и `payback_months` = null. Всё профильное — `model.json → solo` (`params`, `support`, `scenarios.<s>.{hours_per_activated, revenue_per_hour, time_breakeven_month, support_hours_total, support_capacity_month, dev_hours, time_cost, monthly[]}`, `capacity`) и копия `capacity` на верхнем уровне. Графики: `cac-ltv` — часы на активированного и выручка на час против ставки; `payback` — накопленная валовая выручка против стоимости времени. При малом числе платящих (базовый сценарий < 50 новых за горизонт) подписи `cac-ltv`/`payback` в любом профиле содержат абсолютные суммы: «базовый сценарий за N мес.: X новых платящих, Y чистой выручки». Профиль `standard` считает как выше без изменений.

## 9. Зависимости и ранг с их учётом (`score.py`, сверка — `validate_scores.py`)
Обычный `rank` не меняется. Граф: предпосылки предложения = `dependencies` (только существующие id, без самоссылок) ∪ `data/gap-audit-deps.json` `{id: [предпосылка…]}` (аудит пробелов, фаза 5.5); неизвестные ссылки печатаются и пропускаются. Ребро `[a, b]` — «a нужно сделать до b».

- **Циклы:** компоненты сильной связности (≥ 2 узлов); внутри компоненты остаются только рёбра, где предпосылка выше по рангу (`rank(a) < rank(b)`), остальные снимаются (`critical-path.json → cycles, dropped_edges`, stdout, `registry-check.json → dependency_cycles`). Детерминированно, граф после разрыва ацикличен.
- **`blocked_by`** — все транзитивные предпосылки, **`unlocks`** — все транзитивно разблокируемые; оба списка по возрастанию `rank`.
- **Бонус разблокировки:** `dep_bonus(v) = min(bonus_cap, unlock_bonus · Σ_{q ∈ unlocks(v)} composite(q) · decay^(d(v,q) − 1))`, d — длина кратчайшего пути.
- **`dep_score = composite + dep_bonus`; приоритет с наследованием:** `eff(v) = max(dep_score(v), max_{q ∈ unlocks(v)} dep_score(q))` — предпосылка получает приоритет самого ценного, что она открывает.
- **`dep_rank`** — топологический порядок (Кан): из предложений, у которых все предпосылки уже размещены, берётся наибольший `round(eff, 9)`, затем `round(dep_score, 9)`, затем меньший `rank`. Предложение никогда не стоит выше своей предпосылки.
- **Критический путь** (`critical_path: true`, `data/critical-path.json → order`): в замыкании топ-N (`critical_top_n`, N = min(20, число предложений): топ-N и все их предпосылки) — цепочка по рёбрам из ≥ 2 звеньев с наибольшей суммой composite, оканчивающаяся в топ-N; при равенстве — длиннее, затем лучший ранг. Нет рёбер — путь пуст.
- **`data/critical-path.json`:** `{order, edges (все рёбра замыкания), top_n, value, nodes[{id, rank, dep_rank, title, in_top, critical}], cycles, dropped_edges, unknown, warnings, params}`.
- **Предупреждение:** предложение из топ-`warn_top` (20), у которого среди `blocked_by` есть предложение ниже топ-`warn_below` (60) — stdout (последняя строка вывода `score.py` — сводка для `build_all`), `critical-path.json → warnings`, `registry-check.json → dependency_warnings`.

Веса (`weights.json → dependency`): `unlock_bonus` 0,10 · `decay` 0,5 · `bonus_cap` 0,15 · `critical_top_n` 20 · `warn_top` 20 · `warn_below` 60. В чувствительность (§6) не входят.

## 10. Сходство при слиянии черновиков (`merge_proposals.py`)
Нормализация: нижний регистр, ё → е, слова `[a-zа-я0-9]+`, стоп-слова RU/EN (служебные и общие глаголы «сделать/добавить/выпустить…»), лёгкая «обрезка» окончаний RU/EN, основа до 7 (RU) / 8 (EN) знаков. tf = 1 + ln f, idf = ln((1 + N)/(1 + df)) + 1 по всем черновикам прогона.
```
балл = 0,25·cos_tfidf(названия) + 0,15·Жаккар(символьные триграммы названий) + 0,20·cos_tfidf(описания)
     + 0,10·Жаккар(основы описаний) + 0,30·cos_tfidf(название ×2 + описание + теги)
```
Слияние: балл ≥ 0,275 (`--threshold`) или Жаккар основ названий ≥ 0,75 (`--title-threshold`); группы — одиночная связь, новая связь принимается при среднем сходстве групп ≥ 0,5·порога и размере группы ≤ 5. Порог откалиброван на реальном прогоне: 139 кандидатов, 14 известных слияний — найдено 12, ложных 0; на тех же черновиках после ручной чистки (125) — 0 слияний. Победитель: не ронять минимумы категорий (`check_registry.category_requirements`), максимум слитых, категория с запасом ≤ 2 над минимумом, лучший класс доказательств, полнота описания, порядок.

