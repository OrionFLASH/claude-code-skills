#!/usr/bin/env python3
"""Создаёт папку прогона <OUT> по run-config: подпапки, build/STATUS.md с чек-листом фаз, .gitignore для node-модулей.

  init_run.py <OUT>                  по <OUT>/build/run-config.json (его пишет intake.py)
  init_run.py <OUT> --status "фаза 3 готова: …"   дописать строку в STATUS.md (чекпоинт)
  init_run.py <OUT> --done 3         отметить фазу 3 выполненной в чек-листе
  init_run.py <OUT> --show           первый открытый пункт и последние чекпоинты (продолжение после обрыва)

Только стандартная библиотека.
"""
import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

DIRS = ["build/briefs", "research/specs", "research/experiments", "data", "charts/flows", "mockups/current", "mockups/concepts",
        "design-refs", "competitors/shots", "deliverables"]
PHASES = [
    (0, "Подготовка: папка, ветка, проверка инструментов (check_env), план"),
    (1, "Понимание продукта по репозиторию (repo_scan, issues_export) → research/product-understanding.md"),
    (2, "Запуск и изучение приложения (audit_site, ui-inventory, пути пользователя, токены дизайна)"),
    (3, "Тип продукта и адаптация акцентов"),
    (4, "Рынок: конкуренты, сообщества, спрос, события, право (субагенты) → data/*.json"),
    (5, "Реестр предложений: генераторы → merge_proposals → check_registry"),
    (6, "Оценка: score, validate_scores, typesafe_eval, model, charts, чувствительность"),
    (7, "Стратегия: разделы, спеки топ-N, эксперименты, Гант, Kanban, вопросы владельцу"),
    (8, "Макеты, блок-схемы, референсы дизайна, скриншоты конкурентов"),
    (9, "Сборка и QA: build_all (html, xlsx, pptx, pdf), check_links, smoke_html, REPORT.md"),
]


def status_path(out):
    return Path(out) / "build" / "STATUS.md"


def init(out):
    out = Path(out).resolve()
    cfgp = out / "build" / "run-config.json"
    cfg = json.loads(cfgp.read_text(encoding="utf-8")) if cfgp.exists() else {}
    for d in DIRS:
        (out / d).mkdir(parents=True, exist_ok=True)
    gi = out / ".gitignore"
    if not gi.exists():
        gi.write_text("build/node/\n*.tmp\n", encoding="utf-8")
    sp = status_path(out)
    if not sp.exists():
        s = cfg.get("strategy", {})
        head = ["# STATUS — стратегия %s" % cfg.get("product", {}).get("name", out.name), "",
                "Создано: %s. Глубина: %s, предложений ≥ %s, горизонт %s мес + %s г." % (
                    datetime.now().strftime("%Y-%m-%d %H:%M"), s.get("depth", "?"), s.get("proposals_min", "?"),
                    s.get("horizon_months", "?"), s.get("vision_years", "?")), "", "## Фазы"]
        head += ["- [ ] %d. %s" % (n, t) for n, t in PHASES]
        head += ["", "## Чекпоинты", ""]
        sp.write_text("\n".join(head), encoding="utf-8")
    print("OUT=%s" % out)
    return 0


def add_status(out, text):
    sp = status_path(out)
    with sp.open("a", encoding="utf-8") as f:
        f.write("- %s — %s\n" % (datetime.now().strftime("%Y-%m-%d %H:%M"), text.strip()))
    return 0


def mark_done(out, n):
    sp = status_path(out)
    s = sp.read_text(encoding="utf-8")
    s2 = re.sub(r"^- \[ \] %d\. " % n, "- [x] %d. " % n, s, count=1, flags=re.M)
    sp.write_text(s2, encoding="utf-8")
    return 0 if s2 != s else 1


def show(out):
    s = status_path(out).read_text(encoding="utf-8")
    m = re.search(r"^- \[ \] (\d+\. .*)$", s, re.M)
    print("Следующая фаза: %s" % (m.group(1) if m else "все фазы отмечены"))
    cps = re.findall(r"^- \d{4}-\d\d-\d\d .*$", s, re.M)
    for c in cps[-5:]:
        print(c)
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("out")
    ap.add_argument("--status")
    ap.add_argument("--done", type=int)
    ap.add_argument("--show", action="store_true")
    a = ap.parse_args(argv)
    if not status_path(a.out).exists() or not (a.status or a.done is not None or a.show):
        init(a.out)
    if a.status:
        add_status(a.out, a.status)
    if a.done is not None:
        return mark_done(a.out, a.done)
    if a.show:
        return show(a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
