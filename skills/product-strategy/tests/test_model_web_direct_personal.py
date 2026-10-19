"""model.py 1.5: профили web-direct (FB-026) и personal (SM разд. 4), налог и комиссия из пакета локали, ёмкость из capacity.py
(FB-028), блок illustration в режиме sensitivity-only (FB-027), начало выручки по плану и сверка модель ↔ план (SM 6.1).

Запуск: python3 -m pytest skills/product-strategy/tests/test_model_web_direct_personal.py -q
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import capacity  # noqa: E402
import model  # noqa: E402


def run(script, *args):
    e = {k: v for k, v in os.environ.items() if not k.startswith("TYPESAFE_")}
    return subprocess.run([sys.executable, "-B", str(SCRIPTS / script)] + [str(a) for a in args], capture_output=True, text=True, env=e, timeout=300)


def jload(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def make_out(tmp_path, cfg, name="out"):
    out = tmp_path / name
    (out / "data").mkdir(parents=True)
    (out / "build").mkdir()
    (out / "build" / "run-config.json").write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    return out


def run_model(out):
    r = run("model.py", out)
    assert r.returncode == 0, r.stdout + r.stderr
    return jload(out / "data" / "model.json"), jload(out / "build" / "model-params.json"), r.stdout


@pytest.mark.parametrize("cfg,expected", [
    ({"strategy": {"payment_channel": "direct"}}, "web-direct"),
    ({"strategy": {"payment_channel": "store"}}, "mobile-app"),
    ({"product": {"type": "mobile", "forms": ["web", "mobile"]}}, "web-direct"),
    ({"product": {"type": "mobile", "forms": ["mobile"]}}, "mobile-app"),
    ({"project": {"audience": "personal"}}, "personal"),
    ({"project": {"audience": "circle"}, "strategy": {"monetization": "freemium"}}, "personal"),
    ({"project": {"audience": "public"}, "strategy": {"payment_channel": "direct"}}, "web-direct"),
    ({"strategy": {"model_profile": "web-direct", "monetization": "donations"}}, "web-direct"),
])
def test_select_profile_15(cfg, expected):
    assert model.select_profile(cfg)[0] == expected


def test_web_direct_from_locale_without_manual_edits(tmp_path):
    """FB-026: эталон ARC — веб/PWA с ЮKassa: model-params без ручных правок, payment_fee и НПД — из пакета локали ru."""
    cfg = {"mode": "concept", "product": {"type": "mobile", "forms": ["web", "mobile"]},
           "strategy": {"horizon_months": 6, "markets": ["ru", "en"], "profile": "zero-budget-solo"},
           "project": {"currency": "RUB", "team_size": 1}, "idea": {"facets": {"hours_week": 15}}}
    M, P, out = run_model(make_out(tmp_path, cfg))
    assert P["model_profile"]["value"] == "web-direct" and M["model_profile"] == "web-direct"
    g = P["common"]
    assert g["payment_fee"]["value"] == 0.035 and "пакет локали ru" in g["payment_fee"]["note"] and g["payment_fee"]["label"] == "допущение"
    assert g["tax_rate"]["value"] == 0.04 and "НПД" in g["tax_rate"]["note"]
    assert g["store_fee"]["value"] == 0.0
    base = P["scenarios"]["base"]
    assert "visitors_month" in base and "installs_month" not in base and "cost_per_install" not in base
    b = M["scenarios"]["base"]
    assert b["funnel"][0]["label"] == "Посетители"
    gv = {k: v["value"] for k, v in g.items() if isinstance(v.get("value"), (int, float))}
    per = gv["price_month"] * (1 - gv["payment_fee"]) * (1 - gv["refund_rate"]) * (1 - gv["tax_rate"]) * gv["gross_margin"]
    life = min(1 / base["churn_monthly"]["value"], gv["ltv_cap_months"])
    assert b["ltv"] == round(per * life, 2)                                        # налог учтён в чистой цене
    assert any("web-direct" in n for n in M["notes"]) and "web-direct" in out


def test_web_direct_english_market_and_tax_regime(tmp_path):
    M, P, _ = run_model(make_out(tmp_path, {"strategy": {"payment_channel": "direct", "markets": ["en"]}, "project": {"currency": "USD"}}))
    assert P["common"]["payment_fee"]["value"] == 0.03 and P["common"]["tax_rate"]["value"] == 0.0
    # явный налоговый режим действует и на прежние профили; без него saas не меняется
    _, P2, _ = run_model(make_out(tmp_path, {"strategy": {"markets": ["ru"]}, "project": {"currency": "RUB", "tax_regime": "usn6"}}, "u"))
    assert P2["model_profile"]["value"] == "saas" and P2["common"]["tax_rate"]["value"] == 0.06
    _, P3, _ = run_model(make_out(tmp_path, {"strategy": {"markets": ["ru"]}, "project": {"currency": "RUB"}}, "s"))
    assert "tax_rate" not in P3["common"]


def test_personal_profile_cost_of_ownership(tmp_path):
    """SM разд. 4: «только для меня» — нет воронки, CAC, LTV; стоимость владения и окупаемость личных усилий."""
    cfg = {"project": {"audience": "personal", "currency": "RUB"}, "strategy": {"horizon_months": 12},
           "idea": {"facets": {"hours_week": 8}}}
    out = make_out(tmp_path, cfg)
    M, P, stdout = run_model(out)
    assert M["model_profile"] == "personal" and M["revenue_model"] == "none"
    assert set(P["scenarios"]["base"]) >= {"hours_saved_per_week", "support_hours_month", "money_saved_month"}
    assert P["scenario_labels"] == {"pessimistic": "минимальный", "base": "обычный", "optimistic": "с поддержкой"}
    b = M["scenarios"]["base"]
    assert b["label"] == "обычный" and b["cac"] is None and b["ltv"] is None and "funnel" not in b and "monthly" not in b
    pb = M["personal"]["scenarios"]["base"]
    cap = capacity.capacity(cfg, 12)
    start = P["common"]["use_start_month"]["value"]
    # до начала использования — вся ёмкость в часы, после — поддержка
    assert pb["monthly"][0]["hours_spent"] == cap["hours_month"] and pb["monthly"][start - 1]["hours_spent"] == P["scenarios"]["base"]["support_hours_month"]["value"]
    assert b["value"] == pb["totals"]["value"] and b["net_value"] == round(b["value"] - b["cost"], 2)
    # порог окупаемости: при найденных часах экономии чистая ценность ≈ 0
    need = b["hours_saved_per_week_to_break_even"]
    sc = json.loads(json.dumps(P["scenarios"]["base"]))
    sc["hours_saved_per_week"]["value"] = need
    net = model.personal_simulate(P["common"], sc, 12, cap["hours_month"])["totals"]["net_value"]
    assert abs(net) < 0.01 * max(1.0, b["cost"])
    assert M["capacity"]["dev_days_total"] == cap["dev_days"] and M["sensitivity"]["items"]
    assert "обычный" in stdout
    keys = json.loads(run("charts.py", out, "--list-keys").stdout)
    assert "funnel" in keys["skipped"] and "cac-ltv" in keys["skipped"]           # воронки и LTV для личного инструмента нет
    out2 = make_out(tmp_path, dict(cfg, project={"audience": "personal_then_public", "currency": "RUB"}), "o2")
    M2, _, _ = run_model(out2)
    assert any("выпустить наружу" in n for n in M2["notes"])


def test_capacity_from_capacity_py_and_legacy_solo(tmp_path):
    """FB-028: модель берёт ёмкость из capacity.py; прежние solo.days_per_month/hours_per_day не задают её."""
    cfg = {"strategy": {"horizon_months": 6, "profile": "zero-budget-solo"}, "project": {"currency": "RUB", "team_size": 1},
           "idea": {"facets": {"hours_week": 15}}}
    out = make_out(tmp_path, cfg)
    M, P, _ = run_model(out)
    c = capacity.capacity(cfg, 6)
    assert M["capacity"]["dev_days_total"] == c["dev_days"] == 34.1 and M["capacity"]["line"] == c["line"] and M["capacity"]["day_hours"] == 8
    assert "days_per_month" not in P["solo"] and "hours_per_day" not in P["solo"]
    P["solo"]["days_per_month"] = {"value": 12, "label": "допущение", "note": "1.4"}
    P["solo"]["hours_per_day"] = {"value": 6, "label": "допущение", "note": "1.4"}
    (out / "build" / "model-params.json").write_text(json.dumps(P, ensure_ascii=False), encoding="utf-8")
    M2, _, _ = run_model(out)
    assert M2["capacity"]["dev_days_total"] == c["dev_days"] and any("больше не задают ёмкость" in n for n in M2["notes"])
    # standard-профиль тоже получает блок capacity (одни числа для модели, плана и текста)
    M3, _, _ = run_model(make_out(tmp_path, {"strategy": {"horizon_months": 12}}, "std"))
    assert M3["capacity"]["dev_days_total"] == capacity.capacity({}, 12)["dev_days"]


def test_sensitivity_only_illustration_block(tmp_path):
    """FB-027: в sensitivity-only денежные итоги помечены illustrative и вынесены в блок illustration."""
    M, _, out = run_model(make_out(tmp_path, {"strategy": {"horizon_months": 12}}))
    assert M["mode"] == "sensitivity-only"
    assert all(sc.get("illustrative") is True for sc in M["scenarios"].values())
    ill = M["illustration"]
    assert ill["label"] == "[иллюстрация при допущениях]" and ill["scenarios"]["base"]["net_revenue"] == M["scenarios"]["base"]["totals"]["net_revenue"]
    assert "roi" in ill["scenarios"]["base"] and "иллюстрация" in out
    M2, _, _ = run_model(make_out(tmp_path, {"project": {"traffic_hint": 4000}}, "f"))
    assert M2["mode"] == "forecast" and "illustration" not in M2 and "illustrative" not in M2["scenarios"]["base"]


def test_revenue_start_from_plan_and_reconciliation(tmp_path):
    """SM 6.1: выручка не с месяца 1, если платная часть в плане позже; расхождение модели и плана — reconciliation."""
    out = make_out(tmp_path, {"strategy": {"horizon_months": 12}})
    plan = {"horizon_months": 12, "milestones": {"launch": {"month": 4, "date": "2027-01-01"}, "paid": {"month": 6, "date": "2027-03-01"}},
            "capacity": {"dev_days": capacity.capacity({}, 12)["dev_days"]}}
    (out / "data" / "plan-baseline.json").write_text(json.dumps(plan), encoding="utf-8")
    M, P, _ = run_model(out)
    assert P["common"]["revenue_start_month"]["value"] == 6 and P["common"]["revenue_start_month"]["label"] == "факт"
    mo = M["scenarios"]["base"]["monthly"]
    assert all(m["revenue"] == 0 and m["paying"] == 0 for m in mo[:5]) and mo[5]["revenue"] > 0
    assert M["reconciliation"]["ok"] is True
    P["common"]["revenue_start_month"]["value"] = 1
    (out / "build" / "model-params.json").write_text(json.dumps(P, ensure_ascii=False), encoding="utf-8")
    M2, _, stdout = run_model(out)
    items = M2["reconciliation"]["items"]
    assert any(i["what"] == "revenue_start" and i["plan"] == 6 for i in items) and "сверка с планом" in stdout


def test_activation_reconciled_with_registry(tmp_path):
    """SM 6.1: активация в модели (signup_to_active) против диапазона «активация» в effect_kpi реестра."""
    out = make_out(tmp_path, {"strategy": {"horizon_months": 12}})
    props = [{"id": "P001", "title": "Мастер", "effect_kpi": [{"kpi": "активация новых", "range": "40–60 %", "label": "оценка"}]},
             {"id": "P002", "title": "Подсказки", "effect_kpi": [{"kpi": "активация", "range": "+5..10 %", "label": "оценка"}]}]
    (out / "data" / "proposals.json").write_text(json.dumps(props, ensure_ascii=False), encoding="utf-8")
    M, P, _ = run_model(out)
    assert P["scenarios"]["base"]["signup_to_active"]["value"] == 0.4
    assert "reconciliation" not in M                                              # 0,4 внутри 40–60 %; прирост «+5..10» не сравнивается
    P["scenarios"]["base"]["signup_to_active"]["value"] = 0.05 * 0.4
    (out / "build" / "model-params.json").write_text(json.dumps(P, ensure_ascii=False), encoding="utf-8")
    M2, _, _ = run_model(out)
    it = M2["reconciliation"]["items"]
    assert len(it) == 1 and it[0]["what"] == "activation" and it[0]["proposal"] == "P001" and it[0]["registry"] == [0.4, 0.6]
