#!/usr/bin/env bash
# Offline tests for claims.py, intake.py, journal.py, build_report.py, render_draft.py (disclosure/links/marker),
# read_templates.py (fetch docs, --format), check_env.py (browser tools), schema 1.1 (validate_findings.py).
# Positive and negative case per command. No network, no browser.
# Optional real data (not committed): REAL_REGISTRY=<registry.json> REAL_FINDINGS=<findings.json>.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; S="$HERE/../scripts"; F="$HERE/fixtures"
if command -v python3 >/dev/null 2>&1; then PY=python3; else PY=python; fi
export PYTHONDONTWRITEBYTECODE=1
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
pass=0; fail=0
ok(){ echo "PASS $1"; pass=$((pass+1)); }; bad(){ echo "FAIL $1"; fail=$((fail+1)); }
check(){ local name="$1"; shift; if "$@"; then ok "$name"; else bad "$name"; fi; }
rc(){ "$@" >/dev/null 2>&1; echo $?; }

# claims.py
"$PY" "$S/claims.py" extract "$F/registry-claims.json" --repo owner/repo --out "$TMP/claims.json" >/dev/null
check "claims extract: 48 issues с fix_claimed, у каждого цитата" "$PY" -c "
import json,sys; c=json.load(open(sys.argv[1]))['claims']
assert len(c)==48, len(c); assert all(x['quote'] for x in c)
assert any(x['claim_kind']=='partial' for x in c) and any(x['version'] for x in c)
" "$TMP/claims.json"
check "claims extract: битый реестр -> код 2" test "$(echo '{' > "$TMP/broken.json"; rc "$PY" "$S/claims.py" extract "$TMP/broken.json")" = 2
"$PY" "$S/claims.py" plan "$TMP/claims.json" --site https://example.com/ --out "$TMP/plan.md" --json "$TMP/rechecks.json" >/dev/null
check "claims plan: >=40 пунктов, у каждого цитата, URL из текста в плане" "$PY" -c "
import json,re,sys
plan=open(sys.argv[1]).read(); items=re.split(r'^## \d+\. ', plan, flags=re.M)[1:]
items=[i for i in items if not i.startswith('Пропущено')]
assert len(items)>=40, len(items)
assert all('\n  > ' in i for i in items), 'нет цитаты'
claims={c['number']:c for c in json.load(open(sys.argv[2]))['claims']}
for i in items:
    n=int(re.match(r'owner/repo#(\d+)', i).group(1)); c=claims[n]
    if c['urls'] or c['paths']: assert '- Где:' in i, n
r=json.load(open(sys.argv[3]))['rechecks']; assert len(r)==len(items) and all(x['quote'] for x in r)
" "$TMP/plan.md" "$TMP/claims.json" "$TMP/rechecks.json"
echo '{"issues":[{"repo":"owner/repo","number":1,"title":"t","state":"open","fix_claimed":false,"body":"","comments":[]}]}' > "$TMP/noclaim.json"
check "claims plan: нет заявлений -> код 1" test "$(rc "$PY" "$S/claims.py" plan "$TMP/noclaim.json")" = 1
check "claims set: FIXED-INSUFFICIENT записан" "$PY" "$S/claims.py" set "$TMP/rechecks.json" --number 51 --status FIXED-INSUFFICIENT --by "Chrome, /lab" --finding F-003
check "claims set: NOT-CHECKED без причины -> код 2" test "$(rc "$PY" "$S/claims.py" set "$TMP/rechecks.json" --number 14 --status NOT-CHECKED)" = 2
if [ -n "${REAL_REGISTRY:-}" ] && [ -f "$REAL_REGISTRY" ]; then
  repo=$("$PY" -c "import json,sys; d=json.load(open(sys.argv[1])); print([i['repo'] for i in d['issues'] if i.get('fix_claimed')][0])" "$REAL_REGISTRY")
  "$PY" "$S/claims.py" extract "$REAL_REGISTRY" --repo "$repo" --out "$TMP/real-claims.json" >/dev/null
  "$PY" "$S/claims.py" plan "$TMP/real-claims.json" --out "$TMP/real-plan.md" >/dev/null
  check "claims на реальном реестре: >=40 пунктов с цитатой" "$PY" -c "
import re,sys; t=open(sys.argv[1]).read(); items=re.split(r'^## \d+\. ', t, flags=re.M)[1:]
assert len(items)>=40 and all('\n  > ' in i for i in items), len(items)" "$TMP/real-plan.md"
fi

# schema 1.1 + validate_findings
check "validate_findings: старый findings.json" "$PY" "$S/validate_findings.py" "$F/findings.json"
check "validate_findings: новые поля (content-i18n, claim_ref, NOT-CHECKED, proposal без actual)" "$PY" "$S/validate_findings.py" "$F/findings-v11.json"
if [ -n "${REAL_FINDINGS:-}" ] && [ -f "$REAL_FINDINGS" ]; then
  check "validate_findings: реальный findings.json прошлого прогона" "$PY" "$S/validate_findings.py" "$REAL_FINDINGS"
fi
"$PY" -c "
import json,sys; d=json.load(open(sys.argv[1]))
d['findings'][0].pop('actual'); d['findings'][0]['frequency']='often'; d['findings'][0]['target_forms']={'owner/repo':'x'}
json.dump(d,open(sys.argv[2],'w'),ensure_ascii=False)" "$F/findings-v11.json" "$TMP/bad11.json"
"$PY" "$S/validate_findings.py" "$TMP/bad11.json" > "$TMP/bad11.out" 2>&1
check "validate_findings: bug без actual, неверный frequency и target_forms -> ошибки" \
  grep -q "ошибок 3" "$TMP/bad11.out"

# render_draft.py: disclosure / links / marker / severity_map
RC="$F/run-config-foreign.yaml"
for id in F-001 F-003; do
  "$PY" "$S/render_draft.py" detailed "$F/findings-v11.json" --id $id --config "$RC" --repo owner/repo --out "$TMP/foreign-$id.md" >/dev/null 2>&1
done
"$PY" "$S/render_draft.py" comment "$F/findings-v11.json" --id F-003 --kind FIXED-INSUFFICIENT --what-fixed a --what-remains b \
  --why c --copy-link "owner/qa-copy#12" --config "$RC" --repo owner/repo --out "$TMP/foreign-comment.md" >/dev/null 2>&1
check "render_draft: disclosure none + cross_links false — нет site-qa-audit, Claude, чужих номеров, маркера" "$PY" -c "
import re,sys
for p in sys.argv[1:]:
    t=open(p).read(); low=t.lower()
    assert 'site-qa-audit' not in low and 'claude' not in low, p
    assert not re.search(r'qa-copy#\d+', t), p
    assert '<!--' not in t, p
assert open(sys.argv[1]).readline().startswith('TITLE: [Незначительно]')
" "$TMP/foreign-F-001.md" "$TMP/foreign-F-003.md" "$TMP/foreign-comment.md"
"$PY" "$S/render_draft.py" detailed "$F/findings-v11.json" --id F-001 --repo owner/repo --disclosure none --marker neutral --out "$TMP/neutral.md" >/dev/null
"$PY" "$S/render_draft.py" detailed "$F/findings-v11.json" --id F-001 --out "$TMP/full.md" >/dev/null
check "render_draft: --marker neutral даёт qa-fp, по умолчанию — маркер и подпись скила" sh -c \
  "grep -q '<!-- qa-fp:' '$TMP/neutral.md' && ! grep -q site-qa-audit '$TMP/neutral.md' && grep -q 'site-qa-audit:fp=' '$TMP/full.md' && grep -q 'qa-copy#7' '$TMP/full.md'"
check "render_draft: proposal без actual — Кратко из suggestion" sh -c \
  "'$PY' '$S/render_draft.py' detailed '$F/findings-v11.json' --id F-002 | grep -A1 '## Кратко' | grep -q 'Переключатель'"
check "render_draft severity: метка репозитория -> шкала скила" test "$("$PY" "$S/render_draft.py" severity --config "$RC" --repo owner/repo --label Серьёзно)" = high
check "render_draft severity: неизвестная метка -> ошибка" test "$(rc "$PY" "$S/render_draft.py" severity --config "$RC" --repo owner/repo --label P9)" != 0
echo '{"issues":[{"repo":"owner/repo","number":77,"title":"x","body":"<!-- qa-fp:0123456789abcdef -->","comments":[]}]}' > "$TMP/reg-neutral.json"
echo '{"run":{"id":"r","site":"https://example.com/","depth":"smoke","mode":"dry-run"},"findings":[{"id":"F-001","fingerprint":"0123456789abcdef","direction":"functional","check_id":"fn.x","type":"bug","severity":"low","title":"x","url":"https://example.com/","actual":"x","sources":["own:checklist"]}]}' > "$TMP/f-neutral.json"
"$PY" "$S/fingerprint.py" match "$TMP/f-neutral.json" "$TMP/reg-neutral.json" --out "$TMP/m-neutral.json" >/dev/null
check "fingerprint match: нейтральный маркер qa-fp находится" "$PY" -c "
import json,sys; m=json.load(open(sys.argv[1])); assert m[0]['exact'][0]['number']==77, m" "$TMP/m-neutral.json"

# build_report.py
RUN="$TMP/run"; mkdir -p "$RUN/logs"
cp "$F/findings-v11.json" "$RUN/findings.json"; cp "$RC" "$RUN/run-config.yaml"; cp "$TMP/rechecks.json" "$RUN/rechecks.json"
printf '# Побочные эффекты\n\n- загружен тестовый файл, флажок отмечен\n' > "$RUN/side_effects.md"
echo '{"rule":"user:U1","url":"https://pay.example.net/"}' > "$RUN/logs/blocked.jsonl"
echo '{"issues":[{"repo":"owner/repo","number":51,"state":"closed"}]}' > "$RUN/registry.json"
"$PY" "$S/build_report.py" report "$RUN" >/dev/null
check "build_report report: таблица перепроверки, NOT-CHECKED с причиной, side_effects, запреты, без {{" "$PY" -c "
import sys; t=open(sys.argv[1]).read()
assert '## Перепроверка заявленных исправлений' in t and '| № | Issue | Заявлено | Статус | Что проверено | Чем |' in t
assert 'NOT-CHECKED: нужен другой тип аккаунта' in t and 'Chrome 1440x813, /lab-full' in t
assert t.count('| owner/repo#51 |')==1, 'строки перепроверки не слиты'
assert 'загружен тестовый файл' in t and 'user:U1' in t and '{{' not in t
" "$RUN/report.md"
check "build_report report: нет findings.json -> код 2" test "$(rc "$PY" "$S/build_report.py" report "$TMP/empty-run")" = 2
"$PY" "$S/build_report.py" publish-table "$RUN" > "$TMP/pt.md"
check "build_report publish-table: closed_claims в политике и в действии, шкала репозитория" sh -c \
  "grep -q 'owner/repo — closed_claims: comment' '$TMP/pt.md' && grep -q 'комментарий: #51 закрыт, closed_claims: comment' '$TMP/pt.md' && grep -q 'owner/other — closed_claims: skip' '$TMP/pt.md' && grep -q '| Незначительно |' '$TMP/pt.md'"
sed 's/closed_claims: comment/closed_claims: skip/' "$RC" > "$RUN/run-config.yaml"
check "build_report publish-table: closed_claims skip -> пропуск" sh -c \
  "'$PY' '$S/build_report.py' publish-table '$RUN' | grep -q 'пропуск: #51 закрыт, closed_claims: skip'"

# intake.py from-text
cat > "$TMP/req.txt" <<'EOF'
Протестируй https://example.com/ глубоко: тексты и локализация, доступность.
Я уже залогинен, подключись к моему браузеру через CDP. Проверь как гость и с Pro.
Телефон Pixel 7, альбомная ориентация и десктоп, Safari тоже.
Репозиторий https://github.com/owner/repo — сверка и комментарии, по закрытым с недоработкой пиши комментарий.
Не упоминай скилл и Claude, не связывай репозитории.
Не нажимай «Поддержать» и «Купить Pro».
EOF
"$PY" "$S/intake.py" from-text --file "$TMP/req.txt" --output-dir "$TMP/out" --out "$TMP/rc-draft.yaml" >/dev/null
check "intake from-text: черновик run-config разбирается и экспортируется в rules.json" sh -c "
'$PY' '$S/url_guard.py' export --config '$TMP/rc-draft.yaml' --out '$TMP/rules-draft.json' >/dev/null &&
'$PY' '$S/shared/miniyaml.py' '$TMP/rc-draft.yaml' | '$PY' -c \"
import json,sys; c=json.load(sys.stdin)
assert c['site']['start_urls']==['https://example.com/'] and c['auth']['mode']=='manual-cdp'
assert c['depth']=='deep' and 'content-i18n' in c['directions'] and 'webkit' in c['devices']['browsers']
r=c['repos'][0]; assert r['url'].endswith('owner/repo') and 'comment' in r['roles']
assert r['disclosure']=='none' and r['cross_links'] is False and r['closed_claims']=='comment'
assert c['rules']['forbidden_actions'][0]['texts']==['Поддержать','Купить Pro']
assert {v['name'] for v in c['devices']['viewports']}=={'pixel7','landscape','desktop'}
\""
check "intake from-text: пустой запрос -> код 2" test "$(rc "$PY" "$S/intake.py" from-text --text "   ")" = 2

# journal.py
J="$TMP/jrun"
check "journal status без журнала -> код 1" test "$(rc "$PY" "$S/journal.py" status "$J")" = 1
"$PY" "$S/journal.py" init "$J" --todo "Разведка" --todo "Перепроверка #51" >/dev/null
"$PY" "$S/journal.py" done "$J" "#51" --note FIXED-INSUFFICIENT >/dev/null
"$PY" "$S/journal.py" note "$J" "side_effects.md: запись" >/dev/null
check "journal: init/done/note/status" sh -c "'$PY' '$S/journal.py' status '$J' --json | '$PY' -c \"
import json,sys; d=json.load(sys.stdin); assert d['todo']==['Разведка'] and d['done']==1\" && grep -q '\[x\].*Перепроверка #51' '$J/journal.md'"
check "journal done: нет совпадения -> код 2" test "$(rc "$PY" "$S/journal.py" done "$J" "нет такого пункта")" = 2

# read_templates.py fetch (local) and render --format
"$PY" "$S/read_templates.py" fetch owner/repo --local "$F/repo-templates" --out "$TMP/tpl/templates-owner__repo.json" >/dev/null
check "read_templates fetch: документы из формы и config.yml скачаны рядом, внешние — списком" "$PY" -c "
import json,sys,os; d=json.load(open(sys.argv[1]))
assert sorted(x['path'] for x in d['docs'])==['docs/attachments.md','docs/testing-guide.md'], d['docs']
assert 'https://chat.example.org/' in d['external_links']
assert os.path.exists(sys.argv[2])" "$TMP/tpl/templates-owner__repo.json" "$TMP/tpl/templates-owner__repo-docs/docs/testing-guide.md"
check "read_templates fetch: нет локальной папки -> код 2" test "$(rc "$PY" "$S/read_templates.py" fetch owner/repo --local "$TMP/nope")" = 2
echo '{"title":"Число 3,354","area":"Лаборатория сборок","steps":"1. Открыть /lab","actual":"3,354","severity":"Незначительно"}' > "$TMP/vals.json"
"$PY" "$S/read_templates.py" render "$TMP/tpl/templates-owner__repo.json" --template Ошибка --values "$TMP/vals.json" --format body > "$TMP/body.md"
check "read_templates render --format body: только тело" sh -c "head -1 '$TMP/body.md' | grep -q '^### Где' && ! grep -q '\"title\"' '$TMP/body.md' && grep -q '^Незначительно' '$TMP/body.md'"
check "read_templates render: неизвестный шаблон -> ошибка" test "$(rc "$PY" "$S/read_templates.py" render "$TMP/tpl/templates-owner__repo.json" --template Нет --values "$TMP/vals.json")" != 0

# check_env.py: browser tools in the current session
"$PY" "$S/check_env.py" --browser-tools-only --cdp-ports 1 --json "$TMP/bt.json" \
  --session-tools "Read,mcp__plugin_playwright_playwright__browser_navigate,mcp__plugin_playwright_playwright__browser_snapshot" > "$TMP/bt.out"
check "check_env: Playwright MCP в сессии + каких инструментов нет" sh -c \
  "grep -q 'Playwright MCP (сессия) |  | OK | в сессии: 2' '$TMP/bt.out' && grep -q 'browser_run_code_unsafe' '$TMP/bt.out' && grep -q 'Доступно в этой сессии: Playwright MCP' '$TMP/bt.out'"
"$PY" "$S/check_env.py" --browser-tools-only --cdp-ports 1 --session-tools "Read,Bash" > "$TMP/bt2.out"
check "check_env: без браузерных инструментов -> «в этой сессии нет»" sh -c \
  "grep -q 'Playwright MCP (сессия) |  | WARN | в этой сессии нет' '$TMP/bt2.out' && ! grep -q 'Доступно в этой сессии: Playwright' '$TMP/bt2.out'"

# item 17: no lines of '=' signs in command examples (zsh expands words starting with '=')
check "документация: нет строк из знаков равенства в примерах команд" sh -c \
  "! grep -rnE '(^|[[:space:];&|])(echo|printf)[[:space:]]+={2,}|^[[:space:]]*={3,}[[:space:]]*$' '$HERE/..' --exclude-dir=node_modules --include='*.md' --include='*.sh' --include='*.ps1' --include='*.yaml' --include='*.py'"

check "url_guard selftest" "$PY" "$S/url_guard.py" selftest

echo "stream A: PASS $pass, FAIL $fail"; [ $fail -eq 0 ]
