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

// rules.json — вывод `url_guard.py export --config run-config.yaml --out rules.json`.
function loadRules(file) {
  if (!file) return null;
  return JSON.parse(fs.readFileSync(file, 'utf8'));
}

function hostMatches(host, pattern) {
  host = host.toLowerCase(); pattern = pattern.toLowerCase();
  if (pattern.includes('/')) return false;
  if (pattern.startsWith('*.')) return host === pattern.slice(2) || host.endsWith(pattern.slice(1));
  const rx = new RegExp('^' + pattern.replace(/[.+^${}()|[\]\\]/g, '\\$&').replace(/\*/g, '.*').replace(/\?/g, '.') + '$');
  return rx.test(host);
}

// Упрощённое зеркало url_guard.check_url для краулинга. Окончательное решение — url_guard.py.
function navAllowed(url, rules) {
  let u;
  try { u = new URL(url); } catch { return { ok: false, reason: 'некорректный URL' }; }
  if (!/^https?:$/.test(u.protocol)) return { ok: false, reason: `схема ${u.protocol}` };
  if (!rules) return { ok: true };
  const r = rules.rules, b = rules.base;
  for (const p of r.forbidden_domains) if (hostMatches(u.hostname, p)) return { ok: false, reason: `forbidden_domains: ${p}` };
  for (const p of b.deny_nav_hosts) if (hostMatches(u.hostname, p)) return { ok: false, reason: `base:nav-host ${p}` };
  if (new RegExp(b.deny_path_regex, 'i').test(u.pathname + u.search)) return { ok: false, reason: 'base:nav-path' };
  for (const p of r.forbidden_url_patterns) if (new RegExp(p, 'i').test(url)) return { ok: false, reason: `forbidden_url_patterns: ${p}` };
  for (const p of r.exclude_patterns) if (new RegExp(p, 'i').test(url)) return { ok: false, reason: `exclude_patterns: ${p}` };
  if (r.allowed_domains.length && !r.allowed_domains.some(p => hostMatches(u.hostname, p)))
    return { ok: false, reason: 'outside-allowlist', external: true };
  return { ok: true };
}

function resourceBlocked(url, rules) {
  if (!rules) return false;
  let u; try { u = new URL(url); } catch { return false; }
  if (rules.rules.forbidden_domains.some(p => hostMatches(u.hostname, p))) return true;
  return rules.base.blocked_origins.some(o => url.toLowerCase().startsWith(o + '/'));
}

// Блокирует в контексте Playwright запросы к запрещённым доменам и навигацию за allowlist.
async function guardContext(context, rules, log = []) {
  if (!rules) return;
  await context.route('**/*', (route) => {
    const req = route.request();
    const url = req.url();
    if (resourceBlocked(url, rules)) { log.push({ blocked: url, reason: 'resource' }); return route.abort('blockedbyclient'); }
    if (req.isNavigationRequest() && req.frame() === req.frame().page().mainFrame()) {
      const v = navAllowed(url, rules);
      if (!v.ok) { log.push({ blocked: url, reason: v.reason }); return route.abort('blockedbyclient'); }
    }
    return route.continue();
  });
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

module.exports = { parseArgs, loadRules, navAllowed, resourceBlocked, guardContext, hostMatches, sleep, writeOut, urlsFromArgs };
