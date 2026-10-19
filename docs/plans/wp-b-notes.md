# WP-B — тексты для файлов оркестратора (SKILL.md, product-concept/SKILL.md, concept-mode.md, CHANGELOG, README)

Пакет: модель, ёмкость, план, согласованность, тексты (AR FB-026, 027, 028, 030, 046, 047, 048, 049; SM 6.1, разд. 4 — профиль
`personal`, сверка модель ↔ план ↔ реестр, контракт Ганта (данные/проверка), канон демо-данных).

## 1. `product-concept/SKILL.md` — таблица фаз C1–C9

Строку **C6** заменить:

| C6 | Оценка, зависимости, модель, графики | `score.py`, `validate_scores.py`, `typesafe_eval.py`, `model.py` (профиль — по `strategy.payment_channel` / `project.audience`: `web-direct`, `personal`, прежние; ёмкость — `capacity.py`), `charts.py` |

Строку **C7** заменить:

| C7 | Канвасы и SWOT; Гант и Kanban первыми → **базовая линия** `plan_baseline.py <OUT>`; **черновик решений** `facts_scaffold.py <OUT> --draft` (создаёт `data/decisions.json` с полем `draft` — подтвердить с владельцем или по умолчанию и удалить `draft`), снова `plan_baseline.py`; текст концепции (сроки — только `{plan:…}`), спеки топ-N, эксперименты; раздел 1 — `summary_scaffold.py <OUT> --to-part`; сверка `plan_baseline.py <OUT> --check` | `concept-canvas.md`, `strategy-section.md` по `concept-outline.md`, `specs.md`, `experiments.md`, `plan_baseline.py`, `decisions.py`, `facts_scaffold.py`, `summary_scaffold.py` |

В строку **C8** (перед `concept-design.md`) добавить: «канон демо-данных `facts_scaffold.py <OUT> --demo-canon` → `data/demo-canon.json` (одни демо-числа для всех макетов и прототипа)».

После таблицы, абзацем:

> Одна ёмкость: `capacity.py <OUT> --line` даёт строку «N ч/нед × доля = … ≈ … дня по 8 ч; за M мес. ≈ K дн. разработки» —
> та же в модели, базовой линии, решениях, факт-листе и брифах; другое определение рабочего дня сборка отмечает (`workday_mismatch`).
> Модель без данных об аудитории — режим sensitivity-only: денежные итоги в тексте только `{model:…}` (сборка ставит метку
> «[иллюстрация при допущениях]») или с этой меткой.

## 2. `SKILL.md` (product-strategy) — фаза 7, абзац про факт-лист

После упоминания `facts_scaffold.py` добавить:

> Сроки и состав плана — из базовой линии: после `gantt.json` — `plan_baseline.py <OUT>` (`data/plan-baseline.json`: вехи, MVP по
> Ганту, критерии отказа, ёмкость, все месяцы горизонта и видения с проверкой «дыр»); авторы пишут `{plan:beta}`, `{plan:launch}`,
> `{plan:mvp_ids}`, `{plan:kill.1.date}`, `{plan:capacity}`. Решения — `decisions.py <OUT> --init --draft` (или `facts_scaffold.py
> <OUT> --draft`): черновик ставок, критериев отказа, North Star, анти-целей и развилок из данных прогона с источниками.
> Резюме — `summary_scaffold.py <OUT>`. Перед сборкой — `plan_baseline.py <OUT> --check` (сборка повторяет проверку сама).

## 3. `references/concept-mode.md`

В раздел про C6 (модель):

> Профиль модели в режиме идеи: оплата на сайте (`strategy.payment_channel = direct`, или мобильное + веб-форма) → `web-direct`
> (посетители, без комиссии магазина; комиссия платёжного сервиса и налог — из пакета локали `references/locales/<рынок>.md`,
> блок `model-defaults`, метка «допущение»); «только для меня / для круга» (`project.audience = personal | circle |
> personal_then_public`) → `personal`: стоимость владения и окупаемость личных усилий (часы разработки и поддержки против
> сэкономленного времени, денег и ошибок; сценарии «минимальный / обычный / с поддержкой»), без воронки, CAC и LTV.
> Выручка начинается с платной вехи плана (`common.revenue_start_month` из `plan-baseline.json`); расхождения модели с планом
> и реестром (активация) — `model.json → reconciliation`.

В раздел про C7 — абзац из п. 1 (базовая линия, черновик решений, резюме, сверка) и про контракт Ганта:

> Гант покрывает весь горизонт и видение без пропусков: `plan-baseline.json → months` (план / «после горизонта» / видение) и
> `gantt_contract` (дыры вроде месяцев 7–12 при горизонте 6 и видении с 13-го, перегруз месяцев); сообщения — в факт-листе.

## 4. `CHANGELOG.md` (1.5.0) — строки WP-B

- **Одна ёмкость (FB-028, SM 6.1):** `scripts/capacity.py` — единственный расчёт (`project.capacity` → ответ опроса →
  `capacity_days_month` → дефолты; `team_size`; строка `line` с русскими дробями; `day_definitions()` для проверки текста);
  `model.py` (все профили, блок `capacity`), `decisions.py --init`, `facts_scaffold.py`, `plan_baseline.py`, `{capacity}` /
  `{plan:capacity}` берут её; `solo.days_per_month / hours_per_day` больше не задают ёмкость (осознанное исправление: дефолт
  10 ч/нед × 70 % ÷ 8 ч вместо 12 дн. × 6 ч).
- **Модель:** профили `web-direct` (FB-026; комиссия и налог НПД/УСН из блока `model-defaults` пакетов локали `ru`/`en`) и
  `personal` (личный инструмент: стоимость владения и окупаемость личных усилий); `common.tax_rate`; `revenue_start_month` по
  плану; блок `illustration` и `illustrative: true` в режиме sensitivity-only (FB-027); `reconciliation` — сверка с планом и
  реестром (начало выручки, горизонт, ёмкость, активация), `breakeven_note`.
- **Базовая линия плана (FB-046):** новый `scripts/plan_baseline.py` → `data/plan-baseline.json` (вехи, MVP по Ганту, критерии
  отказа, North Star, события, архитектура, все месяцы горизонта и видения, контракт Ганта); `--check [--strict]` →
  `build/consistency-report.json` (`plan_mismatch`, `kill_date_mismatch`, `capacity_mismatch`, `workday_mismatch`, `mvp_mismatch`);
  плейсхолдеры `{plan:…}` в сборке.
- **Резюме (FB-047):** новый `scripts/summary_scaffold.py` — черновик раздела 1 только из плейсхолдеров.
- **Черновик решений и факт-листа (FB-048, FB-049):** `decisions.py --init --draft`, `facts_scaffold.py --draft` (создаёт
  `decisions.json`, метки `[черновик: источник]`; на эталоне ARC мест `<заполнить>` 31 → 0); `facts_scaffold.py --demo-canon`
  (`data/demo-canon.json`); в факт-листе — блоки «Ёмкость и базовая линия плана», ключи схем (`data/flows-plan.json`), канон демо.
- **Сборка (FB-027, FB-030):** метка «[иллюстрация при допущениях]» к `{model:…}` итогов в sensitivity-only и
  `illustration_unlabeled` для буквальной выручки; числа без метки не считают значения факт-листа и решений, числа реестра рядом
  с P-id, таблицы с колонкой «Источник» и параметры метода (эталон ARC: 61 → 10 фрагментов); повтор чисел — по контексту
  (`repeats.numbers`), прежний список — `repeats.numbers_value_only`; `decisions_draft`.

## 5. `README.md` / `INSTALL.md`

README, список скриптов: «`plan_baseline.py` — базовая линия плана и проверка согласованности текста; `summary_scaffold.py` —
черновик резюме из плейсхолдеров; `capacity.py` — единая ёмкость». INSTALL — без изменений (только стандартная библиотека).

## 6. Изменённые существующие тесты (осознанно)

- `tests/test_registry2.py::test_model_zero_budget_solo` — ожидания ёмкости: было 144 дн. (12 дн. × 12 мес., день 6 ч), стало
  значение `capacity.capacity({"project": {"team_size": 1}}, 12)` (FB-028: одно определение дня).
- `tests/test_decisions.py::test_repeats_between_sections` — «12 %» в разделах 2 и 3 с разным контекстом теперь в
  `repeats.numbers_value_only`, а не в `repeats.numbers` (FB-030).
