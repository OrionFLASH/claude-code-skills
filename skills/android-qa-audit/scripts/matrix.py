#!/usr/bin/env python3
"""Device matrix «Android API × hardware × runtime variants» by depth, split into up to 4 threads
(references/depth-matrix.md, references/parallelism.md).

  matrix.py build --config run-config.yaml [--env env.json] [--apk-info apk-info.json] [--out device-matrix.json]
                  [--max-workers N] [--json]
  matrix.py show device-matrix.json
  matrix.py variants                          runtime variants and the adb_helpers.py commands behind them

Hardware: devices.hardware null — by depth (+ devices.custom); a list — these + custom; [] with custom — only custom;
both empty — by depth. The first profile is primary (phone by default). A list item may be the name of an existing
own AVD qa-* (its RAM, cores, profile and API are taken from its config.ini; the cell runs only on its API).
Existing own AVDs qa-* with the same API, RAM, cores and device profile are reused instead of creating new ones
(stand.existing: true); own AVDs with other RAM for the same API are suggested in notes.
matrix.cells — user cells: {id, api, hardware, variants, directions, scenario, manual_minutes, background_minutes}
(a long recording, a soak): kind custom. Time: est_minutes = manual work of the agent; est_background_minutes —
background jobs (adb_helpers.py job), they run while the agent works with another stand.
Rules: the primary hardware profile runs on every selected API; other profiles run on the target API
(low-end also on the lowest API); runtime variants (dark theme, font, landscape, RTL, network, battery) run as
settings on an already started stand — no extra AVD. matrix.mode: full in run-config gives the full cartesian
product. Real devices and allowed foreign AVDs from stands.* become their own cells pinned to one thread.
Threads: min(parallel.max_workers ≤ 4, host RAM / (AVD RAM + 1 GB), env.json recommended_max_workers).
"""
import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "shared"))
sys.path.insert(0, str(HERE))
import miniyaml  # noqa: E402
import sdkutil as su  # noqa: E402

MAX_WORKERS = 4
HARDWARE = {  # id -> AVD parameters (avd_manager.py profiles)
    "phone": {"profile": "phone", "ram_mb": 4096, "cores": 4, "data": "6G", "label": "телефон 1080×2400, 4 ГБ, 4 ядра"},
    "phone-8gb": {"profile": "phone", "ram_mb": 8192, "cores": 4, "data": "6G", "label": "телефон 1080×2400, 8 ГБ, 4 ядра"},
    "low-end": {"profile": "small", "ram_mb": 2048, "cores": 2, "data": "4G", "label": "слабый телефон 720×1280, 2 ГБ, 2 ядра"},
    "low-1gb": {"profile": "small", "ram_mb": 1024, "cores": 1, "data": "2G", "label": "очень слабый: 1 ГБ, 1 ядро (API ≤ 29)"},
    "small": {"profile": "small", "ram_mb": 3072, "cores": 2, "data": "4G", "label": "малый экран 720×1280"},
    "large": {"profile": "large", "ram_mb": 6144, "cores": 4, "data": "6G", "label": "большой телефон 1440×3120"},
    "tablet": {"profile": "tablet", "ram_mb": 4096, "cores": 4, "data": "6G", "label": "планшет 2560×1600"},
    "fold": {"profile": "fold", "ram_mb": 4096, "cores": 4, "data": "6G", "label": "складной 2208×1840 (API ≥ 32)"},
}
VARIANTS = {  # id -> (description, adb_helpers.py commands, reset commands)
    "base": ("как есть", [], []),
    "dark": ("тёмная тема", ["dark-mode on"], ["dark-mode off"]),
    "font-1.3": ("крупный шрифт 1.3", ["font-scale 1.3"], ["font-scale 1.0"]),
    "font-2.0": ("шрифт 2.0 (максимум Android 14+)", ["font-scale 2.0"], ["font-scale 1.0"]),
    "dark-font": ("тёмная тема + шрифт 1.3", ["dark-mode on", "font-scale 1.3"], ["dark-mode off", "font-scale 1.0"]),
    "landscape": ("альбомная ориентация", ["rotate landscape"], ["rotate portrait"]),
    "display-large": ("крупный масштаб экрана (density +20%)", ["density <DENSITY*1.2>"], ["density reset"]),
    "rtl": ("RTL-язык (арабский)", ["locale ar <PKG>"], ["locale <APP_LOCALE> <PKG>"]),
    "locale": ("другой язык приложения", ["locale <LOCALE> <PKG>"], ["locale <APP_LOCALE> <PKG>"]),
    "net-3g": ("медленная сеть 3G", ["network 3g"], ["network online"]),
    "net-edge": ("очень медленная сеть EDGE", ["network edge"], ["network online"]),
    "offline": ("без сети", ["network offline"], ["network online"]),
    "net-switch": ("смена сети в процессе", ["network switch --seconds 5"], []),
    "battery-low": ("низкий заряд 5 %", ["battery level 5"], ["battery reset"]),
    "saver": ("экономия заряда", ["battery saver-on"], ["battery saver-off", "battery reset"]),
    "doze": ("Doze (фон)", ["doze enter"], ["doze exit"]),
    "timezone": ("другой часовой пояс", ["timezone <TZ>"], ["timezone <HOST_TZ>"]),
}
DEPTH = {
    "smoke": {"apis": 1, "hardware": ["phone"], "variants": ["base"], "minutes": 25, "secondary_minutes": 15},
    "standard": {"apis": 3, "hardware": ["phone", "low-end"],
                 "variants": ["base", "dark-font", "landscape", "net-3g", "offline"], "minutes": 50, "secondary_minutes": 25},
    "deep": {"apis": 6, "hardware": ["phone", "low-end", "small", "tablet", "fold"],
             "variants": ["base", "dark", "font-2.0", "landscape", "display-large", "rtl", "net-edge", "offline",
                          "net-switch", "battery-low", "saver", "doze", "timezone"], "minutes": 90, "secondary_minutes": 35},
}
COMPAT_DIRECTIONS = ["functional", "visual-ui", "device-config-compat", "compatibility", "lifecycle-resilience", "performance",
                     "accessibility"]
MIDDLE = [29, 30, 31, 33, 34]


def floor_api(host_abi):
    """Lowest API with practical emulator images for the host (arm64 images before 24 are rare)."""
    return 24 if host_abi == "arm64-v8a" else 21


def pick_apis(depth, mn, tg, installed, host_abi, explicit=None):
    if explicit:
        return sorted({int(x) for x in explicit})
    latest = max(installed) if installed else None
    top = tg or latest or 35
    lo = min(max(mn or floor_api(host_abi), floor_api(host_abi)), top)
    if depth == "smoke":
        near = [a for a in installed if lo <= a <= top + 1]
        return [max(near) if near else top]
    if depth == "standard":
        mid = min((a for a in MIDDLE if lo < a < top), key=lambda a: abs(a - (lo + top) / 2), default=None)
        return sorted({lo, top} | ({mid} if mid else set()))
    out = {lo, top} | ({latest} if latest and latest > top else set())
    hi = max(out)
    for a in (33, 29, 31, 34, 26, 35, 30, 28):  # behaviour changes: notifications, scoped storage, exported, …
        if len(out) >= 7:
            break
        if lo < a < hi:
            out.add(a)
    return sorted(out)


def tag_for(api, images, host_abi, preferred=None):
    have = [i for i in images if i.get("api") == api and i.get("abi") == host_abi]
    if preferred:
        hit = [i for i in have if i["tag"] == preferred]
        return preferred, (hit[0]["package"] if hit else None)
    for t in ("google_apis", "default", "google_apis_playstore"):
        hit = [i for i in have if i["tag"] == t]
        if hit:
            return t, hit[0]["package"]
    return "google_apis", None


def avd_name(api, hw, tag):
    import avd_manager  # noqa: E402 — same folder
    p = HARDWARE[hw]
    short = avd_manager.PROFILES[p["profile"]][1]
    return avd_manager.avd_name(api, short, p["ram_mb"], p["cores"], tag)


def avd_profile(avd):
    """Profile alias of an AVD by its hw.device.name (pixel_7 → phone)."""
    import avd_manager  # noqa: E402 — same folder
    dev = avd.get("device") or ""
    return next((k for k, v in avd_manager.PROFILES.items() if dev in v[0]), "phone")


def hardware_from_avd(name, env, notes):
    """devices.hardware: [qa-…] — an existing own AVD as a hardware profile pinned to its API."""
    avd = next((x for x in env.get("avds") or [] if x.get("name") == name), None)
    if not avd:
        notes.append(f"AVD {name} не найден (avd_manager.py list) — профиль пропущен")
        return None
    if avd.get("owner") != "skill":
        notes.append(f"AVD {name} не создан скилом — только stands.use_avds (с разрешения, -read-only); пропущен")
        return None
    data = f"{avd['data_mb'] // 1024}G" if avd.get("data_mb") else "6G"
    HARDWARE[name] = {"profile": avd_profile(avd), "ram_mb": avd.get("ram_mb") or 2048, "cores": avd.get("cores") or 2,
                      "data": data, "label": f"свой AVD {name} ({(avd.get('ram_mb') or 0) // 1024} ГБ, {avd.get('cores') or '?'} ядра)",
                      "avd": name, "fixed_api": avd.get("api"), "tag": avd.get("tag")}
    return name


def existing_avd(env, api, hw, tag):
    """An own AVD qa-* that already has the parameters of this cell (API, RAM, cores, device profile, tag)."""
    p = HARDWARE[hw]
    if p.get("avd"):
        return p["avd"]
    for a in env.get("avds") or []:
        if a.get("owner") != "skill" or a.get("api") != api:
            continue
        if a.get("ram_mb") == p["ram_mb"] and a.get("cores") == p["cores"] and avd_profile(a) == p["profile"] and \
                (a.get("tag") in (None, tag)):
            return a["name"]
    return None


def pick_hardware(devices, depth_default, notes, env=None):
    """Hardware profiles of the matrix (the first one is primary).

    devices.hardware: null/absent — by depth (+ custom profiles); a list — exactly these (+ custom); an empty list
    with custom profiles — ONLY the custom ones; both empty — by depth. An item qa-… — an existing own AVD."""
    custom_ids = []
    for name in devices.get("hardware") or [] if isinstance(devices.get("hardware"), list) else []:
        if isinstance(name, str) and name.startswith("qa-") and name not in HARDWARE:
            hardware_from_avd(name, env or {}, notes)
    for h in devices.get("custom") or []:
        if isinstance(h, dict) and h.get("id"):
            HARDWARE[h["id"]] = {"profile": h.get("profile", "phone"), "ram_mb": int(h.get("ram_mb", 2048)),
                                 "cores": int(h.get("cores", 2)), "data": h.get("data", "6G"), "label": h.get("label", h["id"])}
            custom_ids.append(h["id"])
    listed = devices.get("hardware")
    if isinstance(listed, list):
        hardware = [h for h in listed if h in HARDWARE] + custom_ids
        if not hardware:
            hardware = list(depth_default)
            notes.append("devices.hardware и devices.custom пусты — железо по глубине")
        elif not [h for h in listed if h in HARDWARE]:
            notes.append(f"devices.hardware пуст — только свои профили: {', '.join(custom_ids)}")
    else:
        hardware = list(depth_default) + custom_ids
    return list(dict.fromkeys(hardware)), custom_ids


def build(cfg, env, apk, max_workers=None):
    depth = cfg.get("depth") or "standard"
    if depth not in DEPTH:
        depth = "standard"
    d = DEPTH[depth]
    host_abi = (env.get("host") or {}).get("abi") or su.host_abi()
    images = env.get("images") or []
    installed = sorted({i["api"] for i in images if i.get("abi") == host_abi and i.get("api")})
    android = cfg.get("android") or {}
    devices = cfg.get("devices") or {}
    mn = apk.get("min_sdk") if isinstance(apk.get("min_sdk"), int) else None
    tg = apk.get("target_sdk") if isinstance(apk.get("target_sdk"), int) else None
    explicit_apis = android.get("apis") if isinstance(android.get("apis"), list) and android.get("apis") else None
    apis = pick_apis(depth, mn, tg, installed, host_abi, explicit_apis)
    if android.get("include_latest") and installed and max(installed) not in apis:
        apis.append(max(installed))
    if android.get("include_min") and mn and mn >= floor_api(host_abi) and mn not in apis:
        apis.append(mn)
    apis = sorted(apis)
    notes = []
    hardware, custom_ids = pick_hardware(devices, d["hardware"], notes, env)
    variants = [v for v in (devices.get("variants") or d["variants"]) if v in VARIANTS]
    directions = cfg.get("directions") or []
    full = (cfg.get("matrix") or {}).get("mode") == "full"
    if mn and mn < floor_api(host_abi):
        notes.append(f"minSdk {mn}: образов эмулятора ниже API {floor_api(host_abi)} для {host_abi} обычно нет — "
                     "нижняя граница проверяется на реальном устройстве или x86_64-хосте")
    primary = hardware[0] if hardware else "phone"
    target_api = tg if tg in apis else max(apis)
    low_api = min(apis)
    cells = []

    def add_cell(api, hw, kind, cell_variants, dirs, extra=None):
        if hw == "fold" and api < 32:
            notes.append(f"складной профиль пропущен на API {api} (нужен API ≥ 32)")
            return
        if hw == "low-1gb" and api > 29:
            notes.append(f"1 ГБ ОЗУ на API {api} не поддерживается образами — пропуск")
            return
        p = HARDWARE[hw]
        if p.get("fixed_api") and p["fixed_api"] != api:
            return
        tag, pkg = tag_for(api, images, host_abi, p.get("tag") or (cfg.get("android") or {}).get("image_tag"))
        have = existing_avd(env, api, hw, tag)
        name = have or avd_name(api, hw, tag)
        cell = {"id": f"c{len(cells) + 1:02d}", "kind": kind, "api": api, "label": su.api_label(api), "hardware": hw,
                "hardware_label": p["label"], "ram_mb": p["ram_mb"], "cores": p["cores"], "data": p["data"],
                "profile": p["profile"], "variants": cell_variants, "directions": dirs,
                "stand": {"type": "avd", "name": name, "tag": tag, "existing": bool(have),
                          "image": pkg or f"system-images;android-{api};{tag};{host_abi}", "image_installed": bool(pkg) or bool(have)},
                "est_minutes": (d["minutes"] if kind == "primary" else d["secondary_minutes"]) + 4 * max(0, len(cell_variants) - 1),
                "est_background_minutes": 0}
        cell.update(extra or {})
        cells.append(cell)

    compat_dirs = [x for x in directions if x in COMPAT_DIRECTIONS] or directions
    apis = sorted(set(apis) | {HARDWARE[h]["fixed_api"] for h in hardware if HARDWARE[h].get("fixed_api")})
    target_api = tg if tg in apis else max(apis)
    low_api = min(apis)
    for api in apis:
        for hw in hardware:
            is_primary = api == target_api and hw == primary
            if not full and not is_primary:
                if hw == primary:
                    pass
                elif hw in ("low-end", "low-1gb") and api in (low_api, target_api):
                    pass
                elif api != target_api:
                    continue
            add_cell(api, hw, "primary" if is_primary else "secondary",
                     variants if is_primary else (["base"] if not full else variants),
                     directions if is_primary else compat_dirs)
    for i, uc in enumerate((cfg.get("matrix") or {}).get("cells") or [], 1):
        if not isinstance(uc, dict):
            continue
        hw = uc.get("hardware") or primary
        if isinstance(hw, str) and hw.startswith("qa-") and hw not in HARDWARE:
            hardware_from_avd(hw, env, notes)
        if hw not in HARDWARE:
            notes.append(f"matrix.cells[{i}]: профиль «{hw}» неизвестен — ячейка пропущена")
            continue
        api = int(uc.get("api") or HARDWARE[hw].get("fixed_api") or target_api)
        before = len(cells)
        add_cell(api, hw, "custom", uc.get("variants") or ["base"], uc.get("directions") or directions,
                 {"scenario": uc.get("scenario") or uc.get("id") or f"сценарий {i}", "user_id": uc.get("id"),
                  "est_minutes": int(uc.get("manual_minutes") or 15),
                  "est_background_minutes": int(uc.get("background_minutes") or 0)})
        if len(cells) == before:
            notes.append(f"matrix.cells[{i}]: API {api} не подходит профилю {hw} — пропущено")
    own = [a for a in env.get("avds") or [] if a.get("owner") == "skill"]
    used = {c["stand"].get("name") for c in cells}
    for c in [c for c in cells if c["stand"].get("type") == "avd" and not c["stand"].get("existing")]:
        alt = [a["name"] for a in own if a.get("api") == c["api"] and a["name"] not in used]
        if alt:
            notes.append(f"{c['id']}: создаётся {c['stand']['name']}, а есть свои AVD API {c['api']}: {', '.join(alt)} — "
                         f"взять вместо: devices.hardware: [{alt[0]}]")
    stands = cfg.get("stands") or {}
    for dev in env.get("devices") or []:
        if dev.get("state") != "device" or dev.get("serial") not in (stands.get("use_devices") or []):
            continue
        cells.append({"id": f"c{len(cells) + 1:02d}", "kind": "device", "api": dev.get("api"), "label": su.api_label(dev.get("api")),
                      "hardware": "device", "hardware_label": f"{dev.get('kind')} {dev.get('model') or ''}".strip(),
                      "variants": ["base"], "directions": compat_dirs,
                      "stand": {"type": "device", "serial": dev["serial"], "kind": dev.get("kind")},
                      "est_minutes": d["secondary_minutes"]})
    for name in stands.get("use_avds") or []:
        avd = next((x for x in env.get("avds") or [] if x.get("name") == name), None)
        if avd:
            cells.append({"id": f"c{len(cells) + 1:02d}", "kind": "foreign-avd", "api": avd.get("api"), "label": su.api_label(avd.get("api")),
                          "hardware": "foreign-avd", "hardware_label": f"AVD пользователя {name} (только -read-only)",
                          "variants": ["base"], "directions": compat_dirs,
                          "stand": {"type": "foreign-avd", "name": name, "read_only": True}, "est_minutes": d["secondary_minutes"]})
    threads = plan_threads(cells, cfg, env, max_workers)
    to_install = sorted({c["stand"]["image"] for c in cells if c["stand"].get("type") == "avd" and not c["stand"].get("image_installed")})
    mem = env.get("host") or {}
    return {"depth": depth, "host_abi": host_abi, "apis": apis, "app": {"min_sdk": mn, "target_sdk": tg},
            "hardware": {h: HARDWARE[h] for h in hardware}, "variants": {v: {"desc": VARIANTS[v][0], "commands": VARIANTS[v][1],
                                                                            "reset": VARIANTS[v][2]} for v in variants},
            "cells": cells, "threads": threads,
            "time": {"manual_minutes": sum(c.get("est_minutes") or 0 for c in cells),
                     "background_minutes": sum(c.get("est_background_minutes") or 0 for c in cells)},
            "resources": {"emulators_parallel": len(threads), "images_to_install": to_install,
                          "download_estimate_gb": f"≈ {len(to_install)}–{2 * len(to_install)}" if to_install else "0",
                          "avds_to_create": sorted({c["stand"]["name"] for c in cells if c["stand"].get("type") == "avd"
                                                    and not c["stand"].get("existing")}),
                          "avds_existing": sorted({c["stand"]["name"] for c in cells if c["stand"].get("existing")}),
                          "host_ram_mb": mem.get("total_mb"), "host_available_mb": mem.get("available_mb")},
            "notes": notes}


def plan_threads(cells, cfg, env, max_workers=None):
    asked = max_workers or ((cfg.get("parallel") or {}).get("max_workers")) or 2
    asked = max(1, min(MAX_WORKERS, int(asked)))
    mem = env.get("host") or {}
    avail = mem.get("available_mb")
    heaviest = max([c.get("ram_mb") or 2048 for c in cells] or [2048])
    by_ram = max(1, (avail - 2048) // (heaviest + 1024)) if avail else asked
    rec = env.get("recommended_max_workers") or asked
    n = max(1, min(asked, by_ram, rec, len(cells) or 1))
    threads = [{"id": f"w{i + 1}", "cells": [], "est_minutes": 0} for i in range(n)]
    pinned = {}
    for c in sorted(cells, key=lambda x: -x["est_minutes"]):
        key = c["stand"].get("serial") or (c["stand"]["name"] if c["stand"].get("type") == "foreign-avd" else None)
        if key and key in pinned:
            t = pinned[key]
        else:
            t = min(threads, key=lambda x: x["est_minutes"])
            if key:
                pinned[key] = t
        t["cells"].append(c["id"])
        t["est_minutes"] += c["est_minutes"]
    return [t for t in threads if t["cells"]]


def show(m):
    L = [f"Матрица ({m['depth']}): API {', '.join(map(str, m['apis']))}; потоков {len(m['threads'])}; "
         f"ABI образов {m['host_abi']}", "",
         "| Ячейка | API | Железо | Вариации | Стенд | Образ | Направления | ≈ мин (ручное + фон) |",
         "|---|---|---|---|---|---|---|---|"]
    for c in m["cells"]:
        st = c["stand"]
        stand = (st.get("name") or st.get("serial") or "") + (" (есть)" if st.get("existing") else "")
        img = ("есть" if st.get("image_installed") else "скачать") if st.get("type") == "avd" else "—"
        bg = c.get("est_background_minutes") or 0
        what = c["kind"] + (f": {c['scenario']}" if c.get("scenario") else "")
        L.append(f"| {c['id']} ({what}) | {c['label']} | {c['hardware_label']} | {', '.join(c['variants'])} | "
                 f"`{stand}` | {img} | {len(c['directions'])} | {c['est_minutes']}{f' + {bg} фон' if bg else ''} |")
    L += ["", "Потоки: " + "; ".join(f"{t['id']}: {', '.join(t['cells'])} (≈ {t['est_minutes']} мин)" for t in m["threads"])]
    tm = m.get("time") or {}
    if tm.get("background_minutes"):
        L.append(f"Время: ручная работа ≈ {tm['manual_minutes']} мин + фоновые задачи ≈ {tm['background_minutes']} мин "
                 "(adb_helpers.py job: идут, пока агент работает с другим стендом; long-runs.md)")
    r = m["resources"]
    if r["images_to_install"]:
        L.append(f"Нужно скачать образы ({r['download_estimate_gb']} ГБ, только после согласия): " + ", ".join(r["images_to_install"]))
    L += [f"Примечание: {n}" for n in m.get("notes") or []]
    return "\n".join(L)


def load_json(p):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8")) if p and Path(p).exists() else {}
    except ValueError:
        return {}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--config", required=True)
    b.add_argument("--env")
    b.add_argument("--apk-info")
    b.add_argument("--out")
    b.add_argument("--max-workers", type=int)
    b.add_argument("--json", action="store_true")
    s = sub.add_parser("show")
    s.add_argument("matrix")
    sub.add_parser("variants")
    a = ap.parse_args()
    if a.cmd == "variants":
        for k, (desc, cmds, reset) in VARIANTS.items():
            print(f"{k:<14} {desc:<36} {'; '.join(cmds) or '—'}  (сброс: {'; '.join(reset) or '—'})")
        return
    if a.cmd == "show":
        print(show(load_json(a.matrix)))
        return
    cfg = miniyaml.load_file(a.config) or {}
    run_dir = Path(a.config).resolve().parent
    env = load_json(a.env or run_dir / "env.json")
    apk = load_json(a.apk_info or run_dir / "apk-info.json")
    m = build(cfg, env, apk, a.max_workers)
    out = Path(a.out) if a.out else run_dir / "device-matrix.json"
    out.write_text(json.dumps(m, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(m, ensure_ascii=False, indent=1) if a.json else show(m) + f"\n\n-> {out}")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
