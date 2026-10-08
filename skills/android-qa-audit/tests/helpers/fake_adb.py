#!/usr/bin/env python3
"""Fake adb for offline tests of android-qa-audit. No device, no network.

Environment:
  FAKE_ADB_FIXTURES  folder with fixtures (adb-devices.txt, getprop-*.txt, window_dump.xml, dumpsys-*.txt, …)
  FAKE_ADB_LOG       every call is appended as a JSON line {"serial": …, "args": […]}
  FAKE_ADB_STATE     folder with running fake emulators: emulator-<port>.json {"name", "pid"} (written by fake_tools.py)
                     and the screen rotation of a device: rotation-<serial>.txt (set by `cmd window user-rotation lock N`)
  FAKE_ADB_LOGCAT    logcat fixture (default logcat-crash.txt)
  FAKE_ADB_IME       extra line for `ime list -a -s` (e.g. com.android.adbkeyboard/.AdbIME)
Serials: emulator-* — emulator properties (getprop-emulator.txt); anything else — real phone (getprop-real.txt).
Screen: natural 1080x2400; rotation 1/3 — 2400x1080 and window_dump_landscape.xml.
"""
import json
import os
import shlex
import signal
import sys
from pathlib import Path

FIX = Path(os.environ.get("FAKE_ADB_FIXTURES", Path(__file__).resolve().parent.parent / "fixtures"))
STATE = Path(os.environ.get("FAKE_ADB_STATE", "/nonexistent"))
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


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
        out("UI hierchary dumped to: /sdcard/qa-window_dump.xml\n")
    if c == "wm":
        if rest[:1] == ["size"] and len(rest) == 1:
            out("Physical size: 1080x2400\n")
        if rest[:1] == ["density"] and len(rest) == 1:
            out("Physical density: 420\n")
        out()
    if c == "dumpsys":
        what = rest[0] if rest else ""
        if what == "activity":
            out("  topResumedActivity=ActivityRecord{1a2b u0 com.example.app/.MainActivity t12}\n")
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
    if c == "pidof":
        out("1234\n")
    if c == "ps":
        out("PID NAME\n1\tinit\n600 system_server\n1234 com.example.app\n5678 com.other.app\n")
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
        Path(rest[-1]).write_bytes(b"fake-mp4")
        out(f"{rest[-2]}: 1 file pulled\n")
    if cmd == "exec-out":
        if rest[:1] == ["screencap"]:
            sys.stdout.buffer.write(PNG)
            sys.exit(0)
        if rest[:1] == ["cat"]:
            out(fx("window_dump_landscape.xml" if rotation(serial) in (1, 3) else "window_dump.xml"))
        out()
    if cmd == "logcat":  # -d (dump) and streaming: the fixture, then the stream ends
        out(fx(os.environ.get("FAKE_ADB_LOGCAT", "logcat-crash.txt")))
    if cmd == "shell":
        shell(serial, " ".join(rest))
    out()


if __name__ == "__main__":
    main()
