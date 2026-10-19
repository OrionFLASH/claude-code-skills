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
  - ничего не удаляет: предложения без макетов не меняются. Повторный запуск не меняет файл (идемпотентно);
  - не связывает служебные макеты и карточки: запись индекса или карточка design-refs с `kind: component`
    (общий дизайн-язык, набор компонентов — например, карточка 00 / `M00-design-language`) или `links: false`,
    а также карточки на служебные `_*.html` (`_base`, `_kit-demo`, `_app-demo`) — их `proposals` перечисляют
    предложения, где элемент используется, а не макеты этих предложений (иначе `mockup` у десятков предложений
    указывал бы на макет вне индекса и assemble_strategy падал с `bad_mockup`). Пропуски — в заметках.

--dry-run — показать изменения, файл не писать; --strict — код 1, если есть предупреждения.

Дополнительные режимы (1.5, дизайн-этап):
  link_mockups.py <OUT> --index-only [--json]
      data/mockups-index.json по mockups/concepts/*.html БЕЗ браузера (те же правила, что автообнаружение
      shoot_mockups.mjs: ключ — имя файла, метаданные — атрибуты <html>/<meta name="ps:…">, записи discovered: true
      обновляются, ручные не трогаются, дубли ключей — первая запись). Индекс макетов «заранее» — для specs/брифов до
      снимков. data/proposals.json не нужен и не меняется.
  link_mockups.py <OUT> --collect-gaps [--from ФАЙЛ …] [--dry-run] [--json]
      Строки фиксированного формата из design-refs/*.md и комментариев <!-- … --> макетов mockups/concepts/M*.html
      (и файлов --from, например отчётов агентов):
        НУЖНО-ПРЕДЛОЖЕНИЕ: <заголовок> | <категория> | <связанные P-id через запятую>
        РАСХОЖДЕНИЕ: <P-id> | <ключ макета Mxx> | <суть>        (в комментарии макета ключ можно опустить)
      (англ. NEED-PROPOSAL: / MISMATCH:). Первые → черновики data/proposals-draft-G8.json (id G8-NN, source_group G8,
      полная схема контракта, evidence_class D, needs_details: true — оценки и шаги дописать до слияния; повторный
      запуск не дублирует по заголовку); вторые → записи data/fact-check.json (kind: mockup_vs_registry, status: open;
      без дублей по P-id + макет + суть). Итог — build/collect-gaps.json (числа для REPORT). Дальше — штатно
      merge_proposals.py <OUT> --append G8.
  link_mockups.py <OUT> --remap-drafts [--dry-run] [--json]
      После merge_proposals.py --append G8: id черновиков (G8-01 …) в data-proposals / ps:proposals / data-hs-p макетов
      mockups/concepts/*.html заменяются на P-id по build/id-map.json (накопительная карта merge_proposals).

Код выхода: 0 — готово (предупреждения допустимы); 1 — есть предупреждения при --strict (--collect-gaps: строки с
ошибками формата); 2 — нет data/proposals.json (или нужного входа режима).
Только стандартная библиотека.
"""
import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mockup_kit import html_meta, concept_files, dump_json  # noqa: E402

CATEGORIES = {"product", "acquisition", "conversion", "retention", "monetization", "analytics", "partnerships", "localization",
              "new_lines", "platform",
              # личный режим (WP-C): core, data-sources, …
              "core", "data-sources", "reliability", "privacy-security", "ux", "ai-quality", "maintenance", "personal-analytics"}
NEED_RE = re.compile(r"(?:НУЖНО-ПРЕДЛОЖЕНИЕ|NEED-PROPOSAL)\s*:\s*(.+)", re.I)
MIS_RE = re.compile(r"(?:РАСХОЖДЕНИЕ|MISMATCH)\s*:\s*(.+)", re.I)
PID_RE = re.compile(r"^(P\d{3,}|G\d+-\d{2,})$")
MKEY_RE = re.compile(r"^M\d{2,}[\w-]*$")


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


def no_links(rec, html=""):
    """Служебная запись: kind=component, links=false или файл _*.html — в связывание не идёт."""
    base = str(html or rec.get("html") or rec.get("file") or "").replace("\\", "/").rsplit("/", 1)[-1]
    return str(rec.get("kind") or "").lower() == "component" or rec.get("links") is False or base.startswith("_")


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


# ---------------------------------------------------------------- --index-only
def index_only(out, as_json):
    idx_path = out / "data" / "mockups-index.json"
    items = load_json(idx_path, [])
    if not isinstance(items, list):
        print("ошибка: data/mockups-index.json не список", file=sys.stderr)
        return 2
    seen, res, dups = set(), [], []
    for it in items:
        if isinstance(it, dict) and it.get("key"):
            if it["key"] in seen:
                dups.append(it["key"])
                continue
            seen.add(it["key"])
        res.append(it)
    added, updated = [], []
    by_html = {i.get("html"): i for i in res if isinstance(i, dict) and i.get("html")}
    for f in concept_files(out):
        key, rel = f.stem, "mockups/concepts/" + f.name
        m = html_meta(f)
        cur = next((i for i in res if isinstance(i, dict) and i.get("key") == key), None) or by_html.get(rel)
        want = {"viewport": m.get("viewport") or "1440x900", "title": m.get("title") or key, "proposals": m.get("proposals") or [],
                "kind": m.get("kind") or "concept"}
        if cur:
            if cur.get("discovered") is not True:
                continue
            diff = [k for k in want if cur.get(k) != want[k]]
            if ("links" in m) != (cur.get("links") is False):
                diff.append("links")
            if diff:
                cur.update(want)
                if m.get("links") is False:
                    cur["links"] = False
                else:
                    cur.pop("links", None)
                updated.append("%s (%s)" % (key, ", ".join(diff)))
            continue
        rec = {"key": key, "html": rel, "png": rel.rsplit(".", 1)[0] + ".png", "title": want["title"], "proposals": want["proposals"],
               "viewport": want["viewport"], "kind": want["kind"], "discovered": True}
        if m.get("links") is False:
            rec["links"] = False
        res.append(rec)
        added.append(key)
    if added or updated or dups:
        dump_json(idx_path, res)
    rep = {"index": "data/mockups-index.json", "added": added, "updated": updated, "duplicates": dups, "total": len(res)}
    if as_json:
        print(json.dumps(rep, ensure_ascii=False, indent=2))
    else:
        print("индекс макетов без браузера: %d записей; добавлено %d, обновлено %d%s" % (len(res), len(added), len(updated),
              "; дубли ключей отброшены: " + ", ".join(dups) if dups else ""))
    return 0


# ---------------------------------------------------------------- --collect-gaps
def _cells(s):
    s = re.sub(r"\s*-->\s*$", "", s.strip())
    s = re.sub(r"[*_`]+$", "", re.sub(r"^[*_`]+", "", s)).strip()
    return [c.strip().strip("*_`").strip() for c in s.split("|")]


def _ids(s):
    return [x for x in re.split(r"[,\s;]+", s or "") if PID_RE.match(x)]


def gap_lines(out, extra):
    """[(источник 'файл:строка', ключ макета или None, тип, ячейки)]."""
    res = []
    srcs = sorted((out / "design-refs").glob("*.md")) if (out / "design-refs").is_dir() else []
    srcs = [p for p in srcs if p.name.lower() not in ("readme.md", "readme.generated.md")]
    mk = sorted((out / "mockups" / "concepts").glob("M*.htm*")) if (out / "mockups" / "concepts").is_dir() else []
    files = [(p, None) for p in srcs] + [(p, p.stem) for p in mk] + [(Path(x), None) for x in extra]
    for p, key in files:
        try:
            text = p.read_text(encoding="utf-8")
        except OSError as e:
            print("предупреждение: не прочитан %s: %s" % (p, e), file=sys.stderr)
            continue
        try:
            rel = p.resolve().relative_to(out).as_posix()
        except ValueError:
            rel = p.name
        in_comment = False
        for n, line in enumerate(text.splitlines(), 1):
            if key is not None:                     # в макете — только внутри комментариев <!-- … -->
                visible = in_comment or "<!--" in line
                if "<!--" in line:
                    in_comment = True
                if "-->" in line:
                    in_comment = False
                if not visible:
                    continue
            for kind, rx in (("need", NEED_RE), ("mismatch", MIS_RE)):
                m = rx.search(line)
                if m:
                    res.append(("%s:%d" % (rel, n), key, kind, _cells(m.group(1))))
    return res


def collect_gaps(out, extra, dry, as_json):
    data = out / "data"
    props = load_json(data / "proposals.json", [])
    ids = {p.get("id") for p in props if isinstance(p, dict)} if isinstance(props, list) else set()
    draft_path, fc_path = data / "proposals-draft-G8.json", data / "fact-check.json"
    drafts = load_json(draft_path, [])
    drafts = drafts if isinstance(drafts, list) else []
    fc = load_json(fc_path, [])
    holder = fc if isinstance(fc, list) else (fc.setdefault("items", []) if isinstance(fc, dict) else None)
    if holder is None:
        fc = holder = []
    norm = lambda t: re.sub(r"\W+", " ", str(t).lower()).strip()
    have_titles = {norm(d.get("title")) for d in drafts if isinstance(d, dict)}
    have_titles |= {norm(p.get("title")) for p in props if isinstance(p, dict)} if isinstance(props, list) else set()
    have_fc = {(x.get("proposal"), x.get("mockup"), norm(x.get("summary") or "")) for x in holder if isinstance(x, dict) and x.get("kind") == "mockup_vs_registry"}
    nums = [int(m.group(1)) for d in drafts if isinstance(d, dict) for m in [re.match(r"G8-(\d+)$", str(d.get("id") or ""))] if m]
    nxt = max(nums or [0]) + 1
    added_d, added_f, skipped, errors, warnings = [], [], [], [], []
    today = date.today().isoformat()
    for src, key, kind, cells in gap_lines(out, extra):
        if kind == "need":
            title = cells[0] if cells else ""
            if not title:
                errors.append("%s: НУЖНО-ПРЕДЛОЖЕНИЕ без заголовка" % src)
                continue
            cat = (cells[1] if len(cells) > 1 else "").lower() or "product"
            if cat not in CATEGORIES:
                warnings.append("%s: категория %r не из контракта — записано product" % (src, cat))
                cat = "product"
            related = _ids(cells[2] if len(cells) > 2 else "")
            unknown = [x for x in related if x.startswith("P") and ids and x not in ids]
            if unknown:
                warnings.append("%s: P-id %s нет в реестре" % (src, ", ".join(unknown)))
            if norm(title) in have_titles:
                skipped.append("%s: «%s» уже есть" % (src, title))
                continue
            did = "G8-%02d" % nxt
            nxt += 1
            have_titles.add(norm(title))
            mk = key or next((c for c in cells[3:] if MKEY_RE.match(c)), None)
            d = {"id": did, "title": title[:90], "category": cat, "segment": "[ДОПУЩЕНИЕ] уточнить",
                 "description": "Нужно по макету%s: %s" % (" " + mk if mk else "", title),
                 "rationale": "Экран макета требует функции, которой нет в реестре (%s)." % src,
                 "evidence": [{"kind": "docs", "url": None, "file": src, "title": "Пробел макета ↔ реестра",
                               "note": "строка НУЖНО-ПРЕДЛОЖЕНИЕ в %s" % src, "checked": today}],
                 "evidence_class": "D", "current_feature": "нет", "effect_kpi": [], "steps": [], "dependencies": [x for x in related if x in ids],
                 "effort_days": None, "cost_money": None, "risks": None, "time_to_first_result_days": None, "cheap_test": "",
                 "scores": {}, "kano": None, "horizon": None, "horizon_years": 0, "tags": ["G8", "from-mockups"],
                 "mockup": ("concepts/%s.html" % mk) if mk and (out / "mockups" / "concepts" / ("%s.html" % mk)).exists() else None,
                 "source_group": "G8", "needs_details": True, "related": related, "origin": src}
            drafts.append(d)
            added_d.append(did)
        else:
            if len(cells) >= 3:
                pid, mk, summary = cells[0], cells[1], " | ".join(cells[2:])
            elif len(cells) == 2 and key:
                pid, mk, summary = cells[0], key, cells[1]
            else:
                errors.append("%s: РАСХОЖДЕНИЕ — нужно «P-id | Mxx | суть»" % src)
                continue
            if not PID_RE.match(pid):
                errors.append("%s: РАСХОЖДЕНИЕ — %r не P-id" % (src, pid))
                continue
            if pid.startswith("P") and ids and pid not in ids:
                warnings.append("%s: %s нет в реестре" % (src, pid))
            sig = (pid, mk, norm(summary))
            if sig in have_fc:
                skipped.append("%s: расхождение %s ↔ %s уже записано" % (src, pid, mk))
                continue
            have_fc.add(sig)
            holder.append({"kind": "mockup_vs_registry", "proposal": pid, "mockup": mk, "summary": summary,
                           "fact": "%s ↔ %s: %s" % (pid, mk, summary), "claim": "%s ↔ %s: %s" % (pid, mk, summary),
                           "phase1_value": "реестр %s" % pid, "agent_value": "макет %s: %s" % (mk, summary),
                           "was": "реестр %s" % pid, "now": "макет %s: %s" % (mk, summary),
                           "source": src, "resolved_value": None, "status": "open", "decision": None,
                           "note": "link_mockups --collect-gaps %s" % today})
            added_f.append("%s ↔ %s" % (pid, mk))
    rep = {"date": today, "drafts_added": added_d, "fact_check_added": added_f, "skipped": skipped, "errors": errors, "warnings": warnings,
           "drafts_total": len(drafts), "mismatches_open": sum(1 for x in holder if isinstance(x, dict) and x.get("kind") == "mockup_vs_registry" and x.get("status") == "open"),
           "next": "merge_proposals.py <OUT> --append G8 (после дописывания оценок черновиков)" if drafts else None, "dry_run": dry}
    if not dry:
        if added_d:
            dump_json(draft_path, drafts)
        if added_f:
            dump_json(fc_path, fc)
        dump_json(out / "build" / "collect-gaps.json", rep)
    if as_json:
        print(json.dumps(rep, ensure_ascii=False, indent=2))
    else:
        print("пробелы макетов: черновиков G8 +%d (всего %d) → data/proposals-draft-G8.json; расхождений +%d (открыто %d) → data/fact-check.json%s" % (
            len(added_d), len(drafts), len(added_f), rep["mismatches_open"], " (dry-run, файлы не записаны)" if dry else ""))
        for e in errors:
            print("ошибка формата: " + e)
        for w in warnings:
            print("предупреждение: " + w)
        if added_d:
            print("дальше: дописать оценки черновиков (needs_details) и merge_proposals.py %s --append G8; затем link_mockups.py %s --remap-drafts" % (out.name, out.name))
    return rep


# ---------------------------------------------------------------- --remap-drafts
def remap_drafts(out, dry, as_json):
    idmap = load_json(out / "build" / "id-map.json", None)
    if not isinstance(idmap, dict):
        print("ошибка: нет build/id-map.json (сначала merge_proposals.py --append G8)", file=sys.stderr)
        return 2
    idmap = idmap.get("map", idmap) if isinstance(idmap.get("map"), dict) else idmap
    rx = re.compile(r"(\b(?:data-proposals|data-hs-p|content)\s*=\s*)([\"'])(.*?)\2", re.I | re.S)
    changed = {}
    for f in concept_files(out):
        src = f.read_text(encoding="utf-8")
        cnt = [0]

        def sub(m):
            if m.group(1).lower().startswith("content") and not re.search(r'name\s*=\s*["\']ps:proposals', src[max(0, m.start() - 120): m.start()], re.I):
                return m.group(0)
            def rid(t):
                v = idmap.get(t.group(0))
                if v and v != t.group(0):
                    cnt[0] += 1
                    return str(v)
                return t.group(0)
            return m.group(1) + m.group(2) + re.sub(r"\bG\d+-\d{2,}\b", rid, m.group(3)) + m.group(2)
        new = rx.sub(sub, src)
        if cnt[0]:
            changed[f.name] = cnt[0]
            if not dry:
                f.write_text(new, encoding="utf-8")
    left = sorted({m for f in concept_files(out) for m in re.findall(r"(?:data-proposals|data-hs-p)\s*=\s*[\"'][^\"']*?\b(G\d+-\d{2,})", f.read_text(encoding="utf-8"))})
    rep = {"changed": changed, "unresolved": left, "dry_run": dry}
    if as_json:
        print(json.dumps(rep, ensure_ascii=False, indent=2))
    else:
        print("id черновиков в макетах → P-id: файлов %d, замен %d%s" % (len(changed), sum(changed.values()), " (dry-run)" if dry else ""))
        if left:
            print("предупреждение: в макетах остались id черновиков без P-id в build/id-map.json: " + ", ".join(left))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0], formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    ap.add_argument("out", help="папка прогона <OUT>")
    ap.add_argument("--dry-run", action="store_true", help="не писать файлы")
    ap.add_argument("--strict", action="store_true", help="код выхода 1, если есть предупреждения")
    ap.add_argument("--json", action="store_true", help="печатать отчёт JSON")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--index-only", action="store_true", help="только data/mockups-index.json по HTML макетов, без браузера")
    mode.add_argument("--collect-gaps", action="store_true", help="НУЖНО-ПРЕДЛОЖЕНИЕ / РАСХОЖДЕНИЕ → черновики G8 и fact-check")
    mode.add_argument("--remap-drafts", action="store_true", help="G8-NN в макетах → P-id по build/id-map.json")
    ap.add_argument("--from", dest="extra", action="append", default=[], metavar="ФАЙЛ", help="--collect-gaps: ещё файлы со строками")
    a = ap.parse_args(argv)
    out = Path(a.out).resolve()
    if not out.is_dir():
        print("ошибка: нет папки %s" % out, file=sys.stderr)
        return 2
    if a.index_only:
        return index_only(out, a.json)
    if a.collect_gaps:
        rep = collect_gaps(out, a.extra, a.dry_run, a.json)
        return 1 if a.strict and (rep["errors"] or rep["warnings"]) else 0
    if a.remap_drafts:
        return remap_drafts(out, a.dry_run, a.json)
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
        if no_links(m, html):
            notes.append("макет %s — служебный (kind: %s%s), с предложениями не связывается" % (
                m["key"], m.get("kind") or "—", ", links: false" if m.get("links") is False else ""))
            continue
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
        if no_links(card, html):
            notes.append("карточка %s — служебная (kind: %s, %s), с предложениями не связывается" % (
                f.name, card.get("kind") or "—", "links: false" if card.get("links") is False else html))
            continue
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
