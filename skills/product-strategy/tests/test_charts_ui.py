"""Интерактивные графики на странице (references/interactive-site.md, п. 2.3–2.4): build_html.py встраивает SVG графиков,
показывает панель пояснений и переводит ссылки из пояснений в действия единым роутером.

Демо make_demo.py и make_concept_demo.py (временные папки) → check_registry → score → model → charts → build_html (site и single):
  * структура: site — assets/charts-<группа>.js (window.PS_CHARTS) с ?v=<хеш>, SVG в оболочке нет (подгружается); single —
    SVG в разметке, пояснения в блоке d-charts; ни одного <img> вместо графика с meta; SVG очищен (без скриптов и обработчиков);
  * покрытие ссылок: каждая ссылка панели имеет цель на собранной странице (проверка написана независимо от сборщика); ссылки без
    цели не показываются — предупреждение, с --strict код 1; при полном наборе разделов --strict проходит;
  * старые прогоны без charts/<ключ>.meta.json — статичные картинки и предупреждение;
  * в Chromium (Playwright): разбор ссылок роутером, полный обход КАЖДОГО элемента каждого графика (панель непустая), клавиатура
    (Enter, ←/→, Esc с возвратом фокуса), глубокая ссылка #chart/<ключ>/<id>, старые ссылки #p=…, #lb=c-<ключ>, #s-N, навигация
    #registry не сбрасывает фильтры, ссылки из панели закрывают её; «🔍 Увеличить» открывает просмотр с живым SVG (1.5, FB-035;
    до 1.5 — плоская картинка в лайтбоксе: проверка изменена осознанно).
Пропуск Playwright-тестов — как в соседних тестах (нет node, playwright или браузера).
  python3 -m pytest skills/product-strategy/tests/test_charts_ui.py -q
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import test_build_html as tb

SKILL = Path(__file__).resolve().parent.parent
SCRIPTS = SKILL / "scripts"


def run(script, *args, check=True):
    e = {k: v for k, v in os.environ.items() if not k.startswith("TYPESAFE_")}
    r = subprocess.run([sys.executable, str(SCRIPTS / script)] + [str(a) for a in args], capture_output=True, text=True, env=e, timeout=300)
    if check:
        assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-3000:]
    return r


def jload(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def prepare(out, maker):
    run(maker, out)
    for cmd in (("check_registry.py", out, "--demo"), ("score.py", out), ("model.py", out)):
        run(*cmd, check=False)
    r = run("charts.py", out)
    assert "Проверка пояснений графиков: ок" in r.stdout, r.stdout
    return out


def build(src, dst, *flags):
    shutil.copytree(src, dst)
    r = run("build_html.py", dst, *flags)
    d = dst / "deliverables"
    return {"out": dst, "dir": d, "stdout": r.stdout, "page": (d / "index.html").read_text(encoding="utf-8")}


@pytest.fixture(scope="module")
def runs(tmp_path_factory):
    base = tmp_path_factory.mktemp("charts-ui")
    return {"product": prepare(base / "demo", "make_demo.py"), "concept": prepare(base / "idea", "make_concept_demo.py"), "base": base}


@pytest.fixture(scope="module")
def site_product(runs):
    return build(runs["product"], runs["base"] / "site-product")


@pytest.fixture(scope="module")
def single_concept(runs):
    return build(runs["concept"], runs["base"] / "single-concept", "--single")


def index_keys(out):
    return [e["key"] for e in jload(out / "charts" / "charts-index.json")]


def site_charts(d):
    """{ключ: {svg, meta}} из всех assets/charts-*.js (формат: (window.PS_CHARTS=…||{})["ключ"]={…};)."""
    res = {}
    for f in sorted((d / "assets").glob("charts-*.js")):
        txt = f.read_text(encoding="utf-8")
        assert txt.startswith("/*") and "</script" not in txt
        for m in re.finditer(r'^\(window\.PS_CHARTS=window\.PS_CHARTS\|\|\{\}\)\[("[\w-]+")\]=(.*);$', txt, re.M):
            res[json.loads(m.group(1))] = dict(json.loads(m.group(2)), file=f.name)
    return res


def page_metas(page_or_dir):
    if isinstance(page_or_dir, Path):
        return {k: v["meta"] for k, v in site_charts(page_or_dir).items()}
    return json.loads(tb.json_blocks(page_or_dir)["d-charts"])


# ---------------------------------------------------------------- структура
def test_site_charts_files_and_placeholders(site_product):
    d, page, out = site_product["dir"], site_product["page"], site_product["out"]
    charts = site_charts(d)
    keys = index_keys(out)
    assert set(charts) == set(keys)
    idx = {e["key"]: e for e in jload(out / "charts" / "charts-index.json")}
    for k, c in charts.items():
        raw = jload(out / idx[k]["meta"])
        assert c["svg"].startswith("<svg") and 'data-ps-chart="%s"' % k in c["svg"]
        assert [e["id"] for e in c["meta"]["elements"]] == list(raw["elements"]), k            # порядок ←/→ = порядок meta.elements
        assert c["file"] == "charts-%s.js" % idx[k]["section"]                                 # группа = раздел графика
        assert "sources" not in json.dumps(c["meta"]["elements"][:1])                          # служебные поля в страницу не идут
    # в оболочке — места под графики со ссылкой на файл группы и версией по содержимому; SVG и <img> графиков нет
    srcs = re.findall(r'data-ps-src="(assets/charts-[\w-]+\.js)\?v=([0-9a-f]{10})"', page)
    assert srcs and {s for s, _ in srcs} == {"assets/" + c["file"] for c in charts.values()}
    for s, v in srcs:
        assert v == hashlib.sha1((d / s).read_bytes()).hexdigest()[:10]
    assert "<svg data-ps-chart" not in page and 'data-img="c-' not in page
    assert page.count('class="ps-ichart') >= len(keys) and page.count("ps-primary") == len(keys)
    assert len(re.findall(r'class="ps-howto" id="howto-', page)) == page.count('class="ps-ichart')
    assert page.count("<script") == 3 and 'id="cp"' in page                                    # подгрузка — динамически, не в оболочке
    data = json.loads(re.search(r"window\.PS_DATA=(.*);\n$", (d / "assets" / "data.js").read_text(encoding="utf-8"), re.S).group(1))
    assert not [k for k in data["d-img"] if k.startswith("c-")] and "d-charts" not in data
    assert not (d / "assets" / "img").exists() or not list((d / "assets" / "img").glob("c-*"))   # SVG графиков не дублируются картинками
    assert "Графики: интерактивных %d" % len(keys) in site_product["stdout"]


def test_single_inline_svg_and_meta(single_concept):
    page, out = single_concept["page"], single_concept["out"]
    keys = index_keys(out)
    metas = page_metas(page)
    assert set(metas) == set(keys)
    for k in keys:
        assert re.search(r'<svg [^>]*data-ps-chart="%s"' % re.escape(k), page), k
        assert metas[k]["elements"] and all(e.get("title") for e in metas[k]["elements"])
    markup = re.sub(r"<script.*?</script>", "", page, flags=re.S)
    assert 'data-img="c-' not in markup and "data-ps-src" not in markup
    assert not (single_concept["dir"] / "assets").exists()
    # SVG — без фиксированных width/height (масштаб по viewBox) и без <style>, скриптов и обработчиков
    for svg in re.findall(r"<svg [^>]*data-ps-chart=.*?</svg>", page, re.S):
        root = re.match(r"<svg[^>]*>", svg).group(0)
        assert "viewBox" in root and not re.search(r"\s(width|height)=", root)
        assert "<script" not in svg and "<style" not in svg and not re.search(r"\son\w+=", svg)


def test_svg_fragment_sanitizer():
    bh = tb.bh
    src = ('<?xml version="1.0"?><svg xmlns="http://www.w3.org/2000/svg" width="10" height="5" data-ps-chart="x" class="ps-chart">'
           '<style>body{display:none}</style><script>alert(1)</script><foreignObject><div>x</div></foreignObject>'
           '<g data-ps-el="a" class="ps-el" onclick="alert(2)" tabindex="0"><a href="https://evil.example/"><rect fill="url(https://e/x)"/></a>'
           '<use href="#m"/><image href="https://evil.example/i.png"/></g></svg>')
    s = bh.chart_svg_fragment(src)
    assert s.startswith('<svg xmlns="http://www.w3.org/2000/svg" data-ps-chart="x" class="ps-chart" viewBox="0 0 10 5">')
    for bad in ("<style", "<script", "alert", "foreignObject", "evil.example", "https://e/x", "onclick", "<a "):
        assert bad not in s, bad
    assert 'data-ps-el="a" class="ps-el"' in s and 'href="#m"' in s and 'tabindex="0"' in s


# ---------------------------------------------------------------- покрытие ссылок (проверка независимо от сборщика)
def page_targets(page, data, metas):
    secs = set(re.findall(r'<section id="(s-\d+)"', page))
    reg = {r["id"] for r in data["d-registry"]} if 'id="registry"' in page else set()
    comp = {c["slug"] for c in data["d-comp"] if not c.get("self")} | ({c["slug"] for c in data["d-comp"] if c.get("self")} if data["d-meta"].get("comp_features") else set())
    attrs = {k: set(re.findall(r'data-%s="([^"]+)"' % k, page)) for k in ("gid", "kid", "mock", "flow")}
    charts = {k: {e["id"] for e in m["elements"]} for k, m in metas.items() if re.search(r'class="ps-ichart[^"]*" data-chart="%s"' % re.escape(k), page)}
    return secs, reg, comp, attrs, charts


def target_ok(h, t):
    secs, reg, comp, attrs, charts = t
    m = re.fullmatch(r"#s(\d+)", h)
    if m:
        return "s-" + m.group(1) in secs
    m = re.fullmatch(r"#p/(P\d+)", h)
    if m:
        return m.group(1) in reg
    m = re.fullmatch(r"#registry\?(.+)", h)
    if m:
        return bool(reg) and all(len(p.split("=")) == 2 and p.split("=")[0] in ("category", "horizon", "class", "quadrant", "priority")
                                 for p in m.group(1).split("&"))
    m = re.fullmatch(r"#(gantt|kanban|mockup|flow)/(.+)", h)
    if m:
        return m.group(2) in attrs[{"gantt": "gid", "kanban": "kid", "mockup": "mock", "flow": "flow"}[m.group(1)]]
    m = re.fullmatch(r"#competitor/(.+)", h)
    if m:
        return m.group(1) in comp
    m = re.fullmatch(r"#chart/([\w-]+)(?:/(.+))?", h)
    if m:
        return m.group(1) in charts and (m.group(2) is None or m.group(2) in charts[m.group(1)])
    return False


@pytest.mark.parametrize("mode", ["site_product", "single_concept"])
def test_every_panel_link_has_target(request, mode):
    b = request.getfixturevalue(mode)
    page = b["page"]
    if mode.startswith("site"):
        data = json.loads(re.search(r"window\.PS_DATA=(.*);\n$", (b["dir"] / "assets" / "data.js").read_text(encoding="utf-8"), re.S).group(1))
        metas = page_metas(b["dir"])
    else:
        data = {k: json.loads(v) for k, v in tb.json_blocks(page).items()}
        metas = page_metas(page)
    t = page_targets(page, data, metas)
    hrefs = [l["href"] for m in metas.values() for e in m["elements"] for l in e.get("links", [])]
    assert len(hrefs) > 500
    bad = sorted({h for h in hrefs if not target_ok(h, t)})
    assert not bad, bad[:10]
    kinds = {re.match(r"#(\w+)", h).group(1) for h in hrefs}
    assert {"p", "registry", "chart", "gantt", "kanban", "competitor", "mockup"} <= kinds
    # ссылки, которых на странице нет (в демо — разделы стратегии 4–9, 11, 12, 14–17), не показаны и названы в предупреждении
    raw = 0
    for e in jload(b["out"] / "charts" / "charts-index.json"):
        raw += sum(len(x.get("links") or []) for x in jload(b["out"] / e["meta"])["elements"].values())
    m = re.search(r"пояснения графиков: (\d+) из (\d+) ссылок без цели", b["stdout"])
    assert m and int(m.group(2)) == raw and int(m.group(1)) == raw - len(hrefs)


def test_strict_flag_and_full_sections(runs, tmp_path):
    out = tmp_path / "run"
    shutil.copytree(runs["product"], out)
    r = run("build_html.py", out, "--strict", check=False)
    assert r.returncode == 1 and "ОШИБКА (--strict)" in r.stderr and "#s6" in r.stderr
    # все разделы 1–17 есть — все цели на месте, --strict проходит
    md = (out / "research" / "strategy.md").read_text(encoding="utf-8")
    have = {int(x) for x in re.findall(r"^## (\d+)\.", md, re.M)}
    md += "".join("\n## %d. Раздел %d\nТекст.\n" % (n, n) for n in range(1, 18) if n not in have)
    (out / "research" / "strategy.md").write_text(md, encoding="utf-8")
    r = run("build_html.py", out, "--strict", check=False)
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-2000:]
    assert "без цели — 0" in r.stdout and "пояснения графиков:" not in r.stdout


def test_old_run_without_meta_stays_static(tmp_path, runs):
    out = tb.enrich(tb.make_demo(tmp_path / "old"))                   # график без charts/<ключ>.meta.json
    stdout, page = tb.build(out, "--single")
    assert 'data-key="c-effort-impact"' in page and 'class="ps-ichart' not in page and "d-charts" not in tb.json_blocks(page)
    assert 'id="cp"' not in page and "графики без пояснений" in stdout and "effort-impact" in stdout
    # meta есть, но SVG без разметки data-ps-chart — тоже статичная картинка с предупреждением
    out2 = tmp_path / "broken"
    shutil.copytree(runs["product"], out2)
    (out2 / "charts" / "funnel.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><rect width="10" height="10"/></svg>', encoding="utf-8")
    stdout, page = tb.build(out2, "--single")
    assert 'data-key="c-funnel"' in page and "funnel" not in json.loads(tb.json_blocks(page)["d-charts"])
    assert "нет корня <svg data-ps-chart>" in stdout


# ---------------------------------------------------------------- поведение в браузере (Chromium, Playwright)
UI_JS = r"""
import { createRequire } from 'node:module';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
const [html, nodeDir, hrefsJson] = process.argv.slice(2);
const pw = createRequire(path.join(path.resolve(nodeDir), 'node_modules', '_r.cjs'))('playwright');
let br;
try { br = await pw.chromium.launch(); } catch (e) { console.log(JSON.stringify({ skip: 'нет Chromium: ' + String(e.message || e).split('\n')[0] })); process.exit(0); }
const url = pathToFileURL(html).href, res = { errors: [], external: [] };
const ctx = await br.newContext({ viewport: { width: 1440, height: 900 } });
function watch(p) {
  p.on('pageerror', e => res.errors.push(String(e.message || e).split('\n')[0]));
  p.on('console', m => { if (m.type() === 'error') res.errors.push(m.text().slice(0, 200)); });
  p.on('request', r => { if (!/^(file|data|blob|about):/i.test(r.url())) res.external.push(r.url()); });
}
const p = await ctx.newPage(); watch(p);
await p.goto(url, { waitUntil: 'load' }); await p.waitForTimeout(200);
res.loaded = await p.evaluate(() => new Promise(r => { const t = setTimeout(() => r(false), 20000); PS_ROUTER.loadAll(() => { clearTimeout(t); r(true); }); }));
// роутер: разбор и цели
const hrefs = JSON.parse(hrefsJson);
res.parse = await p.evaluate(hs => hs.map(h => PS_ROUTER.parse(h)), hrefs);
res.resolve = await p.evaluate(hs => hs.map(h => !!PS_ROUTER.resolve(h)), hrefs);
// полный обход: каждый элемент каждого графика (синтетический клик → делегированный обработчик)
res.traverse = await p.evaluate(() => {
  const out = { charts: 0, elements: 0, bad: [] };
  for (const f of document.querySelectorAll('figure.ps-ichart.ps-primary')) {
    const key = f.dataset.chart, els = (PS_ROUTER.meta(key) || {}).elements || []; out.charts++;
    for (const e of els) {
      const el = f.querySelector('svg [data-ps-el="' + CSS.escape(e.id) + '"]'); out.elements++;
      if (!el) { out.bad.push(key + '/' + e.id + ': нет элемента'); continue; }
      el.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
      const st = PS_ROUTER.state(), cp = document.getElementById('cp');
      const ok = st.open && st.key === key && st.id === e.id && !cp.hidden && document.getElementById('cp-title').textContent.trim()
        && document.querySelectorAll('#cp-body > section').length > 0 && el.classList.contains('ps-on') && !!f.querySelector('.ps-ovl .ps-sel-line')
        && document.getElementById('cp-pos').textContent.indexOf(' из ' + els.length) > 0;
      if (!ok) out.bad.push(key + '/' + e.id);
    }
  }
  PS_ROUTER.close();
  return out;
});
// клавиатура: фокус, Enter, →, ←, Esc (фокус возвращается на элемент)
const k = await p.evaluate(() => { const f = [...document.querySelectorAll('figure.ps-ichart.ps-primary')].find(x => ((PS_ROUTER.meta(x.dataset.chart) || {}).elements || []).length > 3);
  const els = PS_ROUTER.meta(f.dataset.chart).elements; const el = f.querySelector('svg [data-ps-el="' + CSS.escape(els[0].id) + '"]'); el.scrollIntoView({ block: 'center' }); el.focus();
  return { key: f.dataset.chart, ids: els.map(e => e.id) }; });
const st = () => p.evaluate(() => ({ s: PS_ROUTER.state(), a: document.activeElement && document.activeElement.getAttribute('data-ps-el'), hash: location.hash }));
res.kb = { key: k.key, ids: k.ids.slice(0, 3), last: k.ids[k.ids.length - 1], steps: [] };
await p.keyboard.press('Enter'); res.kb.steps.push(await st());
await p.keyboard.press('ArrowRight'); res.kb.steps.push(await st());
await p.keyboard.press('ArrowLeft'); await p.keyboard.press('ArrowLeft'); res.kb.steps.push(await st());
await p.keyboard.press('Escape'); res.kb.steps.push(await st());
// ссылка из панели на раздел вне графика закрывает панель; на другой график — переключает
res.panelLink = await p.evaluate(() => {
  for (const f of document.querySelectorAll('figure.ps-ichart.ps-primary')) for (const e of (PS_ROUTER.meta(f.dataset.chart) || {}).elements || []) {
    const l = (e.links || []).find(x => /^#p\//.test(x.href)), c = (e.links || []).find(x => /^#chart\//.test(x.href));
    if (l && c) return { key: f.dataset.chart, id: e.id, p: l.href, c: c.href };
  } return null; });
if (res.panelLink) {
  const L = res.panelLink;
  await p.evaluate(L => PS_ROUTER.go('#chart/' + L.key + '/' + L.id), L);
  await p.click('#cp-body a[href="' + L.c + '"]'); await p.waitForTimeout(50);
  L.afterChart = await st();
  await p.click('#cp-body a[href="' + L.p + '"]'); await p.waitForTimeout(50);
  L.afterP = await p.evaluate(id => ({ s: PS_ROUTER.state(), row: !!document.querySelector('#tb tr.row.open[data-id="' + id + '"]'), hash: location.hash }), L.p.split('/')[1]);
}
// навигация #registry не сбрасывает фильтр; ссылка #registry?… — применяет
res.nav = await p.evaluate(() => {
  const s = document.querySelector('#registry select[data-f="category"]'), v = [...s.options].map(o => o.value).filter(Boolean)[0];
  s.value = v; s.dispatchEvent(new Event('change')); const a = document.querySelector('nav.side a[href="#registry"]'); a.click();
  const kept = s.value === v; PS_ROUTER.go('#registry?horizon=now'); const h = document.querySelector('#registry select[data-f="horizon"]');
  const out = { kept, cat: s.value, hz: h && h.value, rows: document.querySelectorAll('#tb tr.row').length }; document.getElementById('reg-reset').click(); return out; });
// глубокая ссылка после загрузки, старые #lb=c-<ключ>, #p=, #s-N
const deep = res.deepTarget = await p.evaluate(() => { const f = [...document.querySelectorAll('figure.ps-ichart.ps-primary')].pop(); const els = PS_ROUTER.meta(f.dataset.chart).elements; return { key: f.dataset.chart, id: els[Math.min(2, els.length - 1)].id }; });
const p2 = await ctx.newPage(); watch(p2);
await p2.goto(url + '#chart/' + deep.key + '/' + encodeURIComponent(deep.id), { waitUntil: 'load' });
await p2.waitForFunction(() => window.PS_ROUTER && PS_ROUTER.state().open, null, { timeout: 15000 }).catch(() => {});
res.deep = await p2.evaluate(() => ({ s: PS_ROUTER.state(), a: document.activeElement && document.activeElement.getAttribute('data-ps-el'), title: document.getElementById('cp-title').textContent }));
await p2.evaluate(k => { PS_ROUTER.close(); location.hash = '#lb=c-' + k; }, deep.key); await p2.waitForTimeout(400);
res.lb = await p2.evaluate(() => { const f = document.querySelector('figure.ps-ichart.ps-flash'); return { flash: f ? f.dataset.chart : null, lbOpen: !!document.querySelector('#lb.open') }; });
// «🔍 Увеличить» (1.5, FB-035): просмотр с ЖИВЫМ SVG (элементы кликаются), а не плоская картинка в лайтбоксе
await p2.evaluate(() => { const b = document.querySelector('figure.ps-ichart.ps-ready .psi-zoom'); b.click(); }); await p2.waitForTimeout(300);
res.zoom = await p2.evaluate(() => ({ open: !!(window.PSI && PSI.state().open), live: !!document.querySelector('#psi-lb .psi-canvas svg[data-ps-chart] .ps-el'),
  img: !!document.querySelector('#psi-lb img'), lb: !!document.querySelector('#lb.open') }));
await p2.keyboard.press('Escape');
await p2.evaluate(() => { location.hash = '#p=' + document.querySelector('#tb tr.row').dataset.id; }); await p2.waitForTimeout(200);
res.legacyP = await p2.evaluate(() => !!document.querySelector('#pm.open'));
await p2.keyboard.press('Escape');
await br.close();
console.log(JSON.stringify(res));
"""


def run_ui(b, hrefs, tmp_path):
    if not shutil.which("node"):
        pytest.skip("нет node")
    nd = tb.playwright_dir(b["out"])
    if not nd:
        pytest.skip("нет playwright: env PS_NODE_DIR или check_env.py --install-node")
    js = tmp_path / "ui.mjs"
    js.write_text(UI_JS, encoding="utf-8")
    r = subprocess.run(["node", str(js), str(b["dir"] / "index.html"), nd, json.dumps(hrefs)], capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-2000:]
    res = json.loads(r.stdout.strip().splitlines()[-1])
    if res.get("skip"):
        pytest.skip(res["skip"])
    return res


def hrefs_for(out):
    comp = [c["slug"] for c in jload(out / "data" / "competitors.json") if not c.get("self")][0]
    mock = jload(out / "data" / "mockups-index.json")[0]["key"]
    gid = jload(out / "data" / "gantt.json")[0]["id"]
    kid = jload(out / "data" / "kanban.json")["cards"][0]["id"]
    return ["#s1", "#s-1", "#s7", "#p/P001", "#p=P001", "#registry?category=product&class=A", "#registry", "#registry?bogus=1",
            "#gantt/" + gid, "#kanban/" + kid, "#competitor/" + comp, "#mockup/" + mock, "#chart/funnel/stage-activation",
            "#chart/funnel", "#chart/funnel/nope", "#lb=c-funnel", "#unknown", "#gantt/NOPE", "#p/P999"]


@pytest.mark.parametrize("mode", ["site_product", "single_concept"])
def test_panel_router_keyboard_deeplink(request, mode, tmp_path):
    b = request.getfixturevalue(mode)
    hrefs = hrefs_for(b["out"])
    res = run_ui(b, hrefs, tmp_path)
    assert res["loaded"] and res["errors"] == [] and res["external"] == []
    P = dict(zip(hrefs, res["parse"]))
    R = dict(zip(hrefs, res["resolve"]))
    assert P["#s1"] == {"t": "sec", "n": 1, "legacy": False} and P["#s-1"]["legacy"] is True and R["#s1"] and R["#s-1"]
    assert P["#p/P001"] == {"t": "prow", "id": "P001"} and P["#p=P001"]["t"] == "pcard" and R["#p/P001"] and not R["#p/P999"]
    assert P["#registry?category=product&class=A"]["f"] == {"category": "product", "evidence_class": "A"}
    assert P["#registry"]["bare"] is True and P["#registry?bogus=1"]["bad"] is True and not R["#registry?bogus=1"]
    assert P["#chart/funnel/stage-activation"] == {"t": "chart", "key": "funnel", "id": "stage-activation"} and R["#chart/funnel/stage-activation"]
    assert R["#chart/funnel"] and not R["#chart/funnel/nope"] and P["#lb=c-funnel"]["t"] == "lb"
    assert P["#unknown"] is None and not R["#unknown"] and not R["#gantt/NOPE"]
    for h in hrefs[8:12]:
        assert R[h], h
    assert not R["#s7"]                                                # раздела 7 в демо нет — цели нет
    # полный обход: панель для каждого элемента
    tr = res["traverse"]
    n_meta = sum(len(jload(b["out"] / e["meta"])["elements"]) for e in jload(b["out"] / "charts" / "charts-index.json"))
    assert tr["bad"] == [] and tr["charts"] == len(index_keys(b["out"])) and tr["elements"] == n_meta
    # клавиатура
    kb, s = res["kb"], res["kb"]["steps"]
    assert s[0]["s"]["open"] and s[0]["s"]["id"] == kb["ids"][0] and s[0]["a"] == kb["ids"][0]
    assert s[0]["hash"] == "#chart/%s/%s" % (kb["key"], kb["ids"][0])
    assert s[1]["s"]["id"] == kb["ids"][1] and s[1]["a"] == kb["ids"][1]
    assert s[2]["s"]["id"] == kb["last"]                               # ← с первого — по кругу к последнему
    assert not s[3]["s"]["open"] and s[3]["a"] == kb["last"] and s[3]["hash"] == ""
    # ссылки из панели
    L = res["panelLink"]
    assert L and L["afterChart"]["s"]["open"] and "#chart/%s/%s" % (L["afterChart"]["s"]["key"], L["afterChart"]["s"]["id"]) == L["c"]
    assert not L["afterP"]["s"]["open"] and L["afterP"]["row"] and L["afterP"]["hash"] == L["p"]
    assert res["nav"]["kept"] and res["nav"]["hz"] == "now" and res["nav"]["cat"] == "" and res["nav"]["rows"] > 0
    # глубокая ссылка и старые ссылки
    d = res["deep"]
    assert d["s"]["open"] and d["s"]["key"] == res["deepTarget"]["key"] and d["s"]["id"] == res["deepTarget"]["id"] and d["a"] == d["s"]["id"] and d["title"]
    assert res["lb"]["flash"] == res["deepTarget"]["key"] and not res["lb"]["lbOpen"]
    assert res["zoom"]["open"] and res["zoom"]["live"] and not res["zoom"]["img"] and not res["zoom"]["lb"]
    assert res["legacyP"]
