#!/usr/bin/env python3
"""Проверка URL и действий по базовым и пользовательским запретам site-qa-audit.

Команды (все печатают JSON, код выхода 0 = allow, 2 = confirm, 3 = deny, 4 = guard недоступен):
  url_guard.py nav URL --config run-config.yaml [--read-only] [--log <RUN_DIR>/logs/read-only.jsonl]
                                                       переход на страницу; --read-only — только чтение страницы
                                                       (без кликов и отправок): снимает запрет путей покупки/доната
                                                       и rules.read_only_urls, но не OAuth, выход, удаление аккаунта,
                                                       чужие хосты и платёжные шлюзы
  url_guard.py resource URL --config ...               загрузка ресурса (скрипт, тайл, шрифт)
  url_guard.py action --text "Купить" [--name "<aria-label>"] [--role button] [--selector "#buy"]
               [--url URL] [--context "текст диалога/страницы"] --config ...
  url_guard.py blocked-origins --config ...            строка для --blocked-origins Playwright MCP
  url_guard.py export --config ... [--out rules.json]  правила в JSON (для node-скриптов)
  url_guard.py selftest                                встроенные проверки

Базовые запреты зашиты в код и не отключаются конфигом.

Локальные файлы (file://, references/local-files.md): переход и загрузка разрешены только внутри каталогов
site.local_roots (абсолютный путь или file:// URL; также «file:///…» в allowed_domains и «file» в allowed_domains —
каталоги file://-адресов из start_urls). Запрещено всегда: «..» в пути, выход за каталог, симлинк внутри каталога,
file:// с хостом (сетевой путь). Базовые запреты путей (/checkout, /logout…) проверяются по пути ОТ каталога.

Fail closed: любая ошибка (нет --config или файла, ошибка разбора YAML, неверный регэксп в правилах, неверные
аргументы, относительный или слишком широкий local_roots, внутренняя ошибка) -> JSON {"decision": "unavailable", ...}
и код 4. Код 4, любой код кроме 0/2/3, «No such file» или пустой вывод = СТОП: переход или действие не выполнять
(references/safety-rules.md §3, §4).
"""
import argparse
import fnmatch
import json
import os
import re
import sys
import unicodedata
from pathlib import Path
from urllib.parse import unquote, urlsplit
from urllib.request import url2pathname

sys.path.insert(0, str(Path(__file__).resolve().parent / "shared"))
import miniyaml  # noqa: E402  (вендорится из shared/scripts)

ALLOW, CONFIRM, DENY, UNAVAILABLE = "allow", "confirm", "deny", "unavailable"
EXIT = {ALLOW: 0, CONFIRM: 2, DENY: 3, UNAVAILABLE: 4}

# ---- Базовые запреты: навигация ----
# Хосты, переход на которые запрещён всегда (вход через внешние аккаунты, платёжные шлюзы).
# Загрузка ресурсов с них (скрипты виджетов) не блокируется, кроме BASE_BLOCKED_ORIGINS.
BASE_DENY_NAV_HOSTS = [
    "steamcommunity.com", "store.steampowered.com", "login.steampowered.com", "*.steampowered.com",
    "accounts.google.com", "discord.com", "*.discord.com", "discordapp.com",
    "appleid.apple.com", "www.facebook.com", "m.facebook.com", "login.microsoftonline.com",
    "login.live.com", "github.com/login/oauth*", "oauth.vk.com", "id.vk.com", "oauth.yandex.ru",
    "passport.yandex.ru", "id.twitch.tv", "api.twitter.com", "x.com/i/oauth2*", "twitter.com/i/oauth2*",
    "*.paypal.com", "paypal.com", "checkout.stripe.com", "*.stripe.com", "yoomoney.ru", "*.yoomoney.ru",
    "yookassa.ru", "*.yookassa.ru", "pay.google.com", "*.cloudpayments.ru", "*.tinkoff.ru",
    "securepay.tinkoff.ru", "*.robokassa.ru", "*.qiwi.com", "*.adyen.com", "*.braintreegateway.com",
    "*.klarna.com", "patreon.com", "*.patreon.com", "boosty.to", "donationalerts.com", "*.donationalerts.com",
    "ko-fi.com", "buymeacoffee.com", "*.buymeacoffee.com",
]
# Фрагменты пути, которые запрещены на любом домене (OAuth/OpenID/оплата/удаление аккаунта).
BASE_DENY_PATH_RX = re.compile(
    r"(/openid/login|/oauth2?/authorize|/oauth/authorize|/o/oauth2|/authorize\?.*client_id=|"
    r"/checkout|/payment|/pay/|/billing|/subscribe|/donate|"
    r"/account/delete|/delete-account|/close-account|/logout|/signout|/sign-out)",
    re.I,
)
# Режим только чтения (nav --read-only): эти части базового запрета путей снимаются — страницу покупки/доната
# можно открыть и прочитать (цены, тексты согласий), ничего не нажимая. Остальные части (OAuth, выход, удаление
# аккаунта) не снимаются никогда: GET на них уже действие.
READ_ONLY_PATH_RX = re.compile(r"(/checkout|/payment|/pay/|/billing|/subscribe|/donate)", re.I)
NEVER_READ_ONLY_PATH_RX = re.compile(
    r"(/openid/login|/oauth2?/authorize|/oauth/authorize|/o/oauth2|/authorize\?.*client_id=|"
    r"/account/delete|/delete-account|/close-account|/logout|/signout|/sign-out)",
    re.I,
)
# Origins для --blocked-origins Playwright MCP: блокируются целиком (и навигация, и ресурсы).
BASE_BLOCKED_ORIGINS = [
    "https://steamcommunity.com", "https://store.steampowered.com", "https://login.steampowered.com",
    "https://checkout.stripe.com", "https://www.paypal.com", "https://yoomoney.ru", "https://yookassa.ru",
    "https://securepay.tinkoff.ru", "https://pay.google.com",
]

# ---- Базовые запреты: действия ----
# (категория, решение, регэксп по нормализованному тексту элемента)
BASE_ACTION_RULES = [
    ("purchase", DENY, r"\b(купить|оплатить|оплата|оформить заказ|в корзину|заказать|подписаться на|оформить подписку|"
                       r"пожертвовать|задонатить|донат|buy|purchase|pay|checkout|place order|add to cart|"
                       r"subscribe|upgrade|donate|tip|go premium|start trial|оформить|купить сейчас|"
                       r"поддержать|поддержи(те)? (проект|автора)|support (us|the project|the author)|"
                       r"become a (patron|supporter)|buy me a coffee)\b"),
    ("oauth", DENY, r"(войти через|sign in (with|through|via)|log ?in (with|through|via)|continue with|"
                    r"привязать|connect (your )?(steam|google|discord|apple|facebook|twitch|vk|github|account)|"
                    r"link (your )?(steam|google|discord|account)|подключить (steam|google|discord|аккаунт)|"
                    r"\bauthorize\b|авторизовать приложение)"),
    ("account-destructive", DENY, r"(удалить (аккаунт|профиль|учетную запись|учётную запись|все|сохранени)|"
                                  r"delete (account|profile|all|save)|close account|deactivate|сбросить прогресс|"
                                  r"reset (progress|account)|отвязать|unlink|выйти из всех|log ?out everywhere)"),
    ("agreement", DENY, r"(принимаю|я согласен|согласиться|accept (the )?(terms|agreement|eula)|i agree|"
                        r"подписать соглашение)"),
    ("destructive", CONFIRM, r"\b(удалить|стереть|очистить все|delete|remove all|clear all|erase|wipe)\b"),
    # Кнопки-иконки без текста: ×, ✕, 🗑 и т.п. — по смыслу удаление/закрытие с потерей данных.
    ("destructive-icon", CONFIRM, r"^[\s×✕✖✗❌🗑\ufe0f-]+$"),
    ("send-to-people", CONFIRM, r"(отправить|send|submit|пожаловаться|report|написать|post|опубликовать|"
                                r"publish|reply|ответить|invite|пригласить)"),
    ("settings", CONFIRM, r"(сохранить настройки|save settings|изменить пароль|change password|"
                          r"сменить e-?mail|change e-?mail)"),
]
# Кнопка с названием провайдера входа рядом с фразой «войдите через…» = OAuth → запрет.
OAUTH_PROVIDERS = re.compile(
    r"^(google|яндекс|yandex|vk|вконтакте|vkontakte|steam|discord|apple|facebook|twitch|github|telegram|"
    r"microsoft|x|twitter|mail\.ru|ok|одноклассники|сбер ?id|госуслуги|battle\.net|epic games|xbox|playstation)$", re.I)
OAUTH_CONTEXT = re.compile(
    r"(войд(ите|и|ём)|войти|вход|авториз|регистрац|sign ?in|log ?in|continue|connect|продолжить) "
    r"(через|с помощью|with|via|using|through)", re.I)
# В диалогах с этим контекстом «Да/OK/Allow» = подтверждение OAuth или оплаты → запрет.
BASE_DIALOG_DENY_CONTEXT = re.compile(
    r"(steam|openid|oauth|google|discord|apple id|facebook|twitch|оплат|payment|card|карт[аы]|"
    r"подписк|subscription|привяз|link account|authorize|разрешить доступ|grant access|удалить аккаунт|delete account)",
    re.I,
)
CONFIRM_WORDS = re.compile(r"^(да|yes|ok|ок|allow|разрешить|confirm|подтвердить|continue|продолжить|accept|принять)$", re.I)
# Отправка «реальным людям» опасна, только если контекст про обратную связь/сообщения.
SEND_CONTEXT = re.compile(r"(обратн|feedback|contact|контакт|сообщени|message|жалоб|report|support|поддержк|"
                          r"comment|коммент|review|отзыв|chat|чат|invite|пригла|email|почт)", re.I)


def norm(text):
    text = unicodedata.normalize("NFKC", text or "").replace("ё", "е").replace("Ё", "Е")
    return re.sub(r"\s+", " ", text).strip().lower()


def host_matches(host, pattern):
    host, pattern = host.lower(), pattern.lower()
    if "/" in pattern:  # маска «хост/путь» сопоставляется с host+path отдельно
        return False
    if pattern.startswith("*."):
        return host == pattern[2:] or host.endswith(pattern[1:])
    return fnmatch.fnmatch(host, pattern)


def hostpath_matches(host, path, pattern):
    if "/" not in pattern:
        return host_matches(host, pattern)
    return fnmatch.fnmatch(f"{host}{path}".lower(), pattern.lower())


def load_config(path):
    if not path:
        return {}
    cfg = miniyaml.load_file(path) or {}
    return cfg


class GuardUnavailable(Exception):
    """Guard cannot decide (bad config, bad rule, bad input): the caller must stop."""


# ---- Local files (file://) ----
FILE_WORDS = ("file", "file:", "file://")


def is_file_entry(s):
    return str(s).strip().lower().startswith("file:") or str(s).strip().lower() in FILE_WORDS


def file_path_of(url):
    """file:// URL -> normalized absolute OS path. ValueError(reason): host (network path), NUL, «..», not absolute."""
    parts = urlsplit(str(url))
    if parts.scheme.lower() != "file":
        raise ValueError("не file://")
    if (parts.netloc or "").lower() not in ("", "localhost"):
        raise ValueError(f"file:// с хостом «{parts.netloc}» — сетевой путь, не локальный файл")
    decoded = unquote(parts.path or "")
    if "\x00" in decoded:
        raise ValueError("NUL в пути")
    if ".." in decoded.replace("\\", "/").split("/"):
        raise ValueError("«..» в пути — выход вверх по каталогам")
    p = url2pathname(parts.path or "")
    if not p or not os.path.isabs(p):
        raise ValueError("путь не абсолютный")
    return os.path.normpath(p)


def _too_broad(p):
    p = os.path.normcase(os.path.normpath(p))
    home = os.path.normcase(os.path.normpath(os.path.expanduser("~")))
    return p == home or os.path.dirname(p) == p  # «/», «C:\», the home folder itself


def local_roots_of(cfg):
    """Directories where file:// is allowed: [{"path": lexical, "real": realpath}]. GuardUnavailable on a bad entry."""
    site = cfg.get("site") or {}
    entries = site.get("local_roots") or []
    if not isinstance(entries, list):
        raise GuardUnavailable("site.local_roots должен быть списком")
    entries = list(entries)
    keyword = False
    for a in site.get("allowed_domains") or []:
        s = str(a).strip().lower()
        if s in FILE_WORDS:
            keyword = True
        elif s.startswith("file:"):
            entries.append(a)
    if keyword:  # «file» in allowed_domains: the folders of the file:// start URLs
        entries += [u for u in site.get("start_urls") or [] if str(u).strip().lower().startswith("file:")]
    roots = []
    for e in entries:
        s = os.path.expanduser(str(e).strip())
        if s.lower().startswith("file:"):
            try:
                p = file_path_of(s)
            except ValueError as ex:
                raise GuardUnavailable(f"local_roots: {e!r}: {ex}")
        else:
            if not os.path.isabs(s):
                raise GuardUnavailable(f"local_roots: путь должен быть абсолютным: {e!r}")
            if ".." in s.replace("\\", "/").split("/"):
                raise GuardUnavailable(f"local_roots: «..» в пути: {e!r}")
            p = os.path.normpath(s)
        if os.path.isfile(p):  # a start file -> its folder (the app needs its assets)
            p = os.path.dirname(p)
        if _too_broad(p):
            raise GuardUnavailable(f"local_roots: слишком широкий каталог {p!r} (корень диска или домашняя папка) — "
                                   "укажите папку приложения")
        if p not in [r["path"] for r in roots]:
            roots.append({"path": p, "real": os.path.realpath(p)})
    return roots


def _under(p, base):
    pc, bc = os.path.normcase(p), os.path.normcase(base)
    return pc == bc or pc.startswith(bc.rstrip("\\/") + os.sep)


def file_verdict(url, roots):
    """-> {"ok": True, "rel": "/sub/page.html"} or {"ok": False, "reason", "rule"} for a file:// URL."""
    try:
        p = file_path_of(url)
    except ValueError as ex:
        return {"ok": False, "reason": f"file: {ex}", "rule": "base:file-path"}
    if not roots:
        return {"ok": False, "reason": "file:// не разрешён: нет site.local_roots (или allowed_domains: [file] "
                                       "с file:// в start_urls)", "rule": "base:file-no-roots"}
    for r in roots:
        for base in (r["path"], r["real"]):
            if not _under(p, base):
                continue
            rel = os.path.relpath(p, base)
            expected = os.path.normpath(os.path.join(r["real"], rel))
            real = os.path.realpath(p)
            if os.path.normcase(real) != os.path.normcase(expected):
                return {"ok": False, "reason": f"симлинк внутри каталога ({p} -> {real}) — не открывается",
                        "rule": "base:file-symlink"}
            if not os.path.isdir(r["path"]) and not os.path.isdir(r["real"]):
                return {"ok": False, "reason": f"каталог local_roots не найден: {r['path']}", "rule": "base:file-root-missing"}
            return {"ok": True, "rel": "/" + ("" if rel == "." else rel.replace(os.sep, "/"))}
    return {"ok": False, "reason": "локальный файл вне local_roots — не открывается", "rule": "base:file-outside-roots"}


def rules_of(cfg):
    r = cfg.get("rules") or {}
    return {
        # file entries ("file", "file:///…") are local roots, never host masks
        "allowed_domains": [a for a in (cfg.get("site") or {}).get("allowed_domains") or [] if not is_file_entry(a)],
        "local_roots": local_roots_of(cfg),
        "forbidden_domains": r.get("forbidden_domains") or [],
        "forbidden_url_patterns": r.get("forbidden_url_patterns") or [],
        "exclude_patterns": (cfg.get("scope") or {}).get("exclude_patterns") or [],
        "forbidden_actions": r.get("forbidden_actions") or [],
        "require_confirmation_actions": r.get("require_confirmation_actions") or [],
        # Заранее одобренные пользователем действия: снимают только уровень confirm, никогда deny.
        "preapproved_actions": r.get("preapproved_actions") or [],
        # Регэкспы URL, которые пользователь разрешил открывать в режиме только чтения (nav --read-only),
        # даже если они попадают под forbidden_url_patterns / exclude_patterns (страницы входа, покупки).
        "read_only_urls": r.get("read_only_urls") or [],
    }


def validate_rules(cfg):
    """Compile every user regex up front: a broken rule makes the guard unavailable, never permissive."""
    rules = rules_of(cfg)
    for key in ("forbidden_url_patterns", "exclude_patterns", "read_only_urls"):
        if not isinstance(rules[key], list):
            raise GuardUnavailable(f"{key} должен быть списком")
        for pat in rules[key]:
            try:
                re.compile(pat)
            except (re.error, TypeError) as ex:
                raise GuardUnavailable(f"неверный регэксп в {key}: {pat!r} ({ex})")
    for key in ("forbidden_actions", "require_confirmation_actions", "preapproved_actions"):
        for rule in rules[key]:
            if not isinstance(rule, dict):
                raise GuardUnavailable(f"{key}: правило должно быть словарём, получено {rule!r}")
            if rule.get("url_pattern"):
                try:
                    re.compile(rule["url_pattern"])
                except (re.error, TypeError) as ex:
                    raise GuardUnavailable(f"неверный url_pattern в {key} {rule.get('id')}: {ex}")
    return rules


def result(decision, kind, target, reason, rule):
    return {"decision": decision, "kind": kind, "target": target, "reason": reason, "rule": rule}


def check_url(url, cfg, kind="nav", read_only=False):
    """read_only (only kind == "nav", nav --read-only): lift the purchase/donate part of the base path ban and
    user URL bans matching rules.read_only_urls. Never lifted: schemes, forbidden_domains, login/payment hosts,
    OAuth, logout, account deletion, hosts outside allowed_domains."""
    rules = rules_of(cfg)
    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    host, path = (parts.hostname or "").lower(), parts.path or "/"
    full = url if not parts.query else url
    ro = read_only and kind == "nav"
    lifted = []
    local = scheme == "file"
    if local:
        # Local files: only inside site.local_roots; path rules below apply to the path FROM the root folder.
        fv = file_verdict(url, rules["local_roots"])
        if not fv["ok"]:
            return result(DENY, kind, url, fv["reason"], fv["rule"])
        if kind == "resource":
            return result(ALLOW, kind, url, "локальный файл в пределах local_roots", None)
        host, path = "", fv["rel"]
    else:
        if scheme in ("javascript", "data", "blob", "about", "chrome"):
            if kind == "nav" and scheme in ("javascript", "chrome"):
                return result(DENY, kind, url, f"схема {scheme}: не переходить", "base:scheme")
            return result(ALLOW, kind, url, "служебная схема", None)
        if scheme in ("mailto", "tel", "sms"):
            return result(DENY, kind, url, f"{scheme}: открывает внешнее приложение — только зафиксировать", "base:scheme")
        for pat in rules["forbidden_domains"]:
            if hostpath_matches(host, path, pat):
                return result(DENY, kind, url, f"домен запрещён пользователем: {pat}", f"user:forbidden_domains:{pat}")
        if kind == "resource":
            for origin in BASE_BLOCKED_ORIGINS:
                if url.lower().startswith(origin + "/") or url.lower() == origin:
                    return result(DENY, kind, url, f"базовая блокировка origin {origin}", "base:blocked-origin")
            return result(ALLOW, kind, url, "загрузка сторонних ресурсов разрешена", None)
        # nav
        for pat in BASE_DENY_NAV_HOSTS:
            if hostpath_matches(host, path, pat):
                return result(DENY, kind, url, f"внешний вход/оплата/донат ({pat}) — базовый запрет", "base:nav-host")
    path_q = path + ("?" + parts.query if parts.query else "")
    if BASE_DENY_PATH_RX.search(path_q):
        if ro and READ_ONLY_PATH_RX.search(path_q) and not NEVER_READ_ONLY_PATH_RX.search(path_q):
            lifted.append("base:nav-path")
        else:
            return result(DENY, kind, url, "путь OAuth/оплаты/подписки/удаления/выхода — базовый запрет", "base:nav-path")
    ro_ok = ro and any(re.search(p, full, re.I) for p in rules["read_only_urls"])
    for pat in rules["forbidden_url_patterns"]:
        if re.search(pat, full, re.I):
            if ro_ok:
                lifted.append(f"user:forbidden_url_patterns:{pat}")
                continue
            return result(DENY, kind, url, f"URL запрещён пользователем: /{pat}/", f"user:forbidden_url_patterns:{pat}")
    for pat in rules["exclude_patterns"]:
        if re.search(pat, full, re.I):
            if ro_ok:
                lifted.append(f"user:exclude_patterns:{pat}")
                continue
            return result(DENY, kind, url, f"исключено из охвата: /{pat}/", f"user:exclude_patterns:{pat}")
    allowed = rules["allowed_domains"]
    if not local:
        if kind == "nav" and not allowed:  # fail closed: без списка разрешённых доменов переход не выполняется
            return result(DENY, kind, url, "site.allowed_domains не задан — без списка доменов переход не разрешён",
                          "base:no-allowlist")
        if allowed and not any(host_matches(host, p) for p in allowed):
            return result(DENY, kind, url, f"хост {host} вне allowed_domains — внешняя страница, не проверялась",
                          "base:outside-allowlist")
    if lifted:
        res = result(ALLOW, kind, url, "только чтение: открыть и прочитать, НИЧЕГО не нажимать и не отправлять "
                     f"(снят запрет {', '.join(lifted)})", "read-only:" + lifted[0])
        res["read_only"] = True
        return res
    return result(ALLOW, kind, url, "в пределах local_roots" if local else "в пределах разрешённых доменов", None)


def _user_rule_hits(rule, text_n, role, selector, url, context_n):
    texts = [norm(t) for t in (rule.get("texts") or [])]
    if texts and not any(t == text_n or (len(t) > 3 and t in text_n) for t in texts):
        return False
    roles = rule.get("roles") or []
    if roles and role and role not in roles:
        return False
    sels = rule.get("selectors") or []
    if sels and (not selector or selector not in sels):
        return False
    if rule.get("url_pattern") and not (url and re.search(rule["url_pattern"], url, re.I)):
        return False
    if rule.get("context") and norm(rule["context"]) not in context_n:
        return False
    return bool(texts or sels or rule.get("url_pattern"))


def check_action(text, cfg, role=None, selector=None, url=None, context=None, name=None):
    """text — видимый текст; name — доступное имя (aria-label/title/alt). Проверяются оба."""
    res = _check_action(text, cfg, role, selector, url, context, name)
    if res["decision"] == CONFIRM:
        rules = rules_of(cfg)
        text_n = norm(" ".join(x for x in (text, name) if x))
        for rule in rules["preapproved_actions"]:
            if _user_rule_hits(rule, text_n, role, selector, url, norm(context)) or (
                    name and _user_rule_hits(rule, norm(name), role, selector, url, norm(context))):
                return result(ALLOW, "action", res["target"], f"заранее одобрено пользователем: "
                              f"{rule.get('source') or rule.get('id')} (было: {res['reason']})",
                              f"user:preapproved:{rule.get('id')}")
    return res


def _check_action(text, cfg, role=None, selector=None, url=None, context=None, name=None):
    rules = rules_of(cfg)
    text_n, context_n = norm(" ".join(x for x in (text, name) if x)), norm(context)
    target = {"text": text, "name": name, "role": role, "selector": selector, "url": url}
    if url:
        nav = check_url(url, cfg, "nav")
        if nav["decision"] == DENY and nav["rule"] not in ("base:outside-allowlist",):
            return result(DENY, "action", target, "действие на запрещённой странице: " + nav["reason"], nav["rule"])
    for rule in rules["forbidden_actions"]:
        if _user_rule_hits(rule, text_n, role, selector, url, context_n):
            return result(DENY, "action", target, f"запрет пользователя: {rule.get('source') or rule.get('id')}",
                          f"user:forbidden_actions:{rule.get('id')}")
    if OAUTH_PROVIDERS.match(norm(text) or norm(name)) and OAUTH_CONTEXT.search(context_n):
        return result(DENY, "action", target, "кнопка входа через внешний аккаунт (провайдер + «войдите через…») — "
                      "базовый запрет", "base:action:oauth-provider")
    if CONFIRM_WORDS.match(text_n) and BASE_DIALOG_DENY_CONTEXT.search(context_n):
        return result(DENY, "action", target, "подтверждение в диалоге OAuth/оплаты/удаления — базовый запрет",
                      "base:dialog-confirm")
    for category, decision, rx in BASE_ACTION_RULES:
        probe = norm(text) if category == "destructive-icon" else text_n
        if probe and re.search(rx, probe, re.I):
            if category == "send-to-people" and not SEND_CONTEXT.search(context_n + " " + text_n + " " + (url or "")):
                continue
            if decision == DENY:
                return result(DENY, "action", target, f"базовый запрет: {category}", f"base:action:{category}")
            return result(CONFIRM, "action", target, f"нужно подтверждение пользователя: {category}",
                          f"base:action:{category}")
    for rule in rules["require_confirmation_actions"]:
        if _user_rule_hits(rule, text_n, role, selector, url, context_n):
            return result(CONFIRM, "action", target, f"по правилу пользователя нужно подтверждение: "
                          f"{rule.get('source') or rule.get('id')}", f"user:require_confirmation:{rule.get('id')}")
    return result(ALLOW, "action", target, "запретов нет", None)


def blocked_origins(cfg):
    origins = list(BASE_BLOCKED_ORIGINS)
    for pat in rules_of(cfg)["forbidden_domains"]:
        if "*" not in pat and "/" not in pat:
            origins.append("https://" + pat)
    return ";".join(dict.fromkeys(origins))


def export(cfg):
    return {
        "rules": rules_of(cfg),
        "base": {
            "deny_nav_hosts": BASE_DENY_NAV_HOSTS,
            "deny_path_regex": BASE_DENY_PATH_RX.pattern,
            "read_only_path_regex": READ_ONLY_PATH_RX.pattern,
            "never_read_only_path_regex": NEVER_READ_ONLY_PATH_RX.pattern,
            "blocked_origins": BASE_BLOCKED_ORIGINS,
        },
        "throttle_ms": (cfg.get("parallel") or {}).get("throttle_ms", 1500),
    }


def file_selftest_cases():
    """file:// cases on a temporary folder: app/ (root), outside/, a symlink app/evil -> outside/."""
    import tempfile
    from pathlib import Path as P
    tmp = tempfile.mkdtemp(prefix="url-guard-")
    try:
        app, out = P(tmp) / "app", P(tmp) / "outside"
        (app / "sub").mkdir(parents=True)
        out.mkdir()
        for f in (app / "index.html", app / "sub" / "page.html", out / "x.html"):
            f.write_text("<p>x</p>", encoding="utf-8")
        symlink = True
        try:
            os.symlink(str(out), str(app / "evil"))
        except (OSError, NotImplementedError):
            symlink = False  # no symlink privilege (Windows): the case is skipped
        u = (app / "index.html").as_uri()
        root = app.as_uri()
        cfg_k = {"site": {"start_urls": [u], "allowed_domains": ["file"]}}
        cfg_r = {"site": {"local_roots": [str(app)], "allowed_domains": []},
                 "rules": {"forbidden_url_patterns": ["/sub/forbidden"]}}
        cfg_u = {"site": {"allowed_domains": [root + "/"]}}
        cases = [
            (check_url(u, cfg_k), ALLOW),
            (check_url((app / "sub" / "page.html").as_uri() + "#/route", cfg_k), ALLOW),
            (check_url((out / "x.html").as_uri(), cfg_k), DENY),
            (check_url(root + "/sub/../../outside/x.html", cfg_k), DENY),
            (check_url(root + "/sub/%2e%2e/%2e%2e/outside/x.html", cfg_k), DENY),
            (check_url("file://server/share/app/index.html", cfg_k), DENY),
            (check_url(u, {"site": {"allowed_domains": ["example.com"]}}), DENY),
            (check_url((app / "sub" / "page.html").as_uri(), cfg_r), ALLOW),
            (check_url((app / "sub" / "forbidden.html").as_uri(), cfg_r), DENY),
            (check_url(u, cfg_u), ALLOW),
            (check_url((app / "a.js").as_uri(), cfg_k, "resource"), ALLOW),
            (check_url((out / "x.html").as_uri(), cfg_k, "resource"), DENY),
            (check_url("https://example.com/", cfg_k), DENY),
        ]
        if symlink:
            cases.append((check_url((app / "evil" / "x.html").as_uri(), cfg_k), DENY))
        for bad in ({"site": {"local_roots": ["relative/dir"]}}, {"site": {"local_roots": ["/"]}},
                    {"site": {"local_roots": [os.path.expanduser("~")]}}):
            try:
                validate_rules(bad)
                cases.append(({"decision": ALLOW, "target": bad}, DENY))
            except GuardUnavailable:
                cases.append(({"decision": DENY}, DENY))
        return cases
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


def selftest():
    cfg = {
        "site": {"allowed_domains": ["example.com", "*.example.com"]},
        "rules": {
            "forbidden_domains": ["ads.example.net"],
            "forbidden_url_patterns": ["/profile"],
            "forbidden_actions": [{"id": "U1", "source": "не нажимать да при подключении steam",
                                   "texts": ["Да", "Yes"], "context": "steam"},
                                  {"id": "U2", "source": "не трогать раздел профиля", "url_pattern": "/profile"}],
            "require_confirmation_actions": [{"id": "C1", "texts": ["Сохранить"]}],
        },
    }
    cfg_pre = {"site": cfg["site"], "rules": {"preapproved_actions": [
        {"id": "P1", "source": "можно удалять собственные тестовые задачи", "texts": ["×", "Delete", "Купить"],
         "context": "todos"}]}}
    cfg_ro = {"site": cfg["site"], "rules": dict(cfg["rules"], read_only_urls=["/profile/"])}
    try:
        validate_rules({"rules": {"forbidden_url_patterns": ["(unclosed"]}})
        bad_regex_detected = False
    except GuardUnavailable:
        bad_regex_detected = True
    cases = [
        (check_url("https://example.com/a", cfg), ALLOW),
        (check_url("https://sub.example.com/a", cfg), ALLOW),
        (check_url("https://evil.test/", cfg), DENY),
        (check_url("https://example.com/profile/1", cfg), DENY),
        (check_url("https://steamcommunity.com/openid/login?x=1", cfg), DENY),
        (check_url("https://example.com/checkout", cfg), DENY),
        (check_url("https://cdn.other.net/lib.js", cfg, "resource"), ALLOW),
        (check_url("https://ads.example.net/x.js", cfg, "resource"), DENY),
        (check_url("mailto:a@example.com", cfg), DENY),
        (check_action("Купить", cfg), DENY),
        (check_action("Sign in through Steam", cfg), DENY),
        (check_action("Да", cfg, context="Подключить аккаунт Steam?"), DENY),
        (check_action("Yes", cfg, context="Allow example app to access your Google account"), DENY),
        (check_action("Удалить", cfg), CONFIRM),
        (check_action("Отправить", cfg, context="Форма обратной связи"), CONFIRM),
        (check_action("Найти", cfg, context="Поиск по сайту"), ALLOW),
        (check_action("Отправить", cfg, context="Поиск по каталогу"), ALLOW),
        (check_action("Сохранить", cfg), CONFIRM),
        (check_action("Открыть", cfg, url="https://example.com/profile"), DENY),
        (check_action("Clear completed", cfg), ALLOW),
        (check_action("×", cfg), CONFIRM),
        (check_action("", cfg, name="Delete", role="button"), CONFIRM),
        (check_action("×", cfg_pre, name="Delete", context="todos list"), ALLOW),
        (check_action("Купить", cfg_pre), DENY),
        (check_action("Google", cfg, role="button", context="Или войдите через Google Яндекс VK"), DENY),
        (check_action("VK", cfg, context="Sign in with"), DENY),
        (check_action("Google", cfg, context="Карта. Источник: Google Maps"), ALLOW),
        (check_action("Поддержать", cfg), DENY),
        (check_action("Поддержать проект ♥", cfg), DENY),
        # nav --read-only (S-8): purchase/donate pages may be read; OAuth, logout, gateways, foreign hosts — never
        (check_url("https://example.com/donate", cfg, read_only=True), ALLOW),
        (check_url("https://example.com/donate", cfg), DENY),
        (check_url("https://example.com/checkout?plan=pro", cfg, read_only=True), ALLOW),
        (check_url("https://example.com/logout", cfg, read_only=True), DENY),
        (check_url("https://example.com/oauth/authorize?client_id=1", cfg, read_only=True), DENY),
        (check_url("https://checkout.stripe.com/pay/x", cfg, read_only=True), DENY),
        (check_url("https://evil.test/donate", cfg, read_only=True), DENY),
        (check_url("https://example.com/profile/1", cfg, read_only=True), DENY),
        (check_url("https://example.com/profile/1", cfg_ro, read_only=True), ALLOW),
        (check_url("https://example.com/profile/1", cfg_ro), DENY),
        (check_url("https://ads.example.net/donate", cfg, read_only=True), DENY),
        # fail closed: a broken user regex makes the guard unavailable
        ({"decision": DENY if bad_regex_detected else ALLOW}, DENY),
    ] + file_selftest_cases()
    failed = [(c, exp) for c, exp in cases if c["decision"] != exp]
    for c, exp in failed:
        print(f"FAIL ожидалось {exp}: {json.dumps(c, ensure_ascii=False)}")
    print(f"selftest: {len(cases) - len(failed)}/{len(cases)} OK")
    return 1 if failed else 0


class FailClosedParser(argparse.ArgumentParser):
    """Bad arguments are a guard failure (code 4), not argparse's code 2 (which means «confirm» here)."""

    def error(self, message):
        unavailable(f"неверные аргументы: {message}")


def unavailable(reason):
    print(json.dumps(result(UNAVAILABLE, "guard", None, "guard недоступен — СТОП, переход/действие не выполнять: "
                            + reason, "guard:unavailable"), ensure_ascii=False))
    sys.exit(EXIT[UNAVAILABLE])


def append_log(path, entry):
    if not path:
        return
    from datetime import datetime, timezone
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(dict(ts=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), **entry),
                            ensure_ascii=False) + "\n")


def main():
    ap = FailClosedParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["nav", "resource", "action", "blocked-origins", "export", "selftest"])
    ap.add_argument("target", nargs="?")
    ap.add_argument("--config")
    ap.add_argument("--text")
    ap.add_argument("--role")
    ap.add_argument("--selector")
    ap.add_argument("--url")
    ap.add_argument("--context")
    ap.add_argument("--name", help="доступное имя элемента: aria-label / title / alt")
    ap.add_argument("--read-only", action="store_true",
                    help="nav: страница только для чтения, без кликов и отправок (safety-rules.md §3.13)")
    ap.add_argument("--log", help="nav --read-only: дописать «прочитано без действий» в этот JSONL")
    ap.add_argument("--out")
    a = ap.parse_args()
    if a.command == "selftest":
        sys.exit(selftest())
    if a.command in ("nav", "resource", "action", "export") and not a.config:
        unavailable("нет --config <RUN_DIR>/run-config.yaml: без правил прогона guard ничего не разрешает")
    if a.config and not Path(a.config).is_file():
        unavailable(f"файл конфига не найден: {a.config}")
    try:
        cfg = load_config(a.config)
        if not isinstance(cfg, dict):
            raise GuardUnavailable("конфиг прогона пустой или не словарь")
        validate_rules(cfg)
    except GuardUnavailable as ex:
        unavailable(str(ex))
    except Exception as ex:  # noqa: BLE001 — any parse failure must stop the caller
        unavailable(f"конфиг не прочитан: {type(ex).__name__}: {ex}")
    if a.command in ("nav", "resource"):
        if not a.target:
            ap.error("нужен URL")
        res = check_url(a.target, cfg, a.command, read_only=a.read_only)
        if res.get("read_only"):
            append_log(a.log, {"type": "read-only", "decision": "allow", "url": a.target, "rule": res["rule"],
                               "note": "прочитано без действий"})
    elif a.command == "action":
        if a.text is None and a.selector is None and a.name is None:
            ap.error("нужен --text, --name или --selector")
        res = check_action(a.text or "", cfg, a.role, a.selector, a.url, a.context, a.name)
    elif a.command == "blocked-origins":
        print(blocked_origins(cfg))
        return
    else:
        data = export(cfg)
        if a.out:
            Path(a.out).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            print(a.out)
        else:
            print(json.dumps(data, ensure_ascii=False, indent=2))
        return
    print(json.dumps(res, ensure_ascii=False))
    sys.exit(EXIT[res["decision"]])


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        main()
    except SystemExit:
        raise
    except Exception as ex:  # noqa: BLE001 — fail closed: an unexpected error is never «allow»
        unavailable(f"внутренняя ошибка: {type(ex).__name__}: {ex}")
