# -*- coding: utf-8 -*-
"""WP-A 1.5: досье идеи (concept_dossier.py) — ключевые слова и перевод темы без заглушек <EN: …> (FB-022, FB-023),
пересмотр идеи C4.5: idea.version/pitch_v2/history и data/premises.json → досье, затравки, idea.json (FB-044, сторона
--refresh), разделы RQ и материалов владельца (FB-001, FB-002), совместимость с прогонами 1.4.
pytest tests/test_concept_intake_dossier.py"""
import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import concept_dossier as cd  # noqa: E402

PY = [sys.executable, "-B"]
AR_PITCH = ("Платный сайт/приложение-трекер для игры ARC Raiders: предметы, спауны ARC-роботов, карты, статистика и прогресс "
            "игрока, синхронизация со Steam/сохранениями; ориентир — metaforge.app")
AR_REQUEST = ("!concept " + AR_PITCH + ". Как конкуренты подключаются к игре? Можно ли получить сохранения игрока и откуда? "
              "Ссылки: официальный сайт игры https://arcraiders.com, один из лучших трекеров https://metaforge.app, моё прежнее "
              "исследование https://claude.ai/artifact/6TutY7eZ6edMZFxwKrzPsN — возьми как основу вопросов.")


def env_home(tmp_path):
    e = {k: v for k, v in os.environ.items() if k not in ("TYPESAFE_API_KEY", "TYPESAFE_API_URL")}
    (tmp_path / "home").mkdir(parents=True, exist_ok=True)
    e["HOME"] = str(tmp_path / "home")
    return e


def run(tmp_path, script, *args):
    return subprocess.run(PY + [str(SCRIPTS / script)] + [str(a) for a in args], capture_output=True, text=True, timeout=120,
                          env=env_home(tmp_path))


def make_out(tmp_path, *extra, answers=None):
    r = run(tmp_path, "intake.py", "concept-apply", "--repo", tmp_path, "--idea", AR_PITCH, "--from-askuser",
            json.dumps(answers or {"Форма": "Веб-приложение и мобильное приложение или удобная мобильная версия веба"}, ensure_ascii=False),
            "--request", AR_REQUEST, *extra)
    assert r.returncode == 0, r.stdout + r.stderr
    return Path(next(line[4:] for line in r.stdout.splitlines() if line.startswith("OUT=")))


def test_keywords_and_topic_without_en_placeholders(tmp_path):
    out = make_out(tmp_path, "--topic-en", "ARC Raiders tracker")
    r = run(tmp_path, "concept_dossier.py", out)
    assert r.returncode == 0, r.stderr
    plan = (out / "build" / "search-plan.md").read_text(encoding="utf-8")
    assert plan.count("<EN:") == 0 and "ARC Raiders tracker alternatives" in plan               # FB-023: 0 заглушек
    assert "Ключевые слова идеи: ARC Raiders, трекер" in plan and "платный" not in plan.split("## ")[0]
    assert "Внешняя платформа: ARC Raiders" in plan and "Вопрос запроса RQ" in plan
    idea = json.loads((out / "data" / "idea.json").read_text(encoding="utf-8"))
    assert idea["keywords"][0] == "ARC Raiders" and idea["topic_en"] == "ARC Raiders tracker" and idea["forms"] == ["web", "mobile_web"]
    assert idea["capacity"]["day_hours"] == 8 and len(idea["request_questions"]) >= 2 and len(idea["owner_docs"]) == 3


def test_topic_en_flag_persists_and_warning_without_it(tmp_path):
    out = make_out(tmp_path)
    r = run(tmp_path, "concept_dossier.py", out)
    assert r.returncode == 0 and "<EN:" in (out / "build" / "search-plan.md").read_text(encoding="utf-8")
    assert "заглушки <EN: …>" in r.stderr and "--topic-en" in r.stderr
    r = run(tmp_path, "concept_dossier.py", out, "--topic-en", "ARC Raiders tracker")
    assert r.returncode == 0 and "<EN:" not in (out / "build" / "search-plan.md").read_text(encoding="utf-8")
    cfg = json.loads((out / "build" / "run-config.json").read_text(encoding="utf-8"))
    assert cfg["idea"]["topic_en"] == "ARC Raiders tracker"
    assert run(tmp_path, "concept_dossier.py", out).returncode == 0                               # повтор (build_all) — без заглушек
    assert "<EN:" not in (out / "build" / "search-plan.md").read_text(encoding="utf-8")


def test_dossier_sections_rq_owner_materials_checks(tmp_path):
    out = make_out(tmp_path)
    assert run(tmp_path, "concept_dossier.py", out).returncode == 0
    d = (out / "research" / "idea-dossier.md").read_text(encoding="utf-8")
    assert "## Вопросы из запроса владельца (RQ)" in d and "| RQ01 |" in d
    assert "## Материалы владельца" in d and "основа вопросов" in d and "not_attempted" in d
    assert "## Дополнительные блоки опроса" in d and "ARC Raiders" in d
    assert "Ёмкость (одна для всех файлов" in d and "формы: web, mobile_web" in d
    idea = json.loads((out / "data" / "idea.json").read_text(encoding="utf-8"))
    assert any(q["kind"] == "check" and "не прочитан" in q["question"] for q in idea["open_questions"])
    assert "/Users/" not in d


def test_refresh_after_pivot(tmp_path):
    out = make_out(tmp_path, "--topic-en", "ARC Raiders tracker")
    assert run(tmp_path, "concept_dossier.py", out).returncode == 0
    cfgp = out / "build" / "run-config.json"
    cfg = json.loads(cfgp.read_text(encoding="utf-8"))
    cfg["idea"].update({"version": 2, "pitch_v2": "Личный план игрока ARC Raiders на открытых данных: что оставить, продать, переработать",
                        "history": [{"version": 1, "pitch": AR_PITCH, "date": "2026-10-17", "reason": "рынок опроверг платный справочник"}]})
    cfgp.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    (out / "data" / "premises.json").write_text(json.dumps({"version": 1, "premises": [
        {"id": "PR1", "kind": "distinct", "key": True, "text": "Платный справочник предметов нужен игрокам", "status": "refuted",
         "source": "research/market.md:12"},
        {"id": "PR2", "kind": "feasibility", "key": True, "text": "Синхронизация с сервером игры", "status": "refuted", "source": "research/integration.md:40"},
        {"id": "PR3", "kind": "audience", "key": False, "text": "Игроки ищут русский интерфейс", "status": "confirmed", "source": "data/keywords.json"},
        {"id": "PR4", "kind": "monetization", "key": True, "text": "Платят за личное без рекламы", "status": "partial", "source": "research/market.md:30"}],
        "decision": "narrow"}, ensure_ascii=False), encoding="utf-8")
    r = run(tmp_path, "concept_dossier.py", out, "--refresh")
    assert r.returncode == 0, r.stderr
    assert "Пересмотр идеи: версия 2" in r.stdout and "опровергнуто 2" in r.stdout
    idea = json.loads((out / "data" / "idea.json").read_text(encoding="utf-8"))
    assert idea["version"] == 2 and idea["pitch_v2"].startswith("Личный план") and idea["history"] and len(idea["premises"]) == 4
    d = (out / "research" / "idea-dossier.md").read_text(encoding="utf-8")
    assert "## Пересмотр идеи (C4.5)" in d and "Личный план игрока" in d and "опровергнута" in d
    assert "Опровергнуто исследованием" in d and d.index("> Личный план") < d.index("## Ответы по темам")
    seeds = (out / "build" / "seeds.md").read_text(encoding="utf-8")
    assert "НЕ предлагать (опровергнуто): Синхронизация с сервером игры" in seeds and "С оговоркой (частично)" in seeds
    plan = (out / "build" / "search-plan.md").read_text(encoding="utf-8")
    assert "план игрока ARC Raiders проблема" in plan                                          # тема — по идее v2
    assert "<EN: план игрока ARC Raiders>" in plan and "прежней версии идеи" in r.stderr         # перевод v1 устарел
    r = run(tmp_path, "concept_dossier.py", out, "--topic-en", "ARC Raiders player plan")
    assert "<EN:" not in (out / "build" / "search-plan.md").read_text(encoding="utf-8")


def test_old_run_config_still_builds(tmp_path):
    """Прогон 1.4.0: в run-config нет новых полей (keywords, topic_en, audience, forms, request_questions)."""
    out = make_out(tmp_path)
    cfgp = out / "build" / "run-config.json"
    cfg = json.loads(cfgp.read_text(encoding="utf-8"))
    for k in ("keywords", "keywords_source", "topic_en", "request_questions", "block_answers", "checks", "request", "decisions"):
        cfg["idea"].pop(k, None)
    for k in ("audience", "release_outward", "capacity"):
        cfg["project"].pop(k, None)
    cfg["product"].pop("forms", None)
    cfg["product"].pop("future_forms", None)
    cfg["sources"]["owner_docs"] = ["~/docs/old-research.md"]                                   # 1.4: строки, не объекты
    cfg.pop("registry", None)
    cfg.pop("git", None)
    cfg.pop("owner_rules", None)
    cfgp.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    r = run(tmp_path, "concept_dossier.py", out)
    assert r.returncode == 0, r.stderr
    idea = json.loads((out / "data" / "idea.json").read_text(encoding="utf-8"))
    assert idea["keywords"][0] == "ARC Raiders" and idea["audience"] == "public" and idea["owner_docs"] == []
    assert run(tmp_path, "intake.py", "show", cfgp).returncode == 0
    assert cd.keywords("приложение для обмена книгами")[:2] == ["обмена", "книгами"]
