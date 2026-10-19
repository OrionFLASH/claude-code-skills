# -*- coding: utf-8 -*-
"""WP-D 1.5.0: пересмотр идеи C4.5 (FB-044, pivot_check.py), предпроверка жизнеспособности с единой ёмкостью (FB-028) и в
личном режиме (SM 4.3, typesafe_concept.py), вопросы Jev личного режима (typesafe_eval.py). Без сети.
Запуск: python3 -m pytest tests/test_process_pivot.py -q -p no:cacheprovider
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import typesafe_concept  # noqa: E402
import typesafe_eval  # noqa: E402


def run(script, *args):
    e = {k: v for k, v in os.environ.items() if not k.startswith("TYPESAFE_")}
    return subprocess.run([sys.executable, "-B", str(SCRIPTS / script)] + [str(a) for a in args], capture_output=True, text=True, env=e, timeout=300)


def jload(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def jdump(p, obj):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    Path(p).write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")


@pytest.fixture()
def cdemo(tmp_path):
    out = tmp_path / "c"
    assert run("make_concept_demo.py", out, "--proposals", "50").returncode == 0
    return out


# ---------------------------------------------------------------- FB-044: пересмотр идеи
def test_pivot_draft_check_question_and_narrow(cdemo):
    r = run("pivot_check.py", cdemo)
    assert r.returncode == 0 and "черновик data/premises.json" in r.stdout
    doc = jload(cdemo / "data" / "premises.json")
    kinds = [p["kind"] for p in doc["premises"]]
    assert {"distinct", "monetization", "key_feature", "feasibility"} <= set(kinds) and all(p["status"] is None for p in doc["premises"])
    assert run("pivot_check.py", cdemo, "--check").returncode == 2                         # не заполнено
    for p in doc["premises"]:
        p["status"], p["source"] = "confirmed", "research/market.md:10"
    doc["premises"][0]["status"] = "refuted"
    doc["narrowing"] = "личный каталог полок без обмена"
    jdump(cdemo / "data" / "premises.json", doc)
    r = run("pivot_check.py", cdemo, "--check", "--json")
    res = json.loads(r.stdout)
    assert r.returncode == 3 and res["needs_decision"] and res["refuted_key"] == ["PR1"]
    q = res["question"]
    assert q["options"][0]["label"] == "Принять сужение (Recommended)" and len(q["options"]) == 3 and "Исследование изменило идею" in q["question"]
    r = run("pivot_check.py", cdemo, "--decide", "narrow", "--pitch-v2", "Личный каталог книжных полок дома", "--name", "Полка",
            "--forms", "web,mobile_web", "--reason", "обмен не нужен соседям")
    assert r.returncode == 0, r.stderr
    cfg = jload(cdemo / "build" / "run-config.json")
    assert cfg["idea"]["version"] == 2 and cfg["idea"]["pitch_v2"].startswith("Личный каталог") and cfg["idea"]["history"][0]["version"] == 1
    assert cfg["product"]["name"] == "Полка" and cfg["product"]["forms"] == ["web", "mobile_web"]
    idea = jload(cdemo / "data" / "idea.json")
    assert idea["version"] == 2 and idea["history"] and idea["pitch_v2"]                   # после пересборки досье — тоже
    assert jload(cdemo / "data" / "premises.json")["decision"] == "narrow"
    assert run("pivot_check.py", cdemo, "--check").returncode == 0                         # решение принято
    # бриф следующей фазы видит сужение
    run("render_brief.py", "concept-canvas", "--out", cdemo)
    assert "идея v2: Личный каталог книжных полок дома" in (cdemo / "build" / "briefs" / "concept-canvas.md").read_text(encoding="utf-8")


def test_pivot_keep_and_narrow_requires_pitch(cdemo):
    run("pivot_check.py", cdemo)
    assert run("pivot_check.py", cdemo, "--decide", "narrow").returncode == 2
    r = run("pivot_check.py", cdemo, "--decide", "keep", "--by", "default")
    assert r.returncode == 0 and jload(cdemo / "data" / "premises.json")["by"] == "default"
    assert jload(cdemo / "build" / "run-config.json")["idea"].get("version", 1) == 1


def test_pivot_refuses_normal_mode(tmp_path):
    jdump(tmp_path / "o" / "build" / "run-config.json", {"product": {"name": "x"}})
    assert run("pivot_check.py", tmp_path / "o").returncode == 2


# ---------------------------------------------------------------- FB-028: выполнимость по единой ёмкости
def test_feasible_uses_capacity_against_mvp_size():
    base = {"mode": "concept", "project": {"team_size": 1}, "strategy": {"horizon_months": 6},
            "idea": {"facets": {"mvp": "full", "mvp_weeks": 6, "hours_week": 15}, "answers": {}}}
    full = typesafe_concept.heuristic(base)["feasible"]
    assert "ёмкость ≈" in full["note"] and "60–120 дн. объёма MVP" in full["note"]
    single = dict(base, idea={"facets": {"mvp": "single_feature", "mvp_weeks": 18, "hours_week": 15}, "answers": {}})
    assert typesafe_concept.heuristic(single)["feasible"]["p"] > full["p"]                   # одна функция за 4 мес. — выполнимее


# ---------------------------------------------------------------- SM 4.3: личный режим в предпроверке
def test_personal_mode_questions_and_verdict():
    cfg = {"mode": "concept", "project": {"audience": "personal", "team_size": 1}, "strategy": {"horizon_months": 6},
           "idea": {"facets": {"pain": "personal", "current": "manual", "frequency": "daily", "value": "time", "mvp": "single_feature",
                               "mvp_weeks": 6, "data": "personal"}, "answers": {}}}
    items = typesafe_concept.heuristic(cfg)
    assert set(items) == {"pain", "faster", "build_vs_buy", "feasible", "maintain", "payback", "data_risk", "ban_risk"}
    doc = typesafe_concept.doc_for(items, "heuristic", cfg)
    assert doc["audience"] == "personal" and [q["key"] for q in doc["questions"]][:2] == ["pain", "faster"]
    assert next(q for q in doc["questions"] if q["key"] == "data_risk")["good"] == "low"
    assert "reach" not in doc["items"] and "revenue" not in doc["items"]
    assert doc["risk"] == max(items["ban_risk"]["p"], items["data_risk"]["p"])
    assert set(typesafe_concept.questions_for({"project": {"audience": "public"}})) == set(typesafe_concept.QUESTIONS)


def test_personal_mode_jev_questions_for_proposals():
    q = typesafe_eval.questions_for({"project": {"audience": "circle"}})
    assert "p_acquisition" not in q and "p_revenue" not in q and {"p_time_saved", "p_maintainable"} <= set(q)
    assert "задачу владельца" in q["impact"]["instructions"]
    assert typesafe_eval.questions_for({}) == typesafe_eval.QUESTIONS or "p_acquisition" in typesafe_eval.questions_for({})
    assert "Личный инструмент владельца" in typesafe_eval.context_from_config({"project": {"audience": "personal"}, "product": {"name": "x"}})
