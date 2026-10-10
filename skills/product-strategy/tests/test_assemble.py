"""Сборка стратегии и вспомогательные скрипты product-strategy 1.1 (pytest, без сети).

assemble_strategy, link_mockups, merge_sources, build_methodology, facts_scaffold, build_design_refs_readme, relocate_run
и правки check_links (плейсхолдеры, файлы использования, title = url) на демо-прогоне make_demo.py.
Запуск: python3 -m pytest skills/product-strategy/tests/test_assemble.py -q
"""
import csv
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
NEW_SCRIPTS = ["assemble_strategy.py", "link_mockups.py", "merge_sources.py", "build_methodology.py", "facts_scaffold.py",
               "build_design_refs_readme.py", "relocate_run.py", "check_links.py"]


def run(script, *args):
    e = {k: v for k, v in os.environ.items() if not k.startswith("TYPESAFE_")}
    return subprocess.run([sys.executable, "-B", str(SCRIPTS / script)] + [str(a) for a in args], capture_output=True, text=True, env=e, timeout=180)


def jload(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def jdump(p, obj):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    Path(p).write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def write(p, text):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    Path(p).write_text(text, encoding="utf-8")


@pytest.fixture(scope="module")
def base(tmp_path_factory):
    """Демо-прогон + оценка + графики + модель + проверка реестра (один раз на модуль)."""
    out = tmp_path_factory.mktemp("asm") / "demo"
    for cmd in (("make_demo.py", out), ("score.py", out), ("charts.py", out), ("model.py", out), ("check_registry.py", out, "--demo")):
        r = run(*cmd)
        assert r.returncode == 0, "%s: %s" % (cmd[0], r.stdout + r.stderr)
    assert (out / "data" / "scores.json").exists() and (out / "charts" / "charts-index.json").exists()
    return out


@pytest.fixture
def out(base, tmp_path):
    dst = tmp_path / "out"
    shutil.copytree(base, dst)
    (dst / "research" / "strategy.md").unlink()
    return dst


def sections(**texts):
    """{'6': 'текст'} → части build/parts для разделов; недостающие 1…17 заполняются короткими заготовками."""
    res = {}
    for n in range(1, 18):
        res[n] = texts.get(str(n), "## %d. Раздел %d\nТекст раздела." % (n, n))
    for k, v in texts.items():
        res[int(k)] = v if v.lstrip().startswith("##") else "## %s. Раздел %s\n%s" % (k, k, v)
    return res


def put_parts(out, texts, per_file=False):
    secs = sections(**texts)
    if per_file:
        for n, t in secs.items():
            write(out / "build" / "parts" / ("strategy-%02d.md" % n), t + "\n")
    else:                                                      # несколько разделов в одном файле
        write(out / "build" / "parts" / "strategy-A.md", "\n\n".join(secs[n] for n in range(1, 9)) + "\n")
        write(out / "build" / "parts" / "strategy-B.md", "\n\n".join(secs[n] for n in range(9, 18)) + "\n")


def codes(report, key="errors"):
    return {x["code"] for x in report[key]}


# ---------------------------------------------------------------- --help и коды выхода
@pytest.mark.parametrize("script", NEW_SCRIPTS)
def test_help(script):
    r = run(script, "--help")
    assert r.returncode == 0 and "usage" in r.stdout.lower()


def test_exit_2_without_data(tmp_path):
    for script in ("assemble_strategy.py", "link_mockups.py", "merge_sources.py", "build_methodology.py", "facts_scaffold.py"):
        assert run(script, tmp_path).returncode == 2, script
    assert run("build_design_refs_readme.py", tmp_path).returncode == 2
    assert run("relocate_run.py", tmp_path / "a", tmp_path / "b").returncode == 2


# ---------------------------------------------------------------- assemble_strategy
def test_assemble_placeholders_ranks_and_idempotent(out):
    scores = {s["id"]: s for s in jload(out / "data" / "scores.json")}
    assert jload(out / "data" / "proposals.json")[19].get("mockup") is None            # у P020 макета нет
    put_parts(out, {
        "1": "## 1. Резюме\nСтавка P001 стоит на месте {rank:P001}, с зависимостями {deprank:P002}. [допущение]\n\n"
             "![[mockup:?P001]]\n\nМежду ними текст.\n\n![[mockup:?P020]]\n\nКонец раздела.",
        "2": "## 2. Продукт\nКарта: ![[chart:effort-impact]]\n\nКод `{rank:P003}` не трогаем.\n\n```\n![[chart:nope]] {rank:P999}\n```",
        "10": "## 10. Дорожная карта\nСм. P004.\n\n![[ref:01-demo]]\n\n![[mockup:M02-demo]]"})
    r = run("assemble_strategy.py", out)
    assert r.returncode == 0, r.stdout + r.stderr
    text = (out / "research" / "strategy.md").read_text(encoding="utf-8")
    assert "стоит на месте %s," % scores["P001"]["rank"] in text
    dep = scores["P002"].get("dep_rank", scores["P002"]["rank"])
    assert "зависимостями %s." % dep in text
    assert "![[mockup:M01-demo]]" in text and "?P001" not in text and "?P020" not in text
    assert "`{rank:P003}`" in text and "![[chart:nope]]" in text                         # код не трогаем
    assert text.index("## 1. ") < text.index("## 2. ") < text.index("## 10. ") < text.index("## 17. ")
    rep = jload(out / "build" / "assemble-report.json")
    assert rep["ok"] and rep["mode"] == "parts" and rep["substituted"]["rank"] == 1
    assert any(n["code"] == "mockup_absent" and "макета для P020 нет" in n["message"] for n in rep["notes"])
    assert rep["mockups_removed"] == [{"proposal": "P020", "note": "макета для P020 нет"}]
    assert not rep["sections_missing"] and len(rep["parts"]) == 2
    before = text
    mtime = (out / "research" / "strategy.md").stat().st_mtime_ns
    r2 = run("assemble_strategy.py", out)
    assert r2.returncode == 0
    assert (out / "research" / "strategy.md").read_text(encoding="utf-8") == before
    assert (out / "research" / "strategy.md").stat().st_mtime_ns == mtime                # повторный запуск файл не трогает


def test_assemble_per_file_sections_and_order(out):
    put_parts(out, {"6": "## 6. Привлечение\nТекст про P001."}, per_file=True)
    r = run("assemble_strategy.py", out)
    assert r.returncode == 0, r.stdout + r.stderr
    text = (out / "research" / "strategy.md").read_text(encoding="utf-8")
    heads = [ln for ln in text.splitlines() if ln.startswith("## ")]
    assert [int(h.split(".")[0].split()[1]) for h in heads] == list(range(1, 18))


def test_assemble_broken_markers_are_errors(out):
    put_parts(out, {
        "3": "## 3. Рынок\n![[chart:no-such-chart]]\n\n![[mockup:Z99-none]]\n\n![[ref:99-none]]\n\n![[flow:nope]]\n\n"
             "Неизвестное P999 и {rank:P998}.\n\n![[chart:oops]\n\n![[video:x]]\n\n![[mockup:?P999]]"})
    r = run("assemble_strategy.py", out)
    assert r.returncode == 1, r.stdout + r.stderr
    rep = jload(out / "build" / "assemble-report.json")
    assert not rep["ok"]
    assert {"bad_chart", "bad_mockup", "bad_ref", "bad_flow", "bad_pid", "missing_rank", "bad_marker"} <= codes(rep)
    assert any("P999" in e["message"] for e in rep["errors"]) and all(e.get("section") == 3 or e["code"] == "missing_section" for e in rep["errors"] if "line" in e or "section" in e)
    # --lenient: те же проблемы, но код 0
    r2 = run("assemble_strategy.py", out, "--lenient")
    assert r2.returncode == 0
    rep2 = jload(out / "build" / "assemble-report.json")
    assert rep2["ok"] and not rep2["errors"] and {"bad_chart", "bad_mockup"} <= codes(rep2, "warnings")


def test_assemble_check_does_not_write(out):
    put_parts(out, {})
    r = run("assemble_strategy.py", out, "--check", "--json")
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)["checked_only"] is True
    assert not (out / "research" / "strategy.md").exists() and not (out / "build" / "assemble-report.json").exists()


def test_assemble_in_place_on_demo(base, tmp_path):
    out = tmp_path / "inplace"
    shutil.copytree(base, out)
    before = (out / "research" / "strategy.md").read_text(encoding="utf-8")
    r = run("assemble_strategy.py", out)
    assert r.returncode == 0, r.stdout + r.stderr
    rep = jload(out / "build" / "assemble-report.json")
    assert rep["mode"] == "in-place" and rep["markers"]["chart"] == 1 and rep["markers"]["mockup"] == 1 and rep["markers"]["ref"] == 1
    assert "missing_section" in codes(rep, "warnings")                    # в демо нет разделов 4–9
    assert (out / "research" / "strategy.md").read_text(encoding="utf-8").startswith("# Стратегия")
    assert before.split("\n")[0] == (out / "research" / "strategy.md").read_text(encoding="utf-8").split("\n")[0]
    assert run("assemble_strategy.py", out, "--require-all").returncode == 1


def test_assemble_in_place_fixes_placeholders(base, tmp_path):
    out = tmp_path / "inplace2"
    shutil.copytree(base, out)
    p = out / "research" / "strategy.md"
    p.write_text(p.read_text(encoding="utf-8") + "\nРанг {rank:P005}.\n", encoding="utf-8")
    assert run("assemble_strategy.py", out).returncode == 0
    rank = {s["id"]: s["rank"] for s in jload(out / "data" / "scores.json")}["P005"]
    assert "Ранг %s." % rank in p.read_text(encoding="utf-8")


def test_assemble_insert_mockups_idempotent(out):
    props = {p["id"]: p for p in jload(out / "data" / "proposals.json")}
    idx = {m["key"]: m for m in jload(out / "data" / "mockups-index.json")}
    cat_sec = {"acquisition": 6, "conversion": 7, "monetization": 8, "retention": 9}
    expected = {}
    for k, m in idx.items():
        pid = sorted(m["proposals"])[0]
        expected[k] = cat_sec.get(props[pid]["category"], 10)
    put_parts(out, {"7": "## 7. Конверсия\nУже вставлен макет: ![[mockup:M03-demo]]"})
    r = run("assemble_strategy.py", out, "--insert-mockups")
    assert r.returncode == 0, r.stdout + r.stderr
    text = (out / "research" / "strategy.md").read_text(encoding="utf-8")
    for key, sec in expected.items():
        assert text.count("![[mockup:%s]]" % key) == 1, key                        # ни один не продублирован
    rep = jload(out / "build" / "assemble-report.json")
    inserted = {k: i["section"] for i in rep["mockups_inserted"] for k in i["keys"]}
    assert inserted == {k: s for k, s in expected.items() if k != "M03-demo"}
    # блок лежит в конце своего раздела
    for sec in set(inserted.values()):
        chunk = text.split("## %d. " % sec, 1)[1].split("\n## ", 1)[0]
        assert "### Макеты концептов" in chunk
    again = run("assemble_strategy.py", out, "--insert-mockups")
    assert again.returncode == 0 and (out / "research" / "strategy.md").read_text(encoding="utf-8") == text
    assert {k for i in jload(out / "build" / "assemble-report.json")["mockups_inserted"] for k in i["keys"]} == set(inserted)   # части — источник: вставка та же
    # режим «на месте» ничего не дублирует
    inplace = run("assemble_strategy.py", out, "--insert-mockups", "--no-parts")
    assert inplace.returncode == 0 and (out / "research" / "strategy.md").read_text(encoding="utf-8") == text
    assert jload(out / "build" / "assemble-report.json")["mockups_inserted"] == []


def test_assemble_insert_mockups_bad_key_is_error(out):
    props = jload(out / "data" / "proposals.json")
    props[10]["mockup"] = "concepts/M99-ghost.html"
    jdump(out / "data" / "proposals.json", props)
    put_parts(out, {})
    assert run("assemble_strategy.py", out, "--insert-mockups").returncode == 1
    assert run("assemble_strategy.py", out, "--insert-mockups", "--lenient").returncode == 0


def test_assemble_urls_and_unlabeled_numbers(out):
    put_parts(out, {"5": "## 5. Позиционирование\nКонверсия вырастет на 15 % за квартал.\n\n"
                         "Конверсия вырастет на 20 % [оценка: эксперимент].\n\nСтоимость 500 ₽ по [тарифу](https://docs.python.org/3/).\n\n"
                         "Плейсхолдер https://… и https://example.com/x и https://docs.python.org/3/library/json.html."})
    r = run("assemble_strategy.py", out)
    assert r.returncode == 0, r.stdout + r.stderr
    rep = jload(out / "build" / "assemble-report.json")
    assert rep["unlabeled_numbers"]["count"] == 1 and "15 %" in rep["unlabeled_numbers"]["examples"][0]["text"]
    assert "bad_url" in codes(rep, "warnings") and "url_not_in_sources" in codes(rep, "warnings")
    bad = [w for w in rep["warnings"] if w["code"] == "bad_url"]
    assert len(bad) == 2 and all(w.get("section") == 5 for w in bad)


def test_assemble_uses_list_keys_when_no_index(out):
    (out / "charts" / "charts-index.json").unlink()
    put_parts(out, {"2": "## 2. Продукт\n![[chart:effort-impact]]"})
    r = run("assemble_strategy.py", out, "--json")
    rep = json.loads(r.stdout)
    # без индекса ключи берутся из `charts.py --list-keys`; если флага ещё нет — ключ нельзя подтвердить (ошибка), но скрипт не падает
    assert r.returncode in (0, 1) and (r.returncode == 0 or "bad_chart" in codes(rep))


# ---------------------------------------------------------------- link_mockups
def test_link_mockups(out):
    props = jload(out / "data" / "proposals.json")
    for p in props[:6]:
        p["mockup"] = None
    props[6]["mockup"] = "concepts/M77-missing.html"                                   # несуществующий файл
    jdump(out / "data" / "proposals.json", props)
    idx = jload(out / "data" / "mockups-index.json")
    idx.append({"key": "M07-orphan", "html": "mockups/concepts/M07-orphan.html", "png": "", "title": "без предложений", "proposals": [], "viewport": "1440x900", "kind": "concept"})
    idx.append({"key": "_base", "html": "mockups/concepts/_base.html", "png": "", "title": "эталон", "proposals": [], "viewport": "1440x900", "kind": "concept"})
    idx[0]["proposals"] = ["P001", "P999"]                                              # P999 нет в реестре
    jdump(out / "data" / "mockups-index.json", idx)
    jdump(out / "design-refs" / "02-extra.json", {"file": "mockups/concepts/M02-demo.html", "proposals": ["P010"], "title": "доп", "hotspots": []})
    before = (out / "data" / "proposals.json").read_text(encoding="utf-8")
    r = run("link_mockups.py", out, "--dry-run", "--json")
    assert r.returncode == 0, r.stderr
    rep = json.loads(r.stdout)
    assert (out / "data" / "proposals.json").read_text(encoding="utf-8") == before             # dry-run не пишет
    assert rep["changed"] >= 7 and any("P999" in w for w in rep["warnings"]) and any("M07-orphan" in w for w in rep["warnings"])
    assert any("P007" in w and "несуществующий" in w for w in rep["warnings"])
    assert not any("_base" in w for w in rep["warnings"]) and any("_base" in n for n in rep["notes"])
    r = run("link_mockups.py", out)
    assert r.returncode == 0
    got = {p["id"]: p for p in jload(out / "data" / "proposals.json")}
    assert got["P001"]["mockup"] == "concepts/M01-demo.html" and got["P001"]["mockups"] == ["concepts/M01-demo.html"]
    assert got["P010"]["mockup"] == "concepts/M02-demo.html"                                    # из design-refs
    assert got["P007"]["mockup"] == "concepts/M07-demo.html" or got["P007"]["mockup"] == "concepts/M77-missing.html"
    assert list(got["P001"]).index("mockups") == list(got["P001"]).index("mockup") + 1
    again = run("link_mockups.py", out, "--json")
    assert json.loads(again.stdout)["changed"] == 0                                             # идемпотентно
    assert run("link_mockups.py", out, "--strict").returncode == 1                              # предупреждения → 1


# ---------------------------------------------------------------- merge_sources
def make_sources_out(tmp_path):
    out = tmp_path / "srcrun"
    jdump(out / "data" / "sources.json", [
        {"id": "S001", "url": "https://Docs.Python.org/3/library/json.html#section", "title": "JSON", "date_checked": "2026-01-01", "used_for": "база", "status": 200, "note": ""},
        {"id": "S002", "url": "https://realsite.org/page/", "title": "https://realsite.org/pa…", "date_checked": "2026-01-02", "used_for": "старое", "status": 404, "note": "мёртвая"}])
    jdump(out / "data" / "sources-a.json", [
        {"id": "S001", "url": "https://docs.python.org/3/library/json.html?utm_source=x&utm_medium=y", "title": "", "date_checked": "2026-02-02", "used_for": "фрагмент A", "status": 301, "note": ""},
        {"id": "S002", "url": "https://another.org/guide/start", "title": "https://another.org/guide/start", "date_checked": "2026-02-02", "used_for": "A2", "status": None, "note": ""}])
    jdump(out / "data" / "sources-b.json", [
        {"id": "S001", "url": "https://…", "title": "плейсхолдер", "used_for": "B", "status": None, "note": ""},
        {"id": "S002", "url": "https://example.com/x", "title": "пример", "used_for": "B", "status": None, "note": ""},
        {"id": "S003", "url": "https://REALSITE.org/page", "title": "Страница", "used_for": "фрагмент B", "status": None, "note": "другое"}])
    prop = {"id": "P001", "evidence": [{"url": "https://docs.python.org/3/library/csv.html", "title": "CSV", "kind": "docs"},
                                       {"url": "https://example.org/placeholder", "title": "x", "kind": "docs"}],
            "steps": [{"what": "a", "doc_url": None}, {"what": "b", "doc_url": "https://docs.python.org/3/library/csv.html"}]}
    jdump(out / "data" / "proposals.json", [prop])
    jdump(out / "data" / "kanban.json", {"columns": [], "cards": [{"id": "P001", "links": ["https://git-scm.com/docs"]}]})
    jdump(out / "data" / "competitors.json", [{"slug": "comp", "name": "Конкурент", "url": "https://competitor.io/", "sources": ["https://competitor.io/pricing"]}])
    write(out / "research" / "strategy.md", "## 1. Резюме\nСм. [PEP 8](https://peps.python.org/pep-0008/), плейсхолдер https://… и https://broken.dev/(x. S002 источник.\n")
    write(out / "research" / "specs" / "P001-spec.md", "# Спека\nЕщё https://peps.python.org/pep-0008/ и https://git-scm.com/docs.\n")
    return out


def test_merge_sources(tmp_path):
    out = make_sources_out(tmp_path)
    r = run("merge_sources.py", out, "--dry-run", "--json")
    assert r.returncode == 0, r.stderr
    assert jload(out / "data" / "sources.json")[0]["id"] == "S001" and len(jload(out / "data" / "sources.json")) == 2       # dry-run не пишет
    assert not (out / "build" / "merge-sources-report.json").exists()
    r = run("merge_sources.py", out)
    assert r.returncode == 0, r.stdout + r.stderr
    res = jload(out / "data" / "sources.json")
    assert [s["id"] for s in res] == ["S%03d" % i for i in range(1, len(res) + 1)]
    urls = [s["url"] for s in res]
    keys = [u.lower().split("#")[0].split("?")[0].rstrip("/") for u in urls]
    assert len(set(keys)) == len(keys)                                                           # дублей нет
    first = res[0]
    assert first["status"] == 200 and first["date_checked"] == "2026-01-01"                      # status/date_checked существующих не тронуты
    assert first["title"] == "JSON" and "база" in first["used_for"] and "фрагмент A" in first["used_for"]
    second = res[1]
    assert second["status"] == 404 and second["date_checked"] == "2026-01-02"
    assert second["title"] == "Страница"                                                          # обрезанный URL в title заменён названием из дубля
    assert "мёртвая" in second["note"] and "другое" in second["note"] and "фрагмент B" in second["used_for"] and "старое" in second["used_for"]
    by = {s["url"]: s for s in res}
    another = by["https://another.org/guide/start"]
    assert another["title"] == "another.org / start" and "без названия" in another["note"]
    csv_src = by["https://docs.python.org/3/library/csv.html"]
    assert csv_src["title"] == "CSV" and csv_src["status"] is None and csv_src["date_checked"] is None and "P001" in csv_src["used_for"]
    assert by["https://git-scm.com/docs"]["used_for"].count("канбан") == 1 and "спецификации" in by["https://git-scm.com/docs"]["used_for"]
    assert by["https://peps.python.org/pep-0008/"]["title"] == "PEP 8" and "стратегия" in by["https://peps.python.org/pep-0008/"]["used_for"]
    assert by["https://competitor.io/"]["title"] == "Конкурент" and "https://competitor.io/pricing" in by
    assert all(s["title"] and s["title"] != s["url"] for s in res)
    bad = {"https://…", "https://example.com/x", "https://example.org/placeholder", "https://broken.dev/(x"}
    assert not bad & set(urls)
    rep = jload(out / "build" / "merge-sources-report.json")
    assert {d["url"] for d in rep["dropped"]} >= bad and rep["merged"] and rep["added"] and rep["retitled"]
    snapshot = (out / "data" / "sources.json").read_text(encoding="utf-8")
    assert run("merge_sources.py", out).returncode == 0
    assert (out / "data" / "sources.json").read_text(encoding="utf-8") == snapshot                # идемпотентно
    assert run("merge_sources.py", out, "--strict").returncode == 1                               # предупреждения об отброшенных


def test_merge_sources_keep_ids_and_example_flag(base, tmp_path):
    out = tmp_path / "demo2"
    shutil.copytree(base, out)
    r = run("merge_sources.py", out, "--dry-run", "--json")
    rep = json.loads(r.stdout)
    assert rep["added"] == [] and rep["dropped"]                                    # example.* без флага — плейсхолдеры
    r = run("merge_sources.py", out, "--dry-run", "--json", "--allow-example")
    rep = json.loads(r.stdout)
    assert len(rep["added"]) > 20 and rep["after"] == rep["before"] + len(rep["added"])
    sp = jload(out / "data" / "sources.json")
    sp[1]["id"] = "S077"
    jdump(out / "data" / "sources.json", sp)
    assert run("merge_sources.py", out, "--keep-ids", "--allow-example").returncode == 0
    ids = [s["id"] for s in jload(out / "data" / "sources.json")]
    assert "S077" in ids and len(set(ids)) == len(ids)


# ---------------------------------------------------------------- build_methodology
def test_build_methodology(out):
    r = run("build_methodology.py", out)
    assert r.returncode == 0, r.stdout + r.stderr
    text = (out / "research" / "methodology.md").read_text(encoding="utf-8")
    for h in ("## 1. Шкалы и якоря", "## 2. Формулы", "## 3. Фактические веса", "## 4. Чувствительность", "## 5. Классы доказательств",
              "## 6. Профиль", "## 7. TypeSafe", "## 8. Модель", "## 9. Ограничения"):
        assert h in text, h
    assert "methodology-anchors.md" in text and "| rice | 0.3 |" in text and "прогонов:" in text
    w = jload(out / "data" / "weights.json")
    assert str(w["composite"]["wsjf"]) in text
    props = jload(out / "data" / "proposals.json")
    assert "**%d**" % len(props) in text
    assert "_нет данных_" in text.split("## 7. TypeSafe")[1].split("## 8.")[0]                      # typesafe-jev.json в демо нет
    assert run("build_methodology.py", out).returncode == 0                                           # повтор поверх своего файла
    # рукописный файл не затирается
    write(out / "research" / "methodology.md", "# Рукописная методология\n")
    r = run("build_methodology.py", out)
    assert r.returncode == 0 and (out / "research" / "methodology.generated.md").exists()
    assert (out / "research" / "methodology.md").read_text(encoding="utf-8").startswith("# Рукописная")
    assert run("build_methodology.py", out, "--force").returncode == 0
    assert "generated-by" in (out / "research" / "methodology.md").read_text(encoding="utf-8")


def test_build_methodology_with_typesafe_and_missing_files(out):
    ids = [p["id"] for p in jload(out / "data" / "proposals.json")]
    items = {pid: {"p_success": (i % 10) / 10, "risk": 0.5} for i, pid in enumerate(ids)}
    jdump(out / "data" / "typesafe-jev.json", {"model": "jev-test", "date": "2026-10-10", "questions": [{"key": "p_success", "text": "?", "kind": "p"}], "items": items, "skipped": None})
    (out / "data" / "sensitivity.json").unlink()
    (out / "data" / "model.json").unlink()
    r = run("build_methodology.py", out, "--stdout")
    assert r.returncode == 0
    assert "jev-test" in r.stdout and "composite~p_success" in r.stdout
    assert r.stdout.count("_нет данных_") >= 2


# ---------------------------------------------------------------- facts_scaffold
def test_facts_scaffold(out):
    r = run("facts_scaffold.py", out)
    assert r.returncode == 0, r.stdout + r.stderr
    text = (out / "build" / "strategy-facts.md").read_text(encoding="utf-8")
    for h in ("## Цель и допущения", "## Топ-20 по рангу", "dep_rank", "## Кандидаты в «три главные ставки»", "## Три главные ставки (заготовка)",
              "## Допустимые ключи для вставок", "## Три сценария модели", "## Развилки владельца", "## Реестр в числах"):
        assert h in text, h
    scores = sorted(jload(out / "data" / "scores.json"), key=lambda s: s["rank"])
    assert scores[0]["id"] in text and "effort-impact" in text and "M01-demo" in text and "01-demo" in text
    assert "<заполнить>" in text and "Демо-вопрос про аудиторию" in text                              # развилки из questions-owner.md
    assert "pessimistic" in text and "base" in text and "optimistic" in text
    # второй запуск не затирает ручную правку
    (out / "build" / "strategy-facts.md").write_text(text + "\nРУЧНАЯ ПРАВКА\n", encoding="utf-8")
    assert run("facts_scaffold.py", out).returncode == 0
    assert "РУЧНАЯ ПРАВКА" in (out / "build" / "strategy-facts.md").read_text(encoding="utf-8")
    assert (out / "build" / "strategy-facts.new.md").exists()


def test_facts_scaffold_without_charts_and_scores(out):
    shutil.rmtree(out / "charts")
    (out / "data" / "scores.json").unlink()
    (out / "data" / "model.json").unlink()
    (out / "research" / "questions-owner.md").unlink()
    r = run("facts_scaffold.py", out, "--stdout")
    assert r.returncode == 0, r.stderr
    assert "_нет данных_" in r.stdout and "## Допустимые ключи для вставок" in r.stdout
    fc = [{"claim": "Число Issues", "was": "закрыто 20 из 24", "now": "открыто 5 из 24", "source": "gh issue list"}]
    jdump(out / "data" / "fact-check.json", fc)
    r = run("facts_scaffold.py", out, "--stdout")
    assert "закрыто 20 из 24" in r.stdout and "открыто 5 из 24" in r.stdout


# ---------------------------------------------------------------- build_design_refs_readme
def test_design_refs_readme(out):
    jdump(out / "design-refs" / "02-second.json", {"file": "mockups/concepts/M02-demo.html", "png": "design-refs/02-second.png", "title": "Второй экран",
                                                  "proposals": ["P002"], "kind": "mobile", "summary": "кратко", "shared": ["Шапка (.ps-top)"], "hotspots": [],
                                                  "questions": ["Нужен ли тёмный вариант?"]})
    write(out / "design-refs" / "02-second.md", "# Второй\n")
    write(out / "design-refs" / "03-only-md.md", "# Без JSON\n")
    r = run("build_design_refs_readme.py", out)
    assert r.returncode == 0, r.stdout + r.stderr
    text = (out / "design-refs" / "README.md").read_text(encoding="utf-8")
    assert "| 01 | `01-demo` | page | P001 | 1 | нет |" in text and "| 02 | `02-second` | mobile | P002 | 0 |" in text
    assert "## Как пользоваться" in text and "## Общие элементы" in text and "Шапка (.ps-top)" in text
    assert "Нужен ли тёмный вариант?" in text and "## Порядок постановки задач" in text
    assert "03-only-md" in text and "без `03-only-md.json`" in text
    assert text.index("`01-demo`", text.index("Порядок постановки")) > 0
    write(out / "design-refs" / "README.md", "# ручной\n")
    assert run("build_design_refs_readme.py", out).returncode == 0
    assert (out / "design-refs" / "README.generated.md").exists() and (out / "design-refs" / "README.md").read_text(encoding="utf-8") == "# ручной\n"


# ---------------------------------------------------------------- relocate_run
def test_relocate_run(tmp_path):
    repo = tmp_path / "repo"
    old = tmp_path / "scratch" / "run-1"
    assert run("make_demo.py", old).returncode == 0
    write(old / "build" / "briefs" / "x.md", "Команда: python3 build_all.py %s\nФайл %s/data/proposals.json и %s-other\n" % (old, old, old))
    write(old / "build" / "rebuild.sh", "#!/bin/sh\ncd %s && ls\n" % old)
    write(old / "data" / "note.json", json.dumps({"p": str(old) + "/research"}))
    write(old / "build" / "node" / "node_modules" / "m" / "index.js", "// %s\n" % old)
    write(old / "deliverables" / "big.html", "x" * (6 * 1024 * 1024) + str(old))                    # > 5 МБ — не обрабатывается
    (repo).mkdir()
    new = repo / "strategy" / "2026-10-10"
    r = run("relocate_run.py", old, new, "--repo", repo, "--inside-repo", "--branch", "docs/strategy-test", "--dry-run", "--json")
    assert r.returncode == 0, r.stdout + r.stderr
    assert not new.exists() and json.loads(r.stdout)["dry_run"] is True
    r = run("relocate_run.py", old, new, "--repo", repo, "--inside-repo", "--branch", "docs/strategy-test", "--json")
    assert r.returncode == 0, r.stdout + r.stderr
    rep = json.loads(r.stdout)
    assert rep["remaining_total"] == 0 and rep["replacements"] >= 6 and rep["replacement"] == "strategy/2026-10-10"
    assert rep["large_or_binary_with_old_path"] and rep["large_or_binary_with_old_path"][0]["file"] == "deliverables/big.html"
    assert "build_all.py" in rep["rebuild_command"]
    assert (old / "build" / "node").exists() and not (new / "build" / "node").exists()              # node не копируется
    x = (new / "build" / "briefs" / "x.md").read_text(encoding="utf-8")
    assert "strategy/2026-10-10/data/proposals.json" in x and "build_all.py strategy/2026-10-10\n" in x
    assert "%s-other" % old in x                                                                    # соседний путь с общим префиксом не задет
    cfg = jload(new / "build" / "run-config.json")
    assert cfg["output"] == {"dir": str(new.resolve()), "inside_repo": True, "git_branch": "docs/strategy-test"} and cfg["repo"]["path"] == str(repo.resolve())
    assert "build/node/" in (new / ".gitignore").read_text(encoding="utf-8")
    assert "Перенос папки прогона" in (new / "build" / "STATUS.md").read_text(encoding="utf-8")
    # ни одного упоминания старого пути в обработанных файлах и в отчёте (кроме больших файлов)
    pat = re.compile(re.escape(str(old)) + r"(?![\w\-])")
    leftovers = [f for f in new.rglob("*") if f.is_file() and f.name != "big.html" and pat.search(f.read_bytes().decode("utf-8", "ignore"))]
    assert leftovers == []


def test_relocate_run_absolute_and_move(tmp_path):
    old, new = tmp_path / "a" / "run", tmp_path / "b" / "run2"
    assert run("make_demo.py", old).returncode == 0
    r = run("relocate_run.py", old, new, "--move", "--no-inside-repo", "--json")
    assert r.returncode == 0, r.stdout + r.stderr
    rep = json.loads(r.stdout)
    assert not old.exists() and rep["remaining_total"] == 0 and rep["replacement"] == str(new.resolve())
    assert jload(new / "build" / "run-config.json")["output"]["inside_repo"] is False
    # повторный запуск на месте: старого пути нет, новая папка уже на месте — заменять нечего, код 0
    assert run("relocate_run.py", old, new).returncode == 0
    # целевая папка занята
    old2 = tmp_path / "c"
    assert run("make_demo.py", old2).returncode == 0
    assert run("relocate_run.py", old2, new).returncode == 2


# ---------------------------------------------------------------- check_links
def test_check_links_placeholders_files_and_titles(out):
    p = out / "research" / "strategy.md"
    p.write_text("## 1. Резюме\nПлейсхолдер https://… и пример https://example.com/a, реальная <https://docs.python.org/3/> ссылка.\n", encoding="utf-8")
    write(out / "research" / "specs" / "P001-spec.md", "См. https://… ещё раз.\n")
    src = jload(out / "data" / "sources.json")
    src.append({"id": "S900", "url": "https://docs.python.org/3/library/json.html", "title": "https://docs.python.org/3/library/js…", "date_checked": None, "used_for": "", "status": None, "note": ""})
    jdump(out / "data" / "sources.json", src)
    before = (out / "data" / "sources.json").read_text(encoding="utf-8")
    r = run("check_links.py", out, "--offline")
    assert r.returncode == 0, r.stderr
    assert (out / "data" / "sources.json").read_text(encoding="utf-8") == before                    # sources.json не меняется, плейсхолдеры не записаны
    assert "https://…" not in before
    rows = {x["url"]: x for x in csv.DictReader(open(out / "data" / "links-check.csv", encoding="utf-8"))}
    ph = rows["https://…"]
    assert "неверный формат" in ph["verdict"] and "research/strategy.md" in ph["files"] and "research/specs/P001-spec.md" in ph["files"]
    ex = rows["https://example.com/a"]
    assert "example" in ex["verdict"] and "research/strategy.md" in ex["files"]
    assert rows["https://docs.python.org/3/"]["verdict"].startswith("не проверялось")
    assert "используется в" in r.stdout and "без названия" in r.stdout and "S900" in r.stdout
    assert run("check_links.py", out, "--offline", "--strict").returncode == 1
    j = run("check_links.py", out, "--offline", "--json")
    data = json.loads(j.stdout)
    assert any(t["id"] == "S900" for t in data["no_title"]) and any(x["url"] == "https://…" and x["files"] for x in data["problems"])
