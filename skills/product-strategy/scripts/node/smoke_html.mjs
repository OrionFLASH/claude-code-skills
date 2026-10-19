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
// Геометрия (1440×900, 820×1180 и 390×844, Chromium и WebKit): раскрывает КАЖДУЮ строку реестра и меряет её — строка
// display:table-row, столбец значения dl.kv ≥ 120 px, секция ≥ 200 px, карточка в видимой части реестра, ничего не торчит
// из карточки, нет заголовка-«сироты» внизу колонки; высота ≥ --max-row-height (2500 px) — ПРЕДУПРЕЖДЕНИЕ (статус warn), не
// провал; карточка в окне P-id — те же правила; таблицы: на 1440 не шире рамки, последняя колонка не обрезана, на 820/390 —
// прокрутка внутри рамки; на 1440 — предупреждение «пустая область» (колонка > 40 % ширины таблицы при медиане текста < 20
// знаков, если таблица упирается в рамку);
// Гант: подписи месяцев не обрезаны, ромбы вех внутри диаграммы; ширина документа ≤ ширины окна.
// Контраст ≥ 4,5:1 (крупный текст ≥ 3:1) по computed color для бейджей, тегов, подписей, ссылок — в светлой, тёмной и
// «авто» при тёмной системной теме. WebKit берётся из playwright или из кэша ~/Library/Caches/ms-playwright
// (webkit-*); нет WebKit — проверка «skip» с пояснением (условие окружения, --require all его не требует).
// Режим «Отслеживание» (есть раздел #progress, т. е. data/progress.json): раздел и плитки, фильтр статуса и быстрые фильтры
// реестра (число строк меняется), сортировка по статусу, поля статуса в CSV, карточка с блоком «Выполнение», Гант с
// линией «Сегодня» внутри диаграммы на 1440 и 390 px, модалка задачи со статусами, переключатель Kanban «Как в плане / По
// фактам», ссылки только https://github.com/, контраст статусных чипов в трёх темах, нет переполнения на 390 px.
// Раздела нет — эти проверки «skip» по условию (страница без прогресса), --require all их не требует.
// Интерактивные графики (charts/<ключ>.meta.json → встроенный SVG с панелью пояснений; references/interactive-site.md, 2.3–2.4):
// все графики смонтированы (site: assets/charts-*.js подгружены), у каждого «Как читать график», элементы ↔ пояснения 1:1, одна
// остановка Tab на график; клик по выборке элементов (≤ 40 на график, у маленьких — все) открывает непустую панель, плюс клики
// мышью; клавиатура (→ без панели двигает фокус, Enter/Space открывают, ←/→ по кругу, Esc закрывает и возвращает фокус); при печати
// панель скрыта; легенда подсвечивает группу, подпись data-ps-ref открывает элемент, подсказка при наведении; каждая уникальная
// ссылка из пояснений разрешается роутером и ведёт к видимой цели (и по 2 ссылки каждого вида — настоящим кликом в панели);
// глубокая ссылка #chart/<ключ>/<id> после загрузки; на 390 px — нижний лист без горизонтальной прокрутки; контраст панели в
// трёх темах и контура выбранного элемента ≥ 3:1. В WebKit и Firefox (если запускается) — клик, →, Esc и ссылка из панели.
// Lite-страница (build_html.py --lite): картинки assets/ рядом со страницей существуют и грузятся; локальные файлы
// разрешены только внутри папки страницы, всё прочее — «внешний запрос».
// Сайт (build_html.py по умолчанию, режим site: index.html + assets/ + data/): передайте deliverables/index.html или <OUT>.
// Те же проверки, что для single, плюс: страница открыта по file://, все ссылки assets/* (css, js, img, миниатюры) существуют,
// нет инлайн-скриптов (CSP script-src 'self'), нарушений CSP, 404 и ошибок консоли, внешних запросов 0, data/*.csv|json на
// месте и совпадают с реестром страницы; размеры: index.html > 1 МБ — предупреждение, сайт > 25 МБ — совет. Загрузка по file://
// проверяется отдельно в каждом доступном движке (Chromium, WebKit, Firefox); итог печатается списком «проверено на: …».
// Слой интерактивности 1.5 (FB-035/036, references/interactive-site.md, п. 3): то, что ВИДИТ пользователь, — у каждого графика и схемы
// видимая кнопка «🔍 Увеличить» (на 390 px ≥ 44×32 и не на заголовке графика), курсор zoom-in на фоне и pointer на элементах, строка
// «Графики и схемы кликабельны…» вверху и в разделах; настоящее наведение мышью (без force) показывает подсказку «название + что это» в
// пределах окна и контур; клик → непустая панель; «🔍» / клик по фону / Enter на кнопке открывают просмотр с ЖИВЫМ SVG (не <img>):
// «+», колесо, перетаскивание меняют transform, «Сброс» возвращает, Tab не выходит из окна, Esc закрывает и возвращает фокус на кнопку;
// в просмотре элементы (выборка ≤ 40 на график, все блоки схем) нажимаются там, где они сверху, иначе — через список; P-id открывает
// карточку поверх просмотра; телефон: просмотр на весь экран, нижний лист, щипок и двойное касание; печать без кнопок и подсказок;
// одна обёртка и одна кнопка на график (идемпотентность). Те же проверки по каждому графику и схеме — в WebKit (и Firefox, если запускается).
// На странице без слоя (до 1.5) проверки падают со списком провалов по каждому графику. Поиск по странице («/», часть слова, е/ё,
// фраза, фильтр, подсветка на странице), сущности текста (нет «мёртвых» P-/G-id и «раздел N»), просмотр макетов («Открыть интерактивный
// макет», вторая тема), Гант без обрезанных подписей. Компонент, заменённый расширением (PS.replace('lightbox'|'viewer'|'search'|
// 'entities'), — его проверки «skip» с пояснением (условие окружения), а не провал. Поиск конкурентов — по названию из данных, без
// заданных фраз.
// Нет данных для проверки — она «skip» (не провал), если не перечислена в --require (all — любая пропущенная проверка
// данных считается провалом). Статус «warn» — предупреждение (итог «пройдено с предупреждениями», код выхода 0).
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
const USAGE = 'node smoke_html.mjs <index.html | OUT> [--node-dir <dir>] [--require all|a,b] [--engines chromium,webkit,firefox] '
  + '[--max-row-height 2500] [--shots <dir>] [--json] [--headed]';

function parseArgs(argv) {
  const a = { target: null, nodeDir: null, require: [], shots: null, json: false, headed: false, engines: ['chromium', 'webkit', 'firefox'], maxRowH: 2500 };
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
let IS_SITE = false;
const counts = {};
const SKIP = (reason, env) => ({ skip: reason, env: !!env });
const OK = (detail) => ({ ok: true, detail });
const FAIL = (detail) => ({ ok: false, detail });
const WARN = (detail) => ({ ok: true, warn: true, detail });   // предупреждение: не провал, но в итоге отдельной строкой
const sleep = ms => new Promise(r => setTimeout(r, ms));
// скрипт, который Playwright добавляет в каждую страницу: единый доступ к данным (site: window.PS_DATA; single: <script type=application/json>)
// и сбор нарушений CSP (securitypolicyviolation)
const INIT = () => {
  window.__psData = id => {
    const D = window.PS_DATA;
    if (D && Object.prototype.hasOwnProperty.call(D, id)) return D[id];
    const e = document.getElementById(id);
    try { return e ? JSON.parse(e.textContent) : null; } catch (x) { return null; }
  };
  window.__cspv = [];
  document.addEventListener('securitypolicyviolation', e => window.__cspv.push((e.violatedDirective || '') + ' ' + (e.blockedURI || '')));
};
const warnings = [];       // советы и предупреждения (не провалы)
const engines = [];        // {name, version, status: tested|unavailable, scope: [...], note}

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
  try { await page.evaluate(() => { if (window.PSI && PSI.close) PSI.close(); }); await closeLayers(page); } catch (e) { /* страница могла закрыться */ }
  const status = res && res.skip ? 'skip' : res && res.ok ? (res.warn ? 'warn' : 'pass') : 'fail';
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
await ctx.addInitScript(INIT);
const page = await ctx.newPage();
page.setDefaultTimeout(10000);
watch(page, 'desktop');
await page.goto(URL_, { waitUntil: 'load' });
await sleep(300);
// компоненты, которые взяло на себя расширение страницы (build/extra*.js → PS.replace): их встроенные проверки — skip с пояснением
const REPLACED = await page.evaluate(() => (window.PS && PS.replaced) ? PS.replaced() : []).catch(() => []);
const replacedSkip = n => REPLACED.includes(n) ? SKIP(`компонент «${n}» заменён расширением страницы (PS.replace) — проверяет слой расширения`, true) : null;

// ---------------------------------------------------------------- счётчики
await check(page, 'counts', async () => {
  Object.assign(counts, await page.evaluate(() => ({
    sections: document.querySelectorAll('main > section').length,
    nav: document.querySelectorAll('nav.side a[data-sec]').length,
    rows: document.querySelectorAll('#tb tr.row').length,
    figures: document.querySelectorAll('figure.lb').length,
    images: Object.keys(window.__psData('d-img') || {}).length,
    pid_links: document.querySelectorAll('a.pid').length,
    gantt_rows: document.querySelectorAll('.grow[data-g]').length,
    kanban_cards: document.querySelectorAll('.kcard[data-k]').length,
    flow_nodes: document.querySelectorAll('.flowsvg [data-node].fnode').length,
    refcards: document.querySelectorAll('article.ref').length,
    competitors: document.querySelectorAll('.ccard').length,
    csp: !!document.querySelector('meta[http-equiv="Content-Security-Policy"][content*="default-src \'none\'"]'),
    site: !!window.PS_DATA && !!document.querySelector('script[src*="data.js"]'),
    referrer: !!document.querySelector('meta[name="referrer"][content="no-referrer"]'),
  })));
  if (!counts.sections) return FAIL('нет разделов main > section');
  if (counts.nav !== counts.sections) return FAIL(`ссылок навигации ${counts.nav}, разделов ${counts.sections}`);
  if (!counts.csp) {
    // site без CSP-мета допустим только как запасной вариант (--site-csp none): referrer no-referrer и «внешних запросов 0»
    if (!(counts.site && counts.referrer)) return FAIL('нет CSP default-src none');
    warnings.push('страница site собрана без CSP-мета (запасной вариант --site-csp none): защита — referrer no-referrer и проверка «внешних запросов 0»');
  }
  IS_SITE = counts.site;
  return OK(`режим ${counts.site ? 'site' : 'single/lite'}, разделов ${counts.sections}, строк ${counts.rows}, фигур ${counts.figures}, P-ссылок ${counts.pid_links}`);
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
    const reg = (window.__psData('d-registry') || []), ids = new Set(reg.map(r => r.id));
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
  if (replacedSkip('lightbox')) return replacedSkip('lightbox');
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
  if (replacedSkip('lightbox')) return replacedSkip('lightbox');
  // фигура, у референса (или подсказок макета m:<ключ>) которой есть зоны с координатами; описания без координат — только список
  await page.evaluate(() => { const refs = window.__psData('d-refs') || {}; document.querySelectorAll('[data-smoke-hs]').forEach(x => x.removeAttribute('data-smoke-hs'));
    const f = [...document.querySelectorAll('figure.lb[data-ref]')].find(x => x.offsetParent && ((refs[x.dataset.ref] || {}).hotspots || []).some(h => h.l != null));
    if (f) f.setAttribute('data-smoke-hs', ''); });
  const fig = page.locator('figure.lb[data-smoke-hs]').first();
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
  if (replacedSkip('lightbox')) return replacedSkip('lightbox');
  const id = await page.evaluate(() => {
    const reg = (window.__psData('d-registry') || []);
    const img = (window.__psData('d-img') || {});
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
// блок схемы — настоящим кликом мыши в точке, где он сверху (без force: FB-036)
await check(page, 'flow-node', async () => {
  const n = await page.locator('.flowsvg [data-node].fnode').count();
  if (!n) return SKIP('нет: узлов схемы');
  let pt = null;
  for (let i = 0; i < n && !pt; i++) pt = await page.evaluate(topPoint, ['.flowsvg [data-node].fnode', i]);
  if (!pt) return FAIL('ни один блок схемы нельзя нажать мышью: все перекрыты');
  await page.mouse.click(pt.x, pt.y);
  await page.waitForSelector('#im.open');
  const t = (await page.textContent('#imtitle')).trim(), b = (await page.textContent('#imbody')).trim();
  if (!t || !b) return FAIL('пустая модалка');
  return OK(t.slice(0, 70));
});

// ---------------------------------------------------------------- конкуренты
await check(page, 'competitors', async () => {
  const total = await page.locator('.ccard').count();
  if (!total) return SKIP('нет конкурентов');
  // название — из данных карточки (d-comp по data-slug), а не первые слова заголовка: в заголовке после имени идёт вердикт
  const name = await page.evaluate(i => { const c = document.querySelectorAll('.ccard')[i], slug = c && c.dataset.slug;
    const d = (window.__psData('d-comp') || []).find(x => x.slug === slug); return ((d && d.name) || (c.querySelector('h4 a') || c.querySelector('h4')).textContent).trim(); }, Math.min(1, total - 1));
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
    const reg = (window.__psData('d-registry') || []);
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
    const r = await page.evaluate(q => { const reg = Object.fromEntries(window.__psData('d-registry').map(x => [x.id, x]));
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
  const id = await page.evaluate(() => { const reg = window.__psData('d-registry');
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

// ---------------------------------------------------------------- интерактивные графики (references/interactive-site.md, 2.3–2.4)
// Графики с charts/<ключ>.meta.json — встроенный SVG (site: подгружается из assets/charts-<группа>.js). Клик по выборке элементов
// (все у графиков ≤ 40 элементов, иначе 40 равномерно; полный обход — tests/test_charts_ui.py) открывает непустую панель; настоящие
// клики мышью по точке, где элемент сверху; клавиатура (Enter, ←/→, Esc возвращает фокус); подпись-ссылка и легенда; «Как читать
// график»; подсказка при наведении; все ссылки из пояснений разрешаются и ведут к видимой цели; глубокая ссылка #chart/<ключ>/<id>.
const CH_SAMPLE = 40;
// Нет интерактивных графиков (старый прогон без meta или графиков нет) — «skip» по условию, как у прогресса: --require all его не требует
// (сборщик в этом случае печатает предупреждение «графики без пояснений»).
const NO_CH = 'нет интерактивных графиков (нет charts/<ключ>.meta.json — графики статичные или их нет)';
const HAS_CH = (await page.locator('figure.ps-ichart').count()) > 0;
async function chartsReady(p) {
  return p.evaluate(() => new Promise(res => { if (!window.PS_ROUTER) { res(false); return; } const t = setTimeout(() => res(false), 20000); PS_ROUTER.loadAll(() => { clearTimeout(t); res(true); }); }));
}
function chartsInPage() {     // по одному экземпляру на ключ (основной — в разделе «Графики»)
  const figs = [...document.querySelectorAll('figure.ps-ichart')], seen = new Set(), out = [];
  for (const f of figs.filter(x => x.classList.contains('ps-primary')).concat(figs)) {
    const key = f.dataset.chart; if (seen.has(key)) continue; seen.add(key);
    const svg = f.querySelector('svg[data-ps-chart]'), meta = PS_ROUTER.meta(key) || {};
    const ids = svg ? [...svg.querySelectorAll('.ps-el[data-ps-el]')].map(e => e.getAttribute('data-ps-el')) : [];
    const mids = (meta.elements || []).map(e => e.id);
    out.push({ key, ids: mids, n: ids.length, ready: f.classList.contains('ps-ready'), howto: ((f.querySelector('.ps-howto') || {}).textContent || '').trim().length,
      noMeta: ids.filter(i => !mids.includes(i)), noEl: mids.filter(i => !ids.includes(i)), img: !!f.querySelector('img'),
      tabstops: svg ? svg.querySelectorAll('.ps-el[tabindex="0"]').length : 0, svgKey: svg ? svg.getAttribute('data-ps-chart') : null });
  }
  return { figs: figs.length, charts: out };
}
const sampleIds = ids => ids.length <= CH_SAMPLE ? ids : Array.from({ length: CH_SAMPLE }, (_, i) => ids[Math.round(i * (ids.length - 1) / (CH_SAMPLE - 1))]);
function clickInPage({ key, ids }) {      // синтетический клик (делегированный обработчик) → панель
  const q = s => window.CSS && CSS.escape ? CSS.escape(s) : s;
  const f = document.querySelector(`figure.ps-ichart.ps-primary[data-chart="${q(key)}"]`) || document.querySelector(`figure.ps-ichart[data-chart="${q(key)}"]`);
  const bad = []; let ok = 0;
  for (const id of ids) {
    const el = f.querySelector(`svg [data-ps-el="${q(id)}"]`);
    if (!el) { bad.push(id + ': нет элемента'); continue; }
    el.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
    const st = PS_ROUTER.state(), cp = document.getElementById('cp');
    const title = document.getElementById('cp-title').textContent.trim(), secs = document.querySelectorAll('#cp-body > section').length;
    const vis = !!cp && !cp.hidden && cp.getBoundingClientRect().width > 0, ring = !!f.querySelector('.ps-ovl .ps-sel-line');
    if (!vis || st.key !== key || st.id !== id || !title || !secs || !ring || !el.classList.contains('ps-on'))
      bad.push(`${id}: панель ${vis}, выбран ${st.id}, заголовок «${title.slice(0, 24)}», блоков ${secs}, контур ${ring}`);
    else ok++;
  }
  PS_ROUTER.close();
  return { ok, bad };
}
function hitPoint({ key, id }) {          // точка, где элемент (или его подпись data-ps-ref) — верхний под курсором
  const q = s => window.CSS && CSS.escape ? CSS.escape(s) : s;
  const f = document.querySelector(`figure.ps-ichart.ps-primary[data-chart="${q(key)}"]`) || document.querySelector(`figure.ps-ichart[data-chart="${q(key)}"]`);
  const el = f && f.querySelector(`svg [data-ps-el="${q(id)}"]`); if (!el) return null;
  el.scrollIntoView({ block: 'center', inline: 'center', behavior: 'instant' });
  for (const c of [el, ...el.querySelectorAll('*')]) {
    const r = c.getBoundingClientRect(); if (!r.width && !r.height) continue;
    for (const [fx, fy] of [[0.5, 0.5], [0.15, 0.5], [0.85, 0.5], [0.5, 0.2], [0.5, 0.8]]) {
      const x = r.left + r.width * fx, y = r.top + r.height * fy;
      if (x < 1 || y < 1 || x >= innerWidth - 1 || y >= innerHeight - 1) continue;
      const g = (document.elementFromPoint(x, y) || {}).closest?.('[data-ps-ref], .ps-el');
      if (g && (g.getAttribute('data-ps-ref') || g.getAttribute('data-ps-el')) === id && g.closest('figure.ps-ichart') === f) return { x, y };
    }
  }
  return null;
}
function verifyInPage(h) {               // после перехода: цель существует и видна на экране
  const r = PS_ROUTER.parse(h); if (!r) return 'ссылка не разбирается';
  const inView = el => { if (!el || !el.getClientRects().length) return false; const b = el.getBoundingClientRect(); return b.bottom > 0 && b.top < innerHeight && b.right > 0 && b.left < innerWidth; };
  const q = s => window.CSS && CSS.escape ? CSS.escape(s) : s;
  switch (r.t) {
    case 'sec': return inView(document.getElementById('s-' + r.n)) ? '' : 'раздел не на экране';
    case 'prow': { const tr = document.querySelector(`#tb tr.row.open[data-id="${q(r.id)}"]`); return tr && inView(tr) ? '' : 'строка реестра не раскрыта или не видна'; }
    case 'reg': {
      if (r.bare) return inView(document.getElementById('registry')) ? '' : 'реестр не на экране';
      const rows = [...document.querySelectorAll('#tb tr.row')];
      const sel = Object.entries(r.f).every(([k, v]) => { const s = document.querySelector(`#registry select[data-f="${k}"]`); return !s || s.value === v; });
      const cat = !r.f.category || rows.every(x => x.dataset.cat === r.f.category);
      return sel && cat && inView(document.getElementById('registry')) ? '' : `фильтр не применён (строк ${rows.length})`;
    }
    case 'chart': {
      const st = PS_ROUTER.state(), f = PS_ROUTER.resolve(h);
      if (!r.id) return inView(f) ? '' : 'график не на экране';
      const el = f && f.querySelector(`svg [data-ps-el="${q(r.id)}"]`);
      return st.open && st.key === r.key && st.id === r.id && inView(el) ? '' : `элемент не выбран (выбран ${st.key}/${st.id})`;
    }
    default: { const st = PS_ROUTER.state(); return inView(PS_ROUTER.resolve(h)) && !st.open ? '' : 'цель не на экране или панель не закрылась'; }
  }
}
await check(page, 'charts-structure', async () => {
  if (!HAS_CH) return SKIP(NO_CH, true);
  if (!await chartsReady(page)) return FAIL('файлы графиков не подгрузились (PS_ROUTER.loadAll)');
  const r = await page.evaluate(chartsInPage);
  const bad = [];
  for (const c of r.charts) {
    if (!c.ready || c.svgKey !== c.key) bad.push(`${c.key}: не смонтирован`);
    if (!c.howto) bad.push(`${c.key}: нет «Как читать график»`);
    if (c.img) bad.push(`${c.key}: <img> вместо встроенного SVG`);
    if (c.noMeta.length) bad.push(`${c.key}: элементы без пояснения ${c.noMeta.slice(0, 3).join(', ')}`);
    if (c.noEl.length) bad.push(`${c.key}: пояснения без элемента ${c.noEl.slice(0, 3).join(', ')}`);
    if (c.tabstops !== 1) bad.push(`${c.key}: остановок Tab ${c.tabstops} (нужна 1, внутри — ←/→)`);
  }
  Object.assign(counts, { charts: r.charts.length, chart_figures: r.figs, chart_elements: r.charts.reduce((a, c) => a + c.n, 0) });
  if (bad.length) return FAIL(bad.slice(0, 6).join('; '));
  return OK(`графиков ${r.charts.length} (вставок ${r.figs}), элементов ${counts.chart_elements}; у каждого howto, 1 остановка Tab`);
});
await check(page, 'charts-click', async () => {
  if (!HAS_CH) return SKIP(NO_CH, true);
  const r = await page.evaluate(chartsInPage);
  let ok = 0, n = 0, real = 0, nohit = 0; const bad = [];
  for (const c of r.charts) {
    const ids = sampleIds(c.ids); n += ids.length;
    const res = await page.evaluate(clickInPage, { key: c.key, ids });
    ok += res.ok; bad.push(...res.bad.map(x => c.key + '/' + x));
    for (const id of [...new Set([ids[0], ids[Math.floor(ids.length / 2)], ids[ids.length - 1]])]) {      // настоящие клики мышью
      const pt = await page.evaluate(hitPoint, { key: c.key, id });
      if (!pt) { nohit++; continue; }
      await page.mouse.click(pt.x, pt.y); await sleep(30);
      const st = await page.evaluate(() => ({ s: PS_ROUTER.state(), t: document.getElementById('cp-title').textContent.trim() }));
      if (!st.s.open || st.s.key !== c.key || st.s.id !== id || !st.t) bad.push(`${c.key}/${id}: клик мышью открыл ${st.s.key}/${st.s.id}`); else real++;
      await page.keyboard.press('Escape'); await sleep(20);
    }
  }
  await shot(page, 'desktop-chart-panel');
  if (bad.length) return FAIL(`${bad.length} из ${n}: ` + bad.slice(0, 5).join('; '));
  if (!real) return FAIL('ни один элемент не кликается мышью (перекрыт)');
  if (nohit) warnings.push(`графики: у ${nohit} элементов выборки нет точки, где они сверху (перекрыты соседями) — клик мышью не проверен`);
  return OK(`панель открыта для ${ok} из ${n} элементов выборки (≤ ${CH_SAMPLE} на график), кликов мышью ${real}`);
});
await check(page, 'charts-keyboard', async () => {
  if (!HAS_CH) return SKIP(NO_CH, true);
  const c = (await page.evaluate(chartsInPage)).charts.find(x => x.ids.length >= 3);
  if (!c) return SKIP('нет графика с 3+ элементами');
  const sel = `figure.ps-ichart.ps-primary[data-chart="${c.key}"] svg [data-ps-el="${c.ids[0]}"]`;
  await page.evaluate(s => { const el = document.querySelector(s); el.scrollIntoView({ block: 'center' }); el.focus(); }, sel);
  const state = () => page.evaluate(() => ({ s: PS_ROUTER.state(), a: document.activeElement && document.activeElement.getAttribute('data-ps-el'), cp: !document.getElementById('cp').hidden }));
  await page.keyboard.press('ArrowRight'); const f1 = await state();
  if (f1.cp || f1.a !== c.ids[1]) return FAIL(`→ без панели: фокус ${f1.a}, ожидался ${c.ids[1]}`);
  await page.keyboard.press('ArrowLeft');
  await page.keyboard.press('Enter'); const s1 = await state();
  if (!s1.cp || s1.s.id !== c.ids[0] || s1.a !== c.ids[0]) return FAIL('Enter не открыл панель: ' + JSON.stringify(s1));
  await page.keyboard.press('ArrowRight'); const s2 = await state();
  if (s2.s.id !== c.ids[1] || s2.a !== c.ids[1]) return FAIL('→ не перешёл к следующему элементу: ' + JSON.stringify(s2));
  await page.keyboard.press('ArrowLeft'); await page.keyboard.press('ArrowLeft'); const s3 = await state();
  if (s3.s.id !== c.ids[c.ids.length - 1]) return FAIL('← с первого элемента не перешёл к последнему: ' + s3.s.id);
  await page.keyboard.press(' '); const s4 = await state();
  if (!s4.cp || s4.s.id !== c.ids[c.ids.length - 1]) return FAIL('Space не открыл элемент');
  const hash = await page.evaluate(() => location.hash);
  await page.keyboard.press('Escape'); const s5 = await state();
  if (s5.cp || s5.a !== c.ids[c.ids.length - 1]) return FAIL(`Esc: панель ${s5.cp}, фокус ${s5.a}`);
  const hash2 = await page.evaluate(() => location.hash);
  await page.emulateMedia({ media: 'print' });
  await page.evaluate(s => document.querySelector(s).dispatchEvent(new MouseEvent('click', { bubbles: true })), sel);
  const printHidden = await page.evaluate(() => getComputedStyle(document.getElementById('cp')).display === 'none');
  await page.emulateMedia({ media: 'screen' }); await page.keyboard.press('Escape');
  if (!printHidden) return FAIL('панель видна при печати');
  return OK(`${c.key}: → без панели, Enter, →, ← по кругу, Space, Esc вернул фокус; hash ${hash} → «${hash2}»; при печати панель скрыта`);
});
await check(page, 'charts-legend-ref-howto', async () => {
  if (!HAS_CH) return SKIP(NO_CH, true);
  const r = await page.evaluate(() => {
    const out = {};
    const leg = document.querySelector('figure.ps-ichart.ps-ready svg .ps-el[data-ps-highlight]');
    if (leg) { leg.dispatchEvent(new MouseEvent('click', { bubbles: true })); const svg = leg.ownerSVGElement;
      out.legend = { id: leg.getAttribute('data-ps-el'), on: svg.classList.contains('ps-hl-on'), n: svg.querySelectorAll('.ps-hl').length, txt: /подсвечено/.test(document.getElementById('cp-body').textContent), sel: PS_ROUTER.state().id };
      PS_ROUTER.close(); out.legend.off = !svg.classList.contains('ps-hl-on'); }
    const ref = [...document.querySelectorAll('figure.ps-ichart.ps-ready svg [data-ps-ref]')].find(x => !x.closest('.ps-el') || x.closest('.ps-el').getAttribute('data-ps-el') !== x.getAttribute('data-ps-ref'));
    if (ref) { ref.dispatchEvent(new MouseEvent('click', { bubbles: true })); out.ref = { want: ref.getAttribute('data-ps-ref'), got: PS_ROUTER.state().id }; PS_ROUTER.close(); }
    const btn = document.querySelector('figure.ps-ichart .ps-howto-btn');
    if (btn) { btn.click(); const hw = document.getElementById(btn.getAttribute('aria-controls')); out.howto = { vis: !!hw && !hw.hidden && hw.getClientRects().length > 0, exp: btn.getAttribute('aria-expanded'), len: hw ? hw.textContent.trim().length : 0, dl: hw ? hw.querySelectorAll('.ps-legend dt').length : 0 }; btn.click(); }
    return out;
  });
  if (!r.legend) return FAIL('нет пунктов легенды (data-ps-highlight)');
  if (!r.legend.on || !r.legend.n || !r.legend.txt || r.legend.sel !== r.legend.id || !r.legend.off) return FAIL('легенда: ' + JSON.stringify(r.legend));
  if (r.ref && r.ref.got !== r.ref.want) return FAIL(`подпись data-ps-ref=${r.ref.want} открыла ${r.ref.got}`);
  if (!r.howto || !r.howto.vis || r.howto.exp !== 'true' || r.howto.len < 20) return FAIL('«Как читать график»: ' + JSON.stringify(r.howto));
  // подсказка при наведении
  const c = (await page.evaluate(chartsInPage)).charts[0];
  const pt = await page.evaluate(hitPoint, { key: c.key, id: c.ids[Math.floor(c.ids.length / 2)] });
  let tip = 'не проверена (нет точки)';
  if (pt) { await page.mouse.move(pt.x, pt.y); await page.mouse.move(pt.x + 1, pt.y + 1); await sleep(50);
    const t = await page.evaluate(() => { const e = document.getElementById('cp-tip'); return e && !e.hidden ? e.textContent : ''; });
    if (!t) return FAIL('нет подсказки при наведении'); tip = `«${t.slice(0, 30)}»`; await page.mouse.move(2, 2); }
  return OK(`легенда ${r.legend.id}: подсвечено ${r.legend.n}; ${r.ref ? 'подпись → ' + r.ref.got : 'подписей-ссылок нет'}; howto ${r.howto.len} зн., легенда ${r.howto.dl}; подсказка ${tip}`);
});
await check(page, 'charts-links', async () => {
  if (!HAS_CH) return SKIP(NO_CH, true);
  const hrefs = await page.evaluate(() => { const hs = new Set(); document.querySelectorAll('figure.ps-ichart').forEach(f => { ((PS_ROUTER.meta(f.dataset.chart) || {}).elements || []).forEach(e => (e.links || []).forEach(l => hs.add(l.href))); }); return [...hs]; });
  if (!hrefs.length) return FAIL('в пояснениях графиков нет ни одной ссылки');
  const bad = [], types = {};
  for (const h of hrefs) {      // переход роутером к каждой уникальной ссылке
    const err = await page.evaluate(h => new Promise(res => { if (!PS_ROUTER.resolve(h)) { res('нет цели на странице'); return; } PS_ROUTER.go(h);
      requestAnimationFrame(() => requestAnimationFrame(() => res(''))); }), h);
    const v = err || await page.evaluate(verifyInPage, h);
    const t = h.replace(/^#(\w+).*/, '$1'); types[t] = (types[t] || 0) + 1;
    if (v) bad.push(`${h}: ${v}`);
  }
  // настоящие клики по ссылкам в панели: по 2 ссылки каждого вида
  const sample = await page.evaluate(() => {
    const by = {}; document.querySelectorAll('figure.ps-ichart.ps-primary').forEach(f => { ((PS_ROUTER.meta(f.dataset.chart) || {}).elements || []).forEach(e => (e.links || []).forEach(l => {
      const t = l.href.replace(/^#(\w+).*/, '$1'); by[t] = by[t] || []; if (by[t].length < 2 && !by[t].some(x => x.href === l.href)) by[t].push({ key: f.dataset.chart, id: e.id, href: l.href }); })); });
    return Object.values(by).flat();
  });
  let clicked = 0;
  for (const s of sample) {
    await page.evaluate(s => { PS_ROUTER.go('#chart/' + s.key + '/' + s.id); }, s); await sleep(30);
    const a = page.locator(`#cp-body a[href="${s.href}"]`).first();
    if (!await a.count()) { bad.push(`${s.key}/${s.id}: в панели нет ссылки ${s.href}`); continue; }
    await a.scrollIntoViewIfNeeded(); await a.click(); await sleep(60);
    const v = await page.evaluate(verifyInPage, s.href);
    if (v) bad.push(`клик ${s.href} (из ${s.key}/${s.id}): ${v}`); else clicked++;
  }
  const back = await page.evaluate(() => { const r = document.getElementById('reg-reset'); if (r) r.click(); PS_ROUTER.close(); return location.hash; });
  if (bad.length) return FAIL(`${bad.length} из ${hrefs.length}: ` + bad.slice(0, 5).join('; '));
  return OK(`уникальных ссылок ${hrefs.length} (${Object.entries(types).map(([k, v]) => k + ' ' + v).join(', ')}) — все цели есть и видны; кликов в панели ${clicked}; hash ${back}`);
});
await check(page, 'charts-deeplink', async () => {
  if (!HAS_CH) return SKIP(NO_CH, true);
  const cs = (await page.evaluate(chartsInPage)).charts;
  const c = cs[cs.length - 1], id = c.ids[Math.min(2, c.ids.length - 1)];
  const c2 = await ctx.newPage(); watch(c2, 'deeplink');
  try {
    await c2.goto(URL_ + '#chart/' + c.key + '/' + encodeURIComponent(id), { waitUntil: 'load' });
    await c2.waitForFunction(() => window.PS_ROUTER && PS_ROUTER.state().open, null, { timeout: 15000 });
    const st = await c2.evaluate(() => ({ s: PS_ROUTER.state(), a: document.activeElement && document.activeElement.getAttribute('data-ps-el'), t: document.getElementById('cp-title').textContent }));
    const v = await c2.evaluate(verifyInPage, '#chart/' + c.key + '/' + id);
    if (st.s.key !== c.key || st.s.id !== id || st.a !== id || v) return FAIL(`#chart/${c.key}/${id}: ${JSON.stringify(st)} ${v}`);
    const lb = await c2.evaluate(k => { PS_ROUTER.close(); location.hash = '#p=' + ((window.__psData('d-registry') || [])[0] || {}).id; return k; }, c.key);
    await c2.waitForSelector('#pm.open', { timeout: 5000 }).catch(() => {});
    const legacy = await c2.evaluate(() => !!document.querySelector('#pm.open'));
    if (!legacy) return FAIL('старая ссылка #p=… не открыла карточку');
    return OK(`#chart/${c.key}/${id} после загрузки: выбран «${st.t.slice(0, 40)}», фокус на элементе; старая #p=… открывает карточку`);
  } finally { await c2.close(); }
});

// ---------------------------------------------------------------- слой интерактивности 1.5: видимость и просмотр (FB-035, FB-036)
// точка внутри элемента, где он верхний под курсором (целые координаты: WebKit округляет координаты мыши), или null
function topPoint([sel, idx]) {
  const el = document.querySelectorAll(sel)[idx || 0]; if (!el) return null;
  el.scrollIntoView({ block: 'center', inline: 'nearest', behavior: 'instant' });
  for (const c of [el, ...el.querySelectorAll('*')]) {
    const r = c.getBoundingClientRect(); if (r.width < 1 && r.height < 1) continue;
    for (const [fx, fy] of [[.5, .5], [.3, .5], [.7, .5], [.5, .3], [.5, .7], [.2, .2], [.8, .8], [.2, .8], [.8, .2], [.1, .5], [.9, .5]]) {
      const x = Math.round(r.left + r.width * fx), y = Math.round(r.top + r.height * fy);
      if (x < 1 || y < 1 || x >= innerWidth - 1 || y >= innerHeight - 1) continue;
      const t = document.elementFromPoint(x, y);
      if (t && (t === el || el.contains(t))) return { x, y };
    }
  }
  return null;
}
const HAS_FLOW = (await page.locator('.flowsvg').count()) > 0;
const NO_VIEW = 'нет интерактивных графиков и блок-схем';
const viewerSkip = () => (!HAS_CH && !HAS_FLOW) ? SKIP(NO_VIEW, true) : replacedSkip('viewer');
// по одному экземпляру на график (основной — в разделе «Графики») и на схему (раздел «Блок-схемы» или первая вставка)
function viewTargets() {
  const out = [], seen = new Set(), q = s => window.CSS && CSS.escape ? CSS.escape(s) : s;
  const figs = [...document.querySelectorAll('figure.ps-ichart')];
  for (const f of figs.filter(x => x.classList.contains('ps-primary')).concat(figs)) {
    const k = f.dataset.chart; if (seen.has('c:' + k)) continue; seen.add('c:' + k);
    out.push({ kind: 'chart', key: k, sel: `figure.ps-ichart${f.classList.contains('ps-primary') ? '.ps-primary' : ''}[data-chart="${q(k)}"]`, box: '.ps-svg' });
  }
  [...document.querySelectorAll('.flowsvg')].forEach(b => { const k = b.dataset.imgkey || b.id; if (seen.has('f:' + k)) return; seen.add('f:' + k);
    out.push({ kind: 'flow', key: k, sel: `.flowsvg[data-imgkey="${q(b.dataset.imgkey || '')}"]`, box: null }); });
  return out;
}
// разметка и вид у ОДНОГО графика/схемы: обёртка, видимая кнопка, курсоры, строка-подсказка раздела
function viewInfo(t) {
  const f = document.querySelector(t.sel); if (!f) return { missing: true };
  const box = t.kind === 'chart' ? f.querySelector('.ps-svg') : f, wrap = box && box.parentElement && box.parentElement.classList.contains('psi-wrap') ? box.parentElement : null;
  const z = wrap && wrap.querySelector(':scope > .psi-zoom'), zr = z && z.getBoundingClientRect(), cs = z && getComputedStyle(z);
  const el = t.kind === 'chart' ? box && box.querySelector('svg[data-ps-chart] .ps-el') : box.querySelector('.fnode[data-node]');
  const sec = f.closest('section[id]');
  return { wrap: !!wrap, zoom: !!(z && zr.width > 0 && zr.height > 0 && cs.visibility !== 'hidden' && cs.display !== 'none'), text: z ? z.textContent.trim() : '',
    buttons: wrap ? wrap.querySelectorAll(':scope > .psi-zoom').length : 0, nested: !!(wrap && wrap.closest('.psi-wrap .psi-wrap, .psi-wrap > * .psi-wrap')),
    cursorBg: box ? getComputedStyle(box).cursor : '', cursorEl: el ? getComputedStyle(el).cursor : '', hint: !!(sec && (sec.id === 'top' || sec.querySelector(':scope > .psi-hint'))),
    img: t.kind === 'chart' ? !!(box && box.querySelector('img')) : false };
}
async function vstate(p) {
  return p.evaluate(() => { const lb = document.getElementById('psi-lb'), c = lb && lb.querySelector('.psi-canvas'), st = window.PSI ? PSI.state() : null;
    return { open: !!(st && st.open), transform: c ? c.style.transform : '', st, live: !!(c && c.querySelector('svg .ps-el, svg .fnode')), img: !!(c && c.querySelector('img')),
      focusIn: !!(lb && lb.contains(document.activeElement)), rect: lb && !lb.hidden ? (r => ({ w: Math.round(r.width), h: Math.round(r.height) }))(lb.getBoundingClientRect()) : null }; });
}
async function panelInfo(p) {
  return p.evaluate(() => { const pb = document.querySelector('#psi-lb .psi-pb'); if (!pb) return { len: 0, heads: {} };
    const heads = {}; pb.querySelectorAll('section').forEach(s => { const h = s.querySelector('h4'); if (h) heads[h.textContent.trim()] = (s.textContent || '').trim().length; });
    return { len: (pb.textContent || '').trim().length, heads, title: (document.querySelector('#psi-lb .psi-ptitle') || {}).textContent || '' }; });
}
async function closeViewer(p) { await p.keyboard.press('Escape'); await sleep(60); if ((await vstate(p)).open) await p.evaluate(() => PSI.close()); }

await check(page, 'viewer-structure', async () => {
  const sk = viewerSkip(); if (sk) return sk;
  if (HAS_CH && !await chartsReady(page)) return FAIL('файлы графиков не подгрузились');
  const ts = await page.evaluate(viewTargets), bad = [], pageBad = [];
  let ok = 0;
  for (const t of ts) {
    const i = await page.evaluate(viewInfo, t), name = (t.kind === 'chart' ? 'график ' : 'схема ') + t.key;
    if (i.missing) { bad.push(name + ': нет на странице'); continue; }
    const b = [];
    if (!i.wrap) b.push('нет обёртки .psi-wrap');
    if (!i.zoom) b.push('нет видимой кнопки «🔍 Увеличить»');
    else if (!/Увеличить/.test(i.text)) b.push('кнопка без текста «Увеличить»');
    if (i.buttons > 1 || i.nested) b.push(`повтор обёртки или кнопки (${i.buttons})`);
    if (i.cursorBg !== 'zoom-in') b.push('курсор фона ' + (i.cursorBg || '—') + ' (нужен zoom-in)');
    if (i.cursorEl && i.cursorEl !== 'pointer') b.push('курсор элемента ' + i.cursorEl);
    if (!i.hint) b.push('в разделе нет строки «Графики и схемы кликабельны…»');
    if (i.img) b.push('<img> вместо встроенного SVG');
    if (b.length) bad.push(name + ': ' + b.join(', ')); else ok++;
  }
  const top = await page.evaluate(() => { const h = document.querySelector('.psi-hint[data-psi-top]'); return h ? h.textContent.trim() : ''; });
  if (!/кликабельны/.test(top)) pageBad.push('вверху страницы нет строки «Графики и схемы кликабельны…»');
  const idem = await page.evaluate(() => ({ wraps: document.querySelectorAll('.psi-wrap').length, buttons: document.querySelectorAll('.psi-wrap > .psi-zoom').length,
    boxes: document.querySelectorAll('figure.ps-ichart .ps-svg, .flowsvg').length, nested: document.querySelectorAll('.psi-wrap .psi-wrap').length }));
  if (idem.wraps !== idem.boxes || idem.buttons !== idem.wraps || idem.nested) pageBad.push('идемпотентность: ' + JSON.stringify(idem));
  Object.assign(counts, { viewer_targets: ts.length, viewer_wraps: idem.wraps });
  if (bad.length || pageBad.length) return Object.assign(FAIL(`провалы у ${bad.length} из ${ts.length} графиков и схем` + (pageBad.length ? '; ' + pageBad.join('; ') : '') + ': ' + bad.slice(0, 12).join('; ')),
    { data: { failed: bad, page: pageBad } });
  return OK(`графиков и схем ${ts.length}: у каждого видимая «🔍 Увеличить», курсор zoom-in/pointer, строка-подсказка; обёрток ${idem.wraps} = блоков ${idem.boxes}`);
});

await check(page, 'viewer-hover', async () => {
  const sk = viewerSkip(); if (sk) return sk;
  const ts = await page.evaluate(viewTargets), bad = []; let ok = 0, n = 0;
  for (const t of ts) {
    const sel = t.kind === 'chart' ? `${t.sel} svg[data-ps-chart] .ps-el` : `${t.sel} .fnode[data-node]`;
    const cnt = await page.locator(sel).count(); if (!cnt) continue; n++;
    let pt = null; for (let i = 0; i < Math.min(cnt, 12) && !pt; i++) pt = await page.evaluate(topPoint, [sel, Math.floor(i * cnt / Math.min(cnt, 12))]);
    if (!pt) { bad.push(`${t.key}: ни один элемент не сверху под курсором`); continue; }
    await page.mouse.move(pt.x - 3, pt.y - 3); await page.mouse.move(pt.x, pt.y); await sleep(50);   // настоящее наведение, без force
    const r = await page.evaluate(kind => { const tip = document.getElementById(kind === 'chart' ? 'cp-tip' : 'psi-tip'); const vis = !!(tip && !tip.hidden && tip.getClientRects().length);
      const b = vis ? tip.getBoundingClientRect() : null; const ring = !!document.querySelector('.psi-wrap svg .psi-ovl .psi-hov, .psi-wrap svg .ps-ovl .ps-foc-line');
      return { vis, inView: !!b && b.left >= 0 && b.top >= 0 && b.right <= innerWidth + 1 && b.bottom <= innerHeight + 1, text: vis ? tip.textContent.trim() : '', bold: vis ? (tip.querySelector('b') || {}).textContent || '' : '', ring }; }, t.kind);
    if (!r.vis || !r.text) bad.push(`${t.key}: подсказки при наведении нет`);
    else if (!r.inView) bad.push(`${t.key}: подсказка за краем окна`);
    else if (!r.bold) bad.push(`${t.key}: в подсказке нет названия элемента`);
    else if (!r.ring) bad.push(`${t.key}: нет контура наведения`);
    else ok++;
  }
  await page.mouse.move(2, 2);
  // фокус с клавиатуры: та же подсказка у элемента графика
  let kb = 'нет графиков';
  if (HAS_CH) {
    const c = (await page.evaluate(chartsInPage)).charts.find(x => x.ids.length);
    if (c) { await page.evaluate(k => { const el = document.querySelector(`figure.ps-ichart.ps-primary[data-chart="${k}"] svg .ps-el[tabindex="0"]`); if (el) { el.scrollIntoView({ block: 'center', behavior: 'instant' }); el.focus({ preventScroll: true }); } }, c.key);
      await sleep(120); await page.keyboard.press('ArrowRight'); await sleep(60);   // фокус переведён клавиатурой → :focus-visible
      const t = await page.evaluate(() => { const tip = document.getElementById('cp-tip'); return tip && !tip.hidden ? tip.textContent.trim() : ''; });
      kb = t ? `фокус: «${t.slice(0, 30)}»` : 'фокус без подсказки';
      if (!t) bad.push(`${c.key}: при фокусе с клавиатуры подсказки нет`); }
  }
  if (bad.length) return FAIL(`${bad.length} из ${n}: ` + bad.slice(0, 10).join('; '));
  return OK(`подсказка «название + что это» и контур при наведении мышью: ${ok} из ${n}; ${kb}`);
});

await check(page, 'viewer-open', async () => {
  const sk = viewerSkip(); if (sk) return sk;
  const ts = await page.evaluate(viewTargets), bad = []; let ok = 0;
  for (const t of ts) {
    const zsel = t.kind === 'chart' ? `${t.sel} .psi-zoom` : `${t.sel} ~ .psi-zoom`;
    if (!await page.locator(zsel).count()) { bad.push(`${t.key}: нет кнопки`); continue; }
    await page.locator(zsel).first().scrollIntoViewIfNeeded(); await page.locator(zsel).first().click(); await sleep(140);
    let v = await vstate(page);
    if (!v.open) { bad.push(`${t.key}: кнопка не открыла просмотр`); continue; }
    const b = [];
    if (!v.live || v.img) b.push(v.img ? 'в просмотре картинка <img>, а не живой SVG' : 'в просмотре нет элементов SVG');
    if (!v.focusIn) b.push('фокус не в окне просмотра');
    const t0 = v.transform;
    await page.click('#psi-lb [data-psi-z="in"]'); await sleep(30); const t1 = (await vstate(page)).transform;
    const c = await page.evaluate(() => { const s = document.querySelector('#psi-lb .psi-stage').getBoundingClientRect(); return { x: Math.round(s.left + s.width / 2), y: Math.round(s.top + s.height / 2) }; });
    await page.mouse.move(c.x, c.y); await page.mouse.wheel(0, -240); await sleep(50); const t2 = (await vstate(page)).transform;
    await page.click('#psi-lb [data-psi-z="reset"]'); await sleep(30); const t3 = (await vstate(page)).transform;
    if (!(t0 && t1 !== t0 && t2 !== t1)) b.push('«+» или колесо не меняют масштаб');
    if (t3 !== t0) b.push('«Сброс» не вернул вписанный вид');
    await page.mouse.move(c.x, c.y); await page.mouse.down(); await page.mouse.move(c.x + 60, c.y + 30, { steps: 4 }); await page.mouse.up(); await sleep(30);
    if ((await vstate(page)).transform === t3) b.push('перетаскивание не сдвигает');
    // Tab не выходит из окна
    let out = 0; for (let i = 0; i < 14; i++) { await page.keyboard.press('Tab'); if (!(await vstate(page)).focusIn) { out++; break; } }
    if (out) b.push('Tab вывел фокус из окна просмотра');
    await page.keyboard.press('Escape'); await sleep(60); v = await vstate(page);
    if (v.open) b.push('Esc не закрыл просмотр');
    const back = await page.evaluate(z => { const a = document.activeElement; return !!(a && a.matches && a.matches('.psi-zoom') && a === document.querySelector(z)); }, zsel);
    if (!back) b.push('фокус не вернулся на кнопку');
    // клик по фону и Enter на кнопке открывают тот же просмотр
    const bg = await page.evaluate(t => { const f = document.querySelector(t.sel), box = t.kind === 'chart' ? f.querySelector('.ps-svg') : f; const r = box.getBoundingClientRect();
      for (let fy = .06; fy < .96; fy += .06) for (let fx = .04; fx < .97; fx += .06) { const x = Math.round(r.left + r.width * fx), y = Math.round(r.top + r.height * fy); if (y < 2 || y > innerHeight - 2 || x < 2 || x > innerWidth - 2) continue;
        const e = document.elementFromPoint(x, y); if (e && box.contains(e) && !e.closest('.ps-el,[data-ps-ref],.fnode,[data-node],button,a')) return { x, y }; } return null; }, t);
    if (bg) { await page.mouse.click(bg.x, bg.y); await sleep(100); if (!(await vstate(page)).open) b.push('клик по фону не открыл просмотр'); await closeViewer(page); }
    await page.focus(zsel); await page.keyboard.press('Enter'); await sleep(100);
    if (!(await vstate(page)).open) b.push('Enter на кнопке не открыл просмотр'); await closeViewer(page);
    if (b.length) bad.push(`${t.key}: ` + b.join(', ')); else ok++;
  }
  await shot(page, 'desktop-viewer');
  if (bad.length) return FAIL(`${bad.length} из ${ts.length}: ` + bad.slice(0, 10).join('; '));
  return OK(`просмотр с живым SVG у ${ok} из ${ts.length}: «🔍», клик по фону, Enter; «+»/колесо/перетаскивание/«Сброс»; Tab в окне; Esc → фокус на кнопку`);
});

await check(page, 'viewer-elements', async () => {
  const sk = viewerSkip(); if (sk) return sk;
  const ts = await page.evaluate(viewTargets), bad = []; let mouse = 0, list = 0, real = 0, total = 0, pidInfo = 'P-id в панели нет';
  for (const t of ts) {
    await page.evaluate(k => PSI.open(k), t.kind === 'chart' ? t.key : t.key.replace(/^flow-/, '')); await sleep(140);
    const v = await vstate(page); if (!v.open) { bad.push(`${t.key}: просмотр не открылся`); continue; }
    const ov = await page.evaluate(() => ({ list: document.querySelectorAll('#psi-lb .psi-chip[data-psi-sel]').length, how: /Как читать/.test(document.querySelector('#psi-lb .psi-pb').textContent) }));
    if (!ov.list || !ov.how) bad.push(`${t.key}: без выбора нет «Как читать» или списка элементов`);
    const ids = v.st.ids, pick = t.kind === 'flow' ? ids : sampleIds(ids);
    // точки, где элемент сверху: одним проходом в странице (синтетический клик в найденный верхний элемент = попадание мышью)
    const hits = await page.evaluate(([kind, pick]) => {
      const q = s => window.CSS && CSS.escape ? CSS.escape(s) : s, out = {};
      for (const id of pick) {
        const el = document.querySelector(`#psi-lb .psi-canvas ${kind === 'flow' ? '.fnode[data-node="' + q(id) + '"]' : '[data-ps-el="' + q(id) + '"]'}`); out[id] = null; if (!el) continue;
        for (const c of [el, ...el.querySelectorAll('*')]) { const r = c.getBoundingClientRect(); if (r.width < 1 && r.height < 1) continue;
          for (const [fx, fy] of [[.5, .5], [.3, .5], [.7, .5], [.5, .3], [.5, .7]]) { const x = Math.round(r.left + r.width * fx), y = Math.round(r.top + r.height * fy);
            const e = document.elementFromPoint(x, y); if (e && (e === el || el.contains(e))) { out[id] = { x, y }; break; } } if (out[id]) break; }
      } return out; }, [t.kind, pick]);
    const realIds = new Set([pick[0], pick[Math.floor(pick.length / 2)], pick[pick.length - 1]].filter(id => hits[id]));
    for (const id of pick) {
      total++;
      const pt = hits[id];
      if (pt && realIds.has(id)) { await page.mouse.click(pt.x, pt.y); real++; }
      else if (pt) await page.evaluate(([x, y]) => { const e = document.elementFromPoint(x, y); e.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, clientX: x, clientY: y })); }, [pt.x, pt.y]);
      else await page.evaluate(id => PSI.select(id), id);
      await sleep(8);
      const s = (await vstate(page)).st, pi = await panelInfo(page);
      const need = t.kind === 'flow' ? (pi.heads['Что это'] || 0) > 0 && (pi.heads['Что сделать'] || 0) > 0 : pi.len > 20;
      if (s.sel === id && need) { if (pt) mouse++; else list++; } else bad.push(`${t.key}/${id}: панель ${pi.len} зн. (${Object.keys(pi.heads).join('/')})`);
    }
    // ←/→ — соседний элемент
    if (ids.length > 1) { const s0 = (await vstate(page)).st.sel; await page.keyboard.press('ArrowRight'); await sleep(20); const s1 = (await vstate(page)).st.sel; if (s1 === s0) bad.push(`${t.key}: → не перешёл к соседнему`); }
    // P-id → карточка поверх просмотра; Esc закрывает карточку, затем просмотр
    const pid = page.locator('#psi-lb .psi-pb a[data-pid]').first();
    if (pidInfo === 'P-id в панели нет' && await pid.count()) {
      await pid.click(); await sleep(120);
      const z = await page.evaluate(() => ({ pm: !!document.querySelector('#pm.open'), above: +getComputedStyle(document.getElementById('pm')).zIndex > +getComputedStyle(document.getElementById('psi-lb')).zIndex }));
      await page.keyboard.press('Escape'); await sleep(80);
      const after = await page.evaluate(() => ({ pm: !!document.querySelector('#pm.open'), viewer: PSI.state().open }));
      if (!z.pm || !z.above) bad.push(`${t.key}: P-id не открыл карточку поверх просмотра`);
      else if (after.pm || !after.viewer) bad.push(`${t.key}: Esc закрыл не верхний слой (карточку)`);
      else pidInfo = 'P-id → карточка поверх просмотра, Esc — по слоям';
    }
    await closeViewer(page);
  }
  if (bad.length) return FAIL(`${bad.length} проблем: ` + bad.slice(0, 10).join('; '));
  return OK(`элементов в просмотре ${total}: попадание мышью ${mouse} (настоящих кликов ${real}), через список ${list} (перекрыты); ${pidInfo}`);
});

await check(page, 'viewer-print', async () => {
  const sk = viewerSkip(); if (sk) return sk;
  await page.emulateMedia({ media: 'print' });
  const r = await page.evaluate(() => [...document.querySelectorAll('.psi-zoom, .psi-hint, .psi-cue')].filter(e => getComputedStyle(e).display !== 'none').length);
  await page.emulateMedia({ media: 'screen' });
  return r ? FAIL(`при печати видны кнопки или подсказки: ${r}`) : OK('при печати кнопки «Увеличить», плашки и строки-подсказки скрыты');
});

// ---------------------------------------------------------------- поиск по странице, сущности текста, просмотр макетов (1.5, SM раздел 8)
await check(page, 'search', async () => {
  if (replacedSkip('search')) return replacedSkip('search');
  if (!await page.evaluate(() => !!window.PS_SEARCH)) return FAIL('нет поиска по странице (window.PS_SEARCH)');
  // слово из текста раздела стратегии (≥ 6 букв, с «е» — для проверки е/ё), часть слова и фраза из двух слов
  const w = await page.evaluate(() => { const secs = [...document.querySelectorAll('main section.strat p, main section.strat li, main section p')];
    for (const p of secs) { const ws = (p.textContent.match(/[А-Яа-яЁё]{6,}/g) || []).filter(x => /е/.test(x.toLowerCase())); if (ws.length >= 1) { const m = p.textContent.match(/([А-Яа-яЁё]{4,})\s+([А-Яа-яЁё]{4,})/); return { word: ws[0], phrase: m ? m[1] + ' ' + m[2] : '' }; } } return null; });
  if (!w) return SKIP('нет текста разделов для поиска');
  const btn = page.locator('nav.side .pss-open').first();
  if (!await btn.count()) return FAIL('нет кнопки «Поиск по странице» в меню разделов');
  await page.keyboard.press('/'); await sleep(150);
  if (!await page.locator('#pss.open').count()) return FAIL('клавиша «/» не открыла поиск');
  const res = async q => { await page.fill('#pss-q', q); await sleep(260); return page.evaluate(() => ({ n: document.querySelectorAll('#pss-res li').length, cnt: document.getElementById('pss-count').textContent, marks: document.querySelectorAll('#pss-res mark').length })); };
  const r1 = await res(w.word);
  if (!r1.n || !r1.marks) return FAIL(`«${w.word}»: ${r1.cnt}`);
  const yo = w.word.replace(/е/, 'ё'), r2 = await res(yo);
  if (!r2.n) return FAIL(`е/ё: «${yo}» не нашёл «${w.word}»`);
  const part = w.word.slice(0, 4), r3 = await res(part);
  if (!r3.n) return FAIL(`часть слова «${part}» ничего не нашла`);
  let ph = 'фразы нет'; if (w.phrase) { const r4 = await res('"' + w.phrase + '"'); if (!r4.n) return FAIL(`фраза «${w.phrase}» не найдена`); ph = `фраза → ${r4.n}`; }
  await res(w.word);
  const chips = await page.locator('#pss .pss-filters button[data-t]:not([data-t=""])').count();
  if (chips) { await page.locator('#pss .pss-filters button[data-t]:not([data-t=""])').first().click(); await sleep(80); }
  const filt = await page.evaluate(() => document.querySelectorAll('#pss-res li').length);
  await page.focus('#pss-q'); await page.keyboard.press('Enter'); await sleep(350);
  const after = await page.evaluate(() => { const m = document.querySelector('mark.pss-hit'); const b = m && m.getBoundingClientRect(); return { open: !!document.querySelector('#pss.open'), marks: document.querySelectorAll('mark.pss-hit').length, inView: !!b && b.top >= 0 && b.bottom <= innerHeight }; });
  if (after.open) return FAIL('Enter не закрыл поиск и не перешёл к результату');
  if (!after.marks) return FAIL('после перехода совпадения не подсвечены на странице');
  await page.evaluate(() => PS_SEARCH.clear());
  return OK(`«${w.word}» → ${r1.n}, «${yo}» → ${r2.n}, «${part}» → ${r3.n}, ${ph}; фильтр → ${filt}; переход: подсвечено ${after.marks}${after.inView ? ', на экране' : ''}`);
});
await check(page, 'entities', async () => {
  if (replacedSkip('entities')) return replacedSkip('entities');
  const a = await page.evaluate(() => window.PS_ENTS ? PS_ENTS.audit() : null);
  if (!a) return FAIL('нет слоя сущностей (window.PS_ENTS)');
  if (a.inert) return FAIL(`«мёртвых» упоминаний: ${a.inert} (P-id ${a.pid}, G-id ${a.gantt}, «раздел N» ${a.sec}, ID строк ${a.row}): ${a.examples.join(', ')}`);
  let nav = 'ссылок на разделы нет';
  const sec = page.locator('main a.ps-ent[data-ent^="sec:"]').first();
  if (await sec.count()) { const n = (await sec.getAttribute('data-ent')).split(':')[1]; await sec.scrollIntoViewIfNeeded(); await sec.click(); await sleep(150);
    const top = await page.evaluate(n => { const s = document.getElementById('s-' + n); return s ? Math.round(s.getBoundingClientRect().top) : null; }, n);
    if (top == null || top < -5 || top > 200) return FAIL(`ссылка «раздел ${n}» не привела к разделу (верх ${top})`); nav = `«раздел ${n}» → раздел`; }
  let term = 'терминов глоссария нет';
  const t = page.locator('main a.ps-term').first();
  if (await t.count()) { await t.scrollIntoViewIfNeeded(); await t.click(); await sleep(120); const ok = await page.evaluate(() => !!document.querySelector('#im.open') && /Что это/.test(document.getElementById('imbody').textContent));
    await page.keyboard.press('Escape'); if (!ok) return FAIL('клик по термину не открыл определение'); term = 'термин → определение'; }
  return OK(`«мёртвых» сущностей 0; связано: сущностей ${a.ents_linked}, терминов ${a.terms_linked}; ${nav}; ${term}`);
});
await check(page, 'mockup-viewer', async () => {
  if (replacedSkip('lightbox')) return replacedSkip('lightbox');
  const f = page.locator('main figure.lb[data-mock]:visible').first();
  if (!await f.count()) return SKIP('нет макетов с картинкой');
  const info = await f.evaluate(e => ({ html: e.getAttribute('data-html') || '', alt: e.getAttribute('data-alt') || '', pids: (e.getAttribute('data-pids') || '').split(/\s+/).filter(Boolean).length }));
  await f.scrollIntoViewIfNeeded(); await f.click(); await page.waitForSelector('#lb.open');
  const r = await page.evaluate(() => { const o = document.getElementById('lbopen'), p = document.getElementById('lbpids'), t = document.getElementById('lbtheme');
    return { link: o && !o.hidden ? o.getAttribute('href') : '', pids: p && !p.hidden ? p.querySelectorAll('a.pid').length : 0, theme: !!t && !t.hidden, src: document.getElementById('lbimg').getAttribute('src') }; });
  const bad = [];
  if (info.html && !r.link) bad.push('нет «Открыть интерактивный макет»');
  if (info.pids && !r.pids) bad.push('нет связанных P-id');
  if (info.alt) { if (!r.theme) bad.push('нет переключателя темы'); else { await page.click('#lbtheme'); await sleep(80); const src2 = await page.getAttribute('#lbimg', 'src'); if (src2 === r.src) bad.push('тема не переключилась'); } }
  await page.keyboard.press('Escape');
  if (bad.length) return FAIL(bad.join('; '));
  return OK(`макет: ${r.link ? 'интерактивный HTML ' + r.link.split('/').pop() : 'без HTML'}, P-id ${r.pids}${info.alt ? ', вторая тема переключается' : ''}`);
});

// ---------------------------------------------------------------- мобильная ширина 390 px
const mctx =await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 1, hasTouch: true });
await mctx.addInitScript(INIT);
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
await check(mpage, 'charts-mobile', async () => {
  if (!HAS_CH) return SKIP(NO_CH, true);
  if (!await chartsReady(mpage)) return FAIL('файлы графиков не подгрузились');
  const c = (await mpage.evaluate(chartsInPage)).charts.find(x => x.ids.length > 2) || (await mpage.evaluate(chartsInPage)).charts[0];
  const pt = await mpage.evaluate(hitPoint, { key: c.key, id: c.ids[Math.floor(c.ids.length / 2)] });
  if (pt) await mpage.touchscreen.tap(pt.x, pt.y); else await mpage.evaluate(c => PS_ROUTER.go('#chart/' + c.key + '/' + c.ids[0]), c);
  await sleep(150);
  const r = await mpage.evaluate(() => { const p = document.getElementById('cp').getBoundingClientRect(), el = document.querySelector('svg .ps-el.ps-on'), e = el && el.getBoundingClientRect();
    return { open: PS_ROUTER.state().open, l: Math.round(p.left), r: Math.round(p.right), b: Math.round(p.bottom), t: Math.round(p.top), W: innerWidth, H: innerHeight,
      sw: document.documentElement.scrollWidth, body: document.getElementById('cp-body').textContent.trim().length, elTop: e ? Math.round(e.top) : null, elBottom: e ? Math.round(e.bottom) : null }; });
  await shot(mpage, 'mobile-chart-panel');
  await mpage.keyboard.press('Escape');
  if (!r.open || !r.body) return FAIL('панель не открылась: ' + JSON.stringify(r));
  if (r.l < 0 || r.r > r.W || r.b < r.H - 1 || r.t < r.H * 0.3) return FAIL('не нижний лист: ' + JSON.stringify(r));
  if (r.sw > r.W + 1) return FAIL(`горизонтальная прокрутка документа: ${r.sw} > ${r.W}`);
  if (r.elTop != null && (r.elBottom <= 0 || r.elTop >= r.t)) return FAIL(`выбранный элемент закрыт листом: элемент ${r.elTop}–${r.elBottom}, лист с ${r.t}`);
  return OK(`${pt ? 'касание' : 'переход'}: нижний лист ${r.r - r.l}×${r.b - r.t} px, элемент над листом, ширина документа ${r.sw} ≤ ${r.W}`);
});
await check(mpage, 'viewer-mobile', async () => {
  const sk = viewerSkip(); if (sk) return sk;
  if (HAS_CH && !await chartsReady(mpage)) return FAIL('файлы графиков не подгрузились');
  const ts = await mpage.evaluate(viewTargets), bad = [];
  // кнопка на каждом графике и схеме: ≥ 44×32 px и не закрывает заголовок графика (первую подпись SVG)
  const sizes = await mpage.evaluate(ts => ts.map(t => { const f = document.querySelector(t.sel); if (!f) return { key: t.key, miss: true };
    const box = t.kind === 'chart' ? f.querySelector('.ps-svg') : f, z = box && box.parentElement.querySelector(':scope > .psi-zoom'); if (!z) return { key: t.key, miss: true };
    const zr = z.getBoundingClientRect(), tx = [...box.querySelectorAll('svg text')].find(x => (x.textContent || '').trim()), tr = tx && tx.getBoundingClientRect();
    const over = !!tr && tr.width > 0 && !(tr.right <= zr.left || tr.left >= zr.right || tr.bottom <= zr.top || tr.top >= zr.bottom);
    return { key: t.key, w: Math.round(zr.width), h: Math.round(zr.height), over }; }), ts);
  for (const s of sizes) { if (s.miss) bad.push(`${s.key}: нет кнопки`); else { if (s.w < 44 || s.h < 32) bad.push(`${s.key}: кнопка ${s.w}×${s.h} < 44×32`); if (s.over) bad.push(`${s.key}: кнопка закрывает заголовок графика`); } }
  const t = ts.find(x => x.kind === 'chart') || ts[0];
  const zsel = t.kind === 'chart' ? `${t.sel} .psi-zoom` : `${t.sel} ~ .psi-zoom`;
  await mpage.locator(zsel).first().scrollIntoViewIfNeeded();
  const zb = await mpage.locator(zsel).first().boundingBox();
  await mpage.touchscreen.tap(Math.round(zb.x + zb.width / 2), Math.round(zb.y + zb.height / 2)); await sleep(220);
  let v = await vstate(mpage);
  const W = await mpage.evaluate(() => innerWidth), H = await mpage.evaluate(() => innerHeight);
  if (!v.open) return FAIL('касание кнопки не открыло просмотр; ' + bad.slice(0, 4).join('; '));
  if (!v.rect || v.rect.w !== W || v.rect.h !== H) bad.push(`просмотр не на весь экран: ${JSON.stringify(v.rect)} при ${W}×${H}`);
  if (await mpage.evaluate(() => document.getElementById('psi-lb').classList.contains('psi-sheet-open'))) bad.push('лист панели открыт без выбора');
  const s0 = v.st.scale;
  await mpage.evaluate(() => {      // щипок двумя пальцами — синтетические pointer-события (в Playwright нет мультитача)
    const st = document.querySelector('#psi-lb .psi-stage'), r = st.getBoundingClientRect(), cx = r.left + r.width / 2, cy = r.top + r.height / 2;
    const ev = (type, id, x, y) => st.dispatchEvent(new PointerEvent(type, { pointerId: id, pointerType: 'touch', clientX: x, clientY: y, bubbles: true, isPrimary: id === 11 }));
    ev('pointerdown', 11, cx - 30, cy); ev('pointerdown', 12, cx + 30, cy);
    for (let k = 1; k <= 6; k++) { ev('pointermove', 11, cx - 30 - k * 12, cy); ev('pointermove', 12, cx + 30 + k * 12, cy); }
    ev('pointerup', 11, cx - 102, cy); ev('pointerup', 12, cx + 102, cy); });
  await sleep(60); v = await vstate(mpage);
  if (!(v.st.scale > s0 * 1.5)) bad.push(`щипок не увеличил: ${s0.toFixed(3)} → ${v.st.scale.toFixed(3)}`);
  await mpage.click('#psi-lb [data-psi-z="reset"]'); await sleep(60);
  const s1 = (await vstate(mpage)).st.scale;
  const sp = await mpage.evaluate(() => { const s = document.querySelector('#psi-lb .psi-stage').getBoundingClientRect(); return { x: Math.round(s.left + s.width / 2), y: Math.round(s.top + s.height * 0.3) }; });
  await mpage.touchscreen.tap(sp.x, sp.y); await sleep(90); await mpage.touchscreen.tap(sp.x, sp.y); await sleep(160);
  if (!((await vstate(mpage)).st.scale > s1 * 1.5)) bad.push('двойное касание не увеличило');
  await mpage.click('#psi-lb [data-psi-z="reset"]'); await sleep(60);
  const ids = (await vstate(mpage)).st.ids; let pt = null;
  for (let i = 0; i < ids.length && !pt; i++) pt = await mpage.evaluate(([kind, id]) => { const q = s => window.CSS && CSS.escape ? CSS.escape(s) : s;
    const el = document.querySelector(`#psi-lb .psi-canvas ${kind === 'flow' ? '.fnode[data-node="' + q(id) + '"]' : '[data-ps-el="' + q(id) + '"]'}`); if (!el) return null;
    const r = el.getBoundingClientRect(), x = Math.round(r.left + r.width / 2), y = Math.round(r.top + r.height / 2), e = document.elementFromPoint(x, y);
    return e && (e === el || el.contains(e)) && y < innerHeight - 90 ? { x, y } : null; }, [t.kind, ids[i]]);
  if (pt) { await mpage.touchscreen.tap(pt.x, pt.y); await sleep(450); } else await mpage.evaluate(id => PSI.select(id), ids[0]);
  const sh = await mpage.evaluate(() => { const lb = document.getElementById('psi-lb'), p = lb.querySelector('.psi-panel').getBoundingClientRect(), el = lb.querySelector('.psi-canvas .psi-on'), e = el && el.getBoundingClientRect();
    return { open: lb.classList.contains('psi-sheet-open'), len: lb.querySelector('.psi-pb').textContent.trim().length, bottom: Math.round(innerHeight - p.bottom), top: Math.round(p.top), H: innerHeight,
      elBottom: e ? Math.round(e.bottom) : null, elTop: e ? Math.round(e.top) : null, sw: document.documentElement.scrollWidth, W: innerWidth }; });
  await shot(mpage, 'mobile-viewer-sheet');
  if (!sh.open || sh.len < 20) bad.push('касание элемента не раскрыло нижний лист с подробностями');
  else if (sh.bottom !== 0 || sh.top < sh.H * 0.3) bad.push(`лист не внизу экрана: ${JSON.stringify(sh)}`);
  else if (sh.elTop != null && (sh.elBottom <= 0 || sh.elTop >= sh.top)) bad.push(`выбранный элемент закрыт листом: ${sh.elTop}–${sh.elBottom}, лист с ${sh.top}`);
  if (sh.sw > sh.W + 1) bad.push(`горизонтальная прокрутка ${sh.sw} > ${sh.W}`);
  await closeViewer(mpage);
  if (bad.length) return FAIL(bad.slice(0, 10).join('; '));
  return OK(`кнопки ${sizes.length} шт. ≥ 44×32 и не на заголовках; просмотр ${W}×${H} на весь экран, щипок и двойное касание, лист внизу, элемент над листом`);
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
const GEOM_VIEWS = [{ name: '1440', w: 1440, h: 900 }, { name: '820', w: 820, h: 1180 }, { name: '390', w: 390, h: 844 }];
const EMPTY_SHARE = 0.4, EMPTY_MEDIAN = 20;   // «пустая область»: колонка > 40 % ширины таблицы при медиане текста < 20 знаков
const MIN_DD = 120, MIN_SEC = 200;

// выполняется в странице (одним evaluate): раскрывает каждую строку реестра по очереди и меряет её
async function geomInPage({ maxH, minDD, minSec, view, emptyShare, emptyMedian }) {
  const R = { view, rows: 0, heights: [], tallest: null, minDD: null, minSec: null, bad: [], tall: [], modal: [], tables: 0, tableBad: [], tableWarn: [], gantt: null, ganttBad: [], pageW: 0, vw: innerWidth };
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
      if (h >= maxH) R.tall.push(id + ' ' + h + ' px');           // длинная карточка — предупреждение, не провал (B-48)
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
    const det = box.closest('details'), dsum = det && det.querySelector(':scope > summary');
    if (dsum && det.contains(box)) name = dsum.textContent.trim();     // таблица в свёрнутом блоке — по его заголовку
    while (e && !name) { let p = e.previousElementSibling; while (p && !name) { if (/^H[2-4]$/.test(p.tagName)) name = p.textContent.trim(); p = p.previousElementSibling; } e = e.parentElement; if (e && e.tagName === 'SECTION') { name = name || ((e.querySelector('h2') || {}).textContent || e.id || ''); break; } }
    name = '«' + name.replace(/\s+/g, ' ').slice(0, 48) + '»';
    const over = Math.round(t.getBoundingClientRect().width - box.clientWidth), ox = getComputedStyle(box).overflowX;
    let cut = 0;
    for (const r of t.rows) { const c = r.cells[r.cells.length - 1]; if (c && c.scrollWidth > c.clientWidth + 1) cut++; }
    if (view === '1440' && over > 1) R.tableBad.push(name + ': шире рамки на ' + over + ' px (последняя колонка уходит за край)');
    if (over > 1 && ox !== 'auto' && ox !== 'scroll') R.tableBad.push(name + ': обрезана без прокрутки');
    if (cut) R.tableBad.push(name + ': в последней колонке обрезано ячеек: ' + cut);
    // «пустые области» (A-1.13): таблица упирается в рамку (естественная ширина ≥ рамки), а одна колонка с короткими
    // значениями (медиана < 20 знаков) забирает > 40 % ширины — её раздувает одно длинное значение или nowrap
    if (view === '1440') {
      const head = t.tHead && t.tHead.rows[0], body = t.tBodies[0];
      const ncol = head ? head.cells.length : 0;
      if (ncol >= 3 && body && body.rows.length >= 2) {
        const prevW = t.style.width; t.style.width = 'max-content';
        const natural = t.getBoundingClientRect().width; t.style.width = prevW;
        const tw = t.getBoundingClientRect().width;
        if (natural >= box.clientWidth - 1 && tw > 0) {
          for (let k = 0; k < ncol; k++) {
            const hc = head.cells[k]; if (!hc || hc.colSpan > 1) continue;
            const share = hc.getBoundingClientRect().width / tw;
            // медиана по непустым ячейкам: колонка примечаний, заполненная в паре строк, — не «пустая область»
            const lens = [...body.rows].map(r => r.cells[k]).filter(Boolean).map(c => c.textContent.replace(/\s+/g, ' ').trim()).filter(x => x && !/^[—–-]$/.test(x)).map(x => x.length).sort((a, b) => a - b);
            if (!lens.length) continue;
            const med = lens[Math.floor(lens.length / 2)];
            if (share > emptyShare && med < emptyMedian)
              R.tableWarn.push(name + ', колонка «' + hc.textContent.replace(/\s+/g, ' ').trim().slice(0, 32) + '»: ' + Math.round(share * 100) + ' % ширины при медиане ' + med + ' знаков (пустая область)');
          }
        }
      }
    }
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
        const r = await p.evaluate(geomInPage, { maxH: args.maxRowH, minDD: MIN_DD, minSec: MIN_SEC, view: v.name, emptyShare: EMPTY_SHARE, emptyMedian: EMPTY_MEDIAN });
        await geomShots(p, engine, v, r);
        if (!r.rows && !r.tables && !r.gantt) return SKIP('нет реестра, таблиц и Ганта');
        const hs = r.heights.slice().sort((a, b) => a - b);
        const data = { rows: r.rows, height: hs.length ? { min: hs[0], median: hs[Math.floor(hs.length / 2)], max: hs[hs.length - 1], maxId: r.tallest.id } : null,
          minDD: r.minDD, minSection: r.minSec, tables: r.tables, gantt: r.gantt, pageWidth: r.pageW, viewport: r.vw, tall: r.tall, tableWarn: r.tableWarn };
        const bad = [...r.bad, ...r.modal, ...r.tableBad, ...r.ganttBad];
        if (r.pageW > r.vw) bad.push(`ширина документа ${r.pageW} > ${r.vw} (горизонтальная прокрутка страницы)`);
        const sum = `строк ${r.rows}` + (data.height ? `, высота мин/мед/макс ${data.height.min}/${data.height.median}/${data.height.max} px (${data.height.maxId})` : '')
          + (r.minDD != null ? `, столбец значения ≥ ${r.minDD} px` : '') + `, таблиц ${r.tables}` + (r.gantt ? `, Гант: подписей ${r.gantt.labels}, вех ${r.gantt.milestones}${r.gantt.scroll ? ', прокрутка в рамке' : ''}` : '')
          + `, ширина ${r.pageW} ≤ ${r.vw}`;
        // предупреждения (не провал): карточки выше --max-row-height, «пустые области» таблиц
        const warn = [...(r.tall.length ? [`карточек выше ${args.maxRowH} px: ${r.tall.length} (${r.tall.slice(0, 6).join(', ')}) — проверьте объём текста`] : []), ...r.tableWarn];
        for (const w of r.tableWarn) if (!warnings.includes('таблица ' + w)) warnings.push('таблица ' + w);
        const wtxt = warn.length ? ' | предупреждения: ' + warn.slice(0, 6).join('; ') : '';
        const res = bad.length ? FAIL(`${bad.length} проблем: ` + bad.slice(0, 8).join('; ') + wtxt + ' | ' + sum) : warn.length ? WARN(sum + wtxt) : OK(sum);
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
  '.pst', '.gst', '.gpl', '.gtd', '.kmoved', '.pg-sub', '.pg-ok', '.pg-warn', '.pst-go', '.kbv-r+label',
  // панель пояснений графика (открыта на элементе с метриками и ссылками) и «Как читать график»
  '#cp h3', '#cp h4', '#cp p', '#cp li', '#cp a', '#cp dt', '#cp dd', '#cp .tag', '.cp-kind', '#cp-pos', '.cp-chart', '#cp button',
  '.ps-howto p', '.ps-legend dt', '.ps-legend dd', '.ps-acts .linkbtn'];
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
  const chOpen = await p.evaluate(() => new Promise(res => {      // панель графика: элемент с метриками и ссылками, раскрытый «Как читать график»
    if (!window.PS_ROUTER || !document.querySelector('figure.ps-ichart')) { res(false); return; }
    const t = setTimeout(() => res(false), 20000);
    PS_ROUTER.loadAll(() => { clearTimeout(t); let pick = null;
      document.querySelectorAll('figure.ps-ichart.ps-primary').forEach(f => { if (pick) return; const e = ((PS_ROUTER.meta(f.dataset.chart) || {}).elements || []).find(x => (x.metrics || []).length && (x.links || []).length); if (e) pick = [f, e.id]; });
      if (!pick) { res(false); return; }
      const b = pick[0].querySelector('.ps-howto-btn'); if (b) b.click();
      PS_ROUTER.go('#chart/' + pick[0].dataset.chart + '/' + pick[1]); res(true); });
  }));
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
  // контур выбранного элемента графика: ≥ 3:1 к подложке графика и не только цвет (рамка вокруг элемента) — в светлой и тёмной теме
  for (const [name, attr] of [['charts-ring-contrast-light', 'light'], ['charts-ring-contrast-dark', 'dark']]) {
    await check(page, name, async () => {
      if (!chOpen) return SKIP(NO_CH, true);
      await p.evaluate(a => document.documentElement.setAttribute('data-theme', a), attr); await sleep(60);
      const r = await p.evaluate(() => {
        const parse = s => { const m = /rgba?\(([^)]+)\)/.exec(s || ''); return m ? m[1].split(/[\s,/]+/).filter(Boolean).map(parseFloat) : null; };
        const lin = x => { x /= 255; return x <= 0.03928 ? x / 12.92 : Math.pow((x + 0.055) / 1.055, 2.4); };
        const lum = c => 0.2126 * lin(c[0]) + 0.7152 * lin(c[1]) + 0.0722 * lin(c[2]);
        const line = document.querySelector('.ps-ovl .ps-sel-line'), halo = document.querySelector('.ps-ovl .ps-sel-halo'); if (!line) return null;
        const box = line.closest('.ps-svg'), bg = parse(getComputedStyle(box).backgroundColor), fg = parse(getComputedStyle(line).stroke), hb = line.getBoundingClientRect();
        const ratio = (Math.max(lum(fg), lum(bg)) + 0.05) / (Math.min(lum(fg), lum(bg)) + 0.05);
        return { ratio: Math.round(ratio * 100) / 100, w: parseFloat(getComputedStyle(line).strokeWidth), halo: !!halo, box: Math.round(hb.width) + '×' + Math.round(hb.height), fg: getComputedStyle(line).stroke, bg: getComputedStyle(box).backgroundColor };
      });
      if (!r) return FAIL('нет контура выбранного элемента');
      if (r.ratio < 3 || r.w < 2 || !r.halo) return FAIL('контур: ' + JSON.stringify(r));
      return OK(`контур ${r.fg} на ${r.bg}: ${r.ratio}:1, ${r.w} px + белый ореол, рамка ${r.box}`);
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
  const urls = await page.evaluate(() => Object.values(window.__psData('d-img') || {}).concat(Object.values(window.__psData('d-thumb') || {}).map(t => t && t[0]))
    .filter(u => typeof u === 'string' && !/^data:/.test(u)));
  if (!urls.length) return SKIP('страница автономная (собрана без --lite и site)', true);
  const outside = [], missing = [];
  for (const u of urls) {
    let rel = u; try { rel = decodeURIComponent(u.split('#')[0]); } catch (e) { /* как есть */ }
    const p = path.resolve(PAGE_DIR, rel);
    if (!p.startsWith(PAGE_DIR + path.sep)) outside.push(u); else if (!fs.existsSync(p)) missing.push(u);
  }
  if (outside.length) return FAIL('ссылки на картинки вне папки страницы: ' + outside.slice(0, 3).join(', '));
  if (missing.length) return FAIL(`нет файлов (${missing.length} из ${urls.length}): ` + missing.slice(0, 3).join(', '));
  const thumbs = await page.evaluate(() => Object.keys(window.__psData('d-thumb') || {}).length);
  const key = await page.evaluate(() => {
    const m = window.__psData('d-img'), al = (window.__psData('d-alias') || {});
    const f = [...document.querySelectorAll('figure.lb[data-key]')].find(x => { const k = al[x.dataset.key] || x.dataset.key; return m[k] && !/^data:/.test(m[k]) && x.offsetParent; });
    document.querySelectorAll('[data-smoke-lite]').forEach(x => x.removeAttribute('data-smoke-lite'));
    if (f) f.setAttribute('data-smoke-lite', ''); return f ? f.dataset.key : null;
  });
  let info = '';
  if (key && REPLACED.includes('lightbox')) info = ', просмотр картинок заменён расширением — открытие не проверялось';
  else if (key) {
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

// ---------------------------------------------------------------- сайт (режим site): файлы, ссылки, размеры, открытые данные
function tinyCsv(text) {   // минимальный разбор CSV (кавычки, переводы строк внутри полей) → массив строк
  const rows = []; let row = [], f = '', q = false;
  text = text.replace(/^﻿/, '');
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (q) { if (c === '"') { if (text[i + 1] === '"') { f += '"'; i++; } else q = false; } else f += c; }
    else if (c === '"') q = true;
    else if (c === ',') { row.push(f); f = ''; }
    else if (c === '\n') { row.push(f); rows.push(row); row = []; f = ''; }
    else if (c !== '\r') f += c;
  }
  if (f !== '' || row.length) { row.push(f); rows.push(row); }
  return rows;
}
function walkFiles(dir, base = dir) {
  const out = [];
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const f = path.join(dir, e.name);
    if (e.isDirectory()) out.push(...walkFiles(f, base)); else out.push(path.relative(base, f).split(path.sep).join('/'));
  }
  return out;
}
await check(page, 'site-structure', async () => {
  if (!IS_SITE) return SKIP('страница не в режиме site (single/lite)', true);
  const src = fs.readFileSync(HTML, 'utf8');
  const refs = [...src.matchAll(/<(?:link|script|img)\b[^>]*?\b(?:href|src)="([^"]+)"/g)].map(m => m[1]).filter(u => !/^(#|data:|mailto:)/.test(u) && !/rel="icon"/.test(u));
  const ext = refs.filter(u => /^[a-z][a-z0-9+.-]*:/i.test(u) || u.startsWith('//'));
  if (ext.length) return FAIL('внешние ссылки в оболочке: ' + ext.slice(0, 3).join(', '));
  const missing = [], outside = [];
  for (const u of refs) {
    let rel = u.split('#')[0].split('?')[0]; try { rel = decodeURIComponent(rel); } catch (e) { /* как есть */ }
    const f = path.resolve(PAGE_DIR, rel);
    if (!f.startsWith(PAGE_DIR + path.sep)) outside.push(u); else if (!fs.existsSync(f)) missing.push(u);
  }
  if (outside.length) return FAIL('ссылки вне папки сайта: ' + outside.slice(0, 3).join(', '));
  if (missing.length) return FAIL(`нет файлов (${missing.length} из ${refs.length}): ` + missing.slice(0, 3).join(', '));
  const inline = [...src.matchAll(/<script\b([^>]*)>/g)].filter(m => !/\bsrc=/.test(m[1]));
  if (inline.length) return FAIL(`инлайн-скриптов: ${inline.length} (запрещены CSP script-src 'self')`);
  if (/<script[^>]+type="application\/json"/.test(src)) return FAIL('данные остались в index.html (<script type=application/json>) — должны быть в assets/data.js');
  const pageUrl = await page.evaluate(() => location.protocol);
  if (pageUrl !== 'file:') return FAIL('страница открыта не по file://: ' + pageUrl);
  const cspv = await page.evaluate(() => window.__cspv || []);
  if (cspv.length) return FAIL('нарушения CSP: ' + cspv.slice(0, 3).join(' | '));
  const fetched = [...localFiles].filter(f => !fs.existsSync(f));
  if (fetched.length) return FAIL('запрошены несуществующие файлы: ' + fetched.slice(0, 3).join(', '));
  const idx = fs.statSync(HTML).size;
  let total = idx; let n = 0;
  for (const d of ['assets', 'data']) { const dir = path.join(PAGE_DIR, d); if (fs.existsSync(dir)) for (const r of walkFiles(dir)) { if (!path.basename(r).startsWith('.')) { total += fs.statSync(path.join(dir, r)).size; n++; } } }
  const mb = x => (x / 1048576).toFixed(2) + ' МБ';
  if (idx > 1048576) warnings.push(`index.html ${mb(idx)} — больше 1 МБ без данных: проверьте объём текста стратегии и встроенных SVG`);
  if (total > 25 * 1048576) warnings.push(`сайт ${mb(total)} — больше 25 МБ: перекодируйте картинки в WebP (Pillow/ffmpeg), уменьшите скриншоты; для пересылки одним файлом — --single`);
  Object.assign(counts, { site_index_bytes: idx, site_total_bytes: total, site_files: n + 1, site_refs: refs.length });
  return OK(`по file://, ссылок в оболочке ${refs.length} — все файлы на месте, запрошено локальных файлов ${localFiles.size}, инлайн-скриптов 0, нарушений CSP 0; index.html ${mb(idx)}, весь сайт ${mb(total)} (${n + 1} файлов)`);
});
await check(page, 'site-open-data', async () => {
  if (!IS_SITE) return SKIP('страница не в режиме site (single/lite)', true);
  const dir = path.join(PAGE_DIR, 'data');
  if (!fs.existsSync(dir)) return FAIL('нет папки data/ рядом со страницей');
  const rows = await page.evaluate(() => (window.__psData('d-registry') || []).length);
  const have = fs.readdirSync(dir).sort();
  const info = [];
  if (rows) {
    for (const need of ['proposals.json', 'proposals.csv']) if (!have.includes(need)) return FAIL('нет data/' + need);
    const pj = JSON.parse(fs.readFileSync(path.join(dir, 'proposals.json'), 'utf8'));
    if (pj.length !== rows) return FAIL(`data/proposals.json: ${pj.length} предложений, на странице ${rows}`);
    const pc = tinyCsv(fs.readFileSync(path.join(dir, 'proposals.csv'), 'utf8'));
    if (pc.length - 1 !== rows) return FAIL(`data/proposals.csv: ${pc.length - 1} строк, на странице ${rows}`);
    if (pc[0][0] !== 'id' || pc.slice(1).some(r => r.length !== pc[0].length)) return FAIL('data/proposals.csv: ширина строк не совпадает с заголовком');
    info.push(`proposals ${rows}`);
  }
  for (const f of have.filter(f => f.endsWith('.csv') && f !== 'proposals.csv')) {
    const t = tinyCsv(fs.readFileSync(path.join(dir, f), 'utf8'));
    if (t.length < 2) return FAIL(`data/${f}: пустая таблица`);
    if (t.slice(1).some(r => r.length !== t[0].length)) return FAIL(`data/${f}: ширина строк не совпадает с заголовком`);
    info.push(`${f.replace('.csv', '')} ${t.length - 1}`);
  }
  return OK(`data/: ${have.length} файлов (${info.join(', ')}); страница от них не зависит`);
});

// ---------------------------------------------------------------- движки: загрузка по file:// и ключевое действие в каждом
// Chromium — основной (все проверки выше); WebKit и Firefox — геометрия (WebKit) и эта проверка загрузки: скрипты и стили
// выполнились (CSP 'self' на file://), данные подключены, нарушений CSP, ошибок консоли и внешних запросов нет, P-ссылка открывает карточку.
const errLine = e => { const l = String((e && e.message) || e).split('\n'); const m = l.find(x => /\[err\]/.test(x) && !/headless mode/.test(x)); return (m ? m.replace(/^.*\[err\]\s*/, '') : l[0]).slice(0, 160); };
// причина недоступности движка из <OUT>/build/env.json (check_env.py): первое поле reason|error|why|note у ключа с именем движка
function envNote(name) {
  try {
    const e = JSON.parse(fs.readFileSync(path.join(OUT, 'build', 'env.json'), 'utf8')); let found = '';
    (function walk(o, k) {
      if (found || !o || typeof o !== 'object') return;
      if (String(k).toLowerCase().includes(name)) { const r = o.reason || o.error || o.why || o.note; if (r) { found = String(r).split('\n')[0].slice(0, 160); return; } }
      for (const [kk, v] of Object.entries(o)) walk(v, kk);
    })(e, '');
    return found;
  } catch (x) { return ''; }
}
async function launchFirefox() {
  try { return { browser: await pw.firefox.launch({ headless: !args.headed }), how: 'playwright' }; } catch (e) { var first = errLine(e); }
  const bases = [process.env.PLAYWRIGHT_BROWSERS_PATH, path.join(os.homedir(), 'Library', 'Caches', 'ms-playwright'),
    path.join(os.homedir(), '.cache', 'ms-playwright'), path.join(process.env.LOCALAPPDATA || '', 'ms-playwright')].filter(Boolean);
  for (const base of bases) {
    if (!fs.existsSync(base)) continue;
    const cands = fs.readdirSync(base).filter(n => /^firefox-\d+$/.test(n)).sort((a, b) => +b.split('-')[1] - +a.split('-')[1]);
    for (const c of cands) {
      const exe = [path.join(base, c, 'firefox', 'Nightly.app', 'Contents', 'MacOS', 'firefox'), path.join(base, c, 'firefox', 'firefox'), path.join(base, c, 'firefox', 'firefox.exe')].find(p => fs.existsSync(p));
      if (!exe) continue;
      try { return { browser: await pw.firefox.launch({ executablePath: exe, headless: !args.headed }), how: c }; } catch (e) { first = errLine(e) || first; }
    }
  }
  return { browser: null, why: first || 'нет Firefox в кэше Playwright' };
}
async function engineLoad(br, name) {
  await check(page, `engine-load-${name}`, async () => {
    const c = await br.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
    try {
      await c.addInitScript(INIT);
      const p = await c.newPage(); p.setDefaultTimeout(30000); watch(p, 'load-' + name);
      await p.goto(URL_, { waitUntil: 'load', timeout: 180000 }); await sleep(500);
      const r = await p.evaluate(() => ({
        proto: location.protocol, rows: document.querySelectorAll('#tb tr.row').length, sections: document.querySelectorAll('main > section').length,
        site: !!window.PS_DATA, reg: (window.__psData('d-registry') || []).length, cspv: window.__cspv || [],
        styled: getComputedStyle(document.body).fontSize !== '16px' || getComputedStyle(document.querySelector('nav.side') || document.body).position !== 'static',
      }));
      if (r.proto !== 'file:') return FAIL('не file://: ' + r.proto);
      if (!r.sections) return FAIL('разделов нет — скрипты/стили не выполнились');
      if (r.reg && !r.rows) return FAIL(`реестр (${r.reg}) не нарисован — app.js/data.js не выполнились`);
      if (r.cspv.length) return FAIL('нарушения CSP: ' + r.cspv.slice(0, 3).join(' | '));
      let modal = '';
      const link = p.locator('main a.pid:not(#registry a.pid):visible').first();
      if (await link.count()) { await link.scrollIntoViewIfNeeded(); await link.click(); await p.waitForSelector('#pm.open', { timeout: 10000 }); await p.keyboard.press('Escape'); modal = ', карточка предложения открывается'; }
      let charts = '';
      if (HAS_CH) {           // интерактивный график в этом движке: подгрузка, клик мышью, →, Esc с возвратом фокуса, ссылка из панели
        if (!await chartsReady(p)) return FAIL('графики не подгрузились (assets/charts-*.js)');
        const cs = (await p.evaluate(chartsInPage)).charts;
        const bad = cs.filter(c => !c.ready || !c.howto || c.noMeta.length || c.noEl.length).map(c => c.key);
        if (bad.length) return FAIL('графики не готовы: ' + bad.slice(0, 5).join(', '));
        const c = cs.find(x => x.ids.length > 2) || cs[0];
        let pt = null, id = null;
        for (const cand of sampleIds(c.ids)) { pt = await p.evaluate(hitPoint, { key: c.key, id: cand }); if (pt) { id = cand; break; } }
        if (!pt) return FAIL(`${c.key}: ни одного элемента нельзя нажать мышью`);
        await p.mouse.click(pt.x, pt.y); await sleep(80);
        const s1 = await p.evaluate(() => ({ s: PS_ROUTER.state(), t: document.getElementById('cp-title').textContent.trim(), secs: document.querySelectorAll('#cp-body > section').length }));
        if (!s1.s.open || s1.s.id !== id || !s1.t || !s1.secs) return FAIL(`клик по ${c.key}/${id}: ` + JSON.stringify(s1));
        await p.keyboard.press('ArrowRight'); await sleep(40);
        const s2 = await p.evaluate(() => ({ s: PS_ROUTER.state(), a: document.activeElement && document.activeElement.getAttribute('data-ps-el') }));
        if (s2.s.id === id || s2.a !== s2.s.id) return FAIL('→ не перешёл к следующему элементу: ' + JSON.stringify(s2));
        await p.keyboard.press('Escape'); await sleep(40);
        const s3 = await p.evaluate(() => ({ open: PS_ROUTER.state().open, a: document.activeElement && document.activeElement.getAttribute('data-ps-el') }));
        if (s3.open || s3.a !== s2.s.id) return FAIL('Esc: ' + JSON.stringify(s3));
        const lk = await p.evaluate(c => { for (const e of (PS_ROUTER.meta(c) || {}).elements || []) { const l = (e.links || []).find(x => /^#p\//.test(x.href)); if (l) return { id: e.id, href: l.href }; } return null; }, c.key);
        if (lk) {
          await p.evaluate(([k, i]) => PS_ROUTER.go('#chart/' + k + '/' + i), [c.key, lk.id]); await sleep(40);
          await p.locator(`#cp-body a[href="${lk.href}"]`).first().click(); await sleep(80);
          const v = await p.evaluate(verifyInPage, lk.href);
          if (v) return FAIL(`ссылка ${lk.href} из панели: ${v}`);
        }
        charts = `, график ${c.key}: клик, →, Esc${lk ? ', ссылка ' + lk.href : ''}`;
      }
      if ((HAS_CH || HAS_FLOW) && name !== 'chromium') {    // просмотр в этом движке (в Chromium — полные проверки viewer-* выше) — по КАЖДОМУ графику и схеме (FB-036): кнопка видна, живой SVG, «+», клик элемента, Esc
        if (REPLACED.includes('viewer')) { charts += ', просмотр заменён расширением'; }
        else {
          const ts = await p.evaluate(viewTargets), vbad = []; let vok = 0;
          for (const t of ts) {
            const i = await p.evaluate(viewInfo, t);
            if (!i.zoom) { vbad.push(`${t.key}: нет видимой кнопки «🔍 Увеличить»`); continue; }
            const zsel = t.kind === 'chart' ? `${t.sel} .psi-zoom` : `${t.sel} ~ .psi-zoom`;
            await p.locator(zsel).first().scrollIntoViewIfNeeded(); await p.locator(zsel).first().click(); await sleep(150);
            let v = await vstate(p);
            if (!v.open || !v.live) { vbad.push(`${t.key}: просмотр ${v.open ? 'без живого SVG' : 'не открылся'}`); await closeViewer(p); continue; }
            const t0 = v.transform; await p.click('#psi-lb [data-psi-z="in"]'); await sleep(40);
            if ((await vstate(p)).transform === t0) vbad.push(`${t.key}: «+» не меняет масштаб`);
            await p.click('#psi-lb [data-psi-z="reset"]'); await sleep(40);
            const id = v.st.ids.find(Boolean);
            const pt = id && await p.evaluate(([kind, id]) => { const q = s => window.CSS && CSS.escape ? CSS.escape(s) : s;
              const els = [...document.querySelectorAll(`#psi-lb .psi-canvas ${kind === 'flow' ? '.fnode[data-node]' : '.ps-el[data-ps-el]'}`)];
              for (const el of els) { const r = el.getBoundingClientRect(), x = Math.round(r.left + r.width / 2), y = Math.round(r.top + r.height / 2), e = document.elementFromPoint(x, y);
                if (e && (e === el || el.contains(e))) return { x, y, id: el.getAttribute('data-ps-el') || el.getAttribute('data-node') }; } return null; }, [t.kind, id]);
            if (pt) { await p.mouse.click(pt.x, pt.y); await sleep(60); const s = (await vstate(p)).st, pi = await panelInfo(p); if (s.sel !== pt.id || pi.len < 20) vbad.push(`${t.key}: клик по ${pt.id} не открыл панель`); }
            else vbad.push(`${t.key}: ни один элемент не нажимается мышью`);
            await p.keyboard.press('Escape'); await sleep(60);
            v = await vstate(p); const back = await p.evaluate(z => document.activeElement === document.querySelector(z), zsel);
            if (v.open || !back) vbad.push(`${t.key}: Esc ${v.open ? 'не закрыл' : 'не вернул фокус на кнопку'}`); else vok++;
          }
          if (vbad.length) return FAIL(`просмотр в ${name}: ${vbad.length} из ${ts.length}: ` + vbad.slice(0, 8).join('; '));
          charts += `, просмотр: ${vok} из ${ts.length} графиков и схем (кнопка, живой SVG, «+», клик, Esc)`;
        }
      }
      return OK(`${r.site ? 'site' : 'single/lite'} по file://: разделов ${r.sections}, строк реестра ${r.rows}${modal}${charts}`);
    } finally { await c.close(); }
  });
}
engines.push({ name: 'chromium', version: browser.version(), status: 'tested', scope: ['все проверки', 'геометрия', 'контраст', 'загрузка по file://', 'графики'] });
await engineLoad(browser, 'chromium');
let wk = null, ff = null;
if (args.engines.includes('webkit')) {
  wk = await launchWebkit();
  if (wk) {
    await geometryPass(wk.browser, 'webkit'); await engineLoad(wk.browser, 'webkit');
    engines.push({ name: 'webkit', version: wk.browser.version(), status: 'tested', scope: ['геометрия', 'загрузка по file://'].concat(HAS_CH ? ['графики: клик, клавиатура, ссылка'] : []) });
  } else {
    for (const v of GEOM_VIEWS) await check(page, `geometry-webkit-${v.name}`, async () => SKIP('WebKit не установлен в кэше Playwright: npx --prefix <node-dir> playwright install webkit', true));
    await check(page, 'engine-load-webkit', async () => SKIP('WebKit не установлен в кэше Playwright', true));
    engines.push({ name: 'webkit', status: 'unavailable', note: 'не установлен в кэше Playwright' });
  }
}
if (args.engines.includes('firefox')) {
  ff = await launchFirefox();
  if (ff.browser) {
    await engineLoad(ff.browser, 'firefox');
    engines.push({ name: 'firefox', version: ff.browser.version(), status: 'tested', scope: ['загрузка по file://'].concat(HAS_CH ? ['графики: клик, клавиатура, ссылка'] : []) });
  } else {
    const note = envNote('firefox');      // причина из build/env.json (check_env.py), если записана — FB-039
    await check(page, 'engine-load-firefox', async () => SKIP('Firefox не запустился: ' + ff.why + (note && note !== ff.why ? ' (check_env.py: ' + note + ')' : ''), true));
    engines.push({ name: 'firefox', status: 'unavailable', note: ff.why + (note && note !== ff.why ? ' (check_env.py: ' + note + ')' : '') });
  }
}

// ---------------------------------------------------------------- итог
checks.push({ name: 'console-errors', status: errors.length ? 'fail' : 'pass', detail: errors.length ? errors.slice(0, 5).join(' | ') : '0' });
checks.push({ name: 'external-requests', status: external.length ? 'fail' : 'pass', detail: external.length ? external.slice(0, 5).join(' | ') : '0' });
await browser.close();
if (wk) await wk.browser.close();
if (ff && ff.browser) await ff.browser.close();

const reqAll = args.require.includes('all');
for (const c of checks) {   // --require all не требует проверок, пропущенных из-за окружения (нет WebKit, страница без --lite)
  if (c.status === 'skip' && ((reqAll && !c.env) || args.require.includes(c.name))) { c.status = 'fail'; c.detail = 'обязательная проверка пропущена: ' + c.detail; }
}
const failed = checks.filter(c => c.status === 'fail');
const result = { ok: failed.length === 0, file: HTML, mode: IS_SITE ? 'site' : 'single', counts, passed: checks.filter(c => c.status === 'pass').length,
  failed: failed.length, warned: checks.filter(c => c.status === 'warn').length, skipped: checks.filter(c => c.status === 'skip').length, checks, errors, external, engines, warnings };
const testedOn = engines.filter(e => e.status === 'tested').map(e => `${e.name} ${e.version} (${e.scope.join(', ')})`);
const notRun = engines.filter(e => e.status !== 'tested').map(e => `${e.name} — не проверен: ${e.note}`);
if (args.json) {
  console.log(JSON.stringify(result, null, 1));
} else {
  const mark = { pass: 'OK  ', fail: 'FAIL', skip: 'skip', warn: 'WARN' };
  for (const c of checks) console.log(`${mark[c.status]} ${c.name.padEnd(18)} ${c.detail}`);
  console.log('проверено на: ' + testedOn.join('; ') + (notRun.length ? ' | ' + notRun.join('; ') : ''));
  for (const w of warnings) console.log('ВНИМАНИЕ: ' + w);
  console.log(`ИТОГ: ${result.ok ? (result.warned ? 'пройдено с предупреждениями' : 'пройдено') : 'есть провалы'} — ok ${result.passed}, warn ${result.warned}, fail ${result.failed}, skip ${result.skipped}; ` +
    `ошибок консоли ${errors.length}, внешних запросов ${external.length}; ${HTML}`);
}
process.exit(result.ok ? 0 : 1);
