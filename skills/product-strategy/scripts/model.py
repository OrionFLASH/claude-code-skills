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
Только стандартная библиотека.
"""
import argparse
import copy
import json
import math
import sys
from pathlib import Path

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
MONEY_COMMON = ("price_month", "price_one_time")
MONEY_SCEN = ("fixed_cost_month", "cost_per_paid_signup")
SOLO_SCEN = {  # профиль zero-budget-solo: без платных каналов, скромный органический трафик, почти нулевые затраты (USD)
    "pessimistic": {"visitors_month": 300, "traffic_growth": 0.03, "fixed_cost_month": 0.0},
    "base": {"visitors_month": 800, "traffic_growth": 0.06, "fixed_cost_month": 6.0},
    "optimistic": {"visitors_month": 2500, "traffic_growth": 0.10, "fixed_cost_month": 12.0},
}
SOLO_PARAMS = {
    "days_per_month": {"value": 12, "label": A, "note": "рабочих дней в месяц на проект на человека (личный проект — по вечерам и выходным)"},
    "hours_per_day": {"value": 6, "label": A, "note": "продуктивных часов в рабочий день"},
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


def default_params(cfg):
    """Параметры по умолчанию с учётом run-config: валюта, price_hint/traffic_hint, профиль."""
    cfg = cfg or {}
    project = cfg.get("project") or {}
    profile = (cfg.get("strategy") or {}).get("profile") or "standard"
    code, preset = currency_preset(project.get("currency") or "USD")
    P = copy.deepcopy(DEFAULT_PARAMS)
    P["currency"] = code
    f = preset["factor"] if preset else 1.0
    if not preset:
        P.setdefault("notes", []).append("нет пресета для валюты %s — суммы в масштабе USD-дефолтов, замените" % code)
    if profile == "zero-budget-solo":
        for name, over in SOLO_SCEN.items():
            sc = P["scenarios"][name]
            for k, v in over.items():
                sc[k]["value"] = v
            sc["paid_share"] = {"value": 0.0, "label": A, "note": "профиль zero-budget-solo: платных каналов нет"}
        P["solo"] = copy.deepcopy(SOLO_PARAMS)
        P["solo"]["hourly_rate"]["value"] = preset["hourly_rate"] if preset else SOLO_PARAMS["hourly_rate"]["value"]
        if isinstance(project.get("team_size"), (int, float)) and project["team_size"] > 0:
            P["solo"]["team_size"] = {"value": project["team_size"], "label": "факт", "note": "run-config project.team_size"}
    if f != 1.0:
        for k in MONEY_COMMON:
            P["common"][k]["value"] = nice(P["common"][k]["value"] * f)
        for sc in P["scenarios"].values():
            for k in MONEY_SCEN:
                sc[k]["value"] = nice(sc[k]["value"] * f)
    hint = project.get("price_hint")
    if isinstance(hint, (int, float)) and not isinstance(hint, bool) and hint > 0:
        P["common"]["price_month"] = {"value": float(hint), "label": "оценка", "note": "run-config project.price_hint"}
    th = project.get("traffic_hint")
    if isinstance(th, (int, float)) and not isinstance(th, bool) and th > 0:
        for name, k in (("pessimistic", 0.5), ("base", 1.0), ("optimistic", 3.0)):
            P["scenarios"][name]["visitors_month"] = {"value": round(th * k), "label": "оценка",
                                                      "note": "run-config project.traffic_hint × %s" % k}
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


def simulate(common, sc, months, model_kind):
    """Помесячный расчёт одного сценария."""
    g = {k: float(val(v)) for k, v in common.items()}
    s = {k: float(val(v)) for k, v in sc.items()}
    visitors = s["visitors_month"]
    active = paying = referred = 0.0
    monthly, tot = [], dict(visitors=0.0, signups=0.0, activated=0.0, new_paying=0.0, net=0.0, marketing=0.0,
                            cost=0.0, active=0.0, paying=0.0, referred=0.0)
    cum_margin = cum_cost = 0.0
    breakeven = None
    for m in range(1, months + 1):
        signups = visitors * s["visit_to_signup"] + referred
        activated = signups * s["signup_to_active"]
        active = active * s["retention_monthly"] + activated
        new_paying = activated * s["active_to_paying"]
        if model_kind == "one_time":
            paying = new_paying
            revenue = new_paying * g["price_one_time"]
        else:
            paying = paying * (1 - s["churn_monthly"]) + new_paying
            revenue = paying * g["price_month"]
        net = revenue * (1 - g["payment_fee"]) * (1 - g["refund_rate"])
        marketing = signups * s["paid_share"] * s["cost_per_paid_signup"]
        cost = s["fixed_cost_month"] + marketing
        cum_margin += net * g["gross_margin"]
        cum_cost += cost
        if breakeven is None and cum_cost > 0 and cum_margin >= cum_cost:
            breakeven = m
        new_referred = active * s["referral_rate"]
        monthly.append({"month": m, "visitors": round(visitors), "signups": round(signups, 1),
                        "users": round(active, 1), "paying": round(paying, 1), "new_paying": round(new_paying, 2),
                        "revenue": round(net, 2), "cost": round(cost, 2), "marketing": round(marketing, 2),
                        "cum_margin": round(cum_margin, 2), "cum_cost": round(cum_cost, 2)})
        for k, v in (("visitors", visitors), ("signups", signups), ("activated", activated), ("new_paying", new_paying),
                     ("net", net), ("marketing", marketing), ("cost", cost), ("active", active), ("paying", paying),
                     ("referred", new_referred)):
            tot[k] += v
        referred = new_referred
        visitors *= 1 + s["traffic_growth"]
    cac = tot["marketing"] / tot["new_paying"] if tot["new_paying"] > 0 else None
    arpu = tot["net"] / tot["active"] if tot["active"] > 0 else 0.0
    arppu = tot["net"] / tot["paying"] if tot["paying"] > 0 else 0.0
    if model_kind == "one_time":
        ltv = g["price_one_time"] * (1 - g["payment_fee"]) * (1 - g["refund_rate"]) * g["gross_margin"] * (1 + g["repeat_purchase_rate"])
        payback = (0.0 if (cac or 0) <= ltv else None) if cac is not None else None
    else:
        life = min(1.0 / s["churn_monthly"], g["ltv_cap_months"]) if s["churn_monthly"] > 0 else g["ltv_cap_months"]
        per_month = g["price_month"] * (1 - g["payment_fee"]) * (1 - g["refund_rate"]) * g["gross_margin"]
        ltv = per_month * life
        payback = (cac / per_month) if (cac and per_month > 0) else (0.0 if cac == 0 else None)
    roi = (tot["net"] * g["gross_margin"] - tot["cost"]) / tot["cost"] if tot["cost"] > 0 else None
    funnel = [  # AARRR за весь горизонт; Retention — средняя активная база в месяц
        {"stage": "acquisition", "label": "Посетители", "value": round(tot["visitors"])},
        {"stage": "activation", "label": "Активированные", "value": round(tot["activated"], 1)},
        {"stage": "retention", "label": "Активные в месяц (среднее)", "value": round(tot["active"] / months, 1)},
        {"stage": "revenue", "label": "Новые платящие", "value": round(tot["new_paying"], 1)},
        {"stage": "referral", "label": "Регистрации по приглашениям", "value": round(tot["referred"], 1)},
    ]
    return {"funnel": funnel, "monthly": monthly, "cac": r2(cac), "ltv": r2(ltv), "ltv_cac": r2(ltv / cac) if cac else None,
            "payback_months": r2(payback), "breakeven_month": breakeven, "arpu": r2(arpu), "arppu": r2(arppu),
            "churn": s["churn_monthly"] if model_kind != "one_time" else None, "roi": r2(roi),
            "totals": {"visitors": round(tot["visitors"]), "signups": round(tot["signups"], 1),
                       "activated": round(tot["activated"], 1),
                       "new_paying": round(tot["new_paying"], 1), "net_revenue": round(tot["net"], 2),
                       "cost": round(tot["cost"], 2), "marketing": round(tot["marketing"], 2)}}


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


def solo_block(params, res, months, out_dir):
    """Метрики профиля zero-budget-solo (время вместо денег) → (solo, capacity)."""
    so = {k: float(val(v)) for k, v in (params.get("solo") or SOLO_PARAMS).items()}
    g = {k: float(val(v)) for k, v in params["common"].items()}
    cap_h = so["team_size"] * so["days_per_month"] * so["hours_per_day"]
    rate = so["hourly_rate"]
    kind = res["revenue_model"]
    per_pay = (g["price_one_time"] if kind == "one_time" else g["price_month"]) * (1 - g["payment_fee"]) * (1 - g["refund_rate"]) * g["gross_margin"]
    sup_pay = so["support_hours_per_paying_month"] * rate * (12 if kind == "one_time" else 1)
    after = per_pay - sup_pay
    sup_free = so["support_hours_per_active_month"] * rate
    out = {"profile": "zero-budget-solo", "params": {k: labelled(v) for k, v in (params.get("solo") or SOLO_PARAMS).items()},
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
    plan, why = load_effort_plan(out_dir)
    base = out["scenarios"].get("base") or next(iter(out["scenarios"].values()))
    days_total = so["team_size"] * so["days_per_month"] * months
    sup_days = base["support_hours_total"] / so["hours_per_day"] if so["hours_per_day"] else 0.0
    avail = max(0.0, days_total - sup_days)
    clean = lambda x: int(x) if float(x).is_integer() else x
    cap = {"team_size": clean(so["team_size"]), "days_per_month": clean(so["days_per_month"]), "hours_per_day": clean(so["hours_per_day"]),
           "horizon_months": months, "dev_days_total": round(days_total, 1), "support_days_base": round(sup_days, 1),
           "dev_days_available": round(avail, 1),
           "note": "ёмкость = людей × дней/мес × месяцев; минус поддержка базового сценария; всё — допущения solo.*"}
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
    out["capacity"] = cap
    b = out["scenarios"].get("base", base)
    out["notes"] = [
        "CAC неприменим: платного привлечения нет; стоимость роста — время разработчика (%.0f ч на активированного, базовый)."
        % (b["hours_per_activated"] or 0),
        "ROI неприменим: денежных вложений нет; смотрите безубыточность по времени и выручку на час.",
        "Поддержка: %s на платящего против %s валовой выручки с него — %s." % (
            round(sup_pay, 2), round(per_pay, 2), "съедает выручку" if after <= 0 else "выручка покрывает"),
    ]
    return out, cap


def build(params, months, cfg=None, out_dir=None):
    """Модель по параметрам → объект data/model.json."""
    kind = val(params.get("revenue_model", "subscription"))
    common = params["common"]
    cfg = cfg or {}
    profile = (cfg.get("strategy") or {}).get("profile") or "standard"
    code, preset = currency_preset(params.get("currency", "USD"))
    res = {"currency": params.get("currency", "USD"), "currency_symbol": (preset or {}).get("symbol", code),
           "profile": profile, "revenue_model": kind, "horizon_months": months, "scenarios": {}, "notes": []}
    for name in SCENARIOS:
        sc = params["scenarios"][name]
        r = simulate(common, sc, months, kind)
        assumptions = {k: labelled(v) for k, v in common.items()}
        assumptions.update({k: labelled(v) for k, v in sc.items()})
        assumptions["revenue_model"] = labelled(params.get("revenue_model", "subscription"))
        res["scenarios"][name] = dict(assumptions=assumptions, **r)
    n_assumed = sum(1 for sc in res["scenarios"].values() for a in sc["assumptions"].values() if a["label"] == A)
    res["notes"] = [
        "Все входы — помеченные параметры из build/model-params.json; допущений: %d. Замените их фактами владельца." % n_assumed,
        "CAC — смешанный, на нового платящего, только по платным каналам; органика учитывается через постоянные затраты.",
        "LTV для подписки ограничен %s мес.; для разовой покупки — чистая цена × маржа × (1 + повторные покупки)."
        % val(common.get("ltv_cap_months", 36)),
        "Формулы — в docstring scripts/model.py и references/scoring.md.",
    ] + list(params.get("notes") or [])
    if profile == "zero-budget-solo":
        solo, cap = solo_block(params, res, months, out_dir)
        for name, sc in res["scenarios"].items():
            sc["roi"] = ROI_NA
            sc["roi_note"] = "денежных вложений нет — затраты это время разработчика: solo.scenarios.%s" % name
            sc["cac"] = None
            sc["cac_note"] = "неприменимо: платного привлечения нет; см. solo.scenarios.%s.hours_per_activated" % name
            sc["ltv_cac"] = None
            sc["payback_months"] = None
        res["solo"] = solo
        res["capacity"] = cap
        res["notes"][1] = "Профиль zero-budget-solo: CAC и ROI неприменимы (нулевой бюджет), метрики усилий — в solo."
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
    defaults = default_params(cfg)
    if ppath.exists():
        params = deep_merge(defaults, json.loads(ppath.read_text(encoding="utf-8")))
        want = (cfg.get("project") or {}).get("currency")
        if want and str(want).upper() != str(params.get("currency")).upper():
            print("! валюта в %s (%s) не совпадает с project.currency (%s) — удалите файл, чтобы пересоздать"
                  % (ppath.name, params.get("currency"), want))
    else:
        params = defaults
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
    print("Модель: %s, горизонт %d мес., валюта %s" % (model["revenue_model"], months, cur))
    for name, sc in model["scenarios"].items():
        print("  %-11s CAC %s, LTV %s, окупаемость %s мес., безубыточность мес. %s, ROI %s, выручка %s"
              % (name, sc["cac"], sc["ltv"], sc["payback_months"], sc["breakeven_month"], sc["roi"], sc["totals"]["net_revenue"]))
    if model.get("solo"):
        so = model["solo"]
        for name, x in so["scenarios"].items():
            print("  %-11s ч на активированного %s, выручка на час %s %s, безубыточность по времени мес. %s, поддержка %s ч"
                  % (name, x["hours_per_activated"], x["revenue_per_hour"], model["currency_symbol"], x["time_breakeven_month"],
                     x["support_hours_total"]))
        c = model["capacity"]
        pp = c.get("p0_p1") or {}
        print("  ёмкость: %s дн. за %s мес. (после поддержки %s); P0–P1: %s"
              % (c["dev_days_total"], c["horizon_months"], c["dev_days_available"],
                 pp.get("skipped") or "%s из %s помещаются (сумма середин %s дн.)" % (pp["fits_count"], pp["count"], pp["effort_days_mid_total"])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
