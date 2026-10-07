// Замок навигации для Playwright MCP (browser_run_code_unsafe). См. references/safety-rules.md §3.11.
// Применять, когда охват — «только эти страницы» (scope.type url-list/current-screen) или запрет «никуда не переходить».
// Перед передачей в MCP заменить __ALLOWED_RE__ на регэксп разрешённых URL документа (якоря #… допустимы), например:
//   ^https://example\.com/?(#.*)?$
// Что делает:
//   1) обрывает навигацию главного фрейма на любой URL вне регэкспа (клик по ссылке, redirect, location=…);
//   2) блокирует history.pushState/replaceState на неразрешённый адрес (SPA-роутеры) и window.open;
//   3) пишет попытки в window.__qaNavAttempts и console.warn('[qa-lock] …') — их нужно перенести в отчёт.
// Ограничение: блокировка pushState может оставить состояние приложения «как будто перешли» без смены URL —
// поведение после такого клика проверять, но не считать дефектом сайта.
async (page) => {
  const ALLOWED = new RegExp(String.raw`__ALLOWED_RE__`);
  await page.route('**/*', (route) => {
    const req = route.request();
    if (req.isNavigationRequest() && req.frame() === page.mainFrame() && !ALLOWED.test(req.url())) {
      return route.abort('blockedbyclient');
    }
    return route.continue();
  });
  const lock = (src) => {
    const allowed = new RegExp(src);
    const ok = (u) => { try { return allowed.test(new URL(u, location.href).href); } catch { return false; } };
    window.__qaNavAttempts = window.__qaNavAttempts || [];
    for (const m of ['pushState', 'replaceState']) {
      const orig = history[m].bind(history);
      history[m] = (s, t, u) => {
        if (u != null && !ok(u)) { window.__qaNavAttempts.push({ m, u: String(u) }); console.warn('[qa-lock] blocked ' + m + ' ' + u); return; }
        return orig(s, t, u);
      };
    }
    window.open = (u) => { window.__qaNavAttempts.push({ m: 'open', u: String(u) }); console.warn('[qa-lock] blocked window.open ' + u); return null; };
  };
  await page.addInitScript(lock, ALLOWED.source);
  await page.evaluate(lock, ALLOWED.source);
  return 'navigation lock on: ' + ALLOWED.source;
}
