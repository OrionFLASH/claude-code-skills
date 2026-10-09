#!/usr/bin/env python3
"""Test stands for android-qa-audit: AVDs created by the skill (prefix qa-), emulators, system images
(references/stands.md). The user's own AVDs are never changed, deleted or started without --allow-foreign
(and then only with -read-only -no-snapshot-save).

  avd_manager.py list [--json]                              AVDs (owner), running emulators, installed images
  avd_manager.py images [--available] [--api N] [--json]    installed images (+ sdkmanager --list: network, read-only)
  avd_manager.py profiles                                   device profiles (avdmanager list device -c, needs Java)
  avd_manager.py name  --api 34 [--profile phone] [--ram 2048] [--cores 2] [--tag google_apis] [--suffix x]
  avd_manager.py plan  --api 34 [--profile phone|small|tablet|fold|<avdmanager id>] [--ram MB] [--cores N]
                       [--data 6G] [--size 1080x2400] [--density 420] [--orientation portrait|landscape]
                       [--tag google_apis|google_apis_playstore|default] [--abi auto] [--name qa-…] [--json]
  avd_manager.py install-image --api N [--tag …] [--abi auto] [--yes] [--accept-licenses] [--run-dir R]
  avd_manager.py create <plan options> --yes [--run-dir R]
  avd_manager.py start NAME [--port 5554] [--headless] [--cold-boot] [--wipe-data] [--read-only] [--snapshot S]
                       [--netspeed full|lte|hsdpa|umts|edge|gprs] [--netdelay none|lte|umts|edge|gprs]
                       [--locale ru-RU] [--timezone Europe/Moscow] [--gpu auto] [--allow-foreign] [--owner w1] [--run-dir R]
                       [--mic-inject] [--keep-audio] [--extra-args "-prop k=v -camera-back virtualscene"] [--confirmed]
                       an AVD that is already running is NOT started again (exit 3): one stand — one executor;
                       --extra-args: white list (guard.py emulator-args; -grpc only with -grpc-use-token/-jwt, deny → 3,
                       host mic/camera → 2 until --confirmed); --mic-inject: -grpc <free port> -grpc-use-token, audio on
  avd_manager.py wait-boot SERIAL [--timeout 420] [--unlock] [--disable-animations] [--run-dir R]
  avd_manager.py snapshot save|load|list SERIAL [NAME]      quick reset of an own emulator (adb emu avd snapshot)
  avd_manager.py stop SERIAL|NAME [--run-dir R] [--any-qa] [--owner w1]   --owner: a stand of another thread -> exit 3
  avd_manager.py delete NAME --yes                          only AVDs created by the skill (qa- + marker), not running
  avd_manager.py cleanup --run-dir R [--stop] [--delete-avds] [--delete-apk-copies] [--delete-recordings] [--yes]

Ownership: name starts with "qa-" AND <name>.avd/android-qa-audit.json exists (written by create).
<RUN_DIR>/stands.json records what this run created and started (cleanup works only with that).
Exit codes: 0 ok, 2 bad input / refused, 3 forbidden (foreign AVD), 4 image missing, 5 licenses not accepted,
6 boot timeout / emulator died, 127 tool missing.
"""
import argparse
import datetime
import json
import os
import re
import shutil
import socket
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import sdkutil as su  # noqa: E402
from masking import mask  # noqa: E402 — emulator logs and gRPC errors may contain tokens

PROFILES = {  # alias -> (avdmanager ids in preference order, short name for the AVD name, lcd WxH, density)
    "phone": (["pixel_7", "pixel_6", "pixel_5", "Nexus 5"], "pixel7", "1080x2400", 420),
    "small": (["small_phone", "Nexus 4", "Nexus S"], "small", "720x1280", 320),
    "large": (["pixel_7_pro", "medium_phone", "Nexus 6"], "large", "1440x3120", 560),
    "tablet": (["pixel_tablet", "medium_tablet", "Nexus 9"], "tablet", "2560x1600", 320),
    "fold": (["pixel_fold", "7.6in Foldable"], "fold", "2208x1840", 420),
}
TAG_SHORT = {"google_apis": "", "google_apis_playstore": "play", "default": "aosp", "google_atd": "atd", "aosp_atd": "aospatd"}
TAG_PREFERENCE = ["google_apis", "default", "google_apis_playstore", "google_atd", "aosp_atd"]
NETSPEED = ["gsm", "hscsd", "gprs", "edge", "umts", "hsdpa", "lte", "evdo", "full", "5g"]
NETDELAY = ["gsm", "hscsd", "gprs", "edge", "umts", "lte", "evdo", "none", "5g"]


def now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def die(msg, code=2):
    sys.stderr.write(f"avd_manager: {msg}\n")
    sys.exit(code)


# ---------- run registry <RUN_DIR>/stands.json ----------

class Registry:
    def __init__(self, run_dir):
        self.path = Path(run_dir) / "stands.json" if run_dir else None
        self.lock = self.path.with_suffix(".json.lock") if self.path else None

    def __enter__(self):
        if not self.path:
            return self
        self.path.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.time() + 20
        while True:
            try:
                fd = os.open(str(self.lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.close(fd)
                return self
            except FileExistsError:
                try:
                    if time.time() - self.lock.stat().st_mtime > 60:
                        self.lock.unlink()
                        continue
                except OSError:
                    pass
                if time.time() > deadline:
                    die(f"занят {self.lock} (другой поток?) — повторите")
                time.sleep(0.2)

    def __exit__(self, *exc):
        if self.lock:
            try:
                self.lock.unlink()
            except OSError:
                pass

    def load(self):
        if not self.path or not self.path.exists():
            return {"avds_created": [], "emulators": [], "devices": []}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except ValueError:
            return {"avds_created": [], "emulators": [], "devices": []}

    def save(self, data):
        if self.path:
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
            os.replace(str(tmp), str(self.path))


# ---------- helpers ----------

def adb_path():
    p = su.tool_path("adb")
    if not p:
        die("adb не найден (platform-tools)", 127)
    return p


def running_emulators():
    """{serial: avd_name} of online emulators (adb emu avd name, read-only)."""
    adb = su.tool_path("adb")
    if not adb:
        return {}
    _, devs, _ = su.Adb(path=adb).devices()
    out = {}
    for d in devs:
        if d["serial"].startswith("emulator-") and d["state"] in ("device", "offline"):
            code, txt, _ = su.Adb(d["serial"], adb).cmd("emu", "avd", "name", timeout=10)
            name = txt.strip().splitlines()[0].strip() if code == 0 and txt.strip() else None
            out[d["serial"]] = name
    return out


def find_avd(name):
    return next((x for x in su.list_avds() if x["name"] == name), None)


def owned(avd):
    return bool(avd) and avd["owner"] == "skill"


def parse_size(text):
    m = re.match(r"^(\d+)x(\d+)$", text or "")
    if not m:
        die(f"размер экрана «{text}» — нужен формат 1080x2400")
    return int(m.group(1)), int(m.group(2))


def resolve_profile(alias):
    if alias in PROFILES:
        return PROFILES[alias]
    short = re.sub(r"[^a-z0-9]+", "", alias.lower())[:12] or "custom"
    return [alias], short, None, None


def choose_image(api, tag=None, abi=None):
    abi = abi if abi and abi != "auto" else su.host_abi()
    sdk, _ = su.find_sdk()
    imgs = [i for i in su.system_images(sdk) if i["api"] == api and i["abi"] == abi]
    if tag:
        hit = [i for i in imgs if i["tag"] == tag]
        return (hit[0] if hit else None), tag, abi
    for t in TAG_PREFERENCE:
        hit = [i for i in imgs if i["tag"] == t]
        if hit:
            return hit[0], t, abi
    return None, "google_apis", abi


def avd_name(api, profile_short, ram, cores, tag, suffix=None):
    parts = [f"qa-api{api}", profile_short, f"{max(1, round(ram / 1024))}gb" if ram >= 1024 else f"{ram}mb", f"{cores}c"]
    if TAG_SHORT.get(tag, tag):
        parts.append(TAG_SHORT.get(tag, tag))
    if suffix:
        parts.append(re.sub(r"[^a-z0-9-]+", "-", suffix.lower()).strip("-"))
    return "-".join(p for p in parts if p)


def make_plan(a):
    ids, short, lcd, density = resolve_profile(a.profile)
    image, tag, abi = choose_image(a.api, a.tag, a.abi)
    size = a.size or lcd
    name = a.name or avd_name(a.api, short, a.ram, a.cores, tag, a.suffix)
    if not name.startswith(su.AVD_PREFIX):
        die(f"имя AVD должно начинаться с «{su.AVD_PREFIX}»: так скил отличает свои AVD от чужих")
    platform = image["platform"] if image else f"android-{a.api}"
    package = image["package"] if image else f"system-images;{platform};{tag};{abi}"
    existing = find_avd(name)
    sdk, _ = su.find_sdk()
    plan = {"name": name, "api": a.api, "label": su.api_label(a.api), "profile": a.profile, "device_ids": ids,
            "image": package, "image_installed": bool(image), "tag": tag, "abi": abi,
            "host_abi_match": abi == su.host_abi(),
            "config": {"hw.ramSize": str(a.ram), "hw.cpu.ncore": str(a.cores), "disk.dataPartition.size": a.data,
                       "hw.initialOrientation": a.orientation, "hw.keyboard": "yes", "hw.gpu.enabled": "yes",
                       "fastboot.forceColdBoot": "no", "showDeviceFrame": "no"},
            "exists": bool(existing), "existing_owner": existing["owner"] if existing else None,
            "disk_free_gb": su.disk_free_gb(su.avd_home()), "sdk": str(sdk) if sdk else None}
    if size:
        w, h = parse_size(size)
        plan["config"].update({"hw.lcd.width": str(w), "hw.lcd.height": str(h)})
    if a.density or density:
        plan["config"]["hw.lcd.density"] = str(a.density or density)
    steps = []
    if not image:
        steps.append(f"avd_manager.py install-image --api {a.api} --tag {tag} --abi {abi} --yes --run-dir <RUN_DIR>   "
                     f"# {package}: загрузка ≈ 1–2 ГБ, на диске ≈ 3–6 ГБ (оценка); только после согласия пользователя")
    if not existing:
        steps.append(f"avd_manager.py create --api {a.api} --profile {a.profile} --ram {a.ram} --cores {a.cores} "
                     f"--data {a.data} --tag {tag} --yes --run-dir <RUN_DIR>")
    elif not owned(existing):
        steps.append(f"ОСТАНОВКА: AVD {name} уже есть и не создан скилом — выберите другое имя (--suffix)")
    plan["steps"] = steps
    if not plan["host_abi_match"]:
        plan["warning"] = f"образ {abi} на хосте {su.host_abi()} работает без ускорения — очень медленно"
    return plan


def plan_args(p, create=False):
    p.add_argument("--api", type=int, required=True)
    p.add_argument("--profile", default="phone", help="phone | small | large | tablet | fold | id из avdmanager list device")
    p.add_argument("--ram", type=int, default=2048, help="МБ, по умолчанию 2048")
    p.add_argument("--cores", type=int, default=2)
    p.add_argument("--data", default="6G", help="размер раздела данных: 2G, 6G, 8G")
    p.add_argument("--size", help="WxH экрана, по умолчанию из профиля")
    p.add_argument("--density", type=int)
    p.add_argument("--orientation", default="portrait", choices=["portrait", "landscape"])
    p.add_argument("--tag", help="google_apis (по умолчанию) | google_apis_playstore | default")
    p.add_argument("--abi", default="auto")
    p.add_argument("--name")
    p.add_argument("--suffix")
    p.add_argument("--json", action="store_true")
    if create:
        p.add_argument("--yes", action="store_true")
        p.add_argument("--run-dir")


# ---------- commands ----------

def cmd_list(a):
    avds = su.list_avds()
    running = running_emulators()
    by_name = {v: k for k, v in running.items() if v}
    sdk, _ = su.find_sdk()
    images = su.system_images(sdk)
    for x in avds:
        x["running"] = by_name.get(x["name"])
    data = {"avd_home": str(su.avd_home()), "avds": avds, "running": running, "images": images, "host_abi": su.host_abi()}
    if a.json:
        print(json.dumps(data, ensure_ascii=False, indent=1))
        return
    print(f"AVD ({data['avd_home']}):")
    print("| Имя | Владелец | API | ABI | Профиль | ОЗУ | Ядра | Данные | Экран | Запущен |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for x in avds:
        owner = {"skill": "скил", "user": "пользователь — не менять", "qa-prefix-no-marker": "qa- без метки — не менять"}[x["owner"]]
        print(f"| {x['name']} | {owner} | {x['api'] or '?'} | {x['abi'] or '?'} | {x['device'] or '?'} | "
              f"{x['ram_mb'] or '?'} МБ | {x['cores'] or '?'} | {x['data_mb'] or '?'} МБ | "
              f"{(x['lcd'] or '?')}@{x['density'] or '?'} | {x['running'] or '—'} |")
    if not avds:
        print("| — | | | | | | | | | |")
    started = ", ".join(f"{k} ({v or '?'})" for k, v in running.items()) or "нет"
    print(f"\nЗапущенные эмуляторы: {started}")
    print(f"Образы ({su.host_abi()} — с ускорением): " +
          ("; ".join(f"{su.api_label(i['api'])} {i['tag']} {i['abi']}" for i in images) or "нет"))


def sdkmanager_list():
    sm = su.tool_path("sdkmanager")
    if not sm:
        return None, "sdkmanager не найден (cmdline-tools)"
    code, out, err, _ = su.run_sdk_tool([sm, "--list"], timeout=300)
    if code != 0:
        return None, (err or out).strip()[-300:]
    section, res = None, {"installed": [], "available": []}
    for line in out.splitlines():
        if re.match(r"^\s*Installed packages:", line):
            section = "installed"
        elif re.match(r"^\s*Available Packages:", line):
            section = "available"
        elif re.match(r"^\s*Available Updates:", line):
            section = None
        m = re.match(r"^\s*(system-images;[^|\s]+)\s*\|\s*(\S+)\s*\|\s*(.*?)\s*(\|.*)?$", line)
        if m and section:
            parts = m.group(1).split(";")
            res[section].append({"package": m.group(1), "api": su.parse_api(parts[1]), "tag": parts[2], "abi": parts[3],
                                 "revision": m.group(2), "desc": m.group(3)})
    return res, None


def cmd_images(a):
    sdk, _ = su.find_sdk()
    data = {"host_abi": su.host_abi(), "installed": su.system_images(sdk)}
    if a.available:
        lst, err = sdkmanager_list()
        data["available"] = [i for i in (lst or {}).get("available", []) if a.api is None or i["api"] == a.api]
        data["error"] = err
    if a.api is not None:
        data["installed"] = [i for i in data["installed"] if i["api"] == a.api]
    if a.json:
        print(json.dumps(data, ensure_ascii=False, indent=1))
        return
    print("Установлены: " + ("; ".join(f"{i['package']}" for i in data["installed"]) or "нет"))
    if a.available:
        av = [i for i in data["available"] if i["abi"] == data["host_abi"]]
        print(f"Доступны для {data['host_abi']}: " + ("; ".join(i["package"] for i in av) or (data["error"] or "нет")))


def cmd_profiles(a):
    am = su.tool_path("avdmanager")
    if not am:
        die("avdmanager не найден (cmdline-tools)", 127)
    code, out, err, _ = su.run_sdk_tool([am, "list", "device", "-c"], timeout=120)
    ids = [ln.strip() for ln in out.splitlines() if ln.strip() and not ln.startswith(("/", "Error", "Warning"))
           and su.JAVA_NOISE not in ln]
    print(json.dumps({"aliases": {k: v[0] for k, v in PROFILES.items()}, "ids": ids}, ensure_ascii=False, indent=1))


def cmd_name(a):
    ids, short, _, _ = resolve_profile(a.profile)
    _, tag, _ = choose_image(a.api, a.tag, a.abi)
    print(avd_name(a.api, short, a.ram, a.cores, tag, a.suffix))


def cmd_plan(a):
    plan = make_plan(a)
    if a.json:
        print(json.dumps(plan, ensure_ascii=False, indent=1))
        return
    print(f"AVD {plan['name']}: {plan['label']}, профиль {plan['profile']} ({plan['device_ids'][0]}), "
          f"ОЗУ {a.ram} МБ, ядер {a.cores}, данные {a.data}, образ {plan['image']} "
          f"({'установлен' if plan['image_installed'] else 'НЕ установлен'})"
          + (f"; AVD уже есть ({plan['existing_owner']})" if plan["exists"] else ""))
    if plan.get("warning"):
        print("Внимание: " + plan["warning"])
    for s in plan["steps"]:
        print("  " + s)


JAVA_NOTE = "Java -ea: строка «integer expression expected» скрыта — безвредна, команда завершилась успешно"


def note_image(run_dir, package, already, java_noise=0):
    """--run-dir: record the image in <RUN_DIR>/stands.json (images_installed) and a line in journal.md if it exists."""
    if not run_dir:
        return
    with Registry(run_dir) as reg:
        data = reg.load()
        data.setdefault("images_installed", []).append({"package": package, "at": now(), "already": already,
                                                        "java_ea_noise": bool(java_noise)})
        reg.save(data)
    journal = Path(run_dir) / "journal.md"
    if journal.exists():
        sys.path.insert(0, str(HERE / "shared"))
        import runjournal  # noqa: E402 — vendored shared module
        j = runjournal.need(run_dir)
        j["log"].append(f"- {runjournal.now()} — образ {'уже был' if already else 'установлен'}: {package}")
        runjournal.write(run_dir, j)


def cmd_install_image(a):
    image, tag, abi = choose_image(a.api, a.tag, a.abi)
    if image:
        print(f"образ уже установлен: {image['package']}")
        note_image(a.run_dir, image["package"], True)
        return
    lst, err = sdkmanager_list()
    cands = [i for i in (lst or {}).get("available", []) if i["api"] == a.api and i["tag"] == tag and i["abi"] == abi]
    exact = [i for i in cands if i["package"].split(";")[1] == f"android-{a.api}"]
    package = (exact or cands)[0]["package"] if (exact or cands) else f"system-images;android-{a.api};{tag};{abi}"
    free = su.disk_free_gb(su.avd_home())
    print(f"Установка: {package}\n  загрузка ≈ 1–2 ГБ, на диске ≈ 3–6 ГБ (оценка); свободно {free} ГБ"
          + ("" if cands else f"\n  в списке sdkmanager не найден ({err or 'нет такого пакета'}) — имя пакета предположительное"))
    if free is not None and free < 8:
        die(f"мало места на диске ({free} ГБ) — освободите не меньше 8 ГБ", 2)
    if not a.yes:
        print("План без изменений. Выполнить: тот же вызов с --yes (только после согласия пользователя).")
        return
    sm = su.tool_path("sdkmanager")
    if not sm:
        die("sdkmanager не найден (cmdline-tools)", 127)
    code, out, e, noise = su.run_sdk_tool([sm, "--install", package], timeout=3600,
                                          input=("y\n" * 30) if a.accept_licenses else "\n")
    text = out + e
    if code != 0 and re.search(r"licen[cs]e", text, re.I):
        die("лицензии не приняты: пользователь выполняет `sdkmanager --licenses` сам или соглашается и тогда — "
            "повтор с --accept-licenses", 5)
    if code != 0:
        die("sdkmanager: " + text.strip()[-400:], 2)
    print(text.strip()[-300:])
    if noise:
        print(f"({JAVA_NOTE})")
    print(f"готово: {package}")
    note_image(a.run_dir, package, False, noise)


def write_config(cfg_path, updates):
    lines = cfg_path.read_text(encoding="utf-8").splitlines() if cfg_path.exists() else []
    seen = set()
    out = []
    for ln in lines:
        k = ln.split("=", 1)[0].strip() if "=" in ln else None
        if k in updates:
            out.append(f"{k}={updates[k]}")
            seen.add(k)
        else:
            out.append(ln)
    out += [f"{k}={v}" for k, v in updates.items() if k not in seen and v is not None]
    cfg_path.write_text("\n".join(out) + "\n", encoding="utf-8")


def cmd_create(a):
    plan = make_plan(a)
    name = plan["name"]
    if plan["exists"]:
        if plan["existing_owner"] != "skill":
            die(f"AVD {name} уже есть и не создан скилом — не трогаю; выберите другое имя (--suffix)", 3)
        print(json.dumps({"name": name, "reused": True, "image": plan["image"]}, ensure_ascii=False))
        with Registry(a.run_dir) as reg:
            data = reg.load()
            if not any(x["name"] == name for x in data["avds_created"]):
                data.setdefault("avds_reused", [])
                if name not in data["avds_reused"]:
                    data["avds_reused"].append(name)
            reg.save(data)
        return
    if not plan["image_installed"]:
        die(f"нет образа {plan['image']}: {plan['steps'][0]}", 4)
    if not a.yes:
        cmd_plan(a)
        print("План без изменений. Создать: тот же вызов с --yes.")
        return
    am = su.tool_path("avdmanager")
    if not am:
        die("avdmanager не найден (cmdline-tools)", 127)
    last, noise = "", 0
    for dev in plan["device_ids"]:
        cmd = [am, "create", "avd", "-n", name, "-k", plan["image"], "-d", dev]
        code, out, err, noise = su.run_sdk_tool(cmd, timeout=300, input="no\n")
        last = (out + err).strip()
        if code == 0 and find_avd(name):
            plan["device"] = dev
            break
        if find_avd(name):  # created but returned an error: do not leave half-made AVDs
            break
    avd = find_avd(name)
    if not avd or not avd["exists"]:
        die("avdmanager не создал AVD: " + last[-400:], 2)
    path = Path(avd["path"])
    marker = {"created_by": "android-qa-audit", "created_at": now(), "image": plan["image"], "profile": plan["profile"],
              "device": plan.get("device"), "run_dir": str(Path(a.run_dir).resolve()) if a.run_dir else None,
              "config": plan["config"]}
    (path / su.AVD_MARKER).write_text(json.dumps(marker, ensure_ascii=False, indent=1), encoding="utf-8")
    write_config(path / "config.ini", plan["config"])
    with Registry(a.run_dir) as reg:
        data = reg.load()
        data["avds_created"].append({"name": name, "created_at": marker["created_at"], "image": plan["image"],
                                     "config": plan["config"]})
        reg.save(data)
    res = {"name": name, "created": True, "path": str(path), "image": plan["image"], "device": plan.get("device")}
    if noise:
        res["note"] = JAVA_NOTE
    print(json.dumps(res, ensure_ascii=False))


def port_free(port):
    for p in (port, port + 1):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.bind(("127.0.0.1", p))
        except OSError:
            return False
        finally:
            s.close()
    return True


def tcp_free(port):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def pick_grpc_port(reserved):
    """gRPC port of the emulator (127.0.0.1): 8554, 8556, … not used by another emulator of the run or the host."""
    for port in range(8554, 8700, 2):
        if port not in reserved and tcp_free(port):
            return port
    die("нет свободного порта gRPC 8554–8698")


def extra_emulator_args(a):
    """--extra-args and --mic-inject → list of flags checked by guard.check_emulator_args (deny → 3, confirm → 2)."""
    import shlex
    import guard  # noqa: E402 — same folder
    extra = shlex.split(a.extra_args or "")
    decision = guard.check_emulator_args(extra)
    if decision["decision"] == guard.DENY:
        print(json.dumps({"blocked": True, **decision}, ensure_ascii=False))
        die(f"флаги эмулятора запрещены: {decision['reason']}", 3)
    if decision["decision"] == guard.CONFIRM and not a.confirmed:
        print(json.dumps({"needs_confirmation": True, **decision}, ensure_ascii=False))
        die(f"нужно согласие пользователя: {decision['reason']} — после «да» тот же вызов с --confirmed", 2)
    return extra, decision


def pick_port(reserved, wanted=None):
    online = set(running_emulators())
    for port in ([wanted] if wanted else range(5554, 5684, 2)):
        if f"emulator-{port}" in online or port in reserved:
            continue
        if port_free(port):
            return port
    die(f"порт {wanted} занят" if wanted else "нет свободного порта эмулятора 5554–5682")


def cmd_start(a):
    avd = find_avd(a.name)
    if not avd:
        die(f"нет AVD {a.name} (avd_manager.py list)")
    foreign = not owned(avd)
    if foreign and not a.allow_foreign:
        die(f"AVD {a.name} не создан скилом — запуск только с разрешения пользователя (--allow-foreign), "
            "и тогда с -read-only -no-snapshot-save (его состояние не меняется)", 3)
    emu = su.tool_path("emulator")
    if not emu:
        die("emulator не найден (sdkmanager \"emulator\")", 127)
    if a.netspeed not in NETSPEED or a.netdelay not in NETDELAY:
        die(f"--netspeed из {NETSPEED}, --netdelay из {NETDELAY}")
    extra, _ = extra_emulator_args(a)
    if a.mic_inject and foreign:
        die("--mic-inject (gRPC с токеном) — только для своих AVD qa-*", 3)
    # One stand — one executor (S-7): an AVD that is already running is reused, not started again.
    already = [s for s, n in running_emulators().items() if n == a.name]
    if already and not a.read_only:
        die(f"AVD {a.name} уже запущен ({', '.join(already)}) — работать в нём (один стенд — одно действие за раз), "
            "лишний эмулятор не запускать; второй экземпляр — только --read-only и по решению оркестратора", 3)
    with Registry(a.run_dir) as reg:
        data = reg.load()
        reserved = {e["port"] for e in data["emulators"] if e.get("port") and su.pid_alive(e.get("pid"))}
        port = pick_port(reserved, a.port)
        cmd = [emu, "-avd", a.name, "-port", str(port), "-no-boot-anim", "-no-snapshot-save", "-no-metrics",
               "-netspeed", a.netspeed, "-netdelay", a.netdelay]
        read_only = a.read_only or foreign
        if read_only:
            cmd.append("-read-only")
        keep_audio = a.keep_audio or a.mic_inject
        if a.headless:
            cmd += ["-no-window"] + ([] if keep_audio else ["-no-audio"])
        grpc_port = None
        if a.mic_inject and "-grpc" not in extra:
            reserved = {e.get("grpc_port") for e in data["emulators"] if e.get("grpc_port") and su.pid_alive(e.get("pid"))}
            grpc_port = pick_grpc_port(reserved)
            cmd += ["-grpc", str(grpc_port), "-grpc-use-token"]
        elif "-grpc" in extra:
            grpc_port = int(extra[extra.index("-grpc") + 1])
        if "-gpu" not in extra:
            cmd += ["-gpu", a.gpu or ("swiftshader_indirect" if a.headless else "auto")]
        cmd += extra
        if a.cold_boot:
            cmd.append("-no-snapshot-load")
        if a.snapshot:
            cmd += ["-snapshot", a.snapshot]
        if a.wipe_data:
            if foreign:
                die("--wipe-data для чужого AVD запрещён", 3)
            cmd.append("-wipe-data")
        if a.locale:
            cmd += ["-change-locale", a.locale]
        if a.timezone:
            cmd += ["-timezone", a.timezone]
        log = (Path(a.run_dir) / "logs" if a.run_dir else Path(tempfile.gettempdir())) / f"emulator-{a.name}-{port}.log"
        proc = su.popen_detached(cmd, log)
        entry = {"name": a.name, "serial": f"emulator-{port}", "port": port, "pid": proc.pid, "started_at": now(),
                 "headless": a.headless, "read_only": read_only, "foreign": foreign, "log": str(log),
                 "owner": a.owner or "orchestrator", "args": [str(c) for c in cmd[1:]]}
        if grpc_port:
            entry.update({"grpc_port": grpc_port, "grpc_auth": "token" if "-grpc-use-token" in cmd else "jwt"})
        if extra:
            entry["extra_args"] = extra
        data["emulators"].append(entry)
        reg.save(data)
    time.sleep(1.5)
    if proc.poll() is not None:
        tail = log.read_text(encoding="utf-8", errors="replace")[-600:] if log.exists() else ""
        die(f"эмулятор завершился сразу (код {proc.returncode}): {mask(tail.strip())}", 6)
    if grpc_port:
        entry["note"] = ("gRPC 127.0.0.1:%d с токеном: токен — в discovery-файле эмулятора (adb emu avd discoverypath), "
                         "не печатается; подача звука — adb_helpers.py mic-inject" % grpc_port)
    print(json.dumps(entry, ensure_ascii=False))


def cmd_wait_boot(a):
    adb = su.Adb(a.serial, adb_path())
    start = time.time()
    entry = None
    if a.run_dir:
        entry = next((e for e in reversed(Registry(a.run_dir).load()["emulators"]) if e["serial"] == a.serial), None)
    stage = "ожидание устройства"
    while time.time() - start < a.timeout:
        if entry and entry.get("pid") and not su.pid_alive(entry["pid"]):
            tail = Path(entry["log"]).read_text(encoding="utf-8", errors="replace")[-600:] if Path(entry["log"]).exists() else ""
            die(f"процесс эмулятора завершился ({stage}): {mask(tail.strip())}", 6)
        code, state, _ = adb.cmd("get-state", timeout=10)
        if code == 0 and state.strip() == "device":
            stage = "загрузка Android"
            if adb.getprop("sys.boot_completed") == "1" and adb.getprop("init.svc.bootanim") in ("stopped", ""):
                c, out, _ = adb.shell("pm", "path", "android", timeout=15)
                if c == 0 and "package:" in out:
                    break
        time.sleep(3)
    else:
        die(f"{a.serial}: не загрузился за {a.timeout} с ({stage}); журнал эмулятора — logs/emulator-*.log", 6)
    if a.unlock:
        adb.shell("input", "keyevent", "82", timeout=10)
        adb.shell("wm", "dismiss-keyguard", timeout=10)
    if a.disable_animations:
        for key in ("window_animation_scale", "transition_animation_scale", "animator_duration_scale"):
            adb.shell("settings", "put", "global", key, "0", timeout=10)
    props = adb.getprop()
    secs = round(time.time() - start)
    print(json.dumps({"serial": a.serial, "ready": True, "boot_seconds": secs, **su.device_summary(props)},
                     ensure_ascii=False))
    sys.stderr.write(f"готов: {a.serial} загружен за {secs} с\n")


def ensure_own_emulator(serial, run_dir):
    data = Registry(run_dir).load() if run_dir else {"emulators": []}
    entry = next((e for e in reversed(data["emulators"]) if e["serial"] == serial), None)
    name = running_emulators().get(serial)
    avd = find_avd(name) if name else None
    if entry and not entry.get("foreign"):
        return entry, name
    if owned(avd):
        return entry, name
    die(f"{serial} ({name or '?'}) — не свой эмулятор: не трогаю", 3)


def cmd_snapshot(a):
    ensure_own_emulator(a.serial, a.run_dir)
    adb = su.Adb(a.serial, adb_path())
    args = ["emu", "avd", "snapshot", a.action] + ([a.snap] if a.snap else [])
    if a.action in ("save", "load") and not a.snap:
        die("нужно имя снимка")
    code, out, err = adb.cmd(*args, timeout=180)
    print((out + err).strip())
    sys.exit(0 if code == 0 and "KO" not in out else 2)


def stop_serial(serial, entry, adb):
    adb = su.Adb(serial, adb)
    adb.cmd("emu", "kill", timeout=20)
    deadline = time.time() + 40
    while time.time() < deadline:
        _, devs, _ = adb.devices()
        gone = not any(d["serial"] == serial for d in devs)
        dead = not (entry and su.pid_alive(entry.get("pid")))
        if gone and dead:
            return True
        time.sleep(1)
    if entry and su.pid_alive(entry.get("pid")):
        su.kill_pid(entry["pid"])
        return True
    return False


def cmd_stop(a):
    adb = adb_path()
    running = running_emulators()
    data = Registry(a.run_dir).load() if a.run_dir else {"emulators": []}
    targets = []
    if a.target in running:
        targets = [a.target]
    else:
        targets = [s for s, n in running.items() if n == a.target]
    if not targets:
        die(f"{a.target}: не запущен")
    for serial in targets:
        entry = next((e for e in reversed(data["emulators"]) if e["serial"] == serial), None)
        avd = find_avd(running.get(serial) or "")
        if not entry and not (a.any_qa and owned(avd)):
            die(f"{serial} ({running.get(serial)}) запущен не этим прогоном — не останавливаю"
                + ("" if owned(avd) else " (чужой AVD)") + "; свой AVD qa- можно остановить с --any-qa", 3)
        if entry and a.owner and entry.get("owner") not in (None, a.owner):
            die(f"{serial} — стенд потока {entry.get('owner')}, не {a.owner}: чужие стенды не останавливать "
                "(adb emu kill / kill-server тоже нельзя)", 3)
        ok = stop_serial(serial, entry, adb)
        print(f"{serial}: {'остановлен' if ok else 'не удалось остановить'}")
        if entry:
            with Registry(a.run_dir) as reg:
                d = reg.load()
                for e in d["emulators"]:
                    if e["serial"] == serial and e.get("pid") == entry.get("pid"):
                        e["stopped_at"] = now()
                reg.save(d)


def delete_avd(name):
    avd = find_avd(name)
    if not avd:
        die(f"нет AVD {name}")
    if not owned(avd):
        die(f"AVD {name} не создан скилом ({avd['owner']}) — удалять нельзя", 3)
    if name in running_emulators().values():
        die(f"AVD {name} запущен — сначала avd_manager.py stop", 2)
    home = su.avd_home().resolve()
    path = Path(avd["path"]).resolve()
    if path.parent != home or not path.name.startswith(su.AVD_PREFIX):
        die(f"путь {path} вне {home} — удаляю только вручную", 3)
    am = su.tool_path("avdmanager")
    if am:
        su.run_sdk_tool([am, "delete", "avd", "-n", name], timeout=120)
    if path.exists():
        shutil.rmtree(path)
    ini = home / f"{name}.ini"
    if ini.exists():
        ini.unlink()
    return True


def cmd_delete(a):
    if not a.yes:
        die("удаление только с --yes (после ответа пользователя)")
    delete_avd(a.name)
    print(f"удалён AVD {a.name}")


def cmd_cleanup(a):
    reg = Registry(a.run_dir)
    data = reg.load()
    run = Path(a.run_dir)
    plan = []
    alive = [e for e in data["emulators"] if not e.get("stopped_at") and su.pid_alive(e.get("pid"))]
    if a.stop:
        plan += [("stop", e["serial"], e["name"]) for e in alive]
    if a.delete_avds:
        plan += [("delete-avd", x["name"], "") for x in data["avds_created"] if find_avd(x["name"])]
    if a.delete_apk_copies and (run / "apk").is_dir():
        plan += [("rm", str(p), "") for p in sorted((run / "apk").iterdir()) if p.suffix.lower() in (".apk", ".aab", ".apks", ".xapk")]
    if a.delete_recordings and (run / "recordings").is_dir():
        plan += [("rm", str(p), "") for p in sorted((run / "recordings").iterdir()) if p.is_file()]
    if not plan:
        print("уборка: нечего делать")
        return
    for act, what, extra in plan:
        print(f"  {act}: {what} {extra}".rstrip())
    if not a.yes:
        print("План без изменений. Выполнить: тот же вызов с --yes (после ответа пользователя).")
        return
    adb = adb_path()
    for act, what, extra in plan:
        if act == "stop":
            entry = next(e for e in alive if e["serial"] == what)
            stop_serial(what, entry, adb)
            with Registry(a.run_dir) as r:
                d = r.load()
                for e in d["emulators"]:
                    if e["serial"] == what and e.get("pid") == entry.get("pid"):
                        e["stopped_at"] = now()
                r.save(d)
        elif act == "delete-avd":
            try:
                delete_avd(what)
            except SystemExit as ex:
                print(f"  не удалён {what}: код {ex.code}")
                continue
            with Registry(a.run_dir) as r:
                d = r.load()
                for x in d["avds_created"]:
                    if x["name"] == what:
                        x["deleted_at"] = now()
                r.save(d)
        else:
            Path(what).unlink(missing_ok=True)
    print("уборка: готово")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list").add_argument("--json", action="store_true")
    im = sub.add_parser("images")
    im.add_argument("--available", action="store_true")
    im.add_argument("--api", type=int)
    im.add_argument("--json", action="store_true")
    sub.add_parser("profiles")
    for name in ("name", "plan"):
        plan_args(sub.add_parser(name))
    plan_args(sub.add_parser("create"), create=True)
    ii = sub.add_parser("install-image")
    ii.add_argument("--api", type=int, required=True)
    ii.add_argument("--tag")
    ii.add_argument("--abi", default="auto")
    ii.add_argument("--yes", action="store_true")
    ii.add_argument("--accept-licenses", action="store_true")
    ii.add_argument("--run-dir", help="записать образ в <RUN_DIR>/stands.json (images_installed) и в journal.md")
    st = sub.add_parser("start")
    st.add_argument("name")
    st.add_argument("--port", type=int)
    st.add_argument("--headless", action="store_true")
    st.add_argument("--cold-boot", action="store_true")
    st.add_argument("--wipe-data", action="store_true")
    st.add_argument("--read-only", action="store_true")
    st.add_argument("--snapshot")
    st.add_argument("--netspeed", default="full")
    st.add_argument("--netdelay", default="none")
    st.add_argument("--locale")
    st.add_argument("--timezone")
    st.add_argument("--gpu")
    st.add_argument("--allow-foreign", action="store_true")
    st.add_argument("--owner", help="поток-владелец стенда (w1, w2…); записывается в stands.json")
    st.add_argument("--extra-args", help="дополнительные флаги эмулятора одной строкой (белый список guard.py emulator-args)")
    st.add_argument("--mic-inject", action="store_true",
                    help="gRPC с токеном для mic-inject: -grpc <свободный порт> -grpc-use-token, звук не выключается")
    st.add_argument("--keep-audio", action="store_true", help="с --headless не добавлять -no-audio")
    st.add_argument("--confirmed", action="store_true", help="пользователь согласился на флаги уровня confirm")
    st.add_argument("--run-dir")
    wb = sub.add_parser("wait-boot")
    wb.add_argument("serial")
    wb.add_argument("--timeout", type=int, default=420)
    wb.add_argument("--unlock", action="store_true")
    wb.add_argument("--disable-animations", action="store_true")
    wb.add_argument("--run-dir")
    sn = sub.add_parser("snapshot")
    sn.add_argument("action", choices=["save", "load", "list"])
    sn.add_argument("serial")
    sn.add_argument("snap", nargs="?")
    sn.add_argument("--run-dir")
    sp = sub.add_parser("stop")
    sp.add_argument("target")
    sp.add_argument("--owner", help="поток, который останавливает: чужой стенд (другой owner в stands.json) — код 3")
    sp.add_argument("--run-dir")
    sp.add_argument("--any-qa", action="store_true")
    de = sub.add_parser("delete")
    de.add_argument("name")
    de.add_argument("--yes", action="store_true")
    cl = sub.add_parser("cleanup")
    cl.add_argument("--run-dir", required=True)
    cl.add_argument("--stop", action="store_true")
    cl.add_argument("--delete-avds", action="store_true")
    cl.add_argument("--delete-apk-copies", action="store_true")
    cl.add_argument("--delete-recordings", action="store_true")
    cl.add_argument("--yes", action="store_true")
    a = ap.parse_args()
    {"list": cmd_list, "images": cmd_images, "profiles": cmd_profiles, "name": cmd_name, "plan": cmd_plan,
     "install-image": cmd_install_image, "create": cmd_create, "start": cmd_start, "wait-boot": cmd_wait_boot,
     "snapshot": cmd_snapshot, "stop": cmd_stop, "delete": cmd_delete, "cleanup": cmd_cleanup}[a.cmd](a)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
