"""sample_size.py: выборка двух долей, срок набора, Пуассон, ложная тревога, experiments.json, измеримость критериев (pytest).

Запуск: python3 -m pytest skills/product-strategy/tests/test_sample_size.py -q
"""
import json
import os
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import sample_size as ss  # noqa: E402


def run(script, *args):
    e = {k: v for k, v in os.environ.items() if not k.startswith("TYPESAFE_")}
    return subprocess.run([sys.executable, "-B", str(SCRIPTS / script)] + [str(a) for a in args], capture_output=True, text=True, env=e, timeout=300)


def jload(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def jdump(p, obj):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    Path(p).write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def test_two_proportions_reference_values():
    assert ss.n_two_proportions(0.05, 0.06) == 8158                    # классический пример: 5 % → 6 %, α 0,05, мощность 0,8
    assert ss.n_two_proportions(0.05, 0.06, two_sided=False) < 8158
    assert ss.n_two_proportions(0.05, 0.06, power=0.9) > 8158
    assert ss.n_two_proportions(0.10, 0.12) < ss.n_two_proportions(0.10, 0.11)
    with pytest.raises(ValueError):
        ss.n_two_proportions(0.05, 0.05)
    with pytest.raises(ValueError):
        ss.n_two_proportions(0.0, 0.1)


def test_calc_relative_traffic_and_rate():
    r = ss.calc(0.05, 0.2, relative=True, traffic_per_week=1000)
    assert r["target"] == 0.06 and r["n_per_arm"] == 8158 and r["n_total"] == 16316 and r["weeks"] == 17
    r = ss.calc(0.05, 0.01, traffic_per_week=1000, share=0.5)
    assert r["weeks"] == 33
    t = ss.weeks_rate(4, 3)                                            # −25 % покупок при 4 в неделю ≈ год наблюдений
    assert 50 < t < 60
    rr = ss.calc(4, -0.25, relative=True, kind="rate")
    assert rr["weeks"] == 55 and rr["target"] == 3.0


def test_false_alarm_simulation_grows_with_peeking():
    one = ss.simulate_false_alarm(0.1, 2000, sims=1500, peeks=1, seed=3)["rate"]
    many = ss.simulate_false_alarm(0.1, 2000, sims=1500, peeks=8, seed=3)["rate"]
    assert 0.025 < one < 0.075 and many > one + 0.03


def test_cli_calculator():
    r = run("sample_size.py", "--baseline", "0.05", "--mde", "0.01", "--alpha", "0.05", "--power", "0.8", "--traffic", "200")
    assert r.returncode == 0 and "n = 8158" in r.stdout and "82 нед." in r.stdout, r.stdout + r.stderr
    j = json.loads(run("sample_size.py", "--baseline", "0.05", "--mde", "0.01", "--simulate", "500", "--peeks", "3", "--json").stdout)
    assert j["n_per_arm"] == 8158 and 0 <= j["false_alarm"]["rate"] <= 1 and j["false_alarm"]["peeks"] == 3
    assert run("sample_size.py", "--baseline", "0.05", "--mde", "0").returncode == 1
    assert run("sample_size.py", "--baseline", "0.05", "--mde", "0.01", "--alpha", "1.5").returncode == 1
    assert run("sample_size.py", "/nonexistent/dir/xyz", "--recalc").returncode == 2


@pytest.fixture
def demo(tmp_path):
    out = tmp_path / "demo"
    for cmd in (("make_demo.py", out), ("score.py", out), ("model.py", out)):
        r = run(*cmd)
        assert r.returncode == 0, r.stdout + r.stderr
    return out


def test_add_recalc_experiments_json(demo):
    r = run("sample_size.py", demo, "--add", "E01", "--baseline", "0.3", "--mde", "0.05", "--title", "Мастер", "--proposal", "P001",
            "--population", "signups")
    assert r.returncode == 0, r.stdout + r.stderr
    e = jload(demo / "data" / "experiments.json")
    row = e["experiments"][0]
    assert row["id"] == "E01" and row["n_per_arm"] == ss.n_two_proportions(0.3, 0.35) and row["title"] == "Мастер"
    assert "data/model.json" in row["traffic_source"] and row["weeks"] > 0 and row["status"] in ("observable", "unobservable")
    w0 = row["weeks"]
    assert run("sample_size.py", demo, "--add", "E02", "--baseline", "0.05", "--mde", "0.01", "--traffic", "100", "--per", "day").returncode == 0
    e = jload(demo / "data" / "experiments.json")
    e2 = next(x for x in e["experiments"] if x["id"] == "E02")
    assert e2["traffic_per_week"] == 700 and e2["weeks"] == 24
    # модель: трафик ×4 → --recalc сокращает срок E01, а E02 (явный трафик) не трогает
    p = jload(demo / "build" / "model-params.json")
    p["scenarios"]["base"]["visitors_month"]["value"] *= 4
    jdump(demo / "build" / "model-params.json", p)
    assert run("model.py", demo).returncode == 0
    assert run("sample_size.py", demo, "--recalc").returncode == 0
    e = jload(demo / "data" / "experiments.json")
    assert next(x for x in e["experiments"] if x["id"] == "E01")["weeks"] < w0
    assert next(x for x in e["experiments"] if x["id"] == "E02")["weeks"] == 24
    assert run("sample_size.py", demo).returncode == 0


def test_criteria_measurability(demo):
    soon = (date.today() + timedelta(weeks=8)).isoformat()
    later = (date.today() + timedelta(weeks=40)).isoformat()
    jdump(demo / "data" / "decisions.json", {"version": 1, "north_star": {"metric": "активные"}, "bets": [
        {"id": 1, "name": "Покупки", "kill": {"metric": "покупок в неделю", "baseline": 4, "threshold": 3, "date": soon, "kind": "rate"}},
        {"id": 2, "name": "Активация", "kill": {"metric": "активация", "baseline": 0.30, "threshold": 0.33, "date": later,
                                                "population": "signups"}},
        {"id": 3, "name": "Без данных", "kill": {"metric": "NPS", "threshold": 40, "date": later, "kind": "other"}}]})
    r = run("sample_size.py", demo, "--criteria")
    assert r.returncode == 0, r.stdout + r.stderr
    crit = {c["id"]: c for c in jload(demo / "data" / "experiments.json")["criteria"]}
    assert crit["K1"]["status"] == "unobservable" and crit["K1"]["weeks"] >= 40 and "нед." in crit["K1"]["reason"]
    assert crit["K2"]["status"] == "observable" and crit["K2"]["n"] == ss.n_one_proportion(0.33, 0.30)
    assert crit["K2"]["traffic_per_week"] > 0 and crit["K3"]["status"] == "unknown"
    assert run("sample_size.py", demo, "--criteria", "--strict").returncode == 1
    # нет трафика: модель без воронки и без traffic_hint → ненаблюдаем
    rows = ss.evaluate_criteria(demo, jload(demo / "data" / "decisions.json"), model={}, cfg={}, exps={})
    assert {r["id"]: r["status"] for r in rows}["K2"] == "unobservable"
