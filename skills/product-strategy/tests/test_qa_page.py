"""Эпик E-QA-PAGE (docs/plans/2026-10-11-feedback-triage.md): генератор страницы и smoke.

Q1 — класс num только для числовых колонок (таблица «Сообщества» с длинным audience_size, A-1.13, B-48);
Q2 — smoke: «пустые области» таблиц и высота карточки — предупреждения (статус warn), а не провалы;
Q4 — тёмная тема статус-меток (.st-ok/.st-bad/✓ матрицы) на токенах продукта, где «dark» встречается в :not(...);
универсальный перенос в ячейках и блоках (<wbr> в длинных токенах), мобильная ширина.

  PS_NODE_DIR=~/.cache/product-strategy/node python3 -m pytest skills/product-strategy/tests/test_qa_page.py -q
"""
import json
import re
import shutil
import subprocess

import pytest

import test_build_html as tb

bh = tb.bh

LONG_AUDIENCE = ("около 120 тысяч участников, из них активных в обсуждениях примерно 8–10 тысяч в неделю "
                 "по оценке модераторов сообщества")

# как в реальном прогоне «Слышно»: тёмная тема — [data-theme=dark], светлая — [data-theme=light] и светлый @media,
# селектор которого содержит «dark» внутри :not(...) — раньше эти светлые токены уходили в тёмную тему
TOKENS_CSS = """
:root { --font-sans: "Inter", system-ui, sans-serif; --radius: 14px; }
[data-theme="dark"] { color-scheme: dark; --bg: #071719; --surface: #102428; --surface-2: #182e34; --text: #eafffb;
  --muted: #8fb3ad; --border: #1e4852; --primary: #2fd3bf; }
[data-theme="light"] { color-scheme: light; --bg: #f3f8f7; --surface: #e8f1ef; --surface-2: #ffffff; --text: #0b2a2c;
  --muted: #4f6866; --border: #d6e3e0; --primary: #0b7d70; }
@media (prefers-color-scheme: light) {
  :root:not([data-theme="dark"]) { --bg: #f3f8f7; --surface: #e8f1ef; --surface-2: #ffffff; --text: #0b2a2c;
    --muted: #4f6866; --border: #d6e3e0; }
}
"""


def rjson(p):
    return json.loads(p.read_text(encoding="utf-8"))


def wjson(p, data):
    p.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


@pytest.fixture(scope="module")
def qa(tmp_path_factory):
    """Демо: длинная текстовая «аудитория» у первого сообщества, токены продукта со светлым @media и :not([data-theme=dark])."""
    out = tb.make_demo(tmp_path_factory.mktemp("qa") / "run", 40)
    comm = rjson(out / "data" / "communities.json")
    comm[0]["audience_size"] = LONG_AUDIENCE
    comm[0]["self_promo_rules"] = "только в пятничной ветке; ссылка на GitHub — в комментарии, не в посте"
    wjson(out / "data" / "communities.json", comm)
    (out / "mockups").mkdir(exist_ok=True)
    (out / "mockups" / "tokens.css").write_text(TOKENS_CSS, encoding="utf-8")
    stdout, page = tb.build(out)
    return {"out": out, "page": page, "stdout": stdout}


# ---------------------------------------------------------------- Q1: num по типу данных
def test_num_col_detection():
    for v in ("12 000", "~50k", "1,5 млн", "≈ 30 %", "12 000+", "$9.99", "12–15k", 5, 3.5):
        assert bh.is_num_text(v), v
    for v in ("около 12 тыс. участников", "много", "5 000 участников", True, "high"):
        assert not bh.is_num_text(v), v
    assert bh.num_col(["12 000", "—", None, "5k", ""])
    assert not bh.num_col(["12 000", LONG_AUDIENCE])
    assert not bh.num_col([None, "—", ""])            # пустая колонка — не числовая


def market_table(page, title):
    m = re.search(r"<h3>" + re.escape(title) + r" \(\d+\)</h3><div class=\"tbl\">(.*?)</table>", page, re.S)
    assert m, title
    return m.group(1)


def test_communities_text_audience_not_num(qa):
    t = market_table(qa["page"], "Сообщества")
    assert '<th class="aud">Аудитория</th>' in t and '<th class="rules">Правила самопромо</th>' in t
    row = re.search(r"<tr><td>[^\n]*?" + re.escape(LONG_AUDIENCE[:20]), t)
    assert row and 'class="num">' + LONG_AUDIENCE[:10] not in t
    assert re.search(r'<td class="aud">' + re.escape(LONG_AUDIENCE[:20]), t)
    assert '<td class="num" data-v=' in t                # «Риск бана» остаётся числовой
    css = qa["page"]
    assert "table.comm td.rules,table.comm th.rules{min-width:220px}" in css


def test_communities_numeric_audience_stays_num(tmp_path):
    out = tb.make_demo(tmp_path / "run", 20)
    comm = rjson(out / "data" / "communities.json")
    for i, c in enumerate(comm):
        c["audience_size"] = ["12 000", "~50k", "1,5 млн", "—", 800][i % 5]
    wjson(out / "data" / "communities.json", comm)
    _, page = tb.build(out)
    t = market_table(page, "Сообщества")
    assert '<th class="num">Аудитория</th>' in t and '<td class="num">12 000</td>' in t


# ---------------------------------------------------------------- перенос: <wbr> в длинных токенах, CSS
def test_wbr_long_tokens():
    s = bh.wbr_long("setExactAndAllowWhileIdle и https://example.com/a/b?x=1&amp;y=2 обычные слова")
    assert "set<wbr>Exact<wbr>And" in s and "https://<wbr>example.<wbr>com/<wbr>a/" in s
    assert "&amp;" in s and "&<wbr>amp" not in s and "&amp<wbr>;" not in s
    assert "обычные слова" in s                                          # короткие слова не трогаются
    a = '<a href="https://example.com/very/long/path/abcdef">https://example.com/very/long/path/abcdef</a>'
    out = bh.wbr_long(a)
    assert out.startswith('<a href="https://example.com/very/long/path/abcdef">') and "<wbr>" in out   # атрибуты целы


def test_universal_wrap_css(qa):
    page = qa["page"]
    assert re.search(r"main\{[^}]*overflow-wrap:break-word", page)
    assert ".tbl td{overflow-wrap:break-word;word-break:normal}" in page
    assert "main .tag,main .st-ok,main .st-bad,main .st-unk,main .ok{white-space:normal;max-width:100%;overflow-wrap:anywhere}" in page  # телефон
    # markdown-таблица: длинный токен в ячейке получает <wbr>
    md = bh.Markdown()
    html = md.render("| a | b |\n|---|---|\n| setExactAndAllowWhileIdleCompat | x |\n")
    assert "set<wbr>Exact" in html


# ---------------------------------------------------------------- Q4: тёмная тема статус-меток
def test_parse_tokens_not_dark_selector():
    base, dark = bh.parse_tokens(TOKENS_CSS)
    assert base["bg"] == "#f3f8f7" and dark["bg"] == "#071719" and dark["surface"] == "#102428"
    v = bh.theme_vars(base, dark)
    assert v["light"]["--ps-bg"] == "#f3f8f7" and v["dark"]["--ps-bg"] == "#071719"


def test_dark_tokens_with_light_bg_ignored():
    """«Тёмные» токены со светлым фоном не переворачивают тёмную тему: остаётся нейтральная тёмная."""
    v = bh.theme_vars({}, {"bg": "#f3f8f7", "text": "#0b2a2c"})
    assert bh.luminance(bh.parse_color(v["dark"]["--ps-bg"])) < 0.2


@pytest.mark.parametrize("tokens", [({}, {}), "slyshno", ({"accent": "#f5a623", "bg": "#101418", "text": "#e8eaed"}, {})])
def test_status_colors_contrast(tokens):
    base, dark = bh.parse_tokens(TOKENS_CSS) if tokens == "slyshno" else tokens
    v = bh.theme_vars(base, dark)
    for m, mode in v.items():
        surf, surf2 = bh.parse_color(mode["--ps-surface"]), bh.parse_color(mode["--ps-surface-2"])
        acc = bh.parse_color(mode["--ps-accent"])
        soft = 0.13 if m == "light" else 0.22
        for key, tint in (("--ps-ok", (21, 128, 61)), ("--ps-bad", (180, 35, 24))):
            fg = bh.parse_color(mode[key])
            for bg in (surf, surf2, bh.mix(surf, tint, 0.14), bh.mix(surf2, tint, 0.14), bh.mix(surf, acc, soft)):
                assert bh.contrast(fg, bg) >= 4.5, (m, key, mode[key], bg)


def test_status_css_uses_theme_vars(qa):
    page = qa["page"]
    assert "color:var(--ps-ok,#166534)" in page and "color:var(--ps-bad,#9f1f14)" in page
    assert not re.search(r"[{;]color:#(4ade80|f87171)", page)     # нет жёстких «тёмных» цветов в правилах — только переменные темы
    assert "table.cm tr.self td.n,table.cm tr.self td.u{color:var(--ps-text)}" in page


# ---------------------------------------------------------------- smoke (node + playwright)
def test_smoke_long_audience_and_dark_tokens(qa):
    """A-1.13/B-48: длинная «аудитория» — geometry-*-1440 зелёный (Chromium и WebKit), 820 и 390 тоже; контраст в трёх темах."""
    res = tb.run_smoke(qa["out"], "--engines", "chromium,webkit")
    by = {c["name"]: c for c in res["checks"]}
    for eng in ("chromium", "webkit"):
        for v in ("1440", "820", "390"):
            c = by.get("geometry-%s-%s" % (eng, v))
            assert c, (eng, v)
            if c["status"] == "skip" and c.get("env"):
                continue
            assert c["status"] == "pass", c
            assert c["data"]["pageWidth"] <= c["data"]["viewport"]
    for t in ("contrast-light", "contrast-dark", "contrast-auto-dark"):
        assert by[t]["status"] == "pass", by[t]


def inject_empty_area(page):
    long_cell = " ".join(["длинное значение раздувает колонку"] * 14)
    rows = "".join("<tr><td>%s</td><td>тип %d</td><td>%s</td><td>%s</td></tr>"
                   % (long_cell if i == 0 else "к%d" % i, i, "обычная заметка средней длины " * 3, "ещё одна заметка " * 4) for i in range(6))
    table = ('<h3>Таблица с пустой областью</h3><div class="tbl"><table class="data"><thead><tr><th>Короткая</th><th>Тип</th>'
             "<th>Заметка</th><th>Ещё</th></tr></thead><tbody>" + rows + "</tbody></table></div>")
    marker = "<h3>Сообщества ("
    assert marker in page
    return page.replace(marker, table + marker, 1)


def test_smoke_warnings_not_failures(qa, tmp_path):
    """Q2: «пустая область» таблицы и карточка выше --max-row-height — статус warn и строка в warnings, код выхода 0."""
    if not shutil.which("node") or not tb.playwright_dir(qa["out"]):
        pytest.skip("нет node/playwright")
    out = tmp_path / "w"
    shutil.copytree(qa["out"], out)
    target = out / "deliverables" / "index.html"
    target.write_text(inject_empty_area(target.read_text(encoding="utf-8")), encoding="utf-8")
    r = subprocess.run(["node", str(tb.SMOKE), str(target), "--node-dir", tb.playwright_dir(out), "--json", "--engines", "chromium",
                        "--max-row-height", "300"], capture_output=True, text=True, timeout=600)
    if r.returncode == 3:
        pytest.skip(r.stderr.strip())
    res = json.loads(r.stdout)
    by = {c["name"]: c for c in res["checks"]}
    g = by["geometry-chromium-1440"]
    assert g["status"] == "warn", g
    assert any("Таблица с пустой областью" in w and "«Короткая»" in w for w in g["data"]["tableWarn"]), g["data"]["tableWarn"]
    assert g["data"]["tall"], g["data"]
    assert by["geometry-chromium-390"]["status"] == "warn" and "карточек выше 300 px" in by["geometry-chromium-390"]["detail"]
    assert any("пустая область" in w for w in res["warnings"])
    assert r.returncode == 0 and res["ok"] and res["warned"] >= 3, [c for c in res["checks"] if c["status"] == "fail"]


# ---------------------------------------------------------------- склейка: build_all, init_run, render_brief, check_env
import argparse  # noqa: E402
import importlib.util  # noqa: E402
import os  # noqa: E402
import sys  # noqa: E402


def load(name):
    spec = importlib.util.spec_from_file_location("ps_" + name, tb.SCRIPTS / (name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(tb.SCRIPTS))
    spec.loader.exec_module(mod)
    return mod


def run_py(script, *args):
    return subprocess.run([sys.executable, str(tb.SCRIPTS / script)] + [str(a) for a in args], capture_output=True, text=True)


def ba_args(**kw):
    d = dict(only="", skip="", links=False, strict=False, typesafe=False, track=False, single=False, lite=False, zip=False, engines=None)
    d.update(kw)
    return argparse.Namespace(**d)


def test_build_all_plan_strict_flowcheck_disclosure(tmp_path):
    ba = load("build_all")
    out = tb.make_demo(tmp_path / "run", 10)
    cfg = rjson(out / "build" / "run-config.json")
    steps = {n: (en, why, cmd) for n, en, why, cmd in ba.plan(out, cfg, ba_args(strict=True))}
    assert "--strict" not in steps["html"][2]                       # демо-прогон: разделы неполные намеренно
    real = dict(cfg, assumptions=[], disclosure="none")
    steps = {n: (en, why, cmd) for n, en, why, cmd in ba.plan(out, real, ba_args(strict=True))}
    assert steps["html"][2][-1] == "--strict"
    assert steps["disclosure"][0] and steps["disclosure"][2][-2:] == ["disclosure-check", str(out)]
    assert steps["flowcheck"][2][1].endswith("check_flow.mjs")
    full = {n: en for n, en, *_ in ba.plan(out, dict(cfg, disclosure="full"), ba_args())}
    assert full["disclosure"] is False
    (out / "data" / "flows.json").unlink()
    assert {n: (en, why) for n, en, why, _ in ba.plan(out, cfg, ba_args())}["flowcheck"] == (False, "нет схем data/flows.json")


def test_build_all_partial_summary_honest(tmp_path):
    """A-1.12e / L7: --only — «частичный запуск», остальные шаги «не запускались», рядом итог последнего полного прогона."""
    out = tb.make_demo(tmp_path / "run", 10)
    r = run_py("build_all.py", out, "--only", "score")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "Итог (частичный запуск --only score): запущенные шаги собраны" in r.stdout and "всё собрано" not in r.stdout
    assert "не запускались в этом вызове: " in r.stdout and "Полного прогона ещё не было" in r.stdout
    assert not (out / "build" / "build-all-last.json").exists()
    r = run_py("build_all.py", out, "--skip", "links,pptx,pdf,smoke,mockups,xlsx,deck,html,flowcheck")
    assert r.returncode == 0, r.stdout + r.stderr
    last = rjson(out / "build" / "build-all-last.json")
    assert last["summary"].startswith("всё собрано") and "html" in last["not_run"] and last["steps"]
    r = run_py("build_all.py", out, "--only", "score")
    assert "Итог последнего полного прогона (%s): всё собрано" % last["date"] in r.stdout


def test_init_run_external_phases(tmp_path):
    out = tmp_path / "run"
    (out / "build").mkdir(parents=True)
    wjson(out / "build" / "run-config.json", {"product": {"name": "X", "mode": "external"}, "strategy": {}})
    assert run_py("init_run.py", out).returncode == 0
    st = (out / "build" / "STATUS.md").read_text(encoding="utf-8")
    assert "- [ ] 1. Понимание продукта без кода: store_stats.py, app_scan.py, сайт" in st and "трекер" in st
    assert "- — repo_scan.py: режим external" in st and "- — repo_facts.py:" in st and "repo_scan, issues_export" not in st
    r = run_py("init_run.py", out, "--done", "1", "--force")
    assert r.returncode == 0, r.stderr
    assert "- [x] 1. Понимание продукта без кода" in (out / "build" / "STATUS.md").read_text(encoding="utf-8")
    out2 = tmp_path / "repo-run"                                           # обычный режим не меняется
    (out2 / "build").mkdir(parents=True)
    wjson(out2 / "build" / "run-config.json", {"product": {"name": "X", "mode": "repo"}, "strategy": {}})
    assert run_py("init_run.py", out2).returncode == 0
    st2 = (out2 / "build" / "STATUS.md").read_text(encoding="utf-8")
    assert "repo_scan, issues_export" in st2 and "Не применяется" not in st2


def test_render_brief_requester_line(tmp_path):
    rb = load("render_brief")
    out = tb.make_demo(tmp_path / "run", 10)
    cfgp = out / "build" / "run-config.json"
    cfg = rjson(cfgp)
    cfg.setdefault("project", {}).update({"requester_role": "analyst", "product_owner": "ООО «Пример»"})
    wjson(cfgp, cfg)
    ctx = rb.Ctx(tb.SKILL / "templates" / "briefs" / "registry-generator.md", out, {})
    facts = rb.r_product_facts(ctx)
    assert "- Заказчик: сторонний аналитик / подрядчик, владелец продукта: ООО «Пример»." in facts
    cfg["project"].pop("requester_role"); cfg["project"].pop("product_owner")
    wjson(cfgp, cfg)
    assert "Заказчик:" not in rb.r_product_facts(rb.Ctx(tb.SKILL / "templates" / "briefs" / "registry-generator.md", out, {}))


def test_check_env_selftest(tmp_path):
    """A-3.6: XLSX всегда (stdlib); PPTX/PDF — OK или SKIP без модулей, но не FAIL."""
    j = tmp_path / "st.json"
    r = run_py("check_env.py", "--selftest", "--json", j)
    rows = {x["format"]: x for x in rjson(j)["selftest"]}
    assert r.returncode == 0, r.stdout + r.stderr
    assert rows["XLSX"]["status"] == "OK" and re.search(r"листов [1-9]", rows["XLSX"]["detail"])
    for f in ("PPTX", "PDF"):
        assert rows[f]["status"] in ("OK", "SKIP"), rows[f]
    assert "Итог самопроверки: форматы собираются и открываются" in r.stdout
