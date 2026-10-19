"""Страница стратегии 1.5: слой интерактивности в генераторе (FB-035, FB-037, FB-038, FB-039; SM, раздел 8) — проверки разметки без браузера.

Демо make_demo.py (site) и make_concept_demo.py (single), как в test_charts_ui.py, плюс точечные прогоны во временных папках:
  * у КАЖДОГО графика и схемы — обёртка .psi-wrap с одной кнопкой «🔍 Увеличить»; строка «Графики и схемы кликабельны…» вверху и под
    заголовком каждого раздела с графиками; старых «⤢ увеличить» / «открыть схему как картинку» нет; слой — в app.js (site) или в том же
    встроенном скрипте (single, хеш CSP совпадает), стили — блоком ps-1.5;
  * заглушки ленивых графиков (site) — размером с график (aspect-ratio из viewBox, высота на телефоне), картинки — width/aspect-ratio;
  * схемы: role="group", у каждого блока <title> из flows.json → what и aria-label, aria-labelledby — только на существующие id;
  * таблицы текста: пустая колонка не выводится, ширины колонок — только при «пустой области»;
  * Гант на весь горизонт: горизонт 6 мес. и задачи до 24-го → шкала «7–12», «год 2», пробел 7–12 заштрихован и назван;
  * глоссарий research/glossary.md → раздел и данные d-gloss (синонимы из templates/glossary.md); прочие research/*.md → поиск;
  * подсказки элементов макетов (mockups/hotspots.json, атрибуты data-hs-*), вторая тема снимка, ссылка на живой HTML.
  python3 -m pytest skills/product-strategy/tests/test_site_interactive.py -q
"""
import hashlib
import base64
import json
import re
import shutil

import pytest

import test_build_html as tb
from test_charts_ui import prepare, build, jload, site_charts

bh = tb.bh


@pytest.fixture(scope="module")
def runs(tmp_path_factory):
    base = tmp_path_factory.mktemp("site-ix")
    return {"product": prepare(base / "demo", "make_demo.py"), "concept": prepare(base / "idea", "make_concept_demo.py"), "base": base}


@pytest.fixture(scope="module")
def site_product(runs):
    return build(runs["product"], runs["base"] / "site-product")


@pytest.fixture(scope="module")
def single_concept(runs):
    return build(runs["concept"], runs["base"] / "single-concept", "--single")


def wraps(page):
    return re.findall(r'<div class="psi-wrap psi-(chart|flow)">(.*?)<button type="button" class="psi-zoom"(.*?)</button><span class="psi-cue"', page, re.S)


# ---------------------------------------------------------------- FB-035: кнопки, подсказки, слой в генераторе
@pytest.mark.parametrize("mode", ["site_product", "single_concept"])
def test_every_chart_and_flow_has_zoom_button(request, mode):
    page = request.getfixturevalue(mode)["page"]
    w = wraps(page)
    charts = page.count('class="ps-ichart')
    flows = page.count('<div class="flowsvg"')
    assert charts > 15 and flows >= 1
    assert sum(1 for k, _, _ in w if k == "chart") == charts and sum(1 for k, _, _ in w if k == "flow") == flows
    assert page.count('class="psi-zoom"') == charts + flows                      # одна кнопка на обёртку
    for kind, box, btn in w:
        assert ("ps-svg" in box) if kind == "chart" else box.startswith('<div class="flowsvg"')
        assert "Увеличить" in btn and 'aria-label="Увеличить ' in btn
    markup = re.sub(r"<script>.*?</script>", "", page, flags=re.S)
    assert "⤢ увеличить" not in markup and "открыть схему как картинку" not in markup and 'data-key="c-' not in markup
    # строка-подсказка: вверху страницы и под заголовком каждого раздела с графиками или схемами
    assert page.count('data-psi-top="1"') == 1 and bh.PSI_HINT in page
    for sec in re.findall(r'<section id="([^"]+)"[^>]*>(.*?)</section>', page, re.S):
        if sec[0] != "top" and 'class="psi-wrap' in sec[1]:
            assert re.search(r'</h2><p class="psi-hint">', sec[1]), sec[0]


def test_site_layer_in_app_js_and_css(site_product):
    d, page = site_product["dir"], site_product["page"]
    app = (d / "assets" / "app.js").read_text(encoding="utf-8")
    for need in ("window.PSI = {", "window.PS_SEARCH = {", "window.PS_ENTS = {", "window.PS = {", "PS.replace", "Связанные предложения", "Где на странице"):
        assert need in app, need
    css = (d / "assets" / "app.css").read_text(encoding="utf-8")
    assert "/* ps-1.5:start" in css and ".psi-zoom{" in css and "@media print{.psi-zoom" in css
    assert page.count("<script") == 3                                            # слой — в app.js, не отдельным файлом
    assert "Слои страницы: увеличение графиков и схем — кнопок %d" % page.count('class="psi-zoom"') in site_product["stdout"]


def test_single_layer_inside_hashed_script(single_concept):
    page = single_concept["page"]
    scripts = re.findall(r"<script>(.*?)</script>", page, re.S)
    assert len(scripts) == 2 and "window.PSI = {" in scripts[1] and "window.PS_SEARCH = {" in scripts[1]
    csp = re.search(r'Content-Security-Policy" content="([^"]+)"', page).group(1)
    for s in scripts:
        assert "'sha256-%s'" % base64.b64encode(hashlib.sha256(s.encode("utf-8")).digest()).decode() in csp


# ---------------------------------------------------------------- FB-037: стабильная высота заглушек и картинок
def test_site_placeholders_have_final_size(site_product):
    d, page = site_product["dir"], site_product["page"]
    charts = site_charts(d)
    boxes = re.findall(r'<div class="ps-svg ps-wait" data-chart="([\w-]+)"[^>]*? style="--ps-ar:([\d.]+) / ([\d.]+);--ps-mh:(\d+)px">', page)
    assert boxes and len(boxes) == page.count('class="ps-svg ps-wait"')
    for key, w, h, mh in boxes:
        vw, vh = bh.svg_viewbox(charts[key]["svg"])
        assert abs(float(w) - vw) < 0.01 and abs(float(h) - vh) < 0.01
        assert int(mh) == round(560 * vh / vw + 2)
    css = (d / "assets" / "app.css").read_text(encoding="utf-8")
    assert '.ps-svg.ps-wait[style*="--ps-ar"]{aspect-ratio:var(--ps-ar)' in css and "min-height:var(--ps-mh" in css


def test_lazy_images_reserve_their_size(tmp_path):
    out = tb.enrich(tb.make_demo(tmp_path / "run"))
    _, page = tb.build(out)
    imgs = re.findall(r'<img data-img="[^"]+" alt="[^"]*" width="(\d+)" height="(\d+)" style="width:(\d+)px;aspect-ratio:(\d+) / (\d+)"', page)
    assert imgs and all(w == aw and h == ah for w, h, _, aw, ah in imgs)
    assert all(int(sw) <= int(w) for w, _, sw, _, _ in imgs)


# ---------------------------------------------------------------- FB-038: доступность схем
@pytest.mark.parametrize("mode", ["site_product", "single_concept"])
def test_flow_nodes_titled_and_grouped(request, mode, runs):
    page = request.getfixturevalue(mode)["page"]
    out = runs["product" if mode == "site_product" else "concept"]
    nodes = {n["id"]: n for f in jload(out / "data" / "flows.json") for n in f["nodes"]}
    for svg in re.findall(r'<div class="flowsvg"[^>]*>(<svg\b.*?</svg>)', page, re.S):
        root = re.match(r"<svg\b[^>]*>", svg).group(0)
        assert 'role="group"' in root and 'role="img"' not in root and ('aria-label="' in root or "aria-labelledby" in root)
        ids = re.findall(r'data-node="([^"]+)"', svg)
        assert ids
        for nid in ids:
            g = re.search(r'<[a-z]+\s[^>]*data-node="%s"[^>]*>(\s*<title[^>]*>([^<]*)</title>)?' % re.escape(nid), svg)
            assert g.group(2), nid                                               # <title> у 100 % блоков
            assert nodes[nid]["label"] in g.group(2) and (nodes[nid]["what"] in g.group(2))
            assert '— открыть расшифровку"' in g.group(0)


def test_flow_a11y_unit():
    src = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 300 100" role="img" aria-labelledby="t d"><title id="t">Схема</title>'
           '<g data-node="k:1"><title>уже есть</title><rect width="10" height="10"/></g><g data-node="k:2"><rect width="10" height="10"/></g>'
           '<rect data-node="k:3" width="5" height="5"/></svg>')
    s = bh.sanitize_svg(src, "fl-k-1", {"k:1", "k:2", "k:3"})
    s = bh.flow_a11y(s, "fl-k-1", {"k:2": {"label": "Оплата", "what": "Пользователь платит картой"}}, "Путь")
    root = re.match(r"<svg\b[^>]*>", s).group(0)
    assert 'role="group"' in root and 'aria-labelledby="fl-k-1-t"' in root          # «d» нет — убран, «t» переименован областью
    assert s.count("<title") == 3 and "уже есть" in s                                # своё не дублируется
    assert '<title class="ps-nt">Оплата: Пользователь платит картой</title>' in s
    assert re.search(r'<rect data-node="k:3"[^>]*aria-label="k:3 — открыть расшифровку"[^>]*/>', s)   # самозакрывающийся — только aria-label
    s2 = bh.flow_a11y(bh.sanitize_svg('<svg viewBox="0 0 10 10" aria-labelledby="nope"><g data-node="a"/></svg>', "fl-x-1", {"a"}), "fl-x-1", {}, "Название")
    assert 'aria-label="Название"' in s2 and "aria-labelledby" not in s2 and 'role="group"' in s2


# ---------------------------------------------------------------- FB-039: таблицы без пустых колонок; карточки свёрнуты на узком экране
def test_markdown_drops_empty_columns_and_sizes_outliers():
    md = bh.Markdown()
    t = md.render("| Шаг | Значение | Метка |\n|---|---|---|\n| Игроков | ≈ 6 млн | факт |\n| Аудитория | — | факт |\n| Ядро | | оценка |\n")
    assert "<th>Шаг</th><th>Значение</th><th>Метка</th>" in t                          # не пустая — остаётся
    t = md.render("| Параметр | Значение | Что следует |\n|---|---|---|\n| Цель | | вывод 1 |\n| Срок | — | вывод 2 |\n")
    assert "Значение" not in t and "<th>Параметр</th><th>Что следует</th>" in t and t.count("<td>") == 4
    long = "расширение MetaForge — 40 000, расширение ARCTracker — 30 000; ARCTracker.io на Overwolf — 139 000 загрузок"
    t = md.render("| Шаг | Значение | Метка |\n|---|---|---|\n| Игроков в неделю | ≈ 6 млн | факт: beebom.com по Nexon |\n"
                  "| Пользователи | %s | факт: Chrome Web Store |\n| Ядро | 37 742 | факт: discord.com |\n" % long)
    cols = [float(x) for x in re.findall(r'<col style="width:([\d.]+)%">', t)]
    assert len(cols) == 3 and abs(sum(cols) - 100) < 0.5 and cols[1] < 40
    assert "<colgroup>" not in md.render("| A | B | C |\n|---|---|---|\n| 1 | 2 | 3 |\n| 4 | 5 | 6 |\n")


def test_registry_card_folds_on_narrow_screens(single_concept):
    js = re.findall(r"<script>(.*?)</script>", single_concept["page"], re.S)[1]
    assert "matchMedia('(max-width: 900px)')" in js
    assert "sec('Эффект и KPI', kpi ? '<ul>' + kpi + '</ul>' : '', '', 1, nk)" in js and "sec('Затраты и проверка', costs, '', 1)" in js


# ---------------------------------------------------------------- Гант на весь горизонт (SM 6.1 / раздел 8)
def test_gantt_whole_horizon_and_gaps(single_concept, site_product):
    page, out = single_concept["page"], single_concept["out"]
    cfg = jload(out / "build" / "run-config.json")
    assert cfg["strategy"]["horizon_months"] == 6 and max(g["end_month"] for g in jload(out / "data" / "gantt.json")) == 24
    gantt = re.search(r'<section id="gantt".*?</section>', page, re.S).group(0)
    assert re.search(r'<span class="yr"[^>]*title="месяцы 7–12 · видение, год 1">7–12</span>', gantt)
    assert re.search(r'<span class="yr"[^>]*>год 2</span>', gantt) and "мес. 7–18" not in gantt
    assert re.search(r'<div class="ggap" style="--x0:[\d.]+;--x1:[\d.]+" title="месяцы 7–12: задач нет"', gantt)
    assert 'class="gin has-gaps"' in gantt and "Месяцы без задач: 7–12" in gantt
    assert "data/gantt.json: месяцы 7–12 без задач" in single_concept["stdout"]
    # горизонт 12 и задачи на все месяцы (демо продукта) — без пробелов и без изменений шкалы
    g2 = re.search(r'<section id="gantt".*?</section>', site_product["page"], re.S).group(0)
    assert "ggap" not in g2 and re.search(r'<span class="yr" style="[^"]*">год 2</span>', g2)


# ---------------------------------------------------------------- глоссарий, исследования для поиска
GLOSSARY = ("# Глоссарий: Demo\n\nДата: 2026-10-19.\n\n| Термин | Значение |\n|---|---|\n"
            "| Отток | доля пользователей, ушедших за период |\n| North Star | одна главная метрика ценности (источник: research/metrics.md) |\n"
            "\n- **Фейковая дверь** — кнопка платной функции до её разработки: считает интерес\n")


def test_glossary_section_and_terms_data(runs, tmp_path):
    out = tmp_path / "run"
    shutil.copytree(runs["product"], out)
    (out / "research" / "glossary.md").write_text(GLOSSARY, encoding="utf-8")
    stdout, page = tb.build(out)
    sec = re.search(r'<section id="glossary".*?</section>', page, re.S).group(0)
    assert 'id="gl-отток"' in sec and 'id="gl-north-star"' in sec and 'id="gl-фейковая-дверь"' in sec
    assert '<a href="#glossary" data-sec="glossary"' in page and "глоссарий — терминов 3" in stdout
    g = {x["key"]: x for x in tb.data(page, "d-gloss")}
    assert g["отток"]["forms"] == ["Отток", "churn"] and g["north-star"]["src"] == "research/metrics.md"
    assert "Полярная звезда" in g["north-star"]["forms"] and g["фейковая-дверь"]["what"].startswith("кнопка платной функции")
    assert bh.parse_glossary("| Термин | Значение |\n|---|---|\n") == []


def test_research_docs_for_search(runs, tmp_path):
    out = tmp_path / "run"
    shutil.copytree(runs["product"], out)
    (out / "research" / "market-notes.md").write_text("# Заметки о рынке\n\nЦены у конкурентов растут.\n\n```\nкод\n```\n", encoding="utf-8")
    (out / "research" / "specs").mkdir(exist_ok=True)
    (out / "research" / "specs" / "s1.md").write_text("Спека экрана оплаты.\n", encoding="utf-8")
    _, page = tb.build(out)
    docs = tb.data(page, "d-docs")
    assert [d["path"] for d in docs] == ["research/market-notes.md", "research/specs/s1.md"]
    assert docs[0]["title"] == "Заметки о рынке" and "Цены у конкурентов" in docs[0]["text"] and "код" not in docs[0]["text"]
    assert docs[0]["href"].endswith("research/market-notes.md")
    _, shell = tb.build(out, "--site")
    js = (out / "deliverables" / "assets" / "search-docs.js").read_text(encoding="utf-8")
    assert js.startswith("/* product-strategy") and "window.PS_DOCS=" in js and "Спека экрана оплаты" in js
    assert re.search(r'<meta name="ps-docs" content="assets/search-docs\.js\?v=[0-9a-f]{10}">', shell) and shell.count("<script") == 3
    assert "d-docs" not in (out / "deliverables" / "assets" / "data.js").read_text(encoding="utf-8")


# ---------------------------------------------------------------- макеты: подсказки элементов, вторая тема, живой HTML
def test_mockup_hotspots_theme_and_html(tmp_path):
    out = tb.enrich(tb.make_demo(tmp_path / "run"))
    idx = tb.rjson(out / "data" / "mockups-index.json")
    idx[1]["png_dark"] = "mockups/concepts/M02-demo-dark.png"
    tb.wjson(out / "data" / "mockups-index.json", idx)
    (out / "mockups" / "concepts" / "M02-demo-dark.png").write_bytes(tb.png_bytes(1440, 900, (20, 20, 30)))
    tb.wjson(out / "mockups" / "hotspots.json", {"version": 1, "mockups": {"M02-demo": {"items": [
        {"n": 1, "id": "cta", "title": "Кнопка «Начать»", "what": "Главное действие экрана", "why": "Ведёт к активации", "p": ["P002", "P003"], "sec": [3, 10], "r": [0.1, 0.2, 0.3, 0.05]},
        {"n": 2, "id": "hdr", "title": "Шапка", "what": "Навигация", "p": [], "sec": [], "r": [0, 0, 1, 0.08]}]}}})
    (out / "mockups" / "concepts" / "M03-demo.html").write_text(
        '<!doctype html><body><button data-hs="go" data-hs-title="Поиск" data-hs-what="Строка поиска" data-hs-why="Быстрый вход" data-hs-p="P003 G8-01" '
        'data-hs-sec="5">x</button><span data-hs="go">часть</span></body>', encoding="utf-8")
    stdout, page = tb.build(out)
    refs = tb.data(page, "d-refs")
    m2 = refs["m:M02-demo"]
    assert m2["mock"] is True and m2["html"].endswith("M02-demo.html") and len(m2["hotspots"]) == 2
    h = m2["hotspots"][0]
    assert (h["l"], h["t"], h["w"], h["h"]) == (10.0, 20.0, 30.0, 5.0) and h["pids"] == ["P002", "P003"] and h["sec"] == [3, 10] and h["why"] == "Ведёт к активации"
    m3 = refs["m:M03-demo"]["hotspots"]
    assert len(m3) == 1 and m3[0]["title"] == "Поиск" and m3[0]["pids"] == ["P003"] and "l" not in m3[0]   # без координат — только список
    fig = re.search(r'<figure class="lb[^"]*" data-mock="M02-demo"[^>]*>', page).group(0)
    assert 'data-ref="m:M02-demo"' in fig and 'data-html="' in fig and 'data-alt="m-M02-demo-dark"' in fig and 'data-alt-theme="dark"' in fig
    assert 'data-pids="' in fig and "подсказок элементов макетов 3" in stdout
    assert tb.data(page, "d-img")["m-M02-demo-dark"].startswith("data:image/png")
    assert '<a id="lbopen" class="lbopen" target="_blank" rel="noopener" hidden>Открыть интерактивный макет ↗</a>' in page and 'id="lbtheme"' in page
    reg = {r["id"]: r for r in tb.data(page, "d-registry")}
    assert any(c["ref"] == "m:M02-demo" for c in reg[idx[1]["proposals"][0]]["concepts"])
