"""Профили model.py (one_time_purchase, mobile-app, oss), отдельный платный канал, режим sensitivity-only (pytest, без сети).

Запуск: python3 -m pytest skills/product-strategy/tests/test_model_profiles.py -q
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import model  # noqa: E402


def run(script, *args):
    e = {k: v for k, v in os.environ.items() if not k.startswith("TYPESAFE_")}
    return subprocess.run([sys.executable, "-B", str(SCRIPTS / script)] + [str(a) for a in args], capture_output=True, text=True, env=e, timeout=300)


def jload(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def make_out(tmp_path, cfg):
    out = tmp_path / "out"
    (out / "data").mkdir(parents=True)
    (out / "build").mkdir()
    (out / "build" / "run-config.json").write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    return out


def run_model(out):
    r = run("model.py", out)
    assert r.returncode == 0, r.stdout + r.stderr
    return jload(out / "data" / "model.json"), jload(out / "build" / "model-params.json")


@pytest.mark.parametrize("cfg,expected", [
    ({}, "saas"),
    ({"strategy": {"monetization": "freemium"}, "product": {"type": "saas"}}, "saas"),
    ({"strategy": {"monetization": "one_time"}}, "one_time_purchase"),
    ({"product": {"type": "mobile"}, "strategy": {"monetization": "freemium"}}, "mobile-app"),
    ({"product": {"type": "mobile"}, "strategy": {"monetization": "one_time"}}, "mobile-app"),
    ({"strategy": {"monetization": "donations"}}, "oss"),
    ({"project": {"goal": "oss"}}, "oss"),
    ({"project": {"goal": "oss"}, "strategy": {"monetization": "freemium"}}, "saas"),
    ({"strategy": {"model_profile": "one_time_purchase", "monetization": "donations"}}, "one_time_purchase"),
])
def test_select_profile(cfg, expected):
    assert model.select_profile(cfg)[0] == expected


def test_one_time_purchase_without_manual_edits(tmp_path):
    out = make_out(tmp_path, {"strategy": {"monetization": "one_time", "horizon_months": 12}})
    M, P = run_model(out)
    assert P["model_profile"]["value"] == "one_time_purchase" and P["revenue_model"]["value"] == "one_time"
    assert M["model_profile"] == "one_time_purchase" and M["revenue_model"] == "one_time"
    g = {k: v["value"] for k, v in P["common"].items()}
    b = M["scenarios"]["base"]
    exp_ltv = g["price_one_time"] * (1 - g["payment_fee"]) * (1 - g["refund_rate"]) * g["gross_margin"] * (1 + g["repeat_purchase_rate"])
    assert b["ltv"] == round(exp_ltv, 2) and b["churn"] is None
    assert all(m["paying"] == round(m["new_paying"], 1) for m in b["monthly"])          # разовая: платящие месяца = новые
    assert [f["label"] for f in b["funnel"]][3] == "Новые покупатели"


def test_mobile_app_profile_installs_store_fee_refunds(tmp_path):
    out = make_out(tmp_path, {"product": {"type": "mobile"}, "strategy": {"horizon_months": 12}, "project": {"currency": "USD"}})
    M, P = run_model(out)
    base = P["scenarios"]["base"]
    assert "installs_month" in base and "visitors_month" not in base and "cost_per_install" in base and "install_to_signup" in base
    assert P["common"]["store_fee"]["value"] == 0.15 and P["common"]["refund_rate"]["value"] > 0
    b = M["scenarios"]["base"]
    assert M["model_profile"] == "mobile-app" and b["funnel"][0]["label"] == "Установки"
    assert b["monthly"][0]["visitors"] == base["installs_month"]["value"] and b["totals"]["installs"] == b["totals"]["visitors"]
    g = {k: v["value"] for k, v in P["common"].items()}
    per = g["price_month"] * (1 - g["payment_fee"]) * (1 - g["store_fee"]) * (1 - g["refund_rate"]) * g["gross_margin"]
    life = min(1 / base["churn_monthly"]["value"], g["ltv_cap_months"])
    assert b["ltv"] == round(per * life, 2)
    # маркетинг считается по установкам: CPI × доля × установки первого месяца
    m1 = b["monthly"][0]
    assert m1["marketing"] == round(base["installs_month"]["value"] * base["paid_share"]["value"] * base["cost_per_install"]["value"], 2)
    assert any("mobile-app" in n for n in M["notes"])
    c = run("charts.py", out, "--only", "funnel,cac-ltv,payback,forecast-fan")
    assert c.returncode == 0, c.stdout + c.stderr


def test_mobile_price_and_fee_from_store_stats_and_config(tmp_path):
    out = make_out(tmp_path, {"product": {"type": "mobile"}, "strategy": {"monetization": "one_time"}, "project": {"currency": "RUB"}})
    (out / "data" / "store-stats.json").write_text(json.dumps({"stores": [{"store": "RuStore", "price": 299, "commission": 15,
                                                                         "installs_month": 2000}]}), encoding="utf-8")
    M, P = run_model(out)
    assert P["revenue_model"]["value"] == "one_time"
    assert P["common"]["price_one_time"] == {"value": 299.0, "label": "факт", "note": "data/store-stats.json"}
    assert P["common"]["store_fee"]["value"] == 0.15 and P["common"]["store_fee"]["label"] == "факт"
    assert P["scenarios"]["base"]["installs_month"]["value"] == 2000 and P["scenarios"]["base"]["installs_month"]["label"] == "факт"
    assert M["audience_data"] is True and M["mode"] == "forecast"
    out2 = make_out(tmp_path / "b", {"product": {"type": "mobile"}, "project": {"store_fee": 30, "price_hint": 5}})
    _, P2 = run_model(out2)
    assert P2["common"]["store_fee"]["value"] == 0.3 and P2["common"]["price_month"]["value"] == 5.0


def test_oss_donations_time_costs_no_cac(tmp_path):
    out = make_out(tmp_path, {"strategy": {"monetization": "donations", "horizon_months": 12}, "project": {"goal": "oss", "team_size": 2}})
    M, P = run_model(out)
    assert P["revenue_model"]["value"] == "donations" and "donation_month" in P["common"] and "price_month" not in P["common"]
    assert "active_to_donor" in P["scenarios"]["base"] and "active_to_paying" not in P["scenarios"]["base"]
    assert M["model_profile"] == "oss" and M["solo"]["profile"] == "oss" and M["solo"]["params"]["team_size"]["value"] == 2
    for sc in M["scenarios"].values():
        assert sc["cac"] is None and sc["cac_paid"] is None and sc["paid"]["mode"] == "none"
        assert isinstance(sc["roi"], str) and "OSS" in sc["roi"]
        assert sc["assumptions"]["paid_share"]["value"] == 0.0
    assert M["scenarios"]["base"]["funnel"][3]["label"] == "Новые доноры"
    # спонсоры добавляют фиксированную выручку каждый месяц
    rev0 = M["scenarios"]["base"]["totals"]["net_revenue"]
    P["common"]["sponsors_month"]["value"] = 100.0
    (out / "build" / "model-params.json").write_text(json.dumps(P, ensure_ascii=False), encoding="utf-8")
    M2, _ = run_model(out)
    fee = P["common"]["payment_fee"]["value"]
    assert abs(M2["scenarios"]["base"]["totals"]["net_revenue"] - rev0 - 12 * 100 * (1 - fee)) < 0.05
    c = run("charts.py", out, "--only", "cac-ltv,payback")
    assert c.returncode == 0, c.stdout + c.stderr


def test_paid_channel_separate_from_blended(tmp_path):
    out = make_out(tmp_path, {"strategy": {"horizon_months": 12}})
    M, P = run_model(out)
    b = M["scenarios"]["base"]
    assert b["paid"]["mode"] == "share" and b["cac_paid"] > b["cac"] > 0               # смешанный CAC скрывает платный
    assert b["paid"]["cac_blended"] == b["cac"] and b["paid"]["new_paying"] < b["totals"]["new_paying"]
    assert abs(b["cac_paid"] - b["paid"]["marketing"] / b["paid"]["new_paying"]) < 0.05
    assert M["scenarios"]["pessimistic"]["cac_paid"] is None                            # платного канала нет
    # отдельный бюджет: платные регистрации поверх органики, конверсия платных ниже
    P["scenarios"]["base"]["paid_budget_month"] = {"value": 500.0, "label": "оценка", "note": "тест"}
    P["scenarios"]["base"]["paid_conversion_factor"] = {"value": 0.5, "label": "допущение", "note": "тест"}
    (out / "build" / "model-params.json").write_text(json.dumps(P, ensure_ascii=False), encoding="utf-8")
    M2, _ = run_model(out)
    b2 = M2["scenarios"]["base"]
    assert b2["paid"]["mode"] == "budget" and b2["totals"]["marketing"] == 500.0 * 12
    assert b2["paid"]["signups"] == round(500.0 / P["scenarios"]["base"]["cost_per_paid_signup"]["value"] * 12, 1)
    assert b2["totals"]["signups"] > b["totals"]["signups"] - b["paid"]["signups"]
    assert b2["cac_paid"] > b2["cac"]


def test_sensitivity_only_without_audience_data(tmp_path):
    out = make_out(tmp_path, {"strategy": {"horizon_months": 12}})
    M, _ = run_model(out)
    assert M["mode"] == "sensitivity-only" and M["forecast"] is False and M["audience_data"] is False
    items = M["sensitivity"]["items"]
    assert items and [i["swing_net_revenue"] for i in items] == sorted((i["swing_net_revenue"] for i in items), reverse=True)
    assert {"visitors_month", "churn_monthly", "price_month"} <= {i["param"] for i in items}
    ch = next(i for i in items if i["param"] == "churn_monthly")
    assert ch["high"]["net_revenue"] < M["sensitivity"]["base"]["net_revenue"] < ch["low"]["net_revenue"]
    assert any("sensitivity-only" in n for n in M["notes"])
    out2 = make_out(tmp_path / "f", {"project": {"traffic_hint": 4000}})
    M2, _ = run_model(out2)
    assert M2["mode"] == "forecast" and M2["audience_data"] is True
    out3 = make_out(tmp_path / "x", {"project": {"traffic_hint": 4000}, "strategy": {"model_mode": "sensitivity-only"}})
    assert run_model(out3)[0]["mode"] == "sensitivity-only"


def test_legacy_params_without_profile_stay_saas(tmp_path):
    out = make_out(tmp_path, {"strategy": {"horizon_months": 6}})
    _, P = run_model(out)
    P.pop("model_profile")
    (out / "build" / "run-config.json").write_text(json.dumps({"product": {"type": "mobile"}}), encoding="utf-8")
    (out / "build" / "model-params.json").write_text(json.dumps(P, ensure_ascii=False), encoding="utf-8")
    r = run("model.py", out)
    assert r.returncode == 0 and "нет model_profile" in r.stdout and "mobile-app" in r.stdout
    M = jload(out / "data" / "model.json")
    assert M["model_profile"] == "saas" and "installs" not in M["scenarios"]["base"]["totals"]


def test_saas_numbers_unchanged_and_new_keys(tmp_path):
    out = make_out(tmp_path, {"strategy": {"horizon_months": 12}})
    M, P = run_model(out)
    assert P["common"] == model.DEFAULT_PARAMS["common"]
    b = M["scenarios"]["base"]
    assert b["cac"] == 50.0 and b["ltv"] == 158.27 and b["payback_months"] == 5.27       # как в 1.x (дефолты USD)
    assert set(b["monthly"][0]) == {"month", "visitors", "signups", "users", "paying", "new_paying", "revenue", "cost", "marketing",
                                    "cum_margin", "cum_cost"}                    # строка как в 1.x (страница — таблица фиксированной ширины)
    assert "cac_paid" in b and "paid" in b
