"""Диспетчер заданий субагентов dispatch.py (эпик E-ORCH): очередь, зависимости, параллелизм, agents.json, прогноз, триаж.

Агенты не запускаются: проверяется выдача «готовых к запуску», отметки о завершении, закрытие волны (check_paths),
отчёт раздела 11 и прогноз по таблице глубины. Без сети.
Запуск: python3 -m pytest skills/product-strategy/tests/test_dispatch.py -q
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
TEMPLATES = Path(__file__).resolve().parent.parent / "templates"
sys.path.insert(0, str(SCRIPTS))
import dispatch  # noqa: E402


def run(*args):
    e = {k: v for k, v in os.environ.items() if not k.startswith("TYPESAFE_")}
    return subprocess.run([sys.executable, "-B", str(SCRIPTS / "dispatch.py")] + [str(a) for a in args], capture_output=True, text=True,
                          env=e, timeout=180)


def write(p, text):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    Path(p).write_text(text, encoding="utf-8")


def state(out):
    return json.loads((out / "build" / "agents.json").read_text(encoding="utf-8"))


@pytest.fixture()
def out(tmp_path):
    o = tmp_path / "o"
    write(o / "build" / "run-config.json", json.dumps({"strategy": {"depth": "standard"}, "tools": {"max_parallel_agents": 2}}))
    for name in ("research-competitors", "research-communities", "research-keywords", "registry-generator"):
        write(o / "build" / "briefs" / ("%s.md" % name), (TEMPLATES / "briefs" / ("%s.md" % name)).read_text(encoding="utf-8"))
    return o


def test_queue_dependencies_and_slots(out):
    tasks = [{"id": "comp", "brief": "build/briefs/research-competitors.md", "wave": "4", "kind": "research", "search": 30},
             {"id": "comm", "brief": "build/briefs/research-communities.md", "wave": "4", "kind": "research", "search": 20},
             {"id": "kw", "brief": "build/briefs/research-keywords.md", "wave": "4", "kind": "research"},
             {"id": "G1", "brief": "build/briefs/registry-generator.md", "wave": "5a", "kind": "titles", "deps": ["comp", "comm", "kw"]}]
    write(out / "build" / "tasks.json", json.dumps(tasks))
    r = run(out, "load", out / "build" / "tasks.json")
    assert r.returncode == 0 and "добавлено заданий: 4" in r.stdout, r.stderr
    st = state(out)
    comp = next(t for t in st["tasks"] if t["id"] == "comp")
    assert comp["model"] == "sonnet" and "data/competitors.json" in comp["paths"] and comp["budget"]["search"] == 30   # пути — из «Выдачи»
    g1 = next(t for t in st["tasks"] if t["id"] == "G1")
    assert g1["paths"] == ["data/proposals-draft-*.json"] and g1["task"]
    # лимит 2 из run-config: выдаются два задания, G1 ждёт зависимостей
    r = run(out, "ready", "--start", "--json")
    rep = json.loads(r.stdout)
    assert [x["id"] for x in rep["ready"]] == ["comp", "comm"] and rep["free_slots"] == 2
    assert "Прочитай и выполни бриф" in rep["ready"][0]["prompt"] and "build/briefs/research-competitors.md" in rep["ready"][0]["prompt"]
    assert str(Path.home()) not in rep["ready"][0]["prompt"]
    assert (out / "build" / "waves" / "4.json").is_file()                      # снимок волны для check_paths
    assert json.loads(run(out, "ready", "--json").stdout)["ready"] == []        # слотов нет
    assert run(out, "done", "comp", "--tokens", "200000", "--minutes", "20", "--search", "25", "--model-actual", "sonnet-4").returncode == 0
    rep = json.loads(run(out, "ready", "--start", "--json").stdout)
    assert [x["id"] for x in rep["ready"]] == ["kw"]                           # освободился слот → следующее задание
    run(out, "done", "comm", "--tokens", "100000", "--minutes", "10", "--result", "rework")
    st = state(out)
    comm = next(t for t in st["tasks"] if t["id"] == "comm")
    assert comm["status"] == "pending" and len(comm["attempts"]) == 1           # доработка — снова в очереди
    run(out, "ready", "--start")
    run(out, "done", "comm", "--tokens", "50000", "--minutes", "5")
    r = run(out, "done", "kw", "--tokens", "150000", "--minutes", "15")
    assert "волна 4 завершена" in r.stdout and "close-wave 4" in r.stdout
    st = state(out)
    comm = next(t for t in st["tasks"] if t["id"] == "comm")
    assert comm["tokens"] == 150000 and comm["minutes"] == 15.0 and comm["status"] == "done"
    rep = json.loads(run(out, "ready", "--json").stdout)
    assert [x["id"] for x in rep["ready"]] == ["G1"]


def test_failed_dependency_blocks_and_overlapping_paths(out):
    assert run(out, "add", "--id", "A", "--wave", "1", "--paths", "data/a.json", "--model", "opus").returncode == 0
    assert run(out, "add", "--id", "B", "--wave", "1", "--paths", "data/a.json").returncode == 0
    assert run(out, "add", "--id", "C", "--wave", "2", "--deps", "A", "--kind", "plan").returncode == 0
    rep = json.loads(run(out, "ready", "--start", "--json").stdout)
    assert [x["id"] for x in rep["ready"]] == ["A"] and rep["ready"][0]["model"] == "opus"
    assert any(b["id"] == "B" and "пересекаются" in b["why"] for b in json.loads(run(out, "ready", "--json").stdout)["blocked"])
    run(out, "done", "A", "--result", "failed")
    rep = json.loads(run(out, "ready", "--json").stdout)
    assert [x["id"] for x in rep["ready"]] == ["B"] and any(b["id"] == "C" and "A" in b["why"] for b in rep["blocked"])
    assert run(out, "add", "--id", "A").returncode == 2                          # дубль id
    assert run(out, "add", "--id", "Z", "--kind", "nope").returncode == 2        # неизвестный kind (argparse)


def test_close_wave_runs_check_paths(out):
    run(out, "add", "--id", "comp", "--brief", "build/briefs/research-competitors.md", "--wave", "4", "--kind", "research")
    run(out, "ready", "--start")
    write(out / "data" / "competitors.json", "[]")
    write(out / "data" / "sources-competitors.json", json.dumps([{"id": "SC001", "url": "https://docs.python.org/3/", "title": "Python"}]))
    write(out / "data" / "stray.json", "{}")                                     # агент вышел за свои пути
    run(out, "done", "comp")
    r = run(out, "close-wave", "4", "--json")
    assert r.returncode == 1, r.stdout + r.stderr
    info = json.loads(r.stdout)
    assert [v["file"] for v in info["check_paths"]["violations"]] == ["data/stray.json"]
    assert info["merge_sources"]["code"] == 0                                   # merge_sources --keep-ids после волны
    assert (out / "data" / "sources.json").is_file()
    assert state(out)["waves"]["4"]["closed"]
    assert run(out, "close-wave", "nope").returncode == 2


def test_report_respects_disclosure(out):
    run(out, "add", "--id", "G1", "--wave", "5a", "--kind", "details", "--search", "5", "--fetch", "10")
    run(out, "start", "G1")
    run(out, "done", "G1", "--tokens", "180000", "--minutes", "22", "--search", "4", "--fetch", "9", "--model-actual", "opus")
    r = run(out, "report", "--write")
    assert r.returncode == 0
    assert "| 5a / G1 | sonnet → opus | 0.18 млн | 22.0 | 4 из 5 / 9 из 10 | ok |" in r.stdout
    assert (out / "build" / "agents-report.md").read_text(encoding="utf-8").startswith("## 11.")
    cfg = json.loads((out / "build" / "run-config.json").read_text(encoding="utf-8"))
    cfg["disclosure"] = "summary"
    write(out / "build" / "run-config.json", json.dumps(cfg))
    assert run(out, "report").stdout.strip().startswith("Подготовлено с помощью ИИ-инструментов")
    cfg["disclosure"] = "none"
    write(out / "build" / "run-config.json", json.dumps(cfg))
    assert "disclosure: none" in run(out, "report").stdout
    s = run(out, "status")
    assert "Волна 5a: 1 заданий — готово 1" in s.stdout


def test_forecast_calibration_and_scope(out):
    std = dispatch.forecast("standard", 5, {})
    deep = dispatch.forecast("deep", 5, {})
    # калибровка по двум прогонам: standard ≈ 27 агентов / 6,3 млн / 6 ч; deep ≈ 50 / 11 млн / 4–5 ч (±30 %)
    assert 22 <= std["agents"] <= 35 and 4.4 <= std["tokens_m"] <= 8.2 and std["hours_range"][0] <= 6 <= std["hours_range"][1]
    assert 40 <= deep["agents"] <= 60 and 7.7 <= deep["tokens_m"] <= 14.3 and deep["hours_range"][0] <= 5 <= deep["hours_range"][1]
    q = dispatch.forecast("quick", 5, {})
    ex = dispatch.forecast("exhaustive", 5, {})
    assert q["agents"] < std["agents"] < deep["agents"] < ex["agents"] and q["tokens_m"] < std["tokens_m"] < deep["tokens_m"] < ex["tokens_m"]
    assert dispatch.forecast("standard", 1, {})["hours"] > std["hours"]                # меньше параллелизм — дольше
    cut = dispatch.forecast("standard", 5, {"scope": {"legal": False, "design_mockups": False, "design_refs": False, "communities": False},
                                            "phases": {"gap_audit": False}})
    assert cut["agents"] < std["agents"] and all(r["phase"] != "5.5" for r in cut["phases"])
    r = run(out, "forecast")                                                           # глубина и параллелизм — из run-config
    assert r.returncode == 0 and "глубина standard, параллельно ≤ 2" in r.stdout and "| 5 |" in r.stdout
    j = json.loads(run(out, "forecast", "--depth", "deep", "--parallel", "5", "--json", "--from-agents").stdout)
    assert j["depth"] == "deep" and j["actual"]["agents"] == 0 and "opus" in j["tokens_by_model_m"]


def test_triage_file_and_apply(out):
    run(out, "add", "--id", "G1", "--wave", "5a", "--kind", "titles", "--task", "заголовки кандидатов группы G1", "--paths", "data/proposals-draft-G1.json")
    run(out, "add", "--id", "G2", "--wave", "5a", "--kind", "titles", "--paths", "data/proposals-draft-G2.json")
    r = run(out, "triage", "5a")
    assert r.returncode == 0 and "typesafe_triage.py --batch" in r.stdout
    items = json.loads((out / "build" / "triage-5a.json").read_text(encoding="utf-8"))
    # 1.5.0 (FB-013): shared_out — агенты пишут в общий <OUT>, триаж не ставит isolation
    assert items[0] == {"id": "G1", "task": "заголовки кандидатов группы G1", "paths": ["data/proposals-draft-G1.json"], "shared_out": True}
    result = {"tasks": [{"id": "G1", "model": "haiku", "effort": "low", "confirm": True, "fallback": "sonnet", "effort_confirm": True, "effort_fallback": "medium"},
                        {"id": "G2", "model": "opus", "effort": "high", "confirm": False, "effort_confirm": False}],
              "ask": {"questions": [{"question": "haiku?"}]}}
    write(out / "build" / "triage-5a.result.json", json.dumps(result))
    r = run(out, "triage", "5a", "--apply", out / "build" / "triage-5a.result.json")
    assert "нужно подтверждение" in r.stdout
    t = {x["id"]: x for x in state(out)["tasks"]}
    assert (t["G1"]["model"], t["G1"]["effort"]) == ("sonnet", "medium") and (t["G2"]["model"], t["G2"]["effort"]) == ("opus", "high")
    run(out, "triage", "5a", "--apply", out / "build" / "triage-5a.result.json", "--confirmed")
    t = {x["id"]: x for x in state(out)["tasks"]}
    assert (t["G1"]["model"], t["G1"]["effort"]) == ("haiku", "low")
    rep = json.loads(run(out, "ready", "--json").stdout)
    assert rep["ready"][0]["effort"] == "low"


def test_triage_run_with_fake_script(out, tmp_path):
    fake = tmp_path / "typesafe_triage.py"
    write(fake, "import json,sys\nitems=json.load(open(sys.argv[sys.argv.index('--batch')+1]))\n"
                "print(json.dumps({'tasks':[{'id':i['id'],'model':'opus','effort':'xhigh','confirm':False,'effort_confirm':False} for i in items]}))\n")
    run(out, "add", "--id", "S1", "--wave", "7", "--kind", "section")
    r = run(out, "triage", "7", "--run", fake)
    assert r.returncode == 0, r.stderr
    t = state(out)["tasks"][0]
    assert t["model"] == "opus" and t["effort"] == "xhigh" and t["triage"] == "typesafe-triage"
