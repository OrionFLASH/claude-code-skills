# -*- coding: utf-8 -*-
"""2.3.0 (#28): зарегистрирован ли хук на самом деле и как вызывать скилл через Skill — только чтение, без сети.

Что проверяется (для --check и --where):
  * ручные хуки UserPromptSubmit на typesafe_triage.py в ~/.claude/settings.json, ~/.claude/settings.local.json,
    .claude/settings.json и .claude/settings.local.json проекта: путь существует?
  * плагин typesafe-triage@…: включён ли (enabledPlugins с учётом приоритета local > project > user), установлен ли
    (~/.claude/plugins/installed_plugins.json), есть ли в папке версии hooks/hooks.json с нашим хуком и сам скрипт;
  * disableAllHooks (в любом файле настроек, в том числе управляемом организацией) и allowManagedHooksOnly;
  * выключатели скилла: TYPESAFE_TRIAGE=off, файл .typesafe-triage-off;
  * копии скилла в ~/.claude/skills и .claude/skills проекта: битые ссылки, резервные копии внутри каталога скиллов
    (Claude Code видит их как ещё один скилл с тем же именем — источник «призрака»), копия рядом с плагином.
Итог — «зарегистрирован / нет», список проблем и готовые команды починки. Из настроек читаются только блоки hooks,
enabledPlugins и флаги хуков; ключи и прочее не выводятся.
"""
import json
import os
import re
from pathlib import Path

PLUGIN = "typesafe-triage"
MARKETPLACE_REPO = "OrionFLASH/claude-code-skills"
DEFAULT_MARKETPLACE = "claude-code-skills"
SKILL_NAME = "typesafe-triage"
PLUGIN_SKILL = "%s:%s" % (PLUGIN, SKILL_NAME)
MANAGED_SETTINGS = ("/Library/Application Support/ClaudeCode/managed-settings.json", "/etc/claude-code/managed-settings.json",
                    "C:/ProgramData/ClaudeCode/managed-settings.json")
NAME_RE = re.compile(r"^name:\s*['\"]?([\w:.-]+)", re.M)
HOOK_PATH_RE = re.compile(r"\"([^\"]*typesafe_triage\.py)\"|([^\s\"'=]*typesafe_triage\.py)")


def _json(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def settings_files(home, cwd):
    """(уровень, путь) в порядке приоритета снизу вверх: user < user-local < project < project-local."""
    out = [("user", Path(home, ".claude", "settings.json")), ("user-local", Path(home, ".claude", "settings.local.json"))]
    if cwd:
        out += [("project", Path(cwd, ".claude", "settings.json")), ("local", Path(cwd, ".claude", "settings.local.json"))]
    return out


def _expand(path, home):
    path = path.replace("${HOME}", home).replace("$HOME", home).replace("%USERPROFILE%", home)
    return home + path[1:] if path.startswith("~") else path


def manual_hooks(files, home):
    """Ручные хуки UserPromptSubmit на typesafe_triage.py → [{file, command, path, exists}]."""
    out = []
    for _lvl, sf in files:
        groups = (_json(sf).get("hooks") or {}).get("UserPromptSubmit") or []
        for g in groups if isinstance(groups, list) else []:
            for hk in (g.get("hooks") or []) if isinstance(g, dict) else []:
                cmd = hk.get("command") if isinstance(hk, dict) else None
                if not isinstance(cmd, str) or "typesafe_triage" not in cmd:
                    continue
                m = HOOK_PATH_RE.search(cmd)
                raw = (m.group(1) or m.group(2)) if m else None
                rec = {"file": str(sf), "command": cmd, "path": None, "exists": None,
                       "timeout": hk.get("timeout") if isinstance(hk, dict) else None}
                if raw and "CLAUDE_PLUGIN_ROOT" not in raw:
                    p = _expand(raw, home)
                    rec.update(path=p, exists=os.path.isfile(p))
                out.append(rec)
    return out


def enabled_plugins(files):
    """Ключи typesafe-triage@… → (включён?, файл, где задано последним) с учётом приоритета уровней."""
    state = {}
    for _lvl, sf in files:
        ep = _json(sf).get("enabledPlugins") or {}
        if isinstance(ep, dict):
            for k, v in ep.items():
                if k.startswith(PLUGIN + "@"):
                    state[k] = (bool(v), str(sf))
    return state


def installed_plugins(home, cwd):
    """installed_plugins.json → {ключ: [{installPath, version, scope}]} для typesafe-triage@…"""
    data = _json(Path(home, ".claude", "plugins", "installed_plugins.json"))
    plugins = data.get("plugins") if isinstance(data.get("plugins"), dict) else data
    out = {}
    root = str(Path(cwd).resolve()) if cwd else None
    for k, entries in (plugins or {}).items():
        if not str(k).startswith(PLUGIN + "@"):
            continue
        for e in entries if isinstance(entries, list) else [entries]:
            if not isinstance(e, dict):
                continue
            proj = e.get("projectPath")
            if e.get("scope") not in (None, "user") and proj and root and not root.startswith(str(proj)):
                continue
            out.setdefault(k, []).append({"installPath": e.get("installPath"), "version": e.get("version"), "scope": e.get("scope")})
    return out


def plugin_hook_ok(install_path):
    """В папке версии плагина есть hooks/hooks.json с UserPromptSubmit → typesafe_triage.py и сам скрипт. → (ok, причина)."""
    if not install_path or not os.path.isdir(install_path):
        return False, "папки версии нет (%s)" % install_path
    hj = Path(install_path, "hooks", "hooks.json")
    data = _json(hj)
    groups = ((data.get("hooks") or {}).get("UserPromptSubmit") or []) if data else []
    cmds = [hk.get("command", "") for g in groups if isinstance(g, dict) for hk in (g.get("hooks") or []) if isinstance(hk, dict)]
    if not any("typesafe_triage.py" in c for c in cmds):
        return False, "в %s нет хука UserPromptSubmit на typesafe_triage.py" % hj
    if not Path(install_path, "scripts", "typesafe_triage.py").is_file():
        return False, "нет scripts/typesafe_triage.py в %s" % install_path
    return True, None


def known_marketplaces(home, files):
    names = set(_json(Path(home, ".claude", "plugins", "known_marketplaces.json")).keys())
    for _lvl, sf in files:
        names |= set((_json(sf).get("extraKnownMarketplaces") or {}).keys())
    return names


def hooks_disabled(files, managed=MANAGED_SETTINGS):
    """disableAllHooks / allowManagedHooksOnly → [(файл, флаг)]."""
    out = []
    for sf in [p for _l, p in files] + [Path(m) for m in managed]:
        d = _json(sf)
        for flag in ("disableAllHooks", "allowManagedHooksOnly"):
            if d.get(flag) is True:
                out.append((str(sf), flag))
    return out


def _skill_name(skill_md):
    try:
        head = Path(skill_md).read_text(encoding="utf-8", errors="replace")[:2000]
    except OSError:
        return None
    m = NAME_RE.search(head)
    return m.group(1) if m else None


def skill_copies(home, cwd):
    """Копии скилла в каталогах скиллов (без скрытых папок: .trash Claude Code не читает)
    → [{dir, name, kind: active|backup|broken}]."""
    roots = [Path(home, ".claude", "skills")] + ([Path(cwd, ".claude", "skills")] if cwd else [])
    out = []
    for root in roots:
        try:
            entries = sorted(root.iterdir())
        except OSError:
            continue
        for d in entries:
            if d.name.startswith("."):
                continue
            if d.is_symlink() and not d.exists():
                if SKILL_NAME in d.name:
                    out.append({"dir": str(d), "name": None, "kind": "broken"})
                continue
            if not d.is_dir():
                continue
            name = _skill_name(d / "SKILL.md")
            if name == SKILL_NAME:
                out.append({"dir": str(d), "name": name, "kind": "active" if d.name == SKILL_NAME else "backup"})
    return out


def skill_status(home, cwd, plugin_on):
    """Как вызывать скилл через Skill и что мешает → (имя | None, пояснение, проблемы, починка).
    Плагинный скилл называется «плагин:скилл» — typesafe-triage:typesafe-triage; «typesafe-triage» без префикса — только
    копия в каталоге скиллов. Резервная копия или битая ссылка в каталоге скиллов дают второй скилл или «призрак»."""
    problems, fixes = [], []
    copies = skill_copies(home, cwd)
    for c in copies:
        if c["kind"] == "broken":
            problems.append("битая ссылка %s: в списке скиллов будет «призрак» (Unknown skill)" % c["dir"])
            fixes.append("удалите ссылку %s" % c["dir"])
        elif c["kind"] == "backup":
            problems.append("резервная копия %s внутри каталога скиллов: Claude Code видит её как ещё один скилл %s"
                            % (c["dir"], SKILL_NAME))
            fixes.append("перенесите %s за пределы каталога скиллов (например, в ~/.claude/backups/)" % c["dir"])
        elif plugin_on:
            problems.append("копия %s и плагин одновременно: два скилла (%s и %s); оставьте один" % (c["dir"], SKILL_NAME, PLUGIN_SKILL))
    if plugin_on:
        return (PLUGIN_SKILL, "плагин: вызывать Skill(\"%s\"); имя без префикса — только для копии в ~/.claude/skills"
                % PLUGIN_SKILL, problems, fixes)
    if any(c["kind"] == "active" for c in copies):
        return SKILL_NAME, "копия в каталоге скиллов: Skill(\"%s\")" % SKILL_NAME, problems, fixes
    return (None, "скилл не найден ни плагином, ни копией: Skill его не вызовет (скрипт можно запускать по пути из --where)",
            problems, fixes)


def guarded_hook_command(script, python="python3"):
    """Защищённая команда ручного хука (как в INSTALL.md) для данного пути скрипта."""
    p = script.replace("\\", "/")
    home = os.path.expanduser("~").replace("\\", "/")
    if home and p.startswith(home + "/"):
        p = "$HOME" + p[len(home):]
    return ('f="%s"; if [ -f "$f" ]; then %s "$f" --hook; else echo \'{"systemMessage":"TypeSafe-триаж пропущен: скрипт хука '
            'не найден, проверьте установку (--where)"}\'; fi' % (p, python))


def check(home=None, cwd=None, script=None, environ=None, managed=MANAGED_SETTINGS):
    """Полная проверка → {registered, by, problems, fixes, skill_name, skill_note, off}."""
    home = home or os.path.expanduser("~")
    env = os.environ if environ is None else environ
    script = script or os.path.join(os.path.dirname(os.path.abspath(__file__)), "typesafe_triage.py")
    files = settings_files(home, cwd)
    problems, fixes, by = [], [], []
    manual = manual_hooks(files, home)
    for h in manual:
        if h["exists"] is False:
            problems.append("ручной хук в %s ведёт в несуществующий файл %s (python3 вернёт код 2 — запрос заблокируется)"
                            % (h["file"], h["path"]))
            fixes.append("в %s замените команду хука на: %s" % (h["file"], guarded_hook_command(script)))
        else:
            by.append("ручной хук в %s" % h["file"])
            if isinstance(h.get("timeout"), (int, float)) and h["timeout"] < 10:
                problems.append("у ручного хука в %s timeout %s < 10 с" % (h["file"], h["timeout"]))
                fixes.append("в %s поставьте \"timeout\": 10" % h["file"])
    enabled = enabled_plugins(files)
    installed = installed_plugins(home, cwd)
    for key in sorted(set(enabled) | set(installed)):
        on, where = enabled.get(key, (False, None))
        inst = installed.get(key) or []
        if on and not inst:
            problems.append("плагин %s включён (%s), но не установлен" % (key, where))
            fixes.append("claude plugin install %s, затем /reload-plugins" % key)
        elif on:
            ok, why = plugin_hook_ok(inst[-1].get("installPath"))
            if ok:
                by.append("плагин %s %s" % (key, inst[-1].get("version") or ""))
            else:
                problems.append("плагин %s включён, но хук недоступен: %s" % (key, why))
                fixes.append("claude plugin update %s (или uninstall + install), затем /reload-plugins" % key)
        elif inst:
            problems.append("плагин %s установлен, но выключен%s" % (key, (" (%s)" % where) if where else ""))
            fixes.append("claude plugin enable %s, затем /reload-plugins" % key)
    if enabled and any(on for on, _ in enabled.values()) and [h for h in manual if h["exists"]]:
        problems.append("хук и в settings.json, и в плагине: заметка одна, но оставьте один (для плагина — хук плагина)")
    off = []
    if str(env.get("TYPESAFE_TRIAGE", "")).lower() in ("off", "0", "false", "no"):
        off.append("TYPESAFE_TRIAGE=%s" % env.get("TYPESAFE_TRIAGE"))
    try:
        d = Path(cwd or os.getcwd()).resolve()
        off += ["файл %s" % (p / ".typesafe-triage-off") for p in [d, *d.parents] if (p / ".typesafe-triage-off").exists()]
    except OSError:
        pass
    if not by:
        if not fixes:   # ни ручного хука, ни плагина — поставить плагин (или прописать ручной хук)
            mk = known_marketplaces(home, files)
            name = next((k.split("@", 1)[1] for k in installed), DEFAULT_MARKETPLACE)
            if name not in mk:
                fixes.append("claude plugin marketplace add %s" % MARKETPLACE_REPO)
            fixes.append("claude plugin install %s@%s, затем /reload-plugins (или ручной хук: %s)"
                         % (PLUGIN, name, guarded_hook_command(script)))
        problems.insert(0, "хук не зарегистрирован: заметок «TypeSafe-триаж» не будет")
    disabled = hooks_disabled(files, managed)
    for f, flag in disabled:
        problems.append("%s: true в %s — %s" % (flag, f, "все хуки выключены" if flag == "disableAllHooks"
                                               else "разрешены только хуки организации"))
        if flag == "disableAllHooks":
            fixes.append("уберите \"disableAllHooks\": true из %s" % f)
    plugin_on = any(on for on, _ in enabled.values())
    skill_name, note, sp, sf = skill_status(home, cwd, plugin_on)
    problems += sp
    fixes += sf
    return {"registered": bool(by) and not any(flag == "disableAllHooks" for _f, flag in disabled), "by": by,
            "problems": problems, "fixes": fixes, "skill_name": skill_name, "skill_note": note, "off": off}


def report_lines(res):
    """Человекочитаемые строки для --check."""
    lines = ["Хук и вызов скилла:"]
    if res["registered"]:
        state = "зарегистрирован — " + "; ".join(res["by"])
    elif res["by"]:
        state = "прописан (%s), но не сработает — см. ВНИМАНИЕ" % "; ".join(res["by"])
    else:
        state = "НЕ зарегистрирован"
    lines.append("  хук: %s" % state)
    if res["off"]:
        lines.append("  выключен скиллом: %s (хук молчит)" % ", ".join(res["off"]))
    lines.append("  Skill: %s" % res["skill_note"])
    for p in res["problems"]:
        lines.append("  ВНИМАНИЕ: %s" % p)
    if res["fixes"]:
        lines.append("  Починка:")
        lines += ["    %s" % f for f in res["fixes"]]
    lines.append("  Список скиллов и хуки плагинов Claude Code читает при старте сессии: после починки — /reload-plugins "
                 "или новая сессия; перенос папки скилла в открытой сессии оставляет «призрак» (Unknown skill) до перезапуска.")
    return lines
