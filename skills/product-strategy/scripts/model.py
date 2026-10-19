#!/usr/bin/env python3
"""Параметрическая модель юнит-экономики и воронки AARRR в трёх сценариях → data/model.json.

  model.py <OUT> [--params FILE] [--months N]

Параметры: --params FILE, иначе <OUT>/build/model-params.json (создаётся с дефолтами, если его нет — правьте его
и перезапускайте). Горизонт: --months, иначе run-config strategy.horizon_months, иначе 12.
Каждый вход — объект {"value", "label": "факт|оценка|допущение", "note"}; в model.json попадает как есть.
Дефолты — нейтральные допущения для небольшого цифрового продукта, а не данные: замените их фактами владельца.

Модель (помесячно, m = 1..N):
  visitors_m      = visitors_month · (1 + traffic_growth)^(m−1)
  signups_m       = visitors_m · visit_to_signup + referred_{m−1}
  activated_m     = signups_m · signup_to_active
  active_m        = active_{m−1} · retention_monthly + activated_m              (активная база)
  new_paying_m    = activated_m · active_to_paying
  paying_m        = paying_{m−1} · (1 − churn_monthly) + new_paying_m            (подписка)
  revenue_m       = paying_m · price_month                                       (подписка)
                  = new_paying_m · price_one_time                                (разовая покупка)
  net_revenue_m   = revenue_m · (1 − payment_fee) · (1 − refund_rate)
  referred_m      = active_m · referral_rate
  marketing_m     = signups_m · paid_share · cost_per_paid_signup
  cost_m          = fixed_cost_month + marketing_m     (переменные издержки учтены в gross_margin)
  CAC   = Σ marketing / Σ new_paying              (смешанный, на платящего; 0 при нулевом маркетинге)
  ARPU  = Σ net_revenue / Σ active                (на активного пользователя в месяц)
  ARPPU = Σ net_revenue / Σ paying                (на платящего в месяц; для разовой — на покупку)
  LTV   = price_month · (1 − fee)(1 − refund) · gross_margin · min(1/churn_monthly, ltv_cap_months)   (подписка)
        = price_one_time · (1 − fee)(1 − refund) · gross_margin · (1 + repeat_purchase_rate)   (разовая)
  payback_months = CAC / (price_month · (1 − fee)(1 − refund) · gross_margin)   (подписка; 0 при CAC = 0;
                   null, если платящих нет); для разовой — 0, если LTV ≥ CAC, иначе null
  breakeven_month = первый месяц, где накопленная net_revenue·gross_margin ≥ накопленных затрат (или null)
  ROI = (Σ net_revenue·gross_margin − Σ cost) / Σ cost

Валюта и подсказки (только при создании build/model-params.json; существующий файл — источник правды):
  валюта — run-config project.currency (иначе USD); денежные дефолты (цены, постоянные затраты, стоимость платной
  регистрации, ставка часа) пересчитываются пресетом валюты CURRENCIES (множитель уровня цен, округление до двух
  значащих цифр) — это допущение, не курс; project.price_hint → price_month (метка «оценка»);
  project.traffic_hint → visitors_month базового сценария (пессимистичный ×0,5, оптимистичный ×3).

Профиль strategy.profile = zero-budget-solo («нулевой бюджет, один разработчик»): платного привлечения нет
(paid_share = 0), трафик и постоянные затраты меньше; вместо CAC — часы разработчика на одного активированного
пользователя; ёмкость разработчика (project.team_size × solo.days_per_month × solo.hours_per_day) — явное
ограничение: блок capacity (сколько предложений P0–P1 по середине effort_days помещается в горизонт за вычетом
поддержки, порядок — dep_rank, иначе rank из data/scores.json); поддержка (часы на платящего и на активного ×
ставка часа) — «съедает» ли она выручку; безубыточность по времени — первый месяц, где накопленная валовая выручка
≥ (часы ёмкости × ставка + постоянные затраты); ROI — «неприменимо (нулевой бюджет)», CAC — null с пояснением.
Всё профильное — в model.json под ключом solo (и копия capacity на верхнем уровне). Профиль standard не меняется.
  hours_per_activated   = ёмкость_ч/мес · месяцев · growth_time_share / Σ activated
  support_hours_m       = paying_m · support_hours_per_paying_month + active_m · support_hours_per_active_month
  time_breakeven_month  = первый m: Σ net·gross_margin ≥ m · ёмкость_ч/мес · hourly_rate + Σ fixed_cost
  revenue_per_hour      = (Σ net·gross_margin − Σ fixed_cost) / (ёмкость_ч/мес · месяцев)

Профиль модели (model_profile; только при создании build/model-params.json, дальше — поле model_profile в файле;
старый файл без поля считается saas, как раньше). Выбор: run-config strategy.model_profile, иначе
strategy.monetization = donations или project.goal = oss без платной модели → oss; product.type = mobile → mobile-app;
strategy.monetization = one_time → one_time_purchase; иначе saas.
  saas               — дефолты выше (подписка);
  one_time_purchase  — пресет разовой покупки: revenue_model = one_time, цена покупки, возвраты, повторные покупки,
                       конверсия в покупку (около 25 параметров не нужно править вручную);
  mobile-app         — установки вместо визитов: installs_month, install_to_signup, cost_per_install (CPI);
                       комиссия магазина common.store_fee (итоговая комиссия 1 − (1 − payment_fee)(1 − store_fee)),
                       возвраты refund_rate; цена и комиссия — из run-config project.price_hint / project.store_fee
                       или data/store-stats.json (price | price_month | price_one_time, store_fee | commission,
                       installs_month), revenue_model — one_time при monetization = one_time, иначе subscription;
  oss                — доход = поддержка: revenue_model = donations, доноры = активированные × active_to_donor,
                       выручка = доноры · donation_month + sponsors_month; затраты = время (блок solo, как в
                       zero-budget-solo), платного привлечения нет — CAC и ROI неприменимы.
Платный канал отдельно (все профили): блок scenarios.*.paid и поле cac_paid = маркетинг / новые платящие из платного
канала; cac — смешанный (маркетинг / все новые платящие). Режим платного канала: share — доля верхушки воронки
(paid_share), budget — отдельный бюджет paid_budget_month / стоимость единицы (поверх органики, не доля тех же
визитов/установок); paid_conversion_factor — конверсия платных относительно органики (по умолчанию 1).
  cac_paid = Σ marketing / Σ new_paying_paid;  ltv_cac_paid = LTV / cac_paid
Режим модели (mode): forecast | sensitivity-only. Нет данных об аудитории (все входы воронки — допущения, нет
traffic_hint/фактов) → sensitivity-only: сценарии считаются (для графиков), но это иллюстрация; блок sensitivity —
как меняются выручка, активная база и безубыточность базового сценария при ±20 % по каждому ключевому параметру.
Явно: run-config strategy.model_mode или поле mode в build/model-params.json.
В режиме sensitivity-only денежные итоги сценариев помечены illustrative: true и продублированы в блоке illustration
(label «[иллюстрация при допущениях]»); assemble_strategy.py подставляет {model:…} таких итогов только с этой меткой (FB-027).

Ёмкость (все профили, FB-028): одна функция scripts/capacity.py → capacity(cfg, months) из run-config project.capacity
(иначе ответ опроса idea.facets.hours_week, иначе project.capacity_days_month, иначе дефолты 10 ч/нед × 70 % × 8 ч).
Блок capacity в model.json (dev_days_total, day_hours, line …) — те же числа, что в факт-листе, плане и брифах.
Прежние solo.days_per_month / solo.hours_per_day в build/model-params.json 1.4 больше не задают ёмкость (печатается заметка).

Профили 1.5:
  web-direct — веб/PWA с оплатой напрямую через платёжный сервис: посетители вместо установок, магазина нет (store_fee 0),
               payment_fee и налог (tax_rate, режим — project.tax_regime, иначе по умолчанию пакета) — из пакета локали
               references/locales/<рынок>.md (блок ```json model-defaults```), метка «допущение». Выбор: strategy.model_profile,
               strategy.payment_channel = direct, или product.type = mobile при веб-форме (product.forms: web|pwa).
  personal   — личный инструмент (project.audience = personal | circle | personal_then_public): «стоимость владения и
               окупаемость личных усилий» — часы разработки и поддержки (ёмкость capacity.py) против сэкономленного времени,
               денег и ошибок; сценарии «минимальный / обычный / с поддержкой» (ключи pessimistic / base / optimistic);
               воронки, CAC и LTV нет; помесячный расчёт — в блоке personal.
Налог: common.tax_rate (доля выручки) умножается в net_of после комиссий и возвратов; нет параметра — 0 (как в 1.4).
Сверка с планом: common.revenue_start_month — месяц начала выручки (до него платящих нет); при создании параметров берётся из
data/plan-baseline.json (milestones.paid, иначе launch), иначе 1 (как раньше). Расхождение с планом — блок reconciliation.
Только стандартная библиотека.
"""
import argparse
import copy
import json
import math
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
import capacity as capmod  # noqa: E402

SKILL = HERE.parent

SCENARIOS = ["pessimistic", "base", "optimistic"]
A = "допущение"

DEFAULT_PARAMS = {
    "version": 1,
    "currency": "USD",
    "revenue_model": {"value": "subscription", "label": A, "note": "subscription | one_time — уточнить у владельца"},
    "common": {
        "price_month": {"value": 12.0, "label": A, "note": "цена подписки в месяц; заменить ценой продукта или конкурентов"},
        "price_one_time": {"value": 29.0, "label": A, "note": "цена разовой покупки (для revenue_model = one_time)"},
        "payment_fee": {"value": 0.05, "label": A, "note": "комиссия платёжного провайдера, доля"},
        "refund_rate": {"value": 0.02, "label": A, "note": "доля возвратов"},
        "gross_margin": {"value": 0.85, "label": A, "note": "валовая маржа после переменных затрат (хостинг, поддержка)"},
        "repeat_purchase_rate": {"value": 0.0, "label": A, "note": "доля повторных покупок (разовая модель)"},
        "ltv_cap_months": {"value": 36, "label": A, "note": "верхняя граница срока жизни клиента для LTV"},
    },
    "scenarios": {
        "pessimistic": {
            "visitors_month": {"value": 2500, "label": A, "note": "посетителей в первый месяц"},
            "traffic_growth": {"value": 0.02, "label": A, "note": "рост посетителей в месяц"},
            "visit_to_signup": {"value": 0.03, "label": A, "note": "посетитель → регистрация"},
            "signup_to_active": {"value": 0.30, "label": A, "note": "регистрация → активация (первое ценное действие)"},
            "retention_monthly": {"value": 0.50, "label": A, "note": "доля активных, оставшихся через месяц"},
            "active_to_paying": {"value": 0.02, "label": A, "note": "активированный → платящий"},
            "churn_monthly": {"value": 0.10, "label": A, "note": "отток платящих в месяц"},
            "referral_rate": {"value": 0.005, "label": A, "note": "приглашённых регистраций на активного в месяц"},
            "paid_share": {"value": 0.0, "label": A, "note": "доля регистраций из платных каналов"},
            "cost_per_paid_signup": {"value": 6.0, "label": A, "note": "стоимость платной регистрации"},
            "fixed_cost_month": {"value": 250.0, "label": A, "note": "постоянные затраты в месяц (инфраструктура, сервисы)"},
        },
        "base": {
            "visitors_month": {"value": 5000, "label": A, "note": "посетителей в первый месяц"},
            "traffic_growth": {"value": 0.05, "label": A, "note": "рост посетителей в месяц"},
            "visit_to_signup": {"value": 0.05, "label": A, "note": "посетитель → регистрация"},
            "signup_to_active": {"value": 0.40, "label": A, "note": "регистрация → активация"},
            "retention_monthly": {"value": 0.60, "label": A, "note": "доля активных, оставшихся через месяц"},
            "active_to_paying": {"value": 0.05, "label": A, "note": "активированный → платящий"},
            "churn_monthly": {"value": 0.06, "label": A, "note": "отток платящих в месяц"},
            "referral_rate": {"value": 0.01, "label": A, "note": "приглашённых регистраций на активного в месяц"},
            "paid_share": {"value": 0.2, "label": A, "note": "доля регистраций из платных каналов"},
            "cost_per_paid_signup": {"value": 5.0, "label": A, "note": "стоимость платной регистрации"},
            "fixed_cost_month": {"value": 400.0, "label": A, "note": "постоянные затраты в месяц"},
        },
        "optimistic": {
            "visitors_month": {"value": 15000, "label": A, "note": "посетителей в первый месяц"},
            "traffic_growth": {"value": 0.09, "label": A, "note": "рост посетителей в месяц"},
            "visit_to_signup": {"value": 0.07, "label": A, "note": "посетитель → регистрация"},
            "signup_to_active": {"value": 0.55, "label": A, "note": "регистрация → активация"},
            "retention_monthly": {"value": 0.70, "label": A, "note": "доля активных, оставшихся через месяц"},
            "active_to_paying": {"value": 0.07, "label": A, "note": "активированный → платящий"},
            "churn_monthly": {"value": 0.04, "label": A, "note": "отток платящих в месяц"},
            "referral_rate": {"value": 0.02, "label": A, "note": "приглашённых регистраций на активного в месяц"},
            "paid_share": {"value": 0.3, "label": A, "note": "доля регистраций из платных каналов"},
            "cost_per_paid_signup": {"value": 4.0, "label": A, "note": "стоимость платной регистрации"},
            "fixed_cost_month": {"value": 600.0, "label": A, "note": "постоянные затраты в месяц"},
        },
    },
}


# пресеты валют: символ, множитель уровня цен к USD-дефолтам (допущение, не курс), ставка часа разработчика
CURRENCIES = {
    "USD": {"symbol": "$", "factor": 1.0, "hourly_rate": 40},
    "EUR": {"symbol": "€", "factor": 0.92, "hourly_rate": 38},
    "GBP": {"symbol": "£", "factor": 0.8, "hourly_rate": 35},
    "RUB": {"symbol": "₽", "factor": 32.0, "hourly_rate": 1500},
    "KZT": {"symbol": "₸", "factor": 230.0, "hourly_rate": 6000},
    "UAH": {"symbol": "₴", "factor": 16.0, "hourly_rate": 600},
    "BYN": {"symbol": "Br", "factor": 1.2, "hourly_rate": 45},
    "PLN": {"symbol": "zł", "factor": 2.6, "hourly_rate": 120},
    "INR": {"symbol": "₹", "factor": 25.0, "hourly_rate": 1200},
    "BRL": {"symbol": "R$", "factor": 2.5, "hourly_rate": 90},
    "TRY": {"symbol": "₺", "factor": 15.0, "hourly_rate": 700},
    "CNY": {"symbol": "¥", "factor": 3.5, "hourly_rate": 150},
    "JPY": {"symbol": "¥", "factor": 110.0, "hourly_rate": 4500},
}
MONEY_COMMON = ("price_month", "price_one_time", "donation_month", "sponsors_month")
MONEY_SCEN = ("fixed_cost_month", "cost_per_paid_signup", "cost_per_install", "paid_budget_month")
MODEL_PROFILES = ("saas", "one_time_purchase", "mobile-app", "oss", "web-direct", "personal")
MODES = ("forecast", "sensitivity-only")
PERSONAL_AUDIENCES = ("personal", "circle", "personal_then_public")
ILLUSTRATION_LABEL = "[иллюстрация при допущениях]"
# денежные и прогнозные итоги сценария: в режиме sensitivity-only — только с меткой иллюстрации
ILLUSTRATIVE_KEYS = ("net_revenue", "revenue_last", "revenue_first", "roi", "ltv", "ltv_cac", "ltv_cac_paid", "cac", "cac_paid",
                     "payback_months", "breakeven_month", "arpu", "arppu", "users_last", "paying_last", "new_paying", "cost",
                     "marketing", "cum_margin_last", "cum_cost_last", "net_value", "value")
SCENARIO_LABELS_PERSONAL = {"pessimistic": "минимальный", "base": "обычный", "optimistic": "с поддержкой"}


def _p(value, note):
    return {"value": value, "label": A, "note": note}


def _scen(**per_param):
    """{param: ((pess, base, opt), note)} → {scenario: {param: {value, label, note}}}."""
    out = {n: {} for n in SCENARIOS}
    for k, (vals, note) in per_param.items():
        for n, v in zip(SCENARIOS, vals):
            out[n][k] = _p(v, note)
    return out


# пресеты профилей модели поверх DEFAULT_PARAMS (USD; деньги пересчитываются пресетом валюты); None — удалить параметр
PROFILE_PRESETS = {
    "one_time_purchase": {
        "revenue_model": _p("one_time", "профиль one_time_purchase: разовая покупка"),
        "common": {
            "price_one_time": _p(29.0, "цена разовой покупки; заменить ценой продукта или аналогов"),
            "refund_rate": _p(0.05, "доля возвратов покупок"),
            "repeat_purchase_rate": _p(0.10, "доля повторных покупок (обновления, дополнения)"),
            "gross_margin": _p(0.90, "валовая маржа после переменных затрат"),
        },
        "scenarios": _scen(active_to_paying=((0.01, 0.03, 0.05), "активированный → покупатель"),
                           churn_monthly=((0.0, 0.0, 0.0), "не используется: разовая покупка")),
    },
    "mobile-app": {
        "common": {
            "price_month": _p(4.99, "цена подписки в приложении в месяц"),
            "price_one_time": _p(4.99, "цена покупки в приложении (для revenue_model = one_time)"),
            "payment_fee": _p(0.0, "платёж идёт через магазин — комиссия в store_fee"),
            "store_fee": _p(0.15, "комиссия магазина (15 % — программы для малых разработчиков; проверить для своего магазина)"),
            "refund_rate": _p(0.03, "доля возвратов через магазин"),
            "gross_margin": _p(0.90, "валовая маржа после переменных затрат (серверы, push)"),
        },
        "scenarios": dict((n, dict(v, visitors_month=None, visit_to_signup=None, cost_per_paid_signup=None)) for n, v in _scen(
            installs_month=((1000, 3000, 10000), "установок в первый месяц"),
            install_to_signup=((0.5, 0.6, 0.7), "установка → регистрация (первый запуск с онбордингом)"),
            signup_to_active=((0.3, 0.4, 0.5), "регистрация → активация"),
            retention_monthly=((0.25, 0.35, 0.45), "доля активных, оставшихся через месяц (у мобильных ниже, чем у веба)"),
            active_to_paying=((0.01, 0.02, 0.04), "активированный → платящий"),
            churn_monthly=((0.15, 0.10, 0.07), "отток платящих в месяц"),
            referral_rate=((0.002, 0.005, 0.01), "приглашённых регистраций на активного в месяц"),
            paid_share=((0.0, 0.2, 0.3), "доля установок из платных каналов"),
            cost_per_install=((1.5, 1.2, 0.9), "стоимость платной установки (CPI)"),
            fixed_cost_month=((100.0, 200.0, 400.0), "постоянные затраты в месяц (серверы, аккаунты разработчика)"),
        ).items()),
    },
    "oss": {
        "revenue_model": _p("donations", "профиль oss: доход — поддержка (донаты, спонсоры)"),
        "common": {
            "price_month": None, "price_one_time": None, "repeat_purchase_rate": None,
            "donation_month": _p(5.0, "средний ежемесячный донат на донора"),
            "sponsors_month": _p(0.0, "спонсорство организаций в месяц (фиксированная сумма)"),
            "payment_fee": _p(0.05, "комиссия платформы донатов"),
            "refund_rate": _p(0.0, "возвратов у донатов нет"),
            "gross_margin": _p(1.0, "переменных затрат нет: инфраструктура — в fixed_cost_month"),
        },
        "scenarios": dict((n, dict(v, active_to_paying=None)) for n, v in _scen(
            visitors_month=((500, 1500, 5000), "посетителей сайта и страницы проекта в первый месяц"),
            visit_to_signup=((0.05, 0.08, 0.10), "посетитель → установка/первый запуск"),
            active_to_donor=((0.002, 0.005, 0.01), "активированный → донор"),
            churn_monthly=((0.08, 0.05, 0.03), "отток доноров в месяц"),
            paid_share=((0.0, 0.0, 0.0), "профиль oss: платного привлечения нет"),
            cost_per_paid_signup=((0.0, 0.0, 0.0), "профиль oss: платного привлечения нет"),
            fixed_cost_month=((0.0, 5.0, 20.0), "постоянные затраты в месяц (домен, хостинг, CI)"),
        ).items()),
    },
    "web-direct": {   # payment_fee и tax_rate — из пакета локали (default_params), здесь — запасные значения
        "common": {
            "price_month": _p(5.0, "цена подписки в месяц при оплате на сайте; заменить ценой продукта или аналогов"),
            "price_one_time": _p(15.0, "цена разовой покупки на сайте (для revenue_model = one_time)"),
            "store_fee": _p(0.0, "магазина приложений нет: веб/PWA, оплата напрямую через платёжный сервис"),
            "refund_rate": _p(0.05, "доля возвратов (веб-оплата, отказ от подписки)"),
            "gross_margin": _p(0.90, "валовая маржа после переменных затрат (хостинг, рассылки)"),
        },
        "scenarios": _scen(
            visitors_month=((1000, 3000, 9000), "посетителей сайта в первый месяц (установок нет: веб/PWA)"),
            paid_share=((0.0, 0.1, 0.2), "доля регистраций из платных каналов"),
            fixed_cost_month=((5.0, 15.0, 40.0), "постоянные затраты в месяц (VPS или хостинг, домен, почта)"),
        ),
    },
}
# личный инструмент: ценность — сэкономленное время, деньги и ошибки владельца (и его круга), затраты — время и сервисы (USD)
PERSONAL_SCEN = {
    "hours_saved_per_week": ((0.5, 1.5, 3.0), "сэкономленных часов в неделю на пользователя после начала использования"),
    "money_saved_month": ((0.0, 5.0, 10.0), "сэкономленных денег в месяц на пользователя (заменённые подписки, сервисы)"),
    "errors_avoided_month": ((0.0, 1.0, 2.0), "предотвращённых ошибок или потерь в месяц на пользователя"),
    "cost_per_error": ((10.0, 20.0, 30.0), "цена одной ошибки или потери"),
    "support_hours_month": ((2.0, 4.0, 8.0), "часов поддержки и обновлений в месяц после начала использования"),
    "fixed_cost_month": ((0.0, 5.0, 15.0), "постоянные затраты в месяц (хостинг, API, домен)"),
}
PERSONAL_MONEY = ("money_saved_month", "cost_per_error", "fixed_cost_month")
PERSONAL_SENS = (("hours_saved_per_week", "сэкономленные часы"), ("money_saved_month", "сэкономленные деньги"),
                 ("errors_avoided_month", "предотвращённые ошибки"), ("support_hours_month", "часы поддержки"),
                 ("fixed_cost_month", "постоянные затраты"))
AUDIENCE_KEYS = ("visitors_month", "installs_month", "visit_to_signup", "install_to_signup", "signup_to_active",
                 "active_to_paying", "active_to_donor")
SENS_KEYS = (("visitors_month", "трафик"), ("installs_month", "установки"), ("visit_to_signup", "визит → регистрация"),
             ("install_to_signup", "установка → регистрация"), ("signup_to_active", "активация"),
             ("retention_monthly", "удержание"), ("active_to_paying", "конверсия в оплату"), ("active_to_donor", "конверсия в доноры"),
             ("churn_monthly", "отток"), ("price_month", "цена подписки"), ("price_one_time", "цена покупки"),
             ("donation_month", "средний донат"))
SOLO_SCEN = {  # профиль zero-budget-solo: без платных каналов, скромный органический трафик, почти нулевые затраты (USD)
    "pessimistic": {"visitors_month": 300, "traffic_growth": 0.03, "fixed_cost_month": 0.0},
    "base": {"visitors_month": 800, "traffic_growth": 0.06, "fixed_cost_month": 6.0},
    "optimistic": {"visitors_month": 2500, "traffic_growth": 0.10, "fixed_cost_month": 12.0},
}
SOLO_PARAMS = {   # ёмкость (часы в неделю, доля разработки, часов в дне) — не здесь, а в run-config project.capacity (capacity.py)
    "team_size": {"value": 1, "label": A, "note": "людей в команде (project.team_size)"},
    "hourly_rate": {"value": 40, "label": A, "note": "цена часа разработчика (упущенная ставка) — для «безубыточности по времени»"},
    "growth_time_share": {"value": 0.3, "label": A, "note": "доля ёмкости на привлечение и активацию (контент, сообщества, онбординг)"},
    "support_hours_per_paying_month": {"value": 0.5, "label": A, "note": "часов поддержки на платящего в месяц"},
    "support_hours_per_active_month": {"value": 0.02, "label": A, "note": "часов поддержки на активного (в т. ч. бесплатного) в месяц"},
    "support_capacity_alert": {"value": 0.5, "label": A, "note": "доля ёмкости на поддержку, после которой развитие останавливается"},
}
ROI_NA = "неприменимо (нулевой бюджет)"


def nice(x):
    """Округление до двух значащих цифр (допущения не должны выглядеть точными)."""
    if not x:
        return 0.0
    mag = 10 ** (math.floor(math.log10(abs(x))) - 1)
    return float(round(x / mag) * mag)


def currency_preset(code):
    code = str(code or "USD").upper()
    return code, CURRENCIES.get(code)


def is_number(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def select_profile(cfg):
    """(профиль модели, почему) по run-config: strategy.model_profile → monetization/goal/product.type."""
    cfg = cfg or {}
    st, pr, pj = cfg.get("strategy") or {}, cfg.get("product") or {}, cfg.get("project") or {}
    explicit = st.get("model_profile")
    if explicit in MODEL_PROFILES:
        return explicit, "run-config strategy.model_profile"
    aud = str(pj.get("audience") or "").lower()
    if aud in PERSONAL_AUDIENCES:
        return "personal", "project.audience = %s (личный инструмент)" % aud
    mon = str(st.get("monetization") or "").lower()
    if mon in ("donations", "donation", "oss", "sponsorship"):
        return "oss", "strategy.monetization = %s" % mon
    if pj.get("goal") == "oss" and mon in ("", "none", "free"):
        return "oss", "project.goal = oss без платной модели"
    pay = str(st.get("payment_channel") or "").lower()
    if pay == "direct":
        return "web-direct", "strategy.payment_channel = direct (оплата напрямую через платёжный сервис)"
    if pay == "store":
        return "mobile-app", "strategy.payment_channel = store (оплата через магазин приложений)"
    if pay == "donations":
        return "oss", "strategy.payment_channel = donations"
    forms = {str(f).lower() for f in (pr.get("forms") or []) if f}
    if str(pr.get("type") or "").lower() in ("mobile", "mobile-app", "android", "ios"):
        if forms & {"web", "pwa", "site", "web-app"}:
            return "web-direct", "product.type = %s, но есть веб-форма (%s): оплата на сайте без комиссии магазина; уточните " \
                                 "strategy.payment_channel" % (pr.get("type"), ", ".join(sorted(forms)))
        return "mobile-app", "product.type = %s" % pr.get("type")
    if mon in ("one_time", "one-time", "one_time_purchase"):
        return "one_time_purchase", "strategy.monetization = one_time"
    return "saas", "по умолчанию"


LOCALE_BLOCK_RE = re.compile(r"```json[ \t]+model-defaults[ \t]*\n(.*?)\n```", re.S)


def locale_defaults(cfg):
    """(код локали, блок model-defaults) из references/locales/<рынок>.md: первый рынок strategy.markets с блоком,
    иначе по валюте (RUB → ru), иначе en; нет блока → (None, {})."""
    cfg = cfg or {}
    cands = [str(m).lower() for m in ((cfg.get("strategy") or {}).get("markets") or []) if m]
    cur = str((cfg.get("project") or {}).get("currency") or "").upper()
    cands += ["ru"] if cur in ("RUB", "BYN", "KZT") else []
    cands += ["en"]
    for code in cands:
        f = SKILL / "references" / "locales" / ("%s.md" % code)
        try:
            m = LOCALE_BLOCK_RE.search(f.read_text(encoding="utf-8"))
        except OSError:
            continue
        if m:
            try:
                return code, json.loads(m.group(1))
            except ValueError:
                continue
    return None, {}


def tax_param(cfg, loc_code, loc, default_needed):
    """common.tax_rate по project.tax_regime (явно) или режиму по умолчанию пакета локали → параметр | None."""
    pj = (cfg or {}).get("project") or {}
    regimes = ((loc.get("tax") or {}).get("regimes")) or {}
    want = pj.get("tax_regime")
    if want is None and not default_needed:
        return None
    team = pj.get("team_size") if isinstance(pj.get("team_size"), int) else 1
    key = want or (loc.get("tax") or {}).get("default_solo" if team <= 1 else "default_team")
    r = regimes.get(str(key)) if key else None
    if not isinstance(r, dict):
        if want is not None:
            return {"value": 0.0, "label": A, "note": "project.tax_regime = %s — нет в пакете локали %s; налог не учтён, задайте tax_rate" % (want, loc_code)}
        return None
    payer_b2b = str((cfg.get("idea") or {}).get("facets", {}).get("segment") or "").lower() in ("b2b", "smb", "enterprise")
    rate = r.get("rate_b2b") if payer_b2b and r.get("rate_b2b") is not None else r.get("rate", 0.0)
    src = "run-config project.tax_regime" if want else "режим по умолчанию"
    return {"value": float(rate), "label": A,
            "note": "налог: %s (%s; пакет локали %s) — проверить актуальную ставку по первоисточнику" % (r.get("label") or key, src, loc_code)}


def load_plan(out_dir):
    """data/plan-baseline.json (plan_baseline.py) или None."""
    if out_dir is None:
        return None
    try:
        d = json.loads((Path(out_dir) / "data" / "plan-baseline.json").read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else None
    except (OSError, ValueError):
        return None


def plan_month(plan, *kinds):
    """Месяц первой вехи из перечисленных видов в plan-baseline (milestones.<вид>.month) или None."""
    ms = (plan or {}).get("milestones") or {}
    for k in kinds:
        v = ms.get(k)
        if isinstance(v, dict) and isinstance(v.get("month"), (int, float)):
            return int(v["month"])
    return None


def apply_preset(P, profile):
    preset = PROFILE_PRESETS.get(profile)
    if not preset:
        return P
    if "revenue_model" in preset:
        P["revenue_model"] = copy.deepcopy(preset["revenue_model"])
    for k, v in (preset.get("common") or {}).items():
        if v is None:
            P["common"].pop(k, None)
        else:
            P["common"][k] = copy.deepcopy(v)
    for name, over in (preset.get("scenarios") or {}).items():
        sc = P["scenarios"][name]
        for k, v in over.items():
            if v is None:
                sc.pop(k, None)
            else:
                sc[k] = copy.deepcopy(v)
    return P


def store_stats(out_dir):
    """Цена, комиссия и установки из data/store-stats.json (терпимо к формату) → dict."""
    if out_dir is None:
        return {}
    try:
        d = json.loads((Path(out_dir) / "data" / "store-stats.json").read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return {}
    rows = d if isinstance(d, list) else ([d] + list(d.get("stores") or [])) if isinstance(d, dict) else []
    res = {}
    for r in rows:
        if not isinstance(r, dict):
            continue
        for key, names in (("price", ("price_month", "price", "price_one_time")), ("store_fee", ("store_fee", "commission", "fee")),
                           ("installs_month", ("installs_month", "installs_per_month"))):
            for n in names:
                if key not in res and is_number(r.get(n)) and r[n] > 0:
                    res[key] = float(r[n])
    if res.get("store_fee", 0) > 1:                       # 15 → 0.15
        res["store_fee"] /= 100.0
    return res


def default_params(cfg, profile=None, out_dir=None):
    """Параметры по умолчанию с учётом run-config: валюта, price_hint/traffic_hint, профиль стратегии и профиль модели."""
    cfg = cfg or {}
    project = cfg.get("project") or {}
    st = cfg.get("strategy") or {}
    sprofile = st.get("profile") or "standard"
    why = "задан явно"
    if profile is None:
        profile, why = select_profile(cfg)
    code, preset = currency_preset(project.get("currency") or "USD")
    if profile == "personal":
        return personal_params(cfg, code, preset, why, out_dir)
    P = copy.deepcopy(DEFAULT_PARAMS)
    P["currency"] = code
    P["model_profile"] = {"value": profile, "label": "факт" if why.startswith("run-config strategy.model") else A,
                          "note": "профиль модели: %s (%s); %s" % (profile, why, " | ".join(MODEL_PROFILES))}
    apply_preset(P, profile)
    loc_code, loc = locale_defaults(cfg)
    if profile == "web-direct":
        d = ((loc.get("payment") or {}).get("direct")) or {}
        if is_number(d.get("payment_fee")):
            P["common"]["payment_fee"] = {"value": float(d["payment_fee"]), "label": A,
                                          "note": "%s (пакет локали %s)" % (d.get("note") or "комиссия платёжного сервиса", loc_code)}
    tx = tax_param(cfg, loc_code, loc, profile == "web-direct")
    if tx is not None:
        P["common"]["tax_rate"] = tx
    mon = str(st.get("monetization") or "").lower()
    if profile == "mobile-app" and mon in ("one_time", "one-time"):
        P["revenue_model"] = _p("one_time", "mobile-app: покупка в приложении (strategy.monetization = one_time)")
    top = "installs_month" if profile == "mobile-app" else "visitors_month"
    f = preset["factor"] if preset else 1.0
    if not preset:
        P.setdefault("notes", []).append("нет пресета для валюты %s — суммы в масштабе USD-дефолтов, замените" % code)
    if sprofile == "zero-budget-solo" or profile == "oss":
        for name, over in SOLO_SCEN.items():
            sc = P["scenarios"][name]
            for k, v in over.items():
                k = top if k == "visitors_month" else k
                if profile == "oss" and k == top:
                    continue                                   # у oss свой трафик (страница проекта)
                sc[k]["value"] = v
            sc["paid_share"] = {"value": 0.0, "label": A, "note": "профиль %s: платных каналов нет" % (
                "oss" if profile == "oss" else "zero-budget-solo")}
        P["solo"] = copy.deepcopy(SOLO_PARAMS)
        P["solo"]["hourly_rate"]["value"] = preset["hourly_rate"] if preset else SOLO_PARAMS["hourly_rate"]["value"]
        if isinstance(project.get("team_size"), (int, float)) and project["team_size"] > 0:
            P["solo"]["team_size"] = {"value": project["team_size"], "label": "факт", "note": "run-config project.team_size"}
    if f != 1.0:
        for k in MONEY_COMMON:
            if k in P["common"]:
                P["common"][k]["value"] = nice(P["common"][k]["value"] * f)
        for sc in P["scenarios"].values():
            for k in MONEY_SCEN:
                if k in sc:
                    sc[k]["value"] = nice(sc[k]["value"] * f)
    one_time = val(P["revenue_model"]) == "one_time"
    price_key = "donation_month" if profile == "oss" else ("price_one_time" if one_time else "price_month")
    ss = store_stats(out_dir) if profile == "mobile-app" else {}
    if ss.get("price"):
        P["common"][price_key] = {"value": ss["price"], "label": "факт", "note": "data/store-stats.json"}
    if ss.get("store_fee") is not None:
        P["common"]["store_fee"] = {"value": ss["store_fee"], "label": "факт", "note": "data/store-stats.json"}
    if ss.get("installs_month"):
        for name, k in (("pessimistic", 0.5), ("base", 1.0), ("optimistic", 3.0)):
            P["scenarios"][name][top] = {"value": round(ss["installs_month"] * k), "label": "факт" if k == 1.0 else "оценка",
                                         "note": "data/store-stats.json installs_month × %s" % k}
    sf = project.get("store_fee")
    if profile == "mobile-app" and is_number(sf) and 0 <= sf < 100:
        P["common"]["store_fee"] = {"value": sf / 100.0 if sf > 1 else float(sf), "label": "факт", "note": "run-config project.store_fee"}
    hint = project.get("price_hint")
    if is_number(hint) and hint > 0:
        P["common"][price_key] = {"value": float(hint), "label": "оценка", "note": "run-config project.price_hint"}
    th = project.get("traffic_hint")
    if is_number(th) and th > 0:
        for name, k in (("pessimistic", 0.5), ("base", 1.0), ("optimistic", 3.0)):
            P["scenarios"][name][top] = {"value": round(th * k), "label": "оценка",
                                         "note": "run-config project.traffic_hint × %s" % k}
    mode = st.get("model_mode")
    if mode in MODES:
        P["mode"] = {"value": mode, "label": "факт", "note": "run-config strategy.model_mode"}
    plan = load_plan(out_dir)
    start = plan_month(plan, "paid", "launch")
    if start and start > 1:
        P["common"]["revenue_start_month"] = {"value": start, "label": "факт",
                                              "note": "месяц начала выручки — из data/plan-baseline.json (веха %s)" % (
                                                  "paid" if plan_month(plan, "paid") else "launch")}
    return P


def personal_params(cfg, code, preset, why, out_dir=None):
    """Параметры профиля personal: ценность для владельца против времени и затрат (USD-дефолты × пресет валюты)."""
    cfg = cfg or {}
    pj = cfg.get("project") or {}
    aud = str(pj.get("audience") or "personal").lower()
    f = preset["factor"] if preset else 1.0
    rate = preset["hourly_rate"] if preset else SOLO_PARAMS["hourly_rate"]["value"]
    users = 1 if aud in ("personal", "personal_then_public") else 3
    plan = load_plan(out_dir)
    start = plan_month(plan, "beta", "mvp", "launch")
    P = {"version": 1, "currency": code,
         "model_profile": {"value": "personal", "label": "факт" if why.startswith("run-config strategy.model") else A,
                           "note": "профиль модели: personal (%s) — стоимость владения и окупаемость личных усилий" % why},
         "revenue_model": _p("none", "личный инструмент: выручки нет; ценность — сэкономленное время, деньги и ошибки"),
         "scenario_labels": dict(SCENARIO_LABELS_PERSONAL),
         "common": {
             "hourly_rate": _p(rate, "цена часа владельца (упущенная ставка) — переводит часы в деньги"),
             "users": {"value": users, "label": A if aud != "personal" else "факт",
                       "note": "пользователей: %s (project.audience = %s)" % (users, aud)},
             "use_start_month": ({"value": start, "label": "факт", "note": "начало использования — веха из data/plan-baseline.json"}
                                 if start else _p(3, "месяц, с которого инструментом пользуются (до него — разработка)")),
         },
         "scenarios": {n: {} for n in SCENARIOS}}
    for k, (vals, note) in PERSONAL_SCEN.items():
        for n, v in zip(SCENARIOS, vals):
            P["scenarios"][n][k] = _p(nice(v * f) if (k in PERSONAL_MONEY and f != 1.0) else v, note)
    if not preset:
        P.setdefault("notes", []).append("нет пресета для валюты %s — суммы в масштабе USD-дефолтов, замените" % code)
    mode = (cfg.get("strategy") or {}).get("model_mode")
    if mode in MODES:
        P["mode"] = {"value": mode, "label": "факт", "note": "run-config strategy.model_mode"}
    return P


def val(x):
    """Значение параметра: объект {"value"} или голое число."""
    return x["value"] if isinstance(x, dict) and "value" in x else x


def labelled(x):
    """Параметр с меткой (голое число → допущение)."""
    if isinstance(x, dict) and "value" in x:
        return {"value": x["value"], "label": x.get("label", A), "note": x.get("note", "")}
    return {"value": x, "label": A, "note": ""}


def deep_merge(base, extra):
    out = copy.deepcopy(base)
    for k, v in (extra or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict) and "value" not in v:
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def r2(x):
    return None if x is None else round(x, 2)


def pick(d, *names, default=0.0):
    for n in names:
        if n in d:
            return d[n]
    return default


def unit_price(g, kind):
    """Цена единицы выручки: месячная подписка, покупка или донат."""
    if kind == "one_time":
        return pick(g, "price_one_time")
    if kind == "donations":
        return pick(g, "donation_month", "price_month")
    return pick(g, "price_month")


def net_factor(g):
    """Доля цены, остающаяся после комиссий (провайдер × магазин) и возвратов."""
    return net_of(1.0, g)


def net_of(x, g):
    """Сумма после комиссий провайдера и магазина и возвратов (порядок умножения как в 1.0 — без расхождений округления)."""
    y = x * (1 - pick(g, "payment_fee")) * (1 - pick(g, "store_fee")) * (1 - pick(g, "refund_rate"))
    return y * (1 - pick(g, "tax_rate")) if "tax_rate" in g else y


def simulate(common, sc, months, model_kind):
    """Помесячный расчёт одного сценария."""
    g = {k: float(val(v)) for k, v in common.items() if is_number(val(v))}
    s = {k: float(val(v)) for k, v in sc.items() if is_number(val(v))}
    mobile = "installs_month" in s
    visitors = pick(s, "installs_month", "visitors_month")
    conv1 = pick(s, "install_to_signup", "visit_to_signup")
    a2p = pick(s, "active_to_paying", "active_to_donor")
    churn = pick(s, "churn_monthly")
    price = unit_price(g, model_kind)
    per_install = "cost_per_install" in s
    unit_cost = pick(s, "cost_per_install", "cost_per_paid_signup")
    budget = pick(s, "paid_budget_month")
    pcf = pick(s, "paid_conversion_factor", default=1.0)
    paid_share = pick(s, "paid_share")
    sponsors = pick(g, "sponsors_month") if model_kind == "donations" else 0.0
    paid_mode = "budget" if budget > 0 else ("share" if paid_share > 0 and unit_cost > 0 else "none")
    rev_start = int(pick(g, "revenue_start_month", default=1.0) or 1)
    active = paying = referred = 0.0
    monthly, tot = [], dict(visitors=0.0, signups=0.0, activated=0.0, new_paying=0.0, net=0.0, marketing=0.0,
                            cost=0.0, active=0.0, paying=0.0, referred=0.0, paid_signups=0.0, new_paying_paid=0.0)
    cum_margin = cum_cost = 0.0
    breakeven = None
    for m in range(1, months + 1):
        signups = visitors * conv1 + referred
        if paid_mode == "budget":                      # отдельный бюджет поверх органики
            units = budget / unit_cost if unit_cost > 0 else 0.0
            paid_signups = units * conv1 if per_install else units
            signups += paid_signups
            marketing = budget if unit_cost > 0 else 0.0
        elif per_install:                              # доля установок из платных каналов
            paid_signups = visitors * paid_share * conv1
            marketing = visitors * paid_share * unit_cost
        else:                                          # доля регистраций из платных каналов (как в 1.0)
            paid_signups = signups * paid_share
            marketing = paid_signups * unit_cost
        act_paid = paid_signups * s["signup_to_active"] * pcf
        activated = (signups - paid_signups) * s["signup_to_active"] + act_paid
        active = active * s["retention_monthly"] + activated
        new_paying_paid = act_paid * a2p
        new_paying = (activated - act_paid) * a2p + new_paying_paid
        if m < rev_start:                              # платная часть ещё не запущена (план): платящих нет
            new_paying = new_paying_paid = 0.0
        if model_kind == "one_time":
            paying = new_paying
            revenue = new_paying * price
        else:                                          # подписка или донаты (доноры с оттоком)
            paying = paying * (1 - churn) + new_paying
            revenue = paying * price + sponsors
        net = net_of(revenue, g)
        cost = s["fixed_cost_month"] + marketing
        cum_margin += net * g["gross_margin"]
        cum_cost += cost
        if breakeven is None and cum_cost > 0 and cum_margin >= cum_cost:
            breakeven = m
        new_referred = active * s["referral_rate"]
        # набор полей помесячной строки не расширять: страница показывает её таблицей (ширина рамки); итоги — в totals/paid
        monthly.append({"month": m, "visitors": round(visitors), "signups": round(signups, 1),
                        "users": round(active, 1), "paying": round(paying, 1), "new_paying": round(new_paying, 2),
                        "revenue": round(net, 2), "cost": round(cost, 2), "marketing": round(marketing, 2),
                        "cum_margin": round(cum_margin, 2), "cum_cost": round(cum_cost, 2)})
        for k, v in (("visitors", visitors), ("signups", signups), ("activated", activated), ("new_paying", new_paying),
                     ("net", net), ("marketing", marketing), ("cost", cost), ("active", active), ("paying", paying),
                     ("referred", new_referred), ("paid_signups", paid_signups), ("new_paying_paid", new_paying_paid)):
            tot[k] += v
        referred = new_referred
        visitors *= 1 + s["traffic_growth"]
    cac = tot["marketing"] / tot["new_paying"] if tot["new_paying"] > 0 else None
    cac_paid = tot["marketing"] / tot["new_paying_paid"] if tot["new_paying_paid"] > 0 else None
    arpu = tot["net"] / tot["active"] if tot["active"] > 0 else 0.0
    arppu = tot["net"] / tot["paying"] if tot["paying"] > 0 else 0.0
    per_unit = net_of(price, g) * g["gross_margin"]
    if model_kind == "one_time":
        ltv = per_unit * (1 + pick(g, "repeat_purchase_rate"))
        payback = (0.0 if (cac or 0) <= ltv else None) if cac is not None else None
        payback_paid = (0.0 if cac_paid <= ltv else None) if cac_paid is not None else None
    else:
        life = min(1.0 / churn, g["ltv_cap_months"]) if churn > 0 else g["ltv_cap_months"]
        ltv = per_unit * life
        payback = (cac / per_unit) if (cac and per_unit > 0) else (0.0 if cac == 0 else None)
        payback_paid = (cac_paid / per_unit) if (cac_paid and per_unit > 0) else None
    roi = (tot["net"] * g["gross_margin"] - tot["cost"]) / tot["cost"] if tot["cost"] > 0 else None
    funnel = [  # AARRR за весь горизонт; Retention — средняя активная база в месяц
        {"stage": "acquisition", "label": "Установки" if mobile else "Посетители", "value": round(tot["visitors"])},
        {"stage": "activation", "label": "Активированные", "value": round(tot["activated"], 1)},
        {"stage": "retention", "label": "Активные в месяц (среднее)", "value": round(tot["active"] / months, 1)},
        {"stage": "revenue", "label": "Новые доноры" if model_kind == "donations" else ("Новые покупатели" if model_kind == "one_time" else "Новые платящие"),
         "value": round(tot["new_paying"], 1)},
        {"stage": "referral", "label": "Регистрации по приглашениям", "value": round(tot["referred"], 1)},
    ]
    totals = {"visitors": round(tot["visitors"]), "signups": round(tot["signups"], 1), "activated": round(tot["activated"], 1),
              "new_paying": round(tot["new_paying"], 1), "net_revenue": round(tot["net"], 2),
              "cost": round(tot["cost"], 2), "marketing": round(tot["marketing"], 2)}
    if mobile:
        totals["installs"] = totals["visitors"]
    paid = {"mode": paid_mode, "marketing": round(tot["marketing"], 2), "signups": round(tot["paid_signups"], 1),
            "new_paying": round(tot["new_paying_paid"], 2), "cac_paid": r2(cac_paid), "cac_blended": r2(cac),
            "ltv_cac_paid": r2(ltv / cac_paid) if cac_paid else None, "payback_paid_months": r2(payback_paid),
            "unit": "установка" if per_install else "регистрация", "conversion_factor": pcf,
            "note": ("бюджет %s в месяц / стоимость единицы, поверх органики" % r2(budget)) if paid_mode == "budget" else
                    ("доля %s %s из платных каналов" % (r2(paid_share), "установок" if per_install else "регистраций")) if paid_mode == "share"
                    else "платного канала нет"}
    return {"funnel": funnel, "monthly": monthly, "cac": r2(cac), "cac_paid": r2(cac_paid), "ltv": r2(ltv),
            "ltv_cac": r2(ltv / cac) if cac else None, "ltv_cac_paid": paid["ltv_cac_paid"],
            "payback_months": r2(payback), "breakeven_month": breakeven, "arpu": r2(arpu), "arppu": r2(arppu),
            "churn": churn if model_kind != "one_time" else None, "roi": r2(roi), "paid": paid, "totals": totals}


def sensitivity(common, sc, months, kind, step=0.2):
    """Чувствительность базового сценария: ±step по каждому ключевому параметру → выручка, база, безубыточность."""
    def outcome(r):
        last = r["monthly"][-1] if r["monthly"] else {}
        return {"net_revenue": r["totals"]["net_revenue"], "users_last": last.get("users"), "paying_last": last.get("paying"),
                "breakeven_month": r["breakeven_month"]}
    base = outcome(simulate(common, sc, months, kind))
    items = []
    for key, label in SENS_KEYS:
        where = common if key in common else sc if key in sc else None
        if where is None:
            continue
        v0 = val(where[key])
        if not is_number(v0) or v0 == 0:
            continue
        res = {}
        for tag, k in (("low", 1 - step), ("high", 1 + step)):
            v = v0 * k
            if key not in ("visitors_month", "installs_month") and not key.startswith("price") and key != "donation_month":
                v = min(v, 0.999)
            c2, s2 = copy.deepcopy(common), copy.deepcopy(sc)
            (c2 if where is common else s2)[key] = v
            res[tag] = dict(outcome(simulate(c2, s2, months, kind)), value=round(v, 6))
        items.append({"param": key, "label": label, "base_value": v0, "low": res["low"], "high": res["high"],
                      "swing_net_revenue": round(abs(res["high"]["net_revenue"] - res["low"]["net_revenue"]), 2)})
    items.sort(key=lambda x: -x["swing_net_revenue"])
    return {"scenario": "base", "step": step, "base": base, "items": items,
            "note": "каждый параметр по отдельности ×%s и ×%s, остальные — как в базовом сценарии" % (1 - step, 1 + step)}


def audience_data(params):
    """Есть ли хоть один вход воронки с меткой «факт» или «оценка» (данные об аудитории)."""
    for sc in (params.get("scenarios") or {}).values():
        for k in AUDIENCE_KEYS:
            if isinstance(sc.get(k), dict) and sc[k].get("label") in ("факт", "оценка"):
                return True
    return False


def load_effort_plan(out_dir):
    """Предложения P0–P1 (порядок dep_rank, иначе rank) с серединой effort_days из data/scores.json + proposals.json."""
    if out_dir is None:
        return None, "нет папки прогона"
    try:
        S = json.loads((Path(out_dir) / "data" / "scores.json").read_text(encoding="utf-8"))
        P = json.loads((Path(out_dir) / "data" / "proposals.json").read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None, "нет data/scores.json или data/proposals.json — запустите score.py и перезапустите model.py"
    props = {p.get("id"): p for p in P if isinstance(p, dict)}
    rows = [s for s in S if isinstance(s, dict) and s.get("priority") in ("P0", "P1")]
    by = "dep_rank" if rows and all(isinstance(s.get("dep_rank"), int) for s in rows) else "rank"
    rows.sort(key=lambda s: s.get(by) or 10 ** 6)
    plan = []
    for s in rows:
        ed = (props.get(s["id"]) or {}).get("effort_days")
        if isinstance(ed, list) and len(ed) == 2 and all(isinstance(x, (int, float)) for x in ed):
            plan.append((s["id"], float(ed[0]), (ed[0] + ed[1]) / 2.0))
        else:
            plan.append((s["id"], 0.0, float(s.get("effort_days_mid") or 0.0)))
    return {"order_by": by, "items": plan}, None


def capacity_block(cfg, months, support_hours_total, out_dir, team_size=None):
    """Блок capacity model.json из capacity.py (одно определение дня и ёмкости) + сколько P0–P1 помещается."""
    cfg = copy.deepcopy(cfg or {})
    if team_size and not (cfg.get("project") or {}).get("team_size"):
        cfg.setdefault("project", {})["team_size"] = int(team_size)
    c = capmod.capacity(cfg, months)
    sup_days = support_hours_total / c["day_hours"] if c["day_hours"] else 0.0
    avail = max(0.0, c["dev_days"] - sup_days)
    clean = lambda x: int(x) if float(x).is_integer() else x
    cap = {"team_size": c["team_size"], "hours_per_week": clean(c["hours_per_week"]), "dev_share": c["dev_share"],
           "day_hours": clean(c["day_hours"]), "days_per_month": c["dev_days_month"], "hours_per_day": clean(c["day_hours"]),
           "hours_month": c["hours_month"], "horizon_months": months, "dev_hours_total": c["dev_hours"],
           "dev_days_total": c["dev_days"], "support_days_base": round(sup_days, 1), "dev_days_available": round(avail, 1),
           "source": c["source"], "line": c["line"],
           "note": "ёмкость — scripts/capacity.py (run-config project.capacity): часы в неделю × доля разработки ÷ часов в дне; "
                   "минус поддержка базового сценария"}
    plan, why = load_effort_plan(out_dir)
    if plan is None:
        cap["p0_p1"] = {"skipped": why}
    else:
        acc, fits, rest = 0.0, [], []
        for pid, lo, mid in plan["items"]:   # строгий префикс по порядку: следующее не начинается раньше предыдущего
            if not rest and acc + mid <= avail + 1e-9:
                acc += mid
                fits.append(pid)
            else:
                rest.append(pid)
        tot_mid = sum(x[2] for x in plan["items"])
        cap["p0_p1"] = {"count": len(plan["items"]), "order_by": plan["order_by"],
                        "effort_days_min_total": round(sum(x[1] for x in plan["items"]), 1),
                        "effort_days_mid_total": round(tot_mid, 1), "fits_count": len(fits), "fits_ids": fits,
                        "not_fit_ids": rest, "utilization": round(tot_mid / avail, 2) if avail else None}
    return cap


def solo_block(params, res, months, out_dir, profile_name="zero-budget-solo", cfg=None):
    """Метрики профиля zero-budget-solo / oss (время вместо денег) → (solo, capacity)."""
    so = {k: float(val(v)) for k, v in dict(SOLO_PARAMS, **(params.get("solo") or {})).items() if is_number(val(v))}
    g = {k: float(val(v)) for k, v in params["common"].items() if is_number(val(v))}
    cfg = cfg or {}
    cap_h = capmod.capacity(dict(cfg, project=dict(cfg.get("project") or {}, team_size=(cfg.get("project") or {}).get("team_size") or int(so["team_size"]))),
                            months)["hours_month"]
    rate = so["hourly_rate"]
    kind = res["revenue_model"]
    per_pay = net_of(unit_price(g, kind), g) * g["gross_margin"]
    sup_pay = so["support_hours_per_paying_month"] * rate * (12 if kind == "one_time" else 1)
    after = per_pay - sup_pay
    sup_free = so["support_hours_per_active_month"] * rate
    out = {"profile": profile_name, "params": {k: labelled(v) for k, v in (params.get("solo") or SOLO_PARAMS).items()},
           "capacity_hours_month": round(cap_h, 1),
           "support": {"net_margin_per_paying": round(per_pay, 2), "support_cost_per_paying": round(sup_pay, 2),
                       "margin_after_support": round(after, 2), "support_eats_revenue": after <= 0,
                       "support_cost_per_active": round(sup_free, 2),
                       "free_actives_per_paying": round(after / sup_free, 1) if after > 0 and sup_free > 0 else 0.0,
                       "basis": "на платящего в месяц" if kind != "one_time" else "покупка против поддержки за 12 мес."},
           "scenarios": {}, "notes": []}
    for name, sc in res["scenarios"].items():
        gm = g["gross_margin"]
        cum_m = cum_t = cum_f = 0.0
        tb = cap_month = None
        sup_tot = 0.0
        monthly = []
        for m in sc["monthly"]:
            sh = m["paying"] * so["support_hours_per_paying_month"] + m["users"] * so["support_hours_per_active_month"]
            sup_tot += sh
            fixed = m["cost"] - m["marketing"]
            cum_m += m["revenue"] * gm
            cum_f += fixed
            cum_t = m["month"] * cap_h * rate + cum_f
            if tb is None and cum_m >= cum_t and cum_t > 0:
                tb = m["month"]
            if cap_month is None and cap_h > 0 and sh / cap_h >= so["support_capacity_alert"]:
                cap_month = m["month"]
            monthly.append({"month": m["month"], "cum_margin": round(cum_m, 2), "cum_time_cost": round(cum_t, 2),
                            "support_hours": round(sh, 1)})
        act = sc["totals"].get("activated") or 0.0
        hours = cap_h * months
        growth_h = hours * so["growth_time_share"]
        out["scenarios"][name] = {
            "hours_per_activated": round(growth_h / act, 2) if act > 0 else None,
            "growth_hours": round(growth_h, 1), "dev_hours": round(hours, 1),
            "time_cost": round(hours * rate, 2), "revenue_per_hour": round((cum_m - cum_f) / hours, 2) if hours else None,
            "time_breakeven_month": tb, "support_hours_total": round(sup_tot, 1),
            "support_cost_total": round(sup_tot * rate, 2), "support_capacity_month": cap_month,
            "paying_new_total": sc["totals"]["new_paying"], "paying_end": sc["monthly"][-1]["paying"] if sc["monthly"] else 0,
            "net_revenue_total": sc["totals"]["net_revenue"], "monthly": monthly}
    base = out["scenarios"].get("base") or next(iter(out["scenarios"].values()))
    cap = capacity_block(cfg, months, base["support_hours_total"], out_dir, so["team_size"])
    out["capacity"] = cap
    b = out["scenarios"].get("base", base)
    out["notes"] = [
        "CAC неприменим: платного привлечения нет; стоимость роста — время разработчика (%.0f ч на активированного, базовый)."
        % (b["hours_per_activated"] or 0),
        "ROI неприменим: денежных вложений нет; смотрите безубыточность по времени и выручку на час.",
        "Поддержка: %s на %s против %s валовой выручки с него — %s." % (
            round(sup_pay, 2), "донора" if kind == "donations" else "платящего", round(per_pay, 2),
            "съедает выручку" if after <= 0 else "выручка покрывает"),
    ]
    if profile_name == "oss":
        out["notes"].insert(0, "Профиль oss: доход — поддержка (донаты %s в месяц на донора, спонсоры %s в месяц), затраты — время." % (
            round(unit_price(g, kind), 2), round(pick(g, "sponsors_month"), 2)))
    return out, cap


def personal_simulate(common, sc, months, hours_month):
    """Помесячный расчёт личного инструмента: до начала использования — часы разработки (вся ёмкость), после — поддержка."""
    g = {k: float(val(v)) for k, v in common.items() if is_number(val(v))}
    s = {k: float(val(v)) for k, v in sc.items() if is_number(val(v))}
    rate, users = g.get("hourly_rate", 0.0), max(1.0, g.get("users", 1.0))
    start = max(1, int(g.get("use_start_month", 1)))
    cum_v = cum_c = cum_hs = cum_hsp = 0.0
    pay_m = hours_m = None
    monthly = []
    for m in range(1, months + 1):
        using = m >= start
        spent_h = s.get("support_hours_month", 0.0) if using else hours_month
        saved_h = s.get("hours_saved_per_week", 0.0) * capmod.WEEKS_PER_MONTH * users if using else 0.0
        value = (saved_h * rate + (s.get("money_saved_month", 0.0) + s.get("errors_avoided_month", 0.0) * s.get("cost_per_error", 0.0)) * users
                 ) if using else 0.0
        cost = spent_h * rate + s.get("fixed_cost_month", 0.0)
        cum_v += value
        cum_c += cost
        cum_hs += saved_h
        cum_hsp += spent_h
        if pay_m is None and cum_c > 0 and cum_v >= cum_c:
            pay_m = m
        if hours_m is None and cum_hsp > 0 and cum_hs >= cum_hsp:
            hours_m = m
        monthly.append({"month": m, "using": using, "hours_spent": round(spent_h, 1), "hours_saved": round(saved_h, 1),
                        "value": round(value, 2), "cost": round(cost, 2), "cum_value": round(cum_v, 2), "cum_cost": round(cum_c, 2),
                        "cum_hours_saved": round(cum_hs, 1), "cum_hours_spent": round(cum_hsp, 1)})
    n_use = max(0, months - start + 1)
    other = sum(x["value"] for x in monthly) - sum(x["hours_saved"] for x in monthly) * rate
    per_hour_week = capmod.WEEKS_PER_MONTH * users * rate * n_use
    need = (cum_c - other) / per_hour_week if per_hour_week > 0 else None
    return {"monthly": monthly, "payback_month": pay_m, "hours_payback_month": hours_m, "use_start_month": start,
            "totals": {"hours_spent": round(cum_hsp, 1), "hours_saved": round(cum_hs, 1), "value": round(cum_v, 2),
                       "cost": round(cum_c, 2), "net_value": round(cum_v - cum_c, 2)},
            "roi": round((cum_v - cum_c) / cum_c, 2) if cum_c > 0 else None,
            "hours_saved_per_week_to_break_even": round(max(0.0, need), 2) if need is not None else None}


def personal_build(params, months, cfg, out_dir, res):
    """Профиль personal: стоимость владения и окупаемость личных усилий → заполняет res (сценарии, personal, capacity)."""
    common = params["common"]
    c = capmod.capacity(cfg, months)
    labels = params.get("scenario_labels") or SCENARIO_LABELS_PERSONAL
    pers = {"scenario_labels": labels, "hours_month_build": c["hours_month"], "scenarios": {}, "notes": []}
    for name in SCENARIOS:
        sc = params["scenarios"][name]
        r = personal_simulate(common, sc, months, c["hours_month"])
        assumptions = {k: labelled(v) for k, v in common.items()}
        assumptions.update({k: labelled(v) for k, v in sc.items()})
        assumptions["revenue_model"] = labelled(params.get("revenue_model", "none"))
        res["scenarios"][name] = {"assumptions": assumptions, "label": labels.get(name, name), "totals": r["totals"],
                                  "net_value": r["totals"]["net_value"], "value": r["totals"]["value"], "cost": r["totals"]["cost"],
                                  "hours_spent": r["totals"]["hours_spent"], "hours_saved": r["totals"]["hours_saved"],
                                  "breakeven_month": r["payback_month"], "hours_breakeven_month": r["hours_payback_month"],
                                  "roi": r["roi"], "cac": None, "ltv": None, "payback_months": None,
                                  "hours_saved_per_week_to_break_even": r["hours_saved_per_week_to_break_even"]}
        pers["scenarios"][name] = r
    # чувствительность: ±20 % по каждому ключевому параметру базового сценария → чистая ценность
    base_sc = params["scenarios"]["base"]
    b0 = personal_simulate(common, base_sc, months, c["hours_month"])["totals"]["net_value"]
    items = []
    for key, label in PERSONAL_SENS:
        v0 = val(base_sc.get(key))
        if not is_number(v0) or v0 == 0:
            continue
        out = {}
        for tag, k in (("low", 0.8), ("high", 1.2)):
            s2 = copy.deepcopy(base_sc)
            s2[key] = v0 * k
            out[tag] = {"value": round(v0 * k, 6), "net_value": personal_simulate(common, s2, months, c["hours_month"])["totals"]["net_value"]}
        items.append({"param": key, "label": label, "base_value": v0, "low": out["low"], "high": out["high"],
                      "swing_net_value": round(abs(out["high"]["net_value"] - out["low"]["net_value"]), 2)})
    items.sort(key=lambda x: -x["swing_net_value"])
    res["sensitivity"] = {"scenario": "base", "step": 0.2, "base": {"net_value": b0}, "items": items,
                          "note": "каждый параметр по отдельности ×0,8 и ×1,2, остальные — как в обычном сценарии"}
    b = pers["scenarios"]["base"]
    sym = res["currency_symbol"]
    pers["notes"] = [
        "Профиль personal: выручки, воронки, CAC и LTV нет; ценность — сэкономленное время × цена часа %s %s + сэкономленные деньги "
        "+ предотвращённые ошибки; затраты — часы разработки до месяца %s (вся ёмкость, %s ч/мес.) и поддержки после, плюс сервисы."
        % (fmt_money(val(common.get("hourly_rate")) or 0), sym, b["use_start_month"], c["hours_month"]),
        "Окупаемость личных усилий (обычный сценарий): по деньгам — %s, по часам — %s; чтобы окупиться за горизонт, нужно "
        "экономить ≈ %s ч в неделю." % ("месяц %s" % b["payback_month"] if b["payback_month"] else "не за горизонт",
                                         "месяц %s" % b["hours_payback_month"] if b["hours_payback_month"] else "не за горизонт",
                                         b["hours_saved_per_week_to_break_even"]),
    ]
    if str(((cfg or {}).get("project") or {}).get("audience") or "") == "personal_then_public":
        pers["notes"].append("Выпуск наружу возможен позже: при переходе к аудитории пересоздайте build/model-params.json с профилем "
                             "web-direct или saas (strategy.model_profile) — раздел «Если захочется выпустить наружу».")
    res["personal"] = pers
    sup = sum(x["hours_spent"] for x in b["monthly"] if x["using"])
    res["capacity"] = capacity_block(cfg, months, sup, out_dir)


def fmt_money(x):
    return ("%d" % x) if float(x).is_integer() else ("%.2f" % x)


ACT_RE = re.compile(r"\bактивац|\bactivation", re.I)   # не «реактивация»
RANGE_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:[–—-]|\.\.)\s*(\d+(?:[.,]\d+)?)\s*%")


def registry_items(params, res, out_dir):
    """Сверка модели с реестром: доля активации в модели против диапазона effect_kpi «активация» у предложений (SM 6.1)."""
    if out_dir is None or res.get("model_profile") == "personal":
        return []
    try:
        props = json.loads((Path(out_dir) / "data" / "proposals.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    v = val((params["scenarios"].get("base") or {}).get("signup_to_active"))
    if not is_number(v):
        return []
    items = []
    for p in props if isinstance(props, list) else []:
        for k in (p.get("effect_kpi") or []) if isinstance(p, dict) else []:
            if not isinstance(k, dict) or not ACT_RE.search(str(k.get("kpi") or "")):
                continue
            m = RANGE_RE.search(str(k.get("range") or ""))
            if not m or str(k.get("range") or "").lstrip().startswith(("+", "−", "-")):
                continue                                                   # прирост «+5..10 п. п.» — не уровень
            lo, hi = (float(x.replace(",", ".")) / 100.0 for x in m.groups())
            if not (lo - 1e-9 <= v <= hi + 1e-9):
                items.append({"what": "activation", "model": v, "registry": [lo, hi], "proposal": p.get("id"),
                              "message": "активация в модели %s (base.signup_to_active), а %s ожидает «%s» %s — одно определение активации"
                                         % (v, p.get("id"), k.get("kpi"), k.get("range"))})
            break
        if len(items) >= 5:
            break
    return items


def reconcile(params, res, out_dir):
    """Сверка модели с планом (data/plan-baseline.json): начало выручки, горизонт, ёмкость → список расхождений."""
    plan = load_plan(out_dir)
    items = registry_items(params, res, out_dir)
    if not plan:
        return {"plan": None, "items": items, "ok": not items} if items else None
    if res.get("model_profile") != "personal" and res.get("revenue_model") != "donations":
        want = plan_month(plan, "paid", "launch")
        have = int(val(params["common"].get("revenue_start_month")) or 1)
        if want and have < want:
            items.append({"what": "revenue_start", "model": have, "plan": want,
                          "message": "выручка в модели с месяца %d, а платная часть в плане — с месяца %d: задайте common.revenue_start_month = %d"
                                     % (have, want, want)})
    ph = plan.get("horizon_months")
    if isinstance(ph, (int, float)) and int(ph) != res["horizon_months"]:
        items.append({"what": "horizon", "model": res["horizon_months"], "plan": int(ph),
                      "message": "горизонт модели %d мес., плана — %d мес." % (res["horizon_months"], ph)})
    pc = (plan.get("capacity") or {}).get("dev_days")
    mc = (res.get("capacity") or {}).get("dev_days_total")
    if isinstance(pc, (int, float)) and isinstance(mc, (int, float)) and int(ph or 0) == res["horizon_months"] and abs(pc - mc) > 0.11:
        items.append({"what": "capacity", "model": mc, "plan": pc,
                      "message": "ёмкость модели %s дн., в plan-baseline — %s дн.: перезапустите plan_baseline.py после правки project.capacity"
                                 % (mc, pc)})
    for sc in res["scenarios"].values():
        be = sc.get("breakeven_month")
        mo = sc.get("monthly") or []
        if isinstance(be, int) and 1 <= be <= len(mo) and mo[be - 1].get("cum_cost", 0) and mo[be - 1]["cum_cost"] < 3 * (mo[0].get("cost") or 0) + 1e-9 \
                and be <= 2:
            sc["breakeven_note"] = "безубыточность в месяц %d на очень малых суммах (затраты %s) — не вывод о модели" % (be, mo[be - 1]["cum_cost"])
    return {"plan": "data/plan-baseline.json", "items": items, "ok": not items}


def build(params, months, cfg=None, out_dir=None):
    """Модель по параметрам → объект data/model.json."""
    kind = val(params.get("revenue_model", "subscription"))
    common = params["common"]
    cfg = cfg or {}
    profile = (cfg.get("strategy") or {}).get("profile") or "standard"
    mprofile = val(params.get("model_profile")) or "saas"
    if mprofile not in MODEL_PROFILES:
        mprofile = "saas"
    code, preset = currency_preset(params.get("currency", "USD"))
    if mprofile == "personal":
        has_data = any(isinstance(sc.get(k), dict) and sc[k].get("label") in ("факт", "оценка")
                       for sc in params["scenarios"].values() for k in ("hours_saved_per_week", "money_saved_month"))
    else:
        has_data = audience_data(params)
    mode = val(params.get("mode")) or (cfg.get("strategy") or {}).get("model_mode")
    mode = mode if mode in MODES else ("forecast" if has_data else "sensitivity-only")
    res = {"currency": params.get("currency", "USD"), "currency_symbol": (preset or {}).get("symbol", code),
           "profile": profile, "model_profile": mprofile, "revenue_model": kind, "horizon_months": months,
           "mode": mode, "forecast": mode == "forecast", "audience_data": has_data, "scenarios": {}, "notes": []}
    legacy = [k for k in ("days_per_month", "hours_per_day") if k in (params.get("solo") or {})]
    if mprofile == "personal":
        personal_build(params, months, cfg, out_dir, res)
        n_assumed = sum(1 for sc in res["scenarios"].values() for a in sc["assumptions"].values() if a["label"] == A)
        res["notes"] = ["Все входы — помеченные параметры из build/model-params.json; допущений: %d. Замените их оценками владельца." % n_assumed] \
            + res["personal"]["notes"] + list(params.get("notes") or [])
    else:
        for name in SCENARIOS:
            sc = params["scenarios"][name]
            r = simulate(common, sc, months, kind)
            assumptions = {k: labelled(v) for k, v in common.items()}
            assumptions.update({k: labelled(v) for k, v in sc.items()})
            assumptions["revenue_model"] = labelled(params.get("revenue_model", "subscription"))
            res["scenarios"][name] = dict(assumptions=assumptions, **r)
        res["sensitivity"] = sensitivity(common, params["scenarios"]["base"], months, kind)
        n_assumed = sum(1 for sc in res["scenarios"].values() for a in sc["assumptions"].values() if a["label"] == A)
        res["notes"] = [
            "Все входы — помеченные параметры из build/model-params.json; допущений: %d. Замените их фактами владельца." % n_assumed,
            "CAC — смешанный, на нового платящего (маркетинг / все новые платящие); cac_paid — только платный канал "
            "(маркетинг / новые платящие из платного канала, блок paid); органика учитывается через постоянные затраты.",
            "LTV для подписки ограничен %s мес.; для разовой покупки — чистая цена × маржа × (1 + повторные покупки)."
            % val(common.get("ltv_cap_months", 36)),
            "Формулы — в docstring scripts/model.py и references/scoring.md.",
        ] + list(params.get("notes") or [])
    if mprofile == "mobile-app":
        res["notes"].append("Профиль mobile-app: верх воронки — установки (installs_month), комиссия магазина store_fee = %s, возвраты %s."
                            % (val(common.get("store_fee", 0)), val(common.get("refund_rate", 0))))
    elif mprofile == "one_time_purchase":
        res["notes"].append("Профиль one_time_purchase: выручка — разовые покупки; отток не используется, LTV учитывает повторные покупки.")
    elif mprofile == "web-direct":
        res["notes"].append("Профиль web-direct: веб/PWA, оплата напрямую через платёжный сервис — верх воронки посетители, магазина нет; "
                            "комиссия провайдера payment_fee = %s, налог tax_rate = %s (пакет локали; проверить по первоисточнику)."
                            % (val(common.get("payment_fee", 0)), val(common.get("tax_rate", 0))))
    if int(val(common.get("revenue_start_month")) or 1) > 1 and mprofile != "personal":
        res["notes"].append("Выручка — с месяца %s (common.revenue_start_month, по плану); до него платящих нет." % val(common["revenue_start_month"]))
    if legacy:
        res["notes"].append("solo.%s в build/model-params.json больше не задают ёмкость: она считается scripts/capacity.py из run-config "
                            "project.capacity (одно определение рабочего дня для модели, плана и текстов)." % " и solo.".join(legacy))
    if mode == "sensitivity-only":
        res["notes"].append("Режим sensitivity-only: %s; числа сценариев — иллюстрация, а не прогноз. Опора решений — блок sensitivity "
                            "(какие параметры сильнее всего меняют %s)." % (
                                ("оценок владельца нет (все входы — допущения)" if mprofile == "personal" else
                                 "данных об аудитории нет (все входы воронки — допущения)") if not has_data else "задан явно",
                                "чистую ценность" if mprofile == "personal" else "выручку и базу"))
    if mprofile != "personal" and (profile == "zero-budget-solo" or mprofile == "oss"):
        solo, cap = solo_block(params, res, months, out_dir, "oss" if mprofile == "oss" else "zero-budget-solo", cfg)
        na = "неприменимо (OSS: доход — поддержка, затраты — время)" if mprofile == "oss" else ROI_NA
        for name, sc in res["scenarios"].items():
            sc["roi"] = na
            sc["roi_note"] = "денежных вложений нет — затраты это время разработчика: solo.scenarios.%s" % name
            sc["cac"] = None
            sc["cac_paid"] = None
            sc["cac_note"] = "неприменимо: платного привлечения нет; см. solo.scenarios.%s.hours_per_activated" % name
            sc["ltv_cac"] = None
            sc["ltv_cac_paid"] = None
            sc["payback_months"] = None
        res["solo"] = solo
        res["capacity"] = cap
        res["notes"][1] = ("Профиль oss: CAC и ROI неприменимы (доход — донаты и спонсоры, затраты — время), метрики усилий — в solo."
                           if mprofile == "oss" else
                           "Профиль zero-budget-solo: CAC и ROI неприменимы (нулевой бюджет), метрики усилий — в solo.")
    elif mprofile != "personal":
        res["capacity"] = capacity_block(cfg, months, 0.0, out_dir)
    if mode == "sensitivity-only":
        ill = {}
        for name, sc in res["scenarios"].items():
            sc["illustrative"] = True
            row = {k: sc.get(k) for k in ILLUSTRATIVE_KEYS if is_number(sc.get(k))}
            row.update({k: v for k, v in (sc.get("totals") or {}).items() if k in ("net_revenue", "value", "net_value", "cost") and is_number(v)})
            ill[name] = row
        res["illustration"] = {"label": ILLUSTRATION_LABEL, "scenarios": ill,
                               "note": "режим sensitivity-only: денежные итоги — иллюстрация при допущениях, не прогноз; в тексте — только "
                                       "с меткой %s (assemble_strategy.py ставит её к {model:…} сам)" % ILLUSTRATION_LABEL}
    rc = reconcile(params, res, out_dir)
    if rc is not None:
        res["reconciliation"] = rc
    return res


def main(argv=None):
    ap = argparse.ArgumentParser(description="Юнит-экономика и воронка AARRR в трёх сценариях.")
    ap.add_argument("out", help="папка прогона <OUT>")
    ap.add_argument("--params", help="JSON с параметрами (по умолчанию build/model-params.json)")
    ap.add_argument("--months", type=int, help="горизонт в месяцах (иначе из run-config или 12)")
    a = ap.parse_args(argv)
    out_dir = Path(a.out).resolve()
    ppath = Path(a.params) if a.params else out_dir / "build" / "model-params.json"
    cfg_path = out_dir / "build" / "run-config.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8")) if cfg_path.exists() else {}
    if ppath.exists():
        given = json.loads(ppath.read_text(encoding="utf-8"))
        prof = val(given.get("model_profile")) if isinstance(given, dict) else None
        if prof not in MODEL_PROFILES:
            want_prof = select_profile(cfg)[0]
            prof = "saas"                                  # файл 1.x без профиля: прежняя механика
            if want_prof != "saas":
                print("! в %s нет model_profile — считаю saas (как раньше); по run-config подходит %s — удалите файл, "
                      "чтобы пересоздать с этим профилем" % (ppath.name, want_prof))
        params = deep_merge(default_params(cfg, prof, out_dir), given)
        if not given.get("model_profile"):
            params.pop("model_profile", None)
        want = (cfg.get("project") or {}).get("currency")
        if want and str(want).upper() != str(params.get("currency")).upper():
            print("! валюта в %s (%s) не совпадает с project.currency (%s) — удалите файл, чтобы пересоздать"
                  % (ppath.name, params.get("currency"), want))
    else:
        params = defaults = default_params(cfg, None, out_dir)
        if not a.params:
            ppath.parent.mkdir(parents=True, exist_ok=True)
            ppath.write_text(json.dumps(defaults, ensure_ascii=False, indent=2), encoding="utf-8")
            print("Создан %s с допущениями по умолчанию — отредактируйте и перезапустите." % ppath)
        else:
            print("нет файла параметров %s" % ppath, file=sys.stderr)
            return 1
    months = a.months or int((cfg.get("strategy") or {}).get("horizon_months") or 12)
    months = max(1, months)
    model = build(params, months, cfg, out_dir)
    (out_dir / "data").mkdir(parents=True, exist_ok=True)
    (out_dir / "data" / "model.json").write_text(json.dumps(model, ensure_ascii=False, indent=2), encoding="utf-8")
    cur = model["currency"]
    print("Модель: %s, профиль %s, горизонт %d мес., валюта %s, режим %s" % (model["revenue_model"], model["model_profile"], months, cur,
                                                                          model["mode"]))
    for name, sc in model["scenarios"].items():
        if model["model_profile"] == "personal":
            print("  %-11s (%s) ценность %s, затраты %s, чистая %s %s; окупаемость: деньги мес. %s, часы мес. %s; нужно экономить %s ч/нед"
                  % (name, sc.get("label"), sc["value"], sc["cost"], sc["net_value"], model["currency_symbol"], sc["breakeven_month"],
                     sc["hours_breakeven_month"], sc["hours_saved_per_week_to_break_even"]))
            continue
        print("  %-11s CAC %s (платный %s), LTV %s, окупаемость %s мес., безубыточность мес. %s, ROI %s, выручка %s"
              % (name, sc["cac"], sc.get("cac_paid"), sc["ltv"], sc["payback_months"], sc["breakeven_month"], sc["roi"],
                 sc["totals"]["net_revenue"]))
    if model["mode"] == "sensitivity-only":
        top = model["sensitivity"]["items"][:3]
        print("  sensitivity-only: денежные итоги — иллюстрация %s, прогноз не публиковать; сильнее всего влияют: %s"
              % (ILLUSTRATION_LABEL, ", ".join("%s (±%s)" % (i["label"], i.get("swing_net_revenue", i.get("swing_net_value"))) for i in top)))
    if model.get("solo"):
        so = model["solo"]
        for name, x in so["scenarios"].items():
            print("  %-11s ч на активированного %s, выручка на час %s %s, безубыточность по времени мес. %s, поддержка %s ч"
                  % (name, x["hours_per_activated"], x["revenue_per_hour"], model["currency_symbol"], x["time_breakeven_month"],
                     x["support_hours_total"]))
    c = model.get("capacity")
    if c:
        pp = c.get("p0_p1") or {}
        print("  ёмкость: %s дн. за %s мес. (после поддержки %s); %s; P0–P1: %s"
              % (c["dev_days_total"], c["horizon_months"], c["dev_days_available"], c.get("line", ""),
                 pp.get("skipped") or "%s из %s помещаются (сумма середин %s дн.)" % (pp["fits_count"], pp["count"], pp["effort_days_mid_total"])))
    for it in (model.get("reconciliation") or {}).get("items") or []:
        print("  ! сверка с планом: %s" % it["message"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
