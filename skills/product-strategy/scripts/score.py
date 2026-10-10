#!/usr/bin/env python3
"""Оценка реестра предложений: индексы, составные показатели, приоритеты, метки, чувствительность к весам.

  score.py <OUT> [--weights FILE] [--reset-weights]

Вход:  <OUT>/data/proposals.json (схема — references/data-contract.md);
       необязательно <OUT>/data/typesafe-jev.json (отдельная колонка typesafe, в composite не входит).
Веса:  встроенные по умолчанию; поверх них — <OUT>/data/weights.json, если он уже есть (ручная перенастройка),
       и затем файл --weights (частичный JSON, сливается рекурсивно). --reset-weights игнорирует старый data/weights.json.
Выход: data/scores.json, data/scores.csv, data/weights.json (действующие веса), data/sensitivity.json.

Все формулы — references/scoring.md (держать в синхроне с этим файлом). Только стандартная библиотека.
"""
import argparse
import copy
import csv
import json
import math
import statistics
import sys
from pathlib import Path

VALUE_SUBSCALES = ["reach", "impact", "acquisition", "activation", "conversion", "retention", "revenue",
                   "virality", "seo", "trust", "moat", "fit", "demand", "season"]
RISK_KEYS = ["legal", "ip", "platform", "privacy", "tech", "reputation"]

DEFAULT_WEIGHTS = {
    "version": 1,
    # индекс ценности: взвешенное среднее экспертной value и подшкал (нет подшкалы → берётся value)
    "value": {"value": 2.0, "reach": 1.0, "impact": 1.0, "acquisition": 0.8, "activation": 1.0, "conversion": 1.0,
              "retention": 1.0, "revenue": 1.0, "virality": 0.6, "seo": 0.6, "trust": 0.6, "moat": 0.8, "fit": 0.8,
              "demand": 1.0, "season": 0.4},
    # индекс стоимости: экспертная cost + числовые поля, переведённые в 1–5 по порогам maps
    "cost": {"cost": 2.0, "effort_days": 1.5, "money": 0.8, "time_to_result": 0.8, "dependencies": 0.4},
    # индекс риска: экспертная risk + объект risks (нет ключа → берётся risk)
    "risk": {"risk": 2.0, "legal": 1.2, "ip": 1.0, "platform": 1.0, "privacy": 1.2, "tech": 0.8, "reputation": 1.0},
    # composite: взвешенная сумма нормированных (0–1) показателей, делённая на сумму весов
    "composite": {"rice": 0.30, "ice": 0.20, "wsjf": 0.25, "risk_adjusted": 0.25},
    "evidence_confidence": {"A": 1.0, "B": 0.8, "C": 0.55, "D": 0.35},
    "confidence_mix": {"evidence": 0.6, "testability": 0.25, "agreement": 0.15},
    # охват в условных пользователях/мес по шкале reach 1–5 и множитель влияния RICE (конвенция Intercom)
    "reach_units": {"1": 50, "2": 300, "3": 1250, "4": 6000, "5": 20000},
    "impact_map": {"1": 0.25, "2": 0.5, "3": 1.0, "4": 2.0, "5": 3.0},
    "risk_adjust_max": 0.5,
    # пороги перевода числовых полей в шкалу 1–5: значение ≤ порога k → балл k+1, больше последнего → 5
    "maps": {"effort_days": [2, 5, 15, 40], "money": [0, 500, 5000, 25000],
             "time_to_result": [7, 30, 90, 180], "dependencies": [0, 1, 2, 3]},
    "priority": {"p0_share": 0.15, "p1_until": 0.40, "p2_until": 0.70, "p0_quadrants": ["quick_win", "big_bet"]},
    "labels": {"important_value": 3.6, "effective_quantile": 0.75, "expensive_cost": 3.6, "expensive_money": 10000,
               "risky_risk": 3.0, "fast_days": 14, "slow_days": 90, "strategic_moat": 4,
               "strategic_horizons": ["next", "later", "vision"], "tempting_value": 3.3, "tempting_confidence": 0.55},
    "sensitivity": {"factors": [0.5, 1.5], "groups": ["composite", "value", "cost", "risk"], "top_n": 20},
}

PERTURB_GROUPS = ("composite", "value", "cost", "risk")


# ---------------------------------------------------------------- utils
def load_json(path, default=None):
    """Читает JSON; нет файла → default."""
    p = Path(path)
    if not p.exists():
        return default
    return json.loads(p.read_text(encoding="utf-8"))


def deep_merge(base, extra):
    """Рекурсивно накладывает extra на base (словари сливаются, остальное заменяется)."""
    out = copy.deepcopy(base)
    for k, v in (extra or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def num(x, default):
    """Число или default (bool и строки не считаются числом)."""
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        return default
    if isinstance(x, float) and math.isnan(x):
        return default
    return x


def clamp(x, lo=1.0, hi=5.0):
    return max(lo, min(hi, x))


def to_scale(x, thresholds):
    """Значение → балл 1–5 по возрастающим порогам: x ≤ t[k] → k+1; больше всех порогов → len(t)+1 (≤5)."""
    for k, t in enumerate(thresholds):
        if x <= t:
            return float(k + 1)
    return float(min(5, len(thresholds) + 1))


def half_up(x):
    """Округление до целого «половина вверх» (а не банковское, как round)."""
    return int(math.floor(x + 0.5))


def wmean(vals, weights):
    """Взвешенное среднее по ключам weights; нулевая сумма весов → среднее значений."""
    den = sum(weights.values())
    if den <= 0:
        return statistics.mean(vals.values())
    return sum(vals[k] * w for k, w in weights.items()) / den


def minmax(xs):
    """Минимакс-нормировка в 0–1; все равны → 0."""
    if not xs:
        return []
    lo, hi = min(xs), max(xs)
    return [0.0 if hi == lo else (x - lo) / (hi - lo) for x in xs]


# ---------------------------------------------------------------- metrics
def base_metrics(p, W):
    """Индексы и составные показатели одного предложения (без нормировки по реестру)."""
    s = p.get("scores") or {}
    value = clamp(num(s.get("value"), 3))
    cost = clamp(num(s.get("cost"), 3))
    risk = clamp(num(s.get("risk"), 3))
    conf_expert = clamp(num(s.get("confidence"), 3))
    # подшкалы ценности: известные + любые свои ключи из весов; нет значения → value
    sub = {k: clamp(num(s.get(k), value)) for k in set(VALUE_SUBSCALES) | set(W["value"]) if k != "value"}
    vvals = dict(sub, value=value)
    value_index = wmean({k: vvals[k] for k in W["value"]}, W["value"])

    ed = p.get("effort_days")
    if isinstance(ed, list) and len(ed) == 2 and all(num(x, None) is not None for x in ed):
        effort_mid = (ed[0] + ed[1]) / 2.0
        effort_score = to_scale(effort_mid, W["maps"]["effort_days"])
    else:
        effort_mid = None
        effort_score = cost
    money = num((p.get("cost_money") or {}).get("max"), None) if isinstance(p.get("cost_money"), dict) else None
    money_score = to_scale(money, W["maps"]["money"]) if money is not None else cost
    ttfr = num(p.get("time_to_first_result_days"), None)
    time_score = to_scale(ttfr, W["maps"]["time_to_result"]) if ttfr is not None else cost
    deps = p.get("dependencies") if isinstance(p.get("dependencies"), list) else []
    deps_score = to_scale(len(deps), W["maps"]["dependencies"])
    cvals = {"cost": cost, "effort_days": effort_score, "money": money_score, "time_to_result": time_score,
             "dependencies": deps_score}
    cost_index = wmean({k: cvals.get(k, cost) for k in W["cost"]}, W["cost"])

    risks = p.get("risks") if isinstance(p.get("risks"), dict) else {}
    rvals = {k: clamp(num(risks.get(k), risk)) for k in set(RISK_KEYS) | set(W["risk"]) if k != "risk"}
    rvals["risk"] = risk
    risk_index = wmean({k: rvals[k] for k in W["risk"]}, W["risk"])

    ev = W["evidence_confidence"].get(p.get("evidence_class"), min(W["evidence_confidence"].values()))
    testability = clamp(num(s.get("testability"), conf_expert))
    spread = clamp(num(s.get("spread"), 3))
    mix = W["confidence_mix"]
    confidence = mix["evidence"] * ev + mix["testability"] * testability / 5.0 + mix["agreement"] * (6 - spread) / 5.0

    reach_units = W["reach_units"][str(half_up(sub["reach"]))]
    impact_mult = W["impact_map"][str(half_up(sub["impact"]))]
    effort_for_rice = max(effort_mid if effort_mid is not None else 5.0 * cost, 0.5)
    rice = reach_units * impact_mult * confidence / effort_for_rice
    ice = value_index * (confidence * 5.0) * (6.0 - cost_index)
    bv = value_index
    tc = (sub["season"] + (6.0 - time_score)) / 2.0
    rr = (sub["moat"] + sub["trust"]) / 2.0
    cost_of_delay = bv + tc + rr
    wsjf = cost_of_delay / cost_index
    value_per_effort = value_index / cost_index
    risk_adjusted = value_index * (1.0 - W["risk_adjust_max"] * (risk_index - 1.0) / 4.0)
    return {
        "value_index": value_index, "cost_index": cost_index, "risk_index": risk_index,
        "confidence_calc": confidence, "effort_days_mid": effort_mid if effort_mid is not None else effort_for_rice,
        "reach_units": reach_units, "rice": rice, "ice": ice, "cost_of_delay": cost_of_delay, "wsjf": wsjf,
        "value_per_effort": value_per_effort, "risk_adjusted": risk_adjusted,
        "_sub": sub, "_time_days": ttfr, "_money": money,
    }


def norm_key(key, xs):
    """Нормировка показателя composite: RICE — по log(1+x) (тяжёлый хвост), прочие — минимакс."""
    if key == "rice":
        xs = [math.log1p(max(x, 0.0)) for x in xs]
    return minmax(xs)


def rank_rows(props, W):
    """Метрики + composite + ранг. Возвращает список строк, отсортированный по рангу."""
    rows = []
    for p in props:
        m = base_metrics(p, W)
        m["id"] = p.get("id")
        rows.append(m)
    comp_w = W["composite"]
    den = sum(comp_w.values()) or 1.0
    normed = {k: norm_key(k, [r[k] for r in rows]) for k in comp_w}
    for i, r in enumerate(rows):
        for k in comp_w:
            r["n_" + k] = normed[k][i]
        r["composite"] = sum(comp_w[k] * normed[k][i] for k in comp_w) / den
    rows.sort(key=lambda r: (-round(r["composite"], 9), str(r["id"])))
    for i, r in enumerate(rows, 1):
        r["rank"] = i
    return rows


def classify(rows, props_by_id, W):
    """Квадранты, приоритеты P0–P3, MoSCoW, метки."""
    n = len(rows)
    if not n:
        return rows
    med_v = statistics.median(r["value_index"] for r in rows)
    med_c = statistics.median(r["cost_index"] for r in rows)
    for r in rows:
        hi_v, lo_c = r["value_index"] >= med_v, r["cost_index"] <= med_c
        r["quadrant"] = ("quick_win" if lo_c else "big_bet") if hi_v else ("filler" if lo_c else "money_pit")
    pr = W["priority"]
    k0 = max(1, half_up(n * pr["p0_share"]))
    p0 = [r["id"] for r in rows if r["quadrant"] in pr["p0_quadrants"]][:k0]
    p0 = set(p0)
    for r in rows:
        q = r["rank"] / n
        if r["id"] in p0:
            r["priority"] = "P0"
        elif q <= pr["p1_until"]:
            r["priority"] = "P1"
        elif q <= pr["p2_until"]:
            r["priority"] = "P2"
        else:
            r["priority"] = "P3"
        r["moscow"] = {"P0": "must", "P1": "should", "P2": "could", "P3": "wont"}[r["priority"]]
    L = W["labels"]
    vpe = sorted(r["value_per_effort"] for r in rows)
    vpe_q = vpe[min(n - 1, int(n * L["effective_quantile"]))]
    for r in rows:
        p = props_by_id.get(r["id"], {})
        sub = r["_sub"]
        days = r["_time_days"]
        cost_raw = clamp(num((p.get("scores") or {}).get("cost"), 3))
        labels = []
        if r["value_index"] >= L["important_value"]:
            labels.append("important")
        if r["value_per_effort"] >= vpe_q:
            labels.append("effective")
        if r["cost_index"] >= L["expensive_cost"] or (r["_money"] is not None and r["_money"] >= L["expensive_money"]):
            labels.append("expensive")
        if r["risk_index"] >= L["risky_risk"]:
            labels.append("risky")
        if (days <= L["fast_days"]) if days is not None else cost_raw <= 2:
            labels.append("fast")
        if (days >= L["slow_days"]) if days is not None else cost_raw >= 4:
            labels.append("slow")
        if sub["moat"] >= L["strategic_moat"] and p.get("horizon") in L["strategic_horizons"]:
            labels.append("strategic")
        if r["value_index"] >= L["tempting_value"] and (r["confidence_calc"] < L["tempting_confidence"]
                                                         or p.get("evidence_class") == "D"):
            labels.append("tempting_weak")
        r["labels"] = labels
    return rows


# ---------------------------------------------------------------- sensitivity
def sensitivity(props, W, base_rows):
    """±50 % (factors) каждого веса из групп composite/value/cost/risk: сдвиг рангов и устойчивость топ-N."""
    S = W["sensitivity"]
    top_n = min(S["top_n"], len(base_rows))
    base_rank = {r["id"]: r["rank"] for r in base_rows}
    base_top = {r["id"] for r in base_rows[:top_n]}
    always = set(base_top)
    tornado, runs = [], 0
    for group in S["groups"]:
        if group not in PERTURB_GROUPS:
            continue
        for key in W[group]:
            entry = {"param": "%s.%s" % (group, key)}
            for tag, f in zip(("low", "high"), S["factors"]):
                w2 = copy.deepcopy(W)
                w2[group][key] = W[group][key] * f
                rows = rank_rows(props, w2)
                runs += 1
                shift = statistics.mean(abs(r["rank"] - base_rank[r["id"]]) for r in rows) if rows else 0.0
                top = {r["id"] for r in rows[:top_n]}
                always &= top
                entry["%s_rank_shift" % tag] = round(shift, 3)
                entry["%s_top_overlap" % tag] = len(top & base_top)
            entry["swing"] = round(abs(entry["high_rank_shift"]) + abs(entry["low_rank_shift"]), 3)
            tornado.append(entry)
    tornado.sort(key=lambda e: (-e["swing"], e["param"]))
    return {"tornado": tornado, "top20_stability": round(len(always) / top_n, 3) if top_n else 1.0, "runs": runs,
            "top_n": top_n, "factors": S["factors"], "top20_base": sorted(base_top), "always_top20": sorted(always)}


# ---------------------------------------------------------------- io
ROUND = {"value_index": 4, "cost_index": 4, "risk_index": 4, "confidence_calc": 4, "effort_days_mid": 2, "rice": 3,
         "ice": 3, "cost_of_delay": 4, "wsjf": 4, "value_per_effort": 4, "risk_adjusted": 4, "composite": 6}


def ts_item(item):
    """Оценка TypeSafe для колонки typesafe: нет оценки или ошибка запроса → None."""
    return item if isinstance(item, dict) and item and "error" not in item else None


def build_output(rows, props_by_id, W, jev):
    """Строки scores.json в порядке ранга (неокруглённые значения → округлённые для файла)."""
    out = []
    items = (jev or {}).get("items") or {}
    for r in rows:
        p = props_by_id.get(r["id"], {})
        o = {"id": r["id"], "rank": r["rank"], "title": p.get("title", ""), "category": p.get("category"),
             "evidence_class": p.get("evidence_class"), "horizon": p.get("horizon"), "kano": p.get("kano")}
        for k, nd in ROUND.items():
            o[k] = round(r[k], nd)
        for k in W["composite"]:
            o["n_" + k] = round(r["n_" + k], 4)
        o.update({"quadrant": r["quadrant"], "priority": r["priority"], "moscow": r["moscow"], "labels": r["labels"],
                  "typesafe": ts_item(items.get(r["id"]))})
        out.append(o)
    return out


def write_csv(path, rows):
    """CSV для XLSX/табличного просмотра; списки → «; », typesafe → плоские колонки ts_*."""
    ts_keys = []
    for r in rows:
        for k, v in (r.get("typesafe") or {}).items():
            if isinstance(v, (int, float, str)) and ("ts_" + k) not in ts_keys:
                ts_keys.append("ts_" + k)
    base = [k for k in (rows[0].keys() if rows else ["id", "rank"]) if k != "typesafe"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(base + ts_keys)
        for r in rows:
            line = ["; ".join(map(str, r[k])) if isinstance(r.get(k), list) else r.get(k) for k in base]
            ts = r.get("typesafe") or {}
            line += [ts.get(k[3:]) if isinstance(ts.get(k[3:]), (int, float, str)) else "" for k in ts_keys]
            w.writerow(line)


def effective_weights(out_dir, weights_file=None, reset=False):
    """Встроенные веса ← data/weights.json (если есть и не reset) ← --weights."""
    W = copy.deepcopy(DEFAULT_WEIGHTS)
    existing = out_dir / "data" / "weights.json"
    if existing.exists() and not reset:
        W = deep_merge(W, load_json(existing, {}))
    if weights_file:
        W = deep_merge(W, load_json(weights_file, {}))
    return W


def main(argv=None):
    ap = argparse.ArgumentParser(description="Оценка реестра: индексы, RICE/ICE/WSJF, composite, P0–P3, чувствительность.")
    ap.add_argument("out", help="папка прогона <OUT>")
    ap.add_argument("--weights", help="JSON с весами (частичный; сливается с действующими)")
    ap.add_argument("--reset-weights", action="store_true", help="не читать прежний data/weights.json")
    a = ap.parse_args(argv)
    out_dir = Path(a.out).resolve()
    props = load_json(out_dir / "data" / "proposals.json")
    if props is None:
        print("нет %s" % (out_dir / "data" / "proposals.json"), file=sys.stderr)
        return 1
    W = effective_weights(out_dir, a.weights, a.reset_weights)
    props = [p for p in props if isinstance(p, dict) and p.get("id")]
    by_id = {p["id"]: p for p in props}
    rows = classify(rank_rows(props, W), by_id, W)
    sens = sensitivity(props, W, rows)
    jev = load_json(out_dir / "data" / "typesafe-jev.json")
    out = build_output(rows, by_id, W, jev)
    data = out_dir / "data"
    data.mkdir(parents=True, exist_ok=True)
    (data / "scores.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(data / "scores.csv", out)
    (data / "weights.json").write_text(json.dumps(W, ensure_ascii=False, indent=2), encoding="utf-8")
    (data / "sensitivity.json").write_text(json.dumps(sens, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Оценено предложений: %d; устойчивость топ-%d: %.0f %%; прогонов чувствительности: %d"
          % (len(out), sens["top_n"], sens["top20_stability"] * 100, sens["runs"]))
    for r in out[:10]:
        print("%3d %s %.3f %s %-9s %s" % (r["rank"], r["id"], r["composite"], r["priority"], r["quadrant"], r["title"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
