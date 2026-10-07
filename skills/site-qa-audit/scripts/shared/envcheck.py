#!/usr/bin/env python3
"""Общие проверки окружения для скилов: версии CLI, gh, плагины и скилы Claude Code, таблица.

Используется из scripts/check_env.py скилов (вендорится в scripts/shared/).
  from envcheck import Row, tool_version, gh_status, claude_plugins, user_skills, print_table
Только стандартная библиотека.
"""
import json
import os
import platform
import re
import shutil
import subprocess
from pathlib import Path

OK, WARN, FAIL = "OK", "WARN", "FAIL"


class Row(dict):
    """Строка таблицы: component, version, status, note, fix."""

    def __init__(self, component, version="", status=OK, note="", fix=""):
        super().__init__(component=component, version=version, status=status, note=note, fix=fix)


def run(cmd, timeout=60, cwd=None):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=timeout, shell=isinstance(cmd, str), cwd=cwd)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except FileNotFoundError:
        return 127, ""
    except subprocess.TimeoutExpired:
        return 124, "timeout"


def os_name():
    s = platform.system()
    return {"Darwin": "macOS", "Windows": "Windows", "Linux": "Linux"}.get(s, s) + " " + platform.release()


def parse_version(text):
    m = re.search(r"(\d+)\.(\d+)(?:\.(\d+))?", text or "")
    return tuple(int(x or 0) for x in m.groups()) if m else None


def tool_version(name, cmd=None, min_version=None, fix=""):
    exe = shutil.which(name if cmd is None else cmd[0])
    if not exe:
        return Row(name, "", FAIL, "не найден", fix)
    code, out = run(cmd or [name, "--version"])
    ver = parse_version(out)
    vtext = ".".join(map(str, ver)) if ver else out.strip()[:40]
    if min_version and ver and ver < min_version:
        return Row(name, vtext, FAIL, f"нужна версия ≥ {'.'.join(map(str, min_version))}", fix)
    return Row(name, vtext, OK if code == 0 else WARN)


def gh_status(required_scopes=("repo", "public_repo")):
    if not shutil.which("gh"):
        return Row("gh auth", "", FAIL, "gh не установлен", "https://cli.github.com")
    code, out = run(["gh", "auth", "status"])
    if code != 0:
        return Row("gh auth", "", FAIL, "не авторизован", "gh auth login")
    m = re.search(r"Token scopes:\s*(.+)", out)
    scopes = re.findall(r"'([^']+)'", m.group(1)) if m else []
    acc = re.search(r"account (\S+)", out)
    if scopes and not any(s in scopes for s in required_scopes):
        return Row("gh auth", ",".join(scopes), FAIL, "нет scope repo/public_repo", "gh auth refresh -s repo")
    return Row("gh auth", ",".join(scopes) or "?", OK, f"аккаунт {acc.group(1) if acc else '?'}")


def claude_plugins():
    """Список установленных плагинов: [{id, enabled, mcpServers...}]. [] если CLI недоступен."""
    if not shutil.which("claude"):
        return []
    code, out = run(["claude", "plugin", "list", "--json"], timeout=90)
    if code != 0:
        return []
    try:
        start = out.index("[")
        return json.loads(out[start:])
    except (ValueError, json.JSONDecodeError):
        return []


def claude_mcp_servers():
    """Имена MCP-серверов и их статус из `claude mcp list` (медленно: проверяет подключение)."""
    if not shutil.which("claude"):
        return {}
    code, out = run(["claude", "mcp", "list"], timeout=180)
    res = {}
    for line in out.splitlines():
        m = re.match(r"^(.+?):\s.*-\s*(✔|✘|!|⏸|-)\s*(.*)$", line.strip())
        if m:
            res[m.group(1).strip()] = {"ok": m.group(2) == "✔", "status": m.group(3).strip()}
    return res


def user_skills():
    """Имена скилов в ~/.claude/skills (папки с SKILL.md, включая симлинки)."""
    root = Path(os.environ.get("CLAUDE_SKILLS_DIR", Path.home() / ".claude" / "skills"))
    if not root.exists():
        return []
    return sorted(p.name for p in root.iterdir() if (p / "SKILL.md").exists())


def plugin_skills(plugins):
    """{skill_name: plugin_id} для включённых плагинов (по папкам skills/ в installPath)."""
    res = {}
    for p in plugins:
        if not p.get("enabled"):
            continue
        base = Path(p.get("installPath", ""))
        for d in (base / "skills").glob("*/SKILL.md") if base.exists() else []:
            res[d.parent.name] = p["id"]
        for d in (base / "agents").glob("*.md") if base.exists() else []:
            res["agent:" + d.stem] = p["id"]
    return res


def print_table(rows, file=None):
    cols = [("component", "Компонент"), ("version", "Версия"), ("status", "Статус"), ("note", "Примечание"),
            ("fix", "Как исправить")]
    lines = ["| " + " | ".join(h for _, h in cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    for r in rows:
        lines.append("| " + " | ".join(str(r.get(k, "")).replace("|", "\\|") for k, _ in cols) + " |")
    text = "\n".join(lines)
    print(text, file=file)
    return text
