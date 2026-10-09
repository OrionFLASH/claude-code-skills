'use strict';
// Обход сайта в пределах allowed_domains (статический HTML, без JS) и проверка ссылок.
// Собирает карту страниц, битые ссылки (4xx/5xx), SEO-мета (title, description, canonical, OG, hreflang, h1, lang).
// Внешние ссылки проверяются только HEAD/GET-статусом, на них не переходим.
// node links.js START_URL [--rules rules.json] [--max-pages 50] [--check-external] [--throttle 700] [--out links.json]
//      [--frames all]  documents of <iframe src> within allowed_domains are crawled too (marked frameOf)
//      START_URL may be file:///… or a local path (references/local-files.md): local pages inside site.local_roots
//      (without --rules: the folder of the start file) are read from disk; a missing local file is a broken link (404).
const fs = require('fs');
const path = require('path');
const { fileURLToPath } = require('url');
const { parseArgs, loadRules, navAllowed, sleep, writeOut, toUrl, realpathLoose } = require('./lib');

const UA = 'Mozilla/5.0 site-qa-audit (passive crawl)';
const attr = (tag, name) => { const m = tag.match(new RegExp(`\\b${name}\\s*=\\s*["']([^"']*)["']`, 'i')); return m ? m[1] : null; };

function meta(html) {
  const metas = [...html.matchAll(/<meta\b[^>]*>/gi)].map(m => m[0]);
  const byName = n => { const t = metas.find(x => (attr(x, 'name') || attr(x, 'property') || '').toLowerCase() === n); return t ? attr(t, 'content') : null; };
  const links = [...html.matchAll(/<link\b[^>]*>/gi)].map(m => m[0]);
  const title = (html.match(/<title[^>]*>([\s\S]*?)<\/title>/i) || [])[1];
  return {
    lang: (html.match(/<html[^>]*\blang=["']([^"']+)/i) || [])[1] || null,
    title: title ? title.replace(/\s+/g, ' ').trim() : null,
    description: byName('description'), robots: byName('robots'), viewport: byName('viewport'),
    canonical: (links.find(l => /rel=["']canonical/i.test(l)) && attr(links.find(l => /rel=["']canonical/i.test(l)), 'href')) || null,
    og: { title: byName('og:title'), description: byName('og:description'), image: byName('og:image'), url: byName('og:url'), type: byName('og:type') },
    twitter: byName('twitter:card'),
    hreflang: links.filter(l => /hreflang=/i.test(l)).map(l => ({ lang: attr(l, 'hreflang'), href: attr(l, 'href') })),
    h1: [...html.matchAll(/<h1[^>]*>([\s\S]*?)<\/h1>/gi)].map(m => m[1].replace(/<[^>]+>/g, '').trim()),
    imgNoAlt: [...html.matchAll(/<img\b[^>]*>/gi)].filter(m => attr(m[0], 'alt') === null).length,
    jsonLd: (html.match(/application\/ld\+json/gi) || []).length,
  };
}

const LINKABLE = /^(https?|file):/;
const HTML_EXT = /\.(x?html?)$/i;

// Local page (file://) from disk: status 200 / 404 like a server would answer; directories have no HTML to parse.
function loadLocal(url) {
  let p;
  try { p = fileURLToPath(new URL(url)); } catch (e) { return { status: 0, finalUrl: url, html: '', error: e.message }; }
  try {
    const st = fs.statSync(p);
    if (st.isDirectory()) return { status: 200, finalUrl: url, html: '', note: 'каталог' };
    return { status: 200, finalUrl: url, html: HTML_EXT.test(p) ? fs.readFileSync(p, 'utf8') : '' };
  } catch (e) { return { status: 404, finalUrl: url, html: '', error: e.code || e.message }; }
}

function implicitRules(start) {
  const base = { deny_nav_hosts: [], deny_path_regex: '(?!)', blocked_origins: [] };
  const empty = { forbidden_domains: [], forbidden_url_patterns: [], exclude_patterns: [] };
  const u = new URL(start);
  if (u.protocol === 'file:') {
    let p = fileURLToPath(u);
    if (!fs.existsSync(p) || fs.statSync(p).isFile()) p = path.dirname(p);
    return { rules: { ...empty, allowed_domains: [], local_roots: [{ path: p, real: realpathLoose(p) }] }, base };
  }
  return { rules: { ...empty, allowed_domains: [u.hostname] }, base };
}

async function fetchStatus(url) {
  try {
    let r = await fetch(url, { method: 'HEAD', redirect: 'follow', headers: { 'user-agent': UA } });
    if (r.status === 405 || r.status === 403 || r.status === 501) r = await fetch(url, { method: 'GET', redirect: 'follow', headers: { 'user-agent': UA } });
    return { status: r.status, finalUrl: r.url };
  } catch (e) { return { status: 0, error: String(e.cause && e.cause.code || e.message || e) }; }
}

(async () => {
  const args = parseArgs(process.argv.slice(2), { 'max-pages': '50', throttle: '700' });
  const start = toUrl(args._[0] || args.url);
  if (!start || start === true) { console.error('нужен START_URL (http(s), file:///… или путь к файлу)'); process.exit(1); }
  const rules = loadRules(args.rules) || implicitRules(start);
  const startCheck = navAllowed(start, rules);
  if (!startCheck.ok) { writeOut(args.out, { tool: 'links', start, crawled: 0, blocked: startCheck }); return; }
  const frameOf = new Map();
  const queue = [start], seen = new Set([start.split('#')[0]]), pages = [], linkSources = new Map(), external = new Map(), skipped = [];
  while (queue.length && pages.length < +args['max-pages']) {
    const url = queue.shift();
    let res, html = '';
    const t0 = Date.now();
    try {
      if (/^file:/i.test(url)) {
        const l = loadLocal(url);
        res = { status: l.status, url: l.finalUrl, local: true, error: l.error };
        html = l.html;
      } else {
        res = await fetch(url, { redirect: 'follow', headers: { 'user-agent': UA } });
        if (/text\/html/.test(res.headers.get('content-type') || '')) html = await res.text();
      }
    } catch (e) { pages.push({ url, status: 0, error: String(e.cause && e.cause.code || e.message || e) }); continue; }
    const page = { url, status: res.status, finalUrl: res.url, timeMs: Date.now() - t0, meta: html ? meta(html) : null, links: 0,
      ...(res.local ? { local: true } : {}), ...(res.error ? { error: res.error } : {}) };
    pages.push(page);
    if (args.frames === 'all') {
      page.frames = [];
      for (const m of html.matchAll(/<iframe\b[^>]*\bsrc\s*=\s*["']([^"']+)["']/gi)) {
        let src; try { src = new URL(m[1], res.url).href; } catch { continue; }
        if (!LINKABLE.test(src)) continue;
        page.frames.push(src);
        const v = navAllowed(src, rules, 'subframe');
        const inside = v.ok && navAllowed(src, rules).ok;
        if (inside && !seen.has(src)) { seen.add(src); queue.unshift(src); frameOf.set(src, url); }
      }
    }
    if (frameOf.has(url)) page.frameOf = frameOf.get(url);
    for (const m of html.matchAll(/<a\b[^>]*\bhref\s*=\s*["']([^"']+)["']/gi)) {
      let href;
      try { href = new URL(m[1], res.url).href.split('#')[0]; } catch { continue; }
      if (!LINKABLE.test(href)) continue;
      page.links++;
      if (!linkSources.has(href)) linkSources.set(href, new Set());
      linkSources.get(href).add(url);
      const v = navAllowed(href, rules);
      if (v.ok) { if (!seen.has(href)) { seen.add(href); queue.push(href); } }
      else if (v.external) external.set(href, url);
      else skipped.push({ url: href, from: url, reason: v.reason });
    }
    if (!res.local) await sleep(+args.throttle);
  }
  // Статус внутренних ссылок, которые не попали в обход из-за лимита
  const broken = [];
  for (const p of pages) if (p.status >= 400 || p.status === 0) broken.push({ url: p.url, status: p.status, from: [...(linkSources.get(p.url) || [])].slice(0, 5) });
  const unvisited = queue.slice(0, 100);
  const externalChecked = [];
  if (args['check-external']) {
    for (const [href, from] of [...external].slice(0, 150)) {
      const s = await fetchStatus(href);
      externalChecked.push({ url: href, from, ...s });
      if (s.status >= 400 || s.status === 0) broken.push({ url: href, status: s.status, external: true, from: [from], error: s.error });
      await sleep(300);
    }
  }
  // SEO-сводка: дубли title/description, пустые поля
  const dup = (key) => { const m = new Map(); pages.filter(p => p.meta && p.meta[key]).forEach(p => m.set(p.meta[key], [...(m.get(p.meta[key]) || []), p.url])); return [...m].filter(([, v]) => v.length > 1).map(([k, v]) => ({ value: k, urls: v })); };
  const seo = {
    missingTitle: pages.filter(p => p.meta && !p.meta.title).map(p => p.url),
    missingDescription: pages.filter(p => p.meta && !p.meta.description).map(p => p.url),
    missingCanonical: pages.filter(p => p.meta && !p.meta.canonical).map(p => p.url),
    missingLang: pages.filter(p => p.meta && !p.meta.lang).map(p => p.url),
    h1Problems: pages.filter(p => p.meta && p.meta.h1.length !== 1).map(p => ({ url: p.url, h1: p.meta.h1.length })),
    duplicateTitles: dup('title'), duplicateDescriptions: dup('description'),
  };
  writeOut(args.out, { tool: 'links', start, crawled: pages.length, pages, broken, seo, external: [...external.keys()],
    externalChecked, skipped, unvisited, note: 'Статический обход без JS: для SPA карту дополняет разведка в браузере' +
      (/^file:/i.test(start) ? '; file://: страницы прочитаны с диска, SEO-поля (canonical, description) для локального приложения обычно не важны' : '') });
})().catch(e => { console.error(e); process.exit((e && e.exitCode) || 1); });
