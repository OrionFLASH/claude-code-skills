'use strict';
// Общие утилиты node-скриптов site-qa-audit: аргументы, правила url_guard, троттлинг, вывод JSON.
const fs = require('fs');
const path = require('path');

// Flags of every browser script that never take a value (browserMode, tab registry): `--headed URL` keeps URL positional.
const BOOL_FLAGS = new Set(['headed', 'headless', 'no-tabs']);

function parseArgs(argv, defaults = {}) {
  const out = { _: [], ...defaults };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (!a.startsWith('--')) { out._.push(a); continue; }
    const key = a.slice(2);
    const next = argv[i + 1];
    if (next === undefined || next.startsWith('--') || BOOL_FLAGS.has(key)) out[key] = true;
    else { out[key] = next; i++; }
  }
  return out;
}

// Guard cannot decide (no rules file, broken file, Python bridge failed): exit code 4, the caller stops.
class GuardUnavailableError extends Error {
  constructor(reason, extra = {}) {
    super('guard недоступен — СТОП, переход/действие не выполнено: ' + reason);
    this.name = 'GuardUnavailableError';
    this.exitCode = 4;
    this.decision = { decision: 'unavailable', rule: 'guard:unavailable', reason, ...extra };
  }
}

// rules.json — вывод `url_guard.py export --config run-config.yaml --out rules.json`.
// Fail closed: a path that is given but missing or broken is an error (code 4), never «no rules».
function loadRules(file) {
  if (!file) return null;
  if (file === true) throw new GuardUnavailableError('--rules без пути к rules.json');
  let rules;
  try { rules = JSON.parse(fs.readFileSync(file, 'utf8')); }
  catch (e) { throw new GuardUnavailableError(`rules.json не прочитан (${file}): ${e.code || e.message}`); }
  if (!rules || typeof rules !== 'object' || !rules.rules || !rules.base)
    throw new GuardUnavailableError(`rules.json не похож на вывод url_guard.py export: ${file}`);
  return rules;
}

function hostMatches(host, pattern) {
  host = host.toLowerCase(); pattern = pattern.toLowerCase();
  if (pattern.includes('/')) return false;
  if (pattern.startsWith('*.')) return host === pattern.slice(2) || host.endsWith(pattern.slice(1));
  const rx = new RegExp('^' + pattern.replace(/[.+^${}()|[\]\\]/g, '\\$&').replace(/\*/g, '.*').replace(/\?/g, '.') + '$');
  return rx.test(host);
}

function globRx(pattern) {
  return new RegExp('^' + pattern.toLowerCase().replace(/[.+^${}()|[\]\\]/g, '\\$&').replace(/\*/g, '.*').replace(/\?/g, '.') + '$');
}

// Mirror of url_guard.hostpath_matches: patterns with "/" are matched against host+path.
function hostpathMatches(host, pathname, pattern) {
  if (!pattern.includes('/')) return hostMatches(host, pattern);
  return globRx(pattern).test((host + pathname).toLowerCase());
}

// ---- Local files (file://): mirror of url_guard.file_verdict (references/local-files.md) ----------------------
// rules.rules.local_roots = [{ path, real }] from `url_guard.py export`. Allowed only inside a root, never through
// a symlink below the root; `..` is already resolved by the URL parser, so the prefix check catches the escape.
const normCase = process.platform === 'win32' ? (s) => s.toLowerCase() : (s) => s;  // = Python os.path.normcase

// Like Python os.path.realpath (non-strict): resolve the existing prefix, keep the missing rest as is.
function realpathLoose(p) {
  let cur = p; const rest = [];
  for (;;) {
    try { const r = fs.realpathSync(cur); return rest.length ? path.join(r, ...rest.reverse()) : r; }
    catch {
      const parent = path.dirname(cur);
      if (parent === cur) return p;
      rest.push(path.basename(cur)); cur = parent;
    }
  }
}

function under(p, base) {
  const pc = normCase(p), bc = normCase(base);
  return pc === bc || pc.startsWith(bc.replace(/[\\/]+$/, '') + path.sep);
}

function fileCheck(url, rules) {
  let u;
  try { u = new URL(url); } catch { return { ok: false, reason: 'некорректный URL', rule: 'base:file-path' }; }
  if (u.hostname && u.hostname !== 'localhost') return { ok: false, reason: `file:// с хостом «${u.hostname}» — сетевой путь`, rule: 'base:file-path' };
  let p;
  try { p = path.normalize(require('url').fileURLToPath(u)); } catch (e) { return { ok: false, reason: 'file: ' + e.message, rule: 'base:file-path' }; }
  if (p.includes('\0')) return { ok: false, reason: 'file: NUL в пути', rule: 'base:file-path' };
  const roots = (rules && rules.rules && rules.rules.local_roots) || [];
  if (!roots.length) return { ok: false, reason: 'file:// не разрешён: нет site.local_roots', rule: 'base:file-no-roots' };
  for (const r of roots) {
    for (const base of [r.path, r.real].filter(Boolean)) {
      if (!under(p, base)) continue;
      const rel = path.relative(base, p);
      const expected = path.normalize(path.join(r.real || r.path, rel));
      const real = realpathLoose(p);
      if (normCase(real) !== normCase(expected)) return { ok: false, reason: `симлинк внутри каталога (${p} -> ${real})`, rule: 'base:file-symlink' };
      if (!fs.existsSync(r.path) && !fs.existsSync(r.real || r.path)) return { ok: false, reason: `каталог local_roots не найден: ${r.path}`, rule: 'base:file-root-missing' };
      return { ok: true, rel: '/' + rel.split(path.sep).join('/') };
    }
  }
  return { ok: false, reason: 'локальный файл вне local_roots', rule: 'base:file-outside-roots' };
}

// Упрощённое зеркало url_guard.check_url для краулинга и route-обработчиков. Окончательное решение — url_guard.py.
// kind: 'nav' (main-frame navigation) | 'subframe' (iframe document: only explicit bans, external is allowed;
// a local file:// frame must still be inside local_roots).
// opts.readOnly (main-frame nav only) mirrors `url_guard.py nav --read-only`: the purchase/donate part of the base
// path ban and user URL bans matching rules.read_only_urls are lifted; OAuth, logout, hosts — never.
function navAllowed(url, rules, kind = 'nav', opts = {}) {
  let u;
  try { u = new URL(url); } catch { return { ok: false, reason: 'некорректный URL' }; }
  if (/^(about|data|blob):$/.test(u.protocol)) return { ok: true };
  const local = u.protocol === 'file:';
  if (!local && !/^https?:$/.test(u.protocol)) return { ok: false, reason: `схема ${u.protocol}` };
  if (!rules) return { ok: true };
  const r = rules.rules, b = rules.base;
  const ro = !!opts.readOnly && kind === 'nav';
  const lifted = [];
  let pathname = u.pathname;
  if (local) {
    const fc = fileCheck(url, rules);
    if (!fc.ok) return fc;
    pathname = fc.rel;  // path rules apply to the path FROM the root folder
  } else {
    for (const p of r.forbidden_domains || []) if (hostpathMatches(u.hostname, u.pathname, p)) return { ok: false, reason: `forbidden_domains: ${p}`, rule: `user:forbidden_domains:${p}` };
    for (const p of b.deny_nav_hosts || []) if (hostpathMatches(u.hostname, u.pathname, p)) return { ok: false, reason: `base:nav-host ${p}`, rule: 'base:nav-host' };
  }
  const pq = pathname + u.search;
  if (new RegExp(b.deny_path_regex, 'i').test(pq)) {
    if (ro && b.read_only_path_regex && new RegExp(b.read_only_path_regex, 'i').test(pq) &&
        !new RegExp(b.never_read_only_path_regex || '$^', 'i').test(pq)) lifted.push('base:nav-path');
    else return { ok: false, reason: 'base:nav-path', rule: 'base:nav-path' };
  }
  const roOk = ro && (r.read_only_urls || []).some(p => new RegExp(p, 'i').test(url));
  for (const p of r.forbidden_url_patterns || []) if (new RegExp(p, 'i').test(url)) {
    if (roOk) { lifted.push(`user:forbidden_url_patterns:${p}`); continue; }
    return { ok: false, reason: `forbidden_url_patterns: ${p}`, rule: `user:forbidden_url_patterns:${p}` };
  }
  if (kind === 'subframe') return { ok: true };
  for (const p of r.exclude_patterns || []) if (new RegExp(p, 'i').test(url)) {
    if (roOk) { lifted.push(`user:exclude_patterns:${p}`); continue; }
    return { ok: false, reason: `exclude_patterns: ${p}`, rule: `user:exclude_patterns:${p}` };
  }
  // fail closed like url_guard.py: without allowed_domains a main-frame navigation to a host is not allowed
  if (!local && !(r.allowed_domains || []).length)
    return { ok: false, reason: 'site.allowed_domains не задан', rule: 'base:no-allowlist', external: true };
  if (!local && !r.allowed_domains.some(p => hostMatches(u.hostname, p)))
    return { ok: false, reason: 'outside-allowlist', rule: 'base:outside-allowlist', external: true };
  return lifted.length ? { ok: true, readOnly: true, rule: 'read-only:' + lifted[0] } : { ok: true };
}

function resourceBlocked(url, rules) {
  if (!rules) return false;
  let u; try { u = new URL(url); } catch { return false; }
  if (u.protocol === 'file:') return !fileCheck(url, rules).ok;  // local resources: only inside local_roots
  if ((rules.rules.forbidden_domains || []).some(p => hostpathMatches(u.hostname, u.pathname, p))) return true;
  return (rules.base.blocked_origins || []).some(o => url.toLowerCase().startsWith(o + '/') || url.toLowerCase() === o);
}

// Kept for backward compatibility; the full implementation (tabs, blocked.jsonl, subframes) is guard.js.
async function guardContext(context, rules, log = []) {
  return require('./guard').guardContext(context, rules, { log });
}

const sleep = (ms) => new Promise(r => setTimeout(r, ms));

function writeOut(file, data) {
  const text = JSON.stringify(data, null, 2);
  if (file && file !== true) {
    fs.mkdirSync(path.dirname(path.resolve(file)), { recursive: true });
    fs.writeFileSync(file, text);
    console.error(`-> ${file}`);
  } else process.stdout.write(text + '\n');
}

// A URL as given, or a local path (an existing file or folder, ~ allowed) -> file:// URL (references/local-files.md).
function toUrl(s) {
  if (s === undefined || s === null || s === true) return s;
  s = String(s).trim();
  if (/^[a-z][a-z0-9+.-]*:/i.test(s) && !/^[a-z]:[\\/]/i.test(s)) return s;  // has a scheme (not a Windows drive)
  const p = path.resolve(s.replace(/^~(?=$|[\\/])/, require('os').homedir()));
  return fs.existsSync(p) ? require('url').pathToFileURL(p).href : s;
}

// Positional URLs + every --url (repeatable) + --urls-file; local paths become file:// URLs.
function urlsFromArgs(args, argv = process.argv.slice(2)) {
  let urls = [...args._, ...multiArg(argv, 'url')];
  if (args['urls-file']) urls = urls.concat(fs.readFileSync(args['urls-file'], 'utf8').split(/\r?\n/).map(s => s.trim()).filter(Boolean));
  if (!urls.length) { console.error('нужен хотя бы один URL (позиционно или --url; file:///… и путь к файлу — тоже)'); process.exit(1); }
  return [...new Set(urls.map(toUrl))];
}

// run-config.yaml -> object via the vendored miniyaml (Python stdlib only). JSON files are read directly.
function loadRunConfig(file) {
  if (!file) return {};
  if (/\.json$/i.test(file)) return JSON.parse(fs.readFileSync(file, 'utf8'));
  const { execFileSync } = require('child_process');
  const py = process.env.SITE_QA_PYTHON || (process.platform === 'win32' ? 'python' : 'python3');
  const out = execFileSync(py, [path.join(__dirname, '..', 'shared', 'miniyaml.py'), file], { encoding: 'utf8' });
  return JSON.parse(out || '{}') || {};
}

// Repeated CLI flags (--target a --target b) -> array; parseArgs keeps only the last value.
function multiArg(argv, name) {
  const out = [];
  for (let i = 0; i < argv.length; i++) if (argv[i] === '--' + name && argv[i + 1] !== undefined) out.push(argv[++i]);
  return out;
}

function appendJsonl(file, obj) {
  if (!file) return;
  fs.mkdirSync(path.dirname(path.resolve(file)), { recursive: true });
  fs.appendFileSync(file, JSON.stringify({ ts: new Date().toISOString(), ...obj }) + '\n');
}

// Browser window of the scripts (references/devices-auth.md → «Окно браузера»). First that is set wins:
//   1. the script itself (extra.headless, e.g. guard.js check, device_context media — always hidden);
//   2. command line of any browser script: --headless / --headed, --slowmo <ms>;
//   3. run-config.yaml → browser.headed / browser.slowmo (exported to rules.json → browser): the ONE place to switch
//      the window for the whole run, also in the middle of it (browser_mode.py set <RUN_DIR> --headed);
//   4. environment: SITE_QA_HEADLESS=1 hides, SITE_QA_SLOWMO=<ms>;
//   5. default: a VISIBLE window, slow-mo 250 ms.
function browserMode(rules, extra = {}, argv = process.argv.slice(2)) {
  const b = (rules && rules.browser) || {};
  const env = process.env;
  let headless, source;
  if (extra.headless !== undefined) { headless = !!extra.headless; source = 'script'; }
  else if (argv.includes('--headless')) { headless = true; source = 'cli'; }
  else if (argv.includes('--headed')) { headless = false; source = 'cli'; }
  else if (typeof b.headed === 'boolean') { headless = !b.headed; source = 'run-config'; }
  else if (env.SITE_QA_HEADLESS !== undefined && env.SITE_QA_HEADLESS !== '') { headless = env.SITE_QA_HEADLESS === '1'; source = 'env'; }
  else { headless = false; source = 'default'; }
  const i = argv.indexOf('--slowmo');
  const raw = i >= 0 && argv[i + 1] !== undefined ? argv[i + 1]
    : (b.slowmo !== undefined && b.slowmo !== null ? b.slowmo : (env.SITE_QA_SLOWMO || 250));
  const slowMo = headless ? 0 : Math.max(0, Number(raw) || 0);
  return { headless, slowMo, source };
}

function launchOptions(extra = {}, rules = null) {
  const m = browserMode(rules, extra);
  const { headless: _h, ...rest } = extra;
  return { headless: m.headless, ...(m.headless ? {} : { slowMo: m.slowMo }), ...rest };
}

// ---- Tab registry of the run: <RUN_DIR>/tabs.json, the format and the lock file of scripts/tabs.py (#9) ----------
// RUN_DIR — the first that is set: --run-dir DIR, SITE_QA_RUN_DIR, the folder of --rules when run-config.yaml lies next
// to it (<RUN_DIR>/rules.json). None — nothing is registered (as before 1.5.0). Off: --no-tabs or SITE_QA_TABS=0.
// Owner: --owner <qa-id>, SITE_QA_OWNER, else "node". Records of a script: tool "node" — a page of the script's own
// browser (pid, script); tool "cdp" — a page it created in the user's browser (target id). A script changes ONLY its
// own records (same pid); on exit its open "node" records are closed (the browser dies with the process), a "cdp" page
// it could not close stays open for `tabs.py cleanup <RUN_DIR> --cdp URL --yes`. Registry errors never stop a check.
const TAB_LOCK_STALE_MS = 60000, TAB_LOCK_WAIT_MS = 10000;
const tabNow = () => new Date().toISOString().replace(/\.\d{3}Z$/, 'Z');  // = tabs.py now()
const sleepSync = (ms) => Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, ms);

// fn(data) under <file>.lock (O_EXCL, stale after 60 s — like tabs.py Lock); returns false -> nothing is written.
function withTabsFile(file, fn) {
  const lock = file + '.lock';
  const deadline = Date.now() + TAB_LOCK_WAIT_MS;
  let fd;
  for (;;) {
    try { fd = fs.openSync(lock, 'wx'); break; } catch (e) {
      if (e.code !== 'EEXIST') throw e;
      try { if (Date.now() - fs.statSync(lock).mtimeMs > TAB_LOCK_STALE_MS) { fs.rmSync(lock, { force: true }); continue; } } catch { /* released */ }
      if (Date.now() > deadline) throw new Error(`файл занят (${lock})`);
      sleepSync(50);
    }
  }
  try {
    const data = fs.existsSync(file) ? JSON.parse(fs.readFileSync(file, 'utf8')) : { tabs: [] };
    if (!Array.isArray(data.tabs)) data.tabs = [];
    const res = fn(data);
    if (res !== false) {
      const tmp = file + '.tmp';
      fs.writeFileSync(tmp, JSON.stringify(data, null, 1));
      fs.renameSync(tmp, file);
    }
    return res;
  } finally { fs.closeSync(fd); fs.rmSync(lock, { force: true }); }
}

function flagValue(argv, name) {
  const i = argv.lastIndexOf('--' + name);
  return i >= 0 && argv[i + 1] !== undefined && !argv[i + 1].startsWith('--') ? argv[i + 1] : null;
}

function tabsConfig(argv = process.argv.slice(2), env = process.env) {
  if (argv.includes('--no-tabs') || env.SITE_QA_TABS === '0') return null;
  let runDir = flagValue(argv, 'run-dir') || env.SITE_QA_RUN_DIR || null;
  if (!runDir) {
    const r = flagValue(argv, 'rules');
    if (r && fs.existsSync(path.join(path.dirname(path.resolve(r)), 'run-config.yaml'))) runDir = path.dirname(path.resolve(r));
  }
  if (!runDir) return null;
  if (!fs.existsSync(runDir)) { process.stderr.write(`tabs.json: папки прогона нет (${runDir}) — вкладки не регистрируются\n`); return null; }
  return { runDir: path.resolve(runDir), owner: flagValue(argv, 'owner') || env.SITE_QA_OWNER || 'node' };
}

class TabRegistry {
  constructor({ runDir, owner, script }) {
    this.runDir = runDir; this.file = path.join(runDir, 'tabs.json'); this.owner = owner; this.script = script;
    this.mine = new Map();  // id -> tool, only records of this process
    this.warned = false; this.hooked = false;
  }
  _safe(fn) {
    try { return fn(); } catch (e) {
      if (!this.warned) { this.warned = true; process.stderr.write(`tabs.json: реестр вкладок не обновлён — ${e.message || e}\n`); }
      return null;
    }
  }
  _own(data, id) { return data.tabs.find(t => t.id === id && t.pid === process.pid && t.owner === this.owner); }
  open({ profile = 'desktop', tool = 'node', url = null, targetId = null, engine = null } = {}) {
    const id = this._safe(() => withTabsFile(this.file, (data) => {
      const tid = `T-${String(data.tabs.length + 1).padStart(3, '0')}`;
      data.tabs.push({ id: tid, owner: this.owner, profile, tool, session: `${this.script}:${process.pid}`, url, target_id: targetId,
        window_name: `${this.owner}-${profile}`, opened_at: tabNow(), closed_at: null, pid: process.pid, script: this.script,
        ...(engine ? { engine } : {}) });
      return tid;
    }));
    if (id) { this.mine.set(id, tool); this._hook(); }
    return id;
  }
  update(id, fields) {
    if (!id || !this.mine.has(id)) return;
    this._safe(() => withTabsFile(this.file, (data) => { const t = this._own(data, id); if (!t) return false; Object.assign(t, fields); }));
  }
  close(id, fields = {}) {
    if (!id || !this.mine.has(id)) return;
    this.mine.delete(id);
    this._safe(() => withTabsFile(this.file, (data) => {
      const t = this._own(data, id);
      if (!t || t.closed_at) return false;
      Object.assign(t, fields, { closed_at: tabNow() });
    }));
  }
  // Before the script ends: its own browser pages are closed with the process; CDP pages that are still registered
  // were not closed by the script — they stay open in the registry, with the command to close them.
  cleanup() {
    const left = [...this.mine].filter(([, tool]) => tool === 'cdp').map(([id]) => id);
    for (const [id, tool] of [...this.mine]) if (tool !== 'cdp') this.close(id);
    if (left.length) process.stderr.write(`tabs.json: в браузере пользователя осталась вкладка скрипта ${left.join(', ')} — ` +
      `python3 <SKILL_DIR>/scripts/tabs.py cleanup ${this.runDir} --cdp <URL> --yes\n`);
    return left;
  }
  _hook() {
    if (this.hooked) return;
    this.hooked = true;
    process.once('exit', () => this.cleanup());
  }
}

let tabRegistry;
// The registry of this process (null when RUN_DIR is unknown or registration is off).
function tabs() {
  if (tabRegistry === undefined) {
    const c = tabsConfig();
    tabRegistry = c ? new TabRegistry({ ...c, script: path.basename(process.argv[1] || 'node') }) : null;
  }
  return tabRegistry;
}

const realUrl = (u) => (u && !/^(about|data|blob|chrome-error):/i.test(u) ? u : null);

// Register a page the script opened: url = first real address (updated once), last address on close.
// tool "node": closed in the registry when the page closes; tool "cdp": only after closeTab() (the page in the user's
// browser also "closes" for Playwright on disconnect, while the tab is still there).
function trackPage(page, { profile = 'desktop', tool = 'node', targetId = null, engine = null } = {}) {
  const reg = tabs();
  if (!reg || !page) return null;
  let last = realUrl(page.url());
  const id = reg.open({ profile, tool, targetId, engine, url: last });
  if (!id) return null;
  let named = !!last;
  page.on('framenavigated', (frame) => {
    if (frame !== page.mainFrame()) return;
    const u = realUrl(frame.url());
    if (!u) return;
    last = u;
    if (!named) { named = true; reg.update(id, { url: u }); }
  });
  if (tool !== 'cdp') page.once('close', () => reg.close(id, last ? { url: last } : {}));
  page.__qaTabId = id;
  return id;
}

function closeTab(id, fields = {}) {
  const reg = tabs();
  if (reg && id) reg.close(id, fields);
}

module.exports = { GuardUnavailableError, launchOptions, browserMode, parseArgs, loadRules, navAllowed, resourceBlocked, guardContext, hostMatches, hostpathMatches, sleep, writeOut,
  urlsFromArgs, toUrl, fileCheck, realpathLoose, loadRunConfig, multiArg, appendJsonl,
  tabs, tabsConfig, trackPage, closeTab, TabRegistry, withTabsFile };
