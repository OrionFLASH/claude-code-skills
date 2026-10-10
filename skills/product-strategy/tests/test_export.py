# -*- coding: utf-8 -*-
"""Экспорт product-strategy: build_xlsx.py, build_deck_json.py, check_links.py (без сети), node/build_pptx.mjs и
node/deck_pdf.mjs (пропускаются, если нет node или модулей). pytest tests/test_export.py

Node-тесты ищут модули в env PS_NODE_DIR, затем в scripts/node (папка с node_modules)."""
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import zipfile
import zlib
from pathlib import Path
from xml.dom import minidom

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import build_deck_json  # noqa: E402
import check_links  # noqa: E402

PY = [sys.executable, "-B"]
SLIDE_TYPES = {"title", "section", "bullets", "image", "stats", "table", "card"}


def run(*args, **kw):
    return subprocess.run(PY + [str(SCRIPTS / args[0])] + [str(x) for x in args[1:]], capture_output=True, text=True, timeout=300, **kw)


def png(path, w=320, h=200, rgb=(200, 210, 230)):
    raw = b"".join(b"\x00" + bytes(rgb) * w for _ in range(h))

    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
                     + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def make_demo(path, n=45):
    r = run("make_demo.py", path, "--proposals", n)
    assert r.returncode == 0, r.stderr
    return path


def augment(out):
    """Минимальные scores.json, weights.json, model.json, charts, PNG макетов и tokens.css по контракту."""
    props = json.loads((out / "data/proposals.json").read_text(encoding="utf-8"))
    order = list(reversed(props))  # ранги заведомо не совпадают с порядком реестра
    scores = [{"id": p["id"], "rank": i, "rice": 10.0 / i, "ice": 5.0, "wsjf": 2.0, "value_per_effort": 1.0, "risk_adjusted": 1.0,
               "confidence_calc": 0.7, "composite": round(1 - i / (len(order) + 1), 4), "quadrant": "quick_win",
               "priority": "P0" if i <= 5 else "P2", "moscow": "should", "labels": ["important"], "typesafe": None}
              for i, p in enumerate(order, 1)]
    (out / "data/scores.json").write_text(json.dumps(scores, ensure_ascii=False), encoding="utf-8")
    (out / "data/weights.json").write_text(json.dumps({"composite": {"rice": 0.4, "ice": 0.2, "wsjf": 0.2, "risk_adj": 0.2}}), encoding="utf-8")
    sc = {k: {"assumptions": {"visitors_month": v * 1000, "conv": 0.03}, "funnel": [{"stage": "visit", "value": v * 1000}],
              "monthly": [{"month": m, "users": v * m, "paying": m, "revenue": 9.0 * m, "cost": 100.0} for m in range(1, 13)],
              "cac": 10.0, "ltv": 30.0 * v, "payback_months": 3, "arpu": 9.0, "churn": 0.05, "roi": 0.5 * v}
          for k, v in (("pessimistic", 1), ("base", 2), ("optimistic", 3))}
    (out / "data/model.json").write_text(json.dumps({"scenarios": sc, "notes": ["[допущение] тест"]}, ensure_ascii=False), encoding="utf-8")
    charts = []
    for key in ("effort-impact", "pareto", "gantt"):
        (out / "charts").mkdir(exist_ok=True)
        (out / "charts" / f"{key}.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 225"><rect width="400" height="225" fill="#fff"/>'
                                                   '<rect x="40" y="60" width="60" height="120" fill="#2563eb"/></svg>', encoding="utf-8")
        charts.append({"key": key, "svg": f"charts/{key}.svg", "title": f"График {key}", "caption": "вывод", "section": "plan" if key == "gantt" else "scores"})
    (out / "charts/charts-index.json").write_text(json.dumps(charts, ensure_ascii=False), encoding="utf-8")
    for m in json.loads((out / "data/mockups-index.json").read_text(encoding="utf-8")):
        png(out / m["png"])
    png(out / "design-refs/01-demo.png")
    (out / "mockups/tokens.css").write_text(":root{--bg:#101820;--surface:#1c2530;--text:#eef2f6;--accent:#f5a623;--font:'Arial',sans-serif}", encoding="utf-8")
    return out


@pytest.fixture(scope="module")
def bare(tmp_path_factory):
    return make_demo(tmp_path_factory.mktemp("bare") / "out")


@pytest.fixture(scope="module")
def full(tmp_path_factory):
    return augment(make_demo(tmp_path_factory.mktemp("full") / "out"))


# ---------------------------------------------------------------- XLSX
def xlsx_parts(path):
    z = zipfile.ZipFile(path)
    for n in z.namelist():
        if n.endswith(".xml") or n.endswith(".rels"):
            minidom.parseString(z.read(n))  # каждая часть — валидный XML
    return z


def sheet_xml(z, name):
    wb = z.read("xl/workbook.xml").decode()
    names = re.findall(r'<sheet name="([^"]+)" sheetId="(\d+)"', wb)
    idx = [i for i, (n, _) in enumerate(names, 1) if n == name][0]
    return z.read(f"xl/worksheets/sheet{idx}.xml").decode()


def test_xlsx_structure_and_formulas(bare):
    r = run("build_xlsx.py", bare)
    assert r.returncode == 0, r.stderr
    path = bare / "deliverables/strategy.xlsx"
    z = xlsx_parts(path)
    for part in ("[Content_Types].xml", "xl/workbook.xml", "xl/styles.xml", "xl/sharedStrings.xml", "docProps/core.xml", "docProps/app.xml"):
        assert part in z.namelist()
    names = re.findall(r'<sheet name="([^"]+)"', z.read("xl/workbook.xml").decode())
    assert names == ["Реестр", "Оценки", "Модель", "Источники", "KPI", "Kanban", "Конкуренты", "Гант"]
    core = z.read("docProps/core.xml").decode()
    assert "<dc:creator>Демо Автор (demo)</dc:creator>" in core
    assert "Стратегия развития Demo App" in core and "©" in core
    scores = sheet_xml(z, "Оценки")
    for fn in ("SUMPRODUCT(", "RANK(", "MIN(", "MAX(", "SUM("):
        assert fn in scores, fn
    assert 'ySplit="6"' in scores and 'state="frozen"' in scores       # данные начинаются под блоком весов
    assert re.search(r'<c r="I3" s="3"><v>1\.0</v></c>', scores)          # редактируемый вес над колонкой value
    assert '<autoFilter ref="A6:' in scores
    assert 'r="A6"' in scores and 'r="A7"' in scores
    reg = sheet_xml(z, "Реестр")
    assert '<autoFilter ref="A1:' in reg and "<cols>" in reg
    assert reg.count("<row ") == 46                                      # заголовок + 45 предложений
    assert "model.json" in z.read("xl/sharedStrings.xml").decode()         # лист «Модель» объясняет, чего не хватает
    gantt = sheet_xml(z, "Гант")
    assert 's="7"' in gantt                                               # полосы Ганта закрашены


def test_xlsx_uses_scores_and_model(full):
    r = run("build_xlsx.py", full)
    assert r.returncode == 0, r.stderr
    z = xlsx_parts(full / "deliverables/strategy.xlsx")
    ss = z.read("xl/sharedStrings.xml").decode()
    assert "Базовый" in ss and "LTV/CAC (формула)" in ss
    model = sheet_xml(z, "Модель")
    assert "<f>SUM(" in model and "<f>IF(AND(ISNUMBER(" in model
    scores = sheet_xml(z, "Оценки")
    assert "data/weights.json" in ss
    assert re.search(r'<c r="AC3" s="3"><v>0\.4</v></c>', scores)          # вес RICE из weights.json над n_RICE
    # реестр отсортирован по рангу scores.json: первым идёт последний по id
    strings = re.findall(r"<si><t[^>]*>(.*?)</t></si>", ss)
    reg = sheet_xml(z, "Реестр")
    first_id = re.search(r'<c r="B2"(?: s="\d+")? t="s"><v>(\d+)</v>', reg).group(1)
    assert strings[int(first_id)] == "P045"


def test_xlsx_opens_in_openpyxl(full):
    openpyxl = pytest.importorskip("openpyxl")
    path = full / "deliverables/strategy.xlsx"
    if not path.exists():
        assert run("build_xlsx.py", full).returncode == 0
    wb = openpyxl.load_workbook(path)
    assert wb.sheetnames[:2] == ["Реестр", "Оценки"]
    assert wb.properties.creator == "Демо Автор (demo)"
    ws = wb["Оценки"]
    assert ws.freeze_panes == "C7"
    assert ws.cell(row=6, column=1).value == "ID"
    assert str(ws["AH7"].value).startswith("=RANK(")
    assert wb["Реестр"].auto_filter.ref.startswith("A1:")


@pytest.fixture(scope="module")
def tracked_xlsx(tmp_path_factory, full):
    out = tmp_path_factory.mktemp("trk") / "out"
    shutil.copytree(full, out)
    r = run("make_progress_demo.py", out)
    assert r.returncode == 0, r.stderr
    r = run("build_xlsx.py", out)
    assert r.returncode == 0, r.stderr
    return out


def cells(xml):
    """{адрес: (стиль, формула|None, значение|None)} из листа (без разбора sharedStrings)."""
    out = {}
    for m in re.finditer(r'<c r="([A-Z]+\d+)"(?: s="(\d+)")?(?: t="(\w+)")?>(.*?)</c>', xml):
        f = re.search(r"<f>(.*?)</f>", m.group(4))
        v = re.search(r"<v>(.*?)</v>", m.group(4))
        out[m.group(1)] = (int(m.group(2) or 0), f.group(1) if f else None, v.group(1) if v else None, m.group(3))
    return out


def test_xlsx_progress_sheet(tracked_xlsx):
    z = xlsx_parts(tracked_xlsx / "deliverables/strategy.xlsx")
    names = re.findall(r'<sheet name="([^"]+)"', z.read("xl/workbook.xml").decode())
    assert names == ["Реестр", "Оценки", "Модель", "Источники", "KPI", "Kanban", "Конкуренты", "Гант", "Прогресс", "Таймлайн"]
    pg = json.loads((tracked_xlsx / "data/progress.json").read_text(encoding="utf-8"))
    n = len(pg["items"])
    xml = sheet_xml(z, "Прогресс")
    c = cells(xml)
    strings = re.findall(r"<si><t[^>]*>(.*?)</t></si>", z.read("xl/sharedStrings.xml").decode(), re.S)   # строки с переводами строк
    sv = lambda a: strings[int(c[a][2])] if a in c and c[a][3] == "s" else None
    assert [sv(ref + "1") for ref in "ABCDEFGHIJKLM"] == ["ID", "Название", "Категория", "Приоритет", "Горизонт", "Статус", "Уверенность",
                                                          "Источник", "Issues", "PR", "Последний коммит", "Заметка", "С какой даты"]
    ru = {"done": "выполнено", "partial": "частично", "in_progress": "в работе", "planned": "запланировано", "not_started": "не начато",
          "blocked": "заблокировано", "dropped": "исключено", "obsolete": "устарело", "unknown": "неясно"}
    col_f = [sv("F%d" % r) for r in range(2, n + 2)]
    for k, lab in ru.items():                                         # что посчитает COUNTIF — совпадает со сводкой среза
        assert col_f.count(lab) == pg["summary"][k], k
    # сводка формулами: COUNTIF по колонке статуса, доля, всего, выполнено %, горизонт × выполнено (COUNTIFS)
    assert c["P2"][1] == "COUNTIF($F$2:$F$%d,O2)" % (n + 1) and sv("O2") == "выполнено"
    assert c["Q2"][1].startswith("IF($P$11=0,0,P2/$P$11)") and c["P11"][1] == "COUNTA($A$2:$A$%d)" % (n + 1)
    assert 'COUNTIF($F$2:$F$%d,&quot;выполнено&quot;)' % (n + 1) in c["P12"][1] or "COUNTIF($F$2:$F$%d,\"выполнено\")" % (n + 1) in c["P12"][1]
    assert any(v[1] and v[1].startswith("COUNTIFS($E$2:$E$") for v in c.values())
    assert c["G2"][0] == 17 or c["G2"][2] is None                    # уверенность — в процентах
    # условное форматирование статусов (cellIs → dxf) и dxfs в стилях
    assert '<conditionalFormatting sqref="F2:F%d">' % (n + 1) in xml and xml.count('<cfRule type="cellIs"') >= 18
    assert xml.index("</autoFilter>" if "</autoFilter>" in xml else "<autoFilter") < xml.index("<conditionalFormatting") < xml.index("<pageMargins")
    styles = z.read("xl/styles.xml").decode()
    assert '<dxfs count="12">' in styles and '<cellXfs count="18">' in styles and styles.index("</cellStyles>") < styles.index("<dxfs")
    # Таймлайн: полосы по статусу (стили 10–14), столбец текущего месяца выделен
    tl = sheet_xml(z, "Таймлайн")
    t = cells(tl)
    cur = json.loads((tracked_xlsx / "data/gantt-progress.json").read_text(encoding="utf-8"))["current_month"]
    head = [a for a, v in t.items() if re.fullmatch(r"[A-Z]+1", a) and v[0] == 15]
    assert len(head) == 1 and strings[int(t[head[0]][2])] == "М%d · сегодня" % cur
    assert {v[0] for v in t.values()} & {10, 11, 12, 13, 14} and any(v[0] == 16 for v in t.values())
    assert '<conditionalFormatting sqref="G2:' in tl


def test_xlsx_progress_opens_in_openpyxl(tracked_xlsx):
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.load_workbook(tracked_xlsx / "deliverables/strategy.xlsx")
    ws = wb["Прогресс"]
    assert ws.freeze_panes == "C2" and str(ws["P2"].value).startswith("=COUNTIF(")
    assert len(ws.conditional_formatting) >= 2
    assert wb["Таймлайн"].freeze_panes == "D2"


def test_xlsx_without_progress_unchanged_styles(bare):
    path = bare / "deliverables/strategy.xlsx"
    if not path.exists():
        assert run("build_xlsx.py", bare).returncode == 0
    z = zipfile.ZipFile(path)
    styles = z.read("xl/styles.xml").decode()
    assert "<dxfs" not in styles and '<cellXfs count="10">' in styles
    assert not any("conditionalFormatting" in z.read(n).decode() for n in z.namelist() if n.startswith("xl/worksheets/"))


def test_build_xlsx_without_proposals(tmp_path):
    (tmp_path / "data").mkdir()
    r = run("build_xlsx.py", tmp_path)
    assert r.returncode == 2 and "proposals.json" in r.stderr


# ---------------------------------------------------------------- deck.json
def load_deck(out):
    return json.loads((out / "build/deck.json").read_text(encoding="utf-8"))


def test_deck_json_bare(bare):
    r = run("build_deck_json.py", bare)
    assert r.returncode == 0, r.stderr
    d = load_deck(bare)
    slides = d["slides"]
    assert {s["type"] for s in slides} <= SLIDE_TYPES
    assert slides[0]["type"] == "title" and "Demo App" in slides[0]["title"]
    main = [s for s in slides if not s["appendix"]]
    assert 35 <= len(main) <= 60
    cards = [s for s in slides if s["type"] == "card"]
    assert len(cards) == 30 and all(not s["appendix"] for s in cards)
    assert all("Источники" in s.get("notes", "") or s.get("sources") for s in cards)
    assert all(s["sources"][0].startswith("https://") for s in cards)
    assert any(s["type"] == "table" and s["title"].startswith("Реестр") for s in slides if s["appendix"])
    assert any(s["type"] == "table" and s["title"].startswith("Источники") for s in slides)
    assert any(s["type"] == "stats" for s in main)
    m = d["meta"]
    assert m["author"] == "Демо Автор (demo)" and "©" in m["footer"]
    assert m["counts"]["cards"] == 30 and m["counts"]["main"] == len(main)
    assert set(m["theme"]) >= {"bg", "text", "accent", "font"}


def test_deck_json_full_uses_charts_and_mockups(full):
    r = run("build_deck_json.py", full)
    assert r.returncode == 0, r.stderr
    d = load_deck(full)
    imgs = [s["image"] for s in d["slides"] if s["type"] == "image"]
    assert any(i.endswith(".svg") for i in imgs) and any(i.endswith(".png") for i in imgs)
    assert all((full / i).exists() for i in imgs)
    assert d["meta"]["counts"]["missing_images"] == []
    assert d["meta"]["theme"]["accent"] == "F5A623" and d["meta"]["theme"]["font"] == "Arial"
    assert d["meta"]["theme_source"] == "mockups/tokens.css"
    first_card = next(s for s in d["slides"] if s["type"] == "card")
    assert first_card["card"]["id"] == "P045" and first_card["card"]["rank"] == 1
    assert any(s["title"].startswith("График gantt") for s in d["slides"] if not s["appendix"])


def test_deck_json_respects_main_budget_and_small_registry(tmp_path):
    out = make_demo(tmp_path / "small", n=12)
    assert run("build_deck_json.py", out, "--main-max", "40").returncode == 0
    d = load_deck(out)
    assert len([s for s in d["slides"] if s["type"] == "card"]) == 12
    assert not any(s["title"].startswith("Реестр:") for s in d["slides"])  # все предложения уже на карточках


def test_theme_contrast_guard(tmp_path):
    css = tmp_path / "tokens.css"
    css.write_text(":root{--bg:#ffffff;--text:#fafafa;--primary:rgb(10, 20, 200)}", encoding="utf-8")
    theme, src = build_deck_json.theme_from_tokens(css)
    assert src == "mockups/tokens.css"
    assert theme["accent"] == "0A14C8"
    assert build_deck_json.contrast(theme["text"], theme["bg"]) >= 4.5


def test_parse_strategy_sections():
    md = "# T\n\n## 1. Резюме\nПервая мысль. Вторая мысль.\n\n- пункт со ссылкой [док](https://example.com/a)\n\n![[chart:k1]]\n\n## 2. Дальше\n| a | b |\n|---|---|\n| 1 | 2 |\n"
    secs = build_deck_json.parse_strategy(md)
    assert [s["title"] for s in secs] == ["Резюме", "Дальше"]
    kinds = [k for k, _ in secs[0]["items"]]
    assert kinds == ["text", "bullet", "embed"]
    assert build_deck_json.theses(secs[0]["items"]) == ["Первая мысль. Вторая мысль.", "пункт со ссылкой док"]
    assert secs[1]["items"] == [("table", [["a", "b"], ["1", "2"]])]


# ---------------------------------------------------------------- check_links
def test_check_links_offline(tmp_path):
    out = make_demo(tmp_path / "links", n=10)
    src_path = out / "data/sources.json"
    sources = json.loads(src_path.read_text(encoding="utf-8"))
    sources.append(dict(sources[0], id="S900"))                       # дубль
    sources.append({"id": "S901", "url": "ftp://bad host", "title": "плохой", "date_checked": None, "used_for": "", "status": None, "note": ""})
    src_path.write_text(json.dumps(sources, ensure_ascii=False, indent=2), encoding="utf-8")
    before = src_path.read_text(encoding="utf-8")
    r = run("check_links.py", out, "--offline")
    assert r.returncode == 0, r.stderr
    assert src_path.read_text(encoding="utf-8") == before               # офлайн не меняет sources.json
    import csv
    rows = list(csv.DictReader(open(out / "data/links-check.csv", encoding="utf-8")))
    assert rows and set(rows[0]) == set(check_links.FIELDS)
    assert len({r["url"] for r in rows}) == len(rows)
    by = {r["url"]: r for r in rows}
    assert "неверный формат" in by["ftp://bad host"]["verdict"]
    assert "дубль в sources.json: S001, S900" in by[sources[0]["url"]]["verdict"]
    assert any("P001:evidence" in r["origins"] for r in rows) and any(r["origins"].startswith("competitors:") for r in rows)
    assert all(r["status"] == "" for r in rows)
    r = run("check_links.py", out, "--offline", "--strict")
    assert r.returncode == 1


def test_check_links_verdicts():
    assert check_links.verdict_for(200) == "ok"
    assert check_links.verdict_for(301) == "ok"
    assert check_links.verdict_for(403) == check_links.ANTIBOT
    assert check_links.verdict_for(429) == check_links.ANTIBOT
    assert check_links.verdict_for(503, {"Server": "cloudflare"}) == check_links.ANTIBOT
    assert check_links.verdict_for(503) == "ошибка сервера"
    assert check_links.verdict_for(404) == "мёртвая"
    assert check_links.format_problem("https://example.com/a?b=1") is None
    assert check_links.format_problem("example.com") is not None
    assert check_links.format_problem("https://exa mple.com") is not None


# ---------------------------------------------------------------- Node: PPTX и PDF
def node_dir_with(module):
    for d in (os.environ.get("PS_NODE_DIR"), str(SCRIPTS / "node")):
        if d and (Path(d) / "node_modules" / module / "package.json").exists():
            return d
    return None


NODE = shutil.which("node")


def run_node(script, out, node_dir=None, env=None):
    cmd = [NODE, str(SCRIPTS / "node" / script), str(out)] + (["--node-dir", node_dir] if node_dir else [])
    return subprocess.run(cmd, capture_output=True, text=True, timeout=300, env=env)


@pytest.mark.skipif(not NODE, reason="нет node")
def test_node_scripts_exit_3_without_modules(tmp_path, bare):
    if (SCRIPTS / "node" / "node_modules").exists() or (bare / "build" / "node" / "node_modules").exists():
        pytest.skip("модули лежат рядом со скриптом или в <OUT>/build/node")
    env = {k: v for k, v in os.environ.items() if k != "PS_NODE_DIR"}
    for script, mod in (("build_pptx.mjs", "pptxgenjs"), ("deck_pdf.mjs", "playwright")):
        r = run_node(script, bare, str(tmp_path / "empty"), env=env)
        assert r.returncode == 3, (script, r.stderr)
        assert ("нет %s" % mod) in r.stderr and "check_env.py --install-node" in r.stderr


@pytest.mark.skipif(not NODE, reason="нет node")
def test_build_pptx(full):
    nd = node_dir_with("pptxgenjs")
    if not nd:
        pytest.skip("нет pptxgenjs (PS_NODE_DIR или scripts/node/node_modules)")
    assert run("build_deck_json.py", full).returncode == 0
    r = run_node("build_pptx.mjs", full, nd)
    assert r.returncode == 0, r.stderr
    path = full / "deliverables/strategy.pptx"
    z = zipfile.ZipFile(path)
    names = z.namelist()
    n = len(load_deck(full)["slides"])
    assert "ppt/presentation.xml" in names and "[Content_Types].xml" in names
    assert len([x for x in names if re.fullmatch(r"ppt/slides/slide\d+\.xml", x)]) == n
    assert any(x.startswith("ppt/notesSlides/") for x in names)
    assert any(x.startswith("ppt/media/") and x.endswith(".png") for x in names)
    layouts = " ".join(z.read(x).decode() for x in names if re.fullmatch(r"ppt/slideLayouts/slideLayout\d+\.xml", x))
    for name in ("TITLE", "SECTION", "CONTENT"):
        assert 'name="%s"' % name in layouts
    core = z.read("docProps/core.xml").decode()
    assert "Демо Автор (demo)" in core and "Стратегия развития Demo App" in core
    assert "Demo App · стратегия развития" in z.read("ppt/slideLayouts/slideLayout3.xml").decode() or \
        "Demo App · стратегия развития" in layouts


@pytest.mark.skipif(not NODE, reason="нет node")
def test_deck_pdf(full):
    nd = node_dir_with("playwright")
    if not nd:
        pytest.skip("нет playwright (PS_NODE_DIR или scripts/node/node_modules)")
    assert run("build_deck_json.py", full).returncode == 0
    r = run_node("deck_pdf.mjs", full, nd)
    if r.returncode == 3 and "Chromium" in r.stderr:
        pytest.skip("не установлен браузер Chromium для playwright")
    assert r.returncode == 0, r.stderr
    data = (full / "deliverables/strategy.pdf").read_bytes()
    assert data.startswith(b"%PDF")
    pages = len(re.findall(rb"/Type\s*/Page(?!s)", data))
    assert pages == len(load_deck(full)["slides"])
    assert (full / "build/deck.html").exists()
