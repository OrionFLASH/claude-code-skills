#!/usr/bin/env bash
# Browser tests of 1.3.0 scripts (targets.js, legal_guest.js, rtl.js, repro.js, invariants dialog, shot.js gutter,
# --locales). Local HTML fixtures only, served by `python3 -m http.server` on a free port; no real sites.
# The same server is reachable as 127.0.0.1 and as localhost — two hosts for first-/third-party checks.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if command -v python3 >/dev/null 2>&1; then PY=python3; else PY=python; fi
PORT="$("$PY" -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()')"
"$PY" -m http.server "$PORT" --bind 127.0.0.1 -d "$HERE/fixtures" >/dev/null 2>&1 &
SRV=$!
trap 'kill $SRV 2>/dev/null || true' EXIT
for _ in 1 2 3 4 5 6 7 8 9 10; do "$PY" -c "import urllib.request,sys; urllib.request.urlopen('http://127.0.0.1:$PORT/targets.html')" 2>/dev/null && break; sleep 0.3; done
export SITE_QA_HEADLESS="${SITE_QA_HEADLESS:-1}"
FIXTURE_BASE="http://127.0.0.1:$PORT" FIXTURE_PORT="$PORT" node "$HERE/v130.test.js" "$@"
