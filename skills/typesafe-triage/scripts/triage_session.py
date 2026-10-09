# -*- coding: utf-8 -*-
"""2.3.0: что известно о текущей сессии Claude Code — локально, без сети; наружу ничего не уходит.

Зачем. Заметка говорит «делегируй, если уровень выше твоей модели». Чтобы сравнение было честным, хук должен знать
реальную модель сессии, а не угадывать. Здесь же — effort сессии, есть ли у инструмента Agent параметр effort и длина
сессии (сколько контекста уже накоплено: чем больше, тем дороже передавать его субагенту).

Источники модели (по порядку): TYPESAFE_TRIAGE_SESSION_MODEL (явное указание; unknown/off — не определять) →
стенограмма сессии (transcript_path из ввода хука: модель последнего ответа основной сессии, без субагентов) →
ANTHROPIC_MODEL → поле model в .claude/settings.local.json, .claude/settings.json проекта и ~/.claude/settings.json
(помечается «по настройкам»: запуск с --model или /model их не меняет). Ничего не нашли — модель неизвестна.
Есть ли у Agent параметр effort: TYPESAFE_TRIAGE_AGENT_EFFORT=yes|no → config.json (--set-agent-effort) → стенограмма
(успешный вызов Agent с полем effort). Иначе неизвестно.

Из стенограммы читается только хвост файла (TAIL_BYTES) и только служебные поля: message.model, effort, version, имена
инструментов, наличие ключа effort во входе Agent и флаг is_error результата. Текст сообщений не читается и не сохраняется.
Формат стенограммы внутренний и не документирован: любой сбой разбора — «неизвестно», а не догадка.
"""
import json
import os
import re
from pathlib import Path

TIERS = ("haiku", "sonnet", "opus", "fable")
SESSION_ID_ENV = "CLAUDE_CODE_SESSION_ID"   # есть у процессов, запущенных из Claude Code (Bash, хуки)
EFFORTS = ("low", "medium", "high", "xhigh", "max")
MODEL_ENV = "TYPESAFE_TRIAGE_SESSION_MODEL"
AGENT_EFFORT_ENV = "TYPESAFE_TRIAGE_AGENT_EFFORT"
OFF_WORDS = ("unknown", "off", "none", "no", "0")
YES_WORDS = ("yes", "on", "1", "true", "да")
NO_WORDS = ("no", "off", "0", "false", "нет")
TAIL_BYTES = 1024 * 1024           # читаем не больше хвоста стенограммы (стенограммы бывают по 100+ МБ)
LONG_SESSION_BYTES = 3 * 1024 * 1024   # стенограмма больше — «длинная сессия»: контекст накоплен (оценка, не точный счёт)
AGENT_TOOLS = ("Agent", "Task")


def tier_of(model):
    """Идентификатор или псевдоним модели → уровень (haiku/sonnet/opus/fable) или None.
    opusplan (opus только в режиме плана) считаем sonnet: делегирование касается исполнения."""
    s = str(model or "").strip().lower()
    if not s or s in ("default", "auto") or s in OFF_WORDS:
        return None
    if s.startswith("opusplan"):
        return "sonnet"
    for t in TIERS:
        if t in s:
            return t
    return None


def _yes_no(value):
    s = str(value).strip().lower()
    if s in YES_WORDS:
        return True
    if s in NO_WORDS:
        return False
    return None


def _tail_lines(path, limit=TAIL_BYTES):
    """Строки хвоста файла (первая, обрезанная seek'ом, отбрасывается). → (строки, размер файла)."""
    with open(path, "rb") as f:
        f.seek(0, 2)
        size = f.tell()
        start = max(0, size - limit)
        f.seek(start)
        raw = f.read().decode("utf-8", "replace").split("\n")
    if start > 0 and raw:
        raw = raw[1:]
    return raw, size


def from_transcript(path):
    """Служебные поля стенограммы: модель и effort последнего ответа основной сессии, версия Claude Code, есть ли
    успешный вызов Agent с параметром effort, размер файла. Ошибка чтения/разбора — {}."""
    if not path:
        return {}
    try:
        lines, size = _tail_lines(path)
    except (OSError, ValueError, TypeError):
        return {}
    out = {"bytes": size}
    with_effort, ok_effort = set(), False
    last = None
    for ln in lines:
        if not ln.strip():
            continue
        try:
            rec = json.loads(ln)
        except ValueError:
            continue
        if not isinstance(rec, dict) or rec.get("isSidechain"):
            continue
        if isinstance(rec.get("version"), str):
            out["version"] = rec["version"][:20]
        msg = rec.get("message") if isinstance(rec.get("message"), dict) else {}
        content = msg.get("content") if isinstance(msg.get("content"), list) else []
        if rec.get("type") == "assistant":
            if msg.get("model") and tier_of(msg.get("model")):
                last = rec
            for c in content:
                if (isinstance(c, dict) and c.get("type") == "tool_use" and c.get("name") in AGENT_TOOLS
                        and isinstance(c.get("input"), dict) and "effort" in c["input"]):
                    with_effort.add(c.get("id"))
        elif rec.get("type") == "user" and with_effort:
            for c in content:
                if (isinstance(c, dict) and c.get("type") == "tool_result" and c.get("tool_use_id") in with_effort
                        and not c.get("is_error")):
                    ok_effort = True
    if last is not None:
        out["model"] = str(last["message"]["model"])
        e = str(last.get("effort") or "").lower()
        if e in EFFORTS:
            out["effort"] = e
    if ok_effort:
        out["agent_effort"] = True
    return out


def _settings_model(cwd, home):
    paths = []
    try:
        base = Path(cwd).resolve() if cwd else None
    except (OSError, ValueError):
        base = None
    if base is not None:
        paths += [base / ".claude" / "settings.local.json", base / ".claude" / "settings.json"]
    if home:
        paths.append(Path(home) / ".claude" / "settings.json")
    for p in paths:
        try:
            val = json.loads(p.read_text(encoding="utf-8")).get("model")
        except (OSError, ValueError, AttributeError):
            continue
        if tier_of(val):
            return str(val), p
    return None, None


def find_transcript(session_id, home):
    """Стенограмма сессии по её id (CLAUDE_CODE_SESSION_ID в процессах, запущенных из Claude Code):
    ~/.claude/projects/*/<id>.jsonl. Нет — None."""
    if not session_id or not re.fullmatch(r"[\w-]{8,80}", str(session_id)):
        return None
    try:
        hits = sorted(Path(home, ".claude", "projects").glob("*/%s.jsonl" % session_id))
    except OSError:
        return None
    return str(hits[0]) if hits else None


def session_info(transcript=None, cwd=None, environ=None, home=None, config=None, discover=False):
    """→ {tier, model, model_source, effort, effort_source, agent_effort, agent_effort_source, version, bytes, long, transcript}.
    Неизвестное — None. config — словарь config.json скилла (ключ agent_effort: true/false). discover — без пути
    стенограммы найти её по CLAUDE_CODE_SESSION_ID (ручные команды, запущенные из Claude Code)."""
    env = os.environ if environ is None else environ
    home = home if home is not None else os.path.expanduser("~")
    if transcript is None and discover:
        transcript = find_transcript(env.get(SESSION_ID_ENV), home)
    info = {"tier": None, "model": None, "model_source": None, "effort": None, "effort_source": None,
            "agent_effort": None, "agent_effort_source": None, "version": None, "bytes": None, "long": False,
            "transcript": transcript}
    tr = from_transcript(transcript)
    info["bytes"] = tr.get("bytes")
    info["long"] = bool(tr.get("bytes") and tr["bytes"] >= LONG_SESSION_BYTES)
    info["version"] = tr.get("version")
    declared = (env.get(MODEL_ENV) or "").strip()
    if declared.lower() in OFF_WORDS:
        info["model_source"] = "не определяется (%s=%s)" % (MODEL_ENV, declared)
    elif declared and tier_of(declared):
        info.update(tier=tier_of(declared), model=declared, model_source=MODEL_ENV)
    elif tr.get("model"):
        info.update(tier=tier_of(tr["model"]), model=tr["model"], model_source="стенограмма")
    elif tier_of(env.get("ANTHROPIC_MODEL")):
        info.update(tier=tier_of(env["ANTHROPIC_MODEL"]), model=env["ANTHROPIC_MODEL"], model_source="ANTHROPIC_MODEL")
    else:
        val, path = _settings_model(cwd, home)
        if val:
            info.update(tier=tier_of(val), model=val, model_source="настройки (%s)" % path.name)
    if tr.get("effort"):
        info.update(effort=tr["effort"], effort_source="стенограмма")
    elif str(env.get("CLAUDE_EFFORT") or "").lower() in EFFORTS:
        info.update(effort=env["CLAUDE_EFFORT"].lower(), effort_source="CLAUDE_EFFORT")
    flag = _yes_no(env.get(AGENT_EFFORT_ENV, "")) if env.get(AGENT_EFFORT_ENV) else None
    if flag is not None:
        info.update(agent_effort=flag, agent_effort_source=AGENT_EFFORT_ENV)
    elif isinstance((config or {}).get("agent_effort"), bool):
        info.update(agent_effort=config["agent_effort"], agent_effort_source="config.json (--set-agent-effort)")
    elif tr.get("agent_effort"):
        info.update(agent_effort=True, agent_effort_source="стенограмма (вызов Agent с effort)")
    return info
