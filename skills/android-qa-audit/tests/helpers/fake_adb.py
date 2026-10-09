#!/usr/bin/env python3
"""Fake adb for offline tests of android-qa-audit. No device, no network.

Environment:
  FAKE_ADB_FIXTURES  folder with fixtures (adb-devices.txt, getprop-*.txt, window_dump.xml, dumpsys-*.txt, …)
  FAKE_ADB_LOG       every call is appended as a JSON line {"serial": …, "args": […]}
  FAKE_ADB_STATE     folder with running fake emulators: emulator-<port>.json {"name", "pid"} (written by fake_tools.py)
                     and the screen rotation of a device: rotation-<serial>.txt (set by `cmd window user-rotation lock N`)
  FAKE_ADB_LOGCAT    logcat fixture (default logcat-crash.txt)
  FAKE_ADB_IME       extra line for `ime list -a -s` (e.g. com.android.adbkeyboard/.AdbIME)
  FAKE_ADB_DISCOVERY path printed by `emu avd discoverypath` (emulator gRPC discovery ini); unset — «KO»
  FAKE_ADB_DUMP_FAIL N — the first N `uiautomator dump` calls fail with «could not get idle state» (counter in
                     FAKE_ADB_STATE); «always» — every call fails
  FAKE_ADB_UI_FLOW   JSON {"state": "<screen>", "screens": {"<screen>": {"xml": "<fixture>", "focus": "pkg/.Activity",
                     "taps": [{"bounds": [x1, y1, x2, y2], "to": "<screen>"}], "swipe": "<screen>"}}}: the screen
                     (dump, focus) changes with `input tap` / `input swipe` (state in FAKE_ADB_STATE/ui-<serial>.txt)
  FAKE_ADB_NOTIF     notification fixture (default dumpsys-notification.txt)
  FAKE_ADB_SERVICES  fixture for `dumpsys activity services`; FAKE_ADB_SERVICES_UNTIL N — present only N calls
  FAKE_ADB_PIDOF_UNTIL N — `pidof`/`ps` show the app only for the first N calls (process death)
  FAKE_ADB_PULL_FILE file copied by `adb pull` (default: «fake-mp4» bytes); FAKE_ADB_LS — output of `ls`
Serials: emulator-* — emulator properties (getprop-emulator.txt); anything else — real phone (getprop-real.txt).
Screen: natural 1080x2400; rotation 1/3 — 2400x1080 and window_dump_landscape.xml.
"""
import json
import os
import shlex
import shutil
import signal
import sys
from pathlib import Path

FIX = Path(os.environ.get("FAKE_ADB_FIXTURES", Path(__file__).resolve().parent.parent / "fixtures"))
STATE = Path(os.environ.get("FAKE_ADB_STATE", "/nonexistent"))
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def counter(name):
    """Increment and return a per-test counter (FAKE_ADB_STATE/<name>.count)."""
    if STATE == Path("/nonexistent"):
        return 1
    STATE.mkdir(parents=True, exist_ok=True)
    p = STATE / f"{name}.count"
    n = int(p.read_text() or 0) + 1 if p.exists() else 1
    p.write_text(str(n))
    return n


def flow():
    f = os.environ.get("FAKE_ADB_UI_FLOW")
    if not f:
        return None
    return json.loads(Path(f).read_text(encoding="utf-8"))


def flow_state(serial, fl):
    p = STATE / f"ui-{serial}.txt"
    return p.read_text(encoding="utf-8").strip() if p.exists() else fl["state"]


def flow_set(serial, name):
    STATE.mkdir(parents=True, exist_ok=True)
    (STATE / f"ui-{serial}.txt").write_text(name, encoding="utf-8")


def flow_screen(serial):
    fl = flow()
    if not fl:
        return None
    return fl["screens"][flow_state(serial, fl)]


def fx(name, default=""):
    p = FIX / name
    return p.read_text(encoding="utf-8") if p.exists() else default


def out(text="", code=0):
    sys.stdout.write(text)
    sys.exit(code)


def running():
    res = {}
    if STATE.is_dir():
        for p in STATE.glob("emulator-*.json"):
            try:
                res[p.stem] = json.loads(p.read_text(encoding="utf-8"))
            except ValueError:
                continue
    return res


def devices():
    text = fx("adb-devices.txt", "List of devices attached\n")
    for serial in running():
        text += f"{serial}          device product:sdk_gphone64 model:sdk_gphone64 device:emu64 transport_id:9\n"
    return text


def rotation(serial):
    p = STATE / f"rotation-{serial}.txt"
    try:
        return int(p.read_text(encoding="utf-8").strip() or 0)
    except (OSError, ValueError):
        return 0


def set_rotation(serial, n):
    if STATE != Path("/nonexistent"):
        STATE.mkdir(parents=True, exist_ok=True)
        (STATE / f"rotation-{serial}.txt").write_text(str(n), encoding="utf-8")


def shell(serial, line):
    try:
        t = shlex.split(line)
    except ValueError:
        t = line.split()
    if not t:
        out()
    c, rest = t[0], t[1:]
    real = not serial.startswith("emulator-")
    if c == "getprop":
        props = fx("getprop-real.txt" if real else "getprop-emulator.txt")
        if not rest:
            out(props)
        key = rest[0]
        for ln in props.splitlines():
            if ln.startswith(f"[{key}]:"):
                out(ln.split(": [", 1)[1].rstrip("]") + "\n")
        out("\n")
    if c == "uiautomator":
        fail = os.environ.get("FAKE_ADB_DUMP_FAIL")
        if fail and (fail == "always" or counter(f"dump-{serial}") <= int(fail)):
            out("ERROR: could not get idle state.\n", 0)
        out("UI hierchary dumped to: /sdcard/qa-window_dump.xml\n")
    if c == "wm":
        if rest[:1] == ["size"] and len(rest) == 1:
            out("Physical size: 1080x2400\n")
        if rest[:1] == ["density"] and len(rest) == 1:
            out("Physical density: 420\n")
        out()
    if c == "dumpsys":
        what = rest[0] if rest else ""
        if what == "activity" and rest[1:2] == ["services"]:
            until = os.environ.get("FAKE_ADB_SERVICES_UNTIL")
            if os.environ.get("FAKE_ADB_SERVICES") and (not until or counter(f"svc-{serial}") <= int(until)):
                out(fx(os.environ["FAKE_ADB_SERVICES"]))
            out("ACTIVITY MANAGER SERVICES (dumpsys activity services)\n  (nothing)\n")
        if what == "activity":
            scr = flow_screen(serial)
            focus = scr["focus"] if scr else "com.example.app/.MainActivity"
            out(f"  topResumedActivity=ActivityRecord{{1a2b u0 {focus} t12}}\n")
        if what == "notification":
            out(fx(os.environ.get("FAKE_ADB_NOTIF", "dumpsys-notification.txt")))
        if what == "thermalservice":
            out("IsStatusOverride: false\nThermal Status: 1\n")
        if what in ("meminfo", "gfxinfo", "package", "notification", "diskstats"):
            if what == "gfxinfo" and "reset" in rest:
                out()
            out(fx(f"dumpsys-{what}.txt"))
        if what == "account":
            out(fx("dumpsys-account.txt", "Accounts: 0\n"))
        if what == "input":  # Android 13+: no SurfaceOrientation line (the size must come from elsewhere)
            out("INPUT MANAGER (dumpsys input)\n\nInput Reader State (Nums of device: 1):\n")
        if what == "window" and rest[1:2] == ["displays"]:
            r = rotation(serial)
            cur = "2400x1080" if r in (1, 3) else "1080x2400"
            out(f"WINDOW MANAGER DISPLAY CONTENTS (dumpsys window displays)\n  Display: mDisplayId=0 rootTasks=2\n"
                f"    init=1080x2400 420dpi base=1080x2400 420dpi cur={cur} app={cur} rng=1080x1017-2400x2337\n"
                f"  DisplayRotation\n    mRotation={r} mDeferredRotationPauseCount=0\n")
        if what == "battery":
            out("Current Battery Service state:\n  level: 100\n")
        out()
    if c == "am":
        sub = rest[0] if rest else ""
        if sub == "start":
            out(fx("am-start-cold.txt"))
        out()
    if c == "cmd":
        if rest[:3] == ["window", "user-rotation", "lock"] and len(rest) > 3:
            set_rotation(serial, int(rest[3]))
            out()
        if rest[:2] == ["package", "resolve-activity"]:
            out("priority=0 preferredOrder=0 match=0x108000 specificIndex=-1 isDefault=true\ncom.example.app/.MainActivity\n")
        if rest[:2] == ["uimode", "night"]:
            out("Night mode: " + (rest[2] if len(rest) > 2 else "no") + "\n")
        out()
    if c == "pm":
        if rest[:1] == ["clear"]:
            out("Success\n")
        if rest[:1] == ["path"]:
            paths = {"com.example.app": "package:/data/app/~~AbC==/com.example.app-XyZ==/base.apk\n",
                     "android": "package:/system/framework/framework-res.apk\n"}
            out(paths.get(rest[-1], ""), 0)
        out()
    if c == "monkey":
        out(fx("monkey-crash.txt"))
    if c in ("pidof", "ps"):
        until = os.environ.get("FAKE_ADB_PIDOF_UNTIL")
        alive = not until or counter(f"pid-{serial}-{c}") <= int(until)
        if c == "pidof":
            out("1234\n" if alive else "", 0 if alive else 1)
        out("PID NAME\n1\tinit\n600 system_server\n" + ("1234 com.example.app\n" if alive else "") + "5678 com.other.app\n")
    if c == "df":
        out("Filesystem      1K-blocks    Used Available Use% Mounted on\n/dev/block/dm-5   6082264 2370436   3696356  40% /data\n")
    if c == "ls":
        out(os.environ.get("FAKE_ADB_LS", "") + "\n")
    if c == "input":
        fl = flow()
        if fl and rest[:1] == ["tap"] and len(rest) >= 3:
            x, y = int(float(rest[1])), int(float(rest[2]))
            scr = fl["screens"][flow_state(serial, fl)]
            for tp in scr.get("taps", []):
                b = tp["bounds"]
                if b[0] <= x <= b[2] and b[1] <= y <= b[3]:
                    flow_set(serial, tp["to"])
                    break
        if fl and rest[:1] == ["swipe"]:
            scr = fl["screens"][flow_state(serial, fl)]
            if scr.get("swipe"):
                flow_set(serial, scr["swipe"])
        out()
    if c == "settings" and rest[:3] == ["put", "system", "user_rotation"] and len(rest) > 3:
        set_rotation(serial, int(rest[3]))
        out()
    if c == "settings" and rest[:3] == ["get", "secure", "default_input_method"]:
        out("com.android.inputmethod.latin/.LatinIME\n")
    if c == "settings" and rest[:1] == ["get"]:
        out("1.0\n")
    if c == "ime":
        if rest[:1] == ["list"]:
            out("com.android.inputmethod.latin/.LatinIME\n" + (os.environ.get("FAKE_ADB_IME", "") + "\n").lstrip("\n"))
        out()
    if c == "stat":
        out("15000000\n")
    out()


def main():
    args = sys.argv[1:]
    serial = os.environ.get("ANDROID_SERIAL", "")
    while args and args[0] in ("-s", "-t", "-H", "-P"):
        if args[0] == "-s":
            serial = args[1]
        args = args[2:]
    if os.environ.get("FAKE_ADB_LOG"):
        with open(os.environ["FAKE_ADB_LOG"], "a", encoding="utf-8") as f:
            f.write(json.dumps({"serial": serial, "args": args}, ensure_ascii=False) + "\n")
    if not args:
        out("", 1)
    cmd, rest = args[0], args[1:]
    if cmd == "version":
        out("Android Debug Bridge version 1.0.41\nVersion 35.0.2-12147458\nInstalled as /fake/adb\n")
    if cmd == "devices":
        out(devices())
    if cmd == "get-state":
        out("device\n")
    if cmd == "emu":
        emus = running()
        if rest[:2] == ["avd", "name"]:
            name = (emus.get(serial) or {}).get("name") or fx("emu-avd-name.txt", "qa-api34-pixel7-2gb-2c").strip()
            out(f"{name}\nOK\n")
        if rest[:2] == ["avd", "discoverypath"]:
            d = os.environ.get("FAKE_ADB_DISCOVERY")
            out(f"{d}\nOK\n" if d else "KO: unknown command\n")
        if rest[:1] == ["kill"]:
            info = emus.get(serial)
            if info:
                try:
                    os.kill(int(info["pid"]), signal.SIGTERM)
                except OSError:
                    pass
                (STATE / f"{serial}.json").unlink()
            out("OK: killing emulator, bye bye\n")
        out("OK\n")
    if cmd in ("install", "install-multiple"):
        out("Performing Streamed Install\nSuccess\n")
    if cmd == "uninstall":
        out("Success\n")
    if cmd == "pull":
        src = os.environ.get("FAKE_ADB_PULL_FILE")
        if src:
            shutil.copyfile(src, rest[-1])
        else:
            Path(rest[-1]).write_bytes(b"fake-mp4")
        out(f"{rest[-2]}: 1 file pulled\n")
    if cmd == "push":
        out(f"{rest[0]}: 1 file pushed, 0 skipped.\n")
    if cmd == "exec-out":
        if rest[:1] == ["screencap"]:
            sys.stdout.buffer.write(PNG)
            sys.exit(0)
        if rest[:1] == ["cat"]:
            scr = flow_screen(serial)
            if scr:
                out(fx(scr["xml"]))
            out(fx("window_dump_landscape.xml" if rotation(serial) in (1, 3) else "window_dump.xml"))
        out()
    if cmd == "logcat":  # -d (dump) and streaming: the fixture, then the stream ends
        out(fx(os.environ.get("FAKE_ADB_LOGCAT", "logcat-crash.txt")))
    if cmd == "shell":
        shell(serial, " ".join(rest))
    out()


if __name__ == "__main__":
    main()
