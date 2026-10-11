#!/usr/bin/env python3
"""Единый источник решений стратегии data/decisions.json и плейсхолдеры для текста разделов.

  decisions.py <OUT> --init [--force]          заготовка data/decisions.json (templates/decisions.example.json,
                                                P-id ставок — лидеры P0 из data/scores.json, если он есть)
  decisions.py <OUT> --check [--json]          проверка схемы (код 1 — ошибки)
  decisions.py <OUT> --list-placeholders [--json]   все ключи {bet:…}, {north_star}, {model:…}, {exp:…} с текущими значениями

Схема (подробно — references/decisions.md):
  bets[]       {id 1..3, name, what, why, effect, proposals [P-id], attention_share,
                kill {metric, threshold, date YYYY-MM-DD, baseline?, direction below|above, kind share|rate|other,
                      population visitors|installs|signups|activated|new_paying, traffic_per_week?, unit?, text?},
                premortem [строка | {cause, signal}]}
  north_star   {metric, definition, target, inputs [..]}
  anti_goals   [строка | {text, why}]
  forks        [{id F1…, question, default, cost, decision}]
  capacity     {team_size, hours_per_week, note …}
  bans         [строка]

Плейсхолдеры (подставляет assemble_strategy.py; в коде `…` и в ограждённых блоках не трогаются):
  {bet:1.name} {bet:1.what} {bet:1.kill} {bet:1.kill.metric|threshold|baseline|date|n|weeks|status} {bet:1.pids}
  {bet:1.premortem} {bet:1.premortem.2} {north_star} {north_star.target} {anti_goals} {anti_goals.1}
  {fork:F1} {fork:F1.default} {capacity} {capacity.team_size} {bans}
  {model:base.ltv} {model:pess.cac} {model:base.users_last} …   — из data/model.json (model.py)
  {exp:E01.n} {exp:E01.weeks} {exp:K1.status} …                   — из data/experiments.json (sample_size.py)
  Формат после «|»: {model:base.ltv|money} (с символом валюты), {model:base.churn|%} (доля → проценты), {…|0}/{…|1}/{…|2}
  (знаков после запятой). Неизвестный ключ — ошибка сборки.
Только стандартная библиотека.
"""
import argparse
import json
import math
import re
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent
EXAMPLE = SKILL / "templates" / "decisions.example.json"
NBSP = " "
SCEN_ALIAS = {"pess": "pessimistic", "pessimistic": "pessimistic", "base": "base", "opt": "optimistic", "optimistic": "optimistic"}
BARE = ("north_star", "anti_goals", "capacity", "bans")
KINDS = ("bet", "fork", "model", "exp")
# {bet:1.kill} | {north_star.target} | {model:base.ltv|money}
PH_RE = re.compile(r"\{(?:(bet|fork|model|exp)[ \t]*:[ \t]*([^{}|\n]*?)|(north_star|anti_goals|capacity|bans)((?:\.[A-Za-z0-9_]+)*))"
                   r"[ \t]*(?:\|[ \t]*([%A-Za-z0-9_.]+)[ \t]*)?\}")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
PID_RE = re.compile(r"^P\d{3}$")
POPULATIONS = ("visitors", "installs", "signups", "activated", "new_paying")
# прогнозные ключи модели: в режиме sensitivity-only их нельзя подавать как прогноз
FORECAST_KEYS = ("net_revenue", "revenue_last", "users_last", "paying_last", "breakeven_month", "roi", "new_paying", "activated",
                 "signups", "visitors", "installs", "cost")


# ---------------------------------------------------------------- ввод-вывод
def load_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default
    except (OSError, json.JSONDecodeError) as e:
        print("предупреждение: не удалось прочитать %s: %s" % (path, e), file=sys.stderr)
        return default


def load(out):
    d = load_json(Path(out) / "data" / "decisions.json", None)
    return d if isinstance(d, dict) else None


# ---------------------------------------------------------------- числа и даты по-русски
def is_num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and not (isinstance(x, float) and math.isnan(x))


def group(n):
    s = "%d" % abs(n)
    parts = []
    while len(s) > 3:
        parts.insert(0, s[-3:])
        s = s[:-3]
    parts.insert(0, s)
    return ("-" if n < 0 else "") + NBSP.join(parts)


def fmt_num(v, digits=None):
    """12345.6 → «12 346», 3.456 → «3,46», 0.0612 → «0,061»; digits — фиксированное число знаков после запятой."""
    if not is_num(v):
        return str(v)
    if digits is not None:
        if digits == 0:
            return group(int(round(v)))
        whole, frac = (("%." + str(digits) + "f") % abs(v)).split(".")
        return ("-" if v < 0 else "") + group(int(whole)) + "," + frac
    if float(v).is_integer() or abs(v) >= 100:
        return group(int(round(v)))
    if abs(v) >= 1:
        s = ("%.2f" % v).rstrip("0").rstrip(".")
    else:
        s = ("%.3f" % v).rstrip("0").rstrip(".")
        if s in ("0", "-0"):
            s = ("%.2g" % v)
    return s.replace(".", ",")


def fmt_pct(v, digits=None):
    if not is_num(v):
        return str(v)
    x = v * 100
    if digits is None:
        digits = 0 if float(round(x, 6)).is_integer() else 1
    return fmt_num(x, digits) + NBSP + "%"


def fmt_date(s):
    """«2027-01-31» → «31.01.2027»; иначе как есть."""
    if isinstance(s, str) and DATE_RE.match(s):
        y, m, d = s.split("-")
        return "%s.%s.%s" % (d, m, y)
    return str(s) if s is not None else ""


def apply_format(value, spec, currency_symbol=""):
    """Значение → строка по формату после «|»."""
    if value is None:
        return None
    if not spec:
        return fmt_num(value) if is_num(value) else str(value)
    if not is_num(value):
        return str(value)
    if spec == "%":
        return fmt_pct(value)
    if spec.startswith("%") and spec[1:].isdigit():
        return fmt_pct(value, int(spec[1:]))
    if spec.isdigit():
        return fmt_num(value, int(spec))
    if spec in ("money", "cur"):
        digits = 0 if abs(value) >= 100 or float(value).is_integer() else 2
        return fmt_num(value, digits) + (NBSP + currency_symbol if currency_symbol else "")
    if spec == "int":
        return group(int(round(value)))
    raise ValueError("неизвестный формат «|%s» (допустимы %%, %%1, 0, 1, 2, money, int)" % spec)


# ---------------------------------------------------------------- решения: представление
def kill_threshold_text(kill):
    if not isinstance(kill, dict):
        return ""
    if kill.get("threshold_text"):
        return str(kill["threshold_text"])
    t = kill.get("threshold")
    if is_num(t):
        if kill.get("kind", "share") == "share" and 0 < abs(t) <= 1 and not kill.get("unit"):
            return fmt_pct(t)
        return fmt_num(t) + ((NBSP + str(kill["unit"])) if kill.get("unit") else "")
    return str(t) if t is not None else ""


def kill_text(kill):
    """Полная фраза критерия отказа: «доля активации ниже 35 % к 31.01.2027»."""
    if not isinstance(kill, dict):
        return ""
    if kill.get("text"):
        return str(kill["text"])
    op = "выше" if kill.get("direction") == "above" else "ниже"
    s = "%s %s %s" % (kill.get("metric") or "метрика", op, kill_threshold_text(kill))
    if kill.get("date"):
        s += " к %s" % fmt_date(kill["date"])
    return s


def item_text(x, key="text"):
    if isinstance(x, dict):
        t = x.get(key) or x.get("cause") or x.get("text") or ""
        why = x.get("why") or x.get("signal")
        return ("%s (%s)" % (t, why)) if why else str(t)
    return str(x)


def bets(d):
    out = []
    for b in (d or {}).get("bets") or []:
        if isinstance(b, dict) and b.get("id") is not None:
            out.append(b)
    return out


def bet_by_id(d, i):
    for b in bets(d):
        if str(b.get("id")) == str(i):
            return b
    return None


# ---------------------------------------------------------------- проверка схемы
def validate(d, proposals=None):
    """→ (errors, warnings): списки строк."""
    errs, warns = [], []
    if not isinstance(d, dict):
        return ["decisions.json — не объект"], []
    bl = d.get("bets")
    if not isinstance(bl, list) or not bl:
        errs.append("bets: нужен непустой список ставок")
        bl = []
    elif len(bl) != 3:
        warns.append("bets: ставок %d (по методике — три)" % len(bl))
    seen = set()
    for k, b in enumerate(bl, 1):
        where = "bets[%d]" % k
        if not isinstance(b, dict):
            errs.append("%s: не объект" % where)
            continue
        bid = b.get("id")
        if not isinstance(bid, int) or bid < 1:
            errs.append("%s: id — целое ≥ 1" % where)
        elif bid in seen:
            errs.append("%s: id %s повторяется" % (where, bid))
        seen.add(bid)
        if not str(b.get("name") or "").strip():
            errs.append("%s: нет name" % where)
        for p in b.get("proposals") or []:
            if not PID_RE.match(str(p)):
                errs.append("%s: «%s» — не P-id" % (where, p))
            elif proposals is not None and p not in proposals:
                errs.append("%s: %s нет в data/proposals.json" % (where, p))
        if not b.get("proposals"):
            warns.append("%s: нет proposals (P-id ставки)" % where)
        kill = b.get("kill")
        if not isinstance(kill, dict):
            errs.append("%s: нет kill {metric, threshold, date}" % where)
        else:
            for f in ("metric", "threshold", "date"):
                if kill.get(f) in (None, ""):
                    errs.append("%s.kill: нет %s" % (where, f))
            if kill.get("date") and not DATE_RE.match(str(kill["date"])):
                errs.append("%s.kill.date: формат YYYY-MM-DD (сейчас «%s»)" % (where, kill["date"]))
            if kill.get("direction") not in (None, "below", "above"):
                errs.append("%s.kill.direction: below | above" % where)
            if kill.get("kind") not in (None, "share", "rate", "other"):
                errs.append("%s.kill.kind: share | rate | other" % where)
            if kill.get("population") not in (None,) + POPULATIONS:
                errs.append("%s.kill.population: %s" % (where, " | ".join(POPULATIONS)))
            if kill.get("kind", "share") == "share":
                for f in ("threshold", "baseline"):
                    v = kill.get(f)
                    if is_num(v) and not 0 < v < 1:
                        errs.append("%s.kill.%s: для kind=share — доля (0…1), сейчас %s" % (where, f, v))
            if kill.get("baseline") is None and kill.get("kind", "share") != "other":
                warns.append("%s.kill: нет baseline — измеримость (n и срок) не посчитать" % where)
        pm = b.get("premortem")
        if not pm:
            warns.append("%s: нет premortem (3 причины провала)" % where)
        elif not isinstance(pm, list):
            errs.append("%s.premortem: список" % where)
    ns = d.get("north_star")
    if not isinstance(ns, dict) or not str(ns.get("metric") or "").strip():
        errs.append("north_star: нужен объект с metric")
    ag = d.get("anti_goals")
    if ag is not None and not isinstance(ag, list):
        errs.append("anti_goals: список")
    elif not ag:
        warns.append("anti_goals: пусто (по методике — 3–5)")
    fids = set()
    for k, f in enumerate(d.get("forks") or [], 1):
        if not isinstance(f, dict) or not f.get("id") or not f.get("question"):
            errs.append("forks[%d]: нужны id и question" % k)
            continue
        if f["id"] in fids:
            errs.append("forks[%d]: id %s повторяется" % (k, f["id"]))
        fids.add(f["id"])
        if not f.get("default"):
            warns.append("forks[%d] (%s): нет default — вариант по умолчанию" % (k, f["id"]))
    if d.get("capacity") is not None and not isinstance(d.get("capacity"), dict):
        errs.append("capacity: объект")
    return errs, warns


# ---------------------------------------------------------------- значения плейсхолдеров
def decision_values(d, criteria=None):
    """Плоский словарь «ключ → значение» по decisions.json (+ измеримость из критериев sample_size)."""
    v = {}
    if not isinstance(d, dict):
        return v
    crit = {str(c.get("bet")): c for c in (criteria or []) if isinstance(c, dict)}
    for b in bets(d):
        i = str(b["id"])
        p = "bet:%s." % i
        v[p + "name"] = b.get("name") or ""
        for f in ("what", "why", "effect"):
            if b.get(f) not in (None, ""):
                v[p + f] = b[f]
        v[p + "pids"] = ", ".join(b.get("proposals") or [])
        if is_num(b.get("attention_share")):
            v[p + "share"] = fmt_pct(b["attention_share"])
        kill = b.get("kill") if isinstance(b.get("kill"), dict) else None
        if kill:
            v["bet:%s.kill" % i] = kill_text(kill)
            v[p + "kill.metric"] = kill.get("metric") or ""
            v[p + "kill.threshold"] = kill_threshold_text(kill)
            if kill.get("baseline") is not None:
                v[p + "kill.baseline"] = kill_threshold_text(dict(kill, threshold=kill["baseline"], threshold_text=None))
            if kill.get("date"):
                v[p + "kill.date"] = fmt_date(kill["date"])
            c = crit.get(i)
            if c:
                if c.get("n") is not None:
                    v[p + "kill.n"] = c["n"]
                if c.get("weeks") is not None:
                    v[p + "kill.weeks"] = c["weeks"]
                v[p + "kill.status"] = c.get("status_text") or c.get("status") or ""
        pm = [item_text(x) for x in (b.get("premortem") or [])]
        if pm:
            v[p + "premortem"] = "; ".join(pm)
            for k, t in enumerate(pm, 1):
                v[p + "premortem.%d" % k] = t
    ns = d.get("north_star")
    if isinstance(ns, dict):
        v["north_star"] = ns.get("metric") or ""
        for f in ("metric", "definition", "target"):
            if ns.get(f) not in (None, ""):
                v["north_star." + f] = ns[f]
        if ns.get("inputs"):
            v["north_star.inputs"] = "; ".join(str(x) for x in ns["inputs"])
    ag = [item_text(x) for x in (d.get("anti_goals") or [])]
    if ag:
        v["anti_goals"] = "; ".join(ag)
        for k, t in enumerate(ag, 1):
            v["anti_goals.%d" % k] = t
    for f in d.get("forks") or []:
        if isinstance(f, dict) and f.get("id"):
            p = "fork:%s" % f["id"]
            v[p] = f.get("question") or ""
            for k in ("default", "cost", "decision"):
                if f.get(k) not in (None, ""):
                    v[p + "." + k] = f[k]
    cap = d.get("capacity")
    if isinstance(cap, dict) and cap:
        parts = []
        for k, x in cap.items():
            if isinstance(x, (str, int, float)) and not isinstance(x, bool):
                v["capacity." + k] = x
                if k != "note":
                    parts.append("%s: %s" % (k, fmt_num(x) if is_num(x) else x))
        v["capacity"] = cap.get("text") or cap.get("note") or "; ".join(parts)
    if d.get("bans"):
        v["bans"] = "; ".join(item_text(x) for x in d["bans"])
    return v


def model_values(m):
    """Плоский словарь по data/model.json: {scen}.{метрика}, итоги, последний месяц, допущения, solo, capacity."""
    v = {}
    if not isinstance(m, dict):
        return v
    for k in ("currency", "currency_symbol", "horizon_months", "profile", "model_profile", "revenue_model", "mode"):
        if m.get(k) is not None:
            v[k] = m[k]
    for name, sc in (m.get("scenarios") or {}).items():
        if not isinstance(sc, dict):
            continue
        for k, x in sc.items():
            if is_num(x) or isinstance(x, str):
                v["%s.%s" % (name, k)] = x
        for k, x in (sc.get("totals") or {}).items():
            if is_num(x):
                v["%s.%s" % (name, k)] = x
        for k, x in (sc.get("paid") or {}).items():
            if is_num(x) or isinstance(x, str):
                v["%s.paid.%s" % (name, k)] = x
        mo = sc.get("monthly") or []
        if mo and isinstance(mo[-1], dict):
            for k, x in mo[-1].items():
                if k != "month" and is_num(x):
                    v["%s.%s_last" % (name, k)] = x
        if mo and isinstance(mo[0], dict):
            for k, x in mo[0].items():
                if k != "month" and is_num(x):
                    v["%s.%s_first" % (name, k)] = x
        for k, a in (sc.get("assumptions") or {}).items():
            x = a.get("value") if isinstance(a, dict) else a
            if is_num(x) or isinstance(x, str):
                v.setdefault("%s.%s" % (name, k), x)
    solo = m.get("solo")
    if isinstance(solo, dict):
        for name, sc in (solo.get("scenarios") or {}).items():
            for k, x in (sc or {}).items():
                if is_num(x):
                    v.setdefault("%s.%s" % (name, k), x)
        for k, x in (solo.get("support") or {}).items():
            if is_num(x):
                v["support.%s" % k] = x
    cap = m.get("capacity")
    if isinstance(cap, dict):
        for k, x in cap.items():
            if is_num(x):
                v["capacity.%s" % k] = x
        pp = cap.get("p0_p1") or {}
        for k, x in pp.items():
            if is_num(x):
                v["capacity.p0_p1.%s" % k] = x
    return v


def exp_values(e):
    """Плоский словарь по data/experiments.json: E01.n, E01.weeks, K1.status …"""
    v = {}
    if not isinstance(e, dict):
        return v
    for row in list(e.get("experiments") or []) + list(e.get("criteria") or []):
        if not isinstance(row, dict) or not row.get("id"):
            continue
        rid = str(row["id"])
        for k, x in row.items():
            if k == "id":
                continue
            if is_num(x) or isinstance(x, str):
                v["%s.%s" % (rid, k)] = x
        if row.get("n_per_arm") is not None:
            v["%s.n" % rid] = row["n_per_arm"]
        elif row.get("n") is not None:
            v["%s.n" % rid] = row["n"]
        fa = row.get("false_alarm")
        if isinstance(fa, dict) and is_num(fa.get("rate")):
            v["%s.false_alarm" % rid] = fa["rate"]
        if row.get("status_text"):
            v["%s.status" % rid] = row["status_text"]
    return v


class Registry:
    """Все значения плейсхолдеров прогона: решения, модель, эксперименты."""

    def __init__(self, out, criteria=None):
        out = Path(out)
        self.out = out
        self.decisions = load(out)
        self.model = load_json(out / "data" / "model.json", None)
        self.experiments = load_json(out / "data" / "experiments.json", None)
        if criteria is None and isinstance(self.experiments, dict):
            criteria = self.experiments.get("criteria")
        self.criteria = criteria or []
        self.dec = decision_values(self.decisions, self.criteria)
        self.mod = model_values(self.model)
        self.exp = exp_values(self.experiments)
        self.symbol = (self.model or {}).get("currency_symbol") or (self.model or {}).get("currency") or ""

    def key_of(self, kind, key, bare, tail):
        """Нормализованный ключ из совпадения PH_RE."""
        if bare:
            return bare + (tail or "")
        key = re.sub(r"\s+", "", key or "")
        if kind == "model":
            head, _, rest = key.partition(".")
            if head in SCEN_ALIAS and rest:
                key = SCEN_ALIAS[head] + "." + rest
            return "model:" + key
        return "%s:%s" % (kind, key)

    def lookup(self, full):
        """Нормализованный ключ → (значение | None, причина)."""
        kind, _, key = full.partition(":")
        if not key:                                        # голые north_star / anti_goals / capacity / bans
            kind, key = None, full
        if kind in (None, "bet", "fork"):
            if self.decisions is None:
                return None, "нет data/decisions.json (decisions.py <OUT> --init)"
            k = full
            if k in self.dec:
                return self.dec[k], None
            return None, "нет ключа «%s» в data/decisions.json" % k
        if kind == "model":
            if self.model is None:
                return None, "нет data/model.json (model.py <OUT>)"
            if key in self.mod:
                return self.mod[key], None
            return None, "нет ключа «%s» в data/model.json" % key
        if kind == "exp":
            if key in self.exp:
                return self.exp[key], None
            if self.experiments is None:
                return None, "нет data/experiments.json (sample_size.py <OUT> --add …)"
            return None, "нет ключа «%s» в data/experiments.json" % key
        return None, "неизвестный вид плейсхолдера «%s»" % kind

    def render(self, full, spec):
        val, why = self.lookup(full)
        if val is None:
            return None, why
        try:
            return apply_format(val, spec, self.symbol if full.startswith("model:") or spec == "money" else ""), None
        except ValueError as e:
            return None, str(e)

    def listing(self):
        """[(плейсхолдер, значение-строка, источник)] для --list-placeholders."""
        rows = []
        for k, x in self.dec.items():
            rows.append(("{%s}" % k, apply_format(x, None), "data/decisions.json"))
        for k, x in self.mod.items():
            rows.append(("{model:%s}" % k, apply_format(x, None), "data/model.json"))
        for k, x in self.exp.items():
            rows.append(("{exp:%s}" % k, apply_format(x, None), "data/experiments.json"))
        return rows


def find(text):
    """Итератор совпадений плейсхолдеров решений/модели/экспериментов."""
    return PH_RE.finditer(text)


# ---------------------------------------------------------------- заготовка
def scaffold(out):
    d = load_json(EXAMPLE, None)
    if not isinstance(d, dict):
        d = {"version": 1, "bets": [], "north_star": {"metric": "<заполнить>"}, "anti_goals": [], "forks": [], "capacity": {}, "bans": []}
    d = json.loads(json.dumps(d))
    d.pop("_comment", None)
    d["updated"] = date.today().isoformat()
    scores = load_json(Path(out) / "data" / "scores.json", None)
    if isinstance(scores, list):
        p0 = sorted((s for s in scores if isinstance(s, dict) and s.get("priority") == "P0"), key=lambda s: s.get("dep_rank") or s.get("rank") or 10 ** 6)
        ids = [s["id"] for s in p0 if s.get("id")]
        for k, b in enumerate(d.get("bets") or []):
            chunk = ids[k * 3:(k + 1) * 3]
            if chunk:
                b["proposals"] = chunk
    cfg = load_json(Path(out) / "build" / "run-config.json", {}) or {}
    pj = cfg.get("project") or {}
    if isinstance(pj.get("team_size"), int):
        d.setdefault("capacity", {})["team_size"] = pj["team_size"]
    return d


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0], formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out", help="папка прогона <OUT>")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--init", action="store_true", help="записать заготовку data/decisions.json")
    g.add_argument("--check", action="store_true", help="проверить схему data/decisions.json")
    g.add_argument("--list-placeholders", action="store_true", help="все ключи плейсхолдеров с текущими значениями")
    ap.add_argument("--force", action="store_true", help="--init: перезаписать существующий файл")
    ap.add_argument("--json", action="store_true", help="вывод JSON")
    a = ap.parse_args(argv)
    out = Path(a.out).resolve()
    if not (out / "data").is_dir():
        print("ошибка: нет папки %s/data" % out, file=sys.stderr)
        return 2
    path = out / "data" / "decisions.json"
    if a.init:
        if path.exists() and not a.force:
            print("data/decisions.json уже есть — не перезаписываю (--force перезапишет)", file=sys.stderr)
            return 1
        path.write_text(json.dumps(scaffold(out), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("записано %s — заполните ставки, North Star, анти-цели и развилки" % path)
        return 0
    if a.list_placeholders:
        rows = Registry(out).listing()
        if a.json:
            print(json.dumps([{"placeholder": p, "value": v, "source": s} for p, v, s in rows], ensure_ascii=False, indent=2))
        else:
            for p, v, s in rows:
                print("%-34s %s" % (p, v))
            print("всего %d ключей; {rank:P…}/{deprank:P…} — из data/scores.json" % len(rows))
        return 0
    d = load(out)
    if d is None:
        print("нет data/decisions.json (decisions.py <OUT> --init)", file=sys.stderr)
        return 1
    props = load_json(out / "data" / "proposals.json", None)
    pids = {p.get("id") for p in props if isinstance(p, dict)} if isinstance(props, list) else None
    errs, warns = validate(d, pids)
    if a.json:
        print(json.dumps({"ok": not errs, "errors": errs, "warnings": warns}, ensure_ascii=False, indent=2))
    else:
        for e in errs:
            print("ОШИБКА: %s" % e)
        for w in warns:
            print("предупреждение: %s" % w)
        print("итог: ошибок %d, предупреждений %d" % (len(errs), len(warns)))
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
