'use strict';
// Аннотация скриншота: пунктирная обводка элемента, тонкая стрелка, короткая подпись.
// Рисует поверх готового PNG в локальном Chromium (canvas), сайт не трогает.
//
//   node annotate.js --in shot.png --spec spec.json [--out shot-annotated.png]
//
// spec.json:
// {
//   "scale": 1,                       // device pixel ratio скриншота (1 для scale:"css")
//   "items": [
//     { "box": [x, y, w, h],          // координаты элемента в CSS px относительно скриншота
//       "label": "Контраст 3,19:1 — нужно 4,5:1",
//       "kind": "error" | "question" | "note",   // значок: ✕ / ? / •
//       "style": "both" | "outline" | "arrow",   // по умолчанию both
//       "color": "auto" | "yellow" | "green" | "purple" | "#rrggbb" }
//   ],
//   "avoid": [[x, y, w, h], ...],     // области, которые подпись не должна закрывать (важный контент)
//   "labelWidth": 240,                // макс. ширина подписи в CSS px (shot.js перебирает 240/180/320/140)
//   "gutter": "auto"                  // auto | on | off: поле подписей справа от снимка; auto — для портретных снимков
// }                                   //   (телефон): подписи не закрывают интерфейс, стрелки ведут к рамкам
// Перерисовка без повторного воспроизведения: сырой снимок и spec.json лежат рядом (shot.js сохраняет оба) —
//   node annotate.js --in F-001.png --spec F-001.spec.json [--out F-001-annotated.png]
// В отчёте на каждый элемент: color, label (рамка подписи), overlapCost, contrast (цвет к фону вокруг рамки),
// inside (подпись целиком в картинке), covers (px² подписи поверх чужих рамок, avoid и других подписей).
// Правила оформления — references/screenshots.md.
const fs = require('fs');
const path = require('path');
const { parseArgs } = require('./lib');

const PALETTE = { yellow: '#FFD60A', green: '#30D158', purple: '#BF5AF2' };

function renderInPage({ img, spec, palette }) {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => {
      try {
        const S = spec.scale || 1;
        const W = image.naturalWidth, H = image.naturalHeight;
        // Portrait shots (phones): captions go to a dark field to the right of the image, never over the UI (G-7).
        const portrait = H > W * 1.2;
        const wantGutter = spec.gutter === 'on' || spec.gutter === true ||
          ((spec.gutter === undefined || spec.gutter === 'auto') && portrait && (spec.items || []).some(i => i.label));
        const GUT = wantGutter ? Math.round(Math.max(260 * S, W * 0.8)) : 0;
        const CW = W + GUT;
        const c = document.createElement('canvas'); c.width = CW; c.height = H;
        const g = c.getContext('2d');
        if (GUT) { g.fillStyle = '#1b1b1f'; g.fillRect(W, 0, GUT, H); }
        g.drawImage(image, 0, 0);
        const src = g.getImageData(0, 0, W, H).data;

        // ---- цвет ----
        const hex2rgb = (h) => [1, 3, 5].map(i => parseInt(h.slice(i, i + 2), 16));
        const lum = ([r, gg, b]) => { const f = v => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); }; return 0.2126 * f(r) + 0.7152 * f(gg) + 0.0722 * f(b); };
        const contrast = (a, b) => { const [l1, l2] = [lum(a), lum(b)].sort((x, y) => y - x); return (l1 + 0.05) / (l2 + 0.05); };
        const rgb2hue = ([r, gg, b]) => { r /= 255; gg /= 255; b /= 255; const mx = Math.max(r, gg, b), mn = Math.min(r, gg, b), d = mx - mn; if (!d) return { h: 0, s: 0 }; let h = mx === r ? ((gg - b) / d) % 6 : mx === gg ? (b - r) / d + 2 : (r - gg) / d + 4; h *= 60; if (h < 0) h += 360; return { h, s: mx ? d / mx : 0 }; };
        // Выборка пикселей в кольце вокруг рамки (где пройдут пунктир и стрелка).
        const sample = (x, y, w, h, pad) => {
          const px = []; const step = Math.max(2, Math.round(Math.max(w, h) / 60));
          for (let yy = Math.max(0, y - pad); yy < Math.min(H, y + h + pad); yy += step)
            for (let xx = Math.max(0, x - pad); xx < Math.min(W, x + w + pad); xx += step) {
              const inside = xx > x + pad / 2 && xx < x + w - pad / 2 && yy > y + pad / 2 && yy < y + h - pad / 2;
              if (inside && w > pad && h > pad) continue;
              const i = (yy * W + xx) * 4; px.push([src[i], src[i + 1], src[i + 2]]);
            }
          return px.length ? px : [[128, 128, 128]];
        };
        let lastContrast = null;
        const pickColor = (box, want) => {
          if (want && want !== 'auto') {
            const hex = palette[want] || want; const ring = sample(box[0], box[1], box[2], box[3], 14 * S);
            lastContrast = /^#[0-9a-f]{6}$/i.test(hex) ? ring.reduce((sum, p) => sum + contrast(hex2rgb(hex), p), 0) / ring.length : null;
            return hex;
          }
          const ring = sample(box[0], box[1], box[2], box[3], 14 * S);      // где пройдут пунктир и стрелка
          const wide = sample(box[0], box[1], box[2], box[3], 60 * S);      // окрестность: акцентные цвета сайта
          const share = (px, hc) => px.filter(p => { const hp = rgb2hue(p); const dh = Math.min(Math.abs(hp.h - hc), 360 - Math.abs(hp.h - hc)); return hp.s > 0.3 && dh < 40 && Math.max(...p) > 90; }).length / px.length;
          let best = null;
          for (const [name, hex] of Object.entries(palette)) {
            const rgb = hex2rgb(hex); const hc = rgb2hue(rgb).h;
            // контраст с фоном вокруг рамки минус штраф за совпадение тона с насыщенными цветами рядом
            const cAvg = ring.reduce((sum, p) => sum + contrast(rgb, p), 0) / ring.length;
            const score = Math.min(cAvg, 8) - 12 * share(ring, hc) - 10 * share(wide, hc);
            if (!best || score > best.score) best = { name, hex, score, contrast: cAvg };
          }
          lastContrast = best.contrast;
          return best.hex;
        };

        // ---- геометрия ----
        const items = (spec.items || []).map(it => ({ ...it, box: it.box.map(v => v * S), style: it.style || 'both', kind: it.kind || 'error' }));
        const avoid = (spec.avoid || []).map(b => b.map(v => v * S));
        const PAD = 4 * S;
        const outer = (b) => [b[0] - PAD, b[1] - PAD, b[2] + 2 * PAD, b[3] + 2 * PAD];
        const inter = (a, b) => Math.max(0, Math.min(a[0] + a[2], b[0] + b[2]) - Math.max(a[0], b[0])) * Math.max(0, Math.min(a[1] + a[3], b[1] + b[3]) - Math.max(a[1], b[1]));
        const placed = [];
        const arrows = [];  // уже нарисованные стрелки [x1,y1,x2,y2]
        const segX = (a, b) => {  // пересечение отрезков
          const d = (p, q, r) => (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0]);
          const [p1, p2, p3, p4] = [[a[0], a[1]], [a[2], a[3]], [b[0], b[1]], [b[2], b[3]]];
          return d(p1, p2, p3) * d(p1, p2, p4) < 0 && d(p3, p4, p1) * d(p3, p4, p2) < 0;
        };
        const segRect = (sg, r) => {  // отрезок проходит через прямоугольник
          const [x, y, w, h] = r; const edges = [[x, y, x + w, y], [x + w, y, x + w, y + h], [x, y + h, x + w, y + h], [x, y, x, y + h]];
          return edges.some(e => segX(sg, e));
        };

        const font = `${13 * S}px -apple-system, "Segoe UI", Roboto, Arial, sans-serif`;
        g.font = font;
        const wrap = (text, maxW) => { const words = text.split(/\s+/); const lines = []; let cur = ''; for (const w of words) { const t = cur ? cur + ' ' + w : w; if (g.measureText(t).width > maxW && cur) { lines.push(cur); cur = w; } else cur = t; } if (cur) lines.push(cur); return lines.slice(0, 3); };

        const drawDashedRect = (b, col) => {
          const [x, y, w, h] = outer(b); const r = 4 * S;
          g.save(); g.setLineDash([6 * S, 4 * S]); g.lineWidth = 1.6 * S;
          g.strokeStyle = 'rgba(0,0,0,0.55)'; g.lineWidth = 3 * S; roundRect(x, y, w, h, r); g.stroke();  // тонкая тёмная подложка для читаемости на светлом
          g.strokeStyle = col; g.lineWidth = 1.6 * S; roundRect(x, y, w, h, r); g.stroke();
          g.restore();
        };
        const roundRect = (x, y, w, h, r) => { g.beginPath(); g.moveTo(x + r, y); g.arcTo(x + w, y, x + w, y + h, r); g.arcTo(x + w, y + h, x, y + h, r); g.arcTo(x, y + h, x, y, r); g.arcTo(x, y, x + w, y, r); g.closePath(); };

        const labelBox = (it) => {
          const icon = it.kind === 'question' ? '?' : it.kind === 'note' ? '•' : '✕';
          const lines = wrap(it.label || '', GUT ? GUT - 64 * S : (it.labelWidth || spec.labelWidth || 240) * S);
          const tw = Math.max(...lines.map(l => g.measureText(l).width)) + 22 * S;
          const lh = 17 * S; const w = tw + 12 * S, h = lines.length * lh + 10 * S;
          return { icon, lines, w, h, lh };
        };
        const candidates = (b, lb) => {
          const [x, y, w, h] = outer(b); const cx = x + w / 2, cy = y + h / 2; const out = [];
          if (GUT) {  // gutter: the label column on the right, as close as possible to the element's height
            for (const k of [0, -1, 1, -2, 2, -3, 3, -4, 4, -6, 6, -8, 8, -11, 11, -15, 15])
              out.push([Math.round(W + 16 * S), Math.round(cy - lb.h / 2 + k * (lb.h + 8 * S)), 40]);
            return out;
          }
          for (const dist of [26, 48, 80, 130, 200, 300, 420]) for (let k = 0; k < 16; k++) {
            const ang = (k / 16) * Math.PI * 2; const dx = Math.cos(ang), dy = Math.sin(ang);
            // точка на расстоянии dist от рамки в направлении ang; подпись примыкает к ней ближним краем
            const px = cx + dx * (w / 2 + dist * S), py = cy + dy * (h / 2 + dist * S);
            const lx = dx > 0.3 ? px : dx < -0.3 ? px - lb.w : px - lb.w / 2;
            const ly = dy > 0.3 ? py : dy < -0.3 ? py - lb.h : py - lb.h / 2;
            out.push([Math.round(lx), Math.round(ly), dist]);
          }
          return out;
        };
        // «Занятость» области: плотность перепадов яркости (текст, иконки, линии). Подпись ищет спокойный фон.
        const L = new Float32Array(W * H);
        const SAT = new Uint8Array(W * H);  // 1 — насыщенный яркий пиксель (кнопки, чипы, цветные метки)
        for (let i = 0, j = 0; i < src.length; i += 4, j++) {
          L[j] = 0.299 * src[i] + 0.587 * src[i + 1] + 0.114 * src[i + 2];
          const mx = Math.max(src[i], src[i + 1], src[i + 2]), mn = Math.min(src[i], src[i + 1], src[i + 2]);
          SAT[j] = mx > 110 && (mx - mn) / mx > 0.45 ? 1 : 0;
        }
        const busy = (r) => {
          const [x0, y0, w, h] = r.map(Math.round); let sum = 0, n = 0; const st = Math.max(2, Math.round(3 * S));
          for (let yy = Math.max(1, y0); yy < Math.min(H - 1, y0 + h); yy += st)
            for (let xx = Math.max(1, x0); xx < Math.min(W - 1, x0 + w); xx += st) {
              const j = yy * W + xx; sum += Math.abs(L[j] - L[j + 1]) + Math.abs(L[j] - L[j + W]) + SAT[j] * 25; n++;
            }
          return n ? sum / n : 0;  // ~0 — ровный фон, 20+ — текст/детали
        };
        const pathBusy = (sg) => {  // занятость фона вдоль стрелки
          const len = Math.hypot(sg[2] - sg[0], sg[3] - sg[1]); const k = Math.max(1, Math.round(len / (6 * S))); let sum = 0;
          for (let i = 0; i <= k; i++) { const x = sg[0] + (sg[2] - sg[0]) * i / k, y = sg[1] + (sg[3] - sg[1]) * i / k; sum += busy([x - 3 * S, y - 3 * S, 6 * S, 6 * S]); }
          return sum / (k + 1);
        };
        const arrowFor = (box, r) => {  // от ближайшей точки подписи к ближайшей точке рамки
          const lc = [r[0] + r[2] / 2, r[1] + r[3] / 2]; const tgt = nearestEdge(box, lc);
          return [Math.min(Math.max(tgt[0], r[0]), r[0] + r[2]), Math.min(Math.max(tgt[1], r[1]), r[1] + r[3]), tgt[0], tgt[1]];
        };
        const placeLabel = (it, lb) => {
          const blockers = [...items.map(i => outer(i.box)), ...avoid, ...placed];
          const others = items.filter(i => i !== it).map(i => outer(i.box));
          let best = null;
          for (const [lx, ly, dist] of candidates(it.box, lb)) {
            const r = [lx, ly, lb.w, lb.h];
            const off = Math.max(0, -lx) + Math.max(0, -ly) + Math.max(0, lx + lb.w - CW) + Math.max(0, ly + lb.h - H);
            if (off > 0) continue;
            const ov = blockers.reduce((s, bl) => s + inter(r, bl), 0) / (lb.w * lb.h);  // доля перекрытия
            const ar = arrowFor(it.box, r); const len = Math.hypot(ar[2] - ar[0], ar[3] - ar[1]) / S;
            const crossA = arrows.filter(a => segX(ar, a)).length;
            const crossB = others.filter(b => segRect(ar, b)).length;
            const cost = ov * 400 + busy(r) * 16 + len * 0.3 + pathBusy(ar) * len * 0.02 + crossA * 120 + crossB * 60;
            if (!best || cost < best.cost) best = { x: lx, y: ly, cost: Math.round(cost) };
          }
          if (!best) best = { x: 4 * S, y: 4 * S, cost: 9999 };
          // в крайнем случае — прижать к краю изображения
          best.x = Math.min(Math.max(4 * S, best.x), CW - lb.w - 4 * S); best.y = Math.min(Math.max(4 * S, best.y), H - lb.h - 4 * S);
          return best;
        };
        const drawArrow = (from, to, col) => {
          const [x1, y1] = from, [x2, y2] = to;
          const mx = (x1 + x2) / 2 + (y2 - y1) * 0.12, my = (y1 + y2) / 2 - (x2 - x1) * 0.12;  // лёгкий изгиб
          g.save(); g.lineCap = 'round';
          for (const [stroke, lw] of [['rgba(0,0,0,0.5)', 3 * S], [col, 1.5 * S]]) {
            g.strokeStyle = stroke; g.lineWidth = lw; g.beginPath(); g.moveTo(x1, y1); g.quadraticCurveTo(mx, my, x2, y2); g.stroke();
            const ang = Math.atan2(y2 - my, x2 - mx), L = 8 * S;
            g.beginPath(); g.moveTo(x2, y2); g.lineTo(x2 - L * Math.cos(ang - 0.45), y2 - L * Math.sin(ang - 0.45));
            g.moveTo(x2, y2); g.lineTo(x2 - L * Math.cos(ang + 0.45), y2 - L * Math.sin(ang + 0.45)); g.stroke();
          }
          g.restore();
        };
        // Точка входа стрелки — середина стороны рамки, обращённой к подписи (у соседних рамок точки не совпадают)
        const nearestEdge = (b, p) => {
          const [x, y, w, h] = outer(b);
          const dx = p[0] < x ? x - p[0] : p[0] > x + w ? p[0] - (x + w) : 0;
          const dy = p[1] < y ? y - p[1] : p[1] > y + h ? p[1] - (y + h) : 0;
          if (dx >= dy && dx > 0) return [p[0] < x ? x : x + w, y + h / 2];
          if (dy > 0) return [Math.min(Math.max(p[0], x + Math.min(24 * S, w / 2)), x + w - Math.min(24 * S, w / 2)), p[1] < y ? y : y + h];
          return [Math.min(Math.max(p[0], x), x + w), Math.min(Math.max(p[1], y), y + h)];
        };

        const report = [];
        for (const it of items) {
          const col = pickColor(it.box, it.color);
          if (it.style !== 'arrow') drawDashedRect(it.box, col);
          if (!it.label) { report.push({ color: col, contrast: lastContrast === null ? null : +lastContrast.toFixed(2) }); continue; }
          const lb = labelBox(it); const pos = placeLabel(it, lb);
          placed.push([pos.x - 4 * S, pos.y - 4 * S, lb.w + 8 * S, lb.h + 8 * S]);
          const lc = [pos.x + lb.w / 2, pos.y + lb.h / 2];
          const tgt = nearestEdge(it.box, lc);
          // точка выхода стрелки — ближайшая к цели точка на краю подписи
          const sx = Math.min(Math.max(tgt[0], pos.x), pos.x + lb.w), sy = Math.min(Math.max(tgt[1], pos.y), pos.y + lb.h);
          const dist = Math.hypot(tgt[0] - sx, tgt[1] - sy);
          if (it.style !== 'outline' && dist > 6 * S) { drawArrow([sx, sy], tgt, col); arrows.push([sx, sy, tgt[0], tgt[1]]); }
          // подпись: тёмная полупрозрачная плашка, рамка и значок цветом аннотации, текст светлый
          g.save(); g.fillStyle = 'rgba(17,17,17,0.82)'; roundRect(pos.x, pos.y, lb.w, lb.h, 6 * S); g.fill();
          g.strokeStyle = col; g.lineWidth = 1 * S; g.stroke();
          g.font = `bold ${13 * S}px -apple-system, "Segoe UI", Roboto, Arial, sans-serif`; g.fillStyle = col; g.textBaseline = 'top';
          g.fillText(lb.icon, pos.x + 8 * S, pos.y + 6 * S);
          g.font = font; g.fillStyle = '#f5f5f5';
          lb.lines.forEach((l, i) => g.fillText(l, pos.x + 24 * S, pos.y + 6 * S + i * lb.lh));
          g.restore();
          // Self-check: label inside the image; px² over other boxes (outer frames of other items, avoid, earlier labels).
          const lr = [pos.x, pos.y, lb.w, lb.h];
          const others = [...items.filter(i => i !== it).map(i => outer(i.box)), outer(it.box), ...avoid, ...placed.slice(0, -1)];
          const covers = Math.round(others.reduce((sum, b) => sum + inter(lr, b), 0) / (S * S));
          const inside = pos.x >= 0 && pos.y >= 0 && pos.x + lb.w <= CW && pos.y + lb.h <= H;
          report.push({ color: col, label: [pos.x, pos.y, lb.w, lb.h].map(v => Math.round(v / S)), overlapCost: pos.cost,
            contrast: lastContrast === null ? null : +lastContrast.toFixed(2), inside, covers });
        }
        resolve({ data: c.toDataURL('image/png'), report, canvas: { width: Math.round(CW / S), height: Math.round(H / S), gutter: Math.round(GUT / S) } });
      } catch (e) { reject(String(e && e.stack || e)); }
    };
    image.onerror = () => reject('не удалось загрузить изображение');
    image.src = img;
  });
}

// Render with an already launched browser (shot.js retries placements without relaunching).
async function render(browser, input, spec) {
  const page = await browser.newPage();
  try {
    await page.setContent('<!doctype html><meta charset="utf-8"><body></body>');
    const img = 'data:image/png;base64,' + fs.readFileSync(input).toString('base64');
    const { data, report, canvas } = await page.evaluate(renderInPage, { img, spec, palette: PALETTE });
    return { buffer: Buffer.from(data.split(',')[1], 'base64'), report, canvas };
  } finally { await page.close(); }
}

async function annotate(input, spec, output, opts = {}) {
  const { chromium } = require('playwright');
  const browser = opts.browser || await chromium.launch();
  try {
    const { buffer, report } = await render(browser, input, spec);
    fs.writeFileSync(output, buffer);
    return report;
  } finally { if (!opts.browser) await browser.close(); }
}

if (require.main === module) {
  (async () => {
    const a = parseArgs(process.argv.slice(2));
    if (!a.in || !a.spec) { console.error('нужны --in shot.png --spec spec.json [--out file]'); process.exit(1); }
    const spec = JSON.parse(fs.readFileSync(a.spec, 'utf8'));
    const out = a.out && a.out !== true ? a.out : a.in.replace(/\.png$/i, '') + '-annotated.png';
    const report = await annotate(a.in, spec, out);
    console.log(JSON.stringify({ out: path.resolve(out), items: report }));
  })().catch(e => { console.error(e); process.exit((e && e.exitCode) || 1); });
}

module.exports = { annotate, render, PALETTE };
