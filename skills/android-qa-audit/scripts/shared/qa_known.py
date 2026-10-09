#!/usr/bin/env python3
"""«Already known / intended» documents of the target project for the QA skills.

Many repositories describe what is known, intended or approximate («известные ограничения», «не ошибка»,
«by design», «размер около …»). Before publication the findings are compared with such documents: candidates —
a paragraph that talks about the same thing — are written into the finding (`known_candidates`, with the quote and
whether the paragraph says «задумано / известно / примерно»). Nothing is removed automatically: the agent reads the
quote and, if the document really covers the finding, `set` marks it `status: KNOWN` with the document and quote —
such findings are not published (only the report). Standard library only.

  qa_known.cli(argv, skill)
    fetch --repo owner/repo --path docs/KNOWN.md [--path docs/] --out DIR     gh api contents (read-only)
    check FINDINGS.json --doc FILE [--doc DIR…] [--threshold 0.22] [--json]   candidates → findings[].known_candidates
    set FINDINGS.json --id F-006 --doc FILE --quote "…" [--by "кто"]          status KNOWN (not published)
Environment: QA_GH_BIN — path to gh. Exit codes: 0 ok, 1 candidates found (check) — read them, 2 bad input.
"""
import argparse
import base64
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

INTENT = re.compile(r"задуман|намеренн|так и должно|ожидаем\w* поведени|не (является )?ошибк|не баг|известн\w* "
                    r"(огранич|проблем|особенност)|ограничени|приблизительн|примерно|около\b|≈|~\s?\d|by design|"
                    r"intended|expected behaviou?r|known (issue|limitation)|not a bug|approximate|roughly|wontfix|won't fix",
                    re.I)
WORD = re.compile(r"[A-Za-zА-Яа-яЁё0-9]{3,}")
STOP = {"the", "and", "for", "with", "that", "this", "при", "для", "как", "что", "это", "или", "если", "его", "она",
        "они", "был", "было", "нет", "все", "the", "not", "are", "экран", "screen", "кнопк", "button"}


class KnownError(Exception):
    pass


def stems(text):
    """Cheap stemming that works for Russian and English: lower case, first 6 letters, no stop words."""
    out = set()
    for w in WORD.findall((text or "").lower().replace("ё", "е")):
        s = w[:6]
        if s not in STOP and not s.isdigit():
            out.add(s)
    return out


def paragraphs(text):
    """[(heading, paragraph)] of a Markdown document; list items are separate paragraphs."""
    out, heading, buf = [], "", []

    def flush():
        if buf:
            p = " ".join(x.strip() for x in buf).strip()
            if p:
                out.append((heading, p))
            buf.clear()
    for line in (text or "").splitlines():
        if re.match(r"^#{1,6} ", line):
            flush()
            heading = line.lstrip("#").strip()
        elif not line.strip():
            flush()
        elif re.match(r"^\s*([-*+]|\d+[.)])\s+", line):
            flush()
            buf.append(re.sub(r"^\s*([-*+]|\d+[.)])\s+", "", line))
        elif re.match(r"^\|", line):
            flush()
            buf.append(line.replace("|", " "))
            flush()
        else:
            buf.append(line)
    flush()
    return out


def finding_text(f):
    return " ".join(str(f.get(k) or "") for k in ("title", "actual", "expected", "element", "check_id")) + " " + \
        str(f.get("screen") or "").split(".")[-1]


def score(f_stems, heading, para):
    p = stems(heading + " " + para)
    if not f_stems or not p:
        return 0.0
    common = f_stems & p
    return len(common) / float(min(len(f_stems), 12)) + (0.1 if INTENT.search(para) else 0)


def docs_of(paths):
    files = []
    for p in paths:
        p = Path(p)
        if p.is_dir():
            files += sorted(x for x in p.rglob("*") if x.suffix.lower() in (".md", ".txt", ".markdown"))
        elif p.is_file():
            files.append(p)
        else:
            raise KnownError(f"нет документа {p}")
    return files


def load(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return data, (data.get("findings", []) if isinstance(data, dict) else data)


def save(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def check(findings_path, doc_paths, threshold=0.22, top=3):
    data, fs = load(findings_path)
    docs = [(d, paragraphs(d.read_text(encoding="utf-8", errors="replace"))) for d in docs_of(doc_paths)]
    report = []
    for f in fs:
        fst = stems(finding_text(f))
        cands = []
        for d, paras in docs:
            for heading, para in paras:
                sc = score(fst, heading, para)
                if sc >= threshold:
                    cands.append({"doc": str(d), "heading": heading, "quote": para[:300], "score": round(sc, 2),
                                  "says_intended": bool(INTENT.search(para))})
        cands.sort(key=lambda x: (-x["says_intended"], -x["score"]))
        if cands:
            f["known_candidates"] = cands[:top]
            report.append({"id": f.get("id"), "title": f.get("title"), "candidates": cands[:top]})
        else:
            f.pop("known_candidates", None)
    save(findings_path, data)
    return report


def set_known(findings_path, fid, doc, quote, by=None):
    data, fs = load(findings_path)
    hit = [f for f in fs if f.get("id") == fid]
    if not hit:
        raise KnownError(f"нет находки {fid}")
    hit[0]["status"] = "KNOWN"
    hit[0]["status_reason"] = f"описано в документе проекта как известное/задуманное: {Path(doc).name}"
    hit[0]["known"] = {"doc": str(doc), "quote": quote[:500], "by": by or "агент после чтения цитаты",
                       "at": datetime.now().isoformat(timespec="seconds")}
    save(findings_path, data)
    return hit[0]


def fetch(repo, paths, out_dir):
    gh = os.environ.get("QA_GH_BIN") or shutil.which("gh")
    if not gh:
        raise KnownError("gh не найден — документы можно передать файлами (--doc)")
    repo = re.sub(r"^https?://github\.com/|\.git$|/$", "", repo)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    saved = []

    def api(path):
        p = subprocess.run([gh, "api", f"repos/{repo}/contents/{path}"], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=60)
        if p.returncode != 0:
            raise KnownError(f"gh api {path}: {(p.stderr or p.stdout).strip()[:160]}")
        return json.loads(p.stdout)
    queue = list(paths)
    while queue:
        path = queue.pop(0).strip("/")
        data = api(path)
        if isinstance(data, list):
            queue += [x["path"] for x in data if x.get("type") == "file" and re.search(r"\.(md|txt|markdown)$", x["name"], re.I)]
            continue
        name = path.replace("/", "__")
        (out / name).write_text(base64.b64decode(data.get("content", "")).decode("utf-8", "replace"), encoding="utf-8")
        saved.append(str(out / name))
    return saved


def cli(argv, skill="qa"):
    ap = argparse.ArgumentParser(prog="known_docs.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch")
    f.add_argument("--repo", required=True)
    f.add_argument("--path", action="append", required=True)
    f.add_argument("--out", required=True)
    c = sub.add_parser("check")
    c.add_argument("findings")
    c.add_argument("--doc", action="append", required=True)
    c.add_argument("--threshold", type=float, default=0.22)
    c.add_argument("--json", action="store_true")
    s = sub.add_parser("set")
    s.add_argument("findings")
    s.add_argument("--id", required=True)
    s.add_argument("--doc", required=True)
    s.add_argument("--quote", required=True)
    s.add_argument("--by")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "fetch":
            print(json.dumps({"saved": fetch(a.repo, a.path, a.out)}, ensure_ascii=False, indent=1))
            return 0
        if a.cmd == "set":
            f = set_known(a.findings, a.id, a.doc, a.quote, a.by)
            print(json.dumps({"id": f["id"], "status": f["status"], "known": f["known"]}, ensure_ascii=False))
            return 0
        rep = check(a.findings, a.doc, a.threshold)
        if a.json:
            print(json.dumps(rep, ensure_ascii=False, indent=1))
        else:
            for r in rep:
                print(f"{r['id']}: {r['title']}")
                for x in r["candidates"]:
                    print(f"   {'[задумано/известно] ' if x['says_intended'] else ''}{Path(x['doc']).name} › {x['heading']}: "
                          f"«{x['quote'][:160]}» ({x['score']})")
            print(f"{skill}: кандидатов «уже известно» — у {len(rep)} находок; прочитать цитаты, при совпадении — "
                  f"known_docs.py set … (status KNOWN, не публикуется)")
        return 1 if rep else 0
    except (KnownError, OSError, ValueError) as ex:
        print(f"{skill}: {ex}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(cli(sys.argv[1:]))
