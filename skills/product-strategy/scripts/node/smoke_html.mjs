#!/usr/bin/env node
// Автотест страницы стратегии (deliverables/index.html) через Playwright (Chromium, офлайн).
//
//   node smoke_html.mjs <index.html | OUT> [--node-dir <dir>] [--require all|a,b,…] [--shots <dir>] [--json] [--headed]
//
// Проверяет: ошибки консоли = 0, внешние запросы = 0, счётчики разделов/строк реестра/фигур, фильтры и сортировку
// реестра, экспорт CSV/JSON, модалку предложения из P-ссылки и «Показать в реестре», лайтбокс (открыть, вписать/1:1/2×,
// Ctrl+колесо, стрелки, Esc, #lb=key), зоны (hotspots) референсов, слои (лайтбокс поверх модалки, Esc — верхний слой,
// блокировка прокрутки), модалки Ганта/Kanban/узла схемы, поиск и фильтр конкурентов, scrollspy, тему, авторство,
// отсутствие горизонтального переполнения на 390 px.
// Геометрия (1440×900 и 390×844, Chromium и WebKit): раскрывает КАЖДУЮ строку реестра и меряет её — строка
// display:table-row, высота < --max-row-height (2500 px), столбец значения dl.kv ≥ 120 px, секция ≥ 200 px, карточка в
// видимой части реестра, ничего не торчит из карточки, нет заголовка-«сироты» внизу колонки; карточка в окне P-id —
// те же правила; таблицы: на 1440 не шире рамки, последняя колонка не обрезана, на 390 — прокрутка внутри рамки;
// Гант: подписи месяцев не обрезаны, ромбы вех внутри диаграммы; ширина документа ≤ ширины окна.
// Контраст ≥ 4,5:1 (крупный текст ≥ 3:1) по computed color для бейджей, тегов, подписей, ссылок — в светлой, тёмной и
// «авто» при тёмной системной теме. WebKit берётся из playwright или из кэша ~/Library/Caches/ms-playwright
// (webkit-*); нет WebKit — проверка «skip» с пояснением (условие окружения, --require all его не требует).
// Режим «Отслеживание» (есть раздел #progress, т. е. data/progress.json): раздел и плитки, фильтр статуса и быстрые фильтры
// реестра (число строк меняется), сортировка по статусу, поля статуса в CSV, карточка с блоком «Выполнение», Гант с
// линией «Сегодня» внутри диаграммы на 1440 и 390 px, модалка задачи со статусами, переключатель Kanban «Как в плане / По
// фактам», ссылки только https://github.com/, контраст статусных чипов в трёх темах, нет переполнения на 390 px.
// Раздела нет — эти проверки «skip» по условию (страница без прогресса), --require all их не требует.
// Lite-страница (build_html.py --lite): картинки assets/ рядом со страницей существуют и грузятся; локальные файлы
// разрешены только внутри папки страницы, всё прочее — «внешний запрос».
// Нет данных для проверки — она «skip» (не провал), если не перечислена в --require (all — любая пропущенная проверка
// данных считается провалом).
//
// Playwright ищется так: --node-dir, env PS_NODE_DIR, <OUT>/build/node, ~/.cache/product-strategy/node, папка скрипта (<dir>/node_modules).
// Ничего не ставится глобально. Коды выхода: 0 — всё прошло; 1 — есть провалы; 2 — неверные аргументы или нет файла;
// 3 — нет playwright или браузера (подсказка, как поставить, — в stderr).
import { createRequire } from 'node:module';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url));
const SKILL_DIR = path.resolve(SCRIPT_DIR, '..', '..');
const USAGE = 'node smoke_html.mjs <index.html | OUT> [--node-dir <dir>] [--require all|a,b] [--engines chromium,webkit] '
  + '[--max-row-height 2500] [--shots <dir>] [--json] [--headed]';

function parseArgs(argv) {
  const a = { target: null, nodeDir: null, require: [], shots: null, json: false, headed: false, engines: ['chromium', 'webkit'], maxRowH: 2500 };
  for (let i = 0; i < argv.length; i++) {
    const x = argv[i];
    if (x === '--node-dir') a.nodeDir = argv[++i];
    else if (x === '--require') a.require = String(argv[++i] || '').split(',').map(s => s.trim()).filter(Boolean);
    else if (x === '--engines') a.engines = String(argv[++i] || '').split(',').map(s => s.trim()).filter(Boolean);
    else if (x === '--max-row-height') a.maxRowH = Number(argv[++i]) || 2500;
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
const pw = loadModule('playwright', [args.nodeDir, process.env.PS_NODE_DIR, path.join(OUT, 'build', 'node'), path.join(process.env.HOME || process.env.USERPROFILE || '', '.cache', 'product-strategy', 'node'), SCRIPT_DIR]);
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
const PAGE_DIR = path.dirname(HTML);
const errors = [], external = [];
const localFiles = new Set();
const checks = [];
const counts = {};
const SKIP = (reason, env) => ({ skip: reason, env: !!env });
const OK = (detail) => ({ ok: true, detail });
const FAIL = (detail) => ({ ok: false, detail });
const sleep = ms => new Promise(r => setTimeout(r, ms));

function watch(page, tag) {
  page.on('pageerror', e => errors.push(tag + ' pageerror: ' + String(e.message || e).split('\n')[0]));
  page.on('console', m => { if (m.type() === 'error') errors.push(tag + ' console: ' + m.text().slice(0, 300)); });
  page.on('request', r => {
    const u = r.url();
    if (/^(data|blob|about):/i.test(u)) return;
    if (/^file:/i.test(u)) {           // локальные файлы — только внутри папки страницы (lite: assets/)
      let p = null; try { p = fileURLToPath(u.split('#')[0]); } catch (e) { /* битый URL */ }
      if (p && (p === HTML || p.startsWith(PAGE_DIR + path.sep))) { if (p !== HTML) localFiles.add(p); return; }
      external.push(tag + ' файл вне папки страницы: ' + u); return;
    }
    external.push(tag + ' ' + u);
  });
  page.on('requestfailed', r => { const f = (r.failure() || {}).errorText || ''; if (!/abort|cancel/i.test(f)) errors.push(tag + ' requestfailed: ' + r.url().slice(0, 200) + ' ' + f); });
}

// WebKit: из playwright, иначе самый новый webkit-* из кэша Playwright (версия playwright может ждать другую ревизию)
async function launchWebkit() {
  try { return { browser: await pw.webkit.launch({ headless: !args.headed }), how: 'playwright' }; } catch (e) { /* кэш */ }
  const bases = [process.env.PLAYWRIGHT_BROWSERS_PATH, path.join(os.homedir(), 'Library', 'Caches', 'ms-playwright'),
    path.join(os.homedir(), '.cache', 'ms-playwright'), path.join(process.env.LOCALAPPDATA || '', 'ms-playwright')].filter(Boolean);
  for (const base of bases) {
    if (!fs.existsSync(base)) continue;
    const cands = fs.readdirSync(base).filter(n => /^webkit-\d+$/.test(n)).sort((a, b) => +b.split('-')[1] - +a.split('-')[1]);
    for (const c of cands) {
      const exe = [path.join(base, c, 'pw_run.sh'), path.join(base, c, 'minibrowser-gtk', 'pw_run.sh'), path.join(base, c, 'Playwright.exe')].find(p => fs.existsSync(p));
      if (!exe) continue;
      try { return { browser: await pw.webkit.launch({ executablePath: exe, headless: !args.headed }), how: c }; } catch (e) { /* следующий */ }
    }
  }
  return null;
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
  const item = { name, status, detail: res ? (res.skip || res.detail || '') : '' };
  if (res && res.env) item.env = true;    // пропуск из-за окружения (нет WebKit), а не из-за данных
  if (res && res.data) item.data = res.data;
  checks.push(item);
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
  const disp = await page.evaluate(() => getComputedStyle(document.querySelector('#tb tr.detail')).display);
  await page.locator('#tb tr.row.open td').nth(2).click();
  if (disp !== 'table-row') return FAIL('раскрытая строка display:' + disp + ' (должно быть table-row)');
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

// ---------------------------------------------------------------- отслеживание выполнения (1.2): только если есть раздел #progress
// Нет раздела — проверки «skip» по условию (страница собрана без data/progress.json), --require all их не требует.
const NO_PG = 'нет раздела «Прогресс выполнения» — страница собрана без data/progress.json (режим отслеживания не запускался)';
const HAS_PG = (await page.locator('section#progress').count()) > 0;
const PG_SCOPE = '#progress, .dsec.pg, .kb-facts, #gantt';
async function pgLinks(p) {   // внешние ссылки блоков прогресса — только https://github.com/…
  return p.evaluate(scope => {
    const bad = [], seen = new Set();
    document.querySelectorAll(scope).forEach(root => root.querySelectorAll('a[href]').forEach(a => {
      const h = a.getAttribute('href') || ''; if (seen.has(a)) return; seen.add(a);
      if (/^[a-z][a-z0-9+.-]*:/i.test(h) && !/^https:\/\/github\.com\//.test(h)) bad.push(h.slice(0, 80));
    }));
    const reg = JSON.parse((document.getElementById('d-registry') || { textContent: '[]' }).textContent);
    let n = 0;
    for (const r of reg) { const g = r.pg; if (!g) continue;
      for (const x of [...(g.issues || []), ...(g.prs || []), ...(g.commits || [])]) { if (!x.url) continue; n++; if (!/^https:\/\/github\.com\//.test(x.url)) bad.push('data: ' + x.url.slice(0, 80)); } }
    return { bad, links: seen.size, dataLinks: n };
  }, PG_SCOPE);
}
async function ganttToday(p) {
  return p.evaluate(() => {
    const g = document.querySelector('#gantt .gantt'), gin = g && g.querySelector('.gin'), line = gin && gin.querySelector('.gtoday'), lab = gin && gin.querySelector('.gtd');
    if (!line) return { line: false };
    const gb = gin.getBoundingClientRect(), lb = line.getBoundingClientRect(), tb = lab ? lab.getBoundingClientRect() : null;
    const labelCol = (gin.querySelector('.grow .glabel') || gin.querySelector('.ghead .gl')).getBoundingClientRect();
    const out = [];
    if (lb.left < labelCol.right - 1 || lb.right > gb.right + 1) out.push(`линия x=${Math.round(lb.left - gb.left)} вне дорожки ${Math.round(labelCol.right - gb.left)}…${Math.round(gb.width)}`);
    if (lb.top < gb.top - 1 || lb.bottom > gb.bottom + 1 || lb.height < gb.height * 0.8) out.push('линия не на всю высоту диаграммы');
    if (tb && (tb.left < gb.left - 1 || tb.right > gb.right + 1)) out.push('подпись «Сегодня» за краем диаграммы');
    const pls = [...gin.querySelectorAll('.gpl')], outPl = pls.filter(e => { const b = e.getBoundingClientRect(); return b.left < labelCol.right - 1 || b.right > gb.right + 1; }).length;
    if (outPl) out.push('подписи статусов за краем дорожки: ' + outPl);
    const icons = pls.filter(e => /[✓◐!▸·]/.test(e.textContent)).length;
    if (pls.length && icons < pls.length) out.push('подпись статуса без значка');
    const fills = gin.querySelectorAll('.gbar .gfill').length;
    // показать линию в кадре: прокрутить рамку Ганта так, чтобы линия была видна
    const glw = labelCol.width;
    g.scrollLeft = Math.max(0, line.offsetLeft - glw - (g.clientWidth - glw) / 3);
    return { line: true, x: Math.round(lb.left - gb.left), w: Math.round(gb.width), labels: pls.length, fills, out, pageW: document.documentElement.scrollWidth, vw: innerWidth };
  });
}
await check(page, 'progress-section', async () => {
  if (!HAS_PG) return SKIP(NO_PG, true);
  const r = await page.evaluate(() => ({ tiles: document.querySelectorAll('#progress .pgk').length, nav: !!document.querySelector('nav.side a[data-sec="progress"]'),
    chips: document.querySelectorAll('#progress .pst').length, bars: document.querySelectorAll('#progress .pgrow').length,
    chart: !!document.querySelector('#progress svg.pgc'), leak: /progress:(start|end)/.test(document.querySelector('main').textContent),
    pids: document.querySelectorAll('#progress a.pid').length }));
  if (r.tiles < 6) return FAIL('плиток ' + r.tiles + ' (нужно 6: выполнено, в работе, отстаёт, заблокировано, вне стратегии, дата)');
  if (!r.nav) return FAIL('нет пункта навигации «Прогресс выполнения»');
  if (!r.chips) return FAIL('нет статусных чипов');
  if (r.leak) return FAIL('маркеры автоблока <!-- progress:start/end --> попали в текст страницы');
  await page.evaluate(() => document.getElementById('progress').scrollIntoView({ behavior: 'instant' }));
  await shot(page, 'progress-section-light');
  await page.evaluate(() => document.documentElement.setAttribute('data-theme', 'dark')); await sleep(120);
  await shot(page, 'progress-section-dark');
  await page.evaluate(() => document.documentElement.removeAttribute('data-theme'));
  // плитка со статусом (выполнено/заблокировано) → реестр с фильтром статуса
  if (!await page.locator('#progress .pgk[data-st-go]').count()) return OK(`плиток ${r.tiles}, чипов ${r.chips}; плиток-фильтров нет (нет выполненных и заблокированных)`);
  await page.locator('#progress .pgk[data-st-go]').first().click(); await sleep(120);
  const f = await page.evaluate(() => { const s = document.querySelector('#registry select[data-f="status"]'); const rows = [...document.querySelectorAll('#tb tr.row')];
    return { v: s ? s.value : null, n: rows.length, all: rows.every(x => x.dataset.st === (s && s.value)) }; });
  await page.click('#reg-reset');
  if (!f.v || !f.all) return FAIL('плитка не отфильтровала реестр: ' + JSON.stringify(f));
  return OK(`плиток ${r.tiles}, чипов ${r.chips}, полос ${r.bars}, график ${r.chart ? 'есть' : 'нет'}, P-ссылок ${r.pids}; плитка → фильтр «${f.v}» (${f.n})`);
});
await check(page, 'progress-registry', async () => {
  if (!HAS_PG) return SKIP(NO_PG, true);
  const total = await page.locator('#tb tr.row').count();
  const sel = page.locator('#registry select[data-f="status"]');
  if (!await sel.count()) return FAIL('нет фильтра статуса в реестре');
  const opts = await sel.evaluate(s => [...s.options].filter(o => o.value).map(o => ({ v: o.value, n: +((o.textContent.match(/\((\d+)\)\s*$/) || [])[1] || 0) })));
  const done = [];
  for (const o of opts) {
    await sel.selectOption(o.v); await sleep(30);
    const r = await page.evaluate(v => { const rows = [...document.querySelectorAll('#tb tr.row')]; return { n: rows.length, all: rows.every(x => x.dataset.st === v), cnt: document.getElementById('reg-count').textContent }; }, o.v);
    if (r.n !== o.n || !r.all || !r.cnt.includes(String(r.n))) { await sel.selectOption(''); return FAIL(`статус ${o.v}: строк ${r.n}, в списке ${o.n}, счётчик «${r.cnt}»`); }
    done.push(`${o.v}:${r.n}`);
  }
  await sel.selectOption('');
  if (opts.length > 1 && !opts.some(o => o.n < total)) return FAIL('фильтр статуса не меняет число строк');
  const quick = [];
  for (const q of ['notdone', 'work', 'behind']) {
    const b = page.locator(`#registry [data-qf="${q}"]`); if (!await b.count()) return FAIL('нет быстрого фильтра ' + q);
    await b.click(); await sleep(30);
    const r = await page.evaluate(q => { const reg = Object.fromEntries(JSON.parse(document.getElementById('d-registry').textContent).map(x => [x.id, x]));
      const rows = [...document.querySelectorAll('#tb tr.row')].map(x => reg[x.dataset.id]);
      const ok = rows.every(x => q === 'notdone' ? x.status && !['done', 'dropped', 'obsolete'].includes(x.status) : q === 'work' ? ['in_progress', 'partial'].includes(x.status) : (x.pg && x.pg.behind || []).length > 0);
      return { n: rows.length, ok, pressed: document.querySelector(`#registry [data-qf="${q}"]`).getAttribute('aria-pressed') }; }, q);
    await b.click(); await sleep(30);
    if (!r.ok || r.pressed !== 'true') return FAIL(`быстрый фильтр ${q}: строк ${r.n}, условие ${r.ok}, нажат ${r.pressed}`);
    quick.push(`${q}:${r.n}`);
  }
  // сортировка по статусу (порядок done → … → dropped) и колонка «Статус» с чипами
  await page.locator('#reg-head th[data-k="status"]').click(); await sleep(30);
  const vals = await page.$$eval('#tb tr.row', trs => trs.map(t => t.dataset.v));
  const chips = await page.locator('#tb tr.row .pst').count();
  if (!monotonic(vals, 1)) return FAIL('сортировка по статусу нарушена');
  if (!chips) return FAIL('нет чипов статуса в колонке');
  const [d1] = await Promise.all([page.waitForEvent('download'), page.click('#exp-csv')]);
  const head = fs.readFileSync(await d1.path(), 'utf8').replace(/^﻿/, '').split(/\r\n/)[0];
  await page.locator('#reg-head th[data-k="rank"], #reg-head th[data-k="id"]').first().click();
  if (!/(^|,)status,status_confidence,status_source,issues,prs,last_commit/.test(head)) return FAIL('в CSV нет полей статуса: ' + head.slice(0, 200));
  return OK(`статусы ${done.join(', ')}; быстрые ${quick.join(', ')}; сортировка по статусу, чипов ${chips}; CSV с полями статуса`);
});
await check(page, 'progress-card', async () => {
  if (!HAS_PG) return SKIP(NO_PG, true);
  const id = await page.evaluate(() => { const reg = JSON.parse(document.getElementById('d-registry').textContent);
    const r = reg.find(x => x.pg && (x.pg.issues || []).length && (x.pg.commits || []).length) || reg.find(x => x.pg); return r ? r.id : null; });
  if (!id) return FAIL('ни у одного предложения нет данных выполнения');
  await page.evaluate(id => { location.hash = '#p=' + id; }, id);
  await page.waitForSelector('#pm.open');
  const r = await page.evaluate(() => { const s = document.querySelector('#pmbody .dsec.pg'); return s ? { h: (s.querySelector('h4') || {}).textContent, chip: !!s.querySelector('.pst'),
    gh: s.querySelectorAll('a.gh').length, items: s.querySelectorAll('.pg-items li').length, head: !!document.querySelector('#pmchips .pst') } : null; });
  await shot(page, 'progress-card');
  if (!r) return FAIL(`в карточке ${id} нет блока «Выполнение»`);
  if (r.h !== 'Выполнение' || !r.chip || !r.head) return FAIL('блок «Выполнение» без заголовка или чипа: ' + JSON.stringify(r));
  const l = await pgLinks(page);
  if (l.bad.length) return FAIL('ссылки не на https://github.com/: ' + l.bad.slice(0, 3).join(', '));
  return OK(`${id}: «Выполнение», ссылок GitHub ${r.gh}, строк issues/PR/коммитов/кода ${r.items}`);
});
await check(page, 'progress-gantt-1440', async () => {
  if (!HAS_PG) return SKIP(NO_PG, true);
  if (!await page.locator('#gantt .gantt').count()) return SKIP('нет диаграммы Ганта');
  await page.evaluate(() => { document.getElementById('gantt').scrollIntoView({ behavior: 'instant' }); });
  const r = await ganttToday(page);
  await sleep(100); await shot(page, 'progress-gantt-1440');
  if (!r.line) return FAIL('нет линии «Сегодня»');
  if (r.out.length) return FAIL(r.out.join('; '));
  if (!r.fills) return FAIL('нет заливки полос по доле выполнения');
  return OK(`линия «Сегодня» x=${r.x} из ${r.w} px, подписей статуса ${r.labels}, заливок ${r.fills}`);
});
await check(page, 'progress-gantt-modal', async () => {
  if (!HAS_PG) return SKIP(NO_PG, true);
  const row = page.locator('.grow[data-g] .gbar.gs-done, .grow[data-g] .gbar.gs-behind, .grow[data-g] .gbar.gs-on_track, .grow[data-g] .gbar.gs-partial, .grow[data-g] .gbar.gs-upcoming').first();
  if (!await row.count()) return SKIP('нет полос со статусом');
  await row.scrollIntoViewIfNeeded(); await row.click({ force: true });
  await page.waitForSelector('#im.open');
  const r = await page.evaluate(() => ({ gst: !!document.querySelector('#imbody .gst'), pst: document.querySelectorAll('#imbody .pst').length }));
  if (!r.gst) return FAIL('в модалке задачи нет статуса выполнения');
  return OK(`статус задачи и чипов предложений: ${r.pst}`);
});
await check(page, 'progress-kanban', async () => {
  if (!HAS_PG) return SKIP(NO_PG, true);
  if (!await page.locator('#kanban').count()) return SKIP('нет доски Kanban');
  if (!await page.locator('label[for="kbv-facts"]').count()) return SKIP('нет data/kanban-progress.json — переключателя нет', true);
  await page.evaluate(() => document.getElementById('kanban').scrollIntoView({ behavior: 'instant' }));
  const vis = () => page.evaluate(() => ({ plan: !!document.querySelector('.kb-plan').getClientRects().length, facts: !!document.querySelector('.kb-facts').getClientRects().length }));
  const v0 = await vis();
  await page.click('label[for="kbv-facts"]'); await sleep(80);
  const v1 = await vis();
  const r = await page.evaluate(() => ({ cards: document.querySelectorAll('.kb-facts .kcard').length, moved: document.querySelectorAll('.kb-facts .kmoved').length, chips: document.querySelectorAll('.kb-facts .pst').length }));
  await shot(page, 'progress-kanban-facts');
  await page.click('label[for="kbv-plan"]'); await sleep(50);
  const v2 = await vis();
  if (!v0.plan || v0.facts) return FAIL('по умолчанию должна быть доска «Как в плане»');
  if (v1.plan || !v1.facts) return FAIL('переключатель не показал доску «По фактам»');
  if (!v2.plan || v2.facts) return FAIL('переключатель не вернул доску «Как в плане»');
  return OK(`«По фактам»: карточек ${r.cards}, перенесено ${r.moved}, чипов ${r.chips}`);
});
await check(page, 'progress-links', async () => {
  if (!HAS_PG) return SKIP(NO_PG, true);
  const l = await pgLinks(page);
  if (l.bad.length) return FAIL('ссылки не на https://github.com/: ' + l.bad.slice(0, 5).join(', '));
  return OK(`ссылок в блоках прогресса ${l.links}, ссылок в данных ${l.dataLinks} — все https://github.com/ или внутренние`);
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
await check(mpage, 'progress-gantt-390', async () => {
  if (!HAS_PG) return SKIP(NO_PG, true);
  if (!await mpage.locator('#gantt .gantt').count()) return SKIP('нет диаграммы Ганта');
  await mpage.evaluate(() => { const g = document.querySelector('#gantt .gantt'); g.scrollIntoView({ behavior: 'instant', block: 'start' }); window.scrollBy({ top: -80, behavior: 'instant' }); });
  const r = await ganttToday(mpage);
  await sleep(120); await shot(mpage, 'progress-gantt-390');
  if (!r.line) return FAIL('нет линии «Сегодня»');
  if (r.out.length) return FAIL(r.out.join('; '));
  if (r.pageW > r.vw) return FAIL(`ширина документа ${r.pageW} > ${r.vw}`);
  return OK(`линия «Сегодня» x=${r.x} из ${r.w} px внутри рамки, ширина ${r.pageW} ≤ ${r.vw}`);
});
await check(mpage, 'progress-mobile', async () => {
  if (!HAS_PG) return SKIP(NO_PG, true);
  await mpage.evaluate(() => document.getElementById('progress').scrollIntoView({ behavior: 'instant' })); await sleep(120);
  const r = await mpage.evaluate(() => {
    const W = document.documentElement.clientWidth;
    const inScroller = el => { for (let p = el.parentElement; p && p !== document.body; p = p.parentElement) { const o = getComputedStyle(p).overflowX; if (o === 'auto' || o === 'scroll' || o === 'hidden') return true; } return false; };
    const bad = [...document.querySelectorAll('#progress *')].filter(el => { const b = el.getBoundingClientRect(); return b.width > 0 && b.right > W + 1 && !inScroller(el); })
      .slice(0, 4).map(el => el.tagName.toLowerCase() + (typeof el.className === 'string' && el.className ? '.' + el.className.split(' ')[0] : ''));
    return { sw: document.documentElement.scrollWidth, W, bad };
  });
  await shot(mpage, 'progress-section-390');
  await mpage.evaluate(() => { const l = document.querySelector('label[for="kbv-facts"]'); if (l) { l.click(); document.getElementById('kanban').scrollIntoView({ behavior: 'instant' }); } }); await sleep(100);
  await shot(mpage, 'progress-kanban-390');
  const sw2 = await mpage.evaluate(() => document.documentElement.scrollWidth);
  if (r.sw > r.W + 1 || sw2 > r.W + 1) return FAIL(`ширина документа ${Math.max(r.sw, sw2)} > ${r.W}`);
  if (r.bad.length) return FAIL('за правым краем: ' + r.bad.join(', '));
  return OK(`раздел на ${r.W} px без переполнения`);
});

// ---------------------------------------------------------------- геометрия: все раскрытые строки, окно P-id, таблицы, Гант
const GEOM_VIEWS = [{ name: '1440', w: 1440, h: 900 }, { name: '390', w: 390, h: 844 }];
const MIN_DD = 120, MIN_SEC = 200;

// выполняется в странице (одним evaluate): раскрывает каждую строку реестра по очереди и меряет её
async function geomInPage({ maxH, minDD, minSec, view }) {
  const R = { view, rows: 0, heights: [], tallest: null, minDD: null, minSec: null, bad: [], modal: [], tables: 0, tableBad: [], gantt: null, ganttBad: [], pageW: 0, vw: innerWidth };
  const vis = el => !!el && el.getClientRects().length > 0;
  const wait = ms => new Promise(r => setTimeout(r, ms));
  function card(cardEl, frame) {
    const bad = [], fb = frame.getBoundingClientRect(), cb = cardEl.getBoundingClientRect(), fw = frame.clientWidth;
    const dds = [...cardEl.querySelectorAll('dl.kv dd')].filter(vis).map(d => d.getBoundingClientRect().width);
    const secs = [...cardEl.querySelectorAll(':scope > .dsec')].filter(vis).map(s => s.getBoundingClientRect().width);
    const minD = dds.length ? Math.round(Math.min(...dds)) : null, minS = secs.length ? Math.round(Math.min(...secs)) : null;
    if (minD != null && minD < minDD) bad.push('столбец значения ' + minD + ' px < ' + minDD);
    if (minS != null && minS < minSec) bad.push('секция ' + minS + ' px < ' + minSec);
    if (cb.left < fb.left - 1 || cb.right > fb.left + fw + 1) bad.push('карточка ' + Math.round(cb.width) + ' px вне видимых ' + fw + ' px');
    // заголовок внизу колонки, а его текст — в следующей. Координаты — по Range первого текстового узла: WebKit для
    // блоков внутри колонок отдаёт getBoundingClientRect в координатах первой колонки
    const textLeft = el => { if (!el) return null; const w = document.createTreeWalker(el, NodeFilter.SHOW_TEXT, { acceptNode: t => t.nodeValue.trim() ? 1 : 3 });
      const t = w.nextNode(); if (!t) return null; const r = document.createRange(); r.selectNodeContents(t); const b = r.getClientRects()[0]; return b ? b.left : null; };
    cardEl.querySelectorAll(':scope > .dsec > h4').forEach(h => {
      const a = textLeft(h), f = textLeft(h.nextElementSibling);
      if (a != null && f != null && Math.abs(f - a) > 60) bad.push('заголовок-сирота «' + h.textContent.trim() + '»');
    });
    let spill = 0;
    cardEl.querySelectorAll('*').forEach(e => { const b = e.getBoundingClientRect(); if (b.width && b.height) spill = Math.max(spill, Math.round(b.right - cb.right - 2), Math.round(cb.left - b.left - 2)); });
    if (spill > 0) bad.push('содержимое торчит из карточки на ' + spill + ' px');
    return { bad, minD, minS };
  }
  const tb = document.getElementById('tb'), wrap = document.querySelector('.reg-wrap');
  if (tb && wrap) {
    wrap.scrollLeft = 0;
    const ids = [...tb.querySelectorAll('tr.row')].map(tr => tr.getAttribute('data-id'));
    const row = id => tb.querySelector('tr.row[data-id="' + CSS.escape(id) + '"]');
    const hit = tr => tr.querySelector('td.c-title') || tr.cells[Math.min(2, tr.cells.length - 1)];
    for (const id of ids) {
      hit(row(id)).click();                                   // раскрыть (реестр перерисовывается)
      const tr = row(id), det = tr && tr.nextElementSibling;
      if (!det || !det.classList.contains('detail')) { R.bad.push(id + ': строка не раскрылась'); continue; }
      const c = det.querySelector('div.detail');
      const h = Math.round(det.getBoundingClientRect().height), disp = getComputedStyle(det).display;
      if (c) c.querySelectorAll('details').forEach(d => { d.open = true; });   // свёрнутые секции (телефон) — ширины меряем раскрытыми
      const m = c ? card(c, wrap) : { bad: ['нет карточки div.detail'], minD: null, minS: null };
      if (disp !== 'table-row') m.bad.unshift('display ' + disp + ' (нужно table-row)');
      if (h >= maxH) m.bad.unshift('высота ' + h + ' px ≥ ' + maxH);
      R.heights.push(h);
      if (!R.tallest || h > R.tallest.h) R.tallest = { id, h };
      if (m.minD != null) R.minDD = R.minDD == null ? m.minD : Math.min(R.minDD, m.minD);
      if (m.minS != null) R.minSec = R.minSec == null ? m.minS : Math.min(R.minSec, m.minS);
      if (m.bad.length) R.bad.push(id + ': ' + m.bad.join(', '));
      hit(row(id)).click();                                   // свернуть
    }
    R.rows = ids.length;
    // карточка в окне P-id: первая и самая высокая строки
    for (const id of [...new Set([ids[0], R.tallest && R.tallest.id].filter(Boolean))]) {
      location.hash = '#p=' + id; await wait(80);
      const c = document.querySelector('#pm.open #pmbody div.detail'), box = document.querySelector('#pm .mbox');
      if (!c) { R.modal.push(id + ': окно не открылось'); continue; }
      c.querySelectorAll('details').forEach(d => { d.open = true; });
      const m = card(c, box);
      if (m.bad.length) R.modal.push(id + ' (окно): ' + m.bad.join(', '));
      const close = document.querySelector('#pm [data-close]'); if (close) close.click(); await wait(30);
    }
  }
  // таблицы: раскрыть все <details>, на 1440 таблица не шире рамки, последняя колонка не обрезана, на 390 — прокрутка в рамке
  document.querySelectorAll('main details').forEach(d => { d.open = true; });
  for (const box of document.querySelectorAll('main .tbl')) {
    const t = box.querySelector(':scope > table');
    if (!t || !vis(box)) continue;
    R.tables++;
    let name = '', e = box;
    while (e && !name) { let p = e.previousElementSibling; while (p && !name) { if (/^H[2-4]$/.test(p.tagName)) name = p.textContent.trim(); p = p.previousElementSibling; } e = e.parentElement; if (e && e.tagName === 'SECTION') { name = name || ((e.querySelector('h2') || {}).textContent || e.id || ''); break; } }
    name = '«' + name.replace(/\s+/g, ' ').slice(0, 48) + '»';
    const over = Math.round(t.getBoundingClientRect().width - box.clientWidth), ox = getComputedStyle(box).overflowX;
    let cut = 0;
    for (const r of t.rows) { const c = r.cells[r.cells.length - 1]; if (c && c.scrollWidth > c.clientWidth + 1) cut++; }
    if (view === '1440' && over > 1) R.tableBad.push(name + ': шире рамки на ' + over + ' px (последняя колонка уходит за край)');
    if (over > 1 && ox !== 'auto' && ox !== 'scroll') R.tableBad.push(name + ': обрезана без прокрутки');
    if (cut) R.tableBad.push(name + ': в последней колонке обрезано ячеек: ' + cut);
  }
  // Гант: подписи месяцев не обрезаны, ромбы вех внутри диаграммы, рамка в пределах экрана
  const g = document.querySelector('.gantt'), gin = g && g.querySelector('.gin');
  if (g && gin && vis(g)) {
    const gb = gin.getBoundingClientRect(), spans = [...g.querySelectorAll('.gscale span')], ms = [...g.querySelectorAll('.gms')];
    const cutL = spans.filter(s => s.scrollWidth > s.clientWidth + 1).map(s => s.textContent.trim());
    const outMs = ms.filter(m => { const b = m.getBoundingClientRect(); return b.right > gb.right + 0.5 || b.left < gb.left - 0.5; }).length;
    const scrollOver = Math.round(g.scrollWidth - g.clientWidth - Math.max(0, gin.offsetWidth - g.clientWidth));
    const boxOver = Math.round(g.getBoundingClientRect().right - document.documentElement.clientWidth);
    R.gantt = { labels: spans.length, milestones: ms.length, scroll: g.scrollWidth > g.clientWidth + 1 };
    if (cutL.length) R.ganttBad.push('подписи месяцев обрезаны: ' + cutL.slice(0, 5).join(', '));
    if (outMs) R.ganttBad.push('ромбы вех за краем диаграммы: ' + outMs);
    if (scrollOver > 1) R.ganttBad.push('содержимое шире диаграммы на ' + scrollOver + ' px');
    if (boxOver > 1) R.ganttBad.push('рамка Ганта за правым краем экрана на ' + boxOver + ' px');
  }
  R.pageW = document.documentElement.scrollWidth;
  return R;
}

async function geomShots(p, engine, v, r) {
  if (!args.shots || !r.tallest) return;
  fs.mkdirSync(args.shots, { recursive: true });
  const id = r.tallest.id;
  await p.evaluate(id => { const tr = document.querySelector('#tb tr.row[data-id="' + CSS.escape(id) + '"]'); (tr.querySelector('td.c-title') || tr.cells[2]).click();
    document.getElementById('registry').scrollIntoView({ block: 'start', behavior: 'instant' });
    const t = document.querySelector('#tb tr.row[data-id="' + CSS.escape(id) + '"]'), w = document.querySelector('.reg-wrap');
    w.scrollTop = t.offsetTop - (w.querySelector('thead') || t).offsetHeight; window.scrollBy({ top: w.getBoundingClientRect().top - 60, behavior: 'instant' }); }, id);
  await sleep(250);
  await p.screenshot({ path: path.join(args.shots, `registry-open-${engine}-${v.name}-light.png`) }).catch(() => {});
  await p.evaluate(() => document.documentElement.setAttribute('data-theme', 'dark')); await sleep(150);
  await p.screenshot({ path: path.join(args.shots, `registry-open-${engine}-${v.name}-dark.png`) }).catch(() => {});
  await p.evaluate(() => { document.documentElement.removeAttribute('data-theme'); const g = document.querySelector('#gantt .gantt'); if (g) { g.scrollIntoView({ block: 'start', behavior: 'instant' }); window.scrollBy({ top: -70, behavior: 'instant' }); } }); await sleep(200);
  if (await p.locator('#gantt').count()) await p.screenshot({ path: path.join(args.shots, `gantt-${engine}-${v.name}.png`) }).catch(() => {});
}

async function geometryPass(br, engine) {
  for (const v of GEOM_VIEWS) {
    await check(page, `geometry-${engine}-${v.name}`, async () => {
      const c = await br.newContext({ viewport: { width: v.w, height: v.h }, deviceScaleFactor: 1 });
      try {
        const p = await c.newPage(); p.setDefaultTimeout(30000); watch(p, engine + '-' + v.name);
        await p.goto(URL_, { waitUntil: 'load', timeout: 180000 }); await sleep(300);
        const r = await p.evaluate(geomInPage, { maxH: args.maxRowH, minDD: MIN_DD, minSec: MIN_SEC, view: v.name });
        await geomShots(p, engine, v, r);
        if (!r.rows && !r.tables && !r.gantt) return SKIP('нет реестра, таблиц и Ганта');
        const hs = r.heights.slice().sort((a, b) => a - b);
        const data = { rows: r.rows, height: hs.length ? { min: hs[0], median: hs[Math.floor(hs.length / 2)], max: hs[hs.length - 1], maxId: r.tallest.id } : null,
          minDD: r.minDD, minSection: r.minSec, tables: r.tables, gantt: r.gantt, pageWidth: r.pageW, viewport: r.vw };
        const bad = [...r.bad, ...r.modal, ...r.tableBad, ...r.ganttBad];
        if (r.pageW > r.vw) bad.push(`ширина документа ${r.pageW} > ${r.vw} (горизонтальная прокрутка страницы)`);
        const sum = `строк ${r.rows}` + (data.height ? `, высота мин/мед/макс ${data.height.min}/${data.height.median}/${data.height.max} px (${data.height.maxId})` : '')
          + (r.minDD != null ? `, столбец значения ≥ ${r.minDD} px` : '') + `, таблиц ${r.tables}` + (r.gantt ? `, Гант: подписей ${r.gantt.labels}, вех ${r.gantt.milestones}${r.gantt.scroll ? ', прокрутка в рамке' : ''}` : '')
          + `, ширина ${r.pageW} ≤ ${r.vw}`;
        const res = bad.length ? FAIL(`${bad.length} проблем: ` + bad.slice(0, 8).join('; ') + ' | ' + sum) : OK(sum);
        res.data = data;
        return res;
      } finally { await c.close(); }
    });
  }
}

// ---------------------------------------------------------------- контраст ≥ 4,5:1 по computed color
const CONTRAST_SELS = ['.b', '.tag', '.st', '.st-ok', '.st-bad', '.st-unk', '.ok', '.badge-concept', '.risk', '.kcount', '.muted', 'figcaption',
  '.zoom', 'main a', 'nav.side a', 'summary', '.lblh', '.cmeta', '.count', '.eyebrow', '.kpi .n', '.kpi .l', '.kpi .s', 'dl.kv dt', '.dsec h4',
  '.gid', '.kid', '.gscale span', 'table.cm td', 'th', '.hsn', '.facts dt', '.lead', '.untitled', '.missing', 'code',
  '.pst', '.gst', '.gpl', '.gtd', '.kmoved', '.pg-sub', '.pg-ok', '.pg-warn', '.pst-go', '.kbv-r+label'];
// статусные чипы и подписи режима «Отслеживание» — отдельная проверка в трёх темах (доска «По фактам» включается)
const PG_CONTRAST_SELS = ['.pst', '.gst', '.gpl', '.gtd', '.kmoved', '.pgk .n', '.pgk .l', '.pgk .s', '.pg-sub', '.pg-ok', '.pg-warn', '.pst-go b', '.kbv-r+label', 'a.gh'];
function contrastInPage(sels) {
  const parse = s => { const m = /rgba?\(([^)]+)\)/.exec(s || ''); if (!m) return null; const p = m[1].split(/[\s,/]+/).filter(Boolean).map(parseFloat); return [p[0], p[1], p[2], p.length > 3 ? p[3] : 1]; };
  const lin = x => { x /= 255; return x <= 0.03928 ? x / 12.92 : Math.pow((x + 0.055) / 1.055, 2.4); };
  const lum = c => 0.2126 * lin(c[0]) + 0.7152 * lin(c[1]) + 0.0722 * lin(c[2]);
  const over = (top, base) => [0, 1, 2].map(i => top[i] * top[3] + base[i] * (1 - top[3]));
  const hex = c => '#' + c.map(x => Math.round(x).toString(16).padStart(2, '0')).join('');
  function bgOf(el) {
    const layers = [];
    for (let e = el; e; e = e.parentElement) {
      const cs = getComputedStyle(e);
      if (cs.backgroundImage && cs.backgroundImage !== 'none') return null;   // градиент/картинка — не оцениваем
      const c = parse(cs.backgroundColor);
      if (c && c[3] > 0) { layers.push(c); if (c[3] >= 0.999) break; }
    }
    let base = [255, 255, 255];
    for (let i = layers.length - 1; i >= 0; i--) base = layers[i][3] >= 0.999 ? layers[i].slice(0, 3) : over(layers[i], base);
    return base;
  }
  let checked = 0; const fails = [], seen = new Set();
  for (const sel of sels) {
    let n = 0;
    for (const el of document.querySelectorAll(sel)) {
      if (n >= 300) break;
      if (seen.has(el) || !el.getClientRects().length || el.closest('svg, .flowsvg, #lb')) continue;
      const text = (el.textContent || '').replace(/\s+/g, ' ').trim();
      if (!text) continue;
      const cs = getComputedStyle(el);
      if (cs.visibility === 'hidden' || +cs.opacity === 0) continue;
      const bg = bgOf(el), fg0 = parse(cs.color);
      if (!bg || !fg0) continue;
      seen.add(el); n++; checked++;
      const fg = fg0[3] < 1 ? over(fg0, bg) : fg0.slice(0, 3);
      const L1 = lum(fg), L2 = lum(bg), ratio = (Math.max(L1, L2) + 0.05) / (Math.min(L1, L2) + 0.05);
      const fs = parseFloat(cs.fontSize), fw = parseInt(cs.fontWeight, 10) || 400;
      const need = fs >= 24 || (fs >= 18.66 && fw >= 700) ? 3 : 4.5;
      if (ratio < need - 0.005) fails.push({ sel, text: text.slice(0, 32), ratio: Math.round(ratio * 100) / 100, need, fg: hex(fg), bg: hex(bg) });
    }
  }
  return { checked, fails };
}
async function contrastPass(br) {
  const c = await br.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1, colorScheme: 'light' });
  const p = await c.newPage(); p.setDefaultTimeout(30000); watch(p, 'contrast');
  await p.goto(URL_, { waitUntil: 'load', timeout: 180000 }); await sleep(300);
  await p.evaluate(() => { const tr = document.querySelector('#tb tr.row'); if (tr) (tr.querySelector('td.c-title') || tr.cells[2]).click(); });
  const modes = [['contrast-light', 'light', null], ['contrast-dark', 'dark', null], ['contrast-auto-dark', null, 'dark']];
  for (const [name, attr, scheme] of modes) {
    await check(page, name, async () => {
      await p.emulateMedia({ colorScheme: scheme || 'light' });
      await p.evaluate(a => { if (a) document.documentElement.setAttribute('data-theme', a); else document.documentElement.removeAttribute('data-theme'); }, attr);
      await sleep(80);
      const r = await p.evaluate(contrastInPage, CONTRAST_SELS);
      if (!r.checked) return SKIP('нет текстовых элементов');
      const uniq = []; const keys = new Set();
      for (const f of r.fails) { const k = f.sel + '|' + f.fg + '|' + f.bg; if (!keys.has(k)) { keys.add(k); uniq.push(f); } }
      if (uniq.length) return FAIL(`${r.fails.length} из ${r.checked} ниже порога: ` + uniq.slice(0, 8).map(f => `${f.sel} «${f.text}» ${f.ratio}:1 (${f.fg} на ${f.bg})`).join('; '));
      return OK(`проверено элементов ${r.checked}, все ≥ 4,5:1 (крупный текст ≥ 3:1)`);
    });
  }
  // статусные чипы прогресса: светлая, тёмная, «авто» при тёмной системной теме
  await p.evaluate(() => { const l = document.querySelector('label[for="kbv-facts"]'); if (l) l.click(); });
  for (const [name, attr, scheme] of [['progress-contrast-light', 'light', null], ['progress-contrast-dark', 'dark', null], ['progress-contrast-auto-dark', null, 'dark']]) {
    await check(page, name, async () => {
      if (!HAS_PG) return SKIP(NO_PG, true);
      await p.emulateMedia({ colorScheme: scheme || 'light' });
      await p.evaluate(a => { if (a) document.documentElement.setAttribute('data-theme', a); else document.documentElement.removeAttribute('data-theme'); }, attr);
      await sleep(80);
      const r = await p.evaluate(contrastInPage, PG_CONTRAST_SELS);
      const chips = await p.evaluate(() => document.querySelectorAll('.pst').length);
      if (!chips) return FAIL('нет статусных чипов');
      const uniq = []; const keys = new Set();
      for (const f of r.fails) { const k = f.sel + '|' + f.fg + '|' + f.bg; if (!keys.has(k)) { keys.add(k); uniq.push(f); } }
      if (uniq.length) return FAIL(`${r.fails.length} из ${r.checked} ниже порога: ` + uniq.slice(0, 8).map(f => `${f.sel} «${f.text}» ${f.ratio}:1 (${f.fg} на ${f.bg})`).join('; '));
      return OK(`чипов и подписей проверено ${r.checked}, все ≥ 4,5:1`);
    });
  }
  await c.close();
}

await geometryPass(browser, 'chromium');
await contrastPass(browser);

// ---------------------------------------------------------------- lite: картинки — файлы в assets/ рядом со страницей
await check(page, 'lite-assets', async () => {
  const urls = await page.evaluate(() => Object.values(JSON.parse((document.getElementById('d-img') || { textContent: '{}' }).textContent)).filter(u => typeof u === 'string' && !/^data:/.test(u)));
  if (!urls.length) return SKIP('страница автономная (собрана без --lite)', true);
  const outside = [], missing = [];
  for (const u of urls) {
    let rel = u; try { rel = decodeURIComponent(u.split('#')[0]); } catch (e) { /* как есть */ }
    const p = path.resolve(PAGE_DIR, rel);
    if (!p.startsWith(PAGE_DIR + path.sep)) outside.push(u); else if (!fs.existsSync(p)) missing.push(u);
  }
  if (outside.length) return FAIL('ссылки на картинки вне папки страницы: ' + outside.slice(0, 3).join(', '));
  if (missing.length) return FAIL(`нет файлов (${missing.length} из ${urls.length}): ` + missing.slice(0, 3).join(', '));
  const thumbs = await page.evaluate(() => Object.keys(JSON.parse((document.getElementById('d-thumb') || { textContent: '{}' }).textContent)).length);
  const key = await page.evaluate(() => {
    const m = JSON.parse(document.getElementById('d-img').textContent), al = JSON.parse((document.getElementById('d-alias') || { textContent: '{}' }).textContent);
    const f = [...document.querySelectorAll('figure.lb[data-key]')].find(x => { const k = al[x.dataset.key] || x.dataset.key; return m[k] && !/^data:/.test(m[k]) && x.offsetParent; });
    document.querySelectorAll('[data-smoke-lite]').forEach(x => x.removeAttribute('data-smoke-lite'));
    if (f) f.setAttribute('data-smoke-lite', ''); return f ? f.dataset.key : null;
  });
  let info = '';
  if (key) {
    const fig = page.locator('figure.lb[data-smoke-lite]');
    await fig.scrollIntoViewIfNeeded(); await sleep(400);
    const prev = await page.evaluate(() => { const im = document.querySelector('figure.lb[data-smoke-lite] img'); return { src: (im.currentSrc || im.src || '').slice(0, 40), w: im.naturalWidth }; });
    await fig.click(); await page.waitForSelector('#lb.open');
    await page.waitForFunction(() => { const im = document.getElementById('lbimg'); return im.naturalWidth > 0 && !/^data:/.test(im.getAttribute('src') || ''); }, null, { timeout: 15000 });
    const w = await page.evaluate(() => document.getElementById('lbimg').naturalWidth);
    await page.keyboard.press('Escape');
    if (!prev.w) return FAIL('превью не загрузилось: ' + prev.src);
    info = `, превью «${key}» загружено, в лайтбоксе — полный файл ${w} px`;
  }
  return OK(`ссылок на assets/: ${urls.length}, все файлы на месте, миниатюр в странице: ${thumbs}${info}; локальных файлов запрошено: ${localFiles.size}`);
});

// ---------------------------------------------------------------- WebKit (Safari): та же геометрия
let wk = null;
if (args.engines.includes('webkit')) {
  wk = await launchWebkit();
  if (wk) await geometryPass(wk.browser, 'webkit');
  else for (const v of GEOM_VIEWS) await check(page, `geometry-webkit-${v.name}`, async () => SKIP('WebKit не установлен в кэше Playwright: npx --prefix <node-dir> playwright install webkit', true));
}

// ---------------------------------------------------------------- итог
checks.push({ name: 'console-errors', status: errors.length ? 'fail' : 'pass', detail: errors.length ? errors.slice(0, 5).join(' | ') : '0' });
checks.push({ name: 'external-requests', status: external.length ? 'fail' : 'pass', detail: external.length ? external.slice(0, 5).join(' | ') : '0' });
await browser.close();
if (wk) await wk.browser.close();

const reqAll = args.require.includes('all');
for (const c of checks) {   // --require all не требует проверок, пропущенных из-за окружения (нет WebKit, страница без --lite)
  if (c.status === 'skip' && ((reqAll && !c.env) || args.require.includes(c.name))) { c.status = 'fail'; c.detail = 'обязательная проверка пропущена: ' + c.detail; }
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
