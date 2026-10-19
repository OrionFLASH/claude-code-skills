"""WP-F (1.5): набор макетов 1.3 и проверки shoot_mockups.mjs по фидбэкам прогонов режима идеи.

FB-032 — баги и недостающие компоненты набора (kit-demo без обрезаний на 390 и 1440 px, всё описано в README);
FB-033 — одно правило и один текст бейджа (поиск по templates/ не находит двух текстов; проверка по классу);
FB-007 — чекпоинт выбора направления в брифе; SM 9 — directions_count, «компоновка и метафора», режимы и токены на
режим, галерея, pointer/touch-first (+ автопроверка --targets), мобильный задел, подсветка data-hs (12–25 элементов);
SM 6.4 — вторая тема (--other-theme), SVG-контраст, --only с G8-xx, .ps-segmented без обрезки, цели ≥ 32 px,
недостающие компоненты, локальная дата.

Запуск: python3 -m pytest tests/test_design_fb_kit.py -q -p no:cacheprovider
Тесты с браузером пропускаются без Playwright (PS_NODE_DIR или scripts/node/node_modules).
"""
import json
import os
import re
import shutil
import subprocess
from datetime import date
from pathlib import Path

import pytest

SKILL = Path(__file__).resolve().parents[1]
SCRIPTS = SKILL / "scripts"
NODE_DIR = SCRIPTS / "node"
KIT = SKILL / "templates" / "mockup-kit"
MOBILE = KIT / "mobile"
BRIEFS = SKILL / "templates" / "briefs"


def find_node_dir():
    for d in [os.environ.get("PS_NODE_DIR"), str(NODE_DIR), str(Path.home() / ".cache" / "product-strategy" / "node")]:
        if d and (Path(d) / "node_modules" / "playwright" / "package.json").exists():
            return d
    return None


NODE = shutil.which("node")
PW_DIR = find_node_dir()
needs_pw = pytest.mark.skipif(not NODE or not PW_DIR, reason="playwright недоступен (PS_NODE_DIR или scripts/node/node_modules)")


def node(script, *args, timeout=300):
    return subprocess.run([NODE, str(NODE_DIR / script), *map(str, args), "--node-dir", PW_DIR], capture_output=True, text=True, timeout=timeout)


def jload(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def check(out_dir, key):
    return jload(out_dir / "data" / ("mockups-check.%s.json" % key))


def kit_run(tmp_path, tokens_css="/* без токенов продукта */\n"):
    c = tmp_path / "mockups" / "concepts"
    c.mkdir(parents=True)
    for f in ("_kit.css", "_icons.css", "_base.html", "_hotspots.js"):
        shutil.copy(KIT / f, c / f)
    shutil.copy(KIT / "kit-demo.html", c / "_kit-demo.html")
    for f in ("_mobile.css", "_base-mobile.html", "_storyboard.html"):
        shutil.copy(MOBILE / f, c / f)
    shutil.copy(MOBILE / "kit-demo-mobile.html", c / "_kit-demo-mobile.html")
    (tmp_path / "mockups" / "tokens.css").write_text(tokens_css, encoding="utf-8")
    return tmp_path


# ---------------------------------------------------------------- FB-033: один текст бейджа во всём templates/

BADGE_RE = re.compile(r"Концепт(?:\s+продукта)?,\s*не\s+существующая\s+функция")


def test_fb033_single_badge_text_in_templates():
    # файлы WP-F: набор и брифы дизайна (прочие шаблоны — запрос к их владельцам в docs/plans/wp-f-requests.md)
    found = {}
    own = [f for f in KIT.rglob("*")] + [BRIEFS / n for n in ("concept-design.md", "mockups.md", "design-refs.md", "competitor-cards.md")]
    for f in own:
        if f.is_file() and f.suffix in (".md", ".html", ".css", ".js"):
            for m in BADGE_RE.finditer(f.read_text(encoding="utf-8")):
                found.setdefault(m.group(0), set()).add(str(f.relative_to(SKILL)))
    assert set(found) == {"Концепт, не существующая функция"}, found
    readme = (KIT / "README.md").read_text(encoding="utf-8")
    assert "одна константа" in readme.lower() or "одно правило и одна константа" in readme.lower()
    assert "is-strip" in readme and "is-above-nav" in readme and "is-inline" in readme
    # бриф дизайна и бриф макетов согласованы с README: телефон — is-strip, проверка — по классу, не по тексту
    for b in ("concept-design.md", "mockups.md"):
        t = (BRIEFS / b).read_text(encoding="utf-8")
        assert "is-strip" in t and "ps-concept-badge" in t, b
    cd = (BRIEFS / "concept-design.md").read_text(encoding="utf-8")
    assert "grep -L 'class=\"ps-concept-badge" in cd and "grep -L 'Концепт" not in cd
    assert "на мобильных — над нижней панелью (`is-above-nav`)" not in cd


# ---------------------------------------------------------------- FB-032 / SM 6.4: набор (без браузера)

def test_fb032_kit_css_fixes_and_components():
    css = (KIT / "_kit.css").read_text(encoding="utf-8")
    assert re.search(r"\.ps-badge \{[^}]*flex-shrink: 0", css)                               # бейдж не сжимается
    seg = re.search(r"\.ps-segmented \{([^}]*)\}", css).group(1)
    assert "flex-wrap: wrap" in seg and "overflow-x" not in seg                               # варианты не прячутся
    assert re.search(r"\.ps-segmented\.is-scroll \{[^}]*overflow-x: auto", css)
    assert ".ps-topbar .ps-brand" in css                                                      # бренд без отступов меню
    assert ".ps-brand-mark.is-2" in css
    assert ".ps-topbar .ps-row, .ps-top .ps-row" in css
    assert "flex: 1 1 40%" not in css                                                         # шаги не 2+1
    # цели ≥ 32 px: прежние 28/30 px заменены на --k-target
    for sel in (r"\.ps-segmented > \*", r"\.ps-chip", r"\.ps-switch, \.ps-check, \.ps-radio", r"\.ps-btn\.is-small"):
        body = re.search(sel + r" \{([^}]*)\}", css).group(1)
        assert "var(--k-target)" in body and not re.search(r"min-height: (28|30)px", body), sel
    assert ":root { --k-target: 32px; }" in css and "@media (max-width: 640px) { :root { --k-target: 44px; } }" in css
    for cls in (".ps-site-header", ".ps-site-footer", ".ps-actionbar", ".ps-counter", ".ps-yes", ".ps-no", ".ps-unk", ".ps-chart",
                ".ps-legend", ".ps-level.is-target", ".ps-level.is-stop", ".ps-kbd", ".ps-slider", ".ps-fresh.is-stale", ".ps-stepper",
                ".ps-msg.is-me", ".ps-fn", ".ps-footnotes", "--k-chart-1"):
        assert cls in css, cls
    assert ":root, [data-theme], [data-mode] {" in css                                        # производные цвета режима
    mob = (MOBILE / "_mobile.css").read_text(encoding="utf-8")
    assert ".pm-actionbar" in mob and ".pm-phone:has(.pm-actionbar) .pm-snackbar" in mob     # снекбар над своей панелью
    assert ".pm-phone:not(:has(.pm-tabbar)) .pm-snackbar" in mob and ".pm-chips.is-scroll" in mob
    # иконки undo, box, coin, wifi-off — в наборе, в шапке и в галерее демо
    icons = re.findall(r"^\.ps-i-([\w-]+) \{ --i:", (KIT / "_icons.css").read_text(encoding="utf-8"), re.M)
    assert {"undo", "box", "coin", "wifi-off"} <= set(icons) and len(icons) == 80
    assert "Набор (80)" in (KIT / "_icons.css").read_text(encoding="utf-8")
    demo = (MOBILE / "kit-demo-mobile.html").read_text(encoding="utf-8")
    assert re.findall(r"'([\w-]+)'", demo.split("var ICONS = [", 1)[1].split("];", 1)[0]) == icons
    # каждый новый компонент показан в демо и описан в README
    kd = (KIT / "kit-demo.html").read_text(encoding="utf-8") + demo
    readme = (KIT / "README.md").read_text(encoding="utf-8")
    for cls in ("ps-site-header", "ps-site-footer", "ps-actionbar", "ps-counter", "ps-yes", "ps-unk", "ps-chart", "ps-legend", "ps-level",
                "ps-kbd", "ps-slider", "ps-fresh", "ps-stepper", "ps-msg", "ps-fn", "ps-footnotes", "pm-actionbar", "ps-brand-mark is-2"):
        assert cls in kd, cls
        assert cls.split()[0] in readme, cls
    assert "undo" in readme and "wifi-off" in readme
    seg_in_top = re.search(r'class="ps-topbar".*?class="ps-segmented"', (KIT / "kit-demo.html").read_text(encoding="utf-8"), re.S)
    assert seg_in_top                                                                         # сценарий бага в демо
    for f in ("_hotspots.js", "gallery.html", "tokens-mode.css"):
        assert (KIT / f).is_file() and not re.search(r"https?://", re.sub(r"<!--.*?-->|/\*.*?\*/", "", (KIT / f).read_text(encoding="utf-8"), flags=re.S)), f


# ---------------------------------------------------------------- FB-007 / SM 9: бриф дизайна и справочник

def test_fb007_sm9_concept_design_brief_and_reference():
    t = (BRIEFS / "concept-design.md").read_text(encoding="utf-8")
    for needle in ("C8a", "C8-ask", "C8b", "mockup_kit.py choose", "mockup_kit.py gate", "directions_count", "компоновкой и метафорой, а не цветом",
                   "## Направление A — «Название»", "## Рекомендация", "tokens-<режим>.css", "data-mode", "mockup_kit.py gallery",
                   "data-variant", "data-screen-id", "mobile-later", "12–25 элементов", "_hotspots.js", "data-hs-what", "pointer_first",
                   "data-drag-alt", "НУЖНО-ПРЕДЛОЖЕНИЕ", "РАСХОЖДЕНИЕ", "demo-canon.json", "Набор уже скопирован", "--other-theme"):
        assert needle in t, needle
    assert "скопировать **без правок** `_kit.css`" not in t                                   # набор копирует скрипт (FB-008)
    assert "три направления языка дизайна" not in t and "из трёх" not in t
    m = (BRIEFS / "mockups.md").read_text(encoding="utf-8")
    for needle in ("Набор уже скопирован", "12–25 элементов", "--targets", "--other-theme", "НУЖНО-ПРЕДЛОЖЕНИЕ", "ps-chart", "G8-xx"):
        assert needle in m, needle
    d = (BRIEFS / "design-refs.md").read_text(encoding="utf-8")
    assert "НУЖНО-ПРЕДЛОЖЕНИЕ: <заголовок> | <категория> | <связанные P-id через запятую>" in d
    assert "РАСХОЖДЕНИЕ: <P-id> | <ключ макета Mxx> | <суть>" in d and "--collect-gaps" in d and "hotspots.zones" in d
    ref = (SKILL / "references" / "design.md").read_text(encoding="utf-8")
    for needle in ("## 2.1. Дизайн-этап режима идеи", "## 3.1. Принцип взаимодействия", "mockup_kit.py init", "mockup_kit.py verify",
                   "design_gate", "chosen_by", "--collect-gaps", "--remap-drafts", "--index-only", "--other-theme", "Мобильный задел"):
        assert needle in ref, needle


# ---------------------------------------------------------------- браузер: набор чистый на 1440 и 390 px

@needs_pw
def test_fb032_kit_demo_clean_at_390_and_1440(tmp_path):
    out = kit_run(tmp_path)
    r = node("shoot_mockups.mjs", out, "--kit")
    assert r.returncode == 0, r.stdout + r.stderr
    for key in ("_kit-demo", "_kit-demo-390x844", "_kit-demo-mobile", "_kit-demo-mobile-390x844", "_base", "_base-mobile", "_storyboard"):
        rec = check(out, key)
        assert rec["ok"], (key, rec["problems"])
        assert rec["layout"] == [], (key, rec["layout"][:3])                                 # --layout сам в --kit
        assert rec["targets"]["small_total"] == 0 and rec["targets"]["checked"] > 5, key      # --targets сам в --kit
        assert not rec.get("badge_truncated") and rec["badge_by"] == "class"
    assert check(out, "_kit-demo-390x844")["targets"]["min"] == 44 and check(out, "_kit-demo")["targets"]["min"] == 32


# ---------------------------------------------------------------- браузер: новые проверки shoot_mockups

def page(body, attrs=' data-viewport="1440x900"', head=""):
    return ('<!doctype html><html lang="ru"%s><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>т</title><link rel="stylesheet" href="../tokens.css"><link rel="stylesheet" href="_kit.css">%s</head><body>%s</body></html>') % (attrs, head, body)


BADGE = '<div class="ps-concept-badge">Концепт, не существующая функция · Тест</div>'
TOKENS = """:root[data-theme="dark"], [data-theme="dark"]:not(:root) { --c-bg: #111316; --c-surface: #191c20; --c-text: #e7e9ec; --c-muted: #a2a9b3; --c-border: #30353c; --c-accent: #7ea2ff; --c-on-accent: #0b1020; }
:root, [data-theme="light"] { --c-bg: #fbf7f0; --c-surface: #ffffff; --c-text: #22201c; --c-muted: #5f5a52; --c-border: #e3dccf; --c-accent: #9c3a0e; --c-on-accent: #ffffff; }
"""


@needs_pw
def test_sm64_layout_targets_badge_svg_hotspots(tmp_path):
    out = kit_run(tmp_path, TOKENS)
    c = out / "mockups" / "concepts"
    # 1) обрезанные кнопки: старое поведение сегментов (скрытая прокрутка) и вылезающий ребёнок однострочного ряда
    (c / "M01-layout.html").write_text(page(BADGE + '<div class="ps-topbar"><div class="ps-row" style="width:300px">'
        '<div class="ps-segmented" style="overflow-x:auto;flex-wrap:nowrap;flex-shrink:1;min-width:0"><button>Один</button><button>Два</button><button>Три</button><button>Четыре</button><button>Пять</button></div>'
        '<button class="ps-btn is-primary">Кнопка</button></div></div>'
        '<div style="display:flex;width:200px;overflow:hidden"><span style="flex:none;width:320px">слишком широкий</span></div>'), encoding="utf-8")
    # 2) мелкие цели и перетаскивание без кнопок; ссылка в тексте — исключение
    (c / "M02-targets.html").write_text(page(BADGE + '<button style="all:unset;width:20px;height:20px;display:inline-block">x</button>'
        '<p>Текст со <a href="#">ссылкой</a> внутри.</p><div draggable="true" style="width:200px;height:60px">карточка</div>'
        '<div draggable="true" data-drag-alt="#up" style="width:200px;height:60px">вторая</div><button id="up" class="ps-btn">Выше</button>'), encoding="utf-8")
    # 3) обрезанный бейдж в полосе телефона и бейдж только по тексту
    (c / "M03-badge.html").write_text(page('<div class="pm-phone"><div class="ps-concept-badge is-strip">Концепт, не существующая функция · очень длинное рабочее название продукта · 2026-10-19 · ещё текст</div></div>',
        ' data-viewport="390x844"', '<link rel="stylesheet" href="_mobile.css">'), encoding="utf-8")
    (c / "M04-text-badge.html").write_text(page('<div style="position:fixed;top:0">Концепт, не существующая функция</div><p>старый макет</p>'), encoding="utf-8")
    # 4) SVG: светлый текст на светлой заливке фигуры (раньше не видно), подпись HTML поверх тёмной SVG-фигуры
    (c / "M05-svg.html").write_text(page(BADGE + '<svg width="300" height="80" viewBox="0 0 300 80"><rect x="0" y="0" width="300" height="80" fill="#f2f2f2"/>'
        '<text x="10" y="40" fill="#d0d0d0" font-size="14">бледная подпись</text></svg>'
        '<div style="position:relative;width:300px;height:60px"><svg width="300" height="60" style="position:absolute;inset:0"><rect width="300" height="60" fill="#101010"/></svg>'
        '<span style="position:relative;color:#202020">тёмный текст на тёмном</span></div>'), encoding="utf-8")
    # 5) подсветка элементов + черновой id G8-01 в data-proposals
    hs = "".join('<button class="ps-btn" data-hs="b%d" data-hs-title="Кнопка %d" data-hs-what="что" data-hs-why="зачем" data-hs-p="P00%d">к%d</button>' % (i, i, i, i) for i in range(1, 4))
    (c / "M06-hs.html").write_text(page(BADGE + hs + '<span data-hs="b1">часть</span><script src="_hotspots.js"></script>', ' data-viewport="1440x900" data-proposals="P001,G8-01"'), encoding="utf-8")
    keys = "M01-layout,M02-targets,M03-badge,M04-text-badge,M05-svg,M06-hs"
    r = node("shoot_mockups.mjs", out, "--only", keys, "--layout", "--targets", "--contrast", "--hotspots", "3", "--no-fail")
    assert r.returncode == 0, r.stdout + r.stderr
    lay = check(out, "M01-layout")
    types = {x["type"] for x in lay["layout"]}
    assert types == {"hidden_scroll", "flex_overflow"}, lay["layout"]
    assert any("обрезаны" in p for p in lay["problems"])
    tg = check(out, "M02-targets")["targets"]
    assert tg["small_total"] == 1 and tg["small"][0]["w"] == 20 and tg["min"] == 32            # ссылка в тексте не считается
    assert len(tg["drag_without_buttons"]) == 1                                                # вторая — с data-drag-alt
    b = check(out, "M03-badge")
    assert b["badge_by"] == "class" and b["badge_truncated"] and any("обрезан" in p for p in b["problems"])
    assert b["targets"]["min"] == 44
    tb = check(out, "M04-text-badge")
    assert tb["badge"] and tb["badge_by"] == "text" and any("без класса .ps-concept-badge" in w for w in tb["warnings"])
    sv = check(out, "M05-svg")
    assert sv["contrast"]["svg"] >= 1 and sv["contrast"]["fails"] >= 2, sv["contrast"]
    h = check(out, "M06-hs")
    assert h["ok"], h["problems"]
    assert h["hotspots"]["count"] == 3 and h["hotspots"]["zones"][0]["p"] == ["P001"] and h["hotspots"]["zones"][0]["w"] > 0
    assert h["date"] == date.today().isoformat()                                              # локальная дата
    idx = subprocess.run(["python3", "-B", str(SCRIPTS / "link_mockups.py"), str(out), "--index-only"], capture_output=True, text=True)
    assert idx.returncode == 0, idx.stderr
    assert next(i for i in jload(out / "data" / "mockups-index.json") if i["key"] == "M06-hs")["proposals"] == ["P001", "G8-01"]
    # меньше --hotspots — замечание
    r = node("shoot_mockups.mjs", out, "--only", "M06-hs", "--hotspots", "12", "--no-fail")
    assert any("data-hs 3 < 12" in p for p in check(out, "M06-hs")["problems"])


@needs_pw
def test_sm64_other_theme_and_pointer_first_from_run_config(tmp_path):
    out = kit_run(tmp_path, TOKENS)
    c = out / "mockups" / "concepts"
    (c / "M01-ok.html").write_text(page(BADGE + '<div class="ps-card"><p class="ps-muted">Текст</p><button class="ps-btn is-primary">Ок</button></div>'), encoding="utf-8")
    r = node("shoot_mockups.mjs", out, "--only", "M01-ok", "--other-theme", "--contrast")
    assert r.returncode == 0, r.stdout + r.stderr
    rec = check(out, "M01-ok")
    assert rec["other_theme"]["theme"] == "dark" and rec["other_theme"]["problems"] == []
    assert (c / "M01-ok.theme-dark.png").stat().st_size > 2000 and (c / "M01-ok.png").exists()
    assert "targets" not in rec                                                               # без флага и без pointer_first — как раньше
    # тёмного блока нет — вторая тема не отличается от первой: замечание с префиксом темы
    (out / "mockups" / "tokens.css").write_text(TOKENS.split("\n", 1)[1], encoding="utf-8")
    r = node("shoot_mockups.mjs", out, "--only", "M01-ok", "--other-theme", "--no-fail")
    rec = check(out, "M01-ok")
    assert not rec["ok"] and any(p.startswith("тема dark: вторая тема не отличается") for p in rec["problems"]), rec["problems"]
    # design.pointer_first в run-config включает --targets сам
    (out / "build").mkdir(exist_ok=True)
    (out / "build" / "run-config.json").write_text(json.dumps({"design": {"pointer_first": True}}), encoding="utf-8")
    r = node("shoot_mockups.mjs", out, "--only", "M01-ok", "--no-fail")
    assert check(out, "M01-ok")["targets"]["mode"] == "pointer"
    r = node("shoot_mockups.mjs", out, "--only", "M01-ok", "--no-targets", "--no-fail")
    assert "targets" not in check(out, "M01-ok")
