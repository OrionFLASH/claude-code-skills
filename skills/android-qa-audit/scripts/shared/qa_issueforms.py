#!/usr/bin/env python3
"""GitHub issue forms (.github/ISSUE_TEMPLATE/*.yml) for the QA skills — read-only towards GitHub.

Read a repository's forms (`gh api …/contents/.github/ISSUE_TEMPLATE`, nothing is written), map the fields of a
finding to the form fields («поле формы ← поле находки»), check required fields and dropdown values (only the exact
text of an option is accepted) and render the body exactly as the web form does: `### <label>` + value, an empty
field — `_No response_`, checkboxes — `- [X]` / `- [ ]`, `render: <lang>` — a code block. Markdown-only templates
(.md) are reported with their section headings. Standard library only (+ miniyaml.py next to this file).

  qa_issueforms.cli(argv, skill)   commands for the skill's wrapper script:
    fetch --repo owner/repo --out DIR            download the forms (gh api, read-only) → DIR/<file>
    show FORM.yml [--json]                       fields: id, type, label, required, options
    map FORM.yml --values values.json [--overrides map.json] [--json]   table «поле ← источник», problems
    render FORM.yml --values values.json [--overrides map.json] [--title T] [--out body.md]
values.json — values prepared by the skill: summary, steps, expected, actual, environment, android, device,
app_version, severity, screenshots, logs, screen, suggestion, extra, frequency, platform, title (strings, Markdown).
overrides (map.json) — {"<field id or label>": "<value or exact option text>", "<checkbox label>": true}.
Environment: QA_GH_BIN — path to gh (tests use a fake one).
Exit codes of the CLI: 0 ok, 1 problems (unmapped required field, dropdown value not among options, unchecked
required checkbox — ask the user), 2 bad input / gh error.
"""
import argparse
import base64
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import miniyaml  # noqa: E402

NO_RESPONSE = "_No response_"
# finding value -> regex over a field's id and label (RU/EN); the first matching source wins, in this order
SOURCES = [
    ("steps", r"steps|reproduc|шаг|воспроизвед"),
    ("expected", r"expect|ожида"),
    ("actual", r"actual|observed|what happened|что произошло|фактическ|что случилось"),
    ("logs", r"\blogs?\b|logcat|журнал|stack ?trace|трассировк|crash log"),
    ("screenshots", r"screenshot|скриншот|снимк|media|attachment|вложени|изображени|video|видео|recording|запись экрана"),
    ("android", r"android version|версия android|os version|версия ос|api level|уровень api"),
    ("device", r"device model|модель устройства|модель телефона|phone model|^\S+ device$|^device$|устройство$"),
    ("environment", r"environment|окружени|device|устройств|платформ"),
    ("app_version", r"app version|version of the app|версия прилож|build|сборк|\bversion\b|\bверсия\b"),
    ("severity", r"severity|серь[её]зн|priority|приоритет|impact|критичн"),
    ("frequency", r"frequency|how often|частот|как часто|reproducib|воспроизводим"),
    ("platform", r"platform|\bos\b|операционн"),
    ("screen", r"screen|экран|\barea\b|раздел|component|компонент|where|где именно|feature area|модуль"),
    ("suggestion", r"suggest|proposal|solution|предлож|решени|идея|how should"),
    ("summary", r"summary|describe|description|описани|кратко|суть|problem|проблем|bug|ошибк|what is|что не так"),
    ("extra", r"additional|anything else|other|context|контекст|дополнительн|примечан|notes|прочее|комментар"),
]
SEVERITY_WORDS = {
    "critical": ["critical", "крит", "blocker", "блокир", "urgent", "срочн", "p0", "s1", "sev1", "highest"],
    "high": ["high", "высок", "major", "серь", "p1", "s2", "sev2", "важн"],
    "medium": ["medium", "средн", "normal", "обычн", "moderate", "p2", "s3", "sev3"],
    "low": ["low", "низк", "minor", "незначит", "p3", "s4", "sev4", "lowest"],
    "info": ["info", "trivial", "cosmetic", "косметич", "p4", "lowest", "низк"],
}
FREQ_WORDS = {"always": ["always", "всегда", "every time", "каждый раз", "100"],
              "sometimes": ["sometimes", "иногда", "intermittent", "периодич", "random", "не всегда"],
              "once": ["once", "один раз", "однажды", "rarely", "редко"]}


class FormError(Exception):
    pass


# ---------------------------------------------------------------- gh (read-only)

def gh_bin():
    return os.environ.get("QA_GH_BIN") or shutil.which("gh")


def gh_api(path, timeout=60):
    gh = gh_bin()
    if not gh:
        raise FormError("gh не найден (https://cli.github.com) — формы можно положить файлами и передать путь")
    try:
        p = subprocess.run([gh, "api", path], capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as ex:
        raise FormError(f"gh api {path}: {ex}")
    if p.returncode != 0:
        raise FormError(f"gh api {path}: {(p.stderr or p.stdout).strip()[:200]}")
    try:
        return json.loads(p.stdout)
    except ValueError:
        raise FormError(f"gh api {path}: не JSON")


def fetch(repo, out_dir):
    """Download issue templates of owner/repo into out_dir. Returns [{file, path, kind}]."""
    repo = re.sub(r"^https?://github\.com/|\.git$|/$", "", repo)
    try:
        listing = gh_api(f"repos/{repo}/contents/.github/ISSUE_TEMPLATE")
    except FormError as ex:
        if "404" in str(ex) or "Not Found" in str(ex):
            return []
        raise
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    saved = []
    for item in listing if isinstance(listing, list) else []:
        name = item.get("name", "")
        if item.get("type") != "file" or not re.search(r"\.(ya?ml|md)$", name, re.I):
            continue
        data = gh_api(f"repos/{repo}/contents/{item.get('path')}")
        raw = base64.b64decode(data.get("content", "")).decode("utf-8", "replace")
        (out / name).write_text(raw, encoding="utf-8")
        kind = "config" if name.lower() in ("config.yml", "config.yaml") else ("form" if name.lower().endswith(("yml", "yaml"))
                                                                               else "markdown")
        saved.append({"file": name, "path": str(out / name), "kind": kind})
    return saved


# ---------------------------------------------------------------- forms

def load_form(path):
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    if p.suffix.lower() == ".md":
        front, body = {}, text
        m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
        if m:
            front, body = miniyaml.load(m.group(1)) or {}, m.group(2)
        return {"file": p.name, "kind": "markdown", "name": front.get("name"), "title": front.get("title") or "",
                "labels": as_list(front.get("labels")), "sections": re.findall(r"^#{2,3} (.+)$", body, re.M),
                "template": body, "fields": []}
    try:
        d = miniyaml.load(text) or {}
    except Exception as ex:  # noqa: BLE001 — a form we cannot read is reported, not guessed
        raise FormError(f"{p.name}: YAML не прочитан ({ex})")
    if not isinstance(d, dict) or not isinstance(d.get("body"), list):
        raise FormError(f"{p.name}: нет списка body — это не форма issue")
    fields = []
    for i, el in enumerate(d["body"]):
        if not isinstance(el, dict):
            continue
        at = el.get("attributes") or {}
        val = el.get("validations") or {}
        opts = at.get("options") or []
        fields.append({"type": el.get("type"), "id": el.get("id") or f"field{i}", "label": str(at.get("label") or ""),
                       "description": at.get("description") or "", "placeholder": at.get("placeholder") or "",
                       "required": bool(val.get("required")),
                       "options": [o.get("label") if isinstance(o, dict) else str(o) for o in opts],
                       "option_required": [bool(isinstance(o, dict) and o.get("required")) for o in opts],
                       "multiple": bool(at.get("multiple")), "render": at.get("render"), "value": at.get("value"),
                       "default": at.get("default")})
    return {"file": p.name, "kind": "form", "name": d.get("name"), "description": d.get("description"),
            "title": d.get("title") or "", "labels": as_list(d.get("labels")), "assignees": as_list(d.get("assignees")),
            "fields": fields}


def as_list(v):
    if v is None:
        return []
    if isinstance(v, list):
        return [str(x) for x in v]
    return [x.strip() for x in str(v).split(",") if x.strip()]


def choose_form(forms, kind="bug"):
    """kind: bug | proposal. A form whose name / file / labels look like the kind; else the first form."""
    rx = r"bug|ошибк|баг|defect|дефект|crash|problem" if kind == "bug" else \
        r"feature|enhancement|предлож|идея|request|improv|улучш|suggest"
    cands = [f for f in forms if f.get("kind") in ("form", "markdown")]
    for f in cands:
        if re.search(rx, " ".join([f.get("file") or "", f.get("name") or ""] + f.get("labels", [])), re.I):
            return f
    return cands[0] if cands else None


def source_for(field):
    label, fid = field["label"].strip().lower(), str(field["id"]).replace("-", " ").replace("_", " ").lower()
    for name, rx in SOURCES:
        if re.search(rx, label, re.I) or re.search(rx, fid, re.I):
            return name
    return None


def pick_option(options, value, source):
    """Exact option for a value: the option text itself, or by severity / frequency words, or a contained word."""
    v = str(value or "").strip().lower()
    if not v:
        return None
    for o in options:
        if o.strip().lower() == v:
            return o
    words = SEVERITY_WORDS.get(v) if source == "severity" else FREQ_WORDS.get(v) if source == "frequency" else None
    if words:
        for w in words:
            hit = [o for o in options if w in o.lower()]
            if len(hit) == 1:
                return hit[0]
    hit = [o for o in options if o.lower() in v or v in o.lower()]
    return hit[0] if len(hit) == 1 else None


def lookup(overrides, field):
    for k in (field["id"], field["label"]):
        if k in (overrides or {}):
            return True, overrides[k]
    return False, None


def map_values(form, values, overrides=None):
    """[(field, item)] with item {source, value, checked, problem}; problems are listed separately."""
    rows, problems = [], []
    for f in form["fields"]:
        if f["type"] == "markdown":
            continue
        has, ov = lookup(overrides, f)
        src = "override" if has else source_for(f)
        item = {"id": f["id"], "label": f["label"], "type": f["type"], "required": f["required"], "source": src,
                "value": None, "problem": None}
        if f["type"] == "checkboxes":
            checked = []
            for o, req in zip(f["options"], f["option_required"]):
                on = bool((overrides or {}).get(o)) or (has and ov is True)
                checked.append(on)
                if req and not on:
                    item["problem"] = f"нужно подтверждение пользователя: «{o}» (обязательная отметка)"
            item["value"] = checked
        elif f["type"] == "dropdown":
            raw = ov if has else values.get(src) if src else None
            if has and raw not in f["options"] and not (f["multiple"] and isinstance(raw, list)
                                                         and all(x in f["options"] for x in raw)):
                item["problem"] = f"значение «{raw}» не из вариантов: {', '.join(f['options'])}"
            elif has:
                item["value"] = raw if isinstance(raw, list) else [raw]
            else:
                opt = pick_option(f["options"], raw, src) if raw else None
                if opt:
                    item["value"] = [opt]
                elif f["required"]:
                    item["problem"] = (f"выбрать вариант вручную (точный текст): {', '.join(f['options'])}"
                                       + (f" — значение находки «{raw}» не совпало" if raw else ""))
        else:
            raw = ov if has else (values.get(src) if src else None)
            if raw in (None, "", []) and f.get("value") and f["type"] == "textarea":
                raw = None  # the form's prefilled text is a hint, not an answer
            item["value"] = raw if raw not in (None, "") else None
            if f["required"] and item["value"] is None:
                item["problem"] = "обязательное поле без значения — нет подходящего поля находки (map.json)"
        if item["problem"]:
            problems.append(f"{f['label'] or f['id']}: {item['problem']}")
        rows.append((f, item))
    return rows, problems


def render_body(form, rows):
    out = []
    for f, item in rows:
        out.append(f"### {f['label']}")
        out.append("")
        if f["type"] == "checkboxes":
            out += [f"- [{'X' if on else ' '}] {o}" for o, on in zip(f["options"], item["value"] or [])]
        elif f["type"] == "dropdown":
            out.append(", ".join(item["value"]) if item["value"] else NO_RESPONSE)
        else:
            v = item["value"]
            if v is None:
                out.append(NO_RESPONSE)
            elif f.get("render"):
                out += [f"```{f['render']}", str(v).rstrip(), "```"]
            else:
                out.append(str(v).rstrip())
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def title_for(form, title):
    prefix = form.get("title") or ""
    return (prefix + title) if prefix and not title.startswith(prefix.strip()) else title


def render(form_path, values, overrides=None, title=""):
    """(title, body, labels, problems) for a form; a markdown template gets the skill's own body later."""
    form = load_form(form_path)
    if form["kind"] == "markdown":
        return title_for(form, title), None, form["labels"], [f"{form['file']}: шаблон Markdown — заполнить разделы "
                                                               f"{', '.join(form['sections']) or '(нет заголовков)'}"]
    rows, problems = map_values(form, values, overrides)
    return title_for(form, title), render_body(form, rows), form["labels"], problems


# ---------------------------------------------------------------- CLI for the skills' wrappers

def cli(argv, skill="qa"):
    ap = argparse.ArgumentParser(prog="issue_forms.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch")
    f.add_argument("--repo", required=True)
    f.add_argument("--out", required=True)
    s = sub.add_parser("show")
    s.add_argument("form")
    s.add_argument("--json", action="store_true")
    for name in ("map", "render"):
        p = sub.add_parser(name)
        p.add_argument("form")
        p.add_argument("--values", required=True)
        p.add_argument("--overrides")
        p.add_argument("--json", action="store_true")
        if name == "render":
            p.add_argument("--title", default="")
            p.add_argument("--out")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "fetch":
            res = fetch(a.repo, a.out)
            print(json.dumps({"repo": a.repo, "forms": res, "note": "" if res else "у репозитория нет форм issue — "
                              "шаблон скила"}, ensure_ascii=False, indent=1))
            return 0
        form = load_form(a.form)
        if a.cmd == "show":
            if a.json:
                print(json.dumps(form, ensure_ascii=False, indent=1))
            else:
                print(f"{form['file']}: {form.get('name') or ''} · заголовок «{form.get('title')}» · метки {form['labels']}")
                for fl in form["fields"]:
                    print(f"  [{fl['type']}] {fl['id']}: {fl['label']}" + (" (обязательно)" if fl["required"] else "")
                          + (f" — варианты: {', '.join(fl['options'])}" if fl["options"] else "")
                          + (f" ← {source_for(fl)}" if fl["type"] != "markdown" and source_for(fl) else ""))
            return 0
        values = json.loads(Path(a.values).read_text(encoding="utf-8"))
        overrides = json.loads(Path(a.overrides).read_text(encoding="utf-8")) if a.overrides else {}
        if a.cmd == "map":
            rows, problems = map_values(form, values, overrides)
            if a.json:
                print(json.dumps({"fields": [i for _, i in rows], "problems": problems}, ensure_ascii=False, indent=1))
            else:
                print("| Поле формы | Тип | Источник | Значение |\n|---|---|---|---|")
                for fl, i in rows:
                    v = i["value"]
                    v = ", ".join(map(str, v)) if isinstance(v, list) else (str(v or "—")[:60].replace("\n", " "))
                    print(f"| {fl['label']}{' *' if fl['required'] else ''} | {fl['type']} | {i['source'] or '—'} | "
                          f"{'⚠ ' + i['problem'] if i['problem'] else v} |")
            return 1 if problems else 0
        title, body, labels, problems = render(a.form, values, overrides, a.title)
        if a.out and body is not None:
            Path(a.out).parent.mkdir(parents=True, exist_ok=True)
            Path(a.out).write_text(body, encoding="utf-8")
        print(json.dumps({"title": title, "labels": labels, "out": a.out, "problems": problems,
                          "body": None if a.out else body}, ensure_ascii=False, indent=1))
        return 1 if problems else 0
    except (FormError, OSError, ValueError) as ex:
        print(f"{skill}: {ex}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(cli(sys.argv[1:]))
