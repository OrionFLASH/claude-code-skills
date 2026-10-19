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
--merge (то же — --fact-check) — дописать новые (не known) кандидаты в data/fact-check.json записями {fact, phase1_value,
agent_value, source, resolved_value: null, note, fix: null, applied: false[, fix_hint]} — их остаётся подтвердить
(resolved_value) и указать, что исправить в JSON-источнике: fix {file, path, value} (применяет apply_fact_check.py)
или text_only: true (расхождение только в тексте). fix_hint — подсказка, где искать: карточка конкурента
data/competitors.json ([slug=…]) или параметр build/model-params.json, если их имя встречается в факте.

  collect_reports.py <OUT> --deps [--into-overrides]   второй раунд зависимостей (C7.5, FB-051)
Строки отчётов авторов `ПРЕДПОСЫЛКА: P038 ← P033, P111 | почему` (также `<-`, `PREREQ:`) → build/deps-patch.json —
патч overrides {"P038": {"_add": {"dependencies": ["P033", "P111"]}}} + _summary и _reasons. Пропускаются (с причиной):
неизвестные P-id, самоссылки, уже записанные зависимости, пары, замыкающие цикл. Применить:
merge_proposals.py <OUT> --apply-overrides build/deps-patch.json, затем score.py и Гант. --into-overrides — дописать те
же _add в build/overrides.json (переживут следующее полное слияние).

  collect_reports.py <OUT> --retro                     ретроспектива прогона (FB-004)
build/retro.md + build/retro.json: журнал вмешательств build/interventions.jsonl (строки JSON {ts, by: owner|orchestrator,
what, why, file, phase?, kind?}; пишет init_run.py --intervention), автообнаружение того, чего нет в журнале: ручные брифы
(build/briefs/*.md без шаблона в templates/briefs), правки build/overrides.json, build/model-params.json (параметры с
меткой не «допущение» или файл новее data/model.json), build/merge-map.json, патчи build/deps-patch.json; блоки
«Отступления от брифа» из отчётов агентов; упавшие и пропущенные шаги build/build-all-last.json; неприменённые записи
data/fact-check.json. Разделы — как в фидбэках прогонов: владелец / оркестратор вне скилла / агенты / дефекты и ворота.
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


def fix_hint(out, fact, source=""):
    """Где в JSON-источниках, вероятно, живёт факт: карточка конкурента или параметр модели (только подсказка)."""
    text = norm("%s %s" % (fact, source))
    comps = load_json(out / "data" / "competitors.json", []) or []
    for c in comps if isinstance(comps, list) else []:
        if not isinstance(c, dict) or c.get("self"):
            continue
        names = [n for n in (c.get("name"), c.get("slug")) if n]
        if any(norm(n) and re.search(r"(^|\s)%s(\s|$)" % re.escape(norm(n)), text) for n in names):
            return {"file": "data/competitors.json", "select": "[slug=%s]" % c.get("slug"), "fields": ["price", "monetization", "features"]}
    params = load_json(out / "build" / "model-params.json", {}) or {}
    for k, v in params.items() if isinstance(params, dict) else []:
        if isinstance(v, dict) and "value" in v and (k.lower() in text.replace(" ", "_") or norm(k.replace("_", " ")) in text):
            return {"file": "build/model-params.json", "path": "%s.value" % k}
    return None


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
        rec = {"fact": c["fact"], "phase1_value": c["phase1_value"], "agent_value": c["agent_value"],
               "source": "; ".join(c["agents"]) + (" — " + c["source"] if c["source"] else ""), "resolved_value": None,
               "note": "кандидат collect_reports %s%s" % (c["id"], "; конфликт: " + " / ".join(v["value"] for v in c["variants"]) if c["conflict"] else ""),
               "fix": None, "applied": False}
        hint = fix_hint(out, c["fact"], c["source"])
        if hint:
            rec["fix_hint"] = hint
        holder.append(rec)
        added += 1
    path.write_text(json.dumps(fc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return added


# ---------------------------------------------------------------- второй раунд зависимостей (FB-051)
PREREQ_RE = re.compile(r"(?:ПРЕДПОСЫЛКА|PREREQ(?:UISITE)?)\s*:?\s*\**\s*(P\d{3,})\s*(?:←|<-|⟵|<—)\s*"
                       r"((?:P\d{3,})(?:\s*(?:,|;|и|and)\s*P\d{3,})*)\s*(?:\|\s*(.*))?$", re.I)


def parse_prereqs(text):
    """Строки `ПРЕДПОСЫЛКА: P038 ← P033, P111 | почему` → [{id, prereqs, why, line}]."""
    out = []
    for n, line in enumerate(text.splitlines(), 1):
        s = re.sub(r"\*\*|__|`", "", line).strip()
        s = re.sub(r"^\s*(?:[-*+]|\d+[.)])\s+", "", s)
        m = PREREQ_RE.search(s)
        if m:
            out.append({"id": m.group(1), "prereqs": re.findall(r"P\d{3,}", m.group(2)), "why": (m.group(3) or "").strip(),
                        "line": n})
    return out


def _reaches(graph, start, goal):
    seen, stack = set(), [start]
    while stack:
        v = stack.pop()
        if v == goal:
            return True
        if v in seen:
            continue
        seen.add(v)
        stack += graph.get(v, [])
    return False


def collect_deps(out, files):
    """→ (patch dict для build/deps-patch.json, summary)."""
    props = load_json(out / "data" / "proposals.json", []) or []
    by_id = {p.get("id"): p for p in props if isinstance(p, dict) and p.get("id")}
    gap = load_json(out / "data" / "gap-audit-deps.json", {}) or {}
    graph = {pid: [d for d in (p.get("dependencies") or []) if d in by_id] for pid, p in by_id.items()}
    for k, v in (gap.items() if isinstance(gap, dict) else []):
        if k in graph:
            graph[k] += [d for d in (v if isinstance(v, list) else [v]) if d in by_id and d not in graph[k]]
    patch, reasons, skipped, lines, reports = {}, {}, [], 0, []
    for f in files:
        try:
            text = Path(f).read_text(encoding="utf-8")
        except OSError:
            continue
        rows = parse_prereqs(text)
        try:
            rel = Path(f).resolve().relative_to(out).as_posix()
        except ValueError:
            rel = str(f)
        reports.append({"file": rel, "count": len(rows)})
        for r in rows:
            lines += 1
            dep = r["id"]
            for pre in r["prereqs"]:
                where = "%s:%d" % (rel, r["line"])
                if dep not in by_id or pre not in by_id:
                    skipped.append({"pair": "%s ← %s" % (dep, pre), "why": "нет в реестре %s" % ", ".join(x for x in (dep, pre) if x not in by_id), "where": where})
                elif dep == pre:
                    skipped.append({"pair": "%s ← %s" % (dep, pre), "why": "самоссылка", "where": where})
                elif pre in graph.get(dep, []):
                    skipped.append({"pair": "%s ← %s" % (dep, pre), "why": "уже записано", "where": where})
                elif _reaches(graph, pre, dep):
                    skipped.append({"pair": "%s ← %s" % (dep, pre), "why": "замкнёт цикл (%s уже зависит от %s)" % (pre, dep), "where": where})
                else:
                    graph.setdefault(dep, []).append(pre)
                    patch.setdefault(dep, {"_add": {"dependencies": []}})["_add"]["dependencies"].append(pre)
                    reasons.setdefault(dep, []).append({"prereq": pre, "why": r["why"], "where": where, "agent": Path(f).stem})
    added = sum(len(v["_add"]["dependencies"]) for v in patch.values())
    summary = {"generated": date.today().isoformat(), "reports": len(files), "lines": lines, "added": added,
               "proposals": len(patch), "skipped": skipped, "by_report": reports}
    doc = {"_comment": "collect_reports.py --deps: второй раунд зависимостей из строк «ПРЕДПОСЫЛКА:» отчётов авторов. "
                       "Применить: merge_proposals.py <OUT> --apply-overrides build/deps-patch.json; затем score.py и Гант.",
           "_summary": summary, "_reasons": reasons}
    doc.update(patch)
    return doc, summary


def deps_into_overrides(out, patch):
    """Дописать _add.dependencies патча в build/overrides.json (объединение без повторов). → число добавленных."""
    path = out / "build" / "overrides.json"
    ov = load_json(path, {}) or {}
    if not isinstance(ov, dict):
        return 0
    n = 0
    for pid, p in patch.items():
        if pid.startswith("_"):
            continue
        cur = ov.setdefault(pid, {}).setdefault("_add", {}).setdefault("dependencies", [])
        for d in p["_add"]["dependencies"]:
            if d not in cur:
                cur.append(d)
                n += 1
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(ov, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return n


# ---------------------------------------------------------------- ретроспектива (FB-004)
DEVIATION_HEAD = re.compile(r"^(#{1,6})\s*(?:\d+[.)]\s*)?\**\s*отступлени\w*\s+от\s+брифа", re.I)
DEVIATION_ITEM = re.compile(r"^(\s*)(?:\d+[.)]|[-*+])\s+\**\s*отступлени\w*\s+от\s+брифа[^:\n]*?(?:\**:\**\s*(.*))?$", re.I)
SKILL_BRIEFS = Path(__file__).resolve().parent.parent / "templates" / "briefs"


def block_lines(text, head_re, item_re):
    """Строки блока по заголовку (#…) или пункту списка «N. Название: …» → [(номер строки, текст)]."""
    lines = text.splitlines()
    out = []
    i = 0
    while i < len(lines):
        mh, mi = head_re.match(lines[i]), item_re.match(lines[i])
        if not mh and not mi:
            i += 1
            continue
        if mh:
            level = len(mh.group(1))
            j = i + 1
            while j < len(lines):
                hm = re.match(r"^(#{1,6})\s", lines[j])
                if hm and len(hm.group(1)) <= level:
                    break
                j += 1
            body = [(k + 1, lines[k]) for k in range(i + 1, j)]
        else:
            body = [(i + 1, mi.group(2))] if (mi.group(2) or "").strip() else []
            indent = len(mi.group(1))
            j = i + 1
            while j < len(lines) and lines[j].strip() and (len(lines[j]) - len(lines[j].lstrip()) > indent):
                body.append((j + 1, lines[j]))
                j += 1
        for n, s in body:
            c = clean(s)
            if c and not NONE_RE.match(c):
                out.append((n, c))
        i = j
    return out


def read_interventions(out):
    path = out / "build" / "interventions.jsonl"
    rows = []
    if not path.exists():
        return rows
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except ValueError:
            rows.append({"by": "не указано", "what": line, "why": "", "file": "", "source": "interventions.jsonl:%d (не JSON)" % n})
            continue
        if not isinstance(r, dict):
            continue
        files = r.get("files") if isinstance(r.get("files"), list) else ([r["file"]] if r.get("file") else [])
        by = str(r.get("by") or "не указано").lower()
        rows.append({"by": by if by in ("owner", "orchestrator", "agent") else by, "what": str(r.get("what") or r.get("text") or ""),
                     "why": str(r.get("why") or ""), "file": ", ".join(map(str, files)), "phase": r.get("phase"),
                     "kind": r.get("kind"), "ts": r.get("ts") or r.get("date"), "source": "interventions.jsonl:%d" % n})
    return rows


def template_names():
    return {p.stem for p in SKILL_BRIEFS.glob("*.md")} if SKILL_BRIEFS.is_dir() else set()


def is_rendered_brief(name, templates):
    parts = name.split("-")
    return any("-".join(parts[:k]) in templates for k in range(len(parts), 0, -1))


def collect_retro(out, files):
    journal = read_interventions(out)
    covered = " ".join("%s %s" % (r["file"], r["what"]) for r in journal)
    auto = []

    def add(what, file, why, kind):
        if file and file in covered:
            return
        auto.append({"by": "orchestrator", "what": what, "why": why, "file": file, "kind": kind,
                     "source": "автообнаружение (уточните: init_run.py <OUT> --intervention … --by owner|orchestrator)"})
    tpl = template_names()
    bdir = out / "build" / "briefs"
    for f in sorted(bdir.glob("*.md")) if bdir.is_dir() else []:
        if not is_rendered_brief(f.stem, tpl):
            add("ручной бриф %s (нет шаблона в templates/briefs)" % f.name, "build/briefs/%s" % f.name,
                "шаблона под задачу в скилле нет", "brief")
    ov = load_json(out / "build" / "overrides.json", None)
    if isinstance(ov, dict):
        keys = [k for k in ov if not str(k).startswith("_")]
        if keys:
            add("ручные правки реестра build/overrides.json: %s" % ", ".join(keys[:15]) + (" и ещё %d" % (len(keys) - 15) if len(keys) > 15 else ""),
                "build/overrides.json", "правки, которые должны пережить слияние", "edit")
    mp = out / "build" / "model-params.json"
    params = load_json(mp, None)
    if isinstance(params, dict):
        edited = [k for k, v in params.items() if isinstance(v, dict) and v.get("label") and v.get("label") != "допущение"]
        model = out / "data" / "model.json"
        newer = model.exists() and mp.stat().st_mtime > model.stat().st_mtime + 1
        if edited or newer:
            add("правка параметров модели build/model-params.json%s%s" % (
                ": " + ", ".join(edited[:12]) if edited else "", "; файл новее data/model.json — model.py не перезапущен" if newer else ""),
                "build/model-params.json", "параметры профиля не подошли продукту", "edit")
    mm = load_json(out / "build" / "merge-map.json", None)
    if isinstance(mm, dict) and (mm.get("distinct") or mm.get("merge")) and "--write-distinct" not in str(mm.get("_comment", "")):
        add("решения слияния в build/merge-map.json вписаны вручную (distinct %d, merge %d)" % (len(mm.get("distinct") or []), len(mm.get("merge") or [])),
            "build/merge-map.json", "нет --write-distinct", "edit")
    dp = load_json(out / "build" / "deps-patch.json", None)
    deps_added = ((dp or {}).get("_summary") or {}).get("added") if isinstance(dp, dict) else None
    deviations = []
    for f in files:
        try:
            text = Path(f).read_text(encoding="utf-8")
        except OSError:
            continue
        try:
            rel = Path(f).resolve().relative_to(out).as_posix()
        except ValueError:
            rel = str(f)
        for n, s in block_lines(text, DEVIATION_HEAD, DEVIATION_ITEM):
            deviations.append({"agent": Path(f).stem, "text": s, "where": "%s:%d" % (rel, n)})
    last = load_json(out / "build" / "build-all-last.json", {}) or {}
    gates = []
    for st in last.get("steps") or []:
        if not isinstance(st, dict):
            continue
        note = str(st.get("note") or "")
        if st.get("status") in ("FAIL", "SKIP") or re.search(r"предупрежд|warn|!\s", note, re.I):
            gates.append({"step": st.get("step"), "status": st.get("status"), "note": note})
    fc = load_json(out / "data" / "fact-check.json", None)
    items = fc if isinstance(fc, list) else ((fc.get("items") or fc.get("discrepancies") or fc.get("checks") or []) if isinstance(fc, dict) else [])
    open_fc = [it for it in items if isinstance(it, dict) and not it.get("applied") and not it.get("text_only")
               and "только текст" not in str(it.get("note") or "")]
    entries = journal + auto
    return {"version": 1, "generated": date.today().isoformat(), "entries": entries, "journal": len(journal), "auto": len(auto),
            "by_owner": sum(1 for e in entries if e["by"] == "owner"),
            "by_orchestrator": sum(1 for e in entries if e["by"] == "orchestrator"),
            "deviations": deviations, "gates": gates, "fact_check_open": [str(it.get("fact") or it.get("claim") or "") for it in open_fc],
            "deps_added": deps_added, "build_all": {"date": last.get("date"), "summary": last.get("summary")} if last else None}


def render_retro(doc, product=""):
    def row(e):
        return "| %s | %s | %s | %s | %s |" % (e.get("what", "").replace("|", "/"), e.get("why", "").replace("|", "/") or "—",
                                               e.get("file") or "—", e.get("phase") or "—", e.get("source", ""))
    L = ["# Ретроспектива прогона%s" % (" — " + product if product else ""), "",
         "Собрано `collect_reports.py --retro` %s. Журнал вмешательств — `build/interventions.jsonl` (%d записей), "
         "автообнаружение — %d. Владелец: %d, оркестратор: %d." % (doc["generated"], doc["journal"], doc["auto"],
                                                                 doc["by_owner"], doc["by_orchestrator"]), ""]
    head = "| что | почему | файл | фаза | источник |\n|---|---|---|---|---|"
    for title, by in (("## 1. Что добавил или решил владелец (by: owner)", "owner"),
                      ("## 2. Что оркестратор делал вне скилла (by: orchestrator)", "orchestrator")):
        rows = [e for e in doc["entries"] if e["by"] == by]
        L += [title, ""] + ([head] + [row(e) for e in rows] if rows else ["Нет записей."]) + [""]
    other = [e for e in doc["entries"] if e["by"] not in ("owner", "orchestrator")]
    if other:
        L += ["### Без указания автора (by)", "", head] + [row(e) for e in other] + [""]
    L += ["## 3. Отступления агентов от брифов", ""]
    L += ["- **%s**: %s (`%s`)" % (d["agent"], d["text"], d["where"]) for d in doc["deviations"]] or ["Нет (или блок «Отступления от брифа» в отчётах не заполнялся)."]
    L += ["", "## 4. Дефекты скриптов и предупреждения ворот", ""]
    if doc.get("build_all"):
        L += ["Последний полный `build_all.py` (%s): %s" % (doc["build_all"].get("date") or "?", doc["build_all"].get("summary") or "?"), ""]
    L += ["- %s — %s: %s" % (g["step"], g["status"], g["note"] or "—") for g in doc["gates"]] or ["Упавших и пропущенных шагов нет."]
    L += ["", "## 5. Данные после текстов", "",
          "- Зависимостей добавлено вторым раундом (`build/deps-patch.json`): %s" % (doc["deps_added"] if doc["deps_added"] is not None else "раунд не запускался"),
          "- Записей fact-check без `applied` и без `text_only`: %d%s" % (len(doc["fact_check_open"]), (" — " + "; ".join(doc["fact_check_open"][:10])) if doc["fact_check_open"] else ""),
          ""]
    return "\n".join(L)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0], formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out", help="папка прогона <OUT>")
    ap.add_argument("reports", nargs="*", help="файлы отчётов (по умолчанию build/agent-reports/*.md)")
    ap.add_argument("--merge", action="store_true", help="дописать новые кандидаты в data/fact-check.json (resolved_value: null)")
    ap.add_argument("--fact-check", action="store_true", help="то же, что --merge (черновик записей fact-check с полями fix/applied)")
    ap.add_argument("--deps", action="store_true", help="строки «ПРЕДПОСЫЛКА:» отчётов → build/deps-patch.json")
    ap.add_argument("--into-overrides", action="store_true", help="с --deps: дописать зависимости и в build/overrides.json")
    ap.add_argument("--retro", action="store_true", help="ретроспектива: build/retro.md + build/retro.json")
    ap.add_argument("--json", action="store_true", help="печатать результат JSON")
    a = ap.parse_args(argv)
    out = Path(a.out).resolve()
    if not (out / "data").is_dir():
        print("ошибка: нет папки %s/data" % out, file=sys.stderr)
        return 2
    files = [Path(f) for f in a.reports] or sorted((out / "build" / "agent-reports").glob("*.md")) + sorted((out / "build" / "agent-reports").glob("*.txt"))
    if a.deps:
        patch, s = collect_deps(out, files)
        (out / "build").mkdir(parents=True, exist_ok=True)
        (out / "build" / "deps-patch.json").write_text(json.dumps(patch, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        n_ov = deps_into_overrides(out, patch) if a.into_overrides and s["added"] else 0
        if a.json:
            print(json.dumps(patch, ensure_ascii=False, indent=2))
            return 0
        print("Строк «ПРЕДПОСЫЛКА:» %d в %d отчётах; добавить зависимостей %d у %d предложений; пропущено %d"
              % (s["lines"], s["reports"], s["added"], s["proposals"], len(s["skipped"])))
        for k in sorted(x for x in patch if not x.startswith("_")):
            print("  %s ← %s" % (k, ", ".join(patch[k]["_add"]["dependencies"])))
        for sk in s["skipped"][:20]:
            print("  - пропущено %s: %s (%s)" % (sk["pair"], sk["why"], sk["where"]))
        print("Записано: build/deps-patch.json%s. Дальше: merge_proposals.py <OUT> --apply-overrides build/deps-patch.json; "
              "score.py; Гант" % ("; в build/overrides.json добавлено %d" % n_ov if a.into_overrides else ""))
        return 0
    if a.retro:
        doc = collect_retro(out, files)
        cfg = load_json(out / "build" / "run-config.json", {}) or {}
        (out / "build").mkdir(parents=True, exist_ok=True)
        (out / "build" / "retro.json").write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (out / "build" / "retro.md").write_text(render_retro(doc, ((cfg.get("product") or {}).get("name") or "")) + "\n", encoding="utf-8")
        if a.json:
            print(json.dumps(doc, ensure_ascii=False, indent=2))
            return 0
        print("Ретроспектива: записей %d (журнал %d, автообнаружение %d; владелец %d, оркестратор %d), отступлений агентов %d, "
              "предупреждений ворот %d, fact-check без applied %d → build/retro.md, build/retro.json"
              % (len(doc["entries"]), doc["journal"], doc["auto"], doc["by_owner"], doc["by_orchestrator"], len(doc["deviations"]),
                 len(doc["gates"]), len(doc["fact_check_open"])))
        return 0
    a.merge = a.merge or a.fact_check
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
