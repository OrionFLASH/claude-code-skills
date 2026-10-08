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

# ---------- S-1: skill_dir.py ----------
SD="$S/skill_dir.py"
mkskill(){ mkdir -p "$1/scripts" "$1/.claude-plugin"; printf -- '---\nname: site-qa-audit\ndescription: x\n---\n' > "$1/SKILL.md"; : > "$1/scripts/url_guard.py"; printf '{"version": "%s"}' "$2" > "$1/.claude-plugin/plugin.json"; }
H1="$TMP/h1"; mkdir -p "$H1"
check "skill_dir: только рабочая копия -> dev-checkout с предупреждением" sh -c "
  HOME='$H1' SITE_QA_AUDIT_DIR= '$PY' '$SD' --json > '$TMP/sd0.json' &&
  '$PY' -c \"import json,sys; d=json.load(open(sys.argv[1])); assert d['source']=='dev-checkout' and any('рабочая копия' in w for w in d['warnings']), d\" '$TMP/sd0.json'"
mkskill "$H1/.claude/plugins/cache/claude-code-skills/site-qa-audit/1.9.0" 1.9.0
mkskill "$H1/.claude/plugins/cache/claude-code-skills/site-qa-audit/1.10.0" 1.10.0
check "skill_dir: кэш плагина, новейшая версия (1.10.0 > 1.9.0), путь рабочей копии не печатается" sh -c "
  out=\$(HOME='$H1' SITE_QA_AUDIT_DIR= '$PY' '$SD' 2>/dev/null) && test \"\$out\" = '$H1/.claude/plugins/cache/claude-code-skills/site-qa-audit/1.10.0'"
mkskill "$TMP/inst/site-qa-audit" 2.0.0
mkdir -p "$H1/.claude/plugins"
printf '{"version": 2, "plugins": {"site-qa-audit@claude-code-skills": [{"scope": "user", "installPath": "%s", "version": "2.0.0"}]}}' "$TMP/inst/site-qa-audit" > "$H1/.claude/plugins/installed_plugins.json"
check "skill_dir: installed_plugins.json -> installPath (source plugin)" sh -c "
  HOME='$H1' SITE_QA_AUDIT_DIR= '$PY' '$SD' --json | '$PY' -c \"import json,sys; d=json.load(sys.stdin); assert d['source']=='plugin' and d['version']=='2.0.0', d\""
mkskill "$TMP/custom" 3.0.0
check "skill_dir: SITE_QA_AUDIT_DIR главнее всего; --export" sh -c "
  HOME='$H1' SITE_QA_AUDIT_DIR='$TMP/custom' '$PY' '$SD' --export | grep -qx 'export SITE_QA_AUDIT_DIR=\"$TMP/custom\"'"
check "skill_dir: неверный SITE_QA_AUDIT_DIR -> предупреждение и следующий вариант" sh -c "
  HOME='$H1' SITE_QA_AUDIT_DIR='$TMP/nope' '$PY' '$SD' --json | '$PY' -c \"import json,sys; d=json.load(sys.stdin); assert d['source']=='plugin' and any('не подходит' in w for w in d['warnings']), d\""
mkskill "$TMP/copy/site-qa-audit" 1.3.0; cp "$SD" "$TMP/copy/site-qa-audit/scripts/skill_dir.py"
check "skill_dir: копия скила вне репозитория -> своя папка (self)" sh -c "
  HOME='$H1' SITE_QA_AUDIT_DIR= '$PY' '$TMP/copy/site-qa-audit/scripts/skill_dir.py' --json | '$PY' -c \"import json,sys; d=json.load(sys.stdin); assert d['source']=='self', d\""
check "skill_dir --check: есть -> 0; нет -> 1 и СТОП" sh -c "
  '$PY' '$SD' --check '$TMP/custom' | grep -q '^ok ' && out=\$('$PY' '$SD' --check '$TMP/nope'); test \$? = 1 && echo \"\$out\" | grep -q СТОП"
check "check_env --json: skill_dir и источник в env.json" sh -c "
  HOME='$H1' SITE_QA_AUDIT_DIR='$TMP/custom' '$PY' '$S/check_env.py' --fast --no-browsers --cdp-ports 1 --json '$TMP/env.json' >/dev/null 2>&1;
  '$PY' -c \"import json,sys; d=json.load(open(sys.argv[1])); assert d['skill_dir']=='$TMP/custom' and d['skill_dir_source']=='env', d.get('skill_dir')\" '$TMP/env.json'"
check "intake.py from-text: skill_dir в черновике run-config" sh -c "
  HOME='$H1' SITE_QA_AUDIT_DIR='$TMP/custom' '$PY' '$S/intake.py' from-text --text 'Протестируй https://example.com/' --json | '$PY' -c \"import json,sys; d=json.load(sys.stdin); assert d['config']['skill_dir']=='$TMP/custom', d['config'].get('skill_dir')\""

echo "stream v1.3.0: PASS $pass, FAIL $fail"; [ $fail -eq 0 ]
