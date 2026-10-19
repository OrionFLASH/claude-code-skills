#!/usr/bin/env python3
"""Каркас факт-листа для авторов стратегии: build/strategy-facts.md.

  facts_scaffold.py <OUT> [--force] [--top 20] [--stdout] [--json] [--draft] [--demo-canon]

Собирает из файлов прогона то, что оркестратор раньше переписывал вручную (references/orchestration.md, фаза 7):
  - цель, ограничения и допущения (build/run-config.json), параметры стратегии;
  - топ-N по `rank` и топ-N по `dep_rank` с `blocked_by` (data/scores.json);
  - кандидаты в «три главные ставки»: лидеры P0 по composite и предложения, которые больше всего разблокируют;
  - допустимые ключи для вставок: графики (`charts.py <OUT> --list-keys`, иначе charts/charts-index.json), макеты
    (data/mockups-index.json), референсы (design-refs/*.json), плейсхолдеры {rank:…}/{deprank:…}/![[mockup:?P…]];
  - расхождения с product-understanding.md (data/fact-check.json, если есть);
  - число предложений по категориям и классам доказательств, «что уже есть» (data/repo-scan.json);
  - режим идеи (mode: concept): идея и светофор предпроверки (data/idea.json, data/typesafe-concept.json), без репозитория;
  - три сценария модели (data/model.json), развилки владельца (research/questions-owner.md);
  - заготовки `<заполнить>`: три ставки, North Star, критерии отказа, pre-mortem, анти-цели, запреты;
  - ёмкость — одна строка scripts/capacity.py (`{capacity}`), сроки и состав MVP — data/plan-baseline.json (`{plan:…}`),
    ключи схем — data/flows-plan.json (если есть), канон демо-данных — data/demo-canon.json (если есть).
--draft (FB-048/049): если data/decisions.json нет — пишет черновик `decisions.py --init --draft` (ставки, критерии отказа,
  North Star, анти-цели, развилки, ёмкость — из данных прогона), а в факт-листе у каждого предложенного значения стоит метка
  `[черновик: источник]`; цель, ограничения, допущения и запреты тоже предлагаются из run-config, досье идеи и legal.md.
  Подтвердили — удалите поле draft в decisions.json и перезапустите (метки станут «[решение: decisions.json]»).
--demo-canon: черновик data/demo-canon.json — единый набор демо-данных для макетов и прототипа (числа модели, вехи плана,
  названия ставок, валюта); не перезаписывает существующий файл.
Только факты из файлов — ничего не выдумывается; нет файла — раздел помечается «нет данных». Метки достоверности: [факт: …], [оценка: …], [допущение].

Защита: если build/strategy-facts.md уже есть, он не перезаписывается (там обычно уже ручная правка); свежий каркас
кладётся в build/strategy-facts.new.md. --force перезаписывает основной файл.
Код выхода: 0 — каркас записан; 2 — нет папки <OUT>/data или data/proposals.json.
Только стандартная библиотека.
"""
import argparse
import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
MARKER = "<!-- generated-by: facts_scaffold.py -->"
NO_DATA = "_нет данных_"
FILL = "<заполнить>"


def load_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default
    except (OSError, json.JSONDecodeError) as e:
        print("предупреждение: не удалось прочитать %s: %s" % (path, e), file=sys.stderr)
        return default


def cell(x, n=None):
    s = "—" if x is None or x == "" else str(x)
    s = re.sub(r"(?<!\\)\|", r"\\|", s).replace("\n", " ")
    return s if not n or len(s) <= n else s[:n - 1].rstrip() + "…"


def table(head, rows):
    out = ["| " + " | ".join(head) + " |", "|" + "|".join("---" for _ in head) + "|"]
    out += ["| " + " | ".join(cell(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def num(x, nd=2):
    if isinstance(x, float):
        return ("%." + str(nd) + "f") % x
    return x


def list_keys(out):
    """charts.py <OUT> --list-keys → {available, skipped}; нет флага/ошибка → None."""
    script = HERE / "charts.py"
    if not script.exists():
        return None
    try:
        r = subprocess.run([sys.executable, "-B", str(script), str(out), "--list-keys"], capture_output=True, text=True, timeout=120)
        if r.returncode == 0:
            d = json.loads(r.stdout)
            if isinstance(d, dict) and isinstance(d.get("available"), list):
                return {"available": d["available"], "skipped": d.get("skipped") or {}}
    except (OSError, subprocess.SubprocessError, ValueError):
        pass
    return None


# ---------------------------------------------------------------- разделы
def sec_product(cfg):
    pr, st, pj = cfg.get("product") or {}, cfg.get("strategy") or {}, cfg.get("project") or {}
    L = ["## Продукт и параметры стратегии", ""]
    if not cfg:
        return L + [NO_DATA + " (нет build/run-config.json).", ""]
    rows = [["продукт", pr.get("name")], ["тип", pr.get("type")], ["вид стратегии", st.get("kind")], ["профиль", st.get("profile") or "standard"],
            ["глубина", st.get("depth")], ["горизонт", "%s мес. + видение %s лет" % (st.get("horizon_months"), st.get("vision_years"))],
            ["рынки", ", ".join(st.get("markets") or [])], ["бюджетные варианты", ", ".join((st.get("budget") or {}).get("variants") or [])],
            ["язык", cfg.get("language")]]
    concept = cfg.get("mode") == "concept"
    if concept:     # режим идеи: продукта и репозитория нет — их параметры не выводятся
        idea = cfg.get("idea") or {}
        rows.insert(1, ["стадия", "идея (продукта ещё нет)"])
        rows.insert(2, ["идея", cell(idea.get("pitch") or "—", 300)])
        rows.append(["модель дохода", st.get("monetization") or "—"])
        if st.get("success_criteria"):
            rows.append(["критерий успеха", st["success_criteria"]])
    keys = (("goal", "цель проекта"), ("currency", "валюта"), ("team_size", "размер команды")) if concept else \
        (("goal", "цель проекта"), ("repo_visibility", "видимость репозитория"), ("publish_code", "публикация кода"),
         ("currency", "валюта"), ("team_size", "размер команды"))
    for k, label in keys:
        if pj.get(k) not in (None, ""):
            rows.append([label, pj[k]])
    return L + [table(["параметр", "значение"], rows), ""]


def derived_constraints(cfg):
    """Ограничения из ответов run-config (команда, ёмкость, бюджет, профиль) — для черновика."""
    import capacity as capmod
    st, pj = cfg.get("strategy") or {}, cfg.get("project") or {}
    c = capmod.capacity(cfg, st.get("horizon_months") or 12)
    parts = ["команда %s чел." % c["team_size"], "ёмкость %s" % c["line"]]
    bv = (st.get("budget") or {}).get("variants") or []
    if bv:
        parts.append("бюджет: %s" % ", ".join(bv))
    if st.get("profile"):
        parts.append("профиль %s" % st["profile"])
    if pj.get("audience"):
        parts.append("для кого: %s" % pj["audience"])
    return "; ".join(parts)


def sec_goal(cfg, draft=False, out=None):
    st = cfg.get("strategy") or {}
    L = ["## Цель и допущения", ""]
    goal = st.get("goal")
    if not goal and draft:
        pitch = (cfg.get("idea") or {}).get("pitch") or st.get("success_criteria")
        goal = ("%s [черновик: run-config idea.pitch / success_criteria]" % pitch) if pitch else None
        L.append("**Цель стратегии:** %s" % (goal or FILL))
    else:
        L.append("**Цель стратегии:** %s [факт: run-config.json]" % (goal or FILL))
    L.append("")
    if st.get("constraints"):
        L.append("**Ограничения:** %s [факт: run-config.json]" % st["constraints"])
    elif draft:
        L.append("**Ограничения:** %s [черновик: run-config project/strategy, capacity.py]" % derived_constraints(cfg))
    else:
        L.append("**Ограничения:** %s [факт: run-config.json]" % FILL)
    if (cfg.get("product") or {}).get("known_facts"):
        L += ["", "**Известные факты от владельца:** %s [факт: run-config.json]" % cfg["product"]["known_facts"]]
    assume = cfg.get("assumptions") or []
    rows = ["- %s [допущение]" % (a if isinstance(a, str) else json.dumps(a, ensure_ascii=False)) for a in assume]
    if not rows and draft and out is not None:
        idea = load_json(out / "data" / "idea.json", {}) or {}
        oq = [q for q in (idea.get("open_questions") or []) if q][:3]
        rows = ["- %s [черновик: открытый вопрос data/idea.json]" % (q.get("text") if isinstance(q, dict) else q) for q in oq]
        m = load_json(out / "data" / "model.json", {}) or {}
        if m.get("mode") == "sensitivity-only":
            rows.append("- входы модели — допущения, денежные итоги — иллюстрация [черновик: data/model.json mode = sensitivity-only]")
        import capacity as capmod
        cp = capmod.params(cfg)
        if not cp["explicit"]:
            rows.append("- ёмкость по умолчанию (%s) [черновик: capacity.py, project.capacity не задана]" % capmod.capacity(cfg, 1)["line"])
    L += ["", "**Допущения прогона:**", ""] + (rows or ["- " + FILL])
    return L + [""]


def sec_capacity_plan(out, cfg):
    """Ёмкость (capacity.py) и базовая линия плана (data/plan-baseline.json): одни числа для всех авторов."""
    import capacity as capmod
    st = cfg.get("strategy") or {}
    c = capmod.capacity(cfg, st.get("horizon_months") or 12)
    L = ["## Ёмкость и базовая линия плана", "",
         "**Ёмкость** `{capacity}` / `{plan:capacity}`: %s [оценка: scripts/capacity.py]. Другого определения рабочего дня в тексте не "
         "использовать — сборка отметит `workday_mismatch`." % c["line"], ""]
    b = load_json(out / "data" / "plan-baseline.json", None)
    if not isinstance(b, dict):
        return L + [NO_DATA + ": нет data/plan-baseline.json — запустите `plan_baseline.py <OUT>` после `gantt.json` и до авторов разделов; "
                    "сроки в тексте — только плейсхолдерами `{plan:beta}`, `{plan:launch}`, `{plan:mvp_ids}`, `{plan:kill.N.date}`.", ""]
    ms = b.get("milestones") or {}
    rows = [[k, "`{plan:%s}`" % k, v.get("month"), v.get("text"), v.get("id") or "—"] for k, v in ms.items() if isinstance(v, dict)]
    L += ["Сроки и состав — из `data/plan-baseline.json` (старт %s, горизонт %s мес.) [факт: plan_baseline.py]; в тексте — плейсхолдеры:"
          % (b.get("start_date"), b.get("horizon_months")), "", table(["веха", "плейсхолдер", "месяц", "дата", "задача Ганта"], rows), ""]
    mvp = b.get("mvp") or {}
    L.append("**Состав MVP** `{plan:mvp_ids}` (%s): %s; середина усилий %s дн. против ёмкости до запуска %s дн." % (
        mvp.get("by"), ", ".join(mvp.get("ids") or []) or "—", mvp.get("effort_days_mid"), mvp.get("capacity_days_to_launch")))
    if mvp.get("only_in_registry"):
        L.append("С тегом `mvp` в реестре, но не в Ганте до запуска (не называть составом MVP): %s." % ", ".join(mvp["only_in_registry"][:30]))
    L.append("")
    for k in b.get("kill") or []:
        L.append("- Критерий отказа ставки %s — дата `{plan:kill.%s.date}` = %s" % (k.get("bet"), k.get("bet"), k.get("text")))
    gc = b.get("gantt_contract") or {}
    for m in gc.get("messages") or []:
        L.append("- Гант: %s" % m)
    if b.get("architecture"):
        a = b["architecture"]
        L.append("- Архитектура `{plan:arch}`: %s (%s дн.; %s) [факт: data/integration-options.json]" % (a.get("name"), a.get("days"), a.get("why")))
    return L + [""]


def sec_flows_plan(out):
    """Ключи схем из data/flows-plan.json — до авторов текста (FB-006)."""
    fp = load_json(out / "data" / "flows-plan.json", None)
    if fp is None:
        return []
    items = fp.get("flows") if isinstance(fp, dict) else fp
    rows = [[x.get("key"), cell(x.get("title"), 60), x.get("agent") or "—"] for x in items or [] if isinstance(x, dict) and x.get("key")]
    if not rows:
        return []
    return ["## Ключи схем (data/flows-plan.json)", "",
            "Схемы `![[flow:ключ]]` — только эти ключи (план создан до авторов, схемы рисуются параллельно):", "",
            table(["ключ", "название", "агент"], rows), ""]


def sec_demo_canon(out):
    c = load_json(out / "data" / "demo-canon.json", None)
    if not isinstance(c, dict):
        return []
    vals = c.get("values") or {}
    rows = [[k, cell(v.get("value") if isinstance(v, dict) else v, 50), (v.get("source") if isinstance(v, dict) else "") or "—"] for k, v in list(vals.items())[:40]]
    return ["## Канон демо-данных (data/demo-canon.json)", "",
            "Макеты, прототип и примеры в тексте берут демо-числа только отсюда (одни и те же у всех агентов); демо помечается «демо».", "",
            table(["ключ", "значение", "источник"], rows), ""]


def demo_canon(out, cfg):
    """Черновик data/demo-canon.json: числа модели (базовый сценарий), вехи плана, ставки, валюта — один набор для макетов."""
    import capacity as capmod
    m = load_json(out / "data" / "model.json", {}) or {}
    b = load_json(out / "data" / "plan-baseline.json", {}) or {}
    d = load_json(out / "data" / "decisions.json", {}) or {}
    vals = {}

    def put(k, v, src):
        if v not in (None, "", []):
            vals[k] = {"value": v, "source": src}
    put("product.name", (cfg.get("product") or {}).get("name") or (cfg.get("idea") or {}).get("name"), "run-config")
    put("currency", m.get("currency_symbol") or (cfg.get("project") or {}).get("currency"), "data/model.json")
    base = (m.get("scenarios") or {}).get("base") or {}
    for k in ("price_month", "price_one_time", "visitors_month", "hourly_rate", "hours_saved_per_week"):
        a = (base.get("assumptions") or {}).get(k)
        if isinstance(a, dict):
            put("model.%s" % k, a.get("value"), "data/model.json base.assumptions (%s)" % a.get("label"))
    for k in ("ltv", "net_revenue", "users_last", "paying_last", "net_value"):
        v = base.get(k) if base.get(k) is not None else (base.get("totals") or {}).get(k)
        if v is None and k.endswith("_last") and base.get("monthly"):
            v = base["monthly"][-1].get(k[:-5])
        put("model.%s" % k, v, "data/model.json base" + (" [иллюстрация]" if m.get("mode") == "sensitivity-only" else ""))
    for k, v in (b.get("milestones") or {}).items():
        if isinstance(v, dict):
            put("plan.%s" % k, v.get("text"), "data/plan-baseline.json")
    for x in d.get("bets") or []:
        put("bet.%s.name" % x.get("id"), x.get("name"), "data/decisions.json")
    ns = (d.get("north_star") or {}).get("metric")
    put("north_star", ns, "data/decisions.json")
    put("capacity", capmod.capacity(cfg, (cfg.get("strategy") or {}).get("horizon_months") or 12)["line"], "scripts/capacity.py")
    return {"version": 1, "generated": date.today().isoformat(), "generated_by": "facts_scaffold.py --demo-canon",
            "label": "демо-данные",
            "rule": "одни демо-числа для всех макетов, прототипа и примеров текста; в макете — атрибут data-canon=\"ключ\" у элемента с числом; "
                    "демо-данные помечаются «демо»; новые сущности (имена, предметы, тикеры) — в entities; кейсы ядра прототипа "
                    "(data-canon=\"<кейс>.<поле>\") — в cases: {id, title, fn, inputs, expected, mockups}",
            "values": vals, "entities": [], "screens": {},
            "cases": []}   # формат prototype/js/core.test.js и prototype/tools/check_canon.py (WP-G): заполняет агент ядра / оркестратор


def sec_top(scores, props, n, by, title):
    L = ["## %s" % title, ""]
    if not scores:
        return L + [NO_DATA + " (нет data/scores.json — запустите score.py).", ""]
    rows_src = [s for s in scores if s.get(by) is not None]
    if not rows_src:
        return L + [NO_DATA + ": в scores.json нет поля `%s` (нужен score.py версии 1.1)." % by, ""]
    rows_src.sort(key=lambda s: s[by])
    rows = []
    for s in rows_src[:n]:
        p = props.get(s["id"], {})
        rows.append([s[by], s["id"], cell(s.get("title") or p.get("title"), 70), s.get("category"), s.get("priority"), s.get("horizon"),
                     num(s.get("composite"), 3), s.get("rank") if by == "dep_rank" else s.get("dep_rank"),
                     ", ".join(s.get("blocked_by") or []) or "—"])
    head = [("dep_rank" if by == "dep_rank" else "rank"), "id", "название", "категория", "приоритет", "горизонт", "composite",
            "rank" if by == "dep_rank" else "dep_rank", "blocked_by"]
    return L + [table(head, rows), ""]


def sec_bets(scores, props):
    L = ["## Кандидаты в «три главные ставки»", ""]
    if not scores:
        return L + [NO_DATA + ".", ""]
    byid = {s["id"]: s for s in scores}
    p0 = sorted((s for s in scores if s.get("priority") == "P0"), key=lambda s: -(s.get("composite") or 0))[:12]
    L += ["**Лидеры P0 по composite** (из `scores.json`):", "",
          table(["id", "название", "rank", "composite", "категория", "горизонт", "усилия (дни)", "разблокирует"],
                [[s["id"], cell(s.get("title") or (props.get(s["id"]) or {}).get("title"), 60), s.get("rank"), num(s.get("composite"), 3), s.get("category"),
                  s.get("horizon"), s.get("effort_days_mid"), len(s.get("unlocks") or [])] for s in p0]), ""]
    # разблокирующие: unlocks из scores.json, иначе обратная карта зависимостей реестра
    deps = {}
    for pid, p in props.items():
        for d in p.get("dependencies") or []:
            deps.setdefault(d, set()).add(pid)
    cnt = {i: (set(byid[i].get("unlocks") or []) if byid.get(i, {}).get("unlocks") else deps.get(i, set())) for i in byid}
    top = sorted((i for i in cnt if cnt[i]), key=lambda i: (-len(cnt[i]), byid[i].get("rank") or 10 ** 6))[:10]
    L.append("**Разблокирующие предложения** (больше всего зависящих от них):")
    L.append("")
    if top:
        L.append(table(["id", "название", "rank", "приоритет", "разблокирует", "кого"],
                       [[i, cell(byid[i].get("title") or (props.get(i) or {}).get("title"), 60), byid[i].get("rank"), byid[i].get("priority"), len(cnt[i]),
                         ", ".join(sorted(cnt[i])[:8])] for i in top]))
    else:
        L.append("нет предложений с зависимыми (`dependencies` пусты).")
    L += ["", "Ставка — связка из 3–8 P-id вокруг одной предпосылки и одного результата; выбирает оркестратор. Опираться на `dep_rank`, а не только на `rank`.", ""]
    return L


def load_decisions(out):
    """data/decisions.json (единый источник решений) и измеримость критериев отказа, если файл есть."""
    d = load_json(out / "data" / "decisions.json", None)
    if not isinstance(d, dict):
        return None, []
    crit = []
    try:
        sys.path.insert(0, str(HERE))
        import sample_size
        crit = sample_size.evaluate_criteria(out, d)
    except Exception as e:                       # измеримость — подсказка, каркас без неё всё равно нужен
        print("предупреждение: измеримость критериев не посчитана: %s" % e, file=sys.stderr)
    return d, crit


def draft_mark(d, key, default="решение: decisions.json"):
    """Метка значения: [черновик: источник] для черновика decisions.json, иначе [решение: decisions.json]."""
    dr = (d or {}).get("draft")
    if not dr:
        return "[%s]" % default
    srcs = dr.get("sources") or {}
    src = srcs.get(key)
    if src is None:
        head = key.rsplit(".", 1)[0]
        while head and head not in srcs and "." in head:
            head = head.rsplit(".", 1)[0]
        src = srcs.get(head) or "данные прогона"
    return "[черновик: %s]" % src


def sec_bets_from_decisions(d, crit):
    import decisions as dm
    L = ["## Три главные ставки (из data/decisions.json)", "",
         "Источник правды — `data/decisions.json`; в тексте разделов — только плейсхолдеры `{bet:N.name}`, `{bet:N.kill}`, "
         "`{bet:N.pids}`… (список — `assemble_strategy.py <OUT> --list-placeholders`). Буквальный порог, отличный от файла, сборка отметит.", ""]
    cmap = {str(c.get("bet")): c for c in crit}
    for b in dm.bets(d):
        i = str(b["id"])
        share = b.get("attention_share")
        L.append("**Ставка %s. «%s».** Что: %s. Почему: %s. Ожидаемый эффект: %s. P-id: %s. Доля внимания команды: %s. %s"
                 % (i, b.get("name") or FILL, b.get("what") or FILL, b.get("why") or FILL, b.get("effect") or FILL,
                    ", ".join(b.get("proposals") or []) or FILL, dm.fmt_pct(share) if dm.is_num(share) else FILL,
                    draft_mark(d, "bets.%s" % i)))
        L.append("")
        k = b.get("kill")
        if isinstance(k, dict):
            c = cmap.get(i) or {}
            meas = ("; измеримость: %s — n %s, %s нед. (%s)" % (c.get("status_text"), dm.fmt_num(c["n"]) if c.get("n") is not None else "—",
                                                             c.get("weeks", "—"), c.get("reason", ""))) if c else ""
            L.append("- Критерий отказа `{bet:%s.kill}`: %s%s%s" % (i, dm.kill_text(k), meas, (" " + draft_mark(d, "bets.%s.kill.threshold" % i)
                                                                                         + " " + draft_mark(d, "bets.%s.kill.date" % i)) if d.get("draft") else ""))
        pm = [dm.item_text(x) for x in b.get("premortem") or []]
        L.append("- Pre-mortem `{bet:%s.premortem}`: %s" % (i, "; ".join(pm) if pm else FILL))
        L.append("")
    if len(dm.bets(d)) < 3:
        L += ["Ставок в decisions.json %d — по методике три: %s" % (len(dm.bets(d)), FILL), ""]
    return L


def sec_northstar_from_decisions(d):
    import decisions as dm
    ns = d.get("north_star") if isinstance(d.get("north_star"), dict) else {}
    dr = bool(d.get("draft"))
    L = ["## North Star, анти-цели, развилки, ёмкость (из data/decisions.json)", ""]
    if dr:
        L += ["> **Черновик решений** (`data/decisions.json → draft`): значения предложены `decisions.py --init --draft` по данным "
              "прогона, у каждого — источник. Подтвердите или поправьте их в `data/decisions.json`, затем удалите поле `draft`.", ""]
    L += ["**North Star Metric** `{north_star}`: %s. Определение: %s. Цель `{north_star.target}`: %s. Входные метрики: %s.%s" % (
             ns.get("metric") or FILL, ns.get("definition") or ("—" if dr else FILL), ns.get("target") or ("—" if dr else FILL),
             "; ".join(ns.get("inputs") or []) or ("—" if dr else FILL), (" " + draft_mark(d, "north_star")) if dr else ""), ""]
    ag = [dm.item_text(x) for x in d.get("anti_goals") or []]
    L += ["**Анти-цели** `{anti_goals}`%s:" % ((" " + draft_mark(d, "anti_goals")) if dr and ag else ""), ""] + \
        (["%d. %s" % (k, t) for k, t in enumerate(ag, 1)] if ag else ["- " + FILL]) + [""]
    forks = [f for f in d.get("forks") or [] if isinstance(f, dict)]
    if forks:
        L += ["**Развилки владельца** (`{fork:F1}`, `{fork:F1.default}`):", "",
              table(["id", "вопрос", "по умолчанию", "цена альтернативы", "решение"],
                    [[f.get("id"), f.get("question"), f.get("default"), f.get("cost"), f.get("decision") or "открыто"] for f in forks]), ""]
    cap = d.get("capacity")
    if isinstance(cap, dict) and cap:
        L += ["**Ёмкость** `{capacity}`: %s" % (cap.get("text") or "; ".join("%s: %s" % (k, v) for k, v in cap.items())), ""]
    if d.get("bans"):
        L += ["**Запреты** `{bans}`%s: %s" % ((" " + draft_mark(d, "bans")) if dr else "", "; ".join(dm.item_text(x) for x in d["bans"])), ""]
    return L


def sec_bets_template():
    L = ["## Три главные ставки (заготовка)", "",
         "Решения записать в `data/decisions.json` (`decisions.py <OUT> --init`, схема — references/decisions.md), а в тексте — "
         "плейсхолдеры `{bet:N.…}`; после записи перезапустите facts_scaffold.py — блок заполнится из файла.", ""]
    for i in (1, 2, 3):
        L += ["**Ставка %d. «%s».** Что: %s. Почему: %s. Ожидаемый эффект (диапазон, метка): %s. P-id: %s. Доля внимания команды: %s."
              % (i, FILL, FILL, FILL, FILL, FILL, FILL), ""]
    return L


def sec_northstar():
    return ["## North Star, критерии отказа, pre-mortem, анти-цели (заготовки)", "",
            "**North Star Metric:** %s. Входные метрики (3–5): %s." % (FILL, FILL), "",
            "**Критерии отказа** (метрика, порог, дата) [допущение]:", "",
            "- Ставка 1: %s" % FILL, "- Ставка 2: %s" % FILL, "- Ставка 3: %s" % FILL, "",
            "**Pre-mortem** (3 причины провала каждой ставки и чем ловим заранее):", "",
            "- Ставка 1: %s" % FILL, "- Ставка 2: %s" % FILL, "- Ставка 3: %s" % FILL, "",
            "**Анти-цели** (3–5 вещей, которые сознательно не делаем в горизонте, и почему): %s" % FILL, ""]


def sec_concept(out):
    """Режим идеи: что известно об идее и итог предпроверки жизнеспособности (data/idea.json, data/typesafe-concept.json)."""
    idea = load_json(out / "data" / "idea.json", None)
    L = ["## Идея и предпроверка жизнеспособности", ""]
    if isinstance(idea, dict):
        L.append("Идея: %s [факт: ответ владельца]. Тип: %s; аудитория: %s; рынки: %s; модель: %s [факт: data/idea.json]." % (
            cell(idea.get("pitch") or "—", 400), idea.get("product_type_label") or idea.get("product_type") or "—",
            idea.get("segment_label") or "—", ", ".join(idea.get("markets") or []) or "—", idea.get("monetization_label") or "—"))
        oq = idea.get("open_questions") or []
        L.append("Открытых вопросов по идее: %d (список — `research/idea-dossier.md`)." % len(oq))
    else:
        L.append(NO_DATA + " (нет data/idea.json — запустите concept_dossier.py).")
    ts = load_json(out / "data" / "typesafe-concept.json", None)
    if isinstance(ts, dict) and ts.get("verdict"):
        L.append("Светофор: **%s** — %s (viability %s, риск %s; источник %s, уверенность %s) [оценка: typesafe_concept.py]." % (
            ts["verdict"], ts.get("verdict_label") or "", ts.get("viability"), ts.get("risk"), ts.get("source"), ts.get("confidence")))
        if ts.get("check_first"):
            L.append("Проверить в первую очередь: %s." % ", ".join(ts["check_first"]))
    else:
        L.append(NO_DATA + " (нет data/typesafe-concept.json — запустите typesafe_concept.py).")
    return L + [""] + sec_findings(out, idea if isinstance(idea, dict) else {})


PREMISE_RU = {"confirmed": "подтверждена", "refuted": "опровергнута", "partial": "частично"}


def sec_findings(out, idea):
    """FB-044/FB-048: блок «Выводы исследования» из data/idea.json (pitch_v2, premises[], request_questions[]) — без ручного
    блока «ВЫВОДЫ» в факт-листе; запасной путь предпосылок — data/premises.json, вопросов запроса — run-config."""
    cfg = load_json(out / "build" / "run-config.json", {}) or {}
    ic = cfg.get("idea") or {}
    pitch_v2 = idea.get("pitch_v2") or ic.get("pitch_v2")
    prem = idea.get("premises")
    pdoc = load_json(out / "data" / "premises.json", None)
    if not isinstance(prem, list) or not prem:
        prem = (pdoc or {}).get("premises") if isinstance(pdoc, dict) else []
    prem = [p for p in prem or [] if isinstance(p, dict)]
    rqs = [q for q in (idea.get("request_questions") or ic.get("request_questions") or []) if isinstance(q, dict) and q.get("id")]
    if not (pitch_v2 or prem or rqs):
        return []
    L = ["## Выводы исследования", ""]
    if pitch_v2:
        L.append("Идея v%s после пересмотра (C4.5): %s [факт: решение владельца, data/premises.json]." % (
            idea.get("version") or ic.get("version") or 2, cell(pitch_v2, 400)))
    if prem:
        L.append("")
        L.append(table(["предпосылка", "вид", "статус", "источник"],
                       [[cell(p.get("text"), 160), p.get("kind") or "—", PREMISE_RU.get(p.get("status"), p.get("status") or "не проверена"),
                         cell(p.get("source") or "—", 80)] for p in prem]))
        dec = (pdoc or {}).get("decision") if isinstance(pdoc, dict) else idea.get("pivot_decision")
        if dec:
            L.append("")
            L.append("Решение владельца по пересмотру: %s." % {"keep": "продолжить с исходной идеей", "narrow": "принять сужение",
                                                              "stop": "остановиться"}.get(dec, dec))
    if rqs:
        L += ["", "**Вопросы запроса** — ответ на каждый в тексте с маркером `[RQnn]` (сборка проверяет):", ""]
        L += ["- `[%s]` (%s) %s" % (q["id"], q.get("kind") or "research", cell(q.get("text"), 220)) for q in rqs]
    return L + [""]


def sec_exists(out, cfg=None):
    if (cfg or {}).get("mode") == "concept":
        return ["## Что уже есть (не предлагать как новое)", "",
                "Продукта ещё нет (режим идеи): все предложения — новые, `current_feature` — «нет (продукта ещё нет)». "
                "Опора — `research/idea-dossier.md` и `data/idea.json`; аналоги и их решения — `data/competitors.json`.", ""]
    if ((cfg or {}).get("product") or {}).get("mode") == "external":     # внешний продукт без кода: инвентарь — APK и магазины
        import app_scan                                                  # noqa: E402 — тот же каталог scripts/
        return ["## Что уже есть (не предлагать как новое)", ""] + app_scan.inventory_lines(out) + [
            "Дополнить по `research/product-understanding.md` и `research/ui-inventory.md`: %s" % FILL, ""]
    rs = load_json(out / "data" / "repo-scan.json", None)
    L = ["## Что уже есть (не предлагать как новое)", ""]
    feats = [f.get("name") for f in (rs or {}).get("features") or [] if isinstance(f, dict) and f.get("name")] if isinstance(rs, dict) else []
    if feats:
        L.append("Функции из `data/repo-scan.json` [факт: repo-scan.json]: " + "; ".join(feats[:40]) + ("; и ещё %d" % (len(feats) - 40) if len(feats) > 40 else "") + ".")
        L.append("")
    else:
        L += [NO_DATA + " (нет функций в data/repo-scan.json).", ""]
    L += ["Дополнить по `research/product-understanding.md`: %s" % FILL, ""]
    return L


def sec_factcheck(out, cfg=None):
    L = ["## Расхождения с досье идеи (research/idea-dossier.md)" if (cfg or {}).get("mode") == "concept"
         else "## Расхождения с product-understanding.md", ""]
    fc = load_json(out / "data" / "fact-check.json", None)
    if fc is None:
        return L + [NO_DATA + ": data/fact-check.json нет (сверка фактов не проводилась или расхождений не найдено).", ""]
    items = fc if isinstance(fc, list) else (fc.get("items") or fc.get("discrepancies") or fc.get("checks") or []) if isinstance(fc, dict) else []
    if not items:
        return L + ["В data/fact-check.json расхождений нет.", ""]
    for it in items:
        if isinstance(it, dict):
            parts = []
            for keys, label in ((("claim", "fact", "topic", "what", "title"), None), (("was", "before", "phase1", "understanding", "product_understanding"), "было"),
                                (("now", "after", "actual", "correct", "fix"), "стало"), (("source", "evidence"), "источник"), (("status",), "статус")):
                for k in keys:
                    if it.get(k) not in (None, ""):
                        parts.append(("%s: " % label if label else "") + str(it[k]))
                        break
            L.append("- " + ("; ".join(parts) if parts else json.dumps(it, ensure_ascii=False)))
        else:
            L.append("- %s" % it)
    return L + [""]


def sec_counts(props):
    L = ["## Реестр в числах", ""]
    if not props:
        return L + [NO_DATA + ".", ""]
    cats = sorted({p.get("category") or "?" for p in props.values()})
    cl = "ABCD"
    rows = []
    for c in cats:
        ps = [p for p in props.values() if (p.get("category") or "?") == c]
        rows.append([c, len(ps)] + [sum(1 for p in ps if p.get("evidence_class") == k) for k in cl])
    rows.append(["**всего**", len(props)] + [sum(1 for p in props.values() if p.get("evidence_class") == k) for k in cl])
    return L + [table(["категория", "всего", "A", "B", "C", "D"], rows), ""]


def sec_model(out):
    m = load_json(out / "data" / "model.json", None)
    L = ["## Три сценария модели", ""]
    if not isinstance(m, dict) or not m.get("scenarios"):
        return L + [NO_DATA + " (нет data/model.json).", ""]
    sc = m["scenarios"]
    names = [n for n in ("pessimistic", "base", "optimistic") if n in sc] + [n for n in sc if n not in ("pessimistic", "base", "optimistic")]
    metrics = ["cac", "ltv", "ltv_cac", "payback_months", "arpu", "arppu", "churn", "roi", "breakeven_month"]

    def tot(s, k):
        t = s.get("totals")
        return t.get(k) if isinstance(t, dict) else None
    rows = [[k] + [num(sc[n].get(k), 3) for n in names] for k in metrics if any(sc[n].get(k) is not None for n in names)]
    if m.get("capacity", {}).get("line"):
        notes_cap = m["capacity"]["line"]
    else:
        notes_cap = None
    for k in ("revenue", "net", "cost", "paying"):
        if any(tot(sc[n], k) is not None for n in names):
            rows.append(["итого " + k] + [num(tot(sc[n], k), 1) for n in names])
    last = {n: (sc[n].get("monthly") or [None])[-1] for n in names}
    for k in ("users", "paying"):
        if any(isinstance(v, dict) and v.get(k) is not None for v in last.values()):
            rows.append(["%s в последнем месяце" % k] + [num((last[n] or {}).get(k), 1) for n in names])
    L.append("Валюта %s, модель выручки %s, профиль %s, горизонт %s мес. [оценка: model.py, допущения]" % (
        m.get("currency", "—"), m.get("revenue_model", "—"), m.get("model_profile", "—"), m.get("horizon_months", "—")))
    if m.get("mode") == "sensitivity-only":
        L.append("")
        L.append("**Режим sensitivity-only:** денежные итоги — иллюстрация; в тексте — только `{model:…}` (сборка добавит метку "
                 "«%s») или буквально с этой меткой." % ((m.get("illustration") or {}).get("label") or "[иллюстрация при допущениях]"))
    if m.get("model_profile") == "personal":
        metrics = ["value", "cost", "net_value", "hours_spent", "hours_saved", "breakeven_month", "hours_breakeven_month", "roi",
                   "hours_saved_per_week_to_break_even"]
    L.append("")
    L.append(table(["метрика"] + names, rows))
    notes = m.get("notes") or []
    if notes:
        L += ["", "Примечания модели:"] + ["- %s" % n for n in notes[:6]]
    if notes_cap:
        L += ["- ёмкость в модели: %s" % notes_cap]
    for it in (m.get("reconciliation") or {}).get("items") or []:
        L.append("- ! сверка модели с планом: %s" % it.get("message"))
    return L + [""]


def sec_keys(out):
    L = ["## Допустимые ключи для вставок", ""]
    lk = list_keys(out)
    idx = load_json(out / "charts" / "charts-index.json", None)
    L.append("**Графики** — `![[chart:ключ]]`. Ключей вне списка не использовать: сборка (`assemble_strategy.py`) считает их ошибкой.")
    L.append("")
    if lk is not None:
        L.append("Источник: `charts.py --list-keys`.")
        L.append("")
        L.append("Доступны: " + (", ".join("`%s`" % k for k in lk["available"]) or NO_DATA))
        if lk["skipped"]:
            L += ["", "Пропущены:"] + ["- `%s` — %s" % (k, v) for k, v in lk["skipped"].items()]
    elif isinstance(idx, list) and idx:
        L.append("Источник: charts/charts-index.json (`charts.py --list-keys` недоступен).")
        L += ["", "Доступны: " + ", ".join("`%s`" % c["key"] for c in idx if isinstance(c, dict) and c.get("key"))]
        L += ["", "График `gantt` появляется после записи data/gantt.json и запуска charts.py."]
    else:
        L.append(NO_DATA + ": нет charts/charts-index.json — запустите charts.py до написания разделов.")
    mk = load_json(out / "data" / "mockups-index.json", None)
    L += ["", "**Макеты** — `![[mockup:ключ]]`; для макета предложения, если он может появиться позже, — `![[mockup:?P058]]` (сборщик разрешит или уберёт):", ""]
    if isinstance(mk, list) and mk:
        L.append(table(["ключ", "название", "предложения"], [[m.get("key"), cell(m.get("title"), 60), ", ".join(m.get("proposals") or []) or "—"] for m in mk if isinstance(m, dict)]))
    else:
        L.append(NO_DATA + " (макетов ещё нет; используйте `![[mockup:?Pxxx]]`).")
    refs = sorted((out / "design-refs").glob("[0-9]*.json"))
    L += ["", "**Референсы** — `![[ref:NN-slug]]`:", ""]
    if refs:
        rows = []
        for f in refs:
            d = load_json(f, {}) or {}
            rows.append([f.stem, cell(d.get("title"), 60), ", ".join(d.get("proposals") or []) or "—"])
        L.append(table(["ключ", "название", "предложения"], rows))
    else:
        L.append(NO_DATA + " (design-refs/ пуст).")
    L += ["", "**Плейсхолдеры:** `{rank:P032}` — актуальный ранг, `{deprank:P032}` — ранг с учётом зависимостей (подставляет `assemble_strategy.py`); числа рангов вручную не писать.",
          "Решения — `{bet:1.name}`, `{bet:1.kill}`, `{north_star}`, `{anti_goals}`, `{fork:F1}` (data/decisions.json); числа модели — "
          "`{model:base.ltv|money}`, `{model:pess.cac}`, `{model:base.users_last|0}` (data/model.json); выборки и сроки — `{exp:E01.n}`, "
          "`{exp:E01.weeks}` (data/experiments.json, sample_size.py). Полный список ключей со значениями — `assemble_strategy.py <OUT> --list-placeholders`.", ""]
    return L


def sec_questions(out, forks_in_decisions=False):
    L = ["## Развилки владельца", ""]
    if forks_in_decisions:
        return L + ["Развилки — в data/decisions.json (`{fork:F1}`, блок выше); исходные вопросы — research/questions-owner.md.", ""]
    f = out / "research" / "questions-owner.md"
    if not f.is_file():
        return L + [NO_DATA + ": research/questions-owner.md нет. Каждую развилку описывать как «вариант по умолчанию + цена альтернативы»: %s" % FILL, ""]
    qs = []
    for line in f.read_text(encoding="utf-8").splitlines():
        m = re.match(r"\s*(\d+)\.\s+(.*)", line)
        if m:
            qs.append((m.group(1), m.group(2).strip()))
    if not qs:
        return L + ["В research/questions-owner.md нет нумерованных вопросов.", ""]
    return L + ["Из `research/questions-owner.md`; описывать как развилки с вариантом по умолчанию:", ""] + ["%s. %s" % (n, cell(t, 320)) for n, t in qs[:12]] + [""]


def sec_bans(cfg, d=None, draft=False):
    cons = (cfg.get("strategy") or {}).get("constraints")
    bans = [x if isinstance(x, str) else json.dumps(x, ensure_ascii=False) for x in ((d or {}).get("bans") or [])]
    if draft and (bans or cons):
        L = ["## Запреты", ""]
        if cons:
            L.append("Из ограничений прогона: %s [факт: run-config.json]" % cons)
        L += ["- %s %s" % (x, draft_mark(d, "bans")) for x in bans if x != cons]
        return L + [""]
    return ["## Запреты", "", "Из ограничений прогона: %s [факт: run-config.json]" % (cons or FILL), "",
            "Дополнить: %s" % FILL, ""]


def build(out, n, draft=False):
    cfg = load_json(out / "build" / "run-config.json", {}) or {}
    props_l = load_json(out / "data" / "proposals.json", []) or []
    props = {p["id"]: p for p in props_l if isinstance(p, dict) and p.get("id")}
    scores = load_json(out / "data" / "scores.json", None)
    scores = [s for s in scores if isinstance(s, dict) and s.get("id")] if isinstance(scores, list) else None
    name = (cfg.get("product") or {}).get("name") or ""
    L = [MARKER, "# Факт-лист для авторов стратегии" + (": %s" % name if name else ""), "",
         "Каркас собран `facts_scaffold.py` %s из файлов прогона. Метка «%s» — место для оркестратора; все числа — из `data/*.json`. "
         "Метки достоверности в тексте: `[факт: источник, дата]`, `[оценка: метод]`, `[допущение]`." % (date.today().isoformat(), FILL), "",
         ("Топ-20 и подробности по P-id — вместе с `data/scores.json`; режим идеи — продукта ещё нет, идею и ответы владельца сверять с "
          "`research/idea-dossier.md`%s." % ("" if (out / "research" / "idea-dossier.md").exists() else " (файла пока нет)"))
         if cfg.get("mode") == "concept" else
         "Топ-20 и подробности по P-id — вместе с `data/scores.json`; существование функций сверять с `research/product-understanding.md`%s." %
         ("" if (out / "research" / "product-understanding.md").exists() else " (файла пока нет)"), ""]
    dec, crit = load_decisions(out)
    bets_part = sec_bets_from_decisions(dec, crit) if dec else sec_bets_template()
    ns_part = sec_northstar_from_decisions(dec) if dec else sec_northstar()
    for part in (sec_product(cfg), sec_goal(cfg, draft, out), sec_concept(out) if cfg.get("mode") == "concept" else [],
                 sec_capacity_plan(out, cfg),
                 sec_top(scores, props, n, "rank", "Топ-%d по рангу" % n),
                 sec_top(scores, props, n, "dep_rank", "Топ-%d по рангу с учётом зависимостей (dep_rank)" % n),
                 sec_bets(scores, props), bets_part, ns_part, sec_exists(out, cfg), sec_factcheck(out, cfg), sec_counts(props),
                 sec_model(out), sec_keys(out), sec_flows_plan(out), sec_demo_canon(out), sec_questions(out, draft and bool(dec)),
                 sec_bans(cfg, dec, draft)):
        L += part
    return "\n".join(L).rstrip() + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0], formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out", help="папка прогона <OUT>")
    ap.add_argument("--top", type=int, default=20, help="длина списков топ (по умолчанию 20)")
    ap.add_argument("--force", action="store_true", help="перезаписать build/strategy-facts.md, даже если он уже есть")
    ap.add_argument("--stdout", action="store_true", help="напечатать каркас, файл не писать")
    ap.add_argument("--json", action="store_true", help="печатать краткий отчёт JSON")
    ap.add_argument("--draft", action="store_true", help="предложить значения из данных (черновик decisions.json, метки [черновик: …])")
    ap.add_argument("--demo-canon", action="store_true", help="записать черновик data/demo-canon.json (если его нет)")
    a = ap.parse_args(argv)
    out = Path(a.out).resolve()
    if not (out / "data" / "proposals.json").exists():
        print("ошибка: нет %s/data/proposals.json" % out, file=sys.stderr)
        return 2
    if a.draft and not (out / "data" / "decisions.json").exists():
        import decisions as dm
        (out / "data" / "decisions.json").write_text(json.dumps(dm.draft(out), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("создан черновик data/decisions.json (decisions.py --init --draft): подтвердите значения и удалите поле draft", file=sys.stderr)
    if a.demo_canon:
        dc = out / "data" / "demo-canon.json"
        if dc.exists():
            print("data/demo-canon.json уже есть — не перезаписываю", file=sys.stderr)
        else:
            cfg0 = load_json(out / "build" / "run-config.json", {}) or {}
            dc.write_text(json.dumps(demo_canon(out, cfg0), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print("записан черновик %s — дополните entities/screens до волны макетов" % dc, file=sys.stderr)
    text = build(out, max(1, a.top), a.draft)
    if a.stdout:
        sys.stdout.write(text)
        return 0
    target = out / "build" / "strategy-facts.md"
    protected = target.exists() and not a.force
    if protected:
        target = out / "build" / "strategy-facts.new.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    rep = {"ok": True, "file": target.relative_to(out).as_posix(), "protected": protected, "no_data_sections": text.count(NO_DATA), "placeholders": text.count(FILL)}
    if a.json:
        print(json.dumps(rep, ensure_ascii=False, indent=2))
    else:
        print("записано %s (разделов «нет данных»: %d, мест «%s»: %d)" % (target, rep["no_data_sections"], FILL, rep["placeholders"]))
        if protected:
            print("предупреждение: build/strategy-facts.md уже есть и не перезаписан; свежий каркас — рядом; --force перезапишет основной файл", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
