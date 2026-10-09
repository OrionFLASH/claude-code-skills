#!/usr/bin/env bash
# Browser tests of 1.4.0 on local files (file://): detectors, guard of local roots, links.js, browser mode.
# No server and no network: the fixture app (tests/fixtures/local-app) is copied to a temp folder and opened as file://.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if command -v python3 >/dev/null 2>&1; then PY="${PY:-python3}"; else PY="${PY:-python}"; fi
export SITE_QA_HEADLESS="${SITE_QA_HEADLESS:-1}"
PY="$PY" node "$HERE/v140.test.js" "$@"
