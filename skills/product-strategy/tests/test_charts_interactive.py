"""Интерактивные графики (references/interactive-site.md, п. 2.1–2.2): разметка SVG и charts/<ключ>.meta.json.

Демо-прогоны make_demo.py и make_concept_demo.py (временные папки) → check_registry → score → model → charts:
100 % покрытие элементов пояснениями, уникальные id, атрибуты доступности, кириллица в aria-label, валидный XML,
howto/legend у каждого графика, все ссылки разрешаются (проверка написана независимо от chart_meta.check_meta),
глубокие ссылки, режим идеи, приоритет data/chart-notes.json, ловля ошибок `charts.py --check-meta`.
Запуск: python3 -m pytest skills/product-strategy/tests/test_charts_interactive.py -q
"""
import json
import os
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

SKILL = Path(__file__).resolve().parent.parent
SCRIPTS = SKILL / "scripts"
GLOSSARY = SKILL / "references" / "chart-glossary.ru.json"
NS = "{http://www.w3.org/2000/svg}"
CYR = re.compile(r"[А-Яа-яЁё]")
ALL_KEYS = {"effort-impact", "bubble", "metrics-heatmap", "radar-top10", "pareto", "tornado", "dist-category", "dist-evidence",
            "dist-horizon", "gantt", "funnel", "forecast-fan", "cac-ltv", "payback", "keywords-volume", "events-calendar",
            "competitors-heatmap", "critical-path", "channel-mix", "kpi-tree", "keywords-clusters"}


def run(script, *args):
    e = {k: v for k, v in os.environ.items() if not k.startswith("TYPESAFE_")}
    return subprocess.run([sys.executable, str(SCRIPTS / script)] + [str(a) for a in args],
                          capture_output=True, text=True, env=e, timeout=300)


def jload(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def build(out, maker):
    r = run(maker, out)
    assert r.returncode == 0, r.stdout + r.stderr
    for cmd in (("check_registry.py", out, "--demo"), ("score.py", out), ("model.py", out)):
        run(*cmd)
    r = run("charts.py", out)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "Проверка пояснений графиков: ок" in r.stdout, r.stdout
    return out


@pytest.fixture(scope="module")
def demos(tmp_path_factory):
    base = tmp_path_factory.mktemp("charts-interactive")
    return {"product": build(base / "demo", "make_demo.py"), "concept": build(base / "concept", "make_concept_demo.py")}


@pytest.fixture
def demo_copy(demos, tmp_path):
    dst = tmp_path / "demo"
    shutil.copytree(demos["product"], dst)
    return dst


# ---------------------------------------------------------------- независимая проверка ссылок
def targets(out):
    """Множества существующих целей ссылок по данным прогона (без chart_meta)."""
    t = {"p": {p["id"] for p in jload(out / "data" / "proposals.json")},
         "gantt": {str(g["id"]) for g in jload(out / "data" / "gantt.json")},
         "competitor": {c["slug"] for c in jload(out / "data" / "competitors.json") if c.get("slug")},
         "kanban": {c["id"] for c in jload(out / "data" / "kanban.json")["cards"]},
         "mockup": {m["key"] for m in jload(out / "data" / "mockups-index.json")},
         "flow": {f["key"] for f in jload(out / "data" / "flows.json")}, "chart": {}}
    for e in jload(out / "charts" / "charts-index.json"):
        t["chart"][e["key"]] = set(jload(out / e["meta"])["elements"])
    return t


def resolves(href, t):
    m = re.fullmatch(r"#s(\d+)", href)
    if m:
        return 1 <= int(m.group(1)) <= 17
    m = re.fullmatch(r"#(p|gantt|competitor|kanban|mockup|flow)/(.+)", href)
    if m:
        return m.group(2) in t[m.group(1)]
    m = re.fullmatch(r"#chart/([\w-]+)/(.+)", href)
    if m:
        return m.group(2) in t["chart"].get(m.group(1), set())
    m = re.fullmatch(r"#registry\?(.+)", href)
    if m:
        return all(re.fullmatch(r"(category|horizon|class|quadrant|priority)=[\w-]+", x) for x in m.group(1).split("&"))
    return False


def svg_els(path):
    root = ET.parse(str(path)).getroot()          # валидный XML — иначе ParseError
    return root, [n for n in root.iter() if "data-ps-el" in n.attrib]


# ---------------------------------------------------------------- покрытие, атрибуты, ссылки
@pytest.mark.parametrize("mode", ["product", "concept"])
def test_full_coverage_and_links(demos, mode):
    out = demos[mode]
    idx = jload(out / "charts" / "charts-index.json")
    assert {e["key"] for e in idx} == ALL_KEYS
    t = targets(out)
    total = 0
    for e in idx:
        key = e["key"]
        assert e["meta"] == "charts/%s.meta.json" % key and set(e) >= {"key", "svg", "title", "caption", "section", "meta"}
        meta = jload(out / e["meta"])
        root, els = svg_els(out / e["svg"])
        assert root.attrib.get("data-ps-chart") == key and root.attrib.get("role") == "group"
        assert root.find(NS + "title").text and root.find(NS + "desc") is not None
        ids = [n.attrib["data-ps-el"] for n in els]
        assert ids and len(ids) == len(set(ids)), key                          # уникальность id
        assert set(ids) == set(meta["elements"]), key                          # 100 % покрытие в обе стороны
        for n in els:
            a = n.attrib
            assert a["tabindex"] == "0" and a["role"] == "button" and "ps-el" in a["class"].split(), (key, a)
            assert CYR.search(a["aria-label"]), (key, a["aria-label"])        # подписи по-русски
            assert n.find(NS + "title") is not None and n.find(NS + "title").text == a["aria-label"]
        assert meta["key"] == key and meta["howto"].strip() and meta["legend"], key
        assert all(x["label"] and x["text"] for x in meta["legend"])
        assert meta["mode"] == mode and not meta["warnings"], (key, meta["warnings"])
        for eid, m in meta["elements"].items():
            assert m["title"] and m["summary"], (key, eid)                     # «пояснение не задано» — нет
            assert m["kind"] in {"stage", "point", "bar", "node", "cell", "event", "link", "legend", "axis", "area", "line", "row", "column", "shape"}
            assert len(m["actions"]) <= 4 and all(isinstance(x, str) and x for x in m["actions"])
            for x in m["metrics"]:
                assert x["label"] and "value" in x and x.get("tag"), (key, eid, x)
            for l in m["links"]:
                assert l["label"] and resolves(l["href"], t), (key, eid, l)
            if m.get("highlight"):
                assert any(m["highlight"] in (n.attrib.get("data-ps-group") or "").split() for n in root.iter()), (key, eid)
        for l in meta["links"]:
            assert resolves(l["href"], t)
        total += len(ids)
        assert "…" not in (out / e["svg"]).read_text(encoding="utf-8")
    assert total > 500


def test_expected_elements_and_kinds(demos):
    out = demos["product"]
    meta = {e["key"]: jload(out / e["meta"]) for e in jload(out / "charts" / "charts-index.json")}
    S = jload(out / "data" / "scores.json")
    ei = meta["effort-impact"]["elements"]
    assert {s["id"] for s in S} <= set(ei)                                    # каждая точка — элемент
    assert {"quad-quick_win", "quad-big_bet", "quad-filler", "quad-money_pit", "axis-x", "axis-y"} <= set(ei)
    assert any(k.startswith("legend-cat-") for k in ei) and ei["legend-cat-product"]["kind"] == "legend"
    assert ei["legend-cat-product"]["highlight"] == "g-cat-product"
    fu = meta["funnel"]["elements"]
    assert {"stage-acquisition", "stage-activation", "stage-retention", "stage-revenue", "stage-referral"} <= set(fu)
    assert fu["stage-activation"]["kind"] == "stage" and {"#s7"} <= {l["href"] for l in fu["stage-activation"]["links"]}
    assert all(x["tag"] == "допущение" for x in fu["stage-revenue"]["metrics"])
    kt = meta["kpi-tree"]["elements"]
    assert "kpi-north-star" in kt and any(k.startswith("kpi-") and k != "kpi-north-star" for k in kt)
    cp = jload(out / "data" / "critical-path.json")
    ce = meta["critical-path"]["elements"]
    assert all("edge-%s-%s" % tuple(e) in ce for e in cp["edges"]) and set(cp["order"]) <= set(ce)
    assert ce["edge-%s-%s" % tuple(cp["edges"][0])]["kind"] == "link"
    G = jload(out / "data" / "gantt.json")
    assert {g["id"] for g in G} <= set(meta["gantt"]["elements"])
    assert "competitor-self" in meta["competitors-heatmap"]["elements"]
    assert any(k.startswith("cell-") for k in meta["competitors-heatmap"]["elements"])
    assert {"class-A", "class-D"} <= set(meta["dist-evidence"]["elements"])
    assert "horizon-now" in meta["dist-horizon"]["elements"]
    assert any(k.startswith("param-") for k in meta["tornado"]["elements"])
    assert {"scen-base", "band"} <= set(meta["forecast-fan"]["elements"])
    assert {"cac-base", "ltv-base", "legend-cac"} <= set(meta["cac-ltv"]["elements"])
    assert any(k.startswith("ev-") for k in meta["events-calendar"]["elements"])
    assert any(k.startswith("cluster-") for k in meta["keywords-clusters"]["elements"])
    for k, m in meta.items():   # каждый график — с пояснением «как читать» из глоссария
        assert len(m["howto"]) > 80, k


def test_proposal_explanation_from_data(demos):
    out = demos["product"]
    P = {p["id"]: p for p in jload(out / "data" / "proposals.json")}
    S = jload(out / "data" / "scores.json")
    pid = S[0]["id"]
    m = jload(out / "charts" / "effort-impact.meta.json")["elements"][pid]
    p = P[pid]
    assert m["title"] == "%s — %s" % (pid, p["title"]) and m["kind"] == "point"
    assert m["summary"] == p["description"]
    assert p["rationale"] in m["meaning"] and "Квадрант" in m["meaning"]
    assert any(p["steps"][0]["what"] in a for a in m["actions"])
    labels = {x["label"] for x in m["metrics"]}
    assert {"Ранг по composite", "Ценность (1–5)", "Стоимость (1–5)"} <= labels
    assert any(x["label"] == "Эффект: " + p["effect_kpi"][0]["kpi"] and x["tag"] == p["effect_kpi"][0]["label"] for x in m["metrics"])
    hrefs = [l["href"] for l in m["links"]]
    sec = {"acquisition": 6, "conversion": 7, "monetization": 8, "retention": 9, "product": 10, "platform": 11, "analytics": 12}.get(p["category"])
    assert "#p/" + pid in hrefs and "#registry?category=" + p["category"] in hrefs
    if sec:
        assert "#s%d" % sec in hrefs
    assert "data" in m["sources"]


def test_deep_links_between_charts(demos):
    out = demos["product"]
    heat = jload(out / "charts" / "metrics-heatmap.meta.json")["elements"]
    S = jload(out / "data" / "scores.json")
    cell = heat["cell-%s-value_index" % S[0]["id"]]
    assert "#chart/effort-impact/%s" % S[0]["id"] in [l["href"] for l in cell["links"]]
    cp = jload(out / "data" / "critical-path.json")
    node = jload(out / "charts" / "critical-path.meta.json")["elements"][cp["order"][0]]
    assert "#chart/effort-impact/%s" % cp["order"][0] in [l["href"] for l in node["links"]]
    deep = [l["href"] for e in jload(out / "charts" / "charts-index.json")
            for m in jload(out / e["meta"])["elements"].values() for l in m["links"] if l["href"].startswith("#chart/")]
    assert len(deep) > 30


def test_concept_mode_texts(demos):
    out = demos["concept"]
    fu = jload(out / "charts" / "funnel.meta.json")
    assert fu["mode"] == "concept" and "Продукта ещё нет" in fu["howto"]
    st = fu["elements"]["stage-activation"]
    assert "Продукта ещё нет" in st["summary"] and "прототип" in " ".join(st["actions"])
    assert "#s7" in [l["href"] for l in st["links"]]
    assert any("Первый опыт" in l["label"] for l in st["links"])       # названия разделов — по concept-outline.md
    co = jload(out / "charts" / "competitors-heatmap.meta.json")
    assert "планируемая идея" in co["howto"]
    assert "замысел" in co["elements"]["competitor-self"]["summary"]
    assert jload(out / "charts" / "cac-ltv.meta.json")["elements"].get("panel-hpa")   # профиль нулевого бюджета


def test_glossary_is_complete():
    g = jload(GLOSSARY)
    assert set(map(str, range(1, 18))) == set(g["sections"]) == set(g["sections_concept"])
    for k in ALL_KEYS:
        c = g["charts"][k]
        assert len(c["howto"]) > 80 and c["legend"] and all(1 <= n <= 17 for n in c["sections"]), k
    for st in ("acquisition", "activation", "retention", "revenue", "referral"):
        e = g["stages"][st]
        assert e["summary"] and e["meaning"] and len(e["actions"]) >= 2 and e["concept"]["summary"], st
    assert set(g["quadrants"]) == {"quick_win", "big_bet", "filler", "money_pit"}
    assert set(g["evidence"]) == set("ABCD")
    assert {"rice", "ice", "wsjf", "composite", "value_index", "confidence_calc"} <= set(g["metrics"])
    assert {"tornado", "critical_path", "north_star", "cac", "ltv", "payback"} <= set(g["terms"])
    for cat, n in g["category_sections"].items():
        assert 1 <= n <= 17 and cat in g["categories"]


# ---------------------------------------------------------------- заметки и проверка сборщика
def test_chart_notes_override_and_generic_list(demo_copy):
    out = demo_copy
    pid = jload(out / "data" / "scores.json")[0]["id"]
    notes = {"effort-impact": {"_chart": {"howto": "Свой текст «как читать» от автора."},
                               pid: {"summary": "Авторское пояснение элемента.", "actions": ["Сделать первое", "Сделать второе"],
                                     "links": [{"label": "Битая", "href": "#p/P999"}, {"label": "Раздел 6", "href": "#s6"}]},
                               "axis-x": {"meaning": "Авторский смысл оси."}}}
    (out / "data" / "chart-notes.json").write_text(json.dumps(notes, ensure_ascii=False), encoding="utf-8")
    r = run("charts.py", out, "--only", "effort-impact")
    assert r.returncode == 0, r.stdout
    assert "chart-notes: ссылка без цели пропущена" in r.stdout and "#p/P999" in r.stdout
    meta = jload(out / "charts" / "effort-impact.meta.json")
    assert meta["howto"] == "Свой текст «как читать» от автора."
    el = meta["elements"][pid]
    assert el["summary"] == "Авторское пояснение элемента." and el["actions"] == ["Сделать первое", "Сделать второе"]
    hrefs = [l["href"] for l in el["links"]]
    assert "#s6" in hrefs and "#p/P999" not in hrefs and el["sources"][0] == "notes"
    assert meta["elements"]["axis-x"]["meaning"] == "Авторский смысл оси."
    assert "axis-x" not in meta["generic"]
    gen = json.loads(run("charts.py", out, "--list-generic").stdout)
    assert gen and all({"chart", "id", "title", "reason"} <= set(x) for x in gen)
    assert any(x["chart"] == "bubble" and x["id"] == "axis-x" for x in gen)
    assert not any(x["chart"] == "effort-impact" and x["id"] == "axis-x" for x in gen)
    assert run("charts.py", out, "--check-meta").returncode == 0


def test_check_meta_detects_problems(demo_copy):
    out = demo_copy
    assert run("charts.py", out, "--check-meta").returncode == 0
    mp = out / "charts" / "funnel.meta.json"
    good = mp.read_text(encoding="utf-8")
    meta = json.loads(good)
    meta["elements"]["stage-activation"]["links"].append({"label": "вне", "href": "#s18"})
    meta["elements"]["stage-retention"]["links"].append({"label": "нет такого", "href": "#p/P999"})
    meta["elements"].pop("stage-referral")
    meta["elements"]["ghost"] = {"title": "призрак", "kind": "point", "summary": "x", "links": []}
    meta["howto"] = ""
    mp.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    r = run("charts.py", out, "--check-meta")
    assert r.returncode == 1
    for frag in ("#s18 — раздел вне 1…17", "#p/P999 — нет предложения", "funnel/stage-referral: элемент без записи",
                 "funnel/ghost: запись meta.elements без элемента", "funnel: нет howto"):
        assert frag in r.stdout, (frag, r.stdout)
    mp.write_text(good, encoding="utf-8")
    svg = out / "charts" / "bubble.svg"
    svg.write_text(svg.read_text(encoding="utf-8").replace('tabindex="0"', 'tabindex="-1"', 1), encoding="utf-8")
    r = run("charts.py", out, "--check-meta")
    assert r.returncode == 1 and "нет tabindex=0" in r.stdout


def test_only_keeps_other_meta(demo_copy):
    out = demo_copy
    before = {e["key"]: e for e in jload(out / "charts" / "charts-index.json")}
    (out / "data" / "north-star.json").write_text(json.dumps({"metric": "Еженедельно активные авторы"}, ensure_ascii=False), encoding="utf-8")
    r = run("charts.py", out, "--only", "kpi-tree")
    assert r.returncode == 0 and "ок" in r.stdout, r.stdout
    after = {e["key"]: e for e in jload(out / "charts" / "charts-index.json")}
    assert set(after) == set(before) and all(e.get("meta") for e in after.values())
    ns = jload(out / "charts" / "kpi-tree.meta.json")["elements"]["kpi-north-star"]
    assert "Еженедельно активные авторы" in ns["title"] and "Еженедельно активные авторы" in ns["summary"]


def test_empty_run_still_passes(tmp_path):
    r = run("charts.py", tmp_path)
    assert r.returncode == 0 and jload(tmp_path / "charts" / "charts-index.json") == []
    assert run("charts.py", tmp_path, "--check-meta").returncode == 0
