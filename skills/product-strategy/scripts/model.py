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
Только стандартная библиотека.
"""
import argparse
import copy
import json
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
                       "new_paying": round(tot["new_paying"], 1), "net_revenue": round(tot["net"], 2),
                       "cost": round(tot["cost"], 2), "marketing": round(tot["marketing"], 2)}}


def build(params, months):
    """Модель по параметрам → объект data/model.json."""
    kind = val(params.get("revenue_model", "subscription"))
    common = params["common"]
    res = {"currency": params.get("currency", "USD"), "revenue_model": kind, "horizon_months": months,
           "scenarios": {}, "notes": []}
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
    ]
    return res


def main(argv=None):
    ap = argparse.ArgumentParser(description="Юнит-экономика и воронка AARRR в трёх сценариях.")
    ap.add_argument("out", help="папка прогона <OUT>")
    ap.add_argument("--params", help="JSON с параметрами (по умолчанию build/model-params.json)")
    ap.add_argument("--months", type=int, help="горизонт в месяцах (иначе из run-config или 12)")
    a = ap.parse_args(argv)
    out_dir = Path(a.out).resolve()
    ppath = Path(a.params) if a.params else out_dir / "build" / "model-params.json"
    if ppath.exists():
        params = deep_merge(DEFAULT_PARAMS, json.loads(ppath.read_text(encoding="utf-8")))
    else:
        params = copy.deepcopy(DEFAULT_PARAMS)
        if not a.params:
            ppath.parent.mkdir(parents=True, exist_ok=True)
            ppath.write_text(json.dumps(DEFAULT_PARAMS, ensure_ascii=False, indent=2), encoding="utf-8")
            print("Создан %s с допущениями по умолчанию — отредактируйте и перезапустите." % ppath)
        else:
            print("нет файла параметров %s" % ppath, file=sys.stderr)
            return 1
    cfg_path = out_dir / "build" / "run-config.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8")) if cfg_path.exists() else {}
    months = a.months or int((cfg.get("strategy") or {}).get("horizon_months") or 12)
    months = max(1, months)
    model = build(params, months)
    (out_dir / "data").mkdir(parents=True, exist_ok=True)
    (out_dir / "data" / "model.json").write_text(json.dumps(model, ensure_ascii=False, indent=2), encoding="utf-8")
    cur = model["currency"]
    print("Модель: %s, горизонт %d мес., валюта %s" % (model["revenue_model"], months, cur))
    for name, sc in model["scenarios"].items():
        print("  %-11s CAC %s, LTV %s, окупаемость %s мес., безубыточность мес. %s, ROI %s, выручка %s"
              % (name, sc["cac"], sc["ltv"], sc["payback_months"], sc["breakeven_month"], sc["roi"], sc["totals"]["net_revenue"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
