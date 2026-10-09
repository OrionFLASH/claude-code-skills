'use strict';
// Browser tests of 1.5.0 on local fixtures (file:// and a local http.server for Lighthouse; no real sites):
//   #9  tab registry of node scripts in <RUN_DIR>/tabs.json (own browser — tool node; a page created in «the user's
//       browser» over CDP — tool cdp; crash -> tabs.py cleanup; only own tabs are closed);
//   #34 reachability in WebKit (touch model) and touch-action, e2e stubs under Playwright Test (e2e_run.js, guard in
//       the test context), a separate Playwright MCP with the guard of the run (browser_mode.py mcp --check), and —
//       only with QA_HEADED=1 — a visible window (--headed, slow-mo).
// Run through tests/test_v150_browser.sh. Output: PASS/FAIL/SKIP lines, exit 1 on any FAIL.
const fs = require('fs');
const os = require('os');
const path = require('path');
const { spawnSync, spawn } = require('child_process');
const { pathToFileURL } = require('url');

const SKILL = path.resolve(__dirname, '..');
const NODE_DIR = path.join(SKILL, 'scripts', 'node');
const PY = process.env.PY || (process.platform === 'win32' ? 'python' : 'python3');
const FIX = path.join(__dirname, 'fixtures');
const TMP = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'sqa-150-')));
const only = process.argv[2] ? new RegExp(process.argv[2]) : null;
const pw = require(path.join(NODE_DIR, 'node_modules', 'playwright'));

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
  const r = spawnSync('node', [path.join(NODE_DIR, script), ...args], { encoding: 'utf8', timeout: opts.timeout || 240000, env: { ...process.env, ...(opts.env || {}) } });
  let json = null; try { json = JSON.parse(r.stdout); } catch { /* not JSON */ }
  return { code: r.status, signal: r.signal, out: r.stdout, err: r.stderr, json };
}
const py = (args) => spawnSync(PY, args, { encoding: 'utf8' });
const url = (p) => pathToFileURL(p).href;
const tabsOf = (run) => { try { return JSON.parse(fs.readFileSync(path.join(run, 'tabs.json'), 'utf8')).tabs; } catch { return []; } };
const readJsonl = (f) => fs.existsSync(f) ? fs.readFileSync(f, 'utf8').trim().split('\n').filter(Boolean).map(l => JSON.parse(l)) : [];
const webkitOk = (() => { const r = spawnSync('node', [path.join(NODE_DIR, 'probe.js'), 'webkit'], { encoding: 'utf8' }); try { return JSON.parse(r.stdout).webkit.ok; } catch { return false; } })();

// A run folder: copy of the fixture app, run-config.yaml (local_roots) and rules.json — the layout of a real run.
function makeRun(name, extraCfg = '') {
  const run = path.join(TMP, name);
  fs.mkdirSync(run, { recursive: true });
  fs.cpSync(path.join(FIX, 'local-app'), path.join(run, 'app'), { recursive: true });
  fs.writeFileSync(path.join(run, 'run-config.yaml'),
    `site:\n  start_urls:\n    - ${url(path.join(run, 'app', 'index.html'))}\n  local_roots:\n    - ${path.join(run, 'app')}\n  allowed_domains: []\nrules:\n  forbidden_domains: []\n${extraCfg}`);
  const r = py([path.join(SKILL, 'scripts', 'url_guard.py'), 'export', '--config', path.join(run, 'run-config.yaml'), '--out', path.join(run, 'rules.json')]);
  if (r.status !== 0) throw new Error('url_guard export: ' + r.stdout + r.stderr);
  return { run, rules: path.join(run, 'rules.json'), index: url(path.join(run, 'app', 'index.html')) };
}

// Chromium with a CDP port stands in for «the user's browser» (a temporary profile, never the user's one).
async function startCdpBrowser() {
  const port = 9800 + Math.floor(Math.random() * 400);
  const proc = spawn(pw.chromium.executablePath(), ['--headless=new', `--remote-debugging-port=${port}`, `--user-data-dir=${path.join(TMP, 'profile-' + port)}`,
    '--no-first-run', '--no-default-browser-check', 'about:blank'], { stdio: 'ignore' });
  const cdp = `http://127.0.0.1:${port}`;
  for (let i = 0; i < 50; i++) {
    try { const r = await fetch(cdp + '/json/version'); if (r.ok) break; } catch { /* starting */ }
    await new Promise(r => setTimeout(r, 200));
  }
  const pages = async () => (await (await fetch(cdp + '/json/list')).json()).filter(p => p.type === 'page');
  return { cdp, pages, stop: () => new Promise(res => { proc.once('exit', res); proc.kill(); setTimeout(res, 3000); }) };
}

(async () => {
  // ================= #9: tab registry =================
  const A = makeRun('run-a');

  await t('#9 occlusion.js --rules <RUN_DIR>/rules.json --owner: запись node на каждое устройство, закрыта, url, pid, скрипт', async () => {
    const r = run('occlusion.js', ['--url', A.index, '--rules', A.rules, '--owner', 'qa-ux', '--sizes', '1280x720,800x600']);
    assert(r.code === 0, r.err.slice(0, 300));
    const tabs = tabsOf(A.run);
    assert(tabs.length === 2 && tabs.every(x => x.tool === 'node' && x.owner === 'qa-ux' && x.closed_at && x.script === 'occlusion.js' && x.url === A.index), JSON.stringify(tabs).slice(0, 400));
    assert(tabs.map(x => x.profile).join() === '1280x720,800x600' && tabs[0].pid === tabs[1].pid, JSON.stringify(tabs.map(x => [x.profile, x.pid])));
    assert(/открыто 0/.test(py([path.join(SKILL, 'scripts', 'tabs.py'), 'list', A.run]).stdout), 'tabs.py list');
  });

  await t('#9 a11y.js (2 языка), shot.js --batch (2 снимка, без служебного браузера подписей), device_context run, repro.js — все вкладки в реестре и закрыты', async () => {
    const before = tabsOf(A.run).length;
    const a = run('a11y.js', ['--url', A.index, '--rules', A.rules, '--locales', 'ru-RU,de-DE', '--throttle', '0']);
    assert(a.code === 0, a.err.slice(0, 200));
    const batch = path.join(A.run, 'shots.json');
    fs.writeFileSync(batch, JSON.stringify([{ name: 'F-001-badge', url: A.index, targets: ['#badge|Значок'] }, { name: 'F-002-tiny', url: A.index, size: '800x600', targets: ['#tiny|Мелкая'] }]));
    const s = run('shot.js', ['--batch', batch, '--dir', path.join(A.run, 'screenshots'), '--rules', A.rules]);
    assert(s.code === 0 && fs.existsSync(path.join(A.run, 'screenshots', 'F-001-badge-annotated.png')), s.err.slice(0, 200));
    const d = run('device_context.js', ['run', '--devices', 'pixel7', '--url', A.index, '--rules', A.rules]);
    assert(d.code === 0, d.err.slice(0, 200));
    const p = run('repro.js', ['--url', A.index, '--rules', A.rules, '--js', "document.elementFromPoint(700, 140).id === 'badge'"]);
    assert(p.code === 0, p.out + p.err);
    const tabs = tabsOf(A.run).slice(before);
    const by = (sc) => tabs.filter(x => x.script === sc).map(x => x.profile).join();
    assert(by('a11y.js') === '1440x900@ru-RU,1440x900@de-DE', by('a11y.js'));
    assert(by('shot.js') === 'desktop,800x600', 'shot: ' + by('shot.js'));
    assert(by('device_context.js') === 'pixel7' && by('repro.js') === 'desktop', JSON.stringify(tabs.map(x => [x.script, x.profile])));
    assert(tabs.every(x => x.closed_at && x.owner === 'node'), JSON.stringify(tabs.filter(x => !x.closed_at)));
  });

  await t('#9 без папки прогона (rules.json без run-config.yaml рядом), --no-tabs и SITE_QA_TABS=0 — реестр не пишется; device_context media — не регистрируется', async () => {
    const loose = path.join(TMP, 'loose'); fs.mkdirSync(loose);
    fs.copyFileSync(A.rules, path.join(loose, 'rules.json'));
    const r = run('targets.js', ['--url', A.index, '--rules', path.join(loose, 'rules.json')]);
    assert(r.code === 0 && !fs.existsSync(path.join(loose, 'tabs.json')), 'loose: ' + r.err.slice(0, 200));
    const n = tabsOf(A.run).length;
    assert(run('targets.js', ['--url', A.index, '--rules', A.rules, '--no-tabs']).code === 0, 'no-tabs');
    assert(run('targets.js', ['--url', A.index, '--rules', A.rules], { env: { SITE_QA_TABS: '0' } }).code === 0, 'SITE_QA_TABS=0');
    assert(run('device_context.js', ['media', '--devices', 'pixel7', '--run-dir', A.run]).code === 0, 'media');
    assert(tabsOf(A.run).length === n, `реестр изменился: ${n} -> ${tabsOf(A.run).length}`);
  });

  await t('#9 сбой: process.exit в сценарии — вкладка закрыта обработчиком выхода; SIGKILL — открыта, tabs.py cleanup --yes закрывает как завершённую', async () => {
    const B = makeRun('run-crash');
    const exitScen = path.join(B.run, 'exit.js');
    fs.writeFileSync(exitScen, 'module.exports = async () => { process.exit(7); };');
    const e = run('device_context.js', ['run', '--devices', 'desktop', '--url', B.index, '--rules', B.rules, '--scenario', exitScen]);
    assert(e.code === 7, 'код ' + e.code);
    assert(tabsOf(B.run).length === 1 && tabsOf(B.run)[0].closed_at, JSON.stringify(tabsOf(B.run)));
    const killScen = path.join(B.run, 'kill.js');
    fs.writeFileSync(killScen, "module.exports = async () => { process.kill(process.pid, 'SIGKILL'); };");
    const k = run('device_context.js', ['run', '--devices', 'pixel7', '--url', B.index, '--rules', B.rules, '--scenario', killScen, '--owner', 'qa-crash']);
    assert(k.signal === 'SIGKILL', 'signal ' + k.signal);
    const open = tabsOf(B.run).filter(x => !x.closed_at);
    assert(open.length === 1 && open[0].owner === 'qa-crash' && open[0].profile === 'pixel7', JSON.stringify(open));
    const plan = JSON.parse(py([path.join(SKILL, 'scripts', 'tabs.py'), 'cleanup', B.run, '--owner', 'qa-crash']).stdout).plan;
    assert(plan.length === 1 && /уже закрыта/.test(plan[0].action), JSON.stringify(plan));
    py([path.join(SKILL, 'scripts', 'tabs.py'), 'cleanup', B.run, '--owner', 'qa-crash', '--yes']);
    assert(tabsOf(B.run).every(x => x.closed_at), JSON.stringify(tabsOf(B.run)));
  });

  // «The user's browser» over CDP: only the page the script created is registered and closed — never the user's tab.
  let browser = null;
  try { browser = await startCdpBrowser(); } catch { browser = null; }
  await t('#9 CDP: страница, созданная скриптом в браузере пользователя, — tool cdp с target id, закрыта; вкладка пользователя цела', async () => {
    if (!browser) return 'skip';
    const C = makeRun('run-cdp');
    const userTabs = await browser.pages();
    const r = run('occlusion.js', ['--cdp', browser.cdp, '--page-match', 'no-such-page', '--url', C.index, '--rules', C.rules, '--owner', 'qa-ux']);
    assert(r.code === 0, r.err.slice(0, 300));
    const tabs = tabsOf(C.run);
    assert(tabs.length === 1 && tabs[0].tool === 'cdp' && /^[0-9A-F]{32}$/i.test(tabs[0].target_id || '') && tabs[0].closed_at && tabs[0].url === C.index, JSON.stringify(tabs));
    const now = await browser.pages();
    assert(now.length === userTabs.length && now.every(p => userTabs.some(u => u.id === p.id)), JSON.stringify(now.map(p => p.url)));
  });

  await t('#9 CDP: скрипт убит с открытой вкладкой — tabs.py cleanup --cdp закрывает ТОЛЬКО её (по target id), вкладка пользователя остаётся', async () => {
    if (!browser) return 'skip';
    const C = makeRun('run-cdp-kill');
    const kill = path.join(C.run, 'kill.js');
    fs.writeFileSync(kill, "module.exports = async () => { process.kill(process.pid, 'SIGKILL'); };");
    const userTabs = await browser.pages();
    const r = run('shot.js', ['--cdp', browser.cdp, '--page-match', 'no-such-page', '--url', C.index, '--rules', C.rules, '--setup', kill, '--out', path.join(C.run, 'x.png'), '#badge|x']);
    assert(r.signal === 'SIGKILL', 'signal ' + r.signal);
    const rec = tabsOf(C.run)[0];
    assert(rec && rec.tool === 'cdp' && !rec.closed_at && rec.target_id, JSON.stringify(tabsOf(C.run)));
    assert((await browser.pages()).some(p => p.id === rec.target_id), 'вкладки скрипта нет в браузере');
    const plan = JSON.parse(py([path.join(SKILL, 'scripts', 'tabs.py'), 'cleanup', C.run, '--cdp', browser.cdp]).stdout).plan;
    assert(/закрыть по CDP/.test(plan[0].action), JSON.stringify(plan));
    py([path.join(SKILL, 'scripts', 'tabs.py'), 'cleanup', C.run, '--cdp', browser.cdp, '--yes']);
    await new Promise(res => setTimeout(res, 500));
    const now = await browser.pages();
    assert(!now.some(p => p.id === rec.target_id), 'вкладка скрипта не закрыта');
    assert(userTabs.every(u => now.some(p => p.id === u.id)), 'закрыта вкладка пользователя');
    assert(tabsOf(C.run)[0].closed_at, 'запись не закрыта');
  });

  await t('#9 legal_guest.js --cdp: новый контекст в браузере пользователя — tool cdp, закрыт; без --cdp — tool node', async () => {
    if (!browser) return 'skip';
    const L = makeRun('run-legal');
    const r = run('legal_guest.js', ['--url', L.index, '--rules', L.rules, '--cdp', browser.cdp, '--wait', '200']);
    assert(r.code === 0, r.err.slice(0, 300));
    const n = run('legal_guest.js', ['--url', L.index, '--rules', L.rules, '--wait', '200']);
    assert(n.code === 0, n.err.slice(0, 300));
    const tabs = tabsOf(L.run);
    assert(tabs.length === 2 && tabs[0].tool === 'cdp' && tabs[0].target_id && tabs[1].tool === 'node' && tabs.every(x => x.closed_at), JSON.stringify(tabs));
  });
  if (browser) await browser.stop();

  await t('#9 lighthouse.js (локальный http): одна запись измеряющего Chrome, закрыта', async () => {
    const base = process.env.FIXTURE_BASE;
    if (!base) return 'skip';
    const Lh = makeRun('run-lh');
    const r = run('lighthouse.js', [base + '/targets.html', '--form', 'desktop', '--categories', 'seo', '--run-dir', Lh.run], { timeout: 180000 });
    assert(r.code === 0, (r.err || '').slice(-300));
    const tabs = tabsOf(Lh.run);
    assert(tabs.length === 1 && tabs[0].profile === 'lighthouse-desktop' && tabs[0].engine === 'chrome-launcher' && tabs[0].closed_at, JSON.stringify(tabs));
  });

  // ================= #34: WebKit wheel/gestures (reachability) =================
  await t('#34 reachability: touch-action:none — на десктопе колесо достаёт, на телефоне (Chromium, жест CDP) — недостижим', async () => {
    const r = run('reachability.js', [url(path.join(FIX, 'reach-touch-action.html')), '--sizes', '863x360', '--device', 'pixel7-landscape', '--selector', '#only-missing']);
    const [desk, phone] = r.json.runs;
    assert(desk.items[0].verdict === 'достижим' && desk.items[0].gesture === 'skipped', JSON.stringify(desk.items[0]));
    assert(phone.items[0].verdict === 'недостижим' && phone.items[0].wheel === true && phone.items[0].gesture === false && phone.items[0].gestureMethod === 'cdp', JSON.stringify(phone.items[0]));
  });

  await t('#34 reachability: мобильный WebKit (iphone15-landscape) — эмуляция в Chromium И настоящий WebKit с моделью касания; три фикстуры', async () => {
    if (!webkitOk) return 'skip';
    const v = {};
    for (const fx of ['reach-scroll', 'reach-hidden', 'reach-touch-action']) {
      const r = run('reachability.js', [url(path.join(FIX, fx + '.html')), '--device', 'iphone15-landscape', '--selector', '#only-missing']);
      assert(r.json && r.json.runs.length === 2, fx + ': ' + (r.err || r.out).slice(0, 200));
      const [emu, wk] = r.json.runs;
      assert(emu.engine === 'chromium' && wk.engine === 'webkit' && /модель/.test(wk.engineNote), JSON.stringify([emu.engine, wk.engine, wk.engineNote]));
      const i = wk.items[0];
      assert(i.wheel === null && /not supported in mobile WebKit/.test(i.wheelError || '') && i.gestureMethod === 'touch-model', fx + ': ' + JSON.stringify(i));
      v[fx] = [emu.items[0].verdict, i.verdict, i.gestureBlocked || ''];
    }
    assert(v['reach-scroll'][0] === 'достижим' && v['reach-scroll'][1] === 'достижим', JSON.stringify(v));
    assert(v['reach-hidden'][1] === 'недостижим' && /overflow: hidden/.test(v['reach-hidden'][2]), JSON.stringify(v));
    assert(v['reach-touch-action'][0] === 'недостижим' && v['reach-touch-action'][1] === 'недостижим' && /touch-action: none/.test(v['reach-touch-action'][2]), JSON.stringify(v));
  });

  await t('#34 reachability --webkit chromium|webkit: только эмуляция / только WebKit; десктопный WebKit — колесо работает', async () => {
    if (!webkitOk) return 'skip';
    const f = url(path.join(FIX, 'reach-scroll.html'));
    const c = run('reachability.js', [f, '--device', 'iphone15-landscape', '--webkit', 'chromium', '--selector', '#only-missing']);
    const w = run('reachability.js', [f, '--device', 'iphone15-landscape', '--webkit', 'webkit', '--selector', '#only-missing']);
    assert(c.json.runs.length === 1 && c.json.runs[0].engine === 'chromium', JSON.stringify(c.json.runs.map(x => x.engine)));
    assert(w.json.runs.length === 1 && w.json.runs[0].engine === 'webkit', JSON.stringify(w.json.runs.map(x => x.engine)));
    const d = run('reachability.js', [f, '--sizes', '863x360', '--browser', 'webkit', '--selector', '#only-missing']);
    assert(d.json.runs[0].engine === 'webkit' && d.json.runs[0].items[0].wheel === true && d.json.runs[0].items[0].verdict === 'достижим', JSON.stringify(d.json.runs[0].items[0]));
  });

  // ================= #34: e2e stubs under Playwright Test =================
  const E = makeRun('run-e2e');
  fs.mkdirSync(path.join(E.run, 'drafts', 'e2e'), { recursive: true });
  const finding = (extra = {}) => ({ id: 'F-001', title: 'Значок закрывает кнопку', check_id: 'ui.occlusion', severity: 'medium', url: E.index,
    steps: ['Открыть редактор', 'Посмотреть на кнопку «Сохранить всё»'], expected: 'Кнопка видна целиком', actual: 'Значок закрывает кнопку',
    repro: { url: E.index, js: "document.elementFromPoint(700, 140).id === 'badge'" }, ...extra });
  fs.writeFileSync(path.join(E.run, 'findings.json'), JSON.stringify({ findings: [finding(), finding({ id: 'F-002', repro: undefined })] }));
  const stub = (id, lang) => {
    const out = path.join(E.run, 'drafts', 'e2e', `${id}.spec.${lang}`);
    const r = py([path.join(SKILL, 'scripts', 'e2e_stub.py'), path.join(E.run, 'findings.json'), '--id', id, '--lang', lang, '--out', out]);
    if (r.status !== 0) throw new Error('e2e_stub: ' + r.stderr);
    return out;
  };
  const appUrl = url(path.join(E.run, 'app')) + '/';
  const fixedApp = path.join(E.run, 'app-fixed');
  fs.cpSync(path.join(E.run, 'app'), fixedApp, { recursive: true });
  fs.writeFileSync(path.join(fixedApp, 'index.html'), fs.readFileSync(path.join(fixedApp, 'index.html'), 'utf8').replace('#badge { position: fixed; left: 680px;', '#badge { position: fixed; left: 760px;'));
  const fixedRules = (() => {
    const cfg = path.join(E.run, 'fixed.yaml');
    fs.writeFileSync(cfg, `site:\n  local_roots:\n    - ${fixedApp}\n  allowed_domains: []\n`);
    py([path.join(SKILL, 'scripts', 'url_guard.py'), 'export', '--config', cfg, '--out', path.join(E.run, 'fixed-rules.json')]);
    return path.join(E.run, 'fixed-rules.json');
  })();

  await t('#34 e2e_run: заготовка (ts) под Playwright Test — ДО исправления падает на проверке дефекта (--expect fail, код 0)', async () => {
    const r = run('e2e_run.js', [stub('F-001', 'ts'), '--rules', E.rules, '--app-url', appUrl, '--expect', 'fail']);
    assert(r.code === 0 && r.json.ok, (r.json && r.json.reason) || r.err.slice(0, 300));
    const run0 = r.json.specs[0].tests[0].runs[0];
    assert(run0.status === 'failed' && /дефект воспроизводится/.test(run0.error), JSON.stringify(run0));
    const tab = tabsOf(E.run).find(x => x.script === 'e2e_run.js');
    assert(tab && tab.profile === 'e2e' && tab.closed_at, 'реестр вкладок: ' + JSON.stringify(tabsOf(E.run)));
  });

  await t('#34 e2e_run: после исправления (копия приложения) — проходит 3 раза подряд (--expect pass, --repeat-each 3 по умолчанию); js-заготовка тоже', async () => {
    const r = run('e2e_run.js', [stub('F-001', 'ts'), stub('F-001', 'js'), '--rules', fixedRules, '--app-url', url(fixedApp) + '/', '--expect', 'pass']);
    assert(r.code === 0 && r.json.ok && r.json.repeatEach === 3, (r.json && r.json.reason) || r.err.slice(0, 300));
    assert(r.json.specs.length === 2 && r.json.specs.every(s => s.tests.length === 1 && s.tests[0].runs.length === 3 && s.tests[0].runs.every(x => x.status === 'passed')), JSON.stringify(r.json.specs).slice(0, 300));
    const bad = run('e2e_run.js', [stub('F-001', 'ts'), '--rules', E.rules, '--app-url', appUrl, '--expect', 'pass', '--repeat-each', '1']);
    assert(bad.code === 1 && /не прошли/.test(bad.json.reason), 'pass на дефекте: ' + JSON.stringify(bad.json).slice(0, 200));
  });

  await t('#34 e2e_run: test.fixme (нет repro) — не проход (код 1); адрес вне local_roots — код 3 до запуска; без rules — 4', async () => {
    const f = run('e2e_run.js', [stub('F-002', 'ts'), '--rules', E.rules, '--app-url', appUrl, '--expect', 'pass', '--repeat-each', '1']);
    assert(f.code === 1 && /fixme/.test(f.json.reason), JSON.stringify(f.json).slice(0, 200));
    const outside = url(TMP) + '/';
    const o = run('e2e_run.js', [stub('F-001', 'ts'), '--rules', E.rules, '--app-url', outside, '--expect', 'fail']);
    assert(o.code === 3 && /запрещён/.test(o.json.error), JSON.stringify(o.json).slice(0, 300));
    assert(run('e2e_run.js', [stub('F-001', 'ts'), '--app-url', appUrl]).code === 4, 'без rules');
  });

  await t('#34 e2e_run: guard прогона внутри теста (обёртка @playwright/test) — переход скриптом страницы наружу оборван и записан', async () => {
    const spec = path.join(E.run, 'drafts', 'e2e', 'F-009.spec.ts');
    fs.writeFileSync(spec, `import { test, expect } from '@playwright/test';
const APP_URL = process.env.APP_URL ?? 'file:///path/to/app/';
test('F-009: кнопка уводит из приложения', async ({ page }) => {
  await page.goto(new URL("index.html", APP_URL).href);
  await page.click('#leave');
  await page.waitForTimeout(500);
  expect(page.url(), 'файл вне каталога не открылся').not.toContain('local-outside');
});
`);
    // without the guard the page WOULD open: the target file exists next to the app folder
    fs.copyFileSync(path.join(FIX, 'local-outside.html'), path.join(E.run, 'local-outside.html'));
    const log = path.join(E.run, 'logs', 'blocked-e2e.jsonl');
    const r = run('e2e_run.js', [spec, '--rules', E.rules, '--app-url', appUrl, '--expect', 'pass', '--repeat-each', '1', '--log', log]);
    assert(r.code === 0 && r.json.ok, (r.json && (r.json.reason || r.json.error)) || r.err.slice(0, 300));
    assert(r.json.blocked.some(b => b.rule === 'base:file-outside-roots' && /local-outside/.test(b.url)), JSON.stringify(r.json.blocked));
    assert(readJsonl(log).some(e => e.rule === 'base:file-outside-roots'), 'нет записи в журнале');
  });

  await t('#34 e2e_run на http (локальный сервер, --base-url): заготовка из находки сайта падает на дефекте; чужой хост — код 3', async () => {
    const base = process.env.FIXTURE_BASE;
    if (!base) return 'skip';
    const H = path.join(TMP, 'run-e2e-http');
    fs.mkdirSync(path.join(H, 'drafts', 'e2e'), { recursive: true });
    fs.writeFileSync(path.join(H, 'run-config.yaml'), `site:\n  start_urls:\n    - ${base}/targets.html\n  allowed_domains:\n    - 127.0.0.1\n`);
    py([path.join(SKILL, 'scripts', 'url_guard.py'), 'export', '--config', path.join(H, 'run-config.yaml'), '--out', path.join(H, 'rules.json')]);
    fs.writeFileSync(path.join(H, 'findings.json'), JSON.stringify({ findings: [{ id: 'F-001', title: 'Мелкие кнопки', check_id: 'a11y.target-size', severity: 'low',
      url: base + '/targets.html', steps: ['Открыть страницу'], repro: { url: base + '/targets.html', js: "document.querySelectorAll('button').length > 0" } }] }));
    const spec = path.join(H, 'drafts', 'e2e', 'F-001.spec.ts');
    const s = py([path.join(SKILL, 'scripts', 'e2e_stub.py'), path.join(H, 'findings.json'), '--id', 'F-001', '--out', spec]);
    assert(s.status === 0 && /BASE_URL/.test(fs.readFileSync(spec, 'utf8')), s.stderr);
    const r = run('e2e_run.js', [spec, '--rules', path.join(H, 'rules.json'), '--base-url', base, '--expect', 'fail']);
    assert(r.code === 0 && r.json.ok && r.json.checked.every(c => c.ok), (r.json && (r.json.reason || r.json.error)) || r.err.slice(0, 300));
    const o = run('e2e_run.js', [spec, '--rules', path.join(H, 'rules.json'), '--base-url', 'https://example.com', '--expect', 'fail']);
    assert(o.code === 3, 'код ' + o.code + ' ' + JSON.stringify(o.json).slice(0, 200));
  });

  // ================= #34: Playwright MCP + file:// =================
  await t('#34 browser_mode.py mcp --check: отдельный Playwright MCP открывает file:// приложения, файл вне каталога блокирует guard (запись в журнале)', async () => {
    const M = makeRun('run-mcp');
    const r = py([path.join(SKILL, 'scripts', 'browser_mode.py'), 'mcp', M.run, '--check', '--json']);
    let j = null; try { j = JSON.parse(r.stdout); } catch { /* */ }
    assert(r.status === 0 && j && j.check.ok, (r.stdout + r.stderr).slice(-400));
    assert(j.check.inside.opened && /Локальное приложение/.test(j.check.inside.title || ''), JSON.stringify(j.check.inside));
    assert(j.check.outside[0].blocked && j.check.outside[0].rule === 'base:file-outside-roots', JSON.stringify(j.check.outside));
  });

  await t('#34 MCP без guard (тот же конфиг без initPage): файл вне каталога ОТКРЫВАЕТСЯ — поэтому guard в обёртке обязателен', async () => {
    const M = path.join(TMP, 'run-mcp');
    const cfg = JSON.parse(fs.readFileSync(path.join(M, 'playwright-mcp.json'), 'utf8'));
    delete cfg.browser.initPage;
    const bare = path.join(M, 'mcp-bare.json');
    fs.writeFileSync(bare, JSON.stringify(cfg));
    const outsideFile = path.join(M, 'outside.html');
    fs.writeFileSync(outsideFile, '<title>вне каталога</title><p>x</p>');
    const r = run('mcp_check.js', ['--config', bare, '--url', url(path.join(M, 'app', 'index.html')), '--outside', url(outsideFile)]);
    assert(r.code === 1 && r.json.inside.opened && r.json.outside[0].blocked === false, JSON.stringify(r.json));
  });

  // ================= #34: visible window (only with QA_HEADED=1: opens real windows) =================
  await t('#34 видимое окно (QA_HEADED=1): e2e_run --headed --slowmo и device_context --headed — браузер не headless', async () => {
    if (process.env.QA_HEADED !== '1') return 'skip';
    const spec = path.join(E.run, 'drafts', 'e2e', 'F-010.spec.ts');
    fs.writeFileSync(spec, `import { test, expect } from '@playwright/test';
const APP_URL = process.env.APP_URL ?? 'file:///path/to/app/';
test('F-010: окно видно', async ({ page }) => {
  await page.goto(new URL("index.html", APP_URL).href);
  expect(await page.evaluate(() => navigator.userAgent)).not.toContain('HeadlessChrome');
});
`);
    const r = run('e2e_run.js', [spec, '--rules', E.rules, '--app-url', appUrl, '--expect', 'pass', '--repeat-each', '1', '--headed', '--slowmo', '150'], { env: { SITE_QA_HEADLESS: '' } });
    assert(r.code === 0 && r.json.headed === true && r.json.slowMo === 150, JSON.stringify(r.json).slice(0, 300));
    const scen = path.join(E.run, 'ua.js');
    fs.writeFileSync(scen, 'module.exports = async ({ page }) => ({ ua: await page.evaluate(() => navigator.userAgent) });');
    const d = run('device_context.js', ['run', '--devices', 'desktop', '--url', E.index, '--rules', E.rules, '--scenario', scen, '--headed', '--slowmo', '100'], { env: { SITE_QA_HEADLESS: '' } });
    assert(d.code === 0 && !/HeadlessChrome/.test(d.json.results[0].data.ua), JSON.stringify(d.json).slice(0, 300));
  });

  console.log(`stream v1.5.0 browser: ${pass} PASS, ${fail} FAIL, ${skip} SKIP`);
  try { fs.rmSync(TMP, { recursive: true, force: true }); } catch { /* ignore */ }
  process.exit(fail ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
