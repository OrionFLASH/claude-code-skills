# -*- coding: utf-8 -*-
"""WP-D 1.5.0: диспетчер — политика effort (FB-003), общий OUT без isolation и волны 5+1 (FB-013), учёт агентов и раздел 11 по
волнам (FB-014, SM 6.3), прогноз режима идеи и «быстрая концепция» (SM 10.7), общие пути заданий (SM 6.3). Без сети.
Запуск: python3 -m pytest tests/test_process_dispatch.py -q -p no:cacheprovider
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import dispatch  # noqa: E402


def run(*args):
    e = {k: v for k, v in os.environ.items() if not k.startswith("TYPESAFE_")}
    return subprocess.run([sys.executable, "-B", str(SCRIPTS / "dispatch.py")] + [str(a) for a in args], capture_output=True, text=True,
                          env=e, timeout=120)


def write(p, obj):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    Path(p).write_text(obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False), encoding="utf-8")


def state(out):
    return json.loads((out / "build" / "agents.json").read_text(encoding="utf-8"))


@pytest.fixture()
def out(tmp_path):
    o = tmp_path / "o"
    write(o / "build" / "run-config.json", {"mode": "concept", "strategy": {"depth": "standard"}, "tools": {"max_parallel_agents": 5}})
    return o


def tasks6():
    return [{"id": "T%d" % i, "wave": "C4", "phase": "C4", "kind": "research", "effort": "high", "paths": ["data/x-%d.json" % i]} for i in range(1, 7)]


# ---------------------------------------------------------------- FB-013: волны 5+1, без isolation, shared_out
def test_six_c4_tasks_go_as_5_plus_1_without_isolation(out):
    write(out / "build" / "t.json", tasks6())
    assert run(out, "load", out / "build" / "t.json").returncode == 0
    rep = json.loads(run(out, "ready", "--start", "--json").stdout)
    assert len(rep["ready"]) == 5 and all(it["isolation"] is None for it in rep["ready"]) and "не ставить" in rep["isolation"]
    for t in rep["ready"]:
        run(out, "done", t["id"], "--tokens", "100000", "--model-actual", "sonnet")
    rep2 = json.loads(run(out, "ready", "--start", "--json").stdout)
    assert [t["id"] for t in rep2["ready"]] == ["T6"]
    txt = run(out, "ready").stdout
    assert "isolation" not in txt or "не ставить" in txt
    # triage-файл несёт shared_out; isolation из ответа снимается
    write(out / "build" / "t2.json", [{"id": "X1", "wave": "C5", "kind": "details", "paths": ["data/proposals-draft-G1.json"]}])
    run(out, "load", out / "build" / "t2.json")
    run(out, "triage", "C5")
    assert json.loads((out / "build" / "triage-C5.json").read_text(encoding="utf-8"))[0]["shared_out"] is True
    write(out / "build" / "r.json", {"tasks": [{"id": "X1", "model": "opus", "effort": "high", "isolation": "worktree"}]})
    run(out, "triage", "C5", "--apply", out / "build" / "r.json")
    x1 = next(t for t in state(out)["tasks"] if t["id"] == "X1")
    assert x1["model"] == "opus" and "isolation снят" in x1["note"]


# ---------------------------------------------------------------- FB-003: effort только при effort_policy = explicit
@pytest.mark.parametrize("policy,expected", [(None, "high"), ({"model_policy": "triage", "effort_policy": "explicit"}, "high"),
                                             ({"model_policy": "default", "effort_policy": "none"}, None)])
def test_effort_policy(out, policy, expected):
    cfg = json.loads((out / "build" / "run-config.json").read_text(encoding="utf-8"))
    if policy:
        cfg["tools"]["agents"] = policy
    write(out / "build" / "run-config.json", cfg)
    write(out / "build" / "t.json", tasks6()[:1])
    run(out, "load", out / "build" / "t.json")
    rep = json.loads(run(out, "ready", "--json").stdout)
    assert rep["ready"][0]["effort"] == expected
    if policy and policy["model_policy"] == "triage":
        assert rep["untriaged"] == ["T1"]                                                    # напоминание про триаж
    txt = run(out, "ready").stdout
    assert ('effort="high"' in txt) == (expected == "high")


# ---------------------------------------------------------------- FB-014 / SM: учёт по волнам, раздел 11 без ручного ввода
def test_report_write_has_waves_models_tokens_and_forecast(out):
    write(out / "build" / "t.json", tasks6()[:2] + [{"id": "S1", "wave": "C7", "phase": "C7", "kind": "section", "paths": ["build/parts/strategy-02.md"]}])
    run(out, "load", out / "build" / "t.json")
    run(out, "ready", "--start")
    run(out, "done", "T1", "--tokens", "230000", "--minutes", "20", "--model-actual", "sonnet")
    run(out, "done", "T2", "--tokens", "120000", "--minutes", "15", "--model-actual", "opus")
    r = run(out, "report", "--write")
    assert r.returncode == 0
    md = (out / "build" / "agents-report.md").read_text(encoding="utf-8")
    assert md.startswith("## 11. Использованные инструменты и токены")
    assert "| Волна | Агентов | Токены | Минут агентов | Модели (факт) |" in md
    assert "| C4 | 2 | 0.35 млн | 35 | opus × 1, sonnet × 1 |" in md
    assert "Прогноз до старта: агентов" in md and "факт: агентов 3" in md


# ---------------------------------------------------------------- SM 10.7: прогноз режима идеи и быстрая концепция
def test_concept_forecast_and_fast_mode():
    cfg = {"mode": "concept", "idea": {"facets": {"platform_dependency": True, "sensitive": ["money"]}}, "phases": {"prototype": True}}
    fc = dispatch.forecast("standard", 5, cfg)
    phases = [r["phase"] for r in fc["phases"]]
    assert phases[0] == "C4" and "C8.5" in phases and fc["mode"] == "concept"
    c4 = next(r for r in fc["phases"] if r["phase"] == "C4")
    assert "техническая интеграция с платформой" in c4["kinds"] and "правовой обзор" in c4["kinds"]
    fast = dispatch.forecast("standard", 5, cfg, fast=True)
    assert 8 <= fast["agents"] <= 11 and fast["skipped"] and fast["hours"] <= 3.6
    plain = dispatch.forecast("standard", 5, {"mode": "concept"}, fast=True)
    assert plain["agents"] == 8                                                              # без права и интеграции
    one_pass = dispatch.forecast("standard", 5, {"mode": "concept", "registry": {"passes": 1}})
    c5 = next(r for r in one_pass["phases"] if r["phase"] == "C5")
    assert "реестр, проход 1" not in c5["kinds"]


def test_fast_plan_write_and_load(out):
    cfg = json.loads((out / "build" / "run-config.json").read_text(encoding="utf-8"))
    cfg["idea"] = {"facets": {"platform_dependency": True}}
    write(out / "build" / "run-config.json", cfg)
    r = run(out, "fast-plan", "--write")
    assert r.returncode == 0 and "Опускается:" in r.stdout
    tasks = json.loads((out / "build" / "tasks-fast.json").read_text(encoding="utf-8"))["tasks"]
    ids = [t["id"] for t in tasks]
    assert "I1" in ids and "L1" not in ids and len(tasks) == 9
    assert run(out, "load", out / "build" / "tasks-fast.json").returncode == 0
    r = run(out, "forecast", "--fast")
    assert "Быстрая концепция опускает" in r.stdout


# ---------------------------------------------------------------- SM 6.3: общие пути заданий одной волны
def test_shared_paths_warn_and_owners(out):
    write(out / "build" / "t.json", [{"id": "P1", "wave": "C8.5", "kind": "prototype", "paths": ["prototype/tests/smoke.cjs", "prototype/shots/*.png"]},
                                     {"id": "P2", "wave": "C8.5", "kind": "prototype", "paths": ["prototype/shots/terminal-1.png"]}])
    r = run(out, "load", out / "build" / "t.json")
    assert "общий путь" in r.stderr and "P1 и P2" in r.stderr
    r = run(out, "owners", "--json")
    sh = json.loads(r.stdout)
    assert r.returncode == 1 and sh and sh[0]["tasks"] == ["P1", "P2"]
    rep = json.loads(run(out, "ready", "--start", "--json").stdout)
    assert [t["id"] for t in rep["ready"]] == ["P1"]                                         # одновременно не запускаются
