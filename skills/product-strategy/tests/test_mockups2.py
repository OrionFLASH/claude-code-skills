"""Тесты эпика E-MOCKUPS: мобильный набор (templates/mockup-kit/mobile, _icons.css), мост --c-* и громкая ошибка
запасных цветов, исправления набора (is-inline, --font-mono, метки «НОВОЕ», градиенты), shoot_mockups (--only не
пишет общие файлы, обновление записей discovered, <meta name="ps:…">, высота раскадровки, --contrast),
link_mockups (kind: component), measure_hotspots (screen, --full-page), check_flow.mjs, справочник shared.

Запуск: python3 -m pytest skills/product-strategy/tests/test_mockups2.py -q
Тесты с браузером пропускаются без Playwright (PS_NODE_DIR или scripts/node/node_modules).
"""
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from test_assemble import base, out, put_parts, codes  # noqa: F401  (фикстуры демо-прогона)

SKILL = Path(__file__).resolve().parents[1]
SCRIPTS = SKILL / "scripts"
NODE_DIR = SCRIPTS / "node"
KIT = SKILL / "templates" / "mockup-kit"
MOBILE = KIT / "mobile"


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


def py(script, *args):
    return subprocess.run([sys.executable, "-B", str(SCRIPTS / script), *map(str, args)], capture_output=True, text=True, timeout=180)


def jload(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def jdump(p, obj):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    Path(p).write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def kit_run(tmp_path, tokens_css="/* без токенов продукта */\n"):
    """Папка прогона с полным набором (десктоп + мобильный слой) как после копирования оркестратором."""
    c = tmp_path / "mockups" / "concepts"
    c.mkdir(parents=True)
    for f in ("_kit.css", "_icons.css", "_base.html"):
        shutil.copy(KIT / f, c / f)
    shutil.copy(KIT / "kit-demo.html", c / "_kit-demo.html")
    for f in ("_mobile.css", "_base-mobile.html", "_storyboard.html"):
        shutil.copy(MOBILE / f, c / f)
    shutil.copy(MOBILE / "kit-demo-mobile.html", c / "_kit-demo-mobile.html")
    (tmp_path / "mockups" / "tokens.css").write_text(tokens_css, encoding="utf-8")
    return tmp_path


def check(out_dir, key):
    return jload(out_dir / "data" / ("mockups-check.%s.json" % key))


# ---------------------------------------------------------------- шаблоны (без браузера)

def test_mobile_kit_files_offline_and_classes():
    for f in ("_mobile.css", "_base-mobile.html", "_storyboard.html", "kit-demo-mobile.html", "kit-demo-mobile.png", "storyboard.png"):
        assert (MOBILE / f).is_file(), f
    for f in [KIT / "_icons.css", KIT / "_kit.css", KIT / "kit-demo.html"] + [MOBILE / n for n in ("_mobile.css", "_base-mobile.html", "_storyboard.html", "kit-demo-mobile.html")]:
        text = f.read_text(encoding="utf-8")
        if f.suffix == ".html":
            text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
        assert not re.search(r"https?://", text), f.name                      # офлайн: без адресов
    css = (MOBILE / "_mobile.css").read_text(encoding="utf-8")
    for cls in (".pm-phone", ".pm-status", ".pm-appbar", ".pm-item", ".pm-list", ".pm-tabbar", ".pm-fab", ".pm-sheet", ".pm-grabber",
                ".pm-dialog", ".pm-snackbar", ".pm-notif", ".is-heads-up", ".pm-widget", ".is-lock", ".pm-lock-clock", ".is-home",
                ".pm-board", ".pm-frame", ".pm-cap", ".is-strip", ".pm-scrim"):
        assert cls in css, cls
    assert "--pm-w: 390px" in css and "--pm-h: 844px" in css
    assert not re.search(r"\.pm-body \{[^}]*overflow: hidden", css)            # метки «НОВОЕ» не обрезаются
    # иконки: галерея демо = набор в _icons.css
    icons = re.findall(r"^\.ps-i-([\w-]+) \{ --i: url\(\"data:image/svg\+xml,", (KIT / "_icons.css").read_text(encoding="utf-8"), re.M)
    demo = (MOBILE / "kit-demo-mobile.html").read_text(encoding="utf-8")
    listed = re.findall(r"'([\w-]+)'", demo.split("var ICONS = [", 1)[1].split("];", 1)[0])
    assert len(icons) >= 60 and listed == icons
    for f in ("_base-mobile.html", "_storyboard.html"):
        t = (MOBILE / f).read_text(encoding="utf-8")
        assert "ps-concept-badge" in t and "_mobile.css" in t and "_icons.css" in t and "../tokens.css" in t
    sb = (MOBILE / "_storyboard.html").read_text(encoding="utf-8")
    assert 'data-viewport="1720x1000"' in sb and sb.count('class="pm-frame"') == 4 and 'data-screen="4"' in sb and "is-inline" in sb


def test_kit_fixes_in_css():
    css = (KIT / "_kit.css").read_text(encoding="utf-8")
    assert re.search(r"\.ps-concept-badge\.is-inline \{[^}]*position: relative", css)
    mono = re.search(r"--font-mono: ([^;]+);", css).group(1)
    assert mono.index("Menlo") < mono.index("monospace") and "Consolas" in mono and '"SF Mono"' in mono
    assert re.search(r"\.ps-new::after, \.ps-changed::after \{[^}]*content: \"НОВОЕ\"", css) and ".ps-new.is-inside::after" in css
    assert not re.search(r"\.ps-list \{[^}]*overflow: hidden", css)
    assert "--k-muted-strong" in css and ".is-gradient .ps-muted" in css
    for bridge in ("var(--primary,", "var(--bg,", "var(--card,", "var(--text,", "var(--on-primary,", "var(--k-def-accent)"):
        assert bridge in css, bridge
    assert re.search(r'^\s*:root, \[data-theme="dark"\] \{\s*\n\s*--c-bg: var\(--bg', css, re.M)   # мост не на светлых поддеревьях


# ---------------------------------------------------------------- набор в браузере

@needs_pw
def test_mobile_kit_demo_shoots_clean(tmp_path):
    out_dir = kit_run(tmp_path)
    r = node("shoot_mockups.mjs", out_dir, "--kit")
    assert r.returncode == 0, r.stdout + r.stderr
    for key in ("_kit-demo-mobile", "_kit-demo-mobile-390x844", "_base-mobile", "_storyboard", "_kit-demo", "_base"):
        rec = check(out_dir, key)
        assert rec["ok"], (key, rec["problems"], rec["console_errors"][:5])
        assert not rec["overflow_x"] and rec["badge"]
    demo = check(out_dir, "_kit-demo-mobile")
    assert demo["contrast"]["checked"] > 200 and demo["contrast"]["fails"] == 0
    assert check(out_dir, "_kit-demo")["contrast"]["fails"] == 0
    assert any("запасной палитрой" in w for w in demo["warnings"])                  # пустой tokens.css — предупреждение, не FAIL
    assert check(out_dir, "_base-mobile")["viewport"] == "390x844"
    assert (out_dir / "mockups/concepts/_storyboard.png").stat().st_size > 50000
    assert not (out_dir / "data" / "mockups-index.json").exists()                     # --kit индекс не пишет


BRIDGE_TOKENS = """:root { --bg: #fbf7f0; --surface: #ffffff; --text: #22201c; --muted: #5f5a52; --border: #e3dccf; --primary: #9c3a0e; --on-primary: #ffffff; }
[data-theme="dark"] { --bg: #16130f; --surface: #201c17; --text: #f1ebe2; --muted: #b3aa9c; --border: #3a332a; --primary: #ff9a5c; --on-primary: #1b0d04; }
"""


@needs_pw
@pytest.mark.parametrize("tokens,ok,needle", [
    (BRIDGE_TOKENS, True, None),                                                     # мост из --primary/--bg/--text
    (":root { --paper: #fbf7f0; --ink: #22201c; --brand-color: #b4420f; }\n", False, "использован запасной цвет набора"),
    (":root { --c-bg: #fff; --c-surface: #fff; --c-text: #111; --c-muted: #555; --c-border: #ddd; --c-accent: 222 47% 11%; }\n", False, "не цвет"),
])
def test_bridge_and_loud_fallback(tmp_path, tokens, ok, needle):
    out_dir = kit_run(tmp_path, tokens)
    r = node("shoot_mockups.mjs", out_dir, "--kit", "--no-fail")
    assert r.returncode == 0, r.stdout + r.stderr
    rec = check(out_dir, "_base-mobile")
    assert rec["ok"] is ok, rec["problems"]
    if needle:
        assert any(needle in p for p in rec["problems"]) and needle in r.stdout
    else:
        assert not [c for c in rec["fallback_colors"] if c["core"]]                  # белый --surface продукта — не «запасной»
        demo = check(out_dir, "_kit-demo-mobile")
        assert demo["ok"], demo["problems"]


# ---------------------------------------------------------------- shoot_mockups: общие файлы, discovered, meta

def page(title, attrs="", head="", body=""):
    return ('<!doctype html><html lang="ru"%s><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">%s'
            '<title>%s</title></head><body><h1>%s</h1>%s<div class="ps-concept-badge">Концепт, не существующая функция</div></body></html>') % (attrs, head, title, title, body)


@needs_pw
def test_shoot_only_keeps_shared_files_and_updates_discovered(tmp_path):
    c = tmp_path / "mockups" / "concepts"
    c.mkdir(parents=True)
    (c / "M01-a.html").write_text(page("Первый"), encoding="utf-8")
    (c / "M02-b.html").write_text(page("Второй", head='<meta name="ps:viewport" content="390x844"><meta name="ps:proposals" content="P001, P002">'
                                                  '<meta name="ps:title" content="Второй из meta">'), encoding="utf-8")
    (c / "M00-design-language.html").write_text(page("Язык", ' data-kind="kit"'), encoding="utf-8")
    manual = {"key": "M09-manual", "html": "mockups/concepts/M09-manual.html", "png": "mockups/concepts/M09-manual.png", "title": "Ручная",
              "proposals": ["P009"], "viewport": "1440x900", "kind": "concept"}
    (c / "M09-manual.html").write_text(page("Ручная", ' data-viewport="390x844"'), encoding="utf-8")
    jdump(tmp_path / "data" / "mockups-index.json", [manual, dict(manual)])          # дубль ключа
    r = node("shoot_mockups.mjs", tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    idx = {i["key"]: i for i in jload(tmp_path / "data" / "mockups-index.json")}
    assert len(jload(tmp_path / "data" / "mockups-index.json")) == 4                 # слияние по ключу
    assert idx["M02-b"]["viewport"] == "390x844" and idx["M02-b"]["proposals"] == ["P001", "P002"] and idx["M02-b"]["title"] == "Второй из meta"
    assert idx["M00-design-language"]["kind"] == "component" and idx["M09-manual"]["viewport"] == "1440x900"   # ручная не тронута
    assert check(tmp_path, "M00-design-language")["full_page"]
    index_before = (tmp_path / "data" / "mockups-index.json").read_text(encoding="utf-8")
    agg_before = (tmp_path / "data" / "mockups-check.json").read_text(encoding="utf-8")
    # агент меняет размер и добавляет новый макет — --only не трогает общие файлы
    (c / "M02-b.html").write_text(page("Второй", ' data-viewport="1720x1000" data-proposals="P003"'), encoding="utf-8")
    (c / "M03-new.html").write_text(page("Новый", ' data-viewport="390x844"'), encoding="utf-8")
    r = node("shoot_mockups.mjs", tmp_path, "--only", "M02-b,M03-new")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "не изменены" in r.stdout
    assert (tmp_path / "data" / "mockups-index.json").read_text(encoding="utf-8") == index_before
    assert (tmp_path / "data" / "mockups-check.json").read_text(encoding="utf-8") == agg_before
    assert check(tmp_path, "M02-b")["viewport"] == "1720x1000" and check(tmp_path, "M03-new")["viewport"] == "390x844"
    r = node("shoot_mockups.mjs", tmp_path, "--no-index")
    assert r.returncode == 0 and (tmp_path / "data" / "mockups-index.json").read_text(encoding="utf-8") == index_before
    assert node("shoot_mockups.mjs", tmp_path, "--only", "M77-ghost").returncode == 2
    # оркестратор после волны: discovered-запись обновлена из HTML, новая добавлена, агрегат по всем ключам
    r = node("shoot_mockups.mjs", tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    idx = {i["key"]: i for i in jload(tmp_path / "data" / "mockups-index.json")}
    assert idx["M02-b"]["viewport"] == "1720x1000" and idx["M02-b"]["proposals"] == ["P003"] and "M03-new" in idx
    assert {i["key"] for i in jload(tmp_path / "data" / "mockups-check.json")["items"]} == set(idx)


@needs_pw
def test_storyboard_taller_than_viewport_and_contrast_flag(tmp_path):
    out_dir = kit_run(tmp_path, BRIDGE_TOKENS)
    c = out_dir / "mockups" / "concepts"
    sb = (c / "_storyboard.html").read_text(encoding="utf-8").replace("1720x1000", "1720x900")
    (c / "M01-story.html").write_text(sb, encoding="utf-8")
    (c / "M02-low.html").write_text(page("Низкий контраст", body='<p style="color:#bbb;background:#fff">Бледный текст на белом</p>'), encoding="utf-8")
    r = node("shoot_mockups.mjs", out_dir, "--only", "M01-story,M02-low", "--no-fail")
    assert r.returncode == 0, r.stdout + r.stderr
    story = check(out_dir, "M01-story")
    assert not story["ok"] and any("выше viewport" in p and "раскадровка" in p for p in story["problems"])
    assert check(out_dir, "M02-low")["ok"]                                           # без --contrast контраст не проверяется
    r = node("shoot_mockups.mjs", out_dir, "--only", "M01-story,M02-low", "--full-page", "--contrast", "--no-fail")
    assert check(out_dir, "M01-story")["ok"], check(out_dir, "M01-story")["problems"]
    low = check(out_dir, "M02-low")
    assert not low["ok"] and low["contrast"]["fails"] >= 1


# ---------------------------------------------------------------- link_mockups: карточка общего языка

def test_link_mockups_skips_component_cards(out):  # noqa: F811
    props = jload(out / "data" / "proposals.json")
    for p in props:
        p.pop("mockup", None)
        p.pop("mockups", None)
    jdump(out / "data" / "proposals.json", props)
    ids = [p["id"] for p in props]
    jdump(out / "design-refs" / "00-design-language.json", {"file": "mockups/concepts/_app-demo.html", "kind": "component", "title": "Общий язык",
                                                            "proposals": ids[:40], "hotspots": [], "shared": ["Кнопки"]})
    jdump(out / "design-refs" / "03-shared-off.json", {"file": "mockups/concepts/M03-demo.html", "links": False, "title": "без связей",
                                                       "proposals": ids[40:45], "hotspots": []})
    idx = jload(out / "data" / "mockups-index.json")
    idx.append({"key": "M00-design-language", "html": "mockups/concepts/M00-design-language.html", "png": "", "title": "Язык",
                "proposals": ids[:30], "viewport": "1440x900", "kind": "component"})
    jdump(out / "data" / "mockups-index.json", idx)
    r = py("link_mockups.py", out, "--json")
    assert r.returncode == 0, r.stderr
    rep = json.loads(r.stdout)
    got = {p["id"]: p for p in jload(out / "data" / "proposals.json")}
    used = {m for p in got.values() for m in (p.get("mockups") or [])}
    assert not any("_app-demo" in m or "M00-design-language" in m for m in used)
    assert sum(1 for p in got.values() if p.get("mockup")) <= 6                         # только настоящие макеты демо (6 шт.)
    assert any("00-design-language" in n and "служебная" in n for n in rep["notes"])
    assert any("M00-design-language" in n for n in rep["notes"]) and not any("_app-demo" in w for w in rep["warnings"])
    put_parts(out, {})
    r = py("assemble_strategy.py", out, "--insert-mockups")
    rep = jload(out / "build" / "assemble-report.json")
    assert "bad_mockup" not in codes(rep), [e for e in rep["errors"] if e["code"] == "bad_mockup"][:3]


# ---------------------------------------------------------------- measure_hotspots: раскадровка и длинная страница

@needs_pw
def test_measure_hotspots_screen_and_full_page(tmp_path):
    out_dir = kit_run(tmp_path, BRIDGE_TOKENS)
    jdump(out_dir / "design-refs" / "01-story.json", {"file": "mockups/concepts/_storyboard.html", "width": 1720, "height": 1000})
    spec = tmp_path / "spec.json"
    jdump(spec, [{"n": 1, "selector": '.pm-frame[data-screen="3"] .pm-sheet .ps-btn.is-primary', "title": "Сохранить"},
                 {"n": 2, "selector": '.pm-frame[data-screen="4"] .pm-notif', "title": "Уведомление", "screen": 7}])
    drawn = tmp_path / "zones.png"
    r = node("measure_hotspots.mjs", out_dir, out_dir / "design-refs" / "01-story.json", "--spec", spec, "--draw", drawn)
    assert r.returncode == 0, r.stdout + r.stderr
    hs = {h["n"]: h for h in jload(out_dir / "design-refs" / "01-story.json")["hotspots"]}
    assert hs[1]["screen"] == 3 and hs[2]["screen"] == 7 and hs[1]["x"] > 2 * 390        # кадр 3 — правее двух телефонов
    assert drawn.stat().st_size > 5000 and "к3" in r.stdout
    # длинная страница: зона ниже первого экрана получает координаты от начала страницы
    jdump(out_dir / "design-refs" / "02-long.json", {"file": "mockups/concepts/_kit-demo-mobile.html", "width": 2120, "height": 1000})
    jdump(spec, [{"n": 1, "selector": "#kd-icons", "title": "Иконки", "state": "shared"},
                 {"n": 2, "selector": "[data-theme=dark] .pm-dialog", "title": "Диалог в тёмной теме"}])
    r = node("measure_hotspots.mjs", out_dir, out_dir / "design-refs" / "02-long.json", "--spec", spec, "--full-page")
    assert r.returncode == 0, r.stdout + r.stderr
    card = jload(out_dir / "design-refs" / "02-long.json")
    assert card["full_page"] is True and card["viewport"] == "2120x1000" and card["height"] > 1500
    hs = {h["n"]: h for h in card["hotspots"]}
    assert hs[1]["y"] > 1000 and hs[1]["y"] + hs[1]["h"] <= card["height"]
    assert hs[2]["screen"] == 8                                                          # 5 светлых кадров + 3-й тёмный
    again = tmp_path / "again.png"
    assert node("measure_hotspots.mjs", out_dir, out_dir / "design-refs" / "02-long.json", "--draw", again).returncode == 0
    assert again.stat().st_size > 5000


# ---------------------------------------------------------------- check_flow.mjs

GOOD_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 520 160" width="520" height="160" font-family="Arial" font-size="14">
<g data-node="ok:1"><rect x="20" y="40" width="180" height="50" fill="#eef"/><text x="30" y="70">Первый визит</text></g>
<g data-node="ok:2"><rect x="320" y="40" width="180" height="50" fill="#efe"/><text x="330" y="70">Активация</text></g>
<line x1="200" y1="65" x2="320" y2="65" stroke="#333"/><text x="225" y="55" font-size="12">7 дней</text></svg>"""
BAD_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 600 300" width="600" height="300" font-family="Arial" font-size="14">
<g data-node="bad:1"><rect x="20" y="40" width="160" height="50" fill="#eef"/><text x="30" y="70">Первый визит на сайт продукта</text></g>
<g data-node="bad:2"><rect x="150" y="60" width="160" height="50" fill="#efe"/><text x="160" y="90">Активация</text></g>
<g data-node="bad:3"><rect x="380" y="40" width="160" height="50" fill="#fee"/><text x="390" y="70">Оплата</text></g>
<text x="330" y="60">7 дней</text><text x="340" y="62">триал</text><text x="400" y="55">на блоке</text>
<text x="560" y="200">обрезанная подпись</text></svg>"""


@needs_pw
def test_check_flow(tmp_path):
    (tmp_path / "charts" / "flows").mkdir(parents=True)
    (tmp_path / "charts" / "flows" / "ok.svg").write_text(GOOD_SVG, encoding="utf-8")
    (tmp_path / "charts" / "flows" / "bad.svg").write_text(BAD_SVG, encoding="utf-8")
    jdump(tmp_path / "data" / "flows.json", [
        {"key": "ok", "title": "Хорошая", "svg": "charts/flows/ok.svg", "nodes": [{"id": "ok:1"}, {"id": "ok:2"}]},
        {"key": "bad", "title": "Плохая", "svg": "charts/flows/bad.svg", "nodes": [{"id": "bad:1"}, {"id": "bad:2"}, {"id": "bad:4"}]}])
    draw = tmp_path / "draw"
    r = node("check_flow.mjs", tmp_path, "--draw", draw)
    assert r.returncode == 1, r.stdout + r.stderr
    rep = jload(tmp_path / "data" / "flows-check.json")
    by = {i["key"]: i for i in rep["items"]}
    assert by["ok"]["ok"] and by["ok"]["nodes"] == 2 and not by["ok"]["warnings"]
    types = {p["type"] for p in by["bad"]["problems"]}
    assert types == {"node_overlap", "text_overflow", "text_overlap", "label_on_node", "text_clipped"}, types
    assert any("bad:4" in w for w in by["bad"]["warnings"]) and any("bad:3" in w for w in by["bad"]["warnings"])
    assert rep["summary"] == {"flows": 2, "ok": 1, "failed": 1, "problems": len(by["bad"]["problems"]), "warnings": 2}
    assert (draw / "bad.png").stat().st_size > 2000 and not (draw / "ok.png").exists()
    r = node("check_flow.mjs", tmp_path, "--only", "ok")
    assert r.returncode == 0, r.stdout
    assert {i["key"] for i in jload(tmp_path / "data" / "flows-check.json")["items"]} == {"ok", "bad"}      # --only сливает с прежним
    assert node("check_flow.mjs", tmp_path, "--only", "ghost").returncode == 2


@pytest.mark.skipif(not NODE, reason="нет node")
def test_check_flow_without_playwright_exits_3(tmp_path):
    (tmp_path / "charts" / "flows").mkdir(parents=True)
    (tmp_path / "charts" / "flows" / "ok.svg").write_text(GOOD_SVG, encoding="utf-8")
    empty = tmp_path / "empty"
    empty.mkdir()
    r = subprocess.run([NODE, str(NODE_DIR / "check_flow.mjs"), str(tmp_path), "--node-dir", str(empty)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 3 and "нет playwright" in r.stderr


# ---------------------------------------------------------------- справочник shared (design-refs README)

def test_design_refs_shared_dictionary(tmp_path):
    d = tmp_path / "design-refs"
    card = {"file": "mockups/concepts/M01.html", "title": "т", "proposals": ["P001"], "hotspots": []}
    jdump(d / "00-design-language.json", dict(card, kind="component", shared=["Кнопки (ap-btn)", {"name": "Нижний лист (ap-sheet)", "desc": "лист с ручкой"},
                                                                          "Сегментный переключатель (ap-seg)"]))
    jdump(d / "01-a.json", dict(card, shared=["кнопки", "Сегментный переключатель — карточка 00", "Нижний лист с затемнением — карточка 00"]))
    jdump(d / "02-b.json", dict(card, shared=["Кнопки (ap-btn)", "Шапка приложения"]))
    for s in ("00-design-language", "01-a", "02-b"):
        (d / (s + ".md")).write_text("# к\n", encoding="utf-8")
    r = py("build_design_refs_readme.py", tmp_path, "--json")
    assert r.returncode == 0, r.stderr
    rep = json.loads(r.stdout)
    dic = jload(tmp_path / "build" / "shared-elements.json")
    assert dic["source"] == "design-refs/00-design-language.json" and dic["elements"]["Нижний лист (ap-sheet)"] == "лист с ручкой"
    assert set(dic["elements"]) == {"Кнопки (ap-btn)", "Нижний лист (ap-sheet)", "Сегментный переключатель (ap-seg)"}
    unknown = {(u["card"], u["name"]) for u in rep["shared_unknown"]}
    assert unknown == {("01-a", "Нижний лист с затемнением — карточка 00"), ("02-b", "Шапка приложения")}
    assert "не из справочника" in r.stderr
    text = (d / "README.md").read_text(encoding="utf-8")
    row = next(line for line in text.splitlines() if line.startswith("| Кнопки (ap-btn)"))
    assert "`00-design-language`, `01-a`, `02-b`" in row                                # «кнопки» и «Кнопки (ap-btn)» — одна строка
    assert "Имена не из справочника" in text and "похоже на «Нижний лист (ap-sheet)»" in text
    # описание, добавленное в справочник вручную, сохраняется при пересборке
    dic["elements"]["Кнопки (ap-btn)"] = "основная и вторичная"
    jdump(tmp_path / "build" / "shared-elements.json", dic)
    assert py("build_design_refs_readme.py", tmp_path).returncode == 0
    assert jload(tmp_path / "build" / "shared-elements.json")["elements"]["Кнопки (ap-btn)"] == "основная и вторичная"
