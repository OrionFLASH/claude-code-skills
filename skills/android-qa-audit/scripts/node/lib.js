'use strict';
// Общие утилиты node-скриптов site-qa-audit: аргументы, правила url_guard, троттлинг, вывод JSON.
const fs = require('fs');
const path = require('path');

function parseArgs(argv, defaults = {}) {
  const out = { _: [], ...defaults };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (!a.startsWith('--')) { out._.push(a); continue; }
    const key = a.slice(2);
    const next = argv[i + 1];
    if (next === undefined || next.startsWith('--')) out[key] = true;
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

// Упрощённое зеркало url_guard.check_url для краулинга и route-обработчиков. Окончательное решение — url_guard.py.
// kind: 'nav' (main-frame navigation) | 'subframe' (iframe document: only explicit bans, external is allowed).
// opts.readOnly (main-frame nav only) mirrors `url_guard.py nav --read-only`: the purchase/donate part of the base
// path ban and user URL bans matching rules.read_only_urls are lifted; OAuth, logout, hosts — never.
function navAllowed(url, rules, kind = 'nav', opts = {}) {
  let u;
  try { u = new URL(url); } catch { return { ok: false, reason: 'некорректный URL' }; }
  if (/^(about|data|blob):$/.test(u.protocol)) return { ok: true };
  if (!/^https?:$/.test(u.protocol)) return { ok: false, reason: `схема ${u.protocol}` };
  if (!rules) return { ok: true };
  const r = rules.rules, b = rules.base;
  const ro = !!opts.readOnly && kind === 'nav';
  const lifted = [];
  for (const p of r.forbidden_domains || []) if (hostpathMatches(u.hostname, u.pathname, p)) return { ok: false, reason: `forbidden_domains: ${p}`, rule: `user:forbidden_domains:${p}` };
  for (const p of b.deny_nav_hosts || []) if (hostpathMatches(u.hostname, u.pathname, p)) return { ok: false, reason: `base:nav-host ${p}`, rule: 'base:nav-host' };
  const pq = u.pathname + u.search;
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
  if ((r.allowed_domains || []).length && !r.allowed_domains.some(p => hostMatches(u.hostname, p)))
    return { ok: false, reason: 'outside-allowlist', rule: 'base:outside-allowlist', external: true };
  return lifted.length ? { ok: true, readOnly: true, rule: 'read-only:' + lifted[0] } : { ok: true };
}

function resourceBlocked(url, rules) {
  if (!rules) return false;
  let u; try { u = new URL(url); } catch { return false; }
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

function urlsFromArgs(args) {
  let urls = [...args._];
  if (args['urls-file']) urls = urls.concat(fs.readFileSync(args['urls-file'], 'utf8').split(/\r?\n/).map(s => s.trim()).filter(Boolean));
  if (!urls.length) { console.error('нужен хотя бы один URL'); process.exit(1); }
  return urls;
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

// Browser launch options shared by all scripts: a VISIBLE window by default (user requirement);
// SITE_QA_HEADLESS=1 hides it, SITE_QA_SLOWMO=<ms> slows visible actions down (default 250).
function launchOptions(extra = {}) {
  const headless = extra.headless !== undefined ? !!extra.headless : process.env.SITE_QA_HEADLESS === '1';
  const { headless: _h, ...rest } = extra;
  return { headless, ...(headless ? {} : { slowMo: Number(process.env.SITE_QA_SLOWMO || 250) }), ...rest };
}

module.exports = { GuardUnavailableError, launchOptions, parseArgs, loadRules, navAllowed, resourceBlocked, guardContext, hostMatches, hostpathMatches, sleep, writeOut,
  urlsFromArgs, loadRunConfig, multiArg, appendJsonl };
