#!/usr/bin/env python3
"""Сборка design-refs/README.md из карточек design-refs/*.json (и *.md).

  build_design_refs_readme.py <OUT> [--force] [--stdout] [--json]

Содержимое README:
  - таблица карточек: номер, файл, вид, предложения, число зон (hotspots), PNG (есть/нет), кратко;
  - «Как пользоваться» (из встроенного шаблона) и команды перемера зон;
  - общие элементы (`shared` карточек) с перечислением карточек, где они встречаются; одинаковые по смыслу имена
    («Кнопки (ap-btn)» и «кнопки») сводятся в одну строку;
  - открытые вопросы (`questions` всех карточек) по карточкам;
  - порядок постановки задач: карточки по лучшему рангу своих предложений (`dep_rank`, иначе `rank` из data/scores.json;
    нет оценок — по номеру карточки).
Только факты из файлов. Карточка, у которой есть .md, но нет .json (или наоборот), попадает в список проблем.

Справочник общих элементов build/shared-elements.json ({"source", "elements": {имя: описание}}): строится из `shared`
карточки общего дизайн-языка (00-… или `kind: component`; элемент — строка или {"name", "desc"}; описания можно дать
полем `shared_desc` {имя: описание}); описания из прежнего файла сохраняются. Имена `shared` остальных карточек
сверяются со справочником (без учёта регистра, «ё», пояснения в скобках): новые имена — предупреждение в stderr и
раздел README с ближайшим именем из справочника. Нет карточки 00 и файла — справочник не строится.

Защита: если design-refs/README.md уже есть и написан вручную (нет строки «generated-by: build_design_refs_readme.py»),
он не перезаписывается — результат кладётся в design-refs/README.generated.md; --force перезаписывает.
Код выхода: 0 — README записан (при защите — в .generated.md, предупреждение в stderr); 2 — нет папки design-refs/ с карточками.
Только стандартная библиотека.
"""
import argparse
import difflib
import json
import re
import sys
from datetime import date
from pathlib import Path

MARKER = "<!-- generated-by: build_design_refs_readme.py -->"


def load_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default
    except (OSError, json.JSONDecodeError) as e:
        print("предупреждение: не удалось прочитать %s: %s" % (path, e), file=sys.stderr)
        return default


def esc(x, n=None):
    s = "—" if x in (None, "") else str(x)
    s = re.sub(r"(?<!\\)\|", r"\\|", s).replace("\n", " ")
    return s if not n or len(s) <= n else s[:n - 1].rstrip() + "…"


def short(card, n=110):
    title, summ = (card.get("title") or "").strip(), (card.get("summary") or "").strip()
    text = ("%s — %s" % (title, summ)) if title and summ else (title or summ)
    return esc(text, n)


def norm_name(x):
    """«Кнопки (ap-btn)» → «кнопки»: регистр, ё, пояснение в скобках, лишние пробелы и знаки."""
    s = str(x or "").lower().replace("ё", "е")
    s = re.sub(r"\([^)]*\)", " ", s)
    s = re.sub(r"\s*[—–-]\s*(?:см\.\s*)?карточк\w*\s*0+\s*$", " ", s)
    s = re.sub(r"[«»\"'.,:;]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def shared_items(card):
    """shared карточки → [(имя, описание|None)]; элемент — строка или {"name", "desc"|"description"}."""
    out, desc = [], card.get("shared_desc") if isinstance(card.get("shared_desc"), dict) else {}
    for el in card.get("shared") or []:
        if isinstance(el, dict):
            name = el.get("name") or el.get("title")
            if name:
                out.append((str(name), el.get("desc") or el.get("description") or desc.get(name)))
        elif el:
            out.append((str(el), desc.get(str(el))))
    return out


def base_card(cards):
    """Карточка общего дизайн-языка: номер 00 или kind: component."""
    for stem, c in cards:
        if re.match(r"0+(?:\D|$)", stem):
            return stem, c
    for stem, c in cards:
        if str(c.get("kind") or "").lower() == "component":
            return stem, c
    return None, None


def shared_dictionary(out, cards):
    """Справочник имён общих элементов: (dict имя→описание, источник) или (None, None)."""
    path = out / "build" / "shared-elements.json"
    prev = load_json(path, {}) or {}
    elements = dict(prev.get("elements") or {}) if isinstance(prev, dict) else {}
    stem, c = base_card(cards)
    if c is not None:
        known = {norm_name(k): k for k in elements}
        for name, d in shared_items(c):
            k = known.get(norm_name(name))
            if k is None:
                elements[name] = d or ""
                known[norm_name(name)] = name
            elif d and not elements.get(k):
                elements[k] = d
    if not elements:
        return None, None
    return elements, ("design-refs/%s.json" % stem if stem else prev.get("source"))


def best_rank(card, scores):
    """Лучший (наименьший) dep_rank/rank среди предложений карточки → (число, id) или (None, None)."""
    best = (None, None)
    for pid in card.get("proposals") or []:
        s = scores.get(pid) or {}
        v = s.get("dep_rank") if s.get("dep_rank") is not None else s.get("rank")
        if v is not None and (best[0] is None or v < best[0]):
            best = (v, pid)
    return best


def build(out, cards, md_only, json_only, dictionary=None, unknown=None):
    d = out / "design-refs"
    scores_l = load_json(out / "data" / "scores.json", None)
    scores = {s["id"]: s for s in scores_l if isinstance(s, dict) and s.get("id")} if isinstance(scores_l, list) else {}
    L = [MARKER, "# Карточки референсов (design-refs)", "",
         "Карточка на каждый макет-концепт: по ней можно ставить задачи на интерфейс, не читая стратегию. Каждый макет несёт бейдж "
         "«Концепт, не существующая функция». Файл собран `build_design_refs_readme.py` %s из `design-refs/*.json`." % date.today().isoformat(), ""]
    L += ["## Карточки", ""]
    head = ["№", "Файл", "Вид", "Предложения", "Зон", "PNG", "Кратко"]
    L += ["| " + " | ".join(head) + " |", "|" + "|".join("---" for _ in head) + "|"]
    for stem, c in cards:
        m = re.match(r"(\d+)", stem)
        png = c.get("png") or "design-refs/%s.png" % stem
        has_png = (out / png).exists() or (d / (stem + ".png")).exists()
        L.append("| %s | `%s` | %s | %s | %s | %s | %s |" % (
            m.group(1) if m else "—", stem, esc(c.get("kind")), esc(", ".join(c.get("proposals") or [])),
            len(c.get("hotspots") or []), "есть" if has_png else "нет", short(c)))
    L.append("")
    if md_only or json_only:
        L += ["**Не хватает пары файлов:**", ""]
        L += ["- `%s.md` без `%s.json`" % (s, s) for s in md_only] + ["- `%s.json` без `%s.md`" % (s, s) for s in json_only] + [""]
    L += ["## Как пользоваться", "",
          "1. Откройте PNG карточки (зоны пронумерованы) и рядом её `.md`: «Что это», «Как выглядит», «Как взаимодействовать».",
          "2. Раздел «Что нужно доделать» карточки — готовый список задач: один пункт = одна задача, переносится в трекер как есть.",
          "3. Нумерация элементов в `.md` совпадает с `hotspots[].n` в `.json`; поле `proposals` связывает карточку с реестром.",
          "4. Макеты — концепты, а не существующие функции; перед постановкой задачи прочитайте «Открытые вопросы» карточки.",
          "5. Координаты зон — CSS-пиксели исходного размера (`scale: 2` у мобильных), от левого верхнего угла всего PNG; у раскадровок "
          "(несколько экранов в одном PNG) поле `screen` — номер кадра; у длинных страниц (`full_page: true`) — от начала страницы.", "",
          "Как перемерить зоны после правки макета:", "",
          "```", "PS_NODE_DIR=<OUT>/build/node node <SKILL_DIR>/scripts/node/measure_hotspots.mjs <OUT> design-refs/NN-slug.json --spec <spec.json> [--full-page]", "```",
          "Затем `node <SKILL_DIR>/scripts/node/shoot_mockups.mjs <OUT> --only <ключ>` для нового PNG и копия PNG в `design-refs/`.", ""]
    # общие элементы: одинаковые по смыслу имена — одна строка; имя — из справочника, если есть
    canon = {norm_name(k): k for k in (dictionary or {})}
    shared, names = {}, {}
    for stem, c in cards:
        for el, _ in shared_items(c):
            k = norm_name(el)
            names.setdefault(k, canon.get(k) or el)
            if stem not in shared.setdefault(k, []):
                shared[k].append(stem)
    L += ["## Общие элементы", ""]
    if dictionary:
        L += ["Имена — из справочника `build/shared-elements.json` (%d элементов, источник — карточка общего дизайн-языка)." % len(dictionary), ""]
    if shared:
        L += ["| Элемент | Описание | Карточки |", "|---|---|---|"] + [
            "| %s | %s | %s |" % (esc(names[k]), esc((dictionary or {}).get(canon.get(k, ""), "") or None, 90), esc(", ".join("`%s`" % s for s in v)))
            for k, v in sorted(shared.items(), key=lambda kv: names[kv[0]].lower())]
    else:
        L.append("_нет данных_: ни в одной карточке не заполнено поле `shared`.")
    L.append("")
    if unknown:
        L += ["**Имена не из справочника** (переименуйте в имя из справочника или добавьте элемент в карточку 00):", ""]
        L += ["- `%s`: «%s»%s" % (stem, esc(n), " — похоже на «%s»" % esc(sug) if sug else "") for stem, n, sug in unknown] + [""]
    # открытые вопросы
    L += ["## Открытые вопросы", ""]
    any_q = False
    for stem, c in cards:
        qs = c.get("questions") or []
        if qs:
            any_q = True
            L += ["**`%s`** — %s" % (stem, esc(c.get("title"))), ""] + ["- %s" % q for q in qs] + [""]
    if not any_q:
        L += ["_нет данных_: ни в одной карточке нет открытых вопросов (`questions`).", ""]
    # порядок
    L += ["## Порядок постановки задач", ""]
    ranked = [(best_rank(c, scores), stem, c) for stem, c in cards]
    if scores and any(r[0][0] is not None for r in ranked):
        ranked.sort(key=lambda t: (t[0][0] is None, t[0][0] if t[0][0] is not None else 0, t[1]))
        L.append("По лучшему рангу предложений карточки (%s из data/scores.json): сначала карточки с самыми приоритетными предложениями." %
                 ("dep_rank, где есть, иначе rank" if any(s.get("dep_rank") is not None for s in scores.values()) else "rank"))
        L.append("")
        L += ["| Очередь | Карточка | Лучшее предложение | Ранг |", "|---|---|---|---|"]
        for i, ((r, pid), stem, c) in enumerate(ranked, 1):
            L.append("| %d | `%s` | %s | %s |" % (i, stem, esc(pid), esc(r)))
    else:
        L.append("_нет данных_ о рангах предложений (нет data/scores.json) — порядок по номеру карточки:")
        L.append("")
        L += ["%d. `%s` — %s" % (i, stem, esc(c.get("title"))) for i, (stem, c) in enumerate(cards, 1)]
    L.append("")
    return "\n".join(L).rstrip() + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0], formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out", help="папка прогона <OUT>")
    ap.add_argument("--force", action="store_true", help="перезаписать design-refs/README.md, даже если он написан вручную")
    ap.add_argument("--stdout", action="store_true", help="напечатать текст, файл не писать")
    ap.add_argument("--json", action="store_true", help="печатать краткий отчёт JSON")
    a = ap.parse_args(argv)
    out = Path(a.out).resolve()
    d = out / "design-refs"
    jsons = sorted(f for f in d.glob("*.json")) if d.is_dir() else []
    mds = {f.stem for f in d.glob("*.md") if f.name.lower() != "readme.md" and not f.name.lower().startswith("readme.")} if d.is_dir() else set()
    if not jsons and not mds:
        print("ошибка: в %s нет карточек (*.json, *.md)" % d, file=sys.stderr)
        return 2
    cards, json_only = [], []
    for f in jsons:
        c = load_json(f, None)
        if not isinstance(c, dict) or not ({"file", "hotspots", "title"} & set(c)):
            print("предупреждение: %s не похож на карточку (нет file/hotspots/title), пропущен" % f.name, file=sys.stderr)
            continue
        cards.append((f.stem, c))
        if f.stem not in mds:
            json_only.append(f.stem)
    md_only = sorted(mds - {s for s, _ in cards})
    cards.sort(key=lambda t: t[0])
    dictionary, source = shared_dictionary(out, cards)
    unknown = []
    if dictionary:
        canon = {norm_name(k): k for k in dictionary}
        base_stem = base_card(cards)[0]
        for stem, c in cards:
            if stem == base_stem:
                continue
            for name, _ in shared_items(c):
                if norm_name(name) not in canon:
                    near = difflib.get_close_matches(norm_name(name), list(canon), n=1, cutoff=0.5)
                    unknown.append((stem, name, canon[near[0]] if near else None))
    text = build(out, cards, md_only, json_only, dictionary, unknown)
    if dictionary and not a.stdout:
        dpath = out / "build" / "shared-elements.json"
        dpath.parent.mkdir(parents=True, exist_ok=True)
        dpath.write_text(json.dumps({"source": source, "generated_by": "build_design_refs_readme.py", "elements": dictionary},
                                    ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for stem, n, sug in unknown:
        print("предупреждение: %s: общий элемент «%s» не из справочника build/shared-elements.json%s" % (
            stem, n, " (похоже на «%s»)" % sug if sug else ""), file=sys.stderr)
    if a.stdout:
        sys.stdout.write(text)
        return 0
    target = d / "README.md"
    protected = target.exists() and not a.force and MARKER not in target.read_text(encoding="utf-8")
    if protected:
        target = d / "README.generated.md"
    target.write_text(text, encoding="utf-8")
    rep = {"ok": True, "file": target.relative_to(out).as_posix(), "protected": protected, "cards": len(cards), "md_without_json": md_only, "json_without_md": json_only,
           "shared_dictionary": "build/shared-elements.json" if dictionary else None, "shared_elements": len(dictionary or {}),
           "shared_unknown": [{"card": s_, "name": n, "suggest": g} for s_, n, g in unknown]}
    if a.json:
        print(json.dumps(rep, ensure_ascii=False, indent=2))
    else:
        print("записано %s: карточек %d%s" % (target, len(cards), "; без пары: %s" % ", ".join(md_only + json_only) if md_only or json_only else ""))
        if protected:
            print("предупреждение: design-refs/README.md написан вручную и не перезаписан; сравните и перенесите нужное или запустите с --force", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
