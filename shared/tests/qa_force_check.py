#!/usr/bin/env python3
"""Проверки qa_force.py (принудительный запуск QA-скилов): разбор меток и фраз, выбор скила, хук. Запуск: python3 qa_force_check.py
<папка со скриптом shared>. Только стандартная библиотека; код выхода != 0 при ошибке."""
import json
import subprocess
import sys
from pathlib import Path

SHARED = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[2] / "shared" / "scripts"
sys.path.insert(0, str(SHARED))
import qa_force as q  # noqa: E402

SITE, ANDROID = "site-qa-audit", "android-qa-audit"
fails = []


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        fails.append(name)


def who(text):
    """Какие хуки ответят на запрос → множество скилов."""
    f = q.parse(text)
    return {s for s in (SITE, ANDROID) if f and q.note(s, f)}


# метки и опции
f = q.parse("!qa deep autopilot https://example.com проверь вёрстку")
check("метка !qa: опции и задача", f and f["skill"] is None and f["autopilot"] and f["depth"] == "deep" and f["task"].startswith("https://example.com"))
f = q.parse("!site-qa:smoke https://example.com")
check("метка !site-qa:smoke", f and f["skill"] == SITE and f["depth"] == "smoke" and not f["autopilot"])
f = q.parse("qa:deep https://example.com")
check("метка qa:deep вплотную к двоеточию", f and f["depth"] == "deep")
f = q.parse("qa: deep dive into login https://example.com")
check("«qa: deep …» с пробелом — опций нет", f and f["depth"] is None and f["task"].startswith("deep dive"))
f = q.parse("!android-qa auto app.apk")
check("метка !android-qa auto", f and f["skill"] == ANDROID and f["autopilot"])
f = q.parse("!site-qa-audit deep example.org")
check("метка с полным именем", f and f["skill"] == SITE and f["depth"] == "deep")
check("опция-слово дальше по тексту не опция", q.parse("!qa https://example.com проверь deep")["depth"] is None)
check("метка после служебного блока среды", who("<system-reminder>x</system-reminder> !qa https://a.io") == {SITE})

# выбор скила по содержимому
check("URL → site", who("!qa https://example.com") == {SITE})
check("APK → android", who("!qa app.apk на эмуляторе") == {ANDROID})
check("пакет com.example.app не считается доменом", who("!qa приложение com.example.app apk") == {ANDROID})
check("неясно (!qa) → вопрос от обоих хуков", who("!qa проверь") == {SITE, ANDROID})
check("«qa: …» без URL и APK — обычный текст, хуки молчат", who("qa: deep dive into login") == set())
check("явное имя главнее содержимого", who("!android-qa https://example.com") == {ANDROID})

# фразы
check("фраза «запусти скилл site-qa-audit»", who("запусти скилл site-qa-audit на https://x.org") == {SITE})
check("фраза use the android-qa-audit skill", who("Please use the android-qa-audit skill for app.apk") == {ANDROID})
check("название как объект задачи — не вызов", who("почини баг в site-qa-audit") == set())
check("фраза в кавычках — не вызов", who('в отчёте было "используй site-qa-audit"') == set())
check("фраза в `коде` — не вызов", who("`run site-qa-audit` в примере") == set())
check("слэш обрабатывает Claude Code, хук молчит", who("/site-qa-audit https://x.org") == set())
check("обычный запрос — молчит", who("протестируй сайт https://example.com") == set())

# текст строки
n = q.note(SITE, q.parse("!qa deep autopilot https://example.com"))
check("строка: вызов, автопилот, глубина, без публикации", n and 'Skill("site-qa-audit:site-qa-audit")' in n and "Автопилот" in n
      and "Глубина: deep" in n and "Публикацию в GitHub" in n and "не задавай" in n)

# хук как процесс: JSON, код 0, молчание
script = SHARED / "qa_force.py"


def run_hook(skill, payload, raw=None):
    r = subprocess.run([sys.executable, str(script), "--hook", "--skill", skill], input=raw if raw is not None else json.dumps(payload),
                       capture_output=True, text=True)
    return r.returncode, r.stdout.strip(), r.stderr.strip()


rc, out, err = run_hook(SITE, {"prompt": "!qa deep https://example.com"})
ctx = json.loads(out)["hookSpecificOutput"]["additionalContext"] if out else ""
check("хук: additionalContext, код 0", rc == 0 and "ЯВНЫЙ ВЫЗОВ" in ctx and not err)
check("хук: чужой скил молчит", run_hook(ANDROID, {"prompt": "!qa deep https://example.com"}) == (0, "", ""))
check("хук: не JSON → молчит, код 0", run_hook(SITE, None, raw="не json") == (0, "", ""))
check("хук: неизвестный скил → молчит", run_hook("other", {"prompt": "!qa https://a.io"}) == (0, "", ""))

print("qa_force: %s" % ("PASS" if not fails else "FAIL %d" % len(fails)))
sys.exit(1 if fails else 0)
