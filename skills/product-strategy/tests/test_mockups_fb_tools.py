"""WP-F (1.5): mockup_kit.py (FB-007 чекпоинт выбора, FB-008 набор и M00 скриптом, SM 9 режимы/галерея) и
link_mockups.py (FB-009 --collect-gaps, индекс макетов заранее --index-only, перевод G8-xx → P-id --remap-drafts).

Запуск: python3 -m pytest tests/test_mockups_fb_tools.py -q -p no:cacheprovider
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SKILL = Path(__file__).resolve().parents[1]
SCRIPTS = SKILL / "scripts"
NODE_DIR = SCRIPTS / "node"
sys.path.insert(0, str(SCRIPTS))
import mockup_kit  # noqa: E402


def find_node_dir():
    for d in [os.environ.get("PS_NODE_DIR"), str(NODE_DIR), str(Path.home() / ".cache" / "product-strategy" / "node")]:
        if d and (Path(d) / "node_modules" / "playwright" / "package.json").exists():
            return d
    return None


NODE = shutil.which("node")
PW_DIR = find_node_dir()
needs_pw = pytest.mark.skipif(not NODE or not PW_DIR, reason="playwright недоступен")


def py(script, *args):
    return subprocess.run([sys.executable, "-B", str(SCRIPTS / script), *map(str, args)], capture_output=True, text=True, timeout=180)


def kit(*args):
    return py("mockup_kit.py", *args)


def jload(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def jdump(p, obj):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    Path(p).write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


@pytest.fixture
def run(tmp_path):
    jdump(tmp_path / "build" / "run-config.json", {"mode": "concept", "idea": {"name": "Книжная полка"}, "product": {"type": "saas"},
                                                  "design": {"modes": ["Терминал", "dashboard"]}, "autopilot": False})
    return tmp_path


# ---------------------------------------------------------------- FB-008: init — однократно, идемпотентно, M00 всех форм

def test_fb008_init_idempotent_forms_and_lock(run):
    r = kit("init", run, "--forms", "web,mobile", "--json")
    assert r.returncode == 0, r.stderr
    rep = json.loads(r.stdout)
    c = run / "mockups" / "concepts"
    for f in ("_kit.css", "_icons.css", "_base.html", "_kit-demo.html", "_hotspots.js", "_mobile.css", "_base-mobile.html", "_storyboard.html",
              "_kit-demo-mobile.html", "M00-design-language.html"):
        assert (c / f).is_file(), f
    assert (run / "mockups" / "tokens.css").exists() and (run / "mockups" / "tokens-terminal.css").exists() and (run / "mockups" / "tokens-dashboard.css").exists()
    assert '[data-mode="terminal"]' in (run / "mockups" / "tokens-terminal.css").read_text(encoding="utf-8")
    m00 = (c / "M00-design-language.html").read_text(encoding="utf-8")
    assert 'id="kd-components"' in m00 and 'id="kd-phones"' in m00                            # обе демо: веб и мобильный
    assert 'data-kind="kit"' in m00 and 'data-links="false"' in m00 and "Книжная полка" in m00 and "_mobile.css" in m00
    assert m00.count("// Автопроверка контраста") == 1 and 'class="kd-mslot"' in m00
    lock = jload(run / "build" / "kit.lock")
    assert lock["forms"] == ["web", "mobile"] and "mockups/concepts/M00-design-language.html" in lock["files"] and len(rep["copied"]) == 9
    # повторный запуск (без --forms — формы прежние) ничего не меняет
    before = {p.name: p.read_bytes() for p in c.iterdir()}
    r = kit("init", run)
    assert r.returncode == 0 and "ничего не изменил" in r.stdout
    assert {p.name: p.read_bytes() for p in c.iterdir()} == before
    # verify: набор не менялся → 0; агент поправил _kit.css → 1 со списком; init не затирает правку без --force
    assert kit("verify", run).returncode == 0
    (c / "_kit.css").write_text((c / "_kit.css").read_text(encoding="utf-8") + "\n.m05-x{}\n", encoding="utf-8")
    r = kit("verify", run, "--json")
    assert r.returncode == 1 and json.loads(r.stdout)["changed"] == ["mockups/concepts/_kit.css"]
    r = kit("init", run)
    assert "изменён после init" in r.stdout and ".m05-x" in (c / "_kit.css").read_text(encoding="utf-8")
    assert kit("verify", run, "--update").returncode == 0 and kit("verify", run).returncode == 0
    assert kit("init", run, "--force").returncode == 0 and ".m05-x" not in (c / "_kit.css").read_text(encoding="utf-8")


def test_fb008_forms_from_run_config(tmp_path):
    jdump(tmp_path / "build" / "run-config.json", {"product": {"type": "mobile"}})
    assert kit("init", tmp_path).returncode == 0
    m00 = (tmp_path / "mockups" / "concepts" / "M00-design-language.html").read_text(encoding="utf-8")
    assert 'id="kd-phones"' in m00 and 'id="kd-components"' not in m00 and 'data-viewport="2120x1000"' in m00
    t2 = tmp_path / "web"
    jdump(t2 / "build" / "run-config.json", {"product": {"type": "saas"}, "design": {"mobile_reserve": True}})
    assert kit("init", t2).returncode == 0
    assert jload(t2 / "build" / "kit.lock")["forms"] == ["web", "mobile-later"]
    assert "задел на будущее" in (t2 / "mockups" / "concepts" / "M00-design-language.html").read_text(encoding="utf-8")
    assert kit("init", tmp_path / "nope").returncode == 2
    assert kit("init", t2, "--forms", "tv").returncode != 0


@needs_pw
def test_fb008_m00_shoots_clean(run):
    assert kit("init", run, "--forms", "web,mobile").returncode == 0
    r = subprocess.run([NODE, str(NODE_DIR / "shoot_mockups.mjs"), str(run), "--layout", "--node-dir", PW_DIR], capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stdout + r.stderr
    rec = jload(run / "data" / "mockups-check.M00-design-language.json")
    assert rec["ok"] and rec["kind"] == "component" and rec["full_page"] and rec["contrast"]["fails"] == 0 and rec["layout"] == []
    idx = jload(run / "data" / "mockups-index.json")
    assert idx[0]["key"] == "M00-design-language" and idx[0]["kind"] == "component" and idx[0]["links"] is False


# ---------------------------------------------------------------- FB-007: направления, выбор, ворота

DIRECTIONS = """# Направления языка дизайна

## Направление A — «Глина и бумага»
Суть: тёплые карточки и рукописные акценты, лента.

## Направление B — «Терминал»
Плотные панели, моноширинный акцент.

## Направление C — «Лаборатория»
Холст с графиками.

## Рекомендация
Рекомендую направление B: опытные пользователи, плотность.
"""


def test_fb007_directions_choose_and_gate(run):
    assert kit("directions", run).returncode == 2                                            # шага 1 ещё не было
    (run / "design").mkdir()
    (run / "design" / "directions.md").write_text(DIRECTIONS, encoding="utf-8")
    r = kit("directions", run, "--json")
    assert r.returncode == 0, r.stderr
    d = json.loads(r.stdout)
    assert [x["id"] for x in d["directions"]] == ["B", "A", "C"] and d["recommended"] == "B"   # рекомендованное первым
    assert d["directions"][1]["name"] == "Глина и бумага" and "тёплые карточки" in d["directions"][1]["essence"]
    # вне автопилота шаги 2–3 закрыты до выбора; шаг 1 — открыт
    r = kit("gate", run, "--steps", "2-3")
    assert r.returncode == 3 and "до выбора направления" in r.stdout
    assert kit("gate", run, "--steps", "1").returncode == 0
    assert kit("choose", run, "--direction", "Z").returncode == 2
    r = kit("choose", run, "--direction", "глина и бумага", "--by", "owner")
    assert r.returncode == 0, r.stderr
    design = jload(run / "build" / "run-config.json")["design"]
    assert design["chosen"] == "A" and design["chosen_by"] == "owner" and design["modes"] == ["Терминал", "dashboard"]   # прочее не тронуто
    assert kit("gate", run, "--steps", "2-3").returncode == 0
    ok, why = mockup_kit.design_gate({"autopilot": True}, "1-3")
    assert ok and "автопилот" in why
    assert mockup_kit.design_gate({}, "2-3")[0] is False
    r = kit("choose", run, "--recommended", "--by", "default")
    assert jload(run / "build" / "run-config.json")["design"]["chosen_by"] == "default"
    p = json.loads(kit("params", run, "--json").stdout)
    assert p["chosen"] == "B" and p["directions_count"] == 3 and p["modes"] == ["terminal", "dashboard"]


# ---------------------------------------------------------------- SM 9: галерея

def mock(title, variant="", screen="", note="", status="", props="P001"):
    attrs = ' data-variant="%s"' % variant if variant else ""
    attrs += ' data-screen-id="%s"' % screen if screen else ""
    attrs += ' data-variant-note="%s"' % note if note else ""
    attrs += ' data-variant-status="%s"' % status if status else ""
    return ('<!doctype html><html lang="ru" data-viewport="1440x900" data-proposals="%s"%s><head><meta charset="utf-8"><title>%s</title></head>'
            '<body><div class="ps-concept-badge">Концепт, не существующая функция</div></body></html>') % (props, attrs, title)


def test_sm9_gallery(run):
    c = run / "mockups" / "concepts"
    c.mkdir(parents=True)
    (c / "M01-a-calc.html").write_text(mock("Калькулятор", "A · Терминал", "calc", "Плотные панели"), encoding="utf-8")
    (c / "M02-a-list.html").write_text(mock("Список", "A · Терминал", "list"), encoding="utf-8")
    (c / "M03-b-calc.html").write_text(mock("Калькулятор", "B · Бенто", "calc", "Плитки"), encoding="utf-8")
    (c / "M04-b-list.html").write_text(mock("Список", "B · Бенто", "list"), encoding="utf-8")
    (c / "M05-e-calc.html").write_text(mock("Журнал", "E · Журнал", "calc", "Отклонён владельцем", "rejected"), encoding="utf-8")
    (c / "M01-a-calc.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    r = kit("gallery", run, "--json")
    assert r.returncode == 0, r.stdout + r.stderr
    rep = json.loads(r.stdout)
    assert rep["variants"] == {"A · Терминал": ["M01-a-calc", "M02-a-list"], "B · Бенто": ["M03-b-calc", "M04-b-list"]}
    assert rep["rejected"] == ["E · Журнал"] and rep["compare_rows"] == ["calc", "list"]
    g = (run / "mockups" / "gallery.html").read_text(encoding="utf-8")
    assert "Концепт, не существующая функция · Книжная полка" in g and "{{" not in g
    assert 'src="concepts/M01-a-calc.png"' in g and "снимка нет" in g and "Один сценарий в разных вариантах" in g
    assert g.index("Отклонено") > g.index("B · Бенто") and 'src="concepts/_hotspots.js"' in g
    # у варианта меньше двух экранов — предупреждение и код 1
    (c / "M04-b-list.html").unlink()
    r = kit("gallery", run)
    assert r.returncode == 1 and "экранов 1 < 2" in r.stdout


# ---------------------------------------------------------------- FB-009: --collect-gaps; --index-only; --remap-drafts

def test_fb009_collect_gaps_index_and_remap(run):
    jdump(run / "data" / "proposals.json", [{"id": "P001", "title": "Каталог"}, {"id": "P003", "title": "Согласия"}, {"id": "P111", "title": "Письма"}])
    c = run / "mockups" / "concepts"
    c.mkdir(parents=True)
    (c / "M08-mail.html").write_text(mock("Письма", props="P111,G8-01").replace("</body>",
        "<!-- НУЖНО-ПРЕДЛОЖЕНИЕ: Пробный Pro на 7 дней | monetization | P003 -->\n<!-- РАСХОЖДЕНИЕ: P111 | одно согласие вместо двух чекбоксов -->\n"
        '<button data-hs="b" data-hs-title="Б" data-hs-p="G8-02">x</button></body>'), encoding="utf-8")
    (run / "design-refs").mkdir()
    (run / "design-refs" / "08-mail.md").write_text("# 08\n## Открытые вопросы\n- НУЖНО-ПРЕДЛОЖЕНИЕ: Лист лимита бесплатного тарифа | conversion | P001, P999\n"
                                                    "- **РАСХОЖДЕНИЕ: P001 | M08-mail | /item/<slug> против /ru/<предмет>**\n- РАСХОЖДЕНИЕ: только текст\n"
                                                    "- НУЖНО-ПРЕДЛОЖЕНИЕ: Странная категория | marketing |\n", encoding="utf-8")
    (c / "M09-plain.html").write_text("<!doctype html><p>НУЖНО-ПРЕДЛОЖЕНИЕ: в видимом тексте — не считается</p>", encoding="utf-8")
    r = py("link_mockups.py", run, "--collect-gaps", "--json")
    assert r.returncode == 0, r.stderr
    rep = json.loads(r.stdout)
    assert rep["drafts_added"] == ["G8-01", "G8-02", "G8-03"] and len(rep["fact_check_added"]) == 2
    assert any("только текст" in e or "P-id | Mxx" in e for e in rep["errors"])
    assert any("P999" in w for w in rep["warnings"]) and any("marketing" in w for w in rep["warnings"])
    drafts = {d["id"]: d for d in jload(run / "data" / "proposals-draft-G8.json")}
    d1 = next(d for d in drafts.values() if d["title"].startswith("Лист лимита"))
    assert d1["category"] == "conversion" and d1["dependencies"] == ["P001"] and d1["source_group"] == "G8" and d1["evidence_class"] == "D"
    assert d1["needs_details"] is True and d1["evidence"][0]["file"].startswith("design-refs/08-mail.md:")
    d2 = next(d for d in drafts.values() if d["title"].startswith("Пробный Pro"))
    assert d2["mockup"] == "concepts/M08-mail.html" and d2["evidence"][0]["file"].startswith("mockups/concepts/M08-mail.html:")
    fc = jload(run / "data" / "fact-check.json")
    assert {(x["proposal"], x["mockup"]) for x in fc} == {("P111", "M08-mail"), ("P001", "M08-mail")}
    assert all(x["kind"] == "mockup_vs_registry" and x["status"] == "open" and x["resolved_value"] is None for x in fc)
    summary = jload(run / "build" / "collect-gaps.json")
    assert len(summary["drafts_added"]) == 3 and summary["mismatches_open"] == 2
    # повторный запуск не дублирует; --strict — код 1 из-за ошибок формата
    r = py("link_mockups.py", run, "--collect-gaps", "--json")
    rep = json.loads(r.stdout)
    assert rep["drafts_added"] == [] and rep["fact_check_added"] == [] and len(jload(run / "data" / "fact-check.json")) == 2
    assert py("link_mockups.py", run, "--collect-gaps", "--strict").returncode == 1
    # --index-only: индекс без браузера, черновые id сохраняются
    r = py("link_mockups.py", run, "--index-only", "--json")
    assert r.returncode == 0, r.stderr
    idx = {i["key"]: i for i in jload(run / "data" / "mockups-index.json")}
    assert idx["M08-mail"]["proposals"] == ["P111", "G8-01"] and idx["M08-mail"]["discovered"] is True and idx["M08-mail"]["title"] == "Письма"
    assert json.loads(py("link_mockups.py", run, "--index-only", "--json").stdout)["added"] == []          # идемпотентно
    # --remap-drafts по build/id-map.json (карта merge_proposals)
    jdump(run / "build" / "id-map.json", {"G8-01": "P112", "G8-02": "P113"})
    r = py("link_mockups.py", run, "--remap-drafts", "--json")
    assert r.returncode == 0, r.stderr
    html = (c / "M08-mail.html").read_text(encoding="utf-8")
    assert 'data-proposals="P111,P112"' in html and 'data-hs-p="P113"' in html and json.loads(r.stdout)["unresolved"] == []


def test_fb009_drafts_accepted_by_merge_append(tmp_path):
    out = tmp_path / "demo"
    assert py("make_demo.py", out).returncode == 0
    (out / "design-refs").mkdir(exist_ok=True)
    (out / "design-refs" / "01-x.md").write_text("НУЖНО-ПРЕДЛОЖЕНИЕ: Экспорт истории в CSV | product | P001\n", encoding="utf-8")
    assert py("link_mockups.py", out, "--collect-gaps").returncode == 0
    r = py("merge_proposals.py", out, "--append", "G8")
    assert r.returncode == 0, r.stdout + r.stderr
    assert any(p["title"] == "Экспорт истории в CSV" for p in jload(out / "data" / "proposals.json"))
    assert "G8-01" in jload(out / "build" / "id-map.json")
