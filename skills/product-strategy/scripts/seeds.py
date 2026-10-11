#!/usr/bin/env python3
"""Затравки реестра для фазы 3 (обычный и внешний продукт) → <OUT>/build/seeds.md.

  seeds.py <OUT> [--type saas|consumer|devtool|oss|content|game|bot|mobile|desktop|other] [--force] [--stdout]

Фильтр references/growth-library.md по типу продукта (run-config product.type; --type главнее) и профилю (SOL-* для
zero-budget-solo), затем ранжирование внутри категорий по сигналам применимости: слова из «Сигнал применимости» и
«Что» ищутся в research/product-understanding.md, research/ui-inventory.md, research/app-scan.md,
research/store-stats.md, research/issues-demand.md (что есть на диске). Совпавшие слова пишутся в колонку «Сигнал
найден» — это подсказка генератору реестра, а не доказательство.

Тип продукта: auto/other уточняется по данным — APK (data/app-scan.json), карточки магазинов (data/store-stats.json,
sources.stores) → mobile. Если тип не ясен — затравки только с меткой «все» и вопрос в stdout (код 3): уточнить у
владельца (intake.py update <OUT> --set product.type=…). Режим идеи — затравки пишет concept_dossier.py (здесь —
отказ без --force). Ручной build/seeds.md (без маркера) не затирается: пишется build/seeds.generated.md.
Только стандартная библиотека.
"""
import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import concept_dossier as cd  # noqa: E402 — разбор библиотеки и фильтр по типу — общие с режимом идеи

MARKER = "<!-- generated-by: seeds.py -->"
TYPES = ("saas", "consumer", "devtool", "oss", "content", "game", "bot", "mobile", "desktop", "other")
SIGNAL_FILES = ("research/product-understanding.md", "research/ui-inventory.md", "research/app-scan.md", "research/store-stats.md",
                "research/issues-demand.md", "research/repo-scan.md")
STOP = {"который", "которые", "когда", "через", "чтобы", "этого", "много", "нужно", "можно", "только", "уже", "есть", "нет", "без",
        "для", "или", "при", "под", "над", "это", "так", "как", "что", "все", "всех", "свой", "свои", "своих", "другие", "другой",
        "вместо", "после", "перед", "между", "более", "менее", "очень", "также", "такие", "своей", "своего", "where", "which", "their"}


def jload(p, default=None):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def stems(text):
    """Значимые основы слов (первые 5 букв слов длиной ≥ 5, без стоп-слов)."""
    out = set()
    for w in re.findall(r"[A-Za-zА-Яа-яЁё][A-Za-zА-Яа-яЁё-]{3,}", str(text).lower()):
        if w in STOP or len(w) < 5:
            continue
        out.add(w[:5])
    return out


def resolve_type(out, cfg, forced=None):
    """→ (тип, причина, уверенно ли)."""
    if forced:
        return forced, "--type", True
    t = ((cfg.get("product") or {}).get("type") or "auto")
    if t not in ("auto", "other", ""):
        return t, "run-config product.type", True
    app = jload(out / "data" / "app-scan.json", {}) or {}
    st = jload(out / "data" / "store-stats.json", {}) or {}
    src = cfg.get("sources") or {}
    if app.get("apps"):
        return "mobile", "data/app-scan.json: есть разобранный APK", True
    if any(s.get("status") == "ok" for s in st.get("stores") or []) or src.get("stores") or (src.get("external") or {}).get("stores"):
        return "mobile", "карточки магазинов приложений", True
    return "other", "тип не определён (нет APK, магазинов и манифестов)", False


def build(out, cfg, ptype, sure):
    lib = HERE.parent / "references" / "growth-library.md"
    rows = cd.parse_library(lib)
    solo = (cfg.get("strategy") or {}).get("profile") == "zero-budget-solo"
    external = (cfg.get("product") or {}).get("mode") == "external"
    corpus, used = "", []
    for rel in SIGNAL_FILES:
        p = out / rel
        if p.is_file():
            corpus += "\n" + p.read_text(encoding="utf-8", errors="replace")
            used.append(rel)
    cs = stems(corpus)
    by_cat = {}
    for cat, sid, what, signal, kpi, types in rows:
        if cat == "SOL":
            if not solo or not cd.type_match(types, ptype):
                continue
            m = re.match(r"\[(\w+)\]\s*(.*)", what)
            cat, what = (m.group(1), m.group(2)) if m else ("platform", what)
        elif not cd.type_match(types, ptype):
            continue
        hit = sorted(stems(signal + " " + what) & cs)
        note = ""
        if external and re.search(r"Issues|репозитор|в коде|кода\b|PR\b", signal + what):
            note = " (внешний продукт: сигнал про код/Issues проверять по отзывам, трекеру и APK)"
        by_cat.setdefault(cat, []).append((len(hit), sid, what, signal + note, kpi, hit[:6]))
    order = ["product", "acquisition", "conversion", "retention", "monetization", "analytics", "partnerships", "localization", "new_lines", "platform"]
    total = sum(len(v) for v in by_cat.values())
    with_signal = sum(1 for v in by_cat.values() for x in v if x[0])
    name = (cfg.get("product") or {}).get("name") or out.name
    L = [MARKER, "# Затравки реестра: %s" % name, "",
         "Отфильтровано `seeds.py` из `references/growth-library.md` по типу `%s`%s%s. Всего: %d, с найденным сигналом в "
         "материалах фаз 1–3: %d. Источники сигналов: %s. Это гипотезы для адаптации, а не готовые предложения; «Сигнал "
         "найден» — совпавшие основы слов (подсказка, не доказательство)." % (
             ptype, "" if sure else " [тип не уверен — уточнить у владельца]", " + SOL-* (профиль zero-budget-solo)" if solo else "",
             total, with_signal, ", ".join("`%s`" % u for u in used) or "нет (материалов фаз 1–3 ещё нет — сортировка по библиотеке)"), ""]
    if external:
        L += ["Внешний продукт (кода нет): затравки про код, репозиторий и Issues превращаются в проверку по APK (`data/app-scan.json`), "
              "отзывам и карточкам (`data/store-stats.json`) и трекеру; доступ к консолям и аналитике владельца — вопрос заказчику.", ""]
    for cat in order + sorted(c for c in by_cat if c not in order):
        items = sorted(by_cat.get(cat) or [], key=lambda x: (-x[0], x[1]))
        if not items:
            continue
        L += ["## %s (%d)" % (cat, len(items)), "", "| ID | Что | Сигнал применимости | KPI | Сигнал найден |", "|---|---|---|---|---|"]
        L += ["| %s | %s | %s | %s | %s |" % (sid, cd.cell(w, 220), cd.cell(s, 220), cd.cell(k, 120), ", ".join(h) or "—")
              for _n, sid, w, s, k, h in items] + [""]
    if not total:
        L += ["_Библиотека не найдена или пуста — затравки подобрать вручную._", ""]
    return "\n".join(L).rstrip() + "\n", total, with_signal


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("out")
    ap.add_argument("--type", choices=TYPES)
    ap.add_argument("--force", action="store_true", help="перезаписать ручной build/seeds.md; в режиме идеи — всё равно собрать")
    ap.add_argument("--stdout", action="store_true")
    a = ap.parse_args(argv)
    out = Path(a.out).expanduser().resolve()
    cfg = jload(out / "build" / "run-config.json", {}) or {}
    if cfg.get("mode") == "concept" and not a.force:
        print("seeds.py: режим идеи — build/seeds.md пишет concept_dossier.py (собрать здесь — --force)")
        return 0
    ptype, why, sure = resolve_type(out, cfg, a.type)
    text, total, with_signal = build(out, cfg, ptype, sure)
    if a.stdout:
        print(text)
    else:
        path = out / "build" / "seeds.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and not a.force and MARKER not in path.read_text(encoding="utf-8", errors="replace"):
            path = path.with_name("seeds.generated.md")
        path.write_text(text, encoding="utf-8")
        print("seeds.py: тип %s (%s), затравок %d, с сигналом %d → %s" % (ptype, why, total, with_signal, path))
    if not sure:
        print("Вопрос владельцу: какой это продукт — saas, consumer, content, bot, mobile, desktop, devtool, game, oss? "
              "Ответ — intake.py update %s --set product.type=<тип>, затем seeds.py заново" % out)
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
