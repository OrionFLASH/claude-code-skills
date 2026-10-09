'use strict';
// Контактный лист скриншотов android-qa-audit: миниатюры с подписями, по `per` снимков на лист — один взгляд
// (Read) на 6–8 снимков вместо восьми отдельных. Идея — contactSheet из site-qa-audit/scripts/node/shot.js;
// здесь своя копия под портретные снимки телефона. Вызывает annotate_android.py sheet (не запускать вручную).
//
//   node sheet.js --spec sheet.json
//
// sheet.json: { "out": "/abs/contact.png", "cols": 4, "per": 8, "thumb": 240,
//               "items": [ { "file": "/abs/shot.png", "caption": "soak-rec60-…-t10m · 1080×2400" } ] }
// Вывод: {"sheets": ["/abs/contact.png"]} (листов больше одного — contact-1.png, contact-2.png, …).
// Снимки встраиваются data:-URI в локальную страницу Chromium; сеть и сайты не используются.
const fs = require('fs');
const path = require('path');
const { parseArgs } = require('./lib');

const esc = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
const mime = f => (/\.jpe?g$/i.test(f) ? 'image/jpeg' : 'image/png');

async function contactSheet(items, out, { cols = 4, per = 8, thumb = 240 } = {}) {
  const { chromium } = require('playwright');
  const browser = await chromium.launch();
  const outs = [];
  try {
    for (let i = 0; i < items.length; i += per) {
      const chunk = items.slice(i, i + per);
      const cells = chunk.map(it => `<figure><img src="data:${mime(it.file)};base64,${fs.readFileSync(it.file).toString('base64')}">`
        + `<figcaption>${esc(it.caption || path.basename(it.file))}</figcaption></figure>`).join('');
      const page = await browser.newPage({ viewport: { width: Math.min(chunk.length, cols) * (thumb + 12) + 12, height: 400 } });
      await page.setContent('<!doctype html><meta charset="utf-8"><style>'
        + `body{margin:0;padding:6px;background:#1b1b1b;font:11px -apple-system,"Segoe UI",Arial,sans-serif;color:#eee;`
        + `display:grid;grid-template-columns:repeat(${Math.min(chunk.length, cols)},${thumb}px);gap:12px 12px}`
        + `figure{margin:0}img{width:${thumb}px;height:auto;display:block;border:1px solid #555;background:#fff}`
        + 'figcaption{padding:3px 0;word-break:break-all;line-height:1.3}</style>' + cells);
      await page.waitForFunction(() => [...document.images].every(im => im.complete));
      const name = items.length > per ? out.replace(/\.png$/i, `-${i / per + 1}.png`) : out;
      await page.screenshot({ path: name, fullPage: true });
      await page.close();
      outs.push(path.resolve(name));
    }
  } finally { await browser.close(); }
  return outs;
}

(async () => {
  const a = parseArgs(process.argv.slice(2));
  if (!a.spec || a.spec === true) throw new Error('sheet.js --spec sheet.json');
  const spec = JSON.parse(fs.readFileSync(a.spec, 'utf8'));
  if (!spec.out || !(spec.items || []).length) throw new Error('sheet.json: нужны out и items');
  const sheets = await contactSheet(spec.items, spec.out, { cols: +(spec.cols || 4), per: +(spec.per || 8), thumb: +(spec.thumb || 240) });
  console.log(JSON.stringify({ sheets }));
})().catch(e => { console.error(e.message || String(e)); process.exit(1); });
