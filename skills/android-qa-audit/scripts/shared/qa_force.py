#!/usr/bin/env python3
"""Принудительный запуск QA-скилов (site-qa-audit, android-qa-audit) из текста запроса.

Хук UserPromptSubmit плагина распознаёт явный вызов скила и добавляет в контекст одну строку «ЯВНЫЙ ВЫЗОВ (qa-force)»:
вызвать скилл первым действием и не задавать вопрос о намерении. Сеть не нужна, только стандартная библиотека; хук никогда
не блокирует запрос, не печатает ошибок и всегда завершается с кодом 0.

Способы (слэш `/site-qa-audit …` обрабатывает сам Claude Code и SKILL.md — хук для него молчит):
  метка в начале запроса  `!qa …`, `qa: …`, `!site-qa …`, `site-qa: …`, `!android-qa …`, `android-qa: …`;
                          `!qa` без названия — скил по содержимому (URL, сайт → site-qa-audit; APK, эмулятор → android-qa-audit;
                          неясно — один вопрос пользователю);
  опции в метке           `autopilot` / `auto` / `автопилот` и глубина `smoke` / `standard` / `deep`
                          (`!qa deep autopilot https://…`, `!site-qa:smoke …`, `qa:deep …`); публикацию в GitHub метка не включает;
  фраза в тексте          «запусти скилл site-qa-audit», «через android-qa-audit», "use the site-qa-audit skill" — вне кавычек и кода.

Использование:
  python3 qa_force.py --hook --skill site-qa-audit     # режим хука (stdin = JSON хука), печатает JSON с additionalContext
  python3 qa_force.py --parse "текст" [--skill NAME]   # разбор запроса, JSON (для отладки и тестов)
"""
import json
import re
import sys

SKILLS = ("site-qa-audit", "android-qa-audit")
SHORT = {"qa": None, "site-qa": "site-qa-audit", "android-qa": "android-qa-audit"}   # qa — скил по содержимому
DEPTHS = ("smoke", "standard", "deep")
AUTO_WORDS = ("autopilot", "auto", "автопилот")
_OPT = r"(?:autopilot|auto|автопилот|smoke|standard|deep)(?![\w-])"
# Метки: «!qa …» (опции через пробел, `:` или `/`) и «qa:опция …» (опции только вплотную к двоеточию: «qa: deep dive» — текст)
BANG_RE = re.compile(r"^\s*!(?P<name>site-qa-audit|android-qa-audit|site-qa|android-qa|qa)(?=[\s:/]|$)", re.I)
COLON_RE = re.compile(r"^\s*(?P<name>site-qa-audit|android-qa-audit|site-qa|android-qa|qa):", re.I)
OPT_RE = re.compile(r"[\s:/,+]*(?P<opt>%s)" % _OPT, re.I)
PHRASE_RE = re.compile(
    r"\b(?:запусти\w*|используй\w*|примени\w*|вызови\w*|через|с\s+помощью|run|use|using|invoke|via|with)\s+(?:the\s+|этот\s+|скилл?\s+|skill\s+)*"
    r"(?P<name>(?:site|android)[- ]qa[- ]audit)\b", re.I)
SERVICE_RE = re.compile(
    r"<(system-reminder|ide_selection|ide_opened_file|task-notification|agent-message|user-prompt-submit-hook|command-name|command-message|"
    r"command-args|local-command-stdout|local-command-stderr|local-command-caveat)\b[^>]*>.*?</\1\s*>", re.S | re.I)
MASK_RES = [re.compile(p, re.S) for p in (r"```.*?```", r"«[^«»\n]{1,300}»", r"“[^“”\n]{1,300}”", r'"[^"\n]{1,300}"', r"`[^`\n]{1,300}`")]
ANDROID_RE = re.compile(
    r"\.(?:apk|aab|xapk|apks)\b|\bandroid\b|андроид|\badb\b|эмулятор|\bemulator\b|\bavd\b|\blogcat\b|\bcom\.[a-z0-9_]+\.[a-z0-9_.]+", re.I)
PACKAGE_RE = re.compile(r"\b(?:com|org|net|io|ru)\.[a-z0-9_]+\.[a-z0-9_.]+", re.I)
SITE_RE = re.compile(
    r"https?://|file://|\bwww\.|\bсайт\w*|\bwebsite\b|\bweb[- ]?app\b|веб-?приложени|\blocalhost\b|"
    r"\b[a-z0-9-]+\.(?:com|ru|org|io|net|dev|app|su|рф)\b", re.I)


def _canon(name):
    n = re.sub(r"[ ]", "-", name.lower())
    return SHORT.get(n, n if n in SKILLS else None)


def _options(text, pos, bang):
    """Опции метки после позиции pos → (autopilot, depth, позиция конца)."""
    auto, depth, end = False, None, pos
    first = True
    while True:
        m = OPT_RE.match(text, end)
        if not m:
            break
        if not bang and first and m.start("opt") != pos:   # «qa: deep …» — пробел после двоеточия: опций нет
            break
        first = False
        w = m.group("opt").lower()
        if w in AUTO_WORDS:
            auto = True
        else:
            depth = w
        end = m.end()
    return auto, depth, end


def guess_skill(text):
    """Скил по содержимому: 'site-qa-audit' | 'android-qa-audit' | None (неясно)."""
    android = bool(ANDROID_RE.search(text))
    site = bool(SITE_RE.search(PACKAGE_RE.sub(" ", text)))
    if android and not site:
        return "android-qa-audit"
    if site and not android:
        return "site-qa-audit"
    return None


def parse(prompt):
    """Запрос → None или {form, skill (None — неясно), autopilot, depth, label, task, bang}.
    form: "label" | "phrase"; label — как метка записана в запросе."""
    if not isinstance(prompt, str):
        return None
    text = SERVICE_RE.sub(" ", prompt).strip()
    for rx, bang in ((BANG_RE, True), (COLON_RE, False)):
        m = rx.match(text)
        if m:
            auto, depth, end = _options(text, m.end(), bang)
            task = text[end:].strip(" \t:,")
            return {"form": "label", "skill": _canon(m.group("name")), "autopilot": auto, "depth": depth,
                    "label": text[:end].strip(), "task": task, "bang": bang}
    masked = text
    for rx in MASK_RES:                      # фраза в кавычках, `коде` и блоках кода — цитата, а не просьба
        masked = rx.sub(lambda mt: " " * len(mt.group(0)), masked)
    m = PHRASE_RE.search(masked)
    if m:
        return {"form": "phrase", "skill": _canon(m.group("name")), "autopilot": False, "depth": None,
                "label": m.group(0).strip(), "task": text, "bang": True}
    return None


def note(skill, found):
    """Строка для контекста от имени хука скила `skill`; None — этот хук молчит."""
    target = found["skill"] or guess_skill(found["task"])
    if target and target != skill:
        return None
    label = found["label"]
    if target is None and not found["bang"]:      # «qa: deep dive …» без URL и APK — обычный текст, а не вызов
        return None
    if target is None:
        return ("ЯВНЫЙ ВЫЗОВ (qa-force): пользователь принудительно запускает QA-скил (%s), но тип объекта неясен. Задай ОДИН вопрос "
                "AskUserQuestion: «Сайт или веб-приложение» (site-qa-audit) / «Android-приложение» (android-qa-audit), затем вызови "
                "выбранный скил как явный вызов — вопрос о намерении не задавай. Если такая же строка уже есть выше — это то же "
                "требование, вопрос один." % label)
    parts = ["ЯВНЫЙ ВЫЗОВ (qa-force): пользователь принудительно запускает скил %s (%s). Первым действием вызови Skill(\"%s:%s\"); "
             "вопрос о намерении («Запустить QA-аудит?») не задавай — это явный вызов, сразу «Порядок работы»." % (skill, label, skill, skill)]
    if found["autopilot"]:
        parts.append("Режим «Автопилот» (по SKILL.md: без опроса и «старт», недостающее — по умолчанию, вопрос — только если без него нельзя).")
    if found["depth"]:
        parts.append("Глубина: %s — не переспрашивать, записать в run-config (depth)." % found["depth"])
    parts.append("Публикацию в GitHub эта метка не включает: только отдельным «да». Саму метку в тексте задачи игнорируй.")
    return " ".join(parts)


def hook(skill, data):
    """Ввод хука → JSON для stdout или None."""
    found = parse(data.get("prompt")) if isinstance(data, dict) else None
    text = note(skill, found) if found else None
    if not text:
        return None
    return {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": text}}


def _opt(argv, name):
    return argv[argv.index(name) + 1] if name in argv and argv.index(name) + 1 < len(argv) else None


def main(argv):
    if "--parse" in argv:
        found = parse(_opt(argv, "--parse"))
        skill = _opt(argv, "--skill")
        out = {"found": found, "note": note(skill, found) if found and skill else None}
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0
    if "--hook" in argv:
        try:
            skill = _opt(argv, "--skill")
            if skill not in SKILLS:
                return 0
            out = hook(skill, json.load(sys.stdin))
            if out:
                sys.stdout.write(json.dumps(out, ensure_ascii=False) + "\n")
        except Exception:        # хук не блокирует запрос и не шумит
            pass
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
