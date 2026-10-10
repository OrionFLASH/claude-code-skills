#!/usr/bin/env python3
"""Короткие ролики без звука для находок android-qa-audit (references/clips.md). Не отдельный CLI: adb_helpers.py
регистрирует подкоманды (register) и передаёт себя как `h` (dispatch). Сжатие, GIF, постер, лента кадров и запись в
находку — общий модуль scripts/shared/qa_clips.py.

  clip-start --name F-003-font [--seconds 10] [--size 720] [--bit-rate 2000000] [--touches auto|on|off]
      `adb shell screenrecord --time-limit N --size WxH --bit-rate B /sdcard/qa-clip-<name>.mp4` фоновым процессом
      хоста; состояние — <RUN_DIR>/raw/clip-<serial>.json (PID, пути, прежние show_touches / pointer_location, время).
      Отказ (код 2), если на стенде уже идёт запись; осиротевшее состояние прошлой записи сначала убирается
      (настройки возвращаются). Касания: auto — только на эмуляторе прогона, на устройстве — только --touches on.
  clip-stop [--finding F-003 --caption "…" --kind error|ok|note|after] [--mark "x,y,w,h|подпись|error"]… [--force]
      SIGINT процессу screenrecord на устройстве (дописывает moov), pull в recordings/, удаление с устройства,
      возврат show_touches (в finally — и при ошибке, и при прерывании), проверка «чёрного экрана», метки и подпись,
      сжатие qa_clips.finalize → clips/<name>.mp4 (+ .gif, -poster.png, -sheet.png), запись в находку.
  clip-stop --restore-only — остановить запись, если идёт, и вернуть настройки без ролика.
  clip --name N [--seconds 8] [… как clip-start и clip-stop] -- <шаг> [--then <шаг>]…
      старт → шаги (подкоманды adb_helpers.py теми же функциями, через guard; `wait S` — пауза) → ~1 с → стоп.
      Шаг с запретом / подтверждением / без guard (коды 3 / 2 / 6) не выполняется, цепочка обрывается, ролик в
      находку не пишется. --dry-run — только разобрать шаги.
  clip-rolling start [--segment 8] [--keep 3] | save --name N [--finding F-007 --last 10] | stop | status
      непрерывная запись сегментами фоновым процессом хоста (clip-rolling-run), последние --keep сегментов —
      в <RUN_DIR>/raw/rolling-<serial>/; save — последние ≈ --last секунд (ffmpeg concat; без ffmpeg — последний
      сегмент) как обычный ролик. soak --clips-on-crash вызывает save при падении / ANR.
Коды: 0 готово, 2 неверный вызов / нужно подтверждение / уже идёт, 3 запрет guard, 4 не поддерживается на стенде
(API < 19, нет screenrecord, нет кодека), 5 ошибка (в т.ч. «чёрный экран» без --force), 6 guard недоступен.
"""
import contextlib
import io
import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "shared"))
sys.path.insert(0, str(HERE))
import qa_clips  # noqa: E402

KINDS = qa_clips.KINDS                                  # error | ok | note | after
MARK_KINDS = ("error", "question", "note", "ok")
COLORS = {"error": "0xFFD60A", "question": "0xBF5AF2", "note": "0xBF5AF2", "ok": "0x30D158", "after": "0x30D158"}
BLACK_LIMIT = 0.8
BLACK_WARN = ("чёрный экран: защищённое окно (FLAG_SECURE) или пустой кадр — ролик невозможен/бесполезен; "
              "в находку не записан (--force — записать всё равно)")
UNSUPPORTED_RX = re.compile(r"codec|MediaCodec|encoder|not supported|unable to|Unable to|ERROR|Errno|failed", re.I)
OFFLINE_RX = re.compile(r"device (offline|not found|'[^']*' not found)|no devices|closed|error: device", re.I)
# Steps of `clip`: actions in the interface and configuration (each through guard as a separate command).
STEPS = {"tap", "long-press", "swipe", "scroll", "text", "key", "launch", "stop", "deeplink", "rotate", "font-scale",
         "dark-mode", "animations", "network", "shade", "kill-bg", "screenshot", "dump-ui", "find", "current",
         "trim-memory", "locale", "battery", "doze", "standby", "density", "timezone", "grant", "revoke"}
GUARD_CODES = (2, 3, 6)


class ClipError(Exception):
    def __init__(self, message, code=5, extra=None):
        super().__init__(message)
        self.code = code
        self.extra = extra or {}


class Interrupted(Exception):
    pass


def now():
    return datetime.now().isoformat(timespec="seconds")


def safe_name(value, default="clip"):
    v = re.sub(r"[^A-Za-z0-9_.-]+", "-", value or "").strip("-.")[:60]
    return v or default


def serial_tag(serial):
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", serial or "device")


def load_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def save_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".%d.tmp" % os.getpid())
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(str(tmp), str(path))


def need_run_dir(c):
    if not c.run_dir:
        raise ClipError("ролики пишутся только в папку прогона: нужен --run-dir (или QA_RUN_DIR для обёртки qa)", 2)
    c.run_dir.mkdir(parents=True, exist_ok=True)
    try:
        import gitignore_helper
        gitignore_helper.ensure_run_ignore(c.run_dir)
    except OSError:
        pass


def state_path(c):
    return c.run_dir / "raw" / f"clip-{serial_tag(c.serial)}.json"


def rolling_path(c):
    return c.run_dir / "raw" / f"rolling-{serial_tag(c.serial)}.json"


def rolling_dir(c):
    return c.run_dir / "raw" / f"rolling-{serial_tag(c.serial)}"


def clips_cfg(cfg):
    """Only the `clips:` section: qa_clips.settings() takes a dict without `clips` as the section itself, and the
    top level of run-config has `mode: dry-run` (it must not be read as clips.mode)."""
    sec = (cfg or {}).get("clips") if isinstance(cfg, dict) else None
    return {"clips": sec if isinstance(sec, dict) else {}}


def settings(c):
    return qa_clips.settings(clips_cfg(c.cfg))


@contextlib.contextmanager
def term_as_interrupt():
    """SIGTERM (job stop, kill) → Interrupted, so that `finally` returns the device settings."""
    if not hasattr(signal, "SIGTERM"):
        yield
        return

    def on_term(*_):
        raise Interrupted()
    try:
        old = signal.signal(signal.SIGTERM, on_term)
    except ValueError:      # not the main thread
        yield
        return
    try:
        yield
    finally:
        signal.signal(signal.SIGTERM, old)


# ---------------------------------------------------------------- device helpers

def check_support(c):
    """API ≥ 19 and /system/bin/screenrecord — otherwise «не поддерживается» (4)."""
    api = c.api()
    if api and api < 19:
        raise ClipError(f"не поддерживается: screenrecord есть с Android 4.4 (API 19), на стенде API {api} — "
                        "вместо ролика скриншоты по шагам (screenshot до и после)", 4)
    _, out, _ = c.adb.shell("which", "screenrecord", timeout=10)
    if "screenrecord" in out:
        return
    _, out, _ = c.adb.shell("ls", "/system/bin/screenrecord", timeout=10)
    if "screenrecord" in out and "No such" not in out:
        return
    raise ClipError("не поддерживается: на стенде нет /system/bin/screenrecord (урезанная прошивка или Android TV) — "
                    "вместо ролика скриншоты по шагам", 4)


def record_size(c, h, short):
    """Video size WxH for screenrecord: the current screen (rotation included, display_info) scaled so that the
    short side is `short` px (never upscaled), both sides multiples of 16 (some encoders need it)."""
    info = h.display_info(c)
    size = info.get("size")
    if not size:
        return None, info
    w, hh = size
    k = min(1.0, float(short) / min(w, hh)) if short else 1.0
    return (max(16, int(w * k) // 16 * 16), max(16, int(hh * k) // 16 * 16)), info


def read_setting(c, key):
    _, out, _ = c.adb.shell("settings", "get", "system", key, timeout=10)
    return (out or "").strip() or "null"


def touches_plan(c, mode):
    mode = (mode or "auto").lower()
    stand = c.stand()
    if mode == "on":
        return True, f"--touches on ({stand})"
    if mode == "off":
        return False, "касания не показываются (--touches off)"
    if stand == "own-emulator":
        return True, "auto: эмулятор прогона — касания показываются"
    return False, ("auto: " + ("реальное устройство" if stand == "real" else "эмулятор не этого прогона") +
                   " — касания не показываются (--touches on — только явно)")


def enable_touches(c, st, path):
    """show_touches 1 (через guard). The previous values are saved to the state file BEFORE anything else can fail."""
    t = st["touches"]
    t["show_touches_before"] = read_setting(c, "show_touches")
    t["pointer_location_before"] = read_setting(c, "pointer_location")
    if t["show_touches_before"] == "1":
        t["note"] = "show_touches уже был включён — не меняется"
        return
    c.run("settings", "put", "system", "show_touches", "1")     # guard: exit 2/3/6 here means nothing was changed
    t["changed"] = True
    save_json(path, st)


def restore_touches(c, h, st):
    """Return show_touches to its value before the recording. Guard decides as for any change; a confirmation
    given when it was switched on covers switching it back. Fail closed: guard unavailable → not restored (the
    state stays: clip-stop --restore-only / clip-rolling stop / the next start / cleanup repeat it)."""
    t = (st or {}).get("touches") or {}
    if not t.get("changed"):
        return {"changed": False}
    if t.get("restored"):
        return {"changed": True, "restored": True}
    before = t.get("show_touches_before")
    value = before if before in ("0", "1") else "null"
    # «null» — the setting did not exist before: delete it again (the system default is «off»)
    args = ["settings", "put", "system", "show_touches", value] if value != "null" else ["settings", "delete", "system", "show_touches"]
    try:
        d = c.decide(h.guard.check_adb, ["shell", *args], c.cfg, c.stand(), c.serial)
    except SystemExit:
        return {"changed": True, "restored": False,
                "reason": "guard недоступен — после исправления конфига: clip-stop --restore-only"}
    if d["decision"] == h.guard.DENY:
        c.log("blocked.jsonl", {"rule": d.get("rule"), "reason": d.get("reason"), "target": d.get("target")})
        return {"changed": True, "restored": False, "reason": f"запрет guard: {d.get('reason')}"}
    if d["decision"] == h.guard.CONFIRM and not (st.get("confirmed") or getattr(c.a, "confirmed", False)):
        return {"changed": True, "restored": False, "reason": "нужно подтверждение — clip-stop --restore-only --confirmed"}
    code, out, err = c.adb.shell(*args, timeout=15)
    c.log("actions.jsonl", {"adb": "shell " + " ".join(args), "code": code, "restore": "show_touches"})
    cur = read_setting(c, "show_touches")
    ok = code == 0 and (cur == value or (value in ("0", "null") and cur in ("0", "null")))
    t["restored"] = ok
    res = {"changed": True, "restored": ok, "value": value}
    if not ok:
        res["reason"] = "adb: " + ((out + err).strip()[:160] or f"значение {cur!r} вместо {value!r} (нет связи?)")
    return res


def finish_state(path, st, touches):
    """Remove the state file when nothing is left to restore; otherwise keep it with pending_restore."""
    if not (touches or {}).get("changed") or (touches or {}).get("restored"):
        Path(path).unlink(missing_ok=True)
    else:
        st["pending_restore"] = True
        st["recording"] = False
        save_json(path, st)


def device_pids(c, remote):
    """PIDs of screenrecord writing `remote`: toybox `ps -A -o PID,ARGS` (exact file), else `pidof screenrecord`,
    else old toolbox `ps` (NAME). A `sh -c …` parent with the same text is not taken (first word must be screenrecord)."""
    code, out, _ = c.adb.shell("ps", "-A", "-o", "PID,ARGS", timeout=15)
    rows = [ln.strip().split(None, 1) for ln in (out or "").splitlines() if ln.strip()]
    if code == 0 and rows and rows[0][0] == "PID" and len(rows[0]) > 1 and rows[0][1].startswith("ARGS"):
        return [r[0] for r in rows[1:] if len(r) > 1 and r[0].isdigit() and r[1].split()[0].endswith("screenrecord")
                and remote in r[1]], "ps ARGS"
    _, out, _ = c.adb.shell("pidof", "screenrecord", timeout=10)
    pids = [p for p in (out or "").split() if p.isdigit()]
    if pids:
        return pids, "pidof"
    _, out, _ = c.adb.shell("ps", timeout=15)
    rows = [ln.split() for ln in (out or "").splitlines() if ln.strip()]
    if rows and "PID" in rows[0]:
        i = rows[0].index("PID")
        return [r[i] for r in rows[1:] if len(r) > i and r[i].isdigit() and r[-1].endswith("screenrecord")], "ps"
    return [], "нет"


def sigint(c, remote):
    """SIGINT to the screenrecord of `remote` (guard: `kill -2 <pid>` — SIGINT записи скила). Returns the PIDs."""
    pids, how = device_pids(c, remote)
    if pids:
        c.run("kill", "-2", *pids[:4])
    return pids, how


def remote_size(c, remote):
    code, out, _ = c.adb.shell("stat", "-c", "%s", remote, timeout=10)
    v = (out or "").strip().splitlines()[-1].strip() if (out or "").strip() else ""
    return int(v) if code == 0 and v.isdigit() else None


def wait_stable(c, remote, timeout=6.0):
    """Wait until the remote file stops growing (moov written) — some devices end the adb session a bit early."""
    last, end = None, time.time() + timeout
    while time.time() < end:
        cur = remote_size(c, remote)
        if cur is None:
            return None
        if cur and cur == last:
            return cur
        last = cur
        time.sleep(0.4)
    return last


def host_alive(h, pid, proc=None):
    if proc is not None:
        return proc.poll() is None
    return bool(pid) and h.su.pid_alive(pid)


def finalized(path):
    try:
        data = Path(path).read_bytes()
    except OSError:
        return False
    return len(data) > 32 and b"moov" in data


def log_tail(path, offset=0, limit=600):
    try:
        with open(path, "rb") as f:
            f.seek(offset)
            return f.read().decode("utf-8", "replace").strip()[-limit:]
    except OSError:
        return ""


def screenrecord_args(remote, seconds, size, bit_rate):
    return (["screenrecord", "--time-limit", str(int(seconds))] + (["--size", f"{size[0]}x{size[1]}"] if size else [])
            + ["--bit-rate", str(int(bit_rate)), remote])


def launch_recorder(c, h, args, log, quiet=False):
    """Guard check of the shell line, then `adb shell screenrecord …` as a background host process."""
    c.gate(c.decide(h.guard.check_adb, ["shell", *args], c.cfg, c.stand(), c.serial))
    proc = h.su.popen_detached(c.adb.base() + ["shell", *args], log)
    if not quiet:
        c.log("actions.jsonl", {"adb": "shell " + " ".join(args), "background_pid": proc.pid})
    return proc


def classify_failure(rc, tail):
    if OFFLINE_RX.search(tail or ""):
        return ClipError(f"нет связи с устройством: {tail[-200:]}", 5)
    if UNSUPPORTED_RX.search(tail or ""):
        return ClipError("не поддерживается: screenrecord не запустился на этом стенде — " + (tail[-240:] or f"код {rc}") +
                         ". Эмулятор без кодека (headless со swiftshader, часть образов arm64 API ≤ 30): "
                         "avd_manager.py start … --gpu host или образ новее; adb_helpers.py clip соберёт ролик из "
                         "скриншотов (--fallback auto); на устройстве — меньше --size / --bit-rate", 4)
    return ClipError(f"screenrecord завершился сразу (код {rc}): {tail[-240:] or 'без вывода'}", 5)


def wait_started(c, proc, remote, log, offset, timeout=4.0):
    """Until the device shows our screenrecord (or the host process dies — ClipError with the reason)."""
    end, seen = time.time() + timeout, False
    while time.time() < end:
        rc = proc.poll()
        if rc is not None:
            tail = log_tail(log, offset)
            if rc == 0 and not tail:
                return True
            raise classify_failure(rc, tail)
        if device_pids(c, remote)[0]:
            seen = True
            break
        time.sleep(0.15)
    grace = time.time() + 0.6                      # codec errors come right after the start
    while time.time() < grace:
        rc = proc.poll()
        if rc is not None and rc != 0:
            raise classify_failure(rc, log_tail(log, offset))
        time.sleep(0.1)
    return seen


# ---------------------------------------------------------------- single clip: start / stop

def recorder_alive(h, st, proc=None):
    if not st or not st.get("host_pid"):
        return False
    if time.time() - float(st.get("started_ts") or 0) > float(st.get("seconds") or 180) + 120:
        return False                                   # the time limit is long over: a reused PID, not ours
    return host_alive(h, st["host_pid"], proc)


def recover_clip(c, h, st):
    """Stop a recording left by an interrupted run (if the device still records), delete the temp file, return the
    settings. Used by clip-stop --restore-only, the next clip-start and avd_manager.py cleanup."""
    out = {"name": st.get("name"), "started_at": st.get("started_at")}
    try:
        pids, _ = sigint(c, st.get("remote") or "")
        if pids:
            out["stopped_recorder"] = pids
            time.sleep(1.0)
        if recorder_alive(h, st):
            h.su.kill_pid(st["host_pid"])
        if st.get("remote"):
            c.run("rm", "-f", st["remote"])
    except SystemExit as ex:
        out["cleanup_error"] = f"код {ex.code}"
    except Exception as ex:  # noqa: BLE001 — the settings are returned in any case
        out["cleanup_error"] = f"{type(ex).__name__}: {ex}"
    out["touches"] = restore_touches(c, h, st)
    finish_state(state_path(c), st, out["touches"])
    return out


def start_recording(c, h, name, seconds, short, bit_rate, touches_mode):
    """→ (state, Popen). Raises ClipError / SystemExit (guard); on any failure the settings are returned."""
    need_run_dir(c)
    path = state_path(c)
    notes = []
    old = load_json(path)
    if old:
        if old.get("recording", True) and recorder_alive(h, old):
            raise ClipError(f"на {c.serial} уже идёт запись «{old.get('name')}» (с {old.get('started_at')}) — "
                            "сначала clip-stop", 2)
        rec = recover_clip(c, h, old)
        notes.append(f"осталось состояние прерванной записи «{old.get('name')}» — убрано, show_touches: "
                     f"{'возвращён' if rec['touches'].get('restored') else 'не менялся' if not rec['touches'].get('changed') else 'НЕ возвращён'}")
    rs = load_json(rolling_path(c))
    if rs and rolling_alive(h, rs):
        raise ClipError("на этом стенде идёт непрерывная запись (clip-rolling) — clip-rolling save / stop", 2)
    check_support(c)
    remote = f"/sdcard/qa-clip-{name}.mp4"
    size, info = record_size(c, h, short)
    want, why = touches_plan(c, touches_mode)
    log = c.run_dir / "logs" / f"clip-{serial_tag(c.serial)}.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    st = {"version": 1, "serial": c.serial, "name": name, "remote": remote, "seconds": seconds,
          "size": list(size) if size else None, "screen": info.get("size"), "rotation": info.get("rotation"),
          "bit_rate": bit_rate, "stand": c.stand(), "confirmed": bool(getattr(c.a, "confirmed", False)),
          "started_at": now(), "started_ts": time.time(), "recording": True, "host_pid": None, "log": str(log),
          "touches": {"wanted": want, "why": why, "changed": False}}
    proc = None
    try:
        save_json(path, st)
        if want:
            enable_touches(c, st, path)
        offset = log.stat().st_size if log.exists() else 0
        proc = launch_recorder(c, h, screenrecord_args(remote, seconds, size, bit_rate), log)
        st["host_pid"] = proc.pid
        st["started_ts"] = time.time()
        save_json(path, st)
        st["confirmed_started"] = wait_started(c, proc, remote, log, offset)
        save_json(path, st)
    except BaseException:
        if proc is not None:
            try:
                if proc.poll() is None:
                    sigint(c, remote)
                    time.sleep(0.5)
                    h.su.kill_pid(proc.pid)
                c.run("rm", "-f", remote)             # an empty file stays after «Encoder failed»
            except BaseException:  # noqa: BLE001 — the settings are returned in any case
                pass
        st["touches"] = st.get("touches") or {}
        res = restore_touches(c, h, st)
        finish_state(path, st, res)
        raise
    st["notes"] = notes
    return st, proc


def stop_recorder(c, h, st, proc=None, timeout=15.0):
    info = {"signal": None, "wall_s": round(min(time.time() - float(st.get("started_ts") or time.time()),
                                                float(st.get("seconds") or 180)), 2)}
    pids, how = sigint(c, st["remote"])
    if pids:
        info.update(signal="SIGINT", pids=pids, how=how)
    end = time.time() + timeout
    while time.time() < end and host_alive(h, st.get("host_pid"), proc):
        time.sleep(0.2)
    if host_alive(h, st.get("host_pid"), proc):          # the device did not react: once more, then the host side
        left, _ = sigint(c, st["remote"])
        time.sleep(2.0)
        if host_alive(h, st.get("host_pid"), proc):
            h.su.kill_pid(st.get("host_pid"))
            info["host_killed"] = True
            info["left_pids"] = left
    info["remote_bytes"] = wait_stable(c, st["remote"])
    return info


def stop_and_pull(c, h, st, proc=None):
    """SIGINT → wait → pull → rm. (raw Path, info). ClipError if nothing usable came back."""
    info = stop_recorder(c, h, st, proc)
    local = c.out_path(None, f"{st['name']}-{h.ts()}.mp4", "recordings")
    code, out, err = c.adb_cmd("pull", st["remote"], str(local), timeout=180)
    try:
        c.run("rm", "-f", st["remote"])
    except SystemExit:
        info["rm"] = "не удалён (guard)"
    if code != 0 or not local.is_file() or local.stat().st_size == 0:
        local.unlink(missing_ok=True)
        raise ClipError(f"adb pull {st['remote']}: {(out + err).strip()[:200] or 'файла нет'} — запись не сохранилась "
                        "(устройство отключилось или screenrecord не стартовал)", 5)
    if not finalized(local):
        raise ClipError(f"ролик не финализирован (нет moov): {local.name} — screenrecord остановлен без SIGINT "
                        "или связь оборвалась; повторить запись", 5, {"raw": str(local)})
    return local, info


# ---------------------------------------------------------------- marks, caption, finalize

def resolve_marks(c, h, specs):
    """--mark 'x,y,w,h|подпись|вид' (pixels of the screen, as screenshots) or text=/desc=/id= (the element in a fresh
    tree at the end of the recording). Kind: error | question | note | ok."""
    import annotate_android as an
    marks, need_tree = [], False
    for spec in specs or []:
        parts = [p.strip() for p in str(spec).split("|")]
        kind = (parts[2] if len(parts) > 2 and parts[2] else "error").lower()
        if kind not in MARK_KINDS:
            raise ClipError(f"вид метки {kind!r}: error | question | note | ok", 2)
        try:
            m = an.parse_mark("|".join(parts[:2] + ["note" if kind == "ok" else kind]))
        except an.AnnotateError as ex:
            raise ClipError(f"--mark: {ex}", 2)
        m["kind"] = kind
        if m["avoid"]:
            continue
        need_tree = need_tree or bool(m["target"])
        marks.append(m)
    if need_tree:
        xml, err = h.try_dump(c, 3)
        if xml is None:
            raise ClipError(f"метка text=/id=/desc=: дерево не снято ({err}) — задать x,y,w,h", 2)
        nodes = h.parse_ui(xml)
        for m in marks:
            if m["target"]:
                m["box"] = an.find_box(nodes, *m["target"])
                if m["box"] is None:
                    raise ClipError(f"на экране нет элемента {m['target'][0]}=«{m['target'][1]}»", 4)
    if len(marks) > 3:
        raise ClipError("меток больше 3 — ролик про одно место; разбить", 2)
    return marks


def check_mark_syntax(specs):
    """Before the recording is stopped: a bad --mark must not cost the clip."""
    import annotate_android as an
    for spec in specs or []:
        parts = [p.strip() for p in str(spec).split("|")]
        kind = (parts[2] if len(parts) > 2 and parts[2] else "error").lower()
        if kind not in MARK_KINDS:
            raise ClipError(f"вид метки {kind!r}: error | question | note | ok", 2)
        try:
            an.parse_mark("|".join(parts[:2] + ["note" if kind == "ok" else kind]))
        except an.AnnotateError as ex:
            raise ClipError(f"--mark: {ex}", 2)
    if len(specs or []) > 3:
        raise ClipError("меток больше 3 — ролик про одно место; разбить", 2)


def plaque_lines(caption, marks, kind):
    lines = [{"text": caption.strip()[:90], "kind": "ok" if kind in ("ok", "after") else ("note" if kind == "note" else "error")}] \
        if caption and caption.strip() else []
    for m in marks:
        if m.get("label") and len(lines) < 3:
            lines.append({"text": m["label"][:90], "kind": m["kind"]})
    return lines


def render_plaque(lines, width, out):
    """PNG caption plaque with a transparent background (scripts/node/plaque.js, Chromium via Playwright — the same
    mechanism as annotate.js) for ffmpeg builds without drawtext (no freetype)."""
    import annotate_android as an
    try:
        node, modules = an.node_cmd()
    except an.AnnotateError as ex:
        return {"ok": False, "warning": str(ex)}
    spec = out.with_suffix(".json")
    spec.write_text(json.dumps({"out": str(out.resolve()), "width": int(width), "lines": lines}, ensure_ascii=False),
                    encoding="utf-8")
    try:
        p = subprocess.run([node, str(an.NODE_DIR / "plaque.js"), "--spec", str(spec.resolve())], capture_output=True,
                           text=True, encoding="utf-8", errors="replace", env=dict(os.environ, NODE_PATH=str(modules)),
                           cwd=str(an.NODE_DIR), timeout=120)
    except (OSError, subprocess.TimeoutExpired) as ex:
        return {"ok": False, "warning": f"plaque.js не запустился: {ex}"}
    ok = p.returncode == 0 and out.is_file() and out.stat().st_size > 0
    return {"ok": ok, "file": str(out), "warning": None if ok else f"plaque.js: {(p.stderr or p.stdout).strip()[-200:]}"}


def decorate(raw, work, marks, caption, kind, screen, caps):
    """Boxes (drawbox, palette #FFD60A / #30D158 / #BF5AF2, thin, with a dark under-stroke) and the caption on the raw
    recording, in its own pixels (marks come in screen pixels). Caption: drawtext if ffmpeg has it; otherwise a PNG
    plaque from Chromium + overlay; otherwise none (the caption stays in the finding). → {ok, file, how, warning}"""
    res = {"ok": False, "file": None, "how": None, "caption_drawn": False, "warning": None}
    ff = caps.get("ffmpeg")
    lines = plaque_lines(caption, marks, kind)
    if not ff:
        res["warning"] = "без ffmpeg метки и подпись на ролик не наносятся (подпись — в записи находки)"
        return res
    pr = qa_clips.probe(raw)
    vw, vh = pr.get("width"), pr.get("height")
    if not vw or not vh:
        res["warning"] = "размер ролика не определён (нет ffprobe?) — метки не нанесены"
        return res
    sw, sh = (screen or [vw, vh])[:2]
    if (sw > sh) != (vw > vh):
        sw, sh = sh, sw
    kx, ky = vw / float(sw), vh / float(sh)
    t = max(2, int(round(vw / 360.0)))
    chain = []
    for m in marks:
        x, y, w, hh = m["box"]
        X, Y = max(0, int(round(x * kx))), max(0, int(round(y * ky)))
        W, H = max(4, min(vw - X, int(round(w * kx)))), max(4, min(vh - Y, int(round(hh * ky))))
        chain.append(f"drawbox=x={X}:y={Y}:w={W}:h={H}:color=black@0.55:t={t + 2}")
        chain.append(f"drawbox=x={X}:y={Y}:w={W}:h={H}:color={COLORS.get(m['kind'], COLORS['error'])}@0.95:t={t}")
    margin = int(vh * 0.06)
    inputs, overlay = ["-i", str(Path(raw).resolve())], False          # ffmpeg runs in `work` (caption.txt)
    if lines and caps.get("drawtext"):
        (work / "caption.txt").write_text("\n".join(x["text"] for x in lines), encoding="utf-8")
        fs = max(14, vh // 42)
        chain.append(f"drawtext=textfile=caption.txt:expansion=none:fontcolor=white:fontsize={fs}:line_spacing={fs // 4}:"
                     f"x=(w-text_w)/2:y=h-text_h-{margin}:box=1:boxcolor=black@0.6:boxborderw={max(4, fs // 2)}")
        res["how"] = "drawtext"
    elif lines:
        pl = render_plaque(lines, int(vw * 0.9), work / "plaque.png")
        if pl["ok"]:
            inputs += ["-i", str(Path(pl["file"]).resolve())]
            overlay = True
            res["how"] = "chromium"
        else:
            why = "нет Node.js / Playwright (annotate_android.py check)" if "не поддерживается" in (pl.get("warning") or "") \
                else (pl.get("warning") or "?")[:120]
            res["warning"] = (f"подпись на ролике не нарисована (в ffmpeg нет drawtext, Chromium: {why}) — "
                              "подпись только в записи находки")
    if not chain and not overlay:
        return res
    enc = (["-c:v", "libx264", "-preset", "ultrafast", "-crf", "16", "-pix_fmt", "yuv420p"] if caps.get("libx264")
           else ["-c:v", "mpeg4", "-q:v", "2"])
    out = (work / "decorated.mp4").resolve()

    def run(filters, with_overlay):
        if with_overlay:
            fc = f"[0:v]{','.join(filters) or 'null'}[b];[b][1:v]overlay=x=(main_w-overlay_w)/2:y=main_h-overlay_h-{margin}[v]"
            args = inputs + ["-filter_complex", fc, "-map", "[v]"]
        else:
            args = inputs[:2] + ["-vf", ",".join(filters)]
        cmd = [ff, "-y", "-hide_banner", "-loglevel", "error"] + args + ["-an"] + enc + [str(out)]
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=300, cwd=str(work))
        except (OSError, subprocess.TimeoutExpired) as ex:
            return False, str(ex)
        return p.returncode == 0 and out.is_file() and out.stat().st_size > 0, (p.stderr or "")[-300:]
    ok, err = run(chain, overlay)
    if not ok and res["how"] == "drawtext":           # drawtext without fonts (no fontconfig): boxes only
        ok, err = run(chain[:-1], False) if chain[:-1] else (False, err)
        res["how"] = None
        res["warning"] = f"drawtext не сработал ({err.strip()[-120:]}) — подпись только в записи находки"
    if not ok:
        res["warning"] = (res["warning"] or "") + f" ffmpeg (метки): {err.strip()[-160:]}"
        return res
    res.update(ok=True, file=str(out), caption_drawn=res["how"] in ("drawtext", "chromium"))
    return res


def black_ratio(src, caps, samples=8):
    """Share of almost black frames (0..1) among ~`samples` evenly taken frames; None — not measurable.
    Own variant of qa_clips.black_ratio: that one counts the matches in the last 600 characters of ffmpeg's stderr,
    so a fully black clip comes out as ≈ 0.5 (core issue, see the report); here the whole stderr is read and the
    number of sampled frames is taken from ffmpeg's own counter."""
    ff = caps.get("ffmpeg")
    if not ff:
        return None
    secs = qa_clips.probe(src).get("seconds") or 3.0
    try:
        r = subprocess.run([ff, "-hide_banner", "-nostats", "-i", str(src), "-vf",
                            "fps=%.3f,blackframe=amount=98:threshold=32" % max(0.3, samples / secs), "-an", "-f", "null", "-"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if r.returncode != 0:
        return None
    black = len(re.findall(r"blackframe\S* @ [^\]]*\] frame:\d+ pblack:", r.stderr))
    total = max(1, int(round(max(0.3, samples / secs) * secs)))
    return round(min(1.0, black / float(total)), 2)


def frame_count(src):
    fp = qa_clips.find_ffprobe()
    if not fp:
        return None
    try:
        r = subprocess.run([fp, "-v", "error", "-count_packets", "-select_streams", "v:0", "-show_entries",
                            "stream=nb_read_packets", "-of", "csv=p=0", str(src)], capture_output=True, text=True, timeout=60)
        v = (r.stdout or "").strip().splitlines()[0].strip().rstrip(",") if (r.stdout or "").strip() else ""
        return int(v) if v.isdigit() else None
    except (OSError, subprocess.TimeoutExpired, IndexError):
        return None


def pad_to(src, dst, seconds, caps):
    """screenrecord writes a frame only when the screen changes: a static tail («нажатие ничего не меняет») or a
    whole static segment (one frame, duration 0) is missing from the timeline. Re-time the video at a constant
    30 frames/s (only the first video stream: screenrecord also writes data streams) and append the last frame as
    a still for the missing wall time. True on success."""
    ff = caps["ffmpeg"]
    src, dst = Path(src).resolve(), Path(dst).resolve()
    need = max(0.0, float(seconds) - (qa_clips.probe(src).get("seconds") or 0.0))
    enc = (["-c:v", "libx264", "-preset", "ultrafast", "-crf", "16"] if caps.get("libx264") else ["-c:v", "mpeg4", "-q:v", "2"])
    norm = "fps=30,scale=trunc(iw/2)*2:trunc(ih/2)*2,setsar=1,format=yuv420p"

    def run(args):
        try:
            r = subprocess.run([ff, "-y", "-hide_banner", "-loglevel", "error"] + args, capture_output=True, text=True,
                               timeout=300)
        except (OSError, subprocess.TimeoutExpired):
            return False
        return r.returncode == 0
    if need < 0.1:
        ok = run(["-i", str(src), "-map", "0:v:0", "-vf", norm, "-an"] + enc + [str(dst)])
        return ok and dst.is_file() and dst.stat().st_size > 0
    last = dst.with_name(dst.stem + "-last.png")
    n = frame_count(src)
    grab = (["-vf", "select=eq(n\\,%d)" % (n - 1), "-frames:v", "1"] if n else ["-update", "1"])
    if not run(["-i", str(src), "-map", "0:v:0"] + grab + [str(last)]) or not last.is_file():
        return False
    fc = (f"[0:v:0]{norm}[a];[1:v]{norm},trim=duration={need:.2f}[b];[a][b]concat=n=2:v=1:a=0[v]")
    ok = run(["-i", str(src), "-loop", "1", "-framerate", "30", "-i", str(last), "-filter_complex", fc, "-map", "[v]",
              "-an"] + enc + [str(dst)])
    last.unlink(missing_ok=True)
    return ok and dst.is_file() and dst.stat().st_size > 0


def unique_name(run, name):
    d, n, i = Path(run) / "clips", name, 2
    while any((d / f"{n}{ext}").exists() for ext in qa_clips.VIDEO_EXT + (".gif",)):
        n, i = f"{name}-{i}", i + 1
    return n


def finalize_clip(c, h, raw, name, caption, kind, mark_specs, steps, finding, force, screen, start=0.0,
                  max_seconds=None, extra=None, frames=None, caps=None, wall=None):
    """Static tail → black-screen check → marks/caption → qa_clips.finalize (budget, GIF, poster, frame sheet) →
    finding. Returns the result dict; ok=False with code when the clip must not go to the finding."""
    caps = caps or qa_clips.capabilities()
    s = settings(c)
    raw = Path(raw)
    res = {"ok": False, "raw": str(raw)}
    work = Path(tempfile.mkdtemp(prefix="qaclip-deco-"))
    base = raw
    if wall and caps.get("ffmpeg") and (qa_clips.probe(raw).get("seconds") or 0) < float(wall) - 0.4:
        if pad_to(raw, work / "padded.mp4", wall, caps):
            base = work / "padded.mp4"
            res["padded_to_s"] = round(float(wall), 1)
    br = black_ratio(base, caps)
    res["black_ratio"] = br
    if br is not None and br > BLACK_LIMIT and not force:
        shutil.rmtree(work, ignore_errors=True)
        res.update(code=5, warning=BLACK_WARN)
        return res
    try:
        marks = resolve_marks(c, h, mark_specs)
    except ClipError:
        shutil.rmtree(work, ignore_errors=True)
        raise
    try:
        src, deco = base, None
        if marks or (caption and s["caption"]):
            deco = decorate(base, work, marks, caption if s["caption"] else None, kind, screen, caps)
            if deco["ok"]:
                src = Path(deco["file"])
        cfg = dict(s)
        if deco is not None:
            cfg["caption"] = False                 # drawn (or impossible) here — not again in compress
        if max_seconds:
            cfg["max_seconds"] = max_seconds
        uname = unique_name(c.run_dir, name)
        fin = qa_clips.finalize(src, c.run_dir, uname, {"clips": cfg}, caption=caption, kind=kind, marks=None,
                                start=start, steps=steps)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    if not fin["ok"]:
        res.update(code=5, error="сжатие не удалось: " + str((fin.get("result") or {}).get("warning") or "?"))
        return res
    e = fin["entry"]
    extra = dict(extra or {})
    warn = [x for x in [extra.pop("warning", None), e.get("warning"), (deco or {}).get("warning"),
                        f"доля чёрных кадров {br} — проверить по ленте" if br is not None and br > BLACK_LIMIT else None] if x]
    if warn:
        e["warning"] = "; ".join(warn)
    e.update({"serial": c.serial, "marks": [{"box": [int(v) for v in m["box"]], "label": m["label"], "kind": m["kind"]}
                                            for m in marks], "black_ratio": br,
              "caption_in_video": bool((deco or {}).get("caption_drawn")) or bool(caption and caps.get("drawtext") and s["caption"])})
    if frames:
        e["frames"] = frames
    if extra:
        e.update(extra)
    if not s["keep_raw"] and raw.exists():
        try:
            if raw.resolve().is_relative_to(c.run_dir.resolve()) and not raw.resolve().is_relative_to((c.run_dir / "clips").resolve()):
                raw.unlink()
                res["raw"] = None                  # clips.keep_raw: false — the source is not kept
        except (OSError, ValueError):
            pass
    res.update(ok=True, clip=e, mb=round((e.get("bytes") or 0) / 1048576, 2), warning=e.get("warning"))
    if finding:
        import finding as fmod
        try:
            fmod.attach_clip(c.run_dir, finding, e)
            res["finding"] = finding
        except SystemExit as ex:
            res.update(finding_error=f"находка {finding} не обновлена (код {ex.code}) — finding.py clip позже", code=2)
    sheet = e.get("sheet")
    res["next"] = ((f"посмотреть ленту кадров {sheet} (Read) — на ролике то, что заявлено? Затем " if sheet else
                    "ленты кадров нет (без ffmpeg): посмотреть кадры по шагам или сам ролик; затем ") +
                   f"finding.py clip-viewed {c.run_dir} --id {finding or 'F-NNN'} --file {e['file']}" +
                   ("" if finding else f" (сначала finding.py clip {c.run_dir} --id F-NNN --file {e['file']})"))
    return res


def emit_result(h, res):
    h.emit(res)
    code = res.get("code") if not res.get("ok") else (res.get("code") or 0)
    if code:
        sys.exit(code)


# ---------------------------------------------------------------- subcommands

def opts_from(c):
    a, s = c.a, settings(c)
    return {"seconds": max(1, min(180, int(round(a.seconds if a.seconds else s["max_seconds"])))),
            "short": a.size if a.size else s["width"], "bit_rate": a.bit_rate,
            "touches": a.touches or s.get("touches") or "auto"}


def cmd_start(c, h):
    o = opts_from(c)
    name = safe_name(c.a.name)
    st, _ = start_recording(c, h, name, o["seconds"], o["short"], o["bit_rate"], o["touches"])
    c.log("actions.jsonl", {"clip": "start", "name": name})
    h.emit({"ok": True, "recording": True, "name": name, "remote": st["remote"], "seconds_limit": st["seconds"],
            "size": st["size"], "screen": st["screen"], "touches": st["touches"], "notes": st.get("notes"),
            "state": str(state_path(c)),
            "next": f"воспроизвести шаги находки, затем clip-stop --serial {c.serial} --run-dir {c.run_dir} "
                    "--finding F-NNN --caption «факт» (через ~1 с после результата)"})
    if o["seconds"] > 60:
        sys.stderr.write("adb_helpers: ролик длиннее 60 с — обычно хватает 3–10 с (references/clips.md)\n")


def cmd_stop(c, h):
    a = c.a
    need_run_dir(c)
    path = state_path(c)
    st = load_json(path)
    if a.restore_only:
        if not st:
            h.emit({"ok": True, "restored": None, "note": "состояния записи на этом стенде нет — нечего возвращать"})
            return
        out = recover_clip(c, h, st)
        h.emit(dict(ok=bool(out["touches"].get("restored") or not out["touches"].get("changed")), **out))
        return
    check_mark_syntax(a.mark)
    if not st or not st.get("recording", True):
        if st and st.get("pending_restore"):
            out = recover_clip(c, h, st)
            h.emit(dict(ok=False, error="записи нет; возвращены настройки прерванной записи", **out))
            sys.exit(2)
        raise ClipError("запись не запущена на этом стенде (clip-start) — нечего останавливать", 2)
    raw, info, err, touches = None, None, None, None
    with term_as_interrupt():
        try:
            raw, info = stop_and_pull(c, h, st)
        except ClipError as ex:
            err = ex
        finally:
            touches = restore_touches(c, h, st)
            finish_state(path, st, touches)
    if err:
        h.emit(dict({"ok": False, "error": str(err), "touches": touches}, **err.extra))
        sys.exit(err.code)
    res = finalize_clip(c, h, raw, st["name"], a.caption, a.kind, a.mark, a.step, a.finding, a.force, st.get("screen"),
                        extra={"source": "screenrecord", "touches": bool((st.get("touches") or {}).get("wanted"))},
                        wall=(info or {}).get("wall_s"))
    res.update(touches=touches, stop=info)
    c.log("actions.jsonl", {"clip": "stop", "name": st["name"], "ok": res["ok"], "file": (res.get("clip") or {}).get("file")})
    emit_result(h, res)


def split_steps(argv):
    steps, cur = [], []
    for t in argv or []:
        if t == "--then":
            if cur:
                steps.append(cur)
            cur = []
        else:
            cur.append(t)
    if cur:
        steps.append(cur)
    return steps


def parse_step(c, h, argv, i):
    """(argv, namespace | ('wait', seconds)). Steps are checked BEFORE the recording starts."""
    if argv[0] == "wait":
        try:
            secs = float(argv[1]) if len(argv) > 1 else 1.0
        except ValueError:
            raise ClipError(f"шаг {i}: wait <секунды>", 2)
        return argv, ("wait", max(0.0, min(30.0, secs)))
    if argv[0] not in STEPS:
        raise ClipError(f"шаг {i} «{argv[0]}»: в ролике — действия интерфейса и настройки ({', '.join(sorted(STEPS))}) "
                        "и wait <с>", 2)
    if argv[0] == "text" and "--env" in argv:
        raise ClipError(f"шаг {i}: ввод секрета (--env) под запись запрещён — пароли, коды и логины не записываются "
                        "(safety-rules.md → «Ролики»); войти до clip-start", 2)
    if argv[0] == "shade" and c.stand() == "real":
        raise ClipError(f"шаг {i}: шторка уведомлений реального устройства под запись — там личные уведомления; "
                        "не записывать", 2)
    extra = ["--serial", c.serial] + (["--run-dir", str(c.run_dir)] if c.run_dir else []) + \
        (["--config", c.a.config] if getattr(c.a, "config", None) else []) + \
        (["--confirmed"] if getattr(c.a, "confirm_steps", False) else [])
    buf = io.StringIO()
    try:
        with contextlib.redirect_stderr(buf), contextlib.redirect_stdout(io.StringIO()):
            ns = h.build_parser().parse_args(argv + extra)
    except SystemExit:
        why = (buf.getvalue().strip().splitlines() or ["?"])[-1]
        raise ClipError(f"шаг {i} не разобран: {' '.join(argv)} — {why}", 2)
    for attr in ("x", "y", "text", "id", "desc"):
        if not hasattr(ns, attr):
            setattr(ns, attr, None)
    ns.cmdline = []
    return argv, ns


def run_step(c, ns):
    saved = c.a
    c.a = ns
    so, se, code = io.StringIO(), io.StringIO(), 0
    try:
        with contextlib.redirect_stdout(so), contextlib.redirect_stderr(se):
            ns.fn(c)
    except SystemExit as ex:
        code = ex.code if isinstance(ex.code, int) else (0 if ex.code is None else 5)
        if isinstance(ex.code, str):
            se.write(ex.code)
    except (KeyboardInterrupt, Interrupted):
        raise
    except Exception as ex:  # noqa: BLE001 — a failed step is reported, the recording is stopped normally
        code = 5
        se.write(f"{type(ex).__name__}: {ex}")
    finally:
        c.a = saved
    out = so.getvalue().strip().splitlines()
    parsed = None
    for line in reversed(out):
        try:
            parsed = json.loads(line)
            break
        except ValueError:
            continue
    return code, parsed if parsed is not None else ("\n".join(out)[-300:] or None), se.getvalue().strip()[-300:]


def step_frame(c, h, name, i):
    """Without ffmpeg there is no frame sheet: a screenshot after each step is the model's way to look at the clip."""
    try:
        code, data, _ = c.adb.cmd("exec-out", "screencap", "-p", binary=True, timeout=60)
    except OSError:
        return None
    if code != 0 or not data.startswith(b"\x89PNG"):
        return None
    p = c.run_dir / "clips" / f"{name}-step-{i}.png"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    return str(p.relative_to(c.run_dir))


class FrameGrabber(threading.Thread):
    """Fallback of `clip` when screenrecord cannot work on the stand (no encoder, API < 19): screenshots
    (`exec-out screencap`, read-only) one after another while the steps run — usually 2–4 frames/s."""

    def __init__(self, c, work, limit):
        super().__init__(daemon=True)
        self.base, self.work, self.limit = c.adb.base(), work, limit
        self.frames, self.error, self.stop_ev = [], None, threading.Event()

    def run(self):
        import sdkutil as su
        t0 = time.time()
        while not self.stop_ev.is_set() and time.time() - t0 < self.limit:
            ts = time.time()
            code, data, err = su.run(self.base + ["exec-out", "screencap", "-p"], timeout=20, binary=True)
            if code == 0 and data.startswith(b"\x89PNG"):
                f = self.work / f"f-{len(self.frames):04d}.png"
                f.write_bytes(data)
                self.frames.append((ts, f))
            else:
                self.error = (err or "screencap: не PNG").strip()[:160]
                time.sleep(0.2)


def start_frames(c, h, name, seconds, touches_mode, why):
    """State + touches + FrameGrabber (same state file as clip-start: one recording per stand)."""
    need_run_dir(c)
    path = state_path(c)
    size, info = record_size(c, h, None)
    want, twhy = touches_plan(c, touches_mode)
    st = {"version": 1, "mode": "frames", "serial": c.serial, "name": name, "remote": None, "seconds": seconds,
          "screen": info.get("size"), "stand": c.stand(), "confirmed": bool(getattr(c.a, "confirmed", False)),
          "started_at": now(), "started_ts": time.time(), "recording": True, "host_pid": os.getpid(),
          "fallback_reason": why, "touches": {"wanted": want, "why": twhy, "changed": False}}
    work = Path(tempfile.mkdtemp(prefix="qaclip-frames-"))
    try:
        save_json(path, st)
        if want:
            enable_touches(c, st, path)
    except BaseException:
        finish_state(path, st, restore_touches(c, h, st))
        shutil.rmtree(work, ignore_errors=True)
        raise
    g = FrameGrabber(c, work, seconds)
    g.start()
    return st, g


def frames_to_video(c, h, st, g, caps):
    """Stop the grabber and build recordings/<name>-frames-<ts>.mp4 with the real timing of the screenshots."""
    t_end = time.time()
    g.stop_ev.set()
    g.join(timeout=25)
    try:
        if len(g.frames) < 2:
            raise ClipError("кадры экрана не сняты (" + (g.error or "screencap") + ") — ролик невозможен", 5)
        lst = g.work / "frames.txt"
        lines = []
        for i, (ts, f) in enumerate(g.frames):
            nxt = g.frames[i + 1][0] if i + 1 < len(g.frames) else t_end
            lines.append("file '%s'\nduration %.3f\n" % (f.resolve(), max(0.05, nxt - ts)))
        lines.append("file '%s'\n" % g.frames[-1][1].resolve())       # the concat demuxer needs the last file twice
        lst.write_text("".join(lines), encoding="utf-8")
        raw = c.out_path(None, f"{st['name']}-frames-{h.ts()}.mp4", "recordings").resolve()
        enc = (["-c:v", "libx264", "-preset", "ultrafast", "-crf", "18"] if caps.get("libx264") else ["-c:v", "mpeg4", "-q:v", "2"])
        r = subprocess.run([caps["ffmpeg"], "-y", "-hide_banner", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
                            "-vf", "fps=12,scale=trunc(iw/2)*2:trunc(ih/2)*2", "-pix_fmt", "yuv420p", "-an"] + enc + [str(raw)],
                           capture_output=True, text=True, timeout=300)
        if r.returncode != 0 or not raw.is_file():
            raise ClipError(f"ролик из кадров не собран: {(r.stderr or '').strip()[-200:]}", 5)
        dur = max(0.1, t_end - g.frames[0][0])
        return raw, {"frames_captured": len(g.frames), "fps_captured": round(len(g.frames) / dur, 1)}
    finally:
        shutil.rmtree(g.work, ignore_errors=True)


def cmd_clip(c, h):
    a = c.a
    need_run_dir(c)
    name = safe_name(a.name)
    raw_steps = split_steps(a.cmdline)
    if not raw_steps:
        raise ClipError("clip … -- <шаг> [--then <шаг>]… — нужны шаги воспроизведения (например: -- tap --text «Меню» "
                        "--then wait 1)", 2)
    steps = [parse_step(c, h, s, i) for i, s in enumerate(raw_steps, 1)]
    check_mark_syntax(a.mark)
    plan = [" ".join(shlex.quote(x) for x in s[0]) for s in steps]
    if a.dry_run:
        h.emit({"ok": True, "dry_run": True, "name": name, "steps": plan,
                "note": "шаги разобраны; запись не начиналась, на устройстве ничего не выполнено"})
        return
    o = opts_from(c)
    caps = qa_clips.capabilities()
    grabber, fallback = None, None
    try:
        st, proc = start_recording(c, h, name, o["seconds"], o["short"], o["bit_rate"], o["touches"])
    except ClipError as ex:
        if ex.code != 4 or a.fallback == "none" or not caps.get("ffmpeg") or "уже идёт" in str(ex):
            raise
        fallback = str(ex)
        st, grabber = start_frames(c, h, name, o["seconds"], o["touches"], fallback)
        proc = None
    results, aborted, interrupted, frames = [], None, False, []
    raw, info, err, touches = None, None, None, None
    t0 = time.time()
    with term_as_interrupt():
        try:
            try:
                time.sleep(max(0.0, a.lead))
                for i, (argv, ns) in enumerate(steps, 1):
                    if isinstance(ns, tuple):
                        time.sleep(ns[1])
                        results.append({"step": plan[i - 1], "code": 0})
                        continue
                    code, out, errtxt = run_step(c, ns)
                    results.append({"step": plan[i - 1], "code": code, "output": out, **({"error": errtxt} if errtxt else {})})
                    if code in GUARD_CODES:
                        aborted = {"step": plan[i - 1], "code": code}
                        break
                    if not caps.get("ffmpeg") and grabber is None:
                        fr = step_frame(c, h, name, i)
                        if fr:
                            frames.append(fr)
                time.sleep(max(0.0, a.tail))
            except (KeyboardInterrupt, Interrupted):
                interrupted = True
            try:
                if grabber is not None:
                    raw, info = frames_to_video(c, h, st, grabber, caps)
                else:
                    raw, info = stop_and_pull(c, h, st, proc)
            except ClipError as ex:
                err = ex
        finally:
            if grabber is not None and grabber.is_alive():
                grabber.stop_ev.set()
            touches = restore_touches(c, h, st)
            finish_state(state_path(c), st, touches)
    took = round(time.time() - t0, 1)
    base = {"name": name, "steps": results, "touches": touches, "stop": info, "elapsed_s": took}
    if took > st["seconds"] + 0.5:
        base["warning"] = f"шаги длились {took} с — дольше лимита записи {st['seconds']} с: конец мог не попасть в ролик"
    if interrupted or aborted or err:
        if raw and not settings(c)["keep_raw"]:
            Path(raw).unlink(missing_ok=True)
        why = ("прервано — настройки возвращены" if interrupted else
               f"шаг «{aborted['step']}» не выполнен (код {aborted['code']}: 2 — нужно подтверждение, 3 — запрет guard, "
               "6 — guard недоступен); ролик в находку не записан" if aborted else str(err))
        h.emit(dict(base, ok=False, error=why, blocked=bool(aborted and aborted["code"] == 3)))
        sys.exit(130 if interrupted else (aborted["code"] if aborted else err.code))
    extra = {"source": "frames" if grabber is not None else "screenrecord", "touches": bool(st["touches"].get("wanted"))}
    if grabber is not None:
        extra.update(info or {})
        extra["warning"] = (f"screenrecord недоступен на стенде: ролик собран из скриншотов, ≈{(info or {}).get('fps_captured')} "
                            "кадра/с — плавность и задержки по нему не оценивать")
    res = finalize_clip(c, h, raw, name, a.caption, a.kind, a.mark, plan, a.finding, a.force, st.get("screen"),
                        frames=frames, caps=caps, extra=extra, wall=None if grabber is not None else (info or {}).get("wall_s"))
    if fallback:
        res["fallback"] = fallback
    warn = "; ".join(x for x in [res.get("warning"), base.pop("warning", None)] if x)
    res.update(base)
    res["warning"] = warn or None
    c.log("actions.jsonl", {"clip": "clip", "name": name, "ok": res["ok"], "steps": len(plan)})
    emit_result(h, res)


# ---------------------------------------------------------------- rolling recording

def rolling_alive(h, st):
    if not st or st.get("status") not in ("starting", "running"):
        return False
    hb = float(st.get("heartbeat") or st.get("started_ts") or 0)
    if time.time() - hb > float(st.get("segment") or 8) * 3 + 60:
        return False                                    # no heartbeat: the runner is gone (PID reused?)
    return bool(st.get("runner_pid")) and h.su.pid_alive(st["runner_pid"])


def recover_rolling(c, h, st, keep_segments=False):
    """Clean up after a runner that died (host reboot, lost connection, kill -9): its last segment on the device,
    local segments, settings."""
    out = {"status_was": st.get("status")}
    try:
        cur = (st.get("current") or {}).get("remote")
        if cur:
            if sigint(c, cur)[0]:
                time.sleep(1.0)
            c.run("rm", "-f", cur)
    except SystemExit as ex:
        out["cleanup_error"] = f"код {ex.code}"
    except Exception as ex:  # noqa: BLE001
        out["cleanup_error"] = f"{type(ex).__name__}: {ex}"
    if not keep_segments:
        shutil.rmtree(rolling_dir(c), ignore_errors=True)
    out["touches"] = restore_touches(c, h, st)
    finish_state(rolling_path(c), st, out["touches"])
    return out


def rolling_start(c, h, segment, keep, short, bit_rate, touches_mode, quiet=False):
    """Start the background runner (clip-rolling-run). Returns the state. ClipError on failure (settings returned)."""
    need_run_dir(c)
    path = rolling_path(c)
    notes = []
    old = load_json(path)
    if old:
        if rolling_alive(h, old):
            raise ClipError(f"непрерывная запись на {c.serial} уже идёт (с {old.get('started_at')}) — clip-rolling stop", 2)
        rec = recover_rolling(c, h, old)
        notes.append(f"убрано состояние прошлой непрерывной записи ({old.get('status')}); show_touches: "
                     f"{'возвращён' if rec['touches'].get('restored') else 'не менялся' if not rec['touches'].get('changed') else 'НЕ возвращён'}")
    cs = load_json(state_path(c))
    if cs and cs.get("recording", True) and recorder_alive(h, cs):
        raise ClipError("на этом стенде идёт clip-start — сначала clip-stop", 2)
    check_support(c)
    size, info = record_size(c, h, short)
    want, why = touches_plan(c, touches_mode)
    d = rolling_dir(c)
    shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True, exist_ok=True)
    st = {"version": 1, "serial": c.serial, "tag": serial_tag(c.serial), "segment": segment, "keep": keep,
          "size": list(size) if size else None, "screen": info.get("size"), "bit_rate": bit_rate, "stand": c.stand(),
          "confirmed": bool(getattr(c.a, "confirmed", False)), "status": "starting", "started_at": now(),
          "started_ts": time.time(), "heartbeat": time.time(), "runner_pid": None, "segments": [], "current": None,
          "dir": str(d), "touches": {"wanted": want, "why": why, "changed": False}}
    proc = None
    try:
        save_json(path, st)
        if want:
            enable_touches(c, st, path)
        cmd = [sys.executable, str(HERE / "adb_helpers.py"), "clip-rolling-run", "--serial", c.serial, "--run-dir", str(c.run_dir)]
        if getattr(c.a, "config", None):
            cmd += ["--config", c.a.config]
        if getattr(c.a, "confirmed", False):
            cmd.append("--confirmed")
        proc = h.su.popen_detached(cmd, d / "runner.log")
        end = time.time() + 8.0
        while time.time() < end:
            cur = load_json(path) or {}
            if cur.get("runner_pid") == proc.pid and cur.get("current"):
                st = cur
                break
            if cur.get("status") in ("failed", "lost") or proc.poll() is not None:
                raise ClipError("непрерывная запись не запустилась: " + (cur.get("error") or log_tail(d / "runner.log")[-300:]
                                                                          or f"код {proc.poll()}"), cur.get("error_code") or 5)
            time.sleep(0.15)
        else:
            raise ClipError("фоновый процесс записи не ответил за 8 с: " + log_tail(d / "runner.log")[-300:], 5)
    except BaseException:
        if proc is not None and proc.poll() is None:
            (d / "stop").write_text(now(), encoding="utf-8")
            h.su.kill_pid(proc.pid)
            time.sleep(0.5)
        st = load_json(path) or st
        recover_rolling(c, h, st)
        raise
    c.log("actions.jsonl", {"clip": "rolling-start", "segment": segment, "keep": keep, "runner_pid": proc.pid})
    st["notes"] = notes
    return st


def guarded(c, h, *args, log=False):
    """adb shell with the guard check; actions.jsonl only when log=True (the runner repeats it every segment)."""
    c.gate(c.decide(h.guard.check_adb, ["shell", *map(str, args)], c.cfg, c.stand(), c.serial))
    code, out, err = c.adb.shell(*args, timeout=30)
    if log:
        c.log("actions.jsonl", {"adb": "shell " + " ".join(map(str, args)), "code": code})
    return code, out, err


def device_online(c):
    code, out, _ = c.adb.cmd("get-state", timeout=10)
    return code == 0 and out.strip() == "device"


def rolling_run(c, h):
    """Internal (started by clip-rolling start): record segments one after another until the stop file / SIGTERM.
    The next segment starts BEFORE the finished one is pulled (minimal gap). cut.req (from save) finishes the current
    segment at once and answers cut.done with the same token."""
    path, d = rolling_path(c), rolling_dir(c)
    st = load_json(path)
    if not st:
        sys.exit(2)
    st.update(runner_pid=os.getpid(), status="running", heartbeat=time.time())
    save_json(path, st)
    log = d / "runner.log"
    stop = {"v": False}

    def on_term(*_):
        stop["v"] = True
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, on_term)
    stop_file, cut_req, cut_done = d / "stop", d / "cut.req", d / "cut.done"
    seg, keep = float(st.get("segment") or 8), int(st.get("keep") or 3)
    size, bit_rate, tag = st.get("size"), int(st.get("bit_rate") or 2000000), st.get("tag") or serial_tag(c.serial)
    n, fails, first, cur = int(st.get("next") or 0), 0, True, None

    def stopping():
        return stop["v"] or stop_file.exists()

    def launch():
        nonlocal n, first
        remote = f"/sdcard/qa-roll-{tag}-{n}.mp4"
        off = log.stat().st_size if log.exists() else 0
        proc = launch_recorder(c, h, screenrecord_args(remote, max(1, round(seg)), size, bit_rate), log, quiet=not first)
        first = False
        item = {"n": n, "remote": remote, "proc": proc, "t0": time.time(), "log_off": off}
        n += 1
        st.update(current={"n": item["n"], "remote": remote, "started_ts": item["t0"]}, next=n, heartbeat=time.time())
        save_json(path, st)
        return item

    def finish(item, wait=10.0):
        """SIGINT the device recorder of `item` and wait for its host process."""
        try:
            sigint(c, item["remote"])
        except SystemExit:
            pass
        try:
            item["proc"].wait(timeout=wait)
        except subprocess.TimeoutExpired:
            h.su.kill_pid(item["proc"].pid)

    try:
        while not stopping():
            if cur is None:
                cur = launch()
            time.sleep(0.2)
            rc = cur["proc"].poll()
            cut = cut_req.exists()
            if rc is None and not cut and not stopping():
                if time.time() - float(st.get("heartbeat") or 0) > 5:
                    st["heartbeat"] = time.time()
                    save_json(path, st)
                continue
            if rc is None:
                finish(cur)
                rc = cur["proc"].returncode
            done, cur = cur, None
            dur = time.time() - done["t0"]
            if rc not in (0, None) and dur < 1.5 and not cut:
                fails += 1
                tail = log_tail(log, done["log_off"])
                if not device_online(c):
                    wait_end = time.time() + float(os.environ.get("ANDROID_QA_CLIP_OFFLINE_WAIT") or 60)
                    while time.time() < wait_end:            # wait (60 s by default) for the device to come back
                        if stopping() or device_online(c):
                            break
                        time.sleep(min(2.0, max(0.1, wait_end - time.time())))
                    if not device_online(c):
                        st.update(status="lost", error=f"нет связи с устройством ({tail[-160:]}) — clip-rolling stop / "
                                                       "clip-rolling start после переподключения", error_code=5)
                        break
                    continue
                err = classify_failure(rc, tail)
                if err.code == 4 or fails >= 5:
                    st.update(status="failed", error=str(err), error_code=err.code)
                    break
                time.sleep(1.0)
                continue
            fails = 0
            if not stopping():
                cur = launch()                               # next segment first: minimal gap
            local = d / f"seg-{done['n']}.mp4"
            code, _, _ = c.adb.cmd("pull", done["remote"], str(local), timeout=120)
            try:
                guarded(c, h, "rm", "-f", done["remote"])
            except SystemExit:
                pass
            if code == 0 and local.is_file() and finalized(local):
                st["segments"] = (st.get("segments") or []) + [{"n": done["n"], "file": local.name,
                                                                "seconds": round(dur, 1), "ended_ts": time.time()}]
            else:
                local.unlink(missing_ok=True)
            for old in st["segments"][:-keep]:
                (d / old["file"]).unlink(missing_ok=True)
            st["segments"] = st["segments"][-keep:]
            st["heartbeat"] = time.time()
            if cut:
                token = cut_req.read_text(encoding="utf-8").strip() if cut_req.exists() else ""
                cut_req.unlink(missing_ok=True)
                cut_done.write_text(token, encoding="utf-8")
            save_json(path, st)
    except SystemExit as ex:                                  # guard 2/3/6 on a segment: stop recording
        st.update(status="failed", error=f"guard: код {ex.code} — запись остановлена", error_code=ex.code or 5)
    except Exception as ex:  # noqa: BLE001
        st.update(status="failed", error=f"{type(ex).__name__}: {ex}", error_code=5)
    finally:
        if cur is not None:
            finish(cur, wait=8.0)
            try:
                guarded(c, h, "rm", "-f", cur["remote"])
            except SystemExit:
                pass
        if st.get("status") == "running":
            st["status"] = "stopped"
        st.update(current=None, finished_at=now(), heartbeat=time.time())
        if st["status"] == "failed":
            st["touches_result"] = restore_touches(c, h, st)
        save_json(path, st)
    sys.exit(0)


def rolling_stop(c, h, keep_segments=False):
    path = rolling_path(c)
    st = load_json(path)
    if not st:
        return {"ok": True, "note": "непрерывная запись на этом стенде не запущена"}
    d = rolling_dir(c)
    if st.get("runner_pid") and h.su.pid_alive(st["runner_pid"]):
        d.mkdir(parents=True, exist_ok=True)
        (d / "stop").write_text(now(), encoding="utf-8")
        end = time.time() + 20
        while time.time() < end and h.su.pid_alive(st["runner_pid"]):
            time.sleep(0.2)
        if h.su.pid_alive(st["runner_pid"]):
            h.su.kill_pid(st["runner_pid"])
    st = load_json(path) or st
    out = recover_rolling(c, h, st, keep_segments)
    c.log("actions.jsonl", {"clip": "rolling-stop", "status": out.get("status_was")})
    return dict(ok=bool(out["touches"].get("restored") or not out["touches"].get("changed")), **out)


def pick_segments(d, segs, last):
    """[(file, wall seconds)] — the newest segments that together cover `last` seconds of wall time."""
    files = [(s, d / s["file"]) for s in sorted(segs, key=lambda x: x["n"]) if (d / s["file"]).is_file()]
    pick, total = [], 0.0
    for s, f in reversed(files):
        wall = float(s.get("seconds") or qa_clips.probe(f).get("seconds") or 0)
        pick.insert(0, (f, wall))
        total += wall
        if total >= last:
            break
    return pick


def concat(files, out, caps):
    lst = out.with_suffix(".txt")
    lst.write_text("".join("file '%s'\n" % str(f.resolve()).replace("'", "'\\''") for f in files), encoding="utf-8")
    ff = caps["ffmpeg"]
    for codec in (["-c", "copy"], ["-c:v", "libx264", "-preset", "ultrafast", "-crf", "18", "-pix_fmt", "yuv420p"]):
        r = subprocess.run([ff, "-y", "-hide_banner", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
                            "-an"] + codec + [str(out)], capture_output=True, text=True, timeout=300)
        if r.returncode == 0 and out.is_file() and out.stat().st_size > 0:
            return True
    return False


def rolling_save(c, h, name, last, caption, kind, marks, steps, finding, force):
    """The last ≈ `last` seconds as a regular clip. The runner finishes its current segment first (cut)."""
    need_run_dir(c)
    st = load_json(rolling_path(c))
    if not st:
        raise ClipError("непрерывная запись не запущена (clip-rolling start или soak --clips-on-crash)", 2)
    d = rolling_dir(c)
    note = None
    if rolling_alive(h, st):
        token = uuid.uuid4().hex
        (d / "cut.done").unlink(missing_ok=True)
        (d / "cut.req").write_text(token, encoding="utf-8")
        end = time.time() + 20
        while time.time() < end:
            if (d / "cut.done").exists() and (d / "cut.done").read_text(encoding="utf-8").strip() == token:
                break
            time.sleep(0.2)
        else:
            note = "фон не дописал текущий сегмент за 20 с — взяты готовые сегменты"
        st = load_json(rolling_path(c)) or st
    else:
        note = f"фоновая запись не работает ({st.get('status')}) — взяты готовые сегменты"
    s = settings(c)
    want = min(float(last or s["max_seconds"]), s["max_seconds"])
    trimmed = last and float(last) > s["max_seconds"]
    caps = qa_clips.capabilities()
    picked = pick_segments(d, st.get("segments") or [], want)
    if not picked:
        raise ClipError("сегментов записи нет (запись только началась или не работала): " + (note or ""), 5)
    files = [f for f, _ in picked]
    work = Path(tempfile.mkdtemp(prefix="qaclip-roll-"))
    try:
        if caps.get("ffmpeg"):
            # each segment to its wall duration (screenrecord skips frames of a static screen), then one timeline
            norm = []
            for i, (f, wall) in enumerate(picked):
                out = work / f"n{i}.mp4"
                norm.append(out if pad_to(f, out, wall, caps) else f)
            joined = work / "joined.mp4"
            src = norm[0] if len(norm) == 1 else (joined if concat(norm, joined, caps) else norm[-1])
        else:
            src = files[-1]
            if len(files) > 1:
                note = "; ".join(x for x in [note, "без ffmpeg — только последний сегмент"] if x)
        total = qa_clips.probe(src).get("seconds") or 0
        start = max(0.0, total - want) if total else 0.0
        raw = c.out_path(None, f"{name}-rolling-{h.ts()}.mp4", "recordings")
        shutil.copyfile(src, raw)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    res = finalize_clip(c, h, raw, name, caption, kind, marks, steps, finding, force, st.get("screen"), start=start,
                        caps=caps, extra={"source": "rolling", "touches": bool((st.get("touches") or {}).get("wanted"))})
    notes = [x for x in [note, f"--last {last} больше clips.max_seconds {s['max_seconds']:g} — ролик {want:g} с" if trimmed else None] if x]
    if notes:
        res["note"] = "; ".join(notes)
    c.log("actions.jsonl", {"clip": "rolling-save", "name": name, "ok": res["ok"], "file": (res.get("clip") or {}).get("file")})
    return res


def cmd_rolling(c, h):
    a = c.a
    s = settings(c)
    if a.action == "start":
        st = rolling_start(c, h, max(2.0, min(60.0, a.segment)), max(1, min(20, a.keep)), a.size or s["width"],
                           a.bit_rate, a.touches or s.get("touches") or "auto")
        h.emit({"ok": True, "rolling": True, "segment": st["segment"], "keep": st["keep"], "size": st.get("size"),
                "touches": st.get("touches"), "runner_pid": st.get("runner_pid"), "notes": st.get("notes"),
                "next": f"при сбое: clip-rolling save --name F-NNN-crash --serial {c.serial} --run-dir {c.run_dir}; "
                        "в конце: clip-rolling stop"})
        return
    if a.action == "save":
        check_mark_syntax(a.mark)
        name = safe_name(a.name or (f"{a.finding}-crash" if a.finding else f"crash-{h.ts()}"))
        emit_result(h, rolling_save(c, h, name, a.last, a.caption, a.kind, a.mark, a.step, a.finding, a.force))
        return
    if a.action == "stop":
        need_run_dir(c)
        res = rolling_stop(c, h, a.keep_segments)
        h.emit(res)
        sys.exit(0 if res["ok"] else 5)
    need_run_dir(c)
    st = load_json(rolling_path(c))
    if not st:
        h.emit({"rolling": False})
        return
    view = {k: st.get(k) for k in ("status", "started_at", "segment", "keep", "runner_pid", "error", "touches")}
    view["alive"] = rolling_alive(h, st)
    view["segments"] = len(st.get("segments") or [])
    view["seconds_buffered"] = round(sum(float(x.get("seconds") or 0) for x in st.get("segments") or []), 1)
    h.emit(dict(rolling=True, **view))


# ---------------------------------------------------------------- soak --clips-on-crash

def soak_start(c, h, segment, keep):
    """For soak: start rolling recording; returns (state or None, note)."""
    try:
        s = settings(c)
        st = rolling_start(c, h, max(2.0, min(60.0, segment)), keep, s["width"], 2000000, s.get("touches") or "auto")
        return st, None
    except ClipError as ex:
        return None, f"непрерывная запись не запущена: {ex}"
    except SystemExit as ex:
        return None, f"непрерывная запись не запущена: guard, код {ex.code}"


def soak_save(c, h, name, last, caption):
    try:
        res = rolling_save(c, h, name, last, caption, "error", [], [], None, False)
    except ClipError as ex:
        return {"ok": False, "error": str(ex)}
    except SystemExit as ex:
        return {"ok": False, "error": f"код {ex.code}"}
    out = {"ok": res.get("ok"), "file": (res.get("clip") or {}).get("file"), "sheet": (res.get("clip") or {}).get("sheet"),
           "seconds": (res.get("clip") or {}).get("seconds"), "bytes": (res.get("clip") or {}).get("bytes"),
           "warning": res.get("warning")}
    if res.get("ok"):
        out["entry"] = res["clip"]
    else:
        out["error"] = res.get("warning") or res.get("error")
    return out


def soak_stop(c, h):
    try:
        return rolling_stop(c, h)
    except SystemExit as ex:
        return {"ok": False, "error": f"код {ex.code}"}


def anr_on_screen(c, pkg):
    """The «isn't responding» dialog of the package on the screen (dumpsys window windows; read-only)."""
    _, out, _ = c.adb.shell("dumpsys", "window", "windows", timeout=20)
    for line in (out or "").splitlines():
        if re.search(r"Application Not Responding|isn.t responding|не отвечает", line) and (not pkg or pkg in line):
            return True
    return False


# ---------------------------------------------------------------- registration and dispatch

def register(add, sub, common, fn):
    def rec(p, seconds=True):
        if seconds:
            p.add_argument("--seconds", type=float, help="лимит записи, с (по умолчанию clips.max_seconds = 10; ≤ 180)")
        p.add_argument("--size", type=int, help="короткая сторона кадра, px (по умолчанию clips.width = 720)")
        p.add_argument("--bit-rate", type=int, default=2000000, help="битрейт screenrecord, бит/с")
        p.add_argument("--touches", choices=["auto", "on", "off"],
                       help="показ касаний: auto — эмулятор прогона да, устройство нет (clips.touches)")

    def fin(p):
        p.add_argument("--finding", help="записать ролик в находку (findings.json)")
        p.add_argument("--caption", help="подпись-факт: в кадре (если можно) и в находке")
        p.add_argument("--kind", default="error", choices=list(KINDS), help="error | ok | note | after (после исправления)")
        p.add_argument("--mark", action="append", default=[],
                       help="'x,y,w,h|подпись|error' (пиксели экрана, как у скриншотов) или 'text=…|…' — рамка на ролике")
        p.add_argument("--force", action="store_true", help="записать в находку даже «чёрный» ролик (FLAG_SECURE?)")

    p = add("clip-start", fn)
    p.add_argument("--name", required=True, help="имя ролика: F-003-font → clips/F-003-font.mp4")
    rec(p)
    p = add("clip-stop", fn)
    fin(p)
    p.add_argument("--step", action="append", help="шаг воспроизведения для записи в находке (повторяемый)")
    p.add_argument("--restore-only", action="store_true", help="без ролика: остановить запись и вернуть настройки")
    p = add("clip", fn)
    p.add_argument("--name", required=True)
    rec(p)
    fin(p)
    p.add_argument("--lead", type=float, default=0.5, help="пауза до первого шага, с")
    p.add_argument("--tail", type=float, default=1.0, help="пауза после последнего шага, с")
    p.add_argument("--confirm-steps", action="store_true",
                   help="шаги с подтверждением (код 2) выполнить — только после «да» пользователя на эти действия")
    p.add_argument("--dry-run", action="store_true", help="только разобрать шаги, ничего не записывать")
    p.add_argument("--fallback", choices=["auto", "frames", "none"], default="auto",
                   help="screenrecord не работает на стенде (нет кодека, API < 19): auto/frames — ролик из скриншотов "
                        "(нужен ffmpeg), none — код 4")
    p.epilog = ("Шаги после «--», разделитель --then; каждый шаг — подкоманда adb_helpers.py с её опциями, через guard: "
                "clip --name F-003-menu --seconds 8 -- tap --text «Меню» --expect-change --then wait 1 --then key BACK; "
                "нажатие без дерева: -- tap 540 1200 --no-ui; по описанию: -- long-press --desc «Ещё». "
                "wait S — пауза. Запрещённый шаг не выполняется (logs/blocked.jsonl), цепочка обрывается.")
    p = add("clip-rolling", fn)
    p.add_argument("action", choices=["start", "save", "stop", "status"])
    p.add_argument("--segment", type=float, default=8, help="start: длина сегмента, с")
    p.add_argument("--keep", type=int, default=3, help="start: сколько последних сегментов хранить")
    rec(p, seconds=False)
    p.add_argument("--name", help="save: имя ролика (по умолчанию <finding>-crash)")
    p.add_argument("--last", type=float, help="save: последние N секунд (не больше clips.max_seconds)")
    p.add_argument("--step", action="append", help="save: шаг воспроизведения для записи в находке")
    p.add_argument("--keep-segments", action="store_true", help="stop: оставить сегменты в raw/rolling-<serial>/")
    fin(p)
    p = sub.add_parser("clip-rolling-run", parents=[common])  # internal: started by clip-rolling start
    p.set_defaults(fn=fn)


def dispatch(c, h):
    cmd = c.a.cmd
    try:
        if cmd == "clip-start":
            with term_as_interrupt():
                cmd_start(c, h)
        elif cmd == "clip-stop":
            cmd_stop(c, h)
        elif cmd == "clip":
            cmd_clip(c, h)
        elif cmd == "clip-rolling":
            cmd_rolling(c, h)
        elif cmd == "clip-rolling-run":
            rolling_run(c, h)
    except ClipError as ex:
        h.emit(dict({"ok": False, "error": str(ex), "code": ex.code}, **ex.extra))
        sys.exit(ex.code)
    except (KeyboardInterrupt, Interrupted):
        h.emit({"ok": False, "error": "прервано — настройки устройства возвращены (если менялись)"})
        sys.exit(130)
