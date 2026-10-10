'use strict';
// Плашка подписи для роликов android-qa-audit (clip_android.py → decorate), когда в ffmpeg нет фильтра drawtext
// (сборка без freetype): PNG с прозрачным фоном — тёмная полупрозрачная плашка, белый текст, значок вида
// (✕ ошибка / ? вопрос / • пояснение / ✓ работает) в цвете палитры #FFD60A / #BF5AF2 / #30D158, как у аннотаций
// скриншотов (annotate.js). ffmpeg накладывает её фильтром overlay. Рисует локальный Chromium через Playwright;
// сеть и сайты не используются. Вызывает clip_android.py (не запускать вручную).
//
//   node plaque.js --spec plaque.json
//   plaque.json: { "out": "/abs/plaque.png", "width": 648, "lines": [ { "text": "Меню закрывается через 0,4 с", "kind": "error" } ] }
// Вывод: {"out": "/abs/plaque.png", "width": W, "height": H}
const fs = require('fs');
const { parseArgs } = require('./lib');

const COLORS = { error: '#FFD60A', question: '#BF5AF2', note: '#BF5AF2', ok: '#30D158', after: '#30D158' };
const ICONS = { error: '✕', question: '?', note: '•', ok: '✓', after: '✓' };
const esc = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

(async () => {
  const a = parseArgs(process.argv.slice(2));
  if (!a.spec || a.spec === true) throw new Error('plaque.js --spec plaque.json');
  const spec = JSON.parse(fs.readFileSync(a.spec, 'utf8'));
  const lines = (spec.lines || []).filter(l => l && l.text).slice(0, 3);
  if (!spec.out || !lines.length) throw new Error('plaque.json: нужны out и lines');
  const W = Math.max(160, Math.round(+spec.width || 648));
  const font = Math.max(13, Math.round(W / 24));
  const rows = lines.map(l => `<div class="r"><b style="color:${COLORS[l.kind] || COLORS.error}">${ICONS[l.kind] || ICONS.error}</b>`
    + `<span>${esc(l.text)}</span></div>`).join('');
  const { chromium } = require('playwright');
  const browser = await chromium.launch();
  try {
    const page = await browser.newPage({ viewport: { width: W, height: 400 }, deviceScaleFactor: 1 });
    await page.setContent('<!doctype html><meta charset="utf-8"><style>'
      + 'html,body{margin:0;background:transparent}'
      + `.p{display:inline-block;max-width:${W - 4}px;box-sizing:border-box;background:rgba(18,18,22,.72);color:#fff;`
      + `border-radius:${Math.round(font * 0.5)}px;padding:${Math.round(font * 0.45)}px ${Math.round(font * 0.7)}px;`
      + `font:500 ${font}px/1.3 -apple-system,"Segoe UI",Roboto,"Noto Sans",Arial,sans-serif}`
      + `.r{display:flex;gap:${Math.round(font * 0.45)}px;align-items:baseline}.r+.r{margin-top:${Math.round(font * 0.2)}px}`
      + 'b{font-weight:700}</style><div class="p">' + rows + '</div>');
    const el = await page.$('.p');
    await el.screenshot({ path: spec.out, omitBackground: true });
    const box = await el.boundingBox();
    console.log(JSON.stringify({ out: spec.out, width: Math.round(box.width), height: Math.round(box.height) }));
  } finally { await browser.close(); }
})().catch(e => { console.error(e.message || String(e)); process.exit(1); });
