#!/usr/bin/env python3
"""Разбор «Расхождений с фактами» из отчётов агентов → data/fact-check.candidates.json (кандидаты для fact-check.json).

  collect_reports.py <OUT> [отчёт.md …] [--merge] [--json]

Отчёты: перечисленные файлы, иначе <OUT>/build/agent-reports/*.md (и *.txt). Формат блока — templates/briefs/_report-footer.md:
  ## Расхождения с фактами
  - факт — как во входах — как нашёл — источник
Понимает также: пункт списка «N. Расхождения с фактами …: …» (значения в той же строке через «;» или подпунктами),
таблицу | факт | во входах | нашёл | источник |, разделители « — », « – », « | », JSON-блок {"discrepancies": [{fact,
input_value, found_value, source}]} (или phase1_value/agent_value). «нет» / «расхождений нет» — пустой блок.

Результат: data/fact-check.candidates.json — {version, generated, reports[{file, agent, found, format, count}],
candidates[{id FC001…, fact, phase1_value, agent_value, proposed_value, source, sources, agents, reports[{file, line}],
conflict, variants[{value, agents}], known, resolved_value, status: candidate}]}. Одинаковые факты (без регистра и
пунктуации) сливаются; разные найденные значения → conflict = true и variants, proposed_value — самое частое.
known = true, если факт уже есть в data/fact-check.json (тогда resolved_value оттуда).
--merge — дописать новые (не known) кандидаты в data/fact-check.json записями {fact, phase1_value, agent_value, source,
resolved_value: null, note} — их остаётся подтвердить.
Код выхода: 0; 2 — нет папки <OUT>/data. Только стандартная библиотека.
"""
import argparse
import json
import re
import sys
from collections import Counter
from datetime import date
from pathlib import Path

HEAD = re.compile(r"^(#{1,6})\s*(?:\d+[.)]\s*)?\**\s*расхождения\s+(?:с\s+)?факт", re.I)
ITEM = re.compile(r"^(\s*)(?:\d+[.)]|[-*+])\s+\**\s*расхождения\s+(?:с\s+)?факт[^:\n]*?(?:\**:\**\s*(.*))?$", re.I)
ANY_HEAD = re.compile(r"^#{1,6}\s")
TOP_ITEM = re.compile(r"^(?:\d+[.)])\s")
SEP = re.compile(r"\s+[—–]\s+|\s+\|\s+|\s+-{1,2}\s+")
NONE_RE = re.compile(r"^\W*(?:нет|расхождений\s+нет|не\s+найдено|none|no)\W*$", re.I)
JSON_FENCE = re.compile(r"```(?:json)?\s*\n(.*?)\n```", re.S)


def load_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default
    except (OSError, json.JSONDecodeError) as e:
        print("предупреждение: не удалось прочитать %s: %s" % (path, e), file=sys.stderr)
        return default


def norm(s):
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", str(s or "").lower())).strip()


def clean(s):
    s = re.sub(r"^\s*(?:[-*+]|\d+[.)])\s+", "", s.strip())
    s = re.sub(r"\*\*|__|`", "", s)
    return s.strip().strip("|").strip()


def split_entry(s):
    """«факт — во входах — нашёл — источник» → dict или None."""
    s = clean(s)
    if not s or NONE_RE.match(s):
        return None
    if s.count("|") >= 3:
        cells = [c.strip() for c in s.strip("|").split("|")]
    else:
        cells = [c.strip() for c in SEP.split(s)]
    cells = [c for c in cells if c != ""]
    if len(cells) < 3:
        return None
    if re.fullmatch(r":?-{3,}:?", cells[0]) or norm(cells[0]) in ("факт", "fact"):
        return None                                   # разделитель или заголовок таблицы
    fact, inp, found = cells[0], cells[1], cells[2]
    src = " — ".join(cells[3:]) if len(cells) > 3 else ""
    return {"fact": fact.rstrip(":"), "input_value": inp, "found_value": found, "source": src}


def from_json(text):
    out = []
    for m in JSON_FENCE.finditer(text):
        try:
            d = json.loads(m.group(1))
        except ValueError:
            continue
        items = d.get("discrepancies") if isinstance(d, dict) else None
        if not isinstance(items, list):
            continue
        line = text.count("\n", 0, m.start()) + 2
        for it in items:
            if isinstance(it, dict) and it.get("fact"):
                out.append({"fact": str(it["fact"]), "input_value": str(it.get("input_value", it.get("phase1_value", "")) or ""),
                            "found_value": str(it.get("found_value", it.get("agent_value", "")) or ""),
                            "source": str(it.get("source") or ""), "line": line})
    return out


def parse_report(text):
    """→ (записи, формат, найден ли блок)."""
    rows = from_json(text)
    if rows:
        return rows, "json", True
    lines = text.splitlines()
    i, found, fmt = 0, False, "none"
    while i < len(lines):
        line = lines[i]
        mh = HEAD.match(line)
        mi = None if mh else ITEM.match(line)
        if not mh and not mi:
            i += 1
            continue
        found = True
        if mh:
            level = len(mh.group(1))
            j = i + 1
            while j < len(lines):
                hm = re.match(r"^(#{1,6})\s", lines[j])
                if hm and len(hm.group(1)) <= level:
                    break
                j += 1
            body = [(k + 1, lines[k]) for k in range(i + 1, j)]
            fmt = "block"
        else:
            indent = len(mi.group(1))
            body = []
            rest = (mi.group(2) or "").strip()
            if rest:
                body += [(i + 1, piece) for piece in re.split(r";\s+(?=[^;]+\s[—–|]\s)", rest)]
            j = i + 1
            while j < len(lines):
                s = lines[j]
                if ANY_HEAD.match(s) or (TOP_ITEM.match(s) and len(s) - len(s.lstrip()) <= indent):
                    break
                if not s.strip() and j + 1 < len(lines) and lines[j + 1].strip() and not lines[j + 1].startswith((" ", "\t", "-", "*", "|")):
                    break
                body.append((j + 1, s))
                j += 1
            fmt = "item"
        for ln, s in body:
            e = split_entry(s)
            if e:
                e["line"] = ln
                rows.append(e)
        if any(lines[k].strip().startswith("|") for k in range(i + 1, min(j, len(lines)))):
            fmt = "table" if fmt == "block" else fmt
        i = j
    return rows, fmt, found


def collect(out, files):
    reports, entries = [], []
    for f in files:
        try:
            text = Path(f).read_text(encoding="utf-8")
        except OSError as e:
            reports.append({"file": str(f), "agent": Path(f).stem, "found": False, "format": "error", "count": 0, "note": str(e)})
            continue
        rows, fmt, found = parse_report(text)
        try:
            rel = Path(f).resolve().relative_to(out).as_posix()
        except ValueError:
            rel = str(f)
        agent = Path(f).stem
        reports.append({"file": rel, "agent": agent, "found": found, "format": fmt, "count": len(rows),
                        "note": "" if found else "нет блока «Расхождения с фактами» (формат — templates/briefs/_report-footer.md)"})
        for r in rows:
            entries.append(dict(r, agent=agent, file=rel))
    fc = load_json(out / "data" / "fact-check.json", None)
    fc_items = fc if isinstance(fc, list) else (fc.get("items") or fc.get("discrepancies") or fc.get("checks") or []) if isinstance(fc, dict) else []
    known = {}
    for it in fc_items:
        if isinstance(it, dict):
            k = norm(it.get("fact") or it.get("claim") or it.get("topic") or "")
            if k:
                known[k] = it
    groups = {}
    for e in entries:
        groups.setdefault(norm(e["fact"]), []).append(e)
    cands = []
    for k, es in groups.items():
        values = Counter(norm(e["found_value"]) for e in es)
        by_val = {}
        for e in es:
            by_val.setdefault(norm(e["found_value"]), {"value": e["found_value"], "agents": []})["agents"].append(e["agent"])
        top = values.most_common(1)[0][0]
        kn = known.get(k)
        cands.append({
            "fact": es[0]["fact"], "phase1_value": es[0]["input_value"], "agent_value": by_val[top]["value"],
            "proposed_value": by_val[top]["value"], "source": es[0]["source"],
            "sources": sorted({e["source"] for e in es if e["source"]}), "agents": sorted({e["agent"] for e in es}),
            "reports": [{"file": e["file"], "line": e.get("line")} for e in es],
            "conflict": len(by_val) > 1, "variants": list(by_val.values()) if len(by_val) > 1 else [],
            "known": kn is not None, "resolved_value": (kn or {}).get("resolved_value") if kn else None, "status": "candidate"})
    cands.sort(key=lambda c: (c["known"], not c["conflict"], norm(c["fact"])))
    for n, c in enumerate(cands, 1):
        c["id"] = "FC%03d" % n
    return {"version": 1, "generated": date.today().isoformat(), "reports": reports, "candidates": cands}


def merge_into_fact_check(out, doc):
    path = out / "data" / "fact-check.json"
    fc = load_json(path, None)
    holder = fc if isinstance(fc, list) else (fc.setdefault("items", []) if isinstance(fc, dict) else None)
    if holder is None:
        fc = holder = []
    added = 0
    for c in doc["candidates"]:
        if c["known"]:
            continue
        holder.append({"fact": c["fact"], "phase1_value": c["phase1_value"], "agent_value": c["agent_value"],
                       "source": "; ".join(c["agents"]) + (" — " + c["source"] if c["source"] else ""), "resolved_value": None,
                       "note": "кандидат collect_reports %s%s" % (c["id"], "; конфликт: " + " / ".join(v["value"] for v in c["variants"]) if c["conflict"] else "")})
        added += 1
    path.write_text(json.dumps(fc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return added


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0], formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out", help="папка прогона <OUT>")
    ap.add_argument("reports", nargs="*", help="файлы отчётов (по умолчанию build/agent-reports/*.md)")
    ap.add_argument("--merge", action="store_true", help="дописать новые кандидаты в data/fact-check.json (resolved_value: null)")
    ap.add_argument("--json", action="store_true", help="печатать результат JSON")
    a = ap.parse_args(argv)
    out = Path(a.out).resolve()
    if not (out / "data").is_dir():
        print("ошибка: нет папки %s/data" % out, file=sys.stderr)
        return 2
    files = [Path(f) for f in a.reports] or sorted((out / "build" / "agent-reports").glob("*.md")) + sorted((out / "build" / "agent-reports").glob("*.txt"))
    doc = collect(out, files)
    dest = out / "data" / "fact-check.candidates.json"
    dest.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    added = merge_into_fact_check(out, doc) if a.merge else 0
    if a.json:
        print(json.dumps(dict(doc, merged=added), ensure_ascii=False, indent=2))
        return 0
    if not files:
        print("отчётов нет (build/agent-reports/*.md) — сохраняйте последнее сообщение агента туда; записан пустой %s" % dest)
        return 0
    for r in doc["reports"]:
        print("%-40s %s, записей %d%s" % (r["file"], r["format"], r["count"], (" — " + r["note"]) if r["note"] else ""))
    for c in doc["candidates"]:
        print("%s %s: «%s» → «%s» (%s)%s%s" % (c["id"], c["fact"], c["phase1_value"], c["proposed_value"], ", ".join(c["agents"]),
                                           " КОНФЛИКТ: " + " / ".join(v["value"] for v in c["variants"]) if c["conflict"] else "",
                                           " [уже в fact-check.json]" if c["known"] else ""))
    print("кандидатов %d (конфликтов %d) → %s%s" % (len(doc["candidates"]), sum(c["conflict"] for c in doc["candidates"]), dest,
                                                   "; в fact-check.json добавлено %d" % added if a.merge else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
