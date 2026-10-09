#!/usr/bin/env python3
"""doc_zsh.py SKILL_DIR — no command examples that break in zsh: a variable holding a command or several options
(A="python3 …", D="--serial … --run-dir …") used unquoted as $A / $D — zsh does not split it into words.
Path variables ($S/adb_helpers.py, $R) are fine. Exit 1 with the list of lines.
Shared test helper (source of truth: shared/tests/; copies in skills/<name>/tests/helpers/shared/ — do not edit)."""
import re
import sys
from pathlib import Path

root = Path(sys.argv[1])
ASSIGN = re.compile(r"\b([A-Z][A-Z0-9_]*)=[\"'](python3?|py\b|--)")
bad = []
for p in [root / "SKILL.md", root / "README.md", root / "INSTALL.md"] + sorted((root / "references").rglob("*.md")):
    if not p.exists():
        continue
    text = p.read_text(encoding="utf-8")
    names = {m.group(1) for m in ASSIGN.finditer(text)}
    for no, line in enumerate(text.splitlines(), 1):
        for n in names:
            if re.search(rf"\${n}(?![\w/])", line) or ASSIGN.search(line):
                bad.append(f"{p.relative_to(root)}:{no}: {line.strip()[:100]}")
                break
for b in bad:
    print("zsh:", b)
sys.exit(1 if bad else 0)
