#!/usr/bin/env python3
"""Конвейер пересборки результатов из данных <OUT> одной командой (фазы 6 и 9).

  build_all.py <OUT> [--only score,charts,html] [--skip pptx,pdf] [--links] [--strict] [--typesafe]

Шаги по порядку (каждый пропускается, если выключен в run-config.formats/scope или нет входных данных/инструмента):
  sources    merge_sources.py         data/sources-*.json (фрагменты агентов) → data/sources.json (если есть фрагменты)
  mocklink   link_mockups.py          proposals[].mockup по индексу макетов и design-refs (если есть макеты)
  registry   check_registry.py        проверка реестра (при --strict ошибка останавливает конвейер)
  score      score.py                 составные показатели, приоритеты, чувствительность
  validate   validate_scores.py       независимый пересчёт
  gapaudit   gap_audit.py --check     research/gap-audit.md и черновики G7 (фаза 5.5; нет файла — SKIP с напоминанием)
  typesafe   typesafe_eval.py         оценка Jev (только с --typesafe или tools.typesafe=on и ключом)
  model      model.py                 юнит-экономика (scope.unit_economics)
  charts     charts.py                SVG-графики
  mockups    node/shoot_mockups.mjs   PNG макетов (нужен playwright)
  assemble   assemble_strategy.py     части разделов → strategy.md (есть build/parts) либо только проверка маркеров и P-id
  method     build_methodology.py     research/methodology.md из данных (рукописный не затирается)
  refsreadme build_design_refs_readme.py  design-refs/README.md (если есть карточки)
  html       build_html.py            интерактивная страница (formats.html; --lite — картинки отдельными файлами)
  smoke      node/smoke_html.mjs      автотест страницы (нужен playwright)
  xlsx       build_xlsx.py            (formats.xlsx)
  deck       build_deck_json.py       колода для pptx/pdf
  pptx       node/build_pptx.mjs      (formats.pptx, нужен pptxgenjs)
  pdf        node/deck_pdf.mjs        (formats.pdf, нужен playwright)
  links      check_links.py           --offline по умолчанию; --links — с сетью
  gitignore  check_gitignore.py       файлы прогона не игнорируются git (если <OUT> внутри репозитория)

Node-модули — по check_env.node_dir (PS_NODE_DIR → run-config tools.node_dir → <OUT>/build/node → ~/.cache/product-strategy/node);
ставит их check_env.py --install-node. Статусы: OK, FAIL, «—» (выключено выбором в опросе, не проблема), SKIP (нет инструмента или данных).
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
    """Папка Node-модулей: общая логика с check_env.py (PS_NODE_DIR → run-config → <OUT>/build/node → ~/.cache/product-strategy/node)."""
    sys.path.insert(0, str(HERE))
    import check_env
    return check_env.node_dir(out)


def has_mod(out, name):
    return (node_dir(out) / "node_modules" / name / "package.json").exists()


def plan(out, cfg, a):
    f, sc, tools = cfg.get("formats", {}), cfg.get("scope", {}), cfg.get("tools", {})
    data = Path(out) / "data"
    py = [sys.executable, "-B"]
    nd = ["--node-dir", str(node_dir(out))]
    node = shutil.which("node")
    have_pw, have_pptx = has_mod(out, "playwright") and node, has_mod(out, "pptxgenjs") and node
    mode = tools.get("typesafe", "auto")
    key = bool(os.environ.get("TYPESAFE_API_KEY"))
    done = (data / "typesafe-jev.json").exists()
    ts = a.typesafe or mode == "on" or (mode == "auto" and key and not done)     # auto = «включить при наличии ключа»
    ts_why = ("выключено выбором (tools.typesafe=off)" if mode == "off" else "нет TYPESAFE_API_KEY" if not key
              else "уже оценено (data/typesafe-jev.json); --typesafe пересчитает")
    html = Path(out) / "deliverables" / "index.html"
    root = Path(out)
    parts = bool(list((root / "build" / "parts").glob("strategy-*.md"))) if (root / "build" / "parts").is_dir() else False
    parts = parts or bool(list((root / "research").glob("strategy-part*.md")))
    has_strategy = (root / "research" / "strategy.md").exists() or parts
    has_mock = (data / "mockups-index.json").exists() or bool(list((root / "mockups" / "concepts").glob("*.html"))) if (root / "mockups" / "concepts").is_dir() else (data / "mockups-index.json").exists()
    has_refs = bool(list((root / "design-refs").glob("*.json"))) if (root / "design-refs").is_dir() else False
    gap_on = (cfg.get("phases") or {}).get("gap_audit", True)
    inside = (cfg.get("output") or {}).get("inside_repo", False)
    lite = ["--lite"] if a.lite else []
    eng = ["--engines", a.engines] if a.engines else []
    reg = ["--demo"] if cfg.get("assumptions") and any("Демо" in x for x in cfg["assumptions"]) else []
    return [
        ("sources", bool(list(data.glob("sources-*.json"))), "нет фрагментов data/sources-*.json", py + [str(HERE / "merge_sources.py"), str(out)]),
        ("mocklink", has_mock and (data / "proposals.json").exists(), "нет макетов", py + [str(HERE / "link_mockups.py"), str(out)]),
        ("registry", (data / "proposals.json").exists(), "нет data/proposals.json", py + [str(HERE / "check_registry.py"), str(out)] + reg),
        ("score", (data / "proposals.json").exists(), "нет реестра", py + [str(HERE / "score.py"), str(out)]),
        ("validate", (data / "proposals.json").exists(), "нет реестра", py + [str(HERE / "validate_scores.py"), str(out)]),
        ("gapaudit", bool(gap_on) and (root / "research" / "gap-audit.md").exists(),
         "выключено выбором (phases.gap_audit=false)" if not gap_on else "нет research/gap-audit.md — фаза 5.5 не выполнена (gap_audit.py → агент-аудитор)",
         py + [str(HERE / "gap_audit.py"), str(out), "--check"]),
        ("typesafe", bool(ts), ts_why, py + [str(HERE / "typesafe_eval.py"), str(out)]),
        ("model", sc.get("unit_economics", True), "выключено выбором (scope.unit_economics=false)", py + [str(HERE / "model.py"), str(out)]),
        ("charts", True, "", py + [str(HERE / "charts.py"), str(out)]),
        ("mockups", bool(have_pw) and (data / "mockups-index.json").exists() or (bool(have_pw) and (Path(out) / "mockups" / "concepts").is_dir()), "нет playwright или макетов (mockups/concepts)",
         ["node", str(HERE / "node" / "shoot_mockups.mjs"), str(out)] + nd),
        ("assemble", has_strategy, "нет research/strategy.md и частей разделов",
         py + [str(HERE / "assemble_strategy.py"), str(out)] + ([] if parts else ["--check"]) + (["--lenient"] if not a.strict else [])),
        ("method", (data / "proposals.json").exists(), "нет реестра", py + [str(HERE / "build_methodology.py"), str(out)]),
        ("refsreadme", has_refs, "нет карточек design-refs/*.json", py + [str(HERE / "build_design_refs_readme.py"), str(out)]),
        ("html", f.get("html", True), "выключено выбором (formats.html=false)", py + [str(HERE / "build_html.py"), str(out)] + lite),
        ("smoke", bool(have_pw) and f.get("html", True), "выключено выбором (html)" if not f.get("html", True) else "нет playwright (check_env.py --install-node)",
         ["node", str(HERE / "node" / "smoke_html.mjs"), str(html)] + nd + eng),
        ("xlsx", f.get("xlsx", True), "выключено выбором (formats.xlsx=false)", py + [str(HERE / "build_xlsx.py"), str(out)]),
        ("deck", f.get("pptx", True) or f.get("pdf", True), "выключено выбором (pptx и pdf)", py + [str(HERE / "build_deck_json.py"), str(out)]),
        ("pptx", bool(have_pptx) and f.get("pptx", True), "выключено выбором (formats.pptx=false)" if not f.get("pptx", True) else "нет pptxgenjs (check_env.py --install-node)",
         ["node", str(HERE / "node" / "build_pptx.mjs"), str(out)] + nd),
        ("pdf", bool(have_pw) and f.get("pdf", True), "выключено выбором (formats.pdf=false)" if not f.get("pdf", True) else "нет playwright (check_env.py --install-node)", ["node", str(HERE / "node" / "deck_pdf.mjs"), str(out)] + nd),
        ("links", True, "", py + [str(HERE / "check_links.py"), str(out)] + ([] if a.links else ["--offline"])),
        ("gitignore", bool(inside), "выключено выбором (результат вне репозитория)", py + [str(HERE / "check_gitignore.py"), str(out)]),
    ]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("out")
    ap.add_argument("--only", default="")
    ap.add_argument("--skip", default="")
    ap.add_argument("--links", action="store_true", help="проверять ссылки с сетью")
    ap.add_argument("--strict", action="store_true", help="ошибка check_registry/validate останавливает конвейер")
    ap.add_argument("--typesafe", action="store_true", help="запустить typesafe_eval.py принудительно")
    ap.add_argument("--lite", action="store_true", help="страница без встроенных картинок (assets рядом; цель ≤ 8 МБ)")
    ap.add_argument("--engines", help="движки smoke-теста: chromium,webkit (по умолчанию все доступные)")
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
            results.append((name, "—", "по --only/--skip", 0))
            continue
        if not enabled:
            results.append((name, "—" if why.startswith("выключено выбором") else "SKIP", why, 0))
            continue
        script = Path(cmd[2] if cmd[0] == sys.executable else cmd[1])        # (python -B script) или (node script)
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
            if a.strict and name in ("registry", "validate", "assemble"):
                break
    w = max(len(n) for n, *_ in results)
    print("%-*s  %-4s  %6s  %s" % (w, "шаг", "итог", "сек", "последняя строка / причина"))
    for n, st, msg, dt in results:
        print("%-*s  %-4s  %6.1f  %s" % (w, n, st, dt, msg))
    failed = [n for n, st, *_ in results if st == "FAIL"]
    skipped = [n for n, st, *_ in results if st == "SKIP"]
    off = [n for n, st, *_ in results if st == "—"]
    print("\nИтог: %s" % ("всё собрано" if not failed else "упали шаги: " + ", ".join(failed))
          + ("; пропущено из-за недостающего: " + ", ".join(skipped) if skipped else "")
          + ("; выключено выбором (не ошибка): " + ", ".join(off) if off else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
