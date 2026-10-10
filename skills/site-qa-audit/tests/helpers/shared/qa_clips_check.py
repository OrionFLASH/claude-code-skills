#!/usr/bin/env python3
"""Проверки qa_clips.py (ролики без звука для QA-скилов): настройки, политика auto, сжатие под бюджет, GIF, постер, лента кадров,
запись в находку. Запуск: python3 qa_clips_check.py <папка со скриптом shared>. Без ffmpeg проверки видео пропускаются (SKIP).
Только стандартная библиотека; код выхода != 0 при ошибке."""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

SHARED = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[2] / "shared" / "scripts"
sys.path.insert(0, str(SHARED))
import qa_clips as c  # noqa: E402

fails = []


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        fails.append(name)


# настройки: умолчания, приведение типов, границы
s = c.settings(None)
check("settings: умолчания (10 с, 3 МБ, 720, mp4+gif)", (s["max_seconds"], s["max_mb"], s["width"], s["format"], s["mode"]) == (10.0, 3.0, 720, "both", "auto"))
s = c.settings({"clips": {"mode": "ON", "max_seconds": 999, "max_mb": "0.05", "format": "avi", "width": "540", "mask": "#a"}})
check("settings: целый run-config без ключа clips не считается секцией", c.settings({"mode": "dry-run", "repo": {}})["mode"] == "auto"
      and c.settings({"mode": "dry-run", "clips": {"max_mb": 2}})["max_mb"] == 2.0)
check("settings: gif_max_seconds по умолчанию 8", c.settings(None)["gif_max_seconds"] == 8.0)
check("settings: границы и мусор", (s["mode"], s["max_seconds"], s["max_mb"], s["format"], s["width"], s["mask"]) == ("on", 60.0, 0.2, "both", 540, ["#a"]))

# политика auto
for text, want in [("Кнопка не нажимается: нет фокуса и нет реакции на клик", False), ("Элемент появляется на странице", False),
                   ("Меню закрывается само через 0,4 с — мерцание при открытии", True), ("Приложение зависает при повороте экрана", True),
                   ("Краш при нажатии «Сохранить»", True), ("Контраст текста 3,19:1 — нужно 4,5:1", False), ("Подпись обрезана при шрифте 2.0", False),
                   ("Опечатка в заголовке", False), ("Button flickers on hover", True), ("Drawer does not react to swipe", True)]:
    check("should_record: %s → %s" % (text[:40], want), c.should_record(text, "auto")[0] == want)
check("should_record: off никогда, on всегда", not c.should_record("краш", "off")[0] and c.should_record("опечатка", "on")[0])

# видео (нужен ffmpeg)
ff = c.find_ffmpeg()
if not ff:
    print("SKIP видео: ffmpeg не найден")
else:
    tmp = Path(tempfile.mkdtemp(prefix="qaclipchk-"))
    raw = tmp / "raw.mp4"
    subprocess.run([ff, "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc2=size=1080x2340:rate=30", "-f", "lavfi",
                    "-i", "sine=frequency=440:duration=8", "-t", "8", "-c:v", "libx264", "-b:v", "8M", "-pix_fmt", "yuv420p", "-c:a", "aac", str(raw)], check=True)
    check("probe: сырой ролик со звуком", c.probe(raw)["audio"] is True and abs(c.probe(raw)["seconds"] - 8) < 0.5)
    r = c.compress(raw, tmp / "out.mp4", max_seconds=5, max_mb=1.0, width=540, fps=10)
    pr = c.probe(tmp / "out.mp4")
    check("compress: ok, ≤ 1 МБ, ≤ 5,5 с, без звука, h264, ширина ≤ 540",
          r["ok"] and pr["bytes"] <= 1048576 and pr["seconds"] <= 5.5 and not pr["audio"] and pr["codec"] == "h264" and pr["width"] <= 540)
    r2 = c.compress(raw, tmp / "tiny.mp4", max_seconds=8, max_mb=0.005, width=720, fps=12)
    check("compress: невозможный бюджет → лестница до конца и предупреждение", r2["ok"] and len(r2["attempts"]) == len(c.LADDER) and r2["warning"])
    check("compress: нет файла → ok=False", not c.compress(tmp / "none.mp4", tmp / "x.mp4")["ok"])
    g = c.to_gif(tmp / "out.mp4", tmp / "out.gif", max_mb=2.0, max_seconds=4)
    check("gif: ok и > 0", g["ok"] and (tmp / "out.gif").stat().st_size > 0 and (tmp / "out.gif").read_bytes()[:3] == b"GIF")
    check("poster: PNG", c.poster(tmp / "out.mp4", tmp / "p.png")["ok"] and (tmp / "p.png").read_bytes()[:4] == b"\x89PNG")
    check("sheet: PNG", c.sheet(tmp / "out.mp4", tmp / "s.png", frames=6, cols=3)["ok"] and (tmp / "s.png").stat().st_size > 1000)
    # чёрный экран и рамки до масштабирования
    subprocess.run([ff, "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=black:s=360x640:r=10:d=4", str(tmp / "b.mp4")], check=True)
    br_black, br_norm = c.black_ratio(tmp / "b.mp4"), c.black_ratio(out_mp4 := tmp / "out.mp4")
    check("black_ratio: чёрный ролик ≥ 0,8, обычный ≤ 0,2", br_black is not None and br_black >= 0.8 and br_norm is not None and br_norm <= 0.2)
    check("_vf: рамки рисуются до масштаба", c._vf(180, 10, None, [{"x": 1, "y": 1, "w": 5, "h": 5}]).index("drawbox") < c._vf(180, 10, None, [{"x": 1, "y": 1, "w": 5, "h": 5}]).index("scale="))
    check("compress: ролик с рамкой собран", c.compress(raw, tmp / "m.mp4", max_seconds=2, width=180, marks=[{"x": 10, "y": 10, "w": 100, "h": 60}])["ok"])
    # полный цикл
    run = tmp / "run"
    (run / "recordings").mkdir(parents=True)
    rr = run / "recordings" / "raw.mp4"
    rr.write_bytes(raw.read_bytes())
    fin = c.finalize(rr, run, "F-001-menu", {"clips": {"max_seconds": 4, "max_mb": 1.0, "format": "both"}}, caption="Меню закрывается само", kind="error")
    e = fin["entry"]
    check("finalize: клип, gif, постер, лента, исходник удалён", fin["ok"] and e["file"] == "clips/F-001-menu.mp4" and e["gif"] and e["poster"] and e["sheet"] and not rr.exists())
    check("finalize: относительные пути и sha256", not e["file"].startswith("/") and len(e["sha256"]) == 64 and e["audio"] is False and e["kind"] == "error")
    check("check_entry: до просмотра — только unviewed", [i[0] for i in c.check_entry(e, run)] == ["unviewed"])
    e["viewed"] = True
    check("check_entry: просмотренный — чисто", c.check_entry(e, run) == [])
    (run / e["file"]).write_bytes((run / e["file"]).read_bytes() + b"x")
    check("check_entry: изменённый файл → sha", "sha" in [i[0] for i in c.check_entry(e, run)])
    f = c.add_to_finding({"id": "F-001"}, e)
    check("add_to_finding: clips + recordings, повтор заменяет", len(c.add_to_finding(f, e)["clips"]) == 1 and f["recordings"] == [e["file"]])

# без ffmpeg: копия с предупреждением (подмена PATH)
import os  # noqa: E402
save = (os.environ.get("PATH"), os.environ.get("QA_FFMPEG"))
os.environ["PATH"], os.environ["QA_FFMPEG"] = "/nonexistent", ""
tmp2 = Path(tempfile.mkdtemp(prefix="qaclipchk2-"))
(tmp2 / "a.mp4").write_bytes(b"\x00" * 2048)
r = c.compress(tmp2 / "a.mp4", tmp2 / "b.mp4")
os.environ["PATH"], os.environ["QA_FFMPEG"] = save[0], save[1] or ""
if not save[1]:
    os.environ.pop("QA_FFMPEG", None)
check("без ffmpeg: копия и предупреждение", r["ok"] and r["encoder"] == "raw" and "ffmpeg" in (r["warning"] or "") and (tmp2 / "b.mp4").exists())

print("\nИТОГ: %s" % ("все проверки пройдены" if not fails else "провалены: " + "; ".join(fails)))
sys.exit(1 if fails else 0)
