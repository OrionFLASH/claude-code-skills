#!/usr/bin/env python3
"""Check that --options of node script examples in the documentation exist in the scripts (node has no --help here).

  doc_node_flags.py <SKILL_DIR> [--verbose]

Scans SKILL.md, README.md, INSTALL.md and references/**/*.md (inline code and code blocks) for
`scripts/node/<name>.(js|mjs) … --flag …` and checks that every --flag is read by that script: `a.flag`, `a['flag']`,
`args.flag`, `'--flag'` or a parseArgs default key. Also every `node/<name>.js` mentioned must exist.
Exit: 0 ok, 1 errors (printed).
"""
import argparse
import re
import sys
from pathlib import Path

SPAN = re.compile(r"`([^`\n]+)`")
CALL = re.compile(r"scripts/node/([a-z_][a-z0-9_]*)\.(m?js)\b([^\n]*)")
FLAG = re.compile(r"^\[?(--[a-z][a-z0-9-]*)")


def snippets(path):
    out, block = [], False
    for no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if line.lstrip().startswith("```"):
            block = not block
            continue
        if block:
            out.append((no, re.sub(r"\s#\s.*$", "", line)))
        else:
            out += [(no, m.group(1)) for m in SPAN.finditer(line)]
    return out


LIB_FLAGS = [  # flags read by shared helpers of scripts/node/lib.js, not by the script itself
    (re.compile(r"\burlsFromArgs\b"), {"--url", "--urls-file"}),                       # positional + --url + --urls-file
    (re.compile(r"\b(launchOptions|openDevice)\b"), {"--headed", "--headless", "--slowmo"}),  # lib.browserMode
]


def accepted(src, flag):
    if any(rx.search(src) and flag in flags for rx, flags in LIB_FLAGS):
        return True
    name = flag[2:]
    ident = name.replace("-", "_")
    pats = [rf"\ba(rgs)?\.{re.escape(name)}\b" if "-" not in name else None,
            rf"\ba(rgs)?\[\s*['\"]{re.escape(name)}['\"]\s*\]", rf"['\"]--{re.escape(name)}['\"]",
            rf"['\"]{re.escape(name)}['\"]\s*:", rf"\b{re.escape(ident)}\b\s*:"]
    return any(p and re.search(p, src) for p in pats)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("skill_dir")
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args()
    skill = Path(a.skill_dir).resolve()
    node = skill / "scripts" / "node"
    docs = [skill / "SKILL.md", skill / "README.md", skill / "INSTALL.md"] + sorted((skill / "references").rglob("*.md"))
    errors, checked, cache = [], 0, {}
    for doc in docs:
        if not doc.exists():
            continue
        for no, snip in snippets(doc):
            for m in CALL.finditer(snip.replace("\\|", "|")):
                name, ext, rest = m.group(1), m.group(2), m.group(3)
                where = f"{doc.relative_to(skill)}:{no}"
                f = node / f"{name}.{ext}"
                if not f.exists():
                    errors.append(f"{where}: нет скрипта scripts/node/{name}.{ext}")
                    continue
                src = cache.setdefault(f, f.read_text(encoding="utf-8"))
                rest = re.split(r"\s(?:&&|;|\|\||\|)\s", rest)[0]
                for t in rest.split():
                    fm = FLAG.match(t)
                    if fm and not accepted(src, fm.group(1)):
                        errors.append(f"{where}: {name}.{ext} не читает {fm.group(1)}  ← «{snip.strip()[:110]}»")
                checked += 1
                if a.verbose:
                    print(f"ok {where}: {name}.{ext}")
    for e in errors:
        print("ERROR", e)
    print(f"doc_node_flags: проверено примеров {checked}, ошибок {len(errors)}")
    return 1 if errors else 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
