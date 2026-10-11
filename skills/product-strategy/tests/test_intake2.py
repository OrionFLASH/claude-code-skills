# -*- coding: utf-8 -*-
"""Опрос 1.4 (E-INTAKE): раунд 0 «Заказчик и продукт», валидация --from-askuser, follow_up и update, бюджеты числами,
ёмкость, disclosure и disclosure-check, рынки по адресу и названию, сводка (форматы, «Спрос», прогноз), questions --json.
pytest tests/test_intake2.py"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import intake  # noqa: E402

PY = [sys.executable, "-B"]


def run(*args, **kw):
    return subprocess.run(PY + [str(SCRIPTS / args[0])] + [str(x) for x in args[1:]], capture_output=True, text=True, timeout=300, **kw)


def cfg_of(out):
    return json.loads((Path(out) / "build" / "run-config.json").read_text(encoding="utf-8"))


def apply(tmp_path, answers, *extra, out=None):
    out = out or tmp_path / "run"
    r = run("intake.py", "apply", "--repo", tmp_path, "--from-askuser", json.dumps(answers, ensure_ascii=False), "--out-dir", out, *extra)
    return r, out


# ---------- раунд 0 и questions --json ----------
def test_context_round_fits_ask_user_question_and_headers_unique():
    r0 = intake.questions_json(0)
    assert len(r0) == 1 and r0[0]["round"] == 0 and [q["header"] for q in r0[0]["questions"]] == ["Роль", "Чей продукт", "Ёмкость", "Раскрытие"]
    headers = []
    for r in intake.questions_json(context=True):
        for q in r["questions"]:
            assert len(q["header"]) <= 12 and 2 <= len(q["options"]) <= 4
            assert q["question"].endswith("?") or "(можно несколько)" in q["question"]
            assert all(1 <= len(o["label"].split()) <= 7 for o in q["options"])
            assert q["multiSelect"] or "(Recommended)" in q["options"][0]["label"]
            headers.append(q["header"])
    headers += [h for _p, h, _q, _o in intake.OPEN_CARDS]
    assert len(headers) == len(set(headers))
    assert len(intake.questions_json()) == 6                       # по умолчанию — раунды 1–6, как раньше


def test_questions_json_flag_accepted_and_round0_first():
    r = run("intake.py", "questions", "--json")
    assert r.returncode == 0, r.stderr
    rounds = json.loads(r.stdout)
    assert [x["round"] for x in rounds] == [0, 1, 2, 3, 4, 5, 6]
    r = run("intake.py", "questions", "--round", "0", "--json")
    assert r.returncode == 0 and json.loads(r.stdout)[0]["title"] == "Заказчик и продукт"


# ---------- --from-askuser: обёртка, неизвестные ключи, «Папка = рядом» ----------
def test_answers_wrapper_unwrapped_and_folder_outside_gives_out_dir(tmp_path):
    repo = tmp_path / "proj"
    repo.mkdir()
    ans = {"answers": {"Где сохранить результат?": "ВНЕ репозитория (рядом)", "Глубина": "Быстро"}, "questions": []}
    r = run("intake.py", "apply", "--repo", repo, "--from-askuser", json.dumps(ans, ensure_ascii=False))
    assert r.returncode == 0, r.stderr
    out = Path([l for l in r.stdout.splitlines() if l.startswith("OUT=")][0][4:])
    assert out.parent == tmp_path / "proj-strategy"                  # «рядом» сам даёт папку вне репозитория
    cfg = cfg_of(out)
    assert cfg["output"]["inside_repo"] is False and cfg["strategy"]["depth"] == "quick"
    assert not any("{" in a for a in cfg["assumptions"])            # сырые словари в допущения не попадают
    assert not (repo / "strategy").exists()


def test_apply_from_askuser_function_unwraps():
    cfg = intake.base_config(".")
    intake.apply_from_askuser(cfg, {"answers": {"Бюджет": "Нулевой"}})
    assert cfg["strategy"]["budget"]["variants"] == ["zero"] and not any("answers" in a for a in cfg["assumptions"])


def test_unknown_key_is_error_with_hint_and_lenient_warns(tmp_path):
    r, out = apply(tmp_path, {"Рол": "Партнёр", "Бюджет": "Нулевой"})
    assert r.returncode == 2 and "неизвестный ключ «Рол»" in r.stderr and "«Роль»" in r.stderr and "допустимые заголовки" in r.stderr
    assert not (out / "build" / "run-config.json").exists()
    r, out = apply(tmp_path, {"Бюджет": {"label": "Нулевой"}})
    assert r.returncode == 2 and "не объект" in r.stderr
    r, out = apply(tmp_path, {"Рол": "Партнёр"}, "--lenient")
    assert r.returncode == 0 and "пропущен неизвестный ключ" in r.stdout


def test_list_shaped_answers_accepted():
    flat = intake.unwrap_answers([{"question": "Кто вы относительно продукта?", "answer": "Инвестор"}])
    assert flat == {"Кто вы относительно продукта?": "Инвестор"}
    with pytest.raises(intake.AnswerError):
        intake.unwrap_answers("строка")


# ---------- «Уточню сам» → follow_up → update ----------
def test_text_choice_without_text_creates_follow_up_and_update_closes_it(tmp_path):
    r, out = apply(tmp_path, {"Продукт": "Уточню сам", "Адрес": "Укажу сам"}, "--json")
    assert r.returncode == 0, r.stderr
    d = json.loads(r.stdout)
    paths = {x["path"]: x for x in d["follow_up"]}
    assert {"product.name", "product.url"} <= set(paths) and paths["product.name"]["question"].endswith("?")
    assert "Уточнить ДО «Начинаю?»" in d["summary"]
    cfg = cfg_of(out)
    assert not any("собирался уточнить" in a for a in cfg["assumptions"])
    q = paths["product.name"]["question"]
    r = run("intake.py", "update", out, "--from-askuser", json.dumps({q: "Счётчик — учёт расходов"}, ensure_ascii=False),
            "--set", "product.url=https://schetchik.ru https://www.rustore.ru/catalog/app/ru.schet.app", "--json")
    assert r.returncode == 0, r.stderr
    d = json.loads(r.stdout)
    assert d["follow_up"] == []
    cfg = cfg_of(out)
    assert cfg["product"]["name"] == "Счётчик — учёт расходов" and cfg["product"]["url"] == "https://schetchik.ru"
    assert cfg["sources"]["stores"] == [{"store": "rustore", "id": "ru.schet.app", "url": "https://www.rustore.ru/catalog/app/ru.schet.app"}]
    assert set(cfg["follow_up_done"]) >= {"product.name", "product.url"}


# ---------- бюджет, ёмкость, роль, раскрытие ----------
def test_budget_amounts_default_by_currency_and_custom_amount(tmp_path):
    r, out = apply(tmp_path, {"Бюджет": "Три варианта (Recommended)", "Валюта": "RUB"})
    b = cfg_of(out)["strategy"]["budget"]
    assert r.returncode == 0 and (b["small"], b["medium"], b["period"]) == (50000, 300000, "month")
    assert "small (≤ 50 000 RUB/мес)" in r.stdout
    r, out = apply(tmp_path, {"Бюджет": "до 30 тыс ₽ в месяц", "Валюта": "RUB"}, out=tmp_path / "r2")
    b = cfg_of(out)["strategy"]["budget"]
    assert b["small"] == 30000 and b["note"] == "до 30 тыс ₽ в месяц" and b["medium"] == 300000
    r, out = apply(tmp_path, {"Бюджет": "Малый", "Валюта": "USD"}, out=tmp_path / "r3")
    assert cfg_of(out)["strategy"]["budget"]["small"] == 500
    assert intake.parse_money("1,5 млн руб") == (1500000, "RUB") and intake.parse_money("$300")[0] == 300


@pytest.mark.parametrize("team,cap,expected", [("Один разработчик (Recommended)", "Определи по команде (Recommended)", 12),
                                               ("2–5 человек", "Полный месяц на человека", 60),
                                               ("2–5 человек", "5–15 дней", 10), ("Один разработчик (Recommended)", "18 дней", 18),
                                               ("Один разработчик (Recommended)", "20 часов в неделю", 11)])
def test_capacity_days(tmp_path, team, cap, expected):
    r, out = apply(tmp_path, {"Команда": team, "Ёмкость": cap})
    assert r.returncode == 0, r.stderr
    assert cfg_of(out)["project"]["capacity_days_month"] == expected


def test_role_owner_and_analyst(tmp_path):
    r, out = apply(tmp_path, {"Роль": "Владелец или команда (Recommended)"})
    cfg = cfg_of(out)
    assert cfg["project"]["requester_role"] == "owner" and cfg["project"]["product_owner"] and not cfg["follow_up"]
    r, out = apply(tmp_path, {"Роль": "Сторонний аналитик"}, out=tmp_path / "r2")
    cfg = cfg_of(out)
    assert cfg["project"]["requester_role"] == "analyst" and [x["path"] for x in cfg["follow_up"]] == ["project.product_owner"]
    assert "Заказчик: сторонний аналитик" in r.stdout
    r, out = apply(tmp_path, {"Роль": "QA-подрядчик заказчика"}, out=tmp_path / "r3")
    assert cfg_of(out)["project"]["requester_role"] == "analyst"


def test_disclosure_values_and_check(tmp_path):
    r, out = apply(tmp_path, {"Раскрытие": "Нет, без упоминаний"})
    assert r.returncode == 0 and cfg_of(out)["disclosure"] == "none" and "disclosure=none" in r.stdout
    (out / "deliverables").mkdir(parents=True)
    (out / "deliverables" / "REPORT.md").write_text("# Отчёт\n\nДизайн-токены (12 токенов) сняты с сайта.\n", encoding="utf-8")
    r = run("intake.py", "disclosure-check", out)
    assert r.returncode == 0, r.stdout                                # «дизайн-токены» — не про автоматизацию
    (out / "deliverables" / "index.html").write_text("<p>Разделы писали субагенты Claude, 11 млн токенов.</p>", encoding="utf-8")
    r = run("intake.py", "disclosure-check", out, "--json")
    found = json.loads(r.stdout)["found"]
    assert r.returncode == 1 and {"Claude", "субагенты"} <= {x["term"] for x in found} and any("токенов" in x["term"] for x in found)
    cfg = cfg_of(out)
    cfg["disclosure"] = "summary"
    (out / "build" / "run-config.json").write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    terms = {x["term"] for x in json.loads(run("intake.py", "disclosure-check", out, "--json").stdout)["found"]}
    assert "Claude" in terms and "субагенты" not in terms              # summary: модели и токены нельзя, общее упоминание можно
    cfg["disclosure"] = "full"
    (out / "build" / "run-config.json").write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    assert run("intake.py", "disclosure-check", out).returncode == 0


def test_custom_disclosure_text():
    cfg = intake.base_config(".")
    intake.apply_answers(cfg, {"Раскрытие": "нельзя упоминать автоматизацию в трекерах"})
    assert cfg["disclosure"] == "none"


# ---------- рынки по адресу, названию и магазинам ----------
def test_markets_conflict_asks_and_update_applies_choice(tmp_path):
    (tmp_path / "README.md").write_text("# MyApp\n\nA simple tool to track expenses, written in Python with a small web UI for everyday use.\n",
                                        encoding="utf-8")
    r, out = apply(tmp_path, {"Адрес": "https://moyapp.ru/"}, "--json")
    d = json.loads(r.stdout)
    fu = [x for x in d["follow_up"] if x["path"] == "strategy.markets"]
    assert fu and fu[0]["kind"] == "choice" and fu[0]["card"]["options"][0]["label"].startswith("Только RU")
    cfg = cfg_of(out)
    assert cfg["strategy"]["markets"][0] == "ru" and cfg["project"]["currency"] == "RUB"
    r = run("intake.py", "update", out, "--from-askuser", json.dumps({fu[0]["question"]: "Только EN"}, ensure_ascii=False))
    assert r.returncode == 0, r.stderr
    cfg = cfg_of(out)
    assert cfg["strategy"]["markets"] == ["en"] and cfg["project"]["currency"] == "USD" and cfg["strategy"]["budget"]["small"] == 500
    assert not cfg["follow_up"]


def test_markets_from_store_and_cyrillic_name_without_readme(tmp_path):
    cfg = intake.base_config(tmp_path)
    cfg["product"]["name"] = "Слышно"
    cfg["product"]["url"] = "https://play.google.com/store/apps/details?id=x.y&hl=ru"
    intake.finalize(cfg)
    assert cfg["strategy"]["markets"][0] == "ru" and cfg["sources"]["stores"][0]["store"] == "gplay"
    assert intake._url_lang("https://apps.apple.com/de/app/x/id1") == "de" and intake._url_lang("https://example.com/") is None


# ---------- сводка: форматы, «Спрос», прогноз ----------
def test_summary_confirms_single_format_and_warns_demand_off(tmp_path):
    r, out = apply(tmp_path, {"Форматы": ["Веб-страница (Recommended)"], "Исследования": ["Конкуренты (Recommended)"]})
    assert "получится только веб-страница, верно?" in r.stdout
    assert "keywords-volume" in r.stdout and "events-calendar" in r.stdout and "раздел «Спрос»" in r.stdout
    r, out = apply(tmp_path, {"Форматы": ["Веб-страница (Recommended)", "XLSX"]}, out=tmp_path / "r2")
    assert "верно?" not in r.stdout and "keywords-volume" not in r.stdout


def test_forecast_by_depth_and_parallelism(tmp_path):
    cfg = intake.finalize(intake.base_config(tmp_path))
    std = cfg["forecast"]
    assert std["label"] == "оценка" and std["agents"] == [18, 32] and std["parallel"] == 5 and "допущение" in std["basis"]
    cfg = intake.base_config(tmp_path)
    cfg["strategy"]["depth"] = "deep"
    cfg["_explicit"] = []
    deep = intake.finalize(cfg)["forecast"]
    assert deep["agents"] == [27, 50] and deep["tokens_m"] == [6.0, 11.0]
    cfg = intake.base_config(tmp_path)
    cfg["tools"]["subagents"] = False
    solo = intake.finalize(cfg)["forecast"]
    assert solo["agents"] == [0, 0] and solo["hours"][0] > std["hours"][0]
    cfg = intake.base_config(tmp_path)
    cfg["tools"]["max_parallel_agents"] = 3
    assert intake.finalize(cfg)["forecast"]["hours"][1] > std["hours"][1]
    r, out = apply(tmp_path, {"Глубина": "Глубоко"})
    assert "Прогноз (оценка ±50 %): агентов ≈ 27–50" in r.stdout and cfg_of(out)["forecast"]["depth"] == "deep"


def test_show_handles_old_run_config_without_new_keys(tmp_path):
    cfg = intake.finalize(intake.base_config(tmp_path))
    for k in ("disclosure", "follow_up", "forecast"):
        cfg.pop(k, None)
    for k in ("requester_role", "product_owner", "capacity_days_month"):
        cfg["project"].pop(k, None)
    cfg["product"].pop("mode", None)
    text = intake.show(cfg)
    assert "Заказчик: владелец" in text and "disclosure=full" in text
