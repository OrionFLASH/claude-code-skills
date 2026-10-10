#!/usr/bin/env python3
"""Фаза 5.5 «аудит пробелов и предпосылок»: фактура для агента-аудитора и проверка его выдачи.

  gap_audit.py <OUT> [--top 30] [--bets P012,P031,P056]   → build/gap-audit-facts.md + data/gap-audit-facts.json
  gap_audit.py <OUT> --check                              → проверка research/gap-audit.md и data/proposals-draft-G7.json

Фактура (режим по умолчанию) — только факты из данных, без выводов (выводы делает агент-аудитор):
  - топ-N (по умолчанию 30) по рангу и три главные ставки (--bets, иначе эвристика: лучшие по рангу из квадранта
    big_bet или с меткой strategic, затем просто лучшие по рангу) — с dependencies, транзитивными предпосылками
    (blocked_by), dep_rank и тем, что они разблокируют;
  - предупреждения: предложение из топ-20 зависит (транзитивно) от предложения ниже топ-60;
  - предложения топа без зависимостей, но с ключевыми словами предпосылок (демо, открытый репозиторий, хостинг,
    лицензия, API, платёж, домен, аналитика, установка, сайт, перевод — списки RU/EN ниже) в описании/шагах;
    рядом — предложения реестра, в названии которых есть то же слово (возможные «поставщики» предпосылки);
  - дубли и пересечения внутри топа (сходство merge_proposals.Similarity ≥ --sim, по умолчанию 0,18);
  - возможные противоречия «бесплатно vs платно»: в одном описании «бесплатн/free» и «pro/платн/paid/premium»,
    и пары похожих предложений, где одно про бесплатное, другое про платное;
  - покрытие: категории и классы доказательств в реестре и в топе (минимумы — check_registry.category_requirements),
    доли A+B внешних/внутренних, горизонты; циклы и неизвестные ссылки в зависимостях.
Читает: data/proposals.json, data/scores.json (без него — порядок файла и предупреждение), build/run-config.json,
data/registry-check.json, data/gap-audit-deps.json (необязательно).

--check (для build_all): research/gap-audit.md существует и содержит разделы (заголовки #…) «Предпосылки»,
«Пробелы», «Конфликты»; P-id в нём существуют в реестре; data/proposals-draft-G7.json (если есть) — список
предложений по контракту (check_registry.check_proposal), id вида G7-NN; data/gap-audit-deps.json (если есть) —
объект {id: [id…]} с существующими id. Код выхода 0 — ок, 1 — есть ошибки. Только стандартная библиотека.
"""
import argparse
import json
import re
import sys
from collections import Counter
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_registry import CATEGORIES, category_requirements, check_proposal, evidence_split  # noqa: E402
from merge_proposals import Similarity  # noqa: E402

# семейства предпосылок: ключ → (подпись, регулярное выражение RU/EN)
PREREQ_FAMILIES = [
    ("demo", "публичное демо", r"демо|demo\b|витрин|showcase|playground|песочниц"),
    ("repo_open", "открытый репозиторий / исходный код", r"репозитори|open[ -]?source|открыт\w* код|исходн\w* код|github|\boss\b|форк"),
    ("hosting", "хостинг / сервер", r"хостинг|hosting|захостит|сервер|server|deploy|разверн|развёрт|vps|cloud|облак"),
    ("license", "лицензия", r"лиценз|license|\bmit\b|\bgpl|apache 2|copyright"),
    ("api", "API / интеграция", r"\bapi\b|\bапи\b|sdk|webhook|вебхук|эндпоинт|endpoint"),
    ("payment", "приём платежей", r"платёж|платеж|оплат|payment|checkout|stripe|paddle|юkassa|юкасс|robokassa|самозанят|\bчек(и|ов|ом)?\b"),
    ("domain", "домен", r"домен|domain|\bdns\b"),
    ("analytics", "продуктовая аналитика / измерения", r"аналитик\w* (продукт|воронк|использован|событ)|метрик|событи[йяе] |трекинг|tracking|"
                                                       r"telemetry|телеметр|analytics|utm|счётчик|счетчик|воронк"),
    ("install", "установка / релиз", r"установ|install|релиз|release|пакет|pypi|homebrew|winget|portable|портатив"),
    ("site", "сайт / посадочная страница", r"лендинг|landing|посадочн|сайт\b|сайта|website|github pages|страниц\w* (продукт|установ)"),
    ("i18n", "перевод интерфейса", r"английск|english|перевод|i18n|локализ|translation"),
]
FREE_RE = re.compile(r"бесплатн|\bfree\b|\bfree-|freemium|даром", re.I)
PAID_RE = re.compile(r"\bpro\b|платн|\bpaid\b|premium|премиум|подписк|тариф", re.I)
SECTIONS = {"Предпосылки": r"предпосылк|prerequisit", "Пробелы": r"пробел|gaps?\b", "Конфликты": r"конфликт|противореч|conflict"}


def jload(path, default=None):
    p = Path(path)
    if not p.exists():
        return default
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def short(text, n=400):
    t = re.sub(r"\s+", " ", str(text or "")).strip()
    return t if len(t) <= n else t[:n].rsplit(" ", 1)[0] + " […]"


def text_of(p):
    """Текст для поиска предпосылок: описание, обоснование, шаги (без названия)."""
    steps = " ".join("%s %s %s" % (s.get("what", ""), s.get("where", ""), s.get("how", ""))
                     for s in p.get("steps") or [] if isinstance(s, dict))
    return " ".join([str(p.get("description") or ""), str(p.get("rationale") or ""), steps, str(p.get("current_feature") or "")])


def family_hits(text):
    low = str(text or "").lower().replace("ё", "е")
    out = {}
    for key, _, rx in PREREQ_FAMILIES:
        found = sorted({m.group(0) for m in re.finditer(rx, low)})
        if found:
            out[key] = found[:6]
    return out


def order_proposals(props, scores):
    """Порядок по рангу (scores.json) или по файлу; словарь строк оценок по id."""
    srow = {s.get("id"): s for s in scores or [] if isinstance(s, dict)}
    if srow:
        ordered = sorted((p for p in props if p["id"] in srow), key=lambda p: srow[p["id"]].get("rank", 10 ** 6))
        ordered += [p for p in props if p["id"] not in srow]
    else:
        ordered = list(props)
    rank = {p["id"]: srow.get(p["id"], {}).get("rank", k + 1) for k, p in enumerate(ordered)}
    return ordered, srow, rank


def closure(prereq, start):
    """Транзитивные предпосылки {id: глубина}."""
    seen, frontier, d = {}, [start], 0
    while frontier:
        d += 1
        nxt = []
        for v in frontier:
            for u in prereq.get(v, []):
                if u not in seen and u != start:
                    seen[u] = d
                    nxt.append(u)
        frontier = nxt
    return seen


def build_facts(out_dir, top_n=30, bets_arg=None, sim_min=0.18):
    data = out_dir / "data"
    cfg = jload(out_dir / "build" / "run-config.json", {}) or {}
    props = [p for p in jload(data / "proposals.json", []) or [] if isinstance(p, dict) and p.get("id")]
    scores = jload(data / "scores.json", []) or []
    rc = jload(data / "registry-check.json", {}) or {}
    extra = jload(data / "gap-audit-deps.json", {}) or {}
    notes = []
    if not props:
        raise SystemExit("нет data/proposals.json или он пуст")
    if not scores:
        notes.append("нет data/scores.json — порядок по файлу реестра; запустите score.py для рангов и dep_rank")
    ordered, srow, rank = order_proposals(props, scores)
    by_id = {p["id"]: p for p in props}
    ids = set(by_id)
    prereq, unknown = {}, []
    for p in props:
        lst = []
        for d in p.get("dependencies") or []:
            if d in ids and d != p["id"]:
                lst.append(d)
            elif d != p["id"]:
                unknown.append({"id": p["id"], "ref": d, "source": "dependencies"})
        for d in (extra.get(p["id"]) or []) if isinstance(extra, dict) else []:
            if d in ids and d not in lst and d != p["id"]:
                lst.append(d)
        prereq[p["id"]] = lst
    unlocks = {pid: [] for pid in ids}
    for v, ps in prereq.items():
        for u in ps:
            unlocks[u].append(v)
    n = min(top_n, len(ordered))
    top = ordered[:n]
    top_ids = {p["id"] for p in top}

    def brief(pid, extra_fields=True):
        p, s = by_id[pid], srow.get(pid, {})
        o = {"id": pid, "rank": rank[pid], "dep_rank": s.get("dep_rank"), "title": p.get("title", ""),
             "category": p.get("category"), "priority": s.get("priority"), "quadrant": s.get("quadrant"),
             "evidence_class": p.get("evidence_class"), "horizon": p.get("horizon")}
        if extra_fields:
            o.update({"effort_days": p.get("effort_days"), "description": short(p.get("description")),
                      "current_feature": short(p.get("current_feature"), 200), "tags": p.get("tags") or [],
                      "dependencies": prereq[pid],
                      "blocked_by": s.get("blocked_by") if "blocked_by" in s else sorted(closure(prereq, pid), key=lambda x: rank[x]),
                      "unlocks": sorted(unlocks[pid], key=lambda x: rank[x]), "critical_path": s.get("critical_path")})
        return o

    top_rows = [brief(p["id"]) for p in top]
    # три главные ставки
    if bets_arg:
        bet_ids = [b.strip() for b in bets_arg.split(",") if b.strip() in ids][:3]
        rule = "заданы --bets"
    else:
        pool = [p["id"] for p in ordered if srow.get(p["id"], {}).get("quadrant") == "big_bet"
                or "strategic" in (srow.get(p["id"], {}).get("labels") or [])]
        bet_ids = pool[:3]
        bet_ids += [p["id"] for p in ordered if p["id"] not in bet_ids][:3 - len(bet_ids)]
        rule = "эвристика: лучшие по рангу из квадранта big_bet или с меткой strategic, затем лучшие по рангу"
    bets = []
    for b in bet_ids:
        cl = closure(prereq, b)
        bets.append(dict(brief(b), prerequisites=[dict(brief(u, False), depth=d, in_top=u in top_ids)
                                                  for u, d in sorted(cl.items(), key=lambda kv: (kv[1], rank[kv[0]]))]))
    prereqs = []
    for p in top:
        cl = closure(prereq, p["id"])
        if cl:
            prereqs.append({"id": p["id"], "rank": rank[p["id"]], "title": p.get("title", ""),
                            "transitive": [dict(brief(u, False), depth=d, in_top=u in top_ids)
                                           for u, d in sorted(cl.items(), key=lambda kv: (kv[1], rank[kv[0]]))]})
    # топ-20 зависит от ниже топ-60
    warn_top, warn_below = 20, 60
    D = (jload(data / "weights.json", {}) or {}).get("dependency") or {}
    warn_top, warn_below = int(D.get("warn_top", warn_top)), int(D.get("warn_below", warn_below))
    dep_warn = []
    for p in ordered[:warn_top]:
        for u, d in sorted(closure(prereq, p["id"]).items(), key=lambda kv: rank[kv[0]]):
            if rank[u] > warn_below:
                dep_warn.append({"id": p["id"], "rank": rank[p["id"]], "prereq": u, "prereq_rank": rank[u], "depth": d,
                                 "text": "%s (ранг %d) зависит от %s (ранг %d) — ниже топ-%d" % (p["id"], rank[p["id"]], u, rank[u], warn_below)})
    # ключевые слова предпосылок без зависимостей
    providers = {}
    for key, _, rx in PREREQ_FAMILIES:
        providers[key] = [p["id"] for p in ordered if re.search(rx, str(p.get("title") or "").lower().replace("ё", "е"))]
    flags = []
    scan = top + [by_id[b] for b in bet_ids if b not in top_ids]
    for p in scan:
        if prereq[p["id"]]:
            continue
        hits = family_hits(text_of(p))
        own = family_hits(p.get("title"))
        fam = []
        for key, label, _ in PREREQ_FAMILIES:
            if key not in hits or key in own:
                continue
            if key == "analytics" and p.get("category") == "analytics":
                continue
            prov = [x for x in providers[key] if x != p["id"]][:5]
            fam.append({"family": key, "label": label, "words": hits[key],
                        "providers": [brief(x, False) for x in prov]})
        if fam:
            flags.append({"id": p["id"], "rank": rank[p["id"]], "title": p.get("title", ""), "families": fam})
    # дубли и пересечения внутри топа
    sim = Similarity(props)
    idx = [sim.pos[p["id"]] for p in top]
    similar = []
    for i, j, r in sim.pairs(sim_min, idx):
        a, b = sim.ids[i], sim.ids[j]
        similar.append({"a": a, "b": b, "score": round(r["score"], 3),
                        "kind": "возможный дубль" if r["score"] >= 0.275 else "пересечение",
                        "a_title": by_id[a].get("title", ""), "b_title": by_id[b].get("title", ""),
                        "a_rank": rank[a], "b_rank": rank[b]})
    # бесплатно vs платно
    fvp = []
    for p in top:
        t = "%s %s" % (p.get("title", ""), p.get("description", ""))
        f, pd = sorted({m.group(0).lower() for m in FREE_RE.finditer(t)}), sorted({m.group(0).lower() for m in PAID_RE.finditer(t)})
        if f and pd:
            fvp.append({"id": p["id"], "rank": rank[p["id"]], "title": p.get("title", ""), "free_words": f, "paid_words": pd,
                        "snippet": short(p.get("description"), 240)})
    fvp_pairs = []
    for s in similar:
        ta = "%s %s" % (by_id[s["a"]].get("title", ""), by_id[s["a"]].get("description", ""))
        tb = "%s %s" % (by_id[s["b"]].get("title", ""), by_id[s["b"]].get("description", ""))
        fa, fb = bool(FREE_RE.search(ta)), bool(FREE_RE.search(tb))
        pa, pb = bool(PAID_RE.search(ta)), bool(PAID_RE.search(tb))
        if (fa and pb and not fb) or (fb and pa and not fa):
            fvp_pairs.append({"a": s["a"], "b": s["b"], "score": s["score"], "a_title": s["a_title"], "b_title": s["b_title"]})
    # покрытие
    min_n = rc.get("min") or (cfg.get("strategy") or {}).get("proposals_min") or 100
    reqs = category_requirements(cfg, min_n)
    cnt_all = Counter(p.get("category") for p in props)
    cnt_top = Counter(p.get("category") for p in top)
    cats = {}
    for c in CATEGORIES:
        r = reqs.get(c, {})
        cats[c] = {"total": cnt_all.get(c, 0), "in_top": cnt_top.get(c, 0), "required": r.get("required", 0),
                   "na": r.get("na", False), "optional": r.get("optional", False),
                   "ok": r.get("na") or r.get("optional") or cnt_all.get(c, 0) >= r.get("required", 0)}
    split = evidence_split(props, cfg)
    cls_all = Counter(p.get("evidence_class") for p in props)
    cls_top = Counter(p.get("evidence_class") for p in top)
    hz_top = Counter(p.get("horizon") for p in top)
    coverage = {"categories": cats,
                "missing_in_top": [c for c in CATEGORIES if not cnt_top.get(c) and not cats[c]["na"]],
                "below_minimum": [c for c, v in cats.items() if not v["ok"]],
                "evidence_classes": {"all": {k: cls_all.get(k, 0) for k in "ABCD"}, "top": {k: cls_top.get(k, 0) for k in "ABCD"}},
                "ab_share": round((cls_all.get("A", 0) + cls_all.get("B", 0)) / len(props), 4),
                "ab_external_share": split["ab_external"], "ab_internal_share": split["ab_internal"],
                "horizons_top": dict(hz_top), "top_d_class": [p["id"] for p in top if p.get("evidence_class") == "D"]}
    cp = jload(data / "critical-path.json", {}) or {}
    facts = {"version": 1, "date": date.today().isoformat(), "product": (cfg.get("product") or {}).get("name") or "",
             "profile": (cfg.get("strategy") or {}).get("profile") or "standard",
             "project": cfg.get("project") or {}, "constraints": (cfg.get("strategy") or {}).get("constraints") or "",
             "total": len(props), "top_n": n, "notes": notes,
             "top": top_rows, "bets": {"rule": rule, "items": bets}, "prerequisites": prereqs,
             "dependency_warnings": dep_warn, "keyword_flags": flags, "similar_pairs": similar,
             "free_vs_paid": fvp, "free_vs_paid_pairs": fvp_pairs, "coverage": coverage,
             "critical_path": cp.get("order") or [], "cycles": cp.get("cycles") or [], "unknown_dependencies": unknown,
             "families": [{"key": k, "label": lab, "pattern": rx} for k, lab, rx in PREREQ_FAMILIES]}
    return facts


def render_md(f):
    L = ["# Фактура для аудита пробелов и предпосылок (фаза 5.5)", "",
         "Сгенерировано `gap_audit.py` %s. Только факты из данных; выводы, новые предложения G7-NN и предпосылки "
         "(`data/gap-audit-deps.json`) делает агент-аудитор. Продукт: %s; профиль: %s; предложений: %d; топ: %d."
         % (f["date"], f["product"] or "—", f["profile"], f["total"], f["top_n"]), ""]
    if f["constraints"]:
        L += ["Ограничения из опроса: %s" % f["constraints"], ""]
    for n in f["notes"]:
        L += ["> ! %s" % n, ""]
    L += ["## 1. Три главные ставки", "", "Правило выбора: %s." % f["bets"]["rule"], ""]
    for b in f["bets"]["items"]:
        L.append("### %s «%s» — ранг %s, dep_rank %s, %s, класс %s" % (b["id"], b["title"], b["rank"], b["dep_rank"] or "—",
                                                                     b["category"], b["evidence_class"]))
        L.append("")
        L.append("%s" % b["description"])
        L.append("")
        if b["prerequisites"]:
            L.append("Транзитивные предпосылки: " + "; ".join("%s «%s» (ранг %s, глубина %d%s)" % (
                u["id"], u["title"], u["rank"], u["depth"], "" if u["in_top"] else ", вне топа") for u in b["prerequisites"]))
        else:
            L.append("Предпосылок в реестре нет (dependencies пусто).")
        if b["unlocks"]:
            L.append("Разблокирует: " + ", ".join(b["unlocks"]))
        L.append("")
    L += ["## 2. Топ-%d с зависимостями" % f["top_n"], "",
          "| ранг | dep_rank | id | название | категория | класс | горизонт | усилие, дн. | зависит от | все предпосылки | разблокирует |",
          "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in f["top"]:
        ed = r.get("effort_days") or []
        L.append("| %s | %s | %s%s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
            r["rank"], r["dep_rank"] or "—", r["id"], " ★" if r.get("critical_path") else "", r["title"].replace("|", "/"),
            r["category"], r["evidence_class"], r["horizon"], "–".join(map(str, ed)) if ed else "—",
            ", ".join(r["dependencies"]) or "—", ", ".join(r["blocked_by"] or []) or "—", ", ".join(r["unlocks"]) or "—"))
    L += ["", "★ — на критическом пути (`data/critical-path.json`): %s." % (" → ".join(f["critical_path"]) or "нет"), ""]
    L += ["### Описания топа", ""]
    for r in f["top"]:
        L.append("- **%s** «%s»: %s Сейчас: %s." % (r["id"], r["title"], r["description"], r["current_feature"] or "—"))
    L += ["", "## 3. Предупреждения о зависимостях", ""]
    L += ["- %s" % w["text"] for w in f["dependency_warnings"]] or ["Нет: ни одно предложение топ-20 не зависит от предложений ниже топ-60."]
    if f["cycles"]:
        L += ["- Циклы зависимостей (score.py разорвал детерминированно): " + "; ".join(" ↔ ".join(c) for c in f["cycles"])]
    if f["unknown_dependencies"]:
        L += ["- Неизвестные ссылки в зависимостях: " + "; ".join("%s → %s" % (u["id"], u["ref"]) for u in f["unknown_dependencies"])]
    L += ["", "## 4. Без зависимостей, но с признаками предпосылок", "",
          "Слова найдены в описании/шагах; «поставщики» — предложения реестра с тем же словом в названии.", ""]
    if not f["keyword_flags"]:
        L.append("Нет.")
    for x in f["keyword_flags"]:
        L.append("- **%s** «%s» (ранг %s):" % (x["id"], x["title"], x["rank"]))
        for fam in x["families"]:
            prov = ", ".join("%s (ранг %s)" % (p["id"], p["rank"]) for p in fam["providers"]) or "в реестре нет"
            L.append("  - %s — слова: %s; поставщики: %s" % (fam["label"], ", ".join(fam["words"]), prov))
    L += ["", "## 5. Дубли и пересечения внутри топа", ""]
    L += ["- %.3f %s: %s «%s» (ранг %s) ↔ %s «%s» (ранг %s)" % (s["score"], s["kind"], s["a"], s["a_title"], s["a_rank"],
                                                               s["b"], s["b_title"], s["b_rank"]) for s in f["similar_pairs"]] or ["Нет."]
    L += ["", "## 6. Бесплатно vs платно", ""]
    L += ["- %s «%s» (ранг %s): «%s» и «%s» — %s" % (x["id"], x["title"], x["rank"], ", ".join(x["free_words"]),
                                                     ", ".join(x["paid_words"]), x["snippet"]) for x in f["free_vs_paid"]] or ["В описаниях топа нет."]
    for x in f["free_vs_paid_pairs"]:
        L.append("- пара %s / %s (сходство %.3f): одно про бесплатное, другое про платное — «%s» / «%s»"
                 % (x["a"], x["b"], x["score"], x["a_title"], x["b_title"]))
    c = f["coverage"]
    L += ["", "## 7. Покрытие", "", "| категория | всего | в топе | минимум | статус |", "|---|---|---|---|---|"]
    for k, v in c["categories"].items():
        st = "н/п" if v["na"] else ("по запросу" if v["optional"] else ("ок" if v["ok"] else "ниже минимума"))
        L.append("| %s | %d | %d | %s | %s |" % (k, v["total"], v["in_top"], v["required"], st))
    L += ["", "Нет в топе: %s. Ниже минимума: %s." % (", ".join(c["missing_in_top"]) or "—", ", ".join(c["below_minimum"]) or "—"),
          "Классы доказательств — реестр: %s; топ: %s. A+B всего %.0f %% (внешние %.0f %%, внутренние %.0f %%). "
          "Класс D в топе: %s." % (
              ", ".join("%s %d" % kv for kv in c["evidence_classes"]["all"].items()),
              ", ".join("%s %d" % kv for kv in c["evidence_classes"]["top"].items()), c["ab_share"] * 100,
              c["ab_external_share"] * 100, c["ab_internal_share"] * 100, ", ".join(c["top_d_class"]) or "нет"),
          "Горизонты топа: %s." % (", ".join("%s %d" % kv for kv in c["horizons_top"].items()) or "—"), ""]
    L += ["## 8. Вопросы аудитору", "",
          "1. Что должно существовать до трёх ставок и топа (хостинг, открытый код, лицензия, платёжный путь, домен, "
          "измерения)? Есть ли это в реестре — какие id? Нет — черновик G7-NN.",
          "2. Каких предложений не хватает, чтобы ставки сработали (пробелы)?",
          "3. Какие предложения конфликтуют или дублируют существующую функцию (см. разделы 5–6 и current_feature)?",
          "4. Какие предпосылки дописать в `data/gap-audit-deps.json` (`{\"P035\": [\"P031\", \"P032\"]}`)?", ""]
    return "\n".join(L)


def run_check(out_dir):
    """--check: research/gap-audit.md, черновики G7, gap-audit-deps.json. Возвращает (errors, warnings)."""
    errors, warnings = [], []
    md = out_dir / "research" / "gap-audit.md"
    props = [p for p in jload(out_dir / "data" / "proposals.json", []) or [] if isinstance(p, dict)]
    ids = {p.get("id") for p in props}
    if not md.exists():
        errors.append("нет research/gap-audit.md")
    else:
        text = md.read_text(encoding="utf-8")
        heads = [h.strip().lower() for h in re.findall(r"^#{1,6}\s+(.+)$", text, re.M)]
        for name, rx in SECTIONS.items():
            if not any(re.search(rx, h, re.I) for h in heads):
                errors.append("research/gap-audit.md: нет раздела «%s» (заголовок # …)" % name)
        if ids:
            for pid in sorted(set(re.findall(r"\bP\d{3,}\b", text))):
                if pid not in ids:
                    errors.append("research/gap-audit.md: %s нет в реестре" % pid)
    draft = out_dir / "data" / "proposals-draft-G7.json"
    if draft.exists():
        try:
            raw = json.loads(draft.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raw = None
            errors.append("proposals-draft-G7.json не разбирается как JSON: %s" % e)
        if raw is not None:
            if isinstance(raw, dict):
                raw = raw.get("proposals")
            if not isinstance(raw, list):
                errors.append("proposals-draft-G7.json должен быть списком предложений")
                raw = []
            seen = Counter()
            for i, p in enumerate(raw):
                if not isinstance(p, dict):
                    errors.append("G7 #%d: не объект" % (i + 1))
                    continue
                seen[p.get("id")] += 1
                if not re.fullmatch(r"G7-\d{2,}", str(p.get("id") or "")):
                    errors.append("G7 #%d: id %r не вида G7-NN" % (i + 1, p.get("id")))
                e0, w0 = [], []
                check_proposal(p, i, False, e0, w0, {})
                errors += ["G7: " + e for e in e0]
                warnings += ["G7: " + w for w in w0]
                for d in p.get("dependencies") or []:
                    if d not in ids and not re.fullmatch(r"G7-\d{2,}", str(d)):
                        errors.append("G7 %s: зависимость %r нет ни в реестре, ни среди G7" % (p.get("id"), d))
            for k, v in seen.items():
                if v > 1:
                    errors.append("G7: повторяющийся id %s" % k)
    else:
        warnings.append("нет data/proposals-draft-G7.json — аудитор не предложил новых предложений (допустимо, если так "
                        "сказано в research/gap-audit.md)")
    deps = out_dir / "data" / "gap-audit-deps.json"
    if deps.exists():
        d = jload(deps, None)
        if not isinstance(d, dict):
            errors.append("data/gap-audit-deps.json должен быть объектом {id: [предпосылки]}")
        else:
            for k, v in d.items():
                if k not in ids:
                    errors.append("gap-audit-deps.json: %s нет в реестре" % k)
                for x in (v if isinstance(v, list) else [v]):
                    if x not in ids:
                        errors.append("gap-audit-deps.json: %s → %r нет в реестре" % (k, x))
    return errors, warnings


def main(argv=None):
    ap = argparse.ArgumentParser(description="Аудит пробелов и предпосылок: фактура для агента и проверка его выдачи.")
    ap.add_argument("out", help="папка прогона <OUT>")
    ap.add_argument("--top", type=int, default=30, help="размер топа (30)")
    ap.add_argument("--bets", help="три главные ставки через запятую (иначе эвристика)")
    ap.add_argument("--sim", type=float, default=0.18, help="порог сходства для пар внутри топа (0.18)")
    ap.add_argument("--check", action="store_true", help="проверить research/gap-audit.md и data/proposals-draft-G7.json")
    a = ap.parse_args(argv)
    out_dir = Path(a.out).resolve()
    if a.check:
        errors, warnings = run_check(out_dir)
        for w in warnings:
            print("  - " + w)
        for e in errors:
            print("  ! " + e)
        print("FAIL: ошибок %d" % len(errors) if errors else "OK: аудит пробелов оформлен")
        return 1 if errors else 0
    facts = build_facts(out_dir, a.top, a.bets, a.sim)
    (out_dir / "data").mkdir(parents=True, exist_ok=True)
    (out_dir / "build").mkdir(parents=True, exist_ok=True)
    (out_dir / "data" / "gap-audit-facts.json").write_text(json.dumps(facts, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "build" / "gap-audit-facts.md").write_text(render_md(facts), encoding="utf-8")
    print("Фактура: топ-%d, ставки %s; предупреждений о зависимостях %d; признаков предпосылок %d; похожих пар %d; "
          "«бесплатно/платно» %d" % (facts["top_n"], ", ".join(b["id"] for b in facts["bets"]["items"]),
                                    len(facts["dependency_warnings"]), len(facts["keyword_flags"]),
                                    len(facts["similar_pairs"]), len(facts["free_vs_paid"]) + len(facts["free_vs_paid_pairs"])))
    for n in facts["notes"]:
        print("  ! " + n)
    print("Записано: build/gap-audit-facts.md, data/gap-audit-facts.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
