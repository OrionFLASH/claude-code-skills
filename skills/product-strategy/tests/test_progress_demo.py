"""Тесты make_progress_demo.py — демо-данные режима «Отслеживание выполнения» строго по references/data-contract.md.

  python3 -m pytest skills/product-strategy/tests/test_progress_demo.py -q
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SKILL = Path(__file__).resolve().parent.parent
SCRIPTS = SKILL / "scripts"
GEN = SCRIPTS / "make_progress_demo.py"

STATUSES = {"done", "partial", "in_progress", "planned", "not_started", "blocked", "dropped", "obsolete", "unknown"}
CLOSED = {"done", "dropped", "obsolete"}
GSTATUSES = {"done", "partial", "on_track", "behind", "upcoming"}
REV_TYPES = {"mark_done", "obsolete", "reprioritize", "add", "reschedule", "unblock", "drop"}


def run(script, *args):
    r = subprocess.run([sys.executable, str(SCRIPTS / script)] + [str(a) for a in args], capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr
    return r.stdout


def rj(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def wj(path, obj):
    Path(path).write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def with_scores(out):
    props = rj(out / "data" / "proposals.json")
    wj(out / "data" / "scores.json", [{"id": p["id"], "rank": i, "priority": "P0" if i <= 5 else "P1" if i <= 15 else "P2" if i <= 40 else "P3"}
                                      for i, p in enumerate(props, 1)])
    return out


@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    out = tmp_path_factory.mktemp("pgdemo") / "run"
    run("make_demo.py", out, "--proposals", 80)
    with_scores(out)
    stdout = run("make_progress_demo.py", out, "--apply-block")
    return {"out": out, "stdout": stdout}


def load_all(out):
    d = out / "data"
    return {"progress": rj(d / "progress.json"), "gantt": rj(d / "gantt-progress.json"), "kanban": rj(d / "kanban-progress.json"),
            "revision": rj(d / "revision.json"), "history": rj(out / "tracking" / "history.json"),
            "links": rj(d / "issue-links.json"), "overrides": rj(d / "progress-overrides.json")}


# ---------------------------------------------------------------- progress.json
def test_files_and_top_level_schema(demo):
    a = load_all(demo["out"])
    pg = a["progress"]
    for k in ("version", "baseline", "checked", "months_elapsed", "month_index", "sources", "summary", "items", "outside_strategy",
              "facts_changed", "next_actions", "overdue", "warnings"):
        assert k in pg, k
    assert pg["version"] == 1 and re.match(r"^\d{4}-\d{2}-\d{2}$", pg["checked"])
    assert set(pg["baseline"]) >= {"strategy_dir", "created", "proposals", "git_head", "scan"}
    assert set(pg["sources"]) >= {"repo", "git_log", "scan_diff", "issues", "prs", "gh"}
    assert pg["month_index"] == int(pg["months_elapsed"]) + 1 == 3
    assert "Демо-прогресс" in demo["stdout"]


def test_items_cover_registry_with_all_statuses(demo):
    out = demo["out"]
    pg = rj(out / "data" / "progress.json")
    ids = [p["id"] for p in rj(out / "data" / "proposals.json")]
    assert sorted(pg["items"]) == sorted(ids)
    seen = {it["status"] for it in pg["items"].values()}
    assert seen == STATUSES, STATUSES - seen
    for pid, it in pg["items"].items():
        assert set(it) >= {"status", "suggested", "confidence", "source", "issues", "prs", "commits", "code", "scan_diff",
                           "blocked_by_open", "note", "since"}, pid
        assert it["status"] in STATUSES and it["suggested"] in STATUSES
        assert 0.0 <= it["confidence"] <= 1.0 and it["source"] in ("auto", "override", "link")
        for x in it["issues"]:
            assert set(x) >= {"number", "state", "state_reason", "title", "url", "labels", "closed_at", "match", "score"}
            assert x["state"] in ("open", "closed") and x["match"] in ("explicit", "saved", "similar")
            # заглушка owner/repo (remote нет); PR, найденный среди issues, — kind: pr и ссылка на pull
            assert x["url"] == "https://github.com/owner/repo/%s/%d" % ("pull" if x.get("kind") == "pr" else "issues", x["number"])
        for x in it["prs"]:
            assert x["state"] in ("merged", "open", "closed") and x["url"].startswith("https://github.com/owner/repo/pull/")
        for c in it["commits"]:
            assert re.match(r"^[0-9a-f]{7}$", c["sha"]) and c["match"] in ("explicit", "files", "terms")
        for c in it["code"]:
            assert set(c) == {"file", "kind", "evidence"} and c["kind"] in ("path", "route", "feature")
    by = pg["items"]
    assert all(by[p]["issues"] and by[p]["issues"][0]["state_reason"] in ("completed", "not_planned") for p in by if by[p]["status"] == "dropped")
    blocked = [p for p in by if by[p]["status"] == "blocked"]
    assert blocked and all(by[p]["blocked_by_open"] for p in blocked)


def test_summary_consistent_with_items(demo):
    out = demo["out"]
    pg = rj(out / "data" / "progress.json")
    s, items = pg["summary"], pg["items"]
    assert s["total"] == len(items) == sum(s[k] for k in STATUSES)
    for k in STATUSES:
        assert s[k] == sum(1 for it in items.values() if it["status"] == k), k
    assert s["percent_done"] == round(100.0 * s["done"] / s["total"], 1)
    props = {p["id"]: p for p in rj(out / "data" / "proposals.json")}
    for hz, g in s["by_horizon"].items():
        assert g["total"] == sum(1 for p in props.values() if p["horizon"] == hz)
        assert g.get("done", 0) == sum(1 for pid, it in items.items() if props[pid]["horizon"] == hz and it["status"] == "done")
    assert set(s["by_priority"]) <= {"P0", "P1", "P2", "P3"} and sum(g["total"] for g in s["by_priority"].values()) == s["total"]
    assert sum(g["total"] for g in s["by_category"].values()) == s["total"]


def test_next_actions_overdue_outside_facts(demo):
    out = demo["out"]
    a = load_all(out)
    pg, items = a["progress"], a["progress"]["items"]
    props = {p["id"]: p for p in rj(out / "data" / "proposals.json")}
    assert pg["next_actions"]
    for pid in pg["next_actions"]:
        assert items[pid]["status"] in ("not_started", "planned")
        assert all(items[d]["status"] in CLOSED for d in props[pid].get("dependencies") or [] if d in items)
    behind = {t["id"] for t in a["gantt"]["tasks"] if t["status"] == "behind"}
    assert {o["task"] for o in pg["overdue"]} == behind
    for o in pg["overdue"]:
        assert set(o) == {"task", "proposals", "planned_end_month", "status"} and o["status"] == "behind"
        assert o["planned_end_month"] < pg["month_index"] or any(items[p]["status"] not in CLOSED for p in o["proposals"])
    assert pg["outside_strategy"]
    for o in pg["outside_strategy"]:
        assert set(o) >= {"kind", "number", "title", "state", "url", "suggest", "similar_to"}
        assert o["kind"] in ("issue", "pr") and o["suggest"] in ("candidate-proposal", "bug", "chore")
        assert all(p in items for p in o["similar_to"])
    for f in pg["facts_changed"]:
        assert set(f) == {"fact", "was", "now", "affects"} and all(p in items for p in f["affects"])


# ---------------------------------------------------------------- сопутствующие файлы
def test_gantt_progress(demo):
    out = demo["out"]
    gp = rj(out / "data" / "gantt-progress.json")
    gantt = rj(out / "data" / "gantt.json")
    items = rj(out / "data" / "progress.json")["items"]
    assert gp["current_month"] == 3 and len(gp["tasks"]) == len(gantt)
    for t in gp["tasks"]:
        assert set(t) == {"id", "task", "proposal_ids", "start_month", "end_month", "status", "progress", "done_ids", "open_ids"}
        assert t["status"] in GSTATUSES and 0.0 <= t["progress"] <= 1.0
        assert sorted(t["done_ids"] + t["open_ids"]) == sorted(t["proposal_ids"])
        assert all(items[p]["status"] in CLOSED for p in t["done_ids"])
        if t["status"] == "done":
            assert t["progress"] >= 0.999
        if t["status"] == "upcoming":
            assert t["start_month"] > gp["current_month"]
        if t["status"] == "behind" and t["end_month"] < gp["current_month"]:
            assert t["progress"] < 0.999


def test_kanban_progress(demo):
    out = demo["out"]
    kb = rj(out / "data" / "kanban.json")
    kp = rj(out / "data" / "kanban-progress.json")
    names = [c["name"] for c in kb["columns"]]
    plan = {c["id"]: c["column"] for c in kb["cards"]}
    assert set(kp["columns"]) <= set(names)
    placed = [pid for ids in kp["columns"].values() for pid in ids]
    assert sorted(placed) == sorted(plan)                       # каждая карточка — ровно в одной колонке
    where = {pid: col for col, ids in kp["columns"].items() for pid in ids}
    assert kp["moves"]
    for m in kp["moves"]:
        assert set(m) == {"id", "from", "to", "reason"} and m["from"] == plan[m["id"]] and m["to"] == where[m["id"]] != m["from"]
    moved = {m["id"] for m in kp["moves"]}
    assert all(where[pid] == plan[pid] for pid in plan if pid not in moved)
    items = rj(out / "data" / "progress.json")["items"]
    work = [pid for pid in plan if items[pid]["status"] == "in_progress"]
    assert all(where[pid] == "В работе" for pid in work)        # «в работе» по фактам — в колонке «В работе», не «Готово к разработке»


def test_revision_history_links_overrides(demo):
    a = load_all(demo["out"])
    items = a["progress"]["items"]
    assert a["revision"] and {r["type"] for r in a["revision"]} >= {"mark_done", "reschedule", "add"}
    for r in a["revision"]:
        assert set(r) == {"type", "id", "text", "reason", "evidence", "sections"} and r["type"] in REV_TYPES
        assert r["id"] is None or r["id"] in items
        assert all(isinstance(x, int) for x in r["sections"]) and isinstance(r["evidence"], list)
    h = a["history"]
    assert len(h) == 3 and [x["date"] for x in h] == sorted(x["date"] for x in h)
    assert h[-1]["date"] == a["progress"]["checked"] and h[-1]["summary"]["done"] == a["progress"]["summary"]["done"]
    assert h[0]["summary"]["done"] <= h[1]["summary"]["done"] <= h[2]["summary"]["done"]
    for x in h:
        assert x["summary"]["total"] == sum(x["summary"][k] for k in STATUSES) and x["git_head"]
    for pid, ov in a["overrides"].items():
        assert items[pid]["source"] == "override" and ov["status"] == items[pid]["status"] and ov["by"] == "owner"
    for pid, nums in a["links"].items():
        assert set(nums) <= {x["number"] for x in items[pid]["issues"] if x["match"] == "saved"}


def test_apply_block_idempotent(demo, tmp_path):
    out = tmp_path / "blk"
    shutil.copytree(demo["out"], out)
    md = (out / "research" / "strategy.md").read_text(encoding="utf-8")
    assert md.count("<!-- progress:start -->") == 1 and md.count("<!-- progress:end -->") == 1
    run("make_progress_demo.py", out, "--apply-block", "--seed", 5)
    md2 = (out / "research" / "strategy.md").read_text(encoding="utf-8")
    assert md2.count("<!-- progress:start -->") == 1                # повторный запуск заменяет блок, а не дописывает
    block = md2.split("<!-- progress:start -->")[1].split("<!-- progress:end -->")[0]
    assert "| Срок | Всего | Сделано |" in block and "|---|" in block
    assert md2.index("<!-- progress:start -->") > md2.index("## 13.")   # раздела 14 нет в демо — добавлен в конец


def test_deterministic_seed_and_remote(demo, tmp_path):
    out = tmp_path / "det"
    shutil.copytree(demo["out"], out)
    run("make_progress_demo.py", out)
    a = rj(out / "data" / "progress.json")
    run("make_progress_demo.py", out)
    assert rj(out / "data" / "progress.json") == a                 # тот же seed — тот же срез
    run("make_progress_demo.py", out, "--seed", 99)
    assert rj(out / "data" / "progress.json")["items"] != a["items"]
    cfg = rj(out / "build" / "run-config.json")
    cfg["repo"]["remote"] = "https://github.com/acme/widget.git"
    wj(out / "build" / "run-config.json", cfg)
    run("make_progress_demo.py", out)
    pg = rj(out / "data" / "progress.json")
    urls = [x["url"] for it in pg["items"].values() for x in it["issues"] if x.get("kind") != "pr"]
    assert urls and all(u.startswith("https://github.com/acme/widget/issues/") for u in urls) and pg["remote"] == "acme/widget"


def test_small_registry_without_scores(tmp_path):
    out = tmp_path / "small"
    run("make_demo.py", out, "--proposals", 8)
    run("make_progress_demo.py", out, "--months", 0.5)
    pg = rj(out / "data" / "progress.json")
    assert len(pg["items"]) == 8 and pg["month_index"] == 1
    assert "by_priority" not in pg["summary"]                    # нет scores.json — приоритетов нет
    assert all(it["status"] in STATUSES for it in pg["items"].values())


def test_engine_extra_fields(demo):
    """Поля, которые движок пишет сверх базовой схемы: remote, kind: pr, suspicious, mentions, discrepancies, notes, off_board."""
    a = load_all(demo["out"])
    pg, items = a["progress"], a["progress"]["items"]
    assert pg["remote"] == "owner/repo" and pg["notes"] and isinstance(pg["discrepancies"], list)
    assert any(x.get("suspicious") for it in items.values() for x in it["issues"])
    assert any(x.get("kind") == "pr" for it in items.values() for x in it["issues"])
    assert sum(1 for it in items.values() if it["mentions"]) == 3
    assert all({"title", "horizon", "priority", "issues_before", "mentions"} <= set(it) for it in items.values())
    for d in pg["discrepancies"]:
        assert set(d) >= {"id", "kind", "number", "url", "text"} and d["id"] in items
    s = pg["summary"]
    assert s["previous_check"] == a["history"][-2]["date"] and isinstance(s["changed_since_last"], int)
    kp = a["kanban"]
    on_board = {pid for ids in kp["columns"].values() for pid in ids}
    assert all(o["id"] not in on_board and items[o["id"]]["status"] in ("in_progress", "partial", "done") for o in kp["off_board"])
    assert a["gantt"]["checked"] == pg["checked"] and all("month_index" in h for h in a["history"])


def test_missing_proposals_fails(tmp_path):
    (tmp_path / "data").mkdir()
    r = subprocess.run([sys.executable, str(GEN), str(tmp_path)], capture_output=True, text=True)
    assert r.returncode != 0 and "proposals.json" in (r.stderr + r.stdout)
