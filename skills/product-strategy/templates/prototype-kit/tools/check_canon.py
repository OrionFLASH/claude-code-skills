#!/usr/bin/env python3
"""Сквозная проверка «числа макетов = числа канона = числа ядра» для рабочего прототипа и макетов C8.

  python3 tools/check_canon.py <папка prototype | папка прогона OUT> [--canon PATH] [--mockups DIR ...] [--html FILE ...]
                               [--core] [--json]

Первый аргумент — папка прототипа (<OUT>/prototype) или сама папка прогона <OUT> (так проверяют макеты C8, когда
прототипа ещё нет; --core тогда недоступен). Канон демо-данных: --canon, иначе <OUT>/data/demo-canon.json, иначе
<prototype>/fixtures/canon.json. Канон прогона и фикстура прототипа читаются вместе: значения показа (`values`) — из
канона прогона, кейсы ядра (`cases`) — из канона прогона, а если их там нет — из fixtures/canon.json.

Формат канона (оба вида в одном файле допустимы):
  - значения показа (facts_scaffold.py --demo-canon): {"rule": "… демо …", "values": {"model.price_month": {"value": 12,
    "source": "…"}, …}, "entities": [...], "screens": {...}} — в макете data-canon="model.price_month";
  - кейсы ядра (prototype-core): {"label": "демо-данные", "cases": [{"id": "C01", "fn": "payback", "inputs": {…},
    "expected": {"поле": число|строка|null}, "mockups": ["M01-…"]}]} (или просто список кейсов) — data-canon="C01.поле".

Что проверяется:
  1. канон: есть значения или кейсы; у кейсов уникальные id и непустой expected; пометка демо-данных (label, rule или
     note со словом «демо») — иначе предупреждение;
  2. макеты (--mockups, по умолчанию <OUT>/mockups/concepts без служебных _*.html; --html — отдельные файлы): каждый
     элемент с атрибутом data-canon="<ключ>" показывает значение канона (ключ ищется сначала в values, затем как
     <id кейса>.<поле>; числа — с допуском по округлению показа: «15,07 %» ≈ 15.0712; строки — точное совпадение без
     учёта регистра и пробелов); неизвестный ключ — ошибка; число элементов с data-canon-item="<ключ>" (значки, точки,
     строки на графике) равно значению канона — так ловится «4 значка на графике, а в подписи 3»;
  3. --core: node js/core.test.js <канон с кейсами> — ядро воспроизводит канон (код выхода node).
Код выхода: 0 — расхождений нет; 1 — есть ошибки; 2 — нет канона или папки. Только стандартная библиотека.
"""
import argparse
import html
import json
import re
import subprocess
import sys
from pathlib import Path

ATTR_RE = re.compile(r'<(?P<tag>[a-zA-Z][\w-]*)(?P<attrs>[^>]*?)\bdata-canon="(?P<ref>[^"]+)"(?P<rest>[^>]*)>(?P<body>.*?)</(?P=tag)\s*>',
                     re.S)
ITEM_RE = re.compile(r'\bdata-canon-item="([^"]+)"')
TAG_RE = re.compile(r"<[^>]+>")
NUM_RE = re.compile(r"[−–-]?\d{1,3}(?:[\s  ]\d{3})+(?:[.,]\d+)?|[−–-]?\d+(?:[.,]\d+)?")


def parse_number(s):
    t = re.sub(r"[\s  ]", "", str(s)).replace("−", "-").replace("–", "-")
    if re.fullmatch(r"-?\d+,\d+", t):
        t = t.replace(",", ".")
    else:
        t = t.replace(",", "")
    try:
        return float(t)
    except ValueError:
        return None


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def split_canon(d):
    """→ (кейсы, значения {ключ: значение}, пометка демо)."""
    if isinstance(d, list):
        return d, {}, ""
    if not isinstance(d, dict):
        return [], {}, ""
    vals = {}
    for k, v in (d.get("values") or {}).items():
        vals[str(k)] = v.get("value") if isinstance(v, dict) and "value" in v else v
    label = " ".join(str(d.get(k) or "") for k in ("label", "rule", "note"))
    return list(d.get("cases") or []), vals, label


def load_canon(path, fallback=None):
    """Канон прогона (+ кейсы фикстуры прототипа, если в каноне прогона их нет) → (кейсы, значения, пометка, файл кейсов)."""
    cases, vals, label = split_canon(read_json(path))
    cases_file = Path(path) if cases else None
    if not cases and fallback and Path(fallback).exists() and Path(fallback).resolve() != Path(path).resolve():
        fc, fv, fl = split_canon(read_json(fallback))
        if fc:
            cases, cases_file = fc, Path(fallback)
            label = label or fl
        for k, v in fv.items():
            vals.setdefault(k, v)
    return cases, vals, label, cases_file


def check_canon_schema(cases, label, vals=None):
    errs, warns, seen = [], [], set()
    if not cases and not vals:
        errs.append("канон пуст: нет кейсов и значений")
    for c in cases:
        cid = c.get("id") if isinstance(c, dict) else None
        if not cid:
            errs.append("кейс без id: %r" % (c,))
            continue
        if cid in seen:
            errs.append("повтор id кейса %s" % cid)
        seen.add(cid)
        if not isinstance(c.get("expected"), dict) or not c["expected"]:
            errs.append("%s: нет expected" % cid)
    if "демо" not in label.lower() and "demo" not in label.lower():
        warns.append("в каноне нет пометки демо-данных (поле label) — числа вымышлены, пометьте их")
    return errs, warns


MISSING = object()


def lookup(ref, by_id, vals):
    """data-canon="<ключ>": сначала values канона, затем <id кейса>.<поле>; нет — MISSING."""
    if ref in vals:
        return vals[ref]
    cid, _, key = ref.partition(".")
    c = by_id.get(cid)
    if c and key in (c.get("expected") or {}):
        return c["expected"][key]
    return MISSING


def compare(shown_text, expected):
    """→ None (совпало) или строка причины."""
    text = html.unescape(TAG_RE.sub(" ", shown_text)).strip()
    if expected is None:
        return None if text in ("", "—", "-", "нет") else "ожидалось пусто/«—», показано «%s»" % text
    if isinstance(expected, (int, float)) and not isinstance(expected, bool):
        nums = NUM_RE.findall(text)
        if not nums:
            return "ожидалось %s, показано «%s» (числа нет)" % (expected, text)
        raw = nums[0]
        v = parse_number(raw)
        s = re.sub(r"[\s  ]", "", raw)
        dec = len(re.split(r"[.,]", s)[-1]) if re.search(r"[.,]\d+$", s) else 0
        tol = max(0.5 * 10 ** (-dec), abs(expected) * 1e-9)
        if v is None or abs(v - expected) > tol + 1e-12:
            return "ожидалось %s, показано «%s»" % (expected, raw)
        return None
    norm = lambda s: re.sub(r"\s+", " ", str(s)).strip().lower()
    return None if norm(text) == norm(expected) else "ожидалось «%s», показано «%s»" % (expected, text)


def check_html(files, cases, vals=None):
    by_id = {c["id"]: c for c in cases if isinstance(c, dict) and c.get("id")}
    vals = vals or {}
    errs, checked, items = [], 0, {}
    for f in files:
        src = f.read_text(encoding="utf-8", errors="replace")
        for m in ATTR_RE.finditer(src):
            ref = m.group("ref")
            checked += 1
            exp = lookup(ref, by_id, vals)
            if exp is MISSING:
                errs.append("%s: data-canon=\"%s\" — нет в каноне" % (f.name, ref))
                continue
            why = compare(m.group("body"), exp)
            if why:
                errs.append("%s: %s — %s" % (f.name, ref, why))
        for ref in ITEM_RE.findall(src):
            items[(f.name, ref)] = items.get((f.name, ref), 0) + 1
    for (fname, ref), n in sorted(items.items()):
        exp = lookup(ref, by_id, vals)
        checked += 1
        if not isinstance(exp, (int, float)) or isinstance(exp, bool):
            errs.append("%s: data-canon-item=\"%s\" — в каноне нет числа" % (fname, ref))
        elif n != exp:
            errs.append("%s: элементов data-canon-item=\"%s\" %d, в каноне %s (график ↔ подпись)" % (fname, ref, n, exp))
    return errs, checked


def main(argv=None):
    ap = argparse.ArgumentParser(description="Числа макетов = числа канона = числа ядра (рабочий прототип).")
    ap.add_argument("prototype", help="папка прототипа (<OUT>/prototype) или папка прогона <OUT> (макеты без прототипа)")
    ap.add_argument("--canon", help="канон демо-данных (по умолчанию data/demo-canon.json прогона или fixtures/canon.json)")
    ap.add_argument("--mockups", action="append", default=[], help="папка макетов (по умолчанию <OUT>/mockups/concepts)")
    ap.add_argument("--html", action="append", default=[], help="отдельный HTML-файл для проверки")
    ap.add_argument("--core", action="store_true", help="ещё и node js/core.test.js <канон>")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    root = Path(a.prototype).resolve()
    if not root.is_dir():
        print("нет папки %s" % root, file=sys.stderr)
        return 2
    if (root / "js" / "core.js").exists() or (root / "fixtures").is_dir():
        proto, out = root, root.parent                       # папка прототипа
    elif (root / "prototype").is_dir():
        proto, out = root / "prototype", root                # папка прогона с прототипом
    else:
        proto, out = None, root                              # папка прогона без прототипа (макеты C8)
    fixture = proto / "fixtures" / "canon.json" if proto else None
    canon = Path(a.canon) if a.canon else next((p for p in (out / "data" / "demo-canon.json", fixture) if p and p.exists()), None)
    if not canon or not canon.exists():
        print("нет канона демо-данных (data/demo-canon.json или prototype/fixtures/canon.json)", file=sys.stderr)
        return 2
    cases, vals, label, cases_file = load_canon(canon, None if a.canon else fixture)
    errs, warns = check_canon_schema(cases, label, vals)
    dirs = [Path(d) for d in a.mockups] or ([out / "mockups" / "concepts"] if (out / "mockups" / "concepts").is_dir() and not a.html else [])
    files = sorted(f for d in dirs for f in d.glob("*.html") if not f.name.startswith("_")) + [Path(h) for h in a.html]
    herrs, checked = check_html(files, cases, vals)
    errs += herrs
    if files and not checked:
        warns.append("в %d HTML нет ни одного data-canon — макеты не связаны с каноном" % len(files))
    core_rc = None
    if a.core:
        if not proto:
            errs.append("--core: нет папки прототипа (prototype/js/core.test.js)")
        elif not cases_file:
            errs.append("--core: в каноне нет кейсов ядра (cases) — их пишет агент prototype-core")
        else:
            r = subprocess.run(["node", str(proto / "js" / "core.test.js"), str(cases_file)], capture_output=True, text=True)
            core_rc = r.returncode
            if r.returncode != 0:
                errs.append("ядро не воспроизводит канон: " + (r.stdout.strip().splitlines() or ["node: код %d" % r.returncode])[0])
    res = {"canon": str(canon.name), "cases": len(cases), "values": len(vals), "cases_from": cases_file.name if cases_file else None,
           "html": len(files), "checked": checked, "core_rc": core_rc, "errors": errs, "warnings": warns}
    if a.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        extra = (", значений %d" % len(vals) if vals else "") + (" (кейсы — %s)" % cases_file.name if cases_file and cases_file.name != canon.name else "")
        print("канон %s: кейсов %d%s; HTML %d, сверено значений %d%s" % (canon.name, len(cases), extra, len(files), checked,
                                                                          "" if core_rc is None else "; ядро: %s" % ("ок" if core_rc == 0 else "ошибка")))
        for w in warns:
            print("  ! " + w)
        for e in errs:
            print("  ✗ " + e)
        print("расхождений нет" if not errs else "расхождений: %d" % len(errs))
    return 1 if errs else 0


if __name__ == "__main__":
    raise SystemExit(main())
