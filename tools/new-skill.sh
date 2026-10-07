#!/usr/bin/env bash
# Обёртка над tools/lib/skillsrepo.py (new). См. README.md.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT/shared/scripts/find-python.sh"
exec "$PYTHON" "$ROOT/tools/lib/skillsrepo.py" new "$@"
