#!/usr/bin/env python3
"""Каркас факт-листа для авторов стратегии: build/strategy-facts.md.

  facts_scaffold.py <OUT> [--force] [--top 20] [--stdout] [--json]

Собирает из файлов прогона то, что оркестратор раньше переписывал вручную (references/orchestration.md, фаза 7):
  - цель, ограничения и допущения (build/run-config.json), параметры стратегии;
  - топ-N по `rank` и топ-N по `dep_rank` с `blocked_by` (data/scores.json);
  - кандидаты в «три главные ставки»: лидеры P0 по composite и предложения, которые больше всего разблокируют;
  - допустимые ключи для вставок: графики (`charts.py <OUT> --list-keys`, иначе charts/charts-index.json), макеты
    (data/mockups-index.json), референсы (design-refs/*.json), плейсхолдеры {rank:…}/{deprank:…}/![[mockup:?P…]];
  - расхождения с product-understanding.md (data/fact-check.json, если есть);
  - число предложений по категориям и классам доказательств, «что уже есть» (data/repo-scan.json);
  - три сценария модели (data/model.json), развилки владельца (research/questions-owner.md);
  - заготовки `<заполнить>`: три ставки, North Star, критерии отказа, pre-mortem, анти-цели, запреты.
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
    for k, label in (("goal", "цель проекта"), ("repo_visibility", "видимость репозитория"), ("publish_code", "публикация кода"),
                     ("currency", "валюта"), ("team_size", "размер команды")):
        if pj.get(k) not in (None, ""):
            rows.append([label, pj[k]])
    return L + [table(["параметр", "значение"], rows), ""]


def sec_goal(cfg):
    st = cfg.get("strategy") or {}
    L = ["## Цель и допущения", ""]
    L.append("**Цель стратегии:** %s [факт: run-config.json]" % (st.get("goal") or FILL))
    L.append("")
    L.append("**Ограничения:** %s [факт: run-config.json]" % (st.get("constraints") or FILL))
    if (cfg.get("product") or {}).get("known_facts"):
        L += ["", "**Известные факты от владельца:** %s [факт: run-config.json]" % cfg["product"]["known_facts"]]
    assume = cfg.get("assumptions") or []
    L += ["", "**Допущения прогона:**", ""] + (["- %s [допущение]" % a for a in assume] if assume else ["- " + FILL])
    return L + [""]


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


def sec_bets_template():
    L = ["## Три главные ставки (заготовка)", ""]
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


def sec_exists(out):
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


def sec_factcheck(out):
    L = ["## Расхождения с product-understanding.md", ""]
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
    for k in ("revenue", "net", "cost", "paying"):
        if any(tot(sc[n], k) is not None for n in names):
            rows.append(["итого " + k] + [num(tot(sc[n], k), 1) for n in names])
    last = {n: (sc[n].get("monthly") or [None])[-1] for n in names}
    for k in ("users", "paying"):
        if any(isinstance(v, dict) and v.get(k) is not None for v in last.values()):
            rows.append(["%s в последнем месяце" % k] + [num((last[n] or {}).get(k), 1) for n in names])
    L.append("Валюта %s, модель выручки %s, горизонт %s мес. [оценка: model.py, допущения]" % (m.get("currency", "—"), m.get("revenue_model", "—"), m.get("horizon_months", "—")))
    L.append("")
    L.append(table(["метрика"] + names, rows))
    notes = m.get("notes") or []
    if notes:
        L += ["", "Примечания модели:"] + ["- %s" % n for n in notes[:6]]
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
    L += ["", "**Плейсхолдеры:** `{rank:P032}` — актуальный ранг, `{deprank:P032}` — ранг с учётом зависимостей (подставляет `assemble_strategy.py`); числа рангов вручную не писать.", ""]
    return L


def sec_questions(out):
    L = ["## Развилки владельца", ""]
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


def sec_bans(cfg):
    return ["## Запреты", "", "Из ограничений прогона: %s [факт: run-config.json]" % ((cfg.get("strategy") or {}).get("constraints") or FILL), "",
            "Дополнить: %s" % FILL, ""]


def build(out, n):
    cfg = load_json(out / "build" / "run-config.json", {}) or {}
    props_l = load_json(out / "data" / "proposals.json", []) or []
    props = {p["id"]: p for p in props_l if isinstance(p, dict) and p.get("id")}
    scores = load_json(out / "data" / "scores.json", None)
    scores = [s for s in scores if isinstance(s, dict) and s.get("id")] if isinstance(scores, list) else None
    name = (cfg.get("product") or {}).get("name") or ""
    L = [MARKER, "# Факт-лист для авторов стратегии" + (": %s" % name if name else ""), "",
         "Каркас собран `facts_scaffold.py` %s из файлов прогона. Метка «%s» — место для оркестратора; все числа — из `data/*.json`. "
         "Метки достоверности в тексте: `[факт: источник, дата]`, `[оценка: метод]`, `[допущение]`." % (date.today().isoformat(), FILL), "",
         "Топ-20 и подробности по P-id — вместе с `data/scores.json`; существование функций сверять с `research/product-understanding.md`%s." %
         ("" if (out / "research" / "product-understanding.md").exists() else " (файла пока нет)"), ""]
    for part in (sec_product(cfg), sec_goal(cfg),
                 sec_top(scores, props, n, "rank", "Топ-%d по рангу" % n),
                 sec_top(scores, props, n, "dep_rank", "Топ-%d по рангу с учётом зависимостей (dep_rank)" % n),
                 sec_bets(scores, props), sec_bets_template(), sec_northstar(), sec_exists(out), sec_factcheck(out), sec_counts(props),
                 sec_model(out), sec_keys(out), sec_questions(out), sec_bans(cfg)):
        L += part
    return "\n".join(L).rstrip() + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0], formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out", help="папка прогона <OUT>")
    ap.add_argument("--top", type=int, default=20, help="длина списков топ (по умолчанию 20)")
    ap.add_argument("--force", action="store_true", help="перезаписать build/strategy-facts.md, даже если он уже есть")
    ap.add_argument("--stdout", action="store_true", help="напечатать каркас, файл не писать")
    ap.add_argument("--json", action="store_true", help="печатать краткий отчёт JSON")
    a = ap.parse_args(argv)
    out = Path(a.out).resolve()
    if not (out / "data" / "proposals.json").exists():
        print("ошибка: нет %s/data/proposals.json" % out, file=sys.stderr)
        return 2
    text = build(out, max(1, a.top))
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
