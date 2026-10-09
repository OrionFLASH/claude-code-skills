# -*- coding: utf-8 -*-
"""2.3.0 (#29): --batch tasks.json — таблица {id, model, effort, confidence, reasons}, порядок по paths («выполнять
последовательно»), ОДИН AskUserQuestion на пакет, готовые Agent(...), промпт исполнителя по шаблону, строка атрибуции.
Офлайн. pytest test_typesafe_batch.py"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import triage_batch as batch
import typesafe_triage as t

SKILL = Path(__file__).resolve().parent.parent
SCRIPT = SKILL / "scripts" / "typesafe_triage.py"
TASKS = {"tasks": [
    {"id": "P1", "task": "Выгрузка CSV теряет строки с BOM: найди причину, исправь, добавь тест", "paths": ["src/export/", "tests/test_export.py"],
     "criteria": ["тест на BOM падает до правки и проходит после", "все тесты зелёные"]},
    {"id": "P2", "task": "Поправь опечатки в REPORT.md", "paths": ["docs/REPORT.md"]},
    {"id": "P3", "task": "Добавь в REPORT.md раздел «Не проверено»", "paths": ["./docs/"]},
    {"id": "P4", "task": "Спроектируй и проведи миграцию боевой базы платежей без простоя: двойная запись, сверка, откат"},
]}


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(t, "LOG_PATH", tmp_path / "log.jsonl")
    monkeypatch.setattr(t.guard, "HOME", tmp_path / "guard")
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)


def write(tmp_path, data):
    p = tmp_path / "tasks.json"
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return str(p)


def fake(model, effort, **kw):
    r = {"model": model, "effort": effort, "source": "typesafe", "confidence": "высокая", "reason": "нагрузка 0.7; цена ошибки высокая → opus",
         "effort_reasons": ["a) TypeSafe 0.7", "e) высокая цена ошибки → не ниже high"], "confirm": False, "effort_confirm": False,
         "fallback": model, "effort_fallback": effort, "domain": {"kind": "software"}}
    r.update(kw)
    return r


# ---------- вход ----------
def test_load_tasks_validates_input(tmp_path):
    tasks = batch.load_tasks(write(tmp_path, TASKS))
    assert [x["id"] for x in tasks] == ["P1", "P2", "P3", "P4"] and tasks[3]["paths"] == []
    assert [x["id"] for x in batch.load_tasks(write(tmp_path, ["задача один", {"task": "задача два"}]))] == ["T1", "T2"]
    for bad in ({}, [], [{"id": "A"}], [{"id": "A", "task": "x"}, {"id": "A", "task": "y"}], [{"task": "x", "paths": 5}]):
        with pytest.raises(batch.BatchError):
            batch.load_tasks(write(tmp_path, bad))
    (tmp_path / "bad.json").write_text("{не json")
    with pytest.raises(batch.BatchError):
        batch.load_tasks(str(tmp_path / "bad.json"))


# ---------- пути и порядок ----------
@pytest.mark.parametrize("a,b,yes", [
    ("docs/REPORT.md", "./docs/", True), ("src/a.py", "src/a.py", True), ("src/", "src/x/y.py", True),
    ("src/a.py", "src/ab.py", False), ("docs\\REPORT.md", "docs/report.md", True), ("src/*.py", "src/a.py", True),
    ("*.md", "src/a.py", True), ("tests/test_a.py", "src/a.py", False),
])
def test_overlap(a, b, yes):
    assert batch.overlap(batch.norm_path(a), batch.norm_path(b)) is yes


def test_plan_order_queues_conflicts_and_lists_unchecked(tmp_path):
    o = batch.plan_order(batch.load_tasks(write(tmp_path, TASKS)))
    assert o["parallel"] == ["P1"] and o["unchecked"] == ["P4"]
    assert o["sequential"] == [{"ids": ["P2", "P3"], "shared": ["docs"]}]
    chain = [{"id": "A", "task": "x", "paths": ["a.py"]}, {"id": "B", "task": "x", "paths": ["a.py", "b.py"]},
             {"id": "C", "task": "x", "paths": ["b.py"]}, {"id": "D", "task": "x", "paths": ["d.py"]}]
    o = batch.plan_order(chain)
    assert o["sequential"][0]["ids"] == ["A", "B", "C"] and o["parallel"] == ["D"]


# ---------- подтверждения: один AskUserQuestion ----------
def test_one_ask_with_at_most_four_grouped_questions():
    rows = [dict(batch.row_of({"id": i, "task": "x"}, r), id=i) for i, r in (
        ("A", fake("fable", "max", confirm=True, fallback="opus", effort_confirm=True, effort_fallback="xhigh")),
        ("B", fake("fable", "high", confirm=True, fallback="opus")),
        ("C", fake("haiku", "low", confirm=True, fallback="sonnet", effort_confirm=True, effort_fallback="medium")),
        ("D", fake("opus", "high")))]
    qs = batch.ask_questions(rows)
    assert len(qs) == 4 and all(len(q["header"]) <= 12 and len(q["options"]) == 2 for q in qs)
    assert qs[0]["question"] == "Запустить на haiku задачи C?" and qs[1]["question"] == "Запустить на fable задачи A, B?"
    assert qs[1]["options"][0]["label"] == "Да, fable" and qs[1]["options"][1]["label"] == "Нет, opus"
    assert "Effort max для задач A" in qs[3]["question"]
    assert batch.ask_questions([rows[3]]) == []


def test_agent_args_yes_and_no_variants():
    row = batch.row_of({"id": "A", "task": "x", "paths": ["a.py"]},
                       fake("fable", "max", confirm=True, fallback="opus", effort_confirm=True, effort_fallback="xhigh"))
    task = {"id": "A", "task": "Перепиши модуль биллинга целиком", "paths": ["a.py"]}
    yes, no = batch.agent_args(row, task, True), batch.agent_args(row, task, False)
    assert (yes["model"], yes["effort"], no["model"], no["effort"]) == ("fable", "max", "opus", "xhigh")
    assert yes["isolation"] == "worktree" and yes["run_in_background"] is True and yes["description"].startswith("A: ")
    ro = batch.row_of({"id": "R", "task": "x"}, fake("sonnet", "medium", metrics={"read_only": {"value": 0.95}}))
    assert "isolation" not in batch.agent_args(ro, {"id": "R", "task": "Объясни структуру папки"})


# ---------- промпт исполнителя ----------
def test_template_file_has_markers_and_all_fields():
    text = (SKILL / "references" / "executor-prompt.md").read_text(encoding="utf-8")
    assert batch.TEMPLATE_START in text and batch.TEMPLATE_END in text
    tpl = batch.load_template()
    for k in ("{id}", "{goal}", "{task}", "{context}", "{paths}", "{constraints}", "{criteria}", "{report}", "{model}", "{effort}"):
        assert k in tpl, k
    assert "```" not in tpl


def test_render_prompt_is_self_contained_with_rules_and_attribution():
    task = {"id": "P1", "task": "Почини выгрузку CSV", "paths": ["src/export/", "tests/test_export.py"], "criteria": ["a", "b"]}
    row = batch.row_of(task, fake("opus", "high"))
    p = batch.render_prompt(task, row)
    assert "Ты исполнитель P1 (модель opus, effort high)" in p and "src/export/, tests/test_export.py" in p
    assert "\n- a\n- b" in p and "не вливай, не пушь" in p and "typesafe-triage не применяй" in p
    assert "Co-Authored-By из ТВОЕЙ системной" in p and "модель оркестратора не подставляй" in p
    assert "{" not in p.replace("{}", "")                                   # все поля подставлены
    plain = batch.render_prompt({"id": "X", "task": "задача"}, batch.row_of({"id": "X", "task": "задача"}, fake("sonnet", "medium")))
    assert batch.DEFAULTS["paths"] in plain and batch.DEFAULTS["report"] in plain


# ---------- весь пакет ----------
def test_run_report_structure(tmp_path):
    tasks = batch.load_tasks(write(tmp_path, TASKS))
    rep = batch.run(tasks, lambda x: fake("fable", "max", confirm=True, fallback="opus", effort_confirm=True, effort_fallback="xhigh")
                    if x["id"] == "P4" else fake("sonnet", "high"))
    row4 = next(r for r in rep["tasks"] if r["id"] == "P4")
    assert set(row4) >= {"id", "model", "effort", "confidence", "reasons", "agent", "agent_if_no", "prompt"}
    assert row4["reasons"] == ["цена ошибки высокая → opus", "высокая цена ошибки → не ниже high", "тип software"]
    assert len(rep["ask"]["questions"]) == 2 and rep["sources"] == {"typesafe": 4, "heuristic": 0}
    txt = batch.format_text(rep)
    assert "| id | model | effort | confidence | reasons |" in txt and "| P4 | fable (вопрос) | max (вопрос) |" in txt
    assert "выполнять последовательно: P2 → P3 (общие пути: docs)" in txt and "ОДИН вызов AskUserQuestion" in txt
    assert 'Agent(description="P4: Спроектируй и проведи миграцию", model="fable", effort="max"' in txt
    assert 'нет «да» → Agent(description="P4: Спроектируй и проведи миграцию", model="opus", effort="xhigh"' in txt
    assert "Co-Authored-By" in txt and "----- промпт" not in txt
    assert "----- промпт P1 -----" in batch.format_text(rep, prompts=True)


def test_cli_batch_offline_text_and_json(tmp_path):
    path = write(tmp_path, TASKS)
    env = dict(os.environ, TYPESAFE_TRIAGE_HOME=str(tmp_path / "st"))
    env.pop("TYPESAFE_API_KEY", None)
    r = subprocess.run([sys.executable, "-B", str(SCRIPT), "--batch", path], capture_output=True, text=True, env=env, timeout=60)
    assert r.returncode == 0 and "TypeSafe-триаж --batch: задач 4 (TypeSafe 0, эвристика 4)" in r.stdout
    assert "низкая (эвристика)" in r.stdout and "нет TYPESAFE_API_KEY" not in r.stdout
    j = subprocess.run([sys.executable, "-B", str(SCRIPT), "--batch", path, "--json"], capture_output=True, text=True, env=env, timeout=60)
    rep = json.loads(j.stdout)
    assert [x["id"] for x in rep["tasks"]] == ["P1", "P2", "P3", "P4"] and all(x["prompt"] for x in rep["tasks"])
    assert all(x["model"] in ("sonnet", "opus") for x in rep["tasks"])      # без TypeSafe — ни haiku, ни fable
    bad = subprocess.run([sys.executable, "-B", str(SCRIPT), "--batch"], capture_output=True, text=True, env=env, timeout=60)
    assert bad.returncode == 2
    log = (tmp_path / "st" / "log.jsonl").read_text(encoding="utf-8")
    assert log.count("\n") == 8                                              # каждая задача обоих запусков — в обычном журнале
