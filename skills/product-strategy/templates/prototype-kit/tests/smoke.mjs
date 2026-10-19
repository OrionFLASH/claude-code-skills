// Смоук рабочего прототипа в браузере (Playwright, без установки в прототип): открывает index.html по file://,
// проходит все режимы в светлой и тёмной теме, снимает PNG и проверяет:
//   - нет ошибок консоли и необработанных исключений;
//   - нет внешних запросов (разрешены file:, data:, blob:, about:) — запросы наружу блокируются и считаются ошибкой;
//   - есть бейджи «Концепт продукта…» и «демо-данные»; переключатель режимов; каждый режим рисует непустой экран;
//   - тема переключается (data-theme light → dark); цели нажатия ≥ 32 px (мышь) и ≥ 44 px (тач, 390×844).
// Запуск: node tests/smoke.mjs [--webkit] [--mode <id>] [--no-shots] [--node-dir DIR]
// Результат: shots/smoke-results.json (+ shots/<браузер>-<режим>-<тема>.png). Пишет только в shots/ своего прототипа.
// Код выхода: 0 — всё прошло; 1 — есть замечания; 3 — нет playwright/браузера.
// Модули: --node-dir | $PS_NODE_DIR | <OUT>/build/node | ~/.cache/product-strategy/node | node_modules прототипа.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { createRequire } from 'node:module';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const PROTO = path.resolve(HERE, '..');
const args = process.argv.slice(2);
const opt = { webkit: args.includes('--webkit'), shots: !args.includes('--no-shots') };
for (let i = 0; i < args.length; i++) {
  if (args[i] === '--mode') opt.mode = args[++i];
  if (args[i] === '--node-dir') opt.nodeDir = args[++i];
}

function loadPlaywright() {
  const home = process.env.HOME || process.env.USERPROFILE || '';
  const cands = opt.nodeDir ? [opt.nodeDir] : [process.env.PS_NODE_DIR, path.join(PROTO, '..', 'build', 'node'),
    path.join(home, '.cache', 'product-strategy', 'node'), PROTO].filter(Boolean);
  for (const d of cands) {
    const p = path.join(path.resolve(d), 'node_modules', 'playwright');
    if (fs.existsSync(path.join(p, 'package.json'))) {
      try { return createRequire(import.meta.url)(p); } catch { /* следующий кандидат */ }
    }
  }
  return null;
}

const pw = loadPlaywright();
if (!pw) {
  console.error('нет playwright: установите модули скилла (check_env.py --install-node <OUT>) или укажите --node-dir');
  process.exit(3);
}

const url = pathToFileURL(path.join(PROTO, 'index.html')).href;
const shotsDir = path.join(PROTO, 'shots');
if (opt.shots) fs.mkdirSync(shotsDir, { recursive: true });
const results = { url: 'index.html', browsers: [], problems: [] };
const problem = (b, msg) => results.problems.push(`${b}: ${msg}`);

async function smallTargets(page, min) {
  return page.$$eval('button, a[href], input, select, summary, [role="tab"]', (els, m) => els
    .filter((e) => { const r = e.getBoundingClientRect(); const s = getComputedStyle(e); return r.width > 0 && r.height > 0 && r.right > 0 && r.bottom > 0 && r.left < innerWidth && s.visibility !== 'hidden'; })
    .map((e) => { const r = e.getBoundingClientRect(); return { t: (e.textContent || e.getAttribute('aria-label') || e.id || e.tagName).trim().slice(0, 40), h: Math.round(r.height), w: Math.round(r.width) }; })
    .filter((x) => x.h < m || (x.w < m && x.t.length <= 2)), min);
}

async function run(name, type) {
  let browser;
  try { browser = await type.launch(); } catch (e) {
    if (name === 'webkit') { problem(name, `браузер не запустился (${String(e.message).split('\n')[0]}) — проверка пропущена`); return; }
    console.error(`нет браузера ${name}: ${String(e.message).split('\n')[0]}`); process.exit(3);
  }
  const rec = { name, modes: [], errors: [], external: [] };
  for (const touch of [false, true]) {
    const ctx = await browser.newContext(touch ? { viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: name !== 'firefox' } : { viewport: { width: 1280, height: 860 } });
    const page = await ctx.newPage();
    page.on('console', (m) => { if (m.type() === 'error') rec.errors.push(m.text()); });
    page.on('pageerror', (e) => rec.errors.push(String(e.message || e)));
    await page.route('**/*', (route) => {
      const u = route.request().url();
      if (/^(file|data|blob|about):/.test(u)) return route.continue();
      rec.external.push(u); return route.abort();
    });
    await page.goto(url);
    await page.waitForSelector('#pk-view');
    if (!touch) {
      const concept = await page.locator('.pk-badge-concept').innerText().catch(() => '');
      const demo = await page.locator('#pk-demo').innerText().catch(() => '');
      if (!/Концепт/.test(concept)) problem(name, 'нет бейджа «Концепт продукта, не существующая функция»');
      if (!/демо/.test(demo)) problem(name, 'нет бейджа «демо-данные»');
    }
    let modes = await page.$$eval('#pk-modes [data-mode]', (bs) => bs.map((b) => b.getAttribute('data-mode')));
    if (!modes.length) problem(name, 'нет переключателя режимов');
    if (opt.mode) modes = modes.filter((m) => m === opt.mode);
    for (const m of modes) {
      await page.click(`#pk-modes [data-mode="${m}"]`);
      const text = (await page.locator('#pk-view').innerText()).trim();
      if (!text) problem(name, `режим ${m}: пустой экран`);
      for (const theme of touch ? ['light'] : ['light', 'dark']) {
        await page.evaluate((t) => document.documentElement.setAttribute('data-theme', t), theme);
        if (opt.shots) await page.screenshot({ path: path.join(shotsDir, `${name}-${m}-${theme}${touch ? '-touch' : ''}.png`), fullPage: true });
      }
      const small = await smallTargets(page, touch ? 44 : 32);
      if (small.length) problem(name, `режим ${m}${touch ? ' (тач)' : ''}: цели нажатия меньше ${touch ? 44 : 32} px: ${small.slice(0, 5).map((x) => `${x.t} ${x.w}×${x.h}`).join('; ')}`);
      if (!touch) rec.modes.push(m);
    }
    if (!touch) {
      await page.evaluate(() => document.documentElement.removeAttribute('data-theme'));
      await page.click('#pk-theme');
      const t1 = await page.evaluate(() => document.documentElement.getAttribute('data-theme'));
      await page.click('#pk-theme');
      const t2 = await page.evaluate(() => document.documentElement.getAttribute('data-theme'));
      if (!(t1 === 'light' && t2 === 'dark')) problem(name, `тема не переключается (получено ${t1} → ${t2})`);
    }
    await ctx.close();
  }
  if (rec.errors.length) problem(name, `ошибки консоли: ${rec.errors.slice(0, 3).join(' | ')}`);
  if (rec.external.length) problem(name, `внешние запросы: ${[...new Set(rec.external)].slice(0, 3).join(', ')}`);
  results.browsers.push(rec);
  await browser.close();
}

await run('chromium', pw.chromium);
if (opt.webkit) await run('webkit', pw.webkit);
if (opt.shots) fs.writeFileSync(path.join(shotsDir, 'smoke-results.json'), JSON.stringify(results, null, 2));
const hard = results.problems.filter((p) => !/проверка пропущена/.test(p));
console.log(`${hard.length ? 'FAILED' : 'OK'}: браузеров ${results.browsers.length}, режимов ${results.browsers[0] ? results.browsers[0].modes.length : 0}, замечаний ${hard.length}`);
results.problems.forEach((p) => console.log('  - ' + p));
process.exit(hard.length ? 1 : 0);
