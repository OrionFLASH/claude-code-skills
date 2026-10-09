# -*- coding: utf-8 -*-
"""2.3.0 (#30): журнал решений triage-log.jsonl в корне проекта — опция (по умолчанию выключен), без текста запроса;
--fact пишет факт (модель, токены, минуты, исход); --calibrate сводит факты и показывает недооценку по факту.
Офлайн. pytest test_typesafe_projectlog.py"""
import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import triage_effort as eff
import triage_projectlog as plog
import typesafe_triage as t

SCRIPT = Path(__file__).parent / "typesafe_triage.py"
SECRET_TASK = "Почини импорт CSV у клиента Ромашка, пароль password=hunter2 не трогай"


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(t, "LOG_PATH", tmp_path / "log.jsonl")
    monkeypatch.setattr(t.guard, "HOME", tmp_path / "guard")
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    monkeypatch.delenv("TYPESAFE_TRIAGE", raising=False)
    monkeypatch.setattr(eff, "session_effort", lambda cwd=None: None)


def repo(tmp_path):
    root = tmp_path / "proj"
    (root / ".git").mkdir(parents=True)
    (root / "src").mkdir()
    return root


def hook(monkeypatch, capsys, payload):
    monkeypatch.setattr(t.sys, "stdin", io.StringIO(json.dumps(payload)))
    assert t.run_hook() == 0
    out = capsys.readouterr().out
    return json.loads(out) if out.strip() else {}


def test_off_by_default(tmp_path, monkeypatch, capsys):
    root = repo(tmp_path)
    assert plog.log_path(str(root), environ={}) is None
    hook(monkeypatch, capsys, {"prompt": SECRET_TASK, "cwd": str(root / "src"), "session_id": "s"})
    assert not (root / plog.FILE_NAME).exists()


def test_paths_env_and_flag(tmp_path):
    root = repo(tmp_path)
    sub = root / "src"
    assert plog.log_path(str(sub), environ={plog.ENV: "on"}) == root / plog.FILE_NAME       # корень git-репозитория
    assert plog.log_path(str(sub), environ={plog.ENV: "logs/triage.jsonl"}) == root / "logs" / "triage.jsonl"
    assert plog.log_path(str(sub), value=True, environ={}) == root / plog.FILE_NAME
    explicit = plog.log_path(str(sub), value="/x/y.jsonl", environ={})
    assert explicit.name == "y.jsonl" and explicit.is_absolute()          # на Windows добавляется буква диска
    assert plog.log_path(str(sub), environ={plog.ENV: "off"}) is None


def test_hook_writes_decision_without_text_and_note_shows_id(tmp_path, monkeypatch, capsys):
    root = repo(tmp_path)
    monkeypatch.setenv(plog.ENV, "on")
    out = hook(monkeypatch, capsys, {"prompt": SECRET_TASK, "cwd": str(root / "src"), "session_id": "s"})
    raw = (root / plog.FILE_NAME).read_text(encoding="utf-8")
    rec = json.loads(raw.splitlines()[-1])
    assert rec["kind"] == "decision" and rec["via"] == "hook" and rec["id"] == t.prompt_id(SECRET_TASK)
    assert rec["model"] in t.TIERS and rec["effort"] in eff.EFFORTS and rec["action"] in ("self", "agent", "ask")
    assert rec["session"] == eff.session_tag("s")
    for word in ("Ромашка", "hunter2", "импорт", "CSV"):
        assert word not in raw
    assert ("id %s]" % rec["id"]) in out["hookSpecificOutput"]["additionalContext"].split("\n")[0]


def test_fact_command_and_validation(tmp_path, monkeypatch, capsys):
    root = repo(tmp_path)
    monkeypatch.chdir(root)
    assert t.main(["x", "--fact", "P1", "--model", "opus", "--effort", "xhigh", "--tokens", "550000", "--minutes", "25",
                   "--outcome", "ok", "--review-issues", "0"]) == 0
    rec = json.loads((root / plog.FILE_NAME).read_text(encoding="utf-8").splitlines()[-1])
    assert rec == dict(rec, kind="fact", ref="P1", model="opus", effort="xhigh", tokens=550000, minutes=25.0, outcome="ok",
                       review_issues=0)
    assert t.main(["x", "--fact", "P1", "--outcome", "great"]) == 2
    assert t.main(["x", "--fact", "P1", "--model", "gpt"]) == 2
    assert t.main(["x", "--fact", "P1", "--tokens", "-5"]) == 2
    assert t.main(["x", "--fact", "--model", "opus"]) == 2
    assert "--outcome" in capsys.readouterr().out


def test_expected_cost_from_facts_and_calibrate_summary(tmp_path, monkeypatch, capsys):
    root = repo(tmp_path)
    p = root / plog.FILE_NAME
    r = {"model": "opus", "effort": "xhigh", "source": "typesafe", "confidence": "высокая", "action": {"kind": "agent"}}
    plog.append(p, plog.decision_record("P1", r, "batch", task_id="P1"))
    plog.append(p, plog.fact_record("P1", "opus", "xhigh", 550000, 25, "ok"))
    plog.append(p, plog.decision_record("P2", dict(r, model="sonnet", effort="high"), "batch", task_id="P2"))
    plog.append(p, plog.fact_record("P2", "opus", "high", 300000, 40, "escalated"))
    plog.append(p, plog.fact_record("P9", "opus", "xhigh", 720000, 35, "review", 3))
    recs = plog.read(p)
    assert plog.expected(recs, "opus", "xhigh") == {"tokens": 635000, "minutes": 30, "facts": 2}
    assert plog.expected(recs, "sonnet", "high") is None                                  # фактов нет — оценки нет
    d = plog.decision_record("P3", r, "batch", records=recs)
    assert d["expected"]["tokens"] == 635000
    lines = "\n".join(plog.summary(p))
    assert "решений 2, фактов 3" in lines and "opus/xhigh: фактов 2, медиана токенов 635000" in lines
    assert "сопоставлено с решениями: 2 из 3; недооценка по факту" in lines and "P2: предсказано sonnet/high → факт opus/high" in lines
    monkeypatch.chdir(root)
    assert t.main(["x", "--calibrate", "--heuristic", "--split", "holdout"]) == 0                # факты не меняют код возврата
    assert "Журнал проекта" in capsys.readouterr().out


def test_under_by_fact_rules():
    d = {"model": "sonnet", "effort": "high"}
    assert plog.under_by_fact(d, {"model": "opus", "effort": "high", "outcome": "ok"})          # понадобилась модель выше
    assert plog.under_by_fact(d, {"model": "sonnet", "effort": "xhigh", "outcome": "ok"})       # … или effort выше
    assert plog.under_by_fact(None, {"outcome": "fail"})
    assert not plog.under_by_fact(d, {"model": "sonnet", "effort": "high", "outcome": "review"})


def test_cli_and_batch_write_decisions_with_flag(tmp_path):
    root = repo(tmp_path)
    env = dict(os.environ, TYPESAFE_TRIAGE_HOME=str(tmp_path / "st"))
    env.pop("TYPESAFE_API_KEY", None)
    r = subprocess.run([sys.executable, "-B", str(SCRIPT), "--project-log", SECRET_TASK], capture_output=True, text=True, env=env,
                       timeout=60, cwd=str(root))
    assert r.returncode == 0 and json.loads(r.stdout)["decision_id"] == t.prompt_id(SECRET_TASK)
    tasks = root / "tasks.json"
    tasks.write_text(json.dumps([{"id": "A1", "task": "Поправь опечатки в README"}], ensure_ascii=False), encoding="utf-8")
    b = subprocess.run([sys.executable, "-B", str(SCRIPT), "--batch", str(tasks), "--project-log"], capture_output=True, text=True,
                       env=env, timeout=60, cwd=str(root))
    assert b.returncode == 0
    recs = plog.read(root / plog.FILE_NAME)
    assert [x["via"] for x in recs] == ["cli", "batch"] and recs[1]["task_id"] == "A1" and recs[1]["id"] == "A1"
    assert "hunter2" not in (root / plog.FILE_NAME).read_text(encoding="utf-8")
