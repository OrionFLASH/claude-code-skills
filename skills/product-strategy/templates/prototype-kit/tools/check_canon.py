#!/usr/bin/env python3
"""Сквозная проверка «числа макетов = числа канона = числа ядра» для рабочего прототипа.

  python3 tools/check_canon.py <папка prototype> [--canon PATH] [--mockups DIR ...] [--html FILE ...] [--core] [--json]

Канон демо-данных: --canon, иначе <OUT>/data/demo-canon.json (папка прототипа — <OUT>/prototype), иначе
<prototype>/fixtures/canon.json. Формат: {"label": "демо-данные", "cases": [{"id": "C01", "fn": "payback",
"inputs": {…}, "expected": {"поле": число|строка|null}, "mockups": ["M01-…"]}]} (или просто список кейсов).

Что проверяется:
  1. канон: кейсы с уникальными id и непустым expected; пометка демо-данных (label) — иначе предупреждение;
  2. макеты (--mockups, по умолчанию <OUT>/mockups/concepts; --html — отдельные файлы): каждый элемент
     с атрибутом data-canon="<id>.<поле>" показывает значение канона (числа — с допуском по округлению показа:
     «15,07 %» ≈ 15.0712; строки — точное совпадение без учёта регистра и пробелов); неизвестный кейс или поле —
     ошибка; число элементов с data-canon-item="<id>.<поле>" (значки, точки, строки на графике) равно значению
     канона — так ловится «4 значка на графике, а в подписи 3»;
  3. --core: node js/core.test.js <канон> — ядро воспроизводит канон (код выхода node).
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


def load_canon(path):
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    cases = d if isinstance(d, list) else d.get("cases") or []
    label = "" if isinstance(d, list) else str(d.get("label") or "")
    return cases, label


def check_canon_schema(cases, label):
    errs, warns, seen = [], [], set()
    if not cases:
        errs.append("канон пуст: нет кейсов")
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


def check_html(files, cases):
    by_id = {c["id"]: c for c in cases if isinstance(c, dict) and c.get("id")}
    errs, checked, items = [], 0, {}
    for f in files:
        src = f.read_text(encoding="utf-8", errors="replace")
        for m in ATTR_RE.finditer(src):
            ref = m.group("ref")
            cid, _, key = ref.partition(".")
            checked += 1
            c = by_id.get(cid)
            if not c or key not in (c.get("expected") or {}):
                errs.append("%s: data-canon=\"%s\" — нет в каноне" % (f.name, ref))
                continue
            why = compare(m.group("body"), c["expected"][key])
            if why:
                errs.append("%s: %s — %s" % (f.name, ref, why))
        for ref in ITEM_RE.findall(src):
            items[(f.name, ref)] = items.get((f.name, ref), 0) + 1
    for (fname, ref), n in sorted(items.items()):
        cid, _, key = ref.partition(".")
        exp = (by_id.get(cid) or {}).get("expected", {}).get(key)
        checked += 1
        if not isinstance(exp, (int, float)) or isinstance(exp, bool):
            errs.append("%s: data-canon-item=\"%s\" — в каноне нет числа" % (fname, ref))
        elif n != exp:
            errs.append("%s: элементов data-canon-item=\"%s\" %d, в каноне %s (график ↔ подпись)" % (fname, ref, n, exp))
    return errs, checked


def main(argv=None):
    ap = argparse.ArgumentParser(description="Числа макетов = числа канона = числа ядра (рабочий прототип).")
    ap.add_argument("prototype", help="папка прототипа (<OUT>/prototype)")
    ap.add_argument("--canon", help="канон демо-данных (по умолчанию data/demo-canon.json прогона или fixtures/canon.json)")
    ap.add_argument("--mockups", action="append", default=[], help="папка макетов (по умолчанию <OUT>/mockups/concepts)")
    ap.add_argument("--html", action="append", default=[], help="отдельный HTML-файл для проверки")
    ap.add_argument("--core", action="store_true", help="ещё и node js/core.test.js <канон>")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    proto = Path(a.prototype).resolve()
    if not proto.is_dir():
        print("нет папки %s" % proto, file=sys.stderr)
        return 2
    out = proto.parent
    canon = Path(a.canon) if a.canon else next((p for p in (out / "data" / "demo-canon.json", proto / "fixtures" / "canon.json") if p.exists()), None)
    if not canon or not canon.exists():
        print("нет канона демо-данных (data/demo-canon.json или prototype/fixtures/canon.json)", file=sys.stderr)
        return 2
    cases, label = load_canon(canon)
    errs, warns = check_canon_schema(cases, label)
    dirs = [Path(d) for d in a.mockups] or ([out / "mockups" / "concepts"] if (out / "mockups" / "concepts").is_dir() else [])
    files = sorted(f for d in dirs for f in d.glob("*.html")) + [Path(h) for h in a.html]
    herrs, checked = check_html(files, cases)
    errs += herrs
    if files and not checked:
        warns.append("в %d HTML нет ни одного data-canon — макеты не связаны с каноном" % len(files))
    core_rc = None
    if a.core:
        r = subprocess.run(["node", str(proto / "js" / "core.test.js"), str(canon)], capture_output=True, text=True)
        core_rc = r.returncode
        if r.returncode != 0:
            errs.append("ядро не воспроизводит канон: " + (r.stdout.strip().splitlines() or ["node: код %d" % r.returncode])[0])
    res = {"canon": str(canon.name), "cases": len(cases), "html": len(files), "checked": checked, "core_rc": core_rc,
           "errors": errs, "warnings": warns}
    if a.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        print("канон %s: кейсов %d; HTML %d, сверено значений %d%s" % (canon.name, len(cases), len(files), checked,
                                                                        "" if core_rc is None else "; ядро: %s" % ("ок" if core_rc == 0 else "ошибка")))
        for w in warns:
            print("  ! " + w)
        for e in errs:
            print("  ✗ " + e)
        print("расхождений нет" if not errs else "расхождений: %d" % len(errs))
    return 1 if errs else 0


if __name__ == "__main__":
    raise SystemExit(main())
