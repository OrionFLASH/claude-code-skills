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


def make_demo(path, n=None):
    r = subprocess.run([sys.executable, str(SCRIPTS / "make_demo.py"), str(path)] + (["--proposals", str(n)] if n else []),
                       capture_output=True, text=True)
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
    out = make_demo(tmp_path_factory.mktemp("demo") / "run", 100)     # 100 предложений — геометрия всех строк в smoke
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
    alias = data(page, "d-alias")
    big = imgs[alias.get("m-M01-demo", "m-M01-demo")]
    assert big.startswith("data:image/png;base64,")
    # шесть одинаковых PNG макетов и PNG референса — одна копия байтов, остальные ключи — псевдонимы
    assert page.count(big) == 1
    keys = ["m-M%02d-demo" % k for k in range(1, 7)] + ["r-01-demo"]
    assert len({alias.get(k, k) for k in keys}) == 1
    assert "Object.keys(ALIAS).forEach" in page
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
    assert res["counts"]["figures"] > 0
    assert [c["name"] for c in res["checks"] if c["status"] == "skip" and not c.get("env")] == []   # пропуски — только окружение


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
    env["HOME"] = env["USERPROFILE"] = str(tmp_path / "home")          # кэш ~/.cache/product-strategy/node не должен подхватываться
    page = tmp_path / "lone" / "deliverables" / "index.html"   # рядом нет build/node
    page.parent.mkdir(parents=True)
    shutil.copy(demo["out"] / "deliverables" / "index.html", page)
    if (SCRIPTS / "node" / "node_modules" / "playwright").exists():
        pytest.skip("playwright установлен в scripts/node — проверка кода 3 невозможна")
    r = subprocess.run(["node", str(SMOKE), str(page)], capture_output=True, text=True, env=env, timeout=60)
    assert r.returncode == 3 and "check_env.py --install-node" in r.stderr


# ---------------------------------------------------------------- 1.1: регрессии по реальному прогону (feedback 3.1, P0-1, P2-15, P2-17)
def css_of(page):
    return re.search(r"<style>(.*?)</style>", page, re.S).group(1)


def test_css_registry_detail_row(demo):
    """Раскрытая строка: правила карточки — только для div.detail; tr.detail остаётся строкой таблицы."""
    css = css_of(demo["page"])
    assert "table.reg tr.detail{display:table-row}" in css
    assert not re.search(r"(^|[}\s,])\.detail\s*\{", css), "голый .detail{…} снова попадёт и на <tr class=detail>"
    assert ".reg-wrap{container-type:inline-size}" in css
    assert re.search(r"table\.reg tr\.detail>td>div\.detail\{position:sticky;left:0;width:100%;max-width:100cqw", css)
    assert re.search(r"div\.detail\{display:block;columns:3 280px;[^}]*container-type:inline-size", css)
    assert "minmax(120px,1fr)" in css                          # столбец значения dl.kv ≥ 120 px
    assert ".tbl thead th{background:var(--ps-surface-2);font-weight:600;white-space:normal" in css
    assert ".ghead,.grow{display:grid;grid-template-columns:280px minmax(0,1fr);padding-right:12px}" in css
    assert "@container (max-width:560px)" in css


def test_contrast_tokens():
    """«✓ проверено», «доступны», «новое», ✓ матрицы: ≥ 4,5:1 на своих подложках в обеих темах."""
    white, dark_surface = (255, 255, 255), bh.parse_color("#191c20")
    tint = lambda base: bh.mix(base, (21, 128, 61), 0.14)
    for fg, bg in (("#166534", tint(white)), ("#166534", tint(bh.parse_color("#eef0f3"))), ("#166534", white),
                   ("#166534", bh.mix(white, bh.parse_color("#2f5bd3"), 0.13)),
                   ("#4ade80", tint(dark_surface)), ("#4ade80", dark_surface), ("#9f1f14", bh.mix(white, (180, 35, 24), 0.14))):
        assert bh.contrast(bh.parse_color(fg), bg) >= 4.5, (fg, bg)
    v = bh.theme_vars({}, {})
    for mode in v.values():
        assert bh.contrast(bh.parse_color(mode["--ps-link"]), bh.parse_color(mode["--ps-surface-2"])) >= 4.5


def test_http_url_validation():
    ok = ["https://example.com", "http://example.com/a?b=1#c", "https://пример.рф/путь", "http://localhost:8000/x",
          "http://127.0.0.1/a", "https://sub.domain.co.uk"]
    bad = ["Локальный запуск по README", "https://…", "https://", "ftp://example.com", "javascript:alert(1)", "example.com",
           "https://exa mple.com", "/docs/x", "https://localhost-", ""]
    assert all(bh.http_url(u) for u in ok), [u for u in ok if not bh.http_url(u)]
    assert not any(bh.http_url(u) for u in bad), [u for u in bad if bh.http_url(u)]
    assert bh.ext_link("Локальный запуск") == "Локальный запуск"
    assert 'href="https://e.com/x"' in bh.ext_link("https://e.com/x")


def test_product_url_link_only_if_valid(demo, tmp_path):
    out = tmp_path / "url"
    shutil.copytree(demo["out"], out)
    cfg = rjson(out / "build" / "run-config.json")
    cfg["product"]["url"] = "Локальный запуск: python -m app"
    wjson(out / "build" / "run-config.json", cfg)
    _, page = build(out)
    facts = page.split('<dl class="facts">')[1].split("</dl>")[0]
    assert "Локальный запуск: python -m app" in facts and "<a" not in facts
    cfg["product"]["url"] = "https://example.com/app"
    wjson(out / "build" / "run-config.json", cfg)
    _, page = build(out)
    assert 'href="https://example.com/app"' in page.split('<dl class="facts">')[1].split("</dl>")[0]


def test_sources_untitled(demo, tmp_path):
    assert bh.url_like_title("https://example.com/docs/guide", "https://example.com/docs/guide")
    assert bh.url_like_title("https://example.com/do…", "https://example.com/docs/guide")
    assert bh.url_like_title("example.com/docs/gu", "https://www.example.com/docs/guide")
    assert bh.url_like_title("", "https://example.com")
    assert not bh.url_like_title("Документация API", "https://example.com/docs")
    assert not bh.url_like_title("Example", "https://example.com")
    assert bh.short_url("https://www.example.com/a/very/long/path/to/some/page/index.html?x=1", 30).endswith("…")
    assert bh.short_url("https://www.example.com/docs/") == "example.com/docs"
    out = tmp_path / "src"
    shutil.copytree(demo["out"], out)
    src = rjson(out / "data" / "sources.json")
    src[0].update(url="https://www.example.com/blog/2026/10/some-very-long-article-slug-about-growth", title="https://www.example.com/blog/2026/10/some-ve…")
    src[1].update(url="https://example.org/a", title="Нормальное название")
    src[2].update(url="https://…", title="")
    wjson(out / "data" / "sources.json", src)
    stdout, page = build(out)
    table = page.split('id="src-table"')[1].split("</table>")[0]
    assert table.count("без названия") == 2
    assert '<span class="untitled" title="https://www.example.com/blog/2026/10/some-very-long-article-slug-about-growth">example.com/blog/' in table
    assert "Нормальное название" in table
    assert 'href="https://…"' not in page                     # заглушка — не ссылка
    assert "без названия" in stdout


def test_verdict_and_feature_labels(demo, tmp_path):
    long_v = "Сильный каталог и аналитика, но нет локального режима и экспорта данных пользователя"
    assert bh.verdict_parts("Коротко", None) == ("Коротко", "", False)
    short, full, cut = bh.verdict_parts(long_v, None)
    assert len(short) <= bh.VERDICT_MAX + 1 and short.endswith("…") and full == long_v and cut
    short, full, cut = bh.verdict_parts("Каталог сильнее", long_v)
    assert short == "Каталог сильнее" and full == long_v and not cut
    assert bh.humanize_key("own_channel_analytics") == "Own channel analytics"
    assert bh.humanize_key("Аналитика канала") == "Аналитика канала"
    out = tmp_path / "comp"
    shutil.copytree(demo["out"], out)
    comps = rjson(out / "data" / "competitors.json")
    comps[1]["verdict"] = long_v
    comps[1].pop("verdict_long", None)
    comps[2]["verdict"] = "Сильный каталог"
    comps[2]["verdict_long"] = long_v
    comps[1]["features"] = {"own_channel_analytics": True, "export_csv": False}
    comps[1]["features_labels"] = {"export_csv": "Экспорт в CSV"}
    wjson(out / "data" / "competitors.json", comps)
    _, page = build(out)
    cj = data(page, "d-comp")
    assert cj[1]["verdict_short"].endswith("…") and len(cj[1]["verdict_short"]) <= 46 and cj[1]["verdict_cut"]
    assert cj[2]["verdict_short"] == "Сильный каталог" and cj[2]["verdict_long"] == long_v and not cj[2]["verdict_cut"]
    labels = data(page, "d-meta")["comp_feature_labels"]
    assert labels["own_channel_analytics"] == "Own channel analytics" and labels["export_csv"] == "Экспорт в CSV"
    assert "FL[f] || f" in page and "verdict_short" in page   # матрица и карточка берут подписи и короткий вердикт


def test_typesafe_single_block(demo, tmp_path):
    same = {"p_success": 0.74, "kano": "must", "kano_probs": {"must": 0.77, "linear": 0.23}}
    b = bh.merge_typesafe(same, dict(same, p_success=0.7404))
    assert b["title"] == "TypeSafe Jev (score.py = Jev)" and not b["conflicts"] and b["items"]["p_success"] == 0.7404
    b = bh.merge_typesafe({"p_success": 0.5, "risk": 0.3}, {"p_success": 0.8})
    assert b["conflicts"] == ["p_success"] and b["items"]["p_success"] == {"score.py": 0.5, "Jev": 0.8} and b["items"]["risk"] == 0.3
    assert bh.merge_typesafe(None, {"p": 1})["title"] == "TypeSafe Jev"
    assert bh.merge_typesafe({}, None) is None
    out = tmp_path / "ts"
    shutil.copytree(demo["out"], out)
    props = rjson(out / "data" / "proposals.json")
    wjson(out / "data" / "scores.json", [{"id": p["id"], "rank": i + 1, "typesafe": same} for i, p in enumerate(props)])
    wjson(out / "data" / "typesafe-jev.json", {"model": "jev", "date": "2026-10-10", "items": {p["id"]: same for p in props}})
    _, page = build(out)
    reg = data(page, "d-registry")
    assert all(r["ts_block"]["title"] == "TypeSafe Jev (score.py = Jev)" for r in reg)
    assert "TypeSafe (score.py)', r.typesafe], ['TypeSafe Jev', r.jev]" not in page   # старый двойной вывод


def noisy_png(path, w=160, h=120, seed=1):
    """PNG без сжимаемости (> 32 КБ): в --lite уходит в assets/."""
    import random
    rnd = random.Random(seed)
    raw = b"".join(b"\x00" + bytes(rnd.getrandbits(8) for _ in range(w * 3)) for _ in range(h))

    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
                     + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


@pytest.fixture(scope="module")
def lite(tmp_path_factory):
    out = enrich(make_demo(tmp_path_factory.mktemp("lite") / "run"))
    for k in range(1, 7):
        noisy_png(out / "mockups" / "concepts" / ("M%02d-demo.png" % k), seed=k)
    noisy_png(out / "design-refs" / "01-demo.png", seed=1)       # то же содержимое, что M01 — один файл
    noisy_png(out / "competitors" / "shots" / "rival-1.png", seed=9)
    return out


def test_lite_mode(lite):
    stdout, page = build(lite, "--lite", "--lite-encoder", "none")
    assets = lite / "deliverables" / "assets"
    imgs, alias = data(page, "d-img"), data(page, "d-alias")
    rel = {k: v for k, v in imgs.items() if not v.startswith("data:")}
    assert len(rel) == 7 and all(v.startswith("assets/") for v in rel.values())          # 6 макетов + скриншот; референс — псевдоним
    assert alias.get("m-M01-demo") == "r-01-demo" or alias.get("r-01-demo") == "m-M01-demo"
    assert imgs["c-effort-impact"].startswith("data:image/svg+xml")                     # SVG — всегда в странице
    for v in rel.values():
        assert (assets / v[len("assets/"):]).is_file()
    assert json.loads((assets / bh.ASSETS_MANIFEST).read_text(encoding="utf-8"))
    csp = re.search(r'Content-Security-Policy" content="([^"]+)"', page).group(1)
    assert "img-src data: 'self';" in csp and "http" not in csp
    assert "Режим --lite" in stdout and "assets/" in stdout
    _, full = build(lite)                                       # обычная сборка: автономно, файлы lite удалены
    assert all(v.startswith("data:") for v in data(full, "d-img").values())
    assert "img-src data:;" in re.search(r'Content-Security-Policy" content="([^"]+)"', full).group(1)
    assert not assets.exists()
    assert len(page.encode("utf-8")) < len(full.encode("utf-8"))


def test_lite_stale_assets_removed(lite, tmp_path):
    out = tmp_path / "st"
    shutil.copytree(lite, out)
    build(out, "--lite", "--lite-encoder", "none")
    assets = out / "deliverables" / "assets"
    before = {p.name for p in assets.iterdir()}
    noisy_png(out / "mockups" / "concepts" / "M02-demo.png", seed=42)   # содержимое изменилось — новое имя по хешу
    (assets / "keep-me.txt").write_text("чужой файл", encoding="utf-8")
    build(out, "--lite", "--lite-encoder", "none")
    after = {p.name for p in assets.iterdir()}
    assert "keep-me.txt" in after                               # удаляются только свои файлы по манифесту
    assert len(before - after) == 1 and len(after - before) == 2


def test_lite_thumbnails_with_encoder(lite, tmp_path):
    enc = bh.LiteEncoder("auto")
    if enc.kind == "none":
        pytest.skip("нет Pillow и ffmpeg — миниатюр не будет (проверено в test_lite_mode)")
    out = tmp_path / "th"
    shutil.copytree(lite, out)
    _, page = build(out, "--lite")
    thumbs = data(page, "d-thumb")
    assert thumbs and all(t[0].startswith("data:image/") and 0 < t[1] <= bh.THUMB_MAX for t in thumbs.values())
    for t in thumbs.values():
        mime = t[0].split(";")[0][5:]
        w, h = bh.image_size(base64.b64decode(t[0].split(",", 1)[1]), mime)
        assert max(w, h) <= bh.THUMB_MAX


def test_size_warning_suggests_lite(demo, tmp_path):
    out = tmp_path / "big"
    shutil.copytree(demo["out"], out)
    (out / "charts").mkdir(exist_ok=True)
    big = out / "charts" / "big.png"                          # «картинка» 9,5 МБ → страница > 12 МБ в base64
    with open(big, "wb") as f:
        f.write(png_bytes(4, 4)[:33])
        f.write(os.urandom(9_500_000))
    wjson(out / "charts" / "charts-index.json", [{"key": "big", "png": "charts/big.png", "title": "Большой", "caption": "", "section": "scores"}])
    stdout, _ = build(out)
    assert "больше 12 МБ" in stdout and "--lite" in stdout
    assert "больше 12 МБ" not in demo["stdout"]


# ---------------------------------------------------------------- smoke: геометрия, контраст, lite
def check_status(res, name):
    return {c["name"]: c for c in res["checks"]}.get(name, {}).get("status")


def test_smoke_geometry_all_rows(demo):
    """Демо со 100 предложениями: каждая строка реестра раскрыта и измерена на 1440 и 390 px; контраст в трёх темах."""
    res = run_smoke(demo["out"], "--require", "registry-sort")
    by = {c["name"]: c for c in res["checks"]}
    for v in ("1440", "390"):
        c = by["geometry-chromium-" + v]
        assert c["status"] == "pass", c
        assert c["data"]["rows"] == 100 and c["data"]["height"]["max"] < 2500 and c["data"]["minDD"] >= 120
        assert c["data"]["pageWidth"] <= c["data"]["viewport"]
        w = by.get("geometry-webkit-" + v)
        assert w and (w["status"] == "pass" or (w["status"] == "skip" and w.get("env"))), w
    for t in ("contrast-light", "contrast-dark", "contrast-auto-dark"):
        assert by[t]["status"] == "pass", by[t]
    assert by["lite-assets"]["status"] == "skip" and by["lite-assets"].get("env")


def test_smoke_catches_collapsed_detail_row(demo, tmp_path):
    """Регрессия самого smoke: если вернуть баг 1.0 (строка-сетка), геометрия и registry-sort падают."""
    if not shutil.which("node") or not playwright_dir(demo["out"]):
        pytest.skip("нет node/playwright")
    page = (demo["out"] / "deliverables" / "index.html").read_text(encoding="utf-8")
    bad = page.replace("table.reg tr.detail{display:table-row}", "table.reg tr.detail{display:grid}", 1)
    assert bad != page
    target = tmp_path / "bug" / "deliverables" / "index.html"
    target.parent.mkdir(parents=True)
    target.write_text(bad, encoding="utf-8")
    r = subprocess.run(["node", str(SMOKE), str(target), "--node-dir", playwright_dir(demo["out"]), "--json", "--engines", "chromium"],
                       capture_output=True, text=True, timeout=600)
    if r.returncode == 3:
        pytest.skip(r.stderr.strip())
    res = json.loads(r.stdout)
    assert r.returncode == 1 and not res["ok"]
    assert check_status(res, "registry-sort") == "fail"
    det = {c["name"]: c for c in res["checks"]}["geometry-chromium-1440"]
    assert det["status"] == "fail" and "table-row" in det["detail"]


def test_smoke_lite_page(lite, tmp_path):
    out = tmp_path / "sl"
    shutil.copytree(lite, out)
    build(out, "--lite")
    res = run_smoke(out, "--engines", "chromium")
    by = {c["name"]: c for c in res["checks"]}
    assert by["lite-assets"]["status"] == "pass", by["lite-assets"]
    assert by["lightbox"]["status"] == "pass" and by["external-requests"]["status"] == "pass"


# ---------------------------------------------------------------- 1.2: отслеживание выполнения (data/progress.json)
PROGRESS_FILES = ("data/progress.json", "data/gantt-progress.json", "data/kanban-progress.json", "data/revision.json",
                  "data/issue-links.json", "data/progress-overrides.json", "tracking/history.json")
# ключи строки реестра 1.1 — без progress.json набор не меняется (статус и pg появляются только в режиме отслеживания)
ROW_KEYS_11 = {"id", "title", "category", "segment", "description", "rationale", "evidence", "evidence_class", "current_feature",
               "effect_kpi", "steps", "dependencies", "effort", "cost_money", "risks", "ttfr", "cheap_test", "scores", "kano", "horizon",
               "horizon_years", "tags", "mockup", "source_group", "merged_from", "quadrant", "priority", "moscow", "labels", "typesafe",
               "jev", "ts_block", "m", "concepts", "has_mockup", "mentions", "rdeps", "_hay"}
JSON_BLOCKS_11 = {"d-meta", "d-registry", "d-metrics", "d-refs", "d-gantt", "d-kanban", "d-flows", "d-comp", "d-img", "d-thumb", "d-alias"}


def add_progress(out, *extra):
    r = subprocess.run([sys.executable, str(SCRIPTS / "make_progress_demo.py"), str(out), "--apply-block"] + list(extra),
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return out


@pytest.fixture(scope="module")
def tracked(tmp_path_factory):
    out = add_progress(enrich(make_demo(tmp_path_factory.mktemp("tracked") / "run")))
    stdout, page = build(out)
    return {"out": out, "stdout": stdout, "page": page}


def section_html(page, sid):
    m = re.search(r'<section id="%s"[^>]*>.*?</section>' % re.escape(sid), page, re.S)
    return m.group(0) if m else ""


def test_without_progress_page_unchanged(demo, rich):
    """Регрессия: без data/progress.json — ни раздела, ни блока данных, ни колонки/фильтра статуса, ни стилей прогресса."""
    for page in (demo["page"], rich["page"]):
        assert "progress" not in section_ids(page)
        assert set(json_blocks(page)) == JSON_BLOCKS_11
        assert all(set(r) == ROW_KEYS_11 for r in data(page, "d-registry"))
        assert all("pg" not in g for g in data(page, "d-gantt"))
        markup = re.sub(r"<script>.*?</script>", "", page, flags=re.S)      # общий скрипт содержит обработчики (не срабатывают)
        for marker in ('data-f="status"', 'data-qf=', 'class="gtoday"', 'class="gtd"', 'id="kbv-facts"', 'class="pst', '.pst,.gst{',
                       'data-st-go', 'Прогресс выполнения', "выполнено по проверке", 'id="d-progress"'):
            assert marker not in markup, marker
        assert bh.PROGRESS_CSS not in css_of(page)                                  # стили прогресса — только в режиме отслеживания
        assert re.findall(r'<a href="#([^"]+)" data-sec="\1"', page) == section_ids(page)


def ref_builder_source():
    """build_html.py до 1.2 (коммит перед появлением load_progress) — для побайтовой регрессии разметки; None — нет git."""
    try:
        root = subprocess.run(["git", "-C", str(SKILL), "rev-parse", "--show-toplevel"], capture_output=True, text=True, timeout=20)
        if root.returncode:
            return None
        rel = str(BUILD.relative_to(Path(root.stdout.strip())))
        log = subprocess.run(["git", "-C", root.stdout.strip(), "log", "--reverse", "--format=%H", "-S", "def load_progress", "--", rel],
                             capture_output=True, text=True, timeout=60)
        rev = (log.stdout.split() or [None])[0]
        rev = (rev + "^") if rev else "HEAD"
        src = subprocess.run(["git", "-C", root.stdout.strip(), "show", "%s:%s" % (rev, rel)], capture_output=True, text=True, timeout=60)
        return src.stdout if src.returncode == 0 and "def load_progress" not in src.stdout else None
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def test_without_progress_matches_pre_tracking_builder(rich, tmp_path):
    """Без progress.json разметка, данные и CSS страницы — байт в байт как у сборщика 1.1 (меняется только общий скрипт)."""
    src = ref_builder_source()
    if not src:
        pytest.skip("нет git-истории со сборщиком до 1.2")
    old = tmp_path / "build_html_11.py"
    old.write_text(src, encoding="utf-8")
    out = tmp_path / "ref" / "run"
    shutil.copytree(rich["out"], out)
    r = subprocess.run([sys.executable, str(old), str(out)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    a = (out / "deliverables" / "index.html").read_text(encoding="utf-8")
    _, b = build(out)

    def norm(x):
        x = re.sub(r"<script>.*?</script>", "<script/>", x, flags=re.S)
        return re.sub(r'Content-Security-Policy" content="[^"]+"', "CSP", x)
    assert norm(a) == norm(b)
    assert css_of(a) == css_of(b)


def test_progress_section_and_nav(tracked):
    page = tracked["page"]
    ids = section_ids(page)
    assert "progress" in ids and ids.index("progress") == ids.index("registry") + 1      # в навигации — сразу после реестра
    sec = section_html(page, "progress")
    assert sec.count('class="kpi pgk"') == 6
    for lab in ("выполнено", "в работе", "отстаёт по плану", "заблокировано", "вне стратегии", "дата проверки"):
        assert '<div class="l">' + lab + "</div>" in sec, lab
    for h in ("По горизонтам и приоритетам", "Динамика", "Изменились факты", "Следующие шаги", "Отстаёт по плану",
              "Работа вне стратегии", "Предлагаемые корректировки"):
        assert "<h3" in sec and h in sec, h
    assert '<svg class="pgc"' in sec and "<script" not in sec and "<polyline" in sec
    assert sec.count('class="pgrow"') >= 4                                        # горизонты (+ приоритеты из scores.json)
    pg = rjson(tracked["out"] / "data" / "progress.json")
    for pid in pg["next_actions"]:
        assert 'data-pid="%s"' % pid in sec
    assert "нет issue" in sec and "предпосылок нет" in sec or "предпосылки выполнены" in sec
    assert 'data-st-go="done"' in sec and 'data-qf-go="behind"' in sec
    assert '<a class="gh" href="https://github.com/owner/repo/issues/' in sec    # работа вне стратегии со ссылкой на issue
    meta = data(page, "d-progress")
    assert meta["labels"]["done"] == "выполнено" and meta["icons"]["partial"] == "◐" and meta["order"]["done"] == 0
    assert "выполнено по проверке" in section_html(page, "top")


def test_progress_engine_extras(tracked, tmp_path):
    """Поля движка сверх базовой схемы: расхождения, заметки, off_board, kind: pr, suspicious, mentions, remote, сменили статус."""
    page = tracked["page"]
    sec = section_html(page, "progress")
    pg = rjson(tracked["out"] / "data" / "progress.json")
    if pg["discrepancies"]:
        assert "Считали отсутствующим, а оно уже есть" in sec
    assert "С прошлой проверки (%s) статус сменили" % pg["summary"]["previous_check"] in sec
    assert "демо: GitHub не читался" in sec                                       # notes — в «Предупреждениях проверки»
    kp = rjson(tracked["out"] / "data" / "kanban-progress.json")
    if kp["off_board"]:
        assert 'class="kb-off small"' in section_html(page, "kanban")
    rows = data(page, "d-registry")
    flat = [x for r in rows for x in r["pg"]["issues"]]
    assert any(x["kind"] == "pr" and "/pull/" in x["url"] for x in flat) and any(x["sus"] for x in flat)
    assert sum(1 for r in rows if r["pg"]["mentions"]) == 3 and "Упоминается в эпиках и списках" in page
    # remote берётся из progress.json, если в run-config его нет: коммиты получают ссылки
    assert rjson(tracked["out"] / "build" / "run-config.json")["repo"]["remote"] is None
    assert any(c["url"].startswith("https://github.com/owner/repo/commit/") for r in rows for c in r["pg"]["commits"])


def test_progress_registry_status(tracked):
    page = tracked["page"]
    reg = data(page, "d-registry")
    pg = rjson(tracked["out"] / "data" / "progress.json")
    assert all(r["status"] == pg["items"][r["id"]]["status"] for r in reg)
    assert all(r["pg"]["status"] == r["status"] and "issues" in r["pg"] and "behind" in r["pg"] for r in reg)
    sel = re.search(r'<select data-f="status"[^>]*>(.*?)</select>', page, re.S).group(1)
    counts = {k: int(n) for k, n in re.findall(r'<option value="(\w+)">[^<]*\((\d+)\)</option>', sel)}
    assert counts == {k: v for k, v in pg["summary"].items() if k in counts and v}
    assert sum(counts.values()) == len(reg)
    for q in ("notdone", "work", "behind"):
        assert 'data-qf="%s"' % q in page
    assert '<option value="status">Статус выполнения</option>' in page
    assert "{ k: 'status', t: 'Статус', cls: 'c-st' }" in page                    # колонка «Статус» (видна, только если есть статусы)
    assert "'status', 'status_confidence', 'status_source', 'issues', 'prs', 'last_commit'" in page   # поля в CSV
    behind = {p for o in pg["overdue"] for p in o["proposals"] if pg["items"][p]["status"] not in ("done", "dropped", "obsolete")}
    assert {r["id"] for r in reg if r["pg"]["behind"]} == behind


def test_progress_autoblock_rendered_as_table(tracked):
    page = tracked["page"]
    assert "progress:start" not in page and "progress:end" not in page and "&lt;!--" not in page
    s14 = section_html(page, "s-14")
    assert "<th>Срок</th>" in s14 and ">Сделано</th>" in s14 and "Выполнение на" in s14
    assert '<a class="pid" href="#p=P0' in s14                                    # P-id в тексте блока кликабельны


def test_progress_gantt_and_kanban_markup(tracked):
    page = tracked["page"]
    g = section_html(page, "gantt")
    m = re.search(r'<div class="gtoday" style="--x:([\d.]+)"', g)
    assert m and 0 < float(m.group(1)) < 1 and 'class="gin pgon"' in g and 'class="gtd"' in g
    assert re.search(r'class="gbar gs-(done|partial|behind|on_track|upcoming)[^"]*"[^>]*><span class="gfill" style="width:\d+%"', g)
    assert re.search(r'<span class="gpl gpl-\w+" style="[^"]+">[✓◐!▸·] \d+%', g)
    gp = rjson(tracked["out"] / "data" / "gantt-progress.json")
    js = data(page, "d-gantt")
    assert {x["id"]: x["pg"]["status"] for x in js if "pg" in x} == {t["id"]: t["status"] for t in gp["tasks"]}
    k = section_html(page, "kanban")
    assert 'id="kbv-plan" class="kbv-r" checked' in k and 'id="kbv-facts"' in k
    assert k.count('class="kanban kb-plan"') == 1 and k.count('class="kanban kb-facts"') == 1
    kp = rjson(tracked["out"] / "data" / "kanban-progress.json")
    facts = k.split('class="kanban kb-facts"')[1].split('class="kb-off')[0]      # без строки «не на доске»
    assert facts.count('class="kmoved"') == len(kp["moves"]) and facts.count('class="pst pst-') == sum(len(v) for v in kp["columns"].values())


def test_progress_offline_csp_unique_ids(tracked):
    page = tracked["page"]
    assert not re.search(r"<(script|link|img|iframe)\b[^>]*\b(src|href)\s*=\s*[\"']?(https?:)?//", page, re.I)
    csp = re.search(r'Content-Security-Policy" content="([^"]+)"', page).group(1)
    assert "default-src 'none'" in csp and "connect-src 'none'" in csp
    scripts = re.findall(r"<script>(.*?)</script>", page, re.S)
    assert len(scripts) == 2 and all("'sha256-%s'" % base64.b64encode(hashlib.sha256(s.encode()).digest()).decode() in csp for s in scripts)
    ids = re.findall(r'\sid="([^"]+)"', page)
    assert not sorted({i for i in ids if ids.count(i) > 1})
    for v in json_blocks(page).values():
        assert "<" not in v
        json.loads(v)


def test_progress_escaping_and_github_links(tracked, tmp_path):
    out = tmp_path / "xsspg"
    shutil.copytree(tracked["out"], out)
    pg = rjson(out / "data" / "progress.json")
    pid = next(p for p, it in pg["items"].items() if it["issues"])
    it = pg["items"][pid]
    it["issues"][0].update(title='<script>alert("i")</script>', url="javascript:alert(1)")
    it["issues"].append({"number": 777, "state": "open", "title": "evil host", "url": "https://github.com.evil.example/x", "match": "similar", "score": 0.4})
    it["prs"] = [{"number": 778, "state": "open", "title": "<img src=x onerror=alert(2)>", "url": "http://github.com/owner/repo/pull/778", "match": "explicit"}]
    it["commits"] = [{"sha": "abc1234", "date": "2026-11-01", "subject": "</script><b onmouseover=alert(3)>", "match": "explicit"},
                     {"sha": "not-a-sha'\"", "date": "", "subject": "x", "match": "terms"}]
    it["note"] = "<svg onload=alert(4)>"
    it["code"] = [{"file": "<iframe src=//evil.example>", "kind": "path", "evidence": "<b>"}]
    pg["outside_strategy"][0].update(title="<img src=y onerror=alert(5)>", url="https://evil.example/issues/1")
    pg["facts_changed"][0].update(was="<script>alert(6)</script>", now='"><svg onload=alert(7)>')
    wjson(out / "data" / "progress.json", pg)
    rev = rjson(out / "data" / "revision.json")
    rev[0].update(text="<b onmouseover=alert(8)>x</b>", reason="</section><script>alert(9)</script>")
    wjson(out / "data" / "revision.json", rev)
    cfg = rjson(out / "build" / "run-config.json")
    cfg["repo"]["remote"] = "owner/repo"
    wjson(out / "build" / "run-config.json", cfg)
    _, page = build(out)
    assert page.count("<script") == 2 + len(json_blocks(page))
    for bad in ("<img src=x onerror", "<img src=y onerror", "<svg onload", "<b onmouseover", "<iframe", 'href="javascript:', "evil.example/x\"",
                'href="http://github.com', 'href="https://evil.example'):
        assert bad not in page, bad
    sec = section_html(page, "progress")
    assert "&lt;script&gt;alert(6)&lt;/script&gt;" in sec and "&lt;b onmouseover=alert(8)&gt;" in sec
    hrefs = re.findall(r'href="([^"]+)"', sec)
    assert hrefs and all(h.startswith(("#", "https://github.com/")) for h in hrefs), [h for h in hrefs if not h.startswith(("#", "https://github.com/"))]
    assert 'href="https://github.com/owner/repo/issues/%d"' % pg["outside_strategy"][0]["number"] in sec   # чужой URL → собран из owner/repo
    row = {r["id"]: r for r in data(page, "d-registry")}[pid]["pg"]
    assert row["issues"][0]["title"] == '<script>alert("i")</script>'               # данные доходят до скрипта без искажений
    assert row["issues"][0]["url"] == "https://github.com/owner/repo/issues/%d" % row["issues"][0]["n"]
    assert row["issues"][-1]["url"] == "https://github.com/owner/repo/issues/777"    # github.com.evil.example — не GitHub
    assert row["prs"][0]["url"] == "https://github.com/owner/repo/pull/778"          # http:// → только https, собран из remote
    assert row["commits"][0]["url"] == "https://github.com/owner/repo/commit/abc1234" and row["commits"][1]["url"] == ""
    all_urls = [x["url"] for r in data(page, "d-registry") for k in ("issues", "prs", "commits") for x in r["pg"][k] if x["url"]]
    assert all(u.startswith("https://github.com/") for u in all_urls)


def test_gh_url_rules():
    assert bh.gh_url("https://github.com/o/r/issues/1") == "https://github.com/o/r/issues/1"
    for bad in ("http://github.com/o/r/issues/1", "https://github.com.evil.com/x", "https://user" + "@" + "github.com/o/r", "https://github.com:8443/o/r",
                "javascript:alert(1)", "https://gitlab.com/o/r/-/issues/1", 'https://github.com/o/r"onmouseover=1', "//github.com/o/r"):
        assert bh.gh_url(bad) == "", bad
    assert bh.gh_url(None, "o/r", "issue", 12) == "https://github.com/o/r/issues/12"
    assert bh.gh_url("", "o/r", "pr", "7") == "https://github.com/o/r/pull/7"
    assert bh.gh_url("", "o/r", "commit", "deadbee") == "https://github.com/o/r/commit/deadbee"
    assert bh.gh_url("", "o/r", "commit", "zzz") == "" and bh.gh_url("", "o/r", "issue", -1) == "" and bh.gh_url("", "", "issue", 3) == ""
    assert bh.gh_remote("https://github.com/acme/widget.git") == "acme/widget" and bh.gh_remote("git" + "@" + "github.com:acme/w") == "acme/w"
    assert bh.gh_remote("acme/../x") == "" and bh.gh_remote("не репо") == "" and bh.gh_remote(None) == ""


def test_status_colors_contrast():
    """Чипы статусов: белый текст на насыщенном фоне ≥ 4,5:1 (в любой теме — фон свой)."""
    css = bh.PROGRESS_CSS
    for st in ("done", "partial", "in_progress", "planned", "not_started", "blocked", "dropped", "obsolete", "unknown"):
        m = re.search(r"\.pst-%s[^{]*\{background:(#[0-9a-f]{6})" % st, css) or re.search(r"\.pst-%s,[^{]*\{background:(#[0-9a-f]{6})" % st, css)
        assert m, st
        assert bh.contrast(bh.parse_color(m.group(1)), (255, 255, 255)) >= 4.5, (st, m.group(1))
    assert all(bh.STATUS_ICONS[k] and bh.STATUS_LABELS[k] for k in bh.STATUS_ORDER)
    assert set(bh.GSTATUS_ICONS.values()) == {"✓", "◐", "!", "▸", "·"}


def test_gantt_progress_list_format_and_partial_files(tracked, tmp_path):
    """gantt-progress.json списком (без current_month) — месяц из progress.month_index; без kanban/revision/history — раздел есть."""
    out = tmp_path / "lst"
    shutil.copytree(tracked["out"], out)
    gp = rjson(out / "data" / "gantt-progress.json")
    wjson(out / "data" / "gantt-progress.json", gp["tasks"])
    for f in ("data/kanban-progress.json", "data/revision.json", "tracking/history.json"):
        (out / f).unlink()
    stdout, page = build(out)
    assert 'class="gtoday"' in page and "Сегодня · мес. %d" % rjson(out / "data" / "progress.json")["month_index"] in page
    assert 'id="kbv-facts"' not in page and "Предлагаемые корректировки" not in page
    assert "Нет tracking/history.json" in section_html(page, "progress")
    (out / "data" / "gantt-progress.json").write_text("{битый", encoding="utf-8")
    stdout, page = build(out)
    assert "data/gantt-progress.json" in stdout and 'class="gtoday"' in page     # линия «Сегодня» — по month_index


def test_progress_lite_build(tracked, tmp_path):
    out = tmp_path / "lt"
    shutil.copytree(tracked["out"], out)
    _, page = build(out, "--lite", "--lite-encoder", "none")
    assert "progress" in section_ids(page) and 'class="gtoday"' in page


def test_smoke_progress_strict(tracked):
    res = run_smoke(tracked["out"], "--require", "all", "--engines", "chromium")
    by = {c["name"]: c for c in res["checks"]}
    for name in ("progress-section", "progress-registry", "progress-card", "progress-gantt-1440", "progress-gantt-390",
                 "progress-gantt-modal", "progress-kanban", "progress-links", "progress-mobile", "progress-contrast-light",
                 "progress-contrast-dark", "progress-contrast-auto-dark", "mobile-overflow", "external-requests", "console-errors"):
        assert by[name]["status"] == "pass", by.get(name)


def test_smoke_without_progress_skips(demo):
    res = run_smoke(demo["out"], "--engines", "chromium")
    pg = [c for c in res["checks"] if c["name"].startswith("progress-")]
    assert len(pg) >= 10 and all(c["status"] == "skip" and c.get("env") and "progress.json" in c["detail"] for c in pg)
