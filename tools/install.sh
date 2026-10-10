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
# link_one <имя ссылки> <папка скила>: одна ссылка ~/.claude/skills/<имя> -> папка
link_one() {
  local name="$1" src="$2" dst="$TARGET/$1"
  [[ -f "$src/SKILL.md" ]] || { echo "SKIP  $name: нет $src/SKILL.md"; return; }
  if [[ $MODE == uninstall ]]; then
    if [[ -L "$dst" ]]; then rm "$dst"; echo "REMOVED $dst"; else echo "SKIP  $dst: не симлинк"; fi
    return
  fi
  if [[ -L "$dst" ]]; then
    [[ "$(readlink "$dst")" == "$src" ]] && { echo "OK    $name (уже установлен)"; return; }
    rm "$dst"
  elif [[ -e "$dst" ]]; then
    echo "SKIP  $name: $dst существует и не является симлинком — удалите вручную"
    [[ -e "$dst/$name" ]] && echo "WARN  $name: внутри $dst есть вложенная папка '$name' (копия легла внутрь старой). Удалите её и обновите поверх: cp -r <новая>/. $dst/"
    return
  fi
  ln -s "$src" "$dst"; echo "LINKED $dst -> $src"
}
for name in "$@"; do
  src="$ROOT/skills/$name"
  link_one "$name" "$src"
  # вложенные скилы плагина (например, product-strategy/product-concept) — отдельными ссылками
  for sub in "$src"/*/; do
    [[ -f "${sub}SKILL.md" ]] && link_one "$(basename "$sub")" "${sub%/}"
  done
done
