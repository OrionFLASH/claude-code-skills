#!/usr/bin/env python3
"""Конвейер пересборки результатов из данных <OUT> одной командой (фазы 6 и 9).

  build_all.py <OUT> [--only score,charts,html] [--skip pptx,pdf] [--links] [--strict] [--typesafe]

Шаги по порядку (каждый пропускается, если выключен в run-config.formats/scope или нет входных данных/инструмента):
  registry   check_registry.py        проверка реестра (при --strict ошибка останавливает конвейер)
  score      score.py                 составные показатели, приоритеты, чувствительность
  validate   validate_scores.py       независимый пересчёт
  typesafe   typesafe_eval.py         оценка Jev (только с --typesafe или tools.typesafe=on и ключом)
  model      model.py                 юнит-экономика (scope.unit_economics)
  charts     charts.py                SVG-графики
  mockups    node/shoot_mockups.mjs   PNG макетов (нужен playwright)
  html       build_html.py            интерактивная страница (formats.html)
  smoke      node/smoke_html.mjs      автотест страницы (нужен playwright)
  xlsx       build_xlsx.py            (formats.xlsx)
  deck       build_deck_json.py       колода для pptx/pdf
  pptx       node/build_pptx.mjs      (formats.pptx, нужен pptxgenjs)
  pdf        node/deck_pdf.mjs        (formats.pdf, нужен playwright)
  links      check_links.py           --offline по умолчанию; --links — с сетью

Node-модули — из env PS_NODE_DIR или <OUT>/build/node (ставит check_env.py --install-node <OUT>).
Итог — таблица шагов (OK / SKIP / FAIL) и код 1, если что-то упало. Только стандартная библиотека.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
STEPS = ["registry", "score", "validate", "typesafe", "model", "charts", "mockups", "html", "smoke", "xlsx", "deck", "pptx", "pdf", "links"]


def node_dir(out):
    return Path(os.environ["PS_NODE_DIR"]).expanduser() if os.environ.get("PS_NODE_DIR") else Path(out) / "build" / "node"


def has_mod(out, name):
    return (node_dir(out) / "node_modules" / name / "package.json").exists()


def plan(out, cfg, a):
    f, sc, tools = cfg.get("formats", {}), cfg.get("scope", {}), cfg.get("tools", {})
    data = Path(out) / "data"
    py = [sys.executable, "-B"]
    nd = ["--node-dir", str(node_dir(out))]
    node = shutil.which("node")
    have_pw, have_pptx = has_mod(out, "playwright") and node, has_mod(out, "pptxgenjs") and node
    ts = a.typesafe or (tools.get("typesafe") == "on") or (tools.get("typesafe") == "auto" and os.environ.get("TYPESAFE_API_KEY")
                                                         and not (data / "typesafe-jev.json").exists())
    html = Path(out) / "deliverables" / "index.html"
    reg = ["--demo"] if cfg.get("assumptions") and any("Демо" in x for x in cfg["assumptions"]) else []
    return [
        ("registry", (data / "proposals.json").exists(), "нет data/proposals.json", py + [str(HERE / "check_registry.py"), str(out)] + reg),
        ("score", (data / "proposals.json").exists(), "нет реестра", py + [str(HERE / "score.py"), str(out)]),
        ("validate", (data / "proposals.json").exists(), "нет реестра", py + [str(HERE / "validate_scores.py"), str(out)]),
        ("typesafe", bool(ts), "выключено (tools.typesafe) или нет TYPESAFE_API_KEY", py + [str(HERE / "typesafe_eval.py"), str(out)]),
        ("model", sc.get("unit_economics", True), "scope.unit_economics=false", py + [str(HERE / "model.py"), str(out)]),
        ("charts", True, "", py + [str(HERE / "charts.py"), str(out)]),
        ("mockups", bool(have_pw) and (data / "mockups-index.json").exists(), "нет playwright или mockups-index.json",
         ["node", str(HERE / "node" / "shoot_mockups.mjs"), str(out)] + nd),
        ("html", f.get("html", True), "formats.html=false", py + [str(HERE / "build_html.py"), str(out)]),
        ("smoke", bool(have_pw) and f.get("html", True), "нет playwright или html выключен",
         ["node", str(HERE / "node" / "smoke_html.mjs"), str(html)] + nd),
        ("xlsx", f.get("xlsx", True), "formats.xlsx=false", py + [str(HERE / "build_xlsx.py"), str(out)]),
        ("deck", f.get("pptx", True) or f.get("pdf", True), "pptx и pdf выключены", py + [str(HERE / "build_deck_json.py"), str(out)]),
        ("pptx", bool(have_pptx) and f.get("pptx", True), "нет pptxgenjs или pptx выключен",
         ["node", str(HERE / "node" / "build_pptx.mjs"), str(out)] + nd),
        ("pdf", bool(have_pw) and f.get("pdf", True), "нет playwright или pdf выключен", ["node", str(HERE / "node" / "deck_pdf.mjs"), str(out)] + nd),
        ("links", True, "", py + [str(HERE / "check_links.py"), str(out)] + ([] if a.links else ["--offline"])),
    ]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("out")
    ap.add_argument("--only", default="")
    ap.add_argument("--skip", default="")
    ap.add_argument("--links", action="store_true", help="проверять ссылки с сетью")
    ap.add_argument("--strict", action="store_true", help="ошибка check_registry/validate останавливает конвейер")
    ap.add_argument("--typesafe", action="store_true", help="запустить typesafe_eval.py принудительно")
    a = ap.parse_args(argv)
    out = Path(a.out).resolve()
    cfgp = out / "build" / "run-config.json"
    cfg = json.loads(cfgp.read_text(encoding="utf-8")) if cfgp.exists() else {}
    only = {s for s in a.only.split(",") if s}
    skip = {s for s in a.skip.split(",") if s}
    env = dict(os.environ, PS_NODE_DIR=str(node_dir(out)))
    results = []
    for name, enabled, why, cmd in plan(out, cfg, a):
        if (only and name not in only) or name in skip:
            results.append((name, "SKIP", "--only/--skip", 0))
            continue
        if not enabled:
            results.append((name, "SKIP", why, 0))
            continue
        script = Path(cmd[2] if cmd[0] == sys.executable else cmd[1])
        if not script.exists():
            results.append((name, "SKIP", "нет скрипта %s" % script.name, 0))
            continue
        t0 = time.time()
        r = subprocess.run(cmd, env=env, capture_output=True, text=True)
        dt = time.time() - t0
        tail = ((r.stdout or "") + (r.stderr or "")).strip().splitlines()
        results.append((name, "OK" if r.returncode == 0 else "FAIL", tail[-1][:120] if tail else "", dt))
        if r.returncode:
            sys.stderr.write("\n--- %s (код %d) ---\n%s\n" % (name, r.returncode, "\n".join(tail[-25:])))
            if a.strict and name in ("registry", "validate"):
                break
    w = max(len(n) for n, *_ in results)
    print("%-*s  %-4s  %6s  %s" % (w, "шаг", "итог", "сек", "последняя строка / причина"))
    for n, st, msg, dt in results:
        print("%-*s  %-4s  %6.1f  %s" % (w, n, st, dt, msg))
    failed = [n for n, st, *_ in results if st == "FAIL"]
    print("\nИтог: %s" % ("всё собрано" if not failed else "упали шаги: " + ", ".join(failed)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
