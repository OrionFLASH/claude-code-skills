#!/usr/bin/env python3
"""Long scenarios for android-qa-audit (references/long-runs.md): `adb_helpers.py soak` and `adb_helpers.py job`.
Not a CLI of its own — adb_helpers.py registers the subcommands and passes itself as `h`.

soak: optional start action (tap by text/desc/id or X,Y) → PRECONDITION within --expect-timeout (a text on the screen
and/or a running service of the app) — otherwise the run is `invalid` at once, not after N minutes → every --every
seconds a sample (PSS, PID, free space of /data, focus, service, battery, thermal status, host load) into
raw/soak-<tag>-<serial>.jsonl, screenshots every --screenshots minutes, optional screen off/on → optional stop action
→ result check (a duration ≈ N minutes on the screen, or the duration of a result file pulled from shared storage) →
summary raw/soak-<tag>-<serial>.json (build_report.py: «Длинные сценарии»). Statuses: ok | interrupted (service lost
or process died during the run — a finding) | result-mismatch (the result is shorter / longer than expected) |
invalid (precondition failed — the run says nothing about the app) | stopped (job stop) | failed (error).
Exit code: 0 — ok / interrupted / result-mismatch (look at status), 5 — invalid / failed, 2/3/6 — guard.
--clips-on-crash (1.5.0, references/clips.md): continuous screen recording in segments (clip_android rolling) during
the run; the app's process is checked every ~2 s and the «isn't responding» dialog every ~6 s; on a death / restart /
ANR the last seconds are saved as a clip (clips/soak-<tag>-<event>-<min>m.mp4, summary: clips[], events[].clip).

job: start any adb_helpers.py subcommand in the background (detached; its output — logs/job-<id>.log; state —
raw/jobs/<id>.json) while the orchestrator works with another stand: start / status / list / stop / log.
job stop: writes the stop request raw/jobs/<id>.stop (the job sees it as ANDROID_QA_STOP_FILE; soak checks it every
≤ 0.5 s and between samples and writes its summary `stopped`), then — POSIX — SIGTERM as well; on Windows (no
signals for a detached process) it waits up to --grace seconds for soak to finish by itself and only then kills the
process tree (status `killed`, the summary is not written). Other subcommands are stopped at once.
ANDROID_QA_JOB_STOP=file — the Windows behaviour on any OS (tests, diagnostics).
"""
import argparse
import json
import os
import re
import signal
import struct
import subprocess
import sys
import time
import wave
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
DURATION_RX = re.compile(r"(?<![\d:])(?:(\d{1,2}):)?(\d{1,2}):(\d{2})(?![\d:])")
STOP_ENV = "ANDROID_QA_STOP_FILE"      # set by job-run for its child: the stop request file of the job
GRACEFUL = ("soak",)                   # job subcommands that react to the stop file and write a summary
STOP_SLICE_S = 0.5


class Stop(Exception):
    pass


def stop_requested():
    p = os.environ.get(STOP_ENV)
    return bool(p) and os.path.exists(p)


def file_stop_mode():
    """True — stop jobs by the stop file only (Windows: a detached process gets no SIGTERM; or ANDROID_QA_JOB_STOP=file)."""
    return os.name == "nt" or (os.environ.get("ANDROID_QA_JOB_STOP") or "").lower() == "file"


def sleep_or_stop(seconds):
    """Sleep in short slices; a stop request (job stop) interrupts the wait → Stop."""
    end = time.time() + max(0.0, seconds)
    while True:
        if stop_requested():
            raise Stop()
        left = end - time.time()
        if left <= 0:
            return
        time.sleep(min(STOP_SLICE_S, left))


def now():
    return datetime.now().isoformat(timespec="seconds")


def minutes_arg(v):
    return float(v) if v not in (None, "") else None


# ---------------------------------------------------------------- samples

def parse_df(text):
    """`df /data` (toybox): available KB of the last line."""
    lines = [ln.split() for ln in (text or "").splitlines() if ln.strip()]
    if len(lines) < 2:
        return None
    head, row = lines[0], lines[-1]
    i = next((k for k, x in enumerate(head) if x.lower().startswith("avail")), 3)
    try:
        return int(row[i])
    except (ValueError, IndexError):
        return None


def services_of(text):
    return re.findall(r"\* ServiceRecord\{\S+ \S+ ([\w.$/]+)\}", text or "")


def sample(c, h, pkg, a, start, last_pid):
    rec = {"t_s": round(time.time() - start, 1), "time": now()}
    metrics = set(a.metrics.split(","))
    pids = h.app_pids(c.adb, pkg)
    rec["pid"] = pids[0] if pids else None
    rec["pid_changed"] = bool(last_pid and rec["pid"] and rec["pid"] != last_pid)
    if "meminfo" in metrics:
        _, out, _ = c.adb.shell("dumpsys", "meminfo", pkg, timeout=60)
        m = h.parse_meminfo(out) if "No process found" not in out else {}
        rec["pss_kb"] = m.get("total_pss_kb")
        rec["java_kb"], rec["native_kb"] = m.get("java_heap_kb"), m.get("native_heap_kb")
    if "df" in metrics:
        _, out, _ = c.adb.shell("df", "/data", timeout=20)
        rec["df_avail_kb"] = parse_df(out)
    if "focus" in metrics:
        f = h.current_focus(c)
        rec["focus"] = f"{f.get('package')}/{(f.get('activity') or '').split('.')[-1]}"
    if a.service or "service" in metrics:
        _, out, _ = c.adb.shell("dumpsys", "activity", "services", pkg, timeout=30)
        svcs = services_of(out)
        rec["services"] = [s.split("/")[-1] for s in svcs]
        if a.service:
            rec["service_running"] = any(a.service in s for s in svcs)
    if "battery" in metrics:
        _, out, _ = c.adb.shell("dumpsys", "battery", timeout=15)
        lvl = re.search(r"level: (\d+)", out)
        tmp = re.search(r"temperature: (\d+)", out)
        rec["battery"] = int(lvl.group(1)) if lvl else None
        rec["battery_temp_c"] = int(tmp.group(1)) / 10 if tmp else None
    if "thermal" in metrics:
        _, out, _ = c.adb.shell("dumpsys", "thermalservice", timeout=15)
        st = re.search(r"Thermal Status: (\d)", out)
        rec["thermal_status"] = int(st.group(1)) if st else None
    rec["host"] = h.host_load()
    return rec


def screenshot(c, path):
    code, data, _ = c.adb.cmd("exec-out", "screencap", "-p", binary=True, timeout=60)
    if code == 0 and data.startswith(b"\x89PNG"):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_bytes(data)
        return str(path)
    return None


# ---------------------------------------------------------------- actions through guard

def tap(c, h, spec, no_ui):
    """spec: ("text"|"desc"|"id"|"xy", value). Uses adb_helpers target_point → guard → input tap."""
    kind, value = spec
    ns = argparse.Namespace(**vars(c.a))
    ns.x = ns.y = ns.text = ns.id = ns.desc = None
    ns.index, ns.exact, ns.no_ui, ns.retry, ns.ignore_animations = None, False, no_ui, 4, False
    if kind == "xy":
        ns.x, ns.y = [int(v) for v in value.split(",")]
    else:
        setattr(ns, kind, value)
    saved, c.a = c.a, ns
    try:
        x, y, node, info = h.target_point(c, "tap")
        c.run("input", "tap", x, y)
        c.pause()
    finally:
        c.a = saved
    return {"x": x, "y": y, "element": h.elem_ref(node) if node else None, "element_checked": (info or {}).get("element_checked", True)}


def action_spec(a, prefix):
    for kind in ("text", "desc", "id", "xy"):
        v = getattr(a, f"{prefix}_{kind}", None)
        if v:
            return kind, v
    return None


def screen_texts(c, h, tries=2):
    xml, _ = h.try_dump(c, tries)
    if xml is None:
        return None
    return " ".join(f"{n['text']} {n['desc']}" for n in h.parse_ui(xml))


def wait_text(c, h, text, timeout, stoppable=True):
    deadline = time.time() + timeout
    while True:
        t = screen_texts(c, h, 1)
        if t is not None and text.lower() in t.lower():
            return True
        if time.time() >= deadline:
            return False
        if stoppable and stop_requested():
            raise Stop()
        nap(1.0)


def nap(s):
    time.sleep(max(0.0, s * float(os.environ.get("ANDROID_QA_SLEEP_SCALE") or 1)))


def wait_service(c, pkg, name, timeout):
    deadline = time.time() + timeout
    while True:
        _, out, _ = c.adb.shell("dumpsys", "activity", "services", pkg, timeout=30)
        if any(name in s for s in services_of(out)):
            return True
        if time.time() >= deadline:
            return False
        if stop_requested():
            raise Stop()
        nap(1.0)


# ---------------------------------------------------------------- result checks

def durations_on_screen(text):
    out = []
    for m in DURATION_RX.finditer(text or ""):
        hh, mm, ss = int(m.group(1) or 0), int(m.group(2)), int(m.group(3))
        if ss < 60 and (m.group(1) is None or mm < 60):
            out.append((hh * 3600 + mm * 60 + ss, m.group(0)))
    return out


def media_duration(path):
    """Seconds of a WAV / MP4-family (m4a, mp4, 3gp, aac in mp4) / Ogg (Opus, Vorbis) file, or None."""
    p = Path(path)
    data = p.read_bytes()
    if data[:4] == b"RIFF" and data[8:12] == b"WAVE":
        with wave.open(str(p), "rb") as w:
            return w.getnframes() / float(w.getframerate())
    i = data.find(b"mvhd")
    if i > 4:
        ver = data[i + 4]
        if ver == 1:
            scale, dur = struct.unpack(">IQ", data[i + 24:i + 36])
        else:
            scale, dur = struct.unpack(">II", data[i + 16:i + 24])
        return dur / float(scale) if scale else None
    if data[:4] == b"OggS":
        rate = 48000.0
        v = data.find(b"\x01vorbis")
        if v >= 0:
            rate = float(struct.unpack("<I", data[v + 12:v + 16])[0])
        last = data.rfind(b"OggS")
        gran = struct.unpack("<q", data[last + 6:last + 14])[0]
        return gran / rate if gran > 0 else None
    return None


def check_duration(seconds, expected_s, tolerance):
    allow = max(30.0, expected_s * tolerance)
    return abs(seconds - expected_s) <= allow, round(seconds - expected_s, 1)


def result_file(c, h, glob, tag):
    if not re.match(r"^/[\w./*?-]+$", glob or ""):
        return {"ok": None, "reason": "--result-file: путь на устройстве из букв, цифр и / . _ - * ?"}
    if re.match(r"^/data/(data|user)/", glob):
        return {"ok": None, "reason": "не поддерживается: приватная папка приложения не читается adb pull без root — "
                                      "указать файл в общей папке или проверить длительность на экране (--expect-duration)"}
    line = f"ls -t {glob} 2>/dev/null | head -1"
    c.gate(c.decide(h.guard.check_adb, ["shell", line], c.cfg, c.stand(), c.serial))
    code, out, _ = c.adb.shell_raw(line, timeout=30)
    remote = (out or "").strip().splitlines()[0].strip() if (out or "").strip() else ""
    if not remote:
        return {"ok": False, "reason": f"файл {glob} на устройстве не найден"}
    local = c.out_path(None, f"soak-{tag}-result{Path(remote).suffix}", "raw")
    code, o, e = c.adb.cmd("pull", remote, str(local), timeout=600)
    if code != 0:
        return {"ok": None, "reason": f"adb pull: {(o + e).strip()[:160]}"}
    try:
        secs = media_duration(local)
    except (OSError, wave.Error, struct.error, EOFError):
        secs = None
    if secs is None:
        return {"ok": None, "file": remote, "reason": f"не поддерживается: длительность формата {Path(remote).suffix} не читается"}
    return {"file": remote, "local": str(local), "seconds": round(secs, 1)}


# ---------------------------------------------------------------- soak

def summarize(samples):
    pss = [s["pss_kb"] for s in samples if s.get("pss_kb")]
    res = {"samples": len(samples)}
    if pss:
        ts = [s["t_s"] for s in samples if s.get("pss_kb")]
        res.update({"pss_first_mb": round(pss[0] / 1024, 1), "pss_min_mb": round(min(pss) / 1024, 1),
                    "pss_max_mb": round(max(pss) / 1024, 1), "pss_last_mb": round(pss[-1] / 1024, 1)})
        if len(pss) >= 3 and ts[-1] > ts[0]:
            mt, mp = sum(ts) / len(ts), sum(pss) / len(pss)
            den = sum((t - mt) ** 2 for t in ts)
            slope = sum((t - mt) * (p - mp) for t, p in zip(ts, pss)) / den if den else 0
            res["pss_growth_mb_per_hour"] = round(slope * 3600 / 1024, 1)
    df = [s["df_avail_kb"] for s in samples if s.get("df_avail_kb")]
    if df:
        res["df_min_mb"] = round(min(df) / 1024)
    hosts = [s.get("host") or {} for s in samples]
    emus = [x.get("emulators_running") for x in hosts if x.get("emulators_running") is not None]
    loads = [x.get("load1") for x in hosts if x.get("load1") is not None]
    res["host"] = {"emulators_max": max(emus) if emus else None, "load1_max": max(loads) if loads else None,
                   "cpus": (hosts[0] if hosts else {}).get("cpus")}
    th = [s["thermal_status"] for s in samples if s.get("thermal_status") is not None]
    if th:
        res["thermal_max"] = max(th)
    return res


WATCH_S = 2.0          # --clips-on-crash: how often the app's process is checked between samples


def wait_watch(c, h, pkg, seconds, watch):
    """sleep_or_stop with a light check (--clips-on-crash): the process gone → 'process-died' at once (the crash
    moment must still be in the rolling recording), the ANR dialog → 'anr'. None — the time is up."""
    if not watch:
        sleep_or_stop(seconds)
        return None
    end = time.time() + max(0.0, seconds)
    while True:
        if stop_requested():
            raise Stop()
        left = end - time.time()
        if left <= 0:
            return None
        time.sleep(min(STOP_SLICE_S, left))
        if time.time() < watch["next"]:
            continue
        watch["next"] = time.time() + WATCH_S
        watch["i"] += 1
        pids = h.app_pids(c.adb, pkg)
        if watch["alive"] and not pids:
            return "process-died"
        if pids and watch.get("pid") and pids[0] != watch["pid"]:
            watch["pid"] = pids[0]
            return "process-restarted"
        if pids:
            watch["alive"], watch["pid"] = True, watch.get("pid") or pids[0]
        if watch["i"] % 3 == 0:
            import clip_android
            if clip_android.anr_on_screen(c, pkg):
                if not watch.get("anr"):
                    watch["anr"] = True
                    return "anr"
            else:
                watch["anr"] = False


def save_crash_clip(c, h, a, info, tag, event, t_s):
    import clip_android
    name = f"soak-{tag}-{event}-{max(0, round(t_s / 60))}m"
    what = {"process-died": "процесс приложения завершился", "process-restarted": "процесс перезапущен",
            "anr": "ANR — приложение не отвечает"}.get(event, event)
    res = clip_android.soak_save(c, h, name, a.clips_last, f"{what} на {round(t_s / 60, 1)} мин")
    if res.get("ok"):
        entry = dict(res.pop("entry"), event=event, t_s=t_s)
        info.setdefault("clips", []).append(entry)
    else:
        info.setdefault("clip_errors", []).append({"event": event, "t_s": t_s, "error": res.get("error")})
    return res


def run(c, h):
    a = c.a
    pkg = c.pkg(a.pkg)
    tag = re.sub(r"[^\w.-]+", "-", a.tag or "soak")
    serial = c.serial.replace(":", "_")
    raw = c.out_path(None, f"soak-{tag}-{serial}.jsonl", "raw")
    summary_path = raw.with_suffix(".json")
    shots = []
    events = []
    samples = []
    status, reason, exit_code = "ok", "", None
    start_spec, stop_spec = action_spec(a, "start"), action_spec(a, "stop")
    if a.screen_off_at is not None:  # fail early (before N minutes) if screen control needs a confirmation
        c.gate(c.decide(h.guard.check_adb, ["shell", "wm", "dismiss-keyguard"], c.cfg, c.stand(), c.serial))

    def on_term(*_):
        raise Stop()
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, on_term)
    t0 = time.time()
    info = {"tag": tag, "serial": c.serial, "package": pkg, "minutes_planned": a.minutes, "every_s": a.every,
            "started_at": now(), "start_action": None, "precondition": None, "stop_action": None,
            "file": str(raw), "summary_file": str(summary_path)}
    try:
        shot = screenshot(c, c.out_path(None, f"soak-{tag}-{serial}-before.png", "screenshots"))
        shots += [shot] if shot else []
        if start_spec:
            try:
                info["start_action"] = dict(tap(c, h, start_spec, a.start_no_ui or start_spec[0] == "xy"), spec=list(start_spec))
            except SystemExit as ex:  # guard 2/3/6, ambiguous (2), not found (4): the run did not start
                exit_code = ex.code if isinstance(ex.code, int) else 5
                status = "invalid"
                reason = (f"стартовое нажатие не выполнено (код {exit_code}: 2 — нужно согласие или неоднозначно, "
                          "3 — запрет guard, 4 — элемент не найден, 6 — guard недоступен) — прогон не начат")
                raise Stop()
            nap(1.0)
        pre = {}
        if a.expect_text:
            pre["text"] = wait_text(c, h, a.expect_text, a.expect_timeout)
        if a.service:
            pre["service"] = wait_service(c, pkg, a.service, a.expect_timeout)
        if a.expect_text or a.service:
            info["precondition"] = {"checks": pre, "ok": all(pre.values())}
        shot = screenshot(c, c.out_path(None, f"soak-{tag}-{serial}-start.png", "screenshots"))
        shots += [shot] if shot else []
        if info["precondition"] and not info["precondition"]["ok"]:
            status = "invalid"
            reason = ("предусловие не выполнено после старта: " +
                      ", ".join(f"{k}" for k, v in pre.items() if not v) +
                      (f" (ожидался текст «{a.expect_text}»)" if a.expect_text and not pre.get("text") else "") +
                      (f" (ожидался сервис {a.service})" if a.service and not pre.get("service") else "") +
                      " — прогон недействителен, о приложении ничего не говорит; посмотреть скриншот start")
            raise Stop()
        end = t0 + a.minutes * 60
        watch = None
        if getattr(a, "clips_on_crash", False):
            import clip_android
            keep = max(3, min(10, int((WATCH_S * 2 + 12) // max(2.0, a.clips_segment)) + 2))
            rolling, note = clip_android.soak_start(c, h, a.clips_segment, keep) if c.run_dir else \
                (None, "непрерывная запись не запущена: нужен --run-dir")
            info["clips_on_crash"] = {"recording": bool(rolling), "segment": a.clips_segment, "keep": keep,
                                      **({"note": note} if note else {})}
            if rolling:
                watch = {"next": time.time() + WATCH_S, "i": 0, "alive": bool(h.app_pids(c.adb, pkg)), "pid": None}
        next_shot = t0 + a.screenshots * 60 if a.screenshots else None
        off_at = t0 + a.screen_off_at * 60 if a.screen_off_at is not None else None
        on_at = t0 + a.screen_on_at * 60 if a.screen_on_at is not None else None
        last_pid = None
        with open(raw, "a", encoding="utf-8") as f:
            while True:
                if stop_requested():
                    raise Stop()
                rec = sample(c, h, pkg, a, t0, last_pid)
                samples.append(rec)
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                f.flush()
                n_events = len(events)
                if rec.get("pid") is None and last_pid and (len(samples) < 2 or samples[-2].get("pid")):
                    events.append({"t_s": rec["t_s"], "event": "process-died"})
                elif rec.get("pid") is None and watch and watch.get("died") and not any(e["event"] == "process-died" for e in events):
                    events.append({"t_s": rec["t_s"], "event": "process-died"})
                elif rec.get("pid_changed") or (watch and watch.pop("restarted", False)):
                    events.append({"t_s": rec["t_s"], "event": "process-restarted", "pid": rec["pid"]})
                if watch and watch.pop("anr_now", False):
                    events.append({"t_s": rec["t_s"], "event": "anr"})
                for ev in events[n_events:]:
                    if watch and ev["event"] in ("process-died", "process-restarted", "anr"):
                        clip = save_crash_clip(c, h, a, info, tag, ev["event"], ev["t_s"])
                        if clip.get("ok"):
                            ev["clip"] = clip.get("file")
                        if watch:
                            watch["pid"] = rec.get("pid")
                if a.service and rec.get("service_running") is False and \
                        not (len(samples) > 1 and samples[-2].get("service_running") is False):
                    events.append({"t_s": rec["t_s"], "event": "service-lost", "service": a.service})
                last_pid = rec.get("pid") or last_pid
                lost = [e for e in events if e["event"] in ("process-died", "service-lost")]
                if lost and not a.continue_on_loss:
                    status = "interrupted"
                    reason = f"{lost[0]['event']} на {round(lost[0]['t_s'] / 60, 1)} мин из {a.minutes}"
                    break
                t = time.time()
                if off_at and t >= off_at:
                    c.run("input", "keyevent", str(h.KEYS["SLEEP"]))
                    events.append({"t_s": round(t - t0, 1), "event": "screen-off"})
                    off_at = None
                if on_at and t >= on_at:
                    c.run("input", "keyevent", str(h.KEYS["WAKEUP"]))
                    time.sleep(0.5)
                    c.run("wm", "dismiss-keyguard")
                    events.append({"t_s": round(t - t0, 1), "event": "screen-on"})
                    on_at = None
                if next_shot and t >= next_shot:
                    shot = screenshot(c, c.out_path(None, f"soak-{tag}-{serial}-t{round((t - t0) / 60)}m.png", "screenshots"))
                    shots += [shot] if shot else []
                    next_shot += a.screenshots * 60
                if t >= end:
                    break
                hit = wait_watch(c, h, pkg, max(0.2, min(a.every, end - t)), watch)
                if hit == "process-died":
                    watch["died"] = True
                elif hit == "process-restarted":
                    watch["restarted"] = True
                elif hit == "anr":
                    watch["anr_now"] = True
    except Stop:
        if status == "ok":
            status, reason = "stopped", "остановлено (job stop" + (")" if stop_requested() else " / сигнал)")
    except SystemExit:
        raise
    except Exception as ex:  # noqa: BLE001 — the summary is written in any case
        status, reason = "failed", f"{type(ex).__name__}: {h.mask(str(ex))[:200]}"
    finally:
        if hasattr(signal, "SIGTERM"):  # a repeated stop must not interrupt writing the summary
            signal.signal(signal.SIGTERM, lambda *_: None)
        if (info.get("clips_on_crash") or {}).get("recording"):
            import clip_android
            stopped = clip_android.soak_stop(c, h)
            info["clips_on_crash"]["stopped"] = {k: stopped.get(k) for k in ("ok", "touches", "note", "error") if k in stopped}
        if status in ("ok", "interrupted", "stopped"):
            offs = [e for e in events if e["event"] == "screen-off"]
            if offs and not any(e["event"] == "screen-on" for e in events):  # wake the screen before the stop action
                try:
                    c.run("input", "keyevent", str(h.KEYS["WAKEUP"]))
                    time.sleep(0.5)
                    c.run("wm", "dismiss-keyguard")
                    events.append({"t_s": round(time.time() - t0, 1), "event": "screen-on"})
                except SystemExit:
                    pass
            shot = screenshot(c, c.out_path(None, f"soak-{tag}-{serial}-before-stop.png", "screenshots"))
            shots += [shot] if shot else []
            if stop_spec and status != "stopped":
                try:
                    info["stop_action"] = dict(tap(c, h, stop_spec, a.stop_no_ui or stop_spec[0] == "xy"), spec=list(stop_spec))
                    nap(max(1.0, a.final_wait))
                except SystemExit as ex:
                    info["stop_action"] = {"error": f"не выполнено (код {ex.code})"}
                shot = screenshot(c, c.out_path(None, f"soak-{tag}-{serial}-after-stop.png", "screenshots"))
                shots += [shot] if shot else []
    actual_min = round((time.time() - t0) / 60, 2)
    result = {}
    if status in ("ok", "interrupted") and (a.expect_duration or a.result_file or a.expect_final_text):
        expected = (a.expect_minutes if a.expect_minutes is not None else a.minutes) * 60
        if a.expect_final_text:
            result["final_text"] = wait_text(c, h, a.expect_final_text, 5, stoppable=False)
        if a.expect_duration:
            durs = durations_on_screen(screen_texts(c, h) or "")
            if durs:
                best = min(durs, key=lambda d: abs(d[0] - expected))
                ok, diff = check_duration(best[0], expected, a.tolerance)
                result["screen_duration"] = {"text": best[1], "seconds": best[0], "expected_s": expected, "ok": ok, "diff_s": diff}
            else:
                result["screen_duration"] = {"ok": None, "reason": "длительности вида м:сс на экране нет"}
        if a.result_file:
            rf = result_file(c, h, a.result_file, tag)
            if rf.get("seconds") is not None:
                ok, diff = check_duration(rf["seconds"], expected, a.tolerance)
                rf.update({"expected_s": expected, "ok": ok, "diff_s": diff})
            result["file"] = rf
        bad = [k for k, v in result.items() if (v is False) or (isinstance(v, dict) and v.get("ok") is False)]
        if bad and status == "ok":
            status = "result-mismatch"
            reason = "итог не совпал с ожидаемым: " + ", ".join(bad)
    info.update({"status": status, "valid": status not in ("invalid", "failed"), "reason": reason,
                 "finished_at": now(), "minutes_actual": actual_min, "events": events, "screenshots": shots,
                 "result": result, **summarize(samples)})
    if (info.get("host") or {}).get("emulators_max") and info["host"]["emulators_max"] > 1:
        info["host_note"] = (f"рядом работало эмуляторов: {info['host']['emulators_max']} — временные показатели "
                             "(скорость обработки) искажены; память и стабильность — достоверны")
    summary_path.write_text(json.dumps(info, ensure_ascii=False, indent=1), encoding="utf-8")
    c.log("actions.jsonl", {"soak": tag, "status": status, "minutes": actual_min})
    h.emit(info)
    sys.exit(exit_code if exit_code else (5 if status in ("invalid", "failed") else 0))


# ---------------------------------------------------------------- jobs

def jobs_dir(c):
    if not c.run_dir:
        h_fail("job: нужен --run-dir")
    d = c.run_dir / "raw" / "jobs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def h_fail(msg, code=2):
    sys.stderr.write(f"adb_helpers: {msg}\n")
    sys.exit(code)


def load_job(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def save_job(path, data):
    tmp = Path(str(path) + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(str(tmp), str(path))


def job_view(c, h, j):
    alive = j.get("status") == "running" and h.su.pid_alive(j.get("pid"))
    v = {k: j.get(k) for k in ("id", "status", "serial", "argv", "started_at", "finished_at", "exit_code", "log")}
    if j.get("status") == "running" and not alive:
        v["status"] = "lost"
        v["note"] = "процесс задачи не найден (перезагрузка хоста?) — см. журнал задачи"
    if j.get("argv") and j["argv"][0] == "soak":
        tag = next((j["argv"][i + 1] for i, x in enumerate(j["argv"][:-1]) if x == "--tag"), "soak")
        safe_tag = re.sub(r"[^\w.-]+", "-", tag)
        safe_serial = (j.get("serial") or "").replace(":", "_")
        base = c.run_dir / "raw" / f"soak-{safe_tag}-{safe_serial}"
        summ = load_job(str(base) + ".json")
        if summ and summ.get("finished_at"):
            v["soak"] = {k: summ.get(k) for k in ("status", "reason", "minutes_actual", "pss_max_mb", "pss_growth_mb_per_hour")}
        elif Path(str(base) + ".jsonl").exists():
            lines = Path(str(base) + ".jsonl").read_text(encoding="utf-8").strip().splitlines()
            if lines:
                last = json.loads(lines[-1])
                v["progress"] = {"minutes": round(last.get("t_s", 0) / 60, 1), "pss_mb": round((last.get("pss_kb") or 0) / 1024, 1),
                                 "service_running": last.get("service_running"), "samples": len(lines)}
    return v


def job(c, h):
    a = c.a
    d = jobs_dir(c)
    if a.action == "start":
        argv = list(a.cmdline or [])
        if argv and argv[0] == "--":
            argv = argv[1:]
        if not argv or argv[0] in ("job", "job-run"):
            h_fail("job start … -- <подкоманда adb_helpers.py и её аргументы>")
        jid = re.sub(r"[^\w.-]+", "-", a.name or f"{argv[0]}-{datetime.now().strftime('%H%M%S')}")
        path = d / f"{jid}.json"
        if path.exists() and (load_job(path) or {}).get("status") == "running":
            h_fail(f"задача {jid} уже идёт — другое --name")
        others = [load_job(p) for p in d.glob("*.json")]
        busy = [o["id"] for o in others if o and o.get("status") == "running" and o.get("serial") == c.serial
                and h.su.pid_alive(o.get("pid")) and o.get("argv", [""])[0] == "soak" and argv[0] == "soak"]
        if busy:
            h_fail(f"на {c.serial} уже идёт soak ({', '.join(busy)}): один стенд — одна задача с действиями в интерфейсе")
        log = (c.run_dir / "logs" / f"job-{jid}.log")
        if stop_file(path).exists():   # a stale request of a previous job with this name
            stop_file(path).unlink()
        data = {"id": jid, "argv": argv, "serial": c.serial, "run_dir": str(c.run_dir), "config": c.a.config,
                "confirmed": bool(c.a.confirmed), "status": "running", "started_at": now(), "log": str(log)}
        save_job(path, data)
        proc = h.su.popen_detached([sys.executable, str(HERE / "adb_helpers.py"), "job-run", "--job-file", str(path)], log)
        data["pid"] = proc.pid
        save_job(path, data)
        c.log("actions.jsonl", {"job": jid, "start": argv[:3]})
        h.emit({"ok": True, "job": jid, "pid": proc.pid, "log": str(log), "argv": argv,
                "next": f"job status {jid} — прогресс; job stop {jid} — остановить"})
        return
    if a.action in ("status", "list"):
        items = [load_job(p) for p in sorted(d.glob("*.json"))]
        items = [j for j in items if j and (a.action == "list" or not a.id or j["id"] == a.id)]
        if a.id and not items:
            h_fail(f"нет задачи {a.id}", 4)
        h.emit({"jobs": [job_view(c, h, j) for j in items]})
        return
    if not a.id:
        h_fail(f"job {a.action} <id>")
    path = d / f"{a.id}.json"
    j = load_job(path)
    if not j:
        h_fail(f"нет задачи {a.id}", 4)
    if a.action == "log":
        lines = Path(j["log"]).read_text(encoding="utf-8", errors="replace").splitlines() if Path(j["log"]).exists() else []
        print("\n".join(h.mask(x) for x in lines[-a.lines:]))
        return
    if a.action == "stop":
        if j.get("status") != "running" or not h.su.pid_alive(j.get("pid")):
            h.emit({"ok": True, "job": a.id, "status": j.get("status"), "note": "уже не работает"})
            return
        h.emit(stop_job(c, h, path, j, a.grace))


def stop_file(job_path):
    return Path(job_path).with_suffix(".stop")


def stop_job(c, h, path, j, grace):
    """Stop request file first (soak writes its summary and exits); POSIX — also SIGTERM. Windows (or
    ANDROID_QA_JOB_STOP=file): soak gets up to `grace` seconds to finish by itself, then the process tree is killed
    (taskkill /T /F) and the job is marked `killed` — its summary is not written. Other subcommands — killed at once."""
    stop_file(path).write_text(now(), encoding="utf-8")
    graceful = (j.get("argv") or [""])[0] in GRACEFUL
    file_mode = file_stop_mode()
    wait = (max(5.0, float(grace)) if graceful else 0.0) if file_mode else 60.0
    if not file_mode:
        h.su.kill_pid(j["pid"])
    deadline = time.time() + wait
    while time.time() < deadline and (load_job(path) or {}).get("status") == "running" and h.su.pid_alive(j["pid"]):
        time.sleep(0.5)
    how = "signal" if not file_mode else "stop-file"
    if file_mode and (load_job(path) or {}).get("status") == "running" and h.su.pid_alive(j["pid"]):
        h.su.kill_pid(j["pid"])                      # Windows: taskkill /T /F — the whole tree, no summary
        jj = load_job(path) or j
        jj.update({"status": "killed", "finished_at": now(),
                   "note": (f"не завершилась за {int(wait)} с после запроса остановки — процесс снят, сводка не записана"
                            if graceful else "подкоманда не поддерживает мягкую остановку — процесс снят")})
        save_job(path, jj)
        how = "killed"
    return {"ok": True, "job": j["id"], "stopped": True, "how": how, "view": job_view(c, h, load_job(path) or j)}


def job_run(job_file):
    """Internal: runs the job's subcommand (its stop request file is passed as ANDROID_QA_STOP_FILE), forwards SIGTERM
    to it, records the exit code; status `stopped` if a stop was requested (signal or stop file)."""
    path = Path(job_file)
    j = load_job(path)
    argv = [sys.executable, str(HERE / "adb_helpers.py")] + j["argv"] + ["--serial", j["serial"], "--run-dir", j["run_dir"]]
    if j.get("config"):
        argv += ["--config", j["config"]]
    if j.get("confirmed"):
        argv.append("--confirmed")
    kw = {"start_new_session": True} if os.name != "nt" else {}
    child = subprocess.Popen(argv, stdin=subprocess.DEVNULL, env=dict(os.environ, **{STOP_ENV: str(stop_file(path))}), **kw)
    stopped = {"v": False}

    def term(*_):
        stopped["v"] = True
        try:
            child.send_signal(signal.SIGTERM)
        except OSError:
            pass
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, term)
    code = None
    while code is None:
        try:
            code = child.wait()
        except KeyboardInterrupt:
            term()
    j = load_job(path) or j
    if j.get("status") == "killed":    # job stop has already given up and recorded it
        sys.exit(0)
    stopped["v"] = stopped["v"] or stop_file(path).exists()
    j.update({"status": "stopped" if stopped["v"] else ("done" if code == 0 else "failed"), "exit_code": code,
              "finished_at": now()})
    save_job(path, j)
    journal = Path(j["run_dir"]) / "journal.md"
    if journal.exists():
        try:
            sys.path.insert(0, str(HERE / "shared"))
            import runjournal
            jr = runjournal.need(j["run_dir"])
            jr["log"].append(f"- {runjournal.now()} — задача {j['id']} ({' '.join(j['argv'][:2])}): {j['status']}, код {code}")
            runjournal.write(j["run_dir"], jr)
        except Exception:  # noqa: BLE001 — the journal is a convenience
            pass
    sys.exit(0)
