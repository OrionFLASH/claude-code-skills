'use strict';
// Browser tests of 1.3.0. Run through tests/test_v130_browser.sh (fixture server, FIXTURE_BASE, FIXTURE_PORT).
// Output: PASS/FAIL/SKIP lines, exit 1 on any FAIL.
const fs = require('fs');
const os = require('os');
const path = require('path');
const { spawnSync } = require('child_process');

const SKILL = path.resolve(__dirname, '..');
const NODE_DIR = path.join(SKILL, 'scripts', 'node');
const PY = process.platform === 'win32' ? 'python' : 'python3';
const B = process.env.FIXTURE_BASE;
const PORT = process.env.FIXTURE_PORT;
if (!B) { console.error('FIXTURE_BASE не задан: запускайте через tests/test_v130_browser.sh'); process.exit(2); }
const TMP = fs.mkdtempSync(path.join(os.tmpdir(), 'sqa-130-'));
const only = process.argv[2] ? new RegExp(process.argv[2]) : null;

let pass = 0, fail = 0, skip = 0;
async function t(name, fn) {
  if (only && !only.test(name)) return;
  try {
    const r = await fn();
    if (r === 'skip') { skip++; console.log('SKIP ' + name); } else { pass++; console.log('PASS ' + name); }
  } catch (e) { fail++; console.log('FAIL ' + name + ': ' + String(e && e.message || e).split('\n')[0]); }
}
function assert(c, msg) { if (!c) throw new Error(msg || 'assertion failed'); }
function run(script, args, opts = {}) {
  const r = spawnSync('node', [path.join(NODE_DIR, script), ...args], { encoding: 'utf8', timeout: opts.timeout || 180000, env: { ...process.env, ...(opts.env || {}) } });
  let json = null; try { json = JSON.parse(r.stdout); } catch { /* not JSON */ }
  return { code: r.status, out: r.stdout, err: r.stderr, json };
}
function exportRules(cfgText, name) {
  const cfg = path.join(TMP, name + '.yaml'); fs.writeFileSync(cfg, cfgText);
  const out = path.join(TMP, name + '.json');
  const r = spawnSync(PY, [path.join(SKILL, 'scripts', 'url_guard.py'), 'export', '--config', cfg, '--out', out], { encoding: 'utf8' });
  if (r.status !== 0) throw new Error('url_guard export: ' + r.stdout + r.stderr);
  return out;
}

(async () => {
  const rules = exportRules('site:\n  allowed_domains:\n    - 127.0.0.1\nrules:\n  forbidden_domains: []\n', 'rules');

  // ---------------- targets.js (G-12) + S-4 ----------------
  await t('targets.js: десктоп — 3 из 6 < 24×24 (button 2, link 1), < 44×44: 5, ссылка в тексте — исключение', async () => {
    const r = run('targets.js', [B + '/targets.html', '--rules', rules]);
    const x = r.json.runs[0];
    assert(x.total === 6 && x.lt24.count === 3 && x.lt24.byType.button === 2 && x.lt24.byType.link === 1, JSON.stringify(x));
    assert(x.lt44.count === 5 && x.inline === 1 && x.valid, JSON.stringify(x));
    assert(/3 из 6 меньше 24×24/.test(x.summary) && /3 из 6/.test(r.err), x.summary);
    assert(!x.smallest.some(s => /ghost|hidden/.test(s.selector)), 'скрытые/inert элементы посчитаны');
  });

  await t('targets.js на pixel7 (pointer:coarse): крупные цели сайта включились — 0 < 24×24; 412x915 без касаний — 3', async () => {
    const r = run('targets.js', [B + '/targets.html', '--device', 'pixel7,412x915', '--rules', rules]);
    const [phone, narrow] = r.json.runs;
    assert(phone.media.pointerCoarse && phone.valid && phone.lt24.count === 0 && phone.lt44.count === 1, JSON.stringify(phone));
    assert(narrow.lt24.count === 3 && !narrow.media.pointerCoarse && /WxH@mobile/.test(narrow.media.warning), JSON.stringify(narrow));
  });

  // ---------------- occlusion.js filters (G-11) ----------------
  await t('occlusion.js: фильтр --min-area отбрасывает мелкое пересечение, filtered в ответе', async () => {
    const r = run('occlusion.js', [B + '/occlusion-overlap.html', '--sizes', '1440x813', '--min-area', '1000']);
    const x = r.json.runs[0];
    assert(x.pairs.length === 0 && x.filtered.small >= 1 && r.json.minArea === 1000, JSON.stringify(x.filtered));
    const d = run('occlusion.js', [B + '/occlusion-overlap.html', '--sizes', '1440x813']);
    assert(d.json.runs[0].pairs.length === 1 && d.json.minArea === 16, 'по умолчанию пара должна остаться');
  });

  try { fs.rmSync(TMP, { recursive: true, force: true, maxRetries: 5, retryDelay: 300 }); } catch { /* ignore */ }
  console.log(`\nstream v1.3.0 browser: ${pass} PASS, ${fail} FAIL, ${skip} SKIP`);
  process.exit(fail ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
