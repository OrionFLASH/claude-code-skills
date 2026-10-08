#!/usr/bin/env python3
"""Parse a free-form user request into a draft run-config.yaml (to be confirmed by the user).

  intake.py from-text [--text "…" | --file request.txt | -] [--output-dir DIR] [--out run-config.yaml] [--json]
      Extracts: start URLs and allowed domains, GitHub repositories with roles and publication settings
      (disclosure, cross links, closed_claims), devices and browsers, auth mode, account states,
      depth, mode, directions, prohibitions (→ rules.forbidden_actions / require_confirmation_actions),
      side-effect hints. Everything not recognised is listed under "needs confirmation".
      The draft is NOT final: show the summary to the user and wait for "старт" (references/intake.md).

Exit codes: 0 ok, 2 empty input.
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent / "shared"))
import miniyaml  # noqa: E402

DIRECTIONS = {
    "functional": r"функционал|functional|работоспособн",
    "logic-state": r"логик|состояни|logic|state",
    "ux": r"\bux\b|удобств|юзабил|usability",
    "visual-ui": r"\bui\b|визуал|вёрстк|верстк|visual|дизайн",
    "responsive-cross-browser": r"адаптив|мобильн|кросс-?браузер|responsive|cross-browser",
    "accessibility": r"доступност|accessibility|a11y|wcag",
    "performance": r"производительн|скорост|performance|lighthouse|быстродейств",
    "seo-content": r"\bseo\b|мета-?тег",
    "content-i18n": r"тексты|локализ|перевод|i18n|язык(и|ов)? интерфейса|терминолог|опечат",
    "security-passive": r"безопасност|security|заголовк[иа] безопасности",
    "product": r"продукт|предложени|идеи|product|user stor",
}
DEVICES = [  # (regex, name, width, height)
    (r"pixel\s*7|андроид|android", "pixel7", 412, 915),
    (r"iphone|айфон|телефон|смартфон|мобильн|mobile|phone", "mobile", 375, 812),
    (r"ipad|планшет|tablet", "ipad", 810, 1080),
    (r"альбомн|landscape|горизонтальн", "landscape", 915, 412),
    (r"720p|низк(ое|ие|ом) окн|1280\s*[x×]\s*720|ноутбук", "laptop-720", 1280, 720),
    (r"десктоп|desktop|компьютер|пк\b", "desktop", 1440, 900),
]
BROWSERS = [(r"safari|webkit|сафари", "webkit"), (r"firefox|фаерфокс|файрфокс", "firefox")]
ACCOUNT_STATES = [(r"гост|без входа|не вошед|guest|logged[- ]out", "guest"),
                  (r"без pro|без подписки|free|бесплатн", "free"),
                  (r"с pro|\bpro\b|премиум|premium|с подпиской", "pro")]
NEG = re.compile(r"(\bне\s+(нажим|нажа|загруж|загрузи|отправл|отправ|публик|опубл|удал|трога|заход|выход|меня|"
                 r"подключ|привяз|входи|соглаш|покуп|оплач|кликай|кликн|ставь|включ|упомин|связыв)\w*|"
                 r"\bнельзя\b|\bзапрещ\w*|\bникогда\b|\bdo not\b|\bdon't\b|\bnever\b)", re.I)
ASK = re.compile(r"(спраш\w*|спроси\w*|уточня\w*|ask)\s+(меня\s+)?(перед|before)", re.I)
QUOTE_RX = re.compile(r"«([^«»]{1,80})»|“([^”]{1,80})”|\"([^\"]{1,80})\"")
REPO_URL = re.compile(r"https?://github\.com/([\w.-]+/[\w.-]+?)(?:\.git)?(?=[/\s,;.)»]|$)")
REPO_BARE = re.compile(r"(?<![\w/.@-])([A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9_.-]+)(?![\w/])")
URL_RX = re.compile(r"https?://[^\s,;)»\"']+")
SIDE_EFFECT = re.compile(r"(загруз\w* (файл|сохранени|сейв)|рейтинг|публичн|рассылк|upload|leaderboard)", re.I)


def clauses(text):
    """Split into sentences and list items; keep quotes intact."""
    parts = re.split(r"(?<=[.!?;])\s+|\n+|(?:^|\s)[-•*]\s+", text)
    return [p.strip(" -•*") for p in parts if p and p.strip(" -•*")]


def quotes(s):
    return [next(g for g in m.groups() if g) .strip() for m in QUOTE_RX.finditer(s)]


def strip_www(h):
    h = (h or "").lower()
    return h[4:] if h.startswith("www.") else h


def output_dir_warning(output_dir):
    """Папка результатов внутри git-репозитория проекта — почти всегда ошибка: результаты должны лежать в <OUTPUT_ROOT>/qa-runs."""
    p = Path(output_dir).expanduser().resolve()
    probe = p
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    try:
        top = subprocess.run(["git", "-C", str(probe), "rev-parse", "--show-toplevel"],
                             capture_output=True, text=True, timeout=5).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        top = ""
    if top:
        return "output_dir %s лежит внутри git-репозитория %s — показать пользователю, предложить SITE_QA_OUTPUT_DIR или другой путь" % (p, top)
    return None


def parse(text, output_dir=None):
    low = text.lower()
    notes, missing = [], []
    cfg = {"version": 1, "output_dir": output_dir, "mode": "dry-run", "language": "ru"}

    # repositories
    repos = {}
    for m in REPO_URL.finditer(text):
        repos.setdefault(m.group(1), None)
    for cl in clauses(text):
        if re.search(r"репозитор|repo|issues?\b|github|копи|коммент|свер", cl, re.I):
            for m in REPO_BARE.finditer(URL_RX.sub(" ", cl)):
                cand = m.group(1).rstrip(".")
                if not re.search(r"\.(com|ru|org|net|io|top|html?)\b", cand, re.I) and not re.fullmatch(r"\d+/\d+", cand):
                    repos.setdefault(cand, None)
    site_urls = [u.rstrip(".") for u in URL_RX.findall(text) if "github.com" not in urlsplit(u).netloc.lower()]
    start_urls = list(dict.fromkeys(site_urls))
    hosts = list(dict.fromkeys(strip_www(urlsplit(u).hostname) for u in start_urls if urlsplit(u).hostname))
    strict = bool(re.search(r"(строго|только) (этот|один) (хост|домен)|не выход\w* за (пределы )?(домен|хост|сайт)", low))
    allowed = []
    for h in hosts:
        allowed += [h] if strict else [h, f"*.{h}"]
    cfg["site"] = {"start_urls": start_urls, "allowed_domains": allowed, "third_party_resources": []}
    if not start_urls:
        missing.append("site.start_urls — стартовый URL")

    # auth and account states
    if re.search(r"(подключ\w* к|через) (моему |мой |открыт\w* )?(браузер|chrome|cdp)|cdp|remote-debugging", low):
        auth = "manual-cdp"
    elif re.search(r"войду сам|вход(ом)? вручную|уже (вошёл|вошел|залогинен)|я залогинен|ручн\w* вход|manual login", low):
        auth = "manual"
    elif re.search(r"тестов\w* (аккаунт|учётк|учетк|пользовател)|test account", low):
        auth = "test-account"
    else:
        auth = "none"
    cfg["auth"] = {"mode": auth, "login_url": None, "username_env": "QA_USERNAME", "password_env": "QA_PASSWORD"}
    states = [name for rx, name in ACCOUNT_STATES if re.search(rx, low)]
    if states:
        cfg["auth"]["account_states"] = states

    # scope, directions, depth
    scope = "whole-site"
    if re.search(r"только (эт(у|от|и) )?(страниц|экран|url)|текущ\w* экран", low):
        scope = "current-screen" if "экран" in low else "url-list"
    cfg["scope"] = {"type": scope, "section_prefix": None, "urls": start_urls if scope == "url-list" else [],
                    "page_limit": 50, "exclude_patterns": []}
    dirs = [d for d, rx in DIRECTIONS.items() if re.search(rx, low)]
    if not dirs or re.search(r"все направлени|полн\w* (qa|аудит)|full audit", low):
        dirs = list(DIRECTIONS)
        if not re.search(r"все направлени|полн\w* (qa|аудит)|full audit", low):
            notes.append("направления не названы — взяты все")
    cfg["directions"] = dirs
    cfg["depth"] = ("smoke" if re.search(r"smoke|быстр\w* (проверк|прогон)|поверхностн", low)
                    else "deep" if re.search(r"\bdeep\b|глубок|тщательн|подробн\w* прогон", low) else "standard")

    # devices and browsers
    vps = []
    for rx, name, w, h in DEVICES:
        if re.search(rx, low) and name not in [v["name"] for v in vps]:
            if name == "mobile" and any(v["name"] == "pixel7" for v in vps):
                continue
            vps.append({"name": name, "width": w, "height": h})
    if not vps:
        notes.append("устройства не названы — по матрице глубины")
        vps = [{"name": "desktop", "width": 1440, "height": 900}, {"name": "mobile", "width": 375, "height": 812}]
    browsers = ["chromium"] + [b for rx, b in BROWSERS if re.search(rx, low)]
    cfg["devices"] = {"viewports": vps, "browsers": browsers}

    # mode
    if re.search(r"боев\w* режим|публикуй|опубликуй|заводи issues|создавай issues|\blive\b", low) and \
            not re.search(r"dry-run|черновик|не публикуй", low):
        cfg["mode"] = "live"
    if re.search(r"english|на английском", low):
        cfg["language"] = "en"

    # repositories with roles and publication settings
    repo_list = []
    for repo in repos:
        ctx = " ".join(c for c in clauses(text) if repo in c) or low
        ctx_l = ctx.lower()
        roles = []
        if re.search(r"свер|check|дубл", ctx_l):
            roles.append("check")
        if re.search(r"завод|созда|публик|новые|write", ctx_l):
            roles.append("write-new")
        if re.search(r"копи|copies|дубликат\w* всех", ctx_l):
            roles.append("copies")
        if re.search(r"коммент", ctx_l):
            roles.append("comment")
        entry = {"url": f"https://github.com/{repo}", "roles": roles or ["check"], "style": "detailed",
                 "labels": "existing", "confirm_before_publish": True, "screenshots": "none"}
        if re.search(r"не упомина\w* (скилл?|claude|ии|ai|инструмент)|без (подписи|упоминани)", low):
            entry["disclosure"] = "none"
            entry["marker"] = "none"
        if re.search(r"не связыв|без (перекрёстн|перекрестн)?\w* ?ссыл|не ссылаться|без ссылок", low):
            entry["cross_links"] = False
        m = re.search(r"закрыт\w*[^.]*?(комментари|новый issue|новые issues|пропуск|пропуска|не трога)", low)
        if m:
            entry["closed_claims"] = {"комментари": "comment", "новый issue": "new", "новые issues": "new"}.get(m.group(1), "skip")
        repo_list.append(entry)
    cfg["repos"] = repo_list

    # prohibitions
    forb, conf, side = [], [], []
    n = 0
    for cl in clauses(text):
        if ASK.search(cl):
            n += 1
            conf.append({"id": f"U{n}", "source": cl, "texts": quotes(cl), "roles": ["button", "link"]})
        elif SIDE_EFFECT.search(cl) and re.search(r"\bбез\b|\bwithout\b|пока не|until", cl, re.I):
            # "do not upload without the «X» checkbox": X is a guard element, not a forbidden button
            notes.append(f"условие безопасности для действия с побочным эффектом — оформить как invariant: «{cl}»")
        elif NEG.search(cl) and not re.search(r"не упомина|не связыв|не ссылаться|не публикуй", cl, re.I):
            n += 1
            rule = {"id": f"U{n}", "source": cl, "texts": quotes(cl), "roles": ["button", "link"]}
            if not rule["texts"]:
                notes.append(f"запрет без текста кнопки — уточнить тексты на языках сайта: «{cl}»")
            forb.append(rule)
        if SIDE_EFFECT.search(cl):
            side.append(cl)
    cfg["rules"] = {"forbidden_domains": [], "forbidden_url_patterns": [], "forbidden_actions": forb,
                    "require_confirmation_actions": conf, "preapproved_actions": []}
    if side:
        cfg["side_effects_hints"] = side
        notes.append("есть действия с побочными эффектами — спросить про side_effects и invariants")
    cfg["plugins"] = {"policy": "all-installed", "selected": []}
    cfg["parallel"] = {"max_workers": 1 if auth in ("manual", "manual-cdp") else 2, "throttle_ms": 1500}
    if auth in ("manual", "manual-cdp"):
        notes.append("общая сессия входа — параллельные браузерные потоки не используются (max_workers: 1)")
    if not output_dir:
        missing.append("output_dir — папка результатов (SITE_QA_OUTPUT_DIR или вопрос)")
    else:
        warn = output_dir_warning(output_dir)
        if warn:
            notes.append(warn)
    return cfg, notes, missing


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("from-text")
    f.add_argument("source", nargs="?", help="'-' — читать stdin")
    f.add_argument("--text")
    f.add_argument("--file")
    f.add_argument("--output-dir")
    f.add_argument("--out")
    f.add_argument("--json", action="store_true", help="печатать JSON вместо YAML")
    a = ap.parse_args()
    if a.text is not None:
        text = a.text
    elif a.file:
        text = Path(a.file).read_text(encoding="utf-8")
    elif a.source == "-" or (a.source is None and not sys.stdin.isatty()):
        text = sys.stdin.read()
    else:
        text = a.source or ""
    if not text.strip():
        sys.stderr.write("intake: пустой запрос — нечего разбирать\n")
        sys.exit(2)
    cfg, notes, missing = parse(text, a.output_dir)
    if a.json:
        print(json.dumps({"config": cfg, "notes": notes, "missing": missing}, ensure_ascii=False, indent=1))
        return
    head = ["# run-config.yaml — ЧЕРНОВИК из intake.py from-text. Показать пользователю и подтвердить перед «старт».",
            "# Секреты сюда не пишутся — только имена переменных окружения."]
    head += [f"# Нужно уточнить: {m}" for m in missing] + [f"# Проверить: {x}" for x in notes]
    out = "\n".join(head) + "\n\n" + miniyaml.dump(cfg) + "\n"
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(out, encoding="utf-8")
        print(f"intake: черновик -> {a.out}")
        for m in missing:
            print(f"  нужно уточнить: {m}")
        for x in notes:
            print(f"  проверить: {x}")
    else:
        print(out, end="")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
