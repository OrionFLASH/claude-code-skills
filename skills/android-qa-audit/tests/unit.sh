#!/usr/bin/env bash
# Offline tests of android-qa-audit: no device, no emulator, no network. Fake adb and SDK tools
# (tests/helpers/fake_adb.py, fake_tools.py) in a temporary fake SDK; the user's ~/.android is never touched.
# PY=/usr/bin/python3 tests/unit.sh — run with another Python (minimum 3.9).
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; S="$HERE/../scripts"; F="$HERE/fixtures"; T="$HERE/../templates"
PY="${PY:-$(command -v python3 || command -v python)}"
export PYTHONDONTWRITEBYTECODE=1
TMP="$(mktemp -d)"; trap 'pkill -f "fake_tools.py emulator" >/dev/null 2>&1; rm -rf "$TMP"' EXIT
pass=0; fail=0
ok(){ echo "PASS $1"; pass=$((pass+1)); }; bad(){ echo "FAIL $1"; fail=$((fail+1)); }
check(){ local name="$1"; shift; if "$@"; then ok "$name"; else bad "$name"; fi; }
rc(){ "$@" >/dev/null 2>&1; echo $?; }
pyok(){ "$PY" -c "$1" "${@:2}"; }

echo "Python: $("$PY" --version 2>&1)"

# ---------- isolated environment: fake SDK, fake AVD home, no real adb ----------
export HOME="$TMP/home" CLAUDE_SKILLS_DIR="$TMP/home/.claude/skills" XDG_CONFIG_HOME="$TMP/home/.config" GIT_CONFIG_NOSYSTEM=1
mkdir -p "$HOME" "$CLAUDE_SKILLS_DIR"
unset ANDROID_SDK_ROOT ANDROID_SERIAL ANDROID_USER_HOME ANDROID_EMULATOR_HOME ANDROID_SDK_HOME ANDROID_QA_OUTPUT_DIR
SDK="$TMP/sdk"; export ANDROID_HOME="$SDK" ANDROID_AVD_HOME="$TMP/avd"
export FAKE_ADB_FIXTURES="$F" FAKE_ADB_LOG="$TMP/adb.log" FAKE_ADB_STATE="$TMP/emu-state" FAKE_TOOLS_LOG="$TMP/tools.log"
HOSTABI=$("$PY" -c "import sys; sys.path.insert(0, sys.argv[1]); import sdkutil; print(sdkutil.host_abi())" "$S")
export FAKE_HOST_ABI="$HOSTABI"
mk(){ mkdir -p "$(dirname "$1")"; printf '#!/bin/sh\nexec "%s" "%s" %s "$@"\n' "$PY" "$2" "$3" > "$1"; chmod +x "$1"; }
mk "$SDK/platform-tools/adb" "$HERE/helpers/fake_adb.py" ""
mk "$SDK/emulator/emulator" "$HERE/helpers/fake_tools.py" emulator
mk "$SDK/cmdline-tools/latest/bin/avdmanager" "$HERE/helpers/fake_tools.py" avdmanager
mk "$SDK/cmdline-tools/latest/bin/sdkmanager" "$HERE/helpers/fake_tools.py" sdkmanager
mk "$SDK/build-tools/35.0.0/aapt2" "$HERE/helpers/fake_tools.py" aapt2
mk "$SDK/build-tools/35.0.0/apksigner" "$HERE/helpers/fake_tools.py" apksigner
printf 'Pkg.Revision=19.0\n' > "$SDK/cmdline-tools/latest/source.properties"
mkdir -p "$SDK/system-images/android-34/google_apis/$HOSTABI" "$SDK/platforms/android-34" "$ANDROID_AVD_HOME"
printf 'AndroidVersion.ApiLevel=34\nSystemImage.Abi=%s\nSystemImage.TagId=google_apis\nPkg.Desc=Google APIs\n' "$HOSTABI" \
  > "$SDK/system-images/android-34/google_apis/$HOSTABI/source.properties"
avd(){ # name owner(skill|none) api
  mkdir -p "$ANDROID_AVD_HOME/$1.avd"
  printf 'abi.type=%s\nhw.device.name=pixel_7\nhw.ramSize=2048\nhw.cpu.ncore=2\ndisk.dataPartition.size=6G\nhw.lcd.width=1080\nhw.lcd.height=2400\nhw.lcd.density=420\ntag.id=google_apis\n' "$HOSTABI" > "$ANDROID_AVD_HOME/$1.avd/config.ini"
  printf 'path=%s\ntarget=android-%s\n' "$ANDROID_AVD_HOME/$1.avd" "$3" > "$ANDROID_AVD_HOME/$1.ini"
  [ "$2" = skill ] && echo '{"created_by": "android-qa-audit"}' > "$ANDROID_AVD_HOME/$1.avd/android-qa-audit.json"
  return 0
}
avd qa-api34-pixel7-2gb-2c skill 34; avd Foreign_Phone none 34; avd qa-nomarker none 34
APK="$TMP/in/app-release.apk"; mkdir -p "$TMP/in"; printf 'fake apk bytes' > "$APK"; printf 'other' > "$TMP/in/other.apk"
RUN="$TMP/out/qa-runs/2026-10-08-com.example.app"; mkdir -p "$RUN"; cp "$F/run-config.yaml" "$RUN/run-config.yaml"

# ---------- syntax (Python 3.9 grammar) and wrappers ----------
synt=0
# an older interpreter (< 3.12) catches f-strings that reuse their own quotes — valid only from Python 3.12
OLDPY=""; for c in "${PY39:-}" /usr/bin/python3 python3.9 python3.10 python3.11; do
  [ -n "$c" ] && command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if (3,9) <= sys.version_info < (3,12) else 1)' 2>/dev/null && { OLDPY="$c"; break; }
done
for f in "$S"/*.py "$S"/shared/*.py "$HERE"/helpers/*.py; do
  for p in "$PY" $OLDPY; do
    "$p" -c "import ast,sys; src=open(sys.argv[1],encoding='utf-8').read(); ast.parse(src, sys.argv[1], feature_version=(3,9)); compile(src, sys.argv[1], 'exec')" "$f" 2>"$TMP/ast.err" \
      || { cat "$TMP/ast.err"; bad "syntax ($p): $(basename "$f")"; synt=1; }
  done
done; echo "syntax: проверено $PY${OLDPY:+ и $OLDPY}"
[ $synt -eq 0 ] && ok "синтаксис всех скриптов совместим с Python 3.9"
check "check_env.sh: обёртка исполняемая и передаёт аргументы" sh -c "head -1 '$S/check_env.sh' | grep -q bash && grep -q 'check_env.py\" \"\$@\"' '$S/check_env.sh'"
check "check_env.ps1: ищет Python 3.9+ и py -3" sh -c "grep -q \"'py', '-3'\" '$S/check_env.ps1' && grep -q 'check_env.py' '$S/check_env.ps1'"

# ---------- guard ----------
check "guard selftest" "$PY" "$S/guard.py" selftest
check "guard action: «Купить» -> deny (3)" test "$(rc "$PY" "$S/guard.py" action --text 'Купить' --config "$RUN/run-config.yaml")" = 3
check "guard action: правило пользователя U1 -> deny" test "$(rc "$PY" "$S/guard.py" action --text 'Опубликовать' --config "$RUN/run-config.yaml")" = 3
check "guard adb: pm clear чужого пакета -> deny" test "$(rc "$PY" "$S/guard.py" adb 'shell pm clear com.other.app' --config "$RUN/run-config.yaml")" = 3
check "guard adb: реальное устройство без согласия -> confirm" test "$(rc "$PY" "$S/guard.py" adb 'uninstall com.example.app' --stand real --serial X1 --config "$RUN/run-config.yaml")" = 2
check "guard export -> rules.json" sh -c "'$PY' '$S/guard.py' export --config '$RUN/run-config.yaml' --out '$RUN/rules.json' >/dev/null && grep -q deny_packages '$RUN/rules.json'"

# ---------- templates, miniyaml ----------
"$PY" "$S/shared/miniyaml.py" "$T/run-config.example.yaml" > "$TMP/rc.json"
check "run-config.example.yaml: разделы app/android/devices/stands/rules, max_workers 1..4" pyok "
import json,sys; d=json.load(open(sys.argv[1]))
assert d['app']['package']=='com.example.app' and d['android']['apis']=='auto'
assert d['stands']['create_avds'] is True and d['stands']['consent']==[] and d['matrix']['mode']=='reduced'
assert 1 <= d['parallel']['max_workers'] <= 4 and d['report_destinations']==[{'type':'local'}]
assert d['context']['reuse']=='new' and d['goal']['success']=='findings' and 'forbidden_packages' in d['rules']
" "$TMP/rc.json"
check "finding.schema.json: 11 направлений, Android-поля" pyok "
import json,sys; s=json.load(open(sys.argv[1])); f=s['\$defs']['finding']
assert len(f['properties']['direction']['enum'])==11
for k in ('environment','repro_rate','crash','logcat_excerpt','screen','app_version'): assert k in f['properties'], k
e=f['properties']['environment']['properties']
for k in ('api','device_profile','ram_mb','abi','stand','cell'): assert k in e, k
" "$T/finding.schema.json"
check "шаблоны: app-context.md, issue-detailed.md, run-report.md на месте" sh -c \
  "grep -q '.app-context/' '$T/app-context.md' && grep -q 'android-qa-audit:fp=' '$T/issue-detailed.md' && grep -q 'Матрица стендов' '$T/run-report.md'"

# ---------- sdkutil ----------
check "sdkutil: SDK из ANDROID_HOME, инструменты из SDK (не из PATH)" pyok "
import sys; sys.path.insert(0, sys.argv[1]); import sdkutil as su
sdk, why = su.find_sdk(); assert str(sdk).endswith('sdk') and why=='ANDROID_HOME', (sdk, why)
for t in ('adb','emulator','avdmanager','sdkmanager','aapt2','apksigner'): assert su.find_tool(t)['source']=='sdk', t
assert su.system_images(sdk)[0]['api']==34
" "$S"
check "sdkutil: adb devices -l — состояния и вид (эмулятор/устройство)" pyok "
import sys; sys.path.insert(0, sys.argv[1]); import sdkutil as su
d={x['serial']:x for x in su.parse_devices(open(sys.argv[2]).read() + 'X9 no permissions (user in plugdev group); see [http://developer.android.com/tools/device.html] usb:1-3\n')}
assert d['emulator-5554']['state']=='device' and d['emulator-5554']['kind']=='emulator'
assert d['RX00UNAUTH01']['state']=='unauthorized' and d['emulator-5570']['state']=='offline'
assert d['X9']['state']=='no permissions' and d['R58N00TEST01']['model']=='Example_Phone'
" "$S" "$F/adb-devices.txt"
check "sdkutil: владелец AVD — только qa- + метка" pyok "
import sys; sys.path.insert(0, sys.argv[1]); import sdkutil as su
o={a['name']:a['owner'] for a in su.list_avds()}
assert o=={'Foreign_Phone':'user','qa-api34-pixel7-2gb-2c':'skill','qa-nomarker':'qa-prefix-no-marker'}, o
a=[x for x in su.list_avds() if x['name']=='Foreign_Phone'][0]; assert a['ram_mb']==2048 and a['api']==34 and a['density']==420
assert su.size_mb('4G')==4096 and su.size_mb('512 MB')==512 and su.parse_api('android-37.0')==37
" "$S"

# ---------- check_env ----------
"$PY" "$S/check_env.py" --fast --json "$TMP/env.json" > "$TMP/env.out" 2>&1; c=$?
check "check_env --fast на фейковом SDK: код 0, «можно работать»" sh -c "test $c = 0 && grep -q 'Итог: можно работать' '$TMP/env.out'"
check "check_env: env.json — инструменты, образы, AVD, устройства, рекомендация потоков" pyok "
import json,sys; d=json.load(open(sys.argv[1]))
assert d['tools']['adb'].endswith('platform-tools/adb') and d['images'][0]['api']==34
assert {a['name'] for a in d['avds']}=={'Foreign_Phone','qa-api34-pixel7-2gb-2c','qa-nomarker'}
assert any(x['serial']=='R58N00TEST01' and x['kind']=='real' for x in d['devices'])
assert any(x['serial']=='emulator-5554' and x['kind']=='emulator' for x in d['devices'])
assert 1 <= d['recommended_max_workers'] <= 4 and 'agent:adversarial-breaker' in d['banned']
" "$TMP/env.json"
check "check_env: разбор emulator -accel-check (macOS, Linux, ошибка)" pyok "
import sys; sys.path.insert(0, sys.argv[1]); import check_env as c
assert c.parse_accel_check(0, 'accel:\n0\nHypervisor.Framework OS X Version 27.0\naccel\n')==(True, 'Hypervisor.Framework OS X Version 27.0')
assert c.parse_accel_check(0, 'accel:\n0\nKVM (version 12) is installed and usable.\naccel')[0] is True
assert c.parse_accel_check(1, 'accel:\n7\nWHPX is not installed\naccel')==(False, 'WHPX is not installed')
assert c.parse_accel_check(127, '')==(None, '')
" "$S"
check "check_env: unauthorized устройство и чужие AVD отмечены" sh -c "grep -q 'unauthorized' '$TMP/env.out' && grep -q 'чужой — не менять' '$TMP/env.out'"
check "check_env: adb не в PATH — подсказка для zsh" sh -c "grep -q 'не в PATH' '$TMP/env.out' && grep -q 'export ANDROID_HOME' '$TMP/env.out'"
mkdir -p "$TMP/empty"
check "check_env: нет SDK и adb -> код 1" test "$(ANDROID_HOME="$TMP/empty" PATH=/usr/bin:/bin rc "$PY" "$S/check_env.py" --fast --no-devices)" = 1

# ---------- apk_info ----------
"$PY" "$S/apk_info.py" analyze "$APK" --copy-to "$RUN/apk" --out "$RUN/apk-info.json" >/dev/null 2>"$TMP/apk.err"
check "apk_info analyze: пакет, версии, SDK, launcher, ABI" pyok "
import json,sys; d=json.load(open(sys.argv[1]))
assert d['package']=='com.example.app' and d['version_name']=='2.3.1' and d['version_code']==42
assert d['min_sdk']==24 and d['target_sdk']==34 and d['launchable_activity']=='com.example.app.MainActivity'
assert d['abis']==['arm64-v8a','armeabi-v7a','x86_64'] and d['debuggable'] is True and d['label']=='Example'
" "$RUN/apk-info.json"
check "apk_info: опасные и особые разрешения, maxSdk, API появления диалога" pyok "
import json,sys; d=json.load(open(sys.argv[1])); p={x['short']:x for x in d['permissions']}
assert set(d['dangerous_permissions'])=={'CAMERA','POST_NOTIFICATIONS','ACCESS_FINE_LOCATION'}, d['dangerous_permissions']
assert p['POST_NOTIFICATIONS']['runtime_since']==33 and p['ACCESS_FINE_LOCATION']['max_sdk']==32 and p['SYSTEM_ALERT_WINDOW']['special']
" "$RUN/apk-info.json"
check "apk_info: компоненты (exported), deep link, подпись debug, риски" pyok "
import json,sys; d=json.load(open(sys.argv[1])); c={x['name'].split('.')[-1]:x for x in d['components']}
assert c['SyncService']['exported'] and c['BootReceiver']['exported'] is False and c['DataProvider']['type']=='provider'
assert d['deep_links'][0]['uri']=='https://example.com/item' and d['deep_links'][0]['auto_verify']
assert d['signature']['debug_signed'] and d['signature']['schemes']==['v2'] and d['signature']['verified']
r={x['check_id'] for x in d['risks']}
assert {'sec.debuggable','sec.debug-signature','sec.allow-backup','sec.exported-component','sec.special-permissions'} <= r, r
assert 'sec.cleartext' not in r and not any('MainActivity' in x['title'] for x in d['risks'])
assert d['recommended_apis']['min']==24 and 34 in d['recommended_apis']['suggested']
" "$RUN/apk-info.json"
check "apk_info --copy-to: копия APK и SHA256SUMS в <RUN_DIR>/apk" sh -c \
  "test -f '$RUN/apk/app-release.apk' && grep -q 'app-release.apk' '$RUN/apk/SHA256SUMS' && cmp -s '$APK' '$RUN/apk/app-release.apk'"
check "apk_info summary: таблица для пользователя" sh -c "'$PY' '$S/apk_info.py' summary '$RUN/apk-info.json' | grep -q 'com.example.app' "
check "apk_info: формат aapt (v1) xmltree — (type 0x12), exported по умолчанию" pyok "
import sys; sys.path.insert(0, sys.argv[1]); import apk_info as a
t=a.parse_xmltree(open(sys.argv[2],encoding='utf-8').read()); info=a.from_manifest(t, {})
assert info['package']=='com.example.legacy' and info['min_sdk']==21 and info['target_sdk']==26
assert info['allow_backup'] is True and info['debuggable'] is False and info['uses_cleartext_traffic'] is True
c={x['name'].split('.')[-1]:x for x in info['components']}
assert c['Worker']['exported'] and not c['Worker']['exported_explicit'] and info['launchable_activity']=='com.example.legacy.Main'
" "$S" "$F/manifest-xmltree-aapt1.txt"
"$PY" -c "import zipfile,sys; z=zipfile.ZipFile(sys.argv[1],'w'); z.writestr('splits/base-master.apk','x'); z.writestr('splits/base-arm64_v8a.apk','y'); z.writestr('toc.pb','z'); z.close()" "$TMP/in/app.apks"
check "apk_info: .apks (base + split ABI)" sh -c "'$PY' '$S/apk_info.py' analyze '$TMP/in/app.apks' --no-signature | '$PY' -c \"
import json,sys; d=json.load(sys.stdin); assert d['source']['type']=='apks' and 'base-master.apk' in d['source']['inner'] and d['package']=='com.example.app'\""
check "apk_info: нет файла -> код 2" test "$(rc "$PY" "$S/apk_info.py" analyze "$TMP/in/missing.apk")" = 2

# ---------- avd_manager ----------
check "avd_manager list --json: владельцы и запущенные" sh -c "'$PY' '$S/avd_manager.py' list --json | '$PY' -c \"
import json,sys; d=json.load(sys.stdin); o={a['name']:a['owner'] for a in d['avds']}
assert o['Foreign_Phone']=='user' and d['running'].get('emulator-5554')=='qa-api34-pixel7-2gb-2c'\""
check "avd_manager name: qa-api34-small-2gb-2c" test "$("$PY" "$S/avd_manager.py" name --api 34 --profile small --ram 2048 --cores 2)" = "qa-api34-small-2gb-2c"
check "avd_manager plan: образ установлен, шаг create" sh -c "'$PY' '$S/avd_manager.py' plan --api 34 --profile small --json | '$PY' -c \"
import json,sys; d=json.load(sys.stdin); assert d['image_installed'] and d['name']=='qa-api34-small-2gb-2c' and d['config']['hw.ramSize']=='2048'
assert d['config']['hw.lcd.width']=='720' and any('create' in s for s in d['steps'])\""
check "avd_manager plan: нет образа API 33 -> шаг install-image" sh -c "'$PY' '$S/avd_manager.py' plan --api 33 --json | grep -q install-image"
check "avd_manager create: имя не qa- -> отказ" test "$(rc "$PY" "$S/avd_manager.py" create --api 34 --name MyPhone --yes)" = 2
check "avd_manager create без --yes: только план, AVD не создан" sh -c "'$PY' '$S/avd_manager.py' create --api 34 --profile small >/dev/null && test ! -e '$ANDROID_AVD_HOME/qa-api34-small-2gb-2c.ini'"
"$PY" "$S/avd_manager.py" create --api 34 --profile small --ram 2048 --cores 2 --data 4G --yes --run-dir "$RUN" > "$TMP/create.out" 2>&1
check "avd_manager create --yes: AVD, config.ini, метка, stands.json" sh -c "
  grep -q '^hw.ramSize=2048\$' '$ANDROID_AVD_HOME/qa-api34-small-2gb-2c.avd/config.ini' &&
  grep -q '^hw.cpu.ncore=2\$' '$ANDROID_AVD_HOME/qa-api34-small-2gb-2c.avd/config.ini' &&
  grep -q '^disk.dataPartition.size=4G\$' '$ANDROID_AVD_HOME/qa-api34-small-2gb-2c.avd/config.ini' &&
  grep -q '^hw.lcd.density=320\$' '$ANDROID_AVD_HOME/qa-api34-small-2gb-2c.avd/config.ini' &&
  test -f '$ANDROID_AVD_HOME/qa-api34-small-2gb-2c.avd/android-qa-audit.json' && grep -q qa-api34-small-2gb-2c '$RUN/stands.json'"
check "avd_manager create повторно: переиспользует свой AVD" sh -c "'$PY' '$S/avd_manager.py' create --api 34 --profile small --ram 2048 --cores 2 --yes --run-dir '$RUN' | grep -q '\"reused\": true'"
check "avd_manager delete чужого AVD -> 3, файлы целы" sh -c "test \$('$PY' '$S/avd_manager.py' delete Foreign_Phone --yes >/dev/null 2>&1; echo \$?) = 3 && test -f '$ANDROID_AVD_HOME/Foreign_Phone.ini'"
check "avd_manager delete qa- без метки -> 3" test "$(rc "$PY" "$S/avd_manager.py" delete qa-nomarker --yes)" = 3
check "avd_manager start чужого AVD без --allow-foreign -> 3" test "$(rc "$PY" "$S/avd_manager.py" start Foreign_Phone --run-dir "$RUN")" = 3
"$PY" "$S/avd_manager.py" start qa-api34-small-2gb-2c --headless --run-dir "$RUN" > "$TMP/start.out" 2>&1; c=$?
check "avd_manager start: свободный порт (5554 занят), -no-window, stands.json" sh -c "test $c = 0 && grep -q '\"serial\": \"emulator-5556\"' '$TMP/start.out' && grep -q -- '-no-window' '$TMP/start.out' && ! grep -q -- '-read-only' '$TMP/start.out'"
sleep 1
check "avd_manager wait-boot: boot_completed" sh -c "'$PY' '$S/avd_manager.py' wait-boot emulator-5556 --timeout 20 --run-dir '$RUN' | grep -q '\"api\": 34'"
check "avd_manager stop эмулятора не этого прогона -> 3" test "$(rc "$PY" "$S/avd_manager.py" stop emulator-5554 --run-dir "$RUN")" = 3
check "avd_manager stop своего эмулятора" sh -c "'$PY' '$S/avd_manager.py' stop emulator-5556 --run-dir '$RUN' | grep -q 'остановлен' && test ! -e '$FAKE_ADB_STATE/emulator-5556.json'"
check "avd_manager start чужого с --allow-foreign: -read-only принудительно" sh -c "
  '$PY' '$S/avd_manager.py' start Foreign_Phone --allow-foreign --headless --run-dir '$RUN' | grep -q -- '-read-only' &&
  '$PY' '$S/avd_manager.py' stop Foreign_Phone --run-dir '$RUN' >/dev/null"
check "avd_manager install-image без --yes: только план" sh -c "'$PY' '$S/avd_manager.py' install-image --api 33 | grep -q 'План без изменений'"
check "avd_manager install-image --yes без лицензий -> 5" test "$(rc "$PY" "$S/avd_manager.py" install-image --api 33 --yes)" = 5
check "avd_manager install-image --run-dir: образ уже есть -> stands.json images_installed (already)" sh -c "
  '$PY' '$S/avd_manager.py' install-image --api 34 --run-dir '$RUN' | grep -q 'уже установлен' && '$PY' -c \"
import json,sys; d=json.load(open(sys.argv[1])); assert d['images_installed'][-1]['already'] is True and 'android-34' in d['images_installed'][-1]['package']\" '$RUN/stands.json'"
mkdir -p "$TMP/run-img"; "$PY" "$S/journal.py" init "$TMP/run-img" --todo "Образ" >/dev/null
FAKE_JAVA_EA=1 "$PY" "$S/avd_manager.py" install-image --api 33 --yes --accept-licenses --run-dir "$TMP/run-img" > "$TMP/img.out" 2>&1; c=$?
check "install-image (Java -ea): шум «integer expression expected» скрыт при коде 0, пометка, stands.json и journal.md" sh -c "
  test $c = 0 && ! grep -q '25-ea0: integer expression' '$TMP/img.out' && grep -q 'Java -ea' '$TMP/img.out' && grep -q 'готово: system-images;android-33' '$TMP/img.out' &&
  grep -q 'images_installed' '$TMP/run-img/stands.json' && grep -q 'образ установлен: system-images;android-33' '$TMP/run-img/journal.md'"
check "sdkutil.run_sdk_tool: шум скрыт только при успехе; check_env: sdkmanager --version и пометка «безвредно»" pyok "
import os,sys; sys.path.insert(0, sys.argv[1]); os.environ['FAKE_JAVA_EA']='1'
import sdkutil as su, check_env as ce
sm=su.tool_path('sdkmanager'); code,out,err,noise=su.run_sdk_tool([sm,'--version'])
assert code==0 and noise==1 and 'integer expression' not in err and out.strip()=='19.0', (code,out,err,noise)
code,out,err,noise=su.run_sdk_tool([sm,'--bogus']); assert code!=0 and 'integer expression' in err and noise==1
p=ce.cmdline_tools_probe(sm); assert p['ok'] and p['version']=='19.0' and p['java_ea_noise']==1, p
assert su.strip_java_noise('a\n/x/avdmanager: line 1: test: 25-ea0: integer expression expected\nb\n')==('a\nb\n', 1)
" "$S"
check "avd_manager cleanup: план без --yes, удаление созданного AVD с --yes" sh -c "
  '$PY' '$S/avd_manager.py' cleanup --run-dir '$RUN' --delete-avds | grep -q 'delete-avd: qa-api34-small-2gb-2c' &&
  test -e '$ANDROID_AVD_HOME/qa-api34-small-2gb-2c.ini' &&
  '$PY' '$S/avd_manager.py' cleanup --run-dir '$RUN' --delete-avds --yes >/dev/null && test ! -e '$ANDROID_AVD_HOME/qa-api34-small-2gb-2c.ini' &&
  test -e '$ANDROID_AVD_HOME/Foreign_Phone.ini' && test -e '$ANDROID_AVD_HOME/qa-api34-pixel7-2gb-2c.ini'"

# ---------- adb_helpers (fake adb; emulator-5554 = own AVD qa-api34-pixel7-2gb-2c, R58N00TEST01 = real phone) ----------
: > "$FAKE_ADB_LOG"
check "adb_helpers dump-ui: элементы и кандидаты доступности" sh -c "'$PY' '$S/adb_helpers.py' dump-ui --serial emulator-5554 --run-dir '$RUN' --json '$RUN/raw/ui.json' > '$TMP/ui.out' &&
  grep -q 'a11y.missing-label: id=btn_share' '$TMP/ui.out' && grep -q 'a11y.touch-target: id=btn_share' '$TMP/ui.out' &&
  grep -q 'visual.offscreen: id=btn_login' '$TMP/ui.out' && grep -q 'visual.text-ellipsized' '$TMP/ui.out' && ! grep -q 'missing-label: id=row ' '$TMP/ui.out' &&
  grep -q 'Button \"Далее\" id=btn_next @540,1500' '$TMP/ui.out'"
check "rotate landscape: фактический размер после поворота 2400x1080, поворот применён" sh -c "'$PY' '$S/adb_helpers.py' rotate landscape --serial emulator-5554 --run-dir '$RUN' > '$TMP/rot.out' &&
  grep -q '\"screen\": \[2400, 1080\]' '$TMP/rot.out' && grep -q '\"applied\": true' '$TMP/rot.out' && grep -q '\"rotation_index\": 1' '$TMP/rot.out'"
check "dump-ui после rotate: нет ложных visual.offscreen, настоящий выход за край найден, размер 2400x1080" sh -c "'$PY' '$S/adb_helpers.py' dump-ui --serial emulator-5554 --run-dir '$RUN' --json '$RUN/raw/ui-land.json' > '$TMP/uil.out' &&
  grep -q 'размер 2400x1080 (поворот 1)' '$TMP/uil.out' && grep -q 'visual.offscreen: id=btn_more' '$TMP/uil.out' && test \$(grep -c 'visual.offscreen' '$TMP/uil.out') = 1 &&
  '$PY' -c \"import json,sys; d=json.load(open(sys.argv[1])); assert d['screen']['size']==[2400,1080] and d['screen']['rotation']==1, d['screen']\" '$RUN/raw/ui-land.json'"
check "rotate portrait: 1080x2400" sh -c "'$PY' '$S/adb_helpers.py' rotate portrait --serial emulator-5554 --run-dir '$RUN' | grep -q '\"screen\": \[1080, 2400\]'"
check "размер экрана: rotation из дампа, dumpsys window displays (ROTATION_90, mRotation), dumpsys input (Viewport), оси по границам" pyok "
import sys; sys.path.insert(0, sys.argv[1]); import adb_helpers as h
x=open(sys.argv[2], encoding='utf-8').read(); n=h.parse_ui(x)
assert h.screen_for_dump(x, n, (1080, 2400))[0]==(2400, 1080)
y=x.replace('rotation=\"1\"', ''); assert h.screen_for_dump(y, n, None, (1080, 2400))[0]==(2400, 1080)
assert h.parse_window_displays('  Display: mDisplayId=0\n    init=1080x2400 cur=2400x1080 app=2400x1017\n    mCurrentRotation=ROTATION_90\n')==((2400, 1080), 1)
assert h.parse_window_displays('Display: mDisplayId=0\n cur=1080x2400\n mRotation=0\n  Display: mDisplayId=2\n cur=640x480 mRotation=3')==((1080, 2400), 0)
assert h.parse_input_rotation('Viewport INTERNAL: displayId=0, uniqueId=local:1, port=0, orientation=3, logicalFrame=[0, 0, 2400, 1080]')==3
assert h.parse_input_rotation('    SurfaceOrientation: 1')==1 and h.parse_input_rotation('nothing') is None
c=[x for x in h.a11y_candidates(n, 420, (2400, 1080)) if x['check_id']=='visual.offscreen']; assert len(c)==1 and 'btn_more' in c[0]['element'], c
" "$S" "$F/window_dump_landscape.xml"
check "adb_helpers tap «Купить…» -> 3, нажатия нет, blocked.jsonl" sh -c "test \$('$PY' '$S/adb_helpers.py' tap --text Купить --serial emulator-5554 --run-dir '$RUN' >/dev/null 2>&1; echo \$?) = 3 &&
  ! grep -q 'input tap 540 1660' '$FAKE_ADB_LOG' && grep -q 'base:action:purchase' '$RUN/logs/blocked.jsonl'"
check "adb_helpers tap «Далее» -> нажатие в центр элемента" sh -c "'$PY' '$S/adb_helpers.py' tap --text Далее --serial emulator-5554 --run-dir '$RUN' >/dev/null && grep -q 'input tap 540 1500' '$FAKE_ADB_LOG'"
check "adb_helpers tap «Удалить» -> 2 (спросить), с --confirmed -> нажато" sh -c "test \$('$PY' '$S/adb_helpers.py' tap --text Удалить --serial emulator-5554 --run-dir '$RUN' >/dev/null 2>&1; echo \$?) = 2 &&
  ! grep -q 'input tap 540 1820' '$FAKE_ADB_LOG' && '$PY' '$S/adb_helpers.py' tap --text Удалить --confirmed --serial emulator-5554 --run-dir '$RUN' >/dev/null && grep -q 'input tap 540 1820' '$FAKE_ADB_LOG'"
check "adb_helpers tap по координатам кнопки «Купить» тоже запрещён" test "$(rc "$PY" "$S/adb_helpers.py" tap 500 1650 --serial emulator-5554 --run-dir "$RUN")" = 3
check "adb_helpers uninstall чужого пакета -> 3, adb uninstall не вызван" sh -c "test \$('$PY' '$S/adb_helpers.py' uninstall com.other.app --serial emulator-5554 --run-dir '$RUN' >/dev/null 2>&1; echo \$?) = 3 && ! grep -q '\"uninstall\", \"com.other.app\"' '$FAKE_ADB_LOG'"
check "adb_helpers clear на своём эмуляторе -> pm clear" sh -c "'$PY' '$S/adb_helpers.py' clear --serial emulator-5554 --run-dir '$RUN' | grep -q '\"ok\": true'"
check "adb_helpers реальное устройство: clear с согласием app-only -> ок" sh -c "'$PY' '$S/adb_helpers.py' clear --serial R58N00TEST01 --run-dir '$RUN' | grep -q '\"ok\": true'"
check "adb_helpers реальное устройство: font-scale (настройки устройства) -> 2" test "$(rc "$PY" "$S/adb_helpers.py" font-scale 1.3 --serial R58N00TEST01 --run-dir "$RUN")" = 2
check "adb_helpers реальное устройство без согласия -> 2" sh -c "sed 's/R58N00TEST01/R58N00OTHER0/' '$RUN/run-config.yaml' > '$TMP/rc-noconsent.yaml' && test \$('$PY' '$S/adb_helpers.py' clear --serial R58N00TEST01 --config '$TMP/rc-noconsent.yaml' >/dev/null 2>&1; echo \$?) = 2"
check "adb_helpers install APK другого приложения -> 3" test "$(rc "$PY" "$S/adb_helpers.py" install "$TMP/in/other.apk" --serial emulator-5554 --run-dir "$RUN")" = 3
check "adb_helpers install своего APK -> Success" sh -c "'$PY' '$S/adb_helpers.py' install '$RUN/apk/app-release.apk' --replace --serial emulator-5554 --run-dir '$RUN' | grep -q '\"ok\": true'"
check "adb_helpers text: пробелы -> %s, кириллица -> 4" sh -c "'$PY' '$S/adb_helpers.py' text 'hello world' --serial emulator-5554 --run-dir '$RUN' >/dev/null && grep -q 'input text hello%sworld' '$FAKE_ADB_LOG' &&
  test \$('$PY' '$S/adb_helpers.py' text 'привет' --serial emulator-5554 --run-dir '$RUN' >/dev/null 2>&1; echo \$?) = 4"
check "text: не-ASCII без опций -> 4 с подсказкой --translit / --adbkeyboard, ничего не введено" sh -c "
  '$PY' '$S/adb_helpers.py' text 'привет' --serial emulator-5554 --run-dir '$RUN' > /dev/null 2> '$TMP/tx.err'; test \$? = 4 &&
  grep -q -- '--translit' '$TMP/tx.err' && grep -q -- '--adbkeyboard' '$TMP/tx.err' && ! grep -q 'input text привет' '$FAKE_ADB_LOG'"
check "text --translit: латиница и пометка в выводе" sh -c "'$PY' '$S/adb_helpers.py' text 'QA Тест Щука' --translit --serial emulator-5554 --run-dir '$RUN' > '$TMP/tr.out' &&
  grep -q 'input text QA%sTest%sShchuka' '$FAKE_ADB_LOG' && grep -q '\"translit\": true' '$TMP/tr.out' && grep -q '\"typed\": \"QA Test Shchuka\"' '$TMP/tr.out'"
check "text --translit: emoji не транслитерируется -> 4; секрет (--env) — нельзя -> 2" sh -c "
  test \$('$PY' '$S/adb_helpers.py' text 'Тест 😀' --translit --serial emulator-5554 --run-dir '$RUN' >/dev/null 2>&1; echo \$?) = 4 &&
  test \$(QA_SECRET_TEST='Пароль' '$PY' '$S/adb_helpers.py' text --env QA_SECRET_TEST --translit --serial emulator-5554 --run-dir '$RUN' >/dev/null 2>&1; echo \$?) = 2"
check "text --adbkeyboard: нет ADBKeyBoard -> 4; реальное устройство -> 4" sh -c "
  test \$('$PY' '$S/adb_helpers.py' text 'привет' --adbkeyboard --serial emulator-5554 --run-dir '$RUN' >/dev/null 2>&1; echo \$?) = 4 &&
  test \$(FAKE_ADB_IME=com.android.adbkeyboard/.AdbIME '$PY' '$S/adb_helpers.py' text 'привет' --adbkeyboard --serial R58N00TEST01 --run-dir '$RUN' >/dev/null 2>&1; echo \$?) = 4"
check "text --adbkeyboard на своём эмуляторе: ime set, ADB_INPUT_B64, прежняя клавиатура возвращена" sh -c "
  FAKE_ADB_IME=com.android.adbkeyboard/.AdbIME '$PY' '$S/adb_helpers.py' text 'привет' --adbkeyboard --serial emulator-5554 --run-dir '$RUN' > '$TMP/ak.out' &&
  grep -q '\"via\": \"ADBKeyBoard\"' '$TMP/ak.out' && grep -q 'ADB_INPUT_B64' '$FAKE_ADB_LOG' && grep -q '0L/RgNC40LLQtdGC' '$FAKE_ADB_LOG' &&
  grep -q 'ime set com.android.adbkeyboard/.AdbIME' '$FAKE_ADB_LOG' && grep -q 'ime set com.android.inputmethod.latin/.LatinIME' '$FAKE_ADB_LOG'"
check "translit(): кириллица, ё, акценты; guard: ime set — изменение устройства" pyok "
import sys; sys.path.insert(0, sys.argv[1]); import adb_helpers as h, guard as g
assert h.translit('Ёжик Щука Café') == ('Yozhik Shchuka Cafe', []) and h.translit('a😀')[1]==['😀']
assert g.check_adb('shell ime set x/.Y', {}, 'real', 'S1')['decision']==g.CONFIRM and g.check_adb('shell ime list -a -s', {}, 'real', 'S1')['decision']==g.ALLOW
" "$S"
check "adb_helpers text --env: значение введено, но не напечатано и не в журнале действий" sh -c "QA_SECRET_TEST=Passw0rd '$PY' '$S/adb_helpers.py' text --env QA_SECRET_TEST --serial emulator-5554 --run-dir '$RUN' > '$TMP/sec.out' &&
  ! grep -q Passw0rd '$TMP/sec.out' && ! grep -q Passw0rd '$RUN/logs/actions.jsonl' && grep -q 'input text Passw0rd' '$FAKE_ADB_LOG'"
check "adb_helpers deeplink tel: -> 3" test "$(rc "$PY" "$S/adb_helpers.py" deeplink tel:+70000000000 --serial emulator-5554 --run-dir "$RUN")" = 3
check "adb_helpers deeplink своего домена -> am start VIEW" sh -c "'$PY' '$S/adb_helpers.py' deeplink https://example.com/item/1 --serial emulator-5554 --run-dir '$RUN' | grep -q '\"LaunchState\": \"COLD\"'"
check "adb_helpers meminfo/gfxinfo: разбор и metrics.jsonl" sh -c "'$PY' '$S/adb_helpers.py' meminfo --serial emulator-5554 --run-dir '$RUN' | grep -q '\"total_pss_kb\": 102400' &&
  '$PY' '$S/adb_helpers.py' gfxinfo --serial emulator-5554 --run-dir '$RUN' | grep -q '\"janky_percent\": 8.0' && test \$(grep -c . '$RUN/raw/metrics.jsonl') -ge 2"
check "adb_helpers meminfo: Activities, Java Heap" sh -c "'$PY' '$S/adb_helpers.py' meminfo --serial emulator-5554 --run-dir '$RUN' | grep -q '\"activities\": 2'"
check "adb_helpers start-time cold: медиана" sh -c "'$PY' '$S/adb_helpers.py' start-time --runs 2 --serial emulator-5554 --run-dir '$RUN' | grep -q '\"median_ms\": 812'"
check "adb_helpers crashes: только своё приложение, ANR, маскирование; чужое приложение — в other_processes" sh -c "'$PY' '$S/adb_helpers.py' crashes --serial emulator-5554 --run-dir '$RUN' > '$TMP/cr.out' && '$PY' -c \"
import json,sys; d=json.load(open(sys.argv[1])); assert d['by_type']=={'crash':1,'anr':1,'native':0}, d['by_type']
assert all(x['process'].startswith('com.example.app') for x in d['items']), d['items']
o=d['other_processes']; assert [x['process'] for x in o]==['com.other.app'] and o[0]['owner']=='other-app', o
raw=json.load(open(sys.argv[2])); t=json.dumps(raw['items'], ensure_ascii=False)
assert 'ivan.petrov@example.com' not in t and 'i***@e***.com' in t and 'other app' not in t and raw['other_processes'][0]['process']=='com.other.app'
\" '$TMP/cr.out' '$RUN/raw/crashes-emulator-5554.json'"
check "crashes: падение UiAutomation (dump-ui) из реального logcat — не crash приложения, в other_processes как инструмент" sh -c "
  FAKE_ADB_LOGCAT=logcat-uiautomation.txt '$PY' '$S/adb_helpers.py' crashes com.example.app --serial emulator-5554 --run-dir '$TMP/run-ui' > '$TMP/cru.out' && '$PY' -c \"
import json,sys; d=json.load(open(sys.argv[1])); assert d['count']==0 and d['items']==[], d
o=d['other_processes']; assert len(o)==1 and o[0]['owner']=='tool' and o[0]['thread']=='UiAutomation' and o[0]['pid']=='7460', o
assert 'Bad file descriptor' in o[0]['summary'] and o[0]['process'].startswith('app_process') and d['note']
\" '$TMP/cru.out'"
check "crashes: разбор по процессу — Process:, PID из «Start proc», чужой PID без Process:, ANR только своего пакета" pyok "
import sys; sys.path.insert(0, sys.argv[1]); import adb_helpers as h
log='''10-08 10:00:00.000   600   620 I ActivityManager: Start proc 4321:com.example.app/u0a55 for next-top-activity {com.example.app/.Main}
10-08 10:00:00.100   600   621 I ActivityManager: Start proc 4400:com.google.android.webview:sandboxed_process0:x:0/u0ai1 for  {com.example.app/x}
--------- beginning of crash
10-08 10:00:01.000  4321  4321 E AndroidRuntime: FATAL EXCEPTION: main
10-08 10:00:01.000  4321  4321 E AndroidRuntime: PID: 4321
10-08 10:00:01.000  4321  4321 E AndroidRuntime: java.lang.IllegalStateException: boom
10-08 10:00:02.000  4400  4400 E AndroidRuntime: FATAL EXCEPTION: main
10-08 10:00:02.000  4400  4400 E AndroidRuntime: Process: com.google.android.webview:sandboxed_process0:x:0, PID: 4400
10-08 10:00:02.000  4400  4400 E AndroidRuntime: java.lang.RuntimeException: renderer
10-08 10:00:03.000  4500  4510 E AndroidRuntime: FATAL EXCEPTION: pool-1
10-08 10:00:03.000  4500  4510 E AndroidRuntime: Process: com.example.app:sync, PID: 4500
10-08 10:00:03.000  4500  4510 E AndroidRuntime: java.lang.OutOfMemoryError: sync
10-08 10:00:04.000   600   650 E ActivityManager: ANR in com.google.android.gms (com.google.android.gms/.X)
10-08 10:00:04.000   600   650 E ActivityManager: Reason: executing service
10-08 10:00:05.000   999   999 F DEBUG   : pid: 999, tid: 999, name: x  >>> system_server <<<
'''
items, other = h.parse_crashes(log, 'com.example.app', with_others=True)
assert [(x['type'], x['process']) for x in items]==[('crash','com.example.app'),('crash','com.example.app:sync')], items
o={x['process']:x for x in other}
assert o['com.google.android.webview:sandboxed_process0:x:0']['related_to_app'] and o['com.google.android.gms']['type']=='anr'
assert o['system_server']['owner']=='system' and o['system_server']['type']=='native' and len(other)==3
assert h.parse_crashes(log, 'com.example.app')==items
" "$S"
check "adb_helpers logcat dump: токен в URL замаскирован" sh -c "'$PY' '$S/adb_helpers.py' logcat dump --out '$RUN/logs/lc.txt' --serial emulator-5554 --run-dir '$RUN' >/dev/null && grep -q 'token=\*\*\*' '$RUN/logs/lc.txt' && ! grep -q Abcdef0123456789Abcdef '$RUN/logs/lc.txt'"
check "logcat dump по умолчанию — только приложение (PID, перезапуск по «Start proc», строки ANR), --all — весь журнал" sh -c "
  grep -q 'FATAL EXCEPTION: main' '$RUN/logs/lc.txt' && grep -q 'Start proc 1240' '$RUN/logs/lc.txt' && grep -q 'Reason: Input dispatching' '$RUN/logs/lc.txt' &&
  grep -q OkHttp '$RUN/logs/lc.txt' && ! grep -q 'com.other.app' '$RUN/logs/lc.txt' && ! grep -q OtherSdk '$RUN/logs/lc.txt' && ! grep -q 'Slow operation' '$RUN/logs/lc.txt' &&
  '$PY' '$S/adb_helpers.py' logcat dump --all --out '$RUN/logs/lc-all.txt' --serial emulator-5554 --run-dir '$RUN' | grep -q '\"filtered\": false' &&
  grep -q 'com.other.app' '$RUN/logs/lc-all.txt' && grep -q OtherSdk '$RUN/logs/lc-all.txt'"
check "logcat dump реального фрагмента: строки приложения есть, UiAutomation и сервисов Google нет" sh -c "
  FAKE_ADB_LOGCAT=logcat-uiautomation.txt '$PY' '$S/adb_helpers.py' logcat dump --out '$TMP/lc-ui.txt' --serial emulator-5554 --run-dir '$RUN' >/dev/null &&
  grep -q 'Binder transaction failure' '$TMP/lc-ui.txt' && ! grep -q UiAutomation '$TMP/lc-ui.txt' && ! grep -q GellerException '$TMP/lc-ui.txt'"
waitpid(){ for _ in $(seq 1 50); do kill -0 "$1" 2>/dev/null || return 0; sleep 0.2; done; return 1; }
"$PY" "$S/adb_helpers.py" logcat start --serial emulator-5554 --run-dir "$RUN" > "$TMP/lcs.out" 2>&1
LPID=$("$PY" -c "import json,sys; print(json.load(open(sys.argv[1]))['pid'])" "$TMP/lcs.out" 2>/dev/null || echo 0)
waitpid "$LPID"
check "logcat start: фоновая запись с фильтром по приложению (по PID, с перезапуском), stop маскирует" sh -c "
  grep -q '\"filtered\": true' '$TMP/lcs.out' && '$PY' '$S/adb_helpers.py' logcat stop --serial emulator-5554 --run-dir '$RUN' >/dev/null &&
  F='$RUN/logs/logcat-emulator-5554.txt' && grep -q 'FATAL EXCEPTION: main' \$F && grep -q 'Start proc 1240' \$F && grep -q OkHttp \$F &&
  ! grep -q 'com.other.app' \$F && ! grep -q OtherSdk \$F && grep -q 'token=\*\*\*' \$F"
check "adb_helpers monkey: падение, seed для повтора" sh -c "'$PY' '$S/adb_helpers.py' monkey --events 500 --seed 42 --serial emulator-5554 --run-dir '$RUN' | '$PY' -c \"
import json,sys; d=json.load(sys.stdin); assert d['crash'] and d['aborted'] and d['events_injected']==137 and '-s 42' in d['repro']\""
check "adb_helpers monkey на реальном устройстве (app-only) -> 3" test "$(rc "$PY" "$S/adb_helpers.py" monkey --serial R58N00TEST01 --run-dir "$RUN")" = 3
check "adb_helpers screenshot: PNG в screenshots/" sh -c "'$PY' '$S/adb_helpers.py' screenshot --serial emulator-5554 --run-dir '$RUN' | grep -q screenshots/ && ls '$RUN'/screenshots/*.png >/dev/null"
check "adb_helpers permissions: runtime-разрешения" sh -c "'$PY' '$S/adb_helpers.py' permissions --serial emulator-5554 --run-dir '$RUN' | grep -q 'POST_NOTIFICATIONS\": {\"granted\": false'"
check "adb_helpers notifications: только своё приложение, маскирование" sh -c "'$PY' '$S/adb_helpers.py' notifications --serial emulator-5554 --run-dir '$RUN' > '$TMP/n.out' && grep -q '\"count\": 1' '$TMP/n.out' && grep -q 'i\*\*\*@e\*\*\*.com' '$TMP/n.out' && ! grep -q 'Чужое' '$TMP/n.out'"
check "adb_helpers size: diskstats" sh -c "'$PY' '$S/adb_helpers.py' size --serial emulator-5554 --run-dir '$RUN' | grep -q '\"data_bytes\": 3000000'"
check "adb_helpers network 3g на своём эмуляторе: emu network speed umts" sh -c "'$PY' '$S/adb_helpers.py' network 3g --serial emulator-5554 --run-dir '$RUN' >/dev/null && grep -q '\"network\", \"speed\", \"umts\"' '$FAKE_ADB_LOG'"
check "adb_helpers: actions.jsonl ведётся" test -s "$RUN/logs/actions.jsonl"

# ---------- matrix ----------
mx(){ printf 'depth: %s\ndirections: [functional, ux, accessibility, performance]\nparallel:\n  max_workers: %s\n' "$1" "$2" > "$TMP/mx.yaml"
      "$PY" "$S/matrix.py" build --config "$TMP/mx.yaml" --env "$TMP/env.json" --apk-info "$RUN/apk-info.json" --out "$TMP/m.json" >/dev/null; }
mx smoke 2
check "matrix smoke: 1 ячейка, основной профиль, все направления" pyok "
import json,sys; m=json.load(open(sys.argv[1])); c=m['cells']
assert len(c)==1 and c[0]['kind']=='primary' and c[0]['api']==34 and len(c[0]['directions'])==4 and c[0]['stand']['image_installed']
" "$TMP/m.json"
mx standard 4
check "matrix standard: 3 API (min/середина/target), слабый телефон, вариации на основном" pyok "
import json,sys; m=json.load(open(sys.argv[1]))
assert m['apis'][0]==24 and m['apis'][-1]==34 and len(m['apis'])==3, m['apis']
hw={c['hardware'] for c in m['cells']}; assert hw=={'phone','low-end'}, hw
p=[c for c in m['cells'] if c['kind']=='primary'][0]; assert 'dark-font' in p['variants'] and 'ux' in p['directions']
s=[c for c in m['cells'] if c['kind']=='secondary']; assert all('ux' not in c['directions'] for c in s)
assert 1 <= len(m['threads']) <= 4 and m['resources']['images_to_install']
assert all(c['stand']['name'].startswith('qa-api') for c in m['cells'])
" "$TMP/m.json"
mx deep 8
check "matrix deep: ≤ 7 API, складной только API ≥ 32, потоков ≤ 4" pyok "
import json,sys; m=json.load(open(sys.argv[1]))
assert len(m['apis'])<=7 and 33 in m['apis'] and 29 in m['apis']
assert all(c['api']>=32 for c in m['cells'] if c['hardware']=='fold') and any(c['hardware']=='tablet' for c in m['cells'])
assert len(m['threads'])<=4 and sum(len(t['cells']) for t in m['threads'])==len(m['cells'])
" "$TMP/m.json"
check "matrix show и variants" sh -c "'$PY' '$S/matrix.py' show '$TMP/m.json' | grep -q 'Потоки:' && '$PY' '$S/matrix.py' variants | grep -q 'dark-font'"
mxh(){ printf 'depth: %s\ndirections: [functional]\ndevices:\n  hardware: %s\n  custom:%s\n' "$1" "$2" "$3" > "$TMP/mxh.yaml"
       "$PY" "$S/matrix.py" build --config "$TMP/mxh.yaml" --env "$TMP/env.json" --apk-info "$RUN/apk-info.json" --out "$TMP/mh.json" >/dev/null; }
C8='
    - id: ram-8192
      profile: phone
      ram_mb: 8192
      cores: 4
      data: 6G
      label: 8 ГБ ОЗУ'
mxh smoke '[]' "$C8"
check "matrix: hardware [] + custom -> только custom (без лишней c01 «телефон 4 ГБ»), он primary" pyok "
import json,sys; m=json.load(open(sys.argv[1])); c=m['cells']
assert len(c)==1 and c[0]['hardware']=='ram-8192' and c[0]['kind']=='primary' and c[0]['ram_mb']==8192, c
assert list(m['hardware'])==['ram-8192'] and c[0]['stand']['name']=='qa-api34-pixel7-8gb-4c' and any('только свои' in n for n in m['notes'])
" "$TMP/mh.json"
mxh standard '[]' "$C8"
check "matrix standard: hardware [] + custom -> custom на всех API, primary на целевом" pyok "
import json,sys; m=json.load(open(sys.argv[1])); c=m['cells']
assert {x['hardware'] for x in c}=={'ram-8192'} and len(c)==len(m['apis'])==3 and sum(x['kind']=='primary' for x in c)==1, c
" "$TMP/mh.json"
mxh smoke '[]' ' []'
check "matrix: hardware [] и custom [] -> профиль по глубине (phone)" pyok "
import json,sys; m=json.load(open(sys.argv[1])); assert [x['hardware'] for x in m['cells']]==['phone'], m['cells']
" "$TMP/mh.json"
mxh smoke 'null' "$C8"
check "matrix: hardware null + custom -> по глубине и custom (как раньше), primary — phone" pyok "
import json,sys; m=json.load(open(sys.argv[1])); assert [(x['hardware'], x['kind']) for x in m['cells']]==[('phone','primary'),('ram-8192','secondary')], m['cells']
" "$TMP/mh.json"

# ---------- intake ----------
ij(){ "$PY" "$S/intake.py" from-text --text "$1" --json; }
check "intake: APK, Android 10/14 -> API 29/34, слабый телефон 2 ГБ, тёмная тема, сеть" sh -c "
  '$PY' '$S/intake.py' from-text --json --text 'Протестируй \"/tmp/builds/app-release.apk\" на Android 10 и Android 14 на слабом телефоне с 2 ГБ оперативной памяти, тёмная тема, медленная сеть 3G' | '$PY' -c \"
import json,sys; c=json.load(sys.stdin)['config']
assert c['app']['paths']==['/tmp/builds/app-release.apk'] and c['android']['apis']==[29,34]
assert 'low-end' in c['devices']['hardware'] and c['devices']['custom'][0]['ram_mb']==2048
assert {'dark','net-3g'} <= set(c['devices']['variants']) and c['parallel']['max_workers']==2\""
check "intake: пакет установленного приложения, реальное устройство -> 1 поток" sh -c "
  '$PY' '$S/intake.py' from-text --json --text 'Проверь установленное приложение, пакет com.example.app, на моём телефоне по USB в 3 потока' | '$PY' -c \"
import json,sys; d=json.load(sys.stdin); c=d['config']
assert c['app']['package']=='com.example.app' and c['app']['source']=='installed' and c['parallel']['max_workers']==1
assert any('реальное устройство' in n for n in d['notes'])\""
check "intake: 8 потоков -> 4; запреты с текстами кнопок" sh -c "
  '$PY' '$S/intake.py' from-text --json --text 'Протестируй app.apk в 8 потоков. Не нажимай «Купить» и «Отправить». Спрашивай перед удалением.' | '$PY' -c \"
import json,sys; d=json.load(sys.stdin); c=d['config']
assert c['parallel']['max_workers']==4 and c['rules']['forbidden_actions'][0]['texts']==['Купить','Отправить']
assert c['rules']['require_confirmation_actions'] and any('максимум 4' in n for n in d['notes'])\""
check "intake: пустой запрос -> 2" test "$(rc "$PY" "$S/intake.py" from-text --text '  ')" = 2
check "intake: запрет «камера / QR / точка доступа» -> правила с типовыми текстами RU+EN, пакеты камеры, «проверить на разведке»" sh -c "
  '$PY' '$S/intake.py' from-text --json --text 'Протестируй app.apk, 8 ГБ ОЗУ. Не трогать камеру и сканирование QR, не включать точку доступа Wi-Fi.' | '$PY' -c \"
import json,sys; d=json.load(sys.stdin); c=d['config']; r=c['rules']; fa=r['forbidden_actions']
t={x['topic'] for x in fa}; assert t=={'camera','qr','hotspot'}, t
txt=[y for x in fa for y in x['texts']]
for w in ('Камера','Camera','Сканировать QR','Scan QR','Точка доступа','Hotspot'): assert w in txt, w
assert 'com.android.camera2' in r['forbidden_packages'] and 'com.google.android.GoogleCamera' in r['forbidden_packages']
assert all('разведке' in x['review'] or 'отказ' in x['review'] for x in fa) and any('проверить на разведке' in n for n in d['notes'])
dlg=[x for x in fa if x.get('exact')]; assert len(dlg)==1 and 'Allow' in dlg[0]['texts'] and isinstance(dlg[0]['context'], list)
assert c['devices']['hardware']==[] and c['devices']['custom'][0]['ram_mb']==8192\""
check "intake: «не трогай камеру, микрофон и геолокацию» — отрицание на всё перечисление; «но проверь уведомления» — не запрет" sh -c "
  '$PY' '$S/intake.py' from-text --json --text 'app.apk. Не трогай камеру, микрофон и геолокацию. Не трогай Bluetooth, но проверь уведомления.' | '$PY' -c \"
import json,sys; t={x['topic'] for x in json.load(sys.stdin)['config']['rules']['forbidden_actions']}
assert t=={'camera','microphone','location','bluetooth'}, t\""
"$PY" "$S/intake.py" from-text --text 'Протестируй app.apk. Не трогать камеру и сканирование QR, не включать точку доступа.' --out "$TMP/rc-topics.yaml" >/dev/null
check "guard по черновику intake: «Scan QR» и «Allow» в диалоге камеры -> 3, «Don’t allow» и «Начать» -> 0" sh -c "
  test \$('$PY' '$S/guard.py' action --text 'Scan QR' --config '$TMP/rc-topics.yaml' >/dev/null 2>&1; echo \$?) = 3 &&
  test \$('$PY' '$S/guard.py' action --text 'Allow' --context 'Allow Example to take pictures and record video?' --config '$TMP/rc-topics.yaml' >/dev/null 2>&1; echo \$?) = 3 &&
  test \$('$PY' '$S/guard.py' action --text 'Don’t allow' --context 'Allow Example to take pictures and record video?' --config '$TMP/rc-topics.yaml' >/dev/null 2>&1; echo \$?) = 0 &&
  test \$('$PY' '$S/guard.py' action --text 'Начать' --config '$TMP/rc-topics.yaml' >/dev/null 2>&1; echo \$?) = 0"
check "intake: git.allow_commit_results / allow_commit_apk — только при явном разрешении (RU/EN), по умолчанию false" sh -c "
  for q in 'Протестируй app.apk' 'Протестируй app.apk, не коммить результаты' 'Протестируй app.apk и добавь qa-runs в .gitignore'; do
    '$PY' '$S/intake.py' from-text --json --text \"\$q\" | '$PY' -c \"import json,sys; g=json.load(sys.stdin)['config']['git']; assert g=={'allow_commit_results': False, 'allow_commit_apk': False}, g\" || exit 1; done
  '$PY' '$S/intake.py' from-text --json --text 'Протестируй app.apk и положи результаты в репозиторий' | '$PY' -c \"import json,sys; g=json.load(sys.stdin)['config']['git']; assert g['allow_commit_results'] and not g['allow_commit_apk'], g\" &&
  '$PY' '$S/intake.py' from-text --json --text 'Test app.apk, commit the results and the APK too' | '$PY' -c \"import json,sys; g=json.load(sys.stdin)['config']['git']; assert g['allow_commit_results'] and g['allow_commit_apk'], g\""
check "commit_permission: разрешения и отрицания (RU/EN)" pyok "
import sys; sys.path.insert(0, sys.argv[1]); import qa_gitignore as q
yes=['Положи результаты в репозиторий','коммить результаты','Хочу коммитить qa-runs','результаты можно коммитить','не добавляй qa-runs в .gitignore',
     'Please commit the results','keep the results in git','add the test results to the repo']
no=['не коммить результаты','Результаты не коммитить','не нужно коммитить результаты','добавь qa-runs в .gitignore','do not commit the results',
    'Протестируй сборку из коммита abc123 и запиши результаты','test the build from commit abc and write results','Сохрани результаты в /tmp/x']
for t in yes: assert q.commit_permission(t)['allow_commit_results'], t
for t in no: assert not q.commit_permission(t)['allow_commit_results'], t
assert q.commit_permission('APK тоже коммить')['allow_commit_apk'] and not q.commit_permission('коммить результаты')['allow_commit_apk']
" "$S/shared"
check "intake: черновик YAML читается miniyaml" sh -c "'$PY' '$S/intake.py' from-text --text 'smoke тест app.apk' --out '$TMP/draft.yaml' >/dev/null && '$PY' '$S/shared/miniyaml.py' '$TMP/draft.yaml' | grep -q '\"depth\": \"smoke\"'"

# ---------- findings: validate, fingerprint, drafts, report ----------
cp "$F/findings.json" "$RUN/findings.json"
check "validate_findings: валидный файл, предупреждение о немаскированном e-mail" sh -c "'$PY' '$S/validate_findings.py' '$RUN/findings.json' > '$TMP/vf.out'; test \$? = 0 && grep -q 'e-mail без маскирования' '$TMP/vf.out'"
"$PY" -c "import json,sys; d=json.load(open(sys.argv[1])); d['findings'][0]['direction']='responsive'; d['findings'][1].pop('actual'); json.dump(d,open(sys.argv[2],'w'))" "$RUN/findings.json" "$TMP/bad.json"
check "validate_findings: неверное направление и нет actual -> 1" sh -c "'$PY' '$S/validate_findings.py' '$TMP/bad.json' > '$TMP/vf2.out'; test \$? = 1 && grep -q responsive '$TMP/vf2.out' && grep -q 'нет обязательного поля actual' '$TMP/vf2.out'"
"$PY" "$S/fingerprint.py" compute "$RUN/findings.json" >/dev/null && "$PY" "$S/fingerprint.py" dedupe "$RUN/findings.json" >/dev/null
check "fingerprint dedupe: id=btn_share с разной записью элемента -> одна находка, high" pyok "
import json,sys; f=json.load(open(sys.argv[1]))['findings']
assert len(f)==2, len(f); a=[x for x in f if x['check_id']=='a11y.missing-label'][0]
assert a['severity']=='high' and a['merged_ids']==['F-003'] and len(a['fingerprint'])==16
" "$RUN/findings.json"
FP=$("$PY" -c "import json,sys; print([x for x in json.load(open(sys.argv[1]))['findings'] if x['id']=='F-001'][0]['fingerprint'])" "$RUN/findings.json")
sed "s/FPPLACEHOLDER/$FP/" "$F/issues.json" > "$TMP/issues.json"
"$PY" "$S/fingerprint.py" match "$RUN/findings.json" "$TMP/issues.json" --out "$RUN/matches.json" >/dev/null
check "fingerprint match: точное по маркеру и нечёткий кандидат" pyok "
import json,sys; m={r['id']:r for r in json.load(open(sys.argv[1]))}
assert m['F-001']['exact'][0]['number']==5 and any(c['number']==9 for c in m['F-002']['candidates']), m
" "$RUN/matches.json"
"$PY" -c "import json,sys; p=sys.argv[1]; d=json.load(open(p)); d['findings'][0]['logcat_excerpt']=d['findings'][0]['actual']; json.dump(d,open(p,'w'),ensure_ascii=False)" "$RUN/findings.json"
"$PY" "$S/render_draft.py" all "$RUN/findings.json" --run-dir "$RUN" --repo owner/repo > /dev/null
D="$RUN/drafts/owner__repo"
check "render_draft all: TITLE со шкалой репозитория, маркер, без плейсхолдеров, e-mail замаскирован" sh -c "
  f=\$(ls '$D'/01-NEW-*.md | grep -v body | head -1); head -1 \"\$f\" | grep -q '^TITLE: \[P1\] ' && grep -q 'android-qa-audit:fp=$FP' \"\$f\" &&
  ! grep -q '{{' \"\$f\" && ! grep -q 'ivan.petrov@example.com' \"\$f\" && grep -q 'i\*\*\*@e\*\*\*.com' \"\$f\" && grep -q 'API 34' \"\$f\""
check "render_draft: .body.md без TITLE и index.md с командой gh (не выполняется)" sh -c "
  f=\$(ls '$D'/01-NEW-*.body.md); ! head -1 \"\$f\" | grep -q TITLE && grep -q 'gh issue create -R owner/repo' '$D/index.md' && grep -q 'Ничего не опубликовано' '$D/index.md'"
check "render_draft --disclosure none: без упоминания скила и маркера" sh -c "
  '$PY' '$S/render_draft.py' detailed '$RUN/findings.json' --id F-001 --disclosure none --marker none --out '$TMP/dn.md' >/dev/null 2>&1 &&
  ! grep -qi 'android-qa-audit' '$TMP/dn.md' && ! grep -q 'fp=' '$TMP/dn.md'"
"$PY" "$S/build_report.py" report "$RUN" >/dev/null && "$PY" "$S/build_report.py" summary "$RUN" >/dev/null
check "build_report report: шапка с пакетом, статистика, падения, метрики, запреты, публикация" sh -c "
  grep -q '^# QA Android: Example (\`com.example.app\`)' '$RUN/report.md' && grep -q '## Статистика' '$RUN/report.md' &&
  grep -q '## Падения и ANR' '$RUN/report.md' && grep -q '## Метрики' '$RUN/report.md' && grep -q '## Сработавшие запреты' '$RUN/report.md' &&
  grep -q '## Пассивная проверка APK' '$RUN/report.md' && grep -q '## Публикация' '$RUN/report.md' && ! grep -q '{{' '$RUN/report.md'"
check "build_report summary: без таблицы находок, ссылка на report.md" sh -c "! grep -q '## Находки' '$RUN/summary.md' && grep -q 'report.md' '$RUN/summary.md'"
check "build_report publish-table: dry-run и действие issue" sh -c "'$PY' '$S/build_report.py' publish-table '$RUN' | grep -q 'issue (их шаблон'"
check "build_report: нет findings.json -> 2" test "$(rc "$PY" "$S/build_report.py" report "$TMP/empty")" = 2
check "render_draft summary: итоговый черновик без локальных путей" sh -c "'$PY' '$S/render_draft.py' summary --run-dir '$RUN' --repo owner/repo >/dev/null && ! grep -q 'Папка прогона' '$D/summary.md' && grep -q 'android-qa-audit:run=' '$D/summary.md'"

# ---------- journal ----------
check "journal: init/todo/done/status" sh -c "'$PY' '$S/journal.py' init '$RUN' --todo 'Стенды' --todo 'Разведка' >/dev/null && '$PY' '$S/journal.py' done '$RUN' Стенды >/dev/null &&
  '$PY' '$S/journal.py' status '$RUN' | grep -q 'осталось 1'"

# ---------- export_results (report_destinations: folder — только итоговые файлы) ----------
EX="$TMP/out/qa-runs/2026-10-08-com.example.app-2"; mkdir -p "$EX/screenshots" "$EX/apk" "$EX/logs" "$EX/raw" "$EX/recordings" "$EX/drafts"
printf '# report\n' > "$EX/report.md"; printf '# summary\n' > "$EX/summary.md"
printf '{"findings": [{"id": "F-001", "screenshots": ["screenshots/F-001.png", "apk/app.apk", "screenshots/missing.png"]}]}' > "$EX/findings.json"
for f in screenshots/F-001.png screenshots/other.png apk/app.apk apk/SHA256SUMS logs/logcat-emulator-5554.txt raw/ui.xml recordings/r.mp4 journal.md run-config.yaml env.json; do echo "$f" > "$EX/$f"; done
"$PY" "$S/export_results.py" "$EX" --to "$TMP/dest" > "$TMP/ex.out" 2>&1; c=$?
D2="$TMP/dest/2026-10-08-com.example.app-2"
check "export_results: только summary.md, report.md, findings.json и скриншоты из находок; без apk/, logs/, raw/, видео" sh -c "
  test $c = 0 && test -f '$D2/summary.md' && test -f '$D2/report.md' && test -f '$D2/findings.json' && test -f '$D2/screenshots/F-001.png' &&
  test ! -e '$D2/screenshots/other.png' && test ! -e '$D2/apk' && test ! -e '$D2/logs' && test ! -e '$D2/raw' && test ! -e '$D2/recordings' &&
  test ! -e '$D2/journal.md' && test ! -e '$D2/run-config.yaml' && grep -q 'apk/app.apk' '$TMP/ex.out' && test \$(find '$D2' -type f | wc -l) -eq 4"
check "export_results: повтор — то же содержимое -> 0; изменённый файл -> 1 без записи; --overwrite -> 0" sh -c "
  '$PY' '$S/export_results.py' '$EX' --to '$TMP/dest' >/dev/null && echo changed > '$D2/report.md' &&
  test \$('$PY' '$S/export_results.py' '$EX' --to '$TMP/dest' >/dev/null 2>&1; echo \$?) = 1 && grep -q changed '$D2/report.md' &&
  '$PY' '$S/export_results.py' '$EX' --to '$TMP/dest' --overwrite >/dev/null && cmp -s '$EX/report.md' '$D2/report.md'"
check "export_results: --screenshots all/none; нет summary.md -> 2; папка назначения внутри прогона -> 2" sh -c "
  '$PY' '$S/export_results.py' '$EX' --to '$TMP/dest-all' --screenshots all >/dev/null && test -f '$TMP/dest-all/2026-10-08-com.example.app-2/screenshots/other.png' &&
  '$PY' '$S/export_results.py' '$EX' --to '$TMP/dest-none' --screenshots none >/dev/null && test ! -e '$TMP/dest-none/2026-10-08-com.example.app-2/screenshots' &&
  test \$('$PY' '$S/export_results.py' '$EX' --to '$EX/raw' >/dev/null 2>&1; echo \$?) = 2 &&
  mkdir -p '$TMP/nosum' && test \$('$PY' '$S/export_results.py' '$TMP/nosum' --to '$TMP/dest' >/dev/null 2>&1; echo \$?) = 2"

# ---------- gitignore_helper (shared/qa_gitignore.py, Android defaults) ----------
GH="$S/gitignore_helper.py"
if command -v git >/dev/null 2>&1; then
  mkdir -p "$TMP/plain" "$TMP/repo/sub/qa-runs" "$TMP/neg"
  check "gitignore: вне git -> 0" test "$(rc "$PY" "$GH" check "$TMP/plain")" = 0
  git -C "$TMP/repo" init -q
  check "gitignore: в репозитории, не игнорируется -> 1" test "$(rc "$PY" "$GH" check "$TMP/repo/sub")" = 1
  check "gitignore check --json: 7 шаблонов по умолчанию, qa-runs/ привязан к подпапке" sh -c "'$PY' '$GH' check '$TMP/repo/sub' --json | '$PY' -c \"
import json,sys; d=json.load(sys.stdin); p={x['pattern']:x for x in d['patterns']}
assert list(p)==['qa-runs/','*.apk','*.aab','*.apks','*.xapk','*.keystore','*.jks'] and p['qa-runs/']['line']=='/sub/qa-runs/' and p['*.apk']['line']=='*.apk'
assert p['qa-runs/']['kind']=='results' and p['*.jks']['kind']=='artifacts'\""
  check "gitignore apply --mode gitignore: строки добавлены, повтор не дублирует, check -> 0" sh -c "
    '$PY' '$GH' apply '$TMP/repo/sub' --mode gitignore >/dev/null && '$PY' '$GH' apply '$TMP/repo/sub' --mode gitignore >/dev/null &&
    test \$(grep -c '^/sub/qa-runs/\$' '$TMP/repo/.gitignore') = 1 && test \$(grep -c '^\*\.apk\$' '$TMP/repo/.gitignore') = 1 &&
    grep -q '^\*\.keystore\$' '$TMP/repo/.gitignore' && grep -q 'android-qa-audit' '$TMP/repo/.gitignore' && '$PY' '$GH' check '$TMP/repo/sub' >/dev/null"
  git -C "$TMP/neg" init -q
  check "gitignore --pattern qa-runs/ --mode exclude: только qa-runs/, только .git/info/exclude" sh -c "
    '$PY' '$GH' apply '$TMP/neg' --mode exclude --pattern qa-runs/ >/dev/null && grep -q '^/qa-runs/\$' '$TMP/neg/.git/info/exclude' &&
    ! grep -q apk '$TMP/neg/.git/info/exclude' && test ! -e '$TMP/neg/.gitignore'"
  check "gitignore keep: ответ запомнен, check -> 0" sh -c "'$PY' '$GH' apply '$TMP/neg' --mode keep >/dev/null && grep -q '^keep ' '$TMP/neg/qa-runs/.gitignore-decision' && '$PY' '$GH' check '$TMP/neg' >/dev/null"
  mkdir -p "$TMP/tr"; git -C "$TMP/tr" init -q; echo x > "$TMP/tr/old.apk"; git -C "$TMP/tr" add -A
  git -C "$TMP/tr" -c user.name=t -c user.email=t@example.com commit -qm init
  check "gitignore: APK уже в индексе — подсказка git rm --cached, файл не трогается" sh -c "
    '$PY' '$GH' apply '$TMP/tr' --mode gitignore > '$TMP/tr.out' 2>&1; grep -q 'rm -r --cached' '$TMP/tr.out' && test -n \"\$(git -C '$TMP/tr' ls-files old.apk)\""
  check "gitignore: недопустимый шаблон -> 2" test "$(rc "$PY" "$GH" check "$TMP/repo" --pattern '../x')" = 2
  # ensure — по умолчанию (без явного разрешения) до создания папки прогона
  mkdir -p "$TMP/en1"; git -C "$TMP/en1" init -q
  "$PY" "$GH" ensure "$TMP/en1/proj/out" > "$TMP/en1.out" 2>&1; c=$?
  check "ensure по умолчанию: OUTPUT_ROOT ещё нет — qa-runs/ и *.apk … *.jks в .gitignore репозитория, папки не созданы" sh -c "
    test $c = 0 && grep -q '^/proj/out/qa-runs/\$' '$TMP/en1/.gitignore' && grep -q '^\*\.xapk\$' '$TMP/en1/.gitignore' && grep -q '^\*\.jks\$' '$TMP/en1/.gitignore' &&
    test ! -e '$TMP/en1/proj' && '$PY' '$GH' ensure '$TMP/en1/proj/out' >/dev/null && test \$(grep -c 'qa-runs' '$TMP/en1/.gitignore') = 1 &&
    git -C '$TMP/en1' check-ignore -q --no-index proj/out/qa-runs/2026-10-08-com.example.app/report.md"
  mkdir -p "$TMP/en2"; git -C "$TMP/en2" init -q
  check "ensure --allow-commit-results: qa-runs/ не трогается, сборки и ключи всё равно игнорируются" sh -c "
    '$PY' '$GH' ensure '$TMP/en2' --allow-commit-results >/dev/null && ! grep -q qa-runs '$TMP/en2/.gitignore' && grep -q '^\*\.apk\$' '$TMP/en2/.gitignore' && grep -q '^\*\.keystore\$' '$TMP/en2/.gitignore'"
  mkdir -p "$TMP/en3"; git -C "$TMP/en3" init -q; printf 'git:\n  allow_commit_results: true\n  allow_commit_apk: true\n' > "$TMP/en3-rc.yaml"
  check "ensure: разрешение из run-config (git.*) и из текста запроса — .gitignore не создаётся" sh -c "
    '$PY' '$GH' ensure '$TMP/en3' --config '$TMP/en3-rc.yaml' >/dev/null && test ! -e '$TMP/en3/.gitignore' &&
    '$PY' '$GH' ensure '$TMP/en3' --text 'коммить результаты и APK' >/dev/null && test ! -e '$TMP/en3/.gitignore'"
  mkdir -p "$TMP/en4/qa-runs/r" "$TMP/en4/app"; git -C "$TMP/en4" init -q; echo x > "$TMP/en4/qa-runs/r/report.md"; echo y > "$TMP/en4/app/fixture.apk"
  git -C "$TMP/en4" add -A && git -C "$TMP/en4" -c user.name=t -c user.email=t@example.com commit -qm init
  "$PY" "$GH" ensure "$TMP/en4" > "$TMP/en4.out" 2>&1; c=$?
  check "ensure: qa-runs/ уже в индексе -> код 1, вопрос и команда, файлы не удалены; *.apk проекта — без вопроса" sh -c "
    test $c = 1 && grep -q 'rm -r --cached -- \"qa-runs\"' '$TMP/en4.out' && grep -q 'untrack' '$TMP/en4.out' && grep -q 'файлы проекта' '$TMP/en4.out' &&
    test -n \"\$(git -C '$TMP/en4' ls-files qa-runs)\" && test -n \"\$(git -C '$TMP/en4' ls-files app/fixture.apk)\""
  check "untrack без --yes — только план; с --yes — убрано из индекса, файлы на диске, *.apk проекта не тронут" sh -c "
    '$PY' '$GH' untrack '$TMP/en4' | grep -q 'План' && test -n \"\$(git -C '$TMP/en4' ls-files qa-runs)\" &&
    '$PY' '$GH' untrack '$TMP/en4' --yes >/dev/null && test -z \"\$(git -C '$TMP/en4' ls-files qa-runs)\" && test -f '$TMP/en4/qa-runs/r/report.md' &&
    test -n \"\$(git -C '$TMP/en4' ls-files app/fixture.apk)\" && '$PY' '$GH' ensure '$TMP/en4' >/dev/null"
  mkdir -p "$TMP/en5"; git -C "$TMP/en5" init -q; printf '!qa-runs/\n' > "$TMP/en5/.gitignore"
  check "ensure --mode exclude: правило «!» в .gitignore перекрывает -> код 3; в .gitignore наша строка идёт после «!» и действует" sh -c "
    test \$('$PY' '$GH' ensure '$TMP/en5' --mode exclude >/dev/null 2>&1; echo \$?) = 3 && '$PY' '$GH' ensure '$TMP/en5' >/dev/null &&
    git -C '$TMP/en5' check-ignore -q --no-index qa-runs/x"
  check "ensure вне git -> 0, ничего не создано" sh -c "'$PY' '$GH' ensure '$TMP/plain/x' >/dev/null && test ! -e '$TMP/plain/x' && test ! -e '$TMP/plain/.gitignore'"
else
  echo "SKIP gitignore_helper: нет git"
fi

# ---------- documentation: every command example is accepted by argparse (--help only, nothing runs) ----------
check "примеры команд в SKILL.md, README, INSTALL и references/*.md принимаются скриптами (подкоманды и --опции)" \
  "$PY" "$HERE/helpers/doc_commands.py" "$HERE/.." --python "$PY"

# ---------- masking, universality, SKILL.md ----------
check "masking: e-mail, токены, URL-параметры, телефоны; PID и время в logcat не трогаются" pyok "
import sys; sys.path.insert(0, sys.argv[1]); from masking import mask
t=mask('10-08 12:34:56.789 12345 12399 E X: a.b@example.com +7 912 345-67-89 key=Abcdef0123456789Abcdef0123456789XYZ0 https://h.example.com/x?code=SECRET1&p=2 Authorization: Bearer abcdefghij')
assert '12345 12399' in t and '12:34:56.789' in t and 'a***@e***.com' in t and '***89' in t
assert 'Abcdef0123456789Abcdef' not in t and 'code=***' in t and 'SECRET1' not in t and 'abcdefghij' not in t, t
x=mask('<node password=\"false\" text=\"a\"/> password=\"S3cretValue\"'); assert 'password=\"false\"' in x and 'S3cretValue' not in x, x
" "$S"
SK="$HERE/.."
check "универсальность: в скиле нет личных путей и конкретных приложений" sh -c "! grep -rIl --exclude-dir=__pycache__ -E '/Users/[a-z]+|C:\\\\Users\\\\[A-Za-z]+|TgStat|com\\.versus|Versus' '$SK' | grep -v -E 'tests/unit.sh\$'"
check "SKILL.md: frontmatter, ≤ 300 строк, description ≤ 1024 символов" pyok "
import re,sys; t=open(sys.argv[1],encoding='utf-8').read(); assert t.startswith('---\nname: android-qa-audit\n')
fm=t.split('\n---',1)[0]; d=re.search(r'description: >\n((?:  .*\n)+)', fm+'\n').group(1); d=' '.join(x.strip() for x in d.splitlines())
assert len(d)<=1024, len(d); assert t.count('\n')<=300, t.count('\n')
assert '/android-qa-audit' in d and 'site-qa-audit' in d
" "$SK/SKILL.md"

echo "unit: PASS $pass, FAIL $fail"; [ $fail -eq 0 ]
