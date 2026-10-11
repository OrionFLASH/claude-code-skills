#!/usr/bin/env python3
"""Готовый бриф субагента из шаблона templates/briefs/*.md: подстановка плейсхолдеров из run-config и данных прогона.

  render_brief.py <шаблон | имя> --out <OUT> [--set КЛЮЧ=значение ...] [--set КЛЮЧ=@файл] [--group G1]
                  [--pass titles|details] [--suffix 06] [--base <корень>] [--print] [--allow-missing]
                  [--no-context] [--no-exist-check]
  render_brief.py <шаблон | имя> --list [--out <OUT>] [--set …]   все плейсхолдеры шаблона, откуда берутся и значения

Шаблон — путь к файлу или имя из templates/briefs (registry-generator, research-competitors, strategy-section, specs,
experiments, concept-analogs …). Выдача — <OUT>/build/briefs/<имя>[-<группа|суффикс>].md (группа — --group, иначе
--suffix, иначе значение PART), stdout — путь и строка-промпт агенту (--print — ещё и текст брифа).

Что подставляется (полный список с источниками — --list):
  - из build/run-config.json: продукт, язык, глубина, профиль, вид стратегии, рынки и пакеты локали, валюта, бюджет,
    горизонт и видение, режим (MODE: product | concept), тип продукта, минимумы scope.*, список конкурентов владельца,
    выгрузки аналитики, трафик, ограничения (FORBIDDEN); дата — сегодня;
  - пути: {OUT} — папка прогона от корня репозитория (repo.path или --base; вне его — от общей родительской папки,
    она названа строкой под заголовком), {SKILL_DIR} — через «~»; абсолютные пути с домашней папкой в брифе
    заменяются на «~» (предупреждение);
  - {MISSING_INPUTS} — по таблице выключенных направлений references/orchestration.md (scope.communities/legal/
    issues/keywords/events/unit_economics/design_mockups/design_refs/app_run, TypeSafe, режим идеи — нет кода и
    скриншотов) для файлов, упомянутых в шаблоне, плюс входы из разделов «Входы», которых ещё нет на диске
    (--no-exist-check — не проверять), плюс «keywords.json → volume пуст»; всё на месте — «нет»;
  - общий контекст: {PRODUCT_FACTS} — 5–10 строк о продукте (run-config + первые содержательные строки
    research/product-understanding.md), в режиме идеи {IDEA_FACTS} — из data/idea.json; если в шаблоне нет ни
    того, ни другого, раздел «## Контекст продукта» вставляется перед «## Входы» (--no-context — не вставлять);
  - вычисляемые: {WORDS_MAX} — лимиты слов из таблицы references/strategy-outline.md (режим идеи —
    concept-outline.md) для разделов из {SECTIONS} и глубины; {CHART_KEYS} — available из charts.py --list-keys;
    {MOCKUP_KEYS} — ключи data/mockups-index.json; {IDS} (specs) — топ-scope.specs_top по data/scores.json;
    {MY_TITLES}/{OTHER_TITLES} (registry-generator, --pass details) — заголовки своего и чужих черновиков;
    {CATEGORIES}/{COUNT} — из {QUOTAS}; бюджеты поиска {SEARCH_BUDGET}/{FETCH_BUDGET} — по брифу (orchestration.md),
    0 при sources.web_search=false; {KEYWORDS} — build/search-plan.md или data/keywords.json.
Остальное (QUOTAS, SECTIONS, PART, OTHER_PARTS, KEYS, BETS, PLATFORMS …) — --set. Значение из --set важнее
вычисленного; «@файл» — взять текст из файла.

Справочная строка «Плейсхолдеры: …» в начале шаблона НЕ раскрывается (остаётся справкой). Непарные плейсхолдеры
(в теле остался {КЛЮЧ} без значения или «{КЛЮЧ» без закрывающей скобки) — ошибка, код 1, файл не пишется
(--allow-missing — записать всё равно). Не считаются плейсхолдерами: синтаксис вставок стратегии ({rank:P032},
{deprank:…}, {model:…}), фигурные скобки кода и JSON-примеров, квантификаторы регулярных выражений ({0,40}) — всё,
что не {ЗАГЛАВНЫЕ_БУКВЫ}. Только стандартная библиотека.
"""
import argparse
import calendar
import glob
import json
import os
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent
TEMPLATES = SKILL / "templates" / "briefs"
PH_RE = re.compile(r"\{([A-Z][A-Z0-9_]*)\}")
OPEN_RE = re.compile(r"\{[A-Z][A-Z0-9_]*(?=[^A-Z0-9_}]|$)")
REF_RE = re.compile(r"^\s*Плейсхолдеры:")
PATH_RE = re.compile(r"\{OUT\}/([^\s`'\"),;»|]+)")
EXCEPTIONS = ["{rank:P…}", "{deprank:P…}", "{model:…}", "фигурные скобки кода/JSON", "квантификаторы {m,n}"]

DEPTH_TABLE = {   # references/phases.md, таблица глубины
    "COMMUNITIES_MIN": {"quick": 8, "standard": 20, "deep": 30, "exhaustive": 50},
    "KEYWORDS_MIN": {"quick": 20, "standard": 60, "deep": 120, "exhaustive": 200},
    "EVENTS_MIN": {"quick": 5, "standard": 15, "deep": 25, "exhaustive": 40},
    "COMPETITORS_MIN": {"quick": 6, "standard": 10, "deep": 15, "exhaustive": 25},
    "MOCKUPS_MIN": {"quick": 6, "standard": 12, "deep": 15, "exhaustive": 20},
    "TOP": {"quick": 15, "standard": 30, "deep": 30, "exhaustive": 50},
}
# бюджет веб-поиска по брифам (references/orchestration.md → «Бюджет веб-поиска»): (поиски, открытия страниц)
BUDGETS = {"research-competitors": (30, 60), "concept-analogs": (30, 60), "research-communities": (20, 40),
           "research-keywords": (20, 30), "research-events": (10, 20), "research-legal": (15, 30),
           "registry-generator": (5, 10), "gap-audit": (5, 10), "competitor-cards": (0, 10)}
CONCEPT_SCALE = {"quick": 0.3, "standard": 1.0, "deep": 1.5, "exhaustive": 2.0}

# таблица выключенных направлений (references/orchestration.md → «{MISSING_INPUTS}: условные входы»)
def _scope(cfg, key, default=True):
    v = (cfg.get("scope") or {}).get(key, default)
    return v is not False


DIRECTIONS = [
    (lambda c: not _scope(c, "communities"), ["data/communities.json", "research/communities.md"],
     "направление «сообщества» выключено владельцем (scope.communities=false)"),
    (lambda c: not _scope(c, "legal"), ["research/legal.md"],
     "правовое исследование выключено (scope.legal=false) — ограничения по чек-листу пакета локали в build/strategy-facts.md"),
    (lambda c: c.get("mode") != "concept" and (not _scope(c, "issues") or (c.get("sources") or {}).get("issues") is False),
     ["data/issues.json", "research/issues-demand.md"], "анализ Issues выключен (scope.issues=false; счётчики — в product-understanding.md)"),
    (lambda c: not _scope(c, "keywords"), ["data/keywords.json", "research/keywords.md"],
     "направление «поисковые запросы» выключено (scope.keywords=false)"),
    (lambda c: not _scope(c, "events"), ["data/events.json", "research/events.md"], "календарь событий выключен (scope.events=false)"),
    (lambda c: not _scope(c, "unit_economics"), ["data/model.json"], "юнит-экономика выключена (scope.unit_economics=false)"),
    (lambda c: not _scope(c, "design_mockups"), ["data/mockups-index.json", "mockups/concepts/*"],
     "макеты-концепты выключены (scope.design_mockups=false)"),
    (lambda c: not _scope(c, "design_refs"), ["design-refs/*"], "карточки design-refs выключены (scope.design_refs=false)"),
    (lambda c: c.get("mode") != "concept" and not _scope(c, "app_run", False), ["mockups/current/*", "data/site-audit.json"],
     "запуск приложения выключен или не удался (scope.app_run=false) — инвентарь по коду"),
    (lambda c: str((c.get("tools") or {}).get("typesafe", "auto")).lower() in ("off", "false") or not os.environ.get("TYPESAFE_API_KEY"),
     ["data/typesafe-jev.json"], "оценка TypeSafe не выполнялась (нет TYPESAFE_API_KEY или tools.typesafe=off)"),
    (lambda c: c.get("mode") == "concept",
     ["data/repo-scan.json", "data/repo-facts.json", "research/ui-inventory.md", "data/issues.json", "research/issues-demand.md",
      "mockups/current/*"], "режим идеи: продукта и репозитория ещё нет (код, скриншоты и Issues не анализировались)"),
    (lambda c: c.get("mode") != "concept" and not _scope(c, "repo_analysis"), ["data/repo-scan.json", "data/repo-facts.json"],
     "анализ репозитория выключен (scope.repo_analysis=false)"),
]


# ---------------------------------------------------------------- утилиты
def jload(path, default=None):
    p = Path(path)
    if not p.exists():
        return default
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default


def tilde(path):
    s, home = str(path), str(Path.home())
    return "~" + s[len(home):] if s == home or s.startswith(home + os.sep) else s


def clean(text):
    return re.sub(r"\s*\(Recommended\)\s*", "", str(text or "")).strip()


def add_months(d, n):
    y, m = divmod(d.month - 1 + int(n), 12)
    y, m = d.year + y, m + 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def plural_years(n):
    n = int(n)
    return "%d %s" % (n, "год" if n % 10 == 1 and n % 100 != 11 else ("года" if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14 else "лет"))


def template_path(arg):
    p = Path(arg)
    if p.exists() and p.is_file():
        return p
    name = arg[:-3] if arg.endswith(".md") else arg
    q = TEMPLATES / (name + ".md")
    if q.exists():
        return q
    raise SystemExit("нет шаблона %r (есть: %s)" % (arg, ", ".join(sorted(f.stem for f in TEMPLATES.glob("*.md")))))


# ---------------------------------------------------------------- контекст
class Ctx:
    def __init__(self, tpl_path, out, sets, group=None, pas=None, base=None, exist_check=True):
        self.tpl_path = tpl_path
        self.name = tpl_path.stem
        self.text = tpl_path.read_text(encoding="utf-8")
        self.out = Path(out).resolve() if out else None
        self.cfg = (jload(self.out / "build" / "run-config.json", {}) or {}) if self.out else {}
        self.sets = dict(sets)
        if group:
            self.sets.setdefault("GROUP", group)
        if pas:
            self.sets.setdefault("PASS", pas)
        self.group = group
        self.exist_check = exist_check
        self.concept = self.cfg.get("mode") == "concept"
        self.idea = (jload(self.out / "data" / "idea.json", {}) or {}) if self.out else {}
        self.base_note = None
        self.base = Path(base).resolve() if base else None
        self.cache = {}

    def c(self, *keys, default=None):
        v = self.cfg
        for k in keys:
            if not isinstance(v, dict):
                return default
            v = v.get(k)
        return default if v in (None, "") else v

    @property
    def depth(self):
        return self.c("strategy", "depth", default="standard")

    def get(self, name):
        if name in self.sets:
            return self.sets[name]
        if name not in self.cache:
            fn = RESOLVERS.get(name, (None, None))[1]
            self.cache[name] = fn(self) if (fn and self.out) else None
        return self.cache[name]


# ---------------------------------------------------------------- значения
def r_out(ctx):
    base = ctx.base or (Path(ctx.c("repo", "path")).resolve() if ctx.c("repo", "path") else Path.cwd().resolve())
    try:
        rel = ctx.out.relative_to(base)
        return str(rel) if str(rel) != "." else "."
    except ValueError:
        common = Path(os.path.commonpath([str(ctx.out), str(base)]))
        ctx.base_note = "Пути `{OUT}/…` в этом брифе — от папки `%s` (общая родительская папка репозитория и папки прогона)." % tilde(common)
        return os.path.relpath(str(ctx.out), str(common))


def r_markets(ctx):
    m = [x for x in (ctx.c("strategy", "markets") or []) if x and x != "auto"]
    return ", ".join(m) if m else None


def r_locale(ctx):
    m = [x for x in (ctx.c("strategy", "markets") or []) if x and x != "auto"] or [ctx.c("language", default="ru")]
    found = ["`%s/references/locales/%s.md`" % (tilde(SKILL), x) for x in m if (SKILL / "references" / "locales" / ("%s.md" % x)).exists()]
    return ", ".join(found) if found else "нет пакета"


def r_budget(ctx):
    b = ctx.c("strategy", "budget") or {}
    v = ", ".join(b.get("variants") or []) if isinstance(b, dict) else str(b)
    note = b.get("note") if isinstance(b, dict) else ""
    return (v or "zero") + ("; %s" % note if note else "")


def r_mode(ctx):
    if ctx.name == "flows":
        return None                                   # во flows.md MODE = draw|describe — только --set
    return "concept" if ctx.concept else "product"


def r_ptype(ctx):
    return ctx.idea.get("product_type") or ctx.c("product", "type")


def web_off(ctx):
    src = ctx.cfg.get("sources") or {}
    return src.get("web_search") is False or src.get("web_search_budget_per_hour") == 0


def r_search(ctx):
    if web_off(ctx):
        return "0 (веб-поиск выключен в run-config)"
    if ctx.name == "registry-generator" and ctx.get("PASS") == "titles":
        return "2"
    b = BUDGETS.get(ctx.name)
    return str(b[0]) if b else None


def r_fetch(ctx):
    if web_off(ctx):
        return "0 (веб-поиск выключен в run-config)"
    b = BUDGETS.get(ctx.name)
    return str(b[1]) if b else None


def depth_default(key, scope_key=None):
    def f(ctx):
        if scope_key and ctx.c("scope", scope_key) is not None:
            return str(ctx.c("scope", scope_key))
        return str(DEPTH_TABLE[key].get(ctx.depth, DEPTH_TABLE[key]["standard"]))
    return f


def r_count(ctx):
    if ctx.name == "experiments":
        return str(ctx.c("scope", "experiments", default=8))
    q = ctx.get("QUOTAS")
    if q:
        nums = [int(x) for x in re.findall(r"[—–:=-]\s*(\d+)", str(q))]
        return str(sum(nums)) if nums else None
    return None


def r_categories(ctx):
    q = ctx.get("QUOTAS")
    if not q:
        return None
    cats = re.findall(r"\b([a-z_]+)\b\s*[—–:=-]\s*\d+", str(q))
    return ", ".join(dict.fromkeys(cats)) or None


def scores_order(ctx):
    s = jload(ctx.out / "data" / "scores.json", []) or []
    return [x["id"] for x in sorted((x for x in s if isinstance(x, dict) and x.get("id")), key=lambda x: x.get("rank", 10 ** 6))]


def r_ids(ctx):
    if ctx.name != "specs":
        return None
    order = scores_order(ctx)
    n = int(ctx.c("scope", "specs_top", default=10))
    return ", ".join(order[:n]) or None


def draft_titles(ctx, mine):
    g = ctx.get("GROUP")
    rows = []
    for f in sorted((ctx.out / "data").glob("proposals-draft-*.json")):
        grp = f.stem[len("proposals-draft-"):]
        if (grp == g) != mine:
            continue
        raw = jload(f, [])
        raw = raw.get("proposals", []) if isinstance(raw, dict) else raw
        for p in raw or []:
            if isinstance(p, dict) and p.get("title"):
                rows.append("- %s — %s%s" % (p.get("id") or "?", p["title"], "" if mine else " (у %s)" % grp))
    return rows


def r_my_titles(ctx):
    if ctx.name != "registry-generator":
        return None
    if ctx.get("PASS") == "titles":
        return "— (проход titles: заголовки ещё не утверждены)"
    rows = draft_titles(ctx, True)
    return "\n" + "\n".join(rows) if rows else None


def r_other_titles(ctx):
    if ctx.name != "registry-generator":
        return None
    rows = draft_titles(ctx, False)
    if not rows:
        return "нет"
    return "\n" + "\n".join(rows)


def r_traffic(ctx):
    t = ctx.c("project", "traffic_hint")
    return str(t) if t else "неизвестно"


def r_hstart(ctx):
    return date.today().isoformat()


def r_hend(ctx):
    return add_months(date.today(), int(ctx.c("strategy", "horizon_months", default=12))).isoformat()


def r_owner_list(ctx):
    lst = ctx.c("sources", "competitor_list") or []
    return ", ".join(map(str, lst)) if lst else "нет"


def r_keywords(ctx):
    sp = ctx.out / "build" / "search-plan.md"
    if sp.exists():
        m = re.search(r"Ключевые слова[^:]*:\s*(.+)", sp.read_text(encoding="utf-8"))
        if m:
            return m.group(1).strip().rstrip(".")
    kw = jload(ctx.out / "data" / "keywords.json", []) or []
    qs = [k.get("query") for k in kw if isinstance(k, dict) and k.get("query")]
    if qs:
        return ", ".join(qs[:15])
    seeds = jload(ctx.out / "data" / "repo-facts.json", {}) or {}
    kws = seeds.get("keywords") if isinstance(seeds, dict) else None
    return ", ".join(kws[:15]) if isinstance(kws, list) and kws else None


def r_exports(ctx):
    lst = ctx.c("sources", "analytics_exports") or []
    return ", ".join(map(str, lst)) if lst else "нет"


def understanding_lines(ctx, limit=6):
    """Первые содержательные строки research/product-understanding.md (без заголовков, таблиц, комментариев, цитат)."""
    for name in ("research/product-understanding.md", "research/idea-dossier.md"):
        p = ctx.out / name
        if not p.exists():
            continue
        out = []
        for line in p.read_text(encoding="utf-8").splitlines():
            t = line.strip()
            if not t or t.startswith(("#", "|", "<!--", ">", "```", "---")):
                continue
            t = re.sub(r"^[-*]\s+", "", t)
            if len(t) < 15:
                continue
            out.append(t if len(t) <= 220 else t[:217].rsplit(" ", 1)[0] + "…")
            if len(out) >= limit:
                break
        if out:
            return out, name
    return [], None


# project.requester_role (intake.py, карточка «Роль») → подпись; совпадает с intake.ROLE_NAMES
REQUESTER_ROLES = {"owner": "владелец или команда продукта", "analyst": "сторонний аналитик / подрядчик", "partner": "партнёр",
                   "investor": "инвестор", "other": "другое"}


def r_product_facts(ctx):
    if ctx.concept:
        return idea_facts(ctx)
    c = ctx.c
    lines = []
    nm = c("product", "name") or "продукт"
    lines.append("Продукт: %s%s%s." % (nm, " (%s)" % c("product", "type") if c("product", "type") not in (None, "auto", "other") else "",
                                        ", %s" % c("product", "url") if c("product", "url") else ""))
    role, owner = c("project", "requester_role"), c("project", "product_owner")
    if role or owner:      # кто заказчик и чей продукт — от этого «мы» / «продукт» и адресат «вопросов владельцу» (B-1)
        lines.append("Заказчик: %s, владелец продукта: %s." % (REQUESTER_ROLES.get(role or "owner", role), owner or "не указан — уточнить"))
    if c("strategy", "goal") or c("strategy", "kind"):
        lines.append("Стратегия: %s; цель — %s." % (c("strategy", "kind") or "—", c("strategy", "goal") or "—"))
    mk = r_markets(ctx)
    lines.append("Рынки: %s; язык результатов: %s; валюта: %s." % (mk or "auto", c("language", default="ru"), c("project", "currency") or "—"))
    lines.append("Профиль: %s; команда: %s; бюджет: %s; горизонт %s мес., видение %s." % (
        c("strategy", "profile", default="standard"), c("project", "team_size") or "—", r_budget(ctx),
        c("strategy", "horizon_months", default=12), plural_years(c("strategy", "vision_years", default=3))))
    if c("product", "known_facts"):
        lines.append("Известно со слов владельца: %s" % str(c("product", "known_facts"))[:400])
    if c("strategy", "constraints"):
        lines.append("Ограничения: %s" % str(c("strategy", "constraints"))[:300])
    und, src = understanding_lines(ctx, limit=max(1, 10 - len(lines)))
    lines += und
    if src:
        lines.append("Подробно — `{OUT}/%s`." % src)
    while len(lines) < 5:
        lines.append("Цель проекта: %s; публикация кода: %s." % (c("project", "goal") or "—", c("project", "publish_code") or "—")
                     if len(lines) == 4 else "Подробных фактов о продукте ещё нет — см. входы ниже [допущение].")
    return "\n".join("- " + x for x in lines[:10])


def answers_by_header(ctx):
    ans = ctx.idea.get("answers") or (ctx.c("idea", "answers") or {})
    out = {}
    for k, v in (ans or {}).items():
        if isinstance(v, dict):
            a = v.get("answer")
            a = ", ".join(clean(x) for x in a) if isinstance(a, list) else clean(a)
            out[v.get("header") or k] = (a, v.get("theme"))
    return out


def idea_facts(ctx):
    if not ctx.concept and not ctx.idea:
        return None
    i, A = ctx.idea, answers_by_header(ctx)

    def a(*hs):
        return "; ".join("%s: %s" % (h.lower(), A[h][0]) for h in hs if h in A and A[h][0])

    lines = []
    if i.get("pitch") or ctx.c("idea", "pitch"):
        lines.append("Идея (дословно): %s" % (i.get("pitch") or ctx.c("idea", "pitch")))
    if a("Боль", "Сейчас"):
        lines.append("Проблема — %s." % a("Боль", "Сейчас"))
    seg = i.get("segment_label") or (A.get("Аудитория") or ("", ""))[0]
    lines.append("Аудитория: %s%s; рынки: %s." % (seg or "—", "; " + a("Сегмент") if a("Сегмент") else "", ", ".join(i.get("markets") or []) or r_markets(ctx) or "—"))
    if a("Ценность", "Отличие", "Ага-момент"):
        lines.append("Ядро ценности — %s." % a("Ценность", "Отличие", "Ага-момент"))
    if a("Форма", "MVP", "Срок MVP"):
        lines.append("MVP — %s; тип продукта: %s." % (a("Форма", "MVP", "Срок MVP"), i.get("product_type_label") or r_ptype(ctx) or "—"))
    lines.append("Модель денег: %s%s." % (i.get("monetization_label") or ctx.c("strategy", "monetization") or "—",
                                         "; " + a("Кто платит") if a("Кто платит") else ""))
    lines.append("Команда и ресурсы: %s чел., %s ч/нед., бюджет %s; профиль %s." % (
        i.get("team_size") or ctx.c("project", "team_size") or "—", i.get("hours_week") or "—",
        ", ".join(i.get("budget") or []) or r_budget(ctx), i.get("profile") or ctx.c("strategy", "profile", default="standard")))
    cons = [x for x in [ctx.c("strategy", "constraints"), ", ".join(i.get("sensitive") or [])] if x]
    lines.append("Ограничения: %s." % ("; ".join(cons) if cons else "не названы владельцем [допущение]"))
    if i.get("success_criteria") or ctx.c("strategy", "success_criteria"):
        lines.append("Успех: %s." % (i.get("success_criteria") or ctx.c("strategy", "success_criteria")))
    if (ctx.out / "research" / "idea-dossier.md").exists():
        lines.append("Подробно — `{OUT}/research/idea-dossier.md` (неотвеченное — допущения и открытые вопросы).")
    return "\n".join("- " + x for x in lines[:12])


def r_existing(ctx):
    if ctx.concept:
        return "нет (продукта ещё нет); вне продукта у владельца — только то, что перечислено в досье идеи"
    p = ctx.out / "research" / "product-understanding.md"
    if not p.exists():
        return None
    text = p.read_text(encoding="utf-8")
    m = re.search(r"(?ms)^#{2,4}\s*[^\n]*(уже есть|что есть|функци|инвентар|возможност)[^\n]*\n(.*?)(?=^#{1,4}\s|\Z)", text, re.I)
    if not m:
        return None
    items = [re.sub(r"^[-*]\s+", "", x.strip()) for x in m.group(2).splitlines() if x.strip().startswith(("-", "*"))]
    return "; ".join(items[:20]) + " (см. `{OUT}/research/product-understanding.md`)" if items else None


def r_forbidden(ctx):
    cons = ctx.c("strategy", "constraints")
    return str(cons) if cons else "особых запретов владелец не назвал; общие — правила площадок, право и позиционирование из входов"


def r_words(ctx):
    secs = ctx.get("SECTIONS")
    if not secs:
        return None
    nums = [int(x) for x in re.findall(r"(?<![\d.])(\d{1,2})\.", str(secs))]
    if not nums:
        return None
    outline = SKILL / "references" / ("concept-outline.md" if ctx.concept else "strategy-outline.md")
    rows = {}
    head = None
    for line in outline.read_text(encoding="utf-8").splitlines():
        cells = [x.strip() for x in line.strip().strip("|").split("|")]
        if line.startswith("| №"):
            head = cells
            continue
        if head and len(cells) == len(head) and cells[0].isdigit():
            rows[int(cells[0])] = dict(zip(head, cells))
    depth = ctx.depth
    out = []
    for n in nums:
        r = rows.get(n)
        if not r:
            continue
        if depth in r:
            val, scale = r[depth], 1.0
        else:                                         # concept-outline: только standard — масштаб по глубине
            val, scale = r.get("standard", "—"), CONCEPT_SCALE.get(depth, 1.0)
        m = re.findall(r"\d[\d\s ]*", val)
        if len(m) == 2 and scale != 1.0:
            lo, hi = (int(re.sub(r"\D", "", x)) for x in m)
            val = "%d / %d" % (round(lo * scale, -1), round(hi * scale, -1))
        out.append("%d. %s — %s слов" % (n, r.get("Раздел", ""), val))
    return "; ".join(out) or None


def r_part(ctx):
    secs = ctx.get("SECTIONS")
    m = re.search(r"(?<![\d.])(\d{1,2})\.", str(secs or ""))
    return "%02d" % int(m.group(1)) if m else None


def r_chart_keys(ctx):
    try:
        r = subprocess.run([sys.executable, "-B", str(HERE / "charts.py"), str(ctx.out), "--list-keys"],
                           capture_output=True, text=True, timeout=120)
        keys = json.loads(r.stdout).get("available") or []
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
    return ", ".join(keys) if keys else "графиков нет"


def r_mockup_keys(ctx):
    idx = jload(ctx.out / "data" / "mockups-index.json", []) or []
    keys = [x.get("key") for x in idx if isinstance(x, dict) and x.get("key")]
    return ", ".join(keys) if keys else "макетов ещё нет"


def r_card00(ctx):
    return "есть — ссылаться" if list((ctx.out / "design-refs").glob("00-*.json")) else "нет — элементы набора помечать `shared` без ссылки"


def r_design_answers(ctx):
    A = answers_by_header(ctx)
    items = ["%s: %s" % (h, v) for h, (v, theme) in A.items() if theme == "design" and v]
    return "; ".join(items) if items else "не заданы — допущения"


def r_name_hints(ctx):
    A = answers_by_header(ctx)
    items = ["%s: %s" % (h, v) for h, (v, _) in A.items() if "назван" in h.lower() and v]
    return "; ".join(items) if items else "нет"


def r_steps(ctx):
    return "1-3" if ctx.cfg.get("autopilot") else None


def r_missing(ctx):
    text = ctx.text
    lines, covered = [], set()
    for cond, files, why in DIRECTIONS:
        try:
            on = cond(ctx.cfg)
        except Exception:                             # noqa: BLE001 — кривой конфиг не должен ронять рендер
            on = False
        if not on:
            continue
        def mentioned(f):
            if ("{OUT}/" + f.rstrip("*")) in text:
                return True
            base = f.split("/")[-1]
            return "*" not in base and base in text

        mentioned = [f for f in files if mentioned(f)]
        new = [f for f in mentioned if f not in covered]
        if new:
            covered.update(new)
            lines.append("- %s — %s;" % (", ".join(new), why))
    if ctx.exist_check:
        sections = re.findall(r"(?ms)^## Входы(?![^\n]*которых нет)[^\n]*\n(.*?)(?=^## |\Z)", text)
        absent = []
        for sec in sections:
            for m in PATH_RE.finditer(sec):
                rel = m.group(1).rstrip(".:")
                if "<" in rel or "{" in rel or rel in covered or any(rel.startswith(c.rstrip("*")) and c.endswith("*") for c in covered):
                    continue
                path = ctx.out / rel
                exists = bool(glob.glob(str(path))) if any(ch in rel for ch in "*?[") else path.exists()
                if not exists and rel not in absent:
                    absent.append(rel)
        if absent:
            lines.append("- %s — нет на момент подготовки брифа (фаза ещё не наступила или не выполнялась);" % ", ".join(absent))
    kw = jload(ctx.out / "data" / "keywords.json", None)
    if isinstance(kw, list) and kw and all(isinstance(k, dict) and k.get("volume") in (None, "") for k in kw) and "keywords.json" in text:
        lines.append("- keywords.json → volume — объёмов нет (вход в инструменты не выполнялся), используй кластеры и конкуренцию;")
    if not lines:
        return "нет"
    lines[-1] = lines[-1].rstrip(";") + "."
    return "\n" + "\n".join(lines)


def const(v):
    return lambda ctx: v


def cfgv(*keys, fmt=None, default=None):
    def f(ctx):
        v = ctx.c(*keys, default=default)
        if v is None:
            return None
        return fmt(v) if fmt else str(v)
    return f


# имя → (откуда, функция)
RESOLVERS = {
    "OUT": ("вычисляется: папка прогона от корня репозитория (run-config repo.path или --base)", r_out),
    "SKILL_DIR": ("вычисляется: папка скилла через ~", lambda ctx: tilde(SKILL)),
    "PRODUCT": ("run-config product.name (режим идеи — idea.name)", lambda ctx: ctx.idea.get("name") or ctx.c("product", "name") or ctx.c("idea", "name")),
    "LANG": ("run-config language", cfgv("language", default="ru")),
    "DEPTH": ("run-config strategy.depth", cfgv("strategy", "depth", default="standard")),
    "DATE": ("сегодня (ISO)", lambda ctx: date.today().isoformat()),
    "PROFILE": ("run-config strategy.profile", cfgv("strategy", "profile", default="standard")),
    "MARKETS": ("run-config strategy.markets", r_markets),
    "LOCALE": ("вычисляется: references/locales/<язык>.md для языков рынков", r_locale),
    "CURRENCY": ("run-config project.currency", cfgv("project", "currency")),
    "KIND": ("run-config strategy.kind", cfgv("strategy", "kind")),
    "HORIZON": ("run-config strategy.horizon_months", cfgv("strategy", "horizon_months", fmt=lambda v: "%s мес." % v)),
    "VISION": ("run-config strategy.vision_years", cfgv("strategy", "vision_years", fmt=plural_years)),
    "BUDGET_VARIANTS": ("run-config strategy.budget.variants (+ note)", r_budget),
    "MODE": ("run-config mode: concept | product (во flows.md — только --set draw|describe)", r_mode),
    "PRODUCT_TYPE": ("data/idea.json product_type или run-config product.type", r_ptype),
    "MISSING_INPUTS": ("вычисляется: таблица выключенных направлений (orchestration.md) + отсутствующие входы шаблона", r_missing),
    "SEARCH_BUDGET": ("по брифу (orchestration.md → «Бюджет веб-поиска»); 0 при sources.web_search=false", r_search),
    "FETCH_BUDGET": ("по брифу (orchestration.md → «Бюджет веб-поиска»); 0 при sources.web_search=false", r_fetch),
    "COMPETITORS_MIN": ("run-config scope.competitors_min или таблица глубины", depth_default("COMPETITORS_MIN", "competitors_min")),
    "COMMUNITIES_MIN": ("таблица глубины (references/phases.md)", depth_default("COMMUNITIES_MIN", "communities_min")),
    "KEYWORDS_MIN": ("таблица глубины (references/phases.md)", depth_default("KEYWORDS_MIN", "keywords_min")),
    "EVENTS_MIN": ("таблица глубины (references/phases.md)", depth_default("EVENTS_MIN", "events_min")),
    "MOCKUPS_MIN": ("run-config scope.mockups_min или таблица глубины", depth_default("MOCKUPS_MIN", "mockups_min")),
    "TOP": ("таблица глубины (топ аудита 15/30/50)", depth_default("TOP")),
    "G7_MAX": ("по умолчанию 10", const("10")),
    "COUNT": ("experiments — scope.experiments; registry-generator — сумма {QUOTAS}; иначе --set", r_count),
    "IDS": ("specs: топ-scope.specs_top по data/scores.json", r_ids),
    "CANDIDATES": ("по умолчанию «выбери сам из топ-30»", const("выбери сам из топ-30")),
    "TRAFFIC": ("run-config project.traffic_hint или «неизвестно»", r_traffic),
    "HORIZON_START": ("сегодня", r_hstart),
    "HORIZON_END": ("сегодня + strategy.horizon_months", r_hend),
    "OWNER_LIST": ("run-config sources.competitor_list или «нет»", r_owner_list),
    "KEYWORDS": ("build/search-plan.md («Ключевые слова…») или data/keywords.json", r_keywords),
    "SEED_KEYWORDS": ("build/search-plan.md или data/keywords.json", r_keywords),
    "ANALYTICS_EXPORTS": ("run-config sources.analytics_exports или «нет»", r_exports),
    "PRODUCT_FACTS": ("общий контекст: run-config + research/product-understanding.md (режим идеи — data/idea.json)", r_product_facts),
    "IDEA_FACTS": ("общий контекст идеи: data/idea.json + run-config", idea_facts),
    "EXISTING": ("режим идеи — «нет»; иначе раздел «Что уже есть/Функции» research/product-understanding.md", r_existing),
    "FORBIDDEN": ("run-config strategy.constraints или общая формулировка", r_forbidden),
    "GROUP": ("--group", const(None)),
    "PASS": ("--pass titles|details", const(None)),
    "CATEGORIES": ("коды из {QUOTAS}", r_categories),
    "QUOTAS": ("--set (квоты после закрытия пересечений)", const(None)),
    "MY_TITLES": ("registry-generator --pass details: заголовки data/proposals-draft-<GROUP>.json", r_my_titles),
    "OTHER_TITLES": ("registry-generator: заголовки чужих черновиков или «нет»", r_other_titles),
    "WORDS_MAX": ("вычисляется: таблица объёма outline для {SECTIONS} и глубины", r_words),
    "PART": ("номер первого раздела из {SECTIONS} (06) или --set", r_part),
    "CHART_KEYS": ("вычисляется: charts.py <OUT> --list-keys → available", r_chart_keys),
    "MOCKUP_KEYS": ("data/mockups-index.json → key или «макетов ещё нет»", r_mockup_keys),
    "EXTRA": ("по умолчанию «нет»", const("нет")),
    "CARD00": ("design-refs/00-*.json есть/нет", r_card00),
    "FLOWS_OUT": ("по умолчанию data/flows.json", const("data/flows.json")),
    "SLUGS": ("по умолчанию «все»", const("все")),
    "CHOSEN": ("по умолчанию «нет»", const("нет")),
    "DESIGN_ANSWERS": ("ответы темы «дизайн» из data/idea.json", r_design_answers),
    "NAME_HINTS": ("ответ «Название» из data/idea.json или «нет»", r_name_hints),
    "STEPS": ("autopilot — «1-3», иначе --set", r_steps),
}


# ---------------------------------------------------------------- рендер
# многострочные значения в середине фразы: (первое упоминание — список ниже, повторные — ссылка выше)
SHORT = {"MISSING_INPUTS": ("(список ниже)", "списке «Входы, которых нет в этом прогоне»"),
         "OTHER_TITLES": ("«чужие заголовки» (список ниже)", "«чужие заголовки» (см. список выше)"),
         "MY_TITLES": ("утверждённые заголовки группы (список ниже)", "утверждённые заголовки группы (см. список выше)"),
         "PRODUCT_FACTS": ("контекст продукта (ниже)", "контекст продукта (см. выше)"),
         "IDEA_FACTS": ("контекст идеи (ниже)", "контекст идеи (см. выше)")}


def is_full(line, name):
    """Плейсхолдер один в строке или в её конце после метки («**Чужие заголовки:** {OTHER_TITLES}»)."""
    t = line.rstrip()
    return t.strip() == "{%s}" % name or t.endswith("{%s}" % name)


def placeholders(text, skip_ref=True):
    names, ref_idx = [], None
    for k, line in enumerate(text.splitlines()):
        if skip_ref and ref_idx is None and REF_RE.match(line):
            ref_idx = k
            continue
        for m in PH_RE.finditer(line):
            if m.group(1) not in names:
                names.append(m.group(1))
    return names, ref_idx


def render(ctx, add_context=True):
    """Возвращает (текст, ошибки, предупреждения, значения)."""
    text = ctx.text
    names, ref_idx = placeholders(text)
    values, missing = {}, []
    out_v = ctx.get("OUT")
    for n in ["OUT"] + [x for x in names if x != "OUT"]:
        v = ctx.get(n)
        if v is None:
            if n in names:
                missing.append(n)
        else:
            values[n] = str(v) if n == "OUT" or out_v is None else str(v).replace("{OUT}", str(out_v))
    errors, warns = [], []
    lines = text.splitlines()
    for k, line in enumerate(lines):
        if k == ref_idx:
            continue
        for m in OPEN_RE.finditer(line):
            errors.append("строка %d: непарная скобка %r" % (k + 1, m.group(0)))
    if missing:
        errors.append("непарные плейсхолдеры (нет значения): %s — задайте --set КЛЮЧ=значение (откуда берутся — --list)"
                      % ", ".join("{%s}" % n for n in missing))
    multi = {n for n, v in values.items() if "\n" in v}
    has_full = {n for n in multi for k, line in enumerate(lines) if k != ref_idx and is_full(line, n)}
    shown = set()
    out_lines = []
    for k, line in enumerate(lines):
        if k == ref_idx:
            out_lines.append(line)
            continue
        tail = []

        def sub(m, line=line, tail=tail):
            n = m.group(1)
            if n not in values:
                return m.group(0)
            if n not in multi:
                return values[n]
            if is_full(line, n) and n not in shown:
                shown.add(n)
                return values[n]
            if n not in shown and n not in has_full:   # полного места нет — список сразу после строки
                shown.add(n)
                tail.append(values[n].strip("\n"))
                return SHORT.get(n, ("(см. ниже)", ""))[0]
            return SHORT.get(n, ("", "(см. выше)"))[1]
        out_lines.append(PH_RE.sub(sub, line))
        out_lines += tail
    body = "\n".join(out_lines) + ("\n" if text.endswith("\n") else "")
    if add_context and "PRODUCT_FACTS" not in names and "IDEA_FACTS" not in names and ctx.out:
        ctxv = ctx.get("IDEA_FACTS") if ctx.concept else ctx.get("PRODUCT_FACTS")
        if ctxv:
            block = "## Контекст %s\n%s\n\n" % ("идеи" if ctx.concept else "продукта", ctxv.replace("{OUT}", values.get("OUT", "{OUT}")))
            m = re.search(r"(?m)^## Входы", body)
            body = body[:m.start()] + block + body[m.start():] if m else body + "\n" + block
    if ctx.base_note:
        first = body.split("\n", 1)
        body = first[0] + "\n\n> " + ctx.base_note + ("\n" + first[1] if len(first) > 1 else "\n")
    home = str(Path.home())
    if home and home in body:
        n = body.count(home)
        body = body.replace(home, "~")
        warns.append("абсолютные пути с домашней папкой заменены на «~» (%d)" % n)
    return body, errors, warns, values


def out_name(ctx, suffix=None):
    suf = ctx.group or suffix or ctx.sets.get("PART") or (ctx.get("PART") if ctx.name == "strategy-section" else None)
    return "%s%s.md" % (ctx.name, "-%s" % re.sub(r"[^\w.-]+", "_", str(suf)) if suf else "")


def parse_sets(items):
    out = {}
    for it in items or []:
        if "=" not in it:
            raise SystemExit("--set %r: нужно КЛЮЧ=значение" % it)
        k, v = it.split("=", 1)
        k = k.strip().strip("{}").upper()
        if v.startswith("@"):
            v = Path(v[1:]).read_text(encoding="utf-8").rstrip("\n")
        out[k] = v
    return out


def do_list(ctx):
    names, ref_idx = placeholders(ctx.text)
    every, _ = placeholders(ctx.text, skip_ref=False)
    ref_only = [n for n in every if n not in names]
    print("Шаблон %s: плейсхолдеров в тексте %d%s" % (ctx.tpl_path.name, len(names),
                                                     "" if ctx.out else " (без --out значения не вычисляются)"))
    for n in names + ref_only:
        if n == (ref_only[0] if ref_only else None):
            print("Только в справочной строке (в тексте брифа не используются):")
        src = RESOLVERS.get(n, ("нужно --set", None))[0]
        if n in ctx.sets:
            src = "--set (" + src + ")"
        v = ctx.get(n) if ctx.out or n in ctx.sets else None
        shown = "—" if v is None else re.sub(r"\s+", " ", str(v)).strip()
        if len(shown) > 110:
            shown = shown[:107] + "…"
        print("  {%s}\n      откуда: %s\n      значение: %s" % (n, src, shown if v is not None else "нет — нужно --set %s=…" % n))
    if ref_idx is not None:
        print("Справочная строка «Плейсхолдеры: …» (строка %d) не раскрывается." % (ref_idx + 1))
    print("Не плейсхолдеры (исключения): %s." % "; ".join(EXCEPTIONS))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Готовый бриф субагента из шаблона templates/briefs/*.md.")
    ap.add_argument("template", help="имя шаблона (registry-generator, specs …) или путь к .md")
    ap.add_argument("--out", help="папка прогона <OUT>")
    ap.add_argument("--set", action="append", default=[], metavar="КЛЮЧ=значение", help="значение плейсхолдера (@файл — из файла)")
    ap.add_argument("--group", help="группа генератора (G1…) — {GROUP} и суффикс имени файла")
    ap.add_argument("--pass", dest="pas", choices=["titles", "details"], help="проход генератора реестра — {PASS}")
    ap.add_argument("--suffix", help="суффикс имени готового брифа (если нет --group)")
    ap.add_argument("--base", help="корень для относительных путей {OUT} (по умолчанию run-config repo.path)")
    ap.add_argument("--list", action="store_true", help="перечислить плейсхолдеры шаблона, их источники и значения")
    ap.add_argument("--print", dest="show", action="store_true", help="напечатать готовый бриф")
    ap.add_argument("--allow-missing", action="store_true", help="записать бриф, даже если остались непарные плейсхолдеры")
    ap.add_argument("--no-context", action="store_true", help="не вставлять раздел «Контекст продукта», если его нет в шаблоне")
    ap.add_argument("--no-exist-check", action="store_true", help="не перечислять в {MISSING_INPUTS} отсутствующие на диске входы")
    a = ap.parse_args(argv)
    tpl = template_path(a.template)
    if not a.out and not a.list:
        ap.error("нужен --out <OUT> (или --list)")
    if a.out and not (Path(a.out) / "build" / "run-config.json").exists():
        print("нет %s/build/run-config.json — значения из конфига не подставятся" % a.out, file=sys.stderr)
    ctx = Ctx(tpl, a.out, parse_sets(a.set), a.group, a.pas, a.base, exist_check=not a.no_exist_check)
    if a.list:
        return do_list(ctx)
    body, errors, warns, values = render(ctx, add_context=not a.no_context)
    for w in warns:
        print("  ! " + w, file=sys.stderr)
    dest = ctx.out / "build" / "briefs" / out_name(ctx, a.suffix)
    if errors:
        for e in errors:
            print("ОШИБКА: " + e)
        if not a.allow_missing:
            print("Бриф не записан (%s). Исключения, которые не считаются плейсхолдерами: %s." % (dest.name, "; ".join(EXCEPTIONS)))
            return 1
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(body, encoding="utf-8")
    rel = "%s/build/briefs/%s" % (values.get("OUT", "<OUT>"), dest.name)
    if a.show:
        print(body)
    print("Записано: %s (плейсхолдеров подставлено %d%s)" % (rel, len(values), "; есть непарные" if errors else ""))
    print("Промпт агенту: Прочитай и выполни бриф %s целиком. Пиши только в пути, перечисленные в разделе «Выдача». "
          "Последнее сообщение — отчёт по формату брифа." % rel)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
