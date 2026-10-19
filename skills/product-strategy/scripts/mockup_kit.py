#!/usr/bin/env python3
"""Набор макетов и дизайн-этап прогона: копирование набора, M00, замок набора, выбор направления, галерея вариантов.

  mockup_kit.py init <OUT> [--forms web,mobile|mobile-later] [--modes a,b] [--force] [--json]
  mockup_kit.py verify <OUT> [--update] [--json]
  mockup_kit.py directions <OUT> [--json]
  mockup_kit.py choose <OUT> (--direction <id|название> | --recommended) [--by owner|default]
  mockup_kit.py gate <OUT> --steps 1|2-3|1-3
  mockup_kit.py gallery <OUT> [--min 2] [--title …] [--json]
  mockup_kit.py params <OUT> [--json]

init — однократно и идемпотентно, ДО волны макетов (оркестратор; агенты набор не копируют): копирует набор
  templates/mockup-kit/ в <OUT>/mockups/concepts/ (_kit.css, _icons.css, _base.html, _kit-demo.html, _hotspots.js; для
  форм mobile / mobile-later — ещё _mobile.css, _base-mobile.html, _storyboard.html, _kit-demo-mobile.html), создаёт
  M00-design-language.html — демо всех форм продукта (веб и мобильный — на одной странице, data-kind="kit"), пустой
  mockups/tokens.css, если его нет (токены пишет агент дизайна), mockups/tokens-<режим>.css для --modes (если файла нет)
  и build/kit.lock (sha256 файлов набора). Повторный запуск ничего не меняет; новые формы — докопирует; файл набора,
  изменённый после init, не перезаписывается без --force (оркестратор мог осознанно исправить баг).
  Формы по умолчанию — из run-config: design.forms → product.type (mobile → mobile, иначе web) + design.mobile_reserve
  (→ mobile-later: спутниковая серия «мобильный задел»); режимы — design.modes.
verify — файлы набора и M00 совпадают с build/kit.lock (агенты макетов не меняли набор): код 1 и список изменённых
  или пропавших файлов; --update — принять текущие файлы как новый эталон (после осознанной правки набора).
directions — направления из design/directions.md (заголовки «## Направление A — «Название»», раздел «## Рекомендация»):
  рекомендованное первым — готовые варианты для вопроса владельцу (AskUserQuestion) на чекпоинте C8-ask.
choose — записать выбор в build/run-config.json → design.chosen, design.chosen_name, design.chosen_by (owner | default),
  design.chosen_at; --recommended — рекомендованное из directions.md (автопилот: --by default).
gate — можно ли рендерить шаги 2–3 брифа concept-design: вне автопилота без design.chosen — код 3 и причина
  (функция design_gate(cfg, steps) — для render_brief.py).
gallery — <OUT>/mockups/gallery.html из шаблона templates/mockup-kit/gallery.html: варианты по атрибуту data-variant /
  <meta name="ps:variant"> макетов, по 2–3 рабочих экрана на вариант, таблица «один сценарий в N стилях» по
  data-screen-id / ps:screen, отклонённые варианты (data-variant-status="rejected") — в конце. Предупреждение, если у
  варианта меньше --min экранов. Ссылки «с подсказками» добавляет _hotspots.js.
params — параметры дизайн-этапа из run-config (directions_count, modes, chosen, chosen_by, pointer_first, forms) для брифов.

Код выхода: 0 — готово; 1 — замечания (verify: набор изменён; gallery: варианты не размечены или экранов меньше --min);
2 — ошибка аргументов/файлов; 3 — gate: шаги 2–3 закрыты до выбора направления. Только стандартная библиотека.
"""
import argparse
import hashlib
import html as htmlmod
import json
import os
import re
import sys
import time
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent
KIT = SKILL / "templates" / "mockup-kit"
KIT_VERSION = "1.3"
BADGE_TEXT = "Концепт, не существующая функция"          # одна константа текста бейджа (README набора)

COMMON = [("_kit.css", "_kit.css"), ("_icons.css", "_icons.css"), ("_base.html", "_base.html"),
          ("kit-demo.html", "_kit-demo.html"), ("_hotspots.js", "_hotspots.js")]
MOBILE = [("mobile/_mobile.css", "_mobile.css"), ("mobile/_base-mobile.html", "_base-mobile.html"),
          ("mobile/_storyboard.html", "_storyboard.html"), ("mobile/kit-demo-mobile.html", "_kit-demo-mobile.html")]
FORMS = ("web", "mobile", "mobile-later")
M00 = "M00-design-language.html"


# ---------------------------------------------------------------- общие функции
def load_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default
    except (OSError, ValueError) as e:
        print("предупреждение: не удалось прочитать %s: %s" % (path, e), file=sys.stderr)
        return default


def dump_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".%d.tmp" % os.getpid())
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run_config(out):
    cfg = load_json(Path(out) / "build" / "run-config.json", {})
    return cfg if isinstance(cfg, dict) else {}


def product_name(cfg):
    for keys in (("idea", "name"), ("product", "name")):
        v = cfg
        for k in keys:
            v = v.get(k) if isinstance(v, dict) else None
        if v:
            return str(v)
    return "Продукт"


class Lock:
    """Замок на время init (два одновременных вызова не копируют набор параллельно)."""

    def __init__(self, path, timeout=30):
        self.path, self.timeout = Path(path), timeout

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        t0 = time.time()
        while True:
            try:
                fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, str(os.getpid()).encode())
                os.close(fd)
                return self
            except FileExistsError:
                try:
                    if time.time() - self.path.stat().st_mtime > 60:
                        self.path.unlink()
                        continue
                except FileNotFoundError:
                    continue
                if time.time() - t0 > self.timeout:
                    raise SystemExit("ошибка: не дождались замка %s" % self.path)
                time.sleep(0.05)

    def __exit__(self, *exc):
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass


# ---------------------------------------------------------------- метаданные макета (как в shoot_mockups.mjs)
ATTR_RE = r"\b%s\s*=\s*([\"'])(.*?)\1"
ID_RE = re.compile(r"^(P\d{3,}|G\d+-\d{2,})$")


def html_meta(path):
    """Атрибуты <html>/<body> и <meta name="ps:…"> макета: viewport, title, proposals, kind, links, variant, screen…"""
    try:
        src = Path(path).read_text(encoding="utf-8", errors="replace")[:200000]
    except OSError:
        return {}

    def tag(name):
        m = re.search(r"<%s\b[^>]*>" % name, src, re.I)
        return m.group(0) if m else ""

    def attr(t, a):
        m = re.search(ATTR_RE % re.escape(a), t, re.I | re.S)
        return htmlmod.unescape(m.group(2).strip()) if m else None

    meta = {}
    for m in re.finditer(r"<meta\b[^>]*>", src, re.I):
        name, content = attr(m.group(0), "name"), attr(m.group(0), "content")
        if name and name.lower().startswith("ps:") and content is not None:
            meta[name[3:].lower()] = content
    h, b = tag("html"), tag("body")

    def get(a, k):
        return attr(h, a) or attr(b, a) or meta.get(k) or None

    vp_raw = get("data-viewport", "viewport")
    viewport = "1440x900"
    if vp_raw and re.fullmatch(r"\d{2,5}x\d{2,5}", vp_raw):
        viewport = vp_raw
    elif vp_raw and re.search(r"mobile|phone|390", vp_raw, re.I):
        viewport = "390x844"
    tm = re.search(r"<title[^>]*>([^<]*)</title>", src, re.I)
    title = re.sub(r"\s+", " ", meta.get("title") or (htmlmod.unescape(tm.group(1)) if tm else "")).strip()
    props = [x.strip() for x in re.split(r"[,\s]+", get("data-proposals", "proposals") or "") if ID_RE.match(x.strip())]
    kind_raw = (get("data-kind", "kind") or "").lower()
    kind = "component" if kind_raw == "kit" else kind_raw if kind_raw in ("concept", "component", "current") else "concept"
    res = {"viewport": viewport, "title": title, "proposals": props, "kind": kind,
           "variant": get("data-variant", "variant") or "", "screen": get("data-screen-id", "screen") or "",
           "variant_note": get("data-variant-note", "variant-note") or "",
           "variant_status": (get("data-variant-status", "variant-status") or "").lower(), "mode": get("data-mode", "mode") or ""}
    links = (get("data-links", "links") or "").lower()
    if re.fullmatch(r"false|no|0|нет", links):
        res["links"] = False
    return res


def concept_files(out):
    d = Path(out) / "mockups" / "concepts"
    return sorted(p for p in d.glob("*.htm*") if not p.name.startswith("_")) if d.is_dir() else []


# ---------------------------------------------------------------- init / verify
TR = dict(zip("абвгдеёжзийклмнопрстуфхцчшщъыьэюя", ["a", "b", "v", "g", "d", "e", "e", "zh", "z", "i", "y", "k", "l", "m", "n", "o", "p",
         "r", "s", "t", "u", "f", "kh", "ts", "ch", "sh", "sch", "", "y", "", "e", "yu", "ya"]))


def translit(s):
    return "".join(TR.get(ch, ch) for ch in s)


def wanted_forms(cfg, arg):
    if arg:
        forms = [f.strip() for f in arg.split(",") if f.strip()]
    else:
        d = cfg.get("design") if isinstance(cfg.get("design"), dict) else {}
        forms = d.get("forms") or []
        if isinstance(forms, str):
            forms = [x.strip() for x in forms.split(",") if x.strip()]
        prod = cfg.get("product") if isinstance(cfg.get("product"), dict) else {}
        pf = [str(x) for x in (prod.get("forms") or []) if x]
        if not forms and pf:
            forms = ["mobile" if x == "mobile" else "web" for x in pf if x in ("web", "mobile_web", "pwa", "saas", "mobile", "desktop")]
            if any(x == "mobile" for x in pf) and "web" in forms:
                forms = [x for x in forms if x != "mobile"] + ["mobile"]
        if prod.get("future_forms") and "mobile" not in forms and "mobile-later" not in forms:
            if any(str(x) in ("mobile", "mobile_web", "ios", "android", "app") for x in prod["future_forms"]):
                forms.append("mobile-later")
        if not forms:
            ptype = str((cfg.get("product") or {}).get("type") or "").lower()
            forms = ["mobile"] if ptype == "mobile" else ["web"]
            if d.get("mobile_reserve") and "mobile" not in forms:
                forms.append("mobile-later")
    bad = [f for f in forms if f not in FORMS]
    if bad:
        raise SystemExit("ошибка: --forms: неизвестные формы %s (допустимо: %s)" % (", ".join(bad), ", ".join(FORMS)))
    return list(dict.fromkeys(forms))


def wanted_modes(cfg, arg):
    if arg is not None:
        modes = [m.strip() for m in arg.split(",") if m.strip()]
    else:
        d = cfg.get("design") if isinstance(cfg.get("design"), dict) else {}
        modes = d.get("modes") or []
        if isinstance(modes, str):
            modes = [m.strip() for m in modes.split(",") if m.strip()]
        modes = [m.get("id") or m.get("name") if isinstance(m, dict) else m for m in modes]
    out = []
    for m in modes:
        slug = re.sub(r"[^a-z0-9-]+", "-", translit(str(m).lower())).strip("-")
        if slug and slug not in out:
            out.append(slug)
    return out


def _between(text, start_re, end_re):
    m = re.search(start_re, text, re.S)
    if not m:
        return ""
    e = re.search(end_re, text[m.end():], re.S)
    return text[m.start(): m.end() + (e.end() if e else len(text) - m.end())]


def _split_script(text):
    """Скрипт демо → (часть вставки шаблонов, часть проверки контраста)."""
    m = re.search(r"<script>(.*?)</script>", text, re.S)
    body = m.group(1) if m else ""
    i = body.find("// Автопроверка контраста")
    return (body[:i], body[i:]) if i >= 0 else (body, "")


def build_m00(forms, product, today):
    """M00 — демо всех форм продукта на одной странице (веб: kit-demo.html, мобильный: kit-demo-mobile.html)."""
    web = (KIT / "kit-demo.html").read_text(encoding="utf-8")
    mob = (KIT / "mobile" / "kit-demo-mobile.html").read_text(encoding="utf-8")
    has_web = "web" in forms
    has_mob = any(f in forms for f in ("mobile", "mobile-later"))
    styles, bodies, scripts, contrast = [], [], [], ""
    if has_web:
        styles.append(re.search(r"<style>(.*?)</style>", web, re.S).group(1))
        b = web.split("<body>", 1)[1].split("<script>", 1)[0]
        bodies.append(b)
        clone, contrast = _split_script(web)
        scripts.append(clone)
    if has_mob:
        styles.append(re.search(r"<style>(.*?)</style>", mob, re.S).group(1))
        b = mob.split("<body>", 1)[1].split("<script>", 1)[0]
        clone, c2 = _split_script(mob)
        if has_web:                               # слоты мобильного демо — свои имена, иначе веб-скрипт заполнит их своим шаблоном
            b = b.replace('class="kd-slot"', 'class="kd-mslot"')
            clone = clone.replace("'.kd-slot'", "'.kd-mslot'")
        else:
            contrast = c2
        title = ('<section class="kd-theme" data-theme="light"><h2>Мобильный слой%s</h2></section>' %
                 (" — задел на будущее (mobile-later)" if "mobile-later" in forms and "mobile" not in forms else ""))
        bodies.append(title + b)
        scripts.append(clone)
    badge = "%s · %s · %s" % (BADGE_TEXT, product, today)
    body = "\n".join(bodies)
    body = re.sub(r'(<div class="ps-concept-badge is-inline">)[^<]*(</div>)', lambda m: m.group(1) + htmlmod.escape(badge) + m.group(2), body, count=1)
    if 'ps-concept-badge is-inline' not in body:
        body = '<div class="ps-concept-badge is-inline">%s</div>\n' % htmlmod.escape(badge) + body
    vp = "1440x900" if has_web else "2120x1000"
    vps = "1440x900,390x844" if has_web else "2120x1000,390x844"
    links = ['<link rel="stylesheet" href="../tokens.css">', '<link rel="stylesheet" href="_kit.css">', '<link rel="stylesheet" href="_icons.css">']
    if has_mob:
        links.append('<link rel="stylesheet" href="_mobile.css">')
    return ("<!doctype html>\n<!-- M00 — общий дизайн-язык: все компоненты набора для форм продукта (%s). Создал mockup_kit.py init;\n"
            "     не править вручную (build/kit.lock). Карточка design-refs 00 ссылается на этот файл (kind: component). -->\n"
            '<html lang="ru" data-viewport="%s" data-viewports="%s" data-kind="kit" data-links="false">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width,initial-scale=1">\n<title>M00 — общий дизайн-язык (%s)</title>\n%s\n'
            "<style>%s</style>\n</head>\n<body>\n%s\n<script>%s\n%s</script>\n</body>\n</html>\n") % (
        ", ".join(forms), vp, vps, htmlmod.escape(product), "\n".join(links), "\n".join(styles), body, "\n".join(scripts), contrast)


def cmd_init(a):
    out = Path(a.out).resolve()
    if not out.is_dir():
        print("ошибка: нет папки %s" % out, file=sys.stderr)
        return 2
    cfg = run_config(out)
    lock_path = out / "build" / "kit.lock"
    prev = load_json(lock_path, {}) or {}
    forms = wanted_forms(cfg, a.forms)
    if not a.forms and prev.get("forms"):                 # повторный запуск без --forms — формы прежние (+ новые из run-config)
        forms = list(dict.fromkeys(list(prev["forms"]) + forms))
    modes = wanted_modes(cfg, a.modes)
    if a.modes is None and prev.get("modes"):
        modes = list(dict.fromkeys(list(prev["modes"]) + modes))
    concepts = out / "mockups" / "concepts"
    report = {"forms": forms, "modes": modes, "copied": [], "kept": [], "skipped_modified": [], "created": [], "warnings": []}
    with Lock(out / "build" / ".kit-init.lock"):
        lock = load_json(lock_path, {}) or {}
        files = dict(lock.get("files") or {})
        pairs = list(COMMON) + (list(MOBILE) if any(f in forms for f in ("mobile", "mobile-later")) else [])
        concepts.mkdir(parents=True, exist_ok=True)
        for src_rel, dst_name in pairs:
            src, dst = KIT / src_rel, concepts / dst_name
            rel = "mockups/concepts/" + dst_name
            data = src.read_bytes()
            if dst.exists():
                cur = sha(dst)
                if cur == hashlib.sha256(data).hexdigest():
                    files[rel] = cur
                    report["kept"].append(rel)
                    continue
                if not a.force and (rel not in files or files[rel] != cur):
                    # изменён после init (или лежал до init) — не затираем без --force
                    report["skipped_modified"].append(rel)
                    files.setdefault(rel, cur)
                    continue
                if not a.force and files.get(rel) == cur:
                    report["kept"].append(rel)          # совпадает с замком: шаблон новее, но обновляем только с --force
                    continue
            dst.write_bytes(data)
            files[rel] = sha(dst)
            report["copied"].append(rel)
        # M00 — демо всех форм продукта
        m00, rel00 = concepts / M00, "mockups/concepts/" + M00
        old_forms = lock.get("forms") or []
        need = not m00.exists() or sorted(old_forms) != sorted(forms) or a.force
        if m00.exists() and need and not a.force and rel00 in files and sha(m00) != files[rel00]:
            report["skipped_modified"].append(rel00)
            need = False
        if need:
            m00.write_text(build_m00(forms, product_name(cfg), date.today().isoformat()), encoding="utf-8")
            report["created"].append(rel00)
        if m00.exists():
            files[rel00] = sha(m00)
        tokens = out / "mockups" / "tokens.css"
        if not tokens.exists():
            tokens.write_text("/* Токены продукта ещё не записаны (шаг 2 брифа concept-design.md / audit_site.mjs). Пока набор рисует\n"
                              "   запасной палитрой; shoot_mockups.mjs предупредит об этом. */\n", encoding="utf-8")
            report["created"].append("mockups/tokens.css")
        tpl = (KIT / "tokens-mode.css").read_text(encoding="utf-8")
        for m in modes:
            p = out / "mockups" / ("tokens-%s.css" % m)
            if not p.exists():
                p.write_text(tpl.replace("{{MODE}}", m), encoding="utf-8")
                report["created"].append("mockups/tokens-%s.css" % m)
        new_lock = {"version": KIT_VERSION, "created": lock.get("created") or date.today().isoformat(), "updated": date.today().isoformat(),
                    "forms": forms, "modes": modes, "files": dict(sorted(files.items())),
                    "note": "набор скопирован mockup_kit.py init — агенты макетов его не копируют и не меняют (mockup_kit.py verify)"}
        if new_lock != lock:
            dump_json(lock_path, new_lock)
    for rel in report["skipped_modified"]:
        report["warnings"].append("%s изменён после init — не перезаписан (--force — заменить шаблоном набора)" % rel)
    changed = report["copied"] or report["created"]
    if a.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print("набор макетов %s → mockups/concepts/ (формы: %s%s): скопировано %d, без изменений %d%s" % (
            KIT_VERSION, ", ".join(forms), "; режимы: " + ", ".join(modes) if modes else "", len(report["copied"]), len(report["kept"]),
            "; создано: " + ", ".join(report["created"]) if report["created"] else ""))
        if not changed:
            print("набор уже скопирован — повторный запуск ничего не изменил")
        for w in report["warnings"]:
            print("предупреждение: " + w)
        print("замок: build/kit.lock; проверка после волны макетов — mockup_kit.py verify %s" % a.out)
    return 0


def cmd_verify(a):
    out = Path(a.out).resolve()
    lock_path = out / "build" / "kit.lock"
    lock = load_json(lock_path, None)
    if not isinstance(lock, dict) or not lock.get("files"):
        print("ошибка: нет build/kit.lock — сначала mockup_kit.py init %s" % a.out, file=sys.stderr)
        return 2
    changed, missing = [], []
    for rel, h in lock["files"].items():
        p = out / rel
        if not p.exists():
            missing.append(rel)
        elif sha(p) != h:
            changed.append(rel)
    if a.update and (changed or missing):
        files = {rel: sha(out / rel) for rel in lock["files"] if (out / rel).exists()}
        lock = dict(lock, files=files, updated=date.today().isoformat())
        dump_json(lock_path, lock)
        print("kit.lock обновлён: принято изменённых %d, убрано пропавших %d" % (len(changed), len(missing)))
        return 0
    rep = {"ok": not changed and not missing, "changed": changed, "missing": missing, "files": len(lock["files"])}
    if a.json:
        print(json.dumps(rep, ensure_ascii=False, indent=2))
    else:
        if rep["ok"]:
            print("набор не менялся: %d файлов совпадают с build/kit.lock" % rep["files"])
        for rel in changed:
            print("ИЗМЕНЁН: %s — файлы набора правит только оркестратор (осознанно: mockup_kit.py verify --update)" % rel)
        for rel in missing:
            print("ПРОПАЛ: %s" % rel)
    return 0 if rep["ok"] else 1


# ---------------------------------------------------------------- направления и выбор
DIR_RE = re.compile(r"^#{2,3}\s+(?:Направление|Direction|Вариант)\s+([A-Za-zА-Яа-я0-9]{1,3})\s*[.:)—–-]*\s*(.*)$", re.M)


def parse_directions(out):
    p = Path(out) / "design" / "directions.md"
    if not p.exists():
        return None, None
    text = p.read_text(encoding="utf-8")
    heads = list(DIR_RE.finditer(text))
    dirs = []
    for k, m in enumerate(heads):
        did = m.group(1).upper()
        name = re.sub(r"^[«\"'*\s]+|[»\"'*\s]+$", "", m.group(2)).strip()
        end = heads[k + 1].start() if k + 1 < len(heads) else len(text)
        chunk = text[m.end():end]
        chunk = re.split(r"^#{1,2}\s", chunk, maxsplit=1, flags=re.M)[0]
        essence = ""
        for line in chunk.splitlines():
            t = re.sub(r"[*_`>#]|^\s*[-•]\s*", "", line).strip()
            if t:
                essence = re.sub(r"^(Суть|Одна фраза|Фраза-суть)\s*[:—-]\s*", "", t)[:160]
                break
        dirs.append({"id": did, "name": name or ("Направление " + did), "essence": essence})
    rec = None
    sec = re.search(r"^#{2,3}\s+Рекомендац[^\n]*\n(.*?)(?=^#{1,3}\s|\Z)", text, re.S | re.M)
    if sec and dirs:
        body = sec.group(1)
        ids = [d["id"] for d in dirs]
        m = re.search(r"(?:Направление|Direction|Вариант|выбрано|рекомендую|рекомендуем|рекомендуется)\s*[«\"]?([A-Za-zА-Яа-я0-9]{1,3})\b", body, re.I)
        if m and m.group(1).upper() in ids:
            rec = m.group(1).upper()
        else:
            for d in dirs:
                if d["name"] and d["name"].lower() in body.lower():
                    rec = d["id"]
                    break
    for d in dirs:
        d["recommended"] = d["id"] == rec
    dirs.sort(key=lambda d: not d["recommended"])
    return dirs, rec


def cmd_directions(a):
    dirs, rec = parse_directions(a.out)
    if dirs is None:
        print("ошибка: нет design/directions.md (шаг 1 брифа concept-design.md ещё не выполнен)", file=sys.stderr)
        return 2
    cfg = run_config(a.out)
    want = ((cfg.get("design") or {}).get("directions_count")) if isinstance(cfg.get("design"), dict) else None
    rep = {"directions": dirs, "recommended": rec, "count": len(dirs), "expected": want}
    if a.json:
        print(json.dumps(rep, ensure_ascii=False, indent=2))
    else:
        for d in dirs:
            print("%s%s — %s%s" % (d["id"], " (рекомендовано)" if d["recommended"] else "", d["name"], ": " + d["essence"] if d["essence"] else ""))
        if want and int(want) != len(dirs):
            print("предупреждение: в directions.md %d направлений, а design.directions_count = %s" % (len(dirs), want))
        if not rec:
            print("предупреждение: в разделе «Рекомендация» не найдено рекомендованное направление")
    return 0 if dirs else 1


def cmd_choose(a):
    out = Path(a.out).resolve()
    cfg_path = out / "build" / "run-config.json"
    cfg = load_json(cfg_path, None)
    if not isinstance(cfg, dict):
        print("ошибка: нет или не читается build/run-config.json", file=sys.stderr)
        return 2
    dirs, rec = parse_directions(out)
    if a.recommended:
        if not rec:
            print("ошибка: --recommended: в design/directions.md нет рекомендованного направления", file=sys.stderr)
            return 2
        pick = next(d for d in dirs if d["id"] == rec)
    else:
        want = a.direction.strip()
        pick = None
        for d in dirs or []:
            if want.upper() == d["id"] or want.lower() == d["name"].lower():
                pick = d
        if pick is None:
            if dirs:
                print("ошибка: направления %r нет в design/directions.md (есть: %s)" % (want, ", ".join("%s — %s" % (d["id"], d["name"]) for d in dirs)), file=sys.stderr)
                return 2
            pick = {"id": want, "name": want}
    design = cfg.get("design") if isinstance(cfg.get("design"), dict) else {}
    design.update({"chosen": pick["id"], "chosen_name": pick["name"], "chosen_by": a.by, "chosen_at": date.today().isoformat()})
    cfg["design"] = design
    dump_json(cfg_path, cfg)
    print("design.chosen = %s «%s» (выбрал: %s) → build/run-config.json; дальше — шаги 2–3 брифа concept-design.md" % (
        pick["id"], pick["name"], "владелец" if a.by == "owner" else "по умолчанию (рекомендованное)"))
    return 0


def design_gate(cfg, steps):
    """(можно, причина): шаги 2–3 брифа concept-design вне автопилота — только после design.chosen (FB-007)."""
    steps = str(steps or "")
    if not re.search(r"[23]", steps):
        return True, "шаг 1 (направления) — выбор не нужен"
    if cfg.get("autopilot"):
        return True, "автопилот: направление по умолчанию — рекомендованное (design.chosen_by = default)"
    d = cfg.get("design") if isinstance(cfg.get("design"), dict) else {}
    if d.get("chosen"):
        return True, "выбрано направление %s (%s)" % (d.get("chosen"), d.get("chosen_by") or "owner")
    return False, ("шаги 2–3 (токены и макеты) не рендерятся до выбора направления: сначала шаг 1 → design/directions.md, "
                   "вопрос владельцу (mockup_kit.py directions — варианты, рекомендованное первым), затем "
                   "mockup_kit.py choose <OUT> --direction <id> --by owner")


def cmd_gate(a):
    ok, why = design_gate(run_config(a.out), a.steps)
    print(("можно: " if ok else "закрыто: ") + why)
    return 0 if ok else 3


# ---------------------------------------------------------------- галерея
def cmd_gallery(a):
    out = Path(a.out).resolve()
    files = concept_files(out)
    if not files:
        print("ошибка: нет mockups/concepts/*.html", file=sys.stderr)
        return 2
    cfg = run_config(out)
    product = product_name(cfg)
    items = []
    for f in files:
        m = html_meta(f)
        if m.get("kind") == "component":
            continue
        items.append(dict(m, key=f.stem, file=f.name, png=(f.with_suffix(".png").name if f.with_suffix(".png").exists() else None)))
    variants, order = {}, []
    for it in items:
        v = it["variant"] or ""
        if v not in variants:
            variants[v] = []
            order.append(v)
        variants[v].append(it)
    marked = [v for v in order if v]
    warnings = []
    if not marked:
        warnings.append("варианты не размечены: добавьте макетам data-variant (или <meta name=\"ps:variant\">) — галерея собрана одним списком")
    active = [v for v in marked if not any(i["variant_status"] == "rejected" for i in variants[v])]
    rejected = [v for v in marked if v not in active]
    short = [v for v in active if len(variants[v]) < a.min]
    for v in short:
        warnings.append("вариант «%s»: экранов %d < %d (для сравнения нужно 2–3 рабочих экрана на вариант)" % (v, len(variants[v]), a.min))

    def card(it):
        href = "concepts/" + it["file"]
        title = it["title"] or it["key"]
        img = ('<a href="%s"><img src="concepts/%s" alt="%s" loading="lazy"></a>' % (htmlmod.escape(href), htmlmod.escape(it["png"]), htmlmod.escape(title))
               if it["png"] else '<div class="noimg">снимка нет — shoot_mockups.mjs</div>')
        meta = " · ".join(x for x in [it["key"], it["viewport"], ", ".join(it["proposals"])] if x)
        return ('<div class="c" data-card>%s<div class="cap"><a href="%s">%s</a></div><div class="meta">%s</div></div>' % (
            img, htmlmod.escape(href), htmlmod.escape(title), htmlmod.escape(meta)))

    sections = []
    groups = active + ([""] if "" in variants and marked else []) if marked else [""]
    for v in groups:
        its = variants.get(v, [])
        if not its:
            continue
        note = next((i["variant_note"] for i in its if i["variant_note"]), "")
        head = htmlmod.escape(v) if v else ("Прочие макеты" if marked else "Все макеты")
        sections.append('  <h2>%s</h2>\n  <p>%s</p>\n  <div class="g">%s</div>' % (head, htmlmod.escape(note), "".join(card(i) for i in its)))
    if rejected:
        sections.append("  <h2>Отклонено</h2>")
        for v in rejected:
            its = variants[v]
            note = next((i["variant_note"] for i in its if i["variant_note"]), "")
            sections.append('  <div class="rejected"><h3>%s</h3><p>%s</p><div class="g">%s</div></div>' % (htmlmod.escape(v), htmlmod.escape(note), "".join(card(i) for i in its)))
    compare = ""
    screens = {}
    for v in active:
        for it in variants[v]:
            if it["screen"]:
                screens.setdefault(it["screen"], {})[v] = it
    rows = [(s, by) for s, by in screens.items() if len(by) >= 2]
    if rows:
        head = "".join("<th>%s</th>" % htmlmod.escape(v) for v in active)
        body = []
        for s, by in rows:
            cells = []
            for v in active:
                it = by.get(v)
                if not it:
                    cells.append("<td>—</td>")
                elif it["png"]:
                    cells.append('<td><a href="concepts/%s"><img src="concepts/%s" alt="%s" loading="lazy"></a></td>' % (
                        htmlmod.escape(it["file"]), htmlmod.escape(it["png"]), htmlmod.escape(it["title"] or it["key"])))
                else:
                    cells.append('<td><a href="concepts/%s">%s</a></td>' % (htmlmod.escape(it["file"]), htmlmod.escape(it["title"] or it["key"])))
            body.append("<tr><th>%s</th>%s</tr>" % (htmlmod.escape(s), "".join(cells)))
        compare = ('  <h2>Один сценарий в разных вариантах</h2>\n  <p>Строки — сценарии (data-screen-id), столбцы — варианты.</p>\n'
                   '  <div class="wrap"><table class="cmp"><thead><tr><th>Сценарий</th>%s</tr></thead><tbody>%s</tbody></table></div>') % (head, "".join(body))
    title = a.title or "%s — варианты дизайна" % product
    intro = ("Концепт, не существующая функция. Варианты: %d%s; по 2–3 рабочих экрана на вариант. Нажмите на картинку, чтобы открыть "
             "макет; «с подсказками» — подсветка элементов «что это и для чего»." % (len(active), "; отклонено: %d" % len(rejected) if rejected else "")
             if marked else "Концепт, не существующая функция. Все макеты прогона; варианты не размечены.")
    tpl = (KIT / "gallery.html").read_text(encoding="utf-8")
    tpl = re.sub(r"<!--.*?-->", "<!-- Собрано mockup_kit.py gallery %s — не править вручную (перезаписывается). -->" % date.today().isoformat(), tpl, count=1, flags=re.S)
    page = (tpl.replace("{{LANG}}", htmlmod.escape(str(cfg.get("language") or "ru"))).replace("{{TITLE}}", htmlmod.escape(title))
            .replace("{{BADGE}}", htmlmod.escape("%s · %s · %s" % (BADGE_TEXT, product, date.today().isoformat())))
            .replace("{{INTRO}}", htmlmod.escape(intro)).replace("{{COMPARE}}", compare).replace("{{SECTIONS}}", "\n".join(sections)))
    dest = out / "mockups" / "gallery.html"
    dest.write_text(page, encoding="utf-8")
    rep = {"file": "mockups/gallery.html", "variants": {v: [i["key"] for i in variants[v]] for v in active},
           "rejected": rejected, "compare_rows": [s for s, _ in rows], "warnings": warnings}
    if a.json:
        print(json.dumps(rep, ensure_ascii=False, indent=2))
    else:
        print("галерея: mockups/gallery.html — вариантов %d, отклонено %d, строк сравнения %d" % (len(active), len(rejected), len(rows)))
        for w in warnings:
            print("предупреждение: " + w)
    return 1 if (not marked or short) else 0


def cmd_params(a):
    cfg = run_config(a.out)
    d = cfg.get("design") if isinstance(cfg.get("design"), dict) else {}
    try:
        forms = wanted_forms(cfg, None)
    except SystemExit:
        forms = d.get("forms") or []
    p = {"directions_count": int(d.get("directions_count") or 3), "modes": wanted_modes(cfg, None),
         "default_mode": d.get("default_mode") or None, "chosen": d.get("chosen") or None, "chosen_name": d.get("chosen_name") or None,
         "chosen_by": d.get("chosen_by") or None, "pointer_first": bool(d.get("pointer_first")), "forms": forms,
         "gallery": bool(d.get("gallery", True)), "autopilot": bool(cfg.get("autopilot"))}
    if a.json:
        print(json.dumps(p, ensure_ascii=False, indent=2))
    else:
        print("направлений: %d; режимы: %s; выбрано: %s; принцип: %s; формы: %s" % (
            p["directions_count"], ", ".join(p["modes"]) or "один интерфейс", (p["chosen"] or "нет") + (" (%s)" % p["chosen_by"] if p["chosen_by"] else ""),
            "pointer/touch-first (кнопки — основное, клавиши — ускорение)" if p["pointer_first"] else "не задан", ", ".join(forms)))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0], formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("init", help="скопировать набор, создать M00 и build/kit.lock")
    p.add_argument("out")
    p.add_argument("--forms", help="web,mobile,mobile-later (по умолчанию — из run-config)")
    p.add_argument("--modes", help="режимы интерфейса: tokens-<режим>.css (по умолчанию — design.modes)")
    p.add_argument("--force", action="store_true", help="заменить изменённые файлы набора шаблоном")
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("verify", help="набор не менялся после init")
    p.add_argument("out")
    p.add_argument("--update", action="store_true", help="принять текущие файлы набора как эталон")
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("directions", help="направления из design/directions.md, рекомендованное первым")
    p.add_argument("out")
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("choose", help="записать выбор направления в run-config")
    p.add_argument("out")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--direction")
    g.add_argument("--recommended", action="store_true")
    p.add_argument("--by", choices=["owner", "default"], default="owner")
    p = sub.add_parser("gate", help="можно ли рендерить шаги брифа concept-design")
    p.add_argument("out")
    p.add_argument("--steps", required=True)
    p = sub.add_parser("gallery", help="mockups/gallery.html по вариантам")
    p.add_argument("out")
    p.add_argument("--min", type=int, default=2)
    p.add_argument("--title")
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("params", help="параметры дизайн-этапа из run-config")
    p.add_argument("out")
    p.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    return {"init": cmd_init, "verify": cmd_verify, "directions": cmd_directions, "choose": cmd_choose, "gate": cmd_gate,
            "gallery": cmd_gallery, "params": cmd_params}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
