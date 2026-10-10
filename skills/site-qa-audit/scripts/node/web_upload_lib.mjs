// Shared helpers for the `screenshots: web-upload` strategy (publish_web.mjs, comment_web.mjs).
//
// Design rules (see references/web-upload.md):
// - The browser is the user's own, already logged-in browser reached over CDP. This code never
//   types logins, passwords or tokens and never reads cookies or storage.
// - GitHub API calls go through the `gh` CLI (it owns authentication). The binary can be swapped
//   with --gh / QA_GH_BIN, which is how tests run against a local fake without touching github.com.
// - Selectors target the new GitHub UI: the comment box is found by its placeholder text and
//   buttons by their visible text. Nothing relies on <form> or name="comment[body]".
// - The only button this code may ever click is the exact "Comment" button. Close / Reopen and
//   similar buttons are refused by an explicit check right before the click.
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { createRequire } from 'node:module';

export const COMMENT_PLACEHOLDER = 'Use Markdown to format your comment';
export const SHOT_TOKEN_RE = /\{\{qa-shot:([^}\s]+)\}\}/g;
// Attachment links produced by GitHub uploads (new and legacy hosts). Host-agnostic on purpose
// so that local fixtures can emulate them.
export const ATTACHMENT_RE = /https?:\/\/[^\s)"'<>]+\/(?:user-attachments\/(?:assets|files)\/[A-Za-z0-9._-]+|user-images\.githubusercontent\.com\/[^\s)"'<>]+|[0-9]+\/[0-9a-f-]{36}\.[a-z0-9]+)/g;
// Any button whose text/name matches this is never clicked, whatever the caller asks.
export const FORBIDDEN_BUTTON_RE = /\b(close|closed|reopen|re-open|delete|remove|lock|unlock|transfer|pin|unpin)\b|закры|переоткры|удал/i;
export const EXIT = { OK: 0, USAGE: 1, ENV: 2, NAV_DENIED: 3, NOT_LOGGED_IN: 4, VERIFY_FAILED: 5, SAFETY_STOP: 6, UPLOAD_FAILED: 7 };

export class StopError extends Error {
  constructor(code, message, extra = {}) { super(message); this.code = code; this.extra = extra; }
}

// ---------- arguments ----------
const REPEATABLE = new Set(['shot', 'label']);
export function parseArgs(argv) {
  const out = { _: [], shot: [], label: [] };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (!a.startsWith('--')) { out._.push(a); continue; }
    let key = a.slice(2), val;
    const eq = key.indexOf('=');
    if (eq >= 0) { val = key.slice(eq + 1); key = key.slice(0, eq); }
    else {
      const next = argv[i + 1];
      if (next === undefined || next.startsWith('--')) val = true; else { val = next; i++; }
    }
    if (REPEATABLE.has(key)) out[key].push(...String(val).split(',').map(s => s.trim()).filter(Boolean));
    else out[key] = val;
  }
  return out;
}

export function validateRepo(repo) {
  if (!repo || !/^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(repo))
    throw new StopError(EXIT.USAGE, `Нужен --repo в виде owner/repo (получено: ${repo || 'ничего'}).`);
  return repo;
}

export function fillTemplate(tpl, vars) {
  return tpl.replace(/\{(base|repo|number)\}/g, (_, k) => String(vars[k] ?? ''));
}

export const sleep = (ms) => new Promise(r => setTimeout(r, ms));
export const nonce = () => crypto.randomBytes(6).toString('hex');

// ---------- body / placeholders ----------
export const tokenFor = (name) => `{{qa-shot:${name}}}`;

// Prepare a body with one placeholder per screenshot. Local markdown images pointing at a shot
// (`![x](../screenshots/F-001-annotated.png)`) are turned into placeholders; shots without any
// reference get a placeholder appended above the site-qa-audit marker (or at the end).
export function preparePlaceholders(body, shots) {
  let out = body;
  for (const shot of shots) {
    const name = path.basename(shot);
    const esc = name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    // a clip (1.7.0): the link «[▶ ролик, 6 с, 0,4 МБ](…/F-004.mp4)» becomes the placeholder too (GitHub shows a player)
    const bang = isVideo(name) ? '!?' : '!';
    out = out.replace(new RegExp(`${bang}\\[[^\\]]*\\]\\([^)\\s]*${esc}(?:\\?[^)\\s]*)?\\)`, 'g'), tokenFor(name));
    if (!out.includes(tokenFor(name))) {
      const m = out.match(/\n?<!-- site-qa-audit:[^>]*-->\s*$/);
      out = m ? out.slice(0, m.index) + `\n\n${tokenFor(name)}\n` + m[0] : `${out.replace(/\s*$/, '')}\n\n${tokenFor(name)}\n`;
    }
  }
  return out;
}

export function replacePlaceholders(body, snippets) {
  let out = body;
  for (const [name, snippet] of Object.entries(snippets)) out = out.split(tokenFor(name)).join(snippet);
  return out;
}

// Verification used after every publish: attachments present, no placeholders, no upload stubs.
export function checkBody(body, expectedCount) {
  const problems = [];
  const left = [...(body || '').matchAll(SHOT_TOKEN_RE)].map(m => m[1]).concat([...(body || '').matchAll(RU_SHOT_RE)].map(m => m[1]));
  if (left.length) problems.push(`остались плейсхолдеры: ${left.join(', ')}`);
  if (/!\[Uploading [^\]]*\]\(\)/i.test(body || '')) problems.push('остался текст «Uploading …» незавершённой загрузки');
  const attachments = [...new Set((body || '').match(ATTACHMENT_RE) || [])];
  if (attachments.length < expectedCount) problems.push(`вложений ${attachments.length}, ожидалось не меньше ${expectedCount}`);
  return { ok: problems.length === 0, problems, attachments };
}

// ---------- gh CLI (auth stays inside gh; tokens are never read here) ----------
export function ghBin(args) { return args.gh && args.gh !== true ? String(args.gh) : (process.env.QA_GH_BIN || 'gh'); }

export function gh(bin, argv, { input } = {}) {
  const r = spawnSync(bin, argv, { encoding: 'utf8', input, maxBuffer: 32 * 1024 * 1024 });
  if (r.error) throw new StopError(EXIT.ENV, `Не удалось запустить ${bin}: ${r.error.message}`);
  if (r.status !== 0) throw new StopError(EXIT.ENV, `${bin} ${argv.slice(0, 2).join(' ')} завершился с кодом ${r.status}: ${(r.stderr || '').trim().slice(0, 300)}`);
  return r.stdout;
}

export function ghIssue(bin, repo, number) {
  return JSON.parse(gh(bin, ['api', `repos/${repo}/issues/${number}`]));
}

export function ghComments(bin, repo, number) {
  const raw = gh(bin, ['api', '--paginate', `repos/${repo}/issues/${number}/comments`]);
  // --paginate concatenates JSON arrays: "[...][...]".
  return JSON.parse(`[${raw.trim().replace(/\]\s*\[/g, '],[')}]`).flat();
}

// ---------- browser over CDP ----------
const nodeRequire = createRequire(import.meta.url);

// guard.js (site rules) is deliberately NOT applied here: the audited site's rules.json has its own
// allowed_domains (github.com is outside them) and would classify "Comment" as send-to-people.
// Publishing runs under the explicit --confirm-publish consent plus the strict host lock below.
// loadGuard() is exported only so callers can report whether guard.js is available.
export function loadGuard() {
  try { return nodeRequire('./guard.js'); } catch { return null; }
}

export async function connect(cdpUrl) {
  const { chromium } = nodeRequire('playwright');
  let browser;
  try { browser = await chromium.connectOverCDP(cdpUrl, { timeout: 15000 }); }
  catch (e) {
    throw new StopError(EXIT.ENV, `Не удалось подключиться к браузеру по CDP (${cdpUrl}). Запустите Chrome с --remote-debugging-port и войдите в GitHub вручную. Подробности: ${String(e.message || e).split('\n')[0]}`);
  }
  const context = browser.contexts()[0];
  if (!context) throw new StopError(EXIT.ENV, 'В браузере нет открытого профиля (контекста). Откройте окно Chrome, где выполнен вход в GitHub.');
  return { browser, context };
}

// Local host lock: main-frame document navigations may only go to the GitHub base host.
// Attempts are written to <log-dir>/blocked.jsonl.
export async function lockNavigation(page, baseUrl, blockedLog) {
  const host = new URL(baseUrl).host;
  await page.route('**/*', (route) => {
    const req = route.request();
    if (req.isNavigationRequest() && req.frame() === page.mainFrame()) {
      let h = '';
      try { h = new URL(req.url()).host; } catch { /* invalid */ }
      if (h !== host) {
        logBlocked(blockedLog, { url: req.url(), reason: 'web-upload:host-lock' });
        return route.abort('blockedbyclient');
      }
    }
    return route.continue();
  });
}

export function logBlocked(file, entry) {
  if (!file) return;
  fs.mkdirSync(path.dirname(path.resolve(file)), { recursive: true });
  fs.appendFileSync(file, JSON.stringify({ ts: new Date().toISOString(), source: 'web-upload', ...entry }) + '\n');
}

export function assertSameHost(url, baseUrl) {
  const a = new URL(url), b = new URL(baseUrl);
  if (a.host !== b.host || a.protocol !== b.protocol)
    throw new StopError(EXIT.NAV_DENIED, `Переход на ${a.origin} запрещён: разрешён только ${b.origin}.`);
}

export async function openPage(context, url, opts) {
  assertSameHost(url, opts.baseUrl);
  const page = await context.newPage();
  page.on('dialog', d => d.dismiss().catch(() => {})); // native dialogs are always dismissed
  await lockNavigation(page, opts.baseUrl, opts.blockedLog);
  const resp = await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 30000 });
  page.__qaStatus = resp ? resp.status() : null;
  await page.waitForLoadState('load', { timeout: 15000 }).catch(() => {});
  return page;
}

// A freshly created issue sometimes answers 404 for a few seconds: retry with a growing pause (G-8).
export async function openPageRetry(context, url, opts, { tries = 3, pauseMs = 2000 } = {}) {
  for (let i = 0; i < tries; i++) {
    const page = await openPage(context, url, opts);
    if (page.__qaStatus !== 404) return page;
    await page.close().catch(() => {});
    if (i < tries - 1) await sleep(pauseMs * (i + 1));
  }
  throw new StopError(EXIT.ENV, `Страница ${url} отвечает 404 после ${tries} попыток — проверьте номер issue и права; повторите позже.`);
}

// Placeholders in an EXISTING issue body: {{qa-shot:file.png}} and «**[Скриншот: file.png]**» (G-8).
export const RU_SHOT_RE = /\*\*\[Скриншот:\s*([^\]]+?)\s*\]\*\*/g;
export function existingPlaceholders(body) {
  const out = [];
  for (const m of (body || '').matchAll(SHOT_TOKEN_RE)) out.push({ token: m[0], name: m[1] });
  for (const m of (body || '').matchAll(RU_SHOT_RE)) out.push({ token: m[0], name: m[1] });
  return out;
}

// Logged in = <meta name="user-login"> is non-empty (GitHub sets it for signed-in users) and the
// comment box is present. The script never tries to log in.
export async function ensureLoggedIn(page) {
  const login = await page.evaluate(() => {
    const m = document.querySelector('meta[name="user-login"]');
    return m ? (m.getAttribute('content') || '').trim() : '';
  });
  const onLoginPage = /\/(login|session|signup)(\/|$|\?)/.test(new URL(page.url()).pathname);
  if (!login || onLoginPage) {
    throw new StopError(EXIT.NOT_LOGGED_IN,
      'Нужен вход на GitHub в окне аудита: в браузере, к которому подключён скрипт, вход не выполнен. Войдите вручную в этом окне ' +
      'и запустите команду снова. Скрипт не вводит логины, пароли и токены.');
  }
  return login;
}

// Comment box lookup with fallbacks (new UI first). On failure the error lists every attempt.
export const COMMENT_BOX_SELECTORS = [
  { how: `placeholder «${COMMENT_PLACEHOLDER}»`, get: (p) => p.getByPlaceholder(COMMENT_PLACEHOLDER, { exact: false }) },
  { how: 'textbox «Markdown value»', get: (p) => p.getByRole('textbox', { name: 'Markdown value' }) },
  { how: 'textarea[aria-label*="comment" i]', get: (p) => p.locator('textarea[aria-label*="comment" i]') },
  { how: 'textarea[name="comment[body]"] (legacy UI)', get: (p) => p.locator('textarea[name="comment[body]"]') },
];

export async function findCommentBox(page) {
  const tried = [];
  for (const sel of COMMENT_BOX_SELECTORS) {
    const loc = sel.get(page);
    const n = await loc.count();
    // The new-comment box is the last visible one (inline editors come earlier on the page).
    for (let i = n - 1; i >= 0; i--) {
      if (await loc.nth(i).isVisible()) return loc.nth(i);
    }
    tried.push(`${sel.how}: найдено ${n}, видимых 0`);
  }
  throw new StopError(EXIT.NOT_LOGGED_IN,
    'Поле комментария не найдено. Попытки: ' + tried.join('; ') + '. Возможные причины: нет входа на GitHub в окне аудита, ' +
    'нет прав на комментарии, issue заблокирован или интерфейс GitHub изменился.', { tried });
}

// Upload one file through the comment box and return the markdown/HTML snippet GitHub inserted.
export async function uploadOne(page, box, file, { timeoutMs = 60000 } = {}) {
  const before = new Set((await box.inputValue()).match(ATTACHMENT_RE) || []);
  const tried = [];
  let done = false;
  // 1) "Paste, drop, or click to add files" button (last = the new-comment box) -> file chooser (new UI)
  const btns = page.getByRole('button', { name: /paste, drop, or click to add files|attach files|add files|прикрепить/i });
  const nb = await btns.count();
  if (nb) {
    const btn = btns.nth(nb - 1);
    const label = `${(await btn.getAttribute('aria-label')) || ''} ${(await btn.innerText().catch(() => '')) || ''}`;
    if (FORBIDDEN_BUTTON_RE.test(label)) throw new StopError(EXIT.SAFETY_STOP, `Кнопка прикрепления выглядит опасной («${label.trim()}») — остановка.`);
    try {
      const [chooser] = await Promise.all([page.waitForEvent('filechooser', { timeout: 10000 }), btn.click()]);
      await chooser.setFiles(file); done = true;
    } catch (e) { tried.push(`кнопка «Paste, drop, or click to add files»: ${String(e.message || e).split('\n')[0]}`); }
  } else tried.push('кнопка «Paste, drop, or click to add files»: не найдена');
  // 2) a file input inside the editor container (nearest ancestor that has one)
  if (!done) {
    const handle = await box.elementHandle();
    const input = await page.evaluateHandle((ta) => {
      let el = ta;
      for (let i = 0; i < 10 && el; i++, el = el.parentElement) {
        const f = el.querySelector && el.querySelector('input[type="file"]');
        if (f) return f;
      }
      return null;
    }, handle);
    const inputEl = input.asElement();
    if (inputEl) { await inputEl.setInputFiles(file); done = true; }
    else tried.push('input[type=file] рядом с полем: не найден');
  }
  if (!done) throw new StopError(EXIT.UPLOAD_FAILED, 'Не удалось прикрепить файл. Попытки: ' + tried.join('; '), { tried });
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const val = await box.inputValue();
    const fresh = (val.match(ATTACHMENT_RE) || []).filter(u => !before.has(u));
    if (fresh.length && !/Uploading [^\]]*\]\(\)/i.test(val)) {
      const url = fresh[fresh.length - 1];
      // the full snippet: <img ... src="url" ... /> or ![alt](url)
      const esc = url.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
      const m = val.match(new RegExp(`<img[^>]*${esc}[^>]*>`)) || val.match(new RegExp(`!\\[[^\\]]*\\]\\(${esc}\\)`)) || val.match(new RegExp(`\\[[^\\]]*\\]\\(${esc}\\)`));
      // a video is inserted as a bare link (GitHub renders a player); an image without a snippet — as ![](url)
      return { url, snippet: m ? m[0] : isVideo(file) ? `\n${url}\n` : `![${path.basename(file)}](${url})` };
    }
    await sleep(250);
  }
  throw new StopError(EXIT.UPLOAD_FAILED, `Загрузка ${path.basename(file)} не завершилась за ${Math.round(timeoutMs / 1000)} с (ссылка на вложение не появилась в поле).`);
}

// The ONLY click this module performs on GitHub: the exact "Comment" button nearest to the box.
// Every candidate is re-checked by visible text, aria-label and title; anything that mentions
// close/reopen/delete is skipped, and if no clean candidate remains the run stops.
export async function clickExactComment(page, box) {
  const candidates = page.getByRole('button', { name: 'Comment', exact: true });
  const n = await candidates.count();
  const boxHandle = await box.elementHandle();
  let best = null;
  for (let i = 0; i < n; i++) {
    const c = candidates.nth(i);
    if (!(await c.isVisible())) continue;
    const info = await c.evaluate((el, ta) => {
      const txt = (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim();
      // distance = depth of the lowest common ancestor with the comment box (smaller is closer)
      let a = el, depth = 0, lca = null;
      const anc = new Set(); for (let p = ta; p; p = p.parentElement) anc.add(p);
      for (; a; a = a.parentElement, depth++) if (anc.has(a)) { lca = a; break; }
      return { txt, aria: el.getAttribute('aria-label') || '', title: el.getAttribute('title') || '', disabled: el.disabled || el.getAttribute('aria-disabled') === 'true', depth: lca ? depth : 999 };
    }, boxHandle);
    const all = `${info.txt} ${info.aria} ${info.title}`;
    if (info.txt !== 'Comment' || (info.aria && info.aria !== 'Comment') || FORBIDDEN_BUTTON_RE.test(all) || info.disabled) continue;
    if (!best || info.depth < best.info.depth) best = { c, info };
  }
  if (!best) throw new StopError(EXIT.SAFETY_STOP, 'Не найдена кнопка с текстом ровно «Comment» (Close/Reopen не нажимаются никогда) — комментарий не отправлен.');
  // Defensive re-check immediately before the click.
  const finalText = (await best.c.innerText()).replace(/\s+/g, ' ').trim();
  if (finalText !== 'Comment' || FORBIDDEN_BUTTON_RE.test(finalText)) throw new StopError(EXIT.SAFETY_STOP, `Текст кнопки изменился на «${finalText}» — остановка без нажатия.`);
  await best.c.click();
  return finalText;
}

export function readText(file, what) {
  if (!file || file === true) throw new StopError(EXIT.USAGE, `Не указан ${what}.`);
  try { return fs.readFileSync(String(file), 'utf8'); }
  catch (e) { throw new StopError(EXIT.USAGE, `Не удалось прочитать ${what} (${file}): ${e.code || e.message}`); }
}

export const isVideo = (f) => /\.(mp4|mov|webm)$/i.test(String(f));
// GitHub attachment limit: 10 MB for images and videos on the free plan (100 MB for videos on paid plans) —
// checked before the browser is touched; --max-attach-mb raises it when the user knows the plan allows more.
export const ATTACH_LIMIT_MB = 10;

export function checkShots(shots, maxMb = ATTACH_LIMIT_MB) {
  if (!shots.length) throw new StopError(EXIT.USAGE, 'Нужен хотя бы один --shot <файл.png> (для публикации без картинок используйте gh напрямую).');
  for (const s of shots) {
    if (!fs.existsSync(s)) throw new StopError(EXIT.USAGE, `Файл скриншота не найден: ${s}`);
    if (!/\.(png|jpe?g|gif|webp|mp4|mov|webm)$/i.test(s)) throw new StopError(EXIT.USAGE, `Неподдерживаемый тип файла для вложения: ${s}`);
    const mb = fs.statSync(s).size / 1048576;
    if (mb > maxMb) {
      throw new StopError(EXIT.USAGE, `${path.basename(s)} — ${mb.toFixed(1)} МБ: GitHub принимает вложения до ${maxMb} МБ. ` +
        (isVideo(s) ? 'Сократите ролик (clips.py finalize … --max-mb 3 или короче --seconds в clip.js) или опубликуйте ссылкой из ветки ' +
          '(publish_shots.py push). Ничего не загружено.' : 'Уменьшите изображение. Ничего не загружено.'));
    }
  }
  const names = shots.map(s => path.basename(s));
  const dup = names.find((n, i) => names.indexOf(n) !== i);
  if (dup) throw new StopError(EXIT.USAGE, `Имена скриншотов должны различаться: ${dup}`);
}

export function emit(result, outFile) {
  const text = JSON.stringify(result, null, 2);
  if (outFile && outFile !== true) {
    fs.mkdirSync(path.dirname(path.resolve(String(outFile))), { recursive: true });
    fs.writeFileSync(String(outFile), text + '\n');
  }
  process.stdout.write(text + '\n');
}

export function printPlan(title, steps) {
  process.stderr.write(`${title}\n` + steps.map((s, i) => `  ${i + 1}. ${s}`).join('\n') + '\n' +
    'Это dry-run: ничего не создано и не отправлено. Для реального действия добавьте --confirm-publish.\n');
}

export async function runMain(fn) {
  try { process.exitCode = (await fn()) ?? 0; }
  catch (e) {
    if (e instanceof StopError) {
      process.stderr.write(`ОСТАНОВКА: ${e.message}\n`);
      if (e.extra && Object.keys(e.extra).length) process.stdout.write(JSON.stringify({ ok: false, code: e.code, error: e.message, ...e.extra }, null, 2) + '\n');
      process.exitCode = e.code;
    } else {
      process.stderr.write(`Ошибка: ${e && e.stack || e}\n`);
      process.exitCode = EXIT.ENV;
    }
  }
  // A CDP connection keeps the event loop alive; the user's browser itself is left untouched.
  setTimeout(() => process.exit(process.exitCode), 50);
}
