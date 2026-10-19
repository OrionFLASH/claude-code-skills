# -*- coding: utf-8 -*-
"""Волна 2 (1.5.0): запросы пакетов к init_run.py, dispatch.py, typesafe_concept.py, pivot_check.py, intake.py, app_scan.py —
сверка ветки и owner_rules.tasks_file (FB-034, FB-040), открытые пункты сверки модели и Ганта (wp-b №9), виды новых брифов и
волна C8.5 (wp-g №7), политика моделей и effort (FB-003), решение mvp_capacity (SM 4.3), --topic-en при сужении идеи (FB-044),
вопрос о скриншотах конкурентов и строки сводки «Начинаю?» (FB-042, wp-d №3–4), пути с «~» (FB-017).
Запуск: python3 -m pytest tests/test_wave2_process.py -q -p no:cacheprovider
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import dispatch  # noqa: E402
import init_run  # noqa: E402
import typesafe_concept  # noqa: E402

PY = [sys.executable, "-B"]


def env(**extra):
    e = {k: v for k, v in os.environ.items() if not k.startswith("TYPESAFE_")}
    e.update(extra)
    return e


def run(script, *args, **kw):
    return subprocess.run(PY + [str(SCRIPTS / script)] + [str(a) for a in args], capture_output=True, text=True, timeout=600,
                          env=kw.get("env") or env())


def write(p, obj):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    Path(p).write_text(obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")


def jload(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def git(*args, cwd):
    return subprocess.run(["git"] + list(args), cwd=str(cwd), capture_output=True, text=True, timeout=60,
                          env=env(GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.com"))


needs_git = pytest.mark.skipif(not shutil.which("git"), reason="нет git")


@pytest.fixture(scope="module")
def demo_src(tmp_path_factory):
    out = tmp_path_factory.mktemp("w2p") / "cdemo"
    assert run("make_concept_demo.py", out, "--proposals", "50").returncode == 0
    return out


@pytest.fixture()
def demo(demo_src, tmp_path):
    out = tmp_path / "cdemo"
    shutil.copytree(demo_src, out)
    return out


# ---------------------------------------------------------------- init_run
@needs_git
def test_branch_line_shows_branch_status_and_note(tmp_path):
    """FB-034 (wp-a №3): --show/--status сверяют ветку с output.git_branch и показывают branch_status / branch_note."""
    repo = tmp_path / "repo"
    repo.mkdir()
    git("init", "-q", "-b", "main", cwd=repo)
    out = repo / "concept" / "x"
    write(out / "build" / "run-config.json", {"mode": "concept", "output": {"git_branch": "docs/concept-x", "branch_status": "skipped",
                                                                            "branch_note": "сейчас не основная ветка"}})
    line = init_run.branch_line(out, jload(out / "build" / "run-config.json"))
    assert line.startswith("ВНИМАНИЕ: текущая ветка main") and "не создавалась — сейчас не основная ветка" in line
    git("switch", "-q", "-c", "docs/concept-x", cwd=repo)
    line = init_run.branch_line(out, jload(out / "build" / "run-config.json"))
    assert "совпадает с run-config" in line and "при создании прогона" in line
    assert run("init_run.py", out).returncode == 0
    st = jload(out / "build" / "run-config.json")
    r = run("init_run.py", out, "--status-json")
    if r.returncode == 0 and r.stdout.strip().startswith("{"):
        assert "совпадает с run-config" in json.loads(r.stdout).get("branch", "")
    assert st["output"]["git_branch"] == "docs/concept-x"


@needs_git
def test_owner_rules_tasks_file_default_inside_repo(tmp_path):
    """FB-040 (wp-a №3): owner_rules.tasks_file — чек-лист по умолчанию в TASKS.md (внутри git), STRATEGY_TASKS.md не создаётся;
    вне репозитория правило не применяется."""
    repo = tmp_path / "repo"
    repo.mkdir()
    git("init", "-q", "-b", "main", cwd=repo)
    out = repo / "concept" / "x"
    cfg = {"mode": "concept", "owner_rules": {"sources": ["CLAUDE.md"], "tasks_file": "TASKS.md"}}
    write(out / "build" / "run-config.json", cfg)
    target, why = init_run.tasks_target(out, cfg)
    assert target == repo.resolve() / "TASKS.md" and "owner_rules.tasks_file" in why
    r = run("init_run.py", out, env=env(PS_OWNER_CLAUDE_MD=str(tmp_path / "none.md")))
    assert r.returncode == 0 and (repo / "TASKS.md").exists() and not (out / "STRATEGY_TASKS.md").exists()
    outside = tmp_path / "plain" / "x"
    write(outside / "build" / "run-config.json", cfg)
    assert init_run.tasks_target(outside, cfg)[0] is None


def test_open_items_from_model_and_baseline(tmp_path):
    """wp-b №9: model.json → reconciliation.items и plan-baseline.json → gantt_contract.messages — открытые пункты в --status."""
    out = tmp_path / "o"
    write(out / "build" / "run-config.json", {"mode": "concept"})
    write(out / "data" / "model.json", {"reconciliation": {"items": [{"code": "revenue_before_paid", "message": "выручка с 1-го месяца, а платная веха — 4-й"}]}})
    write(out / "data" / "plan-baseline.json", {"gantt_contract": {"messages": ["нет задач в месяцах 7–12"]}})
    items = init_run.open_items(out)
    assert any("выручка с 1-го месяца" in x for x in items) and any("месяцах 7–12" in x for x in items)
    assert run("init_run.py", out).returncode == 0
    r = run("init_run.py", out, "--status")
    assert "Открытые пункты сверки" in r.stdout and "месяцах 7–12" in r.stdout


# ---------------------------------------------------------------- dispatch
def test_brief_kinds_and_waves_for_new_briefs(tmp_path):
    """wp-g №7: вид и волна новых брифов выводятся из имени; режимы прототипа — prototype_mode."""
    assert dispatch.brief_kind("build/briefs/research-ai.md") == ("ai", "C4")
    assert dispatch.brief_kind("build/briefs/prototype-mode-pro.md") == ("prototype_mode", "C8.5")
    assert dispatch.brief_kind("build/briefs/strategy-summary.md") == ("summary", "C7")
    assert dispatch.brief_kind("build/briefs/strategy-section-S1.md") is None
    out = tmp_path / "o"
    write(out / "build" / "run-config.json", {"mode": "concept"})
    t = dispatch.make_task(out, {"id": "X1", "brief": "build/briefs/concept-admin.md"})
    assert t["kind"] == "module" and t["wave"] == "C7" and t["model"] == "opus"
    t = dispatch.make_task(out, {"id": "X2", "brief": "build/briefs/research-datasources.md", "wave": "C4b"})
    assert t["kind"] == "datasources" and t["wave"] == "C4b" and t["model"] == "sonnet"
    t = dispatch.make_task(out, {"id": "X3", "brief": "build/briefs/research-ai.md", "model": "sonnet"})
    assert t["kind"] is None and t["model"] == "sonnet"                         # явная модель важнее вывода по имени


def test_concept_forecast_modules_and_prototype_steps():
    """wp-g №7: модули C4/C7 по признакам идеи; C8.5 — ядро → оболочка → режимы × N → регрессия."""
    cfg = {"mode": "concept", "idea": {"facets": {"ai_role": ["разбор"], "data_sources_needed": ["API"], "admin_needed": True,
                                                  "owner_repos": ["~/x"], "prototype_needed": True}},
           "design": {"modes": ["beginner", "pro"]}}
    plan = dispatch.concept_agents("deep", cfg)
    assert plan["C4"]["ai"] == 1 and plan["C4"]["datasources"] == 1 and plan["C4"]["owner_refs"] == 1
    assert plan["C7"]["module"] == 2
    assert plan["C8.5"] == {"prototype_core": 1, "prototype_shell": 1, "prototype_mode": 2, "prototype_regression": 1}
    fc = dispatch.forecast("deep", 5, cfg)
    row = next(r for r in fc["phases"] if r["phase"] == "C8.5")
    assert row["agents"] == 5 and row["minutes"] > 0
    assert "C8.5" not in dispatch.concept_agents("standard", {"mode": "concept"})
    assert dispatch.concept_agents("quick", dict(cfg))["C8.5"] == {"prototype_core": 1}


def test_ready_prints_model_and_effort_policy(tmp_path):
    """FB-003 (wp-a №5): effort — только при explicit; custom — правила владельца из tools.agents.note."""
    out = tmp_path / "o"
    write(out / "build" / "run-config.json", {"mode": "concept", "tools": {"agents": {"model_policy": "custom", "effort_policy": "none",
                                                                                      "note": "всё на opus"}}})
    assert run("dispatch.py", out, "add", "--id", "A1", "--brief", "build/briefs/concept-analogs.md", "--kind", "research",
               "--effort", "high").returncode == 0
    r = run("dispatch.py", out, "ready")
    assert "effort=" not in r.stdout and "политика моделей custom: всё на opus" in r.stdout and "effort не задаётся" in r.stdout
    r = run("dispatch.py", out, "ready", "--json")
    d = json.loads(r.stdout)
    assert d["policy"] == {"model": "custom", "effort": "none", "note": "всё на opus"} and d["ready"][0]["effort"] is None
    cfg = jload(out / "build" / "run-config.json")
    cfg["tools"]["agents"] = {"model_policy": "default", "effort_policy": "explicit"}
    write(out / "build" / "run-config.json", cfg)
    r = run("dispatch.py", out, "ready")
    assert 'effort="high"' in r.stdout and "политика моделей default" in r.stdout


# ---------------------------------------------------------------- typesafe_concept, pivot_check
def test_capacity_fit_notes_owner_decision():
    """SM 4.3 C2 (wp-a №6): feasible — по capacity.capacity и решению idea.decisions.mvp_capacity."""
    cfg = {"project": {"capacity": {"hours_per_week": 10, "dev_share": 0.7, "day_hours": 8}},
           "idea": {"facets": {"mvp": "full", "mvp_weeks": 8}, "decisions": {"mvp_capacity": "risk"}}}
    adj, note = typesafe_concept.capacity_fit(cfg)
    assert adj < 0 and "ёмкость ≈" in note and "риск срыва срока принят" in note
    cfg["idea"]["decisions"] = {}
    assert "решение владельца" not in typesafe_concept.capacity_fit(cfg)[1]


def test_pivot_narrow_with_topic_en(demo):
    """FB-044 (wp-a №7): --decide narrow --topic-en → idea.topic_en и topic_en_for = новая версия; план поиска без <EN: …>."""
    assert run("pivot_check.py", demo).returncode == 0
    doc = jload(demo / "data" / "premises.json")
    for p in doc["premises"]:
        p["status"], p["source"] = "refuted", "research/market.md:3"
    write(demo / "data" / "premises.json", doc)
    r = run("pivot_check.py", demo, "--decide", "narrow", "--pitch-v2", "Обмен детскими книгами в одном доме",
            "--topic-en", "children's book swap in one building")
    assert r.returncode == 0, r.stdout + r.stderr
    idea = jload(demo / "build" / "run-config.json")["idea"]
    assert idea["version"] == 2 and idea["topic_en"] == "children's book swap in one building" and idea["topic_en_for"] == 2
    assert jload(demo / "data" / "idea.json")["version"] == 2
    plan = (demo / "build" / "search-plan.md").read_text(encoding="utf-8")
    assert "<EN:" not in plan and "children's book swap" in plan


def test_pivot_narrow_without_topic_en_hints(demo):
    assert run("pivot_check.py", demo).returncode == 0
    r = run("pivot_check.py", demo, "--decide", "narrow", "--pitch-v2", "Только детские книги", "--no-refresh")
    assert r.returncode == 0 and "--topic-en" in r.stdout


# ---------------------------------------------------------------- intake: сводка «Начинаю?», скриншоты, пути с «~»
def _home_env(tmp_path):
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True, exist_ok=True)
    return env(HOME=str(home))


@needs_git
def test_concept_apply_asks_competitor_shots_and_shows_checklist(tmp_path):
    """FB-042 (wp-d №3–4): репозиторий не приватный → вопрос о скриншотах конкурентов до «Начинаю?»; в сводке — чек-лист и прогноз."""
    repo = tmp_path / "repo"
    repo.mkdir()
    git("init", "-q", "-b", "main", cwd=repo)
    answers = {"Вопросов": "15 (Recommended)", "Глубина": "Стандарт (Recommended)", "Папка": "Текущая папка: concept/ (Recommended)"}
    r = subprocess.run(PY + [str(SCRIPTS / "intake.py"), "concept-apply", "--repo", str(repo), "--idea", "Обмен книгами между соседями",
                             "--from-askuser", json.dumps(answers, ensure_ascii=False), "--dry-run", "--json"],
                       capture_output=True, text=True, timeout=120, env=_home_env(tmp_path), cwd=str(repo))
    assert r.returncode == 0, r.stdout + r.stderr
    d = json.loads(r.stdout)
    fu = {x["path"]: x for x in d["follow_up"]}
    assert "output.competitor_shots" in fu and set(fu["output.competitor_shots"]["options"].values()) == {"local", "previews", "git"}
    summary = d["summary"] if isinstance(d["summary"], str) else "\n".join(d["summary"])
    assert "Чек-лист:" in summary and "Прогноз объёма: агентов" in summary


def test_write_config_expands_tilde(tmp_path, monkeypatch):
    """FB-017 (wp-d №2): пути run-config с «~» (relocate_run.py --portable-config) безопасны для записи."""
    import intake
    monkeypatch.setenv("HOME", str(tmp_path))
    p = intake.write_config({"output": {"dir": "~/runs/x"}})
    assert p == tmp_path / "runs" / "x" / "build" / "run-config.json" and p.exists()
    assert jload(p)["output"]["dir"] == "~/runs/x"


def test_app_scan_repo_path_tilde(tmp_path, monkeypatch):
    """wp-d №17: app_scan.collect_targets — repo.path с «~»."""
    import app_scan
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / "proj").mkdir()
    (tmp_path / "proj" / "app.apk").write_bytes(b"PK")
    out = tmp_path / "o"
    write(out / "build" / "run-config.json", {"repo": {"path": "~/proj"}})
    assert [p.name for p in app_scan.collect_targets(out, None)] == ["app.apk"]
