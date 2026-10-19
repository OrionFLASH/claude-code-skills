"""Страница стратегии 1.5 в браузере (FB-035, FB-036; SM, раздел 8). Playwright: Chromium и WebKit; без них тесты пропускаются.

  * «до/после» (FB-036): страница сборщика 1.4 (из git) — smoke падает со списком провалов по КАЖДОМУ графику и схеме; страница 1.5 —
    проверки viewer-* (видимая кнопка, курсоры, настоящее наведение, живой SVG, зум, Tab/Esc, элементы в просмотре, телефон, печать),
    search, entities проходят в Chromium и по каждому графику в WebKit;
  * хуки расширения: build/extra/*.js с PS.replace('lightbox') и PS.on('ready') — встроенный просмотр картинок не открывается, smoke
    пропускает его проверки с пояснением (а не падает), остальное проходит;
  * поиск: формы слова («цена» → «цены», «ценой», но не «ценность»), часть слова, е/ё, фраза, фильтр, #q=…; сущности: «раздел N»,
    G-id, ID строк таблицы, термины глоссария (подсказка, окно), аудит «мёртвых» 0; просмотр макетов: зоны подсказок, P-id и разделы,
    «Открыть интерактивный макет» (#hs), вторая тема; карточка реестра на телефоне свёрнута.
  python3 -m pytest skills/product-strategy/tests/test_site_viewer_ui.py -q
"""
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import test_build_html as tb
from test_charts_ui import prepare

SKILL = Path(__file__).resolve().parent.parent
SMOKE = SKILL / "scripts" / "node" / "smoke_html.mjs"
VIEW = ["viewer-structure", "viewer-hover", "viewer-open", "viewer-elements", "viewer-mobile", "viewer-print", "search", "entities"]


def node_dir(out):
    d = tb.playwright_dir(out)
    if d:
        return d
    c = Path.home() / ".cache" / "product-strategy" / "node"
    return str(c) if (c / "node_modules" / "playwright" / "package.json").exists() else None


def smoke(out, *extra):
    if not shutil.which("node"):
        pytest.skip("нет node")
    nd = node_dir(out)
    if not nd:
        pytest.skip("нет playwright: env PS_NODE_DIR или check_env.py --install-node")
    r = subprocess.run(["node", str(SMOKE), str(out / "deliverables" / "index.html"), "--node-dir", nd, "--json"] + list(extra),
                       capture_output=True, text=True, timeout=900)
    if r.returncode == 3:
        pytest.skip(r.stderr.strip()[:200])
    res = json.loads(r.stdout)
    return r.returncode, res, {c["name"]: c for c in res["checks"]}


def add_pngs(out):
    """Картинки, которых нет в демо: снимки макетов (одна — со второй темой и зонами подсказок), референс, скриншот конкурента."""
    for k in range(1, 7):
        (out / "mockups" / "concepts" / ("M%02d-demo.png" % k)).write_bytes(tb.png_bytes(1440, 900, (240, 240, 240 - k)))
    (out / "mockups" / "concepts" / "M02-demo-dark.png").write_bytes(tb.png_bytes(1440, 900, (25, 25, 35)))
    (out / "design-refs" / "01-demo.png").write_bytes(tb.png_bytes(1440, 900, (230, 240, 250)))
    idx = tb.rjson(out / "data" / "mockups-index.json")
    idx[1]["png_dark"] = "mockups/concepts/M02-demo-dark.png"
    tb.wjson(out / "data" / "mockups-index.json", idx)
    tb.wjson(out / "mockups" / "hotspots.json", {"version": 1, "mockups": {"M02-demo": {"items": [
        {"n": 1, "id": "cta", "title": "Кнопка «Начать»", "what": "Главное действие", "why": "Ведёт к активации", "p": [idx[1]["proposals"][0]], "sec": [2], "r": [0.1, 0.2, 0.3, 0.06]},
        {"n": 2, "id": "nav", "title": "Навигация", "what": "Разделы продукта", "p": [], "sec": [], "r": [0.0, 0.0, 1.0, 0.08]}]}}})
    return out


STRAT_ADD = """
## 14. План действий
Сначала задача G03, затем см. раздел 2 и разделы 3 и 10. Гипотеза H1 проверяется первой; Отток считаем помесячно.

| ID | Гипотеза | Как проверить |
|---|---|---|
| H1 | Цены у конкурентов растут | опрос |
| H2 | Ценой можно привлечь | лендинг |

Калькулятор цены — главный экран.

Ценность продукта — в скорости.

Ёлочная игрушка как пример е/ё.
"""
GLOSS = "# Глоссарий\n\n| Термин | Значение |\n|---|---|\n| Отток | доля пользователей, ушедших за период |\n"


@pytest.fixture(scope="module")
def run15(tmp_path_factory):
    out = add_pngs(prepare(tmp_path_factory.mktemp("viewer-ui") / "run", "make_demo.py"))
    md = (out / "research" / "strategy.md").read_text(encoding="utf-8")
    (out / "research" / "strategy.md").write_text(md + STRAT_ADD, encoding="utf-8")
    (out / "research" / "glossary.md").write_text(GLOSS, encoding="utf-8")
    return out


def old_builder_source():
    """build_html.py до слоя 1.5 (последний коммит без PSI_HINT; не закоммичено — HEAD); None — нет git."""
    try:
        top = subprocess.run(["git", "-C", str(SKILL), "rev-parse", "--show-toplevel"], capture_output=True, text=True, timeout=20)
        if top.returncode:
            return None
        root = top.stdout.strip()
        rel = str(tb.BUILD.relative_to(Path(root)))
        log = subprocess.run(["git", "-C", root, "log", "--reverse", "--format=%H", "-S", "PSI_HINT", "--", rel], capture_output=True, text=True, timeout=60)
        rev = (log.stdout.split() or [None])[0]
        src = subprocess.run(["git", "-C", root, "show", "%s:%s" % ((rev + "^") if rev else "HEAD", rel)], capture_output=True, text=True, timeout=60)
        return src.stdout if src.returncode == 0 and "PSI_HINT" not in src.stdout else None
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def test_before_page_fails_per_chart(run15, tmp_path):
    src = old_builder_source()
    if not src:
        pytest.skip("нет git-истории со сборщиком до 1.5")
    old = tmp_path / "build_html_14.py"
    old.write_text(src, encoding="utf-8")
    out = tmp_path / "before"
    shutil.copytree(run15, out)
    r = subprocess.run([sys.executable, str(old), str(out)], capture_output=True, text=True, timeout=300)
    if r.returncode:
        pytest.skip("сборщик до 1.5 не собрал страницу: " + r.stderr[-200:])
    code, res, ch = smoke(out, "--engines", "chromium")
    assert code == 1 and not res["ok"]
    st = ch["viewer-structure"]
    m = re.search(r"провалы у (\d+) из (\d+) графиков и схем", st["detail"])
    assert st["status"] == "fail" and m and m.group(1) == m.group(2) and int(m.group(2)) >= 20, st["detail"][:300]   # провал у каждого
    failed = st["data"]["failed"]
    assert len(failed) == int(m.group(2)) and any(x.startswith("график funnel: ") and "нет видимой кнопки «🔍 Увеличить»" in x for x in failed)
    assert any(x.startswith("схема ") for x in failed) and "вверху страницы нет строки" in st["detail"]
    assert ch["viewer-open"]["status"] == "fail"


def test_after_page_passes_with_extension(run15, tmp_path):
    out = tmp_path / "after"
    shutil.copytree(run15, out)
    (out / "build" / "extra").mkdir(parents=True, exist_ok=True)
    (out / "build" / "extra" / "10-ext.js").write_text(
        "PS.replace('lightbox'); PS.on('ready', function (a) { document.documentElement.setAttribute('data-ext-ready', a.version); });\n", encoding="utf-8")
    r = subprocess.run([sys.executable, str(tb.BUILD), str(out)], capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stderr
    code, res, ch = smoke(out, "--engines", "chromium,webkit", "--require", ",".join(VIEW))
    bad = {k: v["detail"][:300] for k, v in ch.items() if v["status"] == "fail"}
    assert code == 0 and res["ok"], bad
    for name in VIEW:
        assert ch[name]["status"] == "pass", (name, ch[name]["detail"][:300])
    for name in ("lightbox", "hotspot", "layers"):
        assert ch[name]["status"] == "skip" and "заменён расширением" in ch[name]["detail"] and ch[name].get("env")
    wk = ch.get("engine-load-webkit", {})
    if wk.get("status") == "pass":
        m = re.search(r"просмотр: (\d+) из (\d+)", wk["detail"])
        assert m and m.group(1) == m.group(2) and int(m.group(2)) >= 20
    assert res["errors"] == [] and res["external"] == []


UI = r"""
import { createRequire } from 'node:module';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
const [html, nd, eng] = process.argv.slice(2);
const pw = createRequire(path.join(path.resolve(nd), 'node_modules', '_r.cjs'))('playwright');
let br; try { br = await pw[eng].launch(); } catch (e) { console.log(JSON.stringify({ skip: eng + ': ' + String(e.message).split('\n')[0] })); process.exit(0); }
const url = pathToFileURL(html).href, res = { errors: [] };
const ctx = await br.newContext({ viewport: { width: 1440, height: 900 } });
const p = await ctx.newPage();
p.on('pageerror', e => res.errors.push(String(e.message).split('\n')[0])); p.on('console', m => { if (m.type() === 'error') res.errors.push(m.text().slice(0, 200)); });
await p.goto(url); await p.waitForTimeout(300);
res.search = await p.evaluate(() => { const q = (s, o) => PS_SEARCH.query(s, o).map(r => r.text);
  const has = (arr, w) => arr.some(t => t.indexOf(w) >= 0);
  const cena = q('цена'), part = q('калькул'), yo = q('елочная'), phrase = q('"главный экран"'), any = q('калькулятор ценность', { any: true }), all = q('калькулятор ценность');
  return { cenaForms: has(cena, 'Ценой') && has(cena, 'цены'), cenaNotValue: !cena.some(t => /Ценность продукта/.test(t)),
    part: has(part, 'Калькулятор'), yo: has(yo, 'Ёлочная'), phrase: phrase.length >= 1, anyMore: any.length > all.length, stem: PS_SEARCH.stem('ценой') === PS_SEARCH.stem('цены') && PS_SEARCH.stem('ценность') !== PS_SEARCH.stem('цены') }; });
// окно поиска: «/», ввод, фильтр, Enter → подсветка на странице
await p.keyboard.press('/'); await p.waitForTimeout(150); await p.fill('#pss-q', 'гипотеза'); await p.waitForTimeout(300);
res.ui = await p.evaluate(() => ({ open: document.getElementById('pss').classList.contains('open'), n: document.querySelectorAll('#pss-res li').length, chips: document.querySelectorAll('#pss .pss-filters button').length }));
await p.keyboard.press('Enter'); await p.waitForTimeout(300);
res.ui.marks = await p.evaluate(() => document.querySelectorAll('mark.pss-hit').length);
// сущности: ссылки и действия
res.ents = await p.evaluate(() => ({ sec: [...document.querySelectorAll('a.ps-ent[data-ent^="sec:"]')].map(a => a.getAttribute('href')),
  gantt: !!document.querySelector('a.ps-ent[data-ent="gantt:G03"][data-g-open]'), row: !!document.querySelector('a.ps-ent[data-ent="row:H1"][href="#ent-H1"]'),
  term: !!document.querySelector('a.ps-term[data-term="отток"]'), glossary: !!document.getElementById('gl-отток'), audit: PS_ENTS.audit() }));
await p.click('a.ps-ent[data-ent="gantt:G03"]'); await p.waitForTimeout(150);
res.ents.ganttModal = await p.evaluate(() => !!document.querySelector('#im.open') && /G03|Демо-задача 3/.test(document.getElementById('imtitle').textContent));
await p.keyboard.press('Escape');
const t = p.locator('a.ps-term[data-term="отток"]').first(); await t.scrollIntoViewIfNeeded(); await t.hover(); await p.waitForTimeout(80);
res.ents.tip = await p.evaluate(() => { const e = document.getElementById('ps-etip'); return e && !e.hidden ? e.textContent : ''; });
await t.click(); await p.waitForTimeout(120);
res.ents.termModal = await p.evaluate(() => !!document.querySelector('#im.open') && /доля пользователей/.test(document.getElementById('imbody').textContent));
await p.keyboard.press('Escape');
// просмотр макета: зоны, P-id, разделы, интерактивный макет, вторая тема
const f = p.locator('main figure.lb[data-mock="M02-demo"]').first(); await f.scrollIntoViewIfNeeded(); await f.click(); await p.waitForSelector('#lb.open');
await p.waitForTimeout(200);
res.mock = await p.evaluate(() => ({ pins: document.querySelectorAll('#lbwrap .pin').length, items: document.querySelectorAll('#lbside .hsitem').length,
  pid: !!document.querySelector('#lbside .hsitem a.pid'), sec: !!document.querySelector('#lbside .hsitem a[href="#s2"]'),
  open: (document.getElementById('lbopen').hidden ? '' : document.getElementById('lbopen').getAttribute('href')), theme: !document.getElementById('lbtheme').hidden,
  src: document.getElementById('lbimg').getAttribute('src').slice(-40) }));
await p.click('#lbtheme'); await p.waitForTimeout(80);
res.mock.src2 = await p.evaluate(() => document.getElementById('lbimg').getAttribute('src').slice(-40));
await p.keyboard.press('Escape');
// глубокие ссылки #q= и #gl/
const p2 = await ctx.newPage(); await p2.goto(url + '#q=' + encodeURIComponent('калькулятор')); await p2.waitForTimeout(400);
res.deepQ = await p2.evaluate(() => document.getElementById('pss') && document.getElementById('pss').classList.contains('open') && document.querySelectorAll('#pss-res li').length > 0);
await p2.goto(url + '#gl/' + encodeURIComponent('отток')); await p2.waitForTimeout(400);
res.deepGl = await p2.evaluate(() => { const r = document.getElementById('gl-отток').getBoundingClientRect(); return r.top > 0 && r.bottom < innerHeight; });
// телефон: карточка реестра свёрнута по умолчанию
const m = await (await br.newContext({ viewport: { width: 390, height: 844 } })).newPage(); await m.goto(url); await m.waitForTimeout(300);
res.card = await m.evaluate(() => { const tr = document.querySelector('#tb tr.row'); (tr.querySelector('td.c-title') || tr.cells[2]).click();
  const det = document.querySelector('#tb tr.detail'), c = det.querySelector('div.detail');
  return { folded: c.querySelectorAll(':scope > details.dsec').length, open: c.querySelectorAll(':scope > section.dsec').length, h: Math.round(det.getBoundingClientRect().height) }; });
await br.close();
console.log(JSON.stringify(res));
"""


@pytest.mark.parametrize("eng", ["chromium", "webkit"])
def test_search_entities_mockups_in_browser(run15, tmp_path, eng):
    if not shutil.which("node"):
        pytest.skip("нет node")
    nd = node_dir(run15)
    if not nd:
        pytest.skip("нет playwright")
    out = tmp_path / "run"
    shutil.copytree(run15, out)
    assert subprocess.run([sys.executable, str(tb.BUILD), str(out)], capture_output=True, text=True, timeout=300).returncode == 0
    js = tmp_path / "ui.mjs"
    js.write_text(UI, encoding="utf-8")
    r = subprocess.run(["node", str(js), str(out / "deliverables" / "index.html"), nd, eng], capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-2000:]
    res = json.loads(r.stdout.strip().splitlines()[-1])
    if res.get("skip"):
        pytest.skip(res["skip"])
    assert res["errors"] == []
    s = res["search"]
    assert s["cenaForms"] and s["cenaNotValue"] and s["part"] and s["yo"] and s["phrase"] and s["anyMore"] and s["stem"], s
    assert res["ui"]["open"] and res["ui"]["n"] > 0 and res["ui"]["chips"] >= 2 and res["ui"]["marks"] > 0
    e = res["ents"]
    assert "#s2" in e["sec"] and "#s3" in e["sec"] and "#s10" in e["sec"] and e["gantt"] and e["row"] and e["term"] and e["glossary"]
    assert e["audit"]["inert"] == 0 and e["ganttModal"] and "доля пользователей" in e["tip"] and e["termModal"]
    mk = res["mock"]
    assert mk["pins"] == 2 and mk["items"] == 2 and mk["pid"] and mk["sec"] and mk["open"].endswith("M02-demo.html#hs") and mk["theme"] and mk["src2"] != mk["src"]
    assert res["deepQ"] and res["deepGl"]
    c = res["card"]
    assert c["open"] == 1 and c["folded"] >= 6 and c["h"] < 1500
