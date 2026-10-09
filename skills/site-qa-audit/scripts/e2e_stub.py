#!/usr/bin/env python3
"""Regression test stub (Playwright) from a finding: steps[] become comments, repro becomes the assertion.

  e2e_stub.py findings.json --id F-001 [--lang ts|js] [--out FILE]
  e2e_stub.py findings.json --all --run-dir DIR [--lang ts|js]       -> DIR/drafts/e2e/<id>.spec.ts|js
  --config run-config.yaml (default: next to findings.json) — local_roots for file:// URLs

What is generated (a STUB for the developer who fixes the issue, references/fix-cycle.md):
  - the page: BASE_URL from the environment (default — origin of the finding URL); a local app (file://) —
    APP_URL (folder of the app) + the path from the app folder, never the tester's absolute path;
  - device / size / locale of repro -> test.use(...);
  - steps[] -> numbered comments with TODO (actions are not guessed); expected / actual -> comments;
  - assertion: repro.js -> `expect(await page.evaluate(...)).toBe(false)` (the expression is «the defect is present»);
    repro.selector [+ assert over b = {x, y, w, h}] -> boundingBox check; «iframe#app >>> sel» -> frameLocator;
    no repro -> test.fixme with the expected result to turn into an assertion.
Run the finished test three times before handing it over: npx playwright test <file> --repeat-each=3.
Exit codes: 0 ok, 1 finding not found / bad input.
"""
import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import fingerprint  # noqa: E402 — local_rel / set_roots: file:// path from the app folder

DEVICES = {"pixel7": "Pixel 7", "pixel7-landscape": "Pixel 7 landscape", "iphone15": "iPhone 15",
           "iphone15-landscape": "iPhone 15 landscape", "ipad": "iPad (gen 7)", "ipad-landscape": "iPad (gen 7) landscape"}
SIZES = {"desktop": (1440, 900), "desktop-1280": (1280, 720), "laptop": (1024, 768), "low": (720, 450)}


def js_str(s):
    return json.dumps(str(s), ensure_ascii=False)


def comment(text, indent="  "):
    return "\n".join(f"{indent}// {line}" for line in str(text).splitlines() or [""])


def use_block(r):
    dev = r.get("device") or r.get("size")
    parts, imp_devices = [], False
    if dev in DEVICES or (dev and dev not in SIZES and not re.fullmatch(r"\d+x\d+(@mobile)?", dev)):
        parts.append(f"...devices[{js_str(DEVICES.get(dev, dev))}]")
        imp_devices = True
    elif dev:
        m = re.fullmatch(r"(\d+)x(\d+)(@mobile)?", dev)
        w, h = (int(m.group(1)), int(m.group(2))) if m else SIZES[dev]
        parts.append(f"viewport: {{ width: {w}, height: {h} }}")
        if m and m.group(3):
            parts.append("isMobile: true, hasTouch: true")
    if r.get("locale"):
        parts.append(f"locale: {js_str(r['locale'])}")
    return (f"test.use({{ {', '.join(parts)} }});\n" if parts else ""), imp_devices


def target(url):
    """-> (const declarations, expression for page.goto)."""
    u = urlsplit(url or "")
    if u.scheme == "file":
        rel = fingerprint.local_rel(url)
        tail = rel + (("?" + u.query) if u.query else "") + (("#" + u.fragment) if u.fragment else "")
        return ("// Локальное приложение (file://): APP_URL — file:// URL папки приложения у того, кто запускает тест\n"
                "const APP_URL = process.env.APP_URL ?? 'file:///path/to/app/';\n",
                f"new URL({js_str(tail)}, APP_URL.endsWith('/') ? APP_URL : APP_URL + '/').href")
    origin = f"{u.scheme}://{u.netloc}" if u.scheme and u.netloc else "https://example.com"
    path = (u.path or "/") + (("?" + u.query) if u.query else "") + (("#" + u.fragment) if u.fragment else "")
    return (f"const BASE_URL = process.env.BASE_URL ?? {js_str(origin)};\n", f"new URL({js_str(path)}, BASE_URL).href")


def locator(sel):
    """«iframe#app >>> button.save» -> page.frameLocator('iframe#app').locator('button.save')."""
    parts = [x.strip() for x in str(sel).split(">>>")]
    expr = "page"
    for fr in parts[:-1]:
        expr += f".frameLocator({js_str(fr)})"
    return expr + f".locator({js_str(parts[-1])}).first()"


def stub(f, lang="ts"):
    r = f.get("repro") or {}
    url = r.get("url") or f.get("url") or ""
    consts, goto = target(url)
    use, imp_devices = use_block(r)
    name = f"{f.get('id', 'F-???')}: {f.get('title', '')}"
    head = [f"// Регрессионный тест (заготовка site-qa-audit) — {f.get('id')} «{f.get('title')}» ({f.get('check_id')}).",
            "// Довести до рабочего: заменить TODO действиями, проверить селекторы, убедиться, что тест ПАДАЕТ до",
            "// исправления и проходит после; прогнать три раза подряд: npx playwright test <файл> --repeat-each=3",
            "// Ждать состояния (toBeVisible, waitForFunction), а не фиксированных пауз."]
    imp = "test, expect" + (", devices" if imp_devices else "")
    head.append(f"import {{ {imp} }} from '@playwright/test';" if lang == "ts" else
                f"const {{ {imp} }} = require('@playwright/test');")
    body = [f"  await page.goto({goto});"]
    for i, step in enumerate(f.get("steps") or [], 1):
        body.append(comment(f"{i}. {step}" if not re.match(r"^\s*\d+[.)]", str(step)) else step) + "  — TODO: действие")
    if f.get("expected"):
        body.append(comment(f"Ожидается: {f['expected']}"))
    if f.get("actual"):
        body.append(comment(f"Было (дефект): {f['actual']}"))
    if f.get("verify"):
        body.append(comment(f"Как проверить (из находки): {f['verify']}"))
    fixme = False
    if r.get("js"):
        body.append(f"  const defect = await page.evaluate(() => ({r['js']}));")
        body.append("  expect(defect, 'дефект воспроизводится (выражение из находки)').toBeFalsy();")
    elif r.get("selector"):
        body.append(f"  const el = {locator(r['selector'])};")
        if r.get("assert"):
            body.append("  const bb = await el.boundingBox();")
            body.append("  expect(bb, 'элемент найден').not.toBeNull();")
            ts_bang = "!" if lang == "ts" else ""
            body.append(f"  const b = {{ x: bb{ts_bang}.x, y: bb{ts_bang}.y, w: bb{ts_bang}.width, h: bb{ts_bang}.height }};")
            body.append(f"  expect({r['assert']}, 'дефект по рамке элемента (условие из находки)').toBeFalsy();")
        else:
            body.append("  // Находка: элемент виден, а не должен (или наоборот) — уточнить ожидание")
            body.append("  await expect(el).toBeHidden();")
    else:
        fixme = True
        body.append("  // Нет repro: перевести ожидаемое в проверку, например:")
        body.append("  // await expect(page.getByRole('…', { name: '…' })).toBeVisible();")
    fn = "test.fixme" if fixme else "test"
    lines = head + ["", consts.rstrip("\n")] + ([use.rstrip("\n")] if use else []) + [
        "", f"{fn}({js_str(name)}, async ({{ page }}) => {{"] + body + ["});", ""]
    import render_draft  # noqa: E402 — the tester's home folder never goes into a shared test
    return render_draft.HOME_RX.sub("~", "\n".join(lines))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("findings")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--id")
    g.add_argument("--all", action="store_true")
    ap.add_argument("--run-dir")
    ap.add_argument("--lang", choices=["ts", "js"], default="ts")
    ap.add_argument("--config", help="run-config.yaml (local_roots для file://)")
    ap.add_argument("--out")
    a = ap.parse_args()
    fingerprint.set_roots(a.config or str(Path(a.findings).resolve().parent / "run-config.yaml"))
    data = json.loads(Path(a.findings).read_text(encoding="utf-8"))
    findings = data["findings"] if isinstance(data, dict) else data
    ext = "spec.ts" if a.lang == "ts" else "spec.js"
    if a.id:
        f = next((x for x in findings if x.get("id") == a.id), None)
        if f is None:
            print(f"e2e_stub: находка {a.id} не найдена", file=sys.stderr)
            sys.exit(1)
        text = stub(f, a.lang)
        if a.out:
            Path(a.out).parent.mkdir(parents=True, exist_ok=True)
            Path(a.out).write_text(text, encoding="utf-8")
            print(a.out)
        else:
            print(text, end="")
        return
    if not a.run_dir:
        ap.error("--all: нужен --run-dir")
    out = Path(a.run_dir) / "drafts" / "e2e"
    out.mkdir(parents=True, exist_ok=True)
    n = 0
    for f in findings:
        if f.get("type") in ("proposal", "suggestion", "user-story") or not f.get("id"):
            continue
        (out / f"{f['id']}.{ext}").write_text(stub(f, a.lang), encoding="utf-8")
        n += 1
    print(f"e2e_stub: заготовок {n} -> {out}")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
