"""Тесты дизайн-инструментов product-strategy 1.1: audit_site.mjs (хэш-маршруты, безопасные клики, две темы,
CSS custom properties), набор компонентов templates/mockup-kit (контраст в обеих темах), shoot_mockups.mjs
(автообнаружение, слияние результатов при параллельных запусках), measure_hotspots.mjs --draw.

Запуск: python3 -m pytest skills/product-strategy/tests/test_design.py -q
Тесты с браузером пропускаются без Playwright (PS_NODE_DIR или scripts/node/node_modules).
"""
import functools
import http.server
import json
import os
import re
import shutil
import socketserver
import subprocess
import threading
from pathlib import Path

import pytest

SKILL = Path(__file__).resolve().parents[1]
NODE_DIR = SKILL / "scripts" / "node"
KIT = SKILL / "templates" / "mockup-kit"


def find_node_dir():
    for d in [os.environ.get("PS_NODE_DIR"), str(NODE_DIR)]:
        if d and (Path(d) / "node_modules" / "playwright" / "package.json").exists():
            return d
    return None


NODE = shutil.which("node")
PW_DIR = find_node_dir()
needs_pw = pytest.mark.skipif(not NODE or not PW_DIR, reason="playwright недоступен (PS_NODE_DIR или scripts/node/node_modules)")


def node(script, *args, timeout=240):
    return subprocess.run([NODE, str(NODE_DIR / script), *map(str, args), "--node-dir", PW_DIR], capture_output=True, text=True, timeout=timeout)


# ---------------------------------------------------------------- шаблоны набора (без браузера)

def test_kit_files_present_and_offline():
    for f in ("_kit.css", "_base.html", "kit-demo.html", "README.md"):
        assert (KIT / f).is_file(), f
    css = (KIT / "_kit.css").read_text(encoding="utf-8")
    for cls in (".ps-segmented", ".ps-chip", ".ps-switch", ".ps-check", ".ps-radio", ".ps-btn.is-primary", ".ps-btn.is-danger",
                ".ps-btn.is-ghost", ".ps-card", ".ps-list", ".ps-table", ".ps-modal", ".ps-bottom-nav", ".ps-topbar", ".ps-rail",
                ".ps-empty", ".ps-toast", ".ps-alert", ".ps-concept-badge", ".ps-tip", ".ps-lock"):
        assert cls in css, cls
    assert re.search(r"\.ps-concept-badge \{[^}]*position: fixed[^}]*white-space: nowrap", css)
    assert re.search(r"\.ps-badge \{[^}]*white-space: nowrap[^}]*overflow: hidden", css)
    assert re.search(r"\.ps-rail \{ position: relative", css) and re.search(r"\.ps-tip \{ position: relative", css)
    assert ".ps-lock-body::after" in css and ".ps-lock::after" not in css        # штриховка не закрывает заголовок
    assert '[data-theme="dark"]' in css and "var(--c-bg" not in css.split("@layer")[0]
    for f in ("_kit.css", "_base.html", "kit-demo.html"):
        assert not re.search(r"https?://", (KIT / f).read_text(encoding="utf-8")), f   # офлайн: без внешних адресов
    base = (KIT / "_base.html").read_text(encoding="utf-8")
    assert 'data-viewport="1440x900"' in base and "ps-concept-badge" in base and "../tokens.css" in base


# ---------------------------------------------------------------- audit_site: локальная SPA

SPA = r"""<!doctype html><html lang="ru"><head><meta charset="utf-8"><title>Демо SPA</title>
<style>
:root{--paper:#f4f1ea;--ink:#1b1b1f;--accent:#c2410c;--line:#ddd6c8;--radius-card:12px}
[data-theme="dark"]{--paper:#141416;--ink:#ededf0;--accent:#fb923c;--line:#33333a}
@media (prefers-color-scheme: dark){:root{--glow:#00aaff}}
body{background:var(--paper);color:var(--ink);font-family:Georgia,serif;margin:0;padding:16px}
nav a{color:var(--accent);margin-right:12px}
.card{border:1px solid var(--line);border-radius:var(--radius-card);padding:12px;margin:12px 0}
.details{display:none}.open .details{display:block;padding:40px;background:var(--accent);color:#fff}
button.btn{background:var(--accent);color:#fff;border:0;border-radius:8px;padding:8px 14px}
</style></head><body>
<nav><a href="#/">Главная</a><a href="#/demo">Демо</a><a href="#/about">О проекте</a><a href="#/logout">Выйти</a></nav>
<button id="theme-toggle" type="button">Тема</button>
<main id="app"></main>
<script>
var routes = {
  "/": '<h1>Главная</h1><div class="card"><button class="btn" data-audit-safe onclick="this.parentNode.classList.toggle(\'open\')">Подробнее</button>'
     + '<div class="details">Раскрытые детали карточки</div></div><button class="btn" data-audit-safe onclick="location.hash=\'#/logout\'">Выйти из аккаунта</button>'
     + '<form><button data-audit-safe type="submit">Отправить</button></form><a data-audit-safe href="https://example.org/">Партнёр</a>',
  "/demo": '<h1>Демо</h1><p>Публичное демо</p>',
  "/about": '<h1>О проекте</h1><p>Текст</p>'
};
function render(){ var r = location.hash.replace(/^#!?/, "") || "/"; document.getElementById("app").innerHTML = routes[r] || "<h1>Нет</h1>"; }
window.addEventListener("hashchange", render); render();
document.getElementById("theme-toggle").onclick = function(){ var h = document.documentElement; h.dataset.theme = h.dataset.theme === "dark" ? "light" : "dark"; };
</script></body></html>
"""


class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


@pytest.fixture(scope="module")
def spa(tmp_path_factory):
    root = tmp_path_factory.mktemp("spa")
    (root / "index.html").write_text(SPA, encoding="utf-8")
    handler = functools.partial(_Quiet, directory=str(root))
    srv = socketserver.TCPServer(("127.0.0.1", 0), handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield "http://127.0.0.1:%d/" % srv.server_address[1]
    srv.shutdown()
    srv.server_close()


@pytest.fixture(scope="module")
def audit(spa, tmp_path_factory):
    if not NODE or not PW_DIR:
        pytest.skip("playwright недоступен")
    out = tmp_path_factory.mktemp("audit")
    r = node("audit_site.mjs", spa, out, "--routes-from", "hash", "--themes", "light,dark", "--theme-toggle", "#theme-toggle",
             "--click-safe=", "--delay", "0", "--max-pages", "6")
    assert r.returncode == 0, r.stdout + r.stderr
    d = json.loads((out / "data" / "site-audit.json").read_text(encoding="utf-8"))
    return {"out": out, "d": d, "css": (out / "mockups" / "tokens.css").read_text(encoding="utf-8"), "stdout": r.stdout}


@needs_pw
def test_audit_hash_routes_unique_slugs(audit):
    d, out = audit["d"], audit["out"]
    light = [p for p in d["pages"] if p["theme"] == "light"]
    assert [p["slug"] for p in light] == ["home", "hash-demo", "hash-about"]           # /#/logout не обходится
    shots = [p["screenshot"] for p in d["pages"]]
    assert len(shots) == len(set(shots)) == 6 and all((out / s).exists() for s in shots)
    assert "mockups/current/hash-demo-desktop.png" in shots and "mockups/current/hash-demo-dark-desktop.png" in shots
    assert next(p for p in light if p["slug"] == "hash-demo")["h1"] == ["Демо"]


@needs_pw
def test_audit_safe_clicks(audit):
    d, out = audit["d"], audit["out"]
    home = next(p for p in d["pages"] if p["slug"] == "home" and p["theme"] == "light")
    assert [s["label"] for s in home["states"]] == ["Подробнее"]
    st = home["states"][0]
    assert st["screenshot"] == "mockups/current/home-desktop--1.png" and (out / st["screenshot"]).exists() and not st["navigated"]
    why = {s["label"]: s["why"] for s in home["clicks_skipped"]}
    assert "форма" in why["Отправить"] and "внешняя" in why["Партнёр"] and "опасное" in why["Выйти из аккаунта"]
    assert (out / "mockups/current/home-desktop.png").read_bytes() != (out / st["screenshot"]).read_bytes()
    assert not any(p["states"] for p in d["pages"] if not p["slug"].startswith("home"))                   # клики только там, где есть безопасные элементы
    home_dark = next(p for p in d["pages"] if p["slug"] == "home-dark")
    assert home_dark["states"][0]["screenshot"] == "mockups/current/home-dark-desktop--1.png"


@needs_pw
def test_audit_dark_theme_and_tokens(audit):
    d, css = audit["d"], audit["css"]
    dark = [p for p in d["pages"] if p["theme"] == "dark"]
    assert dark and all(p["theme_method"] == "toggle" for p in dark)
    t = d["tokens"]
    assert t["source"] == "custom-properties" and t["custom_properties"]["light"] >= 5 and t["custom_properties"]["dark"] >= 4
    assert t["dark"]["source"] == "audited"
    light_block = css.split(':root, [data-theme="light"] {')[1]
    dark_block = css.split(':root[data-theme="dark"], [data-theme="dark"]:not(:root) {')[1].split("}")[0]
    assert "--paper: #f4f1ea" in light_block and "--c-bg: #f4f1ea" in light_block
    assert "--paper: rgb(20 20 22)" in dark_block and "--glow: rgb(0 170 255)" in dark_block and "--c-bg: rgb(20 20 22)" in dark_block
    assert not re.search(r"#[0-9a-fA-F]{3,8}", dark_block)                       # тёмные — rgb(), парсеры палитры берут светлые
    for var in ("--c-bg", "--c-text", "--c-accent", "--c-muted", "--radius", "--font"):
        assert var + ":" in light_block


@needs_pw
def test_audit_dark_from_stylesheet_without_dark_shots(spa, tmp_path):
    r = node("audit_site.mjs", spa, tmp_path, "--max-pages", "1", "--delay", "0")
    assert r.returncode == 0, r.stdout + r.stderr
    d = json.loads((tmp_path / "data" / "site-audit.json").read_text(encoding="utf-8"))
    assert d["pages"][0]["states"] == [] and d["clicks"] is None                    # по умолчанию кликов нет
    assert d["tokens"]["dark"]["from"]["--c-bg"] == "stylesheet:--paper"
    assert "--c-bg: rgb(20 20 22)" in (tmp_path / "mockups" / "tokens.css").read_text(encoding="utf-8")


# ---------------------------------------------------------------- набор компонентов: контраст в обеих темах

def kit_out(tmp_path, tokens_css):
    concepts = tmp_path / "mockups" / "concepts"
    concepts.mkdir(parents=True)
    shutil.copy(KIT / "_kit.css", concepts / "_kit.css")
    shutil.copy(KIT / "_base.html", concepts / "_base.html")
    shutil.copy(KIT / "kit-demo.html", concepts / "_kit-demo.html")
    (tmp_path / "mockups" / "tokens.css").write_text(tokens_css, encoding="utf-8")
    return tmp_path


@needs_pw
def test_kit_demo_contrast_both_themes(tmp_path):
    out = kit_out(tmp_path, "/* без токенов продукта — запасные значения набора */\n")
    r = node("shoot_mockups.mjs", out, "--kit")
    assert r.returncode == 0, r.stdout + r.stderr
    for key in ("_kit-demo", "_kit-demo-390x844", "_base"):
        rec = json.loads((out / "data" / ("mockups-check.%s.json" % key)).read_text(encoding="utf-8"))
        assert rec["ok"], (key, rec["problems"], rec["console_errors"][:5])
        assert not rec["overflow_x"]
    demo = json.loads((out / "data" / "mockups-check._kit-demo.json").read_text(encoding="utf-8"))
    assert demo["contrast"]["checked"] > 150 and demo["contrast"]["fails"] == 0
    assert (out / "mockups/concepts/_kit-demo-390x844.png").stat().st_size > 20000
    idx = out / "data" / "mockups-index.json"
    assert not idx.exists() or "_kit" not in idx.read_text(encoding="utf-8")         # набор не попадает в индекс


@needs_pw
def test_kit_demo_reports_bad_contrast(tmp_path):
    out = kit_out(tmp_path, ":root{--c-muted:#c8c8c8;--c-danger:#ff8a80;--c-on-danger:#ffffff}\n")
    r = node("shoot_mockups.mjs", out, "--kit", "--no-fail")
    assert r.returncode == 0, r.stdout + r.stderr
    rec = json.loads((out / "data" / "mockups-check._kit-demo.json").read_text(encoding="utf-8"))
    assert not rec["ok"] and rec["contrast"]["fails"] > 0 and any("контраст" in e for e in rec["console_errors"])


# ---------------------------------------------------------------- shoot_mockups: автообнаружение и параллельные запуски

def mockup_html(title, viewport=None, proposals=None):
    attrs = (' data-viewport="%s"' % viewport if viewport else "") + (' data-proposals="%s"' % proposals if proposals else "")
    return ('<!doctype html><html lang="ru"%s><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>%s</title></head><body><h1 id="t">%s</h1><button id="b" style="margin:40px">Действие</button>'
            '<div class="ps-concept-badge">Концепт, не существующая функция</div></body></html>') % (attrs, title, title)


@pytest.fixture
def mock_out(tmp_path):
    c = tmp_path / "mockups" / "concepts"
    c.mkdir(parents=True)
    (tmp_path / "data").mkdir()
    (c / "M01-a.html").write_text(mockup_html("Первый"), encoding="utf-8")
    (c / "M02-b.html").write_text(mockup_html("Второй макет", "390x844", "P001,P002"), encoding="utf-8")
    (c / "M03-c.html").write_text(mockup_html("Третий", "mobile"), encoding="utf-8")
    (c / "_base.html").write_text(mockup_html("Набор"), encoding="utf-8")
    (tmp_path / "data" / "mockups-index.json").write_text(json.dumps([{
        "key": "M01-a", "html": "mockups/concepts/M01-a.html", "png": "mockups/concepts/M01-a.png", "title": "Заголовок владельца",
        "proposals": ["P009"], "viewport": "1440x900", "kind": "concept"}], ensure_ascii=False), encoding="utf-8")
    return tmp_path


@needs_pw
def test_shoot_mockups_discovery_and_parallel_merge(mock_out):
    procs = [subprocess.Popen([NODE, str(NODE_DIR / "shoot_mockups.mjs"), str(mock_out), "--only", key, "--node-dir", PW_DIR],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for key in ("M02-b", "M03-c")]
    outs = [p.communicate(timeout=240) for p in procs]
    assert all(p.returncode == 0 for p in procs), outs
    idx = json.loads((mock_out / "data" / "mockups-index.json").read_text(encoding="utf-8"))
    keys = [i["key"] for i in idx]
    assert keys.count("M02-b") == 1 and keys.count("M03-c") == 1 and "_base" not in keys and len(idx) == 3
    m1 = idx[0]
    assert m1["title"] == "Заголовок владельца" and m1["proposals"] == ["P009"]                 # существующая запись не тронута
    m2 = next(i for i in idx if i["key"] == "M02-b")
    assert m2["viewport"] == "390x844" and m2["proposals"] == ["P001", "P002"] and m2["title"] == "Второй макет"
    assert next(i for i in idx if i["key"] == "M03-c")["viewport"] == "390x844"
    chk = json.loads((mock_out / "data" / "mockups-check.json").read_text(encoding="utf-8"))
    assert {i["key"] for i in chk["items"]} == {"M02-b", "M03-c"} and chk["summary"]["not_shot"] == 1
    assert (mock_out / "data" / "mockups-check.M02-b.json").exists() and (mock_out / "data" / "mockups-check.M03-c.json").exists()
    r = node("shoot_mockups.mjs", mock_out, "--only", "M01-a")
    assert r.returncode == 0, r.stdout + r.stderr
    chk = json.loads((mock_out / "data" / "mockups-check.json").read_text(encoding="utf-8"))
    assert {i["key"] for i in chk["items"]} == {"M01-a", "M02-b", "M03-c"} and chk["summary"]["ok"] == 3
    assert not list((mock_out / "data").glob("*.tmp")) and not (mock_out / "data" / ".mockups.lock").exists()


@needs_pw
def test_shoot_mockups_without_index_discovers(tmp_path):
    c = tmp_path / "mockups" / "concepts"
    c.mkdir(parents=True)
    (c / "M01-x.html").write_text(mockup_html("Икс"), encoding="utf-8")
    r = node("shoot_mockups.mjs", tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    idx = json.loads((tmp_path / "data" / "mockups-index.json").read_text(encoding="utf-8"))
    assert [i["key"] for i in idx] == ["M01-x"] and idx[0]["viewport"] == "1440x900"


# ---------------------------------------------------------------- measure_hotspots --draw

@needs_pw
def test_measure_hotspots_draw(mock_out, tmp_path):
    (mock_out / "design-refs").mkdir()
    card = mock_out / "design-refs" / "01-a.json"
    card.write_text(json.dumps({"file": "mockups/concepts/M01-a.html", "width": 1440, "height": 900}), encoding="utf-8")
    spec = tmp_path / "spec.json"
    spec.write_text(json.dumps([{"n": 1, "selector": "#t", "title": "Заголовок", "state": "new"},
                                {"n": 2, "selector": "#b", "title": "Кнопка", "state": "changed"}]), encoding="utf-8")
    drawn = tmp_path / "zones.png"
    r = node("measure_hotspots.mjs", mock_out, card, "--spec", spec, "--draw", drawn)
    assert r.returncode == 0, r.stdout + r.stderr
    assert drawn.stat().st_size > 2000
    clean = (mock_out / "design-refs" / "01-a.png").read_bytes()
    assert drawn.read_bytes() != clean                                                         # рамки нарисованы поверх
    assert len(json.loads(card.read_text(encoding="utf-8"))["hotspots"]) == 2
    again = tmp_path / "zones2.png"
    r = node("measure_hotspots.mjs", mock_out, card, "--draw", again)                         # только рисунок по записанным зонам
    assert r.returncode == 0, r.stdout + r.stderr
    assert again.stat().st_size > 2000 and (mock_out / "design-refs" / "01-a.png").read_bytes() == clean
