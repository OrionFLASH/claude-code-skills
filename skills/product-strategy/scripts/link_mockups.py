#!/usr/bin/env python3
"""Обратное связывание макетов с предложениями: data/proposals.json ← mockups-index.json и design-refs/*.json.

  link_mockups.py <OUT> [--dry-run] [--strict] [--json]

Что делает:
  - читает data/mockups-index.json (`proposals` каждого макета) и design-refs/*.json (`file` + `proposals` каждой карточки);
  - выставляет в data/proposals.json поля `mockups` (все макеты предложения, по порядку индекса) и `mockup` (первый;
    если прежний `mockup` существует и входит в набор — он остаётся первым). Значения — пути вида `concepts/<ключ>.html`
    (путь относительно mockups/), как в контракте;
  - предупреждает: о макетах без предложений (служебные `_base`, `_kit` — только заметка), об id в индексе/карточках,
    которых нет в реестре, о карточках design-refs с макетом, которого нет в индексе, и о предложениях, где `mockup`
    указывает на несуществующий файл (такое значение заменяется, если у предложения есть другие макеты, иначе остаётся);
  - ничего не удаляет: предложения без макетов не меняются. Повторный запуск не меняет файл (идемпотентно).

--dry-run — показать изменения, файл не писать; --strict — код 1, если есть предупреждения.
Код выхода: 0 — готово (предупреждения допустимы); 1 — есть предупреждения при --strict; 2 — нет data/proposals.json.
Только стандартная библиотека.
"""
import argparse
import json
import sys
from pathlib import Path


def load_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default
    except (OSError, json.JSONDecodeError) as e:
        print("предупреждение: не удалось прочитать %s: %s" % (path, e), file=sys.stderr)
        return default


def rel_html(path):
    """'mockups/concepts/M01-x.html' → 'concepts/M01-x.html'."""
    p = str(path).replace("\\", "/") if path else ""
    while p.startswith("./"):
        p = p[2:]
    return p[len("mockups/"):] if p.startswith("mockups/") else p


def exists(out, rel):
    return bool(rel) and ((out / "mockups" / rel).exists() or (out / rel).exists())


def reorder(p, add):
    """Вставляет `mockups` сразу после `mockup`, сохраняя порядок остальных полей."""
    new = {}
    for k, v in p.items():
        if k == "mockups":
            continue
        new[k] = v
        if k == "mockup":
            new["mockups"] = add
    if "mockups" not in new:
        new["mockups"] = add
    return new


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0], formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out", help="папка прогона <OUT>")
    ap.add_argument("--dry-run", action="store_true", help="не писать data/proposals.json")
    ap.add_argument("--strict", action="store_true", help="код выхода 1, если есть предупреждения")
    ap.add_argument("--json", action="store_true", help="печатать отчёт JSON")
    a = ap.parse_args(argv)
    out = Path(a.out).resolve()
    pp = out / "data" / "proposals.json"
    props = load_json(pp, None)
    if not isinstance(props, list):
        print("ошибка: нет или не читается %s" % pp, file=sys.stderr)
        return 2
    ids = {p.get("id") for p in props if isinstance(p, dict)}
    warnings, notes = [], []

    # макеты предложений: id → [html-путь…] в порядке индекса, затем карточек design-refs
    linked, index_keys, orphans = {}, set(), []
    index = load_json(out / "data" / "mockups-index.json", None)
    if not isinstance(index, list):
        index = []
        warnings.append("нет data/mockups-index.json: связывание только по design-refs/*.json")
    for m in index:
        if not isinstance(m, dict) or not m.get("key"):
            continue
        html = rel_html(m.get("html") or "concepts/%s.html" % m["key"])
        index_keys.add(html)
        plist = [x for x in (m.get("proposals") or []) if x]
        if not plist:
            (notes if str(m["key"]).startswith("_") else warnings).append("макет %s без предложений" % m["key"])
            orphans.append(m["key"])
        for pid in plist:
            if pid not in ids:
                warnings.append("макет %s: предложения %s нет в реестре" % (m["key"], pid))
                continue
            linked.setdefault(pid, [])
            if html not in linked[pid]:
                linked[pid].append(html)
    for f in sorted((out / "design-refs").glob("*.json")):
        card = load_json(f, None)
        if not isinstance(card, dict) or not card.get("file"):
            continue
        html = rel_html(card["file"])
        if index and html not in index_keys:
            warnings.append("карточка %s: макета %s нет в mockups-index.json" % (f.name, html))
        for pid in card.get("proposals") or []:
            if pid not in ids:
                warnings.append("карточка %s: предложения %s нет в реестре" % (f.name, pid))
                continue
            linked.setdefault(pid, [])
            if html not in linked[pid]:
                linked[pid].append(html)

    changed, result = [], []
    for p in props:
        if not isinstance(p, dict) or not p.get("id"):
            result.append(p)
            continue
        pid, cur = p["id"], p.get("mockup")
        mine = list(linked.get(pid, []))
        cur_ok = bool(cur) and exists(out, rel_html(cur))
        if cur and not cur_ok:
            warnings.append("%s: mockup указывает на несуществующий файл %s" % (pid, cur))
        if cur and cur_ok and rel_html(cur) not in mine:
            warnings.append("%s: mockup %s не связан в mockups-index.json/design-refs" % (pid, cur))
            mine.append(rel_html(cur))
        if not mine:
            result.append(p)
            continue
        first = rel_html(cur) if cur_ok and rel_html(cur) in mine else mine[0]
        rest = [x for x in mine if x != first]
        allm = [first] + rest
        if p.get("mockup") == first and p.get("mockups") == allm:
            result.append(p)
            continue
        q = reorder(dict(p, mockup=first), allm)
        result.append(q)
        changed.append({"id": pid, "mockup": first, "mockups": allm, "was": cur})
    report = {"ok": True, "dry_run": a.dry_run, "proposals": len(props), "linked_proposals": len(linked), "changed": len(changed),
              "changes": changed, "warnings": warnings, "notes": notes, "orphan_mockups": orphans}
    if changed and not a.dry_run:
        pp.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if a.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print("%s: предложений с макетами %d, изменено %d%s" % (pp, len(linked), len(changed), " (dry-run, файл не записан)" if a.dry_run else ""))
        for c in changed[:30]:
            print("  %s: mockup=%s; всего макетов %d%s" % (c["id"], c["mockup"], len(c["mockups"]), " (было %s)" % c["was"] if c["was"] and c["was"] != c["mockup"] else ""))
        if len(changed) > 30:
            print("  … и ещё %d" % (len(changed) - 30))
        for n in notes:
            print("заметка: %s" % n)
        for w in warnings:
            print("предупреждение: %s" % w)
    return 1 if a.strict and warnings else 0


if __name__ == "__main__":
    sys.exit(main())
