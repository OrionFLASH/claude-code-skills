#!/usr/bin/env python3
"""Конвейер пересборки результатов из данных <OUT> одной командой (фазы 6 и 9).

  build_all.py <OUT> [--only score,charts,html] [--skip pptx,pdf] [--links] [--strict] [--accept-known shots,phases]
               [--typesafe] [--single | --lite] [--zip] [--shoot]
  build_all.py <OUT> --preview        черновик (FB-057, SM 10.3): только графики и страница → build/preview/index.html с баннером
                                      «черновик: готовы фазы …», без строгих ворот; deliverables/ не трогается; открыть в
                                      браузере владельца — только по его просьбе (references/safety.md, §8)

Шаги по порядку (каждый пропускается, если выключен в run-config.formats/scope или нет входных данных/инструмента):
  dossier    concept_dossier.py       режим идеи (mode: concept): досье, data/idea.json, план поиска, затравки (идемпотентно)
  viability  typesafe_concept.py      режим идеи: предпроверка жизнеспособности, если data/typesafe-concept.json ещё нет
  sources    merge_sources.py         data/sources-*.json (фрагменты агентов) → data/sources.json (если есть фрагменты)
  mocklink   link_mockups.py          proposals[].mockup по индексу макетов и design-refs (если есть макеты)
  shots      (встроено)               скриншоты конкурентов (FB-012): карточки с http-URL без shot и без shot_blocked →
                                      предупреждение «у N из M конкурентов нет скриншота»; --strict — провал; --shoot (и есть
                                      playwright) — сначала снять: node/shoot_competitors.mjs
  registry   check_registry.py        проверка реестра (при --strict ошибка останавливает конвейер)
  score      score.py                 составные показатели, приоритеты, чувствительность
  validate   validate_scores.py       независимый пересчёт
  gapaudit   gap_audit.py --check     research/gap-audit.md и черновики G7 (фаза 5.5; нет файла — SKIP с напоминанием)
  typesafe   typesafe_eval.py         оценка Jev (только с --typesafe или tools.typesafe=on и ключом)
  model      model.py                 юнит-экономика (scope.unit_economics)
  flowsmerge (встроено)               части схем build/parts/flows-*.json → data/flows.json, проверка дублей ключей (FB-006)
  charts     charts.py                SVG-графики (сам проверяет пояснения графиков — charts --check-meta)
  flowcheck  node/check_flow.mjs      пересечения блоков и подписей в схемах (есть data/flows.json и playwright) → data/flows-check.json
  mockups    node/shoot_mockups.mjs   PNG макетов (нужен playwright)
  assemble   assemble_strategy.py     части разделов → strategy.md (есть build/parts) либо только проверка маркеров и P-id
  consistency plan_baseline.py --check  даты и числа вех против data/plan-baseline.json (FB-046; есть baseline): предупреждение,
                                      в --strict — провал
  method     build_methodology.py     research/methodology.md из данных (рукописный не затирается)
  handoff    handoff.py                    deliverables/CLAUDE_CODE_TASKS.md (если handoff.enabled и состав уже выбран)
  refsreadme build_design_refs_readme.py  design-refs/README.md (если есть карточки)
  html       build_html.py            интерактивная страница (formats.html). По умолчанию — сайт из нескольких файлов (режим site):
                                      deliverables/index.html + assets/ + data/, открывается двойным кликом (file://); --single — прежний
                                      автономный файл; --lite — single с картинками в assets/; --zip — ещё deliverables/strategy-site.zip (только site);
                                      с --strict сборщик падает на ссылках панели графиков без цели на странице (кроме демо-прогона)
  smoke      node/smoke_html.mjs      автотест страницы или сайта (нужен playwright; печатает «проверено на: …» по движкам)
  xlsx       build_xlsx.py            (formats.xlsx)
  deck       build_deck_json.py       колода для pptx/pdf
  pptx       node/build_pptx.mjs      (formats.pptx, нужен pptxgenjs)
  pdf        node/deck_pdf.mjs        (formats.pdf, нужен playwright)
  pdfcheck   (встроено)               PDF (FB-018): «PDF: N страниц, пустых X, обрезанных Y, превью: build/pdf-preview/» — страницы
                                      по PDF (пустые — без текста и картинок), обрезка и превью первых/случайных слайдов — по
                                      build/deck.html в Chromium (если есть playwright)
  report     report.py --if-missing   каркас deliverables/REPORT.md из данных (если отчёта ещё нет; FB-016)
  readme     report.py --readme       deliverables/README.md по шаблону (правленный вручную не затирается)
  disclosure intake.py disclosure-check  нет ли упоминаний автоматизации в deliverables/ (только при run-config.disclosure ≠ full)
  links      check_links.py           --offline по умолчанию; --links — с сетью
  gitignore  check_gitignore.py       файлы прогона не игнорируются git (если <OUT> внутри репозитория)
  track      strategy_track.py check  сверка с репозиторием и GitHub → data/progress.json (только с --track; нужен gh для issues;
                                      в режиме идеи не выполняется — продукта и репозитория ещё нет)
После шагов полного прогона: фазы отмечаются по артефактам (init_run.py --sync, FB-015) и печатается таблица «ворот полноты»
(FB-058) «проверка → статус → что сделать»: скриншоты, фазы, материалы владельца, fact-check применён, согласованность с
baseline, интерактивность (smoke), вопросы запроса, REPORT.md, учёт агентов (режим идеи), PDF, выбор направления дизайна,
пересмотр идеи. В --strict любое «нет» — провал (кроме демо-прогона); осознанное исключение — --accept-known <код,…>
(записывается в build-all-last.json и в REPORT, раздел 19). Таблица сохраняется в build/build-all-last.json → completeness.

Node-модули — по check_env.node_dir (PS_NODE_DIR → run-config tools.node_dir → <OUT>/build/node → ~/.cache/product-strategy/node);
ставит их check_env.py --install-node. Статусы: OK, WARN (предупреждение, не провал), FAIL, «—» (выключено выбором в опросе или
режимом идеи, не проблема), «н/п» (шаг не нужен: нет его входов, например частей схем), SKIP (нет инструмента или данных),
«·» — шаг не запускался в этом вызове (--only/--skip).
Итог — таблица шагов и код 1, если что-то упало. Полный прогон (без --only) сохраняет итог в
build/build-all-last.json; частичный запуск (--only) пишет «частичный запуск» и печатает рядом итог последнего полного прогона —
«всё собрано» после --only не означает, что собрано всё (A-1.12e). Только стандартная библиотека.
"""
import argparse
import json
import os
import random
import re
import shutil
import subprocess
import sys
import time
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
STEPS = ["dossier", "viability", "registry", "score", "validate", "typesafe", "model", "charts", "flowcheck", "mockups", "handoff", "html", "smoke",
         "xlsx", "deck", "pptx", "pdf", "disclosure", "links"]
LAST = "build-all-last.json"
WARN_STEPS = {"shots", "consistency", "pdfcheck"}           # код 1 — предупреждение; в --strict (не демо) — провал
ACCEPT_CODES = ("shots", "phases", "owner_materials", "fact_check", "consistency", "interactivity", "request_questions", "report",
                "agents", "pdf", "design_choice", "pivot", "market")
MARKET_DIRS = [("communities", "data/communities.json", "сообщества"), ("keywords", "data/keywords.json", "поисковые запросы"),
               ("events", "data/events.json", "события"), ("market", "research/market.md", "синтез рынка")]


def node_dir(out):
    """Папка Node-модулей: общая логика с check_env.py (PS_NODE_DIR → run-config → <OUT>/build/node → ~/.cache/product-strategy/node)."""
    import check_env
    return check_env.node_dir(out)


def has_mod(out, name):
    return (node_dir(out) / "node_modules" / name / "package.json").exists()


def jload(p, default=None):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def is_demo(cfg):
    return bool(cfg.get("assumptions")) and any("Демо" in str(x) for x in cfg["assumptions"])


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
    if a.single and a.lite:
        raise SystemExit("--single и --lite взаимоисключающие")
    mode = ["--single"] if a.single else ["--lite"] if a.lite else []        # без флагов build_html.py собирает сайт (site)
    if a.zip:
        if mode:
            print("--zip: архив собирается только в режиме site (без --single/--lite) — пропущено", file=sys.stderr)
        else:
            mode = ["--zip"]
    eng = ["--engines", a.engines] if a.engines else []
    reg = ["--demo"] if is_demo(cfg) else []
    track = ["--no-write-strategy"] if not a.strict else []
    concept = cfg.get("mode") == "concept"
    # --strict: ссылки панели графиков без цели — ошибка сборки; демо-прогон (make_demo: разделы стратегии неполные
    # намеренно) — как check_registry --demo, без строгости
    strict_html = ["--strict"] if a.strict and not reg else []
    flows = (data / "flows.json").exists()
    flow_parts = sorted((root / "build" / "parts").glob("flows-*.json")) if (root / "build" / "parts").is_dir() else []
    disclosure = str(cfg.get("disclosure") or "full")
    me = str(HERE / "build_all.py")
    comps = (data / "competitors.json").exists() and sc.get("competitors", True) is not False
    shoot = ["--shoot"] if getattr(a, "shoot", False) else []
    baseline = (data / "plan-baseline.json").exists()
    steps = [   # шаги режима идеи (в обычном режиме их нет в таблице)
        ("dossier", True, "", py + [str(HERE / "concept_dossier.py"), str(out)]),
        ("viability", not (data / "typesafe-concept.json").exists(), "уже оценено (data/typesafe-concept.json)",
         py + [str(HERE / "typesafe_concept.py"), str(out)]),
    ] if concept else []
    return steps + [
        ("track", bool(a.track) and not concept,
         "режим идеи: продукта и репозитория ещё нет — отслеживать нечего" if concept else "выключено выбором (нужен флаг --track)",
         py + [str(HERE / "strategy_track.py"), "check", str(out)] + track),
        ("sources", bool(list(data.glob("sources-*.json"))), "нет фрагментов data/sources-*.json", py + [str(HERE / "merge_sources.py"), str(out)]),
        ("mocklink", has_mock and (data / "proposals.json").exists(), "нет макетов", py + [str(HERE / "link_mockups.py"), str(out)]),
        ("shots", comps, "выключено выбором (scope.competitors=false)" if sc.get("competitors", True) is False else "нет data/competitors.json",
         py + [me, str(out), "--check-shots"] + shoot),
        ("registry", (data / "proposals.json").exists(), "нет data/proposals.json", py + [str(HERE / "check_registry.py"), str(out)] + reg),
        ("score", (data / "proposals.json").exists(), "нет реестра", py + [str(HERE / "score.py"), str(out)]),
        ("validate", (data / "proposals.json").exists(), "нет реестра", py + [str(HERE / "validate_scores.py"), str(out)]),
        ("gapaudit", bool(gap_on) and (root / "research" / "gap-audit.md").exists(),
         "выключено выбором (phases.gap_audit=false)" if not gap_on else "нет research/gap-audit.md — фаза 5.5 не выполнена (gap_audit.py → агент-аудитор)",
         py + [str(HERE / "gap_audit.py"), str(out), "--check"]),
        ("typesafe", bool(ts), ts_why, py + [str(HERE / "typesafe_eval.py"), str(out)]),
        ("model", sc.get("unit_economics", True), "выключено выбором (scope.unit_economics=false)", py + [str(HERE / "model.py"), str(out)]),
        ("flowsmerge", bool(flow_parts), "не нужно: нет частей build/parts/flows-*.json", py + [me, str(out), "--merge-flows"]),
        ("charts", True, "", py + [str(HERE / "charts.py"), str(out)]),
        ("flowcheck", (flows or bool(flow_parts)) and bool(have_pw), "нет схем data/flows.json" if not (flows or flow_parts) else "нет playwright (check_env.py --install-node)",
         ["node", str(HERE / "node" / "check_flow.mjs"), str(out)] + nd),
        ("mockups", bool(have_pw) and (data / "mockups-index.json").exists() or (bool(have_pw) and (Path(out) / "mockups" / "concepts").is_dir()), "нет playwright или макетов (mockups/concepts)",
         ["node", str(HERE / "node" / "shoot_mockups.mjs"), str(out)] + nd),
        ("assemble", has_strategy, "нет research/strategy.md и частей разделов",
         py + [str(HERE / "assemble_strategy.py"), str(out)] + ([] if parts else ["--check"]) + (["--lenient"] if not a.strict else [])),
        ("consistency", baseline and (HERE / "plan_baseline.py").exists(),
         ("нет data/plan-baseline.json (plan_baseline.py <OUT> — до авторов разделов)" if concept else "не нужно: нет data/plan-baseline.json")
         if not baseline else "нет plan_baseline.py",
         py + [str(HERE / "plan_baseline.py"), str(out), "--check"]),
        ("method", (data / "proposals.json").exists(), "нет реестра", py + [str(HERE / "build_methodology.py"), str(out)]),
        ("handoff", bool((cfg.get("handoff") or {}).get("enabled")) and not (cfg.get("handoff") or {}).get("ask_at_end") and (data / "proposals.json").exists(),
         "выключено выбором (handoff.enabled=false)" if not (cfg.get("handoff") or {}).get("enabled")
         else ("состав выбирается в конце прогона: handoff.py <OUT> --list-sections --json → карточки → handoff.py <OUT> --scope … --save" if (cfg.get("handoff") or {}).get("ask_at_end") else "нет реестра"),
         py + [str(HERE / "handoff.py"), str(out)]),
        ("refsreadme", has_refs, "нет карточек design-refs/*.json", py + [str(HERE / "build_design_refs_readme.py"), str(out)]),
        ("html", f.get("html", True), "выключено выбором (formats.html=false)", py + [str(HERE / "build_html.py"), str(out)] + mode + strict_html),
        ("smoke", bool(have_pw) and f.get("html", True), "выключено выбором (html)" if not f.get("html", True) else "нет playwright (check_env.py --install-node)",
         ["node", str(HERE / "node" / "smoke_html.mjs"), str(html)] + nd + eng),
        ("xlsx", f.get("xlsx", True), "выключено выбором (formats.xlsx=false)", py + [str(HERE / "build_xlsx.py"), str(out)]),
        ("deck", f.get("pptx", True) or f.get("pdf", True), "выключено выбором (pptx и pdf)", py + [str(HERE / "build_deck_json.py"), str(out)]),
        ("pptx", bool(have_pptx) and f.get("pptx", True), "выключено выбором (formats.pptx=false)" if not f.get("pptx", True) else "нет pptxgenjs (check_env.py --install-node)",
         ["node", str(HERE / "node" / "build_pptx.mjs"), str(out)] + nd),
        ("pdf", bool(have_pw) and f.get("pdf", True), "выключено выбором (formats.pdf=false)" if not f.get("pdf", True) else "нет playwright (check_env.py --install-node)", ["node", str(HERE / "node" / "deck_pdf.mjs"), str(out)] + nd),
        ("pdfcheck", f.get("pdf", True) is not False, "выключено выбором (formats.pdf=false)", py + [me, str(out), "--check-pdf"]),
        ("report", (HERE / "report.py").exists(), "нет report.py", py + [str(HERE / "report.py"), str(out), "--if-missing"]),
        ("readme", (HERE / "report.py").exists(), "нет report.py", py + [str(HERE / "report.py"), str(out), "--readme"]),
        ("disclosure", disclosure != "full", "выключено выбором (disclosure=full — раскрытие автоматизации разрешено)",
         py + [str(HERE / "intake.py"), "disclosure-check", str(out)]),
        ("links", True, "", py + [str(HERE / "check_links.py"), str(out)] + ([] if a.links else ["--offline"])),
        ("gitignore", bool(inside), "выключено выбором (результат вне репозитория)", py + [str(HERE / "check_gitignore.py"), str(out)]),
    ]


# ---------------------------------------------------------------- встроенные шаги
def check_shots(out, shoot=False):
    """FB-012: карточки конкурентов с http-URL без shot и без shot_blocked → (код, строка)."""
    out = Path(out)
    if shoot:
        nd = node_dir(out)
        js = HERE / "node" / "shoot_competitors.mjs"
        if shutil.which("node") and (nd / "node_modules" / "playwright" / "package.json").exists() and js.exists():
            subprocess.run(["node", str(js), str(out), "--node-dir", str(nd)], capture_output=True, text=True, timeout=1800)
        else:
            print("--shoot: нет node/playwright или shoot_competitors.mjs — снимки не сняты", file=sys.stderr)
    comps = jload(out / "data" / "competitors.json", []) or []
    comps = comps.get("competitors", []) if isinstance(comps, dict) else comps
    cards = [c for c in comps if isinstance(c, dict) and not c.get("self") and str(c.get("url") or "").startswith(("http://", "https://"))]
    miss = []
    for c in cards:
        shot = c.get("shot")
        ok = bool(shot) and ((out / str(shot)).exists() or (out / "competitors" / "shots" / Path(str(shot)).name).exists())
        if not ok and not c.get("shot_blocked"):
            miss.append(c.get("slug") or c.get("name") or c.get("url"))
    if miss:
        return 1, "у %d из %d конкурентов нет скриншота (не заблокированы анти-ботом): %s — node shoot_competitors.mjs <OUT> или build_all --shoot" % (
            len(miss), len(cards), ", ".join(map(str, miss[:6])) + (" …" if len(miss) > 6 else ""))
    return 0, "скриншоты: %d из %d карточек (заблокированы анти-ботом: %d)" % (len(cards) - sum(1 for c in cards if c.get("shot_blocked")),
                                                                            len(cards), sum(1 for c in cards if c.get("shot_blocked")))


def merge_flows(out):
    """FB-006: build/parts/flows-*.json → data/flows.json; дубли ключей — ошибка (код 1), без частей — 0."""
    out = Path(out)
    parts = sorted((out / "build" / "parts").glob("flows-*.json"))
    merged, seen, dups = [], {}, []
    existing = jload(out / "data" / "flows.json", []) or []
    for f in parts:
        data = jload(f, [])
        data = data.get("flows", []) if isinstance(data, dict) else data
        for fl in data or []:
            if not isinstance(fl, dict) or not fl.get("key"):
                continue
            if fl["key"] in seen:
                dups.append("%s (%s и %s)" % (fl["key"], seen[fl["key"]], f.name))
                continue
            seen[fl["key"]] = f.name
            merged.append(fl)
    if dups:
        return 1, "дубли ключей схем: %s — переименуйте в частях (ключи — из data/flows-plan.json)" % "; ".join(dups)
    plan_keys = [x.get("key") for x in (jload(out / "data" / "flows-plan.json", []) or []) if isinstance(x, dict)]
    for fl in existing if isinstance(existing, list) else []:   # схемы, которых нет в частях, сохраняются
        if isinstance(fl, dict) and fl.get("key") and fl["key"] not in seen:
            merged.append(fl)
    (out / "data").mkdir(parents=True, exist_ok=True)
    (out / "data" / "flows.json").write_text(json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    missing = [k for k in plan_keys if k and k not in {x.get("key") for x in merged}]
    return 0, "схем слито: %d из %d частей → data/flows.json%s" % (len(merged), len(parts),
                                                                ("; нет схем из плана: %s" % ", ".join(missing)) if missing else "")


def pdf_pages(data):
    """Страницы PDF и пустые страницы (без текста и картинок) — по потокам содержимого (FlateDecode через zlib)."""
    objs = {}
    for m in re.finditer(rb"(\d+)\s+0\s+obj(.*?)endobj", data, re.S):
        objs[int(m.group(1))] = m.group(2)
    pages = [(n, body) for n, body in objs.items() if re.search(rb"/Type\s*/Page(?![s\w])", body)]

    def stream_of(n):
        body = objs.get(n, b"")
        m = re.search(rb"stream\r?\n(.*?)\r?\nendstream", body, re.S)
        if not m:
            return b""
        raw = m.group(1)
        if b"FlateDecode" in body[:m.start()]:
            try:
                return zlib.decompress(raw)
            except zlib.error:
                return raw
        return raw

    if not pages:                                      # потоки объектов (ObjStm): только число страниц, пустые не определить
        return len(re.findall(rb"/Type\s*/Page(?![s\w])", data)), []
    empty = []
    for idx, (n, body) in enumerate(sorted(pages), 1):
        refs = []
        mc = re.search(rb"/Contents\s*(\[(.*?)\]|(\d+)\s+0\s+R)", body, re.S)
        if mc:
            refs = [int(x) for x in re.findall(rb"(\d+)\s+0\s+R", mc.group(0))]
        content = b"".join(stream_of(r) for r in refs)
        has_text = b"TJ" in content or b"Tj" in content
        has_img = bool(re.search(rb"\sDo\b", content))
        drawing = len(re.findall(rb"\s(?:re|l|c|m)\s", content)) > 12          # векторные графики без текста — не пустая страница
        if not (has_text or has_img or drawing):
            empty.append(idx)
    return len(pages), empty


PREVIEW_JS = r"""
import { createRequire } from 'node:module'; import path from 'node:path'; import fs from 'node:fs';
const [dir, html, outDir, picks] = process.argv.slice(1);
const pw = createRequire(path.join(dir, 'node_modules', '_r.cjs'))('playwright');
const b = await pw.chromium.launch(); const p = await b.newPage({ viewport: { width: 1280, height: 720 } });
await p.goto('file://' + html);
const res = await p.evaluate(() => [...document.querySelectorAll('.slide')].map((s, i) => {
  const over = s.scrollHeight > s.clientHeight + 2 || s.scrollWidth > s.clientWidth + 2;
  const text = (s.innerText || '').trim().length; const imgs = s.querySelectorAll('img,svg').length;
  return { i: i + 1, over, empty: text < 3 && imgs === 0 };
}));
fs.mkdirSync(outDir, { recursive: true });
const want = new Set(picks.split(',').map(Number));
const slides = await p.$$('.slide');
for (let i = 0; i < slides.length; i++) if (want.has(i + 1)) await slides[i].screenshot({ path: path.join(outDir, `page-${String(i + 1).padStart(2, '0')}.png`) });
await b.close(); console.log(JSON.stringify(res));
"""


def check_pdf(out, n_preview=4):
    """FB-018: «PDF: N страниц, пустых X, обрезанных Y, превью: build/pdf-preview/» → (код, строка)."""
    out = Path(out)
    pdf = out / "deliverables" / "strategy.pdf"
    if not pdf.exists():
        return 0, "PDF нет (deliverables/strategy.pdf) — проверять нечего"
    try:
        n, empty = pdf_pages(pdf.read_bytes())
    except OSError as e:
        return 1, "PDF не прочитан: %s" % e
    cut, prev = None, "нет (нужен playwright)"
    html = out / "build" / "deck.html"
    nd = node_dir(out)
    if html.exists() and shutil.which("node") and (nd / "node_modules" / "playwright" / "package.json").exists():
        rnd = random.Random(n)
        picks = sorted({1, 2, n} | set(rnd.sample(range(1, n + 1), min(max(0, n_preview - 3), n)) if n else set()))
        try:
            r = subprocess.run(["node", "--input-type=module", "-e", PREVIEW_JS, str(nd), str(html.resolve()), str(out / "build" / "pdf-preview"),
                                ",".join(map(str, picks))], capture_output=True, text=True, timeout=300)
            res = json.loads((r.stdout.strip().splitlines() or ["[]"])[-1])
            cut = [x["i"] for x in res if x.get("over")]
            empty = sorted(set(empty) | {x["i"] for x in res if x.get("empty")})
            prev = "build/pdf-preview/ (%d PNG)" % len(list((out / "build" / "pdf-preview").glob("*.png")))
        except (OSError, ValueError, subprocess.SubprocessError) as e:
            prev = "не снято (%s)" % type(e).__name__
    line = "PDF: %d страниц, пустых %d, обрезанных %s, превью: %s" % (n, len(empty), len(cut) if cut is not None else "не проверено", prev)
    if empty:
        line += "; пустые: %s" % ", ".join(map(str, empty[:10]))
    if cut:
        line += "; обрезанные: %s" % ", ".join(map(str, cut[:10]))
    return (1 if (empty or cut) else 0), line


# ---------------------------------------------------------------- ворота полноты (FB-058)
def fact_rows(out):
    d = jload(Path(out) / "data" / "fact-check.json", None)
    if isinstance(d, list):
        return [x for x in d if isinstance(x, dict)], True
    if isinstance(d, dict):
        for k in ("items", "discrepancies", "checks", "facts"):
            if isinstance(d.get(k), list):
                return [x for x in d[k] if isinstance(x, dict)], True
        return [], True
    return [], False


def owner_status(text, url):
    """Статус ссылки в build/owner-materials.md: раздел «## <url>» со строкой «Статус: …» или та же строка."""
    m = re.search(r"(?ms)^## %s\s*\n(.*?)(?=^## |\Z)" % re.escape(url), text)
    if m:
        st = re.search(r"Статус:\s*\**\s*(read|blocked|not_attempted)", m.group(1))
        if st:
            return st.group(1)
    m = re.search(re.escape(url) + r"[^\n]*?\b(read|blocked|not_attempted)\b", text)
    return m.group(1) if m else "not_attempted"


def completeness(out, cfg, results, a):
    """→ [{code, check, status: да|нет|н/п, detail, todo}]."""
    out = Path(out)
    concept = cfg.get("mode") == "concept"
    st = {n: (s, msg) for n, s, msg, _dt in results}
    rows = []

    def add(code, check, status, detail="", todo=""):
        rows.append({"code": code, "check": check, "status": status, "detail": detail, "todo": todo})

    # 1. скриншоты конкурентов
    if (out / "data" / "competitors.json").exists() and (cfg.get("scope") or {}).get("competitors", True) is not False:
        code, line = check_shots(out)
        add("shots", "Скриншоты конкурентов", "нет" if code else "да", line,
            "node shoot_competitors.mjs <OUT> (или build_all --shoot); анти-бот — shot_blocked: true")
    else:
        add("shots", "Скриншоты конкурентов", "н/п", "нет data/competitors.json или scope.competitors=false")
    # 2. фазы
    sp = out / "build" / "STATUS.md"
    try:
        import init_run
        has_phases = sp.exists() and bool(init_run.phases_in(sp.read_text(encoding="utf-8")))
    except Exception:                                  # noqa: BLE001
        has_phases = False
    if has_phases:
        op = init_run.open_phases(out)
        add("phases", "Все фазы отмечены (STATUS.md)", "нет" if op else "да",
            ("открыты: %s" % "; ".join("%s (%s)" % x for x in op)) if op else "все фазы закрыты или выключены выбором",
            "init_run.py <OUT> --done <фаза> (или --show — что не хватает)")
    else:
        add("phases", "Все фазы отмечены (STATUS.md)", "н/п", "в build/STATUS.md нет чек-листа фаз")
    # 3. материалы владельца
    docs = [d for d in ((cfg.get("sources") or {}).get("owner_docs") or []) if isinstance(d, (dict, str))]
    if docs:
        om = out / "build" / "owner-materials.md"
        omt = om.read_text(encoding="utf-8", errors="replace") if om.exists() else ""
        bad = []
        for d in docs:
            d = d if isinstance(d, dict) else {"url": d}
            stt = d.get("status")
            if not stt:
                stt = owner_status(omt, str(d.get("url")))
            if stt == "not_attempted":
                bad.append(str(d.get("url")))
        add("owner_materials", "Материалы владельца прочитаны", "нет" if bad else "да",
            ("статус not_attempted: %s" % ", ".join(bad[:4])) if bad else "%d ссылок — read/blocked" % len(docs),
            "прочитать доступным инструментом (веб, чтение артефактов) и записать build/owner-materials.md (статус, инструмент, выжимка)")
    else:
        add("owner_materials", "Материалы владельца прочитаны", "н/п", "sources.owner_docs пуст")
    # 4. fact-check применён
    fr, has = fact_rows(out)
    if has:
        bad = [x.get("fact") or x.get("claim") or "?" for x in fr
               if (x.get("resolved_value") not in (None, "") or str(x.get("status", "")).lower() in ("resolved", "решено"))
               and not x.get("applied") and "только текст" not in str(x.get("note") or "") and not x.get("text_only")]
        add("fact_check", "Fact-check применён к источникам", "нет" if bad else "да",
            ("решено, но не применено: %s" % ", ".join(map(str, bad[:5]))) if bad else "%d записей" % len(fr),
            "apply_fact_check.py <OUT> (поле fix) или note: «только текст»")
    else:
        add("fact_check", "Fact-check применён к источникам", "н/п", "нет data/fact-check.json")
    # 5. согласованность с plan-baseline
    s, msg = st.get("consistency", ("—", ""))
    add("consistency", "Согласованность с data/plan-baseline.json", {"OK": "да", "WARN": "нет", "FAIL": "нет"}.get(s, "н/п"), msg or "шаг не выполнялся",
        "plan_baseline.py <OUT> --check — даты и числа вех в частях текста → плейсхолдеры {plan:…}")
    # 6. интерактивность / smoke
    s, msg = st.get("smoke", ("—", ""))
    if s == "OK":
        add("interactivity", "Интерактивность страницы (smoke)", "да", msg)
    elif s == "—":
        add("interactivity", "Интерактивность страницы (smoke)", "н/п", msg)
    else:
        add("interactivity", "Интерактивность страницы (smoke)", "нет", msg or s,
            "node smoke_html.mjs deliverables/index.html (нет playwright — check_env.py --install-node); не запускать сборку сдачи с --skip smoke")
    # 7. вопросы запроса
    rqs = [q for q in ((cfg.get("idea") or {}).get("request_questions") or []) if isinstance(q, dict) and q.get("id")]
    if rqs:
        texts = ""
        for fp in sorted((out / "build" / "parts").glob("strategy-*.md")) + [out / "research" / "strategy.md"]:
            if fp.exists():
                texts += fp.read_text(encoding="utf-8", errors="replace")
        miss = [q["id"] for q in rqs if str(q.get("kind") or "research") != "format" and "[%s]" % q["id"] not in texts]
        add("request_questions", "Вопросы запроса отвечены (маркеры [RQnn])", "нет" if miss else "да",
            ("нет маркера: %s" % ", ".join(miss)) if miss else "%d вопросов" % len(rqs), "ответ в разделе с маркером [RQnn] (assemble_strategy.py)")
    else:
        add("request_questions", "Вопросы запроса отвечены (маркеры [RQnn])", "н/п", "idea.request_questions пуст")
    # 8. REPORT.md
    try:
        import report
        rc = report.check_report(out)
        add("report", "REPORT.md: все разделы, без «<заполнить»", "да" if rc["ok"] else "нет",
            "нет файла" if not rc["exists"] else "нет разделов %d, мест «<заполнить» %d" % (len(rc["missing_sections"]), rc["fill"]),
            "report.py <OUT> (каркас из данных), дописать помеченные места")
    except Exception as e:                             # noqa: BLE001
        add("report", "REPORT.md: все разделы, без «<заполнить»", "н/п", "report.py: %s" % type(e).__name__)
    # 9. учёт агентов
    ag = jload(out / "build" / "agents.json", {}) or {}
    n_ag = len(ag.get("tasks") or [])
    if concept:
        add("agents", "Запуски агентов в build/agents.json", "да" if n_ag else "нет", "%d заданий" % n_ag,
            "dispatch.py <OUT> add / ready --start / done --tokens … (режим идеи — обязательно)")
    else:
        add("agents", "Запуски агентов в build/agents.json", "да" if n_ag else "н/п", "%d заданий" % n_ag)
    # 10. PDF
    s, msg = st.get("pdfcheck", ("—", ""))
    if str(msg).startswith("PDF нет"):
        s = "—"
    add("pdf", "PDF без пустых и обрезанных страниц", {"OK": "да", "WARN": "нет", "FAIL": "нет"}.get(s, "н/п"), msg or "PDF не собирался",
        "открыть build/pdf-preview/*.png, поправить вёрстку колоды")
    # 11–12. режим идеи: выбор направления дизайна, пересмотр идеи
    if concept:
        d = cfg.get("design") or {}
        tokens = (out / "mockups" / "tokens.css").exists()
        if tokens:
            ok = isinstance(d, dict) and bool(d.get("chosen")) and (d.get("chosen_by") == "owner" or cfg.get("autopilot"))
            add("design_choice", "Направление дизайна выбрал владелец", "да" if ok else "нет",
                "design.chosen = %s, chosen_by = %s" % ((d or {}).get("chosen") or "—", (d or {}).get("chosen_by") or "—"),
                "AskUserQuestion с направлениями из design/directions.md → run-config design.chosen / chosen_by: owner")
        else:
            add("design_choice", "Направление дизайна выбрал владелец", "н/п", "токенов дизайна ещё нет")
        if (out / "data" / "competitors.json").exists() and (cfg.get("phases") or {}).get("pivot_check", True) is not False:
            pr = jload(out / "data" / "premises.json", None)
            ok = isinstance(pr, dict) and bool(pr.get("decision"))
            add("pivot", "Пересмотр идеи после рынка (C4.5)", "да" if ok else "нет",
                ("решение: %s" % pr.get("decision")) if ok else "нет решения в data/premises.json",
                "pivot_check.py <OUT> → заполнить предпосылки → --check → вопрос владельцу → --decide")
        else:
            add("pivot", "Пересмотр идеи после рынка (C4.5)", "н/п", "исследование рынка ещё не выполнено или фаза выключена")
    # 13. направления рынка (SM 6.2): включённое направление без файла и без строки «пропущено … потому что» в STATUS.md
    if (out / "data" / "competitors.json").exists():
        stt = sp.read_text(encoding="utf-8", errors="replace") if sp.exists() else ""
        sc = cfg.get("scope") or {}
        miss = [label for key, rel, label in MARKET_DIRS
                if sc.get(key, True) is not False and not (out / rel).exists()
                and not re.search(r"пропущ\w*[^\n]*%s|%s[^\n]*пропущ" % (label.split()[0], label.split()[0]), stt, re.I)]
        add("market", "Направления рынка выполнены или явно пропущены", "нет" if miss else "да",
            ("нет файла и пометки «пропущено»: %s" % ", ".join(miss)) if miss else "все включённые направления на месте",
            "запустить бриф направления или init_run.py <OUT> --status \"пропущено: <направление>, потому что …\"")
    accepted = set(getattr(a, "accept_known", None) or [])
    for r in rows:
        r["accepted"] = r["status"] == "нет" and r["code"] in accepted
    return rows


def print_completeness(rows, strict_on):
    print("\nВорота полноты (completeness)%s:" % ("" if strict_on else " — справочно, строго только с --strict"))
    print("| Проверка | Статус | Подробности | Что сделать |")
    print("|---|---|---|---|")
    for r in rows:
        mark = r["status"] + (" (принято: --accept-known %s)" % r["code"] if r.get("accepted") else "")
        detail = re.sub(r" — node shoot_competitors.*$", "", r["detail"] or "")
        print("| %s [%s] | %s | %s | %s |" % (r["check"], r["code"], mark, detail or "—", r["todo"] if r["status"] == "нет" and r["todo"] else "—"))


# ---------------------------------------------------------------- черновик (preview)
def preview(out, cfg, a):
    out = Path(out)
    py = [sys.executable, "-B"]
    pdir = out / "build" / "preview"
    pdir.mkdir(parents=True, exist_ok=True)
    if not (out / "data" / "proposals.json").exists():
        print("ВНИМАНИЕ: реестра ещё нет (фаза C5/5 не выполнена) — черновик будет почти пустым", file=sys.stderr)
    t0 = time.time()
    steps = [("charts", py + [str(HERE / "charts.py"), str(out)]),
             ("html", py + [str(HERE / "build_html.py"), str(out), "--out", str(pdir / "index.html")] + (["--single"] if a.single else []))]
    env = dict(os.environ, PS_NODE_DIR=str(node_dir(out)))
    failed = []
    for name, cmd in steps:
        r = subprocess.run(cmd, env=env, capture_output=True, text=True)
        tail = ((r.stdout or "") + (r.stderr or "")).strip().splitlines()
        print("%-6s %s  %s" % (name, "OK" if r.returncode == 0 else "FAIL", tail[-1][:120] if tail else ""))
        if r.returncode != 0:
            failed.append(name)
            sys.stderr.write("\n".join(tail[-15:]) + "\n")
            if name == "html":
                break
    page = pdir / "index.html"
    if page.exists() and "html" not in failed:
        done = []
        try:
            import init_run
            if (out / "build" / "STATUS.md").exists():
                rows, _ = init_run.phase_report(out)
                done = [r["num"] for r in rows if r["done"] and not r["disabled"]]
        except Exception:                              # noqa: BLE001
            pass
        banner = ('<div class="ps-preview-banner" role="status" style="position:sticky;top:0;z-index:9999;padding:8px 16px;'
                  'background:#fff3cd;color:#5c4400;border-bottom:1px solid #e0c36c;font:14px/1.4 system-ui,sans-serif">'
                  'Черновик (preview), не для сдачи: готовы фазы %s; собрано %s</div>' % (", ".join(done) or "—", time.strftime("%Y-%m-%d %H:%M")))
        html = page.read_text(encoding="utf-8")
        if "ps-preview-banner" not in html:
            html = re.sub(r"(<body[^>]*>)", lambda m: m.group(1) + banner, html, count=1)
            page.write_text(html, encoding="utf-8")
    try:
        shown = page.relative_to(out).as_posix()
    except ValueError:
        shown = str(page)
    print("Черновик: <OUT>/%s (%.0f с). Открыть в браузере владельца — только по его просьбе; deliverables/ не тронут." % (shown, time.time() - t0))
    return 1 if failed else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("out")
    ap.add_argument("--only", default="")
    ap.add_argument("--skip", default="")
    ap.add_argument("--links", action="store_true", help="проверять ссылки с сетью")
    ap.add_argument("--strict", action="store_true", help="ошибка check_registry/validate останавливает конвейер; ворота полноты строгие")
    ap.add_argument("--accept-known", default="", help="осознанные исключения ворот полноты: коды через запятую (%s)" % ", ".join(ACCEPT_CODES))
    ap.add_argument("--typesafe", action="store_true", help="запустить typesafe_eval.py принудительно")
    ap.add_argument("--track", action="store_true", help="перед сборкой обновить статусы выполнения (strategy_track.py check)")
    ap.add_argument("--single", action="store_true", help="страница одним автономным файлом (CSS, JS, данные и картинки внутри; для Artifact ≤ 16 МБ)")
    ap.add_argument("--lite", action="store_true", help="single без встроенных картинок (assets рядом; цель ≤ 8 МБ)")
    ap.add_argument("--zip", action="store_true", help="собрать deliverables/strategy-site.zip (только режим site)")
    ap.add_argument("--engines", help="движки smoke-теста: chromium,webkit (по умолчанию все доступные)")
    ap.add_argument("--shoot", action="store_true", help="снять скриншоты конкурентов перед проверкой (нужен playwright)")
    ap.add_argument("--preview", action="store_true", help="черновик: графики и страница → build/preview/index.html, без ворот")
    ap.add_argument("--merge-flows", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--check-shots", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--check-pdf", action="store_true", help=argparse.SUPPRESS)
    a = ap.parse_args(argv)
    out = Path(a.out).resolve()
    if a.merge_flows:
        code, line = merge_flows(out)
        print(line)
        return code
    if a.check_shots:
        code, line = check_shots(out, a.shoot)
        print(line)
        return code
    if a.check_pdf:
        code, line = check_pdf(out)
        print(line)
        return code
    cfgp = out / "build" / "run-config.json"
    cfg = json.loads(cfgp.read_text(encoding="utf-8")) if cfgp.exists() else {}
    if a.preview:
        return preview(out, cfg, a)
    a.accept_known = [x.strip() for x in a.accept_known.split(",") if x.strip()]
    unknown = [x for x in a.accept_known if x not in ACCEPT_CODES]
    if unknown:
        print("--accept-known: неизвестные коды %s (есть: %s)" % (", ".join(unknown), ", ".join(ACCEPT_CODES)), file=sys.stderr)
        return 2
    demo = is_demo(cfg)
    strict_gate = a.strict and not demo
    only = {s for s in a.only.split(",") if s}
    skip = {s for s in a.skip.split(",") if s}
    env = dict(os.environ, PS_NODE_DIR=str(node_dir(out)))
    results = []
    pdf_line = None
    for name, enabled, why, cmd in plan(out, cfg, a):
        if (only and name not in only) or name in skip:
            results.append((name, "·", "не запускался в этом вызове (%s)" % ("--only" if only and name not in only else "--skip"), 0))
            continue
        if not enabled:
            results.append((name, "н/п" if why.startswith("не нужно") else
                            "—" if why.startswith(("выключено выбором", "режим идеи", "уже оценено")) else "SKIP", why, 0))
            continue
        script = Path(cmd[2] if cmd[0] == sys.executable else cmd[1])        # (python -B script) или (node script)
        if not script.exists():
            results.append((name, "SKIP", "нет скрипта %s" % script.name, 0))
            continue
        t0 = time.time()
        r = subprocess.run(cmd, env=env, capture_output=True, text=True)
        dt = time.time() - t0
        tail = ((r.stdout or "") + (r.stderr or "")).strip().splitlines()
        okc = (0, 1) if name == "track" else (0,)         # check возвращает 1 при предупреждениях (нет gh, нет сканов) — не провал
        if name in WARN_STEPS and r.returncode == 1:
            accepted = {"shots": "shots", "consistency": "consistency", "pdfcheck": "pdf"}[name] in a.accept_known
            status = "FAIL" if (strict_gate and not accepted) else "WARN"
        else:
            status = "OK" if r.returncode in okc else "FAIL"
        results.append((name, status, tail[-1][:160] if tail else "", dt))
        if name == "pdfcheck" and tail and not tail[-1].startswith("PDF нет"):
            pdf_line = tail[-1]
            print(pdf_line)
        if name == "dossier" and r.returncode == 0 and int(((cfg.get("idea") or {}).get("version") or 1)) > 1:
            try:
                import pivot_check
                pivot_check.sync_idea_json(out, cfg["idea"])      # досье пересобрало idea.json — вернуть версию идеи после пивота
            except Exception:                          # noqa: BLE001
                pass
        if status == "FAIL":
            sys.stderr.write("\n--- %s (код %d) ---\n%s\n" % (name, r.returncode, "\n".join(tail[-25:])))
            if a.strict and name in ("registry", "validate", "assemble"):
                break
    partial = bool(only)
    comp_rows = []
    if not partial:
        if (out / "build" / "STATUS.md").exists():
            try:
                import init_run
                marked = init_run.sync(out, quiet=True)
                if marked:
                    print("init_run --sync: по артефактам отмечены фазы %s" % ", ".join(marked))
            except Exception as e:                     # noqa: BLE001
                print("init_run --sync не выполнен: %s" % e, file=sys.stderr)
        comp_rows = completeness(out, cfg, results, a)
        bad = [r for r in comp_rows if r["status"] == "нет" and not r["accepted"]]
        if strict_gate and bad:
            results.append(("completeness", "FAIL", "нет: %s" % ", ".join(r["code"] for r in bad), 0))
        elif bad:
            results.append(("completeness", "WARN", "нет: %s%s" % (", ".join(r["code"] for r in bad), " (демо — не строго)" if demo and a.strict else ""), 0))
        else:
            results.append(("completeness", "OK", "все проверки «да» или н/п", 0))
    w = max(len(n) for n, *_ in results)
    print("%-*s  %-4s  %6s  %s" % (w, "шаг", "итог", "сек", "последняя строка / причина"))
    for n, st, msg, dt in results:
        print("%-*s  %-4s  %6.1f  %s" % (w, n, st, dt, msg))
    if comp_rows:
        print_completeness(comp_rows, strict_gate)
    failed = [n for n, st, *_ in results if st == "FAIL"]
    skipped = [n for n, st, *_ in results if st == "SKIP"]
    off = [n for n, st, *_ in results if st == "—"]
    warned = [n for n, st, *_ in results if st == "WARN"]
    na = [n for n, st, *_ in results if st == "н/п"]
    not_run = [n for n, st, *_ in results if st == "·"]
    head = ("Итог (частичный запуск --only %s): %s" % (",".join(sorted(only)), "запущенные шаги собраны" if not failed else "упали шаги: " + ", ".join(failed))
            if partial else "Итог: %s" % ("всё собрано" if not failed else "упали шаги: " + ", ".join(failed)))
    print("\n" + head
          + ("; предупреждения: " + ", ".join(warned) if warned else "")
          + ("; пропущено из-за недостающего: " + ", ".join(skipped) if skipped else "")
          + ("; выключено выбором (не ошибка): " + ", ".join(off) if off else "")
          + ("; не нужно (нет входов): " + ", ".join(na) if na else "")
          + ("; не запускались в этом вызове: " + ", ".join(not_run) if not_run else ""))
    last_p = out / "build" / LAST
    if partial:
        last = None
        try:
            last = json.loads(last_p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
        if last:
            print("Итог последнего полного прогона (%s): %s" % (last.get("date", "?"), last.get("summary", "?")))
        else:
            print("Полного прогона ещё не было (build/%s нет) — для итога по всем шагам запустите build_all.py без --only" % LAST)
    else:
        try:
            last_p.parent.mkdir(parents=True, exist_ok=True)
            last_p.write_text(json.dumps({
                "date": time.strftime("%Y-%m-%d %H:%M"), "args": [x for x in (argv if argv is not None else sys.argv[1:]) if x != a.out],
                "summary": head.split(": ", 1)[1] + ("; warn: " + ", ".join(warned) if warned else "") + ("; skip: " + ", ".join(skipped) if skipped else "")
                + ("; не запускались (--skip): " + ", ".join(not_run) if not_run else ""),
                "failed": failed, "skipped": skipped, "off": off, "warned": warned, "not_run": not_run,
                "steps": [{"step": n, "status": st, "note": msg, "sec": round(dt, 1)} for n, st, msg, dt in results],
                "completeness": comp_rows, "accepted_known": a.accept_known, "strict": bool(a.strict), "demo": demo, "pdf": pdf_line,
            }, ensure_ascii=False, indent=1), encoding="utf-8")
        except OSError as e:
            print("не записан build/%s: %s" % (LAST, e), file=sys.stderr)
    inside = (cfg.get("output") or {}).get("inside_repo", False)
    if cfg.get("mode") == "concept":
        print("Папка концепции: %s" % ("ВНУТРИ git-репозитория (ветка %s)" % ((cfg.get("output") or {}).get("git_branch") or "—") if inside
                                       else "ВНЕ git-репозитория — в git не попадёт (перенос: init_run.py <OUT> --relocate <repo>/concept/<имя>/<дата> --repo <repo> --inside-repo)"))
    else:
        print("Папка результата: %s" % ("ВНУТРИ репозитория" if inside else "ВНЕ РЕПОЗИТОРИЯ — в git проекта не попадёт (перенос: init_run.py <OUT> --relocate <repo>/strategy/<дата> --repo <repo> --inside-repo)"))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
