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

# ---------- #25: one format of executor results, dup_check, registry slice, one place of truth ----------
VF="$S/validate_findings.py"; IN="$S/ingest_findings.py"; CV="$S/coverage.py"; BR="$S/brief.py"
cat > "$TMP/arr.json" <<'EOF'
[{"direction": "ux", "check_id": "ux.feedback", "type": "bug", "severity": "medium", "title": "Поиск без ответа",
  "url": "https://example.com/", "actual": "ничего", "repro": {"url": "https://example.com/", "js": "true"},
  "dup_check": "done", "sources": ["own:checklist"]}]
EOF
"$PY" -c "import json,sys; d=json.load(open(sys.argv[1])); del d[0]['dup_check']; json.dump(d, open(sys.argv[2],'w'))" "$TMP/arr.json" "$TMP/arr-nodup.json"
check "validate_findings --array: массив без id — 0; файл-массив распознаётся и без --array" sh -c "
  '$PY' '$VF' --array '$TMP/arr.json' >/dev/null && '$PY' '$VF' '$TMP/arr.json' | grep -q 'результат исполнителя (массив): 1'"
check "validate_findings --array: без dup_check — ошибка (код 1)" sh -c "
  out=\$('$PY' '$VF' --array '$TMP/arr-nodup.json'); test \$? = 1 && echo \"\$out\" | grep -q 'dup_check'"
check "validate_findings --array -: блок qa-findings из сообщения на stdin; не JSON и без блока — код 2" sh -c "
  sed 's/\"sources\": \[\"own:checklist\"\]}/\"dup_check\": \"skipped\", \"sources\": [\"own:checklist\"]}/' '$F/agent-message.md' | '$PY' '$VF' --array - | grep -q 'ошибок 0' &&
  test \$(echo 'просто текст' | '$PY' '$VF' --array - >/dev/null; echo \$?) = 2"
printf '{"id": "r", "site": "https://example.com/", "mode": "dry-run"}' > "$TMP/run-bad.json"
check "validate_findings --run: run.json без depth — ошибка" sh -c "
  out=\$('$PY' '$VF' --array '$TMP/arr.json' --run '$TMP/run-bad.json'); test \$? = 1 && echo \"\$out\" | grep -q 'depth'"
check "validate_findings: в findings.json находка исполнителя (ingested) без dup_check — ошибка; старые файлы — 0" sh -c "
  '$PY' -c \"import json,sys; d=json.load(open(sys.argv[1])); d['findings'][0]['ingested']={'thread':'qa-x'}; json.dump(d, open(sys.argv[2],'w'))\" '$F/findings.json' '$TMP/fj.json' &&
  test \$('$PY' '$VF' '$TMP/fj.json' >/dev/null; echo \$?) = 1 && '$PY' '$VF' '$F/findings.json' >/dev/null"

R5="$TMP/run25"; mkdir -p "$R5"
printf 'version: 1\noutput_dir: %s\ndepth: standard\nsite:\n  start_urls:\n    - https://example.com/\n  allowed_domains:\n    - example.com\nrules:\n  forbidden_actions:\n    - id: U1\n      source: "не нажимать Купить"\n      texts: ["Купить"]\nparallel:\n  max_workers: 2\n  throttle_ms: 900\n' "$TMP" > "$R5/run-config.yaml"
cp "$F/registry-claims.json" "$R5/registry.json"
check "fetch_issues brief: строка на issue, закрытый исправленный — «исправлено», лимит с остатком; json" sh -c "
  '$PY' '$S/fetch_issues.py' brief '$R5/registry.json' --limit 4 > '$TMP/rb.md' &&
  test \$(grep -c '^- owner/repo#' '$TMP/rb.md') = 4 && grep -q 'ещё .* issues' '$TMP/rb.md' &&
  '$PY' '$S/fetch_issues.py' brief '$F/registry.json' | grep -q 'owner/repo#5 \[closed: исправлено\]' &&
  '$PY' '$S/fetch_issues.py' brief '$F/registry.json' --format json | '$PY' -c \"import json,sys; d=json.load(sys.stdin); assert d['total']==2 and d['issues'][0]['ref']=='owner/repo#9', d\""
check "brief.py: задание целиком — без {{…}}, блок правил §4 дословно с таблицей правил, срез реестра, --trace, формат" sh -c "
  '$PY' '$BR' '$R5' --thread qa-ux --directions ux,product --pages 'главная' --minutes 20 --registry-limit 3 >/dev/null &&
  B='$R5/briefs/qa-ux.md' && ! grep -q '{{' \"\$B\" && grep -q 'ПРАВИЛА БЕЗОПАСНОСТИ site-qa-audit' \"\$B\" &&
  grep -q 'не нажимать Купить' \"\$B\" && grep -q 'Пауза между действиями не меньше 900 мс' \"\$B\" &&
  grep -q 'owner/repo#48' \"\$B\" && grep -q -- '--trace $R5/logs/guard-qa-ux.jsonl' \"\$B\" && grep -q '\"dup_check\": \"done\"' \"\$B\" &&
  grep -q 'Время: 20 минут' \"\$B\" && grep -q 'checklists/ux.md' \"\$B\" && test -f '$R5/playwright-cli.json' &&
  '$PY' -c \"import json,sys; t=json.load(open(sys.argv[1]))['qa-ux']; assert t['minutes']==20 and t['started_at'] and t['directions']==['ux','product'], t\" '$R5/threads.json'"
check "brief.py: без registry.json — «реестра нет, dup_check: skipped»; битые правила — код 2, задание не создано" sh -c "
  mkdir -p '$TMP/r5b' && cp '$R5/run-config.yaml' '$TMP/r5b/' && '$PY' '$BR' '$TMP/r5b' --thread qa-a >/dev/null &&
  grep -q 'реестра нет' '$TMP/r5b/briefs/qa-a.md' &&
  printf 'site:\n  allowed_domains: [example.com]\nrules:\n  forbidden_url_patterns: [\"(bad\"]\n' > '$TMP/r5b/run-config.yaml' &&
  test \$('$PY' '$BR' '$TMP/r5b' --thread qa-b >/dev/null 2>&1; echo \$?) = 2 && test ! -e '$TMP/r5b/briefs/qa-b.md'"
# the executor works: guard decisions with --trace
UGT(){ "$PY" "$UG" "$@" --config "$R5/run-config.yaml" --trace "$R5/logs/guard-qa-ux.jsonl" >/dev/null 2>&1; }
UGT nav https://example.com/; UGT nav "https://example.com/catalog?token=secret123"; UGT nav https://evil.test/
UGT action --text "Найти" --url https://example.com/ --context "секретный текст формы"; UGT action --text "Найти" --url https://example.com/
UGT action --text "Фильтр" --url https://example.com/catalog; UGT action --text "Купить" --url https://example.com/
check "url_guard --trace: строка на каждое решение, значения query и текст контекста не пишутся" sh -c "
  test \$(wc -l < '$R5/logs/guard-qa-ux.jsonl') -eq 7 && ! grep -q 'secret123' '$R5/logs/guard-qa-ux.jsonl' &&
  ! grep -q 'секретный' '$R5/logs/guard-qa-ux.jsonl' && grep -q '\"decision\": \"deny\"' '$R5/logs/guard-qa-ux.jsonl'"
check "url_guard --trace: журнал не записать — решение то же (0), предупреждение" sh -c "
  mkdir -p '$TMP/tracedir.jsonl' && test \$('$PY' '$UG' nav https://example.com/ --config '$R5/run-config.yaml' --trace '$TMP/tracedir.jsonl' >/dev/null 2>&1; echo \$?) = 0"
cat > "$TMP/msg5.md" <<'EOF'
Готово.
```qa-findings
{"thread": "qa-ux",
 "findings": [
  {"direction": "ux", "check_id": "ux.feedback", "type": "bug", "severity": "medium", "title": "Поиск без ответа",
   "url": "https://example.com/", "actual": "ничего", "repro": {"url": "https://example.com/", "js": "true"},
   "dup_check": "done", "sources": ["own:checklist"]},
  {"direction": "ux", "check_id": "ux.copy", "type": "content", "severity": "low", "title": "Опечатка в кнопке",
   "url": "https://example.com/catalog", "actual": "«Найт»", "sources": ["own:checklist"]}
 ],
 "checked": [{"what": "главная: поиск", "direction": "ux"}],
 "not_checked": [{"what": "корзина", "reason": "запрет U1", "rule": "user:forbidden_actions:U1"},
                 {"what": "каталог на iPad", "reason": "не успел, лимит 20 минут"},
                 {"what": "WebKit", "reason": "браузер не запускается", "category": "environment"},
                 {"what": "каталог на iPad", "reason": "не успел, лимит 20 минут"}],
 "metrics": {"minutes": 18},
 "questions": ["пустой поиск — задумано?"]}
```
EOF
"$PY" "$IN" "$R5" --from "$TMP/msg5.md" > "$TMP/in5.json" 2>&1
check "ingest: findings/<поток>.json — массив с id, coverage/<поток>.json и .md, run.json по схеме run" sh -c "
  '$PY' -c \"import json,sys; a=json.load(open(sys.argv[1])); assert isinstance(a, list) and [x['id'] for x in a]==['F-001','F-002'], a\" '$R5/findings/qa-ux.json' &&
  test -f '$R5/coverage/qa-ux.json' && test -f '$R5/coverage/qa-ux.md' &&
  '$PY' '$VF' --array '$R5/findings/qa-ux.json' --run '$R5/run.json' >/dev/null && '$PY' '$VF' '$R5/findings.json' >/dev/null"
check "ingest: нет dup_check — записано skipped с предупреждением; повтор not_checked убран" sh -c "
  grep -q 'dup_check не указан у F-002' '$TMP/in5.json' &&
  '$PY' -c \"import json,sys; d=json.load(open(sys.argv[1])); assert d['findings'][1]['dup_check']=='skipped'; nc=[x['what'] for x in d['not_checked']]; assert nc.count('каталог на iPad')==1, nc\" '$R5/findings.json'"
check "ingest: повторное уведомление тем же сообщением — «уже принято», ничего не изменилось; --force — дубли пропущены" sh -c "
  '$PY' '$IN' '$R5' --from '$TMP/msg5.md' | grep -q '\"duplicate\": true' &&
  '$PY' -c \"import json,sys; d=json.load(open(sys.argv[1])); assert len(d['findings'])==2 and len(d['not_checked'])==3, d\" '$R5/findings.json' &&
  '$PY' '$IN' '$R5' --from '$TMP/msg5.md' --force | grep -q 'уже есть с тем же заголовком' &&
  '$PY' -c \"import json,sys; d=json.load(open(sys.argv[1])); assert len(d['findings'])==2 and len(d['not_checked'])==3, d\" '$R5/findings.json'"
# deterministic times: the brief 30 min before the last guard decision, the result ingested 31 min after the brief
"$PY" - "$R5" <<'EOF'
import json, sys
from pathlib import Path
r = Path(sys.argv[1])
t = json.loads((r / "threads.json").read_text(encoding="utf-8")); t["qa-ux"]["started_at"] = "2026-10-09T10:00:00Z"
(r / "threads.json").write_text(json.dumps(t), encoding="utf-8")
c = json.loads((r / "coverage" / "qa-ux.json").read_text(encoding="utf-8")); c["updated_at"] = "2026-10-09T10:31:00Z"
(r / "coverage" / "qa-ux.json").write_text(json.dumps(c), encoding="utf-8")
lines = [json.loads(x) for x in (r / "logs" / "guard-qa-ux.jsonl").read_text(encoding="utf-8").splitlines()]
for i, e in enumerate(lines):
    e["ts"] = f"2026-10-09T10:{5 + i:02d}:00Z"
(r / "logs" / "guard-qa-ux.jsonl").write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in lines), encoding="utf-8")
EOF
check "coverage build: время от задания до результата (31 мин, больше лимита 20), переходы 3 (страниц 2), действия 4 (элементов 2)" sh -c "
  '$PY' '$CV' build '$R5' --thread qa-ux >/dev/null &&
  '$PY' -c \"import json,sys; m=json.load(open(sys.argv[1]))['auto_metrics']; assert m['minutes']==31.0 and m['over_limit'] and m['nav_checks']==3 and m['pages']==2 and m['action_checks']==4 and m['controls']==2 and m['denied']==2, m\" '$R5/coverage/qa-ux.json' &&
  grep -q 'больше лимита' '$R5/coverage/qa-ux.md' && grep -q 'главная: поиск' '$R5/coverage/qa-ux.md' && grep -q 'Самооценка исполнителя: minutes: 18' '$R5/coverage/qa-ux.md'"
check "coverage summary: таблица потоков в coverage/summary.md" sh -c "
  '$PY' '$CV' summary '$R5' >/dev/null && grep -q '^| qa-ux | 31.0 ⚠ | 3 (2) | 4 (2) | 2 |' '$R5/coverage/summary.md'"
check "build_report: «Охват по потокам», «Скриншоты находок» и строка о несверенных находках" sh -c "
  '$PY' -c \"import json,sys; d=json.load(open(sys.argv[1])); d['findings'][0]['screenshots']=['screenshots/qa-ux-01-annotated.png']; json.dump(d, open(sys.argv[1],'w'))\" '$R5/findings.json' &&
  '$PY' '$S/build_report.py' report '$R5' >/dev/null && grep -q '## Охват по потокам' '$R5/report.md' &&
  grep -q '## Скриншоты находок' '$R5/report.md' && grep -q 'qa-ux-01-annotated.png' '$R5/report.md' &&
  grep -q 'не делал у 1 находок (F-002)' '$R5/report.md' && grep -q '| каталог на iPad |' '$R5/report.md' &&
  '$PY' '$S/build_report.py' summary '$R5' >/dev/null && grep -q '## Охват по потокам' '$R5/summary.md'"
check "build_report: варианты данных/стенды — таблица по variants из run-config" sh -c "
  cp '$R5/run-config.yaml' '$TMP/rc5.bak' && printf 'variants:\n  - id: test\n  - id: prod\n' >> '$R5/run-config.yaml' &&
  '$PY' -c \"import json,sys; d=json.load(open(sys.argv[1])); d['findings'][0]['variant']='test'; json.dump(d, open(sys.argv[1],'w'))\" '$R5/findings.json' &&
  '$PY' '$S/build_report.py' report '$R5' >/dev/null && grep -q '| test | 1 | 0 |' '$R5/report.md' && grep -q '| prod | 0 | 0 |' '$R5/report.md' &&
  cp '$TMP/rc5.bak' '$R5/run-config.yaml'"

check "coverage build до результата (ход потока по журналу guard), затем ingest того же потока — без ошибок" sh -c "
  '$PY' '$BR' '$R5' --thread qa-prog --directions functional >/dev/null &&
  '$PY' '$UG' nav https://example.com/ --config '$R5/run-config.yaml' --trace '$R5/logs/guard-qa-prog.jsonl' >/dev/null &&
  '$PY' '$CV' build '$R5' --thread qa-prog | grep -q 'переходов 1' &&
  printf '%s\n' 'Итог' '\`\`\`qa-findings' '{\"thread\": \"qa-prog\", \"findings\": [], \"checked\": [{\"what\": \"главная\"}], \"not_checked\": []}' '\`\`\`' > '$TMP/msg-prog.md' &&
  '$PY' '$IN' '$R5' --from '$TMP/msg-prog.md' >/dev/null &&
  '$PY' -c \"import json,sys; c=json.load(open(sys.argv[1])); assert c['checked']==[{'what': 'главная'}] and c['auto_metrics']['nav_checks']==1, c\" '$R5/coverage/qa-prog.json'"

# ---------- #24: second wave by «not checked» ----------
"$PY" "$S/journal.py" init "$R5" >/dev/null
check "coverage again: волна 2 — запреты отдельно, категории (time, environment), задачи потоков, todo в журнале" sh -c "
  '$PY' '$CV' again '$R5' --minutes 10 --per-item 5 > '$TMP/ag.out' &&
  test -f '$R5/waves/2/plan.md' && test -f '$R5/waves/2/qa-w2-1.json' &&
  '$PY' -c \"import json,sys; p=json.load(open(sys.argv[1])); assert len(p['held_forbidden'])==1 and p['held_forbidden'][0]['what']=='корзина'; cats=sorted(x['category'] for t in p['threads'] for x in t['items']); assert cats==['environment','time'], cats\" '$R5/waves/2/plan.json' &&
  grep -q 'Нужно решение пользователя' '$R5/waves/2/plan.md' && grep -q 'Волна 2: qa-w2-1' '$R5/journal.md'"
check "coverage again: --include-forbidden и повтор — волна 3; лимит времени делит пункты по потокам" sh -c "
  '$PY' '$CV' again '$R5' --minutes 5 --per-item 5 --threads 4 --include-forbidden --json > '$TMP/ag3.json' &&
  '$PY' -c \"import json,sys; p=json.load(open(sys.argv[1])); assert p['wave']==3 and len(p['threads'])==3 and all(len(t['items'])==1 for t in p['threads']) and not p['held_forbidden'], p\" '$TMP/ag3.json'"
check "brief.py --items: задачи второй волны в задании" sh -c "
  '$PY' '$BR' '$R5' --thread qa-w2-1 --items '$R5/waves/2/qa-w2-1.json' --minutes 10 >/dev/null &&
  grep -q 'вторая волна по списку «не проверено»' '$R5/briefs/qa-w2-1.md' && grep -q 'WebKit' '$R5/briefs/qa-w2-1.md'"
check "coverage again: пустой список «не проверено» — код 1" sh -c "
  mkdir -p '$TMP/r-empty' && printf '{\"run\": {}, \"findings\": []}' > '$TMP/r-empty/findings.json' &&
  test \$('$PY' '$CV' again '$TMP/r-empty' >/dev/null; echo \$?) = 1"

# ---------- #24: autopilot, data variants and stands, decisions in the journal ----------
JR="$S/journal.py"; RA="$TMP/run-auto"; mkdir -p "$RA" "$TMP/work-cwd"
check "intake --autopilot: решения по умолчанию в decisions, output_dir = папка запуска, dry-run, без «старт»" sh -c "
  cd '$TMP/work-cwd' && env -u SITE_QA_OUTPUT_DIR '$PY' '$S/intake.py' from-text --text 'Проверь https://example.com/, не нажимай «Купить»' --autopilot --json > '$TMP/ap.json' &&
  '$PY' -c \"import json,sys,os; d=json.load(open(sys.argv[1])); c=d['config']; ds=' | '.join(d['decisions'])
assert c['autopilot'] is True and c['mode']=='dry-run' and os.path.realpath(c['output_dir'])==os.path.realpath(sys.argv[2]), c
assert 'output_dir' in ds and 'направления: все' in ds and 'режим: dry-run' in ds and 'варианты данных' in ds and 'без изменений' in ds, ds
assert not any(m.startswith('output_dir') for m in d['missing']), d['missing']
assert c['rules']['forbidden_actions'][0]['texts']==['Купить'], c['rules']\" '$TMP/ap.json' '$TMP/work-cwd'"
check "intake: «автопилот» / «без вопросов» в тексте запроса включают автопилот; обычный запрос — нет" sh -c "
  env -u SITE_QA_OUTPUT_DIR '$PY' '$S/intake.py' from-text --text '/site-qa-audit автопилот: проверь https://example.com/' --output-dir '$TMP' --json | '$PY' -c \"import json,sys; assert json.load(sys.stdin)['config']['autopilot'] is True\" &&
  '$PY' '$S/intake.py' from-text --text 'Проверь https://example.com/ без вопросов' --output-dir '$TMP' --json | '$PY' -c \"import json,sys; assert json.load(sys.stdin)['config']['autopilot'] is True\" &&
  '$PY' '$S/intake.py' from-text --text 'Проверь https://example.com/' --output-dir '$TMP' --json | '$PY' -c \"import json,sys; d=json.load(sys.stdin); assert d['config']['autopilot'] is False and d['decisions']==[]\""
check "intake --autopilot --journal: решения в journal.md (РЕШЕНИЕ … [автопилот]), status показывает их" sh -c "
  '$PY' '$S/intake.py' from-text --text 'Проверь https://example.com/' --output-dir '$TMP' --autopilot --journal '$RA' --out '$RA/run-config.yaml' > '$TMP/ap.out' &&
  grep -q 'решение автопилота:' '$TMP/ap.out' && grep -q '^# Решение автопилота:' '$RA/run-config.yaml' &&
  grep -q 'РЕШЕНИЕ: .*\[автопилот\]' '$RA/journal.md' &&
  '$PY' '$JR' status '$RA' --json | '$PY' -c \"import json,sys; d=json.load(sys.stdin); assert len(d['decisions'])>=4, d\" &&
  test \$('$PY' '$UG' nav https://example.com/ --config '$RA/run-config.yaml' >/dev/null; echo \$?) = 0"
check "intake --autopilot: папка запуска — домашняя (некуда писать) — output_dir остаётся вопросом" sh -c "
  cd \"\$HOME\" && env -u SITE_QA_OUTPUT_DIR '$PY' '$S/intake.py' from-text --text 'Проверь https://example.com/' --autopilot --json | '$PY' -c \"import json,sys; d=json.load(sys.stdin); assert d['config']['output_dir'] is None and any(m.startswith('output_dir') for m in d['missing']) and any('домашняя папка' in n for n in d['notes']), d\""
check "journal decide: решение с причиной в журнале; status — счётчик решений" sh -c "
  '$PY' '$JR' decide '$RA' 'WebKit пропущен' --why 'браузер не запускается' >/dev/null &&
  grep -q 'РЕШЕНИЕ: WebKit пропущен (почему: браузер не запускается)' '$RA/journal.md' &&
  '$PY' '$JR' status '$RA' | grep -q 'решений без вопроса'"
check "intake: стенды и варианты данных — variants по хостам и пометка «включить в охват»; без них — variants []" sh -c "
  '$PY' '$S/intake.py' from-text --text 'Проверь два стенда: https://test.example.com/ и https://example.com/' --output-dir '$TMP' --json | '$PY' -c \"import json,sys; d=json.load(sys.stdin); v=d['config']['variants']; assert [x['id'] for x in v]==['test.example.com','example.com'] and all(x['kind']=='stand' for x in v), v; assert any('включить каждый в охват' in n for n in d['notes'])\" &&
  '$PY' '$S/intake.py' from-text --text 'Проверь на тестовых данных и боевых данных https://example.com/' --output-dir '$TMP' --json | '$PY' -c \"import json,sys; d=json.load(sys.stdin); assert d['config']['variants']==[] and any('variants' in n for n in d['notes'])\" &&
  '$PY' '$S/intake.py' from-text --text 'Проверь https://example.com/' --output-dir '$TMP' --json | '$PY' -c \"import json,sys; d=json.load(sys.stdin); assert d['config']['variants']==[] and not any('variants' in n for n in d['notes'])\""

# ---------- #26: groups by root cause, «Как проверить», e2e stub, screenshots to a private repo ----------
RD="$S/render_draft.py"; FG="$F/findings-groups.json"; RG="$TMP/run-groups"; mkdir -p "$RG"
check "suggest-groups: один элемент и пункт чек-листа на разных страницах/устройствах -> одна группа (F-001..F-003)" sh -c "
  '$PY' '$RD' suggest-groups '$FG' --out '$RG/groups.yaml' >/dev/null &&
  '$PY' -c \"import sys; sys.path.insert(0, sys.argv[1]); import miniyaml; g=miniyaml.load_file(sys.argv[2])['groups']; assert len(g)==1 and g[0]['findings']==['F-001','F-002','F-003'], g\" '$S/shared' '$RG/groups.yaml'"
check "group --map: issue на первопричину — проявления таблицей, шаги основного, «Как проверить» по каждому, маркер на каждую" sh -c "
  '$PY' '$RD' group '$FG' --map '$RG/groups.yaml' --run-dir '$RG' > '$TMP/gm.out' &&
  D='$RG/drafts/groups/G1.md' && grep -q '^TITLE: \[HIGH\] .*(3 проявления)' \"\$D\" && grep -q '## Проявления' \"\$D\" &&
  test \$(grep -c '^| [123] |' \"\$D\") = 3 && grep -q '## Шаги воспроизведения (основное проявление, № 1)' \"\$D\" &&
  grep -q '## Как проверить' \"\$D\" && grep -q 'Проявление 3.\*\* После сохранения ссылка' \"\$D\" &&
  test \$(grep -c 'site-qa-audit:fp=' \"\$D\") = 3 && grep -q 'не в группах 2: F-004, F-005' '$TMP/gm.out' &&
  '$PY' -c \"import json,sys; d=json.load(open(sys.argv[1])); assert d['ungrouped']==['F-004','F-005'] and d['groups'][0]['findings']==['F-001','F-002','F-003'], d\" '$RG/groups.json'"
check "group --map --disclosure none: без подписи и маркеров скила" sh -c "
  '$PY' '$RD' group '$FG' --map '$RG/groups.yaml' --run-dir '$RG' --disclosure none >/dev/null &&
  ! grep -qi 'site-qa-audit' '$RG/drafts/groups/G1.md'"
printf 'groups:\n  - id: A\n    findings: [F-001, F-099]\n' > "$TMP/g-bad1.yaml"
printf 'groups:\n  - id: A\n    findings: [F-001]\n  - id: B\n    findings: [F-001, F-002]\n' > "$TMP/g-bad2.yaml"
check "group --map: неизвестная находка и находка в двух группах — ошибка" sh -c "
  out=\$('$PY' '$RD' group '$FG' --map '$TMP/g-bad1.yaml' --run-dir '$RG' 2>&1); test \$? != 0 && echo \"\$out\" | grep -q 'F-099' &&
  out=\$('$PY' '$RD' group '$FG' --map '$TMP/g-bad2.yaml' --run-dir '$RG' 2>&1); test \$? != 0 && echo \"\$out\" | grep -q 'в двух группах'"
check "detailed: «Как проверить» — из repro (js), из шагов и ожидаемого; без данных — раздела нет" sh -c "
  '$PY' '$RD' detailed '$FG' --id F-001 | grep -A4 '## Как проверить' | grep -q 'elementFromPoint' &&
  '$PY' '$RD' detailed '$FG' --id F-005 | grep -A1 '## Как проверить' | grep -q 'ожидается — Исходные значения' &&
  ! '$PY' '$RD' detailed '$FG' --id F-004 | grep -q '## Как проверить'"
check "group --ids (мелкие одной темы): строка «Как проверить» у находки с repro" sh -c "
  '$PY' '$RD' group '$FG' --ids F-001,F-002 | grep -q 'Как проверить: На https://example.com/report (pixel7)'"
ES="$S/e2e_stub.py"
check "e2e_stub (ts): goto через BASE_URL, шаги комментариями, проверка repro.js — toBeFalsy" sh -c "
  '$PY' '$ES' '$FG' --id F-001 > '$TMP/F-001.spec.ts' &&
  grep -q \"import { test, expect } from '@playwright/test'\" '$TMP/F-001.spec.ts' && grep -q 'new URL(\"/editor\", BASE_URL)' '$TMP/F-001.spec.ts' &&
  grep -q '// 2. Нажать «Сохранить»  — TODO' '$TMP/F-001.spec.ts' && grep -q 'page.evaluate(() => (document.elementFromPoint' '$TMP/F-001.spec.ts' &&
  grep -q 'repeat-each=3' '$TMP/F-001.spec.ts'"
if command -v node >/dev/null 2>&1; then
  check "e2e_stub (js): устройство Pixel 7, рамка элемента, iframe -> frameLocator; синтаксис node --check" sh -c "
    '$PY' -c \"import json,sys; d=json.load(open(sys.argv[1])); d['findings'][1]['repro']['selector']='iframe#app >>> #apply'; json.dump(d, open(sys.argv[2],'w'))\" '$FG' '$TMP/fg2.json' &&
    '$PY' '$ES' '$TMP/fg2.json' --id F-002 --lang js --out '$TMP/F-002.spec.js' >/dev/null && node --check '$TMP/F-002.spec.js' &&
    grep -q 'devices\[\"Pixel 7\"\]' '$TMP/F-002.spec.js' && grep -q 'frameLocator(\"iframe#app\").locator(\"#apply\")' '$TMP/F-002.spec.js' &&
    grep -q 'expect(b.y > 800' '$TMP/F-002.spec.js' && '$PY' '$ES' '$FG' --id F-001 --lang js --out '$TMP/F-001.spec.js' >/dev/null && node --check '$TMP/F-001.spec.js'"
fi
check "e2e_stub: без repro — test.fixme; file:// — APP_URL и путь от каталога, без абсолютного пути; --all — только недочёты" sh -c "
  '$PY' '$ES' '$FG' --id F-005 | grep -q '^test.fixme(' &&
  mkdir -p '$RG/app' && printf 'site:\n  local_roots:\n    - %s/app\n' '$RG' > '$RG/run-config.yaml' &&
  '$PY' -c \"import json,sys,pathlib; d=json.load(open(sys.argv[1])); d['findings'][0]['url']=pathlib.Path(sys.argv[2],'app','sub','page.html').as_uri(); d['findings'][0]['repro']['url']=d['findings'][0]['url']; json.dump(d, open(sys.argv[3],'w'))\" '$FG' '$RG' '$RG/findings.json' &&
  '$PY' '$ES' '$RG/findings.json' --id F-001 > '$TMP/fl.spec.ts' && grep -q 'APP_URL' '$TMP/fl.spec.ts' && grep -q 'new URL(\"sub/page.html\"' '$TMP/fl.spec.ts' &&
  ! grep -q '$RG' '$TMP/fl.spec.ts' &&
  '$PY' '$ES' '$FG' --all --run-dir '$RG' | grep -q 'заготовок 5' && test -f '$RG/drafts/e2e/F-001.spec.ts'"
# publish_shots: fake gh api (repository info, refs, contents) — never the network
PS="$S/publish_shots.py"; RS="$TMP/run-shots"; mkdir -p "$RS/screenshots"
"$PY" -c "
import json,sys; d=json.load(open(sys.argv[1]))
d['findings'][0]['screenshots']=['screenshots/qa-vis-01.png','screenshots/qa-vis-01-annotated.png']
d['findings'][1]['screenshots']=['screenshots/qa-mob-02.png']; d['findings'][1]['evidence']={'sensitive': True}
d['findings'][2]['screenshots']=['screenshots/missing.png']
json.dump(d, open(sys.argv[2],'w'), ensure_ascii=False)" "$FG" "$RS/findings.json"
printf 'png-1' > "$RS/screenshots/qa-vis-01.png"; printf 'png-1-annotated' > "$RS/screenshots/qa-vis-01-annotated.png"; printf 'secret' > "$RS/screenshots/qa-mob-02.png"
printf '{"repos": {"owner/priv": {"private": true, "permissions": {"push": true}, "default_branch": "main", "refs": {"main": "c0ffee"}, "files": {}}, "owner/pub": {"private": false, "permissions": {"push": false}, "default_branch": "main", "refs": {"main": "c0ffee"}, "files": {}}}}' > "$TMP/gh-state.json"
export QA_GH_BIN="$HERE/helpers/fake_gh_contents.py" FAKE_GH_STATE="$TMP/gh-state.json" QA_GH_PAUSE=0
check "publish_shots plan: приватный с push — api-commit (без браузера); без push — web-upload; sensitive и пропавшие — skipped" sh -c "
  '$PY' '$PS' plan '$RS' --repo owner/priv | '$PY' -c \"import json,sys; d=json.load(sys.stdin); assert d['mode']=='api-commit' and d['private'] and [f['file'] for f in d['files']]==['screenshots/qa-vis-01-annotated.png'], d; r=sorted(x['reason'][:8] for x in d['skipped']); assert len(r)==2, d['skipped']\" &&
  '$PY' '$PS' plan '$RS' --repo owner/pub | '$PY' -c \"import json,sys; d=json.load(sys.stdin); assert d['mode']=='web-upload', d\""
check "publish_shots push без --confirm-push — пробный: ничего не загружено, печатается --screenshot-base" sh -c "
  '$PY' '$PS' push '$RS' --repo owner/priv 2> '$TMP/ps.err' | '$PY' -c \"import json,sys; d=json.load(sys.stdin); assert d['dry_run'] and d['uploads'][0]['url'].endswith('/blob/qa-screenshots/qa-screenshots/run-shots/qa-vis-01-annotated.png?raw=true'), d\" &&
  grep -q 'ПРОБНЫЙ' '$TMP/ps.err' && ! grep -q 'PUT' '$TMP/gh-state.json'"
check "publish_shots push --confirm-push: своя ветка от main, загрузка через API, shots-published.json; повтор — без изменений" sh -c "
  '$PY' '$PS' push '$RS' --repo owner/priv --confirm-push > '$TMP/ps1.json' 2>/dev/null &&
  '$PY' -c \"import json,sys; s=json.load(open(sys.argv[1]))['repos']['owner/priv']; assert s['refs']['qa-screenshots']=='c0ffee' and list(s['files'])==['qa-screenshots:qa-screenshots/run-shots/qa-vis-01-annotated.png'], s; p=json.load(open(sys.argv[2])); assert p['screenshots/qa-vis-01-annotated.png'].endswith('?raw=true'), p\" '$TMP/gh-state.json' '$RS/shots-published.json' &&
  '$PY' '$PS' push '$RS' --repo owner/priv --confirm-push 2>/dev/null | '$PY' -c \"import json,sys; d=json.load(sys.stdin); assert [u['status'] for u in d['uploads']]==['unchanged'], d\" &&
  test \$(grep -c '\"PUT\"' '$TMP/gh-state.json') = 1"
check "publish_shots push: в основную ветку — 2; репозиторий без push — 1; ошибка gh — 3" sh -c "
  test \$('$PY' '$PS' push '$RS' --repo owner/priv --branch main --confirm-push >/dev/null 2>&1; echo \$?) = 2 &&
  test \$('$PY' '$PS' push '$RS' --repo owner/pub --confirm-push >/dev/null 2>&1; echo \$?) = 1 &&
  test \$('$PY' '$PS' plan '$RS' --repo owner/none >/dev/null 2>&1; echo \$?) = 3"
unset QA_GH_BIN FAKE_GH_STATE QA_GH_PAUSE

echo "stream v1.4.0: PASS $pass, FAIL $fail"
[ $fail -eq 0 ]
