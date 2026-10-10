#!/usr/bin/env python3
"""Проверка качества реестра data/proposals.json по references/data-contract.md.

  check_registry.py <OUT> [--min N] [--demo] [--quiet]

Проверяет: обязательные поля и типы; уникальность id; минимум предложений (--min, иначе run-config
strategy.proposals_min, иначе 100); минимумы по категориям в процентах от минимума (category_requirements:
категории из strategy.categories_na пропускаются; в профиле strategy.profile = zero-budget-solo минимумы
monetization/partnerships/localization/new_lines — «по запросу», см. ниже); долю классов A+B ≥ 60 % по реестру
и отдельно «внутренние» (код, своё приложение, свои данные, скриншоты, документация репозитория продукта) и
«внешние» (конкуренты, сообщества, Issues, внешняя документация, исследования с URL) доказательства —
предупреждение, если внешних A+B < 40 %; формат URL (http/https, без заглушек вроде example.com); цитаты короче
15 слов; зависимости на существующие id (и циклы — предупреждение); горизонты, классы Кано, шкалы 1–5.
Класс D без url/file — норма (рассуждение в note); предупреждение только если нет и note.

Профиль zero-budget-solo: минимум категории monetization применяется, если strategy.paid_tier = yes или
project.goal = commercial; localization — если рынков (strategy.markets) больше одного; partnerships и new_lines —
только если категория перечислена в strategy.categories_required (туда же можно вписать любую из четырёх).

--demo — режим демо-прогона: заглушки URL разрешены, минимумы по категориям и доля A+B — предупреждения
(демо-данные генерируются случайно).

Код выхода 0 — ошибок нет, 1 — есть ошибки. Отчёт — stdout и data/registry-check.json. Только стандартная библиотека.
"""
import argparse
import json
import math
import re
import sys
from collections import Counter
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

CATEGORIES = ["product", "acquisition", "conversion", "retention", "monetization", "analytics", "partnerships",
              "localization", "new_lines", "platform"]
# минимум по категориям, % от минимального числа предложений (universal-strategy-prompt §7)
CATEGORY_MIN_PCT = {"product": 30, "acquisition": 20, "conversion": 8, "retention": 8, "monetization": 8,
                    "analytics": 6, "partnerships": 6, "localization": 5, "new_lines": 3}
EVIDENCE_KINDS = ["competitor", "community", "issue", "docs", "repo", "research", "analytics", "own_app"]
HORIZONS = ["now", "next", "later", "vision"]
KANO = ["must", "linear", "delight", "indifferent"]
SCORE_REQUIRED = ["value", "cost", "risk", "confidence"]
SCORE_OPTIONAL = ["reach", "impact", "acquisition", "activation", "conversion", "retention", "revenue", "virality",
                  "seo", "trust", "moat", "fit", "demand", "season", "testability", "spread"]
RISK_KEYS = ["legal", "ip", "platform", "privacy", "tech", "reputation"]
AB_MIN_SHARE = 0.60
AB_EXTERNAL_MIN_SHARE = 0.40   # минимум «внешних» A+B — для рыночных предложений
# профиль → категории, минимум которых применяется только «по запросу»
PROFILE_OPTIONAL = {"zero-budget-solo": ["monetization", "partnerships", "localization", "new_lines"]}
INTERNAL_KINDS = {"repo", "own_app", "analytics"}
EXTERNAL_KINDS = {"competitor", "community"}
IMAGE_EXT = re.compile(r"\.(png|jpe?g|webp|gif|svg|avif)(:\d+)?$", re.I)
QUOTE_MAX_WORDS = 15
TITLE_MAX = 90
PLACEHOLDER_HOSTS = re.compile(r"(^|\.)(example\.(com|org|net)|localhost|test|invalid|placeholder\.\w+|yoursite\.\w+|domain\.\w+)$", re.I)
PLACEHOLDER_TEXT = re.compile(r"(…|\.\.\.|TODO|TBD|XXX|<[^>]*>|\{[^}]*\})")
QUOTE_RE = re.compile(r"[«\"“]([^»\"”]{20,})[»\"”]")
# контекст, в котором кавычки — пример текста интерфейса, а не цитата источника
UI_HINT = re.compile(r"(наприм|вида|текст|подпис|формулиров|кнопк|баннер|сообщен|письм|строк|заголов|плашк|"
                     r"карточк|уведомлен|экран|сводк|дайджест|пример|e\.g\.|for example|label|button|copy)", re.I)

# поле: (типы, обязательное). Необязательные проверяются по типу, если есть.
FIELDS = {
    "id": ((str,), True), "title": ((str,), True), "category": ((str,), True), "segment": ((str,), False),
    "description": ((str,), True), "rationale": ((str,), True), "evidence": ((list,), True),
    "evidence_class": ((str,), True), "current_feature": ((str,), False), "effect_kpi": ((list,), True),
    "steps": ((list,), True), "dependencies": ((list,), True), "effort_days": ((list,), True),
    "cost_money": ((dict,), True), "risks": ((dict,), True), "time_to_first_result_days": ((int, float), True),
    "cheap_test": ((str,), True), "scores": ((dict,), True), "kano": ((str,), True), "horizon": ((str,), True),
    "horizon_years": ((int, float), False), "tags": ((list,), False), "mockup": ((str, type(None)), False),
    "source_group": ((str,), False), "merged_from": ((list,), False),
}


def is_num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def type_ok(v, types):
    if bool in types:
        return isinstance(v, types)
    if isinstance(v, bool):
        return False
    return isinstance(v, types)


def check_url(url, demo):
    """None — ок, иначе текст проблемы."""
    if url is None:
        return None
    if not isinstance(url, str) or not url.strip():
        return "пустой URL"
    u = urlparse(url.strip())
    if u.scheme not in ("http", "https") or not u.netloc or " " in url.strip():
        return "не http/https URL: %s" % url
    if PLACEHOLDER_TEXT.search(url):
        return "заглушка в URL: %s" % url
    if not demo and PLACEHOLDER_HOSTS.search(u.hostname or ""):
        return "заглушка-домен: %s" % url
    return None


def long_quotes(text, ui_exception):
    """Цитаты в кавычках из ≥ 15 слов. ui_exception — не считать цитатой пример текста интерфейса."""
    out = []
    if not isinstance(text, str):
        return out
    for m in QUOTE_RE.finditer(text):
        words = len(m.group(1).split())
        if words >= QUOTE_MAX_WORDS:
            if ui_exception and UI_HINT.search(text[max(0, m.start() - 140):m.start()]):
                continue
            out.append(words)
    return out


def find_cycles(graph):
    """Циклы в зависимостях (список цепочек id)."""
    color, stack, cycles = {}, [], []

    def dfs(v):
        color[v] = 1
        stack.append(v)
        for w in graph.get(v, []):
            if w not in graph:
                continue
            if color.get(w) == 1:
                cycles.append(stack[stack.index(w):] + [w])
            elif color.get(w) is None:
                dfs(w)
        stack.pop()
        color[v] = 2

    sys.setrecursionlimit(max(1000, len(graph) * 4 + 100))
    for v in graph:
        if color.get(v) is None:
            dfs(v)
    return cycles


def category_requirements(cfg, min_n):
    """Минимумы категорий для реестра из min_n предложений с учётом run-config.

    Возвращает {категория: {"pct", "required", "na", "optional", "note"}}: required — сколько нужно (0, если
    категория неприменима или минимум «по запросу» в профиле), na — strategy.categories_na, optional — минимум
    снят профилем. Используют check_registry, merge_proposals (не ронять минимум при слиянии) и gap_audit."""
    cfg = cfg or {}
    strat = cfg.get("strategy") or {}
    project = cfg.get("project") or {}
    na = set(strat.get("categories_na") or []) | set((cfg.get("scope") or {}).get("categories_na") or [])
    profile = strat.get("profile") or "standard"
    requested = set(strat.get("categories_required") or [])
    markets = [m for m in (strat.get("markets") or []) if m and m != "auto"]
    out = {}
    for c, pct in CATEGORY_MIN_PCT.items():
        need = int(math.ceil(pct * min_n / 100.0 - 1e-9))
        optional, note = False, ""
        if c in na:
            note = "неприменима (strategy.categories_na)"
        elif c in PROFILE_OPTIONAL.get(profile, []):
            implied = ((c == "monetization" and (strat.get("paid_tier") == "yes" or project.get("goal") == "commercial"))
                       or (c == "localization" and len(markets) > 1))
            if c in requested or implied:
                note = "профиль %s: минимум применяется (%s)" % (
                    profile, "strategy.categories_required" if c in requested else
                    ("платный тариф/коммерческая цель" if c == "monetization" else "рынков больше одного"))
            else:
                optional = True
                note = "профиль %s: минимум по запросу (strategy.categories_required)" % profile
        out[c] = {"pct": pct, "required": 0 if (c in na or optional) else need, "na": c in na, "optional": optional,
                  "nominal": need, "note": note}
    return out


def own_markers(cfg):
    """Признаки «своих» URL: owner/repo продукта и хост product.url (нижний регистр)."""
    cfg = cfg or {}
    marks = []
    remote = str((cfg.get("repo") or {}).get("remote") or "").strip().lower()
    if remote and remote != "null":
        remote = re.sub(r"^(https?://|git@)", "", remote).replace(":", "/")
        remote = re.sub(r"\.git$", "", remote)
        parts = [x for x in remote.split("/") if x]
        if len(parts) >= 2:
            marks.append("/".join(parts[-2:]))
    host = urlparse(str((cfg.get("product") or {}).get("url") or "")).hostname
    if host:
        marks.append(re.sub(r"^www\.", "", host.lower()))
    return marks


def evidence_side(e, own=()):
    """«internal» — код/своё приложение/свои данные/скриншоты/документация репозитория продукта;
    «external» — конкуренты, сообщества, Issues, внешняя документация, исследования с URL; «none» — без источника."""
    if not isinstance(e, dict):
        return "none"
    kind, url, file = e.get("kind"), str(e.get("url") or ""), str(e.get("file") or "")
    low = url.lower()
    if kind in INTERNAL_KINDS or (file and IMAGE_EXT.search(file) and not url):
        return "internal"
    if url and any(m and m in low for m in own):
        return "internal"
    if kind in EXTERNAL_KINDS:
        return "external"
    if kind == "issue":
        return "internal" if e.get("internal") is True else "external"
    if url:
        return "external"
    return "internal" if file else "none"


def evidence_split(props, cfg=None):
    """Доли A+B: всего, «внешние» (у предложения есть хотя бы одно внешнее доказательство) и только «внутренние»."""
    own = own_markers(cfg)
    total = len(props)
    ab_ext = ab_int = 0
    sides = Counter()
    for p in props:
        ev = [e for e in (p.get("evidence") or []) if isinstance(e, dict)]
        ss = [evidence_side(e, own) for e in ev]
        sides.update(ss)
        if p.get("evidence_class") in ("A", "B"):
            if "external" in ss:
                ab_ext += 1
            else:
                ab_int += 1
    return {"ab_external": round(ab_ext / total, 4) if total else 0.0, "ab_internal": round(ab_int / total, 4) if total else 0.0,
            "ab_external_count": ab_ext, "ab_internal_count": ab_int, "evidence_sides": dict(sides), "own_markers": own}


def check_proposal(p, idx, demo, errors, warnings, quote_by_url):
    pid = p.get("id") if isinstance(p.get("id"), str) and p.get("id") else "#%d" % (idx + 1)
    for f, (types, required) in FIELDS.items():
        if f not in p:
            (errors if required else warnings).append("%s: нет поля %s" % (pid, f))
            continue
        v = p[f]
        if not type_ok(v, types):
            (errors if required else warnings).append("%s: %s — неверный тип %s" % (pid, f, type(v).__name__))
            continue
        if required and isinstance(v, str) and not v.strip():
            errors.append("%s: %s пустое" % (pid, f))
    if isinstance(p.get("title"), str) and len(p["title"]) > TITLE_MAX:
        warnings.append("%s: название длиннее %d знаков (%d)" % (pid, TITLE_MAX, len(p["title"])))
    if "category" in p and p.get("category") not in CATEGORIES:
        errors.append("%s: неизвестная категория %r" % (pid, p.get("category")))
    if "evidence_class" in p and p.get("evidence_class") not in ("A", "B", "C", "D"):
        errors.append("%s: класс доказательства %r не из A–D" % (pid, p.get("evidence_class")))
    if "horizon" in p and p.get("horizon") not in HORIZONS:
        errors.append("%s: горизонт %r не из %s" % (pid, p.get("horizon"), "|".join(HORIZONS)))
    if "kano" in p and p.get("kano") not in KANO:
        errors.append("%s: Кано %r не из %s" % (pid, p.get("kano"), "|".join(KANO)))

    ev = p.get("evidence") if isinstance(p.get("evidence"), list) else []
    if isinstance(p.get("evidence"), list) and not ev:
        errors.append("%s: пустой список evidence" % pid)
    for k, e in enumerate(ev):
        if not isinstance(e, dict):
            errors.append("%s: evidence[%d] не объект" % (pid, k))
            continue
        if e.get("kind") not in EVIDENCE_KINDS:
            warnings.append("%s: evidence[%d].kind %r не из перечня" % (pid, k, e.get("kind")))
        if not e.get("url") and not e.get("file"):
            if p.get("evidence_class") != "D":
                errors.append("%s: evidence[%d] без url и file" % (pid, k))
            elif not str(e.get("note") or "").strip():
                warnings.append("%s: evidence[%d] класса D без url/file и без note (нужна цепочка рассуждения)" % (pid, k))
        prob = check_url(e.get("url"), demo)
        if prob:
            errors.append("%s: evidence[%d] %s" % (pid, k, prob))
        for words in long_quotes(e.get("note"), False):
            errors.append("%s: evidence[%d].note — цитата %d слов (нужно < %d)" % (pid, k, words, QUOTE_MAX_WORDS))
        if isinstance(e.get("note"), str) and QUOTE_RE.search(e["note"]) and e.get("url"):
            quote_by_url.setdefault(e["url"], set()).add(pid)
    for fld in ("description", "rationale", "cheap_test", "current_feature"):
        for words in long_quotes(p.get(fld), True):
            errors.append("%s: %s — цитата %d слов (нужно < %d)" % (pid, fld, words, QUOTE_MAX_WORDS))

    steps = p.get("steps") if isinstance(p.get("steps"), list) else []
    if isinstance(p.get("steps"), list) and not steps:
        errors.append("%s: нет шагов (steps)" % pid)
    for k, s in enumerate(steps):
        if not isinstance(s, dict):
            errors.append("%s: steps[%d] не объект" % (pid, k))
            continue
        if not s.get("what"):
            warnings.append("%s: steps[%d] без what" % (pid, k))
        prob = check_url(s.get("doc_url"), demo)
        if prob:
            errors.append("%s: steps[%d].doc_url %s" % (pid, k, prob))

    ed = p.get("effort_days")
    if isinstance(ed, list):
        if len(ed) != 2 or not all(is_num(x) for x in ed) or ed[0] < 0 or ed[0] > ed[1]:
            errors.append("%s: effort_days должен быть [min, max], 0 ≤ min ≤ max: %r" % (pid, ed))
    cm = p.get("cost_money")
    if isinstance(cm, dict):
        if not (is_num(cm.get("min")) and is_num(cm.get("max"))) or cm.get("min", 0) > cm.get("max", 0):
            errors.append("%s: cost_money.min/max — числа, min ≤ max" % pid)
        if not cm.get("currency"):
            warnings.append("%s: cost_money без currency" % pid)
    if is_num(p.get("time_to_first_result_days")) and p["time_to_first_result_days"] < 0:
        errors.append("%s: time_to_first_result_days < 0" % pid)
    rk = p.get("risks")
    if isinstance(rk, dict):
        for k in RISK_KEYS:
            if k in rk and not (is_num(rk[k]) and 1 <= rk[k] <= 5):
                errors.append("%s: risks.%s=%r вне 1–5" % (pid, k, rk[k]))
    sc = p.get("scores")
    if isinstance(sc, dict):
        for k in SCORE_REQUIRED:
            v = sc.get(k)
            if not (is_num(v) and 1 <= v <= 5):
                errors.append("%s: scores.%s=%r — нужно число 1–5" % (pid, k, v))
        for k in SCORE_OPTIONAL:
            if k in sc and not (is_num(sc[k]) and 1 <= sc[k] <= 5):
                errors.append("%s: scores.%s=%r вне 1–5" % (pid, k, sc[k]))
    for k, kp in enumerate(p.get("effect_kpi") or []):
        if not isinstance(kp, dict) or not kp.get("kpi"):
            warnings.append("%s: effect_kpi[%d] без kpi" % (pid, k))
    if isinstance(p.get("mockup"), str) and not p["mockup"].strip():
        warnings.append("%s: mockup — пустая строка (нужно null)" % pid)


def run_check(out_dir, min_override=None, demo=False):
    """Возвращает отчёт (dict) по реестру."""
    out_dir = Path(out_dir)
    cfg_path = out_dir / "build" / "run-config.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8")) if cfg_path.exists() else {}
    strat = cfg.get("strategy") or {}
    min_n = min_override if min_override is not None else strat.get("proposals_min") or 100
    reqs = category_requirements(cfg, min_n)
    na = {c for c, r in reqs.items() if r["na"]}
    errors, warnings = [], []
    path = out_dir / "data" / "proposals.json"
    try:
        props = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        props, _ = [], errors.append("нет файла %s" % path)
    except json.JSONDecodeError as e:
        props, _ = [], errors.append("proposals.json не разбирается как JSON: %s" % e)
    if not isinstance(props, list):
        errors.append("proposals.json должен быть списком объектов")
        props = []
    good = []
    for i, p in enumerate(props):
        if not isinstance(p, dict):
            errors.append("#%d: не объект" % (i + 1))
            continue
        good.append(p)
    quote_by_url = {}
    for i, p in enumerate(good):
        check_proposal(p, i, demo, errors, warnings, quote_by_url)

    ids = [p.get("id") for p in good if isinstance(p.get("id"), str)]
    dup = sorted(k for k, v in Counter(ids).items() if v > 1)
    if dup:
        errors.append("повторяющиеся id: %s" % ", ".join(dup))
    idset = set(ids)
    graph = {}
    for p in good:
        pid = p.get("id")
        deps = p.get("dependencies") if isinstance(p.get("dependencies"), list) else []
        for d in deps:
            if d == pid:
                errors.append("%s: зависит сам от себя" % pid)
            elif d not in idset:
                errors.append("%s: зависимость %r не найдена в реестре" % (pid, d))
        if isinstance(pid, str):
            graph[pid] = [d for d in deps if isinstance(d, str) and d != pid]
    for cyc in find_cycles(graph)[:10]:
        warnings.append("цикл зависимостей: %s" % " → ".join(cyc))
    for url, pids in sorted(quote_by_url.items()):
        if len(pids) > 1:
            warnings.append("цитаты из одного источника в нескольких предложениях (%s): %s" % (url, ", ".join(sorted(pids))))
    if cfg.get("mode") == "concept":        # режим идеи: продукта и репозитория ещё нет — «внутренних» доказательств быть не может
        own = sorted(p.get("id") for p in good if any(isinstance(e, dict) and e.get("kind") in ("repo", "own_app")
                                                      for e in (p.get("evidence") or [])) and isinstance(p.get("id"), str))
        if own:
            warnings.append("режим идеи: доказательства вида repo/own_app у %s — продукта ещё нет, нужен внешний источник"
                            % ", ".join(own[:10]) + (" и ещё %d" % (len(own) - 10) if len(own) > 10 else ""))

    total = len(good)
    if total < min_n:
        errors.append("предложений %d < минимума %d" % (total, min_n))
    cnt = Counter(p.get("category") for p in good)
    cat_report = {}
    soft = warnings if demo else errors
    for c, r in reqs.items():
        need = r["required"]
        actual = cnt.get(c, 0)
        skip = r["na"] or r["optional"]
        cat_report[c] = {"pct": r["pct"], "required": need, "actual": actual, "na": r["na"], "optional": r["optional"],
                         "note": r["note"], "ok": skip or actual >= need}
        if not skip and actual < need:
            soft.append("категория %s: %d < %d (%d %% от %d)" % (c, actual, need, r["pct"], min_n))
    cls = Counter(p.get("evidence_class") for p in good)
    ab = (cls.get("A", 0) + cls.get("B", 0)) / total if total else 0.0
    if total and ab < AB_MIN_SHARE:
        soft.append("доля классов A+B %.0f %% < %.0f %%" % (ab * 100, AB_MIN_SHARE * 100))
    split = evidence_split(good, cfg)
    if total and split["ab_external"] < AB_EXTERNAL_MIN_SHARE:
        warnings.append("внешних A+B (конкуренты, сообщества, внешние источники) %.0f %% < %.0f %% — рыночные предложения "
                        "опираются в основном на код продукта; внутренних A+B %.0f %%"
                        % (split["ab_external"] * 100, AB_EXTERNAL_MIN_SHARE * 100, split["ab_internal"] * 100))
    hz = Counter(p.get("horizon") for p in good)
    return {"ok": not errors, "date": date.today().isoformat(), "demo": demo, "total": total, "min": min_n,
            "profile": strat.get("profile") or "standard",
            "categories_na": sorted(na), "by_category": dict(cnt), "category_minimums": cat_report,
            "evidence_classes": {k: cls.get(k, 0) for k in "ABCD"}, "ab_share": round(ab, 4),
            "ab_external_share": split["ab_external"], "ab_internal_share": split["ab_internal"],
            "evidence_sides": split["evidence_sides"],
            "by_horizon": {k: hz.get(k, 0) for k in HORIZONS}, "errors": errors, "warnings": warnings}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Проверка реестра предложений (data/proposals.json).")
    ap.add_argument("out", help="папка прогона <OUT>")
    ap.add_argument("--min", type=int, default=None, help="минимум предложений (иначе из run-config или 100)")
    ap.add_argument("--demo", action="store_true", help="демо-режим: заглушки URL разрешены, минимумы — предупреждения")
    ap.add_argument("--quiet", action="store_true", help="не печатать предупреждения")
    a = ap.parse_args(argv)
    out_dir = Path(a.out).resolve()
    rep = run_check(out_dir, a.min, a.demo)
    (out_dir / "data").mkdir(parents=True, exist_ok=True)
    (out_dir / "data" / "registry-check.json").write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Предложений: %d (минимум %d)%s; A+B: %.0f %% (внешние %.0f %%, внутренние %.0f %%)"
          % (rep["total"], rep["min"], " [демо]" if a.demo else "", rep["ab_share"] * 100, rep["ab_external_share"] * 100,
             rep["ab_internal_share"] * 100))
    print("По категориям: " + ", ".join("%s %d/%d%s" % (c, v["actual"], v["required"],
                                                       " н/п" if v["na"] else (" по запросу" if v.get("optional") else ""))
                                        for c, v in rep["category_minimums"].items()))
    print("Классы: " + ", ".join("%s %d" % kv for kv in rep["evidence_classes"].items())
          + "; горизонты: " + ", ".join("%s %d" % kv for kv in rep["by_horizon"].items()))
    if rep["warnings"] and not a.quiet:
        print("Предупреждения (%d):" % len(rep["warnings"]))
        for w in rep["warnings"][:60]:
            print("  - " + w)
    if rep["errors"]:
        print("Ошибки (%d):" % len(rep["errors"]))
        for e in rep["errors"][:100]:
            print("  - " + e)
        print("FAIL")
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
