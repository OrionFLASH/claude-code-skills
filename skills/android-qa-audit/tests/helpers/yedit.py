#!/usr/bin/env python3
"""yedit.py SRC DST OLD NEW — copy SRC to DST replacing the first OLD by NEW; «\\n» in NEW is a new line.
Used by tests instead of sed (BSD sed on macOS has no \\n in the replacement)."""
import sys

src, dst, old, new = sys.argv[1:5]
text = open(src, encoding="utf-8").read()
if old not in text:
    sys.exit(f"yedit: «{old}» не найдено в {src}")
open(dst, "w", encoding="utf-8").write(text.replace(old, new.replace("\\n", "\n"), 1))
