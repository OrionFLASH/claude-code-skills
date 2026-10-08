#!/usr/bin/env bash
# Tests for the `screenshots: web-upload` strategy (publish_web.mjs, comment_web.mjs).
# Fully offline: local fixtures via `python3 -m http.server`, a headless Chromium with a CDP port
# instead of the user's browser, and tests/helpers/fake_gh.py instead of the gh CLI.
# Nothing here talks to github.com. Exit code != 0 if any test fails.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
N="$HERE/../scripts/node"; F="$HERE/fixtures"; H="$HERE/helpers"
if command -v python3 >/dev/null 2>&1; then PY=python3; else PY=python; fi
TMP="$(mktemp -d)"
HTTP_PORT="${QA_TEST_HTTP_PORT:-8765}"; CDP_PORT="${QA_TEST_CDP_PORT:-9339}"
BASE="${QA_TEST_BASE_URL:-http://127.0.0.1:$HTTP_PORT}"
SRV_LOG="$TMP/server.log"; STATE="$TMP/gh-state.json"
cleanup(){ [ -n "${SRV:-}" ] && kill "$SRV" 2>/dev/null; [ -n "${BRW:-}" ] && kill "$BRW" 2>/dev/null; wait 2>/dev/null; rm -rf "$TMP"; }
trap cleanup EXIT
pass=0; fail=0
ok(){ echo "PASS $1"; pass=$((pass+1)); }; bad(){ echo "FAIL $1"; fail=$((fail+1)); }
check(){ local name="$1"; shift; if "$@"; then ok "$name"; else bad "$name"; fi; }

export QA_GH_BIN="$H/fake_gh.py" FAKE_GH_STATE="$STATE" FAKE_GH_SERVER_LOG="$SRV_LOG"
EMPTY_STATE='{"issues":{}}'
reset_state(){ printf '%s' "${1:-$EMPTY_STATE}" > "$STATE"; : > "$SRV_LOG"; }
clicks(){ grep -c "__event?.*type=click.*button=$1\|__event?.*button=$1.*type=click" "$SRV_LOG" || true; }
anyclick(){ grep -c "__event?.*type=click" "$SRV_LOG" || true; }
calls_with(){ "$PY" -c "import json,sys; c=json.load(open(sys.argv[1])).get('calls',[]); print(sum(1 for x in c if x[:2]==sys.argv[2].split()))" "$STATE" "$1"; }
body_of(){ "$PY" -c "import json,sys; print(json.load(open(sys.argv[1]))['issues'][sys.argv[2]]['body'])" "$STATE" "$1"; }

# shots + bodies
"$PY" -c "
import base64,sys
png=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==')
for n in ('F-001-menu-annotated.png','F-001-menu.png'): open(sys.argv[1]+'/'+n,'wb').write(png)
" "$TMP"
S1="$TMP/F-001-menu-annotated.png"; S2="$TMP/F-001-menu.png"
printf '### Steps\n1. Open the menu\n\n![F-001-menu-annotated](../screenshots/F-001-menu-annotated.png)\n\n<!-- site-qa-audit:fp=abc123 -->\n' > "$TMP/issue.md"
printf 'Fix is insufficient: the menu still overlaps.\n\n{{qa-shot:F-001-menu-annotated.png}}\n' > "$TMP/comment.md"

# ---------- dry-run (no browser, no gh) ----------
reset_state
out=$(node "$N/publish_web.mjs" --repo owner/repo --title "T" --body-file "$TMP/issue.md" --shot "$S1" --cdp http://127.0.0.1:1 2>"$TMP/err")
c=$?
check "publish dry-run: exit 0, plan printed" test $c -eq 0
check "publish dry-run: nothing called in gh" test "$(calls_with 'issue create')" -eq 0
check "publish dry-run: placeholder replaces local image link" bash -c "grep -q 'qa-shot:F-001-menu-annotated.png' <<<'$out' && ! grep -q '../screenshots' <<<'$out'"
grep -q "dry-run" "$TMP/err" && ok "publish dry-run: message in Russian about --confirm-publish" || bad "publish dry-run message"

out=$(node "$N/comment_web.mjs" --repo owner/repo --number 7 --body-file "$TMP/comment.md" --shot "$S1" --cdp http://127.0.0.1:1 2>/dev/null); c=$?
check "comment dry-run: exit 0, no gh calls" bash -c "[ $c -eq 0 ] && [ \$(python3 -c \"import json;print(len(json.load(open('$STATE')).get('calls',[])))\") -eq 0 ]"

# negative usage checks (no browser needed)
node "$N/publish_web.mjs" --repo "bad repo" --title T --body-file "$TMP/issue.md" --shot "$S1" >/dev/null 2>&1; c=$?
check "publish: invalid --repo -> exit 1" test $c -eq 1
node "$N/publish_web.mjs" --repo o/r --title T --body-file "$TMP/issue.md" --shot "$TMP/missing.png" >/dev/null 2>&1; c=$?
check "publish: missing screenshot -> exit 1" test $c -eq 1
node "$N/comment_web.mjs" --repo o/r --number 3 --body-file "$TMP/comment.md" --shot "$S1" --base-url "$BASE" \
  --issue-url-template "http://evil.test/{repo}/issues/{number}" >/dev/null 2>&1; c=$?
check "comment: issue URL outside base host -> exit 3 (even in dry-run)" test $c -eq 3

# verify-only negative: placeholder left in the body
reset_state '{"issues":{"5":{"number":5,"state":"open","body":"text {{qa-shot:a.png}}","comments":[]}}}'
node "$N/publish_web.mjs" --verify-only --repo o/r --number 5 --expect 1 >/dev/null 2>&1; c=$?
check "verify-only: placeholder left -> exit 5" test $c -eq 5
reset_state '{"issues":{"5":{"number":5,"state":"open","body":"text <img src=\"https://github.com/user-attachments/assets/0f8e2d9a-1111-2222-3333-444455556666\" />","comments":[]}}}'
node "$N/publish_web.mjs" --verify-only --repo o/r --number 5 --expect 1 >/dev/null 2>&1; c=$?
check "verify-only: attachment, no placeholder -> exit 0" test $c -eq 0
reset_state '{"issues":{"5":{"number":5,"state":"closed","body":"x","comments":[{"id":1,"body":"see {{qa-shot:a.png}} <!-- site-qa-audit:web=n1 -->"}]}}}'
node "$N/comment_web.mjs" --verify-only --repo o/r --number 5 --nonce n1 --expect 1 >/dev/null 2>&1; c=$?
check "comment verify-only: placeholder left in comment -> exit 5" test $c -eq 5

# ---------- browser tests ----------
( cd "$F" && exec "$PY" -m http.server "$HTTP_PORT" --bind 127.0.0.1 ) >"$SRV_LOG.boot" 2>"$SRV_LOG" & SRV=$!
node "$H/cdp_browser.mjs" "$CDP_PORT" >"$TMP/brw.out" 2>&1 & BRW=$!
for i in $(seq 1 60); do grep -q ready "$TMP/brw.out" 2>/dev/null && curl -s "$BASE/gh-new-issue.html" >/dev/null 2>&1 && break; sleep 0.25; done
if ! grep -q ready "$TMP/brw.out"; then echo "FAIL browser did not start: $(cat "$TMP/brw.out")"; exit 1; fi
CDP="http://127.0.0.1:$CDP_PORT"
COMMON=(--cdp "$CDP" --base-url "$BASE" --throttle 100 --confirm-publish)

# publish: positive (2 shots, button + file chooser path)
reset_state
node "$N/publish_web.mjs" --repo owner/repo --title "Menu overlaps" --body-file "$TMP/issue.md" --shot "$S1" --shot "$S2" "${COMMON[@]}" \
  --login-url-template "{base}/gh-new-issue.html?n=0" --issue-url-template "{base}/gh-new-issue.html?n={number}" \
  --out "$TMP/pub.json" >/dev/null 2>"$TMP/err"; c=$?
B="$(body_of 1 2>/dev/null)"
check "publish: exit 0 and API verification ok" test $c -eq 0
check "publish: body has 2 attachments, no placeholders" bash -c "[ \$(grep -o 'user-attachments/assets/' <<<'$B' | wc -l) -eq 2 ] && ! grep -q 'qa-shot:' <<<'$B'"
check "publish: fingerprint marker kept last" bash -c "tail -n1 <<<'$B' | grep -q 'site-qa-audit:fp=abc123'"
check "publish: no button on the issue page was clicked (no close/comment)" test "$(anyclick)" -eq 0
check "publish: issue created once, edited once" bash -c "[ $(calls_with 'issue create') -eq 1 ] && [ $(calls_with 'issue edit') -eq 1 ]"

# publish: fallback upload path (no attach button, input[type=file] only)
reset_state
node "$N/publish_web.mjs" --repo owner/repo --title "T" --body-file "$TMP/issue.md" --shot "$S1" "${COMMON[@]}" \
  --login-url-template "{base}/gh-new-issue.html?n=0" --issue-url-template "{base}/gh-new-issue.html?n={number}&attach=input" >/dev/null 2>&1; c=$?
check "publish: fallback to input[type=file] works" test $c -eq 0

# publish: not logged in -> stop before creating anything
reset_state
node "$N/publish_web.mjs" --repo owner/repo --title "T" --body-file "$TMP/issue.md" --shot "$S1" "${COMMON[@]}" \
  --login-url-template "{base}/gh-new-issue.html?n=0&loggedout=1" --issue-url-template "{base}/gh-new-issue.html?n={number}" >/dev/null 2>"$TMP/err"; c=$?
check "publish: no login -> exit 4" test $c -eq 4
check "publish: no login -> Russian message «Нужен вход на GitHub в окне аудита»" grep -q "Нужен вход на GitHub в окне аудита" "$TMP/err"
check "publish: no login -> no issue created" test "$(calls_with 'issue create')" -eq 0

# publish: upload never finishes -> stop, placeholder stays, verification fails
reset_state
node "$N/publish_web.mjs" --repo owner/repo --title "T" --body-file "$TMP/issue.md" --shot "$S1" "${COMMON[@]}" --upload-timeout 2500 \
  --login-url-template "{base}/gh-new-issue.html?n=0" --issue-url-template "{base}/gh-new-issue.html?n={number}&upload=fail" >/dev/null 2>"$TMP/err"; c=$?
check "publish: upload timeout -> exit 7" test $c -eq 7
check "publish: upload timeout -> body not edited, placeholder remains" bash -c "[ $(calls_with 'issue edit') -eq 0 ] && grep -q 'qa-shot:' <<<\"\$(python3 -c \"import json;print(json.load(open('$STATE'))['issues']['1']['body'])\")\""
node "$N/publish_web.mjs" --verify-only --repo owner/repo --number 1 --expect 1 >/dev/null 2>&1; c=$?
check "publish: placeholder left -> verify-only fails (exit 5)" test $c -eq 5

# comment: positive on a closed issue
reset_state '{"issues":{"7":{"number":7,"state":"closed","body":"old","comments":[]}}}'
node "$N/comment_web.mjs" --repo owner/repo --number 7 --body-file "$TMP/comment.md" --shot "$S1" "${COMMON[@]}" \
  --issue-url-template "{base}/gh-closed-issue.html?n={number}" --out "$TMP/com.json" >/dev/null 2>"$TMP/err"; c=$?
check "comment: exit 0 and API verification ok" test $c -eq 0
check "comment: exactly one «Comment» click" test "$(clicks comment)" -eq 1
check "comment: «Reopen» never clicked" test "$(clicks reopen)" -eq 0
check "comment: «Close» never clicked" bash -c "[ $(clicks close) -eq 0 ] && [ $(clicks decoy-close) -eq 0 ]"
check "comment: issue still closed (state_after)" grep -q '"state_after": "closed"' "$TMP/com.json"

# comment: decoy button with aria-label "Comment" but text "Close with comment" placed before the real one
reset_state '{"issues":{"7":{"number":7,"state":"closed","body":"old","comments":[]}}}'
node "$N/comment_web.mjs" --repo owner/repo --number 7 --body-file "$TMP/comment.md" --shot "$S1" "${COMMON[@]}" \
  --issue-url-template "{base}/gh-closed-issue.html?n={number}&decoy=1" >/dev/null 2>&1; c=$?
check "comment+decoy: exit 0, decoy «Close with comment» not clicked" bash -c "[ $c -eq 0 ] && [ $(clicks decoy-close) -eq 0 ] && [ $(clicks comment) -eq 1 ]"

# comment: no «Comment» button at all -> safety stop, nothing clicked
reset_state '{"issues":{"7":{"number":7,"state":"closed","body":"old","comments":[]}}}'
node "$N/comment_web.mjs" --repo owner/repo --number 7 --body-file "$TMP/comment.md" --shot "$S1" "${COMMON[@]}" \
  --issue-url-template "{base}/gh-closed-issue.html?n={number}&nocomment=1" >/dev/null 2>"$TMP/err"; c=$?
check "comment: no «Comment» button -> exit 6, no clicks (Reopen untouched)" bash -c "[ $c -eq 6 ] && [ $(anyclick) -eq 0 ]"

# comment: not logged in
reset_state '{"issues":{"7":{"number":7,"state":"closed","body":"old","comments":[]}}}'
node "$N/comment_web.mjs" --repo owner/repo --number 7 --body-file "$TMP/comment.md" --shot "$S1" "${COMMON[@]}" \
  --issue-url-template "{base}/gh-closed-issue.html?n={number}&loggedout=1" >/dev/null 2>"$TMP/err"; c=$?
check "comment: no login -> exit 4, Russian message, no clicks" bash -c "[ $c -eq 4 ] && grep -q 'Нужен вход на GitHub' '$TMP/err' && [ $(anyclick) -eq 0 ]"

# comment: upload returns a link without URL -> placeholder would stay -> stop before clicking
reset_state '{"issues":{"7":{"number":7,"state":"closed","body":"old","comments":[]}}}'
node "$N/comment_web.mjs" --repo owner/repo --number 7 --body-file "$TMP/comment.md" --shot "$S1" "${COMMON[@]}" --upload-timeout 2500 \
  --issue-url-template "{base}/gh-closed-issue.html?n={number}&upload=broken" >/dev/null 2>"$TMP/err"; c=$?
check "comment: broken upload -> non-zero exit, nothing clicked" bash -c "[ $c -ne 0 ] && [ $(anyclick) -eq 0 ]"

# static guard: the code refuses Close/Reopen explicitly
check "code: explicit Close/Reopen ban present" grep -q "FORBIDDEN_BUTTON_RE.test" "$N/web_upload_lib.mjs"
check "code: no <form> / comment[body] dependency in live selectors" bash -c "! grep -n \"locator('form\" '$N/web_upload_lib.mjs'"

echo "---"; echo "passed: $pass, failed: $fail"
[ "$fail" -eq 0 ]
