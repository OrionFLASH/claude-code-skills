# -*- coding: utf-8 -*-
"""WP-A 1.5: банки вопросов режима идеи — карточка «Начало» (личный режим, режим опроса, модели и effort — FB-003, SM 4),
замены банка для личного режима, условные блоки (ИИ, админка, данные, внешняя платформа FB-056, право, интерфейс,
прототип, контекст владельца, оплата — SM 5.1–5.8), быстрый режим и «по умолчанию для карточки» (SM 3.6),
взаимоисключающий мультивыбор (SM 3.4). pytest tests/test_concept_intake_banks.py"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import concept_banks as cb  # noqa: E402
import intake  # noqa: E402

PY = [sys.executable, "-B"]
IDEA = "Приложение для обмена книгами между соседями. Без денег и курьеров."
AR_REQUEST = ("!concept Платный сайт/приложение-трекер для игры ARC Raiders: предметы, спауны ARC-роботов, карты, статистика и "
              "прогресс игрока, синхронизация со Steam/сохранениями; ориентир — metaforge.app")


def env_home(tmp_path):
    e = {k: v for k, v in os.environ.items() if k not in ("TYPESAFE_API_KEY", "TYPESAFE_API_URL")}
    (tmp_path / "home").mkdir(parents=True, exist_ok=True)
    e["HOME"] = str(tmp_path / "home")
    return e


def run(tmp_path, *args):
    return subprocess.run(PY + [str(SCRIPTS / "intake.py")] + [str(a) for a in args], capture_output=True, text=True, timeout=120,
                          env=env_home(tmp_path))


def apply(tmp_path, answers, *extra, idea=IDEA, cwd=None):
    r = run(tmp_path, "concept-apply", "--repo", cwd or tmp_path, "--idea", idea, "--from-askuser", json.dumps(answers, ensure_ascii=False), *extra)
    assert r.returncode == 0, r.stdout + r.stderr
    out = next(line[4:] for line in r.stdout.splitlines() if line.startswith("OUT="))
    return r, Path(out), json.loads((Path(out) / "build" / "run-config.json").read_text(encoding="utf-8"))


ALL_NEW = list(cb.INTRO) + list(cb.PERSONAL.values()) + list(cb.all_block_questions())


# ---------- формат: ограничения AskUserQuestion и уникальность ключей ----------
def test_new_questions_fit_ask_user_question_and_headers_are_unique():
    headers = [q[3] for q in intake.CONCEPT_BANK] + [h for h, *_ in intake.CONCEPT_SETUP] + list(intake.HANDOFF_HEADERS) + \
              [q[3] for q in ALL_NEW] + list(cb.THEME_CONFIRM.values()) + list(intake.CHECK_HEADER_IDS) + ["Осн. форма", "Имя и папка", "Светофор"]
    assert len(set(headers)) == len(headers), [h for h in headers if headers.count(h) > 1]
    ids = [q[0] for q in intake.CONCEPT_BANK] + [q[0] for q in ALL_NEW]
    assert len(set(ids)) == len(ids)
    for qid, _t, _p, header, text, multi, opts in ALL_NEW:
        assert 1 <= len(header) <= 12, header
        assert text.endswith("?") or "(можно несколько)" in text, text
        assert 2 <= len(opts) <= 4, qid
        labels = [o[0] for o in opts]
        assert labels[0].endswith("(Recommended)") and sum("(Recommended)" in l for l in labels) == 1, qid
        assert all(1 <= len(l.split()) <= 7 for l in labels), labels
        assert all(isinstance(m, dict) and m for _l, _d, m in opts), qid
    assert len(intake.CONCEPT_BANK) == 40                                         # банк 1.4 не тронут


def test_intro_card_and_request_hint(tmp_path):
    r = run(tmp_path, "concept-intro", "--json", "--request", "Хочу сделать приложение только для меня: учёт тренировок")
    d = json.loads(r.stdout)
    assert [q["header"] for q in d["questions"]] == ["Для кого", "Опрос", "Модели", "Effort"]
    assert d["suggested"]["answer"] == "Только для меня"
    assert any("← из запроса" in o["description"] for o in d["questions"][0]["options"] if o["label"] == "Только для меня")


def test_intro_answers_write_contract_fields(tmp_path):
    _r, _out, cfg = apply(tmp_path, {"Для кого": "Публичный продукт (Recommended)", "Модели": "По умолчанию скилла",
                                     "Effort": "Да, явно по задаче", "Опрос": "Глубоко: все блоки целиком"})
    assert cfg["tools"]["agents"] == {"model_policy": "default", "effort_policy": "explicit"}          # FB-003
    assert cfg["project"]["audience"] == "public" and cfg["idea"]["interview_mode"] == "deep"
    _r, _out, cfg = apply(tmp_path / "b", {})
    assert cfg["tools"]["agents"] == {"model_policy": "triage", "effort_policy": "none"} and cfg["project"]["audience"] == "public"
    _r, _out, cfg = apply(tmp_path / "c", {"Модели": "всё на opus"})
    assert cfg["tools"]["agents"]["model_policy"] == "custom" and cfg["tools"]["agents"]["note"] == "всё на opus"


# ---------- личный режим (SM 4) ----------
def test_personal_bank_replaces_market_and_money_questions():
    d = intake.concept_questions_json(25, audience="personal")
    ids = [i["id"] for b in d["batches"] for i in b["ids"]]
    headers = [q["header"] for b in d["batches"] for q in b["questions"]]
    assert len(ids) == 25 and d["all_themes_covered"]
    assert {"p01", "p05", "p06", "p07", "p09"} <= set(ids)
    assert not {"Аудитория", "Модель", "Цена", "Кто платит", "Сегмент", "Успех"} & set(headers)
    pub = intake.concept_questions_json(25, audience="public")
    assert not any(i["id"].startswith("p") for b in pub["batches"] for i in b["ids"])


def test_personal_mode_config_and_seeds(tmp_path):
    _r, out, cfg = apply(tmp_path, {"Для кого": "Только для меня", "Моя задача": "Помогает принимать решения",
                                    "Владение": "До 500 ₽ / $5", "Название": "Полка"})
    assert cfg["project"]["audience"] == "personal" and cfg["project"]["release_outward"] is False
    assert cfg["project"]["goal"] == "personal" and cfg["strategy"]["monetization"] == "none" and cfg["strategy"]["paid_tier"] == "no"
    assert cfg["scope"]["keywords"] is False and cfg["scope"]["events"] is False and cfg["scope"]["competitors"] is True
    assert cfg["idea"]["facets"]["personal_job"] == "decisions" and "c26" in cfg["idea"]["replaced"]
    assert cfg["registry"]["category_minimums"] == "priority" and cfg["registry"]["capacity_cap"] is True
    assert "p01" in cfg["idea"]["answers"] and "c06" not in cfg["idea"]["unanswered"]
    r = subprocess.run(PY + [str(SCRIPTS / "concept_dossier.py"), str(out)], capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    seeds = (out / "build" / "seeds.md").read_text(encoding="utf-8")
    assert "## acquisition" not in seeds and "## monetization" not in seeds and "Личный режим" in seeds
    plan = (out / "build" / "search-plan.md").read_text(encoding="utf-8")
    assert "build vs buy" in plan and "## Деньги и цены" not in plan
    dossier = (out / "research" / "idea-dossier.md").read_text(encoding="utf-8")
    assert "Какую вашу задачу решает приложение?" in dossier and "только для владельца" in dossier


# ---------- условные блоки (SM 5.1–5.8, FB-056) ----------
def test_blocks_ai_core_admin_and_interface():
    d = intake.concept_blocks_json({"ИИ": "ИИ — ядро продукта", "Форма": "Веб-приложение (Recommended)"})
    by = {b["key"]: b for b in d["blocks"]}
    assert len(by["ai"]["ids"]) >= 8                                              # SM: ≥ 8 вопросов про ИИ при ИИ-ядре
    assert len(by["admin"]["ids"]) >= 6                                           # SM: ≥ 6 вопросов про админку для веба
    assert {"interface", "prototype", "owner", "payments"} <= set(by)
    assert all(len(b["questions"]) <= 4 for b in d["batches"]) and d["count"] == sum(len(b["ids"]) for b in d["blocks"])
    helper = intake.concept_blocks_json({"ИИ": "Только если упростит (Recommended)"})
    assert len({b["key"]: b for b in helper["blocks"]}["ai"]["ids"]) == 3
    none = intake.concept_blocks_json({"ИИ": "Без ИИ"})
    assert "ai" not in {b["key"] for b in none["blocks"]}
    fast = intake.concept_blocks_json({"ИИ": "ИИ — ядро продукта"}, mode="fast")
    assert sum(len(b["ids"]) for b in fast["blocks"]) < d["count"]


def test_platform_block_is_auto_and_fills_facets(tmp_path):
    d = intake.concept_blocks_json({}, request=AR_REQUEST)
    plat = next(b for b in d["blocks"] if b["key"] == "platform")
    assert "pl01" not in plat["ids"] and plat["ids"]                              # название платформы уже понято из запроса
    assert any(b["key"] == "data" for b in d["blocks"])
    ans = {"Пл: способ": "Открытые данные сообщества", "Пл: правила": "Только официальное (Recommended)",
           "Пл: закроют": "Ручной ввод как запасной путь (Recommended)"}
    _r, _out, cfg = apply(tmp_path, ans, "--request", AR_REQUEST, idea=AR_REQUEST[9:])
    f = cfg["idea"]["facets"]
    assert f["platform_dependency"] is True and f["platform_name"] == "ARC Raiders" and f["platform_access"] == "community"
    assert {"world", "user", "auth"} <= set(f["platform_data_needs"]) and f["platform_allowed"] == "official_only"
    assert cfg["idea"]["block_answers"]["pl03"]["block"] == "platform" and "platform" in cfg["idea"]["blocks_answered"]


def test_law_block_by_area_and_payment_channel(tmp_path):
    d = intake.concept_blocks_json({"Область": ["Деньги и платежи"]}, request="анализ акций и криптовалюты на бирже")
    law = next(b for b in d["blocks"] if b["key"] == "law")
    assert {"lw01", "fn01", "cr01"} <= set(law["ids"])
    _r, _out, cfg = apply(tmp_path, {"Оплата": "Платёжный сервис на сайте (Recommended)", "Фин: советы": "Нет: аналитика и обучение (Recommended)"})
    assert cfg["strategy"]["payment_channel"] == "direct" and cfg["idea"]["facets"]["fin_advice"] == "no_info_only"
    assert "Модель: web-direct" in _r.stdout                                      # профиль модели — в сводке (WP-B)


def test_block_custom_answers(tmp_path):
    ans = {"Пл: какая": "Steam", "Своё: репо": "~/dev/telegram_stat, https://github.com/me/lab", "Инт: вариант": "5 вариантов",
           "Инт: режимы": "Режимы под разные навыки", "Инт: ввод": "Мышь и тач, видимые кнопки (Recommended)",
           "Прот: нужен": "Ядро и один рабочий экран", "Адм: кто": "Только я (Recommended)", "ИИ: роль": ["Объясняет готовые данные (Recommended)", "Извлекает и классифицирует"]}
    _r, _out, cfg = apply(tmp_path, ans)
    f = cfg["idea"]["facets"]
    assert f["platform_name"] == "Steam" and f["owner_repos"] == ["~/dev/telegram_stat", "https://github.com/me/lab"]
    assert cfg["design"]["directions_count"] == 5 and cfg["design"]["modes"] == ["beginner", "pro"] and cfg["design"]["pointer_first"] is True
    assert f["prototype_needed"] is True and f["prototype_scope"] == "one_screen" and f["admin_who"] == "owner" and f["admin_needed"] is True
    assert f["ai_role"] == ["explain", "extract"]
    assert any(d.get("path") == "~/dev/telegram_stat" and d["kind"] == "repo" for d in cfg["sources"]["owner_docs"])


# ---------- быстрый режим и «по умолчанию для карточки» (SM 3.6) ----------
def test_fast_mode_theme_tables(tmp_path):
    d = intake.concept_questions_json(25, mode="fast", request=AR_REQUEST)
    qs = [q for b in d["batches"] for q in b["questions"]]
    assert len(qs) == 9 and len(d["batches"]) == 3 and all(set(q) == {"header", "question", "multiSelect", "options"} for q in qs)
    assert qs[0]["header"] == "Т1·Проблема" and "(из запроса)" in " ".join(q["question"] for q in qs)
    assert d["theme_batches"]["problem"]
    _r, _out, cfg = apply(tmp_path, {"Опрос": "Быстро: подтвердить таблицу", "Т1·Проблема": "Верно (Recommended)",
                                     "Т2·Аудитория": "Аудитория: малый бизнес", "Т4·Продукт": "Верно (Recommended)"})
    a = cfg["idea"]["answers"]
    assert a["c01"]["confirmed_default"] and a["c06"]["answer"] == "Малый бизнес и фрилансеры" and a["c06"]["correction"]
    assert cfg["idea"]["facets"]["segment"] == "smb" and "c01" not in cfg["idea"]["unanswered"] and "c16" in a


def test_card_default_applies_to_whole_batch(tmp_path):
    batches = intake.concept_questions_json(25)["batches"]
    first = batches[0]["ids"]
    _r, _out, cfg = apply(tmp_path, {first[0]["header"]: "по умолчанию для всей карточки"})
    a = cfg["idea"]["answers"]
    assert all(a[i["id"]].get("card_default") for i in first)
    assert not set(i["id"] for i in first) & set(cfg["idea"]["unanswered"])
    _r, _out, cfg = apply(tmp_path / "b", {"Боль": "по умолчанию"})
    assert cfg["idea"]["answers"]["c01"]["answer"] == "Заметная, но терпимая (Recommended)"


# ---------- взаимоисключающий мультивыбор (SM 3.4) ----------
def test_exclusive_multiselect_is_validated(tmp_path):
    opts = intake.CONCEPT_BY_ID["c38"][6]
    assert intake._split_multi(opts, ["Нет, обычные данные, Деньги и платежи"]) == ["Нет, обычные данные", "Деньги и платежи"]
    _r, _out, cfg = apply(tmp_path, {"Область": ["Нет, обычные данные, Деньги и платежи"]})
    a = cfg["idea"]["answers"]["c38"]
    assert a["exclusive_conflict"] and cfg["idea"]["facets"]["sensitive"] == ["finance"] and cfg["scope"]["legal"] is True
    fu = next(x for x in cfg["follow_up"] if x["header"] == "Чувств. обл.")
    assert set(fu["options"].values()) == {"sensitive", "none"}
    _r, _out, cfg = apply(tmp_path / "b", {"Своё: инстр.": ["Нет ограничений (Recommended)", "Только стандартная библиотека"]})
    assert cfg["idea"]["facets"]["tool_limits"] == ["stdlib_only"]


def test_flat_folder_option(tmp_path):
    _r, out, _cfg = apply(tmp_path, {"Папка": "Плоско: concept/<имя>/", "Название": "Полка"})
    assert out == (tmp_path / "concept" / "polka").resolve()
