#!/usr/bin/env bash
# Печатает команду Python 3 (python3 или python). Подключается через source.
if command -v python3 >/dev/null 2>&1; then PYTHON=python3
elif command -v python >/dev/null 2>&1 && python -c 'import sys; sys.exit(sys.version_info[0]!=3)'; then PYTHON=python
else echo "Ошибка: нужен Python 3" >&2; exit 1; fi
