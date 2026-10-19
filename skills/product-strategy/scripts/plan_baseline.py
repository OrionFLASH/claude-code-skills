#!/usr/bin/env python3
"""Базовая линия плана data/plan-baseline.json и проверка согласованности текстов с ней (FB-046, SM 6.1).

  plan_baseline.py <OUT>                       записать data/plan-baseline.json (до авторов разделов, после gantt.json)
  plan_baseline.py <OUT> --check [--strict] [--json]
                                               сверить части текста и факт-лист с базовой линией → build/consistency-report.json
  plan_baseline.py <OUT> --show                напечатать базовую линию кратко

Что в базовой линии (один источник сроков, ёмкости и состава MVP для всех частей текста):
  - start_date — старт плана (run-config strategy.start_date, иначе created, иначе сегодня); месяц m = start + (m − 1) мес.;
  - capacity — scripts/capacity.py за горизонт (одно определение рабочего дня: day_hours, строка line);
  - milestones — вехи из data/gantt.json: beta, launch, mvp, paid (по полю milestone/kind задачи, иначе по словам
    «бета/beta», «запуск/launch/релиз», «MVP», «оплат/Pro/платн»), horizon_end; дата — из текста задачи (дд.мм.гггг),
    иначе первое число месяца;
  - mvp — P-id задач Ганта до вехи launch (иначе фаза «MVP/сборка», иначе весь горизонт) против тегов `mvp` реестра;
  - kill — критерии отказа ставок с датами (data/decisions.json), north_star и goal (decisions.json, run-config);
  - events — окна событий в горизонте (data/events.json); architecture — вариант data/integration-options.json (схема брифа
    research-integration: recommended = id варианта, options[].{id, title, effort_days [min, max], risks[], value, mvp, queue},
    platform_risks[]): chosen → recommended → лучшее «ценность / дни»; mvp_options и mvp_days — сроки интеграции в составе MVP;
  - months — все месяцы горизонта и видения (plan | gap | vision) с задачами, вехами, нагрузкой (середина effort_days,
    равномерно по месяцам задачи) и ёмкостью месяца; gantt_contract — пропуски месяцев (контракт Ганта на весь горизонт:
    месяцы 1…горизонт и видение до горизонт + 12 × vision_years без «дыр», например 7–12 при горизонте 6 и видении с 13).
Плейсхолдеры для текста (decisions.py / assemble_strategy.py): {plan:beta}, {plan:launch}, {plan:mvp_ids}, {plan:kill.1.date},
{plan:capacity}, {plan:capacity.dev_days}, {plan:day_hours}, {plan:north_star}, {plan:arch} … (список — --list-placeholders сборки).

Проверка (--check; тот же код вызывает assemble_strategy.py, если базовая линия есть):
  plan_mismatch — дата рядом со словами вехи (бета, запуск, MVP, оплата) не совпадает с месяцем вехи;
  kill_date_mismatch — дата рядом с «критерий отказа / остановим» не совпадает ни с одной датой kill;
  capacity_mismatch — «ёмкость … N дн.» не совпадает с ёмкостью базовой линии (за горизонт или накопленной к месяцу);
  workday_mismatch — другое определение рабочего дня («6-часовой день», «день по 6 ч»), чем capacity.day_hours;
  mvp_mismatch — абзац про состав MVP называет P-id, которых нет в mvp.ids.
Код выхода --check: 0 — даты и числа вех согласованы (или заданы {plan:…}), 1 — есть расхождения (последняя строка —
сводка); --strict — ещё и отсутствие базовой линии — код 1, строки помечены «ОШИБКА». Шаг consistency в build_all.py:
код 1 — предупреждение, в --strict — провал. Только стандартная библиотека.
"""
import argparse
import calendar
import json
import re
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
import capacity as capmod  # noqa: E402

MONTHS_RU = ["январь", "февраль", "март", "апрель", "май", "июнь", "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь"]
MONTH_STEMS = {"январ": 1, "феврал": 2, "март": 3, "апрел": 4, "ма[йяе]": 5, "июн": 6, "июл": 7, "август": 8, "сентябр": 9,
               "октябр": 10, "ноябр": 11, "декабр": 12}
DATE_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b|\b(\d{1,2})\.(\d{1,2})\.(\d{4})\b|\b(\d{1,2})\.(\d{4})\b")
MONTH_NAME_RE = re.compile(r"\b(" + "|".join(MONTH_STEMS) + r")\w*[\s ]+(\d{4})\b", re.I)
MONTH_NUM_RE = re.compile(r"(?:\bмесяц\w*[\s ]+|\bмес\.[\s ]*)(\d{1,2})\b|\b(\d{1,2})-?(?:й|го|м)?[\s ]+месяц", re.I)
KIND_WORDS = (
    ("beta", re.compile(r"\bбет\w*|\bbeta\b", re.I)),
    ("launch", re.compile(r"\bзапуск\w*|\blaunch\w*|\bрелиз\w*", re.I)),
    ("paid", re.compile(r"\bоплат\w*|\bплатн\w+\s+(?:тариф|верси|част)\w*|\bмонетизац\w*|\bприём\w*\s+платеж\w*", re.I)),
    ("mvp", re.compile(r"\bmvp\b", re.I)),
)
KILL_RE = re.compile(r"критери\w*\s+(?:отказа|остановки)|\bkill\b|стоп-критери\w*|останов\w*|прекрат\w*|закро\w*\s+ставк", re.I)
CAP_RE = re.compile(r"ёмкост\w*|емкост\w*", re.I)
DAYS_RE = re.compile(r"(\d+(?:[.,]\d+)?)[\s ]*(?:≈[\s ]*)?(?:чел\.?[\s -]*)?(?:дн\.|дней|дня|день|человеко-дн\w*)", re.I)
PID_RE = re.compile(r"(?<![A-Za-z0-9])P\d{3}(?!\d)")
NEAR = 35   # символов от слова вехи до даты
NOT_MVP_RE = re.compile(r"mvp\s+нет|нет\s+в\s+mvp|не\s+вход|вне\s+mvp|после\s+mvp|не\s+в\s+mvp|исключ|отлож|позже|за\s+рамк|v1\b|v2\b|следующ", re.I)
MVP_SCOPE_RE = re.compile(r"\bmvp\b\**[\s\u00a0]*:|\|[\s\u00a0]*mvp(?:[-\s]?\d+)?[\s\u00a0]*\||состав\w*\s+mvp|в\s+mvp\s+(?:входят|включ|войдут)"
                          r"|mvp\s+(?:включает|состоит|входят)", re.I)


# ---------------------------------------------------------------- ввод-вывод
def load_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default
    except (OSError, ValueError) as e:
        print("предупреждение: не удалось прочитать %s: %s" % (path, e), file=sys.stderr)
        return default


def load(out):
    d = load_json(Path(out) / "data" / "plan-baseline.json", None)
    return d if isinstance(d, dict) else None


# ---------------------------------------------------------------- даты
def parse_iso(s):
    try:
        y, m, d = (int(x) for x in str(s)[:10].split("-"))
        return date(y, m, d)
    except (ValueError, TypeError):
        return None


def add_months(d, n):
    y, m = divmod(d.month - 1 + n, 12)
    y += d.year
    m += 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def month_start(start, m):
    """Начало месяца плана m: месяц 1 — с даты старта, дальше — календарные месяцы (как читают Гант авторы)."""
    if m <= 1:
        return start
    d = add_months(date(start.year, start.month, 1), m - 1)
    return d


def month_end(start, m):
    nxt = add_months(date(start.year, start.month, 1), m)
    return date.fromordinal(nxt.toordinal() - 1)


def month_of(start, d):
    """Номер календарного месяца плана (1…), к которому относится дата d (0 — раньше старта)."""
    n = (d.year - start.year) * 12 + (d.month - start.month) + 1
    return n if n >= 1 else 0


def fmt_date(d):
    return "%02d.%02d.%04d" % (d.day, d.month, d.year)


def mon_text(d):
    return "%s %d" % (MONTHS_RU[d.month - 1], d.year)


LABEL_SPAN_RE = re.compile(r"\[[^\]\n]{0,200}\]")
RANGE_RE = re.compile(r"\b(" + "|".join(MONTH_STEMS) + r")\w*[\s\u00a0]*[–—-][\s\u00a0]*(?:" + "|".join(MONTH_STEMS) + r")\w*[\s\u00a0]+(\d{4})\b", re.I)


def mask_labels(text):
    """Метки [факт: источник, 2026-10-17] и ссылки — пробелами той же длины (даты проверок не считаются сроками)."""
    return LABEL_SPAN_RE.sub(lambda m: " " * len(m.group(0)), text)


def dates_in(text):
    """[(позиция, (год, месяц) | ('m', N))] — даты (дд.мм.гггг, гггг-мм-дд, мм.гггг, «январь 2027», «март–июнь 2027»)
    и «месяц N»; даты внутри меток [..] пропускаются."""
    text = mask_labels(text)
    out = []
    ranged = set()
    for m in RANGE_RE.finditer(text):
        stem = m.group(1).lower()
        num = next((v for k, v in MONTH_STEMS.items() if re.match(k, stem)), None)
        if num:
            out.append((m.start(), (int(m.group(2)), num)))
            ranged.add(m.end())
    for m in DATE_RE.finditer(text):
        if m.group(1):
            out.append((m.start(), (int(m.group(1)), int(m.group(2)))))
        elif m.group(4):
            out.append((m.start(), (int(m.group(6)), int(m.group(5)))))
        else:
            out.append((m.start(), (int(m.group(8)), int(m.group(7)))))
    for m in MONTH_NAME_RE.finditer(text):
        if m.end() in ranged:
            continue
        stem = m.group(1).lower()
        num = next((v for k, v in MONTH_STEMS.items() if re.match(k, stem)), None)
        if num:
            out.append((m.start(), (int(m.group(2)), num)))
    for m in MONTH_NUM_RE.finditer(text):
        n = int(m.group(1) or m.group(2))
        if 1 <= n <= 60:
            out.append((m.start(), ("m", n)))
    return sorted(out, key=lambda x: x[0])


def date_from_task(text, start, month):
    """Точная дата из текста задачи Ганта, если она попадает в месяц задачи, иначе начало месяца."""
    for m in DATE_RE.finditer(text or ""):
        try:
            if m.group(1):
                d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            elif m.group(4):
                d = date(int(m.group(6)), int(m.group(5)), int(m.group(4)))
            else:
                continue
        except ValueError:
            continue
        if month_of(start, d) == month:
            return d, True
    return month_start(start, month), False


# ---------------------------------------------------------------- построение
def start_of(cfg):
    st = cfg.get("strategy") or {}
    for key, src in ((st.get("start_date"), "run-config strategy.start_date"), (cfg.get("created"), "run-config created")):
        d = parse_iso(key) if key else None
        if d:
            return d, src
    return date.today(), "сегодня (в run-config нет strategy.start_date и created)"


def gantt_rows(out):
    g = load_json(Path(out) / "data" / "gantt.json", [])
    rows = g.get("tasks") if isinstance(g, dict) else g
    return [r for r in rows or [] if isinstance(r, dict) and isinstance(r.get("start_month"), (int, float))
            and isinstance(r.get("end_month"), (int, float))]


def milestone_kind(row):
    k = str(row.get("milestone") or row.get("kind") or "").lower()
    if k in ("beta", "launch", "mvp", "paid"):
        return k
    text = "%s %s" % (row.get("task") or "", row.get("phase") or "")
    for kind, rx in KIND_WORDS:
        if rx.search(text):
            return kind
    return None


def find_milestones(rows, start, horizon):
    ms = {}
    plan_rows = [r for r in rows if str(r.get("phase") or "").lower() != "vision" and r["start_month"] <= horizon]
    for r in sorted(plan_rows, key=lambda r: (r["end_month"], str(r.get("id")))):
        is_ms = r.get("type") == "milestone" or r.get("milestone")
        kind = milestone_kind(r)
        if not kind or (not is_ms and kind != "paid"):
            continue
        if kind in ms:
            continue
        mo = int(r["end_month"])
        d, exact = date_from_task(r.get("task"), start, mo)
        ms[kind] = {"month": mo, "date": d.isoformat(), "exact": exact, "text": fmt_date(d) if exact else mon_text(d),
                    "mon": mon_text(d), "id": r.get("id"), "task": r.get("task"), "source": "data/gantt.json"}
    if "launch" not in ms:          # последняя контрольная точка горизонта с «запуском» в фазе
        for r in plan_rows:
            if r.get("type") == "milestone" and re.search(r"запуск|launch", str(r.get("phase") or ""), re.I):
                mo = int(r["end_month"])
                d, exact = date_from_task(r.get("task"), start, mo)
                ms["launch"] = {"month": mo, "date": d.isoformat(), "exact": exact, "text": fmt_date(d) if exact else mon_text(d),
                                "mon": mon_text(d), "id": r.get("id"), "task": r.get("task"), "source": "data/gantt.json (фаза)"}
                break
    end = month_end(start, horizon)
    ms["horizon_end"] = {"month": horizon, "date": end.isoformat(), "exact": True, "text": fmt_date(end), "mon": mon_text(end),
                         "source": "start_date + horizon_months"}
    return ms


def effort_mid(p):
    ed = (p or {}).get("effort_days")
    if isinstance(ed, list) and len(ed) == 2 and all(isinstance(x, (int, float)) for x in ed):
        return (ed[0] + ed[1]) / 2.0
    return 0.0


def build(out):
    out = Path(out)
    cfg = load_json(out / "build" / "run-config.json", {}) or {}
    st = cfg.get("strategy") or {}
    horizon = int(st.get("horizon_months") or 12)
    vision_years = st.get("vision_years") if isinstance(st.get("vision_years"), (int, float)) else 2
    start, start_src = start_of(cfg)
    cap = capmod.capacity(cfg, horizon)
    rows = gantt_rows(out)
    props = {p["id"]: p for p in load_json(out / "data" / "proposals.json", []) or [] if isinstance(p, dict) and p.get("id")}
    dec = load_json(out / "data" / "decisions.json", None)
    dec = dec if isinstance(dec, dict) else None
    ms = find_milestones(rows, start, horizon)
    # состав MVP
    launch = (ms.get("launch") or {}).get("month")
    plan_rows = [r for r in rows if str(r.get("phase") or "").lower() != "vision" and r["start_month"] <= horizon]
    if launch:
        mvp_rows, by = [r for r in plan_rows if r["end_month"] <= launch], "задачи Ганта до вехи launch (месяц %d)" % launch
    else:
        mvp_rows = [r for r in plan_rows if re.search(r"mvp|сборк", str(r.get("phase") or ""), re.I)]
        by = "задачи фазы «MVP/сборка» Ганта"
        if not mvp_rows:
            mvp_rows, by = plan_rows, "все задачи Ганта в горизонте (вехи launch нет)"
    mvp_ids = []
    for r in sorted(mvp_rows, key=lambda r: (r["start_month"], str(r.get("id")))):
        for pid in r.get("proposal_ids") or []:
            if pid not in mvp_ids:
                mvp_ids.append(pid)
    tagged = sorted(pid for pid, p in props.items() if any(str(t).lower() == "mvp" for t in (p.get("tags") or [])))
    mvp = {"ids": mvp_ids, "by": by, "registry_tagged": tagged,
           "only_in_gantt": [x for x in mvp_ids if tagged and x not in tagged],
           "only_in_registry": [x for x in tagged if x not in mvp_ids],
           "effort_days_mid": round(sum(effort_mid(props.get(x)) for x in mvp_ids), 1),
           "capacity_days_to_launch": round(cap["dev_days_month"] * (launch or horizon), 1)}
    # критерии отказа, North Star, цель
    kill = []
    for b in (dec or {}).get("bets") or []:
        k = b.get("kill") if isinstance(b, dict) else None
        if isinstance(k, dict) and k.get("date"):
            d = parse_iso(k["date"])
            kill.append({"bet": b.get("id"), "name": b.get("name"), "metric": k.get("metric"), "date": k["date"],
                         "text": fmt_date(d) if d else str(k["date"]), "month": month_of(start, d) if d else None})
    ns = (dec or {}).get("north_star") if isinstance((dec or {}).get("north_star"), dict) else None
    if not ns:
        nsj = load_json(out / "data" / "north-star.json", None)
        ns = nsj if isinstance(nsj, dict) else None
    # события и архитектура
    end = month_end(start, horizon)
    events = []
    for e in load_json(out / "data" / "events.json", []) or []:
        d = parse_iso((e or {}).get("date")) if isinstance(e, dict) else None
        if d and start <= d <= end:
            events.append({"date": d.isoformat(), "text": fmt_date(d), "month": month_of(start, d), "title": e.get("title")})
    arch = None
    io = load_json(out / "data" / "integration-options.json", None)
    opts = io.get("options") if isinstance(io, dict) else io
    opts = [o for o in opts or [] if isinstance(o, dict)]
    if opts:
        rec = io.get("recommended") if isinstance(io, dict) else None      # схема research-integration.md: recommended = id варианта
        pick = next((o for o in opts if o.get("chosen")), None) or \
            next((o for o in opts if rec not in (None, "") and str(o.get("id")) == str(rec)), None) or \
            next((o for o in opts if o.get("recommended") is True), None)
        if pick is None:
            def ratio(o):
                v, dd = o.get("value"), o.get("days") or o.get("effort_days")
                dd = (sum(dd) / 2.0) if isinstance(dd, list) and dd else dd
                return (v or 0) / dd if isinstance(v, (int, float)) and isinstance(dd, (int, float)) and dd > 0 else 0
            pick = max(opts, key=ratio)
        def span(o):
            dd = o.get("days") or o.get("effort_days")
            if isinstance(dd, list) and dd:
                return float(dd[0]), float(dd[-1])
            return (float(dd), float(dd)) if isinstance(dd, (int, float)) else None
        # сроки интеграции в составе MVP: рекомендованный вариант и варианты с mvp: true (G9)
        in_mvp = [o for o in opts if o is pick or o.get("mvp") is True]
        spans = [span(o) for o in in_mvp if span(o)]
        arch = {"id": pick.get("id"), "name": pick.get("name") or pick.get("title"), "days": pick.get("days") or pick.get("effort_days"),
                "risks": pick.get("risks"), "value": pick.get("value"), "options": len(opts),
                "why": "chosen/recommended в файле" if (pick.get("chosen") or pick.get("recommended") is True or
                                                         (rec not in (None, "") and str(pick.get("id")) == str(rec))) else "лучшее отношение ценность / дни",
                "mvp_options": [o.get("id") for o in in_mvp],
                "mvp_days": [round(sum(s[0] for s in spans), 1), round(sum(s[1] for s in spans), 1)] if spans else None,
                "queue": pick.get("queue"),
                "platform_risks": (io.get("platform_risks") if isinstance(io, dict) else None) or [],
                "source": "data/integration-options.json"}
    months, contract = month_grid(rows, props, start, horizon, vision_years, cap, ms)
    return {"version": 1, "generated": date.today().isoformat(), "generated_by": "plan_baseline.py",
            "start_date": start.isoformat(), "start_source": start_src, "horizon_months": horizon, "vision_years": vision_years,
            "capacity": {k: cap[k] for k in ("hours_per_week", "dev_share", "day_hours", "team_size", "hours", "dev_hours", "dev_days",
                                             "dev_days_month", "hours_month", "source", "line")},
            "milestones": ms, "mvp": mvp, "kill": kill,
            "north_star": {"metric": ns.get("metric"), "target": ns.get("target"),
                           "source": "data/decisions.json" if dec and dec.get("north_star") else "data/north-star.json"} if ns else None,
            "goal": st.get("success_criteria") or st.get("goal"),
            "events": events, "architecture": arch, "months": months, "gantt_contract": contract,
            "sources": {"gantt": "data/gantt.json" if rows else None, "decisions": "data/decisions.json" if dec else None,
                        "capacity": "scripts/capacity.py (run-config project.capacity)"}}


def month_grid(rows, props, start, horizon, vision_years, cap, ms):
    """Все месяцы горизонта и видения: задачи, вехи, нагрузка; пропуски — нарушение контракта Ганта."""
    maxm = max([horizon] + [int(r["end_month"]) for r in rows])
    vision_to = max(maxm, horizon + int(round(12 * float(vision_years or 0))))
    by_month = {m: {"tasks": [], "load": 0.0} for m in range(1, vision_to + 1)}
    for r in rows:
        s, e = int(r["start_month"]), int(r["end_month"])
        n = max(1, e - s + 1)
        eff = sum(effort_mid(props.get(p)) for p in r.get("proposal_ids") or [])
        for m in range(max(1, s), min(e, vision_to) + 1):
            by_month[m]["tasks"].append(r.get("id"))
            by_month[m]["load"] += eff / n
    mmap = {}
    for k, v in ms.items():
        if k != "horizon_end":
            mmap.setdefault(v["month"], []).append(k)
    vis_rows = [r for r in rows if str(r.get("phase") or "").lower() == "vision" or r["start_month"] > horizon]
    vis_start = min([int(r["start_month"]) for r in vis_rows], default=None)
    months, plan_empty, gap = [], [], []
    for m in range(1, vision_to + 1):
        d = month_start(start, m)
        period = "plan" if m <= horizon else ("vision" if vis_start and m >= vis_start else "gap")
        if period == "plan" and not by_month[m]["tasks"]:
            plan_empty.append(m)
        if period == "gap" or (period == "vision" and not by_month[m]["tasks"] and m <= maxm):
            gap.append(m)
        months.append({"month": m, "period": period, "start": d.isoformat(), "label": mon_text(d), "tasks": by_month[m]["tasks"],
                       "milestones": mmap.get(m, []), "load_days": round(by_month[m]["load"], 1),
                       "capacity_days": cap["dev_days_month"] if m <= horizon else None,
                       "over_capacity": bool(m <= horizon and by_month[m]["load"] > cap["dev_days_month"] * 1.3 + 1e-9)})
    msgs = []
    if not rows:
        msgs.append("нет data/gantt.json — контракт Ганта не проверен")
    if plan_empty:
        msgs.append("месяцы плана без задач: %s — растяните задачи или добавьте поддерживающие" % spans(plan_empty))
    if gap:
        msgs.append("месяцы %s между горизонтом и видением без задач: добавьте фазу «после горизонта» (phase: \"vision\" с месяца %d) "
                    "или задачи-продолжения, чтобы Гант покрывал весь горизонт и видение" % (spans(gap), horizon + 1))
    if rows and maxm < vision_to:
        msgs.append("видение заканчивается месяцем %d, а по vision_years = %s ожидается до месяца %d" % (maxm, vision_years, vision_to))
    over = [x["month"] for x in months if x["over_capacity"]]
    if over:
        msgs.append("нагрузка выше ёмкости × 1,3 в месяцах %s (ёмкость %s дн./мес.)" % (spans(over), cap["dev_days_month"]))
    return months, {"ok": bool(rows) and not plan_empty and not gap, "plan_months_without_tasks": plan_empty, "gap_months": gap,
                    "vision_from": vis_start, "vision_to": vision_to, "last_month_in_gantt": maxm if rows else None,
                    "over_capacity_months": over, "messages": msgs}


def spans(ms):
    ms = sorted(set(ms))
    out, i = [], 0
    while i < len(ms):
        j = i
        while j + 1 < len(ms) and ms[j + 1] == ms[j] + 1:
            j += 1
        out.append("%d" % ms[i] if i == j else "%d–%d" % (ms[i], ms[j]))
        i = j + 1
    return ", ".join(out)


# ---------------------------------------------------------------- плейсхолдеры {plan:…}
def plan_values(b):
    """Плоский словарь «ключ → значение» для {plan:…}."""
    v = {}
    if not isinstance(b, dict):
        return v
    for k in ("start_date", "horizon_months", "vision_years", "goal"):
        if b.get(k) not in (None, ""):
            v[k] = b[k]
    sd = parse_iso(b.get("start_date"))
    if sd:
        v["start"] = fmt_date(sd)
    for kind, m in (b.get("milestones") or {}).items():
        if not isinstance(m, dict):
            continue
        v[kind] = m.get("text")
        v[kind + ".month"] = m.get("month")
        d = parse_iso(m.get("date"))
        if d:
            v[kind + ".date"] = fmt_date(d)
            v[kind + ".mon"] = mon_text(d)
        if m.get("id"):
            v[kind + ".id"] = m["id"]
    if "horizon_end" in (b.get("milestones") or {}):
        v["end"] = v.get("horizon_end")
    mvp = b.get("mvp") or {}
    if mvp.get("ids") is not None:
        v["mvp_ids"] = ", ".join(mvp["ids"]) or "—"
        v["mvp_count"] = len(mvp["ids"])
        v["mvp_effort_days"] = mvp.get("effort_days_mid")
    cap = b.get("capacity") or {}
    if cap:
        v["capacity"] = cap.get("line")
        for k in ("dev_days", "dev_days_month", "day_hours", "hours_per_week", "dev_share", "team_size", "dev_hours"):
            if cap.get(k) is not None:
                v["capacity." + k] = cap[k]
        v["day_hours"] = cap.get("day_hours")
    for k in b.get("kill") or []:
        i = k.get("bet")
        v["kill.%s.date" % i] = k.get("text")
        v["kill.%s.metric" % i] = k.get("metric") or ""
        if k.get("month") is not None:
            v["kill.%s.month" % i] = k["month"]
    ns = b.get("north_star") or {}
    if ns.get("metric"):
        v["north_star"] = ns["metric"]
        if ns.get("target"):
            v["north_star.target"] = ns["target"]
    a = b.get("architecture") or {}
    if a.get("name"):
        v["arch"] = a["name"]
        if a.get("days") is not None:
            v["arch.days"] = a["days"] if not isinstance(a["days"], list) else "–".join(str(x) for x in a["days"])
    for i, e in enumerate(b.get("events") or [], 1):
        v["event.%d" % i] = "%s (%s)" % (e.get("title"), e.get("text"))
    v = {k: x for k, x in v.items() if x is not None}
    return v


# ---------------------------------------------------------------- проверка согласованности
def _units(text):
    """Абзацы / пункты / строки таблиц вне ограждённого кода → [(строка, текст)]."""
    res, cur, start, fence = [], [], 0, False
    for i, line in enumerate(text.splitlines(), 1):
        s = line.strip()
        if s.startswith("```") or s.startswith("~~~"):
            fence = not fence
            if cur:
                res.append((start, " ".join(cur)))
                cur = []
            continue
        if fence or not s or s.startswith("#"):
            if cur:
                res.append((start, " ".join(cur)))
                cur = []
            continue
        if s.startswith("|") or re.match(r"([-*+]|\d+[.)])\s", s):
            if cur:
                res.append((start, " ".join(cur)))
                cur = []
            res.append((i, s))
            continue
        if not cur:
            start = i
        cur.append(s)
    if cur:
        res.append((start, " ".join(cur)))
    return res


def text_sources(out):
    """Тексты для сверки: части разделов (или strategy.md), факт-лист, резюме → [(файл, текст)]."""
    out = Path(out)
    files = sorted((out / "build" / "parts").glob("strategy-*.md")) + sorted((out / "research").glob("strategy-part*.md"))
    if not files and (out / "research" / "strategy.md").exists():
        files = [out / "research" / "strategy.md"]
    for extra in (out / "build" / "strategy-facts.md", out / "build" / "summary-draft.md", out / "build" / "strategy-summary.md"):
        if extra.exists():
            files.append(extra)
    res = []
    for f in files:
        try:
            res.append((f.relative_to(out).as_posix(), f.read_text(encoding="utf-8")))
        except OSError:
            continue
    return res


def _ym(start, token):
    if token[0] == "m":
        d = month_start(start, token[1])
        return d.year, d.month
    return token


def check_units(units, b):
    """units: [(файл, строка, текст)] → список расхождений с базовой линией."""
    issues = []
    if not isinstance(b, dict):
        return issues
    start = parse_iso(b.get("start_date")) or date.today()
    ms = {k: v for k, v in (b.get("milestones") or {}).items() if isinstance(v, dict) and k != "horizon_end"}
    ms_ym = {}
    for k, v in ms.items():
        d = parse_iso(v.get("date"))
        if d:
            ms_ym[k] = (d.year, d.month)
    kill_ym = set()
    for k in b.get("kill") or []:
        d = parse_iso(k.get("date"))
        if d:
            kill_ym.add((d.year, d.month))
    cap = b.get("capacity") or {}
    day_hours = cap.get("day_hours")
    horizon = int(b.get("horizon_months") or 12)
    cap_vals = set()
    if cap.get("dev_days") is not None:
        cap_vals.add(round(float(cap["dev_days"]), 1))
    if cap.get("dev_days_month"):
        for k in range(1, horizon + 1):
            cap_vals.add(round(float(cap["dev_days_month"]) * k, 1))
    mvp_ids = set((b.get("mvp") or {}).get("ids") or [])
    for f, line, text in units:
        low = text.lower()
        dts = dates_in(text)
        if dts and ms_ym:
            for pos, tok in dts:
                near = None
                best = 10 ** 6
                for kind, rx in KIND_WORDS:          # слово вехи стоит перед датой и близко: «бета 12.01.2027», «запуск — в марте 2027»
                    for m in rx.finditer(text):
                        dist = pos - m.end()
                        if 0 <= dist <= NEAR and dist < best and not any(m.end() <= p2 < pos for p2, _t in dts) \
                                and "|" not in text[m.end():pos]:
                            best, near = dist, kind
                if near is None:
                    continue
                if near and near in ms_ym:
                    ym = _ym(start, tok)
                    if ym != ms_ym[near]:
                        issues.append({"code": "plan_mismatch", "file": f, "line": line, "kind": near,
                                       "found": "%02d.%d" % (ym[1], ym[0]), "expected": ms[near].get("text"),
                                       "message": "веха «%s»: в тексте %02d.%d, в plan-baseline — %s (используйте {plan:%s})" % (
                                           near, ym[1], ym[0], ms[near].get("text"), near), "text": text[:160]})
                        break
        if dts and kill_ym and KILL_RE.search(text) and not any(rx.search(text) for _k, rx in KIND_WORDS):
            yms = {_ym(start, t) for _p, t in dts}
            if not (yms & kill_ym):
                issues.append({"code": "kill_date_mismatch", "file": f, "line": line,
                               "found": ", ".join("%02d.%d" % (m, y) for y, m in sorted(yms)),
                               "expected": ", ".join(k.get("text") for k in b.get("kill") or []),
                               "message": "критерий отказа: даты в тексте не совпадают с датами kill базовой линии (используйте {plan:kill.N.date})",
                               "text": text[:160]})
        cap_hits = [m for c in CAP_RE.finditer(text) for m in DAYS_RE.finditer(text, c.end(), min(len(text), c.end() + 60))] if cap_vals else []
        if cap_hits:
            for m in cap_hits:
                try:
                    x = float(m.group(1).replace(",", "."))
                except ValueError:
                    continue
                if x < 3:
                    continue
                if not any(abs(x - c) <= max(1.0, 0.05 * c) for c in cap_vals):
                    issues.append({"code": "capacity_mismatch", "file": f, "line": line, "found": m.group(0),
                                   "expected": "%s дн. за %s мес. (%s дн./мес.)" % (cap.get("dev_days"), horizon, cap.get("dev_days_month")),
                                   "message": "ёмкость: «%s» не совпадает с базовой линией (%s); используйте {plan:capacity.dev_days}" % (
                                       m.group(0), cap.get("line")), "text": text[:160]})
                    break
        if day_hours:
            for v, frag in capmod.day_definitions(text):
                if abs(v - float(day_hours)) > 1e-6:
                    issues.append({"code": "workday_mismatch", "file": f, "line": line, "found": frag, "expected": "%g ч" % day_hours,
                                   "message": "другое определение рабочего дня: «%s», в capacity — %g ч (одна величина project.capacity.day_hours)"
                                              % (frag, day_hours), "text": text[:160]})
                    break
        if mvp_ids and MVP_SCOPE_RE.search(text) and not NOT_MVP_RE.search(low):
            extra = sorted({p for p in PID_RE.findall(text) if p not in mvp_ids})
            if extra:
                issues.append({"code": "mvp_mismatch", "file": f, "line": line, "found": ", ".join(extra),
                               "expected": ", ".join(sorted(mvp_ids)),
                               "message": "состав MVP: %s нет в MVP по Ганту ({plan:mvp_ids})" % ", ".join(extra), "text": text[:160]})
    return issues


def check(out, b=None):
    b = b or load(out)
    units = []
    for f, text in text_sources(out):
        for line, body in _units(text):
            units.append((f, line, body))
    return check_units(units, b)


# ---------------------------------------------------------------- CLI
def summary_lines(b):
    ms = b.get("milestones") or {}
    L = ["старт %s, горизонт %s мес.; ёмкость: %s" % (b.get("start_date"), b.get("horizon_months"), (b.get("capacity") or {}).get("line"))]
    for k in ("mvp", "beta", "launch", "paid", "horizon_end"):
        if k in ms:
            L.append("  веха %-11s месяц %s — %s%s" % (k, ms[k]["month"], ms[k]["text"], (" (%s)" % ms[k]["id"]) if ms[k].get("id") else ""))
    mvp = b.get("mvp") or {}
    L.append("  MVP: %d P-id (%s); середина усилий %s дн. против ёмкости до запуска %s дн." % (
        len(mvp.get("ids") or []), mvp.get("by"), mvp.get("effort_days_mid"), mvp.get("capacity_days_to_launch")))
    if mvp.get("only_in_registry"):
        L.append("  ! с тегом mvp в реестре, но не в Ганте до запуска: %s" % ", ".join(mvp["only_in_registry"]))
    for k in b.get("kill") or []:
        L.append("  критерий отказа ставки %s: %s" % (k.get("bet"), k.get("text")))
    for m in (b.get("gantt_contract") or {}).get("messages") or []:
        L.append("  ! Гант: %s" % m)
    return L


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0], formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out", help="папка прогона <OUT>")
    ap.add_argument("--check", action="store_true", help="сверить тексты с data/plan-baseline.json")
    ap.add_argument("--strict", action="store_true", help="--check: расхождения — код выхода 1")
    ap.add_argument("--show", action="store_true", help="кратко показать базовую линию")
    ap.add_argument("--json", action="store_true", help="вывод JSON")
    a = ap.parse_args(argv)
    out = Path(a.out).resolve()
    if not (out / "data").is_dir():
        print("ошибка: нет папки %s/data" % out, file=sys.stderr)
        return 2
    if a.show:
        b = load(out)
        if not b:
            print("нет data/plan-baseline.json (plan_baseline.py <OUT>)", file=sys.stderr)
            return 1
        print(json.dumps(b, ensure_ascii=False, indent=1) if a.json else "\n".join(summary_lines(b)))
        return 0
    if a.check:
        b = load(out)
        if not b:
            print("нет data/plan-baseline.json — сначала plan_baseline.py <OUT>", file=sys.stderr)
            return 1 if a.strict else 0
        issues = check(out, b)
        rep = {"ok": not issues, "date": date.today().isoformat(), "baseline": "data/plan-baseline.json", "issues": issues,
               "counts": {c: sum(1 for i in issues if i["code"] == c) for c in sorted({i["code"] for i in issues})}}
        (out / "build").mkdir(parents=True, exist_ok=True)
        (out / "build" / "consistency-report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if a.json:
            print(json.dumps(rep, ensure_ascii=False, indent=2))
        else:
            for i in issues[:40]:
                print("%s [%s] %s:%s — %s" % ("ОШИБКА" if a.strict else "расхождение", i["code"], i["file"], i["line"], i["message"]))
            print("итог: расхождений с plan-baseline %d%s; отчёт build/consistency-report.json" % (len(issues), "" if issues else " — тексты согласованы"))
        return 1 if issues else 0                      # D7: код 0 — согласовано, 1 — расхождения (build_all: WARN, --strict — провал)
    b = build(out)
    (out / "data" / "plan-baseline.json").write_text(json.dumps(b, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if a.json:
        print(json.dumps(b, ensure_ascii=False, indent=2))
    else:
        print("записано %s" % (out / "data" / "plan-baseline.json"))
        print("\n".join(summary_lines(b)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
