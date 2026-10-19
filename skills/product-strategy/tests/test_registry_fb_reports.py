"""1.5, WP-C: отчёты агентов — второй раунд зависимостей (FB-051), fact-check → исправление источников (FB-052),
ретроспектива и журнал вмешательств (FB-004, сторона collect_reports.py --retro).

Запуск: python3 -m pytest skills/product-strategy/tests/test_registry_fb_reports.py -q
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_pipeline import jdump, jload, make_out, run  # noqa: E402
from test_registry2 import regs  # noqa: E402

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import apply_fact_check as afc  # noqa: E402
import collect_reports as cr  # noqa: E402

# пары из фидбэка ARC Raiders (FB-051), перенумерованные на маленький реестр
AUTHOR_A = """# Отчёт автора разделов 9–10
1. Итог: разделы написаны.
2. Зависимости, которых нет в реестре:
- ПРЕДПОСЫЛКА: P008 ← P003, P011 | синк без аккаунта не работает
- **ПРЕДПОСЫЛКА: P005 ← P013, P009, P003** | нужен каталог
ПРЕДПОСЫЛКА: P010 <- P013 | шаг «флаг Pro»
"""
AUTHOR_B = """# Отчёт автора раздела 14
- ПРЕДПОСЫЛКА: P006 ← P013, P011 | почему
- ПРЕДПОСЫЛКА: P012 ← P014 | почему
- ПРЕДПОСЫЛКА: P001 ← P002 | уже записано
- ПРЕДПОСЫЛКА: P002 ← P004 | замкнёт цикл
- ПРЕДПОСЫЛКА: P007 ← P099 | нет такого
"""


def reg_out(tmp_path):
    props = regs(14, ["product", "analytics"])
    props[0]["dependencies"] = ["P002"]
    props[3]["dependencies"] = ["P001"]                                      # P004 → P001 → P002: P002 ← P004 замкнёт цикл
    out = make_out(tmp_path, props, {"strategy": {"proposals_min": 1}})
    rep = out / "build" / "agent-reports"
    rep.mkdir(parents=True)
    (rep / "strategy-section-3.md").write_text(AUTHOR_A, encoding="utf-8")
    (rep / "strategy-section-5.md").write_text(AUTHOR_B, encoding="utf-8")
    return out


def test_second_round_dependencies_from_author_reports(tmp_path):
    out = reg_out(tmp_path)
    assert run("score.py", out).returncode == 0
    cp_before = jload(out / "data" / "critical-path.json")
    r = run("collect_reports.py", out, "--deps", "--into-overrides")
    assert r.returncode == 0, r.stdout + r.stderr
    patch = jload(out / "build" / "deps-patch.json")
    expected = {"P008": ["P003", "P011"], "P005": ["P013", "P009", "P003"], "P010": ["P013"], "P006": ["P013", "P011"], "P012": ["P014"]}
    assert {k: v["_add"]["dependencies"] for k, v in patch.items() if not k.startswith("_")} == expected
    s = patch["_summary"]
    assert s["added"] == 9 and s["lines"] == 8
    why = {x["pair"]: x["why"] for x in s["skipped"]}
    assert why["P001 ← P002"] == "уже записано" and why["P002 ← P004"].startswith("замкнёт цикл") and "P099" in why["P007 ← P099"]
    assert patch["_reasons"]["P008"][0]["where"].endswith(":4")
    a = run("merge_proposals.py", out, "--apply-overrides", out / "build" / "deps-patch.json")
    assert a.returncode == 0, a.stdout
    P = {p["id"]: p for p in jload(out / "data" / "proposals.json")}
    for pid, deps in expected.items():
        assert all(d in P[pid]["dependencies"] for d in deps), (pid, P[pid]["dependencies"])
    assert P["P001"]["dependencies"] == ["P002"]                             # без повторов
    assert run("score.py", out).returncode == 0                              # критический путь пересчитан
    cp_after = jload(out / "data" / "critical-path.json")
    assert len(cp_after["edges"]) > len(cp_before["edges"])
    ov = jload(out / "build" / "overrides.json")                             # переживёт полное слияние
    assert ov["P005"]["_add"]["dependencies"] == ["P013", "P009", "P003"]


def test_parse_prereqs_variants():
    rows = cr.parse_prereqs("* PREREQ: P038 <- P033 and P111 | why\n- предпосылка: P001 ← P002\nтекст P003 ← P004 без метки\n")
    assert [(r["id"], r["prereqs"]) for r in rows] == [("P038", ["P033", "P111"]), ("P001", ["P002"])]


# ---------------------------------------------------------------- FB-052
COMPETITORS = [{"slug": "self", "name": "Трекер", "self": True, "features": {}},
               {"slug": "metaforge", "name": "MetaForge", "price": "тарифы не обнаружены", "monetization": "нет",
                "features": {"premium": False, "sync": True}, "sources": ["https://metaforge.app"]}]


def test_fact_check_fix_applies_to_sources(tmp_path):
    out = make_out(tmp_path, regs(2, ["product"]), {"strategy": {"proposals_min": 1}})
    jdump(out / "data" / "competitors.json", COMPETITORS)
    jdump(out / "build" / "model-params.json", {"price_month": {"value": 199, "label": "допущение", "note": ""}})
    rep_dir = out / "build" / "agent-reports"
    rep_dir.mkdir(parents=True)
    (rep_dir / "strategy-section-3.md").write_text(
        "## Расхождения с фактами\n- MetaForge премиум — нет (competitors.json) — Premium $2,99/$4,99/$9,99 — https://metaforge.app/pricing\n",
        encoding="utf-8")
    r = run("collect_reports.py", out, "--fact-check")
    assert r.returncode == 0, r.stdout + r.stderr
    fc = jload(out / "data" / "fact-check.json")
    assert fc[0]["applied"] is False and fc[0]["fix"] is None
    assert fc[0]["fix_hint"] == {"file": "data/competitors.json", "select": "[slug=metaforge]", "fields": ["price", "monetization", "features"]}
    # подтверждено, но не исправлено — --check падает (ворота build_all --strict)
    fc[0]["resolved_value"] = "Premium $2,99 / $4,99 / $9,99"
    jdump(out / "data" / "fact-check.json", fc)
    c = run("apply_fact_check.py", out, "--check")
    assert c.returncode == 1 and "нет fix" in c.stdout
    fc[0]["fix"] = [{"file": "data/competitors.json", "path": "[slug=metaforge].price", "value": "Premium $2,99 / $4,99 / $9,99"},
                    {"file": "data/competitors.json", "path": "[slug=metaforge].features.premium", "value": True},
                    {"file": "data/competitors.json", "path": "[slug=metaforge].sources", "value": "https://metaforge.app/pricing", "op": "append"}]
    fc.append({"fact": "формулировка в разделе 3", "resolved_value": "уточнено", "text_only": True})
    fc.append({"fact": "не подтверждено", "resolved_value": None})
    jdump(out / "data" / "fact-check.json", fc)
    assert run("apply_fact_check.py", out, "--check").returncode == 1
    a = run("apply_fact_check.py", out)
    assert a.returncode == 0, a.stdout
    mf = jload(out / "data" / "competitors.json")[1]
    assert mf["price"].startswith("Premium") and mf["features"]["premium"] is True and mf["sources"][-1].endswith("/pricing")
    fc2 = jload(out / "data" / "fact-check.json")
    assert fc2[0]["applied"] is True and fc2[0]["previous"][0] == "тарифы не обнаружены"
    c = run("apply_fact_check.py", out, "--check")
    assert c.returncode == 0 and "не подтверждено" in c.stdout                # записей без applied нет; неподтверждённая — предупреждение
    assert run("apply_fact_check.py", out).returncode == 0                   # повторный запуск идемпотентен
    assert jload(out / "data" / "competitors.json")[1]["sources"].count("https://metaforge.app/pricing") == 1


def test_apply_fix_paths_and_safety(tmp_path):
    doc = {"items": [{"id": "a", "v": 1}, {"id": "b", "v": 2}], "x": {"y": 1}}
    assert afc.apply_fix(doc, {"path": "items[id=b].v", "value": 5}) == 2 and doc["items"][1]["v"] == 5
    assert afc.apply_fix(doc, {"path": "items.0.v", "value": 7}) == 1
    afc.apply_fix(doc, {"path": "x", "value": {"z": 2}, "op": "merge"})
    assert doc["x"] == {"y": 1, "z": 2}
    afc.apply_fix(doc, {"path": "x.y", "op": "delete"})
    assert doc["x"] == {"z": 2}
    for bad in ({"path": "items[id=zz].v", "value": 1}, {"path": "nope.v", "value": 1}):
        try:
            afc.apply_fix(doc, bad)
            assert False, bad
        except ValueError:
            pass
    out = make_out(tmp_path, regs(1, ["product"]))
    jdump(out / "data" / "fact-check.json", [{"fact": "x", "fix": {"file": "../outside.json", "path": "a", "value": 1}}])
    r = run("apply_fact_check.py", out)
    assert r.returncode == 1 and "вне папки прогона" in r.stdout


# ---------------------------------------------------------------- FB-004
def test_retro_collects_journal_auto_detected_and_deviations(tmp_path):
    out = make_out(tmp_path, regs(2, ["product"]), {"strategy": {"proposals_min": 1}, "product": {"name": "Трекер"}})
    b = out / "build"
    (b / "briefs").mkdir(parents=True)
    (b / "briefs" / "registry-generator-G1.md").write_text("# Бриф", encoding="utf-8")     # по шаблону
    (b / "briefs" / "tech-integration.md").write_text("# Свой бриф", encoding="utf-8")      # ручной
    (b / "briefs" / "research-owner-notes.md").write_text("# Свой бриф 2", encoding="utf-8")
    jdump(b / "overrides.json", {"_comment": "x", "P001": {"description": "короче"}})
    jdump(b / "model-params.json", {"price_month": {"value": 299, "label": "факт", "note": "ЮKassa"},
                                    "churn": {"value": 0.1, "label": "допущение", "note": ""}})
    jdump(b / "merge-map.json", {"distinct": [["G1-01", "G2-01"]]})
    journal = [{"ts": "2026-10-19T10:00", "by": "owner", "what": "решение: 3D — v2", "why": "бюджет", "file": "data/decisions.json"},
               {"ts": "2026-10-19T11:00", "by": "orchestrator", "what": "написан бриф интеграции", "why": "шаблона нет",
                "file": "build/briefs/tech-integration.md", "phase": "C4"}]
    (b / "interventions.jsonl").write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in journal) + "\n", encoding="utf-8")
    rep = b / "agent-reports"
    rep.mkdir()
    (rep / "mockups-1.md").write_text("# Отчёт\n## Отступления от брифа\n- писал временный скрипт в build/tmp/mockups-1/\n"
                                      "## Расхождения с фактами\nнет\n", encoding="utf-8")
    (rep / "flows-2.md").write_text("1. Итог\n2. Отступления от брифа: нет\n", encoding="utf-8")
    jdump(b / "build-all-last.json", {"date": "2026-10-19 22:59", "summary": "упали шаги: smoke",
                                      "steps": [{"step": "smoke", "status": "FAIL", "note": "lightbox"},
                                                {"step": "registry", "status": "OK", "note": "OK"}]})
    jdump(out / "data" / "fact-check.json", [{"fact": "цена", "resolved_value": "1", "applied": True},
                                             {"fact": "премиум", "resolved_value": "да"}])
    r = run("collect_reports.py", out, "--retro")
    assert r.returncode == 0, r.stdout + r.stderr
    doc = jload(b / "retro.json")
    whats = [e["what"] for e in doc["entries"]]
    # запись на каждый ручной бриф, правку model-params.json и overrides.json; бриф из журнала не дублируется
    assert sum("tech-integration" in e["what"] + e["file"] for e in doc["entries"]) == 1
    assert any("research-owner-notes.md" in w for w in whats)
    assert not any("registry-generator-G1" in w for w in whats)
    assert any("overrides.json" in w and "P001" in w for w in whats)
    assert any("model-params.json" in w and "price_month" in w for w in whats)
    assert any("merge-map.json" in w for w in whats)
    assert doc["by_owner"] == 1 and doc["by_orchestrator"] >= 4
    assert [d["agent"] for d in doc["deviations"]] == ["mockups-1"]
    assert doc["gates"] == [{"step": "smoke", "status": "FAIL", "note": "lightbox"}]
    assert doc["fact_check_open"] == ["премиум"]
    md = (b / "retro.md").read_text(encoding="utf-8")
    for h in ("# Ретроспектива прогона — Трекер", "## 1. Что добавил или решил владелец (by: owner)",
              "## 2. Что оркестратор делал вне скилла (by: orchestrator)", "## 3. Отступления агентов от брифов",
              "## 4. Дефекты скриптов и предупреждения ворот", "решение: 3D — v2", "smoke — FAIL"):
        assert h in md, h
