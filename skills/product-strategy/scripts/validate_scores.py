#!/usr/bin/env python3
"""Независимая проверка оценок: пересчитывает всё с нуля по data/proposals.json и data/weights.json
(свой код, без импорта score.py) и сверяет с data/scores.json.

  validate_scores.py <OUT> [--quiet]

Сверяются индексы, уверенность, RICE/ICE/WSJF, value_per_effort, risk_adjusted, composite (с допуском на округление),
ранги (сортировка по round(composite, 9), затем id; перестановка внутри ничьей с разницей ≤ 1e-6 допускается),
квадранты, приоритеты, MoSCoW и метки; поля зависимостей (blocked_by, unlocks, dep_rank, dep_bonus, critical_path) и
порядок критического пути data/critical-path.json — с учётом data/gap-audit-deps.json и разрыва циклов. Если в
scores.json нет полей зависимостей (файл до 1.1), они не сверяются (сообщение). Код выхода 0 — совпадает, 1 — есть
расхождения или нет файлов. Только стандартная библиотека.
"""
import argparse
import json
import math
import sys
from collections import deque
from pathlib import Path

TIE_EPS = 1e-6
DEP_DEFAULTS = {"unlock_bonus": 0.10, "decay": 0.5, "bonus_cap": 0.15, "critical_top_n": 20, "warn_top": 20, "warn_below": 60}
TOL = {"value_index": 1e-3, "cost_index": 1e-3, "risk_index": 1e-3, "confidence_calc": 1e-3, "rice": 2e-3,
       "ice": 2e-3, "wsjf": 1e-3, "value_per_effort": 1e-3, "risk_adjusted": 1e-3, "composite": 2e-6}
KNOWN_VALUE = ("reach", "impact", "acquisition", "activation", "conversion", "retention", "revenue", "virality",
               "seo", "trust", "moat", "fit", "demand", "season")
KNOWN_RISK = ("legal", "ip", "platform", "privacy", "tech", "reputation")


def is_num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and x == x


def bound(x):
    return 1.0 if x < 1 else 5.0 if x > 5 else float(x)


def score_or(d, key, fallback):
    v = d.get(key) if isinstance(d, dict) else None
    return bound(v) if is_num(v) else fallback


def bucket(x, cuts):
    """Порог → балл: первый порог, который не меньше x, даёт номер (с 1); иначе 5 (или число порогов + 1)."""
    k = 1
    for c in cuts:
        if x <= c:
            return float(k)
        k += 1
    return float(min(k, 5))


def weighted(values, weights):
    tot = 0.0
    acc = 0.0
    for name in weights:
        acc += values[name] * weights[name]
        tot += weights[name]
    if tot <= 0:
        return sum(values.values()) / len(values)
    return acc / tot


def recompute_one(p, W):
    sc = p.get("scores") if isinstance(p.get("scores"), dict) else {}
    v0 = score_or(sc, "value", 3.0)
    c0 = score_or(sc, "cost", 3.0)
    r0 = score_or(sc, "risk", 3.0)
    conf0 = score_or(sc, "confidence", 3.0)
    vals = {"value": v0}
    for k in list(KNOWN_VALUE) + [k for k in W["value"] if k not in KNOWN_VALUE]:
        if k != "value":
            vals[k] = score_or(sc, k, v0)
    vi = weighted({k: vals[k] for k in W["value"]}, W["value"])

    maps = W["maps"]
    ed = p.get("effort_days")
    have_ed = isinstance(ed, list) and len(ed) == 2 and is_num(ed[0]) and is_num(ed[1])
    mid = (ed[0] + ed[1]) * 0.5 if have_ed else None
    cm = p.get("cost_money")
    money = cm.get("max") if isinstance(cm, dict) and is_num(cm.get("max")) else None
    days = p.get("time_to_first_result_days") if is_num(p.get("time_to_first_result_days")) else None
    deps = p.get("dependencies") if isinstance(p.get("dependencies"), list) else []
    cparts = {"cost": c0,
              "effort_days": bucket(mid, maps["effort_days"]) if mid is not None else c0,
              "money": bucket(money, maps["money"]) if money is not None else c0,
              "time_to_result": bucket(days, maps["time_to_result"]) if days is not None else c0,
              "dependencies": bucket(len(deps), maps["dependencies"])}
    ci = weighted({k: cparts.get(k, c0) for k in W["cost"]}, W["cost"])

    rk = p.get("risks") if isinstance(p.get("risks"), dict) else {}
    rparts = {"risk": r0}
    for k in list(KNOWN_RISK) + [k for k in W["risk"] if k not in KNOWN_RISK]:
        if k != "risk":
            rparts[k] = score_or(rk, k, r0)
    ri = weighted({k: rparts[k] for k in W["risk"]}, W["risk"])

    evw = W["evidence_confidence"]
    e = evw[p["evidence_class"]] if p.get("evidence_class") in evw else min(evw.values())
    testab = score_or(sc, "testability", conf0)
    spread = score_or(sc, "spread", 3.0)
    cm_ = W["confidence_mix"]
    conf = cm_["evidence"] * e + cm_["testability"] * (testab / 5.0) + cm_["agreement"] * ((6.0 - spread) / 5.0)

    reach = W["reach_units"][str(int(math.floor(vals["reach"] + 0.5)))]
    imp = W["impact_map"][str(int(math.floor(vals["impact"] + 0.5)))]
    denom = mid if mid is not None else 5.0 * c0
    if denom < 0.5:
        denom = 0.5
    rice = reach * imp * conf / denom
    ice = vi * conf * 5.0 * (6.0 - ci)
    tscore = cparts["time_to_result"]
    wsjf = (vi + (vals["season"] + 6.0 - tscore) / 2.0 + (vals["moat"] + vals["trust"]) / 2.0) / ci
    vpe = vi / ci
    radj = vi * (1.0 - W["risk_adjust_max"] * (ri - 1.0) / 4.0)
    return {"value_index": vi, "cost_index": ci, "risk_index": ri, "confidence_calc": conf, "rice": rice, "ice": ice,
            "wsjf": wsjf, "value_per_effort": vpe, "risk_adjusted": radj,
            "moat": vals["moat"], "days": days, "money": money, "cost_raw": c0}


def recompute(props, W):
    rows = {p["id"]: recompute_one(p, W) for p in props}
    ids = list(rows)
    comp = {i: 0.0 for i in ids}
    wsum = sum(W["composite"].values()) or 1.0
    for key, w in W["composite"].items():
        raw = {i: (math.log1p(max(rows[i][key], 0.0)) if key == "rice" else rows[i][key]) for i in ids}
        if not raw:
            continue
        lo, hi = min(raw.values()), max(raw.values())
        for i in ids:
            comp[i] += w * ((raw[i] - lo) / (hi - lo) if hi > lo else 0.0)
    for i in ids:
        rows[i]["composite"] = comp[i] / wsum
    order = sorted(ids, key=lambda i: (-round(rows[i]["composite"], 9), str(i)))
    for pos, i in enumerate(order, 1):
        rows[i]["rank"] = pos
    return rows, order


def median(xs):
    s = sorted(xs)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2.0


def classify(rows, order, props, W):
    n = len(order)
    if not n:
        return
    mv = median([rows[i]["value_index"] for i in order])
    mc = median([rows[i]["cost_index"] for i in order])
    for i in order:
        r = rows[i]
        if r["value_index"] >= mv:
            r["quadrant"] = "quick_win" if r["cost_index"] <= mc else "big_bet"
        else:
            r["quadrant"] = "filler" if r["cost_index"] <= mc else "money_pit"
    pr = W["priority"]
    quota = max(1, int(math.floor(n * pr["p0_share"] + 0.5)))
    chosen = []
    for i in order:
        if len(chosen) >= quota:
            break
        if rows[i]["quadrant"] in pr["p0_quadrants"]:
            chosen.append(i)
    for i in order:
        share = rows[i]["rank"] / float(n)
        prio = "P0" if i in chosen else "P1" if share <= pr["p1_until"] else "P2" if share <= pr["p2_until"] else "P3"
        rows[i]["priority"] = prio
        rows[i]["moscow"] = dict(P0="must", P1="should", P2="could", P3="wont")[prio]
    L = W["labels"]
    vpes = sorted(rows[i]["value_per_effort"] for i in order)
    cut = vpes[min(n - 1, int(n * L["effective_quantile"]))]
    for i in order:
        r, p = rows[i], props[i]
        lab = []
        if r["value_index"] >= L["important_value"]:
            lab.append("important")
        if r["value_per_effort"] >= cut:
            lab.append("effective")
        if r["cost_index"] >= L["expensive_cost"] or (r["money"] is not None and r["money"] >= L["expensive_money"]):
            lab.append("expensive")
        if r["risk_index"] >= L["risky_risk"]:
            lab.append("risky")
        fast = r["days"] <= L["fast_days"] if r["days"] is not None else r["cost_raw"] <= 2
        slow = r["days"] >= L["slow_days"] if r["days"] is not None else r["cost_raw"] >= 4
        if fast:
            lab.append("fast")
        if slow:
            lab.append("slow")
        if r["moat"] >= L["strategic_moat"] and p.get("horizon") in L["strategic_horizons"]:
            lab.append("strategic")
        if r["value_index"] >= L["tempting_value"] and (r["confidence_calc"] < L["tempting_confidence"] or p.get("evidence_class") == "D"):
            lab.append("tempting_weak")
        r["labels"] = lab


def kosaraju(nodes, edges_out):
    """Компоненты сильной связности (два прохода DFS, итеративно); возвращает словарь узел → номер компоненты."""
    seen, finish = set(), []
    for s0 in nodes:
        if s0 in seen:
            continue
        seen.add(s0)
        st = [(s0, 0)]
        while st:
            v, k = st.pop()
            outs = edges_out.get(v, [])
            if k < len(outs):
                st.append((v, k + 1))
                w = outs[k]
                if w not in seen:
                    seen.add(w)
                    st.append((w, 0))
            else:
                finish.append(v)
    rev = {v: [] for v in nodes}
    for v in nodes:
        for w in edges_out.get(v, []):
            rev[w].append(v)
    comp, cid = {}, 0
    for s0 in reversed(finish):
        if s0 in comp:
            continue
        todo = [s0]
        comp[s0] = cid
        while todo:
            v = todo.pop()
            for w in rev[v]:
                if w not in comp:
                    comp[w] = cid
                    todo.append(w)
        cid += 1
    return comp


def recompute_deps(props_l, rows, order, W, extra):
    """Независимый расчёт полей зависимостей. Возвращает (по id {blocked_by, unlocks, dep_rank, dep_bonus,
    critical_path}, порядок критического пути)."""
    D = dict(DEP_DEFAULTS)
    D.update(W.get("dependency") or {})
    ids = [p["id"] for p in props_l]
    pos = {i: rows[i]["rank"] for i in ids}
    val = {i: rows[i]["composite"] for i in ids}
    need = {i: set() for i in ids}
    for p in props_l:
        for d in (p.get("dependencies") if isinstance(p.get("dependencies"), list) else []):
            if isinstance(d, str) and d != p["id"] and d in need:
                need[p["id"]].add(d)
    for i, lst in (extra or {}).items():
        if i in need:
            for d in (lst if isinstance(lst, list) else [lst]):
                if isinstance(d, str) and d != i and d in need:
                    need[i].add(d)
    out_e = {i: sorted((j for j in ids if i in need[j]), key=lambda x: pos[x]) for i in ids}
    comp = kosaraju(sorted(ids, key=lambda x: pos[x]), out_e)
    size = {}
    for i in ids:
        size[comp[i]] = size.get(comp[i], 0) + 1
    for j in ids:   # внутри компоненты оставить только «предпосылка выше по рангу»
        if size[comp[j]] > 1:
            need[j] = {i for i in need[j] if not (comp[i] == comp[j] and pos[i] > pos[j])}
    kids = {i: [j for j in ids if i in need[j]] for i in ids}

    def bfs(src, nxt):
        dist = {src: 0}
        q = deque([src])
        while q:
            v = q.popleft()
            for w in nxt(v):
                if w not in dist:
                    dist[w] = dist[v] + 1
                    q.append(w)
        del dist[src]
        return dist

    up = {i: bfs(i, lambda v: need[v]) for i in ids}
    down = {i: bfs(i, lambda v: kids[v]) for i in ids}
    bonus = {}
    for i in ids:
        acc = 0.0
        for j, d in down[i].items():
            acc += val[j] * float(D["decay"]) ** (d - 1)
        bonus[i] = min(float(D["bonus_cap"]), float(D["unlock_bonus"]) * acc)
    sc = {i: val[i] + bonus[i] for i in ids}
    inh = {i: max([sc[i]] + [sc[j] for j in down[i]]) for i in ids}
    placed, seq = set(), []
    while len(seq) < len(ids):
        avail = [i for i in ids if i not in placed and need[i] <= placed]
        if not avail:
            break
        pick = min(avail, key=lambda i: (-round(inh[i], 9), -round(sc[i], 9), pos[i]))
        placed.add(pick)
        seq.append(pick)
    drank = {i: k + 1 for k, i in enumerate(seq)}
    ntop = min(int(D["critical_top_n"]), len(ids))
    top = order[:ntop]
    area = set(top)
    for i in top:
        area.update(up[i])
    memo = {}

    def chain(v):
        if v not in memo:
            preds = [u for u in need[v] if u in area]
            if preds:
                u = min(preds, key=lambda x: (-round(chain(x)[0], 9), -chain(x)[1], pos[x]))
                memo[v] = (val[v] + chain(u)[0], chain(u)[1] + 1, u)
            else:
                memo[v] = (val[v], 1, None)
        return memo[v]

    sys.setrecursionlimit(max(1000, 4 * len(ids) + 100))
    ends = [v for v in top if chain(v)[1] >= 2]
    path = []
    if ends:
        v = min(ends, key=lambda x: (-round(chain(x)[0], 9), -chain(x)[1], pos[x]))
        while v is not None:
            path.insert(0, v)
            v = chain(v)[2]
    res = {}
    for i in ids:
        res[i] = {"blocked_by": sorted(up[i], key=lambda x: pos[x]), "unlocks": sorted(down[i], key=lambda x: pos[x]),
                  "dep_rank": drank.get(i), "dep_bonus": bonus[i], "critical_path": i in path}
    return res, path


def validate(out_dir, quiet=False):
    """Возвращает (ok, список сообщений)."""
    data = Path(out_dir) / "data"
    msgs = []
    try:
        props_l = json.loads((data / "proposals.json").read_text(encoding="utf-8"))
        scores = json.loads((data / "scores.json").read_text(encoding="utf-8"))
        W = json.loads((data / "weights.json").read_text(encoding="utf-8"))
    except FileNotFoundError as e:
        return False, ["нет файла: %s" % e.filename]
    props = {p["id"]: p for p in props_l if isinstance(p, dict) and p.get("id")}
    rows, order = recompute(list(props.values()), W)
    classify(rows, order, props, W)
    bad = 0
    if set(props) != {s.get("id") for s in scores}:
        bad += 1
        msgs.append("наборы id в proposals.json и scores.json различаются")
    by_rank = {s.get("rank"): s for s in scores}
    for s in scores:
        i = s.get("id")
        if i not in rows:
            continue
        r = rows[i]
        for key, tol in TOL.items():
            if key not in s or not is_num(s[key]):
                bad += 1
                msgs.append("%s: нет поля %s" % (i, key))
                continue
            # допуск: округление в файле + относительная погрешность для крупных RICE/ICE
            lim = max(tol, abs(r[key]) * 1e-6)
            if abs(s[key] - r[key]) > lim:
                bad += 1
                msgs.append("%s: %s в файле %s, пересчёт %.6f" % (i, key, s[key], r[key]))
        if s.get("rank") != r["rank"]:
            other = by_rank.get(r["rank"])
            if other is not None and other.get("id") in rows and abs(rows[other["id"]]["composite"] - r["composite"]) <= TIE_EPS:
                msgs.append("ничья: %s / %s — порядок различается только внутри ничьей" % (i, other["id"]))
            else:
                bad += 1
                msgs.append("%s: ранг в файле %s, пересчёт %s" % (i, s.get("rank"), r["rank"]))
        for key in ("quadrant", "priority", "moscow"):
            if s.get(key) != r[key]:
                bad += 1
                msgs.append("%s: %s в файле %s, пересчёт %s" % (i, key, s.get(key), r[key]))
        if sorted(s.get("labels") or []) != sorted(r["labels"]):
            bad += 1
            msgs.append("%s: метки в файле %s, пересчёт %s" % (i, s.get("labels"), r["labels"]))
    if [s.get("rank") for s in scores] != list(range(1, len(scores) + 1)):
        bad += 1
        msgs.append("ранги в scores.json не идут подряд 1..N в порядке файла")
    if scores and all("dep_rank" in s for s in scores):
        try:
            extra = json.loads((data / "gap-audit-deps.json").read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            extra = {}
        deps, path = recompute_deps(list(props.values()), rows, order, W, extra if isinstance(extra, dict) else {})
        for s in scores:
            i = s.get("id")
            if i not in deps:
                continue
            d = deps[i]
            for key in ("blocked_by", "unlocks", "dep_rank", "critical_path"):
                if s.get(key) != d[key]:
                    bad += 1
                    msgs.append("%s: %s в файле %s, пересчёт %s" % (i, key, s.get(key), d[key]))
            if not is_num(s.get("dep_bonus")) or abs(s["dep_bonus"] - d["dep_bonus"]) > 2e-6:
                bad += 1
                msgs.append("%s: dep_bonus в файле %s, пересчёт %.6f" % (i, s.get("dep_bonus"), d["dep_bonus"]))
        if sorted(s["dep_rank"] for s in scores) != list(range(1, len(scores) + 1)):
            bad += 1
            msgs.append("dep_rank не образует перестановку 1..N")
        try:
            cp = json.loads((data / "critical-path.json").read_text(encoding="utf-8"))
            if cp.get("order") != path:
                bad += 1
                msgs.append("critical-path.json: порядок %s, пересчёт %s" % (cp.get("order"), path))
        except FileNotFoundError:
            bad += 1
            msgs.append("нет data/critical-path.json")
        msgs.append("зависимости: пересчитаны blocked_by/unlocks/dep_rank/critical_path; критический путь: %s"
                    % (" → ".join(path) or "нет"))
    elif scores:
        msgs.append("поля зависимостей отсутствуют (scores.json до версии 1.1) — не проверялись")
    msgs.append("проверено строк: %d; сумма composite: пересчёт %.4f, файл %.4f"
                % (len(scores), sum(r["composite"] for r in rows.values()), sum(s.get("composite", 0) for s in scores)))
    if bad:
        msgs.append("FAIL: расхождений %d" % bad)
    else:
        msgs.append("OK: независимый пересчёт совпадает")
    return bad == 0, msgs


def main(argv=None):
    ap = argparse.ArgumentParser(description="Независимый пересчёт оценок и сверка с data/scores.json.")
    ap.add_argument("out", help="папка прогона <OUT>")
    ap.add_argument("--quiet", action="store_true", help="печатать только итог и расхождения")
    a = ap.parse_args(argv)
    ok, msgs = validate(Path(a.out).resolve(), a.quiet)
    for m in msgs:
        if a.quiet and m.startswith("ничья"):
            continue
        print(m)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
