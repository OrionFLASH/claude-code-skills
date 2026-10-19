"""Тесты режима site (многофайловая страница, по умолчанию) build_html.py: references/interactive-site.md, раздел 1.

Структура папки deliverables/, ссылки на ассеты, тождественность разделов режиму single, zip, extra.css|js, смена режима
пересборкой без мусора, запасной вариант CSP, открытые данные, режим идеи; smoke на file:// (нужен node + playwright).

  python3 -m pytest skills/product-strategy/tests/test_site_mode.py -q
"""
import hashlib
import json
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

import test_build_html as tb
from test_build_html import SCRIPTS, bh, build, enrich, make_demo, noisy_png

CONCEPT_DEMO = SCRIPTS / "make_concept_demo.py"
JSON_BLOCKS_11 = tb.JSON_BLOCKS_11
SITE_CSP = ("default-src 'none'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; "
            "base-uri 'none'; form-action 'none'")


def run(script, *args, check=True):
    r = subprocess.run([sys.executable, str(SCRIPTS / script)] + [str(a) for a in args], capture_output=True, text=True)
    if check:
        assert r.returncode == 0, r.stdout + r.stderr
    return r


def make_run(path):
    """Демо с крупными картинками (> 32 КБ): в site они уходят в assets/img/ с миниатюрами."""
    out = enrich(make_demo(path))
    for k in range(1, 7):
        noisy_png(out / "mockups" / "concepts" / ("M%02d-demo.png" % k), w=400, h=300, seed=k)
    noisy_png(out / "design-refs" / "01-demo.png", w=400, h=300, seed=1)       # то же содержимое, что M01: один файл
    noisy_png(out / "competitors" / "shots" / "rival-1.png", w=400, h=300, seed=9)
    return out


def files_of(page_dir):
    return sorted(p.relative_to(page_dir).as_posix() for p in page_dir.rglob("*") if p.is_file())


def shell_of(page):
    return re.search(r'<main id="main">(.*)</main>', page, re.S).group(1)


def sections_only(page):
    """Разметка разделов без подвала (текст подвала различается по режимам)."""
    return re.sub(r'<footer class="copy">.*?</footer>', "", shell_of(page), flags=re.S)


def ps_data(page_dir):
    js = (page_dir / "assets" / "data.js").read_text(encoding="utf-8")
    m = re.search(r"window\.PS_DATA=(.*);\n$", js, re.S)
    assert m, js[:200]
    return json.loads(m.group(1))


def refs_of(page):
    return [u for u in re.findall(r'<(?:link|script|img)\b[^>]*?\b(?:href|src)="([^"]+)"', page) if not u.startswith(("data:", "#"))]


@pytest.fixture(scope="module")
def run_dir(tmp_path_factory):
    return make_run(tmp_path_factory.mktemp("site") / "run")


@pytest.fixture(scope="module")
def site(run_dir):
    r = subprocess.run([sys.executable, str(tb.BUILD), str(run_dir)], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    d = run_dir / "deliverables"
    return {"out": run_dir, "dir": d, "stdout": r.stdout, "page": (d / "index.html").read_text(encoding="utf-8")}


# ---------------------------------------------------------------- структура папки
def test_default_mode_is_site_structure(site):
    d = site["dir"]
    fs = files_of(d)
    for need in ("index.html", "assets/app.css", "assets/app.js", "assets/data.js", "assets/head.js", ".ps-site.json"):
        assert need in fs, need
    for need in ("proposals.json", "proposals.csv", "scores.csv", "competitors.csv", "gantt.csv", "kanban.csv", "sources.csv"):
        assert "data/" + need in fs, need
    assert any(f.startswith("assets/img/") and not f.startswith("assets/img/thumbs/") for f in fs)
    assert any(f.startswith("assets/img/thumbs/") for f in fs)
    # необязательные файлы не создаются, пока нет источника
    assert "assets/extra.css" not in fs and "assets/extra.js" not in fs and "assets/charts.js" not in fs
    assert "strategy-site.zip" not in fs
    assert "Режим site" in site["stdout"] and "Размер сайта" in site["stdout"]


def test_shell_has_no_data_inline_code_or_styles(site):
    page = site["page"]
    assert len(page.encode("utf-8")) < 1048576
    assert 'type="application/json"' not in page and "<style" not in page
    assert not [m for m in re.findall(r"<script\b([^>]*)>", page) if "src=" not in m], "инлайн-скрипт запрещён CSP script-src 'self'"
    assert page.count("<script") == 3 and page.count("</script>") == 3          # head.js, data.js, app.js
    assert 'rel="stylesheet" href="assets/app.css?v=' in page
    # порядок: данные до приложения
    assert page.index("assets/data.js") < page.index("assets/app.js")


def test_site_csp_and_referrer(site):
    page = site["page"]
    assert 'http-equiv="Content-Security-Policy" content="%s"' % SITE_CSP in page
    assert '<meta name="referrer" content="no-referrer">' in page
    assert "sha256-" not in page                         # хеши нужны только в single


def test_asset_links_exist_and_versioned(site):
    d, page = site["dir"], site["page"]
    refs = refs_of(page)
    assert len(refs) == 4
    for u in refs:
        assert not re.match(r"^[a-z][a-z0-9+.-]*:|^//", u, re.I), "внешняя ссылка " + u
        rel, _, q = u.partition("?v=")
        f = d / rel
        assert f.is_file(), u
        assert q == hashlib.sha1(f.read_bytes()).hexdigest()[:10], "версия ?v= = хеш содержимого: " + u


def test_data_js_has_all_blocks_and_image_files_exist(site):
    d = site["dir"]
    data = ps_data(d)
    assert set(data) == JSON_BLOCKS_11
    assert len(data["d-registry"]) == 60 and data["d-meta"]["title"]
    urls = [u for u in data["d-img"].values() if u]
    assert urls and all(not u.startswith("data:") for u in urls), "в site картинки — файлы"
    for u in urls:
        assert u.startswith("assets/img/") and (d / u).is_file(), u
    for key, (t, w) in data["d-thumb"].items():
        assert t.startswith("assets/img/thumbs/") and (d / t).is_file() and w > 0, key
    assert data["d-alias"], "одинаковое содержимое (M01 и референс) — одна копия на изображение"
    # data.js — JS, не JSON: fetch() по file:// запрещён, поэтому window.PS_DATA
    assert (d / "assets" / "data.js").read_text(encoding="utf-8").startswith("/*")
    assert "</script" not in (d / "assets" / "data.js").read_text(encoding="utf-8")


def test_one_copy_per_image(site):
    d = site["dir"]
    imgs = [p for p in (d / "assets" / "img").iterdir() if p.is_file()]
    hashes = {}
    for p in imgs:
        hashes.setdefault(hashlib.sha1(p.read_bytes()).hexdigest(), []).append(p.name)
    assert all(len(v) == 1 for v in hashes.values()), hashes
    assert len(imgs) == len({n for n in ps_data(d)["d-img"].values() if n})


def test_open_data_files(site):
    import csv
    d = site["dir"] / "data"
    props = json.loads((d / "proposals.json").read_text(encoding="utf-8"))
    assert props == json.loads((site["out"] / "data" / "proposals.json").read_text(encoding="utf-8"))
    raw = (d / "proposals.csv").read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")
    rows = list(csv.reader(raw.decode("utf-8-sig").splitlines()))
    assert rows[0][:3] == ["id", "title", "category"] and len(rows) == 61
    assert all(len(r) == len(rows[0]) for r in rows)
    if (site["out"] / "data" / "scores.csv").is_file():
        assert (d / "scores.csv").read_bytes() == (site["out"] / "data" / "scores.csv").read_bytes()
    for name, n in (("competitors", 11), ("gantt", 9), ("kanban", 20), ("sources", 20)):
        t = list(csv.reader((d / (name + ".csv")).read_bytes().decode("utf-8-sig").splitlines()))
        assert len(t) == n + 1 and all(len(r) == len(t[0]) for r in t), name


def test_csv_cells_neutralize_formulas():
    assert bh.csv_cell("=1+1") == "'=1+1" and bh.csv_cell("@x") == "'@x" and bh.csv_cell("+7 (900)") == "'+7 (900)"
    assert bh.csv_cell("-5") == "-5" and bh.csv_cell("- пункт") == "'- пункт"
    assert bh.csv_cell(["a", None, "b"]) == "a | b" and bh.csv_cell({"k": 1, "z": None}) == "k=1"
    assert bh.csv_cell(None) == "" and bh.csv_cell(True) == "true" and bh.csv_cell(float("nan")) == ""


# ---------------------------------------------------------------- site и single показывают одно и то же
def test_site_sections_match_single(site, tmp_path):
    out = tmp_path / "run"
    shutil.copytree(site["out"], out)
    _, single = build(out, "--single")
    assert sections_only(single) == sections_only(site["page"])                 # разметка разделов — байт в байт
    # данные те же; различаются только ссылки на картинки (файлы вместо data:)
    blocks = {k: json.loads(v) for k, v in tb.json_blocks(single).items()}
    data = ps_data(site["dir"])
    for k in JSON_BLOCKS_11 - {"d-img", "d-thumb", "d-alias", "d-meta"}:
        assert blocks[k] == data[k], k
    assert set(blocks["d-img"]) == set(data["d-img"]) and all(v.startswith("data:") for v in blocks["d-img"].values())
    assert {k: v for k, v in blocks["d-meta"].items() if k != "lite"} == {k: v for k, v in data["d-meta"].items() if k != "lite"}
    # JS и CSS страницы — те же, что были встроены (только блок данных вынесен)
    css = (out / "deliverables" / "index.html").read_text(encoding="utf-8")
    assert re.search(r"<style>(.*?)</style>", css, re.S).group(1) == (site["dir"] / "assets" / "app.css").read_text(encoding="utf-8")
    assert re.findall(r"<script>(.*?)</script>", css, re.S)[-1] == (site["dir"] / "assets" / "app.js").read_text(encoding="utf-8")


def test_single_flag_is_self_contained(site, tmp_path):
    out = tmp_path / "run"
    shutil.copytree(site["out"], out)
    stdout, page = build(out, "--single")
    d = out / "deliverables"
    assert "sha256-" in page and page.count('type="application/json"') == len(JSON_BLOCKS_11)
    assert "assets/" not in re.sub(r"<script.*?</script>", "", page, flags=re.S)
    assert not (d / "assets").exists() and not (d / "data").exists() and not (d / ".ps-site.json").exists()
    assert "Удалены файлы прошлой сборки другого режима" in stdout
    assert files_of(d) == ["index.html"] + [f for f in files_of(d) if f.startswith("strategy.")]     # остались только свои результаты


def test_lite_flag_backward_compatible(run_dir, tmp_path):
    out = tmp_path / "run"
    shutil.copytree(run_dir, out)
    stdout, page = build(out, "--lite")
    d = out / "deliverables"
    assert "Режим --lite" in stdout and (d / "assets" / ".ps-assets.json").is_file()
    assert "img-src data: 'self'" in page and "sha256-" in page
    assert not (d / "assets" / "app.js").exists() and not (d / "data").exists() and not (d / ".ps-site.json").exists()
    assert tb.json_blocks(page).keys() == JSON_BLOCKS_11


# ---------------------------------------------------------------- смена режима без мусора
def test_mode_switching_leaves_no_leftovers(run_dir, tmp_path):
    out = tmp_path / "run"
    shutil.copytree(run_dir, out)
    d = out / "deliverables"
    mine = d / "data" / "mine.txt"
    (d / "notes.txt").write_text("мои заметки", encoding="utf-8")
    run("build_html.py", out)
    mine.write_text("чужой файл в data/", encoding="utf-8")
    site_files = set(files_of(d))
    assert "assets/app.js" in site_files and "assets/img" not in site_files
    run("build_html.py", out, "--lite")
    lite_files = set(files_of(d))
    assert not any(f.startswith(("assets/img/", "data/proposals")) or f in ("assets/app.js", "assets/data.js", ".ps-site.json") for f in lite_files), lite_files
    assert {"notes.txt", "data/mine.txt"} <= lite_files                                     # чужое не тронуто
    assert any(f.startswith("assets/") for f in lite_files)
    run("build_html.py", out)                                                                # lite → site
    again = set(files_of(d))
    assert not any(f.startswith("assets/") and f.count("/") == 1 and f.endswith((".png", ".webp", ".jpg")) for f in again), "файлы --lite остались"
    assert "assets/.ps-assets.json" not in again and again - {"data/mine.txt", "notes.txt"} == site_files - {"data/mine.txt", "notes.txt"}
    run("build_html.py", out, "--single")
    single_files = set(files_of(d))
    assert "assets/app.js" not in single_files and not any(f.startswith("assets/") for f in single_files)
    assert {"notes.txt", "data/mine.txt", "index.html"} <= single_files
    assert not [f for f in single_files if f.startswith("data/") and f != "data/mine.txt"]


def test_stale_images_removed_on_rebuild(run_dir, tmp_path):
    out = tmp_path / "run"
    shutil.copytree(run_dir, out)
    run("build_html.py", out)
    d = out / "deliverables"
    before = {f for f in files_of(d) if f.startswith("assets/img/")}
    noisy_png(out / "mockups" / "concepts" / "M02-demo.png", w=400, h=300, seed=77)       # содержимое изменилось: новое имя по хешу
    run("build_html.py", out)
    after = {f for f in files_of(d) if f.startswith("assets/img/")}
    assert after != before and len(after) == len(before), "старый вариант картинки удалён, новый добавлен"


def test_manifest_cannot_delete_outside_page_dir(tmp_path):
    page = tmp_path / "deliverables"
    page.mkdir()
    victim = tmp_path / "victim.txt"
    victim.write_text("не трогать", encoding="utf-8")
    (page / bh.SITE_MANIFEST).write_text(json.dumps({"files": ["../victim.txt", "/etc/hosts", "..\\victim.txt"]}), encoding="utf-8")
    assert bh.cleanup_previous(page, set()) == 0
    assert victim.read_text(encoding="utf-8") == "не трогать"


# ---------------------------------------------------------------- extra.css / extra.js
def test_extra_css_js_included_when_present(run_dir, tmp_path):
    out = tmp_path / "run"
    shutil.copytree(run_dir, out)
    (out / "build").mkdir(exist_ok=True)
    (out / "build" / "extra.css").write_text("body{outline:0}\n", encoding="utf-8")
    (out / "build" / "extra.js").write_text("window.__extra=1;\n", encoding="utf-8")
    _, page = build(out, "--site")
    d = out / "deliverables"
    assert (d / "assets" / "extra.css").read_text(encoding="utf-8") == "body{outline:0}\n"
    assert (d / "assets" / "extra.js").read_text(encoding="utf-8") == "window.__extra=1;\n"
    refs = refs_of(page)
    assert [u.split("?")[0] for u in refs] == ["assets/app.css", "assets/extra.css", "assets/head.js", "assets/data.js", "assets/app.js", "assets/extra.js"]
    for u in refs:                                                              # версия ?v= — хеш содержимого
        assert u.split("?v=")[1] == hashlib.sha1((d / u.split("?")[0]).read_bytes()).hexdigest()[:10]
    # убрали extra.* — следующая сборка удаляет свои файлы и ссылки
    (out / "build" / "extra.css").unlink()
    (out / "build" / "extra.js").unlink()
    _, page = build(out, "--site")
    assert not (d / "assets" / "extra.css").exists() and not (d / "assets" / "extra.js").exists()
    assert "extra." not in page


def test_extra_inlined_in_single_and_lite(run_dir, tmp_path):
    """1.5 (SM, раздел 8: хуки расширения совместимы с --single/--lite): build/extra.css|js и build/extra/*.css|js встраиваются
    в автономную страницу — стили отдельным <style>, скрипты отдельными <script> после основного, у каждого свой хеш в CSP.
    Раньше в single/lite они не подключались (с предупреждением) — поведение изменено осознанно."""
    import base64
    out = tmp_path / "run"
    shutil.copytree(run_dir, out)
    (out / "build" / "extra").mkdir(parents=True, exist_ok=True)
    (out / "build" / "extra.css").write_text("body{outline:0}\n", encoding="utf-8")
    (out / "build" / "extra.js").write_text("window.__extra=1;\n", encoding="utf-8")
    (out / "build" / "extra" / "20-layer.js").write_text("window.PS.on('ready',function(){window.__layer=2;});\n", encoding="utf-8")
    (out / "build" / "extra" / "10-layer.css").write_text(".x{color:red}\n", encoding="utf-8")
    for flag in ("--single", "--lite"):
        stdout, page = build(out, flag)
        assert "<style>body{outline:0}\n</style>" in page and "<style>.x{color:red}\n</style>" in page
        scripts = re.findall(r"<script>(.*?)</script>", page, re.S)
        assert scripts[-2:] == ["window.__extra=1;\n", "window.PS.on('ready',function(){window.__layer=2;});\n"]
        csp = re.search(r'Content-Security-Policy" content="([^"]+)"', page).group(1)
        for s in scripts:
            assert "'sha256-%s'" % base64.b64encode(hashlib.sha256(s.encode("utf-8")).digest()).decode() in csp
        assert "не подключены" not in stdout and "Расширения страницы (хуки): assets/extra.css, assets/extra.js, assets/extra/10-layer.css, assets/extra/20-layer.js" in stdout
    # site: те же слои — файлами (папка assets/extra/), с версией по содержимому
    _, page = build(out, "--site")
    refs = [u.split("?")[0] for u in refs_of(page)]
    assert refs == ["assets/app.css", "assets/extra.css", "assets/extra/10-layer.css", "assets/head.js", "assets/data.js", "assets/app.js",
                    "assets/extra.js", "assets/extra/20-layer.js"]
    assert (out / "deliverables" / "assets" / "extra" / "20-layer.js").is_file()


# ---------------------------------------------------------------- CSP: запасной вариант
def test_site_csp_none_fallback(run_dir, tmp_path):
    out = tmp_path / "run"
    shutil.copytree(run_dir, out)
    _, page = build(out, "--site", "--site-csp", "none")
    assert "Content-Security-Policy" not in page
    assert '<meta name="referrer" content="no-referrer">' in page
    assert refs_of(page)[0].startswith("assets/app.css")


# ---------------------------------------------------------------- zip
def test_zip_contains_whole_site(run_dir, tmp_path):
    out = tmp_path / "run"
    shutil.copytree(run_dir, out)
    stdout, _ = build(out, "--site", "--zip")
    d = out / "deliverables"
    zp = d / "strategy-site.zip"
    assert zp.is_file() and "Архив:" in stdout
    with zipfile.ZipFile(zp) as z:
        assert z.testzip() is None
        names = set(z.namelist())
        assert "strategy-site.zip" not in names and not [n for n in names if Path(n).name.startswith(".")]
        site_files = {f for f in files_of(d) if not Path(f).name.startswith(".") and f != "strategy-site.zip" and not f.startswith("strategy.")}
        assert names == site_files
        assert z.read("index.html") == (d / "index.html").read_bytes() and z.read("assets/app.js") == (d / "assets" / "app.js").read_bytes()
    # без --zip следующая сборка удаляет устаревший архив; в single архив не собирается
    build(out, "--site")
    assert not zp.exists()
    r = subprocess.run([sys.executable, str(tb.BUILD), str(out), "--single", "--zip"], capture_output=True, text=True)
    assert r.returncode == 0 and "только в режиме site" in r.stderr and not zp.exists()


def test_build_all_flags(tmp_path):
    out = make_demo(tmp_path / "run")
    only = ["--only", "score,charts,html", "--skip", "pptx,pdf,smoke,mockups"]
    r = run("build_all.py", out, "--zip", *only)
    d = out / "deliverables"
    assert (d / "strategy-site.zip").is_file() and (d / "assets" / "app.js").is_file(), r.stdout
    r = run("build_all.py", out, "--single", *only)
    assert not (d / "assets").exists() and not (d / "strategy-site.zip").exists() and "sha256-" in (d / "index.html").read_text(encoding="utf-8")
    r = run("build_all.py", out, "--lite", *only)
    assert "img-src data: 'self'" in (d / "index.html").read_text(encoding="utf-8")
    r = run("build_all.py", out, *only)
    assert (d / "assets" / "data.js").is_file() and "sha256-" not in (d / "index.html").read_text(encoding="utf-8")
    r = run("build_all.py", out, "--single", "--lite", check=False)
    assert r.returncode != 0
    r = run("build_html.py", out, "--single", "--site", check=False)
    assert r.returncode == 2                                                    # взаимоисключающие флаги


# ---------------------------------------------------------------- режим идеи (mode: concept) — тот же сборщик
@pytest.mark.parametrize("flags", [[], ["--single"]], ids=["site", "single"])
def test_concept_demo_build_all(tmp_path, flags):
    out = tmp_path / "idea"
    run("make_concept_demo.py", out)
    r = run("build_all.py", out, "--strict", "--skip", "pptx,pdf,smoke,mockups", *flags)
    assert "всё собрано" in r.stdout and "режим идеи" in r.stdout
    d = out / "deliverables"
    page = (d / "index.html").read_text(encoding="utf-8")
    assert "<title>Концепция продукта Книжная полка (демо)</title>" in page
    assert 'id="viability"' in page and "Концепт, не существующая функция" in page and 'id="current"' not in page
    if flags:
        assert not (d / "assets").exists() and "sha256-" in page
    else:
        assert (d / "assets" / "data.js").is_file() and SITE_CSP in page
        data = ps_data(d)
        assert data["d-registry"] and not re.search(r"репозитор|скан", page, re.I)         # оболочка без данных: в режиме идеи нет слов про репозиторий
        assert (d / "data" / "proposals.csv").is_file()
        # концепт-стили и концепт-раздел — в app.css
        assert "badge-concept" in (d / "assets" / "app.css").read_text(encoding="utf-8")


# ---------------------------------------------------------------- smoke на file:// (Chromium, WebKit; Firefox — если запускается)
def test_smoke_site_file_protocol(site):
    res = tb.run_smoke(site["out"], "--require", "all")
    by = {c["name"]: c for c in res["checks"]}
    assert res["mode"] == "site" and by["site-structure"]["status"] == "pass" and by["site-open-data"]["status"] == "pass"
    assert by["lite-assets"]["status"] == "pass" and by["engine-load-chromium"]["status"] == "pass"
    assert by["external-requests"]["detail"] == "0" and by["console-errors"]["detail"] == "0"
    tested = {e["name"] for e in res["engines"] if e["status"] == "tested"}
    assert "chromium" in tested and {e["name"] for e in res["engines"]} == {"chromium", "webkit", "firefox"}
    assert res["counts"]["site_index_bytes"] < 1048576


def test_smoke_site_missing_asset_fails(site, tmp_path):
    if not shutil.which("node") or not tb.playwright_dir(site["out"]):
        pytest.skip("нет node/playwright")
    out = tmp_path / "broken"
    shutil.copytree(site["out"], out)
    img = next(p for p in (out / "deliverables" / "assets" / "img").iterdir() if p.is_file() and p.suffix == ".webp")
    img.unlink()
    r = subprocess.run(["node", str(tb.SMOKE), str(out / "deliverables" / "index.html"), "--node-dir", tb.playwright_dir(out), "--json",
                        "--engines", "chromium"], capture_output=True, text=True, timeout=600)
    res = json.loads(r.stdout)
    assert r.returncode == 1 and not res["ok"]
    assert [c for c in res["checks"] if c["status"] == "fail" and c["name"] in ("lite-assets", "console-errors")]


def test_smoke_site_broken_script_reference_fails(site, tmp_path):
    if not shutil.which("node") or not tb.playwright_dir(site["out"]):
        pytest.skip("нет node/playwright")
    out = tmp_path / "broken"
    shutil.copytree(site["out"], out)
    (out / "deliverables" / "assets" / "app.js").unlink()
    r = subprocess.run(["node", str(tb.SMOKE), str(out / "deliverables" / "index.html"), "--node-dir", tb.playwright_dir(out), "--json",
                        "--engines", "chromium"], capture_output=True, text=True, timeout=600)
    assert r.returncode == 1 and not json.loads(r.stdout)["ok"]


def test_smoke_site_via_run_dir_and_single_unchanged(site, tmp_path):
    """smoke принимает и <OUT>; single по-прежнему проходит и честно пропускает проверки сайта."""
    if not shutil.which("node") or not tb.playwright_dir(site["out"]):
        pytest.skip("нет node/playwright")
    out = tmp_path / "run"
    shutil.copytree(site["out"], out)
    build(out, "--single")
    res = tb.run_smoke(out, "--engines", "chromium")
    by = {c["name"]: c for c in res["checks"]}
    assert res["mode"] == "single" and by["site-structure"]["status"] == "skip" and by["site-structure"].get("env")
    assert by["engine-load-chromium"]["status"] == "pass"
