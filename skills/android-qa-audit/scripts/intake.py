#!/usr/bin/env python3
"""Parse a free-form request into a draft run-config.yaml for android-qa-audit (to be confirmed by the user).

  intake.py from-text [--text "…" | --file request.txt | -] [--output-dir DIR] [--out run-config.yaml] [--json] [--lite]
      Extracts: APK/AAB/APKS paths, package name of an installed app, Android versions (API levels or
      «Android 13»), hardware (RAM, cores, storage, low-end phone, tablet, foldable, small screen), runtime
      variants (dark theme, font scale, landscape, RTL/locale, network, battery, Doze, time zone), test kinds,
      directions, depth, real devices, headless, prohibitions (→ rules.forbidden_actions /
      require_confirmation_actions; topics without button texts — camera, QR, hotspot, microphone, location,
      notifications, Bluetooth, contacts — get typical RU+EN texts, camera packages and an "Allow" rule for the
      permission dialog, marked «проверить на разведке»), GitHub repositories, mode, parallel threads
      (parallel.max_workers 1..4), explicit permission to commit results / APK (git.allow_commit_results / _apk).
      Publication disclosure (publish.disclosure: tool by default; none only when the user asks for no mention of
      the tool), hints: Cyrillic input (text --clipboard / ADBKeyBoard), voice/audio apps (mic-inject, audio-voice
      checklist, soak). Everything not recognised is listed under "needs confirmation". The draft is NOT final:
      show it to the user and wait for «старт» (references/intake.md).
      --lite — exploratory run (intake.md → «Лёгкий режим»): one stand, no matrix; the output adds `lite.questions`
      (only what is unclear — ONE AskUserQuestion) and `lite.plan` (what will be done, in order); after the answer
      the run starts without a separate «старт».

Exit codes: 0 ok, 2 empty input.
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "shared"))
import miniyaml  # noqa: E402
import qa_gitignore  # noqa: E402 — commit_permission(): explicit permission to commit results / APK

MAX_WORKERS = 4
ANDROID_TO_API = {"5": 21, "5.0": 21, "5.1": 22, "6": 23, "6.0": 23, "7": 24, "7.0": 24, "7.1": 25, "8": 26, "8.0": 26,
                  "8.1": 27, "9": 28, "10": 29, "11": 30, "12": 31, "12l": 32, "13": 33, "14": 34, "15": 35, "16": 36,
                  "17": 37}
DIRECTIONS = {
    "functional": r"функционал|работоспособн|functional|сценари|основн\w* функц",
    "logic-state": r"логик|состояни|logic|state|данн\w* сохран",
    "ux": r"\bux\b|удобств|юзабил|usability|понятн",
    "visual-ui": r"\bui\b|интерфейс|визуал|вёрстк|верстк|дизайн|visual|layout",
    "device-config-compat": r"конфигурац|разн\w+ (телефон|устройств|экран)|слаб\w+ (телефон|устройств)|планшет|складн|"
                            r"оперативн\w* памят|\bram\b|ядр|тёмн\w* тем|темн\w* тем|шрифт|ориентац|альбомн",
    "lifecycle-resilience": r"жизненн\w* цикл|поворот|сворачива|восстановлен|kill|убийств\w* процесс|lifecycle|устойчив|"
                            r"\bв фоне\b|\bфонов\w*|background|низк\w+ памят",
    "accessibility": r"доступност|accessibility|a11y|talkback|wcag",
    "performance": r"производительн|скорост|быстродейств|performance|тормоз|\bлаг(и|ает|ов)?\b|jank|запуск\w* (приложения )?врем|памят\w* (потребл|утечк)|батаре",
    "security-passive": r"безопасност|security|debuggable|allowbackup|cleartext|экспорт\w* компонент|подпис",
    "compatibility": r"(разн\w+|нескольк\w+|все\w*) верси\w+ (android|андроид|ос)|совместим|compat|android \d+.*android \d+",
    "content-i18n": r"тексты|локализ|перевод|i18n|язык(и|ов)? интерфейса|терминолог|опечат|rtl|арабск|иврит",
}
TEST_KINDS = {
    "manual-scenarios": r"сценари|вручную|ручн\w+ тест|пройди|пройти",
    "monkey": r"monkey|манки|случайн\w+ (нажат|тап|действ)|стресс",
    "ui-auto": r"автотест|автоматическ\w+ (тест|прогон)|uiautomator|по дереву",
    "lifecycle": r"поворот|сворачива|жизненн\w* цикл|kill|восстановлен|смена конфигурац",
    "permissions": r"разрешени|permission",
    "notifications": r"уведомлен|notification|push",
    "deeplinks": r"deep ?link|диплинк|глубок\w+ ссыл|intent-filter",
    "background": r"\bфонов\w*|foreground service|\bв фоне\b|\bdoze\b",
    "low-memory": r"нехватк\w+ памят|low memory|trim-memory|мало памяти",
    "crashes-anr": r"краш|падени|вылет|anr|завис|crash",
    "performance": r"производительн|запуск\w* (холодн|тёпл|тепл)|cold start|jank|gfxinfo|meminfo|батаре",
    "accessibility": r"доступност|talkback|accessibility",
    "security": r"безопасност|security",
    "install-update": r"установк|обновлени\w+ (поверх|с верси)|удалени\w+ приложени|чист\w+ установк|update",
    "edge-input": r"краев|граничн|некорректн\w+ ввод|emoji|длинн\w+ текст",
}
NEG = re.compile(r"(\bне\s+(нажим|нажа|покуп|куп|оплач|плат|отправл|отправ|публик|опубл|удал|трога|заход|входи|"
                 r"звон|пиш|меня|подключ|привяз|соглаш|разреша|выда|ставь|включ|давай|сбрасыв|переход)\w*|"
                 r"\bнельзя\b|\bзапрещ\w*|\bникогда\b|\bdo not\b|\bdon't\b|\bnever\b)", re.I)
ASK = re.compile(r"(спраш\w*|спроси\w*|уточня\w*|ask)\s+(меня\s+)?(перед|before)", re.I)
QUOTE_RX = re.compile(r"«([^«»]{1,80})»|“([^”]{1,80})”|\"([^\"]{1,80})\"")
APK_RX = re.compile(r"(?:«([^«»]+\.(?:apk|aab|apks|xapk))»|\"([^\"]+\.(?:apk|aab|apks|xapk))\"|'([^']+\.(?:apk|aab|apks|xapk))'|"
                    r"((?:~|[A-Za-z]:\\|/|\.{1,2}/|[\w.-]+/)[^\s,;«»\"']*\.(?:apk|aab|apks|xapk))|(\b[\w.-]+\.(?:apk|aab|apks|xapk)\b))", re.I)
PKG_RX = re.compile(r"\b([a-z][a-z0-9_]*(?:\.[a-z0-9_]+){1,})\b")
REPO_URL = re.compile(r"https?://github\.com/([\w.-]+/[\w.-]+?)(?:\.git)?(?=[/\s,;.)»]|$)")
REPO_BARE = re.compile(r"(?<![\w/.@-])([A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9_.-]+)(?![\w/])")
WORD_NUM = {"один": 1, "одном": 1, "два": 2, "двух": 2, "три": 3, "трёх": 3, "трех": 3, "четыре": 4, "четырёх": 4,
            "четырех": 4, "пять": 5, "пяти": 5, "шесть": 6, "восемь": 8, "десять": 10}
WORKERS_RX = re.compile(r"\b(\d+|" + "|".join(WORD_NUM) + r")(?:-?х)?\s+(?:параллельн\w+\s+)?"
                        r"(?:поток\w*|воркер\w*|workers?|threads?|эмулятор\w*)\b|\b(?:max_workers|parallel)\s*[:=]?\s*(\d+)", re.I)
FILE_EXT = re.compile(r"\.(apk|aab|apks|xapk|yaml|yml|json|md|txt|png|jpg|mp4|keystore|jks)$", re.I)


CAMERA_PKGS = ["com.android.camera2", "com.google.android.GoogleCamera", "com.android.camera"]
CAMERA_DIALOG = ["снимать фото", "фото и видео", "take pictures", "camera"]
# Prohibition topics without button texts → rules with typical texts (RU + EN), checked at reconnaissance.
# id, regex over a negated part of a sentence, label, button texts, packages, screens (activity regex),
# permission-dialog contexts (an "Allow" rule with exact texts) or None
TOPICS = [
    ("camera", r"камер|camera|фотоаппарат|сфотограф|сним\w* фото|take (a )?photo", "камера",
     ["Камера", "Открыть камеру", "Сделать фото", "Сфотографировать", "Снять фото", "Camera", "Open camera",
      "Take photo", "Take a photo"], CAMERA_PKGS, [], CAMERA_DIALOG),
    ("qr", r"\bqr\b|qr-?код|сканир|отсканир|\bscan|штрих-?код|barcode", "сканирование QR",
     ["Сканировать", "Сканировать QR", "Сканировать QR-код", "Отсканировать", "QR-сканер", "Scan", "Scan QR",
      "Scan QR code", "QR scanner"], CAMERA_PKGS, [], CAMERA_DIALOG),
    ("hotspot", r"точк\w* доступа|hotspot|раздач\w* (wi-?fi|интернет)|разда\w* (wi-?fi|интернет)|режим\w* модема|"
                r"tether", "точка доступа",
     ["Точка доступа", "Включить точку доступа", "Режим модема", "Раздать Wi-Fi", "Hotspot", "Mobile hotspot",
      "Wi-Fi hotspot", "Turn on hotspot", "Tethering"], [], ["(?i)tether|hotspot"], None),
    ("microphone", r"микрофон|microphone|\bmic\b|запис\w* (голос|звук|аудио)|голосов\w+ (ввод|сообщ)|record(ing)? audio|"
                   r"voice", "микрофон",
     ["Микрофон", "Записать голос", "Голосовое сообщение", "Голосовой ввод", "Удерживайте для записи", "Microphone",
      "Record audio", "Voice message", "Voice input", "Hold to record"], [], [],
     ["записывать аудио", "record audio", "микрофон", "microphone"]),
    ("location", r"геолокац|местоположен|геопозиц|\bgps\b|location|геоданн", "геолокация",
     ["Геолокация", "Местоположение", "Определить местоположение", "Моё местоположение", "Включить геолокацию",
      "Use my location", "Enable location", "Turn on location", "My location", "Location services"], [],
     ["(?i)LocationSettings"], ["местоположени", "location"]),
    ("notifications", r"уведомлен|notification|\bpush\b|пуш-?уведом", "уведомления",
     ["Включить уведомления", "Разрешить уведомления", "Enable notifications", "Turn on notifications",
      "Allow notifications"], [], [], ["уведомлени", "notifications"]),
    ("bluetooth", r"bluetooth|блютуз|блютус", "Bluetooth",
     ["Bluetooth", "Включить Bluetooth", "Turn on Bluetooth", "Устройства поблизости", "Nearby devices"], [],
     ["(?i)bluetooth"], ["bluetooth", "устройства поблизости", "nearby devices"]),
    ("contacts", r"контакт(ы|ам|ов|ами|ах)?\b|contacts", "контакты",
     ["Контакты", "Доступ к контактам", "Пригласить из контактов", "Contacts", "Allow access to contacts",
      "Invite from contacts"], [], [], ["контакт", "contacts"]),
]
ALLOW_TEXTS = ["Разрешить", "При использовании приложения", "Только в этот раз", "Разрешить в любом режиме", "Allow",
               "While using the app", "Only this time", "Allow all the time"]
POSITIVE = re.compile(r"\b(провер\w*|протестир\w*|тестир\w*|посмотр\w*|можно|разрешаю|нужно|надо|включая|check|test|"
                      r"verify|allowed|ok to)\b", re.I)


def negated_parts(clause):
    """Parts of a sentence under a prohibition: «Не трогать камеру и QR, не включать точку доступа» → both parts;
    «не трогай камеру, микрофон и геолокацию» — the negation carries over to a part without its own verb;
    «…, но проверь уведомления» — not carried over. «без камеры» — a prohibition too."""
    parts = re.split(r",|\s+(?:но|а|однако|but|however)\s+", clause)
    out, carry = [], False
    for p in parts:
        if NEG.search(p):
            carry = True
            out.append(p)
        elif carry and not POSITIVE.search(p):
            out.append(p)
        else:
            carry = False
    for m in re.finditer(r"\bбез\s+(\S+(?:\s+\S+)?)", clause, re.I):
        out.append(m.group(0))
    return out


def topic_rules(clause, start_n, dialogs):
    """[(rule, topic)…] for the prohibition topics found in the negated parts of the clause.
    dialogs — contexts of permission-dialog rules already made (camera and QR share one dialog)."""
    text = " ".join(negated_parts(clause)).lower()
    rules, n = [], start_n
    for tid, rx, label, texts, pkgs, screens, dialog in TOPICS:
        if not re.search(rx, text, re.I):
            continue
        n += 1
        rules.append(({"id": f"U{n}", "source": clause, "topic": tid, "texts": list(texts),
                       "review": "типовые тексты — проверить на разведке и дополнить текстами кнопок приложения"}, tid))
        if dialog and tuple(dialog) not in dialogs:
            dialogs.add(tuple(dialog))
            n += 1
            rules.append(({"id": f"U{n}", "source": clause, "topic": tid, "texts": list(ALLOW_TEXTS), "exact": True,
                           "context": list(dialog),
                           "review": f"системный диалог разрешения ({label}): нажимать только отказ"}, tid))
    return rules, n


def clauses(text):
    parts = re.split(r"(?<=[.!?;])\s+|\n+|(?:^|\s)[-•*]\s+", text)
    return [p.strip(" -•*") for p in parts if p and p.strip(" -•*")]


def quotes(s):
    return [next(g for g in m.groups() if g).strip() for m in QUOTE_RX.finditer(s)]


def find_apks(text):
    out = []
    for m in APK_RX.finditer(text):
        p = next(g for g in m.groups() if g).strip().rstrip(".,")
        if p not in out:
            out.append(p)
    return out


def find_package(text, apks):
    low = text.lower()
    if not re.search(r"пакет|package|установленн|уже стоит|уже установ|id приложения|applicationid", low):
        return None
    names = " ".join(apks)
    for m in PKG_RX.finditer(text):
        cand = m.group(1)
        if FILE_EXT.search(cand) or cand in names or re.match(r"^(www|github|play)\.", cand) or \
                re.search(r"\.(com|ru|org|net|io)$", cand) and "/" in text[m.end():m.end() + 1]:
            continue
        if cand.count(".") >= 1 and not re.fullmatch(r"\d+(\.\d+)+", cand) and not cand.startswith("android.permission"):
            return cand
    return None


def find_apis(low):
    apis = set()
    for m in re.finditer(r"\bapi\s*(?:level\s*)?(\d{2})\b", low):
        apis.add(int(m.group(1)))
    for m in re.finditer(r"(?:android|андроид)\w*\s+(\d{1,2}(?:\.\d)?l?)\b", low):
        v = m.group(1)
        if v in ANDROID_TO_API:
            apis.add(ANDROID_TO_API[v])
    for m in re.finditer(r"\b(\d{1,2})\s*(?:и|,|/)\s*(\d{1,2})\s*(?:версии\s*)?(?:android|андроид)", low):
        for v in m.groups():
            if v in ANDROID_TO_API:
                apis.add(ANDROID_TO_API[v])
    return sorted(a for a in apis if 21 <= a <= 40)


def parse(text, output_dir=None):
    low = text.lower()
    notes, missing = [], []
    cfg = {"version": 1, "output_dir": output_dir, "mode": "dry-run", "language": "ru"}

    apks = find_apks(text)
    for p in apks:
        if not Path(p).expanduser().exists():
            notes.append(f"файл не найден: «{p}» — уточнить путь (путь с пробелами писать в кавычках)")
    pkg = find_package(text, apks)
    cfg["app"] = {"source": "apk" if apks else ("installed" if pkg else None), "paths": apks, "package": pkg,
                  "allowed_packages": [], "deeplink_hosts": []}
    if any(p.lower().endswith(".aab") for p in apks):
        cfg["app"]["source"] = "aab"
        notes.append("AAB: для установки нужен bundletool (apk_info.py build-apks) — проверить check_env")
    if not apks and not pkg:
        missing.append("app.paths или app.package — путь к APK/AAB или имя пакета установленного приложения")
    cfg["goal"] = {"what": None, "focus": ["main-flows"], "success": "findings", "success_notes": None}
    cfg["context"] = {"reuse": "new", "sources": [{"type": "chat"}] if len(text) > 200 else [{"type": "app"}], "notes": None}

    # Android versions
    apis = find_apis(low)
    android = {"apis": apis or "auto", "image_tag": None}
    if re.search(r"последн\w+ верси\w+ (android|андроид)|latest android|новейш", low):
        android["include_latest"] = True
    if re.search(r"минимальн\w+ (верси|api)|minsdk", low):
        android["include_min"] = True
    if not apis:
        notes.append("версии Android не названы — по глубине и minSdk/targetSdk из манифеста (depth-matrix.md)")
    cfg["android"] = android

    # hardware and runtime variants
    hw, variants, custom = [], [], []
    ram = re.findall(r"(\d+(?:[.,]\d)?)\s*(?:гб|gb|гиг)\w*\s*(?:оперативн\w*|озу|ram|памят\w*)?", low)
    ram_vals = sorted({float(x.replace(",", ".")) for x in ram if 0.5 <= float(x.replace(",", ".")) <= 16})
    cores = [int(x) for x in re.findall(r"(\d)\s*(?:ядр|cores?|cpu)", low)]
    if re.search(r"слаб\w+ (телефон|устройств|смартфон)|бюджетн|low-?end|дешёв|дешев|старый телефон|мало памяти", low):
        hw.append("low-end")
    if re.search(r"планшет|tablet", low):
        hw.append("tablet")
    if re.search(r"складн|foldable|fold\b", low):
        hw.append("fold")
    if re.search(r"мал\w+ экран|small screen|компактн", low):
        hw.append("small")
    for r_gb in ram_vals:
        mb = int(r_gb * 1024)
        custom.append({"id": f"ram-{mb}", "profile": "small" if mb <= 2048 else "phone", "ram_mb": mb,
                       "cores": cores[0] if cores else (2 if mb <= 2048 else 4), "data": "6G",
                       "label": f"{r_gb:g} ГБ ОЗУ" + (f", {cores[0]} ядра" if cores else "")})
    if hw:
        hw = ["phone"] + hw
    elif custom:  # only «N ГБ ОЗУ»: exactly this configuration, no extra phone 4 GB (matrix.py: [] + custom)
        notes.append("железо: только названная конфигурация (" + ", ".join(x["label"] for x in custom) +
                     "); обычный телефон 4 ГБ добавить — devices.hardware: [phone]")
    vmap = [("dark", r"тёмн\w* тем|темн\w* тем|dark mode|dark theme|ночн\w+ режим"),
            ("font-1.3", r"крупн\w+ шрифт|увеличенн\w+ шрифт|font.?scale|масштаб\w* шрифт"),
            ("font-2.0", r"шрифт\w* 2(\.0)?|максимальн\w+ шрифт"),
            ("landscape", r"альбомн|landscape|горизонтальн|поворот"),
            ("rtl", r"\brtl\b|арабск|иврит|справа налево"),
            ("net-3g", r"\b3g\b|медленн\w+ (сеть|интернет)|плох\w+ (сеть|связь)"),
            ("net-edge", r"\bedge\b|\b2g\b|очень медленн"),
            ("offline", r"офлайн|оффлайн|offline|без (сети|интернета)|авиарежим"),
            ("net-switch", r"смен\w+ сет|переключени\w+ (сети|wi-?fi)"),
            ("battery-low", r"низк\w+ заряд|разряж"),
            ("saver", r"экономи\w+ (заряда|энерги|батаре)|battery saver"),
            ("doze", r"\bdoze\b|режим сна"),
            ("timezone", r"часов\w+ пояс|timezone|time zone"),
            ("display-large", r"масштаб\w* (экрана|интерфейса)|размер (экрана|элементов)|display size")]
    for vid, rx in vmap:
        if re.search(rx, low):
            variants.append(vid)
    m = re.search(r"(?:на|язык\w*)\s+(английск|русск|немецк|арабск|китайск|японск|испанск|французск)\w*", low)
    locale = {"английск": "en-US", "русск": "ru-RU", "немецк": "de-DE", "арабск": "ar", "китайск": "zh-CN",
              "японск": "ja-JP", "испанск": "es-ES", "французск": "fr-FR"}.get(m.group(1)) if m else None
    if locale and locale != "ar":
        variants.append("locale")
    devices = {"hardware": hw if (hw or custom) else None, "custom": custom,
               "variants": (["base"] + variants) if variants else None,
               "locale": locale, "timezone": None}
    cfg["devices"] = devices

    # stands
    real = bool(re.search(r"(мо[её]м|реальн\w+|физическ\w+|подключённ\w+|подключенн\w+) (телефон|устройств|смартфон)|"
                          r"на телефоне|real device|usb", low))
    cfg["stands"] = {"use_devices": [], "consent": [], "use_avds": [], "create_avds": True,
                     "headless": bool(re.search(r"headless|без окна|в фоне эмулятор|no-window", low)),
                     "cleanup": "ask"}
    if real:
        notes.append("упомянуто реальное устройство — отдельный вопрос: какое (serial), что можно делать "
                     "(только чтение / только это приложение / всё), safety-rules.md §3")
    if re.search(r"не (создавай|создавать) (avd|эмулятор)|только (на )?(подключ|реальн)", low):
        cfg["stands"]["create_avds"] = False

    # directions, test kinds, depth
    dirs = [d for d, rx in DIRECTIONS.items() if re.search(rx, low)]
    full = re.search(r"все направлени|полн\w* (qa|тест|аудит|проверк)|full (qa|audit)|найди баги|всё подряд", low)
    if not dirs or full:
        if not full:
            notes.append("направления не названы — взяты все 11")
        dirs = list(DIRECTIONS)
    cfg["directions"] = dirs
    cfg["tests"] = [k for k, rx in TEST_KINDS.items() if re.search(rx, low)] or ["manual-scenarios", "crashes-anr"]
    cfg["depth"] = ("smoke" if re.search(r"smoke|быстр\w* (проверк|прогон|тест)|поверхностн|бегло", low)
                    else "deep" if re.search(r"\bdeep\b|глубок|тщательн|подробн\w* (прогон|тест)|всесторон", low) else "standard")
    if re.search(r"monkey|случайн\w+ нажат", low):
        cfg["monkey"] = {"events": 500, "seed": 42, "throttle_ms": 300}

    # prohibitions
    forb, conf, fpkgs, fscreens, dialogs = [], [], [], [], set()
    n = 0
    for cl in clauses(text):
        if ASK.search(cl):
            n += 1
            conf.append({"id": f"U{n}", "source": cl, "texts": quotes(cl)})
        elif (NEG.search(cl) or re.search(r"\bбез\s", cl, re.I)) and \
                not re.search(r"не упомина|не связыв|не ссылаться|не публикуй|не создавай avd|gitignore|коммит|commit", cl, re.I):
            quoted = quotes(cl)
            if quoted:
                n += 1
                forb.append({"id": f"U{n}", "source": cl, "texts": quoted})
            topics, n = topic_rules(cl, n, dialogs)
            for rule, tid in topics:
                forb.append(rule)
                topic = next(t for t in TOPICS if t[0] == tid)
                fpkgs += [x for x in topic[4] if x not in fpkgs]
                fscreens += [x for x in topic[5] if x not in fscreens]
            labels = list(dict.fromkeys(next(t[2] for t in TOPICS if t[0] == tid) for _, tid in topics))
            if labels:
                notes.append(f"запрет «{cl}» → правила с типовыми текстами ({', '.join(labels)}; RU+EN"
                             + (", пакеты камеры" if any(t in ("camera", "qr") for _, t in topics) else "")
                             + ") — проверить на разведке и дополнить текстами кнопок приложения")
            elif not quoted and NEG.search(cl):
                n += 1
                forb.append({"id": f"U{n}", "source": cl, "texts": []})
                notes.append(f"запрет без текста кнопки — уточнить тексты на языке приложения: «{cl}»")
    cfg["rules"] = {"forbidden_packages": fpkgs, "forbidden_screens": fscreens, "forbidden_deeplinks": [],
                    "forbidden_actions": forb, "require_confirmation_actions": conf, "preapproved_actions": [],
                    "adb_require_confirmation": []}

    # repositories
    repos = {}
    for m in REPO_URL.finditer(text):
        repos.setdefault(m.group(1), None)
    for cl in clauses(text):
        if re.search(r"репозитор|repo|issues?\b|github", cl, re.I):
            for m in REPO_BARE.finditer(re.sub(r"https?://\S+", " ", cl)):
                cand = m.group(1).rstrip(".")
                if not FILE_EXT.search(cand) and not re.search(r"\.(com|ru|org|net|io)\b", cand) and \
                        not re.fullmatch(r"\d+/\d+", cand) and not cand.startswith(("~", ".")):
                    repos.setdefault(cand, None)
    disclosure = "none" if re.search(r"без (упоминани|пометк|подпис|следов)\w*\s*(скил|инструмент|claude|ии\b|ai\b|"
                                     r"автоматиз|бот)|не (упоминай|указывай|пиши)\w*,?\s*(что\s*)?(это\s*)?(скил|"
                                     r"инструмент|claude|ии\b|ai\b|автоматиз|бот)|disclosure:?\s*none|без следов "
                                     r"(скил|инструмент)|no mention of (the )?(tool|claude|ai|automation)", low) else "tool"
    cfg["publish"] = {"disclosure": disclosure, "steps": "human" if re.search(r"человеческ\w* шаг|шаги для человек|"
                                                                             r"без (команд )?adb в шагах|human steps", low) else "auto"}
    if disclosure == "none":
        notes.append("publish.disclosure: none — без подписи и служебных меток скила; для чужих трекеров предупреждение: "
                     "публикация без пометки об автоматизации может ввести мейнтейнеров в заблуждение (repo-sync.md)")
    cfg["repos"] = [{"url": f"https://github.com/{r}", "roles": ["check"], "style": "detailed", "labels": "existing",
                     "confirm_before_publish": True, "attachments": "none", "disclosure": disclosure} for r in repos]
    if repos:
        notes.append("репозитории найдены — уточнить роли (check / write-new / copies / comment), шаблон, метки, вложения")
    if re.search(r"боев\w* режим|публикуй|опубликуй|заводи issues|создавай issues|\blive\b", low) and \
            not re.search(r"dry-run|черновик|не публикуй", low):
        cfg["mode"] = "live"
        notes.append("режим live: перед публикацией всё равно сводная таблица и «да» пользователя")
    if re.search(r"english|на английском", low) and re.search(r"отч[её]т|report|issue", low):
        cfg["language"] = "en"

    # threads
    m = WORKERS_RX.search(low)
    num = m and (m.group(1) or m.group(2))
    asked = (int(num) if num.isdigit() else WORD_NUM[num]) if num else \
        (1 if re.search(r"\bпоследовательно\b|без параллельн|\bsequential", low) else None)
    workers = 2 if asked is None else max(1, min(MAX_WORKERS, asked))
    if asked and asked > MAX_WORKERS:
        notes.append(f"запрошено потоков: {asked} — максимум {MAX_WORKERS}")
    if real and not re.search(r"эмулятор", low):
        workers = min(workers, 1)
        notes.append("только реальное устройство — один поток (одно устройство — одно взаимодействие)")
    cfg["parallel"] = {"max_workers": workers, "throttle_ms": 500}
    cfg["report_destinations"] = [{"type": "local"}]
    perm = qa_gitignore.commit_permission(text)
    cfg["git"] = {"allow_commit_results": perm["allow_commit_results"], "allow_commit_apk": perm["allow_commit_apk"]}
    for key, label in (("results", "результаты (qa-runs/)"), ("apk", "APK, AAB и ключи подписи")):
        if perm[f"allow_commit_{key}"]:
            notes.append(f"явное разрешение коммитить {label}: «{perm['evidence'][key]}» — проверить; без него "
                         "gitignore_helper.py ensure добавит их в .gitignore")
    cfg["plugins"] = {"policy": "all-installed", "selected": []}
    negated = " ".join(negated_parts(text)).lower()
    if re.search(r"кириллиц|по-русски|на русском|русск\w+ (текст|букв|назван|запрос)|unicode|emoji|эмодзи", low):
        notes.append("ввод не-ASCII (кириллица, emoji): adb input его не вводит — text --clipboard (эмулятор, запущенный с "
                     "--mic-inject) или ADBKeyBoard (ime install-adbkeyboard --apk …, с согласия); иначе --translit")
    voice = r"диктофон|запис\w* (голос|речи|звук|аудио)|распознаван\w* речи|расшифровк|транскри|голосов\w+ (приложени|заметк|ассистент)|" \
            r"voice|audio record|speech|микрофон"
    if re.search(voice, low) and not re.search(voice, negated):
        notes.append("голосовое / аудиоприложение: подача звука в микрофон — mic-inject (audio-input.md: gRPC, loopback, "
                     "файл), чек-лист checklists/audio-voice.md, долгие записи — soak / job (long-runs.md)")
    if not output_dir:
        missing.append("output_dir — OUTPUT_ROOT (путь из запроса / ANDROID_QA_OUTPUT_DIR / <cwd>)")
    return cfg, notes, missing


def lite_block(cfg, notes, missing):
    """Exploratory run: only what is unclear (one question) and the plan that starts right after the answer."""
    q = [m for m in missing if not m.startswith("output_dir")]  # OUTPUT_ROOT has a default (<cwd>/qa-runs)
    if any("реальное устройство" in n for n in notes):
        q.append("реальное устройство: serial и что можно делать (read-only / app-only / full)")
    if cfg.get("repos"):
        q.append("репозитории: только сверка или публикация (черновики / после «да»)")
    if cfg.get("android", {}).get("apis") == "auto":
        q.append("версия Android: target из манифеста (Recommended) или указать")
    app = cfg.get("app") or {}
    pkg = app.get("package") or "<package>"
    src = (app.get("paths") or ["<apk>"])[0]
    plan = ["check_env.py --fast --json <RUN_DIR>/env.json",
            f"apk_info.py analyze {src} --summary → gitignore_helper.py ensure <OUTPUT_ROOT> → apk_info.py analyze … --copy-to <RUN_DIR>/apk",
            "один стенд: свой AVD qa-* (avd_manager.py create/start, --mic-inject для голосовых приложений) или подключённое устройство",
            f"adb_helpers.py install / launch --cold {pkg} / logcat start",
            "карта экранов: dump-ui --texts + screenshot (--mark) на каждом экране",
            "исследование по запросу; находки — finding.py add (со скриншотом и отметками)",
            "долгие сценарии — adb_helpers.py job start -- soak … (фоном)",
            "build_report.py report / summary; черновики issues — render_draft.py (dry-run)"]
    return {"questions": q or ["нет — можно начинать"], "plan": plan,
            "note": "лёгкий режим: один вопрос «только неясное», затем сразу работа; matrix.py не нужен (одна ячейка)"}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("from-text")
    f.add_argument("--lite", action="store_true", help="лёгкий (исследовательский) режим: только неясное + план")
    f.add_argument("source", nargs="?", help="'-' — читать stdin")
    f.add_argument("--text")
    f.add_argument("--file")
    f.add_argument("--output-dir")
    f.add_argument("--out")
    f.add_argument("--json", action="store_true")
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
    lite = None
    if a.lite:
        cfg["lite"] = True
        lite = lite_block(cfg, notes, missing)
    if a.json:
        print(json.dumps({"config": cfg, "notes": notes, "missing": missing, **({"lite": lite} if lite else {})},
                         ensure_ascii=False, indent=1))
        return
    head = ["# run-config.yaml — ЧЕРНОВИК из intake.py from-text. Показать пользователю и подтвердить перед «старт».",
            "# Секреты сюда не пишутся — только имена переменных окружения."]
    if lite:
        head = ["# run-config.yaml — лёгкий режим (intake.py from-text --lite): один вопрос «только неясное», затем сразу работа."]
        head += [f"# Спросить: {q}" for q in lite["questions"]] + [f"# План: {s}" for s in lite["plan"]]
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
