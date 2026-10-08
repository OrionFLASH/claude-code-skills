#!/usr/bin/env python3
"""What is inside the app under test: APK / split APKs / .apks / AAB / installed package (read-only).

  apk_info.py analyze PATH [PATH ...] [--out apk-info.json] [--copy-to <RUN_DIR>/apk] [--no-signature] [--summary]
      .apk (one or base + splits), .apks/.xapk (zip of APKs), .aab (needs bundletool: manifest only).
      aapt2 (or aapt) dump badging + xmltree of AndroidManifest.xml, apksigner verify --print-certs.
      --copy-to: copy the input files into the run folder with SHA256SUMS (never into the skills repository).
  apk_info.py installed --package PKG [--serial S] [--pull-to <RUN_DIR>/apk] [--out …] [--summary]
      dumpsys package + pm path from a device (read-only); --pull-to: adb pull the APKs, then analyze them.
  apk_info.py summary apk-info.json
      Markdown summary for the user (package, versions, SDK, permissions, launcher, ABI, risks).
  apk_info.py build-apks APP.aab --out <RUN_DIR>/apk/app.apks [--universal]
      bundletool build-apks (debug keystore of bundletool): to install an AAB on a test stand.

Output JSON: package, version_name, version_code, min_sdk, target_sdk, label, launchable_activity,
permissions (dangerous/special flags, maxSdk), abis, debuggable, allow_backup, uses_cleartext_traffic,
components (effective exported), deep_links, signature, risks (candidate findings for security-passive),
compat (host emulator ABI), recommended_apis.
Exit codes: 0 ok, 2 bad input, 3 tool missing.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path
from xml.etree import ElementTree

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import sdkutil as su  # noqa: E402

ANDROID_NS = "http://schemas.android.com/apk/res/android"
PLAY_MIN_TARGET = 35  # minimal targetSdk for Google Play updates at the time of writing; verify for your release date
DANGEROUS = {
    "READ_CALENDAR": "calendar", "WRITE_CALENDAR": "calendar", "CAMERA": "camera", "READ_CONTACTS": "contacts",
    "WRITE_CONTACTS": "contacts", "GET_ACCOUNTS": "contacts", "ACCESS_FINE_LOCATION": "location",
    "ACCESS_COARSE_LOCATION": "location", "ACCESS_BACKGROUND_LOCATION": "location", "RECORD_AUDIO": "microphone",
    "READ_PHONE_STATE": "phone", "READ_PHONE_NUMBERS": "phone", "CALL_PHONE": "phone", "ANSWER_PHONE_CALLS": "phone",
    "READ_CALL_LOG": "call-log", "WRITE_CALL_LOG": "call-log", "ADD_VOICEMAIL": "phone", "USE_SIP": "phone",
    "PROCESS_OUTGOING_CALLS": "call-log", "BODY_SENSORS": "sensors", "BODY_SENSORS_BACKGROUND": "sensors",
    "ACTIVITY_RECOGNITION": "activity", "SEND_SMS": "sms", "RECEIVE_SMS": "sms", "READ_SMS": "sms",
    "RECEIVE_WAP_PUSH": "sms", "RECEIVE_MMS": "sms", "READ_EXTERNAL_STORAGE": "storage",
    "WRITE_EXTERNAL_STORAGE": "storage", "ACCESS_MEDIA_LOCATION": "storage", "ACCEPT_HANDOVER": "phone",
    "BLUETOOTH_SCAN": "nearby", "BLUETOOTH_CONNECT": "nearby", "BLUETOOTH_ADVERTISE": "nearby",
    "UWB_RANGING": "nearby", "NEARBY_WIFI_DEVICES": "nearby", "POST_NOTIFICATIONS": "notifications",
    "READ_MEDIA_IMAGES": "media", "READ_MEDIA_VIDEO": "media", "READ_MEDIA_AUDIO": "media",
    "READ_MEDIA_VISUAL_USER_SELECTED": "media",
}
# Runtime permission introduced in API level N: below it the dialog does not exist.
RUNTIME_SINCE = {"POST_NOTIFICATIONS": 33, "NEARBY_WIFI_DEVICES": 33, "READ_MEDIA_IMAGES": 33, "READ_MEDIA_VIDEO": 33,
                 "READ_MEDIA_AUDIO": 33, "READ_MEDIA_VISUAL_USER_SELECTED": 34, "BLUETOOTH_SCAN": 31,
                 "BLUETOOTH_CONNECT": 31, "BLUETOOTH_ADVERTISE": 31, "UWB_RANGING": 31, "BODY_SENSORS_BACKGROUND": 33,
                 "ACCESS_BACKGROUND_LOCATION": 29, "ACTIVITY_RECOGNITION": 29, "ACCESS_MEDIA_LOCATION": 29,
                 "READ_PHONE_NUMBERS": 26, "ANSWER_PHONE_CALLS": 26}
SPECIAL = {"SYSTEM_ALERT_WINDOW", "WRITE_SETTINGS", "MANAGE_EXTERNAL_STORAGE", "REQUEST_INSTALL_PACKAGES",
           "SCHEDULE_EXACT_ALARM", "USE_EXACT_ALARM", "PACKAGE_USAGE_STATS", "BIND_ACCESSIBILITY_SERVICE",
           "QUERY_ALL_PACKAGES", "BIND_DEVICE_ADMIN", "REQUEST_IGNORE_BATTERY_OPTIMIZATIONS", "USE_FULL_SCREEN_INTENT",
           "MANAGE_OWN_CALLS", "BIND_NOTIFICATION_LISTENER_SERVICE", "READ_PRIVILEGED_PHONE_STATE"}
SPLIT_ABI = {"arm64_v8a": "arm64-v8a", "armeabi_v7a": "armeabi-v7a", "armeabi": "armeabi", "x86": "x86", "x86_64": "x86_64"}
JVM_NOISE = re.compile(r"^WARNING: (A restricted method|java\.lang\.System::|Use --enable-native-access|Restricted methods)")


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def short_perm(name):
    return name.rsplit(".", 1)[-1] if name.startswith("android.permission.") else name


# ---------- aapt2 / aapt parsing ----------

def parse_badging(text):
    d = {"permissions": [], "features_required": [], "features_optional": [], "abis": [], "alt_abis": [],
         "locales": [], "densities": [], "supports_screens": [], "debuggable": False, "split": None}
    for line in text.splitlines():
        if line.startswith("package:"):
            attrs = dict(re.findall(r"(\w+)='([^']*)'", line))
            d.update(package=attrs.get("name"), version_name=attrs.get("versionName"),
                     version_code=int(attrs["versionCode"]) if attrs.get("versionCode", "").isdigit() else attrs.get("versionCode"),
                     compile_sdk=su.parse_api(attrs.get("compileSdkVersion") or attrs.get("platformBuildVersionCode")),
                     split=attrs.get("split"))
        elif re.match(r"^(sdkVersion|minSdkVersion):'", line):
            d["min_sdk"] = su.parse_api(line.split("'")[1]) or line.split("'")[1]
        elif line.startswith("targetSdkVersion:'"):
            d["target_sdk"] = su.parse_api(line.split("'")[1]) or line.split("'")[1]
        elif re.match(r"^uses-permission(-sdk-23)?:", line):
            attrs = dict(re.findall(r"(\w+)='([^']*)'", line))
            name = attrs.get("name") or (re.findall(r"'([^']+)'", line) or [None])[0]
            if name:
                d["permissions"].append({"name": name, "max_sdk": int(attrs["maxSdkVersion"]) if attrs.get("maxSdkVersion", "").isdigit() else None,
                                         "sdk23_only": "-sdk-23" in line.split(":")[0]})
        elif line.startswith("application-label:'"):
            d.setdefault("label", line.split("'", 1)[1].rstrip("'"))
        elif line.startswith("application:"):
            m = re.search(r"label='([^']*)'", line)
            if m and not d.get("label"):
                d["label"] = m.group(1)
        elif line.startswith("launchable-activity:"):
            m = re.search(r"name='([^']*)'", line)
            d.setdefault("launchable_activity", m.group(1) if m else None)
        elif line.startswith("leanback-launchable-activity:"):
            m = re.search(r"name='([^']*)'", line)
            d["leanback_activity"] = m.group(1) if m else None
        elif line.startswith("native-code:"):
            d["abis"] = re.findall(r"'([^']+)'", line)
        elif line.startswith("alt-native-code:"):
            d["alt_abis"] = re.findall(r"'([^']+)'", line)
        elif line.strip() == "application-debuggable":
            d["debuggable"] = True
        elif re.match(r"^\s*uses-feature(-not-required)?:", line):
            m = re.search(r"name='([^']*)'", line)
            if m:
                d["features_optional" if "not-required" in line else "features_required"].append(m.group(1))
        elif line.startswith("locales:"):
            d["locales"] = [x for x in re.findall(r"'([^']+)'", line) if x != "--_--"]
        elif line.startswith("densities:"):
            d["densities"] = re.findall(r"'([^']+)'", line)
        elif line.startswith("supports-screens:"):
            d["supports_screens"] = re.findall(r"'([^']+)'", line)
    return d


def _attr_value(raw):
    raw = raw.strip()
    m = re.match(r'^"(.*)" \(Raw: ".*"\)$', raw) or re.match(r'^"(.*)"$', raw)
    if m:
        return m.group(1)
    m = re.match(r"^\(type 0x(\w+)\)0x([0-9a-f]+)$", raw, re.I)
    if m:
        t, v = int(m.group(1), 16), int(m.group(2), 16)
        return (v != 0) if t == 0x12 else v
    if raw in ("true", "false"):
        return raw == "true"
    if re.match(r"^-?\d+$", raw):
        return int(raw)
    if re.match(r"^0x[0-9a-f]+$", raw, re.I):
        return int(raw, 16)
    return raw


def parse_xmltree(text):
    """aapt2/aapt `dump xmltree` -> {'tag', 'attrs', 'children'} tree (root: the manifest element)."""
    root = {"tag": "#root", "attrs": {}, "children": [], "indent": -1}
    stack = [root]
    for line in text.splitlines():
        stripped = line.lstrip(" ")
        indent = len(line) - len(stripped)
        if stripped.startswith("E: "):
            tag = stripped[3:].split(" ", 1)[0]
            while stack[-1]["indent"] >= indent:
                stack.pop()
            node = {"tag": tag, "attrs": {}, "children": [], "indent": indent}
            stack[-1]["children"].append(node)
            stack.append(node)
        elif stripped.startswith("A: "):
            m = re.match(r"^A: (?:[^=(]*:)?([\w.-]+)(?:\(0x[0-9a-f]+\))?=(.*)$", stripped, re.I)
            if not m:
                continue
            while len(stack) > 1 and stack[-1]["indent"] >= indent:
                stack.pop()
            stack[-1]["attrs"][m.group(1)] = _attr_value(m.group(2))
    manifests = [c for c in root["children"] if c["tag"] == "manifest"]
    return manifests[0] if manifests else None


def parse_xml_manifest(text):
    """Plain XML manifest (bundletool dump manifest) -> the same tree as parse_xmltree."""
    def conv(el):
        attrs = {}
        for k, v in el.attrib.items():
            name = k.split("}", 1)[-1]
            attrs[name] = (v == "true") if v in ("true", "false") else (int(v) if re.match(r"^-?\d+$", v) else v)
        return {"tag": el.tag, "attrs": attrs, "children": [conv(c) for c in el]}
    return conv(ElementTree.fromstring(text))


def children(node, tag):
    return [c for c in (node or {}).get("children", []) if c["tag"] == tag]


def from_manifest(tree, info):
    """Fill info with manifest facts: application flags, components, deep links."""
    if not tree:
        return info
    a = tree["attrs"]

    def fill(key, value):
        if info.get(key) is None and value is not None:
            info[key] = value
    fill("package", a.get("package"))
    fill("version_name", a.get("versionName"))
    fill("version_code", a.get("versionCode"))
    for sdk in children(tree, "uses-sdk"):
        fill("min_sdk", sdk["attrs"].get("minSdkVersion"))
        fill("target_sdk", sdk["attrs"].get("targetSdkVersion"))
    if not info.get("permissions"):
        info["permissions"] = [{"name": p["attrs"].get("name"), "max_sdk": p["attrs"].get("maxSdkVersion"), "sdk23_only": False}
                               for p in children(tree, "uses-permission") + children(tree, "uses-permission-sdk-23")
                               if p["attrs"].get("name")]
    target = info.get("target_sdk") if isinstance(info.get("target_sdk"), int) else 0
    apps = children(tree, "application")
    app = apps[0]["attrs"] if apps else {}
    info["debuggable"] = bool(app.get("debuggable")) or bool(info.get("debuggable"))
    info["test_only"] = bool(app.get("testOnly"))
    info["allow_backup"] = app.get("allowBackup", True) if apps else None
    info["allow_backup_explicit"] = "allowBackup" in app
    info["backup_rules"] = bool(app.get("fullBackupContent") or app.get("dataExtractionRules"))
    info["network_security_config"] = app.get("networkSecurityConfig")
    if "usesCleartextTraffic" in app:
        info["uses_cleartext_traffic"], info["cleartext_explicit"] = bool(app["usesCleartextTraffic"]), True
    else:
        info["uses_cleartext_traffic"], info["cleartext_explicit"] = (target < 28), False
    info["supports_rtl"] = app.get("supportsRtl")
    info["large_heap"] = app.get("largeHeap")
    comps, links = [], []
    launcher = info.get("launchable_activity")
    for app_node in apps:
        for c in app_node["children"]:
            if c["tag"] not in ("activity", "activity-alias", "service", "receiver", "provider"):
                continue
            ca = c["attrs"]
            filters = []
            for f in children(c, "intent-filter"):
                acts = [x["attrs"].get("name") for x in children(f, "action")]
                cats = [x["attrs"].get("name") for x in children(f, "category")]
                datas = [{k: v for k, v in x["attrs"].items() if k in ("scheme", "host", "port", "path", "pathPrefix",
                                                                       "pathPattern", "pathAdvancedPattern", "mimeType")}
                         for x in children(f, "data")]
                filters.append({"actions": acts, "categories": cats, "data": datas, "auto_verify": bool(f["attrs"].get("autoVerify"))})
                if "android.intent.action.MAIN" in acts and "android.intent.category.LAUNCHER" in cats and not launcher:
                    launcher = ca.get("name")
                if c["tag"] in ("activity", "activity-alias") and "android.intent.action.VIEW" in acts:
                    schemes = [d["scheme"] for d in datas if d.get("scheme")] or []
                    hosts = [d["host"] for d in datas if d.get("host")] or [None]
                    paths = [d.get("path") or d.get("pathPrefix") or d.get("pathPattern") for d in datas
                             if d.get("path") or d.get("pathPrefix") or d.get("pathPattern")] or [""]
                    for s in schemes:
                        for h in hosts:
                            for p in paths:
                                links.append({"activity": ca.get("name"), "uri": f"{s}://{h or ''}{p or ''}",
                                              "scheme": s, "host": h, "path": p or "",
                                              "browsable": "android.intent.category.BROWSABLE" in cats,
                                              "auto_verify": bool(f["attrs"].get("autoVerify"))})
            if "exported" in ca:
                exported, explicit = bool(ca["exported"]), True
            elif c["tag"] == "provider":
                exported, explicit = (target and target < 17), False
            else:
                exported, explicit = bool(filters), False
            comps.append({"type": c["tag"], "name": ca.get("name") or ca.get("targetActivity"), "exported": bool(exported),
                          "exported_explicit": explicit, "permission": ca.get("permission") or ca.get("readPermission"),
                          "enabled": ca.get("enabled", True), "foreground_service_type": ca.get("foregroundServiceType"),
                          "authorities": ca.get("authorities"), "intent_filters": filters})
    info["launchable_activity"] = launcher
    info["components"] = comps
    info["deep_links"] = links
    return info


# ---------- tools ----------

def need(tool):
    p = su.tool_path(tool)
    return p


def aapt_dump(apk):
    """(badging_text, xmltree_text, tool_name)."""
    aapt2, aapt = need("aapt2"), need("aapt")
    if aapt2:
        c1, badging, e1 = su.run([aapt2, "dump", "badging", apk], timeout=120)
        c2, tree, e2 = su.run([aapt2, "dump", "xmltree", "--file", "AndroidManifest.xml", apk], timeout=120)
        if c1 == 0:
            return badging, tree if c2 == 0 else "", "aapt2"
        if not aapt:
            raise RuntimeError((e1 or badging).strip()[:300])
    if aapt:
        c1, badging, e1 = su.run([aapt, "dump", "badging", apk], timeout=120)
        c2, tree, _ = su.run([aapt, "dump", "xmltree", apk, "AndroidManifest.xml"], timeout=120)
        if c1 != 0:
            raise RuntimeError((e1 or badging).strip()[:300])
        return badging, tree if c2 == 0 else "", "aapt"
    raise FileNotFoundError("нет aapt2/aapt (build-tools): sdkmanager \"build-tools;35.0.0\"")


def signature(apk):
    tool = need("apksigner")
    if not tool:
        return {"checked": False, "error": "apksigner не найден (build-tools)"}
    code, out, err = su.run([tool, "verify", "--print-certs", "-v", apk], timeout=180)
    if code in (124, 126, 127):
        return {"checked": False, "error": f"apksigner не запустился ({err.strip()[:120]}); нужна Java 17+"}
    lines = [ln for ln in (out + "\n" + err).splitlines() if ln.strip() and not JVM_NOISE.match(ln)]
    text = "\n".join(lines)
    sig = {"checked": True, "verified": bool(re.search(r"^Verifies$", text, re.M)),
           "schemes": sorted(set(re.findall(r"Verified using (v[\d.]+) scheme[^:]*:\s*true", text))),
           "signers": [], "warnings": [ln[9:].strip() for ln in lines if ln.startswith("WARNING:")][:10]}
    seen = {}
    for ln in lines:
        m = re.match(r"^(?:Signer #?\d+|V[\d.]+ Signer):? certificate DN: (.+)$", ln)
        if m:
            dn = m.group(1).strip()
            if dn not in seen:
                seen[dn] = {"dn": dn, "debug": "CN=Android Debug" in dn}
                sig["signers"].append(seen[dn])
            last = seen[dn]
            continue
        m = re.search(r"certificate SHA-256 digest: ([0-9a-f]+)", ln)
        if m and sig["signers"] and "sha256" not in last:
            last["sha256"] = m.group(1)
    if code != 0 or "DOES NOT VERIFY" in text:
        sig["verified"] = False
        sig["error"] = next((ln for ln in lines if "ERROR" in ln or "DOES NOT VERIFY" in ln), text[:200])
    sig["debug_signed"] = any(x.get("debug") for x in sig["signers"])
    return sig


def bundletool_cmd():
    p = su.tool_path("bundletool")
    if p:
        return [p]
    jar = os.environ.get("BUNDLETOOL_JAR")
    java = shutil.which("java")
    if jar and Path(jar).is_file() and java:
        return [java, "-jar", jar]
    return None


# ---------- analysis ----------

def classify_permissions(perms, min_sdk):
    out = []
    for p in perms:
        short = short_perm(p["name"])
        group = DANGEROUS.get(short) if p["name"].startswith("android.permission.") else None
        out.append({**p, "short": short, "dangerous": bool(group), "group": group,
                    "special": short in SPECIAL, "runtime_since": RUNTIME_SINCE.get(short, 23) if group else None})
    return out


def risks_of(info):
    """Passive security observations (candidates for findings; the agent confirms and rates them)."""
    r = []
    add = lambda cid, sev, title, detail: r.append({"check_id": cid, "severity": sev, "title": title, "detail": detail})  # noqa: E731
    if info.get("debuggable"):
        add("sec.debuggable", "high", "android:debuggable=true", "отладочная сборка: в релизе недопустимо (run-as, отладчик)")
    if info.get("test_only"):
        add("sec.test-only", "medium", "android:testOnly=true", "ставится только с adb install -t; в магазин не попадёт")
    if info.get("allow_backup") and not info.get("backup_rules"):
        add("sec.allow-backup", "low", "allowBackup разрешён без правил" + ("" if info.get("allow_backup_explicit") else " (значение по умолчанию)"),
            "данные приложения попадают в резервную копию/перенос; проверить, нет ли токенов в SharedPreferences")
    if info.get("uses_cleartext_traffic"):
        add("sec.cleartext", "medium", "разрешён незашифрованный HTTP" + ("" if info.get("cleartext_explicit") else f" (по умолчанию для targetSdk {info.get('target_sdk')})"),
            "usesCleartextTraffic=true" + (f"; есть networkSecurityConfig {info['network_security_config']} — проверить домены" if info.get("network_security_config") else ""))
    sig = info.get("signature") or {}
    if sig.get("debug_signed"):
        add("sec.debug-signature", "medium", "подписан отладочным сертификатом (CN=Android Debug)", "для релиза нужна релизная подпись")
    if sig.get("checked") and sig.get("verified") is False:
        add("sec.signature-invalid", "high", "подпись APK не проходит проверку", sig.get("error") or "")
    launcher = info.get("launchable_activity")
    for c in info.get("components") or []:
        if c["exported"] and not c.get("permission") and c["name"] != launcher and c.get("enabled", True) is not False:
            add("sec.exported-component", "info", f"экспортирован без разрешения: {c['type']} {c['name']}",
                "кандидат: проверить, что компонент безопасно принимает внешние интенты (без активных атак)")
        if c["type"] == "provider" and c["exported"] and not c.get("permission"):
            r[-1]["severity"] = "low"
    t = info.get("target_sdk")
    if isinstance(t, int) and t < PLAY_MIN_TARGET:
        add("compat.target-sdk", "info", f"targetSdk {t} ниже {PLAY_MIN_TARGET}", "требование Google Play к targetSdk — сверить на дату релиза")
    special = [p["short"] for p in info.get("permissions") or [] if p.get("special")]
    if special:
        add("sec.special-permissions", "info", "особые разрешения: " + ", ".join(special), "проверить обоснование и запрос в настройках")
    return r


def compat_of(info):
    host = su.host_abi()
    abis = info.get("abis") or []
    note = "нет нативного кода — подходит любой ABI" if not abis else ""
    ok = True
    if abis and host not in abis:
        if host == "arm64-v8a" and not any(a.startswith("arm") for a in abis):
            ok, note = False, f"нативный код только {', '.join(abis)} — на эмуляторе {host} не установится (INSTALL_FAILED_NO_MATCHING_ABIS); нужен x86_64-хост или реальное устройство"
        elif host == "x86_64" and all(a.startswith("arm") for a in abis):
            note = "только ARM-код: на x86_64-образах API 30+ работает через трансляцию (медленнее), на старых — не установится"
        else:
            note = f"нативный код {', '.join(abis)}; хост {host} — проверить установку"
    return {"host_abi": host, "emulator_ok": ok, "note": note}


def recommended_apis(info):
    mn = info.get("min_sdk") if isinstance(info.get("min_sdk"), int) else None
    tg = info.get("target_sdk") if isinstance(info.get("target_sdk"), int) else None
    cands = [mn, 26, 29, 31, 33, 34, 35, tg]
    out = sorted({a for a in cands if a and (mn is None or a >= mn) and (tg is None or a <= max(tg, 35))})
    return {"min": mn, "target": tg, "suggested": out}


def analyze_apks(paths, check_sig=True):
    """Analyze base (+ split) APK files. Returns the info dict."""
    parsed = []
    for p in paths:
        badging, tree_text, tool = aapt_dump(str(p))
        b = parse_badging(badging)
        b["_path"], b["_tree"], b["_tool"] = str(p), tree_text, tool
        parsed.append(b)
    base = next((b for b in parsed if not b.get("split")), parsed[0])
    info = {k: v for k, v in base.items() if not k.startswith("_")}
    info["tool"] = base["_tool"]
    info["splits"] = [{"path": b["_path"], "split": b.get("split"), "abis": b.get("abis")} for b in parsed if b is not base]
    abis = set(info.get("abis") or [])
    for b in parsed:  # ABI of config splits (split='config.arm64_v8a') adds to the base
        abis |= set(b.get("abis") or [])
        tail = (b.get("split") or "").rsplit(".", 1)[-1]
        if tail in SPLIT_ABI:
            abis.add(SPLIT_ABI[tail])
    info["abis"] = sorted(abis)
    tree = parse_xmltree(base["_tree"]) if base["_tree"] else None
    from_manifest(tree, info)
    if check_sig:
        info["signature"] = signature(base["_path"])
    return info


def finish(info, sources):
    info["source"] = sources
    info["permissions"] = classify_permissions(info.get("permissions") or [], info.get("min_sdk"))
    info["dangerous_permissions"] = [p["short"] for p in info["permissions"] if p["dangerous"]]
    info["compat"] = compat_of(info)
    info["recommended_apis"] = recommended_apis(info)
    info["risks"] = risks_of(info)
    return info


def copy_inputs(paths, dest):
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    sums, copied = [], []
    for p in paths:
        p = Path(p)
        target = dest / p.name
        if target.resolve() != p.resolve():
            n = 2
            while target.exists() and sha256(target) != sha256(p):
                target = dest / f"{p.stem}-{n}{p.suffix}"
                n += 1
            if not target.exists():
                shutil.copy2(p, target)
        digest = sha256(target)
        sums.append(f"{digest}  {target.name}")
        copied.append({"file": target.name, "sha256": digest, "size_bytes": target.stat().st_size})
    old = (dest / "SHA256SUMS").read_text(encoding="utf-8").splitlines() if (dest / "SHA256SUMS").exists() else []
    (dest / "SHA256SUMS").write_text("\n".join(dict.fromkeys(old + sums)) + "\n", encoding="utf-8")
    return copied


def extract_zip_apks(path, workdir):
    out = []
    with zipfile.ZipFile(path) as z:
        for n in z.namelist():
            if n.lower().endswith(".apk") and not n.endswith("/"):
                target = Path(workdir) / Path(n).name  # basename only: no zip-slip
                with z.open(n) as src, open(target, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                out.append(target)
    universal = [p for p in out if p.name == "universal.apk"]
    if universal:
        return universal
    base = [p for p in out if p.name in ("base-master.apk", "base.apk")]
    # standalone/split sets: base + config splits for the host
    return (base + [p for p in out if p.name.startswith("base-") and p not in base]) if base else out


def cmd_analyze(a):
    paths = [Path(p).expanduser() for p in a.inputs]
    for p in paths:
        if not p.is_file():
            sys.stderr.write(f"apk_info: нет файла {p}\n")
            sys.exit(2)
    sources = {"type": None, "paths": [str(p) for p in paths],
               "files": [{"file": str(p), "sha256": sha256(p), "size_bytes": p.stat().st_size} for p in paths]}
    exts = {p.suffix.lower() for p in paths}
    try:
        if exts == {".aab"}:
            bt = bundletool_cmd()
            if not bt:
                sys.stderr.write("apk_info: для .aab нужен bundletool (PATH или BUNDLETOOL_JAR)\n")
                sys.exit(3)
            code, xml, err = su.run(bt + ["dump", "manifest", "--bundle", str(paths[0])], timeout=180)
            if code != 0:
                raise RuntimeError(err.strip()[:300])
            info = from_manifest(parse_xml_manifest(xml), {"permissions": []})
            info["tool"] = "bundletool"
            info["signature"] = {"checked": False, "error": "AAB подписывается при публикации; проверяется APK после build-apks"}
            sources["type"] = "aab"
        elif exts & {".apks", ".xapk", ".zip"}:
            with tempfile.TemporaryDirectory() as td:
                apks = extract_zip_apks(paths[0], td)
                if not apks:
                    raise RuntimeError("в архиве нет .apk")
                info = analyze_apks(apks, not a.no_signature)
                sources["type"] = "apks"
                sources["inner"] = [p.name for p in apks]
        else:
            info = analyze_apks(paths, not a.no_signature)
            sources["type"] = "apk" if len(paths) == 1 else "splits"
    except FileNotFoundError as ex:
        sys.stderr.write(f"apk_info: {ex}\n")
        sys.exit(3)
    except (RuntimeError, zipfile.BadZipFile, ElementTree.ParseError) as ex:
        sys.stderr.write(f"apk_info: не удалось разобрать: {ex}\n")
        sys.exit(2)
    if a.copy_to:
        sources["copies"] = copy_inputs(paths, a.copy_to)
        sources["copy_dir"] = str(Path(a.copy_to).resolve())
    info = finish(info, sources)
    emit(info, a)


def parse_dumpsys_package(text, pkg):
    info = {"package": pkg, "permissions": [], "granted": {}, "flags": []}
    sec = re.search(r"Package \[" + re.escape(pkg) + r"\][\s\S]*?(?=\n  Package \[|\n\S|\Z)", text)
    body = sec.group(0) if sec else text
    m = re.search(r"versionCode=(\d+)(?:\s+minSdk=(\d+))?(?:\s+targetSdk=(\d+))?", body)
    if m:
        info["version_code"] = int(m.group(1))
        info["min_sdk"] = int(m.group(2)) if m.group(2) else None
        info["target_sdk"] = int(m.group(3)) if m.group(3) else None
    m = re.search(r"versionName=(\S+)", body)
    info["version_name"] = m.group(1) if m else None
    m = re.search(r"^\s*flags=\[([^\]]*)\]", body, re.M)
    info["flags"] = m.group(1).split() if m else []
    info["debuggable"] = "DEBUGGABLE" in info["flags"]
    info["allow_backup"] = "ALLOW_BACKUP" in info["flags"]
    for key in ("primaryCpuAbi", "codePath", "firstInstallTime", "lastUpdateTime", "installerPackageName"):
        m = re.search(key + r"=([^\n]+)", body)
        info[key] = m.group(1).strip() if m else None
    info["abis"] = [info["primaryCpuAbi"]] if info.get("primaryCpuAbi") not in (None, "null") else []
    req = re.search(r"requested permissions:\n((?:\s{6,}\S.*\n)+)", body)
    if req:
        info["permissions"] = [{"name": ln.strip().split(":")[0], "max_sdk": None, "sdk23_only": False}
                               for ln in req.group(1).splitlines() if ln.strip()]
    for m in re.finditer(r"^\s+([\w.]+): granted=(true|false)", body, re.M):
        info["granted"][m.group(1)] = m.group(2) == "true"
    return info


def cmd_installed(a):
    serial = su.pick_serial(serial=a.serial)
    adb = su.Adb(serial)
    code, out, err = adb.shell("pm", "path", a.package, timeout=30)
    paths = [ln.split(":", 1)[1].strip() for ln in out.splitlines() if ln.startswith("package:")]
    if not paths:
        sys.stderr.write(f"apk_info: пакет {a.package} не установлен на {serial}\n")
        sys.exit(2)
    _, dump, _ = adb.shell("dumpsys", "package", a.package, timeout=60)
    info = parse_dumpsys_package(dump, a.package)
    sources = {"type": "installed", "serial": serial, "device_paths": paths}
    if a.pull_to:
        dest = Path(a.pull_to)
        dest.mkdir(parents=True, exist_ok=True)
        local = []
        for p in paths:
            name = Path(p).name if Path(p).name != "base.apk" else f"{a.package}-base.apk"
            target = dest / name
            c, o, e = adb.cmd("pull", p, str(target), timeout=300)
            if c != 0:
                sys.stderr.write(f"apk_info: adb pull {p}: {(e or o).strip()[:200]}\n")
                sys.exit(2)
            local.append(target)
        dev_info = info
        info = analyze_apks(local, not a.no_signature)
        info["granted"], info["device_flags"] = dev_info["granted"], dev_info["flags"]
        sources["copies"] = copy_inputs(local, dest)
        sources["copy_dir"] = str(dest.resolve())
    info = finish(info, sources)
    emit(info, a)


def emit(info, a):
    text = json.dumps(info, ensure_ascii=False, indent=1)
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(text + "\n", encoding="utf-8")
        print(f"apk_info: -> {a.out}")
    if a.summary or not a.out:
        print(summary(info) if a.summary else text)


def summary(info):
    sig = info.get("signature") or {}
    src = info.get("source") or {}
    perms = info.get("permissions") or []
    dang = [f"{p['short']}" + (f" (API {p['runtime_since']}+)" if p.get("runtime_since", 23) > 23 else "") +
            (f" (до API {p['max_sdk']})" if p.get("max_sdk") else "") for p in perms if p.get("dangerous")]
    rec = info.get("recommended_apis") or {}
    L = [f"## Приложение: {info.get('label') or '?'} (`{info.get('package')}`)", "",
         "| Что | Значение |", "|---|---|",
         f"| Версия | {info.get('version_name')} (code {info.get('version_code')}) |",
         f"| minSdk / targetSdk | {su.api_label(info.get('min_sdk') if isinstance(info.get('min_sdk'), int) else None)} / "
         f"{su.api_label(info.get('target_sdk') if isinstance(info.get('target_sdk'), int) else None)} |",
         f"| Источник | {src.get('type')}: {', '.join(Path(p).name for p in src.get('paths') or src.get('device_paths') or [])} |",
         f"| Стартовая activity | `{info.get('launchable_activity') or 'нет (запуск по имени пакета)'}` |",
         f"| ABI | " + (f"{', '.join(info['abis'])}; " if info.get("abis") else "") + f"{info.get('compat', {}).get('note', '')} |",
         f"| Разрешения | всего {len(perms)}; опасные (запрос в рантайме): {', '.join(dang) or 'нет'} |",
         f"| debuggable / allowBackup / cleartext | {info.get('debuggable')} / {info.get('allow_backup')} / {info.get('uses_cleartext_traffic')} |",
         f"| Экспортировано компонентов | {sum(1 for c in info.get('components') or [] if c['exported'])} из {len(info.get('components') or [])} |",
         f"| Deep links | {', '.join(sorted({d['uri'] for d in info.get('deep_links') or []})[:6]) or 'нет'} |",
         f"| Подпись | " + ("не проверялась" if not sig.get("checked") else
                            ("верна" if sig.get("verified") else "НЕ ВЕРНА") + f", схемы {', '.join(sig.get('schemes') or []) or '?'}"
                            + (", отладочная" if sig.get("debug_signed") else "")) + " |",
         f"| Языки ресурсов | {len(info.get('locales') or [])} |",
         f"| Рекомендуемые API для матрицы | {', '.join(str(x) for x in rec.get('suggested') or []) or '—'} |"]
    if info.get("risks"):
        L += ["", "Кандидаты пассивной безопасности (подтвердить в прогоне):"]
        L += [f"- `{r['check_id']}` ({r['severity']}): {r['title']}" for r in info["risks"][:12]]
    return "\n".join(L)


def cmd_build_apks(a):
    bt = bundletool_cmd()
    if not bt:
        sys.stderr.write("apk_info: нужен bundletool (PATH или BUNDLETOOL_JAR)\n")
        sys.exit(3)
    out = Path(a.out)
    if out.exists():
        sys.stderr.write(f"apk_info: {out} уже есть — не перезаписываю\n")
        sys.exit(2)
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = bt + ["build-apks", "--bundle", str(a.aab), "--output", str(out)] + (["--mode=universal"] if a.universal else [])
    code, o, e = su.run(cmd, timeout=900)
    print((o + e).strip()[-500:])
    sys.exit(0 if code == 0 else 2)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    an = sub.add_parser("analyze")
    an.add_argument("inputs", nargs="+")
    ins = sub.add_parser("installed")
    ins.add_argument("--package", required=True)
    ins.add_argument("--serial")
    ins.add_argument("--pull-to")
    for p in (an, ins):
        p.add_argument("--out")
        p.add_argument("--summary", action="store_true")
        p.add_argument("--no-signature", action="store_true")
    an.add_argument("--copy-to")
    sm = sub.add_parser("summary")
    sm.add_argument("info")
    ba = sub.add_parser("build-apks")
    ba.add_argument("aab")
    ba.add_argument("--out", required=True)
    ba.add_argument("--universal", action="store_true")
    a = ap.parse_args()
    if a.cmd == "analyze":
        cmd_analyze(a)
    elif a.cmd == "installed":
        cmd_installed(a)
    elif a.cmd == "summary":
        print(summary(json.loads(Path(a.info).read_text(encoding="utf-8"))))
    else:
        cmd_build_apks(a)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
