# -*- coding: utf-8 -*-
"""2.3.0 (#28): --check проверяет, что хук реально зарегистрирован (settings.json и плагины), печатает команды починки;
имя скилла для Skill и «призраки» (битые ссылки, резервные копии в каталоге скиллов); синонимы триггеров. Офлайн, на
поддельном домашнем каталоге. pytest test_typesafe_install.py"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import triage_install as inst
import typesafe_triage as t

SKILL = Path(__file__).resolve().parent.parent
SCRIPT = SKILL / "scripts" / "typesafe_triage.py"
KEY = "typesafe-triage@claude-code-skills"


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(t, "LOG_PATH", tmp_path / "log.jsonl")
    monkeypatch.setattr(t.guard, "HOME", tmp_path / "guard")
    monkeypatch.delenv("TYPESAFE_TRIAGE", raising=False)
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)


def home_with(tmp_path, settings=None, installed=None, plugin_files=True, marketplaces=("claude-code-skills",)):
    home = tmp_path / "home"
    (home / ".claude" / "plugins").mkdir(parents=True)
    if settings is not None:
        (home / ".claude" / "settings.json").write_text(json.dumps(settings), encoding="utf-8")
    if installed is not None:
        (home / ".claude" / "plugins" / "installed_plugins.json").write_text(json.dumps({"version": 2, "plugins": installed}))
    (home / ".claude" / "plugins" / "known_marketplaces.json").write_text(json.dumps({m: {} for m in marketplaces}))
    return home


def plugin_dir(home, version="2.3.0", hooks=True, script=True):
    d = home / ".claude" / "plugins" / "cache" / "claude-code-skills" / "typesafe-triage" / version
    (d / "hooks").mkdir(parents=True)
    (d / "scripts").mkdir(parents=True)
    if hooks:
        (d / "hooks" / "hooks.json").write_text((SKILL / "hooks" / "hooks.json").read_text(encoding="utf-8"))
    if script:
        (d / "scripts" / "typesafe_triage.py").write_text("")
    (d / "SKILL.md").write_text("---\nname: typesafe-triage\n---\n")
    return d


def check(home, cwd):
    return inst.check(home=str(home), cwd=str(cwd), script=str(SCRIPT), environ={}, managed=())


def installed_entry(d, version="2.3.0"):
    return {KEY: [{"scope": "user", "installPath": str(d), "version": version}]}


def test_plugin_enabled_and_installed_is_registered(tmp_path):
    home = home_with(tmp_path, {"enabledPlugins": {KEY: True}})
    d = plugin_dir(home)
    (home / ".claude" / "plugins" / "installed_plugins.json").write_text(json.dumps({"version": 2, "plugins": installed_entry(d)}))
    res = check(home, tmp_path)
    assert res["registered"] and res["by"] == ["плагин %s 2.3.0" % KEY] and not res["problems"]
    assert res["skill_name"] == "typesafe-triage:typesafe-triage"


def test_nothing_installed_prints_install_commands(tmp_path):
    res = check(home_with(tmp_path, {}, marketplaces=()), tmp_path)
    assert not res["registered"] and res["problems"][0].startswith("хук не зарегистрирован")
    assert "claude plugin marketplace add OrionFLASH/claude-code-skills" in res["fixes"]
    assert any(f.startswith("claude plugin install typesafe-triage@claude-code-skills") and "/reload-plugins" in f
               and 'if [ -f "$f" ]' in f for f in res["fixes"])
    assert res["skill_name"] is None


def test_installed_but_disabled_suggests_enable(tmp_path):
    home = home_with(tmp_path, {"enabledPlugins": {KEY: False}})
    d = plugin_dir(home)
    (home / ".claude" / "plugins" / "installed_plugins.json").write_text(json.dumps({"version": 2, "plugins": installed_entry(d)}))
    res = check(home, tmp_path)
    assert not res["registered"] and any("установлен, но выключен" in p for p in res["problems"])
    assert res["fixes"] == ["claude plugin enable %s, затем /reload-plugins" % KEY]


def test_project_setting_overrides_user_enable(tmp_path):
    home = home_with(tmp_path, {"enabledPlugins": {KEY: True}})
    d = plugin_dir(home)
    (home / ".claude" / "plugins" / "installed_plugins.json").write_text(json.dumps({"version": 2, "plugins": installed_entry(d)}))
    proj = tmp_path / "proj"
    (proj / ".claude").mkdir(parents=True)
    (proj / ".claude" / "settings.local.json").write_text(json.dumps({"enabledPlugins": {KEY: False}}))
    assert not check(home, proj)["registered"]


def test_enabled_but_version_folder_or_hooks_missing(tmp_path):
    home = home_with(tmp_path, {"enabledPlugins": {KEY: True}}, installed=installed_entry(tmp_path / "gone"))
    res = check(home, tmp_path)
    assert not res["registered"] and any("папки версии нет" in p for p in res["problems"])
    assert any(f.startswith("claude plugin update %s" % KEY) for f in res["fixes"])
    d = plugin_dir(home, "2.3.1", hooks=False)
    (home / ".claude" / "plugins" / "installed_plugins.json").write_text(json.dumps({"version": 2, "plugins": installed_entry(d)}))
    assert any("нет хука UserPromptSubmit" in p for p in check(home, tmp_path)["problems"])
    enabled_not_installed = check(home_with(tmp_path / "x", {"enabledPlugins": {KEY: True}}), tmp_path)
    assert any("включён" in p and "не установлен" in p for p in enabled_not_installed["problems"])


def test_manual_hook_to_missing_file_gets_guarded_fix(tmp_path):
    cmd = 'python3 "$HOME/.claude/skills/typesafe-triage/scripts/typesafe_triage.py" --hook'
    home = home_with(tmp_path, {"hooks": {"UserPromptSubmit": [{"hooks": [{"type": "command", "command": cmd, "timeout": 5}]}]},
                                "env": {"TYPESAFE_API_KEY": "sk-" "secretsecretsecret"}})
    res = check(home, tmp_path)
    assert not res["registered"] and any("несуществующий файл" in p for p in res["problems"])
    assert any(str(SCRIPT.name) in f and 'if [ -f "$f" ]' in f for f in res["fixes"])
    assert "secretsecret" not in json.dumps(res, ensure_ascii=False)


def test_manual_hook_existing_file_and_short_timeout(tmp_path):
    script = tmp_path / "skill" / "scripts" / "typesafe_triage.py"
    script.parent.mkdir(parents=True)
    script.write_text("")
    home = home_with(tmp_path, {"hooks": {"UserPromptSubmit": [{"hooks": [
        {"type": "command", "command": 'python3 "%s" --hook' % script, "timeout": 5}]}]}})
    res = check(home, tmp_path)
    assert res["registered"] and any("timeout 5 < 10" in p for p in res["problems"])


def test_disable_all_hooks_is_reported(tmp_path):
    home = home_with(tmp_path, {"enabledPlugins": {KEY: True}, "disableAllHooks": True})
    d = plugin_dir(home)
    (home / ".claude" / "plugins" / "installed_plugins.json").write_text(json.dumps({"version": 2, "plugins": installed_entry(d)}))
    res = check(home, tmp_path)
    assert not res["registered"] and res["by"] and any("disableAllHooks" in p for p in res["problems"])
    assert any("disableAllHooks" in f for f in res["fixes"])
    assert "прописан" in "\n".join(inst.report_lines(res))


def test_ghosts_backup_copy_broken_link_and_duplicate(tmp_path):
    home = home_with(tmp_path, {"enabledPlugins": {KEY: True}})
    d = plugin_dir(home)
    (home / ".claude" / "plugins" / "installed_plugins.json").write_text(json.dumps({"version": 2, "plugins": installed_entry(d)}))
    skills = home / ".claude" / "skills"
    for name in ("typesafe-triage", "typesafe-triage.bak-20261009"):
        (skills / name).mkdir(parents=True)
        (skills / name / "SKILL.md").write_text("---\nname: typesafe-triage\ndescription: x\n---\n")
    (skills / ".trash" / "typesafe-triage-copy").mkdir(parents=True)     # скрытые папки Claude Code не читает
    (skills / ".trash" / "typesafe-triage-copy" / "SKILL.md").write_text("---\nname: typesafe-triage\n---\n")
    if os.name != "nt":
        os.symlink(str(tmp_path / "nowhere"), str(skills / "typesafe-triage-link"))
    res = check(home, tmp_path)
    text = "\n".join(res["problems"])
    assert "резервная копия" in text and "typesafe-triage.bak-20261009" in text and ".trash" not in text
    assert "два скилла" in text and res["skill_name"] == "typesafe-triage:typesafe-triage"
    if os.name != "nt":
        assert "битая ссылка" in text


def test_copy_install_skill_name_and_off_switch(tmp_path):
    home = home_with(tmp_path, {})
    (home / ".claude" / "skills" / "typesafe-triage").mkdir(parents=True)
    (home / ".claude" / "skills" / "typesafe-triage" / "SKILL.md").write_text("---\nname: typesafe-triage\n---\n")
    (tmp_path / ".typesafe-triage-off").write_text("")
    res = check(home, tmp_path)
    assert res["skill_name"] == "typesafe-triage" and res["off"]


def test_run_check_exit_codes(monkeypatch, capsys):
    monkeypatch.setattr(t, "triage", lambda *a, **k: {"model": "sonnet", "source": "typesafe", "reason": "r"})
    monkeypatch.setattr(t.inst, "check", lambda **k: {"registered": False, "by": [], "problems": ["хук не зарегистрирован"],
                                                     "fixes": ["claude plugin install x"], "skill_name": None, "skill_note": "n", "off": []})
    assert t.run_check() == 3
    out = capsys.readouterr().out
    assert "НЕ зарегистрирован" in out and "Починка:" in out and "claude plugin install x" in out
    monkeypatch.setattr(t.inst, "check", lambda **k: {"registered": True, "by": ["плагин"], "problems": [], "fixes": [],
                                                     "skill_name": "a:b", "skill_note": "n", "off": []})
    assert t.run_check() == 0
    monkeypatch.setattr(t, "triage", lambda *a, **k: {"model": "sonnet", "source": "heuristic", "reason": "r"})
    assert t.run_check() == 1


def test_where_shows_skill_call_name(tmp_path):
    home = home_with(tmp_path, {"enabledPlugins": {KEY: True}})
    rep = t.where_report(home=str(home), cwd=str(tmp_path))
    assert "# вызов через Skill: плагин: вызывать Skill(\"typesafe-triage:typesafe-triage\")" in rep


def test_check_cli_on_fake_home_has_no_secrets(tmp_path):
    home = home_with(tmp_path, {"env": {"TYPESAFE_API_KEY": "sk-" "secretsecretsecret"}})
    env = dict(os.environ, HOME=str(home), TYPESAFE_TRIAGE_HOME=str(tmp_path / "st"))
    env.pop("TYPESAFE_API_KEY", None)
    r = subprocess.run([sys.executable, "-B", str(SCRIPT), "--check"], capture_output=True, text=True, env=env, timeout=60,
                       cwd=str(tmp_path))
    assert r.returncode == 1 and "Хук и вызов скилла:" in r.stdout and "НЕ зарегистрирован" in r.stdout
    assert "secretsecret" not in r.stdout + r.stderr


# ---------- вызов через Skill: frontmatter, имя, синонимы ----------
def frontmatter():
    text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    assert m
    return dict(re.findall(r"^(\w+): (.*)$", m.group(1), re.M))


def test_skill_frontmatter_name_and_plugin_layout():
    fm = frontmatter()
    # у плагина из кэша папка называется по версии (…/typesafe-triage/2.6.0), у клона и копии — typesafe-triage
    assert fm["name"] == "typesafe-triage" and (SKILL.name == "typesafe-triage" or re.fullmatch(r"\d+\.\d+\.\d+", SKILL.name))
    pj = json.loads((SKILL / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    assert pj["name"] == "typesafe-triage" and pj["skills"] == ["./"]       # плагинное имя: typesafe-triage:typesafe-triage


@pytest.mark.parametrize("word", ["triangle", "TypeSave", "триангл", "тайпсейф", "триаж модели", "выбери модель"])
def test_description_has_trigger_synonyms(word):
    assert word.lower() in frontmatter()["description"].lower()


def test_description_fits_limit():
    assert 40 <= len(frontmatter()["description"]) <= 1024
