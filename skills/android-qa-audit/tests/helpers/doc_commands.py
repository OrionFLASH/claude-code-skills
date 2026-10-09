#!/usr/bin/env python3
"""Check that every command example in the skill's documentation is accepted by the script's argparse.

  doc_commands.py <SKILL_DIR> [--python PY] [--verbose]

Scans SKILL.md, README.md, INSTALL.md and references/**/*.md: inline code spans and lines of code blocks with
`<script>.py <subcommand> … --option …`. For every script in scripts/ that uses argparse it runs
`<script> [<subcommand>] --help` (parsing only — nothing is executed) and checks that the subcommand exists and
every --option of the example is known to that (sub)parser. Placeholders (<RUN_DIR>, …, N) are ignored.
Exit: 0 all examples are valid, 1 errors (printed), 2 usage error.
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

SPAN = re.compile(r"`([^`\n]+)`")
CALL = re.compile(r"\b([a-z_][a-z0-9_]*)\.py\b([^\n]*)")
FLAG = re.compile(r"^\[?(--[a-z][a-z0-9-]*)")
WORD = re.compile(r"^[a-z][a-z0-9-]*$")


def snippets(path):
    """(line number, text) of code: inline spans and code-block lines."""
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


QA = re.compile(r"(?:^|[\s/])qa(?:\.ps1)?\s+(emulator-\d+|[A-Z0-9][\w.:-]{5,}|-)\s+([a-z][a-z0-9-]*)\b([^\n]*)")


def commands(text):
    """[(script, [tokens])] for every `<name>.py …` in a snippet (several commands: ;, &&, |, →); the wrapper
    `qa <serial> <command> …` is adb_helpers.py <command> …; `job start … -- <command> …` checks both parts."""
    res = []
    text = text.replace("\\|", "|")
    for part in re.split(r"\s(?:&&|;|\|\||\||→)\s|;\s*|\s→\s", text):
        found = [(m.group(1), m.group(2).split()) for m in CALL.finditer(part)]
        found += [("adb_helpers", [m.group(2)] + m.group(3).split()) for m in QA.finditer(part)
                  if m.group(1) not in ("<serial|->",)]
        for script, toks in found:
            if script == "adb_helpers" and toks[:1] == ["job"] and "--" in toks:
                k = toks.index("--")
                res += [(script, toks[:k]), (script, toks[k + 1:])]
            else:
                res.append((script, toks))
    return res


class Help:
    def __init__(self, scripts, py):
        self.scripts, self.py, self.cache = scripts, py, {}

    def text(self, script, sub=None):
        key = (script, sub)
        if key not in self.cache:
            cmd = [self.py, str(self.scripts / f"{script}.py")] + ([sub] if sub else []) + ["--help"]
            try:
                p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
                self.cache[key] = (p.returncode, p.stdout + p.stderr)
            except (OSError, subprocess.TimeoutExpired) as ex:
                self.cache[key] = (1, str(ex))
        return self.cache[key]

    def choices(self, script):
        """Subcommands (or choices of the first positional) from the usage line; option choices are skipped."""
        code, txt = self.text(script)
        usage = txt.split("\n\n", 1)[0]
        for m in re.finditer(r"\{([a-z0-9,_-]+)\}", usage):
            before = usage[:m.start()].rstrip().split()
            if before and before[-1].lstrip("[").startswith("-") and not before[-1].endswith("]"):
                continue  # [--stand {own-emulator,…}] — choices of an option ([-h] is a whole token)
            return set(m.group(1).split(","))
        return set()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("skill_dir")
    ap.add_argument("--python", default=sys.executable)
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args()
    skill = Path(a.skill_dir).resolve()
    scripts = skill / "scripts"
    known = {p.stem for p in scripts.glob("*.py")
             if "argparse" in p.read_text(encoding="utf-8")
             or re.search(r"\b(qa_\w+|runjournal)\.(main|cli)\(", p.read_text(encoding="utf-8"))}
    docs = [skill / "SKILL.md", skill / "README.md", skill / "INSTALL.md"] + sorted((skill / "references").rglob("*.md"))
    helps = Help(scripts, a.python)
    errors, checked = [], 0
    for doc in docs:
        if not doc.exists():
            continue
        for no, snip in snippets(doc):
            for script, toks in commands(snip):
                if script not in known:
                    continue
                where = f"{doc.relative_to(skill)}:{no}"
                choices = helps.choices(script)
                sub = None
                if toks and choices and not toks[0].startswith(("-", "[", "<", "$", "…", "...")):
                    cand = toks[0].strip("\"'(),")
                    if cand in choices:
                        sub = cand
                    elif WORD.match(cand) and cand not in ("python3", "py", "python"):
                        errors.append(f"{where}: {script}.py — нет подкоманды «{cand}» (есть: {', '.join(sorted(choices))})")
                        continue
                code, txt = helps.text(script, sub)
                if code != 0:
                    errors.append(f"{where}: {script}.py {sub or ''} --help завершился с кодом {code}: {txt.strip()[-200:]}")
                    continue
                for t in toks:
                    m = FLAG.match(t)
                    if not m:
                        continue
                    flag = m.group(1).rstrip("-")
                    if not re.search(rf"(?<![\w-]){re.escape(flag)}(?![\w-])", txt):
                        errors.append(f"{where}: {script}.py {sub or ''} не принимает {flag}  ← «{snip.strip()[:120]}»")
                checked += 1
                if a.verbose:
                    print(f"ok {where}: {script}.py {sub or ''} {' '.join(t for t in toks if t.startswith('-'))}")
    for e in errors:
        print("ОШИБКА " + e)
    print(f"doc_commands: проверено примеров {checked}, ошибок {len(errors)}")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
