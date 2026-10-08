#!/usr/bin/env python3
"""Разбор шаблонов issues репозитория: .github/ISSUE_TEMPLATE (*.md и issue forms *.yml) и CONTRIBUTING.

  read_templates.py fetch owner/repo [--out templates.json] [--docs-dir DIR] [--local REPO_DIR]
      Скачивает через gh и разбирает шаблоны, config.yml, CONTRIBUTING, а также документы репозитория (*.md),
      на которые ссылаются формы, config.yml (contact_links) и CONTRIBUTING: они сохраняются в DIR
      (по умолчанию рядом с --out: <out без .json>-docs/) и в поле "docs". Внешние ссылки — только списком
      ("external_links"), не скачиваются. --local — читать репозиторий из локальной папки (тесты, офлайн).
  read_templates.py parse PATH [PATH ...]
      Разбирает локальные файлы шаблонов (для тестов).
  read_templates.py render templates.json --template NAME --values values.json [--format json|body|draft]
      Собирает тело issue по шаблону: values.json = {"<id или label секции>": "текст", "title": "..."}.
      Для issue forms результат совпадает с тем, что GitHub делает из формы: "### Label\\n\\nзначение".
      --format json (по умолчанию) — {title, body, labels}; body — только тело; draft — "TITLE: …", тело, метки.

Если YAML формы не разбирается мини-парсером, шаблон помечается parse_error и сохраняется raw — заполнить вручную.
"""
import argparse
import base64
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "shared"))
import miniyaml  # noqa: E402

TEMPLATE_DIRS = [".github/ISSUE_TEMPLATE", "ISSUE_TEMPLATE", "docs/ISSUE_TEMPLATE"]
SINGLE_FILES = [".github/ISSUE_TEMPLATE.md", "ISSUE_TEMPLATE.md", "docs/ISSUE_TEMPLATE.md"]
CONTRIB_FILES = ["CONTRIBUTING.md", ".github/CONTRIBUTING.md", "docs/CONTRIBUTING.md"]


def gh_json(path):
    p = subprocess.run(["gh", "api", path], capture_output=True, text=True, encoding="utf-8")
    if p.returncode != 0:
        return None
    return json.loads(p.stdout)


def gh_file(repo, path):
    data = gh_json(f"repos/{repo}/contents/{path}")
    if not data or isinstance(data, list) or "content" not in data:
        return None
    return base64.b64decode(data["content"]).decode("utf-8", errors="replace")


def split_frontmatter(text):
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            return text[3:end], text[end + 4:].lstrip("\n")
    return None, text


def as_list(v):
    if v is None:
        return []
    if isinstance(v, list):
        return v
    return [x.strip() for x in str(v).split(",") if x.strip()]


def parse_md(name, text):
    fm_text, body = split_frontmatter(text)
    fm = {}
    if fm_text:
        try:
            fm = miniyaml.load(fm_text) or {}
        except Exception as ex:  # noqa: BLE001
            fm = {"parse_error": str(ex)}
    sections = [{"id": m.group(2).strip(), "label": m.group(2).strip(), "type": "markdown-heading",
                 "level": len(m.group(1)), "required": None}
                for m in re.finditer(r"^(#{2,4})\s+(.+?)\s*$", body, re.M)]
    return {"file": name, "kind": "markdown", "name": fm.get("name") or Path(name).stem,
            "about": fm.get("about") or fm.get("description"), "title": fm.get("title") or "",
            "labels": as_list(fm.get("labels")), "assignees": as_list(fm.get("assignees")),
            "sections": sections, "body": body}


def parse_form(name, text):
    try:
        y = miniyaml.load(text) or {}
    except Exception as ex:  # noqa: BLE001
        return {"file": name, "kind": "form", "name": Path(name).stem, "parse_error": str(ex), "raw": text}
    sections = []
    for i, el in enumerate(y.get("body") or []):
        attrs = el.get("attributes") or {}
        typ = el.get("type")
        if typ == "markdown":
            sections.append({"id": el.get("id") or f"md{i}", "type": "markdown", "value": attrs.get("value")})
            continue
        opts = attrs.get("options") or []
        sections.append({
            "id": el.get("id") or attrs.get("label"), "label": attrs.get("label"), "type": typ,
            "description": attrs.get("description"), "placeholder": attrs.get("placeholder"),
            "required": bool((el.get("validations") or {}).get("required")),
            "options": [o.get("label") if isinstance(o, dict) else o for o in opts],
            "render": attrs.get("render"),
        })
    return {"file": name, "kind": "form", "name": y.get("name") or Path(name).stem,
            "about": y.get("description"), "title": y.get("title") or "", "labels": as_list(y.get("labels")),
            "assignees": as_list(y.get("assignees")), "projects": as_list(y.get("projects")),
            "type": y.get("type"), "sections": sections}


def parse_file(name, text):
    low = name.lower()
    if low.endswith(("config.yml", "config.yaml")):
        try:
            return {"file": name, "kind": "config", "config": miniyaml.load(text)}
        except Exception as ex:  # noqa: BLE001
            return {"file": name, "kind": "config", "parse_error": str(ex), "raw": text}
    if low.endswith((".yml", ".yaml")):
        return parse_form(name, text)
    return parse_md(name, text)


class GhSource:
    """Repository files through `gh api`."""

    def __init__(self, repo):
        self.repo = repo

    def listdir(self, path):
        listing = gh_json(f"repos/{self.repo}/contents/{path}")
        return listing if isinstance(listing, list) else None

    def read(self, path):
        return gh_file(self.repo, path)


class LocalSource:
    """Repository files from a local folder (tests, offline clones)."""

    def __init__(self, root):
        self.root = Path(root).resolve()

    def _safe(self, path):
        p = (self.root / path).resolve()
        return p if str(p).startswith(str(self.root)) else None

    def listdir(self, path):
        p = self._safe(path)
        if not p or not p.is_dir():
            return None
        return [{"name": x.name, "path": str(x.relative_to(self.root)).replace("\\", "/"),
                 "type": "file" if x.is_file() else "dir"} for x in sorted(p.iterdir())]

    def read(self, path):
        p = self._safe(path)
        return p.read_text(encoding="utf-8", errors="replace") if p and p.is_file() else None


LINK_RX = re.compile(r"\]\(([^)\s]+)\)|(https?://[^\s)\]>\"'«»]+)|(?<![\w/.:-])((?:\.{1,2}/|/)?(?:[\w.-]+/)*[\w.-]+\.md)\b")


def collect_strings(obj):
    if isinstance(obj, dict):
        for v in obj.values():
            yield from collect_strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from collect_strings(v)
    elif isinstance(obj, str):
        yield obj


def resolve_link(link, repo, base_dir):
    """Repository-relative path of a doc link, or None for external links."""
    link = link.split("#")[0].split("?")[0].rstrip(".,;:")
    m = re.match(r"https?://github\.com/([^/]+/[^/]+)/(?:blob|tree|raw)/[^/]+/(.+)$", link)
    if m:
        return m.group(2) if m.group(1).lower() == repo.lower() else None
    if re.match(r"https?://", link) or not link.lower().endswith(".md"):
        return None
    if link.startswith("/"):
        return link.lstrip("/")
    parts = []
    for seg in (base_dir.split("/") if base_dir and not link.startswith("..") else []) + link.split("/"):
        if seg in ("", "."):
            continue
        if seg == "..":
            if parts:
                parts.pop()
            continue
        parts.append(seg)
    return "/".join(parts)


def fetch_docs(result, src, repo, max_docs=20):
    """Download *.md documents referenced from templates, config.yml and CONTRIBUTING (one level + their links)."""
    queue, docs, external = [], {}, []
    owners = [(t.get("file", ""), t) for t in result["templates"]]
    if result.get("config"):
        owners.append((result["config"].get("file", ""), result["config"]))
    if result.get("contributing"):
        owners.append((result["contributing"]["file"], result["contributing"]["text"]))
    for fname, obj in owners:
        for s in collect_strings(obj):
            for m in LINK_RX.finditer(s):
                queue.append((next(g for g in m.groups() if g), fname, 0))
    while queue and len(docs) < max_docs:
        link, origin, depth = queue.pop(0)
        base = "/".join(origin.split("/")[:-1])
        path = resolve_link(link, repo, base)
        if path is None:
            if re.match(r"https?://", link) and link not in external:
                external.append(link)
            continue
        cands = [path]
        if base and not link.startswith(("/", "http")):
            cands.append(resolve_link(link, repo, ""))  # GitHub resolves some links from the repo root
        for cand in dict.fromkeys(c for c in cands if c):
            if cand in docs:
                break
            text = src.read(cand)
            if text is None:
                continue
            docs[cand] = {"path": cand, "referenced_from": origin, "text": text[:50000]}
            if depth < 1:
                queue += [(next(g for g in m.groups() if g), cand, depth + 1) for m in LINK_RX.finditer(text)]
            break
    result["docs"] = list(docs.values())
    result["external_links"] = external
    return result


def fetch(repo, src=None):
    src = src or GhSource(repo)
    result = {"repo": repo, "templates": [], "config": None, "contributing": None}
    for d in TEMPLATE_DIRS:
        listing = src.listdir(d)
        if not isinstance(listing, list):
            continue
        for item in listing:
            if item["type"] != "file" or not re.search(r"\.(md|ya?ml)$", item["name"], re.I):
                continue
            text = src.read(item["path"])
            if text is None:
                continue
            parsed = parse_file(item["path"], text)
            if parsed["kind"] == "config":
                result["config"] = parsed
            else:
                result["templates"].append(parsed)
        break
    if not result["templates"]:
        for f in SINGLE_FILES:
            text = src.read(f)
            if text:
                result["templates"].append(parse_md(f, text))
                break
    for f in CONTRIB_FILES:
        text = src.read(f)
        if text:
            result["contributing"] = {"file": f, "text": text[:20000]}
            break
    return fetch_docs(result, src, repo)


def render(tpl, values):
    """values: ключи — id или label секций, а также 'title'."""
    def val(sec):
        for k in (sec.get("id"), sec.get("label")):
            if k and k in values:
                return values[k]
        return None

    if tpl["kind"] == "form":
        parts = []
        for sec in tpl["sections"]:
            if sec["type"] == "markdown":
                continue
            v = val(sec)
            if isinstance(v, list):
                if sec["type"] == "checkboxes":
                    v = "\n".join(f"- [{'X' if o in v else ' '}] {o}" for o in sec.get("options") or [])
                else:
                    v = ", ".join(map(str, v))
            if v in (None, ""):
                v = "_No response_"
            elif sec.get("render"):
                v = f"```{sec['render']}\n{v}\n```"
            parts.append(f"### {sec['label']}\n\n{v}")
        body = "\n\n".join(parts)
    else:
        body = tpl["body"]
        for sec in tpl["sections"]:
            v = val(sec)
            if v is None:
                continue
            rx = re.compile(r"(^#{%d}\s+%s\s*$)(.*?)(?=^#{1,%d}\s|\Z)" % (sec["level"], re.escape(sec["label"]),
                                                                            sec["level"]), re.M | re.S)
            body = rx.sub(lambda m: m.group(1) + "\n\n" + str(v).strip() + "\n\n", body, count=1)
    title = values.get("title", "")
    if tpl.get("title") and not title.startswith(tpl["title"].strip()):
        title = tpl["title"].strip() + " " + title
    return {"title": title.strip(), "body": body.strip() + "\n", "labels": tpl.get("labels", [])}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch")
    f.add_argument("repo")
    f.add_argument("--out")
    f.add_argument("--docs-dir")
    f.add_argument("--local", help="локальная папка репозитория вместо gh")
    p = sub.add_parser("parse")
    p.add_argument("paths", nargs="+")
    r = sub.add_parser("render")
    r.add_argument("templates")
    r.add_argument("--template", required=True, help="name или file шаблона")
    r.add_argument("--values", required=True)
    r.add_argument("--format", choices=["json", "body", "draft"], default="json")
    a = ap.parse_args()
    if a.cmd == "fetch":
        repo = re.sub(r"^https?://github\.com/|\.git$|/$", "", a.repo)
        if a.local and not Path(a.local).is_dir():
            sys.stderr.write(f"read_templates: нет папки {a.local}\n")
            sys.exit(2)
        res = fetch(repo, LocalSource(a.local) if a.local else None)
        docs_dir = a.docs_dir or (str(Path(a.out).with_suffix("")) + "-docs" if a.out else None)
        if docs_dir:
            for d in res["docs"]:
                target = Path(docs_dir) / d["path"]
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(d["text"], encoding="utf-8")
                d["saved_to"] = str(target)
        text = json.dumps(res, ensure_ascii=False, indent=2)
        if a.out:
            Path(a.out).parent.mkdir(parents=True, exist_ok=True)
            Path(a.out).write_text(text, encoding="utf-8")
            print(f"{repo}: шаблонов {len(res['templates'])}, CONTRIBUTING: {'да' if res['contributing'] else 'нет'}, "
                  f"документов {len(res['docs'])}" + (f" -> {docs_dir}" if res["docs"] else "") +
                  f", внешних ссылок {len(res['external_links'])} -> {a.out}")
            for d in res["docs"]:
                print(f"  прочитать: {d['path']} (ссылка из {d['referenced_from']})")
        else:
            print(text)
    elif a.cmd == "parse":
        print(json.dumps([parse_file(x, Path(x).read_text(encoding="utf-8")) for x in a.paths],
                         ensure_ascii=False, indent=2))
    else:
        data = json.loads(Path(a.templates).read_text(encoding="utf-8"))
        tpls = data["templates"] if isinstance(data, dict) else data
        tpl = next((t for t in tpls if a.template in (t.get("name"), t.get("file"))), None)
        if tpl is None:
            sys.exit(f"шаблон '{a.template}' не найден")
        values = json.loads(Path(a.values).read_text(encoding="utf-8"))
        res = render(tpl, values)
        if a.format == "body":
            print(res["body"], end="")
        elif a.format == "draft":
            print(f"TITLE: {res['title']}\n\n{res['body']}" + (f"\nМетки: {', '.join(res['labels'])}\n" if res["labels"] else ""),
                  end="")
        else:
            print(json.dumps(res, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
