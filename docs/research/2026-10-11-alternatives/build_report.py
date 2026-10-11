#!/usr/bin/env python3
"""Сборка веб-отчёта «Можно ли заменить скилы сторонними» из data/*.json.

  build_report.py [--data data] [--out .]

Читает: data/site-qa-audit.json, android-qa-audit.json, typesafe-triage.json, product-strategy.json, ecosystems.json
и необязательный data/overview.json (общий вывод, план действий, ручные заметки). Пишет сайт из файлов:
index.html + assets/app.css, assets/app.js, assets/data.js (window.REPORT). Открывается офлайн двойным кликом,
внешних запросов нет (ссылки — обычные <a target=_blank>). Только стандартная библиотека.
"""
import argparse
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILLS = [
    ("site-qa-audit", "site-qa-audit", "QA сайтов и веб-приложений"),
    ("android-qa-audit", "android-qa-audit", "QA Android-приложений"),
    ("typesafe-triage", "typesafe-triage (Triangle)", "Выбор модели и effort"),
    ("product-strategy", "product-strategy + product-concept", "Стратегия и концепция продукта"),
]


def load(p, default=None):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def covered(c):
    s = (c.get("coverage") or {})
    return s


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(HERE / "data"))
    ap.add_argument("--out", default=str(HERE))
    a = ap.parse_args(argv)
    data, out = Path(a.data), Path(a.out)
    rep = {"meta": {"title": "Можно ли заменить свои скилы сторонними?", "date": "2026-10-11"}, "skills": [], "overview": load(data / "overview.json", {}) or {},
           "ecosystems": load(data / "ecosystems.json", None)}
    for key, name, sub in SKILLS:
        d = load(data / (key + ".json"), None)
        if d:
            d["key"], d["name"], d["subtitle"] = key, name, sub
            rep["skills"].append(d)
    # единый список источников
    seen, srcs = set(), []
    for blk in rep["skills"] + ([rep["ecosystems"]] if rep["ecosystems"] else []):
        for s in blk.get("sources") or []:
            u = s.get("url")
            if u and u not in seen:
                seen.add(u)
                srcs.append(dict(s, area=blk.get("skill") or "ecosystems"))
    rep["sources"] = srcs
    (out / "assets").mkdir(parents=True, exist_ok=True)
    datajs = "window.REPORT = " + json.dumps(rep, ensure_ascii=False) + ";\n"
    (out / "assets" / "data.js").write_text(datajs, encoding="utf-8")
    for n in ("app.css", "app.js"):
        src = HERE / "template" / n
        (out / "assets" / n).write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    v = hashlib.sha1((datajs + (HERE / "template" / "app.js").read_text(encoding="utf-8")).encode()).hexdigest()[:8]
    html = (HERE / "template" / "index.html").read_text(encoding="utf-8").replace("{V}", v)
    (out / "index.html").write_text(html, encoding="utf-8")
    print("отчёт: %s (скилов %d, источников %d, data.js %.0f КБ)" % (out / "index.html", len(rep["skills"]), len(srcs), len(datajs) / 1024))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
