# -*- coding: utf-8 -*-
"""WP-A 1.5: разбор текста идеи и запроса в режиме идеи — имя, slug и ключевые слова (FB-022, SM 3.5), перевод темы
(FB-023), свободные ответы «Форма» и «Рынки» (FB-024, FB-025), вопросы запроса RQ (FB-001), материалы владельца (FB-002),
предзаполнение опроса (FB-055, SM 3.1). Эталоны — запросы боевых прогонов ARC Raiders и Smart Market Lens AI.
pytest tests/test_concept_intake_text.py"""
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
AR_PITCH = ("Платный сайт/приложение-трекер для игры ARC Raiders: предметы, спауны ARC-роботов, карты, статистика и прогресс "
            "игрока, синхронизация со Steam/сохранениями; ориентир — metaforge.app")
# реконструкция исходного запроса прогона ARC Raiders (раздел A1/A2 фидбэка): идея, вопросы, три ссылки владельца
AR_REQUEST = ("!concept " + AR_PITCH + ". Нужно: трекер предметов и их наличия, спауны ARC-роботов, интерактивная карта, статистика "
              "и прогресс игрока. Изучи конкурентов, российских и зарубежных, их сильные и слабые стороны. Как конкуренты подключаются "
              "к игре? Можно ли получить сохранения игрока и откуда? Как сделать синхронизацию со Steam? Насколько это выгодно? "
              "Предложи стратегию, архитектуру сайта и бэкенда. Сделай интерактивные кликабельные схемы и графики с дополнительной "
              "информацией по каждому элементу. Ссылки: официальный сайт игры https://arcraiders.com, один из лучших трекеров "
              "https://metaforge.app, моё прежнее исследование https://claude.ai/artifact/6TutY7eZ6edMZFxwKrzPsN — возьми как основу "
              "вопросов, самому исследованию целиком не следуй.")
SM_PITCH = ("Веб-сервис (адаптивная верстка, с заделом под мобильную версию/приложение) для анализа Московской биржи (акции, фьючерсы, "
            "срочный рынок; также СПб биржа) и крипторынка с помощью локальных LLM через Ollama. Расчёт «сколько вложить / насколько "
            "должна двинуться цена, чтобы заработать N», пункт цены, комиссии и тарифы, риск/прибыль, паттерны, скринеры движений. "
            "Крипто-раздел: анализатор кошельков, движение крупных средств, on-chain, агрегация нескольких бирж, новостные каналы с "
            "ИИ-анализом, подключение бесплатных API с инструкциями. 5 различных вариантов интерфейса на выбор, много графиков и "
            "3D-визуализации, бэкенд, БД.")


def env_home(tmp_path, **extra):
    e = {k: v for k, v in os.environ.items() if k not in ("TYPESAFE_API_KEY", "TYPESAFE_API_URL")}
    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)
    e["HOME"] = str(home)
    e.update(extra)
    return e


def apply(cwd, answers, *extra, idea=AR_PITCH, env=None):
    r = subprocess.run(PY + [str(SCRIPTS / "intake.py"), "concept-apply", "--repo", str(cwd), "--idea", idea, "--from-askuser",
                             json.dumps(answers, ensure_ascii=False)] + [str(x) for x in extra],
                       capture_output=True, text=True, timeout=120, env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    out = next(line[4:] for line in r.stdout.splitlines() if line.startswith("OUT="))
    return r, Path(out), json.loads((Path(out) / "build" / "run-config.json").read_text(encoding="utf-8"))


# ---------- FB-022, SM 3.5: имя ≤ 4 слов, сущность цела, slug без «Рабочее:» ----------
@pytest.mark.parametrize("pitch,name,slug", [
    (AR_PITCH, "Трекер ARC Raiders", "treker-arc-raiders"),
    ("Приложение для обмена книгами между соседями. Без денег и курьеров.", "Обмен книгами между соседями", "obmen-knigami-mezhdu-sosedyami"),
    (SM_PITCH, "Анализ Московской биржи", "analiz-moskovskoy-birzhi"),
    ("Бот для учёта лекарств в Telegram", "Учёт лекарств в Telegram", "uchet-lekarstv-v-telegram"),
    ("Smart Market Lens AI — веб-сервис для анализа рынка", "Smart Market Lens AI", "smart-market-lens-ai"),
    ("Демо: приложение для обмена книгами между соседями по дому. Взял почитать", "Обмен книгами между соседями", None),
])
def test_auto_name_is_short_and_keeps_entity(pitch, name, slug):
    n, s = intake.idea_name_slug(pitch)
    assert n == name and len(n.split()) <= 4
    if slug:
        assert s == slug
    for ent in ("ARC Raiders", "Telegram", "Smart Market Lens AI"):
        if ent in pitch and ent.split()[0] in n:
            assert ent in n                                                    # сущность не разрезана


def test_slug_from_topic_en_and_working_prefix_is_stripped():
    assert intake.idea_name_slug(AR_PITCH, topic_en="ARC Raiders tracker") == ("Трекер ARC Raiders", "arc-raiders-tracker")
    assert intake.idea_name_slug("x", "Рабочее: Smart Market Lens AI") == ("Smart Market Lens AI", "smart-market-lens-ai")
    assert intake.idea_name_slug("x", "Working title: Lens") == ("Lens", "lens")
    assert intake.clean_given_name("«Рабочее название: Полка»") == "Полка"


def test_keywords_keep_entities_and_drop_form_words():
    kw = intake.idea_keywords(AR_PITCH)
    assert kw[0] == "ARC Raiders" and "трекер" in kw and "предметы" in kw and "спауны" in kw
    assert not {"платный", "игры", "приложение-трекер", "arc", "raiders", "сайт"} & {k.lower() for k in kw}
    assert not any("-" in k and "arc" in k.lower() for k in kw)                # «ARC-роботов» — не ключевое слово
    sm = intake.idea_keywords(SM_PITCH)
    assert not {"веб-сервис", "адаптивная", "верстка", "заделом", "мобильную", "версию"} & set(sm)   # мусор прогона SM
    assert "Московской биржи" in sm


def test_concept_apply_name_slug_keywords_topic_en(tmp_path):
    r, out, cfg = apply(tmp_path, {"Название": "Придумай варианты (Recommended)"}, "--request", AR_REQUEST,
                        "--topic-en", "ARC Raiders tracker", env=env_home(tmp_path))
    assert cfg["product"]["name"] == "Трекер ARC Raiders" and cfg["idea"]["slug"] == "arc-raiders-tracker"
    assert out.parent.name == "arc-raiders-tracker" and cfg["idea"]["topic_en"] == "ARC Raiders tracker"
    assert cfg["idea"]["keywords"][0] == "ARC Raiders" and cfg["idea"]["keywords_source"] == "auto"
    assert "Имя: «Трекер ARC Raiders»" in r.stdout and "тема EN: ARC Raiders tracker" in r.stdout
    assert any(x["path"] == "idea.decisions.name" for x in cfg["follow_up"])     # имя — на подтверждение до «Начинаю?»
    _r, _out, cfg2 = apply(tmp_path / "b", {}, "--name", "Рейдер", "--slug", "raider", "--keywords", "ARC Raiders, трекер",
                           env=env_home(tmp_path))
    assert cfg2["product"]["name"] == "Рейдер" and cfg2["idea"]["slug"] == "raider" and cfg2["idea"]["keywords"] == ["ARC Raiders", "трекер"]
    assert not any(x["path"] == "idea.decisions.name" for x in cfg2["follow_up"])


# ---------- FB-024: свободный ответ «Форма» → все формы, веб-путь, уточнение основной формы ----------
@pytest.mark.parametrize("text,ptype,forms,future,ambiguous", [
    ("Веб-приложение и мобильное приложение или удобная мобильная версия веба", "saas", ["web", "mobile_web"], ["mobile"], False),
    ("веб и мобильная версия", "saas", ["web", "mobile_web"], [], False),
    ("PWA", "saas", ["web", "mobile_web"], [], False),
    ("iOS и Android", "mobile", ["mobile"], [], False),
    ("бот + сайт", "saas", ["web", "bot"], [], True),
    ("мини-приложение в Telegram", "bot", ["bot"], [], False),
    ("Сайт, мобильное приложение позже", "saas", ["web"], ["mobile"], False),
])
def test_parse_forms(text, ptype, forms, future, ambiguous):
    fp = cb.parse_forms(text)
    assert (fp["type"], fp["forms"], fp["future"], fp["ambiguous"]) == (ptype, forms, future, ambiguous)


def test_custom_form_answer_reference_and_follow_up(tmp_path):
    _r, _out, cfg = apply(tmp_path, {"Форма": "Веб-приложение и мобильное приложение или удобная мобильная версия веба"},
                          env=env_home(tmp_path))
    assert cfg["product"]["type"] == "saas" and cfg["product"]["forms"] == ["web", "mobile_web"]
    assert cfg["product"]["future_forms"] == ["mobile"]
    assert any("Форма продукта" in a and "saas" in a for a in cfg["assumptions"])
    _r, _out, cfg = apply(tmp_path / "b", {"Форма": "бот + сайт"}, env=env_home(tmp_path))
    fu = next(x for x in cfg["follow_up"] if x["path"] == "product.type")
    assert fu["header"] == "Осн. форма" and set(fu["options"].values()) == {"saas", "bot"}
    _r, _out, cfg = apply(tmp_path / "c", {"Форма": "бот + сайт", "Осн. форма": "Бот в мессенджере"}, env=env_home(tmp_path))
    assert cfg["product"]["type"] == "bot"                                       # ответ на уточнение принят в concept-apply
    _r, _out, cfg = apply(tmp_path / "d", {"Форма": "Веб-приложение (Recommended)"}, env=env_home(tmp_path))
    assert cfg["product"]["forms"] == ["web"]


# ---------- FB-025: хвост ответа «Рынки» не теряется ----------
def test_markets_tail_is_kept(tmp_path):
    assert intake.market_remainder("Основной русский и английский, плюс языки локализации игры") == "языки локализации игры"
    assert intake.market_remainder("RU + EN") == ""
    r, _out, cfg = apply(tmp_path, {"Рынки": "Основной русский и английский, плюс языки локализации игры"}, env=env_home(tmp_path))
    assert cfg["strategy"]["markets"] == ["ru", "en"] and cfg["strategy"]["markets_note"] == "языки локализации игры"
    assert any("языки локализации игры" in a for a in cfg["assumptions"])
    assert any(q["source"] == "c07" and "языки локализации игры" in q["text"] for q in cfg["idea"]["request_questions"])
    assert "Рынки: ru, en (+ уточнение: «языки локализации игры»" in r.stdout


# ---------- FB-001: вопросы запроса → idea.request_questions ----------
def test_request_questions_from_reference_request():
    rq = cb.request_questions(AR_REQUEST, AR_PITCH)
    assert len(rq) >= 8 and [q["id"] for q in rq[:3]] == ["RQ01", "RQ02", "RQ03"]
    texts = " ".join(q["text"] for q in rq)
    for frag in ("подключаются к игре", "сохранения игрока", "синхронизацию со Steam", "выгодно", "архитектуру", "кликабельные схемы"):
        assert frag in texts, frag
    kinds = {q["kind"] for q in rq}
    assert {"research", "deliverable", "format"} <= kinds
    assert not any("claude.ai" in q["text"] or "https://" in q["text"] for q in rq)


def test_request_questions_in_run_config_and_llm_list(tmp_path):
    r, _out, cfg = apply(tmp_path, {}, "--request", AR_REQUEST, env=env_home(tmp_path))
    assert len(cfg["idea"]["request_questions"]) >= 8 and "Вопросы запроса (RQ" in r.stdout
    llm = json.dumps(["Как конкуренты подключаются к игре?", {"text": "Схемы кликабельные", "kind": "format"}], ensure_ascii=False)
    _r, _out, cfg = apply(tmp_path / "b", {}, "--request", AR_REQUEST, "--request-questions", llm, env=env_home(tmp_path))
    rq = cfg["idea"]["request_questions"]
    assert [q["id"] for q in rq] == ["RQ01", "RQ02"] and rq[1]["kind"] == "format" and rq[0]["source"] == "llm"


# ---------- FB-002: ссылки владельца → run-config ----------
def test_owner_urls_are_classified_and_routed(tmp_path):
    urls = cb.classify_urls(AR_REQUEST)
    by = {u["domain"]: u for u in urls}
    assert set(by) == {"arcraiders.com", "metaforge.app", "claude.ai"}
    assert by["arcraiders.com"]["kind"] == "platform_site" and by["metaforge.app"]["kind"] == "competitor"
    assert by["claude.ai"]["kind"] == "artifact" and by["claude.ai"]["role"] == "base" and by["claude.ai"]["tool"] == "artifact-read"
    assert all(u["status"] == "not_attempted" for u in urls)
    r, _out, cfg = apply(tmp_path, {}, "--request", AR_REQUEST, env=env_home(tmp_path))
    docs = cfg["sources"]["owner_docs"]
    assert len(docs) == 3 and all(d["status"] == "not_attempted" and d.get("role") for d in docs)
    assert cfg["sources"]["external"]["site"] == "https://arcraiders.com" and "metaforge.app" in cfg["sources"]["competitor_list"]
    assert "https://arcraiders.com" in cfg["idea"]["facets"]["platform_urls"]
    assert "Материалы владельца (3)" in r.stdout and "шаг C0.6" in r.stdout


def test_local_paths_in_request_become_owner_docs_without_home():
    urls = cb.classify_urls("Посмотри мой соседний проект /Users/someone/dev/telegram_stat как референс")
    assert urls and urls[0]["path"] == "~/dev/telegram_stat" and urls[0]["kind"] == "repo"
    assert cb.mask("ключ sk-" + "a" * 30 + " в /home/user/x") == "ключ [скрыто] в ~/x"


# ---------- FB-055, SM 3.1: предзаполнение опроса ----------
def test_prefill_reference_request_has_quotes():
    pre = cb.prefill_from_text(AR_REQUEST)
    with_quote = {k: v for k, v in pre.items() if v.get("quote")}
    assert len(with_quote) >= 8, pre                                               # FB-055: ≥ 8 ответов с цитатой
    assert pre["c16"]["answer"].startswith("Веб-приложение") and pre["c07"]["answer"] == "RU + EN"
    assert pre["pl01"]["answer"] == "ARC Raiders" and pre["c22"]["answer"].startswith("metaforge.app")
    assert "c21" not in pre and "ai02" not in pre                                 # claude.ai в ссылке — не сигнал ИИ


def test_prefill_sm_dictation():
    pre = cb.prefill_from_text(SM_PITCH)
    assert pre["c21"]["answer"] == "ИИ — ядро продукта" and pre["ai02"]["answer"].startswith("Локально")
    assert pre["c38"]["answer"] == ["Деньги и платежи"] and pre["c07"]["answer"].startswith("Русскоязычный")
    assert pre["ui02"]["answer"] == "5" and "3D-визуализация" in pre["ui06"]["answer"]
    assert pre["ui03"]["answer"].startswith("Веб сейчас, мобильное позже")
    assert sum(1 for v in pre.values() if v["confidence"] >= cb.CONFIDENT) >= 7


def test_prefill_shortens_interview_and_keeps_15_live():
    d = intake.concept_questions_json(40, request=AR_REQUEST)
    assert d["confirm"] and d["confirm"][0]["header"] == "Из запроса" and "Верно?" in d["confirm"][0]["question"]
    assert set(d["prefilled_ids"]) >= {"c16", "c07", "c22"}
    live = sum(len(b["questions"]) for b in d["batches"])
    assert live == 40 - len(set(d["prefilled_ids"]))                              # освободившиеся места — блоки (платформа…)
    assert d["blocks_in_batches"] and all(x.startswith(("pl", "da")) for x in d["blocks_in_batches"])
    llm = {q[0]: {"answer": q[6][0][0], "confidence": 0.95, "quote": "из запроса"}
           for q in sorted(intake.CONCEPT_BANK, key=lambda q: q[2])[:8]}
    d = intake.concept_questions_json(40, prefill=llm)
    assert len(d["batches"]) <= 8 and sum(len(b["questions"]) for b in d["batches"]) == 32   # FB-055: 40 вопросов — ≤ 8 карточек
    llm15 = {q[0]: {"answer": q[6][0][0], "confidence": 0.9} for q in sorted(intake.CONCEPT_BANK, key=lambda q: q[2])[:15]}
    d = intake.concept_questions_json(40, prefill=llm15)
    assert sum(len(b["questions"]) for b in d["batches"]) == 25 and len(d["prefilled_ids"]) == 15   # SM 12.1: 15 из 40 сняты
    big = {q[0]: {"answer": q[6][0][0], "confidence": 0.9} for q in intake.CONCEPT_BANK[:30]}
    d = intake.concept_questions_json(25, prefill=big)
    assert sum(len(b["questions"]) for b in d["batches"]) >= 15 and d["all_themes_covered"]   # минимум 15 «живых»
    d = intake.concept_questions_json(25)
    assert set(d) == {"count", "total_bank", "min", "coverage", "all_themes_covered", "batches"}   # без новых параметров — как 1.4


def test_prefill_applied_on_confirm_and_corrections(tmp_path):
    pre = json.dumps({"c06": {"answer": "Частные лица (B2C) (Recommended)", "confidence": 0.9, "quote": "игроки"},
                      "Модель": {"answer": "Freemium + подписка (Recommended)", "confidence": "high", "quote": "платный"},
                      "c31": "Нулевой (Recommended)"}, ensure_ascii=False)
    _r, _out, cfg = apply(tmp_path, {"Из запроса": "Да, верно (Recommended)"}, "--prefill", pre, env=env_home(tmp_path))
    a = cfg["idea"]["answers"]
    assert a["c06"]["prefilled"] and a["c06"]["confirmed"] and a["c26"]["prefilled"] and "c06" not in cfg["idea"]["unanswered"]
    assert cfg["strategy"]["monetization"] == "freemium"
    _r, _out, cfg = apply(tmp_path / "b", {"Из запроса": "Модель: разовая покупка"}, "--prefill", pre, env=env_home(tmp_path))
    assert cfg["strategy"]["monetization"] == "one_time" and cfg["idea"]["answers"]["c26"]["correction"]
    _r, _out, cfg = apply(tmp_path / "c", {}, "--prefill", pre, env=env_home(tmp_path))       # без подтверждения — допущение
    assert cfg["idea"]["answers"]["c06"]["confirmed"] is False
    assert any("не подтверждено владельцем" in x for x in cfg["assumptions"])
