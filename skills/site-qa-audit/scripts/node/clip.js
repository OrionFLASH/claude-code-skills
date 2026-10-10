'use strict';
// Short silent clip of a finding's reproduction (references/clips.md): the recording starts right before the steps
// and stops ~1 s after the result. A complement to the annotated screenshot, never a replacement.
//
//   node clip.js --out <RUN_DIR>/clips/F-004-menu.mp4 (--url URL | --cdp http://127.0.0.1:9222 [--page-match substr] [--url URL])
//        [--device pixel7 | --size 1440x813] [--setup steps.js] [--prepare before.js] [--caption "…"]
//        "selector|подпись|kind" ...                  dashed frames over the targets (kind: error|question|note|ok)
//        [--mask ".email,#phone"] [--seconds 10] [--hold 1000] [--wait 500] [--kind error|ok|note|after]
//        [--state auth-state.json] [--rules rules.json] [--log blocked.jsonl] [--read-only] [--no-cursor] [--keep-raw]
//        [--format mp4|gif|both] [--finding F-004 --run-dir <RUN_DIR>]
//
// steps.js (recorded):     module.exports = async ({ page, guarded, clip }) => { await guarded.click('#menu'); };
// before.js (not recorded, e.g. scroll to the place): the same signature.
//   guarded — guard.js rules on every click/fill/press/goto (deny → not performed, written to blocked.jsonl and to the
//   warnings); clip.caption(text, kind) — change the caption, clip.step(text) — add a step to the list, clip.wait(ms).
// Recorder: page.screencast (recent Playwright, 1.63 in the skill: launch AND CDP — the user's tab is recorded as it is) or, when the
// installed Playwright has no screencast, recordVideo of the script's own context (launch only; trimmed to the steps).
// SITE_QA_CLIP_MODE=screencast|video forces one (tests). --cdp: nothing is cleared, no navigation unless --url; the
// overlay and the mask are removed afterwards; a background tab is brought to the front (a warning says so).
// In the frame (injected into the page while recording, closed shadow root, pointer-events: none): dashed frames in the
// palette of annotate.js (#FFD60A / #30D158 / #BF5AF2, thin), a dark caption plate with ✕ ? • ✓ (the caption stays
// the whole clip, the line under it shows the last step), a cursor dot with a ring on click, CSS blur over --mask.
// Never recorded: login and payment pages (url_guard paths and hosts, rules.read_only_urls, /login, /checkout …),
// a visible password / card / one-time-code field, typing into such a field — refused with exit 3, nothing is kept.
// After the recording: `python3 scripts/clips.py finalize` (compress to the budget, GIF, poster, frame sheet, finding).
// Output: ONE JSON line {ok, clip, files, warnings, recorder, cdp, steps}. Exit: 0 done, 1 done with warnings (budget,
// no ffmpeg, a denied step, steps cut by --seconds), 2 bad input, 3 recording forbidden, 4 guard / Playwright unavailable.
const fs = require('fs');
const os = require('os');
const path = require('path');
const { spawnSync } = require('child_process');
const { parseArgs, loadRules, multiArg, toUrl, hostpathMatches } = require('./lib');

const EXIT = { OK: 0, WARN: 1, INPUT: 2, FORBIDDEN: 3, UNAVAILABLE: 4 };
const PALETTE = { yellow: '#FFD60A', green: '#30D158', purple: '#BF5AF2' };  // = annotate.js
const STYLE = { error: [PALETTE.yellow, '✕'], question: [PALETTE.purple, '?'], note: [PALETTE.purple, '•'],
  ok: [PALETTE.green, '✓'], after: [PALETTE.green, '✓'] };
const BOOL = new Set(['--read-only', '--no-cursor', '--keep-raw']);
const SCRIPTS = path.join(__dirname, '..');
const PY = process.env.SITE_QA_PYTHON || (process.platform === 'win32' ? 'python' : 'python3');
const ENV_HINT = 'проверьте окружение: python3 <SKILL_DIR>/scripts/check_env.py --fast --no-browsers; ' +
  'зависимости: cd <SKILL_DIR>/scripts/node && npm install';

class ClipError extends Error {
  constructor(code, message, extra = {}) { super(message); this.code = code; this.extra = extra; }
}

// ---- login / payment ------------------------------------------------------------------------------------------
const SENSITIVE_PATH = /(^|\/)(log-?in|sign-?in|sign_in|sign-?up|signup|register|registration|auth|oauth2?|openid|sso|sessions?|password|forgot(-password)?|reset-password|2fa|mfa|otp|checkout|payments?|pay|billing|subscribe|subscription|donate)(\/|$|[.?#_-])/i;

function urlSensitive(url, rules) {
  let u;
  try { u = new URL(url); } catch { return null; }
  if (!/^(https?|file):$/.test(u.protocol)) return null;
  const pq = u.pathname + u.search;
  if (SENSITIVE_PATH.test(u.pathname)) return `адрес похож на страницу входа или оплаты (${u.pathname})`;
  if (rules) {
    const b = rules.base || {}, r = rules.rules || {};
    try { if (b.deny_path_regex && new RegExp(b.deny_path_regex, 'i').test(pq)) return `запрещённый путь url_guard (вход, оплата, выход): ${u.pathname}`; } catch { /* bad regex: other checks */ }
    if (u.protocol !== 'file:' && (b.deny_nav_hosts || []).some(p => hostpathMatches(u.hostname, u.pathname, p))) return `хост входа или оплаты: ${u.hostname}`;
    if ((r.read_only_urls || []).some(p => { try { return new RegExp(p, 'i').test(url); } catch { return false; } }))
      return 'страница только для чтения (rules.read_only_urls — вход, покупка)';
  }
  return null;
}

// In the page: a visible password / card / one-time-code field or a payment provider iframe.
function domSensitiveInPage() {
  const vis = (e) => { const r = e.getBoundingClientRect(), cs = getComputedStyle(e); return r.width > 0 && r.height > 0 && cs.visibility !== 'hidden' && cs.display !== 'none'; };
  const q = 'input[type=password i], input[autocomplete~="cc-number" i], input[autocomplete~="cc-csc" i], input[autocomplete~="cc-exp" i], ' +
    'input[autocomplete="one-time-code" i], input[name*="cardnumber" i], input[name*="card_number" i], input[name*="cvc" i], input[name*="cvv" i]';
  let el;
  try { el = [...document.querySelectorAll(q)].find(vis); } catch { el = null; }
  if (el) return el.type && el.type.toLowerCase() === 'password' ? 'на странице видно поле пароля' : 'на странице видно поле платёжных данных или одноразового кода';
  const ifr = [...document.querySelectorAll('iframe[src]')].find(f => vis(f) && /stripe|paypal|braintree|adyen|klarna|yookassa|yoomoney|cloudpayments|tinkoff|robokassa|\/checkout|\/payment|\/\/pay\./i.test(f.src));
  return ifr ? 'на странице платёжная форма (iframe)' : null;
}

function secretFieldInPage(el) {
  if (!el || el.tagName !== 'INPUT' && el.tagName !== 'TEXTAREA') return false;
  const t = (el.getAttribute('type') || '').toLowerCase(), ac = (el.getAttribute('autocomplete') || '').toLowerCase();
  const nm = `${el.name || ''} ${el.id || ''}`.toLowerCase();
  return t === 'password' || /cc-|one-time-code|current-password|new-password/.test(ac) || /card.?number|cvc|cvv|otp|passw/.test(nm);
}

// ---- overlay (runs in the page) ------------------------------------------------------------------------------
function overlayInPage(cfg) {
  const W = window;
  if (W.__qaClip) { W.__qaClip.update(cfg); return W.__qaClip.status(); }
  const doc = document;
  const host = doc.createElement('qa-clip-overlay');
  host.setAttribute('aria-hidden', 'true');
  host.style.cssText = 'all:initial;position:fixed;left:0;top:0;width:100vw;height:100vh;pointer-events:none;z-index:2147483647;';
  const root = host.attachShadow({ mode: 'closed' });
  root.innerHTML = '<style>' +
    ':host{all:initial}*{box-sizing:border-box}svg{position:absolute;left:0;top:0;width:100%;height:100%;overflow:visible}' +
    '.plate{position:absolute;display:flex;gap:.45em;align-items:flex-start;background:rgba(17,17,17,.82);color:#f5f5f5;' +
    'border:1px solid var(--c);border-radius:6px;padding:.32em .6em;font:500 var(--fs)/1.3 -apple-system,"Segoe UI",Roboto,Arial,sans-serif;max-width:72%}' +
    '.plate b{color:var(--c);font-weight:700}.plate small{display:block;color:#bdbdbd;font-size:.78em;margin-top:.1em}' +
    '.cur{position:absolute;border-radius:50%;background:rgba(255,255,255,.55);border:1.5px solid rgba(0,0,0,.7);box-shadow:0 0 0 1px rgba(255,255,255,.6);transform:translate(-50%,-50%);display:none}' +
    '.ring{position:absolute;border-radius:50%;border:3px solid #FFD60A;transform:translate(-50%,-50%) scale(.3);opacity:1;' +
    'animation:qa-ring .45s ease-out forwards}@keyframes qa-ring{to{transform:translate(-50%,-50%) scale(1.6);opacity:0}}' +
    '</style><svg></svg><div class="labels"></div><div class="plate cap" style="display:none"></div><div class="cur"></div>';
  doc.documentElement.appendChild(host);
  const svg = root.querySelector('svg'), labels = root.querySelector('.labels'), cap = root.querySelector('.cap'), cur = root.querySelector('.cur');
  const maskStyle = doc.createElement('style');
  maskStyle.setAttribute('data-qa-clip-mask', '');
  (doc.head || doc.documentElement).appendChild(maskStyle);
  let state = cfg;
  const ext = {};  // boxes of targets the page cannot resolve (Playwright selectors): pushed from node
  const vw = () => innerWidth, vh = () => innerHeight;
  const S = () => Math.max(1, Math.min(2.5, vw() / 720));
  const visible = (e) => { const r = e.getBoundingClientRect(), cs = getComputedStyle(e); return r.width > 0 && r.height > 0 && cs.visibility !== 'hidden' && cs.display !== 'none'; };
  // CSS selector or "iframe … >>> css" (same-origin frames); {bad: true} — not resolvable here
  const resolve = (sel) => {
    const parts = String(sel).split('>>>').map(s => s.trim());
    let d = doc, ox = 0, oy = 0;
    try {
      for (let i = 0; i < parts.length - 1; i++) {
        const fr = d.querySelector(parts[i]);
        if (!fr || !fr.contentDocument) return { bad: true };
        const r = fr.getBoundingClientRect();
        ox += r.left + fr.clientLeft; oy += r.top + fr.clientTop; d = fr.contentDocument;
      }
      const el = [...d.querySelectorAll(parts[parts.length - 1])].find(visible);
      if (!el) return null;
      const r = el.getBoundingClientRect();
      return { x: r.left + ox, y: r.top + oy, width: r.width, height: r.height };
    } catch { return { bad: true }; }
  };
  const status = () => (state.targets || []).map(t => (resolve(t.selector) || {}).bad ? 'bad' : 'css');
  const applyMask = () => {
    const ok = [], bad = [];
    for (const m of state.mask || []) { try { doc.querySelectorAll(m); ok.push(m); } catch { bad.push(m); } }
    maskStyle.textContent = ok.length ? `${ok.join(',')}{filter:blur(${Math.round(7 * S())}px)!important}` : '';
    return bad;
  };
  let badMask = applyMask();
  let lastSig = '';
  const draw = () => {
    const s = S();
    const items = (state.targets || []).map((t, i) => {
      let b = resolve(t.selector);
      if (!b || b.bad) b = ext[i] || null;
      return b ? { ...t, b } : null;
    }).filter(Boolean);
    const P = 4 * s;
    // redraw only when something moved or changed (no layout work in idle frames)
    const sig = JSON.stringify([vw(), vh(), state.caption, state.stepText, state.captionColor,
      items.map(it => [it.label, Math.round(it.b.x), Math.round(it.b.y), Math.round(it.b.width), Math.round(it.b.height)])]);
    if (sig === lastSig) return;
    lastSig = sig;
    let html = '';
    labels.textContent = '';
    const taken = items.map(it => [it.b.x - P, it.b.y - P, it.b.width + 2 * P, it.b.height + 2 * P]);
    for (const it of items) {
      const x = it.b.x - P, y = it.b.y - P, w = it.b.width + 2 * P, h = it.b.height + 2 * P, r = 4 * s;
      html += `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="${r}" fill="none" stroke="rgba(0,0,0,.55)" stroke-width="${3 * s}" stroke-dasharray="${6 * s} ${4 * s}"/>` +
        `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="${r}" fill="none" stroke="${it.color}" stroke-width="${1.6 * s}" stroke-dasharray="${6 * s} ${4 * s}"/>`;
      if (it.label) {
        const el = doc.createElement('div');
        el.className = 'plate';
        el.style.setProperty('--c', it.color); el.style.setProperty('--fs', `${Math.round(12 * s)}px`);
        el.innerHTML = '<b></b><span></span>';
        el.firstChild.textContent = it.icon; el.lastChild.textContent = it.label;
        labels.appendChild(el);
        const lw = el.offsetWidth, lh = el.offsetHeight, g = 6 * s;
        // candidates around the frame (above, below, right, left, then shifted), clamped to the screen; the best has the
        // least overlap with frames and labels and does not cover buttons and links of the page
        const clampX = (lx) => Math.max(2, Math.min(vw() - lw - 2, lx)), clampY = (ly) => Math.max(2, Math.min(vh() - lh - 2, ly));
        const cands = [[x, y - lh - g], [x, y + h + g], [x + w + g, y], [x - lw - g, y], [x + w + g, y + h - lh], [x - lw - g, y + h - lh],
          [x + w - lw, y - lh - g], [x + w - lw, y + h + g]].map(([lx, ly]) => [clampX(lx), clampY(ly)]);
        const overlap = (r) => taken.reduce((sum, o) => sum + Math.max(0, Math.min(r[0] + lw, o[0] + o[2]) - Math.max(r[0], o[0])) *
          Math.max(0, Math.min(r[1] + lh, o[1] + o[3]) - Math.max(r[1], o[1])), 0);
        // elementFromPoint skips the overlay (pointer-events: none)
        const ui = (r) => [[0.1, 0.5], [0.5, 0.5], [0.9, 0.5], [0.5, 0.1], [0.5, 0.9]].some(([fx, fy]) => {
          const e = doc.elementFromPoint(r[0] + lw * fx, r[1] + lh * fy);
          return !!(e && e.closest && e.closest('a[href],button,input,select,textarea,[role=button],[role=link],[role=tab],[role=menuitem]'));
        });
        let pos = null, best = Infinity;
        for (const c of cands) {
          const score = overlap(c) * 4 + (ui(c) ? lw * lh : 0);
          if (score < best - 0.5) { best = score; pos = c; }
          if (score === 0) break;
        }
        taken.push([pos[0], pos[1], lw, lh]);
        el.style.left = `${pos[0]}px`; el.style.top = `${pos[1]}px`;
      }
    }
    svg.innerHTML = html;
    if (state.caption || state.stepText) {
      cap.style.display = 'flex';
      cap.style.setProperty('--c', state.captionColor); cap.style.setProperty('--fs', `${Math.round(14 * s)}px`);
      cap.innerHTML = '<b></b><div><span></span><small></small></div>';
      cap.firstChild.textContent = state.captionIcon;
      cap.querySelector('span').textContent = state.caption || '';
      const sm = cap.querySelector('small');
      sm.textContent = state.stepText ? `▸ ${state.stepText}` : '';
      if (!state.stepText) sm.remove();
      // bottom-left; to the top when it would cover a target
      const m = 12 * s, ch = cap.offsetHeight, cw = cap.offsetWidth;
      let top = vh() - ch - m;
      if (items.some(it => it.b.y + it.b.height + P > top && it.b.x - P < m + cw)) top = m;
      cap.style.left = `${m}px`; cap.style.top = `${top}px`;
    } else cap.style.display = 'none';
  };
  let raf = 0;
  const tick = () => { try { draw(); } catch { /* never break the page */ } raf = requestAnimationFrame(tick); };
  tick();
  const iv = setInterval(() => { try { draw(); } catch { /* ignore */ } }, 150);  // background tab: rAF may pause
  const move = (e) => {
    if (!state.cursor) return;
    const p = e.touches && e.touches[0] ? e.touches[0] : e;
    const s = S();
    cur.style.display = 'block';
    cur.style.width = cur.style.height = `${11 * s}px`;
    cur.style.left = `${p.clientX}px`; cur.style.top = `${p.clientY}px`;
  };
  const down = (e) => {
    if (!state.cursor) return;
    move(e);
    const p = e.touches && e.touches[0] ? e.touches[0] : e, s = S();
    const ring = doc.createElement('div');
    ring.className = 'ring';
    ring.style.width = ring.style.height = `${44 * s}px`;
    ring.style.left = `${p.clientX}px`; ring.style.top = `${p.clientY}px`;
    root.appendChild(ring);
    setTimeout(() => ring.remove(), 600);
  };
  const opts = { capture: true, passive: true };
  const evs = [['pointermove', move], ['mousemove', move], ['pointerdown', down], ['touchstart', down]];
  for (const [n, f] of evs) addEventListener(n, f, opts);
  W.__qaClip = {
    update(c) { state = { ...state, ...c }; badMask = applyMask(); lastSig = ''; draw(); },
    setBox(i, b) { ext[i] = b; },
    status() { return { targets: status(), badMask }; },
    remove() {
      cancelAnimationFrame(raf); clearInterval(iv);
      for (const [n, f] of evs) removeEventListener(n, f, opts);
      host.remove(); maskStyle.remove();
      delete W.__qaClip;
    },
  };
  return W.__qaClip.status();
}

// ---- helpers -----------------------------------------------------------------------------------------------------
function parseTarget(raw) {
  const [selector, label = '', kind = 'error'] = String(raw).split('|');
  const k = (kind || 'error').trim();
  const [color, icon] = STYLE[k] || STYLE.error;
  return { selector: selector.trim(), label: label.trim(), kind: k, color, icon };
}

function pySettings(runDir) {
  const r = spawnSync(PY, [path.join(SCRIPTS, 'clips.py'), 'settings', ...(runDir ? [runDir] : [])], { encoding: 'utf8', timeout: 30000 });
  try { return JSON.parse(String(r.stdout).trim().split('\n').pop()); } catch { return null; }
}

function playwrightHasScreencast() {
  try {
    const types = path.join(path.dirname(require.resolve('playwright-core/package.json')), 'types', 'types.d.ts');
    return /\bscreencast:\s*Screencast\b/.test(fs.readFileSync(types, 'utf8'));
  } catch { return false; }
}

function stepLabel(action, res, target) {
  const el = (res && res.element) || {};
  const what = String(el.text || el.name || (typeof target === 'string' ? target : '') || '').replace(/\s+/g, ' ').trim().slice(0, 48);
  if (action === 'goto') return `Открыть ${target}`;
  if (action === 'fill') return `Ввести текст в «${what}»`;
  if (action.startsWith('press ')) return `Клавиша ${action.slice(6)} в «${what}»`;
  const verb = { click: 'Нажать', dblclick: 'Двойное нажатие', check: 'Отметить', uncheck: 'Снять отметку', selectOption: 'Выбрать в',
    setInputFiles: 'Файл в' }[action] || action;
  return `${verb} «${what}»`;
}

function inferRun(out, runDirArg) {
  const dir = path.dirname(out);
  const run = runDirArg && runDirArg !== true ? path.resolve(String(runDirArg)) : (path.basename(dir) === 'clips' ? path.dirname(dir) : dir);
  const sub = path.relative(run, dir) || '.';
  if (sub.startsWith('..') || path.isAbsolute(sub)) throw new ClipError(EXIT.INPUT, `--out ${out} не внутри --run-dir ${run}`);
  return { run, sub: sub.split(path.sep).join('/') };
}

// ---- main -----------------------------------------------------------------------------------------------------------
async function main() {
  const argv = process.argv.slice(2).flatMap(x => (BOOL.has(x) ? [x, 'true'] : [x]));
  const a = parseArgs(argv, { wait: '500', hold: '1000' });
  if (!a.out || a.out === true) throw new ClipError(EXIT.INPUT, 'нужен --out <RUN_DIR>/clips/F-NNN-кратко.mp4');
  if (!a.url && !a.cdp) throw new ClipError(EXIT.INPUT, 'нужен --url URL или --cdp http://127.0.0.1:9222');
  const out = path.resolve(String(a.out));
  const name = path.basename(out).replace(/\.(mp4|webm|mov|gif)$/i, '');
  if (!/^[\w.-]+$/.test(name) || name.startsWith('.')) throw new ClipError(EXIT.INPUT, `имя ролика «${name}»: латиница, цифры, «-», «_» (F-004-menu)`);
  const { run, sub } = inferRun(out, a['run-dir']);
  if (!fs.existsSync(run)) throw new ClipError(EXIT.INPUT, `нет папки прогона ${run}`);
  const kind = a.kind && a.kind !== true ? String(a.kind) : 'error';
  if (!['error', 'ok', 'note', 'after'].includes(kind)) throw new ClipError(EXIT.INPUT, '--kind error|ok|note|after');
  const fmt = a.format && a.format !== true ? String(a.format) : null;
  if (fmt && !['mp4', 'gif', 'both'].includes(fmt)) throw new ClipError(EXIT.INPUT, '--format mp4|gif|both');
  const warnings = [];
  const st = pySettings(fs.existsSync(path.join(run, 'run-config.yaml')) ? run : null);
  if (!st) warnings.push('настройки clips: не прочитаны (python3 scripts/clips.py settings) — умолчания');
  const S = st || { max_seconds: 10, caption: true, mask: [], keep_raw: false };
  const seconds = a.seconds && a.seconds !== true ? Number(a.seconds) : Number(S.max_seconds || 10);
  if (!(seconds >= 1 && seconds <= 60)) throw new ClipError(EXIT.INPUT, '--seconds 1..60');
  const hold = Math.max(0, Number(a.hold) || 0);
  const caption = a.caption && a.caption !== true ? String(a.caption) : '';
  const targets = a._.concat(multiArg(argv, 'target')).map(parseTarget).filter(t => t.selector);
  const mask = [...(S.mask || []), ...(a.mask && a.mask !== true ? String(a.mask).split(',').map(s => s.trim()).filter(Boolean) : [])];
  if (mask.some(m => m.includes('>>>'))) warnings.push('--mask: селекторы внутри iframe (>>>) не размываются — только документ страницы');
  const keepRaw = !!a['keep-raw'] || !!S.keep_raw;
  const cursor = !a['no-cursor'];
  const readOnly = !!a['read-only'];
  const setupFile = a.setup && a.setup !== true ? path.resolve(String(a.setup)) : null;
  const prepareFile = a.prepare && a.prepare !== true ? path.resolve(String(a.prepare)) : null;
  for (const f of [setupFile, prepareFile]) if (f && !fs.existsSync(f)) throw new ClipError(EXIT.INPUT, `нет файла шагов ${f}`);

  // Guard first: a rules path that is given but broken is a stop (code 4), before any browser starts.
  const rules = loadRules(a.rules);
  let pw;
  try { pw = require('playwright'); } catch (e) { throw new ClipError(EXIT.UNAVAILABLE, `Playwright недоступен (${e.code || e.message}) — ${ENV_HINT}`); }
  const { openDevice, attachCdp } = require('./device_context');
  const { guardedPage, GuardConfirmError } = require('./guard');
  const { locate } = require('./frames');
  void pw;

  const forced = process.env.SITE_QA_CLIP_MODE;
  const attach = !!a.cdp && !a.device && !a.size;
  let recorder = forced === 'video' ? 'recordVideo' : forced === 'screencast' ? 'screencast' : (playwrightHasScreencast() ? 'screencast' : 'recordVideo');
  if (recorder === 'recordVideo' && attach)
    throw new ClipError(EXIT.UNAVAILABLE, 'запись вкладки пользователя по CDP требует page.screencast (свежий Playwright, в скиле 1.63) — ' +
      'обновите: cd <SKILL_DIR>/scripts/node && npm install playwright@latest; или запишите в эмуляции (--device / --size)');
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'qa-clip-'));
  const raw = path.join(tmp, 'raw.webm');
  const device = a.device || a.size;
  let dev;
  try {
    if (attach) dev = await attachCdp(String(a.cdp), a['page-match'] && a['page-match'] !== true ? String(a['page-match']) : undefined);
    else {
      const vp = (() => { try { return require('./device_context').resolveDevice(String(device || 'desktop')).options.viewport; } catch { return null; } })();
      dev = await openDevice({ device: device ? String(device) : 'desktop', cdp: a.cdp && a.cdp !== true ? String(a.cdp) : undefined,
        storageState: a.state && a.state !== true ? JSON.parse(fs.readFileSync(String(a.state), 'utf8')) : undefined,
        rules, logFile: a.log, readOnly,
        contextOptions: recorder === 'recordVideo' ? { recordVideo: { dir: tmp, ...(vp ? { size: vp } : {}) } } : null });
    }
  } catch (e) {
    fs.rmSync(tmp, { recursive: true, force: true });
    if (e && e.exitCode === 4) throw e;
    throw new ClipError(EXIT.UNAVAILABLE, `браузер не открылся: ${String(e.message || e).split('\n')[0]} — ${ENV_HINT}`);
  }
  const ctxStart = Date.now();
  const page = dev.page;
  const ctx = { steps: [], denied: [], aborted: null, abortWait: null };
  let recording = false, stopRec = null, overlayOn = false, polls = null, sens = null;
  const abortP = new Promise((_, rej) => { ctx.abortWait = rej; });
  abortP.catch(() => {});
  const abort = (code, msg, extra) => { if (!ctx.aborted) { ctx.aborted = new ClipError(code, msg, extra); ctx.abortWait(ctx.aborted); } };
  const overlayCfg = {
    targets, mask, cursor, caption: S.caption === false ? '' : caption,
    captionColor: STYLE[kind][0], captionIcon: STYLE[kind][1], stepText: '',
  };
  const installOverlay = async () => {
    const r = await page.evaluate(overlayInPage, overlayCfg).catch(() => null);
    overlayOn = !!r;
    return r;
  };
  const checkSensitive = async () => urlSensitive(page.url(), rules) || await page.evaluate(domSensitiveInPage).catch(() => null);
  const notes = [];
  const result = { ok: false, recorder, cdp: attach, warnings, notes };
  try {
    const guarded = guardedPage(page, rules, { logFile: a.log, throttleMs: 0, readOnly });
    const url = toUrl(a.url);
    if (url && url !== true) {
      const why = urlSensitive(String(url), rules);
      if (why) throw new ClipError(EXIT.FORBIDDEN, `запись запрещена: ${why} — записывайте после входа или на гостевом экране`);
      const nav = await guarded.goto(String(url), { waitUntil: 'load', timeout: 45000 });
      if (!nav.performed) throw new ClipError(EXIT.FORBIDDEN, 'переход запрещён guard: ' + nav.reason);
    }
    await page.waitForTimeout(+a.wait || 0);
    if (prepareFile) await require(prepareFile)({ page, guarded, clip: { caption() {}, step() {}, wait: (ms) => page.waitForTimeout(ms) } });
    const why0 = await checkSensitive();
    if (why0) throw new ClipError(EXIT.FORBIDDEN, `запись запрещена: ${why0} — записывайте после входа или на гостевом экране`);
    if (attach) {
      const hidden = await page.evaluate(() => document.visibilityState !== 'visible').catch(() => false);
      if (hidden) { await page.bringToFront().catch(() => {}); notes.push('вкладка пользователя была в фоне — выведена на передний план для записи'); }
    }
    const st0 = await installOverlay();
    if (!st0) warnings.push('подсветка и подпись не встроены в страницу (CSP или ошибка скрипта) — ролик без разметки');
    else {
      if (st0.badMask && st0.badMask.length) warnings.push('--mask: неверные селекторы ' + st0.badMask.join(', '));
      const bad = (st0.targets || []).map((v, i) => (v === 'bad' ? i : -1)).filter(i => i >= 0);
      if (bad.length) {  // Playwright selectors (text=, role=, cross-origin iframes): boxes from node every 150 ms
        polls = setInterval(async () => {
          for (const i of bad) {
            const b = await locate(page, targets[i].selector).filter({ visible: true }).first().boundingBox({ timeout: 120 }).catch(() => null);
            await page.evaluate(([j, box]) => window.__qaClip && window.__qaClip.setBox(j, box), [i, b]).catch(() => {});
          }
        }, 150);
      }
    }
    const missing = [];
    for (const t of targets) {
      const n = await locate(page, t.selector).count().catch(() => 0);
      if (!n) missing.push(t.selector);
    }
    if (missing.length) notes.push('цели пока не найдены (рамка появится, когда элемент станет видимым): ' + missing.join(', '));
    // Navigations during the recording: overlay again; a login/payment page stops everything.
    page.on('domcontentloaded', () => { if (!ctx.aborted && overlayOn) installOverlay(); });
    page.on('framenavigated', (f) => {
      if (f !== page.mainFrame() || !recording) return;
      const why = urlSensitive(f.url(), rules);
      if (why) abort(EXIT.FORBIDDEN, `запись остановлена: ${why} — ролик удалён`);
    });
    await page.waitForTimeout(120);  // the mask and the frames are painted before the first frame

    // ---- record ----
    const vsize = await page.evaluate(() => [innerWidth, innerHeight]).catch(() => [1280, 720]);
    const size = { width: Math.max(2, vsize[0] - vsize[0] % 2), height: Math.max(2, vsize[1] - vsize[1] % 2) };
    let tStart;
    if (recorder === 'screencast') {
      if (!page.screencast || typeof page.screencast.start !== 'function')
        throw new ClipError(EXIT.UNAVAILABLE, 'в этой версии Playwright нет page.screencast — ' + ENV_HINT);
      await page.screencast.start({ path: raw, size });
      tStart = Date.now();
      stopRec = async () => { await page.screencast.stop(); };
      result.start = 0;
    } else {
      tStart = Date.now();
      result.start = Math.max(0, (tStart - ctxStart) / 1000 - 0.15);
      stopRec = async () => { const v = page.video(); await page.close(); if (!v) throw new Error('recordVideo: видео нет'); await v.saveAs(raw); };
    }
    recording = true;
    sens = setInterval(async () => {
      if (!recording || ctx.aborted) return;
      const why = await page.evaluate(domSensitiveInPage).catch(() => null);
      if (why) abort(EXIT.FORBIDDEN, `запись остановлена: ${why} — ролик удалён`);
    }, 400);
    const maxMs = seconds * 1000;
    const setStep = async (text) => {
      overlayCfg.stepText = text;
      await page.evaluate((t) => window.__qaClip && window.__qaClip.update({ stepText: t }), text).catch(() => {});
    };
    const moveTo = async (target) => {
      if (!cursor) return;
      const b = await locate(page, target).first().boundingBox({ timeout: 1000 }).catch(() => null);
      if (b) await page.mouse.move(b.x + b.width / 2, b.y + b.height / 2, { steps: 8 }).catch(() => {});
    };
    const wrap = (action, fn, opts = {}) => async (...args) => {
      if (ctx.aborted) throw ctx.aborted;
      const target = args[0];
      if (opts.typing && typeof target === 'string') {
        const secret = await locate(page, target).first().evaluate(secretFieldInPage).catch(() => false);
        if (secret) { abort(EXIT.FORBIDDEN, 'запись остановлена: ввод в поле пароля, платёжных данных или кода — ролик удалён'); throw ctx.aborted; }
      }
      if (action === 'goto') {
        const why = urlSensitive(String(target), rules);
        if (why) { abort(EXIT.FORBIDDEN, `запись остановлена: переход на ${why} — ролик удалён`); throw ctx.aborted; }
      }
      if (opts.pointer && typeof target === 'string') await moveTo(target);
      const res = await fn(...args);
      if (res && res.performed === false) {
        ctx.denied.push({ action, target: String(target), reason: res.reason, rule: res.rule });
        warnings.push(`шаг не выполнен (guard: ${res.rule || res.decision}): ${action} ${String(target).slice(0, 60)} — ${res.reason}`);
      } else {
        const label = stepLabel(action, res, target);
        ctx.steps.push(label);
        await setStep(label);
      }
      return res;
    };
    const g = {
      ...guarded,
      click: wrap('click', guarded.click, { pointer: true }), dblclick: wrap('dblclick', guarded.dblclick, { pointer: true }),
      check: wrap('check', guarded.check, { pointer: true }), uncheck: wrap('uncheck', guarded.uncheck, { pointer: true }),
      fill: wrap('fill', guarded.fill, { typing: true }), selectOption: wrap('selectOption', guarded.selectOption, { pointer: true }),
      setInputFiles: wrap('setInputFiles', guarded.setInputFiles),
      press: (t, key, o) => wrap('press ' + key, (tt) => guarded.press(tt, key, o), { typing: true })(t),
      goto: wrap('goto', guarded.goto),
    };
    const clip = {
      caption: async (text, k) => {
        const [c, i] = STYLE[k] || STYLE[kind];
        Object.assign(overlayCfg, { caption: String(text || ''), captionColor: c, captionIcon: i });
        await page.evaluate((u) => window.__qaClip && window.__qaClip.update(u), { caption: overlayCfg.caption, captionColor: c, captionIcon: i }).catch(() => {});
      },
      step: async (text) => { ctx.steps.push(String(text)); await setStep(String(text)); },
      wait: (ms) => page.waitForTimeout(ms),
    };
    await page.waitForTimeout(Math.min(400, maxMs / 4));  // lead-in: the state before the steps
    let cut = false;
    if (setupFile) {
      const budget = Math.max(500, maxMs - hold - (Date.now() - tStart) - 300);
      let timer;
      const timeout = new Promise((resolve) => { timer = setTimeout(() => { cut = true; resolve(); }, budget); });
      try { await Promise.race([require(setupFile)({ page, guarded: g, clip }), timeout, abortP]); }
      catch (e) {
        if (ctx.aborted) throw ctx.aborted;
        if (e instanceof GuardConfirmError) throw new ClipError(EXIT.FORBIDDEN, 'шаг требует подтверждения пользователя — ролик не записан: ' + e.message, { question: e.question });
        if (e && e.exitCode === 4) throw e;
        throw new ClipError(EXIT.INPUT, `шаги (${path.basename(setupFile)}) упали: ${String(e.message || e).split('\n')[0]}`);
      } finally { clearTimeout(timer); }
      if (cut) warnings.push(`шаги не уложились в ${seconds} с — ролик обрезан (--seconds больше или шагов меньше)`);
    }
    const left = maxMs - (Date.now() - tStart) - 150;
    await Promise.race([page.waitForTimeout(Math.max(0, Math.min(hold, left))), abortP]);
    if (ctx.aborted) throw ctx.aborted;
    const whyEnd = await checkSensitive();
    if (whyEnd) throw new ClipError(EXIT.FORBIDDEN, `запись остановлена: ${whyEnd} — ролик удалён`);
    recording = false;
    clearInterval(sens); sens = null;
    if (polls) { clearInterval(polls); polls = null; }
    if (recorder === 'screencast') {  // overlay off after the last frame, before stop of a CDP tab
      await stopRec(); stopRec = null;
      if (overlayOn) await page.evaluate(() => window.__qaClip && window.__qaClip.remove()).catch(() => {});
      overlayOn = false;
    } else { await stopRec(); stopRec = null; overlayOn = false; }
    result.recordedMs = Date.now() - tStart;
  } catch (e) {
    recording = false;
    if (sens) clearInterval(sens);
    if (polls) clearInterval(polls);
    if (stopRec) await stopRec().catch(() => {});
    if (overlayOn) await page.evaluate(() => window.__qaClip && window.__qaClip.remove()).catch(() => {});
    await dev.close().catch(() => {});
    fs.rmSync(tmp, { recursive: true, force: true });  // a forbidden recording is never kept
    if (e instanceof ClipError || (e && e.exitCode === 4)) throw e;
    throw new ClipError(EXIT.INPUT, String(e.message || e).split('\n')[0]);
  }
  await dev.close().catch(() => {});

  // ---- finalize: compress, GIF, poster, frame sheet, finding ----
  let src = raw;
  if (!fs.existsSync(src) && recorder === 'recordVideo') {
    const w = fs.readdirSync(tmp).find(f => f.endsWith('.webm'));
    if (w) src = path.join(tmp, w);
  }
  if (!fs.existsSync(src) || !fs.statSync(src).size) { fs.rmSync(tmp, { recursive: true, force: true }); throw new ClipError(EXIT.UNAVAILABLE, 'ролик не записан (пустой файл) — ' + ENV_HINT); }
  if (keepRaw) {
    const keep = path.join(run, 'recordings', `${name}-raw.webm`);
    fs.mkdirSync(path.dirname(keep), { recursive: true });
    fs.copyFileSync(src, keep);
    src = keep;
    result.raw = keep;
  }
  const stepsFile = path.join(tmp, 'steps.json');
  fs.writeFileSync(stepsFile, JSON.stringify(ctx.steps));
  const args = [path.join(SCRIPTS, 'clips.py'), 'finalize', run, '--src', src, '--name', name, '--subdir', sub, '--kind', kind,
    '--steps-json', stepsFile, '--max-seconds', String(seconds), '--no-burn-caption'];
  if (caption) args.push('--caption', caption);
  if (a.finding && a.finding !== true) args.push('--finding', String(a.finding));
  if (result.start) args.push('--start', result.start.toFixed(2));
  if (fmt) args.push('--format', fmt);
  if (keepRaw) args.push('--keep-raw');
  const r = spawnSync(PY, args, { encoding: 'utf8', timeout: 600000 });
  let fin = null;
  try { fin = JSON.parse(String(r.stdout || '').trim().split('\n').pop()); } catch { fin = null; }
  if (!fin || !fin.ok) {
    // Python or ffmpeg failed: keep the raw recording as it is (webm), with a warning.
    const dst = path.join(run, sub, `${name}.webm`);
    fs.mkdirSync(path.dirname(dst), { recursive: true });
    fs.copyFileSync(src, dst);
    warnings.push('clips.py finalize не выполнен (' + ((fin && fin.error) || String(r.stderr || r.error || '').trim().split('\n').pop() || 'нет ответа') +
      `) — ролик сохранён как есть: ${dst}`);
    Object.assign(result, { ok: true, clip: { file: path.relative(run, dst).split(path.sep).join('/'), kind, caption, steps: ctx.steps, viewed: false }, files: { file: dst } });
  } else {
    warnings.push(...(fin.warnings || []));
    Object.assign(result, { ok: true, clip: fin.clip, files: fin.files, finding: fin.finding, next: fin.next });
  }
  fs.rmSync(tmp, { recursive: true, force: true });
  result.steps = ctx.steps;
  if (ctx.denied.length) result.denied = ctx.denied;
  return result;
}

if (require.main === module) {
  main().then((res) => {
    process.stdout.write(JSON.stringify(res) + '\n');
    process.exit(res.warnings && res.warnings.length ? EXIT.WARN : EXIT.OK);
  }).catch((e) => {
    const code = e instanceof ClipError ? e.code : (e && e.exitCode === 4) ? EXIT.UNAVAILABLE : EXIT.INPUT;
    const msg = String((e && e.message) || e).split('\n')[0] + (code === EXIT.UNAVAILABLE && !(e instanceof ClipError) ? ' — ' + ENV_HINT : '');
    process.stdout.write(JSON.stringify({ ok: false, code, error: msg, ...((e && e.extra) || {}) }) + '\n');
    process.stderr.write(msg + '\n');
    process.exit(code);
  });
}

module.exports = { urlSensitive, parseTarget, inferRun, stepLabel, SENSITIVE_PATH };
