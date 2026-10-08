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

  // ---------------- invariants.js: dialog of radio buttons (G-2) ----------------
  const dlgCfg = path.join(TMP, 'dialog.yaml');
  fs.writeFileSync(dlgCfg, [
    'version: 1', 'site:', '  allowed_domains:', '    - 127.0.0.1', 'side_effects:', '  - id: SE1', '    action: upload', '    target: "#upload"',
    '    effect: "сохранение попадает в публичный рейтинг, если не выбрано «Чужое»"', '    leaves: ["локальная копия сохранения"]',
    'invariants:', '  - id: INV2', '    after: SE1', '    within_ms: 3000', '    dialog:', '      choose:', '        - name: "Чуж(ой|ое)"',
    '        - name: "Не сейчас"', '      confirm:', '        role: button', '        name: "^Готово$"', '      then:', '        role: checkbox',
    '        name: "Чуж(ой|ое)"', '        state: checked', '        within_ms: 2000', '    vocabulary: "Чужое сохранение"', '    else: abort',
    'rules:', '  forbidden_domains: []', ''].join('\n'));
  const saveFile = path.join(TMP, 'save.sl2'); fs.writeFileSync(saveFile, 'save');
  const dlg = (variant) => run('invariants.js', ['exec', '--config', dlgCfg, '--effect', 'SE1', '--url', `${B}/upload-guard.html?variant=${variant}`,
    '--run-dir', path.join(TMP, 'dlg-' + variant), '--file', saveFile, '--rules', rules]);

  await t('invariants dialog: «Чужое» + «Не сейчас» выбраны, «Готово» нажата, флажок в панели отмечен -> код 0', async () => {
    const r = dlg('radio');
    assert(r.code === 0 && r.json.status === 'ok', r.out + r.err);
    const inv = r.json.invariants[0];
    assert(inv.steps.map(s => s.choose || s.confirm).join('|') === 'Чужое, только посмотреть|Не сейчас|Готово' && inv.label === 'Чужое сохранение', JSON.stringify(inv));
  });

  await t('invariants dialog (негативный): радио «Чужое» не выбирается -> остановка, «Готово» НЕ нажата', async () => {
    const r = dlg('radio-broken');
    assert(r.code === 3 && r.json.status === 'aborted' && /не выбран после нажатия/.test(r.json.invariants[0].detail), r.out);
    assert(!r.json.invariants[0].steps.some(s => s.confirm), 'кнопка подтверждения нажата');
    assert(/ОСТАНОВЛЕНО/.test(fs.readFileSync(path.join(TMP, 'dlg-radio-broken', 'side_effects.md'), 'utf8')));
  });

  await t('invariants dialog (негативный): после «Готово» флажка в панели нет -> остановка', async () => {
    const r = dlg('radio-nopanel');
    assert(r.code === 3 && /после диалога/.test(r.json.invariants[0].detail), r.out);
  });

  await t('invariants dialog: preflight — диалога до действия нет (ожидаемо)', async () => {
    const r = run('invariants.js', ['preflight', '--config', dlgCfg, '--url', `${B}/upload-guard.html?variant=radio`, '--run-dir', path.join(TMP, 'dlg-pf')]);
    assert(r.code === 0 && r.json.ok && /ожидаемо/.test(r.json.checks[0].before), r.out + r.err);
  });

  // ---------------- repro.js + recheck.py (S-9) ----------------
  await t('repro.js: --js true -> код 0; --selector + --assert по рамке; не воспроизвелось -> код 1; запрещённый URL -> 2', async () => {
    const yes = run('repro.js', ['--url', B + '/targets.html', '--rules', rules, '--js', "document.querySelectorAll('button').length > 3"]);
    assert(yes.code === 0 && yes.json.reproduced === true, yes.out + yes.err);
    const box = run('repro.js', ['--url', B + '/targets.html', '--rules', rules, '--selector', '#b1', '--assert', 'b.w < 24']);
    assert(box.code === 0 && box.json.box.w === 20, box.out + box.err);
    const phone = run('repro.js', ['--url', B + '/targets.html', '--rules', rules, '--device', 'pixel7', '--selector', '#b1', '--assert', 'b.w < 24']);
    assert(phone.code === 1 && phone.json.reproduced === false && phone.json.media.pointerCoarse, phone.out + phone.err);
    const denied = run('repro.js', ['--url', 'http://sibling.example/', '--rules', rules, '--js', 'true']);
    assert(denied.code === 2, 'запрещённый переход: ' + denied.code);
  });

  await t('recheck.py run: короткая форма repro {url, selector, assert} -> repro.js дважды, confirmed', async () => {
    const run2 = path.join(TMP, 'run-recheck');
    fs.mkdirSync(run2, { recursive: true });
    fs.copyFileSync(rules, path.join(run2, 'rules.json'));
    fs.writeFileSync(path.join(run2, 'findings.json'), JSON.stringify({ run: { id: 'r', site: B, depth: 'smoke', mode: 'dry-run' }, findings: [
      { id: 'F-001', direction: 'accessibility', check_id: 'a11y.target-size', type: 'a11y', severity: 'low', title: 'Кнопка 22×22', url: B + '/targets.html',
        actual: '22×22', sources: ['own:script:targets'], repro: { url: B + '/targets.html', selector: '#b1', assert: 'b.w < 24' } },
      { id: 'F-002', direction: 'accessibility', check_id: 'a11y.target-size', type: 'a11y', severity: 'low', title: 'Кнопка на телефоне', url: B + '/targets.html',
        actual: '22×22', sources: ['own:script:targets'], repro: { url: B + '/targets.html', selector: '#b1', assert: 'b.w < 24', device: 'pixel7' } }] }));
    const r = spawnSync(PY, [path.join(SKILL, 'scripts', 'recheck.py'), 'run', run2, '--times', '2', '--pause', '0'], { encoding: 'utf8', timeout: 300000 });
    const rep = Object.fromEntries(JSON.parse(r.stdout).map(x => [x.id, x]));
    assert(rep['F-001'].status === 'confirmed' && rep['F-001'].reproduced_runs === 2, r.stdout);
    assert(rep['F-002'].status === 'not-reproduced', 'на телефоне с pointer:coarse кнопка крупная: ' + r.stdout);
    const saved = JSON.parse(fs.readFileSync(path.join(run2, 'findings.json'), 'utf8')).findings[0].recheck;
    assert(saved.by === 'recheck.py' && saved.runs.length === 2 && saved.argv.some(x => /repro\.js$/.test(x)), JSON.stringify(saved).slice(0, 300));
  });

  try { fs.rmSync(TMP, { recursive: true, force: true, maxRetries: 5, retryDelay: 300 }); } catch { /* ignore */ }
  console.log(`\nstream v1.3.0 browser: ${pass} PASS, ${fail} FAIL, ${skip} SKIP`);
  process.exit(fail ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
