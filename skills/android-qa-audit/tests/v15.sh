# 1.5.0 tests — sourced by tests/unit.sh after v13.sh (uses its PY, S, F, TMP, HERE, H, check, rc, pyok, fake adb/node).
# Clips of findings: clip-start / clip-stop / clip (steps through guard) / clip-rolling, show_touches always returned
# (error, interruption, restore-only, stale state, cleanup), black screen, frames fallback, caption plaque, static tail,
# finding.py clip / clip-viewed, validate_findings, render_draft, build_report, export, attachments, soak --clips-on-crash,
# check_env, intake. Tests that need ffmpeg are SKIP without it; the no-ffmpeg path is tested with a PATH without it.
R15="$TMP/run-15"; mkdir -p "$R15"; cp "$F/run-config.yaml" "$R15/run-config.yaml"
D15="--serial emulator-5554 --run-dir $R15"
FF=$("$PY" -c "import sys; sys.path.insert(0, sys.argv[1]); import qa_clips; print(qa_clips.find_ffmpeg() or '')" "$S/shared")
skip(){ echo "SKIP $1 (нет ffmpeg)"; }
touches(){ "$PY" -c "import json,sys; print(json.load(open(sys.argv[1])).get('show_touches', '0'))" "$FAKE_ADB_STATE/settings-$1.json" 2>/dev/null || echo 0; }
jq1(){ "$PY" -c "import json,sys; d=json.load(open(sys.argv[1])); print(eval(sys.argv[2], {'d': d}))" "$@" 2>/dev/null; }
NOFF="/usr/bin:/bin"     # PATH without ffmpeg (Homebrew / Linuxbrew live elsewhere): the no-ffmpeg path
export ANDROID_QA_CLIP_OFFLINE_WAIT=1
"$PY" "$S/finding.py" add "$R15" --id F-001 --title "Меню закрывается само" --severity medium --direction functional \
  --screen com.example.app.MainActivity --actual "Меню закрывается через 0,4 с" --step "Открыть меню" >/dev/null
"$PY" "$S/finding.py" add "$R15" --id F-002 --title "Анимация дёргается" --severity low --direction visual-ui \
  --screen com.example.app.MainActivity --actual "рывки" >/dev/null
if [ -n "$FF" ]; then
  "$FF" -y -hide_banner -loglevel error -f lavfi -i testsrc2=size=720x1600:rate=30 -t 5 -c:v libx264 -pix_fmt yuv420p "$TMP/rec5.mp4"
  "$FF" -y -hide_banner -loglevel error -f lavfi -i testsrc2=size=720x1600:rate=30 -t 1 -c:v libx264 -pix_fmt yuv420p "$TMP/rec1.mp4"
  "$FF" -y -hide_banner -loglevel error -f lavfi -i color=black:size=720x1600:rate=30 -t 3 -c:v libx264 -pix_fmt yuv420p "$TMP/black.mp4"
  "$FF" -y -hide_banner -loglevel error -f lavfi -i testsrc2=size=1080x2400 -frames:v 1 "$TMP/screen.png"
  "$FF" -y -hide_banner -loglevel error -f lavfi -i testsrc2=size=720x1600:rate=30 -f lavfi -i sine=duration=3 -t 3 \
    -c:v libx264 -pix_fmt yuv420p -c:a aac "$TMP/withaudio.mp4"
  export FAKE_ADB_SCREENRECORD_FILE="$TMP/rec5.mp4"
fi

# ---------- shared module and its check ----------
check "qa_clips: общий модуль и его проверка (настройки, auto, сжатие, GIF, лента, запись в находку)" \
  "$PY" "$H/shared/qa_clips_check.py" "$S/shared"
check "qa_clips_check.py совпадает с shared/tests (в репозитории; установленный скил — пропуск)" sh -c "
  R='$HERE/../../../shared/tests'; test -d \"\$R\" || exit 0; cmp -s \"\$R/qa_clips_check.py\" '$H/shared/qa_clips_check.py'"

# ---------- clip-start / clip-stop ----------
"$PY" "$S/adb_helpers.py" clip-start --name F-001-menu $D15 > "$TMP/c1.json"; c=$?; t1=$(touches emulator-5554)
check "clip-start: код 0, состояние raw/clip-<serial>.json (PID, прежний show_touches), касания включены на эмуляторе прогона" sh -c "
  test $c = 0 && test '$t1' = 1 && grep -q '\"show_touches_before\": \"0\"' '$R15/raw/clip-emulator-5554.json' &&
  grep -q '\"host_pid\": [0-9]' '$R15/raw/clip-emulator-5554.json' && grep -q '\"size\": \[720, 1600\]' '$TMP/c1.json'"
check "clip-start: второй старт на том же стенде — код 2 «уже идёт запись»" sh -c "
  out=\$('$PY' '$S/adb_helpers.py' clip-start --name again $D15); test \$? = 2 && echo \"\$out\" | grep -q 'уже идёт запись'"
check "adb: screenrecord --time-limit --size --bit-rate во временный /sdcard/qa-clip-*.mp4" \
  grep -q '"shell", "screenrecord", "--time-limit", "10", "--size", "720x1600", "--bit-rate", "2000000", "/sdcard/qa-clip-F-001-menu.mp4"' "$FAKE_ADB_LOG"
if [ -n "$FF" ]; then
  "$PY" "$S/adb_helpers.py" clip-stop --finding F-001 --caption "Меню закрывается через 0,4 с" --mark "100,300,600,200|Меню|error" \
    --step "Открыть меню" $D15 > "$TMP/c2.json"; c=$?; t2=$(touches emulator-5554)
  check "clip-stop: SIGINT (kill -2 PID), pull, rm на устройстве; show_touches возвращён; состояние убрано" sh -c "
    test $c = 0 && test '$t2' = 0 && grep -q '\"shell\", \"kill -2 [0-9]*\"' '$FAKE_ADB_LOG' && test ! -f '$FAKE_ADB_STATE/remote/qa-clip-F-001-menu.mp4' &&
    test ! -f '$R15/raw/clip-emulator-5554.json' && grep -q '\"restored\": true' '$TMP/c2.json'"
  check "clip-stop: clips/F-001-menu.mp4 ≤ 3 МБ, без звука, h264, GIF, постер, лента кадров; исходник удалён" pyok "
import json, subprocess, sys; from pathlib import Path
r = Path(sys.argv[1]); d = json.load(open(sys.argv[2])); c = d['clip']
assert d['ok'] and c['file'] == 'clips/F-001-menu.mp4' and c['audio'] is False and c['codec'] == 'h264', c
assert (r / c['file']).stat().st_size <= 3 * 1048576 and (r / c['gif']).is_file() and (r / c['poster']).is_file() and (r / c['sheet']).is_file()
assert c['marks'] == [{'box': [100, 300, 600, 200], 'label': 'Меню', 'kind': 'error'}] and c['steps'] == ['Открыть меню']
assert d['raw'] is None and not list((r / 'recordings').glob('*.mp4')) and c['viewed'] is False and 'clip-viewed' in d['next']
" "$R15" "$TMP/c2.json"
  check "clip-stop --finding: ролик в findings[].clips и в recordings; finding.py list — «не просмотрено роликов: 1»" sh -c "
    '$PY' -c \"import json,sys; f=json.load(open(sys.argv[1]))['findings'][0]; assert f['clips'][0]['file']=='clips/F-001-menu.mp4' and 'clips/F-001-menu.mp4' in f['recordings'], f\" '$R15/findings.json' &&
    '$PY' '$S/finding.py' list '$R15' | grep -q 'не просмотрено роликов: 1'"
  check "подпись в кадре: drawtext или плашка Chromium (node/plaque.js) + overlay — caption_in_video" \
    test "$(jq1 "$TMP/c2.json" "d['clip']['caption_in_video']")" = True
else
  skip "clip-stop со сжатием"
fi
check "<RUN_DIR>/.gitignore: clips/, recordings/, raw/rolling-*/ не коммитятся" sh -c "
  grep -qx 'clips/' '$R15/.gitignore' && grep -qx 'recordings/' '$R15/.gitignore' && grep -qx 'raw/rolling-\*/' '$R15/.gitignore'"

# ---------- the settings are returned on errors, interruption, refusal ----------
FAKE_ADB_SCREENRECORD_NOFILE=1 "$PY" "$S/adb_helpers.py" clip-start --name lost $D15 >/dev/null
"$PY" "$S/adb_helpers.py" clip-stop $D15 > "$TMP/c3.json"; c=$?
check "clip-stop: файла нет на устройстве (pull не удался) — код 5, show_touches всё равно возвращён, состояние убрано" sh -c "
  test $c = 5 && test '$(touches emulator-5554)' = 0 && grep -q 'adb pull' '$TMP/c3.json' && test ! -f '$R15/raw/clip-emulator-5554.json'"
"$PY" "$S/adb_helpers.py" clip --name int --lead 0 --tail 0 $D15 -- wait 8 > "$TMP/c4.json" 2>&1 & bgp=$!
sleep 2.5; ti=$(touches emulator-5554); kill -TERM $bgp 2>/dev/null; wait $bgp; c=$?; sleep 0.5
check "clip: прерывание (SIGTERM) — код 130, show_touches возвращён (был 1 во время записи), осиротевших процессов нет" sh -c "
  test $c = 130 && test '$ti' = 1 && test '$(touches emulator-5554)' = 0 && test ! -f '$R15/raw/clip-emulator-5554.json' &&
  ! pgrep -f 'android-qa-audit/tests/helpers/fake_adb.py .*screenrecord' >/dev/null"
"$PY" "$S/adb_helpers.py" clip-start --name stale $D15 >/dev/null
"$PY" -c "import json,sys; p=sys.argv[1]; d=json.load(open(p)); d['started_ts']-=1000; json.dump(d, open(p,'w'))" "$R15/raw/clip-emulator-5554.json"
"$PY" "$S/adb_helpers.py" clip-start --name fresh $D15 > "$TMP/c5.json"; c=$?
check "clip-start: осиротевшее состояние прошлой записи убирается (настройки возвращены), новая запись стартует" sh -c "
  test $c = 0 && grep -q 'прерванной записи' '$TMP/c5.json' && grep -q '\"name\": \"fresh\"' '$R15/raw/clip-emulator-5554.json'"
"$PY" "$S/adb_helpers.py" clip-stop --restore-only $D15 > "$TMP/c6.json"; c=$?
check "clip-stop --restore-only: запись остановлена без ролика, show_touches возвращён, состояние убрано" sh -c "
  test $c = 0 && test '$(touches emulator-5554)' = 0 && test ! -f '$R15/raw/clip-emulator-5554.json' && grep -q 'stopped_recorder' '$TMP/c6.json'"
check "clip-stop без записи — код 2; --restore-only без состояния — код 0 «нечего возвращать»" sh -c "
  test \$('$PY' '$S/adb_helpers.py' clip-stop $D15 >/dev/null 2>&1; echo \$?) = 2 &&
  '$PY' '$S/adb_helpers.py' clip-stop --restore-only $D15 | grep -q 'нечего возвращать'"
echo '{"show_touches": "null", "pointer_location": "0"}' > "$FAKE_ADB_STATE/settings-emulator-5554.json"
"$PY" "$S/adb_helpers.py" clip-start --name nul $D15 >/dev/null; "$PY" "$S/adb_helpers.py" clip-stop --restore-only $D15 >/dev/null
check "show_touches не было (null) — после записи снова null (settings delete), а не 0" sh -c "
  test '$(touches emulator-5554)' = null && grep -q 'settings delete system show_touches' '$FAKE_ADB_LOG'"
rm -f "$FAKE_ADB_STATE/settings-emulator-5554.json"
FAKE_ADB_SCREENRECORD_FAIL=codec "$PY" "$S/adb_helpers.py" clip-start --name nocodec $D15 > "$TMP/c7.json"; c=$?
check "нет кодека (Encoder failed) — код 4 «не поддерживается» с подсказкой, настройки возвращены, состояния нет" sh -c "
  test $c = 4 && grep -q 'не поддерживается' '$TMP/c7.json' && grep -q 'gpu host' '$TMP/c7.json' && test '$(touches emulator-5554)' = 0 &&
  test ! -f '$R15/raw/clip-emulator-5554.json'"
check "нет screenrecord на стенде / API < 19 — код 4" sh -c "
  test \$(FAKE_ADB_NO_SCREENRECORD=1 '$PY' '$S/adb_helpers.py' clip-start --name x $D15 >/dev/null 2>&1; echo \$?) = 4 &&
  '$PY' -c \"import sys; sys.path.insert(0, sys.argv[1]); import clip_android as ca
class A: confirmed=False
class C:
    a=A(); run_dir=None
    def api(self): return 18
try:
    ca.check_support(C()); sys.exit(1)
except ca.ClipError as ex:
    assert ex.code == 4 and 'API 19' in str(ex)\" '$S'"

# ---------- clip: steps through guard ----------
"$PY" "$S/adb_helpers.py" clip --name F-001-buy --lead 0 --tail 0 $D15 -- tap --text "Купить" > "$TMP/c8.json"; c=$?
check "clip: шаг с запретом (Купить) не выполнен — код 3, logs/blocked.jsonl, цепочка оборвана, ролика нет, настройки возвращены" sh -c "
  test $c = 3 && grep -q '\"blocked\": true' '$TMP/c8.json' && tail -1 '$R15/logs/blocked.jsonl' | grep -q 'base:action:purchase' &&
  ! ls '$R15/clips/' 2>/dev/null | grep -q 'F-001-buy' && test '$(touches emulator-5554)' = 0 && test ! -f '$R15/raw/clip-emulator-5554.json'"
check "clip: секрет (text --env) под запись — код 2 до начала записи; неизвестный шаг / опция — код 2" sh -c "
  : > '$TMP/adb15.log'; FAKE_ADB_LOG='$TMP/adb15.log' '$PY' '$S/adb_helpers.py' clip --name s $D15 -- text --env PASS > '$TMP/c9.json'; test \$? = 2 &&
  grep -q 'секрет' '$TMP/c9.json' && ! grep -q screenrecord '$TMP/adb15.log' &&
  test \$('$PY' '$S/adb_helpers.py' clip --name s $D15 -- install x.apk >/dev/null 2>&1; echo \$?) = 2 &&
  test \$('$PY' '$S/adb_helpers.py' clip --name s $D15 -- tap --bogus >/dev/null 2>&1; echo \$?) = 2 &&
  test \$('$PY' '$S/adb_helpers.py' clip --name s $D15 >/dev/null 2>&1; echo \$?) = 2"
check "clip --dry-run: шаги разобраны, на устройстве ничего не выполнено" sh -c "
  : > '$TMP/adb15.log'; out=\$(FAKE_ADB_LOG='$TMP/adb15.log' '$PY' '$S/adb_helpers.py' clip --name s --dry-run $D15 -- tap --text 'A b' --then scroll down --then wait 1) &&
  echo \"\$out\" | grep -q '\"steps\": \[\"tap --text .A b.\", \"scroll down\", \"wait 1\"\]' && ! grep -qE 'screenrecord|input' '$TMP/adb15.log'"
if [ -n "$FF" ]; then
  "$PY" "$S/adb_helpers.py" clip --name F-002-anim --lead 0 --tail 0.2 --finding F-002 --caption "Рывки анимации" $D15 \
    -- tap --text "Каталог" --then wait 0.3 --then key BACK > "$TMP/c10.json"; c=$?
  check "clip: старт → шаги (tap, wait, key) теми же функциями → стоп; ролик в находке F-002, шаги в записи, касания возвращены" pyok "
import json, sys; d = json.load(open(sys.argv[1])); c = d['clip']
assert d['ok'] and [s['code'] for s in d['steps']] == [0, 0, 0] and d['steps'][0]['output']['action'] == 'tap', d['steps']
assert c['steps'] == [\"tap --text 'Каталог'\", 'wait 0.3', 'key BACK'] and d['finding'] == 'F-002' and d['touches']['restored'] is True
" "$TMP/c10.json"
  check "clip: нажатие из шага записано в logs/actions.jsonl (тот же журнал, что у tap)" grep -q '"adb": "shell input tap 535 165"' "$R15/logs/actions.jsonl"
  FAKE_ADB_SCREENRECORD_FILE="$TMP/black.mp4" "$PY" "$S/adb_helpers.py" clip --name F-002-black --finding F-002 --lead 0 --tail 0 $D15 -- wait 0.1 > "$TMP/c11.json"; c=$?
  check "чёрный экран (FLAG_SECURE): доля чёрных > 0,8 → код 5, предупреждение, в находку не записан" sh -c "
    test $c = 5 && grep -q 'FLAG_SECURE' '$TMP/c11.json' && grep -q '\"black_ratio\": 1.0' '$TMP/c11.json' &&
    ! grep -q 'F-002-black' '$R15/findings.json'"
  FAKE_ADB_SCREENRECORD_FILE="$TMP/black.mp4" "$PY" "$S/adb_helpers.py" clip --name F-002-black --finding F-002 --force --lead 0 --tail 0 $D15 -- wait 0.1 > "$TMP/c12.json"; c=$?
  check "чёрный экран с --force — записан в находку с предупреждением" sh -c "
    test $c = 0 && grep -q 'clips/F-002-black.mp4' '$R15/findings.json' && grep -q 'доля чёрных кадров' '$TMP/c12.json'"
  FAKE_ADB_SCREENRECORD_FILE="$TMP/rec1.mp4" "$PY" "$S/adb_helpers.py" clip --name F-002-static --lead 0 --tail 2.5 $D15 -- wait 0.2 > "$TMP/c13.json"; c=$?
  check "статичный хвост (screenrecord не пишет кадры без изменений): ролик дотянут до длительности записи" pyok "
import json, sys; d = json.load(open(sys.argv[1]))
assert d['ok'] and d.get('padded_to_s') and d['clip']['seconds'] >= 2.5, (d.get('padded_to_s'), d['clip']['seconds'])
" "$TMP/c13.json"
  FAKE_ADB_SCREENRECORD_FAIL=codec FAKE_ADB_SCREENCAP_FILE="$TMP/screen.png" "$PY" "$S/adb_helpers.py" clip --name F-002-frames \
    --lead 0.3 --tail 0.3 $D15 -- wait 1 > "$TMP/c14.json"; c=$?
  check "clip без кодека: запасной путь — ролик из скриншотов (source frames, кадров/с, предупреждение), --fallback none — код 4" sh -c "
    test $c = 0 && '$PY' -c \"import json,sys; d=json.load(open(sys.argv[1])); c=d['clip']; assert c['source']=='frames' and c['frames_captured']>=2 and 'из скриншотов' in c['warning'], c\" '$TMP/c14.json' &&
    test \$(FAKE_ADB_SCREENRECORD_FAIL=codec '$PY' '$S/adb_helpers.py' clip --name n --fallback none --lead 0 --tail 0 $D15 -- wait 0.1 >/dev/null 2>&1; echo \$?) = 4"
else
  skip "clip с шагами, чёрный экран, статичный хвост, ролик из скриншотов"
fi
PATH="$NOFF" QA_FFMPEG= QA_FFPROBE= "$PY" "$S/adb_helpers.py" clip --name F-002-noff --lead 0 --tail 0 $D15 -- key BACK --then wait 0.1 > "$TMP/c15.json"; c=$?
check "без ffmpeg: ролик сохранён как есть с предупреждением, GIF/ленты нет — вместо ленты скриншоты после шагов (frames)" pyok "
import json, sys; from pathlib import Path
d = json.load(open(sys.argv[1])); c = d['clip']
assert d['ok'] and c['encoder'] == 'raw' and 'ffmpeg не найден' in c['warning'] and not c['gif'] and not c.get('sheet'), c
assert c['frames'] == ['clips/F-002-noff-step-1.png'] and (Path(sys.argv[2]) / c['frames'][0]).is_file()
" "$TMP/c15.json" "$R15"

# ---------- real device: touches only by --touches on, the confirmation covers switching back ----------
DR="--serial R58N00TEST01 --run-dir $R15"
"$PY" "$S/adb_helpers.py" clip-start --name real $DR > "$TMP/c16.json"; c=$?
check "реальное устройство (согласие app-only): запись идёт, касания по умолчанию не включаются" sh -c "
  test $c = 0 && grep -q '\"wanted\": false' '$TMP/c16.json' && test '$(touches R58N00TEST01)' = 0"
"$PY" "$S/adb_helpers.py" clip-stop --restore-only $DR >/dev/null
check "реальное устройство, --touches on без согласия на настройки — код 2 (спросить), ничего не изменено" sh -c "
  test \$('$PY' '$S/adb_helpers.py' clip-start --name real --touches on $DR >/dev/null 2>&1; echo \$?) = 2 && test '$(touches R58N00TEST01)' = 0 &&
  test ! -f '$R15/raw/clip-R58N00TEST01.json'"
"$PY" "$S/adb_helpers.py" clip-start --name real --touches on --confirmed $DR >/dev/null; tr1=$(touches R58N00TEST01)
"$PY" "$S/adb_helpers.py" clip-stop --restore-only $DR > "$TMP/c17.json"
check "реальное устройство, --touches on --confirmed: включено, а возврат идёт без повторного вопроса (согласие на включение)" sh -c "
  test '$tr1' = 1 && test '$(touches R58N00TEST01)' = 0 && grep -q '\"restored\": true' '$TMP/c17.json'"

# ---------- findings, validation, drafts, report, export, attachments ----------
if [ -n "$FF" ]; then
  cp "$TMP/rec5.mp4" "$TMP/outside.mp4"
  "$PY" "$S/finding.py" clip "$R15" --id F-002 --file "$TMP/outside.mp4" --kind after --caption "После исправления плавно" > "$TMP/f1.json"; c=$?
  check "finding.py clip: ролик вне clips/ сжат в clips/F-002-outside.mp4 (kind after), лента кадров для просмотра" sh -c "
    test $c = 0 && grep -q '\"file\": \"clips/F-002-outside.mp4\"' '$TMP/f1.json' && grep -q '\"kind\": \"after\"' '$TMP/f1.json' &&
    test -f '$R15/clips/F-002-outside-sheet.png'"
  "$PY" "$S/finding.py" add "$R15" --id F-003 --title "Поворот теряет ввод" --severity medium --direction lifecycle-resilience \
    --screen com.example.app.MainActivity --actual "поле пустое" --clip clips/F-002-outside.mp4 --clip-caption "Поле очищается" > "$TMP/f2.json"; c=$?
  check "finding.py add --clip: готовый ролик из clips/ (GIF, постер, лента найдены по имени) записан в новую находку" pyok "
import json, sys; f = [x for x in json.load(open(sys.argv[1]))['findings'] if x['id'] == 'F-003'][0]; c = f['clips'][0]
assert c['file'] == 'clips/F-002-outside.mp4' and c['sheet'] == 'clips/F-002-outside-sheet.png' and c['caption'] == 'Поле очищается', c
" "$R15/findings.json"
  "$PY" "$S/validate_findings.py" "$R15/findings.json" > "$TMP/v1.out"; c1=$?
  "$PY" "$S/validate_findings.py" "$R15/findings.json" --publish > "$TMP/v2.out"; c2=$?
  check "validate_findings: непросмотренный ролик — предупреждение (код 0); с --publish — ошибка (код 1)" sh -c "
    test $c1 = 0 && grep -q 'WARN  F-001: ролик clips/F-001-menu.mp4: ролик не просмотрен' '$TMP/v1.out' && test $c2 = 1 &&
    grep -q 'ERROR F-001: ролик clips/F-001-menu.mp4: ролик не просмотрен' '$TMP/v2.out'"
  "$PY" "$S/finding.py" clip-viewed "$R15" --id F-001 --file clips/F-001-menu.mp4 >/dev/null
  "$PY" "$S/finding.py" viewed "$R15" --id F-002 --clips >/dev/null
  check "finding.py clip-viewed / viewed --clips: ролики отмечены, list без «не просмотрено роликов» у F-001 и F-002" sh -c "
    ! '$PY' '$S/finding.py' list '$R15' | grep -E '^F-00[12] ' | grep -q 'не просмотрено роликов' && '$PY' '$S/finding.py' list '$R15' | grep '^F-003' | grep -q 'не просмотрено роликов: 1'"
  "$PY" "$S/finding.py" clip-viewed "$R15" --id F-003 >/dev/null
  check "validate_findings --publish: всё просмотрено — 0 ошибок" "$PY" "$S/validate_findings.py" "$R15/findings.json" --publish
  cp "$R15/findings.json" "$TMP/fbak.json"
  "$PY" -c "import json,sys; p=sys.argv[1]; d=json.load(open(p)); d['findings'][0]['clips'][0]['audio']=True; json.dump(d, open(p,'w'), ensure_ascii=False)" "$R15/findings.json"
  check "validate_findings: ролик со звуком — ошибка всегда" sh -c "! '$PY' '$S/validate_findings.py' '$R15/findings.json' >/dev/null && '$PY' '$S/validate_findings.py' '$R15/findings.json' | grep -q 'звук'"
  cp "$TMP/fbak.json" "$R15/findings.json"
  "$PY" -c "import json,sys; p=sys.argv[1]; d=json.load(open(p)); d['findings'][2]['clips'][0]['viewed']=False; json.dump(d, open(p,'w'), ensure_ascii=False)" "$R15/findings.json"
  "$PY" "$S/render_draft.py" all "$R15/findings.json" --run-dir "$R15" > /dev/null 2>"$TMP/rd.err"
  B1=$(ls "$R15"/drafts/local/*-F-001.body.md 2>/dev/null || ls "$R15"/drafts/local/01-*.body.md); B3=$(ls "$R15"/drafts/local/03-*.body.md)
  check "render_draft: просмотренный ролик — GIF inline + «[▶ ролик, N с, 0,N МБ]» на mp4; непросмотренный — нет, он в «Проверить»" sh -c "
    grep -q '^!\[Меню закрывается через 0,4 с\](../../clips/F-001-menu.gif)' '$B1' && grep -q '^\[▶ ролик, [0-9] с, [0-9],[0-9] МБ\](../../clips/F-001-menu.mp4) — Меню' '$B1' &&
    ! grep -q 'F-002-outside' '$B3' && grep -q 'не просмотрен' '$R15/drafts/local/index.md' && grep -q 'не просмотрен' '$TMP/rd.err'"
  check "render_draft --attachments-base: ссылки на ветку (?raw=true), «после исправления» для kind after" sh -c "
    '$PY' '$S/render_draft.py' detailed '$R15/findings.json' --id F-002 --attachments-base https://github.com/o/r/blob/qa/d 2>/dev/null |
    grep -q '\[▶ ролик после исправления, [0-9] с, [0-9],[0-9] МБ\](https://github.com/o/r/blob/qa/d/F-002-outside.mp4?raw=true)'"
  "$PY" "$S/build_report.py" report "$R15" >/dev/null
  check "build_report: раздел «Ролики находок» — находка, вид, длительность, размер, просмотрен, ссылка" sh -c "
    grep -q '^## Ролики находок' '$R15/report.md' && grep -q '^| F-001 | ошибка | [0-9],[0-9] с | 0,[0-9]* МБ | да | Меню закрывается через 0,4 с.* | \[F-001-menu.mp4\](clips/F-001-menu.mp4) |' '$R15/report.md' &&
    grep -q '^| F-003 | .*нет — не публикуется' '$R15/report.md'"
  "$PY" "$S/build_report.py" summary "$R15" >/dev/null; : > "$R15/clips/orphan.mp4"
  check "export_results --clips: referenced (по умолчанию) — ролики, GIF и постеры находок; all — вся папка; none — без роликов" sh -c "
    '$PY' '$S/export_results.py' '$R15' --to '$TMP/ex15' --name a >/dev/null && test -f '$TMP/ex15/a/clips/F-001-menu.mp4' &&
    test -f '$TMP/ex15/a/clips/F-001-menu.gif' && test ! -f '$TMP/ex15/a/clips/orphan.mp4' && test ! -f '$TMP/ex15/a/clips/F-001-menu-sheet.png' &&
    '$PY' '$S/export_results.py' '$R15' --to '$TMP/ex15' --name b --clips all >/dev/null && test -f '$TMP/ex15/b/clips/orphan.mp4' &&
    '$PY' '$S/export_results.py' '$R15' --to '$TMP/ex15' --name c --clips none >/dev/null && test ! -d '$TMP/ex15/c/clips' &&
    '$PY' '$S/export_results.py' --help | grep -q -- '--clips'"
  check "attachments.py plan: ролики (mp4 + GIF) только просмотренных находок едут в ветку со скриншотами; --no-clips — без них" pyok "
import json, subprocess, sys
def plan(*extra):
    out = subprocess.run([sys.executable, sys.argv[1], 'plan', sys.argv[2], '--repo', 'o/r', '--branch', 'qa', '--dir', 'd', '--json', *extra],
                         capture_output=True, text=True).stdout
    return [r['path'] for r in json.loads(out)['files']]
p = plan(); assert 'd/F-001-menu.mp4' in p and 'd/F-001-menu.gif' in p and 'd/F-002-outside.mp4' in p, p
assert plan('--file', 'clips/F-001-menu.mp4') == ['d/F-001-menu.mp4'], 'with --file only that file'
assert not any(x.endswith(('.mp4', '.gif')) for x in plan('--no-clips')), plan('--no-clips')
" "$S/attachments.py" "$R15"
else
  skip "finding.py clip, validate, render_draft, build_report, export, attachments"
fi

# ---------- clip-rolling ----------
"$PY" "$S/adb_helpers.py" clip-rolling start --segment 2 --keep 3 $D15 > "$TMP/r1.json"; c=$?
check "clip-rolling start: фоновый процесс сегментов, состояние raw/rolling-<serial>.json, касания включены" sh -c "
  test $c = 0 && grep -q '\"runner_pid\": [0-9]' '$TMP/r1.json' && test '$(touches emulator-5554)' = 1 && test -f '$R15/raw/rolling-emulator-5554.json'"
check "clip-rolling: второй start — код 2; clip-start во время непрерывной записи — код 2" sh -c "
  test \$('$PY' '$S/adb_helpers.py' clip-rolling start $D15 >/dev/null 2>&1; echo \$?) = 2 &&
  test \$('$PY' '$S/adb_helpers.py' clip-start --name x $D15 >/dev/null 2>&1; echo \$?) = 2"
sleep 4.5
"$PY" "$S/adb_helpers.py" clip-rolling status $D15 > "$TMP/r2.json"
check "clip-rolling status: фон жив, готовые сегменты в raw/rolling-<serial>/ (не больше --keep)" sh -c "
  grep -q '\"alive\": true' '$TMP/r2.json' && n=\$(ls '$R15/raw/rolling-emulator-5554/' | grep -c '^seg-') && test \$n -ge 1 && test \$n -le 3"
"$PY" "$S/adb_helpers.py" clip-rolling save --name F-001-crash --finding F-001 --last 12 --caption "Падение" $D15 > "$TMP/r3.json"; c=$?
check "clip-rolling save: текущий сегмент дописан (cut), последние ≈ --last с (не больше clips.max_seconds) → ролик в находке" pyok "
import json, sys; d = json.load(open(sys.argv[1])); c = d['clip']
assert d['ok'] and c['file'] == 'clips/F-001-crash.mp4' and c['source'] == 'rolling' and d['finding'] == 'F-001', d
assert c['seconds'] is None or c['seconds'] <= 10.5, c['seconds']
assert (sys.argv[2] == '' and 'без ffmpeg' in (d.get('note') or '')) or sys.argv[2] != '' or len(json.load(open(sys.argv[3]))['segments']) <= 1
" "$TMP/r3.json" "$FF" "$R15/raw/rolling-emulator-5554.json"
"$PY" "$S/adb_helpers.py" clip-rolling stop $D15 > "$TMP/r4.json"; c=$?; sleep 0.5
check "clip-rolling stop: фон остановлен, сегменты и временные файлы удалены, show_touches возвращён, процессов не осталось" sh -c "
  test $c = 0 && test '$(touches emulator-5554)' = 0 && test ! -d '$R15/raw/rolling-emulator-5554' && test ! -f '$R15/raw/rolling-emulator-5554.json' &&
  ! ls '$FAKE_ADB_STATE/remote/' 2>/dev/null | grep -q qa-roll- && ! pgrep -f 'clip-rolling-run --serial emulator-5554 --run-dir $R15' >/dev/null"
"$PY" "$S/adb_helpers.py" clip-rolling start --segment 2 $D15 >/dev/null; sleep 1; : > "$FAKE_ADB_STATE/offline-emulator-5554"; sleep 5
st_lost=$(jq1 "$R15/raw/rolling-emulator-5554.json" "d['status']"); rm -f "$FAKE_ADB_STATE/offline-emulator-5554"
"$PY" "$S/adb_helpers.py" clip-rolling start --segment 2 $D15 > "$TMP/r5.json"; c=$?
check "clip-rolling: потеря связи — статус lost; повторный start после переподключения убирает старое (настройки) и пишет заново" sh -c "
  test '$st_lost' = lost && test $c = 0 && grep -q 'убрано состояние прошлой непрерывной записи (lost)' '$TMP/r5.json'"
rp=$(jq1 "$R15/raw/rolling-emulator-5554.json" "d['runner_pid']"); kill -9 "$rp" 2>/dev/null; sleep 0.3
"$PY" "$S/adb_helpers.py" clip-rolling start --segment 2 $D15 > "$TMP/r6.json"; c=$?
"$PY" "$S/adb_helpers.py" clip-rolling stop $D15 >/dev/null; sleep 2.5
check "clip-rolling: фон убит (kill -9) — повторный start подхватывает осиротевшее состояние; после stop процессов нет" sh -c "
  test $c = 0 && grep -q 'убрано состояние' '$TMP/r6.json' && test '$(touches emulator-5554)' = 0 &&
  ! pgrep -f 'clip-rolling-run --serial emulator-5554 --run-dir $R15' >/dev/null"

# ---------- soak --clips-on-crash ----------
rm -f "$FAKE_ADB_STATE"/pid-emulator-5554-*.count
FAKE_ADB_PIDOF_UNTIL=3 "$PY" "$S/adb_helpers.py" soak --minutes 0.3 --every 4 --tag crash --screenshots 0 --clips-on-crash \
  --clips-segment 2 $D15 > "$TMP/s1.json"; c=$?; sleep 0.5
check "soak --clips-on-crash: смерть процесса замечена сразу, ролик последних секунд (events[].clip, clips[]), запись остановлена, касания возвращены" pyok "
import json, sys; from pathlib import Path
d = json.load(open(sys.argv[1])); r = Path(sys.argv[2])
ev = [e for e in d['events'] if e['event'] == 'process-died'][0]
assert d['status'] == 'interrupted' and ev.get('clip', '').startswith('clips/soak-crash-process-died-'), d['events']
assert d['clips'][0]['event'] == 'process-died' and (r / d['clips'][0]['file']).is_file(), d.get('clips')
assert d['clips_on_crash']['recording'] and d['clips_on_crash']['stopped']['touches']['restored'] is True, d['clips_on_crash']
assert not (r / 'raw' / 'rolling-emulator-5554.json').exists()
" "$TMP/s1.json" "$R15"
FAKE_ADB_ANR=1 "$PY" "$S/adb_helpers.py" soak --minutes 0.15 --every 3 --tag anr --screenshots 0 --clips-on-crash --clips-segment 2 $D15 > "$TMP/s2.json"; sleep 0.5
check "soak --clips-on-crash: диалог «не отвечает» (ANR) — событие anr и ролик, прогон продолжается" sh -c "
  '$PY' -c \"import json,sys; d=json.load(open(sys.argv[1])); e=[x for x in d['events'] if x['event']=='anr']; assert e and e[0].get('clip') and d['status']=='ok', d['events']\" '$TMP/s2.json' &&
  test '$(touches emulator-5554)' = 0 && ! pgrep -f 'clip-rolling-run --serial emulator-5554 --run-dir $R15' >/dev/null"
if [ -n "$FF" ]; then
  "$PY" "$S/build_report.py" report "$R15" >/dev/null
  check "build_report: ролики soak (--clips-on-crash) в «Роликах находок»" grep -q '^| soak crash (process-died) |' "$R15/report.md"
fi

# ---------- cleanup, check_env, intake ----------
"$PY" "$S/adb_helpers.py" clip-start --name leftover $D15 >/dev/null
"$PY" "$S/avd_manager.py" cleanup --run-dir "$R15" > "$TMP/cl1.out"; "$PY" "$S/avd_manager.py" cleanup --run-dir "$R15" --yes > "$TMP/cl2.out"
check "avd_manager cleanup: незавершённая запись прогона — первым шагом clip-stop --restore-only (план, затем --yes), касания возвращены" sh -c "
  grep -q 'clip-restore: emulator-5554' '$TMP/cl1.out' && grep -q 'clip-restore emulator-5554: код 0' '$TMP/cl2.out' &&
  test '$(touches emulator-5554)' = 0 && test ! -f '$R15/raw/clip-emulator-5554.json'"
mkdir -p "$R15/recordings" "$R15/raw/rolling-x"; : > "$R15/recordings/r.mp4"; : > "$R15/raw/rolling-x/seg-1.mp4"; : > "$R15/clips/orphan2.mp4"
"$PY" "$S/avd_manager.py" cleanup --run-dir "$R15" --delete-recordings --yes >/dev/null
check "cleanup --delete-recordings: recordings/, raw/rolling-*/ и ролики clips/ без ссылок удалены; ролики находок и soak — нет" sh -c "
  test ! -f '$R15/recordings/r.mp4' && test ! -f '$R15/raw/rolling-x/seg-1.mp4' && test ! -f '$R15/clips/orphan2.mp4' &&
  { test -z '$FF' || test -f '$R15/clips/F-001-menu.mp4'; } && ls '$R15/clips/' | grep -q '^soak-crash-process-died-'"
"$PY" "$S/check_env.py" --fast --json "$TMP/env15.json" > "$TMP/env15.out" 2>&1
check "check_env: строка «ffmpeg (ролики находок)» (рекомендуется, установка с согласия) и «screenrecord на стендах»; env.json" sh -c "
  grep -q 'ffmpeg (ролики находок)' '$TMP/env15.out' && grep -q 'screenrecord на стендах (ролики)' '$TMP/env15.out' &&
  '$PY' -c \"import json,sys; d=json.load(open(sys.argv[1])); assert 'ffmpeg' in d['optional']; assert any(x.get('screenrecord',{}).get('ok') for x in d['devices'] if x.get('state')=='device')\" '$TMP/env15.json' &&
  PATH='$NOFF' QA_FFMPEG= '$PY' '$S/check_env.py' --fast --no-devices | grep 'ffmpeg (ролики находок)' | grep -q 'рекомендуется'"
check "intake from-text: «с видео» → clips.mode on, «без видео» → off (не запрет кнопок), иначе auto; ключи clips: с умолчаниями" pyok "
import json, subprocess, sys
def cfg(t): return json.loads(subprocess.run([sys.executable, sys.argv[1], 'from-text', '--json', '--text', t], capture_output=True, text=True).stdout)['config']
a, b, c = cfg('Протестируй app.apk с видео'), cfg('проверь app.apk, без видео'), cfg('протестируй app.apk на Android 14')
assert (a['clips']['mode'], b['clips']['mode'], c['clips']['mode']) == ('on', 'off', 'auto'), (a['clips'], b['clips'], c['clips'])
assert b['rules']['forbidden_actions'] == [] and c['clips']['max_seconds'] == 10 and c['clips']['touches'] == 'auto'
assert cfg('запиши ролики находок для app.apk')['clips']['mode'] == 'on' and cfg('test app.apk without video')['clips']['mode'] == 'off'
" "$S/intake.py"
check "run-config.example.yaml: раздел clips: (mode auto, 10 с, 3 МБ, touches auto)" pyok "
import json, sys; d = json.load(open(sys.argv[1]))['clips']
assert d['mode'] == 'auto' and d['max_seconds'] == 10 and d['max_mb'] == 3 and d['touches'] == 'auto' and d['keep_raw'] is False, d
" "$TMP/rc.json"
check "после всех тестов роликов на фейковом стенде не осталось записи и фоновых процессов" sh -c "
  sleep 1; ! pgrep -f 'android-qa-audit/tests/helpers/fake_adb.py .*screenrecord' >/dev/null && ! pgrep -f 'clip-rolling-run --serial' >/dev/null"
