#!/usr/bin/env python3
"""Короткие скринкасты (ролики без звука) для QA-скилов: сжатие под бюджет, GIF, постер, контактный лист кадров, запись в находку.

Общий модуль site-qa-audit и android-qa-audit (references/clips.md каждого скила). Только стандартная библиотека;
ffmpeg/ffprobe — внешние программы и **необязательны**: без них ролик сохраняется как есть (с предупреждением), а проверки
размера и длительности работают по размеру файла и заголовку MP4.

Принцип: ролик нужен, чтобы показать то, что скриншот не показывает (анимация, мерцание, зависание, реакция на жест,
переходы, потеря состояния, падение). Короткий (по умолчанию ≤ 10 с), маленький (по умолчанию ≤ 3 МБ), без звука.

  qa_clips.compress(src, dst, ...)  → {ok, file, bytes, seconds, width, height, fps, codec, encoder, attempts[], warning}
  qa_clips.to_gif(src, dst, ...)    → {ok, file, bytes, seconds, warning}
  qa_clips.poster(src, dst)         → PNG-кадр из середины ролика (превью для issue)
  qa_clips.sheet(src, dst, frames)  → PNG-лента кадров (модель смотрит её вместо видео: Read изображения); нужен полноценный ffmpeg
  qa_clips.probe(path)              → {seconds, width, height, fps, codec, bytes, audio}
  qa_clips.entry(...)               → объект для findings[].clips[]
  qa_clips.should_record(text, mode)→ (bool, причина): нужна ли анимация/время для показа дефекта
  qa_clips.settings(cfg)            → настройки из run-config (clips: …) с умолчаниями
  qa_clips.cli(argv)                → qa_clips.py compress|gif|poster|sheet|probe|check ...

Умолчания (clips в run-config): mode auto, max_seconds 10, max_mb 3, width 720, fps 12, format both (mp4 + GIF для коротких),
gif_max_seconds 8, gif_max_mb 1.5, caption true, keep_raw false.
Коды выхода CLI: 0 — готово, 1 — готово с предупреждением (не уложились в бюджет, нет ffmpeg), 2 — ошибка входа.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

DEFAULTS = {
    "mode": "auto",          # auto | on | off
    "max_seconds": 10,
    "max_mb": 3.0,
    "width": 720,
    "fps": 12,
    "format": "both",        # mp4 | gif | both
    "gif_max_seconds": 8,
    "gif_max_mb": 1.5,
    "gif_width": 480,
    "gif_fps": 8,
    "caption": True,
    "touches": "auto",       # android: показывать касания (auto — на эмуляторе да, на устройстве нет)
    "keep_raw": False,
    "mask": [],              # site: CSS-селекторы, которые размываются в кадре
}
KINDS = ("error", "ok", "note", "after")
VIDEO_EXT = (".mp4", ".webm", ".mov", ".mkv")

# Лестница сжатия: (crf, доля ширины от целевой, fps). Берётся первая, что укладывается в бюджет.
LADDER = [(30, 1.0, 1.0), (33, 0.85, 0.85), (36, 0.7, 0.7), (38, 0.55, 0.55), (40, 0.45, 0.45)]

# Признаки, что дефект виден только во времени (для auto): RU и EN, основы слов.
MOTION_RE = re.compile(
    r"анимаци|мерца|мигае|дрожи|дёрга|дерга|подёргив|рывк|\bлаг|тормоз|завис|не реагир|задержк|медленн|плавн|переход между|прокрутк|"
    r"скролл|жест|свайп|смахив|долгое нажат|двойное нажат|потеря состояни|сбрасыва|вспыхив|моргает|закрывается сам|краш|падени|"
    r"вылет|\banr\b|не отвечает|гонк|\brace\b|поворот экрана|смена ориентаци|шторк|toast|тост\b|снэкбар|snackbar|"
    r"flicker|jank|stutter|\blag\b|freez|hang|unrespons|animation|transition|scroll|swipe|gesture|crash|flash|blink|delay|"
    r"state lost|resets?\b|debounce|double[- ]click", re.I)
STATIC_RE = re.compile(r"контраст|обрезан|обрезает|перекрыт|шрифт|размер цели|меньше 24|орфограф|опечатк|перевод|локализац|"
                       r"alt\b|aria|lang\b|meta|og:|hreflang|title\b|цвет|отступ|выравнив|typo|contrast|truncat|clipped|overlap", re.I)


def settings(cfg=None):
    """Настройки роликов из run-config (`clips:`), с умолчаниями и приведением типов. cfg может быть dict или None."""
    raw = {}
    if isinstance(cfg, dict):
        if isinstance(cfg.get("clips"), dict):
            raw = cfg["clips"]
        elif cfg and set(cfg) <= set(DEFAULTS):   # сама секция clips; целый run-config без ключа clips — не секция
            raw = cfg
    s = dict(DEFAULTS)
    for k in DEFAULTS:
        if k in raw and raw[k] is not None:
            s[k] = raw[k]
    s["mode"] = str(s["mode"]).lower() if str(s["mode"]).lower() in ("auto", "on", "off") else "auto"
    s["format"] = str(s["format"]).lower() if str(s["format"]).lower() in ("mp4", "gif", "both") else "both"
    for k in ("max_seconds", "gif_max_seconds"):
        s[k] = max(1.0, min(60.0, float(s[k])))
    for k in ("max_mb", "gif_max_mb"):
        s[k] = max(0.2, min(50.0, float(s[k])))
    for k in ("width", "gif_width", "fps", "gif_fps"):
        s[k] = max(2, int(s[k]))
    s["keep_raw"] = bool(s["keep_raw"])
    s["caption"] = bool(s["caption"])
    s["mask"] = [x for x in (s["mask"] if isinstance(s["mask"], list) else [s["mask"]]) if x]
    return s


def should_record(text, mode="auto", direction=None):
    """(нужен ли ролик, причина). off — нет; on — да; auto — да, если описание дефекта про время/движение/жест/состояние
    и не про чисто статичное свойство (контраст, обрезка, перекрытие, шрифт, орфография)."""
    mode = (mode or "auto").lower()
    if mode == "off":
        return False, "clips.mode=off"
    if mode == "on":
        return True, "clips.mode=on"
    t = text or ""
    m = MOTION_RE.search(t)
    if m and not (STATIC_RE.search(t) and not re.search(r"анимаци|мерца|завис|краш|падени|вылет|flicker|jank|crash|freez", t, re.I)):
        return True, "дефект виден во времени: «%s»" % m.group(0)
    if direction in ("performance", "lifecycle", "gestures", "interaction", "stability"):
        return True, "направление %s зависит от времени" % direction
    return False, "статичный дефект — хватает скриншота"


# ---------- ffmpeg / ffprobe ----------
def _playwright_ffmpeg():
    roots = [Path(os.environ["PLAYWRIGHT_BROWSERS_PATH"])] if os.environ.get("PLAYWRIGHT_BROWSERS_PATH") else []
    home = Path.home()
    roots += [home / "Library" / "Caches" / "ms-playwright", home / ".cache" / "ms-playwright",
              Path(os.environ.get("LOCALAPPDATA", str(home))) / "ms-playwright"]
    for r in roots:
        if r.is_dir():
            for d in sorted(r.glob("ffmpeg-*"), reverse=True):
                for f in d.iterdir():
                    if f.name.startswith("ffmpeg") and f.is_file() and os.access(f, os.X_OK):
                        return str(f)
    return None


def find_ffmpeg(allow_limited=False):
    """Путь к полноценному ffmpeg: QA_FFMPEG → PATH. Сборка из кэша Playwright — урезанная (только VP8), её отдаёт только
    allow_limited=True."""
    p = os.environ.get("QA_FFMPEG")
    if p and Path(p).is_file():
        return p
    p = shutil.which("ffmpeg")
    if p:
        return p
    return _playwright_ffmpeg() if allow_limited else None


def find_ffprobe():
    p = os.environ.get("QA_FFPROBE")
    if p and Path(p).is_file():
        return p
    p = shutil.which("ffprobe")
    if p:
        return p
    ff = find_ffmpeg()
    if ff:
        cand = Path(ff).with_name("ffprobe" + (".exe" if ff.lower().endswith(".exe") else ""))
        if cand.is_file():
            return str(cand)
    return None


def have_filter(name, ffmpeg=None):
    ff = ffmpeg or find_ffmpeg()
    if not ff:
        return False
    try:
        r = subprocess.run([ff, "-hide_banner", "-filters"], capture_output=True, text=True, timeout=20)
        return bool(re.search(r"\b%s\b" % re.escape(name), r.stdout))
    except (OSError, subprocess.TimeoutExpired):
        return False


_DRAWTEXT_OK = {}
_FONTS = ("/System/Library/Fonts/Supplemental/Arial.ttf", "/System/Library/Fonts/Helvetica.ttc", "/Library/Fonts/Arial.ttf",
          "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/dejavu/DejaVuSans.ttf", "/usr/share/fonts/TTF/DejaVuSans.ttf",
          "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf", "C:/Windows/Fonts/arial.ttf")


def find_font():
    for f in _FONTS:
        if Path(f).is_file():
            return f
    return None


def drawtext_works(ffmpeg=None):
    """Фильтр drawtext есть **и** отрисовывает текст (нужен шрифт); результат кешируется. Если фильтр есть, а шрифтов нет,
    подпись через ffmpeg не рисуем — иначе падают все шаги лестницы сжатия."""
    ff = ffmpeg or find_ffmpeg()
    if not ff or not have_filter("drawtext", ff):
        return False
    if ff not in _DRAWTEXT_OK:
        font = find_font()
        flt = "drawtext=text='x':fontsize=12:fontcolor=white:expansion=none" + (":fontfile='%s'" % font if font else "")
        code, _ = _run([ff, "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=black:s=64x32:d=0.1", "-vf", flt,
                        "-frames:v", "1", "-f", "null", "-"], timeout=30)
        _DRAWTEXT_OK[ff] = code == 0
    return _DRAWTEXT_OK[ff]


def capabilities():
    """Что умеет окружение: ffmpeg, ffprobe, кодеки и фильтры (drawtext для подписей в кадре)."""
    ff, fp = find_ffmpeg(), find_ffprobe()
    caps = {"ffmpeg": ff, "ffprobe": fp, "libx264": False, "libvpx": False, "drawtext": False, "gif": False, "version": None,
            "limited_ffmpeg": None if ff else _playwright_ffmpeg()}
    if ff:
        try:
            v = subprocess.run([ff, "-hide_banner", "-version"], capture_output=True, text=True, timeout=20).stdout
            m = re.search(r"ffmpeg version (\S+)", v)
            caps["version"] = m.group(1) if m else None
            enc = subprocess.run([ff, "-hide_banner", "-encoders"], capture_output=True, text=True, timeout=20).stdout
            caps["libx264"] = "libx264" in enc
            caps["libvpx"] = "libvpx" in enc
            caps["gif"] = bool(re.search(r"\bgif\b", enc))
            caps["drawtext"] = drawtext_works(ff)
        except (OSError, subprocess.TimeoutExpired):
            pass
    return caps


def _mp4_duration(path):
    """Длительность MP4 по заголовку mvhd (без ffprobe) или None."""
    try:
        data = Path(path).read_bytes()
    except OSError:
        return None
    i = data.find(b"mvhd")
    if i < 0 or i + 24 > len(data):
        return None
    ver = data[i + 4]
    try:
        if ver == 1:
            ts, dur = struct.unpack(">IQ", data[i + 24:i + 36])
        else:
            ts, dur = struct.unpack(">II", data[i + 16:i + 24])
    except struct.error:
        return None
    return round(dur / ts, 2) if ts else None


def probe(path):
    """{seconds, width, height, fps, codec, bytes, audio}; поля None, если не удалось определить."""
    p = Path(path)
    out = {"seconds": None, "width": None, "height": None, "fps": None, "codec": None, "audio": None,
           "bytes": p.stat().st_size if p.exists() else 0}
    fp = find_ffprobe()
    if fp and p.exists():
        try:
            r = subprocess.run([fp, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(p)],
                               capture_output=True, text=True, timeout=60)
            j = json.loads(r.stdout or "{}")
            for s in j.get("streams", []):
                if s.get("codec_type") == "video" and out["codec"] is None:
                    out["codec"] = s.get("codec_name")
                    out["width"], out["height"] = s.get("width"), s.get("height")
                    num, _, den = (s.get("avg_frame_rate") or "0/1").partition("/")
                    try:
                        out["fps"] = round(float(num) / float(den or 1), 2) if float(den or 1) else None
                    except ValueError:
                        pass
                if s.get("codec_type") == "audio":
                    out["audio"] = True
            if out["audio"] is None:
                out["audio"] = False
            d = (j.get("format") or {}).get("duration")
            out["seconds"] = round(float(d), 2) if d else None
        except (OSError, ValueError, subprocess.TimeoutExpired):
            pass
    if out["seconds"] is None and p.suffix.lower() in (".mp4", ".mov"):
        out["seconds"] = _mp4_duration(p)
    return out


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _run(cmd, timeout=300):
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return r.returncode, (r.stderr or "")[-600:]


def _vf(width, fps, caption=None, marks=None, ffmpeg=None, extra=None):
    """Цепочка фильтров: fps → метки (в пикселях ИСХОДНОГО кадра, до масштаба — рамки не съезжают при смене ширины на шагах
    лестницы) → масштаб до целевой ширины (не увеличивать, чётные размеры) → подпись (в пикселях выхода)."""
    f = ["fps=%s" % fps]
    for m in marks or []:
        f.append("drawbox=x=%d:y=%d:w=%d:h=%d:color=%s@0.95:t=4" % (m["x"], m["y"], m["w"], m["h"], m.get("color", "0xFFD60A")))
    f.append("scale='min(%d,iw)':-2:flags=lanczos" % width)
    if caption and drawtext_works(ffmpeg):
        txt = re.sub(r"[\\':%]", " ", caption)[:90]
        font = find_font()
        f.append("drawbox=x=0:y=ih-44:w=iw:h=44:color=black@0.55:t=fill")
        f.append("drawtext=text='%s':expansion=none:x=12:y=h-32:fontsize=20:fontcolor=white%s" % (txt, ":fontfile='%s'" % font if font else ""))
    if extra:
        f.append(extra)
    return ",".join(f)


def compress(src, dst, max_seconds=10, max_mb=3.0, width=720, fps=12, start=0.0, caption=None, marks=None, scale_ref=None):
    """Сжать ролик под бюджет: без звука, H.264 yuv420p, faststart, не длиннее max_seconds, не тяжелее max_mb.
    Лестница LADDER повторяет кодирование с меньшим качеством/кадрами/шириной, пока не уложится. Без ffmpeg — копия
    исходника с предупреждением. Возвращает словарь результата (ok=False только если нечего сохранять)."""
    src, dst = Path(src), Path(dst)
    res = {"ok": False, "file": str(dst), "bytes": 0, "seconds": None, "width": None, "height": None, "fps": None,
           "codec": None, "encoder": None, "attempts": [], "warning": None}
    if not src.is_file() or src.stat().st_size == 0:
        res["warning"] = "исходный ролик пуст или не найден: %s" % src
        return res
    dst.parent.mkdir(parents=True, exist_ok=True)
    budget = int(max_mb * 1024 * 1024)
    ff = find_ffmpeg()
    if not ff:
        if src.suffix.lower() != dst.suffix.lower():
            dst = dst.with_suffix(src.suffix)
            res["file"] = str(dst)
        if src.resolve() != dst.resolve():
            shutil.copyfile(src, dst)
        pr = probe(dst)
        res.update(ok=True, encoder="raw", bytes=pr["bytes"], seconds=pr["seconds"], width=pr["width"], height=pr["height"],
                   fps=pr["fps"], codec=pr["codec"])
        notes = ["ffmpeg не найден — ролик не сжат (brew install ffmpeg / apt install ffmpeg)"]
        if pr["bytes"] > budget:
            notes.append("размер %.1f МБ больше бюджета %.1f МБ" % (pr["bytes"] / 1048576, max_mb))
        if pr["seconds"] and pr["seconds"] > max_seconds:
            notes.append("длительность %.1f с больше %.0f с" % (pr["seconds"], max_seconds))
        res["warning"] = "; ".join(notes)
        return res
    best = None
    for crf, wk, fk in LADDER:
        w = max(160, int(width * wk) // 2 * 2)
        f = max(4, int(round(fps * fk)))
        tmp = Path(tempfile.mkdtemp(prefix="qaclip-")) / "out.mp4"
        cmd = [ff, "-y", "-hide_banner", "-loglevel", "error"]
        if start:
            cmd += ["-ss", "%.2f" % start]
        cmd += ["-i", str(src), "-map", "0:v:0", "-t", "%.2f" % max_seconds, "-an", "-vf", _vf(w, f, caption, marks, ff),
                "-c:v", "libx264", "-preset", "veryfast", "-crf", str(crf), "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(tmp)]
        code, err = _run(cmd)
        size = tmp.stat().st_size if tmp.exists() else 0
        res["attempts"].append({"crf": crf, "width": w, "fps": f, "bytes": size, "rc": code})
        if code != 0 or size == 0:
            if "Unknown encoder" in err or "libx264" in err:
                res["warning"] = "ffmpeg без libx264: использую VP9/VP8 (webm)"
                tmp.unlink(missing_ok=True)
                return _compress_webm(ff, src, dst, max_seconds, budget, width, fps, start, res)
            res["warning"] = "ffmpeg: " + err.strip().splitlines()[-1] if err.strip() else "ffmpeg завершился с ошибкой"
            continue
        if best is None or size < best[1]:
            best = (tmp, size)
        if size <= budget:
            break
    if best is None:
        return res
    shutil.move(str(best[0]), str(dst))
    pr = probe(dst)
    res.update(ok=True, encoder="ffmpeg-x264", bytes=pr["bytes"], seconds=pr["seconds"], width=pr["width"], height=pr["height"],
               fps=pr["fps"], codec=pr["codec"])
    if pr["bytes"] > budget:
        res["warning"] = "не уложились в %.1f МБ даже на минимальном качестве (%.2f МБ): сократите длительность или область" % (
            max_mb, pr["bytes"] / 1048576)
    return res


def _compress_webm(ff, src, dst, max_seconds, budget, width, fps, start, res):
    dst = dst.with_suffix(".webm")
    res["file"] = str(dst)
    best = None
    for crf, wk, fk in LADDER:
        w = max(160, int(width * wk) // 2 * 2)
        f = max(4, int(round(fps * fk)))
        tmp = Path(tempfile.mkdtemp(prefix="qaclip-")) / "out.webm"
        cmd = [ff, "-y", "-hide_banner", "-loglevel", "error"] + (["-ss", "%.2f" % start] if start else []) + [
            "-i", str(src), "-map", "0:v:0", "-t", "%.2f" % max_seconds, "-an", "-vf", _vf(w, f), "-c:v", "libvpx", "-b:v", "0", "-crf", str(crf), str(tmp)]
        code, err = _run(cmd)
        size = tmp.stat().st_size if tmp.exists() else 0
        res["attempts"].append({"crf": crf, "width": w, "fps": f, "bytes": size, "rc": code, "codec": "vp8"})
        if code == 0 and size and (best is None or size < best[1]):
            best = (tmp, size)
            if size <= budget:
                break
    if best is None:
        return res
    shutil.move(str(best[0]), str(dst))
    pr = probe(dst)
    res.update(ok=True, encoder="ffmpeg-vp8", bytes=pr["bytes"], seconds=pr["seconds"], width=pr["width"], height=pr["height"],
               fps=pr["fps"], codec=pr["codec"])
    return res


def to_gif(src, dst, width=480, fps=8, max_mb=1.5, max_seconds=6, start=0.0):
    """GIF для вставки в issue (рисуется в Markdown везде). Только с ffmpeg; лестница снижает ширину/кадры до бюджета."""
    res = {"ok": False, "file": str(dst), "bytes": 0, "seconds": None, "warning": None}
    ff = find_ffmpeg()
    if not ff:
        res["warning"] = "для GIF нужен ffmpeg"
        return res
    budget = int(max_mb * 1024 * 1024)
    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    best = None
    for wk, fk in ((1.0, 1.0), (0.8, 0.75), (0.65, 0.6), (0.5, 0.5), (0.4, 0.4)):
        w = max(120, int(width * wk) // 2 * 2)
        f = max(3, int(round(fps * fk)))
        tmp = Path(tempfile.mkdtemp(prefix="qagif-")) / "out.gif"
        flt = "fps=%d,scale=%d:-2:flags=lanczos,split[a][b];[a]palettegen=max_colors=96:stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=4" % (f, w)
        cmd = [ff, "-y", "-hide_banner", "-loglevel", "error"] + (["-ss", "%.2f" % start] if start else []) + [
            "-i", str(src), "-t", "%.2f" % max_seconds, "-an", "-filter_complex", flt, "-loop", "0", str(tmp)]
        code, err = _run(cmd)
        size = tmp.stat().st_size if tmp.exists() else 0
        if code == 0 and size and (best is None or size < best[1]):
            best = (tmp, size)
            if size <= budget:
                break
    if best is None:
        res["warning"] = "ffmpeg не смог собрать GIF"
        return res
    shutil.move(str(best[0]), str(dst))
    pr = probe(dst)
    res.update(ok=True, bytes=Path(dst).stat().st_size, seconds=pr["seconds"])
    if res["bytes"] > budget:
        res["warning"] = "GIF %.2f МБ больше бюджета %.1f МБ — не вставлять в issue, ссылка на mp4" % (res["bytes"] / 1048576, max_mb)
    return res


def poster(src, dst, at=None):
    """Один кадр (PNG) из середины ролика — превью для issue и отчёта."""
    ff = find_ffmpeg()      # урезанная сборка из кэша Playwright (только VP8) не умеет PNG и tile — не используем
    if not ff:
        return {"ok": False, "warning": "для постера нужен ffmpeg (brew install ffmpeg)"}
    pr = probe(src)
    t = at if at is not None else ((pr["seconds"] or 2) / 2)
    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    code, err = _run([ff, "-y", "-hide_banner", "-loglevel", "error", "-ss", "%.2f" % t, "-i", str(src), "-frames:v", "1", str(dst)])
    ok = code == 0 and Path(dst).is_file() and Path(dst).stat().st_size > 0
    return {"ok": ok, "file": str(dst), "warning": None if ok else (err.strip().splitlines() or ["ffmpeg: ошибка"])[-1]}


def sheet(src, dst, frames=8, cols=4, thumb=320):
    """Лента кадров ролика одной PNG: модель смотрит её (Read) вместо видео и убеждается, что на ролике то, что заявлено.
    Кадры равномерно по длительности, с номерами секунд."""
    ff = find_ffmpeg()
    if not ff:
        return {"ok": False, "warning": "для ленты кадров нужен ffmpeg (brew install ffmpeg)"}
    pr = probe(src)
    secs = pr["seconds"] or 4.0
    fps = max(0.2, frames / secs)
    rows = (frames + cols - 1) // cols
    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    flt = "fps=%.3f,scale=%d:-2,tile=%dx%d:padding=4:margin=4:color=0x222222" % (fps, thumb, cols, rows)
    code, err = _run([ff, "-y", "-hide_banner", "-loglevel", "error", "-i", str(src), "-vf", flt, "-frames:v", "1", str(dst)])
    ok = code == 0 and Path(dst).is_file() and Path(dst).stat().st_size > 0
    return {"ok": ok, "file": str(dst), "frames": frames, "seconds": secs,
            "warning": None if ok else (err.strip().splitlines() or ["ffmpeg: ошибка"])[-1]}


def black_ratio(src, samples=6):
    """Доля почти чёрных кадров (0..1) среди равномерных выборок — признак FLAG_SECURE / пустого экрана. Читает весь вывод
    ffmpeg (не хвост) и делит на число реально снятых кадров. None — не удалось (нет ffmpeg, битый файл)."""
    ff = find_ffmpeg()
    if not ff:
        return None
    pr = probe(src)
    secs = pr["seconds"] or 3.0
    r = subprocess.run([ff, "-hide_banner", "-i", str(src), "-map", "0:v:0", "-vf",
                        "fps=%.3f,blackframe=amount=98:threshold=32" % max(0.3, samples / secs), "-an", "-f", "null", "-"],
                       capture_output=True, text=True, timeout=180)
    if r.returncode != 0:
        return None
    out = r.stderr or ""
    black = len(re.findall(r"blackframe\b.*\bpblack:\d+", out)) or len(re.findall(r"\[Parsed_blackframe", out))
    frames = None
    m = re.findall(r"frame=\s*(\d+)", out)
    if m:
        frames = int(m[-1])
    total = frames or max(1, int(round(secs * max(0.3, samples / secs))))
    return round(min(1.0, black / float(max(1, total))), 2)


def _rel(x, run_dir):
    """Путь x относительно run_dir (если лежит внутри), иначе как есть; совместимо с Python 3.8 (без Path.is_relative_to)."""
    if not x:
        return None
    if run_dir:
        try:
            return str(Path(x).resolve().relative_to(Path(run_dir).resolve()))
        except ValueError:
            pass
    return str(x)


def _inside(path, base):
    try:
        Path(path).resolve().relative_to(Path(base).resolve())
        return True
    except ValueError:
        return False


def entry(file, run_dir=None, kind="error", caption="", gif=None, poster_file=None, steps=None, encoder=None, result=None, extra=None):
    """Объект для findings[].clips[]: пути — относительно run_dir (если задан), размеры и sha256 — по файлу."""
    p = Path(file)
    rel = lambda x: _rel(x, run_dir)
    pr = probe(p) if p.exists() else {}
    e = {"file": rel(p), "gif": rel(gif), "poster": rel(poster_file), "kind": kind if kind in KINDS else "error",
         "seconds": pr.get("seconds"), "bytes": pr.get("bytes"), "width": pr.get("width"), "height": pr.get("height"), "fps": pr.get("fps"),
         "codec": pr.get("codec"), "audio": bool(pr.get("audio")), "caption": caption or "", "steps": steps or [],
         "encoder": encoder or (result or {}).get("encoder"), "sha256": sha256(p) if p.exists() else None,
         "viewed": False, "created": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    if result and result.get("warning"):
        e["warning"] = result["warning"]
    if extra:
        e.update(extra)
    return e


def check_entry(e, run_dir, cfg=None):
    """Проблемы одного клипа: [(код, текст)] — файл есть, нет звука, длительность и размер в бюджете, просмотрен."""
    s = settings(cfg)
    issues = []
    p = (Path(run_dir) / e["file"]) if e.get("file") and not Path(e["file"]).is_absolute() else Path(e.get("file") or "")
    if not p.is_file():
        return [("missing", "файл ролика не найден: %s" % e.get("file"))]
    size = p.stat().st_size
    if size > s["max_mb"] * 1048576 * 1.05:
        issues.append(("size", "ролик %.2f МБ больше бюджета %.1f МБ" % (size / 1048576, s["max_mb"])))
    sec = e.get("seconds")
    if sec and sec > s["max_seconds"] + 0.5:
        issues.append(("duration", "ролик %.1f с длиннее %.0f с" % (sec, s["max_seconds"])))
    if e.get("audio"):
        issues.append(("audio", "в ролике есть звук — он не нужен и может содержать личное"))
    if e.get("sha256") and sha256(p) != e["sha256"]:
        issues.append(("sha", "файл изменился после записи в находку (sha256 не совпал)"))
    if not e.get("viewed"):
        issues.append(("unviewed", "ролик не просмотрен (лента кадров: qa_clips sheet … и Read)"))
    g = e.get("gif")
    if g:
        gp = (Path(run_dir) / g) if not Path(g).is_absolute() else Path(g)
        if not gp.is_file():
            issues.append(("gif-missing", "GIF не найден: %s" % g))
        elif gp.stat().st_size > s["gif_max_mb"] * 1048576 * 1.05:
            issues.append(("gif-size", "GIF %.2f МБ больше %.1f МБ — в issue ссылкой на mp4" % (gp.stat().st_size / 1048576, s["gif_max_mb"])))
    return issues


def finalize(src, run_dir, name, cfg=None, caption=None, kind="error", marks=None, start=0.0, steps=None, subdir="clips"):
    """Полный цикл после записи: сжать → GIF (если формат и длительность позволяют) → постер → лента кадров → запись для находки.
    src — сырой ролик; результат в <run_dir>/<subdir>/<name>.mp4 (+ .gif, -poster.png, -sheet.png). Сырой файл удаляется,
    если keep_raw=false и он лежит внутри run_dir (но не в clips/)."""
    s = settings(cfg)
    run = Path(run_dir)
    out = run / subdir / (name if name.lower().endswith(VIDEO_EXT) else name + ".mp4")
    res = compress(src, out, s["max_seconds"], s["max_mb"], s["width"], s["fps"], start=start,
                   caption=caption if s["caption"] else None, marks=marks)
    if not res["ok"]:
        return {"ok": False, "result": res, "entry": None}
    video = Path(res["file"])
    gif = None
    if s["format"] in ("gif", "both") and find_ffmpeg() and (res["seconds"] or 0) <= s["gif_max_seconds"] + 0.5:
        g = to_gif(video, video.with_suffix(".gif"), s["gif_width"], s["gif_fps"], s["gif_max_mb"], s["gif_max_seconds"])
        if g["ok"] and not (g["warning"] and "не вставлять" in g["warning"]):
            gif = g["file"]
        elif g["ok"]:
            gif = g["file"]
            res["warning"] = ((res["warning"] + "; ") if res["warning"] else "") + g["warning"]
    if s["format"] == "gif" and gif:
        pass
    po = poster(video, video.with_name(video.stem + "-poster.png"))
    sh = sheet(video, video.with_name(video.stem + "-sheet.png"))
    if not s["keep_raw"] and Path(src).is_file():
        try:
            sp = Path(src).resolve()
            if _inside(sp, run) and not _inside(sp, run / subdir) and sp != video.resolve():
                sp.unlink()
        except OSError:
            pass
    e = entry(video, run, kind, caption or "", gif=gif, poster_file=po.get("file") if po["ok"] else None, steps=steps, result=res,
              extra={"sheet": _rel(sh["file"], run) if sh.get("ok") else None})
    return {"ok": True, "result": res, "entry": e, "poster": po, "sheet": sh}


def add_to_finding(finding, e):
    """Дописать клип в finding['clips'] (дубль по file заменяется) и ссылку в finding['recordings'] для совместимости."""
    clips = [c for c in finding.get("clips") or [] if isinstance(c, dict) and c.get("file") != e["file"]]
    clips.append(e)
    finding["clips"] = clips
    rec = [r for r in finding.get("recordings") or [] if isinstance(r, str)]
    if e["file"] not in rec:
        rec.append(e["file"])
    finding["recordings"] = rec
    return finding


# ---------- CLI ----------
def _json(obj):
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def cli(argv=None):
    ap = argparse.ArgumentParser(prog="qa_clips.py", description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("compress", help="сжать ролик под бюджет")
    c.add_argument("src")
    c.add_argument("dst")
    c.add_argument("--max-seconds", type=float, default=DEFAULTS["max_seconds"])
    c.add_argument("--max-mb", type=float, default=DEFAULTS["max_mb"])
    c.add_argument("--width", type=int, default=DEFAULTS["width"])
    c.add_argument("--fps", type=int, default=DEFAULTS["fps"])
    c.add_argument("--start", type=float, default=0.0)
    c.add_argument("--caption")
    g = sub.add_parser("gif", help="GIF из ролика")
    g.add_argument("src")
    g.add_argument("dst")
    g.add_argument("--width", type=int, default=DEFAULTS["gif_width"])
    g.add_argument("--fps", type=int, default=DEFAULTS["gif_fps"])
    g.add_argument("--max-mb", type=float, default=DEFAULTS["gif_max_mb"])
    g.add_argument("--max-seconds", type=float, default=DEFAULTS["gif_max_seconds"])
    p = sub.add_parser("poster", help="кадр-превью")
    p.add_argument("src")
    p.add_argument("dst")
    p.add_argument("--at", type=float)
    s = sub.add_parser("sheet", help="лента кадров одной PNG (для просмотра моделью)")
    s.add_argument("src")
    s.add_argument("dst")
    s.add_argument("--frames", type=int, default=8)
    s.add_argument("--cols", type=int, default=4)
    s.add_argument("--thumb", type=int, default=320)
    pr = sub.add_parser("probe", help="длительность, размер, кодек, наличие звука")
    pr.add_argument("src")
    sub.add_parser("check", help="что умеет окружение (ffmpeg, кодеки, drawtext)")
    a = ap.parse_args(argv)
    if a.cmd == "check":
        _json(capabilities())
        return 0
    if not Path(a.src).is_file():
        print("нет файла: %s" % a.src, file=sys.stderr)
        return 2
    if a.cmd == "probe":
        _json(probe(a.src))
        return 0
    if a.cmd == "compress":
        r = compress(a.src, a.dst, a.max_seconds, a.max_mb, a.width, a.fps, a.start, a.caption)
    elif a.cmd == "gif":
        r = to_gif(a.src, a.dst, a.width, a.fps, a.max_mb, a.max_seconds)
    elif a.cmd == "poster":
        r = poster(a.src, a.dst, a.at)
    else:
        r = sheet(a.src, a.dst, a.frames, a.cols, a.thumb)
    _json(r)
    return 0 if r.get("ok") and not r.get("warning") else 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(cli())
