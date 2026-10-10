#!/usr/bin/env python3
"""Сборка research/methodology.md из шаблона: подстановка фактических весов, чувствительности, распределений, профиля, TypeSafe.

  build_methodology.py <OUT> [--force] [--stdout] [--json]

Берёт ТОЛЬКО факты из файлов прогона; нет файла — раздел помечается «нет данных»:
  data/weights.json (веса), data/sensitivity.json (торнадо, устойчивость топ-20, число прогонов), data/proposals.json
  и data/registry-check.json (классы доказательств, категории, горизонты), build/run-config.json (профиль, глубина,
  допущения), data/typesafe-jev.json + data/scores.json (модель Jev, число оценок, корреляции), data/model.json,
  data/keywords.json. Формулы — краткая сводка references/scoring.md; якоря шкал — ссылка на references/methodology-anchors.md.

Блок «Адаптация якорей под продукт» остаётся для автора (помечен <заполнить>): скрипт не выдумывает смысл шкал.
Защита: если research/methodology.md уже есть и написан вручную (нет строки-маркера «generated-by: build_methodology.py»),
файл не перезаписывается — результат кладётся в research/methodology.generated.md; --force перезаписывает.
Код выхода: 0 — файл записан (при защите — в .generated.md, предупреждение в stderr и поле protected в --json); 2 — нет папки <OUT>/data.
Только стандартная библиотека.
"""
import argparse
import importlib.util
import json
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
MARKER = "<!-- generated-by: build_methodology.py -->"
NO_DATA = "_нет данных_"
CLASS_TEXT = {
    "A": "первоисточник или живая функция (документация платформы, работающая функция конкурента, функция нашего продукта)",
    "B": "несколько независимых упоминаний (2+ источника)",
    "C": "одно упоминание (одна Issue, пост, отзыв)",
    "D": "логический вывод без внешнего источника",
}


def load_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default
    except (OSError, json.JSONDecodeError) as e:
        print("предупреждение: не удалось прочитать %s: %s" % (path, e), file=sys.stderr)
        return default


def table(head, rows):
    out = ["| " + " | ".join(head) + " |", "|" + "|".join("---" for _ in head) + "|"]
    for r in rows:
        out.append("| " + " | ".join(str(c).replace("|", "\\|").replace("\n", " ") for c in r) + " |")
    return "\n".join(out)


def num(x, nd=2):
    if isinstance(x, float):
        return ("%." + str(nd) + "f") % x
    return str(x)


def pct(x):
    return "%.0f %%" % (x * 100) if isinstance(x, (int, float)) else str(x)


def default_weights():
    try:
        spec = importlib.util.spec_from_file_location("ps_score_defaults", HERE / "score.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return getattr(mod, "DEFAULT_WEIGHTS", None)
    except Exception:
        return None


def ranks(vals):
    order = sorted(range(len(vals)), key=lambda i: vals[i])
    r = [0.0] * len(vals)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and vals[order[j + 1]] == vals[order[i]]:
            j += 1
        for k in range(i, j + 1):
            r[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return r


def spearman(x, y):
    if len(x) < 3:
        return None
    rx, ry = ranks(x), ranks(y)
    mx, my = sum(rx) / len(rx), sum(ry) / len(ry)
    sx = sum((a - mx) ** 2 for a in rx) ** 0.5
    sy = sum((b - my) ** 2 for b in ry) ** 0.5
    if not sx or not sy:
        return None
    return sum((a - mx) * (b - my) for a, b in zip(rx, ry)) / (sx * sy)


# ---------------------------------------------------------------- разделы
def sec_scales(skill_note):
    return ["## 1. Шкалы и якоря", "",
            "Все оценки — шкалы 1–5. `value` — ценность (выше — лучше); `cost` — стоимость и `risk` — риск (1 — дёшево/безопасно, 5 — дорого/опасно); "
            "`confidence` — уверенность, не выше класса доказательства (A ≤ 5, B ≤ 4, C ≤ 3, D ≤ 2). Подшкалы ценности (`reach`, `impact`, `activation` …) "
            "необязательны: нет подшкалы — берётся `value`.", "",
            "Якоря шкал (что значит 1, 3, 5) — `references/methodology-anchors.md` скилла product-strategy.", "",
            "### Адаптация якорей под продукт", "",
            "<заполнить: что значат value 5, reach 5, cost 5, risk 5 именно для этого продукта; на какие данные опирается confidence>", ""]


def sec_formulas():
    return ["## 2. Формулы (кратко)", "",
            "Полный вывод — `references/scoring.md`; единственный источник правды — `scripts/score.py`, независимая сверка — `scripts/validate_scores.py`.", "",
            table(["показатель", "формула"], [
                ["value_index / cost_index / risk_index", "взвешенное среднее экспертной оценки и подшкал / числовых полей (трудозатраты, деньги, срок, зависимости) / шести видов риска"],
                ["confidence_calc", "0,6·E(класс доказательства) + 0,25·testability/5 + 0,15·(6 − spread)/5; E: A 1,0 · B 0,8 · C 0,55 · D 0,35"],
                ["RICE", "охват × влияние × confidence_calc / трудозатраты (середина effort_days, не менее 0,5)"],
                ["ICE", "value_index × (confidence_calc·5) × (6 − cost_index)"],
                ["WSJF", "(ценность + срочность + снижение риска/возможность) / cost_index"],
                ["risk_adjusted", "value_index × (1 − 0,5·(risk_index − 1)/4)"],
                ["composite", "взвешенная сумма минимакс-нормированных RICE (по log(1 + RICE)), ICE, WSJF, risk_adjusted; ранг — по убыванию, при равенстве по id"],
                ["квадрант / приоритет", "по медианам value и cost: quick_win, big_bet, filler, money_pit; P0 — первые 15 % рангов только из quick_win и big_bet; P1 до 40 %, P2 до 70 %, остальное P3"],
            ]), ""]


def sec_weights(out):
    w = load_json(out / "data" / "weights.json", None)
    lines = ["## 3. Фактические веса", ""]
    if not isinstance(w, dict):
        return lines + [NO_DATA + " (нет data/weights.json — запустите score.py).", ""]
    d = default_weights() or {}
    changed = []
    lines.append("Файл `data/weights.json` (версия %s). В колонке «по умолчанию» (если есть) — значение, встроенное в `score.py`, где вес изменён." % w.get("version", "?"))
    lines.append("")
    for grp, title in (("composite", "Композит"), ("value", "Индекс ценности"), ("cost", "Индекс стоимости"), ("risk", "Индекс риска")):
        g = w.get(grp)
        if not isinstance(g, dict):
            continue
        rows = []
        for k, v in g.items():
            dv = (d.get(grp) or {}).get(k) if isinstance(d.get(grp), dict) else None
            mark = ""
            if dv is not None and dv != v:
                mark = "≠ %s" % dv
                changed.append("%s.%s" % (grp, k))
            rows.append([k, v, mark])
        if any(r[2] for r in rows):
            lines += ["**%s**" % title, "", table(["ключ", "вес", "по умолчанию"], rows), ""]
        else:
            lines += ["**%s**" % title, "", table(["ключ", "вес"], [r[:2] for r in rows]), ""]
    if not d:
        lines.append("_Сравнение со значениями по умолчанию недоступно (не удалось прочитать score.py)._")
    elif changed:
        lines.append("Изменены относительно умолчаний: %s." % ", ".join("`%s`" % c for c in changed))
    else:
        lines.append("Все веса совпадают со встроенными умолчаниями `score.py`: это допущение скилла, а не результат калибровки на данных.")
    lines.append("")
    return lines


def sec_sensitivity(out):
    s = load_json(out / "data" / "sensitivity.json", None)
    lines = ["## 4. Чувствительность к весам", ""]
    if not isinstance(s, dict):
        return lines + [NO_DATA + " (нет data/sensitivity.json).", ""]
    n = s.get("top_n", 20)
    lines.append("Каждый вес групп composite, value, cost, risk поочерёдно умножался на 0,5 и 1,5; реестр переранжировался (`score.py`).")
    lines.append("")
    facts = []
    if s.get("runs") is not None:
        facts.append("прогонов: %s" % s["runs"])
    if isinstance(s.get("top20_stability"), (int, float)):
        facts.append("устойчивость топ-%s: %s (доля предложений, не выпавших из топ-%s ни в одном прогоне)" % (n, pct(s["top20_stability"]), n))
    if isinstance(s.get("always_top20"), list):
        facts.append("всегда в топ-%s: %d предложений" % (n, len(s["always_top20"])))
    lines += ["- " + f for f in facts] if facts else [NO_DATA]
    tor = s.get("tornado")
    if isinstance(tor, list) and tor:
        lines += ["", "Самые чувствительные параметры (по сумме сдвигов ранга):", ""]
        lines.append(table(["параметр", "сдвиг ранга ×0,5", "сдвиг ранга ×1,5", "swing"],
                           [[t.get("param"), num(t.get("low_rank_shift")), num(t.get("high_rank_shift")), num(t.get("swing"))] for t in tor[:6]]))
    lines.append("")
    return lines


def sec_evidence(out):
    props = load_json(out / "data" / "proposals.json", None)
    rc = load_json(out / "data" / "registry-check.json", None)
    lines = ["## 5. Классы доказательств и распределение реестра", ""]
    lines.append(table(["класс", "что это"], [[k, v] for k, v in CLASS_TEXT.items()]))
    lines.append("")
    if not isinstance(props, list) or not props:
        return lines + [NO_DATA + " (нет data/proposals.json).", ""]
    total = len(props)
    cls, cat, hor = {}, {}, {}
    for p in props:
        cls[p.get("evidence_class") or "?"] = cls.get(p.get("evidence_class") or "?", 0) + 1
        cat[p.get("category") or "?"] = cat.get(p.get("category") or "?", 0) + 1
        hor[p.get("horizon") or "?"] = hor.get(p.get("horizon") or "?", 0) + 1
    ab = (cls.get("A", 0) + cls.get("B", 0)) / total
    lines.append("Предложений в реестре: **%d**. Доля классов A+B: **%s** (порог проверки `check_registry.py` — 60 %%)." % (total, pct(ab)))
    lines += ["", table(["класс", "число", "доля"], [[k, cls.get(k, 0), pct(cls.get(k, 0) / total)] for k in "ABCD"] +
                         [[k, v, pct(v / total)] for k, v in cls.items() if k not in "ABCD"]), ""]
    mins = (rc or {}).get("category_minimums") if isinstance(rc, dict) else None
    rows = []
    for k, v in sorted(cat.items(), key=lambda kv: -kv[1]):
        m = mins.get(k) if isinstance(mins, dict) else None
        rows.append([k, v, pct(v / total), (str(m.get("required")) + (" (неприменимо)" if m.get("na") else "")) if isinstance(m, dict) else "—"])
    lines += [table(["категория", "число", "доля", "минимум"], rows), "",
              table(["горизонт", "число"], [[k, v] for k, v in sorted(hor.items())]), ""]
    if isinstance(rc, dict):
        lines.append("Проверка реестра (`data/registry-check.json`, %s): ошибок %d, предупреждений %d." %
                     (rc.get("date", "?"), len(rc.get("errors") or []), len(rc.get("warnings") or [])))
        if rc.get("categories_na"):
            lines.append("Категории, неприменимые к продукту: %s." % ", ".join(rc["categories_na"]))
        lines.append("")
    return lines


def sec_profile(out, cfg):
    st = (cfg.get("strategy") or {}) if isinstance(cfg, dict) else {}
    lines = ["## 6. Профиль и параметры прогона", ""]
    if not st:
        return lines + [NO_DATA + " (нет build/run-config.json).", ""]
    profile = st.get("profile") or "standard"
    rows = [["профиль", profile + ("" if st.get("profile") else " (поле не задано, значение по умолчанию)")],
            ["вид стратегии", st.get("kind", "—")], ["глубина", st.get("depth", "—")],
            ["горизонт", "%s мес. + видение %s лет" % (st.get("horizon_months", "—"), st.get("vision_years", "—"))],
            ["рынки", ", ".join(st.get("markets") or []) or "—"], ["минимум предложений", st.get("proposals_min", "—")],
            ["бюджетные варианты", ", ".join((st.get("budget") or {}).get("variants") or []) or "—"]]
    if st.get("constraints"):
        rows.append(["ограничения", st["constraints"]])
    lines += [table(["параметр", "значение"], rows), ""]
    if profile == "zero-budget-solo":
        lines += ["Профиль «нулевой бюджет, один разработчик»: вместо CAC — метрики усилий (часы на одного активированного пользователя), "
                  "ёмкость разработчика в днях в месяц как ограничение плана.", ""]
    assumptions = cfg.get("assumptions") or []
    if assumptions:
        lines += ["Допущения прогона (`run-config.assumptions`):", ""] + ["- %s" % a for a in assumptions] + [""]
    return lines


def sec_typesafe(out):
    t = load_json(out / "data" / "typesafe-jev.json", None)
    lines = ["## 7. TypeSafe (Jev)", ""]
    if not isinstance(t, dict):
        return lines + [NO_DATA + ": data/typesafe-jev.json отсутствует (оценка не выполнялась или выключена: `tools.typesafe`).", ""]
    items = t.get("items") or {}
    if t.get("skipped"):
        return lines + ["Оценка пропущена: %s." % t["skipped"], ""]
    lines.append("Модель: `%s`, дата %s, оценено предложений: **%d**. Вопросов: %d." % (t.get("model", "?"), t.get("date", "?"), len(items), len(t.get("questions") or [])))
    lines.append("Показатели TypeSafe — второе мнение, отдельной колонкой; в composite, ранги и приоритеты они не входят.")
    qs = t.get("questions") or []
    if qs:
        lines += ["", table(["ключ", "вид"], [[q.get("key"), q.get("kind")] for q in qs]), ""]
    cors = t.get("correlations")
    src = "по файлу typesafe-jev.json"
    if not isinstance(cors, dict):
        cors, src = {}, "посчитано build_methodology.py по data/scores.json и data/typesafe-jev.json"
        sc = load_json(out / "data" / "scores.json", None)
        if isinstance(sc, list):
            comp = {s.get("id"): s.get("composite") for s in sc if isinstance(s, dict)}
            for key in ("p_success", "p_user_value", "risk", "impact", "effort"):
                pairs = [(comp[i], v[key]) for i, v in items.items() if i in comp and isinstance(v, dict) and isinstance(v.get(key), (int, float)) and isinstance(comp[i], (int, float))]
                r = spearman([a for a, _ in pairs], [b for _, b in pairs]) if pairs else None
                if r is not None:
                    cors["composite~" + key] = round(r, 3)
    if cors:
        lines += ["Ранговая корреляция Спирмена composite с показателями TypeSafe (%s):" % src, "",
                  table(["пара", "ρ"], [[k, v] for k, v in cors.items()]), ""]
    else:
        lines += ["Корреляции с composite: нет данных (нет data/scores.json или мало оценок).", ""]
    return lines


def sec_model(out):
    m = load_json(out / "data" / "model.json", None)
    lines = ["## 8. Модель юнит-экономики", ""]
    if not isinstance(m, dict):
        return lines + [NO_DATA + " (нет data/model.json).", ""]
    sc = m.get("scenarios") or {}
    lines.append("Файл `data/model.json`: валюта %s, модель выручки %s, горизонт %s мес., сценарии: %s. Параметры — `build/model-params.json`; "
                 "каждый вход — допущение с меткой." % (m.get("currency", "—"), m.get("revenue_model", "—"), m.get("horizon_months", "—"), ", ".join(sc) or "—"))
    lines.append("")
    return lines


def sec_limits(out, cfg):
    lines = ["## 9. Ограничения (из данных прогона)", ""]
    items = []
    kw = load_json(out / "data" / "keywords.json", None)
    if isinstance(kw, list) and kw:
        nul = sum(1 for k in kw if isinstance(k, dict) and k.get("volume") is None)
        if nul:
            items.append("объёмы запросов не получены у %d из %d запросов (`volume: null`)" % (nul, len(kw)))
    sc = (cfg.get("scope") or {}) if isinstance(cfg, dict) else {}
    concept = isinstance(cfg, dict) and cfg.get("mode") == "concept"
    if concept:     # режим идеи: репозитория, приложения и Issues нет по устройству режима, а не по выбору владельца
        items.append("режим идеи: продукта ещё нет — анализ кода, запуск приложения и Issues не проводились; цифры спроса и конверсий "
                     "почти всегда `[допущение]`, доказательства — внешние (аналоги, сообщества, документация платформ)")
        ts = load_json(out / "data" / "typesafe-concept.json", None)
        if isinstance(ts, dict) and ts.get("verdict"):
            items.append("предпроверка жизнеспособности: светофор %s (источник %s, уверенность %s) — ориентир, не прогноз"
                         % (ts["verdict"], ts.get("source"), ts.get("confidence")))
    off = [n for n in ("communities", "legal", "issues", "app_run", "competitors", "keywords", "events")
           if sc.get(n) is False and not (concept and n in ("issues", "app_run"))]
    if off:
        items.append("направления выключены владельцем (`scope`): %s — соответствующие входы стратегии отсутствуют" % ", ".join(off))
    props = load_json(out / "data" / "proposals.json", None)
    if isinstance(props, list) and props:
        d = sum(1 for p in props if p.get("evidence_class") == "D")
        if d:
            items.append("предложений класса D (логический вывод): %d из %d" % (d, len(props)))
    items.append("<заполнить: ограничения, которые видит автор (источники данных, слепые зоны, спорные допущения)>")
    return lines + ["%d. %s" % (i, t) for i, t in enumerate(items, 1)] + [""]


def build(out):
    cfg = load_json(out / "build" / "run-config.json", {}) or {}
    name = ((cfg.get("product") or {}).get("name") or "").strip() if isinstance(cfg, dict) else ""
    lines = [MARKER, "# Методология оценки" + (": %s" % name if name else ""), "",
             "Документ собран `build_methodology.py` %s из файлов прогона; числа — факты из `data/*.json`, метка «<заполнить>» — место для автора." % date.today().isoformat(), ""]
    for part in (sec_scales(None), sec_formulas(), sec_weights(out), sec_sensitivity(out), sec_evidence(out), sec_profile(out, cfg),
                 sec_typesafe(out), sec_model(out), sec_limits(out, cfg)):
        lines += part
    lines += ["---", "Источники: data/weights.json, data/sensitivity.json, data/proposals.json, data/registry-check.json, data/scores.json, "
              "data/typesafe-jev.json, data/model.json, build/run-config.json."]
    return "\n".join(lines).rstrip() + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0], formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out", help="папка прогона <OUT>")
    ap.add_argument("--force", action="store_true", help="перезаписать research/methodology.md, даже если он написан вручную")
    ap.add_argument("--stdout", action="store_true", help="напечатать текст, файл не писать")
    ap.add_argument("--json", action="store_true", help="печатать краткий отчёт JSON")
    a = ap.parse_args(argv)
    out = Path(a.out).resolve()
    if not (out / "data").is_dir():
        print("ошибка: нет папки %s/data" % out, file=sys.stderr)
        return 2
    text = build(out)
    if a.stdout:
        sys.stdout.write(text)
        return 0
    target = out / "research" / "methodology.md"
    protected = False
    if target.exists() and not a.force and MARKER not in target.read_text(encoding="utf-8"):
        target = out / "research" / "methodology.generated.md"
        protected = True
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    nodata = text.count(NO_DATA)
    rep = {"ok": not protected, "file": target.relative_to(out).as_posix(), "protected": protected, "no_data_sections": nodata, "placeholders": text.count("<заполнить")}
    if a.json:
        print(json.dumps(rep, ensure_ascii=False, indent=2))
    else:
        print("записано %s (разделов «нет данных»: %d, мест «<заполнить>»: %d)" % (target, nodata, rep["placeholders"]))
        if protected:
            print("предупреждение: research/methodology.md написан вручную и не перезаписан; сравните и перенесите нужное или запустите с --force", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
