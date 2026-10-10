#!/usr/bin/env python3
"""Сборка <OUT>/build/deck.json — колоды для build_pptx.mjs и deck_pdf.mjs.

Основная часть (цель 40–60 слайдов): титул, KPI-плитки, оглавление, нарратив из research/strategy.md
(раздел «## N. …» → слайд-тезисы, встроенные ![[chart:…]] / ![[mockup:…]] / ![[ref:…]] → слайды-картинки),
топ-30 предложений слайдами-карточками, план (Гант). Приложение: остальные графики и макеты, остаток
реестра и источники таблицами, конкуренты, вопросы владельцу. Источники и полный текст — в notes.

  build_deck_json.py <OUT> [--main-max 60] [--top 30]

Формат deck.json:
  {"meta": {"title", "subtitle", "product", "author", "copyright", "date", "footer", "theme": {bg, surface, text, muted,
            accent, accent2, border, font}, "counts": {...}},
   "slides": [{"type": "title|section|bullets|image|stats|table|card", "title", "subtitle"?, "section"?, "appendix": bool,
               "bullets"?: [str], "image"?: "путь от <OUT>", "caption"?, "stats"?: [{"value", "label"}],
               "columns"?: [str], "rows"?: [[str]], "colW"?: [дюймы], "card"?: {...}, "notes"?: str, "sources"?: [url]}]}
Пути картинок — относительно <OUT>; SVG допускается (build_pptx растрирует его через Chromium, если может).
Только стандартная библиотека; схемы входов — references/data-contract.md.
"""
import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

CATS = {"product": "Продукт", "acquisition": "Привлечение", "conversion": "Конверсия", "retention": "Удержание",
        "monetization": "Монетизация", "analytics": "Аналитика", "partnerships": "Партнёрства",
        "localization": "Локализация", "new_lines": "Новые линии", "platform": "Платформа"}
HORIZONS = {"now": "Сейчас (0–3 мес)", "next": "Дальше (3–12 мес)", "later": "Позже (1–2 года)", "vision": "Видение (2+ года)"}
DEFAULT_THEME = {"bg": "FFFFFF", "surface": "F3F5F8", "text": "1F2933", "muted": "5F6B7A", "accent": "2563EB",
                 "accent2": "D97706", "border": "D5DBE3", "font": "Calibri"}
URL_RE = re.compile(r"https?://[^\s\"'<>)\]]+")
EMBED_RE = re.compile(r"^!\[\[(chart|mockup|ref):([^\]]+)\]\]\s*$")
BULLETS_PER_SLIDE = 6
BULLET_MAX = 190


# ---------------------------------------------------------------- утилиты
def load_json(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default
    except (OSError, json.JSONDecodeError) as e:
        print("предупреждение: не удалось прочитать %s: %s" % (path, e), file=sys.stderr)
        return default


def short(text, limit=BULLET_MAX):
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0].rstrip(",;:—-")
    return cut + "…"


def md_inline(text):
    """Markdown-строка → простой текст; ссылки собираются отдельно."""
    t = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)
    t = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r"\1", t)
    t = re.sub(r"[*_]{2}([^*_]+)[*_]{2}", r"\1", t)
    t = re.sub(r"`([^`]*)`", r"\1", t)
    t = re.sub(r"<[^>]+>", "", t)
    return t.strip()


def first_sentences(text, limit=BULLET_MAX):
    parts = re.split(r"(?<=[.!?…])\s+(?=[A-ZА-ЯЁ0-9«\"(\[])", text)
    acc = ""
    for p in parts:
        if acc and len(acc) + len(p) + 1 > limit:
            break
        acc = (acc + " " + p).strip()
    return short(acc or text, limit)


def hex6(value):
    """CSS-цвет (#rgb, #rrggbb, rgb()/rgba()) → RRGGBB или None."""
    v = (value or "").strip().lower()
    m = re.fullmatch(r"#([0-9a-f]{3})", v)
    if m:
        return "".join(c * 2 for c in m.group(1)).upper()
    m = re.fullmatch(r"#([0-9a-f]{6})(?:[0-9a-f]{2})?", v)
    if m:
        return m.group(1).upper()
    m = re.fullmatch(r"rgba?\(\s*(\d+)[ ,]+(\d+)[ ,]+(\d+).*\)", v)
    if m:
        return "".join("%02X" % min(255, int(x)) for x in m.groups())
    return None


def luminance(h):
    def ch(x):
        c = int(x, 16) / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * ch(h[0:2]) + 0.7152 * ch(h[2:4]) + 0.0722 * ch(h[4:6])


def contrast(a, b):
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def theme_from_tokens(path):
    """Тема из mockups/tokens.css: угадываем роли по именам CSS-переменных; проверяем контраст."""
    theme = dict(DEFAULT_THEME)
    try:
        css = Path(path).read_text(encoding="utf-8")
    except OSError:
        return theme, "по умолчанию"
    var = {k.lower(): v.strip() for k, v in re.findall(r"--([\w-]+)\s*:\s*([^;}]+)", css)}
    roles = {"bg": ["bg", "background", "color-bg", "page", "base"], "surface": ["surface", "card", "panel", "bg-2", "bg2", "elevated"],
             "text": ["text", "fg", "foreground", "ink", "color-text", "body"], "muted": ["muted", "text-muted", "secondary", "subtle"],
             "accent": ["accent", "primary", "brand", "gold", "link"], "accent2": ["accent-2", "accent2", "secondary-accent", "success", "warning"],
             "border": ["border", "line", "divider", "stroke"]}
    found = False
    for role, names in roles.items():
        for n in names:
            hit = next((hex6(v) for k, v in var.items() if (k == n or k.endswith("-" + n) or k.startswith(n + "-")) and hex6(v)), None)
            if hit:
                theme[role] = hit
                found = True
                break
    fnt = next((v for k, v in var.items() if "font" in k and "size" not in k and "weight" not in k), None)
    if fnt:
        first = fnt.split(",")[0].strip().strip("'\"")
        if first and not first.startswith("var(") and first not in ("system-ui", "-apple-system", "sans-serif", "inherit"):
            theme["font"] = first
    if contrast(theme["text"], theme["bg"]) < 4.5:  # читаемость важнее точного совпадения с токенами
        theme["text"] = "111111" if luminance(theme["bg"]) > 0.4 else "F5F5F5"
    if contrast(theme["muted"], theme["bg"]) < 3:
        theme["muted"] = "555555" if luminance(theme["bg"]) > 0.4 else "BBBBBB"
    return theme, ("mockups/tokens.css" if found else "по умолчанию")


# ---------------------------------------------------------------- нарратив
def parse_strategy(md):
    """research/strategy.md → [{num, title, items: [(kind, payload)]}]; kind: bullet|embed|table|text."""
    sections, cur = [], None
    lines = md.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        m = re.match(r"^##\s+(?:(\d+)[.)]\s*)?(.+?)\s*$", line)
        if m and not line.startswith("###"):
            cur = {"num": m.group(1), "title": md_inline(m.group(2)), "items": [], "raw": []}
            sections.append(cur)
            i += 1
            continue
        if cur is None:
            i += 1
            continue
        cur["raw"].append(line)
        em = EMBED_RE.match(line.strip())
        if em:
            cur["items"].append(("embed", (em.group(1), em.group(2).strip())))
        elif line.strip().startswith("|"):
            block = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                block.append(lines[i].strip())
                cur["raw"].append(lines[i])
                i += 1
            rows = [[md_inline(c) for c in r.strip("|").split("|")] for r in block if not re.fullmatch(r"\|[\s:|-]+\|", r)]
            if rows:
                cur["items"].append(("table", rows))
            continue
        elif re.match(r"^\s*(?:[-*+]|\d+[.)])\s+", line):
            cur["items"].append(("bullet", md_inline(re.sub(r"^\s*(?:[-*+]|\d+[.)])\s+", "", line))))
        elif line.startswith("###"):
            cur["items"].append(("bullet", md_inline(line.lstrip("#").strip()) + ":"))
        elif line.strip() and not line.startswith("#") and not line.startswith(">"):
            cur["items"].append(("text", md_inline(line)))
        elif line.startswith(">"):
            cur["items"].append(("text", md_inline(line.lstrip("> "))))
        i += 1
    return sections


def theses(items):
    out = []
    for kind, val in items:
        if kind == "bullet" and val:
            out.append(short(val))
        elif kind == "text" and val:
            out.append(first_sentences(val))
    # подзаголовок «X:» без продолжения не нужен в конце
    while out and out[-1].endswith(":"):
        out.pop()
    return out


# ---------------------------------------------------------------- данные
def rank_proposals(props, scores):
    """Порядок по scores.json; без него — предварительный (value·confidence / (cost·risk))."""
    if scores:
        return sorted(props, key=lambda p: (scores.get(p.get("id"), {}).get("rank") or 10 ** 6, str(p.get("id")))), True

    def pre(p):
        s = p.get("scores") or {}
        num = lambda k, d: s.get(k) if isinstance(s.get(k), (int, float)) else d
        return -(num("value", 3) * num("confidence", 3) / max(num("cost", 3) * num("risk", 2), 1))
    return sorted(props, key=lambda p: (pre(p), str(p.get("id")))), False


def fmt_num(v, nd=2):
    if isinstance(v, bool) or v is None:
        return "—" if v is None else str(v)
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        return ("%." + str(nd) + "f") % v
    return str(v)


def card_for(p, s, rank, out, mockups):
    sc = p.get("scores") or {}
    ed = p.get("effort_days") or []
    cm = p.get("cost_money") or {}
    risks = p.get("risks") or {}
    kpis = p.get("effect_kpi") or []
    if isinstance(kpis, str):
        kpis = [{"kpi": kpis}]
    metrics = [["Ценность", sc.get("value")], ["Стоимость", sc.get("cost")], ["Риск", sc.get("risk")], ["Уверенность", sc.get("confidence")]]
    if s:
        metrics += [["RICE", s.get("rice")], ["Composite", s.get("composite")]]
    else:
        metrics += [["Охват", sc.get("reach", sc.get("value"))], ["Влияние", sc.get("impact", sc.get("value"))]]
    mock = None
    for m in mockups:
        if p.get("id") in (m.get("proposals") or []) and m.get("png") and (out / m["png"]).exists():
            mock = m["png"]
            break
    return {
        "id": p.get("id"), "rank": rank, "title": p.get("title", ""), "category": CATS.get(p.get("category"), p.get("category") or ""),
        "segment": p.get("segment") or "", "description": p.get("description") or "", "rationale": p.get("rationale") or "",
        "current_feature": p.get("current_feature") or "", "cheap_test": p.get("cheap_test") or "",
        "kpi": ["%s %s %s [%s]" % (k.get("kpi", ""), {"up": "↑", "down": "↓"}.get(k.get("direction"), ""), k.get("range", ""), k.get("label", "")) for k in kpis],
        "steps": ["%s — %s" % (st.get("what", ""), st.get("where", "")) if st.get("where") else st.get("what", "") for st in (p.get("steps") or [])],
        "risks": " · ".join("%s %s" % (k, v) for k, v in risks.items() if k != "note" and isinstance(v, (int, float))) + (" · " + risks["note"] if risks.get("note") else ""),
        "evidence_class": p.get("evidence_class") or "", "kano": p.get("kano") or "", "horizon": HORIZONS.get(p.get("horizon"), p.get("horizon") or ""),
        "effort": ("%s–%s чел.-дн." % (ed[0], ed[-1])) if ed else "", "cost": ("%s–%s %s" % (cm.get("min", 0), cm.get("max", 0), cm.get("currency", ""))) if cm else "",
        "priority": (s or {}).get("priority") or "", "quadrant": (s or {}).get("quadrant") or "", "labels": (s or {}).get("labels") or [],
        "metrics": [[lab, fmt_num(v)] for lab, v in metrics], "mockup": mock,
    }


def card_notes(p):
    lines = ["Обоснование: " + (p.get("rationale") or "")]
    for e in p.get("evidence") or []:
        loc = e.get("url") or e.get("file") or ""
        lines.append("Доказательство [%s, класс %s]: %s %s%s" % (e.get("kind", ""), p.get("evidence_class", ""), e.get("title", ""), loc,
                                                                (" — «%s»" % e["note"]) if e.get("note") else ""))
    for i, st in enumerate(p.get("steps") or [], 1):
        lines.append("Шаг %d: %s — %s: %s%s" % (i, st.get("what", ""), st.get("where", ""), st.get("how", ""), (" (%s)" % st["doc_url"]) if st.get("doc_url") else ""))
    if p.get("cheap_test"):
        lines.append("Дешёвая проверка: " + p["cheap_test"])
    if p.get("dependencies"):
        lines.append("Зависимости: " + ", ".join(p["dependencies"]))
    return "\n".join(lines)


def card_sources(p):
    urls = [e.get("url") for e in p.get("evidence") or [] if e.get("url")]
    urls += [st.get("doc_url") for st in p.get("steps") or [] if st.get("doc_url")]
    return list(dict.fromkeys(urls))


def image_path(out, rel):
    """Предпочесть PNG-двойник SVG, если он есть; None, если файла нет."""
    if not rel:
        return None
    p = out / rel
    if p.suffix.lower() == ".svg" and p.with_suffix(".png").exists():
        return str(Path(rel).with_suffix(".png"))
    return rel if p.exists() else None


def gantt_bar(s, e, months):
    return "".join("■" if s <= m <= e else "·" for m in range(1, months + 1))


# ---------------------------------------------------------------- сборка
def build(out, main_max=60, top_n=30):
    out = Path(out).resolve()
    props = load_json(out / "data" / "proposals.json", None)
    if not isinstance(props, list):
        print("ошибка: нет data/proposals.json в %s" % out, file=sys.stderr)
        return None
    cfg = load_json(out / "build" / "run-config.json", {})
    sl = load_json(out / "data" / "scores.json", [])
    scores = {s.get("id"): s for s in sl if isinstance(s, dict)} if isinstance(sl, list) else {}
    charts = [c for c in load_json(out / "charts" / "charts-index.json", []) or [] if isinstance(c, dict)]
    mockups = [m for m in load_json(out / "data" / "mockups-index.json", []) or [] if isinstance(m, dict)]
    sources = load_json(out / "data" / "sources.json", []) or []
    comps = load_json(out / "data" / "competitors.json", []) or []
    gantt = load_json(out / "data" / "gantt.json", []) or []
    md_path = out / "research" / "strategy.md"
    md = md_path.read_text(encoding="utf-8") if md_path.exists() else ""
    theme, theme_src = theme_from_tokens(out / "mockups" / "tokens.css")

    a = cfg.get("author") or {}
    author = ((a.get("name") or "") + (" (%s)" % a["nick"] if a.get("nick") else "")).strip()
    product = (cfg.get("product") or {}).get("name") or (cfg.get("repo") or {}).get("name") or "Продукт"
    st = cfg.get("strategy") or {}
    horizon = int(st.get("horizon_months") or 12)
    today = cfg.get("created") or date.today().isoformat()
    copyright_ = a.get("copyright") or ("© %s %s" % (today[:4], author) if author else "")
    footer = " · ".join(x for x in (product, "стратегия развития", today, copyright_ or author) if x)

    ranked, has_scores = rank_proposals(props, scores)
    chart_by_key = {c.get("key"): c for c in charts}
    mock_by_key = {m.get("key"): m for m in mockups}
    used_charts, used_mocks = set(), set()
    missing = []
    main, appendix = [], []

    def add(lst, slide, appendix_flag):
        slide["appendix"] = appendix_flag
        lst.append(slide)

    def embed_slide(kind, key):
        if kind == "chart":
            c = chart_by_key.get(key)
            img = image_path(out, c.get("svg")) if c else None
            if not img:
                missing.append("chart:" + key)
                return None
            used_charts.add(key)
            return {"type": "image", "title": c.get("title") or key, "image": img, "caption": c.get("caption") or "",
                    "notes": "График %s (charts/charts-index.json). %s" % (key, c.get("caption") or "")}
        if kind == "mockup":
            m = mock_by_key.get(key)
            img = image_path(out, m.get("png")) if m else None
            if not img:
                missing.append("mockup:" + key)
                return None
            used_mocks.add(key)
            return {"type": "image", "title": "Концепт: " + (m.get("title") or key), "image": img,
                    "caption": "Концепт, не существующая функция · %s · предложения: %s" % (key, ", ".join(m.get("proposals") or [])),
                    "notes": "Макет %s (%s)." % (key, m.get("html") or "")}
        ref = load_json(out / "design-refs" / ("%s.json" % key), {})
        img = image_path(out, ref.get("png") or "design-refs/%s.png" % key)
        if not img:
            missing.append("ref:" + key)
            return None
        return {"type": "image", "title": "Референс: " + (ref.get("title") or key), "image": img,
                "caption": "Референс дизайна %s · предложения: %s" % (key, ", ".join(ref.get("proposals") or [])),
                "notes": (ref.get("summary") or "") + ("\nДоделать: " + "; ".join(ref.get("todo") or []) if ref.get("todo") else "")}

    # --- титул, KPI, оглавление
    add(main, {"type": "title", "title": "Стратегия развития %s" % product,
               "subtitle": " · ".join(x for x in (st.get("goal"), "горизонт %d мес." % horizon, today, author) if x),
               "notes": "Авторство: %s. Собрано product-strategy." % (copyright_ or author)}, False)
    classes = [p.get("evidence_class") for p in props]
    ab = (sum(1 for c in classes if c in ("A", "B")) / len(classes) * 100) if classes else 0
    p0 = sum(1 for s in scores.values() if s.get("priority") == "P0")
    stats = [{"value": str(len(props)), "label": "предложений в реестре"}, {"value": "%d%%" % round(ab), "label": "доказательств классов A/B"},
             {"value": str(len([c for c in comps if not c.get("self")])), "label": "конкурентов изучено"},
             {"value": str(len(sources)), "label": "источников с датой проверки"}]
    if p0:
        stats.insert(1, {"value": str(p0), "label": "предложений P0"})
    stats.append({"value": str(horizon), "label": "месяцев — горизонт плана"})
    bets = [p.get("id") + " — " + short(p.get("title"), 80) for p in ranked[:3]]
    add(main, {"type": "stats", "title": "Ключевые цифры", "stats": stats[:6],
               "bullets": ["Ставка %d: %s" % (i, b) for i, b in enumerate(bets, 1)],
               "notes": "Ставки — первые три предложения по %s." % ("рангу scores.json" if has_scores else "предварительному рангу (scores.json нет)")}, False)
    sections = parse_strategy(md)
    if sections:
        add(main, {"type": "bullets", "title": "Содержание",
                   "bullets": [short(("%s. " % s["num"] if s["num"] else "") + s["title"], 90) for s in sections][:14],
                   "notes": "Разделы research/strategy.md."}, False)

    # --- нарратив: раздел → секция-тезисы (+ первая картинка); прочие картинки — в приложение
    narrative, extra_embeds = [], []
    for s in sections:
        th = theses(s["items"])
        urls = list(dict.fromkeys(URL_RE.findall("\n".join(s["raw"]))))
        notes = short("\n".join(x for x in s["raw"] if x.strip()), 3500)
        title = ("%s. " % s["num"] if s["num"] else "") + s["title"]
        slides_here = []
        tables = [t for kd, t in s["items"] if kd == "table" and len(t) >= 2]
        embeds = [v for kd, v in s["items"] if kd == "embed"]
        chunks = [th[i:i + BULLETS_PER_SLIDE] for i in range(0, len(th), BULLETS_PER_SLIDE)][:2]
        if not chunks and not tables:
            chunks = [["Подробности — в заметках к слайду и в веб-версии стратегии."]]
        for k, ch in enumerate(chunks):
            slides_here.append({"type": "bullets", "title": title + (" (продолжение)" if k else ""),
                                "bullets": ch, "notes": notes, "sources": urls})
        for t in tables[:1]:
            slides_here.append({"type": "table", "title": title, "columns": t[0], "rows": [r + [""] * (len(t[0]) - len(r)) for r in t[1:13]],
                                "notes": notes, "sources": urls})
        if slides_here:
            slides_here[0]["section"] = s["title"]
        for e_i, (kind, key) in enumerate(embeds):
            sl_ = embed_slide(kind, key)
            if sl_:
                (slides_here if e_i == 0 else extra_embeds).append(sl_)
        narrative.append(slides_here)

    # --- топ-N карточек
    top = ranked[:top_n]
    cards = [{"type": "section", "title": "Топ-%d предложений" % len(top), "section": "Топ-%d предложений" % len(top),
              "subtitle": "Ранг по %s; полный реестр — веб-версия и strategy.xlsx" % ("composite (score.py)" if has_scores else "предварительной оценке: scores.json ещё нет"),
              "notes": "Карточки: что сделать, почему, шаги, KPI, дешёвая проверка; источники — в заметках каждого слайда."}]
    for i, p in enumerate(top, 1):
        s = scores.get(p.get("id"))
        rank = (s or {}).get("rank") or i
        cards.append({"type": "card", "title": "#%s · %s · %s" % (rank, p.get("id"), short(p.get("title"), 80)),
                      "card": card_for(p, s, rank, out, mockups), "notes": card_notes(p), "sources": card_sources(p)})

    # --- план (Гант)
    plan = []
    gchart = next((c for c in charts if "gantt" in str(c.get("key", "")).lower() or c.get("section") == "plan"), None)
    if gchart and image_path(out, gchart.get("svg")):
        used_charts.add(gchart.get("key"))
        plan.append({"type": "image", "section": "План", "title": gchart.get("title") or "План действий (Гант)",
                     "image": image_path(out, gchart.get("svg")), "caption": gchart.get("caption") or "", "notes": "Данные — data/gantt.json."})
    elif gantt:
        months = max([horizon] + [int(g.get("end_month") or 0) for g in gantt if isinstance(g.get("end_month"), (int, float))])
        months = min(months, 36)
        g_sorted = sorted(gantt, key=lambda g: (g.get("start_month") or 0, g.get("end_month") or 0))
        for k in range(0, len(g_sorted), 12):
            chunk = g_sorted[k:k + 12]
            plan.append({"type": "table", "section": "План" if not k else None, "title": "План действий (Гант)" + (" — продолжение" if k else ""),
                         "columns": ["ID", "Фаза", "Задача", "Мес.", "Шкала, мес. 1–%d" % months, "Предложения"],
                         "rows": [[g.get("id", ""), g.get("phase", ""), short(g.get("task"), 60), "%s–%s" % (g.get("start_month"), g.get("end_month")),
                                   gantt_bar(int(g.get("start_month") or 0), int(g.get("end_month") or 0), months), ", ".join(g.get("proposal_ids") or [])]
                                  for g in chunk],
                         "colW": [0.6, 1.4, 3.6, 0.8, 4.0, 1.7], "fontSize": 9,
                         "notes": "\n".join("%s: %s — готово, когда: %s; ответственный: %s" % (g.get("id"), g.get("task"), g.get("done_criteria", ""), g.get("owner", "")) for g in chunk)})

    # --- бюджет основной части: при переборе картинки из нарратива уходят в приложение, затем сокращаются продолжения
    fixed = len(main) + len(cards) + len(plan) + (1 if narrative else 0)  # + слайд-раздел «Стратегия»

    def narrative_count():
        return sum(len(x) for x in narrative)
    for kind in ("image", "table", "cont"):
        if fixed + narrative_count() <= main_max:
            break
        for grp in narrative:
            for sl_ in list(grp):
                if fixed + narrative_count() <= main_max:
                    break
                if kind == "image" and sl_["type"] == "image":
                    grp.remove(sl_)
                    extra_embeds.append(sl_)
                elif kind == "table" and sl_["type"] == "table" and len(grp) > 1:
                    grp.remove(sl_)
                elif kind == "cont" and sl_["type"] == "bullets" and sl_["title"].endswith("(продолжение)"):
                    grp.remove(sl_)
    if narrative:
        add(main, {"type": "section", "title": "Стратегия", "section": "Стратегия", "subtitle": "Ключевые тезисы по разделам; полный текст — в заметках и веб-версии"}, False)
    for grp in narrative:
        for sl_ in grp:
            add(main, sl_, False)
    for sl_ in cards + plan:
        add(main, sl_, False)

    # --- приложение
    add(appendix, {"type": "section", "title": "Приложение", "section": "Приложение",
                   "subtitle": "Графики, макеты, остаток реестра, источники, конкуренты"}, True)
    for sl_ in extra_embeds:
        add(appendix, dict(sl_, section=None), True)
    for c in charts:
        if c.get("key") in used_charts:
            continue
        img = image_path(out, c.get("svg"))
        if img:
            add(appendix, {"type": "image", "title": c.get("title") or c.get("key"), "image": img, "caption": c.get("caption") or "",
                           "notes": "График %s, раздел %s." % (c.get("key"), c.get("section") or "—")}, True)
        else:
            missing.append("chart:" + str(c.get("key")))
    for m in mockups:
        if m.get("key") in used_mocks:
            continue
        img = image_path(out, m.get("png"))
        if img:
            add(appendix, {"type": "image", "title": ("Концепт: " if m.get("kind", "concept") == "concept" else "Текущее состояние: ") + (m.get("title") or m.get("key")),
                           "image": img, "caption": ("Концепт, не существующая функция" if m.get("kind", "concept") == "concept" else "Текущее состояние")
                           + " · предложения: " + ", ".join(m.get("proposals") or []), "notes": "Макет %s (%s)." % (m.get("key"), m.get("html") or "")}, True)
        else:
            missing.append("mockup:" + str(m.get("key")))
    rest = ranked[top_n:]
    for k in range(0, len(rest), 12):
        chunk = rest[k:k + 12]
        rows = []
        for i, p in enumerate(chunk, top_n + k + 1):
            s = scores.get(p.get("id")) or {}
            sc = p.get("scores") or {}
            rows.append([str(s.get("rank") or i), p.get("id", ""), short(p.get("title"), 70), CATS.get(p.get("category"), p.get("category") or ""),
                         p.get("evidence_class", ""), fmt_num(sc.get("value")), fmt_num(sc.get("cost")), fmt_num(sc.get("risk")),
                         fmt_num(sc.get("confidence")), fmt_num(s.get("composite"), 3) if s else "—", s.get("priority", "—") if s else "—"])
        add(appendix, {"type": "table", "title": "Реестр: предложения %s–%s" % (rows[0][0], rows[-1][0]),
                       "columns": ["#", "ID", "Название", "Категория", "Кл.", "Ценн.", "Стоим.", "Риск", "Увер.", "Composite", "Приор."],
                       "rows": rows, "colW": [0.5, 0.7, 4.6, 1.5, 0.5, 0.65, 0.7, 0.6, 0.65, 0.95, 0.75], "fontSize": 9,
                       "caption": "Полные карточки — веб-версия (фильтры и сортировка) и strategy.xlsx, лист «Реестр»",
                       "notes": "\n".join("%s: %s" % (p.get("id"), short(p.get("description"), 300)) for p in chunk),
                       "sources": [u for p in chunk for u in card_sources(p)][:60]}, True)
    real_comps = [c for c in comps if not c.get("self")]
    for k in range(0, len(real_comps), 10):
        chunk = real_comps[k:k + 10]
        add(appendix, {"type": "table", "title": "Конкуренты" + (" — продолжение" if k else ""),
                       "columns": ["Название", "Тип", "Цена", "Лучше нас", "Мы лучше", "Вердикт"],
                       "rows": [[c.get("name", ""), c.get("type", ""), short(c.get("price"), 30), short("; ".join(c.get("better_than_us") or []), 70),
                                 short("; ".join(c.get("we_better") or []), 70), short(c.get("verdict"), 90)] for c in chunk],
                       "colW": [1.8, 1.0, 1.2, 2.9, 2.9, 2.3], "fontSize": 9,
                       "sources": [u for c in chunk for u in ([c.get("url")] + (c.get("sources") or [])) if u]}, True)
    for k in range(0, len(sources), 14):
        chunk = sources[k:k + 14]
        add(appendix, {"type": "table", "title": "Источники %d–%d" % (k + 1, k + len(chunk)),
                       "columns": ["ID", "Название", "URL", "Статус", "Проверено"],
                       "rows": [[s.get("id", ""), short(s.get("title"), 60), short(s.get("url"), 80), str(s.get("status") if s.get("status") is not None else "—"),
                                 s.get("date_checked") or ""] for s in chunk],
                       "colW": [0.7, 3.9, 5.5, 0.9, 1.1], "fontSize": 8.5,
                       "sources": [s.get("url") for s in chunk if s.get("url")]}, True)
    q_path = out / "research" / "questions-owner.md"
    if q_path.exists():
        qs = [md_inline(re.sub(r"^\s*\d+[.)]\s+", "", ln)) for ln in q_path.read_text(encoding="utf-8").splitlines() if re.match(r"^\s*\d+[.)]\s+", ln)]
        if qs:
            add(appendix, {"type": "bullets", "title": "Вопросы владельцу", "bullets": [short(q, 160) for q in qs[:10]],
                           "notes": "Полный список с запросами данных — research/questions-owner.md"}, True)

    slides = [s for s in main + appendix]
    for s in slides:  # убрать пустые поля
        for k in [k for k, v in s.items() if v in (None, "", [])]:
            del s[k]
    deck = {"meta": {"title": "Стратегия развития %s" % product, "subtitle": st.get("goal") or "", "product": product, "author": author,
                     "copyright": copyright_, "date": today, "footer": footer, "theme": theme, "theme_source": theme_src,
                     "counts": {"main": len(main), "appendix": len(appendix), "cards": len(top), "missing_images": sorted(set(missing))}},
            "slides": slides}
    path = out / "build" / "deck.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(deck, ensure_ascii=False, indent=2), encoding="utf-8")
    return path, deck


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("out", help="папка прогона <OUT>")
    ap.add_argument("--main-max", type=int, default=60, help="предел слайдов основной части (по умолчанию 60)")
    ap.add_argument("--top", type=int, default=30, help="число карточек предложений (по умолчанию 30)")
    a = ap.parse_args(argv)
    res = build(a.out, a.main_max, a.top)
    if res is None:
        return 2
    path, deck = res
    c = deck["meta"]["counts"]
    print("deck.json: %s — слайдов %d (основная часть %d, приложение %d, карточек %d)" % (path, len(deck["slides"]), c["main"], c["appendix"], c["cards"]))
    if c["missing_images"]:
        print("нет файлов картинок (слайды пропущены): %s" % ", ".join(c["missing_images"][:20]), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
