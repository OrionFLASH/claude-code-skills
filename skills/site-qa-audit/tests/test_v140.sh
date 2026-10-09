#!/usr/bin/env bash
# Offline tests for 1.4.0 (Python part, no network, no browser): file:// and local folders in url_guard
# (local_roots, «..», symlinks, host, too broad roots), intake from-text for local apps, fingerprint of file:// URLs,
# local paths masked in drafts. Browser parts — tests/v140.test.js (tests/test_v140_browser.sh).
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; S="$HERE/../scripts"; T="$HERE/../templates"; F="$HERE/fixtures"
if command -v python3 >/dev/null 2>&1; then PY="${PY:-python3}"; else PY="${PY:-python}"; fi
export PYTHONDONTWRITEBYTECODE=1
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
pass=0; fail=0
ok(){ echo "PASS $1"; pass=$((pass+1)); }; bad(){ echo "FAIL $1"; fail=$((fail+1)); }
check(){ local name="$1"; shift; if "$@"; then ok "$name"; else bad "$name"; fi; }
rc(){ "$@" >/dev/null 2>&1; echo $?; }
UG="$S/url_guard.py"
uri(){ "$PY" -c "import pathlib,sys; print(pathlib.Path(sys.argv[1]).as_uri())" "$1"; }

# ---------- #22: file:// and local folders ----------
APP="$TMP/work/app"; OUT="$TMP/work/outside"
mkdir -p "$APP/sub" "$APP/checkout" "$OUT" "$TMP/billing-app"
for f in "$APP/index.html" "$APP/sub/page.html" "$APP/checkout/index.html" "$OUT/x.html" "$TMP/billing-app/index.html"; do echo '<p>x</p>' > "$f"; done
SYMLINK=1; ln -s "$OUT" "$APP/evil" 2>/dev/null || SYMLINK=0
U_APP="$(uri "$APP")"; U_OUT="$(uri "$OUT")"
printf 'site:\n  start_urls:\n    - %s/index.html\n  allowed_domains:\n    - file\n' "$U_APP" > "$TMP/kw.yaml"
printf 'site:\n  local_roots:\n    - %s\n  allowed_domains: []\nrules:\n  forbidden_url_patterns:\n    - "/sub/secret"\n  read_only_urls: []\n' "$APP" > "$TMP/roots.yaml"
printf 'site:\n  allowed_domains:\n    - "%s/"\n' "$U_APP" > "$TMP/urlroot.yaml"
printf 'site:\n  start_urls:\n    - %s/index.html\n  allowed_domains: [file]\n' "$(uri "$TMP/billing-app")" > "$TMP/billing.yaml"

check "file: allowed_domains [file] -> каталог стартового URL: внутри 0" test "$(rc "$PY" "$UG" nav "$U_APP/sub/page.html" --config "$TMP/kw.yaml")" = 0
check "file: SPA-маршрут #/… и ?query внутри каталога -> 0" test "$(rc "$PY" "$UG" nav "$U_APP/index.html?tab=2#/report" --config "$TMP/kw.yaml")" = 0
check "file: соседний каталог (вне local_roots) -> 3" test "$(rc "$PY" "$UG" nav "$U_OUT/x.html" --config "$TMP/kw.yaml")" = 3
check "file: «..» в пути -> 3 (даже если остаётся внутри)" sh -c "
  test \$('$PY' '$UG' nav '$U_APP/sub/../../outside/x.html' --config '$TMP/kw.yaml' >/dev/null; echo \$?) = 3 &&
  test \$('$PY' '$UG' nav '$U_APP/sub/../index.html' --config '$TMP/kw.yaml' >/dev/null; echo \$?) = 3 &&
  test \$('$PY' '$UG' nav '$U_APP/sub/%2e%2e/%2e%2e/outside/x.html' --config '$TMP/kw.yaml' >/dev/null; echo \$?) = 3"
check "file: file://host/… (сетевой путь) -> 3" test "$(rc "$PY" "$UG" nav "file://server/share/app/index.html" --config "$TMP/kw.yaml")" = 3
if [ $SYMLINK -eq 1 ]; then
  out=$("$PY" "$UG" nav "$U_APP/evil/x.html" --config "$TMP/kw.yaml")
  check "file: симлинк внутри каталога наружу -> 3, правило base:file-symlink" sh -c "echo '$out' | grep -q 'base:file-symlink'"
else echo "SKIP file: симлинк (нет прав на симлинки)"; fi
check "file: http-сайт без local_roots -> file:// запрещён (3), правило base:file-no-roots" sh -c "
  '$PY' '$UG' nav '$U_APP/index.html' --config '$T/run-config.example.yaml' | grep -q 'base:file-no-roots'"
check "file: site.local_roots (абсолютный путь) -> внутри 0, правило пользователя по URL -> 3" sh -c "
  test \$('$PY' '$UG' nav '$U_APP/sub/page.html' --config '$TMP/roots.yaml' >/dev/null; echo \$?) = 0 &&
  test \$('$PY' '$UG' nav '$U_APP/sub/secret.html' --config '$TMP/roots.yaml' >/dev/null; echo \$?) = 3"
check "file: «file:///каталог/» в allowed_domains -> 0" test "$(rc "$PY" "$UG" nav "$U_APP/index.html" --config "$TMP/urlroot.yaml")" = 0
check "file: базовый запрет путей — по пути ОТ каталога (/checkout в приложении 3, --read-only 0; каталог billing-app не мешает)" sh -c "
  test \$('$PY' '$UG' nav '$U_APP/checkout/index.html' --config '$TMP/kw.yaml' >/dev/null; echo \$?) = 3 &&
  test \$('$PY' '$UG' nav '$U_APP/checkout/index.html' --config '$TMP/kw.yaml' --read-only >/dev/null; echo \$?) = 0 &&
  test \$('$PY' '$UG' nav '$(uri "$TMP/billing-app")/index.html' --config '$TMP/billing.yaml' >/dev/null; echo \$?) = 0"
check "file: resource внутри каталога 0, снаружи 3" sh -c "
  test \$('$PY' '$UG' resource '$U_APP/app.js' --config '$TMP/kw.yaml' >/dev/null; echo \$?) = 0 &&
  test \$('$PY' '$UG' resource '$U_OUT/x.html' --config '$TMP/kw.yaml' >/dev/null; echo \$?) = 3"
check "file: http-хост при allowed_domains [file] -> 3 (file — не маска хоста)" sh -c "
  test \$('$PY' '$UG' nav 'http://file/' --config '$TMP/kw.yaml' >/dev/null; echo \$?) = 3 &&
  test \$('$PY' '$UG' nav 'https://example.com/' --config '$TMP/kw.yaml' >/dev/null; echo \$?) = 3"
check "file: action на странице вне каталога -> 3; внутри — обычные правила (Купить 3, Найти 0)" sh -c "
  test \$('$PY' '$UG' action --text 'Открыть' --url '$U_OUT/x.html' --config '$TMP/kw.yaml' >/dev/null; echo \$?) = 3 &&
  test \$('$PY' '$UG' action --text 'Купить' --url '$U_APP/index.html' --config '$TMP/kw.yaml' >/dev/null; echo \$?) = 3 &&
  test \$('$PY' '$UG' action --text 'Найти' --url '$U_APP/index.html' --config '$TMP/kw.yaml' >/dev/null; echo \$?) = 0"
printf 'site:\n  local_roots:\n    - relative/app\n' > "$TMP/rel.yaml"
printf 'site:\n  local_roots:\n    - /\n' > "$TMP/slash.yaml"
printf 'site:\n  local_roots:\n    - "~"\n' > "$TMP/home.yaml"
printf 'site:\n  local_roots: %s\n' "$APP" > "$TMP/notlist.yaml"
check "file: относительный / «/» / домашняя папка / не список в local_roots -> код 4 (fail closed)" sh -c "
  for c in rel slash home notlist; do test \$('$PY' '$UG' nav '$U_APP/index.html' --config '$TMP/'\$c'.yaml' >/dev/null; echo \$?) = 4 || exit 1; done"
check "file: export — local_roots [{path, real}] для guard.js, file не попадает в allowed_domains" sh -c "
  '$PY' '$UG' export --config '$TMP/kw.yaml' --out '$TMP/kw-rules.json' >/dev/null &&
  '$PY' -c \"import json,sys,os; d=json.load(open(sys.argv[1])); r=d['rules']; assert r['allowed_domains']==[] and r['local_roots'][0]['path']==os.path.normpath(sys.argv[2]) and r['local_roots'][0]['real']==os.path.realpath(sys.argv[2]), r\" '$TMP/kw-rules.json' '$APP'"
check "file: каталог local_roots удалён -> 3 (base:file-root-missing или вне каталога), не allow" sh -c "
  mkdir -p '$TMP/gone' && printf 'site:\n  local_roots:\n    - $TMP/gone\n' > '$TMP/gone.yaml' && rmdir '$TMP/gone' &&
  test \$('$PY' '$UG' nav '$(uri "$TMP")/gone/index.html' --config '$TMP/gone.yaml' >/dev/null; echo \$?) = 3"

# intake from-text: file:///… and absolute paths -> start_urls + local_roots
check "intake from-text: file:///… и путь к .html -> start_urls, local_roots = каталог, без хостов" sh -c "
  '$PY' '$S/intake.py' from-text --text 'Протестируй офлайн-редактор $U_APP/index.html и отчёт $APP/sub/page.html без сервера' --json > '$TMP/in.json' &&
  '$PY' -c \"import json,sys,os; d=json.load(open(sys.argv[1]))['config']['site']; assert len(d['start_urls'])==2 and all(u.startswith('file:///') for u in d['start_urls']), d; assert os.path.normpath(sys.argv[2]) in d['local_roots'] and d['allowed_domains']==[], d\" '$TMP/in.json' '$APP'"
check "intake from-text: черновик run-config с file:// проходит url_guard (стартовый URL — 0)" sh -c "
  '$PY' '$S/intake.py' from-text --text 'Проверь $U_APP/index.html' --out '$TMP/in-rc.yaml' >/dev/null &&
  test \$('$PY' '$UG' nav '$U_APP/index.html' --config '$TMP/in-rc.yaml' >/dev/null; echo \$?) = 0"

# fingerprint: file:// relative to the local root -> the same fingerprint for a copy of the app elsewhere
mkdir -p "$TMP/run1/app" "$TMP/run2/app"
for n in 1 2; do
  printf 'site:\n  local_roots:\n    - %s/run%s/app\n' "$TMP" "$n" > "$TMP/run$n/run-config.yaml"
  printf '{"run": {"id": "r", "site": "x", "depth": "smoke", "mode": "dry-run"}, "findings": [{"id": "F-001", "direction": "ux", "check_id": "ux.x", "type": "bug", "severity": "low", "title": "t", "url": "%s/sub/page.html#/r", "actual": "a", "sources": ["own:checklist"]}]}' "$(uri "$TMP/run$n/app")" > "$TMP/run$n/findings.json"
  "$PY" "$S/fingerprint.py" compute "$TMP/run$n/findings.json" >/dev/null
done
check "fingerprint: file:// от каталога local_roots — копия приложения в другой папке даёт тот же отпечаток" sh -c "
  '$PY' -c \"import json,sys; a,b=[json.load(open(p))['findings'][0]['fingerprint'] for p in sys.argv[1:]]; assert a==b, (a,b)\" '$TMP/run1/findings.json' '$TMP/run2/findings.json'"
check "fingerprint one: шаблон file/<путь от каталога>, без каталога — два последних элемента" sh -c "
  '$PY' -c \"
import sys; sys.path.insert(0, sys.argv[1]); import fingerprint as f
assert f.url_template('file:///srv/a/app/sub/Page.html#/r') == 'file/sub/page.html#/r', f.url_template('file:///srv/a/app/sub/Page.html#/r')
f.LOCAL_ROOTS = [{'path': '/srv/a/app', 'real': '/srv/a/app'}]
assert f.url_template('file:///srv/a/app/sub/Page.html') == 'file/sub/page.html'
assert f.url_template('file:///srv/a/app/index.html') == 'file/index.html'
\" '$S'"

# drafts: the app folder becomes <app>, a home folder — ~
cat > "$TMP/run1/findings.json" <<EOF
{"run": {"id": "r", "site": "x", "depth": "smoke", "mode": "dry-run"}, "findings": [{"id": "F-001", "direction": "ux", "check_id": "ux.x", "type": "bug", "severity": "low", "title": "Кнопка закрыта", "url": "$(uri "$TMP/run1/app")/index.html", "steps": ["Открыть $(uri "$TMP/run1/app")/index.html"], "actual": "лог: /Users/someone/Library/x.log и /home/someone/a", "sources": ["own:checklist"]}]}
EOF
"$PY" "$S/render_draft.py" detailed "$TMP/run1/findings.json" --id F-001 --run-dir "$TMP/run1" --out "$TMP/d.md" >/dev/null 2>&1
check "render_draft: путь каталога приложения -> <app>, домашние папки -> ~ (ничего из локальных путей в issue)" sh -c "
  grep -q '<app>/index.html' '$TMP/d.md' && ! grep -q '$TMP' '$TMP/d.md' && ! grep -q '/Users/someone' '$TMP/d.md' && ! grep -q '/home/someone' '$TMP/d.md'"

# ---------- #23: copy of the skill in RUN_DIR, browser window in run-config ----------
SKILL="$(cd "$HERE/.." && pwd)"
SN="$S/skill_snapshot.py"
"$PY" "$SN" "$TMP/inst" --from "$SKILL" --mode copy --no-node-modules >/dev/null 2>&1  # «installed» skill elsewhere
mv "$TMP/inst/skill" "$TMP/installed"
mkdir -p "$TMP/installed/scripts/node/node_modules/pkg" && echo "module.exports=1" > "$TMP/installed/scripts/node/node_modules/pkg/index.js"
RUN="$TMP/run-snap"; mkdir -p "$RUN"
printf '# черновик: комментарий сохраняется\nversion: 1\nskill_dir: %s  # старый путь\nmode: dry-run\nsite:\n  allowed_domains:\n    - example.com\n' "$TMP/installed" > "$RUN/run-config.yaml"
check "skill_snapshot: копия в <RUN_DIR>/skill — полный SKILL_DIR без tests/, .snapshot.json с версией" sh -c "
  '$PY' '$SN' '$RUN' --from '$TMP/installed' --update-config > '$TMP/sn.out' 2>&1 &&
  test -f '$RUN/skill/SKILL.md' && test -f '$RUN/skill/scripts/url_guard.py' && test -f '$RUN/skill/templates/finding.schema.json' &&
  test -f '$RUN/skill/references/safety-rules.md' && test ! -e '$RUN/skill/tests' && test -f '$RUN/skill/.snapshot.json' &&
  '$PY' '$S/skill_dir.py' --check '$RUN/skill' | grep -q '^ok '"
check "skill_snapshot: node_modules — жёсткие ссылки (тот же inode), остальное — копии" sh -c "
  '$PY' -c \"import os,sys; a=os.stat(sys.argv[1]); b=os.stat(sys.argv[2]); c=os.stat(sys.argv[3]); d=os.stat(sys.argv[4]); assert a.st_ino==b.st_ino and c.st_ino!=d.st_ino\" '$TMP/installed/scripts/node/node_modules/pkg/index.js' '$RUN/skill/scripts/node/node_modules/pkg/index.js' '$TMP/installed/scripts/url_guard.py' '$RUN/skill/scripts/url_guard.py'"
check "skill_snapshot --update-config: skill_dir -> копия, skill_source -> источник, комментарии и остальное на месте" sh -c "
  grep -q '^# черновик: комментарий сохраняется' '$RUN/run-config.yaml' && grep -q '^mode: dry-run' '$RUN/run-config.yaml' &&
  '$PY' -c \"import sys; sys.path.insert(0, sys.argv[1]); import miniyaml; d=miniyaml.load_file(sys.argv[2]); assert d['skill_dir']==sys.argv[3] and d['skill_source']==sys.argv[4] and d['site']['allowed_domains']==['example.com'], d\" '$S/shared' '$RUN/run-config.yaml' '$RUN/skill' '$TMP/installed'"
rm -rf "$TMP/installed"
check "skill_snapshot: исходная папка удалена посреди прогона — копия работает (url_guard selftest, ingest example)" sh -c "
  '$PY' '$RUN/skill/scripts/url_guard.py' selftest >/dev/null && '$PY' '$RUN/skill/scripts/ingest_findings.py' example | grep -q qa-findings &&
  '$PY' '$RUN/skill/scripts/skill_dir.py' | grep -qx '$RUN/skill'"
check "skill_snapshot: повтор той же версии — уже есть (0); другая версия — 3 без --force" sh -c "
  '$PY' '$SN' '$RUN' --from '$RUN/skill' --json >/dev/null 2>&1; test \$? = 0 || true
  '$PY' -c \"import json,sys; p=sys.argv[1]; d=json.load(open(p)); d['version']='0.0.1'; json.dump(d, open(p,'w'))\" '$RUN/skill/.snapshot.json' &&
  mkdir -p '$TMP/src2' && cp -R '$RUN/skill/.' '$TMP/src2/' && rm -f '$TMP/src2/.snapshot.json' &&
  test \$('$PY' '$SN' '$RUN' --from '$TMP/src2' >/dev/null 2>&1; echo \$?) = 3 &&
  test \$('$PY' '$SN' '$RUN' --from '$TMP/src2' --force >/dev/null 2>&1; echo \$?) = 0"
check "skill_snapshot: источник без SKILL.md -> 1" test "$(rc "$PY" "$SN" "$TMP/run-x" --from "$TMP/nothing")" = 1

# local_app.py copy: an independent copy of the app, run-config -> the copy, the original is no longer allowed
LA="$S/local_app.py"; RUNA="$TMP/run-app"; mkdir -p "$RUNA"
cp -R "$F/local-app" "$TMP/origapp"; ln -s "$OUT" "$TMP/origapp/link-out" 2>/dev/null || true
printf 'version: 1\nsite:\n  start_urls:\n    - %s/sub/page.html\n  allowed_domains:\n    - file\nrules:\n  forbidden_domains: []\n' "$(uri "$TMP/origapp")" > "$RUNA/run-config.yaml"
"$PY" "$UG" export --config "$RUNA/run-config.yaml" --out "$RUNA/rules.json" >/dev/null
check "local_app copy --update-config: копия в <RUN_DIR>/app, start_urls и local_roots на копию, rules.json пересобран" sh -c "
  '$PY' '$LA' copy '$TMP/origapp' '$RUNA' --update-config --json > '$TMP/la.json' &&
  test -f '$RUNA/app/index.html' && test -f '$RUNA/app/sub/page.html' && test ! -e '$RUNA/app/link-out' &&
  '$PY' -c \"import json,sys,os; d=json.load(open(sys.argv[1])); assert d['start_url'].endswith('/app/index.html'), d
import pathlib; sys.path.insert(0, sys.argv[2]); import miniyaml; c=miniyaml.load_file(sys.argv[3])['site']
assert c['local_roots']==[sys.argv[4]] and c['allowed_domains']==[] and c['start_urls'][0].endswith('/app/sub/page.html'), c
r=json.load(open(sys.argv[5]))['rules']; assert r['local_roots'][0]['path']==sys.argv[4], r
c=json.load(open(sys.argv[6])); assert c.get('allowUnrestrictedFileAccess') is True, c\" '$TMP/la.json' '$S/shared' '$RUNA/run-config.yaml' '$RUNA/app' '$RUNA/rules.json' '$RUNA/playwright-cli.json' &&
  test \$('$PY' '$UG' nav '$(uri "$RUNA/app")/index.html' --config '$RUNA/run-config.yaml' >/dev/null; echo \$?) = 0 &&
  test \$('$PY' '$UG' nav '$(uri "$TMP/origapp")/index.html' --config '$RUNA/run-config.yaml' >/dev/null; echo \$?) = 3"
check "local_app copy: копия независима (правка копии не меняет оригинал); повтор без --force — 3" sh -c "
  echo changed >> '$RUNA/app/index.html' && ! grep -q changed '$TMP/origapp/index.html' &&
  test \$('$PY' '$LA' copy '$TMP/origapp' '$RUNA' >/dev/null 2>&1; echo \$?) = 3"
check "local_app copy: папка прогона внутри приложения — без рекурсии (qa-runs/ не копируется в себя)" sh -c "
  mkdir -p '$TMP/proj/qa-runs/r1' && cp '$F/local-app/index.html' '$TMP/proj/' &&
  '$PY' '$LA' copy '$TMP/proj' '$TMP/proj/qa-runs/r1' >/dev/null && test -f '$TMP/proj/qa-runs/r1/app/index.html' && test ! -e '$TMP/proj/qa-runs/r1/app/qa-runs'"

# browser window: run-config browser.* -> rules.json -> node scripts; browser_mode.py show/set
BM="$S/browser_mode.py"; RUNB="$TMP/run-browser"; mkdir -p "$RUNB"
printf '# комментарий\nversion: 1\nsite:\n  allowed_domains: [example.com]\nparallel:\n  max_workers: 2\n' > "$RUNB/run-config.yaml"
"$PY" "$UG" export --config "$RUNB/run-config.yaml" --out "$RUNB/rules.json" >/dev/null
check "browser_mode show: без настройки — окно видно (по умолчанию); SITE_QA_HEADLESS=1 — скрыто (env)" sh -c "
  env -u SITE_QA_HEADLESS '$PY' '$BM' show '$RUNB' --json | '$PY' -c \"import json,sys; d=json.load(sys.stdin); assert d['headed'] and d['source']=='по умолчанию' and d['playwright_cli'].endswith('playwright-cli.json --headed'), d\" &&
  SITE_QA_HEADLESS=1 '$PY' '$BM' show '$RUNB' --json | '$PY' -c \"import json,sys; d=json.load(sys.stdin); assert not d['headed'] and '--headed' not in d['playwright_cli'] and '--config' in d['playwright_cli'], d\""
check "browser_mode set --headed --slowmo 400: run-config и rules.json, главнее SITE_QA_HEADLESS=1; --cli -> --headed" sh -c "
  '$PY' '$BM' set '$RUNB' --headed --slowmo 400 >/dev/null &&
  '$PY' -c \"import json,sys; b=json.load(open(sys.argv[1]))['browser']; assert b=={'headed': True, 'slowmo': 400}, b\" '$RUNB/rules.json' &&
  SITE_QA_HEADLESS=1 '$PY' '$BM' show '$RUNB' --cli | grep -q -- '--headed\$' &&
  '$PY' -c \"import json,sys; d=json.load(open(sys.argv[1])); assert d=={'browser': {'launchOptions': {'headless': False, 'slowMo': 400}}}, d\" '$RUNB/playwright-cli.json' &&
  grep -q '^# комментарий' '$RUNB/run-config.yaml' && grep -q 'max_workers: 2' '$RUNB/run-config.yaml'"
check "browser_mode set --headless / --default" sh -c "
  '$PY' '$BM' set '$RUNB' --headless >/dev/null && ! '$PY' '$BM' show '$RUNB' --cli | grep -q -- '--headed' &&
  '$PY' -c \"import json,sys; d=json.load(open(sys.argv[1])); assert d['browser']['launchOptions']=={'headless': True}, d\" '$RUNB/playwright-cli.json' &&
  '$PY' '$BM' set '$RUNB' --default >/dev/null &&
  '$PY' -c \"import json,sys; b=json.load(open(sys.argv[1]))['browser']; assert b['headed'] is None and b['slowmo']==400, b\" '$RUNB/rules.json'"
if command -v node >/dev/null 2>&1; then
  check "lib.js browserMode: команда > run-config > env > видимое окно; --headed не съедает URL" sh -c "
    cd '$S/node' && SITE_QA_HEADLESS=1 node -e \"
const { browserMode, parseArgs } = require('./lib');
const eq = (a, b, m) => { if (JSON.stringify(a) !== JSON.stringify(b)) { console.error(m, JSON.stringify(a)); process.exit(1); } };
eq(browserMode({ browser: { headed: true, slowmo: 100 } }, {}, []), { headless: false, slowMo: 100, source: 'run-config' }, 'run-config > env');
eq(browserMode({ browser: { headed: true } }, {}, ['--headless']), { headless: true, slowMo: 0, source: 'cli' }, 'cli > run-config');
eq(browserMode(null, {}, []), { headless: true, slowMo: 0, source: 'env' }, 'env');
eq(browserMode({ browser: { headed: false } }, { headless: false }, []).source, 'script', 'script > all');
delete process.env.SITE_QA_HEADLESS; delete process.env.SITE_QA_SLOWMO;
eq(browserMode({ browser: { headed: null } }, {}, []), { headless: false, slowMo: 250, source: 'default' }, 'default');
eq(browserMode(null, {}, ['--headed', '--slowmo', '50']), { headless: false, slowMo: 50, source: 'cli' }, 'cli slowmo');
eq(parseArgs(['--headed', 'file:///a/index.html'])._, ['file:///a/index.html'], 'parseArgs --headed URL');
\""
fi
check "intake from-text: «с открытым окном, замедли до 400» -> browser.headed true, slowmo 400; «в фоне» -> false; иначе null" sh -c "
  '$PY' '$S/intake.py' from-text --text 'Проверь https://example.com/ с открытым окном, замедли до 400 мс' --json | '$PY' -c \"import json,sys; b=json.load(sys.stdin)['config']['browser']; assert b=={'headed': True, 'slowmo': 400}, b\" &&
  '$PY' '$S/intake.py' from-text --text 'Проверь https://example.com/ в фоне' --json | '$PY' -c \"import json,sys; b=json.load(sys.stdin)['config']['browser']; assert b['headed'] is False, b\" &&
  '$PY' '$S/intake.py' from-text --text 'Проверь https://example.com/' --json | '$PY' -c \"import json,sys; b=json.load(sys.stdin)['config']['browser']; assert b=={'headed': None, 'slowmo': None}, b\""

echo "stream v1.4.0: PASS $pass, FAIL $fail"
[ $fail -eq 0 ]
