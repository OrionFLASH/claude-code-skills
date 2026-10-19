#!/usr/bin/env python3
"""Передача стратегии в разработку: один Markdown-файл, по которому Claude Code сам создаст эпики и задачи (GitHub issues).

  handoff.py <OUT> [--scope SECTION[,SECTION…]|all|ui] [--detail links|brief|full] [--horizon now|next|all]
             [--out FILE] [--repo-prefix PATH] [--force] [--dry-run]
  handoff.py <OUT> --list-sections [--json] [--horizon …] [--detail …]

Вход (всё, кроме реестра, необязательно; отсутствующее пропускается с пометкой): build/run-config.json (продукт, дата,
режим, `handoff: {enabled, scope, detail, horizon, ask_at_end}` — значения по умолчанию, флаги главнее),
data/proposals.json, data/scores.json (priority P0–P3, blocked_by), data/gantt.json (done_criteria, сроки),
data/mockups-index.json, design-refs/*.json|md, data/flows.json, research/strategy.md (разделы `## N.`),
research/specs/<P-id>-*.md, research/experiments/E*.md, mockups/tokens.css, data/issue-links.json (уже связанные issues).

Выход: <OUT>/deliverables/CLAUDE_CODE_TASKS.md (или --out): шапка и инструкция агенту (templates/handoff-tasks.md),
карта материалов, эпики по разделам (SECTIONS ниже) с задачами-чекбоксами, макеты и референсы, эксперименты, приложение
(таблица ID → раздел → эпик → issue №, не вошедшие предложения с причиной, предпосылки вне выбранного, пропущенные
материалы). Пути — относительные от корня git-репозитория (`strategy/<дата>/…`), если <OUT> лежит в репозитории;
иначе — относительные от <OUT> (в шапке пометка «папка стратегии: <имя>»). --repo-prefix задаёт префикс вручную.

Раздел предложения (ровно один): ui → compliance → по категории (CATEGORY_SECTION). Признаки ui — привязанный макет,
теги ui/ux/design или (категория conversion/product и слова UI_STEMS/UI_WORDS в названии, описании, шагах). Раздел
experiments не забирает предложения: в нём — файлы research/experiments/E*.md и дешёвые проверки (cheap_test)
предложений горизонта now, у которых нет своего эксперимента.

Детерминированно, без сети (git вызывается только локально, чтобы найти корень репозитория). Идемпотентно: последняя
строка файла — `generated-by: handoff.py · sha256:<…>`; если файл правили вручную (суммы не сходятся или строки нет),
он не затирается — свежая версия кладётся рядом в *.generated.md (--force перезаписывает). --dry-run печатает результат
в stdout и ничего не пишет. --list-sections --json — массив разделов для карточек выбора (id, title, tasks, p0, …).
Код выхода: 0 — готово, 2 — нет реестра или неверные аргументы. Только стандартная библиотека.
"""
import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TEMPLATE = HERE.parent / "templates" / "handoff-tasks.md"
DEFAULT_NAME = "CLAUDE_CODE_TASKS.md"
MARKER_PREFIX = "generated-by: handoff.py · sha256:"
DETAILS = ("links", "brief", "full")
HORIZONS = {"now": ("now",), "next": ("now", "next"), "all": ("now", "next", "later", "vision")}
HORIZON_LABEL = {"now": "now (0–3 мес.)", "next": "now + next (до 12 мес.)", "all": "все горизонты"}
DEFAULTS = {"scope": ["all"], "detail": "brief", "horizon": "next"}

# Разделы-эпики: id, имя, номера разделов strategy.md (первый — основной), цель по умолчанию, о чём (для карточки выбора).
SECTIONS = [
    ("ui", "Интерфейс и дизайн", [7, 10], "Довести интерфейс до макетов: экраны, онбординг, витрина, язык дизайна и пути пользователя.",
     "экраны и макеты, язык дизайна, референсы, блок-схемы"),
    ("product", "Продукт и функции", [10], "Развивать функции продукта по дорожной карте с учётом зависимостей.",
     "новые функции и линии продукта"),
    ("platform", "Технологии, платформа, качество", [11], "Убрать технические препятствия росту: стек, тесты, CI, API, расширяемость.",
     "API, плагины, тесты, CI, долг"),
    ("acquisition", "Привлечение, контент, каталоги", [6, 4], "Привести новых пользователей через контент, каталоги, сообщества и партнёров.",
     "SEO, контент, каталоги, сообщества, партнёрства"),
    ("conversion", "Конверсия и онбординг", [7], "Сократить путь от первого визита до первой ценности.",
     "воронка и активация без экранных работ"),
    ("retention", "Удержание и поддержка", [9], "Возвращать пользователей и удерживать их.",
     "дайджесты, напоминания, возврат ушедших"),
    ("analytics", "Аналитика и измерения", [12], "Измерять воронку и ключевые метрики, чтобы принимать решения по данным.",
     "события, дашборды, когорты"),
    ("monetization", "Модель дохода и устойчивость", [8], "Выстроить устойчивую модель дохода или поддержки проекта.",
     "тарифы, цены, оплата, спонсорство"),
    ("localization", "Локализация и документация", [6, 11], "Открыть продукт новым языкам и рынкам, держать документацию актуальной.",
     "языки, локальные страницы, документация"),
    ("compliance", "Право, безопасность, риски", [13], "Снять правовые риски и риски безопасности до роста.",
     "лицензии, приватность, безопасность"),
    ("experiments", "Эксперименты и проверки гипотез", [12, 7], "Проверить ключевые гипотезы дёшево до крупных вложений.",
     "планы экспериментов и дешёвые проверки"),
]
SECTION_IDS = [s[0] for s in SECTIONS]
SECTION = {s[0]: {"id": s[0], "title": s[1], "strategy": s[2], "goal": s[3], "about": s[4]} for s in SECTIONS}
CATEGORY_SECTION = {"product": "product", "new_lines": "product", "platform": "platform", "acquisition": "acquisition",
                    "partnerships": "acquisition", "conversion": "conversion", "retention": "retention", "analytics": "analytics",
                    "monetization": "monetization", "localization": "localization"}
CATEGORY_RU = {"product": "продукт", "new_lines": "новые линии", "platform": "платформа", "acquisition": "привлечение",
               "partnerships": "партнёрства", "conversion": "конверсия", "retention": "удержание", "analytics": "аналитика",
               "monetization": "монетизация", "localization": "локализация"}
# личный режим (SM разд. 4, категории check_registry.PERSONAL_CATEGORIES): раздел эпика и подпись
CATEGORY_SECTION.update({"core": "product", "data-sources": "platform", "reliability": "platform", "privacy-security": "compliance",
                         "ux": "ui", "ai-quality": "product", "maintenance": "platform", "personal-analytics": "analytics"})
try:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from check_registry import CATEGORY_LABELS_RU as _CAT_ALL
    CATEGORY_RU = dict({k: v.lower() if k != "ux" else v for k, v in _CAT_ALL.items()}, **CATEGORY_RU)
except Exception:                                      # noqa: BLE001
    pass
# Признаки интерфейсной работы — единственное место со списком слов.
UI_TAGS = {"ui", "ux", "design"}
UI_TEXT_CATEGORIES = {"conversion", "product"}
UI_STEMS = ("экран", "интерфейс", "onboarding", "онбординг", "readme-витрин", "страниц", "макет")   # по началу слова
UI_WORDS = ("ui", "ux")                                                                             # целым словом
UI_RE = re.compile(r"(?<![\w-])(?:%s)|(?<![\w-])(?:%s)(?![\w])" % ("|".join(map(re.escape, UI_STEMS)), "|".join(UI_WORDS)), re.I | re.U)
COMPLIANCE_TAGS = {"legal", "security", "compliance"}
RISK_RU = {"legal": "право", "ip": "IP", "platform": "платформа", "privacy": "приватность", "tech": "техника", "reputation": "репутация"}
SECRET_RE = re.compile(r"(?:ghp_|gho_|github_pat_|sk-|xox[abps]-|AKIA)[A-Za-z0-9_\-]{8,}")
PRIO_ORDER = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
HZ_ORDER = {"now": 0, "next": 1, "later": 2, "vision": 3}


# ---------------------------------------------------------------- чтение
def jload(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def tload(path):
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def clean(s, n=None):
    """Одна строка без HTML-угловых скобок и вертикальных черт (таблицы), с обрезкой до n знаков."""
    s = re.sub(r"\s+", " ", str(s if s is not None else "")).strip()
    s = s.replace("<", "‹").replace(">", "›").replace("|", "/")
    s = SECRET_RE.sub("[скрыто]", s)
    if n and len(s) > n:
        s = s[:n - 1].rstrip() + "…"
    return s


def git_top(path):
    try:
        r = subprocess.run(["git", "-C", str(path), "rev-parse", "--show-toplevel"], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    top = r.stdout.strip()
    return Path(top).resolve() if r.returncode == 0 and top else None


def resolve_prefix(out, override=None):
    """(prefix, inside_repo, top). prefix — строка вида 'strategy/2026-10-11/' или ''."""
    if override is not None:
        p = str(override).replace("\\", "/").strip().strip("/")
        return ("" if p in ("", ".") else p + "/"), True, None
    top = git_top(out)
    if top:
        try:
            rel = out.relative_to(top).as_posix()
        except ValueError:
            rel = None
        if rel is not None:
            return ("" if rel == "." else rel + "/"), True, top
    return "", False, None


def parse_strategy(text):
    """{N: {"title", "goal", "body"}} по заголовкам `## N. …`."""
    out, cur = {}, None
    for line in text.splitlines():
        m = re.match(r"^##\s+(\d+)\.\s*(.+?)\s*$", line)
        if m:
            cur = int(m.group(1))
            out[cur] = {"title": m.group(2), "lines": []}
            continue
        if re.match(r"^#{1,2}\s", line):
            cur = None
            continue
        if cur is not None:
            out[cur]["lines"].append(line)
    for n, s in out.items():
        body = "\n".join(s.pop("lines"))
        s["body"] = body
        goal = ""
        for para in re.split(r"\n\s*\n", body):
            p = re.sub(r"!\[\[[^\]]*\]\]", "", para).strip()
            if p and not p.startswith(("|", "#", "```", "<!--")):
                goal = p
                break
        s["goal"] = clean(re.sub(r"[*_`]", "", goal), 300)
    return out


def md_section_lines(text, names):
    """Строки содержания первого раздела `## <имя>` из names (без пустых)."""
    lines = text.splitlines()
    for name in names:
        for i, line in enumerate(lines):
            if re.match(r"^#{2,3}\s+%s\b" % re.escape(name), line, re.I):
                out = []
                for nxt in lines[i + 1:]:
                    if re.match(r"^#{1,3}\s", nxt):
                        break
                    if nxt.strip():
                        out.append(nxt.strip())
                if out:
                    return out
    return []


def load(out):
    d = {"out": out}
    d["cfg"] = jload(out / "build" / "run-config.json", {}) or {}
    d["proposals"] = [p for p in (jload(out / "data" / "proposals.json", None) or []) if isinstance(p, dict) and p.get("id")]
    d["has_proposals"] = (out / "data" / "proposals.json").exists()
    scores = jload(out / "data" / "scores.json", []) or []
    d["scores"] = {s["id"]: s for s in scores if isinstance(s, dict) and s.get("id")}
    gantt = jload(out / "data" / "gantt.json", []) or []
    d["gantt"] = [g for g in gantt if isinstance(g, dict)]
    mi = jload(out / "data" / "mockups-index.json", []) or []
    d["mockups"] = [m for m in mi if isinstance(m, dict) and m.get("key")]
    d["refs"] = []
    for f in sorted((out / "design-refs").glob("*.json")) if (out / "design-refs").is_dir() else []:
        j = jload(f)
        if isinstance(j, dict):
            j["_json"] = "design-refs/" + f.name
            md = f.with_suffix(".md")
            j["_md"] = "design-refs/" + md.name if md.exists() else None
            d["refs"].append(j)
    flows = jload(out / "data" / "flows.json", []) or []
    d["flows"] = [f for f in flows if isinstance(f, dict)]
    d["strategy_text"] = tload(out / "research" / "strategy.md")
    d["strategy"] = parse_strategy(d["strategy_text"])
    d["specs"] = {}
    if (out / "research" / "specs").is_dir():
        for f in sorted((out / "research" / "specs").glob("*.md")):
            m = re.match(r"^(P\d{3,})", f.name)
            if m:
                d["specs"].setdefault(m.group(1), "research/specs/" + f.name)
    d["experiments"] = []
    if (out / "research" / "experiments").is_dir():
        for f in sorted((out / "research" / "experiments").glob("E*.md")):
            m = re.match(r"^(E\d+)", f.name)
            if not m:
                continue
            text = tload(f)
            head = "\n".join(text.splitlines()[:6])
            title = next((re.sub(r"^#\s+(E\d+\.?\s*)?", "", l).strip() for l in text.splitlines() if l.startswith("# ")), f.stem)
            pids = list(dict.fromkeys(re.findall(r"\bP\d{3,}\b", head)))
            kind = re.search(r"Тип:\s*([^·\n]+)", head)
            hyp = md_section_lines(text, ["Гипотеза", "Hypothesis"])
            met = md_section_lines(text, ["Метрики", "Метрика", "Metrics"])
            d["experiments"].append({"id": m.group(1), "path": "research/experiments/" + f.name, "title": clean(title, 120),
                                     "pids": pids, "kind": clean(kind.group(1), 40) if kind else "",
                                     "hypothesis": clean(hyp[0] if hyp else "", 300), "metric": clean(met[0] if met else "", 200)})
    links = jload(out / "data" / "issue-links.json", {}) or {}
    d["issue_links"] = {k: [int(x) for x in v if str(x).isdigit()] for k, v in links.items() if isinstance(v, list)} if isinstance(links, dict) else {}
    return d


# ---------------------------------------------------------------- классификация
def ui_text(p):
    parts = [p.get("title"), p.get("description")]
    for s in p.get("steps") or []:
        if isinstance(s, dict):
            parts += [s.get("what"), s.get("where"), s.get("how")]
        else:
            parts.append(s)
    return " ".join(str(x) for x in parts if x)


def proposal_mockups(p, d):
    """Пути mockups/concepts/… (существующие и нет) — из mockup, mockups и mockups-index."""
    keys = []
    for v in [p.get("mockup")] + list(p.get("mockups") or []):
        if v:
            v = str(v).replace("\\", "/").lstrip("./")
            keys.append(v if v.startswith("mockups/") else "mockups/" + v)
    for m in d["mockups"]:
        if p["id"] in (m.get("proposals") or []) and m.get("html"):
            keys.append(str(m["html"]))
    return list(dict.fromkeys(keys))


def classify(p, d):
    """(id раздела, причина)."""
    tags = {str(t).lower() for t in p.get("tags") or []}
    cat = p.get("category")
    if proposal_mockups(p, d):
        return "ui", "есть макет"
    if tags & UI_TAGS:
        return "ui", "тег " + ", ".join(sorted(tags & UI_TAGS))
    if cat in UI_TEXT_CATEGORIES:
        m = UI_RE.search(ui_text(p))
        if m:
            return "ui", "слово «%s»" % m.group(0).lower()
    risks = p.get("risks") or {}
    hot = [k for k in ("legal", "privacy") if isinstance(risks.get(k), (int, float)) and risks.get(k) >= 4]
    if tags & COMPLIANCE_TAGS:
        return "compliance", "тег " + ", ".join(sorted(tags & COMPLIANCE_TAGS))
    if hot:
        return "compliance", "риск %s ≥ 4" % "/".join(RISK_RU[k] for k in hot)
    if cat in CATEGORY_SECTION:
        return CATEGORY_SECTION[cat], "категория %s" % cat
    return "product", "неизвестная категория «%s» → продукт" % (cat or "—")


# ---------------------------------------------------------------- модель
class Ctx:
    def __init__(self, d, prefix, scope, detail, horizon):
        self.d, self.prefix, self.scope, self.detail, self.horizon = d, prefix, scope, detail, horizon
        self.out = d["out"]

    def exists(self, rel):
        return bool(rel) and (self.out / rel).exists()

    def path(self, rel):
        return "`%s%s`" % (self.prefix, rel)


def prio(d, pid):
    return (d["scores"].get(pid) or {}).get("priority") or "—"


def effort(p):
    e = p.get("effort_days")
    if isinstance(e, (list, tuple)) and len(e) == 2:
        return "%s–%s дн." % (e[0], e[1]) if e[0] != e[1] else "%s дн." % e[0]
    if isinstance(e, (int, float)):
        return "%s дн." % e
    return "усилие —"


def deps_of(d, p):
    s = d["scores"].get(p["id"]) or {}
    dep = s.get("blocked_by") if isinstance(s.get("blocked_by"), list) else p.get("dependencies") or []
    return [x for x in dict.fromkeys(dep) if x and x != p["id"]]


def strategy_refs(d, pid):
    return [n for n, s in sorted(d["strategy"].items()) if re.search(r"\b%s\b" % re.escape(pid), s["body"])]


def build(d, prefix, scope, detail, horizon):
    ctx = Ctx(d, prefix, scope, detail, horizon)
    hz = HORIZONS[horizon]
    by_id = {p["id"]: p for p in d["proposals"]}
    sec_of, reason_of = {}, {}
    for p in d["proposals"]:
        sec_of[p["id"]], reason_of[p["id"]] = classify(p, d)
    tasks = {s: [] for s in SECTION_IDS}
    all_tasks = {s: [] for s in SECTION_IDS}          # без фильтра горизонта (для --list-sections)
    excluded = []
    for p in d["proposals"]:
        sid, h = sec_of[p["id"]], p.get("horizon") or "now"
        t = {"id": p["id"], "kind": "proposal", "title": clean(p.get("title"), 120), "section": sid, "p": p,
             "priority": prio(d, p["id"]), "horizon": h, "reason": reason_of[p["id"]]}
        all_tasks[sid].append(t)
        if sid not in scope:
            excluded.append((p, sid, "раздел «%s» не выбран" % SECTION[sid]["title"]))
        elif h not in hz:
            excluded.append((p, sid, "горизонт %s вне выбранного (%s)" % (h, horizon)))
        else:
            tasks[sid].append(t)
    # общие работы по дизайну (раздел ui)
    ui_best = min([PRIO_ORDER.get(t["priority"], 9) for t in all_tasks["ui"]] or [9])
    ui_prio = "P%d" % ui_best if ui_best < 9 else "—"
    design = []
    if ctx.exists("mockups/tokens.css"):
        design.append({"id": "U01", "kind": "design", "title": "Язык дизайна: перенести токены из mockups/tokens.css в код",
                       "links": [("токены", "mockups/tokens.css")],
                       "text": "Цвета, шрифты, отступы, радиусы и тёмная тема из макетов — переменными в коде; без новых цветов вне токенов."})
    refs_md = [r for r in d["refs"] if r.get("_md")]
    if refs_md:
        design.append({"id": "U02", "kind": "design", "title": "Сверить реализацию с карточками референсов (%d)" % len(refs_md),
                       "links": [("карточка «%s»" % clean(r.get("title") or r["_md"], 60), r["_md"]) for r in refs_md],
                       "text": "По каждой карточке: элементы и зоны (hotspots) реализованы, «Что нужно доделать» закрыто, открытые вопросы сняты."})
    flows = [f for f in d["flows"] if f.get("svg") and ctx.exists(f["svg"])]
    if flows:
        design.append({"id": "U03", "kind": "design", "title": "Реализовать пути пользователя по блок-схемам (%d)" % len(flows),
                       "links": [("блок-схемы", "data/flows.json")] + [("схема «%s»" % clean(f.get("title") or f.get("key"), 60), f["svg"]) for f in flows],
                       "text": "Каждый узел схемы — экран или шаг; список «todo» узлов — в чек-лист; метрики узлов — в аналитику."})
    loose = [m for m in d["mockups"] if not m.get("proposals") and m.get("html") and ctx.exists(m["html"])
             and not str(m.get("key", "")).startswith("_")]
    if loose:
        design.append({"id": "U04", "kind": "design", "title": "Макеты без привязки к предложениям (%d): решить судьбу" % len(loose),
                       "links": [("макет %s" % m["key"], m["html"]) for m in loose],
                       "text": "Решить: реализовать (привязать к задаче) или отложить."})
    for t in design:
        t.update({"section": "ui", "priority": ui_prio, "horizon": "now"})
    all_tasks["ui"] = design + all_tasks["ui"]
    if "ui" in scope:
        tasks["ui"] = design + tasks["ui"]
    # эксперименты: файлы + дешёвые проверки предложений now без своего эксперимента
    exp_tasks, covered = [], set()
    for e in d["experiments"]:
        covered.update(e["pids"])
        pid = e["pids"][0] if e["pids"] else None
        exp_tasks.append({"id": e["id"], "kind": "experiment", "title": clean("Эксперимент: " + e["title"], 120), "section": "experiments",
                          "priority": prio(d, pid) if pid else "—", "horizon": "now", "e": e})   # план проверки — до реализации
    for p in d["proposals"]:
        if (p.get("horizon") or "now") == "now" and str(p.get("cheap_test") or "").strip() and p["id"] not in covered:
            exp_tasks.append({"id": "CT-" + p["id"], "kind": "check", "title": clean("Дешёвая проверка: " + (p.get("title") or ""), 120),
                              "section": "experiments", "priority": prio(d, p["id"]), "horizon": "now", "p": p})
    all_tasks["experiments"] = exp_tasks
    if "experiments" in scope:
        tasks["experiments"] = [t for t in exp_tasks if t["horizon"] in hz]

    def key(t):
        s = d["scores"].get(t.get("p", {}).get("id") if t.get("p") else None) or {}
        # планы экспериментов — первыми в своём эпике, дальше по приоритету; общие работы по дизайну — первыми среди равных
        first = 0 if t["kind"] == "experiment" else 1
        return (first, PRIO_ORDER.get(t["priority"], 9), 0 if t["kind"] == "design" else 1,
                s.get("dep_rank") or s.get("rank") or 10 ** 6, t["id"])
    for sid in SECTION_IDS:
        tasks[sid].sort(key=key)
        all_tasks[sid].sort(key=key)
    included = {t["id"]: t for sid in SECTION_IDS for t in tasks[sid]}
    # предпосылки вне выбранного
    outside = []
    for sid in SECTION_IDS:
        for t in tasks[sid]:
            if t["kind"] != "proposal":
                continue
            for dep in deps_of(d, t["p"]):
                if dep in included:
                    continue
                q = by_id.get(dep)
                if not q:
                    outside.append((t["id"], dep, "—", "нет в реестре"))
                    continue
                ds = sec_of[dep]
                why = ("раздел «%s» не выбран" % SECTION[ds]["title"]) if ds not in scope else "горизонт %s" % (q.get("horizon") or "—")
                outside.append((t["id"], dep, SECTION[ds]["title"], why))
    return {"ctx": ctx, "tasks": tasks, "all_tasks": all_tasks, "excluded": excluded, "outside": outside, "included": included,
            "sec_of": sec_of, "by_id": by_id}


# ---------------------------------------------------------------- отрисовка
def hz_label(h):
    return "later" if h == "vision" else h


def materials(m, t):
    """[(подпись, относительный путь)] существующих материалов задачи."""
    ctx, d = m["ctx"], m["ctx"].d
    out = []
    if t["kind"] == "design":
        return [(a, b) for a, b in t["links"] if ctx.exists(b)]
    if t["kind"] == "experiment":
        e = t["e"]
        out.append(("план эксперимента", e["path"]))
        for pid in e["pids"]:
            if pid in d["specs"]:
                out.append(("спецификация %s" % pid, d["specs"][pid]))
        return out
    p = t["p"]
    pid = p["id"]
    if pid in d["specs"]:
        out.append(("спецификация", d["specs"][pid]))
    for e in d["experiments"]:
        if pid in e["pids"]:
            out.append(("эксперимент %s" % e["id"], e["path"]))
    for html in proposal_mockups(p, d):
        if ctx.exists(html):
            out.append(("макет", html))
            png = html[:-5] + ".png" if html.endswith(".html") else None
            if png and ctx.exists(png):
                out.append(("PNG макета", png))
    for r in d["refs"]:
        hot = [h for h in r.get("hotspots") or [] if isinstance(h, dict) and h.get("proposal") == pid]
        if (pid in (r.get("proposals") or []) or hot) and r.get("_md"):
            out.append(("карточка референса", r["_md"]))
    for f in d["flows"]:
        if any(pid in (n.get("proposals") or []) for n in f.get("nodes") or [] if isinstance(n, dict)) and f.get("svg") and ctx.exists(f["svg"]):
            out.append(("блок-схема «%s»" % clean(f.get("title") or f.get("key"), 40), f["svg"]))
    return list(dict.fromkeys(out))


def strategy_link(m, nums):
    ctx, d = m["ctx"], m["ctx"].d
    if not ctx.exists("research/strategy.md"):
        return "стратегии нет (research/strategy.md не найден)"
    parts = []
    for n in nums:
        s = d["strategy"].get(n)
        parts.append("§ %d «%s»" % (n, clean(s["title"], 60)) if s else "§ %d (в strategy.md нет)" % n)
    return "%s %s" % (ctx.path("research/strategy.md"), ", ".join(parts))


def acceptance(m, p):
    ctx, d = m["ctx"], m["ctx"].d
    pid = p["id"]
    if pid in d["specs"]:
        lines = md_section_lines(tload(ctx.out / d["specs"][pid]), ["Критерии приёмки", "Acceptance criteria", "Требования"])
        crit = [clean(re.sub(r"^(?:[-*+]|\d+[.)])\s+(?:\[[ xX]\]\s*)?", "", l), 240) for l in lines]
        crit = [c for c in crit if c][:8]
        if crit:
            return crit, "из спецификации"
    crit = []
    for k in p.get("effect_kpi") or []:
        if isinstance(k, dict) and k.get("kpi"):
            crit.append("%s %s %s [%s]" % (clean(k.get("kpi"), 60), {"up": "↑", "down": "↓"}.get(k.get("direction"), ""),
                                            clean(k.get("range"), 40), clean(k.get("label") or "оценка", 20)))
    for g in d["gantt"]:
        if pid in (g.get("proposal_ids") or []) and g.get("done_criteria"):
            crit.append("%s: %s" % (g.get("id"), clean(g.get("done_criteria"), 160)))
    return crit, "из KPI и критериев готовности Ганта"


def kpi_line(p):
    out = []
    for k in p.get("effect_kpi") or []:
        if isinstance(k, dict) and k.get("kpi"):
            out.append("%s %s %s" % (clean(k["kpi"], 60), {"up": "↑", "down": "↓"}.get(k.get("direction"), ""), clean(k.get("range"), 40)))
    return "; ".join(out)


def task_lines(m, t):
    ctx, d, detail = m["ctx"], m["ctx"].d, m["ctx"].detail
    deps, checks = [], ""
    if t["kind"] == "proposal":
        for dep in deps_of(d, t["p"]):
            ds = m["sec_of"].get(dep)
            if dep in m["included"]:
                deps.append(dep if ds == t["section"] else "%s (эпик «%s»)" % (dep, SECTION[ds]["title"]))
            else:
                deps.append("%s (вне набора)" % dep)
    elif t["kind"] == "experiment" and t["e"]["pids"]:
        checks = " · проверяет: " + ", ".join(t["e"]["pids"])
    elif t["kind"] == "check":
        checks = " · проверяет: " + t["p"]["id"]
    eff = effort(t["p"]) if t["kind"] == "proposal" else ""
    meta = [t["priority"], "horizon:" + hz_label(t["horizon"])] + ([eff] if eff else [])
    head = "- [ ] **%s · %s** — %s" % (t["id"], t["title"], " · ".join(meta))
    if deps:
        head += " · после: " + ", ".join(deps)
    head += checks
    L = [head]
    ind = "  "
    mats = materials(m, t)
    if t["kind"] == "proposal":
        refs = strategy_refs(d, t["p"]["id"])
        if refs and ctx.exists("research/strategy.md"):
            mats_s = "упоминается в %s § %s" % (ctx.path("research/strategy.md"), ", ".join(map(str, refs)))
        else:
            mats_s = ""
    else:
        mats_s = ""
    if t["kind"] == "design":
        if detail != "links":
            L.append(ind + "- Суть: " + t["text"])
    elif t["kind"] == "experiment":
        e = t["e"]
        if detail != "links":
            if e["hypothesis"]:
                L.append(ind + "- Гипотеза: " + e["hypothesis"])
            if e["metric"]:
                L.append(ind + "- Метрика: " + e["metric"])
            if e["kind"]:
                L.append(ind + "- Тип: " + e["kind"])
    elif t["kind"] == "check":
        if detail != "links":
            L.append(ind + "- Как проверить: " + clean(t["p"].get("cheap_test"), 300))
            k = kpi_line(t["p"])
            if k:
                L.append(ind + "- Что измерить: " + k)
    else:
        p = t["p"]
        if detail != "links":
            gist = clean(" ".join(x for x in [str(p.get("description") or ""), str(p.get("rationale") or "")] if x), 400)
            if gist:
                L.append(ind + "- Суть: " + gist)
            steps = [s for s in p.get("steps") or [] if s]
            if steps:
                L.append(ind + "- Шаги:")
                for s in steps:
                    if isinstance(s, dict):
                        txt = clean(s.get("what"), 160)
                        extra = [x for x in [("где: " + clean(s.get("where"), 80)) if s.get("where") else "",
                                             ("как: " + clean(s.get("how"), 160)) if s.get("how") else ""] if x]
                        if extra:
                            txt += " (" + "; ".join(extra) + ")"
                        if s.get("doc_url"):
                            txt += " — " + clean(s["doc_url"], 200)
                    else:
                        txt = clean(s, 200)
                    L.append(ind * 2 + "- [ ] " + txt)
            k = kpi_line(p)
            if k:
                L.append(ind + "- KPI: " + k)
        if detail == "full":
            crit, src = acceptance(m, p)
            if crit:
                L.append(ind + "- Критерии приёмки (%s):" % src)
                L += [ind * 2 + "- [ ] " + c for c in crit]
            risks = p.get("risks") or {}
            hot = ["%s %s/5" % (RISK_RU.get(k, k), v) for k, v in risks.items() if k in RISK_RU and isinstance(v, (int, float)) and v >= 3]
            rtxt = ", ".join(hot) if hot else "низкие (все ≤ 2)"
            if risks.get("note"):
                rtxt += "; " + clean(risks["note"], 200)
            L.append(ind + "- Риски: " + rtxt)
            if p.get("cheap_test"):
                L.append(ind + "- Дешёвый тест: " + clean(p["cheap_test"], 300))
            ev = [e for e in p.get("evidence") or [] if isinstance(e, dict)][:2]
            evs = []
            for e in ev:
                src_ = e.get("url") or e.get("file")
                evs.append(clean(e.get("title") or e.get("kind") or "источник", 80) + (" — " + clean(src_, 200) if src_ else ""))
            L.append(ind + "- Доказательства: класс %s%s" % (p.get("evidence_class") or "—", ("; " + "; ".join(evs)) if evs else ""))
            for r in d["refs"]:
                hot_z = [h for h in r.get("hotspots") or [] if isinstance(h, dict) and h.get("proposal") == p["id"]]
                if hot_z and r.get("file") and ctx.exists(r["file"]):
                    zones = ", ".join("%s «%s» (%s)" % (h.get("n"), clean(h.get("title"), 40), h.get("state") or "—") for h in hot_z)
                    L.append(ind + "- Экран макета: %s, зоны: %s%s" % (ctx.path(r["file"]), zones,
                                                                       (" — карточка " + ctx.path(r["_md"])) if r.get("_md") else ""))
            for g in d["gantt"]:
                if p["id"] in (g.get("proposal_ids") or []):
                    L.append(ind + "- План: %s «%s», мес. %s–%s" % (g.get("id"), clean(g.get("task"), 80), g.get("start_month"), g.get("end_month")))
    if mats or mats_s:
        L.append(ind + "- Материалы: " + "; ".join(["%s %s" % (a, ctx.path(b)) for a, b in mats] + ([mats_s] if mats_s else [])))
    return L


def epic_kpi(tasks):
    cnt = {}
    for t in tasks:
        p = t.get("p") if t["kind"] == "proposal" else None
        for k in (p or {}).get("effect_kpi") or []:
            if isinstance(k, dict) and k.get("kpi"):
                cnt[clean(k["kpi"], 60)] = cnt.get(clean(k["kpi"], 60), 0) + 1
    top = sorted(cnt.items(), key=lambda x: (-x[1], x[0]))[:3]
    return ", ".join("%s (задач: %d)" % kv for kv in top)


def render_epic(m, sid):
    ctx, d = m["ctx"], m["ctx"].d
    s = SECTION[sid]
    ts = m["tasks"][sid]
    src = next((n for n in s["strategy"] if n in d["strategy"] and d["strategy"][n]["goal"]), None)
    p0 = sum(1 for t in ts if t["priority"] == "P0")
    L = ["### Эпик: %s (`area:%s`)" % (s["title"], sid), "",
         "- Цель: %s" % s["goal"]]
    if src is not None:
        L.append("- Из стратегии (§ %d): «%s»" % (src, d["strategy"][src]["goal"]))
    L.append("- Раздел стратегии: %s" % strategy_link(m, s["strategy"]))
    if sid == "experiments":
        mets = [t["e"]["metric"] for t in ts if t["kind"] == "experiment" and t["e"]["metric"]]
        L.append("- Критерий успеха: по каждой гипотезе принято решение «масштабировать / остановить» по заранее заданному порогу"
                 + ("; метрики: " + "; ".join(clean(x, 80) for x in mets[:3]) if mets else "") + ".")
    else:
        kp = epic_kpi(ts)
        L.append("- KPI / критерий успеха: %s." % (kp or "все задачи эпика закрыты, критерии приёмки выполнены"))
    L.append("- Задач: %d (P0: %d)." % (len(ts), p0))
    L.append("")
    for t in ts:
        L += task_lines(m, t)
    L.append("")
    return L


def prototype_block(ctx):
    """SM 7, п. 5 «связка с handoff»: есть prototype/HANDOFF.md и data/prototype.json → раздел «Перенос рабочего прототипа»
    (ядро, тесты канона, режимы, расхождения прототип ↔ боевая версия из HANDOFF.md). Нет файлов — пустой список."""
    out = ctx.out
    pj = jload(out / "data" / "prototype.json", None)
    hand = out / "prototype" / "HANDOFF.md"
    if not isinstance(pj, dict) or not hand.exists():
        return []
    L = ["## Перенос рабочего прототипа", "",
         "Рабочий прототип (фаза C8.5) — статический HTML+JS: ядро расчётов с тестами канона демо-данных и режимы интерфейса. "
         "Переносить ядро в боевой стек вместе с тестами: числа макетов = числа ядра = канон (`references/prototype.md`).", "",
         "| Что | Где |", "|---|---|"]
    for what, rel in (("Инструкция переноса", "prototype/HANDOFF.md"), ("Прототип", pj.get("path") or "prototype/index.html"),
                      ("Ядро расчётов", "prototype/js/core.js"), ("Тесты ядра (канон)", "prototype/js/core.test.js"),
                      ("Контракт оболочки", "prototype/js/kit.test.js"), ("Сверка канона", "prototype/tools/check_canon.py"),
                      ("Канон демо-данных", "data/demo-canon.json")):
        if ctx.exists(rel):
            L.append("| %s | %s |" % (what, ctx.path(rel)))
    ct, cn = pj.get("core_tests") or {}, pj.get("canon") or {}
    L += ["", "Статус: %s; режимы: %s; тесты ядра: %s прошло, %s упало; канон: кейсов %s, ошибок %s; смоук: %s." % (
        clean(pj.get("status") or "—", 20), ", ".join(map(str, pj.get("modes") or [])) or "—", ct.get("passed", "—"), ct.get("failed", "—"),
        cn.get("cases", "—"), cn.get("errors", "—"),
        ", ".join("%s — %s" % kv for kv in (pj.get("smoke") or {}).items()) or "—"), ""]
    text = tload(hand) or ""
    m = re.search(r"(?ms)^#{2,4}[^\n]*расхожден[^\n]*\n(.*?)(?=^#{1,4}\s|\Z)", text, re.I)
    items = [re.sub(r"^\s*[-*]\s+", "", x).strip() for x in (m.group(1).splitlines() if m else []) if re.match(r"^\s*[-*]\s+", x)]
    if items:
        L += ["**Расхождения прототип ↔ боевая версия** (из `HANDOFF.md`; в боевой версии решить явно):", ""]
        L += ["- %s" % clean(x, 200) for x in items[:20]] + [""]
    else:
        L += ["Расхождения прототип ↔ боевая версия — раздел «Расхождения» в `HANDOFF.md` (не найден — уточнить у агента регрессии).", ""]
    return L


def render(m, cfg, template_text):
    ctx, d = m["ctx"], m["ctx"].d
    out = ctx.out
    concept = cfg.get("mode") == "concept"
    product = (cfg.get("product") or {}).get("name") or (cfg.get("idea") or {}).get("name") or out.name
    date = cfg.get("created") or "—"
    sel = [sid for sid in SECTION_IDS if sid in ctx.scope]
    nonempty = [sid for sid in sel if m["tasks"][sid]]
    empty = [sid for sid in sel if not m["tasks"][sid]]
    all_t = [t for sid in SECTION_IDS for t in m["tasks"][sid]]
    if ctx.prefix:
        paths_note = "Все пути — от корня репозитория; папка стратегии: `%s`." % ctx.prefix.rstrip("/")
        paths_base = "даны от корня репозитория"
    else:
        paths_note = ("Папка стратегии: `%s` (вне git-репозитория). Все пути — относительно этой папки; укажите Claude Code, где она лежит."
                      % out.name)
        paths_base = "даны относительно папки стратегии `%s` (спроси у пользователя, где она лежит, если не нашёл)" % out.name
    remote = (cfg.get("repo") or {}).get("remote")
    repo = ("репозитория `%s`" % remote if remote and not concept else
            "текущего репозитория (уточни у пользователя, если репозиторий продукта ещё не создан)" if concept else "текущего репозитория")
    branch = (cfg.get("output") or {}).get("git_branch")
    sections_s = ", ".join("%s (`%s`)" % (SECTION[s]["title"], s) for s in sel) if set(sel) != set(SECTION_IDS) else "все"
    subs = {
        "PRODUCT": clean(product, 80), "DATE": date, "MODE": "концепция по идее" if concept else "по репозиторию",
        "SECTIONS": sections_s, "HORIZON": HORIZON_LABEL[ctx.horizon], "DETAIL": ctx.detail, "PATHS_NOTE": paths_note,
        "PATHS_BASE": paths_base, "REPO": repo,
        "STRATEGY": ctx.prefix + "research/strategy.md",
        "BRANCH_NOTE": (" (папка стратегии может быть только в ветке `%s`, пока её не влили)" % branch) if branch else "",
        "EPICS": str(len(nonempty)), "TASKS": str(len(all_t)), "P0": str(sum(1 for t in all_t if t["priority"] == "P0")),
        "P1": str(sum(1 for t in all_t if t["priority"] == "P1")), "EXCLUDED": str(len(m["excluded"])),
    }
    text = template_text
    for k, v in subs.items():
        text = text.replace("{%s}" % k, v)
    L = [text.rstrip(), ""]
    # (в) карта материалов
    L += ["## Карта материалов", "", "| Что | Где | Для чего |", "|---|---|---|"]
    mats = [
        ("Стратегия", "research/strategy.md", "цели эпиков, контекст задач (разделы `## N.`)"),
        ("Веб-страница стратегии", "deliverables/index.html", "обзор: реестр, графики, макеты (открыть в браузере)"),
        ("Отчёт", "deliverables/REPORT.md", "краткое изложение для людей"),
        ("Реестр предложений (JSON)", "data/proposals.json", "описание, шаги, KPI, риски по P-id"),
        ("Оценки и приоритеты (JSON)", "data/scores.json", "P0–P3, ранги, предпосылки `blocked_by`"),
        ("Оценки (CSV)", "data/scores.csv", "то же таблицей"),
        ("Реестр (XLSX)", "deliverables/strategy.xlsx", "реестр и план в таблице"),
        ("Спецификации", "research/specs", "требования и критерии приёмки топ-предложений"),
        ("Эксперименты", "research/experiments", "гипотезы, метрики, размер выборки"),
        ("Макеты", "mockups/concepts", "экраны-концепты (.html и .png)"),
        ("Язык дизайна", "mockups/tokens.css", "цвета, шрифты, отступы для кода"),
        ("Карточки референсов", "design-refs", "что на экране, зоны, что доделать"),
        ("Блок-схемы", "data/flows.json", "пути пользователя, узлы ↔ P-id"),
        ("План (Гант)", "data/gantt.json", "сроки, критерии готовности"),
        ("Kanban", "data/kanban.json", "колонки и карточки"),
        ("Аудит пробелов", "research/gap-audit.md", "предпосылки и пропущенное"),
        ("Вопросы владельцу", "research/questions-owner.md", "открытые решения — не превращать в задачи без ответа"),
        ("Досье идеи", "research/idea-dossier.md", "ответы владельца (режим идеи)"),
    ]
    missing_blocks = []
    for what, rel, why in mats:
        if ctx.exists(rel):
            L.append("| %s | %s | %s |" % (what, ctx.path(rel + ("/" if (out / rel).is_dir() else "")), why))
        else:
            missing_blocks.append(what)
    if missing_blocks:
        L += ["", "Нет в этой стратегии: %s." % ", ".join(missing_blocks)]
    L.append("")
    # (г) эпики
    L += ["## Эпики и задачи", "",
          "Формат строки: `ID · название — приоритет · горизонт · усилие · после: предпосылки`. Задачи упорядочены по приоритету и "
          "порядку зависимостей. ID `U..` — общие работы по дизайну, `E..` — эксперименты, `CT-P…` — дешёвые проверки.", ""]
    if not nonempty:
        L += ["_В выбранных разделах и горизонте задач нет._", ""]
    for sid in nonempty:
        L += render_epic(m, sid)
    if empty:
        L += ["Пустые выбранные разделы (задач нет в горизонте «%s»): %s." % (ctx.horizon, ", ".join(SECTION[s]["title"] for s in empty)), ""]
    # (е) макеты и референсы
    L += ["## Макеты и референсы", ""]
    inc_ids = set(m["included"])
    show = []
    for mk in d["mockups"]:
        props = [x for x in mk.get("proposals") or []]
        if (props and inc_ids & set(props)) or ("ui" in ctx.scope and mk.get("html") and ctx.exists(mk["html"])):
            show.append(mk)
    if not d["mockups"]:
        L += ["_Макетов нет (data/mockups-index.json отсутствует или пуст) — блок пропущен._", ""]
    elif not show:
        L += ["_Макеты есть, но не относятся к выбранным задачам._", ""]
    else:
        L += ["| Ключ | Название | P-id | HTML | PNG | Карточка референса |", "|---|---|---|---|---|---|"]
        for mk in show:
            html, png = mk.get("html"), mk.get("png")
            card = next((r["_md"] for r in d["refs"] if r.get("file") == html and r.get("_md")), None)
            L.append("| %s | %s | %s | %s | %s | %s |" % (
                clean(mk["key"], 40), clean(mk.get("title"), 60), ", ".join(mk.get("proposals") or []) or "—",
                ctx.path(html) if ctx.exists(html) else "нет файла", ctx.path(png) if png and ctx.exists(png) else "нет PNG",
                ctx.path(card) if card else "—"))
        L.append("")
    if d["refs"]:
        L += ["Карточки референсов: " + "; ".join("%s %s" % (clean(r.get("title"), 60), ctx.path(r["_md"])) for r in d["refs"] if r.get("_md")) + ".", ""]
    # (ж) эксперименты
    L += ["## Эксперименты", ""]
    exps = [e for e in d["experiments"] if "experiments" in ctx.scope or inc_ids & set(e["pids"])]
    if not d["experiments"]:
        L += ["_Планов экспериментов нет (папки research/experiments нет или она пуста) — блок пропущен._", ""]
    elif not exps:
        L += ["_Эксперименты есть, но не относятся к выбранным задачам._", ""]
    else:
        L += ["| ID | P-id | Гипотеза | Метрика | Файл |", "|---|---|---|---|---|"]
        for e in exps:
            L.append("| %s | %s | %s | %s | %s |" % (e["id"], ", ".join(e["pids"]) or "—", clean(e["hypothesis"], 160) or "—",
                                                   clean(e["metric"], 100) or "—", ctx.path(e["path"])))
        L.append("")
    L += prototype_block(ctx)
    # (з) приложение
    L += ["## Приложение", "", "### Таблица соответствия", "",
          "Заполняет Claude Code после создания issues: номера эпиков — в первой таблице, номера задач — в столбце «Issue №» второй.", "",
          "| Эпик | area | Задач | Issue № эпика |", "|---|---|---|---|"]
    L += ["| %s | %s | %d |  |" % (SECTION[sid]["title"], sid, len(m["tasks"][sid])) for sid in nonempty]
    L += ["", "| ID | Раздел | Эпик | Issue № |", "|---|---|---|---|"]
    for sid in nonempty:
        for t in m["tasks"][sid]:
            pid = t["p"]["id"] if t.get("p") and t["kind"] == "proposal" else t["id"]
            known = d["issue_links"].get(pid) or []
            L.append("| %s | %s | %s |  %s |" % (t["id"], sid, SECTION[sid]["title"], ", ".join("#%d" % n for n in known)))
    L.append("")
    L += ["### Предпосылки вне выбранного", ""]
    if m["outside"]:
        L += ["Эти предпосылки не входят в набор; создайте их отдельно или отметьте в задачах «blocked by» без номера.", "",
              "| Задача | Предпосылка | Где она | Почему не вошла |", "|---|---|---|---|"]
        for tid, dep, where, why in m["outside"]:
            q = m["by_id"].get(dep) or {}
            L.append("| %s | %s %s | %s | %s |" % (tid, dep, clean(q.get("title"), 60), where, why))
    else:
        L.append("Нет: все предпосылки выбранных задач входят в набор.")
    L.append("")
    L += ["### Не вошли в выбранные разделы", ""]
    if m["excluded"]:
        L += ["| P-id | Название | Раздел | Горизонт | Приоритет | Причина |", "|---|---|---|---|---|---|"]
        for p, sid, why in sorted(m["excluded"], key=lambda x: x[0]["id"]):
            L.append("| %s | %s | %s | %s | %s | %s |" % (p["id"], clean(p.get("title"), 70), SECTION[sid]["title"], p.get("horizon") or "—",
                                                       prio(d, p["id"]), why))
    else:
        L.append("Нет: вошли все предложения реестра.")
    L.append("")
    L += ["### Пропущенные материалы", ""]
    props_inc = [t for t in all_t if t["kind"] == "proposal"]
    no_spec = [t["id"] for t in props_inc if t["id"] not in d["specs"]]
    ui_no_mock = [t["id"] for t in m["tasks"]["ui"] if t["kind"] == "proposal" and not any(ctx.exists(h) for h in proposal_mockups(t["p"], d))]
    no_png = [mk["key"] for mk in d["mockups"] if mk.get("html") and ctx.exists(mk["html"]) and not (mk.get("png") and ctx.exists(mk["png"]))]
    broken = sorted({h for t in props_inc for h in proposal_mockups(t["p"], d) if not ctx.exists(h)})
    miss = []
    if no_spec:
        miss.append("Без спецификации (%d из %d): %s." % (len(no_spec), len(props_inc), ", ".join(no_spec)))
    if ui_no_mock:
        miss.append("Интерфейсные задачи без макета: %s." % ", ".join(ui_no_mock))
    if broken:
        miss.append("Макет указан, но файла нет: %s." % ", ".join(broken))
    if no_png:
        miss.append("Макеты без PNG (снимки не делались): %s." % ", ".join(no_png))
    if not d["scores"]:
        miss.append("Нет data/scores.json — приоритеты не проставлены (запустите score.py).")
    if not ctx.exists("research/strategy.md"):
        miss.append("Нет research/strategy.md — цели эпиков взяты по умолчанию.")
    else:
        need = sorted({n for sid in nonempty for n in SECTION[sid]["strategy"]} - set(d["strategy"]))
        if need:
            miss.append("В strategy.md нет разделов: %s — цели этих эпиков взяты по умолчанию." % ", ".join("§ %d" % n for n in need))
    if not d["experiments"]:
        miss.append("Нет планов экспериментов (research/experiments/E*.md).")
    if not d["mockups"]:
        miss.append("Нет макетов (data/mockups-index.json).")
    L += ["- " + x for x in miss] if miss else ["Нет."]
    L.append("")
    return "\n".join(L)


def scrub(text, out, top):
    """Абсолютные пути (папка прогона, корень репозитория, домашняя папка) → относительные или `~`."""
    reps = []
    if top:
        reps.append((str(top) + "/", ""))
    reps.append((str(out) + "/", ""))
    reps.append((str(out), "."))
    home = str(Path.home())
    if home and home != "/":
        reps.append((home, "~"))
    for a, b in reps:
        text = text.replace(a, b)
    return text


def finalize(body):
    body = body.rstrip() + "\n"
    h = hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]
    return body + "\n" + MARKER_PREFIX + h + "\n"


def is_pristine(text):
    """Файл не правили вручную: последняя строка — маркер с суммой содержимого до неё."""
    lines = text.rstrip("\n").split("\n")
    if not lines or not lines[-1].startswith(MARKER_PREFIX):
        return False
    body = "\n".join(lines[:-1]).rstrip("\n")
    body = body.rstrip() + "\n"
    return hashlib.sha256(body.encode("utf-8")).hexdigest()[:16] == lines[-1][len(MARKER_PREFIX):].strip()


def write_out(path, text, force):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not force and not is_pristine(path.read_text(encoding="utf-8", errors="replace")):
        path = path.with_name(path.stem + ".generated.md")
    if not path.exists() or path.read_text(encoding="utf-8", errors="replace") != text:
        path.write_text(text, encoding="utf-8")
    return path


# ---------------------------------------------------------------- параметры и запуск
def parse_scope(val):
    if val is None:
        return None
    items = val if isinstance(val, list) else re.split(r"[,\s]+", str(val))
    items = [str(x).strip().lower() for x in items if str(x).strip()]
    if not items or "all" in items:
        return list(SECTION_IDS)
    bad = [x for x in items if x not in SECTION]
    if bad:
        raise ValueError("неизвестные разделы: %s; допустимо: all, %s" % (", ".join(bad), ", ".join(SECTION_IDS)))
    return [s for s in SECTION_IDS if s in items]


def options(cfg, a):
    h = cfg.get("handoff") if isinstance(cfg.get("handoff"), dict) else {}
    scope = parse_scope(a.scope) if a.scope is not None else parse_scope(h.get("scope") or DEFAULTS["scope"])
    detail = a.detail or h.get("detail") or DEFAULTS["detail"]
    horizon = a.horizon or h.get("horizon") or DEFAULTS["horizon"]
    if detail not in DETAILS:
        raise ValueError("--detail: links|brief|full (получено %s)" % detail)
    if horizon not in HORIZONS:
        raise ValueError("--horizon: now|next|all (получено %s)" % horizon)
    return scope, detail, horizon, h


def list_sections(d, prefix, detail, horizon, template_text):
    full = build(d, prefix, list(SECTION_IDS), detail, horizon)
    res = []
    for sid in SECTION_IDS:
        ts = full["tasks"][sid]
        one = build(d, prefix, [sid], detail, horizon)
        body = "\n".join(render_epic(one, sid)) if ts else ""
        mock = sum(1 for t in ts if t["kind"] == "proposal" and any(full["ctx"].exists(h) for h in proposal_mockups(t["p"], d)))
        if sid == "ui":
            mock = max(mock, sum(1 for mk in d["mockups"] if mk.get("html") and full["ctx"].exists(mk["html"])))
        p0 = sum(1 for t in ts if t["priority"] == "P0")
        res.append({"id": sid, "title": SECTION[sid]["title"], "tasks": len(ts), "tasks_all_horizons": len(full["all_tasks"][sid]),
                    "p0": p0, "p1": sum(1 for t in ts if t["priority"] == "P1"), "has_mockups": mock > 0, "mockups": mock,
                    "strategy_sections": SECTION[sid]["strategy"], "approx_chars": len(body), "approx_lines": body.count("\n"),
                    "about": SECTION[sid]["about"],
                    "summary": "%d задач (P0: %d)%s; %s" % (len(ts), p0, ", макеты: %d" % mock if mock else "", SECTION[sid]["about"])})
    return res


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("out", help="папка стратегии <OUT>")
    ap.add_argument("--scope", help="разделы через запятую, all или ui (по умолчанию — handoff.scope из run-config, иначе all)")
    ap.add_argument("--detail", choices=DETAILS, help="links | brief | full (по умолчанию brief)")
    ap.add_argument("--horizon", choices=list(HORIZONS), help="now | next | all (по умолчанию next)")
    ap.add_argument("--out", dest="out_file", help="куда писать (по умолчанию <OUT>/deliverables/%s)" % DEFAULT_NAME)
    ap.add_argument("--repo-prefix", help="префикс путей от корня репозитория (по умолчанию — по git)")
    ap.add_argument("--list-sections", action="store_true", help="разделы с числом задач (для выбора)")
    ap.add_argument("--json", action="store_true", help="с --list-sections: вывод JSON")
    ap.add_argument("--dry-run", action="store_true", help="напечатать результат, ничего не писать")
    ap.add_argument("--force", action="store_true", help="перезаписать и правленный вручную файл")
    ap.add_argument("--save", action="store_true", help="записать выбор (--scope/--detail/--horizon) в run-config.json → handoff и снять ask_at_end (build_all дальше собирает файл сам)")
    a = ap.parse_args(argv)
    out = Path(a.out).resolve()
    d = load(out)
    if not d["has_proposals"]:
        print("ошибка: нет %s/data/proposals.json" % out, file=sys.stderr)
        return 2
    try:
        scope, detail, horizon, hcfg = options(d["cfg"], a)
    except ValueError as e:
        print("ошибка: %s" % e, file=sys.stderr)
        return 2
    if a.save:                                    # выбор владельца в конце прогона → run-config (build_all его подхватит)
        cp = out / "build" / "run-config.json"
        cfgd = jload(cp, {}) or {}
        cfgd["handoff"] = dict(cfgd.get("handoff") or {}, enabled=True, ask_at_end=False, scope=list(scope), detail=detail, horizon=horizon)
        cp.write_text(json.dumps(cfgd, ensure_ascii=False, indent=2), encoding="utf-8")
        print("run-config: handoff → scope=%s, detail=%s, horizon=%s" % (",".join(scope), detail, horizon))
    prefix, inside, top = resolve_prefix(out, a.repo_prefix)
    template_text = tload(TEMPLATE) or "# Задачи для Claude Code: {PRODUCT}\n"
    if a.list_sections:
        res = list_sections(d, prefix, detail, horizon, template_text)
        if a.json:
            print(json.dumps(res, ensure_ascii=False, indent=2))
        else:
            for r in res:
                print("%-12s %-36s задач %3d (всего %3d), P0 %2d%s" % (r["id"], r["title"], r["tasks"], r["tasks_all_horizons"], r["p0"],
                                                                     ", макеты" if r["has_mockups"] else ""))
        return 0
    m = build(d, prefix, scope, detail, horizon)
    text = finalize(scrub(render(m, d["cfg"], template_text), out, top))
    if a.dry_run:
        sys.stdout.write(text)
        return 0
    target = Path(a.out_file).resolve() if a.out_file else out / "deliverables" / DEFAULT_NAME
    written = write_out(target, text, a.force)
    n = sum(len(v) for v in m["tasks"].values())
    try:
        shown = written.relative_to(out).as_posix()
    except ValueError:
        shown = written.name
    print("Файл для Claude Code: %s (эпиков %d, задач %d, не вошли %d, разделы: %s, горизонт %s, подробность %s)"
          % (shown, sum(1 for v in m["tasks"].values() if v), n, len(m["excluded"]), ",".join(scope), horizon, detail))
    if written.name.endswith(".generated.md"):
        print("предупреждение: %s правили вручную — не перезаписан; свежая версия — %s; --force перезапишет"
              % (target.name, written.name), file=sys.stderr)
    if hcfg and hcfg.get("enabled") is False:
        print("заметка: в run-config handoff.enabled = false; файл собран по явному запуску", file=sys.stderr)
    if not d["scores"]:
        print("предупреждение: нет data/scores.json — приоритеты не проставлены", file=sys.stderr)
    if m["outside"]:
        print("предупреждение: предпосылок вне выбранного — %d (раздел «Предпосылки вне выбранного»)" % len(m["outside"]), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
