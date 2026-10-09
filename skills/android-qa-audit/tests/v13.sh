# 1.3.0 tests — sourced by tests/unit.sh after v12.sh (uses its PY, S, F, TMP, H, R12, D12, check, rc, pyok, fake adb/node).
# PSS chart (SVG) and sparkline in the report, contact sheet of screenshots, job stop by the stop file (Windows behaviour),
# shared test helpers (shared/tests → tests/helpers/shared/, doc_commands --wrapper/--nested).

# ---------- shared test helpers ----------
check "общие тестовые помощники tests/helpers/shared/ совпадают с shared/tests (в репозитории; установленный скил — пропуск)" sh -c "
  R='$HERE/../../../shared/tests'; test -d \"\$R\" || exit 0
  for f in doc_commands.py doc_zsh.py; do cmp -s \"\$R/\$f\" '$H/shared/'\$f || { echo \"устарел \$f: tools/validate.sh --fix\"; exit 1; }; done"
FS="$TMP/fake-doc-skill"; mkdir -p "$FS/scripts"
printf 'import argparse\nap = argparse.ArgumentParser(); sub = ap.add_subparsers(dest="cmd")\nr = sub.add_parser("run"); r.add_argument("--ok", action="store_true")\nj = sub.add_parser("job"); j.add_argument("action"); j.add_argument("--name")\nap.parse_args()\n' > "$FS/scripts/tool.py"
printf -- '---\nname: x\n---\n`qa emulator-5554 run --ok`\n`qa - run --bad`\n`tool.py job start --name x -- run --bad2`\n`qa <serial|-> run --skipped`\n' > "$FS/SKILL.md"
check "doc_commands --wrapper/--nested: обёртка qa и часть после «--» проверяются как команды скрипта" sh -c "
  out=\$('$PY' '$H/shared/doc_commands.py' '$FS' --python '$PY' --wrapper qa=tool --nested tool:job); test \$? = 1 &&
  echo \"\$out\" | grep -q 'tool.py run не принимает --bad ' && echo \"\$out\" | grep -q 'tool.py run не принимает --bad2' &&
  ! echo \"\$out\" | grep -q -- '--ok' && ! echo \"\$out\" | grep -q -- '--skipped' &&
  out2=\$('$PY' '$H/shared/doc_commands.py' '$FS' --python '$PY'); test \$? = 1 && echo \"\$out2\" | grep -q 'tool.py job не принимает --bad2' &&
  ! echo \"\$out2\" | grep -q -- '--bad '"

# ---------- PSS chart and sparkline ----------
check "build_report: PSS картинкой — SVG на каждый soak с точками (charts/), ссылка в отчёте, спарклайн в таблице, события на графике" sh -c "
  '$PY' '$S/build_report.py' report '$R12' >/dev/null && grep -q '^!\[PSS: ok · emulator-5554' '$R12/report.md' &&
  grep -q '(charts/soak-ok-emulator-5554-pss.svg)' '$R12/report.md' && test -f '$R12/charts/soak-lost-emulator-5554-pss.svg' &&
  grep -q 'service-lost' '$R12/charts/soak-lost-emulator-5554-pss.svg' && grep -q '| 100.0–100.0[^|]* ▁▁' '$R12/report.md' &&
  '$PY' -c \"import sys,xml.etree.ElementTree as E; r=E.parse(sys.argv[1]).getroot(); assert r.tag.endswith('svg') and r.findall('{http://www.w3.org/2000/svg}path'), r\" '$R12/charts/soak-ok-emulator-5554-pss.svg' &&
  ! ls '$R12/charts/' | grep -q 'soak-inv-'"
check "build_report --out в другой папке: графики рядом с отчётом, ссылка относительная" sh -c "
  '$PY' '$S/build_report.py' report '$R12' --out '$TMP/rep13/r.md' >/dev/null && test -f '$TMP/rep13/charts/soak-ok-emulator-5554-pss.svg' &&
  grep -q '(charts/soak-ok-emulator-5554-pss.svg)' '$TMP/rep13/r.md'"
check "PSS: точки из raw/ прогона, если папку перенесли; спарклайн, деления осей, экран выкл. и событие в SVG" pyok "
import json, sys; from pathlib import Path; sys.path.insert(0, sys.argv[1]); import build_report as b
d = Path(sys.argv[2]) / 'moved'; (d / 'raw').mkdir(parents=True, exist_ok=True)
(d / 'raw' / 'soak-m-x.jsonl').write_text('\n'.join(json.dumps({'t_s': i * 60, 'pss_kb': (100 + i) * 1024}) for i in range(5)))
class R: dir = d
pts = b.soak_samples(R, {'file': '/nowhere/raw/soak-m-x.jsonl'}); assert pts == [(0.0, 100.0), (1.0, 101.0), (2.0, 102.0), (3.0, 103.0), (4.0, 104.0)], pts
assert b.sparkline([1, 2, 3, 4, 5, 6, 7, 8]) == '▁▂▃▄▅▆▇█' and b.sparkline([5, 5, 5]) == '▁▁▁' and b.sparkline([1]) == ''
assert b.nice_ticks(0, 60, 6) == (0, 60, 10) and b.nice_ticks(93, 115, 4)[2] == 10
svg = b.pss_svg(pts, [{'t_s': 60, 'event': 'screen-off'}, {'t_s': 120, 'event': 'screen-on'}, {'t_s': 180, 'event': 'process-died'}], 'PSS: m & <x>')
assert 'экран выключен 1.0–2.0 мин' in svg and 'process-died 3.0 мин' in svg and 'PSS: m &amp; &lt;x&gt;' in svg and 'prefers-color-scheme: dark' in svg
" "$S" "$TMP"

# ---------- contact sheet ----------
SH="$TMP/sheet13"; mkdir -p "$SH/in"
"$PY" -c "
import struct, sys, zlib
def png(p, w, h):
    c = lambda t, d: struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d) & 0xFFFFFFFF)
    open(p, 'wb').write(b'\x89PNG\r\n\x1a\n' + c(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0)) + c(b'IDAT', zlib.compress(b'\0' * (3 * w + 1) * h)) + c(b'IEND', b''))
for i in (5, 10, 15): png(sys.argv[1] + '/soak-a-t%dm.png' % i, 108, 240)
open(sys.argv[1] + '/note.txt', 'w').write('x')
open(sys.argv[1] + '/p.jpg', 'wb').write(b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xc0\x00\x11\x08\x09\x60\x04\x38\x03\x01\x22\x00')
" "$SH/in"
check "sheet: снимки папки по естественному порядку, листы по --per, HTML-лист с относительными ссылками, размеры PNG/JPEG" sh -c "
  '$PY' '$S/annotate_android.py' sheet --dir '$SH/in' --glob 'soak-*.png' --out '$SH/out/c.png' --per 2 > '$SH/s1.out' && '$PY' -c \"
import json, sys; d = json.load(open(sys.argv[1])); assert d['ok'] and d['count'] == 3 and len(d['sheets']) == 2 and d['sheets'][0].endswith('c-1.png'), d
assert 'Read' in d['must_view']; h = open(d['html'], encoding='utf-8').read()
assert h.index('t5m') < h.index('t10m') < h.index('t15m') and 'src=\\\"../in/soak-a-t5m.png\\\"' in h and '108×240' in h, h
sys.path.insert(0, sys.argv[2]); import annotate_android as a; assert a.image_size(sys.argv[3]) == (1080, 2400), a.image_size(sys.argv[3])
\" '$SH/s1.out' '$S' '$SH/in/p.jpg'"
check "sheet --soak: скриншоты из сводки soak (в т.ч. перенесённой папки прогона); нет node -> код 4, HTML всё равно собран; --html-only -> 0" sh -c "
  '$PY' '$S/annotate_android.py' sheet --soak '$R12/raw/soak-ok-emulator-5554.json' --out '$SH/soak.png' > '$SH/s2.out' && '$PY' -c \"
import json, sys; d = json.load(open(sys.argv[1])); s = json.load(open(sys.argv[2])); assert d['ok'] and d['count'] == len(s['screenshots']) > 0, (d, s['screenshots'])\" '$SH/s2.out' '$R12/raw/soak-ok-emulator-5554.json' &&
  ANDROID_QA_NODE_MODULES='$TMP/none' '$PY' '$S/annotate_android.py' sheet '$SH/in/soak-a-t5m.png' --out '$SH/n.png' > '$SH/s3.out'; test \$? = 4 &&
  grep -q 'не поддерживается' '$SH/s3.out' && grep -q 'n.html' '$SH/s3.out' && test -f '$SH/n.html' &&
  ANDROID_QA_NODE_MODULES='$TMP/none' '$PY' '$S/annotate_android.py' sheet '$SH/in/soak-a-t5m.png' --out '$SH/h.png' --html-only >/dev/null && test -f '$SH/h.html' && test ! -f '$SH/h.sheet.json'"
check "sheet: ошибки — нет снимков (2), не .png (2), сбой sheet.js (5)" sh -c "
  test \$('$PY' '$S/annotate_android.py' sheet --dir '$SH/in' --glob '*.gif' --out '$SH/e.png' >/dev/null 2>&1; echo \$?) = 2 &&
  test \$('$PY' '$S/annotate_android.py' sheet '$SH/in/soak-a-t5m.png' --out '$SH/e.jpg' >/dev/null 2>&1; echo \$?) = 2 &&
  test \$(FAKE_NODE_BAD=1 '$PY' '$S/annotate_android.py' sheet '$SH/in/soak-a-t5m.png' --out '$SH/e.png' >/dev/null 2>&1; echo \$?) = 5"

# ---------- job stop by the stop file (Windows behaviour: ANDROID_QA_JOB_STOP=file) ----------
check "job stop (как на Windows, файл-запрос): soak сам дописывает сводку stopped, задача stopped, без сигнала" sh -c "
  unset FAKE_ADB_UI_FLOW; export ANDROID_QA_JOB_STOP=file
  '$PY' '$S/adb_helpers.py' job start --name w1 $D12 -- soak --minutes 1 --every 1 --screenshots 0 --tag w1 >/dev/null && sleep 3 &&
  start=\$(date +%s); '$PY' '$S/adb_helpers.py' job stop w1 --grace 30 $D12 > '$TMP/w1.out' && test \$((\$(date +%s)-start)) -lt 20 &&
  grep -q '\"how\": \"stop-file\"' '$TMP/w1.out' && test -f '$R12/raw/jobs/w1.stop' &&
  '$PY' -c \"import json,sys; d=json.load(open(sys.argv[1])); assert d['status']=='stopped' and d['reason']=='остановлено (job stop)' and d['samples']>=1, d\" '$R12/raw/soak-w1-emulator-5554.json' &&
  '$PY' -c \"import json,sys; d=json.load(open(sys.argv[1])); assert d['status']=='stopped', d\" '$R12/raw/jobs/w1.json'"
check "job stop (файл-запрос): soak не ответил за --grace -> процесс снят, задача killed с причиной; новый start с тем же именем убирает старый запрос" sh -c "
  unset FAKE_ADB_UI_FLOW; export ANDROID_QA_JOB_STOP=file
  FAKE_ADB_MEMINFO_DELAY=40 '$PY' '$S/adb_helpers.py' job start --name w2 $D12 -- soak --minutes 1 --every 1 --screenshots 0 --tag w2 >/dev/null && sleep 2 &&
  '$PY' '$S/adb_helpers.py' job stop w2 --grace 1 $D12 > '$TMP/w2.out' && grep -q '\"how\": \"killed\"' '$TMP/w2.out' &&
  '$PY' -c \"import json,sys; d=json.load(open(sys.argv[1])); assert d['status']=='killed' and 'сводка не записана' in d['note'], d\" '$R12/raw/jobs/w2.json' &&
  for i in \$(seq 1 20); do '$PY' '$S/adb_helpers.py' job status w2 $D12 | grep -q '\"status\": \"killed\"' && break; sleep 0.5; done;
  '$PY' '$S/adb_helpers.py' job status w2 $D12 | grep -q '\"status\": \"killed\"' &&
  '$PY' '$S/adb_helpers.py' job start --name w1 $D12 -- soak --minutes 0.02 --every 1 --screenshots 0 --tag w1b >/dev/null && test ! -f '$R12/raw/jobs/w1.stop' &&
  for i in \$(seq 1 40); do grep -q '\"status\": \"done\"' '$R12/raw/jobs/w1.json' && break; sleep 0.5; done; grep -q '\"status\": \"done\"' '$R12/raw/jobs/w1.json'"

# ---------- microphone: Windows loopback is not automated (honest hint) ----------
check "mic: Windows — путь loopback не автоматизируется: подсказка о ручном пути и grpc/file (устройство есть и нет)" pyok "
import os, sys; sys.path.insert(0, sys.argv[1]); import mic
os.name = 'nt'; sys.platform = 'win32'
os.environ['ANDROID_QA_LOOPBACK'] = 'CABLE Output (VB-Audio Virtual Cable)|'
i = mic.loopback_info(); assert not i['ready'] and 'вслепую' in i['hint'] and 'grpc' in i['hint'] and 'CABLE Input' in i['hint'], i
os.environ['ANDROID_QA_LOOPBACK'] = ''
i = mic.loopback_info(); assert not i['ready'] and i['hint'].startswith('VB-Audio Virtual Cable') and 'вслепую' in i['hint'], i
" "$S"
