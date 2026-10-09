#!/usr/bin/env python3
"""Контрольные суммы файлов скила (SHA256SUMS): создание при релизе и проверка установленной копии (2.6.0, #48).

  python3 skill_sums.py generate <папка скила> [--write]   # печатает (или пишет в <папка>/SHA256SUMS) суммы всех файлов скила
  python3 skill_sums.py verify <папка скила>               # сверяет файлы с <папка>/SHA256SUMS; код 0 — совпало, 1 — расхождения, 2 — файла сумм нет

Что даёт: убеждается, что установленная копия совпадает с релизом (порча при копировании, случайная правка, неполное обновление).
Чего не даёт: защиты от злонамеренной подмены вместе с самим файлом сумм — для этого сверьте SHA256SUMS с тегом релиза на GitHub
(команда печатается при `verify`). Текстовые файлы хешируются с переводом строк CRLF → LF (git на Windows может подменить их).
Исключены: __pycache__, node_modules, .pytest_cache, .git, .DS_Store и сам SHA256SUMS. Только стандартная библиотека."""
import hashlib
import sys
from pathlib import Path

NAME = "SHA256SUMS"
EXCLUDE_DIRS = {"__pycache__", "node_modules", ".pytest_cache", ".git"}
EXCLUDE_FILES = {NAME, ".DS_Store"}


def collect(root):
    """Относительные POSIX-пути файлов скила, отсортированные."""
    root = Path(root)
    out = []
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(root)
        if any(part in EXCLUDE_DIRS for part in rel.parts) or p.name in EXCLUDE_FILES or p.suffix in (".pyc", ".pyo"):
            continue
        out.append(rel.as_posix())
    return sorted(out)


def file_hash(path):
    data = Path(path).read_bytes()
    if b"\0" not in data[:8192]:
        data = data.replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def generate(root):
    return "".join("%s  %s\n" % (file_hash(Path(root) / rel), rel) for rel in collect(root))


def parse(text):
    out = {}
    for line in text.splitlines():
        parts = line.strip().split("  ", 1)
        if len(parts) == 2 and len(parts[0]) == 64:
            out[parts[1]] = parts[0]
    return out


def verify(root):
    """→ {"ok", "count", "missing", "changed", "extra"}; нет файла сумм — None."""
    sums = Path(root) / NAME
    if not sums.is_file():
        return None
    want = parse(sums.read_text(encoding="utf-8"))
    have = set(collect(root))
    missing = sorted(set(want) - have)
    changed = sorted(r for r in want if r in have and file_hash(Path(root) / r) != want[r])
    extra = sorted(have - set(want))
    return {"ok": not missing and not changed, "count": len(want), "missing": missing, "changed": changed, "extra": extra}


def main(argv):
    if len(argv) < 2 or argv[0] not in ("generate", "verify"):
        print(__doc__)
        return 2
    root = Path(argv[1])
    if argv[0] == "generate":
        text = generate(root)
        if "--write" in argv:
            (root / NAME).write_text(text, encoding="utf-8", newline="\n")
            print("%s: %d файлов" % (root / NAME, text.count("\n")))
        else:
            sys.stdout.write(text)
        return 0
    r = verify(root)
    if r is None:
        print("Файла %s в %s нет — сверять не с чем." % (NAME, root))
        return 2
    print("Файлов в SHA256SUMS: %d; расхождений: изменено %d, отсутствует %d; лишних файлов: %d"
          % (r["count"], len(r["changed"]), len(r["missing"]), len(r["extra"])))
    for k, label in (("changed", "ИЗМЕНЁН"), ("missing", "ОТСУТСТВУЕТ"), ("extra", "лишний")):
        for rel in r[k][:20]:
            print("  %s: %s" % (label, rel))
    return 0 if r["ok"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
