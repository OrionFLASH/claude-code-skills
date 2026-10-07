'use strict';
// Обход сайта в пределах allowed_domains (статический HTML, без JS) и проверка ссылок.
// Собирает карту страниц, битые ссылки (4xx/5xx), SEO-мета (title, description, canonical, OG, hreflang, h1, lang).
// Внешние ссылки проверяются только HEAD/GET-статусом, на них не переходим.
// node links.js START_URL [--rules rules.json] [--max-pages 50] [--check-external] [--throttle 700] [--out links.json]
const { parseArgs, loadRules, navAllowed, sleep, writeOut } = require('./lib');

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

async function fetchStatus(url) {
  try {
    let r = await fetch(url, { method: 'HEAD', redirect: 'follow', headers: { 'user-agent': UA } });
    if (r.status === 405 || r.status === 403 || r.status === 501) r = await fetch(url, { method: 'GET', redirect: 'follow', headers: { 'user-agent': UA } });
    return { status: r.status, finalUrl: r.url };
  } catch (e) { return { status: 0, error: String(e.cause && e.cause.code || e.message || e) }; }
}

(async () => {
  const args = parseArgs(process.argv.slice(2), { 'max-pages': '50', throttle: '700' });
  const start = args._[0];
  if (!start) { console.error('нужен START_URL'); process.exit(1); }
  const rules = loadRules(args.rules) || { rules: { allowed_domains: [new URL(start).hostname], forbidden_domains: [], forbidden_url_patterns: [], exclude_patterns: [] },
    base: { deny_nav_hosts: [], deny_path_regex: '(?!)', blocked_origins: [] } };
  const queue = [start], seen = new Set([start.split('#')[0]]), pages = [], linkSources = new Map(), external = new Map(), skipped = [];
  while (queue.length && pages.length < +args['max-pages']) {
    const url = queue.shift();
    let res, html = '';
    const t0 = Date.now();
    try {
      res = await fetch(url, { redirect: 'follow', headers: { 'user-agent': UA } });
      if (/text\/html/.test(res.headers.get('content-type') || '')) html = await res.text();
    } catch (e) { pages.push({ url, status: 0, error: String(e.cause && e.cause.code || e.message || e) }); continue; }
    const page = { url, status: res.status, finalUrl: res.url, timeMs: Date.now() - t0, meta: html ? meta(html) : null, links: 0 };
    pages.push(page);
    for (const m of html.matchAll(/<a\b[^>]*\bhref\s*=\s*["']([^"']+)["']/gi)) {
      let href;
      try { href = new URL(m[1], res.url).href.split('#')[0]; } catch { continue; }
      if (!/^https?:/.test(href)) continue;
      page.links++;
      if (!linkSources.has(href)) linkSources.set(href, new Set());
      linkSources.get(href).add(url);
      const v = navAllowed(href, rules);
      if (v.ok) { if (!seen.has(href)) { seen.add(href); queue.push(href); } }
      else if (v.external) external.set(href, url);
      else skipped.push({ url: href, from: url, reason: v.reason });
    }
    await sleep(+args.throttle);
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
    externalChecked, skipped, unvisited, note: 'Статический обход без JS: для SPA карту дополняет разведка в браузере' });
})().catch(e => { console.error(e); process.exit(1); });
