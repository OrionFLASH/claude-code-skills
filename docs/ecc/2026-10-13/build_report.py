#!/usr/bin/env python3
"""Сборка страницы «Разбор ECC» из data/*.json → index.html + assets/ (сайт из файлов, офлайн).

  build_report.py [--data data] [--out .]
Читает inventory.json, runtime.json, security.json, graph.json, usage.json, web.json (и overview.json — общий вывод).
Только стандартная библиотека.
"""
import argparse, hashlib, json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def load(p, default=None):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(HERE / "data"))
    ap.add_argument("--out", default=str(HERE))
    a = ap.parse_args(argv)
    data, out = Path(a.data), Path(a.out)
    rep = {"meta": {"title": "Разбор ECC (everything-claude-code)", "date": "2026-10-13", "commit": "b92f181b3b748d1abbc2afd94af6aa7d8c8fca29", "repo": "https://github.com/affaan-m/ECC"}}
    for k in ("inventory", "runtime", "security", "graph", "usage", "web", "overview", "setup", "mechanics", "integration"):
        rep[k] = load(data / (k + ".json"), None)
    (out / "assets").mkdir(parents=True, exist_ok=True)
    datajs = "window.ECC = " + json.dumps(rep, ensure_ascii=False) + ";\n"
    (out / "assets" / "data.js").write_text(datajs, encoding="utf-8")
    for n in ("app.css", "app.js"):
        (out / "assets" / n).write_text((HERE / "template" / n).read_text(encoding="utf-8"), encoding="utf-8")
    v = hashlib.sha1((datajs + (HERE / "template" / "app.js").read_text(encoding="utf-8")).encode()).hexdigest()[:8]
    (out / "index.html").write_text((HERE / "template" / "index.html").read_text(encoding="utf-8").replace("{V}", v), encoding="utf-8")
    have = [k for k in rep if k != "meta" and rep[k]]
    print("отчёт: %s (данные: %s; data.js %.0f КБ)" % (out / "index.html", ", ".join(have), len(datajs.encode()) / 1024))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
