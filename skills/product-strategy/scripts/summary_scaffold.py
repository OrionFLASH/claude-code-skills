#!/usr/bin/env python3
"""Черновик раздела 1 «Резюме» из данных прогона (FB-047): все числа и даты — плейсхолдеры или значения базовой линии.

  summary_scaffold.py <OUT> [--to-part] [--force] [--stdout]

Источники: data/idea.json и data/typesafe-concept.json (идея, светофор), data/premises.json и run-config idea.pitch_v2 /
idea.history (пересмотр идеи), data/plan-baseline.json (сроки, ёмкость, MVP — {plan:…}), data/decisions.json (ставки,
критерии отказа, pre-mortem, North Star, анти-цели, развилки — {bet:…}, {north_star}, {anti_goals}, {fork:…}),
data/scores.json (топ-10 — {rank:P…}), data/model.json (сценарии — {model:…}; в режиме sensitivity-only сборка сама
добавит метку «[иллюстрация при допущениях]»), charts/charts-index.json (вставки).
Текст — каркас для оркестратора или агента резюме (бриф strategy-summary.md, если есть): связки пишет человек, но ни одно
число и ни одна дата не набираются руками — проверка согласованности (plan_baseline.py --check) проходит без расхождений.

Выход: build/summary-draft.md (по умолчанию; не в build/parts/ — сборщик взял бы его как часть и раздел 1 задвоился бы;
его читает бриф strategy-summary.md); --to-part — build/parts/strategy-01.md (если части нет или --force);
--stdout — только напечатать. Код выхода 0; 2 — нет папки <OUT>/data.
Только стандартная библиотека.
"""
import argparse
import json
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

FILL = "<заполнить>"
VERDICT = {"green": "go", "yellow": "go с оговорками", "red": "стоп или пересмотр идеи"}


def load_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def build(out):
    out = Path(out)
    cfg = load_json(out / "build" / "run-config.json", {}) or {}
    idea = load_json(out / "data" / "idea.json", {}) or {}
    ts = load_json(out / "data" / "typesafe-concept.json", {}) or {}
    plan = load_json(out / "data" / "plan-baseline.json", None)
    dec = load_json(out / "data" / "decisions.json", None)
    scores = load_json(out / "data" / "scores.json", None)
    model = load_json(out / "data" / "model.json", None)
    prem = load_json(out / "data" / "premises.json", None)
    charts = {c.get("key") for c in (load_json(out / "charts" / "charts-index.json", []) or []) if isinstance(c, dict)}
    ic = cfg.get("idea") or {}
    st = cfg.get("strategy") or {}
    personal = str((cfg.get("project") or {}).get("audience") or "") in ("personal", "circle", "personal_then_public")
    L = ["## 1. Резюме", "",
         "<!-- generated-by: summary_scaffold.py %s — числа и даты только плейсхолдерами; связки допишите -->" % date.today().isoformat(), ""]
    pitch = ic.get("pitch_v2") or ic.get("pitch") or idea.get("pitch")
    L.append("**Идея и для кого.** %s%s [факт: ответ владельца]." % (
        pitch or FILL, ("; " + (idea.get("segment_label") or "")) if idea.get("segment_label") else ""))
    hist = ic.get("history") or []
    items = prem.get("premises") if isinstance(prem, dict) else prem
    refuted = [x for x in items or [] if isinstance(x, dict) and str(x.get("status") or "").lower() in ("refuted", "опровергнута", "rejected")]
    if ic.get("pitch_v2") or hist or refuted:
        L.append("")
        L.append("**Пересмотр идеи.** Версия идеи %s; исходная формулировка — «%s»; опровергнуто предпосылок: %d%s [факт: data/premises.json]." % (
            ic.get("version") or (len(hist) + 1), (hist[0].get("pitch") if hist and isinstance(hist[0], dict) else ic.get("pitch")) or "—",
            len(refuted), (" (" + "; ".join(str(x.get("text") or x.get("premise") or "")[:80] for x in refuted[:3]) + ")") if refuted else ""))
    L.append("")
    v = ts.get("verdict")
    L.append("**Вердикт: %s.** Предпроверка жизнеспособности — светофор %s (viability %s, риск %s) [оценка: typesafe_concept.py]; "
             "чего не знаем: %s." % (VERDICT.get(v, FILL), v or "—", ts.get("viability", "—"), ts.get("risk", "—"),
                                    ", ".join(ts.get("check_first") or []) or FILL))
    L.append("")
    if plan:
        L.append("**Цель горизонта.** %s к {plan:horizon_end}; North Star — {north_star}%s [допущение]." % (
            "{plan:goal}" if plan.get("goal") else FILL, ", цель {north_star.target}" if (dec or {}).get("north_star", {}).get("target") else ""))
        L.append("")
        L.append("**План.** Старт {plan:start}; %s%s; горизонт до {plan:horizon_end}. Ёмкость: {plan:capacity}. Состав MVP по Ганту: "
                 "{plan:mvp_ids} [факт: data/plan-baseline.json]." % (
                     "закрытая бета {plan:beta}" if (plan.get("milestones") or {}).get("beta") else "бета — не запланирована",
                     ", запуск {plan:launch}" if (plan.get("milestones") or {}).get("launch") else ""))
    else:
        L.append("**План.** %s (нет data/plan-baseline.json — запустите plan_baseline.py <OUT>); ёмкость: {capacity}." % FILL)
    L.append("")
    if dec:
        L.append("**Три ставки.**")
        L.append("")
        for b in dec.get("bets") or []:
            i = b.get("id")
            kd = "{plan:kill.%s.date}" % i if plan and any(k.get("bet") == i for k in plan.get("kill") or []) else "{bet:%s.kill.date}" % i
            L.append("%s. **{bet:%s.name}** ({bet:%s.pids}): {bet:%s.what}. Критерий отказа: {bet:%s.kill} (дата %s). Pre-mortem: "
                     "{bet:%s.premortem}." % (i, i, i, i, i, kd, i) if b.get("what") and b.get("premortem") else
                     "%s. **{bet:%s.name}** ({bet:%s.pids}). Критерий отказа: {bet:%s.kill}." % (i, i, i, i))
        L.append("")
        if dec.get("anti_goals"):
            L += ["**Что сознательно не делаем:** {anti_goals}.", ""]
        if dec.get("forks"):
            L += ["**Развилки владельца:** " + "; ".join("{fork:%s} — по умолчанию {fork:%s.default}" % (f["id"], f["id"]) if f.get("default")
                                                        else "{fork:%s}" % f["id"] for f in dec["forks"] if isinstance(f, dict) and f.get("id")) + ".", ""]
        if dec.get("draft"):
            L += ["> Решения — черновик (`data/decisions.json → draft`): подтвердите их до сборки резюме.", ""]
    else:
        L += ["**Три ставки.** %s (нет data/decisions.json — `decisions.py <OUT> --init --draft`)." % FILL, ""]
    if isinstance(scores, list) and scores:
        top = sorted((x for x in scores if isinstance(x, dict) and x.get("rank")), key=lambda x: x["rank"])[:10]
        L.append("**Топ-10 предложений** (ранг с учётом зависимостей): " + ", ".join(
            "%s «%s» ({deprank:%s})" % (x["id"], str(x.get("title") or "")[:50], x["id"]) for x in top) + ".")
        L.append("")
    if isinstance(model, dict) and model.get("scenarios"):
        if model.get("model_profile") == "personal" or personal:
            L.append("**Стоимость владения.** Обычный сценарий: ценность {model:base.value|money} против затрат {model:base.cost|money}, "
                     "окупаемость личных усилий — месяц {model:base.breakeven_month}; чтобы окупиться, нужно экономить "
                     "{model:base.hours_saved_per_week_to_break_even|1} ч в неделю [оценка: model.py].")
        else:
            L.append("**Деньги (три сценария).** Чистая выручка за {model:horizon_months} мес.: {model:pess.net_revenue|money} / "
                     "{model:base.net_revenue|money} / {model:opt.net_revenue|money} [оценка: model.py]%s." % (
                         "; режим sensitivity-only — сборка пометит числа как иллюстрацию" if model.get("mode") == "sensitivity-only" else ""))
        L.append("")
    ins = [k for k in ("effort-impact", "critical-path", "forecast-fan") if k in charts]
    if ins:
        L += ["![[chart:%s]]" % ins[0], ""]
        if "forecast-fan" in ins[1:]:
            L += ["![[chart:forecast-fan]]", ""]
    L.append("**Первые 30 дней:** %s [допущение]." % ("проверки до разработки по ставкам {bet:1.name}, {bet:2.name}" if dec else FILL))
    return "\n".join(L).rstrip() + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0], formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out", help="папка прогона <OUT>")
    ap.add_argument("--to-part", action="store_true", help="записать build/parts/strategy-01.md")
    ap.add_argument("--force", action="store_true", help="перезаписать существующую часть")
    ap.add_argument("--stdout", action="store_true", help="только напечатать")
    a = ap.parse_args(argv)
    out = Path(a.out).resolve()
    if not (out / "data").is_dir():
        print("ошибка: нет папки %s/data" % out, file=sys.stderr)
        return 2
    text = build(out)
    if a.stdout:
        sys.stdout.write(text)
        return 0
    target = out / "build" / ("parts/strategy-01.md" if a.to_part else "summary-draft.md")
    if a.to_part and target.exists() and not a.force:
        target = out / "build" / "summary-draft.md"
        print("build/parts/strategy-01.md уже есть — черновик записан в build/summary-draft.md (--force перезапишет часть)", file=sys.stderr)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    print("записано %s (мест «%s»: %d)" % (target, FILL, text.count(FILL)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
