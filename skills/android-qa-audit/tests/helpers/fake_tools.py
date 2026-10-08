#!/usr/bin/env python3
"""Fake Android SDK tools for offline tests: aapt2, apksigner, emulator, avdmanager, sdkmanager.

  fake_tools.py <tool> [args…]      (tests create wrappers <tmp>/bin/<tool> -> python3 fake_tools.py <tool> "$@")
Environment: FAKE_ADB_FIXTURES (fixtures), FAKE_ADB_STATE (running emulators), FAKE_TOOLS_LOG (calls),
ANDROID_AVD_HOME (where avdmanager creates AVDs), FAKE_JAVA_EA=1 — sdkmanager/avdmanager print the harmless line of
their shell wrapper under early-access Java («…: test: 25-ea0: integer expression expected») to stderr.
"""
import json
import os
import sys
import time
from pathlib import Path

FIX = Path(os.environ.get("FAKE_ADB_FIXTURES", Path(__file__).resolve().parent.parent / "fixtures"))
STATE = Path(os.environ.get("FAKE_ADB_STATE", "/nonexistent"))


def fx(name):
    return (FIX / name).read_text(encoding="utf-8")


def log(tool, args):
    if os.environ.get("FAKE_TOOLS_LOG"):
        with open(os.environ["FAKE_TOOLS_LOG"], "a", encoding="utf-8") as f:
            f.write(json.dumps({"tool": tool, "args": args}, ensure_ascii=False) + "\n")


def aapt2(args):
    apk = Path(args[-1]).name
    if args[:2] == ["dump", "badging"]:
        name = "badging-other.txt" if "other" in apk else "badging-split-arm64.txt" if "arm64_v8a" in apk else "badging.txt"
        sys.stdout.write(fx(name))
        return 0
    if args[:2] == ["dump", "xmltree"]:
        sys.stdout.write(fx("manifest-xmltree.txt"))
        return 0
    return 1


def emulator(args):
    if args[:1] == ["-version"]:
        print("INFO    | Android emulator version 35.1.20.0 (build_id 12345678) (CL:N/A)")
        return 0
    if args[:1] == ["-accel-check"]:
        print("accel:\n0\nKVM (version 12) is installed and usable.\naccel")
        return 0
    if args[:1] == ["-list-avds"]:
        home = Path(os.environ.get("ANDROID_AVD_HOME", "."))
        print("\n".join(p.stem for p in sorted(home.glob("*.ini"))))
        return 0
    if "-avd" in args:
        name = args[args.index("-avd") + 1]
        port = args[args.index("-port") + 1] if "-port" in args else "5554"
        STATE.mkdir(parents=True, exist_ok=True)
        (STATE / f"emulator-{port}.json").write_text(json.dumps({"name": name, "pid": os.getpid()}), encoding="utf-8")
        print(f"INFO    | fake emulator {name} on port {port}", flush=True)
        deadline = time.time() + 120
        while time.time() < deadline and (STATE / f"emulator-{port}.json").exists():
            time.sleep(0.2)
        return 0
    return 1


def avdmanager(args):
    home = Path(os.environ["ANDROID_AVD_HOME"])
    if args[:2] == ["create", "avd"]:
        sys.stdin.read()
        name = args[args.index("-n") + 1]
        pkg = args[args.index("-k") + 1]
        dev = args[args.index("-d") + 1] if "-d" in args else "pixel_7"
        _, plat, tag, abi = pkg.split(";")
        d = home / f"{name}.avd"
        d.mkdir(parents=True)
        (d / "config.ini").write_text(f"avd.ini.encoding=UTF-8\nabi.type={abi}\nhw.device.name={dev}\nhw.ramSize=1536\n"
                                      f"hw.cpu.ncore=4\ndisk.dataPartition.size=2G\nimage.sysdir.1=system-images/{plat}/{tag}/{abi}/\n"
                                      f"tag.id={tag}\ntarget={plat}\n", encoding="utf-8")
        (home / f"{name}.ini").write_text(f"avd.ini.encoding=UTF-8\npath={d}\ntarget={plat}\n", encoding="utf-8")
        return 0
    if args[:2] == ["delete", "avd"]:
        import shutil
        name = args[args.index("-n") + 1]
        shutil.rmtree(home / f"{name}.avd", ignore_errors=True)
        (home / f"{name}.ini").unlink()
        return 0
    if args[:3] == ["list", "device", "-c"]:
        print("pixel_7\nsmall_phone\npixel_tablet\npixel_fold")
        return 0
    return 1


def sdkmanager(args):
    if args[:1] == ["--version"]:
        print("19.0")
        return 0
    if args[:1] == ["--list"]:
        sys.stdout.write(fx("sdkmanager-list.txt").replace("HOSTABI", os.environ.get("FAKE_HOST_ABI", "arm64-v8a")))
        return 0
    if args[:1] == ["--install"]:
        data = sys.stdin.read()
        if "y" not in data:
            print("License android-sdk-license:\nAccept? (y/N): Skipping following packages as the license is not accepted:")
            return 1
        print(f"[=======================================] 100% Unzipping... {args[1]}\ndone")
        return 0
    return 1


def main():
    tool, args = sys.argv[1], sys.argv[2:]
    log(tool, args)
    if tool in ("sdkmanager", "avdmanager") and os.environ.get("FAKE_JAVA_EA") == "1":
        sys.stderr.write(f"/fake/sdk/cmdline-tools/latest/bin/{tool}: line 173: test: 25-ea0: integer expression expected\n")
        sys.stderr.flush()
    if tool == "aapt2":
        sys.exit(aapt2(args))
    if tool == "apksigner":
        sys.stdout.write(fx("apksigner-debug.txt"))
        sys.exit(0)
    if tool == "emulator":
        sys.exit(emulator(args))
    if tool == "avdmanager":
        sys.exit(avdmanager(args))
    if tool == "sdkmanager":
        sys.exit(sdkmanager(args))
    sys.exit(1)


if __name__ == "__main__":
    main()
