#!/usr/bin/env python3
"""Печатает папку установленного скилла product-strategy (<SKILL_DIR>).

Порядок: переменная PRODUCT_STRATEGY_DIR → установленный плагин (последняя версия в кэше) → ~/.claude/skills/product-strategy
→ папка этого файла. Скрипты и брифы ссылаются на <SKILL_DIR>, а не на рабочую копию репозитория.
Только стандартная библиотека.
"""
import os
import re
import sys
from pathlib import Path

NAME = "product-strategy"


def _ver(p):
    return tuple(int(x) for x in re.findall(r"\d+", p.name)[:3]) or (0,)


def find():
    env = os.environ.get("PRODUCT_STRATEGY_DIR")
    if env and (Path(env) / "SKILL.md").exists():
        return Path(env).resolve()
    cache = Path.home() / ".claude" / "plugins" / "cache"
    if cache.is_dir():
        cands = [v for mp in cache.iterdir() if (mp / NAME).is_dir() for v in (mp / NAME).iterdir() if (v / "SKILL.md").exists()]
        if cands:
            return max(cands, key=_ver).resolve()
    user = Path.home() / ".claude" / "skills" / NAME
    if (user / "SKILL.md").exists():
        return user.resolve()
    return Path(__file__).resolve().parent.parent


if __name__ == "__main__":
    print(find())
    sys.exit(0)
