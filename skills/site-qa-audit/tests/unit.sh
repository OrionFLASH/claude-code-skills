#!/usr/bin/env bash
# Офлайн-проверки скриптов site-qa-audit (без сети и браузера). Код выхода != 0 при ошибке.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; S="$HERE/../scripts"; F="$HERE/fixtures"
if command -v python3 >/dev/null 2>&1; then PY=python3; else PY=python; fi
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
pass=0; fail=0
ok(){ echo "PASS $1"; pass=$((pass+1)); }; bad(){ echo "FAIL $1"; fail=$((fail+1)); }

"$PY" "$S/url_guard.py" selftest >/dev/null && ok "url_guard selftest" || bad "url_guard selftest"

"$PY" "$S/shared/miniyaml.py" "$HERE/../templates/run-config.example.yaml" > "$TMP/rc.json" \
  && "$PY" -c "import json,sys; d=json.load(open(sys.argv[1])); assert d['site']['allowed_domains'] and d['depth']=='smoke'" "$TMP/rc.json" \
  && ok "miniyaml: run-config.example.yaml" || bad "miniyaml: run-config.example.yaml"

"$PY" "$S/url_guard.py" export --config "$HERE/../templates/run-config.example.yaml" --out "$TMP/rules.json" >/dev/null \
  && ok "url_guard export" || bad "url_guard export"
set +e; "$PY" "$S/url_guard.py" nav https://evil.test/ --config "$HERE/../templates/run-config.example.yaml" >/dev/null; c=$?; set -e
[ $c -eq 3 ] && ok "url_guard nav outside allowlist -> deny" || bad "url_guard nav outside allowlist ($c)"

cp "$F/findings.json" "$TMP/f.json"
"$PY" "$S/fingerprint.py" compute "$TMP/f.json" >/dev/null
"$PY" "$S/fingerprint.py" dedupe "$TMP/f.json" >/dev/null
"$PY" -c "
import json,sys; d=json.load(open(sys.argv[1])); f=d['findings']
assert len(f)==2, len(f)
m=[x for x in f if x['check_id']=='a11y.axe.color-contrast'][0]
assert m['severity']=='high' and 'F-002' in m['merged_ids'], m
" "$TMP/f.json" && ok "fingerprint dedupe (одинаковый fp для /items/42?x=1 и /items/7)" || bad "fingerprint dedupe"

FP=$("$PY" -c "import json,sys; print([x for x in json.load(open(sys.argv[1]))['findings'] if x['check_id'].startswith('a11y')][0]['fingerprint'])" "$TMP/f.json")
sed "s/FPPLACEHOLDER/$FP/" "$F/registry.json" > "$TMP/reg.json"
"$PY" "$S/fingerprint.py" match "$TMP/f.json" "$TMP/reg.json" --out "$TMP/m.json" >/dev/null
"$PY" -c "
import json,sys; m={r['id']:r for r in json.load(open(sys.argv[1]))}
assert m['F-001']['exact'][0]['number']==5
assert any(c['number']==9 for c in m['F-003']['candidates']), m['F-003']
" "$TMP/m.json" && ok "fingerprint match (маркер + нечёткий кандидат)" || bad "fingerprint match"

"$PY" "$S/render_draft.py" detailed "$TMP/f.json" --id F-001 --out "$TMP/d.md" >/dev/null
grep -q "^TITLE: \[HIGH\]" "$TMP/d.md" && grep -q "site-qa-audit:fp=$FP" "$TMP/d.md" && ! grep -q "{{" "$TMP/d.md" \
  && ! grep -q "admin@acme-corp.test" "$TMP/d.md" && ok "render_draft detailed (маркер, маскирование, без плейсхолдеров)" || bad "render_draft detailed"

"$PY" "$S/read_templates.py" parse "$F/bug-form.yml" > "$TMP/t.json"
echo '{"title":"Кнопка не работает","url":"https://example.com","steps":"1. Открыть","browser":"Safari"}' > "$TMP/v.json"
"$PY" -c "import json,sys; t=json.load(open(sys.argv[1])); json.dump({'templates':t},open(sys.argv[1],'w'))" "$TMP/t.json"
"$PY" "$S/read_templates.py" render "$TMP/t.json" --template "Bug report" --values "$TMP/v.json" > "$TMP/r.json"
"$PY" -c "
import json,sys; r=json.load(open(sys.argv[1]))
assert r['title']=='[Bug]: Кнопка не работает', r['title']
assert '### Page URL\n\nhttps://example.com' in r['body'] and '\`\`\`text' in r['body'] and r['labels']==['bug','triage']
" "$TMP/r.json" && ok "read_templates parse+render (issue form)" || bad "read_templates render"

"$PY" "$S/validate_findings.py" "$TMP/f.json" >/dev/null && ok "validate_findings: валидный файл" || bad "validate_findings: валидный файл"
"$PY" -c "import json,sys; d=json.load(open(sys.argv[1])); d['findings'][0]['severity']='urgent'; json.dump(d,open(sys.argv[2],'w'))" "$TMP/f.json" "$TMP/bad.json"
set +e; "$PY" "$S/validate_findings.py" "$TMP/bad.json" >/dev/null; c=$?; set -e
[ $c -eq 1 ] && ok "validate_findings: ловит неверный enum" || bad "validate_findings: неверный enum ($c)"

set +e; "$PY" "$S/url_guard.py" action --text "×" --name Delete --context "todos" --config "$F/dry-run-todomvc.run-config.yaml" >/dev/null; c=$?
"$PY" "$S/url_guard.py" action --text "×" --name Delete --context "todos" --config "$HERE/../templates/run-config.example.yaml" >/dev/null; c2=$?; set -e
[ $c -eq 0 ] && [ $c2 -eq 2 ] && ok "url_guard: иконка удаления confirm, с preapproved — allow" || bad "url_guard preapproved ($c/$c2)"

node -e "const s=require('fs').readFileSync(process.argv[1],'utf8').replace('__ALLOWED_RE__','^https://example\\.com/?(#.*)?$'); const f=new Function('return ('+s.replace(/^\s*\/\/.*$/mg,'')+')')(); if (typeof f!=='function') process.exit(1)" "$S/nav_lock.js" && ok "nav_lock.js: синтаксис" || bad "nav_lock.js: синтаксис"

# 1.1.0: syntax of new scripts (no browser, no network)
for f in claims intake journal build_report gitignore_helper export_results shared/qa_gitignore shared/qa_export; do
  "$PY" -c "import ast,sys; ast.parse(open(sys.argv[1],encoding='utf-8').read(), sys.argv[1])" "$S/$f.py" 2>"$TMP/pyc.err" \
    && ok "syntax $f.py" || { cat "$TMP/pyc.err"; bad "syntax $f.py"; }
done
for f in guard invariants occlusion reachability device_context shot frames annotate; do
  node --check "$S/node/$f.js" && ok "node --check $f.js" || bad "node --check $f.js"
done
for f in publish_web comment_web web_upload_lib; do
  node --check "$S/node/$f.mjs" && ok "node --check $f.mjs" || bad "node --check $f.mjs"
done
for f in snap_cdp snap_mcp; do
  node --check "$S/$f.js" && ok "node --check $f.js" || bad "node --check $f.js"
done

"$PY" "$S/shared/miniyaml.py" "$F/side-effects.run-config.yaml" > "$TMP/se.json" \
  && "$PY" -c "import json,sys; d=json.load(open(sys.argv[1])); assert d['invariants'][0]['require']['state']=='checked'" "$TMP/se.json" \
  && ok "miniyaml: side_effects/invariants" || bad "miniyaml: side_effects/invariants"
"$PY" -c "
import json,sys; d=json.load(open(sys.argv[1]))
assert d['auth']['mode']=='none' and d['auth']['cdp_url'].startswith('http://127.0.0.1')
assert d['frames']=='main' and d['side_effects']==[] and d['invariants']==[] and d['devices']['emulate']==[]
assert 'content-i18n' not in d['directions'] and d['auth']['account_states']==[]
" "$TMP/rc.json" && ok "run-config.example.yaml: разделы 1.1.0" || bad "run-config.example.yaml: разделы 1.1.0"

# Stream A (Python: claims, schema, render_draft, intake, journal, build_report, read_templates, check_env)
REAL_REGISTRY="${REAL_REGISTRY:-}" REAL_FINDINGS="${REAL_FINDINGS:-}" bash "$HERE/test_stream_a.sh" > "$TMP/stream-a.log" 2>&1 \
  && ok "stream A ($(tail -1 "$TMP/stream-a.log"))" || { cat "$TMP/stream-a.log"; bad "stream A"; }

# 1.2.0: gitignore_helper (qa-runs/ and git), parallel.max_workers <= 4, run-config goal/context/report_destinations,
# build_report summary, templates/site-context.md
bash "$HERE/test_v12.sh" > "$TMP/v12.log" 2>&1 \
  && ok "v1.2 ($(tail -1 "$TMP/v12.log"))" || { cat "$TMP/v12.log"; bad "v1.2"; }

# 1.2.1: qa-runs/ in .gitignore by default (ensure/untrack), git.allow_commit_results in intake, export_results.py
bash "$HERE/test_v121.sh" > "$TMP/v121.log" 2>&1 \
  && ok "v1.2.1 ($(tail -1 "$TMP/v121.log"))" || { cat "$TMP/v121.log"; bad "v1.2.1"; }

# Browser suites B and C: need node + scripts/node/node_modules/playwright + Chromium; otherwise SKIP.
# Set QA_SKIP_BROWSER=1 to skip them explicitly.
have_browser=0
if [ "${QA_SKIP_BROWSER:-0}" != "1" ] && command -v node >/dev/null 2>&1 && [ -d "$S/node/node_modules/playwright" ]; then
  (cd "$S/node" && node -e "const fs=require('fs');const p=require('playwright').chromium.executablePath();process.exit(p&&fs.existsSync(p)?0:1)") 2>/dev/null && have_browser=1
fi
if [ $have_browser -eq 1 ]; then
  bash "$HERE/test_stream_b.sh" > "$TMP/stream-b.log" 2>&1 \
    && ok "stream B browser ($(grep '^stream B:' "$TMP/stream-b.log" | tail -1))" || { tail -n 30 "$TMP/stream-b.log"; bad "stream B browser"; }
  bash "$HERE/test_stream_c.sh" > "$TMP/stream-c.log" 2>&1 \
    && ok "stream C web-upload ($(grep '^passed:' "$TMP/stream-c.log" | tail -1))" || { tail -n 30 "$TMP/stream-c.log"; bad "stream C web-upload"; }
else
  echo "SKIP stream B/C: нет node, playwright (cd scripts/node && npm install) или Chromium (npx playwright install chromium)"
fi

echo "unit: PASS $pass, FAIL $fail"; [ $fail -eq 0 ]
