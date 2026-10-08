#!/usr/bin/env python3
"""Run journal RUN_DIR/journal.md: what is done and what is left, to resume after a broken session.

  journal.py init RUN_DIR [--title "…"] [--todo "step" ...]   create journal.md (keeps an existing one)
  journal.py todo RUN_DIR "step" ["step" ...]                  add open items
  journal.py done RUN_DIR "text or item number" [--note "…"]   close an open item (substring or number from status)
  journal.py note RUN_DIR "text"                               log entry (decision, where side effects were written…)
  journal.py status RUN_DIR [--json]                           open items and the last entries; exit 1 if journal is missing

journal.md sections: «Осталось» (open "- [ ]" items), «Сделано» ("- [x]" with time), «Записи» (log).
Plain Markdown: can be edited by hand; the script re-reads it each time.
"""
import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

HEADS = ("## Осталось", "## Сделано", "## Записи")


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def strip_box(item):
    return re.sub(r"^- \[ \]\s*", "", item)


def path_of(run_dir):
    return Path(run_dir) / "journal.md"


def read(run_dir):
    p = path_of(run_dir)
    if not p.exists():
        return None
    text = p.read_text(encoding="utf-8")
    title = (re.search(r"^# (.+)$", text, re.M) or [None, "Журнал прогона"])[1]
    parts = {h: [] for h in HEADS}
    cur = None
    for line in text.splitlines():
        if line.strip() in HEADS:
            cur = line.strip()
        elif cur and line.strip():
            parts[cur].append(line.rstrip())
    return {"title": title, "todo": parts[HEADS[0]], "done": parts[HEADS[1]], "log": parts[HEADS[2]]}


def write(run_dir, j):
    lines = [f"# {j['title']}", "", "Журнал для продолжения после обрыва: открытые пункты сверху. "
             "Обновлять скриптом `journal.py` или вручную.", ""]
    for head, key in zip(HEADS, ("todo", "done", "log")):
        lines += [head, ""] + (j[key] or ["—"] if key != "todo" else j[key] or ["- нет открытых пунктов"]) + [""]
    p = path_of(run_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def clean(items):
    return [x for x in items if x not in ("—", "- нет открытых пунктов")]


def need(run_dir):
    j = read(run_dir)
    if j is None:
        sys.stderr.write(f"journal: нет {path_of(run_dir)} — сначала journal.py init\n")
        sys.exit(1)
    for k in ("todo", "done", "log"):
        j[k] = clean(j[k])
    return j


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("init")
    i.add_argument("run_dir")
    i.add_argument("--title")
    i.add_argument("--todo", action="append", default=[])
    t = sub.add_parser("todo")
    t.add_argument("run_dir")
    t.add_argument("items", nargs="+")
    d = sub.add_parser("done")
    d.add_argument("run_dir")
    d.add_argument("item")
    d.add_argument("--note")
    n = sub.add_parser("note")
    n.add_argument("run_dir")
    n.add_argument("text")
    s = sub.add_parser("status")
    s.add_argument("run_dir")
    s.add_argument("--json", action="store_true")
    a = ap.parse_args()

    if a.cmd == "init":
        j = read(a.run_dir)
        if j is not None:
            print(f"journal: уже есть {path_of(a.run_dir)} — продолжаем его")
            return
        j = {"title": a.title or f"Журнал прогона {Path(a.run_dir).resolve().name}", "todo": [], "done": [],
             "log": [f"- {now()} — журнал создан"]}
        j["todo"] = [f"- [ ] {x}" for x in a.todo]
        write(a.run_dir, j)
        print(f"journal: создан {path_of(a.run_dir)}")
    elif a.cmd == "todo":
        j = need(a.run_dir)
        j["todo"] += [f"- [ ] {x}" for x in a.items]
        write(a.run_dir, j)
        print(f"journal: открытых пунктов {len(j['todo'])}")
    elif a.cmd == "done":
        j = need(a.run_dir)
        if a.item.isdigit() and 1 <= int(a.item) <= len(j["todo"]):
            idx = int(a.item) - 1
        else:
            hits = [k for k, x in enumerate(j["todo"]) if a.item.lower() in x.lower()]
            if len(hits) != 1:
                sys.stderr.write(f"journal: «{a.item}» совпадает с {len(hits)} открытыми пунктами — уточните\n")
                sys.exit(2)
            idx = hits[0]
        item = j["todo"].pop(idx)
        text = strip_box(item)
        j["done"].append(f"- [x] {now()} — {text}" + (f" ({a.note})" if a.note else ""))
        write(a.run_dir, j)
        print(f"journal: сделано «{text}», осталось {len(j['todo'])}")
    elif a.cmd == "note":
        j = need(a.run_dir)
        j["log"].append(f"- {now()} — {a.text}")
        write(a.run_dir, j)
        print("journal: запись добавлена")
    else:
        j = need(a.run_dir)
        if a.json:
            print(json.dumps({"todo": [strip_box(x) for x in j["todo"]], "done": len(j["done"]),
                              "last": j["log"][-3:]}, ensure_ascii=False, indent=1))
            return
        print(f"{j['title']}: сделано {len(j['done'])}, осталось {len(j['todo'])}")
        for k, x in enumerate(j["todo"], 1):
            print(f"  {k}. {strip_box(x)}")
        for x in (j["done"][-1:] + j["log"][-2:]):
            print("  последнее: " + x.lstrip("- "))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
