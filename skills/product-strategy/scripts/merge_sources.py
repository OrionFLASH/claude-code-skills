#!/usr/bin/env python3
"""Слияние источников: data/sources-*.json (фрагменты агентов) + data/sources.json → единый data/sources.json.

  merge_sources.py <OUT> [--dry-run] [--keep-ids] [--allow-example] [--from-glob GLOB ...] [--strict] [--json]

Что делает:
  1. База — существующий data/sources.json, затем фрагменты data/sources-*.json (по имени файла).
  2. Дедупликация по нормализованному URL: схема и хост в нижнем регистре, без якоря (#…), без utm_*/gclid/fbclid/yclid,
     без хвостового «/». Дубли сливаются в первую запись: `used_for` и `note` объединяются через «; », пустой `title`
     берётся у дубля. Поля `status` и `date_checked` записей из прежнего sources.json НЕ меняются.
  3. Недостающие URL добавляются из: data/proposals.json (evidence[].url, steps[].doc_url), data/kanban.json (cards[].links),
     data/competitors.json (url, sources[]), research/strategy.md и research/specs/*.md (http(s)-ссылки в тексте).
     Для новых записей `status` и `date_checked` = null (проверит check_links.py), `used_for` — откуда взят URL.
  4. Плейсхолдеры отбрасываются с предупреждением: `https://…`, `<…>`, `{…}`, `example.*` (--allow-example оставляет example.*
     для демо-данных), незакрытые скобки, URL без домена. Уже существующие записи не удаляются (только предупреждение).
  5. `title` обязателен: пусто, равно URL или начинается с http(s):// → «домен / последний сегмент пути» и note «без названия».
  6. Перенумерация S001… (существующие записи идут первыми и сохраняют порядок; --keep-ids оставляет прежние id и дописывает
     новые). Если id поменялись, а в тексте стратегии/спецификаций встречаются ссылки вида S012 — предупреждение.

Отчёт: build/merge-sources-report.json и сводка «добавлено / слито / отброшено». --dry-run ничего не пишет.
Код выхода: 0 — готово (предупреждения допустимы); 1 — предупреждения при --strict; 2 — нет папки <OUT>/data.
Только стандартная библиотека.
"""
import argparse
import json
import re
import sys
from collections import Counter
from datetime import date
from pathlib import Path
from urllib.parse import parse_qsl, unquote, urlencode, urlsplit

TRACKING = {"fbclid", "gclid", "yclid", "mc_cid", "mc_eid"}
URL_RE = re.compile(r"https?://[^\s<>\]\"'`]+", re.I)
MD_LINK_RE = re.compile(r"\[([^\]\n]{1,160})\]\((https?://[^\s)]+(?:\([^)\s]*\))?[^\s)]*)\)")
FIELDS = ["id", "url", "title", "date_checked", "used_for", "status", "note"]
NO_TITLE = "без названия"


def load_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default
    except (OSError, json.JSONDecodeError) as e:
        print("предупреждение: не удалось прочитать %s: %s" % (path, e), file=sys.stderr)
        return default


def clean_url(raw):
    u = raw
    while u and u[-1] in ".,;:!?»”*":
        u = u[:-1]
    while u.endswith(")") and u.count(")") > u.count("("):
        u = u[:-1]
    return u


def url_problem(u, allow_example=False):
    if not isinstance(u, str) or not u.strip():
        return "пустой URL"
    if any(ch.isspace() for ch in u):
        return "пробел в URL"
    if "…" in u or "..." in u:
        return "плейсхолдер «…»"
    if re.search(r"[<>{}]", u):
        return "плейсхолдер <…> или {…}"
    if u.count("(") > u.count(")"):
        return "незакрытая скобка"
    try:
        p = urlsplit(u)
        host = (p.hostname or "").lower()
    except ValueError as e:
        return "неверный формат: %s" % e
    if p.scheme not in ("http", "https"):
        return "схема не http(s)"
    if not host or ("." not in host and host != "localhost"):
        return "нет домена"
    if not allow_example and re.fullmatch(r"(?:www\.)?example\.[a-z.]+", host):
        return "плейсхолдер example.*"
    return None


def norm_url(u):
    try:
        p = urlsplit(u.strip())
        port = p.port
    except ValueError:
        return u.strip()
    host = (p.hostname or "").lower()
    if port and not ((p.scheme.lower() == "http" and port == 80) or (p.scheme.lower() == "https" and port == 443)):
        host += ":%d" % port
    q = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True) if not k.lower().startswith("utm_") and k.lower() not in TRACKING]
    return "%s://%s%s%s" % (p.scheme.lower(), host, p.path.rstrip("/"), ("?" + urlencode(q)) if q else "")


def fallback_title(u):
    """«домен / последний сегмент пути»."""
    try:
        p = urlsplit(u)
        host = (p.hostname or u).lower()
    except ValueError:
        return u[:60]
    host = host[4:] if host.startswith("www.") else host
    segs = [s for s in p.path.split("/") if s]
    return "%s / %s" % (host, unquote(segs[-1])[:60]) if segs else host


def title_missing(rec):
    t = (rec.get("title") or "").strip()
    if not t:
        return True
    u = (rec.get("url") or "").strip()
    return t == u or t.rstrip("/") == u.rstrip("/") or t.lower().startswith(("http://", "https://"))


def join_unique(*parts, sep="; "):
    seen, res = set(), []
    for part in parts:
        for piece in str(part or "").split(sep.strip()):
            piece = piece.strip()
            if piece and piece not in seen:
                seen.add(piece)
                res.append(piece)
    return sep.join(res)


def origin_text(origins):
    """[('реестр', 'P001'), …] → 'реестр: P001, P002; канбан: P003'."""
    groups = {}
    for kind, ident in origins:
        groups.setdefault(kind, [])
        if ident not in groups[kind]:
            groups[kind].append(ident)
    parts = []
    for kind, ids in groups.items():
        shown = ids[:8]
        extra = "" if len(ids) <= 8 else " и ещё %d" % (len(ids) - 8)
        parts.append("%s: %s%s" % (kind, ", ".join(shown), extra) if ids != [""] else kind)
    return "; ".join(parts)


def collect_additions(out):
    """→ {сырой url: {'origins': [(вид, id)], 'title': подсказка|None}} (порядок первого появления)."""
    found = {}

    def add(u, kind, ident="", title=None):
        if isinstance(u, str) and u.strip():
            e = found.setdefault(u.strip(), {"origins": [], "title": None})
            e["origins"].append((kind, ident))
            if title and not e["title"]:
                e["title"] = title.strip()
    for p in load_json(out / "data" / "proposals.json", []) or []:
        if not isinstance(p, dict):
            continue
        for ev in p.get("evidence") or []:
            if isinstance(ev, dict):
                add(ev.get("url"), "реестр", p.get("id", "?"), ev.get("title"))
        for st in p.get("steps") or []:
            if isinstance(st, dict):
                add(st.get("doc_url"), "реестр", p.get("id", "?"))
    kb = load_json(out / "data" / "kanban.json", {}) or {}
    for c in (kb.get("cards") if isinstance(kb, dict) else []) or []:
        if isinstance(c, dict):
            for u in c.get("links") or []:
                add(u if isinstance(u, str) else (u or {}).get("url"), "канбан", c.get("id", "?"), None if isinstance(u, str) else (u or {}).get("title"))
    for c in load_json(out / "data" / "competitors.json", []) or []:
        if isinstance(c, dict):
            add(c.get("url"), "конкуренты", c.get("slug", "?"), c.get("name"))
            for u in c.get("sources") or []:
                add(u, "конкуренты", c.get("slug", "?"))
    texts = [(out / "research" / "strategy.md", "стратегия", "")]
    texts += [(f, "спецификации", f.stem) for f in sorted((out / "research" / "specs").glob("*.md"))]
    for f, kind, ident in texts:
        if not f.is_file():
            continue
        try:
            text = f.read_text(encoding="utf-8")
        except OSError:
            continue
        link_titles = {clean_url(m.group(2)): m.group(1) for m in MD_LINK_RE.finditer(text)}
        for m in URL_RE.finditer(text):
            u = clean_url(m.group(0))
            t = link_titles.get(u)
            add(u, kind, ident, None if (t and t.startswith("http")) else t)
    return found


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0], formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out", help="папка прогона <OUT>")
    ap.add_argument("--dry-run", action="store_true", help="ничего не писать, только показать итог")
    ap.add_argument("--keep-ids", action="store_true", help="не перенумеровывать: прежние id остаются, новые получают следующие номера")
    ap.add_argument("--allow-example", action="store_true", help="не считать example.* плейсхолдером (демо-данные)")
    ap.add_argument("--from-glob", action="append", default=[], metavar="GLOB", help="дополнительные фрагменты относительно <OUT> (например build/parts/sources-*.json); можно повторять")
    ap.add_argument("--strict", action="store_true", help="код 1, если есть предупреждения")
    ap.add_argument("--json", action="store_true", help="печатать отчёт JSON")
    a = ap.parse_args(argv)
    out = Path(a.out).resolve()
    if not (out / "data").is_dir():
        print("ошибка: нет папки %s/data" % out, file=sys.stderr)
        return 2
    sp = out / "data" / "sources.json"
    warnings, merged, dropped, added, retitled = [], [], [], [], []

    existing = load_json(sp, []) or []
    existing = [dict(r) for r in existing if isinstance(r, dict)]
    fragments = []
    frag_files = sorted(f for f in (out / "data").glob("sources-*.json"))
    for g in a.from_glob:
        frag_files += sorted(out.glob(g))
    seen_files = []
    for f in frag_files:
        if f in seen_files or f.name == "sources.json":
            continue
        seen_files.append(f)
        d = load_json(f, [])
        if isinstance(d, dict):
            d = d.get("sources") or []
        for r in d if isinstance(d, list) else []:
            if isinstance(r, dict):
                fragments.append((f.relative_to(out).as_posix(), dict(r)))

    records, by_key = [], {}     # records: {'rec', 'existing', 'old_id'}

    def put(rec, is_existing, src):
        u = (rec.get("url") or "").strip()
        why = url_problem(u, a.allow_example)
        if why and not is_existing:
            dropped.append({"url": u, "reason": why, "from": src})
            warnings.append("отброшен URL «%s» (%s) из %s" % (u[:80], why, src))
            return
        if why and is_existing:
            warnings.append("в существующей записи %s сомнительный URL «%s» (%s) — оставлен" % (rec.get("id", "?"), u[:80], why))
        key = norm_url(u) if u else "id:%s" % rec.get("id")
        if key in by_key:
            base = by_key[key]
            b = base["rec"]
            b["used_for"] = join_unique(b.get("used_for"), rec.get("used_for"))
            b["note"] = join_unique(b.get("note"), rec.get("note"))
            if title_missing(b) and not title_missing(rec):
                b["title"] = rec["title"]
            if not base["existing"]:
                for fld in ("date_checked", "status"):
                    if b.get(fld) in (None, "") and rec.get(fld) not in (None, ""):
                        b[fld] = rec[fld]
            merged.append({"url": u, "into": b.get("url"), "from": src})
            return
        entry = {"rec": rec, "existing": is_existing, "old_id": rec.get("id") if is_existing else None}
        records.append(entry)
        by_key[key] = entry

    for r in existing:
        put(r, True, "data/sources.json")
    for src, r in fragments:
        put(r, False, src)
    for u, info in collect_additions(out).items():
        key = norm_url(u)
        if key in by_key:
            continue
        why = url_problem(u, a.allow_example)
        if why:
            dropped.append({"url": u, "reason": why, "from": origin_text(info["origins"])})
            warnings.append("отброшен URL «%s» (%s): %s" % (u[:80], why, origin_text(info["origins"])))
            continue
        rec = {"id": "", "url": u, "title": info["title"] or "", "date_checked": None, "used_for": origin_text(info["origins"]),
               "status": None, "note": ""}
        put(rec, False, "добавлено автоматически")
        added.append({"url": u, "used_for": rec["used_for"]})

    # названия
    for e in records:
        r = e["rec"]
        if title_missing(r):
            r["title"] = fallback_title(r.get("url") or "")
            r["note"] = join_unique(r.get("note"), NO_TITLE)
            retitled.append({"url": r.get("url"), "title": r["title"]})

    # id
    id_map = {}
    if a.keep_ids:
        cnt = Counter(e["old_id"] for e in records if e["old_id"])
        keep = {i for i, c in cnt.items() if c == 1 and re.fullmatch(r"S\d+", str(i))}
        n = 0
        for e in records:
            if e["old_id"] in keep:
                continue
            while "S%03d" % (n + 1) in keep:
                n += 1
            n += 1
            e["rec"]["id"] = "S%03d" % n
            keep.add(e["rec"]["id"])
    else:
        for i, e in enumerate(records, 1):
            new = "S%03d" % i
            if e["old_id"] and e["old_id"] != new:
                id_map[e["old_id"]] = new
            e["rec"]["id"] = new
    final = []
    for e in records:
        r = e["rec"]
        ordered = {k: r.get(k) for k in FIELDS}
        ordered["note"] = ordered.get("note") or ""
        ordered["used_for"] = ordered.get("used_for") or ""
        for k, v in r.items():
            if k not in ordered:
                ordered[k] = v
        final.append(ordered)

    if id_map:
        refs = set()
        for f in [out / "research" / "strategy.md"] + sorted((out / "research" / "specs").glob("*.md")):
            if f.is_file():
                refs |= set(re.findall(r"(?<![A-Za-z0-9])S\d{3}(?!\d)", f.read_text(encoding="utf-8")))
        hit = sorted(refs & set(id_map))
        if hit:
            warnings.append("id источников изменились (%s), а в тексте стратегии/спецификаций есть ссылки на них — проверьте или используйте --keep-ids" % ", ".join(hit[:10]))

    report = {"ok": True, "date": date.today().isoformat(), "dry_run": a.dry_run, "before": len(existing), "fragments": len(fragments),
              "after": len(final), "added": added, "merged": merged, "dropped": dropped, "retitled": retitled,
              "renumbered": id_map, "fragment_files": [f.relative_to(out).as_posix() for f in seen_files], "warnings": warnings}
    if not a.dry_run:
        sp.write_text(json.dumps(final, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (out / "build").mkdir(parents=True, exist_ok=True)
        (out / "build" / "merge-sources-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if a.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print("%s: было %d, фрагментов %d, стало %d%s" % (sp, len(existing), len(fragments), len(final), " (dry-run, файл не записан)" if a.dry_run else ""))
        print("добавлено %d, слито дублей %d, отброшено %d, названий исправлено %d, id изменено %d" %
              (len(added), len(merged), len(dropped), len(retitled), len(id_map)))
        for w in warnings[:30]:
            print("предупреждение: %s" % w)
        if len(warnings) > 30:
            print("… и ещё %d предупреждений (build/merge-sources-report.json)" % (len(warnings) - 30))
    return 1 if a.strict and warnings else 0


if __name__ == "__main__":
    sys.exit(main())
