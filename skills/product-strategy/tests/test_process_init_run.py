# -*- coding: utf-8 -*-
"""WP-D 1.5.0: процесс прогона в init_run.py — журнал вмешательств (FB-004), один чек-лист в TASKS.md (FB-040), фазы и ворота
(FB-015), ветка (FB-034), decisions.json после оценки (FB-049), статус с ETA (SM 10.2), протокол смены решения (SM 10.1),
фазы C4.5/C7.5/C8.5, каркас материалов владельца (FB-002). Без сети.
Запуск: python3 -m pytest tests/test_process_init_run.py -q -p no:cacheprovider
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
import init_run  # noqa: E402

needs_git = pytest.mark.skipif(not shutil.which("git"), reason="нет git")


def env(**extra):
    e = {k: v for k, v in os.environ.items() if not k.startswith("TYPESAFE_")}
    e.update(extra)
    return e


def run(*args, e=None):
    return subprocess.run([sys.executable, "-B", str(SCRIPTS / "init_run.py")] + [str(a) for a in args], capture_output=True, text=True,
                          env=e or env(), timeout=120)


def write(p, text):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    Path(p).write_text(text, encoding="utf-8")


def concept_out(base, **cfg_extra):
    out = base / "concept" / "idea" / "2026-10-19"
    cfg = {"mode": "concept", "product": {"name": "Трекер ARC Raiders", "type": "saas"}, "idea": {"pitch": "Трекер для игры"},
           "strategy": {"depth": "standard", "horizon_months": 6}, "output": {"inside_repo": True, "git_branch": "docs/concept-arc-raiders-tracker"}}
    cfg.update(cfg_extra)
    write(out / "build" / "run-config.json", json.dumps(cfg, ensure_ascii=False))
    return out


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo)] + list(args), capture_output=True, text=True)


# ---------------------------------------------------------------- FB-004: журнал ручных вмешательств
def test_intervention_journal_records_by_and_kind(tmp_path):
    out = concept_out(tmp_path)
    assert run(out).returncode == 0
    r = run(out, "--intervention", "свой бриф интеграции | в скилле нет брифа | %s/build/briefs/tech-integration.md" % out, "--by", "orchestrator")
    assert r.returncode == 0 and "вмешательство записано" in r.stdout
    run(out, "--intervention", "правка model-params, профиль web вместо mobile, build/model-params.json", "--by", "owner")
    recs = [json.loads(x) for x in (out / "build" / "interventions.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [x["by"] for x in recs] == ["orchestrator", "owner"]
    assert recs[0]["kind"] == "brief" and recs[0]["why"] == "в скилле нет брифа"
    assert str(tmp_path) not in recs[0]["file"] and recs[0]["file"].endswith("build/briefs/tech-integration.md")   # без абсолютных путей
    assert recs[1]["kind"] == "data-edit" and recs[1]["file"] == "build/model-params.json"
    assert recs[0]["phase"] == "C0"                                                           # текущая (следующая) фаза
    assert "Ручных вмешательств в журнале: 2" in run(out, "--show").stdout


# ---------------------------------------------------------------- FB-040: один чек-лист
@needs_git
def test_tasks_md_in_repo_root_gets_phase_block_and_syncs_both_ways(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    write(repo / "TASKS.md", "# TASKS\n\n- [ ] своя задача владельца\n")
    out = concept_out(repo)
    e = env(PS_OWNER_CLAUDE_MD=str(tmp_path / "нет.md"))
    r = run(out, e=e)
    assert r.returncode == 0 and "Чек-лист: TASKS.md" in r.stdout
    assert not (out / "STRATEGY_TASKS.md").exists()                                           # один чек-лист
    t = (repo / "TASKS.md").read_text(encoding="utf-8")
    assert "- [ ] своя задача владельца" in t and "<!-- product-strategy:phases concept/idea/2026-10-19 -->" in t
    assert "- [ ] C0. " in t and "- [ ] C9. " in t
    # отметка в STATUS → в TASKS.md; отметка в TASKS.md → в STATUS
    write(out / "build" / "env.json", json.dumps({"rows": [{"name": "python3"}]}))
    assert run(out, "--done", "C0", e=e).returncode == 0
    assert "- [x] C0. " in (repo / "TASKS.md").read_text(encoding="utf-8")
    t = (repo / "TASKS.md").read_text(encoding="utf-8").replace("- [ ] C3. ", "- [x] C3. ")
    (repo / "TASKS.md").write_text(t, encoding="utf-8")
    run(out, "--sync", e=e)
    st = (out / "build" / "STATUS.md").read_text(encoding="utf-8")
    assert "- [x] C3. " in st and "отмечены по чек-листу TASKS.md: C3" in st
    phases_status = [(n, c) for n, c, _ in init_run.phases_in(st)]
    block = init_run.block_re("concept/idea/2026-10-19").search((repo / "TASKS.md").read_text(encoding="utf-8")).group(0)
    assert phases_status == [(n, c) for n, c, _ in init_run.phases_in(block)]                # фазы совпадают со STATUS.md
    assert "Чек-лист: TASKS.md (в корне репозитория есть TASKS.md" in run(out, "--show", e=e).stdout


@needs_git
def test_claude_md_rule_selects_tasks_md_and_explicit_choice_wins(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    rule = tmp_path / "CLAUDE.md"
    rule.write_text("Для длинной задачи веди чек-лист в TASKS.md в корне проекта.\n", encoding="utf-8")
    out = concept_out(repo)
    r = run(out, e=env(PS_OWNER_CLAUDE_MD=str(rule)))
    assert "правило владельца" in r.stdout and (repo / "TASKS.md").exists() and not (out / "STRATEGY_TASKS.md").exists()
    out2 = concept_out(tmp_path / "repo2")
    git(tmp_path / "repo2", "init", "-q")
    r = run(out2, "--tasks-file", "STRATEGY_TASKS.md", e=env(PS_OWNER_CLAUDE_MD=str(rule)))
    assert r.returncode == 0 and (out2 / "STRATEGY_TASKS.md").exists() and not (tmp_path / "repo2" / "TASKS.md").exists()
    assert json.loads((out2 / "build" / "run-config.json").read_text(encoding="utf-8"))["output"]["tasks_file"] == "STRATEGY_TASKS.md"


def test_outside_repo_keeps_strategy_tasks(tmp_path):
    out = concept_out(tmp_path)
    assert run(out, e=env(PS_OWNER_CLAUDE_MD=str(tmp_path / "x.md"))).returncode == 0
    assert (out / "STRATEGY_TASKS.md").exists()


# ---------------------------------------------------------------- FB-034: ветка
@needs_git
def test_show_compares_branch_with_run_config(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    out = concept_out(repo)
    e = env(PS_OWNER_CLAUDE_MD=str(tmp_path / "x.md"))
    run(out, e=e)
    r = run(out, "--show", e=e)
    assert "текущая ветка main, а в run-config output.git_branch = docs/concept-arc-raiders-tracker" in r.stdout
    git(repo, "switch", "-q", "-c", "docs/concept-arc-raiders-tracker")
    assert "Ветка: docs/concept-arc-raiders-tracker — совпадает с run-config" in run(out, "--show", e=e).stdout


# ---------------------------------------------------------------- фазы 1.5: C4.5, C7.5, C8.5; ворота FB-015
def test_concept_phases_c45_needs_decision_and_c85_off_by_default(tmp_path):
    out = concept_out(tmp_path)
    run(out)
    st = (out / "build" / "STATUS.md").read_text(encoding="utf-8")
    assert "- [ ] C4.5. Пересмотр идеи" in st and "- [ ] C7.5. " in st and "- [ ] C8.5. " in st
    cfg = init_run.load_cfg(out)
    assert init_run.phase_disabled(cfg, "C8.5") and not init_run.phase_disabled(cfg, "C4.5")
    write(out / "data" / "premises.json", json.dumps({"premises": [{"id": "PR1", "status": "refuted"}], "decision": None}))
    assert "решение в data/premises.json" in " ".join(init_run.missing_artifacts(out, cfg, "C4.5"))
    write(out / "data" / "premises.json", json.dumps({"premises": [{"id": "PR1", "status": "refuted"}], "decision": "narrow"}))
    assert init_run.missing_artifacts(out, cfg, "C4.5") == []
    write(out / "build" / "deps-patch.json", "[]")                                            # пустой итог C7.5 — тоже артефакт
    assert init_run.missing_artifacts(out, cfg, "C7.5") == []
    cfg2 = dict(cfg, idea={"pitch": "x", "facets": {"prototype_needed": True}})
    assert not init_run.phase_disabled(cfg2, "C8.5")
    opened = dict(init_run.open_phases(out))
    assert "C0" in opened and "C8.5" not in opened and "C4.5" not in opened                  # C4.5 по артефактам, C8.5 выключена


def test_decisions_init_after_scoring_phase(tmp_path):
    out = concept_out(tmp_path)
    run(out)
    write(out / "data" / "scores.json", json.dumps([{"id": "P001", "rank": 1, "priority": "P0", "title": "x"}]))
    write(out / "data" / "proposals.json", json.dumps([{"id": "P001", "title": "x"}]))
    r = run(out, "--done", "C6")
    assert r.returncode == 0 and (out / "data" / "decisions.json").exists() and "decisions.py --init" in r.stdout


# ---------------------------------------------------------------- SM 10.2: статус с ETA
def test_status_table_eta_open_files_and_running_agents(tmp_path):
    out = concept_out(tmp_path, tools={"max_parallel_agents": 5})
    run(out)
    write(out / "build" / "env.json", "{\"rows\": [1]}")
    write(out / "research" / "idea-dossier.md", "# Досье\nтекст\n")
    write(out / "data" / "idea.json", "{\"pitch\": \"x\"}")
    write(out / "build" / "agents.json", json.dumps({"tasks": [
        {"id": "A1", "wave": "C4", "phase": "C4", "status": "running", "started": "2026-10-19T10:00:00", "kind": "research"},
        {"id": "M1", "wave": "C4", "phase": "C4", "status": "pending", "kind": "research"},
        {"id": "G1", "wave": "C5", "phase": "C5", "status": "pending", "kind": "details"}]}))
    r = run(out, "--status")
    assert r.returncode == 0, r.stderr
    assert "| Фаза | Статус | Что открыть сейчас | ETA | Кто работает |" in r.stdout
    assert "| C1 | готова | `research/idea-dossier.md`" in r.stdout
    assert "| C4 | идёт (агентов работает 1) |" in r.stdout and "| A1 |" in r.stdout
    assert "Осталось ≈" in r.stdout and "Можно открыть уже сейчас: research/idea-dossier.md" in r.stdout
    j = json.loads(run(out, "--status-json").stdout)
    c4 = next(x for x in j["rows"] if x["phase"] == "C4")
    assert c4["eta_min"] >= 5 and j["remaining_min"] > 0
    st = (out / "build" / "STATUS.md").read_text(encoding="utf-8")
    assert "__TABLE__" not in st                                                              # таблица не пишется чекпоинтом
    assert run(out, "--status", "C1 готово").returncode == 0 and "C1 готово" in (out / "build" / "STATUS.md").read_text(encoding="utf-8")
    assert "C4: 2 агент(ов), готово 0, ждём A1, M1" in run(out, "--show").stdout              # FB-014: волны в --show


# ---------------------------------------------------------------- SM 10.1: смена решения
def test_impact_lists_phases_files_commands_and_reopens(tmp_path):
    out = concept_out(tmp_path)
    run(out)
    write(out / "mockups" / "tokens.css", ":root{}")
    write(out / "mockups" / "concepts" / "M01-x.html", "<html>P012</html>")
    write(out / "build" / "parts" / "strategy-10.md", "## 10. План\nP012 — каталог\n")
    s = (out / "build" / "STATUS.md").read_text(encoding="utf-8").replace("- [ ] C8. ", "- [x] C8. ").replace("- [ ] C7. ", "- [x] C7. ")
    (out / "build" / "STATUS.md").write_text(s, encoding="utf-8")
    r = run(out, "--impact", "владелец отклонил вариант E, режимы интерфейса", "--keys", "design.chosen,P012", "--reopen", "--json", "--by", "owner")
    rep = json.loads(r.stdout)
    assert "C8" in rep["phases"] and "C7" in rep["phases"] and rep["proposals"] == ["P012"]
    assert "mockups/tokens.css" in rep["files"] and "build/parts/strategy-10.md" in rep["files"] and "mockups/concepts/M01-x.html" in rep["files"]
    assert any("shoot_mockups" in c for c in rep["commands"]) and any("build_all.py <OUT> --preview" in c for c in rep["commands"])
    assert set(rep["reopened"]) == {"C7", "C8"}
    st = (out / "build" / "STATUS.md").read_text(encoding="utf-8")
    assert "- [ ] C8. " in st and "сняты отметки фаз" in st
    rec = json.loads((out / "build" / "interventions.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert rec["kind"] == "decision-change" and rec["by"] == "owner"


# ---------------------------------------------------------------- FB-002: каркас материалов владельца
def test_owner_materials_skeleton(tmp_path):
    out = concept_out(tmp_path, sources={"owner_docs": [{"url": "https://claude.ai/public/artifacts/abc", "role": "base"},
                                                         {"url": "https://arcraiders.com", "role": "ref", "status": "read", "tool": "WebFetch"}]})
    run(out)
    r = run(out, "--owner-materials")
    assert r.returncode == 0 and "добавлено ссылок 2" in r.stdout
    t = (out / "build" / "owner-materials.md").read_text(encoding="utf-8")
    assert "## https://claude.ai/public/artifacts/abc" in t and "- Статус: not_attempted" in t and "основа вопросов" in t
    assert "- Статус: read" in t
    assert "добавлено ссылок 0" in run(out, "--owner-materials").stdout                      # повтор не дублирует
