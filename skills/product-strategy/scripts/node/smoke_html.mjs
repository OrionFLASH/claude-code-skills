#!/usr/bin/env node
// Автотест страницы стратегии (deliverables/index.html) через Playwright (Chromium, офлайн).
//
//   node smoke_html.mjs <index.html | OUT> [--node-dir <dir>] [--require all|a,b,…] [--shots <dir>] [--json] [--headed]
//
// Проверяет: ошибки консоли = 0, внешние запросы = 0, счётчики разделов/строк реестра/фигур, фильтры и сортировку
// реестра, экспорт CSV/JSON, модалку предложения из P-ссылки и «Показать в реестре», лайтбокс (открыть, вписать/1:1/2×,
// Ctrl+колесо, стрелки, Esc, #lb=key), зоны (hotspots) референсов, слои (лайтбокс поверх модалки, Esc — верхний слой,
// блокировка прокрутки), модалки Ганта/Kanban/узла схемы, поиск и фильтр конкурентов, scrollspy, тему, авторство,
// отсутствие горизонтального переполнения на 390 px. Нет данных для проверки — она «skip» (не провал), если не
// перечислена в --require (all — любая пропущенная проверка считается провалом).
//
// Playwright ищется так: --node-dir, env PS_NODE_DIR, <OUT>/build/node, папка скрипта (<dir>/node_modules).
// Ничего не ставится глобально. Коды выхода: 0 — всё прошло; 1 — есть провалы; 2 — неверные аргументы или нет файла;
// 3 — нет playwright или браузера (подсказка, как поставить, — в stderr).
import { createRequire } from 'node:module';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url));
const SKILL_DIR = path.resolve(SCRIPT_DIR, '..', '..');
const USAGE = 'node smoke_html.mjs <index.html | OUT> [--node-dir <dir>] [--require all|a,b] [--shots <dir>] [--json] [--headed]';

function parseArgs(argv) {
  const a = { target: null, nodeDir: null, require: [], shots: null, json: false, headed: false };
  for (let i = 0; i < argv.length; i++) {
    const x = argv[i];
    if (x === '--node-dir') a.nodeDir = argv[++i];
    else if (x === '--require') a.require = String(argv[++i] || '').split(',').map(s => s.trim()).filter(Boolean);
    else if (x === '--shots') a.shots = argv[++i];
    else if (x === '--json') a.json = true;
    else if (x === '--headed') a.headed = true;
    else if (x === '-h' || x === '--help') { console.log(USAGE); process.exit(0); }
    else if (!a.target) a.target = x;
    else { console.error('лишний аргумент: ' + x + '\n' + USAGE); process.exit(2); }
  }
  return a;
}

const args = parseArgs(process.argv.slice(2));
if (!args.target) { console.error('использование: ' + USAGE); process.exit(2); }
let HTML = path.resolve(args.target);
if (fs.existsSync(HTML) && fs.statSync(HTML).isDirectory()) HTML = path.join(HTML, 'deliverables', 'index.html');
if (!fs.existsSync(HTML)) { console.error('нет файла страницы: ' + HTML); process.exit(2); }
const OUT = path.basename(path.dirname(HTML)) === 'deliverables' ? path.dirname(path.dirname(HTML)) : path.dirname(HTML);

function loadModule(name, dirs) {
  for (const d of dirs) {
    if (!d) continue;
    try { return createRequire(path.join(path.resolve(d), 'node_modules', '_resolver.cjs'))(name); } catch (e) { /* следующий кандидат */ }
  }
  return null;
}
const pw = loadModule('playwright', [args.nodeDir, process.env.PS_NODE_DIR, path.join(OUT, 'build', 'node'), SCRIPT_DIR]);
if (!pw) {
  console.error('нет playwright: python3 ' + path.join(SKILL_DIR, 'scripts', 'check_env.py') + ' --install-node ' + OUT);
  process.exit(3);
}

let browser;
try {
  browser = await pw.chromium.launch({ headless: !args.headed });
} catch (e) {
  const nd = args.nodeDir || process.env.PS_NODE_DIR || path.join(OUT, 'build', 'node');
  console.error('нет браузера Chromium для playwright: npx --prefix ' + nd + ' playwright install chromium\n(' + String(e.message || e).split('\n')[0] + ')');
  process.exit(3);
}

const URL_ = pathToFileURL(HTML).href;
const errors = [], external = [];
const checks = [];
const counts = {};
const SKIP = (reason) => ({ skip: reason });
const OK = (detail) => ({ ok: true, detail });
const FAIL = (detail) => ({ ok: false, detail });
const sleep = ms => new Promise(r => setTimeout(r, ms));

function watch(page, tag) {
  page.on('pageerror', e => errors.push(tag + ' pageerror: ' + String(e.message || e).split('\n')[0]));
  page.on('console', m => { if (m.type() === 'error') errors.push(tag + ' console: ' + m.text().slice(0, 300)); });
  page.on('request', r => { const u = r.url(); if (!/^(file|data|blob|about):/i.test(u)) external.push(tag + ' ' + u); });
}

async function closeLayers(page) {
  for (let i = 0; i < 5; i++) {
    const n = await page.locator('.layer.open').count().catch(() => 0);
    if (!n) break;
    await page.keyboard.press('Escape');
    await sleep(60);
  }
}

async function check(page, name, fn) {
  let res;
  try { res = await fn(); } catch (e) { res = FAIL(String((e && e.message) || e).split('\n')[0]); }
  try { await closeLayers(page); } catch (e) { /* страница могла закрыться */ }
  const status = res && res.skip ? 'skip' : res && res.ok ? 'pass' : 'fail';
  checks.push({ name, status, detail: res ? (res.skip || res.detail || '') : '' });
}

async function shot(page, name) {
  if (!args.shots) return;
  fs.mkdirSync(args.shots, { recursive: true });
  await page.screenshot({ path: path.join(args.shots, name + '.png') }).catch(() => {});
}

const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, acceptDownloads: true });
const page = await ctx.newPage();
page.setDefaultTimeout(10000);
watch(page, 'desktop');
await page.goto(URL_, { waitUntil: 'load' });
await sleep(300);

// ---------------------------------------------------------------- счётчики
await check(page, 'counts', async () => {
  Object.assign(counts, await page.evaluate(() => ({
    sections: document.querySelectorAll('main > section').length,
    nav: document.querySelectorAll('nav.side a[data-sec]').length,
    rows: document.querySelectorAll('#tb tr.row').length,
    figures: document.querySelectorAll('figure.lb').length,
    images: Object.keys(JSON.parse((document.getElementById('d-img') || { textContent: '{}' }).textContent)).length,
    pid_links: document.querySelectorAll('a.pid').length,
    gantt_rows: document.querySelectorAll('.grow[data-g]').length,
    kanban_cards: document.querySelectorAll('.kcard[data-k]').length,
    flow_nodes: document.querySelectorAll('.flowsvg [data-node].fnode').length,
    refcards: document.querySelectorAll('article.ref').length,
    competitors: document.querySelectorAll('.ccard').length,
    csp: !!document.querySelector('meta[http-equiv="Content-Security-Policy"][content*="default-src \'none\'"]'),
  })));
  if (!counts.sections) return FAIL('нет разделов main > section');
  if (counts.nav !== counts.sections) return FAIL(`ссылок навигации ${counts.nav}, разделов ${counts.sections}`);
  if (!counts.csp) return FAIL('нет CSP default-src none');
  return OK(`разделов ${counts.sections}, строк ${counts.rows}, фигур ${counts.figures}, P-ссылок ${counts.pid_links}`);
});
await shot(page, 'desktop-top');

// ---------------------------------------------------------------- реестр: фильтры и поиск
await check(page, 'registry-filter', async () => {
  const total = await page.locator('#tb tr.row').count();
  if (!total) return SKIP('нет реестра');
  const fields = await page.$$eval('#registry select[data-f]', ss => ss.map(s => ({ f: s.dataset.f, v: [...s.options].map(o => o.value).filter(Boolean)[0] || '' })));
  const done = [];
  for (const { f, v } of fields) {
    if (!v) continue;
    const sel = page.locator(`#registry select[data-f="${f}"]`);
    await sel.selectOption(v);
    const r = await page.evaluate(([f, v]) => {
      const rows = [...document.querySelectorAll('#tb tr.row')];
      return { n: rows.length, cat: f === 'category' ? rows.every(x => x.dataset.cat === v) : true, txt: document.getElementById('reg-count').textContent };
    }, [f, v]);
    await sel.selectOption('');
    if (!r.n || r.n > total || !r.cat || !r.txt.includes(String(r.n))) return FAIL(`фильтр ${f}=${v}: строк ${r.n}, счётчик «${r.txt}»`);
    done.push(`${f}:${r.n}`);
  }
  if (await page.locator('#tb tr.row').count() !== total) return FAIL('после сброса фильтров строк не столько, сколько было');
  const id = await page.locator('#tb tr.row').nth(Math.min(3, total - 1)).getAttribute('data-id');
  await page.fill('#q', id);
  await sleep(50);
  const ids = await page.$$eval('#tb tr.row', trs => trs.map(t => t.dataset.id));
  await page.fill('#q', '');
  if (!ids.includes(id) || (total > 1 && ids.length >= total)) return FAIL(`поиск «${id}»: ${ids.length} строк`);
  return OK(`фильтры ${done.join(', ')}; поиск «${id}» → ${ids.length}`);
});

// ---------------------------------------------------------------- реестр: сортировка
function monotonic(vals, dir) {
  const xs = vals.filter(v => v !== '' && v != null);
  const firstEmpty = vals.findIndex(v => v === '' || v == null);
  if (firstEmpty >= 0 && vals.slice(firstEmpty).some(v => v !== '' && v != null)) return false;
  for (let i = 1; i < xs.length; i++) {
    const a = parseFloat(xs[i - 1]), b = parseFloat(xs[i]);
    const d = (!isNaN(a) && !isNaN(b)) ? b - a : String(xs[i]).localeCompare(String(xs[i - 1]), 'ru', { numeric: true });
    if (d * dir < -1e-9) return false;
  }
  return true;
}
await check(page, 'registry-sort', async () => {
  if (!await page.locator('#tb tr.row').count()) return SKIP('нет реестра');
  const out = [];
  const th = page.locator('#reg-head th[data-k="id"]');
  await th.click();
  for (let k = 0; k < 2; k++) {
    const dir = (await page.locator('#reg-head th[data-k="id"]').getAttribute('aria-sort')) === 'ascending' ? 1 : -1;
    const ids = await page.$$eval('#tb tr.row', trs => trs.map(t => t.dataset.id));
    if (!monotonic(ids, dir)) return FAIL('сортировка по ID нарушена (' + dir + ')');
    out.push('id' + (dir > 0 ? '↑' : '↓'));
    if (!k) await page.locator('#reg-head th[data-k="id"]').click();
  }
  const numKey = await page.evaluate(() => { const t = [...document.querySelectorAll('#reg-head th.num')].map(x => x.dataset.k).filter(k => k !== 'rank'); return t[0] || null; });
  if (numKey) {
    await page.locator(`#reg-head th[data-k="${numKey}"]`).click();
    for (let k = 0; k < 2; k++) {
      const dir = (await page.locator(`#reg-head th[data-k="${numKey}"]`).getAttribute('aria-sort')) === 'ascending' ? 1 : -1;
      const vals = await page.$$eval('#tb tr.row', trs => trs.map(t => t.dataset.v));
      if (!monotonic(vals, dir)) return FAIL(`сортировка по ${numKey} нарушена`);
      out.push(numKey + (dir > 0 ? '↑' : '↓'));
      if (!k) await page.locator(`#reg-head th[data-k="${numKey}"]`).click();
    }
  }
  const metric = await page.evaluate(() => {
    const vis = new Set([...document.querySelectorAll('#reg-head th')].map(t => t.dataset.k));
    const o = [...document.querySelectorAll('#sortby option')].map(x => x.value).filter(v => !vis.has(v));
    return o[0] || null;
  });
  if (metric) {
    await page.selectOption('#sortby', metric);
    const extra = await page.locator(`#reg-head th.extra[data-k="${metric}"]`).count();
    const dir = (await page.locator(`#reg-head th[data-k="${metric}"]`).getAttribute('aria-sort')) === 'ascending' ? 1 : -1;
    const vals = await page.$$eval('#tb tr.row', trs => trs.map(t => t.dataset.v));
    if (!extra || !monotonic(vals, dir)) return FAIL(`сортировка по метрике ${metric}: столбец ${extra}, порядок нарушен`);
    out.push('метрика ' + metric);
    await page.click('#sortdir');
    const vals2 = await page.$$eval('#tb tr.row', trs => trs.map(t => t.dataset.v));
    if (!monotonic(vals2, -dir)) return FAIL(`обратная сортировка по ${metric} нарушена`);
  }
  // раскрытие строки
  const row = page.locator('#tb tr.row').first();
  await row.locator('td').nth(2).click();
  const opened = await page.locator('#tb tr.detail').count();
  if (!opened) return FAIL('строка не раскрылась');
  await page.locator('#tb tr.row.open td').nth(2).click();
  return OK(out.join(', ') + '; раскрытие строки');
});
await page.evaluate(() => document.getElementById('registry') && document.getElementById('registry').scrollIntoView({ behavior: 'instant' }));
await shot(page, 'desktop-registry');

// ---------------------------------------------------------------- экспорт
await check(page, 'registry-export', async () => {
  if (!await page.locator('#exp-csv').count()) return SKIP('нет реестра');
  const shown = await page.locator('#tb tr.row').count();
  const [d1] = await Promise.all([page.waitForEvent('download'), page.click('#exp-csv')]);
  const csv = fs.readFileSync(await d1.path(), 'utf8').replace(/^﻿/, '');
  const lines = csv.split(/\r\n/).filter(Boolean);
  const [d2] = await Promise.all([page.waitForEvent('download'), page.click('#exp-json')]);
  const js = JSON.parse(fs.readFileSync(await d2.path(), 'utf8'));
  if (!lines[0].startsWith('id,')) return FAIL('CSV без заголовка id');
  if (js.length !== shown) return FAIL(`JSON: ${js.length} записей, показано ${shown}`);
  return OK(`CSV ${d1.suggestedFilename()} (${lines.length - 1} строк), JSON ${js.length}`);
});

// ---------------------------------------------------------------- P-ссылка → карточка → «Показать в реестре»
await check(page, 'pid-modal', async () => {
  const link = page.locator('main a.pid:not(#registry a.pid):visible').first();
  if (!await link.count()) return SKIP('нет P-ссылок вне реестра');
  const id = await link.getAttribute('data-pid');
  await link.scrollIntoViewIfNeeded();
  await link.click();
  await page.waitForSelector('#pm.open');
  const title = await page.locator('#pmtitle').textContent();
  const locked = await page.evaluate(() => document.documentElement.classList.contains('locked') && getComputedStyle(document.body).overflow === 'hidden');
  const hash = await page.evaluate(() => location.hash);
  await shot(page, 'desktop-modal');
  if (!title.includes(id)) return FAIL(`в заголовке нет ${id}: ${title}`);
  if (!locked) return FAIL('прокрутка страницы не заблокирована');
  await page.click('#pm-reg');
  await sleep(150);
  const st = await page.evaluate(id => {
    const tr = document.querySelector(`#tb tr.row[data-id="${id}"]`);
    const r = tr && tr.getBoundingClientRect();
    return { open: !!document.querySelector('.layer.open'), row: !!tr, expanded: !!(tr && tr.classList.contains('open') && tr.nextElementSibling && tr.nextElementSibling.classList.contains('detail')),
      visible: !!(r && r.bottom > 0 && r.top < innerHeight), locked: document.documentElement.classList.contains('locked') };
  }, id);
  if (st.open || st.locked) return FAIL('модалка не закрылась');
  if (!st.row || !st.expanded || !st.visible) return FAIL('«Показать в реестре»: строка ' + JSON.stringify(st));
  return OK(`${id}: карточка, hash ${hash}, показ в реестре`);
});

// ---------------------------------------------------------------- P-ссылки в тексте, который рисует скрипт (карточка)
await check(page, 'pid-dynamic', async () => {
  const t = await page.evaluate(() => {
    const reg = JSON.parse(document.getElementById('d-registry').textContent || '[]'), ids = new Set(reg.map(r => r.id));
    for (const r of reg) { for (const f of ['description', 'rationale', 'cheap_test', 'current_feature']) {
      const m = String(r[f] || '').match(/P\d{3}/g) || []; const hit = m.find(x => ids.has(x) && x !== r.id); if (hit) return { id: r.id, ref: hit }; } }
    return null;
  });
  if (!t) return SKIP('нет P-номеров в текстах предложений');
  await page.evaluate(id => { location.hash = '#p=' + id; }, t.id);
  await page.waitForSelector('#pm.open');
  const n = await page.locator(`#pmbody .dsec a.pid[data-pid="${t.ref}"]`).count();
  if (!n) return FAIL(`в карточке ${t.id} номер ${t.ref} не стал ссылкой`);
  await page.locator(`#pmbody .dsec a.pid[data-pid="${t.ref}"]`).first().click();
  await sleep(80);
  const now = await page.getAttribute('#pm', 'data-id');
  const back = await page.locator('#pmback').isVisible();
  if (now !== t.ref || !back) return FAIL(`переход ${t.id} → ${t.ref}: открыта ${now}, «назад» ${back}`);
  await page.click('#pmback'); await sleep(60);
  if (await page.getAttribute('#pm', 'data-id') !== t.id) return FAIL('«назад» не вернул прежнюю карточку');
  return OK(`${t.id} → ${t.ref} → назад`);
});

// ---------------------------------------------------------------- лайтбокс
await check(page, 'lightbox', async () => {
  const pick = await page.evaluate(() => {
    const figs = [...document.querySelectorAll('figure.lb')].filter(f => f.offsetParent !== null);
    if (!figs.length) return null;
    const by = {}; figs.forEach(f => { (by[f.dataset.group] = by[f.dataset.group] || new Set()).add(f.dataset.key + '|' + f.dataset.ref); });
    const g = Object.keys(by).sort((a, b) => by[b].size - by[a].size)[0];
    const i = figs.findIndex(f => f.dataset.group === g);
    figs.forEach((f, k) => f.toggleAttribute('data-smoke', k === i));
    return { group: g, n: by[g].size, key: figs[i].dataset.key };
  });
  if (!pick) return SKIP('нет картинок');
  const fig = page.locator('figure.lb[data-smoke]');
  await fig.scrollIntoViewIfNeeded();
  await fig.click();
  await page.waitForSelector('#lb.open');
  await page.waitForFunction(() => document.getElementById('lbimg').naturalWidth > 0);
  await sleep(100);
  const w = async () => page.evaluate(() => Math.round(document.getElementById('lbimg').getBoundingClientRect().width));
  const z = async () => page.getAttribute('#lb', 'data-zoom');
  const wFit = await w();
  await page.click('#lbbar button[data-z="1"]'); const w1 = await w();
  await page.click('#lbbar button[data-z="2"]'); const w2 = await w();
  if (!(w1 > 0) || Math.abs(w2 - 2 * w1) > 3) return FAIL(`зум: вписать ${wFit}, 1:1 ${w1}, 2× ${w2}`);
  await shot(page, 'desktop-lightbox');
  const box = await page.locator('#lbview').boundingBox();
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.keyboard.down('Control'); await page.mouse.wheel(0, 120); await page.keyboard.up('Control');
  await sleep(80);
  let wheel = await z();
  if (wheel === '2') {   // запасной путь: синтетическое событие с ctrlKey
    await page.evaluate(() => document.getElementById('lbview').dispatchEvent(new WheelEvent('wheel', { deltaY: 120, ctrlKey: true, bubbles: true, cancelable: true })));
    wheel = await z();
  }
  if (wheel !== '1') return FAIL('Ctrl+колесо не уменьшило масштаб: ' + wheel);
  let arrows = 'одна картинка в группе';
  if (pick.n > 1) {
    const c0 = await page.textContent('#lbcount');
    await page.keyboard.press('ArrowRight'); await sleep(60);
    const c1 = await page.textContent('#lbcount');
    await page.keyboard.press('ArrowLeft'); await sleep(60);
    const c2 = await page.textContent('#lbcount');
    if (c1 === c0 || c2 !== c0) return FAIL(`стрелки: ${c0} → ${c1} → ${c2}`);
    arrows = `${c0} → ${c1} → ${c2}`;
  }
  await page.keyboard.press('Escape'); await sleep(60);
  if (await page.locator('#lb.open').count()) return FAIL('Esc не закрыл лайтбокс');
  if (await page.evaluate(() => document.documentElement.classList.contains('locked'))) return FAIL('прокрутка осталась заблокированной');
  await page.evaluate(k => { location.hash = '#lb=' + encodeURIComponent(k); }, pick.key);
  await page.waitForSelector('#lb.open', { timeout: 3000 });
  await page.keyboard.press('Escape'); await sleep(60);
  const hashAfter = await page.evaluate(() => location.hash);
  if (/^#lb=/.test(hashAfter)) return FAIL('hash #lb= не сброшен после закрытия');
  return OK(`группа «${pick.group}» (${pick.n}): вписать ${wFit}px, 1:1 ${w1}px, 2× ${w2}px, Ctrl+колесо, стрелки ${arrows}, Esc, #lb=`);
});

// ---------------------------------------------------------------- зоны референсов
await check(page, 'hotspot', async () => {
  const fig = page.locator('figure.lb[data-ref]:not([data-ref=""]):visible').first();
  if (!await fig.count()) return SKIP('нет референсов с картинкой');
  await fig.scrollIntoViewIfNeeded();
  await fig.click();
  await page.waitForSelector('#lb.open');
  await page.waitForFunction(() => document.getElementById('lbimg').naturalWidth > 0);
  const pins = await page.locator('#lbwrap .pin').count();
  if (!pins) return FAIL('нет номеров элементов поверх картинки');
  const free = await page.evaluate(() => [...document.querySelectorAll('#lbwrap .pin')].map((p, i) => {
    const r = p.getBoundingClientRect(); return document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2) === p ? i : -1; }).filter(i => i >= 0));
  if (free.length < pins) return FAIL(`номера перекрывают друг друга: доступно ${free.length} из ${pins}`);
  await page.locator('#lbwrap .pin').nth(free[0]).click();
  const sel = await page.locator('#lbside .hsitem.on').count();
  const items = await page.locator('#lbside .hsitem').count();
  if (sel !== 1) return FAIL('клик по номеру не выделил описание');
  if (items > 1) {
    await page.locator('#lbside .hsitem').nth(1).click();
    if (await page.locator('#lbwrap .pin.on').count() !== 1) return FAIL('клик по описанию не выделил номер');
  }
  return OK(`номеров ${pins}, описаний ${items}`);
});

// ---------------------------------------------------------------- слои: лайтбокс поверх модалки
await check(page, 'layers', async () => {
  const id = await page.evaluate(() => {
    const reg = JSON.parse(document.getElementById('d-registry').textContent || '[]');
    const img = JSON.parse(document.getElementById('d-img').textContent || '{}');
    const r = reg.find(x => (x.concepts || []).some(c => c.img && img[c.img]));
    return r ? r.id : null;
  });
  if (!id) return SKIP('нет предложения с концептом-картинкой');
  await page.evaluate(id => { location.hash = '#p=' + id; }, id);
  await page.waitForSelector('#pm.open');
  const f = page.locator('#pm .concepts figure.lb').first();
  await f.click();
  await page.waitForSelector('#lb.open');
  const z = await page.evaluate(() => [+getComputedStyle(document.getElementById('pm')).zIndex, +getComputedStyle(document.getElementById('lb')).zIndex]);
  if (!(z[1] > z[0])) return FAIL('лайтбокс не поверх модалки: ' + z.join(' / '));
  await page.keyboard.press('Escape'); await sleep(60);
  const s1 = await page.evaluate(() => [!!document.querySelector('#lb.open'), !!document.querySelector('#pm.open'), document.documentElement.classList.contains('locked')]);
  if (s1[0] || !s1[1] || !s1[2]) return FAIL('Esc закрыл не верхний слой: ' + JSON.stringify(s1));
  await page.keyboard.press('Escape'); await sleep(60);
  const s2 = await page.evaluate(() => [!!document.querySelector('.layer.open'), document.documentElement.classList.contains('locked')]);
  if (s2[0] || s2[1]) return FAIL('после второго Esc слой открыт или прокрутка заблокирована');
  return OK(`${id}: модалка → лайтбокс (z ${z[0]} < ${z[1]}), Esc по слоям, прокрутка разблокирована`);
});

// ---------------------------------------------------------------- Гант, Kanban, узел схемы
async function infoModal(selector, name, opts = {}) {
  const el = page.locator(selector).first();
  if (!await el.count()) return SKIP('нет: ' + name);
  await el.scrollIntoViewIfNeeded();
  await el.click(opts);
  await page.waitForSelector('#im.open');
  const t = (await page.textContent('#imtitle')).trim();
  const b = (await page.textContent('#imbody')).trim();
  if (!t || !b) return FAIL('пустая модалка');
  return OK(t.slice(0, 70));
}
await check(page, 'gantt-modal', async () => {
  const r = await infoModal('.grow[data-g] .glabel', 'строк Ганта');
  if (r.ok) await shot(page, 'desktop-gantt-modal');
  return r;
});
await check(page, 'kanban-modal', async () => infoModal('.kcard[data-k] .kt', 'карточек Kanban'));
await check(page, 'flow-node', async () => infoModal('.flowsvg [data-node].fnode', 'узлов схемы', { force: true }));

// ---------------------------------------------------------------- конкуренты
await check(page, 'competitors', async () => {
  const total = await page.locator('.ccard').count();
  if (!total) return SKIP('нет конкурентов');
  const name = (await page.locator('.ccard h4').nth(Math.min(1, total - 1)).textContent()).trim().split(/\s+/).slice(0, 2).join(' ');
  await page.fill('#cq', name); await sleep(80);
  const n = await page.locator('.ccard').count();
  const cnt = await page.textContent('#ccount');
  await page.fill('#cq', '');
  if (!n || n > total || !cnt.includes(String(n))) return FAIL(`поиск «${name}»: ${n} из ${total}`);
  let typeInfo = '';
  if (await page.locator('#ctype').count()) {
    const v = await page.$eval('#ctype', s => [...s.options].map(o => o.value).filter(Boolean)[0] || '');
    if (v) {
      await page.selectOption('#ctype', v); await sleep(50);
      const types = await page.$$eval('.ccard', cs => cs.map(c => c.dataset.type));
      await page.selectOption('#ctype', '');
      if (!types.length || types.some(t => t !== v)) return FAIL('фильтр типа ' + v);
      typeInfo = `, тип ${v}: ${types.length}`;
    }
  }
  const mrows = await page.locator('#cmatrix tbody tr').count();
  const shotFig = page.locator('.ccard figure.lb').first();
  let lbInfo = '';
  if (await shotFig.count()) {
    await shotFig.scrollIntoViewIfNeeded(); await shotFig.click(); await page.waitForSelector('#lb.open');
    lbInfo = ', лайтбокс скриншота'; await page.keyboard.press('Escape');
  }
  await page.evaluate(() => document.getElementById('competitors').scrollIntoView({ behavior: 'instant' }));
  await shot(page, 'desktop-competitors');
  return OK(`карточек ${total}, поиск «${name}» → ${n}${typeInfo}, строк матрицы ${mrows}${lbInfo}`);
});

// ---------------------------------------------------------------- scrollspy
await check(page, 'scrollspy', async () => {
  const ids = await page.$$eval('nav.side a[data-sec]', as => as.map(a => a.dataset.sec));
  if (ids.length < 3) return SKIP('мало разделов');
  const target = ids[Math.floor(ids.length / 2)];
  await page.evaluate(id => document.getElementById(id).scrollIntoView({ behavior: 'instant', block: 'start' }), target);
  await sleep(400);
  const st = await page.evaluate(() => ({ active: (document.querySelector('nav.side a.active') || {}).dataset?.sec || null,
    here: (document.querySelector('nav.side .here-t') || {}).textContent || '', bottom: innerHeight + scrollY >= document.documentElement.scrollHeight - 2,
    scrollLeft: document.getElementById('nav').scrollLeft }));
  if (st.active !== target && !st.bottom) return FAIL(`активный ${st.active}, ожидался ${target}`);
  if (st.scrollLeft !== 0) return FAIL('навигация сдвинута по горизонтали');
  return OK(`«${st.here}» (${st.active})`);
});

// ---------------------------------------------------------------- тема, авторство
await check(page, 'theme', async () => {
  const btn = page.locator('nav.side [data-theme-btn]');
  if (!await btn.count()) return SKIP('нет переключателя темы');
  const seen = [];
  for (let i = 0; i < 3; i++) { await btn.click(); seen.push(await page.evaluate(() => document.documentElement.getAttribute('data-theme') || 'auto')); }
  const bg = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
  if (!seen.includes('light') || !seen.includes('dark') || seen[2] !== 'auto') return FAIL('цикл темы: ' + seen.join(' → '));
  return OK(seen.join(' → ') + ', фон ' + bg);
});
await check(page, 'author', async () => {
  const a = await page.evaluate(() => ({ meta: (document.querySelector('meta[name="author"]') || {}).content || '',
    cp: (document.querySelector('meta[name="copyright"]') || {}).content || '', line: !!document.querySelector('#top .author'),
    footer: (document.querySelector('footer.copy') || {}).textContent || '' }));
  if (!a.meta) return SKIP('автор не задан в build/run-config.json');
  if (!a.line || !a.footer.includes('©')) return FAIL('нет строки автора под H1 или © в подвале');
  return OK(a.meta + ' · ' + a.cp);
});

// ---------------------------------------------------------------- мобильная ширина 390 px
const mctx = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 1, hasTouch: true });
const mpage = await mctx.newPage();
mpage.setDefaultTimeout(10000);
watch(mpage, 'mobile');
await mpage.goto(URL_, { waitUntil: 'load' });
await sleep(300);
await check(mpage, 'mobile-overflow', async () => {
  const probe = async () => mpage.evaluate(() => {
    const W = document.documentElement.clientWidth;
    const inScroller = el => { for (let p = el.parentElement; p && p !== document.body; p = p.parentElement) { const o = getComputedStyle(p).overflowX; if (o === 'auto' || o === 'scroll' || o === 'hidden') return true; } return false; };
    const bad = [...document.querySelectorAll('main *')].filter(el => { const r = el.getBoundingClientRect(); return r.width > 0 && r.right > W + 1 && !inScroller(el); })
      .slice(0, 4).map(el => el.tagName.toLowerCase() + (el.className && typeof el.className === 'string' ? '.' + el.className.split(' ')[0] : ''));
    return { sw: document.documentElement.scrollWidth, W, bad };
  });
  const p1 = await probe();
  await mpage.evaluate(() => window.scrollTo(0, document.body.scrollHeight / 2)); await sleep(150);
  const p2 = await probe();
  await shot(mpage, 'mobile-middle');
  await mpage.evaluate(() => window.scrollTo(0, 0)); await sleep(150);
  if (p1.sw > p1.W + 1 || p2.sw > p2.W + 1) return FAIL(`ширина документа ${Math.max(p1.sw, p2.sw)} > ${p1.W}; выходят: ${[...p1.bad, ...p2.bad].join(', ')}`);
  if (p1.bad.length || p2.bad.length) return FAIL('элементы за правым краем: ' + [...p1.bad, ...p2.bad].join(', '));
  return OK(`ширина ${p1.sw} ≤ ${p1.W}`);
});
await shot(mpage, 'mobile-top');
await check(mpage, 'mobile-nav', async () => {
  const t = mpage.locator('#navtoggle');
  if (!await t.isVisible()) return FAIL('нет кнопки «Разделы» на мобильной ширине');
  await t.click();
  if (!await mpage.locator('nav.side').isVisible()) return FAIL('меню не открылось');
  await shot(mpage, 'mobile-nav');
  const ids = await mpage.$$eval('nav.side a[data-sec]', as => as.map(a => a.dataset.sec));
  const target = ids[Math.min(ids.length - 1, Math.floor(ids.length / 2))];
  await mpage.locator(`nav.side a[data-sec="${target}"]`).click();
  if (await mpage.locator('nav.side').isVisible()) return FAIL('меню не закрылось после выбора раздела');
  let top = null, prev = NaN;   // плавная прокрутка: ждать, пока раздел перестанет двигаться
  for (let i = 0; i < 40; i++) {
    await sleep(100);
    top = await mpage.evaluate(id => Math.round(document.getElementById(id).getBoundingClientRect().top), target);
    if (top === prev) break;
    prev = top;
  }
  const st = await mpage.evaluate(() => ({ sw: document.documentElement.scrollWidth, bar: Math.round(document.querySelector('.mbar').getBoundingClientRect().top),
    bottom: innerHeight + scrollY >= document.documentElement.scrollHeight - 2, here: (document.querySelector('.mbar .here-t') || {}).textContent }));
  await shot(mpage, 'mobile-section');
  if (st.sw > 391) return FAIL('переполнение после перехода: ' + st.sw);
  if (st.bar !== 0) return FAIL('мобильная шапка не у верхнего края: ' + st.bar);
  if ((top < 0 || top > 120) && !st.bottom) return FAIL(`раздел ${target} после перехода на ${top}px от верха (ожидалось 0–120)`);
  return OK(`переход к ${target}: верх раздела ${top}px, шапка «${st.here}»`);
});
await check(mpage, 'mobile-modal', async () => {
  const link = mpage.locator('main a.pid:visible').first();
  if (!await link.count()) return SKIP('нет P-ссылок');
  await link.scrollIntoViewIfNeeded(); await link.click();
  await mpage.waitForSelector('#pm.open');
  const w = await mpage.evaluate(() => { const b = document.querySelector('#pm .mbox').getBoundingClientRect(); return { l: Math.round(b.left), r: Math.round(b.right), W: innerWidth }; });
  await shot(mpage, 'mobile-modal');
  if (w.l < 0 || w.r > w.W) return FAIL('карточка шире экрана: ' + JSON.stringify(w));
  return OK(`карточка ${w.r - w.l}px`);
});

// ---------------------------------------------------------------- итог
checks.push({ name: 'console-errors', status: errors.length ? 'fail' : 'pass', detail: errors.length ? errors.slice(0, 5).join(' | ') : '0' });
checks.push({ name: 'external-requests', status: external.length ? 'fail' : 'pass', detail: external.length ? external.slice(0, 5).join(' | ') : '0' });
await browser.close();

const reqAll = args.require.includes('all');
for (const c of checks) {
  if (c.status === 'skip' && (reqAll || args.require.includes(c.name))) { c.status = 'fail'; c.detail = 'обязательная проверка пропущена: ' + c.detail; }
}
const failed = checks.filter(c => c.status === 'fail');
const result = { ok: failed.length === 0, file: HTML, counts, passed: checks.filter(c => c.status === 'pass').length,
  failed: failed.length, skipped: checks.filter(c => c.status === 'skip').length, checks, errors, external };
if (args.json) {
  console.log(JSON.stringify(result, null, 1));
} else {
  const mark = { pass: 'OK  ', fail: 'FAIL', skip: 'skip' };
  for (const c of checks) console.log(`${mark[c.status]} ${c.name.padEnd(18)} ${c.detail}`);
  console.log(`ИТОГ: ${result.ok ? 'пройдено' : 'есть провалы'} — ok ${result.passed}, fail ${result.failed}, skip ${result.skipped}; ` +
    `ошибок консоли ${errors.length}, внешних запросов ${external.length}; ${HTML}`);
}
process.exit(result.ok ? 0 : 1);
