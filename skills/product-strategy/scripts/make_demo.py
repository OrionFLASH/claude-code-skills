#!/usr/bin/env python3
"""Демо-прогон product-strategy: заполняет <OUT> правдоподобными данными по references/data-contract.md.

Нужен для тестов и самопроверки конвейера (score → charts → build_html/xlsx/pptx) без реального продукта.
Все данные вымышлены и помечены «демо»; ссылки — на example.com.

  make_demo.py <OUT> [--proposals 60] [--seed 7]

Только стандартная библиотека.
"""
import argparse
import json
import random
from datetime import date
from pathlib import Path

CATEGORIES = [("product", 0.30), ("acquisition", 0.20), ("conversion", 0.09), ("retention", 0.09), ("monetization", 0.09),
              ("analytics", 0.06), ("partnerships", 0.06), ("localization", 0.05), ("new_lines", 0.03), ("platform", 0.03)]
VERBS = ["Добавить", "Запустить", "Переработать", "Упростить", "Автоматизировать", "Встроить", "Открыть", "Измерять"]
OBJECTS = {
    "product": ["шаблоны проектов", "совместное редактирование", "экспорт в PDF", "режим офлайн", "историю изменений", "глобальный поиск"],
    "acquisition": ["страницы сравнения с альтернативами", "серию коротких видео", "каталог интеграций", "страницы-ответы под запросы", "awesome-списки"],
    "conversion": ["пример на готовых данных до регистрации", "мастер первого запуска", "чек-лист активации", "пустые состояния с действием"],
    "retention": ["еженедельный дайджест", "итоги месяца", "ленту «что нового»", "напоминания по поведению"],
    "monetization": ["тариф для команд", "годовую оплату со скидкой", "пробный период за приглашение", "предпросмотр платных функций"],
    "analytics": ["схему событий воронки", "дашборд активации", "когортный отчёт удержания"],
    "partnerships": ["партнёрскую программу", "интеграцию с популярным мессенджером", "программу амбассадоров"],
    "localization": ["английскую локаль", "локальные посадочные для рынков", "поддержку RTL"],
    "new_lines": ["мобильное приложение-компаньон", "браузерное расширение"],
    "platform": ["публичный API", "систему плагинов"],
}


def _pick_category(rnd):
    r, acc = rnd.random(), 0.0
    for cat, w in CATEGORIES:
        acc += w
        if r <= acc:
            return cat
    return CATEGORIES[0][0]


def _quota_categories(n, rnd):
    """Категории по квотам (минимумы check_registry выполняются), остаток — по весам, порядок перемешан."""
    import math
    quota = {cat: max(1, math.ceil(n * w)) for cat, w in CATEGORIES}
    while sum(quota.values()) > n:                 # лишнее снимаем с самых крупных категорий, минимумы не трогаем
        big = max(quota, key=lambda c: quota[c] - n * dict(CATEGORIES)[c])
        quota[big] -= 1
    cats = [c for c, k in quota.items() for _ in range(k)]
    while len(cats) < n:
        cats.append(_pick_category(rnd))
    rnd.shuffle(cats)
    return cats


def proposals(n, rnd):
    out = []
    seen = {}
    cats = _quota_categories(n, rnd)
    for i in range(1, n + 1):
        cat = cats[i - 1]
        obj = rnd.choice(OBJECTS[cat])
        cls = rnd.choices("ABCD", weights=[35, 32, 22, 11])[0]
        value, cost, risk = rnd.randint(1, 5), rnd.randint(1, 5), rnd.randint(1, 4)
        lo = rnd.randint(1, 15)
        horizon = rnd.choices(["now", "next", "later", "vision"], weights=[30, 40, 20, 10])[0]
        out.append({
            "id": "P%03d" % i,
            "title": _unique_title("%s %s" % (rnd.choice(VERBS), obj), seen),
            "category": cat,
            "segment": rnd.choice(["новые пользователи", "активные пользователи", "команды", "англоязычный рынок"]),
            "description": "Демо: %s — что именно сделать, в каком объёме и для кого." % obj,
            "rationale": "Демо: снижает трение и повышает целевую метрику; есть пример у конкурентов.",
            "evidence": [{"kind": rnd.choice(["competitor", "community", "issue", "docs", "repo"]),
                          "url": "https://example.com/evidence/%d" % i, "file": None, "title": "Демо-источник %d" % i,
                          "note": "Короткая цитата до 15 слов", "checked": date.today().isoformat()}],
            "evidence_class": cls,
            "current_feature": rnd.choice(["нет", "частично: src/app/main.py:42", "есть, но скрыто в настройках"]),
            "effect_kpi": [{"kpi": rnd.choice(["активация", "D30 удержание", "конверсия в оплату", "органический трафик"]),
                            "direction": "up", "range": "+%d..%d %%" % (1, rnd.randint(3, 12)), "label": "оценка"}],
            "steps": [{"what": "Шаг %d" % k, "where": "репозиторий", "how": "описание шага", "doc_url": "https://example.com/docs/%d" % k}
                      for k in range(1, rnd.randint(2, 5))],
            "dependencies": ["P%03d" % rnd.randint(1, max(1, i - 1))] if i > 5 and rnd.random() < 0.25 else [],
            "effort_days": [lo, lo + rnd.randint(1, 20)],
            "cost_money": {"min": 0, "max": rnd.choice([0, 100, 500, 2000]), "currency": "USD", "note": "демо"},
            "risks": {"legal": rnd.randint(1, 3), "ip": 1, "platform": rnd.randint(1, 3), "privacy": rnd.randint(1, 3),
                      "tech": rnd.randint(1, 4), "reputation": 1, "note": ""},
            "time_to_first_result_days": rnd.choice([7, 14, 30, 60, 90]),
            "cheap_test": "Демо: фейковая дверь / опрос / прототип на 2 дня",
            "scores": {"value": value, "cost": cost, "risk": risk, "confidence": {"A": 5, "B": 4, "C": 3, "D": 2}[cls],
                       "reach": rnd.randint(1, 5), "impact": value},
            "kano": rnd.choice(["must", "linear", "delight", "indifferent"]),
            "horizon": horizon,
            "horizon_years": {"now": 0, "next": 0, "later": 1, "vision": 2}[horizon],
            "tags": [],
            "mockup": None,
            "source_group": "G%d" % rnd.randint(1, 6),
            "merged_from": [],
        })
    return out


def _unique_title(t, seen):
    seen[t] = seen.get(t, 0) + 1
    return t if seen[t] == 1 else "%s (вариант %d)" % (t, seen[t])


def write(out, rel, obj):
    p = out / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(obj, str):
        p.write_text(obj, encoding="utf-8")
    else:
        p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("out")
    ap.add_argument("--proposals", type=int, default=60)
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args(argv)
    rnd = random.Random(a.seed)
    out = Path(a.out).resolve()
    today = date.today().isoformat()
    props = proposals(a.proposals, rnd)
    for k, p in enumerate(props[:6]):            # у первых шести есть концепт-макет
        p["mockup"] = "concepts/M%02d-demo.html" % (k + 1)

    write(out, "build/run-config.json", {
        "version": 1, "created": today, "author": {"name": "Демо Автор", "nick": "demo", "copyright": "© %s Демо" % today[:4]},
        "repo": {"path": str(out), "name": "demo-app", "remote": None, "analyze": True},
        "product": {"name": "Demo App", "url": "https://example.com", "local_run": "none", "run_command": "", "type": "saas", "known_facts": ""},
        "strategy": {"kind": "growth", "goal": "рост активной аудитории и выручки", "depth": "standard", "proposals_min": a.proposals,
                     "horizon_months": 12, "vision_years": 3, "markets": ["ru", "en"],
                     "budget": {"variants": ["zero", "small", "medium"], "note": ""}, "paid_tier": "auto", "constraints": "",
                     "categories_na": [], "profile": "standard"},
        "project": {"goal": "commercial", "repo_visibility": "public", "publish_code": "undecided", "currency": "USD",
                    "price_hint": None, "traffic_hint": None, "team_size": 3},
        "phases": {"gap_audit": True},
        "scope": {"repo_analysis": True, "app_run": False, "competitors": True, "competitors_min": 10, "communities": True,
                  "keywords": True, "events": True, "legal": True, "issues": False, "design_mockups": True, "mockups_min": 6,
                  "design_refs": True, "unit_economics": True, "experiments": 4, "specs_top": 5, "kanban_cards": 20},
        "sources": {"repo": True, "issues": False, "web_search": False, "web_search_budget_per_hour": 0, "analytics_exports": [],
                    "owner_docs": [], "competitor_list": [], "other": ""},
        "formats": {"html": True, "xlsx": True, "pptx": True, "pdf": True, "md": True},
        "tools": {"typesafe": "off", "browser": "none", "subagents": False, "max_parallel_agents": 1},
        "output": {"dir": str(out), "inside_repo": False, "git_branch": ""}, "language": "ru", "autopilot": True,
        "assumptions": ["Демо-данные, все цифры вымышлены"]})
    write(out, "data/proposals.json", props)
    write(out, "data/competitors.json", [{"slug": "self", "name": "Demo App", "url": "https://example.com", "self": True, "type": "direct",
                                          "features": {"templates": True, "api": False, "offline": False, "teams": True},
                                          "features_labels": {"templates": "Шаблоны", "api": "Публичный API", "offline": "Офлайн", "teams": "Команды"},
                                          "verdict": "наш продукт", "verdict_long": "Наш продукт: сильные шаблоны и команды, слабее API и офлайн-режим"}] + [
        {"slug": "rival-%d" % i, "name": "Rival %d" % i, "url": "https://example.com/rival-%d" % i, "type": rnd.choice(["direct", "indirect"]),
         "segment": "SMB", "price": "$%d/мес" % rnd.choice([0, 9, 19, 49]), "monetization": "подписка", "languages": "en",
         "audience": "команды", "freshness": "обновлялся в этом месяце", "traffic": None,
         "features": {"templates": rnd.random() < 0.7, "api": rnd.random() < 0.5, "offline": rnd.random() < 0.3, "teams": rnd.random() < 0.6},
         "features_labels": {"templates": "Шаблоны", "api": "Публичный API", "offline": "Офлайн", "teams": "Команды"},
         "better_than_us": ["онбординг"], "we_better": ["цена"], "best_solutions": ["шаблоны на старте"], "design_note": "светлая тема, крупные карточки",
         "complaints": ["дорого"], "adopt": ["галерея шаблонов"], "avoid": ["принудительная регистрация"], "verdict": "сильнее по онбордингу", "verdict_long": "Сильнее нас по онбордингу и шаблонам, слабее по цене и открытости; стоит перенять галерею шаблонов, не повторять обязательную регистрацию",
         "shot": None, "shot_blocked": False, "sources": ["https://example.com/rival-%d" % i]} for i in range(1, 11)])
    write(out, "data/communities.json", [{"name": "Демо-форум %d" % i, "url": "https://example.com/forum/%d" % i, "platform": "форум",
                                          "language": "ru", "audience_size": None, "self_promo_rules": "только в пятничной ветке",
                                          "allowed_formats": ["кейс", "вопрос"], "ban_risk": rnd.randint(1, 5), "source": "https://example.com/rules"} for i in range(1, 6)])
    write(out, "data/keywords.json", [{"query": "демо запрос %d" % i, "lang": "ru", "cluster": "кластер %d" % (i % 3), "intent": "info",
                                       "volume": rnd.choice([None, 90, 320, 1300]), "volume_source": "демо", "competition": rnd.randint(1, 5)} for i in range(1, 16)])
    write(out, "data/events.json", [{"date": "%s-%02d-15" % (today[:4], m), "date_end": None, "title": "Демо-событие %d" % m, "kind": "конференция",
                                     "relevance": "средняя", "source": "https://example.com/events", "verified": True} for m in (3, 6, 9, 11)])
    write(out, "data/sources.json", [{"id": "S%03d" % i, "url": "https://example.com/evidence/%d" % i, "title": "Демо-источник %d" % i,
                                      "date_checked": today, "used_for": "P%03d" % i, "status": None, "note": ""} for i in range(1, 21)])
    write(out, "data/gantt.json", [
        {"id": "G%02d" % i, "phase": ph, "task": "Демо-задача %d" % i, "proposal_ids": ["P%03d" % i], "start_month": s, "end_month": e,
         "type": "milestone" if s == e else "task", "owner": "команда", "done_criteria": "метрика достигнута", "dependencies": []}
        for i, (ph, s, e) in enumerate([("30 дней", 1, 1), ("90 дней", 1, 3), ("90 дней", 2, 3), ("6 месяцев", 3, 6), ("6 месяцев", 4, 6),
                                        ("12 месяцев", 6, 12), ("12 месяцев", 9, 12), ("vision", 13, 24), ("vision", 24, 36)], 1)])
    cols = ["Идеи", "Проверка", "Готово к разработке", "В работе", "Запуск", "Измерение", "Закрыто"]
    write(out, "data/kanban.json", {"columns": [{"name": c, "wip": w} for c, w in zip(cols, [None, 5, 8, 4, 3, 6, None])],
                                    "cards": [{"id": p["id"], "title": p["title"], "column": cols[k % 6], "goal": "демо-цель", "steps": ["шаг 1", "шаг 2"],
                                               "kpi": "активация", "links": [], "tags": [], "priority": "P1", "effort_days": p["effort_days"]}
                                              for k, p in enumerate(props[:20])]})
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 120"><rect data-node="user-journey:1" x="10" y="30" width="180" height="60" rx="8" fill="#eef"/>'
           '<text x="100" y="65" text-anchor="middle">Первый визит</text><rect data-node="user-journey:2" x="230" y="30" width="180" height="60" rx="8" fill="#efe"/>'
           '<text x="320" y="65" text-anchor="middle">Активация</text><rect data-node="user-journey:3" x="450" y="30" width="180" height="60" rx="8" fill="#fee"/>'
           '<text x="540" y="65" text-anchor="middle">Оплата</text></svg>')
    write(out, "charts/flows/user-journey.svg", svg)
    write(out, "data/flows.json", [{"key": "user-journey", "title": "Путь пользователя", "svg": "charts/flows/user-journey.svg",
                                    "nodes": [{"id": "user-journey:%d" % k, "label": lab, "what": "демо", "now": "демо", "todo": ["демо"],
                                               "proposals": ["P%03d" % k], "metrics": "демо"} for k, lab in enumerate(["Первый визит", "Активация", "Оплата"], 1)]}])
    write(out, "data/mockups-index.json", [{"key": "M%02d-demo" % k, "html": "mockups/concepts/M%02d-demo.html" % k,
                                            "png": "mockups/concepts/M%02d-demo.png" % k, "title": "Демо-концепт %d" % k,
                                            "proposals": [props[k - 1]["id"]], "viewport": "1440x900", "kind": "concept"} for k in range(1, 7)])
    for k in range(1, 7):
        write(out, "mockups/concepts/M%02d-demo.html" % k,
              '<!doctype html><meta charset="utf-8"><title>Демо %d</title><body style="font:16px system-ui;margin:0">'
              '<div style="position:fixed;top:8px;right:8px;background:#c00;color:#fff;padding:4px 8px">Концепт, не существующая функция</div>'
              '<h1 style="padding:40px">Демо-концепт %d</h1></body>' % (k, k))
    write(out, "design-refs/01-demo.json", {"file": "mockups/concepts/M01-demo.html", "png": "design-refs/01-demo.png", "scale": 1,
                                            "width": 1440, "height": 900, "title": "Демо-референс", "proposals": [props[0]["id"]],
                                            "kind": "page", "summary": "демо", "entry": "демо", "shared": [], "new_elements": ["кнопка"],
                                            "hotspots": [{"n": 1, "x": 40, "y": 30, "w": 400, "h": 60, "title": "Заголовок", "text": "демо",
                                                          "proposal": props[0]["id"], "state": "new"}], "todo": ["демо"], "questions": []})
    write(out, "design-refs/01-demo.md", "# Демо-референс\n\n## Что это\nдемо\n\n## Как выглядит\nдемо\n\n## Как взаимодействовать\nдемо\n\n"
                                         "## Что нужно доделать\nдемо\n\n## Элементы\nдемо\n\n## Открытые вопросы\nнет\n")
    top = [p["id"] for p in props[:3]]
    write(out, "research/strategy.md", "\n\n".join([
        "# Стратегия Demo App (демо)",
        "## 1. Резюме\nТри главные ставки: %s, %s, %s. [допущение]" % tuple(top),
        "## 2. Понимание продукта\nДемо-текст со ссылкой на %s.\n\n![[chart:effort-impact]]" % props[3]["id"],
        "## 3. Рынок и конкуренты\nДемо-текст.\n\n![[mockup:M01-demo]]",
        "## 10. Дорожная карта\nДемо: сначала %s, затем %s.\n\n![[ref:01-demo]]" % (props[4]["id"], props[5]["id"]),
        "## 13. План действий\n| Срок | Что |\n|---|---|\n| 30 дней | %s |\n| 90 дней | %s |" % (props[6]["id"], props[7]["id"]),
    ]) + "\n")
    write(out, "research/questions-owner.md", "# Вопросы владельцу\n\n1. Демо-вопрос про аудиторию?\n2. Демо-вопрос про бюджет?\n")
    write(out, "build/STATUS.md", "# Статус\n\nДемо-прогон, сгенерирован make_demo.py %s.\n" % today)
    print("Демо-прогон: %s (предложений %d)" % (out, len(props)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
