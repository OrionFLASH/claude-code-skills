#!/usr/bin/env python3
"""Общая логика tools/: создание каркаса скила, регистрация и проверка.

Использование:
  skillsrepo.py new <name> "<description>"
  skillsrepo.py validate [name ...]
  skillsrepo.py sync [name ...]      # обновить таблицу README и marketplace.json из plugin.json
Только стандартная библиотека Python 3.8+.
"""
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILLS = ROOT / "skills"
MARKETPLACE = ROOT / ".claude-plugin" / "marketplace.json"
README = ROOT / "README.md"
SKELETON = ROOT / "shared" / "templates" / "skill-skeleton"
NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")
TABLE_START, TABLE_END = "<!-- skills-table:start -->", "<!-- skills-table:end -->"

# Шаблоны секретов. Совпадение — ошибка validate.
SECRET_PATTERNS = [
    ("GitHub token", re.compile(r"\b(gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})\b")),
    ("AWS key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("Slack token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b")),
    ("Private key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("OpenAI/Anthropic key", re.compile(r"\bsk-(ant-)?[A-Za-z0-9_-]{20,}\b")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("JWT", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}")),
    ("Password assignment", re.compile(r"(?i)\b(password|passwd|pwd|secret|token)\s*[:=]\s*['\"][^'\"$<{\s]{6,}['\"]")),
]
# E-mail допустим только на зарезервированных доменах-примерах.
EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@([A-Za-z0-9.-]+\.[A-Za-z]{2,})\b")
EMAIL_OK_DOMAINS = {"example.com", "example.org", "example.net", "anthropic.com", "users.noreply.github.com"}
TEXT_EXT = {".md", ".json", ".yaml", ".yml", ".py", ".sh", ".ps1", ".js", ".mjs", ".txt", ".toml"}


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def dump_json(path, data):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def parse_frontmatter(text):
    """Минимальный разбор YAML-frontmatter: ключи верхнего уровня, строки и блоки '>'/'|'."""
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end == -1:
        return None
    body = text[3:end].strip("\n").splitlines()
    result, key, buf = {}, None, []
    for line in body:
        m = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", line)
        if m and not line.startswith(" "):
            if key is not None:
                result[key] = " ".join(buf).strip()
            key, val = m.group(1), m.group(2).strip()
            buf = [] if val in (">", "|", ">-", "|-") else [val.strip("'\"")]
        elif key is not None:
            buf.append(line.strip())
    if key is not None:
        result[key] = " ".join(buf).strip()
    return result


def skill_dirs(names=None):
    if names:
        return [SKILLS / n for n in names]
    return sorted(p for p in SKILLS.iterdir() if p.is_dir()) if SKILLS.exists() else []


def plugin_info(skill):
    return load_json(skill / ".claude-plugin" / "plugin.json")


def changelog_version(skill):
    path = skill / "CHANGELOG.md"
    if not path.exists():
        return None
    m = re.search(r"^## \[?(\d+\.\d+\.\d+)\]?", path.read_text(encoding="utf-8"), re.M)
    return m.group(1) if m else None


def skill_status(skill):
    path = skill / ".status"
    return path.read_text(encoding="utf-8").strip() if path.exists() else "в разработке"


# ---------- sync ----------

def sync(names=None):
    """Привести таблицу README и marketplace.json в соответствие plugin.json скилов."""
    market = load_json(MARKETPLACE)
    plugins = {p["name"]: p for p in market.get("plugins", [])}
    for skill in skill_dirs(names):
        info = plugin_info(skill)
        entry = plugins.get(info["name"], {})
        entry.update({
            "name": info["name"],
            "source": f"./skills/{skill.name}",
            "description": info.get("description", ""),
            "version": info.get("version", "0.1.0"),
        })
        if "keywords" in info:
            entry["keywords"] = info["keywords"]
        plugins[info["name"]] = entry
    market["plugins"] = [plugins[k] for k in sorted(plugins)]
    dump_json(MARKETPLACE, market)

    rows = ["| Имя | Описание | Версия | Статус |", "|-----|----------|--------|--------|"]
    for skill in skill_dirs():
        info = plugin_info(skill)
        desc = info.get("description", "").replace("|", "\\|")
        rows.append(f"| [{info['name']}](skills/{skill.name}/) | {desc} | {info.get('version', '')} | {skill_status(skill)} |")
    text = README.read_text(encoding="utf-8")
    start, end = text.index(TABLE_START) + len(TABLE_START), text.index(TABLE_END)
    README.write_text(text[:start] + "\n" + "\n".join(rows) + "\n" + text[end:], encoding="utf-8", newline="\n")
    print(f"sync: marketplace.json и README обновлены ({len(market['plugins'])} плагинов)")


# ---------- new ----------

def new_skill(name, description):
    if not NAME_RE.match(name):
        sys.exit(f"Ошибка: имя '{name}' должно быть в kebab-case")
    target = SKILLS / name
    if target.exists():
        sys.exit(f"Ошибка: {target} уже существует")
    shutil.copytree(SKELETON, target)
    for path in target.rglob("*"):
        if path.is_file() and path.suffix in TEXT_EXT:
            text = path.read_text(encoding="utf-8")
            text = text.replace("{{name}}", name).replace("{{description}}", description)
            path.write_text(text, encoding="utf-8", newline="\n")
    print(f"new: создан каркас {target.relative_to(ROOT)}")
    sync([name])


# ---------- validate ----------

def scan_secrets(skill):
    problems = []
    for path in skill.rglob("*"):
        if not path.is_file() or path.suffix not in TEXT_EXT or "node_modules" in path.parts:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        rel = path.relative_to(ROOT)
        for label, rx in SECRET_PATTERNS:
            for m in rx.finditer(text):
                line = text.count("\n", 0, m.start()) + 1
                problems.append(f"{rel}:{line}: похоже на секрет ({label})")
        for m in EMAIL_RE.finditer(text):
            domain = m.group(1).lower()
            if domain not in EMAIL_OK_DOMAINS and not domain.endswith(".example") and not domain.endswith(".test"):
                line = text.count("\n", 0, m.start()) + 1
                problems.append(f"{rel}:{line}: e-mail вне доменов-примеров ({m.group(0)})")
    return problems


def validate(names=None):
    market = load_json(MARKETPLACE)
    market_names = {p["name"]: p for p in market.get("plugins", [])}
    readme = README.read_text(encoding="utf-8")
    errors, warnings = [], []
    dirs = skill_dirs(names)
    if not dirs:
        print("validate: скилов нет")
        return 0
    for skill in dirs:
        n = skill.name
        e = lambda msg: errors.append(f"[{n}] {msg}")
        if not skill.exists():
            e("папка не найдена")
            continue
        if not NAME_RE.match(n):
            e("имя папки не в kebab-case")
        for req in ("SKILL.md", "README.md", "CHANGELOG.md", ".claude-plugin/plugin.json"):
            if not (skill / req).exists():
                e(f"нет файла {req}")
        if not (skill / "tests").is_dir():
            e("нет папки tests/")
        skill_md = skill / "SKILL.md"
        if skill_md.exists():
            fm = parse_frontmatter(skill_md.read_text(encoding="utf-8"))
            if fm is None:
                e("SKILL.md без frontmatter")
            else:
                if fm.get("name") != n:
                    e(f"frontmatter name='{fm.get('name')}' не совпадает с папкой")
                desc = fm.get("description", "")
                if len(desc) < 40:
                    e("frontmatter description отсутствует или слишком короткий")
                if len(desc) > 1024:
                    warnings.append(f"[{n}] description длиннее 1024 символов ({len(desc)})")
            lines = skill_md.read_text(encoding="utf-8").count("\n")
            if lines > 400:
                warnings.append(f"[{n}] SKILL.md {lines} строк — вынесите детали в references/")
        pj = skill / ".claude-plugin" / "plugin.json"
        if pj.exists():
            try:
                info = load_json(pj)
            except json.JSONDecodeError as ex:
                e(f"plugin.json невалиден: {ex}")
                info = {}
            if info.get("name") != n:
                e("plugin.json name не совпадает с папкой")
            ver = info.get("version", "")
            if not SEMVER_RE.match(ver):
                e(f"plugin.json version '{ver}' не SemVer")
            cv = changelog_version(skill)
            if cv and cv != ver:
                e(f"версия CHANGELOG ({cv}) != plugin.json ({ver})")
            if n not in market_names:
                e("нет в marketplace.json")
            elif market_names[n].get("version") != ver:
                e(f"версия в marketplace.json ({market_names[n].get('version')}) != plugin.json ({ver})")
            elif market_names[n].get("source") != f"./skills/{n}":
                e("source в marketplace.json не указывает на папку скила")
        if f"](skills/{n}/)" not in readme:
            e("нет в таблице README.md (tools/validate --fix или new-skill)")
        for p in scan_secrets(skill):
            e(p)
    for w in warnings:
        print("WARN ", w)
    for err in errors:
        print("ERROR", err)
    print(f"validate: проверено скилов {len(dirs)}, ошибок {len(errors)}, предупреждений {len(warnings)}")
    return 1 if errors else 0


def main(argv):
    if not argv:
        sys.exit(__doc__)
    cmd, args = argv[0], argv[1:]
    if cmd == "new":
        if len(args) < 2:
            sys.exit('Использование: new <name> "<description>"')
        new_skill(args[0], args[1])
    elif cmd == "validate":
        fix = "--fix" in args
        names = [a for a in args if a != "--fix"]
        if fix:
            sync(names or None)
        sys.exit(validate(names or None))
    elif cmd == "sync":
        sync(args or None)
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main(sys.argv[1:])
