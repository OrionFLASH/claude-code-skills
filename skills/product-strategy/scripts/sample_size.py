#!/usr/bin/env python3
"""Размер выборки и срок эксперимента; измеримость критериев отказа → data/experiments.json.

  Калькулятор (без папки прогона):
    sample_size.py --baseline 0.05 --mde 0.01 [--relative] [--alpha 0.05] [--power 0.8] [--one-sided]
                   [--traffic 200 [--per week|day|month]] [--share 1.0] [--kind share|rate]
                   [--simulate 2000 [--peeks 4] [--seed 7]] [--json]
  Запись эксперимента в прогон:
    sample_size.py <OUT> --add E01 --baseline 0.05 --mde 0.01 [--title …] [--metric …] [--proposal P001]
                   [--population signups] [--traffic N] …       (нет --traffic → поток из data/model.json)
    sample_size.py <OUT> --recalc                пересчитать все эксперименты (после смены модели или трафика)
    sample_size.py <OUT> --criteria [--strict]   измеримость критериев отказа ставок из data/decisions.json
    sample_size.py <OUT>                         показать data/experiments.json

Методы (только стандартная библиотека, statistics.NormalDist):
  - kind=share, A/B двух долей (z-тест):  n на группу = (z₁₋α/₂·√(2·p̄·q̄) + z₁₋β·√(p₁q₁ + p₂q₂))² / (p₂ − p₁)²,
    p₂ = p₁ + MDE (абсолютный; --relative — p₁·(1 + MDE)); --one-sided — z₁₋α;
  - критерий отказа kind=share (одна выборка против порога, односторонний):
    n = (z₁₋α·√(p₀q₀) + z₁₋β·√(p₁q₁))² / (p₁ − p₀)², p₀ = порог, p₁ = baseline (ожидаемое значение);
  - kind=rate (события в неделю, сравнение двух равных периодов, Пуассон):
    T недель = (z + z₁₋β)²·(λ₀ + λ₁) / (λ₀ − λ₁)²; для критерия λ₀ = baseline, λ₁ = порог;
  - срок: недель = n_всего / (трафик в неделю × доля в эксперименте), округление вверх;
  - ложная тревога (--simulate): A/A-симуляция с подглядыванием (--peeks проверок по ходу набора) — доля
    «значимых» результатов при отсутствии эффекта; при одной проверке ≈ α, при подглядывании — больше.
Трафик для прогона: --traffic, иначе kill.traffic_per_week / defaults.traffic_per_week в experiments.json, иначе
среднемесячный поток population из data/model.json (базовый сценарий) / 4,345, иначе run-config project.traffic_hint
(только population=visitors); нет ничего — «ненаблюдаем: нет данных о трафике».
Критерий ненаблюдаем, если нужный срок больше времени до kill.date (или горизонта strategy.horizon_months).
В тексте выборки и сроки — только плейсхолдерами {exp:E01.n}, {exp:E01.weeks}, {exp:K1.status}, {bet:1.kill.weeks}.
Код выхода: 0; 1 — ошибка ввода или (--criteria --strict) есть ненаблюдаемые критерии; 2 — нет папки <OUT>/data.
"""
import argparse
import json
import math
import random
import sys
from datetime import date
from pathlib import Path
from statistics import NormalDist

HERE = Path(__file__).resolve().parent
WEEKS_PER_MONTH = 4.345
PER = {"day": 7.0, "week": 1.0, "month": 1.0 / WEEKS_PER_MONTH}
ND = NormalDist()
POP_FIELD = {"visitors": "visitors", "installs": "visitors", "signups": "signups", "activated": "activated", "new_paying": "new_paying"}


def z(p):
    return ND.inv_cdf(p)


def load_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default
    except (OSError, json.JSONDecodeError) as e:
        print("предупреждение: не удалось прочитать %s: %s" % (path, e), file=sys.stderr)
        return default


# ---------------------------------------------------------------- формулы
def n_two_proportions(p1, p2, alpha=0.05, power=0.8, two_sided=True):
    """n на группу для A/B двух долей."""
    if not (0 < p1 < 1 and 0 < p2 < 1):
        raise ValueError("доли должны быть в (0, 1): %s, %s" % (p1, p2))
    if p1 == p2:
        raise ValueError("MDE = 0: эффект не задан")
    za = z(1 - alpha / 2) if two_sided else z(1 - alpha)
    zb = z(power)
    pbar = (p1 + p2) / 2
    num = (za * math.sqrt(2 * pbar * (1 - pbar)) + zb * math.sqrt(p1 * (1 - p1) + p2 * (1 - p2))) ** 2
    return int(math.ceil(num / (p2 - p1) ** 2))


def n_one_proportion(p0, p1, alpha=0.05, power=0.8, two_sided=False):
    """n для проверки доли против фиксированного порога p0 при ожидаемом значении p1."""
    if not (0 < p0 < 1 and 0 < p1 < 1):
        raise ValueError("доли должны быть в (0, 1): %s, %s" % (p0, p1))
    if p0 == p1:
        raise ValueError("порог равен базовому значению: различие не измерить")
    za = z(1 - alpha / 2) if two_sided else z(1 - alpha)
    zb = z(power)
    num = (za * math.sqrt(p0 * (1 - p0)) + zb * math.sqrt(p1 * (1 - p1))) ** 2
    return int(math.ceil(num / (p1 - p0) ** 2))


def weeks_rate(l0, l1, alpha=0.05, power=0.8, two_sided=True):
    """Недель в каждом из двух периодов, чтобы отличить λ₀ от λ₁ (события в неделю, Пуассон)."""
    if l0 <= 0 or l1 < 0:
        raise ValueError("частоты событий должны быть > 0")
    if l0 == l1:
        raise ValueError("MDE = 0: эффект не задан")
    za = z(1 - alpha / 2) if two_sided else z(1 - alpha)
    zb = z(power)
    return (za + zb) ** 2 * (l0 + l1) / (l0 - l1) ** 2


def _binom(rnd, n, p):
    bv = getattr(rnd, "binomialvariate", None)
    if bv is not None:
        return bv(n, p)
    x = rnd.gauss(n * p, math.sqrt(max(n * p * (1 - p), 1e-12)))         # Python < 3.12: нормальное приближение
    return min(n, max(0, int(round(x))))


def simulate_false_alarm(p, n_per_arm, alpha=0.05, sims=2000, peeks=1, seed=7, two_sided=True):
    """Доля A/A-прогонов, где z-тест хотя бы на одной из peeks проверок «нашёл» эффект."""
    rnd = random.Random(seed)
    zc = z(1 - alpha / 2) if two_sided else z(1 - alpha)
    peeks = max(1, int(peeks))
    bounds = [int(round(n_per_arm * k / peeks)) for k in range(1, peeks + 1)]
    alarms = 0
    for _ in range(int(sims)):
        a = b = done = 0
        hit = False
        for nb in bounds:
            step = nb - done
            if step <= 0:
                continue
            a += _binom(rnd, step, p)
            b += _binom(rnd, step, p)
            done = nb
            pool = (a + b) / (2.0 * done)
            se = math.sqrt(pool * (1 - pool) * 2.0 / done) if 0 < pool < 1 else 0
            if se > 0:
                zz = (b - a) / done / se
                if (abs(zz) if two_sided else zz) > zc:
                    hit = True
                    break
        alarms += hit
    return {"rate": round(alarms / float(sims), 4), "sims": int(sims), "peeks": peeks, "alpha": alpha, "seed": seed}


def calc(baseline, mde, alpha=0.05, power=0.8, relative=False, two_sided=True, kind="share", traffic_per_week=None,
         share=1.0, arms=2, simulate=0, peeks=1, seed=7):
    """Эксперимент A/B → словарь с n_per_arm, n_total, weeks."""
    res = {"kind": kind, "baseline": baseline, "mde": mde, "mde_kind": "relative" if relative else "absolute",
           "alpha": alpha, "power": power, "two_sided": two_sided, "arms": arms}
    if kind == "rate":
        l1 = baseline * (1 + mde) if relative else baseline + mde
        t = weeks_rate(baseline, l1, alpha, power, two_sided)
        res.update({"target": round(l1, 6), "weeks": int(math.ceil(t)), "events_expected": int(math.ceil(t * (baseline + l1))),
                    "method": "Пуассон: два равных периода, z-тест разности счётов"})
        return res
    p2 = baseline * (1 + mde) if relative else baseline + mde
    n = n_two_proportions(baseline, p2, alpha, power, two_sided)
    res.update({"target": round(p2, 6), "n_per_arm": n, "n_total": n * arms, "method": "z-тест двух долей"})
    if traffic_per_week:
        eff = traffic_per_week * (share or 1.0)
        res.update({"traffic_per_week": traffic_per_week, "traffic_share": share,
                    "weeks": int(math.ceil(n * arms / eff)) if eff > 0 else None,
                    "days": int(math.ceil(n * arms / eff * 7)) if eff > 0 else None})
    if simulate:
        res["false_alarm"] = simulate_false_alarm(baseline, n, alpha, simulate, peeks, seed, two_sided)
    return res


# ---------------------------------------------------------------- трафик прогона
def model_flow(model, population):
    """Средний недельный поток population по базовому сценарию data/model.json (или None)."""
    if not isinstance(model, dict):
        return None, None
    sc = (model.get("scenarios") or {}).get("base") or {}
    mo = [m for m in (sc.get("monthly") or []) if isinstance(m, dict)]
    field = POP_FIELD.get(population or "signups", "signups")
    if field == "activated":                     # в помесячной строке нет activated: регистрации × активация сценария
        s2a = ((sc.get("assumptions") or {}).get("signup_to_active") or {}).get("value")
        vals = [m["signups"] * s2a for m in mo if isinstance(m.get("signups"), (int, float))] if isinstance(s2a, (int, float)) else []
    else:
        vals = [m.get(field) for m in mo if isinstance(m.get(field), (int, float))]
    if not vals:
        return None, None
    label = "оценка" if model.get("audience_data") else "допущение"
    return sum(vals) / len(vals) / WEEKS_PER_MONTH, "data/model.json (base, %s в месяц ÷ %s) [%s]" % (field, WEEKS_PER_MONTH, label)


def traffic_for(row, out, model, cfg, exps):
    """(трафик в неделю, источник) для эксперимента или критерия."""
    if isinstance(row.get("traffic_per_week"), (int, float)) and row["traffic_per_week"] > 0:
        return float(row["traffic_per_week"]), row.get("traffic_source") or "задано в записи"
    dflt = (exps or {}).get("defaults") or {}
    if isinstance(dflt.get("traffic_per_week"), (int, float)) and dflt["traffic_per_week"] > 0:
        return float(dflt["traffic_per_week"]), dflt.get("traffic_source") or "experiments.json defaults"
    t, src = model_flow(model, row.get("population"))
    if t:
        return t, src
    th = ((cfg or {}).get("project") or {}).get("traffic_hint")
    if (row.get("population") or "signups") in ("visitors", "installs") and isinstance(th, (int, float)) and th > 0:
        return th / WEEKS_PER_MONTH, "run-config project.traffic_hint ÷ %s" % WEEKS_PER_MONTH
    return None, None


# ---------------------------------------------------------------- критерии отказа
def weeks_until(d, today=None):
    try:
        y, m, dd = (int(x) for x in str(d).split("-"))
        return (date(y, m, dd) - (today or date.today())).days / 7.0
    except (ValueError, TypeError):
        return None


def evaluate_criteria(out, decisions=None, model=None, cfg=None, exps=None, today=None):
    """Измеримость kill-критериев ставок → список словарей (id K<n>, bet, n, weeks, status, status_text, reason)."""
    out = Path(out)
    if decisions is None:
        decisions = load_json(out / "data" / "decisions.json", None)
    if model is None:
        model = load_json(out / "data" / "model.json", None)
    if cfg is None:
        cfg = load_json(out / "build" / "run-config.json", {}) or {}
    if exps is None:
        exps = load_json(out / "data" / "experiments.json", None)
    horizon = int(((cfg.get("strategy") or {}).get("horizon_months")) or 12)
    rows = []
    for b in (decisions or {}).get("bets") or []:
        if not isinstance(b, dict) or not isinstance(b.get("kill"), dict):
            continue
        k = b["kill"]
        row = {"id": "K%s" % b.get("id"), "bet": b.get("id"), "metric": k.get("metric"), "kind": k.get("kind", "share"),
               "baseline": k.get("baseline"), "threshold": k.get("threshold"), "date": k.get("date"),
               "population": k.get("population") or ("signups" if k.get("kind", "share") == "share" else None)}
        alpha, power = float(k.get("alpha", 0.05)), float(k.get("power", 0.8))
        avail = weeks_until(k.get("date"), today) if k.get("date") else None
        if avail is None:
            avail = horizon * WEEKS_PER_MONTH
            row["available_basis"] = "горизонт %d мес." % horizon
        else:
            row["available_basis"] = "до kill.date"
        row["available_weeks"] = round(avail, 1)
        base, thr = k.get("baseline"), k.get("threshold")
        num = lambda x: isinstance(x, (int, float)) and not isinstance(x, bool)
        try:
            if row["kind"] == "other":
                raise ValueError("kind=other: метод расчёта не задан — укажите share или rate")
            if not (num(base) and num(thr)):
                raise ValueError("нет числовых baseline и threshold")
            if row["kind"] == "rate":
                t = weeks_rate(float(base), float(thr), alpha, power, two_sided=False)
                row.update({"n": int(math.ceil(t * (base + thr))), "n_unit": "событий", "weeks": int(math.ceil(t)),
                            "method": "Пуассон, односторонний: период до и после"})
                row["traffic_source"] = "частота событий из baseline"
            else:
                n = n_one_proportion(float(thr), float(base), alpha, power)
                row.update({"n": n, "n_unit": row["population"], "method": "одна доля против порога, односторонний z"})
                tr, src = traffic_for(dict(k, population=row["population"]), out, model, cfg, exps)
                if not tr:
                    raise LookupError("нет данных о трафике (%s в неделю)" % row["population"])
                row.update({"traffic_per_week": round(tr, 1), "traffic_source": src, "weeks": int(math.ceil(n / tr))})
        except LookupError as e:
            row.update({"status": "unobservable", "status_text": "ненаблюдаем", "reason": str(e)})
            rows.append(row)
            continue
        except ValueError as e:
            row.update({"status": "unknown", "status_text": "не рассчитан", "reason": str(e)})
            rows.append(row)
            continue
        if avail <= 0:
            row.update({"status": "unobservable", "status_text": "ненаблюдаем", "reason": "дата критерия уже прошла"})
        elif row["weeks"] > avail:
            row.update({"status": "unobservable", "status_text": "ненаблюдаем",
                        "reason": "нужно %d нед., доступно %.0f нед. (%s)" % (row["weeks"], avail, row["available_basis"])})
        else:
            row.update({"status": "observable", "status_text": "наблюдаем",
                        "reason": "нужно %d нед. из %.0f доступных" % (row["weeks"], avail)})
        rows.append(row)
    return rows


# ---------------------------------------------------------------- файл прогона
def load_exps(out):
    e = load_json(Path(out) / "data" / "experiments.json", None)
    if isinstance(e, list):
        e = {"experiments": e}
    if not isinstance(e, dict):
        e = {}
    e.setdefault("version", 1)
    e.setdefault("experiments", [])
    return e


def save_exps(out, e):
    e["updated"] = date.today().isoformat()
    p = Path(out) / "data" / "experiments.json"
    p.write_text(json.dumps(e, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return p


def compute_row(row, out, model, cfg, exps):
    """Пересчёт одной записи эксперимента (поля ввода сохраняются)."""
    tr, src = traffic_for(row, out, model, cfg, exps)
    r = calc(float(row["baseline"]), float(row["mde"]), float(row.get("alpha", 0.05)), float(row.get("power", 0.8)),
             row.get("mde_kind") == "relative", row.get("two_sided", True), row.get("kind", "share"), tr,
             float(row.get("traffic_share", 1.0)), int(row.get("arms", 2)), int(row.get("simulate") or 0),
             int(row.get("peeks") or 1), int(row.get("seed") or 7))
    keep = {k: row[k] for k in ("id", "title", "metric", "proposal", "population", "simulate", "peeks", "seed", "note", "file") if k in row}
    if row.get("traffic_per_week") and row.get("traffic_source"):
        keep["traffic_source"] = row["traffic_source"]
    new = dict(keep, **r)
    if tr and "traffic_source" not in new:
        new["traffic_source"] = src
    if tr is None and r.get("kind") != "rate":
        new.update({"weeks": None, "status": "unobservable", "status_text": "ненаблюдаем", "reason": "нет данных о трафике"})
    else:
        horizon = int(((cfg or {}).get("strategy") or {}).get("horizon_months") or 12)
        hw = horizon * WEEKS_PER_MONTH
        ok = new.get("weeks") is not None and new["weeks"] <= hw
        new.update({"horizon_weeks": round(hw, 1), "status": "observable" if ok else "unobservable",
                    "status_text": "наблюдаем" if ok else "ненаблюдаем",
                    "reason": ("%s нед. в пределах горизонта" % new.get("weeks")) if ok else
                    ("нужно %s нед. > горизонта %.0f нед." % (new.get("weeks"), hw))})
    new["label"] = "оценка" if "оценка" in str(new.get("traffic_source") or "") or row.get("traffic_per_week") else "допущение"
    return new


def print_calc(r):
    if r.get("kind") == "rate":
        print("Пуассон: λ₀ = %s → λ₁ = %s событий/нед.: нужно %s нед. в каждом периоде (≈ %s событий)"
              % (r["baseline"], r["target"], r["weeks"], r["events_expected"]))
        return
    print("Доли %s → %s (MDE %s %s), α = %s, мощность %s, %s: n = %s на группу, всего %s"
          % (r["baseline"], r["target"], r["mde"], "отн." if r["mde_kind"] == "relative" else "абс.", r["alpha"], r["power"],
             "двусторонний" if r["two_sided"] else "односторонний", r["n_per_arm"], r["n_total"]))
    if r.get("weeks") is not None:
        print("Срок набора при %s в неделю (доля %s): %s нед. (%s дн.)" % (round(r["traffic_per_week"], 1), r.get("traffic_share", 1.0), r["weeks"], r["days"]))
    fa = r.get("false_alarm")
    if fa:
        print("Ложная тревога (A/A, %d симуляций, проверок %d): %.1f %% при α = %s" % (fa["sims"], fa["peeks"], fa["rate"] * 100, fa["alpha"]))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0], formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out", nargs="?", help="папка прогона <OUT> (без неё — только калькулятор)")
    ap.add_argument("--baseline", type=float, help="базовая доля (0…1) или события в неделю (--kind rate)")
    ap.add_argument("--mde", type=float, help="минимальный эффект: абсолютный (0.01 = +1 п. п.) или относительный с --relative")
    ap.add_argument("--relative", action="store_true", help="MDE относительный (0.2 = +20 %%)")
    ap.add_argument("--alpha", type=float, default=0.05)
    ap.add_argument("--power", type=float, default=0.8)
    ap.add_argument("--one-sided", action="store_true", help="односторонний тест")
    ap.add_argument("--kind", choices=["share", "rate"], default="share")
    ap.add_argument("--traffic", type=float, help="участников (обе группы) за период --per")
    ap.add_argument("--per", choices=sorted(PER), default="week", help="период трафика (по умолчанию неделя)")
    ap.add_argument("--share", type=float, default=1.0, help="доля трафика в эксперименте")
    ap.add_argument("--arms", type=int, default=2)
    ap.add_argument("--simulate", type=int, default=0, help="число A/A-симуляций ложной тревоги")
    ap.add_argument("--peeks", type=int, default=1, help="промежуточных проверок в симуляции")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--add", metavar="ID", help="записать/обновить эксперимент в data/experiments.json")
    ap.add_argument("--title")
    ap.add_argument("--metric")
    ap.add_argument("--proposal")
    ap.add_argument("--population", choices=sorted(POP_FIELD), default=None, help="поток для срока из модели")
    ap.add_argument("--recalc", action="store_true", help="пересчитать все эксперименты прогона")
    ap.add_argument("--criteria", action="store_true", help="проверить измеримость критериев отказа из data/decisions.json")
    ap.add_argument("--strict", action="store_true", help="--criteria: код 1, если есть ненаблюдаемые")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    for name in ("alpha", "power", "share"):
        v = getattr(a, name)
        if not 0 < v <= 1 or (name != "share" and v >= 1):
            print("ошибка: --%s вне (0, 1)" % name, file=sys.stderr)
            return 1
    weekly = a.traffic * PER[a.per] if a.traffic else None
    if not a.out:
        if a.baseline is None or a.mde is None:
            ap.error("нужны --baseline и --mde (или папка прогона)")
        try:
            r = calc(a.baseline, a.mde, a.alpha, a.power, a.relative, not a.one_sided, a.kind, weekly, a.share, a.arms,
                     a.simulate, a.peeks, a.seed)
        except ValueError as e:
            print("ошибка: %s" % e, file=sys.stderr)
            return 1
        print(json.dumps(r, ensure_ascii=False, indent=2)) if a.json else print_calc(r)
        return 0
    out = Path(a.out).resolve()
    if not (out / "data").is_dir():
        print("ошибка: нет папки %s/data" % out, file=sys.stderr)
        return 2
    model = load_json(out / "data" / "model.json", None)
    cfg = load_json(out / "build" / "run-config.json", {}) or {}
    exps = load_exps(out)
    if a.add:
        if a.baseline is None or a.mde is None:
            ap.error("--add: нужны --baseline и --mde")
        row = {"id": a.add, "baseline": a.baseline, "mde": a.mde, "mde_kind": "relative" if a.relative else "absolute",
               "alpha": a.alpha, "power": a.power, "two_sided": not a.one_sided, "kind": a.kind, "arms": a.arms,
               "traffic_share": a.share, "population": a.population or ("visitors" if a.kind == "share" else None)}
        for k in ("title", "metric", "proposal"):
            if getattr(a, k):
                row[k] = getattr(a, k)
        if weekly:
            row["traffic_per_week"], row["traffic_source"] = weekly, "--traffic %s в %s" % (a.traffic, a.per)
        if a.simulate:
            row.update({"simulate": a.simulate, "peeks": a.peeks, "seed": a.seed})
        old = next((x for x in exps["experiments"] if x.get("id") == a.add), None)
        for k in ("title", "metric", "proposal", "note", "file"):
            if old and old.get(k) and k not in row:
                row[k] = old[k]
        try:
            new = compute_row(row, out, model, cfg, exps)
        except ValueError as e:
            print("ошибка: %s" % e, file=sys.stderr)
            return 1
        exps["experiments"] = [x for x in exps["experiments"] if x.get("id") != a.add] + [new]
        exps["experiments"].sort(key=lambda x: str(x.get("id")))
        p = save_exps(out, exps)
        print("записано %s: %s" % (p, a.add))
        print_calc(new)
        if new.get("status") == "unobservable":
            print("! %s: %s — %s" % (a.add, new["status_text"], new.get("reason")))
        return 0
    if a.recalc:
        rows = []
        for x in exps["experiments"]:
            src = dict(x)
            if not str(src.get("traffic_source") or "").startswith("--traffic") and not src.get("traffic_fixed"):
                src.pop("traffic_per_week", None)
                src.pop("traffic_source", None)
            try:
                rows.append(compute_row(src, out, model, cfg, exps))
            except (ValueError, KeyError) as e:
                print("пропущен %s: %s" % (x.get("id"), e), file=sys.stderr)
                rows.append(x)
        exps["experiments"] = rows
        p = save_exps(out, exps)
        print("пересчитано экспериментов: %d → %s" % (len(rows), p))
        return 0
    if a.criteria:
        dec = load_json(out / "data" / "decisions.json", None)
        if not isinstance(dec, dict):
            print("нет data/decisions.json (decisions.py <OUT> --init)", file=sys.stderr)
            return 1
        rows = evaluate_criteria(out, dec, model, cfg, exps)
        exps["criteria"] = rows
        p = save_exps(out, exps)
        if a.json:
            print(json.dumps(rows, ensure_ascii=False, indent=2))
        else:
            for r in rows:
                print("%s ставка %s «%s»: %s — n %s, срок %s нед.; %s" % (r["id"], r["bet"], r.get("metric"), r["status_text"],
                                                                     r.get("n", "—"), r.get("weeks", "—"), r.get("reason", "")))
            print("записано %s (criteria); плейсхолдеры {exp:K1.n}, {exp:K1.weeks}, {bet:1.kill.status}" % p)
        bad = [r for r in rows if r["status"] != "observable"]
        return 1 if (a.strict and bad) else 0
    if a.json:
        print(json.dumps(exps, ensure_ascii=False, indent=2))
    else:
        for x in exps["experiments"]:
            print("%s %s: n %s на группу, %s нед., %s" % (x.get("id"), x.get("title") or x.get("metric") or "", x.get("n_per_arm", "—"),
                                                     x.get("weeks", "—"), x.get("status_text", "")))
        for x in exps.get("criteria") or []:
            print("%s (ставка %s): %s, %s нед." % (x["id"], x.get("bet"), x.get("status_text"), x.get("weeks", "—")))
        if not exps["experiments"] and not exps.get("criteria"):
            print("data/experiments.json пуст: sample_size.py <OUT> --add E01 --baseline … --mde …")
    return 0


if __name__ == "__main__":
    sys.exit(main())
