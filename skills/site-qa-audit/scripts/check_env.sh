#!/usr/bin/env bash
# Проверка окружения site-qa-audit. Аргументы передаются в check_env.py (--fast, --json FILE, --no-browsers).
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if command -v python3 >/dev/null 2>&1; then PY=python3; else PY=python; fi
exec "$PY" "$HERE/check_env.py" "$@"
