#!/usr/bin/env python3
"""Safety guard of android-qa-audit: UI actions, foreground packages, deep links and adb commands
are checked against the base prohibitions and the user's rules from run-config.yaml (references/safety-rules.md).

All commands print JSON {decision, kind, target, reason, rule}; exit code 0 = allow, 2 = confirm, 3 = deny.
  guard.py action --text "Купить" [--desc "<content-desc>"] [--id <resource-id>] [--class <class>]
                  [--package <pkg>] [--screen <activity>] [--context "dialog / screen text"] --config run-config.yaml
  guard.py package <pkg> --config …            may the agent interact with this foreground app?
  guard.py deeplink <uri> --config …           may the agent open this URI (am start -a VIEW -d …)?
  guard.py adb "<adb arguments>" --stand own-emulator|foreign-emulator|real [--serial S] --config …
                                               adb command risk: read / app / device / deny × stand × consent
  guard.py export --config … [--out rules.json]
  guard.py selftest

Base prohibitions are in the code and cannot be switched off by the config. preapproved_actions lift only
"confirm", never "deny". adb_helpers.py calls the same functions before every state-changing command and tap.
"""
import argparse
import json
import re
import shlex
import sys
import unicodedata
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "shared"))
import miniyaml  # noqa: E402

ALLOW, CONFIRM, DENY = "allow", "confirm", "deny"
EXIT = {ALLOW: 0, CONFIRM: 2, DENY: 3}
ORDER = {ALLOW: 0, CONFIRM: 1, DENY: 2}

# ---- packages ----
SYSTEM_OK = {"com.android.systemui", "com.android.permissioncontroller", "com.google.android.permissioncontroller",
             "android"}  # status bar, runtime permission dialogs, system dialogs (ANR, chooser)
CONFIRM_PACKAGES = {  # system apps the app may legitimately open; each interaction is asked
    "com.android.settings": "системные настройки",
    "com.android.camera2": "камера", "com.google.android.GoogleCamera": "камера",
    "com.android.documentsui": "выбор файла", "com.google.android.documentsui": "выбор файла",
    "com.google.android.providers.media.module": "выбор фото", "com.android.providers.media.module": "выбор фото",
    "com.android.packageinstaller": "установщик пакетов", "com.google.android.packageinstaller": "установщик пакетов",
    "com.google.android.apps.nexuslauncher": "лаунчер", "com.android.launcher3": "лаунчер",
}
DENY_PACKAGES = {
    "com.android.vending": "Google Play (покупки, установки, оценки)",
    "com.google.android.gms": "аккаунты Google, вход, оплата", "com.google.android.gsf": "сервисы Google",
    "com.android.dialer": "звонки", "com.google.android.dialer": "звонки", "com.android.phone": "звонки",
    "com.android.server.telecom": "звонки",
    "com.google.android.apps.messaging": "SMS", "com.android.mms": "SMS", "com.android.messaging": "SMS",
    "com.android.contacts": "контакты", "com.google.android.contacts": "контакты",
    "com.google.android.gm": "почта", "com.android.email": "почта",
    "com.android.chrome": "браузер (внешняя страница)", "com.android.browser": "браузер (внешняя страница)",
    "org.mozilla.firefox": "браузер (внешняя страница)", "com.google.android.apps.walletnfcrel": "кошелёк",
    "com.google.android.apps.nbu.paisa.user": "платежи",
}

# ---- UI actions: (category, decision, regex over the normalized text + content-desc) ----
BASE_ACTION_RULES = [
    ("purchase", DENY, r"\b(купить|оплатить|оплата|оформить (заказ|подписку)|в корзину|заказать|подписаться за|"
                       r"пожертвовать|задонатить|донат|buy|purchase|pay( now)?|checkout|place order|add to cart|"
                       r"subscribe|upgrade|donate|go premium|start (free )?trial|начать пробный|попробовать бесплатно|"
                       r"1-tap buy|купить за|оформить|поддержать (проект|автора)|support (us|the project))\b"),
    ("oauth", DENY, r"(войти через|войти с помощью|sign in (with|through|via)|log ?in (with|through|via)|continue with|"
                    r"продолжить (с|через) (google|apple|facebook|vk|яндекс)|привязать|connect (your )?(google|apple|"
                    r"facebook|account)|link (your )?account|add account|добавить аккаунт|choose an account|"
                    r"выберите аккаунт|\bauthorize\b|авторизовать приложение)"),
    ("calls-sms", DENY, r"(^|\b)(позвонить|звонок|call now|make a call|^call$|^dial$|набрать номер|отправить (sms|смс)|"
                        r"send (an )?(sms|text message)|^sms$|^смс$)(\b|$)"),
    ("account-destructive", DENY, r"(удалить (аккаунт|профиль|учетную запись|все данные)|delete (account|profile|all data)|"
                                  r"close account|deactivate account|сбросить прогресс|reset (progress|account)|"
                                  r"factory reset|сброс (настроек|к заводским)|стереть все данные|erase all data)"),
    ("device-admin", DENY, r"(администратор(а)? устройства|device admin|activate (this )?(device )?admin|"
                           r"специальных возможност\w* .*включ|turn on .*accessibility|установк\w* из (этого )?источника|"
                           r"install unknown apps|allow from this source)"),
    ("agreement", CONFIRM, r"(принимаю|я согласен|согласиться|принять (условия|соглашение)|accept (the )?(terms|agreement|eula)|"
                           r"i agree|agree and continue|принять и продолжить)"),
    ("destructive", CONFIRM, r"\b(удалить|стереть|очистить|delete|remove|clear all|erase|wipe)\b"),
    ("destructive-icon", CONFIRM, r"^[\s×✕✖✗❌🗑️-]+$"),
    ("send-to-people", CONFIRM, r"(отправить|send|submit|опубликовать|publish|\bpost\b|reply|ответить|invite|пригласить|"
                                r"поделиться|share|оставить отзыв|оценить|rate (us|app)|пожаловаться|report)"),
    ("account-settings", CONFIRM, r"(сохранить настройки|save settings|изменить пароль|change password|сменить e-?mail|"
                                  r"change e-?mail|выйти из аккаунта|^выйти$|log ?out|sign ?out)"),
]
SEND_CONTEXT = re.compile(r"(сообщени|message|chat|чат|коммент|comment|отзыв|review|feedback|обратн|support|поддержк|"
                          r"invite|пригла|share|поделит|email|почт|post|пост|публик|жалоб|report|rate|оцен)", re.I)
ID_PURCHASE = re.compile(r"(^|[_\W])(buy|purchase|checkout|payment|pay|subscribe|subscription|billing|donate|paywall)([_\W]|$)", re.I)
OAUTH_PROVIDERS = re.compile(r"^(google|apple|facebook|vk|вконтакте|яндекс|yandex|telegram|twitter|x|github|microsoft|"
                             r"discord|steam|mail\.ru|ok|сбер ?id|госуслуги|huawei id|samsung account)$", re.I)
OAUTH_CONTEXT = re.compile(r"(войд(ите|и)|войти|вход|авториз|регистрац|sign ?in|log ?in|continue|connect|продолжить) "
                           r"(через|с помощью|with|via|using|through)", re.I)
DIALOG_DENY_CONTEXT = re.compile(r"(google play|оплат|payment|покупк|purchase|подписк|subscription|card|карт[аы]|"
                                 r"привяз|link account|authorize|grant access|разрешить доступ к аккаунту|google account|"
                                 r"удалить аккаунт|delete account|администратор устройства|device admin)", re.I)
CONFIRM_WORDS = re.compile(r"^(да|yes|ok|ок|allow|разрешить|confirm|подтвердить|continue|продолжить|accept|принять)$", re.I)

# ---- deep links ----
DENY_SCHEMES = {"tel": "звонок", "sms": "SMS", "smsto": "SMS", "mms": "MMS", "mmsto": "MMS", "mailto": "письмо",
                "market": "Google Play", "geo": "внешние карты"}

# ---- adb ----
READ_SHELL = re.compile(r"^(getprop|dumpsys|uiautomator|screencap|ps|pidof|top|cat|ls|df|du|id|whoami|date|wm|"
                        r"logcat|echo|sleep|true|ime|uptime|stat|which|toybox|grep|head|tail|wc|sed|awk)$")
READ_PM = {"list", "path", "dump", "resolve-activity", "query-activities", "has-feature", "get-install-location"}
APP_AM = {"start", "start-activity", "force-stop", "kill", "send-trim-memory", "set-inactive", "get-inactive",
          "stack", "make-uid-idle", "crash", "start-foreground-service", "startservice", "start-service"}


def norm(text):
    text = unicodedata.normalize("NFKC", text or "").replace("ё", "е").replace("Ё", "Е")
    return re.sub(r"\s+", " ", text).strip().lower()


def result(decision, kind, target, reason, rule):
    return {"decision": decision, "kind": kind, "target": target, "reason": reason, "rule": rule}


def load_config(path):
    return (miniyaml.load_file(path) or {}) if path else {}


def rules_of(cfg):
    r = cfg.get("rules") or {}
    app = cfg.get("app") or {}
    st = cfg.get("stands") or {}
    return {
        "package": app.get("package"),
        "allowed_packages": [x for x in (app.get("allowed_packages") or []) if x],
        "forbidden_packages": r.get("forbidden_packages") or [],
        "forbidden_screens": r.get("forbidden_screens") or [],
        "forbidden_deeplinks": r.get("forbidden_deeplinks") or [],
        "forbidden_actions": r.get("forbidden_actions") or [],
        "require_confirmation_actions": r.get("require_confirmation_actions") or [],
        "preapproved_actions": r.get("preapproved_actions") or [],
        "adb_require_confirmation": r.get("adb_require_confirmation") or [],
        "consent": [c for c in (st.get("consent") or []) if isinstance(c, dict) and c.get("serial")],
        "deeplink_hosts": app.get("deeplink_hosts") or [],
    }


# ---------- packages, screens, deep links ----------

def check_package(pkg, cfg):
    rules = rules_of(cfg)
    if not pkg:
        return result(ALLOW, "package", pkg, "пакет неизвестен — решают правила действия", None)
    if pkg in rules["forbidden_packages"]:
        return result(DENY, "package", pkg, f"приложение запрещено пользователем: {pkg}", f"user:forbidden_packages:{pkg}")
    if pkg == rules["package"] or pkg in rules["allowed_packages"]:
        return result(ALLOW, "package", pkg, "тестируемое приложение", None)
    if pkg in SYSTEM_OK:
        return result(ALLOW, "package", pkg, "системный интерфейс (разрешения, шторка, системные диалоги)", None)
    if pkg in DENY_PACKAGES:
        return result(DENY, "package", pkg, f"чужое приложение: {DENY_PACKAGES[pkg]} — базовый запрет, вернуться BACK",
                      "base:package")
    if pkg in CONFIRM_PACKAGES:
        return result(CONFIRM, "package", pkg, f"системное приложение ({CONFIRM_PACKAGES[pkg]}) — спросить", "base:package-confirm")
    if not rules["package"]:
        return result(CONFIRM, "package", pkg, "в run-config нет app.package — неизвестно, своё ли это приложение", "base:no-app")
    return result(DENY, "package", pkg, "чужое приложение — не взаимодействовать, вернуться BACK и записать «ведёт в <пакет>»",
                  "base:foreign-package")


def check_screen(screen, cfg):
    for pat in rules_of(cfg)["forbidden_screens"]:
        if screen and re.search(pat, screen, re.I):
            return result(DENY, "screen", screen, f"экран запрещён пользователем: /{pat}/", f"user:forbidden_screens:{pat}")
    return None


def check_deeplink(uri, cfg):
    rules = rules_of(cfg)
    m = re.match(r"^([a-zA-Z][\w+.-]*):", uri or "")
    scheme = m.group(1).lower() if m else ""
    if scheme in DENY_SCHEMES:
        return result(DENY, "deeplink", uri, f"{scheme}: открывает {DENY_SCHEMES[scheme]} — базовый запрет", "base:deeplink-scheme")
    for pat in rules["forbidden_deeplinks"]:
        if re.search(pat, uri, re.I):
            return result(DENY, "deeplink", uri, f"ссылка запрещена пользователем: /{pat}/", f"user:forbidden_deeplinks:{pat}")
    if scheme == "intent" and re.search(r"action=android\.intent\.action\.(CALL|DIAL|SENDTO|SEND)", uri):
        return result(DENY, "deeplink", uri, "intent со звонком/отправкой — базовый запрет", "base:deeplink-intent")
    if scheme in ("http", "https"):
        host = (re.match(r"^https?://([^/:?#]+)", uri) or [None, ""])[1].lower()
        hosts = [h.lower().lstrip("*.") for h in rules["deeplink_hosts"]]
        if hosts and not any(host == h or host.endswith("." + h) for h in hosts):
            return result(CONFIRM, "deeplink", uri, f"хост {host} не из deep links приложения — откроется браузер", "base:deeplink-host")
    return result(ALLOW, "deeplink", uri, "схема приложения или его домен", None)


# ---------- UI actions ----------

def id_words(res_id):
    tail = (res_id or "").split("/")[-1]
    return re.sub(r"[_\-.]+", " ", tail)


def _user_rule_hits(rule, text_n, desc_n, res_id, cls, pkg, screen, context_n):
    texts = [norm(t) for t in (rule.get("texts") or [])]
    probe = " ".join(x for x in (text_n, desc_n) if x)
    if texts and not any(t == text_n or t == desc_n or (len(t) > 3 and t in probe) for t in texts):
        return False
    descs = [norm(t) for t in (rule.get("descs") or [])]
    if descs and not any(d == desc_n or (len(d) > 3 and d in desc_n) for d in descs):
        return False
    ids = rule.get("ids") or []
    if ids and not any(res_id and (res_id == i or res_id.endswith("/" + i) or (len(i) > 3 and i in res_id)) for i in ids):
        return False
    classes = rule.get("classes") or []
    if classes and not any(cls and (cls == c or cls.endswith("." + c)) for c in classes):
        return False
    if rule.get("package") and pkg != rule["package"]:
        return False
    if rule.get("screen_pattern") and not (screen and re.search(rule["screen_pattern"], screen, re.I)):
        return False
    if rule.get("context") and norm(rule["context"]) not in context_n:
        return False
    return bool(texts or descs or ids or rule.get("screen_pattern"))


def check_action(cfg, text="", desc="", res_id="", cls="", pkg="", screen="", context=""):
    res = _check_action(cfg, text, desc, res_id, cls, pkg, screen, context)
    if res["decision"] == CONFIRM:
        args = (norm(text), norm(desc), res_id or "", cls or "", pkg or "", screen or "", norm(context))
        for rule in rules_of(cfg)["preapproved_actions"]:
            if _user_rule_hits(rule, *args):
                return result(ALLOW, "action", res["target"], f"заранее одобрено пользователем: "
                              f"{rule.get('source') or rule.get('id')} (было: {res['reason']})", f"user:preapproved:{rule.get('id')}")
    return res


def _check_action(cfg, text, desc, res_id, cls, pkg, screen, context):
    rules = rules_of(cfg)
    text_n, desc_n, context_n = norm(text), norm(desc), norm(context)
    both = " ".join(x for x in (text_n, desc_n) if x)
    target = {"text": text, "desc": desc, "id": res_id, "class": cls, "package": pkg, "screen": screen}
    p = check_package(pkg, cfg) if pkg else None
    if p and p["decision"] == DENY:
        return result(DENY, "action", target, p["reason"], p["rule"])
    s = check_screen(screen, cfg)
    if s:
        return result(DENY, "action", target, s["reason"], s["rule"])
    args = (text_n, desc_n, res_id or "", cls or "", pkg or "", screen or "", context_n)
    for rule in rules["forbidden_actions"]:
        if _user_rule_hits(rule, *args):
            return result(DENY, "action", target, f"запрет пользователя: {rule.get('source') or rule.get('id')}",
                          f"user:forbidden_actions:{rule.get('id')}")
    if OAUTH_PROVIDERS.match(text_n or desc_n) and OAUTH_CONTEXT.search(context_n):
        return result(DENY, "action", target, "кнопка входа через внешний аккаунт (провайдер + «войти через…»)",
                      "base:action:oauth-provider")
    if CONFIRM_WORDS.match(text_n or desc_n) and DIALOG_DENY_CONTEXT.search(context_n):
        return result(DENY, "action", target, "подтверждение в диалоге оплаты/входа/удаления аккаунта", "base:dialog-confirm")
    for category, decision, rx in BASE_ACTION_RULES:
        probe = (text_n or desc_n) if category in ("destructive-icon", "calls-sms") else both
        if not probe or not re.search(rx, probe, re.I):
            continue
        if category == "send-to-people" and not SEND_CONTEXT.search(" ".join((context_n, both, res_id or ""))):
            continue
        if decision == DENY:
            return result(DENY, "action", target, f"базовый запрет: {category}", f"base:action:{category}")
        return result(CONFIRM, "action", target, f"нужно подтверждение пользователя: {category}", f"base:action:{category}")
    if res_id and ID_PURCHASE.search(id_words(res_id).replace(" ", "_")):
        return result(CONFIRM, "action", target, "resource-id похож на покупку/подписку — спросить", "base:action:purchase-id")
    for rule in rules["require_confirmation_actions"]:
        if _user_rule_hits(rule, *args):
            return result(CONFIRM, "action", target, f"по правилу пользователя нужно подтверждение: "
                          f"{rule.get('source') or rule.get('id')}", f"user:require_confirmation:{rule.get('id')}")
    if p and p["decision"] == CONFIRM:
        return result(CONFIRM, "action", target, p["reason"], p["rule"])
    return result(ALLOW, "action", target, "запретов нет", None)


# ---------- adb commands ----------

def _consent(rules, serial):
    for c in rules["consent"]:
        if str(c.get("serial")) == str(serial):
            return c.get("scope") or "app-only"
    return None


def _split_adb(args):
    """adb argument list -> (subcommand, rest, shell_tokens_list or None)."""
    if isinstance(args, str):
        args = shlex.split(args)
    args = list(args)
    if args and Path(args[0]).name.lower().startswith("adb"):
        args = args[1:]
    while args and args[0] in ("-s", "-t", "-H", "-P", "-L"):
        args = args[2:]
    while args and args[0] in ("-d", "-e", "-a"):
        args = args[1:]
    if not args:
        return "", [], None
    sub, rest = args[0], args[1:]
    shells = None
    if sub in ("shell", "exec-out"):
        rest = [a for a in rest if a not in ("-n", "-T", "-t", "-x")]
        line = " ".join(rest)
        shells = []
        for part in re.split(r"\s*(?:;|&&|\|\||\|)\s*", line):
            try:
                toks = shlex.split(part)
            except ValueError:
                toks = part.split()
            if toks:
                shells.append(toks)
    return sub, rest, shells


def _classify_shell(toks, app):
    """(risk, target_pkg, reason) — risk: read | app | device | deny."""
    c = toks[0]
    rest = toks[1:]
    first = rest[0] if rest else ""
    if c == "reboot":
        if first in ("bootloader", "recovery", "fastboot", "sideload"):
            return "deny", None, f"reboot {first}"
        return "device", None, "перезагрузка устройства"
    if c == "su" or c.endswith("/su"):
        return "deny", None, "root на устройстве"
    if c == "rm":
        paths = [x for x in rest if not x.startswith("-")]
        if paths and all(re.match(r"^/(sdcard|storage/emulated/0|data/local/tmp)/qa-[\w.-]+$", x) for x in paths):
            return "app", None, "удаление временных файлов скила"
        return "deny", None, "rm вне временных файлов скила (/sdcard/qa-*)"
    if c in ("pm", "cmd") and (c == "pm" or first == "package"):
        sub = rest[1] if c == "cmd" and len(rest) > 1 else first
        args = rest[2:] if c == "cmd" else rest[1:]
        if sub in READ_PM:
            return "read", None, f"pm {sub}"
        pkgs = [a for a in args if re.match(r"^[a-zA-Z][\w]*(\.[\w]+)+$", a) and not a.startswith("android.permission")]
        target = pkgs[0] if pkgs else None
        if sub in ("uninstall", "clear", "grant", "revoke", "reset-permissions", "disable", "disable-user", "enable",
                   "hide", "unhide", "suspend", "unsuspend", "set-app-links", "trim-caches", "set-inactive"):
            if sub in ("reset-permissions", "trim-caches", "disable", "disable-user", "hide", "suspend") and target != app:
                return "deny", target, f"pm {sub} затрагивает другие приложения"
            if target and target == app:
                return "app", target, f"pm {sub} для тестируемого приложения"
            return "deny", target, f"pm {sub} для другого приложения ({target or 'не указано'})"
        if sub in ("install", "install-multiple", "install-create", "install-write", "install-commit"):
            return "app", None, "установка через pm"
        return "device", None, f"pm {sub}"
    if c == "am":
        sub = first
        if sub in ("broadcast",):
            if any("MASTER_CLEAR" in a or "FACTORY_RESET" in a for a in rest):
                return "deny", None, "сброс устройства"
            pkg = next((rest[i + 1] for i, a in enumerate(rest[:-1]) if a == "-p"), None)
            return ("app", pkg, "broadcast тестируемому приложению") if pkg and pkg == app else \
                ("device", pkg, "broadcast (системный или другому приложению)")
        if sub in ("start", "start-activity"):
            joined = " ".join(rest)
            if re.search(r"android\.intent\.action\.(CALL|DIAL|SENDTO|CALL_EMERGENCY)", joined) or \
                    re.search(r"-d\s+['\"]?(tel|sms|smsto|mailto|mms):", joined):
                return "deny", None, "звонок / SMS / письмо — базовый запрет"
            comp = next((rest[i + 1] for i, a in enumerate(rest[:-1]) if a == "-n"), "")
            pkg = comp.split("/")[0] if comp else next((a for a in reversed(rest) if re.match(r"^[a-zA-Z][\w]*(\.[\w]+)+$", a)), None)
            if pkg and app and pkg != app and not comp.startswith("com.android.settings"):
                return "device", pkg, f"запуск другого приложения ({pkg})"
            return "app", pkg, "запуск activity"
        if sub in APP_AM:
            pkg = next((a for a in rest[1:] if re.match(r"^[a-zA-Z][\w]*(\.[\w]+)+$", a)), None)
            if pkg and app and pkg != app:
                return "deny", pkg, f"am {sub} для другого приложения"
            return "app", pkg, f"am {sub}"
        return "device", None, f"am {sub}"
    if c == "monkey":
        pkg = next((rest[i + 1] for i, a in enumerate(rest[:-1]) if a == "-p"), None)
        if not pkg or (app and pkg != app):
            return "deny", pkg, "monkey без -p <тестируемый пакет>"
        return "monkey", pkg, "monkey по тестируемому приложению"
    if c == "input":
        return "app", None, "ввод (жест/текст/клавиша) — элемент проверяется guard.py action"
    if c == "screenrecord":
        return "app", None, "запись экрана во временный файл"
    if c == "content":
        return ("read" if first == "query" and not re.search(r"contacts|sms|mms|call_log|telephony", " ".join(rest)) else "deny"), \
            None, f"content {first}"
    if c == "settings":
        if first in ("get", "list"):
            return "read", None, "settings get"
        if "enabled_accessibility_services" in rest or "install_non_market_apps" in rest:
            return "deny", None, "включение служб специальных возможностей / установки из неизвестных источников"
        return "device", None, "settings put/delete"
    if c in ("svc", "setprop", "wm", "locksettings", "dpm", "device_config"):
        if c == "wm" and (not rest or first in ("size", "density") and len(rest) == 1):
            return "read", None, "wm (чтение)"
        if c in ("locksettings", "dpm"):
            return "deny", None, f"{c}: блокировка экрана / администратор устройства"
        if c == "svc" and first == "power" and len(rest) > 1 and rest[1] in ("shutdown", "reboot"):
            return "device", None, "svc power"
        return "device", None, f"{c} {first}".strip()
    if c == "cmd":
        if first in ("account",) or (first == "user" and len(rest) > 1 and rest[1] in ("remove", "create")):
            return "deny", None, f"cmd {first}: аккаунты/пользователи устройства"
        if first == "locale" and len(rest) > 1 and rest[1] == "set-app-locales":
            pkg = rest[2] if len(rest) > 2 else None
            return ("app" if pkg == app else "device"), pkg, "язык приложения"
        if first in ("appops",):
            pkg = rest[2] if len(rest) > 2 else None
            return ("app" if pkg == app else "deny"), pkg, "appops"
        if first in ("notification",) and len(rest) > 1 and rest[1] in ("list", "get"):
            return "read", None, "cmd notification (чтение)"
        return "device", None, f"cmd {first}"
    if c == "dumpsys":
        if len(rest) > 1 and rest[0] == "batterystats" and "--reset" in rest:
            return "device", None, "сброс статистики батареи"
        if rest and rest[0] in ("battery", "deviceidle") and len(rest) > 1 and rest[1] in (
                "set", "unplug", "reset", "force-idle", "unforce", "step", "disable", "enable"):
            return "device", None, f"dumpsys {rest[0]} {rest[1]}"
        return "read", None, "dumpsys (чтение)"
    if c == "logcat" and ("-c" in rest or "--clear" in rest):
        return "device", None, "очистка журнала logcat"
    if READ_SHELL.match(c):
        return "read", None, c
    return "device", None, f"команда {c}"


def classify_adb(args, app):
    sub, rest, shells = _split_adb(args)
    if sub in ("devices", "version", "get-state", "get-serialno", "get-devpath", "wait-for-device", "pull", "help", ""):
        return [("read", None, f"adb {sub}")]
    if sub in ("install", "install-multiple", "install-multi-package"):
        return [("app", None, "установка APK (пакет сверяет adb_helpers.py)")]
    if sub == "uninstall":
        pkg = next((a for a in rest if not a.startswith("-")), None)
        return [("app", pkg, "удаление тестируемого приложения") if pkg and pkg == app else
                ("deny", pkg, f"удаление другого приложения ({pkg})")]
    if sub == "emu":
        if rest[:2] == ["avd", "name"] or rest[:1] in (["help"],):
            return [("read", None, "emu (чтение)")]
        return [("emulator", None, f"консоль эмулятора: {' '.join(rest[:3])}")]
    if sub in ("reboot",):
        return [("deny" if rest and rest[0] in ("bootloader", "recovery", "sideload", "fastboot") else "device", None, "reboot")]
    if sub in ("root", "unroot", "remount", "disable-verity", "enable-verity"):
        return [("emulator", None, f"adb {sub}")]
    if sub in ("push",):
        dest = rest[-1] if rest else ""
        return [("app" if re.match(r"^/(sdcard|data/local/tmp)/qa-", dest) else "device", None, f"push в {dest}")]
    if sub in ("logcat",):
        return [("device" if ("-c" in rest or "--clear" in rest) else "read", None, "logcat")]
    if sub in ("forward", "reverse", "connect", "disconnect", "reconnect", "start-server", "kill-server", "tcpip", "usb"):
        return [("device" if sub in ("tcpip", "usb", "kill-server") else "read", None, f"adb {sub}")]
    if sub in ("shell", "exec-out"):
        if not shells:
            return [("deny", None, "интерактивный shell без команды")]
        return [_classify_shell(t, app) for t in shells]
    if sub in ("backup", "restore", "sideload"):
        return [("deny", None, f"adb {sub}")]
    return [("device", None, f"adb {sub}")]


def check_adb(args, cfg, stand="own-emulator", serial=None):
    """Decision for one adb command on a stand: own-emulator | foreign-emulator | real."""
    rules = rules_of(cfg)
    app = rules["package"]
    scope = _consent(rules, serial) if stand in ("real", "foreign-emulator") else "full"
    target = {"adb": args if isinstance(args, str) else " ".join(map(str, args)), "stand": stand, "serial": serial,
              "consent": scope}
    decisions = []
    for risk, pkg, why in classify_adb(args, app):
        if risk == "read":
            d = result(ALLOW, "adb", target, why, None)
        elif risk == "deny":
            d = result(DENY, "adb", target, f"базовый запрет: {why}", "base:adb")
        elif risk == "emulator":
            d = result(ALLOW, "adb", target, why, None) if stand == "own-emulator" else \
                result(DENY, "adb", target, f"{why} — только на своём эмуляторе", "base:adb-emulator-only")
        elif risk == "monkey":
            d = result(ALLOW, "adb", target, why, None) if stand == "own-emulator" else (
                result(CONFIRM, "adb", target, f"{why} на {stand}: случайные нажатия — спросить", "base:adb-monkey")
                if scope == "full" else result(DENY, "adb", target, f"monkey на {stand} без согласия full", "base:adb-monkey"))
        elif stand == "own-emulator":
            d = result(ALLOW, "adb", target, f"{why} (свой эмулятор)", None)
        elif scope is None:
            d = result(CONFIRM, "adb", target, f"{why}: {stand} без согласия пользователя — спросить", f"base:adb-{stand}")
        elif scope == "read-only":
            d = result(DENY, "adb", target, f"{why}: согласие только на чтение ({stand})", f"base:adb-{stand}-read-only")
        elif risk == "app" or scope == "full":
            d = result(ALLOW, "adb", target, f"{why} (согласие {scope})", None)
        else:
            d = result(CONFIRM, "adb", target, f"{why}: меняет настройки всего устройства ({stand}) — спросить",
                       f"base:adb-{stand}-device")
        decisions.append(d)
    worst = max(decisions, key=lambda x: (ORDER[x["decision"]], x["rule"] is not None)) if decisions else \
        result(ALLOW, "adb", target, "только чтение", None)
    line = target["adb"]
    if worst["decision"] == ALLOW:
        for pat in rules["adb_require_confirmation"]:
            if re.search(pat, line, re.I):
                return result(CONFIRM, "adb", target, f"по правилу пользователя: /{pat}/", f"user:adb_require_confirmation:{pat}")
    return worst


# ---------- CLI ----------

def export(cfg):
    return {"rules": rules_of(cfg), "base": {"deny_packages": DENY_PACKAGES, "confirm_packages": CONFIRM_PACKAGES,
                                             "system_ok": sorted(SYSTEM_OK), "deny_schemes": DENY_SCHEMES,
                                             "action_rules": [(c, d) for c, d, _ in BASE_ACTION_RULES]},
            "throttle_ms": (cfg.get("parallel") or {}).get("throttle_ms", 800)}


def selftest():
    cfg = {"app": {"package": "com.example.app", "deeplink_hosts": ["example.com"]},
           "stands": {"consent": [{"serial": "R1", "scope": "app-only"}, {"serial": "R2", "scope": "full"},
                                  {"serial": "R3", "scope": "read-only"}]},
           "rules": {"forbidden_screens": ["(?i)settings\\.Billing"],
                     "forbidden_actions": [{"id": "U1", "source": "не нажимать «Опубликовать»", "texts": ["Опубликовать"]},
                                           {"id": "U2", "source": "не трогать кнопку экспорта", "ids": ["btn_export"]}],
                     "require_confirmation_actions": [{"id": "C1", "texts": ["Сбросить фильтры"]}],
                     "preapproved_actions": [{"id": "P1", "source": "удалять свои тестовые заметки можно",
                                              "texts": ["Удалить"], "context": "тестовая заметка"}]}}
    A = lambda **kw: check_action(cfg, **kw)["decision"]  # noqa: E731
    D = lambda line, stand="own-emulator", serial=None: check_adb(line, cfg, stand, serial)["decision"]  # noqa: E731
    cases = [
        (A(text="Купить за 199 ₽"), DENY), (A(text="Subscribe"), DENY), (A(text="Оформить подписку"), DENY),
        (A(text="Continue with Google"), DENY), (A(text="Google", context="Войти через"), DENY),
        (A(text="Google", context="Карта Google"), ALLOW), (A(text="Позвонить"), DENY), (A(text="Call"), DENY),
        (A(text="Callback settings"), ALLOW), (A(text="Отправить SMS"), DENY), (A(text="Удалить аккаунт"), DENY),
        (A(text="OK", context="Google Play: подтвердите покупку"), DENY), (A(text="Удалить"), CONFIRM),
        (A(text="Удалить", context="тестовая заметка №1"), ALLOW), (A(text="×"), CONFIRM),
        (A(text="", desc="Закрыть"), ALLOW), (A(text="Отправить", context="Чат с поддержкой"), CONFIRM),
        (A(text="Отправить", context="Поиск по каталогу"), ALLOW), (A(text="Принять и продолжить"), CONFIRM),
        (A(text="Опубликовать"), DENY), (A(text="Экспорт", res_id="com.example.app:id/btn_export"), DENY),
        (A(text="", res_id="com.example.app:id/buy_button"), CONFIRM), (A(text="Сбросить фильтры"), CONFIRM),
        (A(text="Далее", pkg="com.example.app"), ALLOW), (A(text="Install", pkg="com.android.vending"), DENY),
        (A(text="Разрешить", pkg="com.google.android.permissioncontroller"), ALLOW),
        (A(text="Открыть", pkg="com.other.app"), DENY), (A(text="Готово", pkg="com.android.settings"), CONFIRM),
        (A(text="Далее", screen="com.example.app.settings.BillingActivity"), DENY),
        (A(text="Активировать администратора устройства"), DENY), (A(text="Найти"), ALLOW),
        (check_deeplink("tel:+70000000000", cfg)["decision"], DENY), (check_deeplink("market://details?id=x", cfg)["decision"], DENY),
        (check_deeplink("https://example.com/item/1", cfg)["decision"], ALLOW),
        (check_deeplink("https://other.test/x", cfg)["decision"], CONFIRM), (check_deeplink("exampleapp://open", cfg)["decision"], ALLOW),
        (D("shell dumpsys meminfo com.example.app"), ALLOW), (D("shell pm clear com.example.app"), ALLOW),
        (D("shell pm clear com.other.app"), DENY), (D("uninstall com.other.app"), DENY), (D("uninstall com.example.app"), ALLOW),
        (D("uninstall com.example.app", "real"), CONFIRM), (D("uninstall com.example.app", "real", "R1"), ALLOW),
        (D("shell settings put system font_scale 1.3", "real", "R1"), CONFIRM),
        (D("shell settings put system font_scale 1.3", "real", "R2"), ALLOW),
        (D("shell input tap 10 10", "real", "R3"), DENY), (D("shell getprop", "real", "R3"), ALLOW),
        (D("shell am start -a android.intent.action.CALL -d tel:123"), DENY),
        (D("shell monkey -p com.example.app -s 42 500"), ALLOW), (D("shell monkey -s 42 500"), DENY),
        (D("shell monkey -p com.example.app 100", "real", "R2"), CONFIRM),
        (D("emu kill"), ALLOW), (D("emu kill", "foreign-emulator", "emulator-5556"), DENY),
        (D("shell rm -rf /sdcard/qa-rec.mp4"), ALLOW), (D("shell rm -rf /sdcard/DCIM"), DENY),
        (D("shell settings put secure enabled_accessibility_services x/y"), DENY),
        (D("shell am broadcast -a android.intent.action.MASTER_CLEAR"), DENY), (D("shell logcat -c", "real", "R1"), CONFIRM),
        (D("shell pm reset-permissions"), DENY), (D("shell cmd connectivity airplane-mode enable"), ALLOW),
        (D("shell content query --uri content://sms/inbox"), DENY), (D("reboot bootloader"), DENY),
        (D("-s emulator-5554 shell \"getprop sys.boot_completed; dumpsys battery\""), ALLOW),
    ]
    failed = [(i, got, exp) for i, (got, exp) in enumerate(cases) if got != exp]
    for i, got, exp in failed:
        print(f"FAIL #{i}: ожидалось {exp}, получено {got}")
    print(f"selftest: {len(cases) - len(failed)}/{len(cases)} OK")
    return 1 if failed else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["action", "package", "deeplink", "adb", "export", "selftest"])
    ap.add_argument("target", nargs="?")
    ap.add_argument("--config")
    ap.add_argument("--text", default="")
    ap.add_argument("--desc", default="")
    ap.add_argument("--id", default="")
    ap.add_argument("--class", dest="cls", default="")
    ap.add_argument("--package", default="")
    ap.add_argument("--screen", default="")
    ap.add_argument("--context", default="")
    ap.add_argument("--stand", default="own-emulator", choices=["own-emulator", "foreign-emulator", "real"])
    ap.add_argument("--serial")
    ap.add_argument("--out")
    a = ap.parse_args()
    if a.command == "selftest":
        sys.exit(selftest())
    cfg = load_config(a.config)
    if a.command == "action":
        if not (a.text or a.desc or a.id):
            ap.error("нужен --text, --desc или --id")
        res = check_action(cfg, a.text, a.desc, a.id, a.cls, a.package, a.screen, a.context)
    elif a.command == "package":
        res = check_package(a.target or a.package, cfg)
    elif a.command == "deeplink":
        if not a.target:
            ap.error("нужен URI")
        res = check_deeplink(a.target, cfg)
    elif a.command == "adb":
        if not a.target:
            ap.error("нужна строка аргументов adb")
        res = check_adb(a.target, cfg, a.stand, a.serial)
    else:
        data = json.dumps(export(cfg), ensure_ascii=False, indent=2)
        if a.out:
            Path(a.out).parent.mkdir(parents=True, exist_ok=True)
            Path(a.out).write_text(data, encoding="utf-8")
            print(a.out)
        else:
            print(data)
        return
    print(json.dumps(res, ensure_ascii=False))
    sys.exit(EXIT[res["decision"]])


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
