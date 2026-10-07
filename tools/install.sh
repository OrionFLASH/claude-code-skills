#!/usr/bin/env bash
# Ставит скилы симлинками в ~/.claude/skills (правки в репозитории подхватываются сразу).
#   tools/install.sh                 — все скилы
#   tools/install.sh a b             — выбранные
#   tools/install.sh --uninstall a   — убрать симлинки
#   CLAUDE_SKILLS_DIR=… переопределяет целевую папку.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET="${CLAUDE_SKILLS_DIR:-$HOME/.claude/skills}"
MODE=install
if [[ "${1:-}" == "--uninstall" ]]; then MODE=uninstall; shift; fi
if [[ $# -eq 0 ]]; then
  set -- $(cd "$ROOT/skills" && ls -d */ 2>/dev/null | tr -d '/')
fi
mkdir -p "$TARGET"
for name in "$@"; do
  src="$ROOT/skills/$name"; dst="$TARGET/$name"
  [[ -f "$src/SKILL.md" ]] || { echo "SKIP  $name: нет $src/SKILL.md"; continue; }
  if [[ $MODE == uninstall ]]; then
    if [[ -L "$dst" ]]; then rm "$dst"; echo "REMOVED $dst"; else echo "SKIP  $dst: не симлинк"; fi
    continue
  fi
  if [[ -L "$dst" ]]; then
    [[ "$(readlink "$dst")" == "$src" ]] && { echo "OK    $name (уже установлен)"; continue; }
    rm "$dst"
  elif [[ -e "$dst" ]]; then
    echo "SKIP  $name: $dst существует и не является симлинком — удалите вручную"; continue
  fi
  ln -s "$src" "$dst"; echo "LINKED $dst -> $src"
done
