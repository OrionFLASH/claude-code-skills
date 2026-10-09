#!/usr/bin/env python3
"""Environment check for android-qa-audit (references/setup.md). Read-only: installs and changes nothing.

  check_env.py [--fast] [--no-devices] [--json env.json]
    --fast        skip slow checks: `emulator -accel-check`, `java -version`, `sdkmanager --version`, Appium drivers
    --no-devices  do not call `adb devices` (it starts the adb server if it is not running)
    --json FILE   save the result for the run (tools, images, AVDs, devices, host resources, enhancers)

Prints the table «component / version / status / note / how to fix» and the line «Итог: …».
Exit code: 0 — can work, 1 — a required component is missing (adb, aapt2/aapt, Python ≥ 3.9, a test stand).
"""
import argparse
import importlib.util
import json
import os
import re
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "shared"))
sys.path.insert(0, str(HERE))
import envcheck as ec  # noqa: E402
import sdkutil as su  # noqa: E402

# Skills / agents that may strengthen a direction (used only if found; references/plugins-map.md).
ENHANCERS = {
    "ui-ux-pro-max": ("skill", ["ux", "visual-ui"]),
    "laws-of-ux": ("skill", ["ux", "visual-ui"]),
    "ux-heuristics": ("skill", ["ux"]),
    "ux-design-principles": ("skill", ["visual-ui"]),
    "ux-audit": ("skill", ["ux", "functional"]),
    "resilience-audit": ("skill", ["lifecycle-resilience", "logic-state"]),
    "adversarial-audit": ("skill", ["logic-state"]),
    "mobile-workflow-generator": ("skill", ["functional"]),
    "mobile-workflow-to-playwright": ("skill", ["functional"]),
    "agent:mobile-ux-auditor": ("agent", ["ux", "visual-ui"]),
    "agent:accessibility-auditor": ("agent", ["accessibility"]),
}
# Never used (active attacks, load, self-publishing) — references/plugins-map.md.
BANNED = {
    "agent:adversarial-breaker": "активные атаки (инъекции, обход авторизации, удаления)",
    "agent:security-auditor": "смешивает пассивные и активные проверки без контроля",
    "perf-test": "нагрузочное тестирование",
    "security-scan": "сканер уязвимостей",
    "run-qa": "сам запускает агентов без правил скила",
    "submit-learnings": "публикует issue в репозиторий плагина",
}
ZSH_PATH = ('export ANDROID_HOME="{sdk}"; export PATH="$ANDROID_HOME/platform-tools:$ANDROID_HOME/emulator:'
            '$ANDROID_HOME/cmdline-tools/latest/bin:$PATH"  (в ~/.zshrc)')
PS_PATH = ("[Environment]::SetEnvironmentVariable('ANDROID_HOME','{sdk}','User'); "
           "[Environment]::SetEnvironmentVariable('Path', \"$env:Path;{sdk}\\platform-tools;{sdk}\\emulator;"
           "{sdk}\\cmdline-tools\\latest\\bin\", 'User')")


def path_fix(sdk):
    return (PS_PATH if su.IS_WIN else ZSH_PATH).format(sdk=sdk or "<путь к SDK>")


def version_of(text, rx=r"(\d+(?:\.\d+){1,3})"):
    m = re.search(rx, text or "")
    return m.group(1) if m else ""


def java_info(fast):
    jh = os.environ.get("JAVA_HOME")
    exe = None
    if jh and (Path(jh) / "bin" / ("java.exe" if su.IS_WIN else "java")).exists():
        exe = str(Path(jh) / "bin" / ("java.exe" if su.IS_WIN else "java"))
    exe = exe or shutil.which("java")
    if not exe:
        return {"path": None, "major": None, "version": None, "java_home": jh}
    if fast:
        return {"path": exe, "major": None, "version": "не проверялась (--fast)", "java_home": jh}
    code, out, err = su.run([exe, "-version"], timeout=30)
    text = out + err
    m = re.search(r'version "(\d+)(?:\.(\d+))?[^"]*"', text)
    if code != 0 or not m:
        return {"path": exe, "major": None, "version": None, "java_home": jh, "error": text.strip()[:160]}
    major = int(m.group(1))
    if major == 1 and m.group(2):
        major = int(m.group(2))
    full = re.search(r'version "([^"]+)"', text).group(1)
    return {"path": exe, "major": major, "version": full, "java_home": jh, "early_access": "-ea" in full or "ea" == full[-2:]}


def accel_check(emulator, fast):
    """Hardware acceleration for the emulator: HVF (macOS), WHPX/AEHD/HAXM (Windows), KVM (Linux)."""
    res = {"ok": None, "kind": None, "note": ""}
    if sys.platform == "darwin":
        code, out, _ = su.run(["sysctl", "-n", "kern.hv_support"], timeout=5)
        res.update(kind="HVF", ok=(out.strip() == "1") if code == 0 else None,
                   note="Hypervisor.framework " + ("доступен" if out.strip() == "1" else "недоступен"))
    elif sys.platform.startswith("linux"):
        kvm = Path("/dev/kvm")
        res.update(kind="KVM", ok=kvm.exists() and os.access(str(kvm), os.R_OK | os.W_OK),
                   note="/dev/kvm " + ("доступен" if kvm.exists() else "нет") +
                   ("" if not kvm.exists() or os.access(str(kvm), os.R_OK | os.W_OK) else " (нет прав: группа kvm)"))
    if emulator and not fast:
        code, out, err = su.run([emulator, "-accel-check"], timeout=40)
        ok, desc = parse_accel_check(code, out + err)
        if ok is not None:
            kind = "HVF" if "hypervisor" in desc.lower() else (desc.split()[0] if desc else res["kind"])
            res.update(ok=ok, kind=kind, note=f"emulator -accel-check: {desc}"[:160])
    return res


def parse_accel_check(code, text):
    """`emulator -accel-check`: 'accel:' / <status code, 0 = usable> / <description> / 'accel'. -> (ok, description)."""
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    if "accel:" in lines:
        i = lines.index("accel:")
        status = lines[i + 1] if i + 1 < len(lines) else ""
        desc = lines[i + 2] if i + 2 < len(lines) and lines[i + 2] != "accel" else ""
        if status.lstrip("-").isdigit():
            return int(status) == 0, desc or ("usable" if int(status) == 0 else f"код {status}")
    if "is installed and usable" in (text or ""):
        return True, next(ln for ln in lines if "usable" in ln)
    if code == 127 or not lines:
        return None, ""
    return code == 0, lines[-1]


def cmdline_tools_probe(sdkmanager):
    """`sdkmanager --version` — do cmdline-tools start with this Java? (ok, version, java_ea_noise, error)."""
    code, out, err, noise = su.run_sdk_tool([sdkmanager, "--version"], timeout=90)
    ver = version_of(out, r"^\s*(\d+(?:\.\d+)+)\s*$") if code == 0 else ""
    if code == 0 and not ver:
        ver = version_of(out)
    return {"ok": code == 0, "version": ver, "java_ea_noise": noise,
            "error": "" if code == 0 else (err or out).strip()[-200:]}


def device_rows(adb, rows):
    code, devs, err = adb.devices()
    if code != 0:
        rows.append(ec.Row("устройства (adb devices)", "", ec.WARN, (err or "ошибка adb").strip()[:120],
                           "adb kill-server && adb start-server"))
        return []
    for d in devs:
        if d["state"] == "device":
            props = su.Adb(d["serial"], adb.path).getprop()
            d.update(su.device_summary(props))
            d["kind"] = "emulator" if d.get("emulator") or d["serial"].startswith("emulator-") else "real"
    online = [d for d in devs if d["state"] == "device"]
    emus = [d for d in online if d["kind"] == "emulator"]
    real = [d for d in online if d["kind"] == "real"]
    note = "; ".join(f"{d['serial']}: {d['kind']}, {d.get('model') or '?'}, {su.api_label(d.get('api'))}" for d in online)
    rows.append(ec.Row("устройства онлайн", f"{len(real)} реальн., {len(emus)} эмул.", ec.OK if online else ec.WARN,
                       note or "нет — стенд будет эмулятор (AVD)",
                       "" if online else "подключите телефон с отладкой по USB или создайте AVD (avd_manager.py)"))
    for d in devs:
        if d["state"] == "unauthorized":
            rows.append(ec.Row(f"устройство {d['serial']}", "", ec.WARN, "unauthorized — отладка не подтверждена",
                               "разблокируйте телефон и нажмите «Разрешить» в диалоге отладки по USB"))
        elif d["state"] == "offline":
            rows.append(ec.Row(f"устройство {d['serial']}", "", ec.WARN, "offline",
                               "adb reconnect offline; переподключить кабель; перезапустить эмулятор"))
        elif d["state"].startswith("no permissions"):
            rows.append(ec.Row(f"устройство {d['serial']}", "", ec.WARN, "нет прав на USB-устройство (Linux)",
                               "правила udev для Android и группа plugdev"))
    if real:
        rows.append(ec.Row("реальные устройства", str(len(real)), ec.WARN,
                           "используются только после отдельного разрешения пользователя (safety-rules.md)"))
    return devs


def recommended_workers(mem, cpus, avd_ram_mb=2048):
    avail = mem.get("available_mb") or (mem.get("total_mb") or 0) // 2
    by_ram = max(0, (avail - 2048) // (avd_ram_mb + 1024))
    by_cpu = max(1, (cpus or 2) // 2)
    return max(1, min(4, by_ram or 1, by_cpu))


def optional_tool(rows, name, cmd, note, fix, opt):
    exe = shutil.which(cmd[0])
    if not exe:
        rows.append(ec.Row(name, "", ec.WARN, "нет — " + note, fix))
        opt[name] = None
        return None
    code, out, err = su.run([exe] + cmd[1:], timeout=30)
    ver = version_of(out + err)
    rows.append(ec.Row(name, ver, ec.OK if code == 0 else ec.WARN, note))
    opt[name] = {"path": exe, "version": ver}
    return exe


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fast", action="store_true")
    ap.add_argument("--no-devices", action="store_true")
    ap.add_argument("--json")
    a = ap.parse_args()

    rows, required_fail = [], []
    rows.append(ec.Row("ОС", ec.os_name(), ec.OK, f"процессор {su.host_arch()} → образы {su.host_abi()}"))
    pyv = sys.version_info
    rows.append(ec.Row("Python", f"{pyv[0]}.{pyv[1]}.{pyv[2]}", ec.OK if pyv >= (3, 9) else ec.FAIL,
                       "только стандартная библиотека", "Python 3.9+ (python.org)"))
    if pyv < (3, 9):
        required_fail.append("Python ≥ 3.9")

    java = java_info(a.fast)
    if not java["path"]:
        rows.append(ec.Row("Java (JDK 17+)", "", ec.WARN, "нет — не работают sdkmanager, avdmanager, apksigner, bundletool",
                           "Temurin 17/21: brew install --cask temurin@21 / winget install EclipseAdoptium.Temurin.21.JDK"))
    elif java.get("major") is None:
        rows.append(ec.Row("Java (JDK 17+)", java.get("version") or "", ec.WARN if not a.fast else ec.OK,
                           java.get("error") or java["path"], "установите JDK 17+ и задайте JAVA_HOME"))
    else:
        st = ec.OK if java["major"] >= 17 else ec.WARN
        note = "JAVA_HOME " + ("задан" if java["java_home"] else "не задан (берётся java из PATH)")
        if java.get("early_access"):
            note += ("; ранняя сборка (ea): cmdline-tools работают, их обёртки печатают «integer expression expected» — "
                     "безвредно, скил скрывает это при успешной команде; рекомендуется JDK 17 или 21 (Temurin LTS)")
        rows.append(ec.Row("Java (JDK 17+)", java["version"], st, note,
                           "" if st == ec.OK else "нужен JDK 17+: Temurin 17/21"))

    sdk, why = su.find_sdk()
    env_set = [v for v in ("ANDROID_HOME", "ANDROID_SDK_ROOT") if os.environ.get(v)]
    if sdk:
        rows.append(ec.Row("Android SDK", str(sdk), ec.OK if env_set else ec.WARN,
                           f"найден: {why}" + ("" if env_set else "; ANDROID_HOME не задан — скил находит SDK сам, для терминала задайте переменную"),
                           "" if env_set else path_fix(sdk)))
    else:
        rows.append(ec.Row("Android SDK", "", ec.FAIL, "не найден: " + ", ".join(str(p) for p, _ in su.sdk_candidates()[:4]),
                           "Android Studio или command-line tools (INSTALL.md → «Android SDK»)"))

    tools = {t: su.find_tool(t, sdk) for t in su.TOOLS}
    adb_t = tools["adb"]
    if adb_t["path"]:
        code, out, err = su.run([adb_t["path"], "version"], timeout=20)
        ver = version_of(out, r"Version (\S+)") or version_of(out)
        proto = version_of(out, r"version (\d+\.\d+\.\d+)")
        in_path = adb_t["in_path"]
        # not in PATH is not a problem for the skill (scripts call adb by full path): OK with a hint for the terminal
        rows.append(ec.Row("adb (platform-tools)", f"{ver} ({proto})" if proto else ver, ec.OK,
                           adb_t["path"] + ("" if in_path else " — не в PATH: скилу не мешает (вызывает по полному пути); "
                                            "для своего терминала: " + path_fix(sdk))))
    else:
        rows.append(ec.Row("adb (platform-tools)", "", ec.FAIL, "не найден",
                           "sdkmanager \"platform-tools\"  или  brew install --cask android-platform-tools"))
        required_fail.append("adb")

    emu_t = tools["emulator"]
    emu_ver = ""
    if emu_t["path"]:
        code, out, err = su.run([emu_t["path"], "-version"], timeout=30)
        emu_ver = version_of(out + err, r"version (\d+(?:\.\d+)+)")
        rows.append(ec.Row("emulator", emu_ver, ec.OK if code == 0 else ec.WARN, emu_t["path"]))
    else:
        rows.append(ec.Row("emulator", "", ec.WARN, "нет — тестирование только на подключённых устройствах",
                           "sdkmanager \"emulator\""))

    cl = tools["sdkmanager"]["path"] and tools["avdmanager"]["path"]
    clver = ""
    probe = None
    if cl:
        props = su.source_props(Path(tools["sdkmanager"]["path"]).parent.parent / "source.properties")
        clver = props.get("Pkg.Revision", "")
        note = str(Path(tools["sdkmanager"]["path"]).parent) + ("" if java.get("path") else " — без Java не запустятся")
        status, fix = (ec.OK if java.get("path") else ec.WARN), ""
        if java.get("path") and not a.fast:
            probe = cmdline_tools_probe(tools["sdkmanager"]["path"])
            if not probe["ok"]:
                status, fix = ec.WARN, "JDK 17 или 21 (Temurin) и JAVA_HOME — INSTALL.md → «Java»"
                note += f"; sdkmanager --version не запустился: {probe['error']}"
            else:
                note += "; sdkmanager запускается"
                if probe["java_ea_noise"]:
                    note += ("; шум «integer expression expected» от ранней сборки Java (-ea) — безвредно, команда "
                             "завершилась успешно (скил его скрывает); спокойнее — JDK 17/21")
        rows.append(ec.Row("cmdline-tools (sdkmanager, avdmanager)", clver, status, note, fix))
    else:
        rows.append(ec.Row("cmdline-tools (sdkmanager, avdmanager)", "", ec.WARN,
                           "нет — создание AVD и установка образов недоступны",
                           "Android Studio → SDK Manager → «Android SDK Command-line Tools (latest)» или brew install --cask android-commandlinetools"))

    bt = su.build_tools_dirs(sdk) if sdk else []
    aapt = tools["aapt2"]["path"] or tools["aapt"]["path"]
    if aapt:
        rows.append(ec.Row("build-tools (aapt2, apksigner)", bt[0].name if bt else "", ec.OK,
                           ("aapt2" if tools["aapt2"]["path"] else "aapt") + (", apksigner" if tools["apksigner"]["path"] else ", без apksigner")))
    else:
        rows.append(ec.Row("build-tools (aapt2, apksigner)", "", ec.FAIL, "нет aapt2/aapt — разбор APK невозможен",
                           "sdkmanager \"build-tools;35.0.0\" (или новее)"))
        required_fail.append("build-tools (aapt2)")

    plats = su.platforms(sdk)
    rows.append(ec.Row("platforms", ", ".join(plats[-4:]), ec.OK if plats else ec.WARN,
                       "для эмулятора не обязательны", "" if plats else "sdkmanager \"platforms;android-35\""))

    host_abi = su.host_abi()
    images = su.system_images(sdk)
    good = [i for i in images if i["abi"] == host_abi]
    rows.append(ec.Row("образы систем", str(len(images)), ec.OK if good else ec.WARN,
                       "; ".join(f"{su.api_label(i['api'])} {i['tag']} {i['abi']}" + ("" if i["abi"] == host_abi else " (не под этот процессор)")
                                 for i in images) or "нет",
                       "" if good else f"avd_manager.py install-image --api <N> (образ {host_abi}, после подтверждения)"))

    avds = su.list_avds()
    mine = [x for x in avds if x["owner"] == "skill"]
    rows.append(ec.Row("AVD", f"{len(avds)} (скила: {len(mine)})", ec.OK,
                       ", ".join(x["name"] + ("" if x["owner"] == "skill" else " [чужой — не менять]") for x in avds) or "нет",
                       ""))

    devs = []
    if a.no_devices:
        rows.append(ec.Row("устройства онлайн", "", ec.WARN, "не проверялись (--no-devices)"))
    elif adb_t["path"]:
        devs = device_rows(su.Adb(path=adb_t["path"]), rows)

    accel = accel_check(emu_t["path"], a.fast)
    rows.append(ec.Row("аппаратное ускорение", accel.get("kind") or "", ec.OK if accel["ok"] else ec.WARN,
                       accel.get("note") or ("не проверялось (--fast)" if a.fast else "неизвестно"),
                       "" if accel["ok"] else {"darwin": "macOS 11+ на Apple Silicon/Intel с VT-x",
                                               "win32": "включить «Платформа низкоуровневой оболочки Windows» (WHPX) или AEHD",
                                               }.get(sys.platform, "включить виртуализацию в BIOS; sudo usermod -aG kvm $USER")))

    mem, cpus = su.host_memory(), os.cpu_count()
    rows.append(ec.Row("ОЗУ хоста", f"{mem.get('total_mb') or '?'} МБ", ec.OK if (mem.get("total_mb") or 0) >= 8000 else ec.WARN,
                       f"доступно ≈ {mem.get('available_mb') or '?'} МБ; эмулятор с 2 ГБ занимает ≈ 3 ГБ"))
    rows.append(ec.Row("ядра CPU", str(cpus or "?"), ec.OK))
    out_root = os.environ.get("ANDROID_QA_OUTPUT_DIR")
    avd_free = su.disk_free_gb(su.avd_home())
    out_free = su.disk_free_gb(out_root or os.getcwd())
    rows.append(ec.Row("свободно на диске", f"{avd_free} ГБ (AVD), {out_free} ГБ (результаты)",
                       ec.OK if (avd_free or 0) >= 15 else ec.WARN,
                       f"AVD: {su.avd_home()}; образ ≈ 2–6 ГБ, AVD ≈ 2–8 ГБ"))
    workers = recommended_workers(mem, cpus)
    rows.append(ec.Row("параллельных эмуляторов (рекомендация)", str(workers), ec.OK,
                       "по свободной ОЗУ и ядрам; максимум 4 (parallelism.md)"))

    opt = {}
    bt_jar = os.environ.get("BUNDLETOOL_JAR")
    if tools["bundletool"]["path"]:
        optional_tool(rows, "bundletool", [tools["bundletool"]["path"], "version"], "AAB → APK", "", opt)
    elif bt_jar and Path(bt_jar).is_file():
        rows.append(ec.Row("bundletool", Path(bt_jar).name, ec.OK, "BUNDLETOOL_JAR (java -jar)"))
        opt["bundletool"] = {"path": bt_jar, "jar": True}
    else:
        rows.append(ec.Row("bundletool", "", ec.WARN, "нет — AAB не разобрать (APK и установленные приложения — можно)",
                           "brew install bundletool / скачать jar с github.com/google/bundletool и задать BUNDLETOOL_JAR"))
        opt["bundletool"] = None
    optional_tool(rows, "scrcpy", ["scrcpy", "--version"], "показ экрана устройства (необязательно)",
                  "brew install scrcpy / winget install Genymobile.scrcpy", opt)
    optional_tool(rows, "maestro", ["maestro", "--version"], "сценарии UI (необязательный усилитель)",
                  "curl -Ls https://get.maestro.mobile.dev | bash", opt)
    if optional_tool(rows, "appium", ["appium", "--version"], "UI-автоматизация (необязательный усилитель)",
                     "npm i -g appium && appium driver install uiautomator2", opt) and not a.fast:
        code, out, _ = su.run([shutil.which("appium"), "driver", "list", "--installed", "--json"], timeout=60)
        try:
            drivers = sorted(json.loads(out[out.index("{"):]).keys())
        except ValueError:
            drivers = []
        opt["appium"]["drivers"] = drivers
        rows[-1]["note"] += f"; драйверы: {', '.join(drivers) or 'нет'}"
    import mic  # noqa: E402 — loopback detection (read-only, installs nothing)
    lb = mic.loopback_info(fast=a.fast)
    rows.append(ec.Row("виртуальное аудиоустройство (loopback)", ", ".join(lb["devices"][:2]), ec.OK,
                       ("найдено" + ("; вход по умолчанию: " + lb["default_input"] if lb["default_input"] else "")
                        if lb["devices"] else "нет — необязательно: нужно только для подачи звука в микрофон путём 2 "
                                              "(mic-inject --via loopback); пути grpc и file работают без него")
                       + (f"; {lb['hint']}" if lb["hint"] and not lb["ready"] else "")))
    opt["loopback_audio"] = {k: lb[k] for k in ("devices", "default_input", "default_output", "ready")}
    u2 = importlib.util.find_spec("uiautomator2") is not None
    rows.append(ec.Row("python uiautomator2", "", ec.OK if u2 else ec.WARN,
                       "доступен (необязательно)" if u2 else "нет — не нужен: скил работает через adb и uiautomator dump"))
    opt["uiautomator2_py"] = u2
    rows.append(ec.tool_version("git", fix="https://git-scm.com"))
    gh = ec.tool_version("gh", fix="https://cli.github.com (нужен только для GitHub issues)")
    if gh["status"] == ec.FAIL:
        gh["status"] = ec.WARN
    rows.append(gh)
    if shutil.which("gh") and not a.fast:
        st = ec.gh_status()
        if st["status"] == ec.FAIL:
            st["status"] = ec.WARN
        rows.append(st)
    if out_root:
        p = Path(out_root).expanduser()
        rows.append(ec.Row("ANDROID_QA_OUTPUT_DIR", str(p), ec.OK if p.is_dir() else ec.WARN,
                           "папка результатов" + ("" if p.is_dir() else " — папки нет, будет создана")))
    else:
        rows.append(ec.Row("ANDROID_QA_OUTPUT_DIR", "", ec.WARN, "не задана — результаты в <папка запуска>/qa-runs/",
                           'добавить в ~/.claude/settings.json → "env": {"ANDROID_QA_OUTPUT_DIR": "<путь>"}'))

    plugins = ec.claude_plugins() if not a.fast else []
    skills = set(ec.user_skills())
    pskills = ec.plugin_skills(plugins)
    available = {}
    for name, (kind, dirs) in ENHANCERS.items():
        src = "~/.claude/skills" if name in skills else pskills.get(name)
        if src:
            available[name] = {"kind": kind, "source": src, "directions": dirs}
    rows.append(ec.Row("усилители (скилы/агенты)", str(len(available)), ec.OK if available else ec.WARN,
                       ", ".join(sorted(available)) or ("не проверялись (--fast)" if a.fast else "нет — собственные чек-листы"),
                       "references/plugins-map.md"))

    online = [d for d in devs if d.get("state") == "device"]
    can_emulate = bool(emu_t["path"]) and (bool([x for x in avds if x["exists"]]) or (bool(cl) and bool(java.get("path"))))
    if not online and not can_emulate:
        required_fail.append("стенд (нет устройства онлайн и нет эмулятора с AVD/cmdline-tools)")

    print("## Окружение android-qa-audit\n")
    ec.print_table(rows)
    print(f"\nСтенды: устройств онлайн {len(online)}, AVD {len(avds)} (скила {len(mine)}), образов под {host_abi}: {len(good)}"
          f"{'' if accel['ok'] else ' — без ускорения эмулятор будет очень медленным'}")
    print(f"Итог: {'можно работать' if not required_fail else 'нужно исправить: ' + ', '.join(required_fail)}")

    if a.json:
        data = {"rows": rows, "sdk": str(sdk) if sdk else None, "sdk_reason": why,
                "tools": {k: v["path"] for k, v in tools.items()}, "tools_in_path": {k: v["in_path"] for k, v in tools.items()},
                "versions": {"emulator": emu_ver, "cmdline_tools": clver, "build_tools": bt[0].name if bt else None},
                "cmdline_tools_probe": probe,
                "java": java, "host": {"os": ec.os_name(), "arch": su.host_arch(), "abi": host_abi, "cpus": cpus,
                                       **mem, "disk_free_gb_avd": avd_free, "disk_free_gb_output": out_free},
                "accel": accel, "images": images, "avd_home": str(su.avd_home()), "avds": avds, "devices": devs,
                "recommended_max_workers": workers, "optional": opt, "output_dir": out_root,
                "enhancers": available, "banned": BANNED, "required_fail": required_fail}
        Path(a.json).parent.mkdir(parents=True, exist_ok=True)
        Path(a.json).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    sys.exit(1 if required_fail else 0)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
