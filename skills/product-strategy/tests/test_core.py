# -*- coding: utf-8 -*-
"""Ядро product-strategy: опрос (intake.py), проверка инструментов (check_env.py), папка прогона (init_run.py),
путь скилла (skill_dir.py), конвейер (build_all.py), демо (make_demo.py). pytest tests/test_core.py"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import intake  # noqa: E402

PY = [sys.executable, "-B"]


def run(*args, **kw):
    return subprocess.run(PY + [str(SCRIPTS / args[0])] + [str(x) for x in args[1:]], capture_output=True, text=True, timeout=300, **kw)


# ---------- intake: вопросы подходят AskUserQuestion ----------
def test_rounds_fit_ask_user_question_limits():
    rounds = intake.questions_json()
    assert len(rounds) == 4
    headers = []
    for r in rounds:
        assert 1 <= len(r["questions"]) <= 4
        for q in r["questions"]:
            assert len(q["header"]) <= 12, q["header"]
            assert 2 <= len(q["options"]) <= 4, q["header"]
            assert q["question"].endswith("?") or "(можно несколько)" in q["question"]
            labels = [o["label"] for o in q["options"]]
            assert len(set(labels)) == len(labels)
            assert all(1 <= len(l.split()) <= 7 for l in labels), labels
            assert "Other" not in labels and "Другое" not in labels      # «Other» инструмент добавляет сам
            headers.append(q["header"])
    assert len(set(headers)) == len(headers)


def test_recommended_option_is_first_and_single():
    for r in intake.questions_json():
        for q in r["questions"]:
            rec = [i for i, o in enumerate(q["options"]) if "(Recommended)" in o["label"]]
            if not q["multiSelect"]:
                assert rec == [0], q["header"]


def test_defaults_match_user_request(tmp_path):
    cfg = intake.finalize(intake.base_config(tmp_path))
    assert cfg["strategy"]["proposals_min"] == 100 and cfg["strategy"]["proposals_min"] >= 50
    assert cfg["scope"]["repo_analysis"] is True                     # анализ репозитория — по умолчанию
    assert cfg["strategy"]["horizon_months"] == 12 and cfg["strategy"]["vision_years"] == 3
    assert cfg["output"]["dir"].endswith(str(Path("strategy") / cfg["created"]))


def test_apply_answers_and_open(tmp_path):
    ans = {"Стратегия": "Полная: рост + технологии", "Глубина": "Глубоко", "Предложения": "150",
           "Источники": ["Текущий репозиторий (Recommended)"], "Исследования": ["Конкуренты (Recommended)"],
           "Форматы": ["Веб-страница (Recommended)", "XLSX"], "Папка": "Рядом с репозиторием", "Бюджет": "до $300 в месяц",
           "Рынки": "ru, kz"}
    (tmp_path / "a.json").write_text(json.dumps(ans, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "o.json").write_text(json.dumps({"author": "Иванов Иван (ivan)", "sources.competitor_list": "A, B; C"},
                                                ensure_ascii=False), encoding="utf-8")
    out = tmp_path / "run"
    r = run("intake.py", "apply", "--repo", tmp_path, "--answers", tmp_path / "a.json", "--open", tmp_path / "o.json",
            "--out-dir", out, "--set", "scope.experiments=5")
    assert r.returncode == 0, r.stderr
    cfg = json.loads((out / "build" / "run-config.json").read_text(encoding="utf-8"))
    assert cfg["strategy"]["kind"] == "full" and cfg["strategy"]["depth"] == "deep"
    assert cfg["strategy"]["proposals_min"] == 150                   # явный ответ главнее глубины
    assert cfg["scope"]["competitors_min"] == 15                     # из глубины
    assert cfg["scope"]["experiments"] == 5                          # --set главнее
    assert cfg["scope"]["app_run"] is False and cfg["scope"]["communities"] is False and cfg["scope"]["legal"] is False
    assert cfg["formats"] == {"html": True, "xlsx": True, "pptx": False, "pdf": False, "md": True}
    assert cfg["strategy"]["budget"]["note"] == "до $300 в месяц"
    assert cfg["strategy"]["markets"] == ["ru", "kz"]
    assert cfg["author"] == {"name": "Иванов Иван", "nick": "ivan", "copyright": "© %s Иванов Иван (ivan)" % cfg["created"][:4]}
    assert cfg["sources"]["competitor_list"] == ["A", "B", "C"]
    assert "OUT=" in r.stdout


def test_proposals_floor_is_50(tmp_path):
    (tmp_path / "a.json").write_text(json.dumps({"Предложения": "20"}), encoding="utf-8")
    r = run("intake.py", "apply", "--repo", tmp_path, "--answers", tmp_path / "a.json", "--out-dir", tmp_path / "r")
    cfg = json.loads((tmp_path / "r" / "build" / "run-config.json").read_text(encoding="utf-8"))
    assert r.returncode == 0 and cfg["strategy"]["proposals_min"] == 50


def test_from_text_extracts_explicit_params():
    f = intake.from_text("Сделай подробнейшую стратегию, не менее 120 предложений, на 18 месяцев и 5 лет, без субагентов")
    assert f == {"strategy.proposals_min": 120, "strategy.depth": "exhaustive", "strategy.horizon_months": 18,
                 "strategy.vision_years": 5, "tools.subagents": False}
    assert intake.from_text("автопилот, 60 идей")["autopilot"] is True


def test_defaults_autopilot(tmp_path):
    r = run("intake.py", "defaults", "--repo", tmp_path, "--out-dir", tmp_path / "r")
    cfg = json.loads((tmp_path / "r" / "build" / "run-config.json").read_text(encoding="utf-8"))
    assert r.returncode == 0 and cfg["autopilot"] is True and cfg["assumptions"]


# ---------- init_run ----------
def test_init_run_status_cycle(tmp_path):
    out = tmp_path / "o"
    assert run("init_run.py", out).returncode == 0
    for d in ("research", "data", "charts", "mockups/concepts", "design-refs", "deliverables", "build/briefs"):
        assert (out / d).is_dir()
    assert run("init_run.py", out, "--done", "0", "--status", "опрос и инструменты готовы").returncode == 0
    r = run("init_run.py", out, "--show")
    assert "Следующая фаза: 1." in r.stdout and "опрос и инструменты готовы" in r.stdout


# ---------- check_env ----------
def test_check_env_runs_and_writes_json(tmp_path):
    r = run("check_env.py", "--json", tmp_path / "env.json", "--session-skills", "superpowers:brainstorming,data:analyze")
    assert r.returncode in (0, 1) and "python3" in r.stdout
    data = json.loads((tmp_path / "env.json").read_text(encoding="utf-8"))
    names = {x["name"] for x in data["rows"]}
    assert {"python3", "git", "node", "node:playwright", "skill:superpowers"} <= names
    sp = next(x for x in data["rows"] if x["name"] == "skill:superpowers")
    assert sp["status"] == "OK"                                      # увиден по списку сессии
    assert "TYPESAFE_API_KEY" in names
    assert all("sk-" not in json.dumps(x) for x in data["rows"])     # значения ключей не печатаются


def test_check_env_plan_lists_local_installs(tmp_path):
    r = run("check_env.py", "--plan", "--out", tmp_path / "x")
    assert "Поставлю сам" in r.stdout and "Нужно согласие" in r.stdout


# ---------- skill_dir, demo, build_all ----------
def test_skill_dir_prints_folder_with_skill_md():
    r = run("skill_dir.py")
    assert r.returncode == 0 and (Path(r.stdout.strip()) / "SKILL.md").exists()


def test_demo_and_build_all_html_and_xlsx(tmp_path):
    out = tmp_path / "demo"
    assert run("make_demo.py", out, "--proposals", "60").returncode == 0
    props = json.loads((out / "data" / "proposals.json").read_text(encoding="utf-8"))
    assert len(props) == 60 and len({p["category"] for p in props}) == 10
    r = run("build_all.py", out, "--skip", "links,pptx,pdf,smoke,mockups")
    assert "registry" in r.stdout and "Итог" in r.stdout
    if (SCRIPTS / "build_html.py").exists():
        assert (out / "deliverables" / "index.html").exists(), r.stdout + r.stderr
    if (SCRIPTS / "build_xlsx.py").exists():
        assert (out / "deliverables" / "strategy.xlsx").exists(), r.stdout + r.stderr


@pytest.mark.parametrize("name", ["SKILL.md", "INSTALL.md", "README.md", "references/data-contract.md", "references/intake.md",
                                  "references/tools.md"])
def test_docs_exist_and_mention_scripts(name):
    p = SCRIPTS.parent / name
    assert p.exists()
    text = p.read_text(encoding="utf-8")
    for script in ("intake.py", "check_env.py") if name == "SKILL.md" else ("intake.py",) if name == "references/intake.md" else ():
        assert script in text


def test_skill_md_references_existing_files():
    import re
    text = (SCRIPTS.parent / "SKILL.md").read_text(encoding="utf-8")
    for ref in set(re.findall(r"`((?:references|templates)/[\w./-]+\.md)`", text)):
        if "{" in ref:
            continue
        assert (SCRIPTS.parent / ref).exists(), ref
