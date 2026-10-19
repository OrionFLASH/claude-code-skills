"""WP-G (1.5.0, SM 7): набор рабочего прототипа templates/prototype-kit и фаза C8.5 (pytest, без сети).

Критерии приёмки SM 7 и списка изменений (№ 7): «prototype/ создаётся по брифам; числа макетов = числам ядра»:
  - набор открывается по file:// (обычные скрипты, без ES-модулей и внешних адресов), есть контракт registerMode;
  - node js/core.test.js — ядро воспроизводит канон демо-данных; node js/kit.test.js — контракт оболочки, ИИ на фикстурах;
  - tools/check_canon.py ловит расхождение «макет ↔ канон», «график ↔ подпись» (data-canon-item) и «ядро ↔ канон»;
  - смоук в браузере (если есть Playwright): режимы, темы, цели нажатия, без внешних запросов.
Запуск: python3 -m pytest skills/product-strategy/tests/test_prototype_kit.py -q -p no:cacheprovider
"""
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SKILL = Path(__file__).resolve().parent.parent
KIT = SKILL / "templates" / "prototype-kit"
NODE = shutil.which("node")
FILES = ["README.md", "package.json", "index.html", "css/base.css", "js/core.js", "js/core.test.js", "js/kit.test.js",
         "js/data.js", "js/state.js", "js/modes.js", "js/llm.js", "js/mode-example.js", "js/app.js",
         "fixtures/canon.json", "fixtures/llm-replies.js", "tests/smoke.mjs", "tools/check_canon.py"]
BROWSER = ["index.html", "js/core.js", "js/data.js", "js/state.js", "js/modes.js", "js/llm.js", "js/mode-example.js",
           "js/app.js", "fixtures/llm-replies.js", "css/base.css"]


def copy_kit(tmp_path):
    out = tmp_path / "OUT"
    shutil.copytree(KIT, out / "prototype")
    return out


def canon_check(out, *args):
    return subprocess.run([sys.executable, "-I", str(out / "prototype" / "tools" / "check_canon.py"), str(out / "prototype"), *map(str, args)],
                          capture_output=True, text=True, timeout=120)


def test_kit_files_present():
    missing = [f for f in FILES if not (KIT / f).exists()]
    assert not missing, missing
    assert json.loads((KIT / "package.json").read_text(encoding="utf-8"))["type"] == "commonjs"   # require() в любом репозитории


def test_browser_files_work_offline_by_file_url():
    for f in BROWSER:
        t = (KIT / f).read_text(encoding="utf-8")
        assert 'type="module"' not in t, f
        assert not re.search(r"(?m)^\s*(import|export)\s", t), f                 # без ES-модулей: Safari по file://
        assert not re.search(r"https?://", t), f                                 # без внешних адресов и CDN
    html = re.sub(r"(?s)<!--.*?-->", "", (KIT / "index.html").read_text(encoding="utf-8"))
    srcs = re.findall(r'<script src="([^"]+)"', html)
    assert srcs and srcs[-1] == "js/app.js" and all((KIT / s).exists() for s in srcs)
    assert srcs.index("js/modes.js") < srcs.index("js/mode-example.js")
    assert "Концепт продукта, не существующая функция" in html and "демо-данные" in html


def test_core_has_no_dom_or_network():
    t = (KIT / "js" / "core.js").read_text(encoding="utf-8")
    assert not re.search(r"document\.|window\.|fetch\(|XMLHttpRequest|localStorage", t)


@pytest.mark.skipif(not NODE, reason="нет node")
def test_core_and_kit_tests_pass(tmp_path):
    out = copy_kit(tmp_path)
    for script in ("js/core.test.js", "js/kit.test.js"):
        r = subprocess.run([NODE, script], cwd=out / "prototype", capture_output=True, text=True, timeout=120)
        assert r.returncode == 0, r.stdout + r.stderr
        assert r.stdout.startswith("OK:") and " 0 failed" in r.stdout


@pytest.mark.skipif(not NODE, reason="нет node")
def test_core_fails_when_canon_differs(tmp_path):
    """Числа канона (макетов) ≠ числа ядра → тест ядра падает с указанием поля."""
    out = copy_kit(tmp_path)
    canon = json.loads((out / "prototype" / "fixtures" / "canon.json").read_text(encoding="utf-8"))
    canon["cases"][0]["expected"]["paybackWeeks"] = 21
    bad = tmp_path / "bad-canon.json"
    bad.write_text(json.dumps(canon, ensure_ascii=False), encoding="utf-8")
    r = subprocess.run([NODE, "js/core.test.js", str(bad)], cwd=out / "prototype", capture_output=True, text=True, timeout=120)
    assert r.returncode == 1 and "C01.paybackWeeks: ожидалось 21, получено 20" in r.stdout


MOCKUP_OK = """<!doctype html><html lang="ru"><body>
<div class="kpi">Окупится за <b data-canon="C01.paybackWeeks">20</b> нед</div>
<div>Экономия <span data-canon="C01.netSavedPerWeek">2,0 ч</span> в неделю; за год <span data-canon="C01.yearNetHours">+64 ч</span></div>
<div>Минимальный сценарий: <span data-canon="C03.netSavedPerWeek">1,5</span></div>
<svg><circle data-canon-item="C03.paybackWeeks"/></svg>
</body></html>"""


def write_mockup(out, html, name="M01-example.html"):
    d = out / "mockups" / "concepts"
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(html, encoding="utf-8")


def test_check_canon_mockups_match(tmp_path):
    out = copy_kit(tmp_path)
    write_mockup(out, MOCKUP_OK.replace('<svg><circle data-canon-item="C03.paybackWeeks"/></svg>', ""))
    r = canon_check(out)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "сверено значений 4" in r.stdout and "расхождений нет" in r.stdout


def test_check_canon_catches_mismatch_unknown_and_count(tmp_path):
    out = copy_kit(tmp_path)
    html = MOCKUP_OK.replace(">20</b>", ">25</b>").replace("C03.netSavedPerWeek", "C09.netSavedPerWeek")
    write_mockup(out, html)                       # плюс 1 значок data-canon-item при каноне 20 — «график ↔ подпись»
    r = canon_check(out, "--json")
    assert r.returncode == 1
    res = json.loads(r.stdout)
    errs = "\n".join(res["errors"])
    assert "C01.paybackWeeks — ожидалось 20, показано «25»" in errs
    assert 'data-canon="C09.netSavedPerWeek" — нет в каноне' in errs
    assert "элементов data-canon-item=\"C03.paybackWeeks\" 1, в каноне 20 (график ↔ подпись)" in errs


def test_check_canon_prefers_run_canon_and_warns_unmarked(tmp_path):
    out = copy_kit(tmp_path)
    (out / "data").mkdir()
    (out / "data" / "demo-canon.json").write_text(json.dumps({"label": "демо-данные", "cases": [
        {"id": "K1", "fn": "payback", "inputs": {"buildHours": 10, "savedHoursPerWeek": 2}, "expected": {"paybackWeeks": 5}}]},
        ensure_ascii=False), encoding="utf-8")
    write_mockup(out, "<html><body><p>без разметки</p></body></html>")
    r = canon_check(out)
    assert r.returncode == 0 and "канон demo-canon.json" in r.stdout and "макеты не связаны с каноном" in r.stdout
    if NODE:
        r = canon_check(out, "--core")
        assert r.returncode == 0 and "ядро: ок" in r.stdout, r.stdout


def test_check_canon_schema_errors(tmp_path):
    out = copy_kit(tmp_path)
    bad = tmp_path / "c.json"
    bad.write_text(json.dumps({"cases": [{"id": "A"}, {"id": "A", "expected": {"x": 1}}]}), encoding="utf-8")
    r = canon_check(out, "--canon", bad)
    assert r.returncode == 1 and "A: нет expected" in r.stdout and "повтор id кейса A" in r.stdout
    assert "нет пометки демо-данных" in r.stdout


def find_playwright():
    home = os.environ.get("HOME", "")
    for d in [os.environ.get("PS_NODE_DIR"), os.path.join(home, ".cache", "product-strategy", "node")]:
        if d and (Path(d) / "node_modules" / "playwright" / "package.json").exists():
            return d
    return None


@pytest.mark.skipif(not NODE or not find_playwright(), reason="нет node или playwright (check_env.py --install-node)")
def test_smoke_in_browser(tmp_path):
    out = copy_kit(tmp_path)
    r = subprocess.run([NODE, "tests/smoke.mjs", "--node-dir", find_playwright()], cwd=out / "prototype",
                       capture_output=True, text=True, timeout=300)
    if r.returncode == 3:
        pytest.skip("браузер Playwright не установлен: " + r.stderr.strip()[:200])
    assert r.returncode == 0, r.stdout + r.stderr
    res = json.loads((out / "prototype" / "shots" / "smoke-results.json").read_text(encoding="utf-8"))
    assert res["browsers"][0]["modes"] == ["example"] and not res["browsers"][0]["external"]
    assert (out / "prototype" / "shots" / "chromium-example-dark.png").exists()


def test_reference_and_briefs_describe_phase():
    ref = (SKILL / "references" / "prototype.md").read_text(encoding="utf-8")
    for s in ("C8.5", "registerMode", "file://", "data-canon", "data-canon-item", "fixtures/llm-replies.js",
              "HANDOFF.md", "data/prototype.json", "build/tmp/"):
        assert s in ref, s
    briefs = SKILL / "templates" / "briefs"
    core = (briefs / "prototype-core.md").read_text(encoding="utf-8")
    assert "templates/prototype-kit/. {OUT}/prototype/" in core and "check_canon.py" in core
    reg = (briefs / "prototype-regression.md").read_text(encoding="utf-8")
    assert "HANDOFF.md" in reg and "--webkit" in reg and "data/prototype.json" in reg
    mode = (briefs / "prototype-mode.md").read_text(encoding="utf-8")
    assert "PK.registerMode" in mode and "не трогать" in mode
