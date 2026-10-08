#!/usr/bin/env python3
"""Android SDK discovery and safe process helpers for android-qa-audit (Python 3.9+, standard library only).

Used by check_env.py, apk_info.py, avd_manager.py, adb_helpers.py — not a CLI of its own
(`python3 sdkutil.py` prints what was found, for debugging).

Tool lookup order (adb, emulator, sdkmanager, avdmanager, aapt2, aapt, apksigner, bundletool):
  1. environment override ANDROID_QA_<TOOL> (full path; used by tests with fake tools);
  2. the Android SDK: ANDROID_HOME, ANDROID_SDK_ROOT, then typical folders
     (macOS ~/Library/Android/sdk, Windows %LOCALAPPDATA%\\Android\\Sdk, Linux ~/Android/Sdk,
     Homebrew android-commandlinetools, /opt/android-sdk), or the SDK that owns an adb found in PATH;
  3. PATH.
The SDK does not have to be in PATH: scripts call tools by full path.
"""
import json
import os
import platform
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

IS_WIN = os.name == "nt"
EXE = ".exe" if IS_WIN else ""
BAT = ".bat" if IS_WIN else ""

# Android release for an API level (display only).
ANDROID_VERSIONS = {21: "5.0", 22: "5.1", 23: "6.0", 24: "7.0", 25: "7.1", 26: "8.0", 27: "8.1", 28: "9",
                    29: "10", 30: "11", 31: "12", 32: "12L", 33: "13", 34: "14", 35: "15", 36: "16", 37: "17"}

TOOLS = {  # name -> (sdk sub-folders in priority order, file name without extension, kind)
    "adb": (["platform-tools"], "adb", EXE),
    "emulator": (["emulator"], "emulator", EXE),
    "sdkmanager": (["@cmdline", "tools/bin"], "sdkmanager", BAT),
    "avdmanager": (["@cmdline", "tools/bin"], "avdmanager", BAT),
    "apkanalyzer": (["@cmdline", "tools/bin"], "apkanalyzer", BAT),
    "aapt2": (["@build"], "aapt2", EXE),
    "aapt": (["@build"], "aapt", EXE),
    "apksigner": (["@build"], "apksigner", BAT),
    "zipalign": (["@build"], "zipalign", EXE),
    "bundletool": ([], "bundletool", BAT),
}


def env_name(tool):
    return "ANDROID_QA_" + tool.upper()


# ---------- processes ----------

def run(cmd, timeout=60, input=None, cwd=None, binary=False, env=None):
    """Run a command (list, shell=False). Returns (code, stdout, stderr).

    127 — not found, 126 — not executable, 124 — timeout. Never raises for these cases.
    """
    try:
        p = subprocess.run([str(c) for c in cmd], capture_output=True, timeout=timeout, cwd=cwd, env=env, input=input,
                           **({} if binary else {"text": True, "encoding": "utf-8", "errors": "replace"}))
        return p.returncode, p.stdout if p.stdout is not None else (b"" if binary else ""), \
            (p.stderr.decode("utf-8", "replace") if binary else p.stderr) or ""
    except FileNotFoundError:
        return 127, b"" if binary else "", f"не найдено: {cmd[0]}"
    except PermissionError:
        return 126, b"" if binary else "", f"нет прав на запуск: {cmd[0]}"
    except subprocess.TimeoutExpired as ex:
        out = ex.stdout or (b"" if binary else "")
        if not binary and isinstance(out, bytes):
            out = out.decode("utf-8", "replace")
        return 124, out, f"таймаут {timeout} с: {' '.join(str(c) for c in cmd[:4])}"
    except OSError as ex:
        return 126, b"" if binary else "", f"{cmd[0]}: {ex}"


JAVA_NOISE = "integer expression expected"


def strip_java_noise(text):
    """Remove the harmless line of the cmdline-tools shell wrapper under early-access Java ('25-ea'):
    `…/sdkmanager: line 173: test: 25-ea0: integer expression expected`. Returns (text, removed lines)."""
    lines = (text or "").splitlines(keepends=True)
    keep = [ln for ln in lines if JAVA_NOISE not in ln]
    return "".join(keep), len(lines) - len(keep)


def run_sdk_tool(cmd, **kw):
    """run() for sdkmanager / avdmanager: (code, out, err, noise). The Java -ea noise is removed only when the
    command succeeded (code 0) — then it is harmless; on failure everything stays visible."""
    code, out, err = run(cmd, **kw)
    o, n1 = strip_java_noise(out)
    e, n2 = strip_java_noise(err)
    if code == 0:
        return code, o, e, n1 + n2
    return code, out, err, n1 + n2


def popen_detached(cmd, log_path, env=None):
    """Start a long-running process in the background (emulator, logcat). Returns the Popen object."""
    log_path = Path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log = open(log_path, "ab")
    kw = {"stdout": log, "stderr": subprocess.STDOUT, "stdin": subprocess.DEVNULL, "env": env}
    if IS_WIN:
        kw["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x200) | 0x00000008  # DETACHED_PROCESS
    else:
        kw["start_new_session"] = True
    return subprocess.Popen([str(c) for c in cmd], **kw)


def pid_alive(pid):
    if not pid:
        return False
    if IS_WIN:
        code, out, _ = run(["tasklist", "/FI", f"PID eq {int(pid)}", "/NH"], timeout=10)
        return code == 0 and str(int(pid)) in out
    try:
        os.kill(int(pid), 0)
        return True
    except (OSError, ValueError):
        return False


def kill_pid(pid):
    """Terminate a background process started by the skill (logcat). True if a signal was sent."""
    if not pid_alive(pid):
        return False
    if IS_WIN:
        return run(["taskkill", "/PID", str(int(pid)), "/T", "/F"], timeout=15)[0] == 0
    import signal
    try:
        os.kill(int(pid), signal.SIGTERM)
        return True
    except OSError:
        return False


# ---------- SDK and tools ----------

def _home():
    return Path(os.path.expanduser("~"))


def sdk_candidates():
    """Possible SDK roots in priority order (existing or not), with the reason."""
    out = []
    for var in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
        if os.environ.get(var):
            out.append((Path(os.environ[var]).expanduser(), var))
    home = _home()
    if sys.platform == "darwin":
        out += [(home / "Library/Android/sdk", "типовой путь macOS"),
                (Path("/opt/homebrew/share/android-commandlinetools"), "Homebrew (Apple Silicon)"),
                (Path("/usr/local/share/android-commandlinetools"), "Homebrew (Intel)")]
    elif IS_WIN:
        local = os.environ.get("LOCALAPPDATA") or str(home / "AppData/Local")
        out += [(Path(local) / "Android" / "Sdk", "типовой путь Windows")]
    else:
        out += [(home / "Android/Sdk", "типовой путь Linux"), (Path("/opt/android-sdk"), "/opt/android-sdk"),
                (Path("/usr/lib/android-sdk"), "пакет дистрибутива")]
    adb = shutil.which("adb")
    if adb:
        real = Path(os.path.realpath(adb))
        if real.parent.name == "platform-tools":
            out.append((real.parent.parent, "SDK, которому принадлежит adb из PATH"))
    return out


def looks_like_sdk(p):
    return p.is_dir() and any((p / d).is_dir() for d in ("platform-tools", "cmdline-tools", "emulator", "build-tools"))


def find_sdk():
    """(path, reason) of the first existing SDK root, or (None, None)."""
    for p, why in sdk_candidates():
        if looks_like_sdk(p):
            return p.resolve(), why
    return None, None


def _ver_key(name):
    nums = [int(x) for x in re.findall(r"\d+", name)[:4]]
    pre = 0 if re.search(r"rc|alpha|beta|preview", name, re.I) else 1
    return nums + [0] * (4 - len(nums)) + [pre]


def build_tools_dirs(sdk):
    d = Path(sdk) / "build-tools" if sdk else None
    if not d or not d.is_dir():
        return []
    return sorted((x for x in d.iterdir() if x.is_dir() and re.match(r"\d", x.name)), key=lambda x: _ver_key(x.name),
                  reverse=True)


def cmdline_dirs(sdk):
    d = Path(sdk) / "cmdline-tools" if sdk else None
    if not d or not d.is_dir():
        return []
    dirs = [x for x in d.iterdir() if x.is_dir()]
    latest = [x for x in dirs if x.name == "latest"]
    rest = sorted((x for x in dirs if x.name != "latest"), key=lambda x: _ver_key(x.name), reverse=True)
    return [x / "bin" for x in latest + rest]


def find_tool(name, sdk=None):
    """{'name', 'path', 'source': env|sdk|path|None, 'in_path': bool}."""
    subdirs, base, ext = TOOLS.get(name, ([], name, EXE))
    in_path = shutil.which(base) is not None
    res = {"name": name, "path": None, "source": None, "in_path": in_path}
    override = os.environ.get(env_name(name))
    if override:
        res.update(path=override, source="env")
        return res
    if sdk is None:
        sdk, _ = find_sdk()
    if sdk:
        dirs = []
        for sd in subdirs:
            if sd == "@cmdline":
                dirs += cmdline_dirs(sdk)
            elif sd == "@build":
                dirs += build_tools_dirs(sdk)
            else:
                dirs.append(Path(sdk) / sd)
        for d in dirs:
            for cand in ([d / (base + ext)] + ([d / base] if ext else [])):
                if cand.is_file():
                    res.update(path=str(cand), source="sdk")
                    return res
    found = shutil.which(base)
    if found:
        res.update(path=found, source="path")
    return res


def tool_path(name, sdk=None):
    return find_tool(name, sdk)["path"]


def source_props(path):
    """key=value from source.properties / *.ini files."""
    data = {}
    try:
        for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if line and not line.startswith(("#", ";")) and "=" in line:
                k, v = line.split("=", 1)
                data[k.strip()] = v.strip()
    except OSError:
        pass
    return data


parse_ini = source_props


def parse_api(text):
    """'android-34' -> 34, 'android-37.0' -> 37, '34' -> 34; codenames -> None."""
    m = re.search(r"(?:android-)?(\d+)(?:\.\d+)?$", str(text or "").strip())
    return int(m.group(1)) if m else None


def api_label(api):
    if api is None:
        return "API ?"
    return f"API {api}" + (f" (Android {ANDROID_VERSIONS[api]})" if api in ANDROID_VERSIONS else "")


def system_images(sdk):
    """Installed system images: [{package, api, tag, abi, path, desc}]."""
    root = Path(sdk) / "system-images" if sdk else None
    out = []
    if not root or not root.is_dir():
        return out
    for plat in sorted(root.iterdir()):
        if not plat.is_dir():
            continue
        for tag in sorted(plat.iterdir()):
            if not tag.is_dir():
                continue
            for abi in sorted(tag.iterdir()):
                if not abi.is_dir():
                    continue
                props = source_props(abi / "source.properties")
                api = parse_api(props.get("AndroidVersion.ApiLevel") or plat.name)
                out.append({"package": f"system-images;{plat.name};{tag.name};{abi.name}", "api": api,
                            "platform": plat.name, "tag": tag.name, "abi": props.get("SystemImage.Abi") or abi.name,
                            "path": str(abi), "desc": props.get("Pkg.Desc", "")})
    return out


def platforms(sdk):
    d = Path(sdk) / "platforms" if sdk else None
    return sorted(x.name for x in d.iterdir() if x.is_dir()) if d and d.is_dir() else []


# ---------- host ----------

def host_arch():
    m = platform.machine().lower()
    if IS_WIN:
        m = (os.environ.get("PROCESSOR_ARCHITEW6432") or os.environ.get("PROCESSOR_ARCHITECTURE") or m).lower()
    if sys.platform == "darwin" and m == "x86_64":  # x86_64 Python under Rosetta on Apple Silicon
        code, out, _ = run(["sysctl", "-n", "sysctl.proc_translated"], timeout=5)
        if code == 0 and out.strip() == "1":
            return "arm64"
    if m in ("arm64", "aarch64", "armv8", "arm64e", "armv8l"):
        return "arm64"
    if m in ("x86_64", "amd64", "x64"):
        return "x86_64"
    return m or "unknown"


def host_abi():
    """System image ABI that runs with hardware acceleration on this host."""
    return "arm64-v8a" if host_arch() == "arm64" else "x86_64"


def host_memory():
    """{'total_mb', 'available_mb'} (None if unknown)."""
    total = avail = None
    try:
        if sys.platform == "darwin":
            code, out, _ = run(["sysctl", "-n", "hw.memsize"], timeout=5)
            total = int(out.strip()) // 2 ** 20 if code == 0 and out.strip().isdigit() else None
            code, out, _ = run(["vm_stat"], timeout=5)
            if code == 0:
                ps = int((re.search(r"page size of (\d+)", out) or [0, 4096])[1])
                pages = sum(int(n) for k, n in re.findall(r"Pages (free|inactive|speculative|purgeable):\s+(\d+)", out))
                avail = pages * ps // 2 ** 20 if pages else None
        elif IS_WIN:
            import ctypes

            class MS(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
            ms = MS()
            ms.dwLength = ctypes.sizeof(MS)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(ms)):  # type: ignore[attr-defined]
                total, avail = ms.ullTotalPhys // 2 ** 20, ms.ullAvailPhys // 2 ** 20
        else:
            info = dict(re.findall(r"^(\w+):\s+(\d+)", Path("/proc/meminfo").read_text(), re.M))
            total = int(info["MemTotal"]) // 1024 if "MemTotal" in info else None
            avail = int(info["MemAvailable"]) // 1024 if "MemAvailable" in info else None
    except (OSError, ValueError, AttributeError):
        pass
    return {"total_mb": total, "available_mb": avail}


def disk_free_gb(path):
    p = Path(path).expanduser()
    while not p.exists() and p != p.parent:
        p = p.parent
    try:
        return round(shutil.disk_usage(str(p)).free / 2 ** 30, 1)
    except OSError:
        return None


# ---------- AVD ----------

def avd_home():
    """Folder with <name>.ini and <name>.avd/ (emulator rules)."""
    if os.environ.get("ANDROID_AVD_HOME"):
        return Path(os.environ["ANDROID_AVD_HOME"]).expanduser()
    for var in ("ANDROID_USER_HOME", "ANDROID_EMULATOR_HOME"):
        if os.environ.get(var):
            return Path(os.environ[var]).expanduser() / "avd"
    if os.environ.get("ANDROID_SDK_HOME"):  # legacy: the parent of .android
        return Path(os.environ["ANDROID_SDK_HOME"]).expanduser() / ".android" / "avd"
    return _home() / ".android" / "avd"


AVD_PREFIX = "qa-"
AVD_MARKER = "android-qa-audit.json"  # file inside <name>.avd/ that marks an AVD created by this skill


def size_mb(text):
    """'2G' / '2048M' / '2048' / '2 GB' / '512 MB' -> MB (int) or None."""
    m = re.match(r"^\s*(\d+(?:\.\d+)?)\s*([KMGT]?)B?\s*$", str(text or ""), re.I)
    if not m:
        return None
    n, unit = float(m.group(1)), m.group(2).upper()
    return int(n * {"": 1, "K": 1 / 1024, "M": 1, "G": 1024, "T": 1024 * 1024}[unit])


def list_avds(home=None):
    """All AVDs from <avd_home>/*.ini (no Java needed). Ownership: 'skill' only with prefix qa- AND marker file."""
    home = Path(home) if home else avd_home()
    out = []
    if not home.is_dir():
        return out
    for ini in sorted(home.glob("*.ini")):
        name = ini.stem
        meta = parse_ini(ini)
        path = Path(meta.get("path") or (home / f"{name}.avd"))
        if not path.is_dir() and meta.get("path.rel"):
            path = home.parent / meta["path.rel"]
        cfg = parse_ini(path / "config.ini") if path.is_dir() else {}
        marker = path / AVD_MARKER
        owner = "skill" if name.startswith(AVD_PREFIX) and marker.is_file() else (
            "qa-prefix-no-marker" if name.startswith(AVD_PREFIX) else "user")
        sysdir = cfg.get("image.sysdir.1", "")
        out.append({
            "name": name, "path": str(path), "exists": path.is_dir(), "owner": owner,
            "target": meta.get("target") or cfg.get("target"), "api": parse_api(meta.get("target") or cfg.get("target")),
            "abi": cfg.get("abi.type"), "tag": cfg.get("tag.id"), "device": cfg.get("hw.device.name"),
            "ram_mb": size_mb(cfg.get("hw.ramSize")), "cores": int(cfg["hw.cpu.ncore"]) if cfg.get("hw.cpu.ncore", "").isdigit() else None,
            "data_mb": size_mb(cfg.get("disk.dataPartition.size")),
            "lcd": f"{cfg.get('hw.lcd.width')}x{cfg.get('hw.lcd.height')}" if cfg.get("hw.lcd.width") else None,
            "density": int(cfg["hw.lcd.density"]) if cfg.get("hw.lcd.density", "").isdigit() else None,
            "orientation": cfg.get("hw.initialOrientation"), "sysdir": sysdir,
            "playstore": cfg.get("PlayStore.enabled") in ("yes", "true"),
        })
    return out


# ---------- adb ----------

DEVICE_LINE = re.compile(r"^(\S+)\s+(device|offline|unauthorized|recovery|sideload|bootloader|authorizing|connecting|host|"
                         r"no permissions[^\n]*?|unknown)(?:\s+(\S+:.*))?$")


def parse_devices(text):
    """`adb devices -l` -> [{serial, state, model, product, device, transport_id, kind}]."""
    out = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line or line.startswith(("List of devices", "*", "adb server", "daemon")):
            continue
        m = DEVICE_LINE.match(line)
        if not m:
            continue
        extra = dict(re.findall(r"(\w+):(\S+)", m.group(3) or ""))
        serial = m.group(1)
        out.append({"serial": serial, "state": m.group(2).split(" (")[0], "model": extra.get("model"),
                    "product": extra.get("product"), "device": extra.get("device"),
                    "transport_id": extra.get("transport_id"),
                    "kind": "emulator" if serial.startswith("emulator-") else "unknown"})
    return out


def parse_getprop(text):
    """`getprop` output '[key]: [value]' -> dict."""
    return dict(re.findall(r"^\[([^\]]+)\]:\s*\[([^\]]*)\]", text or "", re.M))


def device_summary(props):
    """Short description of a device from getprop."""
    api = int(props["ro.build.version.sdk"]) if props.get("ro.build.version.sdk", "").isdigit() else None
    return {"api": api, "release": props.get("ro.build.version.release"),
            "model": props.get("ro.product.model"), "manufacturer": props.get("ro.product.manufacturer"),
            "abi": props.get("ro.product.cpu.abi"), "abilist": (props.get("ro.product.cpu.abilist") or "").split(","),
            "emulator": props.get("ro.kernel.qemu") == "1" or props.get("ro.boot.qemu") == "1"
            or props.get("ro.hardware") in ("ranchu", "goldfish"),
            "build_type": props.get("ro.build.type"), "locale": props.get("persist.sys.locale") or props.get("ro.product.locale"),
            "avd_name": props.get("ro.boot.qemu.avd_name") or props.get("ro.kernel.qemu.avd_name")}


class Adb:
    """Thin adb wrapper: list args, timeouts, one serial."""

    def __init__(self, serial=None, path=None, timeout=60):
        self.path = path or tool_path("adb")
        self.serial = serial
        self.timeout = timeout

    def available(self):
        return bool(self.path)

    def base(self):
        if not self.path:
            raise SystemExit("adb не найден: установите platform-tools (INSTALL.md) или задайте ANDROID_HOME")
        return [self.path] + (["-s", self.serial] if self.serial else [])

    def cmd(self, *args, timeout=None, binary=False, input=None):
        return run(self.base() + [str(a) for a in args], timeout=timeout or self.timeout, binary=binary, input=input)

    def shell(self, *args, timeout=None, binary=False):
        """adb shell with POSIX quoting of every argument (device side is sh)."""
        line = " ".join(shlex.quote(str(a)) for a in args)
        return self.cmd("shell", line, timeout=timeout, binary=binary)

    def shell_raw(self, line, timeout=None):
        """adb shell with a ready shell line (pipes, $(...)). Use only with trusted, skill-built strings."""
        return self.cmd("shell", line, timeout=timeout)

    def getprop(self, key=None):
        """One property (str) or, without key, all properties (dict) in one call."""
        if key is None:
            code, out, _ = self.shell("getprop", timeout=20)
            return parse_getprop(out) if code == 0 else {}
        code, out, _ = self.shell("getprop", key, timeout=15)
        return out.strip() if code == 0 else ""

    def devices(self):
        code, out, err = run([self.path, "devices", "-l"], timeout=30) if self.path else (127, "", "adb не найден")
        return code, parse_devices(out), err

    def kind(self):
        """emulator | real | unknown — for the current serial."""
        s = self.serial or ""
        if s.startswith("emulator-"):
            return "emulator"
        qemu = self.getprop("ro.kernel.qemu") or self.getprop("ro.boot.qemu")
        hw = self.getprop("ro.hardware")
        if qemu == "1" or hw in ("ranchu", "goldfish"):
            return "emulator"
        return "real" if hw or self.getprop("ro.product.model") else "unknown"


def pick_serial(adb_path=None, serial=None):
    """Explicit serial, ANDROID_SERIAL, or the only online device. SystemExit with a clear message otherwise."""
    if serial:
        return serial
    if os.environ.get("ANDROID_SERIAL"):
        return os.environ["ANDROID_SERIAL"]
    code, devs, err = Adb(path=adb_path).devices()
    online = [d for d in devs if d["state"] == "device"]
    if len(online) == 1:
        return online[0]["serial"]
    if not online:
        raise SystemExit("нет подключённых устройств в состоянии device (adb devices -l): " + (err.strip() or "пусто"))
    raise SystemExit("подключено несколько устройств — укажите --serial: " + ", ".join(d["serial"] for d in online))


def main():
    sdk, why = find_sdk()
    data = {"sdk": str(sdk) if sdk else None, "sdk_reason": why, "host_arch": host_arch(), "host_abi": host_abi(),
            "avd_home": str(avd_home()), "tools": {t: find_tool(t, sdk) for t in TOOLS},
            "images": system_images(sdk), "avds": list_avds(), "memory": host_memory()}
    print(json.dumps(data, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
