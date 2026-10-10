#!/usr/bin/env python3
"""Склейка черновиков реестра data/proposals-draft-*.json → data/proposals.json с поиском семантических дублей.

  merge_proposals.py <OUT> [--threshold 0.275] [--title-threshold 0.75] [--min N] [--dry-run]
  merge_proposals.py <OUT> --suggest [--top 40]                 только печать пар-кандидатов по убыванию сходства
  merge_proposals.py <OUT> --pairs pairs.json [--auto] [--pairs-winner given|auto]
  merge_proposals.py <OUT> --append G7[,G8]                     дописать новые черновики к готовому реестру

Порядок:
1. Читает все data/proposals-draft-<group>.json (список предложений по контракту, id вида <group>-NN).
2. Ручные слияния:
   - --pairs FILE: {"победитель": ["проигравший", …]} — доказательства переносятся (объединение без дублей по
     url/file), теги и зависимости проигравших добавляются, победителю — тег merged:<id проигравшего>, merged_from
     заполняется всегда. С --pairs-winner auto победителя группы выбирает скрипт (правила п. 4). С --pairs
     автоматическое слияние выключено, если не указан --auto.
   - build/merge-map.json (необязательно): {"merge": [{"drop": "G2-18", "into": "G4-03", "reason": "…"}],
     "distinct": [["G1-03", "G5-07"]]} или упрощённо {"G2-18": "G4-03"}; distinct запрещает автослияние пары.
   Ручное слияние, роняющее минимум категории, выполняется (это решение человека), но попадает в отчёт
   (min_violations) с подсказкой, кого сделать победителем.
3. Автодедупликация (сходство, см. ниже): пары с баллом ≥ --threshold или с Жаккаром основ названий
   ≥ --title-threshold объединяются в группы (одиночная связь; новая связь принимается, только если среднее сходство
   между группами ≥ 0,5·порога и группа не больше --max-group), затем в каждой группе выбирается победитель.
4. Победитель: (а) слияние не должно ронять минимум категории (check_registry.category_requirements: минимумы от
   strategy.proposals_min или --min, categories_na, профиль): проигравший из категории, которая упала бы ниже
   минимума, не сливается (пометка «не слито» в отчёте); (б) из допустимых — тот, при ком сливается больше
   проигравших; (в) предложение из категории, близкой к минимуму (запас ≤ 2) или уже ниже него; (г) лучший класс
   доказательств (A > B > C > D); (д) более полное описание (число доказательств, длина описания и обоснования,
   шаги); (е) раньше по порядку файлов.
5. Сортировка по категории (порядок контракта), файлу, исходному id; перенумерация P001…; merged_from — исходный id
   и id всех влитых черновиков (у не слитых — пусто); зависимости переводятся на новые id.

Сходство пары (a, b), все части 0…1:
  нормализация: нижний регистр, ё → е, слова [a-zа-я0-9]+, стоп-слова RU/EN (служебные слова и общие глаголы
  «сделать/добавить/выпустить…»), «обрезка» окончаний (лёгкий стеммер RU/EN) и усечение основы до 7/8 знаков;
  title_cos — косинус tf-idf основ названий; title_tri — Жаккар символьных триграмм названий;
  desc_cos — косинус tf-idf основ описаний; desc_jac — Жаккар множеств основ описаний;
  full_cos — косинус tf-idf «название ×2 + описание + теги»;
  балл = 0,25·title_cos + 0,15·title_tri + 0,20·desc_cos + 0,10·desc_jac + 0,30·full_cos.
  tf = 1 + ln(частота), idf = ln((1 + N)/(1 + df)) + 1 по всем черновикам прогона (частые слова продукта весят меньше).
  Порог 0,275 откалиброван на реальном прогоне (139 кандидатов, 14 известных слияний): 12 из 14 найдены без ложных.

--append G7: существующий data/proposals.json сохраняет id; черновики указанных групп сверяются с реестром и между
собой; дубль существующего вливается в него (существующее остаётся), новые получают следующие номера P###.
Отчёт — stdout и build/merge-report.json (слияния с баллами и причиной выбора победителя, не слитые, кандидаты на
ручную проверку, ручные нарушения минимумов, карта id); --dry-run пишет только отчёт. Только стандартная библиотека.
"""
import argparse
import itertools
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_registry import category_requirements  # noqa: E402

CATEGORY_ORDER = ["product", "acquisition", "conversion", "retention", "monetization", "analytics", "partnerships",
                  "localization", "new_lines", "platform"]
CLASS_RANK = {"A": 0, "B": 1, "C": 2, "D": 3}
DEFAULT_THRESHOLD = 0.275
DEFAULT_TITLE_THRESHOLD = 0.75
REVIEW_MARGIN = 0.10          # кандидаты на ручную проверку: балл ≥ порог − 0,10
CHAIN_FACTOR = 0.5            # среднее сходство между группами ≥ 0,5·порога (защита от «цепочек»)
MAX_GROUP = 5
AT_RISK_SLACK = 2             # запас над минимумом категории, при котором победитель берётся из неё
SIM_WEIGHTS = {"title_cos": 0.25, "title_tri": 0.15, "desc_cos": 0.20, "desc_jac": 0.10, "full_cos": 0.30}

STOP = set((
    "и в во на для по с со из к ко о об от у за не ни что как это или при без над под до после чтобы его её ее их "
    "а но же ли бы то так также уже ещё еще все всё весь вся этот эта эти тот та те свой своя свои своё свое "
    "который которая которые которое где когда если чем там тут сам сама сами один одна одно через между "
    "вместо только даже очень более менее можно нужно надо есть нет был была были будет будут ваш ваша ваши наш "
    "сделать сделайте добавить выпустить запустить дать ввести создать показать показывать показывайте перевести "
    "вынести довести открыть открывать сделай давать добавлять "
    "the of to a an for and in on with by from at is are be this that into via or as it its not no your our "
    "add make build create launch ship release new use using get").split())
RU_END = sorted(set((
    "ейшими ейшего ейшему ейшая ейший ость ости остью ами ями ием иями ией ьев ов ев ей ой ий ый ая яя ое ее ие ые "
    "ую юю ого его ому ему ыми ими ых их ом ем ам ям ах ях ию ью ия ья ть ти ет ют ит ят ешь ишь ете ите ут ат ила "
    "ыла ило ыло или ыли ся сь а я о е и ы у ю ь й").split()), key=len, reverse=True)
EN_END = ["ations", "ation", "ings", "ing", "edly", "ed", "ers", "er", "es", "ly", "ments", "ment", "s"]
WORD_RE = re.compile(r"[a-zа-я0-9]+")


# ---------------------------------------------------------------- нормализация и сходство
def words(text):
    """Слова текста: нижний регистр, ё → е."""
    return WORD_RE.findall(str(text or "").lower().replace("ё", "е"))


def stem(w):
    """Лёгкая «обрезка» окончаний RU/EN и усечение основы (грубая, но устойчивая к падежам и числам)."""
    if re.fullmatch(r"[а-я]+", w):
        if len(w) >= 6 and w[-2:] in ("ся", "сь"):
            w = w[:-2]
        for e in RU_END:
            if w.endswith(e) and len(w) - len(e) >= 3:
                w = w[:-len(e)]
                break
        return w[:7]
    if re.fullmatch(r"[a-z]+", w):
        for e in EN_END:
            if w.endswith(e) and len(w) - len(e) >= 3:
                w = w[:-len(e)]
                break
        return w[:8]
    return w


def stems(text):
    """Список основ значимых слов (без стоп-слов; кириллица от 3 букв, латиница и цифры от 2)."""
    out = []
    for w in words(text):
        if w in STOP or len(w) < 2 or (len(w) < 3 and re.match(r"[а-я]", w)):
            continue
        out.append(stem(w))
    return out


def trigrams(text):
    """Множество символьных триграмм текста без стоп-слов."""
    s = " %s " % " ".join(w for w in words(text) if w not in STOP)
    return {s[i:i + 3] for i in range(len(s) - 2)} if len(s) > 3 else set()


def tfidf(docs):
    """Нормированные tf-idf векторы (tf = 1 + ln f, idf = ln((1+N)/(1+df)) + 1)."""
    df = Counter()
    for d in docs:
        df.update(set(d))
    n = len(docs)
    idf = {t: math.log((1.0 + n) / (1.0 + c)) + 1.0 for t, c in df.items()}
    vecs = []
    for d in docs:
        v = {t: (1.0 + math.log(c)) * idf[t] for t, c in Counter(d).items()}
        norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
        vecs.append({t: x / norm for t, x in v.items()})
    return vecs


def cosine(a, b):
    if len(a) > len(b):
        a, b = b, a
    return sum(x * b.get(t, 0.0) for t, x in a.items())


def jaccard(a, b):
    return len(a & b) / float(len(a | b)) if (a or b) else 0.0


class Similarity:
    """Попарное сходство набора предложений (векторы считаются один раз по всему набору)."""

    def __init__(self, props, weights=None):
        self.w = dict(weights or SIM_WEIGHTS)
        self.ids = [str(p.get("id")) for p in props]
        self.pos = {pid: k for k, pid in enumerate(self.ids)}
        T = [stems(p.get("title")) for p in props]
        D = [stems(p.get("description")) for p in props]
        F = [t * 2 + d + stems(" ".join(map(str, p.get("tags") or []))) for t, d, p in zip(T, D, props)]
        self.tset, self.dset = [set(t) for t in T], [set(d) for d in D]
        self.tv, self.dv, self.fv = tfidf(T), tfidf(D), tfidf(F)
        self.tt = [trigrams(p.get("title")) for p in props]

    def parts(self, i, j):
        """Части сходства и итоговый балл пары по индексам."""
        r = {"title_cos": cosine(self.tv[i], self.tv[j]), "title_tri": jaccard(self.tt[i], self.tt[j]),
             "desc_cos": cosine(self.dv[i], self.dv[j]), "desc_jac": jaccard(self.dset[i], self.dset[j]),
             "full_cos": cosine(self.fv[i], self.fv[j])}
        den = sum(self.w.values()) or 1.0
        r["score"] = sum(self.w[k] * r[k] for k in self.w) / den
        r["title_jac"] = jaccard(self.tset[i], self.tset[j])
        return r

    def score(self, a, b):
        """Балл по id."""
        return self.parts(self.pos[a], self.pos[b])["score"]

    def pairs(self, min_score=0.0, idx=None, min_title=0.999):
        """Все пары (i, j, parts) с баллом ≥ min_score или Жаккаром основ названий ≥ min_title, по убыванию балла."""
        idx = list(range(len(self.ids))) if idx is None else idx
        out = []
        for i, j in itertools.combinations(idx, 2):
            r = self.parts(i, j)
            if r["score"] >= min_score or r["title_jac"] >= min_title:
                out.append((i, j, r))
        out.sort(key=lambda x: (-x[2]["score"], self.ids[x[0]], self.ids[x[1]]))
        return out


def rounded(parts):
    return {k: round(v, 3) for k, v in parts.items()}


# ---------------------------------------------------------------- загрузка
def load_drafts(data_dir, groups=None):
    """Список элементов {file, group, p} из черновиков (groups — ограничить группами)."""
    items = []
    files = sorted(data_dir.glob("proposals-draft-*.json"))
    if groups:
        files = [f for f in files if f.stem[len("proposals-draft-"):] in groups]
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
            p["id"] = str(p["id"])
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


def load_pairs(path):
    """--pairs: {"победитель": ["проигравший", …]} (строка вместо списка допустима) → [(winner, [losers])]."""
    m = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(m, dict):
        raise ValueError("pairs.json должен быть объектом {\"победитель\": [\"проигравшие\"…]}")
    out = []
    for w, losers in m.items():
        if isinstance(losers, str):
            losers = [losers]
        out.append((str(w), [str(x) for x in losers or [] if str(x) != str(w)]))
    return out


def load_config(out_dir):
    p = out_dir / "build" / "run-config.json"
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    except json.JSONDecodeError:
        return {}


# ---------------------------------------------------------------- слияние
def completeness(p):
    """Полнота описания: число доказательств, длина описания и обоснования, шаги."""
    return (len(p.get("evidence") or []), len(str(p.get("description") or "")) + len(str(p.get("rationale") or ""))
            + 40 * len(p.get("steps") or []))


def quality_key(it):
    """Меньше — лучше: класс доказательств, полнота, порядок."""
    p = it["p"]
    comp = completeness(p)
    return (CLASS_RANK.get(p.get("evidence_class"), 9), -comp[0], -comp[1], it["order"])


def absorb(keeper, dup, tag=True):
    """Переносит в keeper id, доказательства (без дублей по url/file), теги, зависимости дубля; тег merged:<id>."""
    kp, dp = keeper["p"], dup["p"]
    keeper["absorbed"] += [dp["id"]] + [x for x in dup["absorbed"] if x != dp["id"]]

    def ekey(e):
        if not isinstance(e, dict):
            return None
        if e.get("url") or e.get("file"):
            return (str(e.get("url") or "").strip().rstrip("/").lower(), str(e.get("file") or "").strip())
        return ("", "", str(e.get("title") or ""), str(e.get("note") or ""))

    seen = {ekey(e) for e in kp.get("evidence") or []}
    for e in dp.get("evidence") or []:
        k = ekey(e)
        if k is not None and k not in seen:
            kp.setdefault("evidence", []).append(e)
            seen.add(k)
    if not isinstance(kp.get("tags"), list):
        kp["tags"] = []
    tags = kp["tags"]
    for t in (dp.get("tags") or []) + (["merged:%s" % dp["id"]] if tag else []):
        if t not in tags:
            tags.append(t)
    for d in dp.get("dependencies") or []:
        if d not in (kp.get("dependencies") or []):
            kp.setdefault("dependencies", []).append(d)


def choose_winner(members, counts, reqs, fixed=None):
    """Победитель группы с учётом минимумов категорий.

    Возвращает (winner, merged_losers, kept_apart[(item, причина)], reason)."""
    cands = [fixed] if fixed is not None else list(members)
    best = None
    for w in cands:
        tmp = Counter(counts)
        ok, apart = [], []
        for l in sorted([m for m in members if m is not w], key=quality_key):
            c = l["p"].get("category")
            need = (reqs.get(c) or {}).get("required") or 0
            if need and tmp[c] >= need and tmp[c] - 1 < need:
                apart.append((l, "уронило бы минимум категории %s (%d при минимуме %d)" % (c, tmp[c], need)))
                continue
            ok.append(l)
            tmp[c] -= 1
        wc = w["p"].get("category")
        need_w = (reqs.get(wc) or {}).get("required") or 0
        slack = counts[wc] - need_w if need_w else 10 ** 6
        at_risk = slack <= AT_RISK_SLACK
        key = (-len(ok), 0 if at_risk else 1, slack if at_risk else 0) + quality_key(w)
        if best is None or key < best[0]:
            best = (key, w, ok, apart, at_risk, slack)
    _, w, ok, apart, at_risk, slack = best
    if fixed is not None:
        reason = "задан вручную"
    elif len(members) - 1 > len(ok) or (apart and len(cands) > 1):
        reason = "максимум слияний без нарушения минимумов категорий"
    elif at_risk and len({m["p"].get("category") for m in members}) > 1:
        wc = w["p"].get("category")
        reason = "категория %s близко к минимуму или ниже (%d при минимуме %d)" % (
            wc, counts[wc], (reqs.get(wc) or {}).get("required") or 0)
    else:
        others = [m for m in members if m is not w]
        wcls = CLASS_RANK.get(w["p"].get("evidence_class"), 9)
        if others and all(wcls < CLASS_RANK.get(m["p"].get("evidence_class"), 9) for m in others):
            reason = "лучший класс доказательств (%s)" % w["p"].get("evidence_class")
        elif others and all(completeness(w["p"]) > completeness(m["p"]) for m in others):
            reason = "более полное описание и доказательства"
        else:
            reason = "равные основания — раньше по порядку"
    return w, ok, apart, reason


def apply_merge(winner, losers, alias, counts):
    for l in losers:
        absorb(winner, l)
        alias[l["p"]["id"]] = winner["p"]["id"]
        counts[l["p"].get("category")] -= 1


def manual_merges(items, by_id, pairs, force, reqs, counts, alias, pairs_winner):
    """Ручные слияния (--pairs и merge-map). Возвращает (merges, dropped, warnings, min_violations)."""
    merges, dropped, warns, viol = [], [], [], []
    groups = []
    for w, losers in pairs:
        groups.append((w, losers, "pairs"))
    for drop, (into, why) in force.items():
        groups.append((into, [drop], "merge-map: " + why))
    for w, losers, origin in groups:
        def live(pid):
            while pid in alias:
                pid = alias[pid]
            return pid
        w_live = live(w)
        missing = [x for x in [w] + losers if x not in by_id]
        if missing:
            warns.append("ручное слияние %s ← %s: нет черновиков %s — пропущено" % (w, ", ".join(losers), ", ".join(missing)))
            continue
        ls = []
        for x in losers:
            lx = live(x)
            if lx != w_live and by_id[lx] not in ls:
                ls.append(by_id[lx])
        if not ls:
            continue
        members = [by_id[w_live]] + ls
        if pairs_winner == "auto" and origin == "pairs":
            winner, ok, apart, reason = choose_winner(members, counts, reqs)
            for it, why in apart:
                warns.append("ручная группа %s: %s не слито — %s" % (w, it["p"]["id"], why))
            ls = ok
            reason = "ручная группа, победитель выбран автоматически: " + reason
        else:
            winner, reason = by_id[w_live], "задан вручную (%s)" % origin
            ls = [m for m in members if m is not winner]
            before = Counter(counts)
            after = Counter(counts)
            for l in ls:
                after[l["p"].get("category")] -= 1
            for c, r in reqs.items():
                need = r.get("required") or 0
                if need and before[c] >= need > after[c]:
                    alt = [m["p"]["id"] for m in members if m["p"].get("category") == c]
                    viol.append({"winner": winner["p"]["id"], "losers": [l["p"]["id"] for l in ls], "category": c,
                                 "before": before[c], "after": after[c], "required": need,
                                 "hint": "сделайте победителем %s или используйте --pairs-winner auto" % ", ".join(alt)})
        apply_merge(winner, ls, alias, counts)
        merges.append({"winner": winner["p"]["id"], "losers": [l["p"]["id"] for l in ls], "score": None,
                       "reason": reason, "manual": True})
        for l in ls:
            dropped.append({"id": l["p"]["id"], "title": l["p"].get("title"), "into": winner["p"]["id"], "similarity": None,
                            "reason": "manual: " + origin})
    return merges, dropped, warns, viol


def auto_merge(alive, sim, thr, title_thr, distinct, reqs, counts, alias, max_group=MAX_GROUP):
    """Автодедупликация по сходству. Возвращает (merges, dropped, not_merged, candidates)."""
    pos = {it["p"]["id"]: k for k, it in enumerate(alive)}
    idx = [sim.pos[it["p"]["id"]] for it in alive]
    pairs = sim.pairs(min(thr - REVIEW_MARGIN, 0.999), idx, min(title_thr, 0.999))
    group = {it["p"]["id"]: {it["p"]["id"]} for it in alive}
    link = {}
    candidates = []
    for i, j, r in pairs:
        a, b = sim.ids[i], sim.ids[j]
        hit = r["score"] >= thr or r["title_jac"] >= title_thr
        if not hit:
            candidates.append({"a": a, "b": b, "similarity": round(r["score"], 3), "parts": rounded(r),
                               "a_title": alive[pos[a]]["p"].get("title"), "b_title": alive[pos[b]]["p"].get("title")})
            continue
        ga, gb = group[a], group[b]
        if ga is gb:
            continue
        if any(frozenset((x, y)) in distinct for x in ga for y in gb):
            candidates.append({"a": a, "b": b, "similarity": round(r["score"], 3), "parts": rounded(r), "note": "distinct",
                               "a_title": alive[pos[a]]["p"].get("title"), "b_title": alive[pos[b]]["p"].get("title")})
            continue
        if len(ga) + len(gb) > max_group:
            candidates.append({"a": a, "b": b, "similarity": round(r["score"], 3), "parts": rounded(r),
                               "note": "группа больше %d" % max_group,
                               "a_title": alive[pos[a]]["p"].get("title"), "b_title": alive[pos[b]]["p"].get("title")})
            continue
        avg = sum(sim.score(x, y) for x in ga for y in gb) / float(len(ga) * len(gb))
        if avg < CHAIN_FACTOR * thr and r["title_jac"] < title_thr:
            candidates.append({"a": a, "b": b, "similarity": round(r["score"], 3), "parts": rounded(r),
                               "note": "цепочка: среднее сходство групп %.3f" % avg,
                               "a_title": alive[pos[a]]["p"].get("title"), "b_title": alive[pos[b]]["p"].get("title")})
            continue
        merged = ga | gb
        for x in merged:
            group[x] = merged
        link.setdefault(frozenset(merged), [])
        for key in (frozenset(ga), frozenset(gb)):
            link[frozenset(merged)] += link.pop(key, [])
        link[frozenset(merged)].append({"a": a, "b": b, "score": round(r["score"], 3), "parts": rounded(r)})
    merges, dropped, not_merged = [], [], []
    clusters = sorted({frozenset(g) for g in group.values() if len(g) > 1},
                      key=lambda g: (-max(e["score"] for e in link.get(g, [{"score": 0}])), sorted(g)))
    for g in clusters:
        members = sorted((alive[pos[x]] for x in g), key=lambda it: it["order"])
        winner, ok, apart, reason = choose_winner(members, counts, reqs)
        edges = link.get(g, [])
        top = max((e["score"] for e in edges), default=None)
        apply_merge(winner, ok, alias, counts)
        if ok:
            merges.append({"winner": winner["p"]["id"], "losers": [l["p"]["id"] for l in ok], "score": top,
                           "pairs": edges, "reason": reason, "manual": False,
                           "categories": {m["p"]["id"]: m["p"].get("category") for m in members}})
        for l in ok:
            sc = max((e["score"] for e in edges if l["p"]["id"] in (e["a"], e["b"])), default=top)
            dropped.append({"id": l["p"]["id"], "title": l["p"].get("title"), "into": winner["p"]["id"],
                            "similarity": sc, "reason": "similarity"})
        for l, why in apart:
            not_merged.append({"id": l["p"]["id"], "title": l["p"].get("title"), "would_merge_into": winner["p"]["id"],
                               "similarity": max((e["score"] for e in edges if l["p"]["id"] in (e["a"], e["b"])), default=top),
                               "reason": why})
    return merges, dropped, not_merged, candidates


def resolve(pid, alias, depth=0):
    while pid in alias and depth < 100:
        pid = alias[pid]
        depth += 1
    return pid


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


def remap_dependencies(props, id_map, alias, keep_ids=()):
    """Зависимости черновиков → новые id; ссылки на влитые дубли — на держателя. Возвращает предупреждения."""
    warn = []
    known = set(keep_ids)
    for p in props:
        new = []
        for d in p.get("dependencies") or []:
            d = str(d)
            target = id_map.get(resolve(d, alias))
            if target is None and (d in known or (not known and re.fullmatch(r"P\d{3,}", d))):
                target = d
            if target is None:
                warn.append("%s: зависимость %r не найдена среди черновиков — удалена" % (p["id"], d))
                continue
            if target != p["id"] and target not in new:
                new.append(target)
        p["dependencies"] = new
    return warn


def prepare(items):
    for k, it in enumerate(items):
        it["order"] = k
        it["absorbed"] = list(it["p"].get("merged_from") or [])
        if it["absorbed"] and it["absorbed"][0] == it["p"]["id"]:
            it["absorbed"] = it["absorbed"][1:]


def print_suggest(sim, items, top, thr):
    rows = sim.pairs(0.0)
    print("Пары-кандидаты по убыванию сходства (порог слияния %.3f); части: title_cos/title_tri/desc_cos/desc_jac/full_cos"
          % thr)
    by = {it["p"]["id"]: it["p"] for it in items}
    for n, (i, j, r) in enumerate(rows[:top], 1):
        a, b = sim.ids[i], sim.ids[j]
        mark = "≥" if r["score"] >= thr else " "
        print("%3d %s %.3f  %s [%s] «%s»\n             %s [%s] «%s»\n             %.2f/%.2f/%.2f/%.2f/%.2f"
              % (n, mark, r["score"], a, by[a].get("category"), by[a].get("title"), b, by[b].get("category"),
                 by[b].get("title"), r["title_cos"], r["title_tri"], r["desc_cos"], r["desc_jac"], r["full_cos"]))
    print("Шаблон ручных пар: {\"победитель\": [\"проигравший\"]} → --pairs build/merge-pairs.json")


def run_append(out_dir, a, cfg, reqs):
    """--append: новые черновики указанных групп к существующему реестру без перенумерации."""
    reg_path = out_dir / "data" / "proposals.json"
    if not reg_path.exists():
        print("нет data/proposals.json — сначала обычное слияние", file=sys.stderr)
        return 1
    existing = [p for p in json.loads(reg_path.read_text(encoding="utf-8")) if isinstance(p, dict) and p.get("id")]
    groups = {g.strip() for g in a.append.split(",") if g.strip()}
    files, new_items = load_drafts(out_dir / "data", groups)
    if not new_items:
        print("нет черновиков групп %s" % ", ".join(sorted(groups)), file=sys.stderr)
        return 1
    old_items = [{"file": "proposals.json", "group": p.get("source_group") or "", "p": p} for p in existing]
    prepare(old_items + new_items)
    for it in old_items:
        it["absorbed"] = [x for x in (it["p"].get("merged_from") or [])[1:]]
    sim = Similarity([it["p"] for it in old_items + new_items])
    counts = Counter(p.get("category") for p in existing)
    alias, merges, dropped = {}, [], []
    old_ids = {p["id"] for p in existing}
    by_id = {it["p"]["id"]: it for it in old_items + new_items}
    new_kept = []
    for it in new_items:
        best = None
        for other in old_items + new_kept:
            r = sim.parts(sim.pos[it["p"]["id"]], sim.pos[other["p"]["id"]])
            if r["score"] >= a.threshold or r["title_jac"] >= a.title_threshold:
                if best is None or r["score"] > best[1]["score"]:
                    best = (other, r)
        if best is None:
            new_kept.append(it)
            counts[it["p"].get("category")] += 1
            continue
        keeper, r = best
        absorb(keeper, it)
        alias[it["p"]["id"]] = keeper["p"]["id"]
        merges.append({"winner": keeper["p"]["id"], "losers": [it["p"]["id"]], "score": round(r["score"], 3),
                       "parts": rounded(r), "reason": "append: существующее предложение сохраняется", "manual": False})
        dropped.append({"id": it["p"]["id"], "title": it["p"].get("title"), "into": keeper["p"]["id"],
                        "similarity": round(r["score"], 3), "reason": "append-similarity"})
    nums = [int(re.sub(r"\D", "", pid)) for pid in old_ids if re.fullmatch(r"P\d+", pid)]
    nxt = max(nums or [0]) + 1
    id_map = {pid: pid for pid in old_ids}
    for it in new_kept:
        id_map[it["p"]["id"]] = "P%03d" % nxt
        nxt += 1
    out = []
    for it in old_items:
        p = dict(it["p"])
        if it["absorbed"]:
            base = (p.get("merged_from") or [])[:1] or [p["id"]]
            p["merged_from"] = list(dict.fromkeys(base + it["absorbed"]))
        out.append(p)
    added = []
    for it in new_kept:
        p = dict(it["p"])
        orig = p["id"]
        p["id"] = id_map[orig]
        p.setdefault("source_group", it["group"])
        p["merged_from"] = list(dict.fromkeys([orig] + it["absorbed"])) if it["absorbed"] else []
        added.append(p)
    warns = remap_dependencies(added, id_map, alias, keep_ids=old_ids | set(id_map.values()))
    full_map = dict(id_map)
    for old, tgt in alias.items():
        full_map[old] = id_map.get(resolve(tgt, alias), tgt)
    report = {"mode": "append", "groups": sorted(groups), "files": [f.name for f in files], "existing": len(existing),
              "loaded": len(new_items), "added": [p["id"] for p in added], "kept": len(out) + len(added),
              "merges": merges, "dropped": dropped, "id_map": full_map, "threshold": a.threshold,
              "title_threshold": a.title_threshold, "warnings": warns, "dry_run": a.dry_run}
    print("Дописано к реестру: %d новых из %d черновиков (%s); слито с существующими: %d"
          % (len(added), len(new_items), ", ".join(sorted(groups)), len(dropped)))
    for d in dropped:
        print("  слито %s «%s» → %s (сходство %.2f)" % (d["id"], d["title"], d["into"], d["similarity"]))
    for w in warns:
        print("  ! " + w)
    (out_dir / "build").mkdir(parents=True, exist_ok=True)
    (out_dir / "build" / "merge-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if a.dry_run:
        return 0
    reg_path.write_text(json.dumps(out + added, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Записано: data/proposals.json, build/merge-report.json")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Склейка черновиков реестра с поиском дублей и перенумерацией.")
    ap.add_argument("out", help="папка прогона <OUT>")
    ap.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD,
                    help="порог объединённого сходства (%.3f)" % DEFAULT_THRESHOLD)
    ap.add_argument("--title-threshold", type=float, default=DEFAULT_TITLE_THRESHOLD,
                    help="порог Жаккара основ названий — сливать почти одинаковые названия (0.75)")
    ap.add_argument("--min", type=int, default=None, help="минимум предложений для минимумов категорий (иначе run-config или 100)")
    ap.add_argument("--max-group", type=int, default=MAX_GROUP, help="наибольший размер группы дублей (5)")
    ap.add_argument("--pairs", help="JSON ручных пар {\"победитель\": [\"проигравшие\"…]}")
    ap.add_argument("--pairs-winner", choices=["given", "auto"], default="given",
                    help="given — победитель как в файле; auto — выбрать по правилам (минимумы категорий, класс, полнота)")
    ap.add_argument("--auto", action="store_true", help="с --pairs: дополнительно автослияние по сходству")
    ap.add_argument("--no-auto", action="store_true", help="без автослияния (только ручные карты)")
    ap.add_argument("--suggest", action="store_true", help="только напечатать пары-кандидаты по убыванию сходства")
    ap.add_argument("--top", type=int, default=40, help="сколько пар печатать в --suggest (40)")
    ap.add_argument("--append", help="группы черновиков через запятую — дописать к готовому data/proposals.json")
    ap.add_argument("--dry-run", action="store_true", help="только отчёт, без записи proposals.json")
    a = ap.parse_args(argv)
    out_dir = Path(a.out).resolve()
    cfg = load_config(out_dir)
    min_n = a.min if a.min is not None else (cfg.get("strategy") or {}).get("proposals_min") or 100
    reqs = category_requirements(cfg, min_n)
    if a.append:
        return run_append(out_dir, a, cfg, reqs)
    files, items = load_drafts(out_dir / "data")
    if not files:
        print("нет черновиков data/proposals-draft-*.json в %s" % out_dir, file=sys.stderr)
        return 1
    dup_ids = [k for k, v in Counter(it["p"]["id"] for it in items).items() if v > 1]
    if dup_ids:
        print("повторяющиеся id черновиков: %s — исправьте до слияния" % ", ".join(sorted(dup_ids)), file=sys.stderr)
        return 1
    prepare(items)
    sim = Similarity([it["p"] for it in items])
    if a.suggest:
        print_suggest(sim, items, a.top, a.threshold)
        return 0
    by_id = {it["p"]["id"]: it for it in items}
    force, distinct = load_map(out_dir / "build" / "merge-map.json")
    pairs = load_pairs(a.pairs) if a.pairs else []
    counts = Counter(it["p"].get("category") for it in items)
    counts_before = dict(counts)
    alias = {}
    m_merges, m_dropped, warns, viol = manual_merges(items, by_id, pairs, force, reqs, counts, alias, a.pairs_winner)
    alive = [it for it in items if it["p"]["id"] not in alias]
    do_auto = not a.no_auto and (not a.pairs or a.auto)
    if do_auto:
        a_merges, a_dropped, not_merged, candidates = auto_merge(alive, sim, a.threshold, a.title_threshold, distinct,
                                                                 reqs, counts, alias, a.max_group)
    else:
        a_merges, a_dropped, not_merged, candidates = [], [], [], []
    kept = [it for it in items if it["p"]["id"] not in alias]
    props, id_map = finalize(kept)
    warns += remap_dependencies(props, id_map, alias)
    full_map = dict(id_map)
    for old in alias:
        tgt = resolve(old, alias)
        if tgt in id_map:
            full_map[old] = id_map[tgt]
    for m in m_merges + a_merges:
        m["winner_new_id"] = id_map.get(m["winner"])
    dropped = m_dropped + a_dropped
    for d in dropped:
        d["into"] = resolve(d["into"], alias)
    report = {"files": [f.name for f in files], "loaded": len(items), "kept": len(props), "threshold": a.threshold,
              "title_threshold": a.title_threshold, "similarity_weights": SIM_WEIGHTS, "auto": do_auto,
              "pairs_file": a.pairs, "pairs_winner": a.pairs_winner, "min": min_n,
              "merges": m_merges + a_merges, "dropped": dropped, "not_merged": not_merged,
              "candidates": sorted(candidates, key=lambda c: -c["similarity"])[:60], "min_violations": viol,
              "category_counts": {"before": counts_before, "after": dict(Counter(p.get("category") for p in props)),
                                  "required": {c: r["required"] for c, r in reqs.items()}},
              "id_map": full_map, "warnings": warns, "dry_run": a.dry_run}
    print("Загружено %d из %d файлов; оставлено %d, слито %d%s"
          % (len(items), len(files), len(props), len(dropped), "" if do_auto else " (автослияние выключено)"))
    for m in m_merges + a_merges:
        sc = "" if m["score"] is None else " (сходство %.3f)" % m["score"]
        print("  %s ← %s%s; победитель: %s" % (m["winner"], ", ".join(m["losers"]), sc, m["reason"]))
    for nm in not_merged:
        print("  не слито %s «%s» (с %s): %s" % (nm["id"], nm["title"], nm["would_merge_into"], nm["reason"]))
    for v in viol:
        print("  ! ручное слияние %s ← %s роняет минимум %s: %d → %d < %d; %s"
              % (v["winner"], ", ".join(v["losers"]), v["category"], v["before"], v["after"], v["required"], v["hint"]))
    if candidates:
        print("Пары на ручную проверку (близко к порогу): %d — см. build/merge-report.json или --suggest" % len(candidates))
    for w in warns:
        print("  ! " + w)
    (out_dir / "build").mkdir(parents=True, exist_ok=True)
    (out_dir / "build" / "merge-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if a.dry_run:
        print("Записано: build/merge-report.json (--dry-run, реестр не менялся)")
        return 0
    (out_dir / "data" / "proposals.json").write_text(json.dumps(props, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Записано: data/proposals.json, build/merge-report.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
