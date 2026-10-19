#!/usr/bin/env python3
"""Единая ёмкость проекта: один расчёт для опроса, модели, факт-листа, плана и брифов (FB-028, SM 6.1).

  capacity(cfg, months) -> {hours, dev_hours, dev_days, day_hours, hours_per_week, dev_share, team_size,
                            hours_month, dev_hours_month, dev_days_month, source, line, …}

Параметры берутся по приоритету:
  1. run-config.json → project.capacity {hours_per_week, dev_share, day_hours, team_size, source};
  2. ответ опроса idea.facets.hours_week (часов в неделю на человека);
  3. project.capacity_days_month — число (человеко-дней разработки в месяц на всю команду, режим стратегии по репозиторию):
     пересчитывается в часы с dev_share = 1 (эти дни уже «чистая разработка»);
  4. значения по умолчанию: 10 ч/нед на человека, 70 % на разработку, 8-часовой день.
team_size — project.capacity.team_size, иначе project.team_size, иначе 1; hours_per_week — на человека.
Единственная величина «часов в рабочем дне» — project.capacity.day_hours (поле project.hours_in_day не вводится).
Другого определения «рабочего дня» в скиле быть не должно: скрипты берут числа отсюда, брифы и тексты — строку `line`.
Только стандартная библиотека. CLI: capacity.py <OUT> [--months 6] [--line]
"""
import json
import re
import sys
from pathlib import Path

DEFAULTS = {"hours_per_week": 10.0, "dev_share": 0.7, "day_hours": 8.0}
WEEKS_PER_MONTH = 52 / 12.0
# формулировки «рабочего дня» в тексте: «8-часовой день», «день по 6 ч», «6 ч в день», «рабочий день 8 ч»
DAY_DEF_RE = re.compile(
    r"(\d+(?:[.,]\d+)?)[\s -]*(?:час\w*|ч\.?)[\s ]*(?:рабоч\w+[\s ]+)?(?:в[\s ]+день|день)\b"
    r"|(?:день|дн[яеи]\w*)[\s ]+по[\s ]+(\d+(?:[.,]\d+)?)[\s ]*(?:час\w*|ч\b)"
    r"|рабоч\w+[\s ]+(?:день|дн\w*)[\s ]*(?:[—–:=-]|в|по)?[\s ]*(\d+(?:[.,]\d+)?)[\s ]*(?:час\w*|ч\b)", re.I)


def _num(v, d):
    try:
        x = float(v)
        return x if x > 0 else d
    except (TypeError, ValueError):
        return d


def _ru(x, nd=None):
    """Число по-русски: 10.5 → «10,5», 8.0 → «8»."""
    x = round(float(x), nd if nd is not None else 2)
    s = ("%d" % x) if float(x).is_integer() else ("%.*f" % (nd if nd is not None else 2, x)).rstrip("0").rstrip(".")
    return s.replace(".", ",")


def _team(cfg, cap):
    for v in (cap.get("team_size"), ((cfg.get("project") or {}).get("team_size"))):
        try:
            if v is not None and not isinstance(v, bool) and int(v) >= 1:
                return int(v)
        except (TypeError, ValueError):
            continue
    return 1


def params(cfg):
    """Параметры ёмкости из конфига (без вычислений) + откуда они взяты."""
    cfg = cfg or {}
    pj = cfg.get("project") or {}
    cap = pj.get("capacity") if isinstance(pj.get("capacity"), dict) else {}
    facets = ((cfg.get("idea") or {}).get("facets")) or {}
    team = _team(cfg, cap)
    src = cap.get("source")
    hw = cap.get("hours_per_week")
    dev_share = cap.get("dev_share")
    day_hours = _num(cap.get("day_hours"), DEFAULTS["day_hours"])
    if hw is None and facets.get("hours_week"):
        hw, src = facets.get("hours_week"), src or "ответ опроса (часов в неделю)"
    cdm = pj.get("capacity_days_month")
    if hw is None and isinstance(cdm, (int, float)) and not isinstance(cdm, bool) and cdm > 0:
        hw = float(cdm) * day_hours / WEEKS_PER_MONTH / team
        dev_share = 1.0 if dev_share is None else dev_share
        src = src or "project.capacity_days_month (%g чел.-дн./мес.)" % cdm
    p = {
        "hours_per_week": round(_num(hw, DEFAULTS["hours_per_week"]), 2),
        "dev_share": min(1.0, _num(dev_share, DEFAULTS["dev_share"])),
        "day_hours": day_hours,
        "team_size": team,
    }
    p["source"] = src or ("project.capacity" if cap else "значения по умолчанию")
    p["explicit"] = bool(cap) or bool(facets.get("hours_week")) or p["source"].startswith("project.capacity_days_month")
    return p


def capacity(cfg, months=6):
    p = params(cfg)
    weeks = float(months) * WEEKS_PER_MONTH
    team = p["team_size"]
    hours = p["hours_per_week"] * team * weeks
    dev_hours = hours * p["dev_share"]
    dev_days = dev_hours / p["day_hours"]
    hm = p["hours_per_week"] * team * WEEKS_PER_MONTH
    out = dict(p, months=months, hours=round(hours, 1), dev_hours=round(dev_hours, 1), dev_days=round(dev_days, 1),
               hours_month=round(hm, 1), dev_hours_month=round(hm * p["dev_share"], 1),
               dev_days_month=round(hm * p["dev_share"] / p["day_hours"], 2))
    who = "" if team == 1 else " × %d чел." % team
    out["line"] = "%s ч/нед%s × %d %% на разработку = %s ч/нед ≈ %s дня по %s ч; за %s мес. ≈ %s дн. разработки (%s)" % (
        _ru(p["hours_per_week"]), who, round(p["dev_share"] * 100), _ru(p["hours_per_week"] * team * p["dev_share"], 1),
        _ru(p["hours_per_week"] * team * p["dev_share"] / p["day_hours"], 1), _ru(p["day_hours"]), _ru(months), _ru(dev_days, 1), p["source"])
    return out


def day_definitions(text):
    """Все упоминания «часов в рабочем дне» в тексте → [(значение, фрагмент)] (для проверки «одного определения дня»)."""
    res = []
    for m in DAY_DEF_RE.finditer(text or ""):
        raw = next(g for g in m.groups() if g)
        try:
            v = float(raw.replace(",", "."))
        except ValueError:
            continue
        if 1 <= v <= 16:
            res.append((v, m.group(0)))
    return res


def load_cfg(out_dir):
    for rel in ("build/run-config.json", "run-config.json"):
        f = Path(out_dir) / rel
        if f.is_file():
            try:
                return json.loads(f.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                return {}
    return {}


def main(argv=None):
    a = list(argv if argv is not None else sys.argv[1:])
    months = None
    if "--months" in a:
        i = a.index("--months")
        months = _num(a[i + 1], 6.0)
        del a[i:i + 2]
    only_line = "--line" in a
    a = [x for x in a if x != "--line"]
    cfg = load_cfg(a[0]) if a else {}
    if months is None:
        months = _num(((cfg.get("strategy") or {}).get("horizon_months")), 6.0)
    c = capacity(cfg, months)
    print(c["line"] if only_line else json.dumps(c, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
