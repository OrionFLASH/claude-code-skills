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

# ---------- S-5: ingest_findings.py ----------
RUN="$TMP/run"; mkdir -p "$RUN"; cp "$CFG" "$RUN/run-config.yaml"
IF="$S/ingest_findings.py"
check "ingest: блок qa-findings -> findings.json, id F-001/F-002, not_checked, questions.json, сырое сообщение" sh -c "
  '$PY' '$IF' '$RUN' --from '$F/agent-message.md' > '$TMP/ing.json' &&
  '$PY' -c \"
import json,sys,os
r=json.load(open(sys.argv[1])); d=json.load(open(sys.argv[2]+'/findings.json'))
assert r['added']==['F-001','F-002'] and r['blocks']==1, r
f=d['findings']; assert f[0]['id']=='F-001' and f[0]['source_id']=='X-1' and 'agent:qa-ux' in f[0]['sources'], f[0]
assert d['run']['id']=='run' and d['run']['site']=='https://example.com/' and d['not_checked'][0]['thread']=='qa-ux'
assert json.load(open(sys.argv[2]+'/questions.json'))[0]['question'].startswith('Пустая')
assert any('нет repro' in w for w in r['warnings']) and os.listdir(sys.argv[2]+'/raw/messages')
\" '$TMP/ing.json' '$RUN'"
check "ingest: повтор того же сообщения — дубли пропущены, id не растут" sh -c "
  '$PY' '$IF' '$RUN' --from '$F/agent-message.md' | '$PY' -c \"import json,sys; r=json.load(sys.stdin); assert r['added']==[] and len(r['skipped'])==2, r\""
printf 'Итог\n```qa-findings\n[{"direction":"ux","check_id":"x","type":"bug","severity":"urgent","title":"t","url":"u","actual":"a","sources":["s"]},{"direction":"ux","check_id":"y","type":"bug","severity":"low","title":"ok","url":"u2","actual":"a","sources":["s"]}]\n```\n' > "$TMP/bad-msg.md"
check "ingest: неверный enum -> код 1, ничего не записано; --partial добавляет валидную" sh -c "
  n0=\$('$PY' -c \"import json; print(len(json.load(open('$RUN/findings.json'))['findings']))\");
  test \$('$PY' '$IF' '$RUN' --from '$TMP/bad-msg.md' >/dev/null; echo \$?) = 1 &&
  test \$('$PY' -c \"import json; print(len(json.load(open('$RUN/findings.json'))['findings']))\") = \$n0 &&
  '$PY' '$IF' '$RUN' --from '$TMP/bad-msg.md' --partial | grep -q 'F-003'"
check "ingest: нет блока -> код 2 и подсказка" sh -c "test \$('$PY' '$IF' '$RUN' --text 'просто текст' >/dev/null; echo \$?) = 2"
check "ingest example: формат блока для заданий" sh -c "'$PY' '$IF' example | grep -q '^\`\`\`qa-findings'"
check "validate_findings: файл после ingest проходит схему (repro, ingested, source_id)" sh -c "'$PY' '$S/validate_findings.py' '$RUN/findings.json' >/dev/null"

# ---------- S-9: recheck.py ----------
RC="$S/recheck.py"
"$PY" - "$RUN/findings.json" "$CFG" <<'PYEOF'
import json, sys
p, cfg = sys.argv[1], sys.argv[2]
d = json.load(open(p))
f = d["findings"]
# F-001: offline repro through the skill's own script; the «defect» = guard denies evil.test (exit 3)
f[0]["repro"] = {"argv": ["python3", "<SKILL_DIR>/scripts/url_guard.py", "nav", "https://evil.test/", "--config", cfg], "expect_exit": 3}
f[1]["repro"] = {"argv": ["python3", "<SKILL_DIR>/scripts/url_guard.py", "nav", "https://evil.test/", "--config", cfg], "expect_exit": 0}
f[2]["repro"] = {"argv": ["bash", "-c", "echo hi"]}
f.append(dict(f[1], id="F-004", title="error case", url="u4", repro={"argv": ["python3", "<SKILL_DIR>/scripts/url_guard.py", "nav", "https://example.com/", "--config", "<RUN_DIR>/missing.yaml"]}))
json.dump(d, open(p, "w"), ensure_ascii=False)
PYEOF
"$PY" "$RC" run "$RUN" --times 2 --pause 0 > "$TMP/rc.json"; rcode=$?
check "recheck run: confirmed (2/2), not-reproduced, refused (не скрипт скила), error (код 4) — код 1" sh -c "
  test $rcode = 1 && '$PY' -c \"
import json,sys
r={x['id']:x for x in json.load(open(sys.argv[1]))}
assert r['F-001']['status']=='confirmed' and r['F-001']['reproduced_runs']==2, r['F-001']
assert r['F-002']['status']=='not-reproduced', r['F-002']
assert r['F-003']['status']=='refused' and 'node/python' in r['F-003']['reason'], r['F-003']
assert r['F-004']['status']=='error', r['F-004']
\" '$TMP/rc.json'"
check "recheck gate: только F-001 можно публиковать; код 1" sh -c "
  out=\$('$PY' '$RC' gate '$RUN'); test \$? = 1 && echo \"\$out\" | grep -q '^F-001: можно публиковать' && echo \"\$out\" | grep -q '^F-002: НЕЛЬЗЯ'"
check "recheck set: ручная независимая перепроверка открывает gate; тем же исполнителем — нет" sh -c "
  '$PY' '$RC' set '$RUN' --id F-002 --status confirmed --by 'qa-verify: Chrome 1440, шаги 1–2' >/dev/null &&
  '$PY' '$RC' gate '$RUN' --id F-002 | grep -q 'можно публиковать' &&
  '$PY' '$RC' set '$RUN' --id F-002 --status confirmed --by 'qa-ux' --same-executor >/dev/null &&
  '$PY' '$RC' gate '$RUN' --id F-002 | grep -q 'тем же исполнителем'"
"$PY" - "$RUN/findings.json" <<'PYEOF'
import json, sys
p = sys.argv[1]; d = json.load(open(p))
d["findings"][0]["legal"] = {"claims_law": True, "norms": ["152-ФЗ ст. 9 (согласие на обработку ПДн)"]}
json.dump(d, open(p, "w"), ensure_ascii=False)
PYEOF
check "юридическое: нормы без второй проверки закрывают gate; recheck.py legal открывает" sh -c "
  '$PY' '$RC' gate '$RUN' --id F-001 | grep -q 'без второй проверки' &&
  '$PY' '$RC' legal '$RUN' --id F-001 --by 'второй исполнитель qa-legal' --result confirmed >/dev/null &&
  '$PY' '$RC' gate '$RUN' --id F-001 | grep -q 'можно публиковать'"
check "render_draft: правовые нормы — «требуется проверка юристом» в теле" sh -c "
  '$PY' '$S/render_draft.py' detailed '$RUN/findings.json' --id F-001 | grep -q 'требуется проверка юристом'"

RUN2="$TMP/run2"; mkdir -p "$RUN2"; cp "$RUN/findings.json" "$RUN2/"
printf 'version: 1\nsite:\n  start_urls: [https://example.com/]\n  allowed_domains: [example.com]\nrepos:\n  - url: owner/repo\n    roles: [write-new]\n' > "$RUN2/run-config.yaml"
check "build_report publish-table: колонка «Перепроверка», без подтверждения — «НЕ публиковать до перепроверки»" sh -c "
  out=\$('$PY' '$S/build_report.py' publish-table '$RUN2') &&
  echo \"\$out\" | grep -q '| Перепроверка |' && echo \"\$out\" | grep 'F-004' | grep -q 'НЕ публиковать до перепроверки' &&
  ! echo \"\$out\" | grep 'F-001' | grep -q 'НЕ публиковать'"

# ---------- G-5: render_draft group / groups ----------
check "render_draft group: таблица, подробности, маркер на каждую находку, тип suggestion" sh -c "
  '$PY' '$S/fingerprint.py' compute '$RUN/findings.json' >/dev/null &&
  out=\$('$PY' '$S/render_draft.py' group '$RUN/findings.json' --ids F-002,F-004 --type suggestion) &&
  echo \"\$out\" | grep -q '^TITLE: \[.*\] Предложения: ' && echo \"\$out\" | grep -q '| № | Где | Сейчас | Предлагаю | Скриншот |' &&
  test \$(echo \"\$out\" | grep -c 'site-qa-audit:fp=') = 2 && echo \"\$out\" | grep -q '^### 2. '"
check "render_draft group: меньше двух id -> ошибка; --body-only печатает TITLE и пишет только тело" sh -c "
  ! '$PY' '$S/render_draft.py' group '$RUN/findings.json' --ids F-002 >/dev/null 2>&1 &&
  '$PY' '$S/render_draft.py' group '$RUN/findings.json' --ids F-002,F-004 --body-only --out '$TMP/g.md' | grep -q '^TITLE: ' && ! grep -q '^TITLE:' '$TMP/g.md'"
check "render_draft groups: мелкие находки по темам -> drafts/groups/" sh -c "
  '$PY' '$S/render_draft.py' groups '$RUN/findings.json' --run-dir '$RUN' >/dev/null && ls '$RUN/drafts/groups/' | grep -q '^01-'"
check "fingerprint match: issue с несколькими маркерами находит каждую находку" sh -c "
  '$PY' '$S/render_draft.py' group '$RUN/findings.json' --ids F-002,F-004 --body-only --out '$TMP/grp.md' >/dev/null &&
  '$PY' -c \"import json,sys; json.dump({'issues':[{'repo':'owner/repo','number':7,'title':'g','body':open(sys.argv[1]).read(),'state':'open','comments':[]}]}, open(sys.argv[2],'w'))\" '$TMP/grp.md' '$RUN/registry.json' &&
  '$PY' '$S/fingerprint.py' match '$RUN/findings.json' '$RUN/registry.json' --out '$TMP/m.json' >/dev/null &&
  '$PY' -c \"import json,sys; m={r['id']:r for r in json.load(open(sys.argv[1]))}; assert m['F-002']['exact'][0]['number']==7 and m['F-004']['exact'][0]['number']==7\" '$TMP/m.json'"

# ---------- G-6: direct_publish.py ----------
DP="$S/direct_publish.py"
printf '{"issues": []}' > "$RUN/registry.json"
check "direct check: F-001 (подтверждена, вторая проверка) -> 0, команды публикации и вопрос при confirm_before_publish" sh -c "
  '$PY' '$DP' check '$RUN' --id F-001 --repo owner/repo > '$TMP/dp.json'; test \$? = 0 &&
  '$PY' -c \"import json,sys; d=json.load(open(sys.argv[1])); assert any('gh issue create' in c for c in d['commands']) and d['ask'], d\" '$TMP/dp.json'"
check "direct check: F-004 без подтверждения -> 1 (gate)" test "$(rc "$PY" "$DP" check "$RUN" --id F-004 --repo owner/repo)" = 1
check "direct check: нет выгрузки issues -> 1" test "$(rc "$PY" "$DP" check "$RUN" --id F-001 --repo owner/repo --registry "$TMP/none.json")" = 1
"$PY" -c "import json,sys; d=json.load(open(sys.argv[1])); f=d['findings'][0]; json.dump({'issues':[{'repo':'owner/repo','number':3,'title':f['title'],'body':f.get('actual',''),'state':'open','comments':[]}]}, open(sys.argv[2],'w'), ensure_ascii=False)" "$RUN/findings.json" "$TMP/reg-fuzzy.json"
check "direct check: похожий issue -> 2 (прочитать), --ack-candidates -> 0" sh -c "
  test \$('$PY' '$DP' check '$RUN' --id F-001 --repo owner/repo --registry '$TMP/reg-fuzzy.json' >/dev/null; echo \$?) = 2 &&
  test \$('$PY' '$DP' check '$RUN' --id F-001 --repo owner/repo --registry '$TMP/reg-fuzzy.json' --ack-candidates >/dev/null; echo \$?) = 0"
check "direct record -> published.json и finding.published; повторный check -> 3; next пропускает опубликованное" sh -c "
  '$PY' '$DP' record '$RUN' --id F-001 --repo owner/repo --number 12 --url https://github.com/owner/repo/issues/12 >/dev/null &&
  test \$('$PY' '$DP' check '$RUN' --id F-001 --repo owner/repo >/dev/null; echo \$?) = 3 &&
  '$PY' '$DP' status '$RUN' | grep -q 'F-001 -> owner/repo#12' &&
  '$PY' '$DP' next '$RUN' --repo owner/repo | grep -vq 'F-001'"

# ---------- G-3/G-4: claims.py preconditions ----------
check "claims plan: предусловия аккаунта у пункта и сводка в начале плана" sh -c "
  '$PY' '$S/claims.py' plan '$F/registry-claims.json' --out '$TMP/plan.md' --json '$TMP/rechecks.json' >/dev/null;
  grep -q '^## Предусловия аккаунта' '$TMP/plan.md' && grep -q 'Предусловия:' '$TMP/plan.md' &&
  '$PY' -c \"import json,sys; r=json.load(open(sys.argv[1]))['rechecks']; assert all('preconditions' in x for x in r)\" '$TMP/rechecks.json'"
check "claims plan --account-states guest,free: пункты с Pro помечены «нет состояния»" sh -c "
  '$PY' '$S/claims.py' plan '$F/registry-claims.json' --account-states guest,free --out '$TMP/plan2.md' >/dev/null;
  grep -q 'нет нужного состояния аккаунта (с Pro' '$TMP/plan2.md' && grep -q 'Не хватает: с Pro' '$TMP/plan2.md'"

# ---------- intake.py: legal-ui, paid tiers, publish_mode ----------
check "intake: «законодательство РФ, cookie-баннер» -> legal-ui; Pro -> paid_tiers и заметка о двух состояниях; «сразу в репозиторий» -> direct" sh -c "
  '$PY' '$S/intake.py' from-text --text 'Протестируй https://example.com/ по законодательству РФ: cookie-баннер, без Pro и с Pro, заводи сразу в репозиторий owner/repo' --json |
  '$PY' -c \"
import json,sys; d=json.load(sys.stdin); c=d['config']
assert 'legal-ui' in c['directions'] and c['auth']['paid_tiers']==['pro'] and c['publish_mode']=='direct', c
assert set(c['auth']['account_states'])>={'free','pro'} and any('двух' in n or 'каждом состоянии' in n for n in d['notes']), d['notes']\""
check "intake: обычный запрос -> без legal-ui, publish_mode batch" sh -c "
  '$PY' '$S/intake.py' from-text --text 'Протестируй https://example.com/ на телефоне, не очищай cookie' --json |
  '$PY' -c \"import json,sys; c=json.load(sys.stdin)['config']; assert 'legal-ui' not in c['directions'] and c['publish_mode']=='batch', c\""

# ---------- S-6/S-7: tabs.py ----------
TB="$S/tabs.py"; TR="$TMP/run-tabs"; mkdir -p "$TR"
check "tabs open: одна вкладка на профиль — вторая -> код 3 и запись существующей" sh -c "
  '$PY' '$TB' open '$TR' --owner qa-ux --profile pixel7 --tool cli --url https://example.com/ | grep -q '\"id\": \"T-001\"' &&
  out=\$('$PY' '$TB' open '$TR' --owner qa-ux --profile pixel7 --tool cli); test \$? = 3 && echo \"\$out\" | grep -q 'используйте эту' &&
  '$PY' '$TB' open '$TR' --owner qa-ux --profile desktop --tool cli >/dev/null &&
  '$PY' '$TB' open '$TR' --owner qa-a11y --profile pixel7 --tool cli >/dev/null"
CDPP="$("$PY" -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()')"
printf '{"pages": [{"id": "U1", "type": "page", "url": "https://example.com/"}, {"id": "U2", "type": "page", "url": "https://example.com/"}, {"id": "Q9", "type": "page", "url": "https://example.com/map"}, {"id": "M1", "type": "page", "url": "https://mail.example/inbox"}]}' > "$TMP/cdp.json"
"$PY" "$HERE/helpers/fake_cdp.py" "$CDPP" "$TMP/cdp.json" & CDPPID=$!
for _ in 1 2 3 4 5 6 7 8 9 10; do "$PY" -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:$CDPP/json/list')" 2>/dev/null && break; sleep 0.2; done
"$PY" "$TB" open "$TR" --owner qa-ux --profile phone-tab --tool cdp --target-id Q9 --url https://example.com/map >/dev/null
check "tabs audit: дубли одного URL и незарегистрированные вкладки сайта; ничего не закрыто" sh -c "
  '$PY' '$TB' audit '$TR' --cdp http://127.0.0.1:$CDPP --domains example.com | '$PY' -c \"
import json,sys; d=json.load(sys.stdin)
assert d['duplicates'][0]['count']==2 and d['site_pages']==3 and len(d['unregistered_site_tabs'])==2, d\" &&
  '$PY' -c \"import json; assert len(json.load(open('$TMP/cdp.json'))['pages'])==4\""
check "tabs cleanup: без --yes — только план; --yes закрывает только свою CDP-вкладку (Q9), CLI — команда close своей сессии" sh -c "
  '$PY' '$TB' cleanup '$TR' --owner qa-ux --cdp http://127.0.0.1:$CDPP | grep -q 'playwright-cli -s=qa-ux close' &&
  '$PY' -c \"import json; assert len(json.load(open('$TMP/cdp.json'))['pages'])==4\" &&
  '$PY' '$TB' cleanup '$TR' --owner qa-ux --cdp http://127.0.0.1:$CDPP --yes >/dev/null &&
  '$PY' -c \"import json; s=json.load(open('$TMP/cdp.json')); assert s['closed']==['Q9'] and len(s['pages'])==3, s\""
check "tabs close/list: вкладки помечаются закрытыми; чужие (qa-a11y) не тронуты" sh -c "
  '$PY' '$TB' close '$TR' --owner qa-ux >/dev/null && '$PY' '$TB' list '$TR' --open --json | '$PY' -c \"
import json,sys; t=json.load(sys.stdin); assert [x['owner'] for x in t]==['qa-a11y'], t\""
{ kill "$CDPPID"; wait "$CDPPID"; } 2>/dev/null

# ---------- documentation: command examples are accepted by the scripts ----------
check "примеры python-команд в SKILL.md, README, INSTALL, references принимаются argparse (--help)" sh -c "
  '$PY' '$HERE/helpers/doc_commands.py' '$HERE/..' --python '$PY' > '$TMP/doc.out' 2>&1 || { cat '$TMP/doc.out'; exit 1; }"
check "примеры node-команд в документации: скрипты существуют, --опции читаются" sh -c "
  '$PY' '$HERE/helpers/doc_node_flags.py' '$HERE/..' > '$TMP/docn.out' 2>&1 || { cat '$TMP/docn.out'; exit 1; }"
mkdir -p "$TMP/fake-skill/scripts/node"; printf 'const a = parseArgs(); if (a.yes) {}\n' > "$TMP/fake-skill/scripts/node/x.js"
printf -- '---\nname: x\n---\n`node <SKILL_DIR>/scripts/node/x.js --yes --nope`\n`node <SKILL_DIR>/scripts/node/missing.js`\n' > "$TMP/fake-skill/SKILL.md"
check "doc_node_flags (негативный): неизвестная опция и несуществующий скрипт — ошибки" sh -c "
  out=\$('$PY' '$HERE/helpers/doc_node_flags.py' '$TMP/fake-skill'); test \$? = 1 && echo \"\$out\" | grep -q -- '--nope' && echo \"\$out\" | grep -q 'missing.js' && ! echo \"\$out\" | grep -q -- 'не читает --yes'"
check "SKILL.md: ≤ 300 строк, пример shot.js «селектор|подпись» в первых 40 строках" sh -c "
  test \$(wc -l < '$HERE/../SKILL.md') -le 300 && head -40 '$HERE/../SKILL.md' | grep -q 'shot.js' && head -40 '$HERE/../SKILL.md' | grep -q '\"#menu|'"

echo "stream v1.3.0: PASS $pass, FAIL $fail"; [ $fail -eq 0 ]
