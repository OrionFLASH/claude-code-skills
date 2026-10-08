// Скриншот + координаты элементов для аннотации (Playwright MCP, browser_run_code_unsafe).
// Перед передачей заменить:
//   __OUT__     — АБСОЛЮТНЫЙ путь PNG в <RUN_DIR>/screenshots/ (без -annotated)
//   __TARGETS__ — JSON-массив целей: [{"selector": "css=…" | "role=button[name=\"…\"]" | "text=…", "label": "коротко, что не так",
//                 "kind": "error|question|note", "row": true}]
//                 row: true — обвести ближайший кликабельный контейнер (строку списка, карточку), а не только текст.
//                 Элемент внутри iframe: "iframe#app >>> button.save" (координаты кадра прибавляются автоматически).
// CDP/Playwright-версия (без MCP) — scripts/snap_cdp.js (= node/shot.js).
// Возвращает spec для node/annotate.js (scale=1, координаты в CSS px области просмотра).
// Агент сохраняет результат в <RUN_DIR>/screenshots/<имя>.spec.json и вызывает:
//   node <SKILL_DIR>/scripts/node/annotate.js --in <png> --spec <spec.json>
async (page) => {
  const targets = __TARGETS__;
  const items = [];
  const missing = [];
  for (const t of targets) {
    const parts = String(t.selector).split('>>>').map(s => s.trim()).filter(Boolean);
    let scope = page;
    for (const fr of parts.slice(0, -1)) scope = scope.frameLocator(fr);
    const loc = scope.locator(parts[parts.length - 1]).first();
    let box = (await loc.count()) ? await loc.boundingBox() : null;  // main-viewport coordinates, frames included
    if (box && t.row) {
      const own = await loc.evaluate((e) => { const r = e.getBoundingClientRect(); return { x: r.x, y: r.y }; });
      const dx = box.x - own.x, dy = box.y - own.y;  // frame offset
      box = await loc.evaluate((e) => {
        // cursor наследуется: берём самый верхний предок с pointer (или явный интерактивный элемент), не выше 200 px
        let n = e, best = null;
        while (n && n !== document.body) {
          const r = n.getBoundingClientRect();
          if (r.height > 200) break;
          if (n.matches('button, a, li, [role=option], [role=button], [role=menuitem]')) { best = n; break; }
          if (getComputedStyle(n).cursor === 'pointer') best = n; else if (best) break;
          n = n.parentElement;
        }
        const r = (best || e).getBoundingClientRect();
        return { x: r.x, y: r.y, width: r.width, height: r.height };
      });
      box = { ...box, x: box.x + dx, y: box.y + dy };
    }
    if (!box) { missing.push(t.selector); continue; }
    items.push({ box: [box.x, box.y, box.width, box.height].map(v => Math.round(v)), label: t.label, kind: t.kind || 'error', style: t.style || 'both' });
  }
  await page.screenshot({ path: '__OUT__', scale: 'css' });
  return JSON.stringify({ scale: 1, items, missing, viewport: page.viewportSize() });
}
