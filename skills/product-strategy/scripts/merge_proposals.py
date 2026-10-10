#!/usr/bin/env python3
"""Склейка черновиков реестра data/proposals-draft-*.json → data/proposals.json.

  merge_proposals.py <OUT> [--threshold 0.6] [--title-threshold 0.75] [--dry-run]

Порядок:
1. Читает все data/proposals-draft-<group>.json (список предложений по контракту, id вида <group>-NN).
2. Ручная карта дублей build/merge-map.json (необязательно):
     {"merge": [{"drop": "G2-18", "into": "G4-03", "reason": "то же, G4-03 шире"}],
      "distinct": [["G1-03", "G5-07"]]}
   либо упрощённо {"G2-18": "G4-03", ...}. merge — принудительное слияние, distinct — запрет автослияния пары.
3. Автодедупликация: коэффициент Жаккара по токенам названия + описания (≥ --threshold) или только названия
   (≥ --title-threshold). Токены: нижний регистр, буквы/цифры длиной > 2, без стоп-слов, усечены до 6 знаков
   (грубая основа слова, чтобы «шаблоны»/«шаблонов» совпадали).
4. Из пары остаётся предложение с более сильным классом доказательства (A > B > C > D), затем с большим числом
   доказательств, затем более раннее (по файлу и id). Доказательства и теги дубля добавляются к оставшемуся.
5. Сортировка по категории (порядок контракта), файлу, исходному id; перенумерация P001…; merged_from — исходный id
   и id всех влитых черновиков; зависимости переводятся на новые id.
Отчёт — stdout и build/merge-report.json (слияния, пары-кандидаты для ручной проверки, карта id).
Только стандартная библиотека.
"""
import argparse
import json
import re
import sys
from pathlib import Path

CATEGORY_ORDER = ["product", "acquisition", "conversion", "retention", "monetization", "analytics", "partnerships",
                  "localization", "new_lines", "platform"]
CLASS_RANK = {"A": 0, "B": 1, "C": 2, "D": 3}
STOP = set(("и в во на для по с со из к ко о об от у за не что как это или при без над под до после чтобы его её их "
            "the of to a an for and in on with by from at is are be this that into via").split())
STEM = 6
REVIEW_MARGIN = 0.15


def tokens(text):
    """Множество усечённых токенов текста."""
    words = re.findall(r"[a-zа-яё0-9]+", str(text or "").lower().replace("ё", "е"))
    return {w[:STEM] for w in words if len(w) > 2 and w not in STOP}


def jaccard(a, b):
    return len(a & b) / len(a | b) if (a or b) else 0.0


def load_drafts(data_dir):
    """Список (файл, группа, предложение) из всех черновиков."""
    items = []
    files = sorted(data_dir.glob("proposals-draft-*.json"))
    for f in files:
        raw = json.loads(f.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            raw = raw.get("proposals", [])
        group = f.stem[len("proposals-draft-"):]
        for k, p in enumerate(raw):
            if not isinstance(p, dict):
                print("пропущен не-объект в %s[%d]" % (f.name, k), file=sys.stderr)
                continue
            if not p.get("id"):
                p["id"] = "%s-%02d" % (group, k + 1)
            items.append({"file": f.name, "group": group, "p": p})
    return files, items


def load_map(path):
    """Ручная карта: (force: {drop_id: (into_id, reason)}, distinct: set(frozenset))."""
    force, distinct = {}, set()
    if not path.exists():
        return force, distinct
    m = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(m, dict) and ("merge" in m or "distinct" in m):
        for e in m.get("merge", []):
            force[e["drop"]] = (e["into"], e.get("reason", "ручная карта"))
        for pair in m.get("distinct", []):
            distinct.add(frozenset(pair))
    elif isinstance(m, dict):
        for k, v in m.items():
            force[k] = (v, "ручная карта") if isinstance(v, str) else (v.get("into"), v.get("reason", "ручная карта"))
    return force, distinct


def stronger(a, b):
    """True, если a стоит оставить вместо b."""
    ka = (CLASS_RANK.get(a["p"].get("evidence_class"), 9), -len(a["p"].get("evidence") or []), a["order"])
    kb = (CLASS_RANK.get(b["p"].get("evidence_class"), 9), -len(b["p"].get("evidence") or []), b["order"])
    return ka < kb


def absorb(keeper, dup):
    """Переносит в keeper id, доказательства и теги дубля."""
    kp, dp = keeper["p"], dup["p"]
    keeper["absorbed"] += [dp["id"]] + dup["absorbed"]
    seen = {(e.get("url"), e.get("file"), e.get("title")) for e in kp.get("evidence") or [] if isinstance(e, dict)}
    for e in dp.get("evidence") or []:
        key = (e.get("url"), e.get("file"), e.get("title")) if isinstance(e, dict) else None
        if key and key not in seen:
            kp.setdefault("evidence", []).append(e)
            seen.add(key)
    for t in dp.get("tags") or []:
        if t not in (kp.get("tags") or []):
            kp.setdefault("tags", []).append(t)
    for d in dp.get("dependencies") or []:
        if d not in (kp.get("dependencies") or []):
            kp.setdefault("dependencies", []).append(d)


def merge(items, force, distinct, thr, title_thr):
    """Возвращает (kept, dropped, candidates, alias: старый id → id оставшегося черновика)."""
    for k, it in enumerate(items):
        it["order"] = k
        it["absorbed"] = list(it["p"].get("merged_from") or [])
        it["tok"] = tokens(it["p"].get("title")) | tokens(str(it["p"].get("description", ""))[:400])
        it["ttok"] = tokens(it["p"].get("title"))
    by_id = {}
    for it in items:
        by_id.setdefault(it["p"]["id"], it)
    dropped, candidates, alias = [], [], {}
    # 1) ручные слияния
    alive = []
    for it in items:
        pid = it["p"]["id"]
        if pid in force and force[pid][0] in by_id and force[pid][0] != pid:
            into, why = force[pid]
            dropped.append({"id": pid, "title": it["p"].get("title"), "into": into, "similarity": None, "reason": "manual: " + why})
            it["into"] = into
        else:
            alive.append(it)
    # 2) автоматическое слияние
    kept = []
    for it in alive:
        best = None
        for k in kept:
            if frozenset((it["p"]["id"], k["p"]["id"])) in distinct:
                continue
            sim, tsim = jaccard(it["tok"], k["tok"]), jaccard(it["ttok"], k["ttok"])
            score = max(sim, tsim)
            if sim >= thr or tsim >= title_thr:
                if best is None or score > best[1]:
                    best = (k, score)
            elif sim >= thr - REVIEW_MARGIN or tsim >= title_thr - REVIEW_MARGIN:
                candidates.append({"a": k["p"]["id"], "b": it["p"]["id"], "similarity": round(score, 3),
                                   "a_title": k["p"].get("title"), "b_title": it["p"].get("title")})
        if best is None:
            kept.append(it)
            continue
        k, score = best
        if stronger(it, k):
            absorb(it, k)
            kept[kept.index(k)] = it
            alias[k["p"]["id"]] = it["p"]["id"]
            dropped.append({"id": k["p"]["id"], "title": k["p"].get("title"), "into": it["p"]["id"],
                            "similarity": round(score, 3), "reason": "jaccard"})
        else:
            absorb(k, it)
            alias[it["p"]["id"]] = k["p"]["id"]
            dropped.append({"id": it["p"]["id"], "title": it["p"].get("title"), "into": k["p"]["id"],
                            "similarity": round(score, 3), "reason": "jaccard"})
    # 3) влить ручные дубли в итоговых держателей (цепочки drop → into → …)
    kept_ids = {k["p"]["id"]: k for k in kept}

    def resolve(pid, depth=0):
        if pid in kept_ids or depth > 50:
            return pid
        nxt = alias.get(pid) or (by_id[pid].get("into") if pid in by_id else None)
        return resolve(nxt, depth + 1) if nxt else pid

    for it in items:
        if it.get("into"):
            target = resolve(it["into"])
            alias[it["p"]["id"]] = target
            if target in kept_ids:
                absorb(kept_ids[target], it)
    for d in dropped:
        d["into"] = resolve(d["into"])
    for old in list(alias):
        alias[old] = resolve(alias[old])
    return kept, dropped, candidates, alias


def finalize(kept):
    """Сортировка, перенумерация, merged_from. Возвращает (proposals, id_map исходный → P###)."""
    def key(it):
        cat = it["p"].get("category")
        return (CATEGORY_ORDER.index(cat) if cat in CATEGORY_ORDER else len(CATEGORY_ORDER), it["file"], str(it["p"]["id"]))

    kept = sorted(kept, key=key)
    id_map = {}
    for n, it in enumerate(kept, 1):
        id_map[it["p"]["id"]] = "P%03d" % n
    out = []
    for it in kept:
        p = dict(it["p"])
        orig = p["id"]
        p["id"] = id_map[orig]
        p.setdefault("source_group", it["group"])
        mf = [orig] + [x for x in it["absorbed"] if x != orig]
        p["merged_from"] = list(dict.fromkeys(mf)) if it["absorbed"] else []
        out.append(p)
    return out, id_map


def remap_dependencies(props, id_map, alias):
    """Зависимости черновиков → новые id; ссылки на влитые дубли — на держателя. Возвращает список предупреждений."""
    warn = []
    for p in props:
        new = []
        for d in p.get("dependencies") or []:
            target = id_map.get(alias.get(d, d)) or (d if re.fullmatch(r"P\d{3}", str(d)) else None)
            if target is None:
                warn.append("%s: зависимость %r не найдена среди черновиков — удалена" % (p["id"], d))
                continue
            if target != p["id"] and target not in new:
                new.append(target)
        p["dependencies"] = new
    return warn


def main(argv=None):
    ap = argparse.ArgumentParser(description="Склейка черновиков реестра с дедупликацией и перенумерацией.")
    ap.add_argument("out", help="папка прогона <OUT>")
    ap.add_argument("--threshold", type=float, default=0.6, help="порог Жаккара по названию+описанию (0.6)")
    ap.add_argument("--title-threshold", type=float, default=0.75, help="порог Жаккара только по названию (0.75)")
    ap.add_argument("--dry-run", action="store_true", help="только отчёт, без записи proposals.json")
    a = ap.parse_args(argv)
    out_dir = Path(a.out).resolve()
    files, items = load_drafts(out_dir / "data")
    if not files:
        print("нет черновиков data/proposals-draft-*.json в %s" % out_dir, file=sys.stderr)
        return 1
    force, distinct = load_map(out_dir / "build" / "merge-map.json")
    kept, dropped, candidates, alias = merge(items, force, distinct, a.threshold, a.title_threshold)
    props, id_map = finalize(kept)
    warns = remap_dependencies(props, id_map, alias)
    full_map = dict(id_map)
    for old, tgt in alias.items():
        if tgt in id_map:
            full_map[old] = id_map[tgt]
    report = {"files": [f.name for f in files], "loaded": len(items), "kept": len(props), "dropped": dropped,
              "candidates": sorted(candidates, key=lambda c: -c["similarity"]), "id_map": full_map,
              "threshold": a.threshold, "title_threshold": a.title_threshold, "warnings": warns, "dry_run": a.dry_run}
    print("Загружено %d из %d файлов; оставлено %d, слито %d" % (len(items), len(files), len(props), len(dropped)))
    for d in dropped:
        sim = "" if d["similarity"] is None else " (сходство %.2f)" % d["similarity"]
        print("  слито %s «%s» → %s [%s]%s" % (d["id"], d["title"], full_map.get(d["into"], d["into"]), d["reason"], sim))
    if candidates:
        print("Пары на ручную проверку (близко к порогу): %d — см. build/merge-report.json" % len(candidates))
    for w in warns:
        print("  ! " + w)
    if a.dry_run:
        return 0
    (out_dir / "data" / "proposals.json").write_text(json.dumps(props, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "build").mkdir(parents=True, exist_ok=True)
    (out_dir / "build" / "merge-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Записано: data/proposals.json, build/merge-report.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
