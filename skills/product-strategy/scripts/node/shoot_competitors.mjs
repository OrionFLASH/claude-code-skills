#!/usr/bin/env node
// Скриншоты главных страниц конкурентов из <OUT>/data/competitors.json (product-strategy).
//
//   node shoot_competitors.mjs <OUT> [--timeout 20000] [--only slug1,slug2] [--include-self] [--delay 1000] [--node-dir <dir>]
//
// Для каждой карточки с http(s) URL: открывает страницу (1440×900), ждёт отрисовки, закрывает cookie-баннер
// только по безопасным селекторам (кнопки «Принять/Accept» внутри баннеров согласия), снимает
// <OUT>/competitors/shots/<slug>.png и обновляет в карточке поля shot, shot_blocked, shot_error.
// shot_blocked=true — капча/анти-бот/HTTP 4xx-5xx (признаки по статусу, заголовку и короткому тексту страницы).
// Без входа в аккаунты и без других кликов; навигации не-GET (формы) блокируются; загрузки запрещены.
// Файл competitors.json перезаписывается после каждой карточки (устойчиво к обрыву).
// Код выхода: 0 — готово, 2 — ошибка аргументов, 3 — нет playwright/Chromium.
// Модули: --node-dir | $PS_NODE_DIR | <OUT>/build/node | ~/.cache/product-strategy/node | папка скрипта.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SKILL_DIR = path.resolve(HERE, '..', '..');
const USAGE = 'node shoot_competitors.mjs <OUT> [--timeout 20000] [--only slug1,slug2] [--include-self] [--delay 1000] [--node-dir <dir>]';

function parseArgs(argv, flags) {
  const pos = []; const opt = {};
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '-h' || a === '--help') { opt.help = true; continue; }
    if (a.startsWith('--')) {
      const eq = a.indexOf('=');
      const k = eq > 0 ? a.slice(2, eq) : a.slice(2);
      if (eq > 0) opt[k] = a.slice(eq + 1); else if (flags.has(k)) opt[k] = true; else opt[k] = argv[++i];
    } else pos.push(a);
  }
  return { pos, opt };
}

function loadPlaywright(opt, out) {
  const cands = opt['node-dir'] ? [opt['node-dir']] : [process.env.PS_NODE_DIR, out && path.join(out, 'build', 'node'), path.join(process.env.HOME || process.env.USERPROFILE || '', '.cache', 'product-strategy', 'node'), HERE].filter(Boolean);
  for (const d of cands) {
    const p = path.join(path.resolve(d), 'node_modules', 'playwright');
    if (fs.existsSync(path.join(p, 'package.json'))) {
      try { return createRequire(import.meta.url)(p); } catch { /* следующий кандидат */ }
    }
  }
  console.error(`нет playwright: python3 ${path.join(SKILL_DIR, 'scripts', 'check_env.py')} --install-node ${out || '<OUT>'}`);
  process.exit(3);
}

const { pos, opt } = parseArgs(process.argv.slice(2), new Set(['include-self']));
if (opt.help || pos.length < 1) { console.log(USAGE); process.exit(opt.help ? 0 : 2); }
const OUT = path.resolve(pos[0]);
const jsonPath = path.join(OUT, 'data', 'competitors.json');
if (!fs.existsSync(jsonPath)) { console.error('ошибка: нет ' + jsonPath); process.exit(2); }
let cards;
try { cards = JSON.parse(fs.readFileSync(jsonPath, 'utf8')); } catch (e) { console.error('ошибка: не разобран competitors.json: ' + e.message); process.exit(2); }
if (!Array.isArray(cards)) { console.error('ошибка: competitors.json должен быть списком'); process.exit(2); }
const TIMEOUT = parseInt(opt.timeout || '20000', 10);
const DELAY = parseInt(opt.delay || '1000', 10);
const only = new Set((opt.only || '').split(',').map((s) => s.trim()).filter(Boolean));
const shotsDir = path.join(OUT, 'competitors', 'shots');
fs.mkdirSync(shotsDir, { recursive: true });

const UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36';
const BLOCK_TITLE = /just a moment|attention required|access denied|forbidden|are you (a )?(human|robot)|verify you are human|captcha|security check|checking your browser|ddos-guard|pardon our interruption|request unsuccessful|request could not be satisfied|доступ запрещ|проверка браузера|вы не робот|подтвердите, что вы/i;
const BLOCK_TEXT = /verify you are human|are you a robot|enable javascript and cookies to continue|checking (if the site connection is secure|your browser)|press (&|and) hold|captcha|cf-chl|ddos-guard|access denied|unusual traffic|подтвердите, что вы не робот|вы не робот|проверяем ваш браузер|доступ ограничен/i;

// Кнопки согласия известных CMP и общий поиск «Принять» внутри баннеров cookie/consent.
const CMP_SELECTORS = [
  '#onetrust-accept-btn-handler', '#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll', '#CybotCookiebotDialogBodyButtonAccept',
  '#didomi-notice-agree-button', '.fc-cta-consent', 'button[data-testid="uc-accept-all-button"]', '#truste-consent-button',
  '.cc-allow', '.cc-accept', '.cc-dismiss', 'button[aria-label="Accept cookies"]', 'button[aria-label="Accept all cookies"]',
  '#cookie-accept', '#accept-cookies', '.cookie-accept', '[data-cookie-accept]', '[data-action="accept-cookies"]',
];
const ACCEPT_TEXT = /^\s*(accept( all)?( cookies)?|allow( all)?( cookies)?|agree|i agree|got it|ok(ay)?|understood|принять( все)?( cookie| куки)?|принимаю|согласен|согласна|понятно|хорошо|ок|разрешить( все)?)\s*[.!]?\s*$/i;

async function dismissCookies(page) {
  for (const sel of CMP_SELECTORS) {
    const el = page.locator(sel).first();
    if (await el.count().catch(() => 0)) {
      if (await safeClick(page, el)) return sel;
    }
  }
  // общий поиск: кнопка с текстом согласия внутри контейнера с признаками cookie/consent
  const handle = await page.evaluateHandle((src) => {
    const re = new RegExp(src, 'i');
    const isBanner = (el) => { for (let n = el; n && n !== document.body; n = n.parentElement) { const s = ((n.id || '') + ' ' + (n.className?.toString?.() || '') + ' ' + (n.getAttribute?.('aria-label') || '')).toLowerCase(); if (/cookie|consent|gdpr|cmp|privacy-banner|cookiebar|куки/.test(s)) return true; } return false; };
    for (const b of document.querySelectorAll('button, [role=button], a')) {
      const t = (b.innerText || b.textContent || '').trim();
      if (t.length > 40 || !re.test(t) || !b.offsetParent) continue;
      if (b.tagName === 'A') { const h = b.getAttribute('href') || ''; if (h && !h.startsWith('#') && !h.startsWith('javascript')) continue; }
      if (isBanner(b)) return b;
    }
    return null;
  }, ACCEPT_TEXT.source).catch(() => null);
  const el = handle && handle.asElement ? handle.asElement() : null;
  if (el) { if (await safeClick(page, el)) return 'текст кнопки'; }
  return null;
}

async function safeClick(page, el) {
  try {
    const info = await el.evaluate((n) => ({ tag: n.tagName, href: n.getAttribute('href') || '', type: n.getAttribute('type') || '', inForm: !!n.closest('form[action]') }));
    if (info.tag === 'A' && info.href && !info.href.startsWith('#') && !info.href.startsWith('javascript')) return false;
    if (info.type === 'submit' && info.inForm) return false;            // кнопка отправки формы — не трогаем
    const before = page.url();
    await el.click({ timeout: 2000 });
    await page.waitForTimeout(700);
    return page.url() === before;
  } catch { return false; }
}

function slugOf(card, i) {
  const s = String(card.slug || card.name || card.url || 'competitor-' + i).toLowerCase().replace(/^https?:\/\//, '').replace(/[^a-z0-9_-]+/g, '-').replace(/^-|-$/g, '');
  return (s || 'competitor-' + i).slice(0, 60);
}

const pw = loadPlaywright(opt, OUT);
let browser;
try { browser = await pw.chromium.launch({ headless: true }); }
catch (e) {
  console.error('не запустился Chromium: ' + String(e.message || e).split('\n')[0]);
  console.error(`поставьте браузер: python3 ${path.join(SKILL_DIR, 'scripts', 'check_env.py')} --install-node ${OUT}`);
  process.exit(3);
}
const stats = { ok: 0, blocked: 0, fail: 0, skipped: 0 };
const save = () => fs.writeFileSync(jsonPath, JSON.stringify(cards, null, 2) + '\n');

for (const [i, card] of cards.entries()) {
  if (!card || typeof card !== 'object') continue;
  const slug = slugOf(card, i);
  if (only.size && !only.has(card.slug) && !only.has(slug)) continue;
  if (card.self && !opt['include-self']) { stats.skipped++; continue; }
  let url;
  try { url = new URL(card.url); } catch { url = null; }
  if (!url || !['http:', 'https:'].includes(url.protocol)) {
    card.shot = null; card.shot_blocked = false; card.shot_error = 'нет http(s) URL'; stats.fail++; save(); continue;
  }
  const file = path.join(shotsDir, `${slug}.png`);
  const rel = `competitors/shots/${slug}.png`;
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, userAgent: UA, locale: 'en-US', acceptDownloads: false });
  await ctx.route('**/*', (route) => {
    const req = route.request();
    if (req.url().startsWith('file:')) return route.abort('accessdenied');
    if (req.isNavigationRequest() && !['GET', 'HEAD'].includes(req.method())) return route.abort('blockedbyclient');
    return route.continue();
  });
  const page = await ctx.newPage();
  page.on('dialog', (d) => d.dismiss().catch(() => {}));
  let status = null; let error = null; let title = ''; let blocked = false; let cookie = null;
  try {
    const resp = await page.goto(url.href, { waitUntil: 'domcontentloaded', timeout: TIMEOUT });
    status = resp ? resp.status() : null;
    await page.waitForLoadState('networkidle', { timeout: Math.min(8000, TIMEOUT) }).catch(() => {});
    await page.waitForTimeout(1500);
  } catch (e) { error = 'goto: ' + String(e.message || e).split('\n')[0].slice(0, 160); }
  try { title = (await page.title()) || ''; } catch { /* страница не отрисовалась */ }
  const probe = await page.evaluate(() => { const t = (document.body?.innerText || '').replace(/\s+/g, ' ').trim(); return { words: t ? t.split(' ').length : 0, text: t.slice(0, 2500) }; }).catch(() => ({ words: 0, text: '' }));
  if (status && status >= 400) blocked = true;
  if (BLOCK_TITLE.test(title)) blocked = true;
  if (probe.words < 200 && BLOCK_TEXT.test(probe.text)) blocked = true;
  if (!blocked && !error) cookie = await dismissCookies(page);
  try {
    await page.screenshot({ path: file, timeout: 15000 });
    if (fs.statSync(file).size < 2000) error = (error ? error + '; ' : '') + 'пустой скриншот';
    card.shot = rel;
  } catch (e) {
    error = (error ? error + '; ' : '') + 'screenshot: ' + String(e.message || e).split('\n')[0].slice(0, 120);
    if (fs.existsSync(file)) fs.unlinkSync(file);
    card.shot = null;
  }
  if (blocked) error = (error ? error + '; ' : '') + (status && status >= 400 ? `HTTP ${status}; ` : '') + `похоже на анти-бот/ошибку: «${title.slice(0, 60)}»`;
  card.shot_blocked = blocked;
  card.shot_error = error;
  if (!card.shot) stats.fail++; else if (blocked) stats.blocked++; else stats.ok++;
  console.log(`${!card.shot ? 'FAIL' : blocked ? 'BLCK' : 'OK  '} ${slug} [${status ?? '-'}] ${title.slice(0, 50)}${cookie ? ' | cookie: ' + cookie : ''}${error ? ' | ' + error : ''}`);
  await ctx.close();
  save();
  if (DELAY) await new Promise((r) => setTimeout(r, DELAY));
}
await browser.close();
save();
console.log(`итого: снято ${stats.ok}, анти-бот ${stats.blocked}, ошибок ${stats.fail}, пропущено ${stats.skipped} → ${path.relative(OUT, jsonPath)}`);
