#!/usr/bin/env python3
"""Device control for android-qa-audit through adb (references/device-control.md). Python 3.9+, stdlib only.

Every state-changing command and every tap goes through guard.py (base prohibitions + run-config rules):
deny -> not executed, logged to <RUN_DIR>/logs/blocked.jsonl, exit 3; confirm -> not executed, exit 2
(repeat with --confirmed only after the user's "yes"); allow -> executed and logged to logs/actions.jsonl.

Common options: --serial S (or ANDROID_SERIAL / the only device), --run-dir R (outputs, logs; run-config.yaml
from there), --config run-config.yaml, --confirmed, --json.  PKG defaults to app.package from run-config.

Device and app:   devices | info | appinfo [PKG] | current | install APK… [--replace] [--downgrade] [--grant-all]
                  [--allow-test] | uninstall [PKG] [--keep-data] | clear [PKG] | launch [PKG] [--activity A] [--cold]
                  | stop [PKG] | kill-bg [PKG] | trim-memory LEVEL [PKG] | deeplink URI [--package P]
UI:               dump-ui [--out F.xml] [--json F.json] | find (--text T | --id ID | --desc D) | tap X Y |
                  tap (--text|--id|--desc) [--index N] | long-press … [--ms 800] | swipe X1 Y1 X2 Y2 [--ms 300] |
                  scroll up|down|left|right | text "abc" [--env VAR] [--translit|--adbkeyboard] | key BACK|HOME|…
                  | screenshot OUT.png | screenrecord OUT.mp4 [--seconds 20] | shade open|close
Configuration:    rotate portrait|landscape|reverse-portrait|reverse-landscape|auto | font-scale 1.3 |
                  density N|reset | dark-mode on|off|auto | locale ru-RU [--system] | timezone Europe/Moscow |
                  network wifi|offline|online|4g|3g|edge|gprs|full|switch | battery level N|unplug|reset|saver-on|saver-off |
                  doze enter|exit | standby on|off [PKG] | animations off|on
Permissions:      permissions [PKG] | grant PERM [PKG] | revoke PERM [PKG] | notifications [PKG]
Logs and metrics: logcat start|stop|dump|clear [--out F] [--package P] [--all] [--lines N] | crashes [PKG] |
                  meminfo [PKG] | gfxinfo [PKG] [--reset] | start-time [PKG] [--mode cold|warm|hot] [--runs 5] |
                  batterystats [PKG] [--reset] | size [PKG] | monkey [PKG] --events 500 --seed 42 [--throttle 300]
Exit codes: 0 ok, 2 needs confirmation / bad input, 3 denied by guard, 4 not supported on this device, 5 failed.
"""
import argparse
import json
import os
import re
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "shared"))
sys.path.insert(0, str(HERE))
import miniyaml  # noqa: E402
import sdkutil as su  # noqa: E402
import guard  # noqa: E402
from masking import mask  # noqa: E402

KEYS = {"BACK": 4, "HOME": 3, "ENTER": 66, "APP_SWITCH": 187, "TAB": 61, "DEL": 67, "MENU": 82, "ESCAPE": 111,
        "DPAD_UP": 19, "DPAD_DOWN": 20, "DPAD_LEFT": 21, "DPAD_RIGHT": 22, "DPAD_CENTER": 23, "SEARCH": 84,
        "VOLUME_UP": 24, "VOLUME_DOWN": 25, "POWER": 26, "WAKEUP": 224, "SLEEP": 223, "MOVE_END": 123,
        "MOVE_HOME": 122, "SPACE": 62, "NOTIFICATION": 83}
TRIM_LEVELS = ["RUNNING_MODERATE", "RUNNING_LOW", "RUNNING_CRITICAL", "UI_HIDDEN", "BACKGROUND", "MODERATE", "COMPLETE"]
NET_PROFILES = {"full": ("full", "none"), "wifi": ("full", "none"), "4g": ("lte", "lte"), "3g": ("umts", "umts"),
                "edge": ("edge", "edge"), "gprs": ("gprs", "gprs")}
INSTALL_HINTS = {
    "INSTALL_FAILED_UPDATE_INCOMPATIBLE": "подпись отличается от установленной версии — удалить старую (данные пропадут; спросить)",
    "INSTALL_FAILED_VERSION_DOWNGRADE": "версия ниже установленной — --downgrade (только debuggable) или удаление",
    "INSTALL_FAILED_NO_MATCHING_ABIS": "нативный код не под ABI устройства — другой образ (x86_64/arm64) или реальное устройство",
    "INSTALL_FAILED_OLDER_SDK": "minSdk приложения выше API устройства — выбрать образ новее",
    "INSTALL_FAILED_INSUFFICIENT_STORAGE": "мало места — увеличить disk.dataPartition.size или очистить устройство",
    "INSTALL_FAILED_TEST_ONLY": "testOnly-сборка — --allow-test (adb install -t)",
    "INSTALL_FAILED_ALREADY_EXISTS": "уже установлено — --replace",
    "INSTALL_FAILED_MISSING_SPLIT": "нужны все split APK — передать их вместе (install-multiple)",
    "INSTALL_FAILED_DEPRECATED_SDK_VERSION": "targetSdk < 23 на Android 14+ — adb install --bypass-low-target-sdk-block",
    "INSTALL_FAILED_USER_RESTRICTED": "на телефоне запрещена установка по USB — включить в параметрах разработчика",
    "INSTALL_FAILED_VERIFICATION_FAILURE": "установку заблокировала проверка (Play Protect) — решение пользователя",
    "INSTALL_FAILED_DUPLICATE_PERMISSION": "другое приложение объявляет то же разрешение — удалить его (спросить)",
    "INSTALL_FAILED_CONFLICTING_PROVIDER": "authority провайдера занята другим приложением",
    "INSTALL_PARSE_FAILED_NO_CERTIFICATES": "APK не подписан — нужна подписанная сборка",
    "INSTALL_FAILED_INVALID_APK": "повреждённый APK или неполный набор split",
}


class Ctx:
    def __init__(self, a):
        self.a = a
        self.run_dir = Path(a.run_dir) if getattr(a, "run_dir", None) else None
        cfg_path = getattr(a, "config", None) or (self.run_dir / "run-config.yaml" if self.run_dir else None)
        self.cfg = miniyaml.load_file(cfg_path) if cfg_path and Path(cfg_path).exists() else {}
        self.app = (self.cfg.get("app") or {}).get("package")
        self.throttle = int(((self.cfg.get("parallel") or {}).get("throttle_ms") or 500)) / 1000.0
        self._serial = None
        self._stand = None
        self._api = None

    @property
    def serial(self):
        if self._serial is None:
            self._serial = su.pick_serial(serial=self.a.serial)
        return self._serial

    @property
    def adb(self):
        return su.Adb(self.serial)

    def pkg(self, value=None):
        p = value or self.app
        if not p:
            fail("не указан пакет: передайте PKG или задайте app.package в run-config.yaml", 2)
        return p

    def api(self):
        if self._api is None:
            v = self.adb.getprop("ro.build.version.sdk")
            self._api = int(v) if v.isdigit() else 0
        return self._api

    def stand(self):
        """own-emulator | foreign-emulator | real."""
        if self._stand:
            return self._stand
        s = self.serial
        if s.startswith("emulator-"):
            code, out, _ = self.adb.cmd("emu", "avd", "name", timeout=10)
            name = out.strip().splitlines()[0].strip() if code == 0 and out.strip() else ""
            avd = next((x for x in su.list_avds() if x["name"] == name), None)
            reg = {}
            if self.run_dir and (self.run_dir / "stands.json").exists():
                reg = json.loads((self.run_dir / "stands.json").read_text(encoding="utf-8"))
            started = [e for e in reg.get("emulators", []) if e.get("serial") == s and not e.get("stopped_at")]
            if (avd and avd["owner"] == "skill") or (started and started[-1].get("read_only")):
                self._stand = "own-emulator"
            else:
                self._stand = "foreign-emulator"
        else:
            self._stand = "foreign-emulator" if self.adb.kind() == "emulator" else "real"
        return self._stand

    def log(self, name, rec):
        if not self.run_dir:
            return
        p = self.run_dir / "logs" / name
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "a", encoding="utf-8") as f:
            f.write(json.dumps({"time": datetime.now().isoformat(timespec="seconds"), "serial": self._serial, **rec},
                               ensure_ascii=False) + "\n")

    def gate(self, decision):
        """Apply a guard decision: exits on deny / unconfirmed confirm."""
        d = decision["decision"]
        if d == guard.DENY:
            self.log("blocked.jsonl", {"rule": decision.get("rule"), "reason": decision.get("reason"),
                                       "target": decision.get("target")})
            print(json.dumps({"blocked": True, **decision}, ensure_ascii=False))
            sys.exit(3)
        if d == guard.CONFIRM and not self.a.confirmed:
            print(json.dumps({"needs_confirmation": True, **decision}, ensure_ascii=False))
            sys.exit(2)
        if d == guard.CONFIRM:
            self.log("actions.jsonl", {"confirmed_by_user": True, "rule": decision.get("rule"),
                                       "target": decision.get("target")})

    def run(self, *shell_args, timeout=60, check_guard=True, binary=False, secret=False):
        """adb shell with guard check of the command line. secret=True: the last argument is never logged."""
        shown = list(map(str, shell_args[:-1])) + ["***"] if secret else list(map(str, shell_args))
        if check_guard:
            self.gate(guard.check_adb(["shell", *shown], self.cfg, self.stand(), self.serial))
        code, out, err = self.adb.shell(*shell_args, timeout=timeout, binary=binary)
        self.log("actions.jsonl", {"adb": "shell " + " ".join(shown)[:300], "code": code})
        return code, out, err

    def adb_cmd(self, *args, timeout=60, check_guard=True):
        if check_guard:
            self.gate(guard.check_adb(list(map(str, args)), self.cfg, self.stand(), self.serial))
        code, out, err = self.adb.cmd(*args, timeout=timeout)
        self.log("actions.jsonl", {"adb": " ".join(map(str, args))[:300], "code": code})
        return code, out, err

    def out_path(self, value, default_name, sub="raw"):
        if value:
            p = Path(value)
        elif self.run_dir:
            p = self.run_dir / sub / default_name
        else:
            p = Path(default_name)
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def pause(self):
        time.sleep(self.throttle)


def fail(msg, code=5):
    sys.stderr.write(f"adb_helpers: {msg}\n")
    sys.exit(code)


def emit(obj, a=None):
    print(json.dumps(obj, ensure_ascii=False, indent=None if not (a and getattr(a, "pretty", False)) else 1))


def ts():
    return datetime.now().strftime("%Y%m%d-%H%M%S")


# ---------- device and app ----------

def cmd_devices(c):
    code, devs, err = su.Adb().devices()
    for d in devs:
        if d["state"] == "device":
            d.update(su.device_summary(su.Adb(d["serial"]).getprop()))
    emit({"devices": devs, "error": err.strip() if code else None})


def cmd_info(c):
    p = c.adb.getprop()
    info = su.device_summary(p)
    _, size, _ = c.adb.shell("wm", "size", timeout=10)
    _, dens, _ = c.adb.shell("wm", "density", timeout=10)
    _, mem, _ = c.adb.shell("cat", "/proc/meminfo", timeout=10)
    _, fs, _ = c.adb.shell("settings", "get", "system", "font_scale", timeout=10)
    _, night, _ = c.adb.shell("cmd", "uimode", "night", timeout=10)
    _, bat, _ = c.adb.shell("dumpsys", "battery", timeout=15)
    m = re.search(r"MemTotal:\s+(\d+)", mem)
    info.update({"serial": c.serial, "stand": c.stand(), "screen": parse_wm(size), "density": parse_wm(dens),
                 "ram_mb": int(m.group(1)) // 1024 if m else None, "font_scale": fs.strip(),
                 "night_mode": night.strip().replace("Night mode: ", ""),
                 "battery_level": (re.search(r"level: (\d+)", bat) or [None, None])[1],
                 "timezone": p.get("persist.sys.timezone")})
    emit(info)


def parse_wm(text):
    over = re.search(r"Override (?:size|density): (\S+)", text or "")
    phys = re.search(r"Physical (?:size|density): (\S+)", text or "")
    return (over or phys).group(1) if (over or phys) else None


def density_of(c):
    _, out, _ = c.adb.shell("wm", "density", timeout=10)
    v = parse_wm(out)
    return int(v) if v and v.isdigit() else 160


def parse_package_dump(text, pkg):
    sys.path.insert(0, str(HERE))
    import apk_info
    return apk_info.parse_dumpsys_package(text, pkg)


def cmd_appinfo(c):
    pkg = c.pkg(c.a.pkg)
    _, out, _ = c.adb.shell("dumpsys", "package", pkg, timeout=60)
    if f"Package [{pkg}]" not in out:
        fail(f"{pkg} не установлен на {c.serial}", 4)
    emit(parse_package_dump(out, pkg))


def current_focus(c):
    _, out, _ = c.adb.shell("dumpsys", "activity", "activities", timeout=30)
    m = re.search(r"(?:topResumedActivity|mResumedActivity|ResumedActivity)[:=]\s*ActivityRecord\{\S+ \S+ ([\w.]+)/([\w.$]+)", out)
    if not m:
        _, out, _ = c.adb.shell("dumpsys", "window", "windows", timeout=30)
        m = re.search(r"mCurrentFocus=Window\{\S+ \S+ ([\w.]+)/([\w.$]+)\}", out) or \
            re.search(r"mCurrentFocus=Window\{\S+ \S+ ([\w.]+)\}", out)
    if not m:
        return {"package": None, "activity": None}
    pkg = m.group(1)
    act = m.group(2) if m.lastindex and m.lastindex >= 2 else None
    if act and act.startswith("."):
        act = pkg + act
    return {"package": pkg, "activity": act}


def cmd_current(c):
    emit(current_focus(c))


def apk_package(path):
    try:
        import apk_info
        badging, _, _ = apk_info.aapt_dump(str(path))
        return apk_info.parse_badging(badging).get("package")
    except Exception:  # noqa: BLE001 — no aapt or broken APK: adb will report
        return None


def cmd_install(c):
    files = [Path(p) for p in c.a.apks]
    for f in files:
        if not f.is_file():
            fail(f"нет файла {f}", 2)
    pkgs = {apk_package(f) for f in files} - {None}
    if c.app and pkgs and pkgs != {c.app}:
        c.gate(guard.result(guard.DENY, "adb", {"install": [str(f) for f in files], "packages": sorted(pkgs)},
                            f"APK другого приложения ({', '.join(sorted(pkgs))}), а тестируется {c.app}", "base:install-other"))
    flags = (["-r"] if c.a.replace else []) + (["-d"] if c.a.downgrade else []) + (["-g"] if c.a.grant_all else []) + \
        (["-t"] if c.a.allow_test else [])
    sub = "install-multiple" if len(files) > 1 else "install"
    code, out, err = c.adb_cmd(sub, *flags, *map(str, files), timeout=600)
    text = (out + err).strip()
    m = re.search(r"(INSTALL_[A-Z_]+)", text)
    res = {"ok": code == 0 and "Success" in text, "package": next(iter(pkgs), None), "output": text[-300:]}
    if m:
        res["code"] = m.group(1)
        res["hint"] = INSTALL_HINTS.get(m.group(1), "см. INSTALL.md → «Частые проблемы»")
    emit(res)
    sys.exit(0 if res["ok"] else 5)


def cmd_uninstall(c):
    pkg = c.pkg(c.a.pkg)
    code, out, err = c.adb_cmd("uninstall", *(["-k"] if c.a.keep_data else []), pkg, timeout=120)
    emit({"ok": "Success" in out, "package": pkg, "output": (out + err).strip()[-200:]})


def cmd_clear(c):
    pkg = c.pkg(c.a.pkg)
    code, out, err = c.run("pm", "clear", pkg, timeout=60)
    emit({"ok": "Success" in out, "package": pkg, "output": (out + err).strip()[-200:]})


def launcher_activity(c, pkg):
    _, out, _ = c.adb.shell("cmd", "package", "resolve-activity", "--brief", "-c", "android.intent.category.LAUNCHER",
                            pkg, timeout=20)
    lines = [ln.strip() for ln in out.splitlines() if "/" in ln]
    return lines[-1] if lines else None


def parse_am_start(text):
    res = {}
    for key in ("Status", "LaunchState", "Activity", "TotalTime", "WaitTime", "ThisTime"):
        m = re.search(rf"^{key}: (\S+)", text, re.M)
        if m:
            res[key] = int(m.group(1)) if m.group(1).isdigit() else m.group(1)
    err = re.search(r"^Error.*$", text, re.M)
    if err:
        res["error"] = err.group(0)
    return res


def launch(c, pkg, activity=None, cold=False):
    comp = activity if activity and "/" in (activity or "") else (f"{pkg}/{activity}" if activity else launcher_activity(c, pkg))
    if cold:
        c.run("am", "force-stop", pkg)
    if comp:
        code, out, err = c.run("am", "start", "-W", "-n", comp, timeout=90)
        res = parse_am_start(out + err)
    else:
        code, out, err = c.run("monkey", "-p", pkg, "-c", "android.intent.category.LAUNCHER", "1", timeout=60)
        res = {"Status": "ok" if "Events injected: 1" in out else "error", "via": "monkey"}
    res["component"] = comp
    return res


def cmd_launch(c):
    res = launch(c, c.pkg(c.a.pkg), c.a.activity, c.a.cold)
    emit(res)
    sys.exit(0 if res.get("Status") == "ok" and not res.get("error") else 5)


def cmd_start_time(c):
    pkg = c.pkg(c.a.pkg)
    comp = c.a.activity or launcher_activity(c, pkg)
    if not comp:
        fail("не найдена стартовая activity (resolve-activity)", 4)
    if "/" not in comp:
        comp = f"{pkg}/{comp}"
    times, states = [], []
    for i in range(c.a.runs):
        if c.a.mode == "cold":
            c.run("am", "force-stop", pkg)
            time.sleep(1.0)
        elif c.a.mode == "warm":
            launch(c, pkg, comp)
            time.sleep(1.5)
            c.run("input", "keyevent", str(KEYS["BACK"]))
            time.sleep(1.0)
        else:
            launch(c, pkg, comp)
            time.sleep(1.5)
            c.run("input", "keyevent", str(KEYS["HOME"]))
            time.sleep(1.0)
        code, out, err = c.run("am", "start", "-W", "-n", comp, timeout=90)
        r = parse_am_start(out + err)
        if "TotalTime" in r:
            times.append(r["TotalTime"])
            states.append(r.get("LaunchState"))
        time.sleep(1.0)
    if not times:
        fail("am start -W не вернул TotalTime", 5)
    res = {"package": pkg, "component": comp, "mode": c.a.mode, "runs": len(times), "times_ms": times,
           "launch_states": states, "median_ms": int(statistics.median(times)), "min_ms": min(times), "max_ms": max(times)}
    emit(res)
    if c.run_dir:
        p = c.run_dir / "raw" / "metrics.jsonl"
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "a", encoding="utf-8") as f:
            f.write(json.dumps({"metric": f"start-{c.a.mode}", "serial": c.serial, **res}, ensure_ascii=False) + "\n")


def cmd_stop(c):
    pkg = c.pkg(c.a.pkg)
    c.run("am", "force-stop", pkg)
    emit({"ok": True, "package": pkg})


def pidof(c, pkg):
    _, out, _ = c.adb.shell("pidof", pkg, timeout=10)
    return [p for p in out.split() if p.isdigit()]


def app_pids(adb, pkg):
    """PIDs of all processes of the package (pkg and pkg:subprocess): ps -A -o PID,NAME, old ps, then pidof."""
    if not pkg:
        return []
    res = []
    for args in (("ps", "-A", "-o", "PID,NAME"), ("ps",)):
        code, out, _ = adb.shell(*args, timeout=20)
        lines = [ln.split() for ln in out.splitlines() if ln.strip()]
        if code != 0 or not lines or "PID" not in lines[0]:
            continue
        i = lines[0].index("PID")
        res = [x[i] for x in lines[1:] if len(x) > i and x[i].isdigit() and belongs(x[-1], pkg)]
        break
    if not res:
        _, out, _ = adb.shell("pidof", pkg, timeout=10)
        res = [p for p in out.split() if p.isdigit()]
    return sorted(set(res), key=int)


def cmd_kill_bg(c):
    pkg = c.pkg(c.a.pkg)
    before = pidof(c, pkg)
    c.run("input", "keyevent", str(KEYS["HOME"]))
    time.sleep(1.5)
    c.run("am", "kill", pkg)
    time.sleep(1.0)
    after = pidof(c, pkg)
    emit({"package": pkg, "pid_before": before, "pid_after": after, "killed": bool(before) and not after,
          "next": "вернуться через «Недавние» (key APP_SWITCH) или launch — проверить восстановление состояния"})


def cmd_trim_memory(c):
    level = c.a.level.upper()
    if level not in TRIM_LEVELS:
        fail(f"уровень из {TRIM_LEVELS}", 2)
    pkg = c.pkg(c.a.pkg)
    code, out, err = c.run("am", "send-trim-memory", pkg, level)
    emit({"ok": code == 0 and "Error" not in out, "package": pkg, "level": level, "output": (out + err).strip()[:200]})


def cmd_deeplink(c):
    c.gate(guard.check_deeplink(c.a.uri, c.cfg))
    args = ["am", "start", "-W", "-a", "android.intent.action.VIEW", "-d", c.a.uri]
    if c.a.package:
        args.append(c.a.package)
    code, out, err = c.run(*args, timeout=60)
    res = parse_am_start(out + err)
    res["focus"] = current_focus(c)
    res["uri"] = c.a.uri
    emit(res)


# ---------- UI ----------

def dump_xml(c):
    for attempt in range(3):
        code, out, err = c.adb.shell("uiautomator", "dump", "/sdcard/qa-window_dump.xml", timeout=40)
        if code == 0 and "dumped to" in (out + err).lower():
            _, xml, _ = c.adb.cmd("exec-out", "cat", "/sdcard/qa-window_dump.xml", timeout=30)
            c.adb.shell("rm", "-f", "/sdcard/qa-window_dump.xml", timeout=10)
            if xml.strip().startswith("<?xml") or "<hierarchy" in xml:
                return xml
        time.sleep(1.5)  # "could not get idle state": animations — retry
    fail("uiautomator dump не удался (экран анимируется или защищён FLAG_SECURE): " + (out + err).strip()[:200], 5)


BOUNDS = re.compile(r"\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]")


def parse_ui(xml):
    """uiautomator XML -> flat list of nodes with path, bounds, center, label, flags."""
    root = ElementTree.fromstring(xml.encode("utf-8") if isinstance(xml, str) else xml)
    nodes = []

    def walk(el, path, parent):
        for i, ch in enumerate([x for x in el if x.tag == "node"]):
            a = ch.attrib
            m = BOUNDS.match(a.get("bounds", ""))
            b = [int(x) for x in m.groups()] if m else [0, 0, 0, 0]
            n = {"path": f"{path}.{i}" if path else str(i), "parent": parent, "text": a.get("text", ""),
                 "desc": a.get("content-desc", ""), "id": a.get("resource-id", ""), "class": a.get("class", ""),
                 "package": a.get("package", ""), "bounds": b, "center": [(b[0] + b[2]) // 2, (b[1] + b[3]) // 2],
                 "w": b[2] - b[0], "h": b[3] - b[1]}
            for flag in ("clickable", "long-clickable", "checkable", "checked", "enabled", "focusable", "focused",
                         "scrollable", "selected", "password"):
                n[flag.replace("-", "_")] = a.get(flag) == "true"
            nodes.append(n)
            walk(ch, n["path"], n["path"])
    walk(root, "", None)
    by_path = {n["path"]: n for n in nodes}
    for n in nodes:  # accessible label: own text/desc or the text of descendants (TalkBack reads children)
        own = (n["desc"] or n["text"]).strip()
        if not own:
            kids = [x for x in nodes if x["path"].startswith(n["path"] + ".") and (x["text"] or x["desc"]).strip()]
            own = " ".join((k["desc"] or k["text"]).strip() for k in kids[:3])
        n["label"] = own
        n["interactive"] = n["clickable"] or n["long_clickable"] or n["checkable"]
        n["clickable_ancestor"] = any(by_path[p]["clickable"] for p in ancestors(n["path"]) if p in by_path)
    return nodes


def ancestors(path):
    parts = path.split(".")
    return [".".join(parts[:i]) for i in range(len(parts) - 1, 0, -1)]


def a11y_candidates(nodes, density, screen):
    """Candidate findings (the agent confirms them by screenshot)."""
    out = []
    sw, sh = screen if screen else (None, None)
    for n in nodes:
        if not n["interactive"] or not n["enabled"] or n["w"] <= 0 or n["h"] <= 0:
            continue
        name = n["label"] or n["id"].split("/")[-1] or n["class"].split(".")[-1]
        if not n["label"]:
            out.append({"check_id": "a11y.missing-label", "severity": "medium", "element": elem_ref(n),
                        "detail": f"{n['class'].split('.')[-1]} без text/contentDescription — TalkBack прочитает «кнопка» без названия"})
        wdp, hdp = n["w"] * 160 / density, n["h"] * 160 / density
        if (wdp < 48 or hdp < 48) and not n["clickable_ancestor"]:
            out.append({"check_id": "a11y.touch-target", "severity": "low", "element": elem_ref(n),
                        "detail": f"«{name[:40]}»: цель {round(wdp)}×{round(hdp)} dp < 48×48 dp"})
        if sw and (n["bounds"][2] > sw + 2 or n["bounds"][3] > sh + 2 or n["bounds"][0] < -2 or n["bounds"][1] < -2):
            out.append({"check_id": "visual.offscreen", "severity": "low", "element": elem_ref(n),
                        "detail": f"«{name[:40]}» выходит за край экрана {n['bounds']}"})
    for n in nodes:
        if n["text"].endswith(("…", "...")) and len(n["text"]) > 4:
            out.append({"check_id": "visual.text-ellipsized", "severity": "info", "element": elem_ref(n),
                        "detail": f"текст обрезан многоточием: «{n['text'][:60]}»"})
    inter = [n for n in nodes if n["interactive"] and not n["clickable_ancestor"] and n["w"] > 0 and n["h"] > 0]
    for i, x in enumerate(inter):
        for y in inter[i + 1:]:
            if y["path"].startswith(x["path"] + ".") or x["path"].startswith(y["path"] + "."):
                continue
            ox = min(x["bounds"][2], y["bounds"][2]) - max(x["bounds"][0], y["bounds"][0])
            oy = min(x["bounds"][3], y["bounds"][3]) - max(x["bounds"][1], y["bounds"][1])
            if ox > 4 and oy > 4 and ox * oy > 0.2 * min(x["w"] * x["h"], y["w"] * y["h"]):
                out.append({"check_id": "visual.overlap", "severity": "medium", "element": elem_ref(x),
                            "detail": f"перекрываются «{(x['label'] or x['id'])[:30]}» и «{(y['label'] or y['id'])[:30]}»"})
    return out


def elem_ref(n):
    parts = []
    if n["id"]:
        parts.append("id=" + n["id"].split(":id/")[-1])
    if n["text"]:
        parts.append(f"text=\"{n['text'][:40]}\"")
    elif n["desc"]:
        parts.append(f"desc=\"{n['desc'][:40]}\"")
    parts.append(n["class"].split(".")[-1])
    return " ".join(parts)


def natural_size(c):
    """`wm size` (override or physical) — the size in the natural orientation (portrait for phones)."""
    _, out, _ = c.adb.shell("wm", "size", timeout=10)
    m = re.match(r"(\d+)x(\d+)", parse_wm(out) or "")
    return (int(m.group(1)), int(m.group(2))) if m else None


def parse_window_displays(text):
    """`dumpsys window displays` (default display): (current logical size incl. rotation, rotation 0–3)."""
    block = re.split(r"\n\s*Display: mDisplayId=(?!0\b)", text or "", maxsplit=1)[0]
    m = re.search(r"\bcur=(\d+)x(\d+)", block)
    size = (int(m.group(1)), int(m.group(2))) if m else None
    rot = None
    r = re.search(r"\bmCurrentRotation=(?:ROTATION_)?(\d+)", block) or re.search(r"\bmRotation=(?:ROTATION_)?(\d+)", block)
    if r:
        v = int(r.group(1))
        rot = v // 90 if v >= 90 or (v == 0 and "ROTATION_0" in r.group(0)) else v
    return size, rot


def parse_input_rotation(text):
    """`dumpsys input`: SurfaceOrientation (Android ≤ 12) or orientation= of the internal viewport."""
    r = re.search(r"SurfaceOrientation: (\d)", text or "") or \
        re.search(r"Viewport INTERNAL:[^\n]*?\borientation=(\d)", text or "")
    return int(r.group(1)) if r else None


def rotated(natural, rot):
    if not natural:
        return None
    w, h = natural
    return (h, w) if rot in (1, 3) else (w, h)


def display_info(c):
    """Current screen: {size [w, h] in the current rotation, rotation 0–3, natural [w, h], source}.

    Sources in order: `dumpsys window displays` (cur=WxH — logical display incl. rotation, override size,
    status/navigation bars and the cutout area), then `wm size` rotated by `dumpsys input`."""
    natural = natural_size(c)
    _, out, _ = c.adb.shell("dumpsys", "window", "displays", timeout=20)
    size, rot = parse_window_displays(out)
    if size:
        if rot is None and natural:
            rot = 0 if size == natural else 1
        return {"size": list(size), "rotation": rot, "natural": list(natural) if natural else None,
                "source": "dumpsys window displays"}
    _, inp, _ = c.adb.shell("dumpsys", "input", timeout=15)
    rot = parse_input_rotation(inp)
    size = rotated(natural, rot or 0)
    return {"size": list(size) if size else None, "rotation": rot, "natural": list(natural) if natural else None,
            "source": "wm size + dumpsys input" if rot is not None else "wm size (поворот неизвестен)"}


def screen_size(c):
    info = display_info(c)
    return tuple(info["size"]) if info["size"] else None


def dump_rotation(xml):
    m = re.search(r"<hierarchy[^>]*\brotation=\"(\d)\"", (xml or "")[:500])
    return int(m.group(1)) if m else None


def screen_for_dump(xml, nodes, natural, current=None):
    """Screen size for the bounds of THIS dump: the dump's own rotation (<hierarchy rotation="N">) applied to the
    natural size; without it — the current display size. If the nodes do not fit it but fit the swapped size, swap
    (the screen turned between the calls). Returns ((w, h) or None, source)."""
    rot = dump_rotation(xml)
    if natural and rot is not None:
        size, src = rotated(natural, rot), f"wm size + rotation={rot} из дампа"
    elif current:
        size, src = tuple(current), "текущий экран"
    else:
        return None, "неизвестно"
    roots = [n for n in nodes if n["parent"] is None] or nodes  # window roots: a truly offscreen child must not decide
    mx = max((n["bounds"][2] for n in roots), default=0)
    my = max((n["bounds"][3] for n in roots), default=0)
    w, h = size
    if (mx > w + 2 or my > h + 2) and mx <= h + 2 and my <= w + 2:
        size, src = (h, w), src + "; оси переставлены по границам узлов"
    return size, src


def fresh_ui(c):
    xml = dump_xml(c)
    return xml, parse_ui(xml)


def cmd_dump_ui(c):
    xml, nodes = fresh_ui(c)
    focus = current_focus(c)
    stamp = ts()
    xml_out = c.out_path(c.a.out, f"ui-{stamp}.xml")
    xml_out.write_text(mask(xml), encoding="utf-8")
    natural = natural_size(c)
    current = None if (natural and dump_rotation(xml) is not None) else screen_size(c)
    screen, src = screen_for_dump(xml, nodes, natural, current)
    cands = a11y_candidates(nodes, density_of(c), screen)
    data = {"focus": focus, "xml": str(xml_out), "nodes": len(nodes),
            "screen": {"size": list(screen) if screen else None, "rotation": dump_rotation(xml), "source": src},
            "candidates": cands,
            "elements": [{"i": k, "label": mask(n["label"])[:60], "id": n["id"].split(":id/")[-1], "class": n["class"].split(".")[-1],
                          "center": n["center"], "bounds": n["bounds"], "clickable": n["interactive"], "enabled": n["enabled"],
                          "checked": n["checked"] if n["checkable"] else None, "scrollable": n["scrollable"],
                          "password": n["password"], "package": n["package"]}
                         for k, n in enumerate(nodes) if n["interactive"] or n["text"] or n["desc"] or n["scrollable"]]}
    if c.a.json_out:
        Path(c.a.json_out).parent.mkdir(parents=True, exist_ok=True)
        Path(c.a.json_out).write_text(json.dumps({**data, "all_nodes": nodes}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"экран: {focus.get('package')}/{focus.get('activity')} · элементов {len(nodes)} · "
          f"размер {'x'.join(map(str, screen)) if screen else '?'} (поворот {dump_rotation(xml)}) · файл {xml_out}")
    for e in data["elements"]:
        flags = ",".join(x for x in ("clickable" if e["clickable"] else "", "disabled" if not e["enabled"] else "",
                                     "scroll" if e["scrollable"] else "", "password" if e["password"] else "",
                                     f"checked={e['checked']}" if e["checked"] is not None else "") if x)
        print(f"[{e['i']}] {e['class']} \"{e['label']}\"" + (f" id={e['id']}" if e["id"] else "") +
              f" @{e['center'][0]},{e['center'][1]}" + (f" ({flags})" if flags else ""))
    if cands:
        print("кандидаты (подтвердить по скриншоту):")
        for x in cands:
            print(f"  {x['check_id']}: {x['element']} — {x['detail']}")


def match_nodes(nodes, a):
    def hit(n):
        if a.text is not None:
            t, want = n["text"].strip().lower(), a.text.strip().lower()
            if not (t == want or (not a.exact and want and want in t)):
                return False
        if a.id is not None and not (n["id"] == a.id or n["id"].endswith(":id/" + a.id)):
            return False
        if a.desc is not None:
            d, want = n["desc"].strip().lower(), a.desc.strip().lower()
            if not (d == want or (not a.exact and want and want in d)):
                return False
        return True
    found = [n for n in nodes if hit(n)]
    found.sort(key=lambda n: (not n["interactive"], not n["enabled"]))
    return found


def cmd_find(c):
    _, nodes = fresh_ui(c)
    found = match_nodes(nodes, c.a)
    emit({"count": len(found), "nodes": [{"label": mask(n["label"])[:80], "id": n["id"], "class": n["class"],
                                          "center": n["center"], "bounds": n["bounds"], "clickable": n["interactive"],
                                          "enabled": n["enabled"]} for n in found[:10]]})
    sys.exit(0 if found else 4)


def node_at(nodes, x, y):
    inside = [n for n in nodes if n["bounds"][0] <= x <= n["bounds"][2] and n["bounds"][1] <= y <= n["bounds"][3]]
    inter = [n for n in inside if n["interactive"]]
    pool = inter or inside
    return min(pool, key=lambda n: n["w"] * n["h"]) if pool else None


def guard_node(c, node, nodes, verb):
    focus = current_focus(c)
    context = " ".join((n["text"] or n["desc"]) for n in nodes if (n["text"] or n["desc"]))[:600]
    if node is None:
        dec = guard.check_package(focus.get("package"), c.cfg)
        if dec["decision"] == guard.ALLOW:
            dec = guard.result(guard.CONFIRM, "action", {"verb": verb}, "элемент под точкой не определён — спросить",
                               "base:action:unknown-element")
    else:
        text = node["text"] or ""
        desc = node["desc"] or ("" if text else node["label"])
        dec = guard.check_action(c.cfg, text=text, desc=desc, res_id=node["id"], cls=node["class"],
                                 pkg=node["package"] or focus.get("package"), screen=focus.get("activity") or "",
                                 context=context)
    c.gate(dec)
    return focus


def target_point(c, verb):
    a = c.a
    _, nodes = fresh_ui(c)
    if a.x is not None and a.y is not None:
        node = node_at(nodes, a.x, a.y)
        x, y = a.x, a.y
    else:
        if a.text is None and a.id is None and a.desc is None:
            fail("нужны координаты X Y или --text/--id/--desc", 2)
        found = match_nodes(nodes, a)
        if not found:
            fail("элемент не найден на экране (dump-ui покажет, что есть)", 4)
        node = found[min(a.index, len(found) - 1)]
        x, y = node["center"]
    guard_node(c, node, nodes, verb)
    return x, y, node


def after_action(c, verb, x, y, node):
    c.pause()
    focus = current_focus(c)
    res = {"ok": True, "action": verb, "x": x, "y": y, "element": elem_ref(node) if node else None, "focus": focus}
    pol = guard.check_package(focus.get("package"), c.cfg)
    if pol["decision"] == guard.DENY:
        res["left_app"] = pol["reason"]
        c.log("blocked.jsonl", {"rule": "base:left-app", "reason": f"после {verb} открылось {focus.get('package')} — вернуться BACK",
                                "target": focus})
    emit(res)


def cmd_tap(c):
    x, y, node = target_point(c, "tap")
    c.run("input", "tap", x, y)
    after_action(c, "tap", x, y, node)


def cmd_long_press(c):
    x, y, node = target_point(c, "long-press")
    c.run("input", "swipe", x, y, x, y, c.a.ms)
    after_action(c, "long-press", x, y, node)


def cmd_swipe(c):
    a = c.a
    c.run("input", "swipe", a.x1, a.y1, a.x2, a.y2, a.ms)
    c.pause()
    emit({"ok": True, "action": "swipe", "from": [a.x1, a.y1], "to": [a.x2, a.y2]})


def cmd_scroll(c):
    size = screen_size(c) or (1080, 1920)
    w, h = size
    cx, cy = w // 2, h // 2
    dx, dy = {"down": (0, -h // 3), "up": (0, h // 3), "left": (w // 3, 0), "right": (-w // 3, 0)}[c.a.direction]
    c.run("input", "swipe", cx, cy, cx + dx, cy + dy, 350)
    c.pause()
    emit({"ok": True, "action": f"scroll {c.a.direction}"})


def input_text_escape(s):
    """`input text` turns %s into a space; shell quoting is done by Adb.shell (shlex.quote)."""
    return s.replace(" ", "%s")


TRANSLIT = {"а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "yo", "ж": "zh", "з": "z", "и": "i",
            "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t",
            "у": "u", "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "shch", "ъ": "", "ы": "y", "ь": "",
            "э": "e", "ю": "yu", "я": "ya", "і": "i", "ї": "yi", "є": "ye", "ґ": "g", "ў": "u",
            "«": "\"", "»": "\"", "„": "\"", "“": "\"", "”": "\"", "‘": "'", "’": "'", "—": "-", "–": "-", "…": "...",
            "№": "No", "\u00a0": " "}
ADB_IME = "com.android.adbkeyboard/.AdbIME"


def translit(text):
    """Latin transliteration (Cyrillic → Latin, accents dropped). Returns (ascii text, characters left as is)."""
    import unicodedata
    out, bad = [], []
    for ch in text:
        if ch.isascii():
            out.append(ch)
            continue
        low = ch.lower()
        if low in TRANSLIT:
            t = TRANSLIT[low]
            out.append(t.capitalize() if ch != low and t else t)
            continue
        base = "".join(x for x in unicodedata.normalize("NFKD", ch) if not unicodedata.combining(x))
        if base and base.isascii():
            out.append(base)
        else:
            bad.append(ch)
    return "".join(out), bad


def adbkeyboard_installed(c):
    _, ime, _ = c.adb.shell("ime", "list", "-a", "-s", timeout=10)
    return ADB_IME in ime


def type_with_adbkeyboard(c, value, secret):
    """ADBKeyBoard on the skill's own emulator: switch IME, send base64 text, restore the previous IME."""
    import base64
    if c.stand() != "own-emulator":
        fail("ADBKeyBoard — только на эмуляторе скила (qa-*): на реальном устройстве и чужом AVD смена клавиатуры — "
             "изменение настроек; ввести вручную или --translit", 4)
    if not adbkeyboard_installed(c):
        fail("ADBKeyBoard не установлен на этом эмуляторе: установить его APK на свой эмулятор можно только с согласия "
             "пользователя (стороннее приложение) — или --translit, или ввести вручную в окне эмулятора", 4)
    _, prev, _ = c.adb.shell("settings", "get", "secure", "default_input_method", timeout=10)
    prev = prev.strip()
    c.run("ime", "enable", ADB_IME)
    c.run("ime", "set", ADB_IME)
    time.sleep(0.5)
    c.run("am", "broadcast", "-a", "ADB_INPUT_B64", "-p", "com.android.adbkeyboard", "--es", "msg",
          base64.b64encode(value.encode("utf-8")).decode("ascii"), secret=secret)
    time.sleep(0.3)
    restored = None
    if prev and prev != "null" and prev != ADB_IME:
        c.run("ime", "set", prev)
        restored = prev
    return restored


def cmd_text(c):
    value = os.environ.get(c.a.env, "") if c.a.env else (c.a.value or "")
    if c.a.env and not value:
        fail(f"переменная окружения {c.a.env} пуста", 2)
    secret = bool(c.a.env)
    res = {"ok": True, "masked": secret}
    if not value.isascii():
        if c.a.translit:
            if secret:
                fail("секрет нельзя транслитерировать — значение изменится; --adbkeyboard или ввести вручную", 2)
            typed, bad = translit(value)
            if bad:
                fail(f"не транслитерируется: {' '.join(sorted(set(bad)))} — ввести вручную или --adbkeyboard", 4)
            res.update({"translit": True, "typed": typed, "original_chars": len(value),
                        "note": "введено латиницей (транслитерация) — указать это в шагах находок"})
            value = typed
        elif c.a.adbkeyboard:
            if c.a.into_id or c.a.into_text:
                focus_into(c)
            restored = type_with_adbkeyboard(c, value, secret)
            c.pause()
            emit(dict(res, chars=len(value), via="ADBKeyBoard", ime_restored=restored))
            return
        else:
            have = adbkeyboard_installed(c)
            fail("не-ASCII текст (кириллица, emoji) через adb input не вводится. Варианты: --translit — латиницей "
                 "(помечается в выводе); --adbkeyboard — через ADBKeyBoard на эмуляторе скила "
                 f"({'установлен на этом устройстве' if have else 'на этом устройстве не установлен'}); "
                 "ввести вручную в окне эмулятора (device-control.md → «Ввод текста»)", 4)
    if c.a.into_id or c.a.into_text:
        focus_into(c)
    c.run("input", "text", input_text_escape(value), secret=secret)
    c.pause()
    emit(dict(res, chars=len(value)))


def focus_into(c):
    c.a.id, c.a.text, c.a.desc, c.a.x, c.a.y, c.a.index, c.a.exact = c.a.into_id, c.a.into_text, None, None, None, 0, False
    x, y, node = target_point(c, "focus")
    c.run("input", "tap", x, y)
    c.pause()


def cmd_key(c):
    name = c.a.name.upper()
    code = KEYS.get(name) or (int(name) if name.isdigit() else None)
    if code is None:
        fail(f"клавиша из {sorted(KEYS)} или код", 2)
    c.run("input", "keyevent", code)
    c.pause()
    emit({"ok": True, "key": name, "focus": current_focus(c)})


def cmd_screenshot(c):
    out = c.out_path(c.a.out, f"shot-{ts()}.png", "screenshots")
    code, data, err = c.adb.cmd("exec-out", "screencap", "-p", binary=True, timeout=60)
    if code != 0 or not data.startswith(b"\x89PNG"):
        fail(f"screencap: {err.strip()[:200] or 'не PNG (защищённый экран FLAG_SECURE?)'}", 5)
    out.write_bytes(data)
    emit({"ok": True, "file": str(out), "bytes": len(data)})


def cmd_screenrecord(c):
    out = c.out_path(c.a.out, f"rec-{ts()}.mp4", "recordings")
    remote = f"/sdcard/qa-rec-{ts()}.mp4"
    secs = max(1, min(180, c.a.seconds))
    code, o, e = c.run("screenrecord", "--time-limit", secs, "--bit-rate", "4000000", remote, timeout=secs + 30)
    if code != 0:
        fail(f"screenrecord: {(o + e).strip()[:200]}", 4)
    pc, po, pe = c.adb.cmd("pull", remote, str(out), timeout=120)
    c.run("rm", "-f", remote)
    if pc != 0:
        fail(f"adb pull: {(po + pe).strip()[:200]}", 5)
    emit({"ok": True, "file": str(out), "seconds": secs})


def cmd_shade(c):
    c.run("cmd", "statusbar", "expand-notifications" if c.a.state == "open" else "collapse")
    c.pause()
    emit({"ok": True, "shade": c.a.state})


# ---------- configuration ----------

def cmd_rotate(c):
    rot = {"portrait": 0, "landscape": 1, "reverse-portrait": 2, "reverse-landscape": 3}
    n = rot.get(c.a.mode)
    if c.a.mode == "auto":
        c.run("settings", "put", "system", "accelerometer_rotation", "1")
    else:
        code, out, err = c.run("cmd", "window", "user-rotation", "lock", n) if c.api() >= 31 else (1, "", "")
        if code != 0 or "Unknown" in out + err:
            c.run("settings", "put", "system", "accelerometer_rotation", "0")
            c.run("settings", "put", "system", "user_rotation", n)
    info = display_info(c)
    deadline = time.time() + 5
    while n is not None and info["rotation"] != n and time.time() < deadline:  # the turn takes a moment
        time.sleep(0.5)
        info = display_info(c)
    applied = n is None or info["rotation"] == n
    emit({"ok": True, "rotation": c.a.mode, "applied": applied, "rotation_index": info["rotation"],
          "screen": info["size"], "source": info["source"],
          "note": "" if applied else "экран не повернулся: приложение может фиксировать ориентацию — это не дефект само "
                                     "по себе; размер — фактический"})


def cmd_font_scale(c):
    c.run("settings", "put", "system", "font_scale", c.a.value)
    emit({"ok": True, "font_scale": c.a.value})


def cmd_density(c):
    if c.a.value == "reset":
        c.run("wm", "density", "reset")
    else:
        c.run("wm", "density", int(c.a.value))
    emit({"ok": True, "density": parse_wm(c.adb.shell("wm", "density", timeout=10)[1])})


def cmd_dark_mode(c):
    val = {"on": "yes", "off": "no", "auto": "auto"}[c.a.mode]
    if c.api() and c.api() < 29:
        fail("системная тёмная тема — с API 29 (Android 10)", 4)
    code, out, err = c.run("cmd", "uimode", "night", val)
    emit({"ok": code == 0, "night": (out + err).strip()})


def cmd_locale(c):
    pkg = c.pkg(c.a.pkg) if not c.a.system else None
    if c.a.system:
        fail("системный язык меняется перезапуском эмулятора: avd_manager.py start <AVD> --locale "
             f"{c.a.tag} (или вручную в настройках устройства)", 4)
    if c.api() < 33:
        fail("язык приложения через adb — с API 33 (cmd locale set-app-locales); на старых API — "
             "перезапуск эмулятора с --locale", 4)
    code, out, err = c.run("cmd", "locale", "set-app-locales", pkg, "--locales", c.a.tag)
    emit({"ok": code == 0 and "Error" not in out + err, "package": pkg, "locale": c.a.tag, "output": (out + err).strip()[:200],
          "note": "перезапустите приложение (stop + launch), чтобы язык применился"})


def cmd_timezone(c):
    c.run("settings", "put", "global", "auto_time_zone", "0")
    code, out, err = c.run("cmd", "alarm", "set-timezone", c.a.tz)
    if code != 0 or "Unknown" in out + err or "Error" in out + err:
        code, out, err = c.run("service", "call", "alarm", "3", "s16", c.a.tz)
    _, tz, _ = c.adb.shell("getprop", "persist.sys.timezone", timeout=10)
    ok = tz.strip() == c.a.tz
    emit({"ok": ok, "timezone": tz.strip(), "note": "" if ok else "не применилось: перезапуск эмулятора с --timezone"})
    sys.exit(0 if ok else 4)


def emu_net(c, speed, delay):
    if c.stand() != "own-emulator" or not c.serial.startswith("emulator-"):
        return "скорость сети ограничивается только на своём эмуляторе"
    c.adb_cmd("emu", "network", "speed", speed)
    c.adb_cmd("emu", "network", "delay", delay)
    return f"{speed}/{delay}"


def airplane(c, on):
    if c.api() >= 30:
        code, out, err = c.run("cmd", "connectivity", "airplane-mode", "enable" if on else "disable")
        if code == 0 and "Unknown" not in out + err:
            return "airplane-mode " + ("on" if on else "off")
    c.run("svc", "wifi", "disable" if on else "enable")
    c.run("svc", "data", "disable" if on else "enable")
    return "wifi+data " + ("off" if on else "on")


def cmd_network(c):
    p = c.a.profile
    res = {"profile": p}
    if p == "offline":
        res["done"] = airplane(c, True)
    elif p == "online":
        res["done"] = airplane(c, False)
        res["speed"] = emu_net(c, "full", "none")
    elif p == "switch":
        c.run("svc", "wifi", "disable")
        time.sleep(max(1, c.a.seconds))
        c.run("svc", "wifi", "enable")
        res["done"] = f"wifi off {c.a.seconds} с → on"
    elif p in NET_PROFILES:
        airplane(c, False)
        res["speed"] = emu_net(c, *NET_PROFILES[p])
    else:
        fail(f"профиль из offline, online, switch, {', '.join(NET_PROFILES)}", 2)
    time.sleep(1.0)
    emit(res)


def cmd_battery(c):
    act = c.a.action
    if act == "level":
        if c.a.value is None:
            fail("нужен уровень 0–100", 2)
        c.run("dumpsys", "battery", "unplug")
        c.run("dumpsys", "battery", "set", "level", int(c.a.value))
    elif act == "unplug":
        c.run("dumpsys", "battery", "unplug")
    elif act == "reset":
        c.run("dumpsys", "battery", "reset")
    elif act in ("saver-on", "saver-off"):
        on = act == "saver-on"
        if on:
            c.run("dumpsys", "battery", "unplug")
        code, out, err = c.run("cmd", "power", "set-mode", "1" if on else "0") if c.api() >= 30 else (1, "", "")
        if code != 0:
            c.run("settings", "put", "global", "low_power", "1" if on else "0")
    _, bat, _ = c.adb.shell("dumpsys", "battery", timeout=15)
    emit({"ok": True, "action": act, "level": (re.search(r"level: (\d+)", bat) or [None, None])[1]})


def cmd_doze(c):
    if c.a.action == "enter":
        c.run("dumpsys", "battery", "unplug")
        code, out, err = c.run("dumpsys", "deviceidle", "force-idle")
    else:
        code, out, err = c.run("dumpsys", "deviceidle", "unforce")
        c.run("dumpsys", "battery", "reset")
    emit({"ok": code == 0, "doze": c.a.action, "output": (out + err).strip()[:200]})


def cmd_standby(c):
    pkg = c.pkg(c.a.pkg)
    c.run("am", "set-inactive", pkg, "true" if c.a.state == "on" else "false")
    _, out, _ = c.adb.shell("am", "get-inactive", pkg, timeout=10)
    emit({"ok": True, "package": pkg, "state": out.strip()})


def cmd_animations(c):
    v = "0" if c.a.state == "off" else "1"
    for key in ("window_animation_scale", "transition_animation_scale", "animator_duration_scale"):
        c.run("settings", "put", "global", key, v)
    emit({"ok": True, "animations": c.a.state})


# ---------- permissions, notifications ----------

def runtime_permissions(c, pkg):
    _, out, _ = c.adb.shell("dumpsys", "package", pkg, timeout=60)
    sec = re.search(r"runtime permissions:\n((?:\s+\S.*\n?)+)", out)
    res = {}
    for m in re.finditer(r"^\s+([\w.]+): granted=(true|false)(?:, flags=\[([^\]]*)\])?", sec.group(1) if sec else "", re.M):
        res[m.group(1)] = {"granted": m.group(2) == "true", "flags": (m.group(3) or "").split()}
    return res


def cmd_permissions(c):
    pkg = c.pkg(c.a.pkg)
    emit({"package": pkg, "runtime": runtime_permissions(c, pkg)})


def full_perm(p):
    return p if "." in p else f"android.permission.{p}"


def cmd_grant(c, revoke=False):
    pkg = c.pkg(c.a.pkg)
    perm = full_perm(c.a.perm)
    code, out, err = c.run("pm", "revoke" if revoke else "grant", pkg, perm)
    st = runtime_permissions(c, pkg).get(perm)
    emit({"ok": code == 0, "package": pkg, "permission": perm, "state": st, "output": (out + err).strip()[:200]})


def cmd_notifications(c):
    pkg = c.pkg(c.a.pkg)
    _, out, _ = c.adb.shell("dumpsys", "notification", "--noredact", timeout=60)
    items = []
    for block in re.split(r"\n\s+NotificationRecord\(", out)[1:]:
        if f"pkg={pkg} " not in block[:300]:
            continue
        g = lambda rx: (re.search(rx, block) or [None, None])[1]  # noqa: E731
        items.append({"id": g(r"\bid=(-?\d+)"), "channel": g(r"channel=(\S+?)[ ,)]"), "importance": g(r"importance=(\d)"),
                      "title": mask(g(r"android\.title=\S+ \((.*?)\)\n") or ""), "text": mask(g(r"android\.text=\S+ \((.*?)\)\n") or "")})
    emit({"package": pkg, "count": len(items), "notifications": items})


# ---------- logs and metrics ----------

def logcat_file(c, out):
    return c.out_path(out, f"logcat-{c.serial.replace(':', '_')}.txt", "logs")


LOG_HEAD = re.compile(r"^(\d\d-\d\d \d\d:\d\d:\d\d\.\d+)\s+(\d+)\s+(\d+)\s+([VDIWEFAS])\s+(.*?)\s*: ")


class AppLogFilter:
    """Keeps logcat lines of the app under test: lines of its PIDs (updated on restart from «Start proc N:<pkg>/»
    and by polling ps), lines that mention the package (ActivityManager: start, ANR, death), buffer markers and
    the continuation lines of a kept multi-line entry (same time, PID, TID, tag)."""

    def __init__(self, pkg, pids=()):
        self.pkg, self.pids, self.last = pkg, set(map(str, pids)), None

    def add_pids(self, pids):
        self.pids.update(map(str, pids))

    def keep(self, line):
        if line.startswith("--------- beginning of"):
            return True
        m = START_PROC.search(line)
        if m and belongs(m.group(2), self.pkg):
            self.pids.add(m.group(1))
        head = LOG_HEAD.match(line)
        key = head.groups() if head else None
        if (key and key[1] in self.pids) or self.pkg in line or (key and key == self.last):
            self.last = key or self.last
            return True
        return False


def cmd_logcat_follow(c):
    """Internal (started by `logcat start`): adb logcat → only the app's lines → stdout (the log file)."""
    import signal
    import subprocess
    import threading
    flt = AppLogFilter(c.a.package, app_pids(c.adb, c.a.package))
    stop = threading.Event()

    def poll():
        while not stop.wait(5):
            try:
                flt.add_pids(app_pids(c.adb, c.a.package))
            except Exception:  # noqa: BLE001 — the device may be busy; next round
                continue

    proc = subprocess.Popen([su.tool_path("adb"), "-s", c.serial, "logcat", "-v", "threadtime", "-b", "main,system,crash"],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)

    def finish(*_):
        stop.set()
        try:
            proc.terminate()
        except OSError:
            pass
        sys.exit(0)

    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, finish)
    threading.Thread(target=poll, daemon=True).start()
    out = sys.stdout.buffer
    try:
        for raw in proc.stdout:
            line = raw.decode("utf-8", "replace")
            if flt.keep(line):
                out.write(raw)
                out.flush()
    finally:
        stop.set()
        if proc.poll() is None:
            proc.terminate()


def cmd_logcat(c):
    act = c.a.action
    pidfile = (c.run_dir or Path(".")) / "logs" / f".logcat-{c.serial.replace(':', '_')}.pid"
    pkg = None if c.a.all else (c.a.package or c.app)
    if act == "start":
        out = logcat_file(c, c.a.out)
        if pidfile.exists() and su.pid_alive(int(pidfile.read_text().split()[0] or 0)):
            emit({"ok": True, "already_running": True, "file": str(out)})
            return
        if pkg:  # default: only the app under test (PIDs follow process restarts); --all — the whole device log
            cmd = [sys.executable, str(Path(__file__).resolve()), "logcat-follow", "--serial", c.serial, "--package", pkg]
        else:
            cmd = [su.tool_path("adb"), "-s", c.serial, "logcat", "-v", "threadtime", "-b", "main,system,crash"]
        proc = su.popen_detached(cmd, out)
        pidfile.parent.mkdir(parents=True, exist_ok=True)
        pidfile.write_text(f"{proc.pid} {out}\n", encoding="utf-8")
        emit({"ok": True, "pid": proc.pid, "file": str(out), "filtered": bool(pkg), "package": pkg,
              "note": "только строки приложения (по PID, с перезапусками); весь журнал устройства — logcat start --all; "
                      "падения и ANR считает `crashes` по полному журналу" if pkg else
                      ("весь журнал устройства" if c.a.all else "пакет неизвестен (нет run-config / --package) — весь журнал")})
    elif act == "stop":
        if not pidfile.exists():
            fail("logcat не запущен этим прогоном", 4)
        pid, path = pidfile.read_text(encoding="utf-8").split(" ", 1)
        su.kill_pid(int(pid))
        pidfile.unlink()
        p = Path(path.strip())
        if p.exists():
            p.write_text(mask(p.read_text(encoding="utf-8", errors="replace")), encoding="utf-8")
        emit({"ok": True, "file": str(p), "masked": True})
    elif act == "clear":
        c.run("logcat", "-c")
        emit({"ok": True, "cleared": True})
    else:
        args = ["logcat", "-d", "-v", "threadtime", "-b", "main,system,crash"] + (["-t", str(c.a.lines)] if c.a.lines else [])
        code, out, err = c.adb.cmd(*args, timeout=90)
        total = out.count("\n")
        if pkg:
            flt = AppLogFilter(pkg, app_pids(c.adb, pkg))
            flt.add_pids(pid for pid, v in process_map(out.splitlines()).items() if belongs(v["name"], pkg))
            out = "".join(ln for ln in out.splitlines(keepends=True) if flt.keep(ln))
        p = logcat_file(c, c.a.out or (f"{c.run_dir}/logs/logcat-dump-{ts()}.txt" if c.run_dir else f"logcat-dump-{ts()}.txt"))
        p.write_text(mask(out), encoding="utf-8")
        emit({"ok": code == 0, "file": str(p), "lines": out.count("\n"), "lines_total": total, "filtered": bool(pkg),
              "package": pkg, "masked": True})


def same_pid_block(lines, i, limit=40):
    """Lines of the same process (threadtime: date time PID TID …) starting at i."""
    parts = lines[i].split()
    pid = parts[2] if len(parts) > 2 else None
    block = [lines[i]]
    for ln in lines[i + 1:i + limit]:
        p = ln.split()
        if ln.startswith("---------") or (pid and len(p) > 2 and p[2] != pid):
            break
        block.append(ln)
    return block


START_PROC = re.compile(r"Start proc (\d+):([^\s/]+)/\S+(?: for .*?\{([\w.]+)/)?")
START_PROC_OLD = re.compile(r"Start proc ([\w.:]+) for .*?: pid=(\d+)")  # Android ≤ 6
RUNTIME_START = re.compile(r">>>>>> START (\S+) uid (\d+) <<<<<<")  # app_process: uiautomator, am, monkey (uid 2000)
CRASH_PROC = re.compile(r"Process: ([\w.:-]+), PID: (\d+)")
TOOL_THREADS = {"UiAutomation", "UiAutomatorThread", "monkey"}
SYSTEM_PREFIXES = ("com.android.", "com.google.android.", "android.", "system_server", "com.qualcomm.", "com.samsung.")


def tt_pid(line):
    p = line.split()
    return p[2] if len(p) > 3 and p[2].isdigit() else None


def belongs(proc, pkg):
    return bool(proc and pkg) and (proc == pkg or proc.startswith(pkg + ":"))


def process_map(lines):
    """pid -> {name, for, tool} from ActivityManager «Start proc», app_process starts and crash headers."""
    res = {}
    for ln in lines:
        m = START_PROC.search(ln)
        if m:
            res[m.group(1)] = {"name": m.group(2), "for": m.group(3), "tool": False}
            continue
        m = START_PROC_OLD.search(ln)
        if m:
            res[m.group(2)] = {"name": m.group(1), "for": None, "tool": False}
            continue
        m = RUNTIME_START.search(ln)
        if m and tt_pid(ln):
            res[tt_pid(ln)] = {"name": f"app_process ({m.group(1).split('.')[-1]}, uid {m.group(2)})", "for": None,
                               "tool": m.group(2) in ("0", "2000")}
        m = CRASH_PROC.search(ln)
        if m and m.group(2) not in res:
            res[m.group(2)] = {"name": m.group(1), "for": None, "tool": False}
    return res


def owner_of(proc, pid, thread, pmap, pkg):
    """tool | system | other-app | unknown — whose crash it is when it is not the app under test."""
    info = pmap.get(pid) or {}
    if info.get("tool") or thread in TOOL_THREADS or (proc or "").startswith(("app_process", "uiautomator", "com.android.commands")):
        return "tool"
    if not proc:
        return "unknown"
    if proc.startswith(SYSTEM_PREFIXES):
        return "system"
    return "other-app"


OWNER_NOTE = {"tool": "инструмент (uiautomator/monkey/am — в т.ч. dump-ui скила), не приложение",
              "system": "системный процесс или сервисы Google", "other-app": "другое приложение",
              "unknown": "процесс не определён (нет «Process:» и PID не принадлежит приложению)"}


def parse_crashes(log_text, pkg, known_pids=(), with_others=False):
    """FATAL EXCEPTION / native crash / ANR from a threadtime logcat.

    A crash belongs to the app only by its process: «Process: <pkg>[:sub], PID: N», or the PID is the app's
    (`Start proc N:<pkg>/…` in the log, or known_pids from ps). FATAL EXCEPTION in another process — UiAutomation of
    `uiautomator dump`, Google services, system_server, other apps — goes to other_processes, never to the app.
    ANR — only «ANR in <pkg>». Returns items (or (items, other_processes) with with_others=True).
    """
    lines = log_text.splitlines()
    pmap = process_map(lines)
    mine_pids = set(map(str, known_pids)) | {pid for pid, v in pmap.items() if belongs(v["name"], pkg)}
    items, others = [], []

    def put(rec, proc, pid, thread=""):
        rec["process"], rec["pid"] = proc, pid
        if thread:
            rec["thread"] = thread
        mine = belongs(proc, pkg) if proc else (pid in mine_pids)
        if mine or not pkg:
            items.append(rec)
            return
        info = pmap.get(pid) or {}
        own = owner_of(proc, pid, thread, pmap, pkg)
        others.append(dict({k: v for k, v in rec.items() if k != "excerpt"},
                           owner=own, note=OWNER_NOTE[own], related_to_app=info.get("for") == pkg))

    for i, ln in enumerate(lines):
        if "FATAL EXCEPTION" in ln:
            block = same_pid_block(lines, i)
            thread = ln.split("FATAL EXCEPTION:", 1)[-1].strip()
            head = next((CRASH_PROC.search(x) for x in block[:4] if CRASH_PROC.search(x)), None)
            pid_line = next((re.search(r"\bPID: (\d+)", x) for x in block[1:4] if re.search(r"\bPID: (\d+)", x)), None)
            pid = head.group(2) if head else (pid_line.group(1) if pid_line else tt_pid(ln))
            proc = head.group(1) if head else (pmap.get(pid) or {}).get("name")
            exc = next((x.split(": ", 1)[-1] for x in block[1:6]
                        if re.search(r"(Exception|Error)\b", x) and "Process:" not in x and "PID:" not in x), "")
            put({"type": "crash", "source": "logcat", "time": " ".join(ln.split()[:2]),
                 "summary": mask(exc.strip())[:200], "excerpt": mask("\n".join(block[:25]))}, proc, pid, thread)
        elif re.search(r"\bANR in ([\w.:]+)", ln):
            proc = re.search(r"\bANR in ([\w.:]+)", ln).group(1)
            block = same_pid_block(lines, i, 12)
            reason = next((x.split("Reason:", 1)[1].strip() for x in block if "Reason:" in x), "")
            pid = next((re.search(r"\bPID: (\d+)", x).group(1) for x in block if re.search(r"\bPID: (\d+)", x)), None)
            put({"type": "anr", "source": "logcat", "time": " ".join(ln.split()[:2]), "summary": mask(reason)[:200],
                 "excerpt": mask("\n".join(block))}, proc, pid)
        elif ">>> " in ln and "<<<" in ln and "pid:" in ln:
            m = re.search(r">>> ([\w.:]+) <<<", ln)
            pm = re.search(r"\bpid: (\d+)", ln)
            pid = pm.group(1) if pm else None
            proc = m.group(1) if m else (pmap.get(pid) or {}).get("name")
            block = lines[max(0, i - 3):i + 20]
            sig = next((x.split("signal", 1)[1].strip() for x in block if " signal " in x), "")
            put({"type": "native", "source": "logcat", "time": " ".join(ln.split()[:2]), "summary": ("signal " + sig)[:200],
                 "excerpt": mask("\n".join(block))}, proc, pid)
    return (items, others) if with_others else items


def dropbox_process_rx(pkg):
    return re.compile(r"^Process: " + re.escape(pkg) + r"(?::[\w.-]+)?\s*$", re.M)


def cmd_crashes(c):
    pkg = c.pkg(c.a.pkg)
    _, log, _ = c.adb.cmd("logcat", "-d", "-v", "threadtime", "-b", "crash,main,system", timeout=120)  # full log
    items, others = parse_crashes(log, pkg, app_pids(c.adb, pkg), with_others=True)
    seen = {(x["type"], x["time"][:14]) for x in items}  # "MM-DD HH:MM:SS"
    for tag, typ in (("data_app_crash", "crash"), ("data_app_anr", "anr"), ("data_app_native_crash", "native")):
        _, box, _ = c.adb.shell("dumpsys", "dropbox", "--print", tag, timeout=60)
        for entry in re.split(r"\n={20,}\n", box):
            m = re.search(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d) " + tag, entry, re.M)
            if m and dropbox_process_rx(pkg).search(entry):
                if (typ, m.group(1)[5:19]) in seen:
                    continue  # the same event already found in logcat
                first = next((x for x in entry.splitlines()[4:12] if x.strip() and not re.match(r"^\w[\w-]*: ", x)), "")
                items.append({"type": typ, "time": m.group(1), "process": pkg, "summary": mask(first.strip())[:200],
                              "source": "dropbox", "excerpt": mask("\n".join(entry.splitlines()[:25]))})
    if c.run_dir:
        p = c.run_dir / "raw" / f"crashes-{c.serial.replace(':', '_')}.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"package": pkg, "items": items, "other_processes": others}, ensure_ascii=False, indent=1),
                     encoding="utf-8")
    emit({"package": pkg, "count": len(items), "by_type": {t: sum(1 for x in items if x["type"] == t) for t in ("crash", "anr", "native")},
          "items": [{k: v for k, v in x.items() if k != "excerpt"} for x in items],
          "other_processes": others,
          "note": "other_processes — падения других процессов (инструменты, система, другие приложения): не находки "
                  "приложения; related_to_app — процесс запущен для приложения (WebView и т.п.), проверить вручную"
          if others else ""})


def parse_meminfo(text):
    res = {}
    m = re.search(r"TOTAL PSS:\s+(\d+)", text)
    if m:
        res["total_pss_kb"] = int(m.group(1))
    else:
        m = re.search(r"^\s*TOTAL\s+(\d+)", text, re.M)
        if m:
            res["total_pss_kb"] = int(m.group(1))
    m = re.search(r"TOTAL RSS:\s+(\d+)", text)
    if m:
        res["total_rss_kb"] = int(m.group(1))
    for key, name in (("Java Heap", "java_heap_kb"), ("Native Heap", "native_heap_kb"), ("Graphics", "graphics_kb"),
                      ("Code", "code_kb"), ("Stack", "stack_kb")):
        m = re.search(rf"^\s*{key}:\s+(\d+)", text, re.M)
        if m:
            res[name] = int(m.group(1))
    for key in ("Views", "Activities", "ViewRootImpl", "AppContexts", "Assets", "WebViews"):
        m = re.search(rf"\b{key}:\s+(\d+)", text)
        if m:
            res[key.lower()] = int(m.group(1))
    return res


def save_metric(c, metric, data):
    if c.run_dir:
        p = c.run_dir / "raw" / "metrics.jsonl"
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "a", encoding="utf-8") as f:
            f.write(json.dumps({"metric": metric, "serial": c.serial, "time": datetime.now().isoformat(timespec="seconds"),
                                **data}, ensure_ascii=False) + "\n")


def cmd_meminfo(c):
    pkg = c.pkg(c.a.pkg)
    _, out, _ = c.adb.shell("dumpsys", "meminfo", pkg, timeout=60)
    if "No process found" in out:
        fail(f"процесс {pkg} не запущен", 4)
    res = {"package": pkg, **parse_meminfo(out)}
    save_metric(c, "meminfo", res)
    emit(res)


def parse_gfxinfo(text):
    res = {}
    for key, name in (("Total frames rendered", "frames"), ("Janky frames", "janky"), ("Number Missed Vsync", "missed_vsync"),
                      ("Number High input latency", "high_input_latency"), ("Number Slow UI thread", "slow_ui_thread"),
                      ("Number Slow bitmap uploads", "slow_bitmap"), ("Number Slow issue draw commands", "slow_draw"),
                      ("Number Frame deadline missed", "deadline_missed")):
        m = re.search(rf"^{key}: (\d+)", text, re.M)
        if m:
            res[name] = int(m.group(1))
    m = re.search(r"^Janky frames: \d+ \(([\d.]+)%\)", text, re.M)
    if m:
        res["janky_percent"] = float(m.group(1))
    for p in (50, 90, 95, 99):
        m = re.search(rf"^{p}th percentile: (\d+)ms", text, re.M)
        if m:
            res[f"p{p}_ms"] = int(m.group(1))
    return res


def cmd_gfxinfo(c):
    pkg = c.pkg(c.a.pkg)
    if c.a.reset:
        c.adb.shell("dumpsys", "gfxinfo", pkg, "reset", timeout=30)
        emit({"ok": True, "reset": True, "package": pkg})
        return
    _, out, _ = c.adb.shell("dumpsys", "gfxinfo", pkg, timeout=60)
    res = {"package": pkg, **parse_gfxinfo(out)}
    save_metric(c, "gfxinfo", res)
    emit(res)


def cmd_batterystats(c):
    pkg = c.pkg(c.a.pkg)
    if c.a.reset:
        c.run("dumpsys", "batterystats", "--reset")
        emit({"ok": True, "reset": True})
        return
    _, out, _ = c.adb.shell("dumpsys", "batterystats", "--charged", pkg, timeout=120)
    raw = c.out_path(None, f"batterystats-{ts()}.txt", "logs")
    raw.write_text(mask(out), encoding="utf-8")
    _, dump, _ = c.adb.shell("dumpsys", "package", pkg, timeout=60)
    uid = (re.search(r"userId=(\d+)", dump) or [None, None])[1]
    est = re.findall(r"^\s+(?:Uid|UID) (u0a\d+|\d+): ([\d.]+).*$", out, re.M)
    wakelocks = len(re.findall(r"Wake lock", out))
    res = {"package": pkg, "uid": uid, "raw": str(raw), "estimated_mah": est[:5], "wake_lock_lines": wakelocks}
    save_metric(c, "batterystats", res)
    emit(res)


def cmd_size(c):
    pkg = c.pkg(c.a.pkg)
    _, paths, _ = c.adb.shell("pm", "path", pkg, timeout=20)
    total = 0
    for p in [ln.split(":", 1)[1].strip() for ln in paths.splitlines() if ln.startswith("package:")]:
        _, st, _ = c.adb.shell("stat", "-c", "%s", p, timeout=10)
        total += int(st.strip()) if st.strip().isdigit() else 0
    _, ds, _ = c.adb.shell("dumpsys", "diskstats", timeout=60)
    res = {"package": pkg, "apk_bytes_on_device": total}
    names = re.search(r'"?Package Names"?:\s*\[([^\]]*)\]', ds)
    if names:
        lst = [x.strip().strip('"') for x in names.group(1).split(",")]
        if pkg in lst:
            i = lst.index(pkg)
            for key, name in (("App Sizes", "app_bytes"), ("App Data Sizes", "data_bytes"), ("Cache Sizes", "cache_bytes")):
                m = re.search(rf'"?{key}"?:\s*\[([^\]]*)\]', ds)
                vals = m.group(1).split(",") if m else []
                if i < len(vals) and vals[i].strip().isdigit():
                    res[name] = int(vals[i].strip())
            res["note"] = "diskstats обновляется системой периодически — значения приблизительные"
    save_metric(c, "size", res)
    emit(res)


def cmd_monkey(c):
    pkg = c.pkg(c.a.pkg)
    _, acc, _ = c.adb.shell("dumpsys", "account", timeout=30)
    m = re.search(r"Accounts: (\d+)", acc)
    if m and int(m.group(1)) > 0 and not c.a.confirmed:
        c.gate(guard.result(guard.CONFIRM, "adb", {"monkey": pkg}, f"на устройстве есть аккаунты ({m.group(1)}): случайные "
                            "нажатия могут совершить действия от их имени — спросить", "base:monkey-accounts"))
    args = ["monkey", "-p", pkg, "-s", c.a.seed, "--throttle", c.a.throttle, "--pct-syskeys", "0",
            "--pct-anyevent", "0", "-v", "-v", c.a.events]
    timeout = int(c.a.events) * (int(c.a.throttle) + 50) / 1000 + 120
    code, out, err = c.run(*args, timeout=timeout)
    text = out + err
    log = c.out_path(None, f"monkey-seed{c.a.seed}-{ts()}.txt", "logs")
    log.write_text(mask(text), encoding="utf-8")
    inj = re.search(r"Events injected: (\d+)", text)
    res = {"package": pkg, "seed": int(c.a.seed), "events_requested": int(c.a.events),
           "events_injected": int(inj.group(1)) if inj else None,
           "crash": bool(re.search(r"// CRASH", text)), "anr": bool(re.search(r"// NOT RESPONDING", text)),
           "aborted": "Monkey aborted" in text, "log": str(log),
           "repro": f"adb shell monkey -p {pkg} -s {c.a.seed} --throttle {c.a.throttle} --pct-syskeys 0 -v -v {c.a.events}"}
    m = re.search(r"// Long Msg: (.+)", text)
    if m:
        res["exception"] = mask(m.group(1))[:200]
    emit(res)


# ---------- CLI ----------

def main():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--serial")
    common.add_argument("--run-dir")
    common.add_argument("--config")
    common.add_argument("--confirmed", action="store_true", help="пользователь подтвердил это действие (только confirm)")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add(name, fn, *pkg_pos):
        p = sub.add_parser(name, parents=[common])
        p.set_defaults(fn=fn)
        if "pkg" in pkg_pos:
            p.add_argument("pkg", nargs="?")
        return p

    add("devices", cmd_devices)
    add("info", cmd_info)
    add("appinfo", cmd_appinfo, "pkg")
    add("current", cmd_current)
    p = add("install", cmd_install)
    p.add_argument("apks", nargs="+")
    for f in ("--replace", "--downgrade", "--grant-all", "--allow-test"):
        p.add_argument(f, action="store_true")
    add("uninstall", cmd_uninstall, "pkg").add_argument("--keep-data", action="store_true")
    add("clear", cmd_clear, "pkg")
    p = add("launch", cmd_launch, "pkg")
    p.add_argument("--activity")
    p.add_argument("--cold", action="store_true")
    p = add("start-time", cmd_start_time, "pkg")
    p.add_argument("--activity")
    p.add_argument("--mode", default="cold", choices=["cold", "warm", "hot"])
    p.add_argument("--runs", type=int, default=5)
    add("stop", cmd_stop, "pkg")
    add("kill-bg", cmd_kill_bg, "pkg")
    p = add("trim-memory", cmd_trim_memory)
    p.add_argument("level")
    p.add_argument("pkg", nargs="?")
    p = add("deeplink", cmd_deeplink)
    p.add_argument("uri")
    p.add_argument("--package")
    p = add("dump-ui", cmd_dump_ui)
    p.add_argument("--out")
    p.add_argument("--json", dest="json_out")
    for name, fn in (("find", cmd_find), ("tap", cmd_tap), ("long-press", cmd_long_press)):
        p = add(name, fn)
        if name != "find":
            p.add_argument("x", nargs="?", type=int)
            p.add_argument("y", nargs="?", type=int)
        p.add_argument("--text")
        p.add_argument("--id")
        p.add_argument("--desc")
        p.add_argument("--index", type=int, default=0)
        p.add_argument("--exact", action="store_true")
        if name == "long-press":
            p.add_argument("--ms", type=int, default=800)
    p = add("swipe", cmd_swipe)
    for k in ("x1", "y1", "x2", "y2"):
        p.add_argument(k, type=int)
    p.add_argument("--ms", type=int, default=300)
    add("scroll", cmd_scroll).add_argument("direction", choices=["up", "down", "left", "right"])
    p = add("text", cmd_text)
    p.add_argument("value", nargs="?")
    p.add_argument("--env", help="ввести значение переменной окружения (секрет не печатается)")
    p.add_argument("--into-id")
    p.add_argument("--into-text")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--translit", action="store_true", help="не-ASCII → латиница (помечается в выводе)")
    g.add_argument("--adbkeyboard", action="store_true", help="не-ASCII через ADBKeyBoard (только эмулятор скила)")
    add("key", cmd_key).add_argument("name")
    add("screenshot", cmd_screenshot).add_argument("out", nargs="?")
    p = add("screenrecord", cmd_screenrecord)
    p.add_argument("out", nargs="?")
    p.add_argument("--seconds", type=int, default=20)
    add("shade", cmd_shade).add_argument("state", choices=["open", "close"])
    add("rotate", cmd_rotate).add_argument("mode", choices=["portrait", "landscape", "reverse-portrait", "reverse-landscape", "auto"])
    add("font-scale", cmd_font_scale).add_argument("value")
    add("density", cmd_density).add_argument("value")
    add("dark-mode", cmd_dark_mode).add_argument("mode", choices=["on", "off", "auto"])
    p = add("locale", cmd_locale)
    p.add_argument("tag")
    p.add_argument("pkg", nargs="?")
    p.add_argument("--system", action="store_true")
    add("timezone", cmd_timezone).add_argument("tz")
    p = add("network", cmd_network)
    p.add_argument("profile")
    p.add_argument("--seconds", type=int, default=5)
    p = add("battery", cmd_battery)
    p.add_argument("action", choices=["level", "unplug", "reset", "saver-on", "saver-off"])
    p.add_argument("value", nargs="?")
    add("doze", cmd_doze).add_argument("action", choices=["enter", "exit"])
    p = add("standby", cmd_standby)
    p.add_argument("state", choices=["on", "off"])
    p.add_argument("pkg", nargs="?")
    add("animations", cmd_animations).add_argument("state", choices=["off", "on"])
    add("permissions", cmd_permissions, "pkg")
    for name, rev in (("grant", False), ("revoke", True)):
        p = add(name, lambda c, rev=rev: cmd_grant(c, rev))
        p.add_argument("perm")
        p.add_argument("pkg", nargs="?")
    add("notifications", cmd_notifications, "pkg")
    p = add("logcat", cmd_logcat)
    p.add_argument("action", choices=["start", "stop", "dump", "clear"])
    p.add_argument("--out")
    p.add_argument("--package", help="пакет для фильтра (по умолчанию app.package из run-config)")
    p.add_argument("--all", action="store_true", help="весь журнал устройства, без фильтра по приложению")
    p.add_argument("--lines", type=int)
    add("logcat-follow", cmd_logcat_follow).add_argument("--package", required=True)  # internal: started by logcat start
    add("crashes", cmd_crashes, "pkg")
    add("meminfo", cmd_meminfo, "pkg")
    add("gfxinfo", cmd_gfxinfo, "pkg").add_argument("--reset", action="store_true")
    add("batterystats", cmd_batterystats, "pkg").add_argument("--reset", action="store_true")
    add("size", cmd_size, "pkg")
    p = add("monkey", cmd_monkey, "pkg")
    p.add_argument("--events", default="500")
    p.add_argument("--seed", default="42")
    p.add_argument("--throttle", default="300")
    a = ap.parse_args()
    if not su.tool_path("adb"):
        fail("adb не найден: установите platform-tools (INSTALL.md) или задайте ANDROID_HOME", 127)
    for attr in ("x", "y", "text", "id", "desc"):
        if not hasattr(a, attr):
            setattr(a, attr, None)
    a.fn(Ctx(a))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
