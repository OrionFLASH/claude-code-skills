#!/usr/bin/env bash
# Offline tests for 1.2.1: results folder in .gitignore by default (gitignore_helper.py ensure / untrack, shared
# qa_gitignore.py), explicit permission to commit results in intake.py (git.allow_commit_results), export_results.py
# (report_destinations: folder — final files only), SKILL.md without the end-of-run .gitignore question.
# No network, no browser; git parts are skipped without git. Temporary repos only (isolated HOME, no global git config).
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; S="$HERE/../scripts"; T="$HERE/../templates"
if command -v python3 >/dev/null 2>&1; then PY=python3; else PY=python; fi
export PYTHONDONTWRITEBYTECODE=1
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
pass=0; fail=0
ok(){ echo "PASS $1"; pass=$((pass+1)); }; bad(){ echo "FAIL $1"; fail=$((fail+1)); }
check(){ local name="$1"; shift; if "$@"; then ok "$name"; else bad "$name"; fi; }
rc(){ "$@" >/dev/null 2>&1; echo $?; }
GH="$S/gitignore_helper.py"

if command -v git >/dev/null 2>&1; then
  export HOME="$TMP/home" XDG_CONFIG_HOME="$TMP/home/.config" GIT_CONFIG_NOSYSTEM=1
  mkdir -p "$HOME" "$TMP/plain" "$TMP/r1" "$TMP/r2" "$TMP/r3" "$TMP/r4/qa-runs/2026-10-08-example.com"
  for r in r1 r2 r3 r4; do git -C "$TMP/$r" init -q; done
  "$PY" "$GH" ensure "$TMP/r1/site/out" > "$TMP/r1.out" 2>&1; c=$?
  check "ensure по умолчанию: qa-runs/ в .gitignore до создания папки (её ещё нет), только qa-runs/" sh -c "
    test $c = 0 && grep -q '^/site/out/qa-runs/\$' '$TMP/r1/.gitignore' && ! grep -q apk '$TMP/r1/.gitignore' && test ! -e '$TMP/r1/site' &&
    '$PY' '$GH' ensure '$TMP/r1/site/out' >/dev/null && test \$(grep -c qa-runs '$TMP/r1/.gitignore') = 1 &&
    git -C '$TMP/r1' check-ignore -q --no-index site/out/qa-runs/2026-10-08-example.com/report.md"
  check "ensure --allow-commit-results: .gitignore не создаётся" sh -c "'$PY' '$GH' ensure '$TMP/r2' --allow-commit-results >/dev/null && test ! -e '$TMP/r2/.gitignore'"
  check "ensure --text: «коммить результаты» — не трогать; «не коммить результаты» — в .gitignore" sh -c "
    '$PY' '$GH' ensure '$TMP/r2' --text 'Протестируй https://example.com/ и коммить результаты' >/dev/null && test ! -e '$TMP/r2/.gitignore' &&
    '$PY' '$GH' ensure '$TMP/r2' --text 'Протестируй https://example.com/, результаты не коммить' >/dev/null && grep -q '^/qa-runs/\$' '$TMP/r2/.gitignore'"
  printf 'git:\n  allow_commit_results: true\n' > "$TMP/rc-allow.yaml"
  check "ensure --config: git.allow_commit_results: true из run-config — не трогать" sh -c "'$PY' '$GH' ensure '$TMP/r3' --config '$TMP/rc-allow.yaml' >/dev/null && test ! -e '$TMP/r3/.gitignore'"
  echo x > "$TMP/r4/qa-runs/2026-10-08-example.com/report.md"
  git -C "$TMP/r4" add -A && git -C "$TMP/r4" -c user.name=t -c user.email=t@example.com commit -qm init
  "$PY" "$GH" ensure "$TMP/r4" --json > "$TMP/r4.json" 2>&1; c=$?
  check "ensure: qa-runs/ уже в индексе -> код 1, команда git rm --cached, файлы не удалены" sh -c "
    test $c = 1 && '$PY' -c \"import json,sys; d=json.load(open(sys.argv[1])); t=d['tracked_results'][0]; assert t['files']==1 and 'rm -r --cached' in t['command'], d\" '$TMP/r4.json' &&
    test -n \"\$(git -C '$TMP/r4' ls-files qa-runs)\" && grep -q '^/qa-runs/\$' '$TMP/r4/.gitignore'"
  check "untrack: без --yes — план; с --yes — убрано из индекса, файл на диске; потом ensure -> 0" sh -c "
    '$PY' '$GH' untrack '$TMP/r4' | grep -q 'План' && test -n \"\$(git -C '$TMP/r4' ls-files qa-runs)\" &&
    '$PY' '$GH' untrack '$TMP/r4' --yes >/dev/null && test -z \"\$(git -C '$TMP/r4' ls-files qa-runs)\" &&
    test -f '$TMP/r4/qa-runs/2026-10-08-example.com/report.md' && '$PY' '$GH' ensure '$TMP/r4' >/dev/null"
  check "ensure вне git -> 0, ничего не создано" sh -c "'$PY' '$GH' ensure '$TMP/plain/out' >/dev/null && test ! -e '$TMP/plain/out' && test ! -e '$TMP/plain/.gitignore'"
else
  echo "SKIP gitignore_helper ensure: нет git"
fi

# intake.py: git.allow_commit_results — only an explicit permission
gv(){ "$PY" "$S/intake.py" from-text --text "$1" --json | "$PY" -c "import json,sys; print(json.load(sys.stdin)['config']['git']['allow_commit_results'])"; }
check "intake: по умолчанию git.allow_commit_results false" test "$(gv 'Протестируй https://example.com/')" = False
check "intake: «положи результаты в репозиторий» -> true" test "$(gv 'Протестируй https://example.com/ и положи результаты в репозиторий')" = True
check "intake: «commit the results» -> true" test "$(gv 'Test https://example.com/ and commit the results')" = True
check "intake: «не коммить результаты» и «добавь qa-runs в .gitignore» -> false" sh -c "
  test \"\$(\"$PY\" \"$S/intake.py\" from-text --text 'Протестируй https://example.com/, не коммить результаты' --json | \"$PY\" -c \"import json,sys; print(json.load(sys.stdin)['config']['git']['allow_commit_results'])\")\" = False &&
  test \"\$(\"$PY\" \"$S/intake.py\" from-text --text 'Протестируй https://example.com/ и добавь qa-runs в .gitignore' --json | \"$PY\" -c \"import json,sys; print(json.load(sys.stdin)['config']['git']['allow_commit_results'])\")\" = False"
check "intake: «не добавляй qa-runs в .gitignore» — разрешение, а не запрет кнопки" sh -c "
  '$PY' '$S/intake.py' from-text --text 'Протестируй https://example.com/. Не добавляй qa-runs в .gitignore.' --json | '$PY' -c \"
import json,sys; d=json.load(sys.stdin); assert d['config']['git']['allow_commit_results'] is True and d['config']['rules']['forbidden_actions']==[], d['config']\""

"$PY" "$S/shared/miniyaml.py" "$T/run-config.example.yaml" > "$TMP/rc.json"
check "run-config.example.yaml: git.allow_commit_results: false" "$PY" -c "
import json,sys; d=json.load(open(sys.argv[1])); assert d['git']=={'allow_commit_results': False}, d.get('git')" "$TMP/rc.json"

# export_results.py: report_destinations: folder — final files only
R="$TMP/qa-runs/2026-10-08-example.com"; mkdir -p "$R/screenshots" "$R/raw" "$R/logs" "$R/drafts/owner__repo"
printf '# report\n' > "$R/report.md"; printf '# summary\n' > "$R/summary.md"
printf '{"findings": [{"id": "F-001", "screenshots": ["screenshots/F-001-annotated.png", "raw/a11y.json"]}]}' > "$R/findings.json"
for f in screenshots/F-001-annotated.png screenshots/F-001.png raw/a11y.json logs/auth-state.json logs/blocked.jsonl drafts/owner__repo/01.md journal.md run-config.yaml; do echo "$f" > "$R/$f"; done
"$PY" "$S/export_results.py" "$R" --to "$TMP/dest" > "$TMP/ex.out" 2>&1; c=$?
D="$TMP/dest/2026-10-08-example.com"
check "export_results: только summary.md, report.md, findings.json и скриншоты находок; без raw/, logs/, drafts/" sh -c "
  test $c = 0 && test -f '$D/summary.md' && test -f '$D/report.md' && test -f '$D/findings.json' && test -f '$D/screenshots/F-001-annotated.png' &&
  test ! -e '$D/screenshots/F-001.png' && test ! -e '$D/raw' && test ! -e '$D/logs' && test ! -e '$D/drafts' && test ! -e '$D/journal.md' &&
  test \$(find '$D' -type f | wc -l) -eq 4"
check "export_results: конфликт имён -> 1 без записи; повтор с тем же содержимым -> 0" sh -c "
  '$PY' '$S/export_results.py' '$R' --to '$TMP/dest' >/dev/null && echo other > '$D/summary.md' &&
  test \$('$PY' '$S/export_results.py' '$R' --to '$TMP/dest' >/dev/null 2>&1; echo \$?) = 1 && grep -q other '$D/summary.md'"

# SKILL.md: .gitignore is set before the run folder, no question at the end
check "SKILL.md: ensure до создания RUN_DIR, без вопроса «Добавить qa-runs/ в .gitignore» в конце" sh -c "
  grep -q 'gitignore_helper.py ensure' '$HERE/../SKILL.md' && ! grep -q 'Добавить qa-runs/ в .gitignore этого репозитория' '$HERE/../SKILL.md' &&
  grep -q 'export_results.py' '$HERE/../SKILL.md'"

echo "stream v1.2.1: PASS $pass, FAIL $fail"; [ $fail -eq 0 ]
