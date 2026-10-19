# -*- coding: utf-8 -*-
"""WP-D 1.5.0: сборка — скриншоты конкурентов (FB-012), фазы и ворота полноты (FB-015, FB-058), черновик preview (FB-057),
слияние частей схем (FB-006), проверка PDF (FB-018), генератор REPORT/README (FB-016). Без сети.
Запуск: python3 -m pytest tests/test_process_build_all.py -q -p no:cacheprovider
"""
import argparse
import json
import os
import subprocess
import sys
import zlib
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import build_all  # noqa: E402
import report  # noqa: E402

PY = [sys.executable, "-B"]


def env():
    return {k: v for k, v in os.environ.items() if not k.startswith("TYPESAFE_")}


def run(script, *args):
    return subprocess.run(PY + [str(SCRIPTS / script)] + [str(a) for a in args], capture_output=True, text=True, env=env(), timeout=600)


def write(p, obj):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    Path(p).write_text(obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False), encoding="utf-8")


def jload(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def ar_like(tmp_path):
    """Прогон «как в фидбэке AR»: снимков нет, фазы открыты, ссылка владельца не прочитана, fact-check не применён,
    вопросы запроса без маркеров, агенты не записаны, направление дизайна без владельца, пересмотра идеи нет."""
    out = tmp_path / "ar"
    cfg = {"mode": "concept", "product": {"name": "Трекер ARC Raiders"}, "strategy": {"depth": "deep"},
           "sources": {"owner_docs": [{"url": "https://claude.ai/public/artifacts/x", "role": "base"}]},
           "idea": {"pitch": "трекер", "request_questions": [{"id": "RQ01", "text": "Как конкуренты подключаются к игре?", "kind": "research"},
                                                             {"id": "RQ02", "text": "Можно ли получить сохранения?", "kind": "research"}]},
           "design": {"chosen": "A"}, "formats": {"html": False, "xlsx": False, "pptx": False, "pdf": False},
           "scope": {"unit_economics": False}}
    write(out / "build" / "run-config.json", cfg)
    assert run("init_run.py", out).returncode == 0
    write(out / "data" / "competitors.json", [{"slug": "self", "self": True, "url": None},
                                              {"slug": "metaforge", "url": "https://metaforge.app"},
                                              {"slug": "raiderbuddy", "url": "https://raiderbuddy.example"},
                                              {"slug": "arctracker", "url": "https://arctracker.example"}])
    write(out / "data" / "fact-check.json", [{"fact": "Premium MetaForge", "phase1_value": "нет", "agent_value": "$2,99", "source": "research/strategy.md:227",
                                              "resolved_value": "есть Premium", "note": ""}])
    write(out / "mockups" / "tokens.css", ":root{}")
    write(out / "research" / "strategy.md", "## 3. Конкуренты\nтекст без маркеров\n")
    return out


def ns(**kw):
    return argparse.Namespace(accept_known=kw.get("accept_known", []))


# ---------------------------------------------------------------- FB-058: ворота полноты
def test_completeness_ar_like_fails_at_least_five_and_passes_after_fixes(tmp_path):
    out = ar_like(tmp_path)
    cfg = jload(out / "build" / "run-config.json")
    rows = build_all.completeness(out, cfg, [("smoke", "SKIP", "нет playwright", 0)], ns())
    bad = {r["code"] for r in rows if r["status"] == "нет"}
    assert {"shots", "phases", "owner_materials", "fact_check", "request_questions", "report", "agents", "design_choice", "pivot"} <= bad
    assert len(bad) >= 5
    shots = next(r for r in rows if r["code"] == "shots")
    assert "у 3 из 3 конкурентов нет скриншота" in shots["detail"]
    # исправления по таблице «что сделать»
    for slug in ("metaforge", "raiderbuddy"):
        write(out / "competitors" / "shots" / ("%s.png" % slug), "png")
    comps = jload(out / "data" / "competitors.json")
    comps[1]["shot"], comps[2]["shot"], comps[3]["shot_blocked"] = "competitors/shots/metaforge.png", "competitors/shots/raiderbuddy.png", True
    write(out / "data" / "competitors.json", comps)
    write(out / "build" / "owner-materials.md", "## https://claude.ai/public/artifacts/x\n- Статус: read\n- Инструмент: чтение артефакта\n")
    fc = jload(out / "data" / "fact-check.json")
    fc[0]["applied"] = True
    write(out / "data" / "fact-check.json", fc)
    write(out / "research" / "strategy.md", "## 3. Конкуренты\nподключение через API [RQ01]; сохранения на сервере [RQ02]\n")
    write(out / "build" / "agents.json", {"tasks": [{"id": "A1", "status": "done"}]})
    cfg["design"]["chosen_by"] = "owner"
    write(out / "build" / "run-config.json", cfg)
    write(out / "data" / "premises.json", {"premises": [], "decision": "narrow"})
    for rel in ("data/communities.json", "data/keywords.json", "data/events.json", "research/market.md"):
        write(out / rel, "[1]" if rel.endswith(".json") else "# Рынок\n")
    rows = build_all.completeness(out, cfg, [("smoke", "OK", "ok 39", 0)], ns(accept_known=["phases", "report"]))
    still = {r["code"] for r in rows if r["status"] == "нет" and not r["accepted"]}
    assert still == set(), rows
    assert {r["code"] for r in rows if r["accepted"]} == {"phases", "report"}


def test_market_directions_need_file_or_skip_note(tmp_path):
    out = ar_like(tmp_path)
    cfg = jload(out / "build" / "run-config.json")
    row = next(r for r in build_all.completeness(out, cfg, [], ns()) if r["code"] == "market")
    assert row["status"] == "нет" and "поисковые запросы" in row["detail"]
    for rel in ("data/communities.json", "data/events.json", "research/market.md"):
        write(out / rel, "[1]" if rel.endswith(".json") else "# Рынок\n")
    run("init_run.py", out, "--status", "пропущено: поисковые запросы, потому что без инструментов объёмов нет")
    row = next(r for r in build_all.completeness(out, cfg, [], ns()) if r["code"] == "market")
    assert row["status"] == "да"


# ---------------------------------------------------------------- FB-012: скриншоты в сборке
def test_shots_step_fails_strict_and_passes_with_shots_and_blocked(tmp_path):
    out = tmp_path / "s"
    write(out / "build" / "run-config.json", {"formats": {"html": False, "xlsx": False, "pptx": False, "pdf": False},
                                              "scope": {"unit_economics": False}})
    write(out / "data" / "competitors.json", [{"slug": "a", "url": "https://a.example"}, {"slug": "b", "url": "https://b.example"}])
    skip = ["--skip", "charts,links,report,readme"]
    r = run("build_all.py", out, "--strict", *skip, "--accept-known", "report,market")
    assert r.returncode == 1
    assert "у 2 из 2 конкурентов нет скриншота (не заблокированы анти-ботом)" in r.stdout
    assert any(line.split()[:2] == ["shots", "FAIL"] for line in r.stdout.splitlines())
    r = run("build_all.py", out, *skip)                                                     # без --strict — предупреждение
    assert r.returncode == 0 and any(line.split()[:2] == ["shots", "WARN"] for line in r.stdout.splitlines())
    write(out / "competitors" / "shots" / "a.png", "png")
    write(out / "data" / "competitors.json", [{"slug": "a", "url": "https://a.example", "shot": "competitors/shots/a.png"},
                                              {"slug": "b", "url": "https://b.example", "shot_blocked": True}])
    r = run("build_all.py", out, "--strict", *skip, "--accept-known", "report,market")
    assert r.returncode == 0, r.stdout + r.stderr
    last = jload(out / "build" / "build-all-last.json")
    assert last["accepted_known"] == ["report", "market"] and any(c["code"] == "shots" and c["status"] == "да" for c in last["completeness"])


def test_unknown_accept_code_is_error(tmp_path):
    out = tmp_path / "s"
    write(out / "build" / "run-config.json", {})
    r = run("build_all.py", out, "--accept-known", "nonsense")
    assert r.returncode == 2 and "неизвестные коды" in r.stderr


# ---------------------------------------------------------------- FB-015 + демо: фазы синхронизируются, демо не строгое
def test_build_all_syncs_phases_and_demo_strict_is_soft(tmp_path):
    out = tmp_path / "cdemo"
    assert run("make_concept_demo.py", out, "--proposals", "50").returncode == 0
    os.rename(out / "build" / "STATUS.md", out / "build" / "STATUS.demo.md")
    assert run("init_run.py", out).returncode == 0
    r = run("build_all.py", out, "--strict", "--skip", "pptx,pdf,smoke,mockups,flowcheck,links,xlsx,deck")
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-2000:]
    assert "init_run --sync: по артефактам отмечены фазы" in r.stdout and "Ворота полноты" in r.stdout
    assert "(демо — не строго)" in r.stdout and "всё собрано" in r.stdout
    st = (out / "build" / "STATUS.md").read_text(encoding="utf-8")
    assert "- [x] C1. " in st and "- [x] C5. " in st
    last = jload(out / "build" / "build-all-last.json")
    assert last["demo"] is True and last["completeness"] and (out / "deliverables" / "REPORT.md").exists()
    rep = (out / "deliverables" / "REPORT.md").read_text(encoding="utf-8")
    assert "## 19. Ворота полноты" in rep


# ---------------------------------------------------------------- FB-057: черновик
def test_preview_builds_into_build_preview_and_leaves_deliverables(tmp_path):
    out = tmp_path / "cdemo"
    assert run("make_concept_demo.py", out, "--proposals", "50").returncode == 0
    had = (out / "deliverables" / "index.html").exists()
    r = run("build_all.py", out, "--preview")
    assert r.returncode == 0, r.stdout + r.stderr
    page = out / "build" / "preview" / "index.html"
    assert page.exists() and "Черновик (preview), не для сдачи" in page.read_text(encoding="utf-8")
    assert "только по его просьбе" in r.stdout
    assert (out / "deliverables" / "index.html").exists() == had and not (out / "build" / "build-all-last.json").exists()


# ---------------------------------------------------------------- FB-006: слияние частей схем
def test_flows_merge_and_duplicate_keys(tmp_path):
    out = tmp_path / "f"
    write(out / "build" / "parts" / "flows-1.json", [{"key": "user-journey", "title": "Путь", "svg": "charts/flows/user-journey.svg", "nodes": []}])
    write(out / "build" / "parts" / "flows-2.json", [{"key": "architecture", "title": "Архитектура", "svg": "x.svg", "nodes": []}])
    write(out / "data" / "flows-plan.json", [{"key": "user-journey"}, {"key": "architecture"}, {"key": "experiment-tree"}])
    code, line = build_all.merge_flows(out)
    assert code == 0 and "схем слито: 2" in line and "нет схем из плана: experiment-tree" in line
    assert [f["key"] for f in jload(out / "data" / "flows.json")] == ["user-journey", "architecture"]
    write(out / "build" / "parts" / "flows-3.json", [{"key": "architecture", "title": "дубль", "svg": "y.svg", "nodes": []}])
    code, line = build_all.merge_flows(out)
    assert code == 1 and "дубли ключей схем: architecture" in line


# ---------------------------------------------------------------- FB-018: PDF
def make_pdf(pages):
    """Минимальный PDF: pages — список строк содержимого (b"" — пустая страница)."""
    objs, kids = [], []
    n = 3
    for content in pages:
        stream = zlib.compress(content)
        objs.append((n, b"<< /Type /Page /Parent 2 0 R /Contents %d 0 R >>" % (n + 1)))
        objs.append((n + 1, b"<< /Length %d /Filter /FlateDecode >>\nstream\n" % len(stream) + stream + b"\nendstream"))
        kids.append(b"%d 0 R" % n)
        n += 2
    body = b"%PDF-1.4\n1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n"
    body += b"2 0 obj << /Type /Pages /Kids [" + b" ".join(kids) + b"] /Count %d >> endobj\n" % len(pages)
    for i, o in objs:
        body += b"%d 0 obj " % i + o + b" endobj\n"
    return body + b"%%EOF\n"


def test_pdf_pages_and_empty_detection(tmp_path):
    data = make_pdf([b"BT /F1 12 Tf 72 700 Td (Hello) Tj ET", b"", b"q 1 0 0 1 0 0 cm /Im1 Do Q"])
    n, empty = build_all.pdf_pages(data)
    assert n == 3 and empty == [2]
    out = tmp_path / "p"
    write(out / "deliverables" / "strategy.pdf", "")
    (out / "deliverables" / "strategy.pdf").write_bytes(data)
    code, line = build_all.check_pdf(out)
    assert code == 1 and line.startswith("PDF: 3 страниц, пустых 1, обрезанных") and "превью:" in line and "пустые: 2" in line
    (out / "deliverables" / "strategy.pdf").write_bytes(make_pdf([b"BT (a) Tj ET"]))
    assert build_all.check_pdf(out)[0] == 0


# ---------------------------------------------------------------- FB-016: REPORT и README из данных
def test_report_generator_sections_check_and_manual_edits(tmp_path):
    out = tmp_path / "cdemo"
    assert run("make_concept_demo.py", out, "--proposals", "50").returncode == 0
    write(out / "build" / "interventions.jsonl", json.dumps({"ts": "2026-10-19T10:00:00", "by": "owner", "what": "правка", "why": "проверка",
                                                             "file": "build/model-params.json", "kind": "data-edit"}, ensure_ascii=False) + "\n")
    r = run("report.py", out)
    assert r.returncode == 0 and "разделов 21" in r.stdout
    text = (out / "deliverables" / "REPORT.md").read_text(encoding="utf-8")
    heads = [h for h in report.template_headings()]
    assert all(h in text for h in heads) and len(heads) == 21
    assert "концепция продукта Книжная полка" in text and "Светофор жизнеспособности" in text and "владелец 1" in text
    assert str(tmp_path) not in text
    assert run("report.py", out, "--check").returncode == 1                                 # есть места «<заполнить»
    filled = text.replace("<заполнить", "заполнено")
    (out / "deliverables" / "REPORT.md").write_text(filled, encoding="utf-8")
    r = run("report.py", out, "--check")
    assert r.returncode == 0, r.stdout
    r = run("report.py", out)                                                                # правленный вручную не затирается
    assert "не затирается" in r.stdout and (out / "deliverables" / "REPORT.generated.md").exists()
    assert (out / "deliverables" / "REPORT.md").read_text(encoding="utf-8") == filled
    r = run("report.py", out, "--readme")
    rd = (out / "deliverables" / "README.md").read_text(encoding="utf-8")
    assert r.returncode == 0 and rd.startswith("# Концепция продукта Книжная полка") and "{PRODUCT}" not in rd


def test_report_respects_disclosure_none(tmp_path):
    out = tmp_path / "cdemo"
    assert run("make_concept_demo.py", out, "--proposals", "50").returncode == 0
    cfg = jload(out / "build" / "run-config.json")
    cfg["disclosure"] = "none"
    write(out / "build" / "run-config.json", cfg)
    run("report.py", out, "--force")
    text = (out / "deliverables" / "REPORT.md").read_text(encoding="utf-8")
    assert "## 11. Использованные инструменты\n" in text and "токен" not in text.lower() and "TypeSafe" not in text and "субагент" not in text
    assert report.check_report(out)["missing_sections"] == []
