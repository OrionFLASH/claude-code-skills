#!/usr/bin/env python3
"""Демо-прогон режима «Идея → концепция» (mode: concept): заполняет <OUT> правдоподобными данными по контракту.

Нужен для тестов и самопроверки конвейера в режиме идеи (досье → предпроверка → реестр → оценки → страница) без
настоящей идеи. Идея вымышлена («демо»), все цифры выдуманы и помечены «демо»; ссылки — на example.com.
После него `build_all.py <OUT> --strict` проходит (шаги, которым нужны Node-модули, — SKIP, если их нет).

  make_concept_demo.py <OUT> [--proposals 60] [--seed 7]

Пишет: build/run-config.json (mode: concept, блок idea — через intake.py), досье (concept_dossier.py: research/idea-dossier.md,
data/idea.json, research/product-understanding.md, build/search-plan.md, build/seeds.md), data/typesafe-concept.json
(эвристика, Jev не вызывался), реестр с метками mvp/v1/later, competitors.json с kind и планируемой идеей (self, planned),
swot.json, personas.json, сообщества, запросы, события, источники, Гант, Kanban, схему, макеты-заглушки с бейджем
«Концепт продукта, не существующая функция», референс, research/strategy.md по references/concept-outline.md.
Только стандартная библиотека.
"""
import argparse
import random
from datetime import date
from pathlib import Path

import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import concept_dossier  # noqa: E402
import intake  # noqa: E402
import make_demo  # noqa: E402
import typesafe_concept  # noqa: E402

IDEA = "Демо: приложение для обмена книгами между соседями по дому. Взял почитать — вернул, без денег и курьеров."
ANSWERS = {   # ответы карточек как вернул бы AskUserQuestion (header → label или свой текст)
    "Вопросов": "25 (Recommended)", "Глубина": "Стандарт (Recommended)",
    "Форматы": ["Веб-страница (Recommended)", "XLSX", "PPTX", "PDF"], "Папка": "Текущая папка: concept/ (Recommended)",
    "Боль": "Заметная, но терпимая (Recommended)", "Сейчас": "Вручную, подручными средствами (Recommended)",
    "Аудитория": "Частные лица (B2C) (Recommended)", "Рынки": "Русскоязычный рынок (Recommended)", "Сегмент": "Сообщество, где я свой",
    "Ценность": "Радость и общение", "Отличие": "Под узкую нишу", "Ага-момент": "В первые 5 минут (Recommended)",
    "Форма": "Веб-приложение (Recommended)", "MVP": "Ручной сервис за интерфейсом", "Срок MVP": "Через 1–2 месяца (Recommended)",
    "Аналоги": "Демо-аналог А, Демо-аналог Б", "Образцы": "Подбери по идее (Recommended)", "Рынок": "Оценить в исследовании (Recommended)",
    "Модель": "Бесплатно: донаты, гранты", "Цена": "Определи по аналогам (Recommended)", "Кто платит": "Пока никто",
    "Команда": "Я один (Recommended)", "Бюджет": "Нулевой (Recommended)", "Время": "5–10 часов (Recommended)",
    "Стиль": "Тёплый и дружелюбный", "Название": "Книжная полка",
    "Область": ["Нет, обычные данные (Recommended)"], "Успех": "100 активных пользователей (Recommended)",
    # «Риск» (c40) намеренно без ответа — проверка допущений
}
FEATURES = {"catalog": "Каталог книг дома", "requests": "Запрос «дай почитать»", "chat": "Чат соседей", "map": "Карта полок",
            "rating": "Отзывы и доверие", "reminders": "Напоминания о возврате"}
MVP_FEATURES = {"catalog", "requests", "reminders"}


def concept_config(out, proposals_min):
    cfg = intake.concept_base_config(out, IDEA, out)
    cfg.setdefault("_explicit", []).append("output.dir")
    notes = intake.apply_concept_answers(cfg, ANSWERS)
    intake._apply_sets(cfg, ["strategy.proposals_min=%d" % proposals_min, "tools.browser=none",
                             "tools.subagents=false", "tools.max_parallel_agents=1", "product.url=https://example.com"])
    notes += intake.concept_finish(cfg, out, "")
    cfg["author"] = {"name": "Демо Автор", "nick": "demo", "copyright": "© %s Демо" % cfg["created"][:4]}
    cfg["autopilot"] = True
    cfg["tools"]["typesafe"] = "off"          # строкой: --set превратил бы «off» в false
    cfg["assumptions"].insert(0, "Демо-данные, все цифры вымышлены")
    return cfg


def concept_proposals(n, rnd):
    props = make_demo.proposals(n, rnd)
    tag = {"now": "mvp", "next": "v1", "later": "later", "vision": "later"}
    for i, p in enumerate(props, 1):
        p["current_feature"] = "нет (продукта ещё нет)"
        p["tags"] = [tag[p["horizon"]]]
        for e in p["evidence"]:
            e["kind"] = rnd.choice(["competitor", "community", "docs", "research"])
        for s in p["steps"]:
            s["where"] = rnd.choice(["прототип", "лендинг", "MVP", "сообщество"])
        p["description"] = p["description"].replace("Демо:", "Демо (концепция):", 1)
    return props


def competitors(rnd, name):
    kinds = ["direct", "direct", "direct", "direct", "indirect", "indirect", "substitute", "substitute", "analog", "inspiration", "anti"]
    self_ = {"slug": "self", "name": name, "url": None, "self": True, "planned": True, "kind": "self", "type": "direct",
             "features": {k: k in MVP_FEATURES or k == "rating" for k in FEATURES}, "features_labels": dict(FEATURES),
             "price": "бесплатно [допущение]", "monetization": "донаты [допущение]",
             "verdict": "Планируемая идея", "verdict_long": "Планируемая идея: каталог полок дома, запросы и напоминания о возврате в MVP"}
    out = [self_]
    for i, kind in enumerate(kinds, 1):
        out.append({
            "slug": "demo-%s-%d" % (kind, i), "name": "Демо-%s %d" % ({"direct": "конкурент", "indirect": "косвенный", "substitute": "заменитель",
                                                                       "analog": "аналог", "inspiration": "образец", "anti": "анти-пример"}[kind], i),
            "url": "https://example.com/%s-%d" % (kind, i), "type": "indirect" if kind in ("analog", "inspiration", "anti") else kind, "kind": kind,
            "sphere": "аренда вещей" if kind == "analog" else ("" if kind != "inspiration" else "соседские сообщества"),
            "segment": "соседи", "audience": "жители многоквартирных домов", "price": "$%d/мес" % rnd.choice([0, 0, 3, 5]),
            "monetization": rnd.choice(["бесплатно", "подписка", "реклама"]), "languages": "ru", "freshness": "демо",
            "traffic": None, "features": {k: rnd.random() < 0.5 for k in FEATURES}, "features_labels": dict(FEATURES),
            "better_than_us": ["узнаваемость"], "we_better": ["фокус на одном доме [оценка]"], "best_solutions": ["простой каталог"],
            "design_note": "светлая тема, крупные обложки", "complaints": ["пусто в моём районе"], "adopt": ["напоминания"],
            "avoid": ["обязательная регистрация до просмотра"], "verdict": "демо: сильнее по охвату",
            "verdict_long": "Демо: сильнее по охвату, слабее по доверию между соседями; перенять напоминания, не повторять регистрацию до просмотра",
            "lessons": ["демо-урок: начинать с одного дома"], "why_it_worked_or_failed": "Демо: механизм вымышлен [допущение]",
            "shot": None, "shot_blocked": False, "sources": ["https://example.com/%s-%d" % (kind, i)]})
    return out


def swot():
    item = lambda t: {"text": t, "basis": "демо-обоснование", "label": "допущение", "source": "data/idea.json"}
    return {"strengths": [item("демо: владелец свой в сообществе"), item("демо: нулевые расходы"), item("демо: простая механика"), item("демо: быстрый MVP")],
            "weaknesses": [item("демо: нет денег на продвижение"), item("демо: один разработчик"), item("демо: модель без дохода"), item("демо: холодный старт")],
            "opportunities": [item("демо: соседские чаты"), item("демо: интерес к осознанному потреблению"), item("демо: библиотеки ищут партнёров"),
                              item("демо: школы и детские книги")],
            "threats": [item("демо: крупные площадки объявлений"), item("демо: низкая частота"), item("демо: потеря книг и недоверие"),
                        item("демо: правила мессенджеров")]}


def personas():
    return [{"id": "PS%d" % i, "segment": seg, "who": "демо-персона %d" % i, "context": "демо", "jobs": {"main": "демо", "emotional": "демо", "social": "демо"},
             "pains": ["демо"], "gains": ["демо"], "alternatives": ["чат дома"], "channels": ["чат дома"], "objections": ["демо"],
             "willingness_to_pay": "низкая [допущение]", "size": "демо", "priority": pr,
             "hypotheses": [{"text": "демо-гипотеза", "check": "интервью 5 соседей", "label": "допущение"}], "label": "допущение", "sources": []}
            for i, (seg, pr) in enumerate([("родители", "primary"), ("студенты", "secondary"), ("пенсионеры", "later")], 1)]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("out")
    ap.add_argument("--proposals", type=int, default=60)
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args(argv)
    rnd = random.Random(a.seed)
    out = Path(a.out).resolve()
    w = lambda rel, obj: make_demo.write(out, rel, obj)
    cfg = concept_config(out, max(50, a.proposals))
    w("build/run-config.json", cfg)
    concept_dossier.run(out)
    ts = typesafe_concept.doc_for(typesafe_concept.heuristic(cfg), "heuristic", cfg, skipped="демо: TypeSafe не вызывался")
    w("data/typesafe-concept.json", ts)
    name = cfg["product"]["name"]
    props = concept_proposals(a.proposals, rnd)
    nm = cfg["scope"]["mockups_min"]
    for k, p in enumerate(props[:nm]):
        p["mockup"] = "concepts/M%02d-demo.html" % (k + 1)
    w("data/proposals.json", props)
    w("data/competitors.json", competitors(rnd, name))
    w("data/swot.json", swot())
    w("data/personas.json", personas())
    today = date.today().isoformat()
    w("data/communities.json", [{"name": "Демо-сообщество %d" % i, "url": "https://example.com/community/%d" % i, "platform": "чат дома",
                                 "language": "ru", "audience_size": None, "self_promo_rules": "демо: только с разрешения админа",
                                 "allowed_formats": ["вопрос"], "ban_risk": rnd.randint(1, 5), "source": "https://example.com/rules"} for i in range(1, 6)])
    w("data/keywords.json", [{"query": "демо обмен книгами %d" % i, "lang": "ru", "cluster": "кластер %d" % (i % 3), "intent": "info",
                              "volume": rnd.choice([None, 90, 320]), "volume_source": "демо", "competition": rnd.randint(1, 5)} for i in range(1, 13)])
    w("data/events.json", [{"date": "%s-%02d-20" % (today[:4], m), "date_end": None, "title": "Демо-событие %d" % m, "kind": "книжная ярмарка",
                            "relevance": "средняя", "source": "https://example.com/events", "verified": True} for m in (4, 9)])
    w("data/sources.json", [{"id": "S%03d" % i, "url": "https://example.com/evidence/%d" % i, "title": "Демо-источник %d" % i,
                             "date_checked": today, "used_for": "P%03d" % i, "status": None, "note": "демо"} for i in range(1, 16)])
    w("data/gantt.json", [
        {"id": "G%02d" % i, "phase": ph, "task": "Демо-задача концепции %d" % i, "proposal_ids": ["P%03d" % i], "start_month": s, "end_month": e,
         "type": "milestone" if s == e else "task", "owner": "владелец", "done_criteria": "демо-критерий", "dependencies": []}
        for i, (ph, s, e) in enumerate([("30 дней", 1, 1), ("MVP", 1, 2), ("MVP", 2, 2), ("6 месяцев", 3, 6), ("6 месяцев", 4, 6),
                                        ("vision", 13, 24)], 1)])
    cols = ["Идеи", "Проверка", "Готово к разработке", "В работе", "Запуск", "Измерение", "Закрыто"]
    w("data/kanban.json", {"columns": [{"name": c, "wip": wip} for c, wip in zip(cols, [None, 5, 8, 4, 3, 6, None])],
                           "cards": [{"id": p["id"], "title": p["title"], "column": cols[k % 3], "goal": "демо-цель", "steps": ["шаг 1"],
                                      "kpi": "активные соседи", "links": [], "tags": p["tags"], "priority": "P1", "effort_days": p["effort_days"]}
                                     for k, p in enumerate(props[:20])]})
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 120"><rect data-node="first-use:1" x="10" y="30" width="180" height="60" rx="8" fill="#eef"/>'
           '<text x="100" y="65" text-anchor="middle">Узнал от соседа</text><rect data-node="first-use:2" x="230" y="30" width="180" height="60" rx="8" fill="#efe"/>'
           '<text x="320" y="65" text-anchor="middle">Нашёл книгу</text><rect data-node="first-use:3" x="450" y="30" width="180" height="60" rx="8" fill="#fee"/>'
           '<text x="540" y="65" text-anchor="middle">Вернул</text></svg>')
    w("charts/flows/first-use.svg", svg)
    w("data/flows.json", [{"key": "first-use", "title": "Первый опыт (концепт)", "svg": "charts/flows/first-use.svg",
                           "nodes": [{"id": "first-use:%d" % k, "label": lab, "what": "демо", "now": "продукта ещё нет", "todo": ["демо"],
                                      "proposals": ["P%03d" % k], "metrics": "демо"} for k, lab in enumerate(["Узнал от соседа", "Нашёл книгу", "Вернул"], 1)]}])
    w("data/mockups-index.json", [{"key": "M%02d-demo" % k, "html": "mockups/concepts/M%02d-demo.html" % k, "png": "mockups/concepts/M%02d-demo.png" % k,
                                   "title": "Демо-экран концепции %d" % k, "proposals": [props[k - 1]["id"]], "viewport": "1440x900", "kind": "concept"}
                                  for k in range(1, nm + 1)])
    for k in range(1, nm + 1):
        w("mockups/concepts/M%02d-demo.html" % k,
          '<!doctype html><meta charset="utf-8"><title>Демо-экран %d</title><body style="font:16px system-ui;margin:0">'
          '<div class="badge-concept" style="position:fixed;top:8px;right:8px;background:#b42318;color:#fff;padding:4px 8px">Концепт продукта, не существующая функция</div>'
          '<h1 style="padding:40px">Демо-экран концепции %d</h1></body>' % (k, k))
    w("design-refs/01-demo.json", {"file": "mockups/concepts/M01-demo.html", "png": "design-refs/01-demo.png", "scale": 1, "width": 1440, "height": 900,
                                   "title": "Демо-референс концепции", "proposals": [props[0]["id"]], "kind": "page", "summary": "демо", "entry": "демо",
                                   "shared": [], "new_elements": ["каталог"], "hotspots": [{"n": 1, "x": 40, "y": 30, "w": 400, "h": 60, "title": "Заголовок",
                                                                                           "text": "демо", "proposal": props[0]["id"], "state": "new"}],
                                   "todo": ["демо"], "questions": []})
    w("design-refs/01-demo.md", "# Демо-референс концепции\n\n## Что это\nдемо\n\n## Как выглядит\nдемо\n\n## Как взаимодействовать\nдемо\n\n"
                                "## Что нужно доделать\nдемо\n\n## Элементы\nдемо\n\n## Открытые вопросы\nнет\n")
    top = [p["id"] for p in props[:3]]
    w("research/strategy.md", "\n\n".join([
        "# Концепция продукта %s (демо)" % name,
        "## 1. Резюме\nВердикт демо-предпроверки: %s. Три гипотезы: %s, %s, %s. [допущение]" % ((ts["verdict"],) + tuple(top)),
        "## 2. Идея, проблема и аудитория\nДемо-текст по досье идеи со ссылкой на %s.\n\n![[chart:effort-impact]]" % props[3]["id"],
        "## 3. Рынок, конкуренты и аналоги\nДемо-текст: прямые, косвенные, заменители, аналоги, образцы, анти-примеры.\n\n![[mockup:M01-demo]]",
        "## 10. Дорожная карта: MVP → v1 → v2\nДемо: сначала %s, затем %s.\n\n![[ref:01-demo]]" % (props[4]["id"], props[5]["id"]),
        "## 14. План: от идеи до запуска MVP и дальше\n| Срок | Что |\n|---|---|\n| 30 дней | %s |\n| MVP | %s |" % (props[6]["id"], props[7]["id"]),
    ]) + "\n")
    w("research/questions-owner.md", "# Вопросы владельцу\n\n1. Демо-вопрос: в каком доме запускаем пилот?\n2. Демо-вопрос: кто модерирует чат?\n")
    w("build/STATUS.md", "# Статус\n\nДемо-прогон концепции, сгенерирован make_concept_demo.py %s.\n" % today)
    print("Демо-концепция: %s (предложений %d, светофор %s)" % (out, len(props), ts["verdict"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
