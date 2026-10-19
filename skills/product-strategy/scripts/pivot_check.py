#!/usr/bin/env python3
"""Фаза C4.5 режима идеи: пересмотр идеи после исследования рынка (пивот-чекпоинт, FB-044) → data/premises.json.

  pivot_check.py <OUT> [--init] [--force]       черновик data/premises.json: ключевые предпосылки идеи (отличие, монетизация,
                                                ключевые функции, техническая осуществимость, аудитория) со статусом null —
                                                заполняет агент или оркестратор по research/market.md, integration.md, legal.md
  pivot_check.py <OUT> [--check] [--json]       оценка: опровергнута хотя бы одна ключевая предпосылка (или две «частично») →
                                                нужен вопрос владельцу; печатает готовую карточку AskUserQuestion
                                                («продолжить с исходной / принять сужение / остановиться»); код 0 — решение не
                                                нужно или уже принято, 3 — нужен вопрос, 2 — нет файла или не заполнен
  pivot_check.py <OUT> --decide keep|narrow|stop [--pitch-v2 "…"] [--name "…"] [--type saas] [--forms web,mobile_web]
                       [--kind …] [--reason "…"] [--by owner|default] [--topic-en "<перевод новой темы>"] [--no-refresh]
                                                записать решение: premises.json (decision, decided, by); narrow — идея v2:
                                                run-config idea.version/pitch_v2/history[] (+ product.name/type/forms, idea.kind)
                                                и data/idea.json; затем concept_dossier.py <OUT> [--refresh] (затравки, досье,
                                                план поиска по новой идее; правленное вручную — в *.generated.md) и
                                                typesafe_concept.py <OUT> (светофор), если не --no-refresh; --topic-en
                                                (тема изменилась) — run-config idea.topic_en и idea.topic_en_for = новая
                                                версия, досье строит английские запросы по нему (иначе — заглушки <EN: …>
                                                и предупреждение «перевод относится к прежней версии»)

Схема data/premises.json:
  {"version": 1, "idea_version": 1, "created": "…", "pitch": "…",
   "premises": [{"id": "PR1", "kind": "distinct|monetization|key_feature|feasibility|audience|other", "key": true,
                 "text": "…", "status": null|"confirmed"|"refuted"|"partial", "evidence": "…", "source": "путь:строка или URL"}],
   "narrowing": "вариант сужения (что оставить)" | null,
   "decision": null|"keep"|"narrow"|"stop", "decided": "…", "by": "owner|default", "pitch_v2": "…", "reason": "…"}
Ворота фазы: init_run.py считает C4.5 готовой, когда в файле есть decision. В REPORT — раздел «Пересмотр идеи»
(report.py). Только стандартная библиотека; сеть не нужна.
"""
import argparse
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
STATUSES = ("confirmed", "refuted", "partial")
KIND_LABELS = {"distinct": "отличие от аналогов", "monetization": "монетизация", "key_feature": "ключевая функция",
               "feasibility": "техническая осуществимость", "audience": "аудитория", "other": "другое"}
DECISIONS = {"keep": "продолжить с исходной идеей", "narrow": "принять сужение", "stop": "остановиться"}


def jload(p, default=None):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def jsave(p, obj):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def answer(cfg, *qids):
    ans = ((cfg.get("idea") or {}).get("answers") or {})
    for q in qids:
        a = ans.get(q)
        if isinstance(a, dict) and a.get("answer"):
            v = a["answer"]
            return ", ".join(map(str, v)) if isinstance(v, list) else str(v)
    return ""


def draft(cfg):
    """Ключевые предпосылки идеи по ответам опроса: что исследование должно подтвердить или опровергнуть."""
    idea = cfg.get("idea") or {}
    fc = idea.get("facets") or {}
    pitch = idea.get("pitch_v2") or idea.get("pitch") or ""
    st = cfg.get("strategy") or {}
    rows = []

    def add(kind, text, key=True):
        rows.append({"id": "PR%d" % (len(rows) + 1), "kind": kind, "key": key, "text": text, "status": None, "evidence": "", "source": None})

    diff = answer(cfg, "c12") or fc.get("differentiator") or ""
    add("distinct", "Идея заметно отличается от существующих аналогов и заменителей%s" % (" (заявлено: %s)" % diff if diff else ""))
    mon = st.get("monetization") or answer(cfg, "c26")
    aud = str((cfg.get("project") or {}).get("audience") or "public")
    if aud in ("personal", "circle"):
        add("monetization", "Личные усилия окупаются: экономия времени, денег или ошибок владельца больше часов на разработку и поддержку")
    else:
        add("monetization", "Пользователи готовы платить по выбранной модели%s, а у конкурентов это не бесплатно" % (" (%s)" % mon if mon else ""))
    feats = [x for x in re.split(r"[,;:]", pitch) if len(x.strip()) > 3][1:4]
    add("key_feature", "Ключевые функции идеи (%s) не даются бесплатно платформой или конкурентами" % ("; ".join(x.strip() for x in feats) or "из идеи"))
    if fc.get("platform_dependency") or fc.get("platform_name"):
        add("feasibility", "Нужные данные и действия платформы %s доступны законным способом (официальный API, открытые данные)"
            % (fc.get("platform_name") or ""))
    else:
        add("feasibility", "MVP технически выполним ресурсами владельца без недоступных данных и интеграций")
    if aud not in ("personal", "circle"):
        add("audience", "Аудиторию можно найти и до неё дойти без большого бюджета", key=False)
    return {"version": 1, "idea_version": int(idea.get("version") or 1), "created": datetime.now().isoformat(timespec="seconds"),
            "pitch": pitch, "premises": rows, "narrowing": None, "decision": None, "decided": None, "by": None, "pitch_v2": None,
            "reason": None}


def evaluate(doc):
    """→ {filled, needs_decision, refuted_key, partial_key, open}."""
    items = [p for p in doc.get("premises") or [] if isinstance(p, dict)]
    open_ = [p["id"] for p in items if p.get("status") not in STATUSES]
    ref = [p for p in items if p.get("key", True) and p.get("status") == "refuted"]
    par = [p for p in items if p.get("key", True) and p.get("status") == "partial"]
    return {"filled": not open_ and bool(items), "open": open_, "refuted_key": [p["id"] for p in ref], "partial_key": [p["id"] for p in par],
            "needs_decision": bool(ref) or len(par) >= 2, "decided": bool(doc.get("decision"))}


def summary(doc):
    lab = {"refuted": "опровергнуто", "partial": "частично", "confirmed": "подтверждено"}
    bad = [p for p in doc.get("premises") or [] if p.get("status") in ("refuted", "partial")]
    return "; ".join("%s — %s" % (p.get("text"), lab[p["status"]]) for p in bad) or "ключевые предпосылки подтверждены"


def question(doc):
    """Карточка AskUserQuestion: исходная — сужение — остановиться (рекомендованный вариант — первым)."""
    ev = evaluate(doc)
    narrow = doc.get("narrowing") or "сузить идею до подтверждённого ядра (что подтвердилось)"
    opts = [{"label": "Принять сужение (Recommended)", "description": narrow[:150]},
            {"label": "Продолжить с исходной", "description": "оставить идею как есть, риски — в отчёт и первые проверки"},
            {"label": "Остановиться", "description": "зафиксировать вывод и закончить прогон на концепции-вердикте"}]
    if not ev["refuted_key"]:
        opts[0]["label"], opts[1]["label"] = "Принять сужение", "Продолжить с исходной (Recommended)"
        opts = [opts[1], opts[0], opts[2]]
    return {"header": "Пересмотр", "multiSelect": False,
            "question": ("Исследование изменило идею: %s. Как продолжаем?" % summary(doc))[:480], "options": opts}


def refresh(out, topic_en=None):
    """Пересобрать досье, затравки, план поиска (новая идея) и светофор."""
    res = []
    dossier = HERE / "concept_dossier.py"
    flag = ["--refresh"] if dossier.exists() and "--refresh" in dossier.read_text(encoding="utf-8", errors="replace") else []
    if topic_en:
        flag += ["--topic-en", topic_en]
    for script, extra in (("concept_dossier.py", flag), ("typesafe_concept.py", [])):
        if not (HERE / script).exists():
            continue
        try:
            r = subprocess.run([sys.executable, "-B", str(HERE / script), str(out)] + extra, capture_output=True, text=True, timeout=300)
            res.append((script, r.returncode, ((r.stdout or "") + (r.stderr or "")).strip().splitlines()[-1:] or [""]))
        except (OSError, subprocess.SubprocessError) as e:
            res.append((script, 1, [str(e)]))
    return res


def decide(out, doc, decision, pitch_v2=None, name=None, ptype=None, forms=None, kind=None, reason=None, by="owner", do_refresh=True,
           topic_en=None):
    cfgp = out / "build" / "run-config.json"
    cfg = jload(cfgp, {}) or {}
    idea = cfg.setdefault("idea", {})
    now = datetime.now().isoformat(timespec="seconds")
    doc.update({"decision": decision, "decided": now, "by": by, "reason": reason})
    changed = []
    if decision == "narrow":
        if not pitch_v2:
            raise ValueError("--decide narrow: нужен --pitch-v2 «идея после сужения»")
        hist = idea.setdefault("history", [])
        hist.append({"version": int(idea.get("version") or 1), "pitch": idea.get("pitch_v2") or idea.get("pitch"), "date": now[:10],
                     "reason": reason or summary(doc), "premises": "data/premises.json"})
        idea["version"] = int(idea.get("version") or 1) + 1
        idea["pitch_v2"] = pitch_v2
        doc["pitch_v2"] = pitch_v2
        changed += ["idea.version", "idea.pitch_v2", "idea.history"]
        if name:
            cfg.setdefault("product", {})["name"] = name
            idea["name"] = name
            changed.append("product.name")
        if ptype:
            cfg.setdefault("product", {})["type"] = ptype
            changed.append("product.type")
        if forms:
            cfg.setdefault("product", {})["forms"] = [x.strip() for x in forms.split(",") if x.strip()]
            changed.append("product.forms")
        if kind:
            idea["kind"] = kind
            changed.append("idea.kind")
        if topic_en and str(topic_en).strip():             # FB-044: перевод темы относится к новой версии идеи
            idea["topic_en"] = str(topic_en).strip()
            idea["topic_en_for"] = idea["version"]
            changed += ["idea.topic_en", "idea.topic_en_for"]
    else:
        idea.setdefault("history", []).append({"version": int(idea.get("version") or 1), "pitch": idea.get("pitch_v2") or idea.get("pitch"),
                                               "date": now[:10], "reason": "пересмотр C4.5: %s" % DECISIONS[decision]})
        changed.append("idea.history")
    jsave(cfgp, cfg)
    jsave(out / "data" / "premises.json", doc)
    sync_idea_json(out, idea)
    ref = refresh(out, idea.get("topic_en") if topic_en else None) if (do_refresh and decision == "narrow") else []
    if ref:
        sync_idea_json(out, idea)                          # досье пересобирает idea.json из run-config — вернуть версию и историю
    return changed, ref


def sync_idea_json(out, idea):
    """data/idea.json: version, pitch_v2, history — как в run-config (источник правды — run-config idea.*)."""
    ij = jload(out / "data" / "idea.json", None)
    if isinstance(ij, dict):
        ij.update({"version": idea.get("version", 1), "pitch_v2": idea.get("pitch_v2"), "history": idea.get("history", [])})
        jsave(out / "data" / "idea.json", ij)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("out")
    ap.add_argument("--init", action="store_true", help="черновик data/premises.json")
    ap.add_argument("--force", action="store_true", help="с --init: перезаписать существующий файл")
    ap.add_argument("--check", action="store_true", help="оценить предпосылки и напечатать вопрос владельцу (по умолчанию)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--decide", choices=sorted(DECISIONS))
    ap.add_argument("--pitch-v2")
    ap.add_argument("--name")
    ap.add_argument("--type", dest="ptype")
    ap.add_argument("--forms")
    ap.add_argument("--kind")
    ap.add_argument("--reason")
    ap.add_argument("--by", default="owner", choices=("owner", "default"))
    ap.add_argument("--no-refresh", action="store_true")
    ap.add_argument("--topic-en", help="--decide narrow: перевод новой темы идеи на английский (idea.topic_en для версии v2)")
    a = ap.parse_args(argv)
    out = Path(a.out).expanduser().resolve()
    cfg = jload(out / "build" / "run-config.json", None)
    if not isinstance(cfg, dict):
        print("ошибка: нет %s/build/run-config.json" % out, file=sys.stderr)
        return 2
    if cfg.get("mode") != "concept":
        print("ошибка: пересмотр идеи — только в режиме идеи (mode: concept)", file=sys.stderr)
        return 2
    pp = out / "data" / "premises.json"
    if a.init or not pp.exists():
        if pp.exists() and not a.force:
            print("data/premises.json уже есть (--force — перезаписать)")
        else:
            doc = draft(cfg)
            jsave(pp, doc)
            print("черновик data/premises.json: %d предпосылок (%s) — заполнить status/evidence/source по research/*.md, затем "
                  "pivot_check.py <OUT> --check" % (len(doc["premises"]), ", ".join(KIND_LABELS[p["kind"]] for p in doc["premises"])))
        if not a.decide:
            return 0
    doc = jload(pp, {}) or {}
    if a.decide:
        try:
            changed, ref = decide(out, doc, a.decide, a.pitch_v2, a.name, a.ptype, a.forms, a.kind, a.reason, a.by, not a.no_refresh,
                                  a.topic_en)
        except ValueError as e:
            print("ошибка: %s" % e, file=sys.stderr)
            return 2
        print("решение записано: %s (%s); изменено: %s" % (DECISIONS[a.decide], a.by, ", ".join(changed)))
        for script, code, tail in ref:
            print("  %s: код %d — %s" % (script, code, tail[0][:160] if tail else ""))
        if a.decide == "narrow" and not a.topic_en:
            print("тема изменилась? перевод для идеи v2 — pivot_check.py <OUT> --decide narrow … --topic-en \"<перевод>\" "
                  "или concept_dossier.py <OUT> --topic-en \"<перевод>\" (иначе в плане поиска останутся <EN: …>)")
        if a.decide == "narrow":
            print("дальше: брифы следующих фаз — render_brief.py … --auto (контекст идеи учтёт сужение); init_run.py <OUT> --done C4.5")
        elif a.decide == "stop":
            print("остановиться: init_run.py <OUT> --status \"C4.5: остановка по решению владельца\"; REPORT — report.py <OUT>")
        return 0
    ev = evaluate(doc)
    res = dict(ev, summary=summary(doc))
    if ev["filled"] and ev["needs_decision"] and not ev["decided"]:
        res["question"] = question(doc)
    if a.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    elif not ev["filled"]:
        print("не заполнены статусы: %s — confirmed / refuted / partial + source" % ", ".join(ev["open"]))
    elif ev["decided"]:
        print("решение уже принято: %s (%s)" % (DECISIONS.get(doc.get("decision"), doc.get("decision")), doc.get("by")))
    elif ev["needs_decision"]:
        print("нужен вопрос владельцу (AskUserQuestion): %s" % json.dumps(res["question"], ensure_ascii=False))
    else:
        print("пересмотр не нужен: %s → pivot_check.py <OUT> --decide keep --by default" % res["summary"])
    if not ev["filled"]:
        return 2
    return 3 if (ev["needs_decision"] and not ev["decided"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
