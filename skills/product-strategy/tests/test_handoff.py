# -*- coding: utf-8 -*-
"""Файл задач для Claude Code (scripts/handoff.py, references/handoff.md): структура, пути, разделы, горизонт и подробность,
идемпотентность, защита ручной правки, --list-sections. Демо-данные — make_demo.py и make_concept_demo.py во временных папках.
pytest tests/test_handoff.py"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import handoff  # noqa: E402

PY = [sys.executable, "-B"]
TASKS = "deliverables/CLAUDE_CODE_TASKS.md"
TASK_RE = re.compile(r"^- \[ \] \*\*([A-Z]+-?P?\d+) · ", re.M)
PATH_RE = re.compile(r"`([^`\s<>*]+)`")
FILE_EXT = (".md", ".json", ".html", ".css", ".svg", ".png", ".csv", ".xlsx")


def run(*args, cwd=None):
    return subprocess.run(PY + [str(SCRIPTS / args[0])] + [str(a) for a in args[1:]], capture_output=True, text=True, timeout=300, cwd=cwd)


def handoff_run(out, *args):
    r = run("handoff.py", out, *args)
    assert r.returncode == 0, r.stdout + r.stderr
    return r


def read(out, name=TASKS):
    return (Path(out) / name).read_text(encoding="utf-8")


def add_materials(out):
    """Спецификация, эксперимент, токены, предложение с тегом legal и связь с issue — то, чего нет в демо."""
    props = json.loads((out / "data" / "proposals.json").read_text(encoding="utf-8"))
    by = {p["id"]: p for p in props}
    target = next(p for p in props if p["category"] == "acquisition" and not p.get("mockup") and p["horizon"] == "now")
    target["tags"] = list(target.get("tags") or []) + ["legal"]
    (out / "data" / "proposals.json").write_text(json.dumps(props, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "research" / "specs").mkdir(parents=True, exist_ok=True)
    (out / "research" / "specs" / "P001-history.md").write_text(
        "# P001. История\nПриоритет: P1\n\n## Проблема\nx\n\n## Критерии приёмки\n- История открывается за 2 с\n- Видны последние 50 правок\n\n"
        "## Оценка\n3 дня\n", encoding="utf-8")
    (out / "research" / "experiments").mkdir(parents=True, exist_ok=True)
    (out / "research" / "experiments" / "E01-door.md").write_text(
        "# E01. Фейковая дверь истории\nПредложение: P002 «x» · Ставка: 1 · Тип: фейковая дверь\n\n## Гипотеза\nЕсли показать кнопку, "
        "то 10 % нажмут.\n\n## Метрики\nCTR кнопки; защитная — отказы.\n", encoding="utf-8")
    (out / "mockups" / "tokens.css").write_text(":root{--bg:#fff}\n", encoding="utf-8")
    (out / "data" / "issue-links.json").write_text(json.dumps({"P001": [12]}), encoding="utf-8")
    return target["id"], by


@pytest.fixture(scope="module")
def base(tmp_path_factory):
    root = tmp_path_factory.mktemp("handoff")
    demo, concept = root / "demo", root / "concept"
    for script, out in (("make_demo.py", demo), ("make_concept_demo.py", concept)):
        r = run(script, out)
        assert r.returncode == 0, r.stderr
        r = run("score.py", out)
        assert r.returncode == 0, r.stderr
    legal_id, _ = add_materials(demo)
    return {"demo": demo, "concept": concept, "legal_id": legal_id}


@pytest.fixture
def demo(base, tmp_path):
    out = tmp_path / "demo"
    shutil.copytree(base["demo"], out)
    return out


@pytest.fixture
def concept(base, tmp_path):
    out = tmp_path / "concept"
    shutil.copytree(base["concept"], out)
    return out


def task_ids(text):
    return TASK_RE.findall(text)


def path_tokens(text):
    out = []
    for tok in PATH_RE.findall(text):
        if tok.startswith(("http", "gh ", "area:", "horizon:")) or ":" in tok:
            continue
        if "/" in tok and (tok.endswith("/") or tok.endswith(FILE_EXT)):
            out.append(tok)
    return out


def assert_no_abs(text, *roots):
    for r in roots:
        assert str(r) not in text
    assert str(Path.home()) not in text
    assert not re.search(r"(?:^|[\s`(|])/(?:Users|home|private|tmp|var)/", text)


# ---------- структура ----------
@pytest.mark.parametrize("kind", ["demo", "concept"])
def test_structure_both_modes(kind, demo, concept):
    out = demo if kind == "demo" else concept
    handoff_run(out)
    text = read(out)
    heads = ["# Задачи для Claude Code", "## Инструкция для Claude Code", "## Карта материалов", "## Эпики и задачи", "## Макеты и референсы",
             "## Эксперименты", "## Приложение", "### Таблица соответствия", "### Предпосылки вне выбранного", "### Не вошли в выбранные разделы",
             "### Пропущенные материалы"]
    pos = [text.find(h) for h in heads]
    assert all(p >= 0 for p in pos) and pos == sorted(pos), list(zip(heads, pos))
    assert ("режим: концепция по идее" if kind == "concept" else "режим: по репозиторию") in text
    for must in ("gh issue list", "дождись подтверждения", "`epic`", "`area:", "`horizon:now`", "Ничего не удаляй", "Issue №", "sub-issue"):
        assert must in text, must
    assert "### Эпик: Интерфейс и дизайн (`area:ui`)" in text
    assert text.rstrip("\n").splitlines()[-1].startswith(handoff.MARKER_PREFIX)
    assert not re.search(r"<\s*/?[a-zA-Z!][^>]*>", re.sub(r"`[^`]*`", "", text)), "в файле не должно быть HTML (вне `кода`)"
    assert "{" + "PRODUCT}" not in text and "{SECTIONS}" not in text
    assert_no_abs(text, out)


@pytest.mark.parametrize("kind", ["demo", "concept"])
def test_all_paths_exist_outside_repo(kind, demo, concept):
    out = demo if kind == "demo" else concept
    handoff_run(out, "--detail", "full", "--horizon", "all")
    text = read(out)
    assert "вне git-репозитория" in text
    toks = path_tokens(text)
    assert len(toks) > 20
    missing = [t for t in toks if not (out / t).exists()]
    assert not missing, missing[:10]


def test_paths_inside_git_repo(base, tmp_path):
    if not shutil.which("git"):
        pytest.skip("нет git")
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    out = repo / "strategy" / "2026-10-11"
    shutil.copytree(base["demo"], out)
    handoff_run(out, "--detail", "full")
    text = read(out)
    assert "папка стратегии: `strategy/2026-10-11`" in text
    toks = path_tokens(text)
    assert toks and all(t.startswith("strategy/2026-10-11/") for t in toks)
    assert not [t for t in toks if not (repo / t).exists()]
    assert_no_abs(text, repo, out)
    # явный префикс главнее git
    handoff_run(out, "--repo-prefix", "docs/plan", "--out", tmp_path / "x.md")
    assert "`docs/plan/research/strategy.md`" in (tmp_path / "x.md").read_text(encoding="utf-8")


# ---------- разделы, горизонт, подробность ----------
def test_scope_ui_is_subset(demo):
    handoff_run(demo, "--out", demo / "all.md")
    handoff_run(demo, "--scope", "ui", "--out", demo / "ui.md")
    all_ids, ui_text = set(task_ids(read(demo, "all.md"))), read(demo, "ui.md")
    ui_ids = task_ids(ui_text)
    assert ui_ids and set(ui_ids) < all_ids
    assert ui_text.count("### Эпик:") == 1 and "### Эпик: Интерфейс и дизайн" in ui_text
    d = handoff.load(demo)
    for pid in ui_ids:
        if pid.startswith("P"):
            p = next(x for x in d["proposals"] if x["id"] == pid)
            assert handoff.classify(p, d)[0] == "ui"
    assert not any(i.startswith(("CT-", "E")) for i in ui_ids)
    assert "U01" in ui_ids                       # токены есть → работа по языку дизайна
    assert "раздел «Продукт и функции» не выбран" in ui_text


def test_horizon_and_detail_change_volume(demo):
    counts = {}
    for hz in ("now", "next", "all"):
        handoff_run(demo, "--horizon", hz, "--out", demo / ("h-%s.md" % hz))
        counts[hz] = len(task_ids(read(demo, "h-%s.md" % hz)))
    assert counts["now"] < counts["next"] < counts["all"]
    sizes = {}
    for det in handoff.DETAILS:
        handoff_run(demo, "--detail", det, "--out", demo / ("d-%s.md" % det))
        sizes[det] = read(demo, "d-%s.md" % det)
    assert len(sizes["links"]) < len(sizes["brief"]) < len(sizes["full"])
    assert task_ids(sizes["links"]) == task_ids(sizes["full"])            # подробность не меняет набор задач
    assert "  - Суть:" not in sizes["links"] and "  - Суть:" in sizes["brief"] and "  - Шаги:" in sizes["brief"]
    full = sizes["full"]
    assert "Критерии приёмки (из спецификации)" in full and "История открывается за 2 с" in full
    assert "Критерии приёмки (из KPI и критериев готовности Ганта)" in full
    assert "Доказательства: класс" in full and "Дешёвый тест:" in full and "Экран макета:" in full and "зоны: 1 «Заголовок»" in full
    assert "Критерии приёмки" not in sizes["brief"].split("## Карта материалов")[1]


def test_each_proposal_in_exactly_one_section(base, demo, concept):
    for out in (demo, concept):
        handoff_run(out, "--horizon", "all", "--scope", "all")
        text = read(out)
        ids = [i for i in task_ids(text) if re.fullmatch(r"P\d{3}", i)]
        props = [p["id"] for p in json.loads((out / "data" / "proposals.json").read_text(encoding="utf-8"))]
        assert sorted(ids) == sorted(props)                                # каждое ровно один раз
        assert "Нет: вошли все предложения реестра." in text
        m = handoff.build(handoff.load(out), "", list(handoff.SECTION_IDS), "brief", "all")
        seen = [t["id"] for sid in handoff.SECTION_IDS for t in m["tasks"][sid] if t["kind"] == "proposal"]
        assert sorted(seen) == sorted(props)
    text = read(demo)
    legal = base["legal_id"]
    assert re.search(r"### Эпик: Право, безопасность, риски.*?\*\*%s · " % legal, text, re.S)


def test_classify_rules():
    d = {"mockups": []}
    P = lambda **kw: dict({"id": "P900", "title": "x", "category": "product", "description": "", "steps": [], "tags": [], "risks": {}}, **kw)
    assert handoff.classify(P(mockup="concepts/M01.html", tags=["legal"]), d)[0] == "ui"            # ui главнее compliance
    assert handoff.classify(P(tags=["UX"]), d)[0] == "ui"
    assert handoff.classify(P(category="conversion", title="Новый экран входа"), d)[0] == "ui"
    assert handoff.classify(P(category="product", steps=[{"what": "собрать UI-kit"}]), d)[0] == "ui"
    assert handoff.classify(P(category="product", title="Guide для build"), d)[0] == "product"     # «ui» внутри слова — не признак
    assert handoff.classify(P(category="acquisition", title="Страницы сравнения"), d)[0] == "acquisition"
    assert handoff.classify(P(category="platform", tags=["security"]), d)[0] == "compliance"
    assert handoff.classify(P(category="retention", risks={"privacy": 4}), d)[0] == "compliance"
    assert handoff.classify(P(category="retention", risks={"privacy": 3}), d)[0] == "retention"
    assert handoff.classify(P(category="partnerships"), d)[0] == "acquisition"
    assert handoff.classify(P(category="new_lines"), d)[0] == "product"
    assert handoff.classify(P(category="weird"), d)[0] == "product"
    d2 = {"mockups": [{"key": "M09", "html": "mockups/concepts/M09.html", "proposals": ["P900"]}]}
    assert handoff.classify(P(category="analytics"), d2) == ("ui", "есть макет")


def test_experiments_and_prerequisites_outside(demo):
    props = json.loads((demo / "data" / "proposals.json").read_text(encoding="utf-8"))
    d = handoff.load(demo)
    ui_now = next(p for p in props if handoff.classify(p, d)[0] == "ui" and p["horizon"] == "now")
    prod = next(p for p in props if handoff.classify(p, d)[0] == "product")
    ui_now["dependencies"] = [prod["id"]]
    (demo / "data" / "proposals.json").write_text(json.dumps(props, ensure_ascii=False, indent=2), encoding="utf-8")
    assert run("score.py", demo).returncode == 0
    r = handoff_run(demo, "--scope", "ui,experiments", "--horizon", "now")
    text = read(demo)
    assert "предпосылок вне выбранного" in r.stderr
    sec = text.split("### Предпосылки вне выбранного")[1].split("###")[0]
    assert "| %s | %s " % (ui_now["id"], prod["id"]) in sec and "раздел «Продукт и функции» не выбран" in sec
    assert "%s (вне набора)" % prod["id"] in text
    ids = task_ids(text)
    exp = text.split("### Эпик: Эксперименты")[1]
    assert task_ids(exp)[0] == "E01"                                   # план эксперимента — первым, даже если P002 не now
    assert "Гипотеза: Если показать кнопку" in exp and "проверяет: P002" in exp
    assert any(i.startswith("CT-P") for i in ids)
    assert "| E01 | P002 | Если показать кнопку" in text


def test_missing_materials_minimal_out(tmp_path):
    out = tmp_path / "min"
    (out / "data").mkdir(parents=True)
    (out / "data" / "proposals.json").write_text(json.dumps([
        {"id": "P001", "title": "Сделать экран входа", "category": "conversion", "horizon": "now", "steps": ["шаг"], "effort_days": [1, 2]},
        {"id": "P002", "title": "Публичный API", "category": "platform", "horizon": "next", "dependencies": ["P001"]}], ensure_ascii=False), encoding="utf-8")
    r = handoff_run(out)
    text = read(out)
    assert "нет data/scores.json" in r.stderr
    assert "Макетов нет" in text and "Планов экспериментов нет" in text and "блок пропущен" in text
    assert "Нет data/scores.json" in text and "Нет research/strategy.md" in text
    assert "Интерфейсные задачи без макета: P001." in text
    assert "после: P001 (эпик «Интерфейс и дизайн»)" in text
    assert set(task_ids(text)) == {"P001", "P002"}
    r = run("handoff.py", tmp_path / "nothing")
    assert r.returncode == 2
    r = run("handoff.py", out, "--scope", "ui,bogus")
    assert r.returncode == 2 and "bogus" in r.stderr


# ---------- идемпотентность и ручная правка ----------
def test_idempotent_and_manual_edit_protected(concept):
    handoff_run(concept)
    f = concept / TASKS
    first = f.read_bytes()
    handoff_run(concept)
    assert f.read_bytes() == first
    assert not (concept / "deliverables" / "CLAUDE_CODE_TASKS.generated.md").exists()
    r = run("handoff.py", concept, "--dry-run")
    assert r.returncode == 0 and r.stdout.encode("utf-8") == first
    edited = first.decode("utf-8").replace("|  |", "| #7 |", 1)          # как если бы Claude Code вписал номер эпика
    f.write_text(edited, encoding="utf-8")
    r = handoff_run(concept, "--detail", "links")
    assert "правили вручную" in r.stderr
    assert f.read_text(encoding="utf-8") == edited
    gen = concept / "deliverables" / "CLAUDE_CODE_TASKS.generated.md"
    assert gen.exists() and "подробность: links" in gen.read_text(encoding="utf-8")
    handoff_run(concept, "--force")
    assert f.read_bytes() == first


def test_dry_run_writes_nothing(demo):
    r = handoff_run(demo, "--dry-run", "--scope", "ui")
    assert r.stdout.startswith("# Задачи для Claude Code") and not (demo / TASKS).exists()


def test_run_config_defaults_and_flags(demo):
    cfg_path = demo / "build" / "run-config.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    cfg["handoff"] = {"enabled": True, "scope": ["ui", "experiments"], "detail": "links", "horizon": "now", "ask_at_end": True}
    cfg_path.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    handoff_run(demo)
    text = read(demo)
    assert "горизонт: now (0–3 мес.) · подробность: links" in text
    assert "Интерфейс и дизайн (`ui`), Эксперименты и проверки гипотез (`experiments`)" in text
    handoff_run(demo, "--scope", "all", "--detail", "full", "--horizon", "all", "--force")
    text = read(demo)
    assert "разделы: все · горизонт: все горизонты · подробность: full" in text


def test_issue_links_prefill(demo):
    handoff_run(demo)
    assert re.search(r"^\| P001 \| ui \| Интерфейс и дизайн \|\s+#12 \|$", read(demo), re.M)


def test_no_html_and_secrets_scrubbed(demo):
    props = json.loads((demo / "data" / "proposals.json").read_text(encoding="utf-8"))
    props[0]["description"] = "Встроить <script>alert(1)</script> и ключ " + "ghp" + "_" + "abcdefghijklmnopqrstuvwxyz123456" + " в %s/notes" % Path.home()
    (demo / "data" / "proposals.json").write_text(json.dumps(props, ensure_ascii=False), encoding="utf-8")
    handoff_run(demo, "--detail", "full")
    text = read(demo)
    assert "<script>" not in text and "ghp_abcdef" not in text and "[скрыто]" in text
    assert_no_abs(text, demo)


# ---------- выбор разделов ----------
def test_list_sections_json(demo):
    r = handoff_run(demo, "--list-sections", "--json")
    secs = json.loads(r.stdout)
    assert [s["id"] for s in secs] == handoff.SECTION_IDS
    for s in secs:
        assert {"id", "title", "tasks", "p0", "has_mockups", "approx_chars", "summary", "strategy_sections"} <= set(s)
        assert isinstance(s["tasks"], int) and s["tasks"] <= s["tasks_all_horizons"]
        assert (s["approx_chars"] > 0) == (s["tasks"] > 0)
    by = {s["id"]: s for s in secs}
    assert by["ui"]["has_mockups"] and by["ui"]["tasks"] > 0 and by["compliance"]["tasks"] >= 1
    handoff_run(demo, "--horizon", "next")
    assert sum(s["tasks"] for s in secs) == len(task_ids(read(demo)))   # те же числа, что в файле (горизонт по умолчанию next)
    r = handoff_run(demo, "--list-sections", "--horizon", "now", "--json")
    assert sum(s["tasks"] for s in json.loads(r.stdout)) < sum(s["tasks"] for s in secs)


# ---------- подключение к опросу и сборке (1.4) ----------
def test_round6_answers_set_handoff_block():
    import intake
    cfg = intake.base_config(".")
    intake.apply_answers(cfg, {"Задачи": "Только интерфейс и дизайн", "Детальность": "Полные описания", "Срок задач": "Все, включая многолетние"})
    assert cfg["handoff"] == {"enabled": True, "ask_at_end": False, "scope": ["ui"], "detail": "full", "horizon": "all"}
    cfg = intake.base_config(".")
    intake.apply_answers(cfg, {"Задачи": "Нет"})
    assert cfg["handoff"]["enabled"] is False
    assert "Файл задач для Claude Code: нет" in intake.show(intake.finalize(cfg))


def test_save_writes_choice_to_run_config(tmp_path):
    out = tmp_path / "demo"
    assert subprocess.run([sys.executable, "-B", str(SCRIPTS / "make_demo.py"), str(out)], capture_output=True, text=True).returncode == 0
    r = subprocess.run([sys.executable, "-B", str(SCRIPTS / "handoff.py"), str(out), "--scope", "ui,product", "--detail", "links", "--horizon", "now", "--save"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    h = json.loads((out / "build" / "run-config.json").read_text(encoding="utf-8"))["handoff"]
    assert h["enabled"] is True and h["ask_at_end"] is False and h["scope"] == ["ui", "product"] and h["detail"] == "links" and h["horizon"] == "now"
