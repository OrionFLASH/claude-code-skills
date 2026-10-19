#!/usr/bin/env python3
"""Значения плейсхолдеров новых брифов 1.5.0 (WP-G) для render_brief.py: признаки идеи, личный режим, модули ИИ и
администрирования, интеграция с внешней платформой, рабочий прототип, архитектура для спецификаций.

Подключение (render_brief.py, после словаря RESOLVERS):
    import brief_facets
    brief_facets.install(RESOLVERS)          # добавляет только отсутствующие ключи — свои резолверы render_brief важнее

Каждая функция получает контекст render_brief.Ctx (поля cfg, idea, out, name, concept; метод c(*keys)) и возвращает
строку или None (None → render_brief считает плейсхолдер незаполненным и просит --set). Источники:
  - build/run-config.json: idea.facets.* (platform_dependency, platform_name, platform_urls, platform_data_needs,
    platform_access, ai_role, ai_where, ai_hardware, admin_needed, admin_settings, data_sources_needed,
    prototype_needed, prototype_scope, stack, owner_repos), project.audience, project.release_outward,
    sources.owner_docs[], design.modes[]/chosen, idea.request_questions[];
  - data/idea.json (facets — запасной источник), data/competitors.json, data/plan-baseline.json → architecture,
    data/integration-options.json, data/flows-plan.json, data/demo-canon.json, build/parts/strategy-*.md (раздел 11).
Без значения в данных — безопасный текст «не указано — …» (бриф рендерится без --set). Только стандартная библиотека.
"""
import json
import os
import re
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent


def skill_dir():
    """Папка скилла через «~» (как {SKILL_DIR} в render_brief): значения резолверов повторно не раскрываются."""
    s, home = str(SKILL), str(Path.home())
    return "~" + s[len(home):] if s == home or s.startswith(home + os.sep) else s


AUDIENCE_LABELS = {
    "personal": "только для себя (личный режим): аудитории, маркетинга и денег нет",
    "circle": "для себя и узкого круга (семья, команда, друзья): личный режим, без маркетинга",
    "personal_then_public": "сначала для себя, возможно позже публично: личный режим + раздел «Если захочется выпустить наружу»",
    "public": "публичный продукт с аудиторией и, возможно, деньгами",
}
PERSONAL = ("personal", "circle", "personal_then_public")
DATA_NEEDS_DEFAULT = ("данные о мире (справочники, каталоги, события, цены); данные о пользователе (профиль, прогресс, "
                      "история); авторизация (вход через платформу, ключи); действия от имени пользователя")


def _jload(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _get(d, *keys):
    for k in keys:
        if not isinstance(d, dict):
            return None
        d = d.get(k)
    return d


def facets(ctx):
    """idea.facets из run-config, дополненные facets из data/idea.json (run-config важнее)."""
    a = _get(ctx.cfg, "idea", "facets") or {}
    b = (ctx.idea or {}).get("facets") or {}
    out = dict(b) if isinstance(b, dict) else {}
    if isinstance(a, dict):
        out.update({k: v for k, v in a.items() if v not in (None, "", [])})
    return out


def _listify(v):
    if v in (None, "", [], {}):
        return []
    if isinstance(v, (list, tuple)):
        return [str(x).strip() for x in v if str(x).strip()]
    if isinstance(v, dict):
        return ["%s: %s" % (k, x) for k, x in v.items() if x not in (None, "", [])]
    return [s.strip() for s in re.split(r"[;\n]", str(v)) if s.strip()]


def audience(ctx):
    v = _get(ctx.cfg, "project", "audience") or facets(ctx).get("audience") or "public"
    return v if v in AUDIENCE_LABELS else "public"


def is_personal(ctx):
    return audience(ctx) in PERSONAL


# ---------------------------------------------------------------- аудитория
def r_audience(ctx):
    a = audience(ctx)
    out = "`%s` — %s" % (a, AUDIENCE_LABELS[a])
    if _get(ctx.cfg, "project", "release_outward") and a != "public":
        out += "; владелец допускает выпуск наружу (`project.release_outward: true`)"
    return out


def r_audience_rules(ctx):
    a = audience(ctx)
    if a == "public":
        return "публичный продукт: поправки личного режима не применяются, правила брифа действуют как написаны"
    rules = ["личный режим (`project.audience = %s`): аудитории и маркетинга нет — не искать каналы, сообщества для "
             "продвижения, цены и платящих; пользователь — владелец%s" % (a, " и его круг" if a == "circle" else ""),
             "ценность — экономия времени, денег и ошибок владельца; сравнение — «готовое вместо своего» (build vs buy)",
             "поправки разделов и метрик — `%s/references/concept-outline.md`, раздел «Личный режим»" % skill_dir()]
    if a == "personal_then_public" or _get(ctx.cfg, "project", "release_outward"):
        rules.append("отдельно отметить, что изменится при выпуске наружу (право, поддержка, хостинг, платежи) — "
                     "для раздела «Если захочется выпустить наружу»")
    return "\n" + "\n".join("- " + r + ";" for r in rules[:-1]) + "\n- " + rules[-1] + "."


# ---------------------------------------------------------------- внешняя платформа (FB-045, FB-056)
def r_platform(ctx):
    f = facets(ctx)
    name = f.get("platform_name") or f.get("platform")
    if name:
        return str(name)
    if f.get("platform_dependency"):
        return "(название не указано — определить по досье идеи) [допущение]"
    return "(не указана — определить по досье идеи: от какой платформы, API или сервиса зависит продукт) [допущение]"


def r_platform_urls(ctx):
    f = facets(ctx)
    urls = _listify(f.get("platform_urls"))
    docs = _get(ctx.cfg, "sources", "owner_docs") or []
    for d in docs if isinstance(docs, list) else []:
        u = d.get("url") if isinstance(d, dict) else d
        if u and str(u).startswith(("http://", "https://")) and u not in urls:
            role = d.get("role") if isinstance(d, dict) else None
            urls.append("%s%s" % (u, " (материал владельца, роль %s)" % role if role else " (материал владельца)"))
    site = _get(ctx.cfg, "sources", "external", "site")
    if site and site not in urls:
        urls.append(str(site))
    return "; ".join(urls) if urls else "нет — найти официальную документацию платформы, условия использования и страницы разработчиков поиском"


def r_data_needs(ctx):
    needs = _listify(facets(ctx).get("platform_data_needs"))
    return "; ".join(needs) if needs else DATA_NEEDS_DEFAULT + " — уточнить, что из этого нужно MVP [допущение]"


def r_platform_access(ctx):
    f = facets(ctx)
    v = f.get("platform_access")
    labels = {"official": "только официальный API", "official_api": "только официальный API", "community": "открытые данные сообщества",
              "manual": "ручной ввод", "research": "исследовать варианты", "mixed": "сочетание официального API и ручного ввода"}
    return labels.get(v, str(v)) if v else "не указано — исследовать все законные варианты; серые методы (обход защиты, чтение памяти, скрейпинг против правил) исключены"


def r_competitors_top(ctx):
    comp = _jload(ctx.out / "data" / "competitors.json", []) if ctx.out else []
    rows = []
    order = {"direct": 0, "indirect": 1, "analog": 2, "substitute": 3, "inspiration": 4, "anti": 5}
    items = [x for x in comp or [] if isinstance(x, dict) and not x.get("self") and x.get("name")]
    items.sort(key=lambda x: order.get(x.get("kind") or x.get("type"), 9))
    for x in items[:8]:
        rows.append("%s%s" % (x["name"], " (%s)" % x["url"] if x.get("url") else ""))
    if rows:
        return "; ".join(rows)
    lst = _get(ctx.cfg, "sources", "competitor_list") or []
    return ", ".join(map(str, lst)) if lst else "списка ещё нет — найти 3–6 продуктов, которые уже подключаются к платформе"


# ---------------------------------------------------------------- источники данных, референсы владельца
def r_data_sources(ctx):
    f = facets(ctx)
    items = _listify(f.get("data_sources_needed")) or _listify(f.get("data_sources"))
    if f.get("platform_name") and not items:
        items = ["данные платформы %s" % f["platform_name"]]
    return "; ".join(items) if items else "не перечислены владельцем — вывести из досье идеи (какие данные нужны каждой функции MVP) [допущение]"


def r_owner_refs(ctx):
    f = facets(ctx)
    items = _listify(f.get("owner_repos")) + _listify(f.get("owner_refs"))
    docs = _get(ctx.cfg, "sources", "owner_docs") or []
    for d in docs if isinstance(docs, list) else []:
        if isinstance(d, dict) and (d.get("role") in ("ref", "base", "follow") or d.get("kind") == "repo"):
            items.append("%s%s%s" % (d.get("url") or d.get("path") or "?", " — роль %s" % d["role"] if d.get("role") else "",
                                     " (статус: %s)" % d["status"] if d.get("status") else ""))
    items = list(dict.fromkeys(items))
    return "; ".join(items) if items else "нет — владелец не назвал референсов; бриф не запускать или спросить владельца"


def r_request_questions(ctx):
    rq = _get(ctx.cfg, "idea", "request_questions") or (ctx.idea or {}).get("request_questions") or []
    rows = []
    for i, q in enumerate(rq if isinstance(rq, list) else [], 1):
        if isinstance(q, dict):
            if q.get("kind", "research") != "research":
                continue
            rows.append("- %s — %s" % (q.get("id") or "RQ%02d" % i, q.get("text") or ""))
        elif str(q).strip():
            rows.append("- RQ%02d — %s" % (i, q))
    return "\n" + "\n".join(rows) if rows else "нет (в запросе владельца не было отдельных вопросов к исследованию)"


# ---------------------------------------------------------------- ИИ и администрирование (SM 5.1, 5.2)
AI_ROLES = {"none": "без ИИ", "helper": "помощник: подсказки и объяснения", "core": "ядро продукта", "explain": "объясняет готовые числа",
            "extract": "извлекает и классифицирует", "generate": "генерирует тексты или код", "agent": "действует как агент",
            "recommend": "рекомендует действия"}
AI_WHERE = {"local": "локально у пользователя (Ollama, LM Studio, llama.cpp)", "server": "свой сервер с GPU", "cloud": "облачный API",
            "hybrid": "гибрид: локально, откат в облако", "local_then_cloud": "локально, облако позже"}


def r_ai_role(ctx):
    f = facets(ctx)
    v = f.get("ai_role") or f.get("ai")
    if not v:
        return "не указана — вывести из досье идеи (объясняет, извлекает, генерирует, действует, рекомендует) [допущение]"
    vals = v if isinstance(v, list) else [v]
    return ", ".join(AI_ROLES.get(str(x), str(x)) for x in vals)


def r_ai_where(ctx):
    f = facets(ctx)
    v = f.get("ai_where")
    hw = f.get("ai_hardware")
    out = AI_WHERE.get(str(v), str(v)) if v else "не указано — сравнить локальный, серверный, облачный и гибридный варианты"
    if hw:
        out += "; железо пользователей: %s" % ("; ".join(_listify(hw)))
    return out


def r_admin_needs(ctx):
    f = facets(ctx)
    items = _listify(f.get("admin_settings")) + _listify(f.get("admin_needed") if not isinstance(f.get("admin_needed"), bool) else None)
    who = f.get("admin_who")
    if who:
        items.insert(0, "кто администрирует: %s" % who)
    if items:
        return "; ".join(items)
    if f.get("admin_needed") is False:
        return "владелец ответил, что админка не нужна — проверить минимум эксплуатации (бэкапы, обновления, ключи) и объяснить отказ"
    return "не указано — вывести из досье: что настраивать без правки кода, журнал, мониторинг, бэкапы, обновления, роли [допущение]"


# ---------------------------------------------------------------- спецификации: архитектура (FB-010)
def _section11(ctx):
    for f in sorted((ctx.out / "build" / "parts").glob("strategy-*.md")) + [ctx.out / "research" / "strategy.md"]:
        if not f.exists():
            continue
        m = re.search(r"(?ms)^##\s*11\.[^\n]*\n(.*?)(?=^##\s*\d+\.|\Z)", f.read_text(encoding="utf-8"))
        if m and m.group(1).strip():
            return f
    return None


def r_arch(ctx):
    pb = _jload(ctx.out / "data" / "plan-baseline.json", {}) or {}
    arch = pb.get("architecture") if isinstance(pb, dict) else None
    if arch:
        if isinstance(arch, dict):
            parts = ["%s: %s" % (k, v if not isinstance(v, (list, dict)) else json.dumps(v, ensure_ascii=False)) for k, v in arch.items()]
            text = "; ".join(parts)
        elif isinstance(arch, list):
            text = "; ".join(str(x if not isinstance(x, dict) else x.get("name") or x.get("id") or json.dumps(x, ensure_ascii=False)) for x in arch)
        else:
            text = str(arch)
        text = text if len(text) <= 600 else text[:597].rsplit(" ", 1)[0] + "…"
        return "%s (из `{OUT}/data/plan-baseline.json` → `architecture`)" % text
    opts = _jload(ctx.out / "data" / "integration-options.json", None)
    chosen = None
    if isinstance(opts, dict):
        lst = opts.get("options") or []
        chosen = next((o for o in lst if isinstance(o, dict) and (o.get("id") == opts.get("recommended") or o.get("recommended"))), None)
    sec = _section11(ctx)
    if chosen or sec:
        bits = []
        if chosen:
            bits.append("вариант интеграции %s «%s» (`{OUT}/data/integration-options.json`)" % (chosen.get("id", "?"), chosen.get("title", "")))
        if sec:
            bits.append("раздел 11 «Технологическое решение» в `{OUT}/%s`" % sec.relative_to(ctx.out).as_posix())
        return "; ".join(bits)
    if ctx.concept:
        return ("архитектуры ещё нет: опираться на требования MVP из досье, предложения категории `platform` и выбранный стек "
                "раздела 11, когда он будет; файлы и модули — как «планируемые», без `путь:строка`")
    return "фактическая архитектура — `{OUT}/research/product-understanding.md`, `{OUT}/data/repo-scan.json` и код (`путь:строка`)"


# ---------------------------------------------------------------- схемы (FB-006)
def flows_plan(ctx):
    d = _jload(ctx.out / "data" / "flows-plan.json", None)
    if isinstance(d, dict):
        d = d.get("flows") or d.get("items") or []
    return [x for x in d or [] if isinstance(x, dict) and x.get("key")]


def r_flows(ctx):
    rows = flows_plan(ctx)
    if not rows:
        return None                                           # без плана — по-прежнему --set FLOWS=…
    return "; ".join("%s — %s" % (x["key"], x.get("title") or x["key"]) for x in rows)


# ---------------------------------------------------------------- прототип (SM 7)
def r_proto_scope(ctx):
    f = facets(ctx)
    v = f.get("prototype_scope") or f.get("prototype_needed")
    labels = {"core": "ядро расчётов с тестами", "one_screen": "ядро + один рабочий экран", "all_modes": "ядро + оболочка + все режимы интерфейса",
              True: "ядро расчётов + один рабочий экран (по умолчанию)", "yes": "ядро расчётов + один рабочий экран (по умолчанию)"}
    if v in (False, "no", "none"):
        return "владелец ответил, что рабочий прототип не нужен — фазу C8.5 не запускать"
    return labels.get(v, str(v)) if v else "ядро расчётов + один рабочий экран (по умолчанию; владелец объём не уточнял)"


def r_proto_modes(ctx):
    modes = _get(ctx.cfg, "design", "modes") or []
    names = [m.get("id") or m.get("name") if isinstance(m, dict) else str(m) for m in modes]
    names = [n for n in names if n]
    return ", ".join(names) if names else "один режим интерфейса (режимов в `design.modes` нет)"


def r_mode_id(ctx):
    modes = _get(ctx.cfg, "design", "modes") or []
    chosen = _get(ctx.cfg, "design", "chosen")
    for m in modes:
        mid = (m.get("id") or m.get("name")) if isinstance(m, dict) else str(m)
        if mid:
            return str(mid)
    return str(chosen) if chosen else "main"


def r_stack(ctx):
    f = facets(ctx)
    v = f.get("stack") or f.get("prototype_stack")
    return ", ".join(_listify(v)) if v else "статический HTML + CSS + JS без сборки (по умолчанию прототипа; боевой стек — раздел 11)"


def r_canon(ctx):
    if (ctx.out / "data" / "demo-canon.json").exists():
        return "`{OUT}/data/demo-canon.json` — канон демо-данных (числа макетов); прототип обязан его воспроизвести"
    return ("канона демо-данных `data/demo-canon.json` нет — собрать канон в `{OUT}/prototype/fixtures/canon.json` по числам "
            "макетов (`mockups/concepts/*.html`, атрибуты `data-canon`) до написания ядра")


RESOLVERS = {
    "AUDIENCE": ("run-config project.audience (+ release_outward); по умолчанию public", r_audience),
    "AUDIENCE_RULES": ("вычисляется: поправки личного режима по project.audience (concept-outline.md, «Личный режим»)", r_audience_rules),
    "PLATFORM": ("run-config idea.facets.platform_name (опрос, тема «Внешняя платформа») или «определить по досье»", r_platform),
    "PLATFORM_URLS": ("idea.facets.platform_urls + sources.owner_docs[].url + sources.external.site или «найти поиском»", r_platform_urls),
    "DATA_NEEDS": ("idea.facets.platform_data_needs или четыре класса данных по умолчанию", r_data_needs),
    "PLATFORM_ACCESS": ("idea.facets.platform_access или «исследовать законные варианты»", r_platform_access),
    "COMPETITORS_TOP": ("data/competitors.json (direct → indirect, до 8) или sources.competitor_list", r_competitors_top),
    "DATA_SOURCES": ("idea.facets.data_sources_needed или «вывести из досье»", r_data_sources),
    "OWNER_REFS": ("idea.facets.owner_repos/owner_refs + sources.owner_docs[] (role ref|base|follow) или «нет»", r_owner_refs),
    "REQUEST_QUESTIONS": ("run-config idea.request_questions[] (kind research) или «нет»", r_request_questions),
    "AI_ROLE": ("idea.facets.ai_role (или ai) или «вывести из досье»", r_ai_role),
    "AI_WHERE": ("idea.facets.ai_where (+ ai_hardware) или «сравнить варианты»", r_ai_where),
    "ADMIN_NEEDS": ("idea.facets.admin_who/admin_settings/admin_needed или «вывести из досье»", r_admin_needs),
    "ARCH": ("data/plan-baseline.json → architecture; иначе integration-options.json и раздел 11 частей; иначе по режиму", r_arch),
    "FLOWS": ("data/flows-plan.json (ключ — название) или --set", r_flows),
    "PROTO_SCOPE": ("idea.facets.prototype_scope / prototype_needed или «ядро + один экран»", r_proto_scope),
    "PROTO_MODES": ("run-config design.modes[] или «один режим»", r_proto_modes),
    "MODE_ID": ("prototype-mode: --set MODE_ID=<режим>; по умолчанию первый из design.modes", r_mode_id),
    "STACK": ("idea.facets.stack или «статический HTML+CSS+JS без сборки»", r_stack),
    "CANON": ("data/demo-canon.json есть/нет", r_canon),
}


def install(resolvers):
    """Добавить резолверы WP-G в словарь render_brief.RESOLVERS (существующие ключи не трогаются). → число добавленных."""
    n = 0
    for k, v in RESOLVERS.items():
        if k not in resolvers:
            resolvers[k] = v
            n += 1
    return n
