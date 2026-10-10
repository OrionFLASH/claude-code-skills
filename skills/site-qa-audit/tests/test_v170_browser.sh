#!/usr/bin/env bash
# Browser tests of 1.7.0 — node/clip.js (references/clips.md). Local fixtures only (clip-demo.html, clip-login.html,
# clip-guest.html) served by `python3 -m http.server` on 127.0.0.1; the «user's browser» for CDP is a headless Chromium
# (tests/helpers/cdp_browser.mjs). Needs node + Playwright (scripts/node) + Chromium; the video checks need ffmpeg and
# ffprobe — otherwise SKIP. QA_KEEP_CLIP=<dir> — copy the demo clip and its frame sheet there (to look at them).
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; S="$HERE/../scripts"; N="$S/node"
if command -v python3 >/dev/null 2>&1; then PY="${PY:-python3}"; else PY="${PY:-python}"; fi
export PYTHONDONTWRITEBYTECODE=1 SITE_QA_HEADLESS="${SITE_QA_HEADLESS:-1}"
TMP="$(mktemp -d)"
pass=0; fail=0; skip=0
ok(){ echo "PASS $1"; pass=$((pass+1)); }; bad(){ echo "FAIL $1"; fail=$((fail+1)); }; sk(){ echo "SKIP $1"; skip=$((skip+1)); }
check(){ local name="$1"; shift; if "$@"; then ok "$name"; else bad "$name"; fi; }
finish(){ echo "stream v1.7.0 browser: PASS $pass, FAIL $fail, SKIP $skip"; [ $fail -eq 0 ]; exit $?; }

if ! command -v node >/dev/null 2>&1 || [ ! -d "$N/node_modules/playwright" ]; then sk "clip.js: нет node или playwright (cd scripts/node && npm install)"; finish; fi
if ! (cd "$N" && node -e "const fs=require('fs');const p=require('playwright').chromium.executablePath();process.exit(p&&fs.existsSync(p)?0:1)") 2>/dev/null; then
  sk "clip.js: нет Chromium (npx playwright install chromium)"; finish
fi
HAVE_FF=0; command -v ffmpeg >/dev/null 2>&1 && command -v ffprobe >/dev/null 2>&1 && HAVE_FF=1
[ $HAVE_FF -eq 1 ] || { sk "clip.js: нет ffmpeg/ffprobe — видео-проверки пропущены (brew install ffmpeg)"; finish; }

PORT="$("$PY" -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()')"
CDP_PORT="$("$PY" -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()')"
"$PY" -m http.server "$PORT" --bind 127.0.0.1 -d "$HERE/fixtures" >/dev/null 2>&1 &
SRV=$!; disown $SRV 2>/dev/null || true
CDPPID=""
trap 'kill $SRV 2>/dev/null; [ -n "$CDPPID" ] && kill $CDPPID 2>/dev/null; rm -rf "$TMP"' EXIT
for _ in 1 2 3 4 5 6 7 8 9 10; do "$PY" -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:$PORT/clip-demo.html')" 2>/dev/null && break; sleep 0.3; done
B="http://127.0.0.1:$PORT"

R="$TMP/run"; mkdir -p "$R/setup"
printf 'version: 1\nsite:\n  allowed_domains:\n    - 127.0.0.1\n  start_urls:\n    - %s/clip-demo.html\n' "$B" > "$R/run-config.yaml"
"$PY" "$S/url_guard.py" export --config "$R/run-config.yaml" --out "$R/rules.json" >/dev/null
echo '{"run": {}, "findings": [{"id": "F-004", "title": "Меню закрывается само через 0,6 с"}]}' > "$R/findings.json"
cat > "$R/setup/menu.js" <<'EOF'
module.exports = async ({ guarded, clip }) => {
  await guarded.click('#menu-btn');
  await clip.wait(1200);
};
EOF
cat > "$R/setup/login.js" <<'EOF'
module.exports = async ({ guarded, clip }) => { await guarded.click('#login'); await clip.wait(1500); };
EOF

# yellow (#FFD60A) and purple (#BF5AF2) pixels of a frame: the frames and the caption plate are in the video
pixels(){ ffmpeg -v error -ss "$2" -i "$1" -frames:v 1 -f rawvideo -pix_fmt rgb24 - | "$PY" -c "
import sys
d = sys.stdin.buffer.read(); y = p = dark = 0
for i in range(0, len(d) - 2, 3):
    r, g, b = d[i], d[i + 1], d[i + 2]
    if r > 200 and g > 165 and b < 90: y += 1
    elif r > 150 and g < 130 and b > 190: p += 1
    elif r < 40 and g < 40 and b < 40: dark += 1
print(y, p, dark)"; }

# ---------- 1. launch: click + highlight + caption + mask ----------
( cd "$N" && node clip.js --url "$B/clip-demo.html" --out "$R/clips/F-004-menu.mp4" --rules "$R/rules.json" --log "$R/logs/blocked.jsonl" \
    --setup "$R/setup/menu.js" --caption "Меню закрывается само через 0,6 с" "#menu|Меню|error" "#menu-btn|Нажатие|note" \
    --mask ".email" --seconds 6 --finding F-004 --run-dir "$R" ) > "$TMP/o1.json"; c=$?
check "clip.js: код 0, recorder screencast, шаг «Нажать «Меню»», JSON одной строкой" sh -c "
  test $c = 0 && test \$(wc -l < '$TMP/o1.json') = 1 &&
  '$PY' -c \"import json,sys; d=json.load(open(sys.argv[1])); assert d['ok'] and d['recorder']=='screencast' and not d['cdp'] and d['steps']==['Нажать «Меню»'] and not d['warnings'], d\" '$TMP/o1.json'"
check "clip.js: mp4 ≤ 3 МБ, H.264, без звука (ffprobe), длительность ≤ --seconds" sh -c "
  test -s '$R/clips/F-004-menu.mp4' && test \$(wc -c < '$R/clips/F-004-menu.mp4') -le 3145728 &&
  test \"\$(ffprobe -v error -select_streams v -show_entries stream=codec_name -of csv=p=0 '$R/clips/F-004-menu.mp4')\" = h264 &&
  test -z \"\$(ffprobe -v error -select_streams a -show_entries stream=index -of csv=p=0 '$R/clips/F-004-menu.mp4')\" &&
  '$PY' -c \"import sys; d=float(sys.argv[1]); assert 1.5 <= d <= 6.5, d\" \$(ffprobe -v error -show_entries format=duration -of csv=p=0 '$R/clips/F-004-menu.mp4')"
check "clip.js: лента кадров, постер, GIF; запись в findings.json (viewed false, caption, steps, sheet)" sh -c "
  test -s '$R/clips/F-004-menu-sheet.png' && test -s '$R/clips/F-004-menu-poster.png' && test -s '$R/clips/F-004-menu.gif' &&
  '$PY' -c \"import json,sys; c=json.load(open(sys.argv[1]))['findings'][0]['clips'][0]
assert c['file']=='clips/F-004-menu.mp4' and c['sheet']=='clips/F-004-menu-sheet.png' and c['viewed'] is False and c['audio'] is False
assert c['caption']=='Меню закрывается само через 0,6 с' and c['steps']==['Нажать «Меню»'], c\" '$R/findings.json'"
read -r Y P D <<< "$(pixels "$R/clips/F-004-menu.mp4" 1.0)"
check "clip.js: на кадре видны рамки и подпись (жёлтые $Y, фиолетовые $P, тёмная плашка $D пикселей)" sh -c "test $Y -ge 15 && test $P -ge 5 && test $D -ge 200"
if [ -n "${QA_KEEP_CLIP:-}" ]; then mkdir -p "$QA_KEEP_CLIP" && cp "$R/clips/F-004-menu"* "$QA_KEEP_CLIP/" && echo "кадры: $QA_KEEP_CLIP/F-004-menu-sheet.png"; fi
check "clip.js → clips.py viewed после ленты кадров; check — код 0" sh -c "
  '$PY' '$S/clips.py' viewed '$R' --id F-004 >/dev/null && '$PY' '$S/clips.py' check '$R' >/dev/null"

# ---------- 2. recordVideo (fallback) ----------
( cd "$N" && SITE_QA_CLIP_MODE=video node clip.js --url "$B/clip-demo.html" --out "$R/clips/F-004-video.mp4" --rules "$R/rules.json" \
    --setup "$R/setup/menu.js" --caption "recordVideo" "#menu|Меню|error" --seconds 6 ) > "$TMP/o2.json"; c=$?
check "clip.js SITE_QA_CLIP_MODE=video: recordVideo, обрезка до шагов (--start), mp4 без звука" sh -c "
  test $c = 0 && '$PY' -c \"import json,sys; d=json.load(open(sys.argv[1])); assert d['recorder']=='recordVideo' and d['start']>0 and d['clip']['seconds']<=6.5, d\" '$TMP/o2.json' &&
  test -z \"\$(ffprobe -v error -select_streams a -show_entries stream=index -of csv=p=0 '$R/clips/F-004-video.mp4')\""

# ---------- 3. CDP: the user's tab is recorded as it is ----------
node "$HERE/helpers/cdp_browser.mjs" "$CDP_PORT" > "$TMP/cdp.log" 2>&1 &
CDPPID=$!; disown $CDPPID 2>/dev/null || true
for _ in $(seq 1 30); do grep -q ready "$TMP/cdp.log" 2>/dev/null && break; sleep 0.3; done
cat > "$TMP/user_tab.js" <<'EOF'
const { chromium } = require(process.argv[2] + '/node_modules/playwright');
(async () => {
  const b = await chromium.connectOverCDP('http://127.0.0.1:' + process.argv[3]);
  const ctx = b.contexts()[0];
  let p = ctx.pages().find(x => x.url().includes('clip-demo'));
  if (process.argv[4] === 'open') {
    p = p || ctx.pages()[0] || await ctx.newPage();
    await p.goto(process.argv[5] + '/clip-demo.html#user');
    await p.evaluate(() => { localStorage.setItem('user-key', '1'); window.__userMarker = 42; });
  } else {
    console.log(JSON.stringify({ pages: ctx.pages().length, ...(await p.evaluate(() => ({ url: location.href, marker: window.__userMarker,
      ls: localStorage.getItem('user-key'), overlay: !!document.querySelector('qa-clip-overlay'), mask: !!document.querySelector('style[data-qa-clip-mask]'),
      api: typeof window.__qaClip, blur: getComputedStyle(document.querySelector('.email')).filter }))) }));
  }
  await b.close();
})().catch(e => { console.error(e.message); process.exit(1); });
EOF
node "$TMP/user_tab.js" "$N" "$CDP_PORT" open "$B"
( cd "$N" && node clip.js --cdp "http://127.0.0.1:$CDP_PORT" --page-match clip-demo --out "$R/clips/F-004-cdp.mp4" --rules "$R/rules.json" \
    --setup "$R/setup/menu.js" --caption "Вкладка пользователя" "#menu|Меню|error" --mask ".email" --seconds 6 ) > "$TMP/o3.json"; c=$?
node "$TMP/user_tab.js" "$N" "$CDP_PORT" check > "$TMP/tab.json"
check "clip.js --cdp: screencast вкладки пользователя, ролик записан" sh -c "
  test $c = 0 && '$PY' -c \"import json,sys; d=json.load(open(sys.argv[1])); assert d['cdp'] and d['recorder']=='screencast' and d['clip']['bytes']>0, d\" '$TMP/o3.json'"
check "clip.js --cdp: вкладка не перезагружена и не уведена (адрес, состояние JS, localStorage), разметка и маска удалены, новых вкладок нет" \
  "$PY" -c "import json,sys; t=json.load(open(sys.argv[1])); assert t['url'].endswith('/clip-demo.html#user') and t['marker']==42 and t['ls']=='1' and not t['overlay'] and not t['mask'] and t['api']=='undefined' and t['blur']=='none' and t['pages']==1, t" "$TMP/tab.json"

# ---------- 4. login / payment: recording forbidden ----------
( cd "$N" && node clip.js --url "$B/clip-login.html" --out "$R/clips/F-009-login.mp4" --rules "$R/rules.json" ) > "$TMP/o4.json"; c=$?
check "clip.js: экран с полем пароля — код 3, файл не создан" sh -c "test $c = 3 && grep -q 'поле пароля' '$TMP/o4.json' && test ! -e '$R/clips/F-009-login.mp4'"
( cd "$N" && node clip.js --url "$B/clip-guest.html" --out "$R/clips/F-010-guest.mp4" --rules "$R/rules.json" --setup "$R/setup/login.js" ) > "$TMP/o5.json"; c=$?
check "clip.js: гостевой экран → диалог с паролем во время записи — остановка, код 3, ролик удалён" sh -c "
  test $c = 3 && grep -q 'запись остановлена' '$TMP/o5.json' && ! ls '$R/clips/' | grep -q F-010"
( cd "$N" && node clip.js --url "$B/account/login" --out "$R/clips/F-011.mp4" --rules "$R/rules.json" ) > "$TMP/o6.json"; c=$?
check "clip.js: адрес /login — код 3 до открытия страницы" sh -c "test $c = 3 && grep -q 'входа или оплаты' '$TMP/o6.json'"
( cd "$N" && node clip.js --url "$B/checkout/pay" --out "$R/clips/F-012.mp4" --rules "$R/rules.json" ) >/dev/null; c=$?
check "clip.js: адрес /checkout — код 3" test $c = 3

# ---------- 5. guard unavailable, read-only, input errors ----------
( cd "$N" && node clip.js --url "$B/clip-demo.html" --out "$R/clips/F-013.mp4" --rules "$R/missing-rules.json" ) > "$TMP/o7.json"; c=$?
check "clip.js: rules.json не прочитан — код 4 (fail closed), совет check_env, браузер не открывался" sh -c "test $c = 4 && grep -q 'check_env' '$TMP/o7.json' && test ! -e '$R/clips/F-013.mp4'"
( cd "$N" && node clip.js --url "$B/clip-demo.html" --out "$R/clips/F-014-ro.mp4" --rules "$R/rules.json" --setup "$R/setup/menu.js" --read-only --seconds 4 ) > "$TMP/o8.json"; c=$?
check "clip.js --read-only: клик не выполнен (guard read-only) — предупреждение, код 1, ролик наблюдения сохранён" sh -c "
  test $c = 1 && '$PY' -c \"import json,sys; d=json.load(open(sys.argv[1])); assert d['denied'][0]['rule']=='read-only' and d['steps']==[] and d['ok'], d\" '$TMP/o8.json'"
( cd "$N" && node clip.js --out "$R/clips/x.mp4" ) >/dev/null 2>&1; c1=$?
( cd "$N" && node clip.js --url "$B/clip-demo.html" --out "$R/clips/bad name.mp4" ) >/dev/null 2>&1; c2=$?
( cd "$N" && node clip.js --url "$B/clip-demo.html" --out "$R/clips/F-1.mp4" --kind wrong ) >/dev/null 2>&1; c3=$?
check "clip.js: ошибки входа (нет --url/--cdp, плохое имя, --kind) — код 2" sh -c "test $c1 = 2 && test $c2 = 2 && test $c3 = 2"

# ---------- 6. no ffmpeg: saved as is with a warning ----------
mkdir -p "$TMP/bin"
ln -sf "$(command -v node)" "$TMP/bin/node"; ln -sf "$(command -v "$PY")" "$TMP/bin/python3"
( cd "$N" && PATH="$TMP/bin:/usr/bin:/bin" QA_FFMPEG= QA_FFPROBE= PLAYWRIGHT_BROWSERS_PATH="${PLAYWRIGHT_BROWSERS_PATH:-}" \
    "$TMP/bin/node" clip.js --url "$B/clip-demo.html" --out "$R/clips/F-015-raw.mp4" --rules "$R/rules.json" --setup "$R/setup/menu.js" --seconds 4 ) > "$TMP/o9.json" 2>/dev/null; c=$?
if command -v ffmpeg | grep -q '^/usr/bin/\|^/bin/'; then sk "clip.js без ffmpeg: ffmpeg в /usr/bin — не убрать из PATH"
else
  check "clip.js без ffmpeg: код 1, ролик сохранён как есть (webm), предупреждение про ffmpeg" sh -c "
    test $c = 1 && test -s '$R/clips/F-015-raw.webm' && grep -q 'ffmpeg не найден' '$TMP/o9.json'"
fi

finish
