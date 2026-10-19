#!/usr/bin/env python3
"""Статический разбор APK/AAB без установки и запуска → <OUT>/data/app-scan.json (+ research/app-scan.md).

  app_scan.py <OUT> [APK …] [--tool auto|python|aapt2] [--max-dex-mb 200] [--stdout]

Без путей APK берутся из run-config (sources.external.apk — их находит intake.py в рабочей папке) и из <repo>/**/*.apk.
Что извлекается (только чтение архива, приложение не устанавливается):
  - манифест: пакет, versionCode/versionName, minSdk/targetSdk/compileSdk, разрешения (опасные помечены), функции
    устройства, компоненты (activity/service/receiver/provider, exported), intent-фильтры, глубокие ссылки (scheme/host),
    флаги allowBackup, usesCleartextTraffic, debuggable, networkSecurityConfig;
  - ресурсы: название приложения (если ссылка на строку), локали строк (языки интерфейса), доля строк на кириллице,
    домены из строк;
  - код без декомпиляции: SDK третьих сторон по сигнатурам классов в classes*.dex (аналитика, краши, реклама,
    платежи, ML/распознавание речи), фреймворк (Flutter, React Native, Expo, Compose), ключевые слова ИИ/ASR
    (openai, whisper, gpt-…) в dex, JS-бандле и конфигах, домены API;
  - нативные библиотеки (ABI, имена .so), ассеты: список и разбор небольших assets/*.json|*.config (ключи; значения,
    похожие на секреты, скрываются), версии библиотек из META-INF/*.version и *.properties;
  - сигналы для стратегии (эвристики, «проверить»): старый targetSdk, нет POST_NOTIFICATIONS при пушах, нет точных
    будильников при напоминаниях, открытый трафик, бэкап, debuggable, экспортированные компоненты без защиты.

Инструменты: собственный разбор бинарного AndroidManifest.xml и resources.arsc (стандартная библиотека) — всегда;
aapt2 (PATH, $ANDROID_HOME/build-tools/*, ~/Library/Android/sdk/build-tools/*) — если найден, для названия и
локалей и сверки (--tool python — не искать). AAB: манифест там в protobuf — разбирается только состав архива
(ограничение записывается в limitations). Обход экранов на эмуляторе (adb, uiautomator) этот скрипт НЕ делает —
для этого скилл android-qa-audit; скриншоты кладутся в mockups/current/. Только стандартная библиотека.
"""
import argparse
import glob
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------- бинарный XML (AXML)
ATTR_IDS = {0x01010003: "name", 0x01010001: "label", 0x01010002: "icon", 0x0101021b: "versionCode", 0x0101021c: "versionName",
            0x0101020c: "minSdkVersion", 0x01010270: "targetSdkVersion", 0x01010010: "exported", 0x0101000f: "debuggable",
            0x01010006: "permission", 0x01010280: "allowBackup", 0x01010027: "scheme", 0x01010028: "host",
            0x01010572: "compileSdkVersion", 0x010104ec: "usesCleartextTraffic"}


def _string_pool(buf, off):
    """Пул строк (ResStringPool) с позиции off → список строк."""
    _t, hsize, _size, count, _styles, flags, s_start, _st_start = struct.unpack_from("<HHIIIIII", buf, off)
    utf8 = bool(flags & 0x100)
    offs = struct.unpack_from("<%dI" % count, buf, off + hsize) if count else ()
    base = off + s_start
    out = []
    for o in offs:
        p = base + o
        try:
            if utf8:
                n = buf[p]
                p += 2 if n & 0x80 else 1
                n = buf[p]
                if n & 0x80:
                    n = ((n & 0x7F) << 8) | buf[p + 1]
                    p += 2
                else:
                    p += 1
                out.append(buf[p:p + n].decode("utf-8", errors="replace"))
            else:
                n = struct.unpack_from("<H", buf, p)[0]
                p += 2
                if n & 0x8000:
                    n = ((n & 0x7FFF) << 16) | struct.unpack_from("<H", buf, p)[0]
                    p += 2
                out.append(buf[p:p + 2 * n].decode("utf-16-le", errors="replace"))
        except (IndexError, struct.error):
            out.append("")
    return out


def _typed(strings, raw, dtype, data):
    if raw != 0xFFFFFFFF and raw < len(strings):
        return strings[raw]
    if dtype == 0x03:
        return strings[data] if data < len(strings) else ""
    if dtype == 0x12:
        return data != 0
    if dtype in (0x10, 0x11):
        return data - (1 << 32) if data & 0x80000000 and dtype == 0x10 else data
    if dtype == 0x01:
        return "@0x%08x" % data
    if dtype == 0x02:
        return "?0x%08x" % data
    if dtype == 0x04:
        return struct.unpack("<f", struct.pack("<I", data))[0]
    return data


def parse_axml(buf):
    """Бинарный XML Android → список элементов [{"tag", "depth", "attrs": {имя: значение}}] в порядке документа."""
    if len(buf) < 8 or struct.unpack_from("<H", buf, 0)[0] != 0x0003:
        raise ValueError("не бинарный XML Android (нет заголовка RES_XML_TYPE)")
    strings, resmap, elems = [], [], []
    pos, depth, end = 8, 0, min(len(buf), struct.unpack_from("<I", buf, 4)[0])
    while pos + 8 <= end:
        ctype, hsize, csize = struct.unpack_from("<HHI", buf, pos)
        if csize < 8:
            break
        if ctype == 0x0001:
            strings = _string_pool(buf, pos)
        elif ctype == 0x0180:
            resmap = list(struct.unpack_from("<%dI" % ((csize - hsize) // 4), buf, pos + hsize))
        elif ctype == 0x0102:
            ext = pos + hsize
            _ns, name, a_start, a_size, a_count = struct.unpack_from("<IIHHH", buf, ext)
            attrs = {}
            for i in range(a_count):
                a = ext + a_start + i * a_size
                _ans, aname, raw, _vs, _r0, dtype, data = struct.unpack_from("<IIIHBBI", buf, a)
                key = strings[aname] if aname < len(strings) else ""
                if not key and aname < len(resmap):
                    key = ATTR_IDS.get(resmap[aname], "0x%08x" % resmap[aname])
                attrs[key] = _typed(strings, raw, dtype, data)
            elems.append({"tag": strings[name] if name < len(strings) else "?", "depth": depth, "attrs": attrs})
            depth += 1
        elif ctype == 0x0103:
            depth = max(0, depth - 1)
        pos += csize
    return elems


# ---------------------------------------------------------------- resources.arsc
def parse_arsc(buf):
    """resources.arsc → (глобальные строки, {res_id: {локаль: строка}} для строковых ресурсов, множество локалей строк)."""
    gstrings, values, locales = [], {}, set()
    if len(buf) < 12 or struct.unpack_from("<H", buf, 0)[0] != 0x0002:
        raise ValueError("не resources.arsc")
    pos = struct.unpack_from("<H", buf, 2)[0]
    total = min(len(buf), struct.unpack_from("<I", buf, 4)[0])
    while pos + 8 <= total:
        ctype, hsize, csize = struct.unpack_from("<HHI", buf, pos)
        if csize < 8:
            break
        if ctype == 0x0001 and not gstrings:
            gstrings = _string_pool(buf, pos)
        elif ctype == 0x0200:
            pkg_id = struct.unpack_from("<I", buf, pos + 8)[0]
            type_off = struct.unpack_from("<I", buf, pos + 8 + 4 + 256)[0]
            types = _string_pool(buf, pos + type_off) if type_off else []
            p = pos + hsize
            while p + 8 <= pos + csize:
                t2, h2, s2 = struct.unpack_from("<HHI", buf, p)
                if s2 < 8:
                    break
                if t2 == 0x0201:
                    tid, flags = buf[p + 8], buf[p + 9]
                    count, e_start = struct.unpack_from("<II", buf, p + 12)
                    cfg = p + 20
                    lang = buf[cfg + 8:cfg + 10]
                    country = buf[cfg + 10:cfg + 12]
                    loc = ""
                    if lang[0] and not (lang[0] & 0x80):
                        loc = lang.decode("latin-1") + ("-" + country.decode("latin-1") if country[0] and not (country[0] & 0x80) else "")
                    tname = types[tid - 1] if 0 < tid <= len(types) else ""
                    if tname == "string":
                        if count and loc:
                            locales.add(loc)
                        idx = p + h2
                        entries = []
                        if flags & 0x01:                              # sparse
                            for k in range(count):
                                ei, eo = struct.unpack_from("<HH", buf, idx + 4 * k)
                                entries.append((ei, eo * 4))
                        elif flags & 0x02:                            # offset16
                            for k in range(count):
                                eo = struct.unpack_from("<H", buf, idx + 2 * k)[0]
                                if eo != 0xFFFF:
                                    entries.append((k, eo * 4))
                        else:
                            for k in range(count):
                                eo = struct.unpack_from("<I", buf, idx + 4 * k)[0]
                                if eo != 0xFFFFFFFF:
                                    entries.append((k, eo))
                        for ei, eo in entries:
                            e = p + e_start + eo
                            if e + 8 > p + s2:
                                continue
                            esize, eflags = struct.unpack_from("<HH", buf, e)
                            if eflags & 0x0008:                       # compact
                                dtype, data = eflags >> 8, struct.unpack_from("<I", buf, e + 4)[0]
                            elif eflags & 0x0001:                     # complex (стили, массивы) — пропуск
                                continue
                            else:
                                _vs, _r0, dtype, data = struct.unpack_from("<HBBI", buf, e + esize)
                            if dtype == 0x03 and data < len(gstrings):
                                rid = ((pkg_id & 0xFF) << 24) | (tid << 16) | ei
                                values.setdefault(rid, {})[loc or ""] = gstrings[data]
                p += s2
        pos += csize
    return gstrings, values, locales


# ---------------------------------------------------------------- справочники
DANGEROUS = {"READ_CALENDAR", "WRITE_CALENDAR", "CAMERA", "READ_CONTACTS", "WRITE_CONTACTS", "GET_ACCOUNTS", "ACCESS_FINE_LOCATION",
             "ACCESS_COARSE_LOCATION", "ACCESS_BACKGROUND_LOCATION", "RECORD_AUDIO", "READ_PHONE_STATE", "READ_PHONE_NUMBERS",
             "CALL_PHONE", "ANSWER_PHONE_CALLS", "READ_CALL_LOG", "WRITE_CALL_LOG", "ADD_VOICEMAIL", "USE_SIP", "BODY_SENSORS",
             "BODY_SENSORS_BACKGROUND", "ACTIVITY_RECOGNITION", "SEND_SMS", "RECEIVE_SMS", "READ_SMS", "RECEIVE_WAP_PUSH",
             "RECEIVE_MMS", "READ_EXTERNAL_STORAGE", "WRITE_EXTERNAL_STORAGE", "ACCESS_MEDIA_LOCATION", "POST_NOTIFICATIONS",
             "NEARBY_WIFI_DEVICES", "BLUETOOTH_SCAN", "BLUETOOTH_CONNECT", "BLUETOOTH_ADVERTISE", "UWB_RANGING", "READ_MEDIA_IMAGES",
             "READ_MEDIA_VIDEO", "READ_MEDIA_AUDIO", "READ_MEDIA_VISUAL_USER_SELECTED"}
SPECIAL = {"SYSTEM_ALERT_WINDOW", "WRITE_SETTINGS", "MANAGE_EXTERNAL_STORAGE", "REQUEST_INSTALL_PACKAGES", "SCHEDULE_EXACT_ALARM",
           "USE_EXACT_ALARM", "PACKAGE_USAGE_STATS", "BIND_ACCESSIBILITY_SERVICE", "REQUEST_IGNORE_BATTERY_OPTIMIZATIONS",
           "QUERY_ALL_PACKAGES", "USE_FULL_SCREEN_INTENT"}
SDKS = [  # (id, название, категория, сигнатуры в dex)
    ("firebase-analytics", "Firebase Analytics", "аналитика", [b"Lcom/google/firebase/analytics/"]),
    ("firebase-crashlytics", "Firebase Crashlytics", "краши", [b"Lcom/google/firebase/crashlytics/"]),
    ("firebase-messaging", "Firebase Cloud Messaging", "пуши", [b"Lcom/google/firebase/messaging/"]),
    ("firebase-remote-config", "Firebase Remote Config", "конфигурация", [b"Lcom/google/firebase/remoteconfig/"]),
    ("sentry", "Sentry", "краши", [b"Lio/sentry/"]),
    ("appmetrica", "AppMetrica", "аналитика", [b"Lio/appmetrica/", b"Lcom/yandex/metrica/"]),
    ("mytracker", "myTracker", "аналитика", [b"Lcom/my/tracker/"]),
    ("amplitude", "Amplitude", "аналитика", [b"Lcom/amplitude/"]),
    ("mixpanel", "Mixpanel", "аналитика", [b"Lcom/mixpanel/"]),
    ("posthog", "PostHog", "аналитика", [b"Lcom/posthog/"]),
    ("appsflyer", "AppsFlyer", "атрибуция", [b"Lcom/appsflyer/"]),
    ("adjust", "Adjust", "атрибуция", [b"Lcom/adjust/sdk/"]),
    ("facebook", "Meta (Facebook) SDK", "реклама/аналитика", [b"Lcom/facebook/FacebookSdk", b"Lcom/facebook/appevents/"]),
    ("admob", "Google Mobile Ads (AdMob)", "реклама", [b"Lcom/google/android/gms/ads/"]),
    ("yandex-ads", "Yandex Mobile Ads", "реклама", [b"Lcom/yandex/mobile/ads/"]),
    ("mytarget", "VK Ads (myTarget)", "реклама", [b"Lcom/my/target/"]),
    ("unity-ads", "Unity Ads", "реклама", [b"Lcom/unity3d/ads/"]),
    ("applovin", "AppLovin", "реклама", [b"Lcom/applovin/"]),
    ("gp-billing", "Google Play Billing", "платежи", [b"Lcom/android/billingclient/"]),
    ("rustore-sdk", "RuStore SDK (платежи, отзывы, обновления)", "платежи", [b"Lru/rustore/sdk/"]),
    ("revenuecat", "RevenueCat", "платежи", [b"Lcom/revenuecat/"]),
    ("gp-review", "Google Play In-App Review", "вовлечение", [b"Lcom/google/android/play/core/review/"]),
    ("gp-update", "Google Play In-App Updates", "вовлечение", [b"Lcom/google/android/play/core/appupdate/"]),
    ("huawei-hms", "Huawei HMS Core", "платформа", [b"Lcom/huawei/hms/"]),
    ("onesignal", "OneSignal", "пуши", [b"Lcom/onesignal/"]),
    ("okhttp", "OkHttp", "сеть", [b"Lokhttp3/"]),
    ("retrofit", "Retrofit", "сеть", [b"Lretrofit2/"]),
    ("room", "Room", "хранение", [b"Landroidx/room/"]),
    ("workmanager", "WorkManager", "фоновая работа", [b"Landroidx/work/"]),
    ("compose", "Jetpack Compose", "интерфейс", [b"Landroidx/compose/"]),
    ("media3", "AndroidX Media3 / ExoPlayer", "медиа", [b"Landroidx/media3/", b"Lcom/google/android/exoplayer2/"]),
    ("onnxruntime", "ONNX Runtime", "ML", [b"Lai/onnxruntime/"]),
    ("tflite", "TensorFlow Lite", "ML", [b"Lorg/tensorflow/lite/"]),
    ("mlkit", "Google ML Kit", "ML", [b"Lcom/google/mlkit/"]),
    ("vosk", "Vosk", "распознавание речи", [b"Lorg/vosk/"]),
    ("sherpa-onnx", "sherpa-onnx", "распознавание речи", [b"Lcom/k2fsa/sherpa/"]),
    ("react-native", "React Native", "фреймворк", [b"Lcom/facebook/react/"]),
    ("expo", "Expo", "фреймворк", [b"Lexpo/modules/"]),
    ("flutter", "Flutter", "фреймворк", [b"Lio/flutter/"]),
    ("kotlin", "Kotlin", "язык", [b"Lkotlin/"]),
]
NATIVE_HINTS = [(r"libflutter\.so", "Flutter"), (r"libhermes", "Hermes (React Native)"), (r"libreactnative", "React Native"),
                (r"libsentry", "Sentry (native)"), (r"libonnxruntime", "ONNX Runtime"), (r"libtensorflowlite", "TensorFlow Lite"),
                (r"whisper", "whisper.cpp / Whisper"), (r"libvosk", "Vosk"), (r"sherpa", "sherpa-onnx"), (r"libsqlcipher", "SQLCipher"),
                (r"libmmkv", "MMKV"), (r"librealm", "Realm"), (r"libunity", "Unity"), (r"libgodot", "Godot"), (r"libcrashlytics", "Crashlytics NDK"),
                (r"ggml|llama", "ggml / llama.cpp"), (r"libopus", "Opus"), (r"libffmpeg|libavcodec", "FFmpeg")]
AI_WORDS = ["openai", "whisper", "gpt-4", "gpt-3.5", "gpt-4o", "chatgpt", "gemini", "anthropic", "claude", "deepgram", "assemblyai",
            "speechkit", "salutespeech", "gigachat", "yandexgpt", "elevenlabs", "huggingface", "ollama", "vosk", "sherpa"]
SECRET_KEY_RE = re.compile(r"key|token|secret|passw|pwd|dsn|auth|credential|private|signature|salt", re.I)
SECRET_VAL_RE = re.compile(r"^(?:AIza[0-9A-Za-z_-]{20,}|sk-[A-Za-z0-9_-]{16,}|[A-Za-z0-9+/_-]{32,}={0,2}|https?://[^@\s]+@[^\s]+)$")
NOISE_DOMAINS = re.compile(r"(?:schemas\.android\.com|www\.w3\.org|ns\.adobe\.com|xmlpull\.org|apache\.org|json-schema\.org|"
                           r"purl\.org|example\.(?:com|org)|localhost|xml\.org|java\.sun\.com|schema\.org)$", re.I)


# ---------------------------------------------------------------- aapt2
def find_aapt2():
    p = shutil.which("aapt2")
    if p:
        return p
    roots = [os.environ.get("ANDROID_HOME"), os.environ.get("ANDROID_SDK_ROOT"), str(Path.home() / "Library/Android/sdk"),
             str(Path.home() / "Android/Sdk")]
    cands = []
    for r in roots:
        if r:
            cands += glob.glob(os.path.join(r, "build-tools", "*", "aapt2"))
    return sorted(cands)[-1] if cands else None


def aapt2_badging(aapt2, apk):
    try:
        r = subprocess.run([aapt2, "dump", "badging", str(apk)], capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.TimeoutExpired) as e:
        return None, str(e)[:160]
    if r.returncode != 0:
        return None, (r.stderr or r.stdout).strip()[:200]
    d = {"permissions": [], "locales": [], "labels": {}}
    for line in r.stdout.splitlines():
        if line.startswith("package:"):
            for k, v in re.findall(r"(\w+)='([^']*)'", line):
                d[k] = v
        elif line.startswith(("sdkVersion:", "minSdkVersion:", "targetSdkVersion:")):
            k, v = line.split(":", 1)
            d["sdkVersion" if k == "minSdkVersion" else k] = v.strip("'")
        elif line.startswith("uses-permission:"):
            m = re.search(r"name='([^']+)'", line)
            if m:
                d["permissions"].append(m.group(1))
        elif line.startswith("application-label"):
            m = re.match(r"application-label(?:-([\w-]+))?:'(.*)'", line)
            if m:
                d["labels"][m.group(1) or ""] = m.group(2)
        elif line.startswith("locales:"):
            d["locales"] = [x.strip("'") for x in line.split(":", 1)[1].split() if x.strip("'") not in ("--_--",)]
        elif line.startswith("native-code:"):
            d["native_code"] = [x.strip("'") for x in line.split(":", 1)[1].split()]
    return d, None


# ---------------------------------------------------------------- разбор APK
def _short(name):
    return name.rsplit(".", 1)[-1] if name.startswith("android.permission.") else name


def manifest_info(elems, resolve):
    m = {"package": None, "version_code": None, "version_name": None, "min_sdk": None, "target_sdk": None, "compile_sdk": None,
         "label": None, "permissions": [], "features": [], "components": {}, "launcher": None, "intent_filters": [], "deep_links": [],
         "exported_unprotected": [], "flags": {}}
    stack = []
    comp = None
    for e in elems:
        stack = stack[:e["depth"]] + [e["tag"]]
        a, tag = e["attrs"], e["tag"]
        if tag == "manifest":
            m["package"] = a.get("package")
            m["version_code"] = a.get("versionCode")
            m["version_name"] = resolve(a.get("versionName"))
            m["compile_sdk"] = a.get("compileSdkVersion") or a.get("platformBuildVersionCode")
        elif tag == "uses-sdk":
            m["min_sdk"] = a.get("minSdkVersion")
            m["target_sdk"] = a.get("targetSdkVersion")
        elif tag in ("uses-permission", "uses-permission-sdk-23") and a.get("name"):
            n = str(a["name"])
            if not any(p["name"] == n for p in m["permissions"]):
                short = n.rsplit(".", 1)[-1]
                m["permissions"].append({"name": n, "dangerous": n.startswith("android.permission.") and short in DANGEROUS,
                                         "special": n.startswith("android.permission.") and short in SPECIAL,
                                         "max_sdk": a.get("maxSdkVersion")})
        elif tag == "uses-feature" and a.get("name"):
            m["features"].append({"name": a["name"], "required": a.get("required", True) is not False})
        elif tag == "application":
            m["label"] = resolve(a.get("label"))
            if isinstance(a.get("label"), str) and a["label"].startswith("@0x"):
                m["label_ref"] = a["label"]
            for k in ("allowBackup", "usesCleartextTraffic", "debuggable", "largeHeap", "networkSecurityConfig", "requestLegacyExternalStorage",
                      "extractNativeLibs", "hardwareAccelerated"):
                if k in a:
                    m["flags"][k] = a[k]
            if a.get("name"):
                m["flags"]["application_class"] = a["name"]
        elif tag in ("activity", "activity-alias", "service", "receiver", "provider"):
            kind = "activity" if tag == "activity-alias" else tag
            name = a.get("name") or a.get("targetActivity")
            comp = {"kind": kind, "name": name, "exported": a.get("exported"), "permission": a.get("permission"), "filters": 0}
            m["components"].setdefault(kind, []).append(comp)
        elif tag == "intent-filter" and comp is not None and len(stack) >= 2 and stack[-2] in ("activity", "activity-alias", "service", "receiver"):
            comp["filters"] += 1
            m["intent_filters"].append({"component": comp["name"], "kind": comp["kind"], "actions": [], "categories": [], "data": []})
        elif tag in ("action", "category", "data") and m["intent_filters"] and len(stack) >= 2 and stack[-2] == "intent-filter":
            f = m["intent_filters"][-1]
            if tag == "action" and a.get("name"):
                f["actions"].append(a["name"])
            elif tag == "category" and a.get("name"):
                f["categories"].append(a["name"])
            elif tag == "data":
                f["data"].append({k: a[k] for k in ("scheme", "host", "path", "pathPrefix", "pathPattern", "mimeType") if k in a})
    for f in m["intent_filters"]:
        if "android.intent.action.MAIN" in f["actions"] and "android.intent.category.LAUNCHER" in f["categories"] and not m["launcher"]:
            m["launcher"] = f["component"]
        if "android.intent.action.VIEW" in f["actions"] and "android.intent.category.BROWSABLE" in f["categories"]:
            for d in f["data"]:
                if d.get("scheme"):
                    link = "%s://%s%s" % (d["scheme"], d.get("host", ""), d.get("path") or d.get("pathPrefix") or "")
                    if link not in m["deep_links"]:
                        m["deep_links"].append(link)
    for kind, items in m["components"].items():
        for c in items:
            exported = c["exported"] if c["exported"] is not None else (c["filters"] > 0 and (m["target_sdk"] or 0) < 31)
            if exported is True and not c["permission"] and kind != "activity" and c["name"]:
                m["exported_unprotected"].append("%s %s" % (kind, c["name"]))
    m["component_counts"] = {k: len(v) for k, v in m["components"].items()}
    m["components"] = {k: [c["name"] for c in v][:60] for k, v in m["components"].items()}
    return m


def _redact(obj, depth=0):
    """JSON-конфиг → копия с ключами и безопасными значениями; похожее на секреты — «<скрыто>»; глубина ≤ 3."""
    if depth > 3:
        return "…"
    if isinstance(obj, dict):
        return {k: ("<скрыто>" if SECRET_KEY_RE.search(str(k)) and not isinstance(v, (dict, list, bool)) else _redact(v, depth + 1))
                for k, v in list(obj.items())[:60]}
    if isinstance(obj, list):
        return [_redact(x, depth + 1) for x in obj[:20]]
    if isinstance(obj, str):
        return "<скрыто>" if SECRET_VAL_RE.match(obj.strip()) else obj[:200]
    return obj


def _domains(blob, limit=40):
    c = Counter()
    for m in re.finditer(rb"https?://([A-Za-z0-9][A-Za-z0-9.-]{2,80}\.[A-Za-z]{2,12})", blob):
        d = m.group(1).decode("ascii", "replace").lower().rstrip(".")
        if not NOISE_DOMAINS.search(d):
            c[d] += 1
    return [{"domain": d, "count": n} for d, n in c.most_common(limit)]


def scan_apk(path, aapt2=None, max_dex_mb=200):
    path = Path(path)
    res = {"file": str(path), "name": path.name, "size_bytes": path.stat().st_size, "sha256": None, "kind": path.suffix.lower().lstrip("."),
           "tools": ["python"], "manifest": None, "label": None, "label_locales": [], "locales": [], "abis": [], "native_libs": [], "native_hints": [],
           "frameworks": [], "sdks": [], "ai_keywords": {}, "domains": [], "assets": {}, "libraries": [], "strings": {},
           "signals": [], "limitations": [], "warnings": []}
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    res["sha256"] = h.hexdigest()
    try:
        z = zipfile.ZipFile(path)
    except zipfile.BadZipFile as e:
        res["warnings"].append("не zip-архив: %s" % e)
        return res
    names = z.namelist()
    aab = "base/manifest/AndroidManifest.xml" in names
    res["entries"] = len(names)
    # ресурсы
    gstrings, values, locales = [], {}, set()
    arsc_name = "resources.arsc" if "resources.arsc" in names else None
    if arsc_name:
        try:
            gstrings, values, locales = parse_arsc(z.read(arsc_name))
        except (ValueError, struct.error, IndexError) as e:
            res["warnings"].append("resources.arsc не разобран: %s" % str(e)[:120])
    elif aab:
        res["limitations"].append("AAB: ресурсы и манифест в protobuf — не разбираются; соберите APK (bundletool) для полного разбора")

    def resolve(v):
        if isinstance(v, str) and v.startswith("@0x"):
            rid = int(v[1:], 16)
            vals = values.get(rid) or {}
            return vals.get("") or vals.get("en") or (next(iter(vals.values())) if vals else v)
        return v

    if "AndroidManifest.xml" in names and not aab:
        try:
            res["manifest"] = manifest_info(parse_axml(z.read("AndroidManifest.xml")), resolve)
            res["label"] = res["manifest"].get("label")
        except (ValueError, struct.error, IndexError) as e:
            res["warnings"].append("AndroidManifest.xml не разобран: %s" % str(e)[:120])
    res["locales"] = sorted(locales)
    ref = (res["manifest"] or {}).get("label_ref")
    if ref and values.get(int(ref[1:], 16)):
        res["label_locales"] = sorted(k or "default" for k in values[int(ref[1:], 16)])
        res["label_translations"] = {k or "default": v for k, v in values[int(ref[1:], 16)].items()}
    if gstrings:
        cyr = sum(1 for s in gstrings if re.search(r"[А-Яа-яЁё]", s))
        res["strings"] = {"count": len(gstrings), "cyrillic": cyr, "cyrillic_share": round(cyr / len(gstrings), 3)}
    # aapt2 — сверка и названия
    if aapt2 and not aab:
        b, err = aapt2_badging(aapt2, path)
        if b:
            res["tools"].append("aapt2")
            mf = res["manifest"] or {}
            if b.get("labels"):
                res["label"] = b["labels"].get("") or next(iter(b["labels"].values()))
            if b.get("locales"):
                res["locales"] = sorted(set(res["locales"]) | set(b["locales"]))
            diffs = []
            for k_m, k_a in (("package", "name"), ("version_name", "versionName"), ("target_sdk", "targetSdkVersion"), ("min_sdk", "sdkVersion")):
                if mf.get(k_m) is not None and b.get(k_a) and str(mf.get(k_m)) != str(b.get(k_a)):
                    diffs.append("%s: python %s ≠ aapt2 %s" % (k_m, mf.get(k_m), b.get(k_a)))
            if diffs:
                res["warnings"].append("расхождение с aapt2: " + "; ".join(diffs))
            res["aapt2"] = {k: b.get(k) for k in ("name", "versionCode", "versionName", "sdkVersion", "targetSdkVersion", "native_code")}
        else:
            res["warnings"].append("aapt2 не сработал: %s" % err)
    # нативные библиотеки
    libs = [n for n in names if re.match(r"(?:base/)?lib/[^/]+/[^/]+\.so$", n)]
    res["abis"] = sorted({n.split("/")[-2] for n in libs})
    res["native_libs"] = sorted({n.rsplit("/", 1)[-1] for n in libs})
    res["native_hints"] = sorted({title for rx, title in NATIVE_HINTS for lib in res["native_libs"] if re.search(rx, lib, re.I)})
    # dex: SDK по сигнатурам, ключевые слова, домены
    dex_names = [n for n in names if re.match(r"(?:base/dex/)?classes\d*\.dex$", n)]
    budget = max_dex_mb * 1024 * 1024
    found_sdk, ai, dom_blob = {}, Counter(), []
    read = 0
    for dn in dex_names:
        info = z.getinfo(dn)
        if read + info.file_size > budget:
            res["limitations"].append("dex-файлы сверх %d МБ не читались (%s и далее)" % (max_dex_mb, dn))
            break
        data = z.read(dn)
        read += len(data)
        for sid, title, cat, sigs in SDKS:
            if sid not in found_sdk and any(s in data for s in sigs):
                found_sdk[sid] = {"id": sid, "name": title, "category": cat, "evidence": dn}
        low = data.lower()
        for w in AI_WORDS:
            n = low.count(w.encode())
            if n:
                ai[w] += n
        dom_blob.append(data)
    res["dex"] = {"files": len(dex_names), "bytes_read": read}
    # ассеты и бандлы
    assets = [n for n in names if n.startswith(("assets/", "base/assets/"))]
    configs = []
    for n in assets:
        info = z.getinfo(n)
        low_n = n.lower()
        if (low_n.endswith((".json", ".config", ".cfg", ".plist", ".properties", ".yaml", ".yml")) or low_n.endswith("app.config")) \
                and info.file_size <= 200_000 and len(configs) < 30:
            raw = z.read(n)
            item = {"path": n, "size": info.file_size}
            try:
                obj = json.loads(raw.decode("utf-8", errors="replace"))
                item["keys"] = list(obj.keys())[:60] if isinstance(obj, dict) else "список из %d" % len(obj) if isinstance(obj, list) else type(obj).__name__
                item["content"] = _redact(obj)
            except ValueError:
                item["text_head"] = "<не JSON: %d байт>" % info.file_size
            configs.append(item)
            lowb = raw.lower()
            for w in AI_WORDS:
                c = lowb.count(w.encode())
                if c:
                    ai[w] += c
            dom_blob.append(raw)
        elif re.search(r"(?:index\.android\.bundle|\.bundle|\.js)$", low_n) and info.file_size <= 40_000_000:
            raw = z.read(n)
            if "react-native" not in found_sdk and low_n.endswith("index.android.bundle"):
                found_sdk["react-native"] = {"id": "react-native", "name": "React Native", "category": "фреймворк", "evidence": n}
            lowb = raw.lower()
            for w in AI_WORDS:
                c = lowb.count(w.encode())
                if c:
                    ai[w] += c
            dom_blob.append(raw)
    if any(n.startswith("assets/flutter_assets/") for n in assets) and "flutter" not in found_sdk:
        found_sdk["flutter"] = {"id": "flutter", "name": "Flutter", "category": "фреймворк", "evidence": "assets/flutter_assets/"}
    big = sorted(((z.getinfo(n).file_size, n) for n in assets), reverse=True)[:10]
    res["assets"] = {"count": len(assets), "configs": configs, "largest": [{"path": n, "size": s} for s, n in big]}
    if gstrings:
        dom_blob.append("\n".join(gstrings).encode("utf-8", "replace"))
    res["domains"] = _domains(b"\n".join(dom_blob))
    res["sdks"] = sorted(found_sdk.values(), key=lambda x: (x["category"], x["id"]))
    res["frameworks"] = sorted({x["name"] for x in res["sdks"] if x["category"] in ("фреймворк",)} |
                               ({"Jetpack Compose"} if "compose" in found_sdk else set()) | ({"Kotlin"} if "kotlin" in found_sdk else set()))
    res["ai_keywords"] = dict(ai.most_common())
    # версии библиотек
    libsv = []
    for n in names:
        if n.startswith("META-INF/") and n.endswith(".version") and len(libsv) < 300:
            libsv.append({"lib": n[len("META-INF/"):-len(".version")], "version": z.read(n).decode("utf-8", "replace").strip()[:40]})
        elif re.match(r"^[\w.-]+\.properties$", n) and len(libsv) < 300:
            txt = z.read(n).decode("utf-8", "replace")
            m = re.search(r"^version=(\S+)", txt, re.M)
            if m:
                libsv.append({"lib": n[:-len(".properties")], "version": m.group(1)})
    res["libraries"] = libsv
    res["signals"] = signals(res)
    res["limitations"].append("статический разбор: поведение, экраны и скорость не проверялись (обход на эмуляторе — android-qa-audit)")
    return res


def signals(r):
    """Эвристики для стратегии и качества — «сигнал, проверить», не факт о дефекте."""
    m = r.get("manifest") or {}
    perms = {p["name"].rsplit(".", 1)[-1] for p in m.get("permissions") or []}
    sdk_ids = {s["id"] for s in r.get("sdks") or []}
    out = []
    t = m.get("target_sdk")
    if isinstance(t, int) and t < 34:
        out.append({"id": "old-target-sdk", "level": "warn", "text": "targetSdk %d < 34: новые версии в Google Play требуют актуальный "
                    "targetSdk (порог растёт ежегодно) — проверить план обновления" % t})
    if isinstance(t, int) and t >= 33 and "POST_NOTIFICATIONS" not in perms and ("firebase-messaging" in sdk_ids or "onesignal" in sdk_ids):
        out.append({"id": "no-post-notifications", "level": "warn", "text": "есть пуш-SDK, но нет POST_NOTIFICATIONS при targetSdk ≥ 33 — "
                    "уведомления на Android 13+ не покажутся"})
    alarmish = any("alarm" in str(c).lower() or "remind" in str(c).lower() for c in (m.get("components") or {}).get("receiver", []))
    if ("RECEIVE_BOOT_COMPLETED" in perms or alarmish) and not ({"SCHEDULE_EXACT_ALARM", "USE_EXACT_ALARM"} & perms):
        out.append({"id": "no-exact-alarm", "level": "info", "text": "напоминания/перезапуск после загрузки без SCHEDULE_EXACT_ALARM/"
                    "USE_EXACT_ALARM — на Android 12+ напоминания могут запаздывать (проверить)"})
    fl = m.get("flags") or {}
    if fl.get("usesCleartextTraffic") is True:
        out.append({"id": "cleartext", "level": "warn", "text": "usesCleartextTraffic=true — разрешён незашифрованный HTTP"})
    if fl.get("debuggable") is True:
        out.append({"id": "debuggable", "level": "error", "text": "debuggable=true в сборке — нельзя для публикации"})
    if fl.get("allowBackup") is True:
        out.append({"id": "allow-backup", "level": "info", "text": "allowBackup=true — данные приложения попадают в резервные копии (проверить, "
                    "нет ли там чувствительного)"})
    if m.get("exported_unprotected"):
        out.append({"id": "exported", "level": "info", "text": "экспортированные компоненты без разрешения: %d (%s)" % (
            len(m["exported_unprotected"]), ", ".join(m["exported_unprotected"][:3]))})
    dang = [p["name"].rsplit(".", 1)[-1] for p in m.get("permissions") or [] if p.get("dangerous")]
    if dang:
        out.append({"id": "dangerous-permissions", "level": "info", "text": "опасные разрешения: %s — объяснение в интерфейсе и в политике "
                    "конфиденциальности" % ", ".join(sorted(dang))})
    ai = r.get("ai_keywords") or {}
    cloud = [w for w in ("openai", "gpt-4", "gpt-4o", "gpt-3.5", "chatgpt", "gemini", "anthropic", "claude", "deepgram", "assemblyai",
                         "gigachat", "yandexgpt", "speechkit", "salutespeech", "elevenlabs") if ai.get(w)]
    if cloud:
        out.append({"id": "cloud-ai", "level": "info", "text": "в коде/бандле упоминаются облачные ИИ-сервисы: %s — проверить, используются ли "
                    "(данные пользователя за рубеж, стоимость, заявления «офлайн»)" % ", ".join(cloud)})
    if not (r.get("locales") or []) or r.get("locales") == ["en"]:
        pass
    return out


def collect_targets(out, paths):
    if paths:
        return [Path(p).expanduser().resolve() for p in paths]
    found = []
    try:
        cfg = json.loads((Path(out) / "build" / "run-config.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        cfg = {}
    repo = Path((cfg.get("repo") or {}).get("path") or ".").expanduser()      # FB-017: путь с «~» (--portable-config)
    for rel in ((cfg.get("sources") or {}).get("external") or {}).get("apk") or []:
        p = (repo / rel) if not Path(rel).is_absolute() else Path(rel)
        if p.is_file():
            found.append(p.resolve())
    if not found and repo.is_dir():
        for p in list(repo.glob("*.apk")) + list(repo.glob("*/*.apk")) + list(repo.glob("*/*/*.apk")):
            found.append(p.resolve())
    return sorted(set(found))


def render_md(doc):
    L = ["# Разбор APK (статический)", "", "Собрано `app_scan.py` %s без установки приложения. Подробно — `data/app-scan.json`. "
         "Сигналы — эвристики «проверить», не подтверждённые дефекты." % doc["generated"][:10], ""]
    for a in doc["apps"]:
        m = a.get("manifest") or {}
        L += ["## %s — %s" % (a["name"], a.get("label") or m.get("package") or "?"), "",
              "- Пакет: `%s`, версия %s (code %s), minSdk %s, targetSdk %s; размер %.1f МБ; инструменты: %s." % (
                  m.get("package"), m.get("version_name"), m.get("version_code"), m.get("min_sdk"), m.get("target_sdk"),
                  a["size_bytes"] / 1048576, ", ".join(a["tools"])),
              "- Название переведено на: %s; локалей строк в ресурсах (вместе с библиотеками androidx/Google): %d; доля строк на "
              "кириллице: %s." % (", ".join(a.get("label_locales") or []) or "—", len(a["locales"]),
                                  (a.get("strings") or {}).get("cyrillic_share", "—")),
              "- Разрешения (%d): %s." % (len(m.get("permissions") or []), (", ".join(
                  ("**%s**" % _short(p["name"])) if p["dangerous"] else _short(p["name"]) for p in m.get("permissions") or []
                  if p["name"].startswith("android.permission.")) or "нет") + (" и ещё %d несистемных (бейджи лаунчеров, push)" % sum(
                      1 for p in m.get("permissions") or [] if not p["name"].startswith("android.permission.")) if any(
                      not p["name"].startswith("android.permission.") for p in m.get("permissions") or []) else "")),
              "- Фреймворки: %s; ABI: %s; нативные: %s." % (", ".join(a["frameworks"]) or "—", ", ".join(a["abis"]) or "—",
                                                           ", ".join(a["native_hints"]) or "—"),
              "- SDK третьих сторон: %s." % ("; ".join("%s (%s)" % (s["name"], s["category"]) for s in a["sdks"]
                                                         if s["category"] not in ("язык", "сеть", "хранение")) or "не найдено"),
              "- Глубокие ссылки: %s." % (", ".join(m.get("deep_links") or []) or "нет"),
              "- Ключевые слова ИИ/ASR: %s." % (", ".join("%s ×%d" % kv for kv in list(a["ai_keywords"].items())[:10]) or "нет"),
              "- Домены (топ-10): %s." % (", ".join(d["domain"] for d in a["domains"][:10]) or "—"), ""]
        if a["signals"]:
            L += ["Сигналы:", ""] + ["- [%s] %s" % (s["level"], s["text"]) for s in a["signals"]] + [""]
        if a["limitations"] or a["warnings"]:
            L += ["Ограничения: " + "; ".join(a["limitations"] + a["warnings"]), ""]
    return "\n".join(L) + "\n"


def _perm_brief(perms):
    """Разрешения кратко: системные android.permission.* по именам, прочие (бейджи лаунчеров, push) — числом."""
    sysp = [_short(p["name"]) for p in perms if p["name"].startswith("android.permission.")]
    other = len(perms) - len(sysp)
    return (", ".join(sysp) or "нет") + (" и ещё %d несистемных" % other if other else "")


def inventory_lines(out):
    """Строки «что уже есть» для facts_scaffold в режиме external: APK (data/app-scan.json) и магазины (data/store-stats.json)."""
    out = Path(out)
    L = ["Внешний продукт: кода нет (product.mode=external) — инвентарь по APK, карточкам магазинов, сайту и обходу приложения.", ""]
    try:
        doc = json.loads((out / "data" / "app-scan.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        doc = None
    for a in (doc or {}).get("apps") or []:
        m = a.get("manifest") or {}
        L.append("APK `%s` [факт: data/app-scan.json]: %s %s, targetSdk %s; SDK: %s; глубокие ссылки: %s; разрешения: %s." % (
            a.get("name"), m.get("package"), m.get("version_name"), m.get("target_sdk"),
            ", ".join(s["name"] for s in a.get("sdks") or [] if s.get("category") not in ("язык", "сеть", "хранение")) or "—",
            ", ".join(m.get("deep_links") or []) or "нет", _perm_brief(m.get("permissions") or [])))
    try:
        st = json.loads((out / "data" / "store-stats.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        st = None
    for s in (st or {}).get("stores") or []:
        wn = ((s.get("fields") or {}).get("whats_new") or {}).get("value")
        if wn:
            L.append("«Что нового» в %s [факт: data/store-stats.json]: %s" % (s.get("store"), str(wn)[:300]))
    if len(L) == 2:
        L.append("_нет данных_ (нет data/app-scan.json и data/store-stats.json — запустите app_scan.py и store_stats.py).")
    L.append("")
    return L


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("out", help="папка прогона <OUT>")
    ap.add_argument("apk", nargs="*", help="пути к APK/AAB (иначе — из run-config sources.external.apk)")
    ap.add_argument("--tool", choices=["auto", "python", "aapt2"], default="auto")
    ap.add_argument("--max-dex-mb", type=int, default=200, help="сколько МБ dex читать (по умолчанию 200)")
    ap.add_argument("--stdout", action="store_true")
    a = ap.parse_args(argv)
    out = Path(a.out).expanduser().resolve()
    targets = collect_targets(out, a.apk)
    if not targets:
        print("ошибка: APK не найдены — передайте пути или добавьте sources.external.apk в run-config", file=sys.stderr)
        return 2
    aapt2 = None if a.tool == "python" else find_aapt2()
    if a.tool == "aapt2" and not aapt2:
        print("ошибка: aapt2 не найден (PATH, $ANDROID_HOME/build-tools)", file=sys.stderr)
        return 2
    apps = []
    for t in targets:
        if not t.is_file():
            print("предупреждение: нет файла %s" % t, file=sys.stderr)
            continue
        apps.append(scan_apk(t, aapt2, a.max_dex_mb))
    doc = {"generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "tool": "app_scan.py", "aapt2": aapt2,
           "apps": apps, "limitations": ["без установки и запуска: экраны, скорость, сеть и поведение не проверялись",
                                          "SDK — по сигнатурам классов в dex; обфускация (R8) может скрыть часть библиотек"]}
    if a.stdout:
        print(json.dumps(doc, ensure_ascii=False, indent=2))
        return 0
    (out / "data").mkdir(parents=True, exist_ok=True)
    (out / "research").mkdir(parents=True, exist_ok=True)
    (out / "data" / "app-scan.json").write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "research" / "app-scan.md").write_text(render_md(doc), encoding="utf-8")
    for x in apps:
        m = x.get("manifest") or {}
        print("app_scan: %s — %s %s, разрешений %d, SDK %d, сигналов %d%s" % (x["name"], m.get("package"), m.get("version_name"),
                                                                           len(m.get("permissions") or []), len(x["sdks"]), len(x["signals"]),
                                                                           ("; " + "; ".join(x["warnings"])) if x["warnings"] else ""))
    print("→ %s\n→ %s" % (out / "data" / "app-scan.json", out / "research" / "app-scan.md"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
