# -*- coding: utf-8 -*-
"""Волна 2 (1.5.0): запросы пакетов к report.py, assemble_strategy.py, model.py, facts_scaffold.py, merge_proposals.py,
handoff.py, build_xlsx.py, build_deck_json.py, make_demo.py, make_concept_demo.py — таблицы REPORT (вопросы запроса с коротким
ответом, материалы владельца, решения до старта, нарезка, ретроспектива, второй раунд зависимостей, перенос из now, G8,
fact-check, прототип, открытые пункты сверки), маркеры [RQnn] (FB-001), формы mobile_web (wp-a №10), «Выводы исследования»
и канон с cases (FB-044/048, wp-g №11), предупреждение needs_details (wp-f C2), раздел прототипа и личные категории в
выгрузках (wp-g №19, wp-c №2), <title> узлов демо-схем и единый бейдж (FB-038, FB-033).
Запуск: python3 -m pytest tests/test_wave2_texts.py -q -p no:cacheprovider
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import report  # noqa: E402

PY = [sys.executable, "-B"]


def env():
    return {k: v for k, v in os.environ.items() if not k.startswith("TYPESAFE_")}


def run(script, *args):
    return subprocess.run(PY + [str(SCRIPTS / script)] + [str(a) for a in args], capture_output=True, text=True, env=env(), timeout=600)


def write(p, obj):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    Path(p).write_text(obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")


def jload(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def demo_src(tmp_path_factory):
    out = tmp_path_factory.mktemp("w2t") / "cdemo"
    assert run("make_concept_demo.py", out, "--proposals", "50").returncode == 0
    return out


@pytest.fixture()
def demo(demo_src, tmp_path):
    out = tmp_path / "cdemo"
    shutil.copytree(demo_src, out)
    return out


def upd_cfg(out, fn):
    cfg = jload(out / "build" / "run-config.json")
    fn(cfg)
    write(out / "build" / "run-config.json", cfg)
    return cfg


# ---------------------------------------------------------------- report.py
def test_report_tables_from_run_data(tmp_path):
    """wp-a №8, wp-c №6, wp-f D3, wp-g №6, wp-b №9: разделы REPORT из данных прогона."""
    out = tmp_path / "r"
    write(out / "build" / "run-config.json", {
        "mode": "concept", "product": {"name": "Тест"},
        "idea": {"request_questions": [{"id": "RQ01", "text": "Как подключиться к игре?", "kind": "research"},
                                       {"id": "RQ02", "text": "Сдать в PDF", "kind": "format"}],
                 "checks": [{"id": "mvp_capacity", "header": "Ёмкость MVP", "message": "MVP не помещается",
                             "options": [{"label": "Одна ключевая функция", "key": "single_feature"}]},
                            {"id": "b2b_social", "header": "B2B и соцсети", "message": "противоречие", "options": [{"label": "x", "key": "x"}]}],
                 "decisions": {"mvp_capacity": "single_feature"}},
        "sources": {"owner_docs": [{"url": "https://a.example", "role": "base", "status": "read"},
                                   {"url": "https://b.example", "role": "ref", "status": "blocked"},
                                   {"url": "https://c.example", "role": "ref", "status": "not_attempted"}]},
        "slicing": {"enabled": True, "decision": "slice", "source": "yellow",
                    "queues": [{"id": "alpha", "name": "Альфа", "goal": "ядро для себя", "enter_when": "сразу"}]}})
    write(out / "build" / "parts" / "strategy-03.md",
          "## 3. Рынок\n\nОфициального API нет, конкуренты читают сохранения через экспорт игрока [RQ01] [факт: wiki]. Дальше текст.\n")
    write(out / "build" / "retro.json", {"entries": [{"by": "owner", "what": "свой бриф", "why": "срочно", "file": "build/briefs/x.md"}],
                                         "journal": 1, "auto": 0, "by_owner": 1, "by_orchestrator": 0})
    write(out / "build" / "deps-patch.json", {"_summary": {"added": 7}})
    write(out / "build" / "merge-report.json", {"cap_now": {"demoted": [{"id": "P010", "effort_mid": 6}, {"id": "P011", "effort_mid": 4.5}]}})
    write(out / "build" / "collect-gaps.json", {"drafts_added": ["G8-01", "G8-02"], "fact_check_added": ["x"], "mismatches_open": 1})
    write(out / "build" / "fact-check-apply.json", {"date": "2026-10-19", "applied": ["a"], "already": [], "text_only": ["b"], "pending": [], "unconfirmed": ["c"]})
    write(out / "data" / "fact-check.json", [{"kind": "mockup_vs_registry", "proposal": "P012", "mockup": "M03", "summary": "в макете нет фильтра",
                                              "status": "open", "decision": None},
                                             {"fact": "цена", "phase1_value": "нет", "agent_value": "990", "resolved_value": "990", "applied": True,
                                              "fix": {"file": "data/competitors.json"}}])
    write(out / "data" / "sources-s1.json", [])
    write(out / "data" / "prototype.json", {"status": "ok", "modes": ["beginner"], "core_tests": {"passed": 12, "failed": 0}, "canon": {"errors": 0}})
    write(out / "data" / "model.json", {"reconciliation": {"items": [{"message": "выручка раньше платной вехи"}]}})
    write(out / "data" / "plan-baseline.json", {"gantt_contract": {"messages": ["нет задач в месяцах 7–12"]}})
    body = report.build_report(out)
    assert "| RQ01 | Как подключиться к игре? | build/parts/strategy-03.md § 3 | Официального API нет, конкуренты читают сохранения" in body
    assert "| RQ02 |" in body and "формат сдачи" in body
    assert "Материалы владельца: 3 (прочитано 1 / заблокировано 1 / не прочитано 1)" in body
    assert "решение до старта «Ёмкость MVP»: Одна ключевая функция" in body and "**решение до старта не получено**: B2B и соцсети" in body
    assert "нарезка на очереди: Альфа — ядро для себя (вход: сразу)" in body
    assert "Всего: 1 (владелец 1, оркестратор 0; из журнала 1" in body and "свой бриф" in body
    assert "Зависимостей добавлено вторым раундом (C7.5): 7" in body
    assert "Перенесено из now по ёмкости: 2 предложений, ≈ 10.5 дн." in body
    assert "черновиков G8 добавлено 2, записей fact-check 1, открытых расхождений 1" in body
    assert "fact-check: применено 1, только текст 1, открыто 1" in body
    assert "| P012 | M03 | в макете нет фильтра | open |" in body
    assert "Источники от авторов разделов: 1" in body and "Рабочий прототип: ok; режимы: beginner; тесты ядра — прошло 12" in body
    assert "выручка раньше платной вехи" in body and "нет задач в месяцах 7–12" in body


def test_report_g8_added_from_append(tmp_path):
    out = tmp_path / "r"
    write(out / "build" / "run-config.json", {"mode": "concept"})
    write(out / "build" / "merge-report.json", {"mode": "append", "groups": ["G8"], "added": ["P061", "P062"]})
    assert "G8 из макетов: добавлено в реестр 2" in report.build_report(out)


# ---------------------------------------------------------------- assemble_strategy: [RQnn]
def test_assemble_requires_rq_markers(demo):
    """FB-001 (wp-a №9): вопрос research/deliverable без маркера [RQ01] — ошибка (в --lenient — предупреждение); format — нет."""
    upd_cfg(demo, lambda c: c["idea"].__setitem__("request_questions", [
        {"id": "RQ01", "text": "Как найти соседей?", "kind": "research"}, {"id": "RQ02", "text": "PDF", "kind": "format"}]))
    r = run("assemble_strategy.py", demo, "--no-parts", "--check", "--json")
    rep = json.loads(r.stdout)
    codes = [e["code"] for e in rep["errors"]]
    assert r.returncode == 1 and codes.count("request_question_unanswered") == 1 and "RQ01" in json.dumps(rep["errors"], ensure_ascii=False)
    assert {q["id"]: q["found"] for q in rep["request_questions"]} == {"RQ01": False, "RQ02": False}
    r = run("assemble_strategy.py", demo, "--no-parts", "--check", "--lenient", "--json")
    assert "request_question_unanswered" in [w["code"] for w in json.loads(r.stdout)["warnings"]]
    s = demo / "research" / "strategy.md"
    text = s.read_text(encoding="utf-8")
    i = text.index("\n## 2.")
    s.write_text(text[:i] + "\n\nСоседей находим через чат дома [RQ01] [допущение].\n" + text[i:], encoding="utf-8")
    rep = json.loads(run("assemble_strategy.py", demo, "--no-parts", "--check", "--json").stdout)
    assert "request_question_unanswered" not in [e["code"] for e in rep["errors"]]
    assert next(q for q in rep["request_questions"] if q["id"] == "RQ01")["sections"] == [1]


# ---------------------------------------------------------------- model.py
def test_select_profile_mobile_web_and_payment_channel():
    """wp-a №10: mobile_web — оплата на сайте (web-direct); future_forms не считаются; payment_channel none — по типу."""
    import model
    assert model.select_profile({"product": {"type": "mobile", "forms": ["mobile", "mobile_web"]}})[0] == "web-direct"
    assert model.select_profile({"product": {"type": "mobile", "forms": ["mobile"], "future_forms": ["web"]}})[0] == "mobile-app"
    assert model.select_profile({"product": {"type": "saas"}, "strategy": {"payment_channel": "none"}})[0] == "saas"
    assert model.select_profile({"product": {"type": "saas"}, "strategy": {"payment_channel": "direct"}})[0] == "web-direct"


# ---------------------------------------------------------------- facts_scaffold
def test_facts_findings_block_and_demo_canon_cases(demo):
    """FB-044/FB-048 (wp-a №11): «Выводы исследования» из data/idea.json (pitch_v2, premises, request_questions);
    wp-g №11: канон демо-данных с label и cases."""
    ij = jload(demo / "data" / "idea.json")
    ij.update({"version": 2, "pitch_v2": "Обмен детскими книгами в одном доме",
               "premises": [{"id": "PR1", "kind": "distinct", "text": "Отличие от чатов дома", "status": "refuted", "source": "research/market.md:4"}],
               "request_questions": [{"id": "RQ01", "text": "Как найти соседей?", "kind": "research"}]})
    write(demo / "data" / "idea.json", ij)
    r = run("facts_scaffold.py", demo, "--stdout")
    assert r.returncode == 0, r.stderr
    assert "## Выводы исследования" in r.stdout and "Обмен детскими книгами в одном доме" in r.stdout
    assert "| Отличие от чатов дома | distinct | опровергнута | research/market.md:4 |" in r.stdout and "`[RQ01]`" in r.stdout
    assert run("facts_scaffold.py", demo, "--demo-canon", "--stdout").returncode == 0
    canon = jload(demo / "data" / "demo-canon.json")
    assert canon["label"] == "демо-данные" and canon["cases"] == [] and isinstance(canon["values"], dict)


# ---------------------------------------------------------------- merge_proposals: needs_details
def test_append_g8_warns_needs_details(demo):
    """wp-f C2: черновик G8 с needs_details: true при --append — «оценки не дописаны»."""
    props = jload(demo / "data" / "proposals.json")
    d = dict(props[0])
    for k in ("merged_from", "source_group"):
        d.pop(k, None)
    d.update({"id": "G8-01", "title": "Совершенно новая кнопка экспорта полки в календарь соседей", "needs_details": True,
              "description": "Уникальное описание черновика из макета без пересечений с реестром.", "scores": {}, "effort_days": None})
    write(demo / "data" / "proposals-draft-G8.json", [d])
    r = run("merge_proposals.py", demo, "--append", "G8")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "оценки не дописаны" in r.stdout and "G8-01" in r.stdout


# ---------------------------------------------------------------- выгрузки: личные категории, прототип в handoff
def test_personal_category_labels_in_exports():
    """wp-c №2: подписи личных категорий — из check_registry.CATEGORY_LABELS_RU; свои подписи выгрузок сохранены."""
    import build_deck_json
    import build_xlsx
    import handoff
    for mod in (build_xlsx, build_deck_json):
        assert mod.CATS["core"] == "Ядро" and mod.CATS["data-sources"] == "Источники данных" and mod.CATS["new_lines"] == "Новые линии"
        assert mod.CATS.get("неизвестная", "неизвестная") == "неизвестная"
    assert handoff.CATEGORY_SECTION["ux"] == "ui" and handoff.CATEGORY_SECTION["privacy-security"] == "compliance"
    assert handoff.CATEGORY_RU["maintenance"] == "поддержка и обновления"


def test_handoff_prototype_section(demo):
    """wp-g №19: prototype/HANDOFF.md + data/prototype.json → раздел «Перенос рабочего прототипа» с расхождениями."""
    write(demo / "data" / "prototype.json", {"status": "partial", "path": "prototype/index.html", "modes": ["beginner", "pro"],
                                             "core_tests": {"passed": 9, "failed": 1}, "canon": {"cases": 4, "errors": 0},
                                             "smoke": {"chromium": "ok", "webkit": "skipped"}})
    write(demo / "prototype" / "index.html", "<!doctype html>")
    write(demo / "prototype" / "js" / "core.js", "")
    write(demo / "prototype" / "HANDOFF.md", "# Перенос\n\n## Расхождения прототип ↔ боевая версия\n- хранение: localStorage вместо базы\n"
                                              "- ИИ: фикстуры вместо живой модели\n\n## Команды\n- node prototype/js/core.test.js\n")
    r = run("handoff.py", demo, "--force")
    assert r.returncode == 0, r.stdout + r.stderr
    text = (demo / "deliverables" / "CLAUDE_CODE_TASKS.md").read_text(encoding="utf-8")
    assert "## Перенос рабочего прототипа" in text and "localStorage вместо базы" in text and "фикстуры вместо живой модели" in text
    assert "prototype/js/core.js" in text and "Статус: partial; режимы: beginner, pro; тесты ядра: 9 прошло, 1 упало" in text
    assert text.index("## Перенос рабочего прототипа") < text.index("## Приложение")
    (demo / "data" / "prototype.json").unlink()
    run("handoff.py", demo, "--force")
    assert "Перенос рабочего прототипа" not in (demo / "deliverables" / "CLAUDE_CODE_TASKS.md").read_text(encoding="utf-8")


# ---------------------------------------------------------------- демо: <title> узлов схем и бейдж
def test_demo_flow_nodes_have_titles_and_badges(tmp_path, demo):
    """FB-038 (wp-d №12, №15; wp-e №1): у <g data-node> демо-схем первым дочерним — <title>; FB-033: бейдж с классом набора."""
    import re
    out = tmp_path / "pdemo"
    assert run("make_demo.py", out).returncode == 0
    for svg, base in ((out / "charts" / "flows" / "user-journey.svg", out), (demo / "charts" / "flows" / "first-use.svg", demo)):
        s = svg.read_text(encoding="utf-8")
        nodes = re.findall(r"<g data-node=\"[^\"]+\">(<[^>]+>)", s)
        assert nodes and all(n == "<title>" for n in nodes), nodes
        assert len(re.findall(r"<title>[^<]+: демо</title>", s)) == len(nodes)
        for f in (base / "mockups" / "concepts").glob("M*.html"):
            assert 'class="ps-concept-badge"' in f.read_text(encoding="utf-8")
