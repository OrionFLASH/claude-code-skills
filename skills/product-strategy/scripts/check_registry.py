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
Ссылки на черновики (G3-07 и т. п.) в тексте, dependencies и tags (кроме merged:…, merged_from, source_group) — ошибка:
их переводит merge_proposals.py по build/id-map.json. Подшкала ценности null или в списке scores_na — «неприменима»
(score.py исключает её из индекса ценности); обязательные value/cost/risk/confidence неприменимыми быть не могут.

Профиль zero-budget-solo: минимум категории monetization применяется, если strategy.paid_tier = yes или
project.goal = commercial; localization — если рынков (strategy.markets) больше одного; partnerships и new_lines —
только если категория перечислена в strategy.categories_required (туда же можно вписать любую из четырёх).

--demo — режим демо-прогона: заглушки URL разрешены, минимумы по категориям и доля A+B — предупреждения
(демо-данные генерируются случайно).

Дополнения 1.5 (все поля run-config необязательны; без них — поведение 1.4):
  - личный режим (project.audience = personal | circle | personal_then_public): свои категории реестра
    (PERSONAL_CATEGORIES: core, data-sources, reliability, privacy-security, ux, ai-quality, maintenance,
    personal-analytics) и минимумы «по приоритету»; категории аудитории (acquisition, conversion, retention,
    monetization, partnerships, localization) — предупреждение (personal_then_public — только в horizon now);
    порог A+B — 40 %, предупреждение о «внешних» A+B не выводится;
  - registry.category_minimums = count | priority (по умолчанию count; priority — в личном режиме и при
    registry.capacity_cap): в режиме priority категория обязана быть представлена (≥ 1), а не набрать долю;
  - evidence.kind = owner_prior_work (прежние работы и репозитории владельца — внутреннее доказательство): класс
    предложения, у которого все доказательства такого вида, — не выше C (A/B — ошибка); такие предложения не входят
    в знаменатель доли A+B;
  - ёмкость (scripts/capacity.py, одна величина project.capacity.day_hours): сумма середин effort_days горизонта
    now против dev_days за registry.now_months (иначе idea.facets.mvp_weeks, иначе 3 мес.) × 1,3 — предупреждение;
  - решения владельца data/decisions.json → horizons[] {proposals, horizon, tag?} (и forks[].apply при заданном
    decision): горизонт/тег реестра расходится с решением — ошибка (исправляет merge_proposals.py --sync-decisions);
  - режим идеи: horizon и тег mvp|v1|later расходятся (mvp → now, v1 → next, later → later|vision) — предупреждение;
  - нарезка на очереди (slicing.enabled, slicing.queues[].id): proposals[].queue — существующая очередь; предложения
    horizon now без очереди — предупреждение; сводка by_queue (число и сумма середин effort_days);
  - ошибка цитаты ≥ 15 слов подсказывает правку в build/overrides.json; --suggest-overrides пишет заготовку
    build/overrides.suggested.json (цитаты сокращены до 10 слов);
  - --quotas [--json] — квоты категорий для брифов генераторов ({QUOTAS}) с учётом режима.
check_proposal(..., draft=True) — черновик (G7/G8 до слияния): нет merged_from/source_group — не предупреждение.

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

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from capacity import capacity as _capacity  # noqa: E402
except ImportError:                                  # pragma: no cover — capacity.py входит в скилл с 1.5
    _capacity = None

CATEGORIES = ["product", "acquisition", "conversion", "retention", "monetization", "analytics", "partnerships",
              "localization", "new_lines", "platform"]
# минимум по категориям, % от минимального числа предложений (universal-strategy-prompt §7)
CATEGORY_MIN_PCT = {"product": 30, "acquisition": 20, "conversion": 8, "retention": 8, "monetization": 8,
                    "analytics": 6, "partnerships": 6, "localization": 5, "new_lines": 3}
# личный режим (project.audience = personal | circle | personal_then_public): свои категории и доли
PERSONAL_CATEGORIES = ["core", "data-sources", "reliability", "privacy-security", "ux", "ai-quality", "maintenance",
                       "personal-analytics"]
PERSONAL_MIN_PCT = {"core": 30, "data-sources": 10, "reliability": 10, "privacy-security": 8, "ux": 10, "ai-quality": 6,
                    "maintenance": 8, "personal-analytics": 5}
PUBLIC_ONLY = ["acquisition", "conversion", "retention", "monetization", "partnerships", "localization"]
ALL_CATEGORIES = CATEGORIES + PERSONAL_CATEGORIES
PERSONAL_AUDIENCES = ("personal", "circle", "personal_then_public")
CATEGORY_LABELS_RU = {
    "product": "Продукт", "acquisition": "Привлечение", "conversion": "Конверсия", "retention": "Удержание",
    "monetization": "Монетизация", "analytics": "Аналитика", "partnerships": "Партнёрства", "localization": "Локализация",
    "new_lines": "Новые направления", "platform": "Платформа", "core": "Ядро", "data-sources": "Источники данных",
    "reliability": "Надёжность", "privacy-security": "Приватность и безопасность", "ux": "Удобство (UX)",
    "ai-quality": "Качество ИИ", "maintenance": "Поддержка и обновления", "personal-analytics": "Личная аналитика"}
EVIDENCE_KINDS = ["competitor", "community", "issue", "docs", "repo", "research", "analytics", "own_app", "owner_prior_work"]
OWNER_KIND = "owner_prior_work"
AB_MIN_SHARE_PERSONAL = 0.40
NOW_CAP_FACTOR = 1.3
TAG_HORIZON = {"mvp": ("now",), "v1": ("next",), "later": ("later", "vision")}
OVERRIDES_HINT = ("исправьте в build/overrides.json (пример: {\"%s\": {\"%s\": \"…\"}}) или в черновике, затем "
                  "merge_proposals.py — правка переживёт следующее слияние; заготовка — check_registry.py <OUT> --suggest-overrides")
HORIZONS = ["now", "next", "later", "vision"]
KANO = ["must", "linear", "delight", "indifferent"]
SCORE_REQUIRED = ["value", "cost", "risk", "confidence"]
VALUE_SUBSCALES = ["reach", "impact", "acquisition", "activation", "conversion", "retention", "revenue", "virality",
                   "seo", "trust", "moat", "fit", "demand", "season"]
DRAFT_REF = re.compile(r"\bG\d+-\d+\b")
REF_SKIP = {"id", "merged_from", "source_group"}
URL_KEYS = {"url", "doc_url", "file"}           # адреса и пути не считаются текстом со ссылками на черновики
SCORE_OPTIONAL = ["reach", "impact", "acquisition", "activation", "conversion", "retention", "revenue", "virality",
                  "seo", "trust", "moat", "fit", "demand", "season", "testability", "spread"]
RISK_KEYS = ["legal", "ip", "platform", "privacy", "tech", "reputation"]
AB_MIN_SHARE = 0.60
AB_EXTERNAL_MIN_SHARE = 0.40   # минимум «внешних» A+B — для рыночных предложений
# профиль → категории, минимум которых применяется только «по запросу»
PROFILE_OPTIONAL = {"zero-budget-solo": ["monetization", "partnerships", "localization", "new_lines"]}
INTERNAL_KINDS = {"repo", "own_app", "analytics", "owner_prior_work"}
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


def find_draft_refs(p):
    """Оставшиеся ссылки на черновики: [(поле, ссылка)] (id, merged_from, source_group и теги merged:… не смотрятся)."""
    out = []

    def walk(v, path):
        if isinstance(v, str):
            out.extend((path, m.group(0)) for m in DRAFT_REF.finditer(v))
        elif isinstance(v, list):
            for k, x in enumerate(v):
                walk(x, "%s[%d]" % (path, k))
        elif isinstance(v, dict):
            for k, x in v.items():
                if k not in URL_KEYS:
                    walk(x, "%s.%s" % (path, k))

    for k, v in p.items():
        if k in REF_SKIP:
            continue
        if k == "tags" and isinstance(v, list):
            v = [t for t in v if not (isinstance(t, str) and t.startswith("merged:"))]
        walk(v, k)
    return out


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


def audience(cfg):
    """project.audience: personal | circle | personal_then_public | public (по умолчанию public — поведение 1.4)."""
    a = str(((cfg or {}).get("project") or {}).get("audience") or "public").strip().lower()
    return a if a in PERSONAL_AUDIENCES + ("public",) else "public"


def is_personal(cfg):
    return audience(cfg) in PERSONAL_AUDIENCES


def active_categories(cfg):
    """Категории реестра для прогона: личный режим — PERSONAL_CATEGORIES (+ категории аудитории для
    personal_then_public — раздел «Если захочется выпустить наружу»), иначе CATEGORIES."""
    if not is_personal(cfg):
        return list(CATEGORIES)
    return PERSONAL_CATEGORIES + (PUBLIC_ONLY if audience(cfg) == "personal_then_public" else [])


def category_mode(cfg):
    """count — минимум долей по числу (1.4); priority — категория должна быть представлена (≥ 1), а место в now
    ей обеспечивает merge_proposals.py --cap-now (категории — приоритет, а не число)."""
    reg = (cfg or {}).get("registry") or {}
    m = str(reg.get("category_minimums") or "").strip().lower()
    if m in ("count", "priority"):
        return m
    return "priority" if (is_personal(cfg) or reg.get("capacity_cap")) else "count"


def ai_in_product(cfg):
    """Есть ли ИИ в продукте по ответам опроса (idea.facets.ai_role|ai)."""
    fc = ((cfg or {}).get("idea") or {}).get("facets") or {}
    v = fc.get("ai_role", fc.get("ai"))
    if isinstance(v, bool):
        return v
    s = str(v or "").strip().lower()
    return bool(s) and not re.search(r"^(no|none|нет|без ии|без ai|without)", s)


def category_requirements(cfg, min_n):
    """Минимумы категорий для реестра из min_n предложений с учётом run-config.

    Возвращает {категория: {"pct", "required", "na", "optional", "note", "nominal", "mode"}}: required — сколько
    нужно (0, если категория неприменима или минимум «по запросу» в профиле; 1 в режиме priority), na —
    strategy.categories_na, optional — минимум снят профилем. Личный режим — свои категории (PERSONAL_MIN_PCT;
    ai-quality — только при ИИ в продукте). Используют check_registry, merge_proposals (не ронять минимум при
    слиянии) и gap_audit."""
    cfg = cfg or {}
    strat = cfg.get("strategy") or {}
    project = cfg.get("project") or {}
    na = set(strat.get("categories_na") or []) | set((cfg.get("scope") or {}).get("categories_na") or [])
    profile = strat.get("profile") or "standard"
    requested = set(strat.get("categories_required") or [])
    markets = [m for m in (strat.get("markets") or []) if m and m != "auto"]
    mode = category_mode(cfg)
    personal = is_personal(cfg)
    table = PERSONAL_MIN_PCT if personal else CATEGORY_MIN_PCT
    out = {}
    for c, pct in table.items():
        need = int(math.ceil(pct * min_n / 100.0 - 1e-9))
        optional, note = False, ""
        if c in na:
            note = "неприменима (strategy.categories_na)"
        elif personal and c == "ai-quality" and not ai_in_product(cfg) and c not in requested:
            optional = True
            note = "личный режим: ИИ в продукте не заявлен — минимум по запросу"
        elif not personal and c in PROFILE_OPTIONAL.get(profile, []):
            implied = ((c == "monetization" and (strat.get("paid_tier") == "yes" or project.get("goal") == "commercial"))
                       or (c == "localization" and len(markets) > 1))
            if c in requested or implied:
                note = "профиль %s: минимум применяется (%s)" % (
                    profile, "strategy.categories_required" if c in requested else
                    ("платный тариф/коммерческая цель" if c == "monetization" else "рынков больше одного"))
            else:
                optional = True
                note = "профиль %s: минимум по запросу (strategy.categories_required)" % profile
        req = 0 if (c in na or optional) else need
        if mode == "priority" and req:
            req = 1
            note = (note + "; " if note else "") + "минимум по приоритету: категория представлена (≥ 1), место в now — --cap-now"
        out[c] = {"pct": pct, "required": req, "na": c in na, "optional": optional, "nominal": need, "note": note,
                  "mode": mode}
    return out


def quotas(cfg, min_n):
    """Квоты генераторов {категория: число} — номинальные доли (в режиме priority тоже: это план генерации, а не
    порог проверки); неприменимые и «по запросу» — 0."""
    return {c: (0 if (r["na"] or r["optional"]) else r["nominal"]) for c, r in category_requirements(cfg, min_n).items()}


def effort_mid(p):
    ed = p.get("effort_days")
    if isinstance(ed, list) and len(ed) == 2 and all(is_num(x) for x in ed):
        return (ed[0] + ed[1]) / 2.0
    return 0.0


def now_months(cfg):
    """Длина горизонта now в месяцах: registry.now_months → idea.facets.mvp_weeks (режим идеи) → 3 (контракт)."""
    cfg = cfg or {}
    reg = cfg.get("registry") or {}
    try:
        v = float(reg.get("now_months"))
        if v > 0:
            return v, "registry.now_months"
    except (TypeError, ValueError):
        pass
    fc = (cfg.get("idea") or {}).get("facets") or {}
    try:
        w = float(fc.get("mvp_weeks"))
        if w > 0:
            return round(w * 12 / 52.0, 2), "idea.facets.mvp_weeks"
    except (TypeError, ValueError):
        pass
    return 3.0, "контракт: now — 0–3 мес."


def capacity_relevant(cfg):
    """Сверять now с ёмкостью, только если ёмкость задана или это прогон одного человека (старые прогоны не шумят)."""
    cfg = cfg or {}
    return bool(((cfg.get("project") or {}).get("capacity")) or (cfg.get("registry") or {}).get("capacity_cap")
                or ((cfg.get("strategy") or {}).get("profile") == "zero-budget-solo")
                or ((cfg.get("idea") or {}).get("facets") or {}).get("hours_week") or is_personal(cfg))


def now_capacity(cfg, props=None, factor=NOW_CAP_FACTOR):
    """Ёмкость горизонта now: {months, months_source, dev_days, ceiling, factor, day_hours, line, now_days, now_count, ok}."""
    months, src = now_months(cfg)
    if _capacity is None:
        return None
    cap = _capacity(cfg or {}, months)
    out = {"months": months, "months_source": src, "dev_days": cap["dev_days"], "factor": factor,
           "ceiling": round(cap["dev_days"] * factor, 1), "day_hours": cap["day_hours"], "line": cap["line"]}
    if props is not None:
        now = [p for p in props if isinstance(p, dict) and p.get("horizon") == "now"]
        out["now_days"] = round(sum(effort_mid(p) for p in now), 1)
        out["now_count"] = len(now)
        out["ok"] = out["now_days"] <= out["ceiling"] + 1e-9
    return out


def owner_only(p):
    """Все доказательства предложения — прежние работы владельца (owner_prior_work)."""
    ev = [e for e in (p.get("evidence") or []) if isinstance(e, dict)]
    return bool(ev) and all(e.get("kind") == OWNER_KIND for e in ev)


def decision_horizons(out_dir):
    """Решения владельца о горизонтах из data/decisions.json: horizons[] {proposals, horizon, tag?, why?} и
    forks[].apply {proposals, horizon, tag?} при заданном decision. → [{id, horizon, tag, why, source}]."""
    p = Path(out_dir) / "data" / "decisions.json"
    try:
        d = json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
    except (OSError, json.JSONDecodeError):
        d = None
    if not isinstance(d, dict):
        return []
    rows = []

    def take(e, source):
        if not isinstance(e, dict):
            return
        hz, tag = e.get("horizon"), e.get("tag")
        if hz is not None and hz not in HORIZONS:
            return
        if not hz and not tag:
            return
        pids = e.get("proposals") or ([e["id"]] if isinstance(e.get("id"), str) and re.fullmatch(r"P\d{3,}", e["id"]) else [])
        for pid in pids if isinstance(pids, list) else [pids]:
            if isinstance(pid, str):
                rows.append({"id": pid, "horizon": hz, "tag": tag, "why": e.get("why") or e.get("note") or "", "source": source})

    for e in d.get("horizons") or []:
        take(e, "decisions.horizons")
    for f in d.get("forks") or []:
        if isinstance(f, dict) and f.get("decision") not in (None, "") and isinstance(f.get("apply"), (dict, list)):
            for e in (f["apply"] if isinstance(f["apply"], list) else [f["apply"]]):
                take(e, "decisions.forks.%s" % f.get("id", "?"))
    return rows


def slicing_queues(cfg):
    s = (cfg or {}).get("slicing") or {}
    if not s.get("enabled"):
        return []
    return [q for q in (s.get("queues") or []) if isinstance(q, dict) and q.get("id")]


def shorten_quotes(text, keep=10):
    """Сокращает цитаты в кавычках из ≥ 15 слов до keep слов с «…» (для заготовки overrides)."""
    def rep(m):
        ws = m.group(1).split()
        if len(ws) < QUOTE_MAX_WORDS:
            return m.group(0)
        return m.group(0)[0] + " ".join(ws[:keep]) + " …" + m.group(0)[-1]
    return QUOTE_RE.sub(rep, text) if isinstance(text, str) else text


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


def check_proposal(p, idx, demo, errors, warnings, quote_by_url, allow_draft_refs=False, draft=False, quote_fix=None):
    """allow_draft_refs — черновик (G7 до слияния): ссылки G\\d+-\\d+ допустимы. draft — черновик G7/G8 до слияния:
    поля слияния (merged_from, source_group) заполняет merge_proposals.py — их отсутствие не предупреждение, а
    заполненный merged_from — предупреждение. quote_fix — словарь {id: {поле: исправленное значение}} для заготовки
    build/overrides.suggested.json."""
    pid = p.get("id") if isinstance(p.get("id"), str) and p.get("id") else "#%d" % (idx + 1)
    soft = warnings if demo else errors
    for f, (types, required) in FIELDS.items():
        if f not in p:
            if draft and f in ("merged_from", "source_group"):
                continue
            (errors if required else warnings).append("%s: нет поля %s" % (pid, f))
            continue
        v = p[f]
        if not type_ok(v, types):
            (errors if required else warnings).append("%s: %s — неверный тип %s" % (pid, f, type(v).__name__))
            continue
        if required and isinstance(v, str) and not v.strip():
            errors.append("%s: %s пустое" % (pid, f))
    if draft and p.get("merged_from"):
        warnings.append("%s: у черновика заполнен merged_from — его заполняет merge_proposals.py при слиянии (уберите)" % pid)
    if isinstance(p.get("title"), str) and len(p["title"]) > TITLE_MAX:
        warnings.append("%s: название длиннее %d знаков (%d)" % (pid, TITLE_MAX, len(p["title"])))
    if "category" in p and p.get("category") not in ALL_CATEGORIES:
        errors.append("%s: неизвестная категория %r" % (pid, p.get("category")))
    if p.get("evidence_class") in ("A", "B") and owner_only(p):
        soft.append("%s: класс %s при доказательствах только owner_prior_work (прежние работы владельца) — класс не выше C"
                    % (pid, p.get("evidence_class")))
    if "queue" in p and p["queue"] is not None and not isinstance(p["queue"], str):
        errors.append("%s: queue — строка (id очереди из slicing.queues) или null" % pid)
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
            errors.append("%s: evidence[%d].note — цитата %d слов (нужно < %d); %s" % (
                pid, k, words, QUOTE_MAX_WORDS, OVERRIDES_HINT % (pid, "evidence")))
            if quote_fix is not None:
                fixed = [dict(x, note=shorten_quotes(x.get("note"))) if isinstance(x, dict) else x for x in ev]
                quote_fix.setdefault(pid, {})["evidence"] = fixed
        if isinstance(e.get("note"), str) and QUOTE_RE.search(e["note"]) and e.get("url"):
            quote_by_url.setdefault(e["url"], set()).add(pid)
    for fld in ("description", "rationale", "cheap_test", "current_feature"):
        for words in long_quotes(p.get(fld), True):
            errors.append("%s: %s — цитата %d слов (нужно < %d); %s" % (pid, fld, words, QUOTE_MAX_WORDS, OVERRIDES_HINT % (pid, fld)))
            if quote_fix is not None:
                quote_fix.setdefault(pid, {})[fld] = shorten_quotes(p.get(fld))

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
            if k in sc and sc[k] is None and k in VALUE_SUBSCALES:
                continue                                  # null — подшкала неприменима
            if k in sc and not (is_num(sc[k]) and 1 <= sc[k] <= 5):
                errors.append("%s: scores.%s=%r вне 1–5" % (pid, k, sc[k]))
    na = p.get("scores_na")
    if na is not None and not isinstance(na, list):
        errors.append("%s: scores_na — нужен список подшкал" % pid)
    if isinstance(na, list):
        for k in na:
            if k in SCORE_REQUIRED:
                errors.append("%s: scores_na — %r обязательна и не может быть неприменимой" % (pid, k))
            elif k not in VALUE_SUBSCALES:
                errors.append("%s: scores_na — %r не подшкала ценности (%s)" % (pid, k, ", ".join(VALUE_SUBSCALES)))
            elif isinstance(sc, dict) and is_num(sc.get(k)):
                warnings.append("%s: scores.%s задана, но в scores_na — считается неприменимой" % (pid, k))
    refs = [] if allow_draft_refs else find_draft_refs(p)
    if refs:
        errors.append("%s: ссылки на черновики %s — переведите в P-id (merge_proposals.py, build/id-map.json)" % (
            pid, ", ".join("%s в %s" % (r, f) for f, r in refs[:5]) + (" и ещё %d" % (len(refs) - 5) if len(refs) > 5 else "")))
    for k, kp in enumerate(p.get("effect_kpi") or []):
        if not isinstance(kp, dict) or not kp.get("kpi"):
            warnings.append("%s: effect_kpi[%d] без kpi" % (pid, k))
    if isinstance(p.get("mockup"), str) and not p["mockup"].strip():
        warnings.append("%s: mockup — пустая строка (нужно null)" % pid)


def run_check(out_dir, min_override=None, demo=False, quote_fix=None):
    """Возвращает отчёт (dict) по реестру. quote_fix — словарь для заготовки overrides (заполняется на месте)."""
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
        check_proposal(p, i, demo, errors, warnings, quote_by_url, quote_fix=quote_fix)

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
        # тег релиза и горизонт (бриф генератора: mvp → now, v1 → next, later → later|vision)
        mism = []
        for p in good:
            tags = [t for t in (p.get("tags") or []) if t in TAG_HORIZON]
            if len(tags) == 1 and p.get("horizon") in HORIZONS and p.get("horizon") not in TAG_HORIZON[tags[0]]:
                mism.append("%s (%s/%s)" % (p.get("id"), tags[0], p.get("horizon")))
        if mism:
            warnings.append("режим идеи: тег релиза расходится с horizon (mvp → now, v1 → next, later → later|vision): %s"
                            % ", ".join(mism[:12]) + (" и ещё %d" % (len(mism) - 12) if len(mism) > 12 else ""))

    by_id = {p.get("id"): p for p in good if isinstance(p.get("id"), str)}
    # решения владельца о горизонтах (data/decisions.json) — источник правды для horizon/тега
    decision_conflicts = []
    for d in decision_horizons(out_dir):
        p = by_id.get(d["id"])
        if p is None:
            warnings.append("decisions.json (%s): %s нет в реестре" % (d["source"], d["id"]))
            continue
        bad = []
        if d["horizon"] and p.get("horizon") != d["horizon"]:
            bad.append("horizon %s, решение — %s" % (p.get("horizon"), d["horizon"]))
        if d["tag"] and d["tag"] not in (p.get("tags") or []):
            bad.append("нет тега %s" % d["tag"])
        if bad:
            decision_conflicts.append(dict(d, registry_horizon=p.get("horizon")))
            errors.append("%s: реестр расходится с решением владельца (%s): %s — merge_proposals.py <OUT> --sync-decisions"
                          % (d["id"], d["source"], "; ".join(bad)))

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
                         "note": r["note"], "ok": skip or actual >= need, "nominal": r["nominal"], "mode": r["mode"]}
        if not skip and actual < need:
            soft.append("категория %s: %d < %d (%s)" % (c, actual, need, "%d %% от %d" % (r["pct"], min_n)
                                                        if r["mode"] == "count" else "минимум по приоритету — категория не представлена"))
    personal = is_personal(cfg)
    aud = audience(cfg)
    if personal:
        extra = sorted(c for c in cnt if c in PUBLIC_ONLY)
        if aud == "personal_then_public":
            now_pub = sorted(p.get("id") for p in good if p.get("category") in PUBLIC_ONLY and p.get("horizon") == "now"
                             and isinstance(p.get("id"), str))
            if now_pub:
                warnings.append("личный режим (сначала для себя): категории аудитории в horizon now у %s — выпуск наружу "
                                "позже (раздел «Если захочется выпустить наружу»)" % ", ".join(now_pub[:12]))
        elif extra:
            warnings.append("личный режим (%s): категории аудитории %s не нужны — замените на %s"
                            % (aud, ", ".join("%s %d" % (c, cnt[c]) for c in extra), ", ".join(PERSONAL_CATEGORIES)))
    elif any(c in PERSONAL_CATEGORIES for c in cnt):
        warnings.append("категории личного режима (%s) в реестре публичного продукта — project.audience не задан как личный"
                        % ", ".join(sorted(c for c in cnt if c in PERSONAL_CATEGORIES)))
    cls = Counter(p.get("evidence_class") for p in good)
    ab = (cls.get("A", 0) + cls.get("B", 0)) / total if total else 0.0
    # предложения только на прежних работах владельца — класс ≤ C и вне знаменателя доли A+B
    owner = [p for p in good if owner_only(p)]
    base = [p for p in good if not owner_only(p)]
    ab_base = (sum(1 for p in base if p.get("evidence_class") in ("A", "B")) / len(base)) if base else 1.0
    try:
        ab_min = float(((cfg.get("registry") or {}).get("ab_min_share")))
    except (TypeError, ValueError):
        ab_min = AB_MIN_SHARE_PERSONAL if personal else AB_MIN_SHARE
    if total and base and ab_base < ab_min:
        soft.append("доля классов A+B %.0f %% < %.0f %%%s" % (
            ab_base * 100, ab_min * 100, " (без %d предложений только на owner_prior_work)" % len(owner) if owner else ""))
    split = evidence_split(good, cfg)
    if total and split["ab_external"] < AB_EXTERNAL_MIN_SHARE and not personal:
        warnings.append("внешних A+B (конкуренты, сообщества, внешние источники) %.0f %% < %.0f %% — рыночные предложения "
                        "опираются в основном на код продукта; внутренних A+B %.0f %%"
                        % (split["ab_external"] * 100, AB_EXTERNAL_MIN_SHARE * 100, split["ab_internal"] * 100))
    hz = Counter(p.get("horizon") for p in good)
    # ёмкость горизонта now (одна величина project.capacity.day_hours — scripts/capacity.py)
    cap = now_capacity(cfg, good) if capacity_relevant(cfg) else None
    if cap and not cap["ok"]:
        warnings.append("сумма середин effort_days в horizon now %.1f дн. > ёмкость %.1f дн. × %.1f = %.1f дн. (%g мес., %s; %s) — "
                        "merge_proposals.py <OUT> --cap-now или registry.capacity_cap"
                        % (cap["now_days"], cap["dev_days"], cap["factor"], cap["ceiling"], cap["months"], cap["months_source"], cap["line"]))
    # очереди нарезки (slicing)
    queues = slicing_queues(cfg)
    qids = [q["id"] for q in queues]
    by_queue = {}
    for p in good:
        q = p.get("queue")
        if q:
            row = by_queue.setdefault(q, {"count": 0, "effort_days": 0.0, "ids": []})
            row["count"] += 1
            row["effort_days"] = round(row["effort_days"] + effort_mid(p), 1)
            row["ids"].append(p.get("id"))
            if queues and q not in qids:
                errors.append("%s: очередь %r нет в slicing.queues (%s)" % (p.get("id"), q, ", ".join(qids)))
            elif not queues:
                warnings.append("%s: queue %r, но slicing.enabled не включён" % (p.get("id"), q))
    if queues:
        noq = sorted(p.get("id") for p in good if p.get("horizon") == "now" and not p.get("queue") and isinstance(p.get("id"), str))
        if noq:
            warnings.append("нарезка на очереди включена, но у предложений now нет queue: %s — merge_proposals.py <OUT> --cap-now"
                            % ", ".join(noq[:15]) + (" и ещё %d" % (len(noq) - 15) if len(noq) > 15 else ""))
    # согласованность merged_from (заполняет merge_proposals.py)
    for p in good:
        mf = p.get("merged_from")
        if isinstance(mf, list) and len(mf) != len(set(map(str, mf))):
            warnings.append("%s: повторы в merged_from %s" % (p.get("id"), mf))
    return {"ok": not errors, "date": date.today().isoformat(), "demo": demo, "total": total, "min": min_n,
            "profile": strat.get("profile") or "standard", "audience": aud, "categories_active": active_categories(cfg),
            "category_mode": category_mode(cfg),
            "categories_na": sorted(na), "by_category": dict(cnt), "category_minimums": cat_report,
            "evidence_classes": {k: cls.get(k, 0) for k in "ABCD"}, "ab_share": round(ab, 4),
            "ab_share_checked": round(ab_base, 4), "ab_min_share": ab_min, "owner_only": [p.get("id") for p in owner],
            "ab_external_share": split["ab_external"], "ab_internal_share": split["ab_internal"],
            "evidence_sides": split["evidence_sides"], "now_capacity": cap, "by_queue": by_queue,
            "decision_conflicts": decision_conflicts,
            "by_horizon": {k: hz.get(k, 0) for k in HORIZONS}, "errors": errors, "warnings": warnings}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Проверка реестра предложений (data/proposals.json).")
    ap.add_argument("out", help="папка прогона <OUT>")
    ap.add_argument("--min", type=int, default=None, help="минимум предложений (иначе из run-config или 100)")
    ap.add_argument("--demo", action="store_true", help="демо-режим: заглушки URL разрешены, минимумы — предупреждения")
    ap.add_argument("--quiet", action="store_true", help="не печатать предупреждения")
    ap.add_argument("--suggest-overrides", action="store_true",
                    help="записать build/overrides.suggested.json — заготовку правок для ошибок цитат (перенесите в overrides.json)")
    ap.add_argument("--quotas", action="store_true", help="только напечатать квоты категорий для брифов генераторов ({QUOTAS})")
    ap.add_argument("--json", action="store_true", help="с --quotas: JSON {категория: число}")
    a = ap.parse_args(argv)
    out_dir = Path(a.out).resolve()
    if a.quotas:
        cfg_path = out_dir / "build" / "run-config.json"
        cfg = json.loads(cfg_path.read_text(encoding="utf-8")) if cfg_path.exists() else {}
        min_n = a.min if a.min is not None else (cfg.get("strategy") or {}).get("proposals_min") or 100
        q = {c: n for c, n in quotas(cfg, min_n).items() if n}
        print(json.dumps(q, ensure_ascii=False) if a.json else ", ".join("%s:%d" % kv for kv in q.items()))
        return 0
    fixes = {} if a.suggest_overrides else None
    rep = run_check(out_dir, a.min, a.demo, quote_fix=fixes)
    (out_dir / "data").mkdir(parents=True, exist_ok=True)
    (out_dir / "data" / "registry-check.json").write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
    if fixes is not None:
        (out_dir / "build").mkdir(parents=True, exist_ok=True)
        doc = {"_comment": "Заготовка check_registry.py --suggest-overrides: цитаты сокращены до 10 слов. Проверьте текст и "
                           "перенесите нужные записи в build/overrides.json, затем merge_proposals.py <OUT> (или "
                           "--apply-overrides build/overrides.json)."}
        doc.update(fixes)
        (out_dir / "build" / "overrides.suggested.json").write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
        print("Заготовка правок: build/overrides.suggested.json (записей %d)" % len(fixes))
    print("Предложений: %d (минимум %d)%s; A+B: %.0f %% (внешние %.0f %%, внутренние %.0f %%)"
          % (rep["total"], rep["min"], " [демо]" if a.demo else "", rep["ab_share"] * 100, rep["ab_external_share"] * 100,
             rep["ab_internal_share"] * 100))
    print("По категориям: " + ", ".join("%s %d/%d%s" % (c, v["actual"], v["required"],
                                                       " н/п" if v["na"] else (" по запросу" if v.get("optional") else ""))
                                        for c, v in rep["category_minimums"].items()))
    print("Классы: " + ", ".join("%s %d" % kv for kv in rep["evidence_classes"].items())
          + "; горизонты: " + ", ".join("%s %d" % kv for kv in rep["by_horizon"].items()))
    if rep.get("now_capacity"):
        c = rep["now_capacity"]
        print("Ёмкость now: %.1f из %.1f дн. (потолок ×%.1f от %.1f дн. за %g мес.)%s"
              % (c["now_days"], c["ceiling"], c["factor"], c["dev_days"], c["months"], "" if c["ok"] else " — ПРЕВЫШЕНИЕ"))
    if rep.get("by_queue"):
        print("Очереди: " + ", ".join("%s %d (%.1f дн.)" % (q, v["count"], v["effort_days"]) for q, v in rep["by_queue"].items()))
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
