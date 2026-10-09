'use strict';
// Browser tests of 1.4.0 on LOCAL FILES (file://, no server): detectors with --url file://…, guard of local roots
// (outside the folder, symlinks, JS navigation), links.js on disk, headers/lighthouse «not applicable», parity of the
// JS mirror (lib.js) with url_guard.py, browser mode from rules.json. Run through tests/test_v140_browser.sh.
// Output: PASS/FAIL/SKIP lines, exit 1 on any FAIL.
const fs = require('fs');
const os = require('os');
const path = require('path');
const { spawnSync } = require('child_process');
const { pathToFileURL } = require('url');

const SKILL = path.resolve(__dirname, '..');
const NODE_DIR = path.join(SKILL, 'scripts', 'node');
const PY = process.env.PY || (process.platform === 'win32' ? 'python' : 'python3');
const FIX = path.join(__dirname, 'fixtures');
const TMP = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'sqa-140-')));
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
const url = (p) => pathToFileURL(p).href;
const readJsonl = (f) => fs.existsSync(f) ? fs.readFileSync(f, 'utf8').trim().split('\n').filter(Boolean).map(l => JSON.parse(l)) : [];

(async () => {
  // A copy of the fixture app in a temp folder (+ a folder next to it and, where possible, a symlink to it).
  const APP = path.join(TMP, 'app');
  fs.cpSync(path.join(FIX, 'local-app'), APP, { recursive: true });
  fs.copyFileSync(path.join(FIX, 'local-outside.html'), path.join(TMP, 'local-outside.html'));
  fs.mkdirSync(path.join(TMP, 'secret')); fs.writeFileSync(path.join(TMP, 'secret', 'data.html'), '<p>секрет</p>');
  let symlink = true;
  try { fs.symlinkSync(path.join(TMP, 'secret'), path.join(APP, 'evil'), 'dir'); } catch { symlink = false; }
  const INDEX = url(path.join(APP, 'index.html'));
  const rules = exportRules(`site:\n  start_urls:\n    - ${INDEX}\n  allowed_domains:\n    - file\nrules:\n  forbidden_domains: []\n`, 'local');

  await t('occlusion.js --url file://… --frames all: пара «значок над кнопкой» и перекрытие кнопки в iframe тостом страницы', async () => {
    const r = run('occlusion.js', ['--url', INDEX, '--rules', rules, '--frames', 'all', '--sizes', '1280x720']);
    const x = r.json.runs[0];
    assert(x.url === INDEX && !x.error && !x.blocked, JSON.stringify(x).slice(0, 300));
    assert(x.frames.some(f => /inner\.html$/.test(f.url)), 'нет кадра inner.html');
    assert(x.pairs.some(p => p.occluded.selector === '#save-all' && p.occluder.selector === '#badge'), 'нет пары #save-all/#badge');
    assert(x.pairs.some(p => p.crossFrame && p.occluded.selector === '#reset'), 'нет crossFrame-пары #reset');
  });

  await t('occlusion.js: путь к файлу без схемы -> file://, файл вне каталога -> blocked base:file-outside-roots', async () => {
    const r = run('occlusion.js', [path.join(APP, 'index.html'), path.join(TMP, 'local-outside.html'), '--rules', rules, '--sizes', '1280x720']);
    const [a, b] = r.json.runs;
    assert(a.url === INDEX && a.pairs, JSON.stringify(a).slice(0, 200));
    assert(b.blocked && b.blocked.rule === 'base:file-outside-roots', JSON.stringify(b));
  });

  await t('reachability.js --url file://… на низком окне: «Применить параметр» недостижим', async () => {
    const r = run('reachability.js', ['--url', INDEX, '--rules', rules, '--sizes', '1280x450']);
    const items = r.json.runs[0].items || [];
    assert(items.some(i => i.selector === '#deep' && i.verdict === 'недостижим'), JSON.stringify(items).slice(0, 300));
  });

  await t('targets.js --url file://…: мелкие цели посчитаны (кнопка 16×16)', async () => {
    const r = run('targets.js', ['--url', INDEX, '--rules', rules]);
    const x = r.json.runs[0];
    assert(x.valid && x.lt24.count >= 1 && x.smallest.some(s => /tiny/.test(s.selector)), JSON.stringify(x).slice(0, 300));
  });

  await t('a11y.js --url file://…: axe по странице и кадру, вне каталога — blocked без открытия', async () => {
    const r = run('a11y.js', ['--url', INDEX, '--url', url(path.join(TMP, 'local-outside.html')), '--rules', rules, '--throttle', '0']);
    const [a, b] = r.json.results;
    assert(!a.error && a.violations.some(v => v.id === 'image-alt') && a.text.frames.length === 1, JSON.stringify(a).slice(0, 300));
    assert(b.blocked && b.blocked.rule === 'base:file-outside-roots' && !b.violations, JSON.stringify(b));
  });

  await t('shot.js --url file://…: снимок и аннотация, rtl.js и device_context run — без ошибок', async () => {
    const out = path.join(TMP, 'shots', 'F-001-badge.png');
    const s = run('shot.js', ['--url', INDEX, '--rules', rules, '--out', out, '#badge|Значок закрывает кнопку']);
    assert(s.code === 0 && fs.existsSync(s.json.annotated) && !s.json.missing.length, s.err.slice(0, 300));
    const r = run('rtl.js', ['--url', INDEX, '--rules', rules]);
    assert(r.code === 0 && r.json.runs[0].url === INDEX && !r.json.runs[0].error, r.out.slice(0, 200));
    const d = run('device_context.js', ['run', '--devices', 'desktop', '--url', INDEX, '--rules', rules]);
    assert(d.code === 0 && d.json.results[0].data.title === 'Локальное приложение (file://): редактор', d.out.slice(0, 300));
  });

  await t('guard: клик с переходом JS на файл вне каталога — переход оборван, запись base:file-outside-roots', async () => {
    const scen = path.join(TMP, 'leave.js');
    fs.writeFileSync(scen, "module.exports = async ({ page, guarded }) => { await guarded.click('#leave'); await page.waitForTimeout(800); return { url: page.url() }; };");
    const log = path.join(TMP, 'logs', 'blocked-leave.jsonl');
    const d = run('device_context.js', ['run', '--devices', 'desktop', '--url', INDEX, '--rules', rules, '--scenario', scen, '--log', log]);
    assert(d.code === 0, d.err.slice(0, 300));
    assert(!/local-outside/.test(d.json.results[0].data.url), 'страница вне каталога открылась: ' + d.json.results[0].data.url);
    assert(readJsonl(log).some(e => e.rule === 'base:file-outside-roots' && /local-outside/.test(e.url)), fs.existsSync(log) ? fs.readFileSync(log, 'utf8') : 'нет журнала');
  });

  await t('guard: симлинк внутри каталога наружу — страница и ресурс через него не открываются', async () => {
    if (!symlink) return 'skip';
    const r = run('occlusion.js', ['--url', url(path.join(APP, 'evil', 'data.html')), '--rules', rules, '--sizes', '800x600']);
    assert(r.json.runs[0].blocked && r.json.runs[0].blocked.rule === 'base:file-symlink', JSON.stringify(r.json.runs[0]));
    // resource through the symlink from an allowed page: blocked at the route level
    fs.writeFileSync(path.join(APP, 'with-link.html'), '<!doctype html><title>x</title><iframe src="evil/data.html"></iframe><img src="evil/none.png">');
    const log = path.join(TMP, 'logs', 'blocked-symlink.jsonl');
    const o = run('occlusion.js', ['--url', url(path.join(APP, 'with-link.html')), '--rules', rules, '--sizes', '800x600', '--frames', 'all', '--log', log]);
    assert(!o.json.runs[0].blocked, JSON.stringify(o.json.runs[0]).slice(0, 200));
    assert(!(o.json.runs[0].frames || []).some(f => /secret|evil/.test(f.url) && f.checked > 0), 'кадр через симлинк проверен');
    assert(readJsonl(log).some(e => e.rule === 'base:file-symlink'), fs.existsSync(log) ? fs.readFileSync(log, 'utf8') : 'нет журнала');
  });

  await t('links.js на file://: страницы с диска, битая локальная ссылка 404, файл вне каталога — skipped', async () => {
    const r = run('links.js', [INDEX, '--rules', rules, '--frames', 'all']);
    const j = r.json;
    assert(j.pages.some(p => /sub\/page\.html$/.test(p.url) && p.status === 200 && p.local), 'нет sub/page.html');
    assert(j.pages.some(p => /inner\.html$/.test(p.url)), 'кадр inner.html не обойдён');
    assert(j.broken.some(b => /nope\.html$/.test(b.url) && b.status === 404), JSON.stringify(j.broken));
    assert(j.skipped.some(s => /local-outside\.html$/.test(s.url)), JSON.stringify(j.skipped));
    const noRules = run('links.js', [path.join(APP, 'index.html')]);
    assert(noRules.json.crawled >= 3 && noRules.json.skipped.some(s => /local-outside/.test(s.url)), 'без --rules каталог стартового файла');
  });

  await t('headers.js и lighthouse.js: file:// — notApplicable, без запросов и падений', async () => {
    const h = run('headers.js', [INDEX]);
    assert(h.code === 0 && h.json.notApplicable[0].url === INDEX && !h.json.pages.length, h.out.slice(0, 200));
    const l = run('lighthouse.js', [INDEX]);
    assert(l.code === 0 && l.json.notApplicable[0].url === INDEX && !l.json.results.length, l.out.slice(0, 200) + l.err.slice(0, 200));
  });

  await t('repro.js --url file://… --js: дефект воспроизводится', async () => {
    const r = run('repro.js', ['--url', INDEX, '--rules', rules, '--js', "document.elementFromPoint(700, 140).id === 'badge'"]);
    assert(r.code === 0 && r.json.reproduced === true, r.out + r.err);
  });

  await t('паритет lib.js (route) и url_guard.py (goto) на file://: одинаковые allow/deny', async () => {
    const { navAllowed, loadRules } = require(path.join(NODE_DIR, 'lib.js'));
    const R = loadRules(rules);
    const cases = [INDEX, url(path.join(APP, 'sub', 'page.html')) + '#/x', url(path.join(TMP, 'local-outside.html')),
      url(path.join(APP, 'checkout', 'pay.html')), url(path.join(APP, 'missing.html')), 'https://example.com/', 'file://server/share/x.html']
      .concat(symlink ? [url(path.join(APP, 'evil', 'data.html'))] : []);
    const bad = [];
    for (const u of cases) {
      const js = navAllowed(u, R).ok;
      const py = spawnSync(PY, [path.join(SKILL, 'scripts', 'url_guard.py'), 'nav', u, '--config', path.join(TMP, 'local.yaml')], { encoding: 'utf8' }).status === 0;
      if (js !== py) bad.push(`${u}: js ${js}, py ${py}`);
    }
    assert(!bad.length, bad.join('; '));
  });

  console.log(`stream v1.4.0 browser: ${pass} PASS, ${fail} FAIL, ${skip} SKIP`);
  try { fs.rmSync(TMP, { recursive: true, force: true }); } catch { /* ignore */ }
  process.exit(fail ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
