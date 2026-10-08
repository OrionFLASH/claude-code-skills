#!/usr/bin/env bash
# Offline tests for 1.2.0: gitignore_helper.py (qa-runs/ and git), intake.py parallel.max_workers <= 4,
# run-config sections goal/context/report_destinations, build_report.py summary, templates/site-context.md.
# No network, no browser; git parts are skipped without git. Temporary repos only (isolated HOME, no global git config).
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; S="$HERE/../scripts"; F="$HERE/fixtures"; T="$HERE/../templates"
if command -v python3 >/dev/null 2>&1; then PY=python3; else PY=python; fi
export PYTHONDONTWRITEBYTECODE=1
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
pass=0; fail=0
ok(){ echo "PASS $1"; pass=$((pass+1)); }; bad(){ echo "FAIL $1"; fail=$((fail+1)); }
check(){ local name="$1"; shift; if "$@"; then ok "$name"; else bad "$name"; fi; }
rc(){ "$@" >/dev/null 2>&1; echo $?; }

# gitignore_helper.py
GH="$S/gitignore_helper.py"
check "gitignore_helper: синтаксис" "$PY" -c "import ast,sys; ast.parse(open(sys.argv[1],encoding='utf-8').read())" "$GH"
if command -v git >/dev/null 2>&1; then
  # isolate from the user's global excludes and config
  export HOME="$TMP/home" XDG_CONFIG_HOME="$TMP/home/.config" GIT_CONFIG_NOSYSTEM=1
  mkdir -p "$HOME" "$TMP/plain" "$TMP/repo/qa-runs/2026-10-08-example.com" "$TMP/repo/proj/sub" "$TMP/neg/qa-runs" "$TMP/tracked/qa-runs/r"
  check "gitignore check: папка вне git -> 0" test "$(rc "$PY" "$GH" check "$TMP/plain")" = 0
  check "gitignore check: нет папки -> 2" test "$(rc "$PY" "$GH" check "$TMP/nope")" = 2
  git -C "$TMP/repo" init -q
  check "gitignore check: в репозитории, qa-runs/ не игнорируется -> 1" test "$(rc "$PY" "$GH" check "$TMP/repo")" = 1
  check "gitignore check --json: путь и шаблон" sh -c "'$PY' '$GH' check '$TMP/repo' --json | '$PY' -c \"
import json,sys; d=json.load(sys.stdin); assert d['in_repo'] and d['path']=='qa-runs/' and d['pattern']=='/qa-runs/' and not d['ignored'], d\""
  check "gitignore apply --mode gitignore -> 0" test "$(rc "$PY" "$GH" apply "$TMP/repo" --mode gitignore)" = 0
  "$PY" "$GH" apply "$TMP/repo" --mode gitignore >/dev/null 2>&1
  check "gitignore apply: идемпотентно (строка одна), check -> 0" sh -c \
    "test \$(grep -c '^/qa-runs/\$' '$TMP/repo/.gitignore') = 1 && '$PY' '$GH' check '$TMP/repo' >/dev/null"
  check "gitignore apply --mode exclude (подпапка): только .git/info/exclude" sh -c \
    "'$PY' '$GH' apply '$TMP/repo/proj/sub' --mode exclude >/dev/null && grep -q '^/proj/sub/qa-runs/\$' '$TMP/repo/.git/info/exclude' && ! grep -q 'proj/sub' '$TMP/repo/.gitignore' && '$PY' '$GH' check '$TMP/repo/proj/sub' >/dev/null"
  git -C "$TMP/neg" init -q; printf '!qa-runs/\n' > "$TMP/neg/.gitignore"
  check "gitignore apply: перекрыто правилом «!» -> 1" test "$(rc "$PY" "$GH" apply "$TMP/neg" --mode exclude)" = 1
  check "gitignore apply --mode keep: ответ запомнен, check -> 0" sh -c \
    "'$PY' '$GH' apply '$TMP/neg' --mode keep >/dev/null && grep -q '^keep ' '$TMP/neg/qa-runs/.gitignore-decision' && '$PY' '$GH' check '$TMP/neg' >/dev/null"
  git -C "$TMP/tracked" init -q; echo x > "$TMP/tracked/qa-runs/r/report.md"
  git -C "$TMP/tracked" add -A && git -C "$TMP/tracked" -c user.name=t -c user.email=t@example.com commit -qm init
  "$PY" "$GH" apply "$TMP/tracked" --mode gitignore > "$TMP/tracked.out" 2>&1; c=$?
  check "gitignore: файлы уже в индексе — игнор добавлен, git rm --cached только подсказан" sh -c \
    "test $c = 0 && grep -q 'rm -r --cached' '$TMP/tracked.out' && test -n \"\$(git -C '$TMP/tracked' ls-files qa-runs)\""
  check "gitignore apply: неверный режим -> 2" test "$(rc "$PY" "$GH" apply "$TMP/repo" --mode bad)" = 2
  check "gitignore apply: вне git -> 2" test "$(rc "$PY" "$GH" apply "$TMP/plain" --mode gitignore)" = 2
else
  echo "SKIP gitignore_helper: нет git"
fi

# intake.py: parallel.max_workers in 1..4
mw(){ "$PY" "$S/intake.py" from-text --text "$1" --json | "$PY" -c "import json,sys; print(json.load(sys.stdin)['config']['parallel']['max_workers'])"; }
check "intake: потоки по умолчанию 2" test "$(mw 'Протестируй https://example.com/')" = 2
check "intake: «в 3 потока» -> 3" test "$(mw 'Протестируй https://example.com/ в 3 потока')" = 3
check "intake: «четыре потока» -> 4" test "$(mw 'Протестируй https://example.com/ в четыре потока')" = 4
check "intake: «8 параллельных потоков» -> 4 и заметка" sh -c "'$PY' '$S/intake.py' from-text --text 'Протестируй https://example.com/ в 8 параллельных потоков' --json | '$PY' -c \"
import json,sys; d=json.load(sys.stdin); assert d['config']['parallel']['max_workers']==4; assert any('максимум 4' in n for n in d['notes']), d['notes']\""
check "intake: вход через CDP и «4 потока» -> 1" test "$(mw 'Проверь https://example.com/, подключись к моему браузеру через CDP, 4 потока')" = 1
check "intake: «последовательно» -> 1" test "$(mw 'Протестируй https://example.com/ последовательно')" = 1
check "intake: «последовательность шагов» не про потоки -> 2" test "$(mw 'Проверь последовательность шагов оформления на https://example.com/')" = 2

# run-config.example.yaml: 1.2.0 sections
"$PY" "$S/shared/miniyaml.py" "$T/run-config.example.yaml" > "$TMP/rc.json"
check "run-config.example.yaml: goal, context, report_destinations, max_workers 1..4" "$PY" -c "
import json,sys; d=json.load(open(sys.argv[1]))
assert 1 <= d['parallel']['max_workers'] <= 4 and d['parallel']['max_workers'] == 2, d['parallel']
assert d['goal']['focus'] == ['main-flows'] and d['goal']['success'] == 'findings'
assert d['context']['reuse'] == 'new' and d['context']['sources'][0]['type'] == 'site'
assert d['report_destinations'] == [{'type': 'local'}]
" "$TMP/rc.json"

# build_report.py summary
RUN="$TMP/run"; mkdir -p "$RUN"
cp "$F/findings-v11.json" "$RUN/findings.json"; cp "$F/run-config-foreign.yaml" "$RUN/run-config.yaml"
"$PY" "$S/build_report.py" summary "$RUN" >/dev/null
check "build_report summary: итог и статистика без таблицы находок, ссылка на report.md" "$PY" -c "
import sys; t=open(sys.argv[1], encoding='utf-8').read()
assert '## Итог' in t and '## Статистика' in t and '## По направлениям' in t
assert '## Находки' not in t and '\`report.md\` рядом' in t and '{{' not in t
" "$RUN/summary.md"
check "build_report summary: нет findings.json -> код 2" test "$(rc "$PY" "$S/build_report.py" summary "$TMP/empty-run")" = 2

# templates/site-context.md
check "site-context.md: разделы памяти о сайте и правило «не хранить»" "$PY" -c "
import sys; t=open(sys.argv[1], encoding='utf-8').read()
for h in ['## Назначение', '## Роли и состояния аккаунта', '## Основные сценарии', '## Терминология',
          '## Известные особенности и ограничения', '## Источники', '## История']:
    assert h in t, h
assert 'Не хранить' in t
" "$T/site-context.md"

echo "stream v1.2: PASS $pass, FAIL $fail"; [ $fail -eq 0 ]
