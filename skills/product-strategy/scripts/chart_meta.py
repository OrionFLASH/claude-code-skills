#!/usr/bin/env python3
"""Метаданные пояснений интерактивных графиков (references/interactive-site.md, п. 2.1–2.2) → charts/<ключ>.meta.json.

Используется из charts.py: графики регистрируют каждый интерактивный элемент в Registry (id, подпись, вид, контекст
данных), затем build_meta() собирает пояснения по приоритету:
  (1) data/chart-notes.json  {ключ: {id: {title, summary, meaning, actions, metrics, links}}, "_chart": {howto, legend}}
  (2) данные прогона         предложение (description, rationale, steps, effect_kpi, оценки, зависимости, горизонт),
                             модель (сценарии, допущения), Гант, конкуренты, запросы, события — то, что передал график
  (3) глоссарий              references/chart-glossary.ru.json (стадии AARRR, квадранты, классы доказательств, …)
Ничего не выдумывается: нет текста — поле пустое и предупреждение «пояснение не задано: <график>/<элемент>».

check_meta(out_dir) — проверка сборщика: каждый data-ps-el имеет запись в meta.elements и наоборот, id уникальны,
атрибуты доступности на месте, у графика есть howto и legend, все ссылки разрешаются (#s1…#s17, #p/<P-id>,
#registry?…, #chart/<ключ>/<id>, #competitor/<slug>, #gantt/<G-id>, #kanban/<P-id>, #flow/<ключ>, #mockup/<ключ>).
Только стандартная библиотека.
"""
import json
import re
import xml.etree.ElementTree as ET
from collections import OrderedDict
from pathlib import Path

HERE = Path(__file__).resolve().parent
GLOSSARY = HERE.parent / "references" / "chart-glossary.ru.json"
NOTES = "data/chart-notes.json"
KINDS = {"stage", "point", "bar", "node", "cell", "event", "link", "legend", "axis", "area", "line", "row", "column", "shape"}
REG_FILTERS = {"category", "horizon", "class", "quadrant", "priority"}
TEXT_FIELDS = ("title", "summary", "meaning")
MAX_ACTIONS, MAX_LINKS, MAX_METRICS = 4, 9, 12
SVG_NS = "{http://www.w3.org/2000/svg}"


def sid(s, fallback="x"):
    """Безопасный id элемента: латиница, цифры, «_», «-», «.»; пусто → fallback."""
    out = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(s or "")).strip("-")
    return out or fallback


def fmt(x, nd=0):
    if x is None:
        return "—"
    s = "{:,.{}f}".format(x, nd) if nd else "{:,.0f}".format(x)
    return s.replace(",", " ").replace(".", ",")


# ---------------------------------------------------------------- реестр элементов (заполняют графики)
class Registry:
    """Интерактивные элементы текущего графика: id → {label, kind, info, highlight}."""

    def __init__(self):
        self.reset(None)

    def reset(self, key):
        self.key = key
        self.variant = None          # ключ глоссария, если отличается (cac-ltv-solo, payback-solo)
        self.els = OrderedDict()

    def add(self, eid, label, kind, info=None, highlight=None):
        base = sid(eid)
        eid, k = base, 2
        while eid in self.els:
            eid, k = "%s-%d" % (base, k), k + 1
        self.els[eid] = {"label": str(label), "kind": kind if kind in KINDS else "shape", "info": dict(info or {}),
                         "highlight": highlight}
        return eid


# ---------------------------------------------------------------- глоссарий и заметки
def load_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def load_glossary(path=GLOSSARY):
    g = load_json(path)
    return g if isinstance(g, dict) else {}


def gfind(gl, path):
    cur = gl
    for p in path:
        if not isinstance(cur, dict) or p not in cur:
            return None
        cur = cur[p]
    return cur if isinstance(cur, dict) else None


def as_text(v):
    return v.strip() if isinstance(v, str) else ""


def str_list(v):
    return [as_text(x) for x in (v if isinstance(v, list) else []) if as_text(x)]


# ---------------------------------------------------------------- контекст прогона
class Context:
    """Данные прогона для пояснений и проверки ссылок."""

    def __init__(self, out_dir, D, glossary=None, notes=None):
        self.out = Path(out_dir)
        self.gl = glossary if glossary is not None else load_glossary()
        cfg = D.get("cfg") or {}
        self.concept = isinstance(cfg, dict) and cfg.get("mode") == "concept"
        self.sections = self.gl.get("sections_concept" if self.concept else "sections") or self.gl.get("sections") or {}
        P = D.get("P") if isinstance(D.get("P"), list) else []
        self.props = OrderedDict((p["id"], p) for p in P if isinstance(p, dict) and p.get("id"))
        self.scores = {r["id"]: r for r in D.get("S") or [] if isinstance(r, dict) and r.get("id")}
        G = D.get("G") if isinstance(D.get("G"), list) else []
        self.gantt = OrderedDict((str(g["id"]), g) for g in G if isinstance(g, dict) and g.get("id"))
        self.gantt_by_pid = {}
        for gid, g in self.gantt.items():
            for pid in g.get("proposal_ids") or []:
                self.gantt_by_pid.setdefault(pid, []).append(gid)
        C = D.get("C") if isinstance(D.get("C"), list) else []
        self.competitors = {str(x["slug"]): x for x in C if isinstance(x, dict) and x.get("slug")}
        kb = load_json(self.out / "data" / "kanban.json")
        self.kanban = {str(c.get("id")) for c in (kb.get("cards") if isinstance(kb, dict) else []) or [] if isinstance(c, dict) and c.get("id")}
        mi = load_json(self.out / "data" / "mockups-index.json")
        self.mockups = {}
        for m in mi if isinstance(mi, list) else []:
            if isinstance(m, dict) and m.get("key"):
                self.mockups[str(m["key"])] = m
        fl = load_json(self.out / "data" / "flows.json")
        self.flows = {str(f["key"]) for f in fl if isinstance(f, dict) and f.get("key")} if isinstance(fl, list) else set()
        self.notes = notes if isinstance(notes, dict) else {}
        self.available = {}          # {ключ графика: set(id элементов)} — для глубоких ссылок между графиками
        self.warnings = []

    # ---- ссылки
    def sec(self, n):
        try:
            n = int(n)
        except (TypeError, ValueError):
            return None
        if not 1 <= n <= 17:
            return None
        name = self.sections.get(str(n), "")
        return {"label": "Раздел %d. %s" % (n, name) if name else "Раздел %d" % n, "href": "#s%d" % n}

    def cat_section(self, cat):
        return (self.gl.get("category_sections") or {}).get(cat)

    def topic_section(self, topic):
        return (self.gl.get("topic_sections") or {}).get(topic)

    def p_link(self, pid, prefix=""):
        p = self.props.get(pid)
        if not p:
            return None
        return {"label": "%s%s — %s" % (prefix, pid, as_text(p.get("title"))), "href": "#p/%s" % pid}

    def reg_link(self, **flt):
        flt = {k: v for k, v in flt.items() if k in REG_FILTERS and v not in (None, "")}
        if not flt:
            return None
        names = {"category": "категория", "horizon": "горизонт", "class": "класс доказательств", "quadrant": "квадрант", "priority": "приоритет"}
        lab = ", ".join("%s «%s»" % (names[k], self.filter_label(k, v)) for k, v in flt.items())
        return {"label": "Показать в реестре: " + lab, "href": "#registry?" + "&".join("%s=%s" % kv for kv in flt.items())}

    def filter_label(self, k, v):
        if k == "category":
            return (gfind(self.gl, ["categories", v]) or {}).get("title", v)
        if k == "horizon":
            return (gfind(self.gl, ["horizons", v]) or {}).get("title", v)
        if k == "quadrant":
            return (gfind(self.gl, ["quadrants", v]) or {}).get("title", v)
        return v

    def valid_href(self, href, own=None):
        """Цель ссылки существует? own — {ключ: ids} текущей сборки (для #chart/…)."""
        h = as_text(href)
        avail = own if own is not None else self.available
        m = re.fullmatch(r"#s(\d+)", h)
        if m:
            return 1 <= int(m.group(1)) <= 17
        m = re.fullmatch(r"#p/(P\d+)", h)
        if m:
            return m.group(1) in self.props
        m = re.fullmatch(r"#registry(?:\?(.*))?", h)
        if m:
            if not m.group(1):
                return True
            pairs = [x.split("=", 1) for x in m.group(1).split("&")]
            return all(len(p) == 2 and p[0] in REG_FILTERS and p[1] for p in pairs)
        m = re.fullmatch(r"#chart/([\w-]+)(?:/(.+))?", h)
        if m:
            ids = avail.get(m.group(1))
            return ids is not None and (m.group(2) is None or m.group(2) in ids)
        m = re.fullmatch(r"#competitor/(.+)", h)
        if m:
            return m.group(1) in self.competitors
        m = re.fullmatch(r"#gantt/(.+)", h)
        if m:
            return m.group(1) in self.gantt
        m = re.fullmatch(r"#kanban/(.+)", h)
        if m:
            return m.group(1) in self.kanban
        m = re.fullmatch(r"#flow/(.+)", h)
        if m:
            return m.group(1) in self.flows
        m = re.fullmatch(r"#mockup/(.+)", h)
        if m:
            return m.group(1) in self.mockups
        return False

    def mockup_for(self, pid):
        p = self.props.get(pid) or {}
        ref = as_text(p.get("mockup"))
        for k, m in self.mockups.items():
            html = as_text(m.get("html"))
            if (ref and (html.endswith(ref) or ref.endswith(k + ".html"))) or pid in (m.get("proposals") or []):
                return k
        return None


# ---------------------------------------------------------------- сборка пояснения элемента
def gloss_entry(ctx, paths):
    """Первая найденная запись глоссария; в режиме идеи поверх неё — подблок concept."""
    for path in paths or []:
        e = gfind(ctx.gl, path)
        if e:
            e = dict(e)
            if ctx.concept and isinstance(e.get("concept"), dict):
                e.update(e["concept"])
            return e
    return None


def score_metrics(s, ctx):
    out = []
    if not s:
        return out
    if s.get("rank") is not None:
        out.append({"label": "Ранг по composite", "value": str(s["rank"]), "tag": "расчёт"})
    if s.get("composite") is not None:
        out.append({"label": "Composite", "value": fmt(s["composite"], 3), "tag": "расчёт"})
    pr = [x for x in (s.get("priority"), (gfind(ctx.gl, ["quadrants", s.get("quadrant")]) or {}).get("title")) if x]
    if pr:
        out.append({"label": "Приоритет и квадрант", "value": " · ".join(pr), "tag": "расчёт"})
    for k, lab in (("value_index", "Ценность (1–5)"), ("cost_index", "Стоимость (1–5)"), ("risk_index", "Риск (1–5)")):
        if s.get(k) is not None:
            out.append({"label": lab, "value": fmt(s[k], 1), "tag": "оценка"})
    if s.get("confidence_calc") is not None:
        out.append({"label": "Уверенность (0–1)", "value": fmt(s["confidence_calc"], 2), "tag": "расчёт"})
    return out


def proposal_parts(ctx, pid):
    """(summary, rationale, actions, metrics, links) предложения — только из данных прогона."""
    p = ctx.props.get(pid) or {}
    s = ctx.scores.get(pid) or {}
    summary = as_text(p.get("description")) or as_text(s.get("title"))
    rationale = as_text(p.get("rationale"))
    actions = []
    for st in p.get("steps") or []:
        if isinstance(st, dict):
            what, how, where = as_text(st.get("what")), as_text(st.get("how")), as_text(st.get("where"))
            txt = what + (": " + how if how else "") + (" (" + where + ")" if where else "")
            if txt:
                actions.append(txt)
        elif as_text(st):
            actions.append(as_text(st))
    actions = actions[:MAX_ACTIONS - 1] if as_text(p.get("cheap_test")) else actions[:MAX_ACTIONS]
    if as_text(p.get("cheap_test")):
        actions.append("Дешёвая проверка: " + as_text(p["cheap_test"]))
    metrics = score_metrics(s, ctx)
    ed = p.get("effort_days")
    if isinstance(ed, list) and len(ed) == 2 and all(isinstance(x, (int, float)) for x in ed):
        metrics.append({"label": "Трудозатраты", "value": "%s–%s чел.-дн." % (fmt(ed[0]), fmt(ed[1])), "tag": "оценка"})
    hz = gfind(ctx.gl, ["horizons", p.get("horizon")])
    if hz:
        metrics.append({"label": "Горизонт", "value": hz["title"], "tag": "план"})
    if p.get("evidence_class"):
        metrics.append({"label": "Класс доказательств", "value": str(p["evidence_class"]), "tag": "оценка"})
    for kp in p.get("effect_kpi") or []:
        if isinstance(kp, dict) and as_text(kp.get("kpi")):
            arrow = {"up": "↑ ", "down": "↓ "}.get(kp.get("direction"), "")
            metrics.append({"label": "Эффект: " + as_text(kp["kpi"]), "value": (arrow + as_text(kp.get("range"))).strip() or "—",
                            "tag": as_text(kp.get("label")) or "оценка"})
    links = [ctx.p_link(pid)]
    cat = p.get("category") or s.get("category")
    links.append(ctx.sec(ctx.cat_section(cat)))
    links.append(ctx.reg_link(category=cat))
    for d in (p.get("dependencies") or [])[:3]:
        links.append(ctx.p_link(d, "Предпосылка: "))
    for d in (s.get("unlocks") or [])[:2]:
        links.append(ctx.p_link(d, "Открывает: "))
    for gid in ctx.gantt_by_pid.get(pid, [])[:2]:
        links.append({"label": "План: %s — %s" % (gid, as_text(ctx.gantt[gid].get("task"))), "href": "#gantt/%s" % gid})
    if pid in ctx.kanban:
        links.append({"label": "Карточка на доске Kanban", "href": "#kanban/%s" % pid})
    mk = ctx.mockup_for(pid)
    if mk:
        links.append({"label": "Макет: " + (as_text(ctx.mockups[mk].get("title")) or mk), "href": "#mockup/%s" % mk})
    return summary, rationale, actions, metrics, [l for l in links if l]


def join_text(*parts):
    out = []
    for x in parts:
        x = as_text(x)
        if x and x not in out:
            out.append(x if x[-1] in ".!?…»)" else x + ".")
    return " ".join(out)


def dedupe(items, keyf):
    seen, out = set(), []
    for x in items:
        k = keyf(x)
        if k and k not in seen:
            seen.add(k)
            out.append(x)
    return out


def compose(key, eid, el, ctx, own, chart_secs=()):
    """Пояснение одного элемента: заметки → данные → глоссарий. Возвращает (meta, generic).
    Заголовок: info.title → заголовок записи глоссария (кроме общих терминов terms.*) → aria-label элемента."""
    info, kind, label = el["info"], el["kind"], el["label"]
    g = gloss_entry(ctx, info.get("gloss")) or {}
    pid = info.get("pid")
    used_data = False
    gpaths = info.get("gloss") or []
    gtitle = as_text(g.get("title")) if g and gpaths and gpaths[0][0] != "terms" else ""
    m = OrderedDict([("title", as_text(info.get("title")) or gtitle or label), ("kind", kind), ("summary", ""), ("meaning", ""),
                     ("actions", []), ("metrics", []), ("links", [])])
    d_summary, d_meaning = as_text(info.get("summary")), as_text(info.get("meaning"))
    d_actions, d_metrics, d_links = list(info.get("actions") or []), list(info.get("metrics") or []), list(info.get("links") or [])
    if pid and pid in ctx.props:
        ps, why, pa, pm, pl = proposal_parts(ctx, pid)
        m["title"] = "%s — %s" % (pid, as_text(ctx.props[pid].get("title")))
        d_summary = d_summary or ps
        d_meaning = join_text(d_meaning, ("Почему: " + why) if why else "")
        d_actions = d_actions + pa
        d_metrics = d_metrics + pm
        d_links = pl + d_links
        for other, oid in (("effort-impact", pid), ("critical-path", pid)):
            if other != key and oid in (own.get(other) or ()):
                d_links.append({"label": "Это предложение на графике «%s»" % CHART_NAMES.get(other, other), "href": "#chart/%s/%s" % (other, oid)})
    if d_summary or d_meaning or d_actions or d_metrics:
        used_data = True
    m["summary"] = d_summary or as_text(g.get("summary"))
    # определение из глоссария дополняет «что значит», если «что это» уже взято из данных
    m["meaning"] = join_text(d_meaning, g.get("meaning") or (g.get("summary") if d_summary and not pid else ""))
    rel = [r for r in info.get("related") or [] if r in ctx.props][:3]
    if rel and not pid:
        p0 = ctx.props[rel[0]]
        d_actions.append("Начните с %s «%s» — лучшего по рангу здесь." % (rel[0], as_text(p0.get("title"))))
        used_data = True
    acts = dedupe([as_text(a) for a in d_actions] + str_list(g.get("actions")), lambda a: a)
    m["actions"] = acts[:MAX_ACTIONS]
    m["metrics"] = [x for x in d_metrics if isinstance(x, dict) and as_text(x.get("label"))][:MAX_METRICS]
    links = list(d_links)
    for r in rel:
        links.append(ctx.p_link(r))
    for r in info.get("plinks") or []:
        links.append(ctx.p_link(r))
    if info.get("cat"):
        links.append(ctx.sec(ctx.cat_section(info["cat"])))
        links.append(ctx.reg_link(category=info["cat"]))
    secs = info.get("section")
    for n in (secs if isinstance(secs, list) else [secs]) + [g.get("section")]:   # noqa: B007
        if n:
            links.append(ctx.sec(n))
    if info.get("registry"):
        links.append(ctx.reg_link(**info["registry"]))
    for x in info.get("deep") or []:      # (ключ, id, подпись) — глубокие ссылки на элементы других графиков
        if x[1] in (own.get(x[0]) or ()):
            links.append({"label": x[2], "href": "#chart/%s/%s" % (x[0], x[1])})
    links = [l for l in links if l]
    if not links:                          # нет своих ссылок — разделы стратегии, где уместен график
        links = [ctx.sec(n) for n in chart_secs if ctx.sec(n)]
    good = []
    for l in links:
        if ctx.valid_href(l.get("href"), own):
            good.append({"label": as_text(l.get("label")) or l["href"], "href": l["href"]})
        else:
            ctx.warnings.append("ссылка без цели пропущена: %s/%s → %s" % (key, eid, l.get("href")))
    m["links"] = dedupe(good, lambda l: l["href"])[:MAX_LINKS]
    if el.get("highlight"):
        m["highlight"] = el["highlight"]
    # (1) заметки авторов — перекрывают поля
    note = ((ctx.notes.get(key) or {}).get(eid)) if isinstance(ctx.notes.get(key), dict) else None
    noted = False
    if isinstance(note, dict):
        for f in TEXT_FIELDS:
            if as_text(note.get(f)):
                m[f], noted = as_text(note[f]), True
        if str_list(note.get("actions")):
            m["actions"], noted = str_list(note["actions"])[:MAX_ACTIONS], True
        if isinstance(note.get("metrics"), list):
            m["metrics"] = [x for x in note["metrics"] if isinstance(x, dict) and as_text(x.get("label"))][:MAX_METRICS]
            noted = True
        if isinstance(note.get("links"), list):
            nl = []
            for l in note["links"]:
                if isinstance(l, dict) and ctx.valid_href(l.get("href"), own):
                    nl.append({"label": as_text(l.get("label")) or l["href"], "href": l["href"]})
                else:
                    ctx.warnings.append("chart-notes: ссылка без цели пропущена: %s/%s → %s" % (key, eid, (l or {}).get("href") if isinstance(l, dict) else l))
            m["links"] = dedupe(nl + m["links"], lambda l: l["href"])[:MAX_LINKS]
            noted = True
    sources = (["notes"] if noted else []) + (["data"] if used_data else []) + (["glossary"] if g else [])
    m["sources"] = sources
    generic = not noted and not used_data
    if not m["summary"]:
        ctx.warnings.append("пояснение не задано: %s/%s" % (key, eid))
    return m, generic


CHART_NAMES = {"effort-impact": "Матрица усилие–влияние", "bubble": "Пузырьковая диаграмма", "metrics-heatmap": "Тепловая карта метрик",
               "radar-top10": "Радары топ-10", "pareto": "Парето", "tornado": "Торнадо чувствительности",
               "dist-category": "Реестр по категориям", "dist-evidence": "Классы доказательств", "dist-horizon": "Горизонты",
               "gantt": "Диаграмма Ганта", "funnel": "Воронка AARRR", "forecast-fan": "Веер прогноза", "cac-ltv": "LTV и CAC",
               "payback": "Окупаемость", "keywords-volume": "Спрос по запросам", "keywords-clusters": "Спрос по кластерам",
               "events-calendar": "Календарь событий", "competitors-heatmap": "Функции конкурентов", "critical-path": "Критический путь",
               "channel-mix": "Каналы привлечения", "kpi-tree": "Дерево метрик"}


def build_meta(key, reg_snapshot, ctx, own, title, caption, section):
    """Метаданные графика по снимку реестра {els, variant}. own — {ключ: ids} всех графиков сборки."""
    gkey = reg_snapshot.get("variant") or key
    gc = gfind(ctx.gl, ["charts", gkey]) or gfind(ctx.gl, ["charts", key]) or {}
    howto = as_text(gc.get("howto_concept")) if ctx.concept and as_text(gc.get("howto_concept")) else as_text(gc.get("howto"))
    legend = [x for x in gc.get("legend") or [] if isinstance(x, dict) and as_text(x.get("label"))]
    note_c = ((ctx.notes.get(key) or {}).get("_chart")) if isinstance(ctx.notes.get(key), dict) else None
    if isinstance(note_c, dict):
        howto = as_text(note_c.get("howto")) or howto
        if isinstance(note_c.get("legend"), list) and note_c["legend"]:
            legend = [x for x in note_c["legend"] if isinstance(x, dict) and as_text(x.get("label"))] or legend
    if not howto:
        ctx.warnings.append("пояснение не задано: %s/howto" % key)
    if not legend:
        ctx.warnings.append("пояснение не задано: %s/legend" % key)
    start = len(ctx.warnings)
    elements, generic = OrderedDict(), []
    for eid, el in reg_snapshot["els"].items():
        m, gen = compose(key, eid, el, ctx, own, gc.get("sections") or ())
        elements[eid] = m
        if gen:
            generic.append(eid)
    links = [ctx.sec(n) for n in gc.get("sections") or []]
    return OrderedDict([("key", key), ("title", title), ("caption", caption), ("section", section),
                        ("mode", "concept" if ctx.concept else "product"), ("howto", howto), ("legend", legend),
                        ("links", [l for l in links if l]), ("elements", elements), ("generic", generic),
                        ("warnings", ctx.warnings[start:])])


# ---------------------------------------------------------------- проверка сборщика
def svg_elements(path):
    """(корень, [(id, attrs)]) интерактивных элементов SVG; ошибка разбора → исключение ET.ParseError."""
    root = ET.parse(str(path)).getroot()
    els = []
    for node in root.iter():
        if "data-ps-el" in node.attrib:
            els.append((node.attrib["data-ps-el"], node.attrib))
    return root, els


def check_meta(out_dir, D=None):
    """Список проблем (пусто — всё хорошо) по charts/charts-index.json и charts/<ключ>.meta.json."""
    out = Path(out_dir)
    probs = []
    idx = load_json(out / "charts" / "charts-index.json")
    if idx is None:
        return probs if not (out / "charts").is_dir() else ["charts/charts-index.json не читается"]
    if D is None:
        D = {"P": load_json(out / "data" / "proposals.json") or [], "S": load_json(out / "data" / "scores.json") or [],
             "G": load_json(out / "data" / "gantt.json") or [], "C": load_json(out / "data" / "competitors.json") or [],
             "cfg": load_json(out / "build" / "run-config.json") or {}}
    ctx = Context(out, D)
    metas = {}
    for e in idx if isinstance(idx, list) else []:
        if not isinstance(e, dict) or not e.get("key"):
            continue
        key = e["key"]
        mp = out / (e.get("meta") or "charts/%s.meta.json" % key)
        meta = load_json(mp)
        if not isinstance(meta, dict):
            probs.append("%s: нет или не читается %s (перестройте графики без --only)" % (key, mp.name))
            continue
        metas[key] = meta
    own = {k: set((m.get("elements") or {}).keys()) for k, m in metas.items()}
    for e in idx if isinstance(idx, list) else []:
        key = e.get("key") if isinstance(e, dict) else None
        if key not in metas:
            continue
        meta = metas[key]
        svgp = out / (e.get("svg") or "charts/%s.svg" % key)
        try:
            root, els = svg_elements(svgp)
        except (OSError, ET.ParseError) as ex:
            probs.append("%s: SVG не разбирается как XML (%s)" % (key, ex))
            continue
        if root.attrib.get("data-ps-chart") != key:
            probs.append("%s: у корня <svg> нет data-ps-chart=\"%s\"" % (key, key))
        if root.find(SVG_NS + "title") is None or root.find(SVG_NS + "desc") is None:
            probs.append("%s: у корня <svg> нет <title>/<desc>" % key)
        ids = [i for i, _ in els]
        dup = sorted({i for i in ids if ids.count(i) > 1})
        if dup:
            probs.append("%s: повторяющиеся data-ps-el: %s" % (key, ", ".join(dup[:10])))
        for i, a in els:
            miss = [n for n, ok in (("tabindex=0", a.get("tabindex") == "0"), ("role=button", a.get("role") == "button"),
                                    ("aria-label", bool(as_text(a.get("aria-label")))),
                                    ("class ps-el", "ps-el" in (a.get("class") or "").split())) if not ok]
            if miss:
                probs.append("%s/%s: нет %s" % (key, i, ", ".join(miss)))
        mel = meta.get("elements") or {}
        for i in sorted(set(ids) - set(mel)):
            probs.append("%s/%s: элемент без записи в meta.elements" % (key, i))
        for i in sorted(set(mel) - set(ids)):
            probs.append("%s/%s: запись meta.elements без элемента в SVG" % (key, i))
        if not as_text(meta.get("howto")):
            probs.append("%s: нет howto" % key)
        if not meta.get("legend"):
            probs.append("%s: нет legend" % key)
        all_links = list(meta.get("links") or []) + [l for m in mel.values() for l in (m.get("links") or [])]
        for l in all_links:
            h = (l or {}).get("href") if isinstance(l, dict) else None
            if not ctx.valid_href(h, own):
                mm = re.fullmatch(r"#s(\d+)", as_text(h))
                why = "раздел вне 1…17" if mm else ("нет предложения" if as_text(h).startswith("#p/") else "цель не найдена")
                probs.append("%s: ссылка %s — %s" % (key, h, why))
    return probs


def list_generic(out_dir):
    """[(ключ, id, заголовок, причина)] — элементы с обобщённым пояснением (только глоссарий) или без пояснения."""
    out = Path(out_dir)
    res = []
    for e in load_json(out / "charts" / "charts-index.json") or []:
        if not isinstance(e, dict):
            continue
        meta = load_json(out / (e.get("meta") or "charts/%s.meta.json" % e.get("key"))) or {}
        gen = set(meta.get("generic") or [])
        for eid, m in (meta.get("elements") or {}).items():
            if not as_text(m.get("summary")):
                res.append((e["key"], eid, m.get("title", ""), "нет пояснения"))
            elif eid in gen:
                res.append((e["key"], eid, m.get("title", ""), "только глоссарий"))
    return res
