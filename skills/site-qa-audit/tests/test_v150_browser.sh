#!/usr/bin/env bash
# Browser tests of 1.5.0: tab registry of node scripts (file:// and a CDP stand-in for the user's browser), reachability
# in WebKit (touch model), e2e stubs under Playwright Test (e2e_run.js), a separate Playwright MCP with the guard of the
# run (browser_mode.py mcp --check). Local fixtures only; Lighthouse uses `python3 -m http.server` on a free port.
# QA_HEADED=1 — also the visible-window test (opens and closes real browser windows; temporary profiles only).
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if command -v python3 >/dev/null 2>&1; then PY="${PY:-python3}"; else PY="${PY:-python}"; fi
PORT="$("$PY" -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()')"
"$PY" -m http.server "$PORT" --bind 127.0.0.1 -d "$HERE/fixtures" >/dev/null 2>&1 &
SRV=$!
trap 'kill $SRV 2>/dev/null || true' EXIT
for _ in 1 2 3 4 5 6 7 8 9 10; do "$PY" -c "import urllib.request,sys; urllib.request.urlopen('http://127.0.0.1:$PORT/targets.html')" 2>/dev/null && break; sleep 0.3; done
export SITE_QA_HEADLESS="${SITE_QA_HEADLESS:-1}"
FIXTURE_BASE="http://127.0.0.1:$PORT" PY="$PY" node "$HERE/v150.test.js" "$@"
