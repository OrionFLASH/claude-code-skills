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

echo "unit: PASS $pass, FAIL $fail"; [ $fail -eq 0 ]
