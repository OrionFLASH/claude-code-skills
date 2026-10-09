#!/usr/bin/env python3
"""The whole task for one executor thread, ready to paste: references/parallelism.md → «Задание субагенту».

  brief.py <RUN_DIR> --thread qa-ux --directions ux,product [--pages "главная, каталог" | --pages-file F]
           [--devices pixel7,desktop] [--minutes 25] [--items waves/2/qa-w2-1.json] [--variants prom,test]
           [--registry <RUN_DIR>/registry.json] [--registry-limit 150] [--enhancers "ux-heuristics"]
           [--out <RUN_DIR>/briefs/<thread>.md] [--print]

Fills the template of parallelism.md with the values of <RUN_DIR>/run-config.yaml: SKILL_DIR (run-config skill_dir —
the copy of the skill in the run, skill_snapshot.py), the rules block of safety-rules.md §4 VERBATIM with the rules
table of this run, the browser window (browser_mode.py; refreshes <RUN_DIR>/playwright-cli.json), the registry slice
(fetch_issues.py brief; none -> «реестра нет, dup_check: skipped»), the result format (ingest_findings.py example),
the time limit and, for the second wave, the items of coverage.py again. The thread is registered in
<RUN_DIR>/threads.json (directions, pages, minutes, started_at): coverage.py counts the thread time from here.
Default output: <RUN_DIR>/briefs/<thread>.md (--print — also to stdout). Exit codes: 0 ok, 2 bad input.
"""
import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent
sys.path.insert(0, str(HERE / "shared"))
sys.path.insert(0, str(HERE))
import browser_mode  # noqa: E402
import fetch_issues  # noqa: E402
import ingest_findings  # noqa: E402
import miniyaml  # noqa: E402
import url_guard  # noqa: E402

DEPTH = {"smoke": "Smoke", "standard": "Smoke + Standard", "deep": "Smoke + Standard + Deep"}


def code_block(md_path, heading):
    """First ```text block after the heading (the template / the rules block are kept in one place: the references)."""
    text = Path(md_path).read_text(encoding="utf-8")
    i = text.index(heading)
    j = text.index("```text\n", i) + len("```text\n")
    k = text.index("\n```\n", j)
    return text[j:k]


def rules_table(cfg):
    rules = url_guard.rules_of(cfg)
    site = cfg.get("site") or {}
    L = []
    if rules["allowed_domains"]:
        L.append(f"- переходы только на хосты: {', '.join(map(str, rules['allowed_domains']))}")
    if rules["local_roots"]:
        L.append("- локальные файлы (file://) только внутри: " + ", ".join(r["path"] for r in rules["local_roots"]) +
                 " («..», симлинки и соседние папки — запрещены)")
    for key, label in (("forbidden_domains", "запрещённые хосты"), ("forbidden_url_patterns", "запрещённые URL (регэкспы)"),
                       ("exclude_patterns", "исключено из охвата"), ("read_only_urls", "только чтение (nav --read-only)")):
        if rules[key]:
            L.append(f"- {label}: " + "; ".join(map(str, rules[key])))
    for key, label in (("forbidden_actions", "НЕЛЬЗЯ"), ("require_confirmation_actions", "только после «да» (вопрос оркестратору)"),
                       ("preapproved_actions", "заранее разрешено (снимает только confirm)")):
        for r in rules[key]:
            parts = [f"«{r.get('source') or r.get('id')}»"]
            if r.get("texts"):
                parts.append("тексты: " + ", ".join(map(str, r["texts"])))
            if r.get("url_pattern"):
                parts.append(f"раздел /{r['url_pattern']}/")
            if r.get("context"):
                parts.append(f"при «{r['context']}»")
            L.append(f"- {label} {r.get('id', '')}: " + "; ".join(parts))
    for se in cfg.get("side_effects") or []:
        if isinstance(se, dict):
            L.append(f"- действие с побочным эффектом {se.get('id')} ({se.get('target')}): НЕ выполнять — только оркестратор "
                     "через invariants.js exec")
    if not site.get("allowed_domains") and not rules["local_roots"]:
        L.append("- allowed_domains не задан: любой переход запрещён (fail closed)")
    return "\n".join(L) or "- только базовые запреты"


def context_path(cfg):
    out = cfg.get("output_dir")
    urls = (cfg.get("site") or {}).get("start_urls") or []
    if not out or not urls:
        return None
    u = urlsplit(str(urls[0]))
    if u.scheme == "file":
        roots = url_guard.local_roots_of(cfg)
        host = "file-" + (Path(roots[0]["path"]).name if roots else "local")
    else:
        host = (u.hostname or "").lower()
        host = host[4:] if host.startswith("www.") else host
    return Path(out) / "qa-runs" / ".site-context" / host / "context.md"


def items_text(path):
    if not path:
        return "по плану прогона (страницы и направления выше)"
    items = json.loads(Path(path).read_text(encoding="utf-8"))
    lines = [f"\n  {i}. {x.get('what')}" + (f" — раньше не проверено: {x.get('reason')}" if x.get("reason") else "")
             + (f" [{x.get('category')}]" if x.get("category") else "") for i, x in enumerate(items, 1)]
    return "вторая волна по списку «не проверено»:" + "".join(lines)


def fill(template, values):
    return re.sub(r"\{\{(\w+)\}\}", lambda m: str(values.get(m.group(1), m.group(0))), template)


def register(run_dir, thread, rec):
    p = Path(run_dir) / "threads.json"
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    old = data.get(thread) or {}
    rec["started_at"] = old.get("started_at") or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    rec["briefs"] = (old.get("briefs") or 0) + 1
    data[thread] = dict(old, **rec)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return data[thread]


def build(a):
    run_dir = Path(a.run_dir)
    cfg_path = run_dir / "run-config.yaml"
    if not cfg_path.is_file():
        raise SystemExit(f"brief: нет {cfg_path}")
    cfg = miniyaml.load_file(str(cfg_path)) or {}
    url_guard.validate_rules(cfg)  # a broken config never goes to an executor
    skill_dir = cfg.get("skill_dir") or str(SKILL)
    thread = a.thread
    if not re.fullmatch(r"[\w.-]+", thread):
        raise SystemExit("brief: --thread — латиница, цифры, «-», «_» (имя сессии playwright-cli)")
    dirs = [d.strip() for d in (a.directions or ",".join(cfg.get("directions") or [])).split(",") if d.strip()]
    pages = Path(a.pages_file).read_text(encoding="utf-8").strip() if a.pages_file else (a.pages or "по карте разведки")
    win = browser_mode.effective(run_dir)
    browser_mode.write_cli_config(run_dir, win)
    window = f"видно, замедление {win['slowmo']} мс" if win["headed"] else "скрыто"
    reg_path = Path(a.registry) if a.registry else run_dir / "registry.json"
    if reg_path.is_file():
        registry = fetch_issues.brief(json.loads(reg_path.read_text(encoding="utf-8")), a.registry_limit)
    else:
        registry = "- реестра нет (репозитории не заданы или не выгружены): сверку не делать, у каждой находки dup_check: skipped"
    variants = a.variants or ", ".join(str(v.get("id") if isinstance(v, dict) else v) for v in cfg.get("variants") or []) \
        or "один (не указаны)"
    devices = a.devices or ", ".join(str(v.get("name")) for v in (cfg.get("devices") or {}).get("viewports") or []
                                     if isinstance(v, dict)) or "по матрице глубины"
    ctx = context_path(cfg)
    rules = code_block(SKILL / "references" / "safety-rules.md", "## 4. Блок правил для исполнителей")
    throttle = (cfg.get("parallel") or {}).get("throttle_ms", 1500)
    rules = (rules.replace("<SKILL_DIR>", skill_dir).replace("<RUN_DIR>", str(run_dir)).replace("<qa-id>", thread)
             .replace("<THROTTLE_MS>", str(throttle)).replace("<RULES_TABLE>", rules_table(cfg)))
    values = {
        "THREAD": thread, "DIRECTIONS": ", ".join(dirs) or "по плану", "SKILL_DIR": skill_dir, "RUN_DIR": str(run_dir),
        "WINDOW": window, "PAGES": pages, "DEVICES": devices, "VARIANTS": variants,
        "MINUTES": f"{a.minutes} минут" if a.minutes else "без лимита (желательно ≤ 30 минут на поток)",
        "ITEMS": items_text(a.items),
        "CONTEXT": str(ctx) if ctx and ctx.exists() else "нет (памяти о сайте пока нет — только этот бриф и run-config)",
        "CHECKLISTS": ", ".join(f"{skill_dir}/references/checklists/{d}.md" for d in dirs
                                if (SKILL / "references" / "checklists" / f"{d}.md").exists()) or "—",
        "DEPTH": DEPTH.get(cfg.get("depth"), "Smoke"),
        "ENHANCERS": a.enhancers or "по plugins-map.md (если назначены оркестратором)",
        "REGISTRY": registry, "RULES_BLOCK": rules,
        "FORMAT": "Формат блока (ingest_findings.py example):\n" + ingest_findings.EXAMPLE.replace("<SKILL_DIR>", skill_dir)
        .replace("<qa-id>", thread),
    }
    text = fill(code_block(SKILL / "references" / "parallelism.md", "## Задание субагенту (шаблон)"), values)
    left = re.findall(r"\{\{\w+\}\}", text)
    if left:
        raise SystemExit(f"brief: не заполнены {sorted(set(left))}")
    rec = register(run_dir, thread, {"directions": dirs, "pages": pages, "devices": devices, "variants": variants,
                                     "minutes": a.minutes, "items": a.items})
    return text, rec


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run_dir")
    ap.add_argument("--thread", required=True, help="id потока = имя сессии playwright-cli (qa-ux)")
    ap.add_argument("--directions", help="направления через запятую (по умолчанию — все из run-config)")
    ap.add_argument("--pages", help="страницы / группа страниц (текстом)")
    ap.add_argument("--pages-file", help="файл со списком страниц")
    ap.add_argument("--devices", help="устройства и браузеры (pixel7,desktop,webkit)")
    ap.add_argument("--minutes", type=int, help="лимит времени потока, мин (подсказка: 20–30)")
    ap.add_argument("--items", help="вторая волна: waves/<n>/<thread>.json из coverage.py again")
    ap.add_argument("--variants", help="варианты данных/стенды для потока (по умолчанию — run-config variants)")
    ap.add_argument("--registry", help="registry.json (по умолчанию <RUN_DIR>/registry.json)")
    ap.add_argument("--registry-limit", type=int, default=150)
    ap.add_argument("--enhancers", help="методики-усилители (plugins-map.md)")
    ap.add_argument("--out", help="файл задания (по умолчанию <RUN_DIR>/briefs/<thread>.md)")
    ap.add_argument("--print", action="store_true", help="также напечатать задание")
    a = ap.parse_args()
    try:
        text, rec = build(a)
    except url_guard.GuardUnavailable as ex:
        print(f"brief: правила прогона не проходят url_guard ({ex}) — задание не создано", file=sys.stderr)
        sys.exit(2)
    out = Path(a.out or Path(a.run_dir) / "briefs" / f"{a.thread}.md")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text + "\n", encoding="utf-8")
    if a.print:
        print(text)
    print(f"brief: {out} ({len(text)} символов) — передать исполнителю целиком; поток {a.thread} зарегистрирован "
          f"({rec['started_at']}), результат — ingest_findings.py {a.run_dir} --from <сообщение> --thread {a.thread}")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
