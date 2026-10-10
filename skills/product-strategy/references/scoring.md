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
Параметры — `build/model-params.json` (создаётся с допущениями по умолчанию), каждый вход `{value, label, note}`. Помесячно m = 1…горизонт:
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
