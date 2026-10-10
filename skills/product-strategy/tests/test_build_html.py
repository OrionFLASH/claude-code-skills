"""Тесты build_html.py (веб-страница стратегии) и автотеста smoke_html.mjs.

Без сети: демо-прогон make_demo.py → build_html.py → проверки разметки, данных, безопасности и офлайн-режима.
Smoke в Chromium (node + playwright) — отдельный тест; пропускается, если playwright не найден
(env PS_NODE_DIR, <OUT>/build/node или scripts/node/node_modules) или нет браузера.

  python3 -m pytest skills/product-strategy/tests/test_build_html.py -q
"""
import base64
import hashlib
import importlib.util
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import zlib
from pathlib import Path

import pytest

SKILL = Path(__file__).resolve().parent.parent
SCRIPTS = SKILL / "scripts"
BUILD = SCRIPTS / "build_html.py"
SMOKE = SCRIPTS / "node" / "smoke_html.mjs"


# ---------------------------------------------------------------- помощники
def load_module():
    spec = importlib.util.spec_from_file_location("ps_build_html", BUILD)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


bh = load_module()


def make_demo(path):
    r = subprocess.run([sys.executable, str(SCRIPTS / "make_demo.py"), str(path)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return path


def build(out, *args):
    r = subprocess.run([sys.executable, str(BUILD), str(out)] + list(args), capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    target = Path(args[args.index("--out") + 1]) if "--out" in args else out / "deliverables" / "index.html"
    return r.stdout, target.read_text(encoding="utf-8")


def json_blocks(page):
    return {m.group(1): m.group(2) for m in re.finditer(r'<script type="application/json" id="([^"]+)">(.*?)</script>', page, re.S)}


def data(page, block):
    return json.loads(json_blocks(page)[block])


def section_ids(page):
    return re.findall(r'<section id="([^"]+)"', page)


def png_bytes(w, h, rgb=(240, 240, 240)):
    """Минимальный валидный PNG (stdlib)."""
    raw = (b"\x00" + bytes(rgb) * w) * h

    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def wjson(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def rjson(path):
    return json.loads(path.read_text(encoding="utf-8"))


def enrich(out):
    """Подложить то, чего нет в демо: scores/sensitivity/weights, график, модель, PNG макетов/референса/скриншотов, вставку схемы."""
    props = rjson(out / "data" / "proposals.json")
    props[1]["description"] += " Сначала сделать P001."      # P-номер в тексте, который рисует скрипт
    wjson(out / "data" / "proposals.json", props)
    quads = ["quick_win", "big_bet", "filler", "money_pit"]
    scores = []
    for i, p in enumerate(props, 1):
        scores.append({"id": p["id"], "rank": i, "title": p["title"], "composite": round(1 - i / 100.0, 4), "rice": 10.0 / i,
                       "ice": 50.0 - i / 2.0, "wsjf": 3.0 - i / 50.0, "value_per_effort": 1.5, "risk_adjusted": 2.5,
                       "confidence_calc": 0.7, "value_index": round(5 - i / 20.0, 3), "cost_index": round(1 + (i % 5) * 0.7, 3),
                       "risk_index": 1.8, "quadrant": quads[i % 4], "priority": "P0" if i <= 5 else "P1" if i <= 20 else "P2",
                       "moscow": "must" if i <= 5 else "should", "labels": ["important"] if i % 3 == 0 else ["fast"], "typesafe": None})
    wjson(out / "data" / "scores.json", scores)
    wjson(out / "data" / "sensitivity.json", {"tornado": [{"param": "composite.rice", "low_rank_shift": 1.2, "high_rank_shift": 2.4, "swing": 3.6}],
                                              "top20_stability": 0.85, "runs": 8, "top_n": 20, "always_top20": [props[0]["id"], props[1]["id"]]})
    wjson(out / "data" / "weights.json", {"composite": {"rice": 0.3, "ice": 0.2, "wsjf": 0.25, "risk_adjusted": 0.25}})
    (out / "charts").mkdir(exist_ok=True)
    (out / "charts" / "effort-impact.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 200"><rect width="400" height="200" fill="#fff"/>'
        '<text x="20" y="40">Матрица усилие–влияние</text></svg>', encoding="utf-8")
    wjson(out / "charts" / "charts-index.json", [{"key": "effort-impact", "svg": "charts/effort-impact.svg", "title": "Матрица усилие–влияние",
                                                  "caption": "быстрые победы — слева сверху", "section": "scores"}])
    sc = lambda k: {"assumptions": {"price_month": {"value": 10 * k, "label": "допущение", "note": "цена"}},
                    "funnel": [{"stage": "acquisition", "label": "Посетители", "value": 1000 * k}],
                    "monthly": [{"month": m, "users": 10 * m * k, "paying": m, "revenue": 5.0 * m, "cost": 7.0} for m in range(1, 13)],
                    "cac": 40.0 / k, "ltv": 90.0 * k, "payback_months": 6.0 / k, "arpu": 1.1, "churn": 0.06, "roi": 0.2 * k,
                    "breakeven_month": None if k < 2 else 9, "totals": {"net_revenue": 390.0 * k, "cost": 84.0}}
    wjson(out / "data" / "model.json", {"currency": "USD", "revenue_model": "subscription", "horizon_months": 12,
                                        "scenarios": {"pessimistic": sc(1), "base": sc(2), "optimistic": sc(3)}, "notes": ["демо-модель"]})
    big = png_bytes(1440, 900)
    for k in range(1, 7):
        (out / "mockups" / "concepts" / ("M%02d-demo.png" % k)).write_bytes(big)
    (out / "design-refs" / "01-demo.png").write_bytes(big)
    (out / "mockups" / "current").mkdir(parents=True, exist_ok=True)
    (out / "mockups" / "current" / "home_desktop.png").write_bytes(png_bytes(320, 200))
    (out / "competitors" / "shots").mkdir(parents=True, exist_ok=True)
    (out / "competitors" / "shots" / "rival-1.png").write_bytes(png_bytes(320, 200, (200, 220, 240)))
    comps = rjson(out / "data" / "competitors.json")
    for c in comps:
        if c.get("slug") == "rival-1":
            c["shot"] = "competitors/shots/rival-1.png"
    wjson(out / "data" / "competitors.json", comps)
    md = (out / "research" / "strategy.md").read_text(encoding="utf-8")
    md += "\n## 14. Схема пути\nСм. ![[flow:user-journey]] и целиком:\n\n![[flow:user-journey]]\n"
    (out / "research" / "strategy.md").write_text(md, encoding="utf-8")
    return out


# ---------------------------------------------------------------- фикстуры
@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    out = make_demo(tmp_path_factory.mktemp("demo") / "run")
    stdout, page = build(out)
    return {"out": out, "stdout": stdout, "page": page}


@pytest.fixture(scope="module")
def rich(tmp_path_factory):
    out = enrich(make_demo(tmp_path_factory.mktemp("rich") / "run"))
    stdout, page = build(out)
    return {"out": out, "stdout": stdout, "page": page}


# ---------------------------------------------------------------- страница демо-прогона
def test_demo_sections_present_and_absent(demo):
    ids = section_ids(demo["page"])
    for sid in ("top", "registry", "flows", "gantt", "kanban", "mockups", "design-refs", "competitors", "market", "sources", "questions"):
        assert sid in ids, sid
    assert any(i.startswith("s-") for i in ids), "нет разделов research/strategy.md"
    for sid in ("scores", "charts", "model", "current"):          # в демо нет этих данных — разделов нет
        assert sid not in ids, sid
    nav = re.findall(r'<a href="#([^"]+)" data-sec="\1"', demo["page"])
    assert nav == ids, "навигация не совпадает с разделами"


def test_offline_no_external_resources(demo, rich):
    for page in (demo["page"], rich["page"]):
        assert not re.search(r"<(script|link|img|iframe|source|video|audio|embed|object)\b[^>]*\b(src|href)\s*=\s*[\"']?(https?:)?//", page, re.I)
        assert not re.search(r'<script\b[^>]*\bsrc=', page, re.I)
        assert not re.search(r'<link\b[^>]*rel="?stylesheet', page, re.I)
        assert "@import" not in page
        assert not re.search(r"url\(\s*['\"]?https?:", page, re.I)
        csp = re.search(r'<meta http-equiv="Content-Security-Policy" content="([^"]+)"', page).group(1)
        assert "default-src 'none'" in csp and "http" not in csp and "connect-src 'none'" in csp


def test_csp_hashes_match_inline_scripts(demo):
    page = demo["page"]
    csp = re.search(r'Content-Security-Policy" content="([^"]+)"', page).group(1)
    scripts = re.findall(r"<script>(.*?)</script>", page, re.S)
    assert len(scripts) == 2                                   # тема в head + основной
    for s in scripts:
        h = base64.b64encode(hashlib.sha256(s.encode("utf-8")).digest()).decode()
        assert "'sha256-%s'" % h in csp
    assert "unsafe-inline" not in csp.split("script-src")[1].split(";")[0]


def test_json_blocks_parse(demo):
    blocks = json_blocks(demo["page"])
    for need in ("d-meta", "d-registry", "d-metrics", "d-img", "d-gantt", "d-kanban", "d-flows", "d-comp", "d-refs"):
        assert need in blocks, need
    for k, v in blocks.items():
        assert "</" not in v and "<" not in v, k                # всё экранировано <
        json.loads(v)
    reg = data(demo["page"], "d-registry")
    assert len(reg) == len(rjson(demo["out"] / "data" / "proposals.json"))
    assert all(r["m"].get("effort_min") is not None for r in reg)


def test_proposal_links(demo):
    page = demo["page"]
    strat = "".join(re.findall(r'<section id="s-[^"]+" class="prose strat">.*?</section>', page, re.S))
    links = re.findall(r'<a class="pid" href="#p=(P\d{3})" data-pid="\1"', strat)
    assert len(links) >= 8
    assert "P004" in links
    assert re.search(r'<td><a class="pid" href="#p=P00\d"', page), "P-ссылки в таблице плана (markdown)"


def test_report_printed(demo, rich):
    assert "Размер страницы" in demo["stdout"] and "Разделы" in demo["stdout"]
    assert "Топ-10 самых тяжёлых вложений" in rich["stdout"]
    assert "chart:effort-impact" in demo["stdout"]            # вставка без графика — предупреждение


def test_author_meta_and_footer(demo):
    page = demo["page"]
    cfg = rjson(demo["out"] / "build" / "run-config.json")["author"]
    assert '<meta name="author" content="%s (%s)">' % (cfg["name"], cfg["nick"]) in page
    assert '<meta name="copyright" content="%s">' % cfg["copyright"] in page
    assert '<p class="author">' in page and '<footer class="copy">' in page
    assert cfg["copyright"] in page.split('<footer class="copy">')[1]


def test_unique_ids(rich):
    ids = re.findall(r'\sid="([^"]+)"', rich["page"])
    dup = sorted({i for i in ids if ids.count(i) > 1})
    assert not dup, dup


# ---------------------------------------------------------------- без и с данными score/charts/model
def test_rich_sections_and_scores(rich):
    page = rich["page"]
    ids = section_ids(page)
    for sid in ("scores", "charts", "model", "current"):
        assert sid in ids, sid
    assert 'data-f="priority"' in page and 'data-f="quadrant"' in page and 'data-f="labels"' in page
    mets = {m["k"] for m in data(page, "d-metrics")}
    assert {"rank", "composite", "value_index", "cost_index", "risk_index", "s_value", "effort_avg"} <= mets
    reg = data(page, "d-registry")
    assert reg[0]["priority"] and reg[0]["quadrant"] and reg[0]["m"]["rank"] == 1
    assert "Устойчивость топ-20" in page and "composite.rice" in page
    assert "не достигается" in page and "Чистая выручка за горизонт" in page and "6 %" in page


def test_images_embedded_once(rich):
    page = rich["page"]
    imgs = data(page, "d-img")
    chart = imgs["c-effort-impact"]
    assert chart.startswith("data:image/svg+xml;base64,")
    assert page.count(chart) == 1                              # вставка в тексте + раздел графиков = одна копия
    assert page.count('data-key="c-effort-impact"') == 2
    assert imgs["m-M01-demo"].startswith("data:image/png;base64,")
    dims = data(page, "d-meta")["dims"]
    assert dims["m-M01-demo"] == [1440, 900]
    assert not re.search(r'<img[^>]+src="data:', page.split('<script type="application/json"')[0]), "src картинок — только из IMG по ключу"


def test_hotspots_and_concepts(rich):
    page = rich["page"]
    refs = data(page, "d-refs")
    hs = refs["01-demo"]["hotspots"]
    assert hs and all(k in hs[0] for k in ("l", "t", "w", "h", "pl", "pt"))
    assert 'data-ref="01-demo"' in page
    reg = {r["id"]: r for r in data(page, "d-registry")}
    c = reg["P001"]["concepts"]
    assert c and c[0]["img"] and c[0]["ref"] == "01-demo"     # макет и его референс — одна запись с зонами
    assert len(c) == 1


def test_flow_embed_and_nodes(rich):
    page = rich["page"]
    svgs = re.findall(r'<div class="flowsvg" id="([^"]+)"', page)
    assert len(svgs) == 2 and len(set(svgs)) == 2              # блочная вставка в тексте + раздел, у каждой своя область
    assert page.count('class="fnode"') >= 6
    assert '<a class="emb" href="#flow-user-journey">' in page
    nodes = data(page, "d-flows")
    assert "user-journey:1" in nodes and nodes["user-journey:1"]["proposals"]


def test_tokens_css_sanitized(rich, tmp_path):
    out = tmp_path / "tok"
    shutil.copytree(rich["out"], out)
    (out / "mockups" / "tokens.css").write_text(
        ":root{--accent:#ff6600;--bg:#ffffff;--text:#111111;--font:'Inter', sans-serif}\n"
        "@import url(http://evil.example/x.css);\nbody{display:none;background:url(http://evil.example/bg.png)}\n"
        "@font-face{font-family:X;src:url(https://evil.example/f.woff2)}\n</style><script>alert(1)</script>", encoding="utf-8")
    _, page = build(out)
    assert "evil.example" not in page
    assert "body{display:none" not in page
    assert "--ps-accent:#ff6600" in page
    assert "'Inter', sans-serif" in page
    assert page.count("<script>") == 2


def test_without_optional_inputs(demo):
    reg = data(demo["page"], "d-registry")
    assert all(not r["priority"] and r["m"].get("rank") is None for r in reg)
    assert 'data-f="priority"' not in demo["page"]


def test_bad_json_skipped(demo, tmp_path):
    out = tmp_path / "bad"
    shutil.copytree(demo["out"], out)
    (out / "data" / "gantt.json").write_text("{не json", encoding="utf-8")
    (out / "data" / "kanban.json").write_text("[1, 2]", encoding="utf-8")
    stdout, page = build(out)
    assert 'id="gantt"' not in page and 'id="kanban"' not in page
    assert "data/gantt.json" in stdout and "data/kanban.json" in stdout


def test_out_and_title_options(demo, tmp_path):
    target = tmp_path / "x" / "page.html"
    _, page = build(demo["out"], "--out", str(target), "--title", "Мой заголовок <b>")
    assert "<title>Мой заголовок &lt;b&gt;</title>" in page
    assert "<h1>Мой заголовок &lt;b&gt;</h1>" in page


def test_missing_out_dir(tmp_path):
    r = subprocess.run([sys.executable, str(BUILD), str(tmp_path / "nope")], capture_output=True, text=True)
    assert r.returncode == 2 and "нет папки" in r.stderr


# ---------------------------------------------------------------- безопасность: данные — не код
def test_escaping_of_data(demo, tmp_path):
    out = tmp_path / "xss"
    shutil.copytree(demo["out"], out)
    evil = '<script>alert("t")</script>'
    props = rjson(out / "data" / "proposals.json")
    props[0]["title"] = evil
    props[0]["description"] = '</script><img src=x onerror=alert(1)>'
    props[0]["evidence"][0]["url"] = "javascript:alert(2)"
    wjson(out / "data" / "proposals.json", props)
    md = (out / "research" / "strategy.md").read_text(encoding="utf-8")
    md += ('\n## 20. Проверка\n<script>alert(3)</script> <img src=x onerror=alert(4)> [ссылка](javascript:alert(5)) '
           '[ок](https://example.com/a_b_c) <iframe src="https://evil.example"></iframe>\n')
    (out / "research" / "strategy.md").write_text(md, encoding="utf-8")
    comps = rjson(out / "data" / "competitors.json")
    comps[1]["name"] = '"><script>alert(6)</script>'
    comps[1]["url"] = "javascript:alert(7)"
    wjson(out / "data" / "competitors.json", comps)
    gantt = rjson(out / "data" / "gantt.json")
    gantt[0]["task"] = "<img src=x onerror=alert(8)>"
    wjson(out / "data" / "gantt.json", gantt)
    kb = rjson(out / "data" / "kanban.json")
    kb["cards"][0]["title"] = '<b onmouseover="alert(9)">x</b>'
    wjson(out / "data" / "kanban.json", kb)
    src = rjson(out / "data" / "sources.json")
    src[0]["title"] = "<svg onload=alert(10)>"
    src[0]["url"] = "javascript:alert(11)"
    wjson(out / "data" / "sources.json", src)
    _, page = build(out)
    assert page.count("<script") == 2 + len(json_blocks(page))  # только свои скрипты и JSON-блоки
    for bad in ("<img src=x onerror", "<iframe", "<svg onload", "<b onmouseover", 'href="javascript:', "href='javascript:"):
        assert bad not in page, bad
    assert "&lt;script&gt;alert(3)&lt;/script&gt;" in page
    assert 'href="https://example.com/a_b_c"' in page          # подчёркивания в URL не превращаются в курсив
    reg = data(page, "d-registry")
    assert reg[0]["title"] == evil                             # данные доходят до JS без искажений
    assert json.loads(json_blocks(page)["d-comp"])[1]["name"] == '"><script>alert(6)</script>'


# ---------------------------------------------------------------- модульные: Markdown, linkify, SVG
def test_markdown_blocks():
    md = bh.Markdown()
    h = md.render("# Заголовок\n\nАбзац **жирный** и *курсив*, `код <b>`, ~~зачёркнуто~~.\n\n"
                  "- один\n- два\n  - вложенный\n1. первый\n2. второй\n\n> цитата\n\n"
                  "| A | B |\n|:--|--:|\n| 1 | x \\| y |\n\n```python\nprint('<x>')\n```\n\n---\n- [x] сделано\n- [ ] нет")
    assert "<h1>Заголовок</h1>" in h
    assert "<strong>жирный</strong>" in h and "<em>курсив</em>" in h and "<code>код &lt;b&gt;</code>" in h and "<del>" in h
    assert re.search(r"<ul><li>один</li><li>два\s*<ul><li>вложенный</li></ul></li></ul>", h)
    assert "<ol><li>первый</li><li>второй</li></ol>" in h
    h2 = md.render("1. a\n  - b\n2. c\n\nТекст:\n- p\n- q")
    assert re.search(r"<ol><li>a\s*<ul><li>b</li></ul></li><li>c</li></ol>", h2) and "<p>Текст:</p>\n<ul><li>p</li><li>q</li></ul>" in h2
    assert "<blockquote><p>цитата</p></blockquote>" in h
    assert '<th class="al-r">B</th>' in h and "<td class=\"al-r\">x | y</td>" in h
    assert "<pre><code class=\"lang-python\">print(&#x27;&lt;x&gt;&#x27;)</code></pre>" in h
    assert "<hr>" in h and "☑ сделано" in h and "☐ нет" in h


def test_markdown_links_and_embeds():
    calls = []

    def embed(kind, key, inline):
        calls.append((kind, key, inline))
        return "<figure>%s</figure>" % key if not inline else "[%s]" % key
    md = bh.Markdown(embed=embed)
    h = md.render("[ok](https://e.com/a_b) [bad](javascript:alert(1)) <https://e.com/x> см. https://e.com/y.\n\n"
                  "![[chart:k1]]\n\nтекст ![[ref:01-a]] дальше\n\n![img](https://e.com/p.png)")
    assert '<a href="https://e.com/a_b" target="_blank" rel="noopener noreferrer">ok</a>' in h
    assert "javascript" not in h.split("bad")[0] + h.split("bad")[1].split("<")[0]
    assert ">bad<" not in h or 'href="javascript' not in h
    assert 'href="https://e.com/x"' in h and 'href="https://e.com/y"' in h and "y</a>." in h
    assert ("chart", "k1", False) in calls and ("ref", "01-a", True) in calls
    assert "<figure>k1</figure>" in h and "<img" not in h      # внешняя картинка — только ссылка


def test_linkify_skips_attributes_and_links():
    titles = {"P001": "a", "P002": "b", "P003": "c"}
    h = bh.linkify('<a href="#">P001</a> P002, <span title="P003">P003</span> P999 XP002 <button>P001</button>', titles)
    assert '<a href="#">P001</a>' in h
    assert '<a class="pid" href="#p=P002" data-pid="P002"' in h
    assert '<span title="P003"><a class="pid" href="#p=P003"' in h
    assert "P999" in h and "#p=P999" not in h and "XP002" in h and h.count("#p=P002") == 1
    assert "<button>P001</button>" in h


def test_sanitize_svg():
    src = ('<?xml version="1.0"?><svg xmlns="http://www.w3.org/2000/svg" width="300" height="100" onload="alert(1)">'
           '<style>.box{fill:red} #g1{opacity:.5}</style><script>alert(2)</script><defs><linearGradient id="g1"/></defs>'
           '<rect data-node="f:1" class="box" x="0" y="0" width="100" height="50" fill="url(#g1)"/>'
           '<image href="https://evil.example/x.png"/><a xlink:href="javascript:alert(3)"><text>t</text></a>'
           '<foreignObject><div>x</div></foreignObject></svg>')
    s = bh.sanitize_svg(src, "sc", {"f:1"})
    for bad in ("alert", "<script", "evil.example", "foreignObject", "onload"):
        assert bad not in s, bad
    assert 'id="sc-g1"' in s and "url(#sc-g1)" in s and "#sc .f-box" in s and "#sc #sc-g1" in s
    assert re.search(r'<rect data-node="f:1" class="fnode f-box"', s) and 'tabindex="0"' in s
    assert 'viewBox="0 0 300 100"' in s and ' width="300"' not in s.split(">")[0]


def test_image_store_rejects_outside_and_non_images(tmp_path):
    out = tmp_path / "o"
    (out / "x").mkdir(parents=True)
    (tmp_path / "secret.png").write_bytes(png_bytes(2, 2))
    (out / "x" / "fake.png").write_text("not an image", encoding="utf-8")
    (out / "x" / "ok.png").write_bytes(png_bytes(3, 2))
    warns = []
    st = bh.Images(out, warns.append)
    assert st.add("../secret.png", "a") is None
    assert st.add(str(tmp_path / "secret.png"), "a") is None
    assert st.add("x/fake.png", "b") is None
    assert st.add("https://example.com/a.png", "c") is None
    k = st.add("x/ok.png", "ok")
    assert k == "ok" and st.add("x/ok.png", "other") == "ok"   # один файл — один ключ
    assert st.meta["ok"]["w"] == 3 and st.meta["ok"]["h"] == 2
    assert any("вне папки" in w for w in warns) and any("не картинка" in w for w in warns)


def test_theme_contrast():
    v = bh.theme_vars({"accent": "#f5a623", "bg": "#101418", "text": "#e8eaed"}, {})
    light, dark = v["light"], v["dark"]
    assert light["--ps-accent"] == "#f5a623" and dark["--ps-bg"] == "#101418"
    for mode in (light, dark):
        c = bh.contrast(bh.parse_color(mode["--ps-link"]), bh.parse_color(mode["--ps-surface"]))
        assert c >= 4.5, (mode["--ps-link"], c)


# ---------------------------------------------------------------- smoke в Chromium (необязательно)
def playwright_dir(out):
    for d in (os.environ.get("PS_NODE_DIR"), str(out / "build" / "node"), str(SCRIPTS / "node")):
        if d and (Path(d) / "node_modules" / "playwright" / "package.json").exists():
            return d
    return None


def run_smoke(out, *extra):
    if not shutil.which("node"):
        pytest.skip("нет node")
    nd = playwright_dir(out)
    if not nd:
        pytest.skip("нет playwright: python3 scripts/check_env.py --install-node <OUT> или env PS_NODE_DIR")
    r = subprocess.run(["node", str(SMOKE), str(out / "deliverables" / "index.html"), "--node-dir", nd, "--json"] + list(extra),
                       capture_output=True, text=True, timeout=600)
    if r.returncode == 3:
        pytest.skip(r.stderr.strip())
    try:
        res = json.loads(r.stdout)
    except ValueError:
        pytest.fail("smoke: не JSON\n" + r.stdout[-2000:] + r.stderr[-2000:])
    bad = [c for c in res["checks"] if c["status"] == "fail"]
    assert r.returncode == 0 and res["ok"], json.dumps(bad, ensure_ascii=False, indent=1)
    assert res["errors"] == [] and res["external"] == []
    return res


def test_smoke_rich_strict(rich):
    res = run_smoke(rich["out"], "--require", "all")
    assert res["counts"]["rows"] == len(rjson(rich["out"] / "data" / "proposals.json"))
    assert res["counts"]["figures"] > 0 and res["skipped"] == 0


def test_smoke_plain_demo(demo):
    res = run_smoke(demo["out"])
    names = {c["name"]: c["status"] for c in res["checks"]}
    for need in ("registry-filter", "registry-sort", "pid-modal", "gantt-modal", "kanban-modal", "flow-node", "competitors",
                 "scrollspy", "mobile-overflow", "console-errors", "external-requests"):
        assert names.get(need) == "pass", (need, names.get(need))


def test_smoke_without_playwright_exits_3(demo, tmp_path):
    if not shutil.which("node"):
        pytest.skip("нет node")
    env = dict(os.environ)
    env.pop("PS_NODE_DIR", None)
    page = tmp_path / "lone" / "deliverables" / "index.html"   # рядом нет build/node
    page.parent.mkdir(parents=True)
    shutil.copy(demo["out"] / "deliverables" / "index.html", page)
    if (SCRIPTS / "node" / "node_modules" / "playwright").exists():
        pytest.skip("playwright установлен в scripts/node — проверка кода 3 невозможна")
    r = subprocess.run(["node", str(SMOKE), str(page)], capture_output=True, text=True, env=env, timeout=60)
    assert r.returncode == 3 and "check_env.py --install-node" in r.stderr
