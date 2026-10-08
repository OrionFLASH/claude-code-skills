#!/usr/bin/env bash
# Browser tests of stream B scripts (guard, occlusion, reachability, device_context, invariants, shot, frames).
# Local HTML fixtures only (tests/fixtures/*.html) served by `python3 -m http.server` on a free port; no real sites.
# Requires: cd scripts/node && npm install (Playwright Chromium; WebKit is optional and reported as SKIP).
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if command -v python3 >/dev/null 2>&1; then PY=python3; else PY=python; fi
PORT="$("$PY" -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()')"
"$PY" -m http.server "$PORT" --bind 127.0.0.1 -d "$HERE/fixtures" >/dev/null 2>&1 &
SRV=$!
trap 'kill $SRV 2>/dev/null || true' EXIT
for _ in 1 2 3 4 5 6 7 8 9 10; do "$PY" -c "import urllib.request,sys; urllib.request.urlopen('http://127.0.0.1:$PORT/guard-actions.html')" 2>/dev/null && break; sleep 0.3; done
FIXTURE_BASE="http://127.0.0.1:$PORT" node "$HERE/stream_b.test.js" "$@"
