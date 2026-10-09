# 1.2.0 tests — sourced by tests/unit.sh (uses its PY, S, F, T, TMP, RUN, check, rc, pyok, fake adb/SDK).
# Microphone (gRPC on a fake HTTP/2 server, loopback, file), emulator flags, tap without a tree, dump-ui retries and
# texts, ambiguity, expectations, notifications, logcat noise, soak and jobs, annotations, finding add, issue forms,
# known docs, attachments by branch, disclosure, human steps, import-file, push-media, ime, qa wrapper, matrix, intake.
H="$HERE/helpers"
R12="$TMP/run-12"; mkdir -p "$R12/raw" "$R12/screenshots"; cp "$F/run-config.yaml" "$R12/run-config.yaml"
D12="--serial emulator-5554 --run-dir $R12"
export ANDROID_QA_LOOPBACK=""          # no host loopback device unless a test sets one (deterministic on any host)
export ANDROID_QA_EMU_RUNNING_DIR="$TMP/no-running" ANDROID_QA_SLEEP_SCALE=0.05
# yedit SRC DST OLD NEW — copy a YAML file replacing the first OLD by NEW («\n» in NEW is a new line; BSD sed cannot)
yedit(){ "$PY" "$H/yedit.py" "$@"; }
mkw(){ "$PY" -c "import wave,struct,sys; w=wave.open(sys.argv[1],'wb'); w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000); w.writeframes(struct.pack('<h',800)*int(16000*float(sys.argv[2]))); w.close()" "$1" "$2"; }
mkw "$TMP/speech.wav" 1.0; mkw "$TMP/rec3s.wav" 3.0
: > "$FAKE_ADB_LOG"

# ---------- masking, guard ----------
check "masking: grpc.token=… и token: … скрыты, «token is invalid» — нет; известный секрет — везде" pyok "
import sys; sys.path.insert(0, sys.argv[1]); from masking import mask, find_unmasked
t=mask('grpc.token=Zx9AbCdEfGh12345 port=8554 token: Qw3rty123456 token is invalid')
assert 'Zx9AbCdEfGh12345' not in t and 'Qw3rty123456' not in t and 'token is invalid' in t, t
assert mask('header was S3cr3tValueXYZ', secrets=('S3cr3tValueXYZ',))=='header was S3cr…(14)'
assert find_unmasked('grpc.token=Zx9AbCdEfGh12345')
" "$S"
check "guard emulator-args: -grpc без токена -> 3, -allow-host-audio -> 2, -grpc с токеном -> 0" sh -c "
  test \$('$PY' '$S/guard.py' emulator-args '-grpc 8554' --config '$R12/run-config.yaml' >/dev/null 2>&1; echo \$?) = 3 &&
  test \$('$PY' '$S/guard.py' emulator-args '-allow-host-audio' --config '$R12/run-config.yaml' >/dev/null 2>&1; echo \$?) = 2 &&
  test \$('$PY' '$S/guard.py' emulator-args '-grpc 8554 -grpc-use-token -no-window' --config '$R12/run-config.yaml' >/dev/null 2>&1; echo \$?) = 0"

# ---------- avd_manager start --extra-args / --mic-inject ----------
avd qa-api34-pixel7-2gb-4c skill 34
check "avd_manager start --extra-args: открытый gRPC -> 3, микрофон хоста без --confirmed -> 2, ничего не запущено" sh -c "
  test \$('$PY' '$S/avd_manager.py' start qa-api34-pixel7-2gb-4c --extra-args '-grpc 8600' --run-dir '$R12' >/dev/null 2>&1; echo \$?) = 3 &&
  test \$('$PY' '$S/avd_manager.py' start qa-api34-pixel7-2gb-4c --extra-args '-allow-host-audio' --run-dir '$R12' >/dev/null 2>&1; echo \$?) = 2 &&
  ! grep -q qa-api34-pixel7-2gb-4c '$R12/stands.json' 2>/dev/null"
"$PY" "$S/avd_manager.py" start qa-api34-pixel7-2gb-4c --headless --mic-inject --extra-args "-prop debug.qa=1" --run-dir "$R12" > "$TMP/mic-start.out" 2>&1; c=$?
EM=$("$PY" -c "import json,sys; print(json.loads(open(sys.argv[1]).read().strip().splitlines()[-1])['serial'])" "$TMP/mic-start.out" 2>/dev/null || echo none)
check "avd_manager start --mic-inject --headless: -grpc <порт> -grpc-use-token, без -no-audio, grpc_port в stands.json" pyok "
import json,sys; e=json.loads(open(sys.argv[1]).read().strip().splitlines()[-1]); a=e['args']
assert '-grpc-use-token' in a and '-grpc' in a and a[a.index('-grpc')+1].isdigit() and '-no-audio' not in a and '-no-window' in a, a
assert '-prop' in a and e['grpc_port']==int(a[a.index('-grpc')+1]) and e['grpc_auth']=='token' and 'не печатается' in e['note']
s=json.load(open(sys.argv[2])); assert s['emulators'][-1]['grpc_port']==e['grpc_port']
" "$TMP/mic-start.out" "$R12/stands.json"
[ "$EM" != none ] && "$PY" "$S/avd_manager.py" stop "$EM" --run-dir "$R12" >/dev/null 2>&1

# ---------- gRPC client: HPACK vectors (RFC 7541 C.4, C.6), fake emulator endpoint ----------
check "grpc_emu: HPACK по примерам RFC 7541 (Хаффман, динамическая таблица с вытеснением)" pyok "
import sys; sys.path.insert(0, sys.argv[1]); import grpc_emu as g
d=g.HpackDecoder()
r=[d.decode(bytes.fromhex(x)) for x in ('828684418cf1e3c2e5f23a6ba0ab90f4ff','828684be5886a8eb10649cbf','828785bf408825a849e95ba97d7f8925a849e95bb8e8b4bf')]
assert r[0][3]==(':authority','www.example.com') and r[1][4]==('cache-control','no-cache') and r[2][4]==('custom-key','custom-value')
d=g.HpackDecoder(256)
r=[d.decode(bytes.fromhex(x)) for x in ('488264025885aec3771a4b6196d07abe941054d444a8200595040b8166e082a62d1bff6e919d29ad171863c78f0b97c8e9ae82ae43d3','4883640effc1c0bf','88c16196d07abe941054d444a8200595040b8166e084a62d1bffc05a839bd9ab77ad94e7821dd7f2e6c7b335dfdfcd5b3960d5af27087f3672c1ab270fb5291f9587316065c003ed4ee5b1063d5007')]
assert r[1][0]==(':status','307') and r[2][5]==('set-cookie','foo=ASDJKHQKBZXOQWEOPIUAXQWEOIU; max-age=3600; version=1'), r
assert g.pb_parse(g.audio_packet(g.audio_format(16000,1,2), b'ab', 5))[3]==[b'ab']
" "$S"
GTK=QaTestGrpcToken0123456789abcdef
"$PY" "$H/fake_grpc.py" --port-file "$TMP/grpc.port" --token "$GTK" --log "$TMP/grpc.log" & GPID=$!
for _ in $(seq 1 50); do [ -s "$TMP/grpc.port" ] && break; sleep 0.1; done
GPORT=$(cat "$TMP/grpc.port" 2>/dev/null || echo 0)
printf 'port.serial=5554\nport.adb=5555\navd.name=qa-api34-pixel7-2gb-2c\ngrpc.port=%s\ngrpc.token=%s\n' "$GPORT" "$GTK" > "$TMP/pid_1.ini"
printf 'port.serial=5554\navd.name=qa-api34-pixel7-2gb-2c\ngrpc.port=%s\ngrpc.token=WrongToken0123456789xyz\n' "$GPORT" > "$TMP/pid_bad.ini"
check "mic-status: путь grpc доступен (токен принят), токен не напечатан" sh -c "
  FAKE_ADB_DISCOVERY='$TMP/pid_1.ini' '$PY' '$S/adb_helpers.py' mic-status $D12 > '$TMP/ms.out' && ! grep -q '$GTK' '$TMP/ms.out' && '$PY' -c \"
import json,sys; d=json.load(open(sys.argv[1])); p={x['path']:x for x in d['paths']}
assert d['recommended']=='grpc' and p['grpc']['available'] and p['file']['available'] and not p['loopback']['available'], d
assert d['discovery']['grpc.token'].startswith('есть'), d['discovery']\" '$TMP/ms.out'"
check "mic-inject --via grpc: речь доставлена (16 кГц, моно, S16), Bearer-токен из discovery, токен не напечатан" sh -c "
  FAKE_ADB_DISCOVERY='$TMP/pid_1.ini' '$PY' '$S/adb_helpers.py' mic-inject --wav '$TMP/speech.wav' --via grpc $D12 > '$TMP/mi.out' &&
  ! grep -q '$GTK' '$TMP/mi.out' '$R12/logs/actions.jsonl' && '$PY' -c \"
import json,sys; d=json.load(open(sys.argv[1])); assert d['ok'] and d['via']=='grpc' and d['seconds_sent']==1.0 and d['packets']==10, d
log=[json.loads(x) for x in open(sys.argv[2])]; a=[x for x in log if x['method']=='injectAudio'][-1]
assert a['auth_ok'] and a['audio_bytes']==32000 and a['format']=={'rate':16000,'channels':0,'format':1,'mode':0}, a\" '$TMP/mi.out' '$TMP/grpc.log'"
check "mic-inject: неверный токен -> grpc «не поддерживается: …» (замаскировано), auto -> путь file (push-media)" sh -c "
  FAKE_ADB_DISCOVERY='$TMP/pid_bad.ini' '$PY' '$S/adb_helpers.py' mic-inject --wav '$TMP/speech.wav' $D12 > '$TMP/mi2.out' &&
  ! grep -q 'WrongToken0123456789xyz' '$TMP/mi2.out' && grep -q '/sdcard/Download/qa-speech.wav' '$FAKE_ADB_LOG' &&
  grep -q 'MEDIA_SCANNER_SCAN_FILE' '$FAKE_ADB_LOG' && '$PY' -c \"
import json,sys; d=json.load(open(sys.argv[1])); s={x['path']:x for x in d['skipped']}
assert d['via']=='file' and d['name']=='qa-speech.wav' and 'UNAUTHENTICATED' in s['grpc']['reason'] and 'loopback' in s, d
assert 'import-file --name qa-speech.wav' in d['next']\" '$TMP/mi2.out'"
check "mic-inject --via grpc без gRPC / на реальном устройстве -> 4 с причиной и следующим путём" sh -c "
  '$PY' '$S/adb_helpers.py' mic-inject --wav '$TMP/speech.wav' --via grpc $D12 > '$TMP/mi3.out'; test \$? = 4 && grep -q -- '--mic-inject' '$TMP/mi3.out' &&
  test \$('$PY' '$S/adb_helpers.py' mic-inject --wav '$TMP/speech.wav' --via grpc --serial R58N00TEST01 --run-dir '$R12' >/dev/null 2>&1; echo \$?) = 4"
printf '#!/bin/sh\nexit 0\n' > "$TMP/fakeplay"; chmod +x "$TMP/fakeplay"
check "mic-inject --via loopback: hostmicon только с --confirmed (2 без него), затем hostmicoff" sh -c "
  test \$(ANDROID_QA_LOOPBACK='BlackHole 2ch|in,out' ANDROID_QA_PLAYER='$TMP/fakeplay' '$PY' '$S/adb_helpers.py' mic-inject --wav '$TMP/speech.wav' --via loopback $D12 >/dev/null 2>&1; echo \$?) = 2 &&
  ANDROID_QA_LOOPBACK='BlackHole 2ch|in,out' ANDROID_QA_PLAYER='$TMP/fakeplay' '$PY' '$S/adb_helpers.py' mic-inject --wav '$TMP/speech.wav' --via loopback --confirmed $D12 | grep -q '\"via\": \"loopback\"' &&
  grep -q 'hostmicon' '$FAKE_ADB_LOG' && grep -q 'hostmicoff' '$FAKE_ADB_LOG'"
check "text --clipboard: кириллица через gRPC setClipboard + KEYCODE_PASTE; секрет через буфер -> 2" sh -c "
  FAKE_ADB_DISCOVERY='$TMP/pid_1.ini' '$PY' '$S/adb_helpers.py' text 'привет мир' --clipboard $D12 | grep -q clipboard &&
  grep -q '\"clipboard\": \"привет мир\"' '$TMP/grpc.log' && grep -q 'input keyevent 279' '$FAKE_ADB_LOG' &&
  test \$(QA_SECRET_TEST='Пароль1' FAKE_ADB_DISCOVERY='$TMP/pid_1.ini' '$PY' '$S/adb_helpers.py' text --env QA_SECRET_TEST --clipboard $D12 >/dev/null 2>&1; echo \$?) = 2"
kill "$GPID" 2>/dev/null; wait "$GPID" 2>/dev/null
check "check_env: строка «виртуальное аудиоустройство (loopback)» (только проверка, ничего не ставит); adb вне PATH — OK" sh -c "
  grep -q 'виртуальное аудиоустройство' '$TMP/env.out' && grep 'adb (platform-tools)' '$TMP/env.out' | grep -q '| OK |'"

# ---------- dump-ui: retries, texts, grep; tap without a tree; ambiguity; expectations ----------
check "dump-ui --retry: два сбоя «could not get idle state», затем успех" sh -c "
  rm -f '$FAKE_ADB_STATE'/dump-*.count; FAKE_ADB_DUMP_FAIL=2 '$PY' '$S/adb_helpers.py' dump-ui --retry 3 $D12 | grep -q 'Далее'"
check "dump-ui: всегда сбой -> 5 и подсказка --no-ui; --ignore-animations ставит масштаб 0 и возвращает" sh -c "
  test \$(FAKE_ADB_DUMP_FAIL=always '$PY' '$S/adb_helpers.py' dump-ui --retry 1 $D12 >/dev/null 2>'$TMP/du.err'; echo \$?) = 5 && grep -q -- '--no-ui' '$TMP/du.err' &&
  FAKE_ADB_DUMP_FAIL=always '$PY' '$S/adb_helpers.py' dump-ui --retry 1 --ignore-animations $D12 >/dev/null 2>&1;
  grep -q 'settings put global animator_duration_scale 0' '$FAKE_ADB_LOG' && grep -q 'settings put global animator_duration_scale 1.0' '$FAKE_ADB_LOG'"
check "dump-ui --texts: полный текст (без обрезки 60 символов), границы и box; --grep" sh -c "
  '$PY' '$S/adb_helpers.py' dump-ui --texts $D12 > '$TMP/dt.out' && grep -q 'Очень длинное название товара, которое не помещается…' '$TMP/dt.out' &&
  grep -q 'box=80,1440,920,120 \"Далее\"' '$TMP/dt.out' && '$PY' '$S/adb_helpers.py' dump-ui --grep 'купить' $D12 > '$TMP/dg.out' &&
  grep -q 'Купить за 199' '$TMP/dg.out' && ! grep -q 'Далее' '$TMP/dg.out'"
check "find: box [x, y, w, h] для --mark" sh -c "'$PY' '$S/adb_helpers.py' find --text Далее $D12 | grep -q '\"box\": \[80, 1440, 920, 120\]'"
check "tap X Y без дерева: 5 с подсказкой; --no-ui: по последнему дереву «Купить» -> 3, «Далее» -> нажато" sh -c "
  test \$(FAKE_ADB_DUMP_FAIL=always '$PY' '$S/adb_helpers.py' tap 540 1500 --retry 1 $D12 >/dev/null 2>&1; echo \$?) = 5 &&
  test \$(FAKE_ADB_DUMP_FAIL=always '$PY' '$S/adb_helpers.py' tap 500 1650 --no-ui $D12 >/dev/null 2>&1; echo \$?) = 3 &&
  FAKE_ADB_DUMP_FAIL=always '$PY' '$S/adb_helpers.py' tap 540 1500 --no-ui $D12 > '$TMP/nu.out' && grep -q 'last\|последний снимок дерева' '$TMP/nu.out' && grep -q '\"element_checked\": true' '$TMP/nu.out'"
rm -f "$R12/raw/.ui-cache-emulator-5554.json"
check "tap --no-ui без снимка дерева: guard по пакету/экрану, element_checked false, скриншот до, запись в actions.jsonl" sh -c "
  FAKE_ADB_DUMP_FAIL=always '$PY' '$S/adb_helpers.py' tap 540 2040 --no-ui $D12 > '$TMP/nu2.out' && grep -q 'input tap 540 2040' '$FAKE_ADB_LOG' &&
  '$PY' -c \"
import json,sys,os; d=json.load(open(sys.argv[1])); assert d['element_checked'] is False and os.path.exists(d['screenshot_before']), d\" '$TMP/nu2.out' &&
  grep -q 'input tap 540 2040' '$R12/logs/actions.jsonl'"
printf '{"state": "dlg", "screens": {"dlg": {"xml": "ui_ambiguous.xml", "focus": "com.example.app/.MainActivity"}}}' > "$TMP/flow-amb.json"
check "tap --text: кнопка «Расшифровать», а не абзац «…Расшифровать?»; два «Удалить» -> ambiguous (2), --index 1 -> второй" sh -c "
  rm -f '$FAKE_ADB_STATE'/ui-*.txt; export FAKE_ADB_UI_FLOW='$TMP/flow-amb.json';
  '$PY' '$S/adb_helpers.py' tap --text Расшифровать $D12 >/dev/null && grep -q 'input tap 790 1600' '$FAKE_ADB_LOG' &&
  '$PY' '$S/adb_helpers.py' tap --text Удалить --confirmed $D12 > '$TMP/amb.out'; test \$? = 2 && grep -q 'ambiguous: 2 matches' '$TMP/amb.out' &&
  '$PY' '$S/adb_helpers.py' tap --text Удалить --index 1 --confirmed $D12 >/dev/null && grep -q 'input tap 790 1850' '$FAKE_ADB_LOG'"
cat > "$TMP/flow-rec.json" <<'JSON'
{"state": "main", "screens": {
 "main": {"xml": "window_dump.xml", "focus": "com.example.app/.MainActivity", "taps": [{"bounds": [80, 1440, 1000, 1560], "to": "rec"}], "swipe": "rec"},
 "rec": {"xml": "ui_rec.xml", "focus": "com.example.app/.RecordActivity", "taps": [{"bounds": [440, 2000, 640, 2100], "to": "saved"}]},
 "saved": {"xml": "ui_saved.xml", "focus": "com.example.app/.MainActivity"}}}
JSON
check "tap --expect-text / --expect-gone: экран изменился; ожидание не выполнено -> 5, ok false" sh -c "
  rm -f '$FAKE_ADB_STATE'/ui-*.txt; export FAKE_ADB_UI_FLOW='$TMP/flow-rec.json';
  '$PY' '$S/adb_helpers.py' tap --text Далее --expect-text 'Идёт запись' --expect-gone Далее $D12 | grep -q '\"ok\": true' &&
  '$PY' '$S/adb_helpers.py' tap --text Стоп --expect-text 'Нет такого' --wait 1 $D12 > '$TMP/ex.out'; test \$? = 5 && grep -q '\"ok\": false' '$TMP/ex.out'"
check "scroll: changed true (содержимое сдвинулось), false (конец списка)" sh -c "
  rm -f '$FAKE_ADB_STATE'/ui-*.txt; export FAKE_ADB_UI_FLOW='$TMP/flow-rec.json';
  '$PY' '$S/adb_helpers.py' scroll down $D12 | grep -q '\"changed\": true' && '$PY' '$S/adb_helpers.py' scroll down $D12 | grep -q '\"changed\": false'"
check "launch --wait-focus: окно приложения в фокусе" sh -c "'$PY' '$S/adb_helpers.py' launch --wait-focus 1 $D12 | grep -q '\"focused\": true'"

# ---------- notifications, logcat noise and summary ----------
"$PY" -c "import sys; open(sys.argv[2],'w',newline='').write(open(sys.argv[1],encoding='utf-8').read().replace('\n','\r\n'))" "$F/dumpsys-notification-progress.txt" "$TMP/notif-crlf.txt"
check "notifications: прогресс FGS (ongoing, category progress, 12/100, «Отмена»), архив не считается, CRLF; сервис FGS" sh -c "
  FAKE_ADB_NOTIF='$TMP/notif-crlf.txt' FAKE_ADB_SERVICES=dumpsys-services.txt '$PY' '$S/adb_helpers.py' notifications $D12 > '$TMP/nt.out' && '$PY' -c \"
import json,sys; d=json.load(open(sys.argv[1])); assert d['count']==1, d; n=d['notifications'][0]
assert n['ongoing'] and n['foreground_service'] and n['category']=='progress' and n['progress']==12 and n['progress_max']==100 and n['percent']==12, n
assert n['title']=='Расшифровка (2 из 3)' and n['actions']==['Отмена'] and n['importance']=='2' and n['id']=='42', n
assert d['foreground_services'][0]['service'].endswith('RecordingService') and d['foreground_services'][0]['foreground_id']=='42'\" '$TMP/nt.out'"
check "logcat dump: шумовые теги эмулятора (V/D/I) отброшены и посчитаны, W/E оставлены; --keep-noise; --summary" sh -c "
  FAKE_ADB_LOGCAT=logcat-noise.txt '$PY' '$S/adb_helpers.py' logcat dump --summary --out '$TMP/ln.txt' $D12 > '$TMP/ln.out' &&
  ! grep -q 'app_time_stats' '$TMP/ln.txt' && ! grep -q 'BufferPoolAccessor' '$TMP/ln.txt' && grep -q 'eglMakeCurrent' '$TMP/ln.txt' && grep -q 'encoder buffer overflow' '$TMP/ln.txt' &&
  '$PY' -c \"
import json,sys; d=json.load(open(sys.argv[1])); assert d['noise_dropped']==4, d; s=d['summary']
assert s['by_level'].get('E')==2 and s['errors'][0]['count']==2 and 'encoder buffer overflow at N ms' in s['errors'][0]['message'], s\" '$TMP/ln.out' &&
  FAKE_ADB_LOGCAT=logcat-noise.txt '$PY' '$S/adb_helpers.py' logcat dump --keep-noise --out '$TMP/ln2.txt' $D12 >/dev/null && grep -q 'app_time_stats' '$TMP/ln2.txt'"
FAKE_ADB_LOGCAT=logcat-noise.txt "$PY" "$S/adb_helpers.py" logcat start $D12 > "$TMP/ls12.out" 2>&1
LP=$("$PY" -c "import json,sys; print(json.load(open(sys.argv[1]))['pid'])" "$TMP/ls12.out" 2>/dev/null || echo 0); waitpid "$LP"
check "logcat stop --summary: файл сводки, шум посчитан фоновым процессом" sh -c "
  '$PY' '$S/adb_helpers.py' logcat stop --summary $D12 > '$TMP/lst.out' && '$PY' -c \"
import json,sys,os; d=json.load(open(sys.argv[1])); assert d['noise_dropped']==4 and os.path.exists(d['summary_file']) and d['summary']['by_level'].get('E')==2, d\" '$TMP/lst.out'"

# ---------- soak and jobs ----------
SK="--every 1 --screenshots 0"
check "soak: предусловие не выполнено (нет «Идёт запись») -> invalid сразу, код 5, сводка в raw/" sh -c "
  rm -f '$FAKE_ADB_STATE'/ui-*.txt; unset FAKE_ADB_UI_FLOW; start=\$(date +%s);
  '$PY' '$S/adb_helpers.py' soak --minutes 1 $SK --tag inv --start-text Далее --expect-text 'Идёт запись' --expect-timeout 1 $D12 > '$TMP/sk1.out'; test \$? = 5 &&
  test \$((\$(date +%s)-start)) -lt 20 && grep -q '\"status\": \"invalid\"' '$TMP/sk1.out' && test -f '$R12/raw/soak-inv-emulator-5554.json' && grep -q 'предусловие' '$TMP/sk1.out'"
check "soak: стартовое нажатие запрещено guard («Купить…») -> код 3, сводка invalid «прогон не начат»" sh -c "
  unset FAKE_ADB_UI_FLOW; '$PY' '$S/adb_helpers.py' soak --minutes 1 $SK --tag deny --start-text Купить $D12 > '$TMP/skd.out'; test \$? = 3 &&
  grep -q 'прогон не начат' '$R12/raw/soak-deny-emulator-5554.json' && grep -q '\"status\": \"invalid\"' '$R12/raw/soak-deny-emulator-5554.json'"
check "soak ok: старт по тексту, предусловие, метрики (PSS, df, focus, хост), стоп, длительность на экране ≈ 3 с" sh -c "
  rm -f '$FAKE_ADB_STATE'/ui-*.txt; export FAKE_ADB_UI_FLOW='$TMP/flow-rec.json';
  '$PY' '$S/adb_helpers.py' soak --minutes 0.05 $SK --tag ok --start-text Далее --expect-text 'Идёт запись' --stop-text Стоп --final-wait 1 --expect-duration $D12 > '$TMP/sk2.out' && '$PY' -c \"
import json,sys; d=json.load(open(sys.argv[1])); assert d['status']=='ok' and d['valid'] and d['samples']>=2 and d['pss_max_mb']==100.0, d
assert d['precondition']['ok'] and d['stop_action']['element'] and d['result']['screen_duration']['ok'] and d['result']['screen_duration']['text']=='0:03', d
s=[json.loads(x) for x in open(sys.argv[2])]; assert s[0]['df_avail_kb']==3696356 and 'host' in s[0] and s[0]['focus'].startswith('com.example.app'), s[0]\" '$TMP/sk2.out' '$R12/raw/soak-ok-emulator-5554.jsonl'"
check "soak: сервис пропал на середине -> interrupted (service-lost), код 0, событие с минутой" sh -c "
  rm -f '$FAKE_ADB_STATE'/svc-*.count; unset FAKE_ADB_UI_FLOW;
  FAKE_ADB_SERVICES=dumpsys-services.txt FAKE_ADB_SERVICES_UNTIL=2 '$PY' '$S/adb_helpers.py' soak --minutes 0.2 $SK --tag lost --service RecordingService $D12 > '$TMP/sk3.out' &&
  '$PY' -c \"
import json,sys; d=json.load(open(sys.argv[1])); assert d['status']=='interrupted' and d['events'][0]['event']=='service-lost' and d['precondition']['ok'], d\" '$TMP/sk3.out'"
check "soak --result-file: длительность WAV из общей папки (pull) сверяется с --minutes" sh -c "
  FAKE_ADB_LS=/sdcard/Recordings/qa-rec.wav FAKE_ADB_PULL_FILE='$TMP/rec3s.wav' '$PY' '$S/adb_helpers.py' soak --minutes 0.05 $SK --tag file --result-file '/sdcard/Recordings/*.wav' $D12 > '$TMP/sk4.out' &&
  '$PY' -c \"
import json,sys; d=json.load(open(sys.argv[1])); f=d['result']['file']; assert f['seconds']==3.0 and f['ok'] and d['status']=='ok', d\" '$TMP/sk4.out'"
check "soak: длительность mp4 (mvhd) и ogg читаются; приватная папка приложения -> «не поддерживается»" pyok "
import sys,struct; sys.path.insert(0, sys.argv[1]); import soak
p=sys.argv[2]+'/x.m4a'; open(p,'wb').write(b'\0\0\0\x20ftypM4A '+b'\0'*20+b'\0\0\0\x6cmoov\0\0\0\x64mvhd'+b'\0'*12+struct.pack('>II',1000,61500)+b'\0'*80)
assert abs(soak.media_duration(p)-61.5)<0.01
o=sys.argv[2]+'/x.ogg'; open(o,'wb').write(b'OggS'+b'\0'*2+struct.pack('<q',48000*5)+b'\0'*20+b'OpusHead'); assert soak.media_duration(o)==5.0
assert soak.durations_on_screen('Запись 1 · 0:03 и 1:02:05')==[(3,'0:03'),(3725,'1:02:05')]
assert soak.check_duration(1790, 1800, 0.05)==(True, -10.0) and soak.check_duration(409, 1800, 0.05)[0] is False
" "$S" "$TMP"
check "job: soak в фоне — start, status (идёт / прогресс), stop -> stopped; второй до конца -> done, запись в журнале" sh -c "
  unset FAKE_ADB_UI_FLOW; '$PY' '$S/journal.py' init '$R12' --todo 'Длинные записи' >/dev/null;
  '$PY' '$S/adb_helpers.py' job start --name s1 $D12 -- soak --minutes 1 --every 1 --screenshots 0 --tag s1 > '$TMP/j1.out' && grep -q '\"job\": \"s1\"' '$TMP/j1.out' &&
  sleep 3 && '$PY' '$S/adb_helpers.py' job status s1 $D12 | grep -q '\"status\": \"running\"' &&
  '$PY' '$S/adb_helpers.py' job stop s1 $D12 > '$TMP/j1s.out' && grep -q '\"stopped\": true' '$TMP/j1s.out' &&
  '$PY' -c \"import json,sys; d=json.load(open(sys.argv[1])); assert d['status'] in ('stopped',), d\" '$R12/raw/jobs/s1.json' &&
  '$PY' -c \"import json,sys; d=json.load(open(sys.argv[1])); assert d['status']=='stopped', d\" '$R12/raw/soak-s1-emulator-5554.json' &&
  '$PY' '$S/adb_helpers.py' job start --name s2 $D12 -- soak --minutes 0.03 --every 1 --screenshots 0 --tag s2 >/dev/null &&
  for i in \$(seq 1 40); do grep -q '\"status\": \"done\"' '$R12/raw/jobs/s2.json' && break; sleep 0.5; done;
  grep -q '\"exit_code\": 0' '$R12/raw/jobs/s2.json' && grep -q 'задача s2' '$R12/journal.md'"
check "job start: второй soak на том же стенде, пока идёт первый -> отказ" sh -c "
  '$PY' '$S/adb_helpers.py' job start --name s3 $D12 -- soak --minutes 1 --every 1 --screenshots 0 --tag s3 >/dev/null && sleep 1 &&
  test \$('$PY' '$S/adb_helpers.py' job start --name s4 $D12 -- soak --minutes 1 --every 1 --tag s4 >/dev/null 2>&1; echo \$?) = 2;
  r=\$?; '$PY' '$S/adb_helpers.py' job stop s3 $D12 >/dev/null; exit \$r"
cp "$F/findings.json" "$R12/findings.json"
check "build_report: «Длинные сценарии» — статусы (НЕДЕЙСТВИТЕЛЕН, прервался), PSS, события; метрики с нагрузкой хоста" sh -c "
  '$PY' '$S/build_report.py' report '$R12' >/dev/null && grep -q '## Длинные сценарии' '$R12/report.md' && grep -q 'НЕДЕЙСТВИТЕЛЕН' '$R12/report.md' &&
  grep -q 'прервался' '$R12/report.md' && grep -q 'service-lost' '$R12/report.md' && grep -q 'Недействительных прогонов: 2' '$R12/report.md'"
check "metrics.jsonl: у замеров есть загрузка хоста (эмуляторов рядом, load)" sh -c "
  '$PY' '$S/adb_helpers.py' meminfo $D12 >/dev/null && tail -1 '$R12/raw/metrics.jsonl' | grep -q '\"emulators_running\"'"

# ---------- annotations, screenshot --mark, finding add, drafts with the annotated shot ----------
mkdir -p "$TMP/nm/playwright"; printf '#!/bin/sh\nexec "%s" "%s" "$@"\n' "$PY" "$H/fake_node.py" > "$TMP/fakenode"; chmod +x "$TMP/fakenode"
export ANDROID_QA_NODE="$TMP/fakenode" ANDROID_QA_NODE_MODULES="$TMP/nm"
cp "$TMP/speech.wav" "$TMP/notpng.bin"; "$PY" -c "import sys; open(sys.argv[1],'wb').write(b'\x89PNG\r\n\x1a\n'+b'\0'*64)" "$R12/screenshots/s1.png"
check "annotate_android: пиксели → dp (420 dpi, 2,625), spec рядом, -annotated.png, отметка по тексту из дампа" sh -c "
  '$PY' '$S/annotate_android.py' render --in '$R12/screenshots/s1.png' --mark '80,1440,920,120|Подпись обрезана|error' --mark 'text=Купить за 199 ₽|Цена?|question' --ui '$F/window_dump.xml' > '$TMP/an.out' &&
  test -f '$R12/screenshots/s1-annotated.png' && '$PY' -c \"
import json,sys; d=json.load(open(sys.argv[1])); s=json.load(open(sys.argv[2])); assert d['ok'] and s['scale']==2.625, (d,s)
assert s['items'][0]['box']==[30.5, 548.6, 350.5, 45.7] and s['items'][1]['kind']=='question' and d['marks'][1]['box']==[80,1600,920,120], s\" '$TMP/an.out' '$R12/screenshots/s1.spec.json'"
check "annotate_android: > 3 отметок и подпись за краем -> предупреждения, код 1; нет node/playwright -> 4 «не поддерживается», spec сохранён" sh -c "
  FAKE_NODE_BAD=1 '$PY' '$S/annotate_android.py' render --in '$R12/screenshots/s1.png' --mark '1,1,9,9|a' --mark '2,2,9,9|b' --mark '3,3,9,9|c' --mark '4,4,9,9|d' > '$TMP/an2.out'; test \$? = 1 &&
  grep -q 'больше 3' '$TMP/an2.out' && grep -q 'за край' '$TMP/an2.out' &&
  ANDROID_QA_NODE_MODULES='$TMP/none' '$PY' '$S/annotate_android.py' render --in '$R12/screenshots/s1.png' --mark '1,1,9,9|a' > '$TMP/an3.out'; test \$? = 4 && grep -q 'не поддерживается' '$TMP/an3.out'"
check "screenshot --mark text=…: снимок, аннотация по свежему дереву, плотность с устройства" sh -c "
  unset FAKE_ADB_UI_FLOW; '$PY' '$S/adb_helpers.py' screenshot '$R12/screenshots/F-001-next.png' --mark 'text=Далее|Кнопка видна|note' $D12 > '$TMP/sm.out' &&
  test -f '$R12/screenshots/F-001-next-annotated.png' && grep -q '\"scale\": 2.625' '$R12/screenshots/F-001-next.spec.json'"
check "finding.py add: находка без ручного JSON, снимок с отметкой (annotated + original), схема, viewed" sh -c "
  '$PY' '$S/finding.py' add '$R12' --title 'Каталог: «Далее» перекрыт баннером' --severity medium --direction visual-ui --type visual \
     --screen com.example.app.MainActivity --step 'Открыть каталог' --step 'adb_helpers.py font-scale 2.0' --step 'adb_helpers.py dumpsys custom' \
     --expected 'Кнопка видна' --actual 'Кнопка закрыта' --shot '$R12/screenshots/s1.png' --mark '80,1440,920,120|Закрыто баннером|error' \
     --env api=34 --env cell=c01 > '$TMP/fa.out' && '$PY' '$S/validate_findings.py' '$R12/findings.json' >/dev/null &&
  FID=\$('$PY' -c \"import json,sys; print(json.load(open(sys.argv[1]))['id'])\" '$TMP/fa.out') && test \"\$FID\" = F-004 &&
  '$PY' -c \"
import json,sys; f=[x for x in json.load(open(sys.argv[1]))['findings'] if x['id']=='F-004'][0]
assert f['screenshots'][0].endswith('-annotated.png') and f['shots'][0]['viewed'] is False and f['environment']['api']==34, f\" '$R12/findings.json' &&
  '$PY' '$S/finding.py' viewed '$R12' --id F-004 >/dev/null && '$PY' '$S/finding.py' list '$R12' | grep -q 'F-004'"
check "finding.py add: неверное направление -> 1, ничего не записано" sh -c "
  n=\$(grep -c '\"id\"' '$R12/findings.json'); test \$('$PY' '$S/finding.py' add '$R12' --title x --severity low --direction nope >/dev/null 2>&1; echo \$?) = 1 &&
  test \$(grep -c '\"id\"' '$R12/findings.json') = \$n"
check "render_draft: в черновике аннотированный снимок вместо оригинала; --human-steps — шаги действиями, команда без перевода — «Проверить»" sh -c "
  '$PY' '$S/render_draft.py' detailed '$R12/findings.json' --id F-004 --human-steps --out '$TMP/d4.md' 2> '$TMP/d4.err' >/dev/null &&
  grep -q 's1-annotated.png' '$TMP/d4.md' && ! grep -q '(screenshots/s1.png)' '$TMP/d4.md' && grep -q 'Размер шрифта: максимальный' '$TMP/d4.md' &&
  grep -q 'переписать для человека' '$TMP/d4.err'"

# ---------- publication: issue forms (fake gh), known docs, attachments by branch, disclosure ----------
GH="$TMP/ghrepo"; mkdir -p "$GH/.github/ISSUE_TEMPLATE" "$GH/docs"; cp "$F/forms/"*.yml "$GH/.github/ISSUE_TEMPLATE/"; cp "$F/known.md" "$GH/docs/KNOWN.md"
printf '#!/bin/sh\nexec "%s" "%s" "$@"\n' "$PY" "$H/fake_gh.py" > "$TMP/fakegh"; chmod +x "$TMP/fakegh"
export QA_GH_BIN="$TMP/fakegh" FAKE_GH_REPO="$GH" FAKE_GH_STATE="$TMP/ghstate"
check "issue_forms fetch: формы репозитория (только чтение) в raw/forms/<owner__repo>" sh -c "
  '$PY' '$S/issue_forms.py' fetch --repo owner/repo --out '$R12/raw/forms/owner__repo' > '$TMP/ff.out' &&
  test -f '$R12/raw/forms/owner__repo/20-bug.yml' && test -f '$R12/raw/forms/owner__repo/30-feature.yml' && grep -q '\"kind\": \"config\"' '$TMP/ff.out'"
printf '{"actual": "Кнопка закрыта", "steps": "1. Открыть", "severity": "high", "app_version": "2.3.1 (42)", "android": "Android 14 (API 34)", "logs": "E X: boom"}' > "$TMP/vals.json"
check "issue_forms map/render: dropdown — точный вариант («high» → «Высокая»), обязательная отметка -> проблема (1); с map.json -> 0, тело как из веб-формы" sh -c "
  '$PY' '$S/issue_forms.py' map '$F/forms/20-bug.yml' --values '$TMP/vals.json' > '$TMP/fm.out'; test \$? = 1 && grep -q 'Высокая' '$TMP/fm.out' && grep -q 'Я поискал' '$TMP/fm.out' &&
  printf '{\"Я поискал среди открытых issues\": true}' > '$TMP/map.json' &&
  '$PY' '$S/issue_forms.py' render '$F/forms/20-bug.yml' --values '$TMP/vals.json' --overrides '$TMP/map.json' --title 'Кнопка' --out '$TMP/fb.md' > '$TMP/fr.out' &&
  grep -q '\"title\": \"\[Bug\]: Кнопка\"' '$TMP/fr.out' && grep -q '^### Шаги воспроизведения' '$TMP/fb.md' && grep -q '^_No response_' '$TMP/fb.md' &&
  grep -q '^- \[X\] Я поискал' '$TMP/fb.md' && grep -q '^- \[ \] Готов помочь' '$TMP/fb.md' && grep -q '^\`\`\`shell' '$TMP/fb.md' && ! grep -q 'Спасибо, что сообщаете' '$TMP/fb.md'"
check "issue_forms: значение dropdown не из вариантов в map.json -> проблема" sh -c "
  printf '{\"severity\": \"P1\"}' > '$TMP/map2.json'; '$PY' '$S/issue_forms.py' map '$F/forms/20-bug.yml' --values '$TMP/vals.json' --overrides '$TMP/map2.json' | grep -q 'не из вариантов'"
"$PY" -c "
import json,sys; p=sys.argv[1]; d=json.load(open(p))
d['findings'].append({'id':'F-005','direction':'ux','check_id':'ux.idea','type':'proposal','severity':'low','title':'Показывать оставшееся время','screen':'MainActivity','sources':['own:checklist'],'suggestion':'Показать оценку времени'})
json.dump(d, open(p,'w'), ensure_ascii=False)" "$R12/findings.json"
yedit "$R12/run-config.yaml" "$TMP/rc-ours.yaml" '    severity_map:' '    ours: true\n    severity_map:'
yedit "$R12/run-config.yaml" "$TMP/rc-att.yaml" '    labels: existing' '    labels: existing\n    attachments: branch\n    attachments_branch: qa-screens\n    attachments_dir: qa/run12'
check "render_draft --form auto: ошибка — по форме бага, предложение — по форме предложения; Форма и Проверить в index.md" sh -c "
  '$PY' '$S/render_draft.py' all '$R12/findings.json' --run-dir '$R12' --repo owner/repo --form auto 2>/dev/null >/dev/null && D='$R12/drafts/owner__repo' &&
  grep -l '^### Шаги воспроизведения' \"\$D\"/*.body.md >/dev/null && grep -l '^### Предложение' \"\$D\"/*.body.md >/dev/null &&
  grep -q '20-bug.yml' \"\$D/index.md\" && grep -q '30-feature.yml' \"\$D/index.md\" && grep -q 'Я поискал' \"\$D/index.md\" && grep -q -- '--label \"triage\"' \"\$D/index.md\""
check "disclosure none: без подписи, маркеров и меток инструмента; предупреждение для чужого трекера; ours: true — без него" sh -c "
  '$PY' '$S/render_draft.py' all '$R12/findings.json' --run-dir '$R12' --repo owner/repo --disclosure none 2> '$TMP/dn.err' >/dev/null && D='$R12/drafts/owner__repo' &&
  ! grep -rqi 'android-qa-audit' \"\$D\"/*.body.md && ! grep -rq '<!--' \"\$D\"/*.body.md && grep -q 'ввести мейнтейнеров в заблуждение' \"\$D/index.md\" &&
  grep -q 'заблуждение' '$TMP/dn.err' && test -s '$TMP/rc-ours.yaml' &&
  '$PY' '$S/render_draft.py' all '$R12/findings.json' --run-dir '$R12' --repo owner/repo --disclosure none --config '$TMP/rc-ours.yaml' 2> '$TMP/dn2.err' >/dev/null &&
  ! grep -q 'заблуждение' '$TMP/dn2.err' && '$PY' '$S/render_draft.py' detailed '$R12/findings.json' --id F-001 | grep -q 'android-qa-audit:fp='"
check "known_docs: кандидаты «уже известно» с цитатой (fetch через gh, только чтение); set -> KNOWN, только отчёт" sh -c "
  '$PY' '$S/known_docs.py' fetch --repo owner/repo --path docs/KNOWN.md --out '$R12/raw/known' >/dev/null &&
  '$PY' '$S/known_docs.py' check '$R12/findings.json' --doc '$R12/raw/known' > '$TMP/kn.out'; test \$? = 1 && grep -q 'F-002' '$TMP/kn.out' && grep -q 'задумано/известно' '$TMP/kn.out' &&
  '$PY' '$S/known_docs.py' set '$R12/findings.json' --id F-002 --doc '$R12/raw/known/docs__KNOWN.md' --quote 'Кнопка «Поделиться» … известная проблема' >/dev/null &&
  '$PY' '$S/validate_findings.py' '$R12/findings.json' >/dev/null && '$PY' '$S/build_report.py' publish-table '$R12' | grep -q 'описано в документах проекта' &&
  '$PY' '$S/build_report.py' report '$R12' >/dev/null && grep -q '## Уже известно' '$R12/report.md'"
check "attachments: план без сети; push без --yes — только план; push --yes — ветка создана, файлы загружены, повтор — «уже есть»; verify" sh -c "
  '$PY' '$S/attachments.py' plan '$R12' --repo owner/repo --branch qa-screens --dir qa/run12 > '$TMP/at.out' && grep -q 's1-annotated.png' '$TMP/at.out' &&
  ! grep -q ' screenshots/s1.png ' '$TMP/at.out' && test ! -e '$TMP/ghstate/branches.json' &&
  '$PY' '$S/attachments.py' push '$R12' --repo owner/repo --branch qa-screens --dir qa/run12 | grep -q 'План без изменений' &&
  '$PY' '$S/attachments.py' push '$R12' --repo owner/repo --branch qa-screens --dir qa/run12 --yes > '$TMP/at2.out' &&
  grep -q 'qa-screens' '$TMP/ghstate/branches.json' && test -f '$TMP/ghstate/uploads/qa-screens/qa/run12/s1-annotated.png' && grep -q 'загружен' '$TMP/at2.out' &&
  '$PY' '$S/attachments.py' push '$R12' --repo owner/repo --branch qa-screens --dir qa/run12 --yes | grep -q 'уже есть' &&
  '$PY' '$S/attachments.py' verify '$R12' --repo owner/repo --branch qa-screens --dir qa/run12 | grep -q '\"ok\": true' &&
  grep -q 'https://github.com/owner/repo/blob/qa-screens/qa/run12' '$R12/attachments.json'"
check "render_draft: repos[].attachments: branch -> ссылки blob/<ветка>/<папка>/…?raw=true" sh -c "
  test -s '$TMP/rc-att.yaml' &&
  '$PY' '$S/render_draft.py' detailed '$R12/findings.json' --id F-004 --repo owner/repo --config '$TMP/rc-att.yaml' --run-dir '$R12' | grep -q 'blob/qa-screens/qa/run12/s1-annotated.png?raw=true'"

# ---------- file picker, push-media, ime ----------
cat > "$TMP/flow-pick.json" <<'JSON'
{"state": "recent", "screens": {
 "recent": {"xml": "picker_recent.xml", "focus": "com.google.android.documentsui/com.android.documentsui.picker.PickActivity", "taps": [{"bounds": [0, 140, 140, 280], "to": "drawer"}]},
 "drawer": {"xml": "picker_drawer.xml", "focus": "com.google.android.documentsui/com.android.documentsui.picker.PickActivity", "taps": [{"bounds": [0, 600, 800, 700], "to": "dl1"}]},
 "dl1": {"xml": "picker_dl1.xml", "focus": "com.google.android.documentsui/com.android.documentsui.picker.PickActivity", "swipe": "dl2"},
 "dl2": {"xml": "picker_dl2.xml", "focus": "com.google.android.documentsui/com.android.documentsui.picker.PickActivity", "taps": [{"bounds": [0, 900, 1080, 1100], "to": "app"}]},
 "app": {"xml": "window_dump.xml", "focus": "com.example.app/.MainActivity"}}}
JSON
check "import-file: выбор файла не открыт -> 4; в пикере без --confirmed -> 2 (системное приложение)" sh -c "
  unset FAKE_ADB_UI_FLOW; test \$('$PY' '$S/adb_helpers.py' import-file --name qa-speech.wav $D12 >/dev/null 2>&1; echo \$?) = 4 &&
  rm -f '$FAKE_ADB_STATE'/ui-*.txt; test \$(FAKE_ADB_UI_FLOW='$TMP/flow-pick.json' '$PY' '$S/adb_helpers.py' import-file --name qa-speech.wav --folder Download $D12 >/dev/null 2>&1; echo \$?) = 2"
check "import-file --confirmed: корни → Downloads → прокрутка → файл → снова приложение (одно согласие на весь импорт)" sh -c "
  rm -f '$FAKE_ADB_STATE'/ui-*.txt; FAKE_ADB_UI_FLOW='$TMP/flow-pick.json' '$PY' '$S/adb_helpers.py' import-file --name qa-speech.wav --folder Download --retries 2 --confirmed $D12 > '$TMP/if.out' &&
  '$PY' -c \"
import json,sys; d=json.load(open(sys.argv[1])); assert d['ok'] and d['focus']['package']=='com.example.app', d
assert d['steps'][:2]==['список папок','папка «Downloads»'] and 'прокрутка списка' in d['steps'] and d['steps'][-1]=='файл «qa-speech.wav»', d['steps']\" '$TMP/if.out'"
yedit "$R12/run-config.yaml" "$TMP/rc-pick.yaml" '  preapproved_actions: []' '  preapproved_actions: []\n  preapproved_packages: [com.google.android.documentsui]'
check "rules.preapproved_packages: выбор файла разрешён на весь прогон — import-file без --confirmed" sh -c "
  rm -f '$FAKE_ADB_STATE'/ui-*.txt; FAKE_ADB_UI_FLOW='$TMP/flow-pick.json' '$PY' '$S/adb_helpers.py' import-file --name qa-speech.wav --folder Download --retries 2 --serial emulator-5554 --run-dir '$R12' --config '$TMP/rc-pick.yaml' | grep -q '\"ok\": true'"
check "push-media: /sdcard/Download/qa-<имя> + медиасканер; --remove; на реальном устройстве (app-only) — тоже свой файл" sh -c "
  '$PY' '$S/adb_helpers.py' push-media '$TMP/speech.wav' --name voice1.wav $D12 | grep -q '/sdcard/Download/qa-voice1.wav' &&
  '$PY' '$S/adb_helpers.py' push-media --remove voice1.wav $D12 >/dev/null && grep -q 'rm -f /sdcard/Download/qa-voice1.wav' '$FAKE_ADB_LOG' &&
  '$PY' '$S/adb_helpers.py' push-media '$TMP/speech.wav' --serial R58N00TEST01 --run-dir '$R12' | grep -q '\"ok\": true'"
printf 'apk' > "$TMP/ADBKeyboard.apk"
check "ime: status; install-adbkeyboard — чужой APK -> 3, без --confirmed -> 2, с --confirmed -> установлен и включён; реальное устройство -> 4" sh -c "
  '$PY' '$S/adb_helpers.py' ime status $D12 | grep -q 'adbkeyboard_installed' &&
  test \$('$PY' '$S/adb_helpers.py' ime install-adbkeyboard --apk '$TMP/in/other.apk' --confirmed $D12 >/dev/null 2>&1; echo \$?) = 3 &&
  test \$('$PY' '$S/adb_helpers.py' ime install-adbkeyboard --apk '$TMP/ADBKeyboard.apk' $D12 >/dev/null 2>&1; echo \$?) = 2 &&
  '$PY' '$S/adb_helpers.py' ime install-adbkeyboard --apk '$TMP/ADBKeyboard.apk' --confirmed $D12 | grep -q '\"installed\": true' &&
  grep -q 'ime enable com.android.adbkeyboard/.AdbIME' '$FAKE_ADB_LOG' &&
  test \$('$PY' '$S/adb_helpers.py' ime install-adbkeyboard --apk '$TMP/ADBKeyboard.apk' --confirmed --serial R58N00TEST01 --run-dir '$R12' >/dev/null 2>&1; echo \$?) = 4"

# ---------- qa wrapper, --journal-done, wait-boot ready ----------
check "scripts/qa <serial> <команда>: --serial и --run-dir из QA_RUN_DIR, работает в zsh и sh" sh -c "
  QA_RUN_DIR='$R12' '$S/qa' emulator-5554 current | grep -q 'com.example.app' && QA_RUN_DIR='$R12' '$S/qa' emulator-5554 dump-ui --texts | grep -q 'Далее' &&
  { ! command -v zsh >/dev/null 2>&1 || QA_RUN_DIR='$R12' zsh -c \"'$S/qa' emulator-5554 key BACK\" | grep -q '\"key\": \"BACK\"'; }"
check "--journal-done: пункт журнала отмечается после успешной команды" sh -c "
  '$PY' '$S/journal.py' todo '$R12' 'Разведка' >/dev/null && '$PY' '$S/adb_helpers.py' current --journal-done Разведка $D12 >/dev/null &&
  grep -q '\[x\].*Разведка' '$R12/journal.md'"

# ---------- matrix: existing own AVDs, phone-8gb, user cells; intake: lite, disclosure, hints ----------
"$PY" "$S/check_env.py" --fast --json "$TMP/env12.json" >/dev/null 2>&1
mm(){ printf '%s\n' "$1" > "$TMP/mm.yaml"; "$PY" "$S/matrix.py" build --config "$TMP/mm.yaml" --env "$TMP/env12.json" --apk-info "$RUN/apk-info.json" --out "$TMP/mm.json" > "$TMP/mm.out"; }
mm 'depth: smoke
directions: [functional]
devices:
  hardware: []
  custom:
    - id: ram-2048
      profile: phone
      ram_mb: 2048
      cores: 2'
check "matrix: свой AVD с теми же параметрами переиспользуется (stand.existing), не создаётся новый" pyok "
import json,sys; m=json.load(open(sys.argv[1])); c=m['cells'][0]
assert c['stand']['name']=='qa-api34-pixel7-2gb-2c' and c['stand']['existing'] and 'qa-api34-pixel7-2gb-2c' in m['resources']['avds_existing'], c
assert 'qa-api34-pixel7-2gb-2c' not in m['resources']['avds_to_create']
" "$TMP/mm.json"
mm 'depth: standard
directions: [functional]
devices:
  hardware: [qa-api34-pixel7-2gb-4c]
matrix:
  cells:
    - id: rec60
      api: 34
      hardware: phone-8gb
      scenario: запись 60 мин, экран выключен
      manual_minutes: 10
      background_minutes: 60'
check "matrix: devices.hardware — имя своего AVD (только его API), профиль phone-8gb, matrix.cells, время «ручное + фон»" pyok "
import json,sys; m=json.load(open(sys.argv[1])); c=m['cells']
own=[x for x in c if x['hardware']=='qa-api34-pixel7-2gb-4c']; assert own and all(x['api']==34 for x in own) and own[0]['stand']['name']=='qa-api34-pixel7-2gb-4c', c
u=[x for x in c if x['kind']=='custom'][0]; assert u['stand']['name']=='qa-api34-pixel7-8gb-4c' and u['est_background_minutes']==60 and u['scenario'].startswith('запись'), u
assert m['time']['background_minutes']==60 and m['hardware'].get('qa-api34-pixel7-2gb-4c', {}).get('ram_mb')==2048
out=open(sys.argv[2],encoding='utf-8').read(); assert '+ 60 фон' in out and 'фоновые задачи' in out
" "$TMP/mm.json" "$TMP/mm.out"
check "intake: disclosure по умолчанию tool; «без упоминания скила» -> none + предупреждение; подсказки кириллица и голосовое приложение" sh -c "
  '$PY' '$S/intake.py' from-text --json --text 'Протестируй app.apk, issues в owner/repo' | '$PY' -c \"
import json,sys; d=json.load(sys.stdin); assert d['config']['publish']['disclosure']=='tool' and d['config']['repos'][0]['disclosure']=='tool'\" &&
  '$PY' '$S/intake.py' from-text --json --text 'Протестируй диктофон app.apk, проверь поиск по русскому тексту, issues в owner/repo без упоминания скила' | '$PY' -c \"
import json,sys; d=json.load(sys.stdin); c=d['config']; n=' '.join(d['notes'])
assert c['publish']['disclosure']=='none' and c['repos'][0]['disclosure']=='none' and 'заблуждение' in n and '--clipboard' in n and 'mic-inject' in n, d\""
check "intake --lite: только неясное (одним вопросом) и план; «не трогай микрофон» — не подсказка голосового приложения" sh -c "
  '$PY' '$S/intake.py' from-text --lite --json --text 'Используя скилл Android qa audit, протестируй app.apk на Android 14' | '$PY' -c \"
import json,sys; d=json.load(sys.stdin); l=d['lite']; assert d['config']['lite'] and l['plan'] and not any('output_dir' in q for q in l['questions']), l\" &&
  '$PY' '$S/intake.py' from-text --json --text 'Протестируй app.apk, не трогай микрофон' | '$PY' -c \"
import json,sys; d=json.load(sys.stdin); assert not any('mic-inject' in n for n in d['notes']), d['notes']\""

# ---------- documentation hygiene ----------
check "документация: нет примеров A=\"python3 …\" + \$A … и D=\"--serial …\" + \$D (zsh не делит их на слова)" "$PY" "$H/shared/doc_zsh.py" "$HERE/.."
check "вендорная копия annotate.js: та же, что в site-qa-audit (иначе — только заметка, не ошибка)" sh -c "
  cmp -s '$S/node/annotate.js' '$HERE/../../site-qa-audit/scripts/node/annotate.js' || echo 'NOTE: annotate.js отличается от site-qa-audit — обновить копию'; true"
