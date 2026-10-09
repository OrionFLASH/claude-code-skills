"""Edits of <RUN_DIR>/run-config.yaml that keep the rest of the file (comments included) as it is.

Module (no CLI), used by skill_snapshot.py, local_app.py, browser_mode.py:
  set_top(path, key, value)          top-level key: a scalar, a list or a dict (the whole block is replaced or added)
  load(path) -> dict                 the parsed config ({} if the file is missing)
  reexport_rules(run_dir)            url_guard.py export -> <RUN_DIR>/rules.json, if rules.json already exists
"""
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "shared"))
import miniyaml  # noqa: E402


def load(path):
    p = Path(path)
    return (miniyaml.load_file(str(p)) or {}) if p.is_file() else {}


def _block(key, value):
    if isinstance(value, (dict, list)) and value:
        return f"{miniyaml._dump_scalar(key)}:\n" + miniyaml.dump(value, 2) + "\n"
    if isinstance(value, dict):
        return f"{key}: {{}}\n"
    if isinstance(value, list):
        return f"{key}: []\n"
    return f"{key}: {miniyaml._dump_scalar(value)}\n"


def set_top(path, key, value):
    """Replace the top-level `key:` entry (its line and the indented lines under it) or append it. Returns new text."""
    p = Path(path)
    text = p.read_text(encoding="utf-8") if p.is_file() else ""
    lines = text.splitlines(keepends=True)
    head = re.compile(rf"^{re.escape(key)}\s*:")
    start = next((i for i, ln in enumerate(lines) if head.match(ln)), None)
    new = _block(key, value)
    if start is None:
        if lines and not lines[-1].endswith("\n"):
            lines[-1] += "\n"
        lines.append(new)
    else:
        end = start + 1
        while end < len(lines) and (lines[end].startswith((" ", "\t")) or not lines[end].strip()):
            end += 1
        # keep blank lines and comments that follow the block
        while end > start + 1 and not lines[end - 1].strip():
            end -= 1
        lines[start:end] = [new]
    out = "".join(lines)
    miniyaml.load(out)  # never write a config that does not parse
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(out, encoding="utf-8")
    return out


def reexport_rules(run_dir):
    """rules.json follows run-config.yaml: re-export it when it exists (node scripts read browser mode and roots)."""
    run_dir = Path(run_dir)
    rules, cfg = run_dir / "rules.json", run_dir / "run-config.yaml"
    if not rules.exists() or not cfg.exists():
        return None
    r = subprocess.run([sys.executable, str(HERE / "url_guard.py"), "export", "--config", str(cfg), "--out", str(rules)],
                       capture_output=True, text=True)
    return {"rules": str(rules), "code": r.returncode, "output": (r.stdout + r.stderr).strip()[-300:]}
