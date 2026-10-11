#!/usr/bin/env python3
"""Заготовки сопутствующих документов стратегии: decision-brief, вопросы владельцу, глоссарий, раздел 17 «Приложение».

  build_appendix.py <OUT> [--only decision-brief,questions,glossary,appendix] [--force] [--json]

Источники (все необязательны): build/run-config.json (продукт, глубина, профиль, assumptions), data/fact-check.json
(нерешённые расхождения; формат терпимый: {fact|claim, phase1_value|was|input_value, agent_value|now|found_value, source,
resolved_value|status}), метки [ДОПУЩЕНИЕ] в research/**/*.md и build/parts/*.md, data/scores.json и data/proposals.json
(кандидаты в ставки по dep_rank), research/questions-owner.md (развилки), data/sources.json (даты проверки).
Шаблоны — templates/decision-brief.md и templates/glossary.md.

Выход:
  research/decision-brief.md   — ставки, развилки с вариантом по умолчанию, допущения, открытые факты (места <заполнить>);
  research/questions-owner.md  — кандидаты в вопросы владельцу: итог ≤ 10 + остальные (fact-check → assumptions → метки);
  research/glossary.md         — термины словаря из шаблона, которые встречаются в текстах прогона;
  build/appendix-17.md         — черновик раздела 17 «Приложение» (ссылки на существующие файлы и список допущений);
                                 вставить в build/parts/strategy-NN.md вручную (в glob частей он не попадает).
Существующий файл в research/ не затирается: новый вариант ложится рядом как *.generated.md (--force — перезаписать).
Вывод детерминирован: одинаковые входы → одинаковые файлы (дата — из run-config.created или сегодняшняя).
Только стандартная библиотека.
"""
import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
TEMPLATES = HERE.parent / "templates"
MARK = re.compile(r"\[(?:ДОПУЩЕНИЕ|допущение|Допущение)[^\]]*\]")
TERM_LINE = re.compile(r"^- \*\*(.+?)\*\*(?: \[синонимы: (.+?)\])? — (.+)$")
FILL = "<заполнить>"


def load_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def cell(x, n=200):
    s = re.sub(r"\s+", " ", str(x if x is not None else "")).strip().replace("|", "\\|")
    return s if len(s) <= n else s[: n - 1] + "…"


def pick(d, keys):
    for k in keys:
        if isinstance(d, dict) and d.get(k) not in (None, ""):
            return d[k]
    return None


def fact_items(out):
    fc = load_json(out / "data" / "fact-check.json")
    items = fc if isinstance(fc, list) else (fc.get("items") or fc.get("discrepancies") or fc.get("checks") or []) if isinstance(fc, dict) else []
    return [it for it in items if isinstance(it, dict)]


def open_facts(out):
    res = []
    for it in fact_items(out):
        resolved = pick(it, ("resolved_value",))
        status = str(it.get("status") or "").lower()
        if resolved in (None, "") and status not in ("resolved", "решено", "closed", "закрыто", "ok"):
            res.append({"fact": pick(it, ("fact", "claim", "topic", "what", "title")) or "?",
                        "was": pick(it, ("phase1_value", "was", "input_value", "before")),
                        "now": pick(it, ("agent_value", "now", "found_value", "after")),
                        "source": pick(it, ("source", "evidence")), "note": it.get("note")})
    return res


def text_files(out):
    files = sorted((out / "research").rglob("*.md")) + sorted((out / "build" / "parts").glob("*.md"))
    return [f for f in files if not f.name.endswith(".generated.md")
            and f.name not in ("questions-owner.md", "glossary.md", "decision-brief.md")]


def markers(out):
    """Метки [ДОПУЩЕНИЕ] в текстах → [{file, line, text}] без повторов по тексту."""
    seen, res = set(), []
    for f in text_files(out):
        try:
            lines = f.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        for i, ln in enumerate(lines, 1):
            if MARK.search(ln):
                t = re.sub(r"[*_`#>]+", "", ln).strip(" -|")
                key = re.sub(r"\W+", " ", MARK.sub("", t)).strip().lower()[:120]
                if key and key not in seen:
                    seen.add(key)
                    res.append({"file": f.relative_to(out).as_posix(), "line": i, "text": cell(t, 180)})
    return res


def owner_questions(out):
    f = out / "research" / "questions-owner.md"
    if not f.is_file():
        return []
    qs = []
    for line in f.read_text(encoding="utf-8").splitlines():
        m = re.match(r"\s*\d+\.\s+(.*)", line)
        if m:
            qs.append(m.group(1).strip())
    return qs


def bets(out, n=5):
    scores = load_json(out / "data" / "scores.json", []) or []
    if not isinstance(scores, list) or not scores:
        return None
    rows = sorted((s for s in scores if isinstance(s, dict) and s.get("id")),
                  key=lambda s: (s.get("dep_rank") or s.get("rank") or 10 ** 6, s.get("id")))
    return rows[:n]


def assumptions(cfg):
    return [str(a) for a in (cfg.get("assumptions") or []) if str(a).strip()]


def render(template, values):
    text = template
    for k, v in values.items():
        text = text.replace("{%s}" % k, v)
    return text


def base_values(out, cfg):
    s = cfg.get("strategy") or {}
    return {"PRODUCT": (cfg.get("product") or {}).get("name") or out.name, "DATE": str(cfg.get("created") or date.today().isoformat())[:10],
            "DEPTH": s.get("depth") or "?", "PROFILE": s.get("profile") or "standard"}


# ---------------------------------------------------------------- документы

def decision_brief(out, cfg):
    tpl = (TEMPLATES / "decision-brief.md").read_text(encoding="utf-8")
    b = bets(out)
    if b:
        bl = ["| Ранг с учётом зависимостей | ID | Предложение | Категория | Класс | Предпосылки |", "|---|---|---|---|---|---|"]
        for s in b:
            bl.append("| %s | %s | %s | %s | %s | %s |" % (s.get("dep_rank") or s.get("rank") or "—", s["id"], cell(s.get("title"), 90),
                                                        s.get("category") or "—", s.get("evidence_class") or "—",
                                                        ", ".join(s.get("blocked_by") or []) or "нет"))
        bl += ["", "Ставки: 1. %s 2. %s 3. %s" % (FILL, FILL, FILL)]
    else:
        bl = ["Нет data/scores.json (оценка ещё не выполнена). Ставки: 1. %s 2. %s 3. %s" % (FILL, FILL, FILL)]
    qs = owner_questions(out)
    if qs:
        fl = ["| Развилка | Вариант по умолчанию | Цена альтернативы |", "|---|---|---|"] + \
             ["| %s | %s | %s |" % (cell(q, 160), FILL, FILL) for q in qs[:8]]
    else:
        fl = ["Нет research/questions-owner.md — развилки %s (вариант по умолчанию + цена альтернативы)." % FILL]
    asm = assumptions(cfg)
    mk = markers(out)
    al = ["- %s" % cell(a, 200) for a in asm[:12]]
    if mk:
        al.append("- Меток [ДОПУЩЕНИЕ] в текстах: %d (первые: %s)" % (len(mk), "; ".join("%s:%d" % (m["file"], m["line"]) for m in mk[:5])))
    if not al:
        al = ["Допущений не записано (run-config.assumptions пуст, меток [ДОПУЩЕНИЕ] нет)."]
    of = open_facts(out)
    ol = ["| Факт | Во входах | Найдено | Источник |", "|---|---|---|---|"] + \
         ["| %s | %s | %s | %s |" % (cell(f["fact"], 80), cell(f["was"], 60), cell(f["now"], 60), cell(f["source"], 60)) for f in of[:10]] \
        if of else ["Нерешённых расхождений нет (или data/fact-check.json отсутствует)."]
    v = base_values(out, cfg)
    v.update({"BETS": "\n".join(bl), "FORKS": "\n".join(fl), "ASSUMPTIONS": "\n".join(al), "OPEN_FACTS": "\n".join(ol)})
    return render(tpl, v)


def questions(out, cfg):
    cands = []
    for f in open_facts(out):
        cands.append("[факт] %s: во входах «%s», найдено «%s»%s — какое значение верное?" % (
            cell(f["fact"], 80), cell(f["was"], 60), cell(f["now"], 60), (" (%s)" % cell(f["source"], 60)) if f["source"] else ""))
    for a in assumptions(cfg):
        cands.append("[допущение] %s — подтвердите или поправьте." % cell(a, 180))
    for m in markers(out):
        cands.append("[в тексте] %s:%d — %s" % (m["file"], m["line"], m["text"]))
    v = base_values(out, cfg)
    L = ["# Вопросы владельцу: %s" % v["PRODUCT"], "",
         "Дата: %s. Заготовка `build_appendix.py`: кандидаты из сверки фактов, `run-config.assumptions` и меток [ДОПУЩЕНИЕ]. "
         "Оркестратор выбирает не больше 10, формулирует как развилки (вариант по умолчанию + цена альтернативы) и удаляет лишнее." % v["DATE"], "",
         "## Итог (не больше 10)", ""]
    if not cands:
        L += ["Кандидатов нет: расхождений, допущений и меток не найдено.", ""]
    L += ["%d. %s" % (i, c) for i, c in enumerate(cands[:10], 1)]
    if len(cands) > 10:
        L += ["", "## Остальные кандидаты", ""] + ["- %s" % c for c in cands[10:]]
    return "\n".join(L).rstrip() + "\n"


def glossary(out, cfg):
    tpl = (TEMPLATES / "glossary.md").read_text(encoding="utf-8")
    head, _, dict_part = tpl.partition("## Словарь")
    terms = []
    for ln in dict_part.splitlines():
        m = TERM_LINE.match(ln.strip())
        if m:
            syn = [x.strip() for x in (m.group(2) or "").split(";") if x.strip()]
            terms.append((m.group(1), syn, m.group(3)))
    corpus = ""
    for f in text_files(out):
        try:
            corpus += f.read_text(encoding="utf-8") + "\n"
        except (OSError, UnicodeDecodeError):
            pass

    def present(word):
        if not corpus:
            return True
        w = re.escape(word)
        flags = re.I if re.fullmatch(r"[\x00-\x7f]+", word) else 0
        return re.search(r"(?<![\wА-Яа-яЁё])%s(?![\wА-Яа-яЁё])" % w if word[0].isalnum() else w, corpus, flags) is not None
    rows = [(t, d) for t, syn, d in terms if present(t) or any(present(s) for s in syn)]
    tl = ["| Термин | Значение |", "|---|---|"] + ["| %s | %s |" % (cell(t, 60), cell(d, 300)) for t, d in rows]
    if not rows:
        tl = ["Терминов словаря в текстах не найдено."]
    v = base_values(out, cfg)
    v["TERMS"] = "\n".join(tl) + ("" if corpus else "\n\n(Текстов прогона ещё нет — показан весь словарь.)")
    return render(head.rstrip() + "\n", v)


def appendix(out, cfg):
    def ref(path, title):
        return "- %s — `%s`" % (title, path) if (out / path).exists() else "- %s — нет в этом прогоне (`%s`)" % (title, path)
    src = load_json(out / "data" / "sources.json", []) or []
    dates = sorted(str(s.get("date_checked")) for s in src if isinstance(s, dict) and s.get("date_checked"))
    asm = assumptions(cfg)
    mk = markers(out)
    L = ["## 17. Приложение", "",
         ref("deliverables/index.html", "Полный реестр предложений (страница)"), ref("deliverables/strategy.xlsx", "Таблица реестра и плана"),
         ref("research/methodology.md", "Методология оценки"), ref("research/gap-audit.md", "Аудит пробелов и предпосылок"),
         ref("data/fact-check.json", "Сверка фактов"),
         "- Источники — `data/sources.json`: %d записей%s" % (len(src), (", проверены %s…%s" % (dates[0], dates[-1])) if dates else ""),
         ref("research/questions-owner.md", "Вопросы владельцу (≤ 10)"), ref("research/glossary.md", "Глоссарий"),
         ref("research/decision-brief.md", "Решения для владельца (1–2 страницы)"), "",
         "### Допущения", ""]
    L += ["%d. %s" % (i, cell(a, 220)) for i, a in enumerate(asm, 1)] or ["Допущений в run-config не записано."]
    if mk:
        L += ["", "Меток [ДОПУЩЕНИЕ] в текстах: %d — список в `research/questions-owner.md`." % len(mk)]
    return "\n".join(L).rstrip() + "\n"


DOCS = {"decision-brief": ("research/decision-brief.md", decision_brief), "questions": ("research/questions-owner.md", questions),
        "glossary": ("research/glossary.md", glossary), "appendix": ("build/appendix-17.md", appendix)}


def write_doc(out, rel, text, force):
    path = out / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not force and rel.startswith("research/"):
        if path.read_text(encoding="utf-8") == text:
            return rel, "без изменений"
        alt = path.with_name(path.stem + ".generated.md")
        alt.write_text(text, encoding="utf-8")
        return alt.relative_to(out).as_posix(), "рядом с существующим (ручной файл не затёрт; --force — перезаписать)"
    path.write_text(text, encoding="utf-8")
    return rel, "записан"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("out", help="папка прогона <OUT>")
    ap.add_argument("--only", default="", help="через запятую: " + ", ".join(DOCS))
    ap.add_argument("--force", action="store_true", help="перезаписать существующие файлы в research/")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    out = Path(a.out).expanduser().resolve()
    if not out.is_dir():
        print("ошибка: нет папки %s" % out, file=sys.stderr)
        return 2
    only = [x.strip() for x in a.only.split(",") if x.strip()] or list(DOCS)
    bad = [x for x in only if x not in DOCS]
    if bad:
        print("ошибка: неизвестные документы: %s (есть: %s)" % (", ".join(bad), ", ".join(DOCS)), file=sys.stderr)
        return 2
    cfg = load_json(out / "build" / "run-config.json", {}) or {}
    res = []
    for key in only:
        rel, fn = DOCS[key]
        path, what = write_doc(out, rel, fn(out, cfg), a.force)
        res.append({"doc": key, "file": path, "result": what})
    summary = {"files": res, "open_facts": len(open_facts(out)), "assumptions": len(assumptions(cfg)), "markers": len(markers(out))}
    if a.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        for r in res:
            print("%s: %s — %s" % (r["doc"], r["file"], r["result"]))
        print("нерешённых фактов %d, допущений в run-config %d, меток [ДОПУЩЕНИЕ] %d" % (summary["open_facts"], summary["assumptions"], summary["markers"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
