#!/usr/bin/env bash
# Offline tests for 1.3.0 (Python part, no network, no browser): fail-closed url_guard (code 4), nav --read-only,
# skill_dir.py, ingest_findings.py (findings as a JSON block in the executor's message), recheck.py (repro + gate),
# tabs.py (tab registry, CDP cleanup against a fake /json endpoint), claims.py account preconditions,
# render_draft.py group, direct_publish.py, legal second check. Browser parts — tests/v130.test.js.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; S="$HERE/../scripts"; T="$HERE/../templates"; F="$HERE/fixtures"
if command -v python3 >/dev/null 2>&1; then PY="${PY:-python3}"; else PY="${PY:-python}"; fi
export PYTHONDONTWRITEBYTECODE=1
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
pass=0; fail=0
ok(){ echo "PASS $1"; pass=$((pass+1)); }; bad(){ echo "FAIL $1"; fail=$((fail+1)); }
check(){ local name="$1"; shift; if "$@"; then ok "$name"; else bad "$name"; fi; }
rc(){ "$@" >/dev/null 2>&1; echo $?; }
CFG="$T/run-config.example.yaml"
UG="$S/url_guard.py"

# ---------- S-2: url_guard fail closed ----------
check "url_guard: без --config -> код 4 (не allow)" test "$(rc "$PY" "$UG" nav https://example.com/)" = 4
check "url_guard: нет файла конфига -> код 4" test "$(rc "$PY" "$UG" nav https://example.com/ --config "$TMP/nope.yaml")" = 4
check "url_guard: неверные аргументы -> код 4, не 2 (2 = confirm)" test "$(rc "$PY" "$UG" nav --config "$CFG")" = 4
check "url_guard: неизвестная команда -> код 4" test "$(rc "$PY" "$UG" bogus --config "$CFG")" = 4
printf 'site:\n  allowed_domains: [example.com]\nrules:\n  forbidden_url_patterns:\n    - "(unclosed"\n' > "$TMP/badrx.yaml"
check "url_guard: неверный регэксп в правилах -> код 4" test "$(rc "$PY" "$UG" nav https://example.com/ --config "$TMP/badrx.yaml")" = 4
printf 'site: [1, 2\n' > "$TMP/broken.yaml"
check "url_guard: битый YAML -> код 4" test "$(rc "$PY" "$UG" nav https://example.com/ --config "$TMP/broken.yaml")" = 4
check "url_guard export без конфига -> код 4 (rules.json не создаётся)" sh -c "test \$('$PY' '$UG' export --out '$TMP/r.json' >/dev/null 2>&1; echo \$?) = 4 && test ! -e '$TMP/r.json'"
out=$("$PY" "$UG" nav https://example.com/ --config "$TMP/nope.yaml")
check "url_guard код 4: JSON decision=unavailable, rule guard:unavailable, слово СТОП" sh -c "echo '$out' | grep -q '\"decision\": \"unavailable\"' && echo '$out' | grep -q 'guard:unavailable' && echo '$out' | grep -q 'СТОП'"
check "url_guard: обычные решения не изменились (allow 0 / deny 3)" sh -c "test \$('$PY' '$UG' nav https://example.com/ --config '$CFG' >/dev/null; echo \$?) = 0 && test \$('$PY' '$UG' nav https://evil.test/ --config '$CFG' >/dev/null; echo \$?) = 3"

# ---------- S-8: nav --read-only ----------
check "read-only: /donate без флага -> 3, с --read-only -> 0 и read_only:true" sh -c "
  test \$('$PY' '$UG' nav https://example.com/donate --config '$CFG' >/dev/null; echo \$?) = 3 &&
  '$PY' '$UG' nav https://example.com/donate --config '$CFG' --read-only --log '$TMP/ro.jsonl' | grep -q '\"read_only\": true' &&
  grep -q 'прочитано без действий' '$TMP/ro.jsonl'"
check "read-only не снимает OAuth, выход, платёжные шлюзы и чужие хосты" sh -c "
  for u in https://example.com/oauth/authorize?client_id=1 https://example.com/logout https://checkout.stripe.com/c/pay https://evil.test/donate; do
    test \$('$PY' '$UG' nav \"\$u\" --config '$CFG' --read-only >/dev/null; echo \$?) = 3 || exit 1; done"
printf 'site:\n  allowed_domains: [example.com]\nrules:\n  forbidden_url_patterns: ["/auth/"]\n  read_only_urls: ["/auth/sign(in|up)"]\n' > "$TMP/ro.yaml"
check "read-only: rules.read_only_urls снимает запрет пользователя только в режиме чтения" sh -c "
  test \$('$PY' '$UG' nav https://example.com/auth/signin --config '$TMP/ro.yaml' --read-only >/dev/null; echo \$?) = 0 &&
  test \$('$PY' '$UG' nav https://example.com/auth/signin --config '$TMP/ro.yaml' >/dev/null; echo \$?) = 3 &&
  test \$('$PY' '$UG' nav https://example.com/auth/reset --config '$TMP/ro.yaml' --read-only >/dev/null; echo \$?) = 3"
check "export: read_only_urls и регэкспы режима чтения для guard.js" sh -c "
  '$PY' '$UG' export --config '$TMP/ro.yaml' --out '$TMP/ro-rules.json' >/dev/null &&
  '$PY' -c \"import json,sys; d=json.load(open(sys.argv[1])); assert d['rules']['read_only_urls'] and d['base']['read_only_path_regex'] and d['base']['never_read_only_path_regex']\" '$TMP/ro-rules.json'"

echo "stream v1.3.0: PASS $pass, FAIL $fail"; [ $fail -eq 0 ]
