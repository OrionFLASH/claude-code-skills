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

echo "stream v1.4.0: PASS $pass, FAIL $fail"
[ $fail -eq 0 ]
