#!/usr/bin/env bash
# Offline tests for 1.5.0 (no network, no browser): the tab registry of node scripts (lib.js ↔ tabs.py: format, lock,
# tool «node», cleanup only of own records), e2e_run.js verdict logic, publish_shots.py checks in advance and the local
# fallback (fake gh), browser_mode.py mcp (config of a separate Playwright MCP with the guard of the run).
# Browser parts — tests/v150.test.js (tests/test_v150_browser.sh).
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; S="$HERE/../scripts"; F="$HERE/fixtures"
if command -v python3 >/dev/null 2>&1; then PY="${PY:-python3}"; else PY="${PY:-python}"; fi
export PYTHONDONTWRITEBYTECODE=1
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
pass=0; fail=0
ok(){ echo "PASS $1"; pass=$((pass+1)); }; bad(){ echo "FAIL $1"; fail=$((fail+1)); }
check(){ local name="$1"; shift; if "$@"; then ok "$name"; else bad "$name"; fi; }
TABS="$S/tabs.py"; LIB="$S/node/lib.js"
HAVE_NODE=0; command -v node >/dev/null 2>&1 && HAVE_NODE=1

# ---------- #9: tab registry ----------
RUN="$TMP/run-tabs"; mkdir -p "$RUN"
# a record of a finished node script (pid that does not exist) and of a running one (this shell)
"$PY" - "$RUN" "$$" <<'EOF'
import json, sys
run, alive = sys.argv[1], int(sys.argv[2])
rec = lambda i, pid, prof: {"id": i, "owner": "qa-ux", "profile": prof, "tool": "node", "session": f"occlusion.js:{pid}", "url": "file:///x/index.html",
                            "target_id": None, "window_name": f"qa-ux-{prof}", "opened_at": "2026-10-09T10:00:00Z", "closed_at": None,
                            "pid": pid, "script": "occlusion.js"}
json.dump({"tabs": [rec("T-001", 999999, "desktop"), rec("T-002", alive, "pixel7")]}, open(f"{run}/tabs.json", "w"))
EOF
check "tabs.py list: запись node-скрипта — инструмент node, скрипт:pid" sh -c "
  '$PY' '$TABS' list '$RUN' | grep -q 'T-001 qa-ux desktop node occlusion.js:999999 открыта'"
check "tabs.py cleanup: процесс завершён — «уже закрыта», работающий скрипт — не трогается; --yes закрывает только завершённый" sh -c "
  '$PY' '$TABS' cleanup '$RUN' | '$PY' -c \"import json,sys; p={x['id']:x['action'] for x in json.load(sys.stdin)['plan']}; assert p['T-001'].startswith('уже закрыта') and p['T-002'].startswith('скрипт ещё работает'), p\" &&
  '$PY' '$TABS' cleanup '$RUN' --yes >/dev/null &&
  '$PY' -c \"import json,sys; t={x['id']:x for x in json.load(open(sys.argv[1]))['tabs']}; assert t['T-001']['closed_at'] and not t['T-002']['closed_at'], t\" '$RUN/tabs.json'"
check "tabs.py open: открытая запись node того же владельца и профиля не мешает (код 0, не 3)" sh -c "
  '$PY' '$TABS' open '$RUN' --owner qa-ux --profile pixel7 --tool cli >/dev/null"
check "tabs.py open --tool node не отклоняется (как запись из lib.js); одна вкладка на профиль для cli/mcp — по-прежнему код 3" sh -c "
  '$PY' '$TABS' open '$RUN' --owner qa-ux --profile pixel7 --tool node >/dev/null &&
  test \$('$PY' '$TABS' open '$RUN' --owner qa-ux --profile pixel7 --tool mcp >/dev/null 2>&1; echo \$?) = 3"

if [ $HAVE_NODE -eq 1 ]; then
  R2="$TMP/run-js"; mkdir -p "$R2"; touch "$R2/run-config.yaml"; echo '{}' > "$R2/rules.json"; mkdir -p "$TMP/norun"; echo '{}' > "$TMP/norun/rules.json"
  check "lib.js tabsConfig: --run-dir > SITE_QA_RUN_DIR > папка --rules с run-config.yaml; иначе выкл.; --no-tabs, SITE_QA_TABS=0" node -e "
    const { tabsConfig } = require(process.argv[1]); const R = process.argv[2], N = process.argv[3];
    const a = (x, m) => { if (!x) throw new Error(m); };
    a(tabsConfig(['--run-dir', R, '--owner', 'qa-ux'], {}).owner === 'qa-ux', 'owner');
    a(tabsConfig([], { SITE_QA_RUN_DIR: R }).runDir === R, 'env');
    a(tabsConfig(['--rules', R + '/rules.json'], {}).runDir === R, 'rules dir');
    a(tabsConfig(['--rules', N + '/rules.json'], {}) === null, 'rules without run-config');
    a(tabsConfig([], {}) === null, 'nothing');
    a(tabsConfig(['--run-dir', R, '--no-tabs'], {}) === null, '--no-tabs');
    a(tabsConfig(['--run-dir', R], { SITE_QA_TABS: '0' }) === null, 'SITE_QA_TABS=0');
    a(tabsConfig([], { SITE_QA_OWNER: 'qa-a11y', SITE_QA_RUN_DIR: R }).owner === 'qa-a11y', 'SITE_QA_OWNER');
  " "$LIB" "$R2" "$TMP/norun"
  check "lib.js parseArgs: --no-tabs без значения (URL остаётся позиционным)" node -e "
    const a = require(process.argv[1]).parseArgs(['--no-tabs', 'file:///x.html', '--owner', 'qa-ux']);
    if (a['no-tabs'] !== true || a._[0] !== 'file:///x.html' || a.owner !== 'qa-ux') process.exit(1);" "$LIB"
  check "TabRegistry: запись в формате tabs.py (id T-NNN, pid, script), выход процесса закрывает свои node-записи" sh -c "
    node -e \"const { TabRegistry } = require(process.argv[1]); const r = new TabRegistry({ runDir: process.argv[2], owner: 'qa-ux', script: 'occlusion.js' });
      const a = r.open({ profile: '1280x720', url: 'file:///x/index.html' }); const b = r.open({ profile: 'pixel7' }); r.close(a, { url: 'file:///x/sub.html' }); console.log(a, b);\" '$LIB' '$R2' > '$TMP/ids.txt' &&
    '$PY' -c \"import json,sys; t=json.load(open(sys.argv[1]))['tabs']; assert [x['id'] for x in t]==['T-001','T-002'], t; assert all(x['closed_at'] and x['tool']=='node' and x['script']=='occlusion.js' and isinstance(x['pid'], int) for x in t), t; assert t[0]['url'].endswith('sub.html'), t\" '$R2/tabs.json' &&
    '$PY' '$TABS' list '$R2' | grep -q 'открыто 0'"
  check "TabRegistry: процесс убит (SIGKILL) — запись остаётся открытой; tabs.py cleanup --yes закрывает её как завершённую" sh -c "
    ( node -e \"const { TabRegistry } = require(process.argv[1]); const r = new TabRegistry({ runDir: process.argv[2], owner: 'qa-ux', script: 'shot.js' }); r.open({ profile: 'desktop' }); process.kill(process.pid, 'SIGKILL');\" '$LIB' '$R2'; true ) 2>/dev/null;
    '$PY' '$TABS' list '$R2' --open --json | '$PY' -c \"import json,sys; t=json.load(sys.stdin); assert len(t)==1 and t[0]['script']=='shot.js', t\" &&
    '$PY' '$TABS' cleanup '$R2' --yes >/dev/null && '$PY' '$TABS' list '$R2' | grep -q 'открыто 0'"
  check "TabRegistry: чужие записи не трогает — close() чужого id ничего не меняет" sh -c "
    node -e \"const { TabRegistry } = require(process.argv[1]); const r = new TabRegistry({ runDir: process.argv[2], owner: 'qa-ux', script: 'x.js' });
      r.mine.set('T-001', 'node'); r.close('T-001'); r.cleanup();\" '$LIB' '$RUN' &&
    '$PY' -c \"import json,sys; t={x['id']:x for x in json.load(open(sys.argv[1]))['tabs']}; assert not t['T-002']['closed_at'], t\" '$RUN/tabs.json'"
  R3="$TMP/run-lock"; mkdir -p "$R3"
  check "общий lock-файл: 3 node-процесса и 2 цикла tabs.py параллельно — 70 записей, id без повторов, все закрыты" sh -c "
    for i in 1 2 3; do node -e \"const { TabRegistry } = require(process.argv[1]); const r = new TabRegistry({ runDir: process.argv[2], owner: 'w' + process.argv[3], script: 'x.js' });
      for (let k = 0; k < 20; k++) r.close(r.open({ profile: 'p' + k }));\" '$LIB' '$R3' \$i & done;
    for j in 1 2; do (for k in 1 2 3 4 5; do '$PY' '$TABS' open '$R3' --owner py\$j --profile p\$k >/dev/null && '$PY' '$TABS' close '$R3' --owner py\$j >/dev/null; done) & done; wait;
    '$PY' -c \"import json,sys; t=json.load(open(sys.argv[1]))['tabs']; ids=[x['id'] for x in t]; assert len(t)==70 and len(set(ids))==70, (len(t), len(set(ids))); assert all(x['closed_at'] for x in t)\" '$R3/tabs.json' &&
    test ! -e '$R3/tabs.json.lock'"

  # ---------- #34: e2e_run.js (logic without a browser) ----------
  check "e2e_run: адреса заготовки (new URL(…, APP_URL|BASE_URL), page.goto(\"…\")) для guard до запуска" node -e "
    const { gotoTargets } = require(process.argv[1]);
    const t = 'await page.goto(new URL(\"sub/page.html\", APP_URL.endsWith(\"/\") ? APP_URL : APP_URL + \"/\").href);\nawait page.goto(\"https://evil.test/x\");';
    const r = gotoTargets(t, 'file:///app/');
    if (r[0] !== 'file:///app/sub/page.html' || r[1] !== 'https://evil.test/x') { console.error(r); process.exit(1); }" "$S/node/e2e_run.js"
  check "e2e_run: вердикт — fail только при падении на проверке дефекта; pass — все повторы; fixme не считается" node -e "
    const { verdict } = require(process.argv[1]);
    const T = (runs, extra = {}) => ({ title: 't', outcome: 'x', annotations: [], runs, ...extra });
    const a = (x, m) => { if (!x) { console.error(m); process.exit(1); } };
    a(verdict('fail', [T([{ status: 'failed', error: 'Error: дефект воспроизводится  expect(received).toBeFalsy()' }])]).ok, 'fail on defect');
    a(!verdict('fail', [T([{ status: 'failed', error: 'page.goto: net::ERR_FILE_NOT_FOUND' }])]).ok, 'fail on goto is not the defect');
    a(!verdict('fail', [T([{ status: 'timedOut', error: 'Test timeout of 30000ms exceeded.' }])]).ok, 'timeout');
    a(!verdict('fail', [T([{ status: 'passed' }])]).ok, 'passes before fix');
    a(verdict('pass', [T([{ status: 'passed' }, { status: 'passed' }, { status: 'passed' }])]).ok, 'pass x3');
    a(!verdict('pass', [T([{ status: 'passed' }, { status: 'failed', error: 'x' }, { status: 'passed' }])]).ok, 'flaky');
    a(!verdict('pass', [T([], { annotations: ['fixme'], outcome: 'skipped' })]).ok, 'fixme');
    a(!verdict('pass', []).ok, 'no tests');" "$S/node/e2e_run.js"
  check "e2e_run: без --rules — код 4 (fail closed), нет файла — 2" sh -c "
    echo 'x' > '$TMP/F-1.spec.ts';
    test \$(node '$S/node/e2e_run.js' '$TMP/F-1.spec.ts' --app-url file:///tmp/ >/dev/null 2>&1; echo \$?) = 4 &&
    test \$(node '$S/node/e2e_run.js' '$TMP/none.spec.ts' --rules '$R2/rules.json' --app-url file:///tmp/ >/dev/null 2>&1; echo \$?) = 2"
else
  echo "SKIP lib.js/e2e_run: нет node"
fi

RB="$TMP/run-brief"; mkdir -p "$RB"
printf 'version: 1\noutput_dir: %s\ndepth: standard\nsite:\n  start_urls:\n    - https://example.com/\n  allowed_domains:\n    - example.com\n' "$TMP" > "$RB/run-config.yaml"
check "brief.py: в задании — node-скрипты с --rules <RUN_DIR>/rules.json --owner <поток> (вкладки в реестр сами)" sh -c "
  '$PY' '$S/brief.py' '$RB' --thread qa-ux >/dev/null && grep -q -- '--rules $RB/rules.json --owner qa-ux' '$RB/briefs/qa-ux.md'"

# ---------- #26: publish_shots — checks in advance, fallback local ----------
PS="$S/publish_shots.py"; FG="$F/findings-groups.json"; RS="$TMP/run-shots"; mkdir -p "$RS/screenshots"
"$PY" -c "
import json,sys; d=json.load(open(sys.argv[1]))
d['findings'][0]['screenshots']=['screenshots/qa-vis-01.png','screenshots/qa-vis-01-annotated.png']
d['findings'][1]['screenshots']=['screenshots/qa-mob-02.png']; d['findings'][1]['evidence']={'sensitive': True}
d['findings'][2]['screenshots']=['screenshots/qa-ux-03-annotated.png']
json.dump(d, open(sys.argv[2],'w'), ensure_ascii=False)" "$FG" "$RS/findings.json"
printf 'png-1' > "$RS/screenshots/qa-vis-01.png"; printf 'png-1-annotated' > "$RS/screenshots/qa-vis-01-annotated.png"
printf 'secret' > "$RS/screenshots/qa-mob-02.png"; printf 'png-3-annotated' > "$RS/screenshots/qa-ux-03-annotated.png"
state(){ printf '%s' "$1" > "$TMP/gh-state.json"; }
REPOS='"repos": {"owner/priv": {"private": true, "permissions": {"push": true}, "default_branch": "main", "refs": {"main": "c0ffee"}, "files": {}}, "owner/pub": {"private": false, "permissions": {"push": false}, "default_branch": "main", "refs": {"main": "c0ffee"}, "files": {}}, "owner/sso": {"private": true, "permissions": {"push": true}, "default_branch": "main", "refs": {"main": "c0ffee"}, "files": {}, "deny_put_after": 1}}'
export QA_GH_BIN="$HERE/helpers/fake_gh_contents.py" FAKE_GH_STATE="$TMP/gh-state.json" QA_GH_PAUSE=0
state "{$REPOS}"
check "publish_shots plan: проверки заранее (gh, вход, репозиторий, push) — без записи; api-commit" sh -c "
  '$PY' '$PS' plan '$RS' --repo owner/priv 2>/dev/null | '$PY' -c \"import json,sys; d=json.load(sys.stdin); assert d['mode']=='api-commit' and [c['check'] for c in d['checks']]==['gh','login','repo','push'] and all(c['ok'] for c in d['checks']), d; assert d['fallback']['mode']=='local'\" &&
  ! grep -q '\"PUT\"\\|\"POST\"' '$TMP/gh-state.json'"
check "publish_shots plan: gh нет — local (код 0, причина и запасной путь), а не ошибка" sh -c "
  QA_GH_BIN='$TMP/no-such-gh' '$PY' '$PS' plan '$RS' --repo owner/priv 2>'$TMP/p.err' | '$PY' -c \"import json,sys; d=json.load(sys.stdin); assert d['mode']=='local' and d['checks'][0]=={'check':'gh','ok':False,'detail':d['checks'][0]['detail']} and 'gh' in d['reason'], d\" &&
  grep -q 'запасной путь: publish_shots.py local' '$TMP/p.err'"
state "{\"auth\": {\"logged_in\": false}, $REPOS}"
check "publish_shots plan: gh не авторизован — local; вход делает только пользователь (gh auth login), скил не входит" sh -c "
  '$PY' '$PS' plan '$RS' --repo owner/priv 2>/dev/null | '$PY' -c \"import json,sys; d=json.load(sys.stdin); assert d['mode']=='local' and 'не авторизован' in d['reason'] and 'gh auth login' in d['reason'], d\" &&
  test \$('$PY' '$PS' push '$RS' --repo owner/priv --confirm-push >/dev/null 2>&1; echo \$?) = 1"
state "{\"auth\": {\"scopes\": [\"read:org\", \"gist\"]}, $REPOS}"
check "publish_shots plan: у токена нет scope repo — push невозможен заранее (web-upload с причиной)" sh -c "
  '$PY' '$PS' plan '$RS' --repo owner/priv 2>/dev/null | '$PY' -c \"import json,sys; d=json.load(sys.stdin); c=[x for x in d['checks'] if x['check']=='push'][0]; assert d['mode']=='web-upload' and not c['ok'] and 'scope repo' in c['detail'] and 'scope repo' in d['reason'], d\""
state "{\"auth\": {\"scopes\": [\"repo\", \"read:org\"]}, $REPOS}"
check "publish_shots push: отказ записи 403 на втором файле — код 3, понятная причина, запасной путь, загруженное — в shots-published.json" sh -c "
  '$PY' '$PS' push '$RS' --repo owner/sso --confirm-push 2>'$TMP/s.err' > '$TMP/s.json'; test \$? = 3 &&
  '$PY' -c \"import json,sys; d=json.load(open(sys.argv[1])); assert [u['status'] for u in d['uploads']]==['created','not uploaded'], d['uploads']; assert '403' in d['error'] and 'Contents: write' in d['error'], d['error']; p=json.load(open(sys.argv[2])); assert list(p)==['screenshots/qa-vis-01-annotated.png'], p\" '$TMP/s.json' '$RS/shots-published.json' &&
  grep -q 'запасной путь: publish_shots.py local' '$TMP/s.err'"
check "publish_shots local: results/screenshots/ + index.md + архив; sensitive не попадает; строка для issue" sh -c "
  '$PY' '$PS' local '$RS' 2>'$TMP/l.err' | '$PY' -c \"import json,sys; d=json.load(sys.stdin); assert d['mode']=='local' and sorted(x['id'] for x in d['files'])==['F-001','F-003'], d; assert 'results/screenshots/' in d['issue_line'], d\" &&
  test -f '$RS/results/screenshots/qa-vis-01-annotated.png' && test ! -e '$RS/results/screenshots/qa-mob-02.png' && test ! -e '$RS/results/screenshots/qa-vis-01.png' &&
  grep -q '| F-001 |' '$RS/results/screenshots/index.md' &&
  '$PY' -c \"import zipfile,sys; n=sorted(zipfile.ZipFile(sys.argv[1]).namelist()); assert n==['index.md','qa-ux-03-annotated.png','qa-vis-01-annotated.png'], n\" '$RS/results/screenshots.zip' &&
  grep -q 'в issue: Скриншоты: приложены к отчёту прогона' '$TMP/l.err'"
check "publish_shots push --fallback-local: без push — сразу local (код 0)" sh -c "
  rm -rf '$RS/results' && '$PY' '$PS' push '$RS' --repo owner/pub --confirm-push --fallback-local 2>/dev/null | '$PY' -c \"import json,sys; d=json.load(sys.stdin); assert d['mode']=='web-upload' and d['local']['mode']=='local', d\" &&
  test -f '$RS/results/screenshots.zip'"
check "build_report: «Скриншоты находок» ссылается на results/screenshots.zip (артефакт при отчёте)" sh -c "
  '$PY' '$S/build_report.py' report '$RS' >/dev/null 2>&1 && grep -q 'results/screenshots.zip' '$RS/report.md'"
unset QA_GH_BIN FAKE_GH_STATE QA_GH_PAUSE

# ---------- #34: browser_mode.py mcp — a separate Playwright MCP of the run ----------
BM="$S/browser_mode.py"; RM="$TMP/run-mcp"; mkdir -p "$RM/app"; echo '<p>x</p>' > "$RM/app/index.html"
printf 'site:\n  start_urls:\n    - %s\n  local_roots:\n    - %s\n  allowed_domains: []\nbrowser:\n  headed: true\n  slowmo: 120\n' "$("$PY" -c "import pathlib,sys; print(pathlib.Path(sys.argv[1]).as_uri())" "$RM/app/index.html")" "$RM/app" > "$RM/run-config.yaml"
check "browser_mode mcp: без rules.json — код 4 (MCP без правил не настраивается)" sh -c "
  test \$('$PY' '$BM' mcp '$RM' >/dev/null 2>&1; echo \$?) = 4"
"$PY" "$S/url_guard.py" export --config "$RM/run-config.yaml" --out "$RM/rules.json" >/dev/null
check "browser_mode mcp: playwright-mcp.json — Chromium скила, профиль в памяти, окно прогона, file:// + guard в каждой вкладке (initPage)" sh -c "
  '$PY' '$BM' mcp '$RM' --json | '$PY' -c \"import json,sys; d=json.load(sys.stdin); assert d['command'][2:4]==['mcp','--config'] and d['claude_mcp_add'].startswith('claude mcp add site-qa-local -- node '), d\" &&
  '$PY' -c \"import json,sys; c=json.load(open(sys.argv[1])); b=c['browser']; assert c['allowUnrestrictedFileAccess'] is True and b['isolated'] is True and b['browserName']=='chromium' and b['launchOptions']=={'headless': False, 'channel': 'chromium', 'slowMo': 120}, c; import os; assert [os.path.realpath(x) for x in b['initPage']]==[os.path.realpath(sys.argv[2])], b\" '$RM/playwright-mcp.json' '$RM/mcp-guard.js' &&
  grep -q 'mcp_guard.js' '$RM/mcp-guard.js' && grep -q 'rules.json' '$RM/mcp-guard.js'"
RW="$TMP/run-web"; mkdir -p "$RW"; printf 'site:\n  start_urls:\n    - https://example.com/\n  allowed_domains:\n    - example.com\n' > "$RW/run-config.yaml"
"$PY" "$S/url_guard.py" export --config "$RW/run-config.yaml" --out "$RW/rules.json" >/dev/null
check "browser_mode mcp: сайт без local_roots — file:// не открывается (нет allowUnrestrictedFileAccess), guard — всё равно" sh -c "
  '$PY' '$BM' mcp '$RW' >/dev/null && '$PY' -c \"import json,sys; c=json.load(open(sys.argv[1])); assert 'allowUnrestrictedFileAccess' not in c and c['browser']['initPage'], c\" '$RW/playwright-mcp.json'"
if [ $HAVE_NODE -eq 1 ]; then
  check "mcp_guard.js: без rules.json — ошибка при загрузке (MCP не откроет вкладку: fail closed)" sh -c "
    ! node -e \"require(process.argv[1]).make(process.argv[2], null)\" '$S/node/mcp_guard.js' '$TMP/missing-rules.json' 2>/dev/null &&
    node -e \"const f = require(process.argv[1]).make(process.argv[2], null); if (typeof f !== 'function') process.exit(1)\" '$S/node/mcp_guard.js' '$RM/rules.json'"
fi

echo "stream v1.5.0: PASS $pass, FAIL $fail"
[ $fail -eq 0 ]
