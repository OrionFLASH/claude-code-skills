# Решения стратегии, плейсхолдеры, выборки и сверка фактов

Решения оркестратора (три ставки, критерии отказа, pre-mortem, North Star, анти-цели, развилки, ёмкость) живут в одном
файле — `data/decisions.json`. Авторы разделов не пересказывают их, а ставят плейсхолдеры; `assemble_strategy.py`
подставляет значения при каждой сборке. Порог поменяли в одном месте — он поменялся во всех разделах.

## 1. `data/decisions.json`

Заготовка: `python3 <SKILL_DIR>/scripts/decisions.py <OUT> --init` (из `templates/decisions.example.json`, P-id ставок —
лидеры P0 по `dep_rank`). **Черновик из данных прогона** (режим идеи — по умолчанию, FB-048/049):
`decisions.py <OUT> --init --draft` или `facts_scaffold.py <OUT> --draft` (создаёт файл, если его нет). Проверка:
`decisions.py <OUT> --check` (код 1 — ошибки схемы; черновик — предупреждение).

Откуда черновик берёт значения (у каждого — источник в `draft.sources`, в факт-листе — метка `[черновик: источник]`):

| Решение | Источник |
|---|---|
| три ставки | лидеры P0 (иначе P1) по `composite` в трёх разных категориях `scores.json`, внутри — порядок `dep_rank`; название, что, почему, эффект — из `proposals.json` лидера |
| критерий отказа | метрика и порог — `effect_kpi` лидера (нижняя граница диапазона «30–50 %»), иначе `cheap_test` («≥ 8 из 200», «5 %»); порог не найден — `kind: other` с текстом проверки; дата — запуск из `plan-baseline.json` + 8 недель (не позже конца горизонта) |
| pre-mortem | `risks.note` предложений ставки + «дешёвая проверка не подтвердилась» |
| North Star | `data/north-star.json`, иначе KPI предложения `analytics` про North Star, иначе `strategy.success_criteria` |
| анти-цели | опровергнутые предпосылки `data/premises.json`, затем P3 / vision с наибольшими усилиями |
| запреты | `strategy.constraints` и строки `research/legal.md` с «запрещено / нельзя / без согласия» |
| развилки | нумерованные вопросы `research/questions-owner.md` (вариант «(по умолчанию)» — в `default`) |
| ёмкость | `scripts/capacity.py` (строка `text` — та же, что в модели, плане и брифах) |

Подтвердили — удалите поле `draft`: метки в факт-листе станут `[решение: decisions.json]`, предупреждение `decisions_draft`
сборки исчезнет.

| Поле | Что | Обязательно |
|---|---|---|
| `bets[]` | 1–3 ставки (по методике три) | да |
| `bets[].id`, `name` | номер 1…3 и короткое название | да |
| `bets[].what`, `why`, `effect`, `attention_share` | что делаем, почему, ожидаемый эффект с меткой, доля внимания (0…1) | нет |
| `bets[].proposals` | P-id ставки (есть в `proposals.json`) | желательно |
| `bets[].kill` | критерий отказа: `metric`, `threshold`, `date` (YYYY-MM-DD) | да |
| `kill.baseline` | значение метрики, если ставка ничего не изменит (сейчас); без него измеримость не посчитать | желательно |
| `kill.direction` | `below` (останавливаем, если ниже порога; по умолчанию) или `above` | нет |
| `kill.kind` | `share` — доля 0…1 (по умолчанию), `rate` — события в неделю, `other` — без расчёта | нет |
| `kill.population` | чей поток даёт выборку для `share`: `visitors`, `installs`, `signups` (по умолчанию), `activated`, `new_paying` | нет |
| `kill.traffic_per_week`, `unit`, `text`, `alpha`, `power` | свой трафик; единица порога; готовая фраза вместо собранной; α и мощность | нет |
| `bets[].premortem` | 3 причины провала: строки или `{cause, signal}` | желательно |
| `north_star` | `{metric, definition, target, inputs[]}` | `metric` |
| `anti_goals` | 3–5 строк или `{text, why}` | желательно |
| `forks[]` | развилки владельца `{id: F1, question, default, cost, decision}` | нет |
| `capacity` | ёмкость `{team_size, hours_per_week, dev_share, day_hours, dev_days, text, note}` — `--init` берёт из `capacity.py` | нет |
| `bans` | запреты для авторов | нет |
| `draft` | `{generated, by, note, sources {путь: источник}}` — черновик; удаляется после подтверждения | нет |

`facts_scaffold.py` заполняет блоки «Три главные ставки» и «North Star, анти-цели, развилки, ёмкость» из этого файла
(с измеримостью критериев), а не заготовками `<заполнить>`.

## 2. Плейсхолдеры

Подставляет `assemble_strategy.py` после `{rank:…}`; в инлайн-коде и ограждённых блоках не трогаются. Полный список
ключей с текущими значениями — `assemble_strategy.py <OUT> --list-placeholders` (или `decisions.py <OUT> --list-placeholders`).

| Плейсхолдер | Значение |
|---|---|
| `{bet:1.name}`, `{bet:1.what}`, `{bet:1.pids}`, `{bet:1.share}` | название, что, P-id через запятую, доля внимания |
| `{bet:1.kill}` | фраза «доля активации ниже 33 % к 31.03.2027» |
| `{bet:1.kill.metric}`, `.threshold`, `.baseline`, `.date` | части критерия |
| `{bet:1.kill.n}`, `{bet:1.kill.weeks}`, `{bet:1.kill.status}` | выборка, срок, «наблюдаем / ненаблюдаем» (расчёт ниже) |
| `{bet:1.premortem}`, `{bet:1.premortem.2}` | все причины через «;» или одна |
| `{north_star}`, `{north_star.target}`, `{north_star.definition}`, `{north_star.inputs}` | North Star |
| `{anti_goals}`, `{anti_goals.1}` | анти-цели через «;» или одна |
| `{fork:F1}`, `{fork:F1.default}`, `{fork:F1.cost}` | развилка |
| `{capacity}`, `{capacity.team_size}`, `{bans}` | ёмкость, запреты; без `decisions.capacity` — строка `capacity.py` |
| `{plan:beta}`, `{plan:launch}`, `{plan:mvp}`, `{plan:paid}`, `{plan:horizon_end}` | вехи из `data/plan-baseline.json` (дата «12.01.2027» или «январь 2027»; `.month`, `.date`, `.mon`, `.id`) |
| `{plan:mvp_ids}`, `{plan:mvp_count}`, `{plan:mvp_effort_days}` | состав MVP по Ганту |
| `{plan:kill.1.date}`, `{plan:kill.1.metric}` | даты критериев отказа (из решений, пересчитанные базовой линией) |
| `{plan:capacity}`, `{plan:capacity.dev_days}`, `{plan:capacity.dev_days_month}`, `{plan:day_hours}` | ёмкость за горизонт и в месяц |
| `{plan:start}`, `{plan:end}`, `{plan:goal}`, `{plan:north_star}`, `{plan:arch}`, `{plan:event.1}` | старт, конец горизонта, цель, North Star, выбранная архитектура, окна событий |
| `{model:base.ltv}`, `{model:pess.cac}`, `{model:opt.cac_paid}` | метрики сценария (`pess`/`base`/`opt` или полные имена) |
| `{model:base.net_revenue}`, `{model:base.users_last}`, `{model:base.paying_last}` | итоги и последний месяц |
| `{model:base.price_month}`, `{model:capacity.dev_days_total}`, `{model:currency}` | допущения, ёмкость, валюта |
| `{exp:E01.n}`, `{exp:E01.weeks}`, `{exp:E01.status}`, `{exp:K1.weeks}` | выборка и срок эксперимента или критерия |

Формат после `|`: `{model:base.ltv|money}` — с символом валюты; `{model:base.churn|%}` — доля в проценты (`|%1` — один знак);
`{…|0}`, `{…|1}`, `{…|2}` — знаков после запятой. Числа — по-русски: «12 346», «3,46».

Ошибки сборки: неизвестный ключ, нет нужного файла (`decisions.json`, `model.json`, `experiments.json`, `plan-baseline.json`).
Модель в режиме `sensitivity-only` (нет данных об аудитории): к `{model:…}` итогов (выручка, ROI, LTV, CAC, окупаемость,
безубыточность, база, платящие) сборка сама дописывает метку «[иллюстрация при допущениях]» — одну на строку; входы-допущения
(`{model:base.price_month}`) не помечаются. Буквальное число рядом со словами «выручка / доход / ROI / LTV / окупаемость» без
этой метки — предупреждение `illustration_unlabeled` (с `--strict` — ошибка). В `model.json` такие итоги помечены
`illustrative: true` и собраны в блок `illustration` (FB-027).

## 3. Сверка текста с решениями

Значения, вставленные плейсхолдерами, всегда совпадают с файлом. Буквальные значения проверяются эвристикой:
абзац (пункт списка, строка таблицы), где упомянута ставка («Ставка 1» или её название) и критерий отказа
(«критерий отказа», «останавливаем», «kill» или имя метрики), с порогом — число с % / п. п. или после «ниже / выше /
порог / не менее…» — или с датой, которые не совпадают с `bets[].kill`, — предупреждение `decision_mismatch` с файлом
части и строкой; с `--strict` — ошибка. То же для North Star: «North Star — «…»» с другим названием и «цель N» с другим числом.
Лечение — заменить буквальное значение плейсхолдером.

## 3а. Базовая линия плана: `plan_baseline.py` (FB-046)

Один источник сроков, ёмкости и состава MVP для всех частей текста. Порядок в фазе 7: `gantt.json` (и раздел 14) → 
`plan_baseline.py <OUT>` → `decisions.py --init --draft` (или `facts_scaffold.py --draft`) → снова `plan_baseline.py` (подтянет
даты критериев отказа) → `facts_scaffold.py` → авторы разделов (сроки — только `{plan:…}`) → `summary_scaffold.py` (раздел 1) →
`plan_baseline.py <OUT> --check` → сборка.

- `data/plan-baseline.json`: `start_date` (`strategy.start_date`, иначе `created`; месяц 1 — с даты старта, дальше календарные
  месяцы), `capacity` (capacity.py), `milestones` (`beta`, `launch`, `mvp`, `paid` — по полю `milestone` задачи Ганта, иначе по
  словам «бета», «запуск/релиз», «MVP», «оплата/монетизация» у контрольных точек; дата — из текста задачи «дд.мм.гггг», если
  попадает в месяц, иначе первое число месяца; `horizon_end`), `mvp` (P-id задач до вехи `launch`; `only_in_registry` — с тегом
  `mvp`, но не в Ганте до запуска), `kill`, `north_star`, `goal`, `events` (окна событий в горизонте), `architecture`
  (выбранный вариант `data/integration-options.json`: `chosen`/`recommended`, иначе лучшее «ценность / дни»), `months`,
  `gantt_contract`.
- **Контракт Ганта на весь горизонт:** `months` — каждый месяц 1…горизонт и видения до горизонт + 12 × `vision_years` с
  периодом `plan | gap | vision`, задачами, вехами, нагрузкой (середина `effort_days` поровну по месяцам задачи) и ёмкостью
  месяца. `gantt_contract.gap_months` — «дыры» (например, 7–12 при горизонте 6 и видении с 13), `plan_months_without_tasks`,
  `over_capacity_months` (нагрузка > ёмкость × 1,3); сообщения печатаются и попадают в факт-лист. Рендер всех месяцев — по `months`.
- `plan_baseline.py <OUT> --check [--strict]` → `build/consistency-report.json` (то же делает каждая сборка `assemble_strategy.py`):
  `plan_mismatch` — дата сразу после слова вехи («бета 15.05.2027», «запуск — в июне 2027», «месяц 5») не совпадает с месяцем
  вехи (даты внутри меток `[факт: …, 2026-10-17]` и через границу ячейки таблицы не считаются); `kill_date_mismatch`;
  `capacity_mismatch` — «ёмкость … N дн.» не совпадает с ёмкостью за горизонт или к месяцу k (допуск 5 %); `workday_mismatch` —
  другое определение рабочего дня, чем `project.capacity.day_hours` (без базовой линии проверяется только оно); `mvp_mismatch` —
  «В MVP: …», «состав MVP», строка таблицы с релизом «MVP-0/MVP-1» называют P-id не из `mvp.ids`. С `--strict` — код 1.

## 3б. Черновик раздела 1: `summary_scaffold.py` (FB-047)

`summary_scaffold.py <OUT>` → `build/strategy-summary.md`; `--to-part` — `build/parts/strategy-01.md` (если части нет, иначе
`--force`). Структура по `concept-outline.md` (идея, пересмотр идеи по `premises.json` / `idea.pitch_v2`, вердикт светофора,
цель горизонта, план, три ставки с критериями отказа и pre-mortem, анти-цели, развилки, топ-10, деньги или стоимость владения,
вставки графиков, первые 30 дней); все числа и даты — плейсхолдеры `{plan:…}`, `{bet:…}`, `{model:…}`, `{deprank:…}`, поэтому
проверка согласованности по разделу 1 проходит без расхождений. Связки пишет оркестратор или агент резюме.

## 3в. Канон демо-данных: `data/demo-canon.json`

До волны макетов и прототипа — `facts_scaffold.py <OUT> --demo-canon` (не перезаписывает файл): `values {ключ: {value, source}}`
— название продукта, валюта, входы и итоги базового сценария модели (с пометкой «иллюстрация» в sensitivity-only), вехи плана,
названия ставок, North Star, ёмкость; `entities` (демо-имена, предметы, тикеры) и `screens` (какие значения на каком экране)
дописывает оркестратор. Правило: все макеты, прототип и примеры текста берут демо-числа только отсюда; в HTML макета у
элемента с числом — `data-canon="ключ"`; демо помечается «демо». Факт-лист показывает канон отдельным блоком.

## 4. Выборки и измеримость: `sample_size.py`

- Калькулятор: `sample_size.py --baseline 0.05 --mde 0.01 --alpha 0.05 --power 0.8 --traffic 200` → n на группу (z-тест
  двух долей), срок набора при трафике (в неделю; `--per day|month`), `--relative` — относительный MDE, `--kind rate` —
  события в неделю (Пуассон), `--simulate 2000 --peeks 4` — доля ложных тревог в A/A при подглядывании.
- Эксперимент в прогон: `sample_size.py <OUT> --add E01 --baseline … --mde … --title … --proposal P001 [--population signups]`
  → `data/experiments.json` (`n_per_arm`, `n_total`, `weeks`, `status`); без `--traffic` поток берётся из `model.json`
  (базовый сценарий, среднее в месяц ÷ 4,345). `--recalc` — пересчитать после смены модели.
- Критерии отказа: `sample_size.py <OUT> --criteria` — для каждой ставки n и срок: доля — одна выборка против порога
  (односторонний z, p₀ = порог, p₁ = baseline), события — два равных периода (Пуассон). Нужный срок больше времени до
  `kill.date` (или горизонта), нет трафика → «ненаблюдаем». Результат — `experiments.json → criteria` (ключи `K1…`).
  `assemble_strategy.py` считает то же при каждой сборке (`kill_unobservable`, с `--strict` — ошибка; отчёт `kill_criteria`).
- Правило текста: любая выборка и срок — только `{exp:…}` или `{bet:N.kill.n|weeks}`; ненаблюдаемый критерий —
  поменять порог, дату или метрику (ближе к воронке), либо прямо написать «ненаблюдаем, решаем качественно: …».

## 5. Числа без метки и повторы

- `assemble_strategy.py` печатает первые `--show` (10) мест «файл части:строка (раздел N): фрагмент»; полный список —
  `build/assemble-report.json → unlabeled_numbers`. `--label-unlabeled` дописывает « [допущение]» в конец каждого
  такого фрагмента в исходной части (в таблице — в последнюю ячейку) и печатает правки.
- Не считаются числами без метки (FB-030): значения плейсхолдеров; числа (с той же единицей — % или деньги), которые есть в
  факт-листе `build/strategy-facts.md` или в значениях решений, экспериментов и базовой линии; числа из `effect_kpi`,
  `cost_money`, `cheap_test` предложения в той же строке, где назван его P-id; строки таблиц, в заголовке которых есть колонка
  «Источник» / «Метка»; параметры метода («мощность 80 %», «α = 5 %»). Значения модели целиком не используются (слишком много
  случайных совпадений) — они попадают через таблицу сценариев факт-листа.
- Повторы: абзацы ≥ 20 слов из разных разделов с долей общих 5-словных шинглов ≥ 0,6 → `repeated_text`
  «раздел A ↔ раздел B» с файлами и строками; общие числа с %/деньгами в разделах 2/3/6/7 — `repeats.numbers` только если
  совпадает и контекст (≥ 2 общих слова в ±5 словах вокруг числа, без меток), прежний список «по значению» —
  `repeats.numbers_value_only`.

## 7. Ёмкость и модель: одно определение (FB-028, SM 6.1)

- Ёмкость считает только `scripts/capacity.py` → `capacity(cfg, months)`: `project.capacity {hours_per_week, dev_share,
  day_hours, team_size}`, иначе ответ опроса `idea.facets.hours_week`, иначе `project.capacity_days_month` (режим стратегии,
  `dev_share = 1`), иначе 10 ч/нед × 70 % ÷ 8 ч. Строка `line` («15 ч/нед × 70 % на разработку = 10,5 ч/нед ≈ 1,3 дня по 8 ч;
  за 6 мес. ≈ 34,1 дн. разработки») — одна для модели (`model.json → capacity`), базовой линии, решений, факт-листа и брифов
  (`capacity.py <OUT> --line`). Поле `project.hours_in_day` не вводится; `solo.days_per_month / hours_per_day` прежних
  `model-params.json` ёмкость не задают (заметка в `model.json`).
- Профили модели 1.5 (`model.py`): `web-direct` — веб/PWA с оплатой напрямую через платёжный сервис (выбор:
  `strategy.payment_channel = direct`, или `product.type = mobile` при веб-форме в `product.forms`, или явно): посетители
  вместо установок, магазина нет, `payment_fee` и налог `tax_rate` (режим — `project.tax_regime`, иначе по умолчанию пакета:
  НПД для одного человека на рынке `ru`) — из блока `model-defaults` пакета локали `references/locales/<рынок>.md`, метка
  «допущение»; `personal` — личный инструмент (`project.audience = personal | circle | personal_then_public`): стоимость
  владения и окупаемость личных усилий (часы разработки по ёмкости до начала использования и часы поддержки после против
  сэкономленного времени × цена часа, денег и ошибок), сценарии «минимальный / обычный / с поддержкой», порог
  `hours_saved_per_week_to_break_even`; воронки, CAC и LTV нет. Плейсхолдеры: `{model:base.value|money}`,
  `{model:base.net_value}`, `{model:base.breakeven_month}`, `{model:base.hours_saved_per_week_to_break_even|1}`.
- Сверка модели с планом: `common.revenue_start_month` (до него платящих нет) берётся при создании параметров из
  `plan-baseline.json` (веха `paid`, иначе `launch`); блок `model.json → reconciliation` перечисляет расхождения (выручка раньше
  платной вехи, другой горизонт, другая ёмкость), `breakeven_note` — безубыточность «на копейках» в первые месяцы.

## 6. Расхождения с фактами из отчётов агентов: `collect_reports.py`

Последнее сообщение агента оркестратор сохраняет в `<OUT>/build/agent-reports/<бриф>[-<группа>].md`. Формат блока —
`templates/briefs/_report-footer.md` (`## Расхождения с фактами` + строки «факт — как во входах — как нашёл — источник»
или JSON `{"discrepancies": […]}`). `collect_reports.py <OUT>` → `data/fact-check.candidates.json`: одинаковые факты
слиты, разные найденные значения — `conflict` и `variants`, `proposed_value` — самое частое, `known` — уже есть в
`fact-check.json`. `--merge` дописывает новые кандидаты в `data/fact-check.json` с `resolved_value: null` — остаётся
подтвердить по первоисточнику.
