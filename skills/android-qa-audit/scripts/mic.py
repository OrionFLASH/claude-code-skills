#!/usr/bin/env python3
"""Sound into the emulated microphone: three paths (references/audio-input.md). Used by adb_helpers.py
`mic-status` / `mic-inject` and by check_env.py (loopback detection). Python 3.9+, standard library only.

  1. grpc     — EmulatorController/injectAudio over gRPC with the per-instance token: own emulator started with
                `avd_manager.py start <AVD> --mic-inject` (= -grpc <port> -grpc-use-token, audio not disabled).
  2. loopback — a virtual audio device of the host (BlackHole / Loopback on macOS, snd-aloop or a PulseAudio/PipeWire
                null sink on Linux, VB-Cable on Windows) as the host input + `adb emu avd hostmicon`; the skill only
                checks and plays the file, it never installs drivers or changes the host's default devices.
  3. file     — no live microphone: push the file to the device (push-media) and import it through the app's
                file picker (import-file).
Each path that cannot work on this machine answers «не поддерживается: <причина>» and names the next path.
"""
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import wave
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import grpc_emu  # noqa: E402
from masking import mask  # noqa: E402

LOOPBACK_RX = re.compile(r"blackhole|loopback|soundflower|vb-?audio|vb-?cable|virtual (audio )?cable|voicemeeter|"
                         r"snd-aloop|null[-_ ]?sink|virtual[-_ ]?mic", re.I)
RATES = (8000, 11025, 16000, 22050, 24000, 32000, 44100, 48000)
CHUNK_S = 0.1   # ≤ 100 ms per packet: the emulator buffers at most 300 ms


def run(cmd, timeout=20):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, encoding="utf-8", errors="replace")
        return p.returncode, p.stdout, p.stderr
    except (OSError, subprocess.TimeoutExpired) as ex:
        return 127, "", str(ex)


# ---------------------------------------------------------------- path 2: host loopback devices

def loopback_info(fast=False):
    """{platform, devices, default_input, default_output, player, ready, note, hint} — read-only."""
    info = {"platform": sys.platform, "devices": [], "default_input": None, "default_output": None, "player": None,
            "ready": False, "note": "", "hint": ""}
    override = os.environ.get("ANDROID_QA_LOOPBACK")  # tests: "BlackHole 2ch|in,out"
    if override is not None:
        name, _, flags = override.partition("|")
        info["devices"] = [name] if name else []
        info["default_input"] = name if "in" in flags else None
        info["default_output"] = name if "out" in flags else None
        info["player"] = os.environ.get("ANDROID_QA_PLAYER") or None
    elif sys.platform == "darwin":
        hal = Path("/Library/Audio/Plug-Ins/HAL")
        if hal.is_dir():
            info["devices"] = sorted(p.stem for p in hal.iterdir() if LOOPBACK_RX.search(p.name))
        if not fast and shutil.which("system_profiler"):
            code, out, _ = run(["system_profiler", "SPAudioDataType"], timeout=30)
            cur = None
            for line in out.splitlines():
                m = re.match(r"^\s{8}(\S.*):\s*$", line)
                if m:
                    cur = m.group(1).strip()
                    if LOOPBACK_RX.search(cur) and cur not in info["devices"]:
                        info["devices"].append(cur)
                elif cur and "Default Input Device: Yes" in line:
                    info["default_input"] = cur
                elif cur and "Default Output Device: Yes" in line:
                    info["default_output"] = cur
        info["player"] = shutil.which("afplay")
    elif sys.platform.startswith("linux"):
        cards = Path("/proc/asound/cards")
        if cards.exists() and "Loopback" in cards.read_text(errors="replace"):
            info["devices"].append("snd-aloop (Loopback)")
        if shutil.which("pactl"):
            code, out, _ = run(["pactl", "list", "short", "sinks"])
            for ln in out.splitlines():
                parts = ln.split("\t")
                if len(parts) > 1 and LOOPBACK_RX.search(parts[1]):
                    info["devices"].append(parts[1])
            code, out, _ = run(["pactl", "get-default-source"])
            info["default_input"] = out.strip() or None
        info["player"] = shutil.which("paplay")
    elif os.name == "nt" and not fast:
        ps = shutil.which("powershell") or shutil.which("pwsh")
        if ps:
            code, out, _ = run([ps, "-NoProfile", "-Command", "Get-CimInstance Win32_SoundDevice | ForEach-Object Name"])
            info["devices"] = [ln.strip() for ln in out.splitlines() if LOOPBACK_RX.search(ln)]
    dev = info["devices"]
    if not dev:
        info["note"] = "виртуального аудиоустройства нет"
        info["hint"] = {"darwin": "BlackHole (brew install --cask blackhole-2ch) или Loopback — ставит пользователь сам",
                        "win32": "VB-Audio Virtual Cable — ставит пользователь сам"}.get(
            sys.platform, "snd-aloop (sudo modprobe snd-aloop) или null-sink PulseAudio/PipeWire — настраивает пользователь")
    else:
        inp = info["default_input"]
        out = info["default_output"]
        if sys.platform.startswith("linux") and info["player"]:
            info["ready"] = bool(inp and LOOPBACK_RX.search(inp))
        else:
            info["ready"] = bool(inp and LOOPBACK_RX.search(inp) and out and LOOPBACK_RX.search(out) and info["player"])
        info["note"] = f"найдено: {', '.join(dev)}"
        if not info["ready"]:
            info["hint"] = ("скил не меняет звуковые устройства хоста: выбрать виртуальное устройство входом "
                            "(и выходом — на macOS) по умолчанию вручную, затем mic-inject --via loopback; "
                            "или путь grpc / file")
            if os.name == "nt":
                info["hint"] = "Windows: воспроизвести файл в VB-Cable вручную; автоматически — путь grpc или file"
    return info


def play_to_loopback(path, info, seconds=None):
    """Play the file into the loopback device. macOS: afplay into the default output (must be the loopback device);
    Linux: paplay --device=<loopback sink>. Returns (ok, text)."""
    player = info.get("player")
    if not player:
        return False, "нет проигрывателя (afplay / paplay)"
    cmd = [player, str(path)]
    if sys.platform.startswith("linux") and Path(player).name == "paplay":
        sink = next((d for d in info["devices"] if not d.startswith("snd-aloop")), None)
        if sink:
            cmd = [player, f"--device={sink}", str(path)]
    if seconds and Path(player).name == "afplay":
        cmd = [player, "-t", str(seconds), str(path)]
    code, out, err = run(cmd, timeout=(seconds or 3600) + 30)
    return code == 0, (out + err).strip()[-200:]


# ---------------------------------------------------------------- WAV → PCM chunks

def wav_params(path):
    """(rate, channels, width, frames) or raises ValueError with a hint."""
    try:
        with wave.open(str(path), "rb") as w:
            rate, ch, width, n = w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getnframes()
    except (wave.Error, EOFError) as ex:
        raise ValueError(f"не WAV PCM ({ex}) — перекодировать: ffmpeg -i in.m4a -ac 1 -ar 16000 -sample_fmt s16 out.wav")
    if ch not in (1, 2) or width not in (1, 2):
        raise ValueError(f"WAV: каналов {ch}, байт на отсчёт {width} — нужен моно/стерео, 8 или 16 бит "
                         "(ffmpeg -i in.wav -ac 1 -ar 16000 -sample_fmt s16 out.wav)")
    if rate not in RATES:
        raise ValueError(f"WAV: частота {rate} Гц — нужна одна из {', '.join(map(str, RATES))} (ffmpeg -ar 16000)")
    return rate, ch, width, n


def chunks(path, at_sec=0.0, loops=1, duration=None):
    """PCM chunks of CHUNK_S seconds: start at at_sec, repeat loops times (0 = endless), stop after duration s."""
    rate, ch, width, n = wav_params(path)
    per = max(1, int(rate * CHUNK_S))
    start = min(n, int(at_sec * rate))
    total = 0.0
    rnd = 0
    while loops == 0 or rnd < loops:
        with wave.open(str(path), "rb") as w:
            w.setpos(start if rnd == 0 else 0)
            while True:
                data = w.readframes(per)
                if not data:
                    break
                total += len(data) / float(ch * width * rate)
                yield data
                if duration and total >= duration:
                    return
        rnd += 1


# ---------------------------------------------------------------- path 1: gRPC

def discovery(c):
    """(info dict, error text). info: port, token, path, avd. Never returns the token in error texts."""
    code, out, err = c.adb.cmd("emu", "avd", "discoverypath", timeout=10)
    lines = [ln.strip() for ln in (out or "").splitlines() if ln.strip() and ln.strip() != "OK"]
    dpath = lines[0] if code == 0 and lines and not lines[0].startswith("KO") else None
    port = c.serial.split("-")[-1] if c.serial.startswith("emulator-") else None
    path, data = grpc_emu.find_discovery(port, dpath)
    if not data:
        return None, ("discovery-файл эмулятора не найден (adb emu avd discoverypath: "
                      f"{(out + err).strip()[:120] or 'пусто'}) — эмулятор запущен без gRPC")
    info = {"path": str(path), "port": data.get("grpc.port"), "token": data.get("grpc.token"), "avd": data.get("avd.name"),
            "jwt": bool(data.get("grpc.jwks")), "keys": grpc_emu.public(data)}
    if not info["port"]:
        return info, "в discovery-файле нет grpc.port — эмулятор запущен без -grpc"
    if not info["token"]:
        return info, ("в discovery-файле нет grpc.token — эмулятор запущен без -grpc-use-token"
                      + (" (только JWT, как из Android Studio: скил JWT не подписывает)" if info["jwt"] else ""))
    return info, None


def stand_args(c):
    """Emulator command line recorded by avd_manager.py start in stands.json (to see -no-audio)."""
    import json
    if not c.run_dir or not (c.run_dir / "stands.json").exists():
        return None
    try:
        reg = json.loads((c.run_dir / "stands.json").read_text(encoding="utf-8"))
    except ValueError:
        return None
    started = [e for e in reg.get("emulators", []) if e.get("serial") == c.serial and not e.get("stopped_at")]
    return started[-1].get("args") if started else None


def grpc_ready(c):
    """(ok, info, reason): own emulator, discovery with token, audio not disabled, getStatus accepted."""
    if c.stand() != "own-emulator":
        return False, None, f"стенд {c.stand()}: подача звука через gRPC — только на своём эмуляторе qa-*"
    info, err = discovery(c)
    if err:
        return False, info, err + " — перезапустить: avd_manager.py start <AVD> --mic-inject --run-dir <RUN_DIR>"
    args = stand_args(c) or []
    if "-no-audio" in args:
        return False, info, "эмулятор запущен с -no-audio (headless без звука) — перезапустить с --mic-inject"
    try:
        st = grpc_emu.get_status(info["port"], info["token"], timeout=8)
    except (grpc_emu.GrpcError, OSError) as ex:
        return False, info, mask(f"gRPC 127.0.0.1:{info['port']} не отвечает или отклонил токен: {ex}",
                                 secrets=(info["token"],))
    info["status"] = st
    return True, info, None


def inject_grpc(c, info, path, a):
    rate, ch, width, n = wav_params(path)
    stop = threading.Event()
    try:
        res = grpc_emu.inject_audio(info["port"], info["token"], chunks(path, a.at_sec, a.loop, a.duration), rate, ch, width,
                                    grpc_emu.MODE_REAL_TIME if a.realtime else grpc_emu.MODE_UNSPECIFIED, stop=stop)
    except KeyboardInterrupt:
        stop.set()
        raise
    except (grpc_emu.GrpcError, OSError) as ex:
        return False, {"error": mask(str(ex), secrets=(info["token"],))}
    res.update({"rate": rate, "channels": ch, "bits": width * 8, "file_seconds": round(n / float(rate), 2)})
    return True, res


# ---------------------------------------------------------------- commands (called by adb_helpers.py)

def path_report(c, h):
    ok, info, why = grpc_ready(c)
    lb = loopback_info(fast=False)
    paths = [{"path": "grpc", "available": ok, "reason": why or f"gRPC 127.0.0.1:{info['port']}, токен принят "
              f"(эмулятор {info.get('status', {}).get('version') or '?'})"},
             {"path": "loopback", "available": lb["ready"] and c.stand() == "own-emulator",
              "reason": (lb["note"] + ("; " + lb["hint"] if lb["hint"] else "")) if c.stand() == "own-emulator"
              else f"стенд {c.stand()}: hostmicon — только на своём эмуляторе"},
             {"path": "file", "available": True, "reason": "push-media + import-file через выбор файла в приложении "
              "(живой микрофон не проверяется)"}]
    return paths, info, lb


def cmd_mic_status(c, h):
    paths, info, lb = path_report(c, h)
    best = next((p["path"] for p in paths if p["available"]), "file")
    h.emit({"serial": c.serial, "stand": c.stand(), "recommended": best, "paths": paths,
            "discovery": (info or {}).get("keys"), "loopback": {k: lb[k] for k in ("devices", "default_input", "default_output")},
            "note": "токен gRPC не печатается; путь 1 — avd_manager.py start <AVD> --mic-inject"})


def cmd_mic_inject(c, h):
    a = c.a
    path = Path(a.wav)
    if not path.is_file():
        h.fail(f"нет файла {path}", 2)
    order = ["grpc", "loopback", "file"] if a.via == "auto" else [a.via]
    skipped = []
    for via in order:
        if via == "grpc":
            ok, info, why = grpc_ready(c)
            if not ok:
                skipped.append({"path": "grpc", "supported": False, "reason": why})
                continue
            c.gate(c.decide(h.guard.check_adb, ["emu", "grpc", "injectAudio"], c.cfg, c.stand(), c.serial))
            try:
                wav_params(path)
            except ValueError as ex:
                h.fail(str(ex), 2)
            started = time.time()
            done, res = inject_grpc(c, info, path, a)
            c.log("actions.jsonl", {"mic_inject": "grpc", "file": path.name, "ok": done,
                                    "seconds": res.get("seconds_sent"), "error": res.get("error")})
            h.emit({"ok": done, "via": "grpc", "file": str(path), "wall_seconds": round(time.time() - started, 1), **res,
                    "skipped": skipped})
            sys.exit(0 if done else 5)
        if via == "loopback":
            lb = loopback_info()
            if c.stand() != "own-emulator" or not lb["ready"]:
                skipped.append({"path": "loopback", "supported": False,
                                "reason": (f"стенд {c.stand()}" if c.stand() != "own-emulator" else lb["note"]) +
                                ("; " + lb["hint"] if lb["hint"] else "")})
                continue
            c.adb_cmd("emu", "avd", "hostmicon")   # guard: confirm (the emulator hears the host input device)
            try:
                ok, text = play_to_loopback(path, lb, a.duration)
            finally:
                c.adb_cmd("emu", "avd", "hostmicoff")
            c.log("actions.jsonl", {"mic_inject": "loopback", "file": path.name, "ok": ok})
            h.emit({"ok": ok, "via": "loopback", "device": lb["default_input"], "player": lb["player"], "output": text,
                    "skipped": skipped})
            sys.exit(0 if ok else 5)
        if via == "file":
            res = h.push_media(c, path, a.folder, a.name)
            h.emit({"ok": True, "via": "file", **res, "skipped": skipped,
                    "next": f"открыть в приложении импорт аудио (системный выбор файла), затем: import-file --name "
                            f"{res['name']} --folder {a.folder}; живой путь «микрофон → запись» этим не проверяется"})
            return
    h.emit({"ok": False, "supported": False, "skipped": skipped,
            "next": "путь file: mic-inject --via file (push-media + import-file)"})
    sys.exit(4)
