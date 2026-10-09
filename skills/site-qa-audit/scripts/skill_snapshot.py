#!/usr/bin/env python3
"""Copy of the skill for one run: <RUN_DIR>/skill — the run and its executors never depend on the installed folder.

  skill_snapshot.py <RUN_DIR> [--from SKILL_DIR] [--mode auto|copy|link] [--no-node-modules] [--update-config]
                    [--force] [--json]

A plugin update or a cleaner may remove the installed skill folder in the middle of a long run («scripts/node
disappeared»). At the start of the run (step 2, right after <RUN_DIR> is created) the skill is copied into
<RUN_DIR>/skill: SKILL.md, references/, templates/, scripts/ (with scripts/node/node_modules), plugin.json. The copy is
a complete SKILL_DIR (skill_dir.py --check passes): put it into run-config.yaml → skill_dir (--update-config does it
and keeps the original path in skill_source) and give it to every executor.

--mode auto (default): node_modules — hard links (no extra space, they survive removal of the installed folder;
       another disk — a plain copy), everything else — copies.  copy — all copies.  link — all hard links.
--from: the source (default: skill_dir.py — SITE_QA_AUDIT_DIR → installed plugin → ~/.claude/skills).
An existing snapshot of the SAME version is reused (exit 0); another version is kept unless --force (exit 3).
tests/ and caches are not copied. Exit codes: 0 ok, 1 source not usable, 3 another snapshot exists.
"""
import argparse
import json
import os
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "shared"))
sys.path.insert(0, str(HERE))
import qa_snapshot  # noqa: E402
import runcfg  # noqa: E402
import skill_dir  # noqa: E402

INCLUDE = ("SKILL.md", "README.md", "INSTALL.md", "CHANGELOG.md", ".claude-plugin", "references", "templates", "scripts")
EXCLUDE = qa_snapshot.DEFAULT_EXCLUDE + ("tests", "qa-runs", ".integration", "*.tmp")
NODE_MODULES = "scripts/node/node_modules"


def snapshot(src, run_dir, mode="auto", node_modules=True, force=False):
    src, run_dir = Path(os.path.abspath(os.path.expanduser(str(src)))), Path(run_dir)
    why = skill_dir.problem(src)
    if why:
        return 1, {"ok": False, "error": f"источник не подходит: {src}: {why}"}
    dst = run_dir / "skill"
    version = skill_dir.version_of(src)
    old = qa_snapshot.read_meta(dst)
    if old and not force:
        if old.get("version") == version and not skill_dir.problem(dst):
            return 0, dict(old, ok=True, skill_dir=str(dst), reused=True)
        return 3, {"ok": False, "skill_dir": str(dst), "error": f"в прогоне уже есть копия версии {old.get('version')} "
                   f"(источник {old.get('from')}); версия скила одна на прогон — --force, чтобы заменить"}
    total = {"files": 0, "bytes": 0, "linked": 0, "copied": 0, "link_fallbacks": 0, "skipped_symlinks": []}
    exclude = EXCLUDE + (() if node_modules else ("node_modules",))
    for name in INCLUDE:
        s = src / name
        if s.is_dir():
            rep = qa_snapshot.copy_tree(s, dst / name, exclude=exclude, mode=mode,
                                        link_prefixes=("node/node_modules",) if name == "scripts" else ())
        elif s.is_file():
            dst.mkdir(parents=True, exist_ok=True)
            shutil.copy2(s, dst / name)
            rep = {"files": 1, "bytes": s.stat().st_size, "linked": 0, "copied": 1, "link_fallbacks": 0, "skipped_symlinks": []}
        else:
            continue
        for k in ("files", "bytes", "linked", "copied", "link_fallbacks"):
            total[k] += rep[k]
        total["skipped_symlinks"] += [f"{name}/{x}" for x in rep["skipped_symlinks"]]
    has_nm = (dst / NODE_MODULES / "playwright").is_dir()
    meta = qa_snapshot.write_meta(dst, {"from": str(src), "version": version, "mode": mode, "node_modules": has_nm,
                                        **{k: total[k] for k in ("files", "bytes", "linked", "copied", "link_fallbacks")}})
    warnings = []
    if not has_nm:
        warnings.append(f"в копии нет node_modules (браузерные скрипты не запустятся): cd {dst / 'scripts' / 'node'} && npm install")
    problem = skill_dir.problem(dst)
    if problem:
        return 1, {"ok": False, "skill_dir": str(dst), "error": f"копия неполная: {problem}"}
    return 0, dict(meta, ok=True, skill_dir=str(dst), reused=False, warnings=warnings,
                   size=qa_snapshot.human_size(total["bytes"]), symlinks_skipped=len(total["skipped_symlinks"]))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run_dir")
    ap.add_argument("--from", dest="src", help="папка скила-источника (по умолчанию skill_dir.py)")
    ap.add_argument("--mode", choices=["auto", "copy", "link"], default="auto")
    ap.add_argument("--no-node-modules", action="store_true", help="без scripts/node/node_modules")
    ap.add_argument("--update-config", action="store_true",
                    help="run-config.yaml: skill_dir — копия, skill_source — источник (и rules.json, если он есть)")
    ap.add_argument("--force", action="store_true", help="заменить копию другой версии")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    src = a.src or skill_dir.find()["skill_dir"] or str(HERE.parent)
    code, res = snapshot(src, a.run_dir, a.mode, not a.no_node_modules, a.force)
    if code == 0 and a.update_config:
        cfg = Path(a.run_dir) / "run-config.yaml"
        runcfg.set_top(cfg, "skill_dir", res["skill_dir"])
        runcfg.set_top(cfg, "skill_source", res.get("from") or str(src))
        res["config_updated"] = str(cfg)
    if a.json:
        print(json.dumps(res, ensure_ascii=False, indent=1))
    elif code == 0:
        how = "уже была" if res.get("reused") else (f"{res['files']} файлов, {res['size']}; жёстких ссылок {res['linked']}, "
                                                     f"копий {res['copied']}")
        print(f"SKILL_DIR прогона: {res['skill_dir']} (версия {res.get('version')}, из {res.get('from')}; {how})")
        for w in res.get("warnings") or []:
            print(f"  внимание: {w}")
        if res.get("config_updated"):
            print(f"  run-config.yaml: skill_dir → копия, skill_source → {res.get('from')}")
    else:
        print(f"skill_snapshot: {res['error']}", file=sys.stderr)
    sys.exit(code)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
