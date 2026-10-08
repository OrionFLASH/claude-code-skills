'use strict';
// Stream B browser tests. Run through tests/test_stream_b.sh (it starts the fixture server and sets FIXTURE_BASE).
// Each command has positive and negative cases. Output: PASS/FAIL/SKIP lines, exit 1 on any FAIL.
const fs = require('fs');
const os = require('os');
const path = require('path');
const { spawnSync, spawn } = require('child_process');

const SKILL = path.resolve(__dirname, '..');
const NODE_DIR = path.join(SKILL, 'scripts', 'node');
const PY = process.platform === 'win32' ? 'python' : 'python3';
const B = process.env.FIXTURE_BASE;
if (!B) { console.error('FIXTURE_BASE не задан: запускайте через tests/test_stream_b.sh'); process.exit(2); }
const pw = require(path.join(NODE_DIR, 'node_modules', 'playwright'));
const guard = require(path.join(NODE_DIR, 'guard.js'));
const TMP = fs.mkdtempSync(path.join(os.tmpdir(), 'sqa-b-'));
const only = process.argv[2] ? new RegExp(process.argv[2]) : null;

let pass = 0, fail = 0, skip = 0;
const results = [];
async function t(name, fn) {
  if (only && !only.test(name)) return;
  try {
    const r = await fn();
    if (r === 'skip') { skip++; console.log('SKIP ' + name); }
    else { pass++; console.log('PASS ' + name); }
  } catch (e) { fail++; console.log('FAIL ' + name + ': ' + String(e && e.message || e).split('\n')[0]); }
}
function assert(c, msg) { if (!c) throw new Error(msg || 'assertion failed'); }
function run(script, args, opts = {}) {
  const r = spawnSync('node', [path.join(NODE_DIR, script), ...args], { encoding: 'utf8', timeout: opts.timeout || 180000, cwd: opts.cwd });
  let json = null; try { json = JSON.parse(r.stdout); } catch { /* not JSON */ }
  return { code: r.status, out: r.stdout, err: r.stderr, json };
}
const readJsonl = (f) => fs.existsSync(f) ? fs.readFileSync(f, 'utf8').trim().split('\n').filter(Boolean).map(JSON.parse) : [];

function exportRules(cfg, out) {
  const r = spawnSync(PY, [path.join(SKILL, 'scripts', 'url_guard.py'), 'export', '--config', cfg, '--out', out], { encoding: 'utf8' });
  if (r.status !== 0) throw new Error('url_guard export: ' + r.stderr);
  return out;
}

const webkitOk = (() => { const r = spawnSync('node', [path.join(NODE_DIR, 'probe.js'), 'webkit'], { encoding: 'utf8' }); try { return JSON.parse(r.stdout).webkit.ok; } catch { return false; } })();

// Chromium with a CDP port stands in for «the user's browser» (auth: manual-cdp).
async function startCdpBrowser() {
  const port = 9300 + Math.floor(Math.random() * 500);
  const proc = spawn(pw.chromium.executablePath(), ['--headless=new', `--remote-debugging-port=${port}`, `--user-data-dir=${path.join(TMP, 'profile-' + port)}`,
    '--no-first-run', '--no-default-browser-check', 'about:blank'], { stdio: 'ignore' });
  const url = `http://127.0.0.1:${port}`;
  for (let i = 0; i < 50; i++) {
    try { const r = await fetch(url + '/json/version'); if (r.ok) break; } catch { /* starting */ }
    await new Promise(r => setTimeout(r, 200));
  }
  return { url, stop: () => new Promise(res => { proc.once('exit', res); proc.kill(); setTimeout(res, 3000); }) };
}

(async () => {
  const guardRules = exportRules(path.join(__dirname, 'fixtures', 'guard.run-config.yaml'), path.join(TMP, 'rules.json'));
  const rules = guard.loadGuardRules(guardRules);

  // ---------------- guard.js ----------------
  await t('guard: «Поддержать» не нажата, событие deny в blocked.jsonl (user:forbidden_actions:U1)', async () => {
    const log = path.join(TMP, 'blocked-1.jsonl');
    const browser = await pw.chromium.launch();
    try {
      const ctx = await browser.newContext();
      await guard.guardContext(ctx, rules, { logFile: log });
      const page = await ctx.newPage();
      const g = guard.guardedPage(page, rules, { logFile: log, throttleMs: 0 });
      await g.goto(B + '/guard-actions.html', { waitUntil: 'load' });
      const r = await g.click('#donate');
      assert(!r.performed && r.decision === 'deny', JSON.stringify(r));
      assert(r.rule === 'user:forbidden_actions:U1', r.rule);
      assert((await page.textContent('#out')) === '', 'клик выполнен');
      assert(readJsonl(log).some(e => e.type === 'action' && e.decision === 'deny' && e.element.text === 'Поддержать'), 'нет события в журнале');
    } finally { await browser.close(); }
  });

  await t('guard: запрос к запрещённому домену заблокирован на уровне route (resource + nav)', async () => {
    const log = path.join(TMP, 'blocked-2.jsonl');
    const browser = await pw.chromium.launch();
    try {
      const ctx = await browser.newContext();
      await guard.guardContext(ctx, rules, { logFile: log });
      const page = await ctx.newPage();
      await page.goto(B + '/guard-actions.html', { waitUntil: 'load' });
      // Raw page.goto (not the wrapper) must be stopped by the route itself.
      let err = null; try { await page.goto('http://sibling.example/', { timeout: 10000 }); } catch (e) { err = e; }
      assert(err && /ERR_BLOCKED_BY_CLIENT/.test(err.message), 'навигация не заблокирована: ' + (err && err.message));
      const ev = readJsonl(log);
      assert(ev.some(e => e.type === 'resource' && /ads\.blocked\.example/.test(e.url)), 'ресурс не заблокирован');
      assert(ev.some(e => e.type === 'nav' && /sibling\.example/.test(e.url)), 'нет nav-события');
    } finally { await browser.close(); }
  });

  await t('guard: вкладка на чужой домен закрыта, ссылка на запрещённый адрес не нажата, × требует подтверждения', async () => {
    const log = path.join(TMP, 'blocked-3.jsonl');
    const browser = await pw.chromium.launch();
    try {
      const ctx = await browser.newContext();
      await guard.guardContext(ctx, rules, { logFile: log });
      const page = await ctx.newPage();
      const g = guard.guardedPage(page, rules, { logFile: log, throttleMs: 0 });
      await g.goto(B + '/guard-actions.html', { waitUntil: 'load' });
      const link = await g.click('#ext');
      assert(!link.performed && link.decision === 'deny', 'ссылка: ' + JSON.stringify(link));
      const popup = await g.click('#popup');
      assert(popup.performed, 'кнопка промо должна нажиматься');
      await page.waitForTimeout(1200);
      assert(ctx.pages().length === 1, 'вкладка не закрыта: ' + ctx.pages().map(p => p.url()));
      assert(readJsonl(log).some(e => e.type === 'tab'), 'нет события tab');
      let confirmErr = null; try { await g.click('#del'); } catch (e) { confirmErr = e; }
      assert(confirmErr && confirmErr.name === 'GuardConfirmError' && /подтвержд/.test(confirmErr.question), 'нет вопроса на ×');
    } finally { await browser.close(); }
  });

  await t('guard (негативный): разрешённые действия выполняются — клик «Показать карту», ввод в поле сообщения', async () => {
    const browser = await pw.chromium.launch();
    try {
      const ctx = await browser.newContext();
      await guard.guardContext(ctx, rules, {});
      const page = await ctx.newPage();
      const g = guard.guardedPage(page, rules, { throttleMs: 0 });
      await g.goto(B + '/guard-actions.html', { waitUntil: 'load' });
      assert((await g.click('#safe')).performed, 'клик не выполнен');
      assert((await page.textContent('#out')) === 'clicked-safe');
      assert((await g.fill('#msg', 'тест')).performed, 'ввод не выполнен');
    } finally { await browser.close(); }
  });

  await t('guard: решения моста совпадают с url_guard.py action', async () => {
    const cases = [['Купить', null, null], ['Поддержать', null, 'button'], ['Найти', 'Поиск по сайту', null], ['Удалить', null, null], ['Google', 'Войдите через Google', 'button']];
    for (const [text, context, role] of cases) {
      const js = await guard.checkAction(rules, { text, context, role });
      const args = [path.join(SKILL, 'scripts', 'url_guard.py'), 'action', '--text', text, '--config', path.join(__dirname, 'fixtures', 'guard.run-config.yaml')];
      if (context) args.push('--context', context);
      if (role) args.push('--role', role);
      const py = JSON.parse(spawnSync(PY, args, { encoding: 'utf8' }).stdout);
      assert(js.decision === py.decision && js.rule === py.rule, `${text}: ${js.decision}/${js.rule} != ${py.decision}/${py.rule}`);
    }
  });

  await t('guard fail closed (S-2): мост недоступен -> GuardUnavailableError, клик и переход не выполнены, событие unavailable', async () => {
    const log = path.join(TMP, 'blocked-unavail.jsonl');
    const browser = await pw.chromium.launch();
    process.env.SITE_QA_GUARD_PY_DIR = path.join(TMP, 'no-such-scripts-dir');
    try {
      const d = await guard.checkAction(rules, { text: 'Показать карту' });
      assert(d.decision === 'unavailable' && d.rule === 'guard:unavailable', JSON.stringify(d));
      const ctx = await browser.newContext();
      const page = await ctx.newPage();
      await page.goto(B + '/guard-actions.html');
      const g = guard.guardedPage(page, rules, { logFile: log, throttleMs: 0 });
      let e1 = null; try { await g.click('#safe'); } catch (e) { e1 = e; }
      assert(e1 && e1.name === 'GuardUnavailableError' && e1.exitCode === 4, 'click: ' + (e1 && e1.message));
      assert((await page.textContent('#out')) === '', 'клик выполнен при недоступном guard');
      let e2 = null; try { await g.goto(B + '/reach-scroll.html'); } catch (e) { e2 = e; }
      assert(e2 && e2.exitCode === 4 && /guard-actions/.test(page.url()), 'goto: ' + (e2 && e2.message) + ' ' + page.url());
      assert(readJsonl(log).filter(e => e.decision === 'unavailable').length === 2, 'нет событий unavailable');
    } finally { delete process.env.SITE_QA_GUARD_PY_DIR; await browser.close(); }
    const missing = run('guard.js', ['check', '--url', B + '/guard-actions.html', '--selector', '#safe', '--rules', path.join(TMP, 'missing-rules.json')]);
    assert(missing.code === 4 && /guard недоступен/.test(missing.err), 'нет rules.json -> код ' + missing.code + ' ' + missing.err);
    const shotMissing = run('shot.js', ['--url', B + '/guard-actions.html', '--rules', path.join(TMP, 'missing-rules.json'), '--out', path.join(TMP, 'x.png'), 'body|x']);
    assert(shotMissing.code === 4, 'shot.js без rules.json -> код ' + shotMissing.code);
  });

  await t('guard read-only (S-8): /donate/ открывается только с readOnly, клики и POST запрещены; без readOnly — deny', async () => {
    const log = path.join(TMP, 'blocked-ro.jsonl');
    const browser = await pw.chromium.launch();
    try {
      const ctx = await browser.newContext();
      await guard.guardContext(ctx, rules, { logFile: log, readOnly: true });
      const page = await ctx.newPage();
      const g = guard.guardedPage(page, rules, { logFile: log, throttleMs: 0, readOnly: true });
      const nav = await g.goto(B + '/donate/', { waitUntil: 'load' });
      assert(nav.performed && nav.readOnly, JSON.stringify(nav));
      assert(/199/.test(await page.textContent('#price')), 'страница не прочитана');
      await page.waitForFunction(() => document.getElementById('out').dataset.post);
      assert((await page.getAttribute('#out', 'data-post')) === 'blocked', 'POST ушёл в режиме только чтения');
      const c = await g.click('#ping');
      assert(!c.performed && c.rule === 'read-only' && (await page.textContent('#out')) === '', JSON.stringify(c));
      const ev = readJsonl(log);
      assert(ev.some(e => e.type === 'read-only' && e.reason === 'прочитано без действий') && ev.some(e => e.rule === 'read-only' && /POST/.test(e.reason)), JSON.stringify(ev));
      const ctx2 = await browser.newContext();
      await guard.guardContext(ctx2, rules, {});
      const p2 = await ctx2.newPage();
      const g2 = guard.guardedPage(p2, rules, { throttleMs: 0 });
      const n2 = await g2.goto(B + '/donate/');
      assert(!n2.performed && n2.rule === 'base:nav-path', JSON.stringify(n2));
    } finally { await browser.close(); }
  });

  await t('guard.js check (CLI): «Поддержать» -> код 3, «Показать карту» -> код 0', async () => {
    const d = run('guard.js', ['check', '--url', B + '/guard-actions.html', '--selector', '#donate', '--rules', guardRules]);
    assert(d.code === 3, 'код ' + d.code + ' ' + d.err);
    const s = run('guard.js', ['check', '--url', B + '/guard-actions.html', '--selector', '#safe', '--rules', guardRules]);
    assert(s.code === 0, 'код ' + s.code + ' ' + s.err);
  });

  // ---------------- occlusion.js ----------------
  await t('occlusion: кнопка 44×44 над 40×40 -> ровно одна пара 36×20, z-index 1250', async () => {
    const r = run('occlusion.js', [B + '/occlusion-overlap.html', '--sizes', '1440x813']);
    const pairs = r.json.runs[0].pairs;
    assert(pairs.length === 1, 'пар: ' + pairs.length);
    const p = pairs[0];
    assert(p.area.w === 36 && p.area.h === 20, JSON.stringify(p.area));
    assert(p.occluded.selector === '#whole-map' && p.occluder.selector === '#bell' && p.occluder.zIndex === 1250, JSON.stringify(p));
  });

  await t('occlusion (негативный): прокручиваемый список под закреплённой панелью -> 0 срабатываний (3 размера + pixel7)', async () => {
    const r = run('occlusion.js', [B + '/occlusion-scroll-list.html', '--sizes', '1440x813,1024x768,720x450', '--device', 'pixel7']);
    for (const x of r.json.runs) {
      assert(!x.error, x.error);
      assert(x.pairs.length === 0, `${x.config}: ${x.pairs.length} пар`);
      assert(x.checked > 5, `${x.config}: проверено ${x.checked}`);
    }
  });

  await t('occlusion --frames all: пара внутри iframe со смещением кадра и перекрытие кадра тостом страницы', async () => {
    const r = run('occlusion.js', [B + '/iframe-app.html', '--sizes', '1280x720', '--frames', 'all']);
    const pairs = r.json.runs[0].pairs;
    const inFrame = pairs.find(p => p.occluded.selector === '#save' && !p.crossFrame);
    assert(inFrame && inFrame.occluded.box.join() === '135,175,40,40' && inFrame.area.w === 20 && inFrame.area.h === 20, JSON.stringify(inFrame));
    assert(pairs.some(p => p.crossFrame && p.occluded.selector === '#calc' && p.occluder.selector === '#toast'), 'нет межкадровой пары');
  });

  await t('occlusion --frames main (негативный): содержимое iframe не проверяется', async () => {
    const r = run('occlusion.js', [B + '/iframe-app.html', '--sizes', '1280x720', '--frames', 'main']);
    assert(r.json.runs[0].pairs.length === 0, 'пар: ' + r.json.runs[0].pairs.length);
  });

  // ---------------- reachability.js ----------------
  await t('reachability: панель выше окна, корень overflow:hidden, 863×360 -> «недостижим»', async () => {
    const r = run('reachability.js', [B + '/reach-hidden.html', '--sizes', '863x360', '--device', 'pixel7-landscape']);
    for (const x of r.json.runs) {
      const it = x.items.find(i => i.name === 'Только ненайденные');
      assert(it && it.verdict === 'недостижим' && it.wheel === false && it.gesture === false, `${x.config}: ${JSON.stringify(it)}`);
    }
  });

  await t('reachability (негативный): та же панель с overflow-y:auto -> «достижим»', async () => {
    const r = run('reachability.js', [B + '/reach-scroll.html', '--sizes', '863x360', '--device', 'pixel7-landscape']);
    for (const x of r.json.runs) {
      const it = x.items.find(i => i.name === 'Только ненайденные');
      assert(it && it.verdict === 'достижим', `${x.config}: ${JSON.stringify(it)}`);
    }
    const tall = run('reachability.js', [B + '/reach-hidden.html', '--device', 'pixel7']);
    assert(tall.json.runs[0].items.length === 0, 'в портрете Pixel 7 панель помещается, кандидатов быть не должно');
  });

  // ---------------- device_context.js ----------------
  await t('device_context list: Pixel 7 412×839, iPad 810×1080 WebKit, landscape 863×360', async () => {
    const r = run('device_context.js', ['list']);
    const d = Object.fromEntries(r.json.devices.map(x => [x.name, x]));
    assert(d.pixel7.viewport === '412x839' && d.ipad.viewport === '810x1080' && d.ipad.engine === 'webkit' && d['pixel7-landscape'].viewport === '863x360', JSON.stringify(d));
  });

  await t('device_context run: один сценарий на списке устройств (последовательно)', async () => {
    const devs = webkitOk ? 'pixel7,ipad,360x640' : 'pixel7,360x640';
    const r = run('device_context.js', ['run', '--devices', devs, '--url', B + '/guard-actions.html', '--rules', guardRules]);
    const res = r.json.results;
    assert(res.length === devs.split(',').length && res.every(x => !x.error), JSON.stringify(res));
    assert(res[0].viewport.width === 412 && res[0].data.innerWidth === 412, JSON.stringify(res[0]));
    if (webkitOk) assert(res[1].engine === 'webkit' && res[1].data.innerWidth === 810, JSON.stringify(res[1]));
  });

  await t('device_context (негативный): неизвестное устройство -> ошибка с перечнем имён, другие устройства не запускаются', async () => {
    const r = run('device_context.js', ['run', '--devices', 'nokia3310', '--url', B + '/guard-actions.html']);
    assert(r.json && r.json.results[0].error && /неизвестное устройство/.test(r.json.results[0].error), r.out + r.err);
  });

  let cdp = null;
  if (!only || only.test('device_context state') || only.test('shot --cdp')) { try { cdp = await startCdpBrowser(); } catch { cdp = null; } }
  await t('device_context state (manual-cdp): только cookie allowed_domains, localStorage/sessionStorage сайта, файл 600, ничего не очищено, state-rm', async () => {
    if (!cdp) return 'skip';
    const b = await pw.chromium.connectOverCDP(cdp.url);
    const ctx = b.contexts()[0];
    const page = ctx.pages()[0] || await ctx.newPage();
    await page.goto(B + '/guard-actions.html');
    await ctx.addCookies([{ name: 'session', value: 'secret-value', url: B },
      { name: 'foreign', value: 'other-secret', domain: '.mail.example', path: '/' },
      { name: 'foreign2', value: 'x', domain: 'search.example', path: '/' }]);
    await page.evaluate(() => { localStorage.setItem('k', 'v'); sessionStorage.setItem('lang', 'ru'); });
    const out = path.join(TMP, 'auth-state.json');
    const no = run('device_context.js', ['state', '--cdp', cdp.url, '--out', path.join(TMP, 'nofilter.json')]);
    assert(no.code !== 0 && /фильтр доменов/.test(no.err) && !fs.existsSync(path.join(TMP, 'nofilter.json')), 'без фильтра доменов файл записан: ' + no.err);
    const r = run('device_context.js', ['state', '--cdp', cdp.url, '--out', out, '--domains', '127.0.0.1']);
    assert(r.code === 0 && r.json.cookies === 1 && r.json.dropped === 2, r.out + r.err);
    assert(r.json.origins === 1 && r.json.sessionStorage === 1 && r.json.domains.join() === '127.0.0.1', r.out);
    assert(!/secret-value|other-secret|mail\.example/.test(r.out + r.err), 'значение или чужой домен попали в вывод');
    assert(/секрет/.test(r.err) && /state-rm/.test(r.err), 'нет предупреждения о секрете');
    if (process.platform !== 'win32') assert((fs.statSync(out).mode & 0o777) === 0o600, 'права файла');
    const saved = JSON.parse(fs.readFileSync(out, 'utf8'));
    assert(saved.cookies.every(c => c.domain === '127.0.0.1') && saved.origins[0].localStorage.some(x => x.name === 'k'), JSON.stringify(saved).slice(0, 300));
    const after = await ctx.cookies(B);
    assert(after.some(c => c.name === 'session'), 'cookie пользователя пропала');
    assert((await page.evaluate(() => localStorage.getItem('k'))) === 'v', 'localStorage очищен');
    // The emulated device gets the login (cookie, localStorage and sessionStorage); --delete-state removes the file.
    const scen = path.join(TMP, 'scen.js');
    fs.writeFileSync(scen, 'module.exports = async ({ page }) => ({ c: await page.evaluate(() => document.cookie), l: await page.evaluate(() => localStorage.getItem("k")), s: await page.evaluate(() => sessionStorage.getItem("lang")) });');
    const copy = path.join(TMP, 'auth-copy.json'); fs.copyFileSync(out, copy);
    const d = run('device_context.js', ['run', '--devices', 'pixel7', '--url', B + '/guard-actions.html', '--state', copy, '--delete-state', '--scenario', scen]);
    const res0 = d.json.results[0];
    assert(res0.auth === 'storageState' && /session=/.test(res0.data.c) && res0.data.l === 'v' && res0.data.s === 'ru', JSON.stringify(d.json));
    assert(!fs.existsSync(copy) && d.json.stateDeleted, 'файл состояния не удалён после run --delete-state');
    const d2 = run('device_context.js', ['run', '--devices', 'pixel7', '--url', B + '/guard-actions.html', '--cdp', cdp.url, '--scenario', scen]);
    assert(d2.json.results[0].auth === 'storageState' && /session=/.test(d2.json.results[0].data.c), JSON.stringify(d2.json));
    const rm = run('device_context.js', ['state-rm', '--out', out]);
    assert(rm.json.removed === true && !fs.existsSync(out), 'state-rm: ' + rm.out);
    await b.close();
  });

  await t('device_context media (S-4): телефон — pointer:coarse; WxH — десктоп с предупреждением; WxH@mobile — касания', async () => {
    const r = run('device_context.js', ['media', '--devices', 'pixel7,412x915,412x915@mobile']);
    const m = Object.fromEntries(r.json.media.map(x => [x.device, x]));
    assert(m.pixel7.pointerCoarse && m.pixel7.touchValid && m.pixel7.expectsTouch, JSON.stringify(m.pixel7));
    assert(!m['412x915'].pointerCoarse && !m['412x915'].touchValid && /WxH@mobile/.test(m['412x915'].warning), JSON.stringify(m['412x915']));
    assert(m['412x915@mobile'].pointerCoarse && m['412x915@mobile'].hoverNone && m['412x915@mobile'].maxTouchPoints >= 1, JSON.stringify(m['412x915@mobile']));
  });

  // ---------------- invariants.js ----------------
  const seCfg = path.join(__dirname, 'fixtures', 'side-effects.run-config.yaml');
  const saveFile = path.join(TMP, 'save.sl2'); fs.writeFileSync(saveFile, 'save');
  const inv = (variant, dir, cfg = seCfg, extra = []) => run('invariants.js', ['exec', '--config', cfg, '--effect', 'SE1', '--url', `${B}/upload-guard.html?variant=${variant}`,
    '--run-dir', dir, '--file', saveFile, ...extra]);

  await t('invariants: защитный чекбокс не появился за 2000 мс -> остановка (код 3) и запись в side_effects.md', async () => {
    const dir = path.join(TMP, 'run-missing');
    const r = inv('missing', dir);
    assert(r.code === 3 && r.json.status === 'aborted', r.out + r.err);
    assert(/Прогон остановлен/.test(r.err), 'нет предупреждения');
    const md = fs.readFileSync(path.join(dir, 'side_effects.md'), 'utf8');
    assert(/ОСТАНОВЛЕНО/.test(md) && /не появился за 2000 мс/.test(md) && /локальная копия/.test(md), md);
  });

  await t('invariants (негативный): чекбокс появился через 1 с и отмечен -> код 0, запись «выполнено»', async () => {
    const dir = path.join(TMP, 'run-ok');
    const r = inv('ok', dir);
    assert(r.code === 0 && r.json.status === 'ok', r.out + r.err);
    assert(/выполнено, инварианты соблюдены/.test(fs.readFileSync(path.join(dir, 'side_effects.md'), 'utf8')));
    const v = JSON.parse(fs.readFileSync(path.join(dir, 'vocabulary.json'), 'utf8'));
    assert(v.INV1.observed === 'Чужое сохранение', JSON.stringify(v));
  });

  await t('invariants: появился, но не отмечен -> остановка; с ensure: true раннер отмечает сам', async () => {
    const r = inv('unchecked', path.join(TMP, 'run-unchecked'));
    assert(r.code === 3, r.out);
    const cfg2 = path.join(TMP, 'se-ensure.yaml');
    fs.writeFileSync(cfg2, fs.readFileSync(seCfg, 'utf8').replace('state: checked', 'state: checked\n      ensure: true'));
    const r2 = inv('unchecked', path.join(TMP, 'run-ensure'), cfg2);
    assert(r2.code === 0 && r2.json.status === 'ok', r2.out + r2.err);
  });

  await t('invariants: словарь — старое название «Чужой сейв» -> код 2 и вопрос; переименованный элемент -> остановка', async () => {
    const cfg3 = path.join(TMP, 'se-vocab.yaml');
    fs.writeFileSync(cfg3, fs.readFileSync(seCfg, 'utf8').replace('vocabulary: "Чужое сохранение"', 'vocabulary: "Чужой сейв"'));
    const r = inv('ok', path.join(TMP, 'run-vocab'), cfg3);
    assert(r.code === 2 && r.json.status === 'vocabulary-changed' && /Чужой сейв/.test(r.json.questions[0]), r.out);
    const prev = path.join(TMP, 'run-ok', 'vocabulary.json');
    const r2 = inv('renamed', path.join(TMP, 'run-renamed'), seCfg, ['--prev-vocab', prev]);
    assert(r2.code === 3, r2.out);
  });

  await t('invariants preflight: элемент есть до действия -> остановка до загрузки (код 2), файл не загружен', async () => {
    const dir = path.join(TMP, 'run-early');
    const r = inv('early', dir);
    assert(r.code === 2 && r.json.status === 'stopped-preflight', r.out);
    assert(/НЕ выполнено/.test(fs.readFileSync(path.join(dir, 'side_effects.md'), 'utf8')));
    const p = run('invariants.js', ['preflight', '--config', seCfg, '--url', `${B}/upload-guard.html?variant=ok`, '--run-dir', path.join(TMP, 'run-pf')]);
    assert(p.code === 0 && p.json.ok, 'preflight ok: ' + p.out);
  });

  await t('invariants: guardedPage не даёт загрузить файл в цель побочного эффекта в обход раннера; log дописывает строку', async () => {
    const browser = await pw.chromium.launch();
    try {
      const page = await browser.newPage();
      const cfg = JSON.parse(spawnSync(PY, [path.join(SKILL, 'scripts', 'shared', 'miniyaml.py'), seCfg], { encoding: 'utf8' }).stdout);
      const g = guard.guardedPage(page, null, { throttleMs: 0, sideEffects: cfg.side_effects, confirmMode: 'return' });
      await page.goto(B + '/upload-guard.html');
      const r = await g.setInputFiles('#upload', saveFile);
      assert(!r.performed && r.rule === 'side_effect:SE1', JSON.stringify(r));
      assert((await page.textContent('#status')) === '', 'файл загружен');
    } finally { await browser.close(); }
    const dir = path.join(TMP, 'run-log');
    const l = run('invariants.js', ['log', '--run-dir', dir, '--what', 'включён «Запомнить»', '--left', 'локальная копия сохранения']);
    assert(l.code === 0 && /Запомнить/.test(fs.readFileSync(path.join(dir, 'side_effects.md'), 'utf8')));
  });

  // ---------------- shot.js ----------------
  const shots = path.join(TMP, 'shots');
  await t('shot: снимок + разметка в одном вызове, авто-avoid соседей, автопроверка пройдена', async () => {
    const r = run('shot.js', ['--url', B + '/occlusion-overlap.html', '--size', '1440x813', '--out', path.join(shots, 'F-001-bell.png'),
      '#bell|Колокольчик закрывает «Вся карта»|error', '#ok-a|@avoid', 'rect:150,15,140,50|@avoid']);
    assert(r.code === 0 && r.json.ok && r.json.items.length === 1 && fs.existsSync(r.json.annotated), r.out + r.err);
    assert(r.json.autoAvoid >= 1, 'соседи не добавлены');
    const spec = JSON.parse(fs.readFileSync(r.json.spec, 'utf8'));
    assert(spec.avoid.length >= 3 && spec.items[0].box.join() === '1380,753,44,44', JSON.stringify(spec));
  });

  await t('shot: селектор внутри iframe -> координаты со смещением кадра', async () => {
    const r = run('shot.js', ['--url', B + '/iframe-app.html', '--size', '1280x720', '--out', path.join(shots, 'F-002-frame.png'), 'iframe#app >>> #save|Под «?»|error']);
    const spec = JSON.parse(fs.readFileSync(r.json.spec, 'utf8'));
    assert(spec.items[0].box.join() === '135,175,40,40', JSON.stringify(spec.items));
  });

  await t('shot (негативный): цель не найдена -> предупреждение, аннотированный файл не создаётся', async () => {
    const r = run('shot.js', ['--url', B + '/occlusion-overlap.html', '--size', '1440x813', '--out', path.join(shots, 'F-003-none.png'), '#nope|нет такого']);
    assert(r.code === 0 && !r.json.annotated && /не найдены: #nope/.test(r.json.warnings.join()), r.out);
    const g = run('shot.js', ['--url', 'http://sibling.example/', '--rules', guardRules, '--out', path.join(shots, 'F-004.png'), 'body|x']);
    assert(g.code === 1 && /переход запрещён/.test(g.err), 'запрещённый URL снят: ' + g.err);
  });

  await t('shot --batch + контактный лист; sheet отдельно', async () => {
    const batch = path.join(TMP, 'shots.json');
    fs.writeFileSync(batch, JSON.stringify([
      { name: 'S-1', url: B + '/occlusion-overlap.html', size: '1440x813', targets: ['#bell|Колокольчик|error'] },
      { name: 'S-2', url: B + '/iframe-app.html', size: '1280x720', targets: ['iframe#app >>> #calc|Под тостом|question'] },
      { name: 'S-3', url: B + '/reach-hidden.html', device: 'pixel7-landscape', targets: ['#layers|Панель выше окна|note'] },
    ]));
    const r = run('shot.js', ['--batch', batch, '--dir', shots, '--json', path.join(TMP, 'batch.json')]);
    const j = JSON.parse(fs.readFileSync(path.join(TMP, 'batch.json'), 'utf8'));
    assert(j.results.length === 3 && j.results.every(x => x.annotated) && j.sheets.length === 1 && fs.existsSync(j.sheets[0]), r.err + JSON.stringify(j));
    const s = run('shot.js', ['sheet', '--out', path.join(TMP, 'sheet.png'), '--per', '2', ...j.results.map(x => x.annotated)]);
    assert(s.json.sheets.length === 2, s.out + s.err);
  });

  await t('shot --cdp: снимок открытой вкладки пользователя без перехода и без очистки cookies', async () => {
    if (!cdp) return 'skip';
    const b = await pw.chromium.connectOverCDP(cdp.url);
    const ctx = b.contexts()[0];
    const page = ctx.pages()[0];
    await page.goto(B + '/occlusion-overlap.html');
    await page.setViewportSize({ width: 1440, height: 813 });
    const before = (await ctx.cookies(B)).length;
    const r = run('shot.js', ['--cdp', cdp.url, '--page-match', 'occlusion-overlap', '--out', path.join(shots, 'F-005-cdp.png'), '#bell|Через CDP|error']);
    assert(r.code === 0 && r.json.annotated, r.out + r.err);
    assert(page.url().endsWith('/occlusion-overlap.html'), 'вкладка ушла: ' + page.url());
    assert((await ctx.cookies(B)).length === before, 'cookies изменились');
    const w = spawnSync('node', [path.join(SKILL, 'scripts', 'snap_cdp.js'), '--cdp', cdp.url, '--page-match', 'occlusion-overlap', '--out', path.join(shots, 'F-006-snapcdp.png'), '#bell|snap_cdp|note'], { encoding: 'utf8' });
    assert(w.status === 0 && JSON.parse(w.stdout).annotated, 'snap_cdp: ' + w.stderr);
    await b.close();
  });
  if (cdp) await cdp.stop();

  // ---------------- frames in detectors ----------------
  await t('a11y.js --frames all: текст и проверки iframe; --frames main (негативный): кадр исключён', async () => {
    const all = run('a11y.js', [B + '/iframe-app.html', '--throttle', '0']).json.results[0];
    assert(all.text.frames.length === 1 && all.text.frames[0].chars > all.text.main && all.note, JSON.stringify(all.text));
    const main = run('a11y.js', [B + '/iframe-app.html', '--throttle', '0', '--frames', 'main']).json.results[0];
    assert(main.text.frames.length === 0, JSON.stringify(main.text));
  });

  await t('links.js --frames all: документ iframe обойдён; без флага (негативный) — нет', async () => {
    const a = run('links.js', [B + '/iframe-app.html', '--frames', 'all', '--throttle', '0', '--max-pages', '5']).json;
    assert(a.pages.some(p => /iframe-inner/.test(p.url) && p.frameOf), JSON.stringify(a.pages.map(p => p.url)));
    const n = run('links.js', [B + '/iframe-app.html', '--throttle', '0', '--max-pages', '5']).json;
    assert(!n.pages.some(p => /iframe-inner/.test(p.url)));
  });

  if (!webkitOk) { skip++; console.log('SKIP WebKit недоступен: проверки iPad/iPhone в WebKit пропущены'); }
  try { fs.rmSync(TMP, { recursive: true, force: true, maxRetries: 5, retryDelay: 300 }); } catch (e) { console.log('NOTE не удалось удалить ' + TMP + ': ' + e.code); }
  console.log(`\nstream B: ${pass} PASS, ${fail} FAIL, ${skip} SKIP`);
  process.exit(fail ? 1 : 0);
})().catch(e => { console.error(e); try { fs.rmSync(TMP, { recursive: true, force: true, maxRetries: 5 }); } catch { /* ignore */ } process.exit(1); });
