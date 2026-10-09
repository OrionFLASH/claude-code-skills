#!/usr/bin/env python3
"""Coverage of executor threads: metrics, «not checked», the second wave.

  thread_coverage.py build <RUN_DIR> [--thread qa-ux]
      coverage/<thread>.md from coverage/<thread>.json (ingest_findings.py: checked / not checked / questions),
      findings/<thread>.json and the thread metrics computed AUTOMATICALLY:
        time      — from the brief (threads.json, brief.py) to the ingested result (or first..last guard decision);
        pages     — navigations checked by url_guard (allowed / unique), from logs/guard-<thread>.jsonl (--trace);
        actions   — clicks/inputs checked by url_guard before doing them (allowed / unique controls), denied, confirm.
      Without --thread — every thread known from threads.json, coverage/*.json, findings/*.json or logs/guard-*.jsonl.
  thread_coverage.py summary <RUN_DIR> [--out FILE]
      table of all threads -> coverage/summary.md (also a section of report.md)
  thread_coverage.py again <RUN_DIR> [--minutes 25] [--per-item 5] [--threads N] [--include-forbidden] [--json]
      SECOND WAVE by the list «not checked» (findings.json not_checked + coverage/*.json): items are classified
      (time, environment, auth, data, other; forbidden — only with --include-forbidden, it needs the user's decision),
      packed into threads (≤ parallel.max_workers, at most 4) so that each fits into --minutes, and written to
      waves/<n>/plan.md, plan.json and waves/<n>/<thread>.json (items for brief.py --items); journal todos added.
      Next step for each thread: brief.py <RUN_DIR> --thread <id> --items waves/<n>/<id>.json --minutes <m>.

Exit codes: 0 ok, 1 nothing to do (again: no items), 2 bad input.
"""
import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "shared"))
import miniyaml  # noqa: E402

SEVERITIES = ["critical", "high", "medium", "low", "info"]
CATEGORY_RX = [
    ("forbidden", r"запрет|forbidden|deny|правил[оа] польз|base:|user:"),
    ("time", r"врем|не успел|лимит|таймаут|timeout|time"),
    ("auth", r"вход|логин|аккаунт|авториз|login|auth|pro\b|подписк"),
    ("environment", r"окружен|браузер|webkit|firefox|safari|устройств|эмуляц|environment|device|не запуска"),
    ("data", r"данн|стенд|вариант|набор|data|fixture|stand"),
]
MAX_WORKERS = 4


def load(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def save(path, data):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def ts(s):
    try:
        return datetime.strptime(s[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def safe(name):
    return re.sub(r"[^\w.-]+", "-", str(name or "agent")).strip("-") or "agent"


def threads_of(run_dir):
    run_dir = Path(run_dir)
    names = list((load(run_dir / "threads.json", {}) or {}).keys())
    for sub, rx in (("coverage", r"^(?!summary)(.+)\.json$"), ("findings", r"^(.+)\.json$"), ("logs", r"^guard-(.+)\.jsonl$")):
        d = run_dir / sub
        if d.is_dir():
            for f in sorted(d.iterdir()):
                m = re.match(rx, f.name)
                if m and m.group(1) not in names:
                    names.append(m.group(1))
    return names


def events_of(run_dir, thread):
    p = Path(run_dir) / "logs" / f"guard-{safe(thread)}.jsonl"
    out = []
    if p.exists():
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
    return out


def metrics(run_dir, thread):
    """Automatic metrics of a thread from the guard trace, the brief registry and the ingest time."""
    ev = events_of(run_dir, thread)
    reg = (load(Path(run_dir) / "threads.json", {}) or {}).get(thread) or {}
    cov = load(Path(run_dir) / "coverage" / f"{safe(thread)}.json", {}) or {}
    times = [t for t in (ts(e.get("ts")) for e in ev) if t]
    start = ts(reg.get("started_at")) or (min(times) if times else None)
    end = ts(cov.get("updated_at")) or (max(times) if times else None)
    if times and end and max(times) > end:
        end = max(times)
    navs = [e for e in ev if e.get("type") == "nav"]
    acts = [e for e in ev if e.get("type") == "action"]
    allowed = [e for e in acts if e.get("decision") == "allow"]
    m = {
        "minutes": round((end - start).total_seconds() / 60, 1) if start and end and end >= start else None,
        "time_source": "задание → приём результата" if reg.get("started_at") and cov.get("updated_at") else
        ("журнал guard" if times else None),
        "nav_checks": len(navs),
        "pages": len({e.get("url") for e in navs if e.get("decision") == "allow"}),
        "action_checks": len(acts),
        "actions_allowed": len(allowed),
        "controls": len({(e.get("selector") or "", e.get("name") or "", e.get("text") or "") for e in allowed}),
        "denied": sum(1 for e in ev if e.get("decision") == "deny"),
        "confirm": sum(1 for e in ev if e.get("decision") == "confirm"),
        "trace": bool(ev),
        "limit_minutes": reg.get("minutes"),
    }
    if m["minutes"] is not None and reg.get("minutes") and m["minutes"] > float(reg["minutes"]):
        m["over_limit"] = True
    return m


def cell(t, n=120):
    t = re.sub(r"\s+", " ", str(t or "")).strip().replace("|", "\\|")
    return t if len(t) <= n else t[:n - 1] + "…"


def sev_line(findings):
    c = {s: 0 for s in SEVERITIES}
    for f in findings:
        if f.get("severity") in c:
            c[f["severity"]] += 1
    parts = [f"{s} {c[s]}" for s in SEVERITIES if c[s]]
    return f"{len(findings)}" + (f" ({', '.join(parts)})" if parts else "")


def build(run_dir, thread):
    run_dir = Path(run_dir)
    name = safe(thread)
    cov = load(run_dir / "coverage" / f"{name}.json", {}) or {}
    reg = (load(run_dir / "threads.json", {}) or {}).get(thread) or {}
    fs = load(run_dir / "findings" / f"{name}.json", []) or []
    m = metrics(run_dir, thread)
    cov.setdefault("thread", thread)
    cov["auto_metrics"] = m
    save(run_dir / "coverage" / f"{name}.json", cov)
    L = [f"# Охват потока {thread}", ""]
    meta = []
    for key, label in (("directions", "Направления"), ("pages", "Страницы"), ("devices", "Устройства"), ("variants", "Варианты"),
                       ("minutes", "Лимит, мин")):
        if reg.get(key):
            v = reg[key]
            meta.append(f"**{label}:** {', '.join(v) if isinstance(v, list) else v}")
    if meta:
        L += [" · ".join(meta), ""]
    L += ["## Метрики (автоматически)", "",
          "| Время, мин | Переходов (страниц) | Проверено действий (элементов) | Запреты / подтверждения | Находок |",
          "|---|---|---|---|---|",
          f"| {m['minutes'] if m['minutes'] is not None else '—'}{' ⚠ больше лимита' if m.get('over_limit') else ''} | "
          f"{m['nav_checks']} ({m['pages']}) | {m['action_checks']} ({m['controls']}) | {m['denied']} / {m['confirm']} | "
          f"{sev_line(fs)} |", ""]
    src = []
    if m["trace"]:
        src.append(f"журнал решений guard `logs/guard-{name}.jsonl` (url_guard.py --trace)")
    else:
        src.append("журнала guard нет — переходы и действия не посчитаны (в задании нужен --trace)")
    if m["time_source"]:
        src.append(f"время: {m['time_source']}")
    L += ["Источник: " + "; ".join(src) + ".", ""]
    if cov.get("metrics"):
        L += ["Самооценка исполнителя: " + ", ".join(f"{k}: {v}" for k, v in cov["metrics"].items()), ""]
    L += ["## Проверено", ""]
    L += [f"- {cell(x.get('what'), 200)}" + (f" ({cell(x.get('direction'), 40)})" if x.get("direction") else "")
          for x in cov.get("checked") or []] or ["- (исполнитель не перечислил)"]
    L += ["", "## Не проверено", "", "| Что | Причина | Категория |", "|---|---|---|"]
    L += [f"| {cell(x.get('what'))} | {cell(x.get('reason'))} | {x.get('category') or category(x)} |"
          for x in cov.get("not_checked") or []] or ["| — | — | — |"]
    if cov.get("questions"):
        L += ["", "## Вопросы", ""] + [f"- {cell(q, 300)}" for q in cov["questions"]]
    L += ["", "## Находки", "", "| ID | Severity | Заголовок | dup_check |", "|---|---|---|---|"]
    L += [f"| {f.get('id')} | {f.get('severity')} | {cell(f.get('title'), 100)} | {f.get('dup_check') or '—'} |" for f in fs] \
        or ["| — | — | — | — |"]
    out = run_dir / "coverage" / f"{name}.md"
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    return out, m


def summary_lines(run_dir):
    run_dir = Path(run_dir)
    names = threads_of(run_dir)
    if not names:
        return []
    L = ["| Поток | Время, мин | Переходов (страниц) | Действий (элементов) | Запреты | Находок | Не проверено |",
         "|---|---|---|---|---|---|---|"]
    for t in names:
        m = metrics(run_dir, t)
        cov = load(run_dir / "coverage" / f"{safe(t)}.json", {}) or {}
        fs = load(run_dir / "findings" / f"{safe(t)}.json", []) or []
        L.append(f"| {t} | {m['minutes'] if m['minutes'] is not None else '—'}{' ⚠' if m.get('over_limit') else ''} | "
                 f"{m['nav_checks']} ({m['pages']}) | {m['action_checks']} ({m['controls']}) | {m['denied']} | "
                 f"{sev_line(fs)} | {len(cov.get('not_checked') or [])} |")
    return L


def category(item):
    if item.get("category"):
        return item["category"]
    if item.get("rule"):
        return "forbidden"
    text = f"{item.get('reason') or ''} {item.get('what') or ''}".lower()
    for cat, rx in CATEGORY_RX:
        if re.search(rx, text):
            return cat
    return "other"


def not_checked_items(run_dir):
    run_dir = Path(run_dir)
    items = list((load(run_dir / "findings.json", {}) or {}).get("not_checked") or [])
    cdir = run_dir / "coverage"
    if cdir.is_dir():
        for f in sorted(cdir.glob("*.json")):
            if f.name == "summary.json":
                continue
            cov = load(f, {}) or {}
            for x in cov.get("not_checked") or []:
                items.append(dict(x, thread=x.get("thread") or cov.get("thread")))
    seen, out = set(), []
    for x in items:
        if not isinstance(x, dict) or not x.get("what"):
            continue
        key = (x.get("what"), x.get("reason"))
        if key not in seen:
            seen.add(key)
            out.append(dict(x, category=category(x)))
    return out


def again(run_dir, minutes=25, per_item=5, threads=None, include_forbidden=False):
    run_dir = Path(run_dir)
    items = not_checked_items(run_dir)
    held = [x for x in items if x["category"] == "forbidden" and not include_forbidden]
    todo = [x for x in items if x not in held]
    cfg = {}
    if (run_dir / "run-config.yaml").exists():
        cfg = miniyaml.load_file(str(run_dir / "run-config.yaml")) or {}
    workers = threads or int(((cfg.get("parallel") or {}).get("max_workers")) or 2)
    workers = max(1, min(MAX_WORKERS, workers))
    waves = run_dir / "waves"
    n = 2 + len([d for d in waves.iterdir() if d.is_dir() and d.name.isdigit()]) if waves.is_dir() else 2
    wdir = waves / str(n)
    # group by direction (then by category) so a thread gets related items; pack to fit the time box
    todo.sort(key=lambda x: (x.get("direction") or "", x["category"], x.get("thread") or ""))
    cap = max(1, int(minutes // max(1, per_item)))
    chunks = [todo[i:i + cap] for i in range(0, len(todo), cap)]
    plan_threads, later = [], []
    for i, chunk in enumerate(chunks):
        if i < workers:
            plan_threads.append({"thread": f"qa-w{n}-{i + 1}", "items": chunk, "minutes": min(minutes, per_item * len(chunk))})
        else:
            later += chunk
    plan = {"wave": n, "minutes": minutes, "per_item": per_item, "workers": workers, "threads": plan_threads,
            "held_forbidden": held, "later": later, "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    if not todo and not held:
        return 1, plan, None
    wdir.mkdir(parents=True, exist_ok=True)
    for t in plan_threads:
        save(wdir / f"{t['thread']}.json", t["items"])
    save(wdir / "plan.json", plan)
    L = [f"# Волна {n}: по списку «не проверено»", "",
         f"Пунктов: {len(todo)} в работу, {len(held)} ждут решения пользователя (запреты), {len(later)} — на следующую волну. "
         f"Потоков: {len(plan_threads)} (максимум {workers}), лимит {minutes} мин на поток (~{per_item} мин на пункт).", ""]
    for t in plan_threads:
        L += [f"## {t['thread']} — {len(t['items'])} пунктов, ~{t['minutes']} мин", "",
              f"`python3 <SKILL_DIR>/scripts/brief.py {run_dir} --thread {t['thread']} --items {wdir / (t['thread'] + '.json')} "
              f"--minutes {t['minutes']}`", ""]
        L += [f"- {cell(x.get('what'), 160)} — {cell(x.get('reason'), 100)} [{x['category']}]"
              + (f" (было: {x['thread']})" if x.get("thread") else "") for x in t["items"]]
        L.append("")
    if held:
        L += ["## Нужно решение пользователя (запреты)", "",
              "Не входят в волну: разрешить один раз / оставить «не проверено» / показать, как проверить вручную.", ""]
        L += [f"- {cell(x.get('what'), 160)} — {cell(x.get('reason'), 100)}" + (f" ({x['rule']})" if x.get("rule") else "")
              for x in held]
        L.append("")
    if later:
        L += ["## Следующая волна", ""] + [f"- {cell(x.get('what'), 160)}" for x in later] + [""]
    (wdir / "plan.md").write_text("\n".join(L), encoding="utf-8")
    if (run_dir / "journal.md").exists():
        todos = [f"Волна {n}: {t['thread']} — {len(t['items'])} пунктов «не проверено» (waves/{n}/plan.md)" for t in plan_threads]
        if held:
            todos.append(f"Волна {n}: спросить пользователя про {len(held)} пунктов под запретом")
        subprocess.run([sys.executable, str(HERE / "journal.py"), "todo", str(run_dir)] + todos, capture_output=True)
    return 0, plan, wdir / "plan.md"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="coverage/<поток>.md с метриками")
    b.add_argument("run_dir")
    b.add_argument("--thread")
    s = sub.add_parser("summary", help="таблица потоков -> coverage/summary.md")
    s.add_argument("run_dir")
    s.add_argument("--out")
    g = sub.add_parser("again", help="вторая волна по списку «не проверено»")
    g.add_argument("run_dir")
    g.add_argument("--minutes", type=int, default=25, help="лимит времени потока, мин")
    g.add_argument("--per-item", type=int, default=5, help="оценка времени на пункт, мин")
    g.add_argument("--threads", type=int, help="потоков (по умолчанию parallel.max_workers, не больше 4)")
    g.add_argument("--include-forbidden", action="store_true", help="включить пункты под запретом (после решения пользователя)")
    g.add_argument("--json", action="store_true")
    a = ap.parse_args()
    if not Path(a.run_dir).is_dir():
        print(f"coverage: нет папки прогона {a.run_dir}", file=sys.stderr)
        sys.exit(2)
    if a.cmd == "build":
        names = [a.thread] if a.thread else threads_of(a.run_dir)
        if not names:
            print("coverage: потоков нет (нет threads.json, coverage/, findings/, logs/guard-*.jsonl)")
            sys.exit(1)
        for t in names:
            out, m = build(a.run_dir, t)
            print(f"{t}: {m['minutes'] if m['minutes'] is not None else '—'} мин, переходов {m['nav_checks']} "
                  f"(страниц {m['pages']}), действий {m['action_checks']} (элементов {m['controls']}) -> {out}")
    elif a.cmd == "summary":
        for t in threads_of(a.run_dir):
            build(a.run_dir, t)
        L = summary_lines(a.run_dir)
        if not L:
            print("coverage: потоков нет")
            sys.exit(1)
        out = Path(a.out or Path(a.run_dir) / "coverage" / "summary.md")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("# Охват по потокам\n\n" + "\n".join(L) + "\n", encoding="utf-8")
        print("\n".join(L))
        print(f"-> {out}")
    else:
        code, plan, path = again(a.run_dir, a.minutes, a.per_item, a.threads, a.include_forbidden)
        if a.json:
            print(json.dumps(plan, ensure_ascii=False, indent=1))
        elif code == 1:
            print("again: список «не проверено» пуст — второй волны нет")
        else:
            print(f"волна {plan['wave']}: потоков {len(plan['threads'])}, пунктов "
                  f"{sum(len(t['items']) for t in plan['threads'])}; под запретом {len(plan['held_forbidden'])}; "
                  f"на следующую волну {len(plan['later'])} -> {path}")
            for t in plan["threads"]:
                print(f"  {t['thread']}: {len(t['items'])} пунктов, ~{t['minutes']} мин — brief.py {a.run_dir} --thread "
                      f"{t['thread']} --items {Path(path).parent / (t['thread'] + '.json')} --minutes {t['minutes']}")
        sys.exit(code)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
