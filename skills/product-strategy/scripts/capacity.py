#!/usr/bin/env python3
"""Единая ёмкость проекта: один расчёт для опроса, модели, факт-листа и брифов (FB-028).

  capacity(cfg, months) -> {hours, dev_hours, dev_days, day_hours, hours_per_week, dev_share, source, line}

Параметры берутся из run-config.json → project.capacity {hours_per_week, dev_share, day_hours, source};
если их нет — из ответа опроса idea.facets.hours_week, затем из значений по умолчанию (10 ч/нед, 70 % на разработку,
8-часовой день). Другого определения «рабочего дня» в скиле быть не должно: все скрипты и брифы берут строку `line`.
Только стандартная библиотека. CLI: capacity.py <OUT> [--months 6]
"""
import json
import sys
from pathlib import Path

DEFAULTS = {"hours_per_week": 10.0, "dev_share": 0.7, "day_hours": 8.0}
WEEKS_PER_MONTH = 52 / 12.0


def _num(v, d):
    try:
        x = float(v)
        return x if x > 0 else d
    except (TypeError, ValueError):
        return d


def params(cfg):
    """Параметры ёмкости из конфига (без вычислений) + откуда они взяты."""
    cfg = cfg or {}
    cap = ((cfg.get("project") or {}).get("capacity")) or {}
    facets = ((cfg.get("idea") or {}).get("facets")) or {}
    src = cap.get("source")
    hw = cap.get("hours_per_week")
    if hw is None and facets.get("hours_week"):
        hw, src = facets.get("hours_week"), src or "ответ опроса (часов в неделю)"
    p = {
        "hours_per_week": _num(hw, DEFAULTS["hours_per_week"]),
        "dev_share": min(1.0, _num(cap.get("dev_share"), DEFAULTS["dev_share"])),
        "day_hours": _num(cap.get("day_hours"), DEFAULTS["day_hours"]),
    }
    p["source"] = src or ("project.capacity" if cap else "значения по умолчанию")
    return p


def capacity(cfg, months=6):
    p = params(cfg)
    weeks = float(months) * WEEKS_PER_MONTH
    hours = p["hours_per_week"] * weeks
    dev_hours = hours * p["dev_share"]
    dev_days = dev_hours / p["day_hours"]
    out = dict(p, months=months, hours=round(hours, 1), dev_hours=round(dev_hours, 1), dev_days=round(dev_days, 1))
    out["line"] = ("%g ч/нед × %d %% на разработку = %.1f ч/нед ≈ %.1f дня по %g ч; за %g мес. ≈ %.1f дн. разработки (%s)" % (
        p["hours_per_week"], round(p["dev_share"] * 100), p["hours_per_week"] * p["dev_share"],
        p["hours_per_week"] * p["dev_share"] / p["day_hours"], p["day_hours"], months, dev_days, p["source"]))
    return out


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
    months = 6.0
    if "--months" in a:
        i = a.index("--months")
        months = _num(a[i + 1], 6.0)
        del a[i:i + 2]
    cfg = load_cfg(a[0]) if a else {}
    print(json.dumps(capacity(cfg, months), ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
