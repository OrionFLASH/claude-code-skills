#!/usr/bin/env python3
"""Необязательная оценка каждого предложения моделью TypeSafe Jev → data/typesafe-jev.json.

  typesafe_eval.py <OUT> [--limit N] [--dry-run] [--redo [--yes]] [--force]

Каждому предложению задаются узкие вопросы (вероятности «да/нет», шкалы 1–5, выбор класса Кано) одним запросом.
Результат — отдельная колонка typesafe в scores.json (score.py), в composite не входит.

Ключ — только из переменной окружения TYPESAFE_API_KEY; никуда не пишется и не печатается.
Нет ключа или run-config tools.typesafe = "off" (без --force) → файл с полем skipped и код 0.
--dry-run — без сети: печатает вопросы и состояние первого предложения, файл не пишет.
--limit N — оценить не больше N предложений (N ≥ 1; --limit 0 — ошибка: «без ограничения» — это отсутствие флага).
--redo — переспросить уже оценённые; иначе оценки дописываются к имеющимся (можно продолжить после обрыва).
  --redo тратит запросы заново, поэтому требует подтверждения: в терминале — вопрос «Продолжить? [y/N]», без
  терминала (агент, CI) — только с --yes. Перед запросами печатается, сколько их будет («Будет запросов: N»).
Личный режим (project.audience = personal | circle | personal_then_public): вместо p_acquisition и p_revenue —
p_time_saved (польза владельцу) и p_maintainable (поддержка посильна одному), impact — влияние на задачу владельца.
Адрес API можно переопределить TYPESAFE_API_URL (только для тестов). Только стандартная библиотека.
"""
import argparse
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

API_URL = os.environ.get("TYPESAFE_API_URL") or "https://api.typesafe.ai/v1/systemone"
MODEL = "jev-latest"
TIMEOUT_S = 60
RETRIES = 3
TRANSIENT_HTTP = {429, 500, 502, 503, 504, 529}
CA_FALLBACKS = ["/etc/ssl/cert.pem", "/opt/homebrew/etc/ca-certificates/cert.pem", "/etc/ssl/certs/ca-certificates.crt"]

# Ключ ответа → вопрос. noul — вероятность «да» (0..1); score — уровень шкалы; choice — один из вариантов.
QUESTIONS = {
    "p_success": {"type": "noul", "instructions": "Насколько вероятно, что при разумной реализации это предложение даст заметный измеримый результат по своей целевой метрике в пределах горизонта стратегии?",
                  "criteria": {"true": "Результат вероятен и измерим", "false": "Результат маловероятен или неизмерим"}},
    "p_user_value": {"type": "noul", "instructions": "Получат ли пользователи продукта от этого предложения ощутимую пользу (решённую задачу, сэкономленное время, новую возможность)?",
                     "criteria": {"true": "Польза ощутима для заметной части пользователей", "false": "Польза слабая или для единиц"}},
    "risk": {"type": "noul", "instructions": "Есть ли у предложения существенный юридический, лицензионный, платформенный, приватностный, репутационный или технический риск?",
             "criteria": {"true": "Риск реален и может навредить или заблокировать", "false": "Риска нет или он легко управляется"}},
    "p_fit": {"type": "noul", "instructions": "Соответствует ли предложение позиционированию продукта и цели стратегии из контекста?",
              "criteria": {"true": "Прямо усиливает позиционирование и цель", "false": "Противоречит или не связано"}},
    "p_cheap_test": {"type": "noul", "instructions": "Можно ли проверить гипотезу дёшево — за одну-две недели без крупной разработки?",
                     "criteria": {"true": "Да, есть дешёвый тест", "false": "Нет, нужна полноценная реализация"}},
    "p_acquisition": {"type": "noul", "instructions": "Приведёт ли предложение новых пользователей (поиск, сообщества, вирусность, партнёры)?",
                      "criteria": {"true": "Да, это канал привлечения", "false": "Нет, на привлечение не влияет"}},
    "p_revenue": {"type": "noul", "instructions": "Повысит ли предложение выручку или конверсию в оплату?",
                  "criteria": {"true": "Да, прямо влияет на деньги", "false": "Нет, с монетизацией не связано"}},
    "impact": {"type": "score", "instructions": "Ожидаемое влияние предложения на рост продукта (аудитория, активация, удержание, выручка) в пределах горизонта.",
               "criteria": ["Почти нет", "Небольшое", "Заметное", "Большое", "Меняет траекторию продукта"]},
    "effort": {"type": "score", "instructions": "Сколько работы потребует реализация для небольшой команды?",
               "criteria": ["До 1 дня", "До недели", "2–4 недели", "1–3 месяца", "Больше 3 месяцев"]},
    "kano": {"type": "choice", "instructions": "К какому классу модели Кано относится предложение для пользователей?",
             "criteria": {"must": "Ожидается по умолчанию, отсутствие раздражает", "linear": "Чем больше, тем лучше — линейная ценность",
                          "delight": "Приятный сюрприз, не ожидается", "indifferent": "Пользователям безразлично"}}}
# личный режим (project.audience = personal | circle | personal_then_public, SM 4.3): вместо вопросов о привлечении и выручке —
# польза владельцу и посильность поддержки; влияние — на задачу владельца, а не на рост аудитории
PERSONAL_AUDIENCES = ("personal", "circle", "personal_then_public")
PERSONAL_REPLACE = {
    "p_acquisition": ("p_time_saved", {"type": "noul", "instructions": "Сэкономит ли предложение владельцу заметное время, деньги или ошибки в его задаче?",
                                       "criteria": {"true": "Да, польза владельцу ощутима", "false": "Нет, польза слабая"}}),
    "p_revenue": ("p_maintainable", {"type": "noul", "instructions": "Посильна ли поддержка результата одному владельцу (обновления, данные, зависимости)?",
                                     "criteria": {"true": "Поддержка посильна", "false": "Поддержка тяжёлая"}}),
}
PERSONAL_IMPACT = {"type": "score", "instructions": "Ожидаемое влияние предложения на задачу владельца (экономия времени, денег, ошибок, качество решений) в пределах горизонта.",
                   "criteria": ["Почти нет", "Небольшое", "Заметное", "Большое", "Меняет то, как владелец решает задачу"]}
PROPOSAL_FIELDS = ["title", "category", "segment", "description", "rationale", "current_feature", "effort_days",
                   "risks", "cheap_test", "horizon", "evidence_class"]


def is_personal(cfg):
    return str(((cfg or {}).get("project") or {}).get("audience") or "public").lower() in PERSONAL_AUDIENCES


def questions_for(cfg):
    """Набор вопросов прогона: публичный (по умолчанию) или личного режима."""
    if not is_personal(cfg):
        return dict(QUESTIONS)
    q = {}
    for k, v in QUESTIONS.items():
        if k in PERSONAL_REPLACE:
            nk, nv = PERSONAL_REPLACE[k]
            q[nk] = nv
        elif k == "impact":
            q[k] = PERSONAL_IMPACT
        else:
            q[k] = v
    return q


def use_questions(cfg):
    """Переключить вопросы модуля на набор прогона (ask, parse_answers, skeleton читают QUESTIONS)."""
    global QUESTIONS
    QUESTIONS = questions_for(cfg)
    return QUESTIONS


def ssl_context():
    """Стандартный контекст; без корневых сертификатов у сборки Python — системный пакет CA. Проверку не отключаем."""
    ctx = ssl.create_default_context()
    if ctx.cert_store_stats().get("x509_ca", 0) == 0:
        for f in CA_FALLBACKS:
            if os.path.exists(f):
                return ssl.create_default_context(cafile=f)
    return ctx


def context_from_config(cfg):
    """Обезличенный контекст продукта из run-config (без путей, адресов репозитория и личных данных)."""
    prod, strat = cfg.get("product") or {}, cfg.get("strategy") or {}
    parts = []
    if prod.get("name"):
        parts.append("Продукт: %s." % prod["name"])
    if prod.get("type") and prod["type"] != "auto":
        parts.append("Тип: %s." % prod["type"])
    if prod.get("known_facts"):
        parts.append("Известно: %s" % str(prod["known_facts"])[:600])
    if strat.get("kind"):
        parts.append("Тип стратегии: %s." % strat["kind"])
    if strat.get("goal"):
        parts.append("Цель: %s." % strat["goal"])
    if strat.get("horizon_months"):
        parts.append("Горизонт: %s мес." % strat["horizon_months"])
    if strat.get("markets"):
        parts.append("Рынки: %s." % ", ".join(map(str, strat["markets"])))
    if strat.get("constraints"):
        parts.append("Ограничения: %s" % str(strat["constraints"])[:300])
    if is_personal(cfg):
        parts.append("Личный инструмент владельца (аудитории и монетизации нет): ценность — экономия времени, денег и ошибок владельца.")
    return " ".join(parts) or "Цифровой продукт; контекст не задан."


def build_state(context, p):
    return {"context": context, "proposal": {k: p.get(k) for k in PROPOSAL_FIELDS if p.get(k) not in (None, "", [])}}


def ask(state, key, url=None, timeout=TIMEOUT_S):
    """Один запрос к TypeSafe с повтором при временных ошибках. Ключ уходит только в заголовок."""
    body = json.dumps({"state": state, "model": MODEL, "questions": QUESTIONS}).encode("utf-8")
    last = None
    for attempt in range(RETRIES + 1):
        req = urllib.request.Request(url or API_URL, data=body, method="POST",
                                     headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=ssl_context()) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            last = e
            if e.code not in TRANSIENT_HTTP or attempt == RETRIES:
                raise
        except (urllib.error.URLError, TimeoutError) as e:
            last = e
            if attempt == RETRIES:
                raise
        time.sleep(1.5 * (attempt + 1))
    raise last


def parse_answers(resp):
    """Ответ API → плоский словарь оценок. Шкалы — уровень + 1 (1–5), вероятности — 0..1."""
    a = resp.get("answers") or {}
    out = {}
    for k, q in QUESTIONS.items():
        ans = a.get(k)
        if not isinstance(ans, dict):
            continue
        if q["type"] == "noul" and "noul" in ans:
            out[k] = round(float(ans["noul"]), 4)
        elif q["type"] == "score" and "score" in ans:
            out[k] = round(float(ans["score"]) + 1, 3)
            if ans.get("confidence") is not None:
                out[k + "_conf"] = round(float(ans["confidence"]), 3)
        elif q["type"] == "choice" and "choice" in ans:
            out[k] = ans["choice"]
            if isinstance(ans.get("probabilities"), dict):
                out[k + "_probs"] = {c: round(float(v), 3) for c, v in ans["probabilities"].items()}
    return out


def write(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def skeleton(prev=None, skipped=None):
    q = [{"key": k, "text": v["instructions"], "kind": {"noul": "p", "score": "score", "choice": "choice"}[v["type"]]}
         for k, v in QUESTIONS.items()]
    return {"model": "jev", "date": date.today().isoformat(), "questions": q,
            "items": dict((prev or {}).get("items") or {}), "skipped": skipped}


def positive_int(text):
    try:
        n = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError("--limit: нужно целое число ≥ 1, получено %r" % text)
    if n < 1:
        raise argparse.ArgumentTypeError("--limit %s: нужно число ≥ 1 (0 не означает «без ограничения» — чтобы оценить "
                                         "все предложения, не указывайте --limit)" % text)
    return n


def pending(todo, items, redo):
    """Предложения, по которым будет запрос: без оценки, с ошибкой или все при --redo."""
    return [p for p in todo if redo or p["id"] not in items or "error" in (items.get(p["id"]) or {})]


def confirm_redo(n, yes, stream=None):
    """--redo: True — можно продолжать. Без терминала — только с --yes."""
    if yes:
        return True
    stream = stream or sys.stdin
    if not (hasattr(stream, "isatty") and stream.isatty()):
        print("--redo переспросит уже оценённые предложения (%d запросов к TypeSafe). Без терминала нужно подтверждение "
              "флагом --yes — остановлено." % n, file=sys.stderr)
        return False
    sys.stdout.write("--redo: будет %d запросов к TypeSafe, прежние оценки перезапишутся. Продолжить? [y/N] " % n)
    sys.stdout.flush()
    ans = stream.readline().strip().lower()
    return ans in ("y", "yes", "д", "да")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Оценка предложений моделью TypeSafe Jev (необязательно).")
    ap.add_argument("out", help="папка прогона <OUT>")
    ap.add_argument("--limit", type=positive_int, help="оценить не больше N предложений (N ≥ 1)")
    ap.add_argument("--dry-run", action="store_true", help="без сети: показать вопросы и состояние, файл не писать")
    ap.add_argument("--redo", action="store_true", help="переспросить уже оценённые (нужно подтверждение или --yes)")
    ap.add_argument("--yes", action="store_true", help="подтвердить --redo без вопроса (для неинтерактивного запуска)")
    ap.add_argument("--force", action="store_true", help="игнорировать tools.typesafe = off в run-config")
    a = ap.parse_args(argv)
    out_dir = Path(a.out).resolve()
    out_path = out_dir / "data" / "typesafe-jev.json"
    props_path = out_dir / "data" / "proposals.json"
    if not props_path.exists():
        print("нет %s" % props_path, file=sys.stderr)
        return 1
    props = [p for p in json.loads(props_path.read_text(encoding="utf-8")) if isinstance(p, dict) and p.get("id")]
    cfg_path = out_dir / "build" / "run-config.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8")) if cfg_path.exists() else {}
    context = context_from_config(cfg)
    use_questions(cfg)
    todo = props[:a.limit] if a.limit else props
    prev = json.loads(out_path.read_text(encoding="utf-8")) if out_path.exists() else None
    prev_items = (prev or {}).get("items") or {}
    will = pending(todo, prev_items, a.redo)

    if a.dry_run:
        print("Вопросы (%d): %s" % (len(QUESTIONS), ", ".join(QUESTIONS)))
        if todo:
            print("Состояние для %s:" % todo[0]["id"])
            print(json.dumps(build_state(context, todo[0]), ensure_ascii=False, indent=2))
        print("Запросов было бы: %d из %d предложений%s (файл не записан)" % (
            len(will), len(todo), "; --redo — все заново" if a.redo else "; уже оценённые пропускаются"))
        return 0

    key = os.environ.get("TYPESAFE_API_KEY", "").strip()
    mode = str((cfg.get("tools") or {}).get("typesafe", "auto")).lower()
    reason = None
    if mode == "off" and not a.force:
        reason = "отключено в run-config (tools.typesafe = off)"
    elif not key:
        reason = "TYPESAFE_API_KEY не задан"
    if reason:
        doc = skeleton(prev, reason)
        write(out_path, doc)
        print("TypeSafe пропущен: %s → %s" % (reason, out_path))
        return 0

    print("Будет запросов: %d (предложений в выборке %d, уже оценено и пропускается %d%s)" % (
        len(will), len(todo), len(todo) - len(will), "; --redo" if a.redo else ""))
    if a.redo and will and not confirm_redo(len(will), a.yes):
        return 2
    doc = skeleton(prev, None)
    done = errors = 0
    model_name = None
    for p in todo:
        pid = p["id"]
        if pid in doc["items"] and not a.redo and "error" not in doc["items"][pid]:
            continue
        try:
            resp = ask(build_state(context, p), key)
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                doc["skipped"] = "доступ отклонён (HTTP %d)" % e.code
                write(out_path, doc)
                print("TypeSafe: доступ отклонён (HTTP %d) — остановлено" % e.code)
                return 0
            doc["items"][pid] = {"error": "HTTP %d" % e.code}
            errors += 1
        except (urllib.error.URLError, TimeoutError, ValueError) as e:
            doc["items"][pid] = {"error": type(e).__name__}
            errors += 1
        else:
            model_name = resp.get("model") or model_name
            item = parse_answers(resp)
            doc["items"][pid] = item
            done += 1
            print("%s p_success %.2f risk %.2f impact %s effort %s kano %s" % (
                pid, item.get("p_success", float("nan")), item.get("risk", float("nan")), item.get("impact"),
                item.get("effort"), item.get("kano")))
        if model_name:
            doc["model"] = model_name
        write(out_path, doc)
        time.sleep(0.2)
    write(out_path, doc)
    print("Готово: оценено %d, ошибок %d, всего в файле %d → %s" % (done, errors, len(doc["items"]), out_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
