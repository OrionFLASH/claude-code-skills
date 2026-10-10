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
  FAKE_ADB_MEMINFO_DELAY S — `dumpsys meminfo` answers after S seconds (a hung soak sample)
  1.5.0 clips (state in FAKE_ADB_STATE): `screenrecord … REMOTE` runs until its --time-limit or until `kill -2 <pid>`
                     (or SIGINT), then «writes» REMOTE — a copy of FAKE_ADB_SCREENRECORD_FILE (default: a few bytes
                     with ftyp/moov) into FAKE_ADB_STATE/remote/; `pidof screenrecord`, `ps -A -o PID,ARGS` show it;
                     `pull` / `rm -f` of /sdcard/qa-clip-* and /sdcard/qa-roll-* use that folder (missing → error).
                     FAKE_ADB_SCREENRECORD_FAIL=codec — screenrecord fails at once (no hardware encoder);
                     FAKE_ADB_SCREENRECORD_NOFILE=1 — screenrecord stops but writes no file (pull fails);
                     FAKE_ADB_NO_SCREENRECORD=1 — no /system/bin/screenrecord. `settings get/put system show_touches |
                     pointer_location` — stored per serial (FAKE_ADB_TOUCHES — initial show_touches, default 0).
                     FAKE_ADB_STATE/offline-<serial> exists → every command for that serial: «device not found».
                     FAKE_ADB_ANR=1 — `dumpsys window windows` shows the ANR dialog of com.example.app.
                     FAKE_ADB_SCREENCAP_FILE — `exec-out screencap -p` returns this PNG (default: a stub header).
Serials: emulator-* — emulator properties (getprop-emulator.txt); anything else — real phone (getprop-real.txt).
Screen: natural 1080x2400; rotation 1/3 — 2400x1080 and window_dump_landscape.xml.
"""
import json
import os
import shlex
import shutil
import signal
import sys
import time
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


FAKE_MP4 = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom" + b"\x00\x00\x00\x08moov" + b"\x00" * 64
SKILL_TMP = ("/sdcard/qa-clip-", "/sdcard/qa-roll-")


def remote_file(path):
    return STATE / "remote" / Path(path).name


def sr_state(serial):
    p = STATE / f"sr-{serial}.json"
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    try:
        os.kill(int(d["pid"]), 0)
    except (OSError, ValueError, KeyError):
        p.unlink(missing_ok=True)
        return None
    return d


def screenrecord(serial, rest, line):
    if os.environ.get("FAKE_ADB_SCREENRECORD_FAIL") == "codec":
        sys.stderr.write("ERROR: unable to configure video/avc codec (err=-38)\n")
        sys.exit(1)
    limit = float(rest[rest.index("--time-limit") + 1]) if "--time-limit" in rest else 180.0
    remote = rest[-1]
    STATE.mkdir(parents=True, exist_ok=True)
    me = STATE / f"sr-{serial}.json"
    me.write_text(json.dumps({"pid": os.getpid(), "remote": remote, "args": line}), encoding="utf-8")
    stop = STATE / f"sr-stop-{os.getpid()}"
    got = {"int": False}

    def on_int(*_):
        got["int"] = True
    signal.signal(signal.SIGINT, on_int)
    start = time.time()
    while time.time() - start < limit and not stop.exists() and not got["int"]:
        time.sleep(0.03)
    stop.unlink(missing_ok=True)
    (STATE / "remote").mkdir(parents=True, exist_ok=True)
    src = os.environ.get("FAKE_ADB_SCREENRECORD_FILE")

    def release():                       # only our own registration (a newer recorder may have replaced it)
        try:
            if json.loads(me.read_text(encoding="utf-8")).get("pid") == os.getpid():
                me.unlink()
        except (OSError, ValueError):
            pass
    if os.environ.get("FAKE_ADB_SCREENRECORD_NOFILE") == "1":      # the device lost the file (pull fails)
        release()
        sys.exit(0)
    if src:
        shutil.copyfile(src, remote_file(remote))
    else:
        remote_file(remote).write_bytes(FAKE_MP4)
    release()
    sys.exit(0)


def settings_store(serial):
    p = STATE / f"settings-{serial}.json"
    try:
        return p, json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return p, {"show_touches": os.environ.get("FAKE_ADB_TOUCHES", "0"), "pointer_location": "0"}


def shell(serial, line):
    try:
        t = shlex.split(line)
    except ValueError:
        t = line.split()
    if not t:
        out()
    c, rest = t[0], t[1:]
    real = not serial.startswith("emulator-")
    if c == "screenrecord":
        screenrecord(serial, rest, line)
    if c == "which":
        if rest[:1] == ["screenrecord"] and os.environ.get("FAKE_ADB_NO_SCREENRECORD") != "1":
            out("/system/bin/screenrecord\n")
        out("", 1)
    if c == "pidof" and rest == ["screenrecord"]:
        d = sr_state(serial)
        out(f"{d['pid']}\n" if d else "", 0 if d else 1)
    if c == "ps" and "-o" in rest and "PID,ARGS" in rest:
        d = sr_state(serial)
        out("PID ARGS\n1 /init\n600 system_server\n" + (f"{d['pid']} {d['args']}\n" if d else ""))
    if c == "kill":
        pids = [x for x in rest if x.isdigit()]
        d = sr_state(serial)
        if d and str(d["pid"]) in pids and ("-2" in rest or "-INT" in rest or "INT" in rest):
            (STATE / f"sr-stop-{d['pid']}").write_text("1")
            out()
        out(f"kill: {pids[0] if pids else '?'}: No such process\n", 1)
    if c == "rm" and any(x.startswith(SKILL_TMP) for x in rest):
        for x in rest:
            if x.startswith(SKILL_TMP):
                remote_file(x).unlink(missing_ok=True)
        out()
    if c == "stat" and rest[-1:] and rest[-1].startswith(SKILL_TMP):
        f = remote_file(rest[-1])
        out(f"{f.stat().st_size}\n" if f.exists() else f"stat: {rest[-1]}: No such file or directory\n", 0 if f.exists() else 1)
    if c == "settings" and len(rest) >= 3 and rest[1] == "system" and rest[2] in ("show_touches", "pointer_location"):
        p, d = settings_store(serial)
        if rest[0] == "get":
            out(d.get(rest[2], "0") + "\n")
        if rest[0] in ("put", "delete"):
            if rest[0] == "put" and len(rest) > 3:
                d[rest[2]] = rest[3]
            elif rest[0] == "delete":
                d[rest[2]] = "null"
            STATE.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(d), encoding="utf-8")
            out()
    if c == "dumpsys" and rest[:2] == ["window", "windows"]:
        out("WINDOW MANAGER WINDOWS (dumpsys window windows)\n" + (
            "  Window #5 Window{9f1 u0 Application Not Responding: com.example.app}:\n" if os.environ.get("FAKE_ADB_ANR") == "1" else ""))
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
            if what == "meminfo" and os.environ.get("FAKE_ADB_MEMINFO_DELAY"):   # a hung sample (job stop tests)
                import time
                time.sleep(float(os.environ["FAKE_ADB_MEMINFO_DELAY"]))
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
    if serial and STATE != Path("/nonexistent") and (STATE / f"offline-{serial}").exists() and args[0] not in ("devices", "version"):
        sys.stderr.write(f"error: device '{serial}' not found\n")
        sys.exit(1)
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
    if cmd == "pull" and rest and rest[0].startswith(SKILL_TMP):
        f = remote_file(rest[0])
        if not f.exists():
            sys.stderr.write(f"adb: error: failed to stat remote object '{rest[0]}': No such file or directory\n")
            sys.exit(1)
        shutil.copyfile(f, rest[-1])
        out(f"{rest[0]}: 1 file pulled\n")
    if cmd == "get-state":
        out("device\n")
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
            src = os.environ.get("FAKE_ADB_SCREENCAP_FILE")      # a real PNG (clip --fallback frames tests)
            sys.stdout.buffer.write(Path(src).read_bytes() if src else PNG)
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
