# -*- coding: utf-8 -*-
"""2.2.0: документация — пути к скриптам без жёсткого ~/.claude/skills/… (T-5), правило effort (T-6). pytest test_typesafe_docs.py"""
from pathlib import Path

import pytest

SKILL = Path(__file__).resolve().parent.parent


@pytest.mark.parametrize("doc", ["SKILL.md", "README.md", "INSTALL.md"])
def test_docs_have_no_fixed_skills_path_commands(doc):
    text = (SKILL / doc).read_text(encoding="utf-8")
    assert "skills/typesafe-triage/scripts/typesafe_triage.py --" not in text      # команды — через $S / --where
    assert "S=~/.claude/skills" not in text
    assert "--where" in text


def test_skill_md_uses_skill_dir_variable():
    text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    assert "${CLAUDE_SKILL_DIR}/scripts" in text


# ---------- T-6 ----------
def test_skill_md_states_user_rule_is_explicit_effort_requirement():
    text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    assert "явное требование" in text and "effort=<effort из заметки>" in text and "CLAUDE.md" in text
